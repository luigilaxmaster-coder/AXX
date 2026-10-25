"""Windows Start application inventory, addressed by an observed application ID."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from difflib import SequenceMatcher

_cache = []
_updated = 0
_lock = threading.Lock()


def installed_apps(refresh=False):
    global _cache, _updated
    if os.name != 'nt':
        return []
    with _lock:
        if not refresh and time.monotonic() - _updated < 60:
            return list(_cache)
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        # Fixed inventory query only. User text never becomes PowerShell source.
        script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $ErrorActionPreference='Stop'; @(Get-StartApps | Select-Object Name,AppID) | ConvertTo-Json -Compress"
        try:
            result = subprocess.run([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise ValueError('Windows no pudo consultar las aplicaciones instaladas.')
            rows = json.loads(result.stdout.decode('utf-8-sig'))
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError('Inventario de aplicaciones inválido.')
            fresh = [{'name': r['Name'], 'app_id': r['AppID']} for r in rows
                     if isinstance(r, dict) and isinstance(r.get('Name'), str) and isinstance(r.get('AppID'), str)
                     and 0 < len(r['AppID']) <= 1024 and not any(ord(c) < 32 for c in r['AppID'])]
            if not fresh:
                raise ValueError('Inventario de aplicaciones vacío.')
        except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
            if _cache:
                _updated = time.monotonic()
                return list(_cache)
            raise
        _cache = fresh
        _updated = time.monotonic()
        return list(_cache)


def capability_status(app):
    """Keep installed-app discovery separate from per-action UIA readiness."""
    if not isinstance(app, dict) or not isinstance(app.get('name'), str) or not isinstance(app.get('app_id'), str):
        raise ValueError('Aplicación observada inválida.')
    return {**app, 'status': {'detected': True, 'registered_routes': ['axx.desktop.window.inspect', 'axx.desktop.window.set_value', 'axx.desktop.window.invoke'],
                             'generic_route_registered': True, 'app_specific_actions_validated': [],
                             'available': 'installed', 'control_availability': 'unknown'}}


def find_app(name, normalize):
    rows = installed_apps()
    exact = [row for row in rows if normalize(row['name']) == name]
    if exact:
        return exact
    partial = [row for row in rows if len(name) >= 3 and name in normalize(row['name'])]
    if partial:
        return partial
    # Speech recognition can alter one syllable. Only resolve a unique, strong
    # match to an application ID observed in the current Windows inventory.
    if len(name) < 5:
        return []
    ranked = sorted(((SequenceMatcher(None, name, normalize(row['name'])).ratio(), row) for row in rows),
                    key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 0.8 or (len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.15):
        return []
    return [ranked[0][1]]
