"""Explicit, reviewed process execution; never a sandbox or a code generator.

Only a newly created process and its Job Object are terminated. Output is evidence,
not instructions. A zero exit code does not certify application effects. Interpreter
arguments require the same exact user review as executable and working directory.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import subprocess
import threading
import time

from backend.inference.process_manager import (
    WindowsJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
)
from .file_inspection import validate_path, hash_file

LOG = logging.getLogger('axx.process_runner')
MAX_OUTPUT = 64 * 1024
ENV_NAMES = frozenset('systemroot windir path temp tmp userprofile appdata localappdata programdata programfiles programfiles(x86) commonprogramfiles comspec number_of_processors processor_architecture username computername'.split())
PARAMETERS = {
    'type': 'object', 'additionalProperties': False,
    'required': ['executable', 'args', 'cwd', 'timeout_s'],
    'properties': {
        'executable': {'type': 'string', 'minLength': 1, 'maxLength': 240},
        'args': {'type': 'array', 'maxItems': 64, 'items': {'type': 'string', 'maxLength': 8192}},
        'cwd': {'type': 'string', 'minLength': 1, 'maxLength': 240},
        'timeout_s': {'type': 'integer', 'minimum': 1, 'maximum': 120},
        'expected_artifact': {'type': 'string', 'minLength': 1, 'maxLength': 240},
    },
}


def _directory(raw):
    from .tools import artifact_path_error
    error = artifact_path_error(raw)
    if error:
        raise ValueError(error)
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('cwd debe ser un directorio local absoluto existente')
    return path.resolve(strict=True)


def validate_inputs(inputs):
    if not isinstance(inputs, dict) or set(inputs) - set(PARAMETERS['properties']) or not set(PARAMETERS['required']) <= set(inputs):
        raise ValueError('Parámetros de proceso incompletos o desconocidos')
    executable = validate_path(inputs['executable'])
    # Windows may execute batch files through a shell even with shell=False.
    if executable.suffix.lower() != '.exe':
        raise ValueError('El ejecutable debe ser un archivo .exe; no se admiten lanzadores batch')
    _directory(inputs['cwd'])
    args = inputs['args']
    if not isinstance(args, list) or len(args) > 64 or any(not isinstance(arg, str) or len(arg) > 8192 or '\0' in arg for arg in args):
        raise ValueError('args debe contener hasta 64 argumentos literales válidos')
    try:
        command_bytes = subprocess.list2cmdline([str(executable), *args]).encode('utf-16-le')
    except UnicodeError as exc:
        raise ValueError('Argumentos Unicode inválidos') from exc
    if len(command_bytes) > 65532:
        raise ValueError('La línea de proceso supera el límite de Windows')
    if type(inputs['timeout_s']) is not int or not 1 <= inputs['timeout_s'] <= 120:
        raise ValueError('timeout_s debe ser un entero entre 1 y 120')
    if 'expected_artifact' in inputs:
        raw = inputs['expected_artifact']
        if not isinstance(raw, str) or not raw or len(raw) > 240:
            raise ValueError('expected_artifact debe ser una ruta relativa no vacía')
        path = Path(raw)
        if path.is_absolute() or path.drive or path.root or '..' in path.parts:
            raise ValueError('El artefacto debe permanecer dentro del workspace')


def _artifact_path(raw, workspace):
    from .tools import artifact_path_error
    root = _directory(str(workspace))
    path = root / raw
    error = artifact_path_error(str(path))
    if error:
        raise ValueError(error)
    if not path.resolve().is_relative_to(root):
        raise ValueError('El artefacto está fuera del workspace')
    return path


def _api(kernel, name, args, result):
    call = getattr(kernel, name)
    call.argtypes, call.restype = args, result
    return call


class ProcessEffectUnknown(RuntimeError):
    """A child may have begun work before custody/readback failed."""


@contextmanager
def _locked_executable(path):
    if os.name != 'nt':
        raise ValueError('La ejecución con custodia de procesos requiere Windows')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    handle = _api(kernel, 'CreateFileW', [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE)(
        path, 0x80000000, 1, None, 3, 0x80, None)
    if handle == C.c_void_p(-1).value:
        raise OSError('No se pudo proteger el ejecutable contra sustitución durante el arranque')
    try:
        yield
    finally:
        _api(kernel, 'CloseHandle', [W.HANDLE], W.BOOL)(handle)


class _ThreadEntry(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('thread_id', W.DWORD),
                ('owner_pid', W.DWORD), ('base_priority', W.LONG), ('delta_priority', W.LONG), ('flags', W.DWORD)]


class _Accounting(C.Structure):
    _fields_ = [('user', C.c_int64), ('kernel', C.c_int64), ('period_user', C.c_int64), ('period_kernel', C.c_int64),
                ('faults', W.DWORD), ('total', W.DWORD), ('active', W.DWORD), ('terminated', W.DWORD)]


def _query_job(kernel, job, info_class, info):
    if not _api(kernel, 'QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL)(
            job.handle, info_class, C.byref(info), C.sizeof(info), None):
        raise OSError('No se pudieron comprobar los límites del Job Object')
    return info


def _resume_owned(kernel, process):
    """The suspended child has exactly one initial thread; no name/PID kill scans."""
    snapshot = _api(kernel, 'CreateToolhelp32Snapshot', [W.DWORD, W.DWORD], W.HANDLE)(4, 0)
    if snapshot == C.c_void_p(-1).value:
        raise OSError('No se pudo observar el hilo inicial suspendido')
    close = _api(kernel, 'CloseHandle', [W.HANDLE], W.BOOL)
    thread_ids = []
    try:
        entry = _ThreadEntry(); entry.dwSize = C.sizeof(entry)
        first = _api(kernel, 'Thread32First', [W.HANDLE, C.POINTER(_ThreadEntry)], W.BOOL)
        following = _api(kernel, 'Thread32Next', [W.HANDLE, C.POINTER(_ThreadEntry)], W.BOOL)
        available = first(snapshot, C.byref(entry))
        while available:
            if entry.owner_pid == process.pid:
                thread_ids.append(entry.thread_id)
            available = following(snapshot, C.byref(entry))
    finally:
        close(snapshot)
    if len(thread_ids) != 1 or process.poll() is not None:
        raise OSError('No se pudo identificar de forma única el hilo del proceso creado')
    thread = _api(kernel, 'OpenThread', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)(2 | 0x40, False, thread_ids[0])
    if not thread:
        raise OSError('No se pudo abrir el hilo inicial')
    try:
        if _api(kernel, 'GetProcessIdOfThread', [W.HANDLE], W.DWORD)(thread) != process.pid:
            raise OSError('El hilo ya no pertenece al proceso creado')
        if _api(kernel, 'ResumeThread', [W.HANDLE], W.DWORD)(thread) != 1:
            raise ProcessEffectUnknown('No se confirmó el arranque del hilo suspendido')
    finally:
        close(thread)


def _stop_owned(kernel, process, job):
    """No taskkill fallback: handles and our verified job are the entire scope."""
    try:
        if not _api(kernel, 'TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL)(job.handle, 1):
            raise OSError('No se confirmó la terminación del Job Object propio')
        process.wait(timeout=3)
        deadline = time.monotonic() + 2
        while _query_job(kernel, job, 1, _Accounting()).active:
            if time.monotonic() >= deadline:
                raise OSError('La terminación de descendientes no pudo confirmarse')
            time.sleep(.02)
    finally:
        job.close()
        if process.poll() is None:
            process.kill()  # Popen retains the exact native handle, not a PID lookup.
            process.wait(timeout=3)


def _spawn_owned(command, cwd, env, cancelled):
    if os.name != 'nt':
        raise ValueError('La ejecución con custodia de procesos requiere Windows')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    job = WindowsJobObject()
    process = None
    try:
        if not job.handle:
            raise OSError('Windows no creó un Job Object')
        info = _query_job(kernel, job, 9, JOBOBJECT_EXTENDED_LIMIT_INFORMATION())
        if info.BasicLimitInformation.LimitFlags != JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE:
            raise OSError('El Job Object no garantiza cancelación sin escape de descendientes')
        process = subprocess.Popen(command, executable=command[0], cwd=cwd, env=env, shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW | 4)
        if not job.assign_process(process._handle):
            raise OSError('El proceso suspendido no pudo asociarse al Job Object')
        created, exited, kernel_time, user_time = (W.FILETIME() for _ in range(4))
        if not _api(kernel, 'GetProcessTimes', [W.HANDLE, *([C.POINTER(W.FILETIME)] * 4)], W.BOOL)(
                process._handle, C.byref(created), C.byref(exited), C.byref(kernel_time), C.byref(user_time)):
            raise OSError('No se pudo leer la identidad temporal del proceso')
        birth = str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        if cancelled.is_set():
            raise ValueError('Ejecución cancelada antes de activar el proceso')
        _resume_owned(kernel, process)
        return process, job, kernel, birth
    except BaseException:
        # Even assignment failure leaves a suspended child, terminated by its handle.
        job.close()
        if process is not None:
            if process.poll() is None:
                process.kill(); process.wait(timeout=3)
            for pipe in (process.stdout, process.stderr):
                pipe.close()
        raise


def run_process(inputs, workspace_root, cancelled=None):
    cancelled = cancelled or threading.Event()
    validate_inputs(inputs)
    if cancelled.is_set():
        return {'success': False, 'error': 'Proceso cancelado antes de ejecutar', 'evidence': {'cancelled': True}}
    artifact = _artifact_path(inputs['expected_artifact'], workspace_root) if 'expected_artifact' in inputs else None
    if artifact is not None and artifact.exists():
        raise ValueError('El artefacto esperado ya existe; no se autoriza sobrescribirlo')
    command = [str(Path(inputs['executable']).resolve(strict=True)), *inputs['args']]
    env = {key: value for key, value in os.environ.items() if key.lower() in ENV_NAMES}
    with _locked_executable(command[0]):
        executable = hash_file(command[0], cancelled)
        validate_inputs(inputs)  # Recheck local paths immediately before creation.
        process, job, kernel, birth = _spawn_owned(command, inputs['cwd'], env, cancelled)
    LOG.info('Reviewed process started pid=%s birth=%s', process.pid, birth)
    buffers = [bytearray(), bytearray()]
    overflow, read_error = threading.Event(), threading.Event()
    def collect(pipe, target):
        try:
            while chunk := pipe.read(4096):
                remaining = MAX_OUTPUT - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    break
        except OSError:
            read_error.set()
        finally:
            pipe.close()
    readers = [threading.Thread(target=collect, args=(pipe, target), daemon=True)
               for pipe, target in zip((process.stdout, process.stderr), buffers)]
    status, error, cleanup_verified = 'exited', None, False
    try:
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + inputs['timeout_s']
        while process.poll() is None:
            if cancelled.is_set():
                status = 'cancelled'; break
            if overflow.is_set():
                status = 'output_limit'; break
            if time.monotonic() >= deadline:
                status = 'timeout'; break
            cancelled.wait(.02)
    except Exception as exc:
        status, error = 'runtime_unknown', str(exc)
    finally:
        try:
            _stop_owned(kernel, process, job)
            cleanup_verified = True
        except (OSError, subprocess.TimeoutExpired) as exc:
            status, error = 'cleanup_unknown', str(exc)
            LOG.warning('Process cleanup unconfirmed pid=%s', process.pid)
        for reader in readers:
            if reader.ident is not None:
                reader.join(2)
    if cleanup_verified:
        if cancelled.is_set():status = 'cancelled'
        elif overflow.is_set():status = 'output_limit'
        elif read_error.is_set() or any(reader.is_alive() for reader in readers):status = 'output_unknown'
    completed = status == 'exited' and process.returncode == 0
    output = {'pid': process.pid, 'process_started': birth, 'exit_code': process.returncode, 'status': status,
              'stdout': bytes(buffers[0]).decode('utf-8', errors='replace'),
              'stderr': bytes(buffers[1]).decode('utf-8', errors='replace'),
              'output_truncated': overflow.is_set(), 'output_encoding': 'utf-8-replacement',
              'process_completed': completed, 'effect_status': 'unknown'}
    evidence = {'verification': 'process_exit', 'executable': executable, 'cwd': inputs['cwd'],
                'cancelled': cancelled.is_set(), 'cleanup_verified': cleanup_verified,
                'application_effect_verified': False, 'effect_uncertain': True, 'reconciliation_required': True}
    if completed and artifact is not None:
        try:
            artifact = _artifact_path(inputs['expected_artifact'], workspace_root)
            output['artifact'] = hash_file(str(artifact), cancelled)
            output['effect_status'] = 'artifact_created'
            evidence.update(verification='artifact_created', effect_uncertain=False, reconciliation_required=False,
                            artifact_verified=True, verification_scope='new_file_bytes_sha256_only')
        except (ValueError, OSError) as exc:
            completed, error = False, str(exc)
    if not completed and not error:
        error = f'Proceso no completado: {status}, código {process.returncode}; los efectos previos no se deshacen'
    LOG.info('Reviewed process finished pid=%s status=%s code=%s', process.pid, status, process.returncode)
    return {'success': completed, 'output': output, 'error': error, 'evidence': evidence}


class ProcessRunTool:
    name = 'process_run'
    version = '1.0.0'
    description = 'Ejecuta un proceso explícitamente revisado y verifica su salida o archivo nuevo'

    def verify_preconditions(self, inputs):
        try:
            validate_inputs(inputs)
            return True, 'Ejecutable y argumentos válidos; requieren revisión explícita'
        except (ValueError, TypeError, OSError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='La ejecución requiere el workspace autorizado')

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        try:
            return ToolResult(**run_process(inputs, workspace_root, cancelled))
        except ProcessEffectUnknown as exc:
            return ToolResult(False, error=str(exc), evidence={'effect_uncertain': True, 'reconciliation_required': True})
        except (ValueError, TypeError, OSError) as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        verified = (result.success and result.evidence.get('verification') == 'artifact_created'
                    and result.evidence.get('artifact_verified') is True
                    and result.output.get('effect_status') == 'artifact_created')
        return bool(verified), ('Archivo nuevo leído y firmado con SHA-256; formato y objetivo no certificados'
                                if verified else result.error or 'Sólo se comprobó la salida del proceso; efecto desconocido')
