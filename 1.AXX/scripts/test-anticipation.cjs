/* Controlled IPC/UI contracts; these do not certify native desktop input or installed binaries. */
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<section id="view-settings"></section><main id="panel" hidden></main>');
  await page.evaluate(()=>{
   const prefs=(mode,interruptions)=>({mode,interruptions,cooldown_seconds:60,max_interruptions_hour:3,retention_days:30,cadence_seconds:30,schedule:null,resources:{max_events_tick:25,max_entries_scan:500,max_file_bytes:41943040,max_tick_ms:1000,max_cpu_ms_tick:250}});
   window.calls=[];window.spoken=[];window.events={};window.missionPlans=[];window.missionProject='Proyecto A';window.data={profile:'discreto',paused:false,observation_paused:false,profiles:{discreto:prefs('OFF','silent'),copiloto:prefs('SUGGEST','cards'),full:prefs('EXECUTE','cards')},scopes:[],sources:{events:false,folders:false,applications:false,screen:false,microphone:false,clipboard:false},observation_targets:[],source_runtime:[],source_observations:[],suggestions:[],grants:[],metrics:{proposed:0,shown:0},capabilities:{verify_artifact:true,verifiers:{hash:{available:true,verification_scope:'integrity_only',semantic_verified:false},docx:{available:true,verification_scope:'integrity_only',semantic_verified:false,reason:'Sin inspector del formato'},pdf:{available:false,verification_scope:'pdf_structure_and_text_readability',reason:'Dependencia local ausente'}}}};
   data.capabilities.mission_steps={available:true,workspace_root:'C:\\ensayo',lifetimes:['one_action','session','mission','until_revoked'],parameter_constraints:'exact_subset',write_scope:'executor_workspace',provider_inference:false,commands:[{command_id:'axx.file.sha256',tool:'file_inspection',category:'file_read',available:true,parameters:{path:{type:'string',required:true}}},{command_id:'axx.artifact.write',tool:'file_artifact_writer',category:'new_artifact',available:true,parameters:{path:{type:'string',required:true},content:{type:'string',required:true}}},{command_id:'axx.artifact.media',tool:'artifact_media',category:'file_read',available:false,reason:'Adaptador no disponible',parameters:{path:{type:'string',required:true}}}]};
   let serial=0;
   window.Axx={isNative:()=>true,newId:()=> 'fixture-'+(++serial),chatWorkspace:{active:{id:'task-a',title:'Proyecto A'},busy:false},skillLibrary:{project:()=>window.missionProject},resident:{schedule(){},drag:null},app:{updateHitMap(){},bridge:{listen:async(id,fn)=>{events[id]=fn;}}},companion:{renderChat(){},openChat(){window.openedChat=true;},speakReply:text=>spoken.push(text)},commandLibrary:{busy:false,operation:null,renderOperation(plan){window.reviewedPlan=plan;}},
    backendRequest:async(method,route,body)=>{
     calls.push({method,route,body:structuredClone(body)});const action=route.split('/').at(-1);
     if(route.startsWith('/axx-api/learning/plans?'))return {plans:structuredClone(window.missionPlans)};
     if(route==='/axx-api/learning/dependencies'){if(window.dependencyError)return {error:{message:'El plan cambió; vuelve a revisarlo.'}};const plan=missionPlans.find(p=>p.operation_id===body.operation_id);plan.mission.mission_dependencies=body.dependencies.map(operation_id=>({operation_id,goal_revision:1,steps_hash:'fixture-steps'}));plan.mission.state='awaiting_approval';return structuredClone(plan);}
     if(route==='/axx-api/learning/plan?id=prepared-fixture')return {kind:'learned_plan',operation_id:'prepared-fixture',conversation_id:'task-a',state:'awaiting_approval',steps:[]};
     if(action==='status'){
      const value=structuredClone(data);value.suggestions=value.suggestions.filter(s=>s.task_id===body.task_id);value.grants=value.grants.filter(g=>g.task_id===body.task_id);
      if(window.delayStatus){window.delayStatus=false;await new Promise(resolve=>{window.releaseStatus=resolve;});}
      return value;
     }
     if(action==='configure'){
      for(const [key,value] of Object.entries(body)){
       if(key==='profiles')for(const [id,p] of Object.entries(value))Object.assign(data.profiles[id],p);
       else if(key==='sources')Object.assign(data.sources,value);else data[key]=value;
      }
      return structuredClone(data);
     }
     if(action==='grant'){if(window.grantError)throw Error('El permiso cambió; revisa su alcance.');const grant={...body,grant_id:'grant-'+(++serial),revoked:false};data.grants.push(grant);return grant;}
     if(action==='revoke'){data.grants.find(g=>g.grant_id===body.grant_id).revoked=true;return {revoked:true};}
     const row=data.suggestions.find(s=>s.suggestion_id===body.suggestion_id);
     if(action==='accept'){
      if(!row||body.plan_hash!==row.plan_hash)throw Error('El plan cambió.');
      if(row.candidate_kind){row.state='PREPARED';row.preparation_complete=true;row.learning_plan_id='prepared-fixture';return row;}
      row.state='VERIFIED';row.approval='manual';row.accepted_hash=body.plan_hash;row.feedback={acceptance:'explicit',usefulness:'unknown',corrections:0};row.result={state:'succeeded',postconditions_passed:true,output:{sha256:'observed-fixture'}};row.message='Hash observado en la prueba de contrato.';return row;
     }
     if(action==='feedback'){
      if(body.action==='shown'){data.metrics.shown++;return {shown:true};}
      if(body.action==='useful'){if(!row.feedback.corrections)row.feedback.usefulness='confirmed';return row;}
      if(body.action==='correction'){row.feedback.usefulness='corrected';row.feedback.corrections++;return row;}
      row.state=({dismiss:'DISMISSED',suppress:'SUPPRESSED',restore:'DETECTED'})[body.action];return row;
     }
     if(action==='cancel'){for(const row of data.suggestions)if(!body.suggestion_id||row.suggestion_id===body.suggestion_id)row.state='CANCELLED';return {cancelled:true};}
     if(action==='forget'){data.suggestions=data.suggestions.filter(r=>r.task_id!==body.task_id);return {forgotten:true};}
     throw Error('Unsupported test route: '+route);
    }};
  });
  await page.addScriptTag({path:path.join(__dirname,'anticipation.js')});
  await page.addStyleTag({content:'#anticipation-card{top:10px;left:10px}'});
  await page.waitForFunction(()=>Axx.anticipation.state?.profile==='discreto');
  assert.equal(await page.locator('#anticipation-profile').inputValue(),'discreto');
  assert.equal(await page.evaluate(()=>Axx.anticipation.allowSurprises()),false);
  await page.selectOption('#anticipation-profile','full');
  await page.waitForFunction(()=>Axx.anticipation.state?.profile==='full');
  assert.equal(await page.evaluate(()=>calls.some(c=>c.route.endsWith('/configure')&&c.body.profile==='full')),true);
  await page.evaluate(()=>{const form=document.querySelector('form[data-profile="full"]');form.elements.interruptions.value='silent';form.requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.profiles.full.interruptions==='silent');
  assert.equal(await page.evaluate(()=>Axx.anticipation.state.profiles.full.mode),'EXECUTE','Quiet interruptions do not reduce Full autonomy');
  await page.evaluate(()=>{data.profile='copiloto';data.profiles.copiloto.mode='EXECUTE';return Axx.anticipation.refresh();});
  assert.match(await page.locator('#anticipation-status').textContent(),/Copiloto · Personalizado: Ejecutar con permiso/);
  assert.match(await page.locator('#anticipation-profile option[value="copiloto"]').textContent(),/Personalizado: Ejecutar con permiso/,'Labels disclose customized execution without changing its authority');
  await page.evaluate(()=>{data.profile='full';data.profiles.copiloto.mode='SUGGEST';return Axx.anticipation.refresh();});
  await page.evaluate(()=>{const form=document.querySelector('form[data-profile="full"]');form.elements.cadence_seconds.value='7';form.elements.resource_max_events_tick.value='4';form.elements.resource_max_entries_scan.value='120';form.elements.resource_max_file_bytes.value='1048576';form.elements.resource_max_tick_ms.value='500';form.elements.resource_max_cpu_ms_tick.value='80';form.elements.schedule_enabled.checked=true;form.elements.schedule_enabled.dispatchEvent(new Event('change'));form.elements.schedule_timezone.value='America/Santo_Domingo';form.elements.schedule_start.value='21:00';form.elements.schedule_end.value='06:00';for(const day of form.querySelectorAll('[name=schedule_days]'))day.checked=['0','4'].includes(day.value);form.requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.profiles.full.cadence_seconds===7);
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/configure')&&c.body.profiles).at(-1).body.profiles.full),{mode:'EXECUTE',interruptions:'silent',cooldown_seconds:60,max_interruptions_hour:3,retention_days:30,cadence_seconds:7,resources:{max_events_tick:4,max_entries_scan:120,max_file_bytes:1048576,max_tick_ms:500,max_cpu_ms_tick:80},schedule:{timezone:'America/Santo_Domingo',days:[0,4],start:'21:00',end:'06:00'}},'Profile saves canonical nested limits and Monday-zero overnight schedule');
  await page.evaluate(()=>{const form=document.querySelector('form[data-profile="full"]');form.elements.schedule_enabled.checked=false;form.elements.schedule_enabled.dispatchEvent(new Event('change'));form.requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.profiles.full.schedule===null);
  assert.equal(await page.locator('form[data-profile="full"] [name=schedule_timezone]').isDisabled(),true,'Disabled scheduling sends null and has no active required fields');
  await page.evaluate(()=>{document.getElementById('anticipation-scope-task').checked=false;document.getElementById('anticipation-scope-project').value='project-a';document.getElementById('anticipation-scope-application').value='editor.exe';document.getElementById('anticipation-scope-device').value='host';document.getElementById('anticipation-scope-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.scopes.length===1);
  assert.deepEqual(await page.evaluate(()=>Axx.anticipation.state.scopes[0]),{project_id:'project-a',application_id:'editor.exe',device_id:'host',profile:'discreto',exclude:false});
  await page.evaluate(()=>{document.getElementById('anticipation-target-root').value='C:\\ensayo';document.getElementById('anticipation-target-project').value='project-a';document.getElementById('anticipation-target-expiry').value='persistent';document.getElementById('anticipation-target-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.observation_targets.length===1);
  const folder=await page.evaluate(()=>Axx.anticipation.state.observation_targets[0]);
  assert.deepEqual(folder,{id:folder.id,source:'folder',task_id:'task-a',project_id:'project-a',application_id:'',device_id:'host',observe:true,retain:false,send_to_provider:false,expires_at:null,root:'C:\\ensayo'});
  assert.equal(await page.evaluate(()=>Axx.anticipation.state.sources.folders),false,'Selecting a target cannot silently enable its source');
  await page.evaluate(()=>{document.getElementById('anticipation-folders').checked=true;document.getElementById('anticipation-folders').dispatchEvent(new Event('change'));});
  await page.waitForFunction(()=>Axx.anticipation.state.sources.folders===true);
  assert.match(await page.locator('#anticipation-source-runtime').textContent(),/Sin lecturas/,'Enabled is not reported as observed');
  await page.evaluate(()=>{document.getElementById('anticipation-target-source').value='application';document.getElementById('anticipation-target-source').dispatchEvent(new Event('change'));document.getElementById('anticipation-target-process').value='editor.exe';document.getElementById('anticipation-target-retain').checked=true;document.getElementById('anticipation-target-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.observation_targets.length===2);
  assert.equal(await page.locator('#anticipation-target-root').isDisabled(),true);
  assert.equal(await page.evaluate(()=>Object.hasOwn(Axx.anticipation.state.observation_targets[1],'root')),false,'Application targets never include disabled folder data');
  assert.deepEqual(await page.evaluate(()=>{const target=Axx.anticipation.state.observation_targets[1];return [target.process_name,target.retain,target.send_to_provider,target.task_id];}),['editor.exe',true,false,'task-a']);
  await page.evaluate(()=>{const id=data.observation_targets[0].id;data.source_runtime=[{id,source:'folder',active:true,samples:4,events:1,truncated:true,error:null},{id:'foreign',active:true,samples:12345,events:1}];data.source_observations=[{task_id:'task-a',observed_at:Date.now()/1000,type:'file.modified',resource:{path:'C:\\ensayo\\<img src=x>.txt',size:8},retained:false},{task_id:'task-b',observed_at:Date.now()/1000,type:'application.opened',resource:{process_name:'private.exe'},retained:true}];return Axx.anticipation.refresh();});
  assert.match(await page.locator('#anticipation-source-runtime').textContent(),/Observación activa · Lecturas: 4 · Cambios: 1 · Exploración parcial/);
  assert.doesNotMatch(await page.locator('#anticipation-source-runtime').textContent(),/12345/);
  assert.doesNotMatch(await page.locator('#anticipation-source-observations').textContent(),/private.exe/);
  assert.equal(await page.locator('#anticipation-source-observations img').count(),0);
  assert.match(await page.locator('#anticipation-verifiers').textContent(),/DOCX · Disponible · Solo integridad por hash · Sin inspector/);
  assert.match(await page.locator('#anticipation-verifiers').textContent(),/PDF · No disponible/);
  await page.evaluate(()=>document.querySelector('#anticipation-targets article input').click());
  await page.waitForFunction(()=>Axx.anticipation.state.observation_targets[0].observe===false);
  assert.equal(await page.evaluate(()=>Axx.anticipation.state.observation_targets[0].retain),false,'Observe and retain remain independent');
  await page.evaluate(()=>document.querySelector('#anticipation-targets article button').click());
  await page.waitForFunction(()=>Axx.anticipation.state.observation_targets.length===1);
  assert.equal(await page.evaluate(()=>calls.some(c=>c.route.includes('/artifact')||c.route.includes('/file.delete'))),false,'Removing a source only changes config');
  await page.evaluate(()=>{
   document.getElementById('anticipation-grant-root').value='C:\\ensayo';document.getElementById('anticipation-grant-expiry').value='persistent';document.getElementById('anticipation-grant-events').checked=true;
   document.getElementById('anticipation-grant-form').requestSubmit();
  });
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===1);
  assert.deepEqual(await page.evaluate(()=>calls.find(c=>c.route.endsWith('/grant')).body),{task_id:'task-a',capability:'verify_artifact',root:'C:\\ensayo',expires_at:null,observe_events:true});
  await page.evaluate(()=>document.querySelector('#anticipation-grants button').click());
  await page.waitForFunction(()=>Axx.anticipation.state.grants[0].revoked);
  assert.equal(await page.locator('#anticipation-mission-grant-root').inputValue(),'C:\\ensayo','Write destination comes from the actual executor workspace');
  assert.deepEqual(await page.locator('#anticipation-mission-lifetime option').evaluateAll(options=>options.map(option=>option.value)),['one_action','session','mission','until_revoked']);
  assert.equal(await page.locator('#anticipation-mission-commands input:checked').count(),0,'Choosing Full never selects or grants actions');
  assert.equal(await page.locator('#anticipation-mission-commands input[value="axx.artifact.media"]').isDisabled(),true);
  assert.doesNotMatch(await page.locator('#anticipation-mission-commands').textContent(),/shell|MCP|abrir aplicaciones/i,'Only registered allowed command IDs are offered');
  await page.evaluate(()=>{document.querySelector('#anticipation-mission-commands input[value="axx.artifact.write"]').checked=true;document.getElementById('anticipation-mission-commands').dispatchEvent(new Event('change'));document.getElementById('anticipation-mission-read-roots').value='C:\\lectura\nC:\\referencias';document.getElementById('anticipation-mission-constraints').value=JSON.stringify({'axx.artifact.write':{path:'copia.txt'}});document.getElementById('anticipation-mission-expiry').value='persistent';document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===2);
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/grant')).at(-1).body),{capability:'mission_steps',task_id:'task-a',root:'C:\\ensayo',read_roots:['C:\\lectura','C:\\referencias'],command_ids:['axx.artifact.write'],expires_at:null,lifetime:'one_action',parameter_constraints:{'axx.artifact.write':{path:'copia.txt'}}});
  assert.match(await page.locator('#anticipation-grants').textContent(),/Pasos de misión[\s\S]*Una acción permitida[\s\S]*axx.artifact.write[\s\S]*copia.txt/);
  await page.evaluate(()=>{document.getElementById('anticipation-mission-constraints').value='{';document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('anticipation-status').textContent.includes('objeto JSON válido'));
  assert.equal(await page.evaluate(()=>Axx.anticipation.state.grants.length),2);
  assert.equal(await page.locator('#anticipation-mission-constraints').inputValue(),'{','Rejected constraints preserve the permission draft');
  await page.evaluate(()=>{document.getElementById('anticipation-mission-constraints').value='';document.getElementById('anticipation-mission-lifetime').value='session';document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===3);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/grant')).at(-1).body.lifetime),'session');
  await page.evaluate(()=>{document.getElementById('anticipation-mission-lifetime').value='until_revoked';document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===4);
  await page.evaluate(()=>document.querySelectorAll('#anticipation-grants article')[1].querySelector('button').click());
  await page.waitForFunction(()=>Axx.anticipation.state.grants[1].revoked);
  await page.evaluate(()=>{const grant=data.grants.find(g=>g.lifetime==='session');grant.active=false;grant.inactive_reason='session_ended';return Axx.anticipation.refresh();});
  assert.match(await page.locator('#anticipation-grants').textContent(),/Sesión finalizada/,'Session validity comes from backend state, never an opaque session ID');
  await page.evaluate(()=>{data.observation_targets.push({id:'external-folder',source:'folder',task_id:'task-a',root:'C:\\documentos',observe:true,retain:true,send_to_provider:false,expires_at:null},{id:'unretained-folder',source:'folder',task_id:'task-a',root:'C:\\transitorio',observe:true,retain:false,expires_at:null},{id:'other-task-folder',source:'folder',task_id:'task-b',root:'C:\\privado',observe:true,retain:true,expires_at:null});return Axx.anticipation.refresh();});
  assert.deepEqual(await page.locator('#anticipation-grant-source option').evaluateAll(options=>options.map(option=>option.value)),['','external-folder'],'External verification needs exact task, folder and independent observation/retention grants');
  await page.evaluate(()=>{const source=document.getElementById('anticipation-grant-source');source.value='external-folder';source.dispatchEvent(new Event('change'));});
  assert.equal(await page.locator('#anticipation-grant-root').inputValue(),'C:\\documentos');
  assert.equal(await page.locator('#anticipation-grant-root').evaluate(input=>input.readOnly),true);
  assert.equal(await page.locator('#anticipation-grant-events').isDisabled(),false,'Automatic verification is independent from the selected source consent');
  assert.equal(await page.locator('#anticipation-grant-events').isChecked(),false,'Selecting an external source cannot authorize automatic checks');
  const sourceConsent=await page.evaluate(()=>JSON.stringify(data.sources));
  await page.evaluate(()=>document.getElementById('anticipation-grant-form').requestSubmit());
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===5);
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/grant')).at(-1).body),{task_id:'task-a',capability:'verify_artifact',root:'C:\\documentos',expires_at:null,observe_events:false,source_target_id:'external-folder',metadata_only:true});
  assert.match(await page.locator('#anticipation-grants').textContent(),/Solo aceptación explícita/);
  assert.equal(await page.evaluate(()=>JSON.stringify(data.sources)),sourceConsent,'A verification permission cannot alter source consent');
  await page.evaluate(()=>{document.getElementById('anticipation-grant-events').checked=true;data.observation_targets.find(target=>target.id==='external-folder').retain=false;return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-grant-source').inputValue(),'');
  assert.equal(await page.locator('#anticipation-grant-root').evaluate(input=>input.readOnly),false);
  assert.equal(await page.locator('#anticipation-grant-events').isChecked(),false,'A lost source cannot transfer automatic authorization to another root');
  await page.evaluate(()=>{
   const mission={mission_id:'prepared-fixture',objective:'Preparar <img src=x> paquete',scope:{project_id:'Proyecto A',task_id:'task-a',resources:['ensayo.txt']},state:'succeeded',plan_hash:'c'.repeat(64),revision:1,deliverables:['paquete.zip'],destination:'C:\\ensayo',success_conditions:['Archivo legible'],dependencies:{},verified_steps:[0],pending_steps:[1],blockers:[],permission:{exact_plan_approved:true,automatic_future_plans_authorized:false},budget:{step_limit:8,model_call_limit:2,model_calls_used:1,model_calls_remaining:1},stop_condition:'verified_goal_or_cancellation',completed:false,user_confirmed_usefulness:true};
   missionPlans=[{operation_id:'prepared-fixture',conversation_id:'task-a',steps:[{},{}],mission},{operation_id:'another-task',conversation_id:'task-b',steps:[],mission:{...mission,objective:'Contenido privado del otro chat',scope:{...mission.scope,task_id:'task-b'}}},{operation_id:'foreign-project',project_id:'Otro proyecto',conversation_id:'task-z',steps:[],mission:{...mission,objective:'Fuera de este proyecto',scope:{...mission.scope,task_id:'task-z',project_id:'Otro proyecto'}}}];
  });
  await page.locator('#anticipation-mission>summary').click();
  await page.waitForFunction(()=>document.querySelectorAll('#anticipation-missions article').length===1);
  assert.match(await page.locator('#anticipation-missions').innerText(),/Resultado recibido; objetivo pendiente · 1\/2 pasos verificados/);
  assert.doesNotMatch(await page.locator('#anticipation-missions').innerText(),/Contenido privado del otro chat|Completada y verificada/);
  assert.equal(await page.locator('#anticipation-missions img').count(),0);
  assert.equal(await page.evaluate(()=>calls.some(c=>c.route==='/axx-api/learning/plans?project_id=Proyecto%20A')),true,'Mission retrieval uses the existing project context');
  await page.evaluate(()=>document.querySelector('#anticipation-missions article>details').open=true);
  await page.evaluate(()=>Axx.anticipation.refresh());
  assert.equal(await page.locator('#anticipation-missions article>details').evaluate(node=>node.open),true,'Status refresh preserves expanded mission details');
  assert.match(await page.locator('#anticipation-missions').innerText(),/no concede permiso para futuros planes autónomos/);
  assert.match(await page.locator('#anticipation-missions').innerText(),/no sustituye las verificaciones de ejecución/);
  assert.deepEqual(await page.locator('#anticipation-missions select option').evaluateAll(options=>options.map(o=>o.value)),['another-task'],'Dependency choices allow explicit same-project cross-chat selection only');
  await page.evaluate(()=>{const form=document.querySelector('[data-dependency-id="prepared-fixture"]');form.parentElement.open=true;form.querySelector('select').value='another-task';form.querySelector('select').dispatchEvent(new Event('change'));missionPlans[1].mission.revision=2;return Axx.anticipation.refresh();});
  await page.waitForFunction(()=>document.querySelector('[data-dependency-id="prepared-fixture"] select')?.value==='another-task');
  assert.equal(await page.locator('[data-dependency-id="prepared-fixture"]').evaluate(form=>form.parentElement.open),true,'Polling changed peer receipts preserves the dependency draft');
  await page.evaluate(()=>{window.dependencyError=true;document.querySelector('[data-dependency-id="prepared-fixture"]').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('anticipation-status').textContent.includes('El plan cambió'));
  assert.equal(await page.locator('[data-dependency-id="prepared-fixture"] select').inputValue(),'another-task','A rejected hash cannot erase the pending selection');
  await page.evaluate(()=>{window.dependencyError=false;document.querySelector('[data-dependency-id="prepared-fixture"]').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('anticipation-missions').textContent.includes('fixture-steps'));
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/learning/dependencies').at(-1).body),{operation_id:'prepared-fixture',dependencies:['another-task'],plan_hash:'c'.repeat(64)},'Mission links bind the exact current plan and explicit IDs without executing');
  assert.match(await page.locator('#anticipation-missions').innerText(),/Pendiente de aprobación/,'Saving links retains the approval boundary');
  await page.evaluate(()=>{missionPlans[0].mission.state='waiting_dependency';return Axx.anticipation.refresh();});
  await page.waitForFunction(()=>document.getElementById('anticipation-missions').textContent.includes('Espera otra misión verificada'));
  await page.locator('#anticipation-missions button').filter({hasText:'Revisar plan'}).click();
  await page.waitForFunction(()=>window.reviewedPlan?.operation_id==='prepared-fixture');
  await page.evaluate(()=>{document.getElementById('anticipation-mission-lifetime').value='mission';document.getElementById('anticipation-mission-lifetime').dispatchEvent(new Event('change'));document.getElementById('anticipation-mission-grant-plan').value='prepared-fixture';document.getElementById('anticipation-mission-grant-plan').dispatchEvent(new Event('change'));document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===6);
  assert.deepEqual(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/grant')).at(-1).body),{capability:'mission_steps',task_id:'task-a',root:'C:\\ensayo',read_roots:['C:\\lectura','C:\\referencias'],command_ids:['axx.artifact.write'],expires_at:null,lifetime:'mission',learning_plan_id:'prepared-fixture',reviewed_plan_hash:'c'.repeat(64)});
  assert.deepEqual(await page.locator('#anticipation-mission-grant-plan option').evaluateAll(options=>options.map(option=>option.value)),['','prepared-fixture'],'A mission grant never selects plans from another task/project');
  await page.evaluate(()=>{missionPlans[0].mission.plan_hash='d'.repeat(64);return Axx.anticipation.refresh();});
  await page.waitForFunction(()=>document.getElementById('anticipation-mission-grant-plan').value==='');
  assert.match(await page.locator('#anticipation-mission-plan-hash').textContent(),/misión cambió/,'A changed mission requires a fresh explicit selection');
  assert.equal(await page.locator('#anticipation-mission-read-roots').inputValue(),'C:\\lectura\nC:\\referencias','A hash change preserves the remaining permission draft');
  await page.evaluate(()=>{document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  assert.equal(await page.evaluate(()=>data.grants.length),6,'A missing exact mission selection cannot grant permission');
  await page.evaluate(()=>{document.getElementById('anticipation-mission-grant-plan').value='prepared-fixture';document.getElementById('anticipation-mission-grant-plan').dispatchEvent(new Event('change'));window.grantError=true;document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('anticipation-status').textContent.includes('permiso cambió'));
  assert.equal(await page.locator('#anticipation-mission-grant-plan').inputValue(),'prepared-fixture','Backend refusal preserves the permission draft without approval');
  await page.evaluate(()=>{window.grantError=false;document.getElementById('anticipation-mission-grant-form').requestSubmit();});
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===7);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/grant')).at(-1).body.reviewed_plan_hash),'d'.repeat(64));
  await page.evaluate(()=>{data.capabilities.mission_steps.available=false;return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-mission-authorize').isDisabled(),true);
  await page.evaluate(()=>{data.capabilities.mission_steps.available=true;return Axx.anticipation.refresh();});
  await page.evaluate(()=>{missionPlans[0].mission.completed=true;missionPlans[0].mission.verified_steps=[0,1];missionPlans[0].mission.pending_steps=[];return Axx.anticipation.refresh();});
  await page.waitForFunction(()=>document.getElementById('anticipation-missions').textContent.includes('Completada y verificada'));
  assert.equal(await page.locator('#anticipation-missions article>details').evaluate(node=>node.open),true,'Changed mission receipts preserve the user expansion');
  await page.evaluate(()=>{
   data.profile='copiloto';data.sources.events=true;
   data.suggestions=[{suggestion_id:'suggestion-a',task_id:'task-a',routine_id:'verify_artifact',plan_hash:'exact-hash-a',verification_scope:'integrity_only',semantic_verified:false,verifier_reason:'Sin inspector del formato',title:'Verificar <img src=x>',state:'AWAITING_APPROVAL',visible:true,plan:{command_id:'axx.artifact.verify',inputs:{path:'ensayo.txt'},source_operation_id:'writer-a',expected_sha256:'a'.repeat(64)},initiative_chain:{root_event_id:'artifact-a',depth:1,budget:1,stop_condition:'verification_terminal'},assessment:{likelihood:{score:1,method:'registered_generated_artifact_rule'}},provenance:{actor:'axx',origin:'direct_instruction',causation_id:'writer-a',human_preference_evidence:false}}];return Axx.anticipation.refresh(true);
  });
  assert.equal(await page.locator('#anticipation-card').isVisible(),true);
  assert.equal(await page.locator('#anticipation-card img').count(),0,'Suggestion text cannot inject markup');
  const hiddenInitiative=await page.evaluate(()=>{const cancellations=calls.filter(c=>c.route.endsWith('/cancel')).length;Axx.app.machine={visible:false};Axx.anticipation.render();return {hidden:document.getElementById('anticipation-card').hidden,profile:Axx.anticipation.state.profile,paused:Axx.anticipation.state.paused,cancelled:calls.filter(c=>c.route.endsWith('/cancel')).length-cancellations};});
  assert.deepEqual(hiddenInitiative,{hidden:true,profile:'copiloto',paused:false,cancelled:0},'Hidden presentation cannot pause or cancel background initiatives');
  await page.evaluate(()=>{Axx.app.machine.visible=true;Axx.anticipation.render();});
  await page.locator('#anticipation-why summary').click();
  const whyHeights=await page.evaluate(()=>{
   const node=document.getElementById('anticipation-card'),why=document.getElementById('anticipation-why'),heights=[];
   for(const open of [false,true,false]){why.open=open;Axx.anticipation.layout({workWidth:1280,workHeight:960,spaceLeft:640,spaceRight:640,spaceAbove:480,spaceBelow:480},180,(id,x,y,w,h)=>{node.style.setProperty('height',h+'px','important');node.style.setProperty('max-height',h+'px','important');heights.push(h);});}
   why.open=true;return heights;
  });
  assert(whyHeights[1]>whyHeights[0]);assert.equal(whyHeights[2],whyHeights[0],'Collapsing Why returns the resident card to its compact height');
  assert.match(await page.locator('#anticipation-why').innerText(),/Observado[\s\S]*artifact-a[\s\S]*Inferido[\s\S]*regla registrada[\s\S]*Actor: Axx[\s\S]*Origen: Orden directa[\s\S]*Causa: writer-a/);
  assert.match(await page.locator('#anticipation-why').innerText(),/Alcance de la comprobación[\s\S]*Integridad por hash/);
  assert.doesNotMatch(await page.locator('#anticipation-why').innerText(),/Integridad verificada/,'A planned verification scope is not a completed result');
  assert.equal(await page.locator('#anticipation-why dt').filter({hasText:/^Confirmado por ti$/}).count(),0,'An inference or Axx event is not user confirmation');
  await page.locator('#anticipation-actions button').filter({hasText:/^Verificar$/}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].state==='VERIFIED');
  assert.deepEqual(await page.evaluate(()=>calls.find(c=>c.route.endsWith('/accept')).body),{suggestion_id:'suggestion-a',plan_hash:'exact-hash-a'});
  assert.equal(await page.locator('#anticipation-phase').innerText(),'Integridad verificada');
  assert.match(await page.locator('#anticipation-why').innerText(),/apariencia no constan verificados[\s\S]*Sin inspector del formato/,'A hash receipt cannot imply semantic or visual success');
  assert.match(await page.locator('#anticipation-why').innerText(),/Aceptaste esta versión exacta[\s\S]*Sin confirmación de utilidad/);
  await page.locator('#anticipation-why button').filter({hasText:'Me resultó útil'}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].feedback.usefulness==='confirmed');
  assert.match(await page.locator('#anticipation-why').innerText(),/Confirmaste la utilidad/);
  await page.locator('#anticipation-why button').filter({hasText:'Necesita corrección'}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].feedback.usefulness==='corrected');
  assert.match(await page.locator('#anticipation-why').innerText(),/Corregido por ti/);
  assert.doesNotMatch(await page.locator('#anticipation-why').innerText(),/Confirmaste la utilidad/,'A correction supersedes prior positive utility feedback');
  await page.evaluate(()=>{data.suggestions[0].result={state:'succeeded',postconditions_passed:false};return Axx.anticipation.refresh();});
  assert.match(await page.locator('#anticipation-phase').innerText(),/falta evidencia/,'Receipt without postconditions is not rendered verified');
  await page.evaluate(()=>{data.profile='discreto';data.effective_profile=null;data.suggestions[0].policy={...data.profiles.copiloto};return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-card').isVisible(),true,'A scoped Copiloto policy remains effective under global Discreto');
  assert.equal(await page.evaluate(()=>Axx.anticipation.allowSurprises()),false,'Ambiguous root scopes never authorize unsolicited voice');
  await page.evaluate(()=>{data.profile='copiloto';delete data.effective_profile;delete data.suggestions[0].policy;});
  await page.evaluate(()=>{data.suggestions[0].context_state='stale';data.suggestions[0].state='AWAITING_APPROVAL';return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-phase').innerText(),'Desactualizado');
  assert.equal(await page.locator('#anticipation-actions button').filter({hasText:/^Verificar$/}).count(),0,'Changed inputs cannot be accepted through an old card');
  assert.match(await page.locator('#anticipation-why').innerText(),/Desactualizado/);
  await page.evaluate(()=>{delete data.suggestions[0].context_state;});
  await page.evaluate(()=>{
   data.suggestions[0].state='AWAITING_APPROVAL';Axx.nativeVoice={activeCapture:{}};return Axx.anticipation.refresh();
  });
  assert.equal(await page.locator('#anticipation-card').isVisible(),false,'Do not interrupt dictation');
  await page.evaluate(()=>{Axx.nativeVoice.activeCapture=null;Axx.symbiosis={liveActive:true};return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-card').isVisible(),false,'Do not interrupt a live call');
  await page.evaluate(()=>{Axx.symbiosis.liveActive=false;return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-card').isVisible(),true);
  await page.evaluate(()=>{data.profile='full';data.profiles.full.interruptions='cards_voice';return Axx.anticipation.refresh();});
  assert.equal(await page.evaluate(()=>Axx.anticipation.allowSurprises()),true);
  assert.equal(await page.evaluate(()=>spoken.length),1);
  await page.evaluate(()=>Axx.anticipation.refresh());
  assert.equal(await page.evaluate(()=>spoken.length),1,'A repeated status does not repeat speech');
  await page.evaluate(()=>{Axx.chatWorkspace.active={id:'task-b',title:'Proyecto B'};Axx.companion.renderChat();});
  assert.equal(await page.locator('#anticipation-card').isVisible(),false,'Chat changes hide the prior task synchronously');
  assert.doesNotMatch(await page.locator('#anticipation-missions').innerText(),/Preparar <img src=x> paquete/,'Chat changes clear prior mission details synchronously');
  assert.equal(await page.locator('#anticipation-targets').innerText(),'','Chat changes clear source authorizations synchronously');
  assert.equal(await page.locator('#anticipation-source-observations').innerText(),'','Chat changes clear local observations synchronously');
  assert.equal(await page.locator('#anticipation-mission-commands input:checked').count(),0,'Chat changes clear pending action authorization choices');
  assert.equal(await page.locator('#anticipation-mission-grant-plan').inputValue(),'','Chat changes clear the reviewed plan binding');
  await page.waitForFunction(()=>Axx.anticipation.state&&Axx.anticipation.state.suggestions.length===0);
  assert.equal(await page.locator('#anticipation-grants').innerText(),'');
  await page.evaluate(()=>{window.delayStatus=true;return void Axx.anticipation.refresh();});
  await page.waitForFunction(()=>window.releaseStatus);
  await page.evaluate(()=>{Axx.chatWorkspace.active={id:'task-a',title:'Proyecto A'};Axx.companion.renderChat();window.releaseStatus();});
  await page.waitForFunction(()=>Axx.anticipation.current?.task_id==='task-a');
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>calls.some(c=>c.route.endsWith('/cancel')));
  assert.equal(await page.locator('#anticipation-card').isVisible(),false);
  await page.evaluate(()=>{data.suggestions[0].state='AWAITING_APPROVAL';return Axx.anticipation.refresh();});
  assert.equal(await page.locator('#anticipation-card').isVisible(),false,'Esc prevents the trigger restarting this execution');
  assert.equal(await page.evaluate(()=>Axx.anticipation.allowSurprises()),false);
  await page.evaluate(()=>{data.profile='copiloto';document.getElementById('anticipation-profile').value='copiloto';document.getElementById('anticipation-profile').dispatchEvent(new Event('change'));});
  await page.waitForFunction(()=>Axx.anticipation.current?.suggestion_id==='suggestion-a');
  await page.locator('#anticipation-actions button').filter({hasText:'No volver a sugerir'}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].state==='SUPPRESSED');
  assert.equal(await page.locator('#anticipation-card').isVisible(),false);
  const boxes=await page.evaluate(()=>{const boxes=[];Axx.anticipation.layout({workWidth:320,workHeight:568,spaceLeft:160,spaceRight:160,spaceAbove:280,spaceBelow:288},180,(...box)=>boxes.push(box));return boxes;});
  assert.equal(boxes.length,0,'Suppression leaves no invisible native input surface');
  await page.evaluate(()=>{
   data.suggestions=[{suggestion_id:'resume-a',task_id:'task-a',routine_id:'resume_task',candidate_kind:'resume_task',plan_hash:'resume-exact',title:'Continuar tarea',state:'AWAITING_APPROVAL',visible:true,plan:{inputs:{path:'C:\\ensayo'}}}];return Axx.anticipation.refresh();
  });
  await page.locator('#anticipation-actions button').filter({hasText:'Preparar reanudación'}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].preparation_complete);
  assert.equal(await page.locator('#anticipation-phase').innerText(),'Preparado');
  assert.equal(await page.locator('#anticipation-actions button').filter({hasText:'Preparar reanudación'}).count(),0);
  await page.locator('#anticipation-actions button').filter({hasText:'Revisar plan'}).click();
  await page.waitForFunction(()=>window.reviewedPlan?.operation_id==='prepared-fixture');
  assert.equal(await page.evaluate(()=>window.openedChat),true);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/commands/execute')||c.route.endsWith('/learning/execute')).length),0,'Preparing and reviewing never execute the proposed effects');
  assert.deepEqual(errors,[]);
  const html=fs.readFileSync(path.join(__dirname,'../Axx.html'),'utf8');assert.match(html,/scripts\/anticipation\.js/);assert.match(html,/Axx\.anticipation\?\.layout\(g,size,add\)/);
  console.log('PASS: scoped Full mission grants and lifetimes, exact hash invalidation, external metadata verification, nested limits, source consent, dependencies, strict receipts, Why, task races, busy deferral, Esc and suppression (controlled IPC)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
