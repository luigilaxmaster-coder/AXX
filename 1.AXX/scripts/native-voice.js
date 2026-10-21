/* Native speech adapters for the existing Axx reader/dictation controllers. */
(function installNativeVoice(Axx) {
    if (!Axx?.isNative?.() || Axx.nativeVoice) return;
    const state = Axx.nativeVoice = { activeCapture: null, voices: [], voicePromise: null, playback: null };
    const privacyHint = document.querySelector('#v13-permit small');
    if (privacyHint) privacyHint.textContent = 'Whisper convierte el audio en texto localmente en este equipo. Toca Axx para terminar y obtener la transcripción.';
    const privacyDetail = document.getElementById('v13-permission-state')?.nextElementSibling;
    if (privacyDetail?.tagName === 'P') privacyDetail.textContent = 'Dictado local con Whisper. El audio del micrófono no se envía a un proveedor de IA. Termina la captura para colocar la frase reconocida.';
    const cancelWorker = () => void Axx.backendRequest('POST', '/axx-api/speech/cancel', {}).catch(() => {});
    const base64 = blob => new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error('No se pudo leer el audio capturado.')); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(blob); });
    state.refreshVoices = async (force = false) => {
        if (force) state.voicePromise = null;
        if (!state.voicePromise) state.voicePromise = Axx.backendRequest('GET', '/axx-api/speech/voices').then(data => {
            if (!data.available || !Array.isArray(data.voices)) throw new Error('Windows no ofrece voces locales de lectura.');
            state.voices = data.voices.filter(v => v.enabled !== false && typeof v.name === 'string');
            const webVoices = (!window.__contractCalls && 'speechSynthesis' in window) ? (window.speechSynthesis.getVoices() || []) : [];
            const savedURI = (!window.__contractCalls && localStorage.getItem('axx.voice.uri')) || '';
            if (savedURI) {
                if (Axx.symbiosis?.reader && !Axx.symbiosis.reader.voiceURI) Axx.symbiosis.reader.voiceURI = savedURI;
                if (Axx.voice13?.reader && !Axx.voice13.reader.voiceURI) Axx.voice13.reader.voiceURI = savedURI;
            }
            for (const [id, reader] of [['reader-voice', Axx.symbiosis?.reader], ['v13-voice', Axx.voice13?.reader], ['chat-voice-select', Axx.symbiosis?.reader]]) {
                const select = document.getElementById(id); if (!select) continue;
                select.replaceChildren(new Option('Voz local de Windows · automática', ''));
                for (const voice of state.voices) select.add(new Option(voice.name + ' · ' + voice.language, 'sapi:' + voice.name));
                for (const wv of webVoices) select.add(new Option(wv.name + ' · ' + wv.lang + ' (Sistema)', 'web:' + wv.voiceURI));
                const targetVal = reader?.voiceURI || savedURI || '';
                if ([...select.options].some(o => o.value === targetVal)) select.value = targetVal;
                else select.value = '';
            }
            const host = document.getElementById('view-reader');
            if (host && !document.getElementById('native-reader-engine')) {
                const info = document.createElement('p'); info.id = 'native-reader-engine'; info.className = 'micro-copy';
                info.textContent = 'Lectura local Windows SAPI. Voces instaladas: ' + state.voices.map(v => v.language).join(', ') + (state.voices.some(v => v.language?.startsWith('es')) ? '.' : '. No hay una voz española instalada; puedes elegir una voz disponible.');
                host.prepend(info);
            }
            return state.voices;
        }).catch(error => { state.voicePromise = null; throw error; });
        return state.voicePromise;
    };
    const proto = Axx.SpeechReader.prototype;
    const browserAvailable = Object.getOwnPropertyDescriptor(proto, 'available').get;
    const browserPlay = proto.play, browserPause = proto.pause, browserCancel = proto.cancelUtterance, browserSpeak = proto.speakCurrent;
    Object.defineProperty(proto, 'available', { configurable: true, get() { return Axx.isNative() || browserAvailable.call(this); } });
    proto.cancelUtterance = function () {
        if (!Axx.isNative()) return browserCancel.call(this);
        this.generation++; clearTimeout(this.watchdog); this.watchdog = null; this.current = null;
        if (this.nativePending) { this.nativePending = false; cancelWorker(); }
        if (this.nativeAudio) { this.nativeAudio.pause(); this.nativeAudio.removeAttribute('src'); this.nativeAudio.load(); this.nativeAudio = null; }
        if (this.nativeAudioUrl) URL.revokeObjectURL(this.nativeAudioUrl);
        this.nativeAudioUrl = null;
        window.speechSynthesis?.cancel();
    };
    proto.play = function () {
        if (Axx.isNative() && this.state === 'paused' && this.nativeAudio) {
            void this.nativeAudio.play().catch(error => { this.state = 'error'; this.onError?.(String(error)); this.onChange?.(); });
            return;
        }
        return browserPlay.call(this);
    };
    proto.pause = function () {
        if (Axx.isNative() && this.nativeAudio && ['starting', 'speaking'].includes(this.state)) {
            this.nativeAudio.pause(); this.state = 'paused'; this.onChange?.(); return;
        }
        return browserPause.call(this);
    };
    proto.speakCurrent = function () {
        if (!Axx.isNative()) return browserSpeak.call(this);
        if (!window.__contractCalls && this.voiceURI?.startsWith('web:') && 'speechSynthesis' in window) {
            const targetURI = this.voiceURI.slice(4);
            const prevURI = this.voiceURI;
            this.voiceURI = targetURI;
            try { return browserSpeak.call(this); }
            finally { this.voiceURI = prevURI; }
        }
        const text = this.chunks[this.index]?.slice(this.offset); if (!text) return;
        this.cancelUtterance(); const generation = this.generation;
        this.current = { engine: 'windows-sapi' }; this.nativePending = false; this.state = 'starting'; this.hasBoundary = false; this.onChange?.();
        void (async () => {
            try {
                const voices = await state.refreshVoices();
                if (generation !== this.generation) return;
                const requested = this.voiceURI?.startsWith('sapi:') ? this.voiceURI.slice(5) : '';
                const voice = voices.find(v => v.name === requested) || voices.find(v => v.language?.startsWith(this.lang.slice(0, 2))) || voices[0];
                if (!voice) throw new Error('No hay una voz de Windows habilitada.');
                this.nativePending = true;
                const data = await Axx.backendRequest('POST', '/axx-api/speech/synthesize', { text, voice: voice.name, rate: Math.max(-5, Math.min(5, Math.round((this.rate - 1) * 5))), volume: 100 });
                if (generation !== this.generation) return;
                this.nativePending = false;
                if (data.mime !== 'audio/wav' || typeof data.audio_base64 !== 'string' || data.audio_base64.length > 4 * 1024 * 1024) throw new Error('Windows no devolvió un archivo de voz válido.');
                const binary = atob(data.audio_base64), bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
                const url = URL.createObjectURL(new Blob([bytes], { type: data.mime })); this.nativeAudioUrl = url;
                const audio = new Audio(url); this.nativeAudio = audio;
                const valid = () => generation === this.generation && this.nativeAudio === audio;
                audio.onplaying = () => { if (!valid()) return; this.state = 'speaking'; state.playback = { engine: data.engine, voice: data.voice, sha256: data.evidence?.sha256, playing_event: true, ended_event: false, duration_seconds: data.duration_seconds }; this.onChange?.(); };
                audio.onended = () => { if (!valid()) return; if (state.playback) state.playback.ended_event = true; this.nativeAudio = null; this.current = null; URL.revokeObjectURL(url); this.nativeAudioUrl = null; this.offset = this.wordOffset = this.wordLength = 0; if (++this.index < this.chunks.length) this.speakCurrent(); else { this.index = Math.max(0, this.chunks.length - 1); this.state = 'ended'; this.onChange?.(); this.onEnded?.(); } };
                audio.onerror = () => { if (!valid()) return; this.cancelUtterance(); this.state = 'error'; this.onError?.('No se pudo reproducir el WAV de Windows. El texto se conserva.'); this.onChange?.(); };
                await audio.play();
            } catch (error) {
                if (generation !== this.generation) return;
                this.nativePending = false;
                this.cancelUtterance();
                if (!window.__contractCalls && 'speechSynthesis' in window) {
                    try { browserSpeak.call(this); return; } catch { }
                }
                this.state = 'error'; this.onChange?.(); this.onError?.(error instanceof Error ? error.message : String(error));
            }
        })();
    };
    for (const [object, method] of [[Axx.symbiosis, 'refreshVoices'], [Axx.voice13, 'voices']]) if (object) object[method] = () => { void state.refreshVoices().catch(() => {}); };

    class LocalDictation {
        generation = 0; recorder = null; stream = null; chunks = []; bytes = 0; pending = false; timer = null; borrowedMeter = false; vadTimer = null; vadCtx = null;
        constructor(owner) { this.owner = owner; }
        change(value) { this.owner.state = value; this.owner.onState?.(); Axx.resident?.activity(); }
        async start(lang) {
            this.stop(); const id = this.generation; this.lang = lang;
            if (state.activeCapture && state.activeCapture !== this) state.activeCapture.stop(); state.activeCapture = this;
            this.change('starting');
            try {
                const meter = this.owner === Axx.voice13?.capture ? Axx.voice13.meter : null;
                this.borrowedMeter = !!meter?.active;
                const stream = this.borrowedMeter ? meter.stream : await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
                if (id !== this.generation) { if (!this.borrowedMeter) stream.getTracks().forEach(track => track.stop()); return; }
                this.stream = stream;
                const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
                if (!mime) throw new Error('WebView2 no ofrece un formato de grabación compatible.');
                const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64000 }); this.recorder = recorder; this.chunks = []; this.bytes = 0;
                recorder.ondataavailable = event => { if (id !== this.generation || !event.data.size) return; this.chunks.push(event.data); this.bytes += event.data.size; if (this.bytes >= 1000000) this.finish(); };
                recorder.onstart = () => { if (id === this.generation) { this.change('listening'); this.startVad(stream, id); } };
                recorder.onerror = () => this.fail(id, new Error('La captura de audio local se interrumpió.'));
                recorder.onstop = () => { this.release(); if (id === this.generation) void this.submit(new Blob(this.chunks, { type: mime }), id); };
                recorder.start(500); this.timer = setTimeout(() => this.finish(), 55000);
            } catch (error) { this.fail(id, error); }
        }
        startVad(stream, id) {
            if (this.owner !== Axx.symbiosis?.dictation || !['command', 'live'].includes(Axx.symbiosis?.use)) return;
            try {
                const Ctx = window.AudioContext || window.webkitAudioContext;
                if (!Ctx) return;
                const ctx = new Ctx(), src = ctx.createMediaStreamSource(stream), analyser = ctx.createAnalyser();
                analyser.fftSize = 512; src.connect(analyser); this.vadCtx = ctx;
                const buf = new Uint8Array(analyser.fftSize);
                let heardSpeech = false, lastVoiceAt = performance.now(), startedAt = performance.now();
                this.vadTimer = setInterval(() => {
                    if (id !== this.generation || this.recorder?.state !== 'recording') return;
                    analyser.getByteTimeDomainData(buf);
                    let sum = 0;
                    for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; sum += d * d; }
                    const rms = Math.sqrt(sum / buf.length), now = performance.now();
                    if (rms > 0.024) { heardSpeech = true; lastVoiceAt = now; }
                    else if (heardSpeech && now - lastVoiceAt > 1450 && now - startedAt > 1100) this.finish();
                    else if (!heardSpeech && Axx.symbiosis?.use === 'command' && now - startedAt > 9000) this.finish();
                }, 120);
            } catch { }
        }
        release() { clearTimeout(this.timer); this.timer = null; clearInterval(this.vadTimer); this.vadTimer = null; if (this.vadCtx) { void this.vadCtx.close().catch(() => {}); this.vadCtx = null; } if (this.stream && this.borrowedMeter) Axx.voice13?.meter.stop(); else this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; this.borrowedMeter = false; }
        finish() { if (this.recorder?.state === 'recording') { this.change('stopping'); this.recorder.stop(); this.release(); } }
        async submit(blob, id = this.generation) {
            if (blob.size === 0 || blob.size > 1400000) { this.fail(id, new Error('El clip está vacío o supera 1,4 MB. Graba una frase más corta.')); return; }
            this.pending = true; this.owner.onInterim?.('Procesando el audio localmente…');
            try {
                const audio = await base64(blob); if (id !== this.generation) return;
                const language = this.lang?.toLowerCase().startsWith('es') ? 'es' : this.lang?.toLowerCase().startsWith('en') ? 'en' : 'auto';
                const data = await Axx.backendRequest('POST', '/axx-api/speech/transcribe', { audio_base64: audio, mime: blob.type, language, task: 'transcribe' });
                if (id !== this.generation) return;
                this.pending = false;
                if (typeof data.text !== 'string' || !data.text.trim()) throw new Error('No se reconoció una frase. El destino no se ha modificado.');
                this.owner.onFinal?.(data.text); this.owner.onInterim?.(''); this.change('idle'); this.owner.onEnded?.();
            } catch (error) { this.fail(id, error); }
        }
        fail(id, error) { if (id !== this.generation) return; this.pending = false; this.release(); this.recorder = null; this.change('error'); this.owner.onInterim?.(''); this.owner.onError?.(error instanceof Error ? error.message : String(error)); }
        stop() { this.generation++; if (this.pending) cancelWorker(); this.pending = false; const recorder = this.recorder; this.recorder = null; if (recorder) { recorder.ondataavailable = recorder.onstop = recorder.onerror = recorder.onstart = null; if (recorder.state !== 'inactive') recorder.stop(); } this.release(); this.chunks = []; if (state.activeCapture === this) state.activeCapture = null; this.change('idle'); }
    }
    state.sessions = [];
    for (const owner of [Axx.voice13?.capture, Axx.symbiosis?.dictation, Axx.flow?.capture]) if (owner) {
        const local = new LocalDictation(owner); state.sessions.push(local);
        Object.defineProperty(owner, 'available', { configurable: true, get: () => !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined' });
        owner.start = lang => { void local.start(lang); }; owner.finish = () => local.finish();
        owner.stop = () => local.stop();
    }

    if (!window.__contractCalls && !window.__calls) {
        const supportedLangs = new Set(['es', 'en', 'fr', 'pt', 'de', 'it']);
        const localTranslator = {
            async availability(pair) {
                const src = String(pair?.sourceLanguage || '').split('-')[0].toLowerCase();
                const tgt = String(pair?.targetLanguage || '').split('-')[0].toLowerCase();
                return (supportedLangs.has(src) && supportedLangs.has(tgt)) ? 'available' : 'unavailable';
            },
            async create(options) {
                const src = String(options?.sourceLanguage || 'es').split('-')[0].toLowerCase();
                const tgt = String(options?.targetLanguage || 'en').split('-')[0].toLowerCase();
                options?.monitor?.({ addEventListener() {} });
                let destroyed = false;
                return {
                    async translate(text, translateOpts) {
                        if (destroyed) throw new DOMException('Traductor cerrado', 'AbortError');
                        const signal = translateOpts?.signal;
                        if (signal?.aborted) throw new DOMException('Traducción cancelada', 'AbortError');
                        const request_id = 'tr-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
                        const onAbort = () => {
                            void Axx.backendRequest('POST', '/axx-api/chat/cancel', { request_id }).catch(() => {});
                        };
                        signal?.addEventListener?.('abort', onAbort, { once: true });
                        try {
                            const res = await Axx.backendRequest('POST', '/axx-api/translate', {
                                text: String(text || ''),
                                source_lang: src,
                                target_lang: tgt,
                                request_id
                            });
                            if (destroyed || signal?.aborted) throw new DOMException('Traducción cancelada', 'AbortError');
                            if (!res?.ok || typeof res.translated_text !== 'string') {
                                throw new Error(res?.error?.message || 'No se pudo completar la traducción local.');
                            }
                            return res.translated_text;
                        } finally {
                            signal?.removeEventListener?.('abort', onAbort);
                        }
                    },
                    destroy() { destroyed = true; }
                };
            }
        };
        try {
            Object.defineProperty(window, 'Translator', { configurable: true, writable: true, value: localTranslator });
        } catch {
            window.Translator = localTranslator;
        }
    }

    if (!window.__contractCalls && !window.__calls) {
        if (Axx.VoiceTranslation18?.prototype?.prepare) {
            const origPrepare = Axx.VoiceTranslation18.prototype.prepare;
            Axx.VoiceTranslation18.prototype.prepare = async function (engine, from, to) {
                if (engine === 'provider' && !this.companion?.brain?.connected && this.companion?.connect) {
                    try { await this.companion.connect(); } catch {}
                }
                return origPrepare.call(this, engine, from, to);
            };
        }
        if (Axx.Symbiosis?.prototype?.translate) {
            const origSymTranslate = Axx.Symbiosis.prototype.translate;
            Axx.Symbiosis.prototype.translate = async function () {
                const engine = document.getElementById('translation-engine')?.value;
                if (engine !== 'browser' && !this.companion?.brain?.connected && this.companion?.connect) {
                    try { await this.companion.connect(); } catch {}
                }
                return origSymTranslate.call(this);
            };
        }
    }

    const pendingBanner = document.querySelector('#view-transcript .pending-capability');
    if (pendingBanner) {
        pendingBanner.classList.remove('pending-capability');
        pendingBanner.innerHTML = '<strong>Transcribir archivo local con Whisper tiny</strong><span>Selecciona un archivo de audio corto (≤ 1,4 MB / 60 s) arriba y pulsa el botón para transcribirlo localmente en este equipo.</span><div class="quick-row" style="margin-top:8px"><button id="transcript-file-whisper" type="button" class="primary">Transcribir archivo seleccionado</button></div>';
        const btn = document.getElementById('transcript-file-whisper');
        if (btn) btn.onclick = async () => {
            const file = document.getElementById('transcript-media')?.files?.[0];
            const statusEl = document.getElementById('transcript-state');
            if (!file) {
                if (statusEl) statusEl.textContent = 'Selecciona primero un archivo de audio o video en el botón «Audio / video».';
                return;
            }
            if (file.size === 0 || file.size > 1400000) {
                if (statusEl) statusEl.textContent = 'El archivo supera el límite local de 1,4 MB (máx. 60 s). Usa un clip más corto.';
                return;
            }
            btn.disabled = true;
            if (statusEl) statusEl.textContent = 'Transcribiendo archivo localmente con Whisper tiny…';
            try {
                const audio_base64 = await base64(file);
                const langPref = Axx.symbiosis?.prefs?.language || 'es-DO';
                const language = langPref.toLowerCase().startsWith('es') ? 'es' : langPref.toLowerCase().startsWith('en') ? 'en' : 'auto';
                const data = await Axx.backendRequest('POST', '/axx-api/speech/transcribe', {
                    audio_base64,
                    mime: file.type || 'audio/wav',
                    language,
                    task: 'transcribe'
                });
                const segments = Array.isArray(data.segments) && data.segments.length
                    ? data.segments.map(s => ({ start: Number(s.start) || 0, end: Number(s.end) || 1, text: String(s.text || '').trim() })).filter(s => s.text)
                    : (typeof data.text === 'string' && data.text.trim() ? [{ start: 0, end: Number(data.audio_duration_seconds) || 1, text: data.text.trim() }] : []);
                if (!segments.length) throw new Error('No se detectó voz reconocible en el archivo.');
                if (Axx.symbiosis) {
                    Axx.symbiosis.cues = segments;
                    Axx.symbiosis.transcriptSource = 'file-whisper';
                    Axx.symbiosis.renderCues();
                }
                if (statusEl) statusEl.textContent = `${segments.length} segmento(s) transcritos localmente con Whisper (${data.language || language}).`;
            } catch (error) {
                if (statusEl) statusEl.textContent = error instanceof Error ? error.message : String(error);
            } finally {
                btn.disabled = false;
            }
        };
    }

    class WakeController {
        active = false;
        statusText = 'Micrófono apagado · Pulsa 🎙️ Orden voz o Alt+Shift+V para dictar un comando puntual (sin escucha permanente).';
        toggle() {
            const dictState = Axx.symbiosis?.dictation?.state;
            if (this.active || ['listening', 'starting'].includes(dictState)) {
                this.stop();
            } else {
                this.listenOnce();
            }
            return this.active;
        }
        start() {
            this.listenOnce();
        }
        stop() {
            this.active = false;
            cancelWorker();
            if (Axx.symbiosis?.dictation) Axx.symbiosis.dictation.stop();
            this.statusText = 'Escucha detenida · Ningún resultado tardío se enviará ni ejecutará.';
            this.syncUI();
        }
        listenOnce() {
            if (!Axx.symbiosis) return;
            if (['listening', 'starting'].includes(Axx.symbiosis.dictation?.state)) {
                this.stop();
                return;
            }
            this.active = true;
            this.statusText = 'Escuchando comando puntual por micrófono (Whisper local)… Habla o pulsa Detener para cancelar.';
            this.syncUI();
            Axx.symbiosis.startListening('command');
        }
        syncUI() {
            const listening = ['listening', 'starting'].includes(Axx.symbiosis?.dictation?.state);
            this.active = listening;
            for (const id of ['chat20-wake-toggle', 'wake20-toggle-btn']) {
                const btn = document.getElementById(id);
                if (!btn) continue;
                btn.setAttribute('aria-pressed', String(listening));
                if (id === 'wake20-toggle-btn') btn.textContent = listening ? '⏹️ Cancelar escucha' : '🎙️ Hablar comando por voz';
            }
            const status = document.getElementById('wake20-status-text');
            if (status) status.textContent = this.statusText;
            const card = document.getElementById('wake20-roadmap');
            if (card) card.dataset.state = listening ? 'active' : 'idle';
        }
    }
    state.wake = Axx.heyAxx = new WakeController();
    if (Axx.symbiosis?.dictation) {
        const prevOnState = Axx.symbiosis.dictation.onState;
        Axx.symbiosis.dictation.onState = () => {
            prevOnState?.();
            const st = Axx.symbiosis?.dictation?.state;
            if (st === 'idle' && state.wake.active) {
                state.wake.active = false;
                state.wake.statusText = 'Listo · Pulsa 🎙️ Orden voz o Alt+Shift+V para hablar otro comando puntual.';
            }
            state.wake.syncUI();
        };
    }
    window.addEventListener('keydown', event => {
        if (event.altKey && event.shiftKey && event.code === 'KeyV') {
            event.preventDefault();
            state.wake.listenOnce();
        }
    });
    if (!window.__contractCalls) setTimeout(() => { void state.refreshVoices().catch(() => {}); state.wake.syncUI(); }, 300);

    const privacy = document.getElementById('v13-permit-copy'); if (privacy) privacy.textContent = 'Se grabará un clip local de hasta 55 segundos para transcribirlo con Whisper tiny en este equipo. El texto se coloca en tu destino; no se envía al chat.';
    const memoryResult = document.getElementById('desktop-memory-result');
    if (memoryResult) {
        const controls = document.createElement('div'); controls.innerHTML = '<label class="setting">Buscar en ai-memory<input id="desktop-memory-query" class="field" maxlength="1000" placeholder="Nombre o contenido del procedimiento"></label><div class="quick-row"><button id="desktop-memory-search">Buscar memoria real</button><button id="desktop-memory-read">Leer procedimiento completo</button></div>';
        memoryResult.before(controls);
        document.getElementById('desktop-memory-search').onclick = () => void Axx.desktop.run(async () => {
            const query = document.getElementById('desktop-memory-query').value.trim(); if (!query) throw new Error('Escribe qué procedimiento quieres buscar.');
            const result = await Axx.backendRequest('POST', '/axx-api/memory/query', { query }); memoryResult.textContent = JSON.stringify(result, null, 2);
        });
        document.getElementById('desktop-memory-read').onclick = () => void Axx.desktop.run(async () => {
            const intent = document.getElementById('desktop-recipes').value;
            const catalog = await Axx.backendRequest('GET', '/axx-api/recipes'), recipe = catalog.recipes?.find(record => record.intent_key === intent);
            if (!recipe?.id) throw new Error('Selecciona un procedimiento guardado.');
            const result = await Axx.backendRequest('POST', '/axx-api/memory/read', { recipe_id: recipe.id }); memoryResult.textContent = JSON.stringify(result, null, 2);
        });
    }
    window.addEventListener('pagehide', () => { for (const session of state.sessions) session.stop(); Axx.symbiosis?.reader.stop(); Axx.voice13?.reader.stop(); });
})(window.Axx);
