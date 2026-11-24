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
  const PALETTE_COLORS = [
    ['#0d1117', '#58a6ff', '#1f6feb'], ['#1a1025', '#c084fc', '#9333ea'], ['#081c24', '#38bdf8', '#0284c7'],
    ['#231115', '#fb7185', '#e11d48'], ['#191326', '#a78bfa', '#7c3aed'], ['#071f18', '#34d399', '#059669'],
    ['#211d16', '#fbbf24', '#d97706'], ['#18181b', '#e4e4e7', '#a1a1aa'], ['#050507', '#818cf8', '#4f46e5'],
  ];
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
    actStates: {}, events: [], pendingApprovals: [],
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

  function renderLibrary() {
    library.replaceChildren(...state.acts.map(act => {
      const img = el('img', {alt: 'Vista aproximada de ' + act.name, title:'Vista SVG aproximada; no es una captura del avatar 3D', width: 64, height: 64, src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(act.thumbnail?.svg || '')});
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
        actions);
      card.dataset.state = live;
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

  function renderTeams() {
    teamsBox.replaceChildren();
    teamsBox.append(el('h4', {textContent: 'Equipos de Acts (Act Teams)'}));
    const form = el('form', {className: 'axx-acts-subbox'});
    const titleIn = el('input', {required: true, placeholder: 'Ej. Equipo Engineering & Visual'});
    const purposeIn = el('input', {placeholder: 'Objetivo del equipo (opcional)'});
    const budgetIn = el('input', {type: 'number', value: '5', min: '0.1', step: '0.5'});
    const membersWrap = el('div', {});
    const memberChecks = state.acts.filter(a => a.enabled).map(a => {
      const cb = el('input', {type: 'checkbox', value: a.agent_id});
      const roleSel = el('select', {}, ...options([['lead', 'Coordinador (lead)'], ['member', 'Miembro'], ['reviewer', 'Revisor (QA)']],
        a.name.toLowerCase().includes('qa') ? 'reviewer' : (a.name.toLowerCase().includes('dev') ? 'lead' : 'member')));
      membersWrap.append(el('div', {className: 'quick-row'}, el('label', {}, cb, ' ' + a.name + ' (' + a.role + ') '), roleSel));
      return {cb, roleSel, agent_id: a.agent_id};
    });
    form.append(field('Nombre del equipo', titleIn), field('Objetivo', purposeIn), field('Presupuesto máximo (USD)', budgetIn),
      el('div', {}, el('strong', {textContent: 'Miembros (sin herencia automática de permisos):'}), membersWrap),
      el('button', {type: 'submit', textContent: 'Crear equipo'}));
    form.onsubmit = attempt(async e => {
      e.preventDefault();
      const chosen = memberChecks.filter(m => m.cb.checked).map(m => ({agent_id: m.agent_id, role: m.roleSel.value}));
      if (!chosen.length) throw new Error('Elige al menos un Act habilitado para el equipo.');
      const tid = 'team-' + crypto.randomUUID().slice(0, 8);
      const lead = chosen.find(m => m.role === 'lead')?.agent_id || chosen[0].agent_id;
      await api('POST', 'teams', {team_id: tid, title: titleIn.value.trim(), purpose: purposeIn.value.trim(),
        members: chosen, coordinator_agent_id: lead, budget_usd: Number(budgetIn.value || 5)});
      say('Equipo creado sin elevar permisos individuales.');
      await load();
    });
    teamsBox.append(form);
    for (const t of state.teams) {
      const membersText = (t.members || []).map(m => (state.acts.find(a => a.agent_id === m.agent_id)?.name || m.agent_id) + ' (' + m.role + ')').join(', ');
      const promptIn = el('input', {placeholder: 'Objetivo para ejecutar este equipo…'});
      const runBtn = el('button', {type: 'button', textContent: 'Ejecutar equipo', onclick: attempt(async () => {
        const goal = promptIn.value.trim() || t.purpose || 'Revisar estado actual';
        const res = await runTeamFromChat(goal, t.team_id);
        say(`Equipo «${t.title}» completado (${res.steps.length} pasos). Resultado enviado al chat.`);
      })});
      teamsBox.append(el('article', {className: 'axx-acts-card'}, el('div', {style: 'grid-column:1 / -1'},
        el('strong', {textContent: t.title}), el('small', {textContent: membersText + ' · pres. $' + (t.budget_usd ?? 5)}),
        el('div', {className: 'quick-row'}, promptIn, runBtn))));
    }
  }

  function renderRoutines() {
    routinesBox.replaceChildren();
    routinesBox.append(el('h4', {textContent: 'Rutinas programadas (Scheduler real)'}));
    const form = el('form', {className: 'axx-acts-subbox'});
    const idIn = el('input', {required: true, placeholder: 'Ej. rutina-qa-diaria'});
    const actSel = el('select', {}, ...options(state.acts.filter(a => a.enabled).map(a => [a.agent_id, a.name])));
    const schedIn = el('input', {required: true, value: 'every:60s', placeholder: 'every:60s o 0 9 * * *'});
    const promptIn = el('input', {placeholder: 'Tarea a ejecutar'});
    const reqApp = el('input', {type: 'checkbox', checked: false});
    form.append(field('ID de rutina', idIn), field('Act asignado', actSel), field('Programación', schedIn),
      field('Instrucción', promptIn), field('Pedir aprobación antes de mutar', reqApp),
      el('button', {type: 'submit', textContent: 'Programar rutina'}));
    form.onsubmit = attempt(async e => {
      e.preventDefault();
      if (!actSel.value) throw new Error('Crea y habilita primero un Act.');
      await api('POST', 'routines', {
        routine_id: idIn.value.trim().replace(/[^A-Za-z0-9_.:-]/g, '-'),
        agent_id: actSel.value,
        conversation_id: activeConvId(),
        schedule_spec: schedIn.value.trim(),
        requested_capabilities: ['read_workspace'],
        requires_approval: reqApp.checked,
        prompt_text: promptIn.value.trim(),
        enabled: true,
      });
      say('Rutina programada (micrófono y entrada física bloqueados automáticamente).');
      await load();
    });
    routinesBox.append(form);
    for (const r of state.routines) {
      const row = el('div', {className: 'quick-row'},
        el('span', {textContent: `${r.routine_id} (${r.agent_id}) · ${r.schedule_spec} · ${r.status}`}),
        el('button', {type: 'button', textContent: 'Ejecutar ahora', onclick: attempt(async () => {
          const trig = await api('POST', 'routines/trigger', {routine_id: r.routine_id, proposes_mutation: r.requires_approval});
          say(`Rutina ${r.routine_id}: ${trig.status}${trig.summary ? ' — ' + trig.summary : ''}`);
          await load();
        })}),
        el('button', {type: 'button', textContent: r.enabled ? 'Pausar' : 'Reanudar', onclick: attempt(async () => {
          await api('POST', r.enabled ? 'routines/pause' : 'routines/resume', {routine_id: r.routine_id});
          await load();
        })}),
        el('button', {type: 'button', textContent: 'Cancelar', onclick: attempt(async () => {
          await api('POST', 'routines/cancel', {routine_id: r.routine_id});
          await load();
        })}));
      routinesBox.append(el('article', {className: 'axx-acts-card'}, el('div', {style: 'grid-column:1 / -1'}, row)));
    }
  }

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

  let swatch = null;
  function miniFormSvg(formId, paletteId, mat) {
    const [p0, acc, glw] = PALETTE_COLORS[paletteId] || PALETTE_COLORS[0];
    const name = FORMS[formId] || 'Core';
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
      <rect width="64" height="64" rx="14" fill="${p0}"/>
      <circle cx="32" cy="28" r="18" fill="${glw}" fill-opacity="0.25" stroke="${acc}" stroke-width="2"/>
      <circle cx="32" cy="28" r="${7 + (formId % 9)}" fill="${acc}" fill-opacity="0.85"/>
      <text x="32" y="57" fill="${acc}" font-size="8" text-anchor="middle">${name}</text></svg>`;
  }
  function renderSwatch() {
    if (!swatch) return;
    const a = state.draft.appearance;
    const cached = state.acts.find(x => x.agent_id === state.draft.agent_id && x.appearance.form_id === a.form_id
      && x.appearance.palette_id === a.palette_id && x.appearance.material_preset === a.material_preset)?.thumbnail?.svg;
    swatch.replaceChildren(
      el('div', {innerHTML: cached || miniFormSvg(a.form_id, a.palette_id, a.material_preset)}),
      el('div', {}, el('strong', {textContent: FORMS[a.form_id] + ' · ' + PALETTES[a.palette_id] + ' · ' + a.material_preset}),
        el('small', {textContent: ' Escala ' + (a.scale ?? 1) + '× · El avatar global de AXX no cambia al editar este Act.'})));
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
      case 'appearance': swatch = el('div', {className: 'axx-acts-swatch-box'}); setTimeout(renderSwatch);
        return [field('Forma', control('appearance.form_id', 'select', {pairs: FORMS.map((f, i) => [i, f]), number: true})),
          field('Paleta', control('appearance.palette_id', 'select', {pairs: PALETTES.map((p, i) => [i, p]), number: true})),
          field('Material', control('appearance.material_preset', 'select', {pairs: MATERIALS.map(m => [m, m.replace(/_/g, ' ')])})),
          field('Escala', control('appearance.scale', 'number', {number: true, attrs: {min: 0.1, max: 2, step: 0.1}})),
          field('Intensidad de animación', control('appearance.animation_intensity', 'number', {number: true, attrs: {min: 0, max: 2, step: 0.1}})),
          field('Reacción al pensar', control('appearance.reactions.thinking', 'text', {attrs: {placeholder: 'pulse_focus'}})),
          field('Reacción ejecutando herramientas', control('appearance.reactions.working', 'text', {attrs: {placeholder: 'orbit_spin'}})),
          field('Reducir animación', control('appearance.reduce_motion', 'checkbox')), swatch];
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
    chatWho.dataset.act = chosen ? 'true' : 'false';
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
            el('img',{alt:'Vista aproximada de '+act.name,title:'Vista SVG aproximada; no es una captura del avatar 3D',width:40,height:40,
              src:'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(act.thumbnail?.svg||'')}),
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

  async function runTeamFromChat(promptText, teamId = null, signal = null) {
    c.sayStatus?.('Coordinando equipo de Acts…');
    if (signal?.aborted) throw new DOMException('Equipo cancelado', 'AbortError');
    const runId = 'teamrun-' + crypto.randomUUID();
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
    }); } finally { signal?.removeEventListener('abort', cancel); }
    if (signal?.aborted) throw new DOMException('Equipo cancelado; revisa los efectos en Actividad', 'AbortError');
    if (file && res.work) await Axx.codeStudio.showTeamResult(res, file, true).catch(() => {});
    await refreshActivity();
    if (c.message && teamId) {
      c.message('assistant', res.consolidated_text, 'local');
      c.renderChat?.(); c.save?.();
    }
    return res;
  }

  const brainChat = c.brain.chat.bind(c.brain);
  c.brain.chat = async function (p, messages, signal, onDelta = () => {}) {
    if (!p.prompt_mode || p.act_id) return brainChat(p, messages, signal, onDelta);
    if (!state.acts.length) await load().catch(() => {});
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    const multi = findAllMentions(lastUser?.content);
    if (multi.length >= 2) {
      const teamRes = await runTeamFromChat(lastUser.content, null, signal);
      onDelta(teamRes.consolidated_text);
      return {text: teamRes.consolidated_text, reason: 'stop', route: {model: multi.map(a => a.intelligence?.model_id).join(' + '), act_team_run: teamRes.run_id}};
    }
    const chosen = localStorage.getItem(chatKey());
    const act = mentioned(lastUser?.content) || multi[0] || state.acts.find(a => a.enabled && a.agent_id === chosen);
    if (!act) return brainChat(p, messages, signal, onDelta);
    return chatAs(act, p, messages, signal, onDelta);
  };

  async function chatAs(act, p, messages, signal, onDelta = () => {}) {
    const connect = act.intelligence?.provider_profile_ref === CONNECT;
    const label = '〔' + act.name + '〕 ';
    state.actStates[act.agent_id] = 'working';
    c.sayStatus?.(act.name + ' está trabajando con ' + modelLabel(act) + '…');
    try {
      const result = await brainChat({...p, act_id: act.agent_id, act_revision: act.revision, provider: connect ? 'chatgpt' : 'bridge',
        selection_mode: 'manual', model: act.intelligence?.model_id || p.model},
        messages, signal, text => onDelta(label + text));
      state.actStates[act.agent_id] = 'completed';
      if (act.voice && (act.voice.auto_speak || c.data?.prefs?.voiceRead)) {
        pendingActVoice = act.voice;
        if (act.voice.auto_speak && !c.data?.prefs?.mutedAll) c._forceVoiceReplyOnce = true;
      }
      return {...result, text: label + result.text};
    } catch (err) {
      state.actStates[act.agent_id] = 'failed';
      throw err;
    }
  }
  Axx.acts = {load, mentioned, findAllMentions, runTeamFromChat, chatAs, get acts() { return state.acts; }, chooseForChat, open: () => toggleStudio(true), close: () => toggleStudio(false)};
  void load().catch(() => {});
})(window.Axx);
