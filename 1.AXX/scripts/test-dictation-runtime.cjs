/** Full native UI with synthetic microphone; no physical recording. */
const fs=require('node:fs'), path=require('node:path'), http=require('node:http'), assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
  const server=http.createServer((req,res)=>{
    const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,'../Axx.html');
    res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');res.end(fs.readFileSync(file));
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
  try{
    const page=await browser.newPage({viewport:{width:1300,height:1000},reducedMotion:'reduce'}),errors=[];
    page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      window.requests=[];window.micRequests=0;window.transcribed=false;
      navigator.mediaDevices.getUserMedia=async()=>{
        window.micRequests++;
        const ctx=new AudioContext();window.fixtureContext=ctx;
        return ctx.createMediaStreamDestination().stream;
      };
      window.MediaRecorder=class{
        static isTypeSupported(){return true;}
        state='inactive';
        constructor(stream){this.stream=stream;}
        start(){this.state='recording';queueMicrotask(()=>this.onstart?.());}
        stop(){this.state='inactive';queueMicrotask(()=>{this.ondataavailable?.({data:new Blob(['fixture audio'],{type:'audio/webm'})});this.onstop?.();});}
      };
      window.__TAURI__={core:{invoke:async(name,args)=>{
        const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
        if(name==='native_status')return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
        if(name==='desktop_layout')return {...desktop,...args};
        if(name==='backend_request'){
          requests.push(args.path);
          if(args.path==='/axx-api/speech/transcribe') {await new Promise(r=>window.releaseTranscript=r);return {text:'Hola desde el dictado'};}
          if(args.path==='/axx-api/speech/voices')return {available:true,voices:[]};
          if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};
          if(args.path.includes('/commands/resolve'))return {match:'none'};
          return {};
        }return null;
      }},event:{listen:async()=>()=>{}}};
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>Axx?.nativeVoice && Axx?.resident?.firstFrame);
    await page.evaluate(()=>{Axx.resident.summon(false);Axx.flow.select('dictation');});
    await page.waitForFunction(()=>document.getElementById('v13-dock').getBoundingClientRect().width>0);
    const layout=await page.evaluate(async()=>{
      await Axx.resident.layout();
      const el=document.getElementById('v13-dock'),before=el.getBoundingClientRect().toJSON();
      Axx.voice13.layout();
      return {before,after:el.getBoundingClientRect().toJSON()};
    });
    for(const key of ['x','y','width','height'])assert.ok(Math.abs(layout.before[key]-layout.after[key])<1,`Dictation layout has competing ${key}: ${JSON.stringify(layout)}`);
    await page.evaluate(()=>Axx.resident.tap());
    assert.equal(await page.evaluate(()=>Axx.voice13.permit),true,'Avatar must request dictation consent instead of toggling the tool menu');
    await page.evaluate(()=>{Axx.voice13.openFields();Axx.voice13.consent=true;Axx.voice13.permit=false;});
    const overlap=await page.evaluate(async()=>{
      await Axx.resident.layout();
      const a=document.getElementById('v13-dock').getBoundingClientRect(),b=document.getElementById('v13-pad').getBoundingClientRect();
      return Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
    });
    assert.equal(overlap,0,'Dictation controls must not sit behind the destination panel');
    await page.evaluate(()=>Axx.voice13.begin());
    try {await page.waitForFunction(()=>Axx.voice13.status==='listening');}
    catch(e){console.log(await page.evaluate(()=>({status:Axx.voice13.status,error:Axx.voice13.error,notice:Axx.voice13.notice,target:Axx.voice13.target?.name,capture:Axx.voice13.capture.state,mics:micRequests})));throw e;}
    assert.equal(await page.evaluate(()=>micRequests),1,'Meter and recorder must share the same capture');
    await page.evaluate(()=>Axx.voice13.pause(true));
    await page.waitForFunction(()=>typeof releaseTranscript==='function');
    assert.equal(await page.evaluate(()=>Axx.voice13.status),'stopping');
    await page.evaluate(()=>releaseTranscript());
    await page.waitForFunction(()=>document.getElementById('v13-note').value.includes('Hola desde el dictado'));
    assert.equal(await page.evaluate(()=>Axx.voice13.status),'paused');
    assert.equal(await page.evaluate(()=>Axx.voice13.meter.active),false);
    assert.equal(await page.evaluate(()=>Axx.companion.data.messages.length),0,'Dictation must not send text');
    assert.equal(await page.evaluate(()=>requests.includes('/axx-api/actions/cancel')),false);
    assert.deepEqual(errors,[]);
    const output=path.resolve(__dirname,'../../evidence/chat-actions-20261021');fs.mkdirSync(output,{recursive:true});
    await page.screenshot({path:path.join(output,'dictation.png')});
    console.log('PASS: stable native dictation geometry, avatar action, one microphone stream, graceful final transcript, no automatic send or unrelated cancellation');
  }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
