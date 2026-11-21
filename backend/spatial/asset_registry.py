"""Asset Gate Registry, license provenance validator, and content-addressed asset store (PR-07 / MP-07 / E2E-12).

Enforces Invariants:
- Content-addressed storage by SHA-256: updating an asset with the same logical name creates a new
  immutable entry and emits an upgrade notice without mutating existing SceneDocuments (E2E-12).
- License compliance: tracks license, author, credit_line, origin_uri, and redistribution_allowed.
  Quixel/Fab/Megascans and excluded third-party models (e.g., Kervan) cannot be marked redistributable.
- Security (MP-07): no automatic downloads outside authorized roots; validates GLB/glTF decoders,
  LOD, triangle limits, and blocks external URI traversal inside glTF JSON.
- Paid generation ('generate_asset') is strictly opt-in and disabled by default in read-only MCP discovery.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import threading
import time
from typing import Any

from backend.shape_registry import ShapeRegistry
from backend.spatial.scene_document import SHA256_RE, _check_id

ALLOWED_ASSET_MIMES = frozenset({
    'model/gltf-binary',
    'model/gltf+json',
    'model/step',
    'model/stl',
    'image/png',
    'image/svg+xml',
})

ALLOWED_DECODERS = frozenset({'gltf', 'draco', 'meshopt', 'step', 'stl', 'png', 'svg'})
ALLOWED_LODS = frozenset({'lod0', 'lod1', 'lod2', 'lod3'})

NON_REDISTRIBUTABLE_SOURCES = frozenset({
    'fab',
    'quixel',
    'megascans',
    'kervan_excluded',
    'proprietary_external',
})

ATTRIBUTION_REQUIRED_LICENSES = frozenset({
    'CC-BY-4.0',
    'CC-BY-3.0',
    'CC-BY-SA-4.0',
})

MAX_ASSET_BYTES = 50 * 1024 * 1024  # 50 MiB
MAX_TRIANGLES = 250_000


class AssetGateError(ValueError):
    """Raised when an asset fails license, decoder, LOD, or security validation."""


class AssetSecurityError(PermissionError):
    """Raised when an asset attempts unauthorized remote access, path traversal, or paid generation without opt-in."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def validate_gltf_or_glb_payload(
    raw_bytes: bytes,
    mime_type: str,
) -> dict[str, Any]:
    """Inspect GLB/glTF bytes to block external path traversal URIs and dangerous extensions (MP-07)."""
    if len(raw_bytes) > MAX_ASSET_BYTES:
        raise AssetGateError(f'Asset size {len(raw_bytes)} exceeds MAX_ASSET_BYTES={MAX_ASSET_BYTES}')

    if mime_type == 'model/gltf-binary':
        if len(raw_bytes) < 28:
            raise AssetGateError('GLB payload too short')
        magic, version, total_len = struct.unpack('<III', raw_bytes[:12])
        if magic != 0x46546C67 or version != 2 or total_len != len(raw_bytes):
            raise AssetGateError('Invalid GLB header')
        json_len, json_type = struct.unpack('<II', raw_bytes[12:20])
        if json_type != 0x4E4F534A:
            raise AssetGateError('GLB missing JSON chunk')
        gltf_obj = json.loads(raw_bytes[20:20 + json_len].decode('utf-8'))
    elif mime_type == 'model/gltf+json':
        gltf_obj = json.loads(raw_bytes.decode('utf-8'))
    else:
        return {'inspected_gltf': False}

    # Check buffers and images for external/traversal URIs
    for section in ('buffers', 'images'):
        for entry in gltf_obj.get(section) or []:
            if isinstance(entry, dict) and 'uri' in entry:
                uri = str(entry['uri'])
                if uri.startswith('data:'):
                    continue
                if '..' in uri or uri.startswith(('/', '\\')) or '://' in uri or ':' in uri:
                    raise AssetSecurityError(f'Blocked unsafe external or traversal URI in glTF {section}: {uri!r}')

    allowed_exts = {
        'KHR_draco_mesh_compression',
        'EXT_meshopt_compression',
        'KHR_materials_pbrSpecularGlossiness',
        'KHR_materials_unlit',
        'KHR_texture_transform',
        'KHR_lights_punctual',
    }
    for ext in gltf_obj.get('extensionsRequired') or []:
        if ext not in allowed_exts:
            raise AssetGateError(f'Unsupported required glTF extension: {ext!r}')

    return {'inspected_gltf': True, 'node_count': len(gltf_obj.get('nodes') or [])}


class AssetRegistry:
    """Content-addressed SQLite + disk asset store with license provenance and read-only Asset Gate discovery."""

    def __init__(
        self,
        db_path: str | Path = ':memory:',
        *,
        storage_root: str | Path | None = None,
        shape_registry: ShapeRegistry | None = None,
        clock=None,
    ):
        self.db_path = str(db_path)
        self.storage_root = Path(storage_root).resolve() if storage_root else None
        if self.storage_root:
            self.storage_root.mkdir(parents=True, exist_ok=True)
        self.shape_registry = shape_registry
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
                    CREATE TABLE IF NOT EXISTS spatial_asset_registry (
                        asset_id TEXT PRIMARY KEY,
                        logical_name TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        mime_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                        license TEXT NOT NULL,
                        asset_source TEXT NOT NULL,
                        origin_uri TEXT NOT NULL,
                        author TEXT NOT NULL DEFAULT '',
                        credit_line TEXT NOT NULL DEFAULT '',
                        attribution_scope TEXT NOT NULL DEFAULT 'project',
                        redistribution_allowed INTEGER NOT NULL DEFAULT 0 CHECK(redistribution_allowed IN (0, 1)),
                        lod_level TEXT NOT NULL DEFAULT 'lod0',
                        triangle_count INTEGER NOT NULL DEFAULT 0,
                        dimensions_m_json TEXT NOT NULL DEFAULT '[1.0, 1.0, 1.0]',
                        decoders_json TEXT NOT NULL DEFAULT '["gltf"]',
                        storage_path TEXT,
                        created_at_ms INTEGER NOT NULL,
                        CHECK(json_valid(dimensions_m_json)),
                        CHECK(json_valid(decoders_json))
                    )
                    '''
                )
                db.execute(
                    'CREATE INDEX IF NOT EXISTS idx_spatial_assets_sha ON spatial_asset_registry(sha256)'
                )
                db.execute(
                    'CREATE INDEX IF NOT EXISTS idx_spatial_assets_logical ON spatial_asset_registry(logical_name, created_at_ms)'
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def register_asset(
        self,
        *,
        asset_id: str,
        logical_name: str,
        raw_bytes: bytes,
        mime_type: str,
        license_id: str,
        asset_source: str = 'local',
        origin_uri: str = 'local://project',
        author: str = '',
        credit_line: str = '',
        attribution_scope: str = 'project',
        redistribution_allowed: bool = True,
        lod_level: str = 'lod0',
        triangle_count: int = 0,
        dimensions_m: list[float] | None = None,
        decoders: list[str] | None = None,
        expected_sha256: str | None = None,
        allow_remote_origin: bool = False,
    ) -> dict[str, Any]:
        """Validate and store an asset in the content-addressed registry (MP-07 / E2E-12)."""
        _check_id(asset_id, 'asset_id')
        if not isinstance(logical_name, str) or not (1 <= len(logical_name.strip()) <= 160):
            raise AssetGateError('Invalid logical_name')
        if mime_type not in ALLOWED_ASSET_MIMES:
            raise AssetGateError(f'Unsupported asset mime_type: {mime_type!r}')
        if not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) == 0:
            raise AssetGateError('raw_bytes must be non-empty')

        if origin_uri.startswith(('http://', 'https://')) and not allow_remote_origin:
            raise AssetSecurityError(
                f'Remote asset origin {origin_uri!r} blocked: automatic remote downloads are disabled by default (MP-07)'
            )
        if '..' in origin_uri:
            raise AssetSecurityError(f'Path traversal in origin_uri blocked: {origin_uri!r}')

        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
                raise AssetGateError('Invalid expected_sha256 format')
            if actual_sha != expected_sha256:
                raise AssetGateError(f'Asset SHA256 mismatch: expected {expected_sha256}, actual {actual_sha}')

        validate_gltf_or_glb_payload(bytes(raw_bytes), mime_type)

        if lod_level not in ALLOWED_LODS:
            raise AssetGateError(f'Invalid lod_level: {lod_level!r}')
        if type(triangle_count) is not int or not (0 <= triangle_count <= MAX_TRIANGLES):
            raise AssetGateError(f'triangle_count {triangle_count} exceeds budget {MAX_TRIANGLES}')

        dec_list = [str(d) for d in (decoders or ['gltf'])]
        if not dec_list or any(d not in ALLOWED_DECODERS for d in dec_list):
            raise AssetGateError(f'Unsupported decoders: {dec_list}')

        dims = dimensions_m
        if dims is not None and (not isinstance(dims, list) or len(dims) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in dims)):
            raise AssetGateError('dimensions_m must be 3 positive numbers [x, y, z] in meters')

        lic = str(license_id or '').strip()
        if not lic:
            raise AssetGateError('Asset license is required')
        src = str(asset_source or 'local').strip().lower()
        if src in NON_REDISTRIBUTABLE_SOURCES:
            if src == 'kervan_excluded':
                raise AssetGateError('Kervan models excluded from MIT license cannot be imported into AXX')
            redistribution_allowed = False

        if lic in ATTRIBUTION_REQUIRED_LICENSES and not str(credit_line).strip():
            raise AssetGateError(f'License {lic} requires a non-empty credit_line')

        storage_path_str = None
        if self.storage_root is not None:
            ext = mime_type.split('/')[-1].split('+')[0]
            blob_path = self.storage_root / f'{actual_sha}.{ext}'
            if not blob_path.exists():
                blob_path.write_bytes(bytes(raw_bytes))
            storage_path_str = str(blob_path)

        now = self.clock()
        upgrade_notice = None

        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                existing_id = db.execute(
                    'SELECT sha256 FROM spatial_asset_registry WHERE asset_id=?',
                    (asset_id,),
                ).fetchone()
                if existing_id and existing_id['sha256'] != actual_sha:
                    raise AssetGateError(
                        f'Immutable asset_id {asset_id} already exists with different sha256; register under a new asset_id'
                    )

                prev_logical = db.execute(
                    '''
                    SELECT asset_id, sha256 FROM spatial_asset_registry
                    WHERE logical_name=? AND sha256!=? ORDER BY created_at_ms DESC LIMIT 1
                    ''',
                    (logical_name.strip(), actual_sha),
                ).fetchone()
                if prev_logical:
                    upgrade_notice = {
                        'logical_name': logical_name.strip(),
                        'previous_asset_id': prev_logical['asset_id'],
                        'previous_sha256': prev_logical['sha256'],
                        'new_asset_id': asset_id,
                        'new_sha256': actual_sha,
                        'auto_replaced_in_scenes': False,
                    }

                db.execute(
                    '''
                    INSERT OR IGNORE INTO spatial_asset_registry
                        (asset_id, logical_name, sha256, mime_type, size_bytes, license,
                         asset_source, origin_uri, author, credit_line, attribution_scope,
                         redistribution_allowed, lod_level, triangle_count, dimensions_m_json,
                         decoders_json, storage_path, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        asset_id,
                        logical_name.strip(),
                        actual_sha,
                        mime_type,
                        len(raw_bytes),
                        lic,
                        src,
                        origin_uri,
                        author.strip()[:160],
                        credit_line.strip()[:500],
                        attribution_scope.strip()[:80],
                        1 if redistribution_allowed else 0,
                        lod_level,
                        triangle_count,
                        json.dumps([float(x) for x in dims] if dims is not None else None),
                        json.dumps(dec_list),
                        storage_path_str,
                        now,
                    ),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

        record = self.get_asset(asset_id)
        if upgrade_notice:
            record['upgrade_notice'] = upgrade_notice
        return record

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        _check_id(asset_id, 'asset_id')
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT * FROM spatial_asset_registry WHERE asset_id=?',
                (asset_id,),
            ).fetchone()
            if not row:
                raise AssetGateError(f'Asset not found: {asset_id}')
            return self._row_to_asset(row)

    def search_assets(
        self,
        query: str,
        *,
        max_triangles: int = MAX_TRIANGLES,
        require_redistributable: bool = False,
        allow_paid_generation: bool = False,
    ) -> dict[str, Any]:
        """Search local ShapeRegistry and content-addressed AssetRegistry (read-only by default)."""
        if allow_paid_generation:
            raise AssetSecurityError(
                'Hosted paid asset generation (generate_asset) is disabled in read-only Asset Gate discovery'
            )
        q = str(query or '').strip().lower()
        local_shapes = []
        if self.shape_registry is not None and q:
            for cid, entry in self.shape_registry.catalog.items():
                hay = f"{cid} {entry.get('label', '')} {entry.get('category', '')} {' '.join(entry.get('aliases', []))}".lower()
                if q in hay:
                    local_shapes.append({
                        'source': 'shape_registry_local',
                        'component_id': cid,
                        'label': entry.get('label', cid),
                        'license': 'MIT',
                        'redistribution_allowed': True,
                    })

        with self.lock, self._connect() as db:
            rows = db.execute(
                'SELECT * FROM spatial_asset_registry WHERE triangle_count <= ? ORDER BY created_at_ms DESC',
                (int(max_triangles),),
            ).fetchall()
            registered = []
            for r in rows:
                item = self._row_to_asset(r)
                if require_redistributable and not item['redistribution_allowed']:
                    continue
                if not q or q in item['logical_name'].lower() or q in item['asset_id'].lower():
                    registered.append(item)

        return {
            'query': query,
            'local_shape_matches': local_shapes[:16],
            'registered_assets': registered[:32],
            'paid_generation_invoked': False,
        }

    @staticmethod
    def _row_to_asset(row: sqlite3.Row) -> dict[str, Any]:
        return {
            'asset_id': row['asset_id'],
            'logical_name': row['logical_name'],
            'sha256': row['sha256'],
            'mime_type': row['mime_type'],
            'size_bytes': int(row['size_bytes']),
            'license': row['license'],
            'asset_source': row['asset_source'],
            'origin_uri': row['origin_uri'],
            'author': row['author'],
            'credit_line': row['credit_line'],
            'attribution_scope': row['attribution_scope'],
            'redistribution_allowed': bool(row['redistribution_allowed']),
            'lod_level': row['lod_level'],
            'triangle_count': int(row['triangle_count']),
            'dimensions_m': json.loads(row['dimensions_m_json']),
            'decoders': json.loads(row['decoders_json']),
            'storage_path': row['storage_path'],
            'created_at_ms': int(row['created_at_ms']),
        }
