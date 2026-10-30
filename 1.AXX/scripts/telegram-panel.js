/* Telegram is configured locally; no credentials are stored in the renderer. */
(function installTelegramPanel(Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.isNative() || Axx.telegramPanel) return;
    const $ = id => document.getElementById(id);
    const card = document.createElement('section');
    card.id = 'telegram-panel'; card.className = 'setup-card';
    card.innerHTML = `
      <h3>Telegram</h3><p class="micro-copy">Tu PC es la casa de Axx. Telegram es la puerta para usarlo desde tu teléfono. Deja Axx abierto y la PC encendida.</p>
      <p id="tg-panel-status" role="status" aria-live="polite">Consultando conexión…</p>
      <p id="tg-next-step" role="status" aria-live="polite"></p>
      <h4>1. Conecta tu cuenta</h4><p id="tg-account-status">Comprobando…</p>
      <p id="tg-login-help" class="micro-copy">Abre la cuenta de Telegram dedicada a Axx. Toca Ajustes → Dispositivos → Vincular dispositivo de escritorio. Escanea este primer QR.</p>
      <button type="button" id="tg-prepare-app" hidden>Preparar la conexión por primera vez</button>
      <div class="quick-row"><button type="button" id="tg-start-qr" class="primary">Conectar con QR</button><button type="button" id="tg-cancel-qr">Cancelar</button></div>
      <img id="tg-login-qr" width="240" height="240" hidden alt="QR 1: vincular la cuenta de Telegram de Axx" style="background:white;padding:8px;max-width:100%;height:auto">
      <p id="tg-login-expiry" class="micro-copy"></p>
      <div id="tg-password-section" hidden><p>Telegram pide la contraseña de verificación en dos pasos que ya tiene esta cuenta. No tienes que crear otra aquí.</p><label>Contraseña de Telegram <input id="tg-password" type="password" autocomplete="off"></label><button type="button" id="tg-submit-password">Continuar</button></div>
      <h4>2. Elige qué puede hacer</h4><p class="micro-copy">Marca lo que permites y pulsa Guardar permisos. Algunas funciones todavía están en preparación.</p>
      <label><input type="checkbox" id="tg-enabled"> Activar Telegram</label>
      <div id="tg-permissions">
        <label><input type="checkbox" data-tg-grant="conversation"> Conversar por texto</label>
        <label><input type="checkbox" data-tg-grant="voice_notes"> Notas de voz · en preparación</label>
        <label><input type="checkbox" data-tg-grant="files"> Archivos · en preparación</label>
        <label><input type="checkbox" data-tg-grant="pc_commands"> Acciones en esta PC</label>
        <label><input type="checkbox" data-tg-grant="private_calls"> Llamadas privadas · aún no disponibles (en reparación)</label>
      </div>
      <div class="quick-row"><button type="button" id="tg-save-permissions">Guardar permisos</button><button type="button" id="tg-pause">Pausar</button><button type="button" id="tg-resume">Reanudar</button></div>
      <p class="micro-copy">Pausar corta el acceso. Cambiar permisos o pausar pide volver a escanear el QR 2; tus datos se conservan.</p>
      <label><input type="checkbox" id="tg-remote-confirmations"> Confirmar comandos desde Telegram</label>
      <p class="micro-copy">Permite aprobar consultas, abrir aplicaciones y cerrar ventanas observadas después de revisar cada orden. Las acciones reservadas siguen requiriendo la PC.</p>
      <button type="button" id="tg-save-confirmations">Guardar confirmación remota</button>
      <h4>3. Abre Axx en tu teléfono</h4><p class="micro-copy">Ahora usa tu cuenta personal. Con la cámara del teléfono, escanea el segundo QR. En Telegram, toca Iniciar y luego Abrir Axx.</p>
      <button type="button" id="tg-prepare-bot" hidden>Preparar el bot y su dirección</button>
      <div class="quick-row"><button type="button" id="tg-pair-create" class="primary">Mostrar QR para teléfono</button><button type="button" id="tg-pair-revoke-all">Desvincular todos</button></div>
      <img id="tg-pair-qr" width="240" height="240" hidden alt="QR 2: abrir Axx en tu teléfono" style="background:white;padding:8px;max-width:100%;height:auto"><p id="tg-pair-expiry" class="micro-copy"></p>
      <div id="tg-pair-list"></div>
      <h4>4. Comprueba y empieza a usarlo</h4><p id="tg-check-status">Actualiza para ver el estado.</p><button type="button" id="tg-refresh">Comprobar conexión</button>
      <ol><li>Abre el chat del bot y envía /start para ver su menú.</li><li>Toca Comandos o escribe /comandos para ver ejemplos.</li><li>Toca Abrir Axx para buscar comandos, escribir al chat y consultar la actividad.</li><li>Revisa la tarjeta de cada orden y elige Aprobar una vez o Denegar. Las acciones reservadas requieren la PC.</li></ol>
      <p class="micro-copy">Chat con IA todavía no está disponible; tu proveedor no cambió. Las llamadas están en reparación.</p>
      <details id="tg-advanced"><summary>Opciones avanzadas · solo la primera vez</summary>
        <button type="button" id="tg-reconnect">Volver a vincular cuenta</button>
        <p class="micro-copy">Los datos se introducen en esta PC y no se vuelven a mostrar.</p>
        <p class="micro-copy">Datos de aplicación: obtén API ID y API hash en my.telegram.org, en API development tools. Son distintos del ID de tu usuario.</p>
        <label>API ID · número de la aplicación <input id="tg-api-id" inputmode="numeric" autocomplete="off"></label>
        <label>API hash · clave de la aplicación <input id="tg-api-hash" type="password" autocomplete="off"></label>
        <label>ID numérico de tu cuenta personal · quién puede usar Axx <input id="tg-owner-id" inputmode="numeric" autocomplete="off"></label>
        <button type="button" id="tg-save-app">Guardar datos de aplicación</button>
        <p id="tg-bot-status" role="status"></p><p class="micro-copy">En Telegram, crea el bot con @BotFather y /newbot. Pega su token aquí. Abre ese bot desde tu cuenta personal y envía /start.</p><label>Token del bot · clave que entrega BotFather <input id="tg-bot-token" type="password" autocomplete="off" placeholder="Dejar vacío para conservar"></label>
        <label>Dirección HTTPS de la Mini App <input id="tg-public-url" type="url" autocomplete="off"></label>
        <label><input id="tg-bot-enabled" type="checkbox"> Activar bot</label><button type="button" id="tg-save-bot">Guardar bot</button>
        <p class="micro-copy">La conversación puede estar bloqueada por la política del proveedor; habilitar un permiso no cambia esa política.</p>
      </details>`;
    $('view-settings')?.append(card);
    for (const label of card.querySelectorAll('label')) { label.style.display = 'block'; label.style.marginBlock = '10px'; }
    const api = (method, route, body) => Axx.backendRequest(method, '/axx-api/telegram/' + route, body);
    let busy = false, info = null, pairExpiry = 0, poll = null, permissionsDirty = false, botDirty = false, confirmationDirty = false;
    function message(text) { $('tg-panel-status').textContent = text; }
    function qrImage(image, value) {
        if (typeof value === 'string' && /^[A-Za-z0-9+/=]+$/.test(value)) { image.src = 'data:image/svg+xml;base64,' + value; image.hidden = false; }
        else { image.hidden = true; image.removeAttribute('src'); }
    }
    function seconds(expiry) { return Math.max(0, Math.ceil(Number(expiry || 0) - Date.now() / 1000)); }
    function tick() {
        const login = info?.qr?.expires_at;
        $('tg-login-expiry').textContent = login ? `QR 1: ${seconds(login)} s restantes.` : '';
        $('tg-pair-expiry').textContent = pairExpiry ? `QR 2: ${seconds(pairExpiry)} s restantes.` : '';
        if (login && !seconds(login)) qrImage($('tg-login-qr'), null);
        if (pairExpiry && !seconds(pairExpiry)) { qrImage($('tg-pair-qr'), null); pairExpiry = 0; }
    }
    function render(value) {
        info = value;
        const account = value.account || {}, bot = value.bot || {}, qr = value.qr || {};
        $('tg-account-status').textContent = account.configured ? 'Tu cuenta ya está guardada en este PC. No repitas este paso.' : 'Todavía no está conectada.';
        $('tg-login-help').hidden = !!account.configured;
        $('tg-prepare-app').hidden = !!value.app_configured;
        $('tg-start-qr').disabled = !value.app_configured;
        $('tg-prepare-bot').hidden = !!(bot.configured && bot.enabled && bot.public_url);
        $('tg-pair-create').disabled = !(account.configured && account.enabled && bot.configured && bot.enabled && bot.public_url);
        $('tg-next-step').textContent = !value.app_configured ? 'Primero: toca Preparar la conexión por primera vez.' : !account.configured ? 'Siguiente: toca Conectar con QR.' : !account.enabled ? 'Siguiente: elige tus permisos y activa Telegram.' : !(bot.configured && bot.enabled && bot.public_url) ? 'Siguiente: prepara el bot y su dirección.' : 'Siguiente: muestra el QR para tu teléfono y escanéalo.';
        $('tg-start-qr').hidden = !!account.configured;
        $('tg-cancel-qr').hidden = !['starting', 'waiting_qr', 'password_required', 'verifying'].includes(qr.state);
        $('tg-password-section').hidden = qr.state !== 'password_required';
        qrImage($('tg-login-qr'), qr.state === 'waiting_qr' && seconds(qr.expires_at) ? qr.image : null);
        if (!permissionsDirty) {
            $('tg-enabled').checked = !!account.enabled;
            for (const node of card.querySelectorAll('[data-tg-grant]')) node.checked = account.grants?.[node.dataset.tgGrant] === true;
        }
        if (!confirmationDirty) $('tg-remote-confirmations').checked = value.remote_confirmations === true;
        $('tg-save-confirmations').disabled = !account.configured;
        $('tg-bot-status').textContent = bot.configured ? `Bot configurado${bot.username ? ': @' + bot.username : ''}.` : 'Bot no configurado.';
        if (value.bot_job?.state === 'running') $('tg-bot-status').textContent = 'Comprobando y guardando el bot…';
        else if (value.bot_job?.state === 'failed') $('tg-bot-status').textContent = 'No se pudo terminar el guardado del bot. Revisa el token, la dirección HTTPS y la conexión.';
        else if (value.bot_job?.state === 'saved') $('tg-bot-status').textContent += value.bot_job.menu_configured === false ? (bot.public_url ? ' Datos guardados; falta actualizar el menú.' : ' Datos guardados; falta la dirección HTTPS.') : ' Datos guardados.';
        if (!botDirty) { $('tg-public-url').value = bot.public_url || ''; $('tg-bot-enabled').checked = !!bot.enabled; }
        $('tg-check-status').textContent = account.configured ? (account.enabled ? 'Cuenta registrada y canal habilitado; falta comprobar la conexión.' : 'Cuenta registrada; canal pausado.') : 'Cuenta no conectada.';
        if (qr.state === 'failed') message('No se pudo conectar la cuenta. Revisa los datos avanzados e inténtalo de nuevo.');
        else if (qr.state === 'password_required') message('Escribe la contraseña de verificación en esta PC.');
        else if (qr.state === 'saved') message('Cuenta conectada.');
        else if (qr.state === 'waiting_qr') message('Escanea el QR 1 desde la cuenta de Telegram de Axx.');
        else if ($('tg-panel-status').textContent === 'Consultando conexión…') message('Configuración cargada. Sigue el paso indicado.');
        tick();
    }
    async function refresh() {
        try {
            render(await api('GET', 'desktop/status'));
            const pair = info.account?.configured && info.account?.enabled ? await api('GET', 'pairing/status') : { bindings: [] };
            const list = $('tg-pair-list'); list.replaceChildren();
            for (const binding of pair.bindings || []) {
                const row = document.createElement('p'); row.textContent = 'Teléfono vinculado ';
                const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Desvincular';
                remove.onclick = () => void run(async () => { await api('POST', 'pairing/revoke', { binding_id: binding.id }); message('Teléfono desvinculado.'); });
                row.append(remove); list.append(row);
            }
            if (pair.bindings?.length) $('tg-next-step').textContent = 'Tu teléfono ya está vinculado. Ve al paso 4 para comprobarlo.';
        } catch { message('No se pudo consultar Telegram. Abre Axx en Windows e inténtalo de nuevo.'); }
    }
    async function run(action) {
        if (busy) return;
        busy = true; card.setAttribute('aria-busy', 'true');
        try { await action(); await refresh(); }
        catch { message('No se pudo completar. Revisa los datos y vuelve a intentarlo.'); }
        finally { busy = false; card.removeAttribute('aria-busy'); }
    }
    $('tg-start-qr').onclick = () => void run(async () => { await api('POST', 'desktop/start_qr', {}); message('Preparando QR 1…'); });
    function advanced(input) { $('tg-advanced').open = true; $(input).focus(); $(input).scrollIntoView({ block: 'center' }); }
    $('tg-prepare-app').onclick = () => advanced('tg-api-id');
    $('tg-prepare-bot').onclick = () => advanced('tg-bot-token');
    $('tg-reconnect').onclick = () => $('tg-start-qr').click();
    $('tg-cancel-qr').onclick = () => void run(async () => { await api('POST', 'desktop/cancel', {}); qrImage($('tg-login-qr'), null); message('Conexión cancelada.'); });
    $('tg-submit-password').onclick = () => void run(async () => { const password = $('tg-password').value; $('tg-password').value = ''; await api('POST', 'desktop/password', { password }); message('Comprobando…'); });
    $('tg-pair-create').onclick = () => void run(async () => { const result = await api('POST', 'pairing/create', {}); pairExpiry = result.expires_at; qrImage($('tg-pair-qr'), result.qr_svg_base64); tick(); message('Escanea el QR 2, toca Iniciar y luego Abrir Axx.'); });
    $('tg-pair-revoke-all').onclick = () => void run(async () => { await api('POST', 'pairing/revoke_all', {}); qrImage($('tg-pair-qr'), null); pairExpiry = 0; message('Vinculaciones revocadas.'); });
    for (const node of card.querySelectorAll('[data-tg-grant], #tg-enabled')) node.onchange = () => { permissionsDirty = true; };
    $('tg-public-url').oninput = $('tg-bot-enabled').onchange = () => { botDirty = true; };
    $('tg-save-permissions').onclick = () => void run(async () => { const grants = Object.fromEntries([...card.querySelectorAll('[data-tg-grant]')].map(node => [node.dataset.tgGrant, node.checked])); await api('POST', 'desktop/update_permissions', { enabled: $('tg-enabled').checked, grants }); permissionsDirty = false; message('Permisos guardados.'); });
    $('tg-remote-confirmations').onchange = () => { confirmationDirty = true; };
    $('tg-save-confirmations').onclick = () => void run(async () => {
        if ($('tg-remote-confirmations').checked && (!info?.account?.enabled || !info.account.grants?.pc_commands)) {
            message('Primero activa Telegram y Acciones en esta PC, y guarda esos permisos.'); return;
        }
        await api('POST', 'desktop/configure_confirmations', { enabled: $('tg-remote-confirmations').checked });
        confirmationDirty = false; message('Permiso de confirmación remota guardado. Cada orden requiere su propia confirmación.');
    });
    $('tg-pause').onclick = () => void run(async () => { await api('POST', 'desktop/pause', {}); message('Canal pausado.'); });
    $('tg-resume').onclick = () => void run(async () => { await api('POST', 'desktop/resume', {}); message('Canal reanudado.'); });
    $('tg-refresh').onclick = () => void run(async () => {
        const status = await api('GET', 'status');
        message(status.worker_running ? 'El proceso de Telegram está activo; falta comprobar la conexión con un mensaje.' : 'El proceso de Telegram no está activo.');
    });
    $('tg-save-app').onclick = () => void run(async () => { const api_id = Number($('tg-api-id').value), api_hash = $('tg-api-hash').value.trim(), owner_id = Number($('tg-owner-id').value); $('tg-api-hash').value = ''; await api('POST', 'desktop/configure_app', { api_id, api_hash, owner_id }); message('Datos de aplicación guardados.'); });
    $('tg-save-bot').onclick = () => void run(async () => { const token = $('tg-bot-token').value; $('tg-bot-token').value = ''; await api('POST', 'desktop/configure_bot', { token, enabled: $('tg-bot-enabled').checked, public_url: $('tg-public-url').value.trim() }); botDirty = false; message('Comprobando bot…'); });
    Axx.FEATURES.push({ id: 'telegram', family: 'settings', title: 'Telegram', view: 'settings', description: 'Conecta tu cuenta y tu teléfono.', availability: 'WINDOWS · CONEXIÓN LOCAL' });
    const openFeature = Axx.companion.openFeature.bind(Axx.companion);
    Axx.companion.openFeature = id => { const result = openFeature(id); if (id === 'telegram') { card.scrollIntoView({ block: 'start' }); void refresh(); } return result; };
    if (Axx.flow?.renderLibrary) {
        const renderLibrary = Axx.flow.renderLibrary.bind(Axx.flow);
        Axx.flow.renderLibrary = function () {
            renderLibrary();
            if (this.nav.category !== 'assist' || $('flow-search').value.trim() || $('flow-grid').querySelector('[data-tool="telegram"]')) return;
            const wrapper = document.createElement('div'); wrapper.className = 'flow-tool';
            const button = document.createElement('button'); button.type = 'button'; button.dataset.tool = 'telegram'; button.textContent = 'Telegram'; button.onclick = () => this.select('telegram'); wrapper.append(button); $('flow-grid').append(wrapper);
        };
    }
    Axx.telegramPanel = { open: () => Axx.companion.openFeature('telegram'), refresh };
    poll = setInterval(() => { if (card.isConnected && $('panel')?.dataset.view === 'settings' && !busy) void refresh(); tick(); }, 2000);
    window.addEventListener('pagehide', () => clearInterval(poll), { once: true });
})(window.Axx);
