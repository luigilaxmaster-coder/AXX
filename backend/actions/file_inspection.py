"""Bounded hashing of explicitly selected local files, without shell evaluation."""
import hashlib
import os
from pathlib import Path
import threading

MAX_BYTES = 512 * 1024 * 1024


def validate_path(raw):
    from .tools import artifact_path_error
    error = artifact_path_error(raw)
    if error:
        raise ValueError(error)
    path = Path(raw)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('Indica la ruta absoluta de un archivo local existente.')
    info = path.stat()
    if getattr(info, 'st_file_attributes', 0) & (0x1000 | 0x40000 | 0x400000):
        raise ValueError('El archivo debe estar disponible localmente antes de leerlo.')
    if info.st_size > MAX_BYTES:
        raise ValueError('El archivo supera el límite de 512 MiB.')
    return path


def fingerprint(info):
    # Windows path-stat and handle-stat can report different creation/change
    # timestamps. Identity, content length and modification time agree.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def hash_file(raw, cancelled):
    path = validate_path(raw)
    before = path.stat()
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
            raise ValueError('El archivo cambió antes de la lectura.')
        while chunk := stream.read(1024 * 1024):
            if cancelled.is_set():
                raise ValueError('Lectura cancelada.')
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('El archivo creció por encima del límite de lectura.')
            digest.update(chunk)
        if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
            raise ValueError('El archivo cambió durante la lectura; el hash no es válido.')
    if fingerprint(path.stat()) != fingerprint(before) or size != before.st_size:
        raise ValueError('El archivo fue sustituido durante la lectura.')
    return {'path': str(path), 'sha256': digest.hexdigest(), 'bytes': size}


def inspect_files(inputs, cancelled=None):
    cancelled = cancelled or threading.Event()
    files = [hash_file(inputs['path'], cancelled)]
    if 'other_path' in inputs:
        files.append(hash_file(inputs['other_path'], cancelled))
    return {'files': files, **({'equal': files[0]['sha256'] == files[1]['sha256']} if len(files) == 2 else {})}
