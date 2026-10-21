"""Unit tests for Identity Store and Preference Persistence.
Verifies:
  - axx-studio-v2 visual preferences persistence
  - Preservation of form, palette, dimensions, camera
  - Stripping of transient task states (thinking, countdown, etc.)
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.sync.identity_sync import IdentityStore

class IdentitySyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'identity.db'
        self.store = IdentityStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_save_and_retrieve_identity(self):
        prefs = {
            'form': 'Pearl',
            'palette': 'Opal',
            'roughness': 0.15,
            'camera': {'fov': 45, 'distance': 2.5}
        }
        self.assertTrue(self.store.save_studio_identity(prefs))
        saved = self.store.get_studio_identity()
        self.assertEqual(saved['form'], 'Pearl')
        self.assertEqual(saved['palette'], 'Opal')
        self.assertEqual(saved['camera']['fov'], 45)

    def test_transient_task_states_are_stripped(self):
        prefs = {
            'form': 'Bloom',
            'palette': 'Neon',
            'countdown_active': True,
            'temporary_state': 'thinking',
            'error_pulse': 1.0
        }
        self.assertTrue(self.store.save_studio_identity(prefs))
        saved = self.store.get_studio_identity()
        self.assertEqual(saved['form'], 'Bloom')
        self.assertNotIn('countdown_active', saved)
        self.assertNotIn('temporary_state', saved)
        self.assertNotIn('error_pulse', saved)

if __name__ == '__main__':
    unittest.main()
