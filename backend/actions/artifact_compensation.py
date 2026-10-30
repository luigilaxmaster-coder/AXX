"""Receipt-bound compensation of newly created files; no deletion or UI input.

Windows primitives are deliberately handle based. Primary contracts:
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle
https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle
Compensation admits only local NTFS with a nonzero file identity. Secure artifact
creation requires Windows ancestor leases; unsupported platforms fail closed
without a path-only fallback.
"""
from contextlib import contextmanager, ExitStack
import ctypes
import copy
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid


TOOL_ACTIONS = {'artifact_quarantine': 'quarantine', 'artifact_restore': 'restore'}
COMMAND_ACTIONS = {'axx.artifact.quarantine': 'quarantine', 'axx.artifact.restore': 'restore'}
PARAMETERS = {'source_operation_id': {'type': 'string', 'required': True, 'maxLength': 128},
    'source_receipt_hash': {'type': 'string', 'required': True, 'maxLength': 64},
    'expected_revision': {'type': 'integer', 'required': True, 'minimum': 0, 'maximum': 2147483647}}
MAX_BYTES = 1024 * 1024
SCHEMA = 'axx_created_file_v1'
QUARANTINE_DIRECTORY = '.axx-quarantine'
ACTIVE_OWNERS = set()
OWNER_LOCK = threading.RLock()


def quarantine_root(workspace):
    return Path(workspace) / QUARANTINE_DIRECTORY


def reserved_path(path):
    return any(part.casefold() == QUARANTINE_DIRECTORY for part in Path(path).parts)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_inputs(inputs):
    if (not isinstance(inputs, dict) or set(inputs) != set(PARAMETERS)
            or not isinstance(inputs['source_operation_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', inputs['source_operation_id'])
            or not isinstance(inputs['source_receipt_hash'], str) or not re.fullmatch('[a-f0-9]{64}', inputs['source_receipt_hash'])
            or type(inputs['expected_revision']) is not int or not 0 <= inputs['expected_revision'] <= 2147483647):
        raise ValueError('COMPENSATION_INPUT_INVALID')
    return dict(inputs)


class NativeUnavailable(ValueError):
    pass


class CompensationError(ValueError):
    pass


class FileInfo(ctypes.Structure):
    _fields_ = [('attributes', wintypes.DWORD), ('creation', wintypes.FILETIME),
        ('access', wintypes.FILETIME), ('write', wintypes.FILETIME), ('volume', wintypes.DWORD),
        ('size_high', wintypes.DWORD), ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
        ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]


class RenameInfo(ctypes.Structure):
    _fields_ = [('flags', wintypes.DWORD), ('root', wintypes.HANDLE), ('length', wintypes.DWORD), ('name', wintypes.WCHAR * 1)]


def _kernel():
    if os.name != 'nt':
        raise NativeUnavailable('COMPENSATION_PLATFORM_UNAVAILABLE')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.GetVolumeInformationByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    return kernel


def native_available():
    try:
        _kernel()
        return True
    except (NativeUnavailable, AttributeError, OSError):
        return False


def _path_key(path):
    return os.path.normcase(os.path.normpath(str(path)))


def _final_path(kernel, handle):
    buffer = ctypes.create_unicode_buffer(1024)
    length = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not 0 < length < len(buffer):
        raise NativeUnavailable('COMPENSATION_PATH_IDENTITY_UNAVAILABLE')
    value = buffer.value
    if value.startswith('\\\\?\\'):
        value = value[4:]
    return value


def _info(kernel, handle, *, directory=False, require_ntfs=True, max_bytes=MAX_BYTES):
    info = FileInfo()
    if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise NativeUnavailable('COMPENSATION_FILE_IDENTITY_UNAVAILABLE')
    index = (info.index_high << 32) | info.index_low
    size = (info.size_high << 32) | info.size_low
    if (require_ntfs and not index or info.attributes & (0x400 | 0x1000 | 0x40000 | 0x400000)
            or bool(info.attributes & 0x10) != directory or not directory and (info.links != 1 or size > max_bytes)):
        raise NativeUnavailable('COMPENSATION_FILE_IDENTITY_UNAVAILABLE')
    filesystem = ctypes.create_unicode_buffer(32)
    if require_ntfs and (not kernel.GetVolumeInformationByHandleW(handle, None, 0, None, None, None, filesystem, len(filesystem))
            or filesystem.value != 'NTFS'):
        raise NativeUnavailable('COMPENSATION_FILESYSTEM_UNAVAILABLE')
    return {'volume': '%08x' % info.volume, 'file_id': '%016x' % index,
        'created': str((info.creation.dwHighDateTime << 32) | info.creation.dwLowDateTime),
        'modified': str((info.write.dwHighDateTime << 32) | info.write.dwLowDateTime),
        'bytes': size, 'links': info.links}


def _birth(identity):
    return {key: identity[key] for key in ('volume', 'file_id', 'created')}


def _absent(path):
    kernel = _kernel()
    attributes = kernel.GetFileAttributesW(str(path))
    if attributes != 0xffffffff:
        return False
    if ctypes.get_last_error() in (2, 3):
        return True
    raise CompensationError('COMPENSATION_LOCATION_UNOBSERVABLE')


@contextmanager
def _open(kernel, path, *, directory=False, moving=False, require_ntfs=True, max_bytes=MAX_BYTES):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 512 * 1024 * 1024:
        raise ValueError('FILE_LEASE_SIZE_LIMIT_INVALID')
    # Deny delete on directories: none of the checked ancestors can be renamed
    # or replaced while the source and destination are resolved. Files deny
    # write/delete sharing across hashing and the rename of that SAME handle.
    # READ_ATTRIBUTES alone does not participate in all Windows share-delete
    # conflicts for directory renames. GENERIC_READ includes LIST_DIRECTORY,
    # making the no-delete-sharing lease effective before a child file opens.
    access = 0x80000000 | (0x10000 if moving and not directory else 0)
    share = 3 if directory else 1
    flags = 0x200000 | (0x2000000 if directory else 0)
    handle = kernel.CreateFileW(str(path), access, share, None, 3, flags, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise CompensationError('COMPENSATION_RESOURCE_UNAVAILABLE_' + ('DIRECTORY_' if directory else 'FILE_') + str(ctypes.get_last_error()))
    try:
        identity = _info(kernel, handle, directory=directory, require_ntfs=require_ntfs, max_bytes=max_bytes)
        if _path_key(_final_path(kernel, handle)) != _path_key(path):
            raise CompensationError('COMPENSATION_RESOURCE_CHANGED')
        yield handle, identity
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def _directories(kernel, path):
    path = Path(path)
    with ExitStack() as stack:
        result = None
        for ancestor in reversed((path, *path.parents)):
            result = stack.enter_context(_open(kernel, ancestor, directory=True))
        yield result


@contextmanager
def protected_creation(path, workspace=None):
    """Protect each parent BEFORE creating children or opening the new file."""
    from .tools import artifact_path_error
    path = Path(os.path.abspath(path))
    root = Path(os.path.abspath(workspace)) if workspace is not None else path.parent
    if artifact_path_error(str(path)) or not path.is_relative_to(root):
        raise CompensationError('ARTIFACT_CREATION_ROOT_UNSAFE')
    kernel = _kernel()  # No unsafe path-only fallback on unsupported platforms.
    with ExitStack() as stack:
        for directory in reversed((path.parent, *path.parent.parents)):
            if not directory.exists():
                if workspace is not None and not directory.is_relative_to(root):
                    raise CompensationError('ARTIFACT_CREATION_ROOT_UNAVAILABLE')
                directory.mkdir()
            stack.enter_context(_open(kernel, directory, directory=True, require_ntfs=False))
        yield path


def _hash_handle(kernel, handle, cancelled):
    digest, count = hashlib.sha256(), 0
    buffer = ctypes.create_string_buffer(65536)
    while True:
        if cancelled.is_set():
            raise CompensationError('COMPENSATION_CANCELLED')
        length = wintypes.DWORD()
        if not kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(length), None):
            raise CompensationError('COMPENSATION_READ_FAILED')
        if not length.value:
            break
        count += length.value
        if count > MAX_BYTES:
            raise CompensationError('COMPENSATION_RESOURCE_CHANGED')
        digest.update(buffer.raw[:length.value])
    return digest.hexdigest(), count


def creation_from_descriptor(descriptor, path, sha256, size):
    """Called only after successful exclusive creation, while its fd is alive."""
    if not native_available():
        return None
    try:
        import msvcrt
        kernel = _kernel()
        handle = msvcrt.get_osfhandle(descriptor)
        identity = _info(kernel, handle)
        if identity['bytes'] != size or _path_key(_final_path(kernel, handle)) != _path_key(path):
            return None
        return {'schema': SCHEMA, 'exclusive_create': True, 'verified': False, 'path': str(path),
            'birth_identity': _birth(identity), 'sha256': sha256, 'bytes': size,
            'method': 'windows_ntfs_creation_descriptor'}
    except (OSError, ValueError, AttributeError):
        return None  # Artifact creation remains useful; compensation is unavailable.


def observe_owned(path, creation, cancelled=None):
    from .tools import artifact_path_error
    if artifact_path_error(str(path)):
        raise CompensationError('COMPENSATION_RESOURCE_UNSAFE')
    cancelled = cancelled or threading.Event()
    kernel = _kernel()
    with _directories(kernel, Path(path).parent):
        with _open(kernel, path) as (handle, before):
            sha, size = _hash_handle(kernel, handle, cancelled)
            after = _info(kernel, handle)
            if (before != after or _birth(after) != creation['birth_identity']
                    or size != creation['bytes'] or sha != creation['sha256']):
                raise CompensationError('COMPENSATION_RESOURCE_CHANGED')
            if creation.get('verified') and creation.get('identity') != after:
                raise CompensationError('COMPENSATION_RESOURCE_CHANGED')
            return after


def rename_owned(source, destination, creation, workspace, cancelled):
    """No path-based replace/copy/delete fallback is permitted."""
    from .tools import artifact_path_error
    root, source, destination = Path(workspace), Path(source), Path(destination)
    if (any(artifact_path_error(str(path)) for path in (root, source, destination))
            or not source.is_relative_to(root) or not destination.is_relative_to(root) or source == destination):
        raise CompensationError('COMPENSATION_RESOURCE_UNSAFE')
    kernel = _kernel()
    with _directories(kernel, root):
        with _directories(kernel, source.parent):
            # A quarantine folder contains only newly named outputs. Never
            # remove it on cancellation; it might already contain other files.
            if destination.parent.name == QUARANTINE_DIRECTORY:
                destination.parent.mkdir(exist_ok=True)
            elif not destination.parent.is_dir():
                raise CompensationError('COMPENSATION_DESTINATION_PARENT_CHANGED')
            with _directories(kernel, destination.parent) as (parent_handle, parent_identity):
                with _open(kernel, source, moving=True) as (handle, before):
                    sha, size = _hash_handle(kernel, handle, cancelled)
                    if (_info(kernel, handle) != before or before != creation['identity']
                            or _birth(before) != creation['birth_identity'] or sha != creation['sha256']
                            or size != creation['bytes'] or before['volume'] != parent_identity['volume']):
                        raise CompensationError('COMPENSATION_RESOURCE_CHANGED')
                    if cancelled.is_set():
                        raise CompensationError('COMPENSATION_CANCELLED')
                    # FILE_RENAME_INFO accepts an absolute destination. All its
                    # ancestor handles remain open without delete sharing, so
                    # this name cannot be redirected between validation/rename.
                    name = str(destination).encode('utf-16-le')
                    # Keep a terminating WCHAR even though FileNameLength excludes
                    # it. The Win32 wrapper accepts a NUL-terminated DOS path.
                    buffer = ctypes.create_string_buffer(max(ctypes.sizeof(RenameInfo), RenameInfo.name.offset + len(name) + ctypes.sizeof(wintypes.WCHAR)))
                    header = RenameInfo.from_buffer(buffer)
                    header.flags, header.root, header.length = 0, None, len(name)
                    ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.name.offset, name, len(name))
                    if not kernel.SetFileInformationByHandle(handle, 3, buffer, len(buffer)):
                        raise CompensationError('COMPENSATION_RENAME_REFUSED_' + str(ctypes.get_last_error()))
                    try:
                        after = _info(kernel, handle)
                        # NTFS name tunneling can restore a former creation time
                        # at the destination. This STILL OPEN protected handle
                        # proves the same volume/file ID; no other field may vary.
                        if after | {'created': before['created']} != before:
                            raise CompensationError('COMPENSATION_RENAME_IDENTITY_UNCERTAIN')
                    except CompensationError as exc:
                        raise CompensationError('COMPENSATION_RENAME_UNCERTAIN') from exc
                    except Exception as exc:
                        raise CompensationError('COMPENSATION_RENAME_UNCERTAIN') from exc
                # Resolve a fresh destination entry after closing the renamed
                # file object; ancestors remain protected throughout verification.
                try:
                    deadline = time.monotonic() + .25
                    while True:
                        try:
                            with _open(kernel, destination) as (_, destination_identity):
                                if destination_identity != after:
                                    raise CompensationError('COMPENSATION_RENAME_IDENTITY_UNCERTAIN')
                            break
                        except CompensationError as exc:
                            if (str(exc) not in ('COMPENSATION_RESOURCE_UNAVAILABLE_FILE_2',
                                    'COMPENSATION_RESOURCE_UNAVAILABLE_FILE_3', 'COMPENSATION_RESOURCE_UNAVAILABLE_FILE_32')
                                    or time.monotonic() >= deadline):
                                raise
                            # Read back only. The rename is NEVER dispatched twice.
                            time.sleep(.01)
                except Exception as exc:
                    raise CompensationError('COMPENSATION_RENAME_UNCERTAIN') from exc
                return after


def initialize(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS artifact_compensations(
            source_operation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
            state TEXT NOT NULL, operation_id TEXT, payload TEXT NOT NULL)''')


def load_source(db, workspace, source_operation_id):
    row = db.execute('SELECT state,result_json FROM command_runs WHERE operation_id=?', (source_operation_id,)).fetchone()
    if not row:
        raise CompensationError('COMPENSATION_SOURCE_UNKNOWN')
    command = json.loads(row[1])
    if row[0] != 'succeeded' or command.get('state') != 'succeeded' or command.get('command_id') != 'axx.artifact.write' or command.get('postconditions_passed') is not True:
        raise CompensationError('COMPENSATION_CREATION_NOT_VERIFIED')
    action_id = 'cmd-' + hashlib.sha256(source_operation_id.encode()).hexdigest()
    action_row = db.execute('SELECT state,inputs_json,result_json FROM operations WHERE operation_id=?', (action_id,)).fetchone()
    if not action_row:
        raise CompensationError('COMPENSATION_CREATION_RECEIPT_MISSING')
    action, inputs = json.loads(action_row[2]), json.loads(action_row[1])
    creation = (action.get('evidence') or {}).get('creation_receipt')
    path = (action.get('output') or {}).get('path')
    expected = (Path(workspace) / command['inputs']['path']).absolute()
    if (action_row[0] != 'succeeded' or action.get('state') != 'succeeded' or action.get('tool_name') != 'file_artifact_writer'
            or action.get('postconditions_passed') is not True or command.get('action_operation_id') != action_id
            or not isinstance(creation, dict) or creation.get('schema') != SCHEMA or creation.get('verified') is not True
            or creation.get('exclusive_create') is not True or not isinstance(path, str)
            or _path_key(path) != _path_key(expected) or not expected.is_relative_to(Path(workspace))
            or _path_key(creation.get('path', '')) != _path_key(expected) or inputs.get('path') != path
            or inputs.get('content') != command['inputs'].get('content')
            or creation.get('sha256') != (action.get('output') or {}).get('sha256')
            or creation.get('sha256') != hashlib.sha256(command['inputs']['content'].encode('utf-8')).hexdigest()
            or creation.get('bytes') != len(command['inputs']['content'].encode('utf-8'))
            or (command.get('evidence') or {}).get('creation_receipt') != creation
            or command.get('output') != action.get('output')):
        raise CompensationError('COMPENSATION_OWNERSHIP_NOT_PROVEN')
    core = {'source_operation_id': source_operation_id, 'action_operation_id': action_id,
        'task_id': command.get('conversation_id') or source_operation_id, 'creation': creation,
        'command_inputs': command['inputs'], 'action_inputs': inputs}
    source_hash = hashlib.sha256(canonical(core).encode()).hexdigest()
    quarantine = quarantine_root(workspace) / (hashlib.sha256(source_operation_id.encode()).hexdigest() + '.artifact')
    record = relationship(db, source_operation_id)
    owned_creation = record.get('current_creation') or creation
    if (record.get('current_creation') and (record.get('source_receipt_hash') != source_hash
            or any(owned_creation['birth_identity'][key] != creation['birth_identity'][key] for key in ('volume', 'file_id')))):
        raise CompensationError('COMPENSATION_OWNERSHIP_NOT_PROVEN')
    return core | {'source_receipt_hash': source_hash, 'path': path, 'quarantine_path': str(quarantine),
        'conversation_id': command.get('conversation_id'), 'owned_creation': owned_creation}


def relationship(db, source_operation_id):
    row = db.execute('SELECT payload FROM artifact_compensations WHERE source_operation_id=?', (source_operation_id,)).fetchone()
    return json.loads(row[0]) if row else {'state': 'present', 'revision': 0, 'operation_id': None}


def project_relationship(db, result):
    row = db.execute('SELECT payload FROM artifact_compensations WHERE source_operation_id=?', (result.get('source_operation_id') or result['operation_id'],)).fetchone()
    if not row:
        return result
    record = json.loads(row[0])
    proof = record.get('result') or {}
    restored = record['state'] == 'present' and proof.get('state') == 'present' and bool(proof.get('verified_at'))
    return result | {'compensation': {key: record.get(key) for key in ('state', 'revision', 'operation_id', 'quarantine_path', 'source_operation_id')}
        | {'available_current': True if restored else None if record['state'] == 'present' else False,
           'verification': {key: proof.get(key) for key in ('verified_at', 'verification', 'identity', 'sha256', 'bytes', 'current_path')}
               if proof.get('verified_at') else None}}


def preview(db, workspace, source_operation_id):
    result = {'source_operation_id': source_operation_id, 'available': False, 'action': None,
        'source_receipt_hash': None, 'task_id': None, 'compensation': relationship(db, source_operation_id),
        'capability': {'native_available': native_available(), 'filesystem_scope': 'local_ntfs_only', 'creation_receipt_required': True}}
    try:
        if not native_available():
            raise NativeUnavailable('COMPENSATION_PLATFORM_UNAVAILABLE')
        source = load_source(db, workspace, source_operation_id)
        record = result['compensation']
        record.update(source_operation_id=source_operation_id, quarantine_path=source['quarantine_path'])
        result.update(source_receipt_hash=source['source_receipt_hash'], task_id=source['task_id'],
            artifact={'path': source['path'], 'sha256': source['creation']['sha256'], 'bytes': source['creation']['bytes'], 'identity': source['owned_creation']['identity']})
        if record['state'] not in ('present', 'quarantined'):
            raise CompensationError('COMPENSATION_RECONCILIATION_REQUIRED')
        action = 'quarantine' if record['state'] == 'present' else 'restore'
        current = source['path'] if action == 'quarantine' else source['quarantine_path']
        destination = source['quarantine_path'] if action == 'quarantine' else source['path']
        observe_owned(current, source['owned_creation'])
        if not _absent(destination):
            raise CompensationError('COMPENSATION_DESTINATION_OCCUPIED')
        result.update(available=True, action=action, reason=None)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # No file text or system diagnostic is public policy evidence.
        result['reason'] = 'COMPENSATION_UNAVAILABLE: falta prueba vigente de propiedad o el recurso requiere revisión.'
        result['reason_code'] = str(exc) if isinstance(exc, (CompensationError, NativeUnavailable)) and re.fullmatch(r'COMPENSATION_[A-Z0-9_]+', str(exc)) else 'COMPENSATION_UNAVAILABLE'
    return result


def _save(db, source_id, record):
    db.execute('''INSERT INTO artifact_compensations VALUES(?,?,?,?,?)
        ON CONFLICT(source_operation_id) DO UPDATE SET revision=excluded.revision,state=excluded.state,operation_id=excluded.operation_id,payload=excluded.payload''',
        (source_id, record['revision'], record['state'], record['operation_id'], canonical(record)))


def _cas_save(db, source_id, record, operation_id, revision, states):
    changed = db.execute('''UPDATE artifact_compensations SET revision=?,state=?,operation_id=?,payload=?
        WHERE source_operation_id=? AND operation_id=? AND revision=? AND state IN (''' + ','.join('?' for _ in states) + ')',
        (record['revision'], record['state'], record['operation_id'], canonical(record), source_id, operation_id, revision, *states)).rowcount
    if changed != 1:
        raise CompensationError('COMPENSATION_CLAIM_CHANGED')


def _owner_alive(record):
    owner = record.get('owner') or {}
    if owner.get('active') is not True:
        return False
    if owner.get('pid') == os.getpid():
        with OWNER_LOCK:
            return owner.get('nonce') in ACTIVE_OWNERS
    try:
        import psutil
        process = psutil.Process(owner['pid'])
        return process.is_running() and process.create_time() == owner['started']
    except (KeyError, ImportError):
        return True
    except Exception as exc:
        import psutil
        return not isinstance(exc, psutil.NoSuchProcess)  # Unknown owner is never a dead-owner proof.


def reconcile_result(db, workspace, command):
    """Observe both names and update only metadata; NEVER invoke rename again."""
    inputs = validate_inputs(command['inputs'])
    source = load_source(db, workspace, inputs['source_operation_id'])
    action_id = 'cmd-' + hashlib.sha256(command['operation_id'].encode()).hexdigest()
    if source['source_receipt_hash'] != inputs['source_receipt_hash']:
        raise CompensationError('COMPENSATION_RECEIPT_CHANGED')
    record = relationship(db, inputs['source_operation_id'])
    if _owner_alive(record):
        raise CompensationError('COMPENSATION_OWNER_STILL_ACTIVE')
    previous_state, previous_revision = record['state'], record['revision']
    if (record.get('operation_id') != action_id or record['revision'] not in (inputs['expected_revision'], inputs['expected_revision'] + 1)):
        raise CompensationError('COMPENSATION_REVISION_CHANGED')
    original_absent, quarantine_absent = _absent(source['path']), _absent(source['quarantine_path'])
    if original_absent == quarantine_absent:
        raise CompensationError('COMPENSATION_LOCATIONS_AMBIGUOUS')
    observed_state = 'quarantined' if original_absent else 'present'
    current = source['quarantine_path'] if original_absent else source['path']
    identity = observe_owned(current, source['owned_creation'])
    intended = 'quarantined' if command['command_id'] == 'axx.artifact.quarantine' else 'present'
    complete = observed_state == intended
    revision = inputs['expected_revision'] + int(complete)
    if not complete and record['revision'] != revision:
        raise CompensationError('COMPENSATION_REVISION_CHANGED')
    output = {'source_operation_id': inputs['source_operation_id'], 'source_receipt_hash': inputs['source_receipt_hash'],
        'source_action_operation_id': source['action_operation_id'], 'original_path': source['path'],
        'quarantine_path': source['quarantine_path'], 'current_path': current, 'state': observed_state,
        'revision': revision, 'sha256': source['creation']['sha256'], 'bytes': source['creation']['bytes'], 'identity': identity}
    output.update(verified_at=time.time(), verification='windows_owned_file_location_readback')
    record.update(state=observed_state, revision=revision, result=output)
    _cas_save(db, inputs['source_operation_id'], record, action_id, previous_revision, (previous_state,))
    return command | {'state': 'succeeded' if complete else 'failed', 'postconditions_passed': complete,
        'output': output, 'effect_status': 'confirmed' if complete else 'not_observed',
        'error': None if complete else {'code': 'COMPENSATION_NOT_MOVED', 'message': 'El archivo sigue en su ubicación anterior; no se repitió la compensación.'},
        'evidence': {'verification': 'windows_owned_file_location_readback', 'reconciled': True,
            'reconciliation_required': False, 'effect_uncertain': False, 'no_bytes_deleted': True, 'redispatched': False}}


class ArtifactCompensationTool:
    version = '1.0.0'
    description = 'Reversible, receipt-bound quarantine or restoration of a newly created Axx artifact; no deletion'

    def __init__(self, action):
        self.action = action
        self.name = 'artifact_' + action

    def verify_preconditions(self, inputs):
        try:
            validate_inputs(inputs)
            if not native_available():
                raise NativeUnavailable('COMPENSATION_PLATFORM_UNAVAILABLE')
            return True, 'Typed receipt reference; ownership is revalidated at the effect boundary'
        except ValueError:
            return False, 'COMPENSATION_INPUT_OR_PLATFORM_UNAVAILABLE'

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='COMPENSATION_RUNTIME_REQUIRED')

    def execute_admitted(self, inputs, workspace_root, cancelled, runtime, operation_id):
        from .tools import ToolResult
        claimed, renamed, dispatching = False, False, False
        nonce = uuid.uuid4().hex
        with OWNER_LOCK:
            ACTIVE_OWNERS.add(nonce)
        try:
            validate_inputs(inputs)
            source = load_source(runtime.db, workspace_root, inputs['source_operation_id'])
            if source['source_receipt_hash'] != inputs['source_receipt_hash']:
                raise CompensationError('COMPENSATION_RECEIPT_CHANGED')
            expected_state = 'present' if self.action == 'quarantine' else 'quarantined'
            runtime.db.execute('BEGIN IMMEDIATE')
            try:
                record = relationship(runtime.db, inputs['source_operation_id'])
                if record['revision'] != inputs['expected_revision'] or record['state'] != expected_state:
                    raise CompensationError('COMPENSATION_REVISION_CHANGED')
                record.update(state='moving_' + self.action, operation_id=operation_id,
                    source_operation_id=inputs['source_operation_id'], source_receipt_hash=inputs['source_receipt_hash'],
                    quarantine_path=source['quarantine_path'], action=self.action, prior_state=expected_state)
                import psutil
                record['owner'] = {'pid': os.getpid(), 'started': psutil.Process().create_time(), 'nonce': nonce, 'active': True}
                _save(runtime.db, inputs['source_operation_id'], record)  # Transaction has checked state/revision exclusively.
                runtime.db.commit(); claimed = True
            except Exception:
                runtime.db.rollback(); raise
            current, destination = ((source['path'], source['quarantine_path']) if self.action == 'quarantine'
                                    else (source['quarantine_path'], source['path']))
            dispatching = True
            identity = rename_owned(current, destination, source['owned_creation'], workspace_root, cancelled)
            renamed = True
            owned_creation = copy.deepcopy(source['owned_creation'])
            owned_creation.update(identity=identity, birth_identity=_birth(identity))
            with runtime.db:
                record.update(current_creation=owned_creation,
                    identity_transition={'before': source['owned_creation']['identity'], 'after': identity,
                                         'method': 'same_protected_windows_handle_rename', 'operation_id': operation_id})
                _cas_save(runtime.db, inputs['source_operation_id'], record, operation_id,
                    inputs['expected_revision'], ('moving_' + self.action,))
            identity = observe_owned(destination, owned_creation)
            if not _absent(current):
                raise CompensationError('COMPENSATION_RENAME_UNCERTAIN')
            output = {'source_operation_id': inputs['source_operation_id'], 'source_receipt_hash': inputs['source_receipt_hash'],
                'source_action_operation_id': source['action_operation_id'], 'original_path': source['path'],
                'quarantine_path': source['quarantine_path'], 'current_path': destination,
                'state': 'quarantined' if self.action == 'quarantine' else 'present', 'revision': record['revision'] + 1,
                'sha256': source['creation']['sha256'], 'bytes': source['creation']['bytes'], 'identity': identity,
                'verified_at': time.time(), 'verification': 'windows_handle_rename_sha256'}
            with runtime.db:
                record.update(state=output['state'], revision=output['revision'], result=output)
                record['owner']['active'] = False
                _cas_save(runtime.db, inputs['source_operation_id'], record, operation_id,
                    inputs['expected_revision'], ('moving_' + self.action,))
            return ToolResult(True, output=output, evidence={'verification': 'windows_handle_rename_sha256',
                'no_bytes_deleted': True, 'original_not_overwritten': True, 'compensation': True})
        except Exception as exc:
            if claimed:
                # Rename may have succeeded even if its acknowledgement was lost.
                uncertain = (renamed or str(exc).startswith('COMPENSATION_RENAME_') and str(exc).endswith('UNCERTAIN')
                    or dispatching and not isinstance(exc, (CompensationError, NativeUnavailable)))
                with runtime.db:
                    record.update(state='unknown' if uncertain else expected_state)
                    record['owner']['active'] = False
                    try:
                        _cas_save(runtime.db, inputs['source_operation_id'], record, operation_id,
                            inputs['expected_revision'], ('moving_' + self.action,))
                    except CompensationError:
                        uncertain = True  # A stale owner can never overwrite a newer claim.
            else:
                uncertain = False
            return ToolResult(False, error='COMPENSATION_NOT_VERIFIED: revisa el recibo y las ubicaciones antes de otra acción.',
                evidence={'effect_uncertain': uncertain, 'no_bytes_deleted': True, 'cancelled': cancelled.is_set() and not uncertain,
                    'diagnostic_code': str(exc) if isinstance(exc, (CompensationError, NativeUnavailable)) and re.fullmatch(r'COMPENSATION_[A-Z0-9_]+', str(exc)) else 'COMPENSATION_INTERNAL_INTERRUPTION',
                    'native_diagnostic': str(exc.__cause__) if isinstance(exc.__cause__, (CompensationError, NativeUnavailable)) and re.fullmatch(r'COMPENSATION_[A-Z0-9_]+', str(exc.__cause__)) else None})
        finally:
            with OWNER_LOCK:
                ACTIVE_OWNERS.discard(nonce)

    def verify_postconditions(self, inputs, result):
        if not result.success:
            return False, result.error
        output = result.output
        if (output.get('source_operation_id') != inputs['source_operation_id']
                or output.get('source_receipt_hash') != inputs['source_receipt_hash']
                or output.get('revision') != inputs['expected_revision'] + 1):
            result.evidence['effect_uncertain'] = True
            return False, 'COMPENSATION_POSTCONDITION_CHANGED'
        return True, 'The same owned file was moved by handle without overwriting or deleting bytes'
