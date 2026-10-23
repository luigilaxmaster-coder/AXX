import os
"""Pairing UI contracts in an isolated browser, not optical camera acceptance."""
import unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT, NATIVE_FIXTURE

LINK='axx://pair?endpoint=https%3A%2F%2F192.168.0.10%3A4443&fingerprint='+'a'*64+'&code='+'b'*32

class PairingUI(unittest.TestCase):
    def test_scan_denied_retry_confirm_and_external_link(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('AXX_TEST_CHROMIUM'))
            page=browser.new_page(viewport={'width':339,'height':673})
            page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
            page.add_init_script(NATIVE_FIXTURE+'''window.pairCalls=0;window.scanCalls=0;
Capacitor.Plugins.AxxTransport.scan=async()=>{scanCalls++;throw Error('Camera access is required');};
Capacitor.Plugins.AxxTransport.pair=async()=>{pairCalls++;if(pairCalls===1)throw Error('This QR expired. Generate a new QR.');};''')
            page.goto('https://axx.test/')
            self.assertEqual(page.locator('html').get_attribute('lang'),'en')
            page.locator('#pc-button').click();page.locator('#scan-qr').click()
            self.assertIn('Camera access',page.locator('#pair-error').inner_text())
            self.assertTrue(page.locator('#scan-qr').is_enabled())
            page.evaluate('(uri)=>Capacitor.Plugins.AxxTransport.scan=async()=>({uri})',LINK)
            page.locator('#scan-qr').click()
            self.assertEqual(page.evaluate('pairCalls'),0)
            self.assertIn('192.168.0.10:4443',page.locator('#pair-preview').inner_text())
            page.locator('#pair-submit').click()
            self.assertIn('expired',page.locator('#pair-error').inner_text())
            self.assertTrue(page.locator('#pair-dialog').is_visible())
            page.locator('#pair-close').click()
            page.evaluate('(uri)=>{Capacitor.Plugins.AxxTransport.pairingLink=async()=>({uri});dispatchEvent(new Event("axxPairingLink"));}',LINK)
            page.locator('#pair-dialog').wait_for()
            self.assertEqual(page.evaluate('pairCalls'),1)
            page.evaluate("Capacitor.Plugins.AxxTransport.profile=async()=>({paired:true,endpoint:'https://192.168.0.10:4443',fingerprint:'test',scopes:['query']})")
            page.locator('#pair-submit').click()
            page.locator('#sync-status[data-state=complete]').wait_for()
            self.assertEqual(page.evaluate('pairCalls'),2)
            self.assertFalse(page.locator('#pair-dialog').is_visible())
            browser.close()
