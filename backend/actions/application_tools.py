"""Exact application routes over existing Windows primitives and input ownership."""
from pathlib import PureWindowsPath
import re
import threading
from urllib.parse import urlsplit

from .. import application_catalog as catalog
from . import windows_automation as uia
from .desktop import plain, validate_url


APPLICATION = {'type': 'string', 'required': True, 'maxLength': 240}
WINDOW = {'window_id': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807},
          'pid': {'type': 'integer', 'minimum': 1, 'maximum': 4294967295}}


def _adapter(title, kind, risk, description, *, approval=False):
    parameters = {'application': dict(APPLICATION, required=kind != 'catalog')}
    if kind not in ('catalog', 'open'):
        parameters |= WINDOW
    if kind == 'navigate':
        parameters |= {'command_id': {'type': 'string', 'required': True, 'maxLength': 100},
                       'url': {'type': 'string', 'maxLength': 2048}}
    if kind == 'browse':
        parameters['url'] = {'type': 'string', 'required': True, 'maxLength': 2048}
    if kind in ('hover', 'youtube'):
        parameters['name' if kind == 'hover' else 'query'] = {'type': 'string', 'required': True, 'maxLength': 500}
    return {'title': title, 'tool': 'application_' + kind, 'risk': risk,
            'requires_approval': approval, 'parameters': parameters, 'aliases': [],
            'description': description}


ADAPTERS = {
    'axx.app.browse': _adapter('Navegar en el navegador solicitado', 'browse', 'local_state',
        'Abre si hace falta y navega en una ventana única del navegador; verifica su barra de direcciones.'),
    'axx.app.hover': _adapter('Mover cursor sobre un elemento por nombre', 'hover', 'local_content_read',
        'Lee la ventana solicitada, localiza una etiqueta visible única y verifica el cursor mediante el broker.'),
    'axx.app.youtube': _adapter('Reproducir un resultado identificado en YouTube', 'youtube', 'local_content_read',
        'Busca la canción, selecciona un resultado observado por título y comprueba identidad y avance del reproductor.'),
    'axx.app.catalog': _adapter('Aplicaciones y comandos disponibles', 'catalog', 'read',
        'Inventario real de Windows y perfiles con instrucciones. La instalación no acredita compatibilidad ni ejecución de todas sus acciones.'),
    'axx.app.open': _adapter('Abrir aplicación exacta', 'open', 'desktop_open',
        'Resuelve nombre, ID o alias exacto a un único ID instalado y solicita su apertura; no elige una coincidencia aproximada.'),
    'axx.app.windows': _adapter('Ventanas de una aplicación', 'windows', 'read',
        'Enumera ventanas cuyo proceso coincide con el perfil o el ejecutable instalado. Informa múltiples ventanas sin elegir la primera.'),
    'axx.app.focus': _adapter('Enfocar aplicación observada', 'focus', 'desktop_open',
        'Enfoca una ventana de la aplicación y comprueba el foco. Con varias ventanas requiere HWND y PID observados.'),
    'axx.app.inspect': _adapter('Inspeccionar aplicación observada', 'inspect', 'read',
        'Inspecciona controles UIA de una ventana vinculada a la aplicación y proceso observados.'),
    'axx.app.close': _adapter('Cerrar ventana de aplicación', 'close', 'local_state',
        'Solicita cierre normal de la ventana seleccionada y respeta los avisos de cambios sin guardar.'),
    'axx.app.navigate': _adapter('Ejecutar comando de aplicación', 'navigate', 'local_state',
        'Sólo comandos declarados en el perfil y comprobados en la ventana viva. Clic y atajos conservan efecto desconocido sin lectura posterior; guías, envío de mensajes y conexiones remotas no se ejecutan.', approval=True),
}


def _profile(query):
    return catalog.profile_for(query)


def _process_path(pid):
    import psutil
    try:
        return str(PureWindowsPath(psutil.Process(pid).exe())).casefold()
    except (psutil.Error, OSError):
        return ''


def _window_rows(application):
    profile = _profile(application)
    executable = None
    if profile:
        names = {name.casefold() for name in profile['process_names']}
        if not names:
            raise ValueError('El perfil no declara una identidad de proceso; usa una observación de ventana explícita.')
    else:
        resolved = catalog.resolve_application(application)
        app_id = resolved['app']['app_id']
        path = PureWindowsPath(app_id)
        if not path.is_absolute() or path.suffix.casefold() != '.exe':
            raise ValueError('La aplicación instalada no expone un ejecutable identificable; no se elige por el título.')
        executable, names = str(path).casefold(), {path.name.casefold()}
    rows = uia.list_windows()
    if len(rows) >= uia.MAX_WINDOWS:
        raise ValueError('La lista de ventanas está incompleta; no se selecciona una coincidencia parcial.')
    matches = []
    for row in rows:
        process = uia.process_name(row['pid'])
        if process.casefold() not in names or executable and _process_path(row['pid']) != executable:
            continue
        birth = uia.process_started(row['pid'])
        if not birth or len(row['title']) >= 2048:
            raise ValueError('La identidad o el título de la ventana no se pudo verificar.')
        matches.append(dict(row, process_name=process, process_started=birth))
    return profile, matches


def _select_window(inputs):
    profile, rows = _window_rows(inputs['application'])
    if 'window_id' in inputs:
        rows = [row for row in rows if row['window_id'] == inputs['window_id'] and row['pid'] == inputs['pid']]
    if len(rows) != 1:
        raise ValueError('Indica window_id y pid de una ventana única obtenida con axx.app.windows; no hay selección por índice.')
    selected = rows[0]
    _, current = _window_rows(inputs['application'])
    current = [row for row in current if row['window_id'] == selected['window_id'] and row['pid'] == selected['pid']]
    fields = ('window_id', 'pid', 'title', 'class_name', 'process_name', 'process_started')
    if len(current) != 1 or any(current[0].get(key) != selected.get(key) for key in fields):
        raise ValueError('La ventana o su proceso cambió durante la selección.')
    return profile, selected


def _command(inputs):
    profile = _profile(inputs['application'])
    if not profile:
        raise ValueError('La aplicación no tiene comandos declarados; usa catálogo e inspección.')
    matches = [row for row in profile['commands'] if row['id'] == inputs['command_id']]
    if len(matches) != 1:
        raise ValueError('El comando no pertenece al perfil seleccionado.')
    command = matches[0]
    if command['kind'] == 'guide' or command.get('requires_connection'):
        raise ValueError('Esta acción es una guía: necesita un adaptador y autorización de conexión propios.')
    if command['kind'] == 'navigate':
        validate_url(inputs.get('url'))
        if not command.get('names'):
            raise ValueError('Falta un selector verificable de la barra de direcciones para este perfil.')
    elif 'url' in inputs:
        raise ValueError('Este comando no admite una dirección URL.')
    if command['kind'] == 'shortcut' and command.get('requires_text'):
        raise ValueError('Este atajo requiere un selector de texto verificable; usa los controles observados.')
    return command


def _observe(window, cancelled, browser=False):
    from .desktop_observation import observe_desktop
    result = (uia.inspect_browser_controls(window['window_id'], window['pid'], cancelled=cancelled) if browser
              else observe_desktop(window['window_id'], window['pid'], cancelled=cancelled))
    if browser: result['quality'] = 'unobservable' if result['observation'].get('minimized') else 'truncated' if result.get('truncated') else 'complete'
    if result.get('truncated') or result.get('quality') != 'complete':
        raise ValueError('La observación está truncada o no es accesible.')
    if result['observation'].get('process_started') != window['process_started']:
        raise ValueError('Cambió la instancia del proceso observado.')
    return result


def _input(window, observation, action, control, **values):
    from .desktop_input import execute_action
    return execute_action({'window_id': window['window_id'], 'pid': window['pid'],
                           'observation_id': observation['observation']['observation_id'],
                           'action': action, **values}, control)


def _url_readback(observed, requested):
    """Compare visible address text; a hidden scheme is explicitly unverified."""
    try:
        target = urlsplit(validate_url(requested))
        if not isinstance(observed, str):
            return False, False
        explicit = re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', observed)
        actual = urlsplit(validate_url(observed if explicit else target.scheme + '://' + observed))
        # No authority/default-port/path/query/fragment normalization. Only the
        # browser's omission of the literal http(s) prefix is accepted.
        expected_address = requested.split('://', 1)[1]
        if explicit:
            matches = actual.scheme == target.scheme and observed.split('://', 1)[1] == expected_address
        else:
            matches = observed == expected_address
        return bool(matches), bool(matches and explicit)
    except ValueError:
        return False, False


def _same_url(left, right):
    return _url_readback(left, right)[0]


def _address_bars(observed, command):
    # Chrome UIA appends a space to the Spanish omnibox label. Only edge
    # whitespace is canonicalized; raw names remain in native identity guards.
    return [row for row in observed['controls'] if isinstance(row.get('name'), str)
            and any(row['name'].strip() == label.strip() for label in command['names'])
            and row.get('control_type') in ('ControlType.Edit', 'ControlType.ComboBox')
            and row.get('enabled') and not row.get('offscreen')
            and row.get('supports_value_pattern') and not row.get('read_only')]


class ApplicationTool:
    version = '1.0.0'

    def __init__(self, kind):
        self.kind, self.name = kind, 'application_' + kind
        self.description = ADAPTERS['axx.app.' + kind]['description']
        self.parameter_names = set(ADAPTERS['axx.app.' + kind]['parameters'])

    def verify_preconditions(self, inputs):
        try:
            rules = ADAPTERS['axx.app.' + self.kind]['parameters']
            if not isinstance(inputs, dict) or set(inputs) - set(rules):
                raise ValueError('Argumentos de aplicación desconocidos.')
            for name, rule in rules.items():
                if name not in inputs:
                    if rule.get('required'):
                        raise ValueError('Falta el argumento ' + name)
                    continue
                value = inputs[name]
                if rule['type'] == 'string':
                    if not isinstance(value, str) or not value.strip() or len(value) > rule['maxLength'] or '\x00' in value:
                        raise ValueError('Texto vacío o fuera de límite: ' + name)
                    value.encode('utf-8')
                elif type(value) is not int or not rule['minimum'] <= value <= rule['maximum']:
                    raise ValueError('Referencia de ventana inválida: ' + name)
            if ('window_id' in inputs) != ('pid' in inputs):
                raise ValueError('window_id y pid deben indicarse juntos.')
            if self.kind == 'navigate':
                _command(inputs)
            if self.kind == 'browse':
                validate_url(inputs['url'])
            if self.kind in ('browse', 'youtube'):
                profile = _profile(inputs['application'])
                if not profile or not any(c['kind'] == 'navigate' for c in profile['commands']):
                    raise ValueError('La aplicación no tiene navegación verificable.')
            return True, 'Argumentos tipados; identidad y controles se comprueban antes de actuar.'
        except (ValueError, TypeError, UnicodeError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        return self.execute_with_runtime(inputs, workspace_root, cancelled, None)

    def execute_with_runtime(self, inputs, workspace_root, cancelled, runtime):
        from .tools import DesktopTool, ToolResult
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid:
                raise ValueError(reason)
            if cancelled.is_set():
                raise ValueError('Operación de aplicación cancelada antes de actuar.')
            if self.kind == 'catalog':
                output = catalog.installed_catalog()
                if inputs.get('application'):
                    profile = _profile(inputs['application'])
                    resolved = catalog.resolve_application(inputs['application']) if not profile else None
                    selected = [row for row in output['profiles'] if profile and row['id'] == profile['id']]
                    applications = [resolved['app']] if resolved else [app for row in selected for app in row['installed_matches']]
                    output = {'profiles': selected, 'applications': applications}
                return ToolResult(True, output=output, evidence={'verification': 'application_inventory_and_profiles', 'effect_executed': False})
            if self.kind == 'open':
                resolved = catalog.resolve_application(inputs['application'])
                return DesktopTool('installed_app').execute_with_control({'app_id': resolved['app']['app_id']}, workspace_root, cancelled, getattr(runtime, 'input_control', None))
            if self.kind == 'windows':
                profile, rows = _window_rows(inputs['application'])
                if 'window_id' in inputs:
                    rows = [row for row in rows if row['window_id'] == inputs['window_id'] and row['pid'] == inputs['pid']]
                return ToolResult(True, output={'application': inputs['application'], 'profile_id': profile['id'] if profile else None,
                    'windows': rows, 'ambiguous': len(rows) > 1}, evidence={'verification': 'application_window_inventory', 'count': len(rows), 'effect_executed': False})
            if self.kind in ('browse', 'hover', 'youtube'):
                from .browser_tasks import execute
                return execute(self, inputs, workspace_root, cancelled, runtime)
            profile, window = _select_window(inputs)
            target = {'window_id': hex(window['window_id']), 'pid': window['pid']}
            if self.kind in ('focus', 'inspect', 'close'):
                kind = {'focus': 'focus_window', 'inspect': 'inspect_window', 'close': 'close_window'}[self.kind]
                result = DesktopTool(kind).execute_with_control(target, workspace_root, cancelled, getattr(runtime, 'input_control', None))
                if result.success and self.kind != 'close' and uia.process_started(window['pid']) != window['process_started']:
                    raise uia.UncertainEffect('La instancia del proceso cambió después de la operación.')
                return result
            command = _command(inputs)
            if command['kind'] == 'invoke':
                observed = _observe(window, cancelled)
                matches = [row for row in observed['controls'] if row.get('name') in command.get('names', [])
                    and row.get('control_type') == 'ControlType.Button' and row.get('enabled') and not row.get('offscreen')
                    and row.get('supports_invoke_pattern')]
                if len(matches) != 1:
                    raise ValueError('No hay un botón visible y único con el nombre declarado.')
                return DesktopTool('invoke_window_button').execute_with_control(dict(target,
                    control_id=matches[0]['control_id'], expected_title=window['title'], expected_name=matches[0]['name']),
                    workspace_root, cancelled, getattr(runtime, 'input_control', None))
            owner = getattr(runtime, 'input_control', None)
            if owner is None:
                raise ValueError('El broker compartido de entrada no está conectado.')
            with owner.automation(cancelled) as control:
                _, current = _select_window(dict(inputs, window_id=window['window_id'], pid=window['pid']))
                if current['process_started'] != window['process_started']:
                    raise ValueError('Cambió el proceso antes de adquirir entrada.')
                uia.focus_window(window['window_id'], window['pid'], control=control)
                observed = _observe(window, control, browser=command['kind'] == 'navigate')
                if command['kind'] == 'shortcut':
                    output = _input(window, observed, 'hotkey', control, keys=command['keys'])
                    return ToolResult(**output)
                return self._navigate_url(inputs, command, window, observed, control)
        except uia.UncertainEffect as exc:
            return ToolResult(False, error=str(exc), evidence={'effect_uncertain': True, 'reconciliation_required': True})
        except (ValueError, OSError, KeyError) as exc:
            return ToolResult(False, error=str(exc), evidence={'cancelled': cancelled.is_set()})

    def _navigate_url(self, inputs, command, window, observed, control):
        from .tools import ToolResult
        dispatched = False
        try:
            dispatched = True
            _input(window, observed, 'hotkey', control, keys=['Control', 'L'])
            observed = _observe(window, control, browser=True)
            candidates = _address_bars(observed, command)
            focused = [row for row in candidates if row.get('control_id') == observed.get('focused_control_id')]
            if len(focused) != 1:
                raise ValueError('No se confirmó el foco en una barra de direcciones editable del navegador. '
                    f'Barras compatibles: {len(candidates)}; foco UIA presente: {bool(observed.get("focused_control_id"))}.')
            uia.set_control_value(window['window_id'], window['pid'], focused[0]['control_id'], inputs['url'],
                                  cancelled=control, expected_title=window['title'])
            observed = _observe(window, control, browser=True)
            current = next((row for row in observed['controls'] if row.get('control_id') == focused[0]['control_id']), None)
            if not current or observed.get('focused_control_id') != current['control_id']:
                raise ValueError('La barra de direcciones perdió el foco antes de navegar.')
            readback = uia.read_control_value(window['window_id'], window['pid'], current['control_id'],
                                             observed['observation']['observation_id'], cancelled=control)
            if not _same_url(readback['value'], inputs['url']):
                raise ValueError('La barra de direcciones no confirmó la URL antes de navegar.')
            _input(window, observed, 'hotkey', control, keys=['Enter'])
            observed = _observe(window, control, browser=True)
            matches = _address_bars(observed, command)
            if len(matches) != 1:
                raise ValueError('La navegación se entregó, pero no se confirmó una URL única después.')
            readback = uia.read_control_value(window['window_id'], window['pid'], matches[0]['control_id'],
                                             observed['observation']['observation_id'], cancelled=control)
            matches_url, scheme_verified = _url_readback(readback['value'], inputs['url'])
            if not matches_url:
                raise ValueError('La navegación se entregó, pero la URL observada después es diferente.')
            return ToolResult(True, output={'window_id': window['window_id'], 'pid': window['pid'], 'url': inputs['url'],
                'observed_url': readback['value'], 'scheme_verified': scheme_verified, 'content_verified': False},
                evidence={'verification': 'application_url_readback', 'accepted': True,
                          'scheme_verified': scheme_verified, 'content_verified': False})
        except (ValueError, OSError, KeyError) as exc:
            if dispatched:
                raise uia.UncertainEffect('Navegación enviada o parcial; requiere inspección antes de repetir: ' + str(exc)) from exc
            raise

    def verify_postconditions(self, inputs, result):
        if self.kind in ('catalog', 'windows'):
            valid = result.success and result.evidence.get('verification') in ('application_inventory_and_profiles', 'application_window_inventory')
        elif self.kind == 'navigate':
            valid = result.success and result.evidence.get('verification') == 'application_url_readback'
        elif self.kind in ('browse', 'hover', 'youtube'):
            expected = {'browse': 'application_url_readback', 'hover': 'cursor_readback', 'youtube': 'youtube_player_progress'}[self.kind]
            valid = result.success and result.evidence.get('verification') == expected
        else:
            from .tools import DesktopTool
            kind = {'open': 'installed_app', 'focus': 'focus_window', 'inspect': 'inspect_window', 'close': 'close_window'}[self.kind]
            return DesktopTool(kind).verify_postconditions(inputs, result)
        return bool(valid), 'Resultado observado de la aplicación' if valid else 'El efecto de la aplicación aún no está verificado.'


TOOLS = {tool.name: tool for tool in (ApplicationTool(kind) for kind in ('catalog', 'open', 'windows', 'focus', 'inspect', 'close', 'navigate', 'browse', 'hover', 'youtube'))}


def resolve_application_command(text):
    if not isinstance(text, str):
        return None
    patterns = [('open', r'(?:abre|abrir|inicia|iniciar)\s+(.+)'),
                ('windows', r'(?:muestra|lista)\s+(?:las\s+)?ventanas\s+de\s+(.+)'),
                ('focus', r'(?:enfoca|enfocar)\s+(.+)'), ('inspect', r'(?:inspecciona|inspeccionar)\s+(.+)'),
                ('catalog', r'(?:muestra|lista)\s+(?:los\s+)?comandos\s+de\s+(.+)')]
    raw = plain(text.strip()).rstrip(' .!')
    for kind, pattern in patterns:
        match = re.fullmatch(pattern, raw)
        if not match:
            continue
        query = match[1].strip()
        if not query or any(c in query for c in ';\r\n'):
            return None
        profile = _profile(query)
        if profile:
            application = profile['id']
        else:
            try:
                application = catalog.resolve_application(query)['app']['app_id']
            except (ValueError, OSError):
                return None
        return {'match': 'exact', 'command_id': 'axx.app.' + kind, 'inputs': {'application': application}}
    return None
