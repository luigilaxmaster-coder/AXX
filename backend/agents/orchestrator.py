"""Multi-Agent Orchestrator — Lead/Subagent Delegation, Draining Agent Switch & Approval Gate (PR-17 / Gate G11).

Enforces Invariants:
- AGENT-03: Changing a conversation's active agent while a run is active puts the previous binding into
  'draining' mode so the in-flight run finishes under its original agent_id while new turns route to
  the newly bound agent.
- SEC-02 / SEC-04 / E2E-10: Every Handoff v1 enforces scope attenuation, DLP context filtering, and
  prompt-injection sanitization.
- E2E-09: Lead agent coordinates Builder + Independent Verifier with real receipts.
- E2E-14: Sensitive operations pause in 'awaiting_approval', emit 'tool.prepared' + 'approval.requested',
  and only dispatch after explicit human approval ('approval.resolved').
"""
from __future__ import annotations

from typing import Any

from backend.agents.bindings import ConversationBindingService
from backend.agents.events import EventHub
from backend.agents.handoffs import (
    attenuate_handoff_grants,
    filter_dlp_context_items,
    inspect_and_sanitize_untrusted_text,
    validate_handoff,
)
from backend.agents.superpowers import IndependentVerifierService
from backend.agents.task_graph import TaskGraphEngine


class ApprovalRequiredPendingError(PermissionError):
    """Raised when attempting to dispatch a sensitive operation before its approval card is resolved (E2E-14)."""


class MultiAgentOrchestrator:
    """Coordinates Lead -> Subagent handoffs, EventHub streaming, approval gates, and draining transitions."""

    def __init__(
        self,
        *,
        task_graph: TaskGraphEngine,
        event_hub: EventHub,
        verifier: IndependentVerifierService,
        bindings: ConversationBindingService | None = None,
    ):
        self.task_graph = task_graph
        self.event_hub = event_hub
        self.verifier = verifier
        self.bindings = bindings
        self.handoffs: dict[str, dict[str, Any]] = {}
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self.active_runs: dict[str, dict[str, Any]] = {}

    def start_run(
        self,
        *,
        run_id: str,
        conversation_id: str,
        lead_agent_id: str,
        nodes: list[dict[str, Any]],
        goal_spec: dict[str, Any] | None = None,
        budget_usd: float = 5.0,
    ) -> dict[str, Any]:
        graph = self.task_graph.create_graph(
            run_id=run_id,
            conversation_id=conversation_id,
            agent_id=lead_agent_id,
            goal_spec=goal_spec or {'objective': 'Multi-agent run'},
            nodes=nodes,
            max_cost_usd=budget_usd,
        )
        self.active_runs[run_id] = {
            'run_id': run_id,
            'conversation_id': conversation_id,
            'bound_agent_id': lead_agent_id,
            'draining': False,
            'status': 'running',
            'graph': graph,
        }
        self.event_hub.publish_event(
            conversation_id=conversation_id,
            run_id=run_id,
            agent_id=lead_agent_id,
            event_type='run.started',
            payload={'lead_agent_id': lead_agent_id, 'budget_usd': budget_usd},
        )
        return self.active_runs[run_id]

    def switch_conversation_agent_mid_run(
        self,
        *,
        conversation_id: str,
        active_run_id: str,
        new_agent_id: str,
    ) -> dict[str, Any]:
        """Switch conversation agent mid-run: mark active run as draining under old agent and bind new turns to new_agent_id (AGENT-03)."""
        if active_run_id not in self.active_runs:
            raise LookupError(f'Active run not found: {active_run_id}')
        run_state = self.active_runs[active_run_id]
        old_agent_id = run_state['bound_agent_id']
        run_state['draining'] = True

        binding_result = None
        if self.bindings is not None:
            binding_result = self.bindings.switch_agent(
                conversation_id,
                new_agent_id,
                has_active_run=True,
                actor='user',
            )

        self.event_hub.publish_event(
            conversation_id=conversation_id,
            run_id=active_run_id,
            agent_id=old_agent_id,
            event_type='agent.updated',
            payload={
                'previous_agent_id': old_agent_id,
                'new_agent_id': new_agent_id,
                'draining_run_id': active_run_id,
            },
        )
        return {
            'conversation_id': conversation_id,
            'draining_run_id': active_run_id,
            'in_flight_run_agent_id': old_agent_id,
            'next_turn_agent_id': new_agent_id,
            'draining': True,
            'binding': binding_result,
        }

    def delegate_handoff(
        self,
        *,
        handoff_payload: dict[str, Any],
        parent_grants: list[str],
        context_items: list[dict[str, Any]] | None = None,
        recipient_allowed_classifications: set[str] | None = None,
        untrusted_notes: str = '',
    ) -> dict[str, Any]:
        """Validate Handoff v1, enforce scope attenuation (SEC-02), DLP filtering (E2E-10), and prompt-injection sanitization (SEC-04)."""
        attenuated_grants = attenuate_handoff_grants(
            parent_grants,
            list(handoff_payload.get('tool_grant_refs', [])),
        )
        candidate = dict(handoff_payload, tool_grant_refs=attenuated_grants)

        safe_context = filter_dlp_context_items(
            list(context_items or []),
            recipient_allowed_classifications=recipient_allowed_classifications,
            strict_raise=True,
        )

        injection_report = inspect_and_sanitize_untrusted_text(untrusted_notes)

        validated = validate_handoff(candidate)
        self.handoffs[validated['handoff_id']] = {
            'handoff': validated,
            'safe_context': safe_context,
            'sanitized_notes': injection_report,
        }

        self.event_hub.publish_event(
            conversation_id=validated['conversation_id'],
            run_id=validated['run_id'],
            agent_id=validated['from_agent_id'],
            event_type='handoff.created',
            payload={
                'handoff_id': validated['handoff_id'],
                'to_agent_id': validated['to_agent_id'],
                'task_id': validated['task_id'],
                'injection_detected': injection_report['injection_detected'],
            },
        )
        return self.handoffs[validated['handoff_id']]

    def request_human_approval(
        self,
        *,
        conversation_id: str,
        run_id: str,
        task_id: str,
        agent_id: str,
        operation_id: str,
        tool_name: str,
        risk_class: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pause a sensitive tool invocation and emit tool.prepared + approval.requested (E2E-14)."""
        card = {
            'operation_id': operation_id,
            'conversation_id': conversation_id,
            'run_id': run_id,
            'task_id': task_id,
            'agent_id': agent_id,
            'tool_name': tool_name,
            'risk_class': risk_class,
            'parameters': dict(parameters or {}),
            'status': 'pending',
        }
        self.pending_approvals[operation_id] = card

        self.event_hub.publish_event(
            conversation_id=conversation_id,
            run_id=run_id,
            agent_id=agent_id,
            event_type='tool.prepared',
            payload={'operation_id': operation_id, 'tool_name': tool_name, 'task_id': task_id},
        )
        self.event_hub.publish_event(
            conversation_id=conversation_id,
            run_id=run_id,
            agent_id=agent_id,
            event_type='approval.requested',
            payload={'operation_id': operation_id, 'tool_name': tool_name, 'risk_class': risk_class},
        )
        return dict(card)

    def resolve_human_approval(
        self,
        *,
        operation_id: str,
        approved: bool,
        actor: str = 'user',
    ) -> dict[str, Any]:
        if operation_id not in self.pending_approvals:
            raise LookupError(f'Pending approval not found: {operation_id}')
        card = self.pending_approvals[operation_id]
        card['status'] = 'approved' if approved else 'denied'
        card['resolved_by'] = actor

        self.event_hub.publish_event(
            conversation_id=card['conversation_id'],
            run_id=card['run_id'],
            agent_id=card['agent_id'],
            event_type='approval.resolved',
            payload={'operation_id': operation_id, 'approved': approved, 'actor': actor},
        )
        if not approved:
            self.task_graph.cancel_task(card['task_id'], reason=f'Denied by {actor}')
        return dict(card)

    def dispatch_approved_tool(
        self,
        *,
        operation_id: str,
        lease_id: str,
        verifier_agent_id: str,
        execute_fn,
    ) -> dict[str, Any]:
        """Dispatch a sensitive tool ONLY if its approval card was explicitly approved, then verify via IndependentVerifier (E2E-14 / ORCH-04)."""
        if operation_id not in self.pending_approvals:
            raise ApprovalRequiredPendingError(f'No approval card exists for operation_id={operation_id!r}')
        card = self.pending_approvals[operation_id]
        if card['status'] != 'approved':
            raise ApprovalRequiredPendingError(
                f"Cannot dispatch operation {operation_id!r}: approval status is {card['status']!r}"
            )

        self.task_graph.lease_and_start_task(
            card['task_id'],
            lease_id=lease_id,
            operation_id=operation_id,
        )
        self.event_hub.publish_event(
            conversation_id=card['conversation_id'],
            run_id=card['run_id'],
            agent_id=card['agent_id'],
            event_type='tool.dispatched',
            payload={'operation_id': operation_id, 'tool_name': card['tool_name']},
        )

        result = execute_fn()
        evidence = {
            'operation_id': operation_id,
            'tool_name': card['tool_name'],
            'receipt': result,
        }
        task_node = self.task_graph.submit_for_verification(
            card['task_id'],
            result=result if isinstance(result, dict) else {'value': result},
            evidence=evidence,
        )
        verdict = self.verifier.verify_task(
            task_node,
            verifier_agent_id=verifier_agent_id,
        )
        verified_task = self.task_graph.complete_verified_task(
            card['task_id'],
            verifier_evidence=verdict,
        )
        self.event_hub.publish_event(
            conversation_id=card['conversation_id'],
            run_id=card['run_id'],
            agent_id=verifier_agent_id,
            event_type='tool.verified',
            payload={'operation_id': operation_id, 'task_id': card['task_id'], 'state': verified_task['state']},
        )
        return verified_task
