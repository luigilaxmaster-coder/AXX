/* Start early when PCM arrives faster than playback; buffer slow phrases intact. */
(function (Axx) {
    if (!Axx) return;
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
    let sharedContext;
    const context = () => {
        if (!sharedContext || sharedContext.state === 'closed') sharedContext = new AudioContext();
        return sharedContext;
    };
    Axx.prepareSpeechAudio = () => context().resume().catch(() => {});
    window.addEventListener('pagehide', () => { void sharedContext?.close().catch(() => {}); });
    class CustomSpeechStream {
        constructor(reader, voice, generation) {
            this.reader = reader; this.voice = voice; this.generation = generation;
            this.language = reader.lang || 'auto';
            this.context = context(); this.sources = new Set(); this.timers = new Set();
            this.stopped = false; this.pending = false; this.nextTime = 0;
            this.nextIndex = reader.index; this.started = performance.now(); this.played = false;
            this.evidence = { engine: 'moss-onnx', voice: voice.name, streaming: true,
                playing_event: false, ended_event: false, chunks: 0, underruns: 0, buffering: 'adaptive', phrase_gaps: 0,
                streamed_phrases: 0, cached_phrases: 0, rebufferings: 0 };
        }
        valid() { return !this.stopped && this.reader.generation === this.generation; }
        async stop() {
            this.stopped = true;
            for (const timer of this.timers) clearTimeout(timer);
            this.timers.clear();
            for (const source of this.sources) { try { source.stop(); } catch {} }
            this.sources.clear();
        }
        async pause() { await this.context.suspend(); }
        async resume() { await this.context.resume(); }
        enqueue(event, index) {
            const rate = event.sample_rate, channels = event.channels;
            if (![24000, 48000].includes(rate) || ![1, 2].includes(channels)
                || typeof event.pcm_base64 !== 'string' || event.pcm_base64.length > 1024 * 1024)
                throw new Error('El motor de voz devolvió audio inválido.');
            const raw = Uint8Array.from(atob(event.pcm_base64), c => c.charCodeAt(0));
            if (!raw.length || raw.length % (channels * 2)) throw new Error('Fragmento de voz incompleto.');
            const frames = raw.length / (channels * 2), view = new DataView(raw.buffer);
            const buffer = this.context.createBuffer(channels, frames, rate);
            for (let channel = 0; channel < channels; channel++) {
                const output = buffer.getChannelData(channel);
                for (let frame = 0; frame < frames; frame++) output[frame] = view.getInt16((frame * channels + channel) * 2, true) / 32768;
            }
            const source = this.context.createBufferSource(); source.buffer = buffer;
            const speed = Math.max(.75, Math.min(1.3, Number(this.reader.rate) || 1));
            source.playbackRate.value = speed; source.connect(this.context.destination);
            const now = this.context.currentTime;
            if (this.nextTime && this.nextTime < now) this.evidence.underruns++;
            const start = Math.max(now + .04, this.nextTime);
            this.nextTime = start + buffer.duration / speed;
            this.sources.add(source); this.evidence.chunks++;
            source.onended = () => { this.sources.delete(source); source.disconnect(); };
            source.start(start);
            // Observe the audio clock (which stops on pause), not a wall timer.
            const observe = () => {
                if (!this.valid()) return;
                if (this.context.currentTime + .001 < start || this.context.state !== 'running') {
                    const timer = setTimeout(() => { this.timers.delete(timer); observe(); }, 20);
                    this.timers.add(timer); return;
                }
                if (!this.played) {
                    this.played = true; this.evidence.playing_event = true;
                    this.evidence.first_audio_ms = Math.round(performance.now() - this.started);
                    Axx.nativeVoice.playback = this.evidence;
                }
                if (this.reader.state !== 'paused') this.reader.state = 'speaking';
                this.reader.index = index; this.reader.onChange?.();
            };
            observe();
        }
        async phrase(text, index) {
            this.pending = true; this.reader.nativePending = true;
            let response;
            for (let attempt = 0; ; attempt++) {
                if (!this.valid()) return;
                try {
                    response = await Axx.backendRequest('POST', '/axx-api/speech/stream/start',
                        { text, voice: this.voice.name, language: this.language, rate: 0, volume: 100 });
                    break;
                } catch (error) {
                    if (attempt >= 20 || !/BUSY|still preparing/i.test(String(error))) throw error;
                    await wait(150);
                }
            }
            let cursor = 0, bytes = 0, seconds = 0, sent = 0, streaming = false, rebuffered = false, firstPacket;
            const events = [];
            const expectedSeconds = Number.isFinite(response.estimated_audio_seconds)
                ? Math.max(1, Math.min(90, response.estimated_audio_seconds)) : Math.max(1, text.length / 7.5) + .5;
            while (this.valid()) {
                const packet = await Axx.backendRequest('POST', '/axx-api/speech/stream/poll',
                    { stream_id: response.stream_id, after: cursor });
                if (!this.valid()) return;
                if (packet.error) throw new Error(packet.error.message || 'No se pudo generar la voz.');
                if (streaming && sent && this.nextTime < this.context.currentTime && !packet.done) {
                    streaming = false; rebuffered = true; this.nextTime = 0;
                    this.evidence.underruns++; this.evidence.rebufferings++;
                }
                for (const event of packet.events) {
                    if (event.seq !== cursor + 1) throw new Error('Se interrumpió el flujo de voz.');
                    bytes += event.pcm_base64.length;
                    if(bytes>16*1024*1024||events.length>=512)throw new Error('La frase supera el límite de audio.');
                    events.push(event); cursor = event.seq;
                    seconds += atob(event.pcm_base64).length / (2 * event.channels * event.sample_rate);
                    if (!firstPacket) firstPacket = { at: performance.now(), elapsed: event.elapsed_ms, seconds };
                }
                const latest = events.at(-1), speed = Math.max(.75, Math.min(1.3, Number(this.reader.rate) || 1));
                const produced = seconds - (firstPacket?.seconds || 0);
                const elapsed = Math.max(performance.now() - (firstPacket?.at || performance.now()),
                    (latest?.elapsed_ms || 0) - (firstPacket?.elapsed || 0)) / 1000;
                const ratio = produced > 0 ? elapsed / produced : Infinity;
                const reserve = .6 + Math.max(0, Math.max(1, expectedSeconds - seconds) * (ratio - 1 / speed));
                // Slow CPUs need enough buffered audio to cover the estimated
                // remaining synthesis. A later stall falls back to whole phrases.
                if (!streaming && latest && !rebuffered &&
                    (latest.cache_hit || (events.length >= 4 && seconds / speed >= Math.max(1, reserve)))) {
                    streaming = true; this.evidence.streamed_phrases++;
                    if (latest.cache_hit) this.evidence.cached_phrases++;
                }
                if (streaming || packet.done) {
                    if (!sent && this.nextTime && this.nextTime < this.context.currentTime) {
                        this.evidence.phrase_gaps++; this.nextTime = 0;
                    }
                    while (sent < events.length) this.enqueue(events[sent++], index);
                }
                if (packet.done) break;
                // The backend waits for the next PCM event. Browser background
                // timer throttling must not delay delivery to the audio clock.
            }
            if(!this.valid())return;
            this.pending = false; this.reader.nativePending = false;
        }
        async play() {
            await this.context.resume();
            while (this.valid()) {
                if (this.nextIndex < this.reader.chunks.length && this.nextTime - this.context.currentTime < 8) {
                    const index = this.nextIndex++;
                    const text = this.reader.chunks[index]?.slice(index === this.reader.index ? this.reader.offset : 0);
                    let remaining = text || '';
                    while (remaining && this.valid()) {
                        const length = Axx.voiceConversation?.phraseLength(remaining, true) || remaining.length;
                        await this.phrase(remaining.slice(0, length).trim(), index);
                        remaining = remaining.slice(length).trimStart();
                    }
                } else if (!this.sources.size && this.nextIndex >= this.reader.chunks.length && !this.reader.awaitingText) {
                    if (!this.played) throw new Error('El motor no generó audio reproducible.');
                    this.evidence.ended_event = true;
                    this.reader.current = null; this.reader.offset = this.reader.wordOffset = this.reader.wordLength = 0;
                    this.reader.index = Math.max(0, this.reader.chunks.length - 1);
                    this.reader.nativeStream = null;
                    this.reader.state = 'ended'; this.reader.onChange?.(); this.reader.onEnded?.();
                    await this.stop(); return;
                } else await wait(35);
            }
        }
    }
    Axx.CustomSpeechStream = CustomSpeechStream;
})(window.Axx);
