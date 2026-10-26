"""Pure/helper and cleanup regression tests; never run installed acceptance here."""
import hashlib
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('native_gateway_verifier',
    Path(__file__).resolve().parents[2] / 'scripts/verify-native-gateway.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def audit_row(receipt='r' * 43, *, server='owned-server', name=verifier.TOOL_NAME):
    return {'id': 'owned-invocation', 'mcpServerId': server, 'tool': {'name': name}, 'status': 'SUCCESS',
            'repeatCount': 1, 'output': {'isError': False, 'content': [
                {'type': 'text', 'text': json.dumps({'receipt': receipt})}]}}


class NativeGatewayVerifierTests(unittest.TestCase):
    def test_cursor_and_monitor_reads_use_and_restore_physical_dpi_context(self):
        active, calls = [False], []
        @contextmanager
        def physical():
            self.assertFalse(active[0])
            active[0] = True
            try:
                yield
            finally:
                active[0] = False
        class User:
            def GetPhysicalCursorPos(user, pointer):
                self.assertTrue(active[0])
                calls.append('cursor')
                pointer._obj.x, pointer._obj.y = 1362, 354
                return True
            def MonitorFromPoint(user, point, flag):
                self.assertTrue(active[0])
                self.assertEqual((point.x, point.y), (1362, 354))
                calls.append('monitor')
                return 1
            def GetMonitorInfoW(user, monitor, pointer):
                self.assertTrue(active[0])
                calls.append('bounds')
                rect = pointer._obj.rcMonitor
                rect.left, rect.top, rect.right, rect.bottom = 0, 0, 1920, 1080
                return True
        cursor = verifier.PhysicalCursor.__new__(verifier.PhysicalCursor)
        cursor.user = User()
        with patch('backend.magic_pen.physical_dpi_context', side_effect=physical):
            self.assertEqual(cursor.position(), (1362, 354))
            self.assertFalse(active[0])
            self.assertEqual(cursor.bounds((1362, 354)), (0, 0, 1920, 1080))
            self.assertFalse(active[0])
        self.assertEqual(calls, ['cursor', 'monitor', 'bounds'])

    def test_pointer_segment_stays_in_physical_monitor_at_edges_and_negative_origin(self):
        self.assertEqual(verifier.choose_pointer_target((10, 10), (0, 0, 100, 100)), (22, 10))
        self.assertEqual(verifier.choose_pointer_target((99, 10), (0, 0, 100, 100)), (87, 10))
        self.assertEqual(verifier.choose_pointer_target((-150, -30), (-200, -100, -100, 0)), (-138, -30))
        self.assertEqual(verifier.choose_pointer_target((4, 20), (0, 0, 8, 100)), (4, 32))
        for point, bounds in [((100, 10), (0, 0, 100, 100)), ((1, 1), (0, 0, 4, 4)),
                              ((40000, 40000), (39900, 39900, 40100, 40100))]:
            with self.subTest(point=point), self.assertRaises(verifier.VerificationError):
                verifier.choose_pointer_target(point, bounds)

    def test_audit_filters_both_server_and_tool_despite_upstream_filter_bug(self):
        owned = audit_row()
        rows = [owned, audit_row(server='other-server'), audit_row(name='unrelated_tool')]
        self.assertEqual(verifier.native_audit_rows(rows, 'owned-server'), [owned])
        self.assertEqual(verifier.native_audit_rows({'items': rows}, 'owned-server'), [owned])
        for malformed in [None, {'data': rows}, [None], rows * 10000]:
            with self.subTest(shape=type(malformed).__name__), self.assertRaises(verifier.VerificationError):
                verifier.audit_rows(malformed)

    def test_audit_receipt_hash_requires_exact_success_child_json_and_one_text(self):
        self.assertEqual(verifier.receipt_hash(audit_row()), hashlib.sha256(('r' * 43).encode()).hexdigest())
        for output in [{'isError': True, 'content': audit_row()['output']['content']},
                       {'content': [{'type': 'text', 'text': 'not JSON'}]},
                       {'content': [{'type': 'text', 'text': json.dumps({'receipt': 'short'})}]},
                       {'content': audit_row()['output']['content'] * 2},
                       {'content': [{'type': 'text', 'text': json.dumps({'content': audit_row()['output']['content']})}]}]:
            with self.subTest(output=output):
                self.assertIsNone(verifier.receipt_hash(dict(audit_row(), output=output)))

    def test_replay_signature_detects_duplicate_and_aggregated_invocations(self):
        row = audit_row()
        before = verifier.audit_signature([row])
        self.assertNotEqual(before, verifier.audit_signature([dict(row, repeatCount=2)]))
        self.assertNotEqual(before, verifier.audit_signature([row, dict(row, id='other-id')]))

    def test_only_exact_compose_app_container_can_be_paused(self):
        fields = ['a' * 64, '/' + verifier.CONTAINER_NAME,
                  {'com.docker.compose.project': 'axx-anythingmcp', 'com.docker.compose.service': 'app'},
                  {'Running': True, 'Paused': False}]
        payload = lambda values: '\n'.join(json.dumps(value) for value in values)
        self.assertEqual(verifier.checked_container(payload(fields)), ('a' * 64, False))
        for index, value in [(0, 'not-container-id'), (1, '/axx-anythingmcp-postgres-1'),
                             (2, {'com.docker.compose.project': 'foreign', 'com.docker.compose.service': 'app'}),
                             (2, {'com.docker.compose.project': 'axx-anythingmcp', 'com.docker.compose.service': 'postgres'}),
                             (3, {'Running': False, 'Paused': False})]:
            wrong = fields.copy()
            wrong[index] = value
            with self.subTest(field=index, value=value), self.assertRaises(verifier.VerificationError):
                verifier.checked_container(payload(wrong))

    def test_cancel_probe_unpauses_owned_container_even_when_prepare_fails(self):
        subject = verifier.InstalledVerifier('unused', '0.22.4')
        subject.cursor = Mock()
        subject.cursor.position.return_value = (40, 40)
        subject.cursor.bounds.return_value = (0, 0, 100, 100)
        subject.prepare = Mock(side_effect=verifier.VerificationError('owned_prepare_failure'))
        container = Mock()
        with patch.object(verifier, 'OwnedGatewayContainer', return_value=container), \
                self.assertRaisesRegex(verifier.VerificationError, 'owned_prepare_failure'):
            subject.cancel_with_gateway_paused()
        container.pause.assert_called_once()
        container.restore.assert_called_once()

    def test_audit_correlation_rejects_aggregated_repeat(self):
        subject = verifier.InstalledVerifier('unused', '0.22.4')
        receipt = verifier.receipt_hash(audit_row())
        subject.successes = [{'operation_id': 'owned', 'receipt_sha256': receipt}]
        subject.audit_snapshot = Mock(return_value=[dict(audit_row(), repeatCount=2)])
        with self.assertRaises(verifier.VerificationError):
            subject.correlate()

    def test_pointer_restoration_runs_after_move_verification_failure(self):
        subject = verifier.InstalledVerifier('unused', '0.22.4', True)
        subject.identify = Mock()
        subject.cursor = Mock()
        subject.cursor.position.side_effect = [(40, 40), (0, 0), (40, 40)]
        subject.cursor.bounds.return_value = (0, 0, 100, 100)
        subject.replay = Mock()
        subject.execute = Mock(return_value=('owned', {}))
        with self.assertRaises(verifier.VerificationError):
            subject.run()
        self.assertEqual(subject.execute.call_args_list[-1].args,
                         ('axx.desktop.pointer.move', {'x': 40, 'y': 40}))


if __name__ == '__main__':
    unittest.main()
