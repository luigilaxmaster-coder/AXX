"""Comprehensive Independent Functional Audit Suite for AXX Evolution 3.0 (Phases 0-13 / Gates G0-G13).

Exercises real HTTP server instances, on-disk SQLite databases across full server restarts,
real ActionExecutor tool execution, real Git repositories and worktrees on disk, real CAD
worker subprocesses producing STEP/GLB files, real WSL2 Linux VM execution and cleanup,
and real Spanish voice normalization/prosody and Windows TTS service integration.
"""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.magic_pen import MagicPenService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.speech.prosody import ProsodyAnalyzer
from backend.speech.speech_text import prepare_spoken_text
from backend.speech.windows_tts import WindowsSpeechService
from backend.sync.identity_sync import IdentityStore
from backend.agents.http_api import EvolutionHttpRuntime


class _HttpTestClient:
    def __init__(self, port: int, token: str):
        self.port = port
        self.token = token

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        headers = {
            'Host': f'127.0.0.1:{self.port}',
            'Authorization': f'Bearer {self.token}',
        }
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
            headers['Content-Length'] = str(len(payload))
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=25)
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode('utf-8')
            return resp.status, (json.loads(raw) if raw else {})
        finally:
            conn.close()


def _start_bound_server(state_path: Path, storage_dir: Path):
    chats = ChatStore(state_path)
    identity = IdentityStore(db_path=state_path)
    executor = ActionExecutor(db_path=state_path, workspace_root=storage_dir / 'artifacts')
    commands = CommandService(executor)
    magic_pen = MagicPenService(executor.workspace_root, None)

    handler_cls = type(
        'AuditAxxHandler',
        (AxxBridgeHandler,),
        {
            'chats': chats,
            'identity': identity,
            'executor': executor,
            'commands': commands,
            'magic_pen': magic_pen,
        },
    )
    server = ThreadedHTTPServer(('127.0.0.1', 0), handler_cls)
    server.evolution_runtime = EvolutionHttpRuntime(
        db_path=state_path,
        storage_dir=storage_dir / 'evolution3',
        chat_store=chats,
        action_executor=executor,
        command_service=commands,
        magic_pen=magic_pen,
        identity_store=identity,
        allow_simulated_sandbox=False,
    )
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    thread.start()
    return server, chats, identity, executor, commands, magic_pen


def _stop_bound_server(server, chats, identity, executor, commands, magic_pen) -> None:
    if getattr(server, 'evolution_runtime', None) is not None:
        server.evolution_runtime.close()
    server.shutdown()
    server.server_close()
    for svc in (magic_pen, commands, chats, identity, executor):
        close_fn = getattr(svc, 'close', None)
        if callable(close_fn):
            close_fn()


class Evolution3FullFunctionalAuditTests(unittest.TestCase):
    def test_01_agent_designer_chat_conversion_and_routines_persist_across_server_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_db = tmp_path / 'state.db'

            # Boot Server Instance #1 on state.db
            srv1, chats1, id1, exec1, cmd1, mp1 = _start_bound_server(state_db, tmp_path)
            try:
                client1 = _HttpTestClient(srv1.server_port, srv1.host_token)

                # Seed realistic legacy v0.22.52 chat and global studio identity
                id1.save_studio_identity({'version': 1, 'studio': {'form': 'Core', 'palette': 'Obsidian'}})
                created_chat = chats1.mutate('create', {'title': 'Proyecto Legado'})
                chat_id = created_chat['id']
                chats1.mutate(
                    'save',
                    {
                        'id': chat_id,
                        'title': 'Proyecto Legado',
                        'messages': [{'id': 'm1', 'role': 'user', 'text': 'Hola Axx', 'status': 'complete', 'at': chats1.clock()}],
                        'draft': 'borrador pendiente',
                    },
                )

                # Toggle feature flags ON via HTTP API (Requirement 1.6)
                status, flags_before = client1.request('GET', '/axx-api/agents/v1/flags')
                self.assertEqual(status, 200)
                for flag_name in ('agent_profiles_v1', 'team_chat_v1', 'code_studio_v1'):
                    st, res = client1.request(
                        'POST',
                        '/axx-api/agents/v1/flags/set',
                        {
                            'flag_id': flag_name,
                            'enabled': True,
                            'expected_revision': 1,
                            'reason': 'functional_audit_activation',
                            'gate_receipt_ref': 'GATE_G13',
                        },
                    )
                    self.assertEqual(st, 200)
                    self.assertTrue(res['flag']['enabled'])

                # Create two independent agents in Agent Designer
                for agent_id, name, form_id, palette_id, role in (
                    ('agent-architect', 'Axx Arquitecto', 17, 5, 'architect'),
                    ('agent-verifier', 'Axx Verificador', 14, 1, 'verifier'),
                ):
                    st, prof_res = client1.request(
                        'POST',
                        '/axx-api/agents/v1/profiles',
                        {
                            'schema_version': '1.0',
                            'agent_id': agent_id,
                            'revision': 1,
                            'name': name,
                            'role': role,
                            'description': 'Audit agent',
                            'instructions': 'Usa worktrees aislados y verifica cada diff.',
                            'enabled': True,
                            'appearance': {
                                'form_id': form_id,
                                'palette_id': palette_id,
                                'catalog_version': 'axx-avatar-24x9-v1',
                                'material_preset': 'obsidian',
                                'scale': 1.0,
                            },
                            'intelligence': {
                                'route': 'manual',
                                'provider_profile_ref': 'ollama-local',
                                'model_id': 'qwen2.5-coder:7b',
                                'fallback': 'ask',
                                'max_parallel_turns': 1,
                            },
                            'voice': {
                                'tts_profile_id': 'axxmorcito',
                                'language': 'es-DO',
                                'auto_speak': True,
                                'speed': 1.0,
                            },
                            'workspace': {
                                'runtime': 'api',
                                'foreground_policy': 'queue',
                                'project_ref': 'axx-repo',
                                'allowed_roots': ['project://axx'],
                            },
                            'permissions': {
                                'tool_grant_refs': ['grant.read.project', 'grant.write.worktree'],
                                'delegation_enabled': True,
                                'max_delegate_depth': 2,
                            },
                            'limits': {
                                'max_concurrent_jobs': 2,
                                'max_retries': 1,
                                'max_cost_usd': 2.0,
                            },
                            'memory_scope': 'agent',
                        },
                    )
                    self.assertEqual(st, 200, prof_res)

                # Update agent-architect form, palette, model, and voice
                st_upd, upd_res = client1.request(
                    'POST',
                    '/axx-api/agents/v1/profiles/update',
                    {
                        'agent_id': 'agent-architect',
                        'expected_revision': 1,
                        'patch': {
                            'appearance': {
                                'form_id': 13,
                                'palette_id': 3,
                                'catalog_version': 'axx-avatar-24x9-v1',
                                'material_preset': 'optical_glass',
                                'scale': 1.05,
                            },
                            'intelligence': {
                                'route': 'manual',
                                'provider_profile_ref': 'openai',
                                'model_id': 'gpt-4.1',
                                'fallback': 'ask',
                                'max_parallel_turns': 1,
                            },
                        },
                    },
                )
                self.assertEqual(st_upd, 200, upd_res)
                self.assertEqual(upd_res['profile']['revision'], 2)
                self.assertEqual(upd_res['profile']['appearance']['form_id'], 13)

                # Convert legacy chat to team without losing history or drafts
                st_conv, conv_res = client1.request(
                    'POST',
                    '/axx-api/agents/v1/bindings/convert',
                    {
                        'conversation_id': chat_id,
                        'lead_agent_id': 'agent-architect',
                        'member_agent_ids': ['agent-verifier'],
                    },
                )
                self.assertEqual(st_conv, 200, conv_res)

                # Schedule an autonomous routine, trigger it, then cancel it
                st_rt, _ = client1.request(
                    'POST',
                    '/axx-api/agents/v1/routines',
                    {
                        'routine_id': 'routine-audit-1',
                        'agent_id': 'agent-architect',
                        'conversation_id': chat_id,
                        'schedule_spec': '0 12 * * *',
                        'requested_capabilities': ['read_scoped'],
                        'enabled': True,
                    },
                )
                self.assertEqual(st_rt, 200)
                st_trig, trig_res = client1.request(
                    'POST',
                    '/axx-api/agents/v1/routines/trigger',
                    {'routine_id': 'routine-audit-1', 'proposes_mutation': True},
                )
                self.assertEqual(st_trig, 200)
                self.assertEqual(trig_res['status'], 'awaiting_approval')
            finally:
                _stop_bound_server(srv1, chats1, id1, exec1, cmd1, mp1)

            # Boot Server Instance #2 on the EXACT same state.db (simulating full AXX restart)
            srv2, chats2, id2, exec2, cmd2, mp2 = _start_bound_server(state_db, tmp_path)
            try:
                client2 = _HttpTestClient(srv2.server_port, srv2.host_token)

                # Verify global studio identity was NOT overwritten by Agent Designer edits
                self.assertEqual(id2.get_studio_identity()['studio']['form'], 'Core')

                # Verify both agent profiles and revision=2 persisted across restart
                st_list, list_res = client2.request('GET', '/axx-api/agents/v1/profiles')
                self.assertEqual(st_list, 200)
                by_id = {p['agent_id']: p for p in list_res['profiles']}
                self.assertIn('agent-architect', by_id)
                self.assertIn('agent-verifier', by_id)
                self.assertEqual(by_id['agent-architect']['revision'], 2)
                self.assertEqual(by_id['agent-architect']['appearance']['form_id'], 13)

                # Verify legacy chat messages, draft, and agent bindings persisted across restart
                legacy_after = chats2.get(chat_id)
                self.assertEqual(legacy_after['draft'], 'borrador pendiente')
                self.assertEqual(len(legacy_after['messages']), 1)
                st_bind, bind_res = client2.request('GET', f'/axx-api/agents/v1/bindings?conversation_id={chat_id}')
                self.assertEqual(st_bind, 200)
                self.assertEqual(len(bind_res['bindings']), 2)

                # Verify routine state persisted and can be reconciled and cancelled across restart
                st_rec, rec_res = client2.request('POST', '/axx-api/agents/v1/routines/reconcile', {})
                self.assertEqual(st_rec, 200)
                self.assertIn('routine-audit-1', rec_res['awaiting_approval'])

                st_canc, canc_res = client2.request(
                    'POST',
                    '/axx-api/agents/v1/routines/cancel',
                    {'routine_id': 'routine-audit-1'},
                )
                self.assertEqual(st_canc, 200)
                self.assertEqual(canc_res['routine']['status'], 'cancelled')
                self.assertFalse(canc_res['routine']['enabled'])
            finally:
                _stop_bound_server(srv2, chats2, id2, exec2, cmd2, mp2)

    def test_02_multiagent_execution_via_real_action_executor_and_magic_pen_cad_motion_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_db = tmp_path / 'state.db'
            srv, chats, id_store, executor, commands, mp = _start_bound_server(state_db, tmp_path)
            try:
                for flag in srv.evolution_runtime.flags.list_flags():
                    srv.evolution_runtime.flags.set_flag(flag['flag_id'], True, reason='isolated functional audit')
                client = _HttpTestClient(srv.server_port, srv.host_token)

                # 1. Multi-agent run executing a real ActionExecutor tool (file_artifact_writer)
                st_run, _ = client.request(
                    'POST',
                    '/axx-api/agents/v1/runs/start',
                    {
                        'run_id': 'run-real-exec-1',
                        'conversation_id': 'conv-exec-1',
                        'lead_agent_id': 'axx-lead',
                        'nodes': [
                            {
                                'task_id': 'task-write-file',
                                'agent_id': 'axx-builder',
                                'role': 'implementer',
                                'depends_on': [],
                                'action_spec': {
                                    'tool_name': 'file_artifact_writer',
                                    'inputs': {
                                        'path': 'multiagent_output.txt',
                                        'content': 'Verificado por ActionExecutor real',
                                    },
                                },
                            },
                            {
                                'task_id': 'task-cancel-demo',
                                'agent_id': 'axx-builder',
                                'role': 'implementer',
                                'depends_on': ['task-write-file'],
                                'action_spec': {'tool_name': 'system_telemetry', 'inputs': {}},
                            },
                        ],
                    },
                )
                self.assertEqual(st_run, 200)

                # A graph does not authorize effects: HTTP dispatch must wait for an exact approval.
                denied, _ = client.request('POST', '/axx-api/agents/v1/runs/execute-task', {'task_id':'task-write-file'})
                self.assertEqual(denied, 403)
                self.assertFalse((executor.workspace_root / 'multiagent_output.txt').exists())
                approval = {'conversation_id':'conv-exec-1','run_id':'run-real-exec-1','task_id':'task-write-file',
                            'agent_id':'axx-builder','operation_id':'op-approved-file','tool_name':'file_artifact_writer',
                            'parameters':{'path':'multiagent_output.txt','content':'Verificado por ActionExecutor real'}}
                self.assertEqual(client.request('POST','/axx-api/agents/v1/approvals/request',approval)[0],200)
                self.assertEqual(client.request('POST','/axx-api/agents/v1/approvals/resolve',
                    {'operation_id':'op-approved-file','approved':True})[0],200)
                # Execute task-write-file via ActionExecutor and verify with IndependentVerifierService
                st_exec, exec_res = client.request(
                    'POST',
                    '/axx-api/agents/v1/runs/execute-task',
                    {
                        'task_id': 'task-write-file',
                        'lease_id': 'lease-exec-1',
                        'operation_id':'op-approved-file',
                        'verifier_agent_id': 'axx-verifier',
                    },
                )
                self.assertEqual(st_exec, 200, exec_res)
                self.assertEqual(exec_res['task']['state'], 'completed')
                written_file = executor.workspace_root / 'multiagent_output.txt'
                self.assertTrue(written_file.is_file())
                self.assertEqual(written_file.read_text(encoding='utf-8'), 'Verificado por ActionExecutor real')

                # Cancel the second task
                st_cancel, cancel_res = client.request(
                    'POST',
                    '/axx-api/agents/v1/runs/cancel',
                    {'task_id': 'task-cancel-demo', 'reason': 'Audit cancellation test'},
                )
                self.assertEqual(st_cancel, 200)
                self.assertEqual(cancel_res['task']['state'], 'cancelled')

                # 2. Magic Pen Evolution: Diagram Studio, CAD Studio worker STEP/GLB, Motion freeze(t) & MP4 export
                st_diag, diag_res = client.request(
                    'POST',
                    '/axx-api/spatial/v2/diagrams/layout',
                    {
                        'diagram': {
                            'diagram_id': 'diag-audit-1',
                            'style_template': 'obsidian_spatial',
                            'nodes': [
                                {'id': 'n1', 'label': 'Frontend WebView2'},
                                {'id': 'n2', 'label': 'Loopback Server'},
                            ],
                            'edges': [{'id': 'e1', 'from': 'n1', 'to': 'n2', 'label': 'Bearer Token'}],
                        }
                    },
                )
                self.assertEqual(st_diag, 200, diag_res)
                self.assertTrue(diag_res['qa']['passed'])
                self.assertIn('<svg', diag_res['svg'])

                st_cad, cad_res = client.request(
                    'POST',
                    '/axx-api/spatial/v2/cad/build',
                    {
                        'task': {
                            'task_id': 'cad-audit-bracket',
                            'units': 'mm',
                            'tolerance_mm': 0.1,
                            'parts': [
                                {
                                    'part_id': 'base-plate',
                                    'name': 'Base Plate',
                                    'kind': 'box',
                                    'dimensions': {'width': 80.0, 'depth': 40.0, 'height': 10.0},
                                    'dimension_sources': {'width': 'documented', 'depth': 'documented', 'height': 'documented'},
                                    'position': [0.0, 0.0, 0.0],
                                }
                            ],
                        }
                    },
                )
                self.assertEqual(st_cad, 200, cad_res)
                self.assertTrue(cad_res['congruence']['congruent'])
                self.assertTrue(Path(cad_res['step_path']).is_file())
                self.assertTrue(Path(cad_res['glb_path']).is_file())

                # Motion Studio deterministic freeze(t) & MP4 export with Spanish TTS narration
                cad_scene = cad_res['scene_document']
                cad_scene['timeline'] = {
                    'duration_seconds': 2.0,
                    'tracks': [
                        {
                            'track_id': 'trk-1',
                            'kind': 'transform',
                            'target_object_id': 'base-plate',
                            'start_time': 0.0,
                            'duration': 2.0,
                            'from_position': [0.0, 0.0, 0.0],
                            'to_position': [10.0, 0.0, 5.0],
                        },
                        {
                            'track_id': 'trk-narr-1',
                            'kind': 'narration',
                            'start_time': 0.0,
                            'duration': 2.0,
                            'title': 'Paso CAD',
                            'narration': 'Exportación CAD en formato .step y .glb con API JSON a 60 FPS.',
                        },
                    ],
                }
                st_frz, frz_res = client.request(
                    'POST',
                    '/axx-api/spatial/v2/motion/freeze',
                    {'scene': cad_scene, 't_sec': 1.0, 'seed': 42},
                )
                self.assertEqual(st_frz, 200)
                obj_by_id = {o['id']: o for o in frz_res['objects']}
                self.assertEqual(obj_by_id['base-plate']['position'], [5.0, 0.0, 2.5])

                st_mp4, mp4_res = client.request(
                    'POST',
                    '/axx-api/spatial/v2/motion/export-mp4',
                    {
                        'scene': cad_scene,
                        'fps': 6,
                        'seed': 42,
                    },
                )
                self.assertEqual(st_mp4, 200, mp4_res)
                self.assertTrue(Path(mp4_res['output_path']).is_file())
                self.assertIn('punto estep', mp4_res['narration_cues'][0]['prepared_spoken_text'].lower())
            finally:
                _stop_bound_server(srv, chats, id_store, executor, commands, mp)

    def test_03_code_studio_http_workflow_and_real_wsl2_vm_isolation_and_spanish_voice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_db = tmp_path / 'state.db'
            repo_dir = tmp_path / 'sample_repo'
            repo_dir.mkdir()
            subprocess.run(['git', 'init'], cwd=str(repo_dir), check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'owner@example.com'], cwd=str(repo_dir), check=True)
            subprocess.run(['git', 'config', 'user.name', 'Owner'], cwd=str(repo_dir), check=True)
            (repo_dir / 'math_ops.py').write_text('def multiply(x, y):\n    return x * y\n', encoding='utf-8')
            (repo_dir / 'test_math_ops.py').write_text(
                'import unittest, math_ops\n'
                'class T(unittest.TestCase):\n'
                '    def test_m(self):\n'
                '        self.assertEqual(math_ops.multiply(6, 7), 42)\n'
                'if __name__ == "__main__":\n'
                '    unittest.main()\n',
                encoding='utf-8',
            )
            subprocess.run(['git', 'add', '.'], cwd=str(repo_dir), check=True)
            subprocess.run(['git', 'commit', '-m', 'init'], cwd=str(repo_dir), check=True, capture_output=True)

            orig_sha = hashlib.sha256((repo_dir / 'math_ops.py').read_bytes()).hexdigest()

            srv, chats, id_store, executor, commands, mp = _start_bound_server(state_db, tmp_path)
            try:
                for flag in srv.evolution_runtime.flags.list_flags():
                    srv.evolution_runtime.flags.set_flag(flag['flag_id'], True, reason='isolated functional audit')
                client = _HttpTestClient(srv.server_port, srv.host_token)

                # 1. Code Studio over HTTP: register -> create worktree -> propose/apply -> run tests -> integrate -> rollback
                client.request('POST', '/axx-api/code/v1/projects/register', {'project_id': 'repo-http', 'project_root': str(repo_dir)})
                st_wt, wt_res = client.request(
                    'POST',
                    '/axx-api/code/v1/worktrees/create',
                    {'workspace_id': 'wt-http-1', 'project_id': 'repo-http', 'agent_id': 'agent-dev', 'task_slug': 'feat'},
                )
                self.assertEqual(st_wt, 200)

                st_pa, _ = client.request(
                    'POST',
                    '/axx-api/code/v1/worktrees/propose-apply',
                    {
                        'changeset_id': 'cs-http-1',
                        'workspace_id': 'wt-http-1',
                        'file_edits': [
                            {'path': 'math_ops.py', 'new_content': 'def multiply(x, y):\n    return int(x) * int(y)\n'}
                        ],
                    },
                )
                self.assertEqual(st_pa, 200)

                st_int, int_res = client.request(
                    'POST',
                    '/axx-api/code/v1/worktrees/integrate',
                    {'changeset_id': 'cs-http-1'},
                )
                self.assertEqual(st_int, 200)
                self.assertEqual(int_res['changeset']['status'], 'integrated')
                self.assertIn('int(x) * int(y)', (repo_dir / 'math_ops.py').read_text(encoding='utf-8'))

                st_tr, tr_res = client.request(
                    'POST',
                    '/axx-api/code/v1/tests/run',
                    {
                        'report_id': 'rep-http-1',
                        'project_id': 'repo-http',
                        'workspace_id': 'wt-http-1',
                        'command': [sys.executable, 'test_math_ops.py'],
                    },
                )
                self.assertEqual(st_tr, 200)
                self.assertTrue(tr_res['receipt']['passed'])

                st_rb, rb_res = client.request(
                    'POST',
                    '/axx-api/code/v1/changesets/rollback',
                    {'changeset_id': 'cs-http-1'},
                )
                self.assertEqual(st_rb, 200)
                self.assertEqual(hashlib.sha256((repo_dir / 'math_ops.py').read_bytes()).hexdigest(), orig_sha)
                client.request('POST', '/axx-api/code/v1/worktrees/remove', {'workspace_id': 'wt-http-1'})

                # 2. Real WSL2 Virtual Machine probe, creation, execution, snapshot, and cleanup
                st_probe, probe_res = client.request('GET', '/axx-api/workspaces/v1/vm/probe')
                self.assertEqual(st_probe, 200)
                if 'wsl2' in probe_res.get('detected_backends', []):
                    st_vmc, vmc_res = client.request(
                        'POST',
                        '/axx-api/workspaces/v1/vm/create',
                        {'vm_id': 'vm-wsl2-audit', 'backend': 'wsl2'},
                    )
                    self.assertEqual(st_vmc, 200)
                    client.request('POST', '/axx-api/workspaces/v1/vm/start', {'vm_id': 'vm-wsl2-audit'})
                    _, lease_res = client.request(
                        'POST',
                        '/axx-api/workspaces/v1/leases/acquire',
                        {
                            'lease_id': 'lease-vm-wsl2',
                            'owner_run_id': 'run-wsl2',
                            'resource_type': 'vm_instance',
                            'resource_key': 'vm-wsl2-audit',
                        },
                    )
                    token = lease_res['lease']['fencing_token']
                    st_act, act_res = client.request(
                        'POST',
                        '/axx-api/workspaces/v1/vm/act',
                        {
                            'vm_id': 'vm-wsl2-audit',
                            'owner_run_id': 'run-wsl2',
                            'fencing_token': token,
                            'action_type': 'guest_write_file',
                            'payload': {'filename': 'hello_guest.txt', 'content': 'isolated_wsl2_verified'},
                        },
                    )
                    self.assertEqual(st_act, 200)
                    self.assertEqual(act_res['status'], 'completed')
                    self.assertEqual(act_res['receipt']['guest_exit_code'], 0)

                    st_snap, snap_res = client.request(
                        'POST',
                        '/axx-api/workspaces/v1/vm/snapshot',
                        {'vm_id': 'vm-wsl2-audit', 'snapshot_label': 'audit'},
                    )
                    self.assertEqual(st_snap, 200)
                    self.assertEqual(len(snap_res['snapshot']['guest_archive_sha256']), 64)

                    client.request('POST', '/axx-api/workspaces/v1/vm/stop', {'vm_id': 'vm-wsl2-audit'})
                    st_dest, dest_res = client.request('POST', '/axx-api/workspaces/v1/vm/destroy', {'vm_id': 'vm-wsl2-audit'})
                    self.assertEqual(st_dest, 200)
                    self.assertTrue(dest_res['vm']['cleaned_guest'])

                # 3. Spanish Voice Normalization, Prosody & Windows Speech Service verification
                spoken, lang = prepare_spoken_text(
                    'Hola Luigi, ¿cómo estás? Revisa el archivo scene.glb y model.step con LSP, DAP y 100%.'
                )
                self.assertEqual(lang, 'es')
                self.assertIn('¿cómo estás?', spoken.lower())
                self.assertIn('punto ge-ele-be', spoken.lower())
                self.assertIn('punto estep', spoken.lower())
                self.assertIn('ele-ese-pe', spoken.lower())
                self.assertIn('de-a-pe', spoken.lower())
                self.assertIn('cien por ciento', spoken.lower())

                clauses = ProsodyAnalyzer.segment(spoken)
                self.assertGreaterEqual(len(clauses), 2)

                speech_svc = WindowsSpeechService(tmp_path / 'speech_state')
                try:
                    voices_info = speech_svc.voices()
                    self.assertIn('voices', voices_info)
                finally:
                    speech_svc.close()
            finally:
                _stop_bound_server(srv, chats, id_store, executor, commands, mp)


if __name__ == '__main__':
    unittest.main()
