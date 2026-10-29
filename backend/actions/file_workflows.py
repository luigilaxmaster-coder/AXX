"""Bounded local discovery and non-overwriting, verified workspace bundles."""
from __future__ import annotations

import fnmatch
import itertools
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import threading
import zipfile

from .file_inspection import MAX_BYTES, fingerprint, hash_file, validate_path

MAX_FILES = 100
MAX_ENTRIES = 10000
MANIFEST = 'axx-manifest.json'


def _check_path(raw):
    from .tools import artifact_path_error
    error = artifact_path_error(raw)
    if error:
        raise ValueError(error)
    return Path(raw)


def _cancelled(cancelled):
    if cancelled.is_set():
        raise ValueError('Operación cancelada; no se eliminan los archivos ya creados.')


def find_files(inputs, cancelled=None):
    cancelled = cancelled or threading.Event()
    if not isinstance(inputs, dict):
        raise ValueError('La búsqueda requiere un objeto de parámetros.')
    if set(inputs) - {'directory', 'pattern', 'recursive', 'limit', 'max_entries_scan'}:
        raise ValueError('Parámetros de búsqueda desconocidos.')
    directory = _check_path(inputs.get('directory'))
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Indica un directorio local absoluto existente.')
    pattern = inputs.get('pattern', '*')
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 100 or any(c in pattern for c in '\\/:\0'):
        raise ValueError('Usa un patrón de nombre, sin rutas.')
    recursive, limit = inputs.get('recursive', False), inputs.get('limit', MAX_FILES)
    if type(recursive) is not bool or type(limit) is not int or not 1 <= limit <= MAX_FILES:
        raise ValueError('recursive debe ser booleano y limit estar entre 1 y 100.')
    scan_limit = inputs.get('max_entries_scan', MAX_ENTRIES)
    if type(scan_limit) is not int or not 1 <= scan_limit <= MAX_ENTRIES:
        raise ValueError('El límite de entradas inspeccionadas debe estar entre 1 y 10000.')
    files, pending, visited, skipped, truncated = [], [(directory, 0)], 0, 0, False
    while pending and len(files) < limit and visited < scan_limit:
        current, depth = pending.pop()
        _cancelled(cancelled)
        _check_path(str(current))
        with os.scandir(current) as entries:
            for entry in itertools.islice(entries, scan_limit - visited):
                _cancelled(cancelled)
                visited += 1
                info = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000):
                    skipped += 1
                    continue
                if stat.S_ISDIR(info.st_mode) and recursive:
                    if depth < 8:
                        pending.append((Path(entry.path), depth + 1))
                    else:
                        truncated = True
                if stat.S_ISREG(info.st_mode) and fnmatch.fnmatchcase(entry.name.casefold(), pattern.casefold()):
                    files.append({'path': entry.path, 'bytes': info.st_size, 'modified_ns': info.st_mtime_ns})
                    if len(files) == limit:
                        truncated = True
                        break
    files.sort(key=lambda row: row['path'].casefold())
    return {'directory': str(directory), 'files': files, 'paths': [row['path'] for row in files],
            'total_bytes': sum(row['bytes'] for row in files), 'truncated': truncated or bool(pending) or visited >= scan_limit,
            'inspected_entries': visited, 'skipped_unavailable_or_linked': skipped,
            'verification': 'local_metadata_only'}


def _bundle_inputs(inputs):
    if not isinstance(inputs, dict):
        raise ValueError('La copia requiere un objeto de parámetros.')
    if set(inputs) - {'paths', 'destination', 'archive_name', 'max_output_bytes'}:
        raise ValueError('Parámetros de copia desconocidos.')
    maximum = inputs.get('max_output_bytes')
    if maximum is not None and (type(maximum) is not int or not 1 <= maximum <= 2 * MAX_BYTES):
        raise ValueError('El presupuesto de salida debe estar entre 1 y 1073741824 bytes.')
    paths = inputs.get('paths')
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
        raise ValueError('Selecciona de 1 a 100 archivos explícitos.')
    sources = [validate_path(raw) for raw in paths]
    destination = _check_path(inputs.get('destination'))
    if destination.is_absolute() or destination.drive or '..' in destination.parts or destination == Path('.'):
        raise ValueError('El destino debe ser una carpeta nueva relativa al espacio autorizado.')
    archive = inputs.get('archive_name')
    if archive is not None:
        name = _check_path(archive)
        if name.name != archive or name.suffix.lower() != '.zip':
            raise ValueError('archive_name debe ser un nombre ZIP, sin directorios.')
    names = [source.name.casefold() for source in sources]
    reserved = {MANIFEST.casefold(), archive.casefold() if archive else ''}
    if len(set(names)) != len(names) or any(name in reserved for name in names):
        raise ValueError('Los nombres seleccionados colisionan entre sí, con el manifiesto o con el ZIP.')
    # Reserve ZIP framing and the manifest inside the same 512 MiB read budget.
    budget = MAX_BYTES - 1024 * 1024 if archive else MAX_BYTES
    if sum(source.stat().st_size for source in sources) > budget:
        raise ValueError('La selección y sus metadatos superan el límite total de 512 MiB.')
    if maximum is not None and sum(source.stat().st_size for source in sources) > maximum:
        raise ValueError('Las copias exceden el presupuesto lógico de salida.')
    return sources, destination, archive


def _copy_file(source, target, cancelled, created=None, *, max_bytes=None):
    validate_path(str(source))
    before = source.stat()
    digest, copied = hashlib.sha256(), 0
    with source.open('rb') as reader:
        if fingerprint(os.fstat(reader.fileno())) != fingerprint(before):
            raise ValueError('El origen cambió antes de copiar.')
        _check_path(str(source))
        _check_path(str(target))
        with target.open('xb') as writer:
            if created is not None:
                created.append(str(target))
            while chunk := reader.read(1024 * 1024):
                _cancelled(cancelled)
                copied += len(chunk)
                if copied > before.st_size:
                    raise ValueError('El origen creció durante la copia.')
                if max_bytes is not None and copied > max_bytes:
                    raise ValueError('La copia excede el presupuesto lógico de salida.')
                writer.write(chunk)
                digest.update(chunk)
        if fingerprint(os.fstat(reader.fileno())) != fingerprint(before):
            raise ValueError('El origen cambió durante la copia.')
    _check_path(str(source))
    if fingerprint(source.stat()) != fingerprint(before) or copied != before.st_size:
        raise ValueError('El origen fue sustituido durante la copia.')
    return {'source': str(source), 'path': str(target), 'name': target.name, 'bytes': copied, 'sha256': digest.hexdigest()}


class _CappedZipWriter(io.BufferedWriter):
    def __init__(self, raw, maximum):
        super().__init__(raw)
        self.maximum = maximum

    def write(self, data):
        if self.tell() + len(data) > self.maximum:
            raise ValueError('El ZIP excede el presupuesto lógico de salida.')
        return super().write(data)


def _verify_bundle(output, cancelled):
    records = output['files']
    for row in records:
        for name in ('source', 'path'):
            observed = hash_file(row[name], cancelled)
            if observed['sha256'] != row['sha256'] or observed['bytes'] != row['bytes']:
                raise ValueError('El origen o su copia no coincide con el hash registrado.')
    manifest = output['manifest']
    if hash_file(manifest['path'], cancelled)['sha256'] != manifest['sha256']:
        raise ValueError('El manifiesto cambió.')
    if output.get('archive'):
        archive = output['archive']
        if hash_file(archive['path'], cancelled)['sha256'] != archive['sha256']:
            raise ValueError('El ZIP cambió.')
        expected = {row['name']: row for row in records}
        expected[MANIFEST] = manifest
        with zipfile.ZipFile(archive['path']) as zipped:
            if len(zipped.namelist()) != len(expected) or set(zipped.namelist()) != set(expected):
                raise ValueError('El ZIP no contiene exactamente los archivos seleccionados y el manifiesto.')
            for name, row in expected.items():
                digest, size = hashlib.sha256(), 0
                with zipped.open(name) as member:
                    while chunk := member.read(1024 * 1024):
                        _cancelled(cancelled)
                        digest.update(chunk)
                        size += len(chunk)
                        if size > row['bytes']:
                            raise ValueError('Una entrada del ZIP supera su tamaño registrado.')
                if digest.hexdigest() != row['sha256'] or size != row['bytes']:
                    raise ValueError('Una entrada del ZIP no coincide con el contenido seleccionado.')


class FindFilesTool:
    name, version = 'file_find', '1.1.0'
    description = 'Find bounded local file metadata without following links or scanning the whole disk'

    def verify_preconditions(self, inputs):
        try:
            directory = _check_path(inputs.get('directory'))
            if not directory.is_absolute() or not directory.is_dir():
                raise ValueError('Indica un directorio local absoluto existente.')
            return True, 'Local directory exists; bounds checked before scanning'
        except (ValueError, OSError, TypeError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_in_workspace(self, inputs, workspace_root):
        return self.execute(inputs)

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        try:
            output = find_files(inputs, cancelled)
            return ToolResult(True, output=output, evidence={'verification': 'local_metadata_only', 'truncated': output['truncated']})
        except (ValueError, OSError, TypeError) as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        return bool(result.success and isinstance(result.output.get('files'), list)), result.error or 'Bounded metadata returned; file content not read'


class FileBundleTool:
    name, version = 'file_bundle', '1.1.0'
    description = 'Copy explicit files into a new workspace folder and optionally create a hash-verified ZIP'

    def verify_preconditions(self, inputs):
        try:
            _bundle_inputs(inputs)
            return True, 'Selected files and non-overwriting destination validated'
        except (ValueError, OSError, TypeError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='An authorized executor workspace is required')

    def execute_in_workspace(self, inputs, workspace_root):
        return self.execute_cancellable(inputs, workspace_root, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        created = []
        output = {'files': []}
        try:
            sources, relative, archive_name = _bundle_inputs(inputs)
            root = _check_path(str(workspace_root)).resolve(strict=True)
            target = root / relative
            _check_path(str(target))
            if not target.resolve().is_relative_to(root) or not target.parent.is_dir():
                raise ValueError('La carpeta padre debe existir dentro del espacio autorizado.')
            _cancelled(cancelled)
            target.mkdir()
            created.append(str(target))
            output['directory'] = str(target)
            maximum = inputs.get('max_output_bytes')
            for source in sources:
                _cancelled(cancelled)
                destination = target / source.name
                remaining = {} if maximum is None else {'max_bytes':maximum - sum(row['bytes'] for row in output['files'])}
                output['files'].append(_copy_file(source, destination, cancelled, created, **remaining))
                if sum(row['bytes'] for row in output['files']) > MAX_BYTES:
                    raise ValueError('Los orígenes crecieron por encima del límite total.')
            manifest_bytes = (json.dumps({'schema_version': 1, 'files': output['files']}, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')
            manifest_path = target / MANIFEST
            occupied = sum(row['bytes'] for row in output['files']) + len(manifest_bytes)
            if maximum is not None and occupied > maximum:
                raise ValueError('El manifiesto excede el presupuesto lógico de salida.')
            _check_path(str(manifest_path))
            _cancelled(cancelled)
            with manifest_path.open('xb') as stream:
                created.append(str(manifest_path))
                stream.write(manifest_bytes)
            output['manifest'] = {'path': str(manifest_path), 'bytes': len(manifest_bytes), 'sha256': hashlib.sha256(manifest_bytes).hexdigest()}
            if archive_name:
                archive_path = target / archive_name
                _check_path(str(archive_path))
                with archive_path.open('xb', buffering=0) as raw:
                    created.append(str(archive_path))
                    stream = raw if maximum is None else _CappedZipWriter(raw, maximum - occupied)
                    with stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
                        for path in [Path(row['path']) for row in output['files']] + [manifest_path]:
                            _check_path(str(path))
                            info = zipfile.ZipInfo(path.name, (1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_DEFLATED
                            size = 0
                            with path.open('rb') as reader, zipped.open(info, 'w') as member:
                                while chunk := reader.read(1024 * 1024):
                                    _cancelled(cancelled)
                                    size += len(chunk)
                                    if size > MAX_BYTES:
                                        raise ValueError('El archivo creció durante la creación del ZIP.')
                                    member.write(chunk)
                output['archive'] = hash_file(str(archive_path), cancelled)
            _verify_bundle(output, cancelled)
            return ToolResult(True, output=output, evidence={'verification': 'source_copy_manifest_zip_sha256', 'created_paths': created})
        except (ValueError, OSError, TypeError, zipfile.BadZipFile) as exc:
            return ToolResult(False, output=output, error=str(exc), evidence={
                'cancelled': cancelled.is_set(), 'created_paths': [raw for raw in created if Path(raw).exists()],
                'effect_uncertain': bool(created), 'partial_effect': bool(created),
                'dispatch_status': 'delivered' if created else 'rejected',
                'effect_status': 'partial' if created else 'not_observed'})

    def verify_postconditions(self, inputs, result):
        if not result.success:
            return False, result.error or 'Bundle incomplete'
        try:
            _verify_bundle(result.output, threading.Event())
            return True, 'Originals, copies, manifest and ZIP entries independently hash-verified'
        except (ValueError, OSError, TypeError, zipfile.BadZipFile) as exc:
            return False, str(exc)
