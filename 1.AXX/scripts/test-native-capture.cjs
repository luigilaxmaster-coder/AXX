const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const server=http.createServer((req,res)=>{const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,req.url.startsWith('/capture-overlay')?'../capture-overlay.html':'../Axx.html');res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');res.end(fs.readFileSync(file));});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
 try{
  const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.calls=[];window.rec={state:'ready',id:''};window.cancelSelection=false;
   window.__TAURI__={core:{invoke:async(name,args)=>{calls.push({name,args});const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
    if(name==='native_status')return {native:true,backendReady:false,desktop};if(name==='desktop_layout')return {...desktop,...args};
    if(name==='capture_select'){await new Promise(r=>setTimeout(r,80));return cancelSelection?null:{x:-100,y:20,width:400,height:300};}
    if(name==='backend_request'){
     if(args.path==='/axx-api/screen/status')return structuredClone(rec);
     if(args.path==='/axx-api/screen/start')return rec={state:'running',id:'rec1',region:args.body.region,fps:30,elapsedMs:1000,bytes:400};
     if(args.path==='/axx-api/screen/control'){const op=args.body.command;rec={...rec,state:op==='pause'?'paused':op==='resume'?'running':'finished',path:op==='stop'?'C:/Axx/artifacts/recordings/test.mp4':'',verified:op==='stop'};return structuredClone(rec);}
     if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};return {};
    }return null;
   }},event:{listen:async()=>()=>{}}};
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>Axx.nativeCapture&&Axx.resident?.firstFrame);
  await page.evaluate(()=>{Axx.resident.summon(false);Axx.flow.select('screen');});
  await page.click('#a11-record-start');await page.waitForFunction(()=>Axx.nativeCapture.state==='running');
  await page.evaluate(()=>Axx.actions.sync());
  assert.equal(await page.locator('#a11-record-pause').textContent(),'','Record controls must stay icon-only after state sync');
  assert.equal(await page.locator('#a11-record-pause svg').count(),1);
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.name==='capture_select').length),1);
  await page.evaluate(()=>{Axx.resident.tap();Axx.resident.tap();});await page.waitForFunction(()=>Axx.nativeCapture.state==='paused');
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.args?.body?.command==='pause').length),1);
  await page.evaluate(()=>Axx.resident.tap());await page.waitForFunction(()=>Axx.nativeCapture.state==='running');
  await page.click('#a11-record-stop');await page.waitForFunction(()=>Axx.nativeCapture.state==='finished');
  assert.equal(await page.locator('#r19-native-result').isVisible(),true);
  assert.equal(await page.evaluate(()=>calls.some(x=>x.args?.path==='/axx-api/screen/save')),false,'Recording must not pass through the 6 MiB base64 endpoint');
  await page.click('#r19-native-open');assert.equal(await page.evaluate(()=>calls.some(x=>x.args?.path==='/axx-api/screen/open')),true);
  await page.evaluate(()=>{cancelSelection=true;});await page.click('#a11-record-start');await page.waitForFunction(()=>!Axx.nativeCapture.selecting);
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.args?.path==='/axx-api/screen/start').length),1,'Cancelling selection cannot start recording');
  assert.deepEqual(errors,[]);
  const output=path.resolve(__dirname,'../../evidence/area-recording-20261021');fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'recording-controls.png')});
  const overlay=await browser.newPage({viewport:{width:1000,height:600}});
  await overlay.addInitScript(()=>{window.finished=[];window.__TAURI__={core:{invoke:async(n,a)=>finished.push(a)}};});
  await overlay.goto(`http://127.0.0.1:${server.address().port}/capture-overlay.html?mode=select&token=test&width=2000&height=1200`);
  await overlay.mouse.move(600,400);await overlay.mouse.down();await overlay.mouse.move(200,100);await overlay.mouse.up();
  assert.deepEqual(await overlay.evaluate(()=>finished[0].rect),[.2,1/6,.4,.5]);
  await overlay.reload();await overlay.keyboard.press('Escape');assert.equal(await overlay.evaluate(()=>finished[0].rect),null);
  console.log('PASS: native area start, avatar pause/resume, duplicate suppression, automatic disk result, cancel selection, reverse drag and Escape');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
