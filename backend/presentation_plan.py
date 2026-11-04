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
from backend.spatial_assets import KINDS, asset_scene, catalog_text

SCHEMA_VERSION = '1.0'
MAX_STEPS = 8
MAX_OPS = 8
MAX_OBJECTS = 24
MAX_ARROWS = 12
FIDELITY = ('illustrative', 'conceptual', 'technical')
SCENE_FIDELITY = ('illustrative', 'conceptual')
BASIS = ('observed', 'documented', 'inferred', 'assumed')
SHAPES = ('box', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'piston', 'connecting_rod', 'crankshaft', 'engine_cylinder')
SHAPE_MAP = {
    'cube': 'box', 'block': 'box', 'plate': 'box', 'cuboid': 'box', 'rectangle': 'box',
    'prism': 'box', 'wall': 'box', 'tower': 'box', 'building': 'box', 'base': 'box',
    'ball': 'sphere', 'orb': 'sphere', 'dome': 'sphere', 'globe': 'sphere',
    'pipe': 'cylinder', 'rod': 'cylinder', 'tube': 'cylinder', 'capsule': 'cylinder',
    'column': 'cylinder', 'pillar': 'cylinder', 'shaft': 'cylinder', 'pin': 'cylinder', 'disc': 'cylinder',
    'pyramid': 'cone', 'roof': 'cone', 'spire': 'cone', 'steeple': 'cone', 'tip': 'cone',
    'ring': 'torus', 'donut': 'torus', 'arch': 'torus',
    'surface': 'plane', 'ground': 'plane', 'floor': 'plane', 'sheet': 'plane',
}
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
    'En scene separa piezas funcionales visibles con etiquetas precisas y proporciones relativas coherentes; usa las formas semánticas de motor cuando correspondan. '
    'En scene.objects usa ids o1, o2, etc.; focus y arrows deben referir esos mismos ids. '
    'Para objetos técnicos, compón la escena con piezas distinguibles, uniones y ejes de movimiento explicables; usa colores diferentes para identificar funciones y una vista despiezada útil. Evita adornos que aparenten especificaciones no observadas. '
    'Añade diagram con nodos d1..d16, bounds=[x,y,ancho,alto] normalizados y edges que refieran nodos existentes. '
    'Añade overlays solo sobre la selección: hasta 16 flechas, cajas, etiquetas o tarjetas vinculadas a step_id; photo=true muestra el recorte seleccionado. '
    'Usa focus solo cuando el paso tenga objetos 3D reales de scene o asset; debe ser una lista de hasta 8 ids únicos existentes. '
    'Si preguntan dónde está algo, dibuja un overlay kind="box" en s1 sobre sus límites visibles dentro de la selección; '
    'si no puedes ubicarlo con confianza, di que no lo encuentras y no dibujes una marca inventada. '
    'Si piden un diagrama, incluye diagram; si piden 3D y el objeto admite una explicación espacial útil, incluye scene o asset conceptual. '
    'Para matemáticas, texto, software o pantallas omite scene: '
    'no uses 3D solo por ser vistoso. La escena es conceptual: no inventes geometría interna, dimensiones exactas ni conexiones. '
    'Nunca incluyas HTML, código ni enlaces.'
    ' Si el sujeto coincide con un ensamblaje local, prefiere "asset":{"kind":"<kind>","scale":1} sin scene; '
    'Axx lo construye localmente como piezas o1..oN, conceptual, sin simulación física ni precisión CAD. Ensamblajes disponibles: ' + catalog_text() + '. '
    'Puedes añadir "diagram":{"nodes":[{"id":"d1","label":"…","step_id":"s1","bounds":[x,y,ancho,alto]}],'
    '"edges":[{"from":"d1","to":"d2","label":"…"}]} con 2 a 16 nodos y hasta 24 enlaces. '
    'Las coordenadas están normalizadas entre 0 y 1. Para enseñar sobre la selección usa "overlays":'
    '[{"id":"a1","kind":"arrow|box|label|card","step_id":"s1","start":[x,y],"end":[x,y],"text":"…","photo":false}]. '
    'Hasta 16 anotaciones; photo solo puede ser true para una tarjeta que muestra la captura seleccionada. '
    'Cada anotación pertenece a un paso y permanece visible en ese paso hasta cambiar de paso o captura.'
)

PLAN_2D_CONTRACT = (
    'Responde SOLO con JSON, sin Markdown: '
    '{"schema_version":"1.0","kind":"presentation","title":"…","summary":"…",'
    '"fidelity":"illustrative|conceptual|technical",'
    '"steps":[{"id":"s1","title":"…","body":"…","narration":"…","basis":"observed|inferred|assumed"}],'
    '"overlays":[{"id":"a1","kind":"box","step_id":"s1","start":[0.1,0.1],"end":[0.3,0.3],"text":"…","photo":false}]}. '
    'Usa de 1 a 4 pasos breves: uno basta para señalar; usa al menos dos para un diagrama explicativo. '
    'IMPORTANTE: "steps" contiene pasos explicativos con id, title, body, narration, basis. '
    'Si se pide señalar algo visible, añade "overlays" como lista separada al nivel principal del JSON, FUERA de steps. '
    'start y end son esquinas de la región visible [x, y], coordenadas entre 0 y 1 relativas a la imagen seleccionada. '
    'Si no puedes localizarlo con confianza, explica que no es visible y omite overlays. '
    'Si se pide diagrama, añade "diagram":{"nodes":[{"id":"d1","label":"…","step_id":"s1",'
    '"bounds":[0.1,0.1,0.3,0.2]},{"id":"d2","label":"…","step_id":"s2",'
    '"bounds":[0.6,0.6,0.3,0.2]}],"edges":[{"from":"d1","to":"d2","label":"…"}]}. '
    'En diagram, bounds significa [x,y,ancho,alto] entre 0 y 1. No añadas scene, asset, focus, HTML ni código. '
    'Distingue lo observado de lo inferido; no inventes medidas ni componentes ocultos.'
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


def _clean_focus_list(focus, ids):
    if not isinstance(focus, list) or len(focus) > 8 or len(focus) != len(set(map(str, focus))):
        return None
    if any(not isinstance(item, str) or item not in ids or not OBJECT_ID.fullmatch(item) for item in focus):
        return None
    return list(focus)


def normalize_model_focus(plan):
    """Drop unreliable optional 3D focus from a model response; validation still owns every required field."""
    if not isinstance(plan, dict):
        return plan
    result = copy.deepcopy(plan)
    if result.get('kind') == 'patch' and isinstance(result.get('ops'), list):
        for op in result['ops']:
            if isinstance(op, dict):
                if 'focus' in op:
                    focus = op['focus']
                    if focus is not None:
                        if not isinstance(focus, list):
                            op.pop('focus', None)
                        else:
                            # deduplicate and keep valid
                            seen = set()
                            cleaned = [i for i in focus if isinstance(i, str) and OBJECT_ID.fullmatch(i) and not (i in seen or seen.add(i))][:8]
                            if cleaned:
                                op['focus'] = cleaned
                            else:
                                op['focus'] = None
                if isinstance(op.get('step'), dict) and 'focus' in op['step']:
                    focus = op['step']['focus']
                    if focus is not None:
                        if not isinstance(focus, list):
                            op['step'].pop('focus', None)
                        else:
                            seen = set()
                            cleaned = [i for i in focus if isinstance(i, str) and OBJECT_ID.fullmatch(i) and not (i in seen or seen.add(i))][:8]
                            if cleaned:
                                op['step']['focus'] = cleaned
                            else:
                                op['step'].pop('focus', None)
        return result
    if not isinstance(result.get('steps'), list):
        return result
    scene = result.get('scene')
    objects = scene.get('objects') if isinstance(scene, dict) else None
    ids = {item.get('id') for item in objects if isinstance(item, dict)} if isinstance(objects, list) else set()
    try:
        if 'asset' in result and isinstance(result['asset'], dict):
            ids.update(o['id'] for o in asset_scene(result['asset'])['objects'])
    except (ValueError, KeyError):
        pass  # no asset or an invalid one: validate_plan reports it
    for step in result['steps']:
        if isinstance(step, dict) and 'focus' in step:
            cleaned = _clean_focus_list(step['focus'], ids)
            if cleaned is not None:
                step['focus'] = cleaned
            else:
                step.pop('focus', None)
    return result


def normalize_model_object_ids(plan):
    """Map unique model-named scene objects to the bounded IDs required by the renderer and clean nulls."""
    if not isinstance(plan, dict):
        return plan
    result = copy.deepcopy(plan)
    for opt in ('asset', 'diagram', 'overlays'):
        if opt in result and result[opt] is None:
            result.pop(opt)
    scene = result.get('scene')
    if not isinstance(scene, dict):
        if result.get('kind') == 'patch' and isinstance(result.get('ops'), list):
            for op in result['ops']:
                if isinstance(op, dict) and op.get('op') == 'object.update':
                    if 'shape' in op and op['shape'] not in SHAPES:
                        op['shape'] = SHAPE_MAP.get(str(op['shape']).lower(), 'box')
                    if 'color' in op and isinstance(op['color'], str):
                        c = op['color'].strip().lower()
                        if re.fullmatch(r'#[0-9a-f]{3}', c):
                            c = '#' + ''.join(ch * 2 for ch in c[1:])
                        elif not COLOR.fullmatch(c):
                            c = '#888888'
                        op['color'] = c
        return result
    if 'arrows' in scene and scene['arrows'] is None:
        scene.pop('arrows')
    objects = scene.get('objects')
    if not isinstance(objects, list) or not 1 <= len(objects) <= MAX_OBJECTS:
        return result
    for obj in objects:
        if isinstance(obj, dict):
            for opt in ('rotation', 'explode'):
                if opt in obj and obj[opt] is None:
                    obj.pop(opt)
            if 'shape' in obj and obj['shape'] not in SHAPES:
                obj['shape'] = SHAPE_MAP.get(str(obj['shape']).lower(), 'box')
            if 'color' in obj and isinstance(obj['color'], str):
                c = obj['color'].strip().lower()
                if re.fullmatch(r'#[0-9a-f]{3}', c):
                    c = '#' + ''.join(ch * 2 for ch in c[1:])
                elif not COLOR.fullmatch(c):
                    c = '#888888'
                obj['color'] = c
            for vec_field, low, high in (('size', 0.05, 10.0), ('position', -10.0, 10.0), ('rotation', -360.0, 360.0), ('explode', -10.0, 10.0)):
                if vec_field in obj and isinstance(obj[vec_field], list) and len(obj[vec_field]) == 3:
                    if all(type(v) in (int, float) and math.isfinite(v) for v in obj[vec_field]):
                        obj[vec_field] = [round(max(low, min(high, float(v))), 4) for v in obj[vec_field]]
    ids = [obj.get('id') if isinstance(obj, dict) else None for obj in objects]
    if (any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,63}', value) for value in ids)
            or len(set(ids)) != len(ids)):
        return result
    if all(OBJECT_ID.fullmatch(value) for value in ids):
        mapping = {value: value for value in ids}
    else:
        mapping = {value: f'o{index}' for index, value in enumerate(ids, 1)}
        for obj in objects:
            obj['id'] = mapping[obj['id']]
    arrows = scene.get('arrows')
    if isinstance(arrows, list):
        valid_arrows = []
        for arrow in arrows:
            if isinstance(arrow, dict) and arrow.get('from') in mapping and arrow.get('to') in mapping and arrow.get('from') != arrow.get('to'):
                arrow['from'] = mapping[arrow['from']]
                arrow['to'] = mapping[arrow['to']]
                valid_arrows.append(arrow)
        scene['arrows'] = valid_arrows
    if isinstance(result.get('steps'), list):
        for step in result['steps']:
            if isinstance(step, dict) and isinstance(step.get('focus'), list):
                if all(isinstance(value, str) and value in mapping for value in step['focus']):
                    step['focus'] = [mapping[value] for value in step['focus']]
                else:
                    step.pop('focus')
    return result

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
                                   'kind': {'type': 'string', 'enum': list(KINDS)}, 'scale': {'type': 'number'}},
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
    if obj.get('rotation') is not None:
        result['rotation'] = _vector(obj['rotation'], 'rotation', -360, 360)
    if obj.get('explode') is not None:
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
    if scene.get('arrows') is not None:
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


def validate_plan(plan, *, min_steps=2):
    _closed(plan, ('schema_version', 'kind', 'title', 'summary', 'fidelity', 'steps'), ('scene', 'asset', 'diagram', 'overlays'), name='Plan')
    if plan['schema_version'] != SCHEMA_VERSION or plan['kind'] != 'presentation':
        raise PlanError('Versión o tipo de plan no compatible.')
    if plan['fidelity'] not in FIDELITY:
        raise PlanError('fidelity debe ser illustrative, conceptual o technical.')
    steps = plan['steps']
    if not isinstance(steps, list) or not min_steps <= len(steps) <= MAX_STEPS:
        raise PlanError(f'El plan necesita entre {min_steps} y {MAX_STEPS} pasos.')
    steps = [_step(s) for s in steps]
    if len({s['id'] for s in steps}) != len(steps):
        raise PlanError('Los ids de los pasos deben ser únicos.')
    result = {'schema_version': SCHEMA_VERSION, 'kind': 'presentation', 'title': _text(plan['title'], 'title', 120),
              'summary': _text(plan['summary'], 'summary', 240), 'fidelity': plan['fidelity'], 'steps': steps}
    if plan.get('scene') is not None:
        result['scene'] = _scene(plan['scene'])
    if plan.get('asset') is not None:
        try:
            scene = asset_scene(plan['asset'])
        except ValueError as exc:
            raise PlanError(str(exc)) from None
        result['asset'] = dict(plan['asset'])
        if 'scene' not in result: result['scene'] = _scene(scene)
    step_ids = {step['id'] for step in steps}
    if plan.get('diagram') is not None: result['diagram'] = _diagram(plan['diagram'], step_ids)
    if plan.get('overlays') is not None: result['overlays'] = _overlays(plan['overlays'], step_ids)
    ids = {o['id'] for o in result.get('scene', {}).get('objects', [])}
    if any(not set(s.get('focus', ())) <= ids for s in steps):
        raise PlanError('focus solo puede nombrar objetos de la escena.')
    return result


def validate_2d_plan(plan):
    """Keep local-model answers on the existing validated 2D canvas."""
    if not isinstance(plan, dict):
        raise PlanError('El plan 2D debe ser un objeto JSON.')
    plan = copy.deepcopy(plan)
    plan.pop('scene', None)
    plan.pop('asset', None)
    if isinstance(plan.get('steps'), list):
        extracted_overlays = []
        clean_steps = []
        for i, step in enumerate(plan['steps']):
            if not isinstance(step, dict):
                continue
            step.pop('focus', None)
            has_overlay = any(k in step for k in ('start', 'end', 'kind'))
            raw_text = str(step.get('text') or step.get('title') or step.get('body') or plan.get('title') or 'Ubicación observada').strip()[:240]
            if has_overlay:
                kind = step.get('kind') if step.get('kind') in ('arrow', 'box', 'label', 'card') else 'box'
                start = step.get('start') if isinstance(step.get('start'), list) and len(step['start']) == 2 else [0.1, 0.1]
                end = step.get('end') if isinstance(step.get('end'), list) and len(step['end']) == 2 else [0.3, 0.3]
                extracted_overlays.append({
                    'id': f"a{len(extracted_overlays) + 1}",
                    'kind': kind,
                    'step_id': step.get('step_id') or step.get('id') or f"s{i+1}",
                    'start': start,
                    'end': end,
                    'text': raw_text,
                    'photo': bool(step.get('photo', False)) if kind == 'card' else False
                })
            step_id = step.get('id') if isinstance(step.get('id'), str) and STEP_ID.fullmatch(step['id']) else f"s{len(clean_steps) + 1}"
            title = str(step.get('title') or raw_text).strip()[:80]
            body = str(step.get('body') or raw_text).strip()[:400]
            narration = str(step.get('narration') or title).strip()[:400]
            basis = step.get('basis') if step.get('basis') in BASIS else 'observed'
            clean_steps.append({'id': step_id, 'title': title, 'body': body, 'narration': narration, 'basis': basis})
        plan['steps'] = clean_steps
        if extracted_overlays:
            existing = plan.get('overlays', [])
            if not isinstance(existing, list):
                existing = []
            combined = existing + extracted_overlays
            valid_steps = {s['id'] for s in clean_steps}
            for ov in combined:
                if ov.get('step_id') not in valid_steps and clean_steps:
                    ov['step_id'] = clean_steps[0]['id']
            plan['overlays'] = combined[:16]

    if isinstance(plan.get('overlays'), list):
        for overlay in plan['overlays']:
            if isinstance(overlay, dict):
                overlay.setdefault('photo', False)
                if overlay.get('kind') != 'arrow' and isinstance(overlay.get('start'), list) and isinstance(overlay.get('end'), list) and len(overlay['start']) == 2 and len(overlay['end']) == 2:
                    s, e = overlay['start'], overlay['end']
                    if all(type(v) in (int, float) and math.isfinite(v) for v in s + e):
                        x0, x1 = min(s[0], e[0]), max(s[0], e[0])
                        y0, y1 = min(s[1], e[1]), max(s[1], e[1])
                        if x1 - x0 < 0.03: x1 = min(1.0, x0 + 0.04)
                        if y1 - y0 < 0.03: y1 = min(1.0, y0 + 0.04)
                        overlay['start'] = [round(max(0.0, min(1.0, x0)), 4), round(max(0.0, min(1.0, y0)), 4)]
                        overlay['end'] = [round(max(0.0, min(1.0, x1)), 4), round(max(0.0, min(1.0, y1)), 4)]
    diagram = plan.get('diagram')
    if (isinstance(diagram, dict) and set(diagram) == {'nodes', 'edges'}
            and isinstance(diagram['nodes'], list) and len(diagram['nodes']) < 2
            and isinstance(diagram['edges'], list)
            and all(isinstance(node, dict) and set(node) == {'id', 'label', 'step_id', 'bounds'} for node in diagram['nodes'])
            and all(isinstance(edge, dict) and set(edge) == {'from', 'to', 'label'} for edge in diagram['edges'])):
        # The renderer derives a diagram from validated steps when a local model omits nodes.
        plan.pop('diagram')
    return validate_plan(plan, min_steps=1)


def apply_patch(plan, patch, *, min_steps=2):
    """Apply a whitelisted patch to a valid plan; the result is revalidated as a whole."""
    _closed(patch, ('schema_version', 'kind', 'answer', 'ops'), name='Patch')
    if patch['schema_version'] != SCHEMA_VERSION or patch['kind'] != 'patch':
        raise PlanError('Versión o tipo de patch no compatible.')
    answer = _text(patch['answer'], 'answer', 600)
    ops = patch['ops']
    if not isinstance(ops, list) or len(ops) > MAX_OPS:
        raise PlanError(f'El patch admite hasta {MAX_OPS} operaciones.')
    result = copy.deepcopy(plan)
    patch_normalized = normalize_model_focus(normalize_model_object_ids(copy.deepcopy(patch)))
    for op in patch_normalized.get('ops', ops):
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
            updated = {**result['steps'][index], **changes}
            if 'focus' in changes and changes['focus'] is None:
                updated.pop('focus', None)
            result['steps'][index] = _step(updated)
        elif kind == 'step.insert_after':
            _closed(op, ('op', 'step_id', 'step'), name='step.insert_after')
            result['steps'].insert(index + 1, _step(op['step']))
        elif kind == 'step.remove':
            _closed(op, ('op', 'step_id'), name='step.remove')
            result['steps'].pop(index)
        else:
            raise PlanError('Operación de patch no permitida.')
    return validate_plan(normalize_model_focus(result), min_steps=min_steps), answer


def parse_json(text):
    """Accept one JSON object or array, stripping markdown fences or wrapping commentary."""
    if not isinstance(text, str) or not text.strip():
        raise PlanError('La respuesta del modelo no es JSON válido.')
    raw = text.strip()
    candidate = None
    fence_match = re.search(r'```(?:json)?\s*([\{\[].*?[\}\]])\s*```', raw, re.S)
    if fence_match:
        candidate = fence_match.group(1).strip()
    if not candidate:
        start = -1
        for i, ch in enumerate(raw):
            if ch in ('{', '['):
                start = i
                break
        if start != -1:
            end = max(raw.rfind('}'), raw.rfind(']'))
            if end > start:
                candidate = raw[start:end + 1]
    if not candidate:
        candidate = raw

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Campo JSON duplicado.')
            result[key] = value
        return result

    def constant(value):
        raise ValueError('Número JSON no finito.')

    def _clean_json(s):
        s = re.sub(r'//[^\n]*', '', s)
        s = re.sub(r',\s*([\}\]])', r'\1', s)
        return s

    try:
        return json.loads(candidate, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        try:
            return json.loads(_clean_json(candidate), object_pairs_hook=pairs, parse_constant=constant)
        except (ValueError, RecursionError) as exc:
            raise PlanError('La respuesta del modelo no es JSON válido.') from exc
