// UI -> authenticated HTTP -> generated interpreter -> durable executor -> file acceptance.
const assert=require('node:assert/strict'),path=require('node:path'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
  const child=spawn('python',['-m','backend.tests.workshop_http_fixture'],{env:{...process.env,AXX_TEST_GOAL_CYCLE:'1'},windowsHide:true,stdio:['ignore','pipe','pipe']});let browser;
  try{
    const config=await new Promise((resolve,reject)=>{let text='';child.stdout.on('data',d=>{text+=d;if(text.includes('\n'))resolve(JSON.parse(text.split('\n')[0]));});child.on('exit',c=>reject(Error('Fixture exited '+c)));});
    browser=await chromium.launch({headless:true,executablePath:path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
    const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.exposeFunction('backend',async(method,route,body)=>{
      const response=await fetch('http://127.0.0.1:'+config.port+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
      const data=await response.json();if(!response.ok)throw Error(data.error?.message||'Backend rejected fixture');return data;
    });
    await page.setContent('<div id="panel"><section id="view-commands"></section><section id="view-agent"></section></div>');
    await page.evaluate(()=>{window.Axx={isNative:()=>true,backendRequest:window.backend,chatWorkspace:{active:{id:'task-chat'}},
      companion:{data:{prefs:{}},openFeature(){},openChat(){},send(){}},resident:{schedule(){}},
      commandLibrary:{busy:false,operation:null,request:window.backend,renderOperation(plan){this.lastOperation=plan;},status(){},open(){}}};});
    await page.addScriptTag({path:'1.AXX/scripts/capability-workshop.js'});
    await page.waitForFunction(()=>document.querySelector('#capability-workshop').getAttribute('aria-busy')==='false');
    const initial=await page.evaluate(()=>Axx.backendRequest('POST','/axx-api/learning/propose',{text:'Normaliza este lote y entrega su archivo',conversation_id:'task-chat',operation_id:'goal-ui'}));
    assert.equal(initial.state,'waiting_capability');
    await page.evaluate(plan=>Axx.capabilityWorkshop.openTask(plan),initial);
    await page.getByRole('button',{name:'Aprobar este código y sus contratos',exact:true}).click();
    await page.getByRole('button',{name:'Activar comando aprobado',exact:true}).click();
    await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.state==='awaiting_approval');
    const resumed=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
    assert.equal(resumed.operation_id,initial.operation_id);assert.deepEqual(resumed.goal_spec,initial.goal_spec);
    const result=await page.evaluate(()=>Axx.backendRequest('POST','/axx-api/learning/execute',{operation_id:'goal-ui',approved:true}));
    assert.equal(result.state,'succeeded');assert.equal(result.goal_verification.passed,true);assert.deepEqual(errors,[]);
    console.log(JSON.stringify({result:'GOAL_CYCLE_UI_HTTP_EXECUTOR_PASS',same_goal_id:true,checks:result.goal_verification.checks.length,native_gui_tested:false,uncaught:errors}));
  }finally{await browser?.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
