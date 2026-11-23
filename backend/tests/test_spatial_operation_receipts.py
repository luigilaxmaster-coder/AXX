"""Retry, restart and history atomicity against the actual SQLite scene store."""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from backend.spatial.scene_document import SceneDocumentStore, SceneDocumentError, import_presentation_plan_v1
from backend.spatial.patches import apply_scene_patch, undo_scene_patch, redo_scene_patch


class SpatialOperationTests(unittest.TestCase):
    def test_retries_restart_collisions_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'scenes.db'
            store = SceneDocumentStore(path)
            other = SceneDocumentStore(path)
            try:
                store.create_document(import_presentation_plan_v1({'scene': {'objects': [
                    {'id': 'part', 'shape': 'box', 'size': [1, 2, 3]}]}}, document_id='s', source_id='capture'))
                patch = {'document_id': 's', 'base_revision': 1, 'operation_id': 'paint',
                         'target_object_ids': ['part'], 'allowed_paths': ['properties'], 'changes': [
                             {'op': 'object.update', 'object_id': 'part', 'fields': {'properties': {'color': '#ff0000'}}}]}
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda svc: apply_scene_patch(svc, patch), [store, other]))
                self.assertEqual(results[0], results[1])
                self.assertEqual(store.get_document('s')['revision'], 2)
                bad = copy.deepcopy(patch)
                bad['changes'][0]['fields']['properties']['color'] = '#00ff00'
                with self.assertRaisesRegex(SceneDocumentError, 'different'):
                    apply_scene_patch(store, bad)
                undone = undo_scene_patch(store, 's', operation_id='undo-paint')
                self.assertEqual(undone['document']['objects'][0]['properties']['color'], '#438ee8')
                self.assertEqual(undo_scene_patch(other, 's', operation_id='undo-paint'), undone)
                redone = redo_scene_patch(store, 's', operation_id='redo-paint')
                self.assertEqual(redone['revision'], 4)
                self.assertEqual(redo_scene_patch(other, 's', operation_id='redo-paint'), redone)
                self.assertEqual(apply_scene_patch(other, patch), results[0])
                self.assertEqual(store.get_document('s')['revision'], 4)
                limited = {'document_id': 's', 'base_revision': 4, 'operation_id': 'limited',
                           'target_object_ids': ['part'], 'allowed_paths': ['properties.color'], 'changes': [
                               {'op': 'object.update', 'object_id': 'part',
                                'fields': {'properties': {'color': '#000000', 'unexpected': True}}}]}
                with self.assertRaises(SceneDocumentError):
                    apply_scene_patch(store, limited)
                limited['operation_id'] = 'add-property'
                limited['allowed_paths'] = ['properties']
                apply_scene_patch(store, limited)
                undo_scene_patch(store, 's', operation_id='undo-property')
                self.assertNotIn('unexpected', store.get_document('s')['objects'][0]['properties'])
            finally:
                store.close(); other.close()
            reopened = SceneDocumentStore(path)
            try:
                self.assertEqual(apply_scene_patch(reopened, patch), results[0])
                self.assertEqual(reopened.get_document('s')['revision'], 6)
                with self.assertRaisesRegex(SceneDocumentError, 'another action'):
                    undo_scene_patch(reopened, 's', operation_id='redo-paint')
            finally:
                reopened.close()
