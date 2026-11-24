"""Drawing and painting tutor: regions, construction lines and colour zones computed from the image itself.

The geometry never comes from a model: AXX quantizes the captured canvas, finds connected regions, and derives
construction axes, basic shapes, contour order and colour zones from them. A model may only phrase the narration
or choose among region ids. Nothing here edits the user's artwork.
"""
from __future__ import annotations

import colorsys
import math
from collections import deque
from typing import Any

from PIL import Image

MAX_SIDE = 192        # analysis resolution: enough for region shapes, cheap on Iris Xe class laptops
MIN_AREA = 0.004      # regions smaller than 0.4 % of the canvas are noise for a tutorial
MAX_REGIONS = 24
COLOR_NAMES = (('rojo', 0), ('naranja', 30), ('amarillo', 55), ('verde', 120), ('cian', 180), ('azul', 225), ('morado', 275), ('rosa', 320))
ALIASES = {'red': 'rojo', 'orange': 'naranja', 'yellow': 'amarillo', 'green': 'verde', 'cyan': 'cian', 'blue': 'azul', 'purple': 'morado',
           'violeta': 'morado', 'celeste': 'cian', 'pink': 'rosa', 'negro': 'negro', 'black': 'negro', 'blanco': 'blanco', 'white': 'blanco', 'gris': 'gris', 'gray': 'gris'}


def color_name(rgb) -> str:
    r, g, b = (c / 255 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l < .16:
        return 'negro'
    if l > .9 and s < .35:
        return 'blanco'
    if s < .18:
        return 'gris'
    hue = h * 360
    return min(COLOR_NAMES, key=lambda item: min(abs(hue - item[1]), 360 - abs(hue - item[1])))[0]


def _shape(fill: float, aspect: float) -> str:
    if fill > .9:
        return 'rectángulo'
    if .68 <= fill <= .86:
        return 'círculo' if .8 <= aspect <= 1.25 else 'óvalo'
    if .4 <= fill < .62:
        return 'triángulo'
    return 'forma libre'


def analyze(image: Image.Image, *, max_colors: int = 8) -> dict[str, Any]:
    """Segment the canvas into colour regions and return geometry in normalized [0..1] image coordinates."""
    im = image.convert('RGB')
    scale = MAX_SIDE / max(im.size)
    small = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.BILINEAR) if scale < 1 else im
    w, h = small.size
    q = small.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette()[:max_colors * 3]
    px = q.load()
    # background = the most frequent index on the border (paper/canvas)
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    background = max(set(border), key=border.count)
    seen = bytearray(w * h)
    regions = []
    for y0 in range(h):
        for x0 in range(w):
            i0 = y0 * w + x0
            if seen[i0] or px[x0, y0] == background:
                continue
            index, queue, pixels = px[x0, y0], deque([(x0, y0)]), []
            seen[i0] = 1
            while queue:
                x, y = queue.popleft()
                pixels.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and px[nx, ny] == index:
                        seen[ny * w + nx] = 1
                        queue.append((nx, ny))
            if len(pixels) < MIN_AREA * w * h:
                continue
            xs, ys = [p[0] for p in pixels], [p[1] for p in pixels]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
            inside = set(pixels)
            # contour: region pixels with a 4-neighbour outside, ordered by angle around the centroid (closed polyline)
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            edge = [(x, y) for x, y in pixels if any(n not in inside for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))]
            edge.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
            step = max(1, len(edge) // 48)
            rgb = tuple(palette[index * 3:index * 3 + 3])
            regions.append({'region_id': f'r{len(regions) + 1}', 'color': '#%02x%02x%02x' % rgb, 'color_name': color_name(rgb),
                            'area': round(len(pixels) / (w * h), 4), 'bbox': [round(x1 / w, 4), round(y1 / h, 4), round((x2 - x1) / w, 4), round((y2 - y1) / h, 4)],
                            'centroid': [round(cx / w, 4), round(cy / h, 4)], 'shape': _shape(len(pixels) / ((x2 - x1) * (y2 - y1)), (x2 - x1) / max(1, y2 - y1)),
                            'contour': [[round((x + .5) / w, 4), round((y + .5) / h, 4)] for x, y in edge[::step]]})
    regions.sort(key=lambda r: -r['area'])
    regions = regions[:MAX_REGIONS]
    for n, r in enumerate(regions, start=1):
        r['region_id'] = f'r{n}'
    return {'width': image.width, 'height': image.height, 'analysis_size': [w, h], 'background': '#%02x%02x%02x' % tuple(palette[background * 3:background * 3 + 3]),
            'regions': regions}


def find_color(analysis: dict, wanted: str) -> list[dict]:
    """Regions of a named colour; an empty list means «no está», never an invented position."""
    name = ALIASES.get(wanted.casefold(), wanted.casefold())
    return [r for r in analysis['regions'] if r['color_name'] == name]


def stages(analysis: dict) -> list[dict]:
    """Construction -> contours -> details -> colour -> shading, each with marks anchored to regions."""
    regions = analysis['regions']
    if not regions:
        return []
    x1 = min(r['bbox'][0] for r in regions); y1 = min(r['bbox'][1] for r in regions)
    x2 = max(r['bbox'][0] + r['bbox'][2] for r in regions); y2 = max(r['bbox'][1] + r['bbox'][3] for r in regions)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    big = [r for r in regions if r['area'] >= .02] or regions[:3]
    small = [r for r in regions if r not in big]
    out = [
        {'stage': 'construction', 'title': 'Construcción: encaje y ejes',
         'narration': f'Encaja la figura en una caja de {round((x2 - x1) * 100)} × {round((y2 - y1) * 100)} % del lienzo y traza sus ejes; después coloca las formas básicas de mayor a menor.',
         'marks': [{'kind': 'guide_line', 'points': [[cx, y1], [cx, y2]]}, {'kind': 'guide_line', 'points': [[x1, cy], [x2, cy]]},
                   {'kind': 'highlight_box', 'bbox': [x1, y1, x2 - x1, y2 - y1]}]
                  + [{'kind': 'outline', 'region_id': r['region_id'], 'label': f"{n}. {r['shape']}"} for n, r in enumerate(big, start=1)]},
        {'stage': 'contours', 'title': 'Contornos principales',
         'narration': 'Repasa los contornos en este orden, de la forma más grande a la más pequeña; las flechas indican el sentido del trazo.',
         'marks': [{'kind': 'path', 'region_id': r['region_id'], 'order': n} for n, r in enumerate(big, start=1)]},
    ]
    if small:
        out.append({'stage': 'details', 'title': 'Detalles', 'narration': 'Añade los detalles internos y relaciónalos con las formas grandes.',
                    'marks': [{'kind': 'outline', 'region_id': r['region_id'], 'label': f'detalle {n}'} for n, r in enumerate(small, start=1)]})
    colors: dict[str, list] = {}
    for r in regions:
        colors.setdefault(r['color_name'], []).append(r)
    out.append({'stage': 'color', 'title': 'Color por zonas',
                'narration': 'Colorea por zonas: ' + ', '.join(f"{name} ({len(rs)} zona{'s' if len(rs) > 1 else ''})" for name, rs in colors.items()) + '. Las máscaras dejan visibles los bordes.',
                'palette': [{'name': name, 'hex': rs[0]['color']} for name, rs in colors.items()],
                'marks': [{'kind': 'color_zone', 'region_id': r['region_id'], 'color': r['color'], 'order': n} for n, r in enumerate(regions, start=1)]})
    out.append({'stage': 'shading', 'title': 'Sombras (luz supuesta arriba a la izquierda)',
                'narration': 'La imagen no indica la luz; se supone arriba a la izquierda. Oscurece el lado inferior derecho de cada forma grande.',
                'assumed': True,
                'marks': [{'kind': 'motion_direction', 'points': [[x1, y1], [cx, cy]]}]
                         + [{'kind': 'region_mask', 'region_id': r['region_id'], 'side': 'bottom_right'} for r in big]})
    return out


def compare(before: dict, after: dict) -> dict:
    """Correction stage: only justified differences (region appeared, vanished, or moved/resized beyond tolerance)."""
    def key(r):
        return r['color_name']
    changes, used = [], set()
    for r in after['regions']:
        match = min((b for b in before['regions'] if key(b) == key(r) and b['region_id'] not in used),
                    key=lambda b: abs(b['centroid'][0] - r['centroid'][0]) + abs(b['centroid'][1] - r['centroid'][1]), default=None)
        if match is None:
            changes.append({'kind': 'added', 'region_id': r['region_id'], 'color_name': r['color_name']})
            continue
        used.add(match['region_id'])
        moved = abs(match['centroid'][0] - r['centroid'][0]) + abs(match['centroid'][1] - r['centroid'][1])
        grown = abs(match['area'] - r['area']) / max(match['area'], 1e-6)
        if moved > .04 or grown > .25:
            changes.append({'kind': 'changed', 'region_id': r['region_id'], 'from': match['region_id'], 'moved': round(moved, 3), 'area_change': round(grown, 2)})
    changes += [{'kind': 'removed', 'region_id': b['region_id'], 'color_name': b['color_name']} for b in before['regions'] if b['region_id'] not in used]
    return {'changed': bool(changes), 'changes': changes}
