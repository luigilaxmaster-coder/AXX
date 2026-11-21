"""Unit and fault-injection tests for Phase 1 (PR-01 & PR-02): TaskGraph and Superpowers."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from backend.actions.executor import ActionExecutor
from backend.agents.superpowers import (
    IndependentVerifierService,
    SuperpowersSecurityError,
    SuperpowersWorkflowService,
)
from backend.agents.task_graph import (
    BudgetExceededError,
    CycleDetectedError,
    TaskGraphEngine,
    TaskGraphError,
    UnknownEffectBlockedError,
)


class TaskGraphAndSuperpowersTests(unittest.TestCase):
    def test_orch_01_dag_topological_order_and_cycle_rejection(self):
        engine = TaskGraphEngine(':memory:')
        self.addCleanup(engine.close)

        # Reject self-dependency and multi-node cycle
        with self.assertRaises(CycleDetectedError):
            engine.create_graph(
                run_id='run-cycle-1',
                agent_id='agent-a',
                goal_spec={'objective': 'test cycle'},
                nodes=[
                    {'task_id': 't1', 'depends_on': ['t2']},
                    {'task_id': 't2', 'depends_on': ['t1']},
                ],
            )

        # Reject delegation depth > max_delegate_depth (2)
        with self.assertRaises(TaskGraphError):
            engine.create_graph(
                run_id='run-depth-exceed',
                agent_id='agent-a',
                goal_spec={'objective': 'test depth'},
                nodes=[
                    {'task_id': 't0'},
                    {'task_id': 't1', 'parent_task_id': 't0'},
                    {'task_id': 't2', 'parent_task_id': 't1'},
                    {'task_id': 't3', 'parent_task_id': 't2'},
                ],
            )

        # Accept valid diamond DAG
        graph = engine.create_graph(
            run_id='run-diamond',
            agent_id='agent-a',
            goal_spec={'objective': 'diamond workflow'},
            nodes=[
                {'task_id': 't-root', 'is_pure': True},
                {'task_id': 't-left', 'depends_on': ['t-root'], 'is_pure': True},
                {'task_id': 't-right', 'depends_on': ['t-root'], 'is_pure': True},
                {'task_id': 't-join', 'depends_on': ['t-left', 't-right'], 'is_pure': True},
            ],
            max_workers=2,
        )
        self.assertEqual(graph['topological_order'], ['t-root', 't-left', 't-right', 't-join'])
        ready = engine.ready_tasks('run-diamond')
        self.assertEqual([t['task_id'] for t in ready], ['t-root'])

    def test_orch_02_crash_after_dispatch_marks_unknown_and_blocks_redispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'state.db'
            with ActionExecutor(db_path=db_path, workspace_root=tmp) as executor:
                engine = TaskGraphEngine(db_path=db_path, action_executor=executor)
                try:
                    engine.create_graph(
                        run_id='run-crash',
                        agent_id='agent-a',
                        goal_spec={'objective': 'write artifact'},
                        nodes=[
                            {
                                'task_id': 't-mutating',
                                'is_pure': False,
                                'action_spec': {
                                    'tool_name': 'file_artifact_writer',
                                    'inputs': {'path': 'out.txt', 'content': 'hello'},
                                },
                            },
                            {
                                'task_id': 't-dependent',
                                'depends_on': ['t-mutating'],
                                'is_pure': True,
                            },
                        ],
                    )

                    # Simulate start + crash mid-flight before receipt completion
                    started = engine.lease_and_start_task('t-mutating', lease_id='lease-1', operation_id='op-crash-1')
                    self.assertEqual(started['state'], 'running')
                    self.assertTrue(started['dispatched'])

                    # Reconcile on restart
                    rec = engine.reconcile_after_crash('run-crash')
                    self.assertEqual(rec['reconciled_unknown'], ['t-mutating'])

                    task_after = engine.get_task('t-mutating')
                    self.assertEqual(task_after['state'], 'unknown')

                    # Attempting to re-lease or re-dispatch must fail with UnknownEffectBlockedError (I-03)
                    with self.assertRaises(UnknownEffectBlockedError):
                        engine.lease_and_start_task('t-mutating', lease_id='lease-2')

                    # Dependent task must be blocked, never ready
                    ready = engine.ready_tasks('run-crash')
                    self.assertEqual(ready, [])
                    self.assertEqual(engine.get_task('t-dependent')['state'], 'blocked')
                finally:
                    engine.close()

    def test_pr_02_superpowers_workflow_executes_via_action_executor_and_independent_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'superpowers.db'
            with ActionExecutor(db_path=db_path, workspace_root=tmp) as executor:
                engine = TaskGraphEngine(db_path=db_path, action_executor=executor)
                try:
                    verifier = IndependentVerifierService(action_executor=executor)
                    workflow = SuperpowersWorkflowService(engine, verifier)

                    # Reject self-review and raw shell bypass
                    with self.assertRaises(SuperpowersSecurityError):
                        workflow.build_superpowers_workflow(
                            run_id='run-bad',
                            lead_agent_id='agent-dev',
                            reviewer_agent_id='agent-dev',
                            goal_spec={'objective': 'self review'},
                        )
                    with self.assertRaises(SuperpowersSecurityError):
                        workflow.build_superpowers_workflow(
                            run_id='run-shell-bypass',
                            lead_agent_id='agent-dev',
                            reviewer_agent_id='agent-qa',
                            goal_spec={'objective': 'bypass'},
                            implementation_action_spec={'kind': 'raw_shell', 'cmd': 'del /q *'},
                        )

                    # Build real workflow writing a verified file via ActionExecutor
                    workflow.build_superpowers_workflow(
                        run_id='run-sp1',
                        lead_agent_id='agent-dev',
                        reviewer_agent_id='agent-qa',
                        goal_spec={'objective': 'Write verified spec artifact'},
                        implementation_action_spec={
                            'kind': 'command',
                            'command_id': 'axx.artifact.write',
                            'tool_name': 'file_artifact_writer',
                            'inputs': {'path': 'feature-out.txt', 'content': 'verified superpower output'},
                        },
                    )

                    # 1. Plan stage
                    engine.lease_and_start_task('run-sp1-plan', lease_id='l-1')
                    engine.submit_for_verification(
                        'run-sp1-plan',
                        result={'plan_steps': 3},
                        evidence={'spec_compliance': True, 'quality': True},
                    )
                    # Self-verification by agent-dev must be rejected and leave task in verifying!
                    self_check = workflow.verify_and_advance_task('run-sp1-plan', verifier_agent_id='agent-dev')
                    self.assertFalse(self_check['verdict']['verified'])
                    self.assertEqual(self_check['verdict']['status'], 'self_verification_prohibited')
                    self.assertEqual(self_check['task']['state'], 'verifying')

                    # Verify with independent agent-qa
                    v_plan = workflow.verify_and_advance_task('run-sp1-plan', verifier_agent_id='agent-qa')
                    self.assertTrue(v_plan['verdict']['verified'])
                    self.assertEqual(v_plan['task']['state'], 'completed')

                    # 2. TDD Red stage
                    ready = engine.ready_tasks('run-sp1')
                    self.assertEqual([r['task_id'] for r in ready], ['run-sp1-tdd-red'])
                    engine.lease_and_start_task('run-sp1-tdd-red', lease_id='l-2')
                    engine.submit_for_verification(
                        'run-sp1-tdd-red',
                        result={'failing_test_defined': True},
                        evidence={'spec_compliance': True, 'quality': True},
                    )
                    v_tdd = workflow.verify_and_advance_task('run-sp1-tdd-red', verifier_agent_id='agent-qa')
                    self.assertTrue(v_tdd['verdict']['verified'])

                    # 3. Implement Green stage via real ActionExecutor
                    ready = engine.ready_tasks('run-sp1')
                    self.assertEqual([r['task_id'] for r in ready], ['run-sp1-implement'])
                    impl_task = engine.dispatch_task_via_executor('run-sp1-implement', lease_id='l-3')
                    self.assertEqual(impl_task['state'], 'verifying')
                    v_impl = workflow.verify_and_advance_task('run-sp1-implement', verifier_agent_id='agent-qa')
                    self.assertTrue(v_impl['verdict']['verified'])
                    self.assertIn(f"executor_receipt:{impl_task['operation_id']}", v_impl['verdict']['checked_items'])
                    written_file = Path(tmp) / 'feature-out.txt'
                    self.assertTrue(written_file.is_file())
                    self.assertEqual(written_file.read_text(encoding='utf-8'), 'verified superpower output')

                    # 4. Review stage
                    ready = engine.ready_tasks('run-sp1')
                    self.assertEqual([r['task_id'] for r in ready], ['run-sp1-review'])
                    engine.lease_and_start_task('run-sp1-review', lease_id='l-4')
                    target_sha = hashlib.sha256(written_file.read_bytes()).hexdigest()
                    engine.submit_for_verification(
                        'run-sp1-review',
                        result={'artifacts': [{'path': str(written_file), 'sha256': target_sha}]},
                        evidence={'spec_compliance': True, 'quality': True},
                    )
                    v_rev = workflow.verify_and_advance_task('run-sp1-review', verifier_agent_id='agent-lead-verifier')
                    self.assertTrue(v_rev['verdict']['verified'])
                    self.assertEqual(engine.get_graph('run-sp1')['status'], 'completed')
                finally:
                    engine.close()

    def test_orch_04_cost_budget_enforcement(self):
        engine = TaskGraphEngine(':memory:')
        self.addCleanup(engine.close)
        engine.create_graph(
            run_id='run-budget',
            agent_id='agent-a',
            goal_spec={'objective': 'budget test'},
            nodes=[{'task_id': 't-costly', 'is_pure': True}],
            max_cost_usd=0.50,
        )
        engine.lease_and_start_task('t-costly', lease_id='l-cost')
        with self.assertRaises(BudgetExceededError):
            engine.submit_for_verification(
                't-costly',
                result={'ok': True},
                evidence={'spec_compliance': True},
                cost_usd=0.75,
            )
        self.assertEqual(engine.get_task('t-costly')['state'], 'blocked')
        self.assertEqual(engine.get_graph('run-budget')['status'], 'blocked')

    def test_action_learning_integrates_task_graph_and_superpowers_without_regression(self):
        from backend.commands import CommandService
        from backend.action_learning import ActionLearning

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'learning.db'
            with ActionExecutor(db_path=db_path, workspace_root=tmp) as executor:
                commands = CommandService(executor)
                learning = ActionLearning(commands, adapter=None)
                try:
                    self.assertIsNotNone(learning.task_graph)
                    self.assertIsNotNone(learning.superpowers)
                    graph = learning.superpowers.build_superpowers_workflow(
                        run_id='run-al-1',
                        lead_agent_id='axx-lead',
                        reviewer_agent_id='axx-reviewer',
                        goal_spec={'objective': 'Verify ActionLearning TaskGraph integration'},
                    )
                    self.assertEqual(len(graph['nodes']), 4)
                finally:
                    learning.close()
                    commands.close()


if __name__ == '__main__':
    unittest.main()
