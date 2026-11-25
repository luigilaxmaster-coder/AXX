"""Real renderer lifecycle when connected Act panels hide, reopen, move, or detach."""
import functools
import http.server
from pathlib import Path
import tempfile
import unittest

from playwright.sync_api import sync_playwright

from backend.tests.test_acts_inference import _Server
from backend.tests.test_acts_ui import ROOT, open_axx, serve


class ActAvatarLifecycleTests(unittest.TestCase):
    def test_hidden_panels_pause_and_resume_the_same_renderer_without_changing_main_avatar(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            srv = _Server(Path(tmp), [])
            web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = open_axx(browser, srv, web)
                        page.evaluate('''() => {
                            window.actRendererInstances = 0; window.actDraws = 0;
                            window.mainAvatarBefore = JSON.stringify(Axx.app.store.data.settings);
                            const Base = Axx.SoftwareRenderer;
                            Axx.SoftwareRenderer = class extends Base {
                                constructor(...args) { super(...args); window.actRendererInstances++; }
                                draw(...args) { window.actDraws++; return super.draw(...args); }
                            };
                            window.actPanel = document.createElement('section');
                            window.actStage = document.createElement('div');
                            actStage.style.cssText = 'position:fixed;left:20px;top:20px;width:160px;height:160px';
                            actPanel.append(actStage); document.body.append(actPanel);
                            Axx.actAvatar.show(actStage, {form_id:17,palette_id:2}, 'working');
                            window.originalActCanvas = actStage.querySelector('canvas');
                        }''')
                        page.wait_for_function('actDraws > 1')
                        for hide, show in [('actPanel.hidden=true', 'actPanel.hidden=false'),
                                           ("actPanel.style.display='none'", "actPanel.style.display=''"),
                                           ("actPanel.style.visibility='hidden'", "actPanel.style.visibility='' ")]:
                            page.evaluate(hide)
                            page.wait_for_timeout(150)
                            count = page.evaluate('actDraws')
                            page.wait_for_timeout(200)
                            self.assertEqual(page.evaluate('actDraws'), count, hide)
                            page.evaluate(show)
                            page.wait_for_function('(n)=>actDraws>n', arg=count)
                            self.assertTrue(page.evaluate('actStage.querySelector("canvas")===originalActCanvas'))
                        page.evaluate('''() => {
                            window.secondActStage = document.createElement('div');
                            secondActStage.style.cssText = 'position:fixed;left:200px;top:20px;width:128px;height:128px';
                            document.body.append(secondActStage);
                            Axx.actAvatar.show(secondActStage,{form_id:5,palette_id:1},'planning');
                        }''')
                        self.assertEqual(page.evaluate('actRendererInstances'), 1)
                        self.assertEqual(page.locator('canvas.axx-act-live').count(), 1)
                        self.assertTrue(page.evaluate('secondActStage.querySelector("canvas")===originalActCanvas'))
                        page.evaluate('secondActStage.remove()')
                        page.wait_for_function('Axx.actAvatar.liveHost===null')
                        count = page.evaluate('actDraws')
                        page.wait_for_timeout(200)
                        self.assertEqual(page.evaluate('actDraws'), count)
                        page.evaluate("Axx.actAvatar.show(actStage,{form_id:17,palette_id:2},'working')")
                        page.wait_for_function('(n)=>actDraws>n', arg=count)
                        self.assertEqual(page.evaluate('actRendererInstances'), 1)
                        self.assertEqual(page.evaluate('JSON.stringify(Axx.app.store.data.settings)'), page.evaluate('mainAvatarBefore'))
                    finally:
                        browser.close()
            finally:
                srv.close(); web.shutdown(); web.server_close()
