/** Controlled UI/IPC contract tests. No microphone, user process or external service is activated. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { requirePlaywright, launchChromium } = require('./test-browser-runtime.cjs');
const { chromium } = requirePlaywright();

(async () => {
  const browser = await launchChromium(chromium);
  const results = [], errors = [];
  try {
    const page = await browser.newPage(); page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<main id="view-files"></main><section id="desktop-runtime"></section><textarea id="chat-input"></textarea>');
    await page.evaluate(() => {
      window.calls = []; window.notices = []; window.fallback = []; window.operations = {}; window.events = {}; window.actions = []; window.cancelledIds = new Set();
      const commands = [
        { id: 'axx.system.telemetry', title: 'Estado del sistema', description: 'Consulta segura', execution_enabled: true, parameters: {}, validation_level: 'IMPLEMENTADO_LOCAL' },
        { id: 'axx.artifact.write', title: 'Crear archivo', execution_enabled: true, parameters: { path: { type: 'string', required: true }, content: { type: 'string', required: true } } },
        { id: 'axx.process.inspect', title: 'Consultar proceso', execution_enabled: true, parameters: { pid: { type: 'integer', required: true } } },
        { id: 'documented.only', title: '<img src=x onerror=window.injected=true>', description: 'Documentado', execution_enabled: false, source_status: 'DOCUMENTED_NOT_EXECUTED', blocked_reason: 'Sin adaptador ejecutable validado', parameters: {} }
      ];
      let serial = 0;
      window.Axx = {
        newId: () => 'fixture-' + (++serial),
        parseIntent: raw => raw.startsWith('calcula ') ? { type: 'calculate' } : null,
        isNative: () => true, resident: { schedule() {} },
        app: { toast: text => notices.push({ role: 'toast', text }), bridge: { listen: async (event, callback) => { window.events[event] = callback; } } },
        voice13: { target: { field: document.getElementById('chat-input') }, applyPending(text) { this.target.field.value = text; } },
        companion: { renderChat() {}, send: async raw => { fallback.push(raw); }, submit: async function () { const field = document.getElementById('chat-input'), text = field.value; field.value = ''; return this.send(text); }, message: (role, text) => notices.push({ role, text }), localNotice: text => notices.push({ role: 'assistant', text }), action: state => actions.push(state), openFeature: id => { window.opened = id; }, openChat() {} },
        backendRequest: async (method, route, body) => {
          calls.push({ method, route, body });
          if (window.errorNext) { const error = window.errorNext; window.errorNext = null; throw new Error(error); }
          if (route.startsWith('/axx-api/commands?')) return { commands, counts: { imported: 1, enabled: 3, blocked: 1, verified_operations: 0 } };
          if (route === '/axx-api/commands/resolve') {
            if (window.holdResolve) await new Promise(resolve => setTimeout(resolve, 100));
            if (body.text === 'estado del sistema') return { match: 'exact', command_id: 'axx.system.telemetry', inputs: {} };
            if (body.text === 'crear archivo') return { match: 'exact', command_id: 'axx.artifact.write', inputs: { path: 'prueba.txt', content: 'Contenido' } };
            if (body.text.startsWith('/comando documented.only')) return { match: 'exact', command_id: 'documented.only', inputs: {} };
            if (body.text === 'varios') return { match: 'ambiguous', candidates: commands.slice(0, 2) };
            return { match: 'none' };
          }
          if (route === '/axx-api/commands/prepare') {
            if (window.holdPrepare) await new Promise(resolve => setTimeout(resolve, 100));
            const operation_id = body.operation_id;
            const state = cancelledIds.has(operation_id) ? 'cancelled' : body.command_id === 'axx.artifact.write' ? 'awaiting_approval' : body.command_id === 'documented.only' ? 'blocked' : 'prepared';
            const operation = { operation_id, command_id: body.command_id, inputs: body.inputs, state, requires_approval: state === 'awaiting_approval', ...(state === 'blocked' ? { error: { code: 'NO_ADAPTER', message: 'Sin adaptador ejecutable validado' } } : {}) };
            operations[operation_id] = operation; return operation;
          }
          if (route === '/axx-api/commands/execute') {
            const operation = operations[body.operation_id];
            if (operation.requires_approval && body.approved !== true) throw new Error('Approval required');
            if (window.holdExecution) await new Promise(resolve => { window.releaseExecution = resolve; });
            if (body.operation_id === window.rejectOperationId) throw new Error('Old execution transport rejected');
            if (window.uncertainExecute) { window.uncertainExecute = false; operation.state = 'succeeded'; operation.postconditions_passed = true; throw new Error('Transport lost'); }
            operation.state = 'succeeded'; operation.postconditions_passed = !window.failPostconditions;
            return { ...operation, evidence: { contract_fixture: true } };
          }
          if (route === '/axx-api/commands/cancel') { if (window.holdCancelBeforeMutation) await new Promise(resolve => { window.releaseCancelBeforeMutation = resolve; }); if (body.operation_id) cancelledIds.add(body.operation_id); for (const operation of Object.values(operations)) if ((!body.operation_id || operation.operation_id === body.operation_id) && ['prepared', 'awaiting_approval', 'running'].includes(operation.state)) operation.state = 'cancelled'; if (window.holdCancel) await new Promise(resolve => { window.releaseCancel = resolve; }); return window.terminalCancel && body.operation_id ? structuredClone(operations[body.operation_id]) : { cancelled: true }; }
          if (route.startsWith('/axx-api/commands/operations?')) { const operation = structuredClone(operations[new URLSearchParams(route.split('?')[1]).get('operation_id')]); if (window.holdRecovery) await new Promise(resolve => { window.releaseRecovery = resolve; }); return { operation }; }
          throw new Error('Unsupported fixture route: ' + route);
        }
      };
    });
    await page.addScriptTag({ path: path.join(__dirname, 'command-library.js') });
    assert.equal(await page.locator('#command-library').count(), 1);
    await page.evaluate(() => Axx.commandLibrary.search('información del sistema'));
    assert.equal(await page.evaluate(() => calls[0].route), '/axx-api/commands?q=informaci%C3%B3n%20del%20sistema&limit=30&offset=0');
    assert.match(await page.locator('#command-library-counts').textContent(), /Importadas: 1 · Habilitadas: 3 · Bloqueadas: 1/);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    results.push('Catalog search encodes Spanish text, displays source/runtime counts, and renders catalog content as text');

    await page.selectOption('#command-library-select', 'documented.only');
    assert.equal(await page.locator('#command-library-prepare').isDisabled(), true);
    assert.match(await page.locator('#command-library-availability').textContent(), /Sin adaptador ejecutable validado/);
    await page.evaluate(() => Axx.companion.send('/comando documented.only {}'));
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), 0);
    results.push('Documented commands stay blocked in selection and explicit text dispatch emits no execute request');

    await page.evaluate(() => Axx.companion.send('estado del sistema'));
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), 1);
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/prepare')).at(-1).body.command_id), 'axx.system.telemetry');
    assert.match(await page.locator('#command-library-status').textContent(), /completado y verificado/);
    results.push('Exact natural text resolves a command ID, prepares typed inputs and verifies its final receipt');

    await page.evaluate(() => { Axx.voice13.applyPending('estado del sistema'); return Axx.companion.send(document.getElementById('chat-input').value); });
    const voiceCall = await page.evaluate(() => calls.filter(call => call.route.endsWith('/prepare')).at(-1));
    assert.equal(voiceCall.body.source, 'voice'); assert.equal(voiceCall.body.command_id, 'axx.system.telemetry');
    results.push('Text placed by the existing voice controller uses the identical command ID with voice provenance');

    await page.evaluate(() => Axx.companion.send('crear archivo'));
    assert.equal(await page.locator('#command-library-approval').isVisible(), true);
    await page.locator('#chat-input').fill('crear archivo');
    await page.evaluate(() => Axx.companion.submit());
    assert.equal(await page.locator('#chat-input').inputValue(), 'crear archivo');
    await page.locator('#chat-input').fill('Podemos conversar mientras espero');
    await page.evaluate(() => Axx.companion.submit());
    assert.equal(await page.evaluate(() => fallback.at(-1)), 'Podemos conversar mientras espero');
    results.push('Pending approval preserves a second action draft while ordinary conversation remains available');
    const beforeApproval = await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length);
    assert.match(await page.locator('#command-library-preview').innerText(), /Archivo\s+prueba.txt/);
    assert.match(await page.locator('#command-library-preview').innerText(), /Contenido que se guardará/);
    assert.equal(await page.locator('#command-library-approve').textContent(), 'Aprobar y ejecutar 1 paso');
    assert.equal(await page.locator('#command-library-technical').getAttribute('open'), null);
    await page.evaluate(() => Axx.companion.send('sí', { source: 'voice' }));
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), beforeApproval);
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(() => !Axx.commandLibrary.busy);
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).at(-1).body.approved), true);
    results.push('A write requires the visible parameter-bound approval button; spoken yes never approves');
    await page.evaluate(() => Axx.commandLibrary.renderOperation({kind:'learned_plan', operation_id:'review-only', state:'awaiting_approval',
      title:'Continuar tarea', steps:[{command_id:'axx.artifact.write',inputs:{path:'hecho.txt',content:'<img src=x onerror=window.injected=true>'}},
      {command_id:'axx.file.sha256',inputs:{path:'hecho.txt'}}], step_records:[{state:'succeeded'},{state:'pending'}]}));
    assert.match(await page.locator('#command-library-preview').innerText(), /Este paso no se repetirá/);
    assert.equal(await page.locator('#command-library-approve').textContent(), 'Aprobar y ejecutar 1 paso');
    assert.equal(await page.locator('#command-library-preview img').count(), 0);
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), beforeApproval + 1);
    await page.evaluate(() => Axx.commandLibrary.renderOperation(Axx.commandLibrary.lastOperation));
    results.push('Readable approval preserves literal inputs, distinguishes completed steps and never executes while rendering');

    await page.selectOption('#command-library-select', 'axx.process.inspect');
    await page.locator('[name="pid"]').fill('12.5');
    const invalid = await page.evaluate(async () => { try { await Axx.commandLibrary.fromSelection(); return false; } catch { return true; } });
    assert.equal(invalid, true);
    results.push('Typed integer parameters reject fractional input before preparation');

    await page.evaluate(async () => { window.holdPrepare = true; const work = Axx.companion.send('crear archivo'); await new Promise(resolve => setTimeout(resolve, 15)); await Axx.commandLibrary.cancel(); await work; window.holdPrepare = false; });
    assert.equal(await page.locator('#command-library-approval').isVisible(), false);
    assert.equal(await page.evaluate(() => Axx.commandLibrary.operation), null);
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/cancel')).at(-1).body.operation_id === calls.filter(call => call.route.endsWith('/prepare')).at(-1).body.operation_id), true);
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), beforeApproval + 1);
    results.push('Cancellation during prepare targets the preassigned operation ID, discards late approval and executes no late command');

    await page.evaluate(async () => { window.holdResolve = true; const work = Axx.companion.send('estado del sistema'); await new Promise(resolve => setTimeout(resolve, 15)); await Axx.commandLibrary.cancel(); await work; window.holdResolve = false; });
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/execute')).length), beforeApproval + 1);
    results.push('Cancellation while resolving prevents a late exact match from preparing or executing');
    await page.evaluate(() => Axx.companion.send('crear archivo'));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => Axx.commandLibrary.operation === null);
    assert.equal(await page.locator('#command-library-approval').isVisible(), false);
    results.push('Escape invalidates a pending approval and requests cancellation of its exact operation');

    const fallbackBefore = await page.evaluate(() => fallback.length);
    await page.evaluate(() => Axx.companion.send('explica un concepto'));
    assert.equal(await page.evaluate(() => fallback.length), fallbackBefore + 1);
    await page.evaluate(() => Axx.companion.send('varios'));
    assert.equal(await page.evaluate(() => fallback.length), fallbackBefore + 1);
    results.push('Unknown phrases preserve the original chat path; ambiguous command names require explicit selection');

    await page.evaluate(async () => { window.failPostconditions = true; await Axx.companion.send('estado del sistema'); window.failPostconditions = false; });
    assert.match(await page.locator('#command-library-status').textContent(), /sin éxito verificado/);
    assert.equal(await page.evaluate(() => actions.at(-1)), 'error');
    results.push('A succeeded state without verified postconditions never produces success feedback');

    await page.evaluate(async () => { window.uncertainExecute = true; await Axx.companion.send('estado del sistema'); });
    assert.match(await page.locator('#command-library-status').textContent(), /incierto/);
    await page.locator('#command-library-recover').click();
    await page.waitForFunction(() => !Axx.commandLibrary.operation);
    assert.match(await page.locator('#command-library-status').textContent(), /succeeded/);
    results.push('A lost execution response can be recovered by operation ID without re-execution');

    await page.evaluate(async () => {
      const previous=Axx.commandLibrary.lastOperation;
      operations[previous.operation_id]={...previous,state:'unknown',postconditions_passed:false};
      await Axx.commandLibrary.recover();
    });
    assert.equal(await page.evaluate(() => Axx.commandLibrary.operation),null);
    assert.equal(await page.evaluate(() => Axx.commandLibrary.lastOperation.state),'unknown');
    assert.equal(await page.locator('#command-library-prepare').isEnabled(),true);
    results.push('An uncertain effect stays visible after recovery without blocking independent observations');

    await page.evaluate(async () => { window.errorNext = 'Backend HTTP 403: Private session rejected'; await Axx.companion.send('estado del sistema'); });
    assert.match(await page.locator('#command-library-status').textContent(), /403/);
    assert.equal(await page.evaluate(() => fallback.length), fallbackBefore + 1);
    results.push('Authorization errors remain visible and never fall through to inference');
    await page.evaluate(async () => {
      await Axx.companion.send('crear archivo');
      window.holdRecovery = true; window.recoveryWork = Axx.commandLibrary.recover();
    });
    await page.waitForFunction(() => typeof window.releaseRecovery === 'function');
    await page.evaluate(() => { window.holdExecution = true; window.executionWork = Axx.commandLibrary.approve(); });
    await page.waitForFunction(() => typeof window.releaseExecution === 'function');
    const recoveryCalls = await page.evaluate(() => calls.filter(call => call.route.startsWith('/axx-api/commands/operations?')).length);
    await page.evaluate(() => { window.holdRecovery = false; return Axx.commandLibrary.recover(); });
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.startsWith('/axx-api/commands/operations?')).length), recoveryCalls);
    await page.evaluate(async () => { window.holdExecution = false; window.releaseExecution(); await window.executionWork; window.releaseRecovery(); await window.recoveryWork; });
    assert.equal(await page.evaluate(() => Axx.commandLibrary.operation), null);
    assert.equal(await page.evaluate(() => Axx.commandLibrary.lastOperation.state), 'succeeded');
    assert.equal(await page.locator('#command-library-approval').isVisible(), false);
    assert.match(await page.locator('#command-library-status').textContent(), /completado y verificado/);
    results.push('Recovery cannot run during execution and a snapshot requested before approval cannot resurrect stale approval after success');
    await page.evaluate(async () => {
      await Axx.companion.send('crear archivo'); window.holdCancel = true;
      window.cancelWork = Axx.commandLibrary.cancel();
    });
    await page.waitForFunction(() => typeof window.releaseCancel === 'function');
    await page.evaluate(async () => { await Axx.companion.send('estado del sistema'); window.holdCancel = false; window.releaseCancel(); await window.cancelWork; });
    assert.equal(await page.evaluate(() => Axx.commandLibrary.lastOperation.state), 'succeeded');
    assert.match(await page.locator('#command-library-status').textContent(), /completado y verificado/);
    results.push('A delayed cancellation receipt cannot overwrite the result of a newer successful command');
    const resolverCount = await page.evaluate(() => calls.filter(call => call.route.endsWith('/resolve')).length);
    await page.evaluate(async () => { window.errorNext = 'Backend unavailable'; await Axx.companion.send('calcula 2 + 3'); });
    assert.equal(await page.evaluate(() => fallback.at(-1)), 'calcula 2 + 3');
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.endsWith('/resolve')).length), resolverCount);
    await page.evaluate(() => { window.errorNext = null; });
    results.push('Existing local tools bypass the catalog resolver and remain available while the backend is unavailable');
    await page.evaluate(async () => {
      await Axx.companion.send('crear archivo');
      window.holdExecution = true; window.releaseExecution = null;
      window.rejectOperationId = Axx.commandLibrary.operation.operation_id;
      const approve = Axx.commandLibrary.approve.bind(Axx.commandLibrary);
      Axx.commandLibrary.approve = () => { window.approvalWork = approve(); return window.approvalWork; };
    });
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(() => typeof window.releaseExecution === 'function');
    await page.evaluate(async () => {
      await Axx.commandLibrary.cancel(); window.holdExecution = false;
      await Axx.companion.send('estado del sistema'); window.releaseExecution();
      await window.approvalWork.catch(() => {});
    });
    assert.equal(await page.evaluate(() => Axx.commandLibrary.lastOperation.state), 'succeeded');
    assert.match(await page.locator('#command-library-status').textContent(), /completado y verificado/);
    results.push('A real approval-button handler ignores a transport rejection from an older cancelled execution');
    await page.evaluate(async () => {
      window.rejectOperationId = null; await Axx.companion.send('crear archivo');
      window.holdCancelBeforeMutation = true; window.terminalCancel = true;
      window.cancelWork = Axx.commandLibrary.cancel();
    });
    await page.waitForFunction(() => typeof window.releaseCancelBeforeMutation === 'function');
    const pendingCancelGeneration = await page.evaluate(() => Axx.commandLibrary.generation);
    await page.evaluate(() => Axx.commandLibrary.cancel(false));
    assert.equal(await page.evaluate(() => Axx.commandLibrary.generation), pendingCancelGeneration);
    const beforePendingCancelRecovery = await page.evaluate(() => calls.filter(call => call.route.startsWith('/axx-api/commands/operations?')).length);
    await page.evaluate(() => Axx.commandLibrary.recover());
    assert.equal(await page.evaluate(() => calls.filter(call => call.route.startsWith('/axx-api/commands/operations?')).length), beforePendingCancelRecovery);
    await page.evaluate(async () => { window.holdCancelBeforeMutation = false; window.releaseCancelBeforeMutation(); await window.cancelWork; });
    assert.equal(await page.evaluate(() => Axx.commandLibrary.lastOperation.state), 'cancelled');
    assert.equal(await page.evaluate(() => Axx.commandLibrary.operation), null);
    assert.equal(await page.locator('#command-library-approval').isVisible(), false);
    assert.match(await page.locator('#command-library-status').textContent(), /cancelled/);
    results.push('Recovery waits for a pending cancellation receipt and cannot restore approval after confirmed cancellation');

    await page.evaluate(async () => {
      Axx.chatWorkspace={active:{id:'origin-chat'},operationCard(){}};
      Axx.companion.openChat=()=>{};
      const backend=Axx.backendRequest;
      Axx.backendRequest=async(method,route,body)=>{
        const result=await backend(method,route,body);
        if(route==='/axx-api/commands/prepare') result.conversation_id='origin-chat';
        return result;
      };
      await Axx.commandLibrary.prepare('axx.artifact.write',{path:'owned.txt',content:'origin output'},'text');
      window.noticesBeforeChatSwitch=notices.length;
      window.holdExecution=true;window.releaseExecution=null;
      window.originApproval=Axx.commandLibrary.approve();
    });
    await page.waitForFunction(()=>typeof releaseExecution==='function');
    await page.evaluate(async()=>{
      Axx.chatWorkspace.active.id='other-chat';window.holdExecution=false;releaseExecution();await originApproval;
    });
    assert.equal(await page.evaluate(()=>notices.length),await page.evaluate(()=>noticesBeforeChatSwitch));
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.lastOperation.conversation_id),'origin-chat');
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.lastOperation.state),'succeeded');
    results.push('An approved command completing after a chat switch stays in its origin operation without a cross-chat notice');

    const preparationsBeforeSwitch=await page.evaluate(()=>calls.filter(call=>call.route.endsWith('/prepare')).length);
    await page.evaluate(()=>{
      Axx.chatWorkspace.active.id='origin-chat';window.holdResolve=true;
      window.originResolve=Axx.companion.send('estado del sistema');
      Axx.chatWorkspace.active.id='other-chat';
    });
    await page.evaluate(async()=>{await originResolve;window.holdResolve=false;});
    assert.equal(await page.evaluate(()=>calls.filter(call=>call.route.endsWith('/prepare')).length),preparationsBeforeSwitch);
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.busy),false);
    results.push('A resolver response arriving after navigation cannot prepare the old request in the new chat');

    await page.evaluate(async()=>{
      Axx.chatWorkspace.active.id='origin-chat';
      Axx.commandLibrary.operation={kind:'learned_plan',operation_id:'owned-plan',conversation_id:'origin-chat',state:'awaiting_approval',plan_hash:'f'.repeat(64),goal_revision:1,goal_spec:{intent:'Deliver <img src=x>',criteria:[{id:'result',kind:'text_exact',parameters:{path:'result.txt',text:'Exact'}}]},steps:[]};
      Axx.commandLibrary.renderOperation(Axx.commandLibrary.operation);
      window.goalReviewRenderedAsText=document.getElementById('command-library-goal').querySelectorAll('img').length===0&&document.getElementById('command-library-goal').textContent.includes('Deliver <img src=x>');
      Axx.commandLibrary.operation.plan_hash='e'.repeat(64);
      window.beforeUnshownHash=calls.length;
      await Axx.commandLibrary.executePlan();
      window.afterUnshownHash=calls.length;
      Axx.commandLibrary.operation.plan_hash='f'.repeat(64);
      Axx.commandLibrary.renderOperation(Axx.commandLibrary.operation);
      const backend=Axx.backendRequest;
      Axx.backendRequest=async(method,route,body)=>{
        if(route==='/axx-api/learning/resume'){window.reviewedResumeBody=structuredClone(body);return {...Axx.commandLibrary.operation,state:'awaiting_approval'};}
        if(route==='/axx-api/learning/execute'){
          window.approvedPlanBody=structuredClone(body);
          await new Promise(resolve=>{window.releasePlan=resolve;});
          return {kind:'learned_plan',operation_id:body.operation_id,conversation_id:'origin-chat',state:'succeeded',postconditions_passed:true,goal_spec:{criteria:[{id:'result',kind:'text_exact'}]},goal_verification:{criteria:[{id:'result',kind:'text_exact',status:'indeterminate',reason_code:'UNAVAILABLE'}]},mission:{completed:true},message:'Private plan output',results:[]};
        }
        return backend(method,route,body);
      };
      window.noticesBeforePlanSwitch=notices.length;
      await Axx.commandLibrary.resumePlan();
      window.originPlan=Axx.commandLibrary.executePlan();
    });
    await page.waitForFunction(()=>typeof releasePlan==='function');
    assert.equal(await page.evaluate(()=>afterUnshownHash),await page.evaluate(()=>beforeUnshownHash),'A changed hash cannot execute without a new displayed review');
    assert.equal(await page.evaluate(()=>goalReviewRenderedAsText),true,'The actual approval surface exposes the fixed goal as text');
    assert.deepEqual(await page.evaluate(()=>approvedPlanBody),{operation_id:'owned-plan',approved:true,plan_hash:'f'.repeat(64)},'Approval is bound to the displayed plan hash');
    assert.deepEqual(await page.evaluate(()=>reviewedResumeBody),{operation_id:'owned-plan',approved:false,plan_hash:'f'.repeat(64)},'Resume requests review for the known hash without approving');
    await page.evaluate(async()=>{Axx.chatWorkspace.active.id='other-chat';releasePlan();await originPlan;});
    assert.equal(await page.evaluate(()=>notices.length),await page.evaluate(()=>noticesBeforePlanSwitch));
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.lastOperation.conversation_id),'origin-chat');
    assert.notEqual(await page.evaluate(()=>actions.at(-1)),'success','Indeterminate criteria cannot produce success feedback even with completed step metadata');
    results.push('A learned plan completing in another chat does not insert or speak its private output there');
    const spotify = await page.evaluate(async()=>{
      const library=Axx.commandLibrary, old={features:Axx.FEATURES,actions:Axx.actions,music:Axx.nativeMusic,media:Axx.media16,home:Axx.home18,visible:Axx.app.setVisible};
      const session={id:'spotify-session',app:'Spotify.exe',playing:false,title:'Bachata Rosa'};
      try{
        Axx.FEATURES=[{id:'music',title:'Música'}];Axx.actions={select(){},open(){}};
        Axx.nativeMusic={snapshot:{sessions:[session]},selectedId:null,refresh:async()=>{},target(){return session;},async command(action){if(action==='play')session.playing=true;}};
        Axx.media16={source:'local'};Axx.home18={wake(){}};Axx.app.setVisible=()=>{};
        const intent=library.internalAction('Reproduce la canción en Spotify.');
        const message=await library.runInternal(intent);
        return {intent,message,selected:Axx.nativeMusic.selectedId,playing:session.playing};
      }finally{Axx.FEATURES=old.features;Axx.actions=old.actions;Axx.nativeMusic=old.music;Axx.media16=old.media;Axx.home18=old.home;Axx.app.setVisible=old.visible;}
    });
    assert.deepEqual(spotify.intent,{id:'music',verb:'start',app:'spotify'});
    assert.equal(spotify.selected,'spotify-session');assert.equal(spotify.playing,true);assert.match(spotify.message,/Reproducción en curso/);
    results.push('Reproduce Spotify targets its observed Windows media session even when Axx music is local');
    const spotifyCold = await page.evaluate(async()=>{
      const library=Axx.commandLibrary, old={features:Axx.FEATURES,actions:Axx.actions,music:Axx.nativeMusic,media:Axx.media16,home:Axx.home18,visible:Axx.app.setVisible,prepare:library.prepare};
      try{
        Axx.FEATURES=[{id:'music',title:'Música'}];Axx.actions={select(){},open(){}};
        Axx.nativeMusic={snapshot:{sessions:[]},refresh:async()=>{}};Axx.media16={source:'local'};Axx.home18={wake(){}};Axx.app.setVisible=()=>{};
        library.prepare=async(commandId,inputs,source)=>({commandId,inputs,source});
        return await library.runInternal({...library.internalAction('Reproduce Spotify'),source:'voice'});
      }finally{Axx.FEATURES=old.features;Axx.actions=old.actions;Axx.nativeMusic=old.music;Axx.media16=old.media;Axx.home18=old.home;Axx.app.setVisible=old.visible;library.prepare=old.prepare;}
    });
    assert.deepEqual(spotifyCold,{commandId:'axx.desktop.spotify.play',inputs:{},source:'voice'});
    results.push('Spotify without a Windows media session routes to the observed app play button');
    const connectFallback = await page.evaluate(async()=>{
      const old=Axx.companion.data, before=fallback.length;
      Axx.companion.data={prefs:{provider:'chatgpt'}};
      try{await Axx.companion.send('haz clic en el primer vídeo',{source:'voice'});return {fallback:fallback.length-before,learning:calls.filter(call=>call.route==='/axx-api/learning/propose').length};}
      finally{Axx.companion.data=old;}
    });
    assert.equal(connectFallback.fallback,0);assert.equal(connectFallback.learning,1);
    results.push('Unresolved ChatGPT actions prepare an explicit reviewed plan instead of becoming a conversational promise');
    const actionWords=await page.evaluate(()=>['escribe en ChatGPT hola','pulsa Enviar','haz clic en Nuevo chat en ChatGPT','presiona Enviar en Antigravity','ejecuta en CMD: dir','/cmd dir','escribe un poema'].map(value=>Axx.commandLibrary.isActionRequest(value)));
    assert.deepEqual(actionWords,[true,true,true,true,true,true,false]);
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.isActionRequest('Con los muebles seleccionados, hazme una lámina')),true);
    results.push('Desktop interaction verbs route as actions while ordinary creative writing stays in chat');
    const language = await page.evaluate(() => ({
        actions: ['¿Me puedes abrirme Obsidian?', 'Oye Axx, por favor podrías buscarme gatos en YouTube',
            'Quiero escuchar Spotify', 'En YouTube búscame gatos', 'Habre Obsidian'].map(value=>Axx.commandLibrary.isActionRequest(value)),
        protected: ['No abras Spotify','Quiero que no cierres Spotify','Cómo puedo abrir Spotify','Me gustaría saber cómo abrir Spotify'].map(value=>Axx.commandLibrary.isActionRequest(value)),
        media: ['Quiero escuchar Spotify','Pon Spotify en pausa','Necesito que pauses Spotify'].map(value=>Axx.commandLibrary.internalAction(value))
    }));
    assert(language.actions.every(Boolean));
    assert(language.protected.every(value=>value===false));
    assert.deepEqual(language.media,[{id:'music',verb:'start',app:'spotify'},{id:'music',verb:'pause',app:'spotify'},{id:'music',verb:'pause',app:'spotify'}]);
    results.push('Spanish carriers and Spotify paraphrases select actions while negation and informational requests stay protected');
    const contextChecks = await page.evaluate(async () => {
      const library = Axx.commandLibrary, previous = Axx.backendRequest, oldChat = Axx.chatWorkspace?.active?.id;
      const url = 'https://www.youtube.com/results?search_query=Faint+Linkin+Park';
      const contexts = [];
      Axx.backendRequest = async (method, route, body) => {
        if (route === '/axx-api/commands/resolve') { contexts.push(structuredClone(body.context)); return {match:'needs_input',message:'fixture'}; }
        if (route === '/axx-api/commands/prepare') {
          const operation={operation_id:body.operation_id,command_id:body.command_id,inputs:body.inputs,state:'prepared',conversation_id:'song-chat'};
          operations[body.operation_id]=operation;return operation;
        }
        const result = await previous(method, route, body);
        if (route === '/axx-api/commands/execute') return {...result,output:{url},evidence:{verification:'application_url_readback'}};
        return result;
      };
      try {
        Axx.chatWorkspace.active.id = 'song-chat';
        await library.prepare('axx.app.browse',{application:'chrome',url},'text');
        await Axx.companion.send('reprodúcela');
        Axx.chatWorkspace.active.id = 'another-chat';
        await Axx.companion.send('reprodúcela');
        library.actionContext={engine:'youtube',query:'old song'};library.actionContextChat='another-chat';library.actionContextAt=Date.now()-600001;
        await Axx.companion.send('reproduce la cancion');
        return {contexts,recognized:library.isActionRequest('reprodúcela')};
      } finally { Axx.backendRequest=previous;Axx.chatWorkspace.active.id=oldChat; }
    });
    assert.equal(contextChecks.recognized,true);
    assert.equal(contextChecks.contexts[0].query,'Faint Linkin Park');
    assert.equal(contextChecks.contexts[0].application,'chrome');
    assert.deepEqual(contextChecks.contexts.slice(1),[{},{}]);
    results.push('Song followups retain the browser and query only in the same chat for ten minutes');
    const sequence=await page.evaluate(async()=>{
      const previous=Axx.backendRequest,seen=[];
      Axx.commandLibrary.operation=null;Axx.commandLibrary.busy=false;
      Axx.backendRequest=async(method,route,body)=>{
        seen.push({route,body});
        if(route==='/axx-api/commands/resolve')return body.text.startsWith('calcula')?{match:'sequence_request'}:{match:'sequence',steps:[{command_id:'axx.desktop.open_url',inputs:{url:'https://www.youtube.com'}},{command_id:'axx.desktop.search',inputs:{engine:'youtube',query:'Faint'}}]};
        if(route==='/axx-api/learning/prepare'||route==='/axx-api/learning/propose')return {...body,kind:'learned_plan',state:'awaiting_approval',message:'Revisa los dos pasos antes de ejecutar.'};
        return previous(method,route,body);
      };
      try {await Axx.companion.send('abre YouTube y luego busca Faint');return {seen,state:Axx.commandLibrary.operation?.state};}
      finally{Axx.backendRequest=previous;}
    });
    assert.equal(sequence.state,'awaiting_approval');
    assert.equal(sequence.seen.filter(c=>c.route==='/axx-api/learning/prepare').length,1);
    assert.equal(sequence.seen.some(c=>/\/(execute|propose)$/.test(c.route)),false);
    results.push('Explicit sequences use one ordered reviewable plan without calling a model or executing before approval');
    const generalSequence=await page.evaluate(async()=>{
      const previous=Axx.backendRequest,calls=[];Axx.commandLibrary.operation=null;Axx.commandLibrary.busy=false;
      Axx.backendRequest=async(method,route,body)=>{calls.push(route);if(route==='/axx-api/commands/resolve')return {match:'sequence_request'};if(route==='/axx-api/learning/propose')return {...body,kind:'learned_plan',state:'awaiting_approval',message:'Revisa el plan.'};return previous(method,route,body);};
      try{
        for(const text of ['calcula 2+2 y luego abre YouTube','calcula 2+2 y abre YouTube','primero calcula 2+2, abre YouTube','calcula "2 y abre Chrome" y abre YouTube','calcula 2+2\nabre YouTube']){
          Axx.commandLibrary.operation=null;Axx.commandLibrary.busy=false;await Axx.companion.send(text);
        }
        return calls;
      }finally{Axx.backendRequest=previous;}
    });
    assert(generalSequence.includes('/axx-api/learning/propose'));assert(!generalSequence.includes('/axx-api/commands/execute'));
    assert.equal(generalSequence.filter(route=>route==='/axx-api/learning/propose').length,5);
    results.push('A local first clause cannot swallow the remaining sequence; unresolved sequences use the general planner');
    const routing=await page.evaluate(async()=>{
      const previous=Axx.backendRequest,calls=[],c=Axx.companion,data=c.data;
      Axx.backendRequest=async(method,route,body)=>{
        calls.push({route,body});
        if(route==='/axx-api/commands/resolve')return body.text==='crea un informe'?{match:'none'}:{match:'exact',command_id:'axx.artifact.write',parameters:{path:{required:true},content:{required:true}},inputs:{}};
        if(route==='/axx-api/learning/propose')return {...body,kind:'learned_plan',state:'needs_input',message:'¿Qué contenido debe tener el archivo?'};
        return previous(method,route,body);
      };
      try{
        c.data={prefs:{provider:'chatgpt'}};Axx.commandLibrary.operation=null;Axx.commandLibrary.learningQuestion=null;
        await c.send('crea un informe');Axx.commandLibrary.learningQuestion=null;
        await c.send('crea un archivo');
        return {calls,question:Axx.commandLibrary.learningQuestion?.question,weak:Axx.commandLibrary.hasLocalIntent('abre Chrome y busca Faint en YouTube')};
      }finally{Axx.backendRequest=previous;c.data=data;}
    });
    assert.equal(routing.calls.filter(c=>c.route==='/axx-api/learning/propose').length,2);
    assert.equal(routing.question,'¿Qué contenido debe tener el archivo?');assert.equal(routing.weak,false);
    assert(!routing.calls.some(c=>c.route==='/axx-api/commands/execute'));
    results.push('Unknown actions and missing parameters reach the selected model planner, including ChatGPT; no partial execution');
    const attention=await page.evaluate(async()=>{
      const lib=Axx.commandLibrary,previous=Axx.backendRequest,oldProject=Axx.skillLibrary,oldAttention=Axx.anticipation,updates=[],notes=[],acknowledgements=[];
      let selectedProject='project-a',memoryGeneration=2;
      Axx.chatWorkspace.active.id='origin-chat';
      Axx.chatWorkspace.captureMemoryToken=()=>({memory_scope:{task_id:'origin-chat',generation:memoryGeneration},memory_context_id:'original-context',epoch:0});
      Axx.chatWorkspace.isMemoryTokenCurrent=token=>token.memory_scope.generation===memoryGeneration&&token.memory_context_id==='original-context';
      Axx.skillLibrary={project:()=>selectedProject};Axx.anticipation={noteMissionPlan:(plan,context)=>notes.push({plan:structuredClone(plan),context:structuredClone(context)}),acknowledgeMissionResponse:(plan,context)=>acknowledgements.push({operation:plan.operation_id,context:structuredClone(context),notice:structuredClone(notices.at(-1))})};
      Axx.companion.updateMissionAttention=(group,options)=>{updates.push({group:structuredClone(group),options});return true;};
      const base={kind:'learned_plan',state:'awaiting_approval',conversation_id:'origin-chat',project_id:'project-a',goal_revision:1,plan_hash:'a'.repeat(64),memory_scope:{task_id:'origin-chat',generation:2},memory_context_id:'original-context',memory_dependencies:[{task_id:'parent',generation:4}],context_dependencies:[{project_id:'project-a',field:'current_folder',revision:7}],steps:[],mission:{mission_id:'explicit-mission',revision:1,state:'awaiting_approval',completed:false},message:'Revisa el plan solicitado.'};
      Axx.backendRequest=async(method,route,body)=>{
        if(route==='/axx-api/learning/prepare'){const response={...structuredClone(base),operation_id:body.operation_id};if(window.holdAttentionPrepare)await new Promise(resolve=>window.releaseAttentionPrepare=resolve);return response;}
        if(route==='/axx-api/learning/execute')return {...structuredClone(base),operation_id:body.operation_id,state:window.attentionResultState,mission:{...base.mission,state:window.attentionResultState},postconditions_passed:true,message:'Respuesta explícita '+window.attentionResultState,results:[]};
        return previous(method,route,body);
      };
      const noticeStart=notices.length,actionStart=actions.length;
      try{
        lib.operation=null;lib.busy=false;await lib.planAction('Plan solicitado',{steps:[]});
        const preparation={notices:notices.length-noticeStart,actions:actions.slice(actionStart),update:updates.at(-1),note:notes.at(-1)};
        for(const state of ['succeeded','paused','cancelled','rejected']){
          lib.operation={...structuredClone(base),operation_id:'explicit-'+state,state:'awaiting_approval'};lib.busy=false;lib.renderOperation(lib.operation);window.attentionResultState=state;await lib.executePlan();
        }
        const states=updates.map(row=>({category:row.group.category,summary:row.group.summary,solicited:row.options.solicited,scope:row.group.memory_scope,dependencies:row.group.memory_dependencies,context:row.group.memory_context_id,ambient:row.group.context_dependencies}));
        lib.operation=null;window.holdAttentionPrepare=true;const pending=lib.planAction('Old project plan',{steps:[]});while(!window.releaseAttentionPrepare)await Promise.resolve();selectedProject='project-b';const before=updates.length,beforeNotices=notices.length;releaseAttentionPrepare();await pending;
        return {preparation,states,lateUpdates:updates.length-before,lateNotices:notices.length-beforeNotices,notices:notices.slice(noticeStart),actions:actions.slice(actionStart),acknowledgements};
      }finally{lib.operation=null;lib.busy=false;Axx.backendRequest=previous;Axx.skillLibrary=oldProject;Axx.anticipation=oldAttention;delete Axx.companion.updateMissionAttention;delete Axx.chatWorkspace.captureMemoryToken;delete Axx.chatWorkspace.isMemoryTokenCurrent;}
    });
    assert.equal(attention.preparation.notices,1,'A requested preparation still renders its chat notice');
    assert.deepEqual(attention.preparation.actions,['thinking'],'A projected explicit decision does not emit another generic approval');
    assert.equal(attention.preparation.update.group.category,'decision');
    assert.equal(attention.preparation.update.options.solicited,true);
    assert.equal(attention.preparation.update.options.notify,false);
    assert.equal(attention.preparation.note.context.memoryToken.memory_context_id,'original-context');
    assert(attention.states.slice(1).every(row=>row.category==='progress'),'Pending goal, pause, cancellation and rejection are not mission errors');
    assert(attention.states.every(row=>row.context==='original-context'&&row.scope.generation===2&&row.dependencies[0].generation===4&&row.ambient[0].field==='current_folder'));
    assert.match(attention.states[1].summary,/Objetivo pendiente/);
    assert.equal(attention.lateUpdates,0);assert.equal(attention.lateNotices,0);
    assert.equal(attention.notices.length,5,'All requested plan responses retain their notices');
    assert.equal(attention.acknowledgements.length,5);assert(attention.acknowledgements.every(row=>row.notice.role==='assistant'&&row.context.memoryToken.memory_context_id==='original-context'),'Response acknowledgement is requested only after the local notice is rendered, with its original token');
    assert(!attention.actions.includes('error'));
    results.push('Requested mission responses retain notices and captured M9 lineage, update one group without proactive admission, and suppress late project responses');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ kind: 'COMMAND_LIBRARY_UI_IPC_CONTRACT_ONLY', passed: results.length, results, uncaught: errors }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
