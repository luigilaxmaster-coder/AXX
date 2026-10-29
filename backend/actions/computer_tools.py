"""Registered desktop primitives over the existing executor and input owner."""
import threading


TARGET = {'window_id': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 9223372036854775807},
          'pid': {'type': 'integer', 'required': True, 'minimum': 1, 'maximum': 4294967295}}
OBSERVATION = {'observation_id': {'type': 'string', 'required': True, 'maxLength': 80}}


def adapter(title, tool, risk, parameters, description, aliases=None):
    return dict(title=title, tool=tool, risk=risk, parameters=parameters,
                description=description, aliases=aliases or [])


ADAPTERS = {
    'axx.desktop.window.select': adapter('Seleccionar ventana única', 'computer_window', 'read',
        {'title': {'type':'string','required':True,'maxLength':2048},
         'process_name': {'type':'string','maxLength':260}},
        'Selecciona una ventana visible por título exacto y proceso opcional. Rechaza duplicados y listas incompletas; devuelve HWND entero y hexadecimal sin cambiar el foco.'),
    'axx.desktop.ground': adapter('Enviar imagen y proponer objetivo visual', 'computer_ground', 'external_content',
        TARGET | OBSERVATION | {'goal': {'type':'string','required':True,'maxLength':1000},
            'provider_name': {'type':'string','required':True,'maxLength':80},
            'model': {'type':'string','required':True,'maxLength':200},
            'image_authorized': {'type':'boolean','required':True}},
        'Envía únicamente la imagen de la ventana autorizada al proveedor visual gratuito seleccionado. Devuelve propuesta sin ejecutar entrada; exige imagen fresca e idéntica al terminar.'),
    'axx.desktop.ocr': adapter('Leer texto de ventana con OCR local', 'computer_ocr', 'local_content_read', TARGET | OBSERVATION,
        'Recorte de ventana capturada, fresco e idéntico después de OCR latino local. Devuelve texto/cajas como contenido no verificado semánticamente; no hace clic ni envía imágenes.'),
    'axx.desktop.window.observe': adapter('Observar geometría de ventana', 'desktop_window_observe', 'read', TARGET,
        'Observa identidad, sesión, geometría y estado minimizado sin leer contenido. Permite preparar una restauración con referencia fresca.'),
    'axx.desktop.observe': adapter('Observar escritorio y ventana', 'computer_observe', 'local_content_read',
        TARGET | {'monitor_id': {'type': 'string', 'maxLength': 100}},
        'Observación fresca con UIA, foco, proceso, geometría y monitores. Captura local opcional mediante monitor_id; no envía imágenes al modelo.'),
    'axx.desktop.control.find': adapter('Localizar control único', 'computer_find', 'local_content_read',
        TARGET | {'name': {'type': 'string', 'required': True, 'maxLength': 500},
                  'pattern': {'type': 'string', 'maxLength': 30}},
        'Observa y devuelve un control habilitado único por nombre exacto y patrón opcional. Se abstiene ante ausencia, duplicados o truncamiento.'),
    'axx.desktop.state': adapter('Establecer estado de control', 'computer_state', 'local_state',
        TARGET | OBSERVATION | {'control_id': {'type': 'string', 'required': True, 'maxLength': 64},
        'pattern': {'type': 'string', 'required': True, 'enum': ['Toggle', 'ExpandCollapse', 'SelectionItem', 'RangeValue', 'Scroll', 'Value']},
        'state': {'type': 'object', 'required': True}},
        'Establece el estado {"value":...} de un control recién observado y comprueba lectura posterior. No alterna a ciegas.'),
    'axx.desktop.input': adapter('Entrada sobre ventana observada', 'computer_input', 'local_state',
        TARGET | OBSERVATION | {'action': {'type': 'string', 'required': True,
            'enum': ['move', 'click', 'double_click', 'right_click', 'drag', 'scroll', 'hotkey', 'type_text']},
            **{name: {'type': 'integer', 'minimum': -1000000, 'maximum': 1000000} for name in ('x','y','to_x','to_y','delta_x','delta_y')},
            'keys': {'type': 'array', 'minItems': 1, 'maxItems': 4, 'items': {'type': 'string', 'maxLength': 30}},
            'text': {'type': 'string', 'maxLength': 512}},
        'Requiere observación vigente y foco exacto; usa el mismo broker que el móvil. Clic/teclas sólo acreditan entrega y dejan el efecto incierto.'),
    'axx.desktop.window.state': adapter('Estado y geometría de ventana', 'desktop_window_state', 'local_state',
        TARGET | OBSERVATION | {'action': {'type':'string','required':True,'enum':['restore','minimize','maximize','move_resize']},
                               'bounds': {'type':'object'}},
        'Restaura, minimiza, maximiza o mueve una ventana recién observada; verifica estado o rectángulo físico. No cierra documentos.'),
    'axx.desktop.grid.read': adapter('Leer tabla accesible', 'computer_grid', 'local_content_read',
        TARGET | OBSERVATION | {'control_id': {'type':'string','required':True,'maxLength':64},
            **{name: {'type':'integer','minimum':0,'maximum':100000} for name in ('row','column')},
            **{name: {'type':'integer','minimum':1,'maximum':20} for name in ('rows','columns')}},
        'Lee un rango limitado de Grid/Table de un control observado; no modifica celdas ni exporta contenido al modelo.'),
    'axx.file.find': adapter('Buscar archivos locales', 'file_find', 'local_file_read',
        {'directory': {'type': 'string', 'required': True, 'maxLength': 240},
         'pattern': {'type': 'string', 'maxLength': 100}, 'recursive': {'type': 'boolean'},
         'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
         'max_entries_scan': {'type': 'integer', 'minimum': 1, 'maximum': 10000}},
        'Búsqueda acotada por carpeta y patrón; no sigue enlaces ni recorre todo el disco.'),
    'axx.file.bundle': adapter('Copiar archivos y crear entrega ZIP', 'file_bundle', 'workspace_write',
        {'paths': {'type': 'array', 'required': True, 'minItems': 1, 'maxItems': 100,
                   'items': {'type': 'string', 'maxLength': 240}},
         'destination': {'type': 'string', 'required': True, 'maxLength': 180},
         'archive_name': {'type': 'string', 'maxLength': 100},
         'max_output_bytes': {'type': 'integer', 'minimum': 1, 'maximum': 1073741824}},
        'Copia archivos elegidos a una carpeta nueva en artifacts, conserva originales y verifica hashes, manifiesto y ZIP opcional. Nunca sobrescribe.'),
    'axx.office.excel.csv': adapter('Importar CSV y verificar Excel', 'office_excel_csv', 'workspace_write',
        {'source': {'type':'string','required':True,'maxLength':240},
         'destination': {'type':'string','required':True,'maxLength':180},
         'delimiter': {'type':'string','required':True,'enum':[',',';','\t']},
         'numeric_column': {'type':'string','required':True,'maxLength':200}},
        'Abre una instancia privada de Excel, importa CSV acotado, genera SUM y guarda una copia XLSX nueva. Reabre y comprueba celdas y total; conserva el CSV.'),
}
from .process_runner import PARAMETERS as PROCESS_PARAMETERS
ADAPTERS['axx.ifc.inventory.csv'] = adapter('Inventariar IFC a CSV', 'ifc_inventory_csv', 'workspace_write',
    {'source': {'type': 'string', 'required': True, 'maxLength': 240},
     'destination': {'type': 'string', 'required': True, 'maxLength': 180}},
    'IFC local de hasta 40 MiB/500 elementos. Conserva GUID y unidad declarada; CSV nuevo con Count para Excel. No calcula cantidades geométricas ni valida un modelo CAD anfitrión.')
for kind in ('pdf', 'media', 'ocr'):
    ADAPTERS['axx.artifact.' + kind] = adapter('Comprobar archivo ' + kind, 'artifact_' + kind, 'local_file_read',
        {'path': {'type': 'string', 'required': True, 'maxLength': 240}},
        'Inspección local acotada con hash. PDF: páginas, dimensiones y texto; multimedia: duración y pistas ffprobe. No acredita render visual ni decodificación completa.')
ADAPTERS['axx.process.run'] = adapter('Ejecutar proceso explícito', 'process_run', 'system_command',
    {name: dict(schema, required=name in PROCESS_PARAMETERS['required']) for name, schema in PROCESS_PARAMETERS['properties'].items()},
    'Sólo para una petición explícita de terminal: ejecutable .exe y argumentos literales revisados. Controla su árbol propio y verifica salida y artefacto nuevo opcional; código cero no demuestra el efecto.')
ADAPTERS['axx.office.word.pdf'] = adapter('Crear copia Word y PDF', 'office_word_pdf', 'workspace_write',
    {'source': {'type':'string','required':True,'maxLength':240},
     'destination': {'type':'string','required':True,'maxLength':180},
     'append_text': {'type':'string','required':True,'maxLength':10000}},
    'Con Word cerrado, abre una copia privada del DOCX, añade texto literal y genera DOCX/PDF nuevos en artifacts. Verifica texto y páginas y conserva el original.')
ADAPTERS['axx.blender.scene.render'] = adapter('Editar copia Blender y renderizar', 'blender_scene_render', 'workspace_write',
    {name:{'type':'string','required':True,'maxLength':240} for name in ('source','destination','scene','camera','object')}
    | {'position':{'type':'array','required':True,'minItems':3,'maxItems':3,'items':{'type':'number'}},
       'width':{'type':'integer','required':True,'minimum':64,'maximum':2048}, 'height':{'type':'integer','required':True,'minimum':64,'maximum':2048}},
    'Copia local sin autoejecutar scripts; escena, cámara y objeto estático exactos. Cambia posición, guarda copia y render PNG con dimensiones verificadas. Sin librerías vinculadas, compositor ni secuenciador.')
ADAPTERS['axx.office.powerpoint.pdf'] = adapter('Editar copia PowerPoint y exportar PDF', 'office_powerpoint_pdf', 'workspace_write',
    {name:{'type':'string','required':True,'maxLength':limit} for name,limit in [('source',240),('destination',180),('shape_name',200),('expected_text',4000),('new_text',4000)]}
    | {'slide':{'type':'integer','required':True,'minimum':1,'maximum':100}},
    'Con PowerPoint cerrado, modifica una forma por diapositiva/nombre/texto esperado exactos en una copia. Reabre PPTX y comprueba PDF, páginas/texto y origen intacto. No admite macros ni enlaces externos.')
for kind in ('tabs', 'inspect', 'navigate'):
    parameters = {} if kind == 'tabs' else {
        'tab_id': {'type': 'string', 'required': True, 'maxLength': 200},
        'expected_url': {'type': 'string', 'required': True, 'maxLength': 4096},
        'browser_session': {'type': 'string', 'required': True, 'maxLength': 64}}
    if kind == 'navigate':
        parameters |= {'document_id': {'type': 'string', 'required': True, 'maxLength': 200},
                       'url': {'type': 'string', 'required': True, 'maxLength': 4096}}
    ADAPTERS['axx.browser.' + kind] = adapter('Navegador: ' + kind, 'browser_' + kind,
        'local_state' if kind == 'navigate' else 'local_content_read', parameters,
        'Puente CDP configurado explícitamente: perfil, sesión y pestaña exactos. No conecta perfiles personales automáticamente ni ejecuta JavaScript libre.')


ADAPTERS['axx.browser.download_pdf'] = adapter('Descargar PDF observado', 'browser_download_pdf', 'workspace_write',
    {name: {'type': 'string', 'required': True, 'maxLength': limit} for name, limit in (
        ('browser_session', 64), ('tab_id', 128), ('document_id', 128), ('expected_url', 4096),
        ('link_name', 500), ('download_url', 4096), ('destination', 180))},
    'Descarga un enlace único por nombre y URL exactos en la pestaña y documento observados. Persiste PDF nuevo en workspace, verifica páginas/hash; rechaza redirecciones y documentos cambiados. Devuelve path para abrir el mismo archivo.')
ADAPTERS['axx.browser.open_pdf'] = adapter('Abrir el PDF verificado', 'browser_open_pdf', 'local_state',
    {name:{'type':'string','required':True,'maxLength':limit} for name,limit in [('path',240),('sha256',64),('browser_session',64)]},
    'Abre el archivo PDF por ruta y hash exactos en una pestaña nueva del perfil CDP configurado. Comprueba URL file del visor y hash; no acredita calidad visual.')

ADAPTERS['axx.obs.observe'] = adapter('Observar OBS', 'obs_observe', 'local_content_read', {},
    'OBS local autenticado: proceso/sesión, perfil, colección, escenas y grabación. No habilita OBS ni cambia su configuración.')
ADAPTERS['axx.obs.control'] = adapter('Controlar grabación o escena OBS', 'obs_control', 'local_state',
    {name: {'type': 'string', 'required': True, 'maxLength': limit} for name, limit in (
        ('obs_session', 64), ('profile', 256), ('collection', 256), ('scene', 256))} |
    {'action': {'type': 'string', 'required': True, 'enum': ['start', 'stop', 'pause', 'resume', 'scene']},
     'target_scene': {'type': 'string', 'maxLength': 256}},
    'Establece estado sin alternar; requiere contexto OBS observado. Stop verifica el archivo outputPath con ffprobe. Una cancelación no detiene automáticamente una grabación ya iniciada; requiere observar y detener explícitamente.')


class ComputerTool:
    version = '1.0.0'
    def __init__(self, kind):
        self.kind, self.name = kind, 'computer_' + kind
        self.description = 'Observed Windows operation: ' + kind

    def verify_preconditions(self, inputs):
        try:
            import math
            schemas = [a['parameters'] for a in ADAPTERS.values() if a['tool'] == self.name]
            if len(schemas) != 1 or not isinstance(inputs, dict):
                raise ValueError('Operación o argumentos de escritorio inválidos')
            schema = schemas[0]
            if set(inputs) - set(schema) or any(spec.get('required') and name not in inputs for name, spec in schema.items()):
                raise ValueError('Faltan argumentos requeridos o hay argumentos desconocidos')

            def validate(value, spec):
                kind = spec.get('type')
                correct = {'integer': type(value) is int, 'boolean': type(value) is bool,
                           'string': isinstance(value, str), 'object': isinstance(value, dict),
                           'array': isinstance(value, list)}
                if not correct.get(kind, False):
                    raise ValueError('Tipo de argumento inválido')
                if 'enum' in spec and value not in spec['enum']:
                    raise ValueError('Valor fuera de las opciones admitidas')
                if kind == 'integer' and not spec.get('minimum', value) <= value <= spec.get('maximum', value):
                    raise ValueError('Número fuera de límites')
                if kind == 'string':
                    if (len(value) > spec.get('maxLength', 8192) or len(value) < spec.get('minLength', 0)
                            or spec.get('required') and not value.strip() or '\x00' in value):
                        raise ValueError('Texto vacío o fuera de límites')
                    value.encode('utf-8')
                if kind == 'array':
                    if not spec.get('minItems', 0) <= len(value) <= spec.get('maxItems', 100):
                        raise ValueError('Lista fuera de límites')
                    for item in value: validate(item, spec['items'])

            for name, value in inputs.items(): validate(value, schema[name])
            if 'control_id' in inputs and (len(inputs['control_id']) != 64 or any(c not in '0123456789abcdef' for c in inputs['control_id'])):
                raise ValueError('Referencia de control inválida')
            if self.kind == 'input':
                from .desktop_input import validate_action
                validate_action(inputs)
            if self.kind == 'state':
                if set(inputs['state']) != {'value'}:
                    raise ValueError('El estado requiere exactamente {"value":valor}')
                value, pattern = inputs['state']['value'], inputs['pattern']
                finite = lambda v: type(v) in (int, float) and math.isfinite(v)
                valid = (pattern == 'Value' and isinstance(value, str) and len(value) <= 8192 and '\x00' not in value
                         or pattern in ('Toggle', 'SelectionItem') and type(value) is bool
                         or pattern == 'ExpandCollapse' and value in ('expanded', 'collapsed')
                         or pattern == 'RangeValue' and finite(value)
                         or pattern == 'Scroll' and isinstance(value, dict) and set(value) == {'horizontal', 'vertical'}
                         and all(finite(v) and (v == -1 or 0 <= v <= 100) for v in value.values()))
                if not valid: raise ValueError('Estado incompatible con el patrón solicitado')
                if pattern == 'Value': value.encode('utf-16-le')
            if self.kind == 'grid' and inputs.get('rows', 10) * inputs.get('columns', 10) > 200:
                raise ValueError('El rango de tabla excede 200 celdas')
            if self.kind in ('ground', 'grounding') and inputs.get('image_authorized') is not True:
                raise ValueError('Se requiere autorización explícita de esta imagen')
            return True, 'Typed target; live observation is checked immediately before dispatch'
        except (ValueError, TypeError, OverflowError) as exc: return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        return self.execute_with_runtime(inputs, workspace_root, cancelled, None)

    def execute_with_runtime(self, inputs, workspace_root, cancelled, runtime):
        from .tools import ToolResult
        from . import windows_automation as uia
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid: return ToolResult(False, error=reason)
            if self.kind == 'window':
                if cancelled.is_set(): raise ValueError('Selección de ventana cancelada')
                requested_process = inputs.get('process_name')
                if requested_process is not None and (not requested_process.strip() or any(c in requested_process for c in '/\\:')):
                    raise ValueError('Indica sólo el nombre del proceso, sin ruta')

                def select(rows):
                    if len(rows) >= uia.MAX_WINDOWS:
                        raise ValueError('La lista de ventanas está incompleta; no se elige por índice')
                    matches = [row for row in rows if row['title'] == inputs['title']]
                    # EnumWindows bounds titles at 2,048; equality at that limit cannot prove completeness.
                    if any(len(row['title']) >= 2048 for row in matches):
                        raise ValueError('El título observado puede estar truncado')
                    if requested_process is not None:
                        matches = [row for row in matches if uia.process_name(row['pid']).casefold() == requested_process.casefold()]
                    if len(matches) != 1:
                        raise ValueError('No se encontró una ventana única con ese título y proceso')
                    return matches[0]

                selected = select(uia.list_windows())
                birth = uia.process_started(selected['pid'])
                process = uia.process_name(selected['pid'])
                if not birth or not process: raise ValueError('No se pudo verificar la identidad del proceso')
                current = select(uia.list_windows())
                if (any(current[k] != selected[k] for k in ('window_id', 'pid', 'title', 'class_name'))
                        or uia.process_started(current['pid']) != birth or uia.process_name(current['pid']) != process):
                    raise ValueError('La ventana o el proceso cambió durante la selección')
                if cancelled.is_set(): raise ValueError('Selección de ventana cancelada')
                return ToolResult(True, output={'window_id':current['window_id'], 'window_id_hex':hex(current['window_id']),
                    'pid':current['pid'], 'title':current['title'], 'process_name':process},
                    evidence={'verification':'unique_window_identity', 'process_started':birth, 'effect_executed':False})
            if self.kind == 'ground':
                from .visual_grounding import propose_grounding
                result = propose_grounding(inputs['window_id'], inputs['pid'], inputs['observation_id'], inputs['goal'],
                    capture_service=getattr(runtime, 'capture_service', None), provider_name=inputs['provider_name'],
                    model=inputs['model'], image_authorized=inputs['image_authorized'], cancelled=cancelled)
                return ToolResult(True, output=result, evidence={'verification': 'fresh_visual_proposal', 'effect_executed': False})
            if self.kind in ('observe', 'find'):
                from .desktop_observation import observe_desktop
                result = observe_desktop(inputs['window_id'], inputs['pid'], cancelled=cancelled,
                    monitor_id=inputs.get('monitor_id'), capture_service=getattr(runtime, 'capture_service', None))
                if self.kind == 'find':
                    matches = [c for c in result['controls'] if c.get('name') == inputs['name'] and c.get('enabled')
                               and not c.get('offscreen') and (not inputs.get('pattern') or inputs['pattern'] in c.get('patterns', []))]
                    if result.get('truncated') or len(matches) != 1:
                        return ToolResult(False, output={'matches': len(matches), 'truncated': result.get('truncated', False)},
                            error='El control no es único o la observación está incompleta')
                    result.update(control_id=matches[0]['control_id'], observation_id=result['observation']['observation_id'])
                else: result['observation_id'] = result['observation']['observation_id']
                return ToolResult(result.get('quality') != 'unobservable', output=result,
                    evidence={'verification': 'fresh_desktop_observation', 'observation_id': result['observation_id']})
            if self.kind == 'grid':
                result = uia.read_control_grid(inputs['window_id'], inputs['pid'], inputs['control_id'], inputs['observation_id'],
                    **{k: inputs[k] for k in ('row','column','rows','columns') if k in inputs}, cancelled=cancelled)
                return ToolResult(True, output=result, evidence={'verification': result.get('verification')})
            owner = getattr(runtime, 'input_control', None)
            if owner is None: raise ValueError('El broker compartido de entrada no está conectado')
            with owner.automation(cancelled) as control:
                if self.kind == 'input':
                    from .desktop_input import execute_action
                    return ToolResult(**execute_action(inputs, control))
                result = uia.set_control_state(inputs['window_id'], inputs['pid'], inputs['control_id'],
                    inputs['observation_id'], inputs['pattern'], inputs['state']['value'], cancelled=control)
                return ToolResult(True, output=result, evidence={'verification': result.get('verification'),
                    'observation_id': inputs['observation_id'], 'postconditions_passed': result.get('postconditions_passed')})
        except uia.UncertainEffect as exc:
            return ToolResult(False, error=str(exc), evidence={'effect_uncertain': True, 'reconciliation_required': True})
        except (ValueError, OSError) as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        valid = result.success and (result.evidence.get('verification') == 'fresh_desktop_observation'
            or self.kind == 'window' and result.evidence.get('verification') == 'unique_window_identity'
            or self.kind == 'ground' and result.evidence.get('verification') == 'fresh_visual_proposal'
            or self.kind == 'state' and result.output.get('postconditions_passed') is True
            or self.kind == 'grid' and result.evidence.get('verification') == 'uia_grid_readback'
            or self.kind == 'input' and inputs['action'] == 'move' and result.output.get('confirmed') is True)
        return bool(valid), 'Estado leído de nuevo' if valid else 'El efecto de la aplicación no se ha verificado'
