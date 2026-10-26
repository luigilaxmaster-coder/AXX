/** Full HTML -> authenticated HTTP -> frozen backend -> real Windows actions.
 * Opens YouTube once; only executes harmless, explicitly approved fixture scripts.
 */
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const http = require('node:http'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');

(async () => {
  const root = path.resolve(__dirname, '../..'), binary = path.resolve(process.argv[2] || path.join(root, 'dist/axx-backend.exe'));
  const evidence = path.join(root, 'evidence/chat-actions-20261021');
  fs.mkdirSync(evidence, {recursive: true});
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'axx-command-e2e-'));
  fs.writeFileSync(path.join(workspace, 'providers.json'), JSON.stringify({allow_paid:false,providers:[]}));
  const token = crypto.randomBytes(32).toString('hex'), ready = path.join(workspace, 'ready.json');
  const log = fs.openSync(path.join(workspace, 'backend.log'), 'a');
  const backend = spawn(binary, ['--port','0','--data-dir',workspace,'--ready-file',ready], {
    cwd:root, env:{...process.env,AXX_HOST_TOKEN:token}, windowsHide:true, stdio:['ignore',log,log]
  });
  let browser, server;
  try {
    const deadline = Date.now() + 60000;
    while (!fs.existsSync(ready)) {
      if (backend.exitCode !== null || Date.now() > deadline) throw new Error('Backend startup failed: ' + workspace);
      await new Promise(r=>setTimeout(r,100));
    }
    const base = 'http://127.0.0.1:' + JSON.parse(fs.readFileSync(ready,'utf8')).port;
    const calls = [];
    const request = async ({method,path:route,body}) => {
      calls.push(route);
      const reply = await fetch(base+route, {method, headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
        ...(body === undefined || body === null || method === 'GET' ? {} : {body:JSON.stringify(body)})});
      const data = await reply.json();
      if (!reply.ok) throw new Error(JSON.stringify(data));
      return data;
    };
    const voices=await request({method:'GET',path:'/axx-api/speech/voices'});
    const voice=voices.voices.find(v=>v.language?.startsWith('en')) || voices.voices[0];
    const audio=await request({method:'POST',path:'/axx-api/speech/synthesize',body:{text:'Hello. This is a local dictation test.',voice:voice.name,rate:0,volume:100}});
    const transcript=await request({method:'POST',path:'/axx-api/speech/transcribe',body:{audio_base64:audio.audio_base64,mime:'audio/wav',language:'en',task:'transcribe'}});
    assert.ok(transcript.text.trim().length>10,JSON.stringify(transcript));
    server = http.createServer((req,res)=>{
      const file = req.url.startsWith('/scripts/') ? path.join(__dirname,path.basename(req.url)) : path.join(__dirname,'../Axx.html');
      res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');
      res.end(fs.readFileSync(file));
    });
    await new Promise(r=>server.listen(0,'127.0.0.1',r));
    browser = await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
    const page = await browser.newPage({viewport:{width:1200,height:1000}}), errors = [];
    page.setDefaultTimeout(15000);
    page.on('pageerror',e=>errors.push(e.message));
    await page.exposeFunction('nativeTestRequest', request);
    await page.addInitScript(()=>{
      window.__TAURI__={core:{invoke:async(name,args)=>{
        const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
        if(name==='native_status') return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
        if(name==='desktop_layout') return {...desktop,...args};
        if(name==='backend_request') return window.nativeTestRequest(args);
        return null;
      }},event:{listen:async()=>()=>{}}};
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    console.log('fixture: HTML loaded');
    await page.waitForFunction(()=>window.Axx?.commandLibrary && window.Axx?.resident?.firstFrame);
    console.log('fixture: UI ready');
    await page.evaluate(()=>Axx.flow.select('chat'));
    await page.locator('#chat-input').fill('abre YouTube');
    await page.locator('#chat-send').click();
    console.log('fixture: YouTube submitted');
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    try { await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.state === 'succeeded'); }
    catch(error) {
      console.log(JSON.stringify({calls, ui:await page.evaluate(()=>({operation:Axx.commandLibrary.lastOperation,messages:Axx.companion.data.messages,status:document.getElementById('command-library-status').textContent}))},null,2));
      throw error;
    }
    const opened = await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    console.log('fixture: Windows handoff confirmed');
    assert.equal(opened.command_id,'axx.desktop.open_url');
    assert.equal(opened.evidence.target,'https://www.youtube.com/');
    assert.equal(opened.evidence.verification,'os_handoff');
    assert.match(await page.locator('#chat-log').innerText(), /enviado a Windows/);
    await page.locator('#chat-input').fill('/cmd echo AXX-COMMAND-OK');
    await page.locator('#chat-send').click();
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.state === 'awaiting_approval');
    assert.equal(await page.locator('#cw-operation').isVisible(),true);
    assert.match(await page.locator('#cw-operation').innerText(),/echo AXX-COMMAND-OK/);
    await page.evaluate(()=>Axx.backendRequest('POST','/axx-api/speech/cancel',{}));
    const pendingId = await page.evaluate(()=>Axx.commandLibrary.operation.operation_id);
    const observed = await request({method:'GET',path:'/axx-api/commands/operations?operation_id='+pendingId});
    assert.equal(observed.operation.state,'awaiting_approval');
    const before = calls.filter(p=>p.endsWith('/execute')).length;
    assert.equal(before,1);
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy && ['succeeded','failed','cancelled','unknown'].includes(Axx.commandLibrary.lastOperation?.state));
    const result = await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    assert.equal(result.state,'succeeded',JSON.stringify(result));
    assert.equal(result.output.stdout.trim(),'AXX-COMMAND-OK');
    await page.evaluate(()=>Axx.flow.select('chat'));
    await page.waitForFunction(()=>document.getElementById('chat-log').textContent.includes('CMD terminó correctamente'));
    assert.match(await page.locator('#chat-log').innerText(), /CMD terminó correctamente/);
    assert.match(await page.locator('#chat-log').innerText(), /AXX-COMMAND-OK/);
    assert.equal(calls.some(p=>p==='/axx-api/chat'),false);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(evidence,'chat-result.png')});
    const report={kind:'FULL_HTML_HTTP_FROZEN_WINDOWS_ACTIONS',binary,sha256:crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex'),
      passed:['YouTube command from chat reaches real Windows handoff after approval','No model required or called','CMD approval is visible in chat before execution','Stopping speech preserves pending command approval','Real CMD output returns to chat','Real local Whisper transcription of generated speech','No browser exceptions'],
      generated_audio_transcript:transcript.text,
      limitations:['Tauri IPC emulated by a test bridge; backend and Windows actions are real','OS accepted browser launch; loaded webpage not inspected']};
    fs.writeFileSync(path.join(evidence,'e2e.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally {
    if(browser) await browser.close();
    if(server) await new Promise(r=>server.close(r));
    spawnSync('taskkill',['/F','/T','/PID',String(backend.pid)],{windowsHide:true,stdio:'ignore'});
    fs.closeSync(log);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
