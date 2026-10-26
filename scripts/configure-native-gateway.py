"""Provision the private Windows MCP route without logging or replacing user credentials."""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.mcp_host.native_gateway import CONFIG_NAME, GATEWAY_TOOL, checked_gateway_config, verify_wsl_network

spec = importlib.util.spec_from_file_location('anythingmcp_local', ROOT/'scripts/anythingmcp-local.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)

CONNECTOR_NAME = 'Axx Windows native'
SERVER_NAME = 'Axx Windows admitted operations'
MANAGED = 'Managed by Axx native gateway setup v1'
STATE_NAME = 'native-provisioning-state.dpapi'


class SetupError(RuntimeError):
    pass


class Rejected(SetupError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def checked_file(path):
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
        raise SetupError('La configuración privada no admite enlaces')
    return path


def checked_data_dir(path):
    directory = checked_file(Path(path)).resolve()
    if any((parent/'.git').exists() for parent in (directory, *directory.parents)):
        raise SetupError('La configuración privada debe guardarse fuera de un repositorio Git')
    return directory


def read_private(path):
    checked_file(path)
    if path.stat().st_size > 1024 * 1024:
        raise SetupError('La configuración privada excede su límite')
    return json.loads(_dpapi_decrypt(path.read_bytes()))


def write_private(path, value):
    write_private_bytes(path, json.dumps(value, ensure_ascii=True, allow_nan=False).encode())


def write_private_bytes(path, value):
    checked_file(path)
    raw = _dpapi_encrypt(value)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name+'.', delete=False) as output:
            temporary = Path(output.name)
            output.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def resource_id(row):
    value = row.get('id') if isinstance(row, dict) else None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise SetupError('AnythingMCP devolvió una identidad inválida')
    return value


class Api:
    def __init__(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token):
            raise SetupError('Renueva la sesión administrativa de AnythingMCP')
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def __call__(self, method, route, body=None):
        if not re.fullmatch(r'[A-Za-z0-9_/-]+', route):
            raise SetupError('Ruta administrativa inválida')
        request = urllib.request.Request('http://127.0.0.1:4000/api/'+route,
            data=None if body is None else json.dumps(body, allow_nan=False).encode(), method=method,
            headers={'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise SetupError('Respuesta administrativa excesiva; revisa la operación antes de repetir')
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise Rejected('La sesión administrativa caducó; renueva la sesión sin cambiar las credenciales') from None
            if error.code < 500:
                raise Rejected(f'AnythingMCP rechazó la solicitud: HTTP {error.code}') from None
            raise SetupError('Fallo administrativo; resultado incierto, revisa el estado antes de repetir') from None
        except (OSError, TimeoutError, ValueError):
            raise SetupError('Transporte administrativo interrumpido; revisa el estado antes de repetir') from None


def login(data_dir):
    if os.name != 'nt':
        raise SetupError('La sesión privada requiere Windows y DPAPI')
    folder = checked_data_dir(data_dir)/'anythingmcp'
    local.protect(folder)
    email = input('Correo de AnythingMCP: ').strip()
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            password = getpass.getpass('Contraseña de AnythingMCP: ')
        except (getpass.GetPassWarning, EOFError):
            raise SetupError('Abre una terminal interactiva que permita introducir la contraseña sin eco') from None
    if not email or len(email) > 320 or any(char in email for char in '\r\n') or not password or len(password) > 8192:
        raise SetupError('Indica correo y contraseña válidos')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request('http://127.0.0.1:4000/api/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise SetupError('Respuesta de inicio de sesión excesiva')
            result = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise Rejected(f'AnythingMCP rechazó el inicio de sesión: HTTP {error.code}') from None
    except (OSError, TimeoutError, ValueError):
        raise SetupError('No se pudo confirmar el inicio de sesión; la sesión previa se conserva') from None
    token = result.get('accessToken') if isinstance(result, dict) else None
    Api(token)
    write_private_bytes(folder/'administrator-session.dpapi', token.encode())
    return {'authenticated': True}


def detect_network(distribution):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', distribution):
        raise SetupError('Distribución WSL inválida')
    wsl = shutil.which('wsl')
    if not wsl:
        raise SetupError('WSL no está disponible')
    command = [wsl, '-d', distribution, '--exec', 'ip', '-json', '-4']
    routes = json.loads(subprocess.run(command+['route', 'show', 'default'], check=True,
        capture_output=True, text=True, timeout=10).stdout)
    addresses = json.loads(subprocess.run(command+['address', 'show', 'dev', 'eth0'], check=True,
        capture_output=True, text=True, timeout=10).stdout)
    hosts = {row['gateway'] for row in routes if row.get('dev') == 'eth0' and row.get('gateway')}
    peers = {info['local'] for row in addresses for info in row.get('addr_info', []) if info.get('family') == 'inet'}
    if len(hosts) != 1 or len(peers) != 1:
        raise SetupError('No hay una ruta IPv4 WSL única')
    network = {'listen_host': hosts.pop(), 'allowed_peer': peers.pop()}
    for value in network.values():
        address = ipaddress.ip_address(value)
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
            raise SetupError('La ruta WSL debe usar direcciones privadas')
    verify_wsl_network(network)
    return network


class Provisioner:
    def __init__(self, data_dir, api):
        self.data_dir, self.api = checked_data_dir(data_dir), api
        self.folder = self.data_dir/'anythingmcp'
        self.path = self.folder/STATE_NAME
        self.config_path = self.data_dir/CONFIG_NAME
        local.protect(self.folder)
        self.state = read_private(self.path) if self.path.exists() else {'version': 1}
        if not isinstance(self.state, dict) or type(self.state.get('version')) is not int or self.state['version'] != 1:
            raise SetupError('Estado de provisión incompatible; se conserva sin reemplazar')
        if self.state.get('pending_write'):
            raise SetupError('Hay una escritura anterior sin confirmar; reconcilia sus recursos antes de repetir')

    def save(self):
        write_private(self.path, self.state)

    def mutate(self, method, route, body, remember=None):
        self.state['pending_write'] = {'method': method, 'route': route}
        self.save()
        try:
            result = self.api(method, route, body)
        except Rejected:
            self.state.pop('pending_write')
            self.save()
            raise
        if remember:
            self.state.update(remember(result))
        self.state.pop('pending_write')
        self.save()
        return result

    def ensure(self, route, state_key, name, payload):
        key = self.state.get(state_key)
        if key:
            row = self.api('GET', route+'/'+resource_id({'id': key}))
            if row.get('name') != name:
                raise SetupError('El recurso guardado cambió de identidad; se conserva sin modificar')
        else:
            matches = [item for item in self.api('GET', route) if item.get('name') == name]
            marker = 'instructions' if route == 'connectors' else 'description'
            if len(matches) > 1 or (matches and matches[0].get(marker) != MANAGED):
                raise SetupError('El nombre reservado ya está ocupado; revisa los recursos existentes')
            if matches:
                row = matches[0]
                self.state[state_key] = resource_id(row)
                self.save()
            else:
                row = self.mutate('POST', route, dict(payload, name=name),
                    lambda result: {state_key: resource_id(result)})
        return row

    def configure(self, network):
        verify_wsl_network(network)
        checked_file(self.config_path)
        previous = checked_gateway_config(read_private(self.config_path)) if self.config_path.exists() else None
        if previous:
            for field in ('native_token', 'listen_port', 'gateway_token'):
                self.state.setdefault(field, previous[field])
            self.state.setdefault('server_id', previous['gateway_url'].rsplit('/', 1)[1])
        self.state.setdefault('native_token', secrets.token_urlsafe(32))
        if 'listen_port' not in self.state:
            with socket.socket() as listener:
                if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                listener.bind((network['listen_host'], 0))
                self.state['listen_port'] = listener.getsockname()[1]
        if type(self.state['listen_port']) is not int or not 1 <= self.state['listen_port'] <= 65535:
            raise SetupError('Puerto nativo guardado inválido')
        if not isinstance(self.state['native_token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', self.state['native_token']):
            raise SetupError('Credencial nativa guardada inválida')
        self.save()
        settings = self.api('GET', 'admin/settings/ssrf-allowed-hosts')
        hosts = settings.get('hosts') if isinstance(settings, dict) else None
        if not isinstance(hosts, list) or any(not isinstance(host, str) for host in hosts):
            raise SetupError('Lista SSRF existente incompatible; no se reemplazará')
        if network['listen_host'] not in hosts:
            self.mutate('PUT', 'admin/settings/ssrf-allowed-hosts', {'hosts': hosts+[network['listen_host']]})
        native_url = f"http://{network['listen_host']}:{self.state['listen_port']}/mcp"
        payload = {'type': 'MCP', 'baseUrl': native_url, 'authType': 'BEARER_TOKEN',
                   'authConfig': {'token': self.state['native_token']}, 'instructions': MANAGED}
        connector = self.ensure('connectors', 'connector_id', CONNECTOR_NAME, payload)
        connector_id = resource_id(connector)
        if (not self.state.get('connector_auth_configured')
                or any(connector.get(field) != payload[field] for field in ('baseUrl', 'authType', 'instructions'))):
            self.mutate('PUT', 'connectors/'+connector_id, {key: value for key, value in payload.items() if key != 'type'},
                lambda result: {'connector_auth_configured': True})
        self.remove_default_attachment(connector_id)
        tool_payload = {'description': MANAGED, 'parameters': {'type': 'object',
            'properties': {'ticket': {'type': 'string'}}, 'required': ['ticket'], 'additionalProperties': False},
            'endpointMapping': {'method': 'axx_native_execute', 'bodyMapping': {'ticket': '$ticket'}},
            'responseMapping': {'cacheTtl': 0}}
        tool_route = 'connectors/'+connector_id+'/tools'
        tool = self.ensure(tool_route, 'tool_id', GATEWAY_TOOL, tool_payload)
        if not tool.get('isEnabled') or any(tool.get(field) != value for field, value in tool_payload.items()):
            self.mutate('PUT', tool_route+'/'+resource_id(tool), dict(tool_payload, isEnabled=True))
        server = self.ensure('mcp-servers', 'server_id', SERVER_NAME,
            {'slug': 'axx-windows-native', 'description': MANAGED})
        server_id = resource_id(server)
        existing = connector_ids(self.api('GET', 'mcp-servers/'+server_id))
        if set(existing)-{connector_id}:
            raise SetupError('El servidor Windows contiene conectores ajenos; se conserva sin modificar')
        if existing != [connector_id]:
            self.mutate('PUT', 'mcp-servers/'+server_id+'/connectors', {'connectorIds': [connector_id]})
        if 'gateway_token' not in self.state:
            def remember_key(result):
                key = result.get('key')
                if not isinstance(key, str) or not re.fullmatch(r'mcp_[A-Za-z0-9_-]{28,252}', key):
                    raise SetupError('Respuesta de clave incompatible; reconcilia la escritura antes de repetir')
                return {'gateway_token': key}
            self.mutate('POST', 'mcp-keys', {'name': 'Axx Windows native route', 'mcpServerId': server_id}, remember_key)
        config = checked_gateway_config(dict(version=1, **network, listen_port=self.state['listen_port'],
            native_token=self.state['native_token'], gateway_url='http://127.0.0.1:4000/mcp/'+server_id,
            gateway_token=self.state['gateway_token']))
        verify_wsl_network(config)
        write_private(self.config_path, config)
        return {'state': 'configured_not_runtime_verified', 'restart_required': True,
                'listen_host': config['listen_host'], 'listen_port': config['listen_port'], 'gateway_url': config['gateway_url']}

    def remove_default_attachment(self, connector_id):
        for server in self.api('GET', 'mcp-servers'):
            if server.get('slug') != 'default':
                continue
            route = 'mcp-servers/'+resource_id(server)
            ids = connector_ids(self.api('GET', route))
            if connector_id in ids:
                self.mutate('PUT', route+'/connectors', {'connectorIds': [key for key in ids if key != connector_id]})


def connector_ids(server):
    rows = server.get('connectors') if isinstance(server, dict) else None
    if not isinstance(rows, list):
        raise SetupError('Relaciones de servidor incompatibles; se conservan sin reemplazar')
    ids = [resource_id({'id': row.get('connectorId')}) for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or len(set(ids)) != len(ids):
        raise SetupError('Relaciones de servidor inválidas; se conservan sin reemplazar')
    return ids


def status(data_dir):
    path = checked_data_dir(data_dir)/CONFIG_NAME
    if not path.exists():
        return {'state': 'direct_after_restart', 'configured': False}
    try:
        config = checked_gateway_config(read_private(path))
        verify_wsl_network(config)
    except (OSError, ValueError, RuntimeError):
        return {'state': 'blocked', 'configured': True, 'reason': 'Invalid configuration or changed WSL network'}
    return {'state': 'configured_not_runtime_verified', 'configured': True,
            'listen_host': config['listen_host'], 'listen_port': config['listen_port'], 'gateway_url': config['gateway_url']}


def disable(data_dir):
    directory = checked_data_dir(data_dir)
    path = checked_file(directory/CONFIG_NAME)
    if not path.exists():
        return {'state': 'direct_after_restart', 'restart_required': True}
    backup = directory/f'native-gateway.disabled-{time.time_ns()}.dpapi'
    os.replace(path, backup)
    return {'state': 'direct_after_restart', 'restart_required': True, 'backup': str(backup), 'gateway_resources_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('login', 'configure', 'status', 'disable'))
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Axx')
    parser.add_argument('--wsl-distribution', default='Ubuntu-24.04')
    args = parser.parse_args()
    args.data_dir = checked_data_dir(args.data_dir)
    if args.action == 'login':
        result = login(args.data_dir)
    elif args.action == 'status':
        result = status(args.data_dir)
    elif args.action == 'disable':
        result = disable(args.data_dir)
    else:
        if os.name != 'nt':
            raise SetupError('La provisión del gateway Windows requiere Windows y DPAPI')
        folder = args.data_dir/'anythingmcp'
        checked_file(folder)
        session = checked_file(folder/'administrator-session.dpapi')
        if not session.is_file():
            raise SetupError('Renueva la sesión administrativa de AnythingMCP antes de configurar')
        if session.stat().st_size > 16384:
            raise SetupError('La sesión administrativa excede su límite')
        token = _dpapi_decrypt(session.read_bytes()).decode()
        result = Provisioner(args.data_dir, Api(token)).configure(detect_network(args.wsl_distribution))
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SetupError as error:
        print('Configuración detenida: '+str(error), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print('Configuración detenida: '+type(error).__name__+'. La configuración previa se conserva.', file=sys.stderr)
        raise SystemExit(1)
