"""Multi-Agent Task Scheduler with Per-Agent Concurrency Caps (PR-17 / ORCH-01).
"""
from __future__ import annotations

from typing import Any


class MultiAgentScheduler:
    """Schedules ready TaskGraph nodes onto specialized agents respecting per-agent concurrency limits."""

    def __init__(self, default_max_concurrent: int = 2):
        self.default_max_concurrent = int(default_max_concurrent)
        self.agent_caps: dict[str, int] = {}
        self.active_by_agent: dict[str, set[str]] = {}

    def configure_agent_limit(self, agent_id: str, max_concurrent_tasks: int) -> None:
        self.agent_caps[agent_id] = max(1, int(max_concurrent_tasks))

    def can_schedule(self, agent_id: str) -> bool:
        cap = self.agent_caps.get(agent_id, self.default_max_concurrent)
        active = self.active_by_agent.get(agent_id, set())
        return len(active) < cap

    def mark_started(self, agent_id: str, task_id: str) -> None:
        if not self.can_schedule(agent_id):
            raise RuntimeError(f'Agent {agent_id!r} exceeded max_concurrent_tasks limit')
        self.active_by_agent.setdefault(agent_id, set()).add(task_id)

    def mark_finished(self, agent_id: str, task_id: str) -> None:
        if agent_id in self.active_by_agent:
            self.active_by_agent[agent_id].discard(task_id)

    def select_dispatchable_tasks(self, ready_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for task in ready_tasks:
            agent_id = task['assigned_agent_id']
            if self.can_schedule(agent_id):
                self.mark_started(agent_id, task['task_id'])
                selected.append(task)
        return selected
