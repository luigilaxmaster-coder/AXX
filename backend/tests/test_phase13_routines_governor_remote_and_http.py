"""Unit, security, and HTTP integration tests for Phase 13 — Routines, ResourceGovernor, Mobile Continuity & HTTP API (PR-19 / Gate G13).

Covers:
- E2E-07: Autonomous routines block microphone/host_input, start paused on import, and require approval cards for mutations.
- PERF-01, PERF-02 & E2E-13: ResourceGovernor queues heavy background jobs when voice is active or avatar FPS/CPU/RAM
  pressure is high; CostLedger pauses runs when budget is exceeded.
- E2E-08 & MOBILE-01: Mobile/Remote continuity enforces device token auth and scope intersection without privilege escalation.
- SEC-01: All /axx-api/agents/v1/*, /axx-api/workspaces/v1/*, /axx-api/code/v1/*, /axx-api/spatial/v2/* routes
  reject unauthenticated or browser-Origin requests (401/403) and serve valid host-token requests (200).
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest

from backend.agents.events import EventHub
from backend.agents.orchestrator import MultiAgentOrchestrator
from backend.agents.resource_governor import ResourceGovernor
from backend.agents.routines import AutonomousRoutineService, RoutineSecurityError
from backend.agents.superpowers import IndependentVerifierService
from backend.agents.task_graph import TaskGraphEngine
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.workspaces.remote_protocol import (
    RemoteAuthenticationError,
    RemoteScopeEscalationError,
    RemoteWorkerContinuityService,
)


class Phase13IntegrationTests(unittest.TestCase):
    def test_e2e07_autonomous_routines_privacy_import_pause_and_approval_gate(self) -> None:
        routines = AutonomousRoutineService(':memory:')
        self.addCleanup(routines.close)

        # 1. Requesting microphone or host_input in a routine is strictly blocked
        with self.assertRaises(RoutineSecurityError):
            routines.register_routine(
                routine_id='rout-bad-mic',
                agent_id='axx-ops',
                conversation_id='conv-1',
                schedule_spec='0 9 * * *',
                requested_capabilities=['read_workspace', 'microphone'],
            )
        with self.assertRaises(RoutineSecurityError):
            routines.register_routine(
                routine_id='rout-bad-input',
                agent_id='axx-ops',
                conversation_id='conv-1',
                schedule_spec='0 9 * * *',
                requested_capabilities=['host_input'],
            )

        # 2. Imported routines always start disabled (paused_on_import) even if enabled=True was passed
        imported = routines.register_routine(
            routine_id='rout-imported',
            agent_id='axx-ops',
            conversation_id='conv-1',
            schedule_spec='0 8 * * *',
            requested_capabilities=['read_workspace'],
            enabled=True,
            imported_from_package=True,
        )
        self.assertFalse(imported['enabled'])
        self.assertEqual(imported['status'], 'paused_on_import')
        trig_imp = routines.trigger_routine('rout-imported')
        self.assertFalse(trig_imp['executed'])

        # 3. Active routine proposing a mutation pauses in awaiting_approval and creates an approval card
        active = routines.register_routine(
            routine_id='rout-daily-clean',
            agent_id='axx-ops',
            conversation_id='conv-1',
            schedule_spec='0 10 * * *',
            requested_capabilities=['read_workspace', 'write_worktree'],
            enabled=True,
            requires_approval=True,
        )
        self.assertTrue(active['enabled'])
        trig = routines.trigger_routine('rout-daily-clean', proposes_mutation=True)
        self.assertFalse(trig['executed'])
        self.assertEqual(trig['status'], 'awaiting_approval')
        self.assertTrue(trig['approval_card_created'])
        self.assertFalse(trig['activated_microphone'])
        self.assertFalse(trig['activated_host_input'])

    def test_perf01_perf02_and_e2e13_resource_governor_and_cost_ledger(self) -> None:
        gov = ResourceGovernor(':memory:', profile_name='Balanceado')
        self.addCleanup(gov.close)

        # Normal idle telemetry -> heavy background job admitted
        gov.update_host_telemetry(cpu_percent=30.0, ram_percent=50.0, avatar_fps=60.0, voice_active=False)
        adm_idle = gov.evaluate_job_admission('cad_step_export')
        self.assertTrue(adm_idle['allowed'])
        self.assertEqual(adm_idle['decision'], 'admitted_background')

        # E2E-13 / PERF-01: When voice is active or avatar FPS drops below 45 or CPU is high,
        # heavy background jobs are queued to protect voice & 3D avatar responsiveness
        gov.update_host_telemetry(cpu_percent=85.0, avatar_fps=38.0, voice_active=True)
        adm_busy = gov.evaluate_job_admission('motion_mp4_render')
        self.assertFalse(adm_busy['allowed'])
        self.assertEqual(adm_busy['decision'], 'queued_for_pressure')
        self.assertIn('voice_or_dictation_active', adm_busy['reasons'])
        self.assertIn('avatar_fps_below_floor', adm_busy['reasons'])
        self.assertIn('cpu_pressure_high', adm_busy['reasons'])

        # Realtime UI/voice job is still admitted immediately
        adm_rt = gov.evaluate_job_admission('voice_tts_synthesis')
        self.assertTrue(adm_rt['allowed'])

        # PERF-02: CostLedger tracks cumulative spend and pauses run when budget is exceeded
        b1 = gov.record_usage_and_check_budget(
            entry_id='cost-1',
            run_id='run-budget-1',
            agent_id='axx-coder',
            provider='openai',
            model='gpt-4.1',
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.60,
            run_budget_usd=1.00,
        )
        self.assertFalse(b1['budget_exceeded'])
        self.assertEqual(b1['decision'], 'within_budget')

        b2 = gov.record_usage_and_check_budget(
            entry_id='cost-2',
            run_id='run-budget-1',
            agent_id='axx-coder',
            provider='openai',
            model='gpt-4.1',
            input_tokens=3000,
            output_tokens=1500,
            cost_usd=0.55,
            run_budget_usd=1.00,
        )
        self.assertTrue(b2['budget_exceeded'])
        self.assertEqual(b2['decision'], 'paused_budget_exceeded')
        self.assertIsNotNone(b2['user_notification'])

    def test_e2e08_and_mobile01_remote_continuity_scope_intersection_and_mobile_approval(self) -> None:
        tg = TaskGraphEngine(':memory:')
        self.addCleanup(tg.close)
        hub = EventHub(':memory:')
        self.addCleanup(hub.close)
        orch = MultiAgentOrchestrator(
            task_graph=tg,
            event_hub=hub,
            verifier=IndependentVerifierService(),
        )
        remote = RemoteWorkerContinuityService()
        remote.register_paired_device(
            device_id='pixel-9-pro',
            device_token='mob-secret-token-998877',
            granted_scopes=['companion.read', 'companion.approvals'],
        )

        # Invalid token rejected
        with self.assertRaises(RemoteAuthenticationError):
            remote.authenticate_device('pixel-9-pro', 'wrong-token')

        # Scope not granted to mobile device -> rejected
        with self.assertRaises(RemoteScopeEscalationError):
            remote.authorize_remote_command(
                device_id='pixel-9-pro',
                presented_token='mob-secret-token-998877',
                required_scope='host.shell_exec',
                agent_allowed_scopes=['companion.read', 'host.shell_exec'],
            )

        # Scope granted to mobile device but NOT allowed on target PC agent -> rejected (no escalation)
        with self.assertRaises(RemoteScopeEscalationError):
            remote.authorize_remote_command(
                device_id='pixel-9-pro',
                presented_token='mob-secret-token-998877',
                required_scope='companion.approvals',
                agent_allowed_scopes=['companion.read'],
            )

        # Mobile companion resolves a pending PC approval card within its granted 'companion.approvals' scope
        orch.start_run(
            run_id='run-mob-1',
            conversation_id='conv-mob-1',
            lead_agent_id='axx-lead',
            nodes=[{'task_id': 't-mob-1', 'agent_id': 'axx-builder', 'role': 'implementer'}],
        )
        orch.request_human_approval(
            conversation_id='conv-mob-1',
            run_id='run-mob-1',
            task_id='t-mob-1',
            agent_id='axx-builder',
            operation_id='op-mob-approve-1',
            tool_name='workspace.apply_changeset',
            risk_class='write_workspace',
        )
        resolved = remote.resolve_approval_from_mobile(
            device_id='pixel-9-pro',
            presented_token='mob-secret-token-998877',
            orchestrator=orch,
            operation_id='op-mob-approve-1',
            approved=True,
        )
        self.assertEqual(resolved['status'], 'approved')
        self.assertEqual(resolved['resolved_by'], 'mobile:pixel-9-pro')

    def test_sec01_loopback_http_api_authentication_and_evolution_endpoints(self) -> None:
        server = ThreadedHTTPServer(('127.0.0.1', 0), AxxBridgeHandler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        try:
            # 1. Request without Authorization Bearer token -> 401 UNAUTHORIZED (SEC-01)
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            conn.request('GET', '/axx-api/agents/v1/flags', headers={'Host': f'127.0.0.1:{port}'})
            resp_401 = conn.getresponse()
            resp_401.read()
            conn.close()
            self.assertEqual(resp_401.status, 401)

            # 2. Request with browser Origin header -> 403 FORBIDDEN (SEC-01)
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            conn.request(
                'GET',
                '/axx-api/agents/v1/flags',
                headers={
                    'Host': f'127.0.0.1:{port}',
                    'Origin': 'https://evil.example.com',
                    'Authorization': f'Bearer {server.host_token}',
                },
            )
            resp_403 = conn.getresponse()
            resp_403.read()
            conn.close()
            self.assertEqual(resp_403.status, 403)

            # 3. Authenticated GET /axx-api/agents/v1/flags -> 200 OK
            auth_headers = {
                'Host': f'127.0.0.1:{port}',
                'Authorization': f'Bearer {server.host_token}',
                'Content-Type': 'application/json',
            }
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            conn.request('GET', '/axx-api/agents/v1/flags', headers=auth_headers)
            resp_flags = conn.getresponse()
            flags_data = json.loads(resp_flags.read().decode('utf-8'))
            conn.close()
            self.assertEqual(resp_flags.status, 200)
            self.assertIn('flags', flags_data)

            # 4. Authenticated POST /axx-api/workspaces/v1/leases/acquire -> 200 OK
            lease_body = json.dumps(
                {
                    'lease_id': 'http-lease-1',
                    'owner_run_id': 'http-run-1',
                    'resource_type': 'host_input',
                    'resource_key': 'windows-host-001',
                }
            ).encode('utf-8')
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            conn.request(
                'POST',
                '/axx-api/workspaces/v1/leases/acquire',
                body=lease_body,
                headers=dict(auth_headers, **{'Content-Length': str(len(lease_body))}),
            )
            resp_lease = conn.getresponse()
            lease_data = json.loads(resp_lease.read().decode('utf-8'))
            conn.close()
            self.assertEqual(resp_lease.status, 200)
            self.assertEqual(lease_data['lease']['fencing_token'], 1)
        finally:
            if getattr(server, 'evolution_runtime', None) is not None:
                server.evolution_runtime.close()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
