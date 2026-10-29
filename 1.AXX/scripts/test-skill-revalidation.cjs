/* Controlled UI/IPC contracts. Real local executor verification lives in test_revalidation.py. */
const assert=require('node:assert/strict'),path=require('node:path');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<section id="command-library"><button id="command-library-learned"></button></section>');
  await page.evaluate(()=>{
   window.calls=[];window.serial=0;window.context={context_revision:2,current_file:'C:\\ensayo\\actual.txt',context_meta:{current_file:{revision:2,status:'active',kind:'confirmed_user',task_id:'task-a'}}};
   window.skill={id:'skill.hash',version:1,trigger:'skill.hash',title:'Comprobar ensayo',objective:'Comprobar ensayo',intent:'ensayo',templates:[{command_id:'axx.file.sha256',inputs:{path:'{{path}}'}}],schema:{type:'object',properties:{path:{type:'string',default:'C:\\stale\\old.txt'},format:{type:'string',enum:['sha256','other'],default:'sha256'},confirm:{type:'boolean',default:true}},required:['path','confirm']},project_id:'A',favorite:false,environment_matches:false,context_matches:true,quarantined:true,executable:true,inference:null,checks:['executor_postconditions'],examples:[],context_dependencies:[]};
   window.Axx={newId:()=> 'trial-'+(++serial),isNative:()=>false,chatWorkspace:{active:{id:'task-a'}},resident:{schedule(){}},anticipation:{state:{capabilities:{mission_steps:{workspace_root:'C:\\ensayo'}}}},companion:{data:{prefs:{skillProject:'A'}},save(){},openFeature(){},renderChat(){}},commandLibrary:{generation:0,busy:false,operation:null,open(){},status(text){window.commandStatus=text;},renderOperation(plan){window.renderedPlan=structuredClone(plan);},request:async(method,route,body)=>{
    calls.push({method,route,body:structuredClone(body)});
    if(route.startsWith('/axx-api/learning/actions?'))return {actions:[structuredClone(skill)]};if(route.startsWith('/axx-api/learning/plans?'))return {plans:[]};if(route.startsWith('/axx-api/learning/context?'))return structuredClone(context);
    if(route==='/axx-api/learning/revalidate'){if(window.rejectTrial)throw Error('El origen está fuera del espacio de ensayo.');return {kind:'learned_plan',operation_id:body.operation_id,state:'awaiting_approval',conversation_id:body.conversation_id,steps:[{command_id:'axx.file.sha256',inputs:{path:body.inputs.path}}],revalidation:{id:body.id,version:body.version},revalidation_scope:{workspace_root:'C:\\ensayo'},plan_hash:'f'.repeat(64),message:'Revisa este ensayo; no se ejecutó.'};}
    if(route==='/axx-api/learning/configure'){skill={...skill,...body.changes,version:skill.version+1,context_matches:true,effect_verified:false};return structuredClone(skill);}
    throw Error('Unsupported fixture route '+route);
   }}};
  });
  await page.addScriptTag({path:path.join(__dirname,'skill-library.js')});
  await page.evaluate(()=>Axx.skillLibrary.open('skill.hash'));
  assert.equal(await page.locator('#skills-editor button').filter({hasText:/^Revisar y ejecutar$/}).isDisabled(),true,'Quarantined skill cannot use ordinary repeat execution');
  await page.locator('#skills-revalidation>summary').click();
  assert.equal(await page.locator('#skills-prepare-revalidation').isDisabled(),false);
  assert.equal(await page.locator('#skills-revalidation [name=path]').inputValue(),'','The trial cannot reuse stale schema defaults');
  assert.equal(await page.locator('#skills-revalidation [name=format]').inputValue(),'');
  assert.equal(await page.locator('#skills-revalidation [name=confirm]').inputValue(),'','Boolean defaults also require an explicit choice');
  await page.locator('#skills-prepare-revalidation').click();
  assert.equal(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/revalidate').length),0);
  await page.locator('#skills-revalidation [name=path]').fill('C:\\ensayo\\fresh.txt');
  await page.locator('#skills-revalidation [name=confirm]').selectOption('false');
  await page.evaluate(()=>{window.rejectTrial=true;});
  await page.locator('#skills-prepare-revalidation').click();
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('fuera del espacio de ensayo'));
  assert.equal(await page.evaluate(()=>Axx.commandLibrary.operation),null,'Rejected preparation cannot leave a phantom planning lock');
  assert.equal(await page.evaluate(()=>Axx.commandLibrary.lastOperation.operation_id),'trial-1','The rejected or uncertain request keeps its operation ID for recovery');
  assert.equal(await page.locator('#skills-revalidation [name=path]').inputValue(),'C:\\ensayo\\fresh.txt','A refusal preserves fresh parameters');
  await page.evaluate(()=>{window.rejectTrial=false;});
  await page.locator('#skills-prepare-revalidation').click();
  await page.waitForFunction(()=>window.renderedPlan?.state==='awaiting_approval');
  assert.deepEqual(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/revalidate').at(-1).body),{id:'skill.hash',version:1,inputs:{path:'C:\\ensayo\\fresh.txt',confirm:false},project_id:'A',conversation_id:'task-a',operation_id:'trial-2'});
  assert.equal(await page.evaluate(()=>calls.some(call=>/execute|propose|repair/.test(call.route))),false,'Preparing a revalidation cannot execute or infer');
  await page.evaluate(()=>{Axx.commandLibrary.operation=null;skill.context_matches=false;skill.context_dependencies=[{project_id:'A',field:'current_file',revision:1}];return Axx.skillLibrary.open('skill.hash');});
  assert.equal(await page.locator('#skills-prepare-revalidation').isDisabled(),true,'Stale immutable references need a new reviewed version');
  await page.locator('#skills-editor details').filter({has:page.locator('summary', {hasText:/^Modificar habilidad$/})}).locator('summary').first().click();
  const refs=page.locator('#skills-refresh-context-refs').locator('..').locator('..');await refs.locator('summary').click();
  await page.waitForFunction(()=>document.getElementById('skills-refresh-context-refs').disabled===false);
  assert.match(await refs.textContent(),/revision_anterior[\s\S]*1[\s\S]*revision_actual[\s\S]*2[\s\S]*actual.txt/);
  await page.evaluate(()=>{document.getElementById('skills-refresh-context-refs').checked=true;});
  await page.locator('#skills-editor button').filter({hasText:/^Guardar cambios$/}).click();
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('Confirma explícitamente'));
  assert.equal(await page.evaluate(()=>calls.some(call=>call.route==='/axx-api/learning/configure')),false,'An automatic checkbox cannot approve new context references');
  await page.locator('#skills-refresh-context-refs').uncheck();await page.locator('#skills-refresh-context-refs').check();
  await page.evaluate(()=>{context.context_revision=3;context.context_meta.current_file.revision=3;context.current_file='C:\\ensayo\\revised.txt';});
  await page.locator('#skills-editor button').filter({hasText:/^Guardar cambios$/}).click();
  await page.waitForFunction(()=>document.getElementById('skills-status').textContent.includes('Las referencias cambiaron'));
  assert.equal(await page.locator('#skills-refresh-context-refs').isChecked(),false,'A revision change resets human approval');
  assert.equal(await page.evaluate(()=>calls.some(call=>call.route==='/axx-api/learning/configure')),false);
  await page.locator('#skills-refresh-context-refs').check();await page.locator('#skills-editor button').filter({hasText:/^Guardar cambios$/}).click();
  await page.waitForFunction(()=>skill.version===2&&document.getElementById('skills-status').textContent.includes('versión nueva'));
  assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/configure').body.changes.context_dependencies),[{project_id:'A',field:'current_file',revision:3}]);
  assert.equal(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/configure').body.changes.version),1,'Saving uses the exact old version and creates an immutable successor');
  assert.equal(await page.locator('#skills-revalidation [name=path]').inputValue(),'','The successor trial also requires fresh parameters');
  assert.equal(await page.locator('#skills-prepare-revalidation').isDisabled(),false);
  assert.equal(await page.locator('#skills-refresh-context-refs').isChecked(),false);
  await page.evaluate(()=>{context.context_meta.current_file.task_id='foreign-task';context.current_file='FOREIGN_PRIVATE_VALUE';return Axx.skillLibrary.open('skill.hash');});
  assert.equal(await page.locator('#skills-refresh-context-refs').isDisabled(),true);
  assert.equal(await page.locator('#skills-prepare-revalidation').isDisabled(),true);
  assert.doesNotMatch(await page.locator('#skills-refresh-context-refs').locator('..').locator('..').textContent(),/FOREIGN_PRIVATE_VALUE/,'Foreign values never enter the reference preview');
  await page.evaluate(()=>{Axx.chatWorkspace.active.id='task-b';Axx.companion.renderChat();});
  assert.equal(await page.locator('#skills-editor').textContent(),'','A chat change removes all previous version/input/reference approvals');
  await page.evaluate(()=>{skill.context_dependencies=[];skill.templates=[{command_id:'axx.desktop.window.invoke',inputs:{}}];return Axx.skillLibrary.open('skill.hash');});
  assert.equal(await page.locator('#skills-prepare-revalidation').isDisabled(),true,'Desktop input and focus never enter this trial flow');
  assert.deepEqual(errors,[]);
  console.log('PASS: fresh typed revalidation review, no defaults/inference/execute, immutable context refresh, trusted exact reference consent and version/chat/privacy guards (controlled IPC)');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
