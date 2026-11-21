"""Crash Reconciliation and Unknown-Effect Recovery Service (PR-17 / ORCH-02).

Enforces Invariants:
- I-03 / ORCH-02: Any side-effecting tool call that was in-flight ('dispatched') when a crash occurred
  transitions to 'unknown' and emits 'run.unknown' + 'approval.requested'. It is NEVER re-executed automatically.
"""
from __future__ import annotations

from typing import Any

from backend.agents.events import EventHub
from backend.agents.task_graph import TaskGraphEngine


class MultiAgentRecoveryService:
    """Reconciles interrupted multi-agent runs after a crash and publishes audit events to EventHub."""

    def __init__(self, task_graph: TaskGraphEngine, event_hub: EventHub):
        self.task_graph = task_graph
        self.event_hub = event_hub

    def reconcile_interrupted_run(
        self,
        *,
        run_id: str,
        conversation_id: str,
        lead_agent_id: str,
    ) -> dict[str, Any]:
        summary = self.task_graph.reconcile_after_crash(run_id)
        unknown_tasks = summary.get('reconciled_unknown', [])
        if unknown_tasks:
            self.event_hub.publish_event(
                conversation_id=conversation_id,
                run_id=run_id,
                agent_id=lead_agent_id,
                event_type='run.unknown',
                payload={
                    'unknown_tasks': unknown_tasks,
                    'auto_retry_blocked': True,
                },
            )
            self.event_hub.publish_event(
                conversation_id=conversation_id,
                run_id=run_id,
                agent_id=lead_agent_id,
                event_type='approval.requested',
                payload={
                    'reason': 'reconcile_unknown_side_effect',
                    'unknown_tasks': unknown_tasks,
                },
            )
        return summary
