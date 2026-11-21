"""Unit tests for Phase 4 (PR-06 / MP-05): Motion/Simulation Studio deterministic freeze(t), TTS sync, and MP4 export."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.spatial.render_jobs import (
    RemoteExportPermissionError,
    export_motion_mp4,
    freeze_scene_at,
)


class MotionStudioTests(unittest.TestCase):
    def _sample_motion_scene(self) -> dict:
        return {
            'schema_version': '2.0',
            'document_id': 'motion-engine-001',
            'revision': 1,
            'mode': 'motion',
            'units': 'mm',
            'fidelity': 'conceptual',
            'coordinate_system': {'up_axis': 'Y', 'handedness': 'right', 'origin': [0, 0, 0]},
            'source': {'kind': 'user_spec', 'source_id': 'spec-mot-1', 'revision': 1},
            'objects': [
                {
                    'id': 'piston-1',
                    'name': 'Pistón Principal',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                    'transform': {'position': [0.0, 0.0, 0.0], 'rotation': [0.0, 0.0, 0.0], 'scale': [1.0, 1.0, 1.0]},
                },
                {
                    'id': 'housing-1',
                    'name': 'Camisa Exterior',
                    'representation': 'primitive',
                    'fidelity': 'conceptual',
                    'measured_source': 'assumed',
                    'transform': {'position': [0.0, 0.0, 0.0], 'rotation': [0.0, 0.0, 0.0], 'scale': [2.0, 2.0, 2.0]},
                },
            ],
            'assets': [],
            'timeline': {
                'duration_seconds': 2.0,
                'tracks': [
                    {
                        'track_id': 'sim-piston',
                        'kind': 'simulation',
                        'target_object_id': 'piston-1',
                        'start_time': 0.0,
                        'duration': 2.0,
                        'simulation_spec': {
                            'kind': 'piston_crank',
                            'frequency_hz': 2.0,
                            'crank_radius': 1.2,
                            'rod_length': 4.0,
                        },
                    },
                    {
                        'track_id': 'cut-housing',
                        'kind': 'cutaway',
                        'target_object_id': 'housing-1',
                        'start_time': 0.0,
                        'duration': 2.0,
                        'from_offset': 1.0,
                        'to_offset': 0.2,
                    },
                    {
                        'track_id': 'cam-orbit',
                        'kind': 'camera',
                        'start_time': 0.0,
                        'duration': 2.0,
                        'from_eye': [0.0, 3.0, 10.0],
                        'to_eye': [5.0, 4.0, 8.0],
                    },
                    {
                        'track_id': 'step-1',
                        'kind': 'teaching_step',
                        'start_time': 0.0,
                        'duration': 2.0,
                        'title': 'Carrera de compresión',
                        'narration': 'El pistón sube 12 cm a 25 °C dentro del cilindro.',
                        'focus': ['piston-1'],
                    },
                ],
            },
        }

    def test_mp_05_deterministic_freeze_at_timestamps_and_reproducible_mp4_export(self):
        scene = self._sample_motion_scene()

        # Verify freeze(t) is 100% deterministic for identical (t, seed) and varies across timestamps
        snap_a1 = freeze_scene_at(scene, 0.35, seed=77)
        snap_a2 = freeze_scene_at(scene, 0.35, seed=77)
        snap_b = freeze_scene_at(scene, 0.85, seed=77)

        self.assertEqual(snap_a1['state_sha256'], snap_a2['state_sha256'])
        self.assertNotEqual(snap_a1['state_sha256'], snap_b['state_sha256'])
        self.assertEqual(snap_a1['simulation_fidelity'], 'illustrative_not_fem_cfd')

        # Verify Spanish spoken text preparation on active narration cue
        cue = snap_a1['active_narration']
        self.assertIsNotNone(cue)
        self.assertIn('doce centímetros', cue['prepared_spoken_text'])
        self.assertIn('veinticinco grados Celsius', cue['prepared_spoken_text'])

        # Verify reproducible MP4 export
        with tempfile.TemporaryDirectory() as tmp:
            out_1 = Path(tmp) / 'motion-1.mp4'
            out_2 = Path(tmp) / 'motion-2.mp4'
            exp_1 = export_motion_mp4(scene, output_path=out_1, fps=5, seed=77)
            exp_2 = export_motion_mp4(scene, output_path=out_2, fps=5, seed=77)

            self.assertEqual(exp_1['mp4_sha256'], exp_2['mp4_sha256'])
            self.assertEqual(exp_1['frame_count'], 10)
            self.assertEqual(exp_1['frame_hashes'], exp_2['frame_hashes'])
            self.assertTrue(out_1.is_file())
            raw_mp4 = out_1.read_bytes()
            self.assertIn(b'ftypisom', raw_mp4[:32])
            self.assertIn(b'moov', raw_mp4)
            self.assertIn(b'mdat', raw_mp4)

    def test_remote_worker_export_requires_explicit_transfer_approval(self):
        scene = self._sample_motion_scene()
        with self.assertRaises(RemoteExportPermissionError):
            export_motion_mp4(scene, fps=2, remote_worker=True, remote_transfer_approved=False)

        approved = export_motion_mp4(scene, fps=2, remote_worker=True, remote_transfer_approved=True)
        self.assertEqual(approved['frame_count'], 4)


if __name__ == '__main__':
    unittest.main()
