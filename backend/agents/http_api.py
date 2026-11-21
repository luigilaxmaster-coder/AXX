"""Additive HTTP API Router for AXX Evolution 3.0 (/axx-api/agents/v1/*, /axx-api/workspaces/v1/*, /axx-api/code/v1/*, /axx-api/spatial/v2/*) (PR-19 / Gate G13).

Enforces Invariants:
- SEC-01: Every endpoint is served behind AxxBridgeHandler._authorized() (loopback Host check,
  Origin block, and constant-time Bearer host token verification).
- I-01: Multi-agent task executions route through ActionExecutor / CommandService.
- I-09 / MOBILE-01: Strictly additive under /axx-api/*; zero modification to existing /v1/* companion
  endpoints or legacy /axx-api/* routes.
"""
from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import urllib.parse
from typing import Any

from backend.agents.bindings import ConversationBindingService
from backend.agents.events import EventHub
from backend.agents.orchestrator import MultiAgentOrchestrator
from backend.agents.profiles import validate_agent_profile
from backend.agents.recovery import MultiAgentRecoveryService
from backend.agents.registry import AgentRegistry
from backend.agents.resource_governor import ResourceGovernor
from backend.agents.routines import AutonomousRoutineService
from backend.agents.superpowers import IndependentVerifierService
from backend.agents.task_graph import TaskGraphEngine
from backend.code_studio.artifact_link import CodeArtifactLinkService
from backend.code_studio.debug_adapters import DebugAdapterManager
from backend.code_studio.git_workspace import GitWorkspaceService
from backend.code_studio.indexer import CodeStructuralIndexer
from backend.code_studio.language_servers import LanguageServerManager
from backend.code_studio.patch_engine import CodePatchEngine
from backend.code_studio.projects import CodeProjectService
from backend.code_studio.test_runner import SupervisedTestRunner
from backend.evolution_flags import EvolutionFeatureFlags
from backend.spatial.asset_registry import AssetRegistry
from backend.spatial.cad_contracts import IsolatedCadWorker
from backend.spatial.diagram_studio import auto_layout_diagram, check_diagram_qa, export_diagram_svg
from backend.spatial.diorama_engine import evaluate_diorama_qa
from backend.spatial.patches import apply_scene_patch
from backend.spatial.render_jobs import export_motion_mp4, freeze_scene_at
from backend.spatial.scene_document import validate_scene_document_v2
from backend.workspaces.browser_sessions import BrowserSessionManager
from backend.workspaces.focus_guard import AttentionGuardian
from backend.workspaces.leases import ResourceLeaseManager
from backend.workspaces.manager import BackgroundInteractionRouter, VirtualCursorTelemetryService
from backend.workspaces.remote_protocol import RemoteWorkerContinuityService
from backend.workspaces.vm_provider import IsolatedVMProvider


class EvolutionHttpRuntime:
    """SQLite-backed runtime container backing the additive Evolution 3.0 HTTP routes."""

    def __init__(
        self,
        db_path: str | Path = ':memory:',
        *,
        storage_dir: str | Path | None = None,
        chat_store=None,
        action_executor=None,
        command_service=None,
        magic_pen=None,
        speech_service=None,
        identity_store=None,
        allow_simulated_sandbox: bool = False,
    ):
        self.db_path = str(db_path)
        if storage_dir is not None:
            self.base_dir = Path(storage_dir).resolve()
        elif self.db_path != ':memory:':
            self.base_dir = (Path(self.db_path).resolve().parent / 'evolution3').resolve()
        else:
            self.base_dir = Path(tempfile.mkdtemp(prefix='axx_evo3_'))
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.chat_store = chat_store
        self.action_executor = action_executor
        self.command_service = command_service
        self.magic_pen = magic_pen
        self.speech_service = speech_service
        self.identity_store = identity_store

        self.flags = EvolutionFeatureFlags(self.db_path)
        if self.magic_pen is not None:
            self.magic_pen.evolution_flags = self.flags

        self.registry = AgentRegistry(self.db_path)
        self.bindings = ConversationBindingService(self.registry, chat_store=self.chat_store)
        if self.chat_store is not None and hasattr(self.chat_store, 'register_forget_hook'):
            self.chat_store.register_forget_hook(self.bindings.scrub_forgotten_conversation)

        self.task_graph = TaskGraphEngine(self.db_path, action_executor=self.action_executor)
        self.verifier = IndependentVerifierService(action_executor=self.action_executor)
        self.event_hub = EventHub(self.db_path)
        self.recovery = MultiAgentRecoveryService(self.task_graph, self.event_hub)
        self.orchestrator = MultiAgentOrchestrator(
            task_graph=self.task_graph,
            event_hub=self.event_hub,
            verifier=self.verifier,
            bindings=self.bindings,
        )
        self.routines = AutonomousRoutineService(self.db_path)
        self.governor = ResourceGovernor(self.db_path)

        self.leases = ResourceLeaseManager(self.db_path)
        self.focus_guard = AttentionGuardian(self.leases)
        self.browsers = BrowserSessionManager(self.leases, profiles_root=self.base_dir / 'browser_profiles')
        self.vms = IsolatedVMProvider(self.leases, allow_simulated_sandbox=allow_simulated_sandbox)
        self.cursors = VirtualCursorTelemetryService()
        self.router = BackgroundInteractionRouter(
            lease_manager=self.leases,
            focus_guard=self.focus_guard,
            browser_manager=self.browsers,
            vm_provider=self.vms,
            cursor_telemetry=self.cursors,
        )
        self.remote = RemoteWorkerContinuityService()

        self.code_projects = CodeProjectService(self.db_path)
        self.code_patches = CodePatchEngine(self.code_projects)
        self.code_git = GitWorkspaceService(self.code_projects, self.code_patches, worktrees_base_dir=self.base_dir / 'worktrees')
        self.code_tests = SupervisedTestRunner(self.code_projects)
        self.code_indexer = CodeStructuralIndexer(self.code_projects)
        self.code_lsp = LanguageServerManager(self.code_projects, self.code_indexer)
        self.code_dap = DebugAdapterManager(self.code_projects)
        self.code_links = CodeArtifactLinkService(self.code_projects)

        self.cad_worker = IsolatedCadWorker()
        self.assets = AssetRegistry(self.db_path, storage_root=self.base_dir / 'assets')

    def close(self) -> None:
        for svc in (
            self.flags,
            self.registry,
            self.task_graph,
            self.event_hub,
            self.routines,
            self.governor,
            self.leases,
            self.code_projects,
            self.assets,
        ):
            close_fn = getattr(svc, 'close', None)
            if callable(close_fn):
                close_fn()


class EvolutionHTTP:
    """Dispatches additive /axx-api/agents/v1/*, /axx-api/workspaces/v1/*, /axx-api/code/v1/*, and /axx-api/spatial/v2/* endpoints."""

    def __init__(self, handler):
        self.handler = handler
        if getattr(self.handler.server, 'evolution_runtime', None) is None:
            detected_db = (
                getattr(getattr(self.handler, 'chats', None), 'db_path', None)
                or getattr(getattr(self.handler, 'executor', None), 'db_path', None)
                or ':memory:'
            )
            self.handler.server.evolution_runtime = EvolutionHttpRuntime(
                db_path=detected_db,
                chat_store=getattr(self.handler, 'chats', None),
                action_executor=getattr(self.handler, 'executor', None),
                command_service=getattr(self.handler, 'commands', None),
                magic_pen=getattr(self.handler, 'magic_pen', None),
                speech_service=getattr(self.handler, 'speech', None),
                identity_store=getattr(self.handler, 'identity', None),
            )
        self.rt: EvolutionHttpRuntime = self.handler.server.evolution_runtime

    def get(self, path: str) -> bool:
        if not path.startswith(('/axx-api/agents/v1/', '/axx-api/workspaces/v1/', '/axx-api/code/v1/', '/axx-api/spatial/v2/')):
            return False

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.handler.path).query, keep_blank_values=True)
        if path == '/axx-api/agents/v1/profiles':
            agent_id = query.get('agent_id', [None])[0]
            if agent_id:
                self.handler._send_json(200, {'profile': self.rt.registry.get_profile(agent_id)})
            else:
                include_disabled = query.get('include_disabled', ['false'])[0].lower() == 'true'
                self.handler._send_json(200, {'profiles': self.rt.registry.list_profiles(include_disabled=include_disabled)})
            return True
        if path == '/axx-api/agents/v1/profiles/export':
            agent_id = query.get('agent_id', [''])[0]
            if not agent_id:
                raise ValueError('agent_id is required')
            self.handler._send_json(200, self.rt.registry.export_agent_package(agent_id))
            return True
        if path == '/axx-api/agents/v1/bindings':
            conv_id = query.get('conversation_id', [''])[0]
            if not conv_id:
                raise ValueError('conversation_id is required')
            self.handler._send_json(200, {'bindings': self.rt.bindings.list_conversation_agents(conv_id)})
            return True
        if path == '/axx-api/agents/v1/flags':
            self.handler._send_json(200, {'flags': self.rt.flags.list_flags()})
            return True
        if path == '/axx-api/agents/v1/runs/status':
            run_id = query.get('run_id', [''])[0]
            if not run_id:
                raise ValueError('run_id is required')
            self.handler._send_json(200, self.rt.task_graph.get_graph(run_id))
            return True
        if path == '/axx-api/agents/v1/routines':
            conv_id = query.get('conversation_id', [None])[0]
            self.handler._send_json(200, {'routines': self.rt.routines.list_routines(conversation_id=conv_id)})
            return True
        if path == '/axx-api/agents/v1/events/sse':
            conv_id = query.get('conversation_id', [''])[0]
            last_id = query.get('last_event_id', [None])[0] or self.handler.headers.get('Last-Event-ID')
            if not conv_id:
                raise ValueError('conversation_id is required')
            replay = self.rt.event_hub.replay_sse(conv_id, last_event_id=last_id)
            self.handler._send_json(200, replay)
            return True
        if path == '/axx-api/agents/v1/events/flight-recorder':
            conv_id = query.get('conversation_id', [''])[0]
            run_id = query.get('run_id', [None])[0]
            if not conv_id:
                raise ValueError('conversation_id is required')
            self.handler._send_json(200, self.rt.event_hub.export_flight_recorder(conv_id, run_id=run_id))
            return True
        if path == '/axx-api/workspaces/v1/vm/probe':
            self.handler._send_json(200, self.rt.vms.probe())
            return True

        self.handler._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': f'Unknown Evolution GET endpoint: {path}'}})
        return True

    def post(self, path: str, body: dict[str, Any]) -> bool:
        if not path.startswith(('/axx-api/agents/v1/', '/axx-api/workspaces/v1/', '/axx-api/code/v1/', '/axx-api/spatial/v2/')):
            return False

        # 1. Feature Flags
        if path == '/axx-api/agents/v1/flags/set':
            updated = self.rt.flags.set_flag(
                body['flag_id'],
                enabled=bool(body['enabled']),
                expected_revision=int(body['expected_revision']),
                actor=str(body.get('actor', 'user')),
                reason=str(body.get('reason', 'api_flag_update')),
                gate_receipt_ref=str(body.get('gate_receipt_ref', '')),
            )
            self.handler._send_json(200, {'flag': updated})
            return True

        # 2. Agent Profiles & Chat Bindings
        if path == '/axx-api/agents/v1/profiles':
            validated = validate_agent_profile(body)
            created = self.rt.registry.create_profile(validated)
            self.handler._send_json(200, {'profile': created})
            return True
        if path == '/axx-api/agents/v1/profiles/update':
            updated = self.rt.registry.update_profile(
                body['agent_id'],
                body['patch'],
                expected_revision=int(body['expected_revision']),
            )
            self.handler._send_json(200, {'profile': updated})
            return True
        if path == '/axx-api/agents/v1/profiles/disable':
            disabled = self.rt.registry.disable_profile(body['agent_id'])
            self.handler._send_json(200, {'profile': disabled})
            return True
        if path == '/axx-api/agents/v1/profiles/import':
            imported = self.rt.registry.import_agent_package(
                body['package'],
                new_agent_id=body.get('new_agent_id'),
            )
            self.handler._send_json(200, {'profile': imported})
            return True
        if path == '/axx-api/agents/v1/bindings/convert':
            converted = self.rt.bindings.convert_chat_to_agent_or_team(
                body['conversation_id'],
                lead_agent_id=body['lead_agent_id'],
                member_agent_ids=body.get('member_agent_ids'),
            )
            self.handler._send_json(200, converted)
            return True
        if path == '/axx-api/agents/v1/bindings/switch':
            switched = self.rt.bindings.switch_agent(
                body['conversation_id'],
                body['new_agent_id'],
                has_active_run=bool(body.get('has_active_run', False)),
                actor=str(body.get('actor', 'user')),
            )
            self.handler._send_json(200, switched)
            return True

        # 3. Multi-Agent Runs, Handoffs, Approvals & Recovery
        if path == '/axx-api/agents/v1/runs/start':
            run_info = self.rt.orchestrator.start_run(
                run_id=body['run_id'],
                conversation_id=body['conversation_id'],
                lead_agent_id=body['lead_agent_id'],
                nodes=body['nodes'],
                goal_spec=body.get('goal_spec'),
                budget_usd=float(body.get('budget_usd', 5.0)),
            )
            self.handler._send_json(200, run_info)
            return True
        if path == '/axx-api/agents/v1/runs/execute-task':
            task_id = body['task_id']
            lease_id = body.get('lease_id', f'lease-{task_id}')
            verifier_id = body.get('verifier_agent_id', 'axx-verifier')
            verifying_node = self.rt.task_graph.dispatch_task_via_executor(
                task_id,
                lease_id=lease_id,
                delivery_mode=body.get('delivery_mode'),
            )
            if verifying_node['state'] == 'verifying':
                verdict = self.rt.verifier.verify_task(verifying_node, verifier_agent_id=verifier_id)
                if verdict.get('verified'):
                    final_node = self.rt.task_graph.complete_verified_task(task_id, verifier_evidence=verdict)
                else:
                    final_node = verifying_node | {'verifier_verdict': verdict}
            else:
                final_node = verifying_node
            self.handler._send_json(200, {'task': final_node})
            return True
        if path == '/axx-api/agents/v1/runs/cancel':
            cancelled = self.rt.task_graph.cancel_task(
                body['task_id'],
                reason=str(body.get('reason', 'Cancelled via API')),
            )
            self.handler._send_json(200, {'task': cancelled})
            return True
        if path == '/axx-api/agents/v1/runs/reconcile':
            summary = self.rt.recovery.reconcile_interrupted_run(
                run_id=body['run_id'],
                conversation_id=body['conversation_id'],
                lead_agent_id=body['lead_agent_id'],
            )
            self.handler._send_json(200, summary)
            return True
        if path == '/axx-api/agents/v1/handoffs':
            res = self.rt.orchestrator.delegate_handoff(
                handoff_payload=body['handoff'],
                parent_grants=body.get('parent_grants', []),
                context_items=body.get('context_items', []),
                untrusted_notes=body.get('untrusted_notes', ''),
            )
            self.handler._send_json(200, res)
            return True
        if path == '/axx-api/agents/v1/approvals/request':
            card = self.rt.orchestrator.request_human_approval(
                conversation_id=body['conversation_id'],
                run_id=body['run_id'],
                task_id=body['task_id'],
                agent_id=body['agent_id'],
                operation_id=body['operation_id'],
                tool_name=body['tool_name'],
                risk_class=body.get('risk_class', 'write_workspace'),
                parameters=body.get('parameters'),
            )
            self.handler._send_json(200, {'approval': card})
            return True
        if path == '/axx-api/agents/v1/approvals/resolve':
            resolved = self.rt.orchestrator.resolve_human_approval(
                operation_id=body['operation_id'],
                approved=bool(body['approved']),
                actor=str(body.get('actor', 'user')),
            )
            self.handler._send_json(200, {'approval': resolved})
            return True

        # 4. Autonomous Routines & ResourceGovernor
        if path == '/axx-api/agents/v1/routines':
            routine = self.rt.routines.register_routine(
                routine_id=body['routine_id'],
                agent_id=body['agent_id'],
                conversation_id=body['conversation_id'],
                schedule_spec=body['schedule_spec'],
                requested_capabilities=body.get('requested_capabilities', []),
                enabled=bool(body.get('enabled', True)),
                requires_approval=bool(body.get('requires_approval', True)),
                imported_from_package=bool(body.get('imported_from_package', False)),
            )
            self.handler._send_json(200, {'routine': routine})
            return True
        if path == '/axx-api/agents/v1/routines/trigger':
            trig = self.rt.routines.trigger_routine(
                body['routine_id'],
                proposes_mutation=bool(body.get('proposes_mutation', True)),
            )
            self.handler._send_json(200, trig)
            return True
        if path == '/axx-api/agents/v1/routines/cancel':
            cancelled = self.rt.routines.cancel_routine(body['routine_id'])
            self.handler._send_json(200, {'routine': cancelled})
            return True
        if path == '/axx-api/agents/v1/routines/reconcile':
            self.handler._send_json(200, self.rt.routines.reconcile_on_startup())
            return True
        if path == '/axx-api/agents/v1/governor/evaluate':
            if 'telemetry' in body and isinstance(body['telemetry'], dict):
                self.rt.governor.update_host_telemetry(**body['telemetry'])
            decision = self.rt.governor.evaluate_job_admission(body['job_class'])
            self.handler._send_json(200, decision)
            return True
        if path == '/axx-api/agents/v1/governor/budget':
            budget_res = self.rt.governor.record_usage_and_check_budget(
                entry_id=body['entry_id'],
                run_id=body['run_id'],
                agent_id=body['agent_id'],
                provider=body.get('provider', 'local'),
                model=body.get('model', 'default'),
                input_tokens=int(body.get('input_tokens', 0)),
                output_tokens=int(body.get('output_tokens', 0)),
                cost_usd=float(body.get('cost_usd', 0.0)),
                run_budget_usd=float(body.get('run_budget_usd', 1.0)),
            )
            self.handler._send_json(200, budget_res)
            return True

        # 5. Workspaces, Leases, FocusGuard, Browsers, UIA & VM
        if path == '/axx-api/workspaces/v1/leases/acquire':
            lease = self.rt.leases.acquire_lease(
                lease_id=body['lease_id'],
                owner_run_id=body['owner_run_id'],
                resource_type=body['resource_type'],
                resource_key=body['resource_key'],
                ttl_ms=int(body.get('ttl_ms', 60000)),
            )
            self.handler._send_json(200, {'lease': lease})
            return True
        if path == '/axx-api/workspaces/v1/leases/release':
            released = self.rt.leases.release_lease(body['lease_id'])
            self.handler._send_json(200, {'lease': released})
            return True
        if path == '/axx-api/workspaces/v1/focus-guard/revoke':
            rev = self.rt.focus_guard.trigger_emergency_hotkey_revocation()
            self.handler._send_json(200, rev)
            return True
        if path == '/axx-api/workspaces/v1/browsers/session':
            sess = self.rt.browsers.create_isolated_session(
                session_id=body['session_id'],
                profile_id=body['profile_id'],
                agent_id=body['agent_id'],
            )
            self.handler._send_json(200, {'session': sess})
            return True
        if path == '/axx-api/workspaces/v1/browsers/act':
            res = self.rt.browsers.execute_dom_action(
                session_id=body['session_id'],
                owner_run_id=body['owner_run_id'],
                fencing_token=int(body['fencing_token']),
                action=body['action'],
                target=body.get('target', ''),
                value=body.get('value', ''),
            )
            self.handler._send_json(200, res)
            return True
        if path == '/axx-api/workspaces/v1/uia/act':
            res = self.rt.router.execute_uia_background_action(
                owner_run_id=body['owner_run_id'],
                fencing_token=int(body['fencing_token']),
                leased_window_key=body['leased_window_key'],
                live_window_info=body['live_window_info'],
                uia_pattern=body['uia_pattern'],
                control_id=body['control_id'],
                value=body.get('value'),
                requires_physical_focus=bool(body.get('requires_physical_focus', False)),
                attempted_silent_sendinput_fallback=bool(body.get('attempted_silent_sendinput_fallback', False)),
                foreground_policy=body.get('foreground_policy', 'queue'),
                approval_token=body.get('approval_token'),
            )
            self.handler._send_json(200, res)
            return True
        if path == '/axx-api/workspaces/v1/vm/create':
            vm = self.rt.vms.create(
                vm_id=body['vm_id'],
                backend=body.get('backend'),
                memory_mb=int(body.get('memory_mb', 2048)),
                vcpus=int(body.get('vcpus', 2)),
            )
            self.handler._send_json(200, {'vm': vm})
            return True
        if path == '/axx-api/workspaces/v1/vm/start':
            vm = self.rt.vms.start(body['vm_id'])
            self.handler._send_json(200, {'vm': vm})
            return True
        if path == '/axx-api/workspaces/v1/vm/act':
            res = self.rt.vms.act(
                vm_id=body['vm_id'],
                owner_run_id=body['owner_run_id'],
                fencing_token=int(body['fencing_token']),
                action_type=body['action_type'],
                payload=body.get('payload'),
            )
            self.handler._send_json(200, res)
            return True
        if path == '/axx-api/workspaces/v1/vm/snapshot':
            snap = self.rt.vms.snapshot(body['vm_id'], snapshot_label=body.get('snapshot_label', 'snap'))
            self.handler._send_json(200, {'snapshot': snap})
            return True
        if path == '/axx-api/workspaces/v1/vm/stop':
            vm = self.rt.vms.stop(body['vm_id'])
            self.handler._send_json(200, {'vm': vm})
            return True
        if path == '/axx-api/workspaces/v1/vm/destroy':
            vm = self.rt.vms.destroy(body['vm_id'])
            self.handler._send_json(200, {'vm': vm})
            return True

        # 6. Code Studio endpoints
        if path == '/axx-api/code/v1/projects/register':
            proj = self.rt.code_projects.register_project(body['project_id'], body['project_root'])
            self.handler._send_json(200, proj)
            return True
        if path == '/axx-api/code/v1/documents/read':
            doc = self.rt.code_projects.read_document(body['project_id'], body['path'])
            self.handler._send_json(200, doc)
            return True
        if path == '/axx-api/code/v1/documents/save':
            saved = self.rt.code_projects.save_document(
                body['project_id'],
                body['path'],
                body['new_content'],
                expected_sha256=body['expected_sha256'],
                encoding=body.get('encoding'),
                line_ending=body.get('line_ending'),
            )
            self.handler._send_json(200, saved)
            return True
        if path == '/axx-api/code/v1/documents/restore':
            restored = self.rt.code_projects.restore_snapshot(
                body['project_id'],
                body['path'],
                body['target_sha256'],
            )
            self.handler._send_json(200, restored)
            return True
        if path == '/axx-api/code/v1/changesets/propose':
            cs = self.rt.code_patches.propose_changeset(
                changeset_id=body['changeset_id'],
                project_id=body['project_id'],
                workspace_id=body['workspace_id'],
                agent_id=body['agent_id'],
                base_commit=body['base_commit'],
                branch=body['branch'],
                file_edits=body['file_edits'],
                test_report_refs=body.get('test_report_refs'),
                approval_operation_id=body.get('approval_operation_id'),
            )
            self.handler._send_json(200, {'changeset': cs})
            return True
        if path == '/axx-api/code/v1/changesets/apply':
            applied = self.rt.code_patches.apply_changeset(body['changeset_id'])
            self.handler._send_json(200, {'changeset': applied})
            return True
        if path == '/axx-api/code/v1/changesets/rollback':
            rolled = self.rt.code_patches.rollback_changeset(body['changeset_id'], force=bool(body.get('force', False)))
            self.handler._send_json(200, rolled)
            return True
        if path == '/axx-api/code/v1/worktrees/create':
            wt = self.rt.code_git.create_agent_worktree(
                workspace_id=body['workspace_id'],
                project_id=body['project_id'],
                agent_id=body['agent_id'],
                task_slug=body['task_slug'],
            )
            self.handler._send_json(200, {'worktree': wt})
            return True
        if path == '/axx-api/code/v1/worktrees/propose-apply':
            applied = self.rt.code_git.propose_and_apply_in_worktree(
                changeset_id=body['changeset_id'],
                workspace_id=body['workspace_id'],
                file_edits=body['file_edits'],
                test_report_refs=body.get('test_report_refs'),
            )
            self.handler._send_json(200, {'changeset': applied})
            return True
        if path == '/axx-api/code/v1/worktrees/integrate':
            integrated = self.rt.code_git.integrate_into_primary_workspace(body['changeset_id'])
            self.handler._send_json(200, {'changeset': integrated})
            return True
        if path == '/axx-api/code/v1/worktrees/remove':
            removed = self.rt.code_git.remove_agent_worktree(body['workspace_id'])
            self.handler._send_json(200, removed)
            return True
        if path == '/axx-api/code/v1/tests/run':
            receipt = self.rt.code_tests.run_test_command(
                report_id=body['report_id'],
                project_id=body['project_id'],
                workspace_id=body['workspace_id'],
                command=body['command'],
            )
            self.handler._send_json(200, {'receipt': receipt})
            return True
        if path == '/axx-api/code/v1/index':
            summary = self.rt.code_indexer.index_project(body['project_id'])
            self.handler._send_json(200, summary)
            return True

        # 7. Spatial Studio v2 endpoints
        if path == '/axx-api/spatial/v2/scenes/validate':
            scene = validate_scene_document_v2(body)
            self.handler._send_json(200, {'valid': True, 'scene': scene})
            return True
        if path == '/axx-api/spatial/v2/scenes/patch':
            patched = apply_scene_patch(body['scene'], body['patch'])
            self.handler._send_json(200, patched)
            return True
        if path == '/axx-api/spatial/v2/diagrams/layout':
            laid_out = auto_layout_diagram(body['diagram'])
            qa = check_diagram_qa(laid_out)
            svg = export_diagram_svg(laid_out)
            self.handler._send_json(200, {'diagram': laid_out, 'qa': qa, 'svg': svg})
            return True
        if path == '/axx-api/spatial/v2/cad/build':
            cad_out = self.rt.base_dir / 'cad_outputs' / str(body.get('task', {}).get('task_id', 'cad-task'))
            cad_out.mkdir(parents=True, exist_ok=True)
            result = self.rt.cad_worker.run_task(body['task'], output_dir=cad_out)
            self.handler._send_json(200, result)
            return True
        if path == '/axx-api/spatial/v2/motion/freeze':
            frozen = freeze_scene_at(body['scene'], t_sec=float(body['t_sec']), seed=int(body.get('seed', 42)))
            self.handler._send_json(200, frozen)
            return True
        if path == '/axx-api/spatial/v2/motion/export-mp4':
            out_file = self.rt.base_dir / 'renders' / f"{body['scene'].get('document_id', 'scene')}.mp4"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            mp4_res = export_motion_mp4(
                body['scene'],
                output_path=out_file,
                fps=int(body.get('fps', 12)),
                seed=int(body.get('seed', 42)),
                narration_text=body.get('narration_text'),
            )
            self.handler._send_json(200, mp4_res)
            return True
        if path == '/axx-api/spatial/v2/assets/register':
            raw_bytes = base64.b64decode(body['content_b64']) if 'content_b64' in body else str(body.get('content_text', '')).encode('utf-8')
            asset = self.rt.assets.register_asset(
                raw_bytes=raw_bytes,
                filename=body['filename'],
                license_spdx=body['license_spdx'],
                provenance_source=body['provenance_source'],
                credit_text=body.get('credit_text', ''),
                triangle_count=int(body.get('triangle_count', 100)),
                lods=body.get('lods', ['lod0']),
            )
            self.handler._send_json(200, {'asset': asset})
            return True
        if path == '/axx-api/spatial/v2/diorama/qa':
            qa = evaluate_diorama_qa(body['scene'])
            self.handler._send_json(200, qa)
            return True

        self.handler._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': f'Unknown Evolution POST endpoint: {path}'}})
        return True
