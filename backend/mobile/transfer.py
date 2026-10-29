"""Bounded, resumable LAN copies. Private metadata and staged bytes stay encrypted."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import unicodedata
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.actions.file_inspection import fingerprint
from backend.actions.tools import artifact_path_error

CHUNK_SIZE = 256 * 1024
MAX_SIZE = 10 * 1024**3
MAX_STAGED = 20 * 1024**3
TERMINAL = {'completed', 'cancelled', 'failed'}
FILE_KINDS = {
    'documents': {'.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.md', '.csv', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp', '.dwg', '.dxf', '.rvt', '.ifc'},
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif', '.svg'},
    'video': {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.3gp'},
    'audio': {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma'},
    'archives': {'.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz'},
}


def _downloads_directory():
    if os.name == 'nt':
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Downloads, 0, None))
    return Path.home() / 'Downloads'


def _uuid(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Identificador de transferencia inválido.') from exc
    return value


def _path(value, *, file=False):
    error = artifact_path_error(value)
    if error:
        raise ValueError(error)
    path = Path(value)
    if '..' in path.parts or not path.is_absolute():
        raise ValueError('Selecciona una ruta local absoluta, sin saltos de carpeta.')
    path = path.resolve(strict=True)
    if file and not path.is_file():
        raise ValueError('El archivo ya no está disponible.')
    return path


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 180 or '/' in value or '\\' in value or value in {'.', '..'}:
        raise ValueError('Nombre de archivo inválido.')
    error = artifact_path_error(value)
    if error:
        raise ValueError(error)
    return value


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


def _kind(value):
    if not isinstance(value, str) or value not in {'all', *FILE_KINDS}:
        raise ValueError('Tipo de archivo no válido.')
    return value


def _allocation_size(size):
    # Reserve cipher tags and a filesystem block per chunk before admitting a copy.
    return size + math.ceil(size / CHUNK_SIZE) * (28 + 4096)


class FileTransfer:
    def __init__(self, store, directory):
        self.store = store
        self.directory = Path(directory) / 'transfer'
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            os.chmod(self.directory, 0o700)
        self.lock = threading.RLock()
        self.workers = set()
        self.closed = False
        key_path = self.directory / ('key.dpapi' if os.name == 'nt' else 'key.bin')
        from backend.auth.chatgpt_auth import _dpapi_encrypt, _dpapi_decrypt
        if not key_path.exists():
            with key_path.open('xb') as target:
                if os.name != 'nt':
                    os.chmod(key_path, 0o600)
                target.write(_dpapi_encrypt(AESGCM.generate_key(bit_length=256)))
                target.flush()
                os.fsync(target.fileno())
        self.cipher = AESGCM(_dpapi_decrypt(key_path.read_bytes()))
        with store._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mobile_file_config (device_id TEXT PRIMARY KEY, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS mobile_file_refs (file_ref TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    payload BLOB NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS mobile_transfers (transfer_id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL, payload BLOB NOT NULL, updated REAL NOT NULL);
            ''')
        with self.lock:
            for item in self._all():
                if item['state'] in {'preparing', 'verifying'}:
                    item.update(state='paused', error='Axx se reinició. Reanuda la transferencia.')
                    self._save(item)

    def _encrypt(self, value, aad):
        nonce = os.urandom(12)
        return nonce + self.cipher.encrypt(nonce, json.dumps(value, ensure_ascii=False).encode(), aad.encode())

    def _decrypt(self, value, aad):
        return json.loads(self.cipher.decrypt(value[:12], value[12:], aad.encode()))

    def _all(self, device_id=None):
        with self.store._connect() as db:
            rows = db.execute('SELECT transfer_id,payload FROM mobile_transfers' +
                              (' WHERE device_id=?' if device_id else '') + ' ORDER BY updated DESC',
                              (device_id,) if device_id else ()).fetchall()
        return [self._decrypt(row['payload'], row['transfer_id']) for row in rows]

    def _load(self, transfer_id, device_id=None):
        _uuid(transfer_id)
        with self.store._connect() as db:
            row = db.execute('SELECT device_id,payload FROM mobile_transfers WHERE transfer_id=?', (transfer_id,)).fetchone()
        if row is None or device_id is not None and row['device_id'] != device_id:
            raise ValueError('Transferencia no disponible para este dispositivo.')
        return self._decrypt(row['payload'], transfer_id)

    def _save(self, item, request_hash=None):
        item['updated_at'] = time.time()
        with self.store._connect() as db:
            if request_hash is not None:
                db.execute('INSERT INTO mobile_transfers VALUES(?,?,?,?,?)',
                           (item['transfer_id'], item['device_id'], request_hash,
                            self._encrypt(item, item['transfer_id']), item['updated_at']))
            else:
                db.execute('UPDATE mobile_transfers SET payload=?,updated=? WHERE transfer_id=?',
                           (self._encrypt(item, item['transfer_id']), item['updated_at'], item['transfer_id']))

    @staticmethod
    def _public(item):
        return {key: value for key, value in item.items() if key not in {'key', 'source', 'source_version', 'chunks'}}

    def _grant(self, device_id, scope):
        device = next((d for d in self.store.devices() if d['device_id'] == device_id and not d['revoked']), None)
        if device is None or scope not in device['scopes']:
            raise ValueError('Autoriza Archivos para este teléfono desde la PC.')

    def config(self, device_id):
        with self.store._connect() as db:
            row = db.execute('SELECT payload FROM mobile_file_config WHERE device_id=?', (device_id,)).fetchone()
        return self._decrypt(row['payload'], device_id) if row else {'roots': []}

    def configure(self, body):
        if not isinstance(body, dict) or set(body) != {'device_id', 'read', 'write', 'roots'}:
            raise ValueError('device_id, read, write y roots son obligatorios.')
        if type(body['read']) is not bool or type(body['write']) is not bool or not isinstance(body['roots'], list) or len(body['roots']) > 8:
            raise ValueError('Permisos de archivos inválidos; máximo ocho carpetas.')
        roots = []
        for raw in body['roots']:
            path = _path(raw)
            if not path.is_dir() or path == Path(path.anchor):
                raise ValueError('Selecciona una carpeta concreta, no un disco completo.')
            if str(path) not in roots:
                roots.append(str(path))
        device_id = body['device_id']
        if body['read'] and not roots:
            raise ValueError('Elige al menos una carpeta para permitir búsquedas.')
        with self.lock:
            self.store.set_file_permissions(device_id, body['read'], body['write'], self._encrypt({'roots': roots}, device_id))
        return self.status(device_id)

    def status(self, device_id=None):
        with self.lock:
            devices = [d for d in self.store.devices() if not d['revoked']]
            active = [i for i in self._all() if i.get('stored', True) and i['state'] != 'cancelled']
            staged = sum(i['size'] for i in active)
            free = self._available_space(active)
            capacity = {'chunk_size': CHUNK_SIZE, 'max_size': MAX_SIZE, 'max_staged': MAX_STAGED,
                        'staged_bytes': staged, 'available_bytes': max(0, min(MAX_SIZE, MAX_STAGED - staged,
                            free * CHUNK_SIZE // (CHUNK_SIZE + 28 + 4096))), 'transport': 'local_tls'}
            if device_id is not None:
                device = next((d for d in devices if d['device_id'] == device_id), None)
                if device is None:
                    raise ValueError('Dispositivo no autorizado.')
                roots = self.config(device_id)['roots']
                return {'permissions': {'read': 'files.read' in device['scopes'], 'write': 'files.write' in device['scopes']},
                        'roots': [{'id': str(i), 'name': Path(path).name} for i, path in enumerate(roots)],
                        'transfers': [self._public(i) for i in self._all(device_id)[:100]],
                        **capacity}
            return {'devices': [{**d, 'roots': self.config(d['device_id'])['roots'],
                                 'permissions': {'read': 'files.read' in d['scopes'], 'write': 'files.write' in d['scopes']}}
                                for d in devices], 'transfers': [self._public(i) for i in self._all()[:100]],
                    **capacity}

    def _available_space(self, active):
        reserved = sum(_allocation_size(max(0, item['size'] - item.get(
            'prepared_bytes' if item['direction'] == 'to_phone' else 'confirmed_bytes', 0)))
            for item in active if item['state'] not in TERMINAL)
        return max(0, shutil.disk_usage(self.directory).free - reserved - 16 * 1024**2)

    def _source(self, device_id, source, version=None):
        self._grant(device_id, 'files.read')
        path = _path(source, file=True)
        roots = [_path(raw) for raw in self.config(device_id)['roots']]
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError('El archivo está fuera de las carpetas autorizadas.')
        info = path.stat()
        if info.st_size > MAX_SIZE or getattr(info, 'st_file_attributes', 0) & (0x1000 | 0x40000 | 0x400000):
            raise ValueError('Archivo demasiado grande o no disponible localmente.')
        current = list(fingerprint(info))
        if version is not None and version != current:
            raise ValueError('El archivo cambió. Búscalo de nuevo antes de enviarlo.')
        return path, current

    def _remember(self, device_id, items):
        self._grant(device_id, 'files.read')
        config, checked, visible = self.config(device_id), [], []
        try:
            for candidate in items:
                item = dict(candidate)
                if item.get('kind') == 'directory':
                    if 'identity' not in item:
                        item = self._directory_item(Path(item['root']), Path(item['source']))
                    self._directory(device_id, item)
                else:
                    path, version = self._source(device_id, item['source'], item.get('source_version'))
                    item.update(source=str(path), source_version=version, name=path.name,
                                size=version[2], bytes=version[2], modified_at=version[3] / 1_000_000_000)
                checked.append(item)
        except (OSError, ValueError) as exc:
            raise ValueError('Los archivos cambiaron o dejaron de estar autorizados. Actualiza la carpeta.') from exc
        with self.lock, self.store._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._grant(device_id, 'files.read')
            if self.config(device_id) != config:
                raise ValueError('Los permisos cambiaron. Vuelve a abrir Carpetas.')
            db.execute('DELETE FROM mobile_file_refs WHERE created<?', (time.time() - 3600,))
            for item in checked:
                reference = str(uuid.uuid4())
                db.execute('INSERT INTO mobile_file_refs VALUES(?,?,?,?)',
                           (reference, device_id, self._encrypt(item, reference), time.time()))
                if item.get('kind') == 'directory':
                    visible.append({'folder_ref': reference, 'name': item['name']})
                else:
                    visible.append({**{k: v for k, v in item.items() if not k.startswith('source')},
                                    'file_ref': reference, 'version': hashlib.sha256(json.dumps(item['source_version']).encode()).hexdigest()})
            db.commit()
        return visible

    def _reference(self, device_id, reference):
        _uuid(reference)
        with self.store._connect() as db:
            row = db.execute('SELECT payload FROM mobile_file_refs WHERE file_ref=? AND device_id=? AND created>?',
                             (reference, device_id, time.time() - 3600)).fetchone()
        if row is None:
            raise ValueError('La referencia caducó. Vuelve a abrir la carpeta o busca de nuevo.')
        return self._decrypt(row['payload'], reference)

    def _directory(self, device_id, item):
        self._grant(device_id, 'files.read')
        try:
            if item.get('kind') != 'directory' or item.get('root') not in self.config(device_id)['roots']:
                raise ValueError()
            root, path = _path(item['root']), _path(item['source'])
            info = path.stat()
            if (not path.is_dir() or not path.is_relative_to(root)
                    or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000)
                    or item.get('identity') != [info.st_dev, info.st_ino]):
                raise ValueError()
        except (KeyError, OSError, ValueError) as exc:
            raise ValueError('Esta carpeta ya no está disponible o autorizada. Vuelve a Carpetas.') from exc
        return root, path

    def _directory_item(self, root, path):
        info = path.stat()
        return {'kind': 'directory', 'source': str(path), 'root': str(root), 'name': path.name,
                'identity': [info.st_dev, info.st_ino]}

    def _file_item(self, root, path, info):
        return {'source': str(path), 'name': path.name,
                'relative_path': str(path.relative_to(root)), 'root_name': root.name,
                'size': info.st_size, 'bytes': info.st_size, 'modified_at': info.st_mtime}

    def browse(self, device_id, body):
        self._grant(device_id, 'files.read')
        if not isinstance(body, dict) or set(body) - {'folder_ref', 'offset', 'limit', 'kind'}:
            raise ValueError('Selecciona una carpeta autorizada.')
        offset, limit = body.get('offset', 0), body.get('limit', 40)
        if type(offset) is not int or not 0 <= offset <= 10000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Página de archivos no válida.')
        kind = _kind(body.get('kind', 'all'))
        items, parents, truncated = [], [], False
        reference = body.get('folder_ref')
        if reference is None:
            for raw in self.config(device_id)['roots']:
                try:
                    root = _path(raw)
                    items.append(self._directory_item(root, root))
                except (OSError, ValueError):
                    truncated = True
        else:
            current = self._reference(device_id, reference)
            root, folder = self._directory(device_id, current)
            path = root
            parents.append(self._directory_item(root, root))
            for part in folder.relative_to(root).parts:
                path /= part
                parents.append(self._directory_item(root, path))
            try:
                with os.scandir(folder) as entries:
                    for index, entry in enumerate(entries):
                        if index >= 10000:
                            truncated = True
                            break
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if entry.is_symlink() or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                items.append({'kind': 'directory', 'source': entry.path, 'root': str(root), 'name': entry.name})
                            elif (entry.is_file(follow_symlinks=False) and info.st_size <= MAX_SIZE
                                  and (kind == 'all' or Path(entry.name).suffix.lower() in FILE_KINDS[kind])):
                                items.append(self._file_item(root, Path(entry.path), info))
                        except (OSError, ValueError):
                            truncated = True
            except OSError as exc:
                raise ValueError('No se puede abrir esta carpeta. Comprueba sus permisos en la PC.') from exc
            self._directory(device_id, current)
        items.sort(key=lambda item: (item.get('kind') != 'directory', _fold(item['name']), item['name']))
        page = self._remember(device_id, items[offset:offset + limit])
        breadcrumbs = [{'name': 'Carpetas', 'folder_ref': None}, *self._remember(device_id, parents)]
        next_offset = offset + limit if offset + limit < len(items) else None
        return {'folders': [item for item in page if 'folder_ref' in item],
                'files': [item for item in page if 'file_ref' in item], 'breadcrumbs': breadcrumbs,
                'next_offset': next_offset, 'truncated': truncated or next_offset is not None}

    def search(self, device_id, body):
        self._grant(device_id, 'files.read')
        if not isinstance(body, dict) or set(body) - {'query', 'modified_after', 'modified_before', 'kind'} or not isinstance(body.get('query'), str) or len(body['query']) > 200:
            raise ValueError('Escribe un nombre o tipo de archivo de hasta 200 caracteres.')
        kind = _kind(body.get('kind', 'all'))
        after, before = body.get('modified_after', 0), body.get('modified_before', time.time() + 86400)
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (after, before)) or after > before:
            raise ValueError('Intervalo de fechas inválido.')
        words = re.findall(r'[\w.-]+', _fold(body['query']))
        ignored = {'axx', 'busca', 'buscar', 'trae', 'traeme', 'mandame', 'envia', 'enviame', 'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'mi', 'pc', 'archivo', 'archivos', 'ultimo', 'ultima', 'aqui', 'telefono'}
        words = [w for w in words if w not in ignored]
        results, visited, truncated = [], 0, False
        for root_raw in self.config(device_id)['roots']:
            root = _path(root_raw)
            pending = [(root, 0)]
            while pending and visited < 10000:
                folder, depth = pending.pop()
                try:
                    _path(str(folder))
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            visited += 1
                            if visited > 10000:
                                truncated = True
                                break
                            info = entry.stat(follow_symlinks=False)
                            if entry.is_symlink() or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x40000 | 0x400000):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if depth < 8:
                                    pending.append((Path(entry.path), depth + 1))
                                else:
                                    truncated = True
                            elif (entry.is_file(follow_symlinks=False) and info.st_size <= MAX_SIZE and after <= info.st_mtime <= before
                                  and (kind == 'all' or Path(entry.name).suffix.lower() in FILE_KINDS[kind])):
                                relative = str(Path(entry.path).relative_to(root))
                                if all(word in _fold(relative) for word in words):
                                    results.append(self._file_item(root, Path(entry.path), info))
                except (OSError, ValueError):
                    truncated = True
            truncated = truncated or bool(pending)
        results.sort(key=lambda item: (-item['modified_at'], item['name'].casefold()))
        truncated = truncated or len(results) > 60
        visible = self._remember(device_id, results[:60])
        return {'files': visible, 'truncated': truncated, 'inspected_entries': min(visited, 10000), 'sort': 'modified_desc'}

    def create(self, device_id, body):
        if not isinstance(body, dict):
            raise ValueError('Transferencia inválida.')
        transfer_id = _uuid(body.get('transfer_id'))
        direction = {'download': 'to_phone', 'upload': 'to_pc'}.get(body.get('direction'), body.get('direction'))
        if direction not in {'to_phone', 'to_pc'}:
            raise ValueError('Dirección de transferencia inválida.')
        self._grant(device_id, 'files.read' if direction == 'to_phone' else 'files.write')
        expected = {'transfer_id', 'direction', 'file_ref'} if direction == 'to_phone' else {'transfer_id', 'direction', 'name', 'sha256'}
        if direction == 'to_pc':
            expected.add('size' if 'size' in body else 'bytes')
        if set(body) != expected:
            raise ValueError('Parámetros de transferencia inválidos.')
        request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.lock:
            with self.store._connect() as db:
                previous = db.execute('SELECT device_id,request_hash FROM mobile_transfers WHERE transfer_id=?', (transfer_id,)).fetchone()
            if previous:
                if previous['device_id'] != device_id or previous['request_hash'] != request_hash:
                    raise ValueError('Este identificador ya pertenece a otra transferencia.')
                return self._public(self._load(transfer_id, device_id))
            if direction == 'to_phone':
                file_ref = _uuid(body['file_ref'])
                source = self._reference(device_id, file_ref)
                if source.get('kind', 'file') != 'file':
                    raise ValueError('Selecciona un archivo, no una carpeta.')
                path, version = self._source(device_id, source['source'], source['source_version'])
                name, size, digest = path.name, path.stat().st_size, None
            else:
                name, size, digest = _name(body['name']), body.get('size', body.get('bytes')), body['sha256']
                if type(size) is not int or not 0 <= size <= MAX_SIZE or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                    raise ValueError('Tamaño o SHA-256 inválido; máximo 10 GiB.')
            active = [i for i in self._all() if i.get('stored', True) and i['state'] != 'cancelled']
            if len(active) >= 100 or sum(i['size'] for i in active) + size > MAX_STAGED:
                raise ValueError('La bandeja llegó a su límite. Elimina copias de Axx que ya no necesites para liberar espacio.')
            if self._available_space(active) < _allocation_size(size):
                raise ValueError('No hay espacio suficiente para guardar la transferencia.')
            item = {'transfer_id': transfer_id, 'device_id': device_id, 'direction': direction, 'name': name,
                    'size': size, 'bytes': size, 'sha256': digest, 'chunk_size': CHUNK_SIZE,
                    'chunk_count': math.ceil(size / CHUNK_SIZE), 'next_index': 0,
                    'state': 'preparing' if direction == 'to_phone' else 'receiving', 'confirmed_bytes': 0,
                    'prepared_bytes': 0, 'created_at': time.time(), 'error': None, 'stored': True,
                    'key': base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()}
            if direction == 'to_phone':
                item.update(source=str(path), source_version=version)
            (self.directory / transfer_id).mkdir()
            self._save(item, request_hash)
            if direction == 'to_phone':
                self._start(transfer_id)
            return self._public(item)

    def _chunk_path(self, item, index):
        return self.directory / item['transfer_id'] / str(index)

    @staticmethod
    def _chunk_aad(item, index):
        return f"axx-transfer-v1:{item['transfer_id']}:{item['device_id']}:{item['size']}:{index}".encode()

    def _write_chunk(self, item, index, data):
        path = self._chunk_path(item, index)
        nonce = os.urandom(12)
        encoded = nonce + AESGCM(base64.b64decode(item['key'])).encrypt(nonce, data, self._chunk_aad(item, index))
        temporary = path.with_suffix('.tmp')
        with temporary.open('wb') as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(path)

    def _read_chunk(self, item, index):
        expected = min(CHUNK_SIZE, item['size'] - index * CHUNK_SIZE) + 28
        with self._chunk_path(item, index).open('rb') as source:
            encoded = source.read(expected + 1)
        if len(encoded) != expected:
            raise ValueError('El bloque almacenado tiene un tamaño inválido.')
        data = AESGCM(base64.b64decode(item['key'])).decrypt(encoded[:12], encoded[12:], self._chunk_aad(item, index))
        return data

    def _start(self, transfer_id):
        if transfer_id in self.workers:
            return
        if len(self.workers) >= 2:
            item = self._load(transfer_id)
            item.update(state='paused', error='Hay dos archivos preparándose. Reanuda cuando terminen.')
            self._save(item)
            return
        self.workers.add(transfer_id)
        worker = self._verify if self._load(transfer_id)['direction'] == 'to_pc' else self._prepare
        threading.Thread(target=worker, args=(transfer_id,), name='axx-file-copy', daemon=True).start()

    def _prepare(self, transfer_id):
        try:
            with self.lock:
                item = self._load(transfer_id)
            path, _ = self._source(item['device_id'], item['source'], item['source_version'])
            digest = hashlib.sha256()
            with path.open('rb') as source:
                if list(fingerprint(os.fstat(source.fileno()))) != item['source_version']:
                    raise ValueError('El archivo cambió antes de preparar la copia.')
                for index in range(item['chunk_count']):
                    with self.lock:
                        current = self._load(transfer_id)
                        if self.closed or current['state'] != 'preparing':
                            return
                        self._source(item['device_id'], item['source'], item['source_version'])
                        data = source.read(CHUNK_SIZE)
                        if len(data) != min(CHUNK_SIZE, item['size'] - index * CHUNK_SIZE):
                            raise ValueError('El archivo cambió durante la copia.')
                        digest.update(data)
                        chunk_hash = hashlib.sha256(data).hexdigest()
                        if index < current['next_index']:
                            if hashlib.sha256(self._read_chunk(current, index)).hexdigest() != chunk_hash:
                                raise ValueError('La versión de origen cambió; inicia una copia nueva.')
                        else:
                            self._write_chunk(current, index, data)
                        current['next_index'] = max(current['next_index'], index + 1)
                        current['prepared_bytes'] = min(current['size'], current['next_index'] * CHUNK_SIZE)
                        self._save(current)
                if source.read(1) or list(fingerprint(os.fstat(source.fileno()))) != item['source_version']:
                    raise ValueError('El archivo cambió durante la copia.')
            self._source(item['device_id'], item['source'], item['source_version'])
            with self.lock:
                current = self._load(transfer_id)
                if current['state'] == 'preparing':
                    current.update(state='ready', sha256=digest.hexdigest(), error=None)
                    self._save(current)
        except Exception:
            with self.lock:
                item = self._load(transfer_id)
                if item['state'] not in {'cancelled', 'paused'}:
                    item.update(state='failed', error='No se pudo preparar una copia íntegra. Comprueba el archivo y sus permisos.')
                    self._save(item)
        finally:
            self._worker_done(transfer_id)

    def _worker_done(self, transfer_id):
        with self.lock:
            self.workers.discard(transfer_id)
            if not self.closed and self._load(transfer_id)['state'] in {'preparing', 'verifying'}:
                self._start(transfer_id)

    def get(self, transfer_id, device_id=None):
        with self.lock:
            return self._public(self._load(transfer_id, device_id))

    def _verify(self, transfer_id):
        try:
            with self.lock:
                item = self._load(transfer_id)
            digest, size = hashlib.sha256(), 0
            for index in range(item['chunk_count']):
                with self.lock:
                    if self.closed or self._load(transfer_id)['state'] != 'verifying':
                        return
                    self._grant(item['device_id'], 'files.write')
                    data = self._read_chunk(item, index)
                digest.update(data)
                size += len(data)
            with self.lock:
                item = self._load(transfer_id)
                if item['state'] != 'verifying':
                    return
                if size != item['size'] or digest.hexdigest() != item['sha256']:
                    raise ValueError('El archivo recibido no coincide con su SHA-256.')
                self._grant(item['device_id'], 'files.write')
                item.update(state='completed', confirmed_bytes=size, completed_at=time.time(), error=None)
                self._save(item)
        except Exception:
            with self.lock:
                item = self._load(transfer_id)
                if item['state'] not in {'cancelled', 'paused'}:
                    item.update(state='failed', error='No se pudo verificar la integridad del archivo recibido.')
                    self._save(item)
        finally:
            self._worker_done(transfer_id)

    def chunk(self, device_id, body):
        if not isinstance(body, dict) or set(body) not in ({'transfer_id', 'index'}, {'transfer_id', 'index', 'data'}):
            raise ValueError('Bloque inválido.')
        with self.lock:
            item = self._load(body['transfer_id'], device_id)
            upload = item['direction'] == 'to_pc'
            self._grant(device_id, 'files.write' if upload else 'files.read')
            if not item.get('stored', True):
                raise ValueError('La copia cifrada se eliminó; se conserva únicamente su recibo.')
            index = body['index']
            if type(index) is not int or not 0 <= index < item['chunk_count']:
                raise ValueError('Índice de bloque inválido.')
            if not upload:
                if 'data' in body or item['state'] not in {'ready', 'completed'}:
                    raise ValueError('La copia aún no está disponible para descargar.')
                data = self._read_chunk(item, index)
                return {'index': index, 'data': base64.b64encode(data).decode(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if item['state'] not in {'receiving', 'completed'} or not isinstance(body.get('data'), str) or len(body['data']) > 4 * math.ceil(CHUNK_SIZE / 3):
                raise ValueError('La recepción está pausada o el bloque es inválido.')
            try:
                data = base64.b64decode(body['data'], validate=True)
            except Exception as exc:
                raise ValueError('El bloque no es Base64 válido.') from exc
            if len(data) != min(CHUNK_SIZE, item['size'] - index * CHUNK_SIZE):
                raise ValueError('El tamaño del bloque no coincide.')
            digest = hashlib.sha256(data).hexdigest()
            if index < item['next_index']:
                if hashlib.sha256(self._read_chunk(item, index)).hexdigest() != digest:
                    raise ValueError('No se puede sustituir un bloque ya confirmado.')
                return self._public(item)
            if index != item['next_index'] or item['state'] == 'completed':
                raise ValueError('Envía los bloques en orden, sin saltos.')
            self._write_chunk(item, index, data)
            item['next_index'] = index + 1
            item['confirmed_bytes'] = min(item['size'], item['next_index'] * CHUNK_SIZE)
            self._save(item)
            return self._public(item)

    def action(self, action, device_id, body):
        if not isinstance(body, dict) or set(body) != ({'transfer_id', 'size', 'sha256'} if action == 'receipt' else {'transfer_id'}):
            raise ValueError('Acción de transferencia inválida.')
        with self.lock:
            item = self._load(body['transfer_id'], device_id)
            self._grant(device_id, 'files.read' if item['direction'] == 'to_phone' else 'files.write')
            if action == 'cancel':
                if item['state'] == 'completed':
                    return self._public(item)
                item.update(state='cancelled', error=None, stored=False)
                self._save(item)
                for path in (self.directory / item['transfer_id']).iterdir():
                    if path.is_file():
                        path.unlink()
            elif action == 'pause':
                if item['state'] not in TERMINAL:
                    item.update(state='paused', error=None)
                    self._save(item)
            elif action == 'resume':
                if item['state'] == 'paused':
                    state = ('ready' if item['sha256'] else 'preparing') if item['direction'] == 'to_phone' else 'receiving'
                    item.update(state=state, error=None)
                    self._save(item)
                    if state == 'preparing':
                        self._start(item['transfer_id'])
            elif action == 'receipt':
                if item['direction'] != 'to_phone' or item['state'] not in {'ready', 'completed'} or type(body['size']) is not int or body['size'] != item['size'] or body['sha256'] != item['sha256']:
                    raise ValueError('El recibo no coincide con el archivo preparado.')
                item.update(state='completed', confirmed_bytes=item['size'], completed_at=time.time(), error=None)
                self._save(item)
            elif action == 'finish':
                if item['direction'] != 'to_pc' or item['state'] not in {'receiving', 'verifying', 'completed'}:
                    raise ValueError('Esta transferencia no puede confirmarse.')
                if item['state'] in {'verifying', 'completed'}:
                    return self._public(item)
                if item['next_index'] != item['chunk_count']:
                    raise ValueError('Faltan bloques por recibir.')
                item.update(state='verifying', error=None)
                self._save(item)
                self._start(item['transfer_id'])
            else:
                raise ValueError('Acción desconocida.')
            return self._public(self._load(item['transfer_id'], device_id))

    def save_downloads(self, body):
        if not isinstance(body, dict) or set(body) != {'transfer_id'}:
            raise ValueError('Selecciona un archivo recibido.')
        with self.lock:
            item = self._load(body['transfer_id'])
            if item['state'] != 'completed' or item['direction'] != 'to_pc' or not item.get('stored', True):
                raise ValueError('El archivo todavía no está recibido y verificado.')
            directory = _path(str(_downloads_directory()))
            name = Path(_name(item['name']))
            for number in range(1, 1001):
                filename = name.name if number == 1 else f'{name.stem} ({number}){name.suffix}'
                destination = directory / filename
                if destination.exists():
                    continue
                try:
                    return self.export({'transfer_id': item['transfer_id'], 'destination': str(destination)})
                except FileExistsError:
                    continue
            raise ValueError('Hay demasiados archivos con ese nombre en Descargas. Usa Guardar como.')

    def export(self, body):
        if not isinstance(body, dict) or set(body) != {'transfer_id', 'destination'}:
            raise ValueError('Selecciona la transferencia y un destino nuevo.')
        error = artifact_path_error(body['destination'])
        if error:
            raise ValueError(error)
        destination = Path(body['destination'])
        if not destination.is_absolute() or '..' in destination.parts or destination.exists():
            raise ValueError('El destino debe ser un archivo nuevo; no se sobrescriben archivos.')
        _path(str(destination.parent))
        if not destination.parent.is_dir():
            raise ValueError('La carpeta de destino no existe.')
        with self.lock:
            item = self._load(body['transfer_id'])
            if item['state'] != 'completed' or item['direction'] != 'to_pc' or not item.get('stored', True):
                raise ValueError('Solo se exportan archivos recibidos y verificados.')
            if shutil.disk_usage(destination.parent).free < item['size']:
                raise ValueError('No hay espacio suficiente en el destino.')
            temporary = destination.parent / ('.axx-' + str(uuid.uuid4()) + '.part')
            digest, size = hashlib.sha256(), 0
            try:
                with temporary.open('xb') as target:
                    for index in range(item['chunk_count']):
                        data = self._read_chunk(item, index)
                        target.write(data)
                        digest.update(data)
                        size += len(data)
                    target.flush()
                    os.fsync(target.fileno())
                if digest.hexdigest() != item['sha256'] or size != item['size']:
                    raise ValueError('No se exportó: la integridad del archivo no coincide.')
                _path(str(destination.parent))
                # Link publishes atomically without replacing an existing destination.
                os.link(temporary, destination)
                item['exported_at'] = time.time()
                self._save(item)
            finally:
                temporary.unlink(missing_ok=True)
            return {'transfer_id': item['transfer_id'], 'path': str(destination), 'size': size, 'sha256': digest.hexdigest(), 'state': 'exported'}

    def remove(self, body):
        if not isinstance(body, dict) or set(body) != {'transfer_id'}:
            raise ValueError('transfer_id requerido.')
        with self.lock:
            item = self._load(body['transfer_id'])
            if item['state'] not in TERMINAL:
                raise ValueError('Cancela la transferencia antes de eliminar su copia.')
            folder = self.directory / item['transfer_id']
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
            item['stored'] = False
            item.pop('key', None)
            self._save(item)
            return self._public(item)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for item in self._all():
                if item['state'] in {'preparing', 'verifying'}:
                    item.update(state='paused', error='Preparación pausada al cerrar Axx.')
                    self._save(item)
