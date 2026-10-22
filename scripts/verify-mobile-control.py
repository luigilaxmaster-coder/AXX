"""Exercise the installed Axx and physical Android through their real transport.
Touch events are driven by CDP on the phone; no fake transport or input backend.
"""
import ctypes as C
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
from playwright.sync_api import sync_playwright
from PIL import ImageGrab
from backend.screen_recording import ScreenRecordingService

OUT=Path(__file__).resolve().parents[1]/'evidence/mobile-20261022/remote-control'
ADB=str(Path(os.environ['ANDROID_HOME'])/'platform-tools/adb.exe')
u=C.WinDLL('user32');u.FindWindowW.restype=C.c_void_p;u.GetForegroundWindow.restype=C.c_void_p
u.ShowWindow.argtypes=[C.c_void_p,C.c_int];u.SetWindowPos.argtypes=[C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint]
target=u.FindWindowW(None,'Axx · verificación de entrada remota');assert target,'Open remote-control-target.py first'
report={'input_source':'CDP touch/click on Samsung; real native TLS transport and installed Windows SendInput','checks':{}}
recording=None
def target_state():return json.loads((OUT/'target-state.json').read_text(encoding='utf-8'))
def check(name,value):report['checks'][name]=value;print(name,json.dumps(value,ensure_ascii=True),flush=True);assert value is not False,name

with sync_playwright() as p:
 m=p.chromium.connect_over_cdp('http://127.0.0.1:9225').contexts[0].pages[0]
 pc=p.chromium.connect_over_cdp('http://127.0.0.1:9226').contexts[0].pages[0]
 def host(path,body=None):return pc.evaluate('([path,body])=>Axx.backendRequest(body===null?"GET":"POST","/axx-api/mobile/"+path,body)',[path,body])
 def status():return host('control/status')
 def click(selector):m.locator(selector).click(timeout=5000)
 def stop():
  if m.locator('#control-stop').is_visible():click('#control-stop');time.sleep(.2)
  host('control/cancel',{})
 def acquire_at(name):
  stop();u.ShowWindow(target,9);u.SetWindowPos(target,C.c_void_p(-1),0,0,1920,1030,0);time.sleep(.25)
  r=target_state()['targets'][name];u.SetCursorPos(r['x']+r['width']//2,r['y']+r['height']//2)
  # Local setup precedes the lease; these clicks are not counted as remote evidence.
  u.mouse_event(2,0,0,0,0);u.mouse_event(4,0,0,0,0);time.sleep(.15)
  assert u.GetForegroundWindow()==target,'Test window lost focus; no text sent'
  pc.evaluate("Axx.nativeInvoke('window_action',{action:'show'})")
  click('#control-acquire');m.locator('#control-stop').wait_for(state='visible',timeout=4000);time.sleep(.1);assert status()['native']['active'],m.locator('#control-status').inner_text()
 def gesture(dx,dy):
  box=m.locator('#control-pad').bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
  session=m.context.new_cdp_session(m)
  session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
  for i in range(1,11):
   session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+dx*i/10,'y':y+dy*i/10}]});time.sleep(.025)
  session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});session.detach();time.sleep(.2)
 try:
  if not m.locator('#control-surface').evaluate('(e)=>e.open'):
   click('[data-pane=pc]');click('#control-open-pad')
  click('[data-control-mode=pad]')
  acquire_at('button');before=target_state()['clicks'];click('#control-left');time.sleep(.3)
  check('left_click_through_overlay',target_state()['clicks']==before+1)
  click('#control-right');time.sleep(.3)
  check('right_click',any(e['type']=='4' and e['num']=='3' for e in target_state()['events']))
  report['material']=status()['native']['material_key'];report['desktop_material']=pc.evaluate('Axx.app.renderer.lutKey')
  check('live_material_identity',report['material']==report['desktop_material'])
  recording=ScreenRecordingService(OUT);rec=recording.start({'region':{'x':0,'y':0,'width':1920,'height':1030},'fps':15,'quality':'detail','countdown':0,'maxMinutes':1})
  before=status()['native']['cursor'];gesture(60,-25);after=status()['native']['cursor']
  check('relative_movement',after['x']>before['x'] and after['y']<before['y']);report['movement']={'before':before,'after':after}
  ImageGrab.grab(all_screens=True,include_layered_windows=True).save(OUT/'desktop-cursor-active.png')
  (OUT/'trackpad-final-real.png').write_bytes(subprocess.check_output([ADB,'exec-out','screencap','-p']))
  acquire_at('canvas');before=target_state()['drag'];click('#control-drag');gesture(45,30);click('#control-drag');time.sleep(.3)
  check('drag',target_state()['drag']!=before)
  click('#control-settings');click('[data-scroll="0,120"]');click('[data-scroll="120,0"]');click('#control-settings');time.sleep(.3)
  check('vertical_scroll',any(e.get('delta')==120 for e in target_state()['events']))
  report['horizontal_scroll']='packet accepted; inspect native event record for horizontal delivery'
  acquire_at('text');click('[data-control-mode=keyboard]');m.locator('#control-text').fill('Axx: español ñ — 中文 😀')
  assert u.GetForegroundWindow()==target,'Focus changed; no text sent'
  click('#control-send');time.sleep(.4);check('unicode_text','Axx: español ñ — 中文 😀' in target_state()['text'])
  (OUT/'keyboard-final-real.png').write_bytes(subprocess.check_output([ADB,'exec-out','screencap','-p']))
  click('[data-key=Control]');m.locator('#control-letter').select_option('A');click('#control-chord');click('[data-key=Control]');time.sleep(.3)
  check('modifier_released',status()['native']['keys']==[])
  click('[data-key=Shift]');check('modifier_held',status()['native']['keys']==['Shift']);click('#control-stop');time.sleep(.2)
  n=status()['native'];check('stop_releases_input',not n['active'] and not n['keys'] and not n['buttons'])
  ImageGrab.grab(all_screens=True,include_layered_windows=True).save(OUT/'desktop-cursor-stopped.png')
  timings=m.evaluate('''async()=>{const a=[];for(let i=0;i<20;i++){const t=performance.now();await Capacitor.Plugins.AxxTransport.request({path:'/v1/control/status',method:'GET'});a.push(performance.now()-t);}return a;}''')
  report['latency']={'operation':'control/status','samples_ms':timings,'median_ms':statistics.median(timings)}
 except Exception as error:
  report['interruption']=str(error);print('INTERRUPTED',str(error),flush=True)
 finally:
  try:stop()
  except Exception:pass
  if recording:
   recording.control(rec['id'],'stop');deadline=time.monotonic()+10
   while recording.status()['state'] in ('running','stopping') and time.monotonic()<deadline:time.sleep(.2)
   report['recording']=recording.status()
  report['target']=target_state();(OUT/'physical-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print('SAVED',str(OUT/'physical-acceptance.json'),flush=True)
