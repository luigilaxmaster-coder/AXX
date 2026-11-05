"""Ranking of the models that exist today for Magic Pen (explain an image as a detailed 3D model), with what is needed to use each one.

Evidence, strongest first:
  1. Aptitude measured on this computer ("verificado" / "no_soportado") from the capability table. It adds to or subtracts from the market score.
  2. The market score from public catalogues (``market_catalog``): computed only from published fields, never from the model's name.
  3. Nothing else. There is no bundled opinion table: a model without data says so.

"Actualizar" is read-only: it downloads two public catalogues (no key, nothing about the user is sent), asks the catalogues of connections the
owner already saved and the local Ollama. Nothing is connected, activated or downloaded here: for every model that is not connected the ranking
offers a pre-filled connection form and the owner pastes their own key and presses Save.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend import market_catalog

MAX_ENTRIES = 40
MAX_CACHED = 150
# Measured evidence moves a model up or down; 3D weighs most because it is the hardest task of the function.
MEASURED_BONUS = {'scene_3d': 15, 'diagram_2d': 3, 'vision': 3, 'json_estricto': 3, 'explicacion': 1}
TASK_NAMES = {'scene_3d': '3D', 'diagram_2d': 'diagrama 2D', 'vision': 'visión', 'json_estricto': 'JSON estricto', 'explicacion': 'explicación'}
NO_MARKET_BASE = 40.0  # a connected model the catalogues do not list (for example a subscription route) starts neutral and lives on its measurements
STATUS_LABELS = {
    'apto_3d': 'Conectado · apto para 3D (prueba básica superada)',
    'conectado': 'Conectado · sin verificar para 3D',
    'solo_2d': 'Conectado · solo 2D (3D no apto)',
    'instalado': 'Instalado en tu Ollama · sin conexión AXX',
    'configurable': 'No conectado · configúralo aquí',
}
STATUS_ORDER = {'apto_3d': 0, 'conectado': 1, 'solo_2d': 2, 'instalado': 3, 'configurable': 4}
KIND_LABELS = {'anthropic': 'Anthropic', 'openai': 'OpenAI', 'gemini': 'Google Gemini', 'openrouter': 'OpenRouter (una clave para casi todos)', 'ollama_cloud': 'Ollama Cloud'}


def norm(model: str) -> str:
    """Comparable id: lower case, no variant suffix, dots and dashes alike (Anthropic's native 5-5 is OpenRouter's 5.5)."""
    return re.sub(r'[.]', '-', str(model).lower().split(':')[0].strip())


def _measured(aptitude: Optional[Dict[str, str]]) -> Dict[str, Any]:
    levels = aptitude or {}
    bonus, reasons = 0.0, []
    for capability, weight in MEASURED_BONUS.items():
        level = levels.get(capability)
        if level == 'verificado':
            bonus += weight
        elif level == 'no_soportado' and capability == 'scene_3d':
            bonus -= 40
    if levels.get('scene_3d') == 'verificado':
        reasons.append('prueba de 3D superada en este equipo (+%d)' % MEASURED_BONUS['scene_3d'])
    elif levels.get('scene_3d') == 'no_soportado':
        reasons.append('falló la prueba de 3D en este equipo (-40)')
    return {'bonus': bonus, 'reasons': reasons, 'tasks': {
        'verificado': [TASK_NAMES[c] for c in TASK_NAMES if levels.get(c) == 'verificado'],
        'declarado': [TASK_NAMES[c] for c in TASK_NAMES if levels.get(c) == 'declarado'],
        'no_apto': [TASK_NAMES[c] for c in TASK_NAMES if levels.get(c) == 'no_soportado']}}


def _release(created: Optional[float], now: float) -> Optional[int]:
    return int((now - created) / 86400) if created else None


def _configure_options(market: Dict[str, Any], connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pre-filled connection forms that would make this model usable. The key is never included: the owner types it themselves."""
    options = []
    if market['source'] == 'ollama_cloud':
        options.append({'kind': 'ollama_cloud', 'model': market['model'], 'name': 'ollama-' + re.sub(r'[^a-z0-9]+', '-', market['model'].lower()).strip('-')[:40]})
    else:
        native = market_catalog.NATIVE_KINDS.get(market['company'])
        if native:
            model = market['model'].replace('.', '-') if native == 'anthropic' else market['model']
            options.append({'kind': native, 'model': model, 'name': native + '-' + re.sub(r'[^a-z0-9]+', '-', model.lower()).strip('-')[:40]})
        options.append({'kind': market_catalog.AGGREGATE_KIND, 'model': market['id'], 'name': 'openrouter-' + re.sub(r'[^a-z0-9]+', '-', market['model'].lower()).strip('-')[:40]})
    saved_kinds = {c.get('kind') for c in connections}
    for option in options:
        option['label'] = 'Configurar con ' + KIND_LABELS.get(option['kind'], option['kind'])
        option['has_connection_kind'] = option['kind'] in saved_kinds  # the owner already trusts that provider; a new key may still be needed for a new name
        option['vision'] = True
    return options


def _market_info(market: Dict[str, Any], now: float, rank: Optional[int] = None, total: int = 0) -> Dict[str, Any]:
    price = {'in': market.get('usd_per_mtok_in'), 'out': market.get('usd_per_mtok_out'), 'free': market.get('free')}
    return {'company': market['company'], 'source': market['source'], 'context': market.get('context'), 'max_output_tokens': market.get('max_output_tokens'),
            'structured_outputs': market.get('structured_outputs'), 'reasoning': market.get('reasoning'), 'price': price, 'released_days_ago': _release(market.get('created'), now),
            'market_rank': rank, 'market_total': total, 'market_score': market.get('score')}


def build(rows: List[Dict[str, Any]], *, market: Optional[Dict[str, Any]] = None, discovered: Optional[List[Dict[str, Any]]] = None,
          ollama: Optional[Dict[str, Any]] = None, connections: Optional[List[Dict[str, Any]]] = None, refreshed: bool = False,
          clock: Callable[[], float] = time.time) -> Dict[str, Any]:
    """rows: selectable vision models from capabilities(); market: load_market() or a cached copy; connections: the owner's saved connections."""
    now = clock()
    connections = connections or []
    kind_of = {c.get('name'): c.get('kind') for c in connections}
    market_models = (market or {}).get('models', [])
    market_models = sorted(market_models, key=lambda m: -m['score'])
    by_norm: Dict[str, Dict[str, Any]] = {}
    market_rank: Dict[str, int] = {}
    for position, item in enumerate(market_models, 1):
        by_norm.setdefault(norm(item['model']), item)  # the best scored variant of a model represents it
        market_rank.setdefault(norm(item['model']), position)
    total = len(market_models)
    info = lambda item: _market_info(item, now, market_rank.get(norm(item['model'])), total)
    account = {norm(m) for catalog in (discovered or []) if catalog.get('ok') for m in catalog.get('models', [])}
    entries, used = [], set()
    for row in rows:
        listed = by_norm.get(norm(row['model']))
        measured = _measured(row.get('aptitude'))
        level = (row.get('aptitude') or {}).get('scene_3d')
        status = 'apto_3d' if level == 'verificado' else 'solo_2d' if level == 'no_soportado' else 'conectado'
        base = listed['score'] if listed else NO_MARKET_BASE
        reasons = (listed['reasons'] if listed else ['sin datos públicos de este modelo; parte de %d' % NO_MARKET_BASE]) + measured['reasons']
        used.add(norm(row['model']))
        entries.append({'provider': 'ChatGPT/Codex' if row['name'] == '@codex' else row['name'], 'connection': row['name'], 'model': row['model'], 'status': status,
                        'score': round(max(0.0, min(130.0, base + measured['bonus'])), 1), 'reasons': reasons, 'tasks': measured['tasks'],
                        'market': info(listed) if listed else None, 'kind': kind_of.get(row['name']),
                        'action': {'type': 'select', 'key': row['name'] + '::' + row['model']}})
    sources = [{'name': 'Conexiones de AXX', 'state': 'ok', 'message': f'{len(entries)} modelo(s) visual(es) conectados y su prueba de aptitud guardada.'}]
    for source in (market or {}).get('sources', []):
        sources.append(source)
    if market is None:
        sources.append({'name': 'Mercado', 'state': 'unavailable', 'message': 'Pulsa «Actualizar ranking» para cargar los modelos actuales de OpenRouter y Ollama Cloud.'})
    if ollama is not None:
        sources.append({'name': 'Ollama local', 'state': 'ok' if ollama.get('available') else 'unavailable',
                        'message': f"{len(ollama.get('models', []))} modelo(s) instalados." if ollama.get('available') else ollama.get('message') or 'Ollama no disponible.'})
        for item in ollama.get('models', []):
            if item.get('configured_as') or norm(item['name']) in used or not item.get('vision'):
                continue
            used.add(norm(item['name']))
            listed = by_norm.get(norm(item['name']))
            entries.append({'provider': 'Ollama', 'connection': '', 'model': item['name'], 'status': 'instalado', 'score': round(listed['score'] if listed else NO_MARKET_BASE, 1),
                            'reasons': (listed['reasons'] if listed else ['visión declarada por Ollama; sin más datos públicos']), 'tasks': _measured({'vision': 'declarado'})['tasks'],
                            'market': info(listed) if listed else None, 'kind': 'ollama',
                            'action': {'type': 'configure', 'options': [{'kind': 'ollama', 'model': item['name'], 'name': 'ollama-' + re.sub(r'[^a-z0-9]+', '-', item['name'].lower()).strip('-')[:40],
                                                                       'label': 'Configurar con tu Ollama local', 'vision': True, 'has_connection_kind': True}],
                                       'note': 'Está instalado en tu Ollama. Guárdalo como conexión y pasa «Probar conexión»: AXX no lo conecta solo.'}})
    for item in market_models:
        if norm(item['model']) in used:
            continue
        used.add(norm(item['model']))
        in_account = norm(item['model']) in account
        options = _configure_options(item, connections)
        note = ('Tu cuenta ya lo ofrece: pega la misma clave. ' if in_account else '') + 'AXX no lo conecta ni guarda claves; tú eliges y la clave es tuya (se guarda cifrada con DPAPI).'
        native = market_catalog.NATIVE_KINDS.get(item['company'])
        entries.append({'provider': KIND_LABELS[native].split(' (')[0] if native else ('Ollama Cloud' if item['source'] == 'ollama_cloud' else item['company']),
                        'connection': '', 'model': item['model'] if item['source'] == 'ollama_cloud' else item['id'], 'status': 'configurable', 'score': item['score'],
                        'reasons': item['reasons'], 'tasks': _measured(None)['tasks'], 'market': info(item), 'kind': None, 'in_account': in_account,
                        'action': {'type': 'configure', 'options': options, 'note': note}})
    entries.sort(key=lambda e: (-e['score'], STATUS_ORDER[e['status']], e['model']))
    connected_first = [e for e in entries if e['status'] in ('apto_3d', 'conectado', 'solo_2d')]
    others = [e for e in entries if e['status'] not in ('apto_3d', 'conectado', 'solo_2d')][:max(0, MAX_ENTRIES - len(connected_first))]
    entries = sorted(connected_first + others, key=lambda e: (-e['score'], STATUS_ORDER[e['status']], e['model']))
    for position, entry in enumerate(entries, 1):
        entry['rank'], entry['status_label'] = position, STATUS_LABELS[entry['status']]
    return {'generated_at': int(now), 'market_at': (market or {}).get('at'), 'refreshed': refreshed, 'entries': entries, 'sources': sources,
            'note': ('Orden = estimación con datos públicos de cada modelo (visión, JSON estricto, salida larga, razonamiento, nivel de precio/tamaño y novedad) '
                     '+ lo que mediste en este equipo. No es un benchmark. Nada se conecta, activa ni descarga sin tu decisión.')}


def _load_cache(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8')) if path else None
        return data if isinstance(data, dict) and isinstance(data.get('models'), list) else None
    except (OSError, ValueError):
        return None


def _save_cache(path: Optional[Path], market: Dict[str, Any]) -> None:
    if not path:
        return
    try:
        trimmed = {**market, 'models': sorted(market['models'], key=lambda m: -m['score'])[:MAX_CACHED]}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(str(path) + '.tmp')
        temporary.write_text(json.dumps(trimmed, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
    except OSError:
        pass  # a cache that cannot be written only costs the next offline start a refresh


def gather(capabilities: Dict[str, Any], config: Dict[str, Any], *, refresh: bool, discover_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
           ollama_fn: Callable[[str], Dict[str, Any]], ollama_url: str, market_fn: Callable[[], Dict[str, Any]] = market_catalog.load_market,
           cache_path: Optional[Path] = None, clock: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Without ``refresh`` nothing leaves the computer (the last downloaded market, if any, is reused). With it: public catalogues, the owner's saved
    connections (read-only, with their own key) and the local Ollama."""
    rows = [*capabilities.get('vision', []), *capabilities.get('codex_vision', [])]
    connections = [p for p in config.get('providers', []) if isinstance(p, dict)]
    if not refresh:
        return build(rows, market=_load_cache(cache_path), connections=connections, refreshed=False, clock=clock)
    market = market_fn()
    if market.get('models'):
        _save_cache(cache_path, market)
    else:
        market = {**(_load_cache(cache_path) or {'models': [], 'at': None}), 'sources': market.get('sources', [])}
    ollama = ollama_fn(ollama_url)
    for item in ollama.get('models', []):  # same rule as /axx-api/ollama/models: "connected" only when the owner saved it for this Ollama
        item['configured_as'] = next((p['name'] for p in connections if p.get('model') == item['name']
                                      and str(p.get('base_url', '')).rstrip('/').removesuffix('/v1') == ollama.get('base_url')), None)
    seen, discovered = set(), []
    for provider in connections:
        kind = provider.get('kind')
        if not provider.get('enabled', True) or kind in (None, 'freellmapi', 'custom', 'compat') or (kind, provider.get('base_url')) in seen:
            continue
        seen.add((kind, provider.get('base_url')))
        label = KIND_LABELS.get(kind, kind).split(' (')[0]
        try:
            result = discover_fn({'name': provider['name'], 'provider': kind, 'base_url': provider['base_url'], 'protocol': provider.get('protocol', 'openai')}, config)
            models = result.get('models') if isinstance(result, dict) else None
            discovered.append({'connection': provider['name'], 'provider': label, 'ok': isinstance(models, list), 'models': [m for m in models or [] if isinstance(m, str)][:300],
                               'message': '' if isinstance(models, list) else 'Catálogo no disponible.'})
        except Exception as exc:  # a catalog that fails must not hide the others; the reason is shown, never a stack trace
            discovered.append({'connection': provider['name'], 'provider': label, 'ok': False, 'models': [], 'message': str(exc)[:200] or 'Catálogo no disponible.'})
    result = build(rows, market=market if market.get('models') else None, discovered=discovered, ollama=ollama, connections=connections, refreshed=True, clock=clock)
    for catalog in discovered:
        result['sources'].append({'name': 'Catálogo de ' + catalog['connection'], 'state': 'ok' if catalog['ok'] else 'unavailable',
                                  'message': f"{len(catalog['models'])} modelo(s) en la cuenta." if catalog['ok'] else catalog['message']})
    return result
