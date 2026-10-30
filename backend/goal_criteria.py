"""Closed, read-only outcome evaluators and typed producer proposals.

No producer executes here. Current command availability, permissions and input
versions must still be admitted by the command/mission boundary.
"""
from contextlib import contextmanager, ExitStack
import copy
import csv
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat

from .actions import file_inspection
from .actions.tools import artifact_path_error

KINDS = {
    'text_exact': ('axx.artifact.write', 'exact_utf8_bytes', ['new_workspace_file']),
    'xlsx_from_csv': ('axx.office.excel.csv', 'csv_cells_types_formula_total', ['private_excel_runtime', 'new_workspace_xlsx']),
    'file_bundle': ('axx.file.bundle', 'selected_sources_copies_manifest_zip', ['new_workspace_directory']),
}
VERSION_KEYS = {'path', 'sha256', 'bytes', 'device', 'inode', 'mtime_ns'}


class CriterionProblem(ValueError):
    pass


def criteria_catalog():
    return [{'kind': kind, 'command_id': values[0], 'verification_scope': values[1],
             'producer_requirements': list(values[2])} for kind, values in KINDS.items()]


def _relative(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 180:
        raise ValueError('Ruta de criterio inválida')
    normalized = raw.replace('\\', '/')
    windows = PureWindowsPath(raw)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                *[f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in '123456789¹²³']}
    # The schema has no workspace yet: lexical checks must not inspect CWD.
    invalid_part = any(part.endswith((' ', '.')) or part.split('.', 1)[0].upper() in reserved
                       or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
                       for part in normalized.split('/'))
    if (windows.is_absolute() or windows.drive or windows.root or any(part in ('', '.', '..') for part in normalized.split('/'))
            or any(part.casefold() == '.axx-quarantine' for part in normalized.split('/')) or invalid_part):
        raise ValueError('La ruta del criterio debe permanecer dentro del workspace sin enlaces ni espacios reservados')
    return normalized


def validate_criteria(criteria, legacy_checks=()):
    if not isinstance(criteria, list) or len(criteria) > 8:
        raise ValueError('Selecciona hasta ocho criterios tipados')
    checked, ids, outputs = [], set(), []
    for row in criteria:
        if (not isinstance(row, dict) or set(row) != {'id', 'kind', 'parameters'}
                or not isinstance(row['id'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', row['id'])
                or row['id'] in ids or not isinstance(row['kind'], str) or row['kind'] not in KINDS or not isinstance(row['parameters'], dict)):
            raise ValueError('Criterio desconocido, ambiguo o inválido')
        ids.add(row['id'])
        kind, parameters = row['kind'], copy.deepcopy(row['parameters'])
        required = {'path', 'text'} if kind == 'text_exact' else {'source', 'destination', 'delimiter', 'numeric_column'} if kind == 'xlsx_from_csv' else {'paths', 'destination'}
        optional = {'archive_name', 'max_output_bytes'} if kind == 'file_bundle' else set()
        if not required <= set(parameters) or set(parameters) - required - optional:
            raise ValueError('Parámetros de criterio inválidos')
        output_field = 'path' if kind == 'text_exact' else 'destination'
        parameters[output_field] = _relative(parameters[output_field])
        if kind == 'text_exact':
            if not isinstance(parameters['text'], str) or len(parameters['text']) > 8000:
                raise ValueError('Texto esperado inválido')
        elif kind == 'xlsx_from_csv':
            parameters['source'] = _relative(parameters['source'])
            if (not parameters['source'].lower().endswith('.csv') or not parameters['destination'].lower().endswith('.xlsx')
                    or parameters['delimiter'] not in (',', ';', '\t') or not isinstance(parameters['numeric_column'], str)
                    or not 1 <= len(parameters['numeric_column']) <= 200):
                raise ValueError('Contrato CSV/XLSX inválido')
        else:
            paths = parameters['paths']
            if not isinstance(paths, list) or not 1 <= len(paths) <= 100:
                raise ValueError('Selecciona de uno a cien orígenes explícitos')
            parameters['paths'] = [_relative(path) for path in paths]
            folded = [path.casefold() for path in parameters['paths']]
            names = [path.rsplit('/', 1)[-1].casefold() for path in parameters['paths']]
            archive = parameters.get('archive_name')
            if archive is not None and (not isinstance(archive, str) or len(archive) > 100 or _relative(archive) != archive
                    or '/' in archive or not archive.lower().endswith('.zip')):
                raise ValueError('Nombre ZIP inválido')
            if (len(set(folded)) != len(paths) or len(set(names)) != len(paths)
                    or any(name in {'axx-manifest.json', archive.casefold() if archive else ''} for name in names)):
                raise ValueError('Orígenes o nombres ambiguos')
            if 'max_output_bytes' in parameters and (type(parameters['max_output_bytes']) is not int
                    or not 1 <= parameters['max_output_bytes'] <= 1073741824):
                raise ValueError('Presupuesto de salida inválido')
        output = parameters[output_field].casefold()
        inputs = parameters.get('paths', [parameters['source']] if 'source' in parameters else [])
        if any(path.casefold() == output or kind == 'file_bundle' and path.casefold().startswith(output + '/') for path in inputs):
            raise ValueError('Un criterio no puede consumir su propio destino nuevo')
        normalized = {'id': row['id'], 'kind': kind, 'parameters': parameters}
        for other_output, other in outputs:
            if output == other_output:
                if kind != other['kind'] or parameters != other['parameters']:
                    raise ValueError('Los criterios contradicen el mismo destino')
            elif output.startswith(other_output + '/') or other_output.startswith(output + '/'):
                raise ValueError('Los destinos de criterios se solapan')
        for check in legacy_checks:
            legacy = _relative(check['path']).casefold()
            if legacy == output and (kind != 'text_exact' or check['text'] != parameters['text']):
                raise ValueError('El criterio contradice la comprobación legacy')
            if legacy.startswith(output + '/') or output.startswith(legacy + '/'):
                raise ValueError('El criterio solapa una comprobación legacy')
        outputs.append((output, normalized)); checked.append(normalized)
    return checked


def _cancel(cancelled):
    if cancelled.is_set():
        raise CriterionProblem('CANCELLED')


def _root(root):
    path = Path(os.path.abspath(root))
    if artifact_path_error(str(path)) or not path.is_dir():
        raise CriterionProblem('PATH_UNSAFE')
    resolved = path.resolve(strict=True)
    if os.path.normcase(str(resolved)) != os.path.normcase(str(path)):
        raise CriterionProblem('PATH_UNSAFE')
    return resolved


def _safe(root, relative):
    path = root / _relative(relative)
    if artifact_path_error(str(path)) or not path.resolve().is_relative_to(root):
        raise CriterionProblem('PATH_UNSAFE')
    return path


@contextmanager
def _scope(root, paths):
    """Reuse Windows ancestor leases without creating any directory or file."""
    with ExitStack() as stack:
        if os.name == 'nt':
            from .actions.artifact_compensation import _kernel, _open
            kernel, directories = _kernel(), set()
            for path in [root, *paths]:
                current = path if path.is_dir() else path.parent
                while not current.exists() and current != current.parent:
                    current = current.parent
                directories.update((current, *current.parents))
            for directory in sorted(directories, key=lambda item: (len(item.parts), str(item).casefold())):
                stack.enter_context(_open(kernel, directory, directory=True, require_ntfs=False))
        for path in paths:
            if artifact_path_error(str(path)) or not path.resolve().is_relative_to(root):
                raise CriterionProblem('PATH_UNSAFE')
        yield
        for path in paths:
            if artifact_path_error(str(path)) or not path.resolve().is_relative_to(root):
                raise CriterionProblem('PATH_UNSAFE')


def _limit(max_file_bytes):
    if type(max_file_bytes) is not int or not 1 <= max_file_bytes <= file_inspection.MAX_BYTES:
        raise ValueError('Límite de lectura inválido')


def _version(relative, root, cancelled, maximum):
    _cancel(cancelled)
    path = _safe(root, relative)
    if not path.exists():
        raise CriterionProblem('INPUT_MISSING')
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum or before.st_ino <= 0:
        raise CriterionProblem('INPUT_INVALID')
    try:
        observed = file_inspection.hash_file(str(path), cancelled)
    except (ValueError, OSError):
        _cancel(cancelled)
        raise CriterionProblem('INPUT_CHANGED') from None
    after = path.stat()
    _cancel(cancelled)
    if (observed['bytes'] > maximum or file_inspection.fingerprint(before) != file_inspection.fingerprint(after)):
        raise CriterionProblem('INPUT_CHANGED')
    return {'path': relative, 'sha256': observed['sha256'], 'bytes': observed['bytes'],
            'device': after.st_dev, 'inode': after.st_ino, 'mtime_ns': after.st_mtime_ns}


def assert_input_versions(versions, root, cancelled, *, max_file_bytes=file_inspection.MAX_BYTES):
    _limit(max_file_bytes)
    if not isinstance(versions, list) or len(versions) > 100:
        raise ValueError('INPUT_CHANGED: versiones inválidas')
    root, seen = _root(root), set()
    for row in versions:
        if (not isinstance(row, dict) or set(row) != VERSION_KEYS or not isinstance(row['sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or any(type(row[key]) is not int for key in ('bytes', 'device', 'inode', 'mtime_ns'))):
            raise ValueError('INPUT_CHANGED: versión inválida')
        relative = _relative(row['path'])
        if relative.casefold() in seen:
            raise ValueError('INPUT_CHANGED: versiones duplicadas')
        seen.add(relative.casefold())
        with _scope(root, [_safe(root, relative)]):
            if _version(relative, root, cancelled, max_file_bytes) != row:
                raise ValueError('INPUT_CHANGED: el recurso de origen cambió')
    _cancel(cancelled)
    return True


@contextmanager
def input_version_lease(versions, root, cancelled, *, max_file_bytes=file_inspection.MAX_BYTES):
    """Keep approved source bytes immutable across the existing Windows producer."""
    assert_input_versions(versions, root, cancelled, max_file_bytes=max_file_bytes)
    if not versions:
        yield
        return
    if os.name != 'nt':
        raise ValueError('INPUT_LEASE_UNAVAILABLE')
    root = _root(root)
    from .actions.artifact_compensation import _kernel, _open
    with _scope(root, [_safe(root, row['path']) for row in versions]), ExitStack() as leases:
        kernel = _kernel()
        for row in versions:
            leases.enter_context(_open(kernel, _safe(root, row['path']), require_ntfs=False, max_bytes=max_file_bytes))
        assert_input_versions(versions, root, cancelled, max_file_bytes=max_file_bytes)
        yield


def _parameters(criterion, root):
    parameters = copy.deepcopy(criterion['parameters'])
    sources = parameters.get('paths', [parameters['source']] if 'source' in parameters else [])
    for source in sources:
        _safe(root, source)
    if 'source' in parameters:
        parameters['source'] = str(_safe(root, parameters['source']))
    if 'paths' in parameters:
        parameters['paths'] = [str(_safe(root, path)) for path in parameters['paths']]
    output = parameters.get('path', parameters.get('destination'))
    return parameters, sources, _safe(root, output)


def _bundle_output(parameters, versions, destination, root, cancelled, maximum):
    from .actions.file_workflows import MANIFEST, _verify_bundle
    records = []
    for relative in parameters['paths']:
        source = _safe(root, relative)
        version = next(row for row in versions if row['path'] == relative)
        records.append({'source': str(source), 'path': str(destination / source.name), 'name': source.name,
                        'bytes': version['bytes'], 'sha256': version['sha256']})
    expected_names = {row['name'] for row in records} | {MANIFEST}
    archive = parameters.get('archive_name')
    if archive: expected_names.add(archive)
    if not destination.is_dir() or {path.name for path in destination.iterdir()} != expected_names:
        raise ValueError('Bundle members differ')
    output = {'directory': str(destination), 'files': records}
    total_bytes = 0
    for name in expected_names:
        relative = (destination / name).relative_to(root).as_posix()
        version = _version(relative, root, cancelled, maximum)
        total_bytes += version['bytes']
        if parameters.get('max_output_bytes') is not None and total_bytes > parameters['max_output_bytes']:
            raise ValueError('Bundle exceeds total output budget')
        if name == MANIFEST:
            if version['bytes'] > 131072: raise ValueError('Manifest too large')
            with (destination / MANIFEST).open('rb') as stream:
                raw = stream.read(min(131072, maximum) + 1)
            if len(raw) > min(131072, maximum): raise ValueError('Manifest too large')
            if hashlib.sha256(raw).hexdigest() != version['sha256']:
                raise CriterionProblem('INPUT_CHANGED')
            actual = json.loads(raw)
            expected = {'schema_version': 1, 'files': records}
            if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
                raise ValueError('Manifest differs from criterion sources')
            output['manifest'] = {'path': str(destination / name), 'bytes': version['bytes'], 'sha256': version['sha256']}
        elif archive and name == archive:
            output['archive'] = {'path': str(destination / name), 'bytes': version['bytes'], 'sha256': version['sha256']}
    _verify_bundle(output, cancelled)


def _evaluate(criterion, root, cancelled, maximum):
    result = {'id': criterion['id'], 'kind': criterion['kind'], 'status': 'indeterminate',
              'reason_code': 'INPUT_INVALID', 'input_versions': []}
    try:
        _cancel(cancelled)
        parameters, sources, destination = _parameters(criterion, root)
        with _scope(root, [destination, *[_safe(root, raw) for raw in sources]]):
            versions = [_version(raw, root, cancelled, maximum) for raw in sources]
            versions.sort(key=lambda row: row['path'].casefold())
            result['input_versions'] = versions
            if criterion['kind'] == 'xlsx_from_csv':
                from .actions.office_workflows import csv_data
                try: data = csv_data(parameters)
                except (ValueError, OSError, UnicodeError, csv.Error): raise CriterionProblem('INPUT_INVALID') from None
            elif criterion['kind'] == 'file_bundle':
                from .actions.file_workflows import _bundle_inputs
                try: _bundle_inputs(parameters)
                except (ValueError, OSError, TypeError): raise CriterionProblem('INPUT_INVALID') from None
            assert_input_versions(versions, root, cancelled, max_file_bytes=maximum)
            if not destination.exists():
                if criterion['kind'] != 'text_exact' and not destination.parent.is_dir():
                    raise CriterionProblem('INPUT_MISSING')
                result.update(status='unsatisfied', reason_code='OUTPUT_MISSING')
                return result
            try:
                if criterion['kind'] == 'text_exact':
                    observed = _version(parameters['path'], root, cancelled, maximum)
                    if observed['sha256'] != hashlib.sha256(parameters['text'].encode('utf8')).hexdigest():
                        raise ValueError('Text differs')
                elif criterion['kind'] == 'xlsx_from_csv':
                    from .actions.office_workflows import verify_xlsx
                    before = _version(parameters['destination'], root, cancelled, maximum)
                    verify_xlsx(destination, data)
                    if _version(parameters['destination'], root, cancelled, maximum) != before:
                        raise CriterionProblem('INPUT_CHANGED')
                else:
                    _bundle_output(criterion['parameters'], versions, destination, root, cancelled, maximum)
                assert_input_versions(versions, root, cancelled, max_file_bytes=maximum)
                result.update(status='satisfied', reason_code='SATISFIED')
            except CriterionProblem:
                raise
            except Exception:
                _cancel(cancelled)
                result.update(status='unsatisfied', reason_code='OUTPUT_MISMATCH')
    except CriterionProblem as exc:
        result.update(status='indeterminate', reason_code=str(exc))
    except (ValueError, OSError):
        result.update(status='indeterminate', reason_code='PATH_UNSAFE')
    return result


def evaluate_criteria(goal, root, cancelled, *, max_file_bytes=file_inspection.MAX_BYTES):
    _limit(max_file_bytes)
    criteria = validate_criteria(goal.get('criteria', []), goal.get('checks', []))
    try: root = _root(root)
    except (ValueError, OSError):
        return [{'id': row['id'], 'kind': row['kind'], 'status': 'indeterminate',
                 'reason_code': 'PATH_UNSAFE', 'input_versions': []} for row in criteria]
    return [_evaluate(row, root, cancelled, max_file_bytes) for row in criteria]


def propose_goal_step(goal, criterion_id, root, cancelled, *, max_file_bytes=file_inspection.MAX_BYTES):
    criteria = validate_criteria(goal.get('criteria', []), goal.get('checks', []))
    selected = next((row for row in criteria if row['id'] == criterion_id), None)
    if selected is None: raise ValueError('CRITERION_UNKNOWN')
    _limit(max_file_bytes)
    root = _root(root)
    assessment = _evaluate(selected, root, cancelled, max_file_bytes)
    if assessment['status'] != 'unsatisfied' or assessment['reason_code'] != 'OUTPUT_MISSING':
        raise ValueError(assessment['reason_code'])
    parameters, _, destination = _parameters(selected, root)
    assert_input_versions(assessment['input_versions'], root, cancelled, max_file_bytes=max_file_bytes)
    if destination.exists(): raise ValueError('OUTPUT_CHANGED')
    if selected['kind'] == 'text_exact':
        parameters = {'path': parameters['path'], 'content': parameters['text']}
    return {'criterion_id': criterion_id, 'step': {'command_id': KINDS[selected['kind']][0], 'inputs': parameters},
            'input_versions': assessment['input_versions']}
