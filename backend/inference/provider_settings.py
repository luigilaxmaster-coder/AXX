"""User-managed endpoints. Credentials remain in the native backend, protected by DPAPI."""
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
import urllib.parse
import urllib.request

from .router import NoRedirect, Router, parse_strict_json, profile_id, source_context_reason
from backend.auth.chatgpt_auth import _dpapi_encrypt, _dpapi_decrypt

LOCK = threading.RLock()
PRESETS = {
    'ollama': ('http://127.0.0.1:11434/v1', 'openai'),
    'ollama_cloud': ('https://ollama.com/v1', 'openai'),
    'compat': ('http://127.0.0.1:1234/v1', 'openai'),
    'freellmapi': ('', 'openai'),
    'groq': ('https://api.groq.com/openai/v1', 'openai'),
    'anthropic': ('https://api.anthropic.com/v1', 'anthropic'),
    'openrouter': ('https://openrouter.ai/api/v1', 'openai'),
    'openai': ('https://api.openai.com/v1', 'openai'),
    'gemini': ('https://generativelanguage.googleapis.com/v1beta/openai', 'openai'),
    'custom': ('', 'openai'),
}

def local_address(host):
    if host == 'localhost':
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or (ip.is_private and not ip.is_link_local and not ip.is_unspecified and not ip.is_multicast)
    except ValueError:
        return False

def endpoint(value, kind):
    if kind not in PRESETS:
        raise ValueError('Proveedor no compatible')
    value = (value or PRESETS[kind][0]).strip().rstrip('/')
    if '://' not in value:
        value = 'http://' + value
    u = urllib.parse.urlsplit(value)
    if not u.hostname or u.username or u.password or u.query or u.fragment or u.scheme not in ('http', 'https'):
        raise ValueError('Usa una URL o IP sin claves, parámetros ni fragmentos')
    if u.scheme == 'http' and not local_address(u.hostname):
        raise ValueError('Los servicios de Internet requieren HTTPS; HTTP se admite para IP local o privada')
    if u.port is not None and not 1 <= u.port <= 65535:
        raise ValueError('Puerto inválido')
    if not u.path or u.path == '/':
        value += '/v1'
    return value

def credentials_dir(config_path):
    return Path(config_path).parent / 'credentials'

def load_credentials(config_path):
    if os.name != 'nt':
        return
    for file in credentials_dir(config_path).glob('AXX_API_*.bin'):
        try:
            os.environ[file.stem] = _dpapi_decrypt(file.read_bytes()).decode('utf-8')
        except Exception:
            # Unreadable keys remain unavailable; never log their content.
            continue

def public_entries(config):
    return [{k: p.get(k) for k in ('name', 'kind', 'base_url', 'model', 'enabled', 'protocol', 'billing_allowed',
                                 'free_confirmed', 'capabilities', 'tasks', 'context_window', 'image_context_tokens',
                                 'task_priority', 'quota_scope_id', 'scope_limit', 'gateway_free_model_ids',
                                 'gateway_attempt_limit', 'gateway_timeout_ms', 'gateway_profile_verified', 'gateway_keyless', 'candidate_only')}
            | {'cost_evidence': p.get('cost_evidence', 'unknown'), 'route_kind': p.get('route_kind', 'unknown')}
            | {'profile_id': profile_id(p), 'source_context_eligible': source_context_reason(p) == 'eligible',
               'source_context_reason': source_context_reason(p), 'allow_sensitive': p.get('allow_sensitive') is True}
            | {'has_key': bool(os.environ.get(p.get('api_key_env', '')))} for p in config.get('providers', [])]

def describe(body):
    kind = body.get('provider', 'custom')
    url = endpoint(body.get('base_url', ''), kind)
    protocol = PRESETS[kind][1] if kind != 'custom' else body.get('protocol', 'openai')
    if protocol not in ('openai', 'anthropic'):
        raise ValueError('Protocolo no compatible')
    return kind, url, protocol

def discover(body, config):
    if body.get('provider') == 'freellmapi':
        from .freellmapi import discover as discover_gateway
        return discover_gateway(body, config)
    kind, url, protocol = describe(body)
    old = next((p for p in config.get('providers', []) if p['name'] == body.get('name')), None)
    key = str(body.get('api_key') or '').strip()
    # A saved credential must never follow an edited endpoint.
    if not key and old and old['base_url'] == url and old.get('protocol', 'openai') == protocol:
        key = os.environ.get(old['api_key_env'], '')
    headers = {'Accept': 'application/json'}
    if protocol == 'anthropic':
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    elif key:
        headers['Authorization'] = 'Bearer ' + key
    ollama = kind in ('ollama', 'ollama_cloud')
    catalog_url = url.removesuffix('/v1') + '/api/tags' if ollama else url + '/models'
    req = urllib.request.Request(catalog_url, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('Catálogo demasiado grande')
        data = parse_strict_json(raw)
        catalog = data.get('models') if ollama and 'models' in data else data.get('data')
        if catalog is None and data.get('object') == 'list':
            catalog = []
        if not isinstance(catalog, list):
            raise ValueError('El servidor no devolvió un catálogo válido')
        models = []
        for item in catalog:
            if not isinstance(item, dict):
                continue
            if ollama and item.get('capabilities') and 'completion' not in item['capabilities']:
                continue
            model = item.get('name', item.get('id')) if ollama else item.get('id')
            if isinstance(model, str) and 0 < len(model) <= 200:
                models.append(model)
        return {'models': list(dict.fromkeys(models))[:300]}
    except Exception as exc:
        code = getattr(exc, 'code', None)
        raise ValueError('No se pudo consultar el catálogo' + (f' (HTTP {code})' if code else '') + '. Revisa dirección y clave; también puedes escribir el modelo manualmente.') from None

def save(body, adapter, config_path):
    with LOCK, adapter.lock:
        if adapter.active_requests:
            raise ValueError('Espera a que termine la respuesta antes de cambiar conexiones')
        kind, url, protocol = describe(body)
        name, model = str(body.get('name') or '').strip(), str(body.get('model') or '').strip()
        if not re.fullmatch(r'[\w .-]{1,80}', name) or not model or len(model) > 200:
            raise ValueError('Indica un nombre (letras, números, espacios, guion) y un modelo válido')
        if re.fullmatch(r'[0-9a-fA-F]{24,}\.[A-Za-z0-9_-]{16,}', model) or model.startswith(('sk-', 'AIza')):
            raise ValueError('Ese valor parece una clave de API. Pégala en Clave de API y selecciona un modelo de la lista.')
        config = copy.deepcopy(adapter.config)
        old = next((p for p in config.get('providers', []) if p['name'] == name), None)
        if old and (old['base_url'] != url or old.get('protocol', 'openai') != protocol):
            raise ValueError('Para cambiar el servidor, crea una conexión con otro nombre y su propia clave')
        key = str(body.get('api_key') or '').strip()
        if len(key) > 8192 or any(ord(c) < 32 for c in key):
            raise ValueError('Clave inválida')
        env = old['api_key_env'] if old else 'AXX_API_' + hashlib.sha256(name.encode()).hexdigest()[:24].upper()
        local = local_address(urllib.parse.urlsplit(url).hostname)
        # Legacy manual eligibility; automatic mode also requires explicit downstream cost evidence.
        free = local or (kind == 'openrouter' and (model.endswith(':free') or model == 'openrouter/free'))
        capabilities = list(old['capabilities']) if old and old['model'] == model else ['text']
        entry = dict(enabled=True, free_confirmed=free, billing_allowed=False, daily_attempt_limit=1000,
                     max_output_tokens=2048, auth_optional=local, cost_evidence='unknown',
                     route_kind='proxy' if kind == 'freellmapi' else 'unknown')
        if old:
            entry.update(old)
            if old['model'] != model:
                for field in ('tasks', 'context_window', 'image_context_tokens', 'task_priority'):
                    entry.pop(field, None)
                entry.update(free_confirmed=free, cost_evidence='unknown')
        entry.update(name=name, kind=kind, base_url=url, protocol=protocol, model=model, api_key_env=env,
                     capabilities=capabilities)
        if 'allow_sensitive' in body:
            if type(body['allow_sensitive']) is not bool:
                raise ValueError('allow_sensitive debe ser un consentimiento booleano explícito')
            entry['allow_sensitive'] = body['allow_sensitive']
        for field in ('enabled', 'free_confirmed', 'billing_allowed', 'cost_evidence', 'route_kind', 'capabilities',
                      'tasks', 'context_window', 'image_context_tokens', 'task_priority', 'gateway_free_model_ids'):
            if field in body:
                entry[field] = body[field]
        # route_kind is also part of the recipient identity. A changed route
        # cannot inherit consent unless the human explicitly supplied it.
        if old and profile_id(old) != profile_id(entry) and 'allow_sensitive' not in body:
            entry['allow_sensitive'] = False
        config['providers'] = [entry if p['name'] == name else p for p in config.get('providers', [])]
        if not old:
            config['providers'].append(entry)
        if kind == 'freellmapi':
            entry.update(route_kind='proxy', gateway_profile_verified=False)
        Router._validate_config(None, config)
        if kind == 'freellmapi' and (body.get('dashboard_token') or (entry.get('cost_evidence') == 'free_tier'
                and entry.get('free_confirmed') and not entry.get('billing_allowed'))):
            from .freellmapi import configure_gateway_credentials, verify_provider
            dashboard_env = configure_gateway_credentials(body, config_path, name)
            if dashboard_env:
                entry['gateway_dashboard_env'] = dashboard_env
            if entry.get('cost_evidence') == 'free_tier' and entry.get('free_confirmed') and not entry.get('billing_allowed'):
                previous_key = os.environ.get(env)
                try:
                    if key:
                        os.environ[env] = key
                    entry.update(verify_provider(entry))
                finally:
                    if previous_key is None:
                        os.environ.pop(env, None)
                    else:
                        os.environ[env] = previous_key
            Router._validate_config(None, config)
        if key:
            if os.name != 'nt':
                raise ValueError('En este sistema configura la clave mediante variables de entorno')
            directory = credentials_dir(config_path)
            directory.mkdir(parents=True, exist_ok=True)
            secret_path = directory / (env + '.bin')
            tmp = secret_path.with_suffix('.tmp')
            tmp.write_bytes(_dpapi_encrypt(key.encode('utf-8')))
            tmp.replace(secret_path)
            os.environ[env] = key
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
        adapter.update_config(config)
        return {'ok': True, 'model': model, 'message': 'Conexión guardada. Consulta el catálogo y selecciona el modelo.'}
