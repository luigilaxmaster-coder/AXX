/* Telegram authenticates identity; the PC grants every operation. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const names = { messages: 'Mensajes', voice_notes: 'Notas de voz', files: 'Archivos', pc_commands: 'Acciones en PC', private_calls: 'Llamadas privadas' };
  const labels = { configured: 'Configurado', not_verified: 'Pendiente de prueba', not_implemented: 'Todavía no implementado', unavailable: 'No disponible', not_configured: 'Sin configurar' };
  let csrf = '', busy = false, avatar = null, pending = null, state = null, lastRtt = null, lastSync = null, pane = 'home';
  try {
    pending = JSON.parse(sessionStorage.getItem('axx.telegram.pending') || 'null');
    if (!pending || typeof pending.request_id !== 'string' || typeof pending.text !== 'string') pending = null;
    $('draft').value = sessionStorage.getItem('axx.telegram.draft') || '';
  } catch { pending = null; }
  const notice = text => { $('error').textContent = text; };
  function expire() {
    csrf = ''; state = null; $('connection').textContent = 'Sesión vencida o acceso denegado. Reabre Axx desde el menú de Telegram.';
    notice('No se pudo autorizar la solicitud. El borrador y el envío pendiente se conservan.'); paint();
  }
  async function request(path, body) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), body ? 95000 : 12000);
    const started = performance.now();
    try {
      const response = await fetch(path, { method: body ? 'POST' : 'GET', credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined, signal: controller.signal });
      lastRtt = Math.round(performance.now() - started);
      if (!response.ok) {
        let code = '';
        try { code = (await response.json()).error; } catch { /* No diagnostic data from the response. */ }
        if (code === 'PAIRING_REQUIRED') {
          csrf = ''; state = null; paint();
          $('connection').textContent = 'Vincula esta Mini App desde el QR en Herramientas → Telegram de tu PC.';
          throw new Error('Vincula esta Mini App desde el QR en Herramientas → Telegram de tu PC.');
        }
        if (code === 'AUTH_REQUIRED' || code === 'SESSION_EXPIRED' || response.status === 401) {
          expire(); throw new Error('Sesión vencida o acceso denegado. Reabre Axx en Telegram.');
        }
        if (code === 'PERMISSION_DENIED' || response.status === 403) {
          const error = new Error('Esta función no tiene permiso. Revísalo en tu PC.'); error.code = 'PERMISSION_DENIED'; throw error;
        }
        if (code === 'CORE_UNAVAILABLE' || response.status === 503) throw new Error('La PC no está disponible; el último estado puede estar desactualizado.');
        if (code === 'INVALID_REQUEST' || response.status === 400) throw new Error('La solicitud no es válida. Revisa los datos e inténtalo de nuevo.');
        throw new Error('La PC no pudo completar la solicitud.');
      }
      return await response.json();
    } catch (error) {
      if (!csrf && path !== '/api/session') throw error;
      if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('No hay conexión con la PC; el último estado puede estar desactualizado.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function paint() {
    const valid = !!csrf && !busy, allowed = state?.permissions?.conversation === true;
    $('draft').disabled = !valid || !allowed;
    $('send').disabled = !valid || !allowed || !!pending;
    $('recover').hidden = !pending; $('recover').disabled = !valid;
    $('retry').hidden = !pending; $('retry').disabled = !valid || !allowed;
  }
  function pairs(element, values) {
    const nodes = [];
    for (const [label, value] of values) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = String(value ?? 'No disponible'); nodes.push(dt, dd);
    }
    element.replaceChildren(...nodes);
  }
  function message(role, text, status = '') {
    const item = document.createElement('p'); item.className = 'message ' + (role === 'user' ? 'user' : 'assistant');
    item.textContent = String(text || '') + (status ? `\n${status}` : ''); $('messages').append(item);
  }
  function appearance(value) {
    if (!value || !window.Axx) { $('avatar').hidden = true; $('avatar-status').hidden = false; return; }
    try {
      const settings = Axx.normalizeSettings({ ...value.settings, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches });
      if (!avatar) { $('avatar').hidden = false; avatar = new Axx.MobileRenderer($('avatar'), settings); avatar.startLoop(); }
      $('avatar').hidden = false; avatar.configure(settings); avatar.setForm(settings.form); avatar.setStudio(value.studio || {}); avatar.setCamera20(value.camera); avatar.setFinish(value.finish || 'obsidian'); $('avatar-status').hidden = true;
    } catch { $('avatar-status').textContent = 'No se pudo mostrar el personaje. Los controles siguen disponibles.'; }
  }
  function renderState(value) {
    state = value; lastSync = new Date();
    const c = value.connection || {}, conv = value.conversation || {};
    $('connection').textContent = c.core_bound ? 'Axx está disponible en tu PC' : value.worker_running ? 'Telegram está activo; esperando tu PC' : 'La app responde; falta comprobar Telegram';
    $('home-summary').textContent = c.core_bound ? 'Tu PC está disponible.' : 'Estoy esperando tu PC.';
    $('simple-state').textContent = $('connection').textContent;
    $('provider-notice').textContent = conv.state && !['ready', 'available', 'configured'].includes(conv.state) ? (conv.message || 'El proveedor de conversación no está disponible. Puedes consultar los comandos autorizados.') : '';
    pairs($('capabilities'), Object.entries(names).map(([key, label]) => [label, labels[value[key]] || value[key] || 'No disponible']));
    const permNames = { conversation: 'Conversación', voice_notes: 'Notas de voz', files: 'Archivos', pc_commands: 'Acciones en PC', private_calls: 'Llamadas privadas' };
    pairs($('permissions'), Object.entries(permNames).map(([key, label]) => [label, value.permissions?.[key] === true ? 'Concedido' : value.permissions?.[key] === false ? 'No concedido' : 'No disponible']));
    pairs($('system-state'), [['Núcleo', c.core_bound ? 'Conectado' : 'No disponible'], ['Cuenta Telegram', c.account_running ? 'Activa' : 'No disponible'], ['Bot', c.bot_running ? 'Activo' : 'No disponible'], ['Proveedor', conv.provider === 'desktop_selected' ? 'Seleccionado en escritorio' : 'No disponible'], ['Modelo', conv.model || 'No disponible'], ['Sesión hasta', value.session_expires_at ? formatTime(value.session_expires_at) : 'No disponible'], ['Tiempo de respuesta', lastRtt == null ? 'No disponible' : `${lastRtt} ms`], ['Última sincronización', lastSync.toLocaleTimeString()]]);
    const safeCode = text => typeof text === 'string' && /^[A-Z_]{1,64}$/.test(text) ? text : null;
    const safeState = text => typeof text === 'string' && /^[a-z_]{1,40}$/.test(text) ? text : 'unavailable';
    $('diagnostics').textContent = JSON.stringify({ connection: { core_bound: !!c.core_bound, account_running: !!c.account_running, bot_running: !!c.bot_running }, conversation_state: safeState(conv.state), reason_code: safeCode(conv.reason_code), capabilities: Object.fromEntries(Object.keys(names).map(key => [key, safeState(value[key])])), rtt_ms: lastRtt, last_sync: lastSync.toISOString() }, null, 2);
    appearance(value.appearance); paint();
  }
  function formatTime(value) {
    const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
    return Number.isNaN(date.getTime()) ? 'No disponible' : date.toLocaleString();
  }
  async function refresh() {
    if (!csrf) return;
    try { renderState(await request('/api/state')); notice(''); }
    catch (error) { if (csrf) { if (error.code !== 'PERMISSION_DENIED') $('connection').textContent = 'Sin conexión · estado anterior desactualizado'; notice(error.message); } }
  }
  async function history() {
    if (!csrf) return;
    try {
      const value = await request('/api/history'); $('messages').replaceChildren();
      for (const item of (Array.isArray(value.messages) ? value.messages.slice(-50) : [])) message(item.role, item.text, item.status || '');
      if (!$('messages').children.length) message('assistant', 'El historial está vacío.');
      $('history-more').hidden = !value.has_more;
    } catch (error) { notice(error.message); }
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notice('Copiado.'); }
    catch { notice(`No se pudo copiar. Mantén pulsado para seleccionar: ${text}`); }
  }
  async function activity() {
    if (!csrf) return;
    try {
      const value = await request('/api/activity'), items = Array.isArray(value.items) ? value.items : [];
      $('activity-list').replaceChildren();
      for (const item of items) {
        const box = document.createElement('article'); box.className = 'activity-item';
        const title = document.createElement('strong'); title.textContent = item.command_id ? 'Acción en tu PC' : 'Solicitud a Axx'; box.append(title);
        const states = { prepared: 'Todavía no se ejecutó', awaiting_approval: 'Espera tu permiso en la PC', running: 'En marcha', succeeded: 'Terminada', completed: 'Terminada', failed: 'No confirmada', unknown: 'Sin confirmar', dispatch_unknown: 'Sin confirmar', delivery_unknown: 'Sin confirmar', cancelled: 'Cancelada', expired: 'Vencida' };
        const waiting = ['prepared', 'awaiting_approval', 'pending'].includes(item.state);
        const terminal = ['succeeded', 'completed', 'failed'].includes(item.state);
        const check = waiting ? 'Todavía no se ejecutó' : item.postconditions_passed === true ? 'Resultado comprobado' : item.postconditions_passed === false && terminal ? 'Comprobación fallida' : 'Resultado sin comprobar';
        for (const text of [`Estado: ${states[item.state] || 'Sin confirmar'}`, check]) { const p = document.createElement('p'); p.textContent = text; box.append(p); }
        const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Detalles'; details.append(summary);
        for (const text of [`ID: ${item.id || 'no disponible'}`, `Fecha: ${formatTime(item.created_at)}`]) { const p = document.createElement('p'); p.textContent = text; details.append(p); }
        if (item.command_id) { const p = document.createElement('p'); p.textContent = 'Comando: ' + item.command_id; details.append(p); }
        if (item.id) { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Copiar ID'; button.onclick = () => void copy(String(item.id)); details.append(button); }
        box.append(details);
        if (item.can_cancel === true && item.id) { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Solicitar cancelación'; button.onclick = async () => { button.disabled = true; try { await request('/api/cancel', { operation_id: item.id, csrf }); notice('Solicitud de cancelación enviada. Consulta el estado para confirmar.'); await activity(); } catch (error) { notice(error.message); button.disabled = false; } }; box.append(button); }
        $('activity-list').append(box);
      }
      if (!items.length) $('activity-list').textContent = 'Sin actividad disponible.';
      return items;
    } catch (error) { notice(error.message); return null; }
  }
  async function send(retry = false) {
    if (busy || !csrf || state?.permissions?.conversation !== true) return;
    const text = $('draft').value.trim();
    if (!retry) {
      if (pending || !text) return;
      pending = { text, request_id: crypto.randomUUID() };
      try { sessionStorage.setItem('axx.telegram.pending', JSON.stringify(pending)); } catch { notice('No se pudo guardar el ID pendiente; el envío no se inició.'); pending = null; return; }
      message('user', text);
    }
    if (!pending) return;
    busy = true; paint(); notice('');
    try {
      const result = await request('/api/chat', { ...pending, csrf });
      message('assistant', result.text || 'El servidor no devolvió texto.');
      pending = null; sessionStorage.removeItem('axx.telegram.pending'); sessionStorage.removeItem('axx.telegram.draft'); $('draft').value = '';
    } catch (error) { notice(`${error.message} El envío queda pendiente; consulta su estado antes de reintentar.`); }
    finally { busy = false; paint(); }
  }
  function navigate(next) {
    if (!['home', 'chat', 'activity', 'status'].includes(next)) return;
    pane = next;
    for (const id of ['home', 'chat', 'activity', 'status']) $(id).hidden = id !== pane;
    for (const button of document.querySelectorAll('[data-pane]')) { if (button.dataset.pane === pane) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }
    if (pane === 'home') tg?.BackButton?.hide?.(); else tg?.BackButton?.show?.();
    avatar?.resize(); if (pane === 'chat') void history(); if (pane === 'activity') void activity();
  }
  $('compose').onsubmit = event => { event.preventDefault(); void send(); };
  $('recover').onclick = async () => { const items = await activity(); if (items) notice('Estado consultado. Revisa Actividad; si no aparece, el resultado sigue sin confirmarse.'); };
  $('retry').onclick = () => void send(true); $('refresh').onclick = () => void refresh(); $('activity-refresh').onclick = () => void activity();
  $('draft').oninput = () => { try { sessionStorage.setItem('axx.telegram.draft', $('draft').value); } catch { notice('No se pudo conservar el borrador.'); } };
  $('copy-diagnostics').onclick = () => void copy($('diagnostics').textContent);
  for (const button of document.querySelectorAll('[data-pane]')) button.onclick = () => navigate(button.dataset.pane);
  for (const button of document.querySelectorAll('[data-open]')) button.onclick = () => navigate(button.dataset.open);
  const back = () => navigate('home'), resize = () => avatar?.resize();
  function visibility() { avatar?.setHidden(document.hidden); if (!document.hidden) void refresh(); }
  async function start() {
    paint();
    if (!tg?.initData) { $('connection').textContent = 'Abre esta app desde el menú de tu bot Axx en Telegram.'; return; }
    tg.ready(); tg.expand(); tg.BackButton?.onClick?.(back); tg.onEvent?.('themeChanged', resize); tg.onEvent?.('viewportChanged', resize);
    const fragment = new URLSearchParams(location.hash.slice(1));
    const values = fragment.getAll('pairing');
    const pairing = values.length === 1 && /^axx_[A-Za-z0-9_-]{43}$/.test(values[0]) ? values[0] : null;
    try {
      const session = await request('/api/session', { init_data: tg.initData, ...(pairing ? { pairing_token: pairing } : {}) });
      if (typeof session.csrf !== 'string' || !session.csrf) throw new Error('No se pudo iniciar la sesión.');
      csrf = session.csrf;
      if (pairing) window.history.replaceState(null, '', location.pathname + location.search);
      paint(); await refresh();
    }
    catch (error) { notice(error.message); }
  }
  document.addEventListener('visibilitychange', visibility);
  const poll = setInterval(() => { if (!document.hidden) void refresh(); }, 15000);
  window.addEventListener('pagehide', () => { clearInterval(poll); document.removeEventListener('visibilitychange', visibility); tg?.BackButton?.offClick?.(back); tg?.offEvent?.('themeChanged', resize); tg?.offEvent?.('viewportChanged', resize); avatar?.stop(); }, { once: true });
  void start();
})();
