"""Operational mission screen with a declared native fixture, not a phone test."""
import json
import re
import unittest

from playwright.sync_api import sync_playwright
from mobile.tests.test_companion_ui import FIXTURE as BASE_FIXTURE
from mobile.tests.test_ui import ROOT


MISSION_FIXTURE = r'''
window.missionPin='a'.repeat(64);
Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,device_id:'device',endpoint:'https://192.168.0.10:4443',fingerprint:missionPin,scopes});
snapshot.capabilities={avatar_customization:true,mission_continuity:true};
window.missionDetail=JSON.parse(localStorage.getItem('fixture.mission.detail')||'null')||{
 operation_id:'pc-existing-mission',conversation_id:'shared',project_id:'project-a',state:'goal_pending',goal_revision:1,plan_hash:'1'.repeat(64),executor:'pc',can_correct:true,
 memory_scope:{task_id:'pc-task',generation:0},memory_context_id:'PRIVATE_MISSION_CONTEXT',
 goal_spec:{intent:'Guardar el informe',destination:'project-a/same.txt',checks:[],criteria:[{id:'report',kind:'text_exact',parameters:{path:'project-a/same.txt',text:'resultado'}}]},
 mission:{mission_id:'pc-existing-mission',objective:'Guardar el informe',destination:'project-a/same.txt',verified_steps:[0],pending_steps:[1],completed:false,budget:{model_calls_used:1,model_call_limit:2}}
};
window.missionReceipt=JSON.parse(localStorage.getItem('fixture.mission.receipt')||'null');
const beforeMissionRequest=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async args=>{
 if(!args.path.startsWith('/v1/work/mission'))return beforeMissionRequest(args);
 if(args.expected_device_id!=='device'||args.expected_fingerprint!==missionPin)throw Error('binding');
 if(args.path==='/v1/work/missions?conversation_id=shared')return {data:{conversation_id:'shared',executor:'pc',missions:[structuredClone(missionDetail)]}};
 if(args.path.startsWith('/v1/work/mission?'))return {data:structuredClone(missionDetail)};
 if(args.path.startsWith('/v1/work/mission-correction?')){
   localStorage.setItem('fixture.mission.queriedCommand',new URL(args.path,'https://axx.test').searchParams.get('command_id'));
   return {data:structuredClone(missionReceipt)};
 }
 if(args.path==='/v1/work/mission-correct'){
   const body=structuredClone(args.body);window.lastMissionBody=body;
   localStorage.setItem('fixture.mission.postCount',String(Number(localStorage.getItem('fixture.mission.postCount')||0)+1));
   const receipt={id:'host-derived-request',request_hash:'f'.repeat(64),state:'awaiting_approval',origin_device_id:'device',from_plan_hash:body.plan_hash,from_goal_revision:body.goal_revision,plan_hash:'2'.repeat(64),goal_revision:body.goal_revision+1};
   missionDetail={...missionDetail,state:'awaiting_approval',goal_revision:receipt.goal_revision,plan_hash:receipt.plan_hash,goal_spec:body.goal_spec,mission:{...missionDetail.mission,destination:body.goal_spec.destination}};
   missionReceipt={command_id:body.command_id,operation_id:body.operation_id,conversation_id:body.conversation_id,executor:'pc',state:'confirmed',from_plan_hash:body.plan_hash,from_goal_revision:body.goal_revision,receipt,mission:structuredClone(missionDetail)};
   localStorage.setItem('fixture.mission.detail',JSON.stringify(missionDetail));localStorage.setItem('fixture.mission.receipt',JSON.stringify(missionReceipt));
   if(localStorage.getItem('fixture.mission.loseAck')){localStorage.removeItem('fixture.mission.loseAck');throw Error('lost acknowledgement');}
   return {data:structuredClone(missionReceipt)};
 }
 throw Error('Unexpected mission fixture route');
};
'''

FIXTURE = BASE_FIXTURE + MISSION_FIXTURE


class MobileMissionUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 339, 'height': 673}, reduced_motion='reduce')
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)

        def serve(route):
            relative = route.request.url.split('https://axx.test/', 1)[1] or 'index.html'
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                route.abort()
                return
            if path.suffix == '.css':
                css = re.sub(r'(font-size:|font:)([\d.]+)px', lambda m: m[1] + str(float(m[2]) * 1.7) + 'px', path.read_text(encoding='utf-8'))
                route.fulfill(body=css, content_type='text/css')
            else:
                route.fulfill(path=str(path))

        self.page.route('https://axx.test/**', serve)
        self.page.add_init_script(FIXTURE)
        self.page.goto('https://axx.test/')
        self.page.locator('#sync-status[data-state=complete]').wait_for()
        self.page.locator('[data-pane=work]').click()
        self.page.locator('#work-activity > summary').click()
        self.page.locator('#mission-continuity').wait_for(state='visible')
        self.page.locator('#mission-continuity > summary').click()
        self.page.get_by_role('button', name='Abrir misión', exact=True).click()
        self.page.locator('#mission-editor').wait_for(state='visible')

    def tearDown(self):
        self.context.close()

    def edit_destination(self):
        goal = json.loads(self.page.locator('#mission-goal').input_value())
        goal['destination'] = 'project-b/same.txt'
        goal['criteria'][0]['parameters']['path'] = 'project-b/same.txt'
        self.page.locator('#mission-goal').fill(json.dumps(goal, ensure_ascii=False))
        self.page.locator('#mission-correction').fill('Usa project-b/same.txt y conserva el prefijo verificado.')
        self.page.locator('#mission-review').click()
        self.assertTrue(self.page.locator('#mission-prepare').is_enabled())
        return goal

    def test_reachable_review_changes_real_contract_and_prepares_original_mission(self):
        self.assertIn('pc-existing-mission', self.page.locator('#mission-identity').inner_text())
        self.assertIn('project-a/same.txt', self.page.locator('#mission-destination').inner_text())
        goal = self.edit_destination()
        self.assertNotIn('PRIVATE_MISSION_CONTEXT', self.page.locator('#mission-review-json').input_value())
        self.page.locator('#mission-prepare').click()
        self.page.wait_for_function("()=>document.querySelector('#mission-status').textContent.includes('Preparado;')")
        body = self.page.evaluate('lastMissionBody')
        self.assertEqual(body['operation_id'], 'pc-existing-mission')
        self.assertEqual(body['goal_revision'], 1)
        self.assertEqual(body['goal_spec'], goal)
        self.assertNotIn('approved', body)
        self.assertEqual(self.page.evaluate("Number(localStorage.getItem('fixture.mission.postCount'))"), 1)

    def test_lost_ack_reload_queries_original_receipt_without_reposting(self):
        self.edit_destination()
        self.page.evaluate("localStorage.setItem('fixture.mission.loseAck','1')")
        self.page.locator('#mission-prepare').click()
        self.page.wait_for_function("()=>localStorage.getItem('fixture.mission.postCount')==='1' && !!localStorage.getItem('axx.missionContinuity.pending')")
        command = self.page.evaluate("JSON.parse(localStorage.getItem('axx.missionContinuity.pending')).body.command_id")
        self.page.reload()
        self.page.locator('#sync-status[data-state=complete]').wait_for()
        self.page.locator('[data-pane=work]').click()
        self.page.locator('#work-activity > summary').click()
        self.page.locator('#mission-continuity').wait_for(state='visible')
        self.page.locator('#mission-continuity > summary').click()
        self.page.wait_for_function("()=>!localStorage.getItem('axx.missionContinuity.pending')")
        self.assertEqual(self.page.evaluate("Number(localStorage.getItem('fixture.mission.postCount'))"), 1)
        self.assertEqual(self.page.evaluate('missionReceipt.command_id'), command)
        self.assertEqual(self.page.evaluate("localStorage.getItem('fixture.mission.queriedCommand')"), command)

    def test_large_text_and_keyboard_preserve_draft_and_bounded_width(self):
        self.edit_destination()
        self.page.locator('#mission-correction').fill('Borrador del usuario')
        self.assertTrue(self.page.locator('#mission-prepare').is_disabled())
        self.page.locator('#mission-correction').focus()
        self.page.set_viewport_size({'width': 339, 'height': 299})
        self.assertEqual(self.page.locator('#mission-correction').input_value(), 'Borrador del usuario')
        self.assertTrue(self.page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'))
        for selector in ('#pane-work', '#mission-continuity', '#mission-editor'):
            self.assertTrue(self.page.locator(selector).evaluate('(node)=>node.scrollWidth<=node.clientWidth'))
        self.assertEqual(self.page.get_by_label('Objetivo completo (JSON): revisa destino, comprobaciones y criterios', exact=True).count(), 1)
        correction = self.page.get_by_label('Corrección que debe preparar la PC', exact=True)
        correction.scroll_into_view_if_needed()
        correction.focus()
        self.assertTrue(correction.evaluate('(node)=>document.activeElement===node'))
        field = correction.bounding_box()
        pane = self.page.locator('#pane-work').bounding_box()
        self.assertGreater(field['y'] + field['height'], pane['y'])
        self.assertLess(field['y'], pane['y'] + pane['height'])
        self.assertEqual(self.page.locator('#mission-status').get_attribute('aria-live'), 'polite')

    def test_known_forgetting_purges_owned_content_and_keeps_pending_identity(self):
        self.edit_destination()
        self.page.locator('#mission-correction').fill('FORGOTTEN_BROWSER_CONTENT_7294')
        self.page.locator('#mission-review').click()
        self.page.evaluate("localStorage.setItem('fixture.mission.loseAck','1')")
        self.page.locator('#mission-prepare').click()
        self.page.wait_for_function("()=>localStorage.getItem('fixture.mission.postCount')==='1' && !!localStorage.getItem('axx.missionContinuity.pending')")
        command = self.page.evaluate("JSON.parse(localStorage.getItem('axx.missionContinuity.pending')).body.command_id")
        self.page.evaluate("""()=>{
          missionReceipt={...missionReceipt,state:'outcome_unknown',memory_forgotten:true};delete missionReceipt.receipt;
          missionDetail={...missionDetail,memory_forgotten:true,can_correct:false};
          localStorage.setItem('fixture.mission.receipt',JSON.stringify(missionReceipt));
          localStorage.setItem('fixture.mission.detail',JSON.stringify(missionDetail));
        }""")
        self.page.locator('#mission-reconcile').click()
        self.page.wait_for_function("()=>JSON.parse(localStorage.getItem('axx.missionContinuity.pending')||'null')?.memory_forgotten===true")
        owned = self.page.evaluate("()=>Object.entries(localStorage).filter(([key])=>key.startsWith('axx.missionContinuity.'))")
        self.assertNotIn('FORGOTTEN_BROWSER_CONTENT_7294', json.dumps(owned))
        self.assertNotIn('PRIVATE_MISSION_CONTEXT', json.dumps(owned))
        pending = self.page.evaluate("JSON.parse(localStorage.getItem('axx.missionContinuity.pending'))")
        self.assertEqual(set(pending['body']), {'command_id', 'operation_id', 'conversation_id', 'plan_hash', 'goal_revision'})
        self.assertEqual(pending['body']['command_id'], command)
        self.assertTrue(self.page.locator('#mission-editor').is_hidden())
        self.assertEqual(self.page.locator('#mission-goal').input_value(), '')
        self.assertEqual(self.page.locator('#mission-correction').input_value(), '')
        self.page.reload()
        self.page.locator('#sync-status[data-state=complete]').wait_for()
        self.assertEqual(self.page.evaluate("Number(localStorage.getItem('fixture.mission.postCount'))"), 1)
        self.assertEqual(self.page.evaluate("JSON.parse(localStorage.getItem('axx.missionContinuity.pending')).body.command_id"), command)


if __name__ == '__main__':
    unittest.main()
