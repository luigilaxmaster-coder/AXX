"""Easter egg «Modo ritmo» in the real Axx.html: the Konami code, the avatar's music deformation and a clean exit.

Browser receipt (Chromium). Windows' output meter is a fixture here (a 120 BPM kick as system_media_status peaks);
the beat tracker, the key trigger and the renderer wiring are the real code. Not installed-app or audio-hardware proof.
"""
import functools
import http.server
from pathlib import Path
import tempfile
import unittest

from playwright.sync_api import sync_playwright

from backend.tests.test_acts_inference import _Server
from backend.tests.test_acts_ui import FAKE_TAURI, ROOT, serve

METER_120 = """(()=>{const invoke=window.__TAURI__.core.invoke;window.__TAURI__.core.invoke=async(name,args)=>{
  if(name!=='system_media_status')return invoke(name,args);
  const t=Math.floor(Date.now()/50)*50,k=t%500;  // Windows refreshes the meter every 50 ms
  return {available:true,audioAvailable:true,peak:Math.min(1,.12+(k<50?.75:k<100?.3:0)),sessions:[{id:'m1',app:'Player',title:'<Groove> Test',playing:true}],updatedAt:t};};})();"""
KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']


class RhythmEggUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.srv = _Server(Path(self.tmp.name), [])
        self.web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))

    def tearDown(self):
        self.web.shutdown(); self.web.server_close(); self.srv.close(); self.tmp.cleanup()

    def open(self, browser):
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})

        def request(method, path, body=None):
            code, data = self.srv.api.request(method, path, body)
            if code >= 400:
                raise RuntimeError(data.get('error', {}).get('message', 'HTTP ' + str(code)))
            return data
        page.expose_function('testBackend', request)
        page.add_init_script(FAKE_TAURI + METER_120)
        page.goto(f'http://127.0.0.1:{self.web.server_port}/Axx.html')
        page.wait_for_function('window.Axx?.app?.renderer && window.Axx?.rhythmEgg')
        return page

    def test_konami_code_makes_axx_move_on_the_beat_and_escape_restores_it(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = self.open(browser)
                # typing the code into a text field is just typing
                page.evaluate("Axx.companion.openFeature('chat')")
                page.locator('#chat-input').focus()
                self.assertEqual(page.evaluate('document.activeElement.id'), 'chat-input')
                for key in KONAMI:
                    page.keyboard.press(key)
                self.assertFalse(page.evaluate('Axx.rhythmEgg.active'))
                page.evaluate('document.activeElement.blur()')
                for key in KONAMI:
                    page.keyboard.press(key)
                self.assertTrue(page.evaluate('Axx.rhythmEgg.active'))
                page.wait_for_function("document.querySelector('.axx-groove b')?.textContent.endsWith('BPM')", timeout=20000)
                bpm = int(page.locator('.axx-groove b').text_content().split()[0])
                self.assertLessEqual(abs(bpm - 120), 2)
                # the avatar's own music deformation receives the beat pulse
                page.wait_for_function('Axx.app.renderer.musicSignal?.pulse > .8', timeout=5000)
                page.wait_for_function('Axx.app.renderer.musicSignal?.pulse < .2', timeout=5000)
                self.assertEqual(page.evaluate('Axx.app.renderer.musicAmount'), .95)
                self.assertEqual(page.locator('.axx-groove-track').text_content(), '<Groove> Test')
                page.get_by_role('button', name='Intensidad del ritmo', exact=True).click()
                self.assertEqual(page.evaluate('Axx.app.renderer.musicAmount'), 1.35)
                page.screenshot(path=str(ROOT / 'build' / 'rhythm-egg.png'))
                page.keyboard.press('Escape')
                self.assertEqual(page.evaluate("""[Axx.rhythmEgg.active, Object.hasOwn(Axx.app.renderer,'setMusicSignal'),
                    Axx.app.renderer.musicSignal, document.querySelector('.axx-groove')]"""), [False, False, None, None])
                # reduced motion: the egg explains why AXX stays still instead of starting
                page.evaluate('Axx.app.store.data.settings.reducedMotion = true')
                for key in KONAMI:
                    page.keyboard.press(key)
                self.assertFalse(page.evaluate('Axx.rhythmEgg.active'))
                self.assertIn('Movimiento reducido', page.locator('#toast').text_content())
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
