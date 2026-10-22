"""Bounded local conversion jobs for the Axx Convertidor panel."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_FILE = 30 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
MAX_CHUNK = 384 * 1024
MAX_PIXELS = 40_000_000


def _pdf():
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise ValueError('El motor PDF no está incluido en este paquete de Axx.') from exc
    return PdfReader, PdfWriter


def _pages(spec, count):
    if not isinstance(spec, str) or not re.fullmatch(r'[0-9,\-\s]{1,200}', spec):
        raise ValueError('Indica páginas como 1, 3-5.')
    pages = []
    for part in spec.split(','):
        match = re.fullmatch(r'\s*(\d+)(?:\s*-\s*(\d+))?\s*', part)
        if not match:
            raise ValueError('Rango de páginas inválido.')
        first, last = int(match[1]), int(match[2] or match[1])
        if first < 1 or last < first or last > count:
            raise ValueError('Página fuera del documento.')
        pages.extend(range(first - 1, last))
    if len(pages) != len(set(pages)):
        raise ValueError('Una página aparece más de una vez.')
    return pages


class ConverterService:
    def __init__(self, workspace_root):
        self.root = Path(workspace_root).resolve() / 'converter'
        self.root.mkdir(parents=True, exist_ok=True)
        # shortcut: in-flight jobs are session-local; add durable resume when long CAD jobs arrive.
        self.jobs = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(2)
        for folder in self.root.iterdir():
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r'[a-f0-9]{32}', folder.name) or (folder / 'manifest.json').exists():
                continue
            for path in [*folder.glob('input-*'), folder / 'output.tmp', folder / 'manifest.tmp',
                         folder / 'convertido.jpg', folder / 'convertido.png', folder / 'unido.pdf', folder / 'paginas.pdf']:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            marker = folder / 'incomplete.json'
            if not marker.exists():
                marker.write_text(json.dumps({'id': folder.name, 'state': 'interrupted', 'created': folder.stat().st_mtime}), encoding='utf-8')

    def _job(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Referencia de trabajo inválida.')
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError('Trabajo no encontrado en esta sesión.')
        return job

    def new(self, files):
        if not isinstance(files, list) or not 1 <= len(files) <= 10:
            raise ValueError('Elige entre 1 y 10 archivos.')
        clean = []
        for item in files:
            if not isinstance(item, dict) or set(item) != {'name', 'size'} or not isinstance(item['name'], str) or not 1 <= len(item['name']) <= 180 or '/' in item['name'] or '\\' in item['name'] or type(item['size']) is not int or not 0 < item['size'] <= MAX_FILE:
                raise ValueError('Nombre o tamaño de entrada inválido (máximo 30 MB por archivo).')
            clean.append({'name': item['name'], 'size': item['size'], 'received': 0})
        if sum(x['size'] for x in clean) > MAX_TOTAL:
            raise ValueError('El lote supera 60 MB.')
        job_id = uuid.uuid4().hex
        folder = self.root / job_id
        folder.mkdir()
        job = {'id': job_id, 'files': clean, 'state': 'uploading', 'stage': 'Recibiendo archivos', 'created': time.time(), 'cancel': False, 'result': None, 'error': None}
        with self.lock:
            self.jobs[job_id] = job
        return self.status(job_id)

    def upload(self, job_id, index, offset, data):
        with self.lock:
            job = self._job(job_id)
            if job['state'] != 'uploading' or type(index) is not int or not 0 <= index < len(job['files']) or type(offset) is not int:
                raise ValueError('Carga no disponible.')
            item = job['files'][index]
            if offset != item['received'] or not isinstance(data, str) or len(data) > 4 * MAX_CHUNK // 3 + 8:
                raise ValueError('Fragmento fuera de orden o demasiado grande.')
            try:
                chunk = base64.b64decode(data, validate=True)
            except Exception as exc:
                raise ValueError('Fragmento base64 inválido.') from exc
            if not chunk or len(chunk) > MAX_CHUNK or offset + len(chunk) > item['size']:
                raise ValueError('Fragmento fuera de límites.')
            path = self.root / job_id / f'input-{index}'
            with path.open('ab') as stream:
                stream.write(chunk)
            item['received'] += len(chunk)
            return {'received': item['received'], 'size': item['size']}

    def probe(self, job_id):
        with self.lock:
            job = self._job(job_id)
            if job['state'] != 'uploading' or any(x['received'] != x['size'] for x in job['files']):
                raise ValueError('La carga todavía no está completa.')
        info = []
        for index, item in enumerate(job['files']):
            path = self.root / job_id / f'input-{index}'
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    if image.format not in {'PNG', 'JPEG'} or getattr(image, 'n_frames', 1) != 1 or image.width * image.height > MAX_PIXELS:
                        raise ValueError('Imagen no compatible con las rutas iniciales.')
                    info.append({'name': item['name'], 'kind': image.format.lower(), 'width': image.width, 'height': image.height, 'sha256': digest, 'size': item['size']})
                continue
            except (UnidentifiedImageError, OSError):
                pass
            with path.open('rb') as stream:
                signature = stream.read(5)
            if signature != b'%PDF-':
                raise ValueError(f'{item["name"]}: formato real no admitido.')
            PdfReader, _ = _pdf()
            try:
                with path.open('rb') as stream:
                    reader = PdfReader(stream, strict=True)
                    if reader.is_encrypted:
                        raise ValueError('PDF protegido: esta ruta requiere un archivo sin contraseña.')
                    if reader.trailer['/Root'].get('/AcroForm'):
                        raise ValueError('PDF con formularios o firmas: esta ruta inicial no lo modifica con seguridad.')
                    sizes = [[float(page.mediabox.width), float(page.mediabox.height)] for page in reader.pages]
                    if not sizes:
                        raise ValueError('PDF sin páginas.')
                    if len(sizes) > 1000:
                        raise ValueError('Este PDF supera el límite inicial de 1000 páginas.')
                    info.append({'name': item['name'], 'kind': 'pdf', 'pages': len(sizes), 'page_sizes_pt': sizes, 'sha256': digest, 'size': item['size']})
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f'{item["name"]}: PDF ilegible o malformado.') from exc
        with self.lock:
            job['info'] = info
            job['state'] = 'ready'
            job['stage'] = 'Revisar operación y pérdidas'
        return self.status(job_id)

    def run(self, job_id, operation, options):
        with self.lock:
            job = self._job(job_id)
            if job['state'] != 'ready' or not isinstance(options, dict):
                raise ValueError('Inspecciona los archivos antes de ejecutar.')
            kinds = [x['kind'] for x in job['info']]
            if operation == 'png-jpeg' and (len(kinds) != 1 or kinds[0] != 'png' or set(options) != {'background', 'quality'} or not isinstance(options['background'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', options['background']) or type(options['quality']) is not int or not 20 <= options['quality'] <= 100):
                raise ValueError('Opciones PNG→JPEG inválidas.')
            if operation == 'jpeg-png' and (len(kinds) != 1 or kinds[0] != 'jpeg' or options):
                raise ValueError('Opciones JPEG→PNG inválidas.')
            if operation == 'pdf-merge' and (len(kinds) < 2 or set(kinds) != {'pdf'} or options):
                raise ValueError('Unir requiere al menos dos PDF.')
            if operation == 'pdf-extract' and (len(kinds) != 1 or kinds[0] != 'pdf' or set(options) != {'pages'}):
                raise ValueError('Extraer requiere un PDF y páginas.')
            if operation not in {'png-jpeg', 'jpeg-png', 'pdf-merge', 'pdf-extract'}:
                raise ValueError('Operación no disponible.')
            if operation == 'pdf-extract':
                options = {'pages': _pages(options['pages'], job['info'][0]['pages'])}
            if not self.slots.acquire(blocking=False):
                raise ValueError('Hay dos conversiones en curso. Espera a que termine una.')
            job['state'] = 'running'
            job['stage'] = 'Convirtiendo'
            threading.Thread(target=self._execute, args=(job_id, operation, options), daemon=True).start()
        return self.status(job_id)

    def _execute(self, job_id, operation, options):
        folder = self.root / job_id
        job = self.jobs[job_id]
        temp = folder / 'output.tmp'
        manifest_temp = folder / 'manifest.tmp'
        final = None
        published = False
        try:
            if operation in {'png-jpeg', 'jpeg-png'}:
                with Image.open(folder / 'input-0') as source:
                    image = ImageOps.exif_transpose(source)
                    image.load()
                    if image.width * image.height > MAX_PIXELS:
                        raise ValueError('Imagen demasiado grande.')
                    if operation == 'png-jpeg':
                        color = tuple(bytes.fromhex(options['background'][1:]))
                        rgba = image.convert('RGBA')
                        result = Image.new('RGB', rgba.size, color)
                        result.paste(rgba, mask=rgba.getchannel('A'))
                        fmt, ext = 'JPEG', 'jpg'
                        result.save(temp, format=fmt, quality=options['quality'], icc_profile=source.info.get('icc_profile'))
                    else:
                        fmt, ext = 'PNG', 'png'
                        image.save(temp, format=fmt, icc_profile=source.info.get('icc_profile'))
                with Image.open(temp) as check:
                    check.verify()
                with Image.open(temp) as check:
                    if check.format != fmt or check.size != (image.width, image.height):
                        raise ValueError('La salida no coincide con la imagen de entrada.')
                expected = {'format': fmt, 'width': image.width, 'height': image.height}
            else:
                PdfReader, PdfWriter = _pdf()
                writer = PdfWriter()
                for index in range(len(job['info'])):
                    if job['cancel']:
                        raise InterruptedError('Cancelado.')
                    with (folder / f'input-{index}').open('rb') as stream:
                        reader = PdfReader(stream, strict=True)
                        page_indices = options['pages'] if operation == 'pdf-extract' else range(len(reader.pages))
                        for page_index in page_indices:
                            if job['cancel']:
                                raise InterruptedError('Cancelado.')
                            writer.add_page(reader.pages[page_index])
                expected = {'pages': len(writer.pages), 'page_sizes_pt': [[float(p.mediabox.width), float(p.mediabox.height)] for p in writer.pages]}
                with temp.open('wb') as stream:
                    writer.write(stream)
                with temp.open('rb') as stream:
                    check = PdfReader(stream, strict=True)
                    actual = [[float(p.mediabox.width), float(p.mediabox.height)] for p in check.pages]
                    if actual != expected['page_sizes_pt']:
                        raise ValueError('La estructura de páginas de salida no coincide.')
                ext = 'pdf'
            if job['cancel']:
                raise InterruptedError('Cancelado.')
            job['stage'] = 'Validando y publicando'
            name = ('unido' if operation == 'pdf-merge' else 'paginas' if operation == 'pdf-extract' else 'convertido') + '.' + ext
            final = folder / name
            if final.exists():
                raise FileExistsError('La salida ya existe.')
            result = {'id': job_id, 'path': str(final), 'name': name, 'size': temp.stat().st_size, 'sha256': hashlib.sha256(temp.read_bytes()).hexdigest(), 'verified': expected, 'operation': operation, 'inputs': job['info']}
            manifest = folder / 'manifest.json'
            with manifest_temp.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp, final)
            published = True
            os.rename(manifest_temp, manifest)
            with self.lock:
                job.update(state='done', stage='Resultado verificado', result=result)
        except InterruptedError:
            with self.lock:
                job.update(state='cancelled', stage='Cancelado')
        except Exception as exc:
            with self.lock:
                job.update(state='failed', stage='Error', error=str(exc))
        finally:
            temp.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
            if published and job['state'] != 'done':
                final.unlink(missing_ok=True)
            for index in range(len(job['files'])):
                (folder / f'input-{index}').unlink(missing_ok=True)
            if job['state'] in {'failed', 'cancelled'}:
                try:
                    (folder / 'incomplete.json').write_text(json.dumps({'id': job_id, 'state': job['state'], 'created': job['created']}), encoding='utf-8')
                except OSError:
                    pass
            self.slots.release()

    def cancel(self, job_id):
        with self.lock:
            job = self._job(job_id)
            job['cancel'] = True
            if job['state'] in {'uploading', 'ready'}:
                job.update(state='cancelled', stage='Cancelado')
                for index in range(len(job['files'])):
                    (self.root / job_id / f'input-{index}').unlink(missing_ok=True)
                try:
                    (self.root / job_id / 'incomplete.json').write_text(json.dumps({'id': job_id, 'state': 'cancelled', 'created': job['created']}), encoding='utf-8')
                except OSError:
                    pass
        return self.status(job_id)

    def status(self, job_id):
        with self.lock:
            job = self._job(job_id)
            return {**{key: job.get(key) for key in ('id', 'files', 'info', 'state', 'stage', 'created', 'result', 'error')}, 'output_directory': str(self.root / job_id)}

    def history(self):
        results = []
        for path in sorted(self.root.glob('*/manifest.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            try:
                results.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        interrupted = []
        for path in sorted(self.root.glob('*/incomplete.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            try:
                interrupted.append(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return {'results': results, 'incomplete': interrupted}

    def open_result(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Referencia de trabajo inválida.')
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job['state'] != 'done':
                raise ValueError('No hay resultado verificado.')
            if job:
                path = Path(job['result']['path'])
            else:
                manifest = self.root / job_id / 'manifest.json'
                if not manifest.is_file():
                    raise ValueError('Resultado no encontrado.')
                path = Path(json.loads(manifest.read_text(encoding='utf-8'))['path'])
            if path.parent != self.root / job_id or not path.is_file():
                raise ValueError('Resultado no encontrado.')
        if os.name != 'nt':
            raise ValueError('Abrir carpeta solo está disponible en Windows.')
        os.startfile(str(path.parent))
        return {'opened': str(path.parent)}
