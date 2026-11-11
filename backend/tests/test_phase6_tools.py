"""Phase 6 contracts: chat tool arguments, real CPU/RAM telemetry and group-context persistence."""
import tempfile
import unittest
from pathlib import Path

from backend.actions.executor import ActionExecutor
from backend.actions.tools import SystemTelemetryTool
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.connect import chat_tools


class FakeConnect:
    def __init__(self):
        self.calls = []

    def execute(self, body, chat_policy=None):
        self.calls.append(body)
        return {'state': 'succeeded', 'operation_id': body['operation_id'], 'postconditions_passed': True}

    def get_task(self, operation_id):
        return {'state': 'succeeded', 'operation_id': operation_id}


class ChatToolArgumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.addCleanup(self.executor.close)
        self.commands = CommandService(self.executor)
        self.addCleanup(self.commands.close)
        config = {'providers': [{'name': 'p', 'model': 'm', 'enabled': True, 'capabilities': ['text', 'tools']}]}
        self.provider, self.tools = chat_tools.catalog(self.commands, config, {'selection_mode': 'manual', 'provider_name': 'p', 'model': 'm'})
        self.connect = FakeConnect()

    def call(self, name, arguments):
        return chat_tools.dispatch(self.connect, [{'type': 'function', 'function': {'name': name, 'arguments': arguments}}],
                                   self.tools, 'req-1', {'conversation_id': 'c'})

    def test_catalog_is_the_bounded_registry_subset_and_documents_empty_arguments(self):
        self.assertEqual(set(self.tools), {'axx_system_telemetry', 'axx_architecture_status', 'axx_artifact_write'})
        self.assertIn('arguments es {}', self.tools['axx_system_telemetry'][1]['description'])
        self.assertIn('axx_system_telemetry', chat_tools.GUIDANCE)

    def test_parameterless_tool_ignores_schema_shaped_arguments_but_runs_with_empty_inputs(self):
        receipt = self.call('axx_system_telemetry', '{"type":"object","properties":{"content":"CPU"}}')
        self.assertEqual(receipt['state'], 'succeeded')
        self.assertEqual(self.connect.calls[-1]['inputs'], {})
        self.assertEqual(self.connect.calls[-1]['command_id'], 'axx.system.telemetry')

    def test_malformed_non_object_duplicate_and_unknown_calls_never_reach_the_executor(self):
        for name, arguments in [('axx_system_telemetry', '{"a":'), ('axx_system_telemetry', '[]'), ('axx_system_telemetry', '"x"'),
                                ('axx_system_telemetry', '{"a":1,"a":2}'), ('axx_shell_powershell', '{}'),
                                ('axx_system_telemetry', '{"channel":"desktop","approved":true}'),
                                ('axx_system_telemetry', '{"type":"object","approved":true}'),
                                ('axx_artifact_write', '{"path":"x.txt"}'),
                                ('axx_artifact_write', '{"path":"x.txt","content":"c","extra":1}')]:
            with self.subTest(name=name, arguments=arguments):
                receipt = self.call(name, arguments)
                self.assertEqual(receipt['state'], 'blocked')
                self.assertFalse(receipt['postconditions_passed'])
        self.assertEqual(self.connect.calls, [])

    def test_tool_with_parameters_keeps_strict_validation_and_valid_calls_pass(self):
        self.assertEqual(self.call('axx_artifact_write', '{"path":"x.txt","content":"c"}')['state'], 'succeeded')
        self.assertEqual(self.connect.calls[-1]['inputs'], {'path': 'x.txt', 'content': 'c'})
        self.assertEqual(self.connect.calls[-1]['origin'], 'axx-provider')

    def test_only_one_call_per_turn(self):
        calls = [{'type': 'function', 'function': {'name': 'axx_system_telemetry', 'arguments': '{}'}}] * 2
        self.assertEqual(chat_tools.dispatch(self.connect, calls, self.tools, 'req-2', {})['state'], 'blocked')


class TelemetryTests(unittest.TestCase):
    def test_cpu_and_memory_are_measured_not_invented(self):
        tool = SystemTelemetryTool()
        result = tool.execute({})
        self.assertTrue(result.success)
        out = result.output
        for key in ('cpu_percent', 'cpu_count', 'memory_percent', 'memory_used_mb', 'memory_total_mb'):
            self.assertIn(key, out)
        if out['cpu_percent'] is not None:
            self.assertTrue(0 <= out['cpu_percent'] <= 100)
        self.assertTrue(tool.verify_postconditions({}, result)[0])
        self.assertTrue(0 < out['memory_used_mb'] <= out['memory_total_mb'])

    def test_postconditions_reject_impossible_readings(self):
        tool = SystemTelemetryTool()
        good = tool.execute({})
        for field, value in (('cpu_percent', 250.0), ('memory_used_mb', good.output['memory_total_mb'] * 2)):
            bad = type(good)(success=True, output=dict(good.output, **{field: value}), evidence=good.evidence)
            self.assertFalse(tool.verify_postconditions({}, bad)[0], field)


class GroupPersistenceTests(unittest.TestCase):
    def test_group_assignment_rotates_context_survives_reopen_and_rejects_stale_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.db'
            store = ChatStore(path)
            cid = store.mutate('create', {'command_mode': 'ask'})['id']
            old = store.get(cid)
            group = store.mutate('group', {'title': 'Grupo'})
            ref = {'memory_scope': old['memory_scope'], 'memory_context_id': old['connect_id']}
            store.mutate('update', {'id': cid, 'group_id': group['id'], **ref})
            new = store.get(cid)
            self.assertEqual(new['group_id'], group['id'])
            self.assertNotEqual(new['connect_id'], old['connect_id'])
            with self.assertRaises(ValueError):
                store.mutate('save', {'id': cid, 'messages': [], 'draft': 'viejo', 'attachment': None, **ref})
            store.mutate('save', {'id': cid, 'messages': [], 'draft': 'nuevo', 'attachment': None,
                                  'memory_scope': new['memory_scope'], 'memory_context_id': new['connect_id']})
            store.close()
            reopened = ChatStore(path)
            try:
                row = reopened.get(cid)
                self.assertEqual((row['group_id'], row['draft'], row['connect_id']), (group['id'], 'nuevo', new['connect_id']))
            finally:
                reopened.close()


if __name__ == '__main__':
    unittest.main()
