"""Desktop panel contract with explicit native/API fixtures, not native acceptance."""
from pathlib import Path
import os
import unittest
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
FIXTURE='''window.__TAURI__={core:{invoke:async(name,args)=>name==='native_status'?{native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop:{screenX:600,screenY:400,workWidth:1440,workHeight:960,spaceLeft:600,spaceRight:840,spaceAbove:400,spaceBelow:560}}:null},event:{listen:async()=>()=>{}}};'''


class TransferPanel(unittest.TestCase):
    def open(self, p, setup=''):
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':960},reduced_motion='reduce')
        def serve(route):
            relative=route.request.url.split('https://axx.test/',1)[1] or 'Axx.html'
            path=(ROOT/relative).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():route.abort();return
            route.fulfill(path=str(path))
        page.route('https://axx.test/**',serve)
        page.add_init_script(FIXTURE+setup)
        page.goto('https://axx.test/')
        page.wait_for_function('()=>Axx.transfer && Axx.resident?.firstFrame')
        return page

    def test_visible_tools_entry_opens_received_files_from_all_phones(self):
        with sync_playwright() as p:
            page=self.open(p,"localStorage.setItem('axx.flow.favorites',JSON.stringify(['notes','calculator']));")
            page.evaluate(r'''()=>{
              window.transferCalls=[];
              Axx.backendRequest=async(method,path,body)=>{
                transferCalls.push({method,path,body});
                if(path.endsWith('/files/status'))return {devices:[{device_id:'phone',name:'Mi teléfono',permissions:{read:true,write:true},roots:[]},{device_id:'tablet',name:'Mi tablet',permissions:{read:true,write:true},roots:[]}],transfers:[
                  {transfer_id:'received-a',device_id:'phone',name:'Plano.pdf',size:2048,direction:'to_pc',state:'completed',completed_at:1700000000},
                  {transfer_id:'received-b',device_id:'tablet',name:'Foto.jpg',size:4194304,direction:'to_pc',state:'completed',completed_at:1700000100},
                  {transfer_id:'partial',device_id:'phone',name:'Parcial.zip',size:1024,direction:'to_pc',state:'receiving'},
                  {transfer_id:'removed',device_id:'phone',name:'Eliminado.pdf',size:1024,direction:'to_pc',state:'completed',stored:false},
                  {transfer_id:'outbound',device_id:'phone',name:'Enviado.pdf',size:1024,direction:'to_phone',state:'completed'}]};
                if(path.endsWith('/files/save'))return {path:'C:\\Users\\test\\Downloads\\Plano.pdf'};
                return {};
              };
              Axx.flow.showQuick();
            }''')
            self.assertTrue(page.evaluate("Axx.flow.favorites.includes('notes') && Axx.flow.favorites.includes('calculator')"))
            self.assertEqual(page.locator('#flow-fan [data-quick="transfer"]').count(),1)
            page.locator('#flow-fan [data-quick="transfer"]').click()
            page.locator('#tf-received [data-transfer-id="received-b"]').wait_for()
            self.assertTrue(page.locator('#tf-received-panel').is_visible())
            self.assertFalse(page.locator('#tf-device-controls').is_visible())
            self.assertEqual(page.locator('#tf-heading-title').inner_text(),'Recibidos del teléfono')
            self.assertEqual(page.locator('#tf-received-count').inner_text(),'2')
            self.assertEqual(page.locator('#tf-received .tf-received-item').count(),2)
            self.assertIn('Mi tablet',page.locator('#tf-received').inner_text())
            self.assertNotIn('Parcial.zip',page.locator('#tf-received').inner_text())
            self.assertNotIn('Eliminado.pdf',page.locator('#tf-received').inner_text())
            self.assertNotIn('Enviado.pdf',page.locator('#tf-received').inner_text())
            page.locator('#tf-received [data-transfer-id="received-a"]').get_by_role('button',name='Guardar en Descargas',exact=True).click()
            page.wait_for_function("transferCalls.some(c=>c.path.endsWith('/files/save'))")
            self.assertEqual(page.evaluate("transferCalls.find(c=>c.path.endsWith('/files/save')).body"),{'transfer_id':'received-a'})
            page.locator('#tf-tab-send').click()
            page.locator('#tf-device').select_option('tablet')
            page.locator('#tf-tab-received').click()
            self.assertEqual(page.locator('#tf-received .tf-received-item').count(),2)
            if os.environ.get('AXX_TEST_EVIDENCE'):
                out=Path(os.environ['AXX_TEST_EVIDENCE']);out.mkdir(parents=True,exist_ok=True)
                page.locator('#view-transfer').evaluate('(el)=>el.scrollTop=0')
                page.screenshot(path=str(out/'received-files.png'),omit_background=True)

    def test_panel_reuses_avatar_and_sends_only_selected_authorized_file(self):
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':960},reduced_motion='reduce')
            def serve(route):
                relative=route.request.url.split('https://axx.test/',1)[1] or 'Axx.html'
                path=(ROOT/relative).resolve()
                if not path.is_relative_to(ROOT) or not path.is_file():route.abort();return
                route.fulfill(path=str(path))
            page.route('https://axx.test/**',serve)
            page.add_init_script(FIXTURE)
            page.goto('https://axx.test/')
            page.wait_for_function('()=>Axx.transfer && Axx.resident?.firstFrame')
            page.evaluate(r'''()=>{
              window.transferCalls=[];window.formBefore=Axx.app.renderer.form;
              const prior=Axx.backendRequest;
              Axx.backendRequest=async(method,path,body)=>{
                if(!path.startsWith('/axx-api/mobile/files')&&!path.startsWith('/axx-api/mobile/transfers'))return prior(method,path,body);
                transferCalls.push({method,path,body});
                if(path.endsWith('/files/status'))return {devices:[{device_id:'phone',name:'Mi teléfono',scopes:[],permissions:{read:true,write:false},roots:['C:\\Documentos']}],transfers:[]};
                if(path.endsWith('/files/search'))return {files:[{file_ref:'opaque',name:'Stand.pdf',size:2048,relative_path:'Stand.pdf',modified_at:1700000000}]};
                return {state:'preparing',name:'Stand.pdf'};
              };
              Axx.flow.showQuick();
            }''')
            page.locator('#flow-fan [data-quick="transfer"]').click()
            page.locator('#tf-tab-send').click()
            page.locator('#tf-device option[value=phone]').wait_for(state='attached')
            page.locator('#tf-tab-activity').click()
            page.locator('#tf-activity-panel details').evaluate('(el)=>el.open=true')
            self.assertTrue(page.locator('#tf-read').is_checked())
            self.assertFalse(page.locator('#tf-write').is_checked())
            self.assertEqual(page.locator('#tf-roots').input_value(),'C:\\Documentos')
            self.assertTrue(page.locator('#tf-device').is_visible())
            page.locator('#tf-tab-send').click()
            page.locator('#tf-query').fill('stand')
            page.locator('#tf-search-form button').click()
            page.locator('#tf-results button').wait_for()
            self.assertEqual(page.evaluate("transferCalls.filter(x=>x.path.endsWith('/transfers/create')).length"),0)
            page.locator('#tf-results button').click()
            page.wait_for_function("()=>transferCalls.some(x=>x.path.endsWith('/transfers/create'))")
            self.assertEqual(page.evaluate("transferCalls.find(x=>x.path.endsWith('/transfers/create')).body.file_ref"),'opaque')
            self.assertEqual(page.evaluate('Axx.app.renderer.form'),page.evaluate('formBefore'))
            if os.environ.get('AXX_TEST_EVIDENCE'):
                out=Path(os.environ['AXX_TEST_EVIDENCE']);out.mkdir(parents=True,exist_ok=True)
                page.locator('#view-transfer').evaluate('(el)=>el.scrollTop=0')
                page.screenshot(path=str(out/'desktop-files.png'),omit_background=True)
            browser.close()


if __name__=='__main__':unittest.main()
