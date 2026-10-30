/* Versioned capability proposals. Execution remains in the existing command service. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative() || !Axx.commandLibrary || !document.getElementById('view-commands')) return;
  const $ = id => document.getElementById(id), commands = Axx.commandLibrary;
  const el = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
  const section = el('section'); section.id = 'capability-workshop'; section.setAttribute('aria-labelledby', 'cap-title');
  section.innerHTML = `<style>
    #capability-workshop{margin:0 0 26px;padding:0 0 24px;border-bottom:1px solid var(--line);color:var(--ink)}
    #capability-workshop h2{margin:4px 0 8px;font-size:22px;letter-spacing:-.5px}
    #capability-workshop h3{margin:0;font-size:15px}
    #capability-workshop p{font-size:13px;line-height:1.65;color:var(--secondary)}
    #capability-workshop .cap-kicker{font-size:10px;letter-spacing:1.5px;font-weight:600;text-transform:uppercase}
    #capability-workshop .cap-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
    #capability-workshop .cap-actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
    #capability-workshop .cap-list{display:grid;gap:8px;margin:12px 0}
    #panel #capability-workshop .cap-item{text-align:left;width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px!important}
    #capability-workshop .cap-item span{font-size:11px;color:var(--secondary)}
    #capability-workshop .cap-editor{padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--surface-subtle);margin-top:16px}
    #capability-workshop .cap-editor[hidden]{display:none!important}
    #capability-workshop textarea{width:100%;box-sizing:border-box;resize:vertical}
    #capability-workshop .cap-code{font:12px/1.6 ui-monospace,Consolas,monospace!important;min-height:220px}
    #capability-workshop .cap-stage{display:inline-block;padding:4px 9px;border-radius:99px;background:var(--accent-soft);color:var(--ink);font-size:11px}
    #capability-workshop .cap-empty{padding:20px;border:1px dashed var(--line);border-radius:12px;text-align:center}
    #capability-workshop .cap-steps{padding-left:20px;font-size:12px;line-height:1.65}
    #capability-workshop pre{max-height:210px;overflow:auto}
  </style>
  <p class="cap-kicker">Taller de Axx</p><h2 id="cap-title">Crear y mejorar capacidades</h2>
  <p>Describe una tarea. Axx prepara código o un procedimiento, muestra las pruebas y pide tu aprobación antes de activar esa versión.</p>
  <form id="cap-form"><label class="setting">Qué quieres que aprenda<textarea id="cap-goal" rows="3" maxlength="4000" required placeholder="Por ejemplo: consultar el estado del equipo y guardar un resumen"></textarea></label>
  <div class="cap-row"><label class="setting">Tipo<select id="cap-kind"><option value="workflow">Procedimiento con comandos disponibles</option><option value="python_transform">Código para transformar y calcular datos</option><option value="source_proposal">Propuesta de integración para revisión técnica</option></select></label>
  <button id="cap-generate" type="submit" class="primary">Crear propuesta</button></div>
  <p id="cap-document-reference" hidden></p><button id="cap-document-clear" type="button" hidden>Quitar referencia</button>
  <p id="cap-provider"></p></form>
  <p id="cap-status" role="status" aria-live="polite"></p>
  <div class="cap-row"><h3>Mis capacidades</h3><button id="cap-refresh" type="button">Actualizar</button></div>
  <div id="cap-list" class="cap-list"></div><article id="cap-editor" class="cap-editor" hidden></article>`;
  $('view-commands').prepend(section);
  let current = null, busy = false, serial = 0, task = null, requestMemory = null, selectedDocuments = [];
  const stateNames = {draft:'Borrador', reviewed:'Revisada', approved:'Revisada', validated:'Comprobada', active:'Activa', revoked:'Desactivada', validation_pending:'Prueba pendiente', review_required:'Revisión de código', testing:'En comprobación', verified:'Comprobada'};
  const stateText = value => stateNames[value] || value || 'Borrador';
  const api = async (method, action, body) => {
    const memory = requestMemory || commands.captureMemory(); commands.checkMemory(memory, true);
    const r = await commands.request(method, '/axx-api/capabilities/' + action, body, memory);
    commands.checkMemory(memory, true);
    if (r?.error) throw new Error(r.error.message || 'No se pudo completar la solicitud.');
    return r;
  };
  const status = text => { $('cap-status').textContent = text; Axx.resident?.schedule(); };
  const prefs = () => { const p = Axx.companion.data.prefs; return {model:p.model || '',provider_name:p.provider === 'chatgpt' ? '@codex' : p.apiConnection || '',selection_mode:p.selection_mode || 'manual'}; };
  const reference = r => ({id:r.id, revision:r.revision, digest:r.digest});
  const button = (text, action, primary = false) => { const n = el('button', text, primary ? 'primary' : ''); n.type = 'button'; n.onclick = () => void run(action); return n; };
  function lock(value) { busy = value; section.setAttribute('aria-busy', String(value)); for (const n of section.querySelectorAll('button,input,select,textarea')) n.disabled = value; }
  async function run(action, memory = commands.captureMemory()) {
    if (busy) return;
    requestMemory = memory;
    lock(true);
    try { commands.checkMemory(requestMemory, true); await action(); }
    catch (error) { status(error.message || String(error)); }
    finally { requestMemory = null; lock(false); Axx.resident?.schedule(); }
  }
  async function refresh(selectedId = current?.id) {
    const generation = ++serial, r = await api('GET', 'list');
    if (generation !== serial) return;
    const list = $('cap-list'); list.replaceChildren();
    for (const row of r.capabilities || []) {
      const n = button('', async () => { current = await api('GET', 'get?id=' + encodeURIComponent(row.id)); render(); }); n.className = 'cap-item';
      n.append(el('strong', row.title || row.definition?.title), el('span', `v${row.revision} · ${stateText(row.state)}`)); list.append(n);
    }
    if (!list.children.length) list.append(el('p', 'Tus propuestas y sus versiones aparecerán aquí.', 'cap-empty'));
    if (selectedId) { current = await api('GET', 'get?id=' + encodeURIComponent(selectedId)); render(); }
    const p = prefs(); $('cap-provider').textContent = 'Modelo seleccionado: ' + (p.model || 'automático según tus ajustes') + '. Se envían el objetivo, los contratos disponibles y la referencia documental seleccionada cuando exista.';
    status(`${r.capabilities?.length || 0} propuestas guardadas. Revisa la versión antes de activarla.`);
  }
  async function mutate(action, extra = {}) {
    const memory = requestMemory || commands.captureMemory(); commands.checkMemory(memory, true);
    current = await api('POST', action, {...reference(current), ...extra});
    await refresh(current.id);
    if (action === 'activate' && task?.capability_build?.id === current.id) {
      if(task.capability_build.revision!==current.revision || task.capability_build.digest!==current.digest)
        task=await commands.request('POST','/axx-api/learning/bind-capability',{operation_id:task.operation_id,...reference(current),goal_revision:task.goal_revision},memory);
      commands.checkMemory(memory, true);
      const plan = await commands.request('POST','/axx-api/learning/resume',{operation_id:task.operation_id,approved:false},memory);
      commands.checkMemory(memory, true);
      if (plan.conversation_id === Axx.chatWorkspace?.active?.id) {
        commands.lastOperation=plan; commands.operation=plan.state==='awaiting_approval'?plan:null;
        commands.renderOperation(plan);commands.status(plan.message);Axx.companion.openChat();
      }
    }
  }
  function render() {
    const root = $('cap-editor'); root.hidden = !current; root.replaceChildren(); if (!current) return;
    const r = current, def = r.definition, source = def.kind === 'source_proposal', transform = def.kind === 'python_transform';
    const head = el('div', undefined, 'cap-row'); head.append(el('h3', def.title), el('span', `v${r.revision} · ${stateText(r.state)}`, 'cap-stage')); root.append(head);
    root.append(el('p', def.objective));
    root.append(el('p', source ? 'Código propuesto para revisión e integración. Axx no lo ejecuta ni lo instala automáticamente.' : transform ? 'Código puro acotado: transforma datos sin acceso a archivos, red, procesos ni credenciales. La aprobación corresponde al código, contratos y pruebas de esta versión.' : r.validation?.runtime_verified ? 'Efecto comprobado por el ejecutor. La activación conserva los permisos de cada comando.' : 'Contrato revisado. La comprobación real se registra al ejecutar la prueba.'));
    root.append(el('p', 'Huella de la versión: ' + r.digest));
    if (r.document_references?.length) {
      const sources = el('details'); sources.append(el('summary', 'Fuentes documentales de esta versión'));
      for (const ref of r.document_references) sources.append(el('p', ref.document_id + ' · revisión ' + ref.revision), el('pre', ref.record_sha256 + '\n' + ref.member_sha256));
      root.append(sources);
    }
    if (!source && !transform) {
      const steps = el('ol', undefined, 'cap-steps');
      for (const step of r.validation?.steps || def.templates || []) { const li = el('li', step.command_id); li.append(el('pre', JSON.stringify(step.inputs, null, 2))); steps.append(li); }
      root.append(steps);
      if (r.validation?.risks?.length) root.append(el('p', 'Riesgos declarados: ' + r.validation.risks.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' · ')));
    } else { const code = el('pre', def.source); root.append(code); }
    if (transform) {
      const tests = el('details'); tests.append(el('summary', 'Contratos, pruebas y resultados'));
      tests.append(el('pre', JSON.stringify({schema:def.schema,output_schema:def.output_schema,tests:def.tests,validation:r.validation}, null, 2))); root.append(tests);
    }
    const details = el('details'); details.append(el('summary', 'Revisar y editar la definición'));
    const label = el('label', 'Definición y parámetros (JSON)', 'setting'); const editor = el('textarea', undefined, 'cap-code'); editor.id = 'cap-definition'; editor.rows = 12; editor.value = JSON.stringify(def, null, 2); label.append(editor); details.append(label);
    details.append(button('Guardar una nueva versión', async () => { const definition = JSON.parse(editor.value); await mutate('revise', {definition}); status('Nueva versión guardada. Requiere revisión y comprobación propias.'); })); root.append(details);
    const actions = el('div', undefined, 'cap-actions');
    if (transform && r.state !== 'revoked' && r.state !== 'active') {
      actions.append(button('Ejecutar pruebas de esta versión', async () => {
        const result = await api('POST', 'validate', reference(r)); await refresh(r.id);
        status(result.self_tests_passed ? 'Todas las pruebas declaradas pasaron. Revisa el código antes de aprobar.' : 'Hay pruebas fallidas. Revisa el resultado y corrige la propuesta.');
      }));
      if (r.validation?.self_tests_passed && !r.approval) actions.append(button('Aprobar este código y sus contratos', async () => { await mutate('approve', {confirmed:true}); status('Código aprobado para esta huella. Falta activarlo.'); }, true));
      if (r.approval) actions.append(button('Activar comando aprobado', async () => { await mutate('activate'); status('Comando activado en la biblioteca. Cada uso valida sus parámetros.'); }, true));
    } else if (!source && r.state !== 'revoked' && r.state !== 'active') {
      if (!r.approval) actions.append(button('Aprobar esta versión', async () => { await mutate('approve', {confirmed:true}); status('Versión aprobada. Preparar la prueba mostrará las acciones y sus destinos.'); }, true));
      else {
        actions.append(button(r.validation_operation_id ? 'Consultar prueba' : 'Preparar prueba', async () => {
          if (commands.busy || commands.operation) throw new Error('Revisa o cancela la acción pendiente antes de preparar otra.');
          const plan = await api('POST', 'prepare', {...reference(r),conversation_id:Axx.chatWorkspace?.active?.id});
          commands.lastOperation = plan; commands.operation = ['prepared','awaiting_approval','running'].includes(plan.state) ? plan : null;
          commands.renderOperation(plan); commands.status(plan.message || stateText(plan.state));
          if (commands.operation || plan.state === 'unknown') commands.open();
          await refresh(r.id); status('Prueba preparada. Revisa sus pasos en la tarjeta de comandos.');
        }, true));
        if (r.validation_operation_id) actions.append(button('Comprobar resultado y activar', async () => { await mutate('activate'); status('Capacidad activada con evidencia. Ya aparece en Mis habilidades.'); }, true));
      }
    }
    if (r.state === 'active' && transform) actions.append(button('Usar comando', async () => { await commands.search(r.generated_command_id); commands.open(); }, true));
    else if (r.state === 'active' && Axx.skillLibrary) actions.append(button('Usar capacidad', () => Axx.skillLibrary.open(r.skill_id), true));
    if (r.active_revision != null && r.state !== 'revoked') actions.append(button('Desactivar capacidad', async () => { await mutate('revoke'); status('Capacidad desactivada. Se conservan sus versiones y resultados.'); }));
    actions.append(button('Exportar propuesta', async () => {
      const file = await api('GET', 'export?id=' + encodeURIComponent(r.id) + '&revision=' + r.revision);
      const url = URL.createObjectURL(new Blob([file.content], {type:file.mime_type})); const a = el('a'); a.href = url; a.download = file.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); status('Exportación preparada.');
    })); root.append(actions);
    const improve = el('details'); improve.append(el('summary', 'Pedir una mejora a Axx'));
    const improveLabel = el('label', 'Qué debe mejorar', 'setting'), goal = el('textarea'); goal.rows = 3; goal.maxLength = 4000; goal.id = 'cap-improvement'; improveLabel.append(goal); improve.append(improveLabel);
    improve.append(button('Proponer nueva versión', async () => {
      if (!goal.value.trim()) throw new Error('Describe la mejora que necesitas.');
      status('Axx está preparando una nueva versión…');
      current = await api('POST', 'generate', {goal:goal.value.trim(),kind:def.kind,...prefs(),capability_id:r.id,revision:r.revision,digest:r.digest,conversation_id:Axx.chatWorkspace?.active?.id});
      await refresh(current.id); status('Mejora guardada como una nueva propuesta.');
    })); root.append(improve);
    const versions = r.versions || [];
    if (versions.length > 1) { const history = el('details'); history.append(el('summary', 'Versiones anteriores'));
      for (const v of versions) { const revision = typeof v === 'number' ? v : v.revision; if (!revision || revision === r.revision) continue;
        history.append(button('Restaurar v' + revision + ' como propuesta', async () => { await mutate('rollback', {target_revision:revision}); status('Versión recuperada como propuesta nueva. Revisa y comprueba antes de activarla.'); }));
      } root.append(history);
    }
  }
  $('cap-form').onsubmit = event => { event.preventDefault(); void run(async () => {
    const goal = $('cap-goal').value.trim(); if (!goal) throw new Error('Describe la capacidad que necesitas.');
    status('Axx está preparando la propuesta…'); current = await api('POST','generate',{goal,kind:$('cap-kind').value,...prefs(),conversation_id:Axx.chatWorkspace?.active?.id,
      ...(selectedDocuments.length ? {document_references:structuredClone(selectedDocuments)} : {})});
    await refresh(current.id); status('Propuesta guardada. Revisa su definición y sus parámetros.'); $('cap-editor').scrollIntoView({block:'nearest'});
  }); };
  $('cap-refresh').onclick = () => void run(() => refresh());
  const openFeature = Axx.companion.openFeature.bind(Axx.companion);
  Axx.companion.openFeature = id => { const result = openFeature(id); if (id === 'commands' && !busy) void run(() => refresh()); return result; };
  async function open(goal = '') { await run(async () => { Axx.companion.openFeature('commands'); if (goal) $('cap-goal').value = goal; await refresh(); section.scrollIntoView({block:'start'}); $('cap-goal').focus(); }); }
  function selectDocuments(references, title) {
    selectedDocuments = structuredClone(references);
    $('cap-document-reference').textContent = selectedDocuments.length ? 'Referencia documental: ' + (title || 'Fuentes de la tarea') + '. Describe qué quieres aprender; crear una propuesta no la ejecuta.' : '';
    $('cap-document-reference').hidden = $('cap-document-clear').hidden = !selectedDocuments.length;
  }
  async function openDocument(procedure, title) {
    if (!procedure?.document_reference || busy) return;
    selectDocuments([procedure.document_reference], title || 'Documento seleccionado');
    await open();
  }
  $('cap-document-clear').onclick = () => { if (!busy) selectDocuments([]); };
  function invalidateMemory(id) {
    const owns = item => item && ((!item.memory_scope && !item.conversation_id && !item.memory_dependencies?.length)
      || item.memory_scope?.task_id === id || item.conversation_id === id || item.memory_dependencies?.some(ref => ref.task_id === id));
    if (owns(current) || owns(task)) { ++serial; current = task = null; render(); $('cap-list').replaceChildren(); }
  }
  async function openTask(plan) {
    if (plan.conversation_id && plan.conversation_id !== Axx.chatWorkspace?.active?.id) return;
    if (!plan.capability_build?.id) return;
    task=plan;
    await run(async()=>{Axx.companion.openFeature('commands');await refresh(plan.capability_build.id);section.scrollIntoView({block:'start'});status('Objetivo conservado: '+plan.request+'. Revisa esta capacidad; al activarla Axx retomará la tarea.');});
  }
  const profileLink = button('Crear y mejorar capacidades', () => open()); $('view-agent').append(profileLink);
  async function propose(goal, kind = 'source_proposal', documentReferences = []) {
    if (busy) return;
    selectDocuments(documentReferences);
    const memory = commands.captureMemory(); await open(goal);
    await run(async () => {
      $('cap-kind').value = kind;
      status('Falta una capacidad ejecutable. Axx está preparando código para revisión…');
      current = await api('POST', 'generate', {goal,kind,...prefs(),conversation_id:Axx.chatWorkspace?.active?.id,
        ...(selectedDocuments.length ? {document_references:structuredClone(selectedDocuments)} : {})});
      await refresh(current.id); status('Propuesta preparada. Revisa el código y sus límites antes de aprobar su implementación.');
    }, memory);
  }
  const send = Axx.companion.send.bind(Axx.companion);
  Axx.companion.send = async (text, metadata) => {
    const raw = String(text || '').trim(), match = raw.match(/^\/(?:capacidad|herramienta)(?:\s+([\s\S]+))?$/i);
    if (match) return open(match[1] || '');
    const create = raw.match(/^(?:crea|crear|desarrolla|programa)\s+(?:una?\s+)?(?:capacidad|habilidad|comando|herramienta)\s+(?:para\s+)?([\s\S]{3,4000})$/i);
    if (create) { Axx.companion.message('user', raw, 'local'); return propose(create[1], /^(?:transformar|calcular|convertir texto|formatear|normalizar)\b/i.test(create[1]) ? 'python_transform' : 'workflow'); }
    return send(text, metadata);
  };
  Axx.capabilityWorkshop = {open,openDocument,openTask,propose,refresh,invalidateMemory,get current(){return current;}};
  void run(() => refresh());
})(window.Axx);
