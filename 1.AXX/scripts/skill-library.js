/* Skills use the same reviewed execution surface as individual commands. */
(() => {
  'use strict';
  const Axx = window.Axx, commands = Axx?.commandLibrary;
  if (!commands) return;
  const $ = id => document.getElementById(id);
  const captureMemory=()=>commands.captureMemory?.()||Axx.chatWorkspace?.captureMemoryToken?.()||null;
  const api = (method, action, body,memory=null) => commands.request(method, '/axx-api/' + action, body,memory);
  const element = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  const button = (text, action) => { const node = element('button', text); node.type = 'button'; node.onclick = () => run(action); return node; };
  const run = async action => { let memory;try {memory=captureMemory();await action(memory); } catch (error) { if(!memory||Axx.chatWorkspace?.isMemoryTokenCurrent(memory,true))$('skills-status').textContent = error.message || String(error); } Axx.resident?.schedule(); };
  const states = {candidate:'Candidata', verified:'Comprobada', awaiting_approval:'Requiere aprobación', waiting_capacity:'Esperando un modelo apto', waiting_capability:'Construyendo una capacidad para esta tarea',
    succeeded:'Completada', goal_pending:'Objetivo pendiente de verificación', failed:'Falló', unknown:'Resultado incierto', interrupted:'Interrumpida', cancelled:'Cancelada', expired:'Requiere revisión', running:'Ejecutando', needs_input:'Faltan datos'};
  const section = element('section'); section.id = 'skill-library'; section.className = 'setup-card';
  section.innerHTML = `<strong>Mis habilidades</strong>
    <label class="setting">Proyecto actual<input id="skills-project" class="field" maxlength="128" placeholder="Personal, o nombre del proyecto"></label>
    <label class="setting">Buscar por nombre, intención o ejemplo<input id="skills-search" class="field" type="search"></label>
    <label><input id="skills-favorites" type="checkbox"> Solo favoritas</label>
    <button id="skills-refresh" type="button">Actualizar biblioteca</button>
    <div id="skills-list"></div><div id="skills-editor"></div>
    <details><summary>Contexto del proyecto</summary>
      <label class="setting">Carpeta actual<input id="skills-folder" class="field"></label>
      <label class="setting">Documento actual<input id="skills-file" class="field"></label>
      <label class="setting">Aplicación actual<input id="skills-app" class="field"></label>
      <button id="skills-save-context" type="button">Guardar contexto</button>
      <p id="skills-context-status" role="status"></p><details><summary>Procedencia y vigencia del contexto guardado</summary><div id="skills-context-evidence"></div>
      <label class="setting">Fuente o sesión registrada<select id="skills-context-origin"></select></label><button id="skills-invalidate-context" type="button">Marcar origen como desactualizado</button><button id="skills-forget-context" type="button">Olvidar este origen</button>
      <p>Olvidar elimina el contexto de ese origen y sus derivados. Los archivos, permisos y el historial de ejecución se conservan. Marcar como desactualizado conserva el dato y bloquea su reutilización automática.</p></details>
    </details>
    <details id="skills-lessons"><summary>Incidentes y correcciones de este chat</summary><p>Una hipótesis describe una posible causa. Una prueba posterior con recibo verificado no demuestra esa causa ni concede permisos.</p>
      <form id="skills-lessons-search"><label class="setting">Buscar referencias<input name="query" class="field" maxlength="1000" type="search"></label><label class="setting">ID de comando, opcional<input name="command_id" class="field" maxlength="128"></label><button type="submit">Consultar hasta tres referencias</button></form>
      <div id="skills-lessons-list"></div><p id="skills-lessons-status" role="status"></p>
      <details><summary>Registrar un incidente observado</summary><p>Selecciona un recibo ya cargado o indica el ID de una operación fallida. La biblioteca comprobará el recibo antes de guardar esta referencia.</p>
        <form id="skills-lesson-form"><label class="setting">Fallo ya cargado en este chat<select name="failed_receipt"><option value="">Escribir ID manualmente</option></select></label><label class="setting">ID de la operación fallida<input name="operation_id" class="field" maxlength="128" required></label><label class="setting">Hipótesis sin confirmar<textarea name="hypothesis" class="field" maxlength="1000" required></textarea></label><label class="setting">Corrección que propones, opcional<textarea name="user_correction" class="field" maxlength="1000"></textarea></label><label class="setting">Prueba ya cargada del mismo comando<select name="verified_receipt"><option value="">Sin selección</option></select></label><label class="setting">ID de la operación de prueba, opcional<input name="verification_operation_id" class="field" maxlength="128"></label><label><input name="allow_provider" type="checkbox"> Permitir usar esta ficha con el modelo configurado</label><p>Puede enviar esta ficha al proveedor. Guardarla u observar no autoriza ese envío.</p><button type="submit">Guardar referencia de incidente</button></form>
      </details></details>
    <details><summary>Combinar habilidades</summary><p>Añade las habilidades en el orden de la tarea. Las lecturas independientes pueden ejecutarse de dos en dos; los cambios en archivos y aplicaciones conservan un solo ejecutor.</p>
      <div id="skills-parts"></div><label class="setting">Objetivo<input id="skills-objective" class="field" maxlength="2000"></label>
      <details id="skills-goal-editor"><summary>Criterios verificables de una misión nueva</summary><p>Define hasta ocho criterios: text_exact, xlsx_from_csv o file_bundle. Usa rutas relativas al espacio de ensayo. El backend comprueba rutas, enlaces y límites. Revisar o preparar no ejecuta efectos.</p><label class="setting">Criterios JSON<textarea id="skills-goal-criteria" class="field" maxlength="16000" rows="8">[]</textarea></label><button id="skills-goal-review" type="button">Revisar criterios</button><pre id="skills-goal-preview"></pre><button id="skills-goal-prepare" type="button" disabled>Preparar misión con criterios</button></details>
      <button id="skills-compose" type="button">Preparar tarea combinada</button><button id="skills-clear-parts" type="button">Vaciar selección</button>
    </details>
    <details id="skills-demonstration"><summary>Aprende esto</summary>
      <p>Elige una ventana y realiza el procedimiento. Axx observa controles accesibles, sin registrar contraseñas ni pulsaciones. Puedes detenerlo en cualquier momento con Escape.</p>
      <button id="skills-inventory" type="button">Detectar aplicaciones y ventanas</button>
      <label class="setting">Ventana<select id="skills-window"></select></label>
      <label class="setting">Nombre y objetivo<input id="skills-demo-objective" class="field" maxlength="2000"></label>
      <button id="skills-demo-start" type="button">Comenzar demostración</button><button id="skills-demo-stop" type="button" disabled>Terminar</button><button id="skills-demo-cancel" type="button" disabled>Cancelar</button>
      <p id="skills-demo-status" role="status"></p><button id="skills-demo-prepare" type="button" disabled>Preparar habilidad candidata</button>
      <details><summary>Capacidades detectadas</summary><pre id="skills-inventory-result" style="white-space:pre-wrap;max-height:220px;overflow:auto"></pre></details>
    </details>
    <details open><summary>Tareas e historial</summary><button id="skills-tasks-refresh" type="button">Actualizar tareas</button><div id="skills-tasks"></div></details>
    <p id="skills-status" role="status"></p>`;
  $('command-library').before(section);
  let skills = [], parts = [], windows = [], demo = null, polling = null, refreshRevision=0, tasksRevision=0, contextBusy=false, lessonRevision=0, lessonScope='', lessonBusy=false, taskPlans=[],taskPlansProject='',currentContext=null,currentContextProject='',editorState=null,goalReview=null,goalScope='';
  const goalDrafts=new Map();
  const contextInputs={current_folder:'skills-folder',current_file:'skills-file',current_application:'skills-app'},contextDirty=new Set();
  const project = () => $('skills-project').value.trim();
  $('skills-project').value = Axx.companion.data.prefs.skillProject || '';
  const task=()=>Axx.chatWorkspace?.active?.id||null,scope=()=>JSON.stringify([project(),task(),Axx.chatWorkspace?.active?.memory_scope?.generation??0,Axx.chatWorkspace?.active?.memory_context_id||Axx.chatWorkspace?.active?.connect_id||'']);
  function clearGoalReview(){goalReview=null;$('skills-goal-preview').textContent='';$('skills-goal-prepare').disabled=true;}
  function syncGoalScope(){const selected=scope();if(goalScope===selected)return;if(goalScope)goalDrafts.set(goalScope,[$('skills-objective').value,$('skills-goal-criteria').value]);goalScope=selected;const draft=goalDrafts.get(selected)||['','[]'];$('skills-objective').value=draft[0];$('skills-goal-criteria').value=draft[1];clearGoalReview();}
  function syncLessonScope(){syncGoalScope();const selected=scope();if(selected===lessonScope)return;lessonScope=selected;++lessonRevision;if(editorState&&editorState.scope!==selected){editorState=null;$('skills-editor').replaceChildren();}$('skills-lessons-list').replaceChildren();$('skills-lesson-form').reset();for(const key of ['scope','humanCorrection','providerConsent'])delete $('skills-lesson-form').dataset[key];$('skills-lessons-search').reset();$('skills-lessons-status').textContent='';renderLessonReceipts();}
  const goalDraftKey=()=>JSON.stringify([scope(),$('skills-objective').value,$('skills-goal-criteria').value]);
  const stableGoal=value=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  function reviewedGoal(intent,raw,original={}){
    let criteria;try{criteria=JSON.parse(raw);}catch{throw Error('Los criterios deben ser una lista JSON válida.');}
    if(typeof intent!=='string'||!intent.trim()||intent.length>4000||!Array.isArray(criteria)||!criteria.length||criteria.length>8)throw Error('Indica un objetivo y entre uno y ocho criterios.');
    const ids=new Set(),relative=value=>typeof value==='string'&&value.length>0&&value.length<=180&&!/^[\\/]|:|\0/.test(value)&&value.replace(/\\/g,'/').split('/').every(part=>part&&part!=='.'&&part!=='..');
    for(const criterion of criteria){
      if(!criterion||typeof criterion!=='object'||Array.isArray(criterion)||Object.keys(criterion).sort().join(',')!=='id,kind,parameters'||typeof criterion.id!=='string'||! /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(criterion.id)||ids.has(criterion.id))throw Error('Cada criterio necesita id único, kind y parameters exactos.');ids.add(criterion.id);
      const p=criterion.parameters;if(!p||typeof p!=='object'||Array.isArray(p))throw Error('Los parámetros del criterio deben ser un objeto.');
      const keys=Object.keys(p).sort().join(',');
      if(criterion.kind==='text_exact'){if(keys!=='path,text'||!relative(p.path)||typeof p.text!=='string'||p.text.length>8000)throw Error('text_exact requiere path relativo y text literal.');}
      else if(criterion.kind==='xlsx_from_csv'){if(keys!=='delimiter,destination,numeric_column,source'||!relative(p.source)||!relative(p.destination)||!p.destination.toLowerCase().endsWith('.xlsx')||![',',';','\t'].includes(p.delimiter)||typeof p.numeric_column!=='string'||!p.numeric_column.length||p.numeric_column.length>200)throw Error('xlsx_from_csv requiere source, destination .xlsx, delimiter y numeric_column.');}
      else if(criterion.kind==='file_bundle'){if(Object.keys(p).some(key=>!['paths','destination','archive_name','max_output_bytes'].includes(key))||!relative(p.destination)||!Array.isArray(p.paths)||!p.paths.length||p.paths.length>100||p.paths.some(path=>!relative(path))||new Set(p.paths).size!==p.paths.length||Object.hasOwn(p,'archive_name')&&(typeof p.archive_name!=='string'||!p.archive_name.length||p.archive_name.length>100||/[\\/]/.test(p.archive_name)||!p.archive_name.toLowerCase().endsWith('.zip'))||Object.hasOwn(p,'max_output_bytes')&&(!Number.isSafeInteger(p.max_output_bytes)||p.max_output_bytes<1||p.max_output_bytes>1073741824))throw Error('file_bundle requiere paths únicos y destination relativos; archive_name .zip y max_output_bytes son opcionales.');}
      else throw Error('Tipo de criterio no disponible.');
    }
    const goal={...original,intent,criteria};if(new TextEncoder().encode(JSON.stringify(goal)).length>16000)throw Error('El contrato completo supera 16000 bytes.');return goal;
  }
  syncGoalScope();
  function lessonReceipts(){
    const receipts=new Map(),plans=taskPlansProject===project()?taskPlans:[],last=commands.lastOperation;
    const add=(record,conversation,command)=>{const result=record.result||record;if(conversation!==task()||!record.operation_id||!command||record.state!==result.state||!['failed','succeeded'].includes(result.state)||result.state==='failed'&&!result.error||result.state==='succeeded'&&result.postconditions_passed!==true)return;receipts.set(record.operation_id,{id:record.operation_id,command,state:result.state,error:result.error});};
    for(const plan of [...plans,...(last?.kind==='learned_plan'?[last]:[])])if(plan.conversation_id===task()&&(plan.project_id??project())===project())for(const [index,record] of (plan.step_records||[]).entries())add(record,plan.conversation_id,record.result?.command_id||record.command_id||plan.steps?.[index]?.command_id);
    if(last?.kind!=='learned_plan')add(last||{},last?.conversation_id,last?.command_id);
    return receipts;
  }
  function renderLessonReceipts(){
    const fields=$('skills-lesson-form').elements,receipts=lessonReceipts(),key=JSON.stringify([scope(),fields.operation_id.value,[...receipts.values()]]),failed=fields.failed_receipt,verified=fields.verified_receipt;if(failed.dataset.key===key)return;failed.dataset.key=key;
    const chosenFailure=fields.operation_id.value,chosenVerification=fields.verification_operation_id.value;failed.replaceChildren(new Option('Escribir ID manualmente',''));verified.replaceChildren(new Option('Sin selección',''));
    const command=receipts.get(chosenFailure)?.command;
    for(const receipt of receipts.values())if(receipt.state==='failed'){const option=new Option(receipt.command+' · '+(receipt.error?.message||receipt.error?.code||receipt.error||'Fallo registrado')+' · '+receipt.id,receipt.id);failed.add(option);}else if(command&&receipt.command===command)verified.add(new Option(receipt.command+' · Recibo con postcondiciones · '+receipt.id,receipt.id));
    if([...failed.options].some(option=>option.value===chosenFailure))failed.value=chosenFailure;if([...verified.options].some(option=>option.value===chosenVerification))verified.value=chosenVerification;
  }
  function adopt(plan) {
    commands.lastOperation = plan; commands.operation = ['awaiting_approval', 'running'].includes(plan.state) ? plan : null;
    commands.busy = false; commands.renderOperation(plan); commands.status(plan.message || states[plan.state] || plan.state);
    if (commands.operation) commands.open();
  }
  async function planRequest(action, body,memory=captureMemory()) {
    const humanGoal=action==='repair'&&body.goal_spec,sameGoal=humanGoal&&commands.operation?.operation_id===body.operation_id&&commands.operation.state!=='running',previous=commands.lastOperation;
    if (commands.busy || commands.operation&&!sameGoal) throw new Error('Revisa o cancela la acción pendiente antes de preparar otra.');
    commands.busy = true; const serial = ++commands.generation,selectedScope=scope();
    commands.operation=commands.lastOperation={kind:'learned_plan',operation_id:body.operation_id,state:'planning',steps:[],...(body.conversation_id?{conversation_id:body.conversation_id}:{})};
    commands.renderOperation(commands.operation);
    try { const plan = await api('POST', 'learning/' + action, body,memory); if (serial === commands.generation&&selectedScope===scope()) {if(body.conversation_id&&plan.conversation_id!==body.conversation_id||body.goal_spec&&plan.operation_id!==body.operation_id)throw Error('La preparación no corresponde a la misión y chat revisados.');if(body.goal_spec&&stableGoal(body.goal_spec)!==stableGoal(Object.fromEntries(Object.keys(body.goal_spec).map(key=>[key,plan.goal_spec?.[key]]))))throw Error('La preparación cambió los criterios revisados; consulta el resultado sin aprobarlo.');adopt(plan);} }
    catch(error){if(selectedScope!==scope()||serial!==commands.generation)return;if(action==='revalidate'||body.goal_spec){commands.lastOperation={...(humanGoal?previous:{}),kind:'learned_plan',operation_id:body.operation_id,conversation_id:body.conversation_id||previous?.conversation_id,state:'unknown',...(humanGoal?{}:{steps:[],...(action==='revalidate'?{revalidation:{id:body.id,version:body.version}}:{goal_spec:body.goal_spec})}),message:'No se confirmó la preparación. Consulta este mismo ID antes de volver a prepararlo.'};commands.operation=null;commands.renderOperation(commands.lastOperation);}throw error;}
    finally { if (serial === commands.generation) {commands.busy = false;if(selectedScope!==scope()&&commands.operation?.operation_id===body.operation_id&&commands.operation.state==='planning')commands.operation=null;} }
  }
  const goalCriteria=plan=>plan.goal_spec?.criteria||plan.mission?.criteria||[];
  const goalEvaluations=plan=>plan.goal_verification?.criteria||plan.goal_progress?.criteria||plan.mission?.goal_progress?.criteria||[];
  const criteriaSatisfied=plan=>goalCriteria(plan).every(criterion=>{const rows=goalEvaluations(plan).filter(row=>row.id===criterion.id&&row.kind===criterion.kind);return rows.length===1&&rows[0].status==='satisfied';});
  const goalProgress=plan=>plan.goal_progress||plan.mission?.goal_progress;
  function sameMission(plan,selected){if(selected!==scope()||plan.conversation_id!==task()||(plan.project_id??project())!==project())throw Error('La misión no corresponde al chat y proyecto actuales.');}
  async function prepareGoalProgress(plan){
    const memory=captureMemory();
    const selected=scope(),progress=goalProgress(plan);sameMission(plan,selected);
    if(commands.busy||commands.operation)throw Error('Revisa o cancela la acción pendiente antes de preparar el siguiente paso.');
    commands.busy=true;const serial=++commands.generation;
    try{
      const fresh=await api('GET','learning/plan?id='+encodeURIComponent(plan.operation_id),undefined,memory);if(serial!==commands.generation||selected!==scope())return;sameMission(fresh,selected);const candidate=goalProgress(fresh);
      if(fresh.operation_id!==plan.operation_id||fresh.plan_hash!==plan.plan_hash||candidate?.status!=='ready'||candidate.fingerprint!==progress.fingerprint||candidate.criterion_id!==progress.criterion_id||candidate.source_plan_hash&&candidate.source_plan_hash!==fresh.plan_hash)throw Error('La revisión o el candidato cambió. Actualiza y revisa el progreso.');
      const result=await api('POST','learning/goal-progress',{operation_id:plan.operation_id,plan_hash:plan.plan_hash,criterion_id:progress.criterion_id,candidate_hash:progress.fingerprint},memory);
      if(serial!==commands.generation||selected!==scope())return;sameMission(result,selected);
      if(result.operation_id!==plan.operation_id||result.state!=='awaiting_approval'||typeof result.plan_hash!=='string'||result.plan_hash===plan.plan_hash)throw Error('No se confirmó un sufijo nuevo para esta misma misión. Consulta su resultado.');
      adopt(result);await tasks();
    }catch(error){if(serial===commands.generation&&selected===scope())throw error;}
    finally{if(serial===commands.generation)commands.busy=false;}
  }
  function renderGoal(row,plan){
    if(!plan.goal_spec&&!goalProgress(plan))return;
    const details=element('details'),criteria=goalCriteria(plan),evaluations=goalEvaluations(plan),progress=goalProgress(plan),selected=scope();details.append(element('summary','Objetivo, criterios y progreso verificable'));
    details.append(element('p','Objetivo fijado · revisión '+(plan.goal_revision??plan.mission?.revision??'No informada')),element('p',plan.goal_spec?.intent||plan.mission?.objective||''));
    const statuses={satisfied:'Satisfecho',unsatisfied:'No satisfecho',indeterminate:'Indeterminado'};
    for(const criterion of criteria){const matches=evaluations.filter(value=>value.id===criterion.id&&value.kind===criterion.kind),evaluation=matches.length===1?matches[0]:null;details.append(element('p',criterion.id+' · '+criterion.kind+' · '+(matches.length>1?'Indeterminado · Evaluaciones duplicadas':statuses[evaluation?.status]||'Sin evaluación')+(evaluation?.reason_code?' · '+evaluation.reason_code:'')),element('pre',JSON.stringify(criterion.parameters,null,2)));}
    const coverage=plan.goal_verification?.coverage;details.append(element('p','Cobertura: '+(coverage==null?'No informada':typeof coverage==='string'?coverage:JSON.stringify(coverage))));
    if(progress){const labels={pending:'Déficit pendiente',waiting_dependency:'Esperando dependencia verificada',ready:'Hay un candidato para el siguiente déficit',prepared:'Sufijo preparado; requiere aprobación',satisfied:'Criterios satisfechos',needs_input:'Necesita información'};details.append(element('p',labels[progress.status]||'Progreso sin confirmar'));if(Number.isSafeInteger(progress.prefix_length))details.append(element('p','Prefijo conservado: '+progress.prefix_length+' pasos. Los recibos se conservan; no se repite el prefijo.'));}
    const budget=plan.mission?.budget;if(budget)details.append(element('p','Presupuesto total de la misión: '+(budget.model_calls_used??'No informado')+'/'+(budget.model_call_limit??'No informado')+' llamadas; restantes: '+(budget.model_calls_remaining??'No informado')));
    const own=plan.conversation_id===task()&&(plan.project_id??project())===project();
    if(progress?.status==='ready'&&own){details.append(element('p','Candidato para el criterio '+(progress.criterion_id||'No informado')),element('pre',JSON.stringify({step:progress.step,fingerprint:progress.fingerprint,source_plan_hash:progress.source_plan_hash},null,2)));const next=button('Preparar siguiente paso',()=>prepareGoalProgress(plan));next.disabled=commands.busy||!!commands.operation||! /^[a-f0-9]{64}$/i.test(plan.plan_hash||'')||! /^[a-f0-9]{64}$/i.test(progress.fingerprint||'')||!criteria.some(criterion=>criterion.id===progress.criterion_id)||!!progress.source_plan_hash&&progress.source_plan_hash!==plan.plan_hash;details.append(next,element('p','Sólo prepara un sufijo de esta misión. Revisa y aprueba su nueva versión para producir efectos.'));}
    if(own&&plan.goal_spec&&!['running','cancelled'].includes(plan.state)){
      const editor=element('details'),input=element('textarea'),correction=element('input'),preview=element('pre');editor.append(element('summary','Corregir criterios con una nueva revisión'));input.className=correction.className='field';input.value=JSON.stringify(criteria,null,2);input.maxLength=16000;input.rows=8;input.setAttribute('aria-label','Criterios corregidos de la misión');correction.setAttribute('aria-label','Motivo de la corrección de criterios');correction.placeholder='Qué debe corregirse';let review=null;
      const apply=button('Preparar corrección de criterios',async memory=>{if(!review||review.key!==JSON.stringify([input.value,correction.value])||selected!==scope())throw Error('Revisa otra vez la corrección actual.');sameMission(plan,selected);const fresh=await api('GET','learning/plan?id='+encodeURIComponent(plan.operation_id),undefined,memory);if(selected!==scope())return;sameMission(fresh,selected);if(fresh.operation_id!==plan.operation_id||fresh.goal_revision!==plan.goal_revision||fresh.plan_hash!==plan.plan_hash)throw Error('La revisión del objetivo cambió; consulta el plan actual antes de corregirlo.');if(!review||review.key!==JSON.stringify([input.value,correction.value]))throw Error('La corrección cambió durante la consulta; revísala otra vez.');await planRequest('repair',{operation_id:plan.operation_id,text:correction.value,goal_spec:review.goal,goal_revision:plan.goal_revision,...prefs()},memory);});apply.disabled=true;
      const reviewButton=element('button','Revisar corrección de criterios');reviewButton.type='button';reviewButton.onclick=event=>run(()=>{if(!event.isTrusted||!correction.value.trim())throw Error('Escribe y revisa explícitamente el motivo de la corrección.');sameMission(plan,selected);review={key:JSON.stringify([input.value,correction.value]),goal:reviewedGoal(plan.goal_spec.intent,input.value,plan.goal_spec)};preview.textContent=JSON.stringify(review.goal,null,2);apply.disabled=false;});
      input.oninput=correction.oninput=()=>{review=null;preview.textContent='';apply.disabled=true;};editor.append(element('p','La corrección humana cambia la revisión y exige una nueva preparación. El modelo no puede sustituir estos criterios.'),input,correction,reviewButton,preview,apply);details.append(editor);
    }
    row.append(details);
  }
  const prefs = () => {const p=Axx.companion.data.prefs;return {model:p.model || '',provider_name:p.provider==='chatgpt'?'@codex':p.provider==='bridge'?p.apiConnection || '':'',selection_mode:p.selection_mode || 'manual'};};
  async function refresh(memory=captureMemory()) {
    const selected=project(),selectedScope=scope(),token=++refreshRevision;
    const [result,context] = await Promise.all([api('GET','learning/actions?project_id='+encodeURIComponent(selected),undefined,memory),api('GET','learning/context?project_id='+encodeURIComponent(selected),undefined,memory)]);
    if(token!==refreshRevision||selectedScope!==scope())return;
    skills = result.actions || []; renderList();renderContext(context);syncLessonScope();
    await tasks();
    if($('skills-lessons').open)await loadLessons();
  }
  function renderContext(context){
    currentContext=context;currentContextProject=project();
    for(const [field,id] of Object.entries(contextInputs))if(!contextDirty.has(field))$(id).value=context[field]||'';
    const root=$('skills-context-evidence'),origin=$('skills-context-origin'),previous=origin.value;root.replaceChildren();origin.replaceChildren();
    const kinds={observed:'Observado',inferred:'Inferido',confirmed_user:'Confirmado por ti'},labels={...Object.fromEntries(Object.entries(contextInputs).map(([field,id])=>[field,$(id).parentElement.firstChild.textContent])),current_project:'Proyecto',aliases:'Alias',defaults:'Valores predeterminados',last_inputs:'Últimas entradas'};
    const origins=new Map();
    for(const [field,meta] of Object.entries(context.context_meta||{})){
      const row=element('p',(labels[field]||field)+' · '+(kinds[meta.kind]||'Procedencia no registrada')+' · '+(meta.status==='stale'?'Desactualizado':meta.status==='active'?'Activo':'Estado no registrado')+' · Revisión: '+meta.revision+' · Actualidad: '+({fresh:'reciente',stale:'desactualizada',unknown:'desconocida'}[meta.freshness]||'no registrada')+(meta.origin?' · Origen: '+meta.origin:'')+(meta.observed_at?' · Registrado: '+new Date(meta.observed_at*1000).toLocaleString():'')+(meta.expires_at?' · Caduca: '+new Date(meta.expires_at*1000).toLocaleString():''));row.style.overflowWrap='anywhere';root.append(row);
      for(const [key,label] of [['source_id','Fuente'],['session_id','Sesión']])if(meta[key]){const value=JSON.stringify({[key]:meta[key]});origins.set(value,label+': '+meta[key]);}
    }
    for(const [value,text] of origins)origin.add(new Option(text,value));if(origins.has(previous))origin.value=previous;
    if(!root.children.length)root.textContent='No hay procedencia de campos registrada.';
    $('skills-invalidate-context').disabled=$('skills-forget-context').disabled=contextBusy||!origins.size;
    $('skills-context-status').textContent='Contexto guardado · Revisión: '+(context.context_revision??'No registrada')+(contextDirty.size?' · Hay campos editados sin guardar.':'');
    editorState?.refresh();
  }
  async function saveContext(memory=captureMemory()){
    const selected=project(),changes={};for(const field of contextDirty)changes[field]=$(contextInputs[field]).value;
    if(!Object.keys(changes).length){$('skills-status').textContent='No hay campos editados para guardar.';return;}
    const source_id=Axx.newId(),session_id=Axx.chatWorkspace?.active?.id,context_meta={};
    for(const field of Object.keys(changes))context_meta[field]={kind:'confirmed_user',origin:'user_settings',source_id,...(session_id?{session_id,task_id:session_id}:{}),observed_at:Date.now()/1000};
    const context=await api('POST','learning/context',{project_id:selected,changes:{...changes,context_meta}},memory);
    if(selected!==project())return;
    for(const [field,value] of Object.entries(changes))if($(contextInputs[field]).value===value)contextDirty.delete(field);
    renderContext(context);$('skills-status').textContent='Contexto guardado. Solo los campos editados se registraron como confirmados por ti.';
  }
  async function invalidateContext(forget,memory=captureMemory()){
    const selected=project(),value=$('skills-context-origin').value;if(!value)throw Error('Selecciona una fuente o sesión registrada.');
    const context=await api('POST','learning/forget-context',{project_id:selected,...JSON.parse(value),forget},memory);if(selected!==project())return;
    renderContext(context);$('skills-status').textContent=(forget?'Contexto olvidado':'Contexto marcado como desactualizado')+' · '+(context.invalidated||[]).length+' referencias invalidadas. Los permisos y el historial de ejecución se conservan.';
  }
  const contextAction=action=>run(async memory=>{if(contextBusy)return;contextBusy=true;$('skills-save-context').disabled=$('skills-invalidate-context').disabled=$('skills-forget-context').disabled=true;try{await action(memory);}finally{contextBusy=false;$('skills-save-context').disabled=false;$('skills-invalidate-context').disabled=$('skills-forget-context').disabled=!$('skills-context-origin').options.length;}});
  async function loadLessons(memory=captureMemory()){
    syncLessonScope();renderLessonReceipts();const selected=scope(),currentTask=task(),currentProject=project(),token=++lessonRevision;if(!currentTask){$('skills-lessons-status').textContent='Selecciona un chat para consultar sus referencias.';return;}
    const query=$('skills-lessons-search').elements,params=new URLSearchParams({project_id:currentProject,task_id:currentTask,query:query.query.value.trim(),command_id:query.command_id.value.trim(),limit:'3'});let result;try{result=await api('GET','learning/lessons?'+params,undefined,memory);}catch(error){if(token!==lessonRevision||selected!==scope())return;throw error;}
    if(token!==lessonRevision||selected!==scope())return;if(!Array.isArray(result.lessons))throw Error('La biblioteca no devolvió referencias válidas.');
    const root=$('skills-lessons-list');root.replaceChildren();
    for(const lesson of result.lessons){
      if(lesson.task_id!==currentTask||lesson.project_id!==''&&lesson.project_id!==currentProject)continue;
      const row=element('article');row.className='setup-card';row.append(element('strong',lesson.command_id+' · '+(lesson.status==='stale'?'Referencia desactualizada':'Referencia de incidente')),element('p','Síntoma observado: '+lesson.symptom+' · '+lesson.error_code));
      const details=element('details'),list=element('dl');details.append(element('summary','Hipótesis, corrección y evidencia'));
      const add=(label,value)=>{if(value===undefined||value===null)return;list.append(element('dt',label),element('dd',String(value)));};
      add('Hipótesis sin confirmar',lesson.hypothesis);if(lesson.user_correction)add(lesson.correction_provenance==='confirmed_user'?'Corrección que escribiste':'Corrección registrada',lesson.user_correction);
      if(lesson.verification?.status==='verified_test')add('Prueba con recibo verificado',lesson.verification.operation_id+'. Esta prueba no confirma la causa del fallo.');
      else add('Prueba posterior','No hay una prueba verificada adjunta.');
      add('Operación de origen',lesson.source_operation_id);add('SHA-256 del recibo de origen',lesson.source_receipt_sha256);
      if(lesson.verification?.receipt_sha256)add('SHA-256 del recibo de prueba',lesson.verification.receipt_sha256);
      if(lesson.environment_scope==='registered_command_at_recording_not_historical_app_version')add('Entorno','Corresponde al comando registrado al guardar la referencia; no certifica la versión histórica de la aplicación.');
      if(lesson.environment_matches===false||lesson.context_matches===false)add('Desactualizado','El entorno o el contexto ya no coincide con el de esta referencia.');
      if(lesson.permissions_granted===false)add('Permisos','Esta referencia no concede permisos.');if(lesson.preference_inferred===false)add('Preferencias','El incidente no acredita una preferencia del usuario.');
      add('Uso con el modelo',lesson.allow_provider===true?'Autorizado por ti; esta ficha puede enviarse al proveedor configurado.':'Uso local; no hay permiso de envío al modelo.');
      list.style.overflowWrap='anywhere';details.append(list);row.append(details,button('Olvidar esta referencia',()=>lessonAction(async memory=>{const result=await api('POST','learning/forget-lesson',{id:lesson.id},memory);if(selected!==scope())return;await loadLessons();$('skills-lessons-status').textContent=(result.forgotten?'Referencia olvidada.':'La referencia ya no estaba guardada.')+(result.command_journal_preserved===true?' El historial de ejecución se conserva.':'');})));root.append(row);
    }
    $('skills-lessons-status').textContent=root.children.length?root.children.length+' referencias de este chat.':'No hay referencias que coincidan en este chat.';
  }
  const lessonAction=action=>run(async memory=>{if(lessonBusy)return;lessonBusy=true;$('skills-lesson-form').querySelector('button').disabled=true;try{await action(memory);}finally{lessonBusy=false;$('skills-lesson-form').querySelector('button').disabled=false;}});
  async function recordLesson(memory=captureMemory()){
    const form=$('skills-lesson-form'),selected=scope(),currentTask=task();if(!currentTask)throw Error('Selecciona el chat de este incidente.');if(form.dataset.scope!==selected)throw Error('El chat o proyecto cambió. Revisa y vuelve a escribir la referencia antes de guardarla.');
    const fields=form.elements,body={operation_id:fields.operation_id.value.trim(),hypothesis:fields.hypothesis.value.trim(),project_id:project(),task_id:currentTask,allow_provider:fields.allow_provider.checked&&form.dataset.providerConsent==='true'};if(fields.user_correction.value.trim()){if(form.dataset.humanCorrection!==fields.user_correction.value)throw Error('La corrección debe escribirla el usuario; el texto automático no se registrará como confirmado.');body.user_correction=fields.user_correction.value.trim();}if(fields.verification_operation_id.value.trim())body.verification_operation_id=fields.verification_operation_id.value.trim();
    try{await api('POST','learning/lesson',body,memory);}catch(error){if(selected!==scope())return;throw error;}if(selected!==scope())return;await loadLessons();$('skills-lessons-status').textContent='Referencia guardada. La hipótesis sigue sin confirmar.';
  }
  function renderList() {
    const query = $('skills-search').value.toLocaleLowerCase(), list = $('skills-list'); list.replaceChildren();
    for (const skill of skills.filter(s => (!$('skills-favorites').checked || s.favorite) && [s.title, s.trigger, ...(s.examples || [])].join(' ').toLocaleLowerCase().includes(query))) {
      const card = element('article'); card.className = 'setup-card';
      card.append(element('strong', skill.title), element('p', `v${skill.version} · ${states[skill.status] || skill.status} · ${skill.goal_confirmed ? 'Objetivo confirmado' : 'Objetivo sin confirmar'}`));
      card.append(element('p', (skill.examples || []).slice(0, 3).join(' · ')));
      card.append(button(skill.favorite ? '★ Favorita' : '☆ Favorita', async memory => { await api('POST','learning/configure',{id:skill.id,changes:{favorite:!skill.favorite}},memory); await refresh(); }));
      card.append(button('Entradas y ejecución', () => edit(skill)));
      list.append(card);
    }
    if (!list.children.length) list.textContent = 'No hay habilidades que coincidan. Usa /aprende en el chat o enseña una demostración.';
    editorState?.refresh();
  }
  function bindingSkill(skill){
    if(!skill||typeof skill!=='object')return false;
    const properties=skill.schema?.properties,required=skill.schema?.required,steps=skill.templates,roles=['other_path','path'];
    return typeof skill.id==='string'&&skill.id.length>0&&skill.executable&&skill.environment_matches!==false&&!skill.quarantined&&skill.context_matches!==false&&skill.inference==null&&properties&&Object.keys(properties).sort().join(',')===roles.join(',')&&roles.every(role=>properties[role]?.type==='string'&&!Object.hasOwn(properties[role],'default'))&&Array.isArray(required)&&required.length===2&&[...required].sort().join(',')===roles.join(',')&&Array.isArray(steps)&&steps.length===1&&steps[0].command_id==='axx.file.compare'&&steps[0].inputs&&Object.keys(steps[0].inputs).sort().join(',')===roles.join(',')&&roles.every(role=>steps[0].inputs[role]==='{{'+role+'}}');
  }
  function resourceBindingEditor(skill,fields,selectedScope,identity,changed){
    const root=element('details'),mode=element('input'),modeLabel=element('label'),choices=new Map();root.id='skills-resource-bindings';mode.id='skills-resource-mode';mode.type='checkbox';modeLabel.append(mode,document.createTextNode(' Usar documentos actuales de dos proyectos para esta preparación'));root.append(element('summary','Comparar documentos actuales de dos proyectos'),modeLabel,element('p','Consulta cada proyecto y elige sus dos referencias explícitamente. La preparación comprobará los archivos y pedirá la aprobación normal; no ejecuta la comparación.'));
    let enabled=false;
    const valid=memory=>{const current=skills.find(row=>row.id===skill.id);return selectedScope===scope()&&editorState?.bindingIdentity===identity&&current?.version===skill.version&&bindingSkill(current)&&current.environment_matches!==false&&!current.quarantined&&current.context_matches!==false&&!!task()&&(!memory||Axx.chatWorkspace?.isMemoryTokenCurrent(memory,true)===true);};
    function fromContext(context,id){
      const meta=context?.context_meta?.current_file;
      if(context?.project_id!==id||typeof context.current_file!=='string'||!context.current_file||meta?.kind!=='confirmed_user'||meta.status!=='active'||!Number.isSafeInteger(meta.revision)||meta.revision<1||meta.expires_at!=null&&(!Number.isFinite(meta.expires_at)||meta.expires_at*1000<=Date.now()))throw Error('Este proyecto no tiene un documento actual confirmado y vigente.');
      const references=[...(meta.memory_scope?[meta.memory_scope]:[]),...(meta.memory_dependencies||[])];if(references.some(ref=>Axx.chatWorkspace?.allowsMemoryReference&&!Axx.chatWorkspace.allowsMemoryReference(ref)))throw Error('La memoria de una fuente cambió; consulta de nuevo su origen.');
      return {project_id:id,field:'current_file',revision:meta.revision,path:context.current_file,task_id:meta.task_id,expires_at:meta.expires_at??null,references:structuredClone(references),key:JSON.stringify([id,context.current_file,meta]),contextSnapshot:currentContext};
    }
    function clear(choice,message='Consulta y elige este documento otra vez.') {++choice.revision;choice.review=null;choice.confirmed=false;choice.choose.checked=false;choice.choose.disabled=true;choice.source.textContent=message;}
    function reviewed(choice){const row=choice.review;return !!row&&choice.project.value.trim()===row.project_id&&!(row.expires_at!=null&&row.expires_at*1000<=Date.now())&&!row.references.some(ref=>Axx.chatWorkspace?.allowsMemoryReference&&!Axx.chatWorkspace.allowsMemoryReference(ref));}
    function refresh(){
      for(const choice of choices.values()){
        if(choice.review&&!reviewed(choice))clear(choice);
        if(choice.review&&choice.review.project_id===currentContextProject&&currentContext&&choice.review.contextSnapshot!==currentContext){try{if(fromContext(currentContext,choice.review.project_id).key!==choice.review.key)clear(choice,'El documento guardado cambió; consulta y elige la revisión actual.');else choice.review.contextSnapshot=currentContext;}catch{clear(choice);}}
        choice.project.disabled=choice.load.disabled=!enabled;choice.choose.disabled=!enabled||!reviewed(choice);
      }
      changed(enabled,valid()&&[...choices.values()].every(choice=>reviewed(choice)&&choice.confirmed&&choice.choose.checked));
    }
    for(const [role,labelText] of [['path','Primer archivo (path)'],['other_path','Segundo archivo (other_path)']]){
      const label=element('label',labelText+' · ID del proyecto (vacío: Personal)'),projectInput=element('input'),source=element('p'),choose=element('input'),chooseLabel=element('label');label.className='setting';projectInput.className='field';projectInput.maxLength=128;projectInput.id='skills-resource-'+role+'-project';projectInput.setAttribute('aria-label',labelText+' · Proyecto');label.append(projectInput);source.id='skills-resource-'+role+'-source';source.textContent='Sin referencia seleccionada.';choose.type='checkbox';choose.disabled=true;choose.id='skills-resource-'+role+'-choose';chooseLabel.append(choose,document.createTextNode(' Elegir este documento para '+role));
      const choice={project:projectInput,source,choose,revision:0,review:null,confirmed:false};
      const load=button('Consultar documento actual de '+role,async memory=>{
        if(!enabled||!valid(memory))throw Error('La selección o el chat cambió; vuelve a abrir la habilidad.');
        const id=projectInput.value.trim();if(id.length>128)throw Error('El ID del proyecto es demasiado largo.');clear(choice,'Consultando documento registrado…');const revision=choice.revision;
        let context;try{context=await api('GET','learning/context?project_id='+encodeURIComponent(id),undefined,memory);}catch(error){if(!valid(memory)||!enabled||revision!==choice.revision||projectInput.value.trim()!==id)return;clear(choice,'No se confirmó la consulta del documento.');throw error;}
        if(!valid(memory)||!enabled||revision!==choice.revision||projectInput.value.trim()!==id)return;
        try{choice.review=fromContext(context,id);}catch(error){clear(choice,error.message);refresh();throw error;}
        source.textContent='Proyecto: '+(id||'Personal')+' · Campo: current_file\nRuta registrada: '+choice.review.path+'\nRevisión: '+choice.review.revision+' · Caducidad: '+(choice.review.expires_at==null?'Sin caducidad registrada':new Date(choice.review.expires_at*1000).toLocaleString())+'\nConfirmado por ti; el archivo se comprobará al preparar.';refresh();
      });load.id='skills-resource-'+role+'-load';choice.load=load;choices.set(role,choice);
      projectInput.oninput=()=>{clear(choice);refresh();};choose.onchange=event=>{choice.confirmed=event.isTrusted&&enabled&&choose.checked&&reviewed(choice);if(!choice.confirmed)choose.checked=false;refresh();};root.append(label,load,source,chooseLabel);
    }
    mode.onchange=event=>{enabled=event.isTrusted&&mode.checked;if(!enabled)mode.checked=false;for(const choice of choices.values())clear(choice,'Consulta y elige este documento.');for(const [name,{field,spec}] of fields){field.disabled=enabled;field.required=!enabled&&skill.schema.required?.includes(name)&&spec.type!=='boolean';}refresh();};
    return {root,get enabled(){return enabled;},refresh,invalidateMemory(id){for(const choice of choices.values())if(choice.review&&(choice.review.task_id===id||choice.review.references.some(ref=>ref.task_id===id)))clear(choice,'El origen se olvidó; revisa una referencia vigente.');refresh();},async prepare(memory){
      refresh();if(!enabled||!valid(memory)||![...choices.values()].every(choice=>reviewed(choice)&&choice.confirmed&&choice.choose.checked))throw Error('Consulta y elige explícitamente los dos documentos actuales.');
      const selected=[...choices].map(([role,choice])=>({role,choice,review:choice.review,revision:choice.revision}));if(selected[0].review.project_id===selected[1].review.project_id)throw Error('Elige documentos de dos proyectos distintos.');
      const current=()=>valid(memory)&&enabled&&selected.every(row=>row.choice.review===row.review&&row.choice.revision===row.revision&&row.choice.confirmed&&row.choice.choose.checked&&row.choice.project.value.trim()===row.review.project_id&&reviewed(row.choice));
      for(const entry of selected){let context;try{context=await api('GET','learning/context?project_id='+encodeURIComponent(entry.review.project_id),undefined,memory);}catch(error){if(!current())return;throw error;}if(!current())return;let fresh;try{fresh=fromContext(context,entry.review.project_id);}catch(error){clear(entry.choice);refresh();throw error;}if(fresh.key!==entry.review.key){clear(entry.choice,'La revisión cambió; consulta y elige el documento actual.');refresh();throw Error('Una referencia cambió antes de preparar.');}}
      if(!valid(memory))return;if(selected.some(({choice})=>!reviewed(choice))){refresh();throw Error('Una referencia caducó antes de preparar.');}const resource_bindings=Object.fromEntries(selected.map(({role,review})=>[role,{project_id:review.project_id,field:'current_file',revision:review.revision}]));await commands.planAction(skill.id,{inputs:{},resource_bindings,memoryToken:memory,resourceReviewCurrent:current});
    }};
  }
  function edit(skill) {
    const selectedScope=scope(),bindingIdentity={};
    const root = $('skills-editor'); root.replaceChildren(element('strong', skill.title));
    const form = element('form'), inputs = new Map();
    for (const [name, spec] of Object.entries(skill.schema?.properties || {})) {
      if (name === skill.inference?.output_parameter) { form.append(element('p',(spec.description || name) + ': se genera al preparar esta ejecución.')); continue; }
      const label = element('label', spec.description || name); label.className = 'setting';
      const field = spec.enum ? element('select') : element('input'); field.className = 'field';
      if (spec.enum) for (const value of spec.enum) field.add(new Option(String(value), JSON.stringify(value)));
      else if (spec.type === 'boolean') field.type = 'checkbox';
      else if (['integer','number'].includes(spec.type)) { field.type = 'number'; field.step = spec.type === 'integer' ? '1' : 'any'; }
      else field.type = 'text';
      if (spec.default !== undefined) { if (spec.type === 'boolean') field.checked = spec.default; else field.value = spec.enum ? JSON.stringify(spec.default) : spec.default; }
      field.required = skill.schema.required?.includes(name) && spec.type !== 'boolean';
      label.append(field); form.append(label); inputs.set(name, {field,spec});
    }
    const values = () => { if (!form.reportValidity()) throw new Error('Completa las entradas requeridas.'); return Object.fromEntries([...inputs].filter(([, {field,spec}]) => spec.type === 'boolean' || field.value !== '').map(([name,{field,spec}]) => [name, spec.enum ? JSON.parse(field.value) : spec.type === 'boolean' ? field.checked : ['number','integer'].includes(spec.type) ? Number(field.value) : field.value])); };
    const submit = element('button', skill.executable ? 'Revisar y ejecutar' : 'Adaptador pendiente'); submit.type = 'submit'; submit.disabled = !skill.executable||skill.environment_matches===false||skill.quarantined||skill.context_matches===false;
    let bindings=null;const unavailable=submit.disabled,submitText=submit.textContent,compose=button('Añadir a tarea combinada',()=>{if(bindings?.enabled)throw Error('Estas referencias requieren una preparación individual nueva.');parts.push({id:skill.id,version:skill.version,inputs:values(),part_id:'part'+parts.length,depends_on:parts.length?[parts.at(-1).part_id]:[]});renderParts();});
    if(bindingSkill(skill)){bindings=resourceBindingEditor(skill,inputs,selectedScope,bindingIdentity,(enabled,ready)=>{submit.disabled=unavailable||enabled&&!ready;submit.textContent=enabled?'Preparar comparación para revisar':submitText;compose.disabled=enabled;});form.append(bindings.root);}
    form.onsubmit=event=>{event.preventDefault();return run(memory=>bindings?.enabled?bindings.prepare(memory):commands.planAction(skill.id,{inputs:values(),memoryToken:memory}));};
    form.append(submit,compose);root.append(form);
    const details = element('details'); details.append(element('summary','Modificar habilidad'));
    const title = element('input'); title.className='field'; title.value=skill.title; title.setAttribute('aria-label','Nombre de la habilidad');
    const examples = element('textarea'); examples.className='field'; examples.value=(skill.examples||[]).join('\n'); examples.setAttribute('aria-label','Ejemplos equivalentes, uno por línea');
    const alias = element('input'); alias.className='field'; alias.placeholder='Expresión habitual para esta habilidad'; alias.setAttribute('aria-label','Alias');
    details.append(element('p','Nombre y formas equivalentes de pedirla:'), title, examples, alias);
    const advanced = element('details'); advanced.append(element('summary','Pasos y parámetros avanzados'));
    advanced.append(element('p','Usa {{nombre}} en los valores que deben cambiar. Declara su tipo y valores predeterminados en el esquema. Los cambios crean una versión candidata que debe volver a comprobarse.'));
    const schema = element('textarea'), templates=element('textarea'), inference=element('textarea');
    schema.className=templates.className='field'; schema.rows=templates.rows=8; schema.value=JSON.stringify(skill.schema,null,2); templates.value=JSON.stringify(skill.templates,null,2);
    schema.setAttribute('aria-label','Esquema de entradas'); templates.setAttribute('aria-label','Pasos de la habilidad');
    inference.className='field';inference.rows=4;inference.value=JSON.stringify(skill.inference||null,null,2);inference.setAttribute('aria-label','Etapa de contenido nuevo');
    advanced.append(schema,templates,element('p','Contenido nuevo opcional: tarea (writing, translation, code o parameters), prompt y output_parameter. Usa null para una habilidad determinista.'),inference); details.append(advanced);
    const references=skill.context_dependencies||[],refsDetail=element('details'),refsPreview=element('pre'),refsStatus=element('p'),refsLabel=element('label'),refsCheckbox=element('input');refsCheckbox.type='checkbox';refsCheckbox.id='skills-refresh-context-refs';refsLabel.append(refsCheckbox,document.createTextNode(' Actualizar referencias con el contexto actual'));refsDetail.append(element('summary','Referencias de contexto de esta versión'),refsLabel,refsStatus,refsPreview);refsPreview.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;max-height:180px;overflow:auto';details.append(refsDetail);
    function refreshedReferences(){
      if(selectedScope!==scope()||currentContextProject!==project()||!currentContext)return {error:'Selecciona esta habilidad y consulta el contexto del proyecto actual.'};
      const next=[],preview=[];
      for(const ref of references){const meta=currentContext.context_meta?.[ref.field];if(ref.project_id!==project()||!meta||meta.status!=='active'||meta.task_id!==task()||meta.expires_at!=null&&meta.expires_at*1000<=Date.now()||!Object.hasOwn(currentContext,ref.field))return {error:'Actualiza explícitamente '+ref.field+' en el contexto de este chat y proyecto. No se eliminará ni trasladará su referencia.'};next.push({...ref,revision:meta.revision});preview.push({field:ref.field,project_id:ref.project_id,revision_anterior:ref.revision,revision_actual:meta.revision,valor_actual:currentContext[ref.field]});}
      return {next,preview,key:JSON.stringify([skill.id,skill.version,selectedScope,currentContext.context_revision,next])};
    }
    refsCheckbox.onchange=event=>{if(event.isTrusted&&refsCheckbox.checked){const current=refreshedReferences();if(!current.error)refsCheckbox.dataset.approved=current.key;}else delete refsCheckbox.dataset.approved;};
    refsDetail.addEventListener('toggle',()=>{if(refsDetail.open)void run(async()=>{const selected=scope(),context=await api('GET','learning/context?project_id='+encodeURIComponent(project()));if(selected===scope()&&editorState?.id===skill.id&&editorState.version===skill.version)renderContext(context);});});
    const trialDetail=element('details'),trialForm=element('form'),trialFields=new Map(),trialStatus=element('p'),trialButton=element('button','Preparar ensayo');trialDetail.id='skills-revalidation';trialButton.id='skills-prepare-revalidation';trialButton.type='submit';trialDetail.append(element('summary','Ensayo explícito de revalidación'),element('p','Escribe parámetros actuales. No se usan valores predeterminados ni se consulta al proveedor. Solo admite archivos del espacio de ensayo y copias nuevas; revisa el plan antes de aprobarlo.'),trialStatus);
    for(const [name,spec] of Object.entries(skill.schema?.properties||{})){const label=element('label',spec.description||name),field=element(spec.enum||spec.type==='boolean'?'select':'input');label.className='setting';field.className='field';field.name=name;if(spec.enum||spec.type==='boolean'){field.add(new Option('Selecciona un valor',''));for(const value of spec.enum||[true,false])field.add(new Option(String(value),JSON.stringify(value)));}else{field.type=['integer','number'].includes(spec.type)?'number':'text';if(spec.type==='number')field.step='any';}field.required=skill.schema.required?.includes(name)||JSON.stringify(skill.templates).includes('{{'+name+'}}');label.append(field);trialForm.append(label);trialFields.set(name,{field,spec});}
    trialForm.append(trialButton);trialDetail.append(trialForm);root.append(trialDetail);
    const direct=new Set(['axx.file.sha256','axx.file.compare','axx.file.find','axx.artifact.pdf','axx.artifact.media','axx.artifact.ocr','axx.artifact.write','axx.file.bundle','axx.office.excel.csv','axx.office.word.pdf','axx.office.powerpoint.pdf']);
    editorState={scope:selectedScope,id:skill.id,version:skill.version,bindingIdentity,bindings,refresh(){bindings?.refresh();const consistent=selectedScope===scope()&&skills.find(row=>row.id===skill.id)?.version===skill.version,current=refreshedReferences();refsCheckbox.disabled=!consistent||!references.length||!!current.error;if(refsCheckbox.dataset.key!==current.key){refsCheckbox.checked=false;delete refsCheckbox.dataset.approved;refsCheckbox.dataset.key=current.key||'';}refsStatus.textContent=!consistent?'La selección cambió; vuelve a abrir esta versión.':current.error||(!references.length?'Esta versión no conserva referencias de contexto.':'Guardar crea una versión nueva y conserva los mismos campos y proyectos.');refsPreview.textContent=current.preview?JSON.stringify(current.preview,null,2):'';const contextValid=currentContextProject===project()&&references.every(ref=>{const meta=currentContext?.context_meta?.[ref.field];return ref.project_id===project()&&meta?.revision===ref.revision&&meta.status==='active'&&[null,undefined,'',task()].includes(meta.task_id)&&!(meta.expires_at!=null&&meta.expires_at*1000<=Date.now());});const supported=skill.executable&&skill.inference==null&&!skill.id.startsWith('workshop.cap.')&&!skill.provenance?.workshop_id&&skill.templates.every(step=>direct.has(step.command_id));trialButton.disabled=!consistent||!task()||!supported||!contextValid;const workspace=Axx.anticipation?.state?.capabilities?.mission_steps?.workspace_root;trialStatus.textContent=!consistent?'La versión o el chat cambió; vuelve a seleccionar la habilidad.':!supported?'Este ensayo no admite inferencia, controles del escritorio, shell, MCP ni promociones del taller.':!contextValid?'Revisa primero las referencias actuales y guarda una versión nueva.':workspace?'Ámbito de ensayo: '+workspace:'El plan mostrará la raíz real del espacio de ensayo antes de aprobar.';}};editorState.refresh();
    trialForm.onsubmit=event=>{event.preventDefault();void run(async()=>{editorState?.refresh();if(trialButton.disabled||selectedScope!==scope())throw Error('Selecciona una versión y un ámbito coherentes para este ensayo.');if(!trialForm.reportValidity())throw Error('Escribe todos los parámetros actuales del ensayo.');const inputs=Object.fromEntries([...trialFields].filter(([,entry])=>entry.field.value!=='').map(([name,{field,spec}])=>[name,spec.enum||spec.type==='boolean'?JSON.parse(field.value):['number','integer'].includes(spec.type)?Number(field.value):field.value]));await planRequest('revalidate',{id:skill.id,version:skill.version,inputs,project_id:project(),conversation_id:task(),operation_id:Axx.newId()});});};
    details.append(button('Guardar cambios',async memory=>{
      if(selectedScope!==scope()||skills.find(row=>row.id===skill.id)?.version!==skill.version)throw Error('La selección o versión cambió. Vuelve a revisar esta habilidad.');const changes={version:skill.version,title:title.value,examples:examples.value.split('\n').map(s=>s.trim()).filter(Boolean),schema:JSON.parse(schema.value),templates:JSON.parse(templates.value),inference:JSON.parse(inference.value)};const updateRefs=refsCheckbox.checked;if(updateRefs){const approved=refsCheckbox.dataset.approved;if(!approved||approved!==refreshedReferences().key)throw Error('Confirma explícitamente las referencias actuales antes de guardarlas.');const latest=await api('GET','learning/context?project_id='+encodeURIComponent(project()),undefined,memory);if(selectedScope!==scope())throw Error('El ámbito cambió antes de guardar.');renderContext(latest);const current=refreshedReferences();if(current.error||current.key!==approved||!refsCheckbox.checked||refsCheckbox.dataset.approved!==approved)throw Error('Las referencias cambiaron; revisa de nuevo sus valores y revisiones.');changes.context_dependencies=current.next;}await api('POST','learning/configure',{id:skill.id,changes},memory);if(selectedScope!==scope())return;
      if(alias.value.trim()){const context=await api('GET','learning/context?project_id='+encodeURIComponent(project()),undefined,memory);if(selectedScope!==scope())return;await api('POST','learning/context',{project_id:project(),changes:{aliases:{...context.aliases,[alias.value.trim()]:skill.id}}},memory);}
      editorState=null;root.replaceChildren(); await refresh();if(updateRefs&&selectedScope===scope()){const updated=skills.find(row=>row.id===skill.id);if(updated)edit(updated);$('skills-status').textContent='Referencias guardadas en una versión nueva. Escribe los parámetros actuales y prepara su ensayo.';}
    }));
    if(skill.effect_verified) for(const [text,confirmed] of [['El resultado cumplió el objetivo',true],['El resultado necesita corrección',false]]) details.append(button(text,async memory=>{await api('POST','learning/configure',{id:skill.id,changes:{version:skill.version,goal_confirmed:confirmed}},memory);await refresh();}));
    root.append(details); root.scrollIntoView({block:'nearest'});
  }
  function renderParts() {
    $('skills-parts').replaceChildren(...parts.map((part,index)=>{
      const row=element('p',`${index+1}. ${skills.find(s=>s.id===part.id)?.title||part.id} · v${part.version}`);
      if(index){const label=element('label'),input=element('input');input.type='checkbox';input.checked=!part.depends_on.length;input.onchange=()=>{part.depends_on=input.checked?[]:[parts[index-1].part_id];};label.append(input,document.createTextNode(' Sin dependencia de la habilidad anterior'));row.append(label);}
      return row;
    }));
  }
  async function tasks(memory=captureMemory()) {
    const selected=project(),selectedTask=task(),token=++tasksRevision,result=await api('GET','learning/plans?project_id='+encodeURIComponent(selected),undefined,memory);if(token!==tasksRevision||selected!==project()||selectedTask!==task())return;const root=$('skills-tasks'); root.replaceChildren();
    taskPlans=result.plans||[];taskPlansProject=selected;renderLessonReceipts();
    for(const plan of result.plans || []) {
      const row=element('article'); row.className='setup-card';
      row.append(element('strong',plan.title||plan.text||plan.operation_id),element('p',`${plan.state==='succeeded'&&(plan.mission?.completed===false||!criteriaSatisfied(plan))?'Objetivo pendiente de verificación':states[plan.state]||plan.state} · ${plan.mission?.verified_steps?.length??(plan.step_records||[]).filter(s=>s.state==='succeeded').length}/${plan.steps?.length||0} pasos · ${plan.model_calls_used||0} llamadas al modelo`));
      renderGoal(row,plan);
      row.append(button('Consultar',async()=>{if(commands.busy||commands.operation)throw new Error('Termina o cancela la acción activa antes de cambiar la tarea mostrada.');const selected=scope(),fresh=await api('GET','learning/plan?id='+encodeURIComponent(plan.operation_id));if(selected===scope())adopt(fresh);}));
      if(!['succeeded','cancelled'].includes(plan.state)) row.append(button('Cancelar tarea',async()=>{await api('POST','learning/cancel',{operation_id:plan.operation_id});await tasks();}));
      if(!['succeeded','cancelled','running','needs_input','goal_pending'].includes(plan.state)) row.append(button('Retomar y revisar',()=>planRequest('resume',{operation_id:plan.operation_id,approved:false,...(plan.plan_hash?{plan_hash:plan.plan_hash}:{})})));
      if(['failed','needs_input'].includes(plan.state)) { const correction=element('input'); correction.className='field'; correction.placeholder=plan.state==='needs_input'?(plan.message||'Información que falta'):'Qué debe cambiar'; correction.setAttribute('aria-label','Corrección o aclaración de la tarea'); row.append(correction,button(plan.state==='needs_input'?'Completar y preparar':'Preparar reparación',()=>planRequest('repair',{operation_id:plan.operation_id,text:correction.value,...prefs()}))); }
      const detail=element('details'); detail.append(element('summary','Evidencias y trazabilidad')); const pre=element('pre',JSON.stringify(plan,null,2)); pre.style.cssText='white-space:pre-wrap;max-height:220px;overflow:auto'; detail.append(pre); row.append(detail); root.append(row);
    }
    if(!root.children.length) root.textContent='No hay tareas en este proyecto.';
  }
  async function inventory() {
    const result=await api('GET','demonstration/inventory'); windows=result.windows||[];
    $('skills-window').replaceChildren(...windows.map((w,index)=>new Option(w.title || 'Ventana '+w.window_id,String(index))));
    $('skills-inventory-result').textContent=JSON.stringify(result,null,2);
  }
  function showDemo(record) {
    demo=record; const active=['starting','recording'].includes(record.status);
    $('skills-demo-start').disabled=active; $('skills-demo-stop').disabled=$('skills-demo-cancel').disabled=!active;
    $('skills-demo-prepare').disabled=record.status!=='stopped'||!record.event_count||!record.reference;
    $('skills-demo-status').textContent=`${({idle:'Lista',starting:'Iniciando observación',recording:'Observando',stopped:'Observación terminada',cancelled:'Cancelada',interrupted:'Interrumpida',failed:'Falló'})[record.status]||record.status} · ${record.event_count||0} eventos. ${record.reason||''}`;
    clearTimeout(polling); if(active) polling=setTimeout(()=>run(async()=>showDemo(await api('GET','demonstration/status'))),1000);
  }
  async function stopDemo(cancel=false) { showDemo(await api('POST','demonstration/stop',{id:demo?.id,cancel})); }
  $('skills-refresh').onclick=()=>run(refresh); $('skills-search').oninput=$('skills-favorites').onchange=renderList;
  $('skills-project').onchange=()=>run(async()=>{if(commands.busy||commands.operation){$('skills-project').value=Axx.companion.data.prefs.skillProject||'';throw new Error('Termina o cancela la acción activa antes de cambiar de proyecto.');}Axx.companion.data.prefs.skillProject=project();Axx.companion.save();commands.learningQuestion=null;commands.actionContext={};parts=[];renderParts();editorState=null;$('skills-editor').replaceChildren();contextDirty.clear();for(const id of Object.values(contextInputs))$(id).value='';$('skills-context-evidence').replaceChildren();$('skills-context-origin').replaceChildren();$('skills-context-status').textContent='Consultando contexto del proyecto…';syncLessonScope();++refreshRevision;++tasksRevision;await refresh();});
  for(const [field,id] of Object.entries(contextInputs))$(id).oninput=event=>{if(event.isTrusted){contextDirty.add(field);$('skills-context-status').textContent='Hay campos editados sin guardar.';}};
  $('skills-save-context').onclick=()=>contextAction(saveContext);$('skills-invalidate-context').onclick=()=>contextAction(memory=>invalidateContext(false,memory));$('skills-forget-context').onclick=()=>contextAction(memory=>invalidateContext(true,memory));
  $('skills-lessons').addEventListener('toggle',()=>{if($('skills-lessons').open)void run(loadLessons);});$('skills-lessons-search').onsubmit=event=>{event.preventDefault();void run(loadLessons);};
  $('skills-lesson-form').oninput=event=>{if(event.isTrusted){const form=$('skills-lesson-form');form.dataset.scope=scope();if(event.target.name==='user_correction')form.dataset.humanCorrection=event.target.value;if(event.target.name==='allow_provider')form.dataset.providerConsent=String(event.target.checked);if(event.target.name==='operation_id'){form.elements.allow_provider.checked=false;delete form.dataset.providerConsent;renderLessonReceipts();}}};$('skills-lesson-form').onsubmit=event=>{event.preventDefault();void lessonAction(recordLesson);};
  $('skills-lesson-form').elements.failed_receipt.onchange=event=>{const form=$('skills-lesson-form');if(!event.isTrusted)return;form.dataset.scope=scope();form.elements.operation_id.value=event.target.value;form.elements.verification_operation_id.value='';form.elements.allow_provider.checked=false;delete form.dataset.providerConsent;renderLessonReceipts();};
  $('skills-lesson-form').elements.verified_receipt.onchange=event=>{if(event.isTrusted){$('skills-lesson-form').dataset.scope=scope();$('skills-lesson-form').elements.verification_operation_id.value=event.target.value;}};
  const renderChat=Axx.companion.renderChat?.bind(Axx.companion);if(renderChat)Axx.companion.renderChat=(...args)=>{const result=renderChat(...args);syncLessonScope();return result;};
  $('skills-tasks-refresh').onclick=()=>run(tasks);
  for(const id of ['skills-objective','skills-goal-criteria'])$(id).addEventListener('input',clearGoalReview);
  $('skills-goal-review').onclick=event=>run(()=>{if(!event.isTrusted)throw Error('Revisa explícitamente los criterios antes de preparar la misión.');const goal=reviewedGoal($('skills-objective').value,$('skills-goal-criteria').value);goalReview={key:goalDraftKey(),scope:scope(),goal};$('skills-goal-preview').textContent=JSON.stringify(goal,null,2);$('skills-goal-prepare').disabled=false;});
  $('skills-goal-prepare').onclick=()=>run(async()=>{if(!task()||!goalReview||goalReview.scope!==scope()||goalReview.key!==goalDraftKey())throw Error('Selecciona un chat y revisa los criterios actuales.');const reviewed=goalReview;await planRequest('propose',{text:reviewed.goal.intent,goal_spec:reviewed.goal,operation_id:Axx.newId(),project_id:project(),conversation_id:task(),...prefs()});if(goalReview===reviewed&&reviewed.scope===scope())clearGoalReview();});
  $('skills-clear-parts').onclick=()=>{parts=[];renderParts();};
  $('skills-compose').onclick=()=>run(()=>planRequest('compose',{text:$('skills-objective').value,parts,operation_id:Axx.newId(),project_id:project()}));
  $('skills-inventory').onclick=()=>run(inventory);
  $('skills-demo-start').onclick=()=>run(async()=>{const window=windows[Number($('skills-window').value)];if(!window)throw new Error('Selecciona una ventana detectada.');showDemo(await api('POST','demonstration/start',{window_id:window.window_id,pid:window.pid,title:window.title,objective:$('skills-demo-objective').value}));});
  $('skills-demo-stop').onclick=()=>run(()=>stopDemo()); $('skills-demo-cancel').onclick=()=>run(()=>stopDemo(true));
  $('skills-demo-prepare').onclick=()=>run(()=>commands.planAction($('skills-demo-objective').value||demo.objective,{context:{demonstration:demo.reference}}));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));},true);
  if(Axx.isNative()) { void Axx.app.bridge.listen('axx-cancel',()=>{if(['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));}); }
  function invalidateMemory(id){
    editorState?.bindings?.invalidateMemory(id);
    if(task()!==id)return;++refreshRevision;++tasksRevision;++lessonRevision;skills=[];parts=[];taskPlans=taskPlans.filter(plan=>plan.conversation_id!==id);currentContext=null;currentContextProject='';editorState=null;clearGoalReview();
    $('skills-list').replaceChildren();$('skills-editor').replaceChildren();$('skills-tasks').replaceChildren();$('skills-lessons-list').replaceChildren();$('skills-context-evidence').replaceChildren();$('skills-context-origin').replaceChildren();
    for(const [field,input] of Object.entries(contextInputs))if(!contextDirty.has(field))$(input).value='';renderParts();
  }
  function memoryFolder(){const meta=currentContext?.context_meta?.current_folder;return currentContextProject===project()&&meta?.status==='active'&&[null,undefined,'',task()].includes(meta.task_id)&&!(meta.expires_at!=null&&meta.expires_at*1000<=Date.now())?currentContext.current_folder:undefined;}
  Axx.skillLibrary={project,refresh,tasks,invalidateMemory,memoryFolder,memoryTarget:()=>editorState?.scope===scope()?{id:editorState.id,version:editorState.version,...(memoryFolder()?{folder:memoryFolder()}:{})}:null,continueTask:(operation_id,text,memory)=>planRequest('repair',{operation_id,text,...prefs()},memory),open:(id)=>{commands.open();section.scrollIntoView({block:'start'});return run(async memory=>{await refresh(memory);if(id){const selected=skills.find(s=>s.id===id);if(!selected)throw new Error('La capacidad no está disponible en este proyecto.');edit(selected);$('skills-editor').scrollIntoView({block:'nearest'});}});},learn:()=>{commands.open();$('skills-demonstration').open=true;$('skills-demonstration').scrollIntoView({block:'start'});run(async()=>{await inventory();showDemo(await api('GET','demonstration/status'));});}};
  const openFeature=Axx.companion.openFeature.bind(Axx.companion);
  Axx.companion.openFeature=id=>id==='learn'?Axx.skillLibrary.learn():openFeature(id);
  $('command-library-learned').textContent='Abrir mis habilidades'; $('command-library-learned').onclick=()=>Axx.skillLibrary.open();
  const quick=button('Aprende esto',()=>Axx.skillLibrary.learn()); quick.id='skills-learn-quick'; $('command-library').prepend(quick);
})();
