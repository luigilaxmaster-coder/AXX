"""Isolated UI contracts; not a substitute for physical Android acceptance."""
import unittest
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT,NATIVE_FIXTURE

CONTROL_FIXTURE='''
window.inputPackets=[];window.inputActive=false;window.failInput=false;
const old=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async({path,body})=>{
 if(!path.startsWith('/v1/control/'))return old({path,body});
 if(path.endsWith('/acquire'))inputActive=true;
 if(path.endsWith('/release'))inputActive=false;
 if(path.endsWith('/events')){inputPackets.push(body);if(failInput)throw Error('lost acknowledgement');}
 return {data:{boot_id:'boot',ttl_ms:3000,lease:{lease_id:'lease',state:inputActive?'granted':'released',last_seq:0},native:{active:inputActive,reason:'released',cursor:{x:10,y:20},keys:[],buttons:[],monitors:[]}}};
};
'''

class RemoteControlUI(unittest.TestCase):
 def test_large_text_keeps_pad_and_keys_large(self):
  with sync_playwright() as p:
   browser=p.chromium.launch();page=browser.new_page(viewport={'width':339,'height':673})
   def serve(route):
    name=route.request.url.split('https://axx.test/',1)[1] or 'index.html';path=ROOT/name
    if name=='css/live-client.css':route.fulfill(body=path.read_text(encoding='utf-8')+'\nhtml,body{font-size:23.8px}',content_type='text/css')
    else:route.fulfill(path=str(path))
   page.route('https://axx.test/**',serve);page.add_init_script(NATIVE_FIXTURE+CONTROL_FIXTURE);page.goto('https://axx.test/')
   out=ROOT.parent.parent/'evidence/mobile-20261022/pairing-fix';out.mkdir(parents=True,exist_ok=True)
   page.locator('#pc-button').click();page.screenshot(path=str(out/'pairing-preview.png'));page.locator('#pair-close').click()
   page.locator('[data-pane=pc]').click();page.locator('#control-open-pad').click()
   page.screenshot(path=str(out/'trackpad-preview.png'));pad=page.locator('#control-pad').bounding_box()
   self.assertGreater(pad['height'],380)
   self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
   page.locator('#control-settings').click();self.assertEqual(page.locator('#control-pad').bounding_box(),pad)
   page.locator('#control-settings').click();page.locator('[data-control-mode=keyboard]').click()
   page.screenshot(path=str(out/'keyboard-preview.png'))
   self.assertGreaterEqual(min(page.locator('[data-key]').evaluate_all('(nodes)=>nodes.map(n=>n.getBoundingClientRect().height)')),60)
   browser.close()

 def test_input_order_stop_and_no_retry_on_lost_ack(self):
  with sync_playwright() as p:
   browser=p.chromium.launch();page=browser.new_page(viewport={'width':360,'height':740})
   page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
   page.add_init_script(NATIVE_FIXTURE+CONTROL_FIXTURE);page.goto('https://axx.test/')
   page.locator('[data-pane=pc]').click();page.locator('#control-open-pad').click();page.locator('#control-acquire').click();page.locator('#control-stop').wait_for()
   page.locator('#control-left').click();page.wait_for_function('inputPackets.length===1')
   self.assertEqual(page.evaluate('inputPackets[0].events'),[{'type':'button','button':'left','down':True},{'type':'button','button':'left','down':False}])
   page.locator('[data-control-mode=keyboard]').click();page.locator('[data-key=Control]').click();page.wait_for_function('inputPackets.length===2')
   page.locator('#control-stop').click();self.assertTrue(page.locator('#control-stop').is_hidden())
   self.assertEqual(page.locator('[data-key=Control]').get_attribute('aria-pressed'),'false')
   page.locator('#control-acquire').click();page.locator('#control-stop').wait_for();page.evaluate('failInput=true')
   page.locator('[data-control-mode=pad]').click();page.locator('#control-right').click();page.wait_for_function('inputPackets.length===3 && !inputActive')
   self.assertTrue(page.locator('#control-stop').is_hidden());self.assertEqual(page.evaluate('inputPackets.length'),3)
   self.assertIn('No se repetirá',page.locator('#control-status').inner_text())
   browser.close()
