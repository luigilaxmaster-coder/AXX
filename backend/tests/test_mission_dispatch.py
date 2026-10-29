"""Reserved plan IDs cannot authorize a different command or bypass plan approval."""
from pathlib import Path
import tempfile
import unittest
from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService


class MissionDispatchTests(unittest.TestCase):
    def test_borrowed_step_id_cannot_write_before_parent_approval(self):
        self._poison(False)

    def test_borrowed_step_id_cannot_change_payload_of_running_parent(self):
        self._poison(True)

    def _poison(self, running):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                plan = learning.prepare_steps('Guardar aprobado.txt', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'approved.txt', 'content': 'original'}}], conversation_id='trial')
                if running:
                    plan.update(state='running', approved_hash=plan['plan_hash'])
                    plan['step_records'][0].update(state='running', resolved_inputs={'path': 'approved.txt', 'content': 'original'})
                    learning._save(plan)
                operation = plan['step_records'][0]['operation_id']
                commands.prepare('axx.artifact.write', {'path': 'poison.txt', 'content': 'unapproved'},
                                 operation_id=operation, conversation_id='trial')
                result = commands.execute(operation, approved=True)
                self.assertEqual(result['state'], 'failed', result)
                self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
                self.assertFalse((executor.workspace_root / 'poison.txt').exists())
                self.assertFalse((executor.workspace_root / 'approved.txt').exists())
            finally:
                learning.close(); commands.close(); executor.close()

    def test_real_approved_plan_still_dispatches_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, None)
            try:
                plan = learning.prepare_steps('Guardar ensayo', [{'command_id': 'axx.artifact.write',
                    'inputs': {'path': 'approved.txt', 'content': 'original'}}], conversation_id='trial')
                result = learning.execute(plan['operation_id'], approved=True)
                self.assertEqual(result['state'], 'succeeded', result)
                self.assertEqual((executor.workspace_root / 'approved.txt').read_text(), 'original')
            finally:
                learning.close(); commands.close(); executor.close()
