"""SceneDocument v2 contract validator, v1 non-destructive adapter, and persistent store (PR-03).

Enforces Invariants:
- I-07: Never claim 'cad_verified' fidelity from an unmeasured image capture or without verified CAD solid assets.
- Never embed large binary STEP/GLB payloads inside JSON; reference external content-addressed assets by sha256.
- Preserve PresentationPlan v1 compatibility via non-destructive import.
"""
from __future__ import annotations

from contextlib import closing
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SHA256_RE = re.compile(r'^[a-f0-9]{64}$')

VALID_MODES = frozenset({'diagram', 'cad', 'simulation', 'motion', 'material', 'diorama', 'conceptual'})
VALID_UNITS = frozenset({'mm', 'cm', 'm', 'in', 'ft', 'unitless'})
VALID_FIDELITIES = frozenset({'illustrative', 'conceptual', 'measured', 'cad_verified'})
VALID_SOURCES = frozenset({'magic_pen_capture', 'file', 'user_spec', 'procedural'})
VALID_REPRESENTATIONS = frozenset({'svg_node', 'mesh', 'brep', 'primitive', 'annotation', 'splat'})
VALID_MEASURED_SOURCES = frozenset({'observed', 'documented', 'inferred', 'assumed'})


class SceneDocumentError(ValueError):
    """Raised when a SceneDocument v2 violates schema or fidelity invariants."""


class StaleSceneRevisionError(ValueError):
    """Raised when a CAS update or patch specifies a stale base_revision (MP-02)."""


def _check_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SceneDocumentError(f'Invalid {field}: {value!r}')
    return value


def _check_vec3(vec: Any, field: str) -> list[float]:
    if not isinstance(vec, list) or len(vec) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in vec):
        raise SceneDocumentError(f'{field} must be a 3-element finite numeric array')
    return [float(x) for x in vec]


def validate_scene_document_v2(doc: Any) -> dict[str, Any]:
    """Validate a SceneDocument v2 dictionary against the canonical contract and I-07 invariants."""
    if not isinstance(doc, dict):
        raise SceneDocumentError('SceneDocument v2 must be a JSON object')
    allowed_top = {
        'schema_version',
        'document_id',
        'revision',
        'mode',
        'units',
        'fidelity',
        'coordinate_system',
        'source',
        'objects',
        'assets',
        'timeline',
        'diagram',
        'metadata',
    }
    extra_top = set(doc) - allowed_top
    if extra_top:
        raise SceneDocumentError(f'Unexpected top-level fields in SceneDocument v2: {sorted(extra_top)}')

    if doc.get('schema_version') != '2.0':
        raise SceneDocumentError("schema_version must be '2.0'")
    doc_id = _check_id(doc.get('document_id'), 'document_id')
    revision = doc.get('revision')
    if type(revision) is not int or revision < 1:
        raise SceneDocumentError('revision must be an integer >= 1')

    mode = doc.get('mode')
    if mode not in VALID_MODES:
        raise SceneDocumentError(f'Invalid mode: {mode!r}')
    units = doc.get('units')
    if units not in VALID_UNITS:
        raise SceneDocumentError(f'Invalid units: {units!r}')
    fidelity = doc.get('fidelity')
    if fidelity not in VALID_FIDELITIES:
        raise SceneDocumentError(f'Invalid fidelity: {fidelity!r}')

    coord = doc.get('coordinate_system')
    if not isinstance(coord, dict):
        raise SceneDocumentError('coordinate_system must be an object')
    if coord.get('up_axis') not in ('X', 'Y', 'Z') or coord.get('handedness') not in ('left', 'right'):
        raise SceneDocumentError('Invalid coordinate_system.up_axis or handedness')
    origin = _check_vec3(coord.get('origin', [0.0, 0.0, 0.0]), 'coordinate_system.origin')

    source = doc.get('source')
    if not isinstance(source, dict):
        raise SceneDocumentError('source must be an object')
    if source.get('kind') not in VALID_SOURCES:
        raise SceneDocumentError(f"Invalid source.kind: {source.get('kind')!r}")
    _check_id(source.get('source_id'), 'source.source_id')
    if type(source.get('revision')) is not int or source['revision'] < 1:
        raise SceneDocumentError('source.revision must be an integer >= 1')
    if 'sha256' in source and source['sha256'] is not None:
        if not isinstance(source['sha256'], str) or not SHA256_RE.fullmatch(source['sha256']):
            raise SceneDocumentError('Invalid source.sha256')

    # Validate assets first so object geometry_asset_id references can be checked
    raw_assets = doc.get('assets')
    if not isinstance(raw_assets, list) or len(raw_assets) > 10000:
        raise SceneDocumentError('assets must be a list of at most 10000 items')
    assets_by_id: dict[str, dict[str, Any]] = {}
    validated_assets: list[dict[str, Any]] = []
    for asset in raw_assets:
        if not isinstance(asset, dict):
            raise SceneDocumentError('Each asset must be an object')
        aid = _check_id(asset.get('asset_id'), 'asset.asset_id')
        if aid in assets_by_id:
            raise SceneDocumentError(f'Duplicate asset_id: {aid}')
        sha = asset.get('sha256')
        if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
            raise SceneDocumentError(f'Invalid sha256 for asset {aid}')
        mime = asset.get('mime_type')
        if not isinstance(mime, str) or not (1 <= len(mime) <= 100):
            raise SceneDocumentError(f'Invalid mime_type for asset {aid}')
        size_bytes = asset.get('size_bytes')
        if type(size_bytes) is not int or size_bytes < 0:
            raise SceneDocumentError(f'Invalid size_bytes for asset {aid}')
        if 'data_base64' in asset or 'raw_bytes' in asset:
            raise SceneDocumentError(f'Binary payload embedding is prohibited in SceneDocument v2 asset {aid}')
        clean_asset = {
            'asset_id': aid,
            'sha256': sha,
            'mime_type': mime,
            'size_bytes': size_bytes,
            'license': str(asset.get('license', 'internal'))[:240],
        }
        if asset.get('source_uri'):
            clean_asset['source_uri'] = str(asset['source_uri'])[:2000]
        if asset.get('credit_line'):
            clean_asset['credit_line'] = str(asset['credit_line'])[:1000]
        assets_by_id[aid] = clean_asset
        validated_assets.append(clean_asset)

    # Validate objects
    raw_objects = doc.get('objects')
    if not isinstance(raw_objects, list) or len(raw_objects) > 10000:
        raise SceneDocumentError('objects must be a list of at most 10000 items')
    seen_obj_ids = set()
    validated_objects: list[dict[str, Any]] = []
    has_verified_brep = False
    for obj in raw_objects:
        if not isinstance(obj, dict):
            raise SceneDocumentError('Each object must be a dictionary')
        oid = _check_id(obj.get('id'), 'object.id')
        if oid in seen_obj_ids:
            raise SceneDocumentError(f'Duplicate object.id: {oid}')
        seen_obj_ids.add(oid)
        name = obj.get('name')
        if not isinstance(name, str) or not (1 <= len(name.strip()) <= 240):
            raise SceneDocumentError(f'Invalid object.name for {oid}')
        rep = obj.get('representation')
        if rep not in VALID_REPRESENTATIONS:
            raise SceneDocumentError(f'Invalid representation for {oid}: {rep!r}')
        obj_fidelity = obj.get('fidelity')
        if obj_fidelity not in VALID_FIDELITIES:
            raise SceneDocumentError(f'Invalid fidelity for {oid}: {obj_fidelity!r}')
        measured_src = obj.get('measured_source', 'assumed')
        if measured_src not in VALID_MEASURED_SOURCES:
            raise SceneDocumentError(f'Invalid measured_source for {oid}: {measured_src!r}')

        geom_id = obj.get('geometry_asset_id')
        if geom_id is not None:
            _check_id(geom_id, 'object.geometry_asset_id')
            if geom_id not in assets_by_id:
                raise SceneDocumentError(f'Object {oid} references unknown geometry_asset_id {geom_id}')

        # Invariant I-07: cad_verified requires concrete units, documented/observed dimensions, and a verified STEP/BRep asset
        if obj_fidelity == 'cad_verified':
            if units == 'unitless':
                raise SceneDocumentError(f'Object {oid} cannot be cad_verified with unitless scene units (I-07)')
            if measured_src in ('inferred', 'assumed'):
                raise SceneDocumentError(
                    f'Object {oid} with measured_source={measured_src!r} cannot claim cad_verified (I-07)'
                )
            if rep != 'brep' or not geom_id:
                raise SceneDocumentError(
                    f'Object {oid} claiming cad_verified must have representation="brep" and a verified geometry_asset_id (I-07)'
                )
            has_verified_brep = True

        transform_raw = obj.get('transform') or {}
        if not isinstance(transform_raw, dict):
            raise SceneDocumentError(f'transform for {oid} must be an object')
        transform = {
            'position': _check_vec3(transform_raw.get('position', [0.0, 0.0, 0.0]), f'{oid}.transform.position'),
            'rotation': _check_vec3(transform_raw.get('rotation', [0.0, 0.0, 0.0]), f'{oid}.transform.rotation'),
            'scale': _check_vec3(transform_raw.get('scale', [1.0, 1.0, 1.0]), f'{oid}.transform.scale'),
        }
        props = obj.get('properties') or {}
        if not isinstance(props, dict):
            raise SceneDocumentError(f'properties for {oid} must be an object')
        # Block scripts or big blobs inside properties
        props_str = json.dumps(props, ensure_ascii=False, allow_nan=False)
        if len(props_str) > 32768:
            raise SceneDocumentError(f'properties for {oid} exceed 32 KiB limit')

        clean_obj: dict[str, Any] = {
            'id': oid,
            'name': name.strip(),
            'representation': rep,
            'fidelity': obj_fidelity,
            'measured_source': measured_src,
            'transform': transform,
            'properties': copy.deepcopy(props),
        }
        if geom_id is not None:
            clean_obj['geometry_asset_id'] = geom_id
        validated_objects.append(clean_obj)

    # Invariant I-07 document-level check
    if fidelity == 'cad_verified':
        if units == 'unitless':
            raise SceneDocumentError('SceneDocument cannot be cad_verified with unitless units (I-07)')
        if source.get('kind') == 'magic_pen_capture' and not has_verified_brep:
            raise SceneDocumentError(
                'An isolated image capture without verified BRep solids and dimensions cannot claim cad_verified (I-07)'
            )
        if not has_verified_brep:
            raise SceneDocumentError('cad_verified scene requires at least one verified BRep object (I-07)')

    # Validate timeline
    timeline = doc.get('timeline')
    if not isinstance(timeline, dict):
        raise SceneDocumentError('timeline must be an object')
    duration = timeline.get('duration_seconds', 0)
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise SceneDocumentError('timeline.duration_seconds must be a non-negative finite number')
    tracks = timeline.get('tracks')
    if not isinstance(tracks, list) or len(tracks) > 10000:
        raise SceneDocumentError('timeline.tracks must be a list')

    result: dict[str, Any] = {
        'schema_version': '2.0',
        'document_id': doc_id,
        'revision': revision,
        'mode': mode,
        'units': units,
        'fidelity': fidelity,
        'coordinate_system': {
            'up_axis': coord['up_axis'],
            'handedness': coord['handedness'],
            'origin': origin,
        },
        'source': copy.deepcopy(source),
        'objects': validated_objects,
        'assets': validated_assets,
        'timeline': {
            'duration_seconds': float(duration),
            'tracks': copy.deepcopy(tracks),
        },
    }
    if 'diagram' in doc and doc['diagram'] is not None:
        if not isinstance(doc['diagram'], dict):
            raise SceneDocumentError('diagram must be an object')
        result['diagram'] = copy.deepcopy(doc['diagram'])
    if 'metadata' in doc and doc['metadata'] is not None:
        if not isinstance(doc['metadata'], dict):
            raise SceneDocumentError('metadata must be an object')
        result['metadata'] = copy.deepcopy(doc['metadata'])
    return result


def import_presentation_plan_v1(
    plan_v1: dict[str, Any],
    *,
    document_id: str,
    source_id: str,
    source_revision: int = 1,
) -> dict[str, Any]:
    """Non-destructively import a PresentationPlan v1 into a validated SceneDocument v2."""
    if not isinstance(plan_v1, dict):
        raise SceneDocumentError('plan_v1 must be a dictionary')
    raw_fidelity = plan_v1.get('fidelity', 'conceptual')
    fidelity = 'illustrative' if raw_fidelity == 'illustrative' else 'conceptual'

    scene_v1 = plan_v1.get('scene') if isinstance(plan_v1.get('scene'), dict) else {}
    v1_objects = scene_v1.get('objects') if isinstance(scene_v1.get('objects'), list) else []
    diagram_v1 = plan_v1.get('diagram') if isinstance(plan_v1.get('diagram'), dict) else None
    steps_v1 = plan_v1.get('steps') if isinstance(plan_v1.get('steps'), list) else []

    mode = 'conceptual' if v1_objects else ('diagram' if diagram_v1 else 'conceptual')
    objects_v2: list[dict[str, Any]] = []
    for item in v1_objects:
        if not isinstance(item, dict):
            continue
        oid = str(item.get('id') or f'o{len(objects_v2) + 1}')
        pos = item.get('position') if isinstance(item.get('position'), list) and len(item.get('position')) == 3 else [0.0, 0.0, 0.0]
        rot = item.get('rotation') if isinstance(item.get('rotation'), list) and len(item.get('rotation')) == 3 else [0.0, 0.0, 0.0]
        size = item.get('size') if isinstance(item.get('size'), list) and len(item.get('size')) == 3 else [1.0, 1.0, 1.0]
        objects_v2.append({
            'id': oid,
            'name': str(item.get('label') or oid)[:240],
            'representation': 'primitive',
            'fidelity': 'conceptual',
            'measured_source': 'inferred',
            'transform': {
                'position': [float(x) for x in pos],
                'rotation': [float(x) for x in rot],
                'scale': [1.0, 1.0, 1.0],
            },
            'properties': {
                'shape': item.get('shape', 'box'),
                'size': [float(x) for x in size],
                'color': item.get('color', '#438ee8'),
                'material': item.get('material', 'plastic'),
                'explode': item.get('explode', [0.0, 0.0, 0.0]),
                'param': item.get('param'),
                'group': item.get('group'),
            },
        })

    if diagram_v1 and isinstance(diagram_v1.get('nodes'), list):
        for node in diagram_v1['nodes']:
            if not isinstance(node, dict):
                continue
            nid = str(node.get('id') or f'd{len(objects_v2) + 1}')
            if any(o['id'] == nid for o in objects_v2):
                nid = f'diag-{nid}'
            bounds = node.get('bounds') if isinstance(node.get('bounds'), list) and len(node.get('bounds')) == 4 else [0.1, 0.1, 0.25, 0.15]
            objects_v2.append({
                'id': nid,
                'name': str(node.get('label') or nid)[:240],
                'representation': 'svg_node',
                'fidelity': fidelity,
                'measured_source': 'observed',
                'transform': {
                    'position': [float(bounds[0]), float(bounds[1]), 0.0],
                    'rotation': [0.0, 0.0, 0.0],
                    'scale': [float(bounds[2]), float(bounds[3]), 1.0],
                },
                'properties': {
                    'bounds': [float(x) for x in bounds],
                    'step_id': node.get('step_id'),
                    'linked_object_id': node.get('object_id'),
                },
            })

    tracks = []
    for idx, step in enumerate(steps_v1):
        if isinstance(step, dict):
            tracks.append({
                'track_id': f"step-{step.get('id', idx + 1)}",
                'kind': 'teaching_step',
                'start_time': float(idx * 4.0),
                'duration': 4.0,
                'title': str(step.get('title', '')),
                'narration': str(step.get('narration', '')),
                'focus': list(step.get('focus') or []),
            })

    doc_v2 = {
        'schema_version': '2.0',
        'document_id': document_id,
        'revision': 1,
        'mode': mode,
        'units': 'unitless',
        'fidelity': fidelity,
        'coordinate_system': {
            'up_axis': 'Y',
            'handedness': 'right',
            'origin': [0.0, 0.0, 0.0],
        },
        'source': {
            'kind': 'magic_pen_capture',
            'source_id': source_id,
            'revision': int(source_revision),
        },
        'objects': objects_v2,
        'assets': [],
        'timeline': {
            'duration_seconds': float(len(tracks) * 4.0),
            'tracks': tracks,
        },
        'diagram': copy.deepcopy(diagram_v1) if diagram_v1 else {'nodes': [], 'edges': []},
        'metadata': {
            'imported_from_schema': '1.0',
            'title': str(plan_v1.get('title', '')),
            'summary': str(plan_v1.get('summary', '')),
        },
    }
    return validate_scene_document_v2(doc_v2)


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class SceneDocumentStore:
    """SQLite-backed versioned store for SceneDocument v2 with immutable revision history and undo/redo stacks."""

    def __init__(self, db_path: str | Path = ':memory:', clock=None):
        self.db_path = str(db_path)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _connect(self):
        if self._persistent_conn is not None:
            return _NullClosing(self._persistent_conn)
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def _init_schema(self) -> None:
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS spatial_scenes_v2 (
                        document_id TEXT PRIMARY KEY,
                        current_revision INTEGER NOT NULL CHECK(current_revision > 0),
                        mode TEXT NOT NULL,
                        fidelity TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        source_revision INTEGER NOT NULL,
                        document_json TEXT NOT NULL,
                        document_sha256 TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        CHECK(json_valid(document_json))
                    )
                    '''
                )
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS spatial_scene_revisions_v2 (
                        document_id TEXT NOT NULL REFERENCES spatial_scenes_v2(document_id) ON DELETE CASCADE,
                        revision INTEGER NOT NULL CHECK(revision > 0),
                        operation_id TEXT NOT NULL,
                        document_json TEXT NOT NULL,
                        document_sha256 TEXT NOT NULL,
                        patch_json TEXT,
                        inverse_patch_json TEXT,
                        created_at_ms INTEGER NOT NULL,
                        PRIMARY KEY(document_id, revision)
                    )
                    '''
                )
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS spatial_scene_undo_stack (
                        document_id TEXT PRIMARY KEY REFERENCES spatial_scenes_v2(document_id) ON DELETE CASCADE,
                        undo_stack_json TEXT NOT NULL DEFAULT '[]',
                        redo_stack_json TEXT NOT NULL DEFAULT '[]'
                    )
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    @staticmethod
    def _doc_hash(doc: dict[str, Any]) -> str:
        raw = json.dumps(doc, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def create_document(self, doc: dict[str, Any], *, operation_id: str = 'op-init') -> dict[str, Any]:
        validated = validate_scene_document_v2(doc)
        if validated['revision'] != 1:
            raise SceneDocumentError('Initial SceneDocument v2 revision must be 1')
        doc_id = validated['document_id']
        doc_json = json.dumps(validated, ensure_ascii=False, allow_nan=False)
        doc_sha = self._doc_hash(validated)
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM spatial_scenes_v2 WHERE document_id=?', (doc_id,)).fetchone():
                    raise SceneDocumentError(f'SceneDocument {doc_id} already exists')
                db.execute(
                    '''
                    INSERT INTO spatial_scenes_v2
                        (document_id, current_revision, mode, fidelity, source_id, source_revision,
                         document_json, document_sha256, created_at_ms, updated_at_ms)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        doc_id,
                        validated['mode'],
                        validated['fidelity'],
                        validated['source']['source_id'],
                        validated['source']['revision'],
                        doc_json,
                        doc_sha,
                        now,
                        now,
                    ),
                )
                db.execute(
                    '''
                    INSERT INTO spatial_scene_revisions_v2
                        (document_id, revision, operation_id, document_json, document_sha256,
                         patch_json, inverse_patch_json, created_at_ms)
                    VALUES (?, 1, ?, ?, ?, NULL, NULL, ?)
                    ''',
                    (doc_id, operation_id, doc_json, doc_sha, now),
                )
                db.execute(
                    "INSERT INTO spatial_scene_undo_stack (document_id, undo_stack_json, redo_stack_json) VALUES (?, '[]', '[]')",
                    (doc_id,),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return validated

    def get_document(self, document_id: str, *, revision: int | None = None) -> dict[str, Any]:
        _check_id(document_id, 'document_id')
        with self.lock, self._connect() as db:
            if revision is None:
                row = db.execute(
                    'SELECT document_json FROM spatial_scenes_v2 WHERE document_id=?',
                    (document_id,),
                ).fetchone()
            else:
                row = db.execute(
                    'SELECT document_json FROM spatial_scene_revisions_v2 WHERE document_id=? AND revision=?',
                    (document_id, int(revision)),
                ).fetchone()
            if not row:
                raise SceneDocumentError(f'SceneDocument {document_id} (revision={revision}) not found')
            return json.loads(row['document_json'])

    def list_revisions(self, document_id: str) -> list[dict[str, Any]]:
        _check_id(document_id, 'document_id')
        with self.lock, self._connect() as db:
            rows = db.execute(
                '''
                SELECT revision, operation_id, document_sha256, created_at_ms
                FROM spatial_scene_revisions_v2 WHERE document_id=? ORDER BY revision ASC
                ''',
                (document_id,),
            ).fetchall()
            return [
                {
                    'revision': int(r['revision']),
                    'operation_id': r['operation_id'],
                    'document_sha256': r['document_sha256'],
                    'created_at_ms': int(r['created_at_ms']),
                }
                for r in rows
            ]
