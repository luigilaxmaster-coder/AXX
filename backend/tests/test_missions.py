"""Mission views use the existing persisted plan and actual executor receipts."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService


class MissionTests(unittest.TestCase):
    def test_slow_plan_recovery_does_not_stall_local_anticipation(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            entered, release, continued = threading.Event(), threading.Event(), threading.Event()
            calls = []
            def slow():
                calls.append(1)
                entered.set()
                release.wait(15)
            class LocalPolicy:
                def tick(self):
                    if entered.is_set(): continued.set()
            learning.anticipation = LocalPolicy()
            try:
                with patch.object(learning, 'retry_waiting', side_effect=slow):
                    learning.start_recovery()
                    self.assertTrue(continued.wait(13), 'Local anticipation was blocked by provider recovery')
                    self.assertEqual(len(calls), 1, 'An in-flight recovery must not be queued twice')
                    release.set()
            finally:
                release.set()
                learning.close()
                commands.close()
                executor.close()

    def test_mission_persists_goal_scope_budget_and_stops_at_verified_result(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                plan = learning.prepare_steps('Guardar el ensayo y comprobarlo', [
                    {'command_id': 'axx.artifact.write', 'inputs': {'path': 'mission.txt', 'content': 'Ensayo'}},
                    {'command_id': 'axx.file.sha256', 'inputs': {}, 'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}
                ], conversation_id='mission-chat', project_id='project-a')
                mission = plan['mission']
                self.assertEqual(mission['scope'], {'project_id': 'project-a', 'task_id': 'mission-chat', 'resources': []})
                self.assertEqual(mission['pending_steps'], [0, 1])
                self.assertFalse(mission['completed'])
                self.assertEqual(mission['budget']['model_calls_used'], 0)
                completed = learning.execute(plan['operation_id'], approved=True)
                self.assertEqual(completed['state'], 'succeeded', completed)
                self.assertTrue(completed['mission']['completed'])
                self.assertEqual(completed['mission']['verified_steps'], [0, 1])
                self.assertEqual(completed['mission']['pending_steps'], [])
                self.assertFalse(completed['mission']['user_confirmed_usefulness'])
                count = len(executor.list_operations())
                learning.close()
                learning = ActionLearning(commands, None)
                restored = learning.get(plan['operation_id'])
                self.assertEqual(restored['mission']['mission_id'], plan['operation_id'])
                self.assertTrue(restored['mission']['completed'])
                learning.execute(plan['operation_id'], approved=True)
                self.assertEqual(len(executor.list_operations()), count)
            finally:
                learning.close()
                commands.close()
                executor.close()

    def test_dispatch_and_acceptance_do_not_complete_mission(self):
        plan = {'operation_id': 'm', 'request': 'Ensayo', 'state': 'running', 'steps': [{}],
                'step_records': [{'state': 'succeeded', 'result': {'state': 'succeeded', 'postconditions_passed': False}}],
                'postconditions_passed': True, 'plan_hash': 'p', 'approved_hash': 'p'}
        mission = ActionLearning._mission(plan)
        self.assertFalse(mission['completed'])
        self.assertEqual(mission['pending_steps'], [0])
        self.assertTrue(mission['permission']['exact_plan_approved'])
        self.assertFalse(mission['permission']['automatic_future_plans_authorized'])
