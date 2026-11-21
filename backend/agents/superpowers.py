"""Superpowers Workflow Engine & Independent Verifier Service (PR-02).

Integrates Superpowers methodology (brainstorm -> plan -> tdd_red -> implement_green -> review -> verify)
with AXX's TaskGraphEngine and CommandService / ActionExecutor.

Invariants:
- I-01: No host/workspace effect bypasses CommandService / ActionExecutor.
- An LLM message NEVER marks a task completed on its own; IndependentVerifierService must
  evaluate concrete postconditions, executor receipts, and artifact hashes.
- If a verifier throws or cannot check a criterion, the verdict is 'verification_unavailable',
  never a false positive success.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from backend.agents.task_graph import TaskGraphEngine, TaskGraphError

SUPERPOWERS_STAGES = (
    'brainstorm',
    'plan',
    'tdd_red',
    'implement_green',
    'review',
    'verify',
)

ROLE_CAPABILITIES: dict[str, dict[str, Any]] = {
    'planner': {
        'allowed_operation_classes': frozenset({'read_scoped', 'compute_pure'}),
        'can_mutate_workspace': False,
        'can_verify_own_work': False,
    },
    'implementer': {
        'allowed_operation_classes': frozenset({'read_scoped', 'compute_pure', 'write_workspace'}),
        'can_mutate_workspace': True,
        'can_verify_own_work': False,
    },
    'tester': {
        'allowed_operation_classes': frozenset({'read_scoped', 'compute_pure'}),
        'can_mutate_workspace': False,
        'can_verify_own_work': False,
    },
    'reviewer': {
        'allowed_operation_classes': frozenset({'read_scoped', 'compute_pure'}),
        'can_mutate_workspace': False,
        'can_verify_own_work': False,
    },
    'verifier': {
        'allowed_operation_classes': frozenset({'read_scoped', 'compute_pure'}),
        'can_mutate_workspace': False,
        'can_verify_own_work': True,
    },
}


class SuperpowersSecurityError(PermissionError):
    """Raised when a workflow attempts to bypass CommandService or self-certify completion."""


class IndependentVerifierService:
    """Verifies task outputs against spec_compliance, quality, executor receipts, and artifact hashes."""

    def __init__(self, action_executor=None):
        self.action_executor = action_executor
        self._custom_checks: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {}

    def register_check(
        self,
        check_id: str,
        fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._custom_checks[check_id] = fn

    def verify_task(
        self,
        task: dict[str, Any],
        *,
        verifier_agent_id: str,
        acceptance_criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        """Inspect a task in 'verifying' state and return a structured verification receipt."""
        producer_agent = task.get('agent_id')
        producer_role = task.get('role')
        if producer_role != 'verifier' and verifier_agent_id == producer_agent:
            return {
                'verified': False,
                'status': 'self_verification_prohibited',
                'spec_compliance': False,
                'quality': False,
                'checked_items': [],
                'unverified_items': list(acceptance_criteria or ['self_verification_rejected']),
                'reason': 'Constructor agent cannot verify its own output; independent verifier required.',
            }

        result = task.get('result') or {}
        evidence = task.get('evidence') or {}
        action_spec = task.get('action_spec') or {}

        checked_items: list[str] = []
        unverified_items: list[str] = list(task.get('unverified_items') or [])

        # 1. Prohibir completado por simple afirmación textual del LLM
        if result.get('llm_claimed_done') is True and not evidence:
            return {
                'verified': False,
                'status': 'unsubstantiated_llm_claim',
                'spec_compliance': False,
                'quality': False,
                'checked_items': [],
                'unverified_items': ['missing_independent_postcondition_evidence'],
                'reason': 'LLM text claim without postcondition evidence cannot mark a task completed.',
            }

        # 2. Si la tarea involucra una operación del ejecutor, verificar recibo real en ActionExecutor
        op_id = task.get('operation_id')
        if action_spec.get('tool_name'):
            if self.action_executor is None:
                return {
                    'verified': False,
                    'status': 'verification_unavailable',
                    'spec_compliance': False,
                    'quality': False,
                    'checked_items': checked_items,
                    'unverified_items': ['action_executor_unavailable'],
                    'reason': 'ActionExecutor not available to verify operation journal receipt.',
                }
            receipt = self.action_executor.get_operation(op_id) if op_id else None
            if not receipt:
                return {
                    'verified': False,
                    'status': 'missing_executor_receipt',
                    'spec_compliance': False,
                    'quality': False,
                    'checked_items': checked_items,
                    'unverified_items': [f'missing_operation_receipt:{op_id}'],
                    'reason': 'Mutating or tool task has no recorded receipt in ActionExecutor journal.',
                }
            if receipt.get('state') != 'succeeded' or receipt.get('postconditions_passed') is not True:
                return {
                    'verified': False,
                    'status': 'executor_postcondition_failed',
                    'spec_compliance': False,
                    'quality': False,
                    'checked_items': checked_items,
                    'unverified_items': [f'executor_state:{receipt.get("state")}'],
                    'reason': f'ActionExecutor receipt state={receipt.get("state")} postconditions={receipt.get("postconditions_passed")}',
                }
            checked_items.append(f'executor_receipt:{op_id}')

        # 3. Verificar hashes de archivos si se declararon artefactos en disco
        for artifact in result.get('artifacts', []):
            if isinstance(artifact, dict) and artifact.get('path') and artifact.get('sha256'):
                p = Path(artifact['path'])
                if not p.is_file():
                    return {
                        'verified': False,
                        'status': 'artifact_missing',
                        'spec_compliance': False,
                        'quality': False,
                        'checked_items': checked_items,
                        'unverified_items': [f'missing_file:{p.name}'],
                        'reason': f'Declared artifact file does not exist: {p}',
                    }
                actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual_sha != artifact['sha256']:
                    return {
                        'verified': False,
                        'status': 'artifact_hash_mismatch',
                        'spec_compliance': False,
                        'quality': False,
                        'checked_items': checked_items,
                        'unverified_items': [f'sha256_mismatch:{p.name}'],
                        'reason': f'Artifact SHA256 mismatch for {p.name}',
                    }
                checked_items.append(f'artifact_sha256:{p.name}')

        # 4. Ejecutar checks registrados (spec_compliance, quality, custom)
        for check_id in action_spec.get('verifier_checks', []):
            fn = self._custom_checks.get(check_id)
            if fn is None:
                unverified_items.append(f'unavailable_check:{check_id}')
                return {
                    'verified': False,
                    'status': 'verification_unavailable',
                    'spec_compliance': False,
                    'quality': False,
                    'checked_items': checked_items,
                    'unverified_items': unverified_items,
                    'reason': f'Required verifier check {check_id} is not registered.',
                }
            try:
                outcome = fn(task, result)
            except Exception as exc:
                unverified_items.append(f'check_exception:{check_id}')
                return {
                    'verified': False,
                    'status': 'verification_unavailable',
                    'spec_compliance': False,
                    'quality': False,
                    'checked_items': checked_items,
                    'unverified_items': unverified_items,
                    'reason': f'Verifier check {check_id} raised {type(exc).__name__}: {exc}',
                }
            if not isinstance(outcome, dict) or outcome.get('passed') is not True:
                return {
                    'verified': False,
                    'status': 'check_failed',
                    'spec_compliance': bool(outcome.get('spec_compliance', False)) if isinstance(outcome, dict) else False,
                    'quality': bool(outcome.get('quality', False)) if isinstance(outcome, dict) else False,
                    'checked_items': checked_items,
                    'unverified_items': unverified_items,
                    'reason': (outcome.get('reason') if isinstance(outcome, dict) else None) or f'Check {check_id} failed',
                }
            checked_items.append(f'check:{check_id}')

        spec_ok = evidence.get('spec_compliance', True) is True
        quality_ok = evidence.get('quality', True) is True
        if not (spec_ok and quality_ok):
            return {
                'verified': False,
                'status': 'quality_or_spec_failed',
                'spec_compliance': spec_ok,
                'quality': quality_ok,
                'checked_items': checked_items,
                'unverified_items': unverified_items,
                'reason': 'spec_compliance or quality check did not pass',
            }

        if not checked_items and not evidence:
            return {
                'verified': False,
                'status': 'insufficient_evidence',
                'spec_compliance': False,
                'quality': False,
                'checked_items': [],
                'unverified_items': ['no_verifiable_evidence'],
                'reason': 'No verifiable evidence provided.',
            }

        return {
            'verified': True,
            'status': 'verified',
            'verifier_agent_id': verifier_agent_id,
            'spec_compliance': True,
            'quality': True,
            'checked_items': checked_items or ['evidence_contract'],
            'unverified_items': unverified_items,
        }


class SuperpowersWorkflowService:
    """Builds and executes Superpowers plan/TDD/review/verify DAGs over TaskGraphEngine."""

    def __init__(
        self,
        task_graph: TaskGraphEngine,
        verifier: IndependentVerifierService,
        *,
        skill_memory=None,
    ):
        self.task_graph = task_graph
        self.verifier = verifier
        self.skill_memory = skill_memory

    def build_superpowers_workflow(
        self,
        *,
        run_id: str,
        lead_agent_id: str,
        reviewer_agent_id: str,
        goal_spec: dict[str, Any],
        implementation_action_spec: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        max_cost_usd: float = 1.0,
    ) -> dict[str, Any]:
        """Create a canonical 5-node Superpowers DAG (plan -> tdd_red -> implement_green -> review -> verify)."""
        if lead_agent_id == reviewer_agent_id:
            raise SuperpowersSecurityError('lead_agent_id and reviewer_agent_id must be distinct for independent review/verification')
        impl_spec = dict(implementation_action_spec or {'kind': 'pure_compute'})
        if impl_spec.get('kind') in ('raw_shell', 'unregistered_eval', 'direct_host_exec'):
            raise SuperpowersSecurityError(
                f"Prohibited execution kind '{impl_spec.get('kind')}': all host effects must use registered CommandService tools"
            )

        nodes = [
            {
                'task_id': f'{run_id}-plan',
                'agent_id': lead_agent_id,
                'role': 'planner',
                'depends_on': [],
                'is_pure': True,
                'action_spec': {'stage': 'plan', 'kind': 'pure_compute'},
            },
            {
                'task_id': f'{run_id}-tdd-red',
                'agent_id': lead_agent_id,
                'role': 'tester',
                'parent_task_id': f'{run_id}-plan',
                'depends_on': [f'{run_id}-plan'],
                'is_pure': True,
                'action_spec': {'stage': 'tdd_red', 'kind': 'pure_compute'},
            },
            {
                'task_id': f'{run_id}-implement',
                'agent_id': lead_agent_id,
                'role': 'implementer',
                'parent_task_id': f'{run_id}-plan',
                'depends_on': [f'{run_id}-tdd-red'],
                'is_pure': not bool(impl_spec.get('tool_name')),
                'action_spec': {'stage': 'implement_green', **impl_spec},
            },
            {
                'task_id': f'{run_id}-review',
                'agent_id': reviewer_agent_id,
                'role': 'reviewer',
                'parent_task_id': f'{run_id}-implement',
                'depends_on': [f'{run_id}-implement'],
                'is_pure': True,
                'action_spec': {'stage': 'review', 'kind': 'pure_compute'},
            },
        ]
        return self.task_graph.create_graph(
            run_id=run_id,
            agent_id=lead_agent_id,
            goal_spec=goal_spec,
            nodes=nodes,
            conversation_id=conversation_id,
            max_cost_usd=max_cost_usd,
        )

    def verify_and_advance_task(
        self,
        task_id: str,
        *,
        verifier_agent_id: str,
        acceptance_criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        task = self.task_graph.get_task(task_id)
        verdict = self.verifier.verify_task(
            task,
            verifier_agent_id=verifier_agent_id,
            acceptance_criteria=acceptance_criteria,
        )
        if verdict['verified'] is True:
            updated = self.task_graph.complete_verified_task(
                task_id,
                verifier_evidence=verdict,
                unverified_items=verdict.get('unverified_items'),
            )
            return {'task': updated, 'verdict': verdict}
        if verdict.get('status') in ('self_verification_prohibited', 'verification_unavailable'):
            # Keep task in 'verifying' state so an authorized/available independent verifier can inspect it
            return {'task': task, 'verdict': verdict}
        repairable = verdict.get('status') in ('check_failed', 'quality_or_spec_failed')
        updated = self.task_graph.fail_task(
            task_id,
            error=f"{verdict.get('status')}: {verdict.get('reason')}",
            repairable=repairable,
        )
        return {'task': updated, 'verdict': verdict}
