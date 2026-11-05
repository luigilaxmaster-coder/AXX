"""Ranking of models for Magic Pen (vision, strict JSON, 3D, 2D diagrams), built from what AXX can actually observe.

Order of evidence, strongest first:
  1. Results measured on this computer by the aptitude test ("verificado" / "no_soportado") stored in the capability table.
  2. What a connection or Ollama itself declares ("declarado").
  3. A small bundled reference table (``REFERENCE``), dated and labelled "orientativo": it is an opinion that can be out of date, never a measurement.

Nothing here connects an account, downloads a model or spends tokens. "Actualizar" only asks, read-only, the catalogs of connections the owner
already saved (with their own key) and of the local Ollama. Models that are not connected are shown with instructions; the owner decides.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

REFERENCE_DATE = '2026-11-04'
MAX_ENTRIES = 24
# Points per capability for a verified result; a declared claim counts 40 %, a failed test 0. The 3D scene weighs most because it is the hardest task.
WEIGHTS = {'scene_3d': 45, 'diagram_2d': 15, 'vision': 15, 'json_estricto': 10, 'explicacion': 5}
TASK_NAMES = {'scene_3d': '3D', 'diagram_2d': 'diagrama 2D', 'vision': 'visión', 'json_estricto': 'JSON estricto', 'explicacion': 'explicación'}
# Orientative family priors (0-100, <= 10 points of a score). They only break ties and place models nobody has tested yet.
PRIORS = [
    (r'^claude-(?:fable|opus)-5', 96, 'Claude de mayor capacidad: visión y salida estructurada sólidas.'),
    (r'^claude-sonnet-5', 92, 'Claude equilibrado: visión y JSON estricto probados en AXX.'),
    (r'^claude-haiku-5', 72, 'Claude rápido y económico; planes 3D complejos pueden quedar cortos.'),
    (r'^gpt-6', 93, 'Modelo de ChatGPT/Codex con entrada de imagen.'),
    (r'^gpt-5', 86, 'Familia GPT con visión.'),
    (r'^gpt-4o', 76, 'GPT con visión; planes 3D largos menos fiables.'),
    (r'^gemini-(?:3|2\.5)', 84, 'Gemini con visión.'),
    (r'^gemini', 66, 'Gemini con visión; versiones antiguas.'),
    (r'(?:qwen\d*(?:\.\d+)?-?vl|qwen\d*(?:\.\d+)?vl)', 62, 'Qwen con visión; útil en local.'),
    (r'^gemma[34]', 60, 'Gemma con visión (4B o más).'),
    (r'llama3\.2-vision', 56, 'Llama con visión; local.'),
    (r'(?:minicpm-v|llava)', 48, 'Visión local ligera; pocas veces completa un plan 3D.'),
]
# Models worth offering when nothing equivalent is connected. "how" is shown, never executed.
REFERENCE = [
    {'provider': 'Anthropic', 'model': 'claude-opus-5-5', 'how': 'Añade tu clave de Anthropic en Ajustes > Proveedores (protocolo Anthropic) con visión activada.'},
    {'provider': 'Anthropic', 'model': 'claude-sonnet-5-5', 'how': 'Añade tu clave de Anthropic en Ajustes > Proveedores (protocolo Anthropic) con visión activada.'},
    {'provider': 'ChatGPT/Codex', 'model': 'gpt-6.1-sol', 'how': 'Se usa con tu suscripción de ChatGPT desde AXX Connect; no requiere clave.'},
    {'provider': 'Ollama', 'model': 'qwen2.5vl:7b', 'how': 'Instalación local, la haces tú: ollama pull qwen2.5vl:7b', 'local': True},
    {'provider': 'Ollama', 'model': 'llama3.2-vision:11b', 'how': 'Instalación local, la haces tú: ollama pull llama3.2-vision:11b', 'local': True},
    {'provider': 'Ollama', 'model': 'gemma3:12b', 'how': 'Instalación local, la haces tú: ollama pull gemma3:12b', 'local': True},
]
STATUS_LABELS = {
    'apto_3d': 'Conectado · apto para 3D (prueba básica superada)',
    'conectado': 'Conectado · sin verificar para 3D',
    'solo_2d': 'Conectado · solo 2D (3D no apto)',
    'instalado': 'Instalado en Ollama · sin conexión AXX',
    'en_cuenta': 'Disponible en tu cuenta · sin conexión AXX',
    'recomendado': 'No conectado · recomendado',
}
KEY_STATUS_ORDER = {'apto_3d': 0, 'conectado': 1, 'solo_2d': 2, 'instalado': 3, 'en_cuenta': 4, 'recomendado': 5}


def prior(model: str) -> tuple[int, str]:
    for pattern, score, note in PRIORS:
        if re.search(pattern, model.lower()):
            return score, note
    return 0, ''


def score_of(aptitude: Optional[Dict[str, str]], model: str) -> tuple[float, str]:
    """(score, basis). Measured points dominate; the prior adds at most 10 and alone caps at 50, so an untested model never outranks a verified one."""
    base, note = prior(model)
    points, measured = 0.0, False
    for capability, weight in WEIGHTS.items():
        level = (aptitude or {}).get(capability)
        if level == 'verificado':
            points, measured = points + weight, True
        elif level == 'declarado':
            points += weight * .4
        elif level == 'no_soportado':
            measured = True
    if measured:
        return round(points + base * .1, 1), 'Medido en este equipo' + (' · ' + note if note else '')
    return round(min(50, points + base * .5), 1), ('Orientativo · ' + note if note else 'Sin datos: pruébalo con «Probar conexión»') + ' (referencia AXX ' + REFERENCE_DATE + ')'


def _tasks(aptitude: Optional[Dict[str, str]]) -> Dict[str, List[str]]:
    levels = aptitude or {}
    return {'verificado': [TASK_NAMES[c] for c in WEIGHTS if levels.get(c) == 'verificado'],
            'declarado': [TASK_NAMES[c] for c in WEIGHTS if levels.get(c) == 'declarado'],
            'no_apto': [TASK_NAMES[c] for c in WEIGHTS if levels.get(c) == 'no_soportado']}


def _connected(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        aptitude = row.get('aptitude') or {}
        level = aptitude.get('scene_3d')
        status = 'apto_3d' if level == 'verificado' else 'solo_2d' if level == 'no_soportado' else 'conectado'
        provider = 'ChatGPT/Codex' if row['name'] == '@codex' else row['name']
        score, basis = score_of(aptitude, row['model'])
        out.append({'provider': provider, 'connection': row['name'], 'model': row['model'], 'status': status, 'score': score, 'basis': basis,
                    'tasks': _tasks(aptitude), 'action': {'type': 'select', 'key': row['name'] + '::' + row['model']}})
    return out


def build(rows: List[Dict[str, Any]], *, discovered: Optional[List[Dict[str, Any]]] = None, ollama: Optional[Dict[str, Any]] = None,
          refreshed: bool = False, clock: Callable[[], float] = time.time) -> Dict[str, Any]:
    """rows: selectable vision models (capabilities()); discovered: [{connection, models}] from catalogs; ollama: ollama_models.detect() or None."""
    entries = _connected(rows)
    have = {(e['connection'], e['model']) for e in entries}
    sources = [{'name': 'Conexiones de AXX', 'state': 'ok', 'message': f'{len(entries)} modelo(s) visual(es) conectados y su prueba de aptitud guardada.'}]
    if ollama is not None:
        sources.append({'name': 'Ollama local', 'state': 'ok' if ollama.get('available') else 'unavailable',
                        'message': (f"{len(ollama.get('models', []))} modelo(s) instalados." if ollama.get('available') else ollama.get('message') or 'Ollama no disponible.')})
        for item in ollama.get('models', []):
            if item.get('configured_as') or (item['name'] and any(e['model'] == item['name'] and e['provider'] != 'ChatGPT/Codex' for e in entries)):
                continue
            if not item.get('vision') and not prior(item['name'])[0]:
                continue  # a text-only local model is of no use for this function
            aptitude = {'vision': 'declarado'} if item.get('vision') else {}
            score, basis = score_of(aptitude, item['name'])
            entries.append({'provider': 'Ollama', 'connection': '', 'model': item['name'], 'status': 'instalado', 'score': score, 'basis': basis,
                            'tasks': _tasks(aptitude), 'action': {'type': 'connect', 'text': 'Está instalado en tu Ollama. Para usarlo, añádelo como conexión en Ajustes > Proveedores; AXX no lo conecta solo.'}})
    for catalog in discovered or []:
        sources.append({'name': 'Catálogo de ' + str(catalog.get('connection', '?')), 'state': 'ok' if catalog.get('ok') else 'unavailable',
                        'message': (f"{len(catalog.get('models', []))} modelo(s) en la cuenta." if catalog.get('ok') else catalog.get('message') or 'No respondió.')})
        for model in catalog.get('models', []) if catalog.get('ok') else []:
            if (catalog['connection'], model) in have or not prior(model)[0]:
                continue
            if any(e['model'] == model and e['provider'] == catalog.get('provider') for e in entries):
                continue
            score, basis = score_of({}, model)
            entries.append({'provider': catalog.get('provider') or catalog['connection'], 'connection': catalog['connection'], 'model': model, 'status': 'en_cuenta',
                            'score': score, 'basis': basis, 'tasks': _tasks({}),
                            'action': {'type': 'connect', 'text': f"Tu cuenta «{catalog['connection']}» lo ofrece. Para usarlo, añade o edita la conexión en Ajustes > Proveedores y activa visión; AXX no lo activa solo."}})
    present = {(e['provider'], e['model']) for e in entries}
    for ref in REFERENCE:
        if (ref['provider'], ref['model']) in present or any(e['model'] == ref['model'] for e in entries):
            continue
        score, basis = score_of({}, ref['model'])
        entries.append({'provider': ref['provider'], 'connection': '', 'model': ref['model'], 'status': 'recomendado', 'score': score, 'basis': basis,
                        'tasks': _tasks({}), 'action': {'type': 'connect', 'text': ref['how']}})
    entries.sort(key=lambda e: (-e['score'], KEY_STATUS_ORDER[e['status']], e['model']))
    entries = entries[:MAX_ENTRIES]
    for position, entry in enumerate(entries, 1):
        entry['rank'], entry['status_label'] = position, STATUS_LABELS[entry['status']]
    return {'generated_at': int(clock()), 'reference_date': REFERENCE_DATE, 'refreshed': refreshed, 'entries': entries, 'sources': sources,
            'note': 'El orden usa primero pruebas medidas en este equipo y después referencias orientativas. Ningún modelo se conecta ni se descarga sin tu decisión.'}


def gather(capabilities: Dict[str, Any], config: Dict[str, Any], *, refresh: bool, discover_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
           ollama_fn: Callable[[str], Dict[str, Any]], ollama_url: str, clock: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Without ``refresh`` nothing leaves the computer. With it, each already-saved connection with a key lists its own catalog (read-only)."""
    rows = [*capabilities.get('vision', []), *capabilities.get('codex_vision', [])]
    if not refresh:
        return build(rows, refreshed=False, clock=clock)
    ollama = ollama_fn(ollama_url)
    for item in ollama.get('models', []):  # same rule as /axx-api/ollama/models: a model is "connected" only when the owner saved it for this Ollama
        item['configured_as'] = next((p['name'] for p in config.get('providers', []) if p.get('model') == item['name']
                                      and str(p.get('base_url', '')).rstrip('/').removesuffix('/v1') == ollama.get('base_url')), None)
    seen, discovered = set(), []
    for provider in config.get('providers', []):
        kind = provider.get('kind')
        if not provider.get('enabled', True) or kind in (None, 'freellmapi', 'custom', 'compat') or (kind, provider.get('base_url')) in seen:
            continue
        seen.add((kind, provider.get('base_url')))
        label = {'anthropic': 'Anthropic', 'ollama_cloud': 'Ollama Cloud', 'openai': 'OpenAI', 'gemini': 'Gemini', 'groq': 'Groq', 'openrouter': 'OpenRouter', 'ollama': 'Ollama'}.get(kind, kind)
        try:
            result = discover_fn({'name': provider['name'], 'provider': kind, 'base_url': provider['base_url'], 'protocol': provider.get('protocol', 'openai')}, config)
            models = result.get('models') if isinstance(result, dict) else None
            discovered.append({'connection': provider['name'], 'provider': label, 'ok': isinstance(models, list), 'models': [m for m in models or [] if isinstance(m, str)][:300],
                               'message': '' if isinstance(models, list) else str((result or {}).get('error', {}).get('message', 'Catálogo no disponible.'))[:200]})
        except Exception as exc:  # a catalog that fails must not hide the others; the reason is shown, never a stack trace
            discovered.append({'connection': provider['name'], 'provider': label, 'ok': False, 'models': [], 'message': str(exc)[:200] or 'Catálogo no disponible.'})
    return build(rows, discovered=discovered, ollama=ollama, refreshed=True, clock=clock)
