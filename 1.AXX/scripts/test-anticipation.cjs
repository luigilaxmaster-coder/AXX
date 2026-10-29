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
   const prefs=(mode,interruptions)=>({mode,interruptions,cooldown_seconds:60,max_interruptions_hour:3,retention_days:30});
   window.calls=[];window.spoken=[];window.events={};window.missionPlans=[];window.missionProject='Proyecto A';window.data={profile:'discreto',paused:false,observation_paused:false,profiles:{discreto:prefs('OFF','silent'),copiloto:prefs('SUGGEST','cards'),full:prefs('EXECUTE','cards')},scopes:[],sources:{events:false,screen:false,microphone:false,clipboard:false},suggestions:[],grants:[],metrics:{proposed:0,shown:0},capabilities:{verify_artifact:true}};
   let serial=0;
   window.Axx={isNative:()=>true,chatWorkspace:{active:{id:'task-a',title:'Proyecto A'},busy:false},skillLibrary:{project:()=>window.missionProject},resident:{schedule(){},drag:null},app:{updateHitMap(){},bridge:{listen:async(id,fn)=>{events[id]=fn;}}},companion:{renderChat(){},openChat(){window.openedChat=true;},speakReply:text=>spoken.push(text)},commandLibrary:{busy:false,operation:null,renderOperation(plan){window.reviewedPlan=plan;}},
    backendRequest:async(method,route,body)=>{
     calls.push({method,route,body:structuredClone(body)});const action=route.split('/').at(-1);
     if(route.startsWith('/axx-api/learning/plans?'))return {plans:structuredClone(window.missionPlans)};
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
     if(action==='grant'){const grant={...body,grant_id:'grant-'+(++serial),revoked:false};data.grants.push(grant);return grant;}
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
  await page.evaluate(()=>{
   document.getElementById('anticipation-grant-root').value='C:\\ensayo';document.getElementById('anticipation-grant-expiry').value='persistent';document.getElementById('anticipation-grant-events').checked=true;
   document.getElementById('anticipation-grant-form').requestSubmit();
  });
  await page.waitForFunction(()=>Axx.anticipation.state.grants.length===1);
  assert.deepEqual(await page.evaluate(()=>calls.find(c=>c.route.endsWith('/grant')).body),{task_id:'task-a',capability:'verify_artifact',root:'C:\\ensayo',expires_at:null,observe_events:true});
  await page.evaluate(()=>document.querySelector('#anticipation-grants button').click());
  await page.waitForFunction(()=>Axx.anticipation.state.grants[0].revoked);
  await page.evaluate(()=>{
   const mission={mission_id:'prepared-fixture',objective:'Preparar <img src=x> paquete',scope:{project_id:'Proyecto A',task_id:'task-a',resources:['ensayo.txt']},state:'succeeded',plan_hash:'mission-a',revision:1,deliverables:['paquete.zip'],destination:'C:\\ensayo',success_conditions:['Archivo legible'],dependencies:{},verified_steps:[0],pending_steps:[1],blockers:[],permission:{exact_plan_approved:true,automatic_future_plans_authorized:false},budget:{step_limit:8,model_call_limit:2,model_calls_used:1,model_calls_remaining:1},stop_condition:'verified_goal_or_cancellation',completed:false,user_confirmed_usefulness:true};
   missionPlans=[{operation_id:'prepared-fixture',conversation_id:'task-a',steps:[{},{}],mission},{operation_id:'another-task',conversation_id:'task-b',steps:[],mission:{...mission,objective:'Contenido privado del otro chat',scope:{...mission.scope,task_id:'task-b'}}}];
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
  await page.locator('#anticipation-missions button').filter({hasText:'Revisar plan'}).click();
  await page.waitForFunction(()=>window.reviewedPlan?.operation_id==='prepared-fixture');
  await page.evaluate(()=>{missionPlans[0].mission.completed=true;missionPlans[0].mission.verified_steps=[0,1];missionPlans[0].mission.pending_steps=[];return Axx.anticipation.refresh();});
  await page.waitForFunction(()=>document.getElementById('anticipation-missions').textContent.includes('Completada y verificada'));
  assert.equal(await page.locator('#anticipation-missions article>details').evaluate(node=>node.open),true,'Changed mission receipts preserve the user expansion');
  await page.evaluate(()=>{
   data.profile='copiloto';data.sources.events=true;
   data.suggestions=[{suggestion_id:'suggestion-a',task_id:'task-a',routine_id:'verify_artifact',plan_hash:'exact-hash-a',title:'Verificar <img src=x>',state:'AWAITING_APPROVAL',visible:true,plan:{command_id:'axx.artifact.verify',inputs:{path:'ensayo.txt'},source_operation_id:'writer-a',expected_sha256:'a'.repeat(64)},initiative_chain:{root_event_id:'artifact-a',depth:1,budget:1,stop_condition:'verification_terminal'},assessment:{likelihood:{score:1,method:'registered_generated_artifact_rule'}},provenance:{actor:'axx',origin:'direct_instruction',causation_id:'writer-a',human_preference_evidence:false}}];return Axx.anticipation.refresh(true);
  });
  assert.equal(await page.locator('#anticipation-card').isVisible(),true);
  assert.equal(await page.locator('#anticipation-card img').count(),0,'Suggestion text cannot inject markup');
  await page.locator('#anticipation-why summary').click();
  assert.match(await page.locator('#anticipation-why').innerText(),/Observado[\s\S]*artifact-a[\s\S]*Inferido[\s\S]*regla registrada[\s\S]*Actor: Axx[\s\S]*Origen: Orden directa[\s\S]*Causa: writer-a/);
  assert.equal(await page.locator('#anticipation-why dt').filter({hasText:/^Confirmado por ti$/}).count(),0,'An inference or Axx event is not user confirmation');
  await page.locator('#anticipation-actions button').filter({hasText:/^Verificar$/}).click();
  await page.waitForFunction(()=>Axx.anticipation.state.suggestions[0].state==='VERIFIED');
  assert.deepEqual(await page.evaluate(()=>calls.find(c=>c.route.endsWith('/accept')).body),{suggestion_id:'suggestion-a',plan_hash:'exact-hash-a'});
  assert.equal(await page.locator('#anticipation-phase').innerText(),'Verificado');
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
  console.log('PASS: profiles, grants, exact acceptance, strict receipts, causal Why evidence, utility/correction, stale refusal, project-scoped missions, safe plan review, task races, busy deferral, Esc and suppression (controlled IPC)');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
