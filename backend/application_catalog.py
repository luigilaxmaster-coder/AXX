"""Documented application profiles joined to exact Windows Start inventory IDs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys

from backend.actions.command_language import plain
from backend.actions.windows_apps import installed_apps


def _normalized(value):
    return ' '.join(plain(value).split())


def _text(value, limit=2000):
    if not isinstance(value, str) or not 0 < len(value) <= limit or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError('Texto de catálogo inválido')
    value.encode('utf-8')
    return value


def _strings(value, limit=2000):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError('Lista de catálogo inválida')
    return [_text(item, limit) for item in value]


def _terms(profile):
    return {_normalized(value) for value in [profile['id'], profile['title'],
        *profile['aliases'], *profile['process_names']]}


def profiles():
    """Return fresh public metadata; a profile never proves installation or execution."""
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    path = root/'resources/application-profiles.json'
    if path.stat().st_size > 512 * 1024:
        raise ValueError('El catálogo por aplicación excede su límite')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'version', 'profiles'} or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Formato del catálogo por aplicación incompatible')
    rows = data['profiles']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('Número de perfiles inválido')
    ids, owners = set(), {}
    for profile in rows:
        if not isinstance(profile, dict) or set(profile) != {'id', 'title', 'aliases', 'process_names', 'commands', 'instructions'}:
            raise ValueError('Perfil de aplicación incompatible')
        key = _text(profile['id'], 64)
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key) or key in ids:
            raise ValueError('Identidad de perfil inválida o repetida')
        ids.add(key)
        _text(profile['title'], 160)
        _strings(profile['aliases'], 160)
        _strings(profile['process_names'], 120)
        _strings(profile['instructions'])
        if any(not re.fullmatch(r'[^\\/:*?"<>|]{1,110}\.(?:exe|bin)', name, re.I) for name in profile['process_names']):
            raise ValueError('Nombre de proceso inválido')
        for term in _terms(profile):
            if term in owners and owners[term] != key:
                raise ValueError('Alias de aplicación ambiguo: '+term)
            owners[term] = key
        commands = profile['commands']
        if not isinstance(commands, list) or len(commands) > 30:
            raise ValueError('Lista de operaciones inválida')
        command_ids = set()
        for command in commands:
            required = {'id', 'title', 'kind', 'description', 'verification'}
            if not isinstance(command, dict) or not required <= set(command) or set(command)-required-{'names', 'keys', 'requires_text', 'requires_connection'}:
                raise ValueError('Operación de aplicación incompatible')
            command_id = _text(command['id'], 64)
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', command_id) or command_id in command_ids:
                raise ValueError('Identidad de operación inválida o repetida')
            command_ids.add(command_id)
            for field in ('title', 'description', 'verification'):
                _text(command[field])
            if command['kind'] not in ('invoke', 'navigate', 'shortcut', 'guide'):
                raise ValueError('Tipo de operación desconocido')
            for field in ('requires_text', 'requires_connection'):
                if field in command and type(command[field]) is not bool:
                    raise ValueError('Requisito de operación inválido')
            for field in ('names', 'keys'):
                if field in command:
                    _strings(command[field], 200)
            if command['kind'] in ('invoke', 'navigate') and not command.get('names'):
                raise ValueError('La operación requiere selectores observables')
            if command['kind'] == 'shortcut' and not command.get('keys'):
                raise ValueError('El atajo requiere teclas explícitas')
    return rows


def _profile_for(query, rows):
    term = _normalized(query)
    matches = [profile for profile in rows if term in _terms(profile)]
    if len(matches) > 1:
        raise ValueError('Perfil de aplicación ambiguo')
    return matches[0] if matches else None


def profile_for(query):
    """Resolve only an exact documented ID, title, alias or process filename."""
    return _profile_for(_text(query, 1024), profiles())


def _inventory():
    rows = installed_apps()
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Inventario de aplicaciones inválido')
    for app in rows:
        if not isinstance(app, dict):
            raise ValueError('Aplicación de inventario inválida')
        _text(app.get('name'), 512)
        _text(app.get('app_id'), 1024)
    return copy.deepcopy(rows)


def _matches(profile, app):
    return _normalized(app['name']) in _terms(profile)


def installed_catalog():
    """Read metadata and the bounded existing inventory; never launch applications."""
    apps, rows = _inventory(), profiles()
    observed = [(_normalized(app['name']), app) for app in apps]
    joined = []
    for profile in rows:
        terms = _terms(profile)
        joined.append(dict(profile, installed_matches=[copy.deepcopy(app) for name, app in observed if name in terms]))
    return {'profiles': joined, 'applications': apps}


def resolve_application(query):
    """Use an exact observed AppID/name or an exact profile alias; never fuzzy-match."""
    raw = _text(query, 1024).strip()
    apps, rows = _inventory(), profiles()
    matches = [app for app in apps if app['app_id'] == raw]
    if not matches:
        matches = [app for app in apps if _normalized(app['name']) == _normalized(raw)]
    profile = _profile_for(raw, rows)
    if not matches and profile:
        matches = [app for app in apps if _matches(profile, app)]
    unique = {app['app_id']: app for app in matches}
    if len(unique) != 1:
        candidates = [{'name': app['name'], 'app_id': app['app_id']} for app in list(unique.values())[:10]]
        reason = 'Hay varias aplicaciones' if unique else 'La aplicación no figura en el inventario'
        raise ValueError(reason+'; selecciona un nombre o AppID exacto. Candidatos: '+json.dumps(candidates, ensure_ascii=False))
    app = next(iter(unique.values()))
    if profile and not _matches(profile, app):
        candidate = json.dumps({'name': app['name'], 'app_id': app['app_id']}, ensure_ascii=False)
        raise ValueError('Identidad de aplicación ambigua entre un perfil y un AppID observado. Candidato: '+candidate)
    return {'profile': _profile_for(app['name'], rows), 'app': app}
