/* Controlled UI/IPC checks, not installed or native desktop acceptance. */
const assert=require('node:assert/strict'),path=require('node:path');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<main><section id="command-library"><button id="command-library-learned"></button></section></main>');
  await page.evaluate(()=>{
   window.calls=[];window.serial=0;window.contexts={A:{project_id:'A',context_revision:1,current_folder:'C:\\observado',current_file:'ensayo.txt',current_application:'editor.exe',context_meta:{current_folder:{kind:'observed',origin:'file-event',revision:1,status:'active',source_id:'watcher-1',session_id:'chat-a',observed_at:1000},current_file:{kind:'inferred',origin:'referencia-<img src=x>',revision:1,status:'stale',source_id:'document-1',depends_on:[{field:'current_folder',revision:1}]}},context_tombstones:{}},B:{project_id:'B',context_revision:3,current_folder:'C:\\otro-proyecto',context_meta:{},context_tombstones:{}}};
   window.Axx={newId:()=> 'user-edit-'+(++serial),isNative:()=>false,chatWorkspace:{active:{id:'chat-a'}},resident:{schedule(){}},companion:{data:{prefs:{skillProject:'A'}},save(){},openFeature(){}},commandLibrary:{busy:false,operation:null,request:async(method,route,body)=>{
    calls.push({method,route,body:structuredClone(body)});
    const project=method==='GET'?new URL('http://fixture'+route).searchParams.get('project_id'):body.project_id;
    if(route.startsWith('/axx-api/learning/actions?'))return {actions:[]};
    if(route.startsWith('/axx-api/learning/plans?'))return {plans:[]};
    if(method==='GET'&&route.startsWith('/axx-api/learning/context?')){const response=structuredClone(contexts[project]);if(window.delayContext===project){window.delayContext=null;await new Promise(resolve=>{window.releaseContext=resolve;});}return response;}
    if(route==='/axx-api/learning/context'){
     if(window.saveError)throw Error('No se pudo guardar el contexto.');
     const context=contexts[project],revision=++context.context_revision;
     for(const [field,value] of Object.entries(body.changes))if(field!=='context_meta'){context[field]=value;context.context_meta[field]={...body.changes.context_meta[field],revision,status:'active'};}
     return structuredClone(context);
    }
    if(route==='/axx-api/learning/forget-context'){
     const context=contexts[project],selector=body.source_id?'source_id':'session_id',affected=Object.keys(context.context_meta).filter(field=>context.context_meta[field][selector]===body[selector]);
     for(const field of affected){if(body.forget){delete context[field];delete context.context_meta[field];context.context_tombstones[field]=++context.context_revision;}else context.context_meta[field].status='stale';}
     return structuredClone({...context,invalidated:affected.map(field=>({field,revision:1}))});
    }
    throw Error('Unsupported fixture route '+route);
   }}};
  });
  await page.addScriptTag({path:path.join(__dirname,'skill-library.js')});
  await page.evaluate(()=>Axx.skillLibrary.refresh());
  await page.evaluate(()=>document.querySelector('#skills-folder').closest('details').open=true);
  assert.equal(await page.locator('#skills-folder').inputValue(),'C:\\observado');
  assert.match(await page.locator('#skills-context-evidence').textContent(),/Observado · Activo[\s\S]*Actualidad: no registrada[\s\S]*Inferido · Desactualizado/);
  assert.equal(await page.locator('#skills-context-evidence img').count(),0,'Provenance never inserts markup');
  await page.locator('#skills-save-context').click();
  assert.equal(await page.evaluate(()=>calls.filter(call=>call.method==='POST').length),0,'Reading or automatic filling is not a user confirmation');
  await page.locator('#skills-folder').fill('C:\\confirmado');
  await page.evaluate(()=>Axx.skillLibrary.refresh());
  assert.equal(await page.locator('#skills-folder').inputValue(),'C:\\confirmado','Refresh preserves an unsaved human edit');
  await page.locator('#skills-save-context').click();
  await page.waitForFunction(()=>contexts.A.current_folder==='C:\\confirmado');
  const saved=await page.evaluate(()=>calls.find(call=>call.method==='POST'&&call.route==='/axx-api/learning/context').body);
  assert.deepEqual(Object.keys(saved.changes).sort(),['context_meta','current_folder']);
  assert.deepEqual({...saved.changes.context_meta.current_folder,observed_at:0},{kind:'confirmed_user',origin:'user_settings',source_id:'user-edit-1',session_id:'chat-a',task_id:'chat-a',observed_at:0});
  assert.equal(typeof saved.changes.context_meta.current_folder.observed_at,'number');
  assert.equal(await page.evaluate(()=>contexts.A.context_meta.current_file.kind),'inferred','Unedited inferred fields never become confirmed');
  assert.match(await page.locator('#skills-context-evidence').textContent(),/Confirmado por ti/);
  await page.locator('#skills-file').fill('corregido.txt');
  await page.evaluate(()=>{window.saveError=true;});
  await page.locator('#skills-save-context').click();
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent==='No se pudo guardar el contexto.');
  assert.equal(await page.locator('#skills-file').inputValue(),'corregido.txt','A failed save keeps the correction draft');
  await page.evaluate(()=>{window.saveError=false;});
  await page.locator('#skills-save-context').click();
  await page.waitForFunction(()=>contexts.A.current_file==='corregido.txt');
  await page.evaluate(()=>document.querySelector('#skills-context-origin').closest('details').open=true);
  await page.locator('#skills-context-origin').selectOption(JSON.stringify({session_id:'chat-a'}));
  await page.locator('#skills-invalidate-context').click();
  await page.waitForFunction(()=>contexts.A.context_meta.current_folder.status==='stale');
  assert.deepEqual(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/forget-context').at(-1).body),{project_id:'A',session_id:'chat-a',forget:false});
  assert.equal(await page.locator('#skills-folder').inputValue(),'C:\\confirmado','Invalidating preserves stored value');
  await page.locator('#skills-context-origin').selectOption(JSON.stringify({source_id:'user-edit-1'}));
  await page.locator('#skills-forget-context').click();
  await page.waitForFunction(()=>!Object.hasOwn(contexts.A,'current_folder'));
  assert.deepEqual(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/forget-context').at(-1).body),{project_id:'A',source_id:'user-edit-1',forget:true});
  assert.equal(await page.locator('#skills-folder').inputValue(),'');
  assert.match(await page.locator('#skills-status').textContent(),/permisos y el historial de ejecución se conservan/);
  await page.evaluate(()=>{window.delayContext='A';void Axx.skillLibrary.refresh();});
  await page.waitForFunction(()=>window.releaseContext);
  await page.locator('#skills-project').fill('B');await page.locator('#skills-project').press('Tab');
  await page.waitForFunction(()=>document.getElementById('skills-folder').value==='C:\\otro-proyecto');
  await page.evaluate(()=>{window.releaseContext();});
  await page.waitForFunction(()=>document.getElementById('skills-context-status').textContent.includes('3'));
  assert.equal(await page.locator('#skills-folder').inputValue(),'C:\\otro-proyecto','A late previous-project response cannot replace current context');
  assert.equal(await page.locator('#skills-context-origin option').count(),0);
  assert.equal(await page.locator('#skills-forget-context').isDisabled(),true);
  assert.equal(await page.evaluate(()=>calls.some(call=>/execute|cancel|revoke/.test(call.route))),false,'Context corrections do not execute plans or clear permissions');
  assert.deepEqual(errors,[]);
  console.log('PASS: actual provenance, human-edited fields only, task/session binding, draft retention, scoped invalidation/forget, safe text and project response races (controlled IPC)');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
