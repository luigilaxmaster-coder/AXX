"""Browser contracts for real-state UI; native storage/transport are explicit fixtures."""
import unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE

FIXTURE = NATIVE_FIXTURE + r'''
window.calls=[];window.locals=[];window.transfer=null;window.holdCommit=false;
const hash='a'.repeat(64);
Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,device_id:'phone',endpoint:'https://192.168.0.10:4443',fingerprint:'test',scopes:['query','files.read','files.write']});
const prior=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async args=>{
 calls.push(args);
 if((args.path.startsWith('/v1/files/')||args.path.startsWith('/v1/transfers')) && (args.expected_device_id!=='phone'||args.expected_fingerprint!=='test'))throw Error('Unbound file request');
 const body=args.body||{};
 if(args.path==='/v1/files/status')return {data:{permissions:{read:true,write:true},transfers:transfer?[transfer]:[]}};
 if(args.path==='/v1/files/search')return {data:{files:[{file_ref:'one',name:'Stand.pdf',size:4,relative_path:'Stand.pdf',modified_at:1700000000},{file_ref:'two',name:'Stand anterior.pdf',size:4,relative_path:'Stand anterior.pdf',modified_at:1700000000}]}};
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
    def open(self, p):
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':339,'height':673},reduced_motion='reduce')
        page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
        page.add_init_script(FIXTURE)
        page.goto('https://axx.test/')
        page.locator('#sync-status[data-state=complete]').wait_for()
        return page

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
            page.locator('#tfm-query').fill('stand')
            page.locator('#tfm-search').click()
            page.locator('#tfm-results button').first.click()
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
