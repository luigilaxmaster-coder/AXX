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
  const states = {candidate:'Candidata', verified:'Comprobada', awaiting_approval:'Requiere aprobación', waiting_capacity:'Esperando un modelo apto',
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
    </details>
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
  let skills = [], parts = [], windows = [], demo = null, polling = null;
  const project = () => $('skills-project').value.trim();
  $('skills-project').value = Axx.companion.data.prefs.skillProject || '';
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
  const prefs = () => ({model:Axx.companion.data.prefs.model || '', provider_name:Axx.companion.data.prefs.apiConnection || '', selection_mode:Axx.companion.data.prefs.selection_mode || 'manual'});
  async function refresh() {
    const result = await api('GET', 'learning/actions?project_id=' + encodeURIComponent(project()));
    skills = result.actions || []; renderList();
    const context = await api('GET', 'learning/context?project_id=' + encodeURIComponent(project()));
    $('skills-folder').value = context.current_folder || ''; $('skills-file').value = context.current_file || ''; $('skills-app').value = context.current_application || '';
    await tasks();
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
    const result=await api('GET','learning/plans?project_id='+encodeURIComponent(project())), root=$('skills-tasks'); root.replaceChildren();
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
  $('skills-project').onchange=()=>run(async()=>{if(commands.busy||commands.operation){$('skills-project').value=Axx.companion.data.prefs.skillProject||'';throw new Error('Termina o cancela la acción activa antes de cambiar de proyecto.');}Axx.companion.data.prefs.skillProject=project();Axx.companion.save();commands.learningQuestion=null;commands.actionContext={};parts=[];renderParts();$('skills-editor').replaceChildren();await refresh();});
  $('skills-save-context').onclick=()=>run(async()=>{await api('POST','learning/context',{project_id:project(),changes:{current_folder:$('skills-folder').value,current_file:$('skills-file').value,current_application:$('skills-app').value,current_project:project()}});$('skills-status').textContent='Contexto guardado.';});
  $('skills-tasks-refresh').onclick=()=>run(tasks);
  $('skills-clear-parts').onclick=()=>{parts=[];renderParts();};
  $('skills-compose').onclick=()=>run(()=>planRequest('compose',{text:$('skills-objective').value,parts,operation_id:Axx.newId(),project_id:project()}));
  $('skills-inventory').onclick=()=>run(inventory);
  $('skills-demo-start').onclick=()=>run(async()=>{const window=windows[Number($('skills-window').value)];if(!window)throw new Error('Selecciona una ventana detectada.');showDemo(await api('POST','demonstration/start',{window_id:window.window_id,pid:window.pid,title:window.title,objective:$('skills-demo-objective').value}));});
  $('skills-demo-stop').onclick=()=>run(()=>stopDemo()); $('skills-demo-cancel').onclick=()=>run(()=>stopDemo(true));
  $('skills-demo-prepare').onclick=()=>run(()=>commands.planAction($('skills-demo-objective').value||demo.objective,{context:{demonstration:demo.reference}}));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));},true);
  if(Axx.isNative()) { void Axx.app.bridge.listen('axx-cancel',()=>{if(['starting','recording'].includes(demo?.status))run(()=>stopDemo(true));}); }
  Axx.skillLibrary={project,refresh,tasks,continueTask:(operation_id,text)=>planRequest('repair',{operation_id,text,...prefs()}),open:()=>{commands.open();section.scrollIntoView({block:'start'});run(refresh);},learn:()=>{commands.open();$('skills-demonstration').open=true;$('skills-demonstration').scrollIntoView({block:'start'});run(async()=>{await inventory();showDemo(await api('GET','demonstration/status'));});}};
  const openFeature=Axx.companion.openFeature.bind(Axx.companion);
  Axx.companion.openFeature=id=>id==='learn'?Axx.skillLibrary.learn():openFeature(id);
  $('command-library-learned').textContent='Abrir mis habilidades'; $('command-library-learned').onclick=()=>Axx.skillLibrary.open();
  const quick=button('Aprende esto',()=>Axx.skillLibrary.learn()); quick.id='skills-learn-quick'; $('command-library').prepend(quick);
})();
