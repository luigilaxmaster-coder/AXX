"""Race regression separate from the presealed ZIP holdout.

The only injected behavior is a real source write at executor entry. Actual
command execution and independent output inspection remain unmocked.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.tests.test_goal_progress_holdout import FIXTURE, NoModel


class GoalProgressInputRaceTests(unittest.TestCase):
    def test_changed_source_at_executor_entry_never_reaches_bundle(self):
        case = json.loads(FIXTURE.read_bytes())['cases'][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = ActionExecutor(root / 'state.db', root / 'artifacts')
            commands = CommandService(executor)
            learning = ActionLearning(commands, NoModel())
            commands.learning = learning
            try:
                workspace = executor.workspace_root
                goal = {'intent': case['intent'], 'criteria': [{'id': case['criterion_id'], 'kind': 'file_bundle',
                    'parameters': {'paths': [row['path'] for row in case['sources']],
                                   'destination': case['destination'], 'archive_name': case['archive_name']}}]}
                steps = [{'command_id': 'axx.artifact.write', 'inputs': {'path': row['path'], 'content': row['text']}}
                         for row in case['sources']]
                prefix = learning.prepare_steps(case['intent'], steps, 'zip-dispatch-version-race', goal_spec=goal)
                pending = learning.execute(prefix['operation_id'], approved=True, plan_hash=prefix['plan_hash'])
                self.assertEqual(pending['state'], 'goal_pending')
                prefix_receipts = copy.deepcopy(pending['step_records'])
                candidate = pending['goal_progress']
                prepared = learning.prepare_goal_progress(pending['operation_id'], pending['plan_hash'],
                    criterion_id=candidate['criterion_id'], candidate_hash=candidate['fingerprint'])
                original_execute = executor.execute_action
                source = workspace / case['sources'][0]['path']
                mutation_attempts, mutation_blocks = [], []

                def mutate_at_executor_entry(tool_name, *args, **kwargs):
                    if tool_name == 'file_bundle':
                        mutation_attempts.append(True)
                        try:
                            source.write_bytes(b'UNREVIEWED_RACE_CONTENT\n')
                        except OSError:
                            mutation_blocks.append(True)
                    return original_execute(tool_name, *args, **kwargs)

                with patch.object(executor, 'execute_action', side_effect=mutate_at_executor_entry):
                    try:
                        final = learning.execute(prepared['operation_id'], approved=True, plan_hash=prepared['plan_hash'])
                    except ValueError:
                        final = learning.get(prepared['operation_id'])
                self.assertEqual(final['step_records'][:2], prefix_receipts)
                self.assertLessEqual(len(mutation_attempts), 1)
                destination = workspace / case['destination']
                if destination.exists():
                    # A source write blocked by a retained native lease may
                    # still deliver exactly the reviewed bytes.
                    for row in case['sources']:
                        expected = row['text'].encode('utf8')
                        self.assertEqual((destination / Path(row['path']).name).read_bytes(), expected)
                        self.assertEqual((workspace / row['path']).read_bytes(), expected)
                    with zipfile.ZipFile(destination / case['archive_name']) as archive:
                        self.assertIsNone(archive.testzip())
                        for row in case['sources']:
                            self.assertEqual(archive.read(Path(row['path']).name), row['text'].encode('utf8'))
                    self.assertTrue(mutation_blocks, 'Source changed after admission but the producer still created output')
                    self.assertTrue(final['mission']['completed'])
                else:
                    # A platform without the required native lease must reject
                    # the suffix before any package effect.
                    self.assertFalse(final['mission']['completed'])
                    self.assertEqual(len(executor.list_operations()), 2)
                self.assertGreaterEqual(len(commands.operations()), 2)
                self.assertLessEqual(len(commands.operations()), 3)
            finally:
                learning.close()
                commands.close()
                executor.close()


if __name__ == '__main__':
    unittest.main()
