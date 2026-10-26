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
