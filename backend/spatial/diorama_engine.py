"""Diorama Render Mode, Codevember Material Presets, and Per-Entity Animation QA (PR-08 / MP-06 / MP-08).

Enforces Invariants:
- I-04 / MP-06: Codevember and Diorama material modes apply ONLY to Magic Pen scene content
  (target_surface='magic_pen_scene'). Any attempt to alter the AXX main avatar's approved
  materials, Obsidian palette, OrganicTendrils, or hitmask raises AvatarMaterialProtectedError.
- MP-08: Per-entity freeze-frame QA detects frozen animated actors, teleport jumps,
  offscreen entities, and missing attribution credits.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from backend.spatial.render_jobs import freeze_scene_at
from backend.spatial.scene_document import validate_scene_document_v2

DIORAMA_PRESETS: dict[str, dict[str, Any]] = {
    'toon_diorama': {
        'lighting': 'cel_directional',
        'outline_stroke_px': 2.0,
        'palette': ['#1e293b', '#38bdf8', '#f43f5e', '#fbbf24', '#f8fafc'],
        'postprocess': 'toon_quantized',
    },
    'pixel_maquette': {
        'lighting': 'isometric_crisp',
        'outline_stroke_px': 1.0,
        'palette': ['#0f172a', '#22d3ee', '#a855f7', '#34d399', '#e2e8f0'],
        'postprocess': 'pixel_grid_snap',
    },
    'studio_clay': {
        'lighting': 'soft_ambient_occlusion',
        'outline_stroke_px': 0.0,
        'palette': ['#d6d3d1', '#a8a29e', '#78716c', '#57534e', '#f5f5f4'],
        'postprocess': 'matte_clay',
    },
    'technical_blueprint_diorama': {
        'lighting': 'uniform_schematic',
        'outline_stroke_px': 1.5,
        'palette': ['#0a192f', '#64ffda', '#8892b0', '#ccd6f6', '#112240'],
        'postprocess': 'wire_overlay',
    },
}

CODEVEMBER_SCENE_MATERIALS: dict[str, dict[str, Any]] = {
    'raymarch_sdf_surface': {
        'shader_family': 'codevember_sdf',
        'roughness': 0.25,
        'metalness': 0.65,
        'isolated_from_avatar': True,
    },
    'metaball_fluid_coating': {
        'shader_family': 'codevember_metaball',
        'roughness': 0.12,
        'metalness': 0.10,
        'isolated_from_avatar': True,
    },
    'caustic_refraction': {
        'shader_family': 'codevember_caustics',
        'roughness': 0.05,
        'transmission': 0.88,
        'isolated_from_avatar': True,
    },
    'voxel_erosion_shell': {
        'shader_family': 'codevember_voxel',
        'roughness': 0.70,
        'metalness': 0.20,
        'isolated_from_avatar': True,
    },
    'membrane_translucent': {
        'shader_family': 'codevember_membrane',
        'roughness': 0.30,
        'transmission': 0.60,
        'isolated_from_avatar': True,
    },
}

PROTECTED_AVATAR_SURFACES = frozenset({
    'main_avatar',
    'avatar_body',
    'organic_tendrils',
    'avatar_hitmask',
    'obsidian_core',
})


class AvatarMaterialProtectedError(PermissionError):
    """Raised when a scene material or diorama preset attempts to modify the protected AXX avatar (MP-06 / I-04)."""


def apply_scene_material_or_diorama_mode(
    scene_doc: dict[str, Any],
    *,
    target_surface: str = 'magic_pen_scene',
    diorama_preset: str | None = None,
    codevember_material: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Apply or toggle off a Diorama/Codevember material mode strictly on a Magic Pen scene document (MP-06)."""
    if target_surface in PROTECTED_AVATAR_SURFACES or target_surface != 'magic_pen_scene':
        raise AvatarMaterialProtectedError(
            f"Protected surface '{target_surface}' cannot be modified by Magic Pen Diorama/Codevember presets (I-04 / MP-06)"
        )
    validated = validate_scene_document_v2(scene_doc)
    next_doc = copy.deepcopy(validated)
    meta = next_doc.setdefault('metadata', {})

    if not enabled:
        meta.pop('diorama_preset', None)
        meta.pop('codevember_material', None)
        if next_doc['mode'] in ('diorama', 'material'):
            next_doc['mode'] = 'conceptual'
        return validate_scene_document_v2(next_doc)

    if diorama_preset is not None:
        if diorama_preset not in DIORAMA_PRESETS:
            raise ValueError(f'Unknown diorama_preset: {diorama_preset!r}')
        meta['diorama_preset'] = {
            'id': diorama_preset,
            **DIORAMA_PRESETS[diorama_preset],
        }
        next_doc['mode'] = 'diorama'

    if codevember_material is not None:
        if codevember_material not in CODEVEMBER_SCENE_MATERIALS:
            raise ValueError(f'Unknown codevember_material: {codevember_material!r}')
        meta['codevember_material'] = {
            'id': codevember_material,
            **CODEVEMBER_SCENE_MATERIALS[codevember_material],
        }
        if diorama_preset is None:
            next_doc['mode'] = 'material'

    meta['avatar_state_untouched'] = True
    return validate_scene_document_v2(next_doc)


def _dist3(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def evaluate_diorama_qa(
    scene_doc: dict[str, Any],
    *,
    timestamps: list[float] | None = None,
    seed: int = 42,
    max_step_displacement: float = 8.0,
    frustum_bound: float = 25.0,
) -> dict[str, Any]:
    """Run per-entity freeze-frame QA detecting frozen actors, teleports, offscreen objects, and missing credits (MP-08)."""
    validated = validate_scene_document_v2(scene_doc)
    duration = float(validated['timeline'].get('duration_seconds', 1.0))
    if timestamps is None:
        if duration <= 0:
            timestamps = [0.0]
        else:
            steps = 5
            timestamps = [round(duration * i / (steps - 1), 4) for i in range(steps)]

    snapshots = [freeze_scene_at(validated, t, seed=seed) for t in timestamps]

    # Identify actors expected to move (targets of transform or simulation tracks)
    animated_actor_ids = {
        tr.get('target_object_id')
        for tr in (validated['timeline'].get('tracks') or [])
        if isinstance(tr, dict) and tr.get('kind') in ('transform', 'simulation') and tr.get('target_object_id')
    }

    history_by_id: dict[str, list[list[float]]] = {o['id']: [] for o in validated['objects']}
    for snap in snapshots:
        for obj in snap['objects']:
            history_by_id[obj['id']].append(obj['position'])

    frozen_actors: list[str] = []
    teleported_actors: list[str] = []
    offscreen_actors: list[str] = []

    for oid, positions in history_by_id.items():
        # Offscreen check across all sampled frames
        if any(any(abs(coord) > frustum_bound for coord in pos) for pos in positions):
            offscreen_actors.append(oid)

        if len(positions) >= 2:
            step_dists = [_dist3(positions[i], positions[i + 1]) for i in range(len(positions) - 1)]
            total_motion = sum(step_dists)
            max_jump = max(step_dists)
            if oid in animated_actor_ids and total_motion < 1e-4:
                frozen_actors.append(oid)
            if max_jump > max_step_displacement:
                teleported_actors.append(oid)

    missing_credits: list[str] = []
    for asset in validated.get('assets', []):
        lic = str(asset.get('license', ''))
        if lic.startswith('CC-BY') and not str(asset.get('credit_line', '')).strip():
            missing_credits.append(asset['asset_id'])

    passed = not (frozen_actors or teleported_actors or offscreen_actors or missing_credits)
    return {
        'passed': passed,
        'sampled_timestamps': timestamps,
        'frozen_actors': sorted(frozen_actors),
        'teleported_actors': sorted(teleported_actors),
        'offscreen_actors': sorted(offscreen_actors),
        'missing_credits': sorted(missing_credits),
    }
