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
from backend.shape_registry import ShapeRegistry, catalog_text as component_catalog, expand_component_refs

SCHEMA_VERSION = '1.0'
MAX_STEPS = 8
MAX_OPS = 16  # corrections may add or remove several parts
MAX_OBJECTS = 48  # detailed technical models need many small parts
MAX_ARROWS = 12
FIDELITY = ('illustrative', 'conceptual', 'technical')
SCENE_FIDELITY = ('illustrative', 'conceptual')
BASIS = ('observed', 'documented', 'inferred', 'assumed')
SHAPES = ('box', 'sphere', 'cylinder', 'cone', 'torus', 'plane', 'piston', 'connecting_rod', 'crankshaft', 'engine_cylinder',
          'ellipsoid', 'capsule', 'tube', 'frustum', 'dome', 'wedge', 'hexprism', 'gable',
          'gear', 'coil', 'l_bracket', 'u_channel', 'i_beam', 'pipe_elbow', 'heatsink', 'flange', 'pyramid', 'chamfer_cylinder',
          'threaded_rod', 'slot', 'rect_tube', 'arc', 'knurled_cylinder',
          'octaprism', 'paraboloid', 'arch', 'dna_helix', 'tapered_capsule',
          'hyperboloid', 'barrel', 'trefoil_knot', 'triangular_prism', 'pentaprism', 'helix_spring',
          'fluted_column', 'tetrahedron', 'dodecahedron', 'icosahedron', 'bipyramid', 'conical_spring')
MATERIALS = ('metal_brushed', 'metal_polished', 'metal_anodized', 'plastic', 'rubber', 'glass', 'ceramic', 'wood', 'fabric', 'stone', 'paint', 'emissive')
SHAPE_MAP = {
    'cube': 'box', 'block': 'box', 'plate': 'box', 'cuboid': 'box', 'rectangle': 'box',
    'prism': 'box', 'wall': 'box', 'tower': 'box', 'building': 'box', 'base': 'box',
    'ball': 'sphere', 'orb': 'sphere', 'dome': 'sphere', 'globe': 'sphere',
    'pipe': 'cylinder', 'rod': 'cylinder', 'tube': 'tube', 'capsule': 'capsule',
    'column': 'cylinder', 'pillar': 'cylinder', 'shaft': 'cylinder', 'pin': 'cylinder', 'disc': 'cylinder',
    'pyramid': 'pyramid', 'roof': 'gable', 'gable_roof': 'gable', 'pitched_roof': 'gable', 'spire': 'cone', 'steeple': 'cone', 'tip': 'cone',
    'ring': 'torus', 'donut': 'torus', 'arch': 'arch',
    'oval': 'ellipsoid', 'egg': 'ellipsoid', 'pill': 'capsule', 'hemisphere': 'dome', 'half_sphere': 'dome',
    'octagonal_prism': 'octaprism', 'octagon': 'octaprism', 'octahedron': 'octaprism',
    'parabola': 'paraboloid', 'dish': 'paraboloid', 'reflector': 'paraboloid', 'antena': 'paraboloid',
    'curved_tube': 'arch', 'curved_pipe': 'arch', 'arco': 'arch',
    'dna': 'dna_helix', 'double_helix': 'dna_helix',
    'streamline_capsule': 'tapered_capsule', 'pod': 'tapered_capsule', 'gondola': 'tapered_capsule',
    'ramp': 'wedge', 'triangular_prism': 'triangular_prism', 'prisma_triangular': 'triangular_prism', 'hexagon': 'hexprism', 'hex': 'hexprism', 'nut': 'hexprism',
    'hiperboloide': 'hyperboloid', 'cooling_tower': 'hyperboloid', 'barril': 'barrel', 'cask': 'barrel',
    'trebol': 'trefoil_knot', 'pentagon': 'pentaprism', 'pentagono': 'pentaprism',
    'hollow_cylinder': 'tube', 'sleeve': 'tube', 'bushing': 'tube', 'truncated_cone': 'frustum', 'taper': 'frustum', 'funnel': 'frustum',
    'cog': 'gear', 'sprocket': 'gear', 'pinion': 'gear', 'toothed_wheel': 'gear',
    'helix': 'coil', 'resorte': 'helix_spring', 'muelle': 'helix_spring', 'spring': 'helix_spring',
    'bracket': 'l_bracket', 'angle_bracket': 'l_bracket', 'escuadra': 'l_bracket',
    'channel': 'u_channel', 'c_channel': 'u_channel', 'perfil_u': 'u_channel',
    'beam': 'i_beam', 'h_beam': 'i_beam', 'girder': 'i_beam', 'perfil_i': 'i_beam',
    'elbow': 'pipe_elbow', 'bend': 'pipe_elbow', 'codo': 'pipe_elbow',
    'radiator': 'heatsink', 'fins': 'heatsink', 'disipador': 'heatsink',
    'collar': 'flange', 'ring_flange': 'flange', 'brida': 'flange',
    'tetrahedro': 'tetrahedron', 'tetraedro': 'tetrahedron', 'piramide': 'pyramid',
    'dodecaedro': 'dodecahedron', 'icosaedro': 'icosahedron', 'bipiramide': 'bipyramid',
    'columna_estriada': 'fluted_column', 'estriado': 'fluted_column', 'fluted': 'fluted_column',
    'resorte_conico': 'conical_spring', 'muelle_conico': 'conical_spring',
    'comb': 'heatsink', 'peine': 'heatsink', 'pines': 'heatsink',
    'hex_bolt': 'hexprism', 'bolt': 'hexprism', 'perno': 'hexprism',
    'beveled_cylinder': 'chamfer_cylinder', 'chamfered_cylinder': 'chamfer_cylinder',
    'threaded': 'threaded_rod', 'thread': 'threaded_rod', 'varilla_roscada': 'threaded_rod', 'stud': 'threaded_rod',
    'oblong': 'slot', 'stadium': 'slot', 'ranura': 'slot',
    'square_tube': 'rect_tube', 'box_section': 'rect_tube', 'frame': 'rect_tube', 'tubo_cuadrado': 'rect_tube',
    'curve': 'arc', 'bent_rod': 'arc', 'handle': 'arc', 'asa': 'arc',
    'knurl': 'knurled_cylinder', 'grip': 'knurled_cylinder', 'moleteado': 'knurled_cylinder',
    'surface': 'plane', 'ground': 'plane', 'floor': 'plane', 'sheet': 'plane',
}
STEP_ID = re.compile(r's[0-9]{1,3}')
OBJECT_ID = re.compile(r'o[0-9]{1,3}')
COLOR = re.compile(r'#[0-9a-fA-F]{6}')
LIMITS = {'title': 80, 'body': 700, 'narration': 400}  # technical explanations need more than 400 characters
OBJECT_FIELDS = ('label', 'shape', 'size', 'position', 'color', 'rotation', 'explode', 'material', 'param', 'group')

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
    'PROCESO OBLIGATORIO: antes de modelar, analiza la imagen. Identifica qué objeto concreto es (no lo confundas con otro por el nombre: un motor eléctrico no es un motor de combustión), '
    'sus componentes visibles, formas, materiales, colores y posición relativa. El paso s1 se titula «Qué se observa», usa basis="observed" y lista técnicamente esos componentes. '
    'Después reconstruye ESE objeto en scene: una pieza por cada componente visible, con etiqueta técnica precisa, proporciones relativas medidas sobre la imagen, color y acabado aproximados. '
    'Cada paso siguiente es una explicación técnica de 3 a 5 frases (body de 350 a 700 caracteres) sobre una función, la relación con las piezas vecinas, el principio físico de funcionamiento, el material probable y lo que NO se puede determinar de la imagen;marca como "inferred" lo que deduces y como "assumed" el conocimiento general. '
    'Usa las formas semánticas piston, connecting_rod, crankshaft y engine_cylinder SOLO si la imagen muestra esos componentes. '
    'VOCABULARIO de scene.objects[].shape: box (param=bisel 0 a .3), sphere, ellipsoid, cylinder, cone, frustum (param=radio superior/inferior), tube (cilindro hueco, param=espesor de pared relativo), capsule, dome (semiesfera), wedge (cuña o rampa), gable (prisma triangular isósceles: tejados a dos aguas y frontones; base x, altura y, longitud z con la cumbrera a lo largo de Z), hexprism, torus, plane, gear (engranaje dentado, param=dientes), coil (muelle helicoidal, param=vueltas), l_bracket (escuadra en L, param=grosor), u_channel (canal en U, param=grosor), i_beam (viga doble T, param=grosor), pipe_elbow (codo 90°, param=radio tubo), heatsink (disipador con aletas térmicas, param=aletas), flange (brida circular perforada, param=pernos), pyramid (pirámide de 4 caras), chamfer_cylinder (cilindro biselado en extremos, param=chaflán), threaded_rod (varilla roscada, param=pasos de rosca), slot (placa con extremos redondeados u ojal alargado), rect_tube (tubo rectangular hueco, param=espesor de pared), arc (varilla curvada o asa, param=ángulo en grados 30 a 360), knurled_cylinder (pomo o mango moleteado, param=estrías), octaprism, paraboloid, arch, dna_helix, tapered_capsule, hyperboloid, barrel, trefoil_knot, triangular_prism, pentaprism, helix_spring, fluted_column, tetrahedron, dodecahedron, icosahedron, bipyramid, conical_spring. '
    'size=[x,y,z] es la caja envolvente SIN rotar. Los cuerpos de revolución (cylinder, cone, frustum, tube, capsule, dome, hexprism) tienen su eje en Y y diámetro x (z es el diámetro en Z; si x≠z la sección es elíptica). '
    'Para un eje horizontal usa rotation=[rx,ry,rz] en grados ([90,0,0] apunta el eje a Z; [0,0,90] lo apunta a X). Signo de los giros: rx>0 baja el lado +Z; rz>0 sube el lado +X; ry>0 lleva +Z hacia +X. '
    'Un tejado a dos aguas se modela con UNA pieza gable (ry=90 si la cumbrera debe correr a lo largo de X), nunca con dos láminas inclinadas. '
    'Cada pieza puede llevar material (metal_brushed, metal_polished, metal_anodized, plastic, rubber, glass, ceramic, wood, fabric, stone, paint, emissive): elige el que se ve en la imagen y un color #rrggbb real. '
    'PROPORCIONES: fija la dimensión mayor del objeto en 8 unidades y centra el modelo cerca de [0,0,0]; mide en la imagen qué fracción de esa dimensión ocupa cada pieza y reprodúcela en size y position (valores entre -10 y 10). '
    'Respeta simetrías, alineaciones, el conteo exacto de piezas repetidas (4 aletas = 4 piezas) y los contactos: ninguna pieza flota sin apoyo salvo que la imagen muestre separación. '
    'ORIENTACIÓN Y CONTACTO: rotation gira la pieza completa sobre su centro; una placa o lámina adosada a una superficie queda plana sobre ella y no se rota 90° salvo que la imagen la muestre de canto. '
    'Una pieza adosada toca a su vecina: position = centro de la vecina + la mitad del tamaño de ambas a lo largo del eje de contacto. Un eje horizontal que atraviesa una tapa se centra en el eje de esa tapa. '
    'COMPONENTES DEL CATÁLOGO: primero analiza las piezas que necesitas; si una coincide con el catálogo (tornillos, tuercas, arandelas, rodamientos, engranajes, poleas, muelles, perfiles, bridas, bisagras, terminales…) DEBES referirla con {"id":"o5","label":"…","component":"<id>","scale":1,"position":[x,y,z],"rotation":[rx,ry,rz],"color":"#rrggbb","material":"…"} sin shape ni size, y ajusta scale, position, rotation, color y material: Axx la expande en piezas reales y tú gastas menos tokens. Solo lo que no exista en el catálogo se construye con primitivas. '
    'Cuando construyas con primitivas un componente técnico reconocible de 2 o más piezas, dale a todas ellas el mismo group con su nombre técnico (p. ej. "Tornillo M4") para poder reutilizarlo. '
    'Modela también los detalles pequeños (tornillos, orificios, ranuras, conectores, juntas, nervaduras) como piezas propias con size mínimo 0.05; usa entre 8 y 32 piezas según la complejidad real del objeto. '
    'La imagen es una proyección: la profundidad que no se ve se estima con proporciones típicas y se declara como inferred. '
    'El último paso se titula «Proporciones y límites»: indica las relaciones usadas (p. ej. largo:diámetro) y lo que no se pudo determinar. '
    'En scene.objects usa ids o1, o2, etc.; focus y arrows deben referir esos mismos ids. '
    'Para objetos técnicos, compón la escena con piezas distinguibles, uniones y ejes de movimiento explicables; usa colores diferentes para identificar funciones y una vista despiezada útil. Evita adornos que aparenten especificaciones no observadas. '
    'Añade diagram con nodos d1..d16, bounds=[x,y,ancho,alto] normalizados y edges que refieran nodos existentes. Si hay scene, un nodo puede llevar object_id con el id de la pieza 3D que representa: al pulsarlo se enfoca esa pieza. '
    'Añade overlays solo sobre la selección: hasta 16 flechas, cajas, etiquetas o tarjetas vinculadas a step_id; photo=true muestra el recorte seleccionado. '
    'Usa focus solo cuando el paso tenga objetos 3D reales de scene o asset; debe ser una lista de hasta 8 ids únicos existentes. '
    'Si preguntan dónde está algo, dibuja un overlay kind="box" en s1 sobre sus límites visibles dentro de la selección; '
    'si no puedes ubicarlo con confianza, di que no lo encuentras y no dibujes una marca inventada. '
    'Si piden un diagrama, incluye diagram; si piden 3D y el objeto admite una explicación espacial útil, incluye scene o asset conceptual. '
    'Para matemáticas, texto, software o pantallas omite scene: '
    'no uses 3D solo por ser vistoso. La escena es conceptual: no inventes geometría interna, dimensiones exactas ni conexiones. '
    'Nunca incluyas HTML, código ni enlaces.'
    ' Construye siempre tu propia scene a partir de lo observado; no uses el campo asset ni ensamblajes predefinidos. '
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
    '{"op":"object.update","object_id":"o1","label":"…","color":"#rrggbb","position":[x,y,z],"size":[x,y,z],"rotation":[rx,ry,rz],"material":"…","param":0.3},{"op":"object.add","object":{"id":"o15","label":"…","shape":"…","size":[x,y,z],"position":[x,y,z],"color":"#rrggbb","rotation":[rx,ry,rz],"material":"…","param":0.3}},{"op":"object.remove","object_id":"o4"}]}. '
    'Incluye solo las operaciones necesarias (0 a 16); en las actualizaciones omite los campos que no cambian. '
    'object.update, object.add y object.remove solo existen si la presentación tiene scene; usa object.add con un id nuevo para piezas que falten y object.remove para sobrantes. '
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


def _clean_object(obj):
    """Drop optional nulls, map shape synonyms, fix colors and clamp vectors of one model-proposed object."""
    if not isinstance(obj, dict):
        return
    for opt in ('rotation', 'explode', 'material', 'param', 'group', 'component', 'scale'):
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
                if isinstance(op, dict) and op.get('op') == 'object.add':
                    _clean_object(op.get('object'))
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
    if 'fidelity' not in scene:  # some models put it on the plan instead of the scene; the value they gave is reused, otherwise the stated default
        scene['fidelity'] = result['fidelity'] if result.get('fidelity') in SCENE_FIDELITY else 'conceptual'
    objects = scene.get('objects')
    if not isinstance(objects, list) or not 1 <= len(objects) <= MAX_OBJECTS:
        return result
    for obj in objects:
        _clean_object(obj)
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
    for node in (result.get('diagram') or {}).get('nodes', []) if isinstance(result.get('diagram'), dict) else []:
        if isinstance(node, dict) and 'object_id' in node:
            if node['object_id'] in mapping:
                node['object_id'] = mapping[node['object_id']]
            else:
                node.pop('object_id')  # an unknown link is dropped; the node still links to its step
    if isinstance(result.get('steps'), list):
        for step in result['steps']:
            if isinstance(step, dict) and isinstance(step.get('focus'), list):
                if all(isinstance(value, str) and value in mapping for value in step['focus']):
                    step['focus'] = [mapping[value] for value in step['focus']]
                else:
                    step.pop('focus')
    return result

def patch_contract(registry=None):
    """PATCH_CONTRACT plus the component catalog, so corrections can add catalog parts instead of rebuilding them from primitives."""
    return (PATCH_CONTRACT + ' En object.add puedes referir una pieza del catálogo con {"op":"object.add","object":{"id":"o15","label":"…","component":"<id>","scale":1,'
            '"position":[x,y,z],"rotation":[rx,ry,rz],"color":"#rrggbb","material":"…"}} sin shape ni size; Axx la expande. Para tornillos, tuercas, arandelas, rodamientos, '
            'engranajes, poleas, muelles, perfiles, bridas o bisagras DEBES usar el catálogo. Catálogo de componentes disponibles: ' + component_catalog(registry or ShapeRegistry()) + '.')


def plan_contract(registry=None):
    """PLAN_CONTRACT plus the live component catalog (built-ins and learned shapes). The stable prefix of every request."""
    return PLAN_CONTRACT + ' Catálogo de componentes disponibles: ' + component_catalog(registry or ShapeRegistry()) + '.'


def output_schema(kind='presentation', *, strict=False, require_scene=False):
    """Small strict JSON Schema for provider-constrained output; Python remains authoritative.

    require_scene makes the 3D scene mandatory for an explicit 3D request, so the model cannot answer with a 2D diagram only."""
    text = {'type': 'string'}
    vector = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3}
    step = {'type': 'object', 'additionalProperties': False,
            'properties': {'id': text, 'title': text, 'body': text, 'narration': text,
                           'basis': {'type': 'string', 'enum': list(BASIS)},
                           'focus': {'type': 'array', 'items': text}},
            'required': ['id', 'title', 'body', 'narration', 'basis']}
    obj = {'type': 'object', 'additionalProperties': False,
           'properties': {'id': text, 'label': text, 'shape': {'type': 'string', 'enum': list(SHAPES)},
                          'size': vector, 'position': vector, 'color': text, 'rotation': vector, 'explode': vector,
                          'material': {'type': 'string', 'enum': list(MATERIALS)}, 'param': {'type': 'number'},
                          'component': text, 'scale': {'type': 'number'}, 'group': text},
           'required': ['id', 'label', 'position', 'color']}  # shape/size are optional only for catalog references; Python still requires them after expansion
    bounds = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 4, 'maxItems': 4}
    point = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}
    diagram = {'type': 'object', 'additionalProperties': False, 'properties': {
        'nodes': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
            'properties': {'id': text, 'label': text, 'step_id': text, 'bounds': bounds, 'object_id': text}, 'required': ['id', 'label', 'step_id', 'bounds']}},
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
                               'steps': {'type': 'array', 'items': step}, 'scene': scene, 'diagram': diagram, 'overlays': overlays},
                # No `asset`: presets are no longer offered, and with it Anthropic rejects the grammar as too large (verified live).
                # validate_plan still accepts `asset` so stored plans keep opening.
                'required': ['schema_version', 'kind', 'title', 'summary', 'fidelity', 'steps', *(['scene'] if require_scene else [])]}
        return _strict_schema(schema) if strict else schema
    if kind == 'patch':
        op = {'type': 'object', 'additionalProperties': False,
              'properties': {'op': {'type': 'string', 'enum': ['step.update', 'step.insert_after', 'step.remove', 'object.update', 'object.add', 'object.remove']},
                             'step_id': text, 'step': step, 'object_id': text, 'object': obj,
                             'title': text, 'body': text, 'narration': text, 'basis': text, 'focus': {'type': 'array', 'items': text},
                             'label': text, 'shape': text, 'size': vector, 'position': vector, 'color': text,
                             'rotation': vector, 'explode': vector,
                             'material': {'type': 'string', 'enum': list(MATERIALS)}, 'param': {'type': 'number'}}, 'required': ['op']}
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
    _closed(obj, ('id', 'label', 'shape', 'size', 'position', 'color'), ('rotation', 'explode', 'material', 'param', 'group'), name='Objeto')
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
    if obj.get('material') is not None:
        if obj['material'] not in MATERIALS:
            raise PlanError('material no permitido.')
        result['material'] = obj['material']
    if obj.get('group') is not None:
        result['group'] = _text(obj['group'], 'group', 80)
    if obj.get('param') is not None:
        if type(obj['param']) not in (int, float) or not math.isfinite(obj['param']) or not 0 <= obj['param'] <= 1:
            raise PlanError('param debe ser un número entre 0 y 1.')
        result['param'] = float(obj['param'])
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


def _diagram(value, steps, object_ids=()):
    _closed(value, ('nodes', 'edges'), name='Diagrama')
    if not isinstance(value['nodes'], list) or not 2 <= len(value['nodes']) <= 16:
        raise PlanError('El diagrama admite entre 2 y 16 nodos.')
    nodes, ids = [], set()
    for node in value['nodes']:
        _closed(node, ('id', 'label', 'step_id', 'bounds'), ('object_id',), name='Nodo')
        if node.get('object_id') is not None and node['object_id'] not in object_ids:
            raise PlanError('object_id de un nodo debe nombrar una pieza existente de la escena.')
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
    if diagram_overlaps(nodes):
        nodes = layout_diagram(nodes, edges)  # the model's own bounds overlapped: lay the flow out deterministically
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
    if plan.get('diagram') is not None: result['diagram'] = _diagram(plan['diagram'], step_ids, {o['id'] for o in result.get('scene', {}).get('objects', [])})
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


def apply_patch(plan, patch, *, min_steps=2, registry=None):
    """Apply a whitelisted patch to a valid plan; the result is revalidated as a whole."""
    _closed(patch, ('schema_version', 'kind', 'answer', 'ops'), name='Patch')
    if patch['schema_version'] != SCHEMA_VERSION or patch['kind'] != 'patch':
        raise PlanError('Versión o tipo de patch no compatible.')
    answer = _text(patch['answer'], 'answer', 600)
    ops = patch['ops']
    if not isinstance(ops, list) or len(ops) > MAX_OPS:
        raise PlanError(f'El patch admite hasta {MAX_OPS} operaciones.')
    result = copy.deepcopy(plan)
    added_refs = {}  # catalog reference id -> ids of the parts it expanded to, so later steps can focus them
    patch_normalized = normalize_model_focus(normalize_model_object_ids(copy.deepcopy(patch)))
    for op in patch_normalized.get('ops', ops):
        kind = op.get('op') if isinstance(op, dict) else None
        if kind == 'object.add':
            _closed(op, ('op', 'object'), name='object.add')
            if 'scene' not in result:
                raise PlanError('object.add solo existe si la presentación tiene scene.')
            objects = result['scene']['objects']
            if isinstance(op['object'], dict) and 'component' in op['object']:
                reference = dict(op['object'])
                try:
                    combined = expand_component_refs(objects + [reference], registry or ShapeRegistry(), max_objects=MAX_OBJECTS)
                except ValueError as exc:
                    raise PlanError(str(exc)) from None
                new_parts = [_fit_part(o) for o in combined if 'axx_component' in o]
                for part in new_parts:
                    part.pop('axx_component')
                    objects.append(_object(part))
                added_refs[reference.get('id', reference['component'])] = [o['id'] for o in new_parts]
                continue
            added = _object(op['object'])  # full validation of the new part
            if any(o['id'] == added['id'] for o in objects) or len(objects) >= MAX_OBJECTS:
                raise PlanError('object.add necesita un id nuevo y no superar el máximo de piezas.')
            objects.append(added)
            continue
        if kind == 'object.remove':
            _closed(op, ('op', 'object_id'), name='object.remove')
            objects = result.get('scene', {}).get('objects', [])
            if not any(o['id'] == op['object_id'] for o in objects) or len(objects) <= 1:
                raise PlanError('object.remove necesita una pieza existente y deja al menos una.')
            result['scene']['objects'] = [o for o in objects if o['id'] != op['object_id']]
            result['scene']['arrows'] = [a for a in result['scene'].get('arrows', []) if op['object_id'] not in (a['from'], a['to'])]
            for step in result['steps']:
                if op['object_id'] in step.get('focus', ()):
                    step['focus'] = [i for i in step['focus'] if i != op['object_id']]
                    if not step['focus']:
                        step.pop('focus')
            continue
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
            if isinstance(changes.get('focus'), list):
                changes['focus'] = _remap(changes['focus'], added_refs)[:8]
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


def prune_invalid_overlays(plan):
    """Annotations are optional decoration: an invalid one is dropped and reported instead of rejecting a valid plan.

    Returns (plan, notes). Nothing is dropped silently, and the structure of everything else stays strictly validated.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get('overlays'), list):
        return plan, []
    steps = {s.get('id') for s in plan.get('steps', []) if isinstance(s, dict)}
    kept, notes, seen = [], [], set()
    for item in plan['overlays']:
        label = str(item.get('text', ''))[:40] if isinstance(item, dict) else ''
        try:
            _overlays([item], steps)
            if item['id'] in seen:
                raise PlanError('id de anotación repetido.')
        except (PlanError, KeyError, TypeError) as exc:
            notes.append(f'Se descartó una anotación{" («" + label + "»)" if label else ""}: {exc}')
            continue
        seen.add(item['id'])
        kept.append(item)
    if not notes:
        return plan, []
    result = dict(plan)
    if kept:
        result['overlays'] = kept
    else:
        result.pop('overlays')
    return result, notes


def _fit_part(part):
    """Catalog parts may fall outside the validator's ranges after scaling; clamp like the model-output normalizer does."""
    part['size'] = [round(max(.05, min(10., v)), 4) for v in part['size']]
    part['position'] = [round(max(-10., min(10., v)), 4) for v in part['position']]
    part['label'] = part['label'][:80]
    return part


def _remap(ids, mapping):
    out = []
    for item in ids:
        for new in mapping.get(item, [item]):
            if new not in out:
                out.append(new)
    return out


def expand_components(plan, registry):
    """Replace {'component': id, ...} scene objects by their real parts and keep focus, arrows and diagram links valid.

    Runs before validation. The original plan is never mutated. Raises PlanError for unknown components or when the
    expanded scene would exceed MAX_OBJECTS.
    """
    scene = plan.get('scene') if isinstance(plan, dict) else None
    objects = scene.get('objects') if isinstance(scene, dict) else None
    if not isinstance(objects, list) or not any(isinstance(o, dict) and 'component' in o for o in objects):
        return plan
    result = copy.deepcopy(plan)
    try:
        expanded = expand_component_refs(result['scene']['objects'], registry, max_objects=MAX_OBJECTS)
    except ValueError as exc:
        raise PlanError(str(exc)) from None
    mapping = {}
    for obj in expanded:
        ref = obj.pop('axx_component', None)  # the marker never reaches the closed schema
        if ref is not None:
            _fit_part(obj)
            mapping.setdefault(ref, []).append(obj['id'])
    result['scene']['objects'] = expanded
    for step in result.get('steps', []) if isinstance(result.get('steps'), list) else []:
        if isinstance(step, dict) and isinstance(step.get('focus'), list):
            step['focus'] = _remap(step['focus'], mapping)[:8]
    arrows = []
    for arrow in result['scene'].get('arrows') or []:
        if isinstance(arrow, dict):
            src, dst = _remap([arrow.get('from')], mapping)[0], _remap([arrow.get('to')], mapping)[0]
            if src != dst:
                arrows.append({**arrow, 'from': src, 'to': dst})
    if 'arrows' in result['scene']:
        result['scene']['arrows'] = arrows
    nodes = result.get('diagram', {}).get('nodes') if isinstance(result.get('diagram'), dict) else None
    for node in nodes or []:
        if isinstance(node, dict) and node.get('object_id') in mapping:
            node['object_id'] = mapping[node['object_id']][0]
    return result


GENERIC_GROUPS = {'pieza', 'parte', 'componente', 'objeto', 'grupo', 'detalle', 'detalles', 'piezas', 'conjunto', 'elemento', 'accesorio'}
MAX_LEARNED = 200


def learn_groups(plan, registry):
    """Store recognizable technical components the model built from primitives (>=2 pieces sharing one group).

    Every stored piece passes the same _object rules as a scene piece; anything invalid or already known is skipped.
    Never raises: learning must not break a valid answer. Returns the ids stored.
    """
    stored = []
    try:
        groups = {}
        for obj in (plan.get('scene') or {}).get('objects', []):
            grp = obj.get('group')
            if not grp and ('·' in obj.get('label', '') or ' - ' in obj.get('label', '')):
                prefix = re.split(r'[·\-]', obj['label'])[0].strip()
                if len(prefix) >= 4 and len(prefix.split()) >= 2:
                    grp = prefix
            if grp:
                groups.setdefault(grp.strip(), []).append(obj)
        for name, parts in groups.items():
            slug = re.sub(r'[^a-z0-9]+', '_', _plain(name)).strip('_')[:40]
            # a reusable component has a technical designation: two or more words or a number; a bare "Motor" or "Soporte" is not one
            if (len(parts) < 2 or len(name) < 4 or not slug or slug in GENERIC_GROUPS or name.lower() in GENERIC_GROUPS
                    or (len(name.split()) < 2 and not re.search(r'\d', name))
                    or registry.has_shape(slug) or registry.match_shape(name) or len(registry._dynamic) >= MAX_LEARNED):
                continue
            lo = [min(o['position'][i] - o['size'][i] / 2 for o in parts) for i in range(3)]
            hi = [max(o['position'][i] + o['size'][i] / 2 for o in parts) for i in range(3)]
            center = [(lo[i] + hi[i]) / 2 for i in range(3)]
            defined = []
            for o in parts:
                part = {'label': o['label'], 'shape': o['shape'], 'size': list(o['size']),
                        'position': [round(o['position'][i] - center[i], 4) for i in range(3)],
                        'material': o.get('material', 'metal_brushed'), 'color': o['color']}
                if o.get('rotation'):
                    part['rotation'] = list(o['rotation'])
                if 'param' in o:
                    part['param'] = o['param']
                _object({'id': 'o1', **part})  # PlanError -> the whole group is skipped
                defined.append(part)
            registry.register_dynamic_shape(slug, {'label': name, 'category': 'learned', 'aliases': [name.lower(), slug],
                'size': [round(hi[i] - lo[i], 4) for i in range(3)], 'parts': defined})
            stored.append(slug)
        # If no explicit groups were defined, learn the full assembly if the plan title is a technical multi-word object
        if not groups and plan.get('title'):
            title = plan.get('title', '').strip()
            scene_objs = (plan.get('scene') or {}).get('objects', [])
            title_slug = re.sub(r'[^a-z0-9]+', '_', _plain(title)).strip('_')[:40]
            if (len(scene_objs) >= 2 and len(title) >= 4 and len(title.split()) >= 2
                    and title_slug and title_slug not in GENERIC_GROUPS and title.lower() not in GENERIC_GROUPS
                    and not registry.has_shape(title_slug) and not registry.match_shape(title)
                    and len(registry._dynamic) < MAX_LEARNED):
                lo = [min(o['position'][i] - o['size'][i] / 2 for o in scene_objs) for i in range(3)]
                hi = [max(o['position'][i] + o['size'][i] / 2 for o in scene_objs) for i in range(3)]
                center = [(lo[i] + hi[i]) / 2 for i in range(3)]
                defined = []
                for o in scene_objs:
                    part = {'label': o['label'], 'shape': o['shape'], 'size': list(o['size']),
                            'position': [round(o['position'][i] - center[i], 4) for i in range(3)],
                            'material': o.get('material', 'metal_brushed'), 'color': o['color']}
                    if o.get('rotation'):
                        part['rotation'] = list(o['rotation'])
                    if 'param' in o:
                        part['param'] = o['param']
                    _object({'id': 'o1', **part})
                    defined.append(part)
                registry.register_dynamic_shape(title_slug, {'label': title, 'category': 'learned_scene',
                    'aliases': [title.lower(), title_slug], 'size': [round(hi[i] - lo[i], 4) for i in range(3)],
                    'parts': defined})
                stored.append(title_slug)
    except Exception:
        pass
    return stored


NUMBER_WORDS = {'un': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'doce': 12}


def _plain(text):
    return ''.join(c for c in __import__('unicodedata').normalize('NFD', str(text).lower()) if __import__('unicodedata').category(c) != 'Mn')


def _rotation_matrix(rotation):
    """three.js Euler order XYZ in degrees: R = Rx * Ry * Rz."""
    rx, ry, rz = (math.radians(v) for v in (rotation or (0, 0, 0)))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    return [[cy * cz, -cy * sz, sy],
            [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
            [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]]


def _half_extents(obj):
    matrix = _rotation_matrix(obj.get('rotation'))
    return [sum(abs(matrix[i][j]) * obj['size'][j] / 2 for j in range(3)) for i in range(3)]


def check_plan(plan, *, touch=.12, limit=6):
    """Local sanity checks on a validated plan. They only warn; nothing is corrected silently and no model is called."""
    scene = plan.get('scene') if isinstance(plan, dict) else None
    if not isinstance(scene, dict) or not scene.get('objects'):
        return []
    objects, warnings = scene['objects'], []
    steps = plan.get('steps') or []
    first = next((st for st in steps if st['id'] == 's1'), steps[0] if steps else None)
    if first:
        text = _plain(first['title'] + ' ' + first['body'])
        for match in re.finditer(r'\b(\d{1,2}|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|doce)\s+([a-z]{5,})', text):
            count = int(match.group(1)) if match.group(1).isdigit() else NUMBER_WORDS[match.group(1)]
            stem = match.group(2)[:5]
            have = sum(1 for o in objects if stem in _plain(o['label']))
            if have and have < count:  # more parts than the text says is normal for a multi-piece component; fewer means pieces are missing
                warnings.append(f'El paso s1 menciona {count} «{match.group(2)}» y la escena tiene {have} pieza(s) con ese nombre.')
    extents = [_half_extents(o) for o in objects]
    for o, half in zip(objects, extents):
        if any(abs(o['position'][i]) + half[i] > 10.001 for i in range(3)):
            warnings.append(f'«{o["label"]}» sobresale del volumen [-10, 10].')
        if o['shape'] in ('gable', 'wedge', 'cone', 'frustum', 'dome') and _rotation_matrix(o.get('rotation'))[1][1] < -.2:
            warnings.append(f'«{o["label"]}» queda boca abajo con su giro; revisa el signo de rotation.')
    if len(objects) > 1:
        parent = list(range(len(objects)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(objects)):
            for j in range(i + 1, len(objects)):
                gap = math.sqrt(sum(max(0., abs(objects[i]['position'][k] - objects[j]['position'][k]) - extents[i][k] - extents[j][k]) ** 2 for k in range(3)))
                if gap <= touch:
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(len(objects)):
            groups.setdefault(find(i), []).append(i)
        main = max(groups.values(), key=len)
        said_apart = [_plain(sentence) for st in steps for sentence in re.split(r'(?<=[.!?])\s+', st['body'] + ' ' + st['title']) if re.search(r'separad|aparte|independient|despiez|suelt|desmontad', _plain(sentence))]
        for members in groups.values():
            if members is not main and len(members) <= max(2, len(objects) // 6):
                stems = {_plain(w)[:5] for i in members for w in re.findall(r'[A-Za-zÁÉÍÓÚáéíóúñÑ]{5,}', objects[i]['label'])}
                if any(stem in sentence for stem in stems for sentence in said_apart):
                    continue
                names = ', '.join(f'«{objects[i]["label"]}»' for i in members[:2])
                warnings.append(f'{names} no toca(n) ninguna otra pieza (¿flota?). Si debe estar separada, indícalo en el texto.')
    return warnings[:limit]


def diagram_overlaps(nodes):
    boxes = [n['bounds'] for n in nodes]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            w, h = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]), min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            if w > 0 and h > 0 and w * h > .01 * min(a[2] * a[3], b[2] * b[3]):
                return True
    return False


def layout_diagram(nodes, edges):
    """Deterministic layered layout (flow left to right, wrapped in bands of 4 columns) with no overlaps; keeps ids, labels and links."""
    order = {n['id']: i for i, n in enumerate(nodes)}
    forward = {n['id']: [] for n in nodes}
    state = {}

    def visit(node):  # DFS in list order; edges that close a cycle are ignored for layering
        state[node] = 1
        for e in sorted((e for e in edges if e['from'] == node), key=lambda e: order[e['to']]):
            if state.get(e['to']) == 1:
                continue
            forward[node].append(e['to'])
            if e['to'] not in state:
                visit(e['to'])
        state[node] = 2
    for n in nodes:
        if n['id'] not in state:
            visit(n['id'])
    layer = {n['id']: 0 for n in nodes}
    for _ in nodes:
        for src, targets in forward.items():
            for dst in targets:
                layer[dst] = max(layer[dst], layer[src] + 1)
    layers = [[n for n in nodes if layer[n['id']] == k] for k in range(max(layer.values()) + 1)]
    layers = [group for group in layers if group]
    cols = min(len(layers), 4)
    bands = [layers[i:i + cols] for i in range(0, len(layers), cols)]
    rows_total = sum(max(len(g) for g in band) for band in bands)
    margin = .04
    cell_w, cell_h = (1 - 2 * margin) / cols, (1 - 2 * margin) / rows_total
    width, height = min(.34, cell_w * .82), min(.2, cell_h * .72)
    placed, row0 = {}, 0
    for band in bands:
        band_rows = max(len(g) for g in band)
        for c, group in enumerate(band):
            for r, node in enumerate(group):
                x = margin + c * cell_w + (cell_w - width) / 2
                y = margin + (row0 + r + (band_rows - len(group)) / 2) * cell_h + (cell_h - height) / 2
                placed[node['id']] = [round(x, 4), round(y, 4), round(width, 4), round(height, 4)]
        row0 += band_rows
    return [{**n, 'bounds': placed[n['id']]} for n in nodes]


def plain_text_diagram(text, question):
    """Bounded illustrative 2D diagram from a visual model's prose (ported from PR #4).

    Only for 2D-capable routes. It is not image grounding and never creates a 3D scene;
    JSON-looking text, code, HTML and refusals remain errors.
    """
    if not isinstance(text, str):
        raise PlanError('El modelo no devolvió texto para el diagrama 2D.')
    raw = text.strip()
    if (len(raw) < 12 or len(raw) > 32000 or '\x00' in raw
            or raw.startswith(('{', '[', '```', '<')) or any(mark in raw for mark in ('{', '}', '```'))
            or re.search(r'(?m)^\s*```|<\s*/?\s*[a-zA-Z][^>]*>', raw)
            or re.match(r'(?i)^(?:lo siento|no puedo|i cannot|i am sorry|sorry)\b', raw)):
        raise PlanError('La respuesta no contiene una explicación textual válida para el diagrama 2D.')
    clean = re.sub(r'(?m)^\s{0,3}(?:#{1,4}\s+|[-*]\s+|\d{1,2}[.)]\s+)', '', raw)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) < 12:
        raise PlanError('La explicación textual es demasiado breve.')
    chunks, current = [], ''
    for word in clean.split(' '):
        if len(word) > 360:
            raise PlanError('La respuesta contiene texto que no se puede representar de forma segura.')
        candidate = (current + ' ' + word).strip()
        if len(candidate) > 360 and current:
            chunks.append(current)
            current = word
            if len(chunks) == 4:
                break
        else:
            current = candidate
    if current and len(chunks) < 4:
        chunks.append(current)
    if not chunks:
        raise PlanError('No se encontró contenido para el diagrama.')
    if len(chunks) == 1:
        context = re.sub(r'\s+', ' ', question if isinstance(question, str) else '').strip()[:380]
        chunks.insert(0, context or 'Objeto o región seleccionada por el usuario.')
    labels = ('Contexto', 'Explicación', 'Relaciones', 'Detalles')
    steps = [{'id': f's{i+1}', 'title': labels[i], 'body': chunk, 'narration': chunk, 'basis': 'assumed'}
             for i, chunk in enumerate(chunks)]
    positions = ((.08, .17, .36, .22), (.56, .17, .36, .22), (.08, .61, .36, .22), (.56, .61, .36, .22))
    diagram = {'nodes': [{'id': f'd{i+1}', 'label': step['title'], 'step_id': step['id'], 'bounds': list(positions[i])}
                         for i, step in enumerate(steps)],
               'edges': [{'from': f'd{i}', 'to': f'd{i+1}', 'label': 'continúa'} for i in range(1, len(steps))]}
    return validate_2d_plan({'schema_version': SCHEMA_VERSION, 'kind': 'presentation', 'title': 'Diagrama de la selección',
        'summary': 'Esquema local derivado de texto del modelo; contenido no verificado contra la captura.',
        'fidelity': 'illustrative', 'steps': steps, 'diagram': diagram})


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
