"""Private gateway configuration; absence selects direct MCP, invalid data never does."""
import ipaddress
import json
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit


CONFIG_NAME = 'native-gateway.dpapi'
GATEWAY_TOOL = 'axx_windows_native_execute'


def checked_gateway_config(value):
    fields = {'version', 'listen_host', 'listen_port', 'allowed_peer', 'native_token', 'gateway_url', 'gateway_token'}
    if not isinstance(value, dict) or set(value) != fields or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Configuración de gateway Windows incompatible')
    for field in ('listen_host', 'allowed_peer'):
        if not isinstance(value[field], str):
            raise ValueError('La dirección WSL debe ser texto IPv4')
        address = ipaddress.ip_address(value[field])
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
            raise ValueError('Windows requiere direcciones privadas de WSL')
    if value['listen_host'] == value['allowed_peer']:
        raise ValueError('Windows y WSL deben tener direcciones distintas')
    if type(value['listen_port']) is not int or not 1 <= value['listen_port'] <= 65535:
        raise ValueError('Puerto nativo inválido')
    if not isinstance(value['gateway_url'], str):
        raise ValueError('Endpoint de gateway inválido')
    url = urlsplit(value['gateway_url'])
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port
            or url.username or url.password or url.query or url.fragment
            or not re.fullmatch(r'/mcp/[A-Za-z0-9_-]{1,100}', url.path)):
        raise ValueError('El gateway Windows requiere un servidor MCP loopback explícito')
    for field in ('native_token', 'gateway_token'):
        if not isinstance(value[field], str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', value[field]):
            raise ValueError('Credencial de gateway inválida')
    return dict(value)


def verify_wsl_network(config):
    import psutil
    for name, addresses in psutil.net_if_addrs().items():
        if 'wsl' not in name.casefold() or 'vethernet' not in name.casefold():
            continue
        for address in addresses:
            if address.family == socket.AF_INET and address.address == config['listen_host'] and address.netmask:
                network = ipaddress.ip_network(address.address + '/' + address.netmask, strict=False)
                if ipaddress.ip_address(config['allowed_peer']) in network:
                    return
    raise ValueError('La red WSL cambió; vuelve a configurar el gateway Windows')


def load_gateway_config(state_dir):
    if state_dir is None:
        return None
    path = Path(state_dir) / CONFIG_NAME
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError('Configuración privada de gateway inválida')
    from backend.auth.chatgpt_auth import _dpapi_decrypt
    return checked_gateway_config(json.loads(_dpapi_decrypt(path.read_bytes())))
