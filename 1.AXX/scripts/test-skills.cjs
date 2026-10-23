/** Full HTML + frozen backend + controlled model transport + real file/Windows effects. */
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const http = require('node:http'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const sourceMode = process.argv[2] === '--source';
  const binary = sourceMode ? path.join(root, 'backend/server.py') : path.resolve(process.argv[2] || path.join(root, 'dist/axx-backend.exe'));
  const evidence = path.join(root, 'build/automatic-skills-e2e', sourceMode ? 'source' : 'packaged');
  fs.mkdirSync(evidence, {recursive:true});
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'axx-learning-e2e-'));
  const target = path.join(workspace, 'artifacts', 'aprendido.txt');
  fs.writeFileSync(path.join(workspace, 'providers.json'), JSON.stringify({allow_paid:false,providers:[]}));
  let modelCalls = 0;
  const modelServer = http.createServer(async (req,res) => {
    const chunks=[]; for await (const chunk of req) chunks.push(chunk);
    const body=JSON.parse(Buffer.concat(chunks).toString()); modelCalls++;
    let user; try { user=JSON.parse(body.messages.at(-1).content).request; } catch { user=null; }
    if(!user){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{role:'assistant',content:'Contenido nuevo comprobado.'},finish_reason:'stop'}]}));return;}
    const plan = user.includes('archivo') ? {title:'Saludo comprobado',steps:[
      {command_id:'axx.artifact.write',inputs:{path:'aprendido.txt',content:'Acción ejecutada de verdad.'}},
      {command_id:'axx.file.sha256',inputs:{path:target}}
    ]} : {title:'Diagnóstico aprendido',steps:[{command_id:'axx.system.telemetry',inputs:{}},{command_id:'axx.process.inspect',inputs:{}}]};
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify({choices:[{message:{role:'assistant',content:JSON.stringify(plan)},finish_reason:'stop'}]}));
  });
  await new Promise(r=>modelServer.listen(0,'127.0.0.1',r));
  const token=crypto.randomBytes(32).toString('hex'), ready=path.join(workspace,'ready.json');
  const log=fs.openSync(path.join(workspace,'backend.log'),'a');
  const backend=spawn(sourceMode?'py':binary,[...(sourceMode?['-3.14',binary]:[]),'--port','0','--data-dir',workspace,'--ready-file',ready],{cwd:root,env:{...process.env,AXX_HOST_TOKEN:token},windowsHide:true,stdio:['ignore',log,log]});
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
      // The dedicated keyless suite tests discovery; this fixture must stay offline.
      if(route.startsWith('/axx-api/keyless/'))return {state:'ready',tasks:{}};
      const response=await fetch(base+route,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
        ...(method==='GET'||body==null?{}:{body:JSON.stringify(body)})});
      const result=await response.json(); if(!response.ok)throw new Error(JSON.stringify(result)); return result;
    };
    await request({method:'POST',path:'/axx-api/providers/save',body:{provider:'ollama',name:'plan-fixture',base_url:'http://127.0.0.1:'+modelServer.address().port,model:'plan-fixture',free_confirmed:true,billing_allowed:false,route_kind:'direct',cost_evidence:'direct_local',context_window:32768,capabilities:['text'],tasks:['chat','plan','parameters','repair','writing']}});
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

    await page.waitForFunction(()=>window.Axx?.skillLibrary);
    await page.evaluate(()=>Object.assign(Axx.companion.data.prefs,{provider:'bridge',apiConnection:'ignored-pin',model:'ignored-model',selection_mode:'automatic_free',voiceRead:false,mutedAll:true}));
    await page.evaluate(()=>Axx.commandLibrary.planAction('prepara un archivo de saludo'));
    let plan=await page.evaluate(()=>Axx.commandLibrary.operation);
    assert.equal(plan?.state,'awaiting_approval');assert.equal(modelCalls,1);assert.equal(fs.existsSync(target),false);
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.state==='succeeded');
    const first=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    assert.equal(fs.readFileSync(target,'utf8'),'Acción ejecutada de verdad.');
    const {actions}=await request({method:'GET',path:'/axx-api/learning/actions'});
    assert.equal(actions.length,1);
    await request({method:'POST',path:'/axx-api/learning/configure',body:{id:actions[0].id,changes:{examples:['otro saludo'],schema:{type:'object',properties:{filename:{type:'string',description:'Nombre del archivo'}},required:['filename']},templates:[{command_id:'axx.artifact.write',inputs:{path:'{{filename}}',content:'Variante comprobada'}}]}}});
    await page.evaluate(()=>Axx.skillLibrary.open());
    await page.waitForFunction(()=>document.querySelector('#skills-list article'));
    await page.locator('#skills-list').getByRole('button',{name:'Entradas y ejecución'}).click();
    await page.locator('#skills-editor input[type=text]').first().fill('variante.txt');
    await page.locator('#skills-editor').getByRole('button',{name:'Revisar y ejecutar'}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.state==='awaiting_approval');
    plan=await page.evaluate(()=>Axx.commandLibrary.operation);assert.equal(plan.model_calls_used,0);assert.equal(modelCalls,1);
    assert.notEqual(plan.operation_id,first.operation_id);
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.state==='succeeded');
    assert.equal(fs.readFileSync(path.join(workspace,'artifacts','variante.txt'),'utf8'),'Variante comprobada');
    await page.evaluate(()=>Axx.skillLibrary.open());
    await page.waitForFunction(()=>document.querySelectorAll('#skills-tasks article').length>=2);
    await page.screenshot({path:path.join(evidence,'skills-library.png')});
    await request({method:'POST',path:'/axx-api/learning/configure',body:{id:actions[0].id,changes:{schema:{type:'object',properties:{filename:{type:'string'},content:{type:'string'}},required:['filename','content']},templates:[{command_id:'axx.artifact.write',inputs:{path:'{{filename}}',content:'{{content}}'}}],inference:{task:'writing',prompt:'Redacta un saludo breve.',output_parameter:'content'}}}});
    await page.evaluate(()=>Axx.skillLibrary.refresh());
    await page.locator('#skills-list').getByRole('button',{name:'Entradas y ejecución'}).click();
    assert.match(await page.locator('#skills-editor form').innerText(),/se genera/);
    assert.equal(await page.locator('#skills-editor form input').count(),1);
    await page.locator('#skills-editor form input').fill('nuevo.txt');
    await page.locator('#skills-editor').getByRole('button',{name:'Revisar y ejecutar'}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.operation?.state==='awaiting_approval');
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.state==='succeeded');
    assert.equal(fs.readFileSync(path.join(workspace,'artifacts','nuevo.txt'),'utf8'),'Contenido nuevo comprobado.');
    assert.equal(modelCalls,2);
    await page.evaluate(()=>{Axx.companion.data.prefs.skillProject='Office';Axx.companion.save();});
    await page.reload(); await page.waitForFunction(()=>window.Axx?.skillLibrary);
    assert.equal(await page.evaluate(()=>Axx.companion.data.prefs.selection_mode),'automatic_free');
    assert.equal(await page.locator('#skills-project').inputValue(),'Office');
    assert.equal(await page.locator('#provider-selection-mode').inputValue(),'automatic_free');
    await page.evaluate(()=>{Axx.companion.openFeature('ai');document.getElementById('tab-mode-api').click();});
    await page.waitForFunction(()=>!document.getElementById('gateway-start').disabled);
    await page.locator('#gateway-controls').evaluate(node=>node.open=true);
    await page.locator('#gateway-start').click();
    await page.waitForFunction(()=>document.getElementById('gateway-result').textContent.includes('Gateway conectado'));
    const gateway=await request({method:'GET',path:'/axx-api/freellmapi/status'});
    assert.equal(gateway.ownership,'managed');assert.equal(gateway.ready_count,0);
    await page.locator('#gateway-import-source').selectOption('plan-fixture');
    await page.locator('#gateway-import').click();
    await page.waitForFunction(()=>document.getElementById('gateway-result').textContent.includes('Conexión añadida'));
    await page.locator('#gateway-inspect').click();
    await page.waitForFunction(()=>document.querySelector('#gateway-members input'));
    await page.locator('#gateway-members input').first().check();
    await page.locator('#gateway-profiles').click();
    await page.waitForFunction(()=>/perfiles verificados y guardados/.test(document.getElementById('gateway-result').textContent));
    const providers=(await request({method:'GET',path:'/axx-api/providers'})).providers;
    assert(providers.some(p=>p.model==='auto:axx_plan'&&p.gateway_profile_verified),await page.locator('#gateway-result').textContent());
    await request({method:'POST',path:'/axx-api/providers/save',body:{provider:'ollama',name:'plan-fixture',base_url:'http://127.0.0.1:'+modelServer.address().port,model:'plan-fixture',enabled:false}});
    await page.evaluate(()=>Axx.commandLibrary.planAction('prepara un diagnóstico del gateway'));
    const gatewayPlan=await page.evaluate(()=>Axx.commandLibrary.operation);
    assert.equal(gatewayPlan?.state,'awaiting_approval',await page.locator('#command-library-status').textContent());
    assert.equal(gatewayPlan.route.selection_mode,'automatic_free');assert.equal(gatewayPlan.route.configured_model,'auto:axx_plan');
    await page.locator('#command-library-approve').click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.state==='succeeded');
    await request({method:'POST',path:'/axx-api/freellmapi/stop',body:{}});
    assert.equal(errors.length,0,errors.join('\n'));
    fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({mode:sourceMode?'source':'packaged',modelCalls,first:first.operation_id,second:plan.operation_id,checks:['automatic ignores pins','real file effect','parameter variation zero inference','new execution identity','visible task history'],errors},null,2));
    console.log('PASS: automatic mode, real file learning, parameter UI, zero-call reuse, history. Evidence: '+evidence);
  } finally {
    await browser?.close();server?.close();modelServer.close();
    if(backend.exitCode===null)spawnSync('taskkill',['/PID',String(backend.pid),'/T','/F'],{windowsHide:true});
    fs.closeSync(log);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
