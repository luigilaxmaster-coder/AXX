"""Typed desktop actions. Natural language is never evaluated as shell code."""
from __future__ import annotations

import base64
import ctypes
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import unicodedata
from urllib.parse import urlencode, urlsplit

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree

APPS = {
    'calculator': ('Calculadora', 'System32/calc.exe', ['calculadora', 'calculator', 'calc']),
    'notepad': ('Bloc de notas', 'System32/notepad.exe', ['bloc de notas', 'notepad']),
    'paint': ('Paint', 'System32/mspaint.exe', ['paint']),
    'explorer': ('Explorador de archivos', 'explorer.exe', ['explorador', 'explorador de archivos', 'file explorer', 'explorer']),
}
SITES = {'youtube': 'https://www.youtube.com/', 'google': 'https://www.google.com/',
         'gmail': 'https://mail.google.com/', 'github': 'https://github.com/',
         'chatgpt': 'https://chatgpt.com/', 'spotify': 'https://open.spotify.com/'}
ENGINES = {'youtube': ('https://www.youtube.com/results', 'search_query'),
           'google': ('https://www.google.com/search', 'q'),
           'bing': ('https://www.bing.com/search', 'q'),
           'duckduckgo': ('https://duckduckgo.com/', 'q')}
SHELL_TIMEOUT = 30
MAX_OUTPUT = 64 * 1024


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def validate_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('La dirección web no es válida.')
    url = urlsplit(value)
    if url.scheme not in ('https', 'http') or not url.hostname or url.username is not None or url.password is not None or '\\' in value:
        raise ValueError('Usa una dirección http o https sin credenciales.')
    try:
        url.port
    except ValueError as exc:
        raise ValueError('El puerto de la dirección no es válido.') from exc
    return value


def validate_inputs(kind, inputs):
    if kind in ('notepad_text', 'explorer_folder'):
        from .application_flows import validate_flow
        validate_flow(kind, inputs)
    elif kind == 'open_url':
        validate_url(inputs.get('url'))
    elif kind == 'open_app':
        if inputs.get('app') not in APPS:
            raise ValueError('Aplicación no disponible. Puedes abrir calculadora, bloc de notas, Paint o explorador.')
    elif kind == 'installed_app':
        if not isinstance(inputs.get('app_id'), str) or not 1 <= len(inputs['app_id']) <= 1024:
            raise ValueError('Selecciona una aplicación instalada.')
    elif kind == 'list_apps':
        if inputs:
            raise ValueError('La lista de aplicaciones no admite parámetros.')
    elif kind == 'list_windows':
        if inputs:
            raise ValueError('La lista de ventanas no admite parámetros.')
    elif kind in ('inspect_window', 'read_window', 'focus_window'):
        if set(inputs) != ({'window_id', 'pid', 'expected_title'} if kind == 'read_window' else {'window_id', 'pid'}):
            raise ValueError('Indica la ventana observada y su proceso.')
        _validate_window_ref(inputs['window_id'], inputs['pid'])
        if kind == 'read_window' and (not isinstance(inputs['expected_title'], str) or not 1 <= len(inputs['expected_title']) <= 2048):
            raise ValueError('Indica el título observado de la ventana.')
    elif kind == 'set_window_value':
        if set(inputs) != {'window_id', 'pid', 'control_id', 'value'}:
            raise ValueError('Indica ventana, proceso, control y texto.')
        _validate_window_ref(inputs['window_id'], inputs['pid'])
        if not isinstance(inputs['control_id'], str) or len(inputs['control_id']) != 64 or any(c not in '0123456789abcdef' for c in inputs['control_id']):
            raise ValueError('control_id debe proceder de una observación UIA reciente.')
        if not isinstance(inputs['value'], str) or len(inputs['value']) > 8192 or '\x00' in inputs['value']:
            raise ValueError('El texto debe tener hasta 8.192 caracteres y no contener NUL.')
        inputs['value'].encode('utf-16-le')
    elif kind == 'cli_anything_scan':
        if set(inputs) != {'window_id', 'pid'}:
            raise ValueError('Indica ventana y proceso observados.')
        _validate_window_ref(inputs['window_id'], inputs['pid'])
    elif kind == 'search':
        if inputs.get('engine') not in ENGINES or not isinstance(inputs.get('query'), str) or not 1 <= len(inputs['query'].strip()) <= 500:
            raise ValueError('Indica una búsqueda y un buscador compatible.')
    elif kind in ('powershell', 'cmd'):
        if not isinstance(inputs.get('script'), str) or not 1 <= len(inputs['script'].strip()) <= 8000 or '\x00' in inputs['script']:
            raise ValueError('Escribe un comando de hasta 8.000 caracteres.')
    else:
        raise ValueError('Acción desconocida.')


def _validate_window_ref(window_id, pid):
    if not isinstance(window_id, str) or not re.fullmatch(r'(?:0x)?[0-9a-fA-F]{1,16}', window_id):
        raise ValueError('window_id debe ser un identificador hexadecimal observado.')
    if type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF:
        raise ValueError('pid debe ser un entero Windows válido.')


def resolve_desktop(text, source, context=None):
    context = {} if context is None else context
    if not isinstance(context, dict) or set(context)-{'engine','query','url'}:
        raise ValueError('Contexto de acción inválido.')
    if any(not isinstance(v,str) or len(v)>2048 for v in context.values()):
        raise ValueError('Contexto de acción inválido.')
    def search_result(engine, query):
        engine = 'google' if engine == 'internet' else engine
        inputs = {'engine':engine,'query':query.strip()}
        validate_inputs('search', inputs)
        return {'match':'exact','command_id':'axx.desktop.search','inputs':inputs}
    missing = {'match':'needs_input','message':'¿Qué quieres buscar? Puedes decir «busca gatitos en YouTube».'}
    shell = re.fullmatch(r'(?:/powershell\s+|ejecuta\s+en\s+powershell:\s*)(.+)', text.strip(), re.I | re.S)
    if shell:
        if source != 'text':
            return {'match': 'unsupported', 'message': 'Escribe el comando PowerShell y revisa su aprobación; no se ejecutan scripts dictados.'}
        return {'match': 'exact', 'command_id': 'axx.shell.powershell', 'inputs': {'script': shell[1]}}
    cmd = re.fullmatch(r'(?:/cmd\s+|ejecuta\s+en\s+cmd:\s*)(.+)', text.strip(), re.I | re.S)
    if cmd:
        if source != 'text':
            return {'match': 'unsupported', 'message': 'Escribe el comando CMD y apruébalo en la PC.'}
        return {'match': 'exact', 'command_id': 'axx.shell.cmd', 'inputs': {'script': cmd[1]}}
    raw = re.sub(r'^[¡¿\s]+', '', text.strip())
    raw = re.sub(r'^(?:(?:oye|hola)\s+)?axx[,\s]+', '', raw, flags=re.I)
    raw = re.sub(r'^por favor[,\s]+', '', raw, flags=re.I)
    raw = re.sub(r'^(?:puedes|podrias|podrías|quiero que)\s+', '', raw, flags=re.I)
    raw = re.sub(r'\s+por favor[?.!]*$', '', raw, flags=re.I)
    raw = re.sub(r'^pero\s+', '', raw, flags=re.I)
    desktop_app = re.fullmatch(r'(?:busca|encuentra|localiza)\s+(.+?)\s+en (?:mi|el) escritorio y (?:abrelo|ábrelo|abrela|ábrela)[.!?]*', raw, re.I)
    if desktop_app:
        if not re.fullmatch(r'[\w\s-]{2,100}', desktop_app[1], re.UNICODE):
            return {'match': 'unsupported', 'message': 'Para abrir un archivo del escritorio, indica su nombre exacto en la biblioteca de archivos.'}
        raw = 'abre ' + desktop_app[1]
    if plain(raw).strip(' .!?') in ('mis aplicaciones', 'aplicaciones instaladas', 'lista de aplicaciones', 'muestra mis aplicaciones'):
        return {'match': 'exact', 'command_id': 'axx.desktop.list_apps', 'inputs': {}}
    engine_pattern = r'(youtube|google|bing|duckduckgo|internet)'
    # Compound open+search is a single typed URL action, not two unrelated effects.
    compound = re.fullmatch(r'(?:abre|abrir|abreme|ábreme)\s+'+engine_pattern+r'\s+y\s+(?:busca|buscar|buscame|búscame)(?:\s+(.+))?',raw,re.I)
    if compound:return search_result(compound[1].lower(),compound[2]) if compound[2] else missing
    slash = re.fullmatch(r'/(?:search|buscar)\s+'+engine_pattern+r'(?:\s+(.+))?',raw,re.I)
    if slash:return search_result(slash[1].lower(),slash[2]) if slash[2] else missing
    if re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+en\s+'+engine_pattern,raw,re.I):return missing
    if re.fullmatch(r'(?:abrela|ábrela|abrelo|ábrelo|abrirlo|abre(?:\s+la)?\s+busqueda)(?:\s+en\s+(?:el\s+)?navegador)?[.!?]*',raw,re.I):
        if context.get('query') and context.get('engine') in ENGINES:return search_result(context['engine'],context['query'])
        if context.get('url'):
            return {'match':'exact','command_id':'axx.desktop.open_url','inputs':{'url':validate_url(context['url'])}}
        return {'match':'needs_input','message':'Indica el enlace o la búsqueda que quieres abrir.'}
    if plain(raw).strip(' .!?') in ('si','confirmar','confirmo'):
        return {'match':'needs_input','message':'No hay una acción pendiente de esa confirmación. Indica qué quieres abrir o buscar.'}
    music = re.fullmatch(r'(?:ponme|pon|reproduce|reproducir|escuchar)(?:\s+(.+))?',raw,re.I)
    if music:return search_result('youtube',music[1]) if music[1] else missing
    music_search = re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+(?:(?:una|un|la|el)\s+)?(?:musica|música|cancion|canción|tema)\s+(?:de\s+)?(.+)', raw, re.I)
    if music_search:return search_result('youtube', music_search[1])
    # Preserve URL case and query punctuation. Only trim sentence marks for named targets.
    opening = re.fullmatch(r'(?:abre|abrir|abras|abreme|ábreme|inicia|ejecuta)\s+(?:(?:la|el)\s+)?(.+)', raw, re.I)
    if opening:
        target = opening[1].strip()
        name = re.sub(r'^(?:la aplicacion|el programa|mi|la|el)\s+', '', plain(target).rstrip('.!?'))
        if name == 'spotify':
            from .windows_apps import find_app
            try:
                spotify = find_app(name, plain)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                spotify = []
            if len(spotify) == 1:
                return {'match': 'exact', 'command_id': 'axx.desktop.installed_app', 'inputs': {'app_id': spotify[0]['app_id']}}
        if name in SITES:
            return {'match': 'exact', 'command_id': 'axx.desktop.open_url', 'inputs': {'url': SITES[name]}}
        for key, (_, _, aliases) in APPS.items():
            if name in aliases:
                return {'match': 'exact', 'command_id': 'axx.desktop.open_app', 'inputs': {'app': key}}
        if re.match(r'https?://', target, re.I) or re.fullmatch(r'(?:[\w-]+\.)+[A-Za-z]{2,}(?:[/?:#].*)?', target):
            url = target if re.match(r'https?://', target, re.I) else 'https://' + target
            validate_url(url)
            return {'match': 'exact', 'command_id': 'axx.desktop.open_url', 'inputs': {'url': url}}
        if not re.search(r'[;&|\n\r]', target):
            from .windows_apps import find_app
            try:
                candidates = find_app(name, plain)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return {'match': 'unsupported', 'message': 'No pude consultar las aplicaciones de Windows. Prueba «mis aplicaciones» para reintentar.'}
            if len(candidates) == 1:
                return {'match': 'exact', 'command_id': 'axx.desktop.installed_app', 'inputs': {'app_id': candidates[0]['app_id']}}
            if candidates:
                return {'match': 'ambiguous', 'message': 'Hay varias aplicaciones. Usa «abre» y el nombre completo: ' + ', '.join(c['name'] for c in candidates[:12]), 'candidates': candidates[:12]}
        return {'match': 'unsupported', 'message': 'No encontré una aplicación instalada con ese nombre. Consulta «mis aplicaciones» o indica una dirección web.'}
    search = re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+en\s+(youtube|google|bing|duckduckgo|internet)\s+(.+)', raw, re.I)
    if search:
        engine, query = search[1].lower(), search[2]
    else:
        search = re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+(.+?)\s+en\s+(youtube|google|bing|duckduckgo|internet)[.!?]*', raw, re.I)
        if not search:
            bare = re.fullmatch(r'(?:busca|buscar|buscame|búscame)(?:\s+(.+))?',raw,re.I)
            if bare:
                return search_result(context.get('engine') if context.get('engine') in ENGINES else 'google',bare[1]) if bare[1] else missing
            if raw.startswith(('/search','/buscar')):return missing
            return None
        query, engine = search[1], search[2].lower()
    return search_result(engine, query)


def open_target(kind, inputs, cancelled=None, control=None):
    validate_inputs(kind, inputs)
    if os.name != 'nt':
        raise ValueError('Esta acción requiere Axx para Windows.')
    if cancelled is not None and cancelled.is_set(): raise ValueError('Acción cancelada antes de abrir.')
    if kind in ('notepad_text', 'explorer_folder'):
        from .application_flows import execute_flow
        return execute_flow(kind, inputs, control)
    if kind in ('installed_app', 'list_apps'):
        from .windows_apps import capability_status, installed_apps
        rows = installed_apps()
        if kind == 'list_apps':
            applications = [capability_status(row) for row in rows]
            return {'success': True, 'output': {'applications': applications},
                    'evidence': {'verification': 'windows_inventory', 'count': len(applications)}}
        app = next((row for row in rows if row['app_id'] == inputs['app_id']), None)
        if not app:
            raise ValueError('La aplicación no aparece en el inventario de Windows. Actualiza la lista.')
        target, label = 'shell:AppsFolder\\' + app['app_id'], app['name']
        app_aliases = ()
    elif kind == 'list_windows':
        from .windows_automation import list_windows
        rows = list_windows()
        return {'success': True, 'output': {'windows': rows},
                'evidence': {'verification': 'visible_windows_inventory', 'accepted': True, 'count': len(rows)}}
    elif kind == 'cli_anything_scan':
        from .cli_anything_engine import ENGINE
        app = ENGINE.scan_window(int(inputs['window_id'], 16), inputs['pid'], cancelled=cancelled)
        return {'success': True, 'output': app.to_dict(),
                'evidence': {'verification': 'uia_capabilities_observed', 'accepted': True,
                            'window_id': app.window_id, 'pid': app.pid, 'count': len(app.controls)}}
    elif kind in ('inspect_window', 'read_window', 'focus_window', 'set_window_value'):
        from .windows_automation import focus_window, inspect_controls, read_window_content, set_control_value
        window_id = int(inputs['window_id'], 16)
        if kind in ('inspect_window', 'read_window'):
            output = (read_window_content(window_id, inputs['pid'], inputs['expected_title'], cancelled=cancelled)
                      if kind == 'read_window' else inspect_controls(window_id, inputs['pid'], cancelled=cancelled))
            evidence = {'verification': output['verification'], 'accepted': True,
                        'window_id': window_id, 'pid': inputs['pid']}
        elif kind == 'focus_window':
            output = focus_window(window_id, inputs['pid'], control=control)
            evidence = {'verification': output['verification'], 'accepted': True,
                        'window_id': window_id, 'pid': inputs['pid']}
        else:
            output = set_control_value(window_id, inputs['pid'], inputs['control_id'], inputs['value'], cancelled=cancelled)
            evidence = {'verification': output['verification'], 'accepted': True,
                        'window_id': window_id, 'pid': inputs['pid'],
                        'control_id': inputs['control_id'],
                        'value_sha256': output['value_sha256'], 'value_length': output['value_length']}
            output = {key: value for key, value in output.items() if key != 'success'}
        return {'success': True, 'output': output, 'evidence': evidence}
    elif kind == 'open_app':
        label, relative, app_aliases = APPS[inputs['app']]
        target = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / relative)
        if not Path(target).is_file():
            raise ValueError(f'{label} no está instalado en este equipo.')
    elif kind == 'search':
        base, param = ENGINES[inputs['engine']]
        target = base + '?' + urlencode({param: inputs['query']})
        label = target
    else:
        target = validate_url(inputs['url'])
        label = target
    before = []
    if kind in ('installed_app', 'open_app'):
        from .windows_automation import list_windows
        before = list_windows()
    os.startfile(target)
    # A shell handoff proves only that Windows accepted the launch request.
    # UI actions remain blocked until a matching foreground window is observed.
    evidence = {'verification': 'os_handoff', 'target': target, 'accepted': True,
                'launch_requested': True, 'window_observed': False,
                'foreground_verified': False, 'ready_for_action': False}
    if kind in ('installed_app', 'open_app'):
        from .windows_automation import observe_foreground
        observed = observe_foreground(label, timeout=4.0, before=before,
                                       aliases=app_aliases if kind == 'open_app' else (),
                                       cancelled=cancelled, control=control,
                                       expected_process=Path(target).name.lower() if kind == 'open_app' and inputs['app'] in ('notepad', 'explorer') else None)
        evidence.update({key: observed[key] for key in
                         ('launch_requested', 'window_observed', 'foreground_verified', 'ready_for_action')})
        evidence['window_verification'] = observed['verification']
        evidence['window'] = observed.get('window')
    return {'success': True, 'output': {'target': target, 'label': label,
                                        'ready_for_action': evidence['ready_for_action']},
            'evidence': evidence}


def run_shell(kind, inputs, workspace, cancelled):
    validate_inputs(kind, inputs)
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / ('System32/cmd.exe' if kind == 'cmd' else 'System32/WindowsPowerShell/v1.0/powershell.exe')
    if os.name != 'nt' or not executable.is_file():
        raise ValueError('El intérprete de comandos de Windows no está disponible.')
    # Fixed launcher and exact reviewed text. Never accept model output here.
    if kind == 'cmd':
        command = [str(executable), '/d', '/s', '/c', inputs['script']]
    else:
        script = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; $ErrorActionPreference = 'Stop';\n" + inputs['script']
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        command = [str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-EncodedCommand', encoded]
    runtime_names = {'systemroot', 'windir', 'path', 'temp', 'tmp', 'userprofile', 'appdata', 'localappdata',
                     'programdata', 'programfiles', 'programfiles(x86)', 'commonprogramfiles', 'comspec',
                     'number_of_processors', 'processor_architecture', 'username', 'computername'}
    env = {key: value for key, value in os.environ.items() if key.lower() in runtime_names}
    if cancelled.is_set():
        return {'success': False, 'error': 'Comando cancelado antes de ejecutar.', 'evidence': {'cancelled': True}}
    process, job = spawn_managed_process(command,
                                        cwd=str(workspace), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    def collect(pipe, target):
        try:
            while chunk := pipe.read(4096):
                remaining = MAX_OUTPUT - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    break
        finally:
            pipe.close()
    readers = [threading.Thread(target=collect, args=(pipe, target), daemon=True) for pipe, target in zip((process.stdout, process.stderr), buffers)]
    for reader in readers:
        reader.start()
    reason = None
    try:
        deadline = time.monotonic() + SHELL_TIMEOUT
        while process.poll() is None:
            if cancelled.is_set():
                reason = 'Comando cancelado. Los cambios que ya haya realizado no se deshacen.'
            elif overflow.is_set():
                reason = 'Comando detenido: la salida superó el límite de 64 KiB.'
            elif time.monotonic() >= deadline:
                reason = 'Comando detenido: superó el límite de 30 segundos.'
            if reason:
                break
            time.sleep(.02)
    finally:
        # Also clean up child processes after the reviewed command exits.
        terminate_process_tree(process, job)
        for reader in readers:
            reader.join(2)
    if cancelled.is_set():
        reason = 'Comando cancelado. Los cambios que ya haya realizado no se deshacen.'
    elif overflow.is_set():
        reason = 'Comando detenido: la salida superó el límite de 64 KiB.'
    # cmd.exe writes in the Windows OEM code page when launched without a console.
    # PowerShell explicitly uses UTF-8 above.
    encoding = f'cp{ctypes.windll.kernel32.GetOEMCP()}' if kind == 'cmd' else 'utf-8'
    output = {'stdout': bytes(buffers[0]).decode(encoding, errors='replace'),
              'stderr': bytes(buffers[1]).decode(encoding, errors='replace'),
              'exit_code': process.returncode}
    return {'success': reason is None and process.returncode == 0, 'output': output,
            'error': reason or (f'{"CMD" if kind == "cmd" else "PowerShell"} terminó con código {process.returncode}.' if process.returncode else None),
            'evidence': {'exit_code': process.returncode, 'cancelled': cancelled.is_set(), 'verification': 'process_exit', 'cwd': str(workspace)}}


def run_powershell(inputs, workspace, cancelled):
    return run_shell('powershell', inputs, workspace, cancelled)
