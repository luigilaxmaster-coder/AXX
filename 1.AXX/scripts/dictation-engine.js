/* Local final-segment dictation. This module never invokes chat or commands. */
(function () {
    'use strict';
    class Segmenter {
        constructor(rate, emit) { this.rate = rate; this.emit = emit; this.reset(); }
        reset() { this.frames = []; this.preroll = []; this.samples = 0; this.quiet = 0; this.calibration = 0; this.noise = 0; this.target = null; }
        feed(frame, target) {
            if (!(frame instanceof Float32Array) || !frame.length || !target) return;
            let energy = 0; for (const sample of frame) energy += sample * sample;
            const rms = Math.sqrt(energy / frame.length), duration = frame.length / this.rate;
            if (this.calibration < .48) { this.noise = Math.min(.04, this.calibration ? this.noise * .8 + rms * .2 : rms); this.calibration += duration; return; }
            const voiced = rms > Math.max(.004, this.noise * 2.5 + .002);
            if (this.target && this.target !== target) this.flush();
            if (!this.samples && !voiced) {
                this.noise = rms < this.noise ? this.noise * .85 + rms * .15 : this.noise * .997 + Math.min(rms, .08) * .003;
                this.preroll.push(frame.slice()); if (this.preroll.length > 2) this.preroll.shift(); return;
            }
            if (!this.samples) { this.target = target; this.frames = this.preroll; this.preroll = []; this.samples = this.frames.reduce((n, f) => n + f.length, 0); }
            this.frames.push(frame.slice()); this.samples += frame.length;
            this.quiet = voiced ? 0 : this.quiet + duration;
            if (this.quiet >= .55 || this.samples / this.rate >= 10) this.flush();
        }
        flush() {
            if (!this.samples) return;
            const pcm = new Float32Array(this.samples); let offset = 0;
            for (const frame of this.frames) { pcm.set(frame, offset); offset += frame.length; }
            const target = this.target;
            this.frames = []; this.samples = this.quiet = 0; this.target = null;
            this.emit(pcm, this.rate, target);
        }
    }
    function wav(pcm, rate) {
        const buffer = new ArrayBuffer(44 + pcm.length * 2), view = new DataView(buffer);
        const word = (at, text) => { for (let i = 0; i < text.length; i++) view.setUint8(at + i, text.charCodeAt(i)); };
        word(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); word(8, 'WAVE'); word(12, 'fmt ');
        view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
        view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
        word(36, 'data'); view.setUint32(40, pcm.length * 2, true);
        for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 32767, true);
        return buffer;
    }
    function settings(value = {}) {
        if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !['language', 'model', 'microphone', 'profile', 'dictionary', 'output'].includes(k))) throw Error('Ajustes de dictado inválidos.');
        const result = { language: 'auto', model: '', microphone: '', profile: 'literal', dictionary: [], output: 'insert', ...value };
        if (!/^(auto|[a-z]{2,3})$/.test(result.language) || typeof result.model !== 'string' || !/^[a-z0-9.-]{0,100}$/.test(result.model)
            || typeof result.microphone !== 'string' || result.microphone.length > 1024 || !['literal', 'conversation', 'technical', 'code'].includes(result.profile)
            || !['insert', 'copy'].includes(result.output) || !Array.isArray(result.dictionary) || result.dictionary.length > 100) throw Error('Ajustes de dictado inválidos.');
        for (const pair of result.dictionary) if (!Array.isArray(pair) || pair.length !== 2 || pair.some(t => typeof t !== 'string' || !t.trim() || t.length > 120 || /[\x00-\x1f\x7f]/.test(t))) throw Error('El diccionario admite hasta 100 pares de texto.');
        return result;
    }
    function processText(text, config) {
        if (typeof text !== 'string' || text.length > 8000) throw Error('Transcripción inválida.');
        if (config.profile === 'literal' || config.profile === 'code') return text;
        for (const [from, to] of config.dictionary) {
            const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            text = text.replace(new RegExp('(?<![\\p{L}\\p{N}_])' + escaped + '(?![\\p{L}\\p{N}_])', 'giu'), () => to);
        }
        return text.trim().replace(/[ \t]+/g, ' ');
    }
    function shortcutChord(text, activation) {
        const parts = text.toUpperCase().split('+').map(p => p.trim()), key = parts.pop(); let modifiers = 0;
        if (!/^[A-Z]$/.test(key)) throw Error('El atajo debe terminar en una letra A–Z.');
        for (const part of parts) { const bit = { CTRL: 2, ALT: 1, SHIFT: 4 }[part]; if (!bit || modifiers & bit) throw Error('Modificador inválido.'); modifiers |= bit; }
        return { key: key.charCodeAt(0), modifiers, activation };
    }
    if (typeof module !== 'undefined' && module.exports) { module.exports = { Segmenter, wav, settings, processText, shortcutChord }; return; }
    const Axx = window.Axx;
    if (!Axx?.nativeVoice || !window.__TAURI__?.core) return;
    const native = request => window.__TAURI__.core.invoke('dictation_control', { request });
    const voice = Axx.nativeVoice;
    let config; try { config = settings(JSON.parse(localStorage.getItem('axx.dictation.v1') || '{}')); } catch { config = settings(); }
    let mode = 'off', phase = 'OFF', session = null, target = null, generation = 0, sequence = 0;
    let stream = null, segmenter = null, starting = false, decoding = false, probing = false;
    let queue = [], pending = [], currentRequest = null, lastError = '', panel;
    let held = false, holdReleased = null;
    let manualFinishing = false;
    let activeShortcut = { key: 68, modifiers: 7, activation: 'toggle', registered: false };
    function commandShortcutMatches(shortcut) {
        try { const command = shortcutChord(voice.wake?.hotkey || '', 'toggle'); return command.key === shortcut.key && command.modifiers === shortcut.modifiers; }
        catch { return false; }
    }
    const capture = { stop: () => { pause(); } };
    let releasePromise = Promise.resolve(), nativeReleasing = false;
    function releaseNative(action = 'audio_stop') {
        if (stream || starting) nativeReleasing = true;
        const release = releasePromise.catch(() => {}).then(() => native({ action })).then(report => {
            if (report?.microphone_open !== false) throw Error('No se confirmó el cierre del micrófono nativo.');
            if (releasePromise === release) { nativeReleasing = false; render(); }
        });
        releasePromise = release;
        void releasePromise.catch(() => { if (releasePromise === release) { nativeReleasing = true; phase = 'ERROR'; lastError = 'No se confirmó el cierre del micrófono; la captura queda bloqueada.'; render(); } });
        return releasePromise;
    }
    voice.waitForNativeCaptureRelease = () => releasePromise;
    const labels = { OFF: 'apagado', ARMED: 'esperando un campo editable', CAPTURING: 'escuchando', DECODING: 'transcribiendo', PAUSED: 'en pausa', ERROR: 'detenido por error' };
    const speechBusy = () => !!(Axx.liveConversation?.active || Axx.symbiosis?.liveActive || Axx.companion?.speaking || [Axx.symbiosis?.reader, Axx.voice13?.reader].some(r => ['starting', 'speaking'].includes(r?.state)));
    const snapshot = () => ({ api_version: 1, mode, state: phase, microphone_open: !!stream || nativeReleasing, decoding, waiting_for_voice: mode !== 'off' && speechBusy(), pending_count: pending.length, queue_length: queue.length, error: lastError });
    function render() {
        window.dispatchEvent(new CustomEvent('axx-dictation-state', { detail: snapshot() }));
        if (panel) {
            panel.querySelector('[data-status]').textContent = `Dictado: ${snapshot().waiting_for_voice ? 'esperando que termine la voz' : labels[phase]}${nativeReleasing ? ' · cerrando micrófono' : stream ? ' · micrófono abierto' : ''}${decoding ? ' · reconociendo' : ''}${lastError ? ' · ' + lastError : ''}`;
            panel.querySelector('[data-mode]').value = mode;
            panel.querySelector('[data-pending]').textContent = pending.map(p => `${p.status}: ${p.text}`).join('\n');
            for (const el of panel.querySelectorAll('[data-config]')) el.disabled = mode !== 'off';
        }
        if ((mode !== 'off' || nativeReleasing) && !speechBusy() && (!voice.activeCapture || voice.activeCapture === capture)) {
            const indicator = document.getElementById('speech-indicator'), label = document.getElementById('speech-status');
            if (indicator) indicator.hidden = false;
            if (label) label.textContent = `Dictado ${labels[phase]} · ${nativeReleasing ? 'cerrando micrófono' : stream ? 'micrófono abierto' : 'sin captura'} · Esc para cancelar`;
        } else if (mode === 'off' && !nativeReleasing && !voice.activeCapture && !Axx.companion?.speaking) {
            const indicator = document.getElementById('speech-indicator'); if (indicator) indicator.hidden = true;
        }
    }
    function release() {
        if (stream || starting) void releaseNative();
        stream = null;
        segmenter?.reset(); segmenter = null;
        if (voice.activeCapture === capture) voice.activeCapture = null;
    }
    function cancelAudio() {
        generation++; release(); queue = [];
        holdReleased?.(); holdReleased = null;
        if (currentRequest) voice.cancelPromise = Axx.backendRequest('POST', '/axx-api/speech/cancel', { request_id: currentRequest }).catch(() => {});
        currentRequest = null; decoding = false;
    }
    function pause() { cancelAudio(); target = null; phase = 'PAUSED'; render(); }
    function stop() {
        held = manualFinishing = false;
        mode = 'off'; cancelAudio(); target = session = null; pending = []; phase = 'OFF'; lastError = '';
        void releaseNative('stop');
        const indicator = document.getElementById('speech-indicator'); if (indicator && !nativeReleasing && !voice.activeCapture && !Axx.companion?.speaking) indicator.hidden = true;
        render();
    }
    function endManual() {
        if (!manualFinishing || decoding || queue.length) return;
        manualFinishing = false; mode = 'off'; phase = 'OFF'; target = session = null; generation++;
        void releaseNative('stop');
        const indicator = document.getElementById('speech-indicator'); if (indicator && !nativeReleasing && !voice.activeCapture && !Axx.companion?.speaking) indicator.hidden = true;
        render();
    }
    async function start(next = 'focus', holding = false) {
        if (!['manual', 'focus'].includes(next)) throw Error('Modo de dictado inválido.');
        stop(); held = holding; const id = generation;
        mode = next; phase = 'ARMED';
        if (Axx.symbiosis?.use === 'command') Axx.symbiosis.dictation.stop();
        render();
        try {
            await releasePromise;
            if (id !== generation) return;
            const report = await Axx.backendRequest('GET', '/axx-api/speech/models');
            if (id !== generation) return;
            if (config.model && !report.models?.some(m => m.id === config.model && m.available)) throw Error('El motor/modelo elegido no está preparado localmente.');
            if (!config.model) await voice.requireTranscription();
            if (id !== generation) return;
            const result = await native({ action: 'start' });
            if (id !== generation) return;
            session = result.session; sequence = 0; render(); await tick();
        } catch (error) { if (id === generation) stop(); throw error; }
    }
    function retain(text, status) {
        if (pending.length >= 10) { pause(); lastError = 'Buffer pendiente lleno; revise o descarte el texto antes de continuar.'; }
        else pending.push({ text, status });
    }
    async function drain() {
        if (decoding || !queue.length) return;
        const id = generation, item = queue.shift(), activeSession = session; decoding = true; render();
        const requestId = 'dictation-' + crypto.randomUUID(); currentRequest = requestId; let finalText = '';
        try {
            const bytes = new Uint8Array(wav(item.pcm, item.rate)); item.pcm = null;
            let binary = ''; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
            const body = { audio_base64: btoa(binary), mime: 'audio/wav', language: config.language, task: 'transcribe', request_id: requestId, ...(config.model ? { model: config.model } : {}) };
            const result = await Axx.backendRequest('POST', '/axx-api/speech/transcribe', body); body.audio_base64 = ''; binary = '';
            if (id !== generation || activeSession !== session) return;
            const text = processText(result.text || '', config).replace(/[\r\n\t]+/g, ' ').trim();
            if (!text) return;
            finalText = text;
            if (held) await new Promise(resolve => { holdReleased = resolve; });
            if (id !== generation || activeSession !== session) return;
            if (config.output === 'copy') { await navigator.clipboard.writeText(text); }
            else {
                const receipt = await native({ action: 'commit', session: activeSession, target: item.target, sequence: item.sequence, text: text + ' ' });
                if (id !== generation) return;
                if (!receipt || !['inserted', 'pending', 'blocked', 'uncertain'].includes(receipt.status)) throw Error('Recibo inválido.');
                if (receipt.status !== 'inserted') retain(text, receipt.status);
            }
        } catch (error) {
            if (id === generation) { if (finalText) retain(finalText, 'uncertain'); lastError = 'El segmento no se pudo completar; no se reintentó.'; phase = 'ERROR'; cancelAudio(); render(); }
        } finally {
            item.pcm = null;
            if (id === generation) { currentRequest = null; decoding = false; render(); void drain(); endManual(); }
        }
    }
    async function beginCapture() {
        if (starting || stream || phase === 'PAUSED' || phase === 'ERROR' || speechBusy() || !target || !voice.acquireCapture(capture, false)) return;
        starting = true; const id = generation;
        try {
            await voice.cancelPromise;
            await releasePromise;
            if (id !== generation) return;
            const currentFocus = await native({ action: 'probe', session });
            if (id !== generation || speechBusy() || !currentFocus.editable || currentFocus.target !== target) { if (id === generation) { phase = 'ARMED'; render(); } return; }
            const acquired = await native({ action: 'audio_start', session, device: config.microphone });
            if (id !== generation) { await releaseNative(); return; }
            if (!acquired?.capture || acquired.sample_rate !== 16000 || acquired.microphone_open !== true) throw Error('Captura nativa inválida.');
            stream = acquired.capture;
            segmenter = new Segmenter(16000, (pcm, sampleRate, destination) => {
                if (queue.length >= 2) { pause(); lastError = 'El reconocimiento va retrasado. Reanude cuando termine.'; render(); return; }
                queue.push({ pcm, rate: sampleRate, target: destination, sequence: ++sequence }); void drain();
            });
            if (id !== generation) return;
            phase = 'CAPTURING'; render();
        } catch (error) { if (id === generation) { cancelAudio(); phase = 'ERROR'; lastError = 'No se pudo iniciar el audio local. Active AXX y revise el permiso o micrófono.'; render(); } }
        finally { starting = false; }
    }
    async function tick() {
        if (!session || probing || mode === 'off') return;
        probing = true; const id = generation;
        try {
            const focus = await native({ action: 'probe', session });
            if (id !== generation || mode === 'off') return;
            target = focus.editable ? focus.target : null;
            if (stream && focus.microphone_open === false) { segmenter?.flush(); release(); phase = 'ARMED'; }
            if (speechBusy()) { if (stream || starting) pause(); render(); return; }
            if (!target) { if (stream) { segmenter?.flush(); release(); } if (!['PAUSED', 'ERROR'].includes(phase)) phase = 'ARMED'; render(); }
            else await beginCapture();
        } catch { if (id === generation) stop(); }
        finally { probing = false; }
    }
    const api = Axx.dictation = {
        status: snapshot, start, stop, pause,
        resume() { if (session) { phase = 'ARMED'; lastError = ''; render(); void tick(); } },
        finish() {
            if (mode === 'manual') manualFinishing = true;
            if (starting) { pause(); endManual(); return; }
            segmenter?.flush();
            if (mode === 'manual') { release(); phase = 'DECODING'; render(); endManual(); }
        },
        configure(value) { if (mode !== 'off') throw Error('Apague el dictado para cambiar ajustes.'); config = settings(value); localStorage.setItem('axx.dictation.v1', JSON.stringify(config)); return { ...config }; },
        settings: () => structuredClone(config), pending: () => structuredClone(pending), discardPending() { pending = []; render(); },
        async copyPending() { await navigator.clipboard.writeText(pending.map(p => p.text).join('\n')); },
        async configureShortcut(shortcut) {
            if (mode !== 'off') throw Error('Apague el dictado antes de cambiar el atajo.');
            if (commandShortcutMatches(shortcut)) throw Error('El atajo ya pertenece a comandos de voz.');
            const report = await window.__TAURI__.core.invoke('dictation_shortcut', { shortcut });
            if (!report?.registered) throw Error('Atajo no disponible.');
            activeShortcut = { ...report.shortcut, registered: true };
            localStorage.setItem('axx.dictation.shortcut.v1', JSON.stringify(report.shortcut)); return report;
        },
        conflictsWithShortcut(combo) {
            try { const other = shortcutChord(combo, 'toggle'); return activeShortcut.registered && other.key === activeShortcut.key && other.modifiers === activeShortcut.modifiers; }
            catch { return false; }
        },
        async transcribeFile(file, { translate = false, targetLanguage = 'en' } = {}) {
            if (!(file instanceof File) || !file.size || file.size > 1400 * 1024 || mode !== 'off' || !['audio/wav', 'audio/x-wav', 'audio/webm', 'audio/ogg', 'audio/mp4'].includes(file.type)) throw Error('Archivo no compatible: máximo 1,4 MB y 60 s; apague el dictado.');
            if (translate && targetLanguage !== 'en') throw Error('La traducción local verificada solo admite destino inglés.');
            const audio = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(Error('No se pudo leer el archivo.')); reader.onload = () => resolve(reader.result.split(',')[1]); reader.readAsDataURL(file); });
            return Axx.backendRequest('POST', '/axx-api/speech/transcribe', { audio_base64: audio, mime: file.type, language: config.language, task: translate ? 'translate' : 'transcribe', ...(config.model ? { model: config.model } : {}) });
        },
    };
    function mount() {
        const host = document.getElementById('voice-panel-controls'); if (!host || host.querySelector('#axx-dictation')) return;
        panel = document.createElement('details'); panel.id = 'axx-dictation';
        panel.innerHTML = '<summary>Dictar donde escriba</summary><p>Escucha local, escribe sin enviar. Ctrl+Alt+Mayús+D activa o termina; Esc cancela. Solo campos editables verificados.</p><label>Modo<select data-mode><option value="off">OFF</option><option value="manual">MANUAL</option><option value="focus">CONTINUO por enfoque</option></select></label><p data-status role="status" aria-live="polite"></p><button type="button" data-pause>Pausar</button><button type="button" data-resume>Reanudar</button><button type="button" data-finish>Terminar frase</button><label>Modelo por tarea<select data-config="model"><option value="">Motor actual de Axx</option></select></label><label>Idioma<input data-config="language" maxlength="3" aria-label="Código de idioma o auto"></label><label>Micrófono<select data-config="microphone"><option value="">Predeterminado</option></select></label><label>Perfil<select data-config="profile"><option value="literal">Literal</option><option value="conversation">Conversación</option><option value="technical">Técnico</option><option value="code">Código</option></select></label><label>Salida<select data-config="output"><option value="insert">Insertar sin enviar</option><option value="copy">Copiar</option></select></label><label>Diccionario: pares JSON<textarea data-config="dictionary" maxlength="25000" aria-label="Diccionario personal"></textarea></label><button type="button" data-save>Guardar ajustes</button><pre data-pending aria-label="Texto pendiente, solo en memoria"></pre><button type="button" data-copy>Copiar pendientes</button><button type="button" data-discard>Descartar pendientes</button><label>Transcribir audio local<input type="file" data-file accept="audio/wav,audio/webm,audio/ogg,audio/mp4"></label><label><input type="checkbox" data-translate>Traducir a inglés explícitamente</label><pre data-file-result></pre>';
        host.append(panel);
        const shortcuts = document.createElement('div');
        shortcuts.innerHTML = '<label>Atajo global<input data-shortcut maxlength="32" value="Ctrl+Alt+Shift+D" aria-label="Atajo de dictado"></label><label>Activación<select data-activation><option value="toggle">Pulsar para activar o terminar</option><option value="hold">Mantener pulsado</option></select></label><button type="button" data-save-shortcut>Guardar atajo</button><button type="button" data-prepare>Preparar modelo</button><button type="button" data-unload>Liberar modelo</button>';
        panel.append(shortcuts);
        const attempt = fn => void Promise.resolve().then(fn).catch(() => { lastError = 'No se pudo completar la operación. Revise el modelo, archivo o ajustes.'; render(); });
        panel.querySelector('[data-mode]').onchange = e => attempt(() => e.target.value === 'off' ? stop() : start(e.target.value));
        for (const [name, fn] of Object.entries({ pause, resume: api.resume, finish: api.finish, copy: api.copyPending, discard: api.discardPending })) panel.querySelector(`[data-${name}]`).onclick = () => attempt(fn);
        for (const input of panel.querySelectorAll('[data-config]')) input.value = input.dataset.config === 'dictionary' ? JSON.stringify(config.dictionary) : config[input.dataset.config];
        panel.querySelector('[data-save]').onclick = () => attempt(() => { const value = {}; for (const input of panel.querySelectorAll('[data-config]')) value[input.dataset.config] = input.dataset.config === 'dictionary' ? JSON.parse(input.value) : input.value; api.configure(value); });
        panel.querySelector('[data-save-shortcut]').onclick = () => attempt(() => api.configureShortcut(shortcutChord(panel.querySelector('[data-shortcut]').value, panel.querySelector('[data-activation]').value)));
        panel.querySelector('[data-prepare]').onclick = () => attempt(() => { if (mode !== 'off' || !config.model) throw Error('Elija un modelo y apague el dictado.'); return Axx.backendRequest('POST', '/axx-api/speech/models/prepare', { model: config.model }); });
        panel.querySelector('[data-unload]').onclick = () => attempt(() => { if (mode !== 'off') throw Error('Apague el dictado.'); return Axx.backendRequest('POST', '/axx-api/speech/models/unload', {}); });
        panel.querySelector('[data-file]').onchange = e => attempt(async () => { const result = await api.transcribeFile(e.target.files[0], { translate: panel.querySelector('[data-translate]').checked }); panel.querySelector('[data-file-result]').textContent = result.text; e.target.value = ''; });
        attempt(async () => {
            const shortcut = await window.__TAURI__.core.invoke('dictation_shortcut', { shortcut: null });
            if (shortcut?.shortcut && shortcut.shortcut.key) {
                const keys = shortcut.shortcut;
                panel.querySelector('[data-shortcut]').value = [[2,'Ctrl'],[1,'Alt'],[4,'Shift']].filter(([bit]) => keys.modifiers & bit).map(([,name]) => name).concat(String.fromCharCode(keys.key)).join('+');
                panel.querySelector('[data-activation]').value = keys.activation;
                panel.querySelector('summary + p').textContent = shortcut.registered ? 'Escucha local, escribe sin enviar. Atajo: ' + panel.querySelector('[data-shortcut]').value + '. Esc cancela. Solo campos editables verificados.' : 'Atajo ocupado o no registrado. Configure otro o active el modo desde aquí. Esc cancela.';
            }
            const report = await Axx.backendRequest('GET', '/axx-api/speech/models');
            for (const model of report.models || []) { const option = new Option(model.id + (model.available ? '' : ' · no disponible'), model.id); option.disabled = !model.available; panel.querySelector('[data-config="model"]').append(option); }
            panel.querySelector('[data-config="model"]').value = config.model;
            for (const device of (await native({ action: 'audio_devices' })).devices || []) panel.querySelector('[data-config="microphone"]').append(new Option(device.label || 'Micrófono', device.id));
            panel.querySelector('[data-config="microphone"]').value = config.microphone;
        }); render();
    }
    void window.__TAURI__.event.listen('axx-dictation-pcm', ({ payload }) => {
        if (!stream || payload?.session !== session || payload.capture !== stream || !Array.isArray(payload.samples) || payload.samples.length > 2048 || typeof payload.target !== 'string') return;
        if (payload.samples.some(v => !Number.isInteger(v) || v < -32768 || v > 32767)) return;
        segmenter?.feed(Float32Array.from(payload.samples, value => value / 32768), payload.target);
    });
    void window.__TAURI__.event.listen('axx-dictation-audio-stopped', ({ payload }) => {
        if (!stream || payload?.capture !== stream || payload.session !== session) return;
        if (payload.error) cancelAudio(); else { segmenter?.flush(); release(); }
        phase = payload.error ? 'ERROR' : 'ARMED';
        if (payload.error) lastError = 'El micrófono nativo se interrumpió. Revise la entrada y reanude.';
        render();
    });
    void window.__TAURI__.event.listen('axx-dictation-cancel', stop);
    void window.__TAURI__.event.listen('axx-dictation-toggle', () => { if (mode === 'manual') api.finish(); else if (mode !== 'off') stop(); else void start('manual').catch(() => { lastError = 'No se pudo iniciar el dictado.'; render(); }); });
    void window.__TAURI__.event.listen('axx-dictation-hold-start', () => { if (mode === 'off') void start('manual', true).catch(() => { stop(); lastError = 'No se pudo iniciar el dictado.'; render(); }); });
    void window.__TAURI__.event.listen('axx-dictation-hold-end', () => { if (!held) return; held = false; holdReleased?.(); holdReleased = null; if (session) api.finish(); else stop(); });
    void (async () => {
        try {
            const report = await window.__TAURI__.core.invoke('dictation_shortcut', { shortcut: null });
            if (report?.shortcut) activeShortcut = { ...report.shortcut, registered: report.registered === true };
            const saved = JSON.parse(localStorage.getItem('axx.dictation.shortcut.v1') || 'null');
            if (commandShortcutMatches(saved || activeShortcut)) {
                await window.__TAURI__.core.invoke('dictation_shortcut', { shortcut: { key: 0, modifiers: 0, activation: 'disabled' } });
                activeShortcut.registered = false; lastError = 'El atajo coincide con comandos de voz; elija otro para dictado.'; render();
            } else await api.configureShortcut(saved || { key: activeShortcut.key, modifiers: activeShortcut.modifiers, activation: activeShortcut.activation });
        } catch { lastError = 'El atajo guardado está ocupado o no es válido.'; render(); }
    })();
    window.addEventListener('pagehide', stop);
    const observer = new MutationObserver(mount); observer.observe(document.body, { childList: true, subtree: true }); mount();
    setInterval(() => { void tick(); }, 200);
})();
