/* Acts Studio and Act selection in the existing chat (Evolution 3.1).
 * Profiles live in the existing AgentRegistry (/axx-api/agents/v1/*); turns go through the existing chat
 * clients with act_id, and the backend resolves the Act's own provider/model. The global AXX avatar,
 * profile and selected model are never written here. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative?.() || !Axx.companion || !document.getElementById('view-agent')) return;
  const c = Axx.companion;
  const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/agents/v1/' + path, body);
  const CONNECT = 'axx-connect', TOOL = 'axx.commands', CODE = 'axx.code', SPATIAL = 'axx.spatial', COMP = 'axx.computer';
  const CODE_OPS = ['worktree', 'patch', 'test', 'integrate', 'review'];
  const SPATIAL_OPS = ['read', 'patch', 'qa', 'cad', 'export'];
  const COMP_OPS = ['files', 'browser', 'uia', 'vm', 'foreground'];
  const FORMS = ['Core', 'Flow', 'Pearl', 'Torus', 'Split', 'Wave', 'Bloom', 'Fold', 'Spike', 'Drift', 'Orbit', 'Morph',
    'Cushion', 'Trefoil', 'Nova', 'Heart', 'Infinity', 'Helix', 'Knot', 'Petal', 'Prism', 'Capsule', 'Crescent', 'Ripple'];
  const PALETTES = ['Obsidian', 'Nebula', 'Ocean', 'Sunset', 'Amethyst', 'Emerald', 'Champagne', 'Silver', 'Void'];
  const MATERIALS = ['obsidian', 'optical_glass', 'iridescent_pearl', 'brushed_titanium', 'velvet_matte', 'bioluminescent_gel'];
  const TEMPLATES = {
    scratch: {label: 'Desde cero', role: 'Asistente especializado', form: 0, palette: 0, mention: '', instructions: ''},
    dev: {label: 'Plantilla: Dev (Programador)', role: 'Ingeniero de software', form: 17, palette: 2, mention: 'Dev',
      instructions: 'Analiza el código, trabaja en worktrees aislados, ejecuta pruebas y conserva contratos públicos.'},
    visual: {label: 'Plantilla: Visual (Diseño y 3D)', role: 'Especialista visual y 3D', form: 20, palette: 1, mention: 'Visual',
      instructions: 'Inspecciona interfaces, SceneDocument v2 y acabados 3D sin romper el diseño aprobado.'},
    qa: {label: 'Plantilla: QA (Revisor)', role: 'Revisor independiente QA', form: 0, palette: 5, mention: 'QA',
      instructions: 'Verifica diffs, resultados de pruebas y regresiones. Emite VEREDICTO: APROBADO o VEREDICTO: CAMBIOS.'},
    research: {label: 'Plantilla: Research (Investigación)', role: 'Analista e investigador', form: 10, palette: 4, mention: 'Research',
      instructions: 'Comprueba fuentes, dependencias y documentación antes de concluir.'},
  };
  const PERSONALITY = {
    formality: ['Formalidad', {casual: 'Cercana', neutral: 'Neutral', formal: 'Formal'}],
    concision: ['Concisión', {brief: 'Breve', balanced: 'Equilibrada', detailed: 'Detallada'}],
    creativity: ['Creatividad', {low: 'Baja', medium: 'Media', high: 'Alta'}],
    proactivity: ['Proactividad', {low: 'Baja', medium: 'Media', high: 'Alta'}],
    research_tendency: ['Investigación', {low: 'Baja', medium: 'Media', high: 'Alta'}],
    technical_depth: ['Profundidad técnica', {low: 'Baja', medium: 'Media', high: 'Alta'}],
    examples: ['Ejemplos', {none: 'Ninguno', some: 'Algunos', many: 'Muchos'}],
    explanation_level: ['Nivel de explicación', {expert: 'Experto', intermediate: 'Intermedio', beginner: 'Principiante'}],
    review_style: ['Estilo de revisión', {lenient: 'Flexible', balanced: 'Equilibrado', strict: 'Estricto'}],
    question_policy: ['Preguntas', {ask_when_blocked: 'Solo si se bloquea', ask_first: 'Confirmar antes', avoid: 'Evitar, declarar supuestos'}],
    response_format: ['Formato', {prose: 'Prosa', bullets: 'Viñetas', structured: 'Secciones'}],
  };
  const TABS = [['identity', 'Identidad'], ['appearance', 'Apariencia'], ['intelligence', 'Inteligencia'], ['personality', 'Personalidad'],
    ['voice', 'Voz'], ['memory', 'Memoria'], ['tools', 'Herramientas'], ['computer', 'Computadora'], ['autonomy', 'Autonomía'],
    ['collaboration', 'Colaboración'], ['resources', 'Recursos']];
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  const options = (pairs, value) => pairs.map(([v, label]) => { const o = new Option(label, v); o.selected = String(v) === String(value ?? ''); return o; });
  let fieldSeq = 0;  // label[for] keeps the accessible name to the label text, not the options
  const field = (label, control) => { control.id ||= 'axx-act-field-' + (++fieldSeq);
    return el('div', {className: 'setting'}, el('label', {htmlFor: control.id, textContent: label}), control); };
  const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
  const set = (obj, path, value) => { const keys = path.split('.'), last = keys.pop(); const t = keys.reduce((o, k) => (o[k] ??= {}), obj);
    if (value === '' || value === undefined) delete t[last]; else t[last] = value; };

  const state = {
    acts: [], teams: [], routines: [], providers: [], voices: [], governor: null,
    actStates: {}, events: [], pendingApprovals: [], lastRun: {},
    draft: null, base: '', grants: [], toolGrant: false, tab: 'identity', subview: 'library',
  };
  const host = el('section', {className: 'axx-acts-studio', hidden: true});
  const status = el('p', {className: 'axx-acts-status', role: 'status', ariaLive: 'polite'});
  const govStatus = el('small', {className: 'axx-acts-gov-status'});
  const library = el('div', {className: 'axx-acts-library', role: 'list', ariaLabel: 'Biblioteca de Acts'});
  const teamsBox = el('section', {className: 'axx-acts-subbox', hidden: true});
  const routinesBox = el('section', {className: 'axx-acts-subbox', hidden: true});
  const editor = el('form', {className: 'axx-acts-editor', hidden: true, noValidate: false});
  const preview = el('pre', {className: 'axx-acts-preview', tabIndex: 0, hidden: true});
  const importInput = el('input', {type: 'file', accept: 'application/json', hidden: true});
  const entry = el('button', {type: 'button', className: 'axx-code-entry', textContent: 'Abrir Acts'});
  const flagButton = el('button', {type: 'button', hidden: true});
  const subTabsRow = el('div', {className: 'axx-acts-segments', role: 'tablist', ariaLabel: 'Secciones de Acts'},
    ...[['library', 'Biblioteca de Acts'], ['teams', 'Equipos (Teams)'], ['routines', 'Rutinas']].map(([id, label]) => {
      const b = el('button', {type: 'button', role: 'tab', textContent: label, onclick: () => { state.subview = id; renderSubview(); }});
      b.dataset.sub = id; return b; }));
  const createButton = el('button', {type: 'button', textContent: 'Crear Act', className: 'primary', onclick: () => edit(null)});
  const importButton = el('button', {type: 'button', textContent: 'Importar perfil', onclick: () => importInput.click()});
  const quickRow = el('div', {className: 'quick-row'}, createButton, importButton, flagButton);
  host.append(
    el('header', {className: 'axx-acts-head'},
      el('div', {}, el('h3', {textContent: 'Acts Studio'}),
        el('p', {className: 'axx-acts-sub', textContent: 'Agentes persistentes: cada Act tiene su modelo, personalidad, forma, voz, memoria y permisos propios.'})),
      govStatus),
    status, el('div', {className: 'axx-acts-toolbar'}, quickRow, subTabsRow), library, teamsBox, routinesBox, editor, preview, importInput);
  document.getElementById('view-agent').append(entry, host);
  document.head.append(el('link', {rel: 'stylesheet', href: 'scripts/agents/acts-studio.css'}));
  const seenCards = new Set();
  // Re-trigger a short highlight so each new status is noticed.
  const say = text => { status.textContent = text; status.classList.remove('axx-acts-flash'); void status.offsetWidth; status.classList.add('axx-acts-flash'); };
  const attempt = task => async (...args) => { try { await task(...args); } catch (e) { say(e?.message || String(e)); } };
  const dirty = () => !!state.draft && JSON.stringify(state.draft) !== state.base;

  function renderSubview() {
    library.hidden = state.subview !== 'library';
    teamsBox.hidden = state.subview !== 'teams';
    routinesBox.hidden = state.subview !== 'routines';
    for (const b of subTabsRow.children) b.setAttribute('aria-selected', String(b.dataset.sub === state.subview));
    if (state.subview === 'teams') renderTeams();
    if (state.subview === 'routines') renderRoutines();
  }

  // The panel title names the open studio; other views (phase7 settings) rewrite it, so re-assert on every change.
  const panelTitle = document.getElementById('panel-title');
  const syncTitle = () => {
    if (!panelTitle) return;
    const view = document.querySelector('#view-agent:not([hidden])');
    const want = !view ? null : !host.hidden ? 'Acts' : view.querySelector('.axx-code-studio:not([hidden])') ? 'Code Studio' : null;
    if (!view) return;  // another view owns the title
    if (want && panelTitle.textContent !== want) panelTitle.textContent = want;
    else if (!want && ['Acts', 'Code Studio'].includes(panelTitle.textContent)) panelTitle.textContent = 'Personalizar AXX';
  };
  Axx.syncStudioTitle = syncTitle;
  if (panelTitle) new MutationObserver(syncTitle).observe(panelTitle, {childList: true, characterData: true, subtree: true});
  new MutationObserver(syncTitle).observe(document.getElementById('view-agent'), {attributes: true, attributeFilter: ['hidden']});

  async function toggleStudio(forceOpen) {
    const targetOpen = forceOpen !== undefined ? forceOpen : host.hidden;
    if (!targetOpen && !host.hidden && dirty() && !confirm('Hay cambios sin guardar en el Act. ¿Cerrar y descartarlos?')) return;
    if (targetOpen) Axx.codeStudio?.close?.();  // one studio at a time in the agent view
    host.hidden = !targetOpen; entry.textContent = host.hidden ? 'Abrir Acts' : 'Cerrar Acts';
    host.parentElement.classList.toggle('axx-acts-active', !host.hidden); syncTitle();
    if (host.hidden) { editor.hidden = true; state.draft = null; } else await load();
    Axx.resident?.schedule?.();
  }
  entry.onclick = attempt(() => toggleStudio());
  // Axx closes the panel on Escape (document capture). With unsaved Act edits, Escape only leaves the field.
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || host.hidden || editor.hidden || !dirty() || !host.contains(document.activeElement)) return;
    e.preventDefault(); e.stopImmediatePropagation(); document.activeElement.blur();
    say('Cambios sin guardar: pulsa «Aplicar y verificar» o «Descartar».');
  }, true);
  window.addEventListener('beforeunload', e => { if (dirty()) { e.preventDefault(); e.returnValue = ''; } });

  // Radial / companion menu hook (no permanent rectangular toolbar added)
  const menu = document.querySelector('.chat20-menu-body');
  if (menu) {
    const actsMenuBtn = el('button', {type: 'button', textContent: 'Acts Studio (Agentes)'});
    actsMenuBtn.onclick = () => { c.openFeature('agent'); void toggleStudio(true); };
    menu.append(actsMenuBtn);
  }
  const origOpenFeature = c.openFeature?.bind(c);
  if (origOpenFeature) {
    c.openFeature = function (id) {
      if (id === 'acts') {
        const res = origOpenFeature('agent');
        void toggleStudio(true).then(() => host.scrollIntoView({block: 'start', behavior: 'smooth'}));
        return res;
      }
      return origOpenFeature(id);
    };
  }

  async function load() {
    const [profiles, providers, flags, teams, routines, voicesData, gov] = await Promise.all([
      api('GET', 'profiles?include_disabled=true'),
      Axx.backendRequest('GET', '/axx-api/providers').catch(() => ({providers: []})),
      api('GET', 'flags').catch(() => ({flags: []})),
      api('GET', 'teams?include_disabled=true').catch(() => ({teams: []})),
      api('GET', 'routines').catch(() => ({routines: []})),
      Axx.backendRequest('GET', '/axx-api/speech/voices').catch(() => ({voices: []})),
      api('GET', 'governor/status').catch(() => null),
    ]);
    state.acts = profiles.profiles || [];
    state.teams = teams.teams || [];
    state.routines = routines.routines || [];
    state.voices = (voicesData.voices || []).filter(v => v.enabled !== false && v.name);
    state.governor = gov;
    if (gov?.telemetry) {
      const t = gov.telemetry;
      govStatus.textContent = `Recursos (${gov.profile}): CPU ${Math.round(t.cpu_percent || 0)}% · RAM ${Math.round(t.ram_percent || 0)}% · FPS ${Math.round(t.avatar_fps || 60)}`;
    }
    // New capabilities start off; only the owner's explicit click enables them.
    const flag = (flags.flags || []).find(f => f.flag_id === 'agent_profiles_v1');
    flagButton.hidden = !flag;
    state.actsOff = !!flag && !flag.enabled;
    flagButton.classList.toggle('primary', state.actsOff);
    createButton.classList.toggle('primary', !state.actsOff);
    for (const b of [createButton, importButton]) { b.disabled = state.actsOff; b.title = state.actsOff ? 'Activa Acts primero' : ''; }
    if (flag) {
      flagButton.textContent = flag.enabled ? 'Desactivar Acts' : 'Activar Acts';
      // Busy until the reload finishes: a second click on a slow reload used to toggle the flag straight back.
      flagButton.onclick = attempt(async () => {
        if (flagButton.getAttribute('aria-busy') === 'true') return;
        const label = flagButton.textContent;
        flagButton.setAttribute('aria-busy', 'true'); flagButton.disabled = true;
        flagButton.textContent = flag.enabled ? 'Desactivando…' : 'Activando…';
        try {
          await api('POST', 'flags/set', {flag_id: flag.flag_id, enabled: !flag.enabled, expected_revision: flag.revision, reason: 'owner_acts_studio'});
          await load(); say(flag.enabled ? 'Acts desactivados: el chat vuelve a responder solo como AXX.' : 'Acts activados. Crea tu primer Act.');
        } finally {
          flagButton.removeAttribute('aria-busy'); flagButton.disabled = false;
          if (flagButton.textContent.endsWith('…')) flagButton.textContent = label;  // failed: load() never relabelled it
        }
      });
      if (!flag.enabled) say('Acts está desactivado. Actívalo para crear Acts y conversar con ellos.');
    }
    state.providers = (providers.providers || []).filter(p => p.enabled && !p.candidate_only);
    await syncConversationBinding().catch(() => {});
    renderLibrary();
    renderSubview();
    syncChatSelect();
    await refreshActivity().catch(() => {});
  }

  function modelLabel(act) {
    const i = act.intelligence || {};
    if (i.route === 'policy') return 'Automático gratis';
    return i.provider_profile_ref ? (i.provider_profile_ref === CONNECT ? 'ChatGPT · ' : i.provider_profile_ref + ' · ') + (i.model_id || 'sin modelo') : 'Sin modelo';
  }

  const STATE_LABEL = {idle: 'En espera', planning: 'Planificando', working: 'Trabajando', awaiting_approval: 'Espera aprobación',
    paused: 'En pausa', blocked: 'Bloqueado', completed: 'Completado', failed: 'Error', disabled: 'Deshabilitado'};
  const AUTONOMY_LABEL = {manual: 'Manual', assisted: 'Asistido', auto_safe: 'Auto seguro', background: 'Segundo plano', scheduled: 'Programado', isolated: 'Aislado'};
  function actLiveStatus(act) {
    if (!act.enabled) return 'disabled';
    return state.actStates[act.agent_id] || ((state.governor?.active_by_act?.[act.agent_id] > 0) ? 'working' : 'idle');
  }

  // ---- Technical sheet: everything AXX enforces for this Act, read from the stored profile and live grants ----
  const TOOL_LABEL = {[TOOL]: 'Comandos AXX', [CODE]: 'Code Studio', [SPATIAL]: 'Escena 3D', [COMP]: 'Computadora'};
  const MEMORY_LABEL = {conversation: 'Solo esta conversación', agent: 'Privada del Act', project: 'Proyecto', explicit_shared: 'Compartida explícitamente'};
  const fmtMs = ms => ms < 1000 ? Math.round(ms) + ' ms' : (ms / 1000).toFixed(ms < 10000 ? 1 : 0).replace('.', ',') + ' s';
  function specSheet(act) {
    const body = el('div', {className: 'axx-acts-spec-body'});
    const box = el('details', {className: 'axx-acts-spec'}, el('summary', {textContent: 'Ficha técnica'}), body);
    box.addEventListener('toggle', () => { if (box.open) void fillSpec(act, body).catch(e => body.replaceChildren(el('p', {textContent: e.message}))); });
    return box;
  }
  async function fillSpec(act, body) {
    const row = (k, ...v) => [el('dt', {textContent: k}), el('dd', {}, ...v)];
    const code = t => el('code', {textContent: String(t)});
    const i = act.intelligence || {}, a = act.appearance || {}, lim = act.limits || {}, run = state.lastRun[act.agent_id];
    const pal = Axx.PALETTES?.[a.palette_id];
    const finish = Axx.actAvatar?.FINISH?.[a.material_preset] || a.material_preset;
    const section = (title, ...rows) => el('section', {}, el('h6', {textContent: title}), el('dl', {}, ...rows.flat()));
    body.replaceChildren(el('p', {className: 'axx-acts-spec-loading', textContent: 'Leyendo permisos…'}));
    const grants = (await api('GET', 'profiles/permissions?agent_id=' + encodeURIComponent(act.agent_id))).permissions || [];
    const active = state.governor?.active_by_act?.[act.agent_id] || 0;
    body.replaceChildren(
      section('Inteligencia',
        row('Proveedor', code(i.provider_profile_ref === CONNECT ? 'axx-connect (ChatGPT)' : i.provider_profile_ref || '—')),
        row('Modelo', code(i.model_id || '—'), ' · ruta ', code(i.route || 'manual'), ' · alternativa ', code(i.fallback || 'none')),
        row('Salida máxima', i.max_tokens_per_turn ? code(i.max_tokens_per_turn + ' tokens/turno') : 'la del proveedor'),
        row('Último turno', run ? el('span', {textContent: (run.ok ? 'completado' : 'falló') + ' en ' + fmtMs(run.ms) + ' · ' + new Date(run.at).toLocaleTimeString()
          + ' · ' + (run.verified ? 'modelo verificado por AXX: ' : 'modelo sin verificar: ') + (run.model || '—')}) : 'sin turnos en esta sesión')),
      section('Permisos (concedidos por ti)',
        ...(grants.length ? grants.map(g => row(TOOL_LABEL[g.tool_id] || g.tool_id,
          code((g.operation_kinds || []).join(', ') || 'sin operaciones'), ' · alcance ', code(g.resource_pattern || '*'),
          ' · ', g.approval_mode === 'deny' ? 'denegado' : 'aprobación ' + (g.approval_mode || '—'),
          g.expires_at_ms ? ' · vence ' + new Date(g.expires_at_ms).toLocaleDateString() : ''))
          : [row('Ninguno', 'conversa y propone; no ejecuta herramientas')])),
      section('Trabajo',
        row('Autonomía', AUTONOMY_LABEL[act.autonomy?.mode] || 'Manual'),
        row('Memoria', MEMORY_LABEL[act.memory_scope] || act.memory_scope || '—'),
        row('Límites', code((lim.max_concurrent_jobs ?? 1) + ' trabajo(s) a la vez'), ' · ', code((lim.max_retries ?? 0) + ' reintento(s)'), ' · ahora activos: ', code(active)),
        row('Colaboración', act.collaboration?.mention ? code('@' + act.collaboration.mention) : '—',
          act.collaboration?.review_required ? ' · exige revisión de otro Act antes de integrar' : ''),
        row('Entorno', code(act.workspace?.runtime || 'none'), ' · primer plano ', code(act.workspace?.foreground_policy || 'deny'))),
      section('Apariencia (renderizador de AXX)',
        row('Forma', code('#' + a.form_id), ' ', (Axx.FORMS?.[a.form_id]?.name || a.form_name || ''), ' — ', Axx.FORMS?.[a.form_id]?.detail || ''),
        row('Paleta', (pal?.name || a.palette_name || ''), ' ', ...(pal?.colors || []).map(c => el('span', {className: 'axx-acts-hex', style: '--hex:' + c, textContent: c}))),
        row('Material', code(a.material_preset || 'obsidian'), ' → acabado ', code(finish)),
        row('Ajustes', code(JSON.stringify({scale: a.scale ?? 1, energy: a.animation_intensity ?? 1, ...(a.studio || {})}))),
        row('Reacciones', Object.keys(a.reactions || {}).length ? code(Object.entries(a.reactions).map(([k, v]) => k + '→' + v).join(' · ')) : 'sin gestos')),
      section('Identificación',
        row('ID', code(act.agent_id)), row('Revisión', code(act.revision), ' (cada cambio se guarda con comprobación de revisión)')));
  }

  function renderLibrary() {
    library.replaceChildren(...state.acts.map(act => {
      const img = lookImg(act.appearance, 64, {svg: act.thumbnail?.svg, alt: act.name + ': ' + (FORMS[act.appearance.form_id] || '') + ' ' + (PALETTES[act.appearance.palette_id] || ''),
        title: 'Forma de AXX dibujada por su renderizador'});
      const live = actLiveStatus(act);
      const badge = el('span', {className: 'axx-acts-badge axx-acts-state', textContent: STATE_LABEL[live] || live});
      badge.dataset.state = live;
      const permBtn = el('button', {type: 'button', textContent: 'Permisos / Historial', onclick: attempt(async () => {
        const [perms, arts] = await Promise.all([
          api('GET', 'profiles/permissions?agent_id=' + encodeURIComponent(act.agent_id)),
          api('GET', 'artifacts?act_id=' + encodeURIComponent(act.agent_id)).catch(() => ({artifacts: []})),
        ]);
        preview.hidden = false;
        const when = ms => ms ? new Date(ms).toLocaleString() : 'sin caducidad';
        preview.textContent = `Permisos de ${act.name} · ${act.agent_id}\n`
          + (perms.permissions.length ? perms.permissions.map(g => `• ${g.tool_id} — ${(g.operation_kinds || []).join(', ') || 'sin operaciones'}`
            + `\n    alcance ${g.resource_pattern} · aprobación ${g.approval_mode} · ${when(g.expires_at_ms)} · concedido por ${g.granted_by}`).join('\n')
            : '• Sin permisos concedidos: conversa y propone, pero no ejecuta herramientas.')
          + `\n\nArtefactos verificados (${arts.artifacts.length})\n`
          + (arts.artifacts.length ? arts.artifacts.slice(0, 12).map(a => `• ${a.artifact_type || a.type || 'artefacto'} · ${a.path_or_ref || ''}`
            + `\n    sha256 ${String(a.sha256 || '').slice(0, 16)}… · ${a.verification_status || ''} · run ${a.run_id || ''}`).join('\n')
            : '• Todavía no hay artefactos.');
        preview.scrollIntoView({block: 'nearest', behavior: 'smooth'});
      })});
      const actions = el('div', {className: 'quick-row'},
        el('button', {type: 'button', className: 'primary', textContent: 'Usar en el chat', disabled: !act.enabled, onclick: attempt(async () => {
          await chooseForChat(act.agent_id); say(act.name + ' responderá en este chat (conversación conservada).');
          c.openFeature?.('chat'); document.getElementById('chat-input')?.focus();
        })}),
        el('button', {type: 'button', textContent: 'Usar la computadora', disabled: !act.enabled,
          title: 'El Act opera la ventana autorizada en «Controlar PC», un gesto verificado a la vez', onclick: attempt(async () => {
            const task = prompt('¿Qué debe hacer ' + act.name + ' en la ventana autorizada de este chat?');
            if (!task?.trim()) return;
            c.openFeature?.('chat');
            const result = await computerTask(act, task.trim());
            c.message?.('assistant', computerReport(act, result), 'local'); c.renderChat?.(); c.save?.();
          })}),
        el('button', {type: 'button', textContent: 'Personalizar', onclick: attempt(() => edit(act))}),
        el('button', {type: 'button', textContent: 'Duplicar', onclick: attempt(() => edit(act, true))}),
        el('button', {type: 'button', textContent: act.enabled ? 'Deshabilitar' : 'Habilitar', onclick: attempt(() => toggle(act))}),
        el('button', {type: 'button', textContent: 'Exportar', onclick: attempt(() => exportAct(act))}),
        permBtn);
      const chip = (text, title) => el('span', {className: 'axx-acts-chip', textContent: text, title: title || text});
      const card = el('article', {className: 'axx-acts-card', role: 'listitem', ariaLabel: act.name},
        el('div', {className: 'axx-acts-thumb'}, img),
        el('div', {className: 'axx-acts-meta'},
          el('div', {className: 'axx-acts-title'}, el('strong', {textContent: act.name}), badge),
          el('span', {className: 'axx-acts-role', textContent: act.role + (act.collaboration?.mention ? ' · @' + act.collaboration.mention : '')}),
          el('div', {className: 'axx-acts-chips'},
            chip(modelLabel(act), 'Proveedor · modelo que usa este Act (verificado en cada turno)'),
            chip(FORMS[act.appearance.form_id] + ' / ' + PALETTES[act.appearance.palette_id], 'Forma y paleta'),
            chip('Autonomía: ' + (AUTONOMY_LABEL[act.autonomy?.mode] || 'Manual'), 'Modo de autonomía'),
            chip('rev. ' + act.revision, 'Revisión del perfil (CAS)'))),
        actions, specSheet(act));
      card.dataset.state = live; card.dataset.agentId = act.agent_id;
      if (!seenCards.has(act.agent_id)) {  // staggered entrance only the first time a card appears, not on every reload
        seenCards.add(act.agent_id); card.classList.add('axx-acts-enter'); card.style.setProperty('--i', String(state.acts.indexOf(act)));
      }
      return card;
    }));
    if (!state.acts.length) {
      const step = (n, title, text) => el('li', {}, el('span', {className: 'axx-acts-step-n', textContent: n, ariaHidden: 'true'}),
        el('div', {}, el('strong', {textContent: title}), el('span', {textContent: text})));
      library.append(el('div', {className: 'axx-acts-intro', role: 'note'},
        el('p', {textContent: state.actsOff
          ? 'Así empiezas con Acts:'
          : 'Todavía no hay Acts. Crea uno para asignarle un modelo y trabajar con él desde el chat.'}),
        el('ol', {className: 'axx-acts-steps'},
          step('1', 'Activar', 'Acts empieza desactivado; solo tú lo enciendes. Nada recibe permisos al activarlo.'),
          step('2', 'Crear y personalizar', 'Nombre, rol, forma y paleta, modelo (Ollama o ChatGPT), voz, memoria y autonomía.'),
          step('3', 'Trabajar', 'Elígelo en el chat o escribe @mención; en Code Studio delega archivos y forma equipos Dev → QA.'),
          step('4', 'Conceder herramientas', 'Cada herramienta (código, comandos, escena, computadora) se concede aparte y se puede revocar.'))));
    }
  }

  // ---- Equipos: node editor over the real team graph ----
  // A node is an Act of the team; a connection salida ● → ● entrada is a handoff: the target runs after the source and
  // receives its verified output. Saved as team.graph; teams/run executes it in topological order and each Act reads only
  // what is connected upstream. During a run, node and connection states come only from that run's EventHub events.
  const withData = (node, data) => (Object.assign(node.dataset, data), node);
  const ROLE_LABEL = {lead: 'Coordinador', member: 'Miembro', reviewer: 'Revisor'};
  const ROLE_NEXT = {lead: 'member', member: 'reviewer', reviewer: 'lead'};
  const NODE_W = 220, NODE_H = 104, GAP_X = 270, GAP_Y = 128;
  const flow = {draft: null, base: '', sel: null, run: null, els: null};
  const flowDirty = () => !!flow.draft && JSON.stringify(flow.draft) !== flow.base;
  const actOf = id => state.acts.find(a => a.agent_id === id);
  const nodeOf = id => flow.draft?.nodes.find(n => n.agent_id === id);
  const guessRole = a => /qa|revis|review/i.test(a.name + ' ' + a.role) ? 'reviewer' : 'member';

  function draftFromTeam(t) {
    const roles = Object.fromEntries((t.members || []).map(m => [m.agent_id, m.role]));
    let nodes, edges;
    if (t.graph?.nodes?.length) {
      nodes = t.graph.nodes.map(n => ({...n, instruction: n.instruction || '', role: roles[n.agent_id] || 'member'}));
      edges = t.graph.edges.map(e => ({from: e.from, to: e.to, label: e.label || '', transfer: e.transfer || 'full'}));
    } else {  // a team saved before graphs runs as lead -> members -> reviewer; draw exactly that chain
      const rank = r => (r === 'lead' ? 0 : r === 'reviewer' ? 2 : 1);
      const ordered = [...(t.members || [])].sort((a, b) => rank(a.role) - rank(b.role));
      nodes = ordered.map((m, i) => ({agent_id: m.agent_id, role: m.role, x: 40 + i * GAP_X, y: 60, instruction: ''}));
      edges = ordered.slice(1).map((m, i) => ({from: ordered[i].agent_id, to: m.agent_id, label: '', transfer: 'full'}));
    }
    return {team_id: t.team_id, revision: t.revision, title: t.title, purpose: t.purpose || '', budget_usd: t.budget_usd ?? 5,
      review_criteria: t.review_criteria || '', delegation_rules: t.delegation_rules || '',
      shared_memory_policy: t.shared_memory_policy || 'explicit_shared', nodes, edges, legacy: !t.graph};
  }
  function openDraft(d) {
    flow.draft = d; flow.base = d.legacy ? '' : JSON.stringify(d); flow.sel = null; flow.run = null;
    renderTeams();
  }
  // Same rule as the backend (_team_flow): topological, the leftmost (then highest) released node first.
  function execOrder(d) {
    const order = [], preds = id => d.edges.filter(e => e.to === id).map(e => e.from);
    while (order.length < d.nodes.length) {
      const ready = d.nodes.filter(n => !order.includes(n.agent_id) && preds(n.agent_id).every(p => order.includes(p)));
      if (!ready.length) return order;  // only possible for an invalid draft; the backend rejects cycles
      ready.sort((a, b) => a.x - b.x || a.y - b.y || (a.agent_id < b.agent_id ? -1 : 1));
      order.push(ready[0].agent_id);
    }
    return order;
  }
  const reaches = (d, from, to) => {
    const seen = new Set(), stack = [from];
    while (stack.length) { const id = stack.pop(); if (id === to) return true;
      if (!seen.has(id)) { seen.add(id); stack.push(...d.edges.filter(e => e.from === id).map(e => e.to)); } }
    return false;
  };
  function connectProblem(d, from, to) {
    if (from === to) return 'Un Act no puede conectarse consigo mismo.';
    if (d.edges.some(e => e.from === from && e.to === to)) return 'Esa conexión ya existe.';
    if (reaches(d, to, from)) return 'Esa conexión cerraría un ciclo: el flujo debe avanzar siempre hacia delante.';
    return '';
  }
  function connect(from, to) {
    const problem = connectProblem(flow.draft, from, to);
    if (problem) return say(problem);
    flow.draft.edges.push({from, to}); flow.sel = {edge: from + '>' + to};
    say(`Conectado: ${actOf(from)?.name || from} entrega su resultado a ${actOf(to)?.name || to}.`);
    renderFlow();
  }
  function autoLayout(d) {
    const depth = {};
    for (const id of execOrder(d)) depth[id] = Math.max(0, ...d.edges.filter(e => e.to === id).map(e => (depth[e.from] ?? 0) + 1));
    const rows = {};
    for (const n of [...d.nodes].sort((a, b) => a.y - b.y)) {
      const col = depth[n.agent_id] ?? 0; rows[col] = (rows[col] ?? -1) + 1;
      n.x = 40 + col * GAP_X; n.y = 30 + rows[col] * GAP_Y;
    }
  }
  const byX = d => [...d.nodes].sort((a, b) => a.x - b.x || a.y - b.y);
  const PATTERNS = {
    chain: ['Cadena', 'Cada Act recibe el resultado del anterior (de izquierda a derecha).', d => {
      const n = byX(d); d.edges = n.slice(1).map((m, i) => ({from: n[i].agent_id, to: m.agent_id})); }],
    fan: ['Abanico y revisión', 'El primero reparte, los del medio trabajan en ramas separadas y el último junta todo.', d => {
      const n = byX(d); if (n.length < 3) throw new Error('El abanico necesita al menos 3 Acts en el lienzo.');
      const [first, last, mid] = [n[0], n.at(-1), n.slice(1, -1)];
      d.edges = [...mid.map(m => ({from: first.agent_id, to: m.agent_id})), ...mid.map(m => ({from: m.agent_id, to: last.agent_id}))];
      first.x = 40; last.x = 40 + 2 * GAP_X; mid.forEach((m, i) => { m.x = 40 + GAP_X; m.y = 20 + i * GAP_Y; });
      first.y = last.y = 20 + (mid.length - 1) * GAP_Y / 2; }],
    clear: ['Sin conexiones', 'Todos trabajan por separado sobre el mismo objetivo; nadie lee a otro.', d => { d.edges = []; }],
  };
  const edgePath = (a, b) => {
    const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, k = Math.max(50, Math.abs(x2 - x1) / 2);
    return `M${x1},${y1} C${x1 + k},${y1} ${x2 - k},${y2} ${x2},${y2}`;
  };
  const svgEl = (tag, attrs = {}) => { const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };

  function renderTeams() {
    teamsBox.replaceChildren();
    const help = el('details', {className: 'axx-flow-help', open: !state.teams.length},
      el('summary', {textContent: 'Cómo funcionan los equipos'}),
      el('ol', {className: 'axx-acts-steps'},
        ...[['Añade Acts al lienzo', 'Cada nodo es un Act con su propio modelo, permisos y estilo.'],
          ['Conecta salida ● → ● entrada', 'Arrastra desde el punto derecho de un Act hasta otro. El segundo trabaja después y recibe el resultado verificado del primero.'],
          ['Asigna la parte de cada uno', 'Cada nodo puede tener su propia tarea; el objetivo general se da al ejecutar.'],
          ['Ejecuta y observa', 'El flujo corre en orden (los números de cada nodo). Cada Act solo lee lo que tiene conectado antes; las ramas no se mezclan.']]
          .map(([t, d], i) => el('li', {}, el('span', {className: 'axx-acts-step-n', textContent: String(i + 1)}),
            el('div', {}, el('strong', {textContent: t}), el('span', {textContent: d}))))));
    const list = el('nav', {className: 'axx-flow-teams', ariaLabel: 'Equipos guardados'},
      el('button', {type: 'button', className: 'primary', textContent: '+ Nuevo equipo', onclick: () => {
        if (flowDirty() && !confirm('Hay cambios sin guardar en el equipo abierto. ¿Descartarlos?')) return;
        openDraft({team_id: null, revision: 0, title: '', purpose: '', budget_usd: 5, review_criteria: '', nodes: [], edges: []});
      }}));
    for (const t of state.teams) {
      const active = flow.draft?.team_id === t.team_id;
      const faces = el('span', {className: 'axx-flow-faces'}, ...(t.members || []).slice(0, 5).map(m => {
        const a = actOf(m.agent_id); return a ? lookImg(a.appearance, 22, {title: a.name}) : el('span', {textContent: '?'}); }));
      const links = t.graph ? t.graph.edges.length : Math.max(0, (t.members || []).length - 1);
      const b = el('button', {type: 'button', className: 'axx-flow-team', onclick: () => {
        if (flowDirty() && !confirm('Hay cambios sin guardar en el equipo abierto. ¿Descartarlos?')) return;
        openDraft(draftFromTeam(t));
      }}, el('strong', {textContent: t.title || t.team_id}), faces,
        el('small', {textContent: `${(t.members || []).length} Acts · ${links} conexiones${t.graph ? '' : ' · cadena clásica'}`}));
      b.setAttribute('aria-current', String(active));
      list.append(b);
    }
    const main = el('div', {className: 'axx-flow-main'});
    teamsBox.append(help, el('div', {className: 'axx-flow-shell'}, list, main));
    flow.els = {main};
    if (!state.acts.some(a => a.enabled)) {
      main.append(el('div', {className: 'axx-flow-empty'}, el('strong', {textContent: 'Primero crea al menos un Act'}),
        el('span', {textContent: 'Los equipos conectan Acts existentes. Crea uno en la Biblioteca y vuelve aquí.'})));
      return;
    }
    if (!flow.draft) {
      main.append(el('div', {className: 'axx-flow-empty'}, el('strong', {textContent: state.teams.length ? 'Elige un equipo o crea uno nuevo' : 'Crea tu primer equipo'}),
        el('span', {textContent: 'Un equipo es un flujo de Acts conectados: por ejemplo Plan → (Front, Back) → QA.'})));
      return;
    }
    renderFlow();
  }

  function renderFlow() {
    const d = flow.draft, main = flow.els?.main;
    if (!d || !main) return;
    main.replaceChildren();
    const order = execOrder(d), step = Object.fromEntries(order.map((id, i) => [id, i + 1]));
    // header: identity and persistence
    const titleIn = el('input', {value: d.title, placeholder: 'Nombre del equipo', ariaLabel: 'Nombre del equipo', required: true,
      oninput: () => { d.title = titleIn.value; markFlow(); }});
    const purposeIn = el('input', {value: d.purpose, placeholder: 'Para qué sirve (opcional)', ariaLabel: 'Propósito',
      oninput: () => { d.purpose = purposeIn.value; markFlow(); }});
    const budgetIn = el('input', {type: 'number', min: '0.1', step: '0.5', value: String(d.budget_usd), ariaLabel: 'Presupuesto máximo (USD)',
      title: 'Presupuesto máximo por ejecución (USD)', oninput: () => { d.budget_usd = Number(budgetIn.value || 5); markFlow(); }});
    const saveBtn = el('button', {type: 'button', textContent: d.team_id ? 'Guardar cambios' : 'Crear equipo', onclick: attempt(() => saveFlow())});
    saveBtn.dataset.flow = 'save';
    const delBtn = el('button', {type: 'button', textContent: 'Eliminar', hidden: !d.team_id, onclick: attempt(async () => {
      if (!confirm(`¿Eliminar el equipo «${d.title}»? Sus ejecuciones pasadas se conservan en Actividad.`)) return;
      await api('POST', 'teams/delete', {team_id: d.team_id}); flow.draft = null; say('Equipo eliminado.'); await load();
    })});
    const head = el('div', {className: 'axx-flow-head'}, titleIn, purposeIn,
      el('label', {className: 'axx-flow-budget'}, '$', budgetIn), saveBtn, delBtn);
    // tools: palette of Acts and connection patterns
    const inTeam = new Set(d.nodes.map(n => n.agent_id));
    const palette = el('div', {className: 'axx-flow-palette', ariaLabel: 'Acts disponibles'},
      el('small', {textContent: 'Añadir:'}),
      ...state.acts.filter(a => a.enabled && !inTeam.has(a.agent_id)).map(a => el('button', {type: 'button', className: 'axx-flow-chip',
        title: `${a.name} · ${a.role}`, onclick: () => addNode(a)}, lookImg(a.appearance, 20), ' ' + a.name)));
    if (palette.children.length === 1) palette.append(el('small', {textContent: 'todos tus Acts habilitados ya están en el lienzo'}));
    const tools = el('div', {className: 'axx-flow-tools'},
      ...Object.entries(PATTERNS).map(([k, [label, tip, fn]]) => el('button', {type: 'button', textContent: label, title: tip,
        disabled: d.nodes.length < 2, onclick: attempt(() => { fn(d); flow.sel = null; say(tip); renderFlow(); })})),
      el('button', {type: 'button', textContent: 'Ordenar', title: 'Coloca cada Act en columnas según el orden de ejecución',
        disabled: !d.nodes.length, onclick: () => { autoLayout(d); renderFlow(); }}));
    // canvas
    const w = Math.max(760, ...d.nodes.map(n => n.x + NODE_W + 60)), h = Math.max(300, ...d.nodes.map(n => n.y + NODE_H + 40));
    const plane = el('div', {className: 'axx-flow-plane'});
    plane.style.width = w + 'px'; plane.style.height = h + 'px';
    const svg = svgEl('svg', {class: 'axx-flow-edges', width: w, height: h, 'aria-hidden': 'true'});
    const defs = svgEl('defs'), marker = svgEl('marker', {id: 'axx-flow-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '7', markerHeight: '7', orient: 'auto-start-reverse'});
    marker.append(svgEl('path', {d: 'M0,0 L10,5 L0,10 z', fill: 'currentColor'})); defs.append(marker); svg.append(defs);
    const canvas = el('div', {className: 'axx-flow-canvas', tabIndex: 0, ariaLabel: 'Lienzo del equipo. Supr borra la selección.'}, plane);
    canvas.style.height = Math.max(240, Math.min(h + 24, 540)) + 'px';  // fits the flow; scrolls beyond that
    plane.append(svg);
    const edgeEls = {};
    const edgeTagText = e => [e.label?.trim(), e.transfer === 'artifact_only' ? 'Solo ref' : e.transfer === 'summary' ? 'Resumen' : ''].filter(Boolean).join(' · ');
    const edgeMid = (a, b) => [(a.x + NODE_W + b.x) / 2, (a.y + b.y + NODE_H) / 2 - 8];
    for (const e of d.edges) {
      const a = nodeOf(e.from), b = nodeOf(e.to); if (!a || !b) continue;
      const key = e.from + '>' + e.to, g = svgEl('g', {class: 'axx-flow-edge', 'data-from': e.from, 'data-to': e.to});
      g.dataset.transfer = e.transfer || 'full';
      const p = svgEl('path', {d: edgePath(a, b), class: 'axx-flow-line', 'marker-end': 'url(#axx-flow-arrow)', id: 'axx-flow-e-' + order.indexOf(e.from) + '-' + order.indexOf(e.to)});
      const hit = svgEl('path', {d: edgePath(a, b), class: 'axx-flow-hit'});
      const [mx, my] = edgeMid(a, b);
      const tag = svgEl('text', {x: mx, y: my, class: 'axx-flow-edge-tag', textContent: edgeTagText(e)});
      hit.addEventListener('click', ev => { ev.stopPropagation(); flow.sel = {edge: key}; renderFlow(); });
      g.append(p, hit, tag);
      const st = flow.run?.edges[key];
      if (st) g.dataset.state = st;
      if (st === 'flowing') {
        const dot = svgEl('circle', {r: '5', class: 'axx-flow-dot'}), anim = svgEl('animateMotion', {dur: '1.4s', repeatCount: 'indefinite'});
        const mp = svgEl('mpath'); mp.setAttribute('href', '#' + p.id); anim.append(mp); dot.append(anim); g.append(dot);
      }
      if (flow.sel?.edge === key) g.classList.add('axx-flow-selected');
      svg.append(g); edgeEls[key] = {g, p, hit, tag};
    }
    flow.syncEdgeTag = e => {
      const els = edgeEls[e.from + '>' + e.to]; if (!els) return;
      els.g.dataset.transfer = e.transfer || 'full';
      els.tag.textContent = edgeTagText(e);
    };
    for (const n of d.nodes) plane.append(nodeCard(n, step[n.agent_id], edgeEls));
    if (!d.nodes.length) plane.append(el('div', {className: 'axx-flow-hint', textContent: 'Añade Acts con los botones de arriba. Después une la salida ● de uno con la entrada ● de otro.'}));
    canvas.addEventListener('pointerdown', ev => { if (ev.target === canvas || ev.target === plane || ev.target === svg) { flow.sel = null; renderFlow(); } });
    canvas.addEventListener('keydown', ev => {
      if ((ev.key === 'Delete' || ev.key === 'Backspace') && flow.sel && !/^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) {
        ev.preventDefault(); removeSelection();
      }
    });
    main.append(head, el('div', {className: 'axx-flow-toolbar'}, palette, tools), canvas, inspector(order), runBar());
    canvas.scrollLeft = flow.scroll?.[0] || 0; canvas.scrollTop = flow.scroll?.[1] || 0;
    canvas.addEventListener('scroll', () => { flow.scroll = [canvas.scrollLeft, canvas.scrollTop]; });
    if (flow.focus) { main.querySelector(`.axx-flow-node[data-agent="${flow.focus}"]`)?.focus({preventScroll: true}); flow.focus = null; }
    saveBtn.classList.toggle('primary', flowDirty() || !d.team_id);
  }

  function nodeCard(n, order, edgeEls) {
    const a = actOf(n.agent_id), run = flow.run, st = run ? (run.states[n.agent_id] || 'queued') : (a?.enabled === false ? 'disabled' : 'idle');
    const inPort = el('span', {className: 'axx-flow-port axx-flow-in', title: 'Entrada: recibe el resultado de los Acts conectados'});
    const outPort = el('span', {className: 'axx-flow-port axx-flow-out', title: 'Salida: arrastra hasta otro Act para conectarlo'});
    const role = el('button', {type: 'button', className: 'axx-flow-role', textContent: ROLE_LABEL[n.role], title: 'Cambiar rol',
      onclick: ev => { ev.stopPropagation(); n.role = ROLE_NEXT[n.role]; markFlow(); renderFlow(); }});
    role.dataset.role = n.role;
    const card = el('div', {className: 'axx-flow-node', tabIndex: 0, role: 'group',
      ariaLabel: `${a?.name || n.agent_id}, paso ${order}, ${ROLE_LABEL[n.role]}`},
      inPort,
      el('div', {className: 'axx-flow-node-head'}, a ? lookImg(a.appearance, 34, {className: 'axx-flow-face'}) : el('span'),
        el('div', {className: 'axx-flow-node-name'}, el('strong', {textContent: a?.name || n.agent_id}), el('small', {textContent: a ? modelLabel(a) : 'Act no disponible'})),
        el('span', {className: 'axx-flow-order', title: 'Orden de ejecución', textContent: String(order)})),
      el('div', {className: 'axx-flow-node-meta'}, role,
        el('span', {className: 'axx-acts-badge axx-acts-state', textContent: run ? (RUN_LABEL[st] || st) : (st === 'disabled' ? 'Deshabilitado' : 'Listo')})),
      el('p', {className: 'axx-flow-task', textContent: n.instruction || 'Sin tarea propia: trabaja sobre el objetivo general.'}),
      outPort,
      el('button', {type: 'button', className: 'axx-flow-x', ariaLabel: 'Quitar del equipo', textContent: '×',
        onclick: ev => { ev.stopPropagation(); flow.sel = {node: n.agent_id}; removeSelection(); }}));
    card.dataset.agent = n.agent_id; card.dataset.state = st;
    card.querySelector('.axx-acts-badge').dataset.state = st;
    if (a) { const [main, light] = paletteColors(a.appearance?.palette_id); card.style.setProperty('--act', main); card.style.setProperty('--act-light', light); }
    if (run?.started?.[n.agent_id] && st === 'working') card.querySelector('.axx-flow-task').textContent = 'Trabajando… ' + fmtMs(performance.now() - run.started[n.agent_id]);
    card.style.left = n.x + 'px'; card.style.top = n.y + 'px';
    if (flow.sel?.node === n.agent_id) card.classList.add('axx-flow-selected');
    // drag to move (redraws only the touching connections)
    card.addEventListener('pointerdown', ev => {
      if (ev.button !== 0 || ev.target.closest('button,.axx-flow-port')) return;
      const sx = ev.clientX, sy = ev.clientY, ox = n.x, oy = n.y; let moved = false;
      card.setPointerCapture(ev.pointerId);
      const move = e => {
        const dx = e.clientX - sx, dy = e.clientY - sy; if (!moved && Math.abs(dx) + Math.abs(dy) < 4) return; moved = true;
        n.x = Math.max(0, Math.round((ox + dx) / 10) * 10); n.y = Math.max(0, Math.round((oy + dy) / 10) * 10);
        card.style.left = n.x + 'px'; card.style.top = n.y + 'px';
        for (const [key, els] of Object.entries(edgeEls)) {
          const [f, t] = key.split('>'); if (f !== n.agent_id && t !== n.agent_id) continue;
          const a = nodeOf(f), b = nodeOf(t), path = edgePath(a, b);
          els.p.setAttribute('d', path); els.hit.setAttribute('d', path);
          if (els.tag) { els.tag.setAttribute('x', (a.x + NODE_W + b.x) / 2); els.tag.setAttribute('y', (a.y + b.y + NODE_H) / 2 - 8); }
        }
      };
      const up = () => { card.removeEventListener('pointermove', move); card.removeEventListener('pointerup', up);
        if (moved) markFlow(); flow.sel = {node: n.agent_id}; flow.focus = n.agent_id; renderFlow(); };
      card.addEventListener('pointermove', move); card.addEventListener('pointerup', up);
    });
    // drag from the output port to another Act to connect them
    outPort.addEventListener('pointerdown', ev => {
      ev.stopPropagation(); ev.preventDefault();
      const plane = card.parentElement, svg = plane.querySelector('.axx-flow-edges');
      const ghost = svgEl('path', {class: 'axx-flow-ghost'}); svg.append(ghost);
      outPort.setPointerCapture(ev.pointerId);
      const rect = () => plane.getBoundingClientRect();
      const move = e => {
        const r = rect(), x = e.clientX - r.left, y = e.clientY - r.top;
        ghost.setAttribute('d', edgePath(n, {x, y: y - NODE_H / 2}));
        for (const c of plane.querySelectorAll('.axx-flow-node')) c.classList.toggle('axx-flow-target',
          c !== card && c.contains(document.elementFromPoint(e.clientX, e.clientY)));
      };
      const up = e => {
        outPort.removeEventListener('pointermove', move); outPort.removeEventListener('pointerup', up); ghost.remove();
        const target = document.elementFromPoint(e.clientX, e.clientY)?.closest('.axx-flow-node');
        plane.querySelectorAll('.axx-flow-target').forEach(c => c.classList.remove('axx-flow-target'));
        if (target && target !== card) connect(n.agent_id, target.dataset.agent);
      };
      outPort.addEventListener('pointermove', move); outPort.addEventListener('pointerup', up);
    });
    card.addEventListener('keydown', ev => {  // keyboard: Enter selects, arrows nudge (Shift = bigger steps)
      if (ev.target !== card) return;
      const step = ev.shiftKey ? 50 : 10, move = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]}[ev.key];
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); flow.sel = {node: n.agent_id}; flow.focus = n.agent_id; renderFlow(); }
      else if (move) { ev.preventDefault(); n.x = Math.max(0, n.x + move[0]); n.y = Math.max(0, n.y + move[1]); flow.focus = n.agent_id; markFlow(); renderFlow(); }
    });
    return card;
  }

  function addNode(a) {
    const d = flow.draft, y = d.nodes.length ? Math.max(...d.nodes.map(n => n.y)) : 0;
    const role = !d.nodes.length ? 'lead' : guessRole(a);
    d.nodes.push({agent_id: a.agent_id, role, x: d.nodes.length ? 40 + GAP_X * Math.min(2, d.nodes.length) : 40, y: d.nodes.length ? y + (d.nodes.length > 2 ? GAP_Y : 0) : 40, instruction: ''});
    flow.sel = {node: a.agent_id}; markFlow(); renderFlow();
    say(`${a.name} añadido. Arrastra desde su salida ● hasta otro Act para conectarlos.`);
  }
  function removeSelection() {
    const d = flow.draft, sel = flow.sel; if (!sel) return;
    if (sel.edge) d.edges = d.edges.filter(e => e.from + '>' + e.to !== sel.edge);
    if (sel.node) { d.nodes = d.nodes.filter(n => n.agent_id !== sel.node); d.edges = d.edges.filter(e => e.from !== sel.node && e.to !== sel.node); }
    flow.sel = null; markFlow(); renderFlow();
  }
  function markFlow() { flow.els?.main.querySelector('[data-flow=save]')?.classList.add('primary'); }

  const RUN_LABEL = {queued: 'En cola', working: 'Trabajando', completed: 'Completado', failed: 'Error', cancelled: 'Detenido'};
  function inspector(order) {
    const d = flow.draft, box = el('aside', {className: 'axx-flow-inspector', ariaLive: 'polite'});
    if (flow.sel?.edge) {
      const [f, t] = flow.sel.edge.split('>');
      const edgeObj = flow.draft.edges.find(e => e.from === f && e.to === t) || {from: f, to: t, label: '', transfer: 'full'};
      const labelIn = el('input', {value: edgeObj.label || '', placeholder: 'Contrato de entrega (ej. Diff + resultados de pruebas)',
        ariaLabel: 'Contrato de entrega', oninput: () => { edgeObj.label = labelIn.value.slice(0, 80); markFlow(); flow.syncEdgeTag?.(edgeObj); }});
      const transferSel = el('select', {ariaLabel: 'Alcance de transferencia',
        onchange: () => { edgeObj.transfer = transferSel.value; markFlow(); flow.syncEdgeTag?.(edgeObj); }},
        ...options([['full', 'Salida completa verificada'], ['summary', 'Resumen conciso (≤420 chars)'], ['artifact_only', 'Solo referencia y SHA de artefacto']], edgeObj.transfer || 'full'));
      const presetRow = el('div', {className: 'axx-flow-presets'},
        ...['Diff + pruebas', 'Diagnóstico raíz', 'Criterios QA', 'Solo hallazgos'].map(text =>
          el('button', {type: 'button', textContent: text, onclick: () => { labelIn.value = text; edgeObj.label = text; markFlow(); flow.syncEdgeTag?.(edgeObj); }})));
      box.append(el('strong', {textContent: `${actOf(f)?.name || f} → ${actOf(t)?.name || t}`}),
        el('p', {textContent: `${actOf(t)?.name || t} trabaja después de ${actOf(f)?.name || f} y recibe su resultado verificado como entrada (Handoff v1: solo los permisos que ambos ya tienen; nada se hereda).`}),
        field('Contrato de entrega en esta conexión', labelIn),
        presetRow,
        field('Qué comparte hacia adelante', transferSel),
        el('button', {type: 'button', textContent: 'Quitar conexión', onclick: () => removeSelection()}));
      return box;
    }
    const n = flow.sel?.node && nodeOf(flow.sel.node);
    if (!n) {
      box.append(el('strong', {textContent: d.nodes.length ? `Orden de ejecución: ${order.map(id => actOf(id)?.name || id).join(' → ')}` : 'Lienzo vacío'}),
        el('p', {textContent: d.edges.length ? 'Selecciona un Act para darle su parte del trabajo o conectarlo; selecciona una línea para ver o quitar la conexión.'
          : d.nodes.length > 1 ? 'Aún no hay conexiones: cada Act trabajará por separado. Conéctalos para que uno use el resultado del otro.' : ''}));
      return box;
    }
    const a = actOf(n.agent_id), task = el('textarea', {rows: 2, value: n.instruction, maxLength: 600, placeholder: 'Ej. Escribe las pruebas; revisa solo seguridad…',
      oninput: () => { n.instruction = task.value; markFlow();  // in place: a re-render here would swallow the next click
        const p = flow.els.main.querySelector(`.axx-flow-node[data-agent="${n.agent_id}"] .axx-flow-task`);
        if (p) p.textContent = n.instruction || 'Sin tarea propia: trabaja sobre el objetivo general.'; }});
    const targets = d.nodes.filter(m => m.agent_id !== n.agent_id && !connectProblem(d, n.agent_id, m.agent_id));
    const pick = el('select', {ariaLabel: 'Conectar salida a'}, new Option('Conectar su salida a…', ''),
      ...targets.map(m => new Option(actOf(m.agent_id)?.name || m.agent_id, m.agent_id)));
    pick.onchange = () => pick.value && connect(n.agent_id, pick.value);
    const ins = d.edges.filter(e => e.to === n.agent_id).map(e => actOf(e.from)?.name || e.from);
    const outs = d.edges.filter(e => e.from === n.agent_id).map(e => actOf(e.to)?.name || e.to);
    box.append(el('div', {className: 'axx-flow-insp-head'}, a ? lookImg(a.appearance, 40) : el('span'),
      el('div', {}, el('strong', {textContent: a?.name || n.agent_id}), el('small', {textContent: (a?.role || '') + ' · ' + (a ? modelLabel(a) : '')}))),
      field('Su parte en este flujo', task),
      el('p', {className: 'axx-flow-io', textContent: `Recibe de: ${ins.join(', ') || 'nadie (empieza con el objetivo)'} · Entrega a: ${outs.join(', ') || 'resultado final'}`}),
      el('div', {className: 'quick-row'}, pick,
        el('button', {type: 'button', textContent: 'Rol: ' + ROLE_LABEL[n.role], onclick: () => { n.role = ROLE_NEXT[n.role]; markFlow(); renderFlow(); }}),
        el('button', {type: 'button', textContent: 'Quitar del equipo', onclick: () => removeSelection()})));
    const out = flow.run?.outputs?.[n.agent_id];
    if (out) box.append(el('details', {className: 'axx-flow-output', open: true}, el('summary', {textContent: `Resultado de ${a?.name} · ${out.model}`}),
      el('pre', {textContent: out.text})));
    return box;
  }

  function runBar() {
    const d = flow.draft, run = flow.run;
    const goal = el('input', {placeholder: 'Objetivo para este equipo (ej. «Prepara la página de precios y revísala»)', ariaLabel: 'Objetivo de la ejecución',
      value: run?.goal || d.purpose || ''});
    const go = el('button', {type: 'button', className: 'primary', textContent: run?.active ? 'Ejecutando…' : 'Ejecutar flujo', disabled: !!run?.active || !d.nodes.length,
      onclick: attempt(() => runFlow(goal.value.trim() || d.purpose || ''))});
    go.dataset.flow = 'run';
    const stop = el('button', {type: 'button', textContent: 'Detener', hidden: !run?.active, onclick: () => run?.abort.abort()});
    const info = el('small', {className: 'axx-flow-runinfo', textContent: run ? (run.active ? `Ejecución en curso · ${fmtMs(performance.now() - run.t0)}` : run.summary || '') : 'El resultado consolidado también se envía al chat activo.'});
    return el('div', {className: 'axx-flow-run'}, goal, go, stop, info);
  }

  async function saveFlow() {
    const d = flow.draft;
    if (!d.title.trim()) throw new Error('Ponle nombre al equipo.');
    if (!d.nodes.length) throw new Error('Añade al menos un Act al lienzo.');
    const off = d.nodes.filter(n => !actOf(n.agent_id)?.enabled).map(n => actOf(n.agent_id)?.name || n.agent_id);
    if (off.length) throw new Error('Quita o habilita estos Acts antes de guardar: ' + off.join(', '));
    if (!d.nodes.some(n => n.role === 'lead')) d.nodes[0].role = 'lead';
    const lead = d.nodes.find(n => n.role === 'lead').agent_id;
    const body = {title: d.title.trim(), purpose: d.purpose.trim(), budget_usd: d.budget_usd, coordinator_agent_id: lead,
      review_criteria: d.review_criteria || '', delegation_rules: d.delegation_rules || '',
      shared_memory_policy: d.shared_memory_policy || 'explicit_shared',
      members: d.nodes.map(n => ({agent_id: n.agent_id, role: n.role})),
      graph: {nodes: d.nodes.map(({agent_id, x, y, instruction}) => ({agent_id, x, y, instruction})),
        edges: d.edges.map(e => ({from: e.from, to: e.to, ...(e.label?.trim() ? {label: e.label.trim()} : {}),
          ...(e.transfer && e.transfer !== 'full' ? {transfer: e.transfer} : {})}))}};
    const res = d.team_id ? await api('POST', 'teams/update', {...body, team_id: d.team_id, expected_revision: d.revision})
      : await api('POST', 'teams', {...body, team_id: 'team-' + crypto.randomUUID().slice(0, 8)});
    await load();
    openDraft(draftFromTeam(res.team));
    say(`Equipo «${res.team.title}» guardado (revisión ${res.team.revision}). Ningún Act recibió permisos nuevos.`);
    return res.team;
  }

  async function runFlow(goal) {
    if (!goal) throw new Error('Escribe el objetivo que el equipo debe cumplir.');
    if (flowDirty() || !flow.draft.team_id) await saveFlow();
    const d = flow.draft, conv = activeConvId(), abort = new AbortController();
    const run = flow.run = {goal, t0: performance.now(), active: true, states: {}, edges: {}, outputs: {}, started: {}, abort};
    let seq = (await api('GET', 'events/sse?conversation_id=' + encodeURIComponent(conv)).catch(() => ({latest_seq: 0}))).latest_seq || 0;
    let runId = null;
    renderFlow();
    const absorb = ev => {
      const p = ev.payload || {}, mine = runId && (p.team_run_id === runId || ev.run_id === runId);
      if (!mine) return;
      if (ev.type === 'run.started' && p.team_run_id) { run.states[ev.agent_id] = 'working'; run.started[ev.agent_id] = performance.now();
        for (const e of d.edges) if (e.to === ev.agent_id && run.edges[e.from + '>' + e.to] !== 'done') run.edges[e.from + '>' + e.to] = 'flowing'; }
      if (ev.type === 'run.completed' && p.team_run_id) { run.states[ev.agent_id] = 'completed';
        for (const e of d.edges) if (e.to === ev.agent_id) run.edges[e.from + '>' + e.to] = 'done'; }
      if (ev.type === 'run.failed') run.states[ev.agent_id] = 'failed';
    };
    let polling = true;
    const poll = (async () => {
      while (polling) {
        await new Promise(r => setTimeout(r, 600));
        const res = await api('GET', `events/sse?conversation_id=${encodeURIComponent(conv)}&last_event_id=${seq}`).catch(() => null);
        if (!res) continue;
        for (const ev of res.events || []) { seq = Math.max(seq, ev.seq || 0); absorb(ev); }
        if (flow.run === run && flow.draft === d) renderFlow();
      }
    })();
    try {
      const res = await runTeamFromChat(goal, d.team_id, abort.signal, id => { runId = id; });
      for (const s of res.steps) { run.states[s.act_id] = 'completed'; run.outputs[s.act_id] = {text: s.text, model: s.model}; }
      for (const e of d.edges) run.edges[e.from + '>' + e.to] = 'done';
      run.summary = `Completado en ${fmtMs(performance.now() - run.t0)} · ${res.steps.length} Acts · ${(res.edges || []).length} handoffs verificados. Resultado enviado al chat.`;
      say(`Equipo «${d.title}» completado. Selecciona un Act para leer su resultado.`);
    } catch (e) {
      for (const id of Object.keys(run.states)) if (run.states[id] === 'working') run.states[id] = abort.signal.aborted ? 'cancelled' : 'failed';
      run.summary = (abort.signal.aborted ? 'Detenido: ' : 'Falló: ') + (e?.message || e);
      throw e;
    } finally {
      polling = false; await poll; run.active = false;
      if (flow.run === run) renderFlow();
    }
  }

  // ---- Rutinas: schedules the backend scheduler really fires ----
  const DAYS = [['1', 'L', 'Lunes'], ['2', 'M', 'Martes'], ['3', 'X', 'Miércoles'], ['4', 'J', 'Jueves'], ['5', 'V', 'Viernes'], ['6', 'S', 'Sábado'], ['0', 'D', 'Domingo']];
  const ROUTINE_STATE = {scheduled: ['Programada', 'idle'], running: ['Ejecutando', 'working'], awaiting_approval: ['Espera tu aprobación', 'awaiting_approval'],
    paused: ['En pausa', 'paused'], paused_on_import: ['En pausa (importada)', 'paused'], failed: ['Falló', 'failed'], cancelled: ['Desactivada', 'disabled'],
    completed: ['Terminada', 'completed'], blocked_dispatcher_unavailable: ['Sin modelo conectado', 'blocked'], queued_for_pressure: ['Esperando recursos', 'paused']};
  const RUN_STATUS = {completed: 'Completada', failed: 'Falló', running: 'En curso', retry_pending: 'Reintentará', awaiting_approval: 'Espera tu aprobación',
    already_recorded: 'Ya registrada', queued_for_pressure: 'Esperando recursos', blocked_dispatcher_unavailable: 'Sin modelo conectado', scheduled: 'Programada'};
  const runStatus = v => RUN_STATUS[v] || ROUTINE_STATE[v]?.[0] || v;
  const routineName = id => String(id).replace(/-/g, ' ');
  const pad = n => String(n).padStart(2, '0');
  function describeSchedule(spec) {
    const s = String(spec || '').trim(), every = /^every:(\d+)(ms|s|m|h)$/i.exec(s);
    if (every) return `Cada ${every[1]} ${{ms: 'ms', s: 's', m: 'min', h: 'h'}[every[2].toLowerCase()]}`;
    if (/^at:\d+$/.test(s)) return 'Una vez · ' + new Date(Number(s.slice(3))).toLocaleString();
    const f = s.split(/\s+/);
    if (f.length === 5 && /^\d+$/.test(f[0]) && /^\d+$/.test(f[1]) && f[2] === '*' && f[3] === '*') {
      const at = `${pad(f[1])}:${pad(f[0])}`;
      if (f[4] === '*') return 'Cada día a las ' + at;
      if (f[4] === '1-5') return 'De lunes a viernes a las ' + at;
      const names = f[4].split(',').map(v => DAYS.find(d => d[0] === String(Number(v) % 7))?.[2]).filter(Boolean);
      if (names.length) return names.join(', ') + ' a las ' + at;
    }
    if (f.length === 5 && /^\*\/(\d+)$/.test(f[0]) && f.slice(1).every(v => v === '*')) return `Cada ${f[0].slice(2)} min`;
    return 'Cron: ' + s;
  }
  function relTime(ms) {
    if (!ms) return '—';
    const dt = ms - Date.now(), abs = Math.abs(dt), m = Math.round(abs / 60000);
    const txt = abs < 60000 ? 'menos de 1 min' : m < 60 ? m + ' min' : m < 1440 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${Math.floor(m / 1440)} d ${Math.floor(m % 1440 / 60)} h`;
    return dt >= 0 ? 'en ' + txt : 'hace ' + txt;
  }
  const rt = {editing: null, history: {}};
  function renderRoutines() {
    routinesBox.replaceChildren();
    const awaiting = state.routines.filter(r => r.status === 'awaiting_approval').length;
    const top = el('div', {className: 'axx-rt-top'},
      el('div', {}, el('h4', {textContent: 'Rutinas'}),
        el('small', {textContent: `${state.routines.filter(r => r.enabled).length} activas${awaiting ? ` · ${awaiting} esperan tu aprobación` : ''} · las ejecuta el planificador de AXX aunque esta vista esté cerrada; nunca usan micrófono ni entrada física.`})),
      el('button', {type: 'button', className: 'primary', textContent: '+ Nueva rutina', onclick: () => { rt.editing = {}; renderRoutines(); }}));
    routinesBox.append(top);
    if (rt.editing) routinesBox.append(routineEditor(rt.editing));
    if (!state.routines.length && !rt.editing)
      routinesBox.append(el('div', {className: 'axx-flow-empty'}, el('strong', {textContent: 'Sin rutinas todavía'}),
        el('span', {textContent: 'Una rutina hace que un Act o un equipo trabaje solo según un horario: «cada día a las 9 revisa los tickets nuevos», «los viernes resume la semana».'})));
    const grid = el('div', {className: 'axx-rt-list'});
    for (const r of [...state.routines].sort((a, b) => (b.status === 'awaiting_approval') - (a.status === 'awaiting_approval') || (a.next_run_at_ms || 9e15) - (b.next_run_at_ms || 9e15)))
      grid.append(routineCard(r));
    routinesBox.append(grid);
  }
  function routineCard(r) {
    const [label, st] = ROUTINE_STATE[r.status] || [r.status, 'idle'], team = r.team_id && state.teams.find(t => t.team_id === r.team_id);
    const act = actOf(r.agent_id);
    const who = team ? el('span', {className: 'axx-flow-faces', title: 'Equipo ' + team.title}, ...(team.members || []).slice(0, 4).map(m => actOf(m.agent_id) ? lookImg(actOf(m.agent_id).appearance, 26) : el('span')))
      : act ? lookImg(act.appearance, 40) : el('span');
    const act1 = (text, fn, cls) => el('button', {type: 'button', textContent: text, className: cls || '', onclick: attempt(async () => { await fn(); await load(); })});
    const actions = el('div', {className: 'quick-row'});
    if (r.status === 'awaiting_approval') actions.append(
      act1('Aprobar y ejecutar', async () => { const res = await api('POST', 'routines/approve', {routine_id: r.routine_id, approved: true});
        say(`«${routineName(r.routine_id)}»: ${runStatus(res.status)}${res.summary ? ' — resultado en su historial y en Actividad' : ''}${res.error ? ' — ' + res.error : ''}`); }, 'primary'),
      act1('Omitir esta vez', async () => { await api('POST', 'routines/approve', {routine_id: r.routine_id, approved: false}); say('Ejecución omitida; sigue programada.'); }));
    else if (r.enabled) actions.append(act1('Ejecutar ahora', async () => {
      const trig = await api('POST', 'routines/trigger', {routine_id: r.routine_id, proposes_mutation: r.requires_approval});
      say(trig.status === 'awaiting_approval' ? 'Pide aprobación: apruébala en esta tarjeta.' : `«${routineName(r.routine_id)}»: ${runStatus(trig.status)}${trig.error ? ' — ' + trig.error : ''}`); }));
    if (!['cancelled', 'completed'].includes(r.status))
      actions.append(act1(r.enabled ? 'Pausar' : 'Reanudar', () => api('POST', r.enabled ? 'routines/pause' : 'routines/resume', {routine_id: r.routine_id})));
    actions.append(
      el('button', {type: 'button', textContent: 'Editar', onclick: () => { rt.editing = r; renderRoutines(); routinesBox.querySelector('.axx-rt-editor')?.scrollIntoView({block: 'nearest'}); }}),
      el('button', {type: 'button', textContent: rt.history[r.routine_id] ? 'Ocultar historial' : 'Historial', onclick: attempt(async () => {
        rt.history[r.routine_id] = rt.history[r.routine_id] ? null : (await api('GET', 'routines/history?routine_id=' + encodeURIComponent(r.routine_id))).runs;
        renderRoutines(); })}));
    if (r.status !== 'cancelled') actions.append(act1('Desactivar', async () => {
      if (!confirm(`¿Desactivar la rutina «${r.routine_id}»? Se detiene si está corriendo y no volverá a ejecutarse.`)) throw new Error('Sin cambios.');
      await api('POST', 'routines/cancel', {routine_id: r.routine_id}); }));
    const card = el('article', {className: 'axx-rt-card'},
      el('div', {className: 'axx-rt-who'}, who),
      el('div', {className: 'axx-rt-body'},
        el('div', {className: 'axx-acts-title'}, el('strong', {textContent: routineName(r.routine_id)}),
          withData(el('span', {className: 'axx-acts-badge axx-acts-state', textContent: label}), {state: st})),
        el('small', {textContent: (team ? `Equipo ${team.title}` : act ? act.name : r.agent_id) + ' · ' + describeSchedule(r.schedule_spec)
          + (r.requires_approval ? ' · pide aprobación' : ' · sin aprobación')}),
        el('p', {className: 'axx-rt-prompt', textContent: r.prompt_text || 'Sin instrucción'}),
        el('div', {className: 'axx-rt-times'},
          el('span', {}, 'Próxima: ', withData(el('b', {className: 'axx-rt-next', textContent: r.enabled ? relTime(r.next_run_at_ms) : '—'}), {at: String(r.next_run_at_ms || '')})),
          el('span', {textContent: 'Última: ' + (r.last_run_at_ms ? relTime(r.last_run_at_ms) : 'nunca')}),
          el('span', {textContent: `Reintentos ${r.retry_count}/${r.max_retries} · $${r.budget_usd}`})),
        actions));
    card.dataset.state = st; card.dataset.routine = r.routine_id;
    const runs = rt.history[r.routine_id];
    if (runs) card.querySelector('.axx-rt-body').append(el('ol', {className: 'axx-rt-history'}, ...(runs.length ? runs.slice(0, 8).map(run => el('li', {},
      withData(el('span', {className: 'axx-acts-badge axx-acts-state', textContent: runStatus(run.status)}), {state: run.status === 'completed' ? 'completed' : run.status === 'running' ? 'working' : 'failed'}),
      ` ${new Date(run.started_at_ms).toLocaleString()}` + (run.finished_at_ms ? ` · ${Math.max(0, Math.round((run.finished_at_ms - run.started_at_ms) / 100) / 10)} s` : ''),
      run.result_summary ? el('details', {}, el('summary', {textContent: 'Resultado'}), el('pre', {textContent: run.result_summary})) : ''))
      : [el('li', {textContent: 'Aún no se ha ejecutado.'})])));
    return card;
  }
  function parseSpec(spec) {  // existing spec -> editor fields
    const s = String(spec || 'every:1h'), every = /^every:(\d+)(m|h)$/.exec(s), f = s.split(/\s+/);
    if (every) return {mode: 'interval', n: every[1], unit: every[2]};
    if (/^at:\d+$/.test(s)) { const d = new Date(Number(s.slice(3))); return {mode: 'once', when: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`}; }
    if (f.length === 5 && /^\d+$/.test(f[0]) && /^\d+$/.test(f[1]) && f[2] === '*' && f[3] === '*') {
      const time = `${pad(f[1])}:${pad(f[0])}`;
      if (f[4] === '*') return {mode: 'daily', time};
      const days = f[4] === '1-5' ? ['1', '2', '3', '4', '5'] : f[4].split(',').map(v => String(Number(v) % 7));
      if (days.every(v => /^[0-6]$/.test(v))) return {mode: 'weekly', time, days};
    }
    return {mode: 'cron', cron: s};
  }
  function routineEditor(r) {
    const isNew = !r.routine_id, sp = parseSpec(r.schedule_spec), form = el('form', {className: 'axx-rt-editor'});
    const nameIn = el('input', {required: true, value: r.routine_id ? r.routine_id.replace(/-/g, ' ') : '', disabled: !isNew, placeholder: 'Ej. Resumen diario de tickets'});
    let target = r.team_id ? 'team' : 'act';
    const actSel = el('select', {}, ...options(state.acts.filter(a => a.enabled).map(a => [a.agent_id, a.name]), r.agent_id));
    const teamSel = el('select', {}, ...options(state.teams.map(t => [t.team_id, t.title || t.team_id]), r.team_id));
    const targetSeg = el('div', {className: 'axx-acts-segments', role: 'tablist'});
    const modes = [['interval', 'Cada cierto tiempo'], ['daily', 'Diario'], ['weekly', 'Días de la semana'], ['once', 'Una vez'], ['cron', 'Avanzado (cron)']];
    let mode = sp.mode;
    const nIn = el('input', {type: 'number', min: '1', value: sp.n || '1', ariaLabel: 'Cantidad'});
    const unitSel = el('select', {ariaLabel: 'Unidad'}, ...options([['m', 'minutos'], ['h', 'horas']], sp.unit || 'h'));
    const timeIn = el('input', {type: 'time', value: sp.time || '09:00', ariaLabel: 'Hora'});
    const days = new Set(sp.days || ['1', '2', '3', '4', '5']);
    const dayRow = el('div', {className: 'axx-rt-days'}, ...DAYS.map(([v, short, long]) => { const b = el('button', {type: 'button', textContent: short, title: long, ariaLabel: long,
      onclick: () => { days.has(v) ? days.delete(v) : days.add(v); b.setAttribute('aria-pressed', String(days.has(v))); refresh(); }});
      b.setAttribute('aria-pressed', String(days.has(v))); return b; }));
    const whenIn = el('input', {type: 'datetime-local', value: sp.when || '', ariaLabel: 'Fecha y hora'});
    const cronIn = el('input', {value: sp.cron || '0 9 * * 1-5', ariaLabel: 'Expresión cron', placeholder: 'min hora día mes día-semana'});
    const modeSeg = el('div', {className: 'axx-acts-segments', role: 'tablist'});
    const modeBox = el('div', {className: 'axx-rt-mode'});
    const preview = el('div', {className: 'axx-rt-preview', ariaLive: 'polite'});
    const promptIn = el('textarea', {rows: 3, required: true, value: r.prompt_text || '', placeholder: 'Qué debe hacer en cada ejecución'});
    const examples = el('div', {className: 'quick-row axx-rt-examples'}, el('small', {textContent: 'Ideas:'}),
      ...['Resume los cambios del día y lista riesgos', 'Revisa el estado del proyecto y propone los 3 siguientes pasos', 'Prepara el informe semanal para el equipo']
        .map(t => el('button', {type: 'button', textContent: t, onclick: () => { promptIn.value = t; }})));
    const approve = el('input', {type: 'checkbox', checked: r.requires_approval ?? true});
    const retries = el('input', {type: 'number', min: '0', max: '5', value: String(r.max_retries ?? 1)});
    const budget = el('input', {type: 'number', min: '0', step: '0.1', value: String(r.budget_usd ?? 0.5)});
    const spec = () => mode === 'interval' ? `every:${Math.max(1, Number(nIn.value) || 1)}${unitSel.value}`
      : mode === 'daily' ? `${Number(timeIn.value.slice(3, 5))} ${Number(timeIn.value.slice(0, 2))} * * *`
      : mode === 'weekly' ? `${Number(timeIn.value.slice(3, 5))} ${Number(timeIn.value.slice(0, 2))} * * ${[...days].sort().join(',') || '*'}`
      : mode === 'once' ? `at:${whenIn.value ? new Date(whenIn.value).getTime() : ''}` : cronIn.value.trim();
    let previewSeq = 0;
    async function refresh() {
      for (const b of targetSeg.children) b.setAttribute('aria-selected', String(b.dataset.v === target));
      for (const b of modeSeg.children) b.setAttribute('aria-selected', String(b.dataset.v === mode));
      actSel.closest('.setting').hidden = target !== 'act'; teamSel.closest('.setting').hidden = target !== 'team';
      modeBox.replaceChildren(...(mode === 'interval' ? [el('span', {textContent: 'Cada'}), nIn, unitSel]
        : mode === 'daily' ? [el('span', {textContent: 'Todos los días a las'}), timeIn]
        : mode === 'weekly' ? [dayRow, el('span', {textContent: 'a las'}), timeIn]
        : mode === 'once' ? [whenIn] : [cronIn, el('small', {textContent: 'min hora día-del-mes mes día-de-semana · ej. «*/30 8-18 * * 1-5»'})]));
      const mySeq = ++previewSeq, s = spec();
      preview.textContent = 'Calculando próximas ejecuciones…';
      try {
        const res = await api('GET', 'routines/preview?schedule_spec=' + encodeURIComponent(s).replace(/\*/g, '%2A'));
        if (mySeq !== previewSeq) return;
        preview.replaceChildren(el('strong', {textContent: describeSchedule(s)}), el('span', {textContent: ' · próximas: '}),
          ...res.next_runs_ms.map((ms, i) => el('span', {className: 'axx-acts-chip', textContent: (i ? '' : '① ') + new Date(ms).toLocaleString() + ` (${relTime(ms)})`})));
        preview.dataset.valid = 'true';
      } catch (e) { if (mySeq === previewSeq) { preview.textContent = 'Programación no válida: ' + (e?.message || e); preview.dataset.valid = 'false'; } }
    }
    for (const [v, l] of [['act', 'Un Act'], ['team', 'Un equipo']]) { const b = el('button', {type: 'button', role: 'tab', textContent: l, disabled: v === 'team' && !state.teams.length,
      onclick: () => { target = v; refresh(); }}); b.dataset.v = v; targetSeg.append(b); }
    for (const [v, l] of modes) { const b = el('button', {type: 'button', role: 'tab', textContent: l, onclick: () => { mode = v; refresh(); }}); b.dataset.v = v; modeSeg.append(b); }
    for (const input of [nIn, unitSel, timeIn, whenIn, cronIn]) input.addEventListener('input', () => refresh());
    form.append(el('h4', {textContent: isNew ? 'Nueva rutina' : 'Editar rutina'}),
      el('div', {className: 'axx-rt-grid'},
        el('section', {}, el('strong', {textContent: '1 · Quién'}), field('Nombre', nameIn), targetSeg, field('Act', actSel), field('Equipo (lo ejecuta entero, en el orden de su flujo)', teamSel)),
        el('section', {}, el('strong', {textContent: '2 · Cuándo'}), modeSeg, modeBox, preview),
        el('section', {}, el('strong', {textContent: '3 · Qué'}), field('Instrucción', promptIn), examples),
        el('section', {}, el('strong', {textContent: '4 · Seguridad'}), field('Pedir mi aprobación antes de cada ejecución', approve),
          field('Reintentos si falla (0–5)', retries), field('Presupuesto por ejecución (USD)', budget),
          el('small', {textContent: 'Las rutinas no pueden usar micrófono ni entrada física; sus herramientas siguen siendo las que concediste a cada Act.'}))),
      el('div', {className: 'quick-row'}, el('button', {type: 'submit', className: 'primary', textContent: isNew ? 'Programar rutina' : 'Guardar rutina'}),
        el('button', {type: 'button', textContent: 'Cancelar', onclick: () => { rt.editing = null; renderRoutines(); }})));
    form.onsubmit = attempt(async e => {
      e.preventDefault();
      if (preview.dataset.valid === 'false') throw new Error('Corrige la programación antes de guardar.');
      const team = target === 'team' && state.teams.find(t => t.team_id === teamSel.value);
      if (target === 'team' && !team) throw new Error('Elige un equipo.');
      const agent = team ? (team.coordinator_agent_id || team.members[0].agent_id) : actSel.value;
      if (!agent) throw new Error('Crea y habilita primero un Act.');
      const slug = (r.routine_id || nameIn.value.normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase().replace(/[^a-z0-9_.:-]+/g, '-').replace(/^-+|-+$/g, '')).slice(0, 80);
      if (!slug) throw new Error('Ponle nombre a la rutina.');
      if (isNew && state.routines.some(x => x.routine_id === slug)) throw new Error('Ya existe una rutina con ese nombre.');
      await api('POST', 'routines', {routine_id: slug, agent_id: agent, team_id: team ? team.team_id : '', conversation_id: r.conversation_id || activeConvId(),
        schedule_spec: spec(), requested_capabilities: ['read_workspace'], requires_approval: approve.checked, prompt_text: promptIn.value.trim(),
        max_retries: Number(retries.value || 0), budget_usd: Number(budget.value || 0), enabled: true});
      rt.editing = null;
      say(`Rutina «${slug.replace(/-/g, ' ')}» programada: ${describeSchedule(spec())}.`);
      await load();
    });
    void refresh();
    return form;
  }
  setInterval(() => {  // countdowns stay honest; when a slot passes, reload what the scheduler did
    if (host.hidden || routinesBox.hidden) return;
    let due = false;
    for (const b of routinesBox.querySelectorAll('.axx-rt-next[data-at]')) {
      const at = Number(b.dataset.at); if (!at) continue; b.textContent = relTime(at); if (at < Date.now() - 3000) due = true;
    }
    if (due && !rt.editing) void load().catch(() => {});
  }, 15000);

  function blank(templateKey = 'scratch') {
    const t = TEMPLATES[templateKey] || TEMPLATES.scratch;
    return {schema_version: '1.0', name: templateKey === 'scratch' ? '' : t.mention, role: templateKey === 'scratch' ? '' : t.role,
      description: '', instructions: t.instructions, enabled: true,
      appearance: {form_id: t.form, palette_id: t.palette, material_preset: 'obsidian', scale: 1, animation_intensity: 1, reduce_motion: false, reactions: {}},
      intelligence: {route: 'manual', fallback: 'none', max_parallel_turns: 1},
      voice: {language: 'es-DO', auto_speak: false, speed: 1, intonation: 'neutral', expressiveness: 'medium', tts_profile_id: ''},
      workspace: {runtime: 'none', foreground_policy: 'deny', allowed_roots: []},
      permissions: {tool_grant_refs: [], delegation_enabled: false, max_delegate_depth: 0},
      limits: {max_concurrent_jobs: 1, max_retries: 0, max_cost_usd: 0, max_ram_mb: 1024, max_cpu_percent: 70, max_task_seconds: 120, remote_execution_allowed: false, user_priority_override: true},
      memory_scope: 'agent', personality: {}, autonomy: {mode: 'manual'},
      collaboration: t.mention ? {mention: t.mention, accepts_handoffs: true} : {}};
  }
  const EDITABLE = ['name', 'role', 'description', 'instructions', 'enabled', 'appearance', 'intelligence', 'voice', 'workspace',
    'limits', 'memory_scope', 'personality', 'autonomy', 'collaboration'];

  async function edit(act, duplicate = false, templateKey = 'scratch') {
    if (dirty() && !confirm('Hay cambios sin guardar. ¿Descartarlos?')) return;
    const base = blank(templateKey);
    if (act) for (const k of EDITABLE) if (act[k] !== undefined) base[k] = structuredClone(act[k]);
    if (act && !duplicate) { base.agent_id = act.agent_id; base.revision = act.revision; }
    if (duplicate) { base.name = (act.name + ' (copia)').slice(0, 80); base.enabled = false;
      if(base.collaboration)delete base.collaboration.mention; }  // copies never inherit grants or mention aliases
    state.grants = act && !duplicate ? (await api('GET', 'profiles/permissions?agent_id=' + encodeURIComponent(act.agent_id))).permissions : [];
    state.toolGrant = state.grants.some(g => g.tool_id === TOOL && g.approval_mode !== 'deny');
    base.toolGrant = state.toolGrant;
    const codeGrant = state.grants.find(g => g.tool_id === CODE && g.approval_mode !== 'deny');
    base.codeOps = Object.fromEntries(CODE_OPS.map(op => [op, !!codeGrant?.operation_kinds.includes(op)]));
    const spGrant = state.grants.find(g => g.tool_id === SPATIAL && g.approval_mode !== 'deny');
    base.spatialOps = Object.fromEntries(SPATIAL_OPS.map(op => [op, !!spGrant?.operation_kinds.includes(op)]));
    const compGrant = state.grants.find(g => g.tool_id === COMP && g.approval_mode !== 'deny');
    base.compOps = Object.fromEntries(COMP_OPS.map(op => [op, !!compGrant?.operation_kinds.includes(op)]));
    state.draft = base; state.base = JSON.stringify(base); state.tab = 'identity';
    preview.hidden = true; renderEditor();
    editor.scrollIntoView({block: 'start', behavior: 'smooth'});  // it opens below the library, out of view
    editor.querySelector('input, select, textarea')?.focus({preventScroll: true});
  }

  function control(path, kind, extra = {}) {
    const value = get(state.draft, path);
    let input;
    if (kind === 'select') input = el('select', {}, ...options(extra.pairs, value));
    else if (kind === 'textarea') input = el('textarea', {value: value ?? '', rows: extra.rows || 3, maxLength: extra.max || 2000});
    else if (kind === 'checkbox') input = el('input', {type: 'checkbox', checked: !!value});
    else {
      const {list, ...attrs} = extra.attrs || {};
      input = el('input', {type: kind, value: value ?? '', ...attrs});
      if (list) input.setAttribute('list', list);
    }
    input.dataset.path = path;
    input.addEventListener('input', () => {
      let v = kind === 'checkbox' ? input.checked : input.value;
      if (extra.number && v !== '') v = Number(v);
      if (extra.csv) v = String(v).split(',').map(s => s.trim()).filter(Boolean);
      set(state.draft, path, (Array.isArray(v) && !v.length) ? undefined : v);
      if (path === 'intelligence.provider_profile_ref') {
        // Router profiles fix the model; ChatGPT starts from the model chosen in Conectar IA and stays editable.
        const p = state.providers.find(x => x.name === v);
        if (v === CONNECT) set(state.draft, 'intelligence.model_id', document.getElementById('ai-model')?.value || undefined);
        else if (p) set(state.draft, 'intelligence.model_id', p.model);
        renderEditor();
      } else if (path.startsWith('appearance.')) renderSwatch();
      markDirty();
    });
    if (kind === 'checkbox') input.addEventListener('change', () => input.dispatchEvent(new Event('input')));
    return input;
  }

  // ---- Appearance: AXX's own 24 forms, 9 palettes and finishes, drawn by its renderer (act-avatar.js) ----
  const AV = Axx.actAvatar;
  const paletteColors = id => (Axx.PALETTES?.[id] || Axx.PALETTES?.[0])?.colors || ['#157eff', '#79e7ff', '#a14dff', '#edb58c'];
  // Fallback when the renderer is unavailable: the backend's cached SVG, else a small swatch in AXX's real colours.
  function fallbackSvg(look) {
    const [main, light, deep] = paletteColors(look.palette_id);
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="14" fill="#0b0f17"/>`
      + `<circle cx="32" cy="32" r="18" fill="${deep}" fill-opacity=".35" stroke="${light}" stroke-width="2"/><circle cx="32" cy="32" r="${8 + (look.form_id % 9)}" fill="${main}"/></svg>`;
  }
  // <img> for an Act look: SVG first (instant), then the real AXX render replaces it.
  function lookImg(look, size, {svg, ...props} = {}) {
    const img = el('img', {alt: '', width: size, height: size, decoding: 'async', ...props,
      src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg || fallbackSvg(look))});
    return AV ? AV.paint(img, look, size * 2) : img;
  }
  const STUDIO_SLIDERS = [['exposure', 'Brillo', .35, 2.2, .05, 1], ['roughness', 'Rugosidad del acabado', .015, .45, .005, .07],
    ['light_angle', 'Ángulo de luz (°)', -180, 180, 5, 0], ['fluidity', 'Fluidez', 0, 2.3, .05, 1]];
  const REACTION_SLOTS = [['thinking', 'Al pensar', 'planning'], ['working', 'Al trabajar', 'working'], ['approval', 'Al pedir aprobación', 'awaiting_approval'],
    ['completed', 'Al completar', 'completed'], ['error', 'Si falla', 'failed']];
  let look = null;  // live parts of the open Appearance tab
  function renderSwatch() { look?.refresh(); }
  function appearancePanel() {
    const d = state.draft, a = d.appearance;
    const change = (path, value) => { set(state.draft, path, value); refresh(); markDirty(); };
    const stage = el('div', {className: 'axx-acts-look-stage', title: 'Arrastra para girar'});
    if (AV) AV.rotatable(stage);
    const caption = el('div', {className: 'axx-acts-look-caption'});
    const tryRow = el('div', {className: 'axx-acts-look-try'}, el('small', {textContent: 'Probar:'}),
      ...[['idle', 'Reposo'], ['planning', 'Pensando'], ['working', 'Trabajando'], ['speaking', 'Hablando'], ['completed', 'Listo'], ['failed', 'Error']]
        .map(([st, label]) => el('button', {type: 'button', textContent: label, onclick: () => AV?.setState(st)})));
    const radio = (label, checked, onclick, ...kids) => {
      const b = el('button', {type: 'button', role: 'radio', ariaLabel: label, onclick}, ...kids);
      b.setAttribute('aria-checked', String(checked)); return b;
    };
    const formGrid = el('div', {className: 'axx-acts-form-grid', role: 'radiogroup', ariaLabel: 'Forma'});
    const paletteRow = el('div', {className: 'axx-acts-palette-row', role: 'radiogroup', ariaLabel: 'Paleta'});
    const materialRow = el('div', {className: 'axx-acts-material-row', role: 'radiogroup', ariaLabel: 'Material'});
    function paintGalleries() {
      formGrid.replaceChildren(...Axx.FORMS.map((f, i) => radio(f.name, i === a.form_id, () => change('appearance.form_id', i),
        lookImg({...a, form_id: i}, 56), el('span', {textContent: f.name}))));
      for (const [i, b] of [...formGrid.children].entries()) b.title = Axx.FORMS[i].detail;
      paletteRow.replaceChildren(...Axx.PALETTES.map((p, i) => radio(p.name, i === a.palette_id, () => change('appearance.palette_id', i),
        el('span', {className: 'axx-acts-palette-dot', style: `background:conic-gradient(${p.colors.join(',')},${p.colors[0]})`}), el('span', {textContent: p.name}))));
      materialRow.replaceChildren(...MATERIALS.map(m => radio(AV?.MATERIAL_LABEL[m] || m, m === (a.material_preset || 'obsidian'),
        () => change('appearance.material_preset', m), lookImg({...a, material_preset: m}, 36), el('span', {textContent: AV?.MATERIAL_LABEL[m] || m}))));
    }
    const slider = (path, label, min, max, step, fallback) => {
      const out = el('output');
      const input = el('input', {type: 'range', min, max, step, value: get(d, path) ?? fallback});
      const show = () => { out.textContent = Number(input.value).toFixed(step < .01 ? 3 : step < 1 ? 2 : 0); };
      input.oninput = () => { show(); set(state.draft, path, Number(input.value)); refresh(false); markDirty(); };
      input.id = 'axx-act-field-' + (++fieldSeq);  // the label names the range input itself, not its wrapper
      show(); return el('div', {className: 'setting'}, el('label', {htmlFor: input.id, textContent: label}), el('div', {className: 'axx-acts-slider'}, input, out));
    };
    const reactions = REACTION_SLOTS.map(([key, label, st]) => {
      const sel = el('select', {}, ...options([['', 'Sin gesto'], ...Object.entries(AV?.GESTURES || {})], get(d, 'appearance.reactions.' + key)));
      sel.onchange = () => { set(state.draft, 'appearance.reactions.' + key, sel.value || undefined); refresh(false); markDirty(); AV?.setState(st); };
      return field(label, sel);
    });
    const motionBox = control('appearance.reduce_motion', 'checkbox');
    motionBox.addEventListener('change', () => refresh(false));
    function refresh(galleries = true) {
      if (!state.draft) return;
      if (galleries) paintGalleries();
      const f = Axx.FORMS[a.form_id], p = Axx.PALETTES[a.palette_id];
      caption.replaceChildren(el('strong', {textContent: f.name + ' · ' + p.name}), el('span', {textContent: f.detail}),
        el('small', {textContent: (AV?.MATERIAL_LABEL[a.material_preset] || a.material_preset) + ' · El avatar principal de AXX no cambia.'}));
      if (AV) AV.show(stage, a, 'idle'); else stage.innerHTML = fallbackSvg(a);
    }
    look = {refresh};
    setTimeout(() => refresh());
    return [
      el('div', {className: 'axx-acts-look'}, el('div', {className: 'axx-acts-look-preview'}, stage, caption, tryRow),
        el('div', {className: 'axx-acts-look-pickers'},
          el('h5', {textContent: 'Forma de AXX'}), formGrid,
          el('h5', {textContent: 'Paleta'}), paletteRow,
          el('h5', {textContent: 'Material'}), materialRow)),
      el('fieldset', {className: 'axx-acts-look-tune'}, el('legend', {textContent: 'Ajustar la forma'}),
        slider('appearance.scale', 'Tamaño', .6, 1.3, .05, 1), slider('appearance.animation_intensity', 'Energía de animación', 0, 2, .1, 1),
        ...STUDIO_SLIDERS.map(([k, label, min, max, step, def]) => slider('appearance.studio.' + k, label, min, max, step, def)),
        field('Reducir animación de este Act', motionBox),
        el('button', {type: 'button', textContent: 'Restablecer ajustes', onclick: () => {
          for (const k of ['studio', 'scale', 'animation_intensity']) delete state.draft.appearance[k];
          markDirty(); renderEditor(); }})),
      el('fieldset', {className: 'axx-acts-look-tune'}, el('legend', {textContent: 'Cómo reacciona mientras trabaja'}), ...reactions,
        el('p', {textContent: 'El gesto se ve en la vista previa, en el chat y en Code Studio cuando el Act cambia de estado.'})),
    ];
  }
  const markDirty = () => { const d = editor.querySelector('.axx-acts-dirty'); if (d) d.textContent = dirty() ? 'Cambios sin guardar' : 'Sin cambios'; };

  function panel(id) {
    const d = state.draft, pairs = obj => Object.entries(obj);
    switch (id) {
      case 'identity': {
        const out = [];
        if (!d.agent_id) {
          const tplSel = el('select', {}, ...options(pairs(TEMPLATES).map(([k, v]) => [k, v.label]), 'scratch'));
          tplSel.onchange = () => void edit(null, false, tplSel.value);
          out.push(field('Plantilla inicial (no concede permisos)', tplSel));
        }
        out.push(
          field('Nombre', control('name', 'text', {attrs: {maxLength: 80, required: true}})),
          field('Nombre corto para @menciones', control('collaboration.mention', 'text', {attrs: {pattern: '[A-Za-z0-9_-]{1,32}', placeholder: 'Dev'}})),
          field('Especialidad / rol', control('role', 'text', {attrs: {maxLength: 240, required: true}})),
          field('Descripción y objetivo', control('description', 'textarea', {max: 2000})),
          field('Idiomas (separados por coma)', el('input', {type: 'text', placeholder: 'es-DO, en-US',
            value: (d.personality?.languages || []).join(', '), oninput: e => {
              const list = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
              set(state.draft, 'personality.languages', list.length ? list : undefined); markDirty();
            }})),
          field('Nivel de iniciativa', control('personality.initiative_level', 'select', {pairs: [['', '—'], ['low', 'Baja'], ['medium', 'Media'], ['high', 'Alta']]})),
          field('Formato de resultados', control('personality.result_format', 'select', {pairs: [['', '—'], ['summary', 'Resumen'], ['detailed', 'Detalle técnico'], ['diff_and_evidence', 'Diff y evidencia'], ['checklist', 'Checklist']]})),
          field('Instrucciones persistentes', control('instructions', 'textarea', {max: 16000, rows: 6})),
        );
        return out;
      }
      case 'appearance': return appearancePanel();
      case 'intelligence': {
        const router = state.providers.map(p => [p.name, p.name + ' · ' + p.model]);
        const isConnect = d.intelligence.provider_profile_ref === CONNECT;
        const models = el('datalist', {id: 'axx-acts-connect-models'}, ...[...(document.getElementById('ai-model')?.options || [])].map(o => new Option(o.value)));
        return [field('Selección', control('intelligence.route', 'select', {pairs: [['manual', 'Manual: este proveedor y modelo'], ['policy', 'Automática gratuita del router']]})),
          field('Proveedor', control('intelligence.provider_profile_ref', 'select', {pairs: [['', '—'], ...router, [CONNECT, 'Axx Connect · ChatGPT']]})),
          field('Modelo', control('intelligence.model_id', 'text', {attrs: {readOnly: !isConnect, list: 'axx-acts-connect-models', maxLength: 180}})), models,
          el('p', {className: 'axx-acts-hint', textContent: isConnect
            ? 'Escribe o elige el modelo de ChatGPT que usará este Act; el modelo global de AXX no cambia.'
            : d.intelligence.provider_profile_ref ? 'El modelo lo fija este perfil en Conectar IA. Si no está instalado (por ejemplo en Ollama), cambia el perfil allí o elige ChatGPT.' : 'Elige un proveedor para ver su modelo.'}),
          field('Alternativa si falla', control('intelligence.fallback', 'select', {pairs: [['none', 'Ninguna: no cambiar de proveedor'], ['ask', 'Preguntar']]})),
          field('Límite de salida (tokens por turno)', control('intelligence.max_tokens_per_turn', 'number', {number: true, attrs: {min: 128, max: 1000000}})),
          el('p', {textContent: 'Las credenciales siguen en Conectar IA; el Act solo referencia la conexión. Nunca se cambia a una ruta de pago.'})];
      }
      case 'personality': return [...pairs(PERSONALITY).map(([k, [label, vals]]) =>
        field(label, control('personality.' + k, 'select', {pairs: [['', '— sin preferencia —'], ...pairs(vals)]}))),
        field('Idioma por defecto', control('personality.default_language', 'text', {attrs: {placeholder: 'es-DO', pattern: '[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*'}})),
        field('Estilo de comunicación', control('personality.communication_style', 'textarea', {max: 500})),
        field('Preferencias de programación', control('personality.coding_preferences', 'textarea', {max: 1000})),
        field('Criterios de calidad', control('personality.quality_criteria', 'textarea', {max: 1000})),
        el('p', {textContent: 'La personalidad orienta cómo responde el Act; no concede permisos ni cambia la seguridad.'})];
      case 'voice': {
        const vPairs = [['', 'Voz global / automática'], ...state.voices.map(v => {
          const uri = (v.engine === 'moss-onnx' || v.engine === 'piper-onnx') ? v.name : 'sapi:' + v.name;
          return [uri, (v.label || v.name) + ' · ' + (v.language || '')];
        })];
        return [field('Voz TTS del Act', control('voice.tts_profile_id', 'select', {pairs: vPairs})),
          field('Idioma', control('voice.language', 'text', {attrs: {maxLength: 48}})),
          field('Velocidad', control('voice.speed', 'number', {number: true, attrs: {min: 0.5, max: 2, step: 0.05}})),
          field('Entonación', control('voice.intonation', 'select', {pairs: [['neutral', 'Neutral'], ['calm', 'Calmado'], ['warm', 'Cálido'], ['focused', 'Enfocado'], ['energetic', 'Enérgico']]})),
          field('Expresividad', control('voice.expressiveness', 'select', {pairs: [['low', 'Baja'], ['medium', 'Media'], ['high', 'Alta']]})),
          field('Hablar respuestas automáticamente', control('voice.auto_speak', 'checkbox')),
          el('p', {textContent: 'Conectado al motor TTS local de AXX. El micrófono nunca se activa sin tu permiso explícito.'})];
      }
      case 'memory': return [field('Alcance', control('memory_scope', 'select', {pairs: [['conversation', 'Solo esta conversación'], ['agent', 'Privada del Act'],
        ['project', 'Proyecto'], ['explicit_shared', 'Compartida explícitamente']]})), privateMemoryPanel()];
      case 'tools': return [field('Comandos AXX (cada acción sigue pidiendo su aprobación)', control('toolGrant', 'checkbox')),
        el('p', {textContent: 'Sin este permiso el Act conversa y propone, pero no recibe herramientas. Revocarlo bloquea la siguiente acción.'}),
        el('fieldset', {}, el('legend', {textContent: 'Code Studio (siempre en el worktree propio del Act)'}),
          field('Crear su worktree', control('codeOps.worktree', 'checkbox')),
          field('Aplicar parches en su worktree', control('codeOps.patch', 'checkbox')),
          field('Ejecutar pruebas en su worktree', control('codeOps.test', 'checkbox')),
          field('Integrar en el proyecto tras pruebas superadas', control('codeOps.integrate', 'checkbox')),
          field('Revisar cambios de otros Acts', control('codeOps.review', 'checkbox'))),
        el('fieldset', {}, el('legend', {textContent: 'Magic Pen / 3D Studio (axx.spatial)'}),
          field('Leer escenas SceneDocument', control('spatialOps.read', 'checkbox')),
          field('Proponer cambios en escena/diagrama', control('spatialOps.patch', 'checkbox')),
          field('Ejecutar Diorama QA / Validación', control('spatialOps.qa', 'checkbox')),
          field('Construir geometría CAD real', control('spatialOps.cad', 'checkbox')),
          field('Exportar artefactos 3D/MP4', control('spatialOps.export', 'checkbox'))),
        el('fieldset', {}, el('legend', {textContent: 'Entorno Windows y Navegador (axx.computer)'}),
          field('Archivos en allowed_roots', control('compOps.files', 'checkbox')),
          field('Sesión de navegador aislado', control('compOps.browser', 'checkbox')),
          field('UI Automation semántica', control('compOps.uia', 'checkbox')),
          field('Espacio aislado / VM compatible', control('compOps.vm', 'checkbox')),
          field('Solicitar primer plano autorizado', control('compOps.foreground', 'checkbox')))];
      case 'computer': return [field('Entorno', control('workspace.runtime', 'select', {pairs: [['none', 'Ninguno'], ['api', 'Archivos/API'], ['browser', 'Navegador aislado'],
        ['window_background', 'Ventana en segundo plano'], ['host_foreground', 'Primer plano (con reserva)'], ['isolated_vm', 'VM aislada'], ['remote', 'Remoto']]})),
        field('Política de foco', control('workspace.foreground_policy', 'select', {pairs: [['deny', 'Rechazar'], ['ask', 'Preguntar'], ['queue', 'Esperar'], ['isolated_only', 'Solo aislado']]}))];
      case 'autonomy': return [field('Modo', control('autonomy.mode', 'select', {pairs: [['manual', 'Manual: conversa y propone'], ['assisted', 'Asistido: prepara y pide aprobación'],
        ['auto_safe', 'Auto seguro'], ['background', 'Segundo plano'], ['scheduled', 'Programado'], ['isolated', 'Aislado']]})),
        el('p', {textContent: 'La autonomía es independiente del rol y no amplía permisos.'})];
      case 'collaboration': return [field('Acepta handoffs', control('collaboration.accepts_handoffs', 'checkbox')),
        field('Requiere revisión de otro Act', control('collaboration.review_required', 'checkbox')),
        field('Reglas de colaboración', control('collaboration.rules', 'textarea', {max: 1000}))];
      case 'resources': return [field('Trabajos simultáneos', control('limits.max_concurrent_jobs', 'number', {number: true, attrs: {min: 1, max: 16}})),
        field('Reintentos', control('limits.max_retries', 'number', {number: true, attrs: {min: 0, max: 8}})),
        field('Gasto máximo (USD)', control('limits.max_cost_usd', 'number', {number: true, attrs: {min: 0, step: 0.01}})),
        field('RAM máxima (MB)', control('limits.max_ram_mb', 'number', {number: true, attrs: {min: 128, max: 65536, step: 128}})),
        field('CPU máxima (%)', control('limits.max_cpu_percent', 'number', {number: true, attrs: {min: 5, max: 100, step: 5}})),
        field('Tiempo máximo por tarea (seg)', control('limits.max_task_seconds', 'number', {number: true, attrs: {min: 5, max: 86400}})),
        field('Prioridad para tareas del usuario', control('limits.user_priority_override', 'checkbox')),
        field('Permitir ejecución remota autorizada', control('limits.remote_execution_allowed', 'checkbox'))];
    }
    return [];
  }

  function renderEditor() {
    editor.hidden = false;
    const list = el('div', {className: 'axx-acts-tabs', role: 'tablist', ariaLabel: 'Secciones del Act'});
    TABS.forEach(([id, label], i) => {
      const tab = el('button', {type: 'button', role: 'tab', textContent: label, tabIndex: id === state.tab ? 0 : -1});
      tab.setAttribute('aria-selected', String(id === state.tab));
      tab.onclick = () => { state.tab = id; renderEditor(); editor.querySelector('[role=tab][aria-selected=true]')?.focus(); };
      tab.onkeydown = e => { const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (step) { e.preventDefault(); state.tab = TABS[(i + step + TABS.length) % TABS.length][0]; renderEditor(); editor.querySelector('[role=tab][aria-selected=true]')?.focus(); } };
      list.append(tab);
    });
    const body = el('fieldset', {className: 'axx-acts-panel', role: 'tabpanel'}, el('legend', {textContent: TABS.find(t => t[0] === state.tab)[1]}), ...panel(state.tab));
    editor.replaceChildren(el('h4', {textContent: state.draft.agent_id ? 'Personalizar ' + state.draft.name : 'Nuevo Act'}), list, body,
      el('div', {className: 'quick-row'}, el('button', {type: 'submit', className: 'primary', textContent: 'Aplicar y verificar'}),
        el('button', {type: 'button', textContent: 'Descartar', onclick: () => { if (!dirty() || confirm('¿Descartar los cambios?')) { state.draft = null; editor.hidden = true; } }}),
        el('span', {className: 'axx-acts-dirty', role: 'status'})));
    markDirty();
  }

  function privateMemoryPanel(){
    const aid=state.draft.agent_id,box=el('section',{}),list=el('div',{}),note=el('textarea',{maxLength:2000,rows:3}),message=el('p',{role:'status'});
    box.append(el('p',{textContent:'Notas privadas explícitas, hasta 90 días. Solo este Act las recibe cuando el alcance es Privada del Act. No se exportan ni se copian al duplicar.'}));
    if(!state.acts.some(a=>a.agent_id===aid)){box.append(el('p',{textContent:'Guarda primero el Act para gestionar sus recuerdos.'}));return box;}
    async function refresh(){
      const {memories}=await api('GET','profiles/memory?agent_id='+encodeURIComponent(aid));
      if(state.draft?.agent_id!==aid)return;
      list.replaceChildren(...memories.map(memory=>el('article',{className:'axx-chat-act-card'},
        el('p',{textContent:memory.content}),el('small',{textContent:'Revisión '+memory.revision+' · vence '+new Date(memory.expires_at_ms).toLocaleDateString()}),
        el('button',{type:'button',textContent:'Corregir recuerdo',onclick:attempt(async()=>{
          const content=prompt('Corregir recuerdo privado:',memory.content);if(!content?.trim())return;
          await api('POST','profiles/memory/save',{agent_id:aid,memory_id:memory.memory_id,expected_revision:memory.revision,content});await refresh();
        })}),el('button',{type:'button',textContent:'Olvidar recuerdo',onclick:attempt(async()=>{
          await api('POST','profiles/memory/forget',{agent_id:aid,memory_id:memory.memory_id,expected_revision:memory.revision});await refresh();
        })}))));
    }
    box.append(field('Recuerdo privado del Act',note),el('button',{type:'button',textContent:'Guardar recuerdo',onclick:attempt(async()=>{
      await api('POST','profiles/memory/save',{agent_id:aid,content:note.value});note.value='';await refresh();message.textContent='Recuerdo guardado solo para este Act.';
    })}),message,list);
    void refresh().catch(e=>message.textContent=e.message);return box;
  }

  async function syncOpsGrant(actId, toolId, ops, allowedList) {
    const existing = state.grants.filter(g => g.tool_id === toolId);
    const prevOps = (existing[0]?.operation_kinds || []).filter(op => allowedList.includes(op));
    if (ops.join() !== prevOps.join() || existing.length > 1) {
      for (const g of existing) await api('POST', 'profiles/permissions/revoke', {agent_id: actId, grant_id: g.grant_id});
      if (ops.length) await api('POST', 'profiles/permissions/grant', {
        agent_id: actId, grant_id: 'grant-' + actId + '-' + toolId.replace(/[^a-z0-9]/gi, ''),
        tool_id: toolId, resource_pattern: '*', operation_kinds: ops, approval_mode: 'ask',
      });
    }
  }

  editor.onsubmit = attempt(async e => {
    e.preventDefault();
    if (!editor.reportValidity()) return;
    const d = structuredClone(state.draft), wantsTool = !!d.toolGrant; delete d.toolGrant;
    const codeOps = CODE_OPS.filter(op => d.codeOps?.[op]); delete d.codeOps;
    const spatialOps = SPATIAL_OPS.filter(op => d.spatialOps?.[op]); delete d.spatialOps;
    const compOps = COMP_OPS.filter(op => d.compOps?.[op]); delete d.compOps;
    for (const k of ['personality', 'collaboration']) if (d[k] && !Object.keys(d[k]).length) delete d[k];
    if (d.voice && !d.voice.tts_profile_id) delete d.voice.tts_profile_id;
    let saved;
    if (d.agent_id) {
      const patch = {}; for (const k of EDITABLE) patch[k] = d[k] ?? null;
      saved = (await api('POST', 'profiles/update', {agent_id: d.agent_id, expected_revision: d.revision, patch})).profile;
    } else {
      const slug = (d.collaboration?.mention || d.name).toLowerCase().normalize('NFD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'act';
      saved = (await api('POST', 'profiles', {...d, agent_id: 'act-' + slug + '-' + crypto.randomUUID().slice(0, 8), revision: 1})).profile;
    }
    if (wantsTool !== state.toolGrant) {
      if (wantsTool) await api('POST', 'profiles/permissions/grant', {agent_id: saved.agent_id, grant_id: 'grant-' + saved.agent_id + '-commands',
        tool_id: TOOL, resource_pattern: '*', operation_kinds: ['command'], approval_mode: 'ask'});
      else for (const g of state.grants.filter(g => g.tool_id === TOOL)) await api('POST', 'profiles/permissions/revoke', {agent_id: saved.agent_id, grant_id: g.grant_id});
    }
    await syncOpsGrant(saved.agent_id, CODE, codeOps, CODE_OPS);
    await syncOpsGrant(saved.agent_id, SPATIAL, spatialOps, SPATIAL_OPS);
    await syncOpsGrant(saved.agent_id, COMP, compOps, COMP_OPS);
    const stored = (await api('GET', 'profiles?agent_id=' + encodeURIComponent(saved.agent_id))).profile;
    const mismatch = ['name', 'role', 'instructions', 'memory_scope'].filter(k => stored[k] !== saved[k]);
    const view = await api('POST', 'profiles/preview', {agent_id: saved.agent_id});
    preview.hidden = false;
    preview.textContent = 'Instrucciones que recibirá el modelo (' + view.transport + '):\n\n' + view.persona;
    state.draft = null; editor.hidden = true;
    await load();
    say(mismatch.length ? 'Guardado, pero difiere al releer: ' + mismatch.join(', ') : 'Guardado y verificado: ' + stored.name + ' · revisión ' + stored.revision + '.');
  });

  async function toggle(act) {
    if (act.enabled) await api('POST', 'profiles/disable', {agent_id: act.agent_id});
    else await api('POST', 'profiles/update', {agent_id: act.agent_id, expected_revision: act.revision, patch: {enabled: true}});
    await load(); say(act.name + (act.enabled ? ' deshabilitado; sus permisos fueron revocados.' : ' habilitado.'));
  }

  async function exportAct(act) {
    const pkg = await api('GET', 'profiles/export?agent_id=' + encodeURIComponent(act.agent_id));
    const url = URL.createObjectURL(new Blob([JSON.stringify(pkg, null, 2)], {type: 'application/json'}));
    el('a', {href: url, download: act.agent_id + '.axx-act.json'}).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    say('Perfil exportado sin credenciales, permisos ni rutas locales.');
  }

  importInput.onchange = attempt(async () => {
    const file = importInput.files[0]; importInput.value = '';
    if (!file) return;
    const pkg = JSON.parse(await file.text());
    const res = await api('POST', 'profiles/import', {package: pkg, new_agent_id: 'act-import-' + crypto.randomUUID().slice(0, 8)});
    await load(); say('Importado deshabilitado y sin permisos: ' + res.profile.name + '. Revísalo antes de habilitarlo.');
  });

  // ---- Chat Integration: Bindings (ACT-08), Per-Act Voice, Activity Drawer (ACT-13), Single-Sentence Team Run ----
  const activeConvId = () => Axx.chatWorkspace?.active?.id || 'default';
  const chatKey = () => 'axx.acts.chat.' + activeConvId();
  const chatSelect = el('select', {className: 'axx-acts-chat-select', ariaLabel: 'Quién responde en este chat', title: 'Quién responde en este chat'});
  const activityBtn = el('button', {type: 'button', className: 'axx-acts-chat-btn', textContent: 'Actividad Acts', hidden: true, title: 'Ver progreso, handoffs y artefactos en este chat'});
  const activityDrawer = el('section', {className: 'axx-acts-activity-drawer', hidden: true, ariaLabel: 'Actividad y Handoffs de Acts'});
  const composerControls = document.querySelector('#chat-form .composer-bottom > div');
  const chatWho = el('label', {className: 'axx-acts-chat-who', hidden: true}, el('span', {textContent: 'Responde', ariaHidden: 'true'}), chatSelect);
  if (composerControls) composerControls.append(chatWho, activityBtn);
  const chatForm = document.getElementById('chat-form');
  if (chatForm) chatForm.before(activityDrawer);

  // Presence: the working Act's own AXX form, animated by its state (one live renderer, moved between boxes).
  function presenceBox() {
    const stage = el('div', {className: 'axx-act-presence-stage', title: 'Arrastra para girar'});
    if (AV) AV.rotatable(stage);
    return el('div', {className: 'axx-act-presence', hidden: true}, stage, el('div', {className: 'axx-act-presence-text', role: 'status', ariaLive: 'polite'}));
  }
  const chatPresence = presenceBox();
  if (chatForm) chatForm.before(chatPresence);
  const presenceTimers = new WeakMap(), presenceClocks = new WeakMap();
  // meta: {startedAt, model} shows the model and a running clock; {detail} shows a final technical line.
  function presence(act, st, text, box = chatPresence, meta = null) {
    if (!box) return;
    clearTimeout(presenceTimers.get(box)); clearInterval(presenceClocks.get(box));
    if (!act) { box.hidden = true; AV?.hide(box.firstChild); return; }
    box.hidden = false; box.dataset.state = st;
    const metaLine = el('small', {className: 'axx-act-presence-meta'});
    box.lastChild.replaceChildren(el('strong', {textContent: act.name}), ' ', el('span', {textContent: text || STATE_LABEL[st] || st}), metaLine);
    if (meta?.startedAt) {
      const clock = () => { metaLine.textContent = (meta.model ? meta.model + ' · ' : '') + fmtMs(performance.now() - meta.startedAt); };
      clock(); presenceClocks.set(box, setInterval(clock, 250));
    } else if (meta?.detail) metaLine.textContent = meta.detail;
    if (AV) AV.show(box.firstChild, act.appearance, st, 1.8);
    else box.firstChild.replaceChildren(lookImg(act.appearance, 48));
    if (st === 'completed' || st === 'failed') presenceTimers.set(box, setTimeout(() => presence(null, '', '', box), st === 'failed' ? 6000 : 2600));
  }

  activityBtn.onclick = attempt(async () => {
    activityDrawer.hidden = !activityDrawer.hidden;
    if (!activityDrawer.hidden) await refreshActivity();
  });

  const EVENT_LABEL = {'run.started': 'empezó a trabajar', 'run.completed': 'terminó', 'run.failed': 'falló',
    'handoff.created': 'pasó el trabajo', 'handoff.completed': 'recibió el traspaso', 'tool.dispatched': 'usó una herramienta',
    'approval.requested': 'pide tu aprobación', 'approval.resolved': 'aprobación resuelta'};
  const EVENT_STATE = {'run.started': 'working', 'run.completed': 'completed', 'run.failed': 'failed', 'approval.requested': 'awaiting_approval'};
  // One readable row per event: who, what (in words), when; the raw type stays visible for diagnosis.
  function eventRow(ev) {
    const type = ev.type || ev.event_type || 'evento';
    const p = ev.payload || {};
    const name = state.acts.find(a => a.agent_id === ev.agent_id)?.name || ev.agent_id || 'AXX';
    const to = p.to_agent_id && (state.acts.find(a => a.agent_id === p.to_agent_id)?.name || p.to_agent_id);
    const detail = to ? '→ ' + to : (p.model || p.tool_id || p.verdict || p.kind || '');
    const ms = ev.ts_ms || ev.created_at_ms || ev.timestamp_ms;
    const row = el('div', {className: 'axx-acts-activity-item'},
      el('strong', {textContent: name}), ' ', el('span', {textContent: EVENT_LABEL[type] || type}),
      detail ? el('span', {className: 'axx-acts-activity-detail', textContent: ' ' + detail}) : '',
      el('code', {textContent: type}), ms ? el('time', {textContent: new Date(ms).toLocaleTimeString()}) : '');
    row.dataset.state = EVENT_STATE[type] || (type.startsWith('handoff') ? 'planning' : 'idle');
    return row;
  }

  async function refreshActivity() {
    const convId = activeConvId();
    const [sse, arts] = await Promise.all([
      api('GET', 'events/sse?conversation_id=' + encodeURIComponent(convId)).catch(() => ({events: []})),
      api('GET', 'artifacts').catch(() => ({artifacts: []})),
    ]);
    state.events = sse.events || [];
    for (const ev of state.events) {
      const evType = ev.type || ev.event_type;
      if (evType === 'run.started') state.actStates[ev.agent_id] = 'working';
      else if (evType === 'approval.requested') state.actStates[ev.agent_id] = 'awaiting_approval';
      else if (evType === 'run.completed') state.actStates[ev.agent_id] = 'completed';
      else if (evType === 'run.failed') state.actStates[ev.agent_id] = 'failed';
    }
    if (activityDrawer.hidden) return;
    activityDrawer.replaceChildren(el('strong', {textContent: `Actividad y Handoffs (${state.events.length} eventos · ${(arts.artifacts || []).length} artefactos)`}));
    for (const ev of state.events.slice(-12).reverse()) {
      const evType = ev.type || ev.event_type;
      const p = ev.payload || {};
      const row = eventRow(ev);
      if (evType === 'approval.requested' && p.operation_id) {
        row.append(' ',
          el('button', {type: 'button', textContent: 'Aprobar', onclick: attempt(async () => {
            await api('POST', 'approvals/resolve', {operation_id: p.operation_id, approved: true, actor: 'user'});
            await refreshActivity();
          })}),
          el('button', {type: 'button', textContent: 'Denegar', onclick: attempt(async () => {
            await api('POST', 'approvals/resolve', {operation_id: p.operation_id, approved: false, actor: 'user'});
            await refreshActivity();
          })}));
      }
      activityDrawer.append(row);
    }
    for (const art of (arts.artifacts || []).slice(0, 5)) {
      activityDrawer.append(el('div', {className: 'axx-acts-activity-item'},
        el('small', {textContent: `Artefacto [${art.artifact_type}] ${art.act_id}: ${art.path_or_ref} (${art.verification_status})`})));
    }
    if (!state.events.length && !(arts.artifacts || []).length) {
      activityDrawer.append(el('small', {textContent: 'Sin eventos activos en esta conversación.'}));
    }
  }

  async function syncConversationBinding() {
    const convId = Axx.chatWorkspace?.active?.id;
    if (!convId || !state.acts.length) return;
    const data = await api('GET', 'bindings?conversation_id=' + encodeURIComponent(convId)).catch(() => null);
    if (!data || Axx.chatWorkspace?.active?.id !== convId) return;
    const lead = (data?.bindings || []).find(b => b.membership_role === 'lead');
    if (lead?.agent_id && state.acts.some(a => a.enabled && a.agent_id === lead.agent_id)) {
      localStorage.setItem(chatKey(), lead.agent_id);
      syncChatSelect();
    } else { localStorage.removeItem(chatKey()); syncChatSelect(); }
  }

  async function chooseForChat(actId) {
    const convId = Axx.chatWorkspace?.active?.id;
    const key = chatKey();
    if (convId && actId) {
      const existing = await api('GET', 'bindings?conversation_id=' + encodeURIComponent(convId)).catch(() => ({bindings: []}));
      const endpoint = (existing.bindings || []).length ? 'bindings/switch' : 'bindings/convert';
      const body = endpoint === 'bindings/convert'
        ? {conversation_id: convId, lead_agent_id: actId, member_agent_ids: []}
        : {conversation_id: convId, new_agent_id: actId, has_active_run: false, actor: 'user'};
      try { await api('POST', endpoint, body); }
      catch (error) { syncChatSelect(); throw error; }
    } else if (convId) {
      await api('POST','bindings/clear-lead',{conversation_id:convId});
    }
    if (actId) localStorage.setItem(key, actId); else localStorage.removeItem(key);
    if (Axx.chatWorkspace?.active?.id === convId) syncChatSelect();
  }
  chatSelect.onchange = () => { void chooseForChat(chatSelect.value).catch(e => c.sayStatus?.(e.message)); };
  document.getElementById('chat-input')?.addEventListener('focus', () => syncChatSelect());
  if (Axx.chatWorkspace?.select) {
    const origSelect = Axx.chatWorkspace.select;
    Axx.chatWorkspace.select = async function (...args) {
      const res = await origSelect.apply(this, args);
      await syncConversationBinding().catch(() => {});
      await refreshActivity().catch(() => {});
      return res;
    };
  }
  function syncChatSelect() {
    const chosen = localStorage.getItem(chatKey()) || '';
    const enabledActs = state.acts.filter(a => a.enabled);
    activityBtn.hidden = chatWho.hidden = !enabledActs.length;  // no Acts: the composer stays exactly as before
    chatSelect.replaceChildren(...options([['', 'AXX'], ...enabledActs.map(a => [a.agent_id, a.name])], chosen));
    const chosenAct = enabledActs.find(a => a.agent_id === chosen);
    chatWho.dataset.act = chosenAct ? 'true' : 'false';
    chatWho.querySelector('img')?.remove();
    if (chosenAct) chatWho.prepend(lookImg(chosenAct.appearance, 22, {className: 'axx-acts-chat-face'}));
  }

  // Acts live inside the existing Chats y grupos browser. All conversations are the
  // original ChatStore records: this view only filters their N:N Act memberships.
  const chatBrowser = document.getElementById('cw-browser');
  const chatActs = el('section', {className:'axx-chat-acts', hidden:true, ariaLabel:'Acts en Chats y grupos'});
  const chatActsStatus = el('p', {role:'status', ariaLive:'polite'});
  const chatActsBody = el('div', {className:'axx-chat-acts-body'});
  let chatActsTab = 'library', chatActsEpoch = 0;
  const chatActsTabs = el('nav', {className:'axx-acts-segments', ariaLabel:'Secciones de Acts en chats'});
  const chatActsSearch = el('input', {type:'search', placeholder:'Buscar Act', ariaLabel:'Buscar Act'});
  const chatActsAgent = el('select', {ariaLabel:'Act para ver conversaciones'});
  for (const [id, label] of [['library','Mis Acts'],['chats','Chats por Act'],['teams','Equipos'],['activity','Actividad']]) {
    const b = el('button', {type:'button', textContent:label, onclick:() => {chatActsTab=id;void renderChatActs();}});
    b.dataset.actTab=id;chatActsTabs.append(b);
  }
  chatActs.append(chatActsTabs, el('div',{className:'quick-row'},
    el('button',{type:'button',textContent:'Crear / configurar Act',onclick:attempt(async()=>{
      c.openFeature('acts');await toggleStudio(true);await edit(null);
    })})),chatActsSearch,chatActsAgent,chatActsStatus,chatActsBody);
  if (chatBrowser) {
    const nav = el('div',{className:'cw-heading axx-chat-act-navigation',role:'tablist',ariaLabel:'Historial y Acts'});
    const all = el('button',{type:'button',role:'tab',textContent:'Todos los chats'});
    const acts = el('button',{type:'button',role:'tab',textContent:'Acts'});
    const show = async enabled => {
      chatBrowser.dataset.actsView=String(enabled);chatActs.hidden=!enabled;
      all.setAttribute('aria-selected',String(!enabled));acts.setAttribute('aria-selected',String(enabled));
      if(enabled){await load();await renderChatActs();}
    };
    all.onclick=()=>void show(false);acts.onclick=()=>void show(true).catch(e=>{chatActsStatus.textContent=e.message;});
    nav.append(all,acts);chatBrowser.insertBefore(nav,chatBrowser.children[1]);chatBrowser.append(chatActs);
    all.setAttribute('aria-selected','true');acts.setAttribute('aria-selected','false');
  }
  chatActsSearch.oninput=()=>void renderChatActs();chatActsAgent.onchange=()=>void renderChatActs();

  async function renderChatActs() {
    const epoch=++chatActsEpoch;
    const fail=err=>{if(epoch===chatActsEpoch)chatActsStatus.textContent=err.message||String(err);};
    try {
      chatActsStatus.textContent='';chatActsBody.replaceChildren();
      for(const b of chatActsTabs.children)b.setAttribute('aria-pressed',String(b.dataset.actTab===chatActsTab));
      chatActsSearch.hidden=chatActsTab!=='library';chatActsAgent.hidden=chatActsTab!=='chats';
      if(chatActsTab==='library') {
        const query=chatActsSearch.value.trim().toLocaleLowerCase();
        for(const act of state.acts.filter(a=>(a.name+' '+a.role).toLocaleLowerCase().includes(query))) {
          const live=actLiveStatus(act);
          const badge=el('span',{className:'axx-acts-badge axx-acts-state',textContent:STATE_LABEL[live]||live});badge.dataset.state=live;
          const row=el('article',{className:'axx-chat-act-card'},
            lookImg(act.appearance,40,{svg:act.thumbnail?.svg,alt:act.name}),
            el('div',{className:'axx-chat-act-meta'},
              el('div',{className:'axx-acts-title'},el('strong',{textContent:act.name}),badge),
              el('small',{textContent:(act.collaboration?.mention?'@'+act.collaboration.mention+' · ':'')+modelLabel(act)})),
            el('div',{className:'axx-chat-act-actions'},
              el('button',{type:'button',className:'primary',textContent:'Chatear',ariaLabel:'Abrir chat de '+act.name,disabled:!act.enabled,
                onclick:()=>void openActChat(act).catch(fail)}),
              el('button',{type:'button',textContent:'Configurar',ariaLabel:'Configurar '+act.name,onclick:attempt(async()=>{
                c.openFeature('acts');await toggleStudio(true);await edit(act);
              })})));
          row.dataset.state=live;row.style.setProperty('--i',String(chatActsBody.childElementCount));
          chatActsBody.append(row);
        }
        if(!chatActsBody.childElementCount)chatActsStatus.textContent='No hay Acts en esta vista. Crea uno y elige su modelo.';
      } else if(chatActsTab==='chats') {
        const selected=chatActsAgent.value;
        chatActsAgent.replaceChildren(...options(state.acts.map(a=>[a.agent_id,a.name]),selected));
        if(!chatActsAgent.value)return;
        const result=await api('GET','conversations?agent_id='+encodeURIComponent(chatActsAgent.value));
        if(epoch!==chatActsEpoch)return;
        for(const thread of result.conversations)chatActsBody.append(el('button',{type:'button',className:'axx-chat-act-thread',
          textContent:(thread.title||thread.conversation_id)+(thread.archived?' · archivado':''),
          onclick:()=>void Axx.chatWorkspace.select(thread.conversation_id).catch(fail)}));
        if(!result.conversations.length)chatActsStatus.textContent='Este Act todavía no tiene conversaciones.';
      } else if(chatActsTab==='teams') {
        for(const team of state.teams)chatActsBody.append(el('article',{className:'axx-chat-act-card'},
          el('strong',{textContent:team.name||team.team_id}),
          el('small',{textContent:(team.members||[]).map(m=>state.acts.find(a=>a.agent_id===m.agent_id)?.name||m.agent_id).join(' → ')}),
          el('button',{type:'button',textContent:'Configurar equipo',onclick:attempt(async()=>{
            c.openFeature('acts');await toggleStudio(true);state.subview='teams';renderSubview();
          })})));
        if(!state.teams.length)chatActsStatus.textContent='No hay equipos. Configúralos en Acts Studio.';
      } else {
        await refreshActivity();if(epoch!==chatActsEpoch)return;
        for(const event of state.events.slice(-30).reverse())chatActsBody.append(eventRow(event));
        if(!state.events.length)chatActsStatus.textContent='No hay actividad registrada en este chat.';
      }
    } catch(error){fail(error);}
  }
  async function openActChat(act) {
    const {conversations}=await api('GET','conversations?agent_id='+encodeURIComponent(act.agent_id));
    const existing=conversations.find(t=>!t.archived);
    if(existing)await Axx.chatWorkspace.select(existing.conversation_id);
    else await Axx.chatWorkspace.create();
    await chooseForChat(act.agent_id);c.openFeature('chat');document.getElementById('chat-input')?.focus();
  }

  function findAllMentions(text) {
    const raw = String(text || '');
    const found = [];
    const seen = new Set();
    for (const m of raw.matchAll(/@([\p{L}\p{N}_-]{1,32})\b/gu)) {
      const low = m[1].toLowerCase();
      const act = state.acts.find(a => a.enabled && ((a.collaboration?.mention || '').toLowerCase() === low || a.name.toLowerCase() === low));
      if (act && !seen.has(act.agent_id)) { seen.add(act.agent_id); found.push(act); }
    }
    for (const act of state.acts) {
      if (!act.enabled || seen.has(act.agent_id)) continue;
      const re = new RegExp(`(?:^|[.!\\n]\\s*)\\b${act.name.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\b\\s*[,:]`, 'i');
      if (re.test(raw)) { seen.add(act.agent_id); found.push(act); }
    }
    return found;
  }

  function mentioned(text) {
    const m = /^\s*@([\p{L}\p{N}_-]{1,32})\b/u.exec(String(text || ''));
    if (!m) return null;
    const name = m[1].toLowerCase();
    return state.acts.find(a => a.enabled && ((a.collaboration?.mention || '').toLowerCase() === name || a.name.toLowerCase() === name)) || null;
  }

  // Per-Act Voice hook on companion.read (preserving global reader & microphone)
  let pendingActVoice = null;
  const origRead = c.read?.bind(c);
  if (origRead) {
    c.read = function (text) {
      const reader = Axx.symbiosis?.reader;
      const author = /^〔([^〕]+)〕/.exec(String(text||''));
      const av = (author && state.acts.find(a=>a.name===author[1])?.voice) || pendingActVoice;
      pendingActVoice = null;
      if(reader)reader.nextTurnVoiceProfile=av?Object.freeze({voiceURI:av.tts_profile_id||reader.voiceURI,
        rate:Number(av.speed)||reader.rate,lang:av.language||reader.lang}):null;
      return origRead(text);
    };
  }

  // A long flow can outlive the native request timeout; the backend keeps working and records a durable receipt.
  async function awaitTeamReceipt(runId, signal, err) {
    for (;;) {
      if (signal?.aborted) throw err;
      const r = await api('GET', 'teams/result?run_id=' + encodeURIComponent(runId)).catch(() => null);
      if (r?.status === 'completed' && r.result) return r.result;
      if (r?.status !== 'running') throw err;
      c.sayStatus?.('El equipo sigue trabajando…');
      await new Promise(f => setTimeout(f, 1500));
    }
  }

  async function runTeamFromChat(promptText, teamId = null, signal = null, onRunId = null) {
    c.sayStatus?.('Coordinando equipo de Acts…');
    if (signal?.aborted) throw new DOMException('Equipo cancelado', 'AbortError');
    const runId = 'teamrun-' + crypto.randomUUID();
    onRunId?.(runId);  // live canvases follow this run's events
    const cancel = () => { void api('POST', 'teams/cancel', {run_id:runId}).catch(() => {}); };
    signal?.addEventListener('abort', cancel, {once:true});
    const file = Axx.codeStudio?.activeFile;  // with a file open in Code Studio the lead Act patches it in its worktree
    let res;
    try { res = await api('POST', 'teams/run', {
      run_id: runId,
      conversation_id: activeConvId(),
      prompt: promptText,
      ...(teamId ? {team_id: teamId} : {}),
      ...(file ? Axx.codeStudio.teamWork(file) : {}),
    }); } catch (err) {
      res = await awaitTeamReceipt(runId, signal, err);
    } finally { signal?.removeEventListener('abort', cancel); }
    if (signal?.aborted) throw new DOMException('Equipo cancelado; revisa los efectos en Actividad', 'AbortError');
    if (file && res.work) await Axx.codeStudio.showTeamResult(res, file, true).catch(() => {});
    await refreshActivity();
    if (c.message && teamId) {
      c.message('assistant', res.consolidated_text, 'local');
      c.renderChat?.(); c.save?.();
    }
    return res;
  }

  // ---- Acts using the computer (backend: agents/v1/computer/act-task) ----
  // AXX observes the window the owner authorized, the Act's own model proposes ONE gesture on a real control, and AXX
  // executes and verifies it through the existing Computer Use executor. The cursor below is drawn only from those
  // executed steps (real screen points); the native input indicator wears the Act's own material meanwhile.
  const ACTION_LABEL = {click: 'clic en', double_click: 'doble clic en', right_click: 'clic derecho en', scroll: 'desplaza',
    hotkey: 'atajo en', type_text: 'escribe en', move: 'se mueve a'};
  const cursorLayer = el('div', {className: 'axx-act-cursor-layer'});
  cursorLayer.setAttribute('aria-hidden', 'true');
  document.body.append(cursorLayer);
  function actCursor(act) {
    const [main, light] = paletteColors(act.appearance?.palette_id);
    const arrow = el('div', {className: 'axx-act-cursor-arrow'});
    arrow.innerHTML = `<svg viewBox="0 0 24 24" width="28" height="28"><path d="M3 2l7.2 19 2.7-7.7L21 10.6z" fill="${main}" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
    const cursor = el('div', {className: 'axx-act-cursor', hidden: true}, el('span', {className: 'axx-act-cursor-ring'}), arrow,
      el('div', {className: 'axx-act-cursor-tag'}, lookImg(act.appearance, 28, {className: 'axx-act-cursor-face'}),
        el('span', {className: 'axx-act-cursor-label'})));
    cursor.style.setProperty('--act', main); cursor.style.setProperty('--act-light', light);
    cursorLayer.append(cursor);
    return cursor;
  }
  // Physical screen pixels (UI Automation) -> CSS pixels of this resident window.
  function placeCursor(cursor, act, step) {
    if (!Number.isFinite(step.x) || !Number.isFinite(step.y)) return;
    const dpr = window.devicePixelRatio || 1, x = step.x / dpr - (window.screenX || 0), y = step.y / dpr - (window.screenY || 0);
    cursor.hidden = x < -60 || y < -60 || x > innerWidth + 60 || y > innerHeight + 60;
    cursor.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    cursor.dataset.state = step.state || 'dispatched';
    cursor.querySelector('.axx-act-cursor-label').textContent = act.name + ' · ' + (ACTION_LABEL[step.action] || step.action) + ' «' + step.label + '»';
    if (step.state === 'succeeded') { cursor.classList.remove('axx-act-click'); void cursor.offsetWidth; cursor.classList.add('axx-act-click'); }
  }
  async function computerTask(act, instruction, {box = chatPresence, signal = null, maxSteps = 8} = {}) {
    const convId = Axx.chatWorkspace?.active?.id;
    if (!convId) throw new Error('Abre un chat: la autorización de la computadora es por chat.');
    const status = await Axx.backendRequest('GET', '/axx-api/computer/status?conversation_id=' + encodeURIComponent(convId));
    if (!status?.active || !status.allow_input)
      throw new Error('Primero autoriza «Controlar PC» con entrada en este chat; después ' + act.name + ' podrá usar esa ventana.');
    const {run} = await api('POST', 'computer/act-task', {act_id: act.agent_id, conversation_id: convId, instruction, max_steps: maxSteps});
    const t0 = performance.now(), clock = {startedAt: t0, model: modelLabel(act)}, cursor = actCursor(act);
    const stop = () => void api('POST', 'computer/act-task/cancel', {run_id: run.run_id}).catch(() => {});
    signal?.addEventListener('abort', stop, {once: true});
    const show = text => {
      presence(act, 'working', text, box, clock);
      box?.lastChild.append(el('button', {type: 'button', className: 'axx-act-stop', textContent: 'Detener', onclick: stop}));
    };
    Axx.inputMaterialOverride = () => AV?.material(act.appearance) || null;
    state.actStates[act.agent_id] = 'working'; markCard(act.agent_id, 'working');
    show('observa ' + (run.target || 'la aplicación') + '…');
    let last = run, shown = 0;
    try {
      do {  // the last poll may already be terminal: its final step is still drawn before leaving
        await new Promise(r => setTimeout(r, 350));
        last = (await api('GET', 'computer/act-task?run_id=' + encodeURIComponent(run.run_id))).run;
        const step = last.steps.at(-1);
        if (step && (last.steps.length !== shown || step.state !== cursor.dataset.state)) {
          shown = last.steps.length; placeCursor(cursor, act, step);
          if (last.state === 'running') show(`paso ${step.step}: ${ACTION_LABEL[step.action] || step.action} «${step.label}»` + (step.say ? ' — ' + step.say : ''));
        }
      } while (last.state === 'running');
    } finally {
      Axx.inputMaterialOverride = null;
      signal?.removeEventListener('abort', stop);
      cursor.classList.add('axx-act-cursor-leaving'); setTimeout(() => cursor.remove(), 2600);
    }
    const ok = last.state === 'completed', verified = last.steps.filter(s => s.state === 'succeeded').length;
    state.actStates[act.agent_id] = ok ? 'completed' : 'failed'; markCard(act.agent_id, ok ? 'completed' : 'failed');
    state.lastRun[act.agent_id] = {at: Date.now(), ms: performance.now() - t0, ok, verified: true, model: last.model || act.intelligence?.model_id};
    presence(act, ok ? 'completed' : 'failed', ok ? (last.summary || 'terminó') : (last.error || 'se detuvo'), box,
      {detail: fmtMs(performance.now() - t0) + ' · ' + verified + ' gesto(s) verificado(s) por AXX · ' + (last.target || '')});
    return last;
  }
  function computerReport(act, runResult) {
    return '〔' + act.name + '〕 ' + (runResult.state === 'completed' ? runResult.summary : 'Se detuvo: ' + runResult.error)
      + (runResult.steps.length ? '\n' + runResult.steps.map(s => `${s.step}. ${ACTION_LABEL[s.action] || s.action} «${s.label}» → `
        + (s.state === 'succeeded' ? 'verificado' : s.state) + (s.error ? ' (' + s.error + ')' : '')).join('\n') : '');
  }

  const brainChat = c.brain.chat.bind(c.brain);
  c.brain.chat = async function (p, messages, signal, onDelta = () => {}) {
    if (!p.prompt_mode || p.act_id) return brainChat(p, messages, signal, onDelta);
    if (!state.acts.length) await load().catch(() => {});
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    // "@Dev pc: abre Archivo y guarda" → that Act operates the window authorized in this chat.
    const pc = /^\s*@([A-Za-z0-9_-]{1,32})\s+(?:pc|computadora)\s*[:,]\s*([\s\S]{1,2000})$/i.exec(String(lastUser?.content || ''));
    const pcAct = pc && state.acts.find(a => a.enabled && [a.collaboration?.mention, a.name].some(n => (n || '').toLowerCase() === pc[1].toLowerCase()));
    if (pcAct) {
      const result = await computerTask(pcAct, pc[2].trim(), {signal});
      const text = computerReport(pcAct, result);
      onDelta(text);
      return {text, reason: 'stop', route: {model: result.model || pcAct.intelligence?.model_id, act_computer_run: result.run_id}};
    }
    const multi = findAllMentions(lastUser?.content);
    if (multi.length >= 2) {
      const t0 = performance.now();
      presence(multi[0], 'working', 'coordina a ' + multi.slice(1).map(a => a.name).join(', ') + '…', chatPresence,
        {startedAt: t0, model: multi.map(a => a.intelligence?.model_id).filter(Boolean).join(' + ')});
      let teamRes;
      try { teamRes = await runTeamFromChat(lastUser.content, null, signal); }
      catch (err) { presence(multi[0], 'failed', signal?.aborted ? 'equipo detenido' : 'el equipo no pudo terminar', chatPresence, {detail: fmtMs(performance.now() - t0)}); throw err; }
      presence(multi[0], 'completed', 'equipo terminado (' + multi.map(a => a.name).join(' → ') + ')', chatPresence,
        {detail: fmtMs(performance.now() - t0) + ' · ' + (teamRes.steps?.length || 0) + ' pasos · ' + (teamRes.run_id || '')});
      onDelta(teamRes.consolidated_text);
      return {text: teamRes.consolidated_text, reason: 'stop', route: {model: multi.map(a => a.intelligence?.model_id).join(' + '), act_team_run: teamRes.run_id}};
    }
    const chosen = localStorage.getItem(chatKey());
    const act = mentioned(lastUser?.content) || multi[0] || state.acts.find(a => a.enabled && a.agent_id === chosen);
    if (!act) return brainChat(p, messages, signal, onDelta);
    return chatAs(act, p, messages, signal, onDelta);
  };

  async function chatAs(act, p, messages, signal, onDelta = () => {}, box = chatPresence) {
    const connect = act.intelligence?.provider_profile_ref === CONNECT;
    const label = '〔' + act.name + '〕 ';
    state.actStates[act.agent_id] = 'working'; markCard(act.agent_id, 'working');
    c.sayStatus?.(act.name + ' está trabajando con ' + modelLabel(act) + '…');
    const clock = {startedAt: performance.now(), model: modelLabel(act)};
    presence(act, 'planning', 'piensa…', box, clock);
    let speaking = false, firstToken = 0;
    try {
      const result = await brainChat({...p, act_id: act.agent_id, act_revision: act.revision, provider: connect ? 'chatgpt' : 'bridge',
        selection_mode: 'manual', model: act.intelligence?.model_id || p.model},
        messages, signal, text => {
          if (!speaking) { speaking = true; firstToken = performance.now() - clock.startedAt; presence(act, 'speaking', 'responde…', box, clock); }
          onDelta(label + text);
        });
      const ms = performance.now() - clock.startedAt, routed = result.route?.act || {};
      state.lastRun[act.agent_id] = {at: Date.now(), ms, ok: true, verified: !!routed.model_verified, model: routed.model || result.route?.model || act.intelligence?.model_id};
      state.actStates[act.agent_id] = 'completed'; markCard(act.agent_id, 'completed');
      presence(act, 'completed', 'respondió', box, {detail: fmtMs(ms) + (firstToken ? ' (primer texto ' + fmtMs(firstToken) + ')' : '')
        + ' · ' + (routed.model_verified ? 'modelo verificado: ' : 'modelo sin verificar: ') + (state.lastRun[act.agent_id].model || '—')});
      if (act.voice && (act.voice.auto_speak || c.data?.prefs?.voiceRead)) {
        pendingActVoice = act.voice;
        if (act.voice.auto_speak && !c.data?.prefs?.mutedAll) c._forceVoiceReplyOnce = true;
      }
      return {...result, text: label + result.text};
    } catch (err) {
      const ms = performance.now() - clock.startedAt;
      state.lastRun[act.agent_id] = {at: Date.now(), ms, ok: false, verified: false, model: act.intelligence?.model_id};
      state.actStates[act.agent_id] = 'failed'; markCard(act.agent_id, 'failed');
      presence(act, 'failed', signal?.aborted ? 'se detuvo' : 'no pudo responder', box,
        {detail: fmtMs(ms) + ' · ' + String(err?.message || err).slice(0, 140)});
      throw err;
    }
  }
  // Live state on an existing card without re-rendering the library.
  function markCard(agentId, live) {
    const card = [...library.children].find(n => n.dataset?.agentId === agentId); if (!card) return;
    card.dataset.state = live;
    const badge = card.querySelector('.axx-acts-state'); if (badge) { badge.dataset.state = live; badge.textContent = STATE_LABEL[live] || live; }
  }
  Axx.acts = {load, mentioned, findAllMentions, runTeamFromChat, chatAs, computerTask, presence, presenceBox, lookImg, get acts() { return state.acts; }, chooseForChat,
    open: () => toggleStudio(true), close: () => toggleStudio(false)};
  void load().catch(() => {});
})(window.Axx);
