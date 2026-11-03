"""PresentationPlan v1: the declarative contract between a vision model and the Magic Pen canvas.

The model is untrusted. Its text is parsed as JSON, checked against this closed
contract and only then rendered by allowlisted frontend components using
textContent. Nothing in a plan is executed or inserted as HTML. An optional
scene is a list of allowlisted primitives; it is always a conceptual
representation, never a simulation or exact geometry.
"""
import copy
import json
import math
import re
from backend.spatial_assets import engine_asset

SCHEMA_VERSION = '1.0'
MAX_STEPS = 8
MAX_OPS = 8
MAX_OBJECTS = 24
MAX_ARROWS = 12
FIDELITY = ('illustrative', 'conceptual', 'technical')
SCENE_FIDELITY = ('illustrative', 'conceptual')
BASIS = ('observed', 'documented', 'inferred', 'assumed')
SHAPES = ('box', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'piston', 'connecting_rod', 'crankshaft', 'engine_cylinder')
STEP_ID = re.compile(r's[0-9]{1,3}')
OBJECT_ID = re.compile(r'o[0-9]{1,3}')
COLOR = re.compile(r'#[0-9a-fA-F]{6}')
LIMITS = {'title': 80, 'body': 400, 'narration': 400}
OBJECT_FIELDS = ('label', 'shape', 'size', 'position', 'color', 'rotation', 'explode')

PLAN_CONTRACT = (
    'Responde SOLO con un objeto JSON, sin texto adicional ni bloques de código, con esta forma exacta: '
    '{"schema_version":"1.0","kind":"presentation","title":"…","summary":"una frase de máximo 24 palabras",'
    '"fidelity":"illustrative|conceptual|technical","steps":[{"id":"s1","title":"…","body":"…","narration":"…",'
    '"basis":"observed|documented|inferred|assumed"}]}. '
    'Usa entre 2 y 8 pasos que formen una secuencia o flujo explicativo. '
    'basis="observed" solo para lo que se ve en la imagen; "inferred" para deducciones; "assumed" para conocimiento general. '
    'No inventes medidas, pines, especificaciones ni datos no visibles; si faltan, dilo y usa fidelity="conceptual". '
    'Si el contenido es un ejemplo didáctico y no un dato de la imagen, márcalo con basis="assumed". '
    'Solo si una vista 3D ayuda de verdad añade scene, usando shapes permitidas y valores acotados. '
    'Para un mecanismo monocilíndrico puedes pedir asset={"kind":"single_cylinder_engine","scale":1}; es una asamblea conceptual, no CAD. '
    'Añade diagram con nodos d1..d16, bounds=[x,y,ancho,alto] normalizados y edges que refieran nodos existentes. '
    'Añade overlays solo sobre la selección: hasta 16 flechas, cajas, etiquetas o tarjetas vinculadas a step_id; photo=true muestra el recorte seleccionado. '
    'En cada paso usa focus con objetos existentes que explica. Para matemáticas, texto, software o pantallas omite scene: '
    'no uses 3D solo por ser vistoso. La escena es conceptual: no inventes geometría interna, dimensiones exactas ni conexiones. '
    'Nunca incluyas HTML, código ni enlaces.'
    ' Para un motor didáctico de un cilindro puedes añadir "asset":{"kind":"single_cylinder_engine","scale":1} '
    'sin scene; Axx construye localmente cilindro o1, pistón o2, biela o3 y cigüeñal o4. Son piezas conceptuales, sin simulación física. '
    'Puedes añadir "diagram":{"nodes":[{"id":"d1","label":"…","step_id":"s1","bounds":[x,y,ancho,alto]}],'
    '"edges":[{"from":"d1","to":"d2","label":"…"}]} con 2 a 16 nodos y hasta 24 enlaces. '
    'Las coordenadas están normalizadas entre 0 y 1. Para enseñar sobre la selección usa "overlays":'
    '[{"id":"a1","kind":"arrow|box|label|card","step_id":"s1","start":[x,y],"end":[x,y],"text":"…","photo":false}]. '
    'Hasta 16 anotaciones; photo solo puede ser true para una tarjeta que muestra la captura seleccionada. '
    'Cada anotación pertenece a un paso y desaparece al terminar o pausar la narración.'
)

PATCH_CONTRACT = (
    'Tienes la presentación actual en JSON. Responde a la pregunta del usuario modificándola SOLO con un objeto JSON '
    'sin texto adicional: {"schema_version":"1.0","kind":"patch","answer":"respuesta breve a la pregunta",'
    '"ops":[{"op":"step.update","step_id":"s2","title":"…","body":"…","narration":"…","basis":"…","focus":["o1"]},'
    '{"op":"step.insert_after","step_id":"s2","step":{"id":"s9","title":"…","body":"…","narration":"…","basis":"…"}},'
    '{"op":"step.remove","step_id":"s3"},'
    '{"op":"object.update","object_id":"o1","label":"…","color":"#rrggbb","position":[x,y,z],"size":[x,y,z]}]}. '
    'Incluye solo las operaciones necesarias (0 a 8); en las actualizaciones omite los campos que no cambian. '
    'object.update solo existe si la presentación tiene scene. '
    'Conserva lo que no cambia. Nunca incluyas HTML, código ni enlaces.'
)


def _strict_schema(schema):
    schema = copy.deepcopy(schema)

    def visit(node):
        if not isinstance(node, dict):
            return
        if node.get('type') == 'object':
            properties = node.get('properties', {})
            required = set(node.get('required', ()))
            for name, child in list(properties.items()):
                visit(child)
                if name not in required:
                    properties[name] = {'anyOf': [child, {'type': 'null'}]}
            node['required'] = list(properties)
        elif node.get('type') == 'array':
            visit(node.get('items'))
        for branch in node.get('anyOf', ()):
            visit(branch)

    visit(schema)
    return schema


def normalize_strict_output(value, schema):
    """Remove only null placeholders used for optional fields in a strict provider schema."""
    if isinstance(value, dict) and isinstance(schema, dict):
        properties = schema.get('properties', {})
        result = {}
        for name, item in value.items():
            child = properties.get(name)
            if not isinstance(child, dict):
                result[name] = item
                continue
            branches = child.get('anyOf', ())
            nullable = next((branch for branch in branches if branch.get('type') == 'null'), None)
            if item is None and nullable is not None:
                continue
            if nullable is not None:
                child = next(branch for branch in branches if branch is not nullable)
            result[name] = normalize_strict_output(item, child)
        return result
    if isinstance(value, list) and isinstance(schema, dict):
        return [normalize_strict_output(item, schema.get('items', {})) for item in value]
    return value


def output_schema(kind='presentation', *, strict=False):
    """Small strict JSON Schema for provider-constrained output; Python remains authoritative."""
    text = {'type': 'string'}
    vector = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}
    step = {'type': 'object', 'additionalProperties': False,
            'properties': {'id': text, 'title': text, 'body': text, 'narration': text,
                           'basis': {'type': 'string', 'enum': list(BASIS)},
                           'focus': {'type': 'array', 'items': text}},
            'required': ['id', 'title', 'body', 'narration', 'basis']}
    obj = {'type': 'object', 'additionalProperties': False,
           'properties': {'id': text, 'label': text, 'shape': {'type': 'string', 'enum': list(SHAPES)},
                          'size': vector, 'position': vector, 'color': text, 'rotation': vector, 'explode': vector},
           'required': ['id', 'label', 'shape', 'size', 'position', 'color']}
    bounds = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4}
    point = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}
    diagram = {'type': 'object', 'additionalProperties': False, 'properties': {
        'nodes': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
            'properties': {'id': text, 'label': text, 'step_id': text, 'bounds': bounds}, 'required': ['id', 'label', 'step_id', 'bounds']}},
        'edges': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
            'properties': {'from': text, 'to': text, 'label': text}, 'required': ['from', 'to', 'label']}}}, 'required': ['nodes', 'edges']}
    overlays = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'properties': {'id': text, 'kind': {'type': 'string', 'enum': ['arrow', 'box', 'label', 'card']},
                       'step_id': text, 'start': point, 'end': point, 'text': text, 'photo': {'type': 'boolean'}},
        'required': ['id', 'kind', 'step_id', 'start', 'end', 'text', 'photo']}}
    if kind == 'presentation':
        scene = {'type': 'object', 'additionalProperties': False,
                 'properties': {'fidelity': {'type': 'string', 'enum': list(SCENE_FIDELITY)},
                                'objects': {'type': 'array', 'items': obj},
                                'arrows': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                    'properties': {'from': text, 'to': text, 'label': text},
                                    'required': ['from', 'to', 'label']}}},
                 'required': ['fidelity', 'objects']}
        schema = {'type': 'object', 'additionalProperties': False,
                'properties': {'schema_version': text, 'kind': {'type': 'string', 'enum': ['presentation']},
                               'title': text, 'summary': text,
                               'fidelity': {'type': 'string', 'enum': list(FIDELITY)},
                               'steps': {'type': 'array', 'items': step}, 'scene': scene, 'diagram': diagram, 'overlays': overlays,
                               'asset': {'type': 'object', 'additionalProperties': False, 'properties': {
                                   'kind': {'type': 'string', 'enum': ['single_cylinder_engine']}, 'scale': {'type': 'number'}},
                                   'required': ['kind', 'scale']}},
                'required': ['schema_version', 'kind', 'title', 'summary', 'fidelity', 'steps']}
        return _strict_schema(schema) if strict else schema
    if kind == 'patch':
        op = {'type': 'object', 'additionalProperties': False,
              'properties': {'op': {'type': 'string', 'enum': ['step.update', 'step.insert_after', 'step.remove', 'object.update']},
                             'step_id': text, 'step': step, 'object_id': text,
                             'title': text, 'body': text, 'narration': text, 'basis': text, 'focus': {'type': 'array', 'items': text},
                             'label': text, 'shape': text, 'size': vector, 'position': vector, 'color': text,
                             'rotation': vector, 'explode': vector}, 'required': ['op']}
        schema = {'type': 'object', 'additionalProperties': False,
                'properties': {'schema_version': text, 'kind': {'type': 'string', 'enum': ['patch']},
                               'answer': text, 'ops': {'type': 'array', 'items': op}},
                'required': ['schema_version', 'kind', 'answer', 'ops']}
        return _strict_schema(schema) if strict else schema
    raise ValueError('Unsupported presentation schema kind')


class PlanError(ValueError):
    """The model output does not satisfy the closed presentation contract."""


def _text(value, name, limit, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise PlanError(f'{name} debe ser texto de 1 a {limit} caracteres.')
    return value.strip()


def _closed(obj, required, optional=(), name='objeto'):
    if not isinstance(obj, dict):
        raise PlanError(f'{name} debe ser un objeto JSON.')
    keys = set(obj)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise PlanError(f'{name} tiene campos ausentes o no permitidos: {sorted(keys ^ set(required))}.')


def _vector(value, name, low, high):
    if (not isinstance(value, list) or len(value) != 3
            or any(type(n) not in (int, float) or not math.isfinite(n) or not low <= n <= high for n in value)):
        raise PlanError(f'{name} debe ser [x,y,z] con valores entre {low} y {high}.')
    return [float(n) for n in value]


def _ids(value, pattern, name, limit):
    if not isinstance(value, list) or len(value) > limit or len(set(map(str, value))) != len(value) \
            or any(not isinstance(i, str) or not pattern.fullmatch(i) for i in value):
        raise PlanError(f'{name} debe ser una lista de hasta {limit} ids únicos.')
    return list(value)


def _step(step):
    _closed(step, ('id', 'title', 'body', 'narration', 'basis'), ('focus',), name='Paso')
    if not isinstance(step['id'], str) or not STEP_ID.fullmatch(step['id']):
        raise PlanError('Cada paso necesita un id como "s1".')
    if step['basis'] not in BASIS:
        raise PlanError('basis debe ser observed, documented, inferred o assumed.')
    result = {'id': step['id'], **{k: _text(step[k], k, n) for k, n in LIMITS.items()}, 'basis': step['basis']}
    if 'focus' in step:
        result['focus'] = _ids(step['focus'], OBJECT_ID, 'focus', 8)
    return result


def _object(obj):
    _closed(obj, ('id', 'label', 'shape', 'size', 'position', 'color'), ('rotation', 'explode'), name='Objeto')
    if not isinstance(obj['id'], str) or not OBJECT_ID.fullmatch(obj['id']):
        raise PlanError('Cada objeto necesita un id como "o1".')
    if obj['shape'] not in SHAPES:
        raise PlanError('shape no permitido.')
    if not isinstance(obj['color'], str) or not COLOR.fullmatch(obj['color']):
        raise PlanError('color debe ser #rrggbb.')
    result = {'id': obj['id'], 'label': _text(obj['label'], 'label', 80), 'shape': obj['shape'],
              'size': _vector(obj['size'], 'size', .05, 10), 'position': _vector(obj['position'], 'position', -10, 10),
              'color': obj['color'].lower()}
    if 'rotation' in obj:
        result['rotation'] = _vector(obj['rotation'], 'rotation', -360, 360)
    if 'explode' in obj:
        result['explode'] = _vector(obj['explode'], 'explode', -10, 10)
    return result


def _scene(scene):
    _closed(scene, ('fidelity', 'objects'), ('arrows',), name='Escena')
    if scene['fidelity'] not in SCENE_FIDELITY:
        raise PlanError('Una escena solo puede ser illustrative o conceptual.')
    objects = scene['objects']
    if not isinstance(objects, list) or not 1 <= len(objects) <= MAX_OBJECTS:
        raise PlanError(f'La escena necesita entre 1 y {MAX_OBJECTS} objetos.')
    objects = [_object(o) for o in objects]
    ids = {o['id'] for o in objects}
    if len(ids) != len(objects):
        raise PlanError('Los ids de los objetos deben ser únicos.')
    result = {'fidelity': scene['fidelity'], 'objects': objects}
    if 'arrows' in scene:
        arrows = scene['arrows']
        if not isinstance(arrows, list) or len(arrows) > MAX_ARROWS:
            raise PlanError(f'La escena admite hasta {MAX_ARROWS} flechas.')
        result['arrows'] = []
        for arrow in arrows:
            _closed(arrow, ('from', 'to', 'label'), name='Flecha')
            if arrow['from'] not in ids or arrow['to'] not in ids or arrow['from'] == arrow['to']:
                raise PlanError('Cada flecha une dos objetos distintos de la escena.')
            result['arrows'].append({'from': arrow['from'], 'to': arrow['to'], 'label': _text(arrow['label'], 'label', 80)})
    return result


def _normalized(value, count, name):
    if (not isinstance(value, list) or len(value) != count
            or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in value)):
        raise PlanError(f'{name} requiere {count} coordenadas finitas entre 0 y 1.')
    return list(value)


def _diagram(value, steps):
    _closed(value, ('nodes', 'edges'), name='Diagrama')
    if not isinstance(value['nodes'], list) or not 2 <= len(value['nodes']) <= 16:
        raise PlanError('El diagrama admite entre 2 y 16 nodos.')
    nodes, ids = [], set()
    for node in value['nodes']:
        _closed(node, ('id', 'label', 'step_id', 'bounds'), name='Nodo')
        if (not isinstance(node['id'], str) or not re.fullmatch(r'd[0-9]{1,3}', node['id']) or node['id'] in ids
                or not isinstance(node['step_id'], str) or node['step_id'] not in steps):
            raise PlanError('Nodo duplicado, identificador inválido o paso desconocido.')
        x, y, width, height = _normalized(node['bounds'], 4, 'bounds')
        if width < .03 or height < .03 or x + width > 1 or y + height > 1:
            raise PlanError('El nodo debe ocupar una región visible dentro del diagrama.')
        ids.add(node['id']); nodes.append({**node, 'label': _text(node['label'], 'label', 100), 'bounds': [x, y, width, height]})
    if not isinstance(value['edges'], list) or len(value['edges']) > 24:
        raise PlanError('El diagrama admite hasta 24 enlaces.')
    edges = []
    for edge in value['edges']:
        _closed(edge, ('from', 'to', 'label'), name='Enlace')
        if edge['from'] not in ids or edge['to'] not in ids or edge['from'] == edge['to']:
            raise PlanError('El enlace requiere dos nodos existentes distintos.')
        edges.append({**edge, 'label': _text(edge['label'], 'label', 80)})
    return {'nodes': nodes, 'edges': edges}


def _overlays(values, steps):
    if not isinstance(values, list) or len(values) > 16:
        raise PlanError('Se admiten hasta 16 anotaciones por presentación.')
    result, ids = [], set()
    for item in values:
        _closed(item, ('id', 'kind', 'step_id', 'start', 'end', 'text', 'photo'), name='Anotación')
        if (not isinstance(item['id'], str) or not re.fullmatch(r'a[0-9]{1,3}', item['id']) or item['id'] in ids
                or item['kind'] not in ('arrow', 'box', 'label', 'card') or not isinstance(item['step_id'], str) or item['step_id'] not in steps
                or type(item['photo']) is not bool or item['photo'] and item['kind'] != 'card'):
            raise PlanError('Anotación, paso o referencia de foto inválida.')
        start, end = _normalized(item['start'], 2, 'start'), _normalized(item['end'], 2, 'end')
        if math.dist(start, end) < .02 or item['kind'] != 'arrow' and (end[0] <= start[0] or end[1] <= start[1]):
            raise PlanError('La anotación requiere extensión visible dentro de la selección.')
        text = item['text']
        if not isinstance(text, str) or len(text) > 240 or '\x00' in text:
            raise PlanError('Texto de anotación inválido.')
        if item['kind'] in ('label', 'card') and not text.strip():
            raise PlanError('La tarjeta o etiqueta requiere texto.')
        ids.add(item['id']); result.append({**item, 'start': start, 'end': end, 'text': text.strip()})
    return result


def validate_plan(plan):
    _closed(plan, ('schema_version', 'kind', 'title', 'summary', 'fidelity', 'steps'), ('scene', 'asset', 'diagram', 'overlays'), name='Plan')
    if plan['schema_version'] != SCHEMA_VERSION or plan['kind'] != 'presentation':
        raise PlanError('Versión o tipo de plan no compatible.')
    if plan['fidelity'] not in FIDELITY:
        raise PlanError('fidelity debe ser illustrative, conceptual o technical.')
    steps = plan['steps']
    if not isinstance(steps, list) or not 2 <= len(steps) <= MAX_STEPS:
        raise PlanError(f'El plan necesita entre 2 y {MAX_STEPS} pasos.')
    steps = [_step(s) for s in steps]
    if len({s['id'] for s in steps}) != len(steps):
        raise PlanError('Los ids de los pasos deben ser únicos.')
    result = {'schema_version': SCHEMA_VERSION, 'kind': 'presentation', 'title': _text(plan['title'], 'title', 120),
              'summary': _text(plan['summary'], 'summary', 240), 'fidelity': plan['fidelity'], 'steps': steps}
    if 'scene' in plan:
        result['scene'] = _scene(plan['scene'])
    if 'asset' in plan:
        try:
            scene = engine_asset(plan['asset'])
        except ValueError as exc:
            raise PlanError(str(exc)) from None
        result['asset'] = dict(plan['asset'])
        if 'scene' not in result: result['scene'] = _scene(scene)
    step_ids = {step['id'] for step in steps}
    if 'diagram' in plan: result['diagram'] = _diagram(plan['diagram'], step_ids)
    if 'overlays' in plan: result['overlays'] = _overlays(plan['overlays'], step_ids)
    ids = {o['id'] for o in result.get('scene', {}).get('objects', [])}
    if any(not set(s.get('focus', ())) <= ids for s in steps):
        raise PlanError('focus solo puede nombrar objetos de la escena.')
    return result


def apply_patch(plan, patch):
    """Apply a whitelisted patch to a valid plan; the result is revalidated as a whole."""
    _closed(patch, ('schema_version', 'kind', 'answer', 'ops'), name='Patch')
    if patch['schema_version'] != SCHEMA_VERSION or patch['kind'] != 'patch':
        raise PlanError('Versión o tipo de patch no compatible.')
    answer = _text(patch['answer'], 'answer', 600)
    ops = patch['ops']
    if not isinstance(ops, list) or len(ops) > MAX_OPS:
        raise PlanError(f'El patch admite hasta {MAX_OPS} operaciones.')
    result = copy.deepcopy(plan)
    for op in ops:
        kind = op.get('op') if isinstance(op, dict) else None
        if kind == 'object.update':
            _closed(op, ('op', 'object_id'), OBJECT_FIELDS, name='object.update')
            objects = result.get('scene', {}).get('objects', [])
            index = next((i for i, o in enumerate(objects) if o['id'] == op['object_id']), None)
            changes = {k: v for k, v in op.items() if k not in ('op', 'object_id')}
            if index is None or not changes:
                raise PlanError('object.update necesita un objeto existente y al menos un cambio.')
            objects[index] = {**objects[index], **changes}  # Checked by the final validate_plan.
            continue
        index = next((i for i, s in enumerate(result['steps']) if s['id'] == op.get('step_id')), None) if kind else None
        if index is None:
            raise PlanError('Cada operación debe referirse a un paso existente.')
        if kind == 'step.update':
            _closed(op, ('op', 'step_id'), ('title', 'body', 'narration', 'basis', 'focus'), name='step.update')
            changes = {k: v for k, v in op.items() if k not in ('op', 'step_id')}
            if not changes:
                raise PlanError('step.update necesita al menos un cambio.')
            result['steps'][index] = _step({**result['steps'][index], **changes})
        elif kind == 'step.insert_after':
            _closed(op, ('op', 'step_id', 'step'), name='step.insert_after')
            result['steps'].insert(index + 1, _step(op['step']))
        elif kind == 'step.remove':
            _closed(op, ('op', 'step_id'), name='step.remove')
            result['steps'].pop(index)
        else:
            raise PlanError('Operación de patch no permitida.')
    return validate_plan(result), answer


def parse_json(text):
    """Accept one JSON object, optionally wrapped in a single ```json fence."""
    text = text.strip()
    fence = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Campo JSON duplicado.')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Número JSON no finito.')
    try:
        return json.loads(fence.group(1) if fence else text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise PlanError('La respuesta del modelo no es JSON válido.') from exc
