"""FreeLLMAPI 0.16.9: real catalogs/profiles and an explicitly owned local gateway.

The inference key authenticates /v1; a separate dashboard session authenticates
/api. Neither readiness nor a localhost URL proves that downstream calls are free.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .router import NoRedirect, parse_strict_json
from .process_manager import spawn_managed_process, terminate_process_tree
from backend.auth.chatgpt_auth import _dpapi_encrypt, _dpapi_decrypt

COMMIT = '26484157fd15f5fb66f54d3a86f568997ea304de'
VERSION = '0.16.9'
TASK_PROFILES = {task: 'axx_' + task for task in ('parameters', 'chat', 'plan', 'vision', 'code', 'writing', 'repair')}
EVALUATION_TASKS = dict(zip('pclvdwrt', ('parameters', 'chat', 'plan', 'vision', 'code', 'writing', 'repair', 'translation')))
CATALOG_LIMIT = 2 * 1024 * 1024
KEYLESS_ENDPOINTS = {
    'kilo': ('https://api.kilo.ai/api/gateway/models', 'https://api.kilo.ai/api/gateway/v1/chat/completions'),
    'ovh': ('https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/models', 'https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions'),
    'aihorde': ('https://oai.aihorde.net/v1/models', 'https://oai.aihorde.net/v1/chat/completions'),
}


def _anonymous_request(platform, body=None, timeout=25):
    """Only fixed public endpoints; never consult environment credentials."""
    url = KEYLESS_ENDPOINTS[platform][body is not None]
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    if platform == 'aihorde' and body is not None:
        headers['Authorization'] = 'Bearer 0000000000'  # documented public sentinel
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(CATALOG_LIMIT + 1)
        if len(raw) > CATALOG_LIMIT:
            raise ValueError('Catálogo público demasiado grande.')
        return parse_strict_json(raw)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise ValueError(f'Endpoint anónimo HTTP {status}.') from None
    except (OSError, ValueError):
        raise ValueError('Endpoint anónimo no respondió JSON válido dentro del plazo.') from None


def _anonymous_models(platform, catalog):
    rows = _rows(catalog.get('data')) if isinstance(catalog, dict) else []
    selected = []
    for model in rows:
        ident = model.get('id')
        if not isinstance(ident, str) or not 0 < len(ident) <= 200:
            continue
        pricing = model.get('pricing', {})
        if platform == 'kilo':
            if (model.get('isFree') is not True or not ident.endswith(':free') or
                    any(str(pricing.get(k)) != '0' for k in ('prompt', 'completion')) or
                    str(pricing.get('request', '0')) != '0' or
                    'text' not in model.get('architecture', {}).get('output_modalities', [])):
                continue
        elif platform == 'ovh':
            # OVH publishes authenticated prices here; its documented anonymous
            # per-IP lane is separate and carries no account or payment token.
            if not model.get('max_completion_tokens', 0):
                continue
        selected.append(model)
    # Prefer bounded, non-reasoning text models for a cheap connectivity check;
    # IDs still come exclusively from the current public catalog.
    def priority(model):
        ident = model['id'].lower()
        preferred = 'lfm-' in ident if platform == 'kilo' else 'mistral-small' in ident
        return (not preferred, 'guard' in ident or 'safety' in ident,
                model.get('context_length') or 10**9, ident)
    selected.sort(key=priority)
    return selected[:2 if platform == 'kilo' else 1]


def _url(value):
    from .provider_settings import endpoint
    result = endpoint(value, 'custom')
    if not result.endswith('/v1'):
        raise ValueError('La URL de FreeLLMAPI debe terminar en /v1.')
    return result


def _request(base_url, path, key='', body=None, method=None, timeout=5):
    headers = {'Accept': 'application/json'}
    if key:
        if not isinstance(key, str) or len(key) > 8192 or any(ord(c) < 32 for c in key):
            raise ValueError('Credencial FreeLLMAPI inválida.')
        headers['Authorization'] = 'Bearer ' + key
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode('utf-8')
    request = urllib.request.Request(_url(base_url).removesuffix('/v1') + path, data=data,
                                     headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=max(.05, min(timeout, 10))) as response:
            raw = response.read(CATALOG_LIMIT + 1)
        if len(raw) > CATALOG_LIMIT:
            raise ValueError('Respuesta FreeLLMAPI demasiado grande.')
        return parse_strict_json(raw)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise ValueError(f'FreeLLMAPI HTTP {status}; comprueba URL y credencial correspondiente.') from None
    except (OSError, ValueError):
        raise ValueError('FreeLLMAPI no devolvió una respuesta JSON válida a tiempo.') from None


def _rows(value):
    if not isinstance(value, list) or len(value) > 10000 or any(not isinstance(item, dict) for item in value):
        raise ValueError('Catálogo FreeLLMAPI inválido.')
    return value


def _connection(body, config):
    if not isinstance(body, dict):
        raise ValueError('Conexión FreeLLMAPI inválida.')
    saved = next((p for p in (config or {}).get('providers', []) if p.get('name') == body.get('name')), {})
    base_url = _url(body.get('base_url') or saved.get('base_url') or '')
    matches = saved.get('base_url') == base_url
    key = body.get('api_key') or (os.environ.get(saved.get('api_key_env', ''), '') if matches else '')
    dashboard = body.get('dashboard_token') or (os.environ.get(saved.get('gateway_dashboard_env', ''), '') if matches else '')
    return base_url, key, dashboard


def discover(body, config=None, timeout=5):
    base_url, key, _ = _connection(body, config)
    catalog = _request(base_url, '/v1/models?execution_status=ready', key, timeout=timeout)
    if not isinstance(catalog, dict):
        raise ValueError('Catálogo FreeLLMAPI inválido.')
    rows = _rows(catalog.get('data'))
    ready, synthetic = [], []
    for item in rows:
        model = item.get('id')
        if not isinstance(model, str) or not 0 < len(model) <= 200:
            continue
        row = {k: item.get(k) for k in ('id', 'owned_by', 'context_window', 'execution_status', 'available')}
        if item.get('execution_status') == 'ready' and item.get('available') is True:
            ready.append(row)
        else:
            synthetic.append(row)
    return {'base_url': base_url, 'models': [r['id'] for r in ready], 'ready_models': ready,
            'routing_entries': synthetic, 'ready_count': len(ready), 'connected': True,
            'free_verified': False, 'profile_names': list(TASK_PROFILES.values())}


def configure_gateway_credentials(body, config_path, name):
    """Save only an explicitly supplied dashboard session using Axx's DPAPI store."""
    from .provider_settings import credentials_dir
    base_url = _url(body.get('base_url'))
    env = 'AXX_API_' + hashlib.sha256(('freellmapi-dashboard:' + base_url).encode()).hexdigest()[:24].upper()
    token = body.get('dashboard_token') or os.environ.get(env, '')
    if not isinstance(token, str) or not token or len(token) > 8192 or any(ord(c) < 32 for c in token):
        raise ValueError('Falta una sesión válida del panel de FreeLLMAPI.')
    auth = _request(base_url, '/api/auth/status', token)
    if not isinstance(auth, dict) or auth.get('authenticated') is not True:
        raise ValueError('La clave unificada no sustituye a la sesión del panel.')
    if os.name != 'nt':
        raise ValueError('La persistencia de sesiones del gateway requiere DPAPI en Windows.')
    directory = credentials_dir(config_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (env + '.bin')
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(_dpapi_encrypt(token.encode('utf-8')))
    tmp.replace(path)
    os.environ[env] = token
    return env


def _free_ids(value):
    if not isinstance(value, list) or len(value) > 100 or any(type(n) is not int or n <= 0 for n in value):
        raise ValueError('Confirma las cuentas gratuitas mediante sus IDs de modelo del gateway.')
    return set(value)


def _profile_task(profile_name):
    task = next((t for t, name in TASK_PROFILES.items() if name == profile_name), None)
    if task is None:
        match = re.fullmatch(r'axx_e_([a-z])_[a-f0-9]{12}', profile_name)
        if match:
            task = EVALUATION_TASKS.get(match[1])
    return task


class _CatalogSnapshotChanged(ValueError):
    """Two read-only catalog observations crossed an actual membership change."""


def _profile_metadata(base_url, api_key, dashboard, profile_name, free_ids, timeout, keyless=False):
    # Gateway catalog sync can commit between /models and /fallback reads.
    # Retry the complete authorization/readiness check once, never just the map.
    for attempt in range(2):
        try:
            return _profile_metadata_once(base_url, api_key, dashboard, profile_name, free_ids, timeout, keyless)
        except _CatalogSnapshotChanged:
            if attempt:
                raise


def _profile_metadata_once(base_url, api_key, dashboard, profile_name, free_ids, timeout, keyless=False):
    release = _request(base_url, '/api/settings/version', dashboard, timeout=timeout)
    if not isinstance(release, dict) or release.get('version') != VERSION:
        raise ValueError('La verificación automática requiere el contrato FreeLLMAPI 0.16.9 integrado.')
    profiles = _rows(_request(base_url, '/api/profiles', dashboard, timeout=timeout))
    profile = next((r for r in profiles if r.get('name', '').lower() == profile_name), None)
    if not profile or profile.get('type') != 'custom' or profile.get('auto_include_new_models') not in (0, False):
        raise ValueError('El perfil no existe o incorpora modelos nuevos sin revisión.')
    profile_id = profile.get('id')
    if type(profile_id) is not int or profile_id <= 0:
        raise ValueError('Identificador de perfil inválido.')
    members = _rows(_request(base_url, f'/api/profiles/{profile_id}/models', dashboard, timeout=timeout))
    members = [m for m in members if m.get('enabled') is True]
    if not members or any(m.get('model_db_id') not in free_ids for m in members):
        raise ValueError('El perfil está vacío o contiene rutas sin gratuidad confirmada.')
    models = _rows(_request(base_url, '/api/models', dashboard, timeout=timeout))
    by_id = {m.get('id'): m for m in models}
    selected = [by_id.get(m['model_db_id'], {}) for m in members]
    if keyless:
        _verify_anonymous_keys(base_url, dashboard, {m.get('platform') for m in selected}, timeout)
    task = _profile_task(profile_name)
    if task is None:
        raise ValueError('Perfil de tarea de Axx desconocido.')
    for model in selected:
        if (model.get('enabled') is not True or type(model.get('contextWindow')) is not int or
                model['contextWindow'] <= 0 or (task == 'vision' and model.get('supportsVision') is not True)):
            raise ValueError('Algún miembro no cumple las capacidades o el contexto del perfil.')
    catalog = discover({'base_url': base_url, 'api_key': api_key}, timeout=timeout)
    # This pinned version always groups models. The chain-scoped read includes
    # the entire enabled catalog, so readiness cannot be borrowed from an off-chain account.
    chain_catalog = _rows(_request(base_url, f'/api/fallback?profile={profile_id}', dashboard, timeout=timeout))
    groups = {}
    for row in chain_catalog:
        canonical = row.get('canonicalId')
        if isinstance(canonical, str) and type(row.get('modelDbId')) is int:
            groups.setdefault(canonical, set()).add(row['modelDbId'])
    covered = set().union(*groups.values()) if groups else set()
    enabled_ids = {m['id'] for m in models if m.get('enabled') is True}
    if covered != enabled_ids:
        current_models = _rows(_request(base_url, '/api/models', dashboard, timeout=timeout))
        if {m['id'] for m in current_models if m.get('enabled') is True} != enabled_ids:
            raise _CatalogSnapshotChanged('El catálogo del gateway cambió durante la verificación del perfil.')
        raise ValueError('El gateway no devolvió el mapa completo de miembros de los grupos.')
    selected_ids = {m['model_db_id'] for m in members}
    ready = any(groups.get(row['id']) and groups[row['id']].issubset(selected_ids)
                for row in catalog['ready_models'])
    if not ready:
        raise ValueError('No hay grupo listo íntegramente dentro del perfil gratuito; revisa cuota y miembros del grupo.')
    guardrails = _request(base_url, '/api/settings/guardrails', dashboard, timeout=timeout)
    attempts = guardrails.get('maxConsecutiveUpstreamFails') if isinstance(guardrails, dict) else None
    if type(attempts) is not int or not 1 <= attempts <= 20:
        raise ValueError('Configura el límite de fallos consecutivos del gateway entre 1 y 20.')
    capabilities = ['text']
    if all(m.get('supportsVision') is True for m in selected):
        capabilities.append('vision')
    if all(m.get('supportsTools') is True for m in selected):
        capabilities.append('tools')
    return {'model': 'auto:' + profile_name, 'tasks': ['writing', 'translation'] if task == 'writing' else [task], 'capabilities': capabilities,
            'context_window': min(m['contextWindow'] for m in selected), 'route_kind': 'proxy',
            'gateway_attempt_limit': attempts, 'gateway_timeout_ms': 20000,
            'gateway_profile_verified': True, 'gateway_profile_id': profile_id,
            'gateway_member_ids': [m['model_db_id'] for m in members]}


def verify_provider(provider, timeout=5):
    model = provider.get('model', '')
    if not isinstance(model, str) or not model.startswith('auto:') or _profile_task(model[5:]) is None:
        raise ValueError('El modo automático requiere un perfil axx verificado.')
    dashboard = os.environ.get(provider.get('gateway_dashboard_env', ''), '')
    if not dashboard:
        raise ValueError('Falta la sesión del panel para verificar el perfil.')
    return _profile_metadata(_url(provider.get('base_url')), os.environ.get(provider.get('api_key_env', ''), ''),
                             dashboard, model[5:], _free_ids(provider.get('gateway_free_model_ids')), timeout,
                             keyless=provider.get('gateway_keyless') is True)


def _verify_anonymous_keys(base_url, dashboard, platforms, timeout=5):
    if not platforms or not platforms.issubset(KEYLESS_ENDPOINTS):
        raise ValueError('La ruta anónima contiene un proveedor no autorizado.')
    keys = _rows(_request(base_url, '/api/keys', dashboard, timeout=timeout))
    for platform in platforms:
        active = [k for k in keys if k.get('platform') == platform and k.get('enabled') is True]
        if not active or any(k.get('keyless') is not True for k in active):
            raise ValueError('La ruta anónima necesita exclusivamente cuentas sin claves personales.')


def evaluation_provider(provider, model_ids, task, timeout=5):
    """Prepare an isolated, exact logical-model profile; never send inference."""
    if task not in {*TASK_PROFILES, 'translation'}:
        raise ValueError('Tarea de evaluación desconocida.')
    selected = _free_ids(model_ids)
    if not selected or not selected.issubset(_free_ids(provider.get('gateway_free_model_ids'))):
        raise ValueError('La evaluación requiere miembros gratuitos confirmados.')
    base_url = _url(provider.get('base_url'))
    dashboard = os.environ.get(provider.get('gateway_dashboard_env', ''), '')
    key = os.environ.get(provider.get('api_key_env', ''), '')
    if not dashboard:
        raise ValueError('Falta la sesión del panel para aislar la evaluación.')
    grouping = _rows(_request(base_url, '/api/fallback', dashboard, timeout=timeout))
    groups = {}
    for row in grouping:
        if isinstance(row.get('canonicalId'), str) and type(row.get('modelDbId')) is int:
            groups.setdefault(row['canonicalId'], set()).add(row['modelDbId'])
    canonical = next((name for name, members in groups.items() if members == selected), None)
    ready = discover({'base_url': base_url, 'api_key': key}, timeout=timeout)
    if canonical is None or canonical not in ready['models']:
        raise ValueError('Selecciona exactamente un grupo completo disponible para evaluar.')
    digest = hashlib.sha256(json.dumps(sorted(selected)).encode()).hexdigest()[:12]
    code = next(code for code, value in EVALUATION_TASKS.items() if value == task)
    # Official profile names are capped at twenty characters.
    name = f'axx_e_{code}_{digest}'
    profiles = _rows(_request(base_url, '/api/profiles', dashboard, timeout=timeout))
    profile = next((p for p in profiles if p.get('name', '').lower() == name), None)
    if profile is None:
        profile = _request(base_url, '/api/profiles', dashboard, {'name': name, 'empty': True}, 'POST', timeout)
        ident = profile.get('id') if isinstance(profile, dict) else None
        if type(ident) is not int or ident <= 0:
            raise ValueError('El gateway no confirmó el perfil de evaluación.')
        _request(base_url, f'/api/profiles/{ident}/reorder', dashboard,
                 [{'modelDbId': member, 'priority': i, 'enabled': True} for i, member in enumerate(sorted(selected))],
                 'PUT', timeout)
    # An existing same-name profile is never edited. Live validation below also
    # checks capabilities, version, quotas, membership and the gateway attempt cap.
    result = _profile_metadata(base_url, key, dashboard, name, selected, timeout,
                               keyless=provider.get('gateway_keyless') is True)
    if set(result['gateway_member_ids']) != selected:
        raise ValueError('El perfil de evaluación existente tiene miembros distintos.')
    return {**provider, **result, 'gateway_free_model_ids': sorted(selected)}


def installation_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Axx/gateways/freellmapi-install.json'


class FreeLLMAPIService:
    def __init__(self, state_dir, config_path=None):
        self.root = Path(state_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'freellmapi.json'
        self.config_path = Path(config_path) if config_path else self.root / 'providers.json'
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.is_file() else {}
        self.lock = threading.RLock()
        self.process = self.job = None
        self.owner_file = None
        self.dashboard = self.api_key = ''
        self.bootstrap_cancel = threading.Event()
        self.provisioning = None

    def candidate_catalog(self, body=None, config=None):
        body = self._body(body)
        base, key, dashboard = _connection(body, config)
        deadline = time.monotonic() + 10
        def left():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('El catálogo del gateway excedió diez segundos.')
            return min(5, remaining)
        models = _rows(_request(base, '/api/models', dashboard, timeout=left()))
        grouping = _rows(_request(base, '/api/fallback', dashboard, timeout=left()))
        ready = set(discover({'base_url': base, 'api_key': key}, timeout=left())['models'])
        canonical = {r['modelDbId']: r['canonicalId'] for r in grouping
                     if type(r.get('modelDbId')) is int and isinstance(r.get('canonicalId'), str)}
        groups = {}
        for ident, name in canonical.items():
            groups.setdefault(name, []).append(ident)
        rows = []
        for model in models:
            provenance = self.state.get('imports', {}).get(base, {}).get(str(model['id']), {})
            if provenance.get('model_id') != model.get('modelId'):
                provenance = {}
            group = canonical.get(model['id'])
            rows.append({**{k: model.get(k) for k in ('id', 'platform', 'modelId', 'contextWindow', 'supportsVision',
                                                     'supportsTools', 'enabled', 'intelligenceRank', 'speedRank')},
                         'canonical_id': group, 'group_ready': group in ready, 'group_member_ids': groups.get(group, []),
                         'provider_kind': provenance.get('provider_kind'), 'source_connection': provenance.get('source_connection')})
        return {'base_url': base, 'models': rows}

    def provision(self):
        if self.bootstrap_cancel.is_set():
            raise ValueError('Instalación de FreeLLMAPI cancelada.')
        if installation_path().is_file():
            return
        if os.name != 'nt':
            raise ValueError('La instalación administrada necesita Windows.')
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        script = root / 'scripts/setup-freellmapi.ps1'
        if not script.is_file():
            raise ValueError('Falta el instalador integrado de FreeLLMAPI.')
        process, job = spawn_managed_process(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                               '-File', str(script)], stdin=subprocess.DEVNULL,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.provisioning = (process, job)
            deadline = time.monotonic() + 600
            while process.poll() is None:
                if self.bootstrap_cancel.wait(.2):
                    raise ValueError('Instalación de FreeLLMAPI cancelada.')
                if time.monotonic() > deadline:
                    raise ValueError('La instalación oficial de FreeLLMAPI excedió diez minutos.')
            if process.returncode != 0 or not installation_path().is_file():
                raise ValueError('La instalación oficial de FreeLLMAPI no terminó correctamente.')
        finally:
            terminate_process_tree(process, job)
            self.provisioning = None

    def bootstrap_keyless(self):
        """Connect only verified anonymous routes, staged for task evaluation."""
        if self.bootstrap_cancel.is_set():
            raise ValueError('Preparación de rutas anónimas cancelada.')
        self.provision()
        if self.bootstrap_cancel.is_set():
            raise ValueError('Preparación de rutas anónimas cancelada.')
        self.start()
        base = self.state['base_url']
        keys = _rows(_request(base, '/api/keys', self.dashboard))
        if all(k.get('keyless') is True for k in keys):
            _request(base, '/api/settings/guardrails', self.dashboard, {'maxConsecutiveUpstreamFails': 1}, 'PUT')
        cached = self.state.get('keyless_bootstrap', {})
        if cached and time.time() - cached.get('checked_at', 0) < (21600 if cached.get('providers') else 300):
            valid = []
            for provider in cached.get('providers', []):
                try:
                    if provider.get('base_url') != base or provider.get('gateway_keyless') is not True:
                        continue
                    env = provider.get('api_key_env', '')
                    if re.fullmatch(r'AXX_API_[A-F0-9]{24}', env):
                        os.environ[env] = self.api_key
                    validated = {**provider, **verify_provider(provider), 'tasks': [*TASK_PROFILES, 'translation']}
                    platform = next((e.get('provider') for e in self.state.get('keyless_evidence', [])
                                     if e.get('model_db_id') in provider.get('gateway_member_ids', [])), 'unknown')
                    validated.setdefault('daily_attempt_limit', 200 if platform == 'kilo' else 40)
                    validated.setdefault('quota_scope_id', 'anonymous-public-' + platform)
                    valid.append(validated)
                except ValueError:
                    pass
            if valid or not cached.get('providers'):
                return {'providers': valid, 'evidence': self.state.get('keyless_evidence', []),
                        'status': 'ready' if valid else 'unavailable', 'reused': True,
                        'message': f'{len(valid)} rutas anónimas preparadas; evidencia reciente reutilizada.'}
        evidence, approved = [], []
        models = _rows(_request(base, '/api/models', self.dashboard))
        for platform in KEYLESS_ENDPOINTS:
            if self.bootstrap_cancel.is_set():
                raise ValueError('Preparación de rutas anónimas cancelada.')
            # Never let the official no-key add operation reuse a personal row.
            if any(k.get('platform') == platform and k.get('keyless') is not True for k in keys):
                evidence.append({'provider': platform, 'status': 'personal_account_preserved'})
                continue
            try:
                catalog = _anonymous_request(platform, timeout=10)
                candidates = _anonymous_models(platform, catalog)
                for candidate in candidates:
                    if self.bootstrap_cancel.is_set():
                        raise ValueError('Preparación de rutas anónimas cancelada.')
                    ident = candidate['id']
                    record = {'provider': platform, 'model_id': ident, 'checked_at': int(time.time()),
                              'catalog_url': KEYLESS_ENDPOINTS[platform][0], 'allow_sensitive': False,
                              'authentication': 'public_anonymous', 'status': 'not_verified'}
                    started = time.monotonic()
                    try:
                        context = candidate.get('context_length')
                        if type(context) is not int or context <= 0:
                            raise ValueError('El catálogo no publica un contexto verificable para este modelo.')
                        answer = _anonymous_request(platform, {'model': ident, 'messages': [
                            {'role': 'user', 'content': 'Reply with exactly OK.'}], 'max_tokens': 256, 'temperature': 0})
                        if self.bootstrap_cancel.is_set():
                            raise ValueError('Preparación de rutas anónimas cancelada.')
                        content = answer.get('choices', [{}])[0].get('message', {}).get('content')
                        record['latency_ms'] = round((time.monotonic() - started) * 1000)
                        record['response_model'] = answer.get('model')
                        record['response_sha256'] = hashlib.sha256(str(content).encode()).hexdigest()
                        if not isinstance(content, str) or content.strip().rstrip('.!') != 'OK':
                            raise ValueError('La respuesta no superó la comprobación sintética pública.')
                        _request(base, '/api/keys', self.dashboard, {'platform': platform, 'label': 'Axx anonymous'}, 'POST')
                        _verify_anonymous_keys(base, self.dashboard, {platform})
                        # Registering a built-in key can refresh its models. Do
                        # not use the pre-registration snapshot to decide create.
                        models = _rows(_request(base, '/api/models', self.dashboard))
                        model = next((m for m in models if m.get('platform') == platform and m.get('modelId') == ident), None)
                        metadata = {'displayName': ('Axx anonymous ' + platform + ' ' + ident)[:200],
                                    'contextWindow': context, 'supportsVision': False, 'supportsTools': False}
                        if model:
                            _request(base, f"/api/models/{model['id']}", self.dashboard, {**metadata, 'enabled': True}, 'PATCH')
                            model_id = model['id']
                        else:
                            created = _request(base, '/api/models', self.dashboard, {'platform': platform, 'modelId': ident, **metadata}, 'POST')
                            model_id = created.get('id')
                        if type(model_id) is not int or model_id <= 0:
                            raise ValueError('El gateway no confirmó el modelo público.')
                        record.update(status='connectivity_verified', model_db_id=model_id, context_window=context)
                        approved.append(record)
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        record['message'] = str(exc)
                    evidence.append(record)
            except ValueError as exc:
                evidence.append({'provider': platform, 'status': 'unavailable', 'message': str(exc)})
        self.state['keyless_evidence'] = evidence[-20:]
        self._save()
        providers = []
        if approved:
            from .provider_settings import credentials_dir
            env = 'AXX_API_' + hashlib.sha256(('freellmapi-keyless:' + base).encode()).hexdigest()[:24].upper()
            directory = credentials_dir(self.config_path)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (env + '.bin')).write_bytes(_dpapi_encrypt(self.api_key.encode()))
            os.environ[env] = self.api_key
            dashboard_env = configure_gateway_credentials({'base_url': base, 'dashboard_token': self.dashboard}, self.config_path, 'anonymous')
            for record in approved:
                provider = {'name': 'Axx anonymous ' + record['provider'] + ' ' + str(record['model_db_id']),
                            'kind': 'freellmapi', 'protocol': 'openai', 'base_url': base, 'api_key_env': env,
                            'gateway_dashboard_env': dashboard_env, 'gateway_free_model_ids': [record['model_db_id']],
                            'free_confirmed': True, 'billing_allowed': False, 'cost_evidence': 'free_tier',
                            'route_kind': 'proxy', 'gateway_keyless': True, 'candidate_only': True,
                            'enabled': True, 'allow_sensitive': False, 'max_output_tokens': 1024,
                            'daily_attempt_limit': 200 if record['provider'] == 'kilo' else 40,
                            'quota_scope_id': 'anonymous-public-' + record['provider']}
                try:
                    provider = evaluation_provider(provider, [record['model_db_id']], 'plan')
                    provider['tasks'] = [*TASK_PROFILES, 'translation']
                    providers.append(provider)
                except ValueError as exc:
                    record['status'], record['message'] = 'gateway_unverified', str(exc)
        self.state['keyless_evidence'] = evidence[-20:]
        self.state['keyless_bootstrap'] = {'checked_at': int(time.time()), 'providers': providers}
        self._save()
        return {'providers': providers, 'evidence': evidence, 'status': 'ready' if providers else 'unavailable',
                'message': f'{len(providers)} rutas anónimas listas para evaluación por tarea.'}

    def cancel_keyless(self):
        self.bootstrap_cancel.set()

    def cancel_bootstrap(self):
        self.bootstrap_cancel.set()
        if self.provisioning:
            terminate_process_tree(*self.provisioning)

    def _save(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.state, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    def _body(self, body):
        body = dict(body or {})
        if not body.get('base_url') and self.state.get('base_url'):
            body['base_url'] = self.state['base_url']
        if body.get('base_url') == self.state.get('base_url') and self.process and self.process.poll() is None:
            if not body.get('api_key'):
                body['api_key'] = self.api_key
            if not body.get('dashboard_token'):
                body['dashboard_token'] = self.dashboard
        return body

    def status(self, body=None, config=None):
        body = self._body(body)
        if not body.get('base_url'):
            saved = next((p for p in (config or {}).get('providers', []) if p.get('kind') == 'freellmapi' and p.get('enabled')), None)
            if saved:
                body.update(name=saved['name'], base_url=saved['base_url'])
        owned = bool(self.process and self.process.poll() is None and body.get('base_url') == self.state.get('base_url'))
        managed = bool(body.get('base_url') == self.state.get('base_url') and self.state.get('port'))
        installed = installation_path().is_file()
        result = {'installed': installed, 'ownership': 'managed' if managed else 'external' if body.get('base_url') else 'none',
                  'running': owned, 'base_url': body.get('base_url'), 'version': VERSION if managed and installed else None,
                  'commit': COMMIT if managed and installed else None, 'installed_version': VERSION if installed else None,
                  'connected': False, 'ready_count': 0,
                  'managed_enabled': self.state.get('enabled', False)}
        if body.get('base_url'):
            try:
                catalog = discover(body, config, timeout=2)
                result.update(connected=True, ready_count=catalog['ready_count'], routing_entries=catalog['routing_entries'])
            except ValueError as exc:
                result['message'] = str(exc)
        return result

    def discover(self, body, config=None):
        return discover(self._body(body), config)

    def profiles(self, body, config=None):
        body = self._body(body)
        base_url, key, dashboard = _connection(body, config)
        if not dashboard:
            raise ValueError('Los perfiles requieren una sesión del panel, distinta de la clave unificada.')
        existing = _rows(_request(base_url, '/api/profiles', dashboard))
        models = _rows(_request(base_url, '/api/models', dashboard))
        catalog = discover({'base_url': base_url, 'api_key': key})
        ready_ids = {m['id'] for m in catalog['ready_models']}
        grouping = _rows(_request(base_url, '/api/fallback', dashboard))
        canonical_by_id = {m['modelDbId']: m['canonicalId'] for m in grouping
                           if type(m.get('modelDbId')) is int and isinstance(m.get('canonicalId'), str)}
        grouped_ids = {}
        for model_id, canonical in canonical_by_id.items():
            grouped_ids.setdefault(canonical, []).append(model_id)
        free_ids = _free_ids(body.get('gateway_free_model_ids', []))
        by_name = {p.get('name', '').lower(): p for p in existing}
        rows = []
        owned_ids = self.state.setdefault('profile_ids', {}).setdefault(base_url, {})
        for task, name in TASK_PROFILES.items():
            profile = by_name.get(name)
            candidates = [m for m in models if m.get('id') in free_ids and m.get('enabled') is True
                          and type(m.get('contextWindow')) is int and m['contextWindow'] > 0
                          and (task != 'vision' or m.get('supportsVision') is True)]
            axis = 'speedRank' if task in {'parameters', 'chat'} else 'intelligenceRank'
            candidates.sort(key=lambda m: (m.get(axis) or 100000, m['id']))
            selected = candidates[:5]
            if body.get('create') is True and not profile:
                profile = _request(base_url, '/api/profiles', dashboard, {'name': name, 'empty': True}, 'POST')
                if type(profile.get('id')) is not int:
                    raise ValueError('El gateway no confirmó la creación del perfil.')
                owned_ids[name] = profile['id']
                self._save()
            if body.get('create') is True and profile and owned_ids.get(name) == profile.get('id'):
                _request(base_url, f"/api/profiles/{profile['id']}/reorder", dashboard,
                         [{'modelDbId': m['id'], 'priority': i, 'enabled': True} for i, m in enumerate(selected)], 'PUT')
            row = {'task': task, 'name': name, 'model': 'auto:' + name, 'exists': bool(profile),
                   'candidate_member_ids': [m['id'] for m in selected], 'verified': False}
            if profile:
                try:
                    row['provider_fields'] = _profile_metadata(base_url, key, dashboard, name, free_ids, 5)
                    row['verified'] = True
                except ValueError as exc:
                    row['message'] = str(exc)
            rows.append(row)
        public_models = []
        for model in models:
            canonical = canonical_by_id.get(model.get('id'))
            provenance = self.state.get('imports', {}).get(base_url, {}).get(str(model.get('id')), {})
            # Retain provenance only while the gateway row still names the exact
            # imported model. It is a display association, never cost authority.
            if provenance.get('model_id') != model.get('modelId'):
                provenance = {}
            public_models.append({
                **{k: model.get(k) for k in ('id', 'platform', 'modelId', 'contextWindow', 'supportsVision',
                                            'supportsTools', 'intelligenceRank', 'speedRank', 'enabled')},
                'canonical_id': canonical, 'group_ready': canonical in ready_ids,
                'group_member_ids': sorted(grouped_ids.get(canonical, [])),
                'provider_kind': provenance.get('provider_kind'),
                'source_connection': provenance.get('source_connection'),
            })
        return {'profiles': rows, 'base_url': base_url, 'free_model_ids': sorted(free_ids), 'models': public_models}

    def credentials(self, body, config=None):
        body = self._body(body)
        base_url, _, dashboard = _connection(body, config)
        name = body.get('name')
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise ValueError('Indica el nombre de la conexión.')
        env = configure_gateway_credentials({'base_url': base_url, 'dashboard_token': dashboard}, self.config_path, name)
        return {'gateway_dashboard_env': env, 'base_url': base_url, 'has_dashboard_session': True}

    def import_provider(self, body, config):
        """Register only the selected, already confirmed-free Axx connection."""
        from .provider_settings import endpoint, local_address
        from urllib.parse import urlsplit
        body = self._body(body)
        base_url, _, dashboard = _connection(body, config)
        if not dashboard:
            raise ValueError('Se necesita la sesión del panel del gateway.')
        source = next((p for p in config.get('providers', []) if p.get('name') == body.get('source_name')), None)
        if not source or not source.get('enabled') or source.get('kind') == 'freellmapi':
            raise ValueError('Selecciona una conexión existente habilitada que no sea otro FreeLLMAPI.')
        source_url = endpoint(source.get('base_url'), source.get('kind', 'custom'))
        free = source.get('cost_evidence') == 'free_tier' or (
            source.get('cost_evidence') == 'direct_local' and source.get('route_kind') == 'direct'
            and local_address(urlsplit(source_url).hostname))
        if source.get('free_confirmed') is not True or source.get('billing_allowed') is not False or not free:
            raise ValueError('La conexión debe tener gratuidad explícita y facturación desactivada.')
        if source.get('protocol', 'openai') != 'openai' or source_url == base_url:
            raise ValueError('La importación requiere un endpoint OpenAI distinto del gateway.')
        context = source.get('context_window')
        if type(context) is not int or context <= 0:
            raise ValueError('Configura primero el contexto comprobado de ese modelo en Axx.')
        key = os.environ.get(source.get('api_key_env', ''), '')
        if not key and source.get('auth_optional') is not True:
            raise ValueError('La credencial guardada de la conexión no está disponible.')
        response = _request(base_url, '/api/keys/custom', dashboard, {
            'baseUrl': source_url, 'apiKey': key, 'model': source['model'], 'label': 'Axx: ' + source['name'],
            'displayName': 'Axx ' + source['name'],
            'supportsTools': 'tools' in source.get('capabilities', []),
            'supportsVision': 'vision' in source.get('capabilities', [])}, 'POST')
        model_id = response.get('modelDbId') if isinstance(response, dict) else None
        if type(model_id) is not int or model_id <= 0:
            raise ValueError('El gateway no confirmó un modelo de conversación importado.')
        _request(base_url, f'/api/models/{model_id}', dashboard, {'contextWindow': context}, 'PATCH')
        models = _rows(_request(base_url, '/api/models', dashboard))
        model = next((m for m in models if m.get('id') == model_id), None)
        if not model or model.get('modelId') != source['model'] or model.get('contextWindow') != context:
            raise ValueError('No se confirmó la configuración del modelo importado.')
        self.state.setdefault('imports', {}).setdefault(base_url, {})[str(model_id)] = {
            'provider_kind': source.get('kind'), 'source_connection': source['name'], 'model_id': source['model']}
        self._save()
        return {'imported': True, 'source_name': source['name'], 'model_ids': [model_id],
                'models': [{k: model.get(k) for k in ('id', 'modelId', 'platform', 'contextWindow', 'supportsTools', 'supportsVision')}],
                'base_url': base_url, 'inference_performed': False}

    def start(self):
        with self.lock:
            try:
                return self._start()
            except Exception:
                self.close()
                raise

    def _start(self):
        with self.lock:
            if os.name != 'nt':
                raise ValueError('El gateway administrado requiere Windows; puedes conectar una instancia externa.')
            if self.process and self.process.poll() is None:
                return self.status()
            marker = installation_path()
            if not marker.is_file():
                raise ValueError('Primero ejecuta scripts/setup-freellmapi.ps1 para instalar la versión fijada.')
            install = json.loads(marker.read_text(encoding='utf-8-sig'))
            if install.get('commit') != COMMIT:
                raise ValueError('La instalación no coincide con la revisión integrada.')
            source = Path(install['source_dir'])
            entry = source / 'server/dist/index.js'
            node = Path(install['node_executable'])
            if not entry.is_file() or not node.is_file():
                raise ValueError('La instalación administrada está incompleta.')
            runtime = self.root / 'freellmapi-runtime'
            runtime.mkdir(parents=True, exist_ok=True)
            import msvcrt
            self.owner_file = (runtime / 'owner.lock').open('a+b')
            if self.owner_file.seek(0, 2) == 0:
                self.owner_file.write(b'0')
                self.owner_file.flush()
            self.owner_file.seek(0)
            try:
                msvcrt.locking(self.owner_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError('Otra instancia de Axx administra esta base del gateway.') from None
            secret_file = runtime / 'managed-secrets.bin'
            if not secret_file.is_file():
                if (runtime / 'freeapi.db').exists():
                    raise ValueError('Falta la clave de cifrado de una base existente; no se reemplazará.')
                secret_file.write_bytes(_dpapi_encrypt(json.dumps({'encryption_key': secrets.token_hex(32),
                                                                  'password': secrets.token_urlsafe(32)}).encode()))
            secure = json.loads(_dpapi_decrypt(secret_file.read_bytes()))
            with socket.socket() as check:
                try:
                    check.bind(('127.0.0.1', self.state.get('port', 0)))
                except OSError:
                    raise ValueError('El puerto guardado pertenece a otro proceso; no se iniciará otro gateway.') from None
                port = check.getsockname()[1]
            self.state.update(port=port, base_url=f'http://127.0.0.1:{port}/v1', enabled=True)
            self._save()
            env = dict(os.environ)
            env.update(PORT=str(port), HOST='127.0.0.1', NODE_ENV='production',
                       ENCRYPTION_KEY=secure['encryption_key'], FREEAPI_DB_PATH=str(runtime / 'freeapi.db'),
                       FREEAPI_ENV_PATH=str(runtime / 'unused.env'), CLIENT_DIST=str(source / 'client/dist'),
                       FALLBACK_TIME_BUDGET_MS='20000', MAX_CONSECUTIVE_UPSTREAM_FAILS='3',
                       MODEL_PROBE_ENABLED='0', COOLDOWN_PROBE_DISABLED='1',
                       FREEAPI_CONFIG_JSON=json.dumps({'admin': {'email': 'axx@localhost.invalid', 'password': secure['password']}}))
            self.process, self.job = spawn_managed_process([str(node), str(entry)], cwd=str(source), env=env,
                                                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    auth = _request(self.state['base_url'], '/api/auth/login', body={'email': 'axx@localhost.invalid',
                                                                                 'password': secure['password']}, timeout=1)
                    self.dashboard = auth['token']
                    self.api_key = _request(self.state['base_url'], '/api/settings/api-key', self.dashboard)['apiKey']
                    configure_gateway_credentials({'base_url': self.state['base_url'], 'dashboard_token': self.dashboard},
                                                  self.config_path, 'FreeLLMAPI')
                    return self.status()
                except (ValueError, KeyError):
                    time.sleep(.2)
            self.close()
            raise ValueError('El gateway administrado no quedó disponible en veinte segundos.')

    def reconnect(self):
        return self.start() if self.state.get('enabled') else self.status()

    def close(self):
        self.bootstrap_cancel.set()
        with self.lock:
            if self.process:
                terminate_process_tree(self.process, self.job)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    raise ValueError('El proceso administrado todavía no confirmó su cierre.') from None
            self.process = self.job = None
            if self.owner_file:
                self.owner_file.close()
                self.owner_file = None
            self.dashboard = self.api_key = ''

    def stop(self):
        with self.lock:
            self.state['enabled'] = False
            self._save()
            self.close()
            return self.status()
