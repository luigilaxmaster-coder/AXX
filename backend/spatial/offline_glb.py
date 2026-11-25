"""Admission for the renderer's offline GLB loader; no external resources or decoder fetching."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import struct

from PIL import Image
from backend.spatial.asset_registry import AssetGateError, AssetSecurityError, MAX_ASSET_BYTES, MAX_TRIANGLES


def validate_offline_glb(raw: bytes) -> dict:
    try:
        return _validate_offline_glb(raw)
    except (KeyError,IndexError,TypeError,AttributeError,OverflowError,RecursionError,struct.error) as exc:
        raise AssetGateError('Malformed GLB structure') from None


def _validate_offline_glb(raw: bytes) -> dict:
    def reject(message):
        raise AssetGateError(message)

    if not 28 <= len(raw) <= MAX_ASSET_BYTES or struct.unpack_from('<III', raw) != (0x46546C67, 2, len(raw)):
        reject('Invalid bounded GLB 2.0 header')
    length, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4E4F534A or length > 2*1024*1024 or 28+length > len(raw):
        reject('Invalid GLB JSON chunk')
    doc = json.loads(raw[20:20+length])
    pending=[(doc,0)];items=0
    while pending:
        value,depth=pending.pop();items+=1
        if depth>64 or items>100_000:reject('GLB JSON structure budget exceeded')
        if isinstance(value,float) and not math.isfinite(value):reject('Nonfinite GLB metadata')
        if isinstance(value,dict):pending.extend((v,depth+1) for v in value.values())
        elif isinstance(value,list):pending.extend((v,depth+1) for v in value)
    blen, bkind = struct.unpack_from('<II', raw, 20+length)
    if bkind != 0x004E4942 or 28+length+blen != len(raw):
        reject('Invalid GLB binary chunk')
    binary = memoryview(raw)[28+length:]
    if len(doc.get('buffers', [])) != 1 or doc['buffers'][0].get('byteLength', blen+1) > blen:
        reject('Only one embedded binary buffer is supported')
    if doc.get('skins') or doc.get('animations'):
        reject('Rigged/embedded animation assets need a dedicated adapter; use the AXX timeline')
    for section in ('buffers', 'images'):
        for entry in doc.get(section, []):
            if 'uri' in entry:
                raise AssetSecurityError('Offline GLB requires embedded buffers and images; URI loading is disabled')
    if set(doc.get('extensionsRequired', [])) - {'KHR_materials_unlit', 'KHR_texture_transform'}:
        reject('This GLB requires an unavailable decoder or material extension')
    views = doc.get('bufferViews', [])
    if len(views) > 4096 or len(doc.get('accessors', [])) > 4096:
        reject('GLB accessor budget exceeded')
    total_values=0
    for acc in doc.get('accessors',[]):
        count=acc.get('count')
        if type(count) is not int or count<1:reject('Invalid accessor count')
        total_values+=count*{'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}.get(acc.get('type'),16)
        if total_values>8_000_000:reject('Aggregate accessor budget exceeded')
    for view in views:
        start, size = view.get('byteOffset', 0), view.get('byteLength')
        if (type(start) is not int or type(size) is not int or start < 0 or size < 0
                or start+size > blen or view.get('buffer', 0) != 0 or view.get('extensions')):
            reject('Invalid or compressed buffer view')

    def accessor(index, *, position=False, indices=False):
        if type(index) is not int or not 0 <= index < len(doc.get('accessors', [])):
            reject('Invalid accessor reference')
        acc = doc['accessors'][index]
        view_id, count = acc.get('bufferView'), acc.get('count')
        if type(view_id) is not int or not 0 <= view_id < len(views) or acc.get('sparse'):
            reject('Missing buffer view or unsupported sparse accessor')
        if type(count) is not int or not 1 <= count <= MAX_TRIANGLES*3:
            reject('Mesh vertex/index budget exceeded')
        components = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}.get(acc.get('type'))
        formats = {5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
        if components is None or acc.get('componentType') not in formats:
            reject('Unsupported accessor format')
        fmt, width = formats[acc['componentType']]
        view = views[view_id]
        stride, offset = view.get('byteStride', components*width), acc.get('byteOffset', 0)
        if (type(offset) is not int or offset < 0 or type(stride) is not int
                or not components*width <= stride <= 252 or offset+(count-1)*stride+components*width > view['byteLength']):
            reject('Accessor exceeds its buffer view')
        if position and (components != 3 or fmt != 'f'):
            reject('Mesh positions must be float32 VEC3')
        if indices and (components != 1 or fmt not in ('B','H','I')):
            reject('Mesh indices must be unsigned SCALAR')
        values = []
        for row in range(count):
            value = struct.unpack_from('<'+fmt*components, binary, view.get('byteOffset',0)+offset+row*stride)
            if any(not math.isfinite(v) or (position and abs(v)>1e6) for v in value):
                reject('Nonfinite or out-of-bounds mesh data')
            if indices: values.append(value[0])
        return count, values

    for index in range(len(doc.get('accessors', []))):
        accessor(index)
    triangles = 0
    meshes = doc.get('meshes', [])
    if not 1 <= len(meshes) <= 128:
        reject('GLB must contain 1..128 meshes')
    mesh_counts = []
    for mesh in meshes:
        count = 0
        for primitive in mesh.get('primitives', []):
            if primitive.get('mode',4) != 4 or primitive.get('targets') or primitive.get('extensions'):
                reject('Only uncompressed static triangle meshes are supported')
            vertices, _ = accessor(primitive.get('attributes',{}).get('POSITION'), position=True)
            size, indices = accessor(primitive['indices'], indices=True) if 'indices' in primitive else (vertices, [])
            if size % 3 or (indices and max(indices) >= vertices):
                reject('Invalid triangle indices')
            count += size//3
        if not count: reject('Empty mesh')
        mesh_counts.append(count)
    nodes = doc.get('nodes', [])
    if not 1 <= len(nodes) <= 512:
        reject('Node budget exceeded')
    seen = set()
    def walk(index, ancestors):
        nonlocal triangles
        if type(index) is not int or not 0 <= index < len(nodes) or index in ancestors or len(ancestors)>32:
            reject('Invalid/cyclic GLB hierarchy')
        if index in seen: reject('A GLB node must have one parent')
        seen.add(index)
        node = nodes[index]
        for key, length in [('matrix',16),('translation',3),('rotation',4),('scale',3)]:
            if key in node and (not isinstance(node[key],list) or len(node[key])!=length
                    or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in node[key])):
                reject('Invalid node transform')
        if 'mesh' in node:
            mid = node['mesh']
            if type(mid) is not int or not 0 <= mid < len(meshes): reject('Invalid mesh reference')
            triangles += mesh_counts[mid]
            if triangles>MAX_TRIANGLES: reject('Scene exceeds triangle budget')
        for child in node.get('children',[]): walk(child, ancestors|{index})
    scenes = doc.get('scenes', [])
    sid = doc.get('scene',0)
    if type(sid) is not int or not 0 <= sid < len(scenes): reject('Missing GLB scene')
    for root in scenes[sid].get('nodes',[]): walk(root,set())
    pixels = 0
    for image in doc.get('images', []):
        vi = image.get('bufferView')
        if type(vi) is not int or not 0 <= vi < len(views) or image.get('mimeType') not in ('image/png','image/jpeg'):
            reject('Only embedded PNG/JPEG textures are supported')
        view = views[vi]
        with Image.open(io.BytesIO(binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']])) as tex:
            if tex.width>4096 or tex.height>4096: reject('Texture exceeds 4096 pixels per axis')
            pixels += tex.width*tex.height
            if pixels>32*1024*1024: reject('Texture pixel budget exceeded')
            tex.verify()
    if not triangles: reject('No triangles in active scene')
    return {'valid':True, 'sha256':hashlib.sha256(raw).hexdigest(), 'triangle_count':triangles,
            'node_count':len(seen), 'texture_count':len(doc.get('images',[])), 'texture_pixels':pixels, 'size_bytes':len(raw)}
