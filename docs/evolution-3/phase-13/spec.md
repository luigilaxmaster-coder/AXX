# Phase 13 Specification — Autonomous Routines, ResourceGovernor, Mobile/Remote Continuity & HTTP API (`PR-19`, Gate `G13`)

## 1. Objective
Complete the final phase of AXX Evolution 3.0 with privacy-hardened autonomous routines, real-time `ResourceGovernor` & `CostLedger` prioritizing user voice and 3D avatar rendering, authenticated Mobile Companion <-> PC Agent Workspace continuity with strict scope intersection, and the unified host-token-authenticated HTTP router (`/axx-api/agents/v1/*`, `/axx-api/workspaces/v1/*`, `/axx-api/code/v1/*`, `/axx-api/spatial/v2/*`).

## 2. Deliverables
- `backend/agents/routines.py` (`AutonomousRoutineService` blocking `microphone`/`host_input`, pausing imported routines on import, and gating mutating triggers on approval cards `E2E-07`)
- `backend/agents/resource_governor.py` (`ResourceGovernor` with `Eco`/`Balanceado`/`Máximo` profiles queueing heavy background jobs when `voice_active=True` or `avatar_fps < 45` or CPU/RAM thresholds are exceeded `PERF-01`, `E2E-13`; `CostLedger` pausing runs exceeding `run_budget_usd` `PERF-02`)
- `backend/workspaces/remote_protocol.py` (`RemoteWorkerContinuityService` enforcing constant-time device token auth and `device_scopes & agent_scopes` intersection without privilege escalation `E2E-08`, `MOBILE-01`, `SEC-01`)
- `backend/agents/http_api.py` (`EvolutionHTTP` & `EvolutionHttpRuntime`) and additive routing in `backend/server.py`
- `docs/evolution-3/qa/acceptance-matrix.csv` (updated with verified evidence references across Phases 0–13)
- `backend/tests/test_phase13_routines_governor_remote_and_http.py`
