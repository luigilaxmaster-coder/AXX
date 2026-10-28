/* Per-voice sound color for local PCM and WAV playback; no raw audio is stored. */
(function (Axx) {
    const key = 'axx.voice.audio.v3';
    const limits = { bass: [-9, 9], presence: [-9, 9], air: [-9, 9], level: [.25, 1.5], pitch: [-3, 3] };
    const neutral = { bass: 0, presence: 0, air: 0, level: 1, pitch: 0 };
    const presets = {
        natural: neutral,
        warm: { bass: 5, presence: 0, air: -3, level: 1, pitch: -.5 },
        clear: { bass: -3, presence: 4, air: 3, level: 1, pitch: 0 },
        soft: { bass: 2, presence: -3, air: -4, level: .9, pitch: -.5 }
    };
    const personalitySound = {
        natural: neutral,
        friendly: { ...neutral, bass: 3, air: -2, pitch: -.5 },
        direct: { ...neutral, bass: -1, presence: 3, air: 2 },
        formal: { ...neutral, presence: 2, air: -1, pitch: -.5 },
        playful: { ...neutral, bass: -1, presence: 2, air: 3, pitch: 1.5 },
        psycho: { ...neutral, bass: 5, presence: -2, air: -4, pitch: -1.5 }
    };
    const personalityRate = { natural: 1, friendly: .96, direct: 1.07, formal: .94, playful: 1.06, psycho: .91 };
    let saved;
    try {
        const current = localStorage.getItem(key);
        saved = JSON.parse(current || localStorage.getItem('axx.voice.audio.v2') || localStorage.getItem('axx.voice.audio.v1') || '{}');
        if (!current) {
            const base = personalitySound[Axx.companion?.data?.prefs?.personalityStyle] || neutral;
            // shortcut: legacy values were absolute; the current personality preserves their audible value during migration.
            for (const [voice, values] of Object.entries(saved))
                saved[voice] = Object.fromEntries(Object.entries(values || {}).filter(([name, value]) =>
                    Object.hasOwn(neutral, name) && Number.isFinite(Number(value)) && Number(value) !== base[name])
                    .map(([name, value]) => [name, Number(value) - base[name]]));
            localStorage.setItem(key, JSON.stringify(saved));
        }
    } catch { saved = {}; }
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
    const chains = new Set();
    let audioContext;
    const clamp = (name, value) => {
        const number = Number(value), [min, max] = limits[name];
        return Number.isFinite(number) ? Math.round(Math.max(min, Math.min(max, number)) * 100) / 100 : neutral[name];
    };
    const valid = voice => /^(moss|piper):[a-z0-9_-]{1,70}$/i.test(voice || '');
    const personality = () => Axx.companion?.data?.prefs?.personalityStyle || 'natural';
    const manual = voice => Object.keys(saved[voice] || {}).some(name => Object.hasOwn(limits, name));
    const get = voice => Object.fromEntries(Object.keys(limits).map(name =>
        [name, clamp(name, valid(voice) ? (personalitySound[personality()]?.[name] ?? neutral[name])
            + (Number(saved[voice]?.[name]) || 0) : undefined)]));
    const apply = chain => {
        const values = get(chain.voice), now = chain.context.currentTime;
        for (const [name, node] of [['bass', chain.bass], ['presence', chain.presence], ['air', chain.air]])
            node.gain.setTargetAtTime(values[name], now, .03);
        chain.level.gain.setTargetAtTime(values.level, now, .03);
    };
    const set = (voice, patch) => {
        if (!valid(voice) || !patch || typeof patch !== 'object') return get(voice);
        const base = personalitySound[personality()] || neutral, next = { ...saved[voice] };
        for (const name of Object.keys(limits)) if (Object.hasOwn(patch, name)) {
            const offset = clamp(name, patch[name]) - base[name];
            if (Math.abs(offset) < .001) delete next[name]; else next[name] = offset;
        }
        if (Object.keys(next).length) saved[voice] = next; else delete saved[voice];
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
        bass.connect(presence).connect(air).connect(level).connect(limiter).connect(ctx.destination);
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
        refreshPersonality() { for (const active of chains) apply(active); this.refreshPanel?.(); },
        speed(voice, rate) { return Math.max(.7, Math.min(1.5, Math.max(.75, Math.min(1.3, Number(rate) || 1))
            * (personalityRate[personality()] || 1) * 2 ** (get(voice).pitch / 12))); } };
    const mount = () => {
        const host = document.getElementById('voice-panel-controls');
        const voiceSelect = document.getElementById('voice-panel-select');
        if (!host || !voiceSelect || document.getElementById('voice-audio-controls')) return;
        const section = document.createElement('section');
        section.id = 'voice-audio-controls';
        section.innerHTML = '<div class="voice-studio-heading"><strong>Sonido de la voz</strong><span>Por voz · MOSS y Piper</span></div><label>Personalidad al hablar<select id="voice-audio-personality"><option value="natural">Natural</option><option value="friendly">Cercana</option><option value="direct">Directa</option><option value="formal">Formal</option><option value="playful">Juguetona</option><option value="psycho">Psicópata · ficción +17</option></select></label><label>Perfil de sonido<select id="voice-audio-preset"><option value="auto">Según personalidad</option><option value="natural">Natural</option><option value="warm">Cálida</option><option value="clear">Clara</option><option value="soft">Suave</option><option value="custom">Personalizado</option></select></label><div class="voice-audio-sliders"></div><button id="voice-audio-reset" type="button">Usar sonido de personalidad</button><p id="voice-audio-note" class="micro-copy"></p>';
        const labels = { bass: ['Cuerpo · graves', '-9', '9', '1', ' dB'], presence: ['Claridad · medios', '-9', '9', '1', ' dB'], air: ['Brillo · agudos', '-9', '9', '1', ' dB'], pitch: ['Altura', '-3', '3', '.5', ' semitonos'], level: ['Nivel', '.25', '1.5', '.05', '×'] };
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
        const personalitySelect = section.querySelector('#voice-audio-personality');
        const refresh = () => {
            const voice = voiceSelect.value, enabled = valid(voice), values = get(voice);
            personalitySelect.value = personality();
            for (const [name, [, , , , unit]] of Object.entries(labels)) {
                const input = section.querySelector('#voice-audio-' + name);
                input.disabled = !enabled; input.value = String(values[name]);
                section.querySelector('#voice-audio-' + name + '-value').textContent = String(values[name]).replace('.', ',') + unit;
            }
            preset.disabled = !enabled;
            preset.value = enabled && !manual(voice) ? 'auto' : Object.keys(presets).find(name => Object.keys(limits).every(field => presets[name][field] === values[field])) || 'custom';
            section.querySelector('#voice-audio-reset').disabled = !enabled;
            section.querySelector('#voice-audio-note').textContent = enabled
                ? 'Pulsa Probar voz para comparar. La ecualización cambia al instante; altura y ritmo, en la próxima frase. Tus ajustes se combinan con la personalidad.'
                : 'El sonido de Windows se ajusta en su propio motor. Elige MOSS o Piper para usar estos controles.';
        };
        personalitySelect.onchange = () => {
            const chatSelect = document.getElementById('chat-personality-style');
            if (!chatSelect) return;
            chatSelect.value = personalitySelect.value;
            chatSelect.dispatchEvent(new Event('change', { bubbles: true }));
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
