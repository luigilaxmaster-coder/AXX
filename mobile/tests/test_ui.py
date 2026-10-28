"""Browser contract tests with a fake native transport; not Android acceptance."""
import base64
import struct
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / 'www'
LINK='axx://pair?endpoint=https%3A%2F%2F192.168.0.10%3A4443&fingerprint='+'a'*64+'&code='+'b'*32
NATIVE_FIXTURE = '''window.Capacitor={Plugins:{AxxTransport:{
 profile:async()=>({paired:false}),
 pair:async()=>{},
 request:async({path})=>({data:path==='/v1/status'?{ready:true}:
 path==='/v1/snapshot'?{conversation_id:'test-conversation',messages:[],appearance:window.testAppearance||{settings:{form:19,palette:1,scale:1},studio:{living:true},camera:[0,0],finish:'prism',activity:{state:'thinking',moving:true}}}:
 path==='/v1/appearance'?{appearance:window.testAppearance||null}:path==='/v1/tasks'?{operations:[]}:{tools:[]}}),
 updateHomeIcon:async({png})=>{(window.testHomeIcons??=[]).push(png);document.body.dataset.iconUpdates=String(testHomeIcons.length);},
 shortcut:async({png})=>{window.testIcon=png;return {requested:false};}
 }}};'''


class MobileUI(unittest.TestCase):
    def test_pair_state_scroll_interaction_and_transparent_shortcut(self):
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':360,'height':640},reduced_motion='reduce')
            def serve(route):
                relative=route.request.url.split('https://axx.test/',1)[1] or 'index.html'
                path=(ROOT/relative).resolve()
                if not path.is_relative_to(ROOT) or not path.is_file():
                    route.abort();return
                route.fulfill(path=str(path))
            page.route('https://axx.test/**',serve)
            page.add_init_script(NATIVE_FIXTURE)
            page.goto('https://axx.test/')
            page.locator('#pc-button').click()
            page.locator('#pair-manual summary').click()
            page.locator('#pair-uri').fill(LINK)
            # Profile becomes paired only after confirmation in this isolated fixture.
            page.evaluate("Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,endpoint:'https://192.168.1.2:443',fingerprint:'test',scopes:['query']})")
            page.locator('#pair-submit').click()
            page.locator('#sync-status[data-state=complete]').wait_for()
            self.assertEqual(page.evaluate('axxMobileRenderer.form'),19)
            self.assertEqual(page.evaluate('axxMobileRenderer.finish'),'prism')
            self.assertTrue(page.evaluate('axxMobileRenderer.settings.reducedMotion'))
            self.assertEqual(page.evaluate('axxMobileRenderer.settings.quality'),'balanced')
            self.assertTrue(page.evaluate('document.documentElement.scrollHeight<=innerHeight'))
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            page.locator('body[data-icon-updates="1"]').wait_for()
            page.evaluate("window.testAppearance={settings:{form:3,palette:2,scale:1},studio:{living:true},camera:[0,0],finish:'prism',activity:{state:'idle',moving:false}}")
            page.locator('#refresh').click()
            page.locator('body[data-icon-updates="2"]').wait_for()
            self.assertEqual(page.evaluate('axxMobileRenderer.form'),3)
            self.assertNotEqual(*page.evaluate('testHomeIcons.slice(0,2)'))
            page.evaluate('testAppearance.camera=[1,0];testAppearance.activity.state="thinking"')
            page.locator('#refresh').click()
            self.assertEqual(page.evaluate('testHomeIcons.length'),2)
            page.locator('#character-options').click()
            page.locator('.avatar-controls summary').click()
            page.locator('#avatar-interact').click()
            self.assertEqual(page.locator('#avatar-interact').get_attribute('aria-pressed'),'true')
            page.locator('#axx-avatar-canvas').press('Enter')
            self.assertIn('toque',page.locator('#avatar-state').inner_text())
            page.locator('[data-pane=pc]').click()
            page.locator('#pin-shortcut').click()
            png=base64.b64decode(page.evaluate('testIcon').split(',')[1])
            self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
            width,height=struct.unpack('>II',png[16:24])
            self.assertGreaterEqual(width,256);self.assertGreaterEqual(height,256)
            from PIL import Image
            import io
            alpha=Image.open(io.BytesIO(png)).getchannel('A')
            self.assertEqual(alpha.getextrema(),(0,255))
            browser.close()


if __name__ == '__main__':unittest.main()
