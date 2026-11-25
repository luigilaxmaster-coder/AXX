"""Export actual renderer mesh buffers as glTF, retaining piece IDs and PBR factors.

This validates geometry bytes, not engineering dimensions or asset ownership.
Conceptual, unitless scenes remain explicitly conceptual in the artifact.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
from typing import Any

from backend.spatial.cad_contracts import validate_glb_bytes


def export_renderer_glb(scene: dict, parts: list[dict[str, Any]]) -> tuple[bytes, dict]:
    if not isinstance(parts, list) or not 1 <= len(parts) <= 256:
        raise ValueError('Export requires 1..256 renderer meshes')
    object_ids = {o['id'] for o in scene['objects']}
    buffer, views, accessors, meshes, nodes, materials = bytearray(), [], [], [], [], []
    triangles = 0
    units = scene['units']
    scale = {'mm': .001, 'cm': .01, 'm': 1., 'in': .0254, 'ft': .3048, 'unitless': 1.}.get(units)
    if scale is None:
        raise ValueError('Unsupported scene units for GLB export')

    def attribute(values, kind, target, *, integer=False):
        raw = struct.pack(f'<{len(values)}{"I" if integer else "f"}', *values)
        views.append({'buffer': 0, 'byteOffset': len(buffer), 'byteLength': len(raw), 'target': target})
        buffer.extend(raw)
        acc = {'bufferView': len(views) - 1, 'componentType': 5125 if integer else 5126,
               'count': len(values) if integer else len(values) // 3, 'type': kind}
        if kind == 'VEC3' and target == 34962:
            acc.update(min=[min(values[i::3]) for i in range(3)], max=[max(values[i::3]) for i in range(3)])
        accessors.append(acc)
        return len(accessors) - 1

    for part in parts:
        if not isinstance(part, dict) or part.get('object_id') not in object_ids:
            raise ValueError('Renderer mesh must reference an existing scene piece')
        pos_raw = base64.b64decode(part['positions_b64'], validate=True)
        idx_raw = base64.b64decode(part['indices_b64'], validate=True)
        if (not pos_raw or len(pos_raw) % 12 or len(pos_raw) > 6000000
                or not idx_raw or len(idx_raw) % 12 or len(idx_raw) > 3000000):
            raise ValueError('Malformed or oversized mesh buffers')
        vertices = [v * scale for v in struct.unpack(f'<{len(pos_raw)//4}f', pos_raw)]
        indices = list(struct.unpack(f'<{len(idx_raw)//4}I', idx_raw))
        if any(not math.isfinite(v) or abs(v) > 1e8 for v in vertices):
            raise ValueError('Non-finite or out-of-range mesh vertices')
        if max(indices) >= len(vertices) // 3:
            raise ValueError('Mesh indices exceed the position buffer')
        triangles += len(indices) // 3
        if triangles > 250000:
            raise ValueError('Export exceeds 250000 triangles')
        normals = [0.] * len(vertices)
        for n in range(0, len(indices), 3):
            a, b, c = [i * 3 for i in indices[n:n + 3]]
            u, v = [vertices[b+j] - vertices[a+j] for j in range(3)], [vertices[c+j] - vertices[a+j] for j in range(3)]
            normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            for i in (a, b, c):
                for j in range(3):
                    normals[i+j] += normal[j]
        for n in range(0, len(normals), 3):
            length = math.sqrt(sum(x*x for x in normals[n:n+3])) or 1.
            normals[n:n+3] = [x / length for x in normals[n:n+3]]
        material = part.get('material') or {}
        color = material.get('color', [1., 1., 1.])
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError('Invalid material color')
        values = [*color, material.get('opacity', 1.), material.get('roughness', .5), material.get('metalness', 0.)]
        if len(color) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in values):
            raise ValueError('Invalid PBR material factors')
        materials.append({'name': part['object_id'], 'doubleSided': True,
                          'alphaMode': 'BLEND' if values[3] < 1 else 'OPAQUE',
                          'pbrMetallicRoughness': {'baseColorFactor': values[:4],
                                                   'roughnessFactor': values[4], 'metallicFactor': values[5]}})
        attrs = {'POSITION': attribute(vertices, 'VEC3', 34962), 'NORMAL': attribute(normals, 'VEC3', 34962)}
        primitive = {'attributes': attrs, 'indices': attribute(indices, 'SCALAR', 34963, integer=True),
                     'material': len(materials) - 1}
        meshes.append({'name': part['object_id'], 'primitives': [primitive]})
        nodes.append({'name': part['object_id'], 'mesh': len(meshes) - 1,
                      'extras': {'object_id': part['object_id'], 'scene_revision': scene['revision']}})
    gltf = {'asset': {'version': '2.0', 'generator': 'AXX Magic Pen renderer mesh export'}, 'scene': 0,
            'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes, 'materials': materials,
            'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(buffer)}],
            'extras': {'document_id': scene['document_id'], 'revision': scene['revision'], 'source_units': units,
                       'fidelity': 'conceptual', 'engineering_verified': False}}
    header = json.dumps(gltf, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    header += b' ' * (-len(header) % 4)
    raw = (struct.pack('<III', 0x46546C67, 2, 28 + len(header) + len(buffer))
           + struct.pack('<II', len(header), 0x4E4F534A) + header
           + struct.pack('<II', len(buffer), 0x004E4942) + buffer)
    validated = validate_glb_bytes(raw)
    return raw, {'valid': validated['valid'], 'triangle_count': triangles, 'mesh_count': len(meshes),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'fidelity': 'conceptual', 'engineering_verified': False}
