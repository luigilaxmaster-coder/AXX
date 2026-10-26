"""Prepare or start the private local AnythingMCP stack; never overwrite its secrets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import re
import shutil
import subprocess
import sys
import urllib.request


IMAGES = {
    'app': 'helpcodeai/anythingmcp@sha256:b53b9192e46d3dfd236200a64977b659c4c4f378ea08335deaf76e48bfb2eb98',
    'postgres': 'postgres@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b',
}
# Axx admission budget, not an upstream minimum: leave room for two images and the database.
MIN_FREE = 8 * 1024 ** 3


def compose():
    return {'name': 'axx-anythingmcp', 'services': {
        'app': {'image': IMAGES['app'], 'platform': 'linux/amd64',
            'ports': ['127.0.0.1:3000:3000', '127.0.0.1:4000:4000'],
            'environment': {
                'NODE_ENV': 'production', 'PORT': '4000',
                'NEXT_PUBLIC_API_URL': 'http://localhost:4000',
                'DATABASE_URL': 'postgresql://amcp:${POSTGRES_PASSWORD:?required}@postgres:5432/anythingmcp',
                'JWT_SECRET': '${JWT_SECRET:?required}', 'ENCRYPTION_KEY': '${ENCRYPTION_KEY:?required}',
                'CORS_ORIGIN': 'http://localhost:3000', 'SERVER_URL': 'http://localhost:4000',
                'FRONTEND_URL': 'http://localhost:3000', 'MCP_AUTH_MODE': 'legacy',
                'MCP_ALLOW_ANONYMOUS': 'false', 'ALLOW_OPEN_REGISTRATION': 'false'},
            'depends_on': {'postgres': {'condition': 'service_healthy'}},
            'healthcheck': {'test': ['CMD', 'wget', '--no-verbose', '--tries=1', '--spider', 'http://localhost:4000/health'],
                            'interval': '5s', 'timeout': '5s', 'retries': 20, 'start_period': '20s'},
            'restart': 'unless-stopped'},
        'postgres': {'image': IMAGES['postgres'], 'volumes': ['postgres_data:/var/lib/postgresql/data'],
            'environment': {'POSTGRES_USER': 'amcp', 'POSTGRES_PASSWORD': '${POSTGRES_PASSWORD:?required}', 'POSTGRES_DB': 'anythingmcp'},
            'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U amcp -d anythingmcp'], 'interval': '3s', 'timeout': '3s', 'retries': 10},
            'restart': 'unless-stopped'}}, 'volumes': {'postgres_data': {}}}


def protect(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
        raise ValueError('La carpeta privada no puede ser un enlace')
    if os.name == 'nt':
        import win32api
        import win32security
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
        try: sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
        finally: token.Close()
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        folder.chmod(0o700)


def prepare(folder):
    protect(folder)
    env = folder / '.env'
    if env.is_symlink(): raise ValueError('El archivo privado no puede ser un enlace')
    if not env.exists():
        with env.open('x', encoding='ascii') as output:
            for key in ('JWT_SECRET', 'ENCRYPTION_KEY', 'POSTGRES_PASSWORD'):
                output.write(key + '=' + secrets.token_hex(32) + '\n')
        if os.name != 'nt': env.chmod(0o600)
    else:
        values = dict(line.split('=', 1) for line in env.read_text(encoding='ascii').splitlines() if '=' in line)
        if any(len(values.get(key, '')) != 64 or any(c not in '0123456789abcdef' for c in values[key])
               for key in ('JWT_SECRET', 'ENCRYPTION_KEY', 'POSTGRES_PASSWORD')):
            raise ValueError('Configuración privada existente incompatible; se conserva sin reemplazar')
    target = folder / 'compose.json'
    if target.is_symlink(): raise ValueError('La configuración no puede ser un enlace')
    target.write_text(json.dumps(compose(), indent=2) + '\n', encoding='utf-8')
    return target


def docker_command(distribution=None):
    if distribution:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', distribution): raise ValueError('Distribución WSL inválida')
        wsl = shutil.which('wsl')
        return [wsl, '-d', distribution, '-u', 'root', '--exec', 'docker'] if wsl else []
    docker = shutil.which('docker')
    return [docker] if docker else []


def wsl_keeper(folder, distribution, start=True):
    """WSL systemd alone does not keep a distribution alive after the CLI exits."""
    if not distribution: return
    import psutil
    command = [shutil.which('wsl'), '-d', distribution, '--exec', 'sleep', 'infinity']
    path = folder/'keeper.json'
    process = None
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            candidate = psutil.Process(saved['pid'])
            actual = candidate.cmdline()
            if (actual and os.path.normcase(actual[0]) == os.path.normcase(command[0]) and actual[1:] == command[1:]
                    and candidate.create_time() == saved['created_at']):
                process = candidate
        except (OSError, ValueError, KeyError, psutil.Error): pass
    if start and process is None:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        process = psutil.Process(child.pid)
        path.write_text(json.dumps({'pid': process.pid, 'created_at': process.create_time()}), encoding='utf-8')
    elif not start and process is not None:
        for child in reversed(process.children(recursive=True)):
            try: child.terminate()
            except psutil.NoSuchProcess: pass
        process.terminate()
        process.wait(timeout=5)


def preflight(folder, distribution=None):
    reasons = []
    free = shutil.disk_usage(folder).free
    if free < MIN_FREE: reasons.append('Espacio libre inferior al presupuesto de Axx (8 GiB)')
    docker = docker_command(distribution)
    if not docker:
        reasons.append('Docker no está instalado o no figura en PATH')
    else:
        try:
            result = subprocess.run(docker + ['version', '--format', '{{json .Server}}'], capture_output=True, text=True, timeout=15)
            server = json.loads(result.stdout) if result.returncode == 0 else None
            if not server or server.get('Os') != 'linux' or int(server['Version'].split('.')[0]) < 24:
                reasons.append('Se requiere un motor Docker Linux 24+ activo')
            subprocess.run(docker + ['compose', 'version'], check=True, capture_output=True, timeout=15)
        except (ValueError, KeyError, subprocess.SubprocessError): reasons.append('Docker Compose o su motor no están disponibles')
    return {'ready_to_start': not reasons, 'free_bytes': free, 'blockers': reasons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'status', 'start', 'stop'))
    parser.add_argument('--directory', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Axx' / 'anythingmcp')
    parser.add_argument('--wsl-distribution', help='Usar el motor Docker de esta distribución WSL existente')
    args = parser.parse_args()
    folder = args.directory.absolute()
    if args.action in ('prepare', 'start'): prepare(folder)
    if not folder.exists(): raise ValueError('Ejecuta prepare antes de consultar el estado')
    if args.action == 'start': wsl_keeper(folder, args.wsl_distribution)
    report = preflight(folder, args.wsl_distribution)
    report.update(directory=str(folder), endpoint='http://127.0.0.1:4000/mcp', prepared=(folder/'compose.json').is_file())
    if args.action in ('start', 'stop'):
        if args.action == 'start' and not report['ready_to_start']:
            print(json.dumps(report, ensure_ascii=False, indent=2)); return 2
        engine = docker_command(args.wsl_distribution)
        engine_folder = str(folder)
        if args.wsl_distribution:
            engine_folder = subprocess.run(engine[:-1] + ['wslpath', '-a', str(folder)],
                check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        command = engine + ['compose', '--env-file', engine_folder + '/.env', '-f', engine_folder + '/compose.json']
        if args.action == 'stop':
            subprocess.run(command + ['stop'], check=True, timeout=60)
            wsl_keeper(folder, args.wsl_distribution, start=False)
            print(json.dumps({'stopped': True, 'data_preserved': True})); return 0
        subprocess.run(command + ['config', '--quiet'], check=True, timeout=30)
        subprocess.run(command + ['up', '-d', '--quiet-pull', '--wait', '--wait-timeout', '180'], check=True, timeout=240)
        with urllib.request.urlopen('http://127.0.0.1:4000/health', timeout=10) as response:
            report['api_health_http'] = response.status
        report['mcp_authenticated'] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('Preparación detenida: ' + type(exc).__name__ + '. Los secretos existentes se conservan.', file=sys.stderr)
        raise SystemExit(1)
