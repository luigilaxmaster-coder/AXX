"""Browser contracts with an explicit native fixture; no physical phone claim."""
import unittest
import re
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE, LINK

FIXTURE = NATIVE_FIXTURE + '''
window.commands=[{id:'axx.generated.example',title:'Ejemplo aprobado',description:'Herramienta de la PC',pc_approval_required:false,
 parameters:{enabled:{type:'boolean',required:true},values:{type:'array',required:true},limit:{type:'integer'}}}];
window.scopes=['query','tools.control'];window.sent=[];window.receipt={state:'unknown',postconditions_passed:false};
window.textMode='standard';window.failTextSize=false;
Capacitor.Plugins.AxxTransport.textSize=async(args={})=>{if(failTextSize)throw Error('No se guardó');if(args.mode)textMode=args.mode;return {mode:textMode};};
window.snapshot={conversation_id:'shared',messages:[],appearance:{settings:{form:3,palette:1,scale:1},studio:{living:true},camera:[0,0],finish:'prism'},pc_name:'Mi PC',inference:{model:'modelo-PC'}};
Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,device_id:'device',endpoint:'https://192.168.0.10:4443',fingerprint:'test',scopes});
const baseRequest=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async args=>{
 if(args.path.startsWith('/v1/command?'))throw Error('PC error (404)');
 if(args.path==='/v1/snapshot')return {data:{...snapshot,scopes}};
 if(args.path==='/v1/work/catalog')return {data:{commands}};
 if(args.path==='/v1/work/execute'){sent.push(args.body);return {data:receipt};}
 if(args.path.startsWith('/v1/work/operation'))return {data:receipt};
 return baseRequest(args);
};
'''


class CompanionUI(unittest.TestCase):
    def test_text_size_choice_and_failure_keep_the_confirmed_setting(self):
        with sync_playwright() as p:
            page=self.open(p,339)
            page.locator('[data-pane=pc]').click()
            self.assertEqual(page.locator('#text-size').input_value(),'standard')
            page.locator('#text-size').select_option('system')
            page.wait_for_function('()=>textMode==="system"')
            page.evaluate('failTextSize=true')
            page.locator('#text-size').select_option('standard')
            page.wait_for_function('()=>!document.querySelector("#text-size").disabled')
            self.assertEqual(page.locator('#text-size').input_value(),'system')
            self.assertIn('No se pudo cambiar',page.locator('#notice').inner_text())

    def test_chat_receipts_use_readable_states_and_preserve_single_delivery(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{window.chatCount=0;const request=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                if(args.path==='/v1/commands'){chatCount++;return {data:{task_id:'internal-receipt-id',state:'queued'}};}
                if(args.path.startsWith('/v1/command?'))return {data:{task_id:'internal-receipt-id',state:'completed'}};
                return request(args);
              };}''')
            page.locator('[data-pane=chat]').click();page.locator('#draft').fill('hola')
            page.locator('#send').click()
            page.wait_for_function('()=>document.querySelector("#command-state").textContent==="Respuesta recibida"')
            self.assertEqual(page.evaluate('chatCount'),1)
            self.assertNotIn('internal-receipt-id',page.locator('#command-state').inner_text())
            self.assertEqual(page.locator('#draft').input_value(),'')

    def test_phone_layout_large_text_and_keyboard_keep_navigation_and_composer_visible(self):
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':339,'height':673},reduced_motion='reduce')
            def serve(route):
                path=ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html')
                if path.suffix=='.css':
                    # Android WebView textZoom scales explicit px text as well as rem.
                    css=re.sub(r'(font-size:|font:)([\d.]+)px',lambda m:m[1]+str(float(m[2])*1.7)+'px',path.read_text(encoding='utf-8'))
                    route.fulfill(body=css,content_type='text/css')
                else:route.fulfill(path=str(path))
            page.route('https://axx.test/**',serve);page.add_init_script(FIXTURE);page.goto('https://axx.test/')
            page.locator('#sync-status[data-state=complete]').wait_for()
            self.assertFalse(page.locator('.intro').count())
            self.assertGreaterEqual(page.locator('#axx-avatar-canvas').bounding_box()['height'],160)
            self.assertLess(page.locator('#open-chat').bounding_box()['y'],600)
            for name in ['chat','work','pc','axx']:
                page.locator('[data-pane='+name+']').click()
                self.assertTrue(page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight'))
                self.assertGreaterEqual(page.locator('[data-pane='+name+']').bounding_box()['height'],48)
            page.locator('[data-pane=chat]').click();page.locator('#draft').fill('Borrador conservado')
            page.locator('#draft').focus()
            page.set_viewport_size({'width':339,'height':299})
            send=page.locator('#send').bounding_box();nav=page.locator('.live-nav').bounding_box()
            self.assertLessEqual(send['y']+send['height'],nav['y']+1)
            self.assertEqual(page.locator('#draft').input_value(),'Borrador conservado')
            browser.close()

    def test_pc_palette_finish_and_lighting_change_the_shared_character(self):
        with sync_playwright() as p:
            page=self.open(p,339)
            before=page.locator('#axx-avatar-canvas').evaluate('(c)=>c.toDataURL()')
            page.evaluate('()=>{snapshot.appearance.settings.palette=2;snapshot.appearance.finish="obsidian";snapshot.appearance.studio.exposure=1.6;}')
            page.locator('#refresh').click()
            page.wait_for_function('()=>axxMobileRenderer.settings.palette===2 && axxMobileRenderer.finish==="obsidian"')
            self.assertEqual(page.evaluate('axxMobileRenderer.getStudio().exposure'),1.6)
            self.assertNotEqual(before,page.locator('#axx-avatar-canvas').evaluate('(c)=>c.toDataURL()'))

    def test_unconfirmed_delivery_does_not_break_reconnection_or_resend(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{
              localStorage.setItem('axx.mobile.pending',JSON.stringify({command_id:'unconfirmed',text:'Mi borrador'}));
              localStorage.setItem('axx.mobile.draft','Mi borrador');
            }''')
            page.reload()
            page.locator('#sync-status[data-state=complete]').wait_for()
            page.locator('[data-pane=chat]').click()
            # The fixture has no command receipt: its pending lookup must not
            # turn an authenticated snapshot into a disconnected PC.
            page.wait_for_function('()=>document.querySelector("#command-state").textContent.includes("sin confirmar")')
            self.assertTrue(page.locator('#pc-dot.online').is_visible())
            self.assertTrue(page.locator('#send').is_disabled())
            page.on('dialog',lambda dialog:dialog.accept())
            page.locator('#forget-delivery').click()
            self.assertEqual(page.locator('#draft').input_value(),'Mi borrador')
            self.assertTrue(page.locator('#send').is_enabled())
            self.assertEqual(page.evaluate('sent.length'),0)

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
            page.locator('[data-pane=chat]').click()
            page.locator('#draft').fill('Mi borrador')
            page.evaluate("snapshot.messages=[{id:'m1',role:'assistant',text:'Nuevo mensaje del PC',source:'desktop'}];snapshot.appearance.settings.form=19;snapshot.inference.model='nuevo-modelo';scopes=['query'];")
            page.wait_for_function("() => document.querySelector('#model-state').textContent.includes('nuevo-modelo')")
            self.assertIn('Nuevo mensaje del PC',page.locator('#messages').inner_text())
            self.assertEqual(page.locator('#draft').input_value(),'Mi borrador')
            self.assertEqual(page.evaluate('axxMobileRenderer.form'),19)
            self.assertEqual(page.locator('.permission-row[data-granted=true]').count(),1)
            page.locator('[data-pane=axx]').click()
            page.locator('#open-catalog').click()
            page.locator('#work-commands-card details summary').click()
            page.locator('#work-command-select option').wait_for(state='attached')
            self.assertEqual(page.locator('#work-command-select').input_value(),'axx.generated.example')
            page.locator('#work-command-filter').fill('sin coincidencia')
            self.assertEqual(page.locator('#work-command-select option').count(),0)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_typed_parameters_unknown_effect_is_not_replayed_or_called_verified(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('#open-catalog').click()
            page.locator('#work-commands-card details summary').click()
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
