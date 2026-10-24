// Real authenticated HTTP/SQLite/executor with deterministic proposal model.
const assert=require('node:assert/strict'),path=require('path'),{spawn}=require('child_process');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
  const child=spawn('python',['-m','backend.tests.workshop_http_fixture'],{windowsHide:true,stdio:['ignore','pipe','pipe']});let browser;
  try{
    const config=await new Promise((resolve,reject)=>{let output='';child.stdout.on('data',d=>{output+=d;if(output.includes('\n'))resolve(JSON.parse(output.split('\n')[0]));});child.stderr.on('data',d=>process.stderr.write(d));child.on('exit',c=>reject(Error('Fixture exited '+c)));});
    browser=await chromium.launch({headless:true,executablePath:path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
    const p=await browser.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
    await p.exposeFunction('backend',async(method,route,body)=>{const r=await fetch('http://127.0.0.1:'+config.port+route,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error?.message||JSON.stringify(data));return data;});
    await p.setContent('<div id="panel"><section id="view-commands"></section><section id="view-agent"></section></div>');
    await p.evaluate(()=>{window.Axx={isNative:()=>true,backendRequest:window.backend,companion:{data:{prefs:{}},openFeature(){},send(){}},commandLibrary:{busy:false,operation:null,renderOperation(p){this.lastOperation=p;},status(){},open(){}},resident:{schedule(){}}};});
    await p.addScriptTag({path:'1.AXX/scripts/capability-workshop.js'});
    await p.waitForFunction(()=>document.querySelector('#capability-workshop').getAttribute('aria-busy')==='false');
    await p.fill('#cap-goal','Consulta el estado del equipo');await p.click('#cap-generate');
    await p.waitForFunction(()=>!!Axx.capabilityWorkshop.current&&!document.querySelector('#cap-generate').disabled);
    assert.match(await p.locator('#cap-editor').innerText(),/Estado del equipo/);
    await p.getByRole('button',{name:'Aprobar esta versión',exact:true}).click();
    await p.getByRole('button',{name:'Preparar prueba',exact:true}).click();
    await p.waitForFunction(()=>!!Axx.commandLibrary.lastOperation?.operation_id&&!document.querySelector('#cap-generate').disabled);
    const plan=await p.evaluate(()=>Axx.commandLibrary.lastOperation);assert.equal(plan.state,'awaiting_approval');
    const result=await p.evaluate(async id=>Axx.backendRequest('POST','/axx-api/learning/execute',{operation_id:id,approved:true}),plan.operation_id);assert.equal(result.state,'succeeded');
    await p.evaluate(()=>Axx.commandLibrary.operation=null);
    await p.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();
    await p.waitForFunction(()=>Axx.capabilityWorkshop.current?.state==='active');
    assert.equal(await p.evaluate(()=>Axx.capabilityWorkshop.current.validation.runtime_verified),true);
    await p.getByRole('button',{name:'Desactivar capacidad',exact:true}).click();
    await p.waitForFunction(()=>Axx.capabilityWorkshop.current?.state==='revoked');
    assert.deepEqual(errors,[]);
    console.log('PASS: workshop proposal UI -> version-bound approval -> real command receipts -> activation -> revoke; no browser exceptions');
  }finally{await browser?.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
