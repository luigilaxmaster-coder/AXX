const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const server=http.createServer((req,res)=>{const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,'../Axx.html');res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');res.end(fs.readFileSync(file));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
 try {
  const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.controls=[];window.fixture={available:true,audioAvailable:true,peak:.4,currentId:'a',sessions:[{id:'a',app:'Browser',title:'Vídeo de prueba',playing:true,canPlay:true,canPause:true,canNext:false,canPrevious:false,canSeek:false,time:4,duration:60},{id:'b',app:'Player',title:'Otra pista',playing:false,canPlay:true,canPause:true,canNext:true,canPrevious:true,canSeek:true,time:0,duration:120}]};
   window.__TAURI__={core:{invoke:async(name,args)=>{
    const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
    if(name==='native_status')return {native:true,backendReady:false,desktop};
    if(name==='desktop_layout')return {...desktop,...args};
    if(name==='system_media_status')return structuredClone({...fixture,updatedAt:Date.now()});
    if(name==='system_media_control'){controls.push(args);await new Promise(r=>setTimeout(r,80));const s=fixture.sessions.find(s=>s.id===args.id);if(!s)throw Error('La sesión terminó');s.playing=args.command==='play';return true;}
    if(name==='backend_request'){if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};return {};}
    return null;
   }},event:{listen:async()=>()=>{}}};
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(()=>Axx.nativeMusic?.snapshot?.sessions?.length===2,{},{timeout:5000});
  await page.evaluate(()=>{Axx.resident.summon(false);Axx.flow.select('music');});
  assert.equal(await page.evaluate(()=>Axx.media16.source),'system');
  assert.equal(await page.evaluate(()=>{const p=document.getElementById('panel').getBoundingClientRect(),b=document.getElementById('m16-play').getBoundingClientRect();return b.top>=p.top&&b.bottom<=p.bottom;}),true,'Playback control is visible without scrolling');
  const dir=path.resolve(__dirname,'../../evidence/system-music-20261021');fs.mkdirSync(dir,{recursive:true});
  await page.screenshot({path:path.join(dir,'music-playing.png')});
  await page.evaluate(()=>{Axx.resident.tap();Axx.resident.tap();});
  await page.waitForFunction(()=>!Axx.nativeMusic.pending);
  assert.deepEqual(await page.evaluate(()=>controls.map(x=>[x.id,x.command])),[['a','pause']]);
  assert.equal(await page.evaluate(()=>Axx.media16.state.playing),false);
  await page.selectOption('#m16-system-sessions','b');
  await page.click('#m16-play');
  await page.waitForFunction(()=>controls.length===2&&!Axx.nativeMusic.pending);
  assert.deepEqual(await page.evaluate(()=>controls.map(x=>[x.id,x.command])),[['a','pause'],['b','play']]);
  await page.evaluate(async()=>{fixture.sessions=fixture.sessions.filter(x=>x.id!=='b');await Axx.nativeMusic.refresh();});
  assert.equal(await page.evaluate(()=>Axx.nativeMusic.selectedId),'b','A disappeared manual target must not redirect to another app');
  assert.equal(await page.locator('#m16-play').isDisabled(),true);
  await page.selectOption('#m16-system-sessions','');
  await page.evaluate(async()=>{fixture.sessions=[];fixture.peak=.6;await Axx.nativeMusic.refresh();});
  assert.equal(await page.locator('#m16-play').isDisabled(),true);
  assert.match(await page.locator('#m16-system-info').innerText(),/audio|sonido/i);
  const signal=await page.evaluate(()=>{Axx.nativeMusic.level=0;const s=Axx.nativeMusic.signal(.016);return {level:s.level,bass:s.bass};});
  assert.ok(signal.level>0&&signal.level<.6,'Amplitude reaction eases towards the measured level');
  await page.evaluate(()=>{Axx.nativeMusic.snapshot.updatedAt=0;for(let i=0;i<200;i++)Axx.nativeMusic.signal(.016);});
  assert.ok(await page.evaluate(()=>Axx.nativeMusic.level<.001),'Stale audio decays to silence');
  await page.evaluate(()=>Axx.media16.choose('local'));
  assert.equal(await page.evaluate(()=>Axx.actions.remoteMusic.active),false);
  assert.deepEqual(errors,[]);
  await page.evaluate(()=>Axx.media16.choose('system'));await page.screenshot({path:path.join(dir,'music.png')});
  console.log('PASS: automatic detection, avatar pause, duplicate suppression, explicit session resume, disappeared target, audio without controls, local source, no JS errors');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
