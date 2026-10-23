import os,unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT,NATIVE_FIXTURE

class PhoneVoiceUI(unittest.TestCase):
 def test_phone_can_start_review_and_confirm_voice(self):
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('AXX_TEST_CHROMIUM'));page=browser.new_page(viewport={'width':360,'height':740});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
   page.add_init_script(NATIVE_FIXTURE+'''
   window.voiceSession=null;window.confirmed=null;window.language=null;
   const base=Capacitor.Plugins.AxxTransport.request;
   Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,scopes:['query','voice','tools.control']});
   Capacitor.Plugins.AxxTransport.request=async(args)=>{
    if(!args.path.startsWith('/v1/voice/'))return base(args);
    if(args.path.endsWith('/start')){language=args.body.language;voiceSession={session_id:'session',state:'review',text:'abre calculadora'};return {data:voiceSession};}
    if(args.path.endsWith('/confirm')){confirmed=args.body;voiceSession={...voiceSession,state:'ready'};return {data:voiceSession};}
    return {data:{session:voiceSession}};
   };
   const snap=()=>({permission:'granted',state:'idle',session_id:'',reason:'',visible:true});
   Capacitor.Plugins.AxxVoice={status:async()=>snap(),permit:async()=>snap(),heartbeat:async()=>{},addListener:async()=>{}};
   ''')
   page.goto('https://axx.test/')
   self.assertEqual(page.locator('#voice-panel').count(),1);self.assertEqual(page.locator('#voice-permit').count(),1)
   page.locator('[data-pane=pc]').click();page.locator('#phone-voice-start').click()
   page.locator('#phone-voice-review').wait_for(state='visible')
   self.assertEqual(page.locator('#phone-voice-text').input_value(),'abre calculadora')
   page.locator('#phone-voice-text').fill('abre bloc de notas');page.locator('#phone-voice-confirm').click()
   page.wait_for_function('confirmed!==null')
   self.assertEqual(page.evaluate('confirmed.text'),'abre bloc de notas');self.assertEqual(page.evaluate('language'),'es')
   self.assertEqual(errors,[]);browser.close()
