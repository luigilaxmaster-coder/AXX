/* Skills use the same reviewed execution surface as individual commands. */
(() => {
  'use strict';
  const Axx = window.Axx, commands = Axx?.commandLibrary;
  if (!commands) return;
  const $ = id => document.getElementById(id);
  const api = (method, action, body) => commands.request(method, '/axx-api/' + action, body);
  const element = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  const button = (text, action) => { const node = element('button', text); node.type = 'button'; node.onclick = () => run(action); return node; };
  const run = async action => { try { await action(); } catch (error) { $('skills-status').textContent = error.message || String(error); } Axx.resident?.schedule(); };
  const states = {candidate:'Candidata', verified:'Comprobada', awaiting_approval:'Requiere aprobación', waiting_capacity:'Esperando un modelo apto', waiting_capability:'Construyendo una capacidad para esta tarea',
    succeeded:'Completada', failed:'Falló', unknown:'Resultado incierto', interrupted:'Interrumpida', cancelled:'Cancelada', expired:'Requiere revisión', running:'Ejecutando', needs_input:'Faltan datos'};
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
      <details><summary>Registrar un incidente observado</summary><p>Usa el ID de un comando fallido del historial. La biblioteca comprobará su recibo antes de guardar esta referencia.</p>
        <form id="skills-lesson-form"><label class="setting">ID del comando fallido<input name="operation_id" class="field" maxlength="128" required></label><label class="setting">Hipótesis sin confirmar<textarea name="hypothesis" class="field" maxlength="1000" required></textarea></label><label class="setting">Corrección que propones, opcional<textarea name="user_correction" class="field" maxlength="1000"></textarea></label><label class="setting">ID de prueba posterior, opcional<input name="verification_operation_id" class="field" maxlength="128"></label><button type="submit">Guardar referencia de incidente</button></form>
      </details></details>
    <details><summary>Combinar habilidades</summary><p>Añade las habilidades en el orden de la tarea. Las lecturas independientes pueden ejecutarse de dos en dos; los cambios en archivos y aplicaciones conservan un solo ejecutor.</p>
      <div id="skills-parts"></div><label class="setting">Objetivo<input id="skills-objective" class="field" maxlength="2000"></label>
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
  let skills = [], parts = [], windows = [], demo = null, polling = null, refreshRevision=0, tasksRevision=0, contextBusy=false, lessonRevision=0, lessonScope='', lessonBusy=false;
  const contextInputs={current_folder:'skills-folder',current_file:'skills-file',current_application:'skills-app'},contextDirty=new Set();
  const project = () => $('skills-project').value.trim();
  $('skills-project').value = Axx.companion.data.prefs.skillProject || '';
  const task=()=>Axx.chatWorkspace?.active?.id||null,scope=()=>JSON.stringify([project(),task()]);
  function syncLessonScope(){const selected=scope();if(selected===lessonScope)return;lessonScope=selected;++lessonRevision;$('skills-lessons-list').replaceChildren();$('skills-lesson-form').reset();delete $('skills-lesson-form').dataset.scope;delete $('skills-lesson-form').dataset.humanCorrection;$('skills-lessons-search').reset();$('skills-lessons-status').textContent='';}
  function adopt(plan) {
    commands.lastOperation = plan; commands.operation = ['awaiting_approval', 'running'].includes(plan.state) ? plan : null;
    commands.busy = false; commands.renderOperation(plan); commands.status(plan.message || states[plan.state] || plan.state);
    if (commands.operation) commands.open();
  }
  async function planRequest(action, body) {
    if (commands.busy || commands.operation) throw new Error('Revisa o cancela la acción pendiente antes de preparar otra.');
    commands.busy = true; const serial = ++commands.generation;
    commands.operation=commands.lastOperation={kind:'learned_plan',operation_id:body.operation_id,state:'planning',steps:[]};
    commands.renderOperation(commands.operation);
    try { const plan = await api('POST', 'learning/' + action, body); if (serial === commands.generation) adopt(plan); }
    finally { if (serial === commands.generation) commands.busy = false; }
  }
  const prefs = () => {const p=Axx.companion.data.prefs;return {model:p.model || '',provider_name:p.provider==='chatgpt'?'@codex':p.provider==='bridge'?p.apiConnection || '':'',selection_mode:p.selection_mode || 'manual'};};
  async function refresh() {
    const selected=project(),token=++refreshRevision;
    const [result,context] = await Promise.all([api('GET','learning/actions?project_id='+encodeURIComponent(selected)),api('GET','learning/context?project_id='+encodeURIComponent(selected))]);
    if(token!==refreshRevision||selected!==project())return;
    skills = result.actions || []; renderList();renderContext(context);syncLessonScope();
    await tasks();
    if($('skills-lessons').open)await loadLessons();
  }
  function renderContext(context){
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
  }
  async function saveContext(){
    const selected=project(),changes={};for(const field of contextDirty)changes[field]=$(contextInputs[field]).value;
    if(!Object.keys(changes).length){$('skills-status').textContent='No hay campos editados para guardar.';return;}
    const source_id=Axx.newId(),session_id=Axx.chatWorkspace?.active?.id,context_meta={};
    for(const field of Object.keys(changes))context_meta[field]={kind:'confirmed_user',origin:'user_settings',source_id,...(session_id?{session_id,task_id:session_id}:{}),observed_at:Date.now()/1000};
    const context=await api('POST','learning/context',{project_id:selected,changes:{...changes,context_meta}});
    if(selected!==project())return;
    for(const [field,value] of Object.entries(changes))if($(contextInputs[field]).value===value)contextDirty.delete(field);
    renderContext(context);$('skills-status').textContent='Contexto guardado. Solo los campos editados se registraron como confirmados por ti.';
  }
  async function invalidateContext(forget){
    const selected=project(),value=$('skills-context-origin').value;if(!value)throw Error('Selecciona una fuente o sesión registrada.');
    const context=await api('POST','learning/forget-context',{project_id:selected,...JSON.parse(value),forget});if(selected!==project())return;
    renderContext(context);$('skills-status').textContent=(forget?'Contexto olvidado':'Contexto marcado como desactualizado')+' · '+(context.invalidated||[]).length+' referencias invalidadas. Los permisos y el historial de ejecución se conservan.';
  }
  const contextAction=action=>run(async()=>{if(contextBusy)return;contextBusy=true;$('skills-save-context').disabled=$('skills-invalidate-context').disabled=$('skills-forget-context').disabled=true;try{await action();}finally{contextBusy=false;$('skills-save-context').disabled=false;$('skills-invalidate-context').disabled=$('skills-forget-context').disabled=!$('skills-context-origin').options.length;}});
  async function loadLessons(){
    syncLessonScope();const selected=scope(),currentTask=task(),currentProject=project(),token=++lessonRevision;if(!currentTask){$('skills-lessons-status').textContent='Selecciona un chat para consultar sus referencias.';return;}
    const query=$('skills-lessons-search').elements,params=new URLSearchParams({project_id:currentProject,task_id:currentTask,query:query.query.value.trim(),command_id:query.command_id.value.trim(),limit:'3'});let result;try{result=await api('GET','learning/lessons?'+params);}catch(error){if(token!==lessonRevision||selected!==scope())return;throw error;}
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
      list.style.overflowWrap='anywhere';details.append(list);row.append(details,button('Olvidar esta referencia',()=>lessonAction(async()=>{const result=await api('POST','learning/forget-lesson',{id:lesson.id});if(selected!==scope())return;await loadLessons();$('skills-lessons-status').textContent=(result.forgotten?'Referencia olvidada.':'La referencia ya no estaba guardada.')+(result.command_journal_preserved===true?' El historial de ejecución se conserva.':'');})));root.append(row);
    }
    $('skills-lessons-status').textContent=root.children.length?root.children.length+' referencias de este chat.':'No hay referencias que coincidan en este chat.';
  }
  const lessonAction=action=>run(async()=>{if(lessonBusy)return;lessonBusy=true;$('skills-lesson-form').querySelector('button').disabled=true;try{await action();}finally{lessonBusy=false;$('skills-lesson-form').querySelector('button').disabled=false;}});
  async function recordLesson(){
    const form=$('skills-lesson-form'),selected=scope(),currentTask=task();if(!currentTask)throw Error('Selecciona el chat de este incidente.');if(form.dataset.scope!==selected)throw Error('El chat o proyecto cambió. Revisa y vuelve a escribir la referencia antes de guardarla.');
    const fields=form.elements,body={operation_id:fields.operation_id.value.trim(),hypothesis:fields.hypothesis.value.trim(),project_id:project(),task_id:currentTask};if(fields.user_correction.value.trim()){if(form.dataset.humanCorrection!==fields.user_correction.value)throw Error('La corrección debe escribirla el usuario; el texto automático no se registrará como confirmado.');body.user_correction=fields.user_correction.value.trim();}if(fields.verification_operation_id.value.trim())body.verification_operation_id=fields.verification_operation_id.value.trim();
    try{await api('POST','learning/lesson',body);}catch(error){if(selected!==scope())return;throw error;}if(selected!==scope())return;await loadLessons();$('skills-lessons-status').textContent='Referencia guardada. La hipótesis sigue sin confirmar.';
  }
  function renderList() {
    const query = $('skills-search').value.toLocaleLowerCase(), list = $('skills-list'); list.replaceChildren();
    for (const skill of skills.filter(s => (!$('skills-favorites').checked || s.favorite) && [s.title, s.trigger, ...(s.examples || [])].join(' ').toLocaleLowerCase().includes(query))) {
      const card = element('article'); card.className = 'setup-card';
      card.append(element('strong', skill.title), element('p', `v${skill.version} · ${states[skill.status] || skill.status} · ${skill.goal_confirmed ? 'Objetivo confirmado' : 'Objetivo sin confirmar'}`));
      card.append(element('p', (skill.examples || []).slice(0, 3).join(' · ')));
      card.append(button(skill.favorite ? '★ Favorita' : '☆ Favorita', async () => { await api('POST','learning/configure',{id:skill.id,changes:{favorite:!skill.favorite}}); await refresh(); }));
      card.append(button('Entradas y ejecución', () => edit(skill)));
      list.append(card);
    }
    if (!list.children.length) list.textContent = 'No hay habilidades que coincidan. Usa /aprende en el chat o enseña una demostración.';
  }
  function edit(skill) {
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
    form.onsubmit = event => { event.preventDefault(); run(() => commands.planAction(skill.id,{inputs:values()})); };
    const submit = element('button', skill.executable ? 'Revisar y ejecutar' : 'Adaptador pendiente'); submit.type = 'submit'; submit.disabled = !skill.executable;
    form.append(submit, button('Añadir a tarea combinada', () => { parts.push({id:skill.id,version:skill.version,inputs:values(),part_id:'part'+parts.length,depends_on:parts.length?[parts.at(-1).part_id]:[]}); renderParts(); })); root.append(form);
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
    details.append(button('Guardar cambios',async()=>{
      await api('POST','learning/configure',{id:skill.id,changes:{version:skill.version,title:title.value,examples:examples.value.split('\n').map(s=>s.trim()).filter(Boolean),schema:JSON.parse(schema.value),templates:JSON.parse(templates.value),inference:JSON.parse(inference.value)}});
      if(alias.value.trim()){const context=await api('GET','learning/context?project_id='+encodeURIComponent(project()));await api('POST','learning/context',{project_id:project(),changes:{aliases:{...context.aliases,[alias.value.trim()]:skill.id}}});}
      root.replaceChildren(); await refresh();
    }));
    if(skill.effect_verified) for(const [text,confirmed] of [['El resultado cumplió el objetivo',true],['El resultado necesita corrección',false]]) details.append(button(text,async()=>{await api('POST','learning/configure',{id:skill.id,changes:{version:skill.version,goal_confirmed:confirmed}});await refresh();}));
    root.append(details); root.scrollIntoView({block:'nearest'});
  }
  function renderParts() {
    $('skills-parts').replaceChildren(...parts.map((part,index)=>{
      const row=element('p',`${index+1}. ${skills.find(s=>s.id===part.id)?.title||part.id} · v${part.version}`);
      if(index){const label=element('label'),input=element('input');input.type='checkbox';input.checked=!part.depends_on.length;input.onchange=()=>{part.depends_on=input.checked?[]:[parts[index-1].part_id];};label.append(input,document.createTextNode(' Sin dependencia de la habilidad anterior'));row.append(label);}
      return row;
    }));
  }
  async function tasks() {
    const selected=project(),token=++tasksRevision,result=await api('GET','learning/plans?project_id='+encodeURIComponent(selected));if(token!==tasksRevision||selected!==project())return;const root=$('skills-tasks'); root.replaceChildren();
    for(const plan of result.plans || []) {
      const row=element('article'); row.className='setup-card';
      row.append(element('strong',plan.title||plan.text||plan.operation_id),element('p',`${states[plan.state]||plan.state} · ${(plan.step_records||[]).filter(s=>s.state==='succeeded').length}/${plan.steps?.length||0} pasos · ${plan.model_calls_used||0} llamadas al modelo`));
      row.append(button('Consultar',async()=>{if(commands.busy||commands.operation)throw new Error('Termina o cancela la acción activa antes de cambiar la tarea mostrada.');adopt(await api('GET','learning/plan?id='+encodeURIComponent(plan.operation_id)));}));
      if(!['succeeded','cancelled'].includes(plan.state)) row.append(button('Cancelar tarea',async()=>{await api('POST','learning/cancel',{operation_id:plan.operation_id});await tasks();}));
      if(!['succeeded','cancelled','running','needs_input'].includes(plan.state)) row.append(button('Retomar y revisar',()=>planRequest('resume',{operation_id:plan.operation_id,approved:false})));
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
  $('skills-project').onchange=()=>run(async()=>{if(commands.busy||commands.operation){$('skills-project').value=Axx.companion.data.prefs.skillProject||'';throw new Error('Termina o cancela la acción activa antes de cambiar de proyecto.');}Axx.companion.data.prefs.skillProject=project();Axx.companion.save();commands.learningQuestion=null;commands.actionContext={};parts=[];renderParts();$('skills-editor').replaceChildren();contextDirty.clear();for(const id of Object.values(contextInputs))$(id).value='';$('skills-context-evidence').replaceChildren();$('skills-context-origin').replaceChildren();$('skills-context-status').textContent='Consultando contexto del proyecto…';syncLessonScope();++refreshRevision;++tasksRevision;await refresh();});
  for(const [field,id] of Object.entries(contextInputs))$(id).oninput=event=>{if(event.isTrusted){contextDirty.add(field);$('skills-context-status').textContent='Hay campos editados sin guardar.';}};
  $('skills-save-context').onclick=()=>contextAction(saveContext);$('skills-invalidate-context').onclick=()=>contextAction(()=>invalidateContext(false));$('skills-forget-context').onclick=()=>contextAction(()=>invalidateContext(true));
  $('skills-lessons').addEventListener('toggle',()=>{if($('skills-lessons').open)void run(loadLessons);});$('skills-lessons-search').onsubmit=event=>{event.preventDefault();void run(loadLessons);};
  $('skills-lesson-form').oninput=event=>{if(event.isTrusted){$('skills-lesson-form').dataset.scope=scope();if(event.target.name==='user_correction')$('skills-lesson-form').dataset.humanCorrection=event.target.value;}};$('skills-lesson-form').onsubmit=event=>{event.preventDefault();void lessonAction(recordLesson);};
  const renderChat=Axx.companion.renderChat?.bind(Axx.companion);if(renderChat)Axx.companion.renderChat=(...args)=>{const result=renderChat(...args);syncLessonScope();return result;};
  $('skills-tasks-refresh').onclick=()=>run(tasks);
  $('skills-clear-parts').onclick=()=>{parts=[];renderParts();};
  $('skills-compose').onclick=()=>run(()=>planRequest('compose',{text:$('skills-objective').value,parts,operation_id:Axx.newId(),project_id:project()}));
  $('skills-inventory').onclick=()=>run(inventory);
  $('skills-demo-start').onclick=()=>run(async()=>{const window=windows[Number($('skills-window').value)];if(!window)throw new Error('Selecciona una ventana detectada.');showDemo(await api('POST','demonstration/start',{window_id:window.window_id,pid:window.pid,title:window.title,objective:$('skills-demo-objective').value}));});
  $('skills-demo-stop').onclick=()=>run(()=>stopDemo()); $('skills-demo-cancel').onclick=()=>run(()=>stopDemo(true));
  $('skills-demo-prepare').onclick=()=>run(()=>commands.planAction($('skills-demo-objective').value||demo.objective,{context:{demonstration:demo.reference}}));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));},true);
  if(Axx.isNative()) { void Axx.app.bridge.listen('axx-cancel',()=>{if(['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));}); }
  Axx.skillLibrary={project,refresh,tasks,continueTask:(operation_id,text)=>planRequest('repair',{operation_id,text,...prefs()}),open:(id)=>{commands.open();section.scrollIntoView({block:'start'});return run(async()=>{await refresh();if(id){const selected=skills.find(s=>s.id===id);if(!selected)throw new Error('La capacidad no está disponible en este proyecto.');edit(selected);$('skills-editor').scrollIntoView({block:'nearest'});}});},learn:()=>{commands.open();$('skills-demonstration').open=true;$('skills-demonstration').scrollIntoView({block:'start'});run(async()=>{await inventory();showDemo(await api('GET','demonstration/status'));});}};
  const openFeature=Axx.companion.openFeature.bind(Axx.companion);
  Axx.companion.openFeature=id=>id==='learn'?Axx.skillLibrary.learn():openFeature(id);
  $('command-library-learned').textContent='Abrir mis habilidades'; $('command-library-learned').onclick=()=>Axx.skillLibrary.open();
  const quick=button('Aprende esto',()=>Axx.skillLibrary.learn()); quick.id='skills-learn-quick'; $('command-library').prepend(quick);
})();
