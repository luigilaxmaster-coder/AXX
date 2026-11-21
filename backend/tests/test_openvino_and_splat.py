"""Unit tests for Phase 6 (PR-09 / Gate G6): Opt-in OpenVINO auxiliary provider and isolated Pixelart Splat mode."""
from __future__ import annotations

import unittest

from backend.spatial.openvino_and_splat import (
    OpenVinoPolicyError,
    SplatPrecisionConflictError,
    benchmark_auxiliary_task,
    build_pixelart_splat_preview,
    probe_openvino_runtime,
)


class OpenVinoAndSplatTests(unittest.TestCase):
    def test_gate_g6_openvino_probe_benchmark_and_manual_provider_preservation(self):
        probe = probe_openvino_runtime()
        self.assertTrue(probe['opt_in_only'])
        self.assertFalse(probe['replaces_manual_provider'])
        self.assertFalse(probe['supports_50b_100b_on_iris_xe'])

        # Disabled opt-in must reject execution
        with self.assertRaises(OpenVinoPolicyError):
            benchmark_auxiliary_task(opt_in_enabled=False)

        # 50B/100B model claim on local laptop must be rejected
        with self.assertRaises(OpenVinoPolicyError):
            benchmark_auxiliary_task(opt_in_enabled=True, requested_model_params_b=70.0)

        bench = benchmark_auxiliary_task(
            opt_in_enabled=True,
            manual_provider_selected='codex-subscription',
            requested_model_params_b=1.5,
        )
        self.assertTrue(bench['benchmark_passed'])
        self.assertEqual(bench['manual_provider_preserved'], 'codex-subscription')
        self.assertFalse(bench['silent_fallback_performed'])

    def test_splat_preview_works_on_diorama_and_rejects_precision_cad_or_kervan(self):
        conceptual_scene = {
            'schema_version': '2.0',
            'document_id': 'splat-demo-1',
            'revision': 1,
            'mode': 'conceptual',
            'units': 'm',
            'fidelity': 'conceptual',
            'coordinate_system': {'up_axis': 'Y', 'handedness': 'right', 'origin': [0, 0, 0]},
            'source': {'kind': 'user_spec', 'source_id': 's1', 'revision': 1},
            'objects': [
                {
                    'id': 'o1',
                    'name': 'Torre',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                }
            ],
            'assets': [],
            'timeline': {'duration_seconds': 0, 'tracks': []},
        }
        splat_doc = build_pixelart_splat_preview(conceptual_scene, pixel_grid_size=32)
        self.assertEqual(splat_doc['fidelity'], 'illustrative')
        self.assertEqual(splat_doc['objects'][0]['representation'], 'splat')
        self.assertTrue(splat_doc['metadata']['splat_renderer']['avatar_renderer_isolated'])

        # Reject precision CAD mode
        cad_scene = dict(conceptual_scene, mode='cad')
        with self.assertRaises(SplatPrecisionConflictError):
            build_pixelart_splat_preview(cad_scene)

        # Reject Kervan excluded assets
        with self.assertRaises(SplatPrecisionConflictError):
            build_pixelart_splat_preview(conceptual_scene, asset_source='kervan_excluded')


if __name__ == '__main__':
    unittest.main()
