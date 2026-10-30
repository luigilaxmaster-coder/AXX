"""Explicit resource selection crosses authenticated HTTP without inference."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class NoModel:
    def __init__(self):
        self.calls = 0

    def route(self, request):
        self.calls += 1
        raise AssertionError('An explicit resource selection must not call a provider')


class ResourceBindingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = NoModel()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.chats = ChatStore(self.executor.db_path)
        self.tasks = [self.chats.mutate('create', {'title': name})['id'] for name in ('Source A', 'Source B', 'Review')]
        self.files, self.bindings = {}, {}
        for role, project, task, content in zip(('path', 'other_path'), ('project-a', 'project-b'), self.tasks, (b'LEFT\x00\xff', b'RIGHT\x00\xff')):
            path = self.executor.workspace_root / project / 'input.bin'
            path.parent.mkdir()
            path.write_bytes(content)
            self.files[role] = (path, content)
            context = self.learning.skills.update_context(project, {'current_file': str(path),
                'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': task, 'source_id': 'explicit-fixture',
                    'expires_at': time.time() + 3600}}}, **self.scope(task))
            self.bindings[role] = {'project_id': project, 'field': 'current_file', 'revision': context['context_meta']['current_file']['revision']}
        self.skill_id = 'skill.explicit.compare'
        self.learning.skills.insert({'id': self.skill_id, 'version': 1, 'trigger': self.skill_id, 'title': 'Comparar archivos explícitos',
            'schema': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'other_path': {'type': 'string'}},
                'required': ['path', 'other_path']},
            'templates': [{'command_id': 'axx.file.compare', 'inputs': {'path': '{{path}}', 'other_path': '{{other_path}}'}}],
            'examples': [], 'project_id': '', 'environment': get_action_env_fingerprint(['axx.file.compare']),
            'checks': ['executor_postconditions'], 'provenance': {}, 'created_at': time.time(), 'executable': True})
        handler = type('ResourceBindingHandler', (AxxBridgeHandler,), {'executor': self.executor, 'commands': self.commands,
            'learning': self.learning, 'chats': self.chats})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.chats.close()
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def scope(self, task):
        chat = self.chats.get(task)
        return {'memory_scope': copy.deepcopy(chat['memory_scope']), 'memory_context_id': chat['context_id']}

    def request(self, route, body=None, *, auth=True):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.server.host_token
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + route,
            data=None if body is None else json.dumps(body, allow_nan=False).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            with response:
                return response.status, json.loads(response.read())

    def body(self, **extra):
        return {'text': self.skill_id, 'operation_id': 'http-explicit-resources', 'project_id': 'review-project',
            'conversation_id': self.tasks[2], **self.scope(self.tasks[2]), 'resource_bindings': copy.deepcopy(self.bindings), **extra}

    def propose(self, **extra):
        code, plan = self.request('learning/propose', self.body(**extra))
        self.assertEqual(code, 200, plan)
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.commands.operations(), [])
        return plan

    def test_authentication_and_strict_top_level_shape_precede_provider_and_effects(self):
        self.assertEqual(self.request('learning/propose', self.body(), auth=False)[0], 401)
        for invalid in (None, [], 'this and the other', True):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.request('learning/propose', self.body(resource_bindings=invalid))[0], 400)
        self.assertEqual(self.request('learning/propose', self.body(grant=True))[0], 400)
        self.assertEqual(self.request('learning/prepare', {'text': 'Compare', 'steps': [], 'resource_bindings': self.bindings})[0], 400)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.commands.operations(), [])

    def test_review_seals_two_origins_and_real_comparison_needs_exact_approval(self):
        plan = self.propose()
        for role, selector in self.bindings.items():
            captured = plan['resource_bindings'][role]
            self.assertEqual({key: captured[key] for key in selector}, selector)
            path, content = self.files[role]
            self.assertEqual(captured['input_version']['sha256'], hashlib.sha256(content).hexdigest())
            self.assertEqual(captured['input_version']['path'], path.relative_to(self.executor.workspace_root).as_posix())
        for task in self.tasks[:2]:
            self.assertIn(self.scope(task)['memory_scope'], plan['memory_dependencies'])
        approval = {'operation_id': plan['operation_id'], 'approved': True, 'plan_hash': 'stale', **self.scope(self.tasks[2])}
        self.assertEqual(self.request('learning/execute', approval)[0], 400)
        self.assertEqual(self.commands.operations(), [])
        if os.name == 'nt':
            code, final = self.request('learning/execute', approval | {'plan_hash': plan['plan_hash']})
            self.assertEqual(code, 200, final)
            self.assertEqual(final['state'], 'succeeded', final)
            output = final['step_records'][0]['result']['output']
            self.assertFalse(output['equal'])
            self.assertEqual([row['sha256'] for row in output['files']],
                [hashlib.sha256(content).hexdigest() for _, content in self.files.values()])
            self.assertEqual(len(self.commands.operations()), 1)
        else:
            # A platform without the native lease cannot silently compare mutable paths.
            self.request('learning/execute', approval | {'plan_hash': plan['plan_hash']})
            self.assertFalse(any(row.get('state') == 'succeeded' for row in self.commands.operations()))
        self.assertEqual(self.model.calls, 0)
        for path, content in self.files.values():
            self.assertEqual(path.read_bytes(), content)

    def test_empty_or_ambiguous_selection_cannot_fall_back_to_inference(self):
        for ordinal, bindings in enumerate(({}, {'path': self.bindings['path']}, {'path': 'this', 'other_path': 'the other'})):
            with self.subTest(bindings=bindings):
                code, plan = self.request('learning/propose', self.body(operation_id='ambiguous-' + str(ordinal), resource_bindings=bindings))
                self.assertEqual(code, 200, plan)
                self.assertEqual(plan['state'], 'needs_input', plan)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.commands.operations(), [])

    def test_same_operation_different_roles_and_client_authority_are_rejected(self):
        plan = self.propose()
        swapped = {'path': self.bindings['other_path'], 'other_path': self.bindings['path']}
        self.assertEqual(self.request('learning/propose', self.body(resource_bindings=swapped))[0], 400)
        forged = copy.deepcopy(self.bindings)
        forged['path']['sha256'] = '0' * 64
        code, rejected = self.request('learning/propose', self.body(operation_id='forged-resource', resource_bindings=forged))
        self.assertEqual(code, 200, rejected)
        self.assertEqual(rejected['state'], 'needs_input', rejected)
        code, replay = self.request('learning/plan?id=' + urllib.parse.quote(plan['operation_id']))
        self.assertEqual(code, 200, replay)
        self.assertEqual(replay['resource_bindings'], plan['resource_bindings'])
        self.assertEqual(replay['plan_hash'], plan['plan_hash'])
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.commands.operations(), [])

    def test_source_reconfirmation_invalidates_review_without_refreshing_snapshot(self):
        plan = self.propose()
        role = 'other_path'
        selector = self.bindings[role]
        code, changed = self.request('learning/context', {'project_id': selector['project_id'], 'conversation_id': self.tasks[1],
            **self.scope(self.tasks[1]), 'changes': {'current_file': str(self.files[role][0]),
                'context_meta': {'current_file': {'kind': 'confirmed_user', 'task_id': self.tasks[1]}}}})
        self.assertEqual(code, 200, changed)
        self.assertGreater(changed['context_meta']['current_file']['revision'], selector['revision'])
        code, current = self.request('learning/plan?id=' + urllib.parse.quote(plan['operation_id']))
        self.assertEqual(code, 200, current)
        self.assertEqual(current['state'], 'needs_input', current)
        self.assertIsNone(current.get('approved_hash'))
        self.assertEqual(current['resource_bindings'], plan['resource_bindings'])
        self.request('learning/execute', {'operation_id': plan['operation_id'], 'approved': True,
            'plan_hash': plan['plan_hash'], **self.scope(self.tasks[2])})
        self.assertEqual(self.commands.operations(), [])
        self.assertEqual(self.model.calls, 0)

    def test_forgetting_source_removes_binding_metadata_but_preserves_files(self):
        plan = self.propose(goal_spec={'intent': 'Comparar fuentes revisadas',
            'sources': [str(path) for path, _ in self.files.values()]})
        code, preview = self.request('learning/memory-preview', {'text': 'olvida lo que aprendiste de esta sesión',
            'task_id': self.tasks[0], 'project_id': 'project-a', 'operation_id': 'forget-bound-source', **self.scope(self.tasks[0])})
        self.assertEqual(code, 200, preview)
        self.assertEqual(preview['status'], 'ready', preview)
        code, forgotten = self.request('learning/memory-apply', {'change': preview['change'],
            'review_hash': preview['review_hash'], 'confirmed': True})
        self.assertEqual(code, 200, forgotten)
        code, current = self.request('learning/plan?id=' + urllib.parse.quote(plan['operation_id']))
        self.assertEqual(code, 200, current)
        self.assertTrue(current.get('memory_forgotten'), current)
        self.assertNotIn('resource_bindings', current)
        self.assertNotIn('resource_binding_selectors', current)
        row = self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (plan['operation_id'],)).fetchone()
        durable = json.loads(row[0])
        self.assertNotIn('resource_bindings', durable)
        self.assertNotIn('resource_binding_selectors', durable)
        self.assertEqual(durable['inputs'], {})
        self.assertTrue(all(step['inputs'] == {} for step in durable['steps']))
        self.assertTrue(all('inputs' not in reference for reference in durable['skill_versions']))
        self.assertTrue(all('resolved_inputs' not in record for record in durable['step_records']))
        pending, strings = [durable], []
        while pending:
            value = pending.pop()
            if isinstance(value, dict): pending.extend(value.values())
            elif isinstance(value, list): pending.extend(value)
            elif isinstance(value, str): strings.append(value)
        for path, _ in self.files.values():
            self.assertFalse(any(str(path) in value for value in strings))
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.commands.operations(), [])
        for path, content in self.files.values():
            self.assertEqual(path.read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
