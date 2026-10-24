/* Optional conversational cues while a spoken answer is pending. */
(function (Axx) {
    'use strict';
    if (!Axx) return;

    let lastFiller = '';
    const fillers = {
        es: {
            search: [
                'Déjame revisar esa pregunta.',
                'Un momento, reviso la información.',
                'Déjame pensar en eso.',
                'Voy a comprobar lo que sé.'
            ],
            action: [
                'Entendido, reviso los pasos.',
                'Déjame ver cómo hacerlo.',
                'Un momento, reviso la petición.',
                'Veamos qué hace falta.'
            ],
            analysis: [
                'A ver, déjame revisarlo.',
                'Un momento, déjame calcular eso.',
                'Déjame revisar los datos.',
                'Voy a comprobar el cálculo.'
            ],
            general: [
                'Okay, déjame ver.',
                'Te escucho, un segundo.',
                'Dame un momento.',
                'Entendido, ya te digo.'
            ]
        },
        en: {
            search: [
                'Let me review that question.',
                'One moment while I check.',
                'Let me think about that.'
            ],
            action: [
                'Got it, let me check the steps.',
                'Let me see how to do that.',
                'One moment while I review it.'
            ],
            analysis: [
                'Let me analyze that.',
                'One moment, calculating.',
                'Checking the details now.'
            ],
            general: [
                'Okay, let me see.',
                'Give me just a second.',
                'Got it, checking now.'
            ]
        }
    };

    Axx.selectConversationalFiller = function (promptText, targetLang) {
        const text = String(promptText || '').toLowerCase().trim();
        const lang = targetLang === 'en' ? 'en' : 'es';
        const bank = fillers[lang] || fillers.es;

        let category = 'general';
        if (/\b(busca|buscar|quien|quién|cual|cuál|donde|dónde|cuando|cuándo|noticias|precio|informaci[oó]n|investiga|search|who|what|where|when)\b/i.test(text)) {
            category = 'search';
        } else if (/\b(haz|crea|escribe|ejecuta|abre|pon|activa|guarda|borra|elimina|inicia|configura|make|create|write|run|open|start|set)\b/i.test(text)) {
            category = 'action';
        } else if (/\b(calcula|cuanto|cuánto|analiza|compara|por qu[eé]|explica|diferencia|calculate|analyze|compare|why|how|explain)\b/i.test(text)) {
            category = 'analysis';
        }

        const candidates = bank[category] || bank.general;
        const available = candidates.filter(f => f !== lastFiller);
        const pool = available.length ? available : candidates;
        const choice = pool[Math.floor(Math.random() * pool.length)] || candidates[0];
        lastFiller = choice;
        return choice;
    };

    let loadingState = null;

    Axx.startLoadingAudio = function () {
        if (loadingState) return;
        try {
            const audio = Axx.AudioManager?.shared;
            if (!audio?.enabled || audio.allMuted || audio.profile === 'silent' || audio.capture || document.hidden) return;
            const ctx = audio.ctx;
            if (!ctx || ctx.state !== 'running' || !audio.buses.state) return;

            const now = ctx.currentTime;
            const masterGain = ctx.createGain();
            masterGain.gain.setValueAtTime(0.0001, now);
            masterGain.gain.linearRampToValueAtTime(0.038, now + 0.35);

            // 1. Continuous harmonic hum (F3 + C4 fifth) with soft lowpass breathing sweep
            const osc1 = ctx.createOscillator();
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(174.61, now);

            const osc2 = ctx.createOscillator();
            osc2.type = 'triangle';
            osc2.frequency.setValueAtTime(261.63, now);

            const filter = ctx.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(280, now);

            const lfo = ctx.createOscillator();
            const lfoGain = ctx.createGain();
            lfo.frequency.setValueAtTime(0.55, now);
            lfoGain.gain.setValueAtTime(35, now);
            lfo.connect(lfoGain);
            lfoGain.connect(filter.frequency);

            osc1.connect(filter);
            osc2.connect(filter);
            filter.connect(masterGain);

            // 2. Subtle rhythmic computing radar pulses (soft high ping)
            const pulseOsc = ctx.createOscillator();
            pulseOsc.type = 'sine';
            pulseOsc.frequency.setValueAtTime(587.33, now);

            const pulseGain = ctx.createGain();
            pulseGain.gain.setValueAtTime(0.012, now);

            const pulseLfo = ctx.createOscillator();
            pulseLfo.type = 'sine';
            pulseLfo.frequency.setValueAtTime(2.2, now);
            const pulseLfoGain = ctx.createGain();
            pulseLfoGain.gain.setValueAtTime(0.012, now);
            pulseLfo.connect(pulseLfoGain);
            pulseLfoGain.connect(pulseGain.gain);

            pulseOsc.connect(pulseGain);
            pulseGain.connect(masterGain);

            masterGain.connect(audio.buses.state);

            osc1.start(now);
            osc2.start(now);
            lfo.start(now);
            pulseOsc.start(now);
            pulseLfo.start(now);

            loadingState = {
                ctx, masterGain,
                nodes: [osc1, osc2, lfo, lfoGain, filter, pulseOsc, pulseGain, pulseLfo, pulseLfoGain, masterGain]
            };
        } catch {
            loadingState = null;
        }
    };

    Axx.stopLoadingAudio = function () {
        if (!loadingState) return;
        const current = loadingState;
        loadingState = null;
        try {
            const { ctx, masterGain, nodes } = current;
            const now = ctx.currentTime;
            masterGain.gain.cancelScheduledValues(now);
            masterGain.gain.setTargetAtTime(0.0001, now, 0.08);
            setTimeout(() => {
                for (const node of nodes) {
                    try { if (node.stop) node.stop(); node.disconnect(); } catch {}
                }
            }, 350);
        } catch {}
    };
})(window.Axx = window.Axx || {});
