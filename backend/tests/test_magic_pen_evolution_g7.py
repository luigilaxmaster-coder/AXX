"""Integration and non-regression tests for Phase 7 (PR-10 / Gate G7 / E2E-06): Magic Pen Evolution Integration."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.evolution_flags import FeatureDisabledError
from backend.magic_pen import MagicPenService
from backend.spatial.diorama_engine import evaluate_diorama_qa
from backend.spatial_pipeline import catalog_matches, parse_blueprint


class MagicPenEvolutionG7Tests(unittest.TestCase):
    def test_e2e_06_magic_pen_photo_to_cad_to_motion_and_flag_off_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = MagicPenService(tmp)
            try:
                # 1. With default flags OFF, Evolution 3.0 methods are blocked while legacy MagicPenService is intact
                with self.assertRaises(FeatureDisabledError):
                    service.build_cad_scene_v2({'task_id': 't1', 'units': 'mm', 'parts': []})

                # 2. Enable Phase 2, 3, 4, 5 flags for E2E-06
                for flag_id in ('magic_scene_v2', 'cad_worker_v1', 'motion_worker_v1', 'asset_gate_mcp_v1', 'diorama_v1'):
                    service.evolution_flags.set_flag(flag_id, True, actor='owner', reason='Gate G7 E2E-06 test')

                # 3. Simulate IdentifyContract blueprint parsing and ShapeRegistry local lookup (E2E-06)
                blueprint = parse_blueprint('''{
                    "objeto": "Soporte de eje con brida",
                    "categoria": "mecanico",
                    "descripcion": "Conjunto mecánico de brida y eje",
                    "vista": "tres cuartos",
                    "componentes": [
                        {"nombre": "Brida base", "forma": "cilindro", "proporcion": "base", "material": "acero"},
                        {"nombre": "Eje rotativo", "forma": "cilindro", "proporcion": "central", "material": "acero"}
                    ],
                    "proporcion_global": "2:1:1",
                    "simetria": "axial",
                    "buscar": ["brida", "eje", "tornillo"],
                    "dudas": ["profundidad exacta del chavetero trasero"]
                }''')
                matches = catalog_matches(service.shapes, blueprint)
                self.assertIsInstance(matches, list)
                self.assertEqual(len(blueprint['dudas']), 1)

                # 4. Generate verified parametric CAD solid (STEP + GLB) and store SceneDocument v2
                cad_res = service.build_cad_scene_v2({
                    'task_id': 'e2e06-assembly',
                    'units': 'mm',
                    'tolerance_mm': 0.01,
                    'parts': [
                        {
                            'part_id': 'flange-base',
                            'name': 'Brida Base',
                            'kind': 'flange',
                            'dimensions': {'radius': 50.0, 'inner_radius': 15.0, 'thickness': 12.0},
                            'dimension_sources': {'radius': 'documented', 'inner_radius': 'documented', 'thickness': 'documented'},
                            'position': [0.0, 0.0, 0.0],
                        },
                        {
                            'part_id': 'rotor-shaft',
                            'name': 'Eje Rotativo',
                            'kind': 'shaft',
                            'dimensions': {'radius': 14.5, 'length': 80.0},
                            'dimension_sources': {'radius': 'observed', 'length': 'documented'},
                            'position': [0.0, 0.0, 20.0],
                        },
                    ],
                })
                doc_id = cad_res['scene_document']['document_id']
                self.assertEqual(cad_res['scene_document']['fidelity'], 'cad_verified')
                self.assertTrue(Path(cad_res['step_path']).is_file())
                self.assertTrue(Path(cad_res['glb_path']).is_file())

                # 5. Apply incremental ScenePatch by base_revision=1 to add a deterministic motion timeline
                patched = service.patch_scene_v2({
                    'document_id': doc_id,
                    'base_revision': 1,
                    'operation_id': 'op-e2e06-timeline',
                    'target_object_ids': ['rotor-shaft'],
                    'allowed_paths': ['timeline'],
                    'changes': [
                        {
                            'op': 'timeline.update',
                            'timeline': {
                                'duration_seconds': 1.0,
                                'tracks': [
                                    {
                                        'track_id': 'tr-extract-shaft',
                                        'kind': 'transform',
                                        'target_object_id': 'rotor-shaft',
                                        'start_time': 0.0,
                                        'duration': 1.0,
                                        'from_position': [0.0, 0.0, 20.0],
                                        'to_position': [0.0, 0.0, 26.0],
                                    },
                                    {
                                        'track_id': 'tr-narration',
                                        'kind': 'teaching_step',
                                        'start_time': 0.0,
                                        'duration': 1.0,
                                        'title': 'Extracción axial',
                                        'narration': 'El eje avanza 6 mm sobre el eje Z.',
                                        'focus': ['rotor-shaft'],
                                    },
                                ],
                            },
                        }
                    ],
                })
                self.assertEqual(patched['revision'], 2)

                # 6. Freeze at t=0.5s and export reproducible MP4
                motion_out = service.freeze_and_export_motion_v2(
                    doc_id,
                    timestamp_seconds=0.5,
                    seed=101,
                    export_mp4=True,
                    fps=4,
                )
                shaft_pose = next(o for o in motion_out['frozen']['objects'] if o['id'] == 'rotor-shaft')
                self.assertAlmostEqual(shaft_pose['position'][2], 23.0, places=3)
                self.assertIn('seis milímetros', motion_out['frozen']['active_narration']['prepared_spoken_text'])
                self.assertTrue(Path(motion_out['mp4']['output_path']).is_file())

                # 7. Run per-entity Diorama/Animation QA on the patched scene
                qa = evaluate_diorama_qa(patched['document'])
                self.assertTrue(qa['passed'])

                # 8. Decisive rollback test (§19.6): disabling flags blocks v2 dispatches while preserving stored data and v1
                for flag_id in ('magic_scene_v2', 'cad_worker_v1', 'motion_worker_v1', 'asset_gate_mcp_v1', 'diorama_v1'):
                    service.evolution_flags.set_flag(flag_id, False, actor='owner', reason='Rollback to v0.22.52 mode')
                with self.assertRaises(FeatureDisabledError):
                    service.patch_scene_v2({
                        'document_id': doc_id,
                        'base_revision': 2,
                        'operation_id': 'op-blocked',
                        'target_object_ids': [],
                        'allowed_paths': ['timeline'],
                        'changes': [{'op': 'timeline.update', 'timeline': {'duration_seconds': 0, 'tracks': []}}],
                    })
            finally:
                service.close()


if __name__ == '__main__':
    unittest.main()
