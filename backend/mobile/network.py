"""Read-only, bounded discovery of the explicitly selected mobile network."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


TAILSCALE_RANGE = ipaddress.ip_network('100.64.0.0/10')


def tailscale_status():
    executable = (str(Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tailscale' / 'tailscale.exe')
                  if os.name == 'nt' else shutil.which('tailscale'))
    if not executable or not Path(executable).is_file():
        raise RuntimeError('Instala Tailscale en la PC y en el teléfono e inicia sesión en la misma red privada.')
    result = subprocess.run([executable, 'status', '--json'], capture_output=True, text=True,
                            timeout=3, check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if len(result.stdout) > 1024 * 1024:
        raise RuntimeError('Tailscale devolvió un estado demasiado grande.')
    try:
        value = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError('Tailscale no responde. Abre Tailscale y comprueba que esté conectado.') from exc
    if not isinstance(value, dict):
        raise RuntimeError('Tailscale devolvió un estado inválido.')
    return value


class MobileNetwork:
    def __init__(self, lan_resolver, tailscale_probe=tailscale_status):
        self.lan_resolver = lan_resolver
        self.tailscale_probe = tailscale_probe
        self.lock = threading.Lock()
        self.cached = None
        self.checked_at = 0

    @staticmethod
    def validate_mode(mode):
        if mode not in ('lan', 'tailscale'):
            raise ValueError('Selecciona Red local o Tailscale.')
        return mode

    def status(self, mode, *, refresh=False):
        self.validate_mode(mode)
        if mode == 'lan':
            try:
                return {'mode': mode, 'ready': True, 'address': self.lan_resolver(),
                        'message': 'Red local: conecta el teléfono al mismo Wi-Fi que la PC.'}
            except (OSError, RuntimeError, ValueError):
                return {'mode': mode, 'ready': False,
                        'message': 'No hay una red local disponible. Conecta la PC a una red privada.'}
        with self.lock:
            if not refresh and self.cached and time.monotonic() - self.checked_at < 10:
                return dict(self.cached)
            result = {'mode': mode, 'ready': False}
            try:
                value = self.tailscale_probe()
                if value.get('BackendState') != 'Running':
                    raise RuntimeError('Abre Tailscale en la PC e inicia sesión; conecta el teléfono a la misma red privada de Tailscale.')
                own = value.get('Self') or {}
                if own.get('Online') is not True:
                    raise RuntimeError('La PC está desconectada de Tailscale. Activa Tailscale en ambos dispositivos.')
                addresses = value.get('TailscaleIPs') or own.get('TailscaleIPs') or []
                for raw in addresses:
                    address = ipaddress.ip_address(raw)
                    if address.version == 4 and address in TAILSCALE_RANGE:
                        result.update(ready=True, address=str(address),
                                      message='Tailscale conectado. Mantén Tailscale activo en el teléfono y escanea este QR de Axx.')
                        break
                if not result['ready']:
                    raise RuntimeError('Tailscale aún no tiene una dirección IPv4 privada. Espera a que conecte y vuelve a intentarlo.')
            except (OSError, RuntimeError, ValueError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
                result['message'] = str(exc) if isinstance(exc, RuntimeError) else 'No se pudo consultar Tailscale. Abre Tailscale y vuelve a intentarlo.'
            self.cached, self.checked_at = result, time.monotonic()
            return dict(result)

    def resolve(self, mode):
        result = self.status(mode, refresh=True)
        if not result['ready']:
            raise RuntimeError(result['message'])
        return result['address']
