"""One capability description source for Axx UI, Codex dynamic tools and MCP.

Existing CommandService entries remain authoritative for legacy executor policy.
UI entries call existing UI methods through a bounded, authenticated mailbox;
they never invoke the chat/planner or evaluate code supplied by a model.
"""
from __future__ import annotations

import copy
import math
from backend.commands import ADAPTERS, normalized
from backend.actions.tools import get_tool

VERSION = '0.1.0'


def obj(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


def string(maximum=4000, enum=None):
    result = {'type': 'string', 'maxLength': maximum}
    if enum is not None:
        result['enum'] = enum
    return result


LOCAL_ACTIONS = ['timer', 'pause', 'resume', 'cancel', 'note', 'todo', 'completeTodo',
                 'notes', 'searchNotes', 'todos', 'calculate', 'convert', 'analyze',
                 'time', 'date', 'summon', 'follow', 'stay', 'hide', 'help', 'greet']
PANEL_IDS = ['commands', 'applications', 'agent', 'stopwatch', 'textstudio', 'images', 'reach', 'chat', 'timer', 'notes', 'todos',
             'calculator', 'files', 'focus', 'appearance', 'studio', 'lab', 'audio', 'sound',
             'ai', 'settings', 'mcp', 'inbox', 'help', 'dictation', 'reader', 'translation',
             'transcript', 'morphui', 'roadmap', 'organic', 'music', 'screen', 'layout11']

# Definitions describe the existing handlers. UI availability is a live heartbeat,
# not the presence of these definitions or a saved preference.
UI_CAPABILITIES = {
    'axx.ui.identity': {
        'title': 'Identidad visual existente', 'description': 'Consulta o ajusta forma, paleta, acabado, movimiento y tamaño usando la autoridad visual actual.',
        'handler': 'Axx.stability20.updateSettings/Axx.symbiosis.applyFinish20/Axx.companion.setSize', 'risk': 'local_state',
        'input_schema': obj({'action': string(enum=['status', 'settings', 'finish', 'size']),
            'form': {'type': 'integer', 'minimum': 0, 'maximum': 23}, 'palette': {'type': 'integer', 'minimum': 0, 'maximum': 8},
            'motionStyle': string(enum=['organic', 'velvet', 'tide', 'gyre', 'breathing', 'suspended']),
            'finish': string(enum=['obsidian', 'prism', 'smoke']), 'size': {'type': 'integer', 'minimum': 160, 'maximum': 640}}, ['action']),
        'effects': 'Modifica sólo los ajustes solicitados de la identidad existente.', 'verification': 'Readback de settings, renderer y tamaño persistido.'},
    'axx.ui.local': {
        'title': 'Herramientas locales de Axx',
        'description': 'Temporizador, notas, tareas, cálculo, conversión, análisis de texto y presencia. Usa handlers locales existentes, sin inferencia.',
        'handler': 'Axx.companion.runLocal', 'risk': 'local_state',
        'input_schema': obj({'action': string(enum=LOCAL_ACTIONS), 'ms': {'type': 'integer', 'minimum': 1000, 'maximum': 86400000},
            'kind': string(enum=['timer', 'focus']), 'text': string(65536), 'index': {'type': 'integer', 'minimum': 0, 'maximum': 199},
            'value': {'type': 'number', 'minimum': -1e15, 'maximum': 1e15}, 'from': string(24), 'to': string(24)}, ['action']),
        'effects': 'Puede guardar notas/tareas, cambiar temporizador o presencia; las consultas sólo leen.',
        'verification': 'Readback de timer, notas, tareas y preferencias desde las autoridades existentes en la UI.'},
    'axx.ui.panel': {
        'title': 'Abrir panel radial', 'description': 'Abre un panel independiente existente sin cambiar la distribución radial.',
        'handler': 'Axx.companion.openFeature', 'risk': 'local_state',
        'input_schema': obj({'feature': string(enum=PANEL_IDS)}, ['feature']),
        'effects': 'Abre el panel solicitado.', 'verification': 'Panel visible y selección observados en la UI.'},
    'axx.ui.text_transform': {
        'title': 'Transformar texto', 'description': 'Transformación determinista existente; devuelve el texto y no lo envía a un chat.',
        'handler': 'Axx.transformText', 'risk': 'read',
        'input_schema': obj({'text': string(65536), 'action': string(enum=['clean', 'dedupe', 'sort', 'upper', 'lower', 'json', 'links'])}, ['text', 'action']),
        'effects': 'Calcula un resultado sin insertar ni enviar mensajes.', 'verification': 'Resultado de la función pura existente y readback de tipo/cadena.'},
    'axx.ui.music': {
        'title': 'Controlar música local', 'description': 'Controla la biblioteca local ya seleccionada por el usuario. No conecta Spotify ni descarga música.',
        'handler': 'Axx.actions.music', 'risk': 'local_state',
        'input_schema': obj({'action': string(enum=['play', 'pause', 'next', 'previous', 'select', 'shuffle', 'repeat', 'seek']),
            'index': {'type': 'integer', 'minimum': 0, 'maximum': 9999}, 'enabled': {'type': 'boolean'},
            'mode': string(enum=['off', 'all', 'one']), 'seconds': {'type': 'number', 'minimum': -86400, 'maximum': 86400}}, ['action']),
        'effects': 'Cambia reproducción local y sus preferencias.', 'verification': 'Readback de audio.paused/currentTime, índice, shuffle y repeat.'},
    'axx.ui.system_media': {
        'title': 'Controlar Spotify o Chrome en Windows',
        'description': 'Reproduce, pausa o cambia pista de una sesión multimedia de Spotify o Chrome observada por Windows. No busca ni selecciona canciones.',
        'handler': 'Axx.nativeMusic.command', 'risk': 'local_state',
        'input_schema': obj({'app': string(enum=['spotify','chrome']), 'action': string(enum=['play','pause','next','previous'])}, ['app','action']),
        'effects': 'Envía un control únicamente a la sesión identificada de la aplicación solicitada.',
        'verification': 'Readback de la misma sesión y estado de reproducción; salto de pista requiere título nuevo o se marca incierto.'},
    'axx.ui.reader': {
        'title': 'Lectura de texto', 'description': 'Utiliza el lector existente. La disponibilidad de voz depende del servicio nativo autorizado.',
        'handler': 'Axx.symbiosis.reader', 'risk': 'local_state',
        'input_schema': obj({'action': string(enum=['set_text', 'play', 'pause', 'stop', 'jump']), 'text': string(65536), 'title': string(240),
            'index': {'type': 'integer', 'minimum': 0, 'maximum': 9999}}, ['action']),
        'effects': 'Modifica texto/posición o inicia/pausa/detiene lectura.', 'verification': 'Readback del estado, texto/chunks e índice del lector real.'},
    'axx.ui.stopwatch': {
        'title': 'Cronómetro', 'description': 'Consulta, inicia, pausa o marca vueltas en el cronómetro existente.',
        'handler': 'Axx.utilities.toggleWatch/markLap', 'risk': 'local_state',
        'input_schema': obj({'action': string(enum=['status', 'start', 'pause', 'lap'])}, ['action']),
        'effects': 'Cambia el cronómetro independiente del temporizador.', 'verification': 'Readback de running, elapsed y laps del cronómetro.'},
    'axx.ui.dictation': {
        'title': 'Dictado sin enviar', 'description': 'Abre o detiene dictado; insertar transcripción es una acción separada y nunca envía el mensaje.',
        'handler': 'Axx.voice13/Axx.nativeVoice', 'risk': 'microphone',
        'input_schema': obj({'action': string(enum=['open', 'stop', 'status'])}, ['action']),
        'effects': 'Abre el panel o detiene una captura existente; comenzar micrófono requiere UI/permiso.',
        'verification': 'Readback de estado del dictado; apertura no demuestra transcripción.'},
    'axx.ui.screen': {
        'title': 'Grabación de pantalla', 'description': 'Consulta o detiene grabación existente. Iniciar/exportar requiere el selector autorizado en la interfaz.',
        'handler': 'Axx.actions.screen', 'risk': 'screen_capture',
        'input_schema': obj({'action': string(enum=['open', 'stop', 'status'])}, ['action']),
        'effects': 'Abre el panel o detiene la captura; no promete un archivo guardado.',
        'verification': 'Readback de estado y existencia/tamaño del Blob si está disponible.'},
}

# Implemented application surfaces whose autonomous adapter cannot yet prove the
# complete effect. Keep them discoverable with their actual handler and precise
# gate; a disabled descriptor is never interpreted as an executable recipe.
PENDING_CAPABILITIES = {
    'axx.ui.files.import': ('Importar archivos/datos', 'Axx UI file picker/import handlers', 'Requiere selección explícita del archivo y validación del importador en el panel Archivos.'),
    'axx.ui.files.export': ('Exportar archivos/datos', 'Axx UI export/save picker handlers', 'Requiere destino autorizado y verificación del archivo final; abrir el selector no demuestra exportación.'),
    'axx.ui.images.transform': ('Procesar imagen seleccionada', 'Axx.utilities.selectImage/image export', 'Requiere imagen seleccionada por el usuario y verificación del archivo exportado.'),
    'axx.ui.translation': ('Traducción', 'Axx.symbiosis.translate', 'El motor de proveedor llama al chat y no se expone por riesgo de recursión. Usa el panel; el motor de navegador requiere su disponibilidad real.'),
    'axx.ui.dictation.insert': ('Insertar dictado sin enviar', 'Axx.voice13.applyPending/nativeVoice insertion owner', 'Requiere destino de inserción seleccionado y readback en la aplicación de destino; enviar sigue siendo una acción independiente.'),
    'axx.ui.screen.start': ('Iniciar grabación', 'Axx.capture19.start/Axx.actions.screen', 'Requiere selector de pantalla y permiso del usuario en la UI; despacho no verifica captura.'),
    'axx.ui.screen.export': ('Guardar grabación', 'Axx.actions.screen save picker', 'Requiere destino y archivo final verificable; un Blob en memoria no es un vídeo guardado.'),
    'axx.ui.workspace': ('Disposición de paneles', 'Axx.organic.newWorkspace/arrange/fold/openDesk', 'Los métodos existen; el adaptador de mutación/readback de disposición aún no está validado.'),
    'axx.desktop.launch': ('Abrir aplicación autorizada', '/axx-api/desktop/discover/authorize/launch', 'El endpoint actual sólo devuelve dispatched y PID; falta verificación de ventana/proceso para habilitar esta capacidad autónoma.'),
    'axx.speech.synthesize': ('Síntesis nativa de voz', 'backend.speech.windows_tts.WindowsSpeechService.synthesize', 'Conectada mediante el lector nativo de Axx; exportación autónoma MCP de audio no habilitada ni verificada.'),
    'axx.speech.transcribe': ('Transcribir audio autorizado', 'backend.speech.offline_asr.OfflineTranscriptionService.transcribe', 'Conectada mediante el dictado nativo de Axx; requiere audio autorizado y disponibilidad del motor/modelo tiny existente.'),
}


def legacy_schema(parameters):
    properties, required = {}, []
    for name, rule in parameters.items():
        item = {key: value for key, value in rule.items() if key not in ('required', 'maxBytes')}
        if rule.get('maxBytes') and 'maxLength' not in item:
            item['maxLength'] = rule['maxBytes']
        properties[name] = item
        if rule.get('required'):
            required.append(name)
    return obj(properties, required)


def augment_registry(commands):
    """Extend the SAME CommandService map; MCP never keeps an executable copy."""
    for key, item in UI_CAPABILITIES.items():
        commands.commands[key] = copy.deepcopy(item) | {
            'id': key, 'category': 'Axx UI existente', 'parameters': {}, 'aliases': [],
            'execution_enabled': False, 'requires_approval': False,
            'blocked_reason': 'La UI nativa debe estar activa y confirmar disponibilidad del handler.',
            'source_status': 'IMPLEMENTADO_LOCAL', 'source': {'kind': 'ui_adapter'}}
        commands.search_index[key] = normalized(key + ' ' + item['title'] + ' ' + item['description'])
    for key, (title, handler, reason) in PENDING_CAPABILITIES.items():
        commands.commands[key] = {'id': key, 'title': title, 'handler': handler, 'description': reason,
            'category': 'Axx existente · intervención requerida', 'parameters': {}, 'input_schema': obj(),
            'aliases': [], 'execution_enabled': False, 'requires_approval': False, 'risk': 'unreviewed',
            'blocked_reason': reason, 'source_status': 'IMPLEMENTADO_LOCAL', 'source': {'kind': 'existing_unbridged'}}
        commands.search_index[key] = normalized(key + ' ' + title + ' ' + reason)


def describe(commands, entry, ui_available=False):
    result = copy.deepcopy(entry)
    key = entry['id']
    if key in UI_CAPABILITIES:
        result['execution_enabled'] = ui_available
        result['blocked_reason'] = None if ui_available else 'UI nativa sin heartbeat reciente o handler no anunciado.'
        result['dependencies'] = ['Axx UI nativa activa', entry['handler']]
    else:
        adapter = ADAPTERS.get(key)
        tool = get_tool(adapter['tool']) if adapter else None
        result['input_schema'] = entry.get('input_schema') or legacy_schema(entry.get('parameters', {}))
        result['handler'] = ('backend.actions.tools.' + tool.__class__.__name__) if tool else entry.get('handler')
        result['dependencies'] = ['Python runtime', 'Axx ActionExecutor'] if tool else ['Adaptador ejecutable validado ausente']
        result['effects'] = entry.get('description', '')
        result['verification'] = 'Tool.verify_postconditions y evidencia persistida por ActionExecutor' if tool else entry.get('blocked_reason', 'Sin verificador ejecutable')
    result['adapter_version'] = getattr(get_tool(ADAPTERS[key]['tool']), 'version', VERSION) if key in ADAPTERS else VERSION
    result['output_schema'] = obj({'operation_id': string(128), 'state': string(32), 'postconditions_passed': {'type': 'boolean'},
        'output': {}, 'evidence': {'type': 'object'}}, ['operation_id', 'state']) | {'additionalProperties': True}
    result['timeout_seconds'] = 30
    result['cancellable'] = key in UI_CAPABILITIES or key in ADAPTERS
    result['retry'] = 'Reutilizar operation_id; no repetir unknown, failed o efecto consumado automáticamente.'
    result['effective_permissions'] = 'UI approval required for workspace_write' if entry.get('requires_approval') else entry.get('risk', 'unreviewed')
    return result


def validate(schema, value, path='inputs'):
    """Small strict JSON-schema subset used by our closed registry (no coercion)."""
    kind = schema.get('type')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str),
             'integer': type(value) is int, 'number': type(value) in (int, float) and math.isfinite(value), 'boolean': type(value) is bool}
    if kind and not valid.get(kind, False):
        raise ValueError(f'{path}: tipo {kind} requerido')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: valor no permitido')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - properties.keys():
            raise ValueError(f'{path}: parámetros desconocidos')
        if set(schema.get('required', [])) - value.keys():
            raise ValueError(f'{path}: faltan parámetros requeridos')
        for key, entry in value.items():
            if key in properties:
                validate(properties[key], entry, f'{path}.{key}')
    if isinstance(value, str) and len(value) > schema.get('maxLength', 65536):
        raise ValueError(f'{path}: texto demasiado largo')
    if type(value) in (int, float) and not isinstance(value, bool):
        if value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf):
            raise ValueError(f'{path}: número fuera de límites')


def validate_ui(command_id, inputs):
    validate(UI_CAPABILITIES[command_id]['input_schema'], inputs)
    action = inputs.get('action')
    required = {'timer': ['ms'], 'note': ['text'], 'todo': ['text'], 'completeTodo': ['index'],
        'searchNotes': ['text'], 'calculate': ['text'], 'convert': ['value', 'from', 'to'], 'analyze': ['text'],
        'select': ['index'], 'shuffle': ['enabled'], 'repeat': ['mode'], 'seek': ['seconds'],
        'set_text': ['text'], 'jump': ['index']}.get(action, [])
    if any(key not in inputs for key in required):
        raise ValueError('Faltan parámetros para la acción ' + action)
    if action in ('note', 'todo', 'searchNotes', 'calculate') and not inputs['text'].strip():
        raise ValueError('El texto requerido no puede estar vacío')
    if action == 'todo' and len(inputs['text']) > 1000:
        raise ValueError('Máximo 1000 caracteres para una tarea')
    if command_id == 'axx.ui.identity':
        if action == 'settings' and not any(key in inputs for key in ('form', 'palette', 'motionStyle')):
            raise ValueError('Especifica al menos un ajuste visual')
        if action in ('finish', 'size') and action not in inputs:
            raise ValueError('Falta valor de ' + action)


def read_only_aliases():
    """Generate precise read-only names only from the authoritative adapters.

    A generic action tool includes effects with different permissions. These
    aliases let a host apply accurate read-only policy without approving or
    weakening the generic action boundary.
    """
    return {command_id.replace('.', '_'): command_id for command_id, adapter in ADAPTERS.items()
            if adapter['risk'] == 'read'}


def concrete_action_arguments(name, arguments):
    aliases = read_only_aliases()
    if name not in aliases:
        return dict(arguments)
    return {'command_id': aliases[name], 'inputs': {key: value for key, value in arguments.items() if key != 'operation_id'},
            'operation_id': arguments['operation_id']}


def tool_descriptors(commands=None, *, computer=False):
    # Five protocol tools plus generated precise aliases. All action IDs resolve
    # against the SAME registered adapter and existing execution/approval policy.
    action = obj({'command_id': string(128), 'inputs': {'type': 'object'}, 'operation_id': string(128),
        'origin': string(enum=['mcp', 'codex-host', 'axx-provider']), 'parent_execution_id': string(128),
        'delegation_depth': {'type': 'integer', 'minimum': 0, 'maximum': 1}}, ['command_id', 'inputs', 'operation_id'])
    definitions = [
        ('axx_computer_status','Consulta el alcance autorizado (escritorio completo o ventana) en ESTE chat. No captura imágenes.',obj(),True),
        ('axx_computer_observe','Recibe una imagen real, controles e identidad. En escritorio completo, sin ventana muestra el escritorio y enumera aplicaciones; con window_id y pid de esa lista enfoca y amplía cualquier aplicación permitida. En modo ventana no cambia el destino. Coordenadas en píxeles de ESTA imagen según image_bounds, nunca píxeles globales. Un árbol parcial no garantiza ausencia de controles.',obj({'operation_id':string(128),'window_id':{'type':'integer','minimum':1},'pid':{'type':'integer','minimum':1}},['operation_id']),True),
        ('axx_computer_act','Opera el último destino observado mediante el dueño de entrada de Axx. Usa control_id o coordenadas de la imagen vigente. Salvo move, expected debe incluir name y opcional value/present/focused, o region_changed [left,top,right,bottom] de la imagen. Un cambio de región NO verifica el objetivo: observa después y compruébalo visualmente. Si queda unknown, pide revisión y no repitas. Cada gesto consume la observación; observa siempre antes del siguiente.',obj({
            'operation_id':string(128),'observation_id':string(80),'action':string(enum=['move','click','double_click','right_click','drag','scroll','hotkey','type_text']),
            'control_id':string(64),**{k:{'type':'integer','minimum':0,'maximum':100000} for k in ('x','y','to_x','to_y')},
            **{k:{'type':'integer','minimum':-2000,'maximum':2000} for k in ('delta_x','delta_y')},
            'keys':{'type':'array','minItems':1,'maxItems':4,'items':string(30)},'text':string(512),
            'expected':obj({'name':string(200),'value':string(8192),'present':{'type':'boolean'},'focused':{'type':'boolean'},'region_changed':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'integer','minimum':0,'maximum':1280}}})},['operation_id','observation_id','action']),False),
        ('axx_computer_stop','Revoca el computer use de este chat y detiene su entrada. No revierte los efectos realizados.',obj(),False),
        ('axx_status', 'Estado real del ejecutor local y disponibilidad de Axx. Autenticación e inferencia se verifican por separado.', obj(), True),
        ('axx_list_capabilities', 'Busca el registro único; conserva comandos documentados no ejecutables con su motivo. Consulta antes de ejecutar.', obj({'query': string(500), 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'offset': {'type': 'integer', 'minimum': 0, 'maximum': 20000}}), True),
        ('axx_execute_action', 'Ejecuta una capacidad concreta con operation_id idempotente. Las escrituras esperan aprobación en Axx. No llama al chat ni al planificador. Consulta la tarea hasta verificar el resultado.', action, False),
        ('axx_get_task', 'Lee progreso, evidencia y estado de una tarea por operation_id. Un timeout o unknown no autoriza repetir efectos.', obj({'operation_id': string(128)}, ['operation_id']), True),
        ('axx_cancel_task', 'Detiene acciones pendientes y solicita cancelación. No revierte efectos consumados; revisa el resultado.', obj({'operation_id': string(128)}, ['operation_id']), False),
    ]
    if not computer:definitions=[row for row in definitions if not row[0].startswith('axx_computer_')]
    for name, command_id in read_only_aliases().items():
        adapter = ADAPTERS[command_id]
        schema = legacy_schema(adapter['parameters'])
        if 'operation_id' in schema['properties']:
            raise ValueError('El parámetro reservado operation_id colisiona con el adaptador')
        schema['properties']['operation_id'] = string(128)
        schema['required'].append('operation_id')
        definitions.append((name, adapter['description'] + ' Operación de consulta sin escritura. '
            'Reutiliza operation_id para reintentos y consulta axx_get_task hasta verificar el resultado.', schema, True))
    return [{'name': name, 'description': description, 'inputSchema': schema,
             'annotations': {'readOnlyHint': read, 'destructiveHint': not read, 'idempotentHint': True, 'openWorldHint': False}}
            for name, description, schema, read in definitions]


def dynamic_tools(commands=None, *, computer=False):
    return [{'type': 'namespace', 'name': 'axx',
             'description': 'Herramientas de Axx con permisos y verificación del ejecutor local.',
             'tools': [{'type': 'function', 'name': entry['name'], 'description': entry['description'],
                        'inputSchema': entry['inputSchema'], 'deferLoading': False}
                       for entry in tool_descriptors(commands, computer=computer)]}]
