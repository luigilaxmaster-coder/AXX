"""AgentProfile DTOs, JSON Schema validation, 24/9 Canonical AvatarFormAdapter, and Safe Import/Export (PR-11).

Enforces Invariants:
- I-04 / AGENT-02: Maps the 24 canonical AXX forms (0..23) and 9 palettes (0..8) with cached SVG/data
  thumbnails (128-256px) so resting agents never spawn full WebGL/WebGPU render loops.
- AGENT-01: Individual agent profiles are completely separate from the global AXX profile.
- AGENT-05 / E2E-15: Export/import strips all secrets, tokens, grant IDs, local paths, and conversation
  histories; imported profiles and routines always start disabled (enabled=False) with zero grants.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from typing import Any

CANONICAL_AXX_FORMS: tuple[str, ...] = (
    'Core',
    'Flow',
    'Pearl',
    'Torus',
    'Split',
    'Wave',
    'Bloom',
    'Fold',
    'Spike',
    'Drift',
    'Orbit',
    'Morph',
    'Cushion',
    'Trefoil',
    'Nova',
    'Heart',
    'Infinity',
    'Helix',
    'Knot',
    'Petal',
    'Prism',
    'Capsule',
    'Crescent',
    'Ripple',
)

CANONICAL_AXX_PALETTES: tuple[dict[str, str], ...] = (
    {'id': 0, 'name': 'Obsidian', 'primary': '#0d1117', 'accent': '#58a6ff', 'glow': '#1f6feb'},
    {'id': 1, 'name': 'Nebula', 'primary': '#1a1025', 'accent': '#c084fc', 'glow': '#9333ea'},
    {'id': 2, 'name': 'Ocean', 'primary': '#081c24', 'accent': '#38bdf8', 'glow': '#0284c7'},
    {'id': 3, 'name': 'Sunset', 'primary': '#231115', 'accent': '#fb7185', 'glow': '#e11d48'},
    {'id': 4, 'name': 'Amethyst', 'primary': '#191326', 'accent': '#a78bfa', 'glow': '#7c3aed'},
    {'id': 5, 'name': 'Emerald', 'primary': '#071f18', 'accent': '#34d399', 'glow': '#059669'},
    {'id': 6, 'name': 'Champagne', 'primary': '#211d16', 'accent': '#fbbf24', 'glow': '#d97706'},
    {'id': 7, 'name': 'Silver', 'primary': '#18181b', 'accent': '#e4e4e7', 'glow': '#a1a1aa'},
    {'id': 8, 'name': 'Void', 'primary': '#050507', 'accent': '#818cf8', 'glow': '#4f46e5'},
)

CATALOG_VERSION = 'axx-avatar-24x9-v1'

ALLOWED_MATERIAL_PRESETS = frozenset({
    'obsidian',
    'optical_glass',
    'iridescent_pearl',
    'brushed_titanium',
    ' velvet_matte'.strip(),
    'bioluminescent_gel',
})

ALLOWED_RUNTIMES = frozenset({
    'none',
    'api',
    'browser',
    'window_background',
    'host_foreground',
    'isolated_vm',
    'remote',
})

ALLOWED_FOREGROUND_POLICIES = frozenset({
    'ask',
    'queue',
    'isolated_only',
    'deny',
})

ALLOWED_MEMORY_SCOPES = frozenset({
    'conversation',
    'agent',
    'project',
    'explicit_shared',
})

ALLOWED_FALLBACKS = frozenset({
    'none',
    'ask',
    'authorized_profiles',
})

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SECRET_LEAK_RE = re.compile(
    r'(?:\bsk-[A-Za-z0-9]{16,}\b|\bghp_[A-Za-z0-9]{20,}\b|\bAIza[0-9A-Za-z_-]{20,}\b|\bBearer\s+[A-Za-z0-9._-]{16,}\b)',
    re.IGNORECASE,
)


class AgentProfileValidationError(ValueError):
    """Raised when an AgentProfile violates schema, appearance, or secret-hygiene rules."""


class AvatarFormAdapter:
    """Adapter for the 24 canonical AXX forms and 9 palettes with cached 128-256px SVG thumbnails (AGENT-02)."""

    def __init__(self):
        self._thumb_cache: dict[str, dict[str, Any]] = {}

    def catalog(self) -> dict[str, Any]:
        return {
            'catalog_version': CATALOG_VERSION,
            'form_count': len(CANONICAL_AXX_FORMS),
            'palette_count': len(CANONICAL_AXX_PALETTES),
            'forms': [
                {'form_id': idx, 'name': name}
                for idx, name in enumerate(CANONICAL_AXX_FORMS)
            ],
            'palettes': list(CANONICAL_AXX_PALETTES),
            'materials': sorted(ALLOWED_MATERIAL_PRESETS),
        }

    def get_thumbnail(
        self,
        form_id: int,
        palette_id: int,
        *,
        material_preset: str = 'obsidian',
        size_px: int = 128,
        reduce_motion: bool = False,
    ) -> dict[str, Any]:
        if type(form_id) is not int or not (0 <= form_id <= 23):
            raise AgentProfileValidationError(f'form_id must be in 0..23, got {form_id!r}')
        if type(palette_id) is not int or not (0 <= palette_id <= 8):
            raise AgentProfileValidationError(f'palette_id must be in 0..8, got {palette_id!r}')
        if type(size_px) is not int or not (64 <= size_px <= 256):
            raise AgentProfileValidationError('Thumbnail size_px must be between 64 and 256')
        mat = str(material_preset or 'obsidian')
        if mat not in ALLOWED_MATERIAL_PRESETS:
            raise AgentProfileValidationError(f'Unsupported material_preset: {mat!r}')

        cache_key = f'{CATALOG_VERSION}:{form_id}:{palette_id}:{mat}:{size_px}:{int(bool(reduce_motion))}'
        if cache_key in self._thumb_cache:
            return copy.deepcopy(self._thumb_cache[cache_key])

        form_name = CANONICAL_AXX_FORMS[form_id]
        palette = CANONICAL_AXX_PALETTES[palette_id]
        cx = size_px // 2
        cy = size_px // 2
        r_outer = int(size_px * 0.36)
        r_inner = int(size_px * 0.18) + (form_id % 7)

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size_px} {size_px}" width="{size_px}" height="{size_px}" '
            f'data-form-id="{form_id}" data-form-name="{html.escape(form_name)}" data-palette-id="{palette_id}" '
            f'data-material="{html.escape(mat)}" data-reduce-motion="{str(bool(reduce_motion)).lower()}">'
            f'<rect width="{size_px}" height="{size_px}" rx="{size_px // 5}" fill="{palette["primary"]}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{palette["glow"]}" fill-opacity="0.28" stroke="{palette["accent"]}" stroke-width="2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="{palette["accent"]}" fill-opacity="0.85"/>'
            f'<text x="{cx}" y="{size_px - 10}" fill="{palette["accent"]}" font-family="Segoe UI, sans-serif" '
            f'font-size="11" text-anchor="middle">{html.escape(form_name)}</text>'
            '</svg>'
        )
        entry = {
            'cache_key': cache_key,
            'catalog_version': CATALOG_VERSION,
            'form_id': form_id,
            'form_name': form_name,
            'palette_id': palette_id,
            'palette_name': palette['name'],
            'material_preset': mat,
            'size_px': size_px,
            'reduce_motion': bool(reduce_motion),
            'webgl_loop_active': False,
            'svg': svg,
            'sha256': hashlib.sha256(svg.encode('utf-8')).hexdigest(),
        }
        self._thumb_cache[cache_key] = entry
        return copy.deepcopy(entry)

    def invalidate_cache(
        self,
        *,
        form_id: int | None = None,
        palette_id: int | None = None,
    ) -> int:
        if form_id is None and palette_id is None:
            count = len(self._thumb_cache)
            self._thumb_cache.clear()
            return count
        removed = 0
        for key in list(self._thumb_cache):
            item = self._thumb_cache[key]
            if (form_id is None or item['form_id'] == form_id) and (
                palette_id is None or item['palette_id'] == palette_id
            ):
                del self._thumb_cache[key]
                removed += 1
        return removed


def validate_agent_profile(profile: Any) -> dict[str, Any]:
    """Validate an AgentProfile v1 object against schemas/agent-profile.schema.json and security rules."""
    if not isinstance(profile, dict):
        raise AgentProfileValidationError('AgentProfile must be a JSON object')

    raw_dump = json.dumps(profile, ensure_ascii=False)
    if SECRET_LEAK_RE.search(raw_dump):
        raise AgentProfileValidationError('Raw API key, bearer token, or secret detected in AgentProfile (SEC-01 / AGENT-05)')

    required_fields = {
        'schema_version',
        'agent_id',
        'revision',
        'name',
        'role',
        'instructions',
        'enabled',
        'appearance',
        'intelligence',
        'workspace',
        'permissions',
        'limits',
        'memory_scope',
    }
    missing = required_fields - set(profile)
    if missing:
        raise AgentProfileValidationError(f'Missing required AgentProfile fields: {sorted(missing)}')

    allowed_fields = required_fields | {'description', 'voice', 'collaboration', 'autonomy'}
    extra = set(profile) - allowed_fields
    if extra:
        raise AgentProfileValidationError(f'Unexpected AgentProfile fields: {sorted(extra)}')

    if profile.get('schema_version') != '1.0':
        raise AgentProfileValidationError("schema_version must be '1.0'")

    agent_id = profile.get('agent_id')
    if not isinstance(agent_id, str) or not ID_RE.fullmatch(agent_id):
        raise AgentProfileValidationError(f'Invalid agent_id: {agent_id!r}')

    revision = profile.get('revision')
    if type(revision) is not int or revision < 1:
        raise AgentProfileValidationError('revision must be an integer >= 1')

    name = profile.get('name')
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 80):
        raise AgentProfileValidationError('name must be 1..80 characters')

    role = profile.get('role')
    if not isinstance(role, str) or not (1 <= len(role.strip()) <= 240):
        raise AgentProfileValidationError('role must be 1..240 characters')

    description = str(profile.get('description', ''))
    if len(description) > 2000:
        raise AgentProfileValidationError('description exceeds 2000 characters')

    instructions = profile.get('instructions')
    if not isinstance(instructions, str) or len(instructions) > 16000:
        raise AgentProfileValidationError('instructions must be a string up to 16000 characters')

    enabled = profile.get('enabled')
    if type(enabled) is not bool:
        raise AgentProfileValidationError('enabled must be a boolean')

    # Appearance validation (24 forms, 9 palettes)
    app = profile.get('appearance')
    if not isinstance(app, dict):
        raise AgentProfileValidationError('appearance must be an object')
    form_id = app.get('form_id')
    palette_id = app.get('palette_id')
    if type(form_id) is not int or not (0 <= form_id <= 23):
        raise AgentProfileValidationError(f'appearance.form_id must be 0..23, got {form_id!r}')
    if type(palette_id) is not int or not (0 <= palette_id <= 8):
        raise AgentProfileValidationError(f'appearance.palette_id must be 0..8, got {palette_id!r}')
    cat_ver = str(app.get('catalog_version') or CATALOG_VERSION)[:80]
    mat_preset = str(app.get('material_preset') or 'obsidian')[:120]
    if mat_preset not in ALLOWED_MATERIAL_PRESETS:
        raise AgentProfileValidationError(f'Invalid appearance.material_preset: {mat_preset!r}')
    scale = float(app.get('scale', 1.0))
    if not (0.1 <= scale <= 2.0):
        raise AgentProfileValidationError('appearance.scale must be between 0.1 and 2.0')
    clean_appearance = {
        'form_id': form_id,
        'form_name': CANONICAL_AXX_FORMS[form_id],
        'palette_id': palette_id,
        'palette_name': CANONICAL_AXX_PALETTES[palette_id]['name'],
        'catalog_version': cat_ver,
        'material_preset': mat_preset,
        'animation_profile': str(app.get('animation_profile', 'calm_idle'))[:120],
        'scale': round(scale, 3),
        'reduce_motion': bool(app.get('reduce_motion', False)),
    }

    # Intelligence validation
    intel = profile.get('intelligence')
    if not isinstance(intel, dict):
        raise AgentProfileValidationError('intelligence must be an object')
    if any(k in intel for k in ('api_key', 'secret', 'token', 'password')):
        raise AgentProfileValidationError('Credentials cannot be stored inside AgentProfile.intelligence')
    route = intel.get('route')
    if route not in ('manual', 'policy'):
        raise AgentProfileValidationError("intelligence.route must be 'manual' or 'policy'")
    fallback = intel.get('fallback')
    if fallback not in ALLOWED_FALLBACKS:
        raise AgentProfileValidationError(f'Invalid intelligence.fallback: {fallback!r}')
    max_turns = intel.get('max_parallel_turns', 1)
    if type(max_turns) is not int or not (1 <= max_turns <= 8):
        raise AgentProfileValidationError('intelligence.max_parallel_turns must be 1..8')
    clean_intel: dict[str, Any] = {
        'route': route,
        'fallback': fallback,
        'max_parallel_turns': max_turns,
    }
    if intel.get('provider_profile_ref'):
        ref = str(intel['provider_profile_ref'])
        if not ID_RE.fullmatch(ref):
            raise AgentProfileValidationError('Invalid intelligence.provider_profile_ref')
        clean_intel['provider_profile_ref'] = ref
    if 'model_id' in intel:
        clean_intel['model_id'] = str(intel.get('model_id', ''))[:180]
    if 'max_tokens_per_turn' in intel:
        mtok = int(intel['max_tokens_per_turn'])
        if not (128 <= mtok <= 1_000_000):
            raise AgentProfileValidationError('max_tokens_per_turn must be between 128 and 1000000')
        clean_intel['max_tokens_per_turn'] = mtok

    # Voice validation (connected to AXX's real voice engine & preserving microphone preferences)
    voice = profile.get('voice') or {}
    if not isinstance(voice, dict):
        raise AgentProfileValidationError('voice must be an object')
    speed = float(voice.get('speed', 1.0))
    if not (0.5 <= speed <= 2.0):
        raise AgentProfileValidationError('voice.speed must be between 0.5 and 2.0')
    clean_voice: dict[str, Any] = {
        'language': str(voice.get('language', 'es-DO'))[:48],
        'auto_speak': bool(voice.get('auto_speak', False)),
        'speed': round(speed, 2),
        'preserve_user_microphone': True,
    }
    if voice.get('tts_profile_id'):
        tref = str(voice['tts_profile_id'])
        if not ID_RE.fullmatch(tref):
            raise AgentProfileValidationError('Invalid voice.tts_profile_id')
        clean_voice['tts_profile_id'] = tref

    # Workspace validation
    ws = profile.get('workspace')
    if not isinstance(ws, dict):
        raise AgentProfileValidationError('workspace must be an object')
    runtime = ws.get('runtime')
    if runtime not in ALLOWED_RUNTIMES:
        raise AgentProfileValidationError(f'Invalid workspace.runtime: {runtime!r}')
    fg_policy = ws.get('foreground_policy')
    if fg_policy not in ALLOWED_FOREGROUND_POLICIES:
        raise AgentProfileValidationError(f'Invalid workspace.foreground_policy: {fg_policy!r}')
    allowed_roots = ws.get('allowed_roots') or []
    if not isinstance(allowed_roots, list) or len(allowed_roots) > 50:
        raise AgentProfileValidationError('workspace.allowed_roots must be a list of at most 50 entries')
    clean_ws: dict[str, Any] = {
        'runtime': runtime,
        'foreground_policy': fg_policy,
        'allowed_roots': [str(r)[:400] for r in allowed_roots],
    }
    if ws.get('project_ref'):
        pref = str(ws['project_ref'])
        if not ID_RE.fullmatch(pref):
            raise AgentProfileValidationError('Invalid workspace.project_ref')
        clean_ws['project_ref'] = pref

    # Permissions validation (role text never elevates permissions)
    perms = profile.get('permissions')
    if not isinstance(perms, dict):
        raise AgentProfileValidationError('permissions must be an object')
    grant_refs = perms.get('tool_grant_refs')
    if not isinstance(grant_refs, list) or len(grant_refs) > 128:
        raise AgentProfileValidationError('permissions.tool_grant_refs must be a list of at most 128 items')
    clean_grants = []
    for g in grant_refs:
        if not isinstance(g, str) or not ID_RE.fullmatch(g):
            raise AgentProfileValidationError(f'Invalid tool_grant_ref: {g!r}')
        if g not in clean_grants:
            clean_grants.append(g)
    delegation_enabled = perms.get('delegation_enabled')
    if type(delegation_enabled) is not bool:
        raise AgentProfileValidationError('permissions.delegation_enabled must be a boolean')
    max_depth = int(perms.get('max_delegate_depth', 0))
    if not (0 <= max_depth <= 8):
        raise AgentProfileValidationError('permissions.max_delegate_depth must be 0..8')
    clean_perms = {
        'tool_grant_refs': clean_grants,
        'delegation_enabled': delegation_enabled,
        'max_delegate_depth': max_depth if delegation_enabled else 0,
    }

    # Limits validation
    limits = profile.get('limits')
    if not isinstance(limits, dict):
        raise AgentProfileValidationError('limits must be an object')
    mc_jobs = limits.get('max_concurrent_jobs')
    m_retries = limits.get('max_retries')
    if type(mc_jobs) is not int or not (1 <= mc_jobs <= 16):
        raise AgentProfileValidationError('limits.max_concurrent_jobs must be 1..16')
    if type(m_retries) is not int or not (0 <= m_retries <= 8):
        raise AgentProfileValidationError('limits.max_retries must be 0..8')
    max_cost = float(limits.get('max_cost_usd', 0.0))
    if max_cost < 0:
        raise AgentProfileValidationError('limits.max_cost_usd must be >= 0')
    clean_limits: dict[str, Any] = {
        'max_concurrent_jobs': mc_jobs,
        'max_retries': m_retries,
        'max_cost_usd': round(max_cost, 4),
    }
    if 'max_ram_mb' in limits:
        ram = int(limits['max_ram_mb'])
        if ram < 128:
            raise AgentProfileValidationError('limits.max_ram_mb must be >= 128')
        clean_limits['max_ram_mb'] = ram

    mem_scope = profile.get('memory_scope')
    if mem_scope not in ALLOWED_MEMORY_SCOPES:
        raise AgentProfileValidationError(f'Invalid memory_scope: {mem_scope!r}')

    return {
        'schema_version': '1.0',
        'agent_id': agent_id,
        'revision': revision,
        'name': name.strip(),
        'role': role.strip(),
        'description': description,
        'instructions': instructions,
        'enabled': enabled,
        'appearance': clean_appearance,
        'intelligence': clean_intel,
        'voice': clean_voice,
        'workspace': clean_ws,
        'permissions': clean_perms,
        'limits': clean_limits,
        'memory_scope': mem_scope,
    }


def export_agent_package(
    profile: dict[str, Any],
    *,
    skills: list[dict[str, Any]] | None = None,
    routines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Export a sanitized, shareable Agent/Team package stripping grants, local roots, secrets, and active routines (AGENT-05)."""
    cleaned_input = {
        k: v
        for k, v in (profile if isinstance(profile, dict) else {}).items()
        if k not in ('thumbnail', 'draining', 'created_at_ms', 'updated_at_ms', 'disabled_at_ms')
    }
    validated = validate_agent_profile(cleaned_input)
    sanitized_profile = copy.deepcopy(validated)
    # Strip local grants, local workspace paths, and disable by default
    sanitized_profile['enabled'] = False
    sanitized_profile['permissions']['tool_grant_refs'] = []
    sanitized_profile['workspace']['allowed_roots'] = []
    if sanitized_profile['workspace']['runtime'] in ('host_foreground', 'window_background'):
        sanitized_profile['workspace']['runtime'] = 'none'

    sanitized_routines = []
    for r in routines or []:
        if isinstance(r, dict):
            sanitized_routines.append({
                'routine_id': str(r.get('routine_id', 'routine-1'))[:120],
                'schedule': copy.deepcopy(r.get('schedule') or {}),
                'work_spec': copy.deepcopy(r.get('work_spec') or {}),
                'enabled': False,  # UR-011 / E2E-15: imported routines always start paused
            })

    sanitized_skills = []
    for s in skills or []:
        if isinstance(s, dict):
            sanitized_skills.append({
                'skill_id': str(s.get('skill_id', 'skill-1'))[:120],
                'title': str(s.get('title', ''))[:160],
                'license': str(s.get('license', 'MIT'))[:80],
                'sha256': str(s.get('sha256', '0' * 64))[:64],
                'executable_without_command_service': False,
            })

    return {
        'package_version': '1.0',
        'kind': 'axx_agent_package',
        'profile': sanitized_profile,
        'declarative_skills': sanitized_skills,
        'routines': sanitized_routines,
        'security_audit': {
            'contains_credentials': False,
            'contains_grants': False,
            'contains_personal_memory': False,
            'routines_paused': True,
        },
    }


def import_agent_package(package_data: dict[str, Any]) -> dict[str, Any]:
    """Validate an imported agent/team package and enforce disabled grants, paused routines, and zero privilege escalation (E2E-15)."""
    if not isinstance(package_data, dict) or package_data.get('kind') != 'axx_agent_package':
        raise AgentProfileValidationError('Invalid axx_agent_package payload')
    raw_dump = json.dumps(package_data, ensure_ascii=False)
    if SECRET_LEAK_RE.search(raw_dump):
        raise AgentProfileValidationError('Rejected imported package containing raw secret or token')

    raw_profile = copy.deepcopy(package_data.get('profile') or {})
    # Force security invariants on import regardless of what the JSON requested
    raw_profile['enabled'] = False
    raw_profile['revision'] = 1
    raw_profile.setdefault('permissions', {})['tool_grant_refs'] = []
    raw_profile.setdefault('workspace', {})['allowed_roots'] = []
    if raw_profile['workspace'].get('runtime') in ('host_foreground', 'window_background'):
        raw_profile['workspace']['runtime'] = 'none'

    validated_profile = validate_agent_profile(raw_profile)
    routines = []
    for r in package_data.get('routines') or []:
        if isinstance(r, dict):
            routines.append({
                'routine_id': str(r.get('routine_id', 'imported-routine'))[:120],
                'schedule': copy.deepcopy(r.get('schedule') or {}),
                'work_spec': copy.deepcopy(r.get('work_spec') or {}),
                'enabled': False,
            })

    return {
        'profile': validated_profile,
        'routines': routines,
        'import_report': {
            'effective_grants': [],
            'routines_created_paused': len(routines),
            'admin_role_privilege_escalation': False,
            'status': 'disabled_pending_user_review',
        },
    }
