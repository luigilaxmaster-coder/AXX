"""Typed desktop actions. Natural language is never evaluated as shell code."""
from __future__ import annotations

import base64
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
    'calculator': ('Calculadora', 'System32/calc.exe', ['calculadora', 'calc']),
    'notepad': ('Bloc de notas', 'System32/notepad.exe', ['bloc de notas', 'notepad']),
    'paint': ('Paint', 'System32/mspaint.exe', ['paint']),
    'explorer': ('Explorador de archivos', 'explorer.exe', ['explorador', 'explorador de archivos']),
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
    if kind == 'open_url':
        validate_url(inputs.get('url'))
    elif kind == 'open_app':
        if inputs.get('app') not in APPS:
            raise ValueError('Aplicación no disponible. Puedes abrir calculadora, bloc de notas, Paint o explorador.')
    elif kind == 'search':
        if inputs.get('engine') not in ENGINES or not isinstance(inputs.get('query'), str) or not 1 <= len(inputs['query'].strip()) <= 500:
            raise ValueError('Indica una búsqueda y un buscador compatible.')
    elif kind == 'powershell':
        if not isinstance(inputs.get('script'), str) or not 1 <= len(inputs['script'].strip()) <= 8000 or '\x00' in inputs['script']:
            raise ValueError('Escribe un comando PowerShell de hasta 8.000 caracteres.')
    else:
        raise ValueError('Acción desconocida.')


def resolve_desktop(text, source):
    shell = re.fullmatch(r'(?:/powershell\s+|ejecuta\s+en\s+powershell:\s*)(.+)', text.strip(), re.I | re.S)
    if shell:
        if source != 'text':
            return {'match': 'unsupported', 'message': 'Escribe el comando PowerShell y revisa su aprobación; no se ejecutan scripts dictados.'}
        return {'match': 'exact', 'command_id': 'axx.shell.powershell', 'inputs': {'script': shell[1]}}
    raw = re.sub(r'^[¡¿\s]+', '', text.strip())
    raw = re.sub(r'^(?:(?:oye|hola)\s+)?axx[,\s]+', '', raw, flags=re.I)
    raw = re.sub(r'^por favor[,\s]+', '', raw, flags=re.I)
    raw = re.sub(r'^(?:puedes|podrias|podrías|quiero que)\s+', '', raw, flags=re.I)
    raw = re.sub(r'\s+por favor[?.!]*$', '', raw, flags=re.I)
    # Preserve URL case and query punctuation. Only trim sentence marks for named targets.
    opening = re.fullmatch(r'(?:abre|abrir|abras|abreme|ábreme|inicia|ejecuta)\s+(?:(?:la|el)\s+)?(.+)', raw, re.I)
    if opening:
        target = opening[1].strip()
        name = plain(target).rstrip('.!?')
        if name in SITES:
            return {'match': 'exact', 'command_id': 'axx.desktop.open_url', 'inputs': {'url': SITES[name]}}
        for key, (_, _, aliases) in APPS.items():
            if name in aliases:
                return {'match': 'exact', 'command_id': 'axx.desktop.open_app', 'inputs': {'app': key}}
        if re.match(r'https?://', target, re.I) or re.fullmatch(r'(?:[\w-]+\.)+[A-Za-z]{2,}(?:[/?:#].*)?', target):
            url = target if re.match(r'https?://', target, re.I) else 'https://' + target
            validate_url(url)
            return {'match': 'exact', 'command_id': 'axx.desktop.open_url', 'inputs': {'url': url}}
        return {'match': 'unsupported', 'message': 'No tengo un acceso configurado para esa aplicación. Puedo abrir YouTube, páginas web, calculadora, bloc de notas, Paint y explorador. Para un comando concreto escribe /powershell seguido del comando y revisa la aprobación.'}
    search = re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+en\s+(youtube|google|bing|duckduckgo|internet)\s+(.+)', raw, re.I)
    if search:
        engine, query = search[1].lower(), search[2]
    else:
        search = re.fullmatch(r'(?:busca|buscar|buscame|búscame)\s+(.+?)\s+en\s+(youtube|google|bing|duckduckgo|internet)[.!?]*', raw, re.I)
        if not search:
            return None
        query, engine = search[1], search[2].lower()
    return {'match': 'exact', 'command_id': 'axx.desktop.search', 'inputs': {'engine': 'google' if engine == 'internet' else engine, 'query': query}}


def open_target(kind, inputs):
    validate_inputs(kind, inputs)
    if os.name != 'nt':
        raise ValueError('Esta acción requiere Axx para Windows.')
    if kind == 'open_app':
        label, relative, _ = APPS[inputs['app']]
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
    os.startfile(target)
    # ShellExecute acceptance is observable; page load/window visibility is not.
    return {'success': True, 'output': {'target': target, 'label': label},
            'evidence': {'verification': 'os_handoff', 'target': target, 'accepted': True}}


def run_powershell(inputs, workspace, cancelled):
    validate_inputs('powershell', inputs)
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if os.name != 'nt' or not executable.is_file():
        raise ValueError('PowerShell de Windows no está disponible.')
    # Fixed encoding/error setup plus the exact user-reviewed script; no language-model output.
    script = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; $ErrorActionPreference = 'Stop';\n" + inputs['script']
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    runtime_names = {'systemroot', 'windir', 'path', 'temp', 'tmp', 'userprofile', 'appdata', 'localappdata',
                     'programdata', 'programfiles', 'programfiles(x86)', 'commonprogramfiles', 'comspec',
                     'number_of_processors', 'processor_architecture', 'username', 'computername'}
    env = {key: value for key, value in os.environ.items() if key.lower() in runtime_names}
    if cancelled.is_set():
        return {'success': False, 'error': 'Comando cancelado antes de ejecutar.', 'evidence': {'cancelled': True}}
    process, job = spawn_managed_process([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-EncodedCommand', encoded],
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
    output = {'stdout': bytes(buffers[0]).decode('utf-8', errors='replace'), 'stderr': bytes(buffers[1]).decode('utf-8', errors='replace'), 'exit_code': process.returncode}
    return {'success': reason is None and process.returncode == 0, 'output': output,
            'error': reason or (f'PowerShell terminó con código {process.returncode}.' if process.returncode else None),
            'evidence': {'exit_code': process.returncode, 'cancelled': cancelled.is_set(), 'verification': 'process_exit', 'cwd': str(workspace)}}
