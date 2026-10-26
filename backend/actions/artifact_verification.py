"""Bounded artifact inspection in a disposable worker, under the existing executor."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from .file_inspection import hash_file, validate_path

MAX_PDF_BYTES = 40 * 1024 * 1024


def inspect_pdf(raw):
    from pypdf import PdfReader
    path = validate_path(raw)
    with path.open('rb') as stream:
        content = stream.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES or not content.startswith(b'%PDF-'):
        raise ValueError('PDF inválido o mayor de 40 MiB')
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise ValueError('PDF cifrado: requiere una ruta explícita de desbloqueo')
    if not 1 <= len(reader.pages) <= 300:
        raise ValueError('Se admiten PDF de 1 a 300 páginas')
    pages, snippets = [], []
    for page in reader.pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        if not all(math.isfinite(v) and 0 < v <= 20000 for v in (width, height)):
            raise ValueError('Geometría de página inválida')
        # Reading each content stream catches broken objects; worker bounds parser time.
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > 8 * 1024 * 1024:
            raise ValueError('Contenido de página mayor de 8 MiB')
        text = page.extract_text() or ''
        snippets.append(text[:max(0, 10000 - sum(map(len, snippets)))])
        pages.append({'width_pt': width, 'height_pt': height, 'rotation': page.rotation})
    digest = hash_file(raw, threading.Event())
    if digest['sha256'] != hashlib.sha256(content).hexdigest():
        raise ValueError('El PDF cambió durante la inspección')
    return {**digest, 'page_count': len(pages), 'pages': pages, 'text_excerpt': '\n'.join(snippets),
            'verification': 'pdf_structure_and_content', 'visual_render_verified': False}


def inspect_media(raw):
    path = validate_path(raw)
    executable = shutil.which('ffprobe')
    if not executable or not Path(executable).is_absolute():
        raise ValueError('ffprobe no está disponible en PATH')
    before = hash_file(str(path), threading.Event())
    completed = subprocess.run([executable, '-v', 'error', '-protocol_whitelist', 'file',
        '-show_entries', 'format=duration,format_name:stream=index,codec_type,codec_name,width,height,sample_rate,channels,duration',
        '-of', 'json', str(path)], stdin=subprocess.DEVNULL, capture_output=True,
        timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode or len(completed.stdout) > 128 * 1024:
        raise ValueError('ffprobe no pudo comprobar el archivo multimedia')
    data = json.loads(completed.stdout)
    duration = float(data.get('format', {}).get('duration', 0))
    streams = data.get('streams', [])
    if not math.isfinite(duration) or duration <= 0 or not 1 <= len(streams) <= 64:
        raise ValueError('El archivo no tiene duración positiva y pistas comprobables')
    if not any(row.get('codec_type') in ('audio', 'video') for row in streams):
        raise ValueError('No hay pistas de audio o vídeo')
    after = hash_file(str(path), threading.Event())
    if before != after:
        raise ValueError('El archivo multimedia sigue cambiando')
    return {**after, 'duration_seconds': duration, 'streams': streams,
            'format': data['format'].get('format_name'), 'verification': 'ffprobe_metadata',
            'full_decode_verified': False}


def run_inspector(kind, path, cancelled=None):
    from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
    if kind not in ('pdf', 'media', 'ifc', 'ocr'):
        raise ValueError('Inspección no registrada')
    cancelled = cancelled or threading.Event()
    validate_path(path)
    if cancelled.is_set():
        raise ValueError('Inspección cancelada')
    command = ([sys.executable, '--artifact-worker'] if getattr(sys, 'frozen', False)
               else [sys.executable, '-m', 'backend.actions.artifact_verification'])
    process, job = spawn_managed_process(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    payload = json.dumps({'kind': kind, 'path': path}).encode()
    deadline = time.monotonic() + 25
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            from backend.inference.process_manager import JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation
            kernel = ctypes.windll.kernel32
            kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
            inside = wintypes.BOOL()
            if not job or not job.handle or not kernel.IsProcessInJob(process._handle, job.handle, ctypes.byref(inside)) or not inside.value:
                raise ValueError('El inspector no está dentro de su proceso supervisado')
            limit = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limit.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # kill-on-close, aggregate job memory
            limit.JobMemoryLimit = 1024 * 1024 * 1024
            if not kernel.SetInformationJobObject(job.handle, JobObjectExtendedLimitInformation, ctypes.byref(limit), ctypes.sizeof(limit)):
                raise ValueError('No se pudo limitar la memoria del inspector')
        while True:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise TimeoutError('Inspección cancelada o fuera de plazo')
            try:
                stdout, stderr = process.communicate(payload, timeout=.1)
                break
            except subprocess.TimeoutExpired:
                payload = None
        if len(stdout) > 256 * 1024 or len(stderr) > 256 * 1024:
            raise ValueError('La inspección excedió el límite de salida')
        result = json.loads(stdout)
        if process.returncode or not result.get('success'):
            raise ValueError(result.get('error', 'Fallo de inspección'))
        return result['output']
    finally:
        terminate_process_tree(process, job)


class ArtifactInspectTool:
    version = '1.0.0'

    def __init__(self, kind):
        if kind not in ('pdf', 'media', 'ocr'):
            raise ValueError('Inspección no registrada')
        self.kind, self.name = kind, 'artifact_' + kind
        self.description = 'Inspect a selected local ' + kind + ' and return bounded evidence'

    def verify_preconditions(self, inputs):
        try:
            if not isinstance(inputs, dict) or set(inputs) != {'path'}:
                raise ValueError('Indica sólo path')
            validate_path(inputs['path'])
            if self.kind == 'media' and not shutil.which('ffprobe'):
                raise ValueError('ffprobe no está instalado/configurado')
            return True, 'Archivo local y lector comprobados'
        except (ValueError, OSError, TypeError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid:
                raise ValueError(reason)
            output = run_inspector(self.kind, inputs['path'], cancelled)
            return ToolResult(True, output=output, evidence={'verification': output['verification']})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:600], evidence={'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        try:
            valid = bool(result.success and hash_file(inputs['path'], threading.Event())['sha256'] == result.output['sha256'])
            return valid, 'Archivo inspeccionado sin cambios' if valid else 'No se verificó el archivo'
        except (ValueError, OSError, KeyError) as exc:
            return False, str(exc)


def worker_main():
    try:
        request = json.loads(sys.stdin.buffer.read(4097))
        if set(request) != {'kind', 'path'} or request['kind'] not in ('pdf', 'media', 'ifc', 'ocr'):
            raise ValueError('Solicitud de inspector inválida')
        from .ifc_inventory import inspect_ifc
        from .local_ocr import inspect_ocr
        output = {'pdf': inspect_pdf, 'media': inspect_media, 'ifc': inspect_ifc, 'ocr': inspect_ocr}[request['kind']](request['path'])
        result = {'success': True, 'output': output}
    except Exception as exc:
        result = {'success': False, 'error': str(exc)[:600]}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(worker_main())
