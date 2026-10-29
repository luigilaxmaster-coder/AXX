"""Local dictation controller; explicit native fixture, no hardware claim."""
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


SCRIPT = (Path(__file__).parents[1] / 'js' / 'file-dictation.js').read_text(encoding='utf-8')
FIXTURE = '''
window.calls=[]; window.discarded=false;
window.crypto.randomUUID=()=> '00000000-0000-4000-8000-000000000001';
window.Capacitor={Plugins:{
  AxxTransport:{profile:async()=>({paired:true,device_id:'phone-a',fingerprint:'a'.repeat(64)}),request:async args=>{calls.push(args);return {data:args.path.includes('?')?{state:'completed',text:'Tráeme el PDF de mi PC'}:{state:'transcribing'}};}},
  AxxVoice:{status:async()=>({state:'idle'}),permit:async()=>({permission:'granted'}),
    start:async()=>({state:'recording'}),heartbeat:async()=>{},stop:async()=>({state:'stopped'}),
    audio:async()=>({mime:'audio/mp4',audio_base64:'fixture'}),discard:async()=>{discarded=true;},addListener:async()=>{}}
}};
'''


class FileDictationTests(unittest.TestCase):
    def test_local_dictation_creates_reviewable_draft_without_command_dispatch(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content('<form id="chat-form"><textarea id="draft">Hola.</textarea></form>')
            page.evaluate(FIXTURE)
            page.evaluate(SCRIPT)
            page.locator('#file-dictation').click()
            self.assertEqual(page.locator('#file-dictation').inner_text(), 'Terminar dictado')
            page.locator('#file-dictation').click()
            page.wait_for_function('discarded')
            self.assertEqual(page.locator('#draft').input_value(), 'Hola. Tráeme el PDF de mi PC')
            self.assertFalse(page.evaluate('axxFileDictationActive'))
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/commands').length"), 0)
            self.assertEqual(page.evaluate("calls.filter(c=>c.path==='/v1/files/dictation').length"), 1)
            self.assertTrue(page.evaluate("calls.every(c=>c.expected_device_id==='phone-a' && c.expected_fingerprint==='a'.repeat(64))"))
            browser.close()

    def test_missing_native_voice_does_not_add_a_nonworking_button(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content('<form id="chat-form"><textarea id="draft"></textarea></form>')
            page.evaluate(SCRIPT)
            self.assertEqual(page.locator('#file-dictation').count(), 0)
            browser.close()
