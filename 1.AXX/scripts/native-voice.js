/* Native speech adapters for the existing Axx reader/dictation controllers. */
(function installNativeVoice(Axx) {
    if (!Axx?.isNative?.() || Axx.nativeVoice) return;
    const state = Axx.nativeVoice = { activeCapture: null, voices: [], voicePromise: null, playback: null };
    try { state.liveDeviceId = localStorage.getItem('axx.live.microphone') || ''; } catch { state.liveDeviceId = ''; }
    // RMS envelope only: this state contains no audio or recognized text.
    state.inputLevel = null;
    const privacyHint = document.querySelector('#v13-permit small');
    if (privacyHint) privacyHint.textContent = 'Whisper convierte el audio en texto localmente en este equipo. Toca Axx para terminar y obtener la transcripción.';
    const privacyDetail = document.getElementById('v13-permission-state')?.nextElementSibling;
    if (privacyDetail?.tagName === 'P') privacyDetail.textContent = 'Dictado local con Whisper. El audio del micrófono no se envía a un proveedor de IA. Termina la captura para colocar la frase reconocida.';
    const cancelWorker = () => state.cancelPromise = Axx.backendRequest('POST', '/axx-api/speech/cancel', {}).catch(() => {});
    const showVoiceStatus = (message, phase = 'idle') => {
        for (const id of ['native-reader-engine', 'chat-voice-status', 'chat-live-voice-status', 'voice-panel-status']) {
            const info = document.getElementById(id);
            if (info) { info.setAttribute('role', 'status'); info.dataset.phase = phase; info.textContent = message; }
        }
    };
    const defaultVoice = document.getElementById('chat-voice-default');
    if (defaultVoice) {
        defaultVoice.hidden = false;
        defaultVoice.onclick = () => {
            const select = document.getElementById('chat-voice-select');
            if (!state.voices.some(voice => voice.name === 'moss:axx-sam') || !select) return;
            select.value = 'moss:axx-sam';
            select.dispatchEvent(new Event('change', { bubbles: true }));
        };
    }
    state.prepareVoice = voice => {
        const ticket = state.prepareTicket = (state.prepareTicket || 0) + 1;
        if (!voice?.startsWith('moss:') && !voice?.startsWith('piper:')) { showVoiceStatus('Voz del sistema seleccionada. Pulsa Probar voz para escucharla.'); return; }
        const selected = state.voices.find(item => item.name === voice);
        if (!selected) { showVoiceStatus('La voz seleccionada no está disponible. Revisa su instalación en Voces de Axx y pulsa Actualizar voces.', 'error'); return; }
        const label = selected.engine === 'piper-onnx' ? (selected.label || selected.name).split(' · ').slice(0, 3).join(' · ') : (selected.label || selected.name).split(' · ')[0];
        showVoiceStatus(label + ' · Preparando el modelo local… La primera carga puede tardar varios segundos.', 'loading');
        void Axx.prepareSpeechAudio?.();
        void (async () => {
            let status = await Axx.backendRequest('POST', '/axx-api/speech/prepare', { voice });
            for (let attempt = 0; attempt < 180 && ticket === state.prepareTicket; attempt++) {
                const ready = status.prepared_voices?.includes(voice);
                if (ready) { showVoiceStatus(label + ' · Lista para hablar. Pulsa Probar voz para escucharla.', 'ready'); return; }
                await new Promise(resolve => setTimeout(resolve, 500));
                if (ticket !== state.prepareTicket) return;
                const report = await Axx.backendRequest('GET', '/axx-api/speech/status');
                status = voice.startsWith('piper:') ? report.piper : report.custom;
                if (status?.error) throw new Error(status.error);
                if (!status?.preparing_voice && !status?.prepared_voices?.includes(voice))
                    status = await Axx.backendRequest('POST', '/axx-api/speech/prepare', { voice });
            }
            if (ticket === state.prepareTicket) throw new Error('Voice preparation timed out');
        })().catch(() => {
            if (ticket === state.prepareTicket) showVoiceStatus('No se pudo preparar ' + label + '. Pulsa Actualizar voces para reintentar.', 'error'); });
    };
    const base64 = clip => new Promise((resolve, reject) => {
        const reader = clip.reader = new FileReader();
        const clear = () => { if (clip.reader === reader) clip.reader = null; reader.onload = reader.onerror = reader.onabort = null; };
        reader.onerror = reader.onabort = () => { clear(); reject(new Error('No se pudo leer el audio capturado.')); };
        reader.onload = () => { const value = String(reader.result).split(',')[1]; clear(); resolve(value); };
        reader.readAsDataURL(clip.blob);
    });
    state.refreshVoices = async (force = false) => {
        if (force) state.voicePromise = null;
        if (!state.voicePromise) showVoiceStatus('Buscando las voces instaladas…', 'loading');
        if (!state.voicePromise) state.voicePromise = Axx.backendRequest('GET', '/axx-api/speech/voices').then(data => {
            if (!data.available || !Array.isArray(data.voices)) throw new Error('Windows no ofrece voces locales de lectura.');
            state.voices = data.voices.filter(v => v.enabled !== false && typeof v.name === 'string');
            const hasDefault = state.voices.some(voice => voice.name === 'moss:axx-sam');
            if (defaultVoice) {
                defaultVoice.disabled = !hasDefault;
                defaultVoice.textContent = hasDefault ? 'Usar Xxx default' : 'Xxx default no disponible';
            }
            const savedRate = Number(localStorage.getItem('axx.voice.rate') || 1);
            if (Number.isFinite(savedRate) && savedRate >= .75 && savedRate <= 1.3)
                for (const reader of [Axx.symbiosis?.reader, Axx.voice13?.reader]) if (reader) reader.rate=savedRate;
            const webVoices = (!window.__contractCalls && 'speechSynthesis' in window) ? (window.speechSynthesis.getVoices() || []) : [];
            const savedURI = window.__contractCalls ? null : localStorage.getItem('axx.voice.uri');
            const defaultURI = (!window.__contractCalls &&
                (state.voices.find(v => v.name === 'moss:axx-morcito') || state.voices.find(v => v.name === 'moss:axx-sam') || state.voices.find(v => v.name === 'moss:axx-valeria'))?.name) || '';
            const effectiveURI = savedURI ?? defaultURI;
            for (const reader of [Axx.symbiosis?.reader, Axx.voice13?.reader])
                if (reader) reader.voiceURI = effectiveURI;
            for (const [id, reader] of [['reader-voice', Axx.symbiosis?.reader], ['v13-voice', Axx.voice13?.reader], ['chat-voice-select', Axx.symbiosis?.reader], ['voice-panel-select', Axx.symbiosis?.reader], ['chat-live-voice', Axx.symbiosis?.reader]]) {
                const select = document.getElementById(id); if (!select) continue;
                select.replaceChildren(new Option('Voz rápida de Windows · automática', ''));
                for (const voice of state.voices) select.add(new Option(voice.engine === 'moss-onnx' || voice.engine === 'piper-onnx' ? (voice.label || voice.name) : (voice.label || voice.name) + ' · ' + voice.language, voice.engine === 'moss-onnx' || voice.engine === 'piper-onnx' ? voice.name : 'sapi:' + voice.name));
                if (!state.voices.some(v => v.name === 'moss:axx-morcito')) { const missing = new Option('Axxmorcito · no disponible', 'moss:axx-morcito'); missing.disabled = true; select.add(missing); }
                if (!hasDefault) { const missing = new Option('Xxx default · no disponible', 'moss:axx-sam'); missing.disabled = true; select.add(missing); }
                for (const [uri, label] of [['piper:es_ES-carlfm-x_low', 'Piper · España · CarlFM · no instalada'], ['piper:es_MX-ald-medium', 'Piper · México · Ald · no instalada']]) {
                    if (!state.voices.some(v => v.name === uri)) { const missing = new Option(label, uri); missing.disabled = true; select.add(missing); }
                }
                for (const wv of webVoices) select.add(new Option(wv.name + ' · ' + wv.lang + ' (Sistema)', 'web:' + wv.voiceURI));
                const targetVal = reader?.voiceURI || effectiveURI || '';
                if ([...select.options].some(o => o.value === targetVal)) select.value = targetVal;
                else select.value = '';
                if (!select.dataset.customVoicePrepare) {
                    select.dataset.customVoicePrepare = 'true';
                    select.addEventListener('change', () => {
                        Axx.stability20?.syncVoiceURI?.(select.value);
                        state.prepareVoice(select.value);
                    });
                }
            }
            const host = document.getElementById('view-reader');
            if (host && !document.getElementById('native-reader-engine')) {
                const info = document.createElement('p'); info.id = 'native-reader-engine'; info.className = 'micro-copy';
                info.textContent = 'Elige una voz local en Voces de Axx. MOSS y Piper pueden tardar en preparar el modelo la primera vez.';
                host.prepend(info);
            }
            Axx.stability20?.updateVoiceCards?.();
            Axx.voiceAudio?.refreshPanel?.();
            state.prepareVoice(effectiveURI);
            return state.voices;
        }).catch(error => {
            state.voicePromise = null;
            showVoiceStatus('No se pudo consultar las voces locales. Pulsa Actualizar voces para reintentar.', 'error');
            throw error;
        });
        return state.voicePromise;
    };
    const proto = Axx.SpeechReader.prototype;
    const browserAvailable = Object.getOwnPropertyDescriptor(proto, 'available').get;
    const browserPlay = proto.play, browserPause = proto.pause, browserCancel = proto.cancelUtterance, browserSpeak = proto.speakCurrent;
    Object.defineProperty(proto, 'available', { configurable: true, get() { return Axx.isNative() || browserAvailable.call(this); } });
    proto.cancelUtterance = function () {
        if (!Axx.isNative()) return browserCancel.call(this);
        this.awaitingText = false; this.generation++; clearTimeout(this.watchdog); this.watchdog = null; this.current = null;
        if (this.nativePending) { this.nativePending = false; cancelWorker(); }
        if (this.nativeStream) { void this.nativeStream.stop(); this.nativeStream = null; }
        this.nativePrefetch = null;
        this.nativeVoiceName = null;
        if (this.nativeAudio) { this.nativeAudio.pause(); this.nativeAudio.removeAttribute('src'); this.nativeAudio.load(); this.nativeAudio = null; }
        this.nativeAudioChain?.dispose(); this.nativeAudioChain = null;
        if (this.nativeAudioUrl) URL.revokeObjectURL(this.nativeAudioUrl);
        this.nativeAudioUrl = null;
        window.speechSynthesis?.cancel();
    };
    proto.prefetchNativeNext = function () {
        if (this.nativeStream) return;
        if (!Axx.isNative() || !this.nativeAudio || this.nativePrefetch || !this.nativeVoiceName) return;
        const index = this.index + 1, text = this.chunks[index];
        if (!text) return;
        const generation = this.generation;
        const request = { text, voice: this.nativeVoiceName,
            rate: this.nativeVoiceName.startsWith('piper:') ? 0 : Math.max(-5, Math.min(5, Math.round((this.rate - 1) * 5))), volume: 100 };
        const prefetch = { index, generation, promise: Axx.backendRequest('POST', '/axx-api/speech/synthesize', request) };
        this.nativePrefetch = prefetch;
        this.nativePending = true;
        void prefetch.promise.then(() => { if (this.nativePrefetch === prefetch) this.nativePending = false; },
            () => { if (this.nativePrefetch === prefetch) this.nativePending = false; });
    };
    proto.play = function () {
        if (this.state === 'paused' && this.nativeStream) {
            const stream = this.nativeStream;
            void stream.resume().then(() => { if (this.nativeStream === stream) { this.state = stream.played ? 'speaking' : 'starting'; this.onChange?.(); } }); return;
        }
        if (Axx.isNative() && this.state === 'paused' && this.nativeAudio) {
            void this.nativeAudio.play().catch(error => { this.state = 'error'; this.onError?.(String(error)); this.onChange?.(); });
            return;
        }
        return browserPlay.call(this);
    };
    proto.pause = function () {
        if (this.nativeStream && ['starting', 'speaking'].includes(this.state)) {
            void this.nativeStream.pause(); this.state = 'paused'; this.onChange?.(); return;
        }
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
        const carried = this.nativePrefetch?.index === this.index && this.nativePrefetch.generation === this.generation
            ? this.nativePrefetch : null;
        if (!carried) { const awaiting = this.awaitingText; this.cancelUtterance(); this.awaitingText = awaiting; }
        const generation = this.generation;
        this.current = { engine: 'windows-sapi' }; this.nativePending = false; this.state = 'starting'; this.hasBoundary = false; this.onChange?.();
        void (async () => {
            try {
                const voices = await state.refreshVoices();
                if (generation !== this.generation) return;
                const requested = this.voiceURI?.startsWith('sapi:') ? this.voiceURI.slice(5) : /^(moss|piper):/.test(this.voiceURI || '') ? this.voiceURI : '';
                if (/^(moss|piper):/.test(requested) && !voices.some(v => v.name === requested))
                    throw new Error('La voz seleccionada no está disponible. Revisa su instalación en Voces de Axx.');
                const voice = voices.find(v => v.name === requested)
                    || voices.find(v => v.engine !== 'moss-onnx' && v.engine !== 'piper-onnx' && v.language?.startsWith(this.lang.slice(0, 2)))
                    || voices.find(v => v.engine !== 'moss-onnx' && v.engine !== 'piper-onnx') || voices[0];
                if (!voice) throw new Error('No hay una voz de Windows habilitada.');
                if (voice.engine === 'moss-onnx' && Axx.CustomSpeechStream) {
                    await state.cancelPromise;
                    if (generation !== this.generation) return;
                    const stream = this.nativeStream = new Axx.CustomSpeechStream(this, voice, generation);
                    this.current = { engine: 'moss-onnx', streaming: true };
                    this.nativeVoiceName = voice.name;
                    await stream.play(); return;
                }
                this.nativePending = true;
                const data = carried ? await carried.promise : await Axx.backendRequest('POST', '/axx-api/speech/synthesize', { text, voice: voice.name, rate: voice.engine === 'piper-onnx' ? 0 : Math.max(-5, Math.min(5, Math.round((this.rate - 1) * 5))), volume: 100 });
                if (generation !== this.generation) return;
                this.nativePending = false;
                if (carried && this.nativePrefetch === carried) this.nativePrefetch = null;
                if (data.mime !== 'audio/wav' || typeof data.audio_base64 !== 'string' || data.audio_base64.length > 17 * 1024 * 1024) throw new Error('El motor de voz no devolvió un WAV válido.');
                const binary = atob(data.audio_base64), bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
                const url = URL.createObjectURL(new Blob([bytes], { type: data.mime })); this.nativeAudioUrl = url;
                const audio = new Audio(url); this.nativeAudio = audio;
                if (data.engine === 'moss-onnx' || data.engine === 'piper-onnx') {
                    audio.preservesPitch = false;
                    audio.playbackRate = Axx.voiceAudio?.speed(voice.name, this.rate) || Math.max(.75,Math.min(1.3,Number(this.rate)||1));
                    if (Axx.voiceAudio) this.nativeAudioChain = Axx.voiceAudio.attach(audio, voice.name);
                }
                const valid = () => generation === this.generation && this.nativeAudio === audio;
                audio.onplaying = () => { if (!valid()) return; this.state = 'speaking'; this.nativeVoiceName = voice.name; state.playback = { engine: data.engine, voice: data.voice, sha256: data.evidence?.sha256, playing_event: true, ended_event: false, duration_seconds: data.duration_seconds }; this.prefetchNativeNext(); this.onChange?.(); };
                audio.onended = () => { if (!valid()) return; if (state.playback) state.playback.ended_event = true; this.nativeAudioChain?.dispose(); this.nativeAudioChain = null; this.nativeAudio = null; this.current = null; URL.revokeObjectURL(url); this.nativeAudioUrl = null; this.offset = this.wordOffset = this.wordLength = 0; if (++this.index < this.chunks.length) this.speakCurrent(); else { this.index = Math.max(0, this.chunks.length - 1); this.state = this.awaitingText ? 'waiting' : 'ended'; this.onChange?.(); if (!this.awaitingText) this.onEnded?.(); } };
                audio.onerror = () => { if (!valid()) return; this.cancelUtterance(); this.state = 'error'; this.onError?.('No se pudo reproducir el WAV de Windows. El texto se conserva.'); this.onChange?.(); };
                if (this.nativeAudioChain) await this.nativeAudioChain.context.resume();
                await audio.play();
            } catch (error) {
                if (generation !== this.generation) return;
                this.nativePending = false;
                this.cancelUtterance();
                if (!/^(moss|piper):/.test(this.voiceURI || '') && !window.__contractCalls && 'speechSynthesis' in window) {
                    try { browserSpeak.call(this); return; } catch { }
                }
                this.state = 'error'; this.onChange?.(); this.onError?.(error instanceof Error ? error.message : String(error));
                showVoiceStatus(error instanceof Error ? error.message : 'No se pudo reproducir la voz.', 'error');
            }
        })();
    };
    for (const [object, method] of [[Axx.symbiosis, 'refreshVoices'], [Axx.voice13, 'voices']]) if (object) object[method] = () => { void state.refreshVoices().catch(() => {}); };

    class LocalDictation {
        generation = 0; recorder = null; stream = null; chunks = []; bytes = 0; pending = false; timer = null; borrowedMeter = false; vadTimer = null; vadCtx = null; clip = null;
        constructor(owner, options) { this.owner = owner; this.preempt = options.preempt !== false; }
        change(value) { this.owner.state = value; this.owner.onState?.(); Axx.resident?.activity(); }
        async start(lang) {
            // Speculative owners must leave both capture and local ASR untouched.
            if (!this.preempt && (this.pending || state.activeCapture || this.recorder?.state === 'recording')) return 'busy';
            if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
                if (this.preempt) this.fail(this.generation, new Error('La captura de audio local no está disponible.'));
                return 'unavailable';
            }
            this.stop(false); const id = this.generation; this.lang = lang; this.lastVoiceAt = 0;
            if (state.activeCapture && state.activeCapture !== this) state.activeCapture.stop();
            // A previous owner's callback may hand the microphone to a successor.
            if (state.activeCapture && state.activeCapture !== this) return 'busy';
            state.activeCapture = this;
            this.change('starting');
            try {
                await state.cancelPromise;
                if(id!==this.generation)return 'unavailable';
                const meter = this.owner === Axx.voice13?.capture ? Axx.voice13.meter : null;
                const borrowedMeter = !!meter?.active; this.borrowedMeter = borrowedMeter;
                const device = this.owner === Axx.quickReply?.capture || this.owner === Axx.symbiosis?.dictation && Axx.symbiosis.use === 'live' ? state.liveDeviceId : '';
                const stream = borrowedMeter ? meter.stream : await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, ...(device ? {deviceId:{exact:device}} : {}) }, video: false });
                if (id !== this.generation) { if (!borrowedMeter) stream.getTracks().forEach(track => track.stop()); return 'unavailable'; }
                this.stream = stream;
                for(const track of stream.getAudioTracks())track.addEventListener('ended',()=>{if(id===this.generation&&this.recorder?.state==='recording')this.fail(id,new Error('El micrófono se desconectó. Elige otra entrada y vuelve a iniciar.'));},{once:true});
                const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
                if (!mime) throw new Error('WebView2 no ofrece un formato de grabación compatible.');
                const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64000 }); this.recorder = recorder; this.chunks = []; this.bytes = 0;
                recorder.ondataavailable = event => { if (id !== this.generation || !event.data.size) return; this.chunks.push(event.data); this.bytes += event.data.size; if (this.bytes >= 1000000) this.finish(); };
                recorder.onstart = () => { if (id === this.generation) void this.startVad(stream, id).then(() => { if (id === this.generation) this.change('listening'); }).catch(error => this.fail(id, error)); };
                recorder.onerror = () => this.fail(id, new Error('La captura de audio local se interrumpió.'));
                recorder.onstop = () => {
                    if (id !== this.generation || this.recorder !== recorder) return;
                    const blob = new Blob(this.chunks, { type: mime });
                    recorder.ondataavailable = recorder.onstop = recorder.onerror = recorder.onstart = null;
                    this.recorder = null; this.chunks = []; this.bytes = 0; this.release();
                    void this.submit(blob, id);
                };
                recorder.start(500); this.timer = setTimeout(() => this.finish(), 55000);
                return 'started';
            } catch (error) {
                const message = error?.name === 'NotFoundError' || error?.name === 'OverconstrainedError' ? 'El micrófono seleccionado no está disponible. Elige otro en Voz, ritmo y privacidad.'
                    : error?.name === 'NotAllowedError' ? 'Windows no permitió acceder al micrófono. Revisa el permiso de micrófono para Axx.'
                    : error?.name === 'NotReadableError' ? 'No se puede leer el micrófono. Revisa si está desconectado u ocupado por otra aplicación.' : error;
                this.fail(id, typeof message === 'string' ? new Error(message) : message);
                return 'unavailable';
            }
        }
        async startVad(stream, id) {
            const isChatDraft = this.owner === state.chatDraft;
            const isQuick = this.owner === Axx.quickReply?.capture;
            if (!isChatDraft && !isQuick && (this.owner !== Axx.symbiosis?.dictation || !['command', 'live'].includes(Axx.symbiosis?.use))) return;
                const Ctx = window.AudioContext || window.webkitAudioContext;
                if (!Ctx) throw new Error('El analizador de voz no está disponible. Actualiza WebView2 y vuelve a iniciar.');
                const ctx = new Ctx(), src = ctx.createMediaStreamSource(stream), analyser = ctx.createAnalyser();
                analyser.fftSize = 1024; src.connect(analyser); this.vadCtx = ctx;
                try { await Promise.race([ctx.resume(), new Promise((_,reject)=>{this.resumeTimer=setTimeout(()=>reject(new Error('El audio está suspendido. Vuelve a pulsar Iniciar para activar el micrófono.')),2500);}),new Promise(resolve=>{this.resumeCancelled=resolve;})]); }
                finally { clearTimeout(this.resumeTimer); this.resumeTimer=null; this.resumeCancelled=null; }
                if (id !== this.generation) return;
                if (ctx.state !== 'running') throw new Error('El audio está suspendido. Vuelve a pulsar Iniciar para activar el micrófono.');
                const buf = new Float32Array(analyser.fftSize);
                let heardSpeech = false, voiceFrames = 0, lastVoiceAt = performance.now(), startedAt = performance.now(), noiseFloor = 0;
                const calibration=[];let ready;const calibrated=new Promise(resolve=>{ready=resolve;this.calibrationCancelled=resolve;});
                state.inputLevel = { owner:this.owner, rms:0, threshold:.004, noise_floor:0, heard_speech:false, phase:'calibrating', device:stream.getAudioTracks()[0]?.label || 'Micrófono' };
                this.vadTimer = setInterval(() => {
                    if (id !== this.generation || this.recorder?.state !== 'recording') return;
                    if (ctx.state !== 'running') { this.fail(id,new Error('El analizador de voz se suspendió. Vuelve a iniciar la conversación.')); return; }
                    analyser.getFloatTimeDomainData(buf);
                    let sum = 0;
                    for (let i = 0; i < buf.length; i++) sum += buf[i]*buf[i];
                    const rms = Math.sqrt(sum / buf.length), now = performance.now();
                    const calibrating = now-startedAt < 480 || calibration.length < 6;
                    if(calibrating){
                        // A partial first analyser frame must not become the
                        // baseline. Require enough samples even under UI load.
                        calibration.push(rms);const settled=calibration.slice(-5).sort((a,b)=>a-b);
                        noiseFloor=settled[Math.floor(settled.length/2)];
                    }else if(ready){ready();ready=null;this.calibrationCancelled=null;}
                    const threshold=Math.max(.004,Math.min(.08,noiseFloor*2.5+.002));
                    const voiced=!calibrating&&noiseFloor<.04&&rms>threshold;
                    if (voiced) { voiceFrames++; if(voiceFrames>=2)heardSpeech = true; lastVoiceAt = now; if (heardSpeech) this.lastVoiceAt = now; }
                    else {
                        voiceFrames=0;
                        if(!calibrating)noiseFloor = rms<noiseFloor ? noiseFloor*.85+rms*.15 : noiseFloor*.997+Math.min(rms,.08)*.003;
                        const live = isQuick || !isChatDraft && Axx.symbiosis?.use === 'live';
                        const pause = live ? (Axx.liveConversation?.pauseMs || 550) : 550;
                        if (heardSpeech && now - lastVoiceAt > pause && now - startedAt > 600) this.finish();
                        else if (!heardSpeech && now - startedAt > (live ? 30000 : 9000)) this.fail(id,new Error('No se detectó una frase. Revisa el nivel y el micrófono elegido; también puedes pulsar Responder ahora.'));
                    }
                    if(id===this.generation)state.inputLevel={owner:this.owner,rms,noise_floor:noiseFloor,threshold,heard_speech:heardSpeech,last_voice_at:heardSpeech?lastVoiceAt:null,at:now,phase:calibrating?'calibrating':voiced?'voice':noiseFloor>=.04?'noise':'quiet',device:stream.getAudioTracks()[0]?.label||'Micrófono'};
                }, 80);
                await calibrated;
        }
        release() { clearTimeout(this.timer); this.timer = null; clearInterval(this.vadTimer); this.vadTimer = null; clearTimeout(this.resumeTimer); this.resumeTimer=null; this.resumeCancelled?.(); this.resumeCancelled=null; this.calibrationCancelled?.(); this.calibrationCancelled=null; if (this.vadCtx) { void this.vadCtx.close().catch(() => {}); this.vadCtx = null; } if (this.stream && this.borrowedMeter) Axx.voice13?.meter.stop(); else this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; this.borrowedMeter = false; if(state.inputLevel?.owner===this.owner)state.inputLevel=null; }
        clearClip(clip = this.clip) { if (!clip) return; if (clip.reader?.readyState === 1) clip.reader.abort(); clip.reader = null; if (clip.payload) clip.payload.audio_base64 = ''; clip.blob = clip.audio = clip.payload = null; if (this.clip === clip) this.clip = null; }
        finish() { if (this.recorder?.state === 'recording') { this.change('stopping'); this.recorder.stop(); this.release(); } }
        async submit(blob, id = this.generation) {
            const clip = { blob, audio: null, payload: null, reader: null }; blob = null;
            if (id !== this.generation) { this.clearClip(clip); return; }
            this.clip = clip;
            this.pending = true;
            try {
                if (clip.blob.size === 0 || clip.blob.size > 1400000) throw new Error('El clip está vacío o supera 1,4 MB. Graba una frase más corta.');
                this.owner.onInterim?.('Procesando el audio localmente…');
                if (id !== this.generation) return;
                clip.audio = await base64(clip); if (id !== this.generation) return;
                await state.cancelPromise; if(id!==this.generation)return;
                const language = this.lang?.toLowerCase().startsWith('es') ? 'es' : this.lang?.toLowerCase().startsWith('en') ? 'en' : 'auto';
                const began=performance.now();
                clip.payload = { audio_base64: clip.audio, mime: clip.blob.type, language, task: 'transcribe' };
                const data = await Axx.backendRequest('POST', '/axx-api/speech/transcribe', clip.payload);
                if (id !== this.generation) return;
                this.pending = false;
                state.lastRecognition={duration_ms:Math.round(performance.now()-began),speech_end_at_ms:this.lastVoiceAt || null,
                    completed_at_ms:performance.now(),timings_ms:data.timings_ms ? {...data.timings_ms} : null};
                if (typeof data.text !== 'string' || !data.text.trim()) throw new Error('No se reconoció una frase. El destino no se ha modificado.');
                this.clearClip(clip);
                this.owner.onFinal?.(data.text);
                // A voice command may transfer the microphone to another session.
                if (id !== this.generation) return;
                this.owner.onInterim?.(''); this.change('idle'); this.owner.onEnded?.();
            } catch (error) { this.fail(id, error); }
            finally {
                this.clearClip(clip);
                if (id === this.generation) {
                    this.pending = false; this.chunks = []; this.bytes = 0; this.release();
                    if (state.activeCapture === this) state.activeCapture = null;
                }
            }
        }
        fail(id, error) { if (id !== this.generation) return; this.stop(false); this.change('error'); this.owner.onInterim?.(''); this.owner.onError?.(error instanceof Error ? error.message : String(error)); }
        stop(notify = true) { this.generation++; if (this.pending) cancelWorker(); this.pending = false; this.clearClip(); const recorder = this.recorder; this.recorder = null; if (recorder) { recorder.ondataavailable = recorder.onstop = recorder.onerror = recorder.onstart = null; if (recorder.state !== 'inactive') recorder.stop(); } this.release(); this.chunks = []; this.bytes = 0; if (state.activeCapture === this) state.activeCapture = null; if (notify) this.change('idle'); }
    }
    state.sessions = [];
    state.attach = (owner, options = {}) => {
        if (!options || typeof options !== 'object' || Array.isArray(options) || Object.keys(options).some(key => key !== 'preempt') || 'preempt' in options && typeof options.preempt !== 'boolean') throw new TypeError('Opciones internas de captura inválidas.');
        const local = new LocalDictation(owner, options); state.sessions.push(local);
        Object.defineProperty(owner, 'available', { configurable: true, get: () => !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined' });
        owner.start = lang => local.start(lang); owner.finish = () => local.finish();
        owner.stop = () => local.stop();
    };
    for (const owner of [Axx.voice13?.capture, Axx.symbiosis?.dictation, Axx.flow?.capture]) if (owner) state.attach(owner);

    // The composer dictates into its own draft. It uses the same exclusive
    // capture service as other voice tools, without interpreting or sending text.
    const chatField = document.getElementById('chat-input');
    let draftTarget = null;
    const chatDraft = state.chatDraft = {
        state: 'idle',
        onState() {
            const active = ['starting', 'listening', 'stopping'].includes(this.state);
            const c = Axx.companion, mic = document.getElementById('chat-mic');
            c.dictating = this.state === 'listening' || this.state === 'stopping';
            c.dictationStarting = this.state === 'starting';
            const label = this.state === 'listening' ? 'Terminar dictado y transcribir' : active ? 'Cancelar dictado' : 'Dictar un mensaje';
            mic.setAttribute('aria-pressed', String(active));
            mic.setAttribute('aria-label', label); mic.title = label;
            document.getElementById('speech-indicator').hidden = !active && !c.speaking;
            if (active) document.getElementById('speech-status').textContent = this.state === 'starting' ? 'Preparando micrófono…' : this.state === 'stopping' ? 'Transcribiendo en este equipo…' : 'Dictando tu mensaje · pulsa el micrófono para terminar';
            c.refreshVoiceState();
        },
        onFinal(text) {
            const target = draftTarget;
            if (!target || target.conversationId !== Axx.chatWorkspace?.active?.id || chatField.value !== target.value || !chatField.getClientRects().length) return;
            const prefix = target.start > 0 && !/\s$/.test(target.value.slice(0, target.start)) ? ' ' : '';
            const insert = prefix + text.trim() + ' ';
            if (chatField.maxLength > 0 && target.value.length - (target.end - target.start) + insert.length > chatField.maxLength) {
                Axx.companion.sayStatus('El dictado supera el límite del mensaje. Acorta el borrador y vuelve a dictar.', true);
                return;
            }
            chatField.setRangeText(insert, target.start, target.end, 'end');
            draftTarget = null;
            chatField.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
            Axx.companion.scheduleDrafts();
        },
        onError(message) { draftTarget = null; Axx.companion.sayStatus(message, true); },
        onInterim(message) { if (message) document.getElementById('speech-status').textContent = message; },
        onEnded() { draftTarget = null; },
    };
    state.attach(chatDraft);
    const beginDraft = chatDraft.start, stopDraft = chatDraft.stop;
    chatDraft.start = () => {
        if (!chatField?.getClientRects().length || chatField.disabled) return;
        Axx.liveConversation?.stop(); Axx.companion.stopDictation(); Axx.companion.stopSpeech();
        Axx.app.stopAudio(); Axx.app.stopDemo();
        draftTarget = { conversationId: Axx.chatWorkspace?.active?.id, value: chatField.value, start: chatField.selectionStart, end: chatField.selectionEnd };
        beginDraft(Axx.symbiosis?.prefs.language || 'es-DO');
    };
    chatDraft.stop = () => { draftTarget = null; stopDraft(); };
    chatDraft.toggle = () => {
        if (chatDraft.state === 'listening') chatDraft.finish();
        else if (['starting', 'stopping'].includes(chatDraft.state)) chatDraft.stop();
        else chatDraft.start();
    };
    chatField?.addEventListener('input', () => {
        if (draftTarget && chatField.value !== draftTarget.value) chatDraft.stop();
    });
    const chatPanel = document.getElementById('panel');
    const draftVisibility = new MutationObserver(() => {
        if (draftTarget && (chatPanel.hidden || chatPanel.dataset.view !== 'chat')) chatDraft.stop();
    });
    if (chatPanel) draftVisibility.observe(chatPanel, { attributes: true, attributeFilter: ['hidden', 'data-view'] });
    window.addEventListener('pagehide', () => draftVisibility.disconnect());

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
                                selection_mode: Axx.companion.data.prefs.selection_mode || 'manual',
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

    class WakeController {
        active = false;
        mode = 'hotkey';
        hotkey = 'Alt+Shift+V';
        recording = false;
        rearmTimer = null;
        paused = false;
        statusText = 'Micrófono apagado · Pulsa el atajo o el botón de voz para dictar.';

        constructor() {
            try {
                this.mode = localStorage.getItem('axx.activation.mode') || 'hotkey';
                this.hotkey = localStorage.getItem('axx.activation.hotkey') || 'Alt+Shift+V';
            } catch {
                this.mode = 'hotkey';
                this.hotkey = 'Alt+Shift+V';
            }
            this.statusText = this.mode === 'always_active'
                ? 'Siempre activo · Escuchando continuamente mientras Axx esté abierto.'
                : 'Micrófono apagado · Pulsa 🎙️ Orden voz o ' + this.hotkey + ' para hablar.';
            this.initListeners();
        }

        initListeners() {
            window.addEventListener('keydown', e => {
                if (this.recording) {
                    e.preventDefault();
                    e.stopPropagation();
                    this.captureRecordedKey(e);
                    return;
                }
                if (e.isComposing || e.repeat) return;
                if (this.matches(e)) {
                    e.preventDefault();
                    e.stopPropagation();
                    this.toggle();
                }
            }, true);

            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    if (this.rearmTimer) { clearTimeout(this.rearmTimer); this.rearmTimer = null; }
                    if (this.active && this.mode === 'always_active') this.stop(false);
                } else if (this.mode === 'always_active') {
                    this.scheduleRearm(400);
                }
            });
        }

        matches(e) {
            if (!this.hotkey) return false;
            const parts = this.hotkey.toLowerCase().split('+').map(s => s.trim());
            const wantCtrl = parts.includes('ctrl') || parts.includes('control');
            const wantAlt = parts.includes('alt');
            const wantShift = parts.includes('shift');
            const wantMeta = parts.includes('meta') || parts.includes('win') || parts.includes('cmd');
            if (Boolean(e.ctrlKey) !== wantCtrl) return false;
            if (Boolean(e.altKey) !== wantAlt) return false;
            if (Boolean(e.shiftKey) !== wantShift) return false;
            if (Boolean(e.metaKey) !== wantMeta) return false;
            const keyPart = parts.find(p => !['ctrl','control','alt','shift','meta','win','cmd'].includes(p));
            if (!keyPart) return false;
            if (keyPart === 'space') return e.code === 'Space' || e.key === ' ';
            if (keyPart === 'enter') return e.code === 'Enter';
            if (e.key && e.key.toLowerCase() === keyPart) return true;
            if (e.code && e.code.toLowerCase() === ('key' + keyPart)) return true;
            if (e.code && e.code.toLowerCase() === keyPart) return true;
            return false;
        }

        startRecording() {
            this.recording = true;
            this.syncUI();
        }

        stopRecording() {
            this.recording = false;
            this.syncUI();
        }

        captureRecordedKey(e) {
            const isModifier = ['Control', 'Shift', 'Alt', 'Meta'].includes(e.key);
            if (isModifier) return;
            const parts = [];
            if (e.ctrlKey) parts.push('Ctrl');
            if (e.altKey) parts.push('Alt');
            if (e.shiftKey) parts.push('Shift');
            if (e.metaKey) parts.push('Win');
            let keyName = e.key;
            if (e.code === 'Space' || e.key === ' ') keyName = 'Space';
            else if (e.code.startsWith('Key')) keyName = e.code.slice(3).toUpperCase();
            else if (e.code.startsWith('Digit')) keyName = e.code.slice(5);
            else if (keyName.length === 1) keyName = keyName.toUpperCase();
            parts.push(keyName);
            const combo = parts.join('+');
            this.setHotkey(combo);
            this.stopRecording();
        }

        setMode(mode) {
            this.mode = mode === 'always_active' ? 'always_active' : 'hotkey';
            try { localStorage.setItem('axx.activation.mode', this.mode); } catch {}
            if (this.rearmTimer) { clearTimeout(this.rearmTimer); this.rearmTimer = null; }
            if (this.mode === 'always_active') {
                this.paused = false;
                this.statusText = 'Siempre activo · Escuchando continuamente mientras Axx esté abierto.';
                this.listenOnce();
            } else {
                this.stop();
                this.statusText = 'Modo atajo (' + this.hotkey + ') activado.';
            }
            this.syncUI();
        }

        setHotkey(combo) {
            if (!combo || typeof combo !== 'string') combo = 'Alt+Shift+V';
            this.hotkey = combo.trim();
            try { localStorage.setItem('axx.activation.hotkey', this.hotkey); } catch {}
            this.statusText = this.mode === 'always_active'
                ? 'Siempre activo · Escuchando continuamente mientras Axx esté abierto.'
                : 'Atajo actualizado a ' + this.hotkey + ' · Pulsa para hablar.';
            this.syncUI();
        }

        resetHotkey() {
            this.setHotkey('Alt+Shift+V');
        }

        onSpeechFinished() {
            this.scheduleRearm(450);
        }

        scheduleRearm(delay = 500) {
            if (this.rearmTimer) clearTimeout(this.rearmTimer);
            this.rearmTimer = null;
            if (this.mode !== 'always_active' || this.paused || document.hidden || Axx.companion?.data?.prefs?.mutedAll) return;
            this.rearmTimer = setTimeout(() => {
                this.rearmTimer = null;
                if (this.mode !== 'always_active' || this.paused || document.hidden || this.active || Axx.companion?.data?.prefs?.mutedAll) return;
                const readerState = Axx.symbiosis?.reader?.state;
                if (Axx.companion?.pending || Axx.companion?.speaking || ['starting', 'speaking', 'paused'].includes(readerState)) {
                    this.scheduleRearm(500);
                    return;
                }
                this.listenOnce();
            }, delay);
        }

        toggle() {
            if (this.active) {
                this.stop();
            } else {
                this.listenOnce();
            }
            return this.active;
        }

        start() {
            this.listenOnce();
        }

        stop(pause = true) {
            this.paused = pause;
            this.active = false;
            if (this.rearmTimer) { clearTimeout(this.rearmTimer); this.rearmTimer = null; }
            if (Axx.symbiosis?.use === 'command') Axx.symbiosis.dictation.stop();
            this.statusText = this.mode === 'always_active'
                ? 'Escucha pausada · Pulsa Hablar para reanudar el modo continuo.'
                : 'Escucha detenida · Pulsa ' + this.hotkey + ' para hablar.';
            this.syncUI();
        }

        listenOnce() {
            if (!Axx.symbiosis) return;
            this.paused = false;
            if (this.rearmTimer) { clearTimeout(this.rearmTimer); this.rearmTimer = null; }
            Axx.liveConversation?.stop();
            state.chatDraft.stop();
            this.active = true;
            this.statusText = this.mode === 'always_active'
                ? 'Siempre activo · Escuchando tu voz… Habla y deja una pausa.'
                : 'Escuchando una orden por voz… Habla y deja una pausa.';
            this.syncUI();
            Axx.symbiosis.startListening('command');
        }

        syncUI() {
            const listening = Axx.symbiosis?.use === 'command' && ['listening', 'starting', 'stopping'].includes(Axx.symbiosis?.dictation?.state);
            this.active = listening;
            for (const id of ['chat20-wake-toggle', 'wake20-toggle-btn']) {
                const btn = document.getElementById(id);
                if (!btn) continue;
                btn.setAttribute('aria-pressed', String(listening));
                btn.classList.toggle('is-listening', listening);
                if (id === 'wake20-toggle-btn') btn.textContent = listening ? '⏹️ Detener escucha' : '🎙️ Hablar comando por voz';
                if (id === 'chat20-wake-toggle') {
                    btn.title = listening
                        ? 'Detener escucha de voz'
                        : (this.mode === 'always_active' ? 'Modo siempre activo (Hands-free)' : 'Dictar comando por voz (' + this.hotkey + ')');
                }
            }
            const status = document.getElementById('wake20-status-text');
            if (status) status.textContent = this.statusText;
            const card = document.getElementById('wake20-roadmap');
            if (card) card.dataset.state = listening ? 'active' : 'idle';

            // Sync dedicated activation section controls
            const modeSelects = [document.getElementById('chat-activation-mode'), document.getElementById('roadmap-activation-mode')];
            for (const sel of modeSelects) {
                if (sel && sel.value !== this.mode) sel.value = this.mode;
            }
            const hotkeyInputs = [document.getElementById('chat-activation-hotkey'), document.getElementById('roadmap-activation-hotkey')];
            for (const inp of hotkeyInputs) {
                if (inp) inp.value = this.recording ? 'Pulsa tus teclas…' : this.hotkey;
                if (inp) inp.style.borderColor = this.recording ? '#00e5ff' : '';
            }
            const hotkeyWraps = [document.getElementById('chat-hotkey-wrap'), document.getElementById('roadmap-hotkey-wrap')];
            for (const wrap of hotkeyWraps) {
                if (wrap) wrap.hidden = this.mode === 'always_active';
            }
            const alwaysTips = [document.getElementById('chat-always-tip'), document.getElementById('roadmap-always-tip')];
            for (const tip of alwaysTips) {
                if (tip) tip.hidden = this.mode !== 'always_active';
            }
            const recordBtns = [document.getElementById('chat-hotkey-record'), document.getElementById('roadmap-hotkey-record')];
            for (const btn of recordBtns) {
                if (btn) btn.textContent = this.recording ? 'Cancelar' : 'Grabar';
            }

            let banner = document.getElementById('chat-voice-banner');
            if (!banner) {
                const form = document.getElementById('chat-form');
                if (form) {
                    banner = document.createElement('div');
                    banner.id = 'chat-voice-banner';
                    banner.className = 'chat-voice-banner';
                    banner.setAttribute('role','status'); banner.setAttribute('aria-live','polite');
                    banner.innerHTML = '<span class="chat-voice-dot"></span><span id="chat-voice-text">Escuchando una orden por voz…</span><button id="chat-voice-cancel" type="button">Detener</button>';
                    form.before(banner);
                    banner.querySelector('#chat-voice-cancel')?.addEventListener('click', () => state.wake.stop());
                }
            }
            if (banner) {
                banner.hidden = !listening || Axx.symbiosis?.use !== 'command';
                const txt = banner.querySelector('#chat-voice-text');
                if (txt) txt.textContent = listening ? (this.statusText || 'Escuchando una orden por voz…') : '';
            }
        }
    }
    state.wake = Axx.heyAxx = new WakeController();
    if (Axx.symbiosis?.dictation) {
        const prevOnState = Axx.symbiosis.dictation.onState;
        Axx.symbiosis.dictation.onState = () => {
            prevOnState?.();
            document.getElementById('chat-mic')?.setAttribute('aria-pressed', String(['starting', 'listening', 'stopping'].includes(chatDraft.state)));
            const st = Axx.symbiosis?.use === 'command' ? Axx.symbiosis.dictation.state : 'idle';
            if (st === 'idle' && state.wake.active) {
                state.wake.active = false;
                state.wake.statusText = state.wake.mode === 'always_active'
                    ? 'Siempre activo · Procesando…'
                    : 'Listo · Pulsa 🎙️ Orden voz o ' + state.wake.hotkey + ' para hablar.';
                if (state.wake.mode === 'always_active') {
                    // Fallback rearm if no speech is spoken after 2.5s
                    state.wake.scheduleRearm(2500);
                }
            } else if (st === 'listening') {
                state.wake.active = true;
                state.wake.statusText = state.wake.mode === 'always_active'
                    ? 'Siempre activo · Escuchando tu voz…'
                    : 'Escuchando una orden por voz…';
            } else if (st === 'starting') {
                state.wake.active = true;
                state.wake.statusText = 'Iniciando micrófono y Whisper local…';
            }
            state.wake.syncUI();
        };
    }
    if (!window.__contractCalls) setTimeout(() => {
        void state.refreshVoices().catch(() => {});
        state.wake.syncUI();
        if (state.wake.mode === 'always_active') state.wake.scheduleRearm(400);
    }, 300);

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
