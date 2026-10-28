/* Per-voice sound color for local PCM and WAV playback; no raw audio is stored. */
(function (Axx) {
    const key = 'axx.voice.audio.v1';
    const limits = { bass: [-9, 9], presence: [-9, 9], air: [-9, 9], level: [.5, 1.15], pitch: [-2, 2] };
    const neutral = { bass: 0, presence: 0, air: 0, level: 1, pitch: 0 };
    const presets = {
        natural: neutral,
        warm: { bass: 3, presence: 0, air: -2, level: 1, pitch: 0 },
        clear: { bass: -2, presence: 3, air: 2, level: 1, pitch: 0 },
        soft: { bass: 1, presence: -2, air: -3, level: .95, pitch: 0 }
    };
    const personalitySound = {
        natural: neutral,
        friendly: { ...neutral, bass: 1, air: -1 },
        direct: { ...neutral, presence: 1, air: 1 },
        formal: { ...neutral, presence: 1 },
        playful: { ...neutral, presence: 1, air: 1 },
        psycho: { ...neutral, bass: 2, air: -1 }
    };
    const personalityRate = { natural: 1, friendly: .98, direct: 1.03, formal: .97, playful: 1.04, psycho: .95 };
    let saved;
    try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch { saved = {}; }
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
    const chains = new Set();
    let audioContext;
    const clamp = (name, value) => {
        const number = Number(value), [min, max] = limits[name];
        return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : neutral[name];
    };
    const valid = voice => /^(moss|piper):[a-z0-9_-]{1,70}$/i.test(voice || '');
    const personality = () => Axx.companion?.data?.prefs?.personalityStyle || 'natural';
    const manual = voice => Object.hasOwn(saved, voice);
    const get = voice => Object.fromEntries(Object.keys(limits).map(name =>
        [name, clamp(name, valid(voice) ? (manual(voice) ? saved[voice]?.[name] : personalitySound[personality()]?.[name]) : undefined)]));
    const apply = chain => {
        const values = get(chain.voice), now = chain.context.currentTime;
        for (const [name, node] of [['bass', chain.bass], ['presence', chain.presence], ['air', chain.air]])
            node.gain.setTargetAtTime(values[name], now, .03);
        chain.level.gain.setTargetAtTime(values.level, now, .03);
    };
    const set = (voice, patch) => {
        if (!valid(voice) || !patch || typeof patch !== 'object') return get(voice);
        saved[voice] = { ...get(voice), ...Object.fromEntries(Object.keys(limits)
            .filter(name => Object.hasOwn(patch, name)).map(name => [name, clamp(name, patch[name])])) };
        try { localStorage.setItem(key, JSON.stringify(saved)); } catch { }
        for (const chain of chains) if (chain.voice === voice) apply(chain);
        return get(voice);
    };
    const reset = voice => {
        if (!valid(voice)) return;
        delete saved[voice];
        try { localStorage.setItem(key, JSON.stringify(saved)); } catch { }
        for (const active of chains) if (active.voice === voice) apply(active);
    };
    const context = () => audioContext && audioContext.state !== 'closed' ? audioContext : (audioContext = new AudioContext());
    const chain = (ctx, voice) => {
        const bass = ctx.createBiquadFilter(); bass.type = 'lowshelf'; bass.frequency.value = 180;
        const presence = ctx.createBiquadFilter(); presence.type = 'peaking'; presence.frequency.value = 1550; presence.Q.value = .8;
        const air = ctx.createBiquadFilter(); air.type = 'highshelf'; air.frequency.value = 4200;
        const limiter = ctx.createDynamicsCompressor(); limiter.threshold.value = -3; limiter.knee.value = 3;
        limiter.ratio.value = 6; limiter.attack.value = .003; limiter.release.value = .15;
        const level = ctx.createGain();
        bass.connect(presence).connect(air).connect(limiter).connect(level).connect(ctx.destination);
        const result = { input: bass, context: ctx, voice, bass, presence, air, level,
            dispose() { chains.delete(result); for (const node of [bass, presence, air, limiter, level]) node.disconnect(); } };
        chains.add(result); apply(result);
        return result;
    };
    const attach = (element, voice) => {
        const ctx = context(), source = ctx.createMediaElementSource(element), output = chain(ctx, voice);
        source.connect(output.input);
        return { ...output, context: ctx, dispose() { source.disconnect(); output.dispose(); } };
    };
    Axx.voiceAudio = { get, set, reset, presets, chain, attach, context,
        refreshPersonality() { for (const active of chains) if (!manual(active.voice)) apply(active); this.refreshPanel?.(); },
        speed(voice, rate) { return Math.max(.65, Math.min(1.5, Number(rate) || 1) * (manual(voice) ? 1 : personalityRate[personality()] || 1) * 2 ** (get(voice).pitch / 12)); } };
    const mount = () => {
        const host = document.getElementById('voice-panel-controls');
        const voiceSelect = document.getElementById('voice-panel-select');
        if (!host || !voiceSelect || document.getElementById('voice-audio-controls')) return;
        const section = document.createElement('section');
        section.id = 'voice-audio-controls';
        section.innerHTML = '<div class="voice-studio-heading"><strong>Sonido de la voz</strong><span>Por voz · MOSS y Piper</span></div><label>Perfil de sonido<select id="voice-audio-preset"><option value="auto">Según personalidad</option><option value="natural">Natural</option><option value="warm">Cálida</option><option value="clear">Clara</option><option value="soft">Suave</option><option value="custom">Personalizado</option></select></label><div class="voice-audio-sliders"></div><button id="voice-audio-reset" type="button">Usar sonido de personalidad</button><p id="voice-audio-note" class="micro-copy">La personalidad ajusta sutilmente el ritmo y el color; tus ajustes manuales tienen prioridad. Los audios originales permanecen intactos.</p>';
        const labels = { bass: ['Cuerpo · graves', '-9', '9', '1', ' dB'], presence: ['Claridad · medios', '-9', '9', '1', ' dB'], air: ['Brillo · agudos', '-9', '9', '1', ' dB'], pitch: ['Altura', '-2', '2', '.5', ' semitonos'], level: ['Nivel', '.5', '1.15', '.05', '×'] };
        for (const [name, [title, min, max, step]] of Object.entries(labels)) {
            const label = document.createElement('label');
            label.textContent = title;
            const output = document.createElement('output'); output.id = 'voice-audio-' + name + '-value';
            const input = document.createElement('input'); input.id = 'voice-audio-' + name;
            input.type = 'range'; input.min = min; input.max = max; input.step = step;
            label.append(output, input); section.querySelector('.voice-audio-sliders').append(label);
            input.oninput = () => { set(voiceSelect.value, { [name]: input.value }); refresh(); };
        }
        host.append(section);
        const preset = section.querySelector('#voice-audio-preset');
        const refresh = () => {
            const voice = voiceSelect.value, enabled = valid(voice), values = get(voice);
            for (const [name, [, , , , unit]] of Object.entries(labels)) {
                const input = section.querySelector('#voice-audio-' + name);
                input.disabled = !enabled; input.value = String(values[name]);
                section.querySelector('#voice-audio-' + name + '-value').textContent = String(values[name]).replace('.', ',') + unit;
            }
            preset.disabled = !enabled;
            preset.value = enabled && !manual(voice) ? 'auto' : Object.keys(presets).find(name => Object.keys(limits).every(field => presets[name][field] === values[field])) || 'custom';
            section.querySelector('#voice-audio-reset').disabled = !enabled;
            section.querySelector('#voice-audio-note').textContent = enabled
                ? 'Se aplica al reproducir. La altura también cambia ligeramente la duración; las muestras originales permanecen intactas.'
                : 'El sonido de Windows se ajusta en su propio motor. Elige MOSS o Piper para usar estos controles.';
        };
        preset.onchange = () => { if (preset.value === 'auto') reset(voiceSelect.value); else if (presets[preset.value]) set(voiceSelect.value, presets[preset.value]); refresh(); };
        section.querySelector('#voice-audio-reset').onclick = () => { reset(voiceSelect.value); refresh(); };
        voiceSelect.addEventListener('change', refresh);
        Axx.voiceAudio.refreshPanel = refresh;
        refresh();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
    else mount();
    const style = document.createElement('style');
    style.textContent = '#view-voices #voice-audio-controls{display:grid;gap:14px;margin-top:3px;padding:18px;border:1px solid #416778;border-radius:15px;background:#102a3c}#view-voices #voice-audio-controls .voice-studio-heading{margin:0 0 3px}#view-voices .voice-audio-sliders{display:grid;gap:14px}#panel #view-voices #voice-audio-controls button{min-height:40px;border:1px solid #5b788b;border-radius:10px;background:#203e4d!important;color:#e7f6fa!important;font-weight:650}#panel #view-voices #voice-audio-controls .micro-copy{color:#b5cada!important;opacity:1}#view-voices #voice-audio-controls button:focus-visible,#view-voices #voice-audio-controls select:focus-visible,#view-voices #voice-audio-controls input:focus-visible,#view-voices .voice-phrases-toggle input:focus-visible{outline:2px solid #75e2d5;outline-offset:2px}#view-voices .voice-phrases-toggle{display:flex!important;align-items:flex-start;gap:12px;padding:14px;border:1px solid #416778;border-radius:12px;background:#102a3c}#view-voices .voice-phrases-toggle input{width:18px;height:18px;flex:none;margin:2px 0 0;accent-color:#59d0c4}#view-voices .voice-phrases-toggle span{display:grid;gap:4px}#view-voices .voice-phrases-toggle small{color:#b5cada;font-size:11px;line-height:1.45;font-weight:400}';
    document.head.append(style);
    window.addEventListener('pagehide', () => { void audioContext?.close().catch(() => {}); });
})(window.Axx = window.Axx || {});
