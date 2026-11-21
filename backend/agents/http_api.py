"""Additive HTTP API Router for AXX Evolution 3.0 (/axx-api/agents/v1/*, /axx-api/workspaces/v1/*, /axx-api/code/v1/*, /axx-api/spatial/v2/*) (PR-19 / Gate G13).

Enforces Invariants:
- SEC-01: Every endpoint is served behind AxxBridgeHandler._authorized() (loopback Host check,
  Origin block, and constant-time Bearer host token verification).
- I-09 / MOBILE-01: Strictly additive under /axx-api/*; zero modification to existing /v1/* companion
  endpoints or legacy /axx-api/* routes.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import urllib.parse
from typing import Any

from backend.agents.bindings import ConversationBindingService
from backend.agents.events import EventHub
from backend.agents.orchestrator import MultiAgentOrchestrator
from backend.agents.profiles import validate_agent_profile
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
from backend.spatial.diagram_studio import auto_layout_diagram, check_diagram_qa
from backend.spatial.diorama_engine import evaluate_diorama_qa
from backend.spatial.patches import apply_scene_patch
from backend.spatial.render_jobs import freeze_scene_at
from backend.spatial.scene_document import validate_scene_document_v2
from backend.workspaces.browser_sessions import BrowserSessionManager
from backend.workspaces.focus_guard import AttentionGuardian
from backend.workspaces.leases import ResourceLeaseManager
from backend.workspaces.manager import BackgroundInteractionRouter, VirtualCursorTelemetryService
from backend.workspaces.remote_protocol import RemoteWorkerContinuityService
from backend.workspaces.vm_provider import IsolatedVMProvider


class EvolutionHttpRuntime:
    """In-memory / SQLite runtime container backing the additive Evolution 3.0 HTTP routes."""

    def __init__(self, db_path: str | Path = ':memory:', *, storage_dir: str | Path | None = None):
        self.db_path = str(db_path)
        self.base_dir = Path(storage_dir) if storage_dir else Path(tempfile.mkdtemp(prefix='axx_evo3_'))
        self.flags = EvolutionFeatureFlags(self.db_path)
        self.registry = AgentRegistry(self.db_path)
        self.bindings = ConversationBindingService(self.registry)
        self.task_graph = TaskGraphEngine(self.db_path)
        self.verifier = IndependentVerifierService()
        self.event_hub = EventHub(self.db_path)
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
        self.vms = IsolatedVMProvider(self.leases, allow_simulated_sandbox=True)
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
            self.handler.server.evolution_runtime = EvolutionHttpRuntime()
        self.rt: EvolutionHttpRuntime = self.handler.server.evolution_runtime

    def get(self, path: str) -> bool:
        if not path.startswith(('/axx-api/agents/v1/', '/axx-api/workspaces/v1/', '/axx-api/code/v1/', '/axx-api/spatial/v2/')):
            return False

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.handler.path).query, keep_blank_values=True)
        if path == '/axx-api/agents/v1/profiles':
            self.handler._send_json(200, {'profiles': self.rt.registry.list_profiles()})
            return True
        if path == '/axx-api/agents/v1/flags':
            self.handler._send_json(200, {'flags': self.rt.flags.list_flags()})
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

        # 1. Agents & Orchestration endpoints
        if path == '/axx-api/agents/v1/profiles':
            validated = validate_agent_profile(body)
            created = self.rt.registry.register_profile(validated)
            self.handler._send_json(200, {'profile': created})
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
        if path == '/axx-api/agents/v1/routines':
            routine = self.rt.routines.register_routine(
                routine_id=body['routine_id'],
                agent_id=body['agent_id'],
                conversation_id=body['conversation_id'],
                schedule_spec=body['schedule_spec'],
                requested_capabilities=body.get('requested_capabilities', []),
                enabled=bool(body.get('enabled', True)),
                imported_from_package=bool(body.get('imported_from_package', False)),
            )
            self.handler._send_json(200, {'routine': routine})
            return True
        if path == '/axx-api/agents/v1/governor/evaluate':
            if 'telemetry' in body and isinstance(body['telemetry'], dict):
                self.rt.governor.update_host_telemetry(**body['telemetry'])
            decision = self.rt.governor.evaluate_job_admission(body['job_class'])
            self.handler._send_json(200, decision)
            return True

        # 2. Workspaces & Computer Use endpoints
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
        if path == '/axx-api/workspaces/v1/focus-guard/revoke':
            rev = self.rt.focus_guard.trigger_emergency_hotkey_revocation()
            self.handler._send_json(200, rev)
            return True

        # 3. Code Studio endpoints
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
            )
            self.handler._send_json(200, saved)
            return True

        # 4. Spatial Studio v2 endpoints
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
            self.handler._send_json(200, {'diagram': laid_out, 'qa': qa})
            return True
        if path == '/axx-api/spatial/v2/motion/freeze':
            frozen = freeze_scene_at(body['scene'], t_sec=float(body['t_sec']), seed=int(body.get('seed', 42)))
            self.handler._send_json(200, frozen)
            return True
        if path == '/axx-api/spatial/v2/diorama/qa':
            qa = evaluate_diorama_qa(body['scene'])
            self.handler._send_json(200, qa)
            return True

        self.handler._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': f'Unknown Evolution POST endpoint: {path}'}})
        return True
