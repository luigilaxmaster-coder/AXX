# Phase 11 Specification — Multi-Agent Orchestration, Typed Handoffs & EventHub SSE (`PR-17`, Gate `G11`)

## 1. Objective
Implement multi-agent orchestration across Lead, Builder, and Independent Verifier agents using schema-validated `Handoff v1` contracts with scope attenuation, DLP context filtering, prompt-injection sanitization, mid-run `draining` agent transitions, Human-in-the-Loop approval cards, and a per-conversation monotonic `EventHub` with SSE `Last-Event-ID` replay and secret-redacted Flight Recorder exports.

## 2. Deliverables
- `backend/agents/handoffs.py` (`validate_handoff` against `schemas/handoff.schema.json`, `attenuate_handoff_grants` `SEC-02`, `inspect_and_sanitize_untrusted_text` `SEC-04`, `filter_dlp_context_items` `E2E-10`)
- `backend/agents/events.py` (`EventHub`, `validate_runtime_event` against `schemas/runtime-event.schema.json`, monotonic per-conversation `seq`, `replay_sse` with `Last-Event-ID` and pruned-window snapshot fallback `ORCH-03`, `redact_secrets`, and `export_flight_recorder` `E2E-11`)
- `backend/agents/scheduler.py` (`MultiAgentScheduler` with per-agent concurrency caps)
- `backend/agents/recovery.py` (`MultiAgentRecoveryService` emitting `run.unknown` and `approval.requested` on crash reconciliation `ORCH-02`)
- `backend/agents/orchestrator.py` (`MultiAgentOrchestrator` coordinating Lead/Subagent delegation `E2E-09`, mid-run `draining` agent switches `AGENT-03`, and mandatory approval gates `E2E-14`)
- `1.AXX/scripts/agents/agent-timeline.js`, `team-chat.js`, `work-approvals.js`
- `backend/tests/test_multiagent_orchestration.py`
