"""Incremental ScenePatch CAS engine, inverse patches, undo/redo, and binary hash preservation (PR-03 / MP-02).

Enforces:
- CAS check on base_revision (409 stale_revision on mismatch).
- Whitelist validation on target_object_ids and allowed_paths.
- Immutable historical binary asset hashes: changing a geometry asset requires a new asset_id/sha256,
  never mutating an existing asset's sha256 in place.
- Computes exact inverse patches for deterministic undo/redo and returns per-object/timeline
  render invalidation sets instead of rebuilding the entire scene.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from backend.spatial.scene_document import (
    SceneDocumentError,
    SceneDocumentStore,
    StaleSceneRevisionError,
    _check_id,
    validate_scene_document_v2,
)

ALLOWED_PATCH_PATHS = frozenset({
    'name',
    'transform',
    'transform.position',
    'transform.rotation',
    'transform.scale',
    'properties',
    'geometry_asset_id',
    'fidelity',
    'measured_source',
    'diagram.nodes',
    'diagram.edges',
    'timeline',
    'assets',
})


def apply_scene_patch(
    store: SceneDocumentStore,
    patch: dict[str, Any],
    *,
    record_undo: bool = True,
    clear_redo: bool = True,
) -> dict[str, Any]:
    """Validate and apply an incremental ScenePatch with CAS revision checking."""
    if not isinstance(patch, dict):
        raise SceneDocumentError('ScenePatch must be an object')
    doc_id = _check_id(patch.get('document_id'), 'patch.document_id')
    base_rev = patch.get('base_revision')
    if type(base_rev) is not int or base_rev < 1:
        raise SceneDocumentError('patch.base_revision must be an integer >= 1')
    op_id = _check_id(patch.get('operation_id'), 'patch.operation_id')

    target_ids = patch.get('target_object_ids')
    if not isinstance(target_ids, list):
        raise SceneDocumentError('patch.target_object_ids must be a list')
    target_set = {_check_id(t, 'target_object_id') for t in target_ids}

    allowed_paths = patch.get('allowed_paths')
    if not isinstance(allowed_paths, list) or not allowed_paths:
        raise SceneDocumentError('patch.allowed_paths must be a non-empty list')
    for path_key in allowed_paths:
        if not isinstance(path_key, str) or (
            path_key not in ALLOWED_PATCH_PATHS and not path_key.startswith('properties.')
        ):
            raise SceneDocumentError(f'Path not permitted in ScenePatch: {path_key!r}')
    allowed_set = set(allowed_paths)

    changes = patch.get('changes')
    if not isinstance(changes, list) or not (1 <= len(changes) <= 256):
        raise SceneDocumentError('patch.changes must be a list of 1..256 operations')

    with store.lock, store._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            row = db.execute(
                'SELECT current_revision, document_json FROM spatial_scenes_v2 WHERE document_id=?',
                (doc_id,),
            ).fetchone()
            if not row:
                raise SceneDocumentError(f'SceneDocument {doc_id} not found')
            current_rev = int(row['current_revision'])
            if current_rev != base_rev:
                raise StaleSceneRevisionError(
                    f'stale_revision for {doc_id}: expected base_revision={base_rev}, actual={current_rev}'
                )

            current_doc = json.loads(row['document_json'])
            next_doc = copy.deepcopy(current_doc)

            existing_assets = {a['asset_id']: a for a in next_doc.get('assets', [])}
            objects_by_id = {o['id']: o for o in next_doc.get('objects', [])}

            inverse_changes: list[dict[str, Any]] = []
            invalidated_objects: set[str] = set()
            invalidated_timeline = False
            invalidated_diagram = False

            for change in changes:
                if not isinstance(change, dict):
                    raise SceneDocumentError('Each change item must be an object')
                op = change.get('op')

                if op == 'asset.register':
                    if 'assets' not in allowed_set:
                        raise SceneDocumentError("Change 'asset.register' requires 'assets' in allowed_paths")
                    asset = change.get('asset')
                    if not isinstance(asset, dict):
                        raise SceneDocumentError('asset.register requires an asset object')
                    aid = _check_id(asset.get('asset_id'), 'asset.asset_id')
                    if aid in existing_assets:
                        # MP-02: Never overwrite an existing asset hash with different bytes
                        if existing_assets[aid]['sha256'] != asset.get('sha256'):
                            raise SceneDocumentError(
                                f'Immutable binary asset violation (MP-02): cannot overwrite asset {aid} with different sha256'
                            )
                    else:
                        next_doc['assets'].append(copy.deepcopy(asset))
                        existing_assets[aid] = asset
                        inverse_changes.append({'op': 'asset.unregister', 'asset_id': aid})

                elif op == 'asset.unregister':
                    aid = _check_id(change.get('asset_id'), 'asset_id')
                    if aid in existing_assets:
                        old_asset = copy.deepcopy(existing_assets.pop(aid))
                        next_doc['assets'] = [a for a in next_doc['assets'] if a['asset_id'] != aid]
                        inverse_changes.append({'op': 'asset.register', 'asset': old_asset})

                elif op == 'object.update':
                    oid = _check_id(change.get('object_id'), 'change.object_id')
                    if oid not in target_set:
                        raise SceneDocumentError(f'Object {oid} is not listed in target_object_ids')
                    if oid not in objects_by_id:
                        raise SceneDocumentError(f'Target object {oid} does not exist in scene')
                    target_obj = objects_by_id[oid]
                    fields = change.get('fields')
                    if not isinstance(fields, dict) or not fields:
                        raise SceneDocumentError(f'object.update for {oid} requires non-empty fields')
                    old_fields: dict[str, Any] = {}
                    for k, v in fields.items():
                        if k == 'properties' and isinstance(v, dict):
                            if 'properties' not in allowed_set and not any(
                                f'properties.{pk}' in allowed_set for pk in v
                            ):
                                raise SceneDocumentError(f'Property update not in allowed_paths for {oid}')
                            old_props = copy.deepcopy(target_obj.get('properties', {}))
                            old_fields['properties'] = old_props
                            target_obj.setdefault('properties', {}).update(copy.deepcopy(v))
                        elif k == 'transform' and isinstance(v, dict):
                            if 'transform' not in allowed_set and not any(
                                f'transform.{tk}' in allowed_set for tk in v
                            ):
                                raise SceneDocumentError(f'Transform update not in allowed_paths for {oid}')
                            old_fields['transform'] = copy.deepcopy(target_obj.get('transform', {}))
                            target_obj.setdefault('transform', {}).update(copy.deepcopy(v))
                        else:
                            if k not in allowed_set:
                                raise SceneDocumentError(f'Field {k!r} not in allowed_paths for {oid}')
                            old_fields[k] = copy.deepcopy(target_obj.get(k))
                            target_obj[k] = copy.deepcopy(v)
                    inverse_changes.append({'op': 'object.update', 'object_id': oid, 'fields': old_fields})
                    invalidated_objects.add(oid)

                elif op == 'object.add':
                    obj = change.get('object')
                    if not isinstance(obj, dict):
                        raise SceneDocumentError('object.add requires an object dictionary')
                    oid = _check_id(obj.get('id'), 'object.id')
                    if oid not in target_set:
                        raise SceneDocumentError(f'Added object {oid} must be declared in target_object_ids')
                    if oid in objects_by_id:
                        raise SceneDocumentError(f'Object {oid} already exists')
                    new_obj = copy.deepcopy(obj)
                    next_doc['objects'].append(new_obj)
                    objects_by_id[oid] = new_obj
                    inverse_changes.append({'op': 'object.remove', 'object_id': oid})
                    invalidated_objects.add(oid)

                elif op == 'object.remove':
                    oid = _check_id(change.get('object_id'), 'change.object_id')
                    if oid not in target_set:
                        raise SceneDocumentError(f'Removed object {oid} must be declared in target_object_ids')
                    if oid not in objects_by_id:
                        raise SceneDocumentError(f'Object {oid} does not exist')
                    removed_obj = copy.deepcopy(objects_by_id.pop(oid))
                    next_doc['objects'] = [o for o in next_doc['objects'] if o['id'] != oid]
                    inverse_changes.append({'op': 'object.add', 'object': removed_obj})
                    invalidated_objects.add(oid)

                elif op == 'timeline.update':
                    if 'timeline' not in allowed_set:
                        raise SceneDocumentError("'timeline' must be in allowed_paths for timeline.update")
                    old_timeline = copy.deepcopy(next_doc['timeline'])
                    new_timeline = change.get('timeline')
                    if not isinstance(new_timeline, dict):
                        raise SceneDocumentError('timeline.update requires a timeline object')
                    next_doc['timeline'] = copy.deepcopy(new_timeline)
                    inverse_changes.append({'op': 'timeline.update', 'timeline': old_timeline})
                    invalidated_timeline = True

                elif op == 'diagram.update':
                    if 'diagram.nodes' not in allowed_set and 'diagram.edges' not in allowed_set:
                        raise SceneDocumentError('diagram.update requires diagram.nodes or diagram.edges in allowed_paths')
                    old_diagram = copy.deepcopy(next_doc.get('diagram') or {'nodes': [], 'edges': []})
                    new_diagram = change.get('diagram')
                    if not isinstance(new_diagram, dict):
                        raise SceneDocumentError('diagram.update requires a diagram object')
                    next_doc['diagram'] = copy.deepcopy(new_diagram)
                    inverse_changes.append({'op': 'diagram.update', 'diagram': old_diagram})
                    invalidated_diagram = True

                else:
                    raise SceneDocumentError(f'Unsupported ScenePatch operation: {op!r}')

            next_rev = current_rev + 1
            next_doc['revision'] = next_rev
            # Immutable source_revision check
            if next_doc['source'] != current_doc['source']:
                raise SceneDocumentError('ScenePatch cannot mutate immutable source metadata')

            validated_next = validate_scene_document_v2(next_doc)
            doc_json = json.dumps(validated_next, ensure_ascii=False, allow_nan=False)
            doc_sha = store._doc_hash(validated_next)
            now = store.clock()

            inverse_patch = {
                'document_id': doc_id,
                'base_revision': next_rev,
                'operation_id': f'inv-{op_id}',
                'target_object_ids': sorted(target_set),
                'allowed_paths': sorted(allowed_set | {'assets'}),
                'changes': list(reversed(inverse_changes)),
            }

            db.execute(
                '''
                UPDATE spatial_scenes_v2
                SET current_revision=?, mode=?, fidelity=?, document_json=?, document_sha256=?, updated_at_ms=?
                WHERE document_id=? AND current_revision=?
                ''',
                (
                    next_rev,
                    validated_next['mode'],
                    validated_next['fidelity'],
                    doc_json,
                    doc_sha,
                    now,
                    doc_id,
                    current_rev,
                ),
            )
            db.execute(
                '''
                INSERT INTO spatial_scene_revisions_v2
                    (document_id, revision, operation_id, document_json, document_sha256,
                     patch_json, inverse_patch_json, created_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    doc_id,
                    next_rev,
                    op_id,
                    doc_json,
                    doc_sha,
                    json.dumps(patch, ensure_ascii=False),
                    json.dumps(inverse_patch, ensure_ascii=False),
                    now,
                ),
            )

            stack_row = db.execute(
                'SELECT undo_stack_json, redo_stack_json FROM spatial_scene_undo_stack WHERE document_id=?',
                (doc_id,),
            ).fetchone()
            undo_stack = json.loads(stack_row['undo_stack_json']) if stack_row else []
            redo_stack = json.loads(stack_row['redo_stack_json']) if stack_row else []
            if record_undo:
                undo_stack.append({
                    'forward_patch': patch,
                    'inverse_patch': inverse_patch,
                    'from_revision': current_rev,
                    'to_revision': next_rev,
                })
            if clear_redo:
                redo_stack = []
            db.execute(
                'UPDATE spatial_scene_undo_stack SET undo_stack_json=?, redo_stack_json=? WHERE document_id=?',
                (
                    json.dumps(undo_stack, ensure_ascii=False),
                    json.dumps(redo_stack, ensure_ascii=False),
                    doc_id,
                ),
            )
            db.execute('COMMIT')
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise

    return {
        'document': validated_next,
        'revision': next_rev,
        'document_sha256': doc_sha,
        'inverse_patch': inverse_patch,
        'render_invalidation': {
            'full_rebuild': False,
            'invalidated_object_ids': sorted(invalidated_objects),
            'invalidated_timeline': invalidated_timeline,
            'invalidated_diagram': invalidated_diagram,
        },
    }


def undo_scene_patch(store: SceneDocumentStore, document_id: str, *, operation_id: str) -> dict[str, Any]:
    """Pop the latest reversible operation from undo_stack and apply its inverse patch."""
    _check_id(document_id, 'document_id')
    _check_id(operation_id, 'operation_id')
    with store.lock, store._connect() as db:
        row = db.execute(
            'SELECT undo_stack_json, redo_stack_json FROM spatial_scene_undo_stack WHERE document_id=?',
            (document_id,),
        ).fetchone()
        if not row:
            raise SceneDocumentError(f'SceneDocument {document_id} not found')
        undo_stack = json.loads(row['undo_stack_json'])
        redo_stack = json.loads(row['redo_stack_json'])
        if not undo_stack:
            raise SceneDocumentError(f'Nothing to undo for SceneDocument {document_id}')
        entry = undo_stack.pop()
        current_doc = store.get_document(document_id)
        inv = copy.deepcopy(entry['inverse_patch'])
        inv['base_revision'] = current_doc['revision']
        inv['operation_id'] = operation_id

    outcome = apply_scene_patch(store, inv, record_undo=False, clear_redo=False)
    redo_entry = {
        'forward_patch': entry['forward_patch'],
        'inverse_patch': entry['inverse_patch'],
    }
    redo_stack.append(redo_entry)
    with store.lock, store._connect() as db:
        with db:
            db.execute(
                'UPDATE spatial_scene_undo_stack SET undo_stack_json=?, redo_stack_json=? WHERE document_id=?',
                (json.dumps(undo_stack, ensure_ascii=False), json.dumps(redo_stack, ensure_ascii=False), document_id),
            )
    return outcome


def redo_scene_patch(store: SceneDocumentStore, document_id: str, *, operation_id: str) -> dict[str, Any]:
    """Re-apply the most recently undone patch from redo_stack."""
    _check_id(document_id, 'document_id')
    _check_id(operation_id, 'operation_id')
    with store.lock, store._connect() as db:
        row = db.execute(
            'SELECT undo_stack_json, redo_stack_json FROM spatial_scene_undo_stack WHERE document_id=?',
            (document_id,),
        ).fetchone()
        if not row:
            raise SceneDocumentError(f'SceneDocument {document_id} not found')
        redo_stack = json.loads(row['redo_stack_json'])
        if not redo_stack:
            raise SceneDocumentError(f'Nothing to redo for SceneDocument {document_id}')
        entry = redo_stack.pop()
        current_doc = store.get_document(document_id)
        fwd = copy.deepcopy(entry['forward_patch'])
        fwd['base_revision'] = current_doc['revision']
        fwd['operation_id'] = operation_id
        with db:
            db.execute(
                'UPDATE spatial_scene_undo_stack SET redo_stack_json=? WHERE document_id=?',
                (json.dumps(redo_stack, ensure_ascii=False), document_id),
            )
    return apply_scene_patch(store, fwd, record_undo=True, clear_redo=False)
