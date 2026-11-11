/* Phase 7 presentation layer. It only MOVES controls that other modules own into labelled groups:
   ids, handlers, persistence and permissions stay with their owners. Nothing is cloned or re-created. */
(function (Axx) {
  'use strict'; if (!Axx?.isNative() || Axx.phase7) return;
  const $ = id => document.getElementById(id);
  const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; };
  const relayout = () => Axx.resident?.schedule?.();
  const labelOf = id => $(id)?.closest('label');

  /** A titled group. `body` receives adopted nodes; `more` is its progressive-disclosure drawer. */
  function group(view, key, title, hint, moreLabel) {
    const g = make('section', 'p7-group'); g.dataset.short = title.split(/ (?:e|y) /)[0]; g.id = 'p7-' + key; g.setAttribute('aria-labelledby', g.id + '-title');
    const head = make('header'), h = make('h3', '', title); h.id = g.id + '-title'; head.append(h, make('p', '', hint));
    g.body = make('div', 'p7-body'); g.append(head, g.body);
    if (moreLabel) { const d = make('details', 'p7-more'); d.append(make('summary', '', moreLabel)); d.ontoggle = relayout; g.more = d; g.append(d); }
    view.append(g); return g;
  }
  /** One decision per row: what it does on the left, the existing control(s) on the right. */
  function row(target, title, hint, controls, tone) {
    const r = make('div', 'p7-row' + (tone ? ' p7-' + tone : '') + (controls.filter(n => n && !n.hidden && n.type !== 'file').length > 2 ? ' p7-stack' : '')), copy = make('div', 'p7-copy'), actions = make('div', 'p7-actions');
    copy.append(make('strong', '', title), make('small', '', hint)); actions.append(...controls.filter(Boolean)); r.append(copy, actions); target.append(r); return r;
  }
  /** Collapsed home for a card owned by another module. Opens itself whenever that module scrolls to its card. */
  function fold(target, card, fallback) {
    if (!card || card.closest('.p7-fold')) return;
    if (card.querySelectorAll('button,input,select,textarea').length < 2) return void target.append(card); // a one-button shortcut is already minimal
    const d = make('details', 'p7-fold'), title = card.querySelector(':scope>strong,:scope>h3,:scope>legend,:scope>div>strong')?.textContent || card.textContent.trim() || fallback;
    d.append(make('summary', '', title.trim().slice(0, 60))); d.ontoggle = relayout; target.append(d); d.append(card);
    card.scrollIntoView = function (options) { d.open = true; const g = d.closest('details.p7-more'); if (g) g.open = true; return Element.prototype.scrollIntoView.call(this, options); };
  }
  const main = (...ids) => ids.forEach(id => $(id)?.classList.add('p7-main'));
  const nav = (view, groups) => { const n = make('nav', 'p7-nav'); n.setAttribute('aria-label', 'Secciones');
    for (const g of groups) { const b = make('button', '', g.dataset.short || g.querySelector('h3').textContent); b.type = 'button'; b.onclick = () => g.scrollIntoView({ block: 'start', behavior: 'smooth' }); n.append(b); }
    view.prepend(n); };

  /* ── Sistema y datos ─────────────────────────────────────────────────────────────── */
  const S = $('view-settings'); let settingsGroups = null;
  // Cards other modules add to this view. Unknown newcomers also land in «Conexiones», never out of sight.
  const PERSONAL = ['axx-interface-theme', 'resident-studio', 'reset-layout'];
  function settings() {
    if (!S) return;
    if (!settingsGroups) {
      const loose = [...S.children];
      for (const title of S.querySelectorAll(':scope>.section-title')) title.hidden = true; // replaced by the group headings
      const win = group(S, 'windows', 'Windows e inicio', 'Cómo aparece AXX en tu escritorio y cómo lo llamas.', 'Dock y distribución de ventanas');
      const data = group(S, 'data', 'Datos y almacenamiento', 'Notas, tareas, historial y preferencias viven solo en este equipo.');
      const backup = group(S, 'backup', 'Copias de seguridad', 'Guarda todo AXX en un archivo o recupéralo desde uno.');
      const perf = group(S, 'performance', 'Rendimiento y diagnóstico', 'Ajusta el detalle gráfico y revisa el estado técnico.');
      const links = group(S, 'connections', 'Conexiones e integraciones', 'Teléfono, Telegram, MCP, control del PC y autonomía. Abre solo la que necesites.');
      const personal = group(S, 'personal', 'Personalización', 'Tema, forma y distribución de AXX.');
      settingsGroups = { win, data, backup, perf, links, personal };

      win.body.append(...[$('native-warning'), labelOf('always-top'), labelOf('autostart'), labelOf('shortcut')].filter(Boolean));
      row(win.body, 'Traer AXX', 'Llévalo junto al cursor o devuélvelo a su sitio.', [$('summon-settings'), $('recenter'), $('reset-position')]);
      row(win.body, 'Presentar y ocultar', 'Modo presentación, ocultar el cuerpo o cerrar la aplicación.', [$('presentation'), $('hide-avatar'), $('quit-native')]);
      win.more.append(...[labelOf('dock-placement'), ...loose.filter(n => n.matches('details.panel-info-fold')), $('dock-position-reset'), $('reset-desktop-layout')].filter(Boolean));
      main('summon-settings');

      row(data.body, 'Exportar mis datos', 'Descarga un archivo JSON con todo lo guardado. No borra nada.', [$('export-data')]);
      row(data.body, 'Borrar datos locales', 'Elimina notas, conversación, tareas, temporizador y preferencias. Pide confirmación y no se puede deshacer.', [$('clear-data')], 'danger');
      data.body.append(...loose.filter(n => n.matches('p.micro-copy') && /telemetr/i.test(n.textContent)));
      main('export-data');

      row(backup.body, 'Crear copia completa', 'Un único archivo con tus datos y ajustes para guardarlo donde quieras.', [$('backup-all')]);
      row(backup.body, 'Restaurar desde una copia', 'Reemplaza los datos locales por los del archivo. Pide confirmación antes de reemplazar.', [$('import-all'), $('import-file')], 'caution');
      main('backup-all');

      perf.body.append(...[labelOf('quality'), labelOf('reduced-motion'), labelOf('static-mode'), labelOf('show-label'), S.querySelector('.compat-info')].filter(Boolean));
      perf.append(...[$('toggle-diagnostics'), $('diagnostics')].filter(Boolean)); // the existing button already is the disclosure
      if ($('desktop-runtime')) fold(perf, $('desktop-runtime'), 'Windows · acciones y memoria');

      for (const id of PERSONAL) if ($(id)) personal.body.append($(id));
      for (const empty of S.querySelectorAll(':scope>.quick-row')) if (!empty.children.length) empty.remove(); // their buttons now live in rows
      nav(S, [win, data, backup, perf, links, personal]);
    }
    const { links, personal } = settingsGroups;
    for (const n of [...S.children]) {
      if (n.matches('.p7-group,.p7-nav,.section-title,[hidden]') || n.tagName === 'INPUT') continue;
      if (n.id === 'mcp-settings-shortcut') links.body.prepend(n);            // it scrolls to the MCP card, which opens its fold
      else if (n.tagName === 'BUTTON') personal.body.append(n);
      else if (n.matches('section,fieldset,article')) fold(links.body, n, 'Integración');
      else links.body.append(n);
    }
  }

  /* ── IA y proveedores ────────────────────────────────────────────────────────────── */
  const A = $('view-ai'); let aiBuilt = false, saved = [], testing = false;
  const CAPS = { text: 'Texto', vision: 'Visión', tools: 'Herramientas' };
  /** Reads the owners' state; it never marks anything verified by itself. */
  function aiFacts() {
    const c = Axx.companion, p = c.data.prefs, b = c.brain, automatic = p.selection_mode === 'automatic_free' && p.provider !== 'chatgpt';
    const entry = p.provider === 'bridge' && !automatic ? saved.find(s => s.name === p.apiConnection && s.model === p.model) : null;
    const verified = b.connected && b.inferenceVerified === true;
    const model = automatic ? 'Selección automática' : p.model || 'Sin modelo seleccionado';
    const route = p.provider === 'chatgpt' ? 'Cuenta ChatGPT' : automatic ? 'Rutas gratuitas sin clave' : entry ? entry.name : b.connected ? b.providerName : p.model ? 'Conexión guardada' : 'Los comandos locales siguen disponibles';
    const state = verified ? ['ok', 'Respuesta comprobada'] : b.connected ? ['pending', 'Conectado · respuesta sin comprobar'] : p.model || automatic ? ['off', 'Sin comprobar'] : ['off', 'Sin modelo'];
    const cost = p.provider === 'chatgpt' ? 'Consume la cuota de tu suscripción de ChatGPT.'
      : automatic ? 'Rutas gratuitas de servicios públicos externos. No usa tu saldo.'
      : !entry ? (p.model ? 'Coste sin verificar. Una API externa puede cobrar por uso.' : '—')
      : entry.kind === 'ollama' || entry.cost_evidence === 'direct_local' ? 'Sin coste: el modelo se ejecuta en tu equipo.'
      : entry.billing_allowed ? 'Puede consumir tu saldo o cuota: lo autorizaste en esta conexión.'
      : entry.free_confirmed || entry.cost_evidence === 'free_tier' ? 'Declarada como gratuita. No tiene autorización para usar saldo.'
      : entry.cost_evidence === 'paid' ? 'Marcada como de pago y sin autorización para usar tu saldo.'
      : 'Coste sin verificar. Una API externa puede cobrar por uso.';
    const caps = entry?.capabilities?.length ? entry.capabilities.map(k => CAPS[k] || k).join(' · ') + ' (declaradas' + (entry.tasks?.length ? '; tareas: ' + entry.tasks.join(', ') : '') + ')'
      : p.provider === 'chatgpt' ? 'Texto y herramientas de AXX. La voz usa los motores locales.' : automatic ? 'Se eligen por tarea entre las rutas comprobadas.' : 'Sin declarar. Compruébalas con una tarea real.';
    return { model, route, state, cost, caps };
  }
  function aiRender() {
    if (!aiBuilt) return; const f = aiFacts();
    $('p7-ai-model').textContent = f.model; $('p7-ai-route').textContent = f.route;
    $('p7-ai-state').textContent = f.state[1]; $('p7-ai-state').dataset.state = f.state[0];
    $('p7-ai-cost').textContent = f.cost; $('p7-ai-caps').textContent = f.caps;
    $('gateway-controls').hidden = $('provider-kind').value !== 'freellmapi'; // only the selected platform's own controls
  }
  async function aiTest() {
    const c = Axx.companion, p = c.data.prefs, out = $('p7-ai-result');
    if (testing || c.pending || c.connecting) { out.textContent = 'Espera a que termine la respuesta o la conexión en curso.'; return; }
    out.textContent = 'Comprobando…';
    // A saved API connection has a real inference probe. Its owner disables and restores the view's controls itself.
    if (p.provider === 'bridge' && p.selection_mode !== 'automatic_free' && p.apiConnection && p.model) {
      const probe = $('provider-probe'), refresh = $('provider-refresh');
      // providers.js only loads the saved connections when its tab is clicked; ask it to, then wait for it to settle.
      if (probe.disabled) { refresh.click(); await new Promise(done => { const t = setInterval(() => { if (!refresh.disabled) { clearInterval(t); done(); } }, 40); }); }
      if (!probe.disabled) return probe.click();
    }
    testing = true; $('p7-ai-test').disabled = true;
    try { await c.connect(); const f = aiFacts();    // every other route: the owner's own connection check
      out.textContent = f.state[0] === 'ok' ? 'El modelo respondió en esta sesión.' : c.brain.connected ? 'El servidor responde. La respuesta del modelo se comprobará con tu primera pregunta.' : 'No se pudo conectar. Revisa la conexión elegida abajo.';
    } catch (error) { out.textContent = 'No se comprobó: ' + (error.message || String(error)); }
    finally { testing = false; $('p7-ai-test').disabled = false; aiRender(); }
  }
  function ai() {
    if (!A || !$('provider-probe')) return;              // providers.js builds its panel after startup; retried on open
    if (!aiBuilt) {
      const now = group(A, 'ai-now', 'Modelo en uso', 'Lo que AXX utiliza ahora para responder.');
      now.body.innerHTML = '<div class="p7-ai-head"><div><strong id="p7-ai-model"></strong><small id="p7-ai-route"></small></div><span id="p7-ai-state" role="status"></span></div>'
        + '<dl class="p7-facts"><div><dt>Coste</dt><dd id="p7-ai-cost"></dd></div><div><dt>Capacidades</dt><dd id="p7-ai-caps"></dd></div></dl>'
        + '<div class="p7-actions"><button id="p7-ai-test" class="p7-main" type="button">Probar conexión</button></div><p id="p7-ai-result" role="status" aria-live="polite"></p>';
      now.body.append(...[labelOf('ai-model'), $('ai-status')].filter(Boolean));
      const choose = group(A, 'ai-choose', 'Cambiar o conectar', 'Elige de dónde viene el modelo. Solo verás los controles de esa opción.');
      choose.body.append(A.querySelector('.ai-mode-selector'), $('subpanel-local'), $('subpanel-chatgpt'), $('subpanel-api'));
      const adv = make('details', 'p7-more'); adv.id = 'p7-ai-advanced'; adv.append(make('summary', '', 'Opciones avanzadas')); adv.ontoggle = relayout;
      adv.append(...[labelOf('ai-chat-tools'), labelOf('keep-history'), labelOf('voice-autosend'), A.querySelector(':scope>details.panel-info-fold')].filter(Boolean));
      A.prepend(now); A.append(adv);
      // Choosing an option brings its controls to the top, so the status card never pushes them below the fold.
      const tabs = A.querySelector('.ai-mode-selector'); tabs.addEventListener('click', event => { if (event.target.closest('.ai-mode-btn')) tabs.scrollIntoView({ block: 'start' }); });
      $('p7-ai-test').onclick = aiTest;
      new MutationObserver(() => { $('p7-ai-result').textContent = $('provider-probe-result').textContent; aiRender(); }).observe($('provider-probe-result'), { childList: true, characterData: true, subtree: true });
      const sync = Axx.companion.syncProvider.bind(Axx.companion);
      Axx.companion.syncProvider = (...args) => { const result = sync(...args); aiRender(); return result; };
      A.addEventListener('change', () => queueMicrotask(aiRender)); A.addEventListener('click', () => setTimeout(aiRender, 0));
      aiBuilt = true;
    }
    aiRender();
    Axx.backendRequest('GET', '/axx-api/providers').then(r => { saved = r.providers || []; aiRender(); }).catch(() => {});
  }

  /* ── Personalizar AXX ────────────────────────────────────────────────────────────── */
  // One entry, five tabs. Each tab shows the controls where their owner keeps them; nothing is duplicated.
  const TABS = [['shape', 'Forma', 'Forma y materiales', 'appearance'], ['interface', 'Interfaz', 'Interfaz y colores', 'personalize'],
    ['motion', 'Movimiento', 'Movimiento y presencia', 'personalize'], ['sound', 'Sonidos', 'Sonidos y respuesta', 'sound'], ['agent', 'Personalidad', 'Personalidad e instrucciones del agente', 'agent']];
  const P = make('section', 'panel-view'); P.id = 'view-personalize'; P.hidden = true; $('panel').append(P);
  const tabs = make('nav', 'p7-tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Personalizar AXX');
  let tab = 'interface', personalBuilt = false; const loans = [];
  const go = key => { const t = TABS.find(t => t[0] === key); if (t[3] === 'personalize') tab = key; Axx.companion.openFeature(t[3]); tabs.querySelector('[aria-selected=true]')?.focus(); };
  for (const [key, label, full] of TABS) { const b = make('button', '', label); b.type = 'button'; b.setAttribute('role', 'tab'); b.title = full; b.setAttribute('aria-label', full); b.dataset.p7Tab = key; b.onclick = () => go(key); tabs.append(b); }
  tabs.onkeydown = event => { const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key]; if (!step) return; event.preventDefault();
    const i = TABS.findIndex(t => t[0] === tabs.querySelector('[aria-selected=true]')?.dataset.p7Tab); go(TABS[(i + step + TABS.length) % TABS.length][0]); };
  const link = (label, run) => { const b = make('button', '', label); b.type = 'button'; b.onclick = run; return b; };
  /** A control shown in two entries lives in whichever one is open; a placeholder keeps its place at home. */
  const lend = (node, slot) => { if (!node) return; const home = document.createComment('p7-home'); node.before(home); loans.push({ node, home, slot }); };
  function personal(view) {
    if (!personalBuilt) {
      const face = make('div'); face.dataset.p7Section = 'interface';
      const theme = group(face, 'theme', 'Tema y colores', 'Claro u oscuro, colores, tipografía y widgets. Cada tema guarda su combinación.');
      const layout = group(face, 'layout', 'Paneles y dock', 'Dónde aparecen el dock y las ventanas, y cómo recuperarlos.');
      const dock = labelOf('dock-placement'), help = dock?.nextElementSibling?.matches('details') ? dock.nextElementSibling : null;
      layout.body.append(...[dock, help].filter(Boolean));
      row(layout.body, 'Recuperar posiciones', 'Devuelve el dock, las ventanas y las medidas de los paneles a su sitio.', [$('dock-position-reset'), $('reset-desktop-layout'), $('reset-layout')]);
      const move = make('div'); move.dataset.p7Section = 'motion';
      const motion = group(move, 'motion', 'Movimiento', 'Carácter y expresividad del cuerpo. No cambia la forma.');
      if ($('id20-motion')) motion.body.append($('id20-motion'));
      const calm = group(move, 'calm', 'Menos movimiento', 'Para concentrarte o aligerar el equipo.');
      const presence = group(move, 'presence', 'Presencia', 'Cómo y cuándo se hace notar AXX.');
      row(presence.body, 'Presencia y autonomía', 'Discreto, Copiloto o Full. Se ajusta junto a sus permisos.', [link('Abrir', () => { Axx.companion.openFeature('settings'); $('anticipation-settings')?.scrollIntoView({ block: 'start' }); })]);
      row(presence.body, 'Laboratorio de animaciones', 'Muestras de cada estado. No ejecuta tareas.', [link('Abrir', () => Axx.companion.openFeature('lab'))]);
      P.append(face, move);
      lend($('axx-interface-theme'), theme.body); lend(labelOf('reduced-motion'), calm.body); lend(labelOf('static-mode'), calm.body);
      const more = settingsGroups?.win.more; if (more && more.children.length < 2) more.remove();
      if (settingsGroups) row(settingsGroups.personal.body, 'Personalizar AXX', 'Forma, colores, movimiento, sonidos y personalidad en un solo lugar.', [link('Abrir', () => go('interface'))]).querySelector('button').classList.add('p7-main');
      personalBuilt = true;
    }
    const here = TABS.some(t => t[3] === view);
    for (const { node, home, slot } of loans) if (view === 'personalize') slot.append(node); else if (home.parentNode && node.previousSibling !== home) home.after(node);
    if (!here) return;
    const key = view === 'personalize' ? tab : TABS.find(t => t[3] === view)[0];
    $('view-' + view).prepend(tabs);
    for (const b of tabs.children) { const on = b.dataset.p7Tab === key; b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; }
    for (const s of P.querySelectorAll(':scope>[data-p7-section]')) s.hidden = s.dataset.p7Section !== key;
    if ($('panel-title')) $('panel-title').textContent = 'Personalizar AXX';
  }
  if (!Axx.FEATURES.some(f => f.id === 'personalize')) Axx.FEATURES.push({ id: 'personalize', family: 'settings', title: 'Personalizar AXX', description: 'Forma, interfaz, movimiento, sonidos y personalidad del agente.', view: 'personalize', availability: 'DISPONIBLE · LOCAL' });

  /* ── Wiring ──────────────────────────────────────────────────────────────────────── */
  const arrange = { settings, ai };
  const show = view => { try { arrange[view]?.(); personal(view); } catch (error) { console.error('phase7-ui', error); } };
  const openFeature = Axx.companion.openFeature.bind(Axx.companion);
  Axx.companion.openFeature = function (id) { const result = openFeature(id), view = Axx.FEATURES.find(f => f.id === id)?.view; if (view) show(view); return result; };
  // Views are also opened by the catalog and by other modules; follow whichever one becomes visible.
  new MutationObserver(list => { for (const m of list) if (m.target.classList.contains('panel-view') && !m.target.hidden) show(m.target.id.slice(5)); })
    .observe($('panel'), { attributes: true, attributeFilter: ['hidden'], subtree: true });
  const all = () => { for (const view of Object.keys(arrange)) show(view); show([...$('panel').querySelectorAll(':scope>.panel-view')].find(v => !v.hidden)?.id.slice(5)); };
  Axx.phase7 = { arrange, personalize: go };
  all(); setTimeout(all, 1500); // modules that add their cards after startup
})(window.Axx);
