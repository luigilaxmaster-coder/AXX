/* Native speech adapters for the existing Axx reader/dictation controllers.
 * Draft: not loaded by Axx.html until the resident snapshot is accepted. */
(function installNativeVoice(Axx) {
    if (!Axx?.isNative?.() || Axx.nativeVoice) return;
    const state = Axx.nativeVoice = { activeCapture: null, voices: [], voicePromise: null, playback: null };
    const cancelWorker = () => void Axx.backendRequest('POST', '/axx-api/actions/cancel', {}).catch(() => {});
    const base64 = blob => new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error('No se pudo leer el audio capturado.')); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(blob); });
    state.refreshVoices = async () => {
        if (!state.voicePromise) state.voicePromise = Axx.backendRequest('GET', '/axx-api/speech/voices').then(data => {
            if (!data.available || !Array.isArray(data.voices)) throw new Error('Windows no ofrece voces locales de lectura.');
            state.voices = data.voices.filter(v => v.enabled !== false && typeof v.name === 'string');
            for (const [id, reader] of [['reader-voice', Axx.symbiosis?.reader], ['v13-voice', Axx.voice13?.reader]]) {
                const select = document.getElementById(id); if (!select) continue;
                select.replaceChildren(new Option('Voz local de Windows · automática', ''));
                for (const voice of state.voices) select.add(new Option(voice.name + ' · ' + voice.language, 'sapi:' + voice.name));
                select.value = reader?.voiceURI || '';
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
            } catch (error) { if (generation !== this.generation) return; this.nativePending = false; this.cancelUtterance(); this.state = 'error'; this.onChange?.(); this.onError?.(error instanceof Error ? error.message : String(error)); }
        })();
    };
    for (const [object, method] of [[Axx.symbiosis, 'refreshVoices'], [Axx.voice13, 'voices']]) if (object) object[method] = () => { void state.refreshVoices().catch(() => {}); };

    class LocalDictation {
        generation = 0; recorder = null; stream = null; chunks = []; bytes = 0; pending = false; timer = null; borrowedMeter = false;
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
                recorder.onstart = () => { if (id === this.generation) this.change('listening'); };
                recorder.onerror = () => this.fail(id, new Error('La captura de audio local se interrumpió.'));
                recorder.onstop = () => { this.release(); if (id === this.generation) void this.submit(new Blob(this.chunks, { type: mime }), id); };
                recorder.start(500); this.timer = setTimeout(() => this.finish(), 55000);
            } catch (error) { this.fail(id, error); }
        }
        release() { clearTimeout(this.timer); this.timer = null; if (this.stream && this.borrowedMeter) Axx.voice13?.meter.stop(); else this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; this.borrowedMeter = false; }
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
        owner.start = lang => { void local.start(lang); }; owner.finish = () => local.finish(); owner.stop = () => local.stop();
    }
    const privacy = document.getElementById('v13-permit-copy'); if (privacy) privacy.textContent = 'Se grabará un clip local de hasta 55 segundos para transcribirlo con Whisper tiny en este equipo. El texto se coloca en tu destino; no se envía al chat.';
    window.addEventListener('pagehide', () => { for (const session of state.sessions) session.stop(); Axx.symbiosis?.reader.stop(); Axx.voice13?.reader.stop(); });
})(window.Axx);
