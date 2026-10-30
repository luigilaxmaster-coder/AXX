"""Compensated or source-derived output cannot feed reusable routine preparation."""
import json
import unittest
from unittest.mock import patch

from backend.tests import test_anticipation_grants as fixtures
from backend.anticipation import StaleContext
from backend.memory.skill_memory import validate_schema
from backend.memory.procedural_memory import get_action_env_fingerprint


class CompensationPreparationTests(unittest.TestCase):
    setUp = fixtures.MissionGrantTests.setUp
    tearDown = fixtures.MissionGrantTests.tearDown
    plan = fixtures.MissionGrantTests.plan
    grant = fixtures.MissionGrantTests.grant

    def interrupted(self):
        self.grant()
        plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'first.txt', 'content': 'first'}},
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'second.txt', 'content': 'second'}}])
        run = self.learning._run_step
        def pause_after_first(*args, **kwargs):
            result = run(*args, **kwargs)
            self.learning.pause(plan['operation_id'])
            return result
        with patch.object(self.learning, '_run_step', side_effect=pause_after_first):
            result = self.learning.execute(plan['operation_id'], approved=True)
        self.learning.pause_events[plan['operation_id']].clear()
        result.update(state='interrupted', pause_requested=False)
        self.learning._save(result)
        return result

    def compensate(self, source_operation_id, action='quarantine'):
        preview = self.commands.compensation_preview(source_operation_id)
        self.assertTrue(preview['available'], preview)
        prepared = self.commands.prepare_compensation(source_operation_id, preview['source_receipt_hash'],
            preview['compensation']['revision'], action=action)
        result = self.commands.execute(prepared['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded', result)

    def test_full_checkpoint_stops_after_quarantine_then_restores_without_repeating_writer(self):
        plan = self.interrupted()
        first = plan['step_records'][0]['operation_id']
        self.compensate(first)
        self.service.tick()
        self.assertEqual([row for row in self.service.suggestions() if row.get('candidate_kind') == 'resume_task'], [])
        self.assertFalse((self.executor.workspace_root / 'second.txt').exists())
        self.assertEqual(self.commands.get(first)['state'], 'succeeded')
        self.compensate(first, 'restore')
        self.service.tick()
        self.assertEqual((self.executor.workspace_root / 'second.txt').read_text(), 'second')
        writers = [row for row in self.executor.list_operations(100) if row['tool_name'] == 'file_artifact_writer']
        self.assertEqual(len(writers), 2)
        self.assertEqual(self.learning.get(plan['operation_id'])['step_records'][0]['operation_id'], first)
        self.assertEqual(self.model.calls, 0)

    def test_direct_dispatch_guard_projects_own_compensated_prefix_from_sql(self):
        plan = self.interrupted()
        self.compensate(plan['step_records'][0]['operation_id'])
        plan.update(state='running', approved_hash=plan['plan_hash'])
        plan['step_records'][1]['state'] = 'running'
        self.learning._save(plan)
        step, record = plan['steps'][1], plan['step_records'][1]
        prepared = self.commands.prepare(step['command_id'], step['inputs'], operation_id=record['operation_id'], conversation_id='task-a')
        result = self.commands.execute(prepared['operation_id'], approved=True)
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
        self.assertFalse((self.executor.workspace_root / 'second.txt').exists())

    def routine_evidence(self):
        self.service.configure({'profile': 'copiloto'})
        skill = self.learning.skills.insert({'id': 'fixture.telemetry', 'version': 1, 'trigger': 'fixture.telemetry',
            'title': 'Synthetic diagnostic', 'examples': [], 'schema': validate_schema({}),
            'templates': [{'command_id': 'axx.system.telemetry', 'inputs': {}}], 'project_id': '', 'favorite': False,
            'checks': ['executor_postconditions'], 'executable': True,
            'environment': get_action_env_fingerprint(['axx.system.telemetry']), 'provenance': {}})
        plans = []
        for number in range(3):
            plan = self.learning.prepare_steps('Entrega sintética', [
                {'command_id': 'axx.artifact.write', 'inputs': {'path': 'delivery-' + str(number) + '.txt', 'content': 'delivery'}}],
                conversation_id='task-a')
            with self.learning.lock:
                self.learning._bind(skill, {}, plan)
                self.learning._ready(plan, 'Entrega sintética')
                self.learning._save(plan)
            completed = self.learning.execute(plan['operation_id'], approved=True)
            self.assertEqual(completed['state'], 'succeeded', completed)
            plans.append(completed)
        return plans

    def test_routine_candidate_revalidates_all_three_deliverable_sources(self):
        plans = self.routine_evidence()
        self.service.tick()
        candidate = next(row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine')
        self.compensate(plans[0]['step_records'][0]['operation_id'])
        result = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertIn(result['state'], ('FAILED', 'CANCELLED'))
        self.assertFalse(result.get('preparation_complete'))
        self.assertEqual(self.model.calls, 0)

    def test_prepared_routine_is_born_with_source_dependencies_and_blocks_later_compensation(self):
        plans = self.routine_evidence()
        self.service.tick()
        candidate = next(row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine')
        prepared = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(prepared['state'], 'PREPARED', prepared)
        plan = self.learning.get(prepared['learning_plan_id'])
        self.assertEqual(len(plan['mission_dependencies']), 3)
        self.compensate(plans[0]['step_records'][0]['operation_id'])
        before = len(self.executor.list_operations(100))
        blocked = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(blocked['state'], 'waiting_dependency', blocked)
        self.assertEqual(len(self.executor.list_operations(100)), before)

    def mark_observed_fixture(self, operation_id):
        # A source-derived completed plan can use an existing exact skill, but
        # that is not authorization to turn its inputs into a recurring habit.
        # Build this historical DTO directly; no real observation is captured.
        with self.learning.lock, self.learning.db:
            source = json.loads(self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?',
                (operation_id,)).fetchone()[0])
            source['observation_dependencies'] = [{'target_id': 'synthetic-source', 'consent_digest': 'fixture',
                'observation_id': 'synthetic-observation', 'generation': 1}]
            source['plan_hash'] = self.learning._plan_hash(source)
            source['approved_hash'] = source['plan_hash']
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?',
                (json.dumps(source), operation_id))
        return source

    def test_source_derived_completed_plans_do_not_infer_reusable_routine(self):
        plans = self.routine_evidence()
        for plan in plans:
            self.mark_observed_fixture(plan['operation_id'])
        self.service.tick()
        self.assertEqual([row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine'], [])
        self.assertEqual(self.model.calls, 0)

    def test_routine_source_cannot_be_source_derived_even_with_matching_hash(self):
        self.routine_evidence()
        self.service.tick()
        candidate = next(row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine')
        source = self.mark_observed_fixture(candidate['plan']['learning_operation_id'])
        # A proposal from a prior implementation can bind this exact source
        # hash. The dedicated source policy must reject it independently.
        candidate['plan']['source_plan_hash'] = source['plan_hash']
        with self.service.lock, self.assertRaisesRegex(StaleContext, 'no se convierte'):
            self.service._preparation_source(candidate)

    def test_routine_consumption_excludes_source_derived_member_of_three_evidences(self):
        self.routine_evidence()
        self.service.tick()
        candidate = next(row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine')
        evidence_id = next(key for key in candidate['plan']['evidence_ids'] if key != candidate['plan']['learning_operation_id'])
        self.mark_observed_fixture(evidence_id)
        before = len(self.executor.list_operations(100))
        result = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertIn(result['state'], ('FAILED', 'CANCELLED'))
        self.assertFalse(result.get('preparation_complete'))
        self.assertEqual(len(self.executor.list_operations(100)), before)


if __name__ == '__main__':
    unittest.main()
