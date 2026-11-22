/* Acts Studio and Act selection in the existing chat (Evolution 3.1).
 * Profiles live in the existing AgentRegistry (/axx-api/agents/v1/*); turns go through the existing chat
 * clients with act_id, and the backend resolves the Act's own provider/model. The global AXX avatar,
 * profile and selected model are never written here. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative?.() || !Axx.companion || !document.getElementById('view-agent')) return;
  const c = Axx.companion;
  const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/agents/v1/' + path, body);
  const CONNECT = 'axx-connect', TOOL = 'axx.commands';
  const FORMS = ['Core', 'Flow', 'Pearl', 'Torus', 'Split', 'Wave', 'Bloom', 'Fold', 'Spike', 'Drift', 'Orbit', 'Morph',
    'Cushion', 'Trefoil', 'Nova', 'Heart', 'Infinity', 'Helix', 'Knot', 'Petal', 'Prism', 'Capsule', 'Crescent', 'Ripple'];
  const PALETTES = ['Obsidian', 'Nebula', 'Ocean', 'Sunset', 'Amethyst', 'Emerald', 'Champagne', 'Silver', 'Void'];
  const MATERIALS = ['obsidian', 'optical_glass', 'iridescent_pearl', 'brushed_titanium', 'velvet_matte', 'bioluminescent_gel'];
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

  const state = {acts: [], providers: [], draft: null, base: '', grants: [], toolGrant: false, tab: 'identity'};
  const host = el('section', {className: 'axx-acts-studio', hidden: true});
  const status = el('p', {className: 'axx-acts-status', role: 'status', ariaLive: 'polite'});
  const library = el('div', {className: 'axx-acts-library', role: 'list', ariaLabel: 'Biblioteca de Acts'});
  const editor = el('form', {className: 'axx-acts-editor', hidden: true, noValidate: false});
  const preview = el('pre', {className: 'axx-acts-preview', tabIndex: 0, hidden: true});
  const importInput = el('input', {type: 'file', accept: 'application/json', hidden: true});
  const entry = el('button', {type: 'button', className: 'axx-code-entry', textContent: 'Abrir Acts'});
  host.append(el('h3', {textContent: 'Acts'}), status,
    el('div', {className: 'quick-row'}, el('button', {type: 'button', textContent: 'Crear Act', onclick: () => edit(null)}),
      el('button', {type: 'button', textContent: 'Importar perfil', onclick: () => importInput.click()})),
    library, editor, preview, importInput);
  document.getElementById('view-agent').append(entry, host);
  document.head.append(el('link', {rel: 'stylesheet', href: 'scripts/agents/acts-studio.css'}));
  const say = text => { status.textContent = text; };
  const attempt = task => async (...args) => { try { await task(...args); } catch (e) { say(e?.message || String(e)); } };
  const dirty = () => !!state.draft && JSON.stringify(state.draft) !== state.base;

  entry.onclick = attempt(async () => {
    if (!host.hidden && dirty() && !confirm('Hay cambios sin guardar en el Act. ¿Cerrar y descartarlos?')) return;
    host.hidden = !host.hidden; entry.textContent = host.hidden ? 'Abrir Acts' : 'Cerrar Acts';
    if (host.hidden) { editor.hidden = true; state.draft = null; } else await load();
    Axx.resident?.schedule?.();
  });
  window.addEventListener('beforeunload', e => { if (dirty()) { e.preventDefault(); e.returnValue = ''; } });

  const flagButton = el('button', {type: 'button', hidden: true});
  host.querySelector('.quick-row').append(flagButton);
  async function load() {
    const [profiles, providers, flags] = await Promise.all([api('GET', 'profiles?include_disabled=true'),
      Axx.backendRequest('GET', '/axx-api/providers').catch(() => ({providers: []})), api('GET', 'flags').catch(() => ({flags: []}))]);
    state.acts = profiles.profiles || [];
    // New capabilities start off; only the owner's explicit click enables them.
    const flag = (flags.flags || []).find(f => f.flag_id === 'agent_profiles_v1');
    flagButton.hidden = !flag;
    if (flag) {
      flagButton.textContent = flag.enabled ? 'Desactivar Acts' : 'Activar Acts';
      flagButton.onclick = attempt(async () => {
        await api('POST', 'flags/set', {flag_id: flag.flag_id, enabled: !flag.enabled, expected_revision: flag.revision, reason: 'owner_acts_studio'});
        await load(); say(flag.enabled ? 'Acts desactivados: el chat vuelve a responder solo como AXX.' : 'Acts activados.');
      });
      if (!flag.enabled) say('Acts está desactivado. Actívalo para crear Acts y conversar con ellos.');
    }
    state.providers = (providers.providers || []).filter(p => p.enabled && !p.candidate_only);
    renderLibrary(); syncChatSelect();
  }

  function modelLabel(act) {
    const i = act.intelligence || {};
    if (i.route === 'policy') return 'Automático gratis';
    return i.provider_profile_ref ? (i.provider_profile_ref === CONNECT ? 'ChatGPT · ' : i.provider_profile_ref + ' · ') + (i.model_id || 'sin modelo') : 'Sin modelo';
  }

  function renderLibrary() {
    library.replaceChildren(...state.acts.map(act => {
      const img = el('img', {alt: '', width: 56, height: 56, src: 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(act.thumbnail?.svg || '')});
      const actions = el('div', {className: 'quick-row'},
        el('button', {type: 'button', textContent: 'Usar en el chat', disabled: !act.enabled, onclick: () => { chooseForChat(act.agent_id); say(act.name + ' responderá en este chat.'); }}),
        el('button', {type: 'button', textContent: 'Personalizar', onclick: attempt(() => edit(act))}),
        el('button', {type: 'button', textContent: 'Duplicar', onclick: attempt(() => edit(act, true))}),
        el('button', {type: 'button', textContent: act.enabled ? 'Deshabilitar' : 'Habilitar', onclick: attempt(() => toggle(act))}),
        el('button', {type: 'button', textContent: 'Exportar', onclick: attempt(() => exportAct(act))}));
      return el('article', {className: 'axx-acts-card', role: 'listitem', ariaLabel: act.name}, img,
        el('div', {}, el('strong', {textContent: act.name}), el('span', {textContent: ' · ' + act.role}),
          el('small', {textContent: modelLabel(act) + ' · ' + (act.enabled ? 'Activo' : 'Deshabilitado') + ' · rev. ' + act.revision
            + ' · ' + FORMS[act.appearance.form_id] + ' / ' + PALETTES[act.appearance.palette_id]})), actions);
    }));
    if (!state.acts.length) library.append(el('p', {textContent: 'Todavía no hay Acts. Crea uno para asignarle un modelo y trabajar con él desde el chat.'}));
  }

  function blank() {
    return {schema_version: '1.0', name: '', role: '', description: '', instructions: '', enabled: true,
      appearance: {form_id: 0, palette_id: 0, material_preset: 'obsidian', scale: 1, reduce_motion: false},
      intelligence: {route: 'manual', fallback: 'none', max_parallel_turns: 1},
      voice: {language: 'es-DO', auto_speak: false, speed: 1},
      workspace: {runtime: 'none', foreground_policy: 'deny', allowed_roots: []},
      permissions: {tool_grant_refs: [], delegation_enabled: false, max_delegate_depth: 0},
      limits: {max_concurrent_jobs: 1, max_retries: 0, max_cost_usd: 0}, memory_scope: 'agent',
      personality: {}, autonomy: {mode: 'manual'}, collaboration: {}};
  }
  const EDITABLE = ['name', 'role', 'description', 'instructions', 'enabled', 'appearance', 'intelligence', 'voice', 'workspace',
    'limits', 'memory_scope', 'personality', 'autonomy', 'collaboration'];

  async function edit(act, duplicate = false) {
    if (dirty() && !confirm('Hay cambios sin guardar. ¿Descartarlos?')) return;
    const base = blank();
    if (act) for (const k of EDITABLE) if (act[k] !== undefined) base[k] = structuredClone(act[k]);
    if (act && !duplicate) { base.agent_id = act.agent_id; base.revision = act.revision; }
    if (duplicate) { base.name = (act.name + ' (copia)').slice(0, 80); base.enabled = false; }  // copies never inherit grants
    state.grants = act && !duplicate ? (await api('GET', 'profiles/permissions?agent_id=' + encodeURIComponent(act.agent_id))).permissions : [];
    state.toolGrant = state.grants.some(g => g.tool_id === TOOL && g.approval_mode !== 'deny');
    base.toolGrant = state.toolGrant;
    state.draft = base; state.base = JSON.stringify(base); state.tab = 'identity';
    preview.hidden = true; renderEditor();
  }

  function control(path, kind, extra = {}) {
    const value = get(state.draft, path);
    let input;
    if (kind === 'select') input = el('select', {}, ...options(extra.pairs, value));
    else if (kind === 'textarea') input = el('textarea', {value: value ?? '', rows: extra.rows || 3, maxLength: extra.max || 2000});
    else if (kind === 'checkbox') input = el('input', {type: 'checkbox', checked: !!value});
    else {
      const {list, ...attrs} = extra.attrs || {};  // `list` is a read-only DOM property; it must be an attribute
      input = el('input', {type: kind, value: value ?? '', ...attrs});
      if (list) input.setAttribute('list', list);
    }
    input.dataset.path = path;
    input.addEventListener('input', () => {
      let v = kind === 'checkbox' ? input.checked : input.value;
      if (extra.number && v !== '') v = Number(v);
      set(state.draft, path, v);
      if (path === 'intelligence.provider_profile_ref' && v !== CONNECT) {  // router routes pin one model per provider
        const p = state.providers.find(x => x.name === v); if (p) set(state.draft, 'intelligence.model_id', p.model);
        renderEditor();
      } else if (path.startsWith('appearance.')) renderSwatch();
      markDirty();
    });
    if (kind === 'checkbox') input.addEventListener('change', () => input.dispatchEvent(new Event('input')));
    return input;
  }

  let swatch = null;
  function renderSwatch() {
    if (!swatch) return;
    const a = state.draft.appearance;
    swatch.textContent = 'Vista previa: ' + FORMS[a.form_id] + ' · ' + PALETTES[a.palette_id] + ' · ' + a.material_preset
      + ' (la miniatura del catálogo se genera al guardar; el avatar principal de AXX no cambia).';
  }
  const markDirty = () => { editor.querySelector('.axx-acts-dirty').textContent = dirty() ? 'Cambios sin guardar' : 'Sin cambios'; };

  function panel(id) {
    const d = state.draft, pairs = obj => Object.entries(obj);
    switch (id) {
      case 'identity': return [field('Nombre', control('name', 'text', {attrs: {maxLength: 80, required: true}})),
        field('Nombre corto para @menciones', control('collaboration.mention', 'text', {attrs: {pattern: '[A-Za-z0-9_-]{1,32}', placeholder: 'Dev'}})),
        field('Especialidad / rol', control('role', 'text', {attrs: {maxLength: 240, required: true}})),
        field('Descripción y objetivo', control('description', 'textarea', {max: 2000})),
        field('Instrucciones persistentes', control('instructions', 'textarea', {max: 16000, rows: 6}))];
      case 'appearance': swatch = el('p', {className: 'axx-acts-swatch'}); setTimeout(renderSwatch);
        return [field('Forma', control('appearance.form_id', 'select', {pairs: FORMS.map((f, i) => [i, f]), number: true})),
          field('Paleta', control('appearance.palette_id', 'select', {pairs: PALETTES.map((p, i) => [i, p]), number: true})),
          field('Material', control('appearance.material_preset', 'select', {pairs: MATERIALS.map(m => [m, m.replace(/_/g, ' ')])})),
          field('Escala', control('appearance.scale', 'number', {number: true, attrs: {min: 0.1, max: 2, step: 0.1}})),
          field('Reducir animación', control('appearance.reduce_motion', 'checkbox')), swatch];
      case 'intelligence': {
        const router = state.providers.map(p => [p.name, p.name + ' · ' + p.model]);
        const isConnect = d.intelligence.provider_profile_ref === CONNECT;
        const models = el('datalist', {id: 'axx-acts-connect-models'}, ...[...(document.getElementById('ai-model')?.options || [])].map(o => new Option(o.value)));
        return [field('Selección', control('intelligence.route', 'select', {pairs: [['manual', 'Manual: este proveedor y modelo'], ['policy', 'Automática gratuita del router']]})),
          field('Proveedor', control('intelligence.provider_profile_ref', 'select', {pairs: [['', '—'], ...router, [CONNECT, 'Axx Connect · ChatGPT']]})),
          field('Modelo', control('intelligence.model_id', 'text', {attrs: {readOnly: !isConnect, list: 'axx-acts-connect-models', maxLength: 180}})), models,
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
      case 'voice': return [field('Idioma', control('voice.language', 'text', {attrs: {maxLength: 48}})),
        field('Velocidad', control('voice.speed', 'number', {number: true, attrs: {min: 0.5, max: 2, step: 0.05}})),
        field('Hablar respuestas automáticamente', control('voice.auto_speak', 'checkbox')),
        el('p', {textContent: 'Usa los servicios de voz existentes. El micrófono nunca se activa sin tu permiso.'})];
      case 'memory': return [field('Alcance', control('memory_scope', 'select', {pairs: [['conversation', 'Solo esta conversación'], ['agent', 'Privada del Act'],
        ['project', 'Proyecto'], ['explicit_shared', 'Compartida explícitamente']]}))];
      case 'tools': return [field('Comandos AXX (cada acción sigue pidiendo su aprobación)', control('toolGrant', 'checkbox')),
        el('p', {textContent: 'Sin este permiso el Act conversa y propone, pero no recibe herramientas. Revocarlo bloquea la siguiente acción.'})];
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
        field('Gasto máximo (USD)', control('limits.max_cost_usd', 'number', {number: true, attrs: {min: 0, step: 0.01}}))];
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
      el('div', {className: 'quick-row'}, el('button', {type: 'submit', textContent: 'Aplicar y verificar'}),
        el('button', {type: 'button', textContent: 'Descartar', onclick: () => { if (!dirty() || confirm('¿Descartar los cambios?')) { state.draft = null; editor.hidden = true; } }}),
        el('span', {className: 'axx-acts-dirty', role: 'status'})));
    markDirty();
  }

  editor.onsubmit = attempt(async e => {
    e.preventDefault();
    if (!editor.reportValidity()) return;
    const d = structuredClone(state.draft), wantsTool = !!d.toolGrant; delete d.toolGrant;
    for (const k of ['personality', 'collaboration']) if (d[k] && !Object.keys(d[k]).length) delete d[k];
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
    // Verify persistence by reading the stored profile back, not by trusting the form.
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

  // ---- Chat: choose an Act per conversation, or mention it with @ ----
  const chatKey = () => 'axx.acts.chat.' + (Axx.chatWorkspace?.active?.id || 'default');
  const chatSelect = el('select', {className: 'axx-acts-chat-select', ariaLabel: 'Quién responde en este chat', title: 'Quién responde en este chat'});
  document.querySelector('#chat-form .composer-bottom > div')?.append(chatSelect);
  chatSelect.onchange = () => chooseForChat(chatSelect.value);
  document.getElementById('chat-input')?.addEventListener('focus', () => syncChatSelect());
  function chooseForChat(actId) { if (actId) localStorage.setItem(chatKey(), actId); else localStorage.removeItem(chatKey()); syncChatSelect(); }
  function syncChatSelect() {
    const chosen = localStorage.getItem(chatKey()) || '';
    chatSelect.replaceChildren(...options([['', 'AXX'], ...state.acts.filter(a => a.enabled).map(a => [a.agent_id, a.name])], chosen));
  }
  function mentioned(text) {
    const m = /^\s*@([\p{L}\p{N}_-]{1,32})\b/u.exec(String(text || ''));
    if (!m) return null;
    const name = m[1].toLowerCase();
    return state.acts.find(a => a.enabled && ((a.collaboration?.mention || '').toLowerCase() === name || a.name.toLowerCase() === name)) || null;
  }
  const brainChat = c.brain.chat.bind(c.brain);
  c.brain.chat = async function (p, messages, signal, onDelta = () => {}) {
    if (!p.prompt_mode || p.act_id) return brainChat(p, messages, signal, onDelta);  // translations and nested calls pass through
    if (!state.acts.length) await load().catch(() => {});
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    const chosen = localStorage.getItem(chatKey());
    const act = mentioned(lastUser?.content) || state.acts.find(a => a.enabled && a.agent_id === chosen);
    if (!act) return brainChat(p, messages, signal, onDelta);
    const connect = act.intelligence?.provider_profile_ref === CONNECT;
    const label = '〔' + act.name + '〕 ';
    c.sayStatus?.(act.name + ' está trabajando con ' + modelLabel(act) + '…');
    const result = await brainChat({...p, act_id: act.agent_id, act_revision: act.revision, provider: connect ? 'chatgpt' : 'bridge',
      selection_mode: 'manual', model: act.intelligence?.model_id || p.model},
      messages, signal, text => onDelta(label + text));
    return {...result, text: label + result.text};
  };
  Axx.acts = {load, mentioned, get acts() { return state.acts; }, chooseForChat};
  void load().catch(() => {});
})(window.Axx);
