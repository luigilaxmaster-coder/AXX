/* Profiles share the existing backend, chat, voice and resident surface owners. */
(function (Axx) {
 'use strict';
 if (!Axx?.isNative() || !Axx.chatWorkspace || !document.getElementById('view-settings')) return;
 const $ = id => document.getElementById(id), names = {discreto:'Discreto',copiloto:'Copiloto',full:'Full'};
 const states = {DETECTED:'Detectado',PREPARED:'Preparado',AWAITING_APPROVAL:'Requiere aceptación',EXECUTING:'En ejecución',VERIFIED:'Verificado',FAILED:'No verificado',CANCELLED:'Cancelado',EXPIRED:'Caducado',DISMISSED:'Descartado',SUPPRESSED:'No volver a sugerir'};
 const section = document.createElement('section');section.id='anticipation-settings';section.className='setup-card';
 section.innerHTML=`<strong>Presencia y autonomía</strong>
 <label class="setting">Perfil<select id="anticipation-profile" aria-label="Perfil de autonomía"><option value="discreto">Discreto</option><option value="copiloto">Copiloto</option><option value="full">Full</option></select></label>
 <p>Discreto responde a tus órdenes. Copiloto propone y prepara. Full ejecuta iniciativas cubiertas por tus permisos. Los comandos explícitos conservan sus capacidades.</p>
 <div class="quick-row"><button id="anticipation-pause" type="button">Pausar iniciativas</button><button id="anticipation-observation" type="button">Pausar observación</button></div>
 <p id="anticipation-status" role="status" aria-live="polite">Comprobando perfiles…</p>
 <details id="anticipation-mission"><summary>Misión de este chat</summary><p id="anticipation-mission-status" role="status"></p><div id="anticipation-missions"></div></details>
 <details><summary>Ajustes de cada perfil</summary><div id="anticipation-profiles"></div></details>
 <details><summary>Ámbitos y exclusiones</summary><form id="anticipation-scope-form">
 <label class="setting">Perfil para este ámbito<select id="anticipation-scope-profile"><option value="discreto">Discreto</option><option value="copiloto">Copiloto</option><option value="full">Full</option></select></label>
 <label><input id="anticipation-scope-task" type="checkbox" checked> Limitar al chat actual</label>
 <label class="setting">Carpeta absoluta, opcional<input id="anticipation-scope-root" maxlength="4096" placeholder="C:\\Proyecto"></label>
 <label><input id="anticipation-scope-exclude" type="checkbox"> Excluir este ámbito de las iniciativas</label><button type="submit">Guardar ámbito</button></form><div id="anticipation-scopes"></div></details>
 <details><summary>Permisos de verificación</summary><p>Permite únicamente inspeccionar archivos de ensayo de esta carpeta en el chat actual. No autoriza cambios, envíos ni control del escritorio.</p>
 <form id="anticipation-grant-form"><label class="setting">Carpeta autorizada<input id="anticipation-grant-root" maxlength="4096" required placeholder="C:\\Proyecto\\ensayo"></label>
 <label class="setting">Vigencia<select id="anticipation-grant-expiry"><option value="3600">Una hora</option><option value="86400">Un día</option><option value="persistent">Hasta revocación</option></select></label>
 <label><input id="anticipation-grant-events" type="checkbox"> Observar eventos de archivos generados en este ámbito</label><button type="submit">Autorizar verificación en este chat</button></form><div id="anticipation-grants"></div></details>
 <details><summary>Observación y memoria</summary><p id="anticipation-sources"></p><label><input id="anticipation-events" type="checkbox"> Procesar eventos autorizados de Axx</label>
 <p>Pantalla, micrófono y portapapeles no están disponibles como fuentes de anticipación en esta entrega. Las autorizaciones de voz y Computer Use se administran por separado.</p>
 <p>Los eventos se procesan localmente. Activar Full no autoriza capturas ni el envío de contenido a proveedores.</p>
 <button id="anticipation-forget" type="button">Borrar memoria de anticipación de este chat</button><div id="anticipation-history"></div><pre id="anticipation-metrics" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details>`;
 $('view-settings').prepend(section);
 for (const [id,name] of Object.entries(names)) {
  const details=document.createElement('details');details.innerHTML=`<summary>${name}</summary><form data-profile="${id}">
   <label class="setting">Iniciativa<select name="mode"><option value="OFF">Solo responder</option><option value="SHADOW">Evaluar en silencio</option><option value="SUGGEST">Sugerir</option><option value="PREPARE">Preparar</option><option value="EXECUTE">Ejecutar con permiso</option></select></label>
   <label class="setting">Interrupciones<select name="interruptions"><option value="silent">Silencioso</option><option value="cards">Tarjetas</option><option value="voice">Voz</option><option value="cards_voice">Tarjetas y voz</option></select></label>
   <label class="setting">Pausa entre propuestas, segundos<input name="cooldown_seconds" type="number" min="0" max="86400" required></label>
   <label class="setting">Máximo de interrupciones por hora<input name="max_interruptions_hour" type="number" min="0" max="60" required></label>
   <label class="setting">Retención, días<input name="retention_days" type="number" min="1" max="365" required></label><button type="submit">Guardar ${name}</button></form>`;
  $('anticipation-profiles').append(details);
 }
 const card=document.createElement('section');card.id='anticipation-card';card.hidden=true;card.setAttribute('aria-label','Propuesta de Axx');
 card.innerHTML=`<style>
 #anticipation-card{position:fixed;z-index:94;pointer-events:auto;box-sizing:border-box;width:280px;padding:12px;border:1px solid var(--line,#ffffff26);border-radius:18px;background:color-mix(in srgb,var(--surface,#18212c) var(--widget-opacity,96%),transparent);color:var(--ink,#edf2fa);box-shadow:0 6px 20px #0002;font:calc(13px * var(--interface-scale,1))/1.5 var(--interface-font,"Segoe UI",sans-serif)}
 #anticipation-card[hidden]{display:none!important}#anticipation-card p{margin:5px 0;white-space:pre-line;overflow-wrap:anywhere;max-height:115px;overflow:auto}#anticipation-card small{color:var(--secondary,#a9b6c6)}
 #anticipation-card .anticipation-actions{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}#anticipation-card button{font:inherit;color:inherit;background:var(--surface-subtle,#ffffff0a);border:1px solid var(--line,#ffffff26);border-radius:10px;min-height:44px;padding:7px 10px;cursor:pointer}#anticipation-card button:focus-visible{outline:2px solid var(--accent,#95c9fc);outline-offset:2px}#anticipation-settings label:has(input[type=checkbox]){display:block;margin:8px 0}#anticipation-settings form{margin:10px 0}#anticipation-settings [role=status]{overflow-wrap:anywhere}
 #anticipation-card summary{cursor:pointer;min-height:44px;align-content:center}#anticipation-card summary:focus-visible{outline:2px solid var(--accent,#95c9fc);outline-offset:2px}.anticipation-evidence dl{margin:0;overflow-wrap:anywhere}.anticipation-evidence dt{font-weight:600;margin-top:8px}.anticipation-evidence dd{margin:2px 0 8px;white-space:pre-wrap}#anticipation-card .anticipation-evidence-body{max-height:190px;overflow:auto;font-size:12px}
 </style><small id="anticipation-phase"></small><p id="anticipation-text" role="status" aria-live="polite"></p><div id="anticipation-actions" class="anticipation-actions"></div>`;
 document.body.append(card);
 let snapshot=null,origin=null,revision=0,loading=false,mutation=false,current=null,stopped=false,settingsKey='',missionRevision=0,missionsLoading=false,missionKey='';
 const spoken=new Set(),acknowledged=new Set();
 const task=()=>Axx.chatWorkspace.active?.id||null;
 const api=async(action,body,method='POST')=>{
  const value=await Axx.backendRequest(method,'/axx-api/anticipation/'+action,body);
  if(!value||typeof value!=='object'||value.error)throw Error(value?.error?.message||'No se pudo consultar la anticipación.');
  return value;
 };
 const notice=e=>{$('anticipation-status').textContent=e.message||String(e);};
 function changed(){Axx.resident?.schedule();void Axx.app?.updateHitMap?.();}
 function hide(){current=null;if(!card.hidden){card.hidden=true;changed();}}
 function busy(){
  const c=Axx.companion,s=Axx.symbiosis;
  return Boolean(Axx.chatWorkspace.busy||c?.pending||c?.externalBusy||c?.dictating||c?.speaking||Axx.commandLibrary?.busy||Axx.nativeVoice?.activeCapture||s?.liveActive||['starting','listening','stopping'].includes(s?.dictation?.state)||Axx.voice13?.status==='listening'||[s?.reader,Axx.voice13?.reader].some(r=>['starting','speaking','paused'].includes(r?.state))||Axx.magicPen?.isOpen()||Axx.quickReply?.active||Axx.resident?.drag);
 }
 function preferences(){return snapshot?.effective_profile===null?{}:snapshot?.profiles?.[snapshot.effective_profile||snapshot.profile]||{};}
 function allowSurprises(){const p=preferences();return !stopped&&!!snapshot&&!snapshot.paused&&!snapshot.observation_paused&&snapshot.sources?.events===true&&!['OFF','SHADOW'].includes(p.mode)&&['voice','cards_voice'].includes(p.interruptions);}
 function button(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.disabled=mutation;b.onclick=()=>void run(fn);return b;}
 async function run(fn){
  if(mutation)return;mutation=true;
  let failure;
  try{await fn();await refresh(true);}catch(e){failure=e;}finally{mutation=false;renderSettings(!!failure);renderCard();if(failure)notice(failure);}
 }
 async function configure(patch){await api('configure',patch);stopped=false;}
 const stale=row=>row.context_state==='stale'||row.state==='EXPIRED'||!row.preparation_complete&&['DETECTED','PREPARED','AWAITING_APPROVAL'].includes(row.state)&&Number.isFinite(row.expires_at)&&row.expires_at*1000<=Date.now();
 function explanation(row){
  const details=document.createElement('details');details.className='anticipation-evidence';details.dataset.suggestionId=row.suggestion_id;
  const summary=document.createElement('summary');summary.textContent='¿Por qué?';
  const list=document.createElement('dl');
  const add=(label,text)=>{const name=document.createElement('dt'),value=document.createElement('dd');name.textContent=label;value.textContent=text;list.append(name,value);};
  const provenance=row.provenance||{},assessment=row.assessment||{},refs=[];
  if(row.initiative_chain?.root_event_id)refs.push('Evento registrado: '+row.initiative_chain.root_event_id);
  if(row.plan?.source_operation_id)refs.push('Operación de origen: '+row.plan.source_operation_id);
  if(row.plan?.expected_sha256)refs.push('SHA-256 de referencia: '+row.plan.expected_sha256);
  if(Number.isInteger(row.plan?.last_verified_step))refs.push('Último paso verificado: '+(row.plan.last_verified_step<0?'Ninguno':row.plan.last_verified_step+1));
  for(const item of row.evidence||[])refs.push(JSON.stringify(item));
  if(row.state==='VERIFIED'&&row.result?.state==='succeeded'&&row.result?.postconditions_passed===true){
   for(const file of row.result.output?.files||[])if(file.sha256)refs.push('SHA-256 observado: '+file.sha256+(file.path?' · '+file.path:''));
   if(row.result.output?.sha256)refs.push('SHA-256 observado: '+row.result.output.sha256);
  }
  add('Observado',refs.length?refs.join('\n'):'Esta propuesta no adjunta referencias de observación.');
  const methods={registered_generated_artifact_rule:'Se propone comprobar el archivo mediante la regla registrada de archivo generado.',verified_checkpoint:'Se propone preparar la continuación desde un punto de recuperación verificado.',repeated_verified_skill:'Se propone preparar una habilidad a partir de ejecuciones verificadas anteriores.'};
  add('Inferido',methods[assessment.likelihood?.method]||(assessment.likelihood?.method?'Método registrado: '+assessment.likelihood.method:'No se adjuntó el motivo de esta propuesta.'));
  const actors={user:'Usuario',axx:'Axx',automation:'Otra automatización',system:'Sistema operativo'},origins={direct_instruction:'Orden directa',manual_action:'Acción manual',suggestion_accepted:'Propuesta aceptada',autonomous_routine:'Rutina autónoma',external_process:'Proceso externo',suggestion:'Propuesta de Axx'};
  add('Procedencia','Actor: '+(actors[provenance.actor]||provenance.actor||'No registrado')+'\nOrigen: '+(origins[provenance.origin]||provenance.origin||'No registrado')+'\nCausa: '+(provenance.causation_id||'No registrada'));
  if(provenance.human_preference_evidence===false)add('Preferencias','Este evento no acredita una preferencia del usuario.');
  const grant=(snapshot?.grants||[]).find(g=>g.grant_id===row.grant_id&&g.task_id===row.task_id);
  if(row.approval==='manual'&&row.accepted_hash===row.plan_hash)add('Confirmado por ti','Aceptaste esta versión exacta del plan.');
  else if(grant)add('Permiso registrado',grant.root+' · '+(grant.revoked?'Revocado':grant.expires_at===null?'Hasta revocación':new Date(grant.expires_at*1000).toLocaleString())+'. Se revalida antes de ejecutar.');
  else add('Autorización','Esta propuesta no adjunta una aceptación exacta ni un permiso persistente registrado.');
  if(row.feedback?.corrections>0||row.feedback?.usefulness==='corrected')add('Corregido por ti','El resultado recibió correcciones; la aceptación no acredita utilidad completa.');
  else if(row.feedback?.usefulness==='confirmed')add('Confirmado por ti','Confirmaste la utilidad del resultado.');
  else add('Utilidad','Sin confirmación de utilidad. Aceptar un plan no confirma su resultado.');
  if(stale(row))add('Desactualizado','El contexto o la vigencia de esta propuesta dejó de ser válido. Hace falta una preparación nueva.');
  else if(Number.isFinite(row.expires_at))add('Vigencia','Caduca: '+new Date(row.expires_at*1000).toLocaleString());
  if(row.initiative_chain)add('Límite de iniciativa','Profundidad: '+row.initiative_chain.depth+' · Presupuesto: '+row.initiative_chain.budget+' · Parada: '+row.initiative_chain.stop_condition);
  const body=document.createElement('div');body.className='anticipation-evidence-body';body.append(list);details.append(summary,body);
  if(['VERIFIED','FAILED'].includes(row.state)||row.preparation_complete){
   body.append(button('Me resultó útil',()=>api('feedback',{suggestion_id:row.suggestion_id,action:'useful'})),button('Necesita corrección',()=>api('feedback',{suggestion_id:row.suggestion_id,action:'correction'})));
  }
  details.addEventListener('toggle',changed);return details;
 }
 async function loadMissions(){
  if(!$('anticipation-mission').open||missionsLoading)return;
  const selected=task(),project=Axx.skillLibrary?.project()||Axx.companion.data?.prefs?.skillProject||'',token=++missionRevision;
  if(!selected){$('anticipation-missions').replaceChildren();$('anticipation-mission-status').textContent='Selecciona un chat.';return;}
  missionsLoading=true;
  try{
   const result=await Axx.backendRequest('GET','/axx-api/learning/plans?project_id='+encodeURIComponent(project));
   if(token!==missionRevision||selected!==task()||project!==(Axx.skillLibrary?.project()||Axx.companion.data?.prefs?.skillProject||''))return;
   if(result?.error||!Array.isArray(result?.plans))throw Error(result?.error?.message||'No se pudo consultar la misión.');
   const plans=result.plans.filter(p=>p.conversation_id===selected&&p.mission?.scope?.task_id===selected),host=$('anticipation-missions'),key=JSON.stringify([selected,project,plans]);
   if(missionKey===key)return;missionKey=key;
   const expanded=new Set([...host.querySelectorAll('details[open]')].map(n=>n.dataset.missionId));host.replaceChildren();
   $('anticipation-mission-status').textContent=plans.length?plans.length+' planes de este chat · Proyecto: '+(project||'Personal'):'Este chat todavía no tiene un plan de misión persistente.';
   for(const plan of plans){
    const mission=plan.mission,article=document.createElement('article'),title=document.createElement('strong'),progress=document.createElement('p');
    const labels={awaiting_approval:'Pendiente de aprobación',running:'En curso',paused:'En pausa',pausing:'Pausa solicitada',cancelled:'Cancelada',unknown:'Pendiente de reconciliación',expired:'Requiere revisión',blocked:'Bloqueada',needs_input:'Necesita datos',interrupted:'Interrumpida',waiting_capacity:'Espera un modelo apto',waiting_capability:'Espera una capacidad'};
    title.textContent=mission.objective||plan.request||'Misión';
    progress.textContent=(mission.completed===true?'Completada y verificada':mission.state==='succeeded'?'Resultado recibido; objetivo pendiente':labels[mission.state]||mission.state)+' · '+(mission.verified_steps||[]).length+'/'+(plan.steps||[]).length+' pasos verificados';
    const details=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('dl');summary.textContent='Objetivo, límites y evidencia';
    const add=(label,value)=>{if(value===undefined||value===null)return;const name=document.createElement('dt'),text=document.createElement('dd');name.textContent=label;text.textContent=typeof value==='string'?value:JSON.stringify(value,null,2);list.append(name,text);};
    add('Entregables',mission.deliverables);add('Destino',mission.destination);add('Condiciones de éxito',mission.success_conditions);add('Recursos',mission.scope.resources);add('Dependencias',mission.dependencies);add('Pasos pendientes',(mission.pending_steps||[]).map(index=>index+1));add('Bloqueos',mission.blockers);
    add('Permiso',mission.permission?.exact_plan_approved?'Versión exacta del plan aprobada.':'Esta versión del plan no consta aprobada.');
    if(mission.permission?.automatic_future_plans_authorized===false)add('Iniciativas futuras','Este plan no concede permiso para futuros planes autónomos.');
    const budget=mission.budget;
    if(budget)add('Presupuesto','Límite de pasos: '+budget.step_limit+'\nConsultas al modelo: '+budget.model_calls_used+'/'+budget.model_call_limit+'\nConsultas restantes: '+budget.model_calls_remaining);
    add('Condición de parada',mission.stop_condition==='verified_goal_or_cancellation'?'Resultado verificado o cancelación.':mission.stop_condition);add('Revisión',mission.revision);
    add('Utilidad',mission.user_confirmed_usefulness===true?'Confirmada por ti; no sustituye las verificaciones de ejecución.':'Sin confirmación de utilidad.');
    details.className='anticipation-evidence';details.dataset.missionId=mission.mission_id;details.open=expanded.has(mission.mission_id);details.append(summary,list);
    const review=button('Revisar plan',()=>reviewPlan({learning_plan_id:plan.operation_id,task_id:selected}));review.disabled=false;article.append(title,progress,details,review);host.append(article);
   }
  }catch(e){if(token===missionRevision)$('anticipation-mission-status').textContent=e.message||String(e);}
  finally{if(token===missionRevision)missionsLoading=false;}
 }
 function renderSettings(fill=false){
  if(!snapshot)return;
  const key=JSON.stringify([task(),snapshot.profile,snapshot.paused,snapshot.observation_paused,snapshot.profiles,snapshot.sources,snapshot.scopes,snapshot.grants,snapshot.suggestions,snapshot.metrics,mutation]);
  if(!fill&&settingsKey===key)return;settingsKey=key;
  $('anticipation-profile').value=snapshot.profile;
  $('anticipation-pause').textContent=snapshot.paused?'Reanudar iniciativas':'Pausar iniciativas';
  $('anticipation-observation').textContent=snapshot.observation_paused?'Reanudar observación':'Pausar observación';
  $('anticipation-status').textContent=names[snapshot.profile]+(snapshot.paused?' · Iniciativas pausadas':'')+(snapshot.observation_paused?' · Observación pausada':'')+' · '+(task()?'Chat: '+(Axx.chatWorkspace.active?.title||task()):'Selecciona un chat');
  for(const form of $('anticipation-profiles').querySelectorAll('form')){
   if(!fill&&(form.dataset.dirty==='true'||form.contains(document.activeElement)))continue;
   for(const [key,value] of Object.entries(snapshot.profiles?.[form.dataset.profile]||{}))if(form.elements.namedItem(key))form.elements.namedItem(key).value=value;
   form.dataset.dirty='false';
  }
  $('anticipation-events').checked=snapshot.sources?.events===true;
  $('anticipation-sources').textContent='Fuentes activas: '+(snapshot.observation_paused?'ninguna (pausa global)':snapshot.sources?.events?'eventos autorizados':'ninguna')+'.';
  const scopes=$('anticipation-scopes');scopes.replaceChildren();
  for(const [i,scope] of (snapshot.scopes||[]).entries()){
   const p=document.createElement('p');p.textContent=(scope.exclude?'Excluido':names[scope.profile]||scope.profile)+' · '+(scope.task_id||'Todos los chats')+' · '+(scope.root||'Todos los recursos');
   p.append(button('Quitar ámbito',()=>configure({scopes:snapshot.scopes.filter((_,j)=>i!==j)})));scopes.append(p);
  }
  const grants=$('anticipation-grants');grants.replaceChildren();
  for(const grant of snapshot.grants||[]){
   if(grant.task_id!==task())continue;
   const p=document.createElement('p');p.textContent=grant.root+' · '+(grant.revoked?'Revocado':grant.expires_at===null?'Hasta revocación':new Date(grant.expires_at*1000).toLocaleString());
   if(!grant.revoked)p.append(button('Revocar',()=>api('revoke',{grant_id:grant.grant_id})));grants.append(p);
  }
  const history=$('anticipation-history'),expanded=new Set([...history.querySelectorAll('details[open]')].map(n=>n.dataset.suggestionId));history.replaceChildren();
  for(const row of snapshot.suggestions||[]){
   if(row.task_id!==task())continue;
   const p=document.createElement('p');p.textContent=(states[row.state]||row.state)+' · '+(row.title||row.routine_id);
   if(row.state==='SUPPRESSED')p.append(button('Volver a permitir',()=>api('feedback',{suggestion_id:row.suggestion_id,action:'restore'})));
   const why=explanation(row);why.open=expanded.has(row.suggestion_id);history.append(p,why);
  }
  $('anticipation-metrics').textContent=JSON.stringify(snapshot.metrics||{},null,2);
 }
 function renderCard(){
  if(!snapshot||origin!==task()||snapshot.paused||stopped||document.hidden||busy()){hide();return;}
  const rows=(snapshot.suggestions||[]).filter(r=>r.task_id===task()&&r.visible===true&&!['DISMISSED','SUPPRESSED','CANCELLED','EXPIRED'].includes(r.state));
  const row=rows.find(r=>['AWAITING_APPROVAL','PREPARED','DETECTED','EXECUTING'].includes(r.state))||rows[0];
  if(!row){hide();return;}
  const prefs=row.policy||preferences();
  if(['OFF','SHADOW'].includes(prefs.mode)||prefs.interruptions==='silent'){hide();return;}
  const verified=row.state==='VERIFIED'&&row.result?.state==='succeeded'&&row.result?.postconditions_passed===true;
  const phase=stale(row)?'Desactualizado':row.state==='VERIFIED'&&!verified?'Resultado recibido; falta evidencia':states[row.state]||row.state;
  const message=row.state==='VERIFIED'&&!verified?'No se recibió evidencia de verificación.':row.message;
  const text=(row.title||'Verificar archivo')+(message?'\n'+message:'')+(row.plan?.inputs?.path?'\n'+row.plan.inputs.path:'');
  const key=[row.suggestion_id,row.state,row.plan_hash,row.preparation_complete,text,phase,mutation,JSON.stringify([row.assessment,row.provenance,row.evidence,row.feedback,row.plan,row.accepted_hash,row.grant_id,row.expires_at,row.result?.output])].join('/');current=row;
  if(card.dataset.renderKey!==key){
   const expanded=card.dataset.suggestionId===row.suggestion_id&&$('anticipation-why')?.open;
   card.dataset.renderKey=key;card.dataset.suggestionId=row.suggestion_id;$('anticipation-phase').textContent=phase;$('anticipation-text').textContent=text;
   const actions=$('anticipation-actions');actions.replaceChildren();
   if(['AWAITING_APPROVAL','PREPARED'].includes(row.state)&&!row.preparation_complete&&!stale(row)){
    const label=({resume_task:'Preparar reanudación',prepare_routine:'Preparar rutina'})[row.candidate_kind]||'Verificar';
    actions.append(button(label,()=>api('accept',{suggestion_id:row.suggestion_id,plan_hash:row.plan_hash})));
   }
   if(row.preparation_complete&&row.learning_plan_id)actions.append(button('Revisar plan',()=>reviewPlan(row)));
   if(row.state==='EXECUTING')actions.append(button('Detener',()=>stop(row.suggestion_id)));
   actions.append(button('Descartar',()=>api('feedback',{suggestion_id:row.suggestion_id,action:'dismiss'})));
   if(row.routine_id)actions.append(button('No volver a sugerir',()=>api('feedback',{suggestion_id:row.suggestion_id,action:'suppress'})));
   $('anticipation-why')?.remove();const why=explanation(row);why.id='anticipation-why';why.open=!!expanded;card.append(why);
  }
  if(['voice','cards_voice'].includes(prefs.interruptions)&&!spoken.has(row.suggestion_id+'/'+row.state)){
   spoken.add(row.suggestion_id+'/'+row.state);
   if(row.state!=='VERIFIED'||verified)Axx.companion?.speakReply?.(phase+'. '+(row.message||row.title||'Verificación de archivo.'));
  }
  const hidden=prefs.interruptions==='voice';if(card.hidden!==hidden){card.hidden=hidden;changed();}
  if(!acknowledged.has(row.suggestion_id)){acknowledged.add(row.suggestion_id);void api('feedback',{suggestion_id:row.suggestion_id,action:'shown'}).catch(e=>{acknowledged.delete(row.suggestion_id);notice(e);});}
 }
 async function reviewPlan(row){
  const lib=Axx.commandLibrary;if(!lib||lib.busy||lib.operation&&lib.operation.operation_id!==row.learning_plan_id)throw Error('Revisa primero la acción pendiente.');
  const plan=await Axx.backendRequest('GET','/axx-api/learning/plan?id='+encodeURIComponent(row.learning_plan_id));
  if(plan?.operation_id!==row.learning_plan_id||plan.conversation_id!==task()||row.task_id!==task())throw Error('El plan no corresponde a este chat.');
  lib.lastOperation=plan;lib.operation=['awaiting_approval','running'].includes(plan.state)?plan:null;
  lib.renderOperation(plan);Axx.companion.openChat();
 }
 async function refresh(fill=false){
  const selected=task();if(selected!==origin){origin=selected;snapshot=null;hide();$('anticipation-grants').replaceChildren();$('anticipation-history').replaceChildren();$('anticipation-missions').replaceChildren();$('anticipation-mission-status').textContent='';++missionRevision;missionsLoading=false;missionKey='';$('anticipation-status').textContent='Cargando el ámbito de este chat…';++revision;loading=false;}
  if(loading&&!fill)return;
  const token=++revision;loading=true;
  try{
   const value=await api('status',{task_id:selected});
   if(token!==revision||selected!==task())return;
   snapshot=value;renderSettings(fill);renderCard();void loadMissions();
  }catch(e){if(token===revision){snapshot=null;hide();notice(e);}}
  finally{if(token===revision)loading=false;}
 }
 async function stop(id){stopped=true;hide();++revision;loading=false;await api('cancel',id?{suggestion_id:id}:{});await refresh();}
 function layout(g,size,add){
  renderCard();if(card.hidden)return;
  const width=Math.min(Math.round(280*(Axx.interfaceTheme?.widgetScale||1)),g.workWidth-24),height=Math.min(card.scrollHeight||180,g.workHeight-24);
  const gap=size*.34+14,above=g.spaceAbove>=gap+height||g.spaceAbove>g.spaceBelow;
  const x=Math.max(-g.spaceLeft+12,Math.min(g.spaceRight-width-12,-width/2));
  const y=Math.max(-g.spaceAbove+12,Math.min(g.spaceBelow-height-12,above?-gap-height:gap));
  add('anticipation-card',Math.round(x),Math.round(y),width,height);
 }
 $('anticipation-profile').onchange=()=>void run(()=>configure({profile:$('anticipation-profile').value}));
 $('anticipation-pause').onclick=()=>void run(()=>configure({paused:!snapshot?.paused}));
 $('anticipation-observation').onclick=()=>void run(()=>configure({observation_paused:!snapshot?.observation_paused}));
 $('anticipation-events').onchange=()=>void run(()=>configure({sources:{events:$('anticipation-events').checked}}));
 $('anticipation-mission').addEventListener('toggle',()=>{if($('anticipation-mission').open)void loadMissions();});
 for(const form of $('anticipation-profiles').querySelectorAll('form')){
  form.oninput=()=>{form.dataset.dirty='true';};
  form.onsubmit=e=>{e.preventDefault();const settings=Object.fromEntries(new FormData(form));for(const key of ['cooldown_seconds','max_interruptions_hour','retention_days'])settings[key]=Number(settings[key]);void run(()=>configure({profiles:{[form.dataset.profile]:settings}}));};
 }
 $('anticipation-scope-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  const scoped=$('anticipation-scope-task').checked,root=$('anticipation-scope-root').value.trim();
  if(scoped&&!task())throw Error('Selecciona un chat para guardar su ámbito.');
  if(!scoped&&!root)throw Error('Indica una carpeta o limita el ámbito al chat actual.');
  const scope={...(scoped?{task_id:task()}:{}),...(root?{root}:{}),profile:$('anticipation-scope-profile').value,exclude:$('anticipation-scope-exclude').checked};
  await configure({scopes:[...(snapshot?.scopes||[]),scope]});
 });};
 $('anticipation-grant-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  if(!task())throw Error('Selecciona el chat que recibirá este permiso.');
  const expiry=$('anticipation-grant-expiry').value;
  await api('grant',{task_id:task(),capability:'verify_artifact',root:$('anticipation-grant-root').value.trim(),expires_at:expiry==='persistent'?null:Date.now()/1000+Number(expiry),observe_events:$('anticipation-grant-events').checked});
 });};
 $('anticipation-forget').onclick=()=>void run(async()=>{if(!task())throw Error('Selecciona un chat.');if(confirm('¿Borrar únicamente los eventos y propuestas aprendidos en este chat? Los permisos y archivos se conservan.'))await api('forget',{task_id:task()});});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.repeat)void stop().catch(notice);},true);
 void Axx.app?.bridge?.listen?.('axx-cancel',()=>{void stop().catch(notice);});
 const renderChat=Axx.companion.renderChat.bind(Axx.companion);
 Axx.companion.renderChat=function(...args){const value=renderChat(...args);if(origin!==task()){snapshot=null;hide();void refresh();}else renderCard();return value;};
 const timer=setInterval(()=>void refresh(),3000);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)hide();else void refresh();});
 window.addEventListener('pagehide',()=>{clearInterval(timer);++revision;hide();});
 Axx.anticipation={refresh,layout,cancel:stop,allowSurprises,get state(){return snapshot;},get current(){return current;}};
 void refresh(true);
})(window.Axx);
