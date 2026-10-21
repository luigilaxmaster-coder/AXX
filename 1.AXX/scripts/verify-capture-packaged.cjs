/* Runs the real Windows host and bundled backend against an owned color window. */
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process'),{createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const root=path.resolve(__dirname,'../..'),exe=path.join(root,'src-tauri/target/release/Axx.exe');
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'axx-capture-native-'));
 const port=19483;let app,browser,fixture;
 try{
  fixture=spawn('py',['-3.14','-c',"import ctypes,tkinter as t;ctypes.windll.user32.SetProcessDPIAware();w=t.Tk();w.overrideredirect(True);w.geometry('320x240+80+80');w.configure(background='#22bb66');w.attributes('-topmost',True);w.mainloop()"],{windowsHide:true,stdio:'ignore'});
  app=spawn(exe,[],{cwd:path.dirname(exe),env:{...process.env,LOCALAPPDATA:data,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1`},windowsHide:true,stdio:'ignore'});
  for(let i=0;i<100;i++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{await wait(300);}}
  assert.ok(browser,'WebView2 debugging endpoint did not start');
  const context=browser.contexts()[0];let main;
  for(let i=0;i<100;i++){main=context.pages().find(p=>p.url().includes('Axx.html'));if(main)break;await wait(200);}
  assert.ok(main,'Main WebView not found');
  await main.waitForFunction(()=>window.Axx?.nativeCapture&&Axx.resident?.firstFrame,{},{timeout:60000});
  let ready=false;
  for(let i=0;i<150;i++){const s=await main.evaluate(()=>Axx.nativeInvoke('native_status',{}));if(s.backendReady){ready=true;break;}if(s.backendError)throw new Error(s.backendError);await wait(300);}
  assert.ok(ready,'Bundled backend did not become ready');
  await main.evaluate(()=>{Axx.resident.summon(false);Axx.flow.select('screen');Axx.capture19.prefs.options.countdown=0;});
  await main.locator('#a11-record-start').click();
  let selector;
  for(let i=0;i<100;i++){selector=context.pages().find(p=>p.url().includes('mode=select'));if(selector)break;await wait(100);}
  assert.ok(selector,'Native selector did not open');
  await selector.waitForLoadState('domcontentloaded');
  const desktop=await selector.evaluate(()=>({width:+new URL(location.href).searchParams.get('width'),height:+new URL(location.href).searchParams.get('height'),w:innerWidth,h:innerHeight}));
  const x=v=>v/desktop.width*desktop.w,y=v=>v/desktop.height*desktop.h;
  await selector.mouse.move(x(100),y(100));await selector.mouse.down();await selector.mouse.move(x(300),y(260),{steps:8});await selector.mouse.up();
  await main.waitForFunction(()=>Axx.nativeCapture.state==='running'||Axx.nativeCapture.state==='error',{},{timeout:20000});
  assert.equal(await main.evaluate(()=>Axx.nativeCapture.state),'running',await main.evaluate(()=>Axx.nativeCapture.error));
  await wait(1500);
  await main.evaluate(()=>Axx.resident.tap());await main.waitForFunction(()=>Axx.nativeCapture.state==='paused');
  let halo=context.pages().find(p=>p.url().includes('mode=halo'));assert.ok(halo,'Halo missing');
  await halo.waitForFunction(()=>document.documentElement.dataset.phase==='paused');
  await wait(500);await main.evaluate(()=>Axx.resident.tap());await main.waitForFunction(()=>Axx.nativeCapture.state==='running');
  await wait(700);await main.locator('#a11-record-stop').click();
  await main.waitForFunction(()=>['finished','error'].includes(Axx.nativeCapture.state),{},{timeout:20000});
  const status=await main.evaluate(()=>Axx.backendRequest('GET','/axx-api/screen/status'));
  assert.equal(status.state,'finished',status.error);assert.ok(status.verified);
  const verify=spawnSync('py',['-3.14','-c',"import av,sys,json;v=av.open(sys.argv[1]);f=next(v.decode(video=0));a=f.to_ndarray(format='rgb24');points=[a[1,1].tolist(),a[50,50].tolist(),a[-2,-2].tolist()];assert (f.width,f.height)==(200,160),(f.width,f.height);assert all(abs(p[0]-34)<20 and abs(p[1]-187)<20 and abs(p[2]-102)<20 for p in points),points;print(json.dumps({'resolution':[f.width,f.height],'pixels':points}))",status.path],{encoding:'utf8',windowsHide:true});
  assert.equal(verify.status,0,verify.stderr);
  const out=path.join(root,'evidence/area-recording-20261021');
  fs.writeFileSync(path.join(out,'packaged-native.json'),JSON.stringify({realHost:true,bundledBackend:true,areaSelection:true,haloExcluded:true,avatarPauseResume:true,frames:status.frames,bytes:status.bytes,sha256:status.sha256,decoded:JSON.parse(verify.stdout)},null,2));
  // Exercise native Escape cancellation and prove the backend survives selector destruction.
  await main.locator('#a11-record-start').click();
  for(let i=0;i<100;i++){selector=context.pages().find(p=>p.url().includes('mode=select'));if(selector)break;await wait(100);}
  await selector.keyboard.press('Escape');await main.waitForFunction(()=>!Axx.nativeCapture.selecting);
  assert.equal((await main.evaluate(()=>Axx.backendRequest('GET','/axx-api/screen/status'))).state,'finished');
  console.log('PASS: real Tauri area selection, bundled MP4, halo excluded at edges, avatar pause/resume, Escape, backend stays alive');
 }finally{
  if(browser)await browser.close();
  for(const proc of [app,fixture])if(proc?.pid)spawnSync('taskkill',['/PID',String(proc.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  // Temp application state remains outside the repository for failed-run diagnostics.
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
