/** Full HTML + frozen backend + controlled model transport + real file/Windows effects. */
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const http = require('node:http'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');

async function goalUi() {
  const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
  try {
    const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.setContent('<section id="command-library"><button id="command-library-learned"></button></section>');
    await page.evaluate(()=>{
      window.calls=[];window.rendered=[];window.criteria=[{id:'note',kind:'text_exact',parameters:{path:'note.txt',text:'Expected <img src=x>'}},{id:'sheet',kind:'xlsx_from_csv',parameters:{source:'data.csv',destination:'report.xlsx',delimiter:',',numeric_column:'amount'}},{id:'bundle',kind:'file_bundle',parameters:{paths:['note.txt','report.xlsx'],destination:'bundle',archive_name:'result.zip',max_output_bytes:1048576}}];
      const evaluation=criteria.map((criterion,index)=>({id:criterion.id,kind:criterion.kind,status:index===1?'indeterminate':'unsatisfied',reason_code:index===1?'SOURCE_UNAVAILABLE':'OUTPUT_MISSING'}));
      window.baseGoalPlan={kind:'learned_plan',operation_id:'goal-mission',conversation_id:'chat-a',project_id:'A',state:'succeeded',plan_hash:'a'.repeat(64),goal_revision:2,goal_locked:true,goal_spec:{intent:'Deliver the reviewed result',criteria},goal_verification:{passed:false,coverage:'typed_criteria',criteria:evaluation},goal_progress:{status:'pending',criteria:evaluation,prefix_length:1},steps:[{command_id:'axx.artifact.write',inputs:{path:'prefix.txt',content:'Already done'}}],step_records:[{operation_id:'prefix-receipt',state:'succeeded',result:{state:'succeeded',postconditions_passed:true}}],mission:{completed:true,verified_steps:[0],budget:{model_calls_used:1,model_call_limit:2,model_calls_remaining:1}}};
      window.plans=[structuredClone(baseGoalPlan)];let serial=0;
      window.Axx={newId:()=> 'goal-fixture-'+(++serial),isNative:()=>false,chatWorkspace:{active:{id:'chat-a'}},resident:{schedule(){}},companion:{data:{prefs:{skillProject:'A'}},save(){},openFeature(){},renderChat(){}},commandLibrary:{busy:false,operation:null,generation:0,renderOperation(plan){rendered.push(structuredClone(plan));},status(){},open(){},request:async(method,route,body)=>{
        calls.push({method,route,body:structuredClone(body)});
        if(route.startsWith('/axx-api/learning/plans?'))return {plans:structuredClone(plans)};
        if(route.startsWith('/axx-api/learning/actions?'))return {actions:[]};
        if(route.startsWith('/axx-api/learning/context?'))return {context_meta:{}};
        if(route.startsWith('/axx-api/learning/plan?id=')){const plan=structuredClone(plans[0]);if(window.staleGoal){plan.goal_revision++;plan.plan_hash='d'.repeat(64);}return plan;}
        if(route==='/axx-api/learning/propose'){
          const plan={...structuredClone(baseGoalPlan),operation_id:body.operation_id,conversation_id:body.conversation_id,project_id:body.project_id,state:'awaiting_approval',plan_hash:'b'.repeat(64),goal_spec:structuredClone(body.goal_spec)};
          if(window.rewriteGoal)plan.goal_spec.criteria[0].parameters.text='Model replacement';
          if(window.delayPropose){window.delayPropose=false;await new Promise(resolve=>{window.releasePropose=resolve;});}return plan;
        }
        if(route==='/axx-api/learning/repair')return {...structuredClone(plans[0]),state:'awaiting_approval',plan_hash:'b'.repeat(64),goal_spec:structuredClone(body.goal_spec),goal_revision:body.goal_revision+1};
        if(route==='/axx-api/learning/goal-progress'){
          const plan=structuredClone(plans[0]);plan.state='awaiting_approval';plan.plan_hash='b'.repeat(64);plan.goal_progress.status='prepared';plan.steps.push(structuredClone(plan.goal_progress.step));
          if(window.delayProgress){window.delayProgress=false;await new Promise(resolve=>{window.releaseProgress=resolve;});}plans=[plan];return structuredClone(plan);
        }
        throw Error('Unsupported controlled goal route '+route);
      }}};
    });
    await page.addScriptTag({path:path.join(__dirname,'skill-library.js')});
    await page.evaluate(()=>Axx.skillLibrary.tasks());
    const row=page.locator('#skills-tasks article').first();
    await row.evaluate(node=>node.querySelectorAll('details').forEach(details=>details.open=true));
    assert.match(await row.locator(':scope > p').textContent(),/Objetivo pendiente/,'Verified steps cannot override an indeterminate goal');
    assert.match(await row.textContent(),/Indeterminado[\s\S]*typed_criteria[\s\S]*Prefijo conservado: 1[\s\S]*1\/2 llamadas/);
    assert.equal(await row.locator('img').count(),0,'Criteria and expected content are text only');
    assert.equal(await row.getByRole('button',{name:'Preparar siguiente paso',exact:true}).count(),0,'Pending criteria do not invent a producer');
    for(const status of ['waiting_dependency','satisfied','needs_input']){await page.evaluate(status=>{plans[0].goal_progress.status=status;return Axx.skillLibrary.tasks();},status);await row.evaluate(node=>node.querySelectorAll('details').forEach(details=>details.open=true));assert.equal(await row.getByRole('button',{name:'Preparar siguiente paso',exact:true}).count(),0,'A non-ready progress status never prepares a suffix');}
    await page.evaluate(()=>{plans[0].goal_progress.status='pending';plans[0].goal_verification.criteria=criteria.map(criterion=>({id:criterion.id,kind:criterion.kind,status:'satisfied',reason_code:'VERIFIED'}));plans[0].goal_verification.criteria.push({...plans[0].goal_verification.criteria[0],status:'unsatisfied'});return Axx.skillLibrary.tasks();});
    assert.match(await row.locator(':scope > p').textContent(),/Objetivo pendiente/,'Contradictory duplicate evaluations cannot certify completion');
    await page.evaluate(()=>{plans=[structuredClone(baseGoalPlan)];return Axx.skillLibrary.tasks();});await row.evaluate(node=>node.querySelectorAll('details').forEach(details=>details.open=true));
    await page.locator('#skills-goal-editor').evaluate(node=>{node.open=true;node.parentElement.open=true;});
    const raw=await page.evaluate(()=>JSON.stringify(criteria));
    await page.locator('#skills-objective').fill('Deliver a reviewed result');await page.locator('#skills-goal-criteria').fill('[{"id":"x","kind":"python","parameters":{}}]');await page.locator('#skills-goal-review').click();
    await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('Tipo de criterio no disponible'));assert.equal(await page.locator('#skills-goal-prepare').isDisabled(),true,'Human criteria cannot supply an arbitrary evaluator');
    await page.locator('#skills-objective').fill('Deliver a reviewed result');await page.locator('#skills-goal-criteria').fill(raw);
    await page.locator('#skills-goal-review').click();
    assert.equal(await page.locator('#skills-goal-preview img').count(),0);
    await page.locator('#skills-goal-criteria').fill(raw+' ');
    assert.equal(await page.locator('#skills-goal-prepare').isDisabled(),true,'Editing invalidates the previous review');
    await page.locator('#skills-goal-review').click();await page.locator('#skills-goal-prepare').click();
    await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.state==='awaiting_approval');
    assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/propose').body.goal_spec),{intent:'Deliver a reviewed result',criteria:JSON.parse(raw)});
    await page.evaluate(()=>{Axx.commandLibrary.operation=null;window.rewriteGoal=true;});
    await page.locator('#skills-goal-review').click();await page.locator('#skills-goal-prepare').click();
    await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('cambió los criterios'));
    assert.equal(await page.evaluate(()=>Axx.commandLibrary.operation),null,'A model replacement is not adopted for approval');
    await page.evaluate(()=>{window.rewriteGoal=false;Axx.commandLibrary.operation=null;});
    const corrected=JSON.parse(raw);corrected[0].parameters.text='Human correction';
    await row.getByLabel('Criterios corregidos de la misión').fill(JSON.stringify(corrected));await row.getByLabel('Motivo de la corrección de criterios').fill('Use the exact agreed text');
    await row.getByRole('button',{name:'Revisar corrección de criterios',exact:true}).click();
    await page.evaluate(()=>{window.staleGoal=true;});await row.getByRole('button',{name:'Preparar corrección de criterios',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('revisión del objetivo cambió'));
    assert.equal(await page.evaluate(()=>calls.some(call=>call.route==='/axx-api/learning/repair')),false,'A stale goal revision cannot submit a repair');
    await page.evaluate(()=>{window.staleGoal=false;});await row.getByRole('button',{name:'Preparar corrección de criterios',exact:true}).click();
    await page.waitForFunction(()=>calls.some(call=>call.route==='/axx-api/learning/repair')&&Axx.commandLibrary.operation?.state==='awaiting_approval');
    assert.deepEqual(await page.evaluate(()=>{const body=calls.find(call=>call.route==='/axx-api/learning/repair').body;return [body.operation_id,body.goal_revision,body.goal_spec.criteria[0].parameters.text];}),['goal-mission',2,'Human correction']);
    await page.evaluate(()=>{Axx.commandLibrary.operation=null;plans=[structuredClone(baseGoalPlan)];plans[0].state='goal_pending';plans[0].mission.completed=false;Object.assign(plans[0].goal_progress,{status:'ready',criterion_id:'note',fingerprint:'c'.repeat(64),source_plan_hash:plans[0].plan_hash,step:{command_id:'axx.artifact.write',inputs:{path:'note.txt',content:'Expected <img src=x>'}}});return Axx.skillLibrary.tasks();});
    await row.evaluate(node=>node.querySelectorAll('details').forEach(details=>details.open=true));
    await page.evaluate(()=>{window.staleGoal=true;});await row.getByRole('button',{name:'Preparar siguiente paso',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('candidato cambió'));
    assert.equal(await page.evaluate(()=>calls.some(call=>call.route==='/axx-api/learning/goal-progress')),false);
    await page.evaluate(()=>{window.staleGoal=false;});await row.getByRole('button',{name:'Preparar siguiente paso',exact:true}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.plan_hash==='b'.repeat(64));
    assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/goal-progress').body),{operation_id:'goal-mission',plan_hash:'a'.repeat(64),criterion_id:'note',candidate_hash:'c'.repeat(64)});
    assert.deepEqual(await page.evaluate(()=>[Axx.commandLibrary.operation.operation_id,Axx.commandLibrary.operation.step_records,Axx.commandLibrary.operation.mission.budget]),['goal-mission',await page.evaluate(()=>baseGoalPlan.step_records),{model_calls_used:1,model_call_limit:2,model_calls_remaining:1}]);
    await page.evaluate(()=>{Axx.commandLibrary.operation=null;plans[0].state='goal_pending';plans[0].plan_hash='a'.repeat(64);plans[0].goal_progress.status='ready';window.delayProgress=true;return Axx.skillLibrary.tasks();});
    await row.evaluate(node=>node.querySelectorAll('details').forEach(details=>details.open=true));await row.getByRole('button',{name:'Preparar siguiente paso',exact:true}).click();
    await page.waitForFunction(()=>typeof window.releaseProgress==='function');const beforeLate=await page.evaluate(()=>rendered.length);
    await page.evaluate(()=>{Axx.chatWorkspace.active.id='chat-b';document.getElementById('skills-project').value='B';Axx.companion.renderChat();releaseProgress();});
    await page.waitForFunction(()=>!Axx.commandLibrary.busy);assert.equal(await page.evaluate(()=>rendered.length),beforeLate,'A late suffix is not adopted in another chat/project');
    assert.equal(await page.locator('#skills-goal-prepare').isDisabled(),true);
    assert.equal(await page.evaluate(()=>calls.some(call=>/execute/.test(call.route)||call.body?.approved===true)),false,'Goal preparation never approves or executes effects');
    assert.deepEqual(errors,[]);console.log('PASS: typed human criteria, immutable reviewed goal, stale revision/candidate guards, same-mission suffix preparation, preserved prefix/budget, indeterminate status and late chat/project response (controlled IPC only)');
  } finally {await browser.close();}
}

(async () => {
  if(process.argv.includes('--goal-ui'))return goalUi();
  const root = path.resolve(__dirname, '../..');
  const sourceMode = process.argv[2] === '--source';
  const binary = sourceMode ? path.join(root, 'backend/server.py') : path.resolve(process.argv[2] || path.join(root, 'dist/axx-backend.exe'));
  const evidence = path.join(root, 'evidence/action-instructions-20261022');
  fs.mkdirSync(evidence, {recursive:true});
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'axx-learning-e2e-'));
  const target = path.join(workspace, 'artifacts', 'aprendido.txt');
  fs.writeFileSync(path.join(workspace, 'providers.json'), JSON.stringify({allow_paid:false,providers:[]}));
  let modelCalls = 0;
  const modelServer = http.createServer(async (req,res) => {
    const chunks=[]; for await (const chunk of req) chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks).toString()); modelCalls++;
    const user=JSON.parse(body.messages.at(-1).content).request;
    const plan = user.includes('archivo') ? {title:'Saludo comprobado',steps:[
      {command_id:'axx.artifact.write',inputs:{path:'aprendido.txt',content:'Acción ejecutada de verdad.'}},
      {command_id:'axx.file.sha256',inputs:{path:target}}
    ]} : {title:'Diagnóstico aprendido',steps:[{command_id:'axx.system.telemetry',inputs:{}},{command_id:'axx.process.inspect',inputs:{pid:process.pid}}]};
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify({choices:[{message:{role:'assistant',content:JSON.stringify(plan)},finish_reason:'stop'}]}));
  });
  await new Promise(r=>modelServer.listen(0,'127.0.0.1',r));
  const token=crypto.randomBytes(32).toString('hex'), ready=path.join(workspace,'ready.json');
  const log=fs.openSync(path.join(workspace,'backend.log'),'a');
  const backend=spawn(sourceMode?(process.env.AXX_TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe')):binary,[...(sourceMode?[binary]:[]),'--port','0','--data-dir',workspace,'--ready-file',ready],{cwd:root,env:{...process.env,AXX_HOST_TOKEN:token},windowsHide:true,stdio:['ignore',log,log]});
  let browser,server;
  try {
    const deadline=Date.now()+90000;
    while(!fs.existsSync(ready)) {
      if(backend.exitCode!==null || Date.now()>deadline) throw new Error('Backend failed: '+workspace);
      await new Promise(r=>setTimeout(r,100));
    }
    const base='http://127.0.0.1:'+JSON.parse(fs.readFileSync(ready,'utf8')).port;
    const calls=[];
    const request=async({method,path:route,body})=>{
      calls.push(route);
      const response=await fetch(base+route,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
        ...(method==='GET'||body==null?{}:{body:JSON.stringify(body)})});
      const result=await response.json(); if(!response.ok)throw new Error(JSON.stringify(result)); return result;
    };
    await request({method:'POST',path:'/axx-api/providers/save',body:{provider:'ollama',name:'plan-fixture',base_url:'http://127.0.0.1:'+modelServer.address().port,model:'plan-fixture'}});
    server=http.createServer((req,res)=>{
      const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,'../Axx.html');
      res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');res.end(fs.readFileSync(file));
    });
    await new Promise(r=>server.listen(0,'127.0.0.1',r));
    browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
    const page=await browser.newPage({viewport:{width:1200,height:1000}}),errors=[];
    page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
    await page.exposeFunction('nativeTestRequest',request);
    await page.addInitScript(()=>{
      window.__TAURI__={core:{invoke:async(name,args)=>{
        const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
        if(name==='native_status')return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
        if(name==='desktop_layout')return {...desktop,...args};
        if(name==='backend_request')return window.nativeTestRequest(args);
        return null;
      }},event:{listen:async()=>()=>{}}};
    });
    await page.goto('http://127.0.0.1:'+server.address().port);
    await page.waitForFunction(()=>window.Axx?.commandLibrary && window.Axx?.resident?.firstFrame);
    await page.waitForFunction(()=>window.Axx?.chatWorkspace?.ready);
    await page.evaluate(()=>Object.assign(Axx.companion.data.prefs,{provider:'bridge',selection_mode:'manual',apiConnection:'plan-fixture',model:'plan-fixture',voiceRead:false,mutedAll:true}));
    await page.evaluate(()=>Axx.commandLibrary.search('AXX-01-0001'));
    await page.waitForFunction(()=>document.getElementById('command-library-steps').textContent.includes('Windows'));
    console.log('Full imported procedure loaded');

    await page.evaluate(()=>Axx.companion.send('prepara un archivo de saludo y comprueba su hash'));
    let plan=await page.evaluate(()=>Axx.commandLibrary.operation);
    assert.equal(plan?.state,'awaiting_approval',JSON.stringify({status:await page.locator('#command-library-status').textContent(),chat:await page.locator('#chat-log').innerText(),calls}));
    assert.equal(plan.steps.length,2);assert.equal(fs.existsSync(target),false);
    assert.match(await page.locator('#command-library-preview').innerText(),/aprendido.txt/);
    await page.screenshot({path:path.join(evidence,'learning-approval.png')});
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.state==='succeeded');
    assert.equal(fs.readFileSync(target,'utf8'),'Acción ejecutada de verdad.');
    plan=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    assert.equal(plan.results[1].evidence.files[0].sha256,crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex'));
    assert.equal(modelCalls,1);console.log('Model plan executed real write and hash, then saved');

    await page.evaluate(()=>Axx.companion.send('prepara un diagnóstico completo'));
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.state==='succeeded');
    assert.equal(modelCalls,2);
    await page.evaluate(()=>Axx.companion.send('prepara un diagnóstico completo'));
    plan=await page.evaluate(()=>Axx.commandLibrary.operation);
    assert.equal(plan.model_calls_used,0);assert.equal(modelCalls,2);
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.state==='succeeded');
    console.log('Learned workflow repeated without another model call');

    await page.evaluate(()=>Axx.companion.send('abre youtube y buscame un video de gatitos'));
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.state==='succeeded');
    plan=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    assert.equal(plan.state,'succeeded');assert.match(plan.evidence.target,/youtube.com\/results\?search_query=/);
    assert.equal(modelCalls,2);assert.equal(calls.includes('/axx-api/chat'),false);
    const followup=await request({method:'POST',path:'/axx-api/commands/resolve',body:{text:'busca afraid',context:{engine:'youtube'}}});
    assert.equal(followup.inputs.engine,'youtube');
    const slash=await request({method:'POST',path:'/axx-api/commands/resolve',body:{text:'/search youtube afraid'}});
    assert.equal(slash.inputs.query,'afraid');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(evidence,'learning-result.png')});
    const actions=await request({method:'GET',path:'/axx-api/learning/actions'});
    assert.equal(actions.actions.length,2);
    const report={kind:sourceMode?'FULL_HTML_SOURCE_BACKEND_REAL_EFFECTS':'FULL_HTML_FROZEN_BACKEND_REAL_EFFECTS',binary,sha256:crypto.createHash('sha256').update(fs.readFileSync(binary)).digest('hex'),
      model_transport:'controlled local OpenAI-compatible response fixture',modelCalls,learnedActions:actions.actions.length,
      checks:['full procedure details loaded','new request reaches model planner','approval shows exact steps before effects','real file creation and SHA256 verification','learned workflow persisted','repeat executes without model','compound YouTube search handed to Windows','context and slash search resolve correctly','no normal chat inference used','no JavaScript exceptions'],
      limitations:['Tauri IPC emulated by test bridge','Windows browser handoff checked; loaded YouTube page not inspected','Model reasoning quality is not measured by this fixture']};
    fs.writeFileSync(path.join(evidence,'learning-e2e.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  }finally{
    if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));
    await new Promise(r=>modelServer.close(r));
    spawnSync('taskkill',['/F','/T','/PID',String(backend.pid)],{windowsHide:true,stdio:'ignore'});fs.closeSync(log);
  }
})().catch(e=>{console.error(e);process.exitCode=1});
