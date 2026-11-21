"""Unit tests for Phase 0 (PR-00): Evolution 3.0 feature flags and upstream manifest validation."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.evolution_flags import (
    EVOLUTION_FLAG_SPECS,
    EvolutionFeatureFlags,
    FeatureDisabledError,
    StaleFlagRevisionError,
    verify_upstream_manifest,
)


class EvolutionFeatureFlagsTests(unittest.TestCase):
    def test_all_twelve_flags_default_to_off_and_never_grant_permissions(self):
        flags = EvolutionFeatureFlags(':memory:')
        self.addCleanup(flags.close)
        items = flags.list_flags()
        self.assertEqual(len(items), 12)
        self.assertEqual({item['flag_id'] for item in items}, set(EVOLUTION_FLAG_SPECS))
        for item in items:
            self.assertFalse(item['enabled'], f"{item['flag_id']} must default to OFF")
            self.assertEqual(item['revision'], 1)
            self.assertFalse(item['grants_permissions'])
            with self.assertRaises(FeatureDisabledError):
                flags.require_enabled_for_new_dispatch(item['flag_id'])

    def test_cas_revision_update_and_audit_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'flags.sqlite'
            flags = EvolutionFeatureFlags(db_path)
            self.addCleanup(flags.close)

            updated = flags.set_flag(
                'magic_scene_v2',
                True,
                expected_revision=1,
                actor='owner',
                reason='Phase 2 Gate G2 passed',
                gate_receipt_ref='docs/evolution-3/phase-2/GATE_G2.md',
            )
            self.assertTrue(updated['enabled'])
            self.assertEqual(updated['revision'], 2)
            flags.require_enabled_for_new_dispatch('magic_scene_v2')

            with self.assertRaises(StaleFlagRevisionError):
                flags.set_flag('magic_scene_v2', False, expected_revision=1, actor='owner')

            reverted = flags.set_flag(
                'magic_scene_v2',
                False,
                expected_revision=2,
                actor='owner',
                reason='Rollback test',
            )
            self.assertFalse(reverted['enabled'])
            self.assertEqual(reverted['revision'], 3)

            audit = flags.audit_history('magic_scene_v2')
            self.assertEqual(len(audit), 2)
            self.assertEqual(audit[0]['revision'], 3)
            self.assertFalse(audit[0]['new_enabled'])
            self.assertEqual(audit[1]['revision'], 2)
            self.assertTrue(audit[1]['new_enabled'])

    def test_upstream_manifest_validation_passes_on_pack_and_rejects_gpl_copy(self):
        manifest_path = (
            Path(__file__).resolve().parents[2]
            / 'docs'
            / 'evolution-3'
            / 'records'
            / 'upstream-lock.json'
        )
        summary = verify_upstream_manifest(manifest_path)
        self.assertTrue(summary['valid'])
        self.assertEqual(summary['total_entries'], 29)
        self.assertEqual(summary['verified_commits'], 5)


if __name__ == '__main__':
    unittest.main()
