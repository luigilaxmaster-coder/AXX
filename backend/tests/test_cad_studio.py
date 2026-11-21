"""Unit and worker tests for Phase 3 (PR-05 / MP-03): CAD Studio, STEP/GLB congruence, and isolated worker recovery."""
from __future__ import annotations

from pathlib import Path
import json
import math
import struct
import tempfile
import unittest

from backend.spatial.cad_contracts import (
    CadContractError,
    CadWorkerTimeoutError,
    IsolatedCadWorker,
    execute_cad_geometry_task,
    validate_geometry_task,
    validate_glb_bytes,
    validate_step_bytes,
)


class CadStudioTests(unittest.TestCase):
    def test_physical_units_real_solids_rotation_and_distinct_meshes(self):
        for units, mm in [('mm', 1), ('cm', 10), ('m', 1000), ('in', 25.4), ('ft', 304.8)]:
            task = {'task_id': 'units-' + units, 'units': units, 'tolerance_mm': .01, 'parts': [
                {'part_id': 'box', 'kind': 'box', 'dimensions': {'width':2,'height':3,'depth':4},
                 'measured_source':'documented','position':[1,2,3], 'rotation':[0,0,math.pi/2]},
                {'part_id': 'tube', 'kind': 'tube', 'dimensions': {'radius':1,'inner_radius':.5,'length':5},
                 'measured_source':'documented','position':[10,0,0]}]}
            result = execute_cad_geometry_task(task)
            solids = validate_step_bytes(result['step_bytes'])['solids']
            self.assertAlmostEqual(solids[0]['volume_mm3'], 24 * mm**3, places=3)
            self.assertAlmostEqual(solids[1]['volume_mm3'], math.pi * .75 * 5 * mm**3, places=3)
            for actual, expected in zip(solids[0]['bounding_box'], [3*mm,2*mm,4*mm]):
                self.assertAlmostEqual(actual, expected, places=5)
            raw = result['glb_bytes']; size = struct.unpack_from('<I', raw, 12)[0]
            gltf = json.loads(raw[20:20+size])
            accessors = [mesh['primitives'][0]['attributes']['POSITION'] for mesh in gltf['meshes']]
            self.assertEqual(len(set(accessors)), 2, 'Each part needs its own geometry, not a repeated assembly')
            for mesh in gltf['meshes']:
                self.assertIn('NORMAL', mesh['primitives'][0]['attributes'])
            # An independent STEP reimport and actual binary positions agree in physical mm.
            self.assertTrue(result['congruence']['congruent'])

    def test_mp_03_parametric_step_glb_generation_and_congruence_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                'task_id': 'cad-bracket-001',
                'units': 'mm',
                'tolerance_mm': 0.01,
                'parts': [
                    {
                        'part_id': 'base-plate',
                        'name': 'Placa Base Mecanizada',
                        'kind': 'plate_with_holes',
                        'dimensions': {'width': 120.0, 'height': 80.0, 'thickness': 10.0, 'hole_diameter': 8.0},
                        'dimension_sources': {
                            'width': 'documented',
                            'height': 'documented',
                            'thickness': 'documented',
                            'hole_diameter': 'documented',
                        },
                        'position': [0.0, 0.0, 0.0],
                        'explode_vector': [0.0, 0.0, -25.0],
                    },
                    {
                        'part_id': 'drive-shaft',
                        'name': 'Eje Principal',
                        'kind': 'shaft',
                        'dimensions': {'radius': 12.5, 'length': 95.0},
                        'dimension_sources': {'radius': 'observed', 'length': 'documented'},
                        'position': [0.0, 0.0, 50.0],
                        'explode_vector': [0.0, 0.0, 35.0],
                    },
                ],
                'section_plane': {'axis': 'Z', 'offset': 5.0},
                'explode_factor': 0.5,
            }

            result = execute_cad_geometry_task(task, output_dir=tmp)
            self.assertTrue(result['congruence']['congruent'])
            self.assertEqual(result['congruence']['solid_count'], 2)
            self.assertLessEqual(result['congruence']['max_dimensional_delta'], task['tolerance_mm'])

            scene = result['scene_document']
            self.assertEqual(scene['fidelity'], 'cad_verified')
            self.assertEqual(scene['units'], 'mm')
            self.assertEqual(result['diagnostic_report']['engineering_verification_status'], 'engineering-unverified')

            step_info = validate_step_bytes(Path(result['step_path']).read_bytes())
            glb_info = validate_glb_bytes(Path(result['glb_path']).read_bytes())
            self.assertEqual(step_info['solid_count'], 2)
            self.assertEqual(glb_info['node_count'], 2)

    def test_inferred_dimensions_cap_fidelity_at_conceptual_and_block_code_injection(self):
        # Part with inferred dimension must NOT claim cad_verified (I-07)
        inferred_task = {
            'task_id': 'cad-photo-estimate',
            'units': 'mm',
            'parts': [
                {
                    'part_id': 'est-box',
                    'name': 'Carcasa estimada desde foto',
                    'kind': 'box',
                    'dimensions': {'width': 50.0, 'height': 30.0, 'depth': 20.0},
                    'dimension_sources': {'width': 'observed', 'height': 'observed', 'depth': 'inferred'},
                }
            ],
        }
        res = execute_cad_geometry_task(inferred_task)
        self.assertEqual(res['scene_document']['fidelity'], 'conceptual')
        self.assertTrue(res['diagnostic_report']['inferred_dimensions_present'])

        # Block arbitrary Python/runpy injection (I-08)
        with self.assertRaises(CadContractError):
            validate_geometry_task({
                'task_id': 'cad-malicious',
                'units': 'mm',
                'python_code': 'import os; os.system("calc")',
                'parts': [],
            })

    def test_isolated_cad_worker_execution_and_timeout_kill_recovery(self):
        worker = IsolatedCadWorker()  # Includes cold native CAD kernel startup; the hang test retains its 0.4 s deadline.
        with tempfile.TemporaryDirectory() as tmp:
            valid_task = {
                'task_id': 'cad-worker-ok',
                'units': 'mm',
                'parts': [
                    {
                        'part_id': 'flange-1',
                        'name': 'Brida DN50',
                        'kind': 'flange',
                        'dimensions': {'radius': 45.0, 'inner_radius': 20.0, 'thickness': 14.0},
                        'dimension_sources': {'radius': 'documented', 'inner_radius': 'documented', 'thickness': 'documented'},
                    }
                ],
            }
            res = worker.run_task(valid_task, output_dir=tmp)
            self.assertTrue(res['congruence']['congruent'])
            self.assertTrue(Path(res['step_path']).is_file())
            self.assertTrue(Path(res['glb_path']).is_file())

            # Simulate worker hang and verify kill + recovery for subsequent valid task
            hung_task = dict(valid_task, task_id='cad-worker-hang', _simulate_hang_seconds=5.0)
            with self.assertRaises(CadWorkerTimeoutError):
                worker.run_task(hung_task, output_dir=tmp, timeout_override=0.4)
            self.assertTrue(worker.last_crash_recovered)

            # Subsequent task after timeout recovery succeeds cleanly
            res_after = worker.run_task(dict(valid_task, task_id='cad-worker-recovered'), output_dir=tmp)
            self.assertTrue(res_after['congruence']['congruent'])


if __name__ == '__main__':
    unittest.main()
