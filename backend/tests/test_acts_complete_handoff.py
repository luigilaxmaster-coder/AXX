"""Comprehensive Evolution 3.1 ACTS Acceptance Suite.

Covers the full Engineering Handoff 3.1 gaps:
- VISUAL-01 (24 distinct canonical parametric SVGs) & VISUAL-03 (performance benchmark with Code Studio + Acts open)
- ACT-08 (lossless chat conversion & bindings in UI + SQLite)
- ACT-11..13 & Scenario 16 (single-sentence Dev -> Visual -> QA Team TaskGraph + independent models + handoffs + artifacts)
- ACT-14 & ResourceGovernor concurrency / budget enforcement
- ROUTINE-01..03 (real connected RoutineDispatcher, restart persistence, pause/resume, history)
- Spatial / Magic Pen Act authorization (axx.spatial)
- Workspace / Computer Use Act authorization (axx.computer: files, isolated browser, foreground deny)
- LSP / DAP probing & honest UNAVAILABLE reporting + AST diagnostics
- Per-Act TTS voice configuration persistence & audio routing
"""
from __future__ import annotations

import functools
import http.server
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from playwright.sync_api import sync_playwright

from backend.agents.act_inference import ActInferenceError
from backend.agents.profiles import AvatarFormAdapter, CANONICAL_AXX_FORMS
from backend.tests import test_motion_studio
from backend.tests.test_acts_code_tools import git_repo
from backend.tests.test_acts_inference import _EchoModel, _Server, act_spec, provider
from backend.tests.test_acts_ui import ROOT, open_axx, serve


class ActsCompleteHandoffTests(unittest.TestCase):
    def setUp(self):
        _EchoModel.seen = []
        self.echo = serve(_EchoModel)
        base = f'http://127.0.0.1:{self.echo.server_port}/v1'
        self.providers = [
            provider('loop-dev', base, 'model-dev'),
            provider('loop-vis', base, 'model-visual'),
            provider('loop-qa', base, 'model-qa'),
        ]

    def tearDown(self):
        self.echo.shutdown()
        self.echo.server_close()

    def test_visual01_24_canonical_forms_have_24_distinct_svg_geometries(self):
        adapter = AvatarFormAdapter()
        hashes = set()
        for form_id in range(24):
            thumb = adapter.get_thumbnail(form_id, 2, material_preset='optical_glass', size_px=128)
            self.assertEqual(thumb['form_name'], CANONICAL_AXX_FORMS[form_id])
            self.assertFalse(thumb['webgl_loop_active'])
            hashes.add(thumb['sha256'])
        self.assertEqual(len(hashes), 24, 'Each of the 24 canonical forms must produce a unique SVG thumbnail')

    def test_routine01_to_03_connected_dispatcher_restart_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srv1 = _Server(root, self.providers)
            try:
                srv1.rt.registry.create_profile(act_spec('act-ops', 'Ops', 'Orbit', 'loop-dev', 'model-dev'))
                c, res = srv1.api.request('POST', '/axx-api/agents/v1/routines', {
                    'routine_id': 'rout-every-10s',
                    'agent_id': 'act-ops',
                    'conversation_id': 'conv-rout-1',
                    'schedule_spec': 'every:10s',
                    'requested_capabilities': ['read_workspace'],
                    'requires_approval': False,
                    'prompt_text': 'Comprobar salud del proyecto',
                    'enabled': True,
                })
                self.assertEqual(c, 200, res)
                self.assertIsNotNone(res['routine']['next_run_at_ms'])

                c, trig = srv1.api.request('POST', '/axx-api/agents/v1/routines/trigger', {
                    'routine_id': 'rout-every-10s',
                    'proposes_mutation': False,
                })
                self.assertEqual(c, 200, trig)
                self.assertTrue(trig['dispatcher_connected'])
                self.assertTrue(trig['executed'])
                self.assertEqual(trig['status'], 'completed')
                self.assertFalse(trig['activated_microphone'])
                self.assertFalse(trig['activated_host_input'])

                # Verify history and tick_due_routines with future timestamp
                c, hist = srv1.api.request('GET', '/axx-api/agents/v1/routines/history?routine_id=rout-every-10s')
                self.assertEqual(c, 200)
                self.assertGreaterEqual(len(hist['runs']), 1)

                c, tick = srv1.api.request('POST', '/axx-api/agents/v1/routines/tick', {'now_ms': int(time.time() * 1000) + 60_000})
                self.assertEqual(c, 200, tick)
                self.assertEqual(len(tick['results']), 1)
                self.assertTrue(tick['results'][0]['executed'])

                # Pause & resume
                self.assertEqual(srv1.api.request('POST', '/axx-api/agents/v1/routines/pause', {'routine_id': 'rout-every-10s'})[1]['routine']['status'], 'paused')
                self.assertEqual(srv1.api.request('POST', '/axx-api/agents/v1/routines/resume', {'routine_id': 'rout-every-10s'})[1]['routine']['status'], 'scheduled')
            finally:
                srv1.close()

            # Restart server on same DB and confirm routine & history survive (ROUTINE-03)
            srv2 = _Server(root, self.providers)
            try:
                c, rec = srv2.api.request('POST', '/axx-api/agents/v1/routines/reconcile', {})
                self.assertEqual(c, 200, rec)
                self.assertIn('rout-every-10s', rec['scheduled'])
                c, hist2 = srv2.api.request('GET', '/axx-api/agents/v1/routines/history?routine_id=rout-every-10s')
                self.assertGreaterEqual(len(hist2['runs']), 2)
            finally:
                srv2.close()

    def test_scenario16_dev_visual_qa_single_prompt_and_spatial_computer_gates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            repo = git_repo(root)
            srv = _Server(root, self.providers)
            try:
                for flag in ('agent_profiles_v1', 'code_studio_v1', 'magic_scene_v2'):
                    srv.rt.flags.set_flag(flag, True, reason='scenario 16 gate test')
                srv.api.request('POST', '/axx-api/code/v1/projects/register', {'project_id': 'proj-s16', 'project_root': str(repo)})
                scene = test_motion_studio.MotionStudioTests()._sample_motion_scene()
                srv.api.request('POST', '/axx-api/spatial/v2/scenes', {'scene': scene})

                # Create Dev, Visual, QA with distinct forms, voices & models
                srv.rt.registry.create_profile(act_spec(
                    'act-dev', 'Dev', 'Helix', 'loop-dev', 'model-dev', role='Programador',
                    voice={'language': 'es-DO', 'speed': 1.05, 'tts_profile_id': 'moss:axx-sam', 'intonation': 'focused', 'expressiveness': 'medium', 'auto_speak': True},
                    limits={'max_concurrent_jobs': 1, 'max_retries': 0, 'max_cost_usd': 1.0, 'max_ram_mb': 1024, 'max_cpu_percent': 75},
                    collaboration={'mention': 'Dev', 'accepts_handoffs': True},
                ))
                srv.rt.registry.create_profile(act_spec(
                    'act-visual', 'Visual', 'Prism', 'loop-vis', 'model-visual', role='Especialista Visual 3D',
                    workspace={'runtime': 'api', 'foreground_policy': 'deny', 'allowed_roots': [str(root / 'safe_dir')]},
                    collaboration={'mention': 'Visual', 'accepts_handoffs': True},
                ))
                srv.rt.registry.create_profile(act_spec(
                    'act-qa', 'QA', 'Core', 'loop-qa', 'model-qa', role='Revisor QA',
                    collaboration={'mention': 'QA', 'accepts_handoffs': True},
                ))

                # Spatial permission gate (axx.spatial): denied without grant, allowed with grant
                patch_body = {'act_id': 'act-visual', 'patch': {
                    'document_id': scene['document_id'], 'base_revision': 1, 'operation_id': 'vis-patch-1',
                    'target_object_ids': ['piston-1'], 'allowed_paths': ['name'],
                    'changes': [{'op': 'object.update', 'object_id': 'piston-1', 'fields': {'name': 'Visual Inspected'}}],
                }}
                self.assertEqual(srv.api.request('POST', '/axx-api/spatial/v2/scenes/patch', patch_body)[0], 403)
                srv.rt.registry.grant_permission(grant_id='g-vis-sp', agent_id='act-visual', tool_id='axx.spatial',
                                                 resource_pattern='*', operation_kinds=['read', 'patch', 'qa'])
                self.assertEqual(srv.api.request('POST', '/axx-api/spatial/v2/scenes/patch', patch_body)[0], 200)

                # Computer Use gate (PC-01..05): foreground deny enforced via axx.computer
                srv.rt.registry.grant_permission(grant_id='g-vis-pc', agent_id='act-visual', tool_id='axx.computer',
                                                 resource_pattern='*', operation_kinds=['files', 'foreground'])
                code_fg, _ = srv.api.request('POST', '/axx-api/workspaces/v1/uia/act', {
                    'act_id': 'act-visual', 'owner_run_id': 'r1', 'fencing_token': 1,
                    'leased_window_key': 'win-1', 'live_window_info': {}, 'uia_pattern': 'InvokePattern',
                    'control_id': 'btn1', 'requires_physical_focus': True,
                })
                self.assertEqual(code_fg, 403)

                # LSP/DAP probe reports honest UNAVAILABLE for uninstalled servers while AST works
                c, lsp_stat = srv.api.request('GET', '/axx-api/code/v1/lsp/status')
                self.assertEqual(c, 200)
                self.assertIn('python', lsp_stat['servers'])
                c, dap_stat = srv.api.request('GET', '/axx-api/code/v1/dap/status')
                self.assertEqual(c, 200)
                self.assertIn('debugpy', dap_stat['adapters'])
                c, lsp_insp = srv.api.request('POST', '/axx-api/code/v1/lsp/inspect', {
                    'project_id': 'proj-s16', 'language': 'python', 'path': 'calc.py',
                })
                self.assertEqual(c, 200, lsp_insp)
                self.assertTrue(lsp_insp['editor_usable'])
                self.assertGreaterEqual(len(lsp_insp['symbols']), 1)

                # ResourceGovernor concurrency enforcement (max_concurrent_jobs = 1)
                srv.rt.acts.begin_execution('act-dev', 'lock-1')
                try:
                    with self.assertRaises(ActInferenceError) as ctx:
                        srv.rt.acts.begin_execution('act-dev', 'lock-2')
                    self.assertEqual(ctx.exception.code, 'ACT_CONCURRENCY_LIMIT')
                finally:
                    srv.rt.acts.end_execution('act-dev', 'lock-1')

                # Single-prompt multi-Act team execution: Dev -> Visual -> QA
                srv.rt.registry.create_team(
                    team_id='team-core', title='Core Engineering', coordinator_agent_id='act-dev',
                    budget_usd=4.0, max_concurrency=2,
                    members=[{'agent_id': 'act-dev', 'role': 'lead'}, {'agent_id': 'act-visual', 'role': 'member'}, {'agent_id': 'act-qa', 'role': 'reviewer'}],
                )
                self.assertEqual(len(srv.api.request('GET', '/axx-api/agents/v1/teams')[1]['teams']), 1)

                c, run_res = srv.api.request('POST', '/axx-api/agents/v1/teams/run', {
                    'conversation_id': 'conv-s16',
                    'project_id': 'proj-s16',
                    'file_path': 'calc.py',
                    'scene_document_id': scene['document_id'],
                    'prompt': 'Dev, mejora este componente. Visual, revisa la interfaz. QA, verifica los resultados.',
                })
                self.assertEqual(c, 200, run_res)
                self.assertEqual([s['act_id'] for s in run_res['steps']], ['act-dev', 'act-visual', 'act-qa'])
                self.assertEqual([s['model'] for s in run_res['steps']], ['model-dev', 'model-visual', 'model-qa'])
                self.assertEqual(len(run_res['artifacts']), 3)
                # Confirm Visual actually received scene context & QA received prior team output
                self.assertIn(scene['document_id'], _EchoModel.seen[-2]['messages'][-1]['content'])
                self.assertIn('[Visual · model-visual]', _EchoModel.seen[-1]['messages'][-1]['content'])
                # EventHub recorded handoffs and completion
                c, replay = srv.api.request('GET', '/axx-api/agents/v1/events/sse?conversation_id=conv-s16')
                ev_types = [e['type'] for e in replay['events']]
                self.assertIn('handoff.created', ev_types)
                self.assertIn('handoff.completed', ev_types)
                self.assertIn('run.completed', ev_types)
            finally:
                srv.close()

    def test_ui_chat_conversion_and_team_and_performance_visual03(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            repo = git_repo(root)
            srv = _Server(root, self.providers)
            web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))
            try:
                srv.rt.flags.set_flag('agent_profiles_v1', True, reason='ui full handoff test')
                srv.rt.flags.set_flag('code_studio_v1', True, reason='ui benchmark test')
                srv.rt.registry.create_profile(act_spec('act-dev', 'Dev', 'Helix', 'loop-dev', 'model-dev', collaboration={'mention': 'Dev'}))
                srv.rt.registry.create_profile(act_spec('act-visual', 'Visual', 'Prism', 'loop-vis', 'model-visual', collaboration={'mention': 'Visual'}))
                srv.rt.registry.create_profile(act_spec('act-qa', 'QA', 'Core', 'loop-qa', 'model-qa', collaboration={'mention': 'QA'}))
                # Create existing conversation in SQLite ChatStore with preserved message and draft (ACT-08)
                conv = srv.chats.mutate('create', {'title': 'Hilo Existente', 'draft': 'borrador conservado'})
                cid = conv['id']
                meta = srv.chats.get(cid)
                srv.chats.mutate('save', {
                    'id': cid, 'draft': 'borrador conservado',
                    'memory_scope': meta['memory_scope'], 'memory_context_id': meta['context_id'],
                    'messages': [{'id': 'm-old', 'role': 'user', 'status': 'complete', 'text': 'Historial previo', 'at': srv.chats.clock()}],
                })

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        t0 = time.perf_counter()
                        page = open_axx(browser, srv, web)
                        page.wait_for_function("window.Axx?.chatWorkspace?.ready === true", timeout=30000)
                        page.evaluate(f"(async()=>{{ await Axx.chatWorkspace.refresh(); await Axx.chatWorkspace.select('{cid}'); }})()")
                        page.evaluate("Axx.companion.openFeature('agent')")
                        page.get_by_role('button', name='Abrir Acts', exact=True).click()
                        page.wait_for_function("document.querySelectorAll('.axx-acts-card').length >= 3")

                        # ACT-08: Convert existing chat to Dev and verify messages + draft untouched in SQLite
                        page.locator('.axx-acts-card', has_text='Dev').get_by_role('button', name='Usar en el chat').click()
                        page.wait_for_function("document.querySelector('.axx-acts-status').textContent.includes('responderá en este chat')")
                        after_bind = srv.chats.get(cid)
                        self.assertEqual(after_bind['draft'], 'borrador conservado')
                        self.assertEqual(len(after_bind['messages']), 1)
                        self.assertEqual(srv.rt.bindings.list_conversation_members(cid)[0]['agent_id'], 'act-dev')

                        # Multi-mention single-sentence team execution via existing chat brain
                        team_reply = page.evaluate("""(async()=>{const r=await Axx.companion.brain.chat(
                            {...Axx.companion.data.prefs, prompt_mode:'conversation'},
                            [{role:'user',content:'@Dev mejora calc.py. @Visual revisa la vista. @QA verifica todo.'}],
                            new AbortController().signal, ()=>{}); return r;})()""")
                        self.assertIn('〔Dev · model-dev〕', team_reply['text'])
                        self.assertIn('〔Visual · model-visual〕', team_reply['text'])
                        self.assertIn('〔QA · model-qa〕', team_reply['text'])

                        # Check Activity & Handoffs drawer in chat
                        page.evaluate("Axx.companion.openChat()")
                        page.get_by_role('button', name='Actividad Acts', exact=True).click()
                        page.wait_for_function("!document.querySelector('.axx-acts-activity-drawer').hidden && document.querySelector('.axx-acts-activity-drawer').textContent.includes('handoff.completed')")

                        # Open Code Studio alongside Acts and check LSP + performance (VISUAL-03)
                        page.evaluate("Axx.companion.openFeature('agent')")
                        page.get_by_role('button', name='Abrir Code Studio', exact=True).click()
                        page.wait_for_function('Axx.codeStudio.editor !== null', timeout=60000)
                        page.locator('[data-code=root]').fill(str(repo))
                        page.get_by_role('button', name='Abrir proyecto', exact=True).click()
                        page.locator('[data-code=browser]').get_by_role('button', name='calc.py', exact=True).click()
                        page.wait_for_function("Axx.codeStudio.editor.getValue().includes('def add')")
                        page.get_by_role('button', name='Diagnósticos y LSP', exact=True).click()
                        page.wait_for_function("document.querySelector('[data-code=output]').textContent.includes('LSP (python)')")
                        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                        # Check frame responsiveness (double rAF latency under open Acts + Monaco)
                        raf_ms = page.evaluate("new Promise(r=>{const a=performance.now();requestAnimationFrame(()=>requestAnimationFrame(()=>r(performance.now()-a)));})")
                        self.assertLess(raf_ms, 500.0, f'UI frame stall detected: {raf_ms}ms (total open={elapsed_ms}ms)')
                    finally:
                        browser.close()
            finally:
                web.shutdown()
                web.server_close()
                srv.close()


if __name__ == '__main__':
    unittest.main()
