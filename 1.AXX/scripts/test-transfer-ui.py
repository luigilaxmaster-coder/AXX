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

    def same_name_phones(self,page):
        page.evaluate(r'''()=>{
          window.phoneRows=[{device_id:'phone-OLD111',name:'SM-A217M',created_at:1700000000,permissions:{read:true,write:true},roots:['C:\\Old']},{device_id:'phone-NEW222',name:'SM-A217M',created_at:1700000100,permissions:{read:false,write:true},roots:[]}];
          window.savedGrants=[];
          const prior=Axx.backendRequest;Axx.backendRequest=async(method,path,body)=>{
            if(path.endsWith('/files/status'))return {devices:phoneRows,transfers:[]};
            if(path.endsWith('/files/permissions')){savedGrants.push(body);if(window.holdGrant)await new Promise(resolve=>window.finishGrant=resolve);return {};}
            return prior(method,path,body);
          };Axx.transfer.open();
        }''')
        page.locator('#tf-device option[value="phone-NEW222"]').wait_for(state='attached')
        page.locator('#tf-tab-activity').click()
        page.locator('#tf-activity-panel details').evaluate('(el)=>el.open=true')

    def test_same_model_links_are_distinct_and_refresh_preserves_selection_and_draft(self):
        with sync_playwright() as p:
            page=self.open(p);self.same_name_phones(page)
            self.assertEqual(page.locator('#tf-device').input_value(),'phone-NEW222')
            self.assertIn('NEW222',page.locator('#tf-device option:checked').text_content())
            self.assertRegex(page.locator('#tf-device option:checked').text_content(),r'\d')
            page.locator('#tf-device').select_option('phone-OLD111')
            page.locator('#tf-roots').fill('C:\\Draft')
            page.evaluate("phoneRows.push({device_id:'phone-NEW333',name:'SM-A217M',created_at:1700000200,permissions:{read:false,write:false},roots:[]})")
            page.locator('#tf-refresh').click()
            page.locator('#tf-device option[value="phone-NEW333"]').wait_for(state='attached')
            self.assertEqual(page.locator('#tf-device').input_value(),'phone-OLD111')
            self.assertEqual(page.locator('#tf-roots').input_value(),'C:\\Draft')
            page.locator('#tf-device').select_option('phone-NEW222')
            page.evaluate("phoneRows[1].permissions.read=true;phoneRows[1].roots=['C:\\\\Updated']")
            page.locator('#tf-refresh').click()
            page.wait_for_function("()=>document.querySelector('#tf-roots').value==='C:\\\\Updated'")
            self.assertTrue(page.locator('#tf-read').is_checked())
            self.assertEqual(page.evaluate('savedGrants.length'),0)

    def test_quoted_path_uses_selected_id_and_late_save_preserves_another_draft(self):
        with sync_playwright() as p:
            page=self.open(p);self.same_name_phones(page)
            page.locator('#tf-read').check()
            page.locator('#tf-roots').fill('"C:\\Documents"')
            page.evaluate('window.holdGrant=true')
            page.locator('#tf-permissions button').click()
            page.wait_for_function('()=>typeof finishGrant==="function"')
            self.assertEqual(page.evaluate('savedGrants[0].device_id'),'phone-NEW222')
            self.assertEqual(page.evaluate('savedGrants[0].roots'),['C:\\Documents'])
            page.locator('#tf-device').select_option('phone-OLD111')
            page.locator('#tf-roots').fill('C:\\Keep-this-draft')
            page.evaluate('finishGrant()')
            page.wait_for_function("()=>document.querySelector('#tf-status').textContent.includes('NEW222')")
            self.assertEqual(page.locator('#tf-device').input_value(),'phone-OLD111')
            self.assertEqual(page.locator('#tf-roots').input_value(),'C:\\Keep-this-draft')
            self.assertEqual(page.evaluate('savedGrants.length'),1)

    def test_new_link_cannot_redirect_ready_results_or_a_stale_send_callback(self):
        with sync_playwright() as p:
            page=self.open(p);self.same_name_phones(page)
            page.evaluate('''()=>{window.sends=[];const prior=Axx.backendRequest;Axx.backendRequest=async(m,p,b)=>{
              if(p.endsWith('/files/search'))return {files:[{file_ref:'file-A',name:'A.txt',relative_path:'A.txt',size:4,modified_at:1700000000}]};
              if(p.endsWith('/transfers/create')){sends.push(b);return {state:'ready',name:'A.txt'};}return prior(m,p,b);};}''')
            page.locator('#tf-tab-send').click();page.locator('#tf-query').fill('A.txt');page.locator('#tf-search-form button').click()
            page.locator('#tf-results button').wait_for()
            page.evaluate("window.staleSend=document.querySelector('#tf-results button').onclick;phoneRows.push({device_id:'phone-NEW333',name:'SM-A217M',created_at:1700000200,permissions:{read:true,write:true},roots:[]})")
            page.locator('#tf-refresh').click();page.locator('#tf-device option[value="phone-NEW333"]').wait_for(state='attached')
            self.assertEqual(page.locator('#tf-device').input_value(),'phone-NEW222')
            page.locator('#tf-results button').click();page.wait_for_function('()=>sends.length===1')
            self.assertEqual(page.evaluate('sends[0].device_id'),'phone-NEW222')
            page.wait_for_timeout(100)
            page.locator('#tf-device').select_option('phone-OLD111')
            self.assertEqual(page.locator('#tf-results button').count(),0)
            page.evaluate('staleSend()')
            page.wait_for_function("()=>document.querySelector('#tf-status').textContent.includes('Vuelve a elegir el archivo')")
            self.assertEqual(page.evaluate('sends.length'),1)

    def test_missing_or_revoked_link_keeps_its_draft_and_blocks_cross_device_save(self):
        with sync_playwright() as p:
            for revoked in [False,True]:
                with self.subTest(revoked=revoked):
                    page=self.open(p);self.same_name_phones(page);draft=r'C:\Unsent-for-A'
                    page.locator('#tf-roots').fill(draft)
                    page.evaluate('''revoked=>{window.originalLink=phoneRows[1];if(revoked)originalLink.revoked=true;else phoneRows=phoneRows.filter(row=>row!==originalLink);}''',revoked)
                    page.locator('#tf-refresh').click()
                    page.wait_for_function("()=>document.querySelector('#tf-device option:checked')?.disabled===true")
                    self.assertEqual(page.locator('#tf-device').input_value(),'phone-NEW222')
                    self.assertEqual(page.locator('#tf-roots').input_value(),draft)
                    self.assertTrue(page.locator('#tf-permissions button').is_disabled())
                    page.locator('#tf-permissions').dispatch_event('submit')
                    page.wait_for_function("()=>document.querySelector('#tf-status').textContent.includes('Selecciona un teléfono válido')")
                    self.assertEqual(page.evaluate('savedGrants.length'),0)
                    page.locator('#tf-device').select_option('phone-OLD111')
                    self.assertEqual(page.locator('#tf-roots').input_value(),page.evaluate('phoneRows[0].roots[0]'))
                    page.evaluate('originalLink.revoked=false;if(!phoneRows.includes(originalLink))phoneRows.push(originalLink)')
                    page.locator('#tf-refresh').click()
                    page.wait_for_function("()=>!document.querySelector('#tf-device option[value=\\\"phone-NEW222\\\"]').disabled")
                    page.locator('#tf-device').select_option('phone-NEW222')
                    self.assertEqual(page.locator('#tf-roots').input_value(),draft)
                    self.assertEqual(page.evaluate('savedGrants.length'),0)

    def test_first_link_cannot_inherit_a_draft_without_a_device(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate(r'''()=>{
              window.phoneRows=[];window.savedGrants=[];
              const prior=Axx.backendRequest;Axx.backendRequest=async(m,p,b)=>{
                if(p.endsWith('/files/status'))return {devices:phoneRows,transfers:[]};
                if(p.endsWith('/files/permissions')){savedGrants.push(b);return {};}
                return prior(m,p,b);
              };Axx.transfer.open();
            }''')
            page.locator('#tf-tab-activity').click()
            page.locator('#tf-activity-panel details').evaluate('(el)=>el.open=true')
            page.wait_for_function("()=>document.querySelector('#tf-device').value===''")
            page.evaluate(r'''()=>{
              window.disabledWithoutDevice=['tf-read','tf-write','tf-roots'].every(id=>document.getElementById(id).disabled);
              const roots=document.getElementById('tf-roots');roots.value='C:\\Unbound';roots.dispatchEvent(new Event('input'));
              phoneRows.push({device_id:'phone-FIRST',name:'SM-A217M',permissions:{read:false,write:true},roots:['C:\\Current']});
            }''')
            page.locator('#tf-refresh').click()
            page.locator('#tf-device option[value="phone-FIRST"]').wait_for(state='attached')
            self.assertEqual(page.locator('#tf-roots').input_value(),r'C:\Current')
            self.assertFalse(page.locator('#tf-read').is_checked())
            self.assertTrue(page.locator('#tf-write').is_checked())
            self.assertTrue(page.evaluate('disabledWithoutDevice'))
            self.assertEqual(page.evaluate('savedGrants.length'),0)
            page.locator('#tf-permissions button').click()
            page.wait_for_function('()=>savedGrants.length===1')
            self.assertEqual(page.evaluate('savedGrants[0].device_id'),'phone-FIRST')
            self.assertEqual(page.evaluate('savedGrants[0].roots'),[r'C:\Current'])

    def test_late_search_and_revoked_link_cannot_publish_or_send_old_results(self):
        with sync_playwright() as p:
            page=self.open(p);self.same_name_phones(page)
            page.evaluate('''()=>{window.sends=[];window.holdSearch=true;const prior=Axx.backendRequest;Axx.backendRequest=async(m,p,b)=>{
              if(p.endsWith('/files/search')){const result={files:[{file_ref:'old-file',name:'Old.txt',relative_path:'Old.txt',size:4,modified_at:1700000000}]};if(holdSearch)await new Promise(resolve=>window.finishSearch=resolve);return result;}
              if(p.endsWith('/transfers/create')){sends.push(b);return {state:'ready'};}return prior(m,p,b);};}''')
            page.locator('#tf-tab-send').click();page.locator('#tf-query').fill('Old.txt');page.locator('#tf-search-form button').click()
            page.wait_for_function('()=>typeof finishSearch==="function"')
            page.locator('#tf-device').select_option('phone-OLD111')
            page.evaluate('async()=>{finishSearch();await new Promise(requestAnimationFrame);}')
            self.assertEqual(page.locator('#tf-results button').count(),0)
            page.evaluate('holdSearch=false')
            page.locator('#tf-search-form button').click();page.locator('#tf-results button').wait_for()
            page.evaluate("()=>{window.revokedSend=document.querySelector('#tf-results button').onclick;phoneRows[0].revoked=true;}")
            page.locator('#tf-refresh').click()
            page.wait_for_function("()=>document.querySelector('#tf-device option:checked')?.disabled===true")
            self.assertEqual(page.locator('#tf-results button').count(),0)
            page.evaluate('revokedSend()')
            page.wait_for_function("()=>document.querySelector('#tf-status').textContent.includes('Vuelve a elegir el archivo')")
            self.assertEqual(page.evaluate('sends.length'),0)

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
