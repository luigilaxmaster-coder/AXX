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
  <p>Describe una tarea. Axx propone una herramienta que puedes revisar, probar y guardar con sus resultados.</p>
  <form id="cap-form"><label class="setting">Qué quieres que aprenda<textarea id="cap-goal" rows="3" maxlength="4000" required placeholder="Por ejemplo: consultar el estado del equipo y guardar un resumen"></textarea></label>
  <div class="cap-row"><label class="setting">Tipo<select id="cap-kind"><option value="workflow">Procedimiento con comandos disponibles</option><option value="source_proposal">Propuesta de herramienta en código</option></select></label>
  <button id="cap-generate" type="submit" class="primary">Crear propuesta</button></div>
  <p id="cap-provider"></p></form>
  <p id="cap-status" role="status" aria-live="polite"></p>
  <div class="cap-row"><h3>Mis capacidades</h3><button id="cap-refresh" type="button">Actualizar</button></div>
  <div id="cap-list" class="cap-list"></div><article id="cap-editor" class="cap-editor" hidden></article>`;
  $('view-commands').prepend(section);
  let current = null, busy = false, serial = 0;
  const stateNames = {draft:'Borrador', reviewed:'Revisada', approved:'Revisada', validated:'Comprobada', active:'Activa', revoked:'Desactivada', validation_pending:'Prueba pendiente', review_required:'Revisión de código', testing:'En comprobación', verified:'Comprobada'};
  const stateText = value => stateNames[value] || value || 'Borrador';
  const api = async (method, action, body) => {
    const r = await Axx.backendRequest(method, '/axx-api/capabilities/' + action, body);
    if (r?.error) throw new Error(r.error.message || 'No se pudo completar la solicitud.');
    return r;
  };
  const status = text => { $('cap-status').textContent = text; Axx.resident?.schedule(); };
  const prefs = () => { const p = Axx.companion.data.prefs; return {model:p.model || '',provider_name:p.apiConnection || '',selection_mode:p.selection_mode || 'manual'}; };
  const reference = r => ({id:r.id, revision:r.revision, digest:r.digest});
  const button = (text, action, primary = false) => { const n = el('button', text, primary ? 'primary' : ''); n.type = 'button'; n.onclick = () => void run(action); return n; };
  function lock(value) { busy = value; section.setAttribute('aria-busy', String(value)); for (const n of section.querySelectorAll('button,input,select,textarea')) n.disabled = value; }
  async function run(action) {
    if (busy) return;
    lock(true);
    try { await action(); }
    catch (error) { status(error.message || String(error)); }
    finally { lock(false); Axx.resident?.schedule(); }
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
    const p = prefs(); $('cap-provider').textContent = 'Modelo seleccionado: ' + (p.model || 'automático según tus ajustes') + '. Solo se envían el objetivo y los contratos disponibles.';
  }
  async function mutate(action, extra = {}) {
    current = await api('POST', action, {...reference(current), ...extra});
    await refresh(current.id);
  }
  function render() {
    const root = $('cap-editor'); root.hidden = !current; root.replaceChildren(); if (!current) return;
    const r = current, def = r.definition, source = def.kind === 'source_proposal';
    const head = el('div', undefined, 'cap-row'); head.append(el('h3', def.title), el('span', `v${r.revision} · ${stateText(r.state)}`, 'cap-stage')); root.append(head);
    root.append(el('p', def.objective));
    root.append(el('p', source ? 'Código propuesto para revisión e integración. Axx no lo ejecuta ni lo instala automáticamente.' : r.validation?.runtime_verified ? 'Efecto comprobado por el ejecutor. La activación conserva los permisos de cada comando.' : 'Contrato revisado. La comprobación real se registra al ejecutar la prueba.'));
    if (!source) {
      const steps = el('ol', undefined, 'cap-steps');
      for (const step of r.validation?.steps || def.templates || []) { const li = el('li', step.command_id); li.append(el('pre', JSON.stringify(step.inputs, null, 2))); steps.append(li); }
      root.append(steps);
      if (r.validation?.risks?.length) root.append(el('p', 'Riesgos declarados: ' + r.validation.risks.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join(' · ')));
    } else { const code = el('pre', def.source); root.append(code); }
    const details = el('details'); details.append(el('summary', 'Revisar y editar la definición'));
    const label = el('label', 'Definición y parámetros (JSON)', 'setting'); const editor = el('textarea', undefined, 'cap-code'); editor.id = 'cap-definition'; editor.rows = 12; editor.value = JSON.stringify(def, null, 2); label.append(editor); details.append(label);
    details.append(button('Guardar una nueva versión', async () => { const definition = JSON.parse(editor.value); await mutate('revise', {definition}); status('Nueva versión guardada. Requiere revisión y comprobación propias.'); })); root.append(details);
    const actions = el('div', undefined, 'cap-actions');
    if (!source && r.state !== 'revoked' && r.state !== 'active') {
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
    if (r.state === 'active' && Axx.skillLibrary) actions.append(button('Usar capacidad', () => Axx.skillLibrary.open(r.skill_id), true));
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
    status('Axx está preparando la propuesta…'); current = await api('POST','generate',{goal,kind:$('cap-kind').value,...prefs(),conversation_id:Axx.chatWorkspace?.active?.id});
    await refresh(current.id); status('Propuesta guardada. Revisa su definición y sus parámetros.'); $('cap-editor').scrollIntoView({block:'nearest'});
  }); };
  $('cap-refresh').onclick = () => void run(() => refresh());
  async function open(goal = '') { Axx.companion.openFeature('commands'); if (goal) $('cap-goal').value = goal; await run(() => refresh()); section.scrollIntoView({block:'start'}); $('cap-goal').focus(); }
  const profileLink = button('Crear y mejorar capacidades', () => open()); $('view-agent').append(profileLink);
  const send = Axx.companion.send.bind(Axx.companion);
  Axx.companion.send = async (text, metadata) => { const match = String(text || '').trim().match(/^\/(?:capacidad|herramienta)(?:\s+([\s\S]+))?$/i); if (match) return open(match[1] || ''); return send(text, metadata); };
  Axx.capabilityWorkshop = {open,refresh,get current(){return current;}};
  void run(() => refresh());
})(window.Axx);
