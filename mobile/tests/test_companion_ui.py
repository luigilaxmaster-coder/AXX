"""Browser contracts with an explicit native fixture; no physical phone claim."""
import unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE, LINK

FIXTURE = NATIVE_FIXTURE + '''
window.commands=[{id:'axx.generated.example',title:'Ejemplo aprobado',description:'Herramienta de la PC',pc_approval_required:false,
 parameters:{enabled:{type:'boolean',required:true},values:{type:'array',required:true},limit:{type:'integer'}}}];
window.scopes=['query','tools.control'];window.sent=[];window.receipt={state:'unknown',postconditions_passed:false};
window.snapshot={conversation_id:'shared',messages:[],appearance:{settings:{form:3,palette:1,scale:1},studio:{living:true},camera:[0,0],finish:'prism'},pc_name:'Mi PC',inference:{model:'modelo-PC'}};
Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,device_id:'device',endpoint:'https://192.168.0.10:4443',fingerprint:'test',scopes});
const baseRequest=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async args=>{
 if(args.path==='/v1/snapshot')return {data:{...snapshot,scopes}};
 if(args.path==='/v1/work/catalog')return {data:{commands}};
 if(args.path==='/v1/work/execute'){sent.push(args.body);return {data:receipt};}
 if(args.path.startsWith('/v1/work/operation'))return {data:receipt};
 return baseRequest(args);
};
'''


class CompanionUI(unittest.TestCase):
    def open(self, playwright, width=390):
        browser=playwright.chromium.launch()
        page=browser.new_page(viewport={'width':width,'height':844},reduced_motion='reduce')
        page.set_default_timeout(7000)
        page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
        page.add_init_script(FIXTURE)
        page.goto('https://axx.test/')
        page.locator('#sync-status[data-state=complete]').wait_for()
        return page

    def test_live_snapshot_permissions_catalog_and_draft_survive_polling(self):
        with sync_playwright() as p:
            page=self.open(p,339)
            page.locator('#draft').fill('Mi borrador')
            page.evaluate("snapshot.messages=[{id:'m1',role:'assistant',text:'Nuevo mensaje del PC',source:'desktop'}];snapshot.appearance.settings.form=19;snapshot.inference.model='nuevo-modelo';scopes=['query'];")
            page.wait_for_function("() => document.querySelector('#model-state').textContent.includes('nuevo-modelo')")
            self.assertIn('Nuevo mensaje del PC',page.locator('#messages').inner_text())
            self.assertEqual(page.locator('#draft').input_value(),'Mi borrador')
            self.assertEqual(page.evaluate('axxMobileRenderer.form'),19)
            self.assertEqual(page.locator('.permission-row[data-granted=true]').count(),1)
            page.locator('#open-catalog').click()
            page.locator('#work-command-select option').wait_for(state='attached')
            self.assertEqual(page.locator('#work-command-select').input_value(),'axx.generated.example')
            page.locator('#work-command-filter').fill('sin coincidencia')
            self.assertEqual(page.locator('#work-command-select option').count(),0)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_typed_parameters_unknown_effect_is_not_replayed_or_called_verified(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('#open-catalog').click()
            page.locator('[data-field=enabled]').check()
            page.locator('[data-field=values]').fill('[1,2]')
            page.locator('#work-generic-form button').click()
            page.wait_for_function('() => sent.length===1')
            self.assertEqual(page.evaluate('sent[0].inputs'),{'enabled':True,'values':[1,2]})
            page.wait_for_function("() => document.querySelector('#work-status').textContent.includes('unknown')")
            self.assertNotIn('verificado',page.locator('#work-status').inner_text())
            page.locator('#work-generic-form button').click()
            self.assertEqual(page.evaluate('sent.length'),1)
            page.evaluate("receipt={state:'succeeded',postconditions_passed:true,output:{value:3}}")
            page.wait_for_function("() => document.querySelector('#work-status').textContent.includes('Ejecutado y verificado')")
            self.assertEqual(page.evaluate('sent.length'),1)

    def test_malformed_pair_link_cannot_reach_native_pair(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('()=>{window.pairCount=0;Capacitor.Plugins.AxxTransport.pair=async()=>{pairCount++;};}')
            page.locator('#pc-button').click()
            page.locator('#pair-manual summary').click()
            page.locator('#pair-uri').fill(LINK+'&code=duplicate')
            page.locator('#pair-submit').click()
            self.assertEqual(page.evaluate('pairCount'),0)
            self.assertIn('QR válido',page.locator('#pair-error').inner_text())
