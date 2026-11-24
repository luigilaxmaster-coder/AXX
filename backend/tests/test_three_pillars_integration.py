"""Connected UI/API checks using real disk, SQLite, Git, WebGL and GLB bytes.

The native IPC and model are controlled fixtures. These are browser integration
receipts, separate from installed WebView2 and real-provider acceptance.
"""
import functools
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from playwright.sync_api import sync_playwright

from backend.magic_pen import write_json
from backend.spatial.scene_document import import_presentation_plan_v1
from backend.tests.test_acts_inference import _Server, act_spec
from backend.tests.test_acts_code_tools import git_repo
from backend.tests.test_acts_ui import ROOT, open_axx, serve


class ThreePillarsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.srv = _Server(self.root, [])
        for flag in ('agent_profiles_v1', 'code_studio_v1', 'magic_scene_v2'):
            self.srv.rt.flags.set_flag(flag, True, reason='isolated three pillars integration')

    def tearDown(self):
        self.srv.close()
        self.tmp.cleanup()

    def act(self, aid):
        return self.srv.rt.registry.create_profile(act_spec(aid, aid.title(), 'Helix', 'loop-a', 'model-alpha'))

    def test_context_proposal_api_uses_server_packet_cas_scope_and_revocation(self):
        repo = git_repo(self.root)
        rt = self.srv.rt
        rt.code_projects.register_project('p', str(repo))
        self.act('dev')
        rt.registry.grant_permission(agent_id='dev', grant_id='code', tool_id='axx.code', resource_pattern='p',
                                    operation_kinds=['worktree', 'patch'], approval_mode='ask')
        api = self.srv.api
        code, result = api.request('POST', '/axx-api/code/v1/context/build',
                                  {'project_id': 'p', 'act_id': 'dev', 'selections': [{'path': 'calc.py'}]})
        self.assertEqual(code, 200, result)
        packet = result['context']
        wt = rt.code_git.create_agent_worktree(workspace_id='w', project_id='p', agent_id='dev', task_slug='fix')
        proposal = {'context_sha256': packet['packet_sha256'], 'file_edits': [
            {'path': 'calc.py', 'expected_base_sha256': packet['files'][0]['sha256'],
             'hunks': [{'old_text': 'a - b', 'new_text': 'a + b'}]}]}
        body = {'act_id': 'dev', 'workspace_id': 'w', 'changeset_id': 'c', 'context': packet,
                'proposal_text': json.dumps(proposal)}
        # A maliciously altered client packet cannot replace the server's persisted context.
        body['context'] = {**packet, 'act_id': 'evil', 'files': []}
        code, result = api.request('POST', '/axx-api/code/v1/worktrees/apply-proposal', body)
        self.assertEqual(code, 200, result)
        self.assertIn('a + b', (Path(wt['worktree_path']) / 'calc.py').read_text())
        self.assertIn('a - b', (repo / 'calc.py').read_text())
        rt.registry.revoke_permission('dev', 'code')
        code, result = api.request('POST', '/axx-api/code/v1/worktrees/apply-proposal', {**body, 'changeset_id': 'c2'})
        self.assertEqual(code, 403, result)

    def test_act_voice_survives_async_voice_discovery_without_changing_global_reader(self):
        spec=act_spec('dev','Dev','Helix','local','model-alpha',voice={'tts_profile_id':'sapi:ActVoice','speed':1.2,'language':'es-DO'})
        self.srv.rt.registry.create_profile(spec)
        web=serve(functools.partial(__import__('http.server',fromlist=['SimpleHTTPRequestHandler']).SimpleHTTPRequestHandler,
                                   directory=str(ROOT/'1.AXX')))
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    page=open_axx(browser,self.srv,web)
                    page.evaluate('''async()=>{
                        await Axx.acts.load();const reader=Axx.symbiosis.reader;
                        reader.voiceURI='sapi:GlobalVoice';reader.rate=1;reader.lang='es-ES';
                        Axx.nativeVoice.refreshVoices=()=>new Promise(resolve=>setTimeout(()=>resolve([
                          {name:'GlobalVoice',engine:'windows-sapi',language:'es-ES'},
                          {name:'ActVoice',engine:'windows-sapi',language:'es-DO'}]),30));
                        const request=Axx.backendRequest;
                        Axx.backendRequest=async(method,path,body)=>{
                          if(path==='/axx-api/speech/synthesize'){window.actSynthesis=body;throw Error('Controlled playback stop');}
                          return request(method,path,body);
                        };
                        Axx.companion.read('〔Dev〕 Una respuesta del Act.');
                    }''')
                    page.wait_for_function('window.actSynthesis')
                    self.assertEqual(page.evaluate('actSynthesis.voice'),'ActVoice')
                    self.assertEqual(page.evaluate('Axx.symbiosis.reader.voiceURI'),'sapi:GlobalVoice')
                    self.assertEqual(page.evaluate('Axx.symbiosis.reader.rate'),1)
                    page.evaluate("Axx.symbiosis.reader.setText('Lectura humana')")
                    self.assertIsNone(page.evaluate('Axx.symbiosis.reader.turnVoiceProfile'))
                finally:browser.close()
        finally:web.shutdown();web.server_close()

    def test_local_asset_factory_inserts_real_component_with_undo_and_remote_fallback(self):
        rt=self.srv.rt
        rt.flags.set_flag('asset_gate_mcp_v1',True,reason='local asset factory test')
        rt.scenes.create_document(import_presentation_plan_v1({'scene':{'objects':[
            {'id':'base','shape':'box','size':[1,1,1],'position':[0,0,0],'color':'#438ee8'}]}},
            document_id='assembly',source_id='capture'))
        component=rt.assets.shape_registry.list_components()[0]
        api=self.srv.api
        code,result=api.request('POST','/axx-api/spatial/v2/assets/resolve',{'query':component['label'],'use_asset_gate':True})
        self.assertEqual(code,200,result)
        self.assertTrue(result['local_shape_matches'])
        self.assertEqual(result['remote_status'],'unavailable')
        body={'document_id':'assembly','base_revision':1,'component_id':component['id'],'operation_id':'insert-once'}
        code,applied=api.request('POST','/axx-api/spatial/v2/assets/insert-component',body)
        self.assertEqual(code,200,applied)
        self.assertGreater(len(applied['document']['objects']),1)
        self.assertEqual(applied['provenance']['source'],'local_procedural')
        code,retry=api.request('POST','/axx-api/spatial/v2/assets/insert-component',body)
        self.assertEqual((code,retry),(200,applied))
        code,undone=api.request('POST','/axx-api/spatial/v2/scenes/undo',{'document_id':'assembly','operation_id':'undo-insert'})
        self.assertEqual(code,200,undone)
        self.assertEqual([p['id'] for p in undone['document']['objects']],['base'])

    def test_acts_history_tab_reuses_chats_and_switches_without_losing_draft(self):
        self.act('dev'); self.act('qa')
        srv = self.srv
        conv = srv.chats.mutate('create', {'title': 'Proyecto existente', 'draft': 'pendiente'})
        srv.rt.bindings.bind_agent_to_conversation(conv['id'], 'dev')
        web = serve(functools.partial(__import__('http.server', fromlist=['SimpleHTTPRequestHandler']).SimpleHTTPRequestHandler,
                                      directory=str(ROOT / '1.AXX')))
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = open_axx(browser, srv, web)
                    page.wait_for_function('Axx.chatWorkspace?.ready')
                    page.evaluate('(id)=>Axx.chatWorkspace.select(id)', conv['id'])
                    page.evaluate("Axx.companion.openFeature('chat')")
                    if page.locator('#cw-browse').is_visible():
                        page.locator('#cw-browse').click()
                    page.locator('.axx-chat-act-navigation').get_by_role('tab', name='Acts', exact=True).click()
                    page.get_by_role('button', name='Mis Acts', exact=True).wait_for()
                    page.get_by_role('button', name='Chats por Act', exact=True).click()
                    page.get_by_label('Act para ver conversaciones', exact=True).select_option('dev')
                    page.get_by_role('button', name='Proyecto existente', exact=True).wait_for()
                    before = srv.chats.get(conv['id'])
                    page.evaluate("Axx.acts.chooseForChat('qa')")
                    members = srv.rt.bindings.list_conversation_members(conv['id'])
                    self.assertEqual(members[0]['agent_id'], 'qa')
                    self.assertEqual(sum(m['membership_role'] == 'lead' for m in members), 1)
                    after = srv.chats.get(conv['id'])
                    for key in ('id', 'created', 'draft', 'group_id', 'messages'):
                        self.assertEqual(after[key], before[key])
                    page.evaluate("Axx.acts.chooseForChat('')")
                    self.assertFalse(any(m['membership_role'] == 'lead' for m in srv.rt.bindings.list_conversation_members(conv['id'])))
                finally:
                    browser.close()
        finally:
            web.shutdown(); web.server_close()

    def test_magic_pen_edits_real_mesh_exports_glb_and_reopens_revision(self):
        srv = self.srv
        capture = srv.magic_pen.acquire(Image.new('RGB', (400, 300), 'white'), {'id': 'fixture'})
        plan = {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Mecanismo', 'summary': 'Tres piezas',
                'fidelity': 'conceptual', 'steps': [{'id': 's1', 'title': 'Piezas', 'body': 'Tres piezas relacionadas.',
                    'basis': 'inferred', 'narration': 'Tres piezas.', 'focus': ['a']}],
                'scene': {'fidelity': 'conceptual', 'objects': [
                    {'id': x, 'label': x.upper(), 'shape': shape, 'size': [1, 1, 1], 'position': [i*2, 0, 0],
                     'color': '#438ee8', 'material': 'plastic'}
                    for i, (x, shape) in enumerate([('a', 'box'), ('b', 'sphere'), ('c', 'cylinder')])], 'arrows': []}}
        capture['queries'] = [{'id': 'a' * 32, 'source_id': capture['id'], 'revision': 1,
                               'state': 'completed', 'format': 'presentation', 'presentation': plan}]
        write_json(srv.magic_pen.directory(capture['id']) / 'document.json', capture)
        web = serve(functools.partial(__import__('http.server', fromlist=['SimpleHTTPRequestHandler']).SimpleHTTPRequestHandler,
                                      directory=str(ROOT / '1.AXX')))
        try:
            with sync_playwright() as p:
                # GPU-less CI runners: request Chromium's software WebGL explicitly (it is no longer an automatic fallback).
                browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
                try:
                    page = open_axx(browser, srv, web)
                    page.evaluate('''async id=>{const pen=Axx.magicPen;pen.active=true;pen.root.hidden=false;pen.state='reviewing';
                        const doc=await Axx.backendRequest('POST','/axx-api/pen/get',{id});await pen.load(doc,true);pen.showWidget();}''', capture['id'])
                    # Wait for the real scene or for Magic Pen's own failure reason, never a blind timeout.
                    page.wait_for_function('(Axx.magicPen.player?.scene && Axx.magicPen.player?.v2Scene) || Axx.magicPen.player?.sceneFailed', timeout=60000)
                    self.assertFalse(page.evaluate('Axx.magicPen.player.sceneFailed || ""'),
                                     page.evaluate("JSON.stringify({webgl2: !!document.createElement('canvas').getContext('webgl2')})"))
                    initial = page.evaluate('Axx.magicPen.player.scene.geometrySnapshot()')
                    page.evaluate("Axx.magicPen.player.picked='a';Axx.magicPen.renderAnswers()")
                    page.get_by_label('Color de A', exact=True).fill('#ff0000')
                    page.get_by_label('Material de A', exact=True).select_option('metal_brushed')
                    page.get_by_label('Escala X de A', exact=True).fill('2')
                    page.get_by_role('button', name='Aplicar material y escala a A', exact=True).click()
                    page.wait_for_function('Axx.magicPen.player.v2Scene.revision===2')
                    changed = page.evaluate('Axx.magicPen.player.scene.geometrySnapshot()')
                    self.assertEqual(changed[0]['material']['metalness'], .92)
                    self.assertEqual(changed[0]['material']['color'], [1, 0, 0])
                    self.assertNotEqual(changed[0]['positions_b64'], initial[0]['positions_b64'])
                    self.assertEqual(changed[1]['positions_b64'], initial[1]['positions_b64'])
                    page.get_by_role('button', name='Guardar geometría 3D verificable como GLB', exact=True).click()
                    page.wait_for_function("document.getElementById('mp-export').textContent.includes('GLB guardado y verificado')")
                    assets = srv.rt.assets.search_assets('scene-')['registered_assets']
                    self.assertEqual(len(assets), 1)
                    raw = Path(assets[0]['storage_path']).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), assets[0]['sha256'])
                    self.assertTrue(raw.startswith(b'glTF'))
                    page.evaluate("Axx.magicPen.sceneHistoryV2('undo')")
                    self.assertEqual(page.evaluate('Axx.magicPen.player.v2Scene.revision'), 3)
                    page.evaluate("Axx.magicPen.sceneHistoryV2('redo')")
                    page.evaluate('''async()=>{Axx.magicPen.player.v2Scene=null;await Axx.magicPen.ensureSceneV2(false);}''')
                    self.assertEqual(page.evaluate('Axx.magicPen.player.v2Scene.revision'), 4)
                    self.assertEqual(page.evaluate('Axx.magicPen.player.scene.geometrySnapshot()[0].material.color'), [1, 0, 0])
                    evidence = ROOT / 'build/three-pillars/screenshots'
                    evidence.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(evidence / 'magic-pen-edit.png'))
                    (evidence.parent / 'scene-edited.glb').write_bytes(raw)
                    page.evaluate("Axx.magicPen.addRotationV2('a')")
                    video = page.evaluate('Axx.magicPen.exportSceneVideo()')
                    self.assertEqual(video['frame_count'], 50)
                    self.assertEqual(video['render_mode'], 'threejs_webgl_canvas')
                    self.assertTrue(video['motion_observed'])
                    video_raw = Path(video['output_path']).read_bytes()
                    self.assertEqual(hashlib.sha256(video_raw).hexdigest(), video['mp4_sha256'])
                    (evidence.parent / 'scene-motion.mp4').write_bytes(video_raw)
                    (evidence.parent / 'scene-motion-receipt.json').write_text(json.dumps(video, indent=2), encoding='utf-8')
                    # Reuse the actual exported mesh, not a proxy primitive.
                    inserted=page.evaluate('(id)=>Axx.magicPen.insertGlbV2(id)',assets[0]['asset_id'])
                    imported_id=inserted['document']['objects'][-1]['id']
                    imported=page.evaluate('(id)=>Axx.magicPen.player.scene.geometrySnapshot().filter(p=>p.object_id===id)',imported_id)
                    self.assertEqual(len(imported),3)
                    self.assertEqual(imported[0]['material']['metalness'],.92)
                    self.assertEqual(imported[0]['material']['color'],[1,0,0])
                    page.evaluate("Axx.magicPen.sceneHistoryV2('undo')")
                    self.assertEqual(page.evaluate('Axx.magicPen.player.scene.qa().objects'),3)
                    # The CAD worker creates three actual solids, reimports STEP, and renders its own GLB nodes.
                    page.once('dialog',lambda dialog:dialog.accept())
                    cad=page.evaluate('Axx.magicPen.buildCadV2()')
                    self.assertTrue(cad['congruence']['congruent'])
                    self.assertEqual(cad['congruence']['solid_count'],3)
                    parts=[o for o in cad['document']['objects'] if o['properties'].get('cad_task')]
                    self.assertEqual(len(parts),3)
                    self.assertEqual(page.evaluate('Axx.magicPen.player.scene.qa().objects'),6)
                    part=parts[0]
                    updated=page.evaluate('''async part=>{
                        const dims={...part.properties.dimensions,width:40};return Axx.magicPen.buildCadV2(part,dims);
                    }''',part)
                    self.assertNotEqual(updated['congruence']['step_sha256'],cad['congruence']['step_sha256'])
                    self.assertTrue(updated['congruence']['congruent'])
                    self.assertEqual(len(updated['document']['objects']),6)
                    self.assertEqual(page.evaluate('Axx.magicPen.player.scene.qa().objects'),6)
                    before=page.evaluate('Axx.magicPen.player.scene.snapshot()')
                    page.evaluate("Axx.magicPen.player.scene.setSection('x',0)")
                    self.assertNotEqual(before,page.evaluate('Axx.magicPen.player.scene.snapshot()'))
                    page.screenshot(path=str(evidence/'magic-pen-cad.png'))
                finally:
                    browser.close()
        finally:
            web.shutdown(); web.server_close()
