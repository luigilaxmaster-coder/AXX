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
import math
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

# Acts (Evolution 3.1): optional, additive behaviour sections. Absent sections keep AgentProfile v1 output unchanged.
PERSONALITY_ENUMS: dict[str, tuple[str, ...]] = {
    'formality': ('casual', 'neutral', 'formal'),
    'concision': ('brief', 'balanced', 'detailed'),
    'creativity': ('low', 'medium', 'high'),
    'proactivity': ('low', 'medium', 'high'),
    'research_tendency': ('low', 'medium', 'high'),
    'technical_depth': ('low', 'medium', 'high'),
    'examples': ('none', 'some', 'many'),
    'explanation_level': ('expert', 'intermediate', 'beginner'),
    'review_style': ('lenient', 'balanced', 'strict'),
    'question_policy': ('ask_when_blocked', 'ask_first', 'avoid'),
    'response_format': ('prose', 'bullets', 'structured'),
}
PERSONALITY_TEXT_LIMITS = {'communication_style': 500, 'coding_preferences': 1000, 'quality_criteria': 1000}
AUTONOMY_MODES = ('manual', 'assisted', 'auto_safe', 'background', 'scheduled', 'isolated')
MENTION_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
LANG_RE = re.compile(r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$')

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SECRET_LEAK_RE = re.compile(
    r'(?:\bsk-[A-Za-z0-9]{16,}\b|\bghp_[A-Za-z0-9]{20,}\b|\bAIza[0-9A-Za-z_-]{20,}\b|\bBearer\s+[A-Za-z0-9._-]{16,}\b)',
    re.IGNORECASE,
)


class AgentProfileValidationError(ValueError):
    """Raised when an AgentProfile violates schema, appearance, or secret-hygiene rules."""


def _form_svg_geometry(form_id: int, cx: int, cy: int, s: int, accent: str, glow: str, mat: str) -> str:
    """Return distinct parametric SVG silhouette matching each of the 24 canonical AXX forms."""
    import math
    r = s * 0.27
    stroke_w = max(1.6, round(s * 0.018, 2))
    fill_op = {'optical_glass': '0.35', 'iridescent_pearl': '0.88', 'brushed_titanium': '0.78',
               'velvet_matte': '0.92', 'bioluminescent_gel': '0.68'}.get(mat, '0.82')
    gid = f'g{form_id}'
    if form_id == 0:  # Core: layered magnetic sphere
        return f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 1:  # Flow: sweeping fluid ribbons
        return f'<path d="M{cx-r:.1f} {cy} C{cx-r*0.5:.1f} {cy-r*1.1:.1f},{cx+r*0.5:.1f} {cy+r*1.1:.1f},{cx+r:.1f} {cy} C{cx+r*0.5:.1f} {cy-r*0.9:.1f},{cx-r*0.5:.1f} {cy+r*0.9:.1f},{cx-r:.1f} {cy}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 2:  # Pearl: specular nested pearl orb
        return f'<circle cx="{cx}" cy="{cy}" r="{r*0.95:.1f}" fill="url(#{gid})" fill-opacity="0.92" stroke="{accent}" stroke-width="{stroke_w}"/><ellipse cx="{cx-r*0.28:.1f}" cy="{cy-r*0.3:.1f}" rx="{r*0.28:.1f}" ry="{r*0.16:.1f}" fill="#ffffff" fill-opacity="0.45"/>'
    if form_id == 3:  # Torus: thick metallic ring
        return f'<circle cx="{cx}" cy="{cy}" r="{r*0.76:.1f}" fill="none" stroke="url(#{gid})" stroke-width="{r*0.42:.1f}"/><circle cx="{cx}" cy="{cy}" r="{r*0.97:.1f}" fill="none" stroke="{accent}" stroke-width="1.2" opacity="0.7"/>'
    if form_id == 4:  # Split: twin counter-balanced halves
        return f'<path d="M{cx-2} {cy-r:.1f} A{r:.1f} {r:.1f} 0 0 0 {cx-2} {cy+r:.1f}Z M{cx+2} {cy-r:.1f} A{r:.1f} {r:.1f} 0 0 1 {cx+2} {cy+r:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 5:  # Wave: harmonic dual crest
        return f'<path d="M{cx-r*1.15:.1f} {cy} Q{cx-r*0.55:.1f} {cy-r:.1f},{cx} {cy} T{cx+r*1.15:.1f} {cy} Q{cx+r*0.55:.1f} {cy+r*0.9:.1f},{cx} {cy} T{cx-r*1.15:.1f} {cy}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 6:  # Bloom: 6-petal radiant blossom
        petals = ''.join(
            f'<ellipse cx="{cx + math.cos(a)*r*0.46:.1f}" cy="{cy + math.sin(a)*r*0.46:.1f}" rx="{r*0.44:.1f}" ry="{r*0.24:.1f}" transform="rotate({math.degrees(a):.1f} {cx + math.cos(a)*r*0.46:.1f} {cy + math.sin(a)*r*0.46:.1f})" fill="url(#{gid})" fill-opacity="0.72" stroke="{accent}" stroke-width="1.1"/>'
            for a in (k * math.pi / 3 for k in range(6))
        )
        return petals + f'<circle cx="{cx}" cy="{cy}" r="{r*0.28:.1f}" fill="{accent}"/>'
    if form_id == 7:  # Fold: faceted origami fold
        return f'<polygon points="{cx},{cy-r*1.05:.1f} {cx+r:.1f},{cy-r*0.1:.1f} {cx+r*0.45:.1f},{cy+r:.1f} {cx-r*0.65:.1f},{cy+r*0.75:.1f} {cx-r:.1f},{cy-r*0.2:.1f}" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/><line x1="{cx}" y1="{cy-r*1.05:.1f}" x2="{cx}" y2="{cy+r*0.85:.1f}" stroke="{accent}" stroke-width="1.1" opacity="0.65"/>'
    if form_id == 8:  # Spike: 8-point crystalline star
        pts = ' '.join(
            f'{cx + math.cos(k*math.pi/8)*(r*1.12 if k%2==0 else r*0.46):.1f},{cy + math.sin(k*math.pi/8)*(r*1.12 if k%2==0 else r*0.46):.1f}'
            for k in range(16)
        )
        return f'<polygon points="{pts}" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 9:  # Drift: asymmetric droplet cloud
        return f'<path d="M{cx-r*0.9:.1f} {cy+r*0.25:.1f} C{cx-r*1.1:.1f} {cy-r*0.65:.1f},{cx+r*0.2:.1f} {cy-r*1.15:.1f},{cx+r*0.9:.1f} {cy-r*0.2:.1f} C{cx+r*1.2:.1f} {cy+r*0.7:.1f},{cx-r*0.2:.1f} {cy+r*1.1:.1f},{cx-r*0.9:.1f} {cy+r*0.25:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 10:  # Orbit: core + inclined orbital rings
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{r*1.15:.1f}" ry="{r*0.36:.1f}" transform="rotate(-24 {cx} {cy})" fill="none" stroke="{accent}" stroke-width="1.6"/><ellipse cx="{cx}" cy="{cy}" rx="{r*1.15:.1f}" ry="{r*0.36:.1f}" transform="rotate(24 {cx} {cy})" fill="none" stroke="{glow}" stroke-width="1.4"/><circle cx="{cx}" cy="{cy}" r="{r*0.48:.1f}" fill="url(#{gid})" stroke="{accent}" stroke-width="1.4"/>'
    if form_id == 11:  # Morph: fluid squircle lobe
        return f'<path d="M{cx} {cy-r:.1f} C{cx+r*0.85:.1f} {cy-r*0.95:.1f},{cx+r*1.1:.1f} {cy+r*0.25:.1f},{cx+r*0.55:.1f} {cy+r*0.85:.1f} C{cx-r*0.1:.1f} {cy+r*1.15:.1f},{cx-r*1.05:.1f} {cy+r*0.65:.1f},{cx-r*0.85:.1f} {cy-r*0.3:.1f} C{cx-r*0.7:.1f} {cy-r*0.85:.1f},{cx-r*0.35:.1f} {cy-r:.1f},{cx} {cy-r:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 12:  # Cushion: rounded tetrahedral pillow
        return f'<rect x="{cx-r*0.86:.1f}" y="{cy-r*0.86:.1f}" width="{r*1.72:.1f}" height="{r*1.72:.1f}" rx="{r*0.48:.1f}" transform="rotate(15 {cx} {cy})" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 13:  # Trefoil: three interlocked lobes
        return ''.join(
            f'<circle cx="{cx + math.cos(a)*r*0.42:.1f}" cy="{cy + math.sin(a)*r*0.42:.1f}" r="{r*0.48:.1f}" fill="url(#{gid})" fill-opacity="0.72" stroke="{accent}" stroke-width="1.3"/>'
            for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)
        )
    if form_id == 14:  # Nova: sunburst core
        rays = ''.join(
            f'<line x1="{cx + math.cos(k*math.pi/6)*r*0.5:.1f}" y1="{cy + math.sin(k*math.pi/6)*r*0.5:.1f}" x2="{cx + math.cos(k*math.pi/6)*r*1.12:.1f}" y2="{cy + math.sin(k*math.pi/6)*r*1.12:.1f}" stroke="{accent}" stroke-width="1.8" stroke-linecap="round"/>'
            for k in range(12)
        )
        return rays + f'<circle cx="{cx}" cy="{cy}" r="{r*0.55:.1f}" fill="url(#{gid})" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 15:  # Heart: sculpted geometric cardioid
        return f'<path d="M{cx} {cy+r*0.95:.1f} C{cx-r*1.2:.1f} {cy+r*0.2:.1f},{cx-r*1.05:.1f} {cy-r*0.95:.1f},{cx} {cy-r*0.35:.1f} C{cx+r*1.05:.1f} {cy-r*0.95:.1f},{cx+r*1.2:.1f} {cy+r*0.2:.1f},{cx} {cy+r*0.95:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 16:  # Infinity: continuous lemniscate ribbon
        return f'<path d="M{cx} {cy} C{cx-r*0.5:.1f} {cy-r*0.85:.1f},{cx-r*1.25:.1f} {cy-r*0.5:.1f},{cx-r*1.05:.1f} {cy} C{cx-r*1.25:.1f} {cy+r*0.5:.1f},{cx-r*0.5:.1f} {cy+r*0.85:.1f},{cx} {cy} C{cx+r*0.5:.1f} {cy-r*0.85:.1f},{cx+r*1.25:.1f} {cy-r*0.5:.1f},{cx+r*1.05:.1f} {cy} C{cx+r*1.25:.1f} {cy+r*0.5:.1f},{cx+r*0.5:.1f} {cy+r*0.85:.1f},{cx} {cy}Z" fill="none" stroke="url(#{gid})" stroke-width="{r*0.26:.1f}" stroke-linecap="round"/>'
    if form_id == 17:  # Helix: intertwined double strand
        return f'<path d="M{cx-r*0.55:.1f} {cy-r:.1f} C{cx+r*0.85:.1f} {cy-r*0.35:.1f},{cx-r*0.85:.1f} {cy+r*0.35:.1f},{cx+r*0.55:.1f} {cy+r:.1f}" fill="none" stroke="{accent}" stroke-width="{r*0.22:.1f}" stroke-linecap="round"/><path d="M{cx+r*0.55:.1f} {cy-r:.1f} C{cx-r*0.85:.1f} {cy-r*0.35:.1f},{cx+r*0.85:.1f} {cy+r*0.35:.1f},{cx-r*0.55:.1f} {cy+r:.1f}" fill="none" stroke="url(#{gid})" stroke-width="{r*0.22:.1f}" stroke-linecap="round"/>'
    if form_id == 18:  # Knot: torus-knot weave
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{r*0.95:.1f}" ry="{r*0.44:.1f}" transform="rotate(60 {cx} {cy})" fill="none" stroke="{glow}" stroke-width="{r*0.2:.1f}"/><ellipse cx="{cx}" cy="{cy}" rx="{r*0.95:.1f}" ry="{r*0.44:.1f}" transform="rotate(-60 {cx} {cy})" fill="none" stroke="{accent}" stroke-width="{r*0.2:.1f}"/><ellipse cx="{cx}" cy="{cy}" rx="{r*0.95:.1f}" ry="{r*0.44:.1f}" fill="none" stroke="url(#{gid})" stroke-width="{r*0.18:.1f}"/>'
    if form_id == 19:  # Petal: sculpted curved blade
        return f'<path d="M{cx} {cy-r*1.05:.1f} C{cx+r*0.95:.1f} {cy-r*0.45:.1f},{cx+r*0.8:.1f} {cy+r*0.7:.1f},{cx} {cy+r*1.05:.1f} C{cx-r*0.8:.1f} {cy+r*0.7:.1f},{cx-r*0.95:.1f} {cy-r*0.45:.1f},{cx} {cy-r*1.05:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 20:  # Prism: hexagonal diamond facet
        pts = ' '.join(f'{cx + math.cos(k*math.pi/3 - math.pi/6)*r:.1f},{cy + math.sin(k*math.pi/3 - math.pi/6)*r:.1f}' for k in range(6))
        return f'<polygon points="{pts}" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/><polygon points="{cx},{cy-r:.1f} {cx+r*0.86:.1f},{cy+r*0.5:.1f} {cx-r*0.86:.1f},{cy+r*0.5:.1f}" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="1"/>'
    if form_id == 21:  # Capsule: angled aerodynamic stadium pill
        return f'<rect x="{cx-r*0.52:.1f}" y="{cy-r:.1f}" width="{r*1.04:.1f}" height="{r*2:.1f}" rx="{r*0.52:.1f}" transform="rotate(28 {cx} {cy})" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    if form_id == 22:  # Crescent: razor lunar arc
        return f'<path d="M{cx+r*0.35:.1f} {cy-r*0.95:.1f} A{r:.1f} {r:.1f} 0 1 0 {cx+r*0.35:.1f} {cy+r*0.95:.1f} A{r*0.72:.1f} {r*0.82:.1f} 0 1 1 {cx+r*0.35:.1f} {cy-r*0.95:.1f}Z" fill="url(#{gid})" fill-opacity="{fill_op}" stroke="{accent}" stroke-width="{stroke_w}"/>'
    # form_id == 23: Ripple: concentric acoustic rings
    return f'<circle cx="{cx}" cy="{cy}" r="{r*1.02:.1f}" fill="none" stroke="{glow}" stroke-width="1.5" opacity="0.55"/><circle cx="{cx}" cy="{cy}" r="{r*0.72:.1f}" fill="none" stroke="{accent}" stroke-width="2" opacity="0.8"/><circle cx="{cx}" cy="{cy}" r="{r*0.38:.1f}" fill="url(#{gid})" stroke="{accent}" stroke-width="1.4"/>'


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
        cy = int(size_px * 0.45)
        r_outer = int(size_px * 0.38)
        gid = f'g{form_id}'
        shape_svg = _form_svg_geometry(form_id, cx, cy, size_px, palette['accent'], palette['glow'], mat)

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size_px} {size_px}" width="{size_px}" height="{size_px}" '
            f'data-form-id="{form_id}" data-form-name="{html.escape(form_name)}" data-palette-id="{palette_id}" '
            f'data-material="{html.escape(mat)}" data-reduce-motion="{str(bool(reduce_motion)).lower()}">'
            f'<defs><linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{palette["accent"]}"/><stop offset="100%" stop-color="{palette["glow"]}"/></linearGradient></defs>'
            f'<rect width="{size_px}" height="{size_px}" rx="{size_px // 5}" fill="{palette["primary"]}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{palette["glow"]}" fill-opacity="0.14"/>'
            f'{shape_svg}'
            f'<text x="{cx}" y="{size_px - 9}" fill="{palette["accent"]}" font-family="Segoe UI, sans-serif" '
            f'font-size="11" font-weight="600" text-anchor="middle">{html.escape(form_name)}</text>'
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

    allowed_fields = required_fields | {'description', 'voice', 'collaboration', 'autonomy', 'personality'}
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
    if 'animation_intensity' in app:
        ai = float(app['animation_intensity'])
        if not (0.0 <= ai <= 2.0):
            raise AgentProfileValidationError('appearance.animation_intensity must be 0.0..2.0')
        clean_appearance['animation_intensity'] = round(ai, 2)
    # Per-Act renderer studio (same ranges as AXX's SoftwareRenderer.setStudio); the global avatar never reads it.
    studio = app.get('studio')
    if studio is not None:
        if not isinstance(studio, dict):
            raise AgentProfileValidationError('appearance.studio must be an object')
        ranges = {'exposure': (0.35, 2.2), 'roughness': (0.015, 0.45), 'light_angle': (-180.0, 180.0), 'fluidity': (0.0, 2.3)}
        clean_studio = {}
        for key, (low, high) in ranges.items():
            if studio.get(key) is None:
                continue
            value = studio[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not (low <= value <= high):
                raise AgentProfileValidationError(f'appearance.studio.{key} must be {low}..{high}')
            clean_studio[key] = round(float(value), 3)
        if clean_studio:
            clean_appearance['studio'] = clean_studio
    if isinstance(app.get('reactions'), dict):
        clean_appearance['reactions'] = {
            str(k)[:40]: str(v)[:80]
            for k, v in app['reactions'].items()
            if k in ('idle', 'listening', 'thinking', 'working', 'approval', 'completed', 'error') and v is not None
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
        tref = str(voice['tts_profile_id']).strip()
        if not re.fullmatch(r'^[A-Za-z0-9_.: ()-]{1,160}$', tref):
            raise AgentProfileValidationError('Invalid voice.tts_profile_id')
        clean_voice['tts_profile_id'] = tref
    if 'intonation' in voice:
        inton = str(voice['intonation'])
        if inton not in ('calm', 'warm', 'focused', 'energetic', 'neutral'):
            raise AgentProfileValidationError('Invalid voice.intonation')
        clean_voice['intonation'] = inton
    if 'expressiveness' in voice:
        expr = str(voice['expressiveness'])
        if expr not in ('low', 'medium', 'high'):
            raise AgentProfileValidationError('Invalid voice.expressiveness')
        clean_voice['expressiveness'] = expr
    if 'listen_allowed' in voice:
        clean_voice['listen_allowed'] = bool(voice['listen_allowed'])
    if 'dictation_allowed' in voice:
        clean_voice['dictation_allowed'] = bool(voice['dictation_allowed'])

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
    if 'max_cpu_percent' in limits:
        cpu = float(limits['max_cpu_percent'])
        if not (5.0 <= cpu <= 100.0):
            raise AgentProfileValidationError('limits.max_cpu_percent must be 5..100')
        clean_limits['max_cpu_percent'] = round(cpu, 1)
    if 'max_task_seconds' in limits:
        secs = int(limits['max_task_seconds'])
        if not (5 <= secs <= 86400):
            raise AgentProfileValidationError('limits.max_task_seconds must be 5..86400')
        clean_limits['max_task_seconds'] = secs
    if 'daily_budget_usd' in limits:
        dbudget = float(limits['daily_budget_usd'])
        if dbudget < 0:
            raise AgentProfileValidationError('limits.daily_budget_usd must be >= 0')
        clean_limits['daily_budget_usd'] = round(dbudget, 4)
    if 'remote_execution_allowed' in limits:
        clean_limits['remote_execution_allowed'] = bool(limits['remote_execution_allowed'])
    if 'user_priority_override' in limits:
        clean_limits['user_priority_override'] = bool(limits['user_priority_override'])

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
        **validate_act_behavior(profile),
    }


def validate_act_behavior(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate the optional Acts sections. Personality shapes wording only; it never grants tools or permissions."""
    out: dict[str, Any] = {}
    if profile.get('personality') is not None:
        raw = profile['personality']
        if not isinstance(raw, dict):
            raise AgentProfileValidationError('personality must be an object')
        extra_keys = {'default_language', 'languages', 'initiative_level', 'result_format'}
        unknown = set(raw) - set(PERSONALITY_ENUMS) - set(PERSONALITY_TEXT_LIMITS) - extra_keys
        if unknown:
            raise AgentProfileValidationError(f'Unexpected personality fields: {sorted(unknown)}')
        clean: dict[str, Any] = {}
        for key, allowed in PERSONALITY_ENUMS.items():
            if key in raw:
                if raw[key] not in allowed:
                    raise AgentProfileValidationError(f'personality.{key} must be one of {list(allowed)}')
                clean[key] = raw[key]
        for key, limit in PERSONALITY_TEXT_LIMITS.items():
            if key in raw:
                if not isinstance(raw[key], str) or len(raw[key]) > limit:
                    raise AgentProfileValidationError(f'personality.{key} must be text up to {limit} characters')
                clean[key] = raw[key].strip()
        if 'default_language' in raw:
            if not isinstance(raw['default_language'], str) or not LANG_RE.fullmatch(raw['default_language']):
                raise AgentProfileValidationError('personality.default_language must be a language code')
            clean['default_language'] = raw['default_language']
        if 'languages' in raw:
            langs = raw['languages']
            if not isinstance(langs, list) or len(langs) > 12 or not all(isinstance(x, str) and LANG_RE.fullmatch(x) for x in langs):
                raise AgentProfileValidationError('personality.languages must be a list of language codes')
            clean['languages'] = list(dict.fromkeys(langs))
        if 'initiative_level' in raw:
            if raw['initiative_level'] not in ('low', 'medium', 'high'):
                raise AgentProfileValidationError('personality.initiative_level must be low, medium or high')
            clean['initiative_level'] = raw['initiative_level']
        if 'result_format' in raw:
            if raw['result_format'] not in ('summary', 'detailed', 'diff_and_evidence', 'checklist'):
                raise AgentProfileValidationError('personality.result_format invalid')
            clean['result_format'] = raw['result_format']
        out['personality'] = clean
    if profile.get('autonomy') is not None:
        raw = profile['autonomy']
        if not isinstance(raw, dict) or set(raw) - {'mode'} or raw.get('mode') not in AUTONOMY_MODES:
            raise AgentProfileValidationError(f'autonomy must be {{"mode": one of {list(AUTONOMY_MODES)}}}')
        out['autonomy'] = {'mode': raw['mode']}
    if profile.get('collaboration') is not None:
        raw = profile['collaboration']
        if not isinstance(raw, dict) or set(raw) - {'mention', 'accepts_handoffs', 'review_required', 'rules'}:
            raise AgentProfileValidationError('collaboration accepts mention, accepts_handoffs, review_required and rules')
        clean = {}
        if 'mention' in raw:
            if not isinstance(raw['mention'], str) or not MENTION_RE.fullmatch(raw['mention']):
                raise AgentProfileValidationError('collaboration.mention must be 1..32 letters, digits, _ or -')
            clean['mention'] = raw['mention']
        for key in ('accepts_handoffs', 'review_required'):
            if key in raw:
                if type(raw[key]) is not bool:
                    raise AgentProfileValidationError(f'collaboration.{key} must be a boolean')
                clean[key] = raw[key]
        if 'rules' in raw:
            if not isinstance(raw['rules'], str) or len(raw['rules']) > 1000:
                raise AgentProfileValidationError('collaboration.rules must be text up to 1000 characters')
            clean['rules'] = raw['rules'].strip()
        out['collaboration'] = clean
    return out


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
