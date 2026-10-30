"""Plan projections share real SQLite with forgetting, policy and budget writers."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory import task_memory


class NoInference:
    def route(self, request):
        raise AssertionError('Reading a plan must not invoke a model')


class LearningReadConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoInference())
        self.commands.learning = self.learning
        self.policy = AnticipationService(self.commands)
        self.learning.anticipation = self.policy
        self.chats = ChatStore(self.executor.db_path)
        self.a = self.chats.mutate('create', {'title': 'A'})['id']
        self.b = self.chats.mutate('create', {'title': 'B'})['id']
        self.plans = {}
        for task, secret in ((self.a, 'PRIVATE_A'), (self.b, 'PRIVATE_B')):
            chat = self.chats.get(task)
            self.plans[task] = self.learning.prepare_steps(secret,
                [{'command_id': 'axx.system.telemetry', 'inputs': {}}],
                conversation_id=task, memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])

    def tearDown(self):
        self.learning.db.set_trace_callback(None)
        self.learning.close(); self.policy.close(); self.chats.close()
        self.commands.close(); self.executor.close(); self.temp.cleanup()

    def trace_readers(self):
        violations, observed = [], []
        def trace(sql):
            if not threading.current_thread().name.startswith('plan-reader'):
                return
            observed.append(sql.split()[0])
            if not self.learning.lock._is_owned() or not self.policy.lock._is_owned():
                violations.append(sql[:100])
        self.learning.db.set_trace_callback(trace)
        return violations, observed

    def test_get_and_list_hold_both_locks_through_final_memory_projection(self):
        violations, observed = self.trace_readers()
        errors = []
        def read():
            try:
                self.learning.get(self.plans[self.a]['operation_id'])
                self.learning.list_plans()
                rows = self.learning.list_plans(conversation_id=self.a)
                self.assertEqual([row['operation_id'] for row in rows], [self.plans[self.a]['operation_id']])
                with self.assertRaises(ValueError):
                    self.learning.list_plans(conversation_id='missing-conversation')
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=read, name='plan-reader-lock-check', daemon=True)
        worker.start(); worker.join(10)
        self.assertFalse(worker.is_alive(), 'Plan projection deadlocked')
        self.assertEqual(errors, [])
        self.assertIn('SELECT', observed)
        self.assertIn('INSERT', observed)
        self.assertEqual(violations, [], 'Reader SQL escaped the learning/policy locks')

    def test_parallel_get_list_forget_budget_and_policy_remain_consistent(self):
        violations, observed = self.trace_readers()
        iterations = 12
        barrier = threading.Barrier(7)
        errors, samples = [], []
        old = self.chats.get(self.a)
        budget_plan = copy.deepcopy(self.plans[self.b])

        def readers(index, turn):
            if index % 2:
                rows = self.learning.list_plans()
                self.assertEqual(len(rows), 2)
            else:
                rows = [self.learning.get(self.plans[self.a if turn % 2 else self.b]['operation_id'])]
            for plan in rows:
                self.assertGreaterEqual(plan['model_calls_used'], 0)
                self.assertLessEqual(plan['model_calls_used'], plan['model_call_limit'])
                if plan.get('memory_forgotten'):
                    self.assertNotIn('PRIVATE_A', json.dumps(plan))
            samples.extend(rows)

        def forget(turn):
            if turn == 3:
                result = self.learning.forget_session(self.a, 'parallel-forget', old['memory_scope'],
                    chats=self.chats, memory_context_id=old['context_id'])
                self.assertEqual(result['state'], 'applied')
            else:
                with self.learning.lock:
                    task_memory.state(self.learning.db, self.a)

        def budget(turn):
            key = 'cancelled-before-dispatch-' + str(turn)
            self.learning._reserve_model_call(budget_plan, key, 'plan', single_request=True)
            # The test never dispatches upstream; settle the actual reservation
            # as that known zero-attempt outcome, without mocking any success.
            self.learning._settle_model_call(budget_plan, key,
                {'ok': False, 'error': {'upstream_attempts': 0, 'attempt_budget_used': 0}}, single_request=True)

        def policy(turn):
            self.policy.configure({'profiles': {'discreto': {'resources': {'model_call_limit': 2}}}})
            self.assertEqual(self.policy.budget_for_task(self.b)['model_call_limit'], 2)

        def run(action):
            try:
                for turn in range(iterations):
                    barrier.wait(10)
                    action(turn)
                    barrier.wait(10)
            except BaseException as error:
                errors.append(error)
                barrier.abort()

        actions = [lambda turn, index=index: readers(index, turn) for index in range(4)] + [forget, budget, policy]
        workers = [threading.Thread(target=run, args=(action,), name='plan-reader-' + str(index) if index < 4 else 'writer-' + str(index),
                                    daemon=True) for index, action in enumerate(actions)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(30)
        self.assertFalse(any(worker.is_alive() for worker in workers), 'Concurrent plan readers/writers deadlocked')
        self.assertEqual(errors, [])
        self.assertTrue(observed)
        self.assertEqual(violations, [], 'Shared SQLite connection used outside both locks')
        self.assertGreaterEqual(len(samples), iterations * 4)
        forgotten = self.learning.get(self.plans[self.a]['operation_id'])
        self.assertTrue(forgotten['memory_forgotten'])
        self.assertNotIn('PRIVATE_A', json.dumps(forgotten))
        current = self.learning.get(self.plans[self.b]['operation_id'])
        self.assertEqual(current['request'], 'PRIVATE_B')
        self.assertEqual(current['model_calls_used'], 0)
        self.assertEqual(current['model_calls_reserved'], 0)
        self.assertEqual(current['route_requests'], iterations)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.learning.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
