import tempfile
import unittest
from pathlib import Path

from backend.mobile.trust_store import MobileTrustStore, PairingError, CommandConflict


class MobileTrustStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MobileTrustStore(Path(self.temp.name) / "state.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_pairing_code_is_single_use_and_credentials_are_scoped(self):
        code = self.store.create_pairing(scopes={"query", "voice"}, now=100)

        device = self.store.consume_pairing(code, "Phone", now=101)

        self.assertTrue(self.store.authorize(device["credential"], "query"))
        self.assertFalse(self.store.authorize(device["credential"], "tools.control"))
        with self.assertRaises(PairingError):
            self.store.consume_pairing(code, "Other", now=101)

    def test_expired_pairing_and_revoked_credentials_are_rejected(self):
        code = self.store.create_pairing(scopes={"query"}, now=100)
        with self.assertRaises(PairingError):
            self.store.consume_pairing(code, "Phone", now=221)

        code = self.store.create_pairing(scopes={"query"}, now=300)
        device = self.store.consume_pairing(code, "Phone", now=301)
        self.store.revoke(device["device_id"])
        self.assertFalse(self.store.authorize(device["credential"], "query"))

    def test_command_retries_reuse_task_and_payload_changes_conflict(self):
        code = self.store.create_pairing(scopes={"query", "voice"}, now=100)
        device = self.store.consume_pairing(code, "Phone", now=101)
        first = self.store.admit_command(device["device_id"], "cmd-1", {"text": "hola"}, task_id="task-1")
        retry = self.store.admit_command(device["device_id"], "cmd-1", {"text": "hola"}, task_id="task-2")

        self.assertEqual(first["task_id"], "task-1")
        self.assertEqual(retry["task_id"], "task-1")
        self.assertTrue(retry["duplicate"])
        same = self.store.admit_command(device['device_id'], 'cmd-1', {'text':'hola'}, task_id='task-1')
        self.assertTrue(same['duplicate'])
        with self.assertRaises(CommandConflict):
            self.store.admit_command(device["device_id"], "cmd-1", {"text": "adiós"}, task_id="task-3")

    def test_restart_preserves_command_and_marks_uncertain_effect(self):
        device = self.store.consume_pairing(self.store.create_pairing(), 'Phone')
        admitted = self.store.admit_command(device['device_id'], 'one', {'text':'hi'})
        self.store.finish_command(admitted['task_id'], 'running')
        restarted = MobileTrustStore(self.store.db_path)
        restarted.recover_commands()
        self.assertEqual(restarted.command(device['device_id'], 'one')['state'], 'outcome_unknown')
        self.assertEqual(restarted.admit_command(device['device_id'], 'one', {'text':'hi'})['task_id'], admitted['task_id'])


if __name__ == "__main__":
    unittest.main()
