"""Unit tests for Procedural Memory and Lifecycle Reuse.
Demonstrates the full verified cycle:
  Execute action -> Verify postconditions -> Save recipe ->
  Restart system -> Retrieve recipe -> Reuse with new inputs ->
  Verify postconditions again -> Confirm 0 LLM calls used.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.actions.executor import ActionExecutor
from backend.memory.procedural_memory import ProceduralMemory, get_current_env_fingerprint

class ProceduralMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'memory.db'
        self.executor = ActionExecutor(self.db_path)
        self.memory = ProceduralMemory(self.db_path)

    def tearDown(self):
        self.memory.close()
        self.executor.close()
        self.tmp.cleanup()

    def test_complete_procedural_lifecycle_across_restart(self):
        # 1. Define and execute a first procedural task
        file_path_1 = Path(self.tmp.name) / 'output_1.txt'
        res1 = self.executor.execute_action('file_artifact_writer', {
            'path': str(file_path_1),
            'content': 'First execution data'
        })
        self.assertEqual(res1['state'], 'succeeded')
        self.assertTrue(res1['postconditions_passed'])

        # 2. Register verified procedure recipe
        recipe_id = 'recipe-create-verified-doc'
        intent_key = 'create_verified_project_doc'
        steps = [
            {
                'tool': 'file_artifact_writer',
                'args': {
                    'path': '$inputs.destination_path',
                    'content': '$inputs.file_text'
                }
            }
        ]
        schema = {
            'destination_path': {'type': 'string', 'required': True},
            'file_text': {'type': 'string', 'required': True}
        }
        recipe = self.memory.register_recipe(
            id=recipe_id,
            intent_key=intent_key,
            steps=steps,
            schema=schema,
            preconditions=['destination_path is writable'],
            postconditions=['file exists and sha256 matches'],
            status='verified'
        )
        self.assertEqual(recipe.status, 'verified')

        # 3. Simulate RESTART: Close current memory instance and create a new instance
        self.memory.close()
        self.memory = ProceduralMemory(self.db_path)

        # 4. Find recipe after restart
        found_recipe = self.memory.find_recipe(intent_key)
        self.assertIsNotNone(found_recipe)
        self.assertEqual(found_recipe.id, recipe_id)
        self.assertEqual(found_recipe.version, 1)

        # 5. Reuse procedure with NEW inputs (new path, new content)
        file_path_2 = Path(self.tmp.name) / 'reused_output_2.txt'
        new_inputs = {
            'destination_path': str(file_path_2),
            'file_text': 'Reused execution data with new inputs after reboot'
        }
        reuse_res = self.memory.execute_recipe(found_recipe, new_inputs, self.executor)

        # 6. Verify result of reused procedure
        self.assertEqual(reuse_res['outcome'], 'succeeded')
        self.assertEqual(reuse_res['model_calls_used'], 0)  # Reusing recipe required ZERO LLM calls!
        self.assertGreaterEqual(reuse_res['duration_ms'], 0.0)
        self.assertTrue(file_path_2.exists())
        self.assertEqual(file_path_2.read_text(), 'Reused execution data with new inputs after reboot')

        # 7. Verify attempt was persisted in SQLite
        cur = self.memory.db.execute('SELECT outcome, duration_ms FROM recipe_attempts WHERE recipe_id=?', (recipe_id,))
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 'succeeded')

    def test_environment_fingerprint_mismatch_skips_recipe(self):
        # Register recipe tied to a different environment
        self.memory.register_recipe(
            id='recipe-other-env',
            intent_key='test_env_mismatch',
            steps=[],
            schema={},
            env_fingerprint='incompatible_linux_fp'
        )
        # Attempting to find recipe under current Windows environment returns None
        found = self.memory.find_recipe('test_env_mismatch')
        self.assertIsNone(found)

if __name__ == '__main__':
    unittest.main()
