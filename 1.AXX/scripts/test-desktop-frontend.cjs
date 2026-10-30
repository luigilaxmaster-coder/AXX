/** Controlled browser/IPC contract tests. These do not certify native Windows behavior. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { createRequire } = require('node:module');
const bundledRequire = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = bundledRequire('playwright');
const productionHtml = fs.readFileSync(path.join(__dirname, '../Axx.html'), 'utf8');
const html = process.env.AXX_TEST_VOICE_DRAFT ? productionHtml.replace('</body>', '<script>' + fs.readFileSync(path.join(__dirname, 'native-voice-fallback.draft.js'), 'utf8') + '</script></body>') : productionHtml;
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
assert(!html.includes('X-Axx-Token'), 'Host credentials must not appear in the frontend');
assert(!html.includes("const apiBase ="), 'Production must not hardcode a development port');
const reviewRequest='lista mis ventanas y consulta el estado del sistema';
const reviewResolution=JSON.parse(execFileSync(process.env.AXX_TEST_PYTHON||'python',['-c',`
import json,sys,tempfile
from pathlib import Path
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
with tempfile.TemporaryDirectory() as directory:
    executor=ActionExecutor(Path(directory)/'state.db',Path(directory)/'artifacts')
    commands=CommandService(executor)
    try:
        result=commands.resolve(sys.argv[1])
        assert executor.list_operations()==[]
        print(json.dumps(result,ensure_ascii=False))
    finally:
        commands.close();executor.close()
`,reviewRequest],{cwd:path.join(__dirname,'../..'),encoding:'utf8',windowsHide:true}));
assert.equal(reviewResolution.match,'sequence','The review fixture must be reachable through the production resolver');
assert.deepEqual(reviewResolution.steps,[{command_id:'axx.desktop.list_windows',inputs:{}},{command_id:'axx.system.telemetry',inputs:{}}]);

(async () => {
  const server = http.createServer((req, res) => { if (req.url?.startsWith('/scripts/') && /\.(js|css)$/.test(req.url)) { const file=path.join(__dirname,path.basename(req.url)); if (fs.existsSync(file)) { res.writeHead(200, { 'Content-Type': req.url.endsWith('.css')?'text/css':'application/javascript' }); res.end(fs.readFileSync(file)); return; } } res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  const results = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => { errors.push(e.message); if(process.env.AXX_TEST_ERROR_STACK)process.stderr.write(e.stack+'\n'); });
    await page.addInitScript(() => {
      // This suite verifies explicit provider/model eligibility. Do not inherit
      // the separate automatic discovery flow from fresh-install preferences.
      localStorage.setItem('axx.companion.v4', JSON.stringify({ version: 4, prefs: { provider: 'bridge', selection_mode: 'manual' } }));
      localStorage.setItem('axx.live.pause', '700');
      window.__contractCalls = [];
      window.__contractModels = [];
      window.__contractProviderRows = null;
      window.__contractSavedProviders = null;
      window.__contractHoldChat = false;
      window.__contractIdentity = null;
      window.__contractRecipes = [];
      window.__contractCommands = {};
      window.__contractEvents = {};
      window.__contractConversation = { id: 'contract-chat', title: 'Contract conversation', messages: [], draft: '', draft_at: Date.now(), updated: Date.now(), mode: 'ask', context: [], links: [], connect_id: 'contract-connect', shared_id: 'contract-shared' };
      const pcm = new Uint8Array(44 + 3200), view = new DataView(pcm.buffer);
      const str = (at, text) => [...text].forEach((c, i) => pcm[at + i] = c.charCodeAt(0));
      str(0, 'RIFF'); view.setUint32(4, pcm.length - 8, true); str(8, 'WAVE'); str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); str(36, 'data'); view.setUint32(40, 3200, true);
      window.__contractWav = btoa(String.fromCharCode(...pcm));
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        window.__contractCalls.push({ name, args });
        const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1660, spaceRight: 260, spaceAbove: 800, spaceBelow: 240 };
        if (name === 'native_status') return { native: true, backendReady: !window.__contractSuppressBackend, backendError: null, shortcut: 'Alt+Shift+A', restoreShortcutAvailable: !localStorage.getItem('contract.restore-conflict'), restoreShortcutError: localStorage.getItem('contract.restore-conflict') ? 'Ctrl+Alt+Espacio no disponible' : null, alwaysOnTop: true, timer: null, dataDirectory: 'CONTRACT_TEST_ONLY', desktop };
        if (name === 'desktop_layout') { await new Promise(resolve => setTimeout(resolve, 45)); window.__contractLayout = args; return { ...desktop, ...args }; }
        if (name === 'capture_halo' && window.__contractFailHalo) { window.__contractFailHalo = false; throw Error('Capture affinity busy'); }
        if (name !== 'backend_request') return null;
        const { method, path, body } = args;
        if (path === '/axx-api/prompts/compose') return {version:'contract-fixture',mode:body.mode,text:'Controlled prompt contract: '+body.mode};
        if (path === '/axx-api/chat/migrate') return { id: window.__contractConversation.id };
        if (path === '/axx-api/chat/conversations') return { conversations: [window.__contractConversation], groups: [], default_mode: 'ask' };
        if (path.startsWith('/axx-api/chat/conversations?id=')) return structuredClone(window.__contractConversation);
        if (path === '/axx-api/chat/save') {
          const row=window.__contractConversation, messages=new Map(row.messages.map(message=>[message.id,message]));
          for(const message of body.messages||[])messages.set(message.id,message);
          Object.assign(row,{draft:body.draft,attachment:body.attachment,messages:[...messages.values()]});return {saved:true};
        }
        if (path === '/axx-api/chat/operations') return { operations: [] };
        if (path === '/axx-api/status') return { ready: true, provider: 'Contract fixture', details: { providers: window.__contractProviderRows || (window.__contractModels.length ? window.__contractModels : ['configured-fixture-model']).map(model => ({ name: 'contract-fixture', state: window.__contractProviderState || (window.__contractModels.length ? 'ready_locally' : 'missing_key'), model, capabilities:['text'], tasks:['chat'] })) } };
        if (path === '/axx-api/models') return { models: window.__contractModels };
        if (path === '/axx-api/providers') return { providers:window.__contractSavedProviders || [] };
        if (path === '/axx-api/identity') {
          if (method === 'GET') return { identity: window.__contractIdentity };
          window.__contractIdentity = body; return { saved: true };
        }
        if (path === '/axx-api/recipes' && method === 'GET') return { recipes: window.__contractRecipes };
        if (path === '/axx-api/actions/execute') return { operation_id: body.operation_id, tool_name: body.tool_name, state: 'succeeded', postconditions_passed: true, output: { os: 'CONTRACT_ONLY' }, evidence: { fixture: true } };
        if (path === '/axx-api/commands/resolve') { if (window.__contractDenyResolver) throw new Error('Backend HTTP 403: test denial'); return window.__contractResolve || { match: 'none' }; }
        if (path.startsWith('/axx-api/commands?')) return { commands: [{ id: 'axx.system.telemetry', title: 'Estado del sistema', description: 'CONTRACT_ONLY', execution_enabled: true, parameters: {} }], counts: { imported: 0, enabled: 1, blocked: 0, verified_operations: 0 } };
        if (path === '/axx-api/commands/prepare') {
          const operation_id = body.operation_id;
          return window.__contractCommands[operation_id] = { operation_id, command_id: body.command_id, inputs: body.inputs, state: body.command_id === 'axx.artifact.write' ? 'awaiting_approval' : 'prepared' };
        }
        if(path==='/axx-api/commands/compensation-preview'){
          if(window.__holdCompensationPreview){window.__holdCompensationPreview=false;await new Promise(resolve=>{window.__releaseCompensationPreview=resolve;});}
          return structuredClone(window.__compensationPreview);
        }
        if(path==='/axx-api/commands/compensation-prepare'){
          const preview=window.__compensationPreview;if(body.source_operation_id!==preview.source_operation_id||body.source_receipt_hash!==preview.source_receipt_hash||body.expected_revision!==preview.compensation.revision||body.action!==preview.action)throw Error('COMPENSATION_PREVIEW_CHANGED');
          return window.__contractCommands[body.operation_id]={operation_id:body.operation_id,command_id:'axx.artifact.'+body.action,source_operation_id:body.source_operation_id,inputs:{source_operation_id:body.source_operation_id,source_receipt_hash:body.source_receipt_hash,expected_revision:body.expected_revision},conversation_id:window.__compensationSource.conversation_id,state:window.__compensationBadApproval?'prepared':'awaiting_approval',requires_approval:!window.__compensationBadApproval};
        }
        if (path === '/axx-api/recipes/prepare') {
          const recipe = window.__contractRecipes.find(record => record.intent_key === body.intent_key);
          if (!recipe || Object.keys(body.inputs).some(key => !(key in recipe.schema))) throw new Error('Parámetros de receta desconocidos');
          return window.__contractCommands[body.operation_id] = { operation_id: body.operation_id, command_id: 'axx.system.telemetry', inputs: {}, state: 'prepared' };
        }
        if (path === '/axx-api/commands/execute') {
          const operation=window.__contractCommands[body.operation_id];
          if(operation?.source_operation_id){if(body.approved!==true)throw Error('Approval required');const preview=window.__compensationPreview;preview.compensation.revision++;preview.compensation.state=operation.command_id.endsWith('.quarantine')?'quarantined':'present';preview.action=preview.compensation.state==='quarantined'?'restore':'quarantine';return window.__contractCommands[body.operation_id]={...operation,state:'succeeded',postconditions_passed:true,output:{source_operation_id:operation.source_operation_id,original_path:preview.artifact.path,current_path:preview.artifact.path,state:preview.compensation.state,revision:preview.compensation.revision},evidence:{no_bytes_deleted:true}};}
          return { ...operation, state: 'succeeded', postconditions_passed: true, output: { ready_for_action: true }, action_operation_id: 'fixture-action-' + body.operation_id, evidence: { fixture: true } };
        }
        if(path==='/axx-api/commands/reconcile'){const operation=window.__contractCommands[body.operation_id];return window.__contractCommands[body.operation_id]={...operation,state:'succeeded',postconditions_passed:true,output:{source_operation_id:operation.source_operation_id,original_path:window.__compensationPreview.artifact.path,state:'quarantined'},evidence:{reconciled:true,redispatched:false}};}
        if (path === '/axx-api/commands/cancel') {const operation=window.__contractCommands[body.operation_id];if(operation?.source_operation_id)return window.__contractCommands[body.operation_id]={...operation,state:'cancelled'};return { cancelled: true };}
        if (path === '/axx-api/learning/prepare') return window.__contractPlan = {...body,kind:'learned_plan',state:'awaiting_approval',message:'Revisa los dos pasos.',step_records:body.steps.map((_,i)=>({step_id:String(i),state:'pending'}))};
        if (path === '/axx-api/learning/actions') return {actions:[]};
        if (path.startsWith('/axx-api/learning/plan?id=')) return structuredClone(window.__contractPlan);
        if (path === '/axx-api/learning/execute') {
          if(body.operation_id!==window.__contractPlan.operation_id||body.approved!==true)throw Error('Wrong approval');
          await new Promise(resolve=>setTimeout(resolve,100));
          return window.__contractPlan={...window.__contractPlan,state:'succeeded',postconditions_passed:true,message:'Dos pasos comprobados.',results:[],step_records:window.__contractPlan.step_records.map(row=>({...row,state:'succeeded'}))};
        }
        if (path === '/axx-api/recipes/register') { window.__contractRecipes.push({ id: body.id, intent_key: body.intent_key, status: 'verified', schema: {} }); return { saved: true }; }
        if (path === '/axx-api/recipes/execute') return { success: true, fixture: true, steps_executed: 1 };
        if (path === '/axx-api/chat/cancel') return { cancelled: true };
        if (path === '/axx-api/actions/cancel') return { cancelled: true };
        if (path === '/axx-api/speech/voices') return { available: true, engine: 'windows-sapi', voices: [{ name: 'Contract fixture voice', language: 'en-US', enabled: true }] };
        if (path === '/axx-api/speech/synthesize') return { engine: 'windows-sapi', voice: body.voice, language: 'en-US', audio_base64: window.__contractWav, mime: 'audio/wav', duration_seconds: .1, evidence: { sha256: 'CONTRACT_ONLY' } };
        if (path === '/axx-api/speech/transcribe') { if (window.__contractHoldAsr) await new Promise(resolve => setTimeout(resolve, 150)); return { text: 'Texto del contrato de ASR', engine: 'faster-whisper', model: 'tiny' }; }
        if (path === '/axx-api/memory/query') return { hits: [{ path: 'recipes/contract.md' }], memory: { backend: 'ai-memory' }, execution_allowed: false };
        if (path === '/axx-api/memory/read') return { page: { body: 'Contract full recipe record' }, memory: { backend: 'ai-memory' }, execution_allowed: false };
        if (path === '/axx-api/chat') {
          if (window.__contractHoldChat) await new Promise(resolve => setTimeout(resolve, 500));
          return { request_id: body.request_id, choices: [{ message: { content: 'Contract fixture response' }, finish_reason: 'stop' }], axx_router: { provider: 'contract-fixture', model: body.model, elapsed_ms: 17 } };
        }
        throw new Error('Unsupported contract fixture route: ' + path);
      } }, event: { listen: async (name, fn) => { (window.__contractEvents[name] ||= []).push(fn); return () => {}; } } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.desktop?.ready && Axx.chatWorkspace?.ready && !window.Axx.companion.connecting);
    assert.deepEqual(errors, []);
    assert.equal(await page.locator('#fatal').textContent(), '');
    results.push('Full original HTML starts without uncaught exceptions');
    const corrections = await page.evaluate(async () => {
      const library=Axx.commandLibrary, companion=Axx.companion;
      const saved={operation:library.operation,lastOperation:library.lastOperation,busy:library.busy,generation:library.generation,observation:library.observationRevision,cancelling:library.cancellingGeneration,question:library.learningQuestion,request:library.request,render:library.renderOperation,status:library.status,notice:library.notice,message:companion.message,continueTask:Axx.skillLibrary.continueTask,chat:Axx.chatWorkspace.active.id,voiceRead:companion.data.prefs.voiceRead,voiceExplicit:localStorage.getItem('axx.voice.read.explicit'),stopSpeech:companion.stopSpeech};
      const calls=[],origin=saved.chat;
      const verifiedStep={state:'succeeded',operation_id:'completed-once',result:{state:'succeeded',postconditions_passed:true}},activeStep={state:'running',operation_id:'in-flight'};
      let plan={kind:'learned_plan',operation_id:'trial-correction',state:'running',conversation_id:origin,request:'ensayo',steps:[{command_id:'axx.artifact.write'},{command_id:'axx.file.sha256'}],step_records:[verifiedStep,activeStep]};
      try {
        library.operation=library.lastOperation=plan;
        library.busy=true;companion.message=()=>{};library.notice=text=>calls.push(['notice',text]);library.renderOperation=()=>{};library.status=()=>{};
        Axx.skillLibrary.continueTask=async(id,text)=>{calls.push(['repair',id,text]);};
        library.request=async(method,path,body)=>{
          if(body?.operation_id==='trial-correction'||path==='/axx-api/learning/plan?id=trial-correction'){
            calls.push([path,structuredClone(body)]);
            if(path.endsWith('/pause')){if(window.__releaseNaturalPause)await new Promise(resolve=>{window.__finishNaturalPause=resolve;});return {...plan,state:plan.state==='running'?'pausing':'paused',message:'Pausa solicitada'};}
            if(path.endsWith('/resume'))return {...plan,state:'awaiting_approval',message:'Revisa los pasos pendientes'};
            if(path.endsWith('/cancel'))return {...plan,state:'cancelled',message:'Cancelada'};
            return structuredClone(plan);
          }
          return saved.request.call(library,method,path,body);
        };
        await companion.send('No, ese archivo no.',{source:'voice'});
        const question=structuredClone(library.learningQuestion);
        await companion.send('C:\\destino-correcto\\ensayo.txt');
        const deferred=calls.filter(item=>item[0]==='repair').length===0&&library.learningQuestion.operation_id===question.operation_id;
        companion.data.prefs.voiceRead=true;companion.stopSpeech=()=>calls.push(['mute-speech']);
        const mute=companion.externalCommand('silencio');await mute();
        const speechOnly={muted:companion.data.prefs.voiceRead===false,pauses:calls.filter(item=>item[0]==='/axx-api/learning/pause').length};
        await companion.send('Espera, sigo yo',{source:'voice'});
        library.busy=false;plan={...plan,state:'awaiting_approval'};library.operation=library.lastOperation=plan;
        await companion.send('ese archivo no');
        const releasedApproval=library.operation===null;
        plan={...plan,state:'paused'};library.lastOperation=plan;
        await companion.send('C:\\destino-correcto\\ensayo.txt');
        await companion.send('Continúa desde aquí',{source:'voice'});
        library.operation={...library.operation,conversation_id:'another-chat'};
        await companion.send('ese archivo no');
        library.operation={...plan};delete library.operation.conversation_id;
        await companion.send('ese archivo no');
        library.learningQuestion={...question};Axx.chatWorkspace.active.id='another-chat';
        await companion.send('hola');
        const isolatedQuestion=library.learningQuestion===null;
        Axx.chatWorkspace.active.id=origin;library.operation=library.lastOperation={...plan,state:'running'};library.busy=true;
        window.__releaseNaturalPause=true;const delayed=companion.send('ese archivo no');
        while(!window.__finishNaturalPause)await new Promise(resolve=>setTimeout(resolve,0));
        Axx.chatWorkspace.active.id='another-chat';const other={...plan,operation_id:'other-task',conversation_id:'another-chat'};library.operation=library.lastOperation=other;
        window.__finishNaturalPause();await delayed;
        const isolatedResponse=library.lastOperation===other&&library.learningQuestion===null;
        Axx.chatWorkspace.active.id=origin;library.operation=library.lastOperation={...plan,state:'running'};library.busy=true;window.__finishNaturalPause=null;
        const cancelledPause=companion.send('ese archivo no');while(!window.__finishNaturalPause)await new Promise(resolve=>setTimeout(resolve,0));
        await library.cancel();window.__finishNaturalPause();await cancelledPause;
        const cancellationRace=library.lastOperation.state==='cancelled'&&library.learningQuestion===null;
        return {calls,question,deferred,releasedApproval,isolatedQuestion,isolatedResponse,cancellationRace,steps:plan.step_records,local:library.hasLocalIntent('no, ese archivo no'),speechOnly,correctionForMute:library.taskCorrection('silencio')};
      } finally {
        delete window.__releaseNaturalPause;delete window.__finishNaturalPause;Axx.chatWorkspace.active.id=saved.chat;
        Object.assign(library,{operation:saved.operation,lastOperation:saved.lastOperation,busy:saved.busy,generation:saved.generation,observationRevision:saved.observation,cancellingGeneration:saved.cancelling,learningQuestion:saved.question,request:saved.request,renderOperation:saved.render,status:saved.status,notice:saved.notice});companion.message=saved.message;companion.stopSpeech=saved.stopSpeech;companion.data.prefs.voiceRead=saved.voiceRead;companion.syncPreferences();if(saved.voiceExplicit===null)localStorage.removeItem('axx.voice.read.explicit');else localStorage.setItem('axx.voice.read.explicit',saved.voiceExplicit);Axx.skillLibrary.continueTask=saved.continueTask;
      }
    });
    assert.equal(corrections.calls.filter(item=>item[0]==='/axx-api/learning/pause').length,5);
    assert.equal(corrections.calls.filter(item=>item[0]==='/axx-api/learning/resume').length,1);
    assert.equal(corrections.calls.find(item=>item[0]==='/axx-api/learning/resume')[1].approved,false);
    assert.equal(corrections.calls.filter(item=>item[0]==='repair').length,1);
    assert.deepEqual(corrections.calls.find(item=>item[0]==='repair').slice(1),['trial-correction','C:\\destino-correcto\\ensayo.txt']);
    assert.equal(corrections.question.operation_id,'trial-correction');
    assert.equal(corrections.question.conversation_id,'contract-chat');
    assert(corrections.deferred&&corrections.releasedApproval&&corrections.isolatedQuestion&&corrections.isolatedResponse&&corrections.cancellationRace);
    assert.equal(corrections.steps[0].operation_id,'completed-once');assert.equal(corrections.steps[0].result.postconditions_passed,true,'Correction keeps completed operation receipts');
    assert(corrections.calls.some(item=>item[0]==='notice'&&item[1].includes('Selecciona la tarea')));
    assert.equal(corrections.local,true);assert.equal(corrections.correctionForMute,null);assert.deepEqual(corrections.speechOnly,{muted:true,pauses:1});
    results.push('Natural corrections bind exact chat/task, wait for confirmed pause, preserve completed receipts and stale-response isolation; speech mute remains independent');
    assert.equal(await page.evaluate(() => Axx.liveConversation.pauseMs), 700);
    assert.equal(await page.locator('#chat-live-pause').inputValue(), '700');
    results.push('The saved 700 ms voice pause is restored on startup and matches the visible setting');
    const nativeBackground = await page.evaluate(() => [document.documentElement, document.body].map(e => getComputedStyle(e).backgroundColor));
    assert.deepEqual(nativeBackground, ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0)']);
    results.push('Native overlay backgrounds are transparent while the original UI surfaces remain');
    const launcherNavigation = await page.evaluate(() => {
      const body = document.body, launcher = document.getElementById('flow-pill');
      const previous = { step: body.dataset.flowStep, invoked: body.classList.contains('resident-invoked'), hidden: launcher.hidden };
      body.classList.add('resident-invoked'); launcher.hidden = false;
      body.dataset.flowStep = '4'; const panel = getComputedStyle(launcher).display;
      body.dataset.flowStep = '1'; const home = getComputedStyle(launcher).display;
      if (previous.step === undefined) delete body.dataset.flowStep; else body.dataset.flowStep = previous.step;
      body.classList.toggle('resident-invoked', previous.invoked); launcher.hidden = previous.hidden;
      return { panel, home };
    });
    assert.equal(launcherNavigation.panel, 'none');
    assert.notEqual(launcherNavigation.home, 'none');
    results.push('The tool launcher yields to an open panel and returns on the home surface');
    await page.waitForFunction(() => window.__contractLayout?.ready === true);
    const residentStartup = await page.evaluate(() => ({ layout: window.__contractLayout, size: Axx.resident.size, visibleButtons: [...document.querySelectorAll('button')].filter(n => n.getClientRects().length && getComputedStyle(n).visibility !== 'hidden').map(n => n.id) }));
    assert.equal(residentStartup.layout.width, 1920);
    assert.equal(residentStartup.layout.height, 1040);
    assert.equal(residentStartup.layout.stableSurface, true);
    assert.deepEqual(residentStartup.visibleButtons, []);
    await page.setViewportSize({ width: 1920, height: 1040 });
    const startupPng = await page.screenshot({ omitBackground: true });
    const alpha = await page.evaluate(async encoded => {
      const image = new Image(); image.src = 'data:image/png;base64,' + encoded; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
      const context = canvas.getContext('2d'); context.drawImage(image, 0, 0); const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const r = document.getElementById('stage').getBoundingClientRect(); let paintedOutside = 0, paintedBody = 0;
      // Ignore only the 1/255 alpha rounding fringe of the canvas blur filter.
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) if (data[(y * canvas.width + x) * 4 + 3] > 1) { if (x < r.left || x >= r.right || y < r.top || y >= r.bottom) paintedOutside++; else paintedBody++; }
      return { paintedOutside, paintedBody };
    }, startupPng.toString('base64'));
    if (alpha.paintedOutside) {
      fs.writeFileSync(path.join(__dirname, '../../build/desktop-alpha-failure.png'), startupPng);
      console.error('Startup alpha mismatch', alpha, await page.evaluate(() => ({stage: document.getElementById('stage').getBoundingClientRect().toJSON()})));
    }
    assert.equal(alpha.paintedOutside, 0); assert(alpha.paintedBody > 100);
    results.push('Resident startup paints only the real liquid canvas on a transparent, stable monitor surface');
    await page.evaluate(() => Axx.flow.select('chat'));
    await page.waitForFunction(() => window.__contractLayout.width > Axx.resident.size + 100);
    const expanded = await page.evaluate(() => window.__contractLayout);
    await page.setViewportSize({ width: expanded.width, height: expanded.height });
    await page.waitForFunction(() => document.getElementById('panel').getBoundingClientRect().width >= 400);
    assert(await page.evaluate(() => { const p = document.getElementById('panel').getBoundingClientRect(); return p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight; }));
    assert.equal(await page.evaluate(() => Axx.resident.size), residentStartup.size);
    await page.evaluate(() => Axx.resident.fold());
    await page.waitForFunction(() => window.__contractLayout.width === 1920);
    await page.setViewportSize({ width: residentStartup.layout.width, height: residentStartup.layout.height });
    await page.locator('#panel').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('#panel').isVisible(), false);
    results.push('Opening and closing chat preserves the monitor surface and avatar size');
    const bodyPoint = await page.evaluate(() => {
      const r = document.getElementById('avatar').getBoundingClientRect();
      for (let radius = 0; radius < 100; radius += 5) for (let angle = 0; angle < Math.PI * 2; angle += .3) { const x = r.left + r.width / 2 + Math.cos(angle) * radius, y = r.top + r.height / 2 + Math.sin(angle) * radius; if (Axx.app.renderer.hitTest(x, y)) return { x, y }; }
      return null;
    });
    assert(bodyPoint);
    await page.mouse.move(bodyPoint.x, bodyPoint.y); await page.mouse.down(); await page.mouse.move(bodyPoint.x + 20, bodyPoint.y + 14); await page.mouse.up();
    await page.waitForFunction(() => window.__contractCalls.some(c => c.name === 'desktop_move_body'));
    const dragCalls = await page.evaluate(() => window.__contractCalls.filter(c => c.name === 'desktop_move_body'));
    assert.equal(dragCalls.length, 1);
    assert.equal(await page.evaluate(() => Axx.flow.nav.step), 0);
    results.push('Dragging the opaque body invokes native body movement once and releasing opens no tool');
    await page.setViewportSize({ width: 1440, height: 960 });
    assert.equal(await page.evaluate(() => Axx.FORMS.length), 24);
    assert.equal(await page.evaluate(() => Axx.PALETTES.length), 9);
    assert.equal(await page.evaluate(() => Axx.companion.brain.connected), false);
    assert.match(await page.locator('#ai-status').textContent(), /No hay modelos disponibles/);
    results.push('24 forms and 9 palettes retained; empty models remain disconnected');
    for (const providerState of ['missing_key', 'disabled']) {
      const guarded = await page.evaluate(async state => {
        window.__contractModels = ['contract-fixture-model']; window.__contractProviderState = state;
        await Axx.companion.connect();
        return { connected: Axx.companion.brain.connected, models: Axx.companion.brain.models, verified: Axx.companion.brain.inferenceVerified };
      }, providerState);
      assert.equal(guarded.connected, false); assert.deepEqual(guarded.models, []); assert.equal(guarded.verified, false);
    }
    results.push('A nonempty catalog with missing_key or disabled metadata exposes no usable model and remains disconnected');
    await page.evaluate(() => { window.__contractProviderState = 'ready_locally'; });
    await page.evaluate(async () => { window.__contractModels = ['contract-fixture-model']; await Axx.companion.connect(); });
    assert.equal(await page.evaluate(() => Axx.companion.brain.inferenceVerified), false);
    const inference = await page.evaluate(async () => {
      const brain = Axx.companion.brain, prefs = Axx.companion.data.prefs;
      const result = await brain.chat(prefs, [{ role: 'user', content: 'contract only' }], new AbortController().signal, () => {});
      return { result, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat') };
    });
    assert.equal(inference.calls.length, 1);
    assert.equal(inference.calls[0].args.body.stream, false);
    assert.equal(inference.result.route.elapsed_ms, 17);
    results.push('Chat sends exactly one native JSON request and preserves actual route metadata');
    const cancelled = await page.evaluate(async () => {
      window.__contractHoldChat = true;
      const ctrl = new AbortController();
      const pending = Axx.companion.brain.chat(Axx.companion.data.prefs, [{ role: 'user', content: 'cancel contract only' }], ctrl.signal, () => {});
      setTimeout(() => ctrl.abort(), 20);
      try { await pending; return { error: 'not cancelled' }; }
      catch (e) { return { error: e.name, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat/cancel') }; }
    });
    assert.equal(cancelled.error, 'AbortError'); assert.equal(cancelled.calls.length, 1);
    results.push('Cancellation emits one correlated cancellation request and rejects late response');
    // Exercise the actual send wrappers and BrainClient, not just BrainClient.chat:
    // voice metadata previously disappeared in the command resolver, and send
    // referenced an undeclared options variable before reaching the model.
    const conversationTurns = await page.evaluate(async () => {
      const c = Axx.companion, savedPrefs = { ...c.data.prefs }, savedModels = [...window.__contractModels];
      const savedLive = Axx.symbiosis.liveActive, savedForce = c._forceVoiceReplyOnce;
      const requests = () => window.__contractCalls.filter(call => call.args?.path === '/axx-api/chat');
      const speechBefore = window.__contractCalls.filter(call => call.args?.path === '/axx-api/speech/synthesize').length;
      window.__contractHoldChat = false;
      try {
        window.__contractModels = ['contract-fixture-model', 'contract-voice-model'];
        Object.assign(c.data.prefs, { model: 'contract-fixture-model', apiConnection: 'contract-fixture', voiceModel: 'contract-voice-model', voiceApiConnection: 'contract-fixture', voiceRead: false, mutedAll: true });
        Axx.symbiosis.liveActive = false; c._forceVoiceReplyOnce = false;
        await c.connect();
        const baseSignature = c.brain.signature, baseConnection = c.brain.connectionSignature;
        const turn = async (text, metadata) => {
          const before = requests().length, firstMessage = c.data.messages.length;
          // Omitting the second argument is intentional: keyboard sends must
          // remain valid independently of live voice state or metadata.
          if (metadata === undefined) await c.send(text); else await c.send(text, metadata);
          return { text, requests: requests().slice(before).map(call => call.args.body), messages: c.data.messages.slice(firstMessage).map(({ role, text, status, model, source }) => ({ role, text, status, model, source })), pending: Boolean(c.pending), signature: c.brain.signature, connection: c.brain.connectionSignature };
        };
        const text = await turn('¿Qué significa resiliencia?');
        const voice = await turn('¿Qué significa empatía?', { source: 'voice' });
        const textAfterVoice = await turn('¿Qué significa paciencia?');
        c.data.prefs.voiceModel = 'not-in-the-verified-catalog';
        const unknownVoiceModel = await turn('¿Qué significa curiosidad?', { source: 'voice' });
        c.data.prefs.voiceModel = 'contract-voice-model'; c.data.prefs.voiceApiConnection = 'different-unverified-connection';
        const legacyVoiceConnection = await turn('¿Qué significa gratitud?', { source: 'voice' });
        const beforeChangedConnection = requests().length;
        let changedConnectionError = '';
        try { await c.brain.chat({ ...c.data.prefs, model: 'contract-voice-model', apiConnection: 'different-unverified-connection' }, [{ role: 'user', content: 'Contract connection boundary' }], new AbortController().signal, () => {}); }
        catch (error) { changedConnectionError = String(error.message); }
        const changedConnection = { error: changedConnectionError, requests: requests().slice(beforeChangedConnection), signature: c.brain.signature, connection: c.brain.connectionSignature };
        return { text, voice, textAfterVoice, unknownVoiceModel, legacyVoiceConnection, changedConnection, baseSignature, baseConnection, models: [...c.brain.models], speechDelta: window.__contractCalls.filter(call => call.args?.path === '/axx-api/speech/synthesize').length - speechBefore };
      } finally {
        for (const key of Object.keys(c.data.prefs)) if (!Object.hasOwn(savedPrefs, key)) delete c.data.prefs[key];
        Object.assign(c.data.prefs, savedPrefs); window.__contractModels = savedModels;
        Axx.symbiosis.liveActive = savedLive; c._forceVoiceReplyOnce = savedForce;
        await c.connect(); c.save();
      }
    });
    assert.deepEqual(conversationTurns.models, ['contract-fixture-model', 'contract-voice-model']);
    for (const [name, model, voice] of [['text', 'contract-fixture-model', false], ['voice', 'contract-voice-model', true], ['textAfterVoice', 'contract-fixture-model', false], ['legacyVoiceConnection', 'contract-voice-model', true]]) {
      const turn = conversationTurns[name];
      assert.equal(turn.requests.length, 1, name + ' must send exactly one real IPC chat request');
      assert.equal(turn.requests[0].model, model);
      assert.equal(turn.requests[0].provider_name, 'contract-fixture');
      assert.equal(turn.requests[0].stream, false);
      assert.equal(turn.requests[0].max_tokens === 384, voice, name + ' must apply voice brevity only to an explicit voice turn');
      assert.equal(turn.requests[0].messages[0].content, 'Controlled prompt contract: '+(voice?'voice':'conversation'));
      assert(turn.messages.some(message => message.role === 'user' && message.text === turn.text));
      assert(turn.messages.some(message => message.role === 'assistant' && message.text === 'Contract fixture response' && message.model === model && message.status === 'complete'), name + ' must finish with the actual model response');
      assert.equal(turn.pending, false);
      assert.equal(turn.signature, conversationTurns.baseSignature, name + ' must not replace the selected text model signature');
      assert.equal(turn.connection, conversationTurns.baseConnection);
    }
    assert.equal(conversationTurns.speechDelta, 0, 'The model send contract must not play physical audio');
    assert.equal(conversationTurns.text.requests[0].messages[0].role, 'system');
    results.push('Actual companion.send supports text without options and explicit voice through all wrappers, returns model responses, and preserves the text model after a verified voice model turn');
    for (const name of ['unknownVoiceModel']) {
      const turn = conversationTurns[name];
      assert.deepEqual(turn.requests, [], name + ' must not reach an unverified model or connection');
      const response = turn.messages.find(message => message.role === 'assistant' && message.status === 'error');
      assert(response, name + ' must report a visible error');
      assert.match(response.text, /Conecta|verifica|conexión|modelo/);
      assert.doesNotMatch(response.text, /ReferenceError|options is not defined/);
      assert.equal(turn.pending, false);
      assert.equal(turn.signature, conversationTurns.baseSignature);
      assert.equal(turn.connection, conversationTurns.baseConnection);
    }
    assert.deepEqual(conversationTurns.changedConnection.requests, [], 'Another connection must be rejected before IPC dispatch');
    assert.match(conversationTurns.changedConnection.error, /Conecta|verifica|conexión|modelo/);
    assert.equal(conversationTurns.changedConnection.signature, conversationTurns.baseSignature);
    assert.equal(conversationTurns.changedConnection.connection, conversationTurns.baseConnection);
    results.push('Voice rejects uncatalogued models, ignores legacy route overrides, and BrainClient rejects another connection before model dispatch');
    const voiceAction = await page.evaluate(async () => {
      const c = Axx.companion, savedVoiceModel = c.data.prefs.voiceModel, savedMode = c.data.prefs.selection_mode;
      const savedModels = c.brain.models, savedConnected = c.brain.connected;
      const before = window.__contractCalls.length;
      try {
        c.brain.connected = true; c.brain.models = ['contract-fixture-model', 'contract-voice-model'];
        await c.send('/modelo-voz contract-voice-model');
        const selected = c.data.prefs.voiceModel;
        await c.send('/modelo-voz unavailable-model');
        const kept = c.data.prefs.voiceModel;
        window.__contractResolve = { match: 'exact', command_id: 'axx.desktop.installed_app', inputs: { app_id: 'md.obsidian' } };
        await c.send('abre Obsidian', { source: 'voice' });
        await c.send('Oye Axx, por favor podrías abrirme Obsidian', { source: 'voice' });
        window.__contractResolve = { match: 'exact', command_id: 'axx.desktop.window.close', inputs: { window_id: '12', pid: 45 } };
        await c.send('cierra Obsidian', { source: 'voice' });
        window.__contractResolve = { match: 'exact', command_id: 'axx.desktop.search', inputs: { engine: 'google', query: 'youtube' } };
        await c.send('en chrome busca youtube', { source: 'voice' });
        await c.send('And Chrome. Busca YouTube.', { source: 'voice' });
        await c.send('En Chrome Bosca YouTube.', { source: 'voice' });
        await c.send('Me puedes buscar YouTube usando Chrome', { source: 'voice' });
        await c.send('En YouTube búscame gatos', { source: 'voice' });
        const shown = document.getElementById('chat-voice-model')?.value;
        c.data.prefs.selection_mode = 'automatic_free'; Axx.refreshVoiceModelOptions();
        const selector = document.getElementById('chat-voice-model');
        const clearAvailable = !selector.disabled && [...selector.options].some(option => option.value === '');
        selector.value = ''; selector.dispatchEvent(new Event('change'));
        return { selected, kept, shown, clearAvailable, cleared:c.data.prefs.voiceModel,
          calls: window.__contractCalls.slice(before).filter(call => call.name === 'backend_request').map(call => call.args) };
      } finally {
        window.__contractResolve = null; c.data.prefs.voiceModel = savedVoiceModel; c.data.prefs.selection_mode = savedMode;
        c.brain.models = savedModels; c.brain.connected = savedConnected;
        Axx.refreshVoiceModelOptions?.(); c.save();
      }
    });
    assert.equal(voiceAction.selected, 'contract-voice-model');
    assert.equal(voiceAction.kept, 'contract-voice-model');
    assert.equal(voiceAction.shown, 'contract-voice-model');
    assert.equal(voiceAction.clearAvailable, true);
    assert.equal(voiceAction.cleared, '');
    assert.equal(voiceAction.calls.find(call => call.path === '/axx-api/commands/resolve')?.body.source, 'voice');
    assert.equal(voiceAction.calls.find(call => call.path === '/axx-api/commands/prepare')?.body.command_id, 'axx.desktop.installed_app');
    assert.equal(voiceAction.calls.find(call => call.path === '/axx-api/commands/prepare')?.body.inputs.app_id, 'md.obsidian');
    assert(voiceAction.calls.some(call => call.path === '/axx-api/commands/prepare' && call.body.command_id === 'axx.desktop.window.close'));
    assert.equal(voiceAction.calls.filter(call => call.path === '/axx-api/commands/prepare' && call.body.command_id === 'axx.desktop.search').length, 5);
    assert(voiceAction.calls.some(call => call.path === '/axx-api/commands/execute'));
    assert.equal(voiceAction.calls.some(call => call.path === '/axx-api/chat'), false);
    results.push('Voice model selection retains only a catalogued model; an installed-app voice request reaches typed resolve, prepare and execute without model chat');
    const liveRecovery = await page.evaluate(async () => {
      const voice = Axx.symbiosis, original = voice.startListening;
      let restarted = 0;
      try {
        Axx.liveConversation.show();
        voice.startListening = () => { restarted++; };
        voice.liveActive = true;
        voice.dictation.onError('El dictado repitió palabras varias veces. Repite la orden antes de ejecutar una acción.');
        await new Promise(resolve => setTimeout(resolve, 350));
        return { active: voice.liveActive, restarted, status: document.getElementById('live-status').textContent };
      } finally { voice.liveActive = false; voice.startListening = original; }
    });
    assert.equal(liveRecovery.active, true);
    assert.equal(liveRecovery.restarted, 1);
    assert.match(liveRecovery.status, /Escuchando de nuevo/);
    results.push('Live voice recovers from a repeated ASR transcript without silently switching off');
    const unavailableMain = await page.evaluate(async () => {
      const before = window.__contractCalls.length, previous = window.__contractModels;
      window.__contractModels = ['contract-fixture-model'];
      const client = new Axx.BrainClient();
      let error = '';
      try { await client.connect({ provider:'bridge', selection_mode:'manual', apiConnection:'contract-fixture', model:'missing-model' }); }
      catch (cause) { error = cause.message; }
      finally { window.__contractModels = previous; }
      return { error, connected:client.connected, calls:window.__contractCalls.slice(before).map(call=>call.args?.path) };
    });
    assert.match(unavailableMain.error, /missing-model.*contract-fixture-model/);
    assert.equal(unavailableMain.connected, false);
    assert.equal(unavailableMain.calls.includes('/axx-api/chat'), false);
    results.push('An unavailable selected chat model shows the detected alternative and blocks inference');
    const taskFit = await page.evaluate(async () => {
      const c = Axx.companion, prior = { ...c.data.prefs };
      window.__contractProviderRows = [
        { name:'chat-route', model:'chat-model', state:'ready_locally', capabilities:['text'], tasks:['chat'] },
        { name:'vision-route', model:'vision-model', state:'ready_locally', capabilities:['vision'], tasks:['vision'] },
        { name:'plan-route', model:'plan-model', state:'ready_locally', capabilities:['text'], tasks:['plan'] }];
      window.__contractSavedProviders = window.__contractProviderRows.map(({name,model})=>({name,model,enabled:true}));
      try {
        Object.assign(c.data.prefs, { selection_mode:'manual', apiConnection:'chat-route', model:'chat-model', visionConnection:'', visionModel:'' });
        const details = document.getElementById('model-task-fit'); details.open = true; details.dispatchEvent(new Event('toggle'));
        const openClass = document.getElementById('subpanel-api').classList.contains('model-task-open');
        document.getElementById('model-task-kind').value = 'vision';
        await document.getElementById('model-task-check').onclick();
        const root = document.getElementById('model-task-options');
        const before = root.textContent;
        root.querySelector('button').click();
        const chosen = { visionConnection:c.data.prefs.visionConnection, visionModel:c.data.prefs.visionModel, chatModel:c.data.prefs.model,
          reloaded:Axx.decodeCompanion(localStorage.getItem(c.key)).prefs.visionModel };
        const invalidVision = [null, 7, {}, 'x'.repeat(201)].map(visionModel =>
          Axx.decodeCompanion(JSON.stringify({version:4,prefs:{visionConnection:'vision-route',visionModel}})).prefs.visionModel);
        document.getElementById('model-task-kind').value = 'plan';
        await document.getElementById('model-task-check').onclick();
        const plan = { text:root.textContent, buttons:[...root.querySelectorAll('button')].map(button=>button.textContent),
          rejected:await Axx.modelSelection.run({target:'plan-route'}), chatModel:c.data.prefs.model };
        document.getElementById('model-task-kind').value = 'grounding';
        await document.getElementById('model-task-check').onclick();
        details.open = false; details.dispatchEvent(new Event('toggle'));
        return { before, chosen, invalidVision, plan, grounding:root.textContent, openClass };
      } finally {
        Object.assign(c.data.prefs, prior); c.save(); window.__contractProviderRows = null; window.__contractSavedProviders = null;
      }
    });
    assert.match(taskFit.before, /vision-model.*vision-route/);
    assert.doesNotMatch(taskFit.before, /chat-route.*chat-model.*listo localmente/);
    assert.deepEqual(taskFit.chosen, {visionConnection:'vision-route',visionModel:'vision-model',chatModel:'chat-model',reloaded:'vision-model'});
    assert.deepEqual(taskFit.invalidVision, ['', '', '', '']);
    assert.match(taskFit.plan.text, /plan-model.*plan-route/);
    assert.deepEqual(taskFit.plan.buttons, []);
    assert.match(taskFit.plan.rejected, /no declara aptitud para conversar.*chat-route.*chat-model/);
    assert.equal(taskFit.plan.chatModel, 'chat-model');
    assert.equal(taskFit.openClass, true);
    assert.match(taskFit.grounding, /Ningún modelo de Ollama ha superado esa prueba/);
    results.push('Task-aware model panel persists vision separately, rejects a plan-only chat route and does not certify Agent-S grounding');
    const voicePreferences = await page.evaluate(() => {
      const c = Axx.companion, prior = { voiceModel: c.data.prefs.voiceModel, voiceFillers: c.data.prefs.voiceFillers, loadingSound: c.data.prefs.loadingSound };
      const exact = 'catalog/voice:Q4_K_M', boundary = 'v'.repeat(200);
      const decode = prefs => Axx.decodeCompanion(JSON.stringify({ version: 4, prefs }));
      try {
        Object.assign(c.data.prefs, { voiceModel: exact, voiceFillers: true, loadingSound: true }); c.save();
        const saved = localStorage.getItem(c.key), parsed = JSON.parse(saved);
        return {
          empty: Axx.emptyCompanion().prefs.voiceModel,
          exact: decode({ voiceModel: exact }).prefs.voiceModel,
          boundary: decode({ voiceModel: boundary }).prefs.voiceModel,
          invalid: [null, 7, true, {}, []].map(voiceModel => decode({ voiceModel }).prefs.voiceModel),
          oversized: decode({ voiceModel: 'v'.repeat(201) }).prefs.voiceModel,
          legacy: decode({ provider: 'bridge', selection_mode: 'manual', model: 'contract-fixture-model' }).prefs,
          persisted: parsed.prefs.voiceModel,
          reloaded: Axx.decodeCompanion(saved).prefs.voiceModel,
          defaults: [Axx.emptyCompanion().prefs.voiceFillers, Axx.emptyCompanion().prefs.loadingSound],
          savedCues: [parsed.prefs.voiceFillers, parsed.prefs.loadingSound],
          reloadedCues: [Axx.decodeCompanion(saved).prefs.voiceFillers, Axx.decodeCompanion(saved).prefs.loadingSound],
          invalidCues: [decode({ voiceFillers: 'true' }).prefs.voiceFillers, decode({ loadingSound: 1 }).prefs.loadingSound],
          persistError: c.persistError
        };
      } finally { Object.assign(c.data.prefs, prior); c.save(); }
    });
    assert.equal(voicePreferences.empty, '');
    assert.equal(voicePreferences.exact, 'catalog/voice:Q4_K_M');
    assert.equal(voicePreferences.boundary, 'v'.repeat(200));
    assert.deepEqual(voicePreferences.invalid, ['', '', '', '', '']);
    assert.equal(voicePreferences.oversized, '');
    assert.equal(voicePreferences.legacy.voiceModel, '');
    assert.equal(voicePreferences.legacy.model, 'contract-fixture-model');
    assert.equal(voicePreferences.persisted, 'catalog/voice:Q4_K_M');
    assert.equal(voicePreferences.reloaded, voicePreferences.persisted);
    assert.deepEqual(voicePreferences.defaults, [false, false]);
    assert.deepEqual(voicePreferences.savedCues, [true, true]);
    assert.deepEqual(voicePreferences.reloadedCues, [false, false]);
    assert.deepEqual(voicePreferences.invalidCues, [false, false]);
    assert.equal(voicePreferences.persistError, false);
    results.push('Version 4 voice model preferences survive the actual save/decode path exactly, retain legacy defaults, and reject invalid types or names longer than 200 characters');
    const identity = await page.evaluate(() => {
      const app = Axx.app; app.store.data.settings.form = 17; app.store.data.settings.palette = 5; app.store.data.settings.keepForm = true;
      app.refreshIdentity(); app.machine.setConversation('thinking'); app.tick();
      return { saved: JSON.parse(localStorage.getItem('axx-studio-v2')), shown: app.displayForm20('error') };
    });
    assert.equal(identity.saved.form, 17); assert.equal(identity.saved.palette, 5); assert.equal(identity.shown, 17);
    results.push('Task state preserves canonical form and palette');
    await page.evaluate(() => { Axx.companion.openFeature('settings'); document.getElementById('desktop-runtime').scrollIntoView(); });
    await page.locator('#desktop-telemetry').click();
    await page.waitForFunction(() => Axx.desktop.lastOperation?.state === 'succeeded');
    await page.locator('#desktop-runtime details').nth(1).locator('summary').click();
    await page.locator('#desktop-recipe-save').click();
    await page.waitForFunction(() => document.getElementById('desktop-recipes').value === 'consultar-mi-pc');
    await page.locator('#desktop-recipe-run').click();
    await page.waitForFunction(() => window.__contractCalls.some(call => call.args?.path === '/axx-api/recipes/prepare'));
    await page.waitForFunction(() => !Axx.commandLibrary.busy);
    assert.equal(await page.evaluate(() => window.__contractCalls.filter(call => call.args?.path === '/axx-api/recipes/execute').length), 0);
    assert.equal(await page.evaluate(() => Object.keys(window.__contractCalls.filter(call => call.args?.path === '/axx-api/recipes/prepare').at(-1).args.body.inputs).length), 0);
    assert.equal(await page.evaluate(() => Axx.desktop.lastOperation?.state), 'succeeded');
    results.push('Visible action and recipe reuse controls pass through command preparation, preserve verified action IDs and register the real receipt');
    await page.evaluate(() => Axx.companion.send('/comandos estado del sistema'));
    await page.waitForFunction(() => document.getElementById('command-library-select').options.length === 1 && document.getElementById('command-library-select').value === 'axx.system.telemetry');
    assert.equal(await page.locator('#command-library').isVisible(), true);
    assert.match(await page.locator('#command-library-counts').textContent(), /Habilitadas: 1/);
    assert.equal(await page.evaluate(() => Axx.FORMS.length), 24);
    results.push('The command library opens inside the original files tool and exposes live availability without replacing the avatar');
    await page.evaluate(()=>{
      const lib=Axx.commandLibrary,chat=Axx.chatWorkspace.active.id;
      window.__compensationSource={operation_id:'created-proof',command_id:'axx.artifact.write',state:'succeeded',postconditions_passed:true,conversation_id:chat,inputs:{path:'nuevo.txt',content:'Fixture'},output:{path:'C:\\ensayo\\nuevo.txt'},evidence:{creation_receipt:{verified:true}}};
      window.__compensationOriginal=JSON.stringify(__compensationSource);
      window.__compensationPreview={source_operation_id:'created-proof',available:true,action:'quarantine',source_receipt_hash:'e'.repeat(64),task_id:chat,artifact:{path:'C:\\ensayo\\nuevo.txt',bytes:7,sha256:'f'.repeat(64),identity:{volume:'fixture',file_id:'owned',modified:'1'}},compensation:{state:'present',revision:0,quarantine_path:'C:\\ensayo\\.axx-quarantine\\opaque.artifact'},capability:{native_available:true,filesystem_scope:'local_ntfs_only',creation_receipt_required:true}};
      lib.operation=null;lib.busy=false;lib.lastOperation=__compensationSource;lib.renderOperation(__compensationSource);
      window.__compensationExecBefore=__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/execute').length;
    });
    await page.waitForFunction(()=>!document.getElementById('command-library-compensation-review').hidden&&!Axx.commandLibrary.compensationLoading);
    await page.locator('#command-library-compensation-review').click();
    await page.waitForFunction(()=>!document.getElementById('command-library-compensation-prepare').hidden);
    assert.match(await page.locator('#command-library-compensation-status').textContent(),/Apartar archivo nuevo[\s\S]*nuevo.txt[\s\S]*C:\\ensayo\\nuevo.txt/);
    assert.doesNotMatch(await page.locator('#command-library-compensation-status').textContent(),/created-proof|eeeeeeee/,'The human review uses the actual filename/path, with IDs and hashes in details');
    await page.locator('#command-library-compensation-prepare').click();
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.command_id==='axx.artifact.quarantine');
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/execute').length),await page.evaluate(()=>__compensationExecBefore),'Preview and preparation never execute compensation');
    assert.match(await page.locator('#cw-operation>p').first().textContent(),/Apartar archivo nuevo[\s\S]*nuevo.txt/);
    assert.equal(await page.locator('#cw-operation>pre').count(),0,'Opaque command inputs are confined to Details');
    await page.evaluate(()=>{Axx.commandLibrary.clearCompensation();Axx.commandLibrary.renderOperation(Axx.commandLibrary.operation);});
    await page.waitForFunction(()=>Axx.commandLibrary.compensationApprovalMatches(Axx.commandLibrary.operation));
    assert.match(await page.locator('#command-library-preview').textContent(),/C:\\ensayo\\nuevo.txt/,'Reopening approval refreshes its trusted path without stale RAM preview');
    await page.locator('#cw-operation button').filter({hasText:'Aprobar y ejecutar'}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.state==='succeeded'&&Axx.commandLibrary.lastOperation.command_id==='axx.artifact.quarantine');
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/execute').at(-1).args.body.approved),true);
    assert.equal(await page.evaluate(()=>JSON.stringify(__compensationSource)===__compensationOriginal),true,'The historical creation receipt is never rewritten');
    await page.evaluate(()=>Axx.commandLibrary.open());
    await page.waitForFunction(()=>document.getElementById('command-library-compensation-review').textContent==='Revisar archivo apartado'&&!Axx.commandLibrary.compensationLoading);
    await page.locator('#command-library-compensation-review').click();
    await page.waitForFunction(()=>Axx.commandLibrary.compensationReview?.preview.action==='restore');
    const compensationPrepares=await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/compensation-prepare').length);
    await page.evaluate(()=>{__compensationPreview.compensation.revision=3;});
    await page.locator('#command-library-compensation-prepare').click();
    await page.waitForFunction(()=>document.getElementById('command-library-status').textContent.includes('La revisión cambió'));
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/compensation-prepare').length),compensationPrepares,'A changed revision must be shown again before preparation');
    await page.evaluate(()=>{window.__holdCompensationPreview=true;window.__doubleCompensation=Axx.commandLibrary.prepareCompensation();void Axx.commandLibrary.prepareCompensation();});
    await page.waitForFunction(()=>typeof window.__releaseCompensationPreview==='function');
    await page.evaluate(async()=>{__releaseCompensationPreview();delete window.__releaseCompensationPreview;await __doubleCompensation;});
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.compensationReview),null,'A double invocation invalidates its preview');
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/compensation-prepare').length),compensationPrepares);
    await page.evaluate(()=>{const lib=Axx.commandLibrary;lib.renderOperation(lib.lastOperation);});
    await page.waitForFunction(()=>!Axx.commandLibrary.compensationLoading);
    await page.evaluate(()=>{window.__holdCompensationPreview=true;window.__cancelCompensation=Axx.commandLibrary.reviewCompensation();});
    await page.waitForFunction(()=>typeof window.__releaseCompensationPreview==='function');
    const cancelRequests=await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/cancel').length);
    await page.evaluate(()=>Axx.commandLibrary.cancel());
    await page.evaluate(async()=>{__releaseCompensationPreview();delete window.__releaseCompensationPreview;await __cancelCompensation;});
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/cancel').length),cancelRequests,'Discarding a preview never invokes global command cancellation');
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.compensationReview),null);
    await page.evaluate(()=>{const lib=Axx.commandLibrary;lib.lastOperation={...__compensationSource,evidence:{}};lib.renderOperation(lib.lastOperation);});
    assert.equal(await page.locator('#command-library-compensation').isVisible(),false,'Historical writes without creation proof expose no action');
    await page.evaluate(()=>{__compensationPreview.capability.native_available=false;__compensationPreview.available=false;const lib=Axx.commandLibrary;lib.lastOperation=__compensationSource;lib.renderOperation(lib.lastOperation);});
    await page.waitForFunction(()=>!Axx.commandLibrary.compensationLoading);
    assert.equal(await page.locator('#command-library-compensation-review').isVisible(),false,'Unsupported platforms expose no quarantine button');
    await page.evaluate(()=>{__compensationPreview.capability.native_available=true;__compensationPreview.available=true;const lib=Axx.commandLibrary;lib.clearCompensation();lib.renderOperation(lib.lastOperation);});
    await page.waitForFunction(()=>!Axx.commandLibrary.compensationLoading);
    await page.evaluate(()=>{window.__holdCompensationPreview=true;window.__staleCompensation=Axx.commandLibrary.reviewCompensation();});
    await page.waitForFunction(()=>typeof window.__releaseCompensationPreview==='function');
    await page.evaluate(()=>{window.__compensationChat=Axx.chatWorkspace.active.id;Axx.chatWorkspace.active.id='different-compensation-chat';Axx.companion.renderChat();});
    await page.evaluate(async()=>{__releaseCompensationPreview();delete window.__releaseCompensationPreview;await __staleCompensation;});
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.compensationReview),null,'A changed chat discards late filename/path previews');
    await page.evaluate(()=>{Axx.chatWorkspace.active.id=__compensationChat;Axx.companion.renderChat();const lib=Axx.commandLibrary;const operation={operation_id:'uncertain-compensation',command_id:'axx.artifact.quarantine',source_operation_id:'created-proof',conversation_id:__compensationChat,state:'unknown',inputs:{source_operation_id:'created-proof',source_receipt_hash:'e'.repeat(64),expected_revision:3},evidence:{}};__contractCommands[operation.operation_id]=operation;__compensationPreview.available=false;__compensationPreview.action=null;__compensationPreview.compensation.state='unknown';lib.lastOperation=operation;lib.operation=null;lib.renderOperation(operation);Axx.companion.openChat();});
    await page.waitForFunction(()=>document.getElementById('cw-operation').textContent.includes('Conciliar sin repetir'));
    assert.equal(await page.locator('#cw-operation button').filter({hasText:'permitir otra acción'}).count(),0);
    assert.equal(await page.locator('#cw-operation button').filter({hasText:'Cancelar comando'}).count(),0);
    const compensationExecuteBeforeReconcile=await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/execute').length);
    await page.locator('#cw-operation button').filter({hasText:'Conciliar sin repetir'}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.lastOperation.state==='succeeded');
    assert.equal(await page.evaluate(()=>__contractCalls.filter(call=>call.args?.path==='/axx-api/commands/execute').length),compensationExecuteBeforeReconcile,'Reconcile observes the effect without redispatch');
    assert.equal(await page.evaluate(()=>__contractCalls.some(call=>call.args?.path==='/axx-api/commands/review'&&call.args.body.operation_id==='uncertain-compensation')),false);
    results.push('Receipt-bound NTFS compensation exposes filename/path/effect, preserves explicit approval and original receipts, refreshes stale/double/cancel/chat previews, and reconciles unknown without redispatch');
    await page.evaluate(() => { Axx.companion.openFeature('settings'); Axx.companion.openChat(false); });
    await page.waitForFunction(() => Axx.app.panelFocusTimer === null && document.activeElement === document.getElementById('chat-input'));
    const untouchedDraft = await page.locator('#chat-input').inputValue();
    await page.evaluate(() => {
      Axx.companion.openFeature('settings'); Axx.companion.openChat(false);
      const search=document.getElementById('cw-search');search.value='';search.focus();
    });
    // Span both former 50/70 ms timers: a delayed default focus must never
    // redirect the remaining keyboard input into the message draft.
    await page.keyboard.type('Aceptación',{delay:12});
    await page.waitForFunction(() => Axx.app.panelFocusTimer === null);
    assert.equal(await page.locator('#cw-search').inputValue(),'Aceptación');
    assert.equal(await page.evaluate(() => document.activeElement.id),'cw-search');
    assert.equal(await page.locator('#chat-input').inputValue(),untouchedDraft);
    await page.evaluate(() => Axx.companion.openChat(false));
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => document.activeElement.id),'cw-search','Reopening the visible chat preserves the chosen control');
    await page.evaluate(() => { Axx.companion.openFeature('settings'); Axx.companion.openChat(false); Axx.app.closePanel(); });
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(() => Axx.app.panelFocusTimer),null);
    assert.equal(await page.evaluate(() => document.getElementById('panel').hidden),true);
    assert.notEqual(await page.evaluate(() => document.activeElement.id),'chat-input','Closing cancels the pending focus');
    await page.locator('#cw-search').evaluate(el=>{el.value='';el.dispatchEvent(new Event('input',{bubbles:true}));});
    results.push('One opening owns initial focus; immediate history typing, repeated opens and close/navigation cancel stale autofocus without changing the draft');
    await page.evaluate(()=>Axx.companion.openChat(false));
    if(await page.locator('#cw-browse').isVisible())await page.locator('#cw-browse').click();
    await page.locator('#cw-browser').waitFor({state:'visible'});
    const historyLayout=await page.evaluate(()=>{
      const list=document.getElementById('cw-list'),saved=[...list.childNodes],browser=document.getElementById('cw-browser'),savedStyle=browser.getAttribute('style');
      try {
        // The IPC fixture does not resize a real host; constrain this sidebar
        // to the compact native height while retaining the production styles.
        browser.style.height='520px';browser.style.maxHeight='520px';
        list.replaceChildren(...Array.from({length:24},(_,index)=>{
          const button=document.createElement('button');button.className='cw-thread';
          button.textContent='Conversación de prueba '+index;
          const detail=document.createElement('small');detail.textContent='24/10/2026 · Preguntar';button.append(detail);return button;
        }));
        const last=list.lastElementChild.getBoundingClientRect();
        const organize=document.querySelector('#cw-browser .cw-organize').getBoundingClientRect();
        return {lastBottom:last.bottom,organizeTop:organize.top,scrollHeight:browser.scrollHeight,height:browser.clientHeight};
      } finally { list.replaceChildren(...saved);if(savedStyle===null)browser.removeAttribute('style');else browser.setAttribute('style',savedStyle); }
    });
    assert(historyLayout.organizeTop>=historyLayout.lastBottom,'A long history must not overlap group organization controls');
    assert(historyLayout.scrollHeight>historyLayout.height,'Long histories stay reachable through sidebar scrolling: '+JSON.stringify(historyLayout));
    results.push('Long conversation history reserves its full height and scrolls before group controls without overlapping them');
    const localWithoutBackend = await page.evaluate(async () => {
      window.__contractDenyResolver = true;
      const before = window.__contractCalls.filter(call => call.args?.path === '/axx-api/commands/resolve').length;
      await Axx.companion.send('calcula 2 + 3');
      const calculation = Axx.companion.data.messages.at(-1).text;
      await Axx.companion.send('pon un temporizador de diez segundos');
      const timerStarted = Axx.app.store.data.timer?.status;
      await Axx.companion.send('cancelar temporizador');
      const timerCancelled = Axx.app.store.data.timer?.status;
      window.__contractDenyResolver = false;
      return { before, after: window.__contractCalls.filter(call => call.args?.path === '/axx-api/commands/resolve').length, calculation, timerStarted, timerCancelled };
    });
    assert.equal(localWithoutBackend.before, localWithoutBackend.after);
    assert.match(localWithoutBackend.calculation, /5/);
    assert.equal(localWithoutBackend.timerStarted, 'running');
    assert.equal(localWithoutBackend.timerCancelled, 'cancelled');
    results.push('Original calculator and timer start/cancel remain functional with the catalog backend denied');
    await page.evaluate(() => Axx.flow.select('settings'));
    await page.locator('#desktop-memory-query').fill('consultar-mi-pc');
    await page.locator('#desktop-memory-search').click();
    await page.waitForFunction(() => document.getElementById('desktop-memory-result').textContent.includes('"hits"'));
    await page.locator('#desktop-memory-read').click();
    await page.waitForFunction(() => document.getElementById('desktop-memory-result').textContent.includes('Contract full recipe record'));
    results.push('The memory panel exposes real query/read contracts with execution explicitly disallowed');
    await page.evaluate(() => { Axx.resident.fold(); Axx.organic.newWorkspace(); });
    await page.waitForFunction(() => Axx.resident.boxes.some(box => box.id.startsWith('resident-surface-')));
    const organic = await page.evaluate(() => { const box = Axx.resident.boxes.find(box => box.id.startsWith('resident-surface-')); const r = document.getElementById(box.id).getBoundingClientRect(); return { layout: window.__contractLayout, r: { x: r.x, y: r.y, right: r.right, bottom: r.bottom } }; });
    assert(organic.r.x >= 0 && organic.r.y >= 0 && organic.r.right <= organic.layout.width && organic.r.bottom <= organic.layout.height);
    await page.evaluate(() => { for (const id of [...Axx.organic.surfaces.keys()]) Axx.organic.removeSurface(id); Axx.resident.fold(); });
    results.push('New notebook surfaces are included in compact native geometry and remain fully reachable');
    if (await page.evaluate(() => !!Axx.nativeVoice)) {
      await page.evaluate(() => { window.__readerContract = new Axx.SpeechReader(); window.__readerContract.setText('Lectura del contrato local.'); window.__readerContract.play(); });
      await page.waitForFunction(() => window.__readerContract.state === 'ended');
      assert.equal(await page.evaluate(() => Axx.nativeVoice.playback.playing_event && Axx.nativeVoice.playback.ended_event), true);
      const speech = await page.evaluate(() => window.__contractCalls.filter(c => c.args?.path === '/axx-api/speech/synthesize'));
      assert.equal(speech.length, 1); assert.equal(speech[0].args.body.voice, 'Contract fixture voice');
      results.push('Native reader contract decodes a real PCM fixture WAV and receives playing/ended events without physical speaker claims');
      await page.evaluate(()=>{const r=window.__streamReader=new Axx.SpeechReader();window.__streamEnds=0;r.onEnded=()=>window.__streamEnds++;r.setText('Primera frase hablada.');r.awaitingText=true;r.play();});
      await page.waitForFunction(()=>window.__streamReader.state==='waiting');
      assert.equal(await page.evaluate(()=>window.__streamEnds),0);
      await page.evaluate(()=>{const r=window.__streamReader,first=r.chunks.length;r.chunks.push('Segunda frase hablada.');r.jump(first);r.awaitingText=true;r.play();});
      await page.waitForFunction(()=>window.__streamReader.state==='waiting');
      await page.evaluate(()=>Axx.voiceConversation.finish(window.__streamReader));
      assert.equal(await page.evaluate(()=>window.__streamReader.state),'ended');
      assert.equal(await page.evaluate(()=>window.__streamEnds),1);
      results.push('Native SAPI playback waits through model text gaps, resumes the next phrase and signals exactly one final end');

      const asr = await page.evaluate(async () => {
        const session = Axx.nativeVoice.sessions[0], saved = session.owner.onFinal, finals = [];
        session.owner.onFinal = text => finals.push(text); session.lang = 'es-DO';
        session.lastVoiceAt = performance.now() - 1000;
        const before = window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat').length;
        await session.submit(new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm;codecs=opus' }));
        session.owner.onFinal = saved;
        return { finals, before, after: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat').length, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/speech/transcribe'), recognition: Axx.nativeVoice.lastRecognition };
      });
      assert.deepEqual(asr.finals, ['Texto del contrato de ASR']); assert.equal(asr.calls.length, 1); assert.equal(asr.calls[0].args.body.language, 'es'); assert.equal(asr.before, asr.after);
      assert(asr.recognition.duration_ms >= 0 && asr.recognition.speech_end_at_ms > 0);
      assert(asr.recognition.completed_at_ms > asr.recognition.speech_end_at_ms);
      results.push('ASR transport contract normalizes locale, emits confirmed text and never sends the chat automatically');
    }
    await page.setViewportSize({width:1920,height:1040});
    await page.evaluate(resolution=>{
      Axx.commandLibrary.operation=null;Axx.commandLibrary.busy=false;
      window.__contractResolve=resolution;
      Axx.quickReply.write();
    },reviewResolution);
    await page.fill('#quick-input',reviewRequest);
    await page.press('#quick-input','Enter');
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.state==='awaiting_approval');
    const reviewLease=await page.evaluate(()=>window.__contractCalls.filter(c=>c.name==='window_action'&&c.args?.action==='close_panel').length);
    await page.locator('#quick-approval').click();
    await page.waitForFunction(()=>!document.getElementById('panel').hidden&&document.getElementById('panel').dataset.view==='commands');
    assert.equal(await page.locator('#command-library-approve').isVisible(),true);
    assert.equal(await page.locator('#command-library-approve').isEnabled(),true);
    assert.equal(await page.locator('#command-library-preview > li').count(),2);
    assert.equal(await page.evaluate(()=>window.__contractCalls.filter(c=>c.name==='window_action'&&c.args?.action==='close_panel').length),reviewLease);
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.state==='succeeded'&&!Axx.commandLibrary.busy);
    const approvalCalls=await page.evaluate(()=>window.__contractCalls.filter(c=>c.args?.path==='/axx-api/learning/execute'));
    assert.equal(approvalCalls.length,1);assert.equal(approvalCalls[0].args.body.approved,true);
    assert.equal(await page.locator('#command-library-approval').isVisible(),false);
    results.push('Quick bar sequence opens its visible two-step review and its approval button executes exactly once through the normal frontend handler');
    const halo = await page.evaluate(async () => {
      const capture = Axx.nativeCapture, prior = { state: capture.state, region: capture.region, error: capture.error };
      capture.state = 'running'; capture.region = { x: 30, y: 30, width: 400, height: 300 }; capture.haloKey = '';
      window.__contractFailHalo = true;
      const before = window.__contractCalls.filter(c => c.name === 'capture_halo').length;
      capture.halo(); await capture.haloChain; const afterFailure = capture.haloKey;
      capture.halo(); await capture.haloChain;
      const retries = window.__contractCalls.filter(c => c.name === 'capture_halo').length - before;
      const afterSuccess = capture.haloKey;
      Object.assign(capture, prior); capture.halo(); await capture.haloChain;
      return { afterFailure, retries, afterSuccess };
    });
    assert.equal(halo.afterFailure, ''); assert.equal(halo.retries, 2); assert(halo.afterSuccess);
    results.push('Recording halo retries its existing state after capture-affinity contention instead of caching a failed update');
    await page.waitForFunction(() => window.__contractEvents['axx-show']?.length >= 2);
    const hiddenRaster = await page.evaluate(async () => {
      const renderer=Axx.app.renderer;
      const alpha=()=>renderer.ctx.getImageData(0,0,renderer.canvas.width,renderer.canvas.height).data.reduce((n,v,i)=>n+(i%4===3&&v>0?1:0),0);
      renderer.stop();
      const identity=JSON.stringify([Axx.app.store.data.settings,renderer.getStudio(),renderer.angle]);
      const before={pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length};
      try {
        Axx.companion.hide();
        const hidden={pixels:alpha(),raster:renderer.raster.pixels.some((v,i)=>i%4===3&&v>0),mask:renderer.hitMask().bits.filter(Boolean).length,stageHidden:document.getElementById('stage').hidden,quickHidden:document.getElementById('quick-root').hidden,hit:renderer.hitTest(0,0)};
        renderer.resize();renderer.draw(0);renderer.capturePNG();
        const afterCalls={pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length};
        const restore=document.getElementById('restore').getBoundingClientRect(),x=restore.x+restore.width/2,y=restore.y+restore.height/2;
        const restoreMapped=Axx.resident.interactiveRegions().some(r=>x>=r.x&&x<r.x+r.width&&y>=r.y&&y<r.y+r.height);
        Axx.app.setVisible(true);
        return {before,hidden,afterCalls,restoreMapped,restored:{pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length,stageHidden:document.getElementById('stage').hidden},identityPreserved:identity===JSON.stringify([Axx.app.store.data.settings,renderer.getStudio(),renderer.angle])};
      } finally { Axx.app.setVisible(true);renderer.startLoop(); }
    });
    assert(hiddenRaster.before.pixels>100&&hiddenRaster.before.mask>0);
    assert.deepEqual(hiddenRaster.hidden,{pixels:0,raster:false,mask:0,stageHidden:true,quickHidden:true,hit:false});
    assert.deepEqual(hiddenRaster.afterCalls,{pixels:0,mask:0});assert.equal(hiddenRaster.restoreMapped,true);
    assert(hiddenRaster.restored.pixels>100&&hiddenRaster.restored.mask>0);assert.equal(hiddenRaster.restored.stageHidden,false);assert.equal(hiddenRaster.identityPreserved,true);
    results.push('Hidden resident clears actual canvas/raster and native alpha, retains restore input, and redraws immediately without RAF or identity changes');
    const glVisibility=await page.evaluate(()=>{
      const host=document.createElement('div'),canvas=document.createElement('canvas');host.style.cssText='position:fixed;left:20px;top:20px;width:160px;height:160px';canvas.style.cssText='width:160px;height:160px';host.append(canvas);document.body.append(host);
      if(!canvas.getContext('webgl2',{alpha:true,antialias:true,premultipliedAlpha:true,preserveDrawingBuffer:true,powerPreference:'high-performance'})){host.remove();return {available:false};}
      const renderer=new Axx.LiquidRenderer(canvas,{...Axx.app.store.data.settings,staticMode:true});
      const alpha=()=>{const gl=renderer.gl,pixels=new Uint8Array(canvas.width*canvas.height*4);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);return pixels.reduce((n,v,i)=>n+(i%4===3&&v>0?1:0),0);};
      try{
        renderer.draw(0);const before={pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length};renderer.setHidden(true);
        renderer.resize();renderer.draw(1);renderer.capturePNG();
        const hidden={pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length,hit:renderer.hitTest(80,80)};
        renderer.setHidden(false);return {available:true,before,hidden,restored:{pixels:alpha(),mask:renderer.hitMask().bits.filter(Boolean).length}};
      }finally{renderer.stop();host.remove();}
    });
    if(glVisibility.available){assert(glVisibility.before.pixels>100&&glVisibility.before.mask>0);assert.deepEqual(glVisibility.hidden,{pixels:0,mask:0,hit:false});assert(glVisibility.restored.pixels>100&&glVisibility.restored.mask>0);results.push('WebGL framebuffer and offscreen hitmask stay empty through hidden draw/resize/capture and redraw immediately on restore');}
    else console.log('SKIP: WebGL2 unavailable; software renderer visibility validated separately');
    const publicVisibility=await page.evaluate(async()=>{
      const app=Axx.app,original=app.renderer,oldCanvas=original.canvas,parking=document.createElement('div'),results=[];original.stopLoop?.();original.stop?.();
      const flush=async()=>{for(let i=0;i<30&&app.maskInFlight;i++)await new Promise(resolve=>setTimeout(resolve,10));app.lastHitSignature='';await app.updateHitMap();};
      try{for(const kind of ['software','webgl']){
        const canvas=document.createElement('canvas');canvas.id='avatar';oldCanvas.replaceWith(canvas);parking.append(oldCanvas);
        if(kind==='webgl'&&!canvas.getContext('webgl2',{alpha:true,antialias:true,premultipliedAlpha:true,preserveDrawingBuffer:true,powerPreference:'high-performance'})){canvas.replaceWith(oldCanvas);results.push({kind,available:false});continue;}
        const renderer=new (kind==='software'?Axx.SoftwareRenderer:Axx.LiquidRenderer)(canvas,{...app.store.data.settings,staticMode:true});renderer.stopLoop?.();renderer.stop?.();app.renderer=renderer;
        const alpha=()=>{let pixels;if(renderer.gl){const gl=renderer.gl;pixels=new Uint8Array(canvas.width*canvas.height*4);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}else pixels=renderer.ctx.getImageData(0,0,canvas.width,canvas.height).data;return pixels.reduce((n,v,i)=>n+(i%4===3&&v>0?1:0),0);};
        try{app.setVisible(true);Axx.resident.fold();Axx.flow.nav.step=2;Axx.flow.render();document.getElementById('flow-root').classList.remove('flow-invisible');await Axx.resident.layout();renderer.draw(0);const before=alpha();
          const nativeHides=()=>__contractCalls.filter(call=>call.name==='window_action'&&call.args.action==='hide').length,beforeHide=nativeHides();
          document.getElementById('hide-avatar').click();await flush();
          const buttonHidesHost=nativeHides()-beforeHide;app.setVisible(true);app.hide();await flush();const appHidesHost=nativeHides()-beforeHide;
          const restore=document.getElementById('restore'),rect=restore.getBoundingClientRect(),x=rect.x+rect.width/2,y=rect.y+rect.height/2,map=__contractCalls.filter(call=>call.name==='hit_map').at(-1)?.args.map;
          const hidden={pixels:alpha(),bits:renderer.hitMask().bits.filter(Boolean).length,controls:[...document.querySelectorAll('button,input,textarea,select,summary')].filter(node=>node.id!=='restore'&&node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden'&&Number(getComputedStyle(node).opacity)!==0).map(node=>node.id||node.tagName),restoreVisible:!!restore.getClientRects().length,restoreMapped:map?.regions.some(region=>x>=region.x&&x<region.x+region.width&&y>=region.y&&y<region.y+region.height),onlyRestoreMapped:map?.regions.every(region=>region.x>=rect.x-1&&region.y>=rect.y-1&&region.x+region.width<=rect.right+1&&region.y+region.height<=rect.bottom+1),nativeBits:map?.bits.filter(Boolean).length};
          const restored=[];for(const entry of kind==='software'?['restore','summon-main','summon-key','summon-settings','context-summon','companion','home','event']:['core']){app.setVisible(false);if(entry==='core')app.setVisible(true);else if(entry==='companion')Axx.companion.summon();else if(entry==='home')Axx.home18.call();else if(entry==='event')__contractEvents['axx-show'].forEach(fn=>fn({payload:{follow:false}}));else document.getElementById(entry).click();await flush();restored.push({entry,visible:app.machine.visible,hidden:!!(renderer.hidden||renderer.isHidden),pixels:alpha(),nativeBits:__contractCalls.filter(call=>call.name==='hit_map').at(-1)?.args.map.bits.filter(Boolean).length});}
          results.push({kind,available:true,before,hidden,restored,buttonHidesHost,appHidesHost});
        }finally{app.setVisible(true);renderer.stopLoop?.();renderer.stop?.();canvas.replaceWith(oldCanvas);parking.append(canvas);app.renderer=original;}
      }}finally{app.renderer=original;app.setVisible(true);original.startLoop();Axx.resident.fold();}
      return results;
    });
    for(const result of publicVisibility.filter(result=>result.available)){assert(result.before>100);assert.equal(result.buttonHidesHost,0,'The resident hide button must retain the native host for restore');assert.equal(result.appHidesHost,0,'App.hide must not send window.hide in resident mode');assert.deepEqual(result.hidden,{pixels:0,bits:0,controls:[],restoreVisible:true,restoreMapped:true,onlyRestoreMapped:true,nativeBits:0},JSON.stringify(result));for(const entry of result.restored){assert.equal(entry.visible,true,JSON.stringify(result));assert.equal(entry.hidden,false);assert(entry.pixels>100);assert(entry.nativeBits>0);}}
    const nonresidentHide=await page.evaluate(()=>{const resident=Axx.resident,before=__contractCalls.filter(call=>call.name==='window_action'&&call.args.action==='hide').length;try{Axx.resident=null;Axx.app.hide();return __contractCalls.filter(call=>call.name==='window_action'&&call.args.action==='hide').length-before;}finally{Axx.resident=resident;Axx.app.setVisible(true);}});
    assert.equal(nonresidentHide,1,'The non-resident native view preserves its existing window-hide request');
    results.push('Software UI hide/restore/summon buttons and native events plus core software/WebGL visibility synchronously clear alpha and hide controls except restore with the native map, independently of RAF');
    await page.evaluate(() => Axx.companion.hide());
    assert.equal(await page.evaluate(() => document.body.classList.contains('avatar-hidden')), true);
    await page.locator('#restore').click();
    assert.equal(await page.evaluate(() => document.body.classList.contains('avatar-hidden')), false);
    await page.evaluate(() => Axx.companion.hide());
    await page.evaluate(() => window.__contractEvents['axx-show'].forEach(fn => fn({payload:{follow:false}})));
    assert.equal(await page.evaluate(() => document.body.classList.contains('avatar-hidden')), false);
    assert.equal(await page.locator('#restore').isHidden(), true);
    results.push('A native summon event restores the hidden avatar');
    await page.evaluate(() => localStorage.setItem('contract.restore-conflict', '1'));
    await page.reload();
    await page.waitForFunction(() => window.Axx?.desktop?.ready && Axx.chatWorkspace?.ready);
    assert.equal(await page.locator('#restore kbd').textContent(), 'Alt + Mayús + A');
    assert.match(await page.locator('#native-warning').textContent(), /Ctrl\+Alt\+Espacio no disponible/);
    await page.evaluate(() => localStorage.removeItem('contract.restore-conflict'));
    results.push('A conflicting global restore shortcut displays the available fallback');
    await page.addInitScript(() => { window.requestAnimationFrame = () => 1; window.__contractSuppressBackend = true; });
    await page.reload();
    // RAF is deliberately suspended above, so the observer must use an independent clock.
    await page.waitForFunction(() => window.__contractLayout?.ready === true, null, { polling: 50 });
    assert.equal(await page.evaluate(() => Axx.desktop.ready), false);
    assert.equal(await page.evaluate(() => Axx.resident.startup.renderedBody && Axx.resident.startup.readyAcknowledged), true);
    results.push('Transparent first content and native readiness complete even when hidden WebView suspends all RAF and backend readiness remains pending');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ kind: 'CONTROLLED_BROWSER_IPC_CONTRACT', passed: results.length, results, uncaught: errors }, null, 2));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; });
