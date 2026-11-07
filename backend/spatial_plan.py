"""Declarative Spatial Presentation Plan and strict provider gating for Axx Magic Pen.

Only approved GPT fast models (such as gpt-6.1-sol-fast) with verified structured JSON
support are permitted to generate interactive 3D scene plans.
Local providers (Ollama, LM Studio, etc.) are strictly routed to 2D canvas/SVG overlays
and conversational perception, preventing hallucinated 3D schemas, GPU stalls, or latency spikes.
"""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

LOG = logging.getLogger('axx.spatial_plan')

ALLOWED_MODES = frozenset({'overlay_2d', 'math_graph', 'interactive_3d', 'diagram_2d'})
ALLOWED_ANNOTATION_TYPES = frozenset({'box', 'arrow', 'callout', 'spotlight'})
ALLOWED_PRIMITIVES = frozenset({
    'box', 'cylinder', 'sphere', 'tube', 'shaft', 'piston', 'pcb', 'chip', 'wire', 'arrow'
})

HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
SCRIPT_RE = re.compile(r'<\s*script|javascript\s*:', re.IGNORECASE)
MAX_PRIMITIVES = 128
MAX_ANNOTATIONS = 64
MAX_SUMMARY_LEN = 1000
MAX_LABEL_LEN = 200
MAX_DETAIL_LEN = 800


def is_gpt_fast_model(provider_name: str | None, model_name: str | None) -> bool:
    """Check if the provider and model qualify for strict 3D procedural spatial synthesis.

    Rule: Only GPT-6.1 sol fast (or GPT-6 fast equivalents) with native structured JSON
    support are permitted for 3D spatial explanation. Local/Ollama models are strictly
    restricted to 2D overlay and visual perception.
    """
    p = (provider_name or "").strip().lower()
    m = (model_name or "").strip().lower()

    # Reject any local or unverified providers immediately
    if any(tag in p or tag in m for tag in ("ollama", "lmstudio", "local", "gemma", "qwen", "llama", "phi", "mistral")):
        return False

    # Match gpt-6.1-sol-fast or approved fast GPT-6 patterns
    if "gpt-6.1-sol-fast" in m or ("gpt-6" in m and "fast" in m) or ("sol-fast" in m):
        return True

    # Dedicated fast OpenAI models if provider is explicitly OpenAI / ChatGPT
    if p in ("openai", "chatgpt") and ("6.1" in m or "sol-fast" in m):
        return True

    return False


def get_perception_contract(*, spatial_3d_allowed: bool) -> str:
    """Return the perception contract instruction depending on model capabilities."""
    if spatial_3d_allowed:
        return (
            "Responde en español sobre la imagen seleccionada. Si la explicación requiere comprensión "
            "espacial, mecánica o ensamblaje 3D de piezas, genera un plan declarativo JSON válido "
            "con modo 'interactive_3d' conforme al esquema SpatialPresentationPlan. Si es una explicación "
            "visual plana, diagramática o de interfaz, genera 'overlay_2d' o 'diagram_2d'. "
            "Devuelve el plan en un bloque ```json ... ``` junto a tu resumen explicativo."
        )
    return (
        "Responde en español sobre la imagen seleccionada. Tienes habilitada la capacidad de señalar elementos "
        "y generar diagramas 2D sobre la pantalla del usuario. Si la consulta pide señalar, marcar piezas, botones o zonas, "
        "o trazar un diagrama explicativo, devuelve un bloque ```json con modo 'overlay_2d' o 'diagram_2d', "
        "un 'summary' breve (máximo 25 palabras) para voz, y una lista 'annotations_2d' con cada elemento identificado: "
        "{'id': 'elem_1', 'type': 'box' | 'arrow' | 'spotlight' | 'callout', 'target_box_normalized': [ymin, xmin, ymax, xmax], 'label': 'nombre', 'color': '#hex'}. "
        "Usa coordenadas normalizadas de 0.0 a 1.0. No generes mallas 3D; enfócate en señalar y diagramar con precisión."
    )


def _is_finite_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def _sanitize_string(val: Any, max_len: int, default: str = "") -> str:
    if not isinstance(val, str):
        return default
    cleaned = SCRIPT_RE.sub('', val).strip()
    return cleaned[:max_len]


def _validate_color(val: Any, default: str = "#38bdf8") -> str:
    if isinstance(val, str) and HEX_COLOR_RE.match(val.strip()):
        return val.strip().lower()
    return default


def _validate_normalized_box(box: Any) -> list[float]:
    """Validate and clamp [ymin, xmin, ymax, xmax] between 0.0 and 1.0."""
    default_box = [0.0, 0.0, 1.0, 1.0]
    if not isinstance(box, list) or len(box) != 4:
        return default_box
    if not all(_is_finite_number(x) for x in box):
        return default_box
    ymin = max(0.0, min(1.0, float(box[0])))
    xmin = max(0.0, min(1.0, float(box[1])))
    ymax = max(ymin, min(1.0, float(box[2])))
    xmax = max(xmin, min(1.0, float(box[3])))
    return [round(ymin, 4), round(xmin, 4), round(ymax, 4), round(xmax, 4)]


def _validate_annotations_2d(raw_annotations: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_annotations, list):
        return []
    valid: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_annotations[:MAX_ANNOTATIONS]):
        if not isinstance(item, dict):
            continue
        ann_type = item.get('type')
        if ann_type not in ALLOWED_ANNOTATION_TYPES:
            ann_type = 'box'
        box = _validate_normalized_box(item.get('target_box_normalized') or item.get('box'))
        label = _sanitize_string(item.get('label'), MAX_LABEL_LEN, f"Elemento {idx + 1}")
        color = _validate_color(item.get('color'))
        detail = _sanitize_string(item.get('detail'), MAX_DETAIL_LEN)
        entry: dict[str, Any] = {
            'id': _sanitize_string(item.get('id'), 50, f"ann_{idx + 1}"),
            'type': ann_type,
            'target_box_normalized': box,
            'label': label,
            'color': color,
        }
        if detail:
            entry['detail'] = detail
        valid.append(entry)
    return valid


def _validate_scene_3d(raw_scene: Any) -> dict[str, Any] | None:
    if not isinstance(raw_scene, dict):
        return None
    raw_primitives = raw_scene.get('root_primitives')
    if not isinstance(raw_primitives, list) or not raw_primitives:
        return None

    primitives: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_primitives[:MAX_PRIMITIVES]):
        if not isinstance(item, dict):
            continue
        prim_type = item.get('type')
        if prim_type not in ALLOWED_PRIMITIVES:
            continue

        # Validate 3D dimensions [w, h, d]
        dims = item.get('dimensions')
        if not (isinstance(dims, list) and len(dims) == 3 and all(_is_finite_number(x) and x > 0 for x in dims)):
            dims = [1.0, 1.0, 1.0]
        else:
            dims = [round(min(1000.0, float(x)), 4) for x in dims]

        # Validate position [x, y, z]
        pos = item.get('position')
        if not (isinstance(pos, list) and len(pos) == 3 and all(_is_finite_number(x) for x in pos)):
            pos = [0.0, 0.0, 0.0]
        else:
            pos = [round(max(-1000.0, min(1000.0, float(x))), 4) for x in pos]

        # Validate rotation [rx, ry, rz]
        rot = item.get('rotation')
        if not (isinstance(rot, list) and len(rot) == 3 and all(_is_finite_number(x) for x in rot)):
            rot = [0.0, 0.0, 0.0]
        else:
            rot = [round(float(x), 4) for x in rot]

        # Validate exploded_offset [dx, dy, dz]
        offset = item.get('exploded_offset')
        if not (isinstance(offset, list) and len(offset) == 3 and all(_is_finite_number(x) for x in offset)):
            offset = [0.0, 0.0, 0.0]
        else:
            offset = [round(max(-1000.0, min(1000.0, float(x))), 4) for x in offset]

        color = _validate_color(item.get('color'), "#38bdf8")
        prim_id = _sanitize_string(item.get('id'), 50, f"mesh_{idx + 1}")

        primitives.append({
            'id': prim_id,
            'type': prim_type,
            'dimensions': dims,
            'position': pos,
            'rotation': rot,
            'color': color,
            'exploded_offset': offset
        })

    if not primitives:
        return None

    return {'root_primitives': primitives}


def validate_spatial_plan(
    data: Any,
    *,
    spatial_3d_allowed: bool,
    provider_name: str | None = None,
    model_name: str | None = None
) -> dict[str, Any]:
    """Strictly validate and sanitize a SpatialPresentationPlan dictionary.

    If spatial_3d_allowed is False and the data contains 3D elements, it gracefully
    downgrades the mode to 'overlay_2d' and discards scene_3d.
    """
    if not isinstance(data, dict):
        data = {}

    mode = data.get('mode')
    if mode not in ALLOWED_MODES:
        mode = 'overlay_2d'

    # Strict gating enforcement
    if mode == 'interactive_3d' and not spatial_3d_allowed:
        LOG.info("Explicación 3D solicitada pero el proveedor '%s'/'%s' no es gpt-6.1-sol-fast. Degradando a 2D.",
                 provider_name, model_name)
        mode = 'overlay_2d'

    summary = _sanitize_string(data.get('summary'), MAX_SUMMARY_LEN, "Explicación visual de la región seleccionada.")
    annotations_2d = _validate_annotations_2d(data.get('annotations_2d'))

    # If annotations are empty, add a default overlay annotation covering the region
    if not annotations_2d:
        annotations_2d = [{
            'id': 'ann_default',
            'type': 'box',
            'target_box_normalized': [0.0, 0.0, 1.0, 1.0],
            'label': summary[:80] if summary else "Zona analizada",
            'color': '#38bdf8'
        }]

    scene_3d = None
    if mode == 'interactive_3d' and spatial_3d_allowed:
        scene_3d = _validate_scene_3d(data.get('scene_3d'))
        if not scene_3d:
            # If 3D scene data was empty or invalid, fallback to 2D
            mode = 'overlay_2d'

    return {
        'mode': mode,
        'summary': summary,
        'annotations_2d': annotations_2d,
        'scene_3d': scene_3d,
        'provider_gating': {
            'spatial_3d_allowed': bool(spatial_3d_allowed),
            'active_model': model_name or '',
            'provider_name': provider_name or '',
            'gating_status': 'active' if spatial_3d_allowed else '2d_only'
        }
    }


def extract_or_build_spatial_plan(
    text: str,
    *,
    selection: dict[str, Any] | None = None,
    spatial_3d_allowed: bool = False,
    provider_name: str | None = None,
    model_name: str | None = None
) -> dict[str, Any]:
    """Parse structured JSON from model text or construct a default 2D plan from plain text."""
    if not isinstance(text, str):
        text = ""

    parsed_json: dict[str, Any] | None = None

    # Check for markdown code fence with json
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence_match:
        try:
            candidate = json.loads(fence_match.group(1))
            if isinstance(candidate, dict):
                parsed_json = candidate
        except Exception:
            pass

    if parsed_json is None:
        # Check if text contains a raw JSON object
        raw_match = re.search(r'\{[\s\S]*"mode"[\s\S]*\}', text)
        if raw_match:
            try:
                candidate = json.loads(raw_match.group(0))
                if isinstance(candidate, dict):
                    parsed_json = candidate
            except Exception:
                pass

    if parsed_json is not None:
        return validate_spatial_plan(
            parsed_json,
            spatial_3d_allowed=spatial_3d_allowed,
            provider_name=provider_name,
            model_name=model_name
        )

    # Heuristic fallback for plain-text responses (standard in Ollama/Gemma/Qwen)
    summary_text = text.strip()
    if 'Resumen:' in summary_text:
        parts = summary_text.split('Detalle:', 1)
        summary_line = parts[0].replace('Resumen:', '').strip()
        summary_text = summary_line or summary_text

    # Take first sentence or up to 300 chars for avatar voice / summary bubble
    summary_clean = summary_text.split('\n')[0].strip()
    if len(summary_clean) > 300:
        summary_clean = summary_clean[:297] + '...'

    # Check if text contains lines with coordinates: [ymin, xmin, ymax, xmax] Label
    annotations_from_text: list[dict[str, Any]] = []
    palette = ['#38bdf8', '#22c55e', '#f59e0b', '#ec4899', '#8b5cf6']
    for line in text.splitlines():
        match = re.search(r'\[\s*([0-9]*\.?[0-9]+)\s*,\s*([0-9]*\.?[0-9]+)\s*,\s*([0-9]*\.?[0-9]+)\s*,\s*([0-9]*\.?[0-9]+)\s*\]', line)
        if not match:
            continue
        try:
            y0, x0, y1, x1 = (float(match.group(i)) for i in range(1, 5))
            box = [y0, x0, y1, x1]
            if max(box) > 1.0:
                scale = 1000.0 if max(box) > 100.0 else 100.0
                box = [b / scale for b in box]
            after = line[match.end():].strip(' -:–\t')
            before = line[:match.start()].strip(' -:–\t')
            label_text = after or before or f'Elemento {len(annotations_from_text) + 1}'

            full_line_lower = line.lower()
            ann_type = 'box'
            if any(w in full_line_lower for w in ('flecha', 'arrow', 'señal', 'apunta')):
                ann_type = 'arrow'
            elif any(w in full_line_lower for w in ('spotlight', 'botón', 'boton', 'luz', 'led')):
                ann_type = 'spotlight'
            elif any(w in full_line_lower for w in ('callout', 'globo', 'texto')):
                ann_type = 'callout'

            annotations_from_text.append({
                'id': f'ann_{len(annotations_from_text) + 1}',
                'type': ann_type,
                'target_box_normalized': box,
                'label': label_text[:80],
                'color': palette[len(annotations_from_text) % len(palette)]
            })
            if len(annotations_from_text) >= MAX_ANNOTATIONS:
                break
        except Exception:
            continue

    if annotations_from_text:
        annotations_list = annotations_from_text
        detected_mode = 'diagram_2d' if len(annotations_from_text) > 1 else 'overlay_2d'
    else:
        annotations_list = [{
            'id': 'ann_roi',
            'type': 'box',
            'target_box_normalized': [0.0, 0.0, 1.0, 1.0],
            'label': summary_clean[:60] if summary_clean else 'Selección analizada',
            'color': '#38bdf8',
            'detail': text[:500] if len(text) > len(summary_clean) else None
        }]
        detected_mode = 'overlay_2d'

    plan_data = {
        'mode': detected_mode,
        'summary': summary_clean or 'Análisis completado.',
        'annotations_2d': annotations_list,
        'scene_3d': None
    }

    return validate_spatial_plan(
        plan_data,
        spatial_3d_allowed=spatial_3d_allowed,
        provider_name=provider_name,
        model_name=model_name
    )

