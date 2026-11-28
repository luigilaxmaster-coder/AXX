/* Direct-session presentation over the existing authenticated Connect transport.
 * Provider clients retain session ownership. No credentials, executor or chat runtime here.
 */
(function (Axx) {
  'use strict';
  const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'unknown', 'limit_reached']);
  function element(tag, cls, text) {
    const node = document.createElement(tag); if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text; return node;
  }
  const PROVIDER_META = {
    codex: { label: 'Codex', hint: 'Tu sesión local de Codex' },
    claude: { label: 'Claude Code', hint: 'Sesión local CLI' },
    antigravity: { label: 'Antigravity', hint: 'Requiere CLI conectado' }
  };
  function iconSvg(kind, size = 14) {
    const paths = {
      folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
      thread: 'M5 6h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3v-3H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
      mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M9 22h6',
      send: 'M12 19V5m0 0-6 6m6-6 6 6',
      refresh: 'M3 12a9 9 0 0 1 15.5-6.3L21 8m0-5v5h-5M21 12a9 9 0 0 1-15.5 6.3L3 16m0 5v-5h5',
      chevron: 'm6 9 6 6 6-6',
      spark: 'M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z'
    };
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) svg.setAttribute(k, String(v));
    const p = document.createElementNS(svg.namespaceURI, 'path');
    p.setAttribute('d', paths[kind] || paths.thread);
    svg.append(p);
    return svg;
  }
  function createSurface() {
    const root = element('section', 'notch-chat-surface'); root.setAttribute('aria-label', 'Chat directo con tus aplicaciones');
    const main = element('div', 'notch-chat-main');
    const hero = element('header', 'notch-chat-hero');
    const heroCopy = element('div', 'notch-chat-hero-copy');
    const heroPill = element('div', 'notch-hero-pill');
    const heroDot = element('span', 'notch-hero-dot'); heroDot.setAttribute('aria-hidden', 'true');
    const heroState = element('span', '', 'Listo');
    heroPill.append(heroDot, element('span', 'notch-eyebrow', 'CHAT DIRECTO'), heroState);
    heroCopy.append(heroPill, element('h2', '', 'Continúa en tu sesión.'), element('p', 'notch-muted', 'Proyecto y conversación directa, sin cambiar de ventana.'));
    const avatarStage = element('div', 'notch-chat-avatar-stage');
    const portrait = element('img', 'notch-avatar-portrait notch-chat-portrait'); portrait.alt = ''; portrait.setAttribute('aria-hidden', 'true'); portrait.hidden = true; portrait.draggable = false;
    avatarStage.append(portrait);
    hero.append(heroCopy, avatarStage);
    const providers = element('div', 'notch-chat-providers'); providers.setAttribute('aria-label', 'Aplicación de destino');
    const label = element('div', 'notch-chat-caption', 'Una conversación, sin cambiar de ventana.');
    const selectors = element('div', 'notch-chat-selectors');
    const projectLabel = element('div', 'notch-context-field'); const project = element('select', 'notch-field'); project.setAttribute('aria-label', 'Proyecto del chat directo');
    const sessionLabel = element('div', 'notch-context-field'); const session = element('select', 'notch-field'); session.setAttribute('aria-label', 'Conversación del chat directo');
    const projHead = element('span', 'notch-context-caption'); projHead.append(iconSvg('folder', 11), element('span', '', 'PROYECTO'));
    const sessHead = element('span', 'notch-context-caption'); sessHead.append(iconSvg('thread', 11), element('span', '', 'CONVERSACIÓN'));
    projectLabel.append(projHead); sessionLabel.append(sessHead);
    projectLabel.append(project); sessionLabel.append(session); selectors.append(projectLabel, sessionLabel);
    const moreSessions = element('button', 'notch-more-sessions', 'Ver más'); moreSessions.type = 'button'; moreSessions.hidden = true; moreSessions.setAttribute('aria-label', 'Cargar más conversaciones'); sessionLabel.append(moreSessions);
    const quota = element('div', 'notch-chat-quota'); quota.setAttribute('aria-label', 'Saldo del plan');
    const output = element('div', 'notch-chat-output'); output.setAttribute('role', 'log'); output.setAttribute('aria-live', 'polite');
    const response = element('p', 'notch-chat-response'); output.append(response);
    const status = element('p', 'notch-muted notch-chat-status'); status.setAttribute('role', 'status');
    const form = element('form', 'notch-chat-composer');
    const input = element('textarea', 'notch-chat-input'); input.id = 'notch-chat-input'; input.rows = 2; input.maxLength = 32000;
    input.placeholder = '¿En qué seguimos?'; input.setAttribute('aria-label', 'Mensaje al chat seleccionado');
    const controls = element('div', 'notch-row-between');
    const dictation = element('button', 'notch-mode-link notch-chat-mic-btn'); dictation.type = 'button';
    dictation.append(iconSvg('mic', 13), element('span', '', 'Dictar'));
    const send = element('button', 'notch-pill-btn notch-chat-send-btn', 'Enviar'); send.type = 'submit'; send.dataset.primary = 'true';
    const cancel = element('button', 'notch-mode-link', 'Detener'); cancel.type = 'button'; cancel.hidden = true;
    const refresh = element('button', 'notch-mode-link notch-refresh-btn'); refresh.type = 'button'; refresh.setAttribute('aria-label', 'Actualizar conversaciones y saldo');
    refresh.append(iconSvg('refresh', 12), element('span', '', 'Actualizar'));
    const actions = element('div', 'notch-actions-row'); actions.append(cancel, send);
    const inputTools = element('div', 'notch-chat-input-tools'); inputTools.append(dictation, element('span', 'notch-key-hint', '↵ Intro para enviar'));
    controls.append(inputTools, actions); form.append(input, controls);
    const quotaGroup = element('section', 'notch-plan');
    const planHead = element('div', 'notch-plan-heading'); planHead.append(element('span', 'notch-eyebrow', 'TU PLAN'), refresh); quotaGroup.append(planHead, quota);
    main.append(hero, providers, selectors, label, quotaGroup, output, form, status); root.append(main);
    let provider = 'codex', sessions = [], selected = null, listing = false, activeRun = null, visible = false, privateMode = false;
    let refreshEpoch = 0, pendingPoll = 0, quotaAt = 0, quotaLoading = false, loadingStarted = false, captureBinding = null;
    const drafts = new Map(), requests = new Map();
    let nextCursor = null;
    let reconciliationNeeded = false;
    const pickerDialog = element('section', 'notch-picker-dialog'); pickerDialog.hidden = true;
    pickerDialog.setAttribute('role', 'dialog'); pickerDialog.setAttribute('aria-modal', 'true'); pickerDialog.setAttribute('aria-label', 'Elegir destino de conversación');
    const pickerHeader = element('div', 'notch-row-between'); const pickerTitle = element('h3', 'notch-title-md');
    const pickerClose = element('button', 'notch-mode-link', 'Volver'); pickerClose.type = 'button'; pickerHeader.append(pickerTitle, pickerClose);
    const pickerSearch = element('input', 'notch-picker-search'); pickerSearch.type = 'search'; pickerSearch.placeholder = 'Buscar…'; pickerSearch.setAttribute('aria-label', 'Filtrar destinos');
    const pickerList = element('div', 'notch-picker-list'); pickerList.setAttribute('role', 'listbox'); pickerList.setAttribute('aria-label', 'Destinos disponibles');
    pickerList.id = 'notch-destination-options'; pickerSearch.setAttribute('role', 'combobox'); pickerSearch.setAttribute('aria-controls', pickerList.id); pickerSearch.setAttribute('aria-autocomplete', 'list'); pickerSearch.setAttribute('aria-expanded', 'true');
    pickerDialog.append(pickerHeader, pickerSearch, pickerList); root.append(pickerDialog);
    const pickers = [];
    let currentPicker = null, pickerIndex = 0;
    function closePicker(restore = true) {
      const previous = currentPicker; currentPicker = null; pickerDialog.hidden = true; main.inert = false;
      if (previous) { previous.button.setAttribute('aria-expanded', 'false'); if (restore && previous.button.isConnected) previous.button.focus(); }
    }
    function renderPicker() {
      if (!currentPicker) return;
      const query = pickerSearch.value.toLocaleLowerCase();
      const options = [...currentPicker.select.options].filter(option => !option.disabled && option.value && option.text.toLocaleLowerCase().includes(query));
      pickerIndex = Math.min(pickerIndex, Math.max(0, options.length - 1)); pickerList.replaceChildren();
      options.forEach((option, index) => {
        const row = element('button', 'notch-picker-option'); row.type = 'button'; row.setAttribute('role', 'option'); row.setAttribute('aria-selected', String(option.selected)); row.dataset.active = String(index === pickerIndex);
        row.id = `notch-destination-${index}`; row.tabIndex = -1;
        row.append(element('span', '', option.text), element('small', 'notch-muted', option.selected ? 'Actual' : 'Elegir'));
        row.addEventListener('click', () => { const select = currentPicker.select; closePicker(); select.value = option.value; select.dispatchEvent(new Event('change', { bubbles: true })); }); pickerList.append(row);
      });
      if (!options.length) pickerList.append(element('p', 'notch-muted', 'No hay coincidencias. Prueba otro nombre.'));
      if (options.length) pickerSearch.setAttribute('aria-activedescendant', `notch-destination-${pickerIndex}`); else pickerSearch.removeAttribute('aria-activedescendant');
      pickerList.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
    }
    function addPicker(select, host, name) {
      select.hidden = true; select.tabIndex = -1;
      const button = element('button', 'notch-context-picker'); button.type = 'button'; button.setAttribute('aria-label', name); button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-expanded', 'false');
      const value = element('strong'); button.append(value, element('span', 'notch-picker-chevron', '⌄')); host.append(button);
      const item = { select, button, value, name }; pickers.push(item);
      button.addEventListener('click', () => { if (select.disabled) return; currentPicker = item; pickerTitle.textContent = name; pickerSearch.value = ''; pickerIndex = 0; pickerDialog.hidden = false; main.inert = true; button.setAttribute('aria-expanded', 'true'); renderPicker(); pickerSearch.focus(); });
    }
    addPicker(project, projectLabel, 'Cambiar proyecto'); addPicker(session, sessionLabel, 'Cambiar conversación');
    pickerClose.addEventListener('click', () => closePicker());
    pickerSearch.addEventListener('input', () => { pickerIndex = 0; renderPicker(); });
    pickerDialog.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closePicker(); }
      if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); const count = pickerList.querySelectorAll('button').length; pickerIndex = Math.max(0, Math.min(count - 1, pickerIndex + (event.key === 'ArrowDown' ? 1 : -1))); renderPicker(); }
      if (event.key === 'Enter' && document.activeElement === pickerSearch) { event.preventDefault(); pickerList.querySelector('[data-active="true"]')?.click(); }
      if (event.key === 'Tab') {
        const items = [...pickerDialog.querySelectorAll('button,input')].filter(node => !node.disabled && node.tabIndex !== -1); const first = items[0], last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
    const api = async (method, path, body) => {
      try { return await Axx.backendRequest(method, '/axx-api/connect/' + path, body); }
      catch (value) {
        const message = typeof value === 'string' ? value : value?.message || 'No se pudo consultar AXX.';
        throw Object.assign(new Error(message), { code: value?.code || /^([A-Z_]+):/.exec(message)?.[1] });
      }
    };
    const key = () => `${provider}:${selected?.id || ''}`;
    const remember = () => { if (selected) drafts.set(key(), input.value); };
    const capture = { state: 'idle',
      onState() {
        const busy = ['starting', 'listening', 'stopping'].includes(this.state);
        const dSpan = dictation.querySelector('span');
        const labelText = this.state === 'listening' ? 'Terminar dictado' : busy ? 'Cancelar dictado' : 'Dictar';
        if (dSpan) dSpan.textContent = labelText; else dictation.textContent = labelText;
        dictation.setAttribute('aria-pressed', String(busy));
        if (busy) status.textContent = 'Micrófono activo · el texto quedará en el borrador.';
        syncControls();
      },
      onFinal(text) {
        if (!captureBinding || captureBinding.key !== key() || !visible || input.value !== captureBinding.prefix) return;
        input.value = captureBinding.prefix + (captureBinding.prefix ? ' ' : '') + text;
        remember(); status.textContent = 'Dictado listo. Revisa el texto antes de enviar.'; syncControls();
      },
      onError(message) { status.textContent = message; syncControls(); }, onInterim() {}, onEnded() { captureBinding = null; syncControls(); }
    };
    if (Axx.nativeVoice?.attach) Axx.nativeVoice.attach(capture, { preempt: false });
    else { dictation.disabled = true; dictation.title = 'El dictado requiere el servicio de voz nativo de AXX.'; }
    function stopCapture() { captureBinding = null; capture.stop?.(); }
    function syncControls() {
      const busy = Boolean(activeRun && !TERMINAL.has(activeRun.state));
      const recording = ['starting', 'listening', 'stopping'].includes(capture.state);
      send.disabled = privateMode || listing || busy || !selected || !input.value.trim() || recording || selected.active;
      selectors.hidden = input.hidden = privateMode;
      output.hidden = privateMode || !response.textContent;
      if (privateMode) status.textContent = 'Privacidad activa. Desactívala para mostrar y escribir en este chat.';
      project.disabled = session.disabled = listing || busy || recording;
      cancel.hidden = !busy; refresh.disabled = listing || (busy && !reconciliationNeeded);
      for (const button of providers.children) { button.disabled = busy || recording; button.setAttribute('aria-pressed', String(button.dataset.provider === provider)); }
      dictation.disabled = privateMode || !capture.start || !selected || busy || listing;
      input.disabled = !selected || listing || busy;
      const stateKey = privateMode ? 'private' : recording ? 'listening' : listing ? 'loading' : busy ? 'working' : selected ? 'ready' : 'unavailable';
      root.dataset.state = stateKey;
      if (heroState) {
        heroState.textContent = {
          private: 'Privacidad',
          listening: 'Escuchando…',
          loading: 'Cargando…',
          working: 'Trabajando…',
          ready: selected ? (PROVIDER_META[provider]?.label || 'Listo') : 'Listo',
          unavailable: 'Sin sesión'
        }[stateKey] || 'Listo';
      }
      root.dataset.draft = String(Boolean(input.value.trim()));
      for (const picker of pickers) { picker.button.disabled = picker.select.disabled || !picker.select.value; picker.value.textContent = picker.select.selectedOptions[0]?.text || 'Seleccionar…'; }
      moreSessions.disabled = listing || busy || recording;
      send.textContent = 'Enviar';
      input.placeholder = selected ? `Escribe a ${provider === 'claude' ? 'Claude Code' : provider === 'antigravity' ? 'Antigravity' : 'Codex'}…` : 'Selecciona una conversación para empezar';
    }
    function selectSession(id) {
      remember(); stopCapture(); selected = sessions.find(s => s.id === id) || null;
      input.value = drafts.get(key()) || '';
      response.textContent = requests.get(key())?.response || '';
      output.hidden = !response.textContent;
      status.textContent = selected?.active ? 'Esta conversación está trabajando. Actualiza cuando termine.' : selected ? 'Continuarás en la misma conversación.' : 'Selecciona una conversación para empezar.';
      session.value = selected?.id || ''; syncControls();
    }
    function showSessions() {
      const previousProject = project.value, previousId = selected?.id;
      const roots = [...new Set(sessions.map(s => s.project))];
      project.replaceChildren(...roots.map(p => new Option(p.split(/[\\/]/).filter(Boolean).pop() || p, p)));
      if (roots.includes(previousProject)) project.value = previousProject;
      if (!roots.length) project.add(new Option('Sin proyectos disponibles', ''));
      fillSessionList(previousId);
    }
    function fillSessionList(preferred) {
      const options = sessions.filter(s => s.project === project.value);
      session.replaceChildren(...options.map(s => new Option(s.title + (s.updated_at ? ' · ' + new Date(s.updated_at*1000).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '') + (s.active ? ' · trabajando' : ''), s.id)));
      if (!options.length) session.add(new Option('Sin conversaciones disponibles', ''));
      selectSession(options.some(s => s.id === preferred) ? preferred : options[0]?.id);
    }
    function renderQuota(snapshot) {
      quota.replaceChildren();
      const stale = !snapshot?.checked_at || Date.now()/1000-snapshot.checked_at > 120;
      if (!snapshot?.available || !snapshot.windows?.length) {
        quota.append(element('span', 'notch-muted', 'Saldo del plan · no disponible'));
        quota.title = snapshot?.reason || 'El proveedor no informó una cuota verificable.'; return;
      }
      for (const window of snapshot.windows) {
        const row = element('div', 'notch-usage-window');
        const pct = Math.max(0, Math.min(100, Number(window.remaining_percent) || 0));
        row.dataset.level = pct <= 20 ? 'low' : pct <= 50 ? 'mid' : 'high';
        const heading = element('div', 'notch-usage-heading');
        const windowName = window.window_minutes === 300 ? '5 horas' : window.window_minutes === 10080 ? 'Semanal' : window.window_minutes ? `${window.window_minutes} min` : 'Ventana del proveedor';
        const value = element('strong', 'notch-usage-value'); value.append(element('b', '', String(window.remaining_percent)), element('span', '', '%'));
        heading.append(element('span', 'notch-usage-label', windowName), value, element('span', 'notch-usage-caption', 'disponible'));
        const meter = element('meter', 'notch-usage-meter'); meter.min = 0; meter.max = 100; meter.value = window.remaining_percent; meter.setAttribute('aria-label', `Saldo ${windowName}`);
        row.append(heading, meter);
        const rail = element('span', 'notch-usage-rail'); rail.setAttribute('aria-hidden', 'true'); const fill = element('span'); fill.style.width = `${pct}%`; rail.append(fill); row.append(rail);
        if (window.resets_at) row.append(element('small', 'notch-muted', 'Reinicia ' + new Date(window.resets_at*1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })));
        quota.append(row);
      }
      quota.title = `${snapshot.source} · ${new Date(snapshot.checked_at*1000).toLocaleString()}${stale ? ' · último dato disponible' : ''}`;
      const freshness = element('small', 'notch-muted notch-quota-freshness', 'Actualizado ' + new Date(snapshot.checked_at*1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      freshness.style.gridColumn = '1 / -1'; quota.append(freshness);
      if (stale) quota.append(element('span', 'notch-muted', 'Último dato disponible · pulsa Actualizar.'));
    }
    async function refreshQuota() {
      if (quotaLoading) return; quotaLoading = true;
      quotaAt = Date.now();
      const expected = provider;
      try { const data = await api('GET', 'usage?provider=' + encodeURIComponent(expected)); if (provider === expected) { renderQuota(data); quotaAt = Date.now(); } }
      catch { if (provider === expected) renderQuota(null); }
      finally { quotaLoading = false; }
    }
    async function load(append = false) {
      if (listing || activeRun && !TERMINAL.has(activeRun.state)) return;
      remember(); stopCapture(); listing = true; const epoch = ++refreshEpoch; const expected = provider;
      status.textContent = 'Buscando tus conversaciones…'; syncControls();
      try {
        const data = await api('GET', 'sessions?provider=' + encodeURIComponent(expected) + (append && nextCursor ? '&cursor=' + encodeURIComponent(nextCursor) : ''));
        if (epoch !== refreshEpoch || provider !== expected) return;
        const incoming = Array.isArray(data.sessions) ? data.sessions : [];
        sessions = append ? [...new Map([...sessions, ...incoming].map(s => [s.id, s])).values()] : incoming;
        nextCursor = data.next_cursor || null; moreSessions.hidden = !nextCursor;
        showSessions();
        if (!sessions.length || !data.available) status.textContent = data.reason || 'No hay conversaciones locales para este proveedor.';
        label.textContent = data.scope || ''; label.hidden = !data.scope;
      } catch (error) { if (epoch === refreshEpoch) { sessions = []; showSessions(); status.textContent = error.message || 'No se pudo conectar. Tu borrador se conserva.'; } }
      finally { if (epoch === refreshEpoch) { listing = false; syncControls(); void refreshQuota(); } }
    }
    for (const [id, name] of [['codex', 'Codex'], ['claude', 'Claude Code'], ['antigravity', 'Antigravity']]) {
      const button = element('button', 'notch-chat-provider', name); button.type = 'button'; button.dataset.provider = id;
      button.addEventListener('click', () => { if (listing || provider === id) return; remember(); stopCapture(); provider = id; selected = null; quotaAt = 0; response.textContent = ''; quota.replaceChildren(); void load(); }); providers.append(button);
    }
    function acceptRun(run) {
      reconciliationNeeded = false;
      activeRun = run;
      response.textContent = run.response || ''; output.hidden = !response.textContent;
      if (selected) requests.set(key(), { response: run.response || '', request_id: run.request_id });
      if (TERMINAL.has(run.state)) {
        status.textContent = run.state === 'completed' ? 'Respuesta recibida en la misma conversación.' : run.error?.message || 'La solicitud terminó. Comprueba la conversación antes de volver a enviar.';
        if (run.state === 'completed') { input.value = ''; remember(); }
        void refreshQuota();
      } else status.textContent = run.pending_approvals?.length ? 'El proveedor está esperando una decisión. Puedes detener la solicitud.' : 'Esperando respuesta…';
      syncControls();
    }
    let polling = false;
    async function poll() {
      if (polling || !activeRun || TERMINAL.has(activeRun.state)) return;
      clearTimeout(pendingPoll); polling = true;
      try {
        const run = await api('GET', 'run?request_id=' + encodeURIComponent(activeRun.request_id)); acceptRun(run);
        if (!TERMINAL.has(run.state)) pendingPoll = setTimeout(poll, 650);
      } catch { reconciliationNeeded = true; status.textContent = 'No se pudo consultar el estado. Pulsa Actualizar para reconciliar; no se reenviará el mensaje.'; syncControls(); }
      finally { polling = false; }
    }
    async function submit(event) {
      event?.preventDefault(); if (send.disabled) return;
      stopCapture(); remember(); const request_id = crypto.randomUUID();
      reconciliationNeeded = false;
      activeRun = { request_id, state: 'accepted', response: '' }; response.textContent = ''; output.hidden = true; syncControls();
      status.textContent = `Enviando a ${provider === 'claude' ? 'Claude Code' : 'Codex'}…`;
      try { acceptRun(await api('POST', 'session/start', { provider, session_id: selected.id, request_id, message: input.value.trim() })); if (!TERMINAL.has(activeRun.state)) void poll(); }
      catch (error) {
        if (['BUSY', 'INVALID_INPUT', 'SESSION_UNVERIFIED', 'PROVIDER_UNAVAILABLE', 'AUTH_REQUIRED', 'DISCONNECTED', 'CLOSED', 'MEMORY_SCOPE_CHANGED'].includes(error.code)) {
          // These explicit admission rejections confirm that no turn was sent.
          acceptRun({ request_id, state: 'failed', response: '', error: { code: error.code, message: error.message } });
          return;
        }
        // An HTTP failure may follow durable admission. Reconcile the same ID,
        // never submit it again or silently send the draft to a different chat.
        status.textContent = error.message || 'No se confirmó el envío. Consulta su estado antes de repetir.';
        reconciliationNeeded = true; syncControls();
      }
    }
    form.addEventListener('submit', submit);
    input.addEventListener('input', () => { if (captureBinding) stopCapture(); remember(); syncControls(); });
    input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); void submit(); } });
    project.addEventListener('change', () => { remember(); fillSessionList(); }); session.addEventListener('change', () => selectSession(session.value));
    refresh.addEventListener('click', () => { if (activeRun && !TERMINAL.has(activeRun.state)) void poll(); else void load(); });
    moreSessions.addEventListener('click', () => { if (nextCursor) void load(true); });
    cancel.addEventListener('click', async () => { if (!activeRun) return; stopCapture(); try { await api('POST', 'cancel', { request_id: activeRun.request_id }); void poll(); } catch (error) { status.textContent = error.message; } });
    dictation.addEventListener('click', () => {
      if (capture.state === 'listening') { capture.finish?.(); return; }
      if (['starting', 'stopping'].includes(capture.state)) { stopCapture(); return; }
      captureBinding = { key: key(), prefix: input.value }; void capture.start?.(Axx.companion?.data?.prefs?.voiceLanguage || 'es');
    });
    // Startup/recovery refreshes metadata only. Never replay a prompt when the
    // native backend becomes ready after the user has already opened the notch.
    void Axx.app?.bridge?.listen?.('axx-backend-ready', () => { if (visible) void load(); });
    syncControls(); output.hidden = true;
    return {
      root,
      show(host) { visible = true; host.append(root); if (!loadingStarted) { loadingStarted = true; void load(); } else if (Date.now()-quotaAt > 60000) void refreshQuota(); },
      hide() { visible = false; closePicker(false); stopCapture(); remember(); },
      closePicker() { closePicker(false); },
      setPrivacy(value) { privateMode = Boolean(value); if (privateMode) closePicker(false); if (privateMode && captureBinding) stopCapture(); syncControls(); },
      tick() { if (visible && Date.now()-quotaAt > 60000 && !quotaLoading) void refreshQuota(); },
      getState() { return { provider, sessionId: selected?.id || null, requestId: activeRun?.request_id || null, state: activeRun?.state || 'idle' }; }
    };
  }
  Axx.notchChat = { createSurface };
})(window.Axx = window.Axx || {});
