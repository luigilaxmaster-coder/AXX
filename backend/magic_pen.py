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
from backend.shape_registry import ShapeRegistry
from backend.provider_capabilities import CapabilityTable
from backend.spend_budget import SpendBudget
from backend.spatial_pipeline import COMPARE_CONTRACT, IDENTIFY_CONTRACT, blueprint_context, catalog_matches, parse_blueprint, repair_message
from backend.presentation_plan import PATCH_CONTRACT, PLAN_CONTRACT, PLAN_2D_CONTRACT, PlanError, apply_patch, normalize_model_focus, normalize_model_object_ids, normalize_strict_output, output_schema, parse_json, plain_text_diagram, validate_2d_plan, validate_plan, expand_components, learn_groups, plan_contract, patch_contract, check_plan, diagram_overlaps, prune_invalid_overlays
from backend.inference.provider_settings import anthropic_efforts
from backend.guide_plan import GUIDE_CONTRACT, evaluate, prompt_controls, resolve, snapshot as control_snapshot, validate_guide

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


def scene_png(data):
    """Decode a 3D renderer snapshot. Only a bounded PNG data URL crosses this boundary."""
    prefix = 'data:image/png;base64,'
    # The whole request must fit server.MAX_BODY (2 MiB); the renderer caps pixel ratio at 1.5.
    if not isinstance(data, str) or not data.startswith(prefix) or len(data) > 2_000_000:
        raise ValueError('La escena debe enviarse como imagen PNG.')
    try:
        with Image.open(io.BytesIO(base64.b64decode(data[len(prefix):], validate=True))) as im:
            if im.format != 'PNG' or im.width > 4096 or im.height > 4096:
                raise ValueError('formato o tamaño')
            return im.convert('RGBA')
    except (ValueError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('La escena debe ser una imagen PNG de hasta 4096 × 4096.') from exc


APTITUDE_CONTRACT = (
    'Responde SOLO con JSON, sin Markdown: {"schema_version":"1.0","kind":"presentation","title":"…","summary":"…","fidelity":"conceptual",'
    '"steps":[{"id":"s1","title":"Qué se observa","body":"…","narration":"…","basis":"observed"},{"id":"s2","title":"Relación","body":"…","narration":"…","basis":"inferred"}],'
    '"scene":{"fidelity":"conceptual","objects":[{"id":"o1","label":"…","shape":"box|sphere|cylinder","size":[x,y,z],"position":[x,y,z],"color":"#rrggbb"}]},'
    '"diagram":{"nodes":[{"id":"d1","label":"…","step_id":"s1","bounds":[0.1,0.1,0.3,0.2]},{"id":"d2","label":"…","step_id":"s2","bounds":[0.6,0.6,0.3,0.2]}],'
    '"edges":[{"from":"d1","to":"d2","label":"…"}]}}. Describe lo que ves en la imagen: un objeto 3D por figura con su color real y una explicación breve. '
    'No inventes datos que no se vean. Nunca incluyas HTML, código ni enlaces.'
)


class MagicPenService:
    def __init__(self, root, adapter=None, codex_provider=None):
        self.root = Path(root).resolve() / 'magic-pen'
        self.caps = CapabilityTable(self.root / 'provider-capabilities.json')  # verified / declared / unsupported, per connection and model
        self.budget = SpendBudget(self.root / 'spend-ledger.json')  # estimated spend of paid models; the owner sets the ceiling (5 USD by default)
        self.shapes = ShapeRegistry(self.root / 'shape-registry.json')  # learned components live in the user's data directory, never the repo
        self.root.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.uia = None  # Defaults to backend.actions.windows_automation; tests inject a fake.
        self.codex_provider = codex_provider
        self.spatial_verified = {}
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
            self._cancel_adapter(job['id'], job.get('query', {}).get('provider', {}).get('name'))
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

    def _row(self, name, model, protocol, protocol_3d, efforts, **extra):
        """One selectable model. 3D follows a real test when there is one; otherwise only the protocol's structured-output support."""
        level = self.caps.level(name, model, 'scene_3d')
        spatial = True if level == 'verificado' else False if level == 'no_soportado' else protocol_3d
        return {'name': name, 'model': model, 'protocol': protocol, 'spatial_3d': spatial, 'aptitude': self.caps.summary(name, model),
                'efforts': efforts, **extra}

    def capabilities(self):
        providers = getattr(self.adapter, 'config', {}).get('providers', [])
        vision = []
        for p in providers:
            if (p.get('enabled', True) and (p.get('free_confirmed') is True or p.get('billing_allowed') is True)
                    and 'vision' in p.get('capabilities', [])):
                self.caps.declare(p['name'], p['model'], 'vision', 'Declarada en la configuración de la conexión.')
                anthropic = p.get('protocol') == 'anthropic'
                model_lower = str(p.get('model', '')).lower()
                multimodal_3d = (anthropic or p.get('kind') in ('gemini', 'openai')
                                 or any(m in model_lower for m in ('gemini', 'gpt-4o', 'o1', 'claude')))
                vision.append(self._row(p['name'], p['model'], p.get('protocol', 'openai'), multimodal_3d,
                                        anthropic_efforts(p['model']) if anthropic else []))
        codex = []
        for row in getattr(self.codex_provider, 'model_catalog', []):
            if row.get('model') and isinstance(row.get('input_modalities'), list) and 'image' in row['input_modalities']:
                codex.append(self._row('@codex', row['model'], 'codex', True,
                                       [level.get('reasoningEffort') if isinstance(level, dict) else level for level in row.get('reasoning_efforts') or []]))
        if self.codex_provider and not codex:
            codex.append(self._row('@codex', 'gpt-6.1-sol', 'codex', True, [], status='not_verified'))
        return {'vision': vision, 'codex_vision': codex, 'ocr': False,
                'ocr_message': 'OCR no integrado; el proveedor visual puede leer texto si está configurado.',
                'export_directory': str(self.root / 'exports'), 'budget': self.budget.summary()}

    def verify_spatial(self, body):
        """Explicit aptitude test: one small fixed image, a reduced contract and one call. The verdict and its reason are stored per model."""
        if not isinstance(body, dict) or set(body) != {'provider', 'model', 'effort'}:
            raise ValueError('Indica proveedor, modelo y esfuerzo para verificar la conexión visual.')
        request = {'format': 'presentation', 'selection_mode': 'manual', **body}
        chosen = self._provider(request)
        image = Image.new('RGB', (96, 64), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 12, 42, 52), fill='#d33b36')
        draw.ellipse((56, 16, 84, 44), fill='#2878c8')
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        request_id = 'spatial-verify-' + uuid.uuid4().hex
        structured = chosen['name'] == '@codex' or chosen.get('protocol') == 'anthropic'  # only these routes accept a JSON schema
        schema = output_schema('presentation', strict=chosen['name'] == '@codex') if structured else None
        generation = {'max_tokens': 4096, **({'output_schema': schema} if schema else {})}
        effort = self._effective_effort(request, chosen)
        if effort:
            generation['effort'] = effort
        question = 'Explica la figura roja y el círculo azul de la imagen sintética: un objeto 3D por figura.'
        route_request = {'request_id': request_id, 'conversation_id': request_id, 'task': 'vision',
            'selection_mode': 'manual', 'allow_paid': False, 'deadline_ms': 70000,
            'provider_name': chosen['name'], 'model': chosen['model'], 'generation': generation,
            'messages': [{'role': 'system', 'content': compose('perception', contract=APTITUDE_CONTRACT)['text']},
                {'role': 'user', 'content': [{'type': 'text', 'text': question},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}}]}]}
        if chosen['name'] == '@codex':
            result = self.codex_provider.generate_spatial(route_request)
        else:
            result = self.adapter.route(route_request)
        message = result.get('message', {}) if isinstance(result, dict) else {}
        text = message.get('content') if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_RESPONSE_CHARS:
            err = result.get('error', {}).get('message') if isinstance(result, dict) else None
            raise ValueError(f'La prueba no recibió una respuesta de texto válida del modelo: {err}' if err else 'La prueba no recibió una respuesta de texto válida del modelo.')
        verdict = self._judge_aptitude(chosen, text, schema, question)
        if verdict['verdict'] == 'no_apto':
            raise ValueError('Modelo no apto para Magic Pen: ' + verdict['reason'])
        self._remember_spatial_provider(chosen, result, text_diagram=verdict['mode'] == 'texto', verdict=verdict)
        out = dict(self.spatial_verified[(chosen['name'], chosen['model'])])
        out.update(verdict=verdict['verdict'], reason=verdict['reason'], capabilities=self.caps.summary(chosen['name'], chosen['model']),
                   **({'usage': result['usage']} if isinstance(result.get('usage'), dict) and result['usage'] else {}))
        return out

    def _judge_aptitude(self, chosen, text, schema, question):
        """Score one answer from the fixed test. Never raises on a bad answer: a bad answer is data."""
        name, model = chosen['name'], chosen['model']
        plain = re.sub(r'[\u0300-\u036f]', '', __import__('unicodedata').normalize('NFD', text.lower()))
        sees = bool(re.search(r'roj|\bred\b', plain) and re.search(r'azul|blue', plain))
        parsed = plan = None
        reason, scene_ok, diagram_ok, mode = '', False, False, None
        try:
            parsed = parse_json(text)
            json_ok, json_evidence = True, 'Devolvió JSON válido.'
        except PlanError:
            json_ok, json_evidence = False, 'La respuesta no era JSON válido.'
        if parsed is not None:
            try:
                data = normalize_strict_output(parsed, schema) if chosen['name'] == '@codex' and schema else parsed
                data = normalize_model_focus(expand_components(normalize_model_object_ids(data), self.shapes))
                try:
                    plan = validate_plan(data)
                    objects = (plan.get('scene') or {}).get('objects', [])
                    # With two or more steps the renderer derives the 2D diagram itself, so a plan without nodes still serves 2D
                    scene_ok, diagram_ok, mode = len(objects) >= 2, bool(plan.get('diagram')) or len(plan['steps']) >= 2, 'json_3d'
                    if not scene_ok:
                        reason, mode = 'El plan no incluyó una escena 3D con las dos figuras.', 'json_2d'
                    colors = [tuple(int(o['color'][i:i + 2], 16) for i in (1, 3, 5)) for o in objects]
                    sees = sees or (any(r > 150 and g < 110 and b < 110 for r, g, b in colors) and any(b > 150 and r < 120 for r, g, b in colors))
                except PlanError as exc:
                    reason = str(exc)
                    plan, mode, diagram_ok = validate_2d_plan(data), 'json_2d', True  # the explanation and diagram survive without a scene
            except PlanError as exc:
                reason = reason or str(exc)
        if plan is None:
            try:
                plain_text_diagram(text, question)
                diagram_ok, mode = True, 'texto'
            except PlanError as exc:
                reason = reason or str(exc)
        explained = all(len(step['body']) >= 20 for step in plan['steps']) if plan else len(text.strip()) >= 40
        verdict = 'apto_3d' if scene_ok and sees else 'apto_2d' if diagram_ok and sees else 'no_apto'
        if not sees:
            reason = 'No describió la figura roja ni el círculo azul: no parece ver la imagen.'
        elif verdict == 'apto_2d':
            reason = 'Sirve para diagramas 2D y texto; no generó una escena 3D válida (' + (reason or 'sin escena') + ').'
        elif verdict == 'no_apto':
            reason = reason or 'La respuesta no se pudo convertir en un diagrama ni en un plan válido.'
        evidence = 'Prueba de aptitud con imagen sintética.'
        for capability, ok, note in (('vision', sees, 'Describió las dos figuras.' if sees else 'No describió las figuras.'),
                                     ('json_estricto', json_ok, json_evidence), ('scene_3d', scene_ok and sees, 'Plan 3D validado en la prueba básica (dos figuras); no garantiza fidelidad con objetos complejos.' if scene_ok else (reason or 'Sin escena 3D válida.')),
                                     ('diagram_2d', diagram_ok and sees, 'Diagrama válido (' + str(mode) + ').' if diagram_ok else 'Sin diagrama válido.'),
                                     ('explicacion', explained and sees, 'Pasos con contenido.' if explained else 'Explicación vacía o demasiado corta.')):
            self.caps.verify(name, model, capability, ok, f'{evidence} {note}', mode=mode if capability in ('scene_3d', 'diagram_2d') else None)
        return {'verdict': verdict, 'reason': reason[:300], 'mode': mode}

    def _remember_spatial_provider(self, chosen, result, *, text_diagram=False, verdict=None):
        route = result.get('route') if isinstance(result, dict) else None
        if (not isinstance(route, dict) or route.get('provider_name', route.get('provider')) != chosen['name']
                or route.get('model') != chosen['model']):
            raise ValueError('El proveedor o modelo real no coincide con la selección; no se marcará como verificado.')
        checked = {'provider': chosen['name'], 'model': chosen['model'], 'checked_at': time.time(),
                   'state': 'ready', 'structured_output': bool(chosen.get('spatial_3d')), 'image_input': True,
                   'text_diagram': bool(text_diagram), **({'verdict': verdict['verdict']} if verdict else {})}
        self.spatial_verified[(chosen['name'], chosen['model'])] = checked
        return checked

    @staticmethod
    def _effective_effort(request, provider):
        effort = request.get('effort', 'auto')
        if effort != 'auto':
            return effort
        efforts = provider.get('efforts', [])
        if not isinstance(efforts, list):
            return None
        question = request.get('question', '').casefold()
        if request.get('base_query_id'):
            target = 'high' if len(question) > 180 or re.search(r'\b(analiza|compara|explica|detalla|razona|causa|por qué|cómo funciona|paso a paso)\b', question) else 'low'
        else:
            target = 'medium'
        return target if target in efforts else None

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
        if kind not in ('original', 'annotated', 'scene'):
            raise ValueError('Elige original, anotado o escena.')
        scene = scene_png(body.get('image')) if kind == 'scene' else None
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
        im = scene or self.original(d).convert('RGBA')
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
        if not isinstance(body, dict) or set(body) - {'id', 'revision', 'question', 'provider', 'model', 'selection_mode', 'request_id',
                                                      'format', 'base_query_id', 'effort', 'selected_object_id', 'conversation_id', 'compare_scene'}:
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
        request = {'id': body['id'], 'revision': body['revision'], 'question': question,
                   'provider': provider, 'model': model, 'selection_mode': mode, 'request_id': request_id}
        # Optional keys are omitted for text answers so earlier request signatures stay identical.
        if body.get('format', 'text') not in ('text', 'presentation', 'guide'):
            raise ValueError('Formato de respuesta inválido.')
        if body.get('effort', 'auto') not in ('auto', 'low', 'medium', 'high', 'xhigh', 'max'):
            raise ValueError('Nivel de esfuerzo inválido.')
        if body.get('format', 'text') != 'text':
            request['format'] = body['format']
            request['effort'] = body.get('effort', 'auto')
            if body['format']=='presentation' and (not provider or not model or mode != 'manual'):
                raise ValueError('La presentación requiere un proveedor y modelo elegidos explícitamente.')
        if 'base_query_id' in body:
            base = body['base_query_id']
            if 'format' not in request or not isinstance(base, str) or not re.fullmatch('[a-f0-9]{32}', base):
                raise ValueError('base_query_id requiere formato presentation o guide y un identificador válido.')
            request['base_query_id'] = base
        if 'selected_object_id' in body:
            selected = body['selected_object_id']
            if not request.get('base_query_id') or not isinstance(selected, str) or not re.fullmatch(r'o[0-9]{1,3}', selected):
                raise ValueError('La pieza seleccionada requiere una presentación base e identificador válido.')
            request['selected_object_id'] = selected
        if 'compare_scene' in body:
            if not request.get('base_query_id') or request.get('format') != 'presentation':
                raise ValueError('Comparar el modelo con la imagen requiere una presentación 3D base.')
            scene_png(body['compare_scene'])  # bounded PNG or a clear error; the image itself is used only for this one call
            request['compare_scene'] = body['compare_scene']
        if 'conversation_id' in body:
            conversation = body['conversation_id']
            if not isinstance(conversation, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', conversation):
                raise ValueError('Referencia de conversación inválida.')
            request['conversation_id'] = conversation
        return request

    def _provider(self, request):
        if request.get('format') == 'presentation':
            if request['selection_mode'] != 'manual':
                raise ValueError('La presentación no admite selección automática ni cambio de proveedor.')
            if request['provider'] == '@codex':
                match = next((p for p in self.capabilities()['codex_vision'] if p['model'] == request['model']), None)
                if not match and request['model'] == 'gpt-6.1-sol' and self.codex_provider and request['effort'] == 'auto':
                    match = {'name': '@codex', 'model': request['model'], 'protocol': 'codex', 'spatial_3d': True, 'efforts': [], 'status': 'not_verified'}
                if not match:
                    raise ValueError('El catálogo local no confirma visión para ese modelo Codex. Compruébalo desde Axx Connect.')
                if request['effort'] != 'auto' and request['effort'] not in match['efforts']:
                    raise ValueError('El nivel de esfuerzo no está admitido por el modelo Codex seleccionado.')
                return dict(match)
            chosen = next((p for p in self.capabilities()['vision'] if p['name'] == request['provider']), None)
            if not chosen or chosen['model'] != request['model']:
                raise ValueError('Selecciona una conexión visual autorizada y su modelo exacto.')
            if request['effort'] != 'auto' and request['effort'] not in chosen['efforts']:
                raise ValueError('El nivel de esfuerzo no está admitido por el modelo Claude seleccionado.')
            return dict(chosen)
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
            base_plan = None
            if 'base_query_id' in request:
                base = next((item for item in d.get('queries', []) if item['id'] == request['base_query_id']), None)
                if not base or base.get('revision') != d['revision'] or not isinstance(base.get('presentation'), dict):
                    raise ValueError('STALE_PRESENTATION: la presentación base no pertenece a esta selección.')
                base_plan = base['presentation']
                if request.get('selected_object_id') and not any(o['id'] == request['selected_object_id'] for o in base_plan.get('scene', {}).get('objects', [])):
                    raise ValueError('La pieza seleccionada no pertenece a esta presentación.')
            q = {'id': request['request_id'], 'source_id': d['id'], 'revision': d['revision'],
                 'selection': copy.deepcopy(d['selection']), 'question': request['question'], 'state': 'running',
                 'created_at': time.time(), 'provider': {'name': request['provider'], 'model': request['model']},
                 'selection_mode': request['selection_mode'], 'source_sha256': d['source']['sha256'],
                 **{k: request[k] for k in ('format', 'base_query_id', 'selected_object_id', 'conversation_id') if k in request},
                 'context': {'session_id': d['id'], 'revision': d['revision'], 'capture_sha256': d['source']['sha256']}}
            try:
                q['provider'] = self._provider(request)
                request['effective_effort'] = self._effective_effort(request, q['provider'])
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
                            'request': request, 'query': copy.deepcopy(q), 'base_plan': base_plan, 'cancel': threading.Event(),
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

    def save_view(self, body):
        if not isinstance(body, dict) or set(body) != {'id', 'query_id', 'view'}:
            raise ValueError('Estado de vista inválido.')
        with self.lock:
            d = self.get(body['id'])
            q = next((q for q in d.get('queries', []) if q['id'] == body['query_id']), None)
            if not q or q.get('state') != 'completed' or not q.get('presentation') or q['revision'] != d['revision']:
                raise ValueError('La vista requiere una presentación terminada de la revisión actual.')
            value = body['view']
            if not isinstance(value, dict) or set(value) != {'camera', 'step_id', 'selected', 'hidden', 'separated', 'exploded', 'isolated', 'overview'}:
                raise ValueError('Campos de vista inválidos.')
            objects = {o['id'] for o in q['presentation'].get('scene', {}).get('objects', [])}
            if (not isinstance(value['step_id'], str) or value['step_id'] not in {s['id'] for s in q['presentation']['steps']}
                    or value['selected'] is not None and (not isinstance(value['selected'], str) or value['selected'] not in objects)
                    or any(type(value[key]) is not bool for key in ('exploded', 'isolated', 'overview'))):
                raise ValueError('La vista referencia pasos o piezas desconocidos.')
            for key in ('hidden', 'separated'):
                ids = value[key]
                if not isinstance(ids, list) or len(ids) > 24 or any(not isinstance(i, str) or i not in objects for i in ids) or len(set(ids)) != len(ids):
                    raise ValueError('Lista de piezas de vista inválida.')
            camera = value['camera']
            if camera is not None:
                if not isinstance(camera, dict) or set(camera) != {'target', 'theta', 'phi', 'distance'} or not isinstance(camera['target'], list) or len(camera['target']) != 3:
                    raise ValueError('Cámara inválida.')
                if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000 for v in [*camera['target'], camera['theta'], camera['phi'], camera['distance']]) or not .05 <= camera['distance'] <= 200 or not 0 < camera['phi'] < math.pi:
                    raise ValueError('La cámara excede los límites de la escena.')
            q['view_state'] = copy.deepcopy(value)
            write_json(self.directory(d['id']) / 'document.json', d)
            return {'id': d['id'], 'query_id': q['id'], 'view_state': copy.deepcopy(value)}

    def _uia(self):
        if self.uia is None:
            from backend.actions import windows_automation
            self.uia = windows_automation
        return self.uia

    def _guide_window(self, d, cancelled):
        """Top-most application window under the selection centre, observed through the existing UIA worker."""
        uia, b, source = self._uia(), d['selection']['bounds'], d['source']
        x, y = (b[0] + b[2]) / 2 + source['x'], (b[1] + b[3]) / 2 + source['y']
        own = {os.getpid(), os.getppid()}
        for w in uia.list_windows():  # EnumWindows order is top-most first.
            try:
                if w['pid'] in own or uia.process_name(w['pid']).lower() in ('axx.exe', 'axx-backend.exe'):
                    continue
                geometry = uia.observe_geometry(w['window_id'])
            except (ValueError, OSError):
                continue
            r = geometry['window_bounds']
            if not geometry['minimized'] and r['x'] <= x < r['x'] + r['width'] and r['y'] <= y < r['y'] + r['height']:
                observed = uia.inspect_controls(w['window_id'], w['pid'], cancelled=cancelled)
                return ({'window_id': w['window_id'], 'pid': w['pid'], 'title': observed.get('window_title') or w['title'],
                         'process_started': observed.get('process_started') or uia.process_started(w['pid'])}, observed)
        raise ValueError('No encontré una ventana de aplicación bajo la selección para guiarte.')

    def _guide_record(self, source_id, query_id, step_id, record):
        with self.lock:
            d = self.get(source_id)
            q = next(q for q in d['queries'] if q['id'] == query_id)
            progress = q.setdefault('guide_progress', {})
            if progress.get(step_id, {}).get('state') != 'VERIFIED':  # A verified step is never downgraded.
                progress[step_id] = record
                write_json(self.directory(source_id) / 'document.json', d)
            return copy.deepcopy(progress[step_id])

    def guide_check(self, body):
        """Target or verify one guide step against a fresh observation of the same window instance."""
        if not isinstance(body, dict) or set(body) != {'id', 'query_id', 'step_id', 'phase'} or body['phase'] not in ('target', 'verify'):
            raise ValueError('Comprobación de guía inválida.')
        q = self.query({'id': body['id'], 'query_id': body['query_id']})
        guide, window = q.get('guide'), q.get('guide_window')
        if q['state'] != 'completed' or not guide or not window:
            raise ValueError('La consulta no contiene una guía.')
        step = next((s for s in guide['steps'] if s['id'] == body['step_id']), None)
        if not step:
            raise ValueError('Paso de guía desconocido.')
        previous = q.get('guide_progress', {}).get(step['id'], {})
        result = {'step_id': step['id'], 'bounds': None, 'monitors': None, 'window_title': window['title']}
        if previous.get('state') == 'VERIFIED':
            return {**result, 'state': 'VERIFIED', 'record': previous}
        if body['phase'] == 'verify' and previous.get('state') not in ('WAITING_USER', 'UNKNOWN'):
            raise ValueError('Señala el paso antes de comprobarlo.')
        uia = self._uia()
        try:
            if uia.process_started(window['pid']) != window['process_started']:
                raise ValueError('process restarted')
            observed = uia.inspect_controls(window['window_id'], window['pid'])
        except (ValueError, OSError):  # Closed, restarted or unobservable window: never guess.
            record = self._guide_record(q['source_id'], q['id'], step['id'], {**previous, 'state': 'STALE', 'at': time.time()})
            return {**result, 'state': record['state'], 'record': record}
        status, control = resolve(observed, step['target'])
        post = step['postcondition']
        post_status, post_control = resolve(observed, post.get('target', step['target']))
        title = observed.get('window_title', '')
        result.update(window_title=title, monitors=observed['observation']['monitors'], target_status=status,
                      bounds=control['bounds'] if control else None)
        if body['phase'] == 'target':
            if status != 'found':
                state, baseline = ('AMBIGUOUS' if status == 'ambiguous' else 'TARGET_NOT_FOUND'), None
            else:
                # Re-pointing keeps the first baseline: the user's change may already have happened.
                baseline = previous.get('baseline') or (control_snapshot(post_control) if post_control else None)
                already = post['kind'] != 'value_changed' and evaluate(post, post_status, post_control, baseline, title) == 'VERIFIED'
                state = 'VERIFIED' if already else 'WAITING_USER'
        else:
            baseline = previous.get('baseline')
            state = evaluate(post, post_status, post_control, baseline, title)
            state = 'WAITING_USER' if state == 'WAITING' else state
        record = self._guide_record(q['source_id'], q['id'], step['id'], {
            'state': state, 'baseline': baseline, 'observation_id': observed['observation']['observation_id'], 'at': time.time()})
        return {**result, 'state': record['state'], 'record': record}

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

    def _cancel_adapter(self, query_id, provider_name=None):
        target = self.codex_provider if provider_name == '@codex' else self.adapter
        if target and hasattr(target, 'cancel'):
            try:
                target.cancel('pen-' + query_id)
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
        self._cancel_adapter(q['id'], q.get('provider', {}).get('name'))
        return result

    def _watch_cancellation(self, job):
        # cancel() can arrive before InferenceAdapter registers active_requests.
        # Keep signalling until route exits, rather than treating the first False
        # response as evidence that cancellation finished.
        while not job['route_done'].wait(.02):
            if job['cancel'].is_set():
                self._cancel_adapter(job['id'], job.get('query', {}).get('provider', {}).get('name'))

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

    def _connection(self, chosen):
        """The saved connection behind a chosen row, merged with it: what the budget needs (prices, kind, free flags)."""
        saved = next((p for p in getattr(self.adapter, 'config', {}).get('providers', []) if p.get('name') == chosen.get('name')), {})
        return {**saved, **{k: chosen[k] for k in ('name', 'model', 'protocol') if k in chosen}}

    def _call(self, job, chosen, route_request, presentation, purpose):
        """One model call: budget check, route, readable failure, budget record. Raises ValueError with the reason."""
        connection = self._connection(chosen)
        self.budget.check(connection)
        if presentation and chosen['name'] == '@codex':
            if not self.codex_provider:
                raise ValueError('Axx Connect con Codex no está disponible.')
            result = self.codex_provider.generate_spatial(route_request, cancel_event=job['cancel'])
        else:
            result = self.adapter.route(route_request,
                **({'cancel_event': job['cancel']} if getattr(self.adapter, 'supports_cancel_event', False) is True else {}))
        if not isinstance(result, dict) or result.get('ok') is not True:
            error = result.get('error', {}) if isinstance(result, dict) else {}
            err_msg = str(error.get('message', 'El proveedor no respondió.'))
            if re.search(r'\b429\b', err_msg) or re.search(r'(?i)\b(l[ií]mite|rate[ _]limit|quota|agotad[oa]|5 horas|too many requests)\b', err_msg):
                alts = []
                try:
                    for p in self.capabilities().get('vision', []):
                        if p.get('name') != chosen.get('name') or p.get('model') != chosen.get('model'):
                            alts.append(f"{p.get('name')}:{p.get('model')}")
                except Exception:
                    pass
                if alts:
                    err_msg += f" Sugerencia: cambia en 'Proveedor y calidad' a {', '.join(alts[:3])} para continuar sin agotar tu cuota."
            raise ValueError(err_msg[:2000])
        job['cost_usd'] = job.get('cost_usd', 0.0) + self.budget.record(connection, result.get('usage'), purpose)  # estimated cost of this query, shown in its card
        return result

    def _identify(self, job, chosen, jpeg, q):
        """Cheap first pass: who/what is this and which parts does it have. Never blocks the main call; any failure just means "no blueprint"."""
        route_request = {'request_id': 'pen-' + q['id'] + '-id', 'conversation_id': 'pen-' + q['id'], 'task': 'vision', 'selection_mode': 'manual', 'allow_paid': False,
                         'deadline_ms': 60000, 'provider_name': chosen['name'], 'model': chosen['model'], 'generation': {'max_tokens': 1400},
                         'messages': [{'role': 'system', 'content': IDENTIFY_CONTRACT},
                                      {'role': 'user', 'content': [{'type': 'text', 'text': 'Identifica el objeto de la imagen y sus partes.'},
                                                                   {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode()}}]}]}
        try:
            result = self._call(job, chosen, route_request, False, 'identify')
            text = (result.get('message') or {}).get('content')
            return (parse_blueprint(text), result.get('usage')) if isinstance(text, str) else (None, result.get('usage'))
        except (ValueError, PlanError):
            return None, None

    @staticmethod
    def _sum_usage(*usages):
        total = {}
        for usage in usages:
            for key in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'):
                if isinstance(usage, dict) and isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool):
                    total[key] = total.get(key, 0) + usage[key]
        return total

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
            chosen = q['provider']
            presentation, guide, base_plan = request.get('format') == 'presentation', request.get('format') == 'guide', job.get('base_plan')
            event_support = presentation or getattr(self.adapter, 'supports_cancel_event', False) is True
            if not event_support:
                watcher = threading.Thread(target=self._watch_cancellation, args=(job,), name='axx-pen-cancel', daemon=True)
                watcher.start()
            explicit_3d = bool(presentation and chosen.get('spatial_3d') and not base_plan
                               and re.search(r'(?i)\b(?:3d|tridimensional|maqueta)\b', q['question']))
            compare_jpeg = None
            if base_plan and request.get('compare_scene'):
                rendered = scene_png(request['compare_scene'])
                flat = Image.new('RGB', rendered.size, (232, 234, 238))
                flat.paste(rendered, mask=rendered.split()[3])
                flat.thumbnail((1024, 1024))
                out = io.BytesIO()
                flat.save(out, format='JPEG', quality=88)
                compare_jpeg = out.getvalue()
            contract = 'Responde en español sobre la imagen seleccionada.' + (
                ' ' + GUIDE_CONTRACT if guide else ' ' + (patch_contract(self.shapes) if base_plan else plan_contract(self.shapes) if chosen.get('spatial_3d') else PLAN_2D_CONTRACT) if presentation else '')
            if compare_jpeg:
                contract += ' ' + COMPARE_CONTRACT
            if explicit_3d:
                contract += (' SOLICITUD 3D EXPLÍCITA: analiza primero la imagen y modela el objeto concreto que aparece en ella, nunca un ejemplo genérico ni otro objeto; '
                             'genera 4 a 7 pasos técnicos (s1 «Qué se observa», último «Proporciones y límites») y hasta 32 piezas, una por componente visible y detalle relevante, con scene propia y sin asset; '
                             'respeta las proporciones medidas sobre la imagen. '
                             'Antes de modelar una pieza, busca en el catálogo de componentes: si existe una equivalente (tornillo, engranaje, rodamiento, rotor, válvula, placa…) DEBES usarla con "component" y no reconstruirla con primitivas; '
                             'toda pieza que no esté en el catálogo y se componga de 2 o más primitivas DEBE llevar "group" con un nombre técnico de al menos dos palabras para que Axx la reutilice. '
                             'Omite diagram y overlays si pueden hacer que el JSON 3D quede incompleto. '
                             'Toda escena debe conservar unidades relativas plausibles y fidelidad conceptual. '
                             'Nunca reduzcas una pantalla 2D plana a un falso modelo físico.'
                             ' El JSON DEBE incluir "scene" con todas las piezas: una respuesta sin escena se rechaza.')
            prompt = q['question'] + ('\n\nPresentación actual:\n' + json.dumps(base_plan, ensure_ascii=False) if base_plan else '')
            if compare_jpeg:
                prompt += '\n\nImagen 1: el objeto original. Imagen 2: el render actual del modelo 3D.'
            blueprint, identify_usage = None, None
            if explicit_3d and chosen['name'] != '@codex' and not job['cancel'].is_set():
                blueprint, identify_usage = self._identify(job, chosen, buf.getvalue(), q)
                if blueprint:  # it goes after the stable system prefix, so prompt caching of the contract still works
                    prompt += '\n\n' + blueprint_context(blueprint, catalog_matches(self.shapes, blueprint))
            if request.get('selected_object_id'):
                selected = next(o for o in base_plan['scene']['objects'] if o['id'] == request['selected_object_id'])
                prompt += '\n\nPieza seleccionada en esta misma sesión (datos):\n' + json.dumps(selected, ensure_ascii=False)
            if guide:
                window, observed = self._guide_window(d, job['cancel'])
                prompt += '\n\nControles de la ventana:\n' + prompt_controls(observed)
                if job['cancel'].is_set():
                    return
            # A detailed first 3D plan (up to 32 parts + technical steps) can need 8-10k tokens: the ceiling is high because the owner asked for detail,
            # the real spend is capped by the budget. Patches and 2D stay small.
            generation = {'max_tokens': 12288 if presentation and chosen.get('spatial_3d') and not base_plan else 4096 if compare_jpeg else 2048 if presentation or guide else 1024}
            if presentation and chosen.get('spatial_3d') and (chosen['name'] == '@codex' or chosen.get('protocol') == 'anthropic'):
                # Anthropic rejects the patch schema as "too complex" (live HTTP 400); its answer is bounded by PATCH_CONTRACT and apply_patch.
                if not (base_plan and chosen.get('protocol') == 'anthropic'):
                    generation['output_schema'] = output_schema('patch' if base_plan else 'presentation', strict=chosen['name'] == '@codex', require_scene=explicit_3d)
                if request.get('effective_effort'):
                    generation['effort'] = request['effective_effort']
            images = [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()}}]
            if compare_jpeg:
                images.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(compare_jpeg).decode()}})
            deadline_ms = 150000 if presentation and chosen['name'] == '@codex' else 240000 if presentation and chosen.get('spatial_3d') else 70000
            route_request = {'request_id': 'pen-' + q['id'], 'conversation_id': 'pen-' + q['id'],
                'task': 'vision', 'selection_mode': request['selection_mode'], 'allow_paid': False,
                'deadline_ms': deadline_ms,
                'provider_name': chosen['name'], 'model': chosen['model'], 'generation': generation,
                'messages': [{'role': 'system', 'content': compose('perception', contract=contract)['text']},
                    {'role': 'user', 'content': [{'type': 'text', 'text': prompt}, *images]}]}
            attempts, calls_usage = 0, [identify_usage]
            while True:
                result = self._call(job, chosen, route_request, presentation, 'plan' if attempts == 0 else 'repair')
                message = result.get('message', {})
                text = message.get('content') if isinstance(message, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_RESPONSE_CHARS:
                    raise ValueError('El proveedor no devolvió texto válido dentro del límite.')
                calls_usage.append(result.get('usage'))
                changes = {'state': 'completed', 'response': text, 'route': result.get('route'), 'finished_at': time.time()}
                total_usage = self._sum_usage(*calls_usage)
                if total_usage:
                    changes['usage'] = total_usage  # tokens in/out and cache read/write across every call of this query, shown in the card
                if job.get('cost_usd'):
                    changes['cost_usd'] = round(job['cost_usd'], 4)
                if blueprint:
                    changes['blueprint'] = blueprint
                if attempts:
                    changes['repairs'] = attempts
                if not presentation:
                    break
                try:
                    changes['finish_reason'] = result.get('finish_reason')  # real provider stop reason, kept for diagnosis
                    if result.get('finish_reason') == 'length':
                        raise PlanError('El proveedor agotó los tokens antes de completar el plan visual, también tras un reintento más compacto. Prueba un objeto más concreto o un modelo con más salida.')
                    local_prose = False
                    try:
                        parsed = parse_json(text)
                    except PlanError:
                        if chosen.get('spatial_3d') or base_plan:
                            raise  # Never invent or silently downgrade a requested 3D scene/patch.
                        changes['presentation'] = plain_text_diagram(text, q['question'])
                        changes['visual_notice'] = ('Diagrama 2D construido localmente a partir de texto: el proveedor no devolvió JSON '
                                                    'estructurado. No es una localización verificada de objetos de la captura.')
                        local_prose = True
                    if not local_prose:
                        if chosen['name'] == '@codex':
                            parsed = normalize_strict_output(parsed, generation['output_schema'])
                        fidelity_missing = isinstance(parsed, dict) and isinstance(parsed.get('scene'), dict) and 'fidelity' not in parsed['scene']
                        parsed = normalize_model_object_ids(parsed)
                        parsed = expand_components(parsed, self.shapes)  # catalog references become real parts before validation
                        parsed, dropped_overlays = prune_invalid_overlays(parsed) if not base_plan else (parsed, [])
                        try:
                            drew_overlaps = bool(parsed.get('diagram')) and diagram_overlaps(parsed['diagram']['nodes'])
                        except (KeyError, TypeError, IndexError):
                            drew_overlaps = False
                        parsed = normalize_model_focus(parsed)
                        if base_plan:
                            changes['presentation'], changes['answer'] = apply_patch(base_plan, parsed, min_steps=2 if chosen.get('spatial_3d') else 1, registry=self.shapes)
                            if not chosen.get('spatial_3d'):
                                changes['presentation'] = validate_2d_plan(changes['presentation'])
                        else:
                            changes['presentation'] = validate_plan(parsed) if chosen.get('spatial_3d') else validate_2d_plan(parsed)
                            if explicit_3d and not changes['presentation'].get('scene'):
                                raise PlanError('la petición era un modelo 3D y la respuesta no incluye "scene": falta la escena 3D con las piezas del objeto.')
                        if chosen.get('spatial_3d'):
                            learn_groups(changes['presentation'], self.shapes)  # only validated pieces are ever stored
                        notes = check_plan(changes['presentation']) if chosen.get('spatial_3d') else []  # local checks: they warn, never fix
                        notes += dropped_overlays
                        if fidelity_missing:
                            notes.append('El modelo no indicó la fidelidad de la escena; se usó la del plan o «conceptual».')
                        if drew_overlaps and not base_plan:
                            notes.append('El modelo dibujó nodos solapados; Axx reorganizó el diagrama automáticamente.')
                        if notes:
                            changes['warnings'] = notes
                        self._remember_spatial_provider(chosen, result)
                    break
                except PlanError as exc:
                    # One automatic repair: the model sees its own answer and the exact validation error. It never repeats a request that failed upstream.
                    if attempts >= 1 or not chosen.get('spatial_3d') or job['cancel'].is_set():
                        for key in ('presentation', 'answer', 'warnings', 'visual_notice'):  # nothing half-validated is ever kept
                            changes.pop(key, None)
                        changes.update(state='failed', error='El modelo no devolvió una presentación válida: ' + str(exc))
                        break
                    attempts += 1
                    fix = repair_message(exc, length=result.get('finish_reason') == 'length')
                    if chosen['name'] == '@codex':  # that path takes exactly one system and one user turn with one image
                        retry_messages = [route_request['messages'][0], {'role': 'user', 'content': [{'type': 'text', 'text': prompt + '\n\n' + fix + '\nRespuesta anterior inválida:\n' + text[:6000]}, images[0]]}]
                    else:
                        retry_messages = [*route_request['messages'], {'role': 'assistant', 'content': text}, {'role': 'user', 'content': fix}]
                    route_request = {**route_request, 'request_id': f"pen-{q['id']}-r{attempts}", 'messages': retry_messages}
                    continue
                except ValueError as exc:
                    changes.update(state='failed', error=str(exc))
                    break
            if guide:
                try:
                    changes.update(guide=validate_guide(parse_json(text)), guide_window=window, guide_progress={})
                except PlanError as exc:
                    changes.update(state='failed', error='El modelo no devolvió una guía válida: ' + str(exc))
            with self.lock:
                if not job['cancel'].is_set() and not self.closing:
                    self._replace_query(d['id'], q['id'], changes)
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
