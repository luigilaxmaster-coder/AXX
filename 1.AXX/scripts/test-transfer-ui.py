"""Desktop panel contract with explicit native/API fixtures, not native acceptance."""
from pathlib import Path
import os
import unittest
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
FIXTURE='''window.__TAURI__={core:{invoke:async(name,args)=>name==='native_status'?{native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop:{screenX:600,screenY:400,workWidth:1440,workHeight:960,spaceLeft:600,spaceRight:840,spaceAbove:400,spaceBelow:560}}:null},event:{listen:async()=>()=>{}}};'''


class TransferPanel(unittest.TestCase):
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
              Axx.transfer.open();
            }''')
            page.locator('#tf-device option[value=phone]').wait_for(state='attached')
            self.assertTrue(page.locator('#tf-read').is_checked())
            self.assertFalse(page.locator('#tf-write').is_checked())
            self.assertEqual(page.locator('#tf-roots').input_value(),'C:\\Documentos')
            self.assertTrue(page.locator('#tf-device').is_visible())
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
