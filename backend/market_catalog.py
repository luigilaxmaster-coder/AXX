"""Public catalogues of models that exist today, read-only, for the Magic Pen ranking.

Two sources, both public GET endpoints that need no key and send nothing about the user:
  * OpenRouter ``/api/v1/models``: hundreds of current models with modalities, supported parameters, output limits, reasoning, prices and release date.
  * Ollama Cloud ``/api/tags``: the models Ollama serves in its cloud, with the capabilities Ollama itself declares (vision, tools, thinking).

Nothing is downloaded or connected. The score is computed only from fields these catalogues publish (never from the model's name), and it is an
estimate of fitness for "explain this image as a detailed 3D model": vision, strict JSON, a large output limit, reasoning, size/price tier and age.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

OPENROUTER_URL = 'https://openrouter.ai/api/v1/models'
OLLAMA_CLOUD_URL = 'https://ollama.com/api/tags'
MAX_BYTES = 6 * 1024 * 1024
DAY = 86400
# OpenRouter provider prefix -> the connection kind Axx can use directly with that company's own key.
NATIVE_KINDS = {'anthropic': 'anthropic', 'openai': 'openai', 'google': 'gemini'}
AGGREGATE_KIND = 'openrouter'
# Variants that are the same model sold differently; they would crowd the ranking with duplicates.
DUPLICATE_SUFFIXES = (':batch', ':extended', ':nitro', ':floor', ':online', ':exacto')


def fetch_json(url: str, *, timeout: float = 15, opener=None) -> Any:
    request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Axx-model-ranking/1.0'})
    with (opener or urllib.request.build_opener()).open(request, timeout=timeout) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('El catálogo público es demasiado grande.')
    return json.loads(raw)


def _price(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number * 1_000_000 if number >= 0 and math.isfinite(number) else None  # catalogues publish USD per token; people read USD per million


def market_score(entry: Dict[str, Any], now: float) -> Dict[str, Any]:
    """0-100 estimate from published fields. Returns the score and one human reason per component, so the number can be audited."""
    points, reasons = 0.0, []
    if entry.get('structured_outputs'):
        points += 20; reasons.append('salida JSON estricta (+20)')
    out_limit = entry.get('max_output_tokens') or 0
    if out_limit >= 32000:
        points += 12; reasons.append('salida de 32 000 tokens o más (+12)')
    elif out_limit >= 16000:
        points += 10; reasons.append('salida de 16 000 tokens o más (+10)')
    elif out_limit >= 8000:
        points += 5; reasons.append('salida de 8 000 tokens o más (+5)')
    if (entry.get('context') or 0) >= 200_000:
        points += 5; reasons.append('contexto de 200 000 o más (+5)')
    if entry.get('reasoning'):
        points += 8; reasons.append('razonamiento (+8)')
    out_price = entry.get('usd_per_mtok_out')
    if out_price:  # price per output token tracks model size/tier closely; log scale, 0 at 0.3 USD/M, 30 at 30 USD/M
        tier = max(0.0, min(30.0, 15 * math.log10(max(out_price, 0.01) / 0.3)))
        points += tier; reasons.append(f'nivel de precio/tamaño ({entry["usd_per_mtok_out"]:.2f} USD/M de salida, +{tier:.0f})')
    elif entry.get('parameters_b'):  # Ollama publishes size, not price
        tier = max(0.0, min(30.0, 12 * math.log10(max(entry['parameters_b'], 1) / 4)))
        points += tier; reasons.append(f'tamaño de {entry["parameters_b"]:.0f} mil millones de parámetros (+{tier:.0f})')
    age = (now - entry['created']) / DAY if entry.get('created') else None
    if age is not None:
        gain = 25 if age <= 90 else 18 if age <= 180 else 10 if age <= 365 else 3
        points += gain; reasons.append(f'lanzado hace {int(age)} días (+{gain})')
    return {'score': round(min(100.0, points), 1), 'reasons': reasons}


def openrouter_models(payload: Any, now: float) -> List[Dict[str, Any]]:
    """Vision-capable models of the OpenRouter catalogue, normalised and scored. Pure function over the downloaded JSON."""
    models = []
    for item in (payload.get('data') if isinstance(payload, dict) else None) or []:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            continue
        model_id = item['id']
        arch = item.get('architecture') if isinstance(item.get('architecture'), dict) else {}
        if 'image' not in (arch.get('input_modalities') or []) or model_id.endswith(DUPLICATE_SUFFIXES) or model_id.startswith('~'):
            continue
        expiration = item.get('expiration_date')
        if isinstance(expiration, str) and expiration:
            continue  # announced for removal
        supported = item.get('supported_parameters') if isinstance(item.get('supported_parameters'), list) else []
        top = item.get('top_provider') if isinstance(item.get('top_provider'), dict) else {}
        pricing = item.get('pricing') if isinstance(item.get('pricing'), dict) else {}
        free = model_id.endswith(':free') or (_price(pricing.get('prompt')) == 0 and _price(pricing.get('completion')) == 0)
        company, _, name = model_id.partition('/')
        entry = {'id': model_id, 'name': str(item.get('name') or model_id)[:120], 'company': company, 'model': name, 'source': 'openrouter',
                 'created': item.get('created') if isinstance(item.get('created'), (int, float)) else None,
                 'context': item.get('context_length') if isinstance(item.get('context_length'), int) else None,
                 'max_output_tokens': top.get('max_completion_tokens') if isinstance(top.get('max_completion_tokens'), int) else None,
                 'structured_outputs': 'structured_outputs' in supported or 'response_format' in supported,
                 'reasoning': isinstance(item.get('reasoning'), dict) or 'reasoning' in supported,
                 'usd_per_mtok_in': _price(pricing.get('prompt')), 'usd_per_mtok_out': _price(pricing.get('completion')), 'free': bool(free)}
        entry.update(market_score(entry, now))
        models.append(entry)
    return models


def ollama_cloud_models(payload: Any, now: float) -> List[Dict[str, Any]]:
    models = []
    for item in (payload.get('models') if isinstance(payload, dict) else None) or []:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            continue
        capabilities = [c for c in (item.get('capabilities') or []) if isinstance(c, str)]
        if 'vision' not in capabilities:
            continue
        details = item.get('details') if isinstance(item.get('details'), dict) else {}
        size = details.get('parameter_size')
        try:
            parameters_b = float(size) / 1e9 if size is not None and float(size) > 1e6 else float(str(size).lower().rstrip('b'))
        except (TypeError, ValueError):
            parameters_b = None
        modified = item.get('modified_at')
        created = None
        if isinstance(modified, str):
            try:
                created = time.mktime(time.strptime(modified[:10], '%Y-%m-%d'))
            except ValueError:
                created = None
        entry = {'id': item['name'], 'name': item['name'], 'company': 'ollama', 'model': item['name'], 'source': 'ollama_cloud', 'created': created,
                 'context': None, 'max_output_tokens': None, 'structured_outputs': False, 'reasoning': 'thinking' in capabilities,
                 'usd_per_mtok_in': None, 'usd_per_mtok_out': None, 'free': None, 'parameters_b': parameters_b, 'capabilities': capabilities}
        entry.update(market_score(entry, now))
        models.append(entry)
    return models


def load_market(*, now: Optional[float] = None, fetch: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Both catalogues; one failing never hides the other. Returns models plus a per-source status for the UI."""
    now, fetch = now or time.time(), fetch or fetch_json  # resolved at call time so tests can replace the downloader
    models, sources = [], []
    for name, url, parser in (('OpenRouter', OPENROUTER_URL, openrouter_models), ('Ollama Cloud', OLLAMA_CLOUD_URL, ollama_cloud_models)):
        try:
            found = parser(fetch(url), now)
            models += found
            sources.append({'name': name, 'state': 'ok', 'message': f'{len(found)} modelo(s) con visión.'})
        except (OSError, ValueError, urllib.error.URLError) as exc:
            sources.append({'name': name, 'state': 'unavailable', 'message': f'No se pudo consultar ({type(exc).__name__}).'})
    return {'models': models, 'sources': sources, 'at': int(now)}
