import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService


class RemoteConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)

    def tearDown(self):
        self.commands.close()
        self.executor.close()
        self.tmp.cleanup()

    def prepare(self, op='test-op'):
        return self.commands.prepare('axx.system.telemetry', {}, operation_id=op, conversation_id='telegram', command_mode='ask')

    def test_review_and_confirmation_dispatch_exactly_once(self):
        self.prepare()
        review = self.commands.remote_review('test-op')
        self.assertTrue(review['eligible'])
        self.assertEqual(review['state'], 'awaiting_approval')
        self.assertEqual(review['inputs'], {})
        auth = Mock(return_value=True)
        action = {'state':'succeeded', 'postconditions_passed':True, 'output':{}, 'evidence':{}, 'duration_ms':1}
        with patch.object(self.executor, 'execute_action', return_value=action) as dispatch:
            result = self.commands.confirm_remote('test-op', review['plan_hash'], auth)
            self.assertEqual(result['state'], 'succeeded')
            self.assertEqual(auth.call_count, 2)
            with self.assertRaises(ValueError):
                self.commands.confirm_remote('test-op', review['plan_hash'], auth)
            dispatch.assert_called_once()

    def test_reserved_and_nonstatic_never_eligible(self):
        self.commands.prepare('axx.shell.cmd', {'script':'echo hi'}, operation_id='shell', command_mode='ask')
        self.assertEqual(self.commands.remote_review('shell')['reason'], 'PC_APPROVAL_REQUIRED')
        self.commands.cancel('shell')
        self.prepare('learn-test')
        self.assertEqual(self.commands.remote_review('learn-test')['reason'], 'PLAN_RESERVED')
        self.commands.cancel('learn-test')
        self.prepare('generated-metadata')
        self.commands.commands['axx.system.telemetry']['source'] = {'kind':'generated'}
        self.assertEqual(self.commands.remote_review('generated-metadata')['reason'], 'NOT_STATIC_EXECUTABLE')

    def test_hash_input_and_live_catalog_change_fail_closed(self):
        self.prepare()
        review = self.commands.remote_review('test-op')
        self.commands.commands['axx.system.telemetry']['risk'] = 'local_content_read'
        with patch.object(self.executor, 'execute_action') as dispatch:
            with self.assertRaises(ValueError):
                self.commands.confirm_remote('test-op', review['plan_hash'], lambda: True)
            dispatch.assert_not_called()

    def test_changed_inputs_cannot_confirm_prior_review(self):
        self.commands.prepare('axx.desktop.open_url', {'url':'https://example.org'}, operation_id='url', command_mode='ask')
        review = self.commands.remote_review('url')
        with self.commands.lock:
            row = self.commands.get('url')
            row['inputs'] = {'url':'https://example.com'}
            self.commands.db.execute('UPDATE command_runs SET result_json=? WHERE operation_id=?', (json.dumps(row), 'url'))
            self.commands.db.commit()
        with patch.object(self.executor, 'execute_action') as dispatch:
            with self.assertRaises(ValueError):
                self.commands.confirm_remote('url', review['plan_hash'], lambda: True)
            dispatch.assert_not_called()

    def test_expired_cancelled_and_revoked_do_not_dispatch(self):
        for scenario in ('expired', 'cancelled', 'revoked'):
            with self.subTest(scenario=scenario):
                op = 'op-' + scenario
                self.prepare(op)
                review = self.commands.remote_review(op)
                if scenario == 'expired':
                    self.commands.db.execute('UPDATE command_runs SET expires_at=0 WHERE operation_id=?', (op,))
                    self.commands.db.commit()
                if scenario == 'cancelled':
                    self.commands.cancel(op)
                with patch.object(self.executor, 'execute_action') as dispatch:
                    with self.assertRaises(ValueError):
                        self.commands.confirm_remote(op, review['plan_hash'], lambda: False if scenario == 'revoked' else True)
                    dispatch.assert_not_called()
                if scenario == 'revoked': self.commands.cancel(op)

    def test_revocation_at_dispatch_boundary_fails_without_effect(self):
        self.prepare()
        review = self.commands.remote_review('test-op')
        auth = Mock(side_effect=[True, False])
        with patch.object(self.executor, 'execute_action') as dispatch:
            result = self.commands.confirm_remote('test-op', review['plan_hash'], auth)
        self.assertEqual(result['state'], 'failed')
        dispatch.assert_not_called()
        self.assertEqual(auth.call_count, 2)


if __name__ == '__main__':
    unittest.main()
