"""Browser contract for the foreground phone microphone shortcut (native calls are fixtures)."""
from pathlib import Path
import re
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[1]
HTML = (ROOT / 'client.html').read_text(encoding='utf-8')
HTML = re.sub(r'<script[^>]*></script>|<link[^>]*>|<meta http-equiv="Content-Security-Policy"[^>]*>', '', HTML)
SCRIPT = (ROOT / 'js' / 'remote-voice.js').read_text(encoding='utf-8')
FIXTURE = '''
window.actions=[];window.paired=true;window.allowed=true;window.native={state:'idle',session_id:'',visible:true,permission:'prompt'};
window.server=null;
window.Capacitor={Plugins:{
  AxxTransport:{profile:async()=>({paired:window.paired}),request:async ({path,body})=>{
    if(path==='/v1/voice/poll'){
      if(window.server?.state==='requested' && body.capture.state==='recording')window.server.state='recording';
      return {data:{session:window.server}};
    }
    if(path==='/v1/voice/action'){
      window.actions.push(body);
      if(body.action==='start')window.server={session_id:'phone-session',state:'requested',max_seconds:body.max_seconds,mode:body.mode};
      if(body.action==='stop')window.server.state='stopping';
      return {data:window.server};
    }
    return {data:window.server};
  }},
  AxxVoice:{status:async()=>({...window.native}),permit:async()=>{if(window.allowed)window.native.permission='granted';return {...window.native};},
    start:async ({session_id})=>{window.native.state='recording';window.native.session_id=session_id;return {...window.native};},
    stop:async()=>{window.native.state='stopped';return {...window.native};},
    heartbeat:async()=>{},audio:async()=>({session_id:'phone-session',mime:'audio/mp4',audio_base64:'fixture'}),
    discard:async()=>{window.native.state='idle';window.native.session_id='';},addListener:async()=>{}}
}};
'''


class PhoneVoiceShortcutTests(unittest.TestCase):
    def setUp(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.page = self.browser.new_page()
        self.page.route('https://axx.test/', lambda route: route.fulfill(body=HTML, content_type='text/html'))
        self.page.goto('https://axx.test/')
        self.page.evaluate(FIXTURE)
        self.page.evaluate(SCRIPT)

    def tearDown(self):
        self.browser.close()
        self.playwright.stop()

    def test_two_taps_start_and_stop_same_session(self):
        quick = self.page.locator('#voice-quick')
        quick.click()
        self.assertEqual(self.page.evaluate('actions.length'), 0)
        quick.click()
        self.page.wait_for_function("actions.length===1 && native.state==='recording'")
        self.assertEqual(self.page.evaluate('actions[0]'), {'action': 'start', 'mode': 'confirm', 'max_seconds': 30})
        quick.click()
        quick.click()
        self.page.wait_for_function("actions.length===2 && native.state==='stopped'")
        self.assertEqual(self.page.evaluate('actions[1]'), {'action': 'stop', 'session_id': 'phone-session'})

    def test_denied_microphone_never_starts(self):
        self.page.evaluate('allowed=false')
        self.page.locator('#voice-quick').click()
        self.page.locator('#voice-quick').click()
        self.page.wait_for_function("document.querySelector('#voice-status').textContent.includes('Concede el permiso')")
        self.assertEqual(self.page.evaluate('actions.length'), 0)

    def test_configured_keyboard_shortcut_ignores_text_fields(self):
        self.page.evaluate("document.querySelector('#character-dialog').showModal();document.querySelector('#voice-details').open=true")
        self.page.locator('#voice-key').select_option('alt-v')
        self.page.evaluate("document.querySelector('#character-dialog').close()")
        self.page.evaluate("document.querySelector('#pane-chat').hidden=false")
        self.page.locator('#draft').focus()
        self.page.keyboard.press('Alt+v')
        self.assertEqual(self.page.evaluate('actions.length'), 0)
        self.page.locator('#voice-quick').focus()
        self.page.keyboard.press('Alt+v')
        self.page.wait_for_function('actions.length===1')
        self.assertEqual(self.page.evaluate('actions[0].action'), 'start')
