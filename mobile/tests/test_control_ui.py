"""Isolated UI contracts; not a substitute for physical Android acceptance."""
import unittest
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT,NATIVE_FIXTURE

CONTROL_FIXTURE='''
window.inputPackets=[];window.inputActive=false;window.failInput=false;window.inputLease=0;window.controlCalls=[];window.failRenew=0;window.inputButtons=new Set();window.inputKeys=new Set();
const old=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async({path,body})=>{
 if(!path.startsWith('/v1/control/'))return old({path,body});
 controlCalls.push({path,body});
 if(path.endsWith('/acquire')){inputActive=true;inputLease++;}
 if(path.endsWith('/renew')&&failRenew>0){failRenew--;throw Error('temporary network timeout');}
 if(path.endsWith('/release')){inputActive=false;inputButtons.clear();inputKeys.clear();}
 if(path.endsWith('/events')){inputPackets.push(body);for(const e of body.events){const held=e.type==='button'?inputButtons:e.type==='key'?inputKeys:null;if(held)held[e.down?'add':'delete'](e.button||e.key);}if(failInput)throw Error('lost acknowledgement');}
 return {data:{boot_id:'boot',ttl_ms:3000,lease:{lease_id:'lease-'+inputLease,state:inputActive?'granted':'released',last_seq:0},native:{active:inputActive,reason:'released',cursor:{x:10,y:20},keys:[...inputKeys],buttons:[...inputButtons],monitors:[]}}};
};
'''

class RemoteControlUI(unittest.TestCase):
 def open(self,p):
  browser=p.chromium.launch()
  page=browser.new_page(viewport={'width':339,'height':673},reduced_motion='reduce')
  page.route('https://axx.test/**',lambda route:route.fulfill(path=str(ROOT/(route.request.url.split('https://axx.test/',1)[1] or 'index.html'))))
  page.add_init_script(NATIVE_FIXTURE+CONTROL_FIXTURE);page.goto('https://axx.test/')
  page.locator('[data-pane=pc]').click();page.locator('#control-open-pad').click();page.locator('#control-acquire').click();page.locator('#control-stop').wait_for()
  return page

 def test_one_failed_renewal_recovers_same_lease_without_replaying_input(self):
  with sync_playwright() as p:
   page=self.open(p)
   page.evaluate('''()=>{failRenew=1;const old=Capacitor.Plugins.AxxTransport.request;let gated=false;window.waitRecovery=false;Capacitor.Plugins.AxxTransport.request=async o=>{if(o.path.endsWith('/renew')&&failRenew===0&&!gated){gated=true;waitRecovery=true;await new Promise(resolve=>window.finishRecovery=resolve);}return old(o);};}''')
   page.wait_for_function('()=>waitRecovery')
   self.assertTrue(page.locator('#control-left').is_disabled())
   page.locator('#control-pad').dispatch_event('pointerdown',{'pointerId':11,'clientX':100,'clientY':200})
   self.assertEqual(page.evaluate('inputPackets.length'),0)
   page.evaluate('finishRecovery()')
   page.wait_for_function("()=>document.querySelector('#control-status').textContent.includes('restablecido')")
   self.assertFalse(page.locator('#control-left').is_disabled())
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/acquire')).length"),1)
   self.assertEqual(page.evaluate('inputLease'),1)
   page.locator('#control-left').click();page.wait_for_function('()=>inputPackets.length===1')
   self.assertEqual(page.evaluate('inputPackets[0].seq'),1)

 def test_repeated_renewal_failure_stops_and_requires_explicit_reconnection(self):
  with sync_playwright() as p:
   page=self.open(p);page.evaluate('failRenew=2')
   page.wait_for_function('()=>!inputActive')
   self.assertTrue(page.locator('#control-stop').is_hidden())
   self.assertEqual(page.locator('#control-acquire').inner_text(),'Reconectar')
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/acquire')).length"),1)
   page.locator('#control-acquire').click();page.locator('#control-stop').wait_for()
   self.assertEqual(page.evaluate('inputLease'),2)
   self.assertEqual(page.evaluate('inputPackets.length'),0)

 def test_renewal_failure_with_drag_releases_instead_of_recovering_held_input(self):
  with sync_playwright() as p:
   page=self.open(p);page.locator('#control-drag').click();page.wait_for_function('()=>inputPackets.length===1')
   page.evaluate('failRenew=1;controlCalls=[]')
   page.wait_for_function('()=>!inputActive')
   self.assertEqual(page.locator('#control-drag').get_attribute('aria-pressed'),'false')
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/renew')).length"),1)
   self.assertEqual(page.evaluate('inputPackets.length'),1)

 def test_old_inflight_event_does_not_block_a_new_explicit_session(self):
  with sync_playwright() as p:
   page=self.open(p)
   page.evaluate('''()=>{const old=Capacitor.Plugins.AxxTransport.request;let delayed=false;Capacitor.Plugins.AxxTransport.request=async o=>{const response=await old(o);if(o.path.endsWith('/events')&&!delayed){delayed=true;await new Promise(resolve=>window.finishOldInput=resolve);}return response;};}''')
   page.locator('#control-left').click();page.wait_for_function('()=>!!window.finishOldInput')
   page.locator('#control-stop').click();page.locator('#control-acquire').click();page.locator('#control-stop').wait_for()
   page.locator('#control-right').click();page.evaluate('finishOldInput()')
   page.wait_for_function('()=>inputPackets.length===2')
   self.assertEqual(page.evaluate('inputPackets.map(p=>[p.lease_id,p.seq])'),[['lease-1',1],['lease-2',1]])
   self.assertEqual(page.evaluate('inputPackets[1].events[0].button'),'right')

 def test_unconfirmed_down_and_queued_up_cancel_instead_of_renewing(self):
  with sync_playwright() as p:
   page=self.open(p)
   page.evaluate('''()=>{const old=Capacitor.Plugins.AxxTransport.request;Capacitor.Plugins.AxxTransport.request=async o=>{const response=await old(o);if(o.path.endsWith('/events'))await new Promise(resolve=>window.finishDownAck=resolve);return response;};}''')
   page.locator('#control-drag').click();page.wait_for_function('()=>!!window.finishDownAck')
   page.locator('#control-drag').click();page.evaluate('failRenew=1;controlCalls=[]')
   page.wait_for_function('()=>!inputActive',timeout=5000)
   self.assertFalse(page.evaluate('inputActive'),'A lease must not renew with an unconfirmed down and an unsent up')
   self.assertEqual(page.evaluate('[...inputButtons]'),[])
   self.assertEqual(page.evaluate('inputPackets.length'),1)
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/renew')).length"),1)
   page.evaluate('finishDownAck()');page.wait_for_timeout(100)
   self.assertFalse(page.evaluate('inputActive'))
   self.assertEqual(page.evaluate('inputPackets.length'),1)
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/acquire')).length"),0)

 def test_changed_identity_during_recovery_never_reacquires_or_replays(self):
  with sync_playwright() as p:
   for identity in ['boot','lease']:
    with self.subTest(identity=identity):
     page=self.open(p)
     page.evaluate('''identity=>{failRenew=1;const old=Capacitor.Plugins.AxxTransport.request;Capacitor.Plugins.AxxTransport.request=async o=>{const response=await old(o);if(o.path.endsWith('/renew')){if(identity==='boot')response.data.boot_id='different-boot';else response.data.lease.lease_id='different-lease';}return response;};}''',identity)
     page.wait_for_function("()=>document.querySelector('#control-status').textContent.includes('Reconectar')")
     self.assertTrue(page.locator('#control-stop').is_hidden())
     self.assertEqual(page.locator('#control-surface').get_attribute('data-connected'),'false')
     self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/acquire')).length"),1)
     self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/release')).length"),0)
     self.assertEqual(page.evaluate('inputPackets.length'),0)

 def test_native_held_or_missing_state_prevents_recovery(self):
  with sync_playwright() as p:
   for stage in ['before','recovery']:
    for held in ['button','key','missing']:
     with self.subTest(stage=stage,held=held):
      page=self.open(p)
      page.evaluate('''kind=>{const old=Capacitor.Plugins.AxxTransport.request;window.sawHeldState=false;Capacitor.Plugins.AxxTransport.request=async o=>{const response=await old(o);if(o.path.endsWith('/renew')){if(kind==='button')response.data.native.buttons=['left'];else if(kind==='key')response.data.native.keys=['Control'];else{delete response.data.native.keys;delete response.data.native.buttons;}sawHeldState=true;}return response;};}''',held)
      if stage=='before':page.wait_for_function('()=>sawHeldState')
      page.evaluate('failRenew=1;controlCalls=[]')
      page.wait_for_function('()=>!inputActive',timeout=5000)
      self.assertFalse(page.evaluate('inputActive'))
      self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/renew')).length"),1 if stage=='before' else 2)

 def test_lost_capture_and_background_release_input_without_reacquiring(self):
  with sync_playwright() as p:
   page=self.open(p);box=page.locator('#control-pad').bounding_box()
   page.mouse.move(box['x']+30,box['y']+70);page.mouse.down()
   page.wait_for_function("()=>document.querySelector('#control-drag').getAttribute('aria-pressed')==='true'")
   page.locator('#control-pad').dispatch_event('lostpointercapture',{'pointerId':1})
   page.wait_for_function('()=>inputPackets.length===2');page.mouse.up()
   self.assertEqual(page.evaluate('inputPackets.map(p=>p.events[0].down)'),[True,False])
   page.locator('[data-control-mode=keyboard]').click();page.locator('[data-key=Control]').click()
   page.wait_for_function('()=>inputPackets.length===3')
   page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
   page.wait_for_function('()=>!inputActive')
   self.assertEqual(page.locator('[data-key=Control]').get_attribute('aria-pressed'),'false')
   page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))")
   page.wait_for_timeout(900)
   self.assertEqual(page.evaluate("controlCalls.filter(c=>c.path.endsWith('/acquire')).length"),1)
   self.assertTrue(page.locator('#control-stop').is_hidden())

 def test_large_text_keeps_pad_and_keys_large(self):
  with sync_playwright() as p:
   browser=p.chromium.launch();page=browser.new_page(viewport={'width':339,'height':673})
   def serve(route):
    name=route.request.url.split('https://axx.test/',1)[1] or 'index.html';path=ROOT/name
    if name=='css/live-client.css':route.fulfill(body=path.read_text(encoding='utf-8')+'\nhtml,body{font-size:23.8px}',content_type='text/css')
    else:route.fulfill(path=str(path))
   page.route('https://axx.test/**',serve);page.add_init_script(NATIVE_FIXTURE+CONTROL_FIXTURE);page.goto('https://axx.test/')
   out=Path(self.enterContext(tempfile.TemporaryDirectory(prefix='axx-mobile-ui-')))
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
