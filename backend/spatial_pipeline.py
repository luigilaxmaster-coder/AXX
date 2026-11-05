"""Helpers of the Magic Pen 3D pipeline: identification pass, catalog retrieval, repair and comparison prompts.

Nothing here calls a model. The service decides when to spend tokens; these functions only build and check text, so they are cheap to test.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.presentation_plan import PlanError, parse_json
from backend.shape_registry import ShapeRegistry

IDENTIFY_CONTRACT = (
    'Eres un analista técnico de objetos. Mira la imagen y responde SOLO con JSON, sin Markdown: '
    '{"objeto":"nombre concreto del objeto","categoria":"mecanico|electrico|mueble|vehiculo|natural|edificio|herramienta|deportivo|otro",'
    '"descripcion":"qué es y para qué sirve, en una frase","vista":"frontal|lateral|trasera|superior|tres cuartos|detalle",'
    '"componentes":[{"nombre":"…","forma":"cilindro|caja|esfera|tubo|placa|…","proporcion":"tamaño aproximado respecto del conjunto","material":"…"}],'
    '"proporcion_global":"largo:alto:ancho aproximado","simetria":"…","buscar":["palabras clave de piezas estándar visibles: tornillo, engranaje, rodamiento, rueda…"],'
    '"dudas":["lo que la imagen no permite saber"]}. Máximo 14 componentes. Describe solo lo que se ve; lo que no se ve va en dudas.'
)
MAX_COMPONENTS = 14
MAX_TEXT = 140
REPAIR_PROMPT = (
    'Tu respuesta anterior no pasó la validación de Axx: {error} Devuelve SOLO el JSON completo y corregido, sin Markdown ni comentarios. '
    'Conserva todo lo que estaba bien (objeto, proporciones, piezas) y corrige únicamente lo indicado.{extra}'
)
LENGTH_REPAIR = (' Tu respuesta anterior se cortó por longitud: devuelve un plan más compacto (hasta 20 piezas, pasos con cuerpo breve, sin anotaciones opcionales) '
                 'pero con el JSON cerrado y válido.')
COMPARE_CONTRACT = (
    'MODO COMPARAR Y CORREGIR: recibes DOS imágenes. La primera es el objeto original seleccionado por el usuario. La segunda es el render actual del modelo 3D que Axx construyó '
    '(puede llevar etiquetas de piezas encima; ignóralas). Compara forma general, proporciones, número y posición de las partes, orientación y color. '
    'Corrige solo las diferencias importantes con un parche (object.update, object.add, object.remove) y responde en "answer" con una lista breve de lo que cambiaste y por qué. '
    'Si el modelo ya se parece bien, devuelve ops vacío y dilo en "answer". No inventes piezas que la imagen original no muestre.'
)


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def parse_blueprint(text: str) -> Dict[str, Any]:
    """Validate the identification answer. Raises PlanError; callers treat any failure as "no blueprint" and carry on."""
    data = parse_json(text)
    if not isinstance(data, dict) or not _clean(data.get('objeto')):
        raise PlanError('La identificación no nombra el objeto.')
    components = []
    for item in (data.get('componentes') if isinstance(data.get('componentes'), list) else [])[:MAX_COMPONENTS]:
        if isinstance(item, dict) and _clean(item.get('nombre')):
            components.append({key: _clean(item.get(key), 80) for key in ('nombre', 'forma', 'proporcion', 'material')})
    words = [_clean(w, 40) for w in (data.get('buscar') if isinstance(data.get('buscar'), list) else [])[:12] if _clean(w, 40)]
    doubts = [_clean(w, 100) for w in (data.get('dudas') if isinstance(data.get('dudas'), list) else [])[:6] if _clean(w, 100)]
    return {'objeto': _clean(data['objeto'], 80), 'categoria': _clean(data.get('categoria'), 30), 'descripcion': _clean(data.get('descripcion'), 200),
            'vista': _clean(data.get('vista'), 30), 'componentes': components, 'proporcion_global': _clean(data.get('proporcion_global'), 60),
            'simetria': _clean(data.get('simetria'), 80), 'buscar': words, 'dudas': doubts}


def _tokens(text: str) -> set:
    return {t for t in re.findall(r'[a-záéíóúñ0-9]{3,}', text.lower()) if t not in {'del', 'las', 'los', 'con', 'una', 'uno', 'para', 'que', 'por'}}


def catalog_matches(registry: ShapeRegistry, blueprint: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    """Catalog components whose id, label, category or aliases share words with what was identified, best first. Pure retrieval, no model."""
    wanted = _tokens(' '.join([blueprint.get('objeto', ''), blueprint.get('categoria', ''), blueprint.get('descripcion', ''), ' '.join(blueprint.get('buscar', [])),
                               ' '.join(c['nombre'] + ' ' + c['forma'] for c in blueprint.get('componentes', []))]))
    explicit = _tokens(' '.join(blueprint.get('buscar', [])))
    scored = []
    for cid, entry in registry.catalog.items():
        words = _tokens(' '.join([cid.replace('_', ' '), entry.get('label', ''), entry.get('category', ''), ' '.join(entry.get('aliases', []))]))
        # A shared word counts once; a word the model asked for explicitly counts double. Substring hits catch plurals ("tornillos" ~ "tornillo").
        score = sum(2 if w in explicit else 1 for w in words if w in wanted)
        score += sum(1 for w in words for t in wanted if w != t and len(w) >= 5 and (w.startswith(t[:5]) and t.startswith(w[:5])))
        if score:
            scored.append((score, cid, entry))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [{'id': cid, 'label': entry['label'], 'parts': len(entry.get('parts', [])), 'size': entry.get('size'), 'score': score} for score, cid, entry in scored[:limit]]


def blueprint_context(blueprint: Dict[str, Any], matches: Optional[List[Dict[str, Any]]] = None) -> str:
    parts = [f"ANÁLISIS PREVIO DE LA IMAGEN (una pasada de identificación; contrástalo con la imagen y corrígelo si ves otra cosa): objeto «{blueprint['objeto']}»"
             + (f" ({blueprint['categoria']})" if blueprint.get('categoria') else '') + '.']
    for key, label in (('descripcion', 'Descripción'), ('vista', 'Vista'), ('proporcion_global', 'Proporción global'), ('simetria', 'Simetría')):
        if blueprint.get(key):
            parts.append(f'{label}: {blueprint[key]}.')
    if blueprint.get('componentes'):
        parts.append('Componentes: ' + '; '.join(f"{c['nombre']} ({', '.join(v for v in (c['forma'], c['proporcion'], c['material']) if v)})" for c in blueprint['componentes']) + '.')
    if blueprint.get('dudas'):
        parts.append('Dudas: ' + '; '.join(blueprint['dudas']) + '. Si algo es dudoso, dilo en el paso «Proporciones y límites» en lugar de inventarlo.')
    if matches:
        parts.append('PIEZAS DEL CATÁLOGO QUE ENCAJAN CON ESTE OBJETO (úsalas con "component" en lugar de reconstruirlas): '
                     + '; '.join(f"{m['id']} ({m['label']}, {m['parts']} piezas)" for m in matches) + '.')
    return ' '.join(parts)


def repair_message(error: Any, *, length: bool = False) -> str:
    return REPAIR_PROMPT.format(error=_clean(error, 400), extra=LENGTH_REPAIR if length else '')
