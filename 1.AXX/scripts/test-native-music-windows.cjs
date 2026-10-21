// Real GSMTC/Core Audio integration. Controls only the isolated local test player.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),readline=require('node:readline');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const probe=spawn(path.resolve(__dirname,'../../src-tauri/target/debug/examples/media_probe.exe'),[],{windowsHide:true,stdio:['pipe','pipe','inherit']});
 const pending=[];readline.createInterface({input:probe.stdout}).on('line',line=>pending.shift()?.(JSON.parse(line)));
 const ask=x=>new Promise(resolve=>{pending.push(resolve);probe.stdin.write(JSON.stringify(x)+'\n');});
 const wait=async(fn)=>{for(let n=0;n<60;n++){const s=await ask({});if(fn(s))return s;await sleep(200);}throw Error('Native media condition timed out');};
 const samples=48000*8, wav=Buffer.alloc(44+samples*2);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(48000,24);wav.writeUInt32LE(96000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples*2,40);for(let i=0;i<samples;i++)wav.writeInt16LE(Math.round(Math.sin(i/48000*440*2*Math.PI)*1000),44+i*2);
 const title='AXX-MEDIA-INTEGRATION-'+Date.now();
 const server=http.createServer((req,res)=>{if(req.url==='/tone.wav'){res.setHeader('Content-Type','audio/wav');res.end(wav);}else{res.setHeader('Content-Type','text/html');res.end(`<audio id="a" src="/tone.wav" loop controls></audio><button onclick="a.play()">Play test</button><script>navigator.mediaSession.metadata=new MediaMetadata({title:${JSON.stringify(title)},artist:'Local test'});navigator.mediaSession.setActionHandler('play',()=>a.play());navigator.mediaSession.setActionHandler('pause',()=>a.pause());a.onplay=()=>navigator.mediaSession.playbackState='playing';a.onpause=()=>navigator.mediaSession.playbackState='paused';</script>`);}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;
 try {
  const baseline=await wait(s=>s.available);
  browser=await chromium.launch({headless:false,channel:'msedge',args:['--autoplay-policy=no-user-gesture-required']});
  const page=await browser.newPage();await page.goto(`http://127.0.0.1:${server.address().port}`);await page.click('button');
  const detected=await wait(s=>s.sessions.some(x=>x.title===title&&x.playing));
  const session=detected.sessions.find(x=>x.title===title);
  assert.equal((await ask({id:session.id,command:'pause'})).ok,true);
  await page.waitForFunction(()=>a.paused);await wait(s=>s.sessions.some(x=>x.id===session.id&&!x.playing));
  assert.equal((await ask({id:session.id,command:'play'})).ok,true);
  await page.waitForFunction(()=>!a.paused);await wait(s=>s.sessions.some(x=>x.id===session.id&&x.playing));
  await browser.close();browser=null;
  await wait(s=>!s.sessions.some(x=>x.id===session.id));
  assert.ok((await ask({id:session.id,command:'pause'})).error);
  const dir=path.resolve(__dirname,'../../evidence/system-music-20261021');fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(path.join(dir,'native.json'),JSON.stringify({nativeWindows:true,available:baseline.available,audioAvailable:baseline.audioAvailable,detectedPeak:detected.peak,checks:['own Edge session detected','GSMTC pause confirmed by HTMLMediaElement and native status','GSMTC resume confirmed by HTMLMediaElement and native status','closed session disappears','stale control rejected'],audioMeterValidation:detected.peak>0?'real output measured':'No active output; positive physical audio measurement remains unverified'},null,2));
  console.log('PASS: native Windows real Edge pause/resume/removal; audio meter available='+baseline.audioAvailable+', peak='+detected.peak);
 }finally{await browser?.close();probe.kill();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
