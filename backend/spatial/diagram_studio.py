"""Diagram Studio semantic AST, selective diagram-design templates, Mermaid parser, QA, and SVG/PNG export (PR-04 / MP-04).

Enforces:
- Semantic model of nodes, ports, edges, groups, layers, and layout constraints.
- Safe declarative style templates inspired by diagram-design (never loading untrusted HTML/scripts).
- Import/export Mermaid and JSON AST with visible preservation of unsupported elements.
- Geometric QA (collision/overlap detection, bounds checking, label clipping check) and Security QA
  (blocking <script>, foreignObject, event handlers, and external URLs).
- Deterministic, clip-free SVG and PNG export.
"""
from __future__ import annotations

import copy
import html
import io
import math
import re
from typing import Any

from PIL import Image, ImageDraw

from backend.spatial.patches import apply_scene_patch
from backend.spatial.scene_document import SceneDocumentError, SceneDocumentStore, _check_id

DIAGRAM_STYLE_TEMPLATES: dict[str, dict[str, str]] = {
    'obsidian_spatial': {
        'background': '#0d1117',
        'node_fill': '#161b22',
        'node_stroke': '#58a6ff',
        'text_color': '#e6edf3',
        'edge_stroke': '#8b949e',
        'group_fill': '#11161d',
        'group_stroke': '#30363d',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'architecture_c4': {
        'background': '#f8fafc',
        'node_fill': '#1168bd',
        'node_stroke': '#0b4884',
        'text_color': '#ffffff',
        'edge_stroke': '#475569',
        'group_fill': '#e2e8f0',
        'group_stroke': '#64748b',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'flowchart_clean': {
        'background': '#ffffff',
        'node_fill': '#eff6ff',
        'node_stroke': '#2563eb',
        'text_color': '#1e293b',
        'edge_stroke': '#334155',
        'group_fill': '#f8fafc',
        'group_stroke': '#94a3b8',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'cad_block_schematic': {
        'background': '#0a192f',
        'node_fill': '#112240',
        'node_stroke': '#64ffda',
        'text_color': '#ccd6f6',
        'edge_stroke': '#64ffda',
        'group_fill': '#0d213f',
        'group_stroke': '#233554',
        'font_family': 'Consolas, monospace',
    },
    'circuit_blueprint': {
        'background': '#003366',
        'node_fill': '#004080',
        'node_stroke': '#ffffff',
        'text_color': '#ffffff',
        'edge_stroke': '#99ccff',
        'group_fill': '#002b55',
        'group_stroke': '#66b2ff',
        'font_family': 'Consolas, monospace',
    },
    'sequence_timeline': {
        'background': '#18181b',
        'node_fill': '#27272a',
        'node_stroke': '#a855f7',
        'text_color': '#f4f4f5',
        'edge_stroke': '#c084fc',
        'group_fill': '#202024',
        'group_stroke': '#52525b',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'mindmap_radial': {
        'background': '#0f172a',
        'node_fill': '#1e293b',
        'node_stroke': '#38bdf8',
        'text_color': '#f1f5f9',
        'edge_stroke': '#7dd3fc',
        'group_fill': '#131c31',
        'group_stroke': '#334155',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'state_machine': {
        'background': '#111827',
        'node_fill': '#1f2937',
        'node_stroke': '#10b981',
        'text_color': '#f9fafb',
        'edge_stroke': '#34d399',
        'group_fill': '#17202f',
        'group_stroke': '#374151',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'data_pipeline': {
        'background': '#090d16',
        'node_fill': '#161f30',
        'node_stroke': '#f59e0b',
        'text_color': '#f3f4f6',
        'edge_stroke': '#fbbf24',
        'group_fill': '#0f1623',
        'group_stroke': '#374151',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'network_topology': {
        'background': '#0c0a09',
        'node_fill': '#1c1917',
        'node_stroke': '#06b6d4',
        'text_color': '#fafaf9',
        'edge_stroke': '#22d3ee',
        'group_fill': '#141210',
        'group_stroke': '#44403c',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
    'er_schema': {
        'background': '#ffffff',
        'node_fill': '#fdf4ff',
        'node_stroke': '#c026d3',
        'text_color': '#3b0764',
        'edge_stroke': '#86198f',
        'group_fill': '#faf5ff',
        'group_stroke': '#d8b4fe',
        'font_family': 'Consolas, monospace',
    },
    'minimal_technical': {
        'background': '#fafafa',
        'node_fill': '#ffffff',
        'node_stroke': '#171717',
        'text_color': '#171717',
        'edge_stroke': '#404040',
        'group_fill': '#f5f5f5',
        'group_stroke': '#a3a3a3',
        'font_family': 'Segoe UI, Inter, sans-serif',
    },
}

UNSAFE_CONTENT_RE = re.compile(
    r'(?:<\s*script\b|<\s*foreignObject\b|\bjavascript\s*:|\bon[a-z]+\s*=|https?://)',
    re.IGNORECASE,
)


def _minimum_width_for_label(label: str, canvas_width: int = 1200) -> float:
    """Calculate minimum normalized width [0..1] so label never clips in SVG or PNG export."""
    chars = max(len(label.strip()), 4)
    needed_px = chars * 9.5 + 32.0
    return min(0.48, max(0.12, round(needed_px / float(canvas_width), 4)))


def normalize_diagram_ast(raw_diagram: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a semantic Diagram Studio AST."""
    if not isinstance(raw_diagram, dict):
        raise SceneDocumentError('diagram AST must be an object')
    style = str(raw_diagram.get('style_template', 'obsidian_spatial'))
    if style not in DIAGRAM_STYLE_TEMPLATES:
        raise SceneDocumentError(f'Unknown diagram style_template: {style!r}')

    raw_nodes = raw_diagram.get('nodes') or []
    if not isinstance(raw_nodes, list) or len(raw_nodes) > 256:
        raise SceneDocumentError('diagram.nodes must be a list of at most 256 nodes')

    nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for idx, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            raise SceneDocumentError('Each diagram node must be an object')
        nid = _check_id(n.get('id') or f'd{idx + 1}', 'diagram.node.id')
        if nid in seen_nodes:
            raise SceneDocumentError(f'Duplicate diagram node id: {nid}')
        seen_nodes.add(nid)
        label = str(n.get('label', nid)).strip()
        if not label or len(label) > 200:
            raise SceneDocumentError(f'Invalid label on diagram node {nid}')
        if UNSAFE_CONTENT_RE.search(label):
            raise SceneDocumentError(f'Unsafe active content or remote URL blocked in node {nid} label')

        min_w = _minimum_width_for_label(label)
        bounds = n.get('bounds')
        if isinstance(bounds, list) and len(bounds) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in bounds):
            x, y, w, h = [float(v) for v in bounds]
            w = max(w, min_w)
            h = max(h, 0.08)
            x = min(max(0.02, x), max(0.02, 0.98 - w))
            y = min(max(0.02, y), max(0.02, 0.98 - h))
        else:
            col = idx % 3
            row = idx // 3
            w = max(0.22, min_w)
            h = 0.11
            x = min(0.06 + col * 0.31, 0.98 - w)
            y = min(0.08 + row * 0.18, 0.98 - h)

        ports = n.get('ports')
        if not isinstance(ports, list) or not ports:
            ports = ['in', 'out', 'top', 'bottom']
        else:
            ports = [str(p)[:40] for p in ports[:16]]

        nodes.append({
            'id': nid,
            'label': label,
            'bounds': [round(x, 4), round(y, 4), round(w, 4), round(h, 4)],
            'ports': ports,
            'layer': str(n.get('layer', 'default'))[:60],
            'group_id': str(n['group_id'])[:80] if n.get('group_id') else None,
            'object_id': str(n['object_id'])[:80] if n.get('object_id') else None,
            'step_id': str(n['step_id'])[:80] if n.get('step_id') else None,
        })

    raw_edges = raw_diagram.get('edges') or []
    if not isinstance(raw_edges, list) or len(raw_edges) > 512:
        raise SceneDocumentError('diagram.edges must be a list of at most 512 edges')
    edges: list[dict[str, Any]] = []
    for idx, e in enumerate(raw_edges):
        if not isinstance(e, dict):
            raise SceneDocumentError('Each diagram edge must be an object')
        eid = _check_id(e.get('id') or f'e{idx + 1}', 'diagram.edge.id')
        src = _check_id(e.get('from'), 'diagram.edge.from')
        dst = _check_id(e.get('to'), 'diagram.edge.to')
        if src not in seen_nodes or dst not in seen_nodes:
            raise SceneDocumentError(f'Edge {eid} references unknown node ({src} -> {dst})')
        elabel = str(e.get('label', '')).strip()[:120]
        if UNSAFE_CONTENT_RE.search(elabel):
            raise SceneDocumentError(f'Unsafe content blocked in edge {eid} label')
        edges.append({
            'id': eid,
            'from': src,
            'to': dst,
            'from_port': str(e.get('from_port', 'out'))[:40],
            'to_port': str(e.get('to_port', 'in'))[:40],
            'label': elabel,
        })

    groups = []
    for idx, g in enumerate(raw_diagram.get('groups') or []):
        if isinstance(g, dict):
            gid = _check_id(g.get('id') or f'g{idx + 1}', 'diagram.group.id')
            glabel = str(g.get('label', gid)).strip()[:120]
            if UNSAFE_CONTENT_RE.search(glabel):
                raise SceneDocumentError(f'Unsafe content blocked in group {gid}')
            groups.append({'id': gid, 'label': glabel})

    layers = [str(l)[:60] for l in (raw_diagram.get('layers') or ['default'])[:16]]
    constraints = list(raw_diagram.get('constraints') or [])[:64]
    unsupported = [str(u)[:240] for u in (raw_diagram.get('unsupported_elements') or [])[:64]]

    return {
        'style_template': style,
        'nodes': nodes,
        'edges': edges,
        'groups': groups,
        'layers': layers,
        'constraints': constraints,
        'unsupported_elements': unsupported,
    }


def auto_layout_diagram(diagram: dict[str, Any], *, snap_grid: float = 0.02) -> dict[str, Any]:
    """Arrange diagram nodes without overlaps and with enough width so labels never clip."""
    ast = normalize_diagram_ast(diagram)
    nodes = copy.deepcopy(ast['nodes'])
    n_count = len(nodes)
    if n_count == 0:
        return ast
    cols = max(1, min(3, int(math.ceil(math.sqrt(n_count)))))
    row_y = 0.08
    col_x = 0.05
    row_max_h = 0.11

    for idx, node in enumerate(nodes):
        col = idx % cols
        if col == 0 and idx > 0:
            row_y = round(row_y + row_max_h + 0.07, 4)
            col_x = 0.05
        min_w = _minimum_width_for_label(node['label'])
        max_col_w = round((0.90 - (cols - 1) * 0.04) / cols, 4)
        w = min(max(0.22, min_w), max(0.22, max_col_w))
        h = 0.11
        if col_x + w > 0.96:
            row_y = round(row_y + row_max_h + 0.07, 4)
            col_x = 0.05
        snapped_x = round(round(col_x / snap_grid) * snap_grid, 4)
        snapped_y = round(round(row_y / snap_grid) * snap_grid, 4)
        node['bounds'] = [
            min(max(0.02, snapped_x), round(0.98 - w, 4)),
            min(max(0.02, snapped_y), round(0.98 - h, 4)),
            round(w, 4),
            round(h, 4),
        ]
        col_x = round(node['bounds'][0] + w + 0.04, 4)

    ast['nodes'] = nodes
    return ast


def parse_mermaid_to_diagram(mermaid_text: str, *, style_template: str = 'obsidian_spatial') -> dict[str, Any]:
    """Parse Mermaid flowchart/graph syntax into Diagram Studio AST, preserving unsupported lines visibly."""
    if not isinstance(mermaid_text, str) or not mermaid_text.strip():
        raise SceneDocumentError('Mermaid input must be a non-empty string')
    if UNSAFE_CONTENT_RE.search(mermaid_text):
        raise SceneDocumentError('Unsafe script or remote URL in Mermaid source')

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    unsupported: list[str] = []

    edge_re = re.compile(
        r'^\s*([A-Za-z0-9_.-]+)(?:\[\"?([^\]\"]+)\"?\])?\s*-->\s*(?:\|([^|]+)\|)?\s*([A-Za-z0-9_.-]+)(?:\[\"?([^\]\"]+)\"?\])?\s*$'
    )
    node_re = re.compile(r'^\s*([A-Za-z0-9_.-]+)\[\"?([^\]\"]+)\"?\]\s*$')

    for raw_line in mermaid_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('%%'):
            continue
        if re.match(r'^(?:flowchart|graph)\s+(?:TD|TB|LR|RL|BT)\b', line, re.I):
            continue
        m_edge = edge_re.match(line)
        if m_edge:
            src_id, src_label, edge_label, dst_id, dst_label = m_edge.groups()
            if src_id not in nodes_by_id:
                nodes_by_id[src_id] = {'id': src_id, 'label': (src_label or src_id).strip()}
            elif src_label:
                nodes_by_id[src_id]['label'] = src_label.strip()
            if dst_id not in nodes_by_id:
                nodes_by_id[dst_id] = {'id': dst_id, 'label': (dst_label or dst_id).strip()}
            elif dst_label:
                nodes_by_id[dst_id]['label'] = dst_label.strip()
            edges.append({
                'id': f'e{len(edges) + 1}',
                'from': src_id,
                'to': dst_id,
                'label': (edge_label or '').strip(),
            })
            continue
        m_node = node_re.match(line)
        if m_node:
            nid, nlabel = m_node.groups()
            nodes_by_id[nid] = {'id': nid, 'label': nlabel.strip()}
            continue
        unsupported.append(line)

    raw_ast = {
        'style_template': style_template,
        'nodes': list(nodes_by_id.values()),
        'edges': edges,
        'unsupported_elements': unsupported,
    }
    return auto_layout_diagram(raw_ast)


def export_diagram_to_mermaid(diagram: dict[str, Any]) -> str:
    ast = normalize_diagram_ast(diagram)
    lines = ['flowchart TD']
    for node in ast['nodes']:
        safe_label = node['label'].replace('"', "'")
        lines.append(f'    {node["id"]}["{safe_label}"]')
    for edge in ast['edges']:
        if edge.get('label'):
            safe_elabel = edge['label'].replace('|', '/')
            lines.append(f'    {edge["from"]} -->|{safe_elabel}| {edge["to"]}')
        else:
            lines.append(f'    {edge["from"]} --> {edge["to"]}')
    for unsup in ast.get('unsupported_elements') or []:
        lines.append(f'    %% UNSUPPORTED: {unsup}')
    return '\n'.join(lines)


def check_diagram_qa(diagram: dict[str, Any], *, canvas_width: int = 1200) -> dict[str, Any]:
    """Run geometric and security QA on a Diagram Studio AST (MP-04)."""
    ast = normalize_diagram_ast(diagram)
    nodes = ast['nodes']
    overlaps: list[tuple[str, str]] = []
    out_of_bounds: list[str] = []
    clipped_labels: list[str] = []

    for i, a in enumerate(nodes):
        ax, ay, aw, ah = a['bounds']
        if ax < 0.0 or ay < 0.0 or ax + aw > 1.001 or ay + ah > 1.001:
            out_of_bounds.append(a['id'])
        min_w = _minimum_width_for_label(a['label'], canvas_width=canvas_width)
        if aw + 1e-4 < min_w:
            clipped_labels.append(a['id'])
        for b in nodes[i + 1:]:
            bx, by, bw, bh = b['bounds']
            if ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by:
                overlaps.append((a['id'], b['id']))

    passed = not overlaps and not out_of_bounds and not clipped_labels
    return {
        'passed': passed,
        'node_count': len(nodes),
        'edge_count': len(ast['edges']),
        'overlaps': overlaps,
        'out_of_bounds': out_of_bounds,
        'clipped_labels': clipped_labels,
        'unsupported_elements': ast.get('unsupported_elements', []),
        'active_scripts_blocked': True,
    }


def export_diagram_svg(diagram: dict[str, Any], *, width: int = 1200, height: int = 800) -> str:
    """Export Diagram Studio AST to a sanitized, self-contained, clip-free SVG document (MP-04)."""
    ast = normalize_diagram_ast(diagram)
    theme = DIAGRAM_STYLE_TEMPLATES[ast['style_template']]
    nodes_by_id = {n['id']: n for n in ast['nodes']}

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" data-style="{html.escape(ast["style_template"])}">',
        '<defs>',
        f'  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        f'    <path d="M 0 1 L 10 5 L 0 9 z" fill="{theme["edge_stroke"]}"/>',
        '  </marker>',
        '</defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{theme["background"]}"/>',
    ]

    # Render edges first
    for edge in ast['edges']:
        src = nodes_by_id[edge['from']]
        dst = nodes_by_id[edge['to']]
        sx = (src['bounds'][0] + src['bounds'][2] / 2.0) * width
        sy = (src['bounds'][1] + src['bounds'][3] / 2.0) * height
        dx = (dst['bounds'][0] + dst['bounds'][2] / 2.0) * width
        dy = (dst['bounds'][1] + dst['bounds'][3] / 2.0) * height
        parts.append(
            f'<line id="{html.escape(edge["id"])}" x1="{sx:.1f}" y1="{sy:.1f}" x2="{dx:.1f}" y2="{dy:.1f}" '
            f'stroke="{theme["edge_stroke"]}" stroke-width="2" marker-end="url(#arrow)"/>'
        )
        if edge.get('label'):
            mx = (sx + dx) / 2.0
            my = (sy + dy) / 2.0 - 8.0
            parts.append(
                f'<text x="{mx:.1f}" y="{my:.1f}" fill="{theme["text_color"]}" font-family="{html.escape(theme["font_family"])}" '
                f'font-size="13" text-anchor="middle">{html.escape(edge["label"])}</text>'
            )

    # Render nodes with guaranteed non-clipping box width
    for node in ast['nodes']:
        nx = node['bounds'][0] * width
        ny = node['bounds'][1] * height
        nw = max(node['bounds'][2] * width, len(node['label']) * 9.5 + 32.0)
        nh = max(node['bounds'][3] * height, 48.0)
        cx = nx + nw / 2.0
        cy = ny + nh / 2.0 + 5.0
        parts.append(
            f'<g id="{html.escape(node["id"])}" class="diagram-node" data-layer="{html.escape(node["layer"])}">'
            f'<rect x="{nx:.1f}" y="{ny:.1f}" width="{nw:.1f}" height="{nh:.1f}" rx="8" ry="8" '
            f'fill="{theme["node_fill"]}" stroke="{theme["node_stroke"]}" stroke-width="2"/>'
            f'<text x="{cx:.1f}" y="{cy:.1f}" fill="{theme["text_color"]}" font-family="{html.escape(theme["font_family"])}" '
            f'font-size="15" font-weight="600" text-anchor="middle">{html.escape(node["label"])}</text>'
            '</g>'
        )

    parts.append('</svg>')
    return '\n'.join(parts)


def export_diagram_png(diagram: dict[str, Any], *, width: int = 1200, height: int = 800) -> bytes:
    """Render Diagram Studio AST to PNG bytes using Pillow."""
    ast = normalize_diagram_ast(diagram)
    theme = DIAGRAM_STYLE_TEMPLATES[ast['style_template']]
    img = Image.new('RGBA', (width, height), theme['background'])
    draw = ImageDraw.Draw(img)
    nodes_by_id = {n['id']: n for n in ast['nodes']}

    for edge in ast['edges']:
        src = nodes_by_id[edge['from']]
        dst = nodes_by_id[edge['to']]
        sx = int((src['bounds'][0] + src['bounds'][2] / 2.0) * width)
        sy = int((src['bounds'][1] + src['bounds'][3] / 2.0) * height)
        dx = int((dst['bounds'][0] + dst['bounds'][2] / 2.0) * width)
        dy = int((dst['bounds'][1] + dst['bounds'][3] / 2.0) * height)
        draw.line([(sx, sy), (dx, dy)], fill=theme['edge_stroke'], width=2)

    for node in ast['nodes']:
        nx = int(node['bounds'][0] * width)
        ny = int(node['bounds'][1] * height)
        nw = int(max(node['bounds'][2] * width, len(node['label']) * 9.5 + 32.0))
        nh = int(max(node['bounds'][3] * height, 48.0))
        draw.rounded_rectangle(
            [nx, ny, nx + nw, ny + nh],
            radius=8,
            fill=theme['node_fill'],
            outline=theme['node_stroke'],
            width=2,
        )
        draw.text((nx + 16, ny + nh // 2 - 6), node['label'], fill=theme['text_color'])

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def update_scene_diagram_node(
    store: SceneDocumentStore,
    *,
    document_id: str,
    base_revision: int,
    operation_id: str,
    node_id: str,
    label: str | None = None,
    bounds: list[float] | None = None,
) -> dict[str, Any]:
    """Persist an interactive node edit (move/resize/relabel) into SceneDocument v2 via CAS ScenePatch."""
    doc = store.get_document(document_id)
    diagram = copy.deepcopy(doc.get('diagram') or {'nodes': [], 'edges': []})
    found = False
    for node in diagram.get('nodes', []):
        if node.get('id') == node_id:
            if label is not None:
                node['label'] = label
            if bounds is not None:
                node['bounds'] = bounds
            found = True
            break
    if not found:
        raise SceneDocumentError(f'Diagram node {node_id} not found in document {document_id}')
    normalized_diag = normalize_diagram_ast(diagram)
    patch = {
        'document_id': document_id,
        'base_revision': base_revision,
        'operation_id': operation_id,
        'target_object_ids': [],
        'allowed_paths': ['diagram.nodes', 'diagram.edges'],
        'changes': [{'op': 'diagram.update', 'diagram': normalized_diag}],
    }
    return apply_scene_patch(store, patch)
