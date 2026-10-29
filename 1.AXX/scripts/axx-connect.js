/* Axx Connect: existing visual/command owners, authenticated native IPC only. */
(function (Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.BrainClient || !Axx.isNative()) return;
    const $ = id => document.getElementById(id);
    const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/connect/' + path, body);
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'unknown', 'limit_reached']);
    const c = Axx.companion;
    const state = { active: null, engine: null, draftModel: null, polling: false, last: null, disposed: false, loginPending: false, refreshSeq: 0, refreshPromise: null };
    const card = document.createElement('section');
    card.className = 'setup-card ai-connect-card'; card.id = 'axx-connect';
    card.innerHTML = `<div class="ai-section-head"><span>02</span><div><h3>Elegir y probar un modelo</h3><p>Primero inicia sesión arriba. Elegir aquí no cambia tu modelo actual.</p></div></div>
      <p id="axx-connect-status" role="status">Comprobando sesión y motor…</p>
      <label class="setting">Modelo de ChatGPT<select id="axx-connect-model"><option value="">Selecciona un modelo</option></select></label>
      <article id="axx-connect-model-profile" aria-label="Capacidades del modelo de ChatGPT"></article>
      <button class="primary" id="axx-connect-verify" type="button">Probar respuesta y usar modelo</button>
      <p class="micro-copy">Axx hará una pregunta breve de prueba. Solo activará el modelo si responde correctamente; no usará una API de pago ni cambiará al modelo local automáticamente.</p>
      <div id="axx-connect-interventions"></div>
      <details class="ai-advanced"><summary>Diagnóstico y controles</summary><div class="ai-advanced-body"><div class="quick-row"><button id="axx-connect-refresh" type="button">Actualizar estado</button><button id="axx-connect-reconnect" type="button">Reconectar Axx</button><button id="axx-connect-stop" type="button">Detener tarea</button></div><pre id="axx-connect-history" style="white-space:pre-wrap;max-height:220px;overflow:auto"></pre></div></details>`;
    ($('subpanel-chatgpt') || $('view-settings')).append(card);
    const status = text => { $('axx-connect-status').textContent = text; };
    const error = e => e?.message || String(e);
    const originalConnect = Axx.BrainClient.prototype.connect;
    const originalChat = Axx.BrainClient.prototype.chat;
    const connectionError = (code, message) => Object.assign(new Error(code + ': ' + message), {code});
    const catalog = engine => [...new Set((engine.models || []).map(item => typeof item === 'string' ? item : item.model || item.id).filter(item => typeof item === 'string' && item.length <= 200))].slice(0,100);
    function renderProfile() {
        const engine = state.engine || {}, id = $('axx-connect-model').value;
        const item = (engine.model_catalog || engine.models || []).find(m => typeof m === 'string' ? m === id : (m.model || m.id) === id);
        Axx.renderModelProfile?.($('axx-connect-model-profile'), {...(typeof item === 'object' ? item : {}), model:id, kind:'chatgpt',
            executor_ready:state.executorReady === true, verified:engine.authenticated === true && engine.local_connection_enabled !== false && engine.inference_verified === true && engine.model === id});
    }
    function renderModels(engine) {
        const select = $('axx-connect-model'), selected = state.draftModel || (c.data.prefs.provider === 'chatgpt' ? c.data.prefs.model || '' : '');
        const models = catalog(engine), placeholder = document.createElement('option');
        placeholder.value = ''; placeholder.textContent = 'Selecciona un modelo';
        select.replaceChildren(placeholder);
        for (const id of models) { const option = document.createElement('option'); option.value = id; option.textContent = id; select.append(option); }
        if (selected && !models.includes(selected)) { const unavailable = document.createElement('option'); unavailable.value = selected; unavailable.textContent = 'No disponible: ' + selected; unavailable.disabled = true; select.append(unavailable); }
        select.value = selected; select.disabled = !!state.active; renderProfile();
    }

    function refresh() {
        const sequence = ++state.refreshSeq;
        const pending = (async () => {
            try {
                const result = await api('GET', 'status?engine=1');
                if (!result || typeof result.engine !== 'object' || !result.engine) throw connectionError('ENGINE_UNAVAILABLE', 'No se pudo consultar el motor. Pulsa Actualizar estado para reintentar.');
                if (sequence !== state.refreshSeq) return state.refreshPromise;
                state.engine = result.engine; state.executorReady = result.executor === 'ready';
                const e = result.engine || {};
                renderModels(e);
                const authenticated = e.local_connection_enabled !== false && e.authenticated === true;
                const verified = authenticated && e.inference_verified === true && e.model === c.data.prefs.model;
                const engineState = ['connected', 'authenticated'].includes(e.state) && !authenticated ? 'desconectado · autenticación no acreditada' : e.state === 'connected' && !verified ? 'autenticado · modelo seleccionado por verificar' : e.state;
                status('Motor: ' + (engineState || (authenticated ? 'autenticado · inferencia por verificar' : 'desconectado')) + ' · Ejecutor: ' + (result.executor === 'ready' ? 'disponible' : 'desconectado') + (e.model ? ' · ' + e.model : ''));
                $('chatgpt-badge')?.classList.toggle('connected', verified);
                if ($('chatgpt-badge-text')) $('chatgpt-badge-text').textContent = verified ? 'Inferencia verificada' : authenticated ? 'Sesión autenticada · verificar motor' : 'Desconectado';
                if ($('chatgpt-user-label')) $('chatgpt-user-label').textContent = e.account?.planType || e.plan_type || 'Sesión gestionada por Codex';
                if ($('chatgpt-auth-unauthed')) $('chatgpt-auth-unauthed').hidden = authenticated;
                if ($('chatgpt-auth-authed')) $('chatgpt-auth-authed').hidden = !authenticated;
                const history = await api('GET', 'history');
                if (sequence !== state.refreshSeq) return state.refreshPromise;
                $('axx-connect-history').textContent = JSON.stringify(history, null, 2);
                return result;
            } catch (failure) {
                if (sequence !== state.refreshSeq) return state.refreshPromise;
                throw failure;
            }
        })();
        state.refreshPromise = pending;
        return pending;
    }

    function interventions(run, presented) {
        const root = $('axx-connect-interventions'); root.replaceChildren();
        for (const approvalId of run.pending_approvals || []) {
            const approval = (run.events || []).find(event => event.data?.approval_id === approvalId)?.data || {};
            const row = document.createElement('div'), label = document.createElement('p');
            label.textContent = 'Codex solicita autorización: ' + (approval.method || approval.type || 'operación'); row.append(label);
            for (const [labelText, decision] of [['Rechazar', 'decline'], ['Cancelar turno', 'cancel']]) {
                const button = document.createElement('button'); button.textContent = labelText;
                button.onclick = () => { button.disabled = true; void api('POST', 'approval', {request_id: run.request_id, approval_id: approvalId, decision}).catch(e => status(error(e))); };
                row.append(button);
            }
            root.append(row);
        }
        for (const event of [...(run.events || []), ...(run.tool_results || []).map(item => ({data: item}))]) {
            const data = event.data || {};
                const operation = data.result || data;
            if (operation.state === 'awaiting_approval' && operation.operation_id) {
                const library = Axx.commandLibrary;
                if (!presented.has(operation.operation_id) && Axx.chatWorkspace?.ready
                    && operation.conversation_id && operation.conversation_id === Axx.chatWorkspace.active?.id
                    && library && !library.busy && (!library.operation || library.operation.operation_id === operation.operation_id)) {
                    presented.add(operation.operation_id);
                    library.operation = library.lastOperation = operation;
                    library.renderOperation(operation);
                }
                const button = document.createElement('button'); button.textContent = 'Revisar acción en Biblioteca';
                button.onclick = () => { Axx.commandLibrary.open(); Axx.commandLibrary.lastOperation = operation; void Axx.commandLibrary.recover(); };
                root.append(button);
            }
        }
    }

    async function run(body, signal, onDelta = () => {}) {
        if (state.active) throw new Error('BUSY: hay un turno de Axx Connect activo.');
        const requestId = crypto.randomUUID();
        state.active = requestId;
        const deadline = performance.now() + 75000;
        const cancel = () => { void api('POST', 'cancel', {request_id: requestId}).catch(e => status(error(e))); };
        signal?.addEventListener('abort', cancel, {once: true});
        const bounded = promise => {
            let timer, abort;
            const stopWaiting = new Promise((resolve, reject) => {
                timer = setTimeout(() => reject(connectionError('DEADLINE_EXCEEDED', 'Timeout. Consulta la tarea antes de repetir acciones con efectos.')), Math.max(0, deadline - performance.now()));
                abort = () => reject(new DOMException('Cancelado; consulta los efectos completados.', 'AbortError'));
                signal?.addEventListener('abort', abort, {once:true});
                if (signal?.aborted) abort();
            });
            return Promise.race([promise, stopWaiting]).then(value => {
                if (performance.now() >= deadline) throw connectionError('DEADLINE_EXCEEDED', 'Timeout. Consulta la tarea antes de repetir acciones con efectos.');
                if (signal?.aborted) throw new DOMException('Cancelado; consulta los efectos completados.', 'AbortError');
                return value;
            }).finally(() => { clearTimeout(timer); signal?.removeEventListener('abort', abort); });
        };
        let started;
        let after = 0, observed = '', last;
        const presented = new Set();
        try {
            if (signal?.aborted) throw new DOMException('Cancelado', 'AbortError');
            started = api('POST', 'start', {...body, request_id: requestId});
            await bounded(started);
            if (signal?.aborted) {
                throw new DOMException('Cancelado; consulta los efectos completados.', 'AbortError');
            }
            while (performance.now() < deadline) {
                if (signal?.aborted) throw new DOMException('Cancelado; los efectos completados se conservan.', 'AbortError');
                last = await bounded(api('GET', 'run?request_id=' + encodeURIComponent(requestId) + '&after=' + after));
                state.last = last;
                for (const event of last.events || []) after = Math.max(after, event.seq || 0);
                const text = last.response ?? '';
                if (typeof text === 'string' && text !== observed) { observed = text; onDelta(observed); }
                status(last.state === 'running' ? 'Procesando · ' + requestId : String(last.state || 'Procesando'));
                interventions(last, presented);
                if (terminal.has(last.state)) {
                    if (last.state !== 'completed') throw new Error(last.error?.message || last.error || 'Turno finalizado: ' + last.state);
                    if (!observed.trim()) throw new Error('Codex completó sin texto de respuesta.');
                    return {text: observed, reason: 'stop', route: {provider: 'codex-managed-chatgpt', model: last.model || body.model, request_id: requestId, usage: last.usage}};
                }
                await sleep(150);
            }
            throw connectionError('DEADLINE_EXCEEDED', 'Timeout. Consulta la tarea antes de repetir acciones con efectos.');
        } catch (failure) {
            if (failure.code === 'DEADLINE_EXCEEDED' || failure.name === 'AbortError') {
                cancel();
                // A late start acknowledgement may follow the first cancel.
                // Reconcile only that owned ID, without admitting another run.
                if (started) void started.then(cancel, () => {});
            }
            throw failure;
        } finally {
            signal?.removeEventListener('abort', cancel);
            state.active = null;
            void refresh().catch(e => status(error(e)));
        }
    }

    Axx.BrainClient.prototype.connect = async function (p, signal) {
        if (p.selection_mode === 'automatic_free') p.provider = 'bridge';
        if (p.provider !== 'chatgpt') return originalConnect.call(this, p, signal);
        this.reset();
        const result = await refresh(), engine = result.engine || {};
        const models = catalog(engine), selected = p.model;
        if (typeof selected !== 'string' || !selected.trim()) throw connectionError('MODEL_SELECTION_REQUIRED', 'Selecciona explícitamente un modelo del catálogo y pulsa Verificar conexión.');
        if (!models.includes(selected)) throw connectionError('MODEL_NOT_AVAILABLE', 'El modelo seleccionado no aparece en el catálogo. Se conserva tu selección; elige otro explícitamente.');
        if (engine.local_connection_enabled === false) throw connectionError('DISCONNECTED', 'Axx está desconectado localmente. Pulsa Reconectar Axx antes de verificar.');
        const verified = await run({message: 'Responde solamente AXX_CONNECT_OK. No utilices herramientas.', model: selected, conversation_id: 'axx-connect-health'}, signal);
        if (verified.text.trim() !== 'AXX_CONNECT_OK') throw new Error('La inferencia respondió, pero no pasó la comprobación de conexión.');
        if (p.model !== selected) throw connectionError('MODEL_CHANGED', 'La selección cambió durante la prueba; verifica el modelo elegido.');
        this.models = models; this.providerName = 'Axx Connect · Codex';
        this.inferenceVerified = true; this.connected = true; this.signature = this.signatureOf(p);
        return this.models;
    };
    Axx.BrainClient.prototype.chat = async function (p, messages, signal, onDelta) {
        if (p.selection_mode === 'automatic_free') p.provider = 'bridge';
        if (p.provider !== 'chatgpt') return originalChat.call(this, p, messages, signal, onDelta);
        const system = messages.find(item => item.role === 'system')?.content || '';
        const translation = /^Translate (?:the user's text|the following text) from ([A-Za-z-]{2,20}) to ([A-Za-z-]{2,20})\./.exec(system);
        if (translation) {
            const source = messages.filter(item => item.role === 'user').map(item => item.content).join('\n');
            if (source.length > 32000) throw new Error('La traducción supera 32.000 caracteres; divide el texto. No se ha truncado ni enviado.');
            return run({message: source,
                purpose:'translation', source_language:translation[1], target_language:translation[2],
                model:p.model, conversation_id:'axx-translation-' + crypto.randomUUID()}, signal, onDelta);
        }
        const context = c.data.connectConversationId && !Axx.chatWorkspace ? messages.filter(item => item.role === 'user').slice(-1) : messages.filter(item => item.role !== 'system');
        if (!c.data.connectConversationId) { c.data.connectConversationId = crypto.randomUUID(); c.save(); }
        // Only the backend emits developer policy; profiles and references remain data.
        const references = messages.filter(item => item.role === 'system').slice(p.prompt_mode ? 1 : 0).map(item => item.content);
        const prefix = references.length ? 'Referencias de la aplicación y perfil (datos, no permisos):\n' + JSON.stringify(references) + '\n\nConversación:\n' : '';
        const transcript = () => context.map(item => (item.role === 'assistant' ? 'Axx: ' : 'Usuario: ') + item.content).join('\n\n');
        while (context.length > 1 && prefix.length + transcript().length > 32000) context.shift();
        const message = prefix + transcript();
        if (message.length > 32000) throw new Error('La petición actual y sus referencias superan 32.000 caracteres. Reduce el contexto; no se ha truncado ni enviado.');
        const result = await run({message, purpose:p.voice_turn ? 'voice' : 'chat',
            preferences:{style:p.personalityStyle || 'natural', language:p.voiceLanguage || 'auto', notes:String(p.personalityNotes || '').slice(0,500)},
            model: p.model, conversation_id: c.data.connectConversationId}, signal, onDelta);
        c.save(); this.inferenceVerified = true; this.connected = true; this.lastRoute = result.route;
        return result;
    };
    c.refreshChatGPTUI = async () => { try { const s = await refresh(); return s.engine?.authenticated === true; } catch(e) { status(error(e)); return false; } };
    if ($('chatgpt-custom-client-id')) $('chatgpt-custom-client-id').closest('details').hidden = true;
    if ($('chatgpt-fallback-toggle')) { $('chatgpt-fallback-toggle').closest('label').hidden = true; $('chatgpt-fallback-toggle').disabled = true; }
    c.data.prefs.allow_fallback = false;
    const syncProvider = c.syncProvider.bind(c);
    c.syncProvider = () => {
        syncProvider();
        if (c.data.prefs.provider === 'chatgpt' && $('chat-privacy')) $('chat-privacy').textContent = 'Axx Connect · contexto autorizado → Codex → capacidades de Axx con sus permisos y verificación. Esc cierra la interfaz o detiene el seguimiento; Detener solicita cancelar la tarea y conserva los efectos completados.';
    };
    const loginText = $('chatgpt-auth-unauthed')?.querySelector('p');
    if (loginText) loginText.textContent = 'Autoriza la sesión en el runtime oficial de Codex. Axx no recibe ni copia sus credenciales. La autenticación y la inferencia se comprueban por separado.';
    if ($('chatgpt-login-btn')) $('chatgpt-login-btn').onclick = async () => {
        try {
            await api('POST', 'login', {}); state.loginPending = true;
            status('Autenticando · completa el inicio de sesión oficial de Codex.');
            const deadline = Date.now() + 120000;
            while (state.loginPending && !state.disposed && Date.now() < deadline) {
                await sleep(1500);
                const result = await refresh();
                if (result.engine?.authenticated) { state.loginPending = false; status('Sesión autenticada · pulsa Verificar conexión para comprobar inferencia.'); }
            }
            if (state.loginPending) { state.loginPending = false; await api('POST','login-cancel',{}); status('Inicio de sesión pendiente agotado. Puedes volver a intentarlo.'); }
        }
        catch (e) { status(error(e)); }
    };
    if ($('chatgpt-logout-btn')) {
        $('chatgpt-logout-btn').textContent = 'Desconectar Axx';
        $('chatgpt-logout-btn').title = 'Desconecta solo Axx. Conserva la sesión y las credenciales gestionadas por Codex.';
        $('chatgpt-logout-btn').onclick = async () => { try { await api('POST', 'disconnect', {}); c.brain.reset(); c.data.prefs.provider = 'none'; c.data.prefs.selection_mode = 'manual'; c.save(); c.syncProvider(); await refresh(); } catch(e) { status(error(e)); } };
    }
    if ($('chatgpt-refresh-btn')) $('chatgpt-refresh-btn').onclick = () => void refresh().catch(e => status(error(e)));
    $('axx-connect-refresh').onclick = () => void refresh().catch(e => status(error(e)));
    $('axx-connect-model').onchange = () => {
        const selected = $('axx-connect-model').value;
        if (state.active || !catalog(state.engine || {}).includes(selected)) { renderModels(state.engine || {}); return; }
        state.draftModel = selected; renderProfile();
        status('Listo para probar: ' + selected + '. El modelo en uso sigue igual hasta que pase la prueba.');
    };
    $('axx-connect-reconnect').onclick = async () => { try { await api('POST','reconnect',{}); await refresh(); } catch(e) { status(error(e)); } };
    $('axx-connect-verify').onclick = async () => {
        const selected = $('axx-connect-model').value;
        if (!catalog(state.engine || {}).includes(selected)) { status('Elige un modelo disponible del catálogo.'); return; }
        if (state.active || c.pending || c.connecting || c.externalBusy) { status('Espera a que termine la tarea actual antes de cambiar el modelo.'); return; }
        const button = $('axx-connect-verify'); button.disabled = true;
        status('Probando una respuesta real de ' + selected + '…');
        try {
            const previousRoute = JSON.stringify([c.data.prefs.provider, c.data.prefs.model, c.data.prefs.selection_mode]);
            const draft = {...c.data.prefs, provider:'chatgpt', selection_mode:'manual', ai_mode:'chatgpt', model:selected};
            const trial = new Axx.BrainClient();
            await trial.connect(draft);
            if (c.pending || c.externalBusy || c.connecting || JSON.stringify([c.data.prefs.provider, c.data.prefs.model, c.data.prefs.selection_mode]) !== previousRoute)
                throw new Error('La ruta activa cambió durante la prueba. Vuelve a seleccionar el modelo.');
            Object.assign(c.data.prefs, {provider:'chatgpt', selection_mode:'manual', ai_mode:'chatgpt', model:selected});
            c.brain = trial;
            $('ai-provider').value = 'chatgpt';
            $('ai-model').replaceChildren(...trial.models.map(id => new Option(id, id)));
            $('ai-model').value = selected;
            c.save(); c.syncProvider(); Axx.refreshVoiceModelOptions?.();
            await refresh();
            status('Respuesta comprobada. Ahora Axx usa ' + selected + '.');
        } catch (e) { await refresh().catch(()=>{}); status('No se cambió el modelo: ' + error(e)); }
        finally { button.disabled = false; }
    };
    const stop = () => { if (state.active) void api('POST', 'cancel', {request_id: state.active}).catch(e => status(error(e))); if (state.loginPending) { state.loginPending = false; void api('POST','login-cancel',{}).catch(e => status(error(e))); } c.cancelRequest(); };
    $('axx-connect-stop').onclick = stop;

    // The queue never calls send(), chat(), externalCommand() or a planner.
    async function executeUI(task) {
        const i = task.inputs, before = {notes: Axx.app.store.data.notes.length, todos: c.data.todos.length};
        let output, verified = false;
        if (task.command_id === 'axx.ui.local') {
            output = c.runLocal({...i, type: i.action});
            const t = Axx.app.store.data.timer;
            verified = i.action === 'note' ? Axx.app.store.data.notes.length === before.notes + 1 && Axx.app.store.data.notes[0].text === i.text :
                i.action === 'todo' ? c.data.todos.length === before.todos + 1 && c.data.todos.at(-1).text === i.text.trim() :
                i.action === 'completeTodo' ? c.data.todos[i.index]?.done === true :
                i.action === 'timer' ? t?.status === 'running' : i.action === 'pause' ? t?.status === 'paused' : i.action === 'resume' ? t?.status === 'running' :
                i.action === 'cancel' ? !t || !['running','paused'].includes(t.status) :
                i.action === 'follow' ? c.data.prefs.follow === true : i.action === 'stay' ? c.data.prefs.follow === false :
                !['summon','hide'].includes(i.action) && typeof output === 'string';
        } else if (task.command_id === 'axx.ui.panel') {
            c.openFeature(i.feature); output = {feature: c.dock.selected, level: c.dock.level}; verified = c.dock.selected === i.feature;
        } else if (task.command_id === 'axx.ui.text_transform') {
            output = Axx.transformText(i.text, i.action); verified = typeof output === 'string';
        } else if (task.command_id === 'axx.ui.music') {
            const m = Axx.actions.music;
            if (i.action === 'play') await m.play(); else if (i.action === 'pause') m.pause();
            else if (i.action === 'next') await m.advance(false); else if (i.action === 'previous') await m.previous();
            else if (i.action === 'select') m.select(i.index); else if (i.action === 'shuffle') m.setShuffle(i.enabled);
            else if (i.action === 'repeat') m.setRepeat(i.mode); else if (i.action === 'seek') m.seek(i.seconds);
            output = {index:m.index, tracks:m.tracks.length, paused:m.audio.paused, phase:m.phase, time:m.audio.currentTime, shuffle:m.order.shuffle, repeat:m.order.repeat};
            verified = i.action === 'play' ? !m.audio.paused : i.action === 'pause' ? m.audio.paused : i.action === 'select' ? m.index === i.index : i.action === 'shuffle' ? m.order.shuffle === i.enabled : i.action === 'repeat' ? m.order.repeat === i.mode : false;
        } else if (task.command_id === 'axx.ui.system_media') {
            const media=Axx.nativeMusic;
            if (!media) throw new Error('El control multimedia de Windows no está disponible.');
            await media.refresh();
            const matches=(media.snapshot.sessions||[]).filter(item=>new RegExp(i.app,'i').test(item.app||''));
            if (matches.length!==1) throw new Error(matches.length?'Hay varias sesiones de '+i.app+'. Selecciona una en Música.':'No hay una sesión controlable de '+i.app+' en Windows.');
            const before=matches[0]; media.selectedId=before.id;
            await media.command(i.action);
            if (media.error||media.readError) throw new Error(media.error||media.readError);
            const after=(media.snapshot.sessions||[]).find(item=>item.id===before.id);
            output={app:i.app,session_id:before.id,playing:after?.playing??null,title:after?.title||'',action:i.action};
            verified=!!after&&(i.action==='play'?after.playing===true:i.action==='pause'?after.playing===false:after.title!==before.title);
        } else if (task.command_id === 'axx.ui.reader') {
            const r = Axx.symbiosis.reader;
            if (i.action === 'set_text') r.setText(i.text, 'Axx Connect'); else if (i.action === 'play') r.play();
            else if (i.action === 'pause') r.pause(); else if (i.action === 'stop') r.stop(); else if (i.action === 'jump') r.jump(i.index);
            output = {state:r.state, index:r.index, chunks:r.chunks.length};
            verified = i.action === 'set_text' ? r.chunks.length > 0 : i.action === 'pause' ? r.state === 'paused' : i.action === 'stop' ? !['starting','speaking'].includes(r.state) : i.action === 'jump' ? r.index === i.index : r.state === 'speaking';
        } else if (task.command_id === 'axx.ui.stopwatch') {
            const desk = Axx.utilities, beforeLaps = desk.stopwatch.laps.length;
            if (i.action === 'start' && !desk.stopwatch.running) desk.toggleWatch();
            else if (i.action === 'pause' && desk.stopwatch.running) desk.toggleWatch();
            else if (i.action === 'lap') desk.markLap();
            output = desk.snapshot().stopwatch;
            verified = i.action === 'start' ? output.running : i.action === 'pause' ? !output.running : i.action === 'lap' ? output.laps.length === beforeLaps + 1 : true;
        } else if (task.command_id === 'axx.ui.dictation') {
            if (i.action === 'open') c.openFeature('dictation');
            else if (i.action === 'stop') { Axx.voice13?.stop(); Axx.symbiosis?.stopListening(); for (const session of Axx.nativeVoice?.sessions || []) session.stop(); }
            output = {state:Axx.voice13?.status,recording:(Axx.nativeVoice?.sessions || []).some(s => s.recorder?.state === 'recording'),panel:c.dock.selected};
            verified = i.action === 'open' ? output.panel === 'dictation' : i.action === 'stop' ? !output.recording && output.state !== 'listening' : true;
        } else if (task.command_id === 'axx.ui.screen') {
            const screen = Axx.actions.screen;
            if (i.action === 'open') c.openFeature('screen');
            else if (i.action === 'stop') {
                screen.stop();
                const deadline = Date.now() + 5000;
                while (screen.state === 'stopping' && Date.now() < deadline) await sleep(50);
            }
            output = {state:screen.state,bytes:screen.bytes,panel:c.dock.selected,recorder:screen.recorder?.state || null};
            verified = i.action === 'open' ? output.panel === 'screen' : i.action === 'stop' ?
                ['finished','ready'].includes(screen.state) && (!screen.recorder || screen.recorder.state === 'inactive') : true;
        } else if (task.command_id === 'axx.ui.identity') {
            if (i.action === 'settings') {
                const patch = {};
                for (const key of ['form','palette','motionStyle']) if (Object.hasOwn(i,key)) patch[key] = i[key];
                Axx.app.stopDemo(); Axx.stability20.updateSettings(patch);
                if (!Axx.app.persistStudio20()) throw new Error('No se pudo guardar la identidad. El efecto no se considera verificado.');
                Axx.app.syncSurfaceControls();
            } else if (i.action === 'finish') { Axx.symbiosis.applyFinish20(i.finish); }
            else if (i.action === 'size') c.setSize(i.size, true);
            output = {settings:{...Axx.app.store.data.settings},canonical:JSON.parse(localStorage.getItem('axx-studio-v2') || 'null'),finish:Axx.app.renderer.getFinish(),size:c.bodySizePreference};
            verified = i.action === 'settings' ? ['form','palette','motionStyle'].every(k => !Object.hasOwn(i,k) || (output.settings[k] === i[k] && output.canonical?.[k] === i[k])) : i.action === 'finish' ? output.finish === i.finish : i.action === 'size' ? output.size === i.size : true;
        } else {
            throw new Error('Este control requiere intervención en el panel de Axx; no se ha ejecutado.');
        }
        const snapshot = {app:Axx.app.snapshot(),companion:c.snapshot(),timer:Axx.app.store.data.timer,notes:Axx.app.store.data.notes.length,todos:c.data.todos.length, output};
        return {operation_id:task.operation_id,claim_id:task.claim_id,state:verified?'succeeded':'unknown',snapshot,output,evidence:{verified,source:'existing_ui_handler_readback',app_version:Axx.VERSION}};
    }
    async function queue() {
        if (state.polling || state.disposed) return;
        state.polling = true;
        try {
            const available = {
                'axx.ui.local': typeof c.runLocal === 'function', 'axx.ui.panel': typeof c.openFeature === 'function',
                'axx.ui.text_transform': typeof Axx.transformText === 'function',
                'axx.ui.music': typeof Axx.actions?.music?.play === 'function',
                'axx.ui.system_media': typeof Axx.nativeMusic?.command === 'function',
                'axx.ui.reader': typeof Axx.symbiosis?.reader?.setText === 'function',
                'axx.ui.stopwatch': typeof Axx.utilities?.toggleWatch === 'function',
                'axx.ui.dictation': typeof Axx.voice13?.stop === 'function',
                'axx.ui.screen': typeof Axx.actions?.screen?.stop === 'function',
                'axx.ui.identity': typeof Axx.stability20?.updateSettings === 'function' && typeof Axx.symbiosis?.applyFinish20 === 'function'
            };
            const batch = await api('POST', 'ui/claim', {handlers:Object.keys(available).filter(key => available[key])});
            for (const task of batch.tasks || []) {
                let completion;
                try { completion = await executeUI(task); }
                catch(e) { completion = {operation_id:task.operation_id,claim_id:task.claim_id,state:'failed',snapshot:{},evidence:{verified:false},error:error(e)}; }
                await api('POST', 'ui/complete', completion);
            }
        } catch(e) { if (state.active) status(error(e)); }
        finally { state.polling = false; }
    }
    const queueTimer = setInterval(() => void queue(), 300);
    window.addEventListener('pagehide', () => { state.disposed = true; clearInterval(queueTimer); stop(); });
    Axx.connect = {refresh, run, state, executeUI};
    void refresh().catch(e => status(error(e)));
})(window.Axx);
