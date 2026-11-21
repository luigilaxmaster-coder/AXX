"""Unit and security tests for Phase 5 (PR-07 & PR-08): Asset Gate Registry, Diorama QA, and Avatar Material Protection."""
from __future__ import annotations

import json
import unittest

from backend.spatial.asset_registry import (
    AssetGateError,
    AssetRegistry,
    AssetSecurityError,
)
from backend.spatial.cad_contracts import generate_parametric_glb_bytes, validate_geometry_task
from backend.spatial.diorama_engine import (
    AvatarMaterialProtectedError,
    apply_scene_material_or_diorama_mode,
    evaluate_diorama_qa,
)


class AssetGateAndDioramaTests(unittest.TestCase):
    def _sample_glb_bytes(self, width: float = 10.0) -> bytes:
        task = validate_geometry_task({
            'task_id': 'sample-asset',
            'units': 'mm',
            'parts': [
                {
                    'part_id': 'p1',
                    'name': 'Cubo',
                    'kind': 'box',
                    'dimensions': {'width': width, 'height': 10.0, 'depth': 10.0},
                }
            ],
        })
        return generate_parametric_glb_bytes(task)

    def test_mp_07_asset_gate_license_lod_decoders_and_upgrade_preservation(self):
        reg = AssetRegistry(':memory:')
        self.addCleanup(reg.close)
        glb_v1 = self._sample_glb_bytes(10.0)
        glb_v2 = self._sample_glb_bytes(20.0)

        # CC-BY-4.0 without credit_line must be rejected
        with self.assertRaises(AssetGateError):
            reg.register_asset(
                asset_id='gear-v1',
                logical_name='industrial_gear',
                raw_bytes=glb_v1,
                mime_type='model/gltf-binary',
                license_id='CC-BY-4.0',
                credit_line='',
            )

        # Remote URL download without explicit authorization must be blocked (MP-07)
        with self.assertRaises(AssetSecurityError):
            reg.register_asset(
                asset_id='remote-glb',
                logical_name='remote_mesh',
                raw_bytes=glb_v1,
                mime_type='model/gltf-binary',
                license_id='MIT',
                origin_uri='https://untrusted.example.com/mesh.glb',
                allow_remote_origin=False,
            )

        # Kervan excluded model must be rejected
        with self.assertRaises(AssetGateError):
            reg.register_asset(
                asset_id='kervan-1',
                logical_name='kervan_model',
                raw_bytes=glb_v1,
                mime_type='model/gltf-binary',
                license_id='Custom',
                asset_source='kervan_excluded',
            )

        # glTF JSON with path traversal in buffer URI must be blocked
        bad_gltf = json.dumps({
            'asset': {'version': '2.0'},
            'buffers': [{'uri': '../../secrets/credentials.bin', 'byteLength': 100}],
        }).encode('utf-8')
        with self.assertRaises(AssetSecurityError):
            reg.register_asset(
                asset_id='traversal-gltf',
                logical_name='evil_gltf',
                raw_bytes=bad_gltf,
                mime_type='model/gltf+json',
                license_id='MIT',
            )

        # Valid registration of v1 and v2 (E2E-12: preserves both hashes and emits upgrade_notice)
        rec_v1 = reg.register_asset(
            asset_id='gear-v1',
            logical_name='industrial_gear',
            raw_bytes=glb_v1,
            mime_type='model/gltf-binary',
            license_id='CC-BY-4.0',
            author='Open Mech',
            credit_line='Industrial Gear by Open Mech (CC-BY-4.0)',
            lod_level='lod1',
            triangle_count=12,
            decoders=['gltf'],
        )
        self.assertTrue(rec_v1['redistribution_allowed'])

        rec_v2 = reg.register_asset(
            asset_id='gear-v2',
            logical_name='industrial_gear',
            raw_bytes=glb_v2,
            mime_type='model/gltf-binary',
            license_id='CC-BY-4.0',
            author='Open Mech',
            credit_line='Industrial Gear v2 by Open Mech (CC-BY-4.0)',
            lod_level='lod0',
            triangle_count=12,
            decoders=['gltf'],
        )
        self.assertIn('upgrade_notice', rec_v2)
        self.assertEqual(rec_v2['upgrade_notice']['previous_asset_id'], 'gear-v1')
        self.assertFalse(rec_v2['upgrade_notice']['auto_replaced_in_scenes'])

        # Fab/Megascans source automatically forces redistribution_allowed=False
        fab_rec = reg.register_asset(
            asset_id='fab-rock-1',
            logical_name='quixel_rock',
            raw_bytes=glb_v1,
            mime_type='model/gltf-binary',
            license_id='Fab-Standard',
            asset_source='fab',
            redistribution_allowed=True,
        )
        self.assertFalse(fab_rec['redistribution_allowed'])

        # Read-only search blocks paid generation
        with self.assertRaises(AssetSecurityError):
            reg.search_assets('gear', allow_paid_generation=True)
        search_res = reg.search_assets('industrial_gear', require_redistributable=True)
        self.assertEqual(len(search_res['registered_assets']), 2)

    def test_mp_06_and_mp_08_avatar_material_protection_and_diorama_actor_qa(self):
        base_scene = {
            'schema_version': '2.0',
            'document_id': 'diorama-scene-001',
            'revision': 1,
            'mode': 'conceptual',
            'units': 'm',
            'fidelity': 'conceptual',
            'coordinate_system': {'up_axis': 'Y', 'handedness': 'right', 'origin': [0, 0, 0]},
            'source': {'kind': 'user_spec', 'source_id': 'dio-1', 'revision': 1},
            'objects': [
                {
                    'id': 'actor-ok',
                    'name': 'Actor Móvil',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                    'transform': {'position': [0.0, 0.0, 0.0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]},
                },
            ],
            'assets': [],
            'timeline': {
                'duration_seconds': 2.0,
                'tracks': [
                    {
                        'track_id': 'tr-move',
                        'kind': 'transform',
                        'target_object_id': 'actor-ok',
                        'start_time': 0.0,
                        'duration': 2.0,
                        'from_position': [0.0, 0.0, 0.0],
                        'to_position': [4.0, 0.0, 0.0],
                    }
                ],
            },
        }

        # MP-06: Attempting to apply Codevember or Diorama material to main_avatar or organic_tendrils must fail
        for protected in ('main_avatar', 'organic_tendrils', 'avatar_hitmask', 'obsidian_core'):
            with self.assertRaises(AvatarMaterialProtectedError):
                apply_scene_material_or_diorama_mode(
                    base_scene,
                    target_surface=protected,
                    diorama_preset='toon_diorama',
                )

        # Toggle on and off on magic_pen_scene works and restores mode cleanly
        diorama_on = apply_scene_material_or_diorama_mode(
            base_scene,
            target_surface='magic_pen_scene',
            diorama_preset='toon_diorama',
            codevember_material='raymarch_sdf_surface',
            enabled=True,
        )
        self.assertEqual(diorama_on['mode'], 'diorama')
        self.assertTrue(diorama_on['metadata']['avatar_state_untouched'])

        diorama_off = apply_scene_material_or_diorama_mode(
            diorama_on,
            target_surface='magic_pen_scene',
            enabled=False,
        )
        self.assertEqual(diorama_off['mode'], 'conceptual')
        self.assertNotIn('diorama_preset', diorama_off.get('metadata', {}))

        # MP-08: QA passes on well-behaved moving actor
        qa_ok = evaluate_diorama_qa(diorama_on)
        self.assertTrue(qa_ok['passed'])

        # MP-08: Detect frozen actor, teleporting actor, offscreen actor, and missing CC-BY credit
        bad_scene = {
            **base_scene,
            'objects': [
                {
                    'id': 'actor-frozen',
                    'name': 'Congelado',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                    'transform': {'position': [1.0, 1.0, 1.0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]},
                },
                {
                    'id': 'actor-teleport',
                    'name': 'Teleport',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                    'transform': {'position': [0.0, 0.0, 0.0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]},
                },
            ],
            'assets': [
                {
                    'asset_id': 'uncredited-ccby',
                    'sha256': 'a' * 64,
                    'mime_type': 'model/gltf-binary',
                    'size_bytes': 1024,
                    'license': 'CC-BY-4.0',
                    'credit_line': '',
                }
            ],
            'timeline': {
                'duration_seconds': 1.0,
                'tracks': [
                    {
                        'track_id': 'tr-frozen',
                        'kind': 'transform',
                        'target_object_id': 'actor-frozen',
                        'start_time': 0.0,
                        'duration': 1.0,
                        'from_position': [1.0, 1.0, 1.0],
                        'to_position': [1.0, 1.0, 1.0],
                    },
                    {
                        'track_id': 'tr-teleport',
                        'kind': 'transform',
                        'target_object_id': 'actor-teleport',
                        'start_time': 0.0,
                        'duration': 0.1,
                        'from_position': [0.0, 0.0, 0.0],
                        'to_position': [50.0, 0.0, 0.0],
                    },
                ],
            },
        }
        qa_bad = evaluate_diorama_qa(bad_scene)
        self.assertFalse(qa_bad['passed'])
        self.assertEqual(qa_bad['frozen_actors'], ['actor-frozen'])
        self.assertEqual(qa_bad['teleported_actors'], ['actor-teleport'])
        self.assertEqual(qa_bad['offscreen_actors'], ['actor-teleport'])
        self.assertEqual(qa_bad['missing_credits'], ['uncredited-ccby'])


if __name__ == '__main__':
    unittest.main()
