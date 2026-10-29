"""Magic Pen evidence owned by the existing Axx backend; no action execution."""
from __future__ import annotations
import base64
import copy
from contextlib import closing, contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from PIL import Image, ImageDraw, ImageGrab
from backend.prompts import compose

MAX_QUERY_HISTORY = 100
MAX_RESPONSE_CHARS = 32000
TERMINAL_QUERY_STATES = frozenset({'completed', 'failed', 'cancelled', 'interrupted'})


@contextmanager
def physical_dpi_context():
    """Use physical pixels on this thread, then restore its exact prior context.

    System DPI awareness virtualizes coordinates on mixed-scale monitors. Never
    change process-wide awareness: input/UIA threads already own their contexts.
    """
    if os.name != 'nt':
        raise ValueError('La captura requiere Windows.')
    user = ctypes.WinDLL('user32', use_last_error=True)
    setter = getattr(user, 'SetThreadDpiAwarenessContext', None)
    if setter is None:
        raise ValueError('DPI_UNSUPPORTED: Windows no permite capturar con coordenadas físicas por monitor.')
    setter.argtypes = [wintypes.HANDLE]
    setter.restype = wintypes.HANDLE
    previous = setter(wintypes.HANDLE(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2.
    if not previous:
        raise OSError(ctypes.get_last_error(), 'No se pudo establecer el contexto DPI físico del hilo.')
    try:
        yield user
    finally:
        if not setter(wintypes.HANDLE(previous)):
            raise OSError(ctypes.get_last_error(), 'No se pudo restaurar el contexto DPI del hilo.')


def monitors():
    with physical_dpi_context() as user:
        result = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        def visit(_monitor, _dc, rect, _data):
            r = rect.contents
            result.append({'id': f'{r.left},{r.top},{r.right},{r.bottom}', 'x': r.left, 'y': r.top,
                           'width': r.right-r.left, 'height': r.bottom-r.top})
            return True
        callback = callback_type(visit)
        enum = user.EnumDisplayMonitors
        enum.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
        enum.restype = wintypes.BOOL
        if not enum(None, None, callback, 0):
            raise ValueError('No se pudieron enumerar las pantallas.')
        return result


def number(n):
    return type(n) in (int, float) and math.isfinite(n)


def point(p, w, h):
    return isinstance(p, list) and len(p) == 2 and all(number(n) for n in p) and 0 <= p[0] < w and 0 <= p[1] < h


def validate_selection(s, w, h):
    if s is None:
        return None
    if not isinstance(s, dict) or s.get('shape') not in ('rect', 'point', 'lasso'):
        raise ValueError('INVALID_GEOMETRY: selección inválida.')
    b = s.get('bounds')
    if not isinstance(b, list) or len(b) != 4 or not all(number(n) for n in b) or not (0 <= b[0] < b[2] <= w and 0 <= b[1] < b[3] <= h):
        raise ValueError('INVALID_GEOMETRY: región fuera de la imagen.')
    if s['shape'] == 'point' and not point(s.get('anchor'), w, h):
        raise ValueError('INVALID_GEOMETRY: ancla inválida.')
    if s['shape'] == 'lasso':
        pts = s.get('points')
        if not isinstance(pts, list) or not 3 <= len(pts) <= 4096 or not all(point(p, w, h) and b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] for p in pts):
            raise ValueError('INVALID_GEOMETRY: lazo inválido.')
        area = sum(a[0]*c[1]-c[0]*a[1] for a, c in zip(pts, pts[1:]+pts[:1]))
        if abs(area) < 2:
            raise ValueError('INVALID_GEOMETRY: lazo sin área.')
    return json.loads(json.dumps(s))


def validate_strokes(strokes, w, h):
    if not isinstance(strokes, list) or len(strokes) > 1000:
        raise ValueError('Demasiados trazos.')
    count = 0
    for s in strokes:
        if not isinstance(s, dict) or s.get('tool') not in ('pen', 'marker') or not re.fullmatch(r'#[a-fA-F0-9]{6}', str(s.get('color', ''))) or not number(s.get('width')) or not 1 <= s['width'] <= 80:
            raise ValueError('Trazo inválido.')
        pts = s.get('points')
        if not isinstance(pts, list) or not pts or not all(point(p, w, h) for p in pts):
            raise ValueError('Puntos de tinta inválidos.')
        count += len(pts)
    if count > 50000:
        raise ValueError('Límite de 50000 puntos por captura.')
    return strokes


def write_json(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class MagicPenService:
    def __init__(self, root, adapter=None):
        self.root = Path(root).resolve() / 'magic-pen'
        self.root.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.pending = self.processing = None
        self.worker = None
        self.closing = self.closed = False
        self.index_path = self.root / 'requests.sqlite'
        with closing(sqlite3.connect(self.index_path, timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS request_ids (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, signature TEXT NOT NULL)')
        for path in self.root.glob('*/document.json'):
            d = json.loads(path.read_text(encoding='utf-8'))
            with closing(sqlite3.connect(self.index_path, timeout=10)) as db, db:
                for q in d.get('queries', []):
                    db.execute('INSERT OR IGNORE INTO request_ids VALUES (?,?,?)', (q['id'], d['id'], '!legacy'))
            interrupted = [q for q in d.get('queries', []) if q.get('state') == 'running']
            if interrupted:
                for q in interrupted:
                    q.update(state='interrupted', finished_at=time.time(), error='Axx se cerró durante el análisis. Puedes volver a preguntar.')
                write_json(path, d)

    def _open(self):
        if self.closing or self.closed:
            raise ValueError('Magic Pen está cerrado.')

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closing = True
            jobs = [job for job in (self.pending, self.processing) if job]
            for job in jobs:
                self._cancel_job(job, 'Análisis cancelado al cerrar Axx.')
            self.pending = None
            self.condition.notify_all()
            worker = self.worker
        for job in jobs:
            self._cancel_adapter(job['id'])
        if worker and worker is not threading.current_thread():
            worker.join(timeout=5)
        with self.lock:
            # The existing adapter owns the bounded upstream deadline. A daemon still
            # unwinding is cancelled; its response cannot publish after closing.
            self.closed = True

    def directory(self, id):
        if not isinstance(id, str) or not re.fullmatch('[a-f0-9]{32}', id):
            raise ValueError('Referencia de captura inválida.')
        return self.root / id

    def capabilities(self):
        providers = getattr(self.adapter, 'config', {}).get('providers', [])
        vision = [{'name': p['name'], 'model': p['model']} for p in providers if p.get('enabled', True) and (p.get('free_confirmed') is True or p.get('billing_allowed') is True) and 'vision' in p.get('capabilities', [])]
        return {'vision': vision, 'ocr': False, 'ocr_message': 'OCR no integrado; el proveedor visual puede leer texto si está configurado.', 'export_directory': str(self.root / 'exports')}

    def list(self):
        with self.lock:
            docs = []
            for path in self.root.glob('*/document.json'):
                d = json.loads(path.read_text(encoding='utf-8'))
                docs.append({'id': d['id'], 'source': d['source'], 'revision': d['revision']})
            return sorted(docs, key=lambda d: d['source']['captured_at'], reverse=True)[:100]

    def get(self, id, image=False):
        with self.lock:
            directory = self.directory(id)
            d = json.loads((directory / 'document.json').read_text(encoding='utf-8'))
            if image:
                original = self.original(d)
                original.thumbnail((1600, 1000))
                buf = io.BytesIO()
                original.save(buf, format='PNG')
                d['preview'] = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
            return d

    def original(self, d):
        raw = (self.directory(d['id']) / 'original.png').read_bytes()
        if hashlib.sha256(raw).hexdigest() != d['source']['sha256']:
            raise ValueError('El original no supera la comprobación de integridad.')
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if list(im.size) != [d['source']['width'], d['source']['height']]:
                raise ValueError('Dimensiones del original inválidas.')
            return im.convert('RGB')

    def capture(self, body):
        with physical_dpi_context():
            source = next((m for m in monitors() if m['id'] == body.get('monitor')), None)
            if not source:
                raise ValueError('SOURCE_UNAVAILABLE: la pantalla cambió o se desconectó. Selecciónala otra vez.')
            x, y, w, h = (source[k] for k in ('x', 'y', 'width', 'height'))
            if w*h > 34000000:
                raise ValueError('CAPTURE_UNSUPPORTED: máximo 34 megapíxeles.')
            im = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
            if im.size != (w, h) or source not in monitors():
                raise ValueError('SOURCE_UNAVAILABLE: la pantalla cambió durante la captura.')
        return self.acquire(im, source)

    def acquire(self, im, source, *, image=False):
        with self.lock:
            self._open()
        id = uuid.uuid4().hex
        directory = self.directory(id)
        directory.mkdir()
        path = directory / 'original.png'
        im.convert('RGB').save(path)
        with Image.open(path) as check:
            check.verify()
        d = {'id': id, 'revision': 1, 'source': {**source, 'width': im.width, 'height': im.height,
             'captured_at': time.time(), 'revision': 1, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
             'selection': None, 'strokes': [], 'queries': [], 'exports': []}
        write_json(directory / 'document.json', d)
        return self.get(id, image=image)

    def save(self, body):
        with self.lock:
            d = self.get(body.get('id'))
            if body.get('expected_revision') != d['revision']:
                raise ValueError('STALE_REVISION: vuelve a abrir la captura antes de editar.')
            w, h = d['source']['width'], d['source']['height']
            d['selection'] = validate_selection(body.get('selection'), w, h)
            d['strokes'] = validate_strokes(body.get('strokes'), w, h)
            d['revision'] += 1
            write_json(self.directory(d['id']) / 'document.json', d)
            return d

    def export(self, body):
        with self.lock:
            d = self.get(body.get('id'))
            if body.get('revision') != d['revision']:
                raise ValueError('STALE_REVISION: guarda los cambios primero.')
        kind = body.get('kind')
        if kind not in ('original', 'annotated'):
            raise ValueError('Elige original o anotado.')
        name = body.get('name', '')
        if not isinstance(name, str) or not re.fullmatch(r'[\w -]{1,100}', name) or name.endswith((' ', '.')) or name.upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(10)),*(f'LPT{i}' for i in range(10))}:
            raise ValueError('Nombre de archivo inválido.')
        directory = Path(body.get('directory', ''))
        if not directory.is_absolute():
            raise ValueError('El destino debe ser una carpeta absoluta.')
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (name + '.png')
        if target.exists():
            raise FileExistsError('Ya existe ese archivo. Elige otro nombre.')
        im = self.original(d).convert('RGBA')
        if kind == 'annotated':
            for stroke in d['strokes']:
                layer = Image.new('RGBA', im.size)
                draw = ImageDraw.Draw(layer)
                rgb = tuple(bytes.fromhex(stroke['color'][1:]))
                color = (*rgb, 85 if stroke['tool'] == 'marker' else 255)
                pts = [tuple(p) for p in stroke['points']]
                width = max(1, round(stroke['width']))
                draw.line(pts + pts[-1:], fill=color, width=width, joint='curve')
                r = width/2
                for x, y in (pts[0], pts[-1]):
                    draw.ellipse((x-r,y-r,x+r,y+r), fill=color)
                im = Image.alpha_composite(im, layer)
        temp = directory / ('.' + uuid.uuid4().hex + '.tmp')
        try:
            im.convert('RGB').save(temp, format='PNG')
            with Image.open(temp) as check:
                check.load()
                if check.size != im.size:
                    raise ValueError('EXPORT_FAILED: dimensiones incorrectas.')
            # Publish without replacing another file, including a concurrent export.
            os.link(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        with Image.open(target) as check:
            check.verify()
        result = {'path': str(target), 'kind': kind, 'revision': d['revision'], 'verified': True,
                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size}
        with self.lock:
            current = self.get(d['id'])
            current['exports'].append(result)
            write_json(self.directory(d['id']) / 'document.json', current)
        return result

    def _request(self, body):
        if not isinstance(body, dict) or set(body) - {'id', 'revision', 'question', 'provider', 'model', 'selection_mode', 'request_id'}:
            raise ValueError('Parámetros de análisis inválidos.')
        self.directory(body.get('id'))
        request_id = body.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id):
            raise ValueError('request_id debe contener 32 caracteres hexadecimales.')
        if type(body.get('revision')) is not int or body['revision'] < 1:
            raise ValueError('Revisión de captura inválida.')
        question = body.get('question')
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            raise ValueError('Escribe una pregunta de hasta 4000 caracteres.')
        provider, model = body.get('provider', ''), body.get('model', '')
        if any(not isinstance(value, str) or len(value) > 200 for value in (provider, model)):
            raise ValueError('Proveedor o modelo inválido.')
        mode = body.get('selection_mode', 'manual')
        if mode not in ('manual', 'automatic_free'):
            raise ValueError('Modo de selección inválido.')
        return {'id': body['id'], 'revision': body['revision'], 'question': question,
                'provider': provider, 'model': model, 'selection_mode': mode, 'request_id': request_id}

    def _provider(self, request):
        if not self.adapter or getattr(self.adapter, 'config', {}).get('allow_paid', False) is not False:
            raise ValueError('Análisis visual no configurado con la política existente.')
        if request['selection_mode'] == 'automatic_free':
            return {'name': '', 'model': ''}
        providers = self.capabilities()['vision']
        chosen = None
        if request['provider']:
            chosen = next((p for p in providers if p['name'] == request['provider']), None)
            if not chosen:
                raise ValueError('El proveedor seleccionado no está disponible para visión. Selecciona otro explícitamente.')
            if request['model'] and request['model'] != chosen['model']:
                raise ValueError('El modelo seleccionado no coincide con la ruta visual configurada.')
        elif request['model']:
            matches = [p for p in providers if p['model'] == request['model']]
            if len(matches) != 1:
                raise ValueError('Elige un proveedor visual para el modelo seleccionado; no hay una ruta única.')
            chosen = matches[0]
        elif providers:
            chosen = providers[0]  # Compatibility for callers without a selection.
        if not chosen:
            raise ValueError('Análisis visual no configurado. Conecta un proveedor de Axx con capacidad de visión.')
        return dict(chosen)

    @staticmethod
    def _append_query(document, query):
        history = [*document.get('queries', []), query]
        while len(history) > MAX_QUERY_HISTORY:
            index = next((i for i, item in enumerate(history) if item.get('state') != 'running'), None)
            if index is None:
                break
            history.pop(index)
        document['queries'] = history

    def start(self, body):
        request = self._request(body)
        signature = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.condition:
            self._open()
            with closing(sqlite3.connect(self.index_path, timeout=10)) as db:
                old = db.execute('SELECT source_id,signature FROM request_ids WHERE id=?', (request['request_id'],)).fetchone()
            if old:
                if old == (request['id'], '!cancelled'):
                    with closing(sqlite3.connect(self.index_path, timeout=10)) as db, db:
                        db.execute('UPDATE request_ids SET signature=? WHERE id=?', (signature, request['request_id']))
                    return self.query({'id': request['id'], 'query_id': request['request_id']})
                if old != (request['id'], signature):
                    raise ValueError('REQUEST_ID_CONFLICT: el identificador pertenece a otra pregunta o selección.')
                return self.query({'id': request['id'], 'query_id': request['request_id']})
            d = self.get(request['id'])
            if request['revision'] != d['revision'] or not d['selection']:
                raise ValueError('STALE_REVISION: guarda una selección antes de preguntar.')
            if any(job and not job['cancel'].is_set() and self.query({'id': job['source_id'], 'query_id': job['id']})['state'] == 'running'
                   for job in (self.pending, self.processing)):
                raise ValueError('BUSY: cancela el análisis actual antes de iniciar otro.')
            q = {'id': request['request_id'], 'source_id': d['id'], 'revision': d['revision'],
                 'selection': copy.deepcopy(d['selection']), 'question': request['question'], 'state': 'running',
                 'created_at': time.time(), 'provider': {'name': request['provider'], 'model': request['model']},
                 'selection_mode': request['selection_mode'], 'source_sha256': d['source']['sha256']}
            try:
                q['provider'] = self._provider(request)
            except ValueError as exc:
                q.update(state='failed', error=str(exc), finished_at=time.time())
            # The compact durable index keeps old IDs reserved when visible history
            # is pruned. A replay can never accidentally start another inference.
            with closing(sqlite3.connect(self.index_path, timeout=10)) as db, db:
                db.execute('INSERT INTO request_ids VALUES (?,?,?)', (q['id'], d['id'], signature))
            self._append_query(d, q)
            write_json(self.directory(d['id']) / 'document.json', d)
            if q['state'] != 'running':
                return copy.deepcopy(q)
            snapshot = {name: copy.deepcopy(d[name]) for name in ('id', 'source', 'selection')}
            self.pending = {'id': q['id'], 'source_id': d['id'], 'snapshot': snapshot,
                            'request': request, 'query': copy.deepcopy(q), 'cancel': threading.Event(),
                            'route_done': threading.Event()}
            if not self.worker or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._work, name='axx-magic-pen', daemon=True)
                self.worker.start()
            self.condition.notify_all()
            return copy.deepcopy(q)

    def query(self, body):
        if not isinstance(body, dict) or set(body) != {'id', 'query_id'}:
            raise ValueError('Referencia de consulta inválida.')
        self.directory(body['query_id'])  # Query IDs use the same closed identifier grammar.
        with self.lock:
            d = self.get(body['id'])
            q = next((q for q in d.get('queries', []) if q['id'] == body['query_id']), None)
            if not q:
                raise ValueError('La consulta no existe en esta captura o salió del historial reciente; no se repetirá.')
            return copy.deepcopy(q)

    def _replace_query(self, source_id, query_id, changes):
        with self.lock:
            d = self.get(source_id)
            q = next((q for q in d.get('queries', []) if q['id'] == query_id), None)
            if not q:
                return None
            if q['state'] == 'running':
                q.update(changes)
                write_json(self.directory(source_id) / 'document.json', d)
            return copy.deepcopy(q)

    def _cancel_adapter(self, query_id):
        if self.adapter and hasattr(self.adapter, 'cancel'):
            try:
                self.adapter.cancel('pen-' + query_id)
            except Exception:
                pass  # The persistent cancellation still excludes a late answer.

    def _cancel_job(self, job, reason):
        job['cancel'].set()
        self._replace_query(job['source_id'], job['id'],
                            {'state': 'cancelled', 'error': reason, 'finished_at': time.time()})

    def cancel(self, body):
        with self.condition:
            if not isinstance(body, dict) or set(body) != {'id', 'query_id'}:
                raise ValueError('Referencia de consulta inválida.')
            self.directory(body['query_id'])
            d = self.get(body['id'])
            q = next((q for q in d.get('queries', []) if q['id'] == body['query_id']), None)
            if not q:
                with closing(sqlite3.connect(self.index_path, timeout=10)) as db, db:
                    previous = db.execute('SELECT source_id FROM request_ids WHERE id=?', (body['query_id'],)).fetchone()
                    if previous:
                        raise ValueError('La consulta pertenece a otra captura o salió del historial reciente.')
                    db.execute('INSERT INTO request_ids VALUES (?,?,?)', (body['query_id'], d['id'], '!cancelled'))
                q = {'id': body['query_id'], 'source_id': d['id'], 'revision': d['revision'],
                     'selection': copy.deepcopy(d['selection']), 'question': '', 'provider': {'name': '', 'model': ''},
                     'state': 'cancelled', 'created_at': time.time(), 'finished_at': time.time(),
                     'error': 'Cancelado antes de iniciar el análisis.', 'preparation_cancelled': True}
                self._append_query(d, q)
                write_json(self.directory(d['id']) / 'document.json', d)
                return copy.deepcopy(q)
            if q['state'] in TERMINAL_QUERY_STATES:
                return copy.deepcopy(q)
            for job in (self.pending, self.processing):
                if job and job['id'] == q['id'] and job['source_id'] == q['source_id']:
                    self._cancel_job(job, 'Análisis cancelado. Puedes seleccionar otra zona.')
            self._replace_query(q['source_id'], q['id'],
                                {'state': 'cancelled', 'error': 'Análisis cancelado.', 'finished_at': time.time()})
            if self.pending and self.pending['id'] == q['id']:
                self.pending = None
            self.condition.notify_all()
            result = self.query(body)
        self._cancel_adapter(q['id'])
        return result

    def _watch_cancellation(self, job):
        # cancel() can arrive before InferenceAdapter registers active_requests.
        # Keep signalling until route exits, rather than treating the first False
        # response as evidence that cancellation finished.
        while not job['route_done'].wait(.02):
            if job['cancel'].is_set():
                self._cancel_adapter(job['id'])

    def _work(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.closing)
                if self.closing:
                    return
                job = self.pending
                self.pending = None
                self.processing = job
            try:
                self._run(job)
            finally:
                job['route_done'].set()
                with self.condition:
                    if self.processing is job:
                        self.processing = None
                    self.condition.notify_all()

    def _run(self, job):
        watcher = None
        try:
            if job['cancel'].is_set():
                return
            d, q, request = job['snapshot'], job['query'], job['request']
            im = self.original(d)
            s = q['selection']
            if s['shape'] == 'lasso':
                mask = Image.new('L', im.size)
                ImageDraw.Draw(mask).polygon([tuple(p) for p in s['points']], fill=255)
                im = Image.composite(im, Image.new('RGB', im.size, 'white'), mask)
            b = s['bounds']
            im = im.crop((math.floor(b[0]), math.floor(b[1]), math.ceil(b[2]), math.ceil(b[3])))
            im.thumbnail((1280, 1280))
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=88)
            if job['cancel'].is_set():
                return
            event_support = getattr(self.adapter, 'supports_cancel_event', False) is True
            if not event_support:
                watcher = threading.Thread(target=self._watch_cancellation, args=(job,), name='axx-pen-cancel', daemon=True)
                watcher.start()
            chosen = q['provider']
            result = self.adapter.route({'request_id': 'pen-' + q['id'], 'conversation_id': 'pen-' + q['id'],
                'task': 'vision', 'selection_mode': request['selection_mode'], 'allow_paid': False, 'deadline_ms': 70000,
                'provider_name': chosen['name'], 'model': chosen['model'], 'generation': {'max_tokens': 1024},
                'messages': [{'role': 'system', 'content': compose('perception', contract='Responde en español sobre la imagen seleccionada.')['text']},
                    {'role': 'user', 'content': [{'type': 'text', 'text': q['question']}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}}]}]},
                **({'cancel_event': job['cancel']} if event_support else {}))
            if not isinstance(result, dict) or result.get('ok') is not True:
                error = result.get('error', {}) if isinstance(result, dict) else {}
                raise ValueError(str(error.get('message', 'El proveedor no respondió.'))[:2000])
            message = result.get('message', {})
            text = message.get('content') if isinstance(message, dict) else None
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_RESPONSE_CHARS:
                raise ValueError('El proveedor no devolvió texto válido dentro del límite.')
            with self.lock:
                if not job['cancel'].is_set() and not self.closing:
                    self._replace_query(d['id'], q['id'], {'state': 'completed', 'response': text,
                                        'route': result.get('route'), 'finished_at': time.time()})
        except Exception as exc:
            with self.lock:
                if not job['cancel'].is_set() and not self.closing:
                    self._replace_query(job['source_id'], job['id'],
                                        {'state': 'failed', 'error': str(exc)[:2000], 'finished_at': time.time()})
        finally:
            job['route_done'].set()
            if watcher:
                watcher.join(timeout=.1)

    def analyze(self, body):
        """Legacy synchronous endpoint using the same bounded job lifecycle."""
        if not isinstance(body, dict):
            raise ValueError('Parámetros de análisis inválidos.')
        request = dict(body)
        request.setdefault('request_id', uuid.uuid4().hex)
        q = self.start(request)
        while q['state'] == 'running':
            with self.condition:
                self.condition.wait(timeout=.05)
            q = self.query({'id': q['source_id'], 'query_id': q['id']})
        return q
