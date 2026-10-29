"""Browser contracts for real-state UI; native storage/transport are explicit fixtures."""
import os
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE

FIXTURE = NATIVE_FIXTURE + r'''
window.calls=[];window.locals=[];window.transfer=null;window.holdCommit=false;window.readAllowed=true;
window.binding={device_id:'phone',fingerprint:'test'};
const hash='a'.repeat(64);
Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,...binding,endpoint:'https://192.168.0.10:4443',scopes:['query','files.read','files.write']});
const prior=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async args=>{
 calls.push(args);
 if((args.path.startsWith('/v1/files/')||args.path.startsWith('/v1/transfers')) && (args.expected_device_id!==binding.device_id||args.expected_fingerprint!==binding.fingerprint))throw Error('Unbound file request');
 const body=args.body||{};
 if(args.path==='/v1/files/status')return {data:{max_size:10737418240,permissions:{read:readAllowed,write:true},transfers:transfer?[transfer]:[]}};
 if(args.path==='/v1/files/browse'){
   if(!readAllowed)throw Error('Lectura sin autorizar');
   const root={name:'Carpetas',folder_ref:null},project={name:'Proyectos',folder_ref:'projects'};
   if(!body.folder_ref)return {data:{folders:[project,{name:'Fotos',folder_ref:'photos'}],files:[],breadcrumbs:[root],next_offset:null}};
   const first={file_ref:'plan',name:'Plano.pdf',root_name:'Proyectos',relative_path:'Plano.pdf',size:4,modified_at:1700000000};
   return {data:{folders:[],files:body.offset?[{...first,file_ref:'plan-refreshed'},{...first,file_ref:'report',name:'Informe.pdf',relative_path:'Informe.pdf'}]:[first],breadcrumbs:[root,project],next_offset:body.offset?null:40}};
 }
 if(args.path==='/v1/files/search'){
   const first={file_ref:'one',name:body.kind==='images'?'Foto.jpg':body.kind==='documents'?'Documento.pdf':'Stand.pdf',size:4,root_name:'Proyectos',relative_path:'Stand.pdf',modified_at:1700000000};
   return {data:{files:[first,{...first,file_ref:'two',name:'Stand anterior.pdf',relative_path:'Stand anterior.pdf'}]}};
 }
 if(args.path==='/v1/transfers/create'){
   if(!transfer)transfer={...body,name:body.name||'Stand.pdf',size:4,sha256:hash,chunk_size:262144,chunk_count:1,state:body.direction==='to_pc'?'receiving':'ready',confirmed_bytes:0};
   return {data:{...transfer}};
 }
 if(args.path.startsWith('/v1/transfers?'))return {data:{...transfer}};
 if(args.path==='/v1/transfers/chunk'){
   if(body.data){transfer.confirmed_bytes=4;return {data:{...transfer}};}
   return {data:{data:'YWJjZA==',bytes:4,index:0,sha256:hash}};
 }
 if(args.path==='/v1/transfers/receipt'){
   if(!locals.some(f=>f.state==='received'))throw Error('Receipt before native persistence');
   transfer.state='completed';return {data:{...transfer}};
 }
 if(args.path==='/v1/transfers/finish'){transfer.state='completed';return {data:{...transfer}};}
 if(args.path==='/v1/transfers/pause'){transfer.state='paused';return {data:{...transfer}};}
 if(args.path==='/v1/transfers/resume'){transfer.state='ready';return {data:{...transfer}};}
 if(args.path==='/v1/transfers/cancel'){transfer.state='cancelled';return {data:{...transfer}};}
 return prior(args);
};
Capacitor.Plugins.AxxFiles={
 capacity:async()=>({max_size:10737418240,free_bytes:8589934592}),
 list:async()=>({files:locals}),
 choose:async()=>{const f={file_id:'local',name:'Foto.png',size:4,sha256:hash,state:'ready'};locals.push(f);return f;},
 readChunk:async()=>({index:0,data:'YWJjZA==',bytes:4}),
 beginReceive:async b=>{let f=locals.find(f=>f.file_id===b.transfer_id);if(!f){f={...b,file_id:b.transfer_id,next_index:0,confirmed_bytes:0,state:'receiving'};locals.push(f);}return {...f};},
 writeChunk:async b=>{const f=locals.find(f=>f.file_id===b.transfer_id);f.next_index=1;f.confirmed_bytes=4;return {...f};},
 finishReceive:async b=>{if(holdCommit)await new Promise(r=>window.commitNow=r);const f=locals.find(f=>f.file_id===b.transfer_id);f.state='received';return {...f};},
 export:async()=>({exported:true}),cancel:async()=>({cancelled:true})
};
'''


class TransferUI(unittest.TestCase):
    def open(self, p, setup=''):
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':339,'height':673},reduced_motion='reduce')
        def serve(route):
            relative=route.request.url.split('https://axx.test/',1)[1] or 'index.html'
            # Test these source changes without rebuilding or altering www output.
            base=ROOT.parent if relative in ('js/transfer.js','css/transfer.css') else ROOT
            route.fulfill(path=str(base/relative))
        page.route('https://axx.test/**',serve)
        page.add_init_script(FIXTURE+setup)
        page.goto('https://axx.test/')
        page.locator('#sync-status[data-state=complete]').wait_for()
        return page

    def test_browse_folders_recents_types_and_pagination_at_339px(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('#tfm-launch').click()
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).wait_for()
            evidence=os.environ.get('AXX_TEST_EVIDENCE')
            if evidence:
                Path(evidence).mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(Path(evidence)/'phone-folders.png'))
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).click()
            page.locator('#tfm-browser-list .tf-file').wait_for()
            self.assertEqual(page.locator('#tfm-query').input_value(),'')
            self.assertEqual(page.locator('#tfm-breadcrumbs [aria-current=page]').inner_text(),'Proyectos')
            page.locator('#tfm-more').click()
            page.wait_for_function("()=>document.querySelectorAll('#tfm-browser-list .tf-file').length===2")
            self.assertEqual(page.locator('#tfm-browser-list').inner_text().count('Plano.pdf'),2)  # Name and path, one card.
            self.assertFalse(page.locator('#tfm-more').is_visible())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/browse').at(-1).body.offset"),40)
            page.get_by_role('button',name='Abrir Carpetas',exact=True).click()
            page.get_by_role('button',name='Abrir carpeta Fotos',exact=True).wait_for()
            page.locator('#tfm-recents').click()
            page.locator('#tfm-browser-list .tf-file').nth(1).wait_for()
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/search').at(-1).body.query"),'')
            page.locator('#tfm-kind').select_option('images')
            page.get_by_text('Foto.jpg',exact=True).wait_for()
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/search').at(-1).body.kind"),'images')
            self.assertIn('10.0 GiB por archivo',page.locator('#tfm-capacity').inner_text())
            self.assertIn('8.0 GiB libres',page.locator('#tfm-capacity').inner_text())
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            self.assertTrue(page.locator('#files-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth'))
            page.locator('#tfm-tab-results').focus()
            page.locator('#tfm-tab-results').press('End')
            self.assertEqual(page.locator('#tfm-tab-history').get_attribute('aria-selected'),'true')
            page.locator('#tfm-tab-history').press('Home')
            self.assertEqual(page.locator('#tfm-tab-results').get_attribute('aria-selected'),'true')
            if evidence:
                page.locator('#tfm-results').scroll_into_view_if_needed()
                page.screenshot(path=str(Path(evidence)/'phone-file-browser.png'))

    def test_failed_next_page_retries_folder_and_discloses_partial_scan(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{const prior=Capacitor.Plugins.AxxTransport.request;
              window.failNext=true;window.partialScan=false;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                if(args.path==='/v1/files/browse'&&args.body.offset&&failNext){failNext=false;throw Error('Conexión interrumpida');}
                const result=await prior(args);
                if(args.path==='/v1/files/browse'&&args.body.folder_ref&&partialScan){result.data.next_offset=null;result.data.truncated=true;}
                return result;
              };}''')
            page.locator('#tfm-launch').click()
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).click()
            page.locator('#tfm-more').click()
            page.get_by_role('button',name='Volver a intentar',exact=True).wait_for()
            self.assertFalse(page.locator('#tfm-more').is_visible())
            page.evaluate('partialScan=true')
            page.get_by_role('button',name='Volver a intentar',exact=True).click()
            page.wait_for_function("()=>document.querySelector('#tfm-status').textContent.includes('Listado parcial')")
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/browse').at(-1).body.offset"),0)
            self.assertFalse(page.locator('#tfm-more').is_visible())
            self.assertEqual(page.locator('#tfm-browser-list .tf-file').count(),1)

    def test_download_limits_use_native_capacity_and_show_disabled_actions(self):
        with sync_playwright() as p:
            page=self.open(p,'''Capacitor.Plugins.AxxFiles.capacity=async()=>({max_size:5368709120,free_bytes:1073741824});
              const priorCapacity=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                const result=await priorCapacity(args);
                if(args.path==='/v1/files/search')result.data.files=[{file_ref:'huge',name:'Grande.zip',relative_path:'Grande.zip',size:6442450944,modified_at:1700000000},{file_ref:'full',name:'Espacio.zip',relative_path:'Espacio.zip',size:2147483648,modified_at:1700000000}];
                return result;
              };''')
            page.locator('#tfm-launch').click()
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).wait_for()
            page.locator('#tfm-recents').click()
            page.locator('#tfm-browser-list .tf-file').nth(1).wait_for()
            self.assertIn('5.0 GiB por archivo',page.locator('#tfm-capacity').inner_text())
            self.assertIn('1.0 GiB libres',page.locator('#tfm-capacity').inner_text())
            self.assertTrue(page.locator('#tfm-browser-list .tf-file button').nth(0).is_disabled())
            self.assertTrue(page.locator('#tfm-browser-list .tf-file button').nth(1).is_disabled())
            self.assertIn('Supera el límite',page.locator('#tfm-browser-list').inner_text())
            self.assertIn('No hay suficiente espacio',page.locator('#tfm-browser-list').inner_text())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/create').length"),0)

    def test_late_directory_and_type_responses_cannot_replace_current_view(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{const prior=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                const result=await prior(args);
                if(args.path==='/v1/files/browse'&&args.body.folder_ref==='projects')await new Promise(resolve=>window.releaseDirectory=resolve);
                if(args.path==='/v1/files/search'&&args.body.kind==='images')await new Promise(resolve=>window.releaseImages=resolve);
                return result;
              };}''')
            page.locator('#tfm-launch').click()
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).click()
            page.wait_for_function('()=>typeof releaseDirectory==="function"')
            page.locator('#tfm-recents').click()
            page.get_by_text('Stand.pdf',exact=True).first.wait_for()
            page.evaluate('releaseDirectory()')
            page.wait_for_function("()=>document.querySelector('#tfm-browser-list').getAttribute('aria-busy')==='false'")
            self.assertEqual(page.locator('#tfm-recents').get_attribute('aria-pressed'),'true')
            self.assertNotIn('Plano.pdf',page.locator('#tfm-browser-list').inner_text())
            page.locator('#tfm-kind').select_option('images')
            page.wait_for_function('()=>typeof releaseImages==="function"')
            page.locator('#tfm-kind').select_option('documents')
            page.get_by_text('Documento.pdf',exact=True).wait_for()
            page.evaluate('releaseImages()')
            page.wait_for_function("()=>document.querySelector('#tfm-browser-list').getAttribute('aria-busy')==='false'")
            self.assertNotIn('Foto.jpg',page.locator('#tfm-browser-list').inner_text())
            self.assertIn('Documento.pdf',page.locator('#tfm-browser-list').inner_text())

    def test_late_response_from_previous_device_is_discarded(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('#tfm-launch').click()
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).wait_for()
            page.evaluate('''()=>{const prior=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                const result=await prior(args);
                if(args.path==='/v1/files/browse'&&args.body.folder_ref==='projects')await new Promise(resolve=>window.releaseOldDevice=resolve);
                return result;
              };}''')
            page.get_by_role('button',name='Abrir carpeta Proyectos',exact=True).click()
            page.wait_for_function('()=>typeof releaseOldDevice==="function"')
            page.evaluate("binding={device_id:'other',fingerprint:'other-cert'};window.dispatchEvent(new CustomEvent('axxSnapshot',{detail:{device_id:'other'}}))")
            page.locator('#tfm-recents').click()
            page.get_by_text('Stand.pdf',exact=True).first.wait_for()
            page.evaluate('releaseOldDevice()')
            self.assertNotIn('Plano.pdf',page.locator('#tfm-browser-list').inner_text())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/search').at(-1).expected_fingerprint"),'other-cert')

    def test_read_permission_explains_pc_setup_without_false_empty_state(self):
        with sync_playwright() as p:
            page=self.open(p,'window.readAllowed=false;')
            page.locator('#tfm-launch').click()
            page.get_by_text('Autoriza las carpetas desde tu PC',exact=True).wait_for()
            self.assertIn('Actividad y permisos',page.locator('#tfm-browser-list').inner_text())
            self.assertTrue(page.locator('#tfm-explore').is_disabled())
            self.assertTrue(page.locator('#tfm-kind').is_disabled())
            self.assertFalse(page.locator('#tfm-send').is_disabled())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/browse').length"),0)

    def test_private_query_does_not_reach_shared_chat_and_requires_selection(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('[data-pane=chat]').click()
            page.locator('#draft').fill('Busca en mi PC el PDF del stand')
            page.locator('#send').click()
            page.locator('#tfm-results .tf-item').nth(1).wait_for()
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/commands').length"),0)
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/create').length"),0)
            self.assertIn('2 coincidencias',page.locator('#tfm-status').inner_text())
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            self.assertFalse(page.evaluate("AxxTransfer.privateQuery('busca restaurantes')!==null"))
            self.assertEqual(page.evaluate("AxxTransfer.privateQuery('Axx, busca en mi PC el último PDF del stand y tráemelo aquí').query"),'pdf del stand')
            self.assertEqual(page.evaluate("AxxTransfer.privateQuery('Axx de mi PC, busca el plano del stand y tráemelo aquí').query"),'plano del stand')
            page.evaluate("AxxTransfer.handleText('el segundo')")
            page.wait_for_function("()=>transfer?.state==='completed'")
            self.assertEqual(page.evaluate("calls.find(c=>c.path==='/v1/transfers/create').body.file_ref"),'two')
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/commands').length"),0)

    def test_receipt_only_after_native_commit_and_original_not_opened(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('holdCommit=true')
            page.locator('#tfm-launch').click()
            page.locator('#tfm-search-toggle').click()
            page.locator('#tfm-query').fill('stand')
            page.locator('#tfm-search').click()
            page.locator('#tfm-results .tf-file button').first.click()
            page.wait_for_function('()=>typeof commitNow==="function"')
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/receipt').length"),0)
            self.assertFalse(page.locator('#tfm-arrival').is_visible())
            page.evaluate('commitNow()')
            page.wait_for_function("()=>transfer.state==='completed'")
            page.locator('#tfm-tab-received').click()
            page.locator('#tfm-received button').wait_for()
            self.assertIn('Guardado y verificado',page.locator('#tfm-received').inner_text())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/receipt').length"),1)
            self.assertEqual(page.evaluate('locals[0].state'),'received')

    def test_upload_is_chunked_and_has_confirmed_pc_receipt(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.locator('#tfm-launch').click()
            page.locator('#tfm-send').click()
            page.wait_for_function("()=>transfer?.state==='completed'")
            page.wait_for_function("()=>!localStorage.getItem('axx.transfer.pending')")
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/chunk').length"),1)
            self.assertIn('Recibido y verificado',page.locator('#tfm-status').inner_text())

    def test_late_chunk_response_cannot_replace_confirmed_cancellation(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{const prior=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async args=>{
                const result=await prior(args);
                if(args.path==='/v1/transfers/chunk'&&args.body.data)await new Promise(resolve=>window.releaseChunk=resolve);
                return result;
              };}''')
            page.locator('#tfm-launch').click();page.locator('#tfm-send').click()
            page.wait_for_function('()=>typeof releaseChunk==="function"')
            page.locator('#tfm-current button').filter(has_text='Cancelar').click()
            page.wait_for_function("()=>transfer.state==='cancelled'")
            page.evaluate('releaseChunk()')
            page.wait_for_function("()=>!localStorage.getItem('axx.transfer.pending')")
            self.assertIn('Cancelado',page.locator('#tfm-status').inner_text())
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/transfers/finish').length"),0)


if __name__=='__main__':unittest.main()
