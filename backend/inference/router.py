"""Axx Hardened Sequential Failover Router.
Addresses findings H01 through H10.
Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import json
import logging
import math
import os
import ipaddress
from pathlib import Path
import socket
import sqlite3
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request
import uuid

LOG = logging.getLogger('axx.router')
TASK_PROFILES = ('plan', 'parameters', 'repair', 'vision', 'code', 'writing', 'translation', 'chat')
OUTCOMES = ('succeeded', 'failed', 'user_confirmed', 'user_rejected')
MIN_TASK_OUTCOMES = 5


def profile_id(provider):
    # A changed endpoint/model must never inherit the old responder's quality score.
    identity = {key: provider.get(key) for key in ('name', 'base_url', 'model', 'protocol', 'route_kind')}
    if provider.get('kind') == 'freellmapi':
        identity['gateway_member_ids'] = sorted(provider.get('gateway_member_ids', []))
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]


def automatic_free(provider):
    if provider.get('candidate_only') is True:
        return False
    if provider.get('billing_allowed', False) or provider.get('free_confirmed') is not True:
        return False
    if provider.get('kind') == 'freellmapi' and (provider.get('gateway_profile_verified') is not True
            or not provider['model'].startswith('auto:axx_') or provider.get('route_kind') != 'proxy'
            or not provider.get('gateway_attempt_limit')):
        return False
    evidence = provider.get('cost_evidence', 'unknown')
    return evidence == 'free_tier' or (evidence == 'direct_local' and provider.get('route_kind') == 'direct'
                                      and _is_local_endpoint(provider['base_url']))

# Custom Exceptions with normalized error codes
class RouterError(Exception):
    code = 'PROCESS_FAILURE'
    def __init__(self, message: str, code: str | None = None, *, upstream_attempted: bool | None = None):
        super().__init__(message)
        self.upstream_attempted = upstream_attempted
        if code:
            self.code = code

class RequestError(RouterError):
    code = 'INVALID_REQUEST'

class Exhausted(RouterError):
    code = 'NO_PROVIDER_AVAILABLE'

class StateError(RouterError):
    code = 'STATE_UNAVAILABLE'

class PolicyBlocked(RouterError):
    code = 'UPSTREAM_POLICY'

class UpstreamError(RouterError):
    def __init__(self, status: int, retry_after: float = 0, is_policy: bool = False, message: str | None = None):
        msg = message or f'Upstream HTTP {status}'
        code = 'UPSTREAM_POLICY' if is_policy else ('UPSTREAM_AUTH' if status in (401, 403) else 'UPSTREAM_TEMPORARY')
        super().__init__(msg, code=code)
        self.status = status
        self.retry_after = retry_after
        self.is_policy = is_policy

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def parse_strict_json(raw_bytes: bytes) -> Any:
    """Parses JSON strictly forbidding NaN, Infinity, -Infinity (H02)."""
    def reject_constant(c):
        raise ValueError(f"Unacceptable non-standard JSON constant: {c}")
    return json.loads(raw_bytes.decode('utf-8'), parse_constant=reject_constant)

def retry_seconds(value: str | None) -> float:
    """Safely parses Retry-After header with 24h cap and timezone awareness (H03)."""
    if not value:
        return 0.0
    val_str = str(value).strip()
    try:
        f = float(val_str)
        if not math.isfinite(f) or f < 0:
            return 0.0
        return min(f, 86400.0)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(val_str)
            if parsed.tzinfo is None:
                return 0.0
            now = dt.datetime.now(dt.timezone.utc)
            delta = (parsed - now).total_seconds()
            if not math.isfinite(delta) or delta < 0:
                return 0.0
            return min(delta, 86400.0)
        except (ValueError, TypeError, OverflowError):
            return 0.0

def _is_loopback_http(base_url: str) -> bool:
    u = urllib.parse.urlsplit(base_url)
    return u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost')

def _is_local_endpoint(base_url: str) -> bool:
    host = urllib.parse.urlsplit(base_url).hostname
    if host == 'localhost':
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or (ip.is_private and not ip.is_link_local and not ip.is_unspecified and not ip.is_multicast)
    except ValueError:
        return False

def _optional_auth(p):
    if p.get('kind') == 'freellmapi':
        return False
    return _is_loopback_http(p['base_url']) or (p.get('auth_optional') is True and _is_local_endpoint(p['base_url']))

def http_transport(provider: dict, body: dict, timeout: float, *, response_observer=None) -> dict:
    """Standard HTTP transport with socket timeout and strict response parsing."""
    anthropic = provider.get('protocol') == 'anthropic'
    url = provider['base_url'].rstrip('/') + ('/messages' if anthropic else '/chat/completions')
    if anthropic:
        body = dict(body)
        messages = body['messages']
        body['system'] = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
        body['messages'] = [m for m in messages if m['role'] != 'system']
        body.setdefault('max_tokens', provider.get('max_output_tokens', 2048))
    body_bytes = json.dumps(body, allow_nan=False).encode('utf-8')
    key_env = provider.get('api_key_env')
    api_key = os.environ.get(key_env, '').strip() if key_env else ''
    if not api_key and _is_loopback_http(provider['base_url']):
        api_key = 'ollama-local'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + api_key
    }
    if anthropic:
        headers.pop('Authorization', None)
        headers.update({'x-api-key': api_key, 'anthropic-version': '2023-06-01'})
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            if response_observer is not None:
                response_observer(response.status)
            # Enforce 7 MiB maximum payload reading (H01/H05)
            raw = response.read(7 * 1024 * 1024 + 1)
            if len(raw) > 7 * 1024 * 1024:
                raise UpstreamError(502, message="Response payload exceeds 7 MiB limit")
            try:
                data = parse_strict_json(raw)
                if provider.get('kind') == 'freellmapi' and isinstance(data, dict):
                    routed = urllib.parse.unquote(response.headers.get('X-Routed-Via', ''))
                    platform, separator, model = routed.partition('/')
                    if (separator and 0 < len(platform) <= 80 and 0 < len(model) <= 200
                            and platform not in ('cache', 'idempotency', 'auto', 'fusion')):
                        data['provider'], data['model'] = platform, model
                if anthropic:
                    content = ''.join(part.get('text', '') for part in data.get('content', []) if part.get('type') == 'text')
                    return {'model': data.get('model'), 'choices': [{'message': {'role': 'assistant', 'content': content},
                                         'finish_reason': 'length' if data.get('stop_reason') == 'max_tokens' else 'stop'}]}
                return data
            except (ValueError, UnicodeError) as exc:
                raise UpstreamError(502, message=f"Invalid response JSON: {exc}") from None
    except urllib.error.HTTPError as exc:
        if response_observer is not None:
            response_observer(exc.code)
        headers = exc.headers or {}
        retry_val = headers.get('Retry-After')
        body_text = ''
        try:
            body_text = exc.read(4096).decode('utf-8', errors='replace').lower()
        except Exception:
            pass

        # H07: Distinguish moderation/policy blocks from pure auth failures
        is_policy = False
        if exc.code == 403:
            policy_keywords = ['moderation', 'policy', 'safety', 'content_filter', 'country', 'region', 'terms']
            if any(k in body_text for k in policy_keywords):
                is_policy = True
        
        raise UpstreamError(exc.code, retry_seconds(retry_val), is_policy=is_policy, message=f"HTTP {exc.code}: {body_text[:120]}") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
        raise UpstreamError(503, message=f"Transport connection error: {exc}") from None
    except Exception as exc:
        # H10: Catch any unexpected transport exceptions
        if isinstance(exc, RouterError):
            raise
        raise UpstreamError(500, message=f"Unexpected transport failure: {exc}") from None

class Router:
    """Sequential failover router with full H01-H10 hardening."""
    def __init__(self, config: dict, state: str | Path = 'state.db', *,
                 transport: Callable = http_transport):
        self._validate_config(config)
        self.config = config
        self.providers = config.get('providers', [])
        self.timeout = float(config.get('timeout_seconds', 20))
        self.global_deadline = float(config.get('global_deadline_seconds', 70))
        self.max_attempts = int(config.get('max_attempts', 3))
        self.max_request_bytes = int(config.get('max_request_bytes', 2 * 1024 * 1024))
        self.allow_paid = bool(config.get('allow_paid', False))
        self.transport = transport
        self.state_path = Path(state)

        # Open SQLite with thread safety and busy timeout
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(self.state_path), timeout=10.0, check_same_thread=False)
            self.db.execute('PRAGMA journal_mode=WAL')
            self._init_schema()
        except sqlite3.Error as e:
            raise StateError(f"Failed to initialize SQLite state database: {e}")

    def _validate_config(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a JSON object")
        if config.get('allow_paid', False) is not False:
            raise ValueError('Paid inference is disabled')
        deadline = config.get('global_deadline_seconds', 70)
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or not 0 < deadline <= 70:
            raise ValueError('Invalid global_deadline_seconds')
        
        timeout = config.get('timeout_seconds', 20)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError("Invalid timeout_seconds: must be a finite number between 0 and 120")
            
        max_attempts = config.get('max_attempts', 3)
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError("Invalid max_attempts: must be an integer between 1 and 10")
            
        max_req_bytes = config.get('max_request_bytes', 2 * 1024 * 1024)
        if type(max_req_bytes) is not int or not 1 <= max_req_bytes <= 8 * 1024 * 1024:
            raise ValueError("Invalid max_request_bytes")

        providers = config.get('providers', [])
        if not isinstance(providers, list):
            raise ValueError("providers must be a list")

        names = set()
        for p in providers:
            if not isinstance(p, dict):
                raise ValueError("Each provider must be an object")
            for field in ('name', 'base_url', 'model', 'api_key_env', 'daily_attempt_limit', 'capabilities'):
                if field not in p:
                    raise ValueError(f"Missing provider field: {field}")
            for field in ('name', 'base_url', 'model', 'api_key_env'):
                if not isinstance(p[field], str) or not p[field].strip():
                    raise ValueError(f'Invalid provider {field}')
            for field in ('free_confirmed', 'allow_sensitive', 'billing_allowed', 'auth_optional', 'gateway_profile_verified', 'candidate_only', 'gateway_keyless'):
                if field in p and type(p[field]) is not bool:
                    raise ValueError(f'Invalid provider {field}')
            
            # H06: Explicit enabled requirement
            if p.get('enabled') is not True and p.get('enabled') is not False:
                raise ValueError(f"Provider '{p.get('name')}' must explicitly specify 'enabled' boolean")
            
            # H06: Reject template models
            if p['model'].startswith('REPLACE_') or 'template' in p['model'].lower():
                raise ValueError(f"Provider '{p['name']}' has unconfigured template model: {p['model']}")

            u = urllib.parse.urlsplit(p['base_url'])
            if (u.scheme != 'https' and not (u.scheme == 'http' and _is_local_endpoint(p['base_url']))) or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError("base_url must be HTTPS (or loopback HTTP) without credentials/query/fragment")
            if p.get('protocol', 'openai') not in ('openai', 'anthropic'):
                raise ValueError('Unsupported provider protocol')
                
            if p['name'] in names:
                raise ValueError(f"Duplicate provider name: {p['name']}")
            names.add(p['name'])
            
            if type(p['daily_attempt_limit']) is not int or p['daily_attempt_limit'] < 1:
                raise ValueError("daily_attempt_limit must be a positive integer")
            if not isinstance(p['capabilities'], list) or not all(isinstance(c, str) for c in p['capabilities']):
                raise ValueError("Invalid capabilities list")
            if type(p.get('max_output_tokens', 1024)) is not int or p.get('max_output_tokens', 1024) < 1:
                raise ValueError("Invalid max_output_tokens")
            if 'tasks' in p and (not isinstance(p['tasks'], list) or not all(isinstance(t, str) for t in p['tasks'])):
                raise ValueError("Invalid tasks")
            if 'scope_limit' in p and (type(p['scope_limit']) is not int or p['scope_limit'] < 1):
                raise ValueError('scope_limit must be a positive integer')
            if 'quota_scope_id' in p and (not isinstance(p['quota_scope_id'], str) or not p['quota_scope_id'].strip()):
                raise ValueError('quota_scope_id must be a non-empty string')
            if p.get('cost_evidence', 'unknown') not in ('unknown', 'free_tier', 'direct_local', 'paid'):
                raise ValueError('Invalid cost_evidence')
            if p.get('route_kind', 'unknown') not in ('unknown', 'direct', 'proxy'):
                raise ValueError('Invalid route_kind')
            for field in ('context_window', 'image_context_tokens'):
                if field in p and (type(p[field]) is not int or not 1 <= p[field] <= 10000000):
                    raise ValueError(f'Invalid {field}')
            priority = p.get('task_priority', {})
            if (not isinstance(priority, dict) or any(task not in TASK_PROFILES or type(value) is not int
                    or not 0 <= value <= 100 for task, value in priority.items())):
                raise ValueError('Invalid task_priority')
            for field, maximum in (('gateway_attempt_limit', 20), ('gateway_timeout_ms', 70000)):
                if field in p and (type(p[field]) is not int or not 1 <= p[field] <= maximum):
                    raise ValueError(f'Invalid {field}')
            if 'gateway_free_model_ids' in p and (not isinstance(p['gateway_free_model_ids'], list)
                    or len(p['gateway_free_model_ids']) > 100 or not all(type(value) is int and value > 0
                                                                     for value in p['gateway_free_model_ids'])):
                raise ValueError('Invalid gateway_free_model_ids')
            if 'gateway_dashboard_env' in p and (not isinstance(p['gateway_dashboard_env'], str)
                    or not p['gateway_dashboard_env'].startswith('AXX_API_') or len(p['gateway_dashboard_env']) > 100):
                raise ValueError('Invalid gateway_dashboard_env')

    def _init_schema(self):
        # Schema with quota_scope_id (H04)
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS usage (
                name TEXT,
                day TEXT,
                attempts INTEGER,
                quota_scope_id TEXT,
                PRIMARY KEY(name, day)
            )
        ''')
        if 'quota_scope_id' not in {row[1] for row in self.db.execute('PRAGMA table_info(usage)')}:
            self.db.execute('ALTER TABLE usage ADD COLUMN quota_scope_id TEXT')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS scope_usage (
                scope_id TEXT,
                day TEXT,
                attempts INTEGER,
                PRIMARY KEY(scope_id, day)
            )
        ''')
        # Preserve local historical attempts when upgrading from per-model quotas.
        scopes = {p.get('quota_scope_id') or p['name'] for p in self.providers}
        for scope in scopes:
            names = [p['name'] for p in self.providers if (p.get('quota_scope_id') or p['name']) == scope]
            placeholders = ','.join('?' for _ in names)
            self.db.execute(f'INSERT OR IGNORE INTO scope_usage(scope_id,day,attempts) SELECT ?,day,SUM(attempts) FROM usage WHERE name IN ({placeholders}) GROUP BY day', [scope, *names])
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS cooldown (
                name TEXT PRIMARY KEY,
                until REAL,
                quota_scope_id TEXT
            )
        ''')
        if 'quota_scope_id' not in {row[1] for row in self.db.execute('PRAGMA table_info(cooldown)')}:
            self.db.execute('ALTER TABLE cooldown ADD COLUMN quota_scope_id TEXT')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                name TEXT PRIMARY KEY,
                successes INTEGER DEFAULT 0,
                failures INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0,
                last_status INTEGER
            )
        ''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS inference_routes (
            route_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, task TEXT NOT NULL,
            attribution_id TEXT NOT NULL, metadata TEXT NOT NULL)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS inference_routes_profile ON inference_routes(profile_id,task)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS task_outcomes (
            route_id TEXT NOT NULL, category TEXT NOT NULL, outcome TEXT NOT NULL,
            PRIMARY KEY(route_id,category))''')
        self.db.commit()

    def close(self):
        """Explicitly closes SQLite connection to avoid file locks on Windows."""
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _reserve(self, p: dict) -> bool:
        """Atomic reservation honoring cooldown, daily limit, and quota_scope_id (H04)."""
        day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        scope_id = p.get('quota_scope_id') or p['name']
        now = time.time()
        try:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                # Check cooldown by name or by quota scope
                row = self.db.execute(
                    'SELECT MAX(until) FROM cooldown WHERE name=? OR quota_scope_id=?',
                    (p['name'], scope_id)
                ).fetchone()
                if row and row[0] is not None and row[0] > now:
                    return False
                
                # Check provider daily limit
                self.db.execute('INSERT OR IGNORE INTO usage VALUES(?,?,0,?)', (p['name'], day, scope_id))
                cur = self.db.execute(
                    'UPDATE usage SET attempts=attempts+1 WHERE name=? AND day=? AND attempts<?',
                    (p['name'], day, p['daily_attempt_limit'])
                )
                if cur.rowcount != 1:
                    return False

                # Every attempt reserves the shared account budget, including configs
                # written before scope_limit existed. Use the strictest active row.
                self.db.execute('INSERT OR IGNORE INTO scope_usage VALUES(?,?,0)', (scope_id, day))
                cur_scope = self.db.execute(
                    'UPDATE scope_usage SET attempts=attempts+1 WHERE scope_id=? AND day=? AND attempts<?',
                    (scope_id, day, self._scope_limit(p))
                )
                if cur_scope.rowcount != 1:
                    self.db.execute('UPDATE usage SET attempts=attempts-1 WHERE name=? AND day=?', (p['name'], day))
                    return False

                return True
        except sqlite3.Error as e:
            raise StateError(f"Database reservation failed: {e}")

    def _scope_limit(self, provider: dict) -> int:
        scope_id = provider.get('quota_scope_id') or provider['name']
        limits = [p.get('scope_limit', p['daily_attempt_limit']) for p in self.providers
                  if p.get('enabled') and (p.get('quota_scope_id') or p['name']) == scope_id]
        return min(limits) if limits else provider.get('scope_limit', provider['daily_attempt_limit'])

    def _cool(self, p: dict, seconds: float):
        now = time.time()
        scope_id = p.get('quota_scope_id') or p['name']
        try:
            with self.db:
                self.db.execute(
                    'INSERT INTO cooldown VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET until=max(until,excluded.until)',
                    (p['name'], now + seconds, scope_id)
                )
        except sqlite3.Error as e:
            raise StateError(f"Database cooldown write failed: {e}")

    def _record(self, name: str, success: bool, elapsed: float, status: int):
        try:
            with self.db:
                self.db.execute(
                    '''INSERT INTO metrics(name, successes, failures, latency_ms, last_status)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET
                       successes = successes + excluded.successes,
                       failures = failures + excluded.failures,
                       latency_ms = latency_ms + excluded.latency_ms,
                       last_status = excluded.last_status''',
                    (name, int(success), int(not success), elapsed * 1000.0, status)
                )
        except sqlite3.Error as e:
            LOG.warning("Failed to record metrics: %s", e)

    def reset_cooldown(self, name: str):
        if name not in {p['name'] for p in self.providers}:
            raise ValueError(f"Unknown provider: {name}")
        try:
            with self.db:
                self.db.execute('DELETE FROM cooldown WHERE name=?', (name,))
        except sqlite3.Error as e:
            raise StateError(f"Failed to reset cooldown: {e}")

    def validate_request(self, request: dict):
        """Validates chat request with null checks per field (H02, D)."""
        if not isinstance(request, dict):
            raise RequestError("Request must be a JSON object")
        allowed = {'messages', 'axx_task', 'axx_sensitive', 'temperature', 'max_tokens', 'tools', 'stream', 'model', 'provider_name', 'selection_mode', 'axx_attempt_budget'}
        if 'axx_attempt_budget' in request and (type(request['axx_attempt_budget']) is not int or not 1 <= request['axx_attempt_budget'] <= 10):
            raise RequestError('axx_attempt_budget must be an integer between 1 and 10')
        if request.get('selection_mode', 'manual') not in ('manual', 'automatic_free'):
            raise RequestError('Invalid selection_mode')
        if request.get('selection_mode') == 'automatic_free' and request.get('axx_task', 'chat') not in TASK_PROFILES:
            raise RequestError('Unsupported automatic task profile')
        if 'provider_name' in request and (not isinstance(request['provider_name'], str) or len(request['provider_name']) > 80):
            raise RequestError('Invalid provider name')
        if 'model' in request and (not isinstance(request['model'], str) or len(request['model']) > 200):
            raise RequestError('Invalid model')
        if set(request) - allowed:
            raise RequestError('Unknown request fields')
        try:
            if len(json.dumps(request, allow_nan=False).encode('utf-8')) > self.max_request_bytes:
                raise RequestError('Request exceeds maximum size')
        except (ValueError, TypeError):
            raise RequestError('Request must contain finite JSON values') from None
        if not isinstance(request.get('axx_task', 'chat'), str):
            raise RequestError('axx_task must be a string')
        if type(request.get('axx_sensitive', False)) is not bool:
            raise RequestError('axx_sensitive must be boolean')

        if request.get('stream') is True:
            raise RequestError("stream=true is rejected in this runtime")

        messages = request.get('messages')
        if not isinstance(messages, list) or not messages:
            raise RequestError("'messages' must be a non-empty list")

        allowed_roles = {'system', 'user', 'assistant', 'tool'}
        for i, m in enumerate(messages):
            if not isinstance(m, dict):
                raise RequestError(f"Message {i} must be an object")
            role = m.get('role')
            if role not in allowed_roles:
                raise RequestError(f"Message {i} has invalid role: {role}")
            
            content = m.get('content')
            # Null validation by field: content can be null ONLY if tool_calls are present
            if content is None:
                if role == 'assistant' and m.get('tool_calls'):
                    pass
                else:
                    raise RequestError(f"Message {i} has null 'content' without tool_calls")
            elif not isinstance(content, (str, list)):
                raise RequestError(f"Message {i} content must be string or list")

        # Temperature / top_p finite checks
        if 'temperature' in request:
            t = request['temperature']
            if type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 2:
                raise RequestError("temperature must be a finite number between 0 and 2")
        
        if 'max_tokens' in request:
            mt = request['max_tokens']
            if type(mt) is not int or mt < 1:
                raise RequestError("max_tokens must be a positive integer")

        if 'tools' in request:
            tools = request['tools']
            if tools is not None:
                if not isinstance(tools, list):
                    raise RequestError("'tools' must be a list")
                for t in tools:
                    if not isinstance(t, dict) or t.get('type') != 'function' or 'function' not in t:
                        raise RequestError("Each tool must have type='function' with a function object")

    def _validate_response_message(self, response: dict) -> dict:
        """Validates upstream response structure (H05)."""
        if not isinstance(response, dict):
            raise UpstreamError(502, message="Response is not a JSON object")
        
        choices = response.get('choices')
        if not isinstance(choices, list) or len(choices) == 0:
            raise UpstreamError(502, message="Response has empty or missing choices")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise UpstreamError(502, message="Choice is not an object")

        message = first_choice.get('message')
        if not isinstance(message, dict):
            raise UpstreamError(502, message="Choice message is not an object")
        if message.get('role') != 'assistant':
            raise UpstreamError(502, message='Response message role must be assistant')

        # H05: Must have non-empty content OR valid structured tool_calls
        content = message.get('content')
        tool_calls = message.get('tool_calls')
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise UpstreamError(502, message='tool_calls must be an array')

        has_valid_content = isinstance(content, str) and len(content.strip()) > 0
        has_valid_tools = isinstance(tool_calls, list) and len(tool_calls) > 0

        if not has_valid_content and not has_valid_tools:
            raise UpstreamError(502, message="Response message contains neither valid text content nor tool_calls")

        # If tool_calls present, validate each call structure
        if has_valid_tools:
            for tc in tool_calls:
                if not isinstance(tc, dict) or 'id' not in tc or 'function' not in tc:
                    raise UpstreamError(502, message="Malformed tool_call in assistant message")
                fn = tc.get('function')
                if not isinstance(fn, dict) or 'name' not in fn or 'arguments' not in fn:
                    raise UpstreamError(502, message="Malformed tool function object")
                if not isinstance(tc['id'], str) or not isinstance(fn['name'], str) or not isinstance(fn['arguments'], str):
                    raise UpstreamError(502, message='Invalid tool function types')
                if tc.get('type') != 'function' or not tc['id'].strip() or not fn['name'].strip():
                    raise UpstreamError(502, message='Tool calls require function type and non-empty id/name')
                try:
                    arguments = parse_strict_json(fn['arguments'].encode('utf-8'))
                    if not isinstance(arguments, dict):
                        raise ValueError('Tool arguments must be object')
                except (ValueError, UnicodeError):
                    raise UpstreamError(502, message='Tool arguments must be a JSON object') from None

        return response

    def _outcome_counts(self, profile, task, attribution=None):
        sql = '''SELECT o.outcome,COUNT(*) FROM task_outcomes o JOIN inference_routes r USING(route_id)
                 WHERE r.profile_id=? AND r.task=?'''
        values = [profile, task]
        if attribution:
            sql += ' AND r.attribution_id=?'
            values.append(attribution)
        rows = self.db.execute(sql + ' GROUP BY o.outcome', values).fetchall()
        return dict.fromkeys(OUTCOMES, 0) | dict(rows)

    def record_outcome(self, route, task, outcome):
        """Accept only a locally issued route receipt; execution and confirmation stay separate."""
        if not isinstance(route, dict) or task not in TASK_PROFILES or outcome not in OUTCOMES:
            raise ValueError('Invalid inference task outcome')
        route_id = route.get('route_id')
        if not isinstance(route_id, str) or not 1 <= len(route_id) <= 80:
            raise ValueError('Missing inference route receipt')
        try:
            row = self.db.execute('SELECT metadata FROM inference_routes WHERE route_id=?', (route_id,)).fetchone()
            if not row:
                raise ValueError('Unknown inference route receipt')
            recorded = json.loads(row[0])
            if recorded != route or recorded['task'] != task:
                raise ValueError('Inference outcome does not match its route receipt')
            category = 'execution' if outcome in ('succeeded', 'failed') else 'confirmation'
            with self.db:
                self.db.execute('''INSERT INTO task_outcomes VALUES(?,?,?)
                    ON CONFLICT(route_id,category) DO UPDATE SET outcome=excluded.outcome''', (route_id, category, outcome))
            return self._outcome_counts(recorded['profile_id'], task, recorded['attribution_id'])
        except sqlite3.Error as exc:
            raise StateError(f'Cannot persist task outcome: {exc}') from None

    def _route_metadata(self, provider, response, request, attempts, attempt_budget_used):
        def reported(field):
            value = response.get(field)
            return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 200 else None
        responder_model, responder_provider = reported('model'), reported('provider')
        if provider.get('route_kind') != 'direct' and responder_model == provider['model']:
            responder_model = None
        if request.get('axx_sensitive') is True:
            responder_model = responder_model if responder_model == provider['model'] else None
            responder_provider = responder_provider if responder_provider == provider['name'] else None
        profile = profile_id(provider)
        identity = 'reported' if responder_model else 'unverified_profile'
        attribution = (hashlib.sha256(json.dumps([profile, responder_model, responder_provider]).encode()).hexdigest()[:32]
                       if responder_model else profile)
        mode = request.get('selection_mode', 'manual')
        metadata = dict(provider=provider['name'], model=provider['model'] if mode == 'manual' else responder_model,
                        configured_model=provider['model'], responder_model=responder_model, responder_provider=responder_provider,
                        identity=identity, profile_id=profile, attribution_id=attribution, route_id=str(uuid.uuid4()),
                        task=request.get('axx_task', 'chat'), selection_mode=mode, attempts=attempts, upstream_attempts=attempts,
                        attempt_budget_used=attempt_budget_used)
        try:
            with self.db:
                self.db.execute('INSERT INTO inference_routes VALUES(?,?,?,?,?)',
                                (metadata['route_id'], profile, metadata['task'], attribution, json.dumps(metadata)))
        except sqlite3.Error as exc:
            raise StateError(f'Cannot persist inference route receipt: {exc}') from None
        return metadata

    def _verified_gateway(self, provider, task, deadline_time):
        from .freellmapi import verify_provider
        remaining = deadline_time - time.monotonic()
        if remaining <= 0:
            raise UpstreamError(504, message='Global inference deadline exceeded')
        configured_tasks = provider.get('tasks')
        provider = dict(provider, **verify_provider(provider, timeout=min(5, remaining)))
        if configured_tasks and '*' not in configured_tasks:
            provider['tasks'] = [name for name in provider.get('tasks', []) if name in configured_tasks]
            if task not in provider['tasks']:
                raise ValueError('Gateway task no longer belongs to the configured scope')
        self._validate_config({'providers': [provider]})
        if type(provider.get('gateway_attempt_limit')) is not int:
            raise ValueError('The gateway has no verified attempt bound')
        return provider

    def _automatic_candidates(self, request, task, needs_tools, image_count, deadline_time):
        required = {'text'}
        if needs_tools:
            required.add('tools')
        if image_count or task == 'vision':
            required.add('vision')
        # UTF-8 byte count is a conservative text budget without a model-specific tokenizer.
        input_tokens = len(json.dumps({'messages': request['messages'], 'tools': request.get('tools')},
                                     ensure_ascii=False).encode('utf-8')) + 1024
        status = {p['name']: p for p in self.status()['providers']}
        candidates = []
        attempt_limit = min(self.max_attempts, request.get('axx_attempt_budget', self.max_attempts))
        for provider in self.providers:
            if not automatic_free(provider) or status[provider['name']]['state'] != 'ready_locally':
                continue
            if provider.get('kind') == 'freellmapi':
                try:
                    provider = self._verified_gateway(provider, task, deadline_time)
                except ValueError:
                    continue
                if not automatic_free(provider) or provider['gateway_attempt_limit'] > attempt_limit:
                    continue
            if not required.issubset(provider['capabilities']):
                continue
            tasks = provider.get('tasks')
            if tasks and '*' not in tasks and task not in tasks:
                continue
            if request.get('axx_sensitive') and not provider.get('allow_sensitive', False):
                continue
            # Unknown image token budgets are ineligible; a URL's length is not its image cost.
            if image_count and not provider.get('image_context_tokens'):
                continue
            output = min(request.get('max_tokens', provider.get('max_output_tokens', 1024)), provider.get('max_output_tokens', 1024))
            if provider.get('context_window', 0) < input_tokens + output + image_count * provider.get('image_context_tokens', 0):
                continue
            counts = self._outcome_counts(profile_id(provider), task)
            total = counts['succeeded'] + counts['failed']
            quality = counts['succeeded'] / total if total >= MIN_TASK_OUTCOMES else .5
            candidates.append((-quality, provider.get('task_priority', {}).get(task, 50), len(candidates), provider))
        return [candidate[-1] for candidate in sorted(candidates, key=lambda item: item[:3])]

    def chat(self, request: dict, deadline_time: float | None = None, *, http_receipts: list | None = None) -> dict:
        accounting = {'upstream_attempts': 0, 'attempt_budget_used': 0}
        try:
            return self._chat(request, deadline_time, accounting, http_receipts)
        except Exception as exc:
            # Counts describe this router's dispatches; gateway cost is a
            # conservative downstream bound, never an invented completion count.
            exc.upstream_attempted = accounting['upstream_attempts'] > 0
            exc.upstream_attempts = accounting['upstream_attempts']
            exc.attempt_budget_used = accounting['attempt_budget_used']
            raise

    def _chat(self, request: dict, deadline_time: float | None, accounting: dict, http_receipts=None) -> dict:
        """Executes sequential failover with strict global deadline (H01-H10)."""
        self.validate_request(request)
        attempt_limit = min(self.max_attempts, request.get('axx_attempt_budget', self.max_attempts))

        # Monotonic wall-clock deadline budget (H01)
        start_time = time.monotonic()
        if deadline_time is None:
            deadline_time = start_time + self.global_deadline

        req_task = request.get('axx_task', 'chat')
        req_sensitive = bool(request.get('axx_sensitive', False))
        needs_tools = bool(request.get('tools'))
        image_count = sum(1 for m in request['messages'] if isinstance(m.get('content'), list)
                          for part in m['content'] if isinstance(part, dict) and part.get('type') == 'image_url')
        needs_vision = bool(image_count)
        automatic = request.get('selection_mode', 'manual') == 'automatic_free'
        providers = self._automatic_candidates(request, req_task, needs_tools, image_count, deadline_time) if automatic else self.providers

        attempts = 0
        attempt_budget_used = 0
        last_error = None

        for p in providers:
            # Check remaining global deadline budget
            time_left = deadline_time - time.monotonic()
            if time_left <= 0:
                raise UpstreamError(504, message="Global inference deadline exceeded (70s budget)")

            if not p.get('enabled', False) or p.get('candidate_only') is True:
                continue
            # A new bounded manual request must also constrain proxy fanout.
            # Historical manual requests without this envelope retain their policy.
            bounded_manual_gateway = not automatic and 'axx_attempt_budget' in request and p.get('kind') == 'freellmapi'
            if bounded_manual_gateway:
                if request.get('model') and request['model'] != p['model'] or request.get('provider_name') and request['provider_name'] != p['name']:
                    continue
                try:
                    p = self._verified_gateway(p, req_task, deadline_time)
                except ValueError:
                    continue
            gateway = (automatic or bounded_manual_gateway) and p.get('kind') == 'freellmapi'
            attempt_cost = p['gateway_attempt_limit'] if gateway else 1
            if attempt_budget_used + attempt_cost > attempt_limit:
                continue
            if not automatic and request.get('model') and request['model'] != p['model']:
                continue
            if not automatic and request.get('provider_name') and request['provider_name'] != p['name']:
                continue

            # Cost policy check (H06, Section 6)
            if not self.allow_paid and not p.get('free_confirmed', False) and not p.get('billing_allowed', False):
                continue

            # Capability match check
            if needs_tools and 'tools' not in p.get('capabilities', []):
                continue
            if needs_vision and 'vision' not in p.get('capabilities', []):
                continue

            # Task & sensitivity checks
            tasks = p.get('tasks')
            if tasks and '*' not in tasks and req_task not in tasks:
                continue
            if req_sensitive and not p.get('allow_sensitive', False):
                continue

            # API key resolution check
            key_env = p.get('api_key_env')
            if not _optional_auth(p) and (not key_env or key_env not in os.environ or not os.environ[key_env].strip()):
                continue

            # Atomic quota reservation
            if not self._reserve(p):
                continue

            attempts += 1
            attempt_budget_used += attempt_cost
            accounting.update(upstream_attempts=attempts, attempt_budget_used=attempt_budget_used)
            call_timeout = min(self.timeout, time_left)
            if gateway:
                call_timeout = min(call_timeout, p.get('gateway_timeout_ms', 20000) / 1000)
            call_start = time.monotonic()

            try:
                # Prepare outgoing payload
                payload = {
                    'model': p['model'],
                    'messages': request['messages'],
                    'stream': False
                }
                if 'temperature' in request:
                    payload['temperature'] = request['temperature']
                if 'max_tokens' in request:
                    payload['max_tokens'] = min(request['max_tokens'], p.get('max_output_tokens', 1024))
                elif automatic:
                    payload['max_tokens'] = p.get('max_output_tokens', 1024)
                if 'tools' in request and 'tools' in p.get('capabilities', []):
                    payload['tools'] = request['tools']

                transport_options = {}
                if http_receipts is not None and self.transport is http_transport:
                    # The local transport owns this evidence. Response-supplied
                    # model/provider fields and attempt counts cannot create it.
                    configured = next(item for item in self.providers if item['name'] == p['name'])
                    def received_headers(status):
                        if type(status) is int and 100 <= status <= 599 and len(http_receipts) < 10:
                            http_receipts.append({'ordinal': attempts, 'profile_id': profile_id(configured),
                                'provider_name': configured['name'], 'configured_model': configured['model'],
                                'endpoint_scope': 'gateway_endpoint' if configured.get('kind') == 'freellmapi' else 'configured_endpoint',
                                'evidence_kind': 'http_response_headers', 'status': status, 'at': time.time(),
                                'downstream_confirmed': False})
                    transport_options['response_observer'] = received_headers
                resp = self.transport(p, payload, timeout=call_timeout, **transport_options)
                validated_resp = self._validate_response_message(resp)

                elapsed = time.monotonic() - call_start
                self._record(p['name'], success=True, elapsed=elapsed, status=200)

                validated_resp['axx_router'] = self._route_metadata(p, validated_resp, request, attempts, attempt_budget_used)
                return validated_resp

            except UpstreamError as err:
                elapsed = time.monotonic() - call_start
                self._record(p['name'], success=False, elapsed=elapsed, status=err.status)
                last_error = err

                # H07: Policy block must stop immediately, NO failover
                if err.is_policy or (err.status == 403 and not automatic):
                    raise PolicyBlocked(f"Request blocked by content policy: {err}")

                if err.status == 402:
                    raise PolicyBlocked('Provider requires payment; paid inference is disabled')

                # 400 Bad Request: Do not retry (client error)
                if err.status in (400, 422) or (err.status == 401 and not automatic):
                    raise

                # 429 Rate Limit: apply Retry-After cooldown
                if err.status == 429:
                    cooldown_time = err.retry_after if err.retry_after > 0 else 60.0
                    self._cool(p, cooldown_time)
                elif err.status in (500, 502, 503, 504):
                    self._cool(p, 30.0)

                # Check max attempts limit
                if attempt_budget_used >= attempt_limit:
                    break

            except StateError:
                raise
            except Exception as exc:
                elapsed = time.monotonic() - call_start
                self._record(p['name'], success=False, elapsed=elapsed, status=500)
                last_error = exc
                if attempt_budget_used >= attempt_limit:
                    break

        if last_error:
            if isinstance(last_error, RouterError):
                last_error.upstream_attempted = attempts > 0
                raise last_error
            raise Exhausted(f"All eligible providers exhausted. Last error: {last_error}", upstream_attempted=attempts > 0)
        raise Exhausted("No eligible provider available for request criteria", upstream_attempted=False)

    def status(self) -> dict:
        """Returns local health projection with explicit local quota semantics (H09)."""
        day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        now = time.time()
        providers_status = []

        for p in self.providers:
            name = p['name']
            scope_id = p.get('quota_scope_id') or name
            
            # Local attempts
            usage_row = self.db.execute(
                'SELECT attempts FROM usage WHERE name=? AND day=?', (name, day)
            ).fetchone()
            attempts_today = usage_row[0] if usage_row else 0
            scope_row = self.db.execute('SELECT attempts FROM scope_usage WHERE scope_id=? AND day=?', (scope_id, day)).fetchone()
            scope_attempts = scope_row[0] if scope_row else 0
            scope_limit = self._scope_limit(p)

            # Cooldown check
            cooldown_row = self.db.execute(
                'SELECT MAX(until) FROM cooldown WHERE name=? OR quota_scope_id=?', (name, scope_id)
            ).fetchone()
            cooldown_remaining = max(0.0, cooldown_row[0] - now) if cooldown_row and cooldown_row[0] is not None else 0.0

            # Metrics
            m_row = self.db.execute(
                'SELECT successes, failures, latency_ms, last_status FROM metrics WHERE name=?', (name,)
            ).fetchone()
            if m_row:
                s, f, lat, st = m_row
                total_m = s + f
                mean_lat = (lat / total_m) if total_m > 0 else 0.0
                metrics_dict = {
                    'successes': s,
                    'failures': f,
                    'mean_attempt_ms': round(mean_lat, 2),
                    'last_status': st
                }
            else:
                metrics_dict = {'successes': 0, 'failures': 0, 'mean_attempt_ms': 0.0, 'last_status': None}

            # State determination (H09: 'ready' explicitly documented as local eligibility)
            key_env = p.get('api_key_env')
            has_key = _optional_auth(p) or bool(key_env and os.environ.get(key_env, '').strip())

            if not p.get('enabled', False):
                state = 'disabled'
            elif p.get('free_confirmed') is not True and p.get('billing_allowed') is not True:
                state = 'free_not_confirmed'
            elif not has_key:
                state = 'missing_key'
            elif cooldown_remaining > 0:
                state = 'cooldown'
            elif attempts_today >= p['daily_attempt_limit'] or scope_attempts >= scope_limit:
                state = 'local_quota_exhausted'
            else:
                state = 'ready_locally'

            providers_status.append({
                'name': name,
                'model': p['model'],
                'state': state,
                'quota_scope_id': scope_id,
                'capabilities': p.get('capabilities', []),
                'tasks': p.get('tasks', ['*']),
                'automatic_free_eligible': (automatic_free(p) and bool(p.get('context_window'))
                                            and 'text' in p['capabilities'] and state == 'ready_locally'
                                            and p.get('gateway_attempt_limit', 1) <= self.max_attempts),
                'cost_evidence': p.get('cost_evidence', 'unknown'),
                'route_kind': p.get('route_kind', 'unknown'),
                'context_window': p.get('context_window'),
                'image_context_tokens': p.get('image_context_tokens'),
                'task_priority': p.get('task_priority', {}),
                'gateway_attempt_limit': p.get('gateway_attempt_limit'),
                'gateway_profile_verified': p.get('gateway_profile_verified', False),
                'attempts_today': attempts_today,
                'daily_attempt_limit': p['daily_attempt_limit'],
                'scope_attempts_today': scope_attempts,
                'scope_daily_attempt_limit': scope_limit,
                'cooldown_remaining_seconds': round(cooldown_remaining, 1),
                'metrics': metrics_dict
            })

        return {
            'day_utc': day,
            'quota_source': 'local_attempts_only',
            'providers': providers_status
        }

def cli_main():
    """CLI entry point with safe stdin limit and UTF-8 handling."""
    parser = argparse.ArgumentParser(description="Axx Hardened Inference Router")
    parser.add_argument('--config', default='providers.example.json', help='Path to providers config JSON')
    parser.add_argument('--state', default='state.db', help='Path to state SQLite database')
    parser.add_argument('--status', action='store_true', help='Print status and exit')
    parser.add_argument('--reset-cooldown', metavar='NAME', help='Reset cooldown for provider')
    parser.add_argument('action', nargs='?', default=None, choices=['chat', 'status', 'reset-cooldown'])
    parser.add_argument('target', nargs='?', default=None)

    args = parser.parse_args()

    # Load configuration
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.stderr.write(f"Configuration file not found: {cfg_path}\n")
        sys.exit(1)

    try:
        config = parse_strict_json(cfg_path.read_bytes())
    except Exception as e:
        sys.stderr.write(f"Configuration error: {e}\n")
        sys.exit(1)

    router = None
    try:
        router = Router(config, state=args.state)
        
        # Handle status
        if args.status or args.action == 'status':
            st = router.status()
            sys.stdout.buffer.write(json.dumps(st, indent=2).encode('utf-8'))
            sys.stdout.buffer.write(b'\n')
            sys.exit(0)

        # Handle reset-cooldown
        reset_target = args.reset_cooldown or (args.target if args.action == 'reset-cooldown' else None)
        if reset_target:
            router.reset_cooldown(reset_target)
            sys.stdout.buffer.write(json.dumps({'ok': True, 'reset': reset_target}).encode('utf-8'))
            sys.stdout.buffer.write(b'\n')
            sys.exit(0)

        # Handle chat action: safe limited stdin read (H01)
        if args.action == 'chat' or args.action is None:
            max_limit = router.max_request_bytes + 1
            raw_input = sys.stdin.buffer.read(max_limit)
            if len(raw_input) > router.max_request_bytes:
                sys.stderr.write(f"Request payload exceeds max_request_bytes limit ({router.max_request_bytes})\n")
                sys.exit(1)
            
            try:
                req_obj = parse_strict_json(raw_input)
            except Exception as e:
                sys.stderr.write(f"Invalid JSON on stdin: {e}\n")
                sys.exit(1)

            res = router.chat(req_obj)
            sys.stdout.buffer.write(json.dumps(res, indent=2).encode('utf-8'))
            sys.stdout.buffer.write(b'\n')
            sys.exit(0)

    except Exception as exc:
        err_code = getattr(exc, 'code', 'PROCESS_FAILURE')
        err_dict = {'error': {'code': err_code, 'message': str(exc)}}
        sys.stdout.buffer.write(json.dumps(err_dict, indent=2).encode('utf-8'))
        sys.stdout.buffer.write(b'\n')
        sys.exit(1)
    finally:
        if router:
            router.close()

if __name__ == '__main__':
    cli_main()
