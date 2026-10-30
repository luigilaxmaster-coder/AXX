"""Legacy procedures stay stored but cannot bypass durable task forgetting."""
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.memory import task_memory
from backend.memory.ai_memory_adapter import AiMemoryAdapter
from backend.memory.procedural_memory import ProceduralMemory
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService


class LegacyTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.db'
        self.memory = ProceduralMemory(self.path)
        self.db = sqlite3.connect(self.path)
        self.a, self.b = (task_memory.snapshot(self.db, task) for task in ('a', 'b'))

    def tearDown(self):
        self.memory.close()
        self.db.close()
        self.temp.cleanup()

    def recipe(self, name, scope=None, steps=1):
        return self.memory.register_recipe(name, name, [{'tool': 'system_telemetry', 'args': {}}] * steps,
                                           {}, memory_scope=scope)

    def pending(self):
        self.db.execute('BEGIN IMMEDIATE')
        state = task_memory.begin_forget(self.db, 'a', 'forget-a', 0)
        self.db.commit()
        return state

    def finish(self, state):
        result = self.memory.forget_task('a')
        self.db.execute('BEGIN IMMEDIATE')
        task_memory.finish_forget(self.db, state, result)
        self.db.commit()
        return result

    def test_unknown_bytes_preserved_quarantined_and_known_b_survives_reopen(self):
        legacy = self.recipe('legacy')
        self.recipe('known-a', self.a)
        self.recipe('known-b', self.b)
        legacy_bytes = self.db.execute('SELECT steps_json FROM recipes WHERE id=?', (legacy.id,)).fetchone()[0]
        state = self.pending()
        self.assertIsNone(self.memory.find_recipe('legacy'))
        self.assertIsNone(self.memory.find_recipe('known-a'))
        self.assertIsNotNone(self.memory.find_recipe('known-b'))
        self.finish(state)
        self.assertEqual(self.db.execute('SELECT steps_json FROM recipes WHERE id=?', (legacy.id,)).fetchone()[0], legacy_bytes)
        listed = {item['id']: item for item in self.memory.list_recipes()}
        self.assertTrue(listed['legacy']['requires_review'])
        self.assertFalse(listed['legacy']['auto_select'])
        self.memory.close()
        self.memory = ProceduralMemory(self.path)
        self.assertIsNotNone(self.memory.find_recipe('known-b'))
        self.assertIsNone(self.memory.find_recipe('legacy'))
        with self.assertRaises(ValueError): self.recipe('late-a', self.a)

    def test_cached_unknown_and_old_a_cannot_execute_after_barrier(self):
        legacy = self.recipe('legacy')
        a = self.recipe('known-a', self.a)
        self.pending()
        for recipe in (legacy, a):
            with self.subTest(recipe=recipe.id), patch('backend.actions.executor.ActionExecutor.execute_action') as execute:
                with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, object())
                execute.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM recipe_attempts').fetchone()[0], 0)

    def test_forget_between_steps_stops_next_effect_and_preserves_attempt_receipt(self):
        recipe = self.recipe('known-a', self.a, steps=2)
        memory = self.memory
        case = self
        class Executor:
            calls = 0
            def execute_action(executor, *args, **kwargs):
                case.assertFalse(memory.db.in_transaction, 'SQL writer must not span effects')
                executor.calls += 1
                case.finish(case.pending())
                return {'state': 'succeeded', 'evidence': {'observed': True}}
        executor = Executor()
        with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, executor, operation_id='fixed-attempt')
        self.assertEqual(executor.calls, 1)
        self.assertEqual(self.db.execute('SELECT outcome FROM recipe_attempts WHERE operation_id=?', ('fixed-attempt',)).fetchone()[0], 'failed')
        self.assertIsNotNone(self.db.execute('SELECT result_json FROM recipe_attempts WHERE operation_id=?', ('fixed-attempt',)).fetchone()[0])
        newer = self.recipe('known-a', task_memory.snapshot(self.db, 'a'))
        self.assertGreater(newer.version, recipe.version)

    def test_owned_adapter_filters_unknown_and_forgotten_pages_without_external_deletion_claim(self):
        self.recipe('legacy')
        self.recipe('known-a', self.a)
        self.recipe('known-b', self.b)
        adapter = AiMemoryAdapter()
        adapter.bind_task_memory(self.path)
        self.pending()
        with patch.object(adapter, '_tool') as rpc:
            self.assertIsNone(adapter.read_recipe_page('legacy'))
            self.assertIsNone(adapter.read_recipe_page('known-a', memory_scope=self.a))
            self.assertEqual(adapter.query_recipes('private legacy query'), [])
            self.assertFalse(adapter.write_recipe_page('known-a', 'late', memory_scope=self.a))
            rpc.assert_not_called()
        with patch.object(adapter, '_tool', return_value={'path': 'recipes/known-b.md', 'body': 'B kept'}) as rpc:
            self.assertEqual(adapter.read_recipe_page('known-b', memory_scope=self.b)['body'], 'B kept')
            rpc.assert_called_once()
        with patch.object(adapter, '_tool', return_value={'hits': [
            {'path': 'recipes/legacy.md', 'text': 'old'}, {'path': 'recipes/known-a.md', 'text': 'A'},
            {'path': 'recipes/known-b.md', 'text': 'B'}]}):
            self.assertEqual(adapter.query_recipes('B', memory_scope=self.b), [{'path': 'recipes/known-b.md', 'text': 'B'}])

    def test_context_rotation_with_same_generation_blocks_cached_b_and_late_adapter_read(self):
        with self.db:
            self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT,memory_context_required INTEGER)')
            self.db.execute('INSERT INTO chat_conversations VALUES (?,?,0)', ('b', 'before'))
        recipe = self.memory.register_recipe('known-b', 'known-b', [{'tool': 'system_telemetry', 'args': {}}], {},
                                             memory_scope=self.b, memory_context_id='before')
        adapter = AiMemoryAdapter()
        adapter.bind_task_memory(self.path)
        def read(*args):
            with self.db:
                self.db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?', ('after', 'b'))
            return {'path': 'recipes/known-b.md', 'body': 'late source text'}
        with patch.object(adapter, '_tool', side_effect=read):
            self.assertIsNone(adapter.read_recipe_page('known-b', memory_scope=self.b, memory_context_id='before'))
        self.assertIsNotNone(self.memory.find_recipe('known-b'))
        self.assertEqual([item['id'] for item in self.memory.list_recipes()], ['known-b'])
        with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, object())
        self.assertEqual(task_memory.snapshot(self.db, 'b'), self.b)
        with patch.object(adapter, '_tool', return_value={'path': 'recipes/known-b.md', 'body': 'B kept'}):
            self.assertEqual(adapter.read_recipe_page('known-b', memory_scope=self.b, memory_context_id='after')['body'], 'B kept')
        class Executor:
            def execute_action(executor, *args, **kwargs): return {'state': 'succeeded'}
        self.assertEqual(self.memory.execute_recipe(recipe, {}, Executor(), memory_scope=self.b,
            memory_context_id='after')['outcome'], 'succeeded')

    def test_command_dependency_survives_promotion_restart_and_forget_without_chat_link(self):
        executor = ActionExecutor(self.path, Path(self.temp.name) / 'artifacts')
        commands = CommandService(executor)
        try:
            prepared = commands.prepare('axx.artifact.write', {'path': 'b.txt', 'content': 'SYNTHETIC_A_TO_B'},
                conversation_id='b', memory_scope=self.b, _memory_dependencies=[self.a])
            done = commands.execute(prepared['operation_id'], approved=True)
            self.assertEqual(done['state'], 'succeeded', done)
            source = executor.get_operation(done['action_operation_id'])
            recipe = self.memory.register_recipe('derived-b', 'derived-b',
                [{'tool': source['tool_name'], 'args': source['inputs'] | {'path': '$inputs.path'}}],
                {'path': {'type': 'string', 'required': True}},
                memory_scope=done['memory_scope'], _memory_dependencies=done['memory_dependencies'])
            reused = self.memory.execute_recipe(recipe, {'path': str(executor.workspace_root / 'b-reused.txt')}, executor, operation_id='preserved-attempt')
            self.assertEqual(reused['outcome'], 'succeeded', reused)
            artifact = executor.workspace_root / 'b.txt'
            original = artifact.read_bytes()
            attempt = self.db.execute('SELECT * FROM recipe_attempts WHERE operation_id=?', ('preserved-attempt',)).fetchone()
            journal = self.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (done['operation_id'],)).fetchone()[0]
            self.recipe('independent-b', self.b)
            self.memory.close(); self.memory = ProceduralMemory(self.path)
            cached = self.memory.find_recipe('derived-b')
            self.assertEqual(cached.memory_dependencies, [self.a])
            self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_links'").fetchone())
            result = self.finish(self.pending())
            self.assertEqual(result['forgotten_recipes'], 1)
            self.assertEqual(task_memory.snapshot(self.db, 'b'), self.b)
            self.assertIsNone(self.memory.find_recipe('derived-b'))
            self.assertIsNotNone(self.memory.find_recipe('independent-b'))
            with self.assertRaises(ValueError): self.memory.execute_recipe(cached, {'path': str(executor.workspace_root / 'blocked.txt')}, executor, operation_id='blocked-after-forget')
            with self.assertRaises(ValueError):
                self.memory.register_recipe('late-b', 'late-b', recipe.steps, {}, memory_scope=self.b,
                    _memory_dependencies=done['memory_dependencies'])
            self.assertEqual(artifact.read_bytes(), original)
            self.assertEqual(self.db.execute('SELECT * FROM recipe_attempts WHERE operation_id=?', ('preserved-attempt',)).fetchone(), attempt)
            self.assertEqual(self.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (done['operation_id'],)).fetchone()[0], journal)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM recipe_attempts').fetchone()[0], 1)
        finally:
            commands.close(); executor.close()

    def test_transitive_adapter_result_is_not_published_after_source_forget(self):
        for method in ('read', 'query', 'write'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temp, ProceduralMemory(Path(temp) / 'state.db') as memory:
                path = Path(temp) / 'state.db'
                adapter = AiMemoryAdapter(data_dir=Path(temp) / 'ai-pages'); adapter.bind_task_memory(path)
                page = {'path': 'recipes/derived-b.md', 'body': 'SYNTHETIC_A_TO_B'}
                memory.register_recipe('derived-b', 'derived-b', [{'tool': 'system_telemetry', 'args': {}}], {},
                    memory_scope=self.b, _memory_dependencies=[self.a])
                def delayed(tool, arguments):
                    with memory.db:
                        memory.db.execute('BEGIN IMMEDIATE')
                        state = task_memory.begin_forget(memory.db, 'a', 'forget-a', 0)
                    memory.forget_task('a')
                    with memory.db:
                        memory.db.execute('BEGIN IMMEDIATE'); task_memory.finish_forget(memory.db, state, {})
                    if method == 'query': return {'hits': [{'path': page['path'], 'text': page['body']}]}
                    if method == 'write': return {'path': page['path'], 'page_id': 'synthetic'}
                    return dict(page)
                try:
                    with patch.object(adapter, '_tool', side_effect=delayed) as rpc:
                        if method == 'read': self.assertIsNone(adapter.read_recipe_page('derived-b', memory_scope=self.b))
                        elif method == 'query': self.assertEqual(adapter.query_recipes('synthetic', memory_scope=self.b), [])
                        else: self.assertFalse(adapter.write_recipe_page('derived-b', page['body'], memory_scope=self.b))
                        self.assertEqual(rpc.call_count, 1)
                    self.assertEqual(page['body'], 'SYNTHETIC_A_TO_B')
                    self.assertEqual(task_memory.snapshot(memory.db, 'b'), self.b)
                    with patch.object(adapter, '_tool') as rpc:
                        self.assertIsNone(adapter.read_recipe_page('derived-b', memory_scope=self.b))
                        self.assertFalse(adapter.write_recipe_page('derived-b', 'late', memory_scope=self.b))
                        rpc.assert_not_called()
                finally: memory.close()

    def test_dependency_snapshot_is_fixed_strict_and_checked_on_cached_recipe(self):
        dependencies = [dict(self.a)]
        recipe = self.memory.register_recipe('derived-b', 'derived-b', [{'tool': 'system_telemetry', 'args': {}}], {},
            memory_scope=self.b, _memory_dependencies=dependencies)
        dependencies[0]['task_id'] = 'changed'
        self.assertEqual(recipe.memory_dependencies, [self.a])
        recipe.memory_dependencies.clear()
        with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, object())
        for invalid in ([self.a] * 25, [self.a | {'extra': True}], [{'task_id': 'a', 'generation': True}], ['a']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.memory.register_recipe('invalid', 'invalid', [], {}, memory_scope=self.b, _memory_dependencies=invalid)
        with self.memory.db:
            self.memory.db.execute('UPDATE recipe_memory_scopes SET memory_dependencies_json=? WHERE recipe_id=?', ('{', 'derived-b'))
        self.assertIsNone(self.memory.find_recipe('derived-b'))

    def test_forgotten_page_identity_is_not_rebased_when_recipe_id_is_registered_again(self):
        original = self.memory.register_recipe('reused', 'reused', [{'tool': 'system_telemetry', 'args': {}}], {},
            memory_scope=self.b, _memory_dependencies=[self.a])
        self.finish(self.pending())
        current = self.recipe('reused', self.b)
        self.assertGreater(current.version, original.version)
        self.assertIsNotNone(self.memory.find_recipe('reused'))
        adapter = AiMemoryAdapter(data_dir=Path(self.temp.name) / 'ai-pages'); adapter.bind_task_memory(self.path)
        with patch.object(adapter, '_tool') as rpc:
            self.assertIsNone(adapter.read_recipe_page('reused', memory_scope=self.b))
            self.assertFalse(adapter.write_recipe_page('reused', 'old A page', memory_scope=self.b))
            rpc.assert_not_called()
        with patch.object(adapter, '_tool', return_value={'hits': [{'path': 'recipes/reused.md', 'text': 'old A page'}]}):
            self.assertEqual(adapter.query_recipes('synthetic', memory_scope=self.b), [])

    def test_retained_page_read_cannot_follow_a_new_recipe_version(self):
        self.recipe('reused', self.b)
        adapter = AiMemoryAdapter(data_dir=Path(self.temp.name) / 'ai-pages'); adapter.bind_task_memory(self.path)
        def replace(*args):
            self.recipe('reused', self.b)
            return {'path': 'recipes/reused.md', 'body': 'previous version'}
        with patch.object(adapter, '_tool', side_effect=replace):
            self.assertIsNone(adapter.read_recipe_page('reused', memory_scope=self.b))

    def test_forget_during_final_effect_keeps_receipt_but_does_not_publish_old_result(self):
        recipe = self.memory.register_recipe('derived-b', 'derived-b', [{'tool': 'system_telemetry', 'args': {}}], {},
            memory_scope=self.b, _memory_dependencies=[self.a])
        case = self
        class Executor:
            calls = 0
            def execute_action(executor, *args, **kwargs):
                executor.calls += 1
                case.finish(case.pending())
                return {'state': 'succeeded', 'evidence': {'observed': True}}
        executor = Executor()
        with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, executor, operation_id='finished-before-forget')
        self.assertEqual(executor.calls, 1)
        row = self.db.execute('SELECT outcome,result_json FROM recipe_attempts WHERE operation_id=?', ('finished-before-forget',)).fetchone()
        self.assertEqual(row[0], 'succeeded'); self.assertIsNotNone(row[1])
        with self.assertRaises(ValueError): self.memory.execute_recipe(recipe, {}, executor, operation_id='finished-before-forget')
        self.assertEqual(executor.calls, 1)

    def test_query_rechecks_prior_hit_when_another_hit_is_checked_after_forget(self):
        self.memory.register_recipe('derived-b', 'derived-b', [{'tool': 'system_telemetry', 'args': {}}], {},
            memory_scope=self.b, _memory_dependencies=[self.a])
        self.recipe('independent-b', self.b)
        adapter = AiMemoryAdapter(data_dir=Path(self.temp.name) / 'ai-pages'); adapter.bind_task_memory(self.path)
        admitted = adapter._admitted
        forgotten = False
        def check(recipe_id=None, *args, **kwargs):
            nonlocal forgotten
            if recipe_id == 'independent-b' and not forgotten:
                forgotten = True
                self.finish(self.pending())
            return admitted(recipe_id, *args, **kwargs)
        kept = {'path': 'recipes/independent-b.md', 'text': 'B only'}
        with patch.object(adapter, '_admitted', side_effect=check), patch.object(adapter, '_tool', return_value={'hits': [
            {'path': 'recipes/derived-b.md', 'text': 'SYNTHETIC_A_TO_B'}, kept]}):
            self.assertEqual(adapter.query_recipes('synthetic', memory_scope=self.b), [kept])

    def test_all_shared_connection_access_is_locked_during_two_thread_trace_churn(self):
        recipe = self.recipe('stable-b', self.b)
        memory, case = self.memory, self
        connection = memory.db
        class GuardedConnection:
            def execute(proxy, *args, **kwargs):
                case.assertTrue(memory.lock._is_owned(), 'Shared SQLite access must hold the repository lock')
                return connection.execute(*args, **kwargs)
            def close(proxy):
                case.assertTrue(memory.lock._is_owned(), 'SQLite close must hold the repository lock')
                return connection.close()
            def __getattr__(proxy, name): return getattr(connection, name)
            def __enter__(proxy): connection.__enter__(); return proxy
            def __exit__(proxy, *args): return connection.__exit__(*args)
        class Executor:
            calls = 0
            def execute_action(executor, *args, **kwargs):
                case.assertFalse(memory.lock._is_owned(), 'Do not hold the SQL lock across an effect')
                executor.calls += 1
                return {'state': 'succeeded'}
        memory.db = GuardedConnection()
        barrier, failures, executor = threading.Barrier(2), [], Executor()
        def writer():
            try:
                barrier.wait(3)
                for index in range(24): self.recipe('trace-b-' + str(index), self.b)
            except BaseException as error: failures.append(error)
        def reader():
            try:
                barrier.wait(3)
                for _ in range(24):
                    self.assertEqual(memory.find_recipe('stable-b').id, recipe.id)
                    self.assertTrue(memory.list_recipes())
                    self.assertEqual(memory.execute_recipe(recipe, {}, executor, operation_id='fixed-thread-replay')['outcome'], 'succeeded')
            except BaseException as error: failures.append(error)
        workers = [threading.Thread(target=target) for target in (writer, reader)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(10)
        memory.db = connection
        self.assertFalse(any(worker.is_alive() for worker in workers), 'Repository workers did not finish')
        self.assertEqual(failures, [])
        self.assertEqual(executor.calls, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM recipe_attempts').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
