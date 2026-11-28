"""Subscription metadata only: official account status and opt-in CLI status lines.

Never reads credential stores, issues prompts or estimates allowances from time.
Status-line receipts are client reports, not proof of a billing entitlement.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .session_transport import claude_environment, claude_executable, claude_usage

LOG = logging.getLogger(__name__)
PROVIDERS = ('codex', 'claude', 'antigravity')
MAX_BYTES = 65536


def plan_name(value):
    if not isinstance(value, str) or not 0 < len(value) <= 60:
        return None
    return value.strip() if all(c.isalnum() or c in ' ._+-' for c in value) else None


def unknown(provider, reason):
    return dict(provider=provider, plan=None, connection='unknown', source=None,
                checked_at=None, windows=[], available=False, reason=reason, stale=False)


def statusline_snapshot(provider, payload):
    if provider not in ('claude', 'antigravity') or not isinstance(payload, dict):
        raise ValueError('Proveedor o salida de estado inválidos.')
    result = unknown(provider, 'El cliente no ha informado cuotas numéricas.')
    result.update(source=f'{provider} statusLine', checked_at=time.time(),
                  verification='client_report', connection='reported',
                  plan=plan_name(payload.get('plan_tier')))
    if provider == 'claude':
        result.update(windows=claude_usage(payload)['windows'])
    else:
        if payload.get('product') != 'antigravity':
            raise ValueError('La salida no pertenece a Antigravity.')
        quota = payload.get('quota', {})
        if not isinstance(quota, dict):
            raise ValueError('Cuotas inválidas.')
        for key, entry in list(quota.items())[:20]:
            if not isinstance(entry, dict) or not plan_name(key):
                continue
            fraction = entry.get('remaining_fraction')
            if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
                continue
            reset = None
            try:
                reset = datetime.fromisoformat(entry.get('reset_time', '').replace('Z', '+00:00')).timestamp()
            except (ValueError, TypeError, AttributeError, OverflowError):
                pass
            result['windows'].append(dict(label=key, remaining_percent=round(fraction * 100, 2),
                window_minutes=10080 if 'weekly' in key else 300 if 'five-hour' in key else None,
                resets_at=reset, disabled=entry.get('disabled') is True))
    result['available'] = bool(result['windows'])
    return result


def save_statusline(directory, provider, payload):
    snapshot = statusline_snapshot(provider, payload)
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents readers from seeing half a CLI event.
    fd, temporary = tempfile.mkstemp(prefix=provider + '-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(snapshot, stream, allow_nan=False)
        os.replace(temporary, directory / f'{provider}.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return snapshot


def read_statusline(directory, provider):
    path = Path(directory) / f'{provider}.json'
    try:
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('provider') != provider or value.get('verification') != 'client_report':
            return None
        checked = value.get('checked_at')
        if type(checked) not in (int, float) or not math.isfinite(checked) or checked > time.time() + 60:
            return None
        # Re-project allowlisted fields. No account IDs, email or paths leave the adapter.
        windows = []
        for item in value.get('windows', [])[:20]:
            if not isinstance(item, dict):
                continue
            pct = item.get('remaining_percent')
            if type(pct) in (int, float) and math.isfinite(pct) and 0 <= pct <= 100:
                windows.append({k: item.get(k) for k in ('label', 'remaining_percent', 'window_minutes', 'resets_at', 'disabled')})
        stale = time.time() - checked > 300
        return dict(provider=provider, plan=plan_name(value.get('plan')), checked_at=checked,
                    windows=windows, source=f'{provider} statusLine', verification='client_report',
                    available=bool(windows), stale=stale, connection='stale' if stale else 'reported',
                    reason='Último estado recibido del cliente.' if stale else '')
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def claude_subscription():
    result = unknown('claude', 'Claude Code CLI no está instalado.')
    executable = claude_executable()
    if not executable:
        return result
    try:
        # Official non-inference subcommand; temporary streams bound memory and avoid
        # logging PII. Only the explicitly projected plan/auth flags are returned.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            completed = subprocess.run([executable, 'auth', 'status'], stdin=subprocess.DEVNULL,
                stdout=output, stderr=errors, env=claude_environment(), cwd=Path.home(),
                timeout=8, shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            output.seek(0); raw = output.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or completed.returncode not in (0, 1):
            raise ValueError('No status')
        value = json.loads(raw)
        authenticated = value.get('loggedIn') is True
        result.update(plan=plan_name(value.get('subscriptionType')), connection='connected' if authenticated else 'disconnected',
            checked_at=time.time(), source='claude auth status', verification='official_client',
            auth_method=value.get('authMethod') if value.get('authMethod') in ('claude.ai', 'oauth_token', 'api_key', 'api_key_helper', 'third_party', 'none') else None,
            reason='La CLI no expone saldo numérico aquí. Conecta su salida de estado para recibirlo.' if authenticated else 'Inicia sesión en la CLI oficial de Claude.')
        if result['auth_method'] not in ('claude.ai', 'oauth_token'):
            result['plan'] = None
            if authenticated:
                result['reason'] = 'La CLI usa acceso por API o de terceros; no confirma una suscripción de Claude.'
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        LOG.info('Claude subscription status unavailable')
        result['reason'] = 'No se pudo consultar la CLI de Claude. Vuelve a actualizar.'
    return result


def bridge_setup(directory, provider):
    if provider not in ('claude', 'antigravity'):
        raise ValueError('Este proveedor no usa un puente de estado.')
    import shlex
    args = [sys.executable]
    args += ['--subscription-statusline', provider] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve().parents[2] / 'scripts' / 'subscription-statusline.py'), provider]
    args += ['--state-dir', str(Path(directory).resolve())]
    if os.name == 'nt':
        # statusLine is interpreted by cmd.exe, not merely the C argv parser.
        # Quote every argument, including paths containing &, and reject cmd
        # expansion/control characters rather than generating unsafe setup text.
        if any(any(character in argument for character in '"%!\r\n\x00') for argument in args):
            raise ValueError('La ruta no se puede representar de forma segura en statusLine.')
        command = ' '.join('"' + argument + '\\' * (len(argument) - len(argument.rstrip('\\'))) + '"' for argument in args)
    else:
        command = shlex.join(args)
    return dict(provider=provider, configuration={'statusLine': {'type': 'command', 'command': command}},
        settings_file='~/.claude/settings.json' if provider == 'claude' else '~/.gemini/antigravity-cli/settings.json',
        documentation='https://code.claude.com/docs/en/statusline' if provider == 'claude' else 'https://antigravity.google/docs/cli/statusline/',
        instructions='Añade este bloque a los ajustes de la CLI. Conserva tu comando statusLine si ya tienes uno; no se ha modificado ningún archivo.',
        requires_running_client=True, configured=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Puente local de suscripción desde el statusLine oficial; no inicia inferencia.')
    parser.add_argument('provider', choices=('claude', 'antigravity'))
    parser.add_argument('--state-dir', required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Estado demasiado grande.')
        snapshot = save_statusline(args.state_dir, args.provider, json.loads(raw))
        print('AXX · ' + (snapshot['plan'] or 'Estado sincronizado'))
        return 0
    except (ValueError, OSError, TypeError):
        print('AXX · estado no disponible')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
