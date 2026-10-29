/* Controlled browser/IPC references; no native input or installed acceptance. */
const assert=require('node:assert/strict'),path=require('node:path');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<section id="command-library"><button id="command-library-learned"></button></section>');
  await page.evaluate(()=>{
   window.calls=[];window.lessons=[];
   const sample={id:'lesson.'+'a'.repeat(32),command_id:'axx.artifact.write',project_id:'A',task_id:'chat-a',source_operation_id:'failed-operation',source_receipt_sha256:'failure-receipt',symptom:'No se pudo escribir <img src=x>',error_code:'WRITE_FAILED',hypothesis:'El archivo podría estar bloqueado',cause_confirmed:false,cause_status:'unconfirmed_hypothesis',user_correction:'Elegir otro destino',correction_provenance:'confirmed_user',verification:{operation_id:'verified-operation',receipt_sha256:'verified-receipt',status:'verified_test',proves_cause:false},environment_scope:'registered_command_at_recording_not_historical_app_version',environment_matches:true,context_matches:true,status:'reference',permissions_granted:false,preference_inferred:false,allow_provider:false};
   window.sample=sample;window.lessons=[sample,{...sample,id:'foreign',task_id:'chat-b',symptom:'Privado de otro chat'}];
   window.plans=[{operation_id:'parent-plan',kind:'learned_plan',conversation_id:'chat-a',project_id:'A',state:'failed',steps:[{command_id:'axx.artifact.write'},{command_id:'axx.artifact.write'},{command_id:'axx.file.sha256'}],step_records:[{operation_id:'failed-operation',state:'failed',result:{state:'failed',command_id:'axx.artifact.write',error:{message:'Fallo del ensayo'}}},{operation_id:'verified-operation',state:'succeeded',result:{state:'succeeded',command_id:'axx.artifact.write',postconditions_passed:true}},{operation_id:'other-command-proof',state:'succeeded',result:{state:'succeeded',command_id:'axx.file.sha256',postconditions_passed:true}}]},{operation_id:'foreign-plan',kind:'learned_plan',conversation_id:'chat-b',project_id:'A',state:'failed',steps:[{command_id:'axx.artifact.write'}],step_records:[{operation_id:'private-failure',state:'failed',result:{state:'failed',error:{message:'Other chat'}}}]}];
   window.Axx={newId:()=> 'fixture-id',isNative:()=>false,chatWorkspace:{active:{id:'chat-a'}},resident:{schedule(){}},companion:{data:{prefs:{skillProject:'A'}},save(){},openFeature(){},renderChat(){}},commandLibrary:{busy:false,operation:null,request:async(method,route,body)=>{
    calls.push({method,route,body:structuredClone(body)});
    if(route.startsWith('/axx-api/learning/actions?'))return {actions:[]};if(route.startsWith('/axx-api/learning/plans?'))return {plans:structuredClone(plans)};if(route.startsWith('/axx-api/learning/context?'))return {context_meta:{}};
    if(route.startsWith('/axx-api/learning/lessons?')){const params=new URL('http://fixture'+route).searchParams;const result=structuredClone(lessons.filter(row=>row.task_id===params.get('task_id')&&row.project_id===params.get('project_id')));if(window.delayLessons){window.delayLessons=false;await new Promise(resolve=>{window.releaseLessons=resolve;});}return {lessons:result};}
    if(route==='/axx-api/learning/lesson'){if(body.operation_id!=='failed-operation')throw Error('La operación fallida no existe en el diario.');const record={...sample,...body,id:'lesson.'+'b'.repeat(32)};lessons.unshift(record);return structuredClone(record);}
    if(route==='/axx-api/learning/forget-lesson'){lessons=lessons.filter(row=>row.id!==body.id);return {lesson_id:body.id,forgotten:true,command_journal_preserved:true};}
    throw Error('Unsupported fixture route '+route);
   }}};
  });
  await page.addScriptTag({path:path.join(__dirname,'skill-library.js')});
  await page.evaluate(()=>Axx.skillLibrary.tasks());
  await page.locator('#skills-lessons>summary').click();
  await page.waitForFunction(()=>document.querySelectorAll('#skills-lessons-list article').length===1);
  assert.equal(await page.locator('#skills-lessons-list img').count(),0);
  assert.doesNotMatch(await page.locator('#skills-lessons-list').textContent(),/Privado de otro chat/);
  const query=await page.evaluate(()=>{const url=new URL('http://fixture'+calls.find(call=>call.route.startsWith('/axx-api/learning/lessons?')).route);return Object.fromEntries(url.searchParams);});
  assert.deepEqual(query,{project_id:'A',task_id:'chat-a',query:'',command_id:'',limit:'3'},'Server filters exact chat/project before top-three selection');
  await page.locator('#skills-lessons-list details summary').click();
  assert.match(await page.locator('#skills-lessons-list').innerText(),/Hipótesis sin confirmar[\s\S]*Prueba con recibo verificado[\s\S]*no confirma la causa[\s\S]*no certifica la versión histórica[\s\S]*no concede permisos/);
  assert.match(await page.locator('#skills-lessons-list').innerText(),/Uso local; no hay permiso de envío al modelo/);
  await page.locator('#skills-lesson-form').evaluate(form=>form.closest('details').open=true);
  assert.equal(await page.locator('#skills-lesson-form [name=allow_provider]').isChecked(),false,'Saving starts without provider authorization');
  assert.deepEqual(await page.locator('#skills-lesson-form [name=failed_receipt] option').evaluateAll(options=>options.map(option=>option.value)),['','failed-operation']);
  const beforeSelection=await page.evaluate(()=>calls.length);
  await page.locator('#skills-lesson-form [name=failed_receipt]').press('End');
  assert.equal(await page.locator('#skills-lesson-form [name=operation_id]').inputValue(),'failed-operation');
  assert.deepEqual(await page.locator('#skills-lesson-form [name=verified_receipt] option').evaluateAll(options=>options.map(option=>option.value)),['','verified-operation'],'Only real loaded receipts of the selected command are offered');
  await page.locator('#skills-lesson-form [name=verified_receipt]').press('End');
  assert.equal(await page.evaluate(()=>calls.length),beforeSelection,'Receipt selection reuses existing task data without a fetch');
  await page.locator('#skills-lesson-form [name=hypothesis]').fill('Podría estar bloqueado <img src=x>');
  await page.evaluate(()=>{document.querySelector('#skills-lesson-form [name=user_correction]').value='Texto rellenado automáticamente';document.getElementById('skills-lesson-form').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('texto automático'));
  assert.equal(await page.evaluate(()=>calls.some(call=>call.route==='/axx-api/learning/lesson')),false,'Automatic text cannot become confirmed user correction');
  await page.locator('#skills-lesson-form [name=user_correction]').fill('Usar la carpeta autorizada');
  await page.evaluate(()=>{document.querySelector('#skills-lesson-form [name=allow_provider]').checked=true;});
  await page.locator('#skills-lesson-form button').click();
  await page.waitForFunction(()=>document.getElementById('skills-lessons-status').textContent.includes('La hipótesis sigue sin confirmar'));
  assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/lesson').body),{operation_id:'failed-operation',hypothesis:'Podría estar bloqueado <img src=x>',project_id:'A',task_id:'chat-a',allow_provider:false,user_correction:'Usar la carpeta autorizada',verification_operation_id:'verified-operation'},'A programmatically checked control is not provider consent');
  await page.locator('#skills-lesson-form [name=allow_provider]').uncheck();await page.locator('#skills-lesson-form [name=allow_provider]').check();await page.locator('#skills-lesson-form button').click();
  await page.waitForFunction(()=>calls.filter(call=>call.route==='/axx-api/learning/lesson').length===2&&document.getElementById('skills-lessons-status').textContent.includes('La hipótesis sigue sin confirmar'));
  assert.equal(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/lesson').at(-1).body.allow_provider),true,'Only explicit trusted consent enables provider use');
  assert.match(await page.locator('#skills-lessons-list').textContent(),/esta ficha puede enviarse al proveedor configurado/);
  await page.evaluate(()=>{lessons[0].status='stale';lessons[0].context_matches=false;document.getElementById('skills-lessons-search').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('skills-lessons-list').textContent.includes('Referencia desactualizada'));
  assert.equal(await page.locator('#skills-lesson-form [name=allow_provider]').isChecked(),true,'Reference refresh preserves an explicit draft choice');
  assert.equal(await page.locator('#skills-lessons-list img').count(),0);
  await page.locator('#skills-lessons-list article').first().getByRole('button',{name:'Olvidar esta referencia'}).click();
  await page.waitForFunction(()=>document.getElementById('skills-lessons-status').textContent.includes('El historial de ejecución se conserva'));
  assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/forget-lesson').body),{id:'lesson.'+'b'.repeat(32)});
  await page.locator('#skills-lesson-form [name=operation_id]').fill('absent');assert.equal(await page.locator('#skills-lesson-form [name=allow_provider]').isChecked(),false,'Changing the incident resets provider consent');await page.locator('#skills-lesson-form [name=allow_provider]').check();await page.locator('#skills-lesson-form button').click();
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('no existe en el diario'));
  assert.equal(await page.locator('#skills-lesson-form [name=hypothesis]').inputValue(),'Podría estar bloqueado <img src=x>','A rejected receipt preserves the hypothesis draft');
  assert.equal(await page.locator('#skills-lesson-form [name=allow_provider]').isChecked(),true,'A failed save preserves the explicit draft choice');
  await page.evaluate(()=>{window.delayLessons=true;document.getElementById('skills-lessons-search').requestSubmit();});
  await page.waitForFunction(()=>window.releaseLessons);
  await page.evaluate(()=>{Axx.chatWorkspace.active.id='chat-b';Axx.companion.renderChat();});
  assert.equal(await page.locator('#skills-lessons-list').textContent(),'','Changing chat synchronously removes prior references');
  assert.equal(await page.locator('#skills-lesson-form [name=hypothesis]').inputValue(),'','An old draft cannot be recorded under a new chat');
  assert.equal(await page.locator('#skills-lesson-form [name=allow_provider]').isChecked(),false,'A chat change clears prior provider consent');
  await page.evaluate(()=>window.releaseLessons());
  assert.equal(await page.locator('#skills-lessons-list').textContent(),'','Late previous-chat references stay discarded');
  assert.equal(await page.evaluate(()=>calls.some(call=>/execute|cancel|revoke/.test(call.route))),false,'Incident references grant no execution or permission mutation');
  assert.deepEqual(errors,[]);
  console.log('PASS: scoped incident references, loaded receipt selection without fetch, explicit provider consent, human correction provenance, noncausal proof, stale context, forgetting and draft/chat races (controlled IPC)');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
