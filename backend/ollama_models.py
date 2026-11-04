"""Detect locally installed Ollama models and the capabilities Ollama itself declares (/api/show).

Read-only and local-only: no model is run, no file is written, redirects are refused. When Ollama cannot be reached the result says
so explicitly instead of raising a generic error.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from backend.inference.provider_settings import local_address
from backend.inference.router import NoRedirect

DEFAULT_URL = 'http://127.0.0.1:11434'
MAX_MODELS = 40
MAX_BYTES = 2 * 1024 * 1024


def _get(opener, url: str, body: Any = None, timeout: float = 3) -> Dict[str, Any]:
    request = urllib.request.Request(url, method='POST' if body is not None else 'GET', data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Accept': 'application/json', **({'Content-Type': 'application/json'} if body is not None else {})})
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Respuesta de Ollama demasiado grande')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('Respuesta de Ollama inválida')
    return data


def detect(base_url: str = DEFAULT_URL, *, timeout: float = 3, opener=None) -> Dict[str, Any]:
    base = (base_url or DEFAULT_URL).strip().rstrip('/').removesuffix('/v1')
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.query or not local_address(parts.hostname):
        raise ValueError('La detección solo consulta un Ollama en una dirección local o privada.')
    opener = opener or urllib.request.build_opener(NoRedirect())
    try:
        tags = _get(opener, base + '/api/tags', timeout=timeout)
        names = [m.get('name') or m.get('model') for m in tags.get('models', []) if isinstance(m, dict)]
        models: List[Dict[str, Any]] = []
        for name in [n for n in names if isinstance(n, str) and 0 < len(n) <= 200][:MAX_MODELS]:
            try:
                shown = _get(opener, base + '/api/show', {'model': name}, timeout=timeout)
            except (OSError, ValueError):
                shown = {}
            declared = shown.get('capabilities')
            capabilities = [c for c in declared if isinstance(c, str)][:12] if isinstance(declared, list) else []
            details = shown.get('details') if isinstance(shown.get('details'), dict) else {}
            models.append({'name': name, 'capabilities': capabilities, 'vision': 'vision' in capabilities,
                           'declared': isinstance(declared, list),  # False: this Ollama version does not report capabilities
                           'family': str(details.get('family', ''))[:40], 'parameters': str(details.get('parameter_size', ''))[:20]})
        return {'available': True, 'base_url': base, 'models': models, 'message': ''}
    except urllib.error.HTTPError as exc:
        return {'available': False, 'base_url': base, 'models': [], 'message': f'Ollama respondió HTTP {exc.code} en {base}.'}
    except (OSError, ValueError) as exc:  # URLError, timeouts, refused connections, malformed JSON
        reason = 'respuesta no válida' if isinstance(exc, ValueError) else 'sin conexión'
        return {'available': False, 'base_url': base, 'models': [], 'message': f'Ollama no disponible en {base} ({reason}).'}
