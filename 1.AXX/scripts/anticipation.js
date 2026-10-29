/* Profiles share the existing backend, chat, voice and resident surface owners. */
(function (Axx) {
 'use strict';
 if (!Axx?.isNative() || !Axx.chatWorkspace || !document.getElementById('view-settings')) return;
 const $ = id => document.getElementById(id), names = {discreto:'Discreto',copiloto:'Copiloto',full:'Full'};
 const resourceFields=[['max_events_tick','Eventos por ciclo',1,100],['max_entries_scan','Entradas por exploración',1,2000],['max_file_bytes','Tamaño máximo por archivo, bytes',1024,536870912],['max_tick_ms','Tiempo por ciclo, ms',50,5000],['max_cpu_ms_tick','CPU por ciclo, ms',10,1000]];
 const weekdays=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
 const verificationLabels={integrity_only:'Integridad verificada',pdf_structure_and_text_readability:'Inspección PDF completada',media_metadata:'Metadatos comprobados',image_ocr:'Lectura OCR completada'};
 const verificationScopes={integrity_only:'Integridad por hash',pdf_structure_and_text_readability:'Estructura y legibilidad del texto PDF',media_metadata:'Metadatos multimedia',image_ocr:'Texto mediante OCR'};
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
 <label class="setting">Proyecto, opcional<input id="anticipation-scope-project" maxlength="128"></label><label class="setting">ID de aplicación, opcional<input id="anticipation-scope-application" maxlength="128"></label><label class="setting">Dispositivo, opcional<input id="anticipation-scope-device" maxlength="128" placeholder="host"></label>
 <label><input id="anticipation-scope-exclude" type="checkbox"> Excluir este ámbito de las iniciativas</label><button type="submit">Guardar ámbito</button></form><div id="anticipation-scopes"></div></details>
 <details><summary>Permisos para Full</summary><details><summary>Verificación de archivos</summary><p>Permite comprobar archivos de esta carpeta en el chat actual. Las carpetas externas requieren una fuente autorizada para observar y conservar metadatos. No autoriza cambios, envíos ni control del escritorio.</p>
 <form id="anticipation-grant-form"><label class="setting">Ámbito<select id="anticipation-grant-source"><option value="">Carpeta del espacio de ensayo</option></select></label><label class="setting">Carpeta autorizada<input id="anticipation-grant-root" maxlength="4096" required placeholder="C:\\Proyecto\\ensayo"></label>
 <label class="setting">Vigencia<select id="anticipation-grant-expiry"><option value="3600">Una hora</option><option value="86400">Un día</option><option value="persistent">Hasta revocación</option></select></label>
 <label><input id="anticipation-grant-events" type="checkbox"> Permitir verificación automática de eventos ya autorizados en este ámbito</label><p id="anticipation-grant-source-status"></p><button type="submit">Autorizar verificación en este chat</button></form></details>
 <details id="anticipation-mission-permission"><summary>Acciones acotadas de misión</summary><p id="anticipation-mission-permission-status" role="status"></p><p>Elige acciones concretas. Las escrituras crean archivos nuevos en el espacio de ensayo; las lecturas adicionales requieren raíces explícitas. Cada plan se revalida dentro de este permiso.</p>
 <form id="anticipation-mission-grant-form"><label class="setting">Carpeta de destino dentro del espacio de ensayo<input id="anticipation-mission-grant-root" maxlength="4096" required></label><label class="setting">Carpetas adicionales de solo lectura, una por línea<textarea id="anticipation-mission-read-roots" maxlength="8192"></textarea></label>
 <div id="anticipation-mission-commands"></div><label class="setting">Alcance temporal<select id="anticipation-mission-lifetime"></select></label><label class="setting">Vigencia máxima<select id="anticipation-mission-expiry"><option value="3600">Una hora</option><option value="86400">Un día</option><option value="persistent">Hasta finalizar el alcance o revocarlo</option></select></label>
 <div id="anticipation-mission-plan-scope" hidden><label class="setting">Misión de este chat<select id="anticipation-mission-grant-plan"><option value="">Selecciona una misión</option></select></label><p id="anticipation-mission-plan-hash"></p><button id="anticipation-mission-review" type="button">Revisar plan de esta misión</button></div>
 <details><summary>Restricciones exactas de parámetros</summary><p>Opcional: objeto JSON por ID de comando y parámetros concretos. Los valores deben coincidir exactamente; no admite patrones ni esquemas.</p><label class="setting">Valores permitidos<textarea id="anticipation-mission-constraints" maxlength="12000" placeholder="{}"></textarea></label><pre id="anticipation-mission-parameters" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details>
 <p>No autoriza cambiar el foco, enviar entradas, ejecutar shell/MCP, enviar contenido ni borrar archivos. No autoriza consultas al modelo.</p><button id="anticipation-mission-authorize" type="submit">Autorizar estas acciones en este chat</button></form></details><div id="anticipation-grants"></div></details>
 <details><summary>Observación y memoria</summary><p id="anticipation-sources"></p><label><input id="anticipation-events" type="checkbox"> Procesar eventos autorizados de Axx</label>
 <label><input id="anticipation-folders" type="checkbox"> Habilitar observación de carpetas seleccionadas</label><label><input id="anticipation-applications" type="checkbox"> Habilitar observación de aplicaciones seleccionadas</label>
 <details><summary>Fuentes locales de este chat</summary><p>La fuente debe estar habilitada y tener un ámbito autorizado. Observar, conservar metadatos y enviar contenido son decisiones separadas.</p>
 <form id="anticipation-target-form"><label class="setting">Fuente<select id="anticipation-target-source"><option value="folder">Carpeta</option><option value="application">Aplicación</option></select></label>
 <label class="setting" id="anticipation-target-folder">Carpeta absoluta<input id="anticipation-target-root" maxlength="4096" required></label><label class="setting" id="anticipation-target-app" hidden>Proceso exacto<input id="anticipation-target-process" maxlength="80" placeholder="programa.exe" disabled></label>
 <label class="setting">Proyecto, opcional<input id="anticipation-target-project" maxlength="128"></label><label class="setting">ID de aplicación, opcional<input id="anticipation-target-application" maxlength="128"></label><label class="setting">Dispositivo<input id="anticipation-target-device" maxlength="128" value="host" required></label>
 <label class="setting">Vigencia<select id="anticipation-target-expiry"><option value="3600">Una hora</option><option value="86400">Un día</option><option value="persistent">Hasta revocación</option></select></label>
 <label><input id="anticipation-target-observe" type="checkbox" checked> Observar dentro de este ámbito</label><label><input id="anticipation-target-retain" type="checkbox"> Conservar metadatos de los cambios</label><label><input type="checkbox" disabled> Enviar a proveedores (no disponible)</label><button type="submit">Guardar fuente en este chat</button></form>
 <div id="anticipation-targets"></div><p id="anticipation-source-runtime" role="status"></p><div id="anticipation-source-observations"></div></details>
 <p>Pantalla, micrófono y portapapeles no están disponibles como fuentes de anticipación en esta entrega. Las autorizaciones de voz y Computer Use se administran por separado.</p>
 <p>Los eventos se procesan localmente. Activar Full no autoriza capturas ni el envío de contenido a proveedores.</p>
 <details><summary>Alcance de los verificadores</summary><div id="anticipation-verifiers"></div><p>Un hash comprueba integridad. No acredita contenido, apariencia ni cumplimiento del objetivo.</p></details>
 <button id="anticipation-forget" type="button">Borrar memoria de anticipación de este chat</button><div id="anticipation-history"></div><pre id="anticipation-metrics" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details>`;
 $('view-settings').prepend(section);
 for (const [id,name] of Object.entries(names)) {
  const details=document.createElement('details');details.innerHTML=`<summary>${name}</summary><form data-profile="${id}">
   <label class="setting">Iniciativa<select name="mode"><option value="OFF">Solo responder</option><option value="SHADOW">Evaluar en silencio</option><option value="SUGGEST">Sugerir</option><option value="PREPARE">Preparar</option><option value="EXECUTE">Ejecutar con permiso</option></select></label>
   <label class="setting">Interrupciones<select name="interruptions"><option value="silent">Silencioso</option><option value="cards">Tarjetas</option><option value="voice">Voz</option><option value="cards_voice">Tarjetas y voz</option></select></label>
   <label class="setting">Pausa entre propuestas, segundos<input name="cooldown_seconds" type="number" min="0" max="86400" required></label>
   <label class="setting">Máximo de interrupciones por hora<input name="max_interruptions_hour" type="number" min="0" max="60" required></label>
   <label class="setting">Retención, días<input name="retention_days" type="number" min="1" max="365" required></label>
   <details><summary>Frecuencia, horario y recursos</summary><label class="setting">Intervalo de observación, segundos<input name="cadence_seconds" type="number" min="5" max="3600" required></label>
   <label><input name="schedule_enabled" type="checkbox"> Usar un horario</label><div data-schedule><label class="setting">Zona horaria IANA<input name="schedule_timezone" maxlength="80" required></label><label class="setting">Desde<input name="schedule_start" type="time" required></label><label class="setting">Hasta<input name="schedule_end" type="time" required></label>
   <fieldset><legend>Días</legend>${weekdays.map((day,i)=>`<label><input type="checkbox" name="schedule_days" value="${i}">${day}</label>`).join('')}</fieldset></div>
   ${resourceFields.map(([key,label,min,max])=>`<label class="setting">${label}<input name="resource_${key}" type="number" min="${min}" max="${max}" required></label>`).join('')}</details>
   <button type="submit">Guardar ${name}</button></form>`;
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
 let snapshot=null,origin=null,revision=0,loading=false,mutation=false,current=null,stopped=false,settingsKey='',missionRevision=0,missionsLoading=false,missionKey='',missionPlans=[],missionProject='';
 const lifetimes={one_action:'Una acción permitida',session:'Esta sesión de Axx',mission:'Esta misión exacta',until_revoked:'Hasta revocación'};
 const spoken=new Set(),acknowledged=new Set();
 const task=()=>Axx.chatWorkspace.active?.id||null;
 const project=()=>Axx.skillLibrary?.project()||Axx.companion.data?.prefs?.skillProject||'';
 function syncSchedule(form){for(const input of form.querySelectorAll('[data-schedule] input'))input.disabled=!form.elements.schedule_enabled.checked;}
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
  const scope=row.verification_scope||row.result?.verification_scope||row.plan?.verification_scope;
  if(scope)add('Alcance de la comprobación',verificationScopes[scope]||scope);
  if(row.semantic_verified===false||row.result?.semantic_verified===false)add('Límite','El significado del contenido y la apariencia no constan verificados.');
  if(row.verifier_reason)add('Verificador',row.verifier_reason);
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
  if(!($('anticipation-mission').open||$('anticipation-mission-permission').open)||missionsLoading)return;
  const selected=task(),currentProject=project(),token=++missionRevision;
  if(!selected){$('anticipation-missions').replaceChildren();$('anticipation-mission-status').textContent='Selecciona un chat.';return;}
  missionsLoading=true;
  try{
   const result=await Axx.backendRequest('GET','/axx-api/learning/plans?project_id='+encodeURIComponent(currentProject));
   if(token!==missionRevision||selected!==task()||currentProject!==project())return;
   if(result?.error||!Array.isArray(result?.plans))throw Error(result?.error?.message||'No se pudo consultar la misión.');
   const plans=result.plans.filter(p=>p.conversation_id===selected&&p.mission?.scope?.task_id===selected&&(p.project_id??p.mission.scope.project_id??'')===currentProject),host=$('anticipation-missions'),key=JSON.stringify([selected,currentProject,result.plans]);missionPlans=plans;missionProject=currentProject;renderMissionGrantPlans();
   if(missionKey===key)return;missionKey=key;
   const expanded=new Set([...host.querySelectorAll('details[open]')].map(n=>n.dataset.missionId));
   const drafts=new Map([...host.querySelectorAll('[data-dependency-id]')].map(form=>[form.dataset.dependencyId,{open:form.parentElement.open,dirty:form.dataset.dirty==='true',selected:[...form.querySelector('select').selectedOptions].map(o=>o.value)}]));host.replaceChildren();
   $('anticipation-mission-status').textContent=plans.length?plans.length+' planes de este chat · Proyecto: '+(currentProject||'Personal'):'Este chat todavía no tiene un plan de misión persistente.';
   for(const plan of plans){
    const mission=plan.mission,article=document.createElement('article'),title=document.createElement('strong'),progress=document.createElement('p');
    const labels={awaiting_approval:'Pendiente de aprobación',running:'En curso',paused:'En pausa',pausing:'Pausa solicitada',cancelled:'Cancelada',unknown:'Pendiente de reconciliación',expired:'Requiere revisión',blocked:'Bloqueada',needs_input:'Necesita datos',interrupted:'Interrumpida',waiting_capacity:'Espera un modelo apto',waiting_capability:'Espera una capacidad',waiting_dependency:'Espera otra misión verificada'};
    title.textContent=mission.objective||plan.request||'Misión';
    progress.textContent=(mission.completed===true?'Completada y verificada':mission.state==='succeeded'?'Resultado recibido; objetivo pendiente':labels[mission.state]||mission.state)+' · '+(mission.verified_steps||[]).length+'/'+(plan.steps||[]).length+' pasos verificados';
    const details=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('dl');summary.textContent='Objetivo, límites y evidencia';
    const add=(label,value)=>{if(value===undefined||value===null)return;const name=document.createElement('dt'),text=document.createElement('dd');name.textContent=label;text.textContent=typeof value==='string'?value:JSON.stringify(value,null,2);list.append(name,text);};
    add('Entregables',mission.deliverables);add('Destino',mission.destination);add('Condiciones de éxito',mission.success_conditions);add('Recursos',mission.scope.resources);add('Misiones requeridas',mission.mission_dependencies);add('Pasos pendientes',(mission.pending_steps||[]).map(index=>index+1));add('Bloqueos',mission.blockers);
    add('Permiso',mission.permission?.exact_plan_approved?'Versión exacta del plan aprobada.':'Esta versión del plan no consta aprobada.');
    if(mission.permission?.automatic_future_plans_authorized===false)add('Iniciativas futuras','Este plan no concede permiso para futuros planes autónomos.');
    const budget=mission.budget;
    if(budget)add('Presupuesto','Límite de pasos: '+budget.step_limit+'\nConsultas al modelo: '+budget.model_calls_used+'/'+budget.model_call_limit+'\nConsultas restantes: '+budget.model_calls_remaining);
    add('Condición de parada',mission.stop_condition==='verified_goal_or_cancellation'?'Resultado verificado o cancelación.':mission.stop_condition);add('Revisión',mission.revision);
    add('Utilidad',mission.user_confirmed_usefulness===true?'Confirmada por ti; no sustituye las verificaciones de ejecución.':'Sin confirmación de utilidad.');
    const dependencies=document.createElement('details'),dependencySummary=document.createElement('summary'),form=document.createElement('form'),label=document.createElement('label'),select=document.createElement('select');dependencySummary.textContent='Esperar otras misiones de este proyecto';select.multiple=true;select.size=4;select.setAttribute('aria-label','Misiones requeridas');
    const draft=drafts.get(plan.operation_id),linked=new Set(draft?.dirty?draft.selected:(mission.mission_dependencies||[]).map(d=>d.operation_id));
    for(const other of result.plans){
     if(other.operation_id===plan.operation_id||(other.project_id??other.mission?.scope?.project_id??'')!==currentProject)continue;
     const option=document.createElement('option');option.value=other.operation_id;option.textContent=(other.mission?.objective||other.request||other.operation_id)+' · '+(other.mission?.completed===true?'Verificada':'Pendiente');option.selected=linked.has(other.operation_id);select.append(option);
    }
    label.textContent='Selecciona hasta 16 misiones que deben completarse antes. Guardar los enlaces no aprueba su ejecución.';label.className='setting';label.append(select);const save=document.createElement('button');save.type='submit';save.textContent='Guardar dependencias';form.append(label,save);form.dataset.dependencyId=plan.operation_id;form.dataset.dirty=String(!!draft?.dirty);dependencies.open=!!draft?.open;select.onchange=()=>{form.dataset.dirty='true';};
    form.onsubmit=e=>{e.preventDefault();void run(async()=>{const selected=[...select.selectedOptions].map(o=>o.value);if(selected.length>16)throw Error('Selecciona hasta 16 misiones requeridas.');const result=await Axx.backendRequest('POST','/axx-api/learning/dependencies',{operation_id:plan.operation_id,dependencies:selected,plan_hash:plan.plan_hash||mission.plan_hash});if(!result||result.error)throw Error(result?.error?.message||'No se pudieron guardar las dependencias.');form.dataset.dirty='false';missionKey='';});};
    dependencies.append(dependencySummary,form);details.append(dependencies);
    details.className='anticipation-evidence';details.dataset.missionId=mission.mission_id;details.open=expanded.has(mission.mission_id);details.prepend(summary,list);
    const review=button('Revisar plan',()=>reviewPlan({learning_plan_id:plan.operation_id,task_id:selected}));review.disabled=false;article.append(title,progress,details,review);host.append(article);
   }
  }catch(e){if(token===missionRevision)$('anticipation-mission-status').textContent=e.message||String(e);}
  finally{if(token===missionRevision)missionsLoading=false;}
 }
 const externalTargets=()=>snapshot?.sources?.folders===true?(snapshot.observation_targets||[]).filter(t=>t.task_id===task()&&t.source==='folder'&&t.observe===true&&t.retain===true&&(t.expires_at===null||t.expires_at*1000>Date.now())):[];
 function syncVerificationSource(){
  const target=externalTargets().find(t=>t.id===$('anticipation-grant-source').value),root=$('anticipation-grant-root');root.readOnly=!!target;$('anticipation-grant-events').disabled=false;
  if(target){root.value=target.root;$('anticipation-grant-events').checked=false;}
  $('anticipation-grant-source-status').textContent=target?'Solo lectura de esta fuente. Se conservarán metadatos del resultado; no el texto del documento ni contenido para proveedores.':'Las carpetas externas solo aparecen si su fuente permite observar y conservar metadatos en este chat.';
 }
 function renderMissionGrantPlans(){
  const select=$('anticipation-mission-grant-plan'),key=JSON.stringify([task(),project(),missionPlans]);if(select.dataset.key===key)return;select.dataset.key=key;
  const previous=select.value,hash=select.dataset.planHash,plans=missionProject===project()?missionPlans.filter(p=>p.conversation_id===task()):[];select.replaceChildren(new Option('Selecciona una misión',''));
  for(const plan of plans)if(plan.plan_hash||plan.mission?.plan_hash)select.add(new Option(plan.mission?.objective||plan.request||plan.operation_id,plan.operation_id));
  const selected=plans.find(p=>p.operation_id===previous);
  if(selected&&(selected.plan_hash||selected.mission.plan_hash)===hash)select.value=previous;
  else{delete select.dataset.planHash;$('anticipation-mission-plan-hash').textContent=previous?'La misión cambió o dejó de estar disponible. Selecciónala y revisa de nuevo su versión.':'';}
 }
 function syncMissionLifetime(){const mission=$('anticipation-mission-lifetime').value==='mission';$('anticipation-mission-plan-scope').hidden=!mission;$('anticipation-mission-grant-plan').required=mission;$('anticipation-mission-grant-plan').disabled=!mission;}
 function renderPermissions(){
  const source=$('anticipation-grant-source'),targets=externalTargets(),sourceKey=JSON.stringify([task(),targets]);
  if(source.dataset.key!==sourceKey){const previous=source.value;source.dataset.key=sourceKey;source.replaceChildren(new Option('Carpeta del espacio de ensayo',''));for(const target of targets)source.add(new Option('Fuente de solo lectura · '+target.root,target.id));if(targets.some(t=>t.id===previous))source.value=previous;else if(previous){$('anticipation-grant-root').value='';$('anticipation-grant-events').checked=false;}syncVerificationSource();}
  const capability=snapshot.capabilities?.mission_steps,form=$('anticipation-mission-grant-form'),host=$('anticipation-mission-commands'),commands=capability?.commands||[],key=JSON.stringify([task(),capability]);
  $('anticipation-mission-authorize').disabled=capability?.available!==true;
  $('anticipation-mission-permission-status').textContent=capability?.available===true?'Acciones disponibles según los adaptadores registrados. El permiso se revalida antes de cada plan.':'Los permisos de pasos de misión no están disponibles en este backend.';
  if(host.dataset.key!==key){
   host.dataset.key=key;const checked=new Set([...host.querySelectorAll('input:checked')].map(input=>input.value));host.replaceChildren();
   const categories={inspection:'Inspección local',file_read:'Lectura e inspección local',metadata_read:'Lectura de metadatos',create_copy:'Crear copias de ensayo',new_artifact:'Crear archivos nuevos de ensayo',private_office_copy:'Crear copias privadas con Office'};
   const titles={'axx.file.sha256':'Comprobar integridad SHA-256','axx.file.compare':'Comparar archivos','axx.file.find':'Buscar archivos por metadatos','axx.artifact.pdf':'Inspeccionar estructura y texto PDF','axx.artifact.media':'Leer metadatos multimedia','axx.artifact.ocr':'Leer texto de imagen mediante OCR','axx.artifact.write':'Crear archivo nuevo','axx.file.bundle':'Crear paquete nuevo','axx.office.excel.csv':'Crear copia CSV con Excel privado','axx.office.word.pdf':'Crear copia PDF con Word privado','axx.office.powerpoint.pdf':'Crear copia PDF con PowerPoint privado'};
   for(const category of [...new Set(commands.map(command=>command.category))]){
    const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=categories[category]||category;group.append(legend);
    for(const command of commands.filter(command=>command.category===category)){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=command.command_id;input.name='mission_command';input.disabled=command.available!==true;input.checked=!input.disabled&&checked.has(command.command_id);const title=Axx.commandLibrary?.commands?.find(c=>c.id===command.command_id)?.title||titles[command.command_id]||String(command.tool||command.command_id).replace(/[_.]/g,' ');label.append(input,document.createTextNode(' '+title+' · '+command.command_id+(command.available===true?'':' · No disponible: '+(command.reason||'Adaptador no disponible'))));group.append(label);}host.append(group);
   }
   const lifetime=$('anticipation-mission-lifetime'),previous=lifetime.value;lifetime.replaceChildren();for(const id of capability?.lifetimes||[])lifetime.add(new Option(lifetimes[id]||id,id));if([...lifetime.options].some(option=>option.value===previous))lifetime.value=previous;syncMissionLifetime();
  }
  if(capability?.workspace_root&&!$('anticipation-mission-grant-root').value&&!form.dataset.rootDirty)$('anticipation-mission-grant-root').value=capability.workspace_root;
  if(capability?.workspace_root&&!$('anticipation-grant-root').value&&!$('anticipation-grant-root').readOnly)$('anticipation-grant-root').value=capability.workspace_root;
  const selected=new Set([...host.querySelectorAll('input:checked:not(:disabled)')].map(input=>input.value));$('anticipation-mission-parameters').textContent=JSON.stringify(Object.fromEntries(commands.filter(command=>selected.has(command.command_id)).map(command=>[command.command_id,command.parameters||{}])),null,2);renderMissionGrantPlans();
 }
 function renderSources(){
  for(const source of ['folders','applications'])$('anticipation-'+source).checked=snapshot.sources?.[source]===true;
  const targets=snapshot.observation_targets||[],host=$('anticipation-targets'),key=JSON.stringify([task(),targets,mutation]);
  if(host.dataset.renderKey!==key){
   host.dataset.renderKey=key;host.replaceChildren();
   for(const target of targets.filter(t=>t.task_id===task())){
    const article=document.createElement('article'),description=document.createElement('p');description.textContent=(target.source==='folder'?'Carpeta: '+target.root:'Aplicación: '+target.process_name)+' · Proyecto: '+(target.project_id||'Personal')+' · Dispositivo: '+target.device_id;
    const observe=document.createElement('input'),retain=document.createElement('input'),observeLabel=document.createElement('label'),retainLabel=document.createElement('label');observe.type=retain.type='checkbox';observe.checked=target.observe;retain.checked=target.retain;
    observeLabel.append(observe,document.createTextNode(' Observar'));retainLabel.append(retain,document.createTextNode(' Conservar metadatos'));
    const update=()=>void run(()=>configure({observation_targets:targets.map(t=>t.id===target.id?{...t,observe:observe.checked,retain:retain.checked}:t)}));observe.onchange=retain.onchange=update;
    const expiry=document.createElement('p');expiry.textContent='Vigencia: '+(target.expires_at===null?'Hasta revocación':new Date(target.expires_at*1000).toLocaleString())+' · Envío a proveedores deshabilitado';
    article.append(description,observeLabel,retainLabel,expiry,button('Quitar fuente',()=>configure({observation_targets:targets.filter(t=>t.id!==target.id)})));host.append(article);
   }
  }
  const runtime=(snapshot.source_runtime||[]).filter(r=>targets.some(t=>t.id===r.id&&t.task_id===task()));
  $('anticipation-source-runtime').style.whiteSpace='pre-line';$('anticipation-source-runtime').textContent=runtime.length?runtime.map(r=>r.id+' · '+(r.error?'Error: '+r.error:r.active?'Observación activa':'Sin observación activa')+' · Lecturas: '+r.samples+' · Cambios: '+r.events+(r.truncated?' · Exploración parcial':'')).join('\n'):'Sin lecturas de fuentes locales registradas en este chat.';
  const observations=$('anticipation-source-observations');observations.replaceChildren();
  for(const item of snapshot.source_observations||[]){
   if(item.task_id!==task())continue;
   const p=document.createElement('p');p.textContent=new Date(item.observed_at*1000).toLocaleString()+' · '+item.type+' · '+JSON.stringify(item.resource)+' · '+(item.retained?'Metadatos conservados':'Metadatos transitorios');p.style.overflowWrap='anywhere';observations.append(p);
  }
  const verifiers=$('anticipation-verifiers');verifiers.replaceChildren();
  for(const [format,verifier] of Object.entries(snapshot.capabilities?.verifiers||{})){
   const p=document.createElement('p');p.textContent=format.toUpperCase()+' · '+(verifier.available?'Disponible':'No disponible')+' · '+(verifier.verification_scope==='integrity_only'?'Solo integridad por hash':verifier.verification_scope)+(verifier.reason?' · '+verifier.reason:'');verifiers.append(p);
  }
 }
 function renderSettings(fill=false){
  if(!snapshot)return;
  const key=JSON.stringify([task(),snapshot.profile,snapshot.paused,snapshot.observation_paused,snapshot.profiles,snapshot.sources,snapshot.scopes,snapshot.grants,snapshot.suggestions,snapshot.metrics,snapshot.observation_targets,snapshot.source_runtime,snapshot.source_observations,snapshot.capabilities,mutation]);
  if(!fill&&settingsKey===key)return;settingsKey=key;
  $('anticipation-profile').value=snapshot.profile;
  $('anticipation-pause').textContent=snapshot.paused?'Reanudar iniciativas':'Pausar iniciativas';
  $('anticipation-observation').textContent=snapshot.observation_paused?'Reanudar observación':'Pausar observación';
  $('anticipation-status').textContent=names[snapshot.profile]+(snapshot.paused?' · Iniciativas pausadas':'')+(snapshot.observation_paused?' · Observación pausada':'')+' · '+(task()?'Chat: '+(Axx.chatWorkspace.active?.title||task()):'Selecciona un chat');
  for(const form of $('anticipation-profiles').querySelectorAll('form')){
   if(!fill&&(form.dataset.dirty==='true'||form.contains(document.activeElement)))continue;
   const options=snapshot.profiles?.[form.dataset.profile]||{};
   for(const [key,value] of Object.entries(options))if(form.elements.namedItem(key))form.elements.namedItem(key).value=value;
   for(const [key] of resourceFields)form.elements.namedItem('resource_'+key).value=options.resources?.[key]??'';
   form.elements.schedule_enabled.checked=!!options.schedule;
   form.elements.schedule_timezone.value=options.schedule?.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone;
   form.elements.schedule_start.value=options.schedule?.start||'09:00';form.elements.schedule_end.value=options.schedule?.end||'18:00';
   for(const day of form.querySelectorAll('[name=schedule_days]'))day.checked=(options.schedule?.days||[0,1,2,3,4,5,6]).includes(Number(day.value));syncSchedule(form);
   form.dataset.dirty='false';
  }
  $('anticipation-events').checked=snapshot.sources?.events===true;
  $('anticipation-sources').textContent='Fuentes habilitadas: '+(['events','folders','applications'].filter(key=>snapshot.sources?.[key]).map(key=>({events:'eventos autorizados',folders:'carpetas seleccionadas',applications:'aplicaciones seleccionadas'})[key]).join(', ')||'ninguna')+(snapshot.observation_paused?' · Observación pausada.':'.');
  renderSources();
  renderPermissions();
  const scopes=$('anticipation-scopes');scopes.replaceChildren();
  for(const [i,scope] of (snapshot.scopes||[]).entries()){
   const p=document.createElement('p');p.textContent=(scope.exclude?'Excluido':names[scope.profile]||scope.profile)+' · '+(scope.task_id||'Todos los chats')+' · '+(scope.root||'Todos los recursos')+(scope.project_id?' · Proyecto: '+scope.project_id:'')+(scope.application_id?' · Aplicación: '+scope.application_id:'')+(scope.device_id?' · Dispositivo: '+scope.device_id:'');
   p.append(button('Quitar ámbito',()=>configure({scopes:snapshot.scopes.filter((_,j)=>i!==j)})));scopes.append(p);
  }
  const grants=$('anticipation-grants');grants.replaceChildren();
  for(const grant of snapshot.grants||[]){
   if(grant.task_id!==task())continue;
   const reasons={revoked:'Revocado',expired:'Caducado',session_ended:'Sesión finalizada',consumed:'Una acción ya consumida',source_consent_changed:'El consentimiento de la fuente cambió'};
   const status=reasons[grant.inactive_reason]||(grant.revoked?'Revocado':grant.consumed_operation_id?'Consumido por '+grant.consumed_operation_id:Number.isFinite(grant.expires_at)&&grant.expires_at*1000<=Date.now()?'Caducado':grant.active===false?'No vigente':grant.expires_at===null?'Sin fecha de caducidad':new Date(grant.expires_at*1000).toLocaleString());
   const p=document.createElement('article');p.textContent=(grant.capability==='mission_steps'?'Pasos de misión':'Verificación de archivos')+' · '+grant.root+' · '+status+(grant.lifetime?' · '+(lifetimes[grant.lifetime]||grant.lifetime):'')+(grant.active===true?' · Vigencia base activa; cada plan se revalida':'')+(grant.capability==='verify_artifact'&&grant.observe_events===false?' · Solo aceptación explícita':'');
   if(grant.command_ids){const detail=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('pre');summary.textContent='Acciones, raíces y versión autorizadas';text.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';text.textContent=JSON.stringify({command_ids:grant.command_ids,read_roots:grant.read_roots,parameter_constraints:grant.parameter_constraints,learning_plan_id:grant.learning_plan_id,reviewed_plan_hash:grant.reviewed_plan_hash},null,2);detail.append(summary,text);p.append(detail);}
   if(grant.source_target_id)p.append(document.createTextNode(' · Fuente: '+grant.source_target_id+(grant.metadata_only===true?' · Solo metadatos':'')));
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
  if(!snapshot||origin!==task()||snapshot.paused||stopped||Axx.app.machine?.visible===false||document.hidden||busy()){hide();return;}
  const rows=(snapshot.suggestions||[]).filter(r=>r.task_id===task()&&r.visible===true&&!['DISMISSED','SUPPRESSED','CANCELLED','EXPIRED'].includes(r.state));
  const row=rows.find(r=>['AWAITING_APPROVAL','PREPARED','DETECTED','EXECUTING'].includes(r.state))||rows[0];
  if(!row){hide();return;}
  const prefs=row.policy||preferences();
  if(['OFF','SHADOW'].includes(prefs.mode)||prefs.interruptions==='silent'){hide();return;}
  const verified=row.state==='VERIFIED'&&row.result?.state==='succeeded'&&row.result?.postconditions_passed===true;
  const scope=row.verification_scope||row.result?.verification_scope||row.plan?.verification_scope;
  const phase=stale(row)?'Desactualizado':row.state==='VERIFIED'&&!verified?'Resultado recibido; falta evidencia':verified?(verificationLabels[scope]||'Verificado'):states[row.state]||row.state;
  const message=row.state==='VERIFIED'&&!verified?'No se recibió evidencia de verificación.':row.message;
  const text=(row.title||'Verificar archivo')+(message?'\n'+message:'')+(row.plan?.inputs?.path?'\n'+row.plan.inputs.path:'');
  const key=[row.suggestion_id,row.state,row.plan_hash,row.preparation_complete,text,phase,mutation,JSON.stringify([row.assessment,row.provenance,row.evidence,row.feedback,row.plan,row.accepted_hash,row.grant_id,row.expires_at,row.result?.output,row.verification_scope,row.semantic_verified,row.verifier_reason])].join('/');current=row;
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
  const selected=task();if(selected!==origin){origin=selected;snapshot=null;hide();for(const id of ['anticipation-grants','anticipation-history','anticipation-missions','anticipation-targets','anticipation-source-observations'])$(id).replaceChildren();for(const id of ['anticipation-grant-form','anticipation-mission-grant-form'])$(id).reset();delete $('anticipation-mission-grant-form').dataset.rootDirty;$('anticipation-mission-commands').replaceChildren();$('anticipation-mission-commands').dataset.key='';$('anticipation-grant-source').replaceChildren(new Option('Carpeta del espacio de ensayo',''));$('anticipation-grant-source').dataset.key='';$('anticipation-grant-root').readOnly=false;$('anticipation-grant-events').disabled=false;$('anticipation-mission-grant-plan').replaceChildren(new Option('Selecciona una misión',''));delete $('anticipation-mission-grant-plan').dataset.planHash;$('anticipation-mission-plan-hash').textContent='';missionPlans=[];missionProject='';$('anticipation-targets').dataset.renderKey='';$('anticipation-source-runtime').textContent='';$('anticipation-mission-status').textContent='';++missionRevision;missionsLoading=false;missionKey='';$('anticipation-status').textContent='Cargando el ámbito de este chat…';++revision;loading=false;}
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
  const width=Math.min(Math.round(280*(Axx.interfaceTheme?.widgetScale||1)),g.workWidth-24);
  card.style.setProperty('width',width+'px','important');card.style.removeProperty('height');card.style.removeProperty('max-height');
  const height=Math.min(Math.ceil(card.getBoundingClientRect().height),g.workHeight-24);
  const gap=size*.34+14,above=g.spaceAbove>=gap+height||g.spaceAbove>g.spaceBelow;
  const x=Math.max(-g.spaceLeft+12,Math.min(g.spaceRight-width-12,-width/2));
  const y=Math.max(-g.spaceAbove+12,Math.min(g.spaceBelow-height-12,above?-gap-height:gap));
  add('anticipation-card',Math.round(x),Math.round(y),width,height);
 }
 $('anticipation-profile').onchange=()=>void run(()=>configure({profile:$('anticipation-profile').value}));
 $('anticipation-pause').onclick=()=>void run(()=>configure({paused:!snapshot?.paused}));
 $('anticipation-observation').onclick=()=>void run(()=>configure({observation_paused:!snapshot?.observation_paused}));
 $('anticipation-events').onchange=()=>void run(()=>configure({sources:{events:$('anticipation-events').checked}}));
 for(const source of ['folders','applications'])$('anticipation-'+source).onchange=()=>void run(()=>configure({sources:{[source]:$('anticipation-'+source).checked}}));
 $('anticipation-target-source').onchange=()=>{const application=$('anticipation-target-source').value==='application';$('anticipation-target-folder').hidden=application;$('anticipation-target-app').hidden=!application;$('anticipation-target-root').disabled=application;$('anticipation-target-root').required=!application;$('anticipation-target-process').disabled=!application;$('anticipation-target-process').required=application;};
 $('anticipation-target-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  if(!task())throw Error('Selecciona el chat que autoriza esta fuente.');
  const source=$('anticipation-target-source').value,expiry=$('anticipation-target-expiry').value,targets=snapshot?.observation_targets||[];
  if(targets.length>=32)throw Error('Se permiten hasta 32 fuentes seleccionadas.');
  const target={id:Axx.newId(),source,task_id:task(),project_id:$('anticipation-target-project').value.trim(),application_id:$('anticipation-target-application').value.trim(),device_id:$('anticipation-target-device').value.trim(),observe:$('anticipation-target-observe').checked,retain:$('anticipation-target-retain').checked,send_to_provider:false,expires_at:expiry==='persistent'?null:Date.now()/1000+Number(expiry),...(source==='folder'?{root:$('anticipation-target-root').value.trim()}:{process_name:$('anticipation-target-process').value.trim()})};
  if(source==='application'&&!/^[A-Za-z0-9_. -]{1,76}\.exe$/i.test(target.process_name))throw Error('Indica el nombre exacto de un proceso .exe.');
  await configure({observation_targets:[...targets,target]});
 });};
 $('anticipation-mission').addEventListener('toggle',()=>{if($('anticipation-mission').open)void loadMissions();});
 $('anticipation-mission-permission').addEventListener('toggle',()=>{if($('anticipation-mission-permission').open)void loadMissions();});
 $('anticipation-mission-lifetime').onchange=syncMissionLifetime;
 $('anticipation-mission-grant-root').oninput=()=>{$('anticipation-mission-grant-form').dataset.rootDirty='true';};
 $('anticipation-mission-commands').onchange=renderPermissions;
 $('anticipation-mission-grant-plan').onchange=()=>{const select=$('anticipation-mission-grant-plan'),plan=missionProject===project()?missionPlans.find(p=>p.operation_id===select.value&&p.conversation_id===task()):null;if(plan){select.dataset.planHash=plan.plan_hash||plan.mission.plan_hash;$('anticipation-mission-plan-hash').textContent='Versión: '+select.dataset.planHash+'. Este hash identifica la versión; no contiene sus pasos. Revisa el plan antes de autorizar.';}else{delete select.dataset.planHash;$('anticipation-mission-plan-hash').textContent='';}};
 $('anticipation-mission-review').onclick=()=>void run(async()=>{const id=$('anticipation-mission-grant-plan').value;if(!id)throw Error('Selecciona una misión de este chat.');await reviewPlan({learning_plan_id:id,task_id:task()});});
 $('anticipation-grant-source').onchange=()=>{if(!$('anticipation-grant-source').value)$('anticipation-grant-root').value=snapshot?.capabilities?.mission_steps?.workspace_root||'';syncVerificationSource();};
 for(const form of $('anticipation-profiles').querySelectorAll('form')){
  form.oninput=()=>{form.dataset.dirty='true';};
  form.elements.schedule_enabled.onchange=()=>syncSchedule(form);
  form.onsubmit=e=>{e.preventDefault();void run(async()=>{const settings={mode:form.elements.mode.value,interruptions:form.elements.interruptions.value,resources:{},schedule:null};for(const key of ['cooldown_seconds','max_interruptions_hour','retention_days','cadence_seconds'])settings[key]=Number(form.elements.namedItem(key).value);for(const [key] of resourceFields)settings.resources[key]=Number(form.elements.namedItem('resource_'+key).value);if(form.elements.schedule_enabled.checked){const days=[...form.querySelectorAll('[name=schedule_days]:checked')].map(day=>Number(day.value));if(!days.length)throw Error('Selecciona al menos un día del horario.');settings.schedule={timezone:form.elements.schedule_timezone.value.trim(),days,start:form.elements.schedule_start.value,end:form.elements.schedule_end.value};}await configure({profiles:{[form.dataset.profile]:settings}});form.dataset.dirty='false';});};
 }
 $('anticipation-scope-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  const scoped=$('anticipation-scope-task').checked,root=$('anticipation-scope-root').value.trim(),context={};for(const [key,id] of [['project_id','project'],['application_id','application'],['device_id','device']]){const value=$('anticipation-scope-'+id).value.trim();if(value)context[key]=value;}
  if(scoped&&!task())throw Error('Selecciona un chat para guardar su ámbito.');
  if(!scoped&&!root&&!Object.keys(context).length)throw Error('Indica una carpeta, proyecto, aplicación o dispositivo, o limita el ámbito al chat actual.');
  const scope={...(scoped?{task_id:task()}:{}),...(root?{root}:{}),...context,profile:$('anticipation-scope-profile').value,exclude:$('anticipation-scope-exclude').checked};
  await configure({scopes:[...(snapshot?.scopes||[]),scope]});
 });};
 $('anticipation-grant-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  if(!task())throw Error('Selecciona el chat que recibirá este permiso.');
  const expiry=$('anticipation-grant-expiry').value;
  const target=$('anticipation-grant-source').value?externalTargets().find(t=>t.id===$('anticipation-grant-source').value):null;if($('anticipation-grant-source').value&&!target)throw Error('La fuente ya no está autorizada para este chat.');
  await api('grant',{task_id:task(),capability:'verify_artifact',root:target?target.root:$('anticipation-grant-root').value.trim(),expires_at:expiry==='persistent'?null:Date.now()/1000+Number(expiry),observe_events:$('anticipation-grant-events').checked,...(target?{source_target_id:target.id,metadata_only:true}:{})});
 });};
 $('anticipation-mission-grant-form').onsubmit=e=>{e.preventDefault();void run(async()=>{
  if(!task()||snapshot?.capabilities?.mission_steps?.available!==true)throw Error('No hay permisos de misión disponibles para este chat.');
  const command_ids=[...$('anticipation-mission-commands').querySelectorAll('input:checked:not(:disabled)')].map(input=>input.value);if(!command_ids.length)throw Error('Selecciona al menos una acción disponible.');
  const lifetime=$('anticipation-mission-lifetime').value,expiry=$('anticipation-mission-expiry').value,body={capability:'mission_steps',task_id:task(),root:$('anticipation-mission-grant-root').value.trim(),read_roots:$('anticipation-mission-read-roots').value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean),command_ids,expires_at:expiry==='persistent'?null:Date.now()/1000+Number(expiry),lifetime};
  if(body.read_roots.length>16)throw Error('Selecciona hasta dieciséis carpetas adicionales de lectura.');
  if(lifetime==='mission'){const select=$('anticipation-mission-grant-plan'),plan=missionProject===project()?missionPlans.find(p=>p.operation_id===select.value&&p.conversation_id===task()):null;if(!plan||!select.dataset.planHash||select.dataset.planHash!==(plan.plan_hash||plan.mission.plan_hash))throw Error('Selecciona y revisa la versión actual de la misión.');body.learning_plan_id=plan.operation_id;body.reviewed_plan_hash=select.dataset.planHash;}
  const json=$('anticipation-mission-constraints').value.trim();if(json){let constraints;try{constraints=JSON.parse(json);}catch{throw Error('Las restricciones deben ser un objeto JSON válido.');}if(!constraints||typeof constraints!=='object'||Array.isArray(constraints))throw Error('Indica restricciones por ID de comando.');for(const [id,params] of Object.entries(constraints)){const command=snapshot.capabilities.mission_steps.commands.find(c=>c.command_id===id);if(!command||!command_ids.includes(id)||!params||typeof params!=='object'||Array.isArray(params)||Object.keys(params).some(key=>!Object.hasOwn(command.parameters||{},key)))throw Error('Las restricciones deben usar comandos seleccionados y parámetros registrados.');}body.parameter_constraints=constraints;}
  await api('grant',body);
 });};
 $('anticipation-forget').onclick=()=>void run(async()=>{if(!task())throw Error('Selecciona un chat.');if(confirm('¿Borrar únicamente los eventos y propuestas aprendidos en este chat? Los permisos y archivos se conservan.'))await api('forget',{task_id:task()});});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.repeat)void stop().catch(notice);},true);
 void Axx.app?.bridge?.listen?.('axx-cancel',()=>{void stop().catch(notice);});
 const renderChat=Axx.companion.renderChat.bind(Axx.companion);
 Axx.companion.renderChat=function(...args){const value=renderChat(...args);if(origin!==task()){snapshot=null;hide();void refresh();}else renderCard();return value;};
 const timer=setInterval(()=>void refresh(),3000);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)hide();else void refresh();});
 window.addEventListener('pagehide',()=>{clearInterval(timer);++revision;hide();});
 Axx.anticipation={refresh,render:renderCard,layout,cancel:stop,allowSurprises,get state(){return snapshot;},get current(){return current;}};
 void refresh(true);
})(window.Axx);
