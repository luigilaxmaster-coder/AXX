/* Telegram authenticates identity; the PC grants every operation. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const tg = window.Telegram?.WebApp;
  const names = { messages: 'Mensajes', voice_notes: 'Notas de voz', files: 'Archivos', pc_commands: 'Acciones en PC', private_calls: 'Llamadas privadas' };
  const labels = { configured: 'Configurado', admitted: 'Recibe solicitudes', verified_receipt: 'Hay acciones comprobadas', not_verified: 'Pendiente de prueba', not_implemented: 'Todavía no implementado', unavailable: 'No disponible', not_configured: 'Sin configurar' };
  let csrf = '', busy = false, avatar = null, pending = null, state = null, lastRtt = null, lastSync = null, pane = 'home', reviewToken = null, reviewBusy = false, reviewTimer = null, reviewDeadline = 0;
  let activityItems = null, activityFilter = 'all', activityRequest = 0, stateRequest = 0, historyRequest = 0, reviewRequest = 0, accessEpoch = 0;
  let commandItems = null, commandRequest = 0, commandEmptyText = '';
  try {
    pending = JSON.parse(sessionStorage.getItem('axx.telegram.pending') || 'null');
    if (!pending || typeof pending.request_id !== 'string' || typeof pending.text !== 'string') pending = null;
    $('draft').value = sessionStorage.getItem('axx.telegram.draft') || '';
  } catch { pending = null; }
  const notice = text => { $('error').textContent = text; };
  function requestContext(latest = () => true) {
    const epoch = accessEpoch, session = csrf;
    return () => epoch === accessEpoch && session === csrf && latest();
  }
  function clearHistory(text) {
    historyRequest++; $('messages').textContent = text; $('history-more').hidden = true;
  }
  function clearPrivateActivity() {
    accessEpoch++;
    commandRequest++; commandItems = null; commandEmptyText = ''; $('command-list').replaceChildren(); $('command-status').textContent = 'No hay acceso a los comandos.'; $('command-category').replaceChildren(new Option('Todas', ''));
    activityItems = null; activityRequest++; clearReview(); $('review-card').hidden = true;
    for (const id of ['review-state', 'review-explanation', 'review-title', 'review-description', 'review-risk', 'review-inputs', 'review-expiry', 'review-reason']) $(id).textContent = '';
    $('activity-list').textContent = 'No hay acceso a la actividad.';
    for (const id of ['count-pending', 'count-running', 'count-completed']) $(id).textContent = '—';
    $('activity-badge').hidden = true; $('review-pending').hidden = true;
    $('summary-freshness').textContent = $('activity-freshness').textContent = 'Sin acceso a los datos.';
  }
  function expire() {
    csrf = ''; state = null; clearPrivateActivity(); clearHistory('Abre Axx de nuevo para consultar el historial.'); $('connection').textContent = 'Sesión vencida o acceso denegado. Reabre Axx desde el menú de Telegram.';
    notice('No se pudo autorizar la solicitud. El borrador y el envío pendiente se conservan.'); paint();
  }
  async function request(path, body, current = requestContext()) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), body ? 95000 : 12000);
    const started = performance.now();
    try {
      const response = await fetch(path, { method: body ? 'POST' : 'GET', credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined, signal: controller.signal });
      if (!response.ok) {
        let code = '';
        try { code = (await response.json()).error; } catch { /* No diagnostic data from the response. */ }
        if (!current()) throw Object.assign(new Error('Respuesta anterior descartada.'), { code: 'STALE_RESPONSE' });
        if (code === 'PAIRING_REQUIRED') {
          csrf = ''; state = null; clearPrivateActivity(); clearHistory('Vincula la Mini App para consultar el historial.'); paint();
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
      const value = await response.json();
      if (!current()) throw Object.assign(new Error('Respuesta anterior descartada.'), { code: 'STALE_RESPONSE' });
      lastRtt = Math.round(performance.now() - started);
      return value;
    } catch (error) {
      if (!csrf && path !== '/api/session') throw error;
      if (error.name === 'AbortError' || error instanceof TypeError) {
        if (!current()) throw Object.assign(new Error('Respuesta anterior descartada.'), { code: 'STALE_RESPONSE' });
        throw new Error('No hay conexión con la PC; el último estado puede estar desactualizado.');
      }
      throw error;
    } finally { clearTimeout(timer); }
  }
  function paint() {
    const valid = !!csrf && !busy, allowed = state?.permissions?.conversation === true || state?.permissions?.pc_commands === true;
    $('draft').disabled = !valid || !allowed || !!pending;
    for (const example of document.querySelectorAll('[data-example]')) example.disabled = $('draft').disabled;
    $('send').disabled = !valid || !allowed || !!pending;
    $('recover').hidden = !pending; $('recover').disabled = !valid;
    $('retry').hidden = !pending; $('retry').disabled = !valid || !allowed;
    for (const button of document.querySelectorAll('[data-command-example]')) button.disabled = $('draft').disabled || button.dataset.available !== 'true';
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
    $('avatar').parentElement.dataset.empty = String(!value || !window.Axx);
    if (!value || !window.Axx) { $('avatar').hidden = true; $('avatar-status').hidden = false; return; }
    try {
      const settings = Axx.normalizeSettings({ ...value.settings, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches });
      if (!avatar) { $('avatar').hidden = false; avatar = new Axx.MobileRenderer($('avatar'), settings); avatar.startLoop(); }
      $('avatar').hidden = false; avatar.configure(settings); avatar.setForm(settings.form); avatar.setStudio(value.studio || {}); avatar.setCamera20(value.camera); avatar.setFinish(value.finish || 'obsidian'); $('avatar-status').hidden = true;
    } catch { $('avatar').hidden = true; $('avatar-status').hidden = false; $('avatar').parentElement.dataset.empty = 'true'; $('avatar-status').textContent = 'No se pudo mostrar el personaje. Los controles siguen disponibles.'; }
  }
  function renderState(value) {
    const revoked = Object.keys(state?.permissions || {}).some(key => state.permissions[key] === true && value.permissions?.[key] !== true)
      || (state?.remote_confirmations === true && value.remote_confirmations !== true);
    if (revoked) clearPrivateActivity();
    if (value.permissions?.conversation !== true) clearHistory('La conversación está desactivada. Puedes enviar órdenes si tienen permiso en tu PC.');
    state = value; lastSync = new Date();
    const c = value.connection || {}, conv = value.conversation || {};
    $('connection').textContent = c.core_bound ? 'Axx está disponible en tu PC' : value.worker_running ? 'Telegram está activo; esperando tu PC' : 'La app responde; falta comprobar Telegram';
    $('home-summary').textContent = c.core_bound ? 'Tu PC está disponible.' : 'Estoy esperando tu PC.';
    $('simple-state').textContent = $('connection').textContent;
    $('provider-notice').textContent = conv.state && !['ready', 'available', 'configured'].includes(conv.state) ? (conv.message || 'El proveedor de conversación no está disponible. Puedes consultar los comandos autorizados.') : '';
    pairs($('capabilities'), Object.entries(names).map(([key, label]) => [label, labels[value[key]] || value[key] || 'No disponible']));
    const permNames = { conversation: 'Conversación', voice_notes: 'Notas de voz', files: 'Archivos', pc_commands: 'Acciones en PC', remote_confirmations: 'Confirmaciones desde Telegram', private_calls: 'Llamadas privadas' };
    pairs($('permissions'), Object.entries(permNames).map(([key, label]) => { const enabled = key === 'remote_confirmations' ? value.remote_confirmations : value.permissions?.[key]; return [label, enabled === true ? 'Concedido' : enabled === false ? 'No concedido' : 'No disponible']; }));
    pairs($('system-state'), [['Núcleo', c.core_bound ? 'Conectado' : 'No disponible'], ['Cuenta Telegram', c.account_running ? 'Activa' : 'No disponible'], ['Bot', c.bot_running ? 'Activo' : 'No disponible'], ['Proveedor', conv.provider === 'desktop_selected' ? 'Seleccionado en escritorio' : 'No disponible'], ['Modelo', conv.model || 'No disponible'], ['Sesión hasta', value.session_expires_at ? formatTime(value.session_expires_at) : 'No disponible'], ['Tiempo de respuesta', lastRtt == null ? 'No disponible' : `${lastRtt} ms`], ['Última consulta', lastSync.toLocaleTimeString()]]);
    const safeCode = text => typeof text === 'string' && /^[A-Z_]{1,64}$/.test(text) ? text : null;
    const safeState = text => typeof text === 'string' && /^[a-z_]{1,40}$/.test(text) ? text : 'unavailable';
    $('diagnostics').textContent = JSON.stringify({ connection: { core_bound: !!c.core_bound, account_running: !!c.account_running, bot_running: !!c.bot_running }, conversation_state: safeState(conv.state), reason_code: safeCode(conv.reason_code), capabilities: Object.fromEntries(Object.keys(names).map(key => [key, safeState(value[key])])), rtt_ms: lastRtt, last_sync: lastSync.toISOString() }, null, 2);
    appearance(value.appearance); paint();
  }
  function formatTime(value) {
    const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
    return Number.isNaN(date.getTime()) ? 'No disponible' : date.toLocaleString();
  }
  async function refresh(silent = false) {
    if (!csrf) return;
    const requestId = ++stateRequest, current = requestContext(() => requestId === stateRequest);
    try { const value = await request('/api/state', undefined, current); if (!current()) return; renderState(value); await activity(silent); if (current() && pane === 'commands') await commands(); }
    catch (error) { if (current() && csrf) { if (error.code === 'PERMISSION_DENIED') { state = null; clearPrivateActivity(); clearHistory('No hay acceso al historial.'); $('connection').textContent = 'Acceso denegado.'; paint(); } else $('connection').textContent = 'Sin conexión · estado anterior desactualizado'; if (!silent) notice(error.message); } }
  }
  async function history() {
    if (!csrf) return;
    if (state?.permissions?.conversation !== true) {
      clearHistory('La conversación está desactivada. Puedes enviar órdenes si tienen permiso en tu PC.');
      return;
    }
    const requestId = ++historyRequest, current = requestContext(() => requestId === historyRequest);
    try {
      const value = await request('/api/history', undefined, current); if (!current() || state?.permissions?.conversation !== true) return; $('messages').replaceChildren();
      for (const item of (Array.isArray(value.messages) ? value.messages.slice(-50) : [])) message(item.role, item.text, item.status || '');
      if (!$('messages').children.length) message('assistant', 'El historial está vacío.');
      $('history-more').hidden = !value.has_more;
    } catch (error) { if (!current()) return; if (error.code === 'PERMISSION_DENIED') { clearPrivateActivity(); clearHistory('No hay acceso al historial.'); } notice(error.message); }
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notice('Copiado.'); }
    catch { notice(`No se pudo copiar. Mantén pulsado para seleccionar: ${text}`); }
  }
  function activityGroup(item) {
    if (['prepared', 'awaiting_approval', 'pending'].includes(item.state)) return 'pending';
    if (item.state === 'running') return 'running';
    if (['succeeded', 'completed', 'failed', 'cancelled', 'expired'].includes(item.state)) return 'completed';
    return 'unknown';
  }
  async function commands() {
    if (!csrf) return;
    const requestId = ++commandRequest, current = requestContext(() => requestId === commandRequest);
    if (!commandItems) $('command-status').textContent = 'Consultando comandos…';
    try {
      const result = await request('/api/commands', undefined, current);
      if (!current()) return;
      commandItems = Array.isArray(result.items) ? result.items : [];
      commandEmptyText = typeof result.text === 'string' ? result.text : '';
      const chosen = $('command-category').value;
      const categories = [...new Set(commandItems.map(item => item.category).filter(category => typeof category === 'string' && category))].sort();
      $('command-category').replaceChildren(new Option('Todas', ''), ...categories.map(category => new Option(category, category)));
      if (categories.includes(chosen)) $('command-category').value = chosen;
      renderCommands();
    } catch (error) {
      if (!current()) return;
      if (error.code === 'PERMISSION_DENIED') { state = null; clearPrivateActivity(); clearHistory('No hay acceso al historial.'); $('connection').textContent = 'Acceso denegado.'; paint(); }
      else $('command-status').textContent = 'No se pudo actualizar la lista; los datos anteriores pueden estar desactualizados.';
    }
  }
  function renderCommands() {
    if (!commandItems) return;
    const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
    const search = normalize($('command-search').value.trim()), category = $('command-category').value;
    const shown = commandItems.filter(item => (!category || item.category === category) && [item.title, item.example, item.description, item.category].some(value => typeof value === 'string' && normalize(value).includes(search)));
    $('command-list').replaceChildren();
    for (const item of shown) {
      const card = document.createElement('article'); card.className = 'command-card';
      const title = document.createElement('strong'); title.textContent = typeof item.title === 'string' ? item.title : 'Comando'; card.append(title);
      for (const text of [item.description, typeof item.example === 'string' && item.example ? 'Ejemplo: ' + item.example : '', item.available === false ? (item.reason || 'No disponible en este momento.') : '']) {
        if (typeof text === 'string' && text) { const p = document.createElement('p'); p.textContent = text; card.append(p); }
      }
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Escribir';
      button.dataset.commandExample = typeof item.example === 'string' ? item.example : '';
      button.dataset.available = String(item.available === true && !!button.dataset.commandExample);
      button.disabled = $('draft').disabled || button.dataset.available !== 'true';
      button.onclick = () => { if ($('draft').disabled || button.dataset.available !== 'true') return; $('draft').value = button.dataset.commandExample; $('draft').dispatchEvent(new Event('input')); navigate('chat'); $('draft').focus(); };
      card.append(button); $('command-list').append(card);
    }
    $('command-status').textContent = shown.length ? `${shown.length} comandos en esta lista.` : (!commandItems.length && !search && !category && commandEmptyText) ? commandEmptyText : 'No hay comandos que coincidan.';
  }
  async function activity(silent = false) {
    if (!csrf) return;
    const requestId = ++activityRequest, current = requestContext(() => requestId === activityRequest);
    try {
      const value = await request('/api/activity', undefined, current), items = Array.isArray(value.items) ? value.items : [];
      if (!current()) return null;
      activityItems = items;
      const timestamp = new Date().toLocaleTimeString();
      $('summary-freshness').textContent = $('activity-freshness').textContent = 'Última consulta: ' + timestamp;
      renderActivity();
      return items;
    } catch (error) {
      if (!current()) return null;
      if (error.code === 'PERMISSION_DENIED') { clearPrivateActivity(); clearHistory('No hay acceso al historial.'); }
      else $('summary-freshness').textContent = $('activity-freshness').textContent = 'No se pudo actualizar; los datos anteriores pueden estar desactualizados.';
      if (!silent) notice(error.message);
      return null;
    }
  }
  function renderActivity() {
      if (!activityItems) return;
      const items = activityItems;
      for (const [group, id] of [['pending', 'count-pending'], ['running', 'count-running'], ['completed', 'count-completed']]) $(id).textContent = String(items.filter(item => activityGroup(item) === group).length);
      const reviewable = items.filter(item => activityGroup(item) === 'pending' && item.review_available === true);
      $('activity-badge').textContent = String(reviewable.length); $('activity-badge').hidden = !reviewable.length;
      $('review-pending').hidden = !reviewable.length;
      const shown = items.filter(item => activityFilter === 'all' || activityGroup(item) === activityFilter)
        .slice().sort((a, b) => Number(activityGroup(b) === 'pending') - Number(activityGroup(a) === 'pending'));
      $('activity-list').replaceChildren();
      for (const item of shown) {
        const box = document.createElement('article'); box.className = 'activity-item';
        const title = document.createElement('strong'); title.textContent = item.command_id ? 'Acción en tu PC' : 'Solicitud a Axx'; box.append(title);
        const states = { prepared: 'Todavía no se ejecutó', awaiting_approval: 'Espera tu revisión', running: 'En marcha', succeeded: 'Terminada', completed: 'Terminada', failed: 'No confirmada', unknown: 'Sin confirmar', dispatch_unknown: 'Sin confirmar', delivery_unknown: 'Sin confirmar', cancelled: 'Cancelada', expired: 'Vencida' };
        const waiting = ['prepared', 'awaiting_approval', 'pending'].includes(item.state);
        const terminal = ['succeeded', 'completed', 'failed'].includes(item.state);
        const check = waiting ? 'Todavía no se ejecutó' : item.postconditions_passed === true ? 'Resultado comprobado' : item.postconditions_passed === false && terminal ? 'Comprobación fallida' : 'Resultado sin comprobar';
        for (const text of [`Estado: ${states[item.state] || 'Sin confirmar'}`, check]) { const p = document.createElement('p'); p.textContent = text; box.append(p); }
        const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'Detalles'; details.append(summary);
        for (const text of [`ID: ${item.id || 'no disponible'}`, `Fecha: ${formatTime(item.created_at)}`]) { const p = document.createElement('p'); p.textContent = text; details.append(p); }
        if (item.command_id) { const p = document.createElement('p'); p.textContent = 'Comando: ' + item.command_id; details.append(p); }
        if (item.id) { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Copiar ID'; button.onclick = () => void copy(String(item.id)); details.append(button); }
        box.append(details);
        if (item.review_available === true && item.id) { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Revisar orden'; button.onclick = () => void review(item.id); box.append(button); }
        if (item.can_cancel === true && item.id) { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Solicitar cancelación'; button.onclick = async () => { const current = requestContext(); button.disabled = true; try { await request('/api/cancel', { operation_id: item.id, csrf }, current); if (!current()) return; notice('Solicitud de cancelación enviada. Consulta el estado para confirmar.'); await activity(); } catch (error) { if (current()) { notice(error.message); button.disabled = false; } } }; box.append(button); }
        $('activity-list').append(box);
      }
      if (!shown.length) $('activity-list').textContent = activityFilter === 'all' ? 'Aún no hay solicitudes recientes.' : activityFilter === 'pending' ? 'No hay solicitudes pendientes en esta lista.' : 'No hay solicitudes en este filtro.';
  }
  async function review(operationId) {
    if (!csrf || reviewBusy) return;
    clearReview(); reviewBusy = true; $('review-card').hidden = true;
    const requestId = reviewRequest, current = requestContext(() => requestId === reviewRequest);
    try {
      const value = await request('/api/review', { operation_id: operationId, csrf }, current);
      if (!current()) return;
      $('review-title').textContent = value.title || 'Acción en tu PC';
      $('review-description').textContent = value.description || '';
      const risks = { read: 'Consulta', desktop_open: 'Abrir aplicación/página', system_command: 'Comando del sistema', local_state: 'Cambiar estado de aplicación' };
      $('review-risk').textContent = 'Riesgo: ' + (Object.hasOwn(risks, value.risk) ? risks[value.risk] : 'Requiere revisión en la PC');
      $('review-inputs').textContent = JSON.stringify(value.inputs || {}, null, 2);
      $('review-expiry').textContent = 'Vence: ' + formatTime(value.expires_at);
      $('review-reason').textContent = value.reason || '';
      const reviewable = value.can_confirm === true && ['awaiting_approval', 'prepared'].includes(value.state);
      $('review-state').textContent = reviewable ? 'Orden pendiente · No ejecutada' : '';
      $('review-explanation').textContent = reviewable ? 'Aprobar ejecuta esta orden una vez; denegar la cancela.' : '';
      reviewToken = reviewable && typeof value.token === 'string' ? value.token : null;
      reviewDeadline = typeof value.expires_at === 'number' && Number.isFinite(value.expires_at) ? value.expires_at * 1000 : 0;
      updateReviewExpiry();
      if (reviewToken) reviewTimer = setInterval(updateReviewExpiry, 1000);
      $('review-card').hidden = false; $('review-card').scrollIntoView({ block: 'nearest' });
    } catch (error) { if (current()) notice(error.message); }
    finally { if (requestId === reviewRequest) reviewBusy = false; }
  }
  function clearReview() {
    reviewRequest++; reviewBusy = false;
    clearInterval(reviewTimer); reviewTimer = null; reviewToken = null; reviewDeadline = 0;
    $('review-confirm').disabled = true; $('review-cancel').disabled = true;
  }
  function updateReviewExpiry() {
    const remaining = Math.max(0, Math.ceil((reviewDeadline - Date.now()) / 1000));
    if (reviewToken && remaining === 0) { clearReview(); $('review-reason').textContent = 'La confirmación venció. Revisa la orden de nuevo.'; }
    $('review-confirm').disabled = !reviewToken; $('review-cancel').disabled = !reviewToken;
    if (reviewToken) $('review-expiry').textContent = `La confirmación vence en ${remaining} s.`;
  }
  async function decide(decision) {
    updateReviewExpiry();
    if (!csrf || !reviewToken || reviewBusy) return;
    const token = reviewToken; clearReview(); reviewBusy = true;
    const requestId = reviewRequest, current = requestContext(() => requestId === reviewRequest);
    $('review-confirm').disabled = true; $('review-cancel').disabled = true;
    try {
      const result = await request('/api/decision', { token, decision, csrf }, current);
      if (!current()) return;
      const text = result.state === 'succeeded' && result.postconditions_passed !== true
        ? 'El resultado no está confirmado. Consulta la actividad antes de repetir.'
        : result.text || 'Consulta el estado de la operación.';
      notice(text); $('review-card').hidden = true; await activity();
      if (current() && result.next_operation_id) { reviewBusy = false; await review(result.next_operation_id); }
    } catch (error) { if (current()) notice(error.message + ' Consulta la actividad antes de reintentar.'); }
    finally { if (requestId === reviewRequest) reviewBusy = false; }
  }
  $('review-confirm').onclick = () => void decide('confirm');
  $('review-cancel').onclick = () => void decide('cancel');
  $('review-close').onclick = () => { clearReview(); $('review-card').hidden = true; };
  async function send(retry = false) {
    if (busy || !csrf || (state?.permissions?.conversation !== true && state?.permissions?.pc_commands !== true)) return;
    const text = $('draft').value.trim();
    if (!retry) {
      if (pending || !text) return;
      const candidate = { text, request_id: crypto.randomUUID() };
      if (new TextEncoder().encode(JSON.stringify({ ...candidate, csrf })).length > 16384) { notice('El mensaje es demasiado largo para enviarlo. Acórtalo e inténtalo de nuevo.'); return; }
      pending = candidate;
      try { sessionStorage.setItem('axx.telegram.pending', JSON.stringify(pending)); } catch { notice('No se pudo guardar el ID pendiente; el envío no se inició.'); pending = null; return; }
      message('user', text);
    }
    if (!pending) return;
    if (new TextEncoder().encode(JSON.stringify({ ...pending, csrf })).length > 16384) { notice('Este envío pendiente supera el límite y no puede reintentarse. Consulta su estado en Actividad o en la PC.'); return; }
    busy = true; paint(); notice('');
    const current = requestContext();
    try {
      const result = await request('/api/chat', { ...pending, csrf }, current);
      if (!current()) return;
      message('assistant', result.text || 'El servidor no devolvió texto.');
      pending = null; sessionStorage.removeItem('axx.telegram.pending'); sessionStorage.removeItem('axx.telegram.draft'); $('draft').value = '';
      if (result.state === 'awaiting_approval' && typeof result.operation_id === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(result.operation_id)) {
        navigate('activity'); await review(result.operation_id);
      }
    } catch (error) { if (current()) notice(`${error.message} El envío queda pendiente; consulta su estado antes de reintentar.`); }
    finally { busy = false; paint(); }
  }
  function navigate(next) {
    if (!['home', 'chat', 'commands', 'activity', 'status'].includes(next)) return;
    pane = next;
    for (const id of ['home', 'chat', 'commands', 'activity', 'status']) $(id).hidden = id !== pane;
    for (const button of document.querySelectorAll('[data-pane]')) { if (button.dataset.pane === pane) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }
    if (pane === 'home') tg?.BackButton?.hide?.(); else tg?.BackButton?.show?.();
    avatar?.resize(); if (pane === 'chat') void history(); if (pane === 'activity') void activity(); if (pane === 'commands') void commands();
  }
  $('compose').onsubmit = event => { event.preventDefault(); void send(); };
  $('recover').onclick = async () => { const items = await activity(); if (items) notice('Estado consultado. Revisa Actividad; si no aparece, el resultado sigue sin confirmarse.'); };
  $('retry').onclick = () => void send(true); $('refresh').onclick = () => void refresh(); $('activity-refresh').onclick = () => void activity();
  $('review-pending').onclick = () => { activityFilter = 'pending'; syncFilters(); navigate('activity'); };
  function syncFilters() { for (const button of document.querySelectorAll('[data-activity-filter]')) button.setAttribute('aria-pressed', String(button.dataset.activityFilter === activityFilter)); renderActivity(); }
  for (const button of document.querySelectorAll('[data-activity-filter]')) button.onclick = () => { activityFilter = button.dataset.activityFilter; syncFilters(); };
  for (const button of document.querySelectorAll('[data-example]')) button.onclick = () => { if ($('draft').disabled) return; $('draft').value = button.dataset.example; $('draft').dispatchEvent(new Event('input')); $('draft').focus(); };
  $('command-search').oninput = renderCommands; $('command-category').onchange = renderCommands;
  $('draft').oninput = () => { try { sessionStorage.setItem('axx.telegram.draft', $('draft').value); } catch { notice('No se pudo conservar el borrador.'); } };
  $('copy-diagnostics').onclick = () => void copy($('diagnostics').textContent);
  for (const button of document.querySelectorAll('[data-pane]')) button.onclick = () => navigate(button.dataset.pane);
  for (const button of document.querySelectorAll('[data-open]')) button.onclick = () => navigate(button.dataset.open);
  const back = () => navigate('home'), resize = () => avatar?.resize();
  function visibility() { avatar?.setHidden(document.hidden); if (!document.hidden) void refresh(); }
  async function start() {
    paint();
    const fragment = new URLSearchParams(location.hash.slice(1));
    const values = fragment.getAll('pairing');
    const pairing = values.length === 1 && /^axx_[A-Za-z0-9_-]{43}$/.test(values[0]) ? values[0] : null;
    if (values.length) {
      fragment.delete('pairing');
      const rest = fragment.toString();
      window.history.replaceState(null, '', location.pathname + location.search + (rest ? '#' + rest : ''));
    }
    if (!tg?.initData) { $('connection').textContent = values.length ? 'No se pudo abrir la vinculación. Genera un QR nuevo en tu PC y abre Axx desde Telegram.' : 'Abre esta app desde el menú de tu bot Axx en Telegram.'; return; }
    tg.ready(); tg.expand(); tg.BackButton?.onClick?.(back); tg.onEvent?.('themeChanged', resize); tg.onEvent?.('viewportChanged', resize);
    try {
      const current = requestContext();
      const session = await request('/api/session', { init_data: tg.initData, ...(pairing ? { pairing_token: pairing } : {}) }, current);
      if (!current()) return;
      if (typeof session.csrf !== 'string' || !session.csrf) throw new Error('No se pudo iniciar la sesión.');
      csrf = session.csrf;
      paint(); await refresh();
    }
    catch (error) { if (error.code !== 'STALE_RESPONSE') notice(error.message + (values.length ? ' Genera un QR nuevo en tu PC para volver a vincular.' : '')); }
  }
  document.addEventListener('visibilitychange', visibility);
  const poll = setInterval(() => { if (!document.hidden) void refresh(true); }, 15000);
  window.addEventListener('pagehide', () => { accessEpoch++; clearReview(); clearInterval(poll); document.removeEventListener('visibilitychange', visibility); tg?.BackButton?.offClick?.(back); tg?.offEvent?.('themeChanged', resize); tg?.offEvent?.('viewportChanged', resize); avatar?.stop(); }, { once: true });
  void start();
})();
