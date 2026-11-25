/* Easter egg «Modo ritmo»: ↑ ↑ ↓ ↓ ← → ← → B A makes AXX move to the music playing on Windows.
 * Input: the output peak meter Windows already reports (system_media_status). No audio is captured or recorded.
 * BeatTracker turns that ~20 Hz level into onsets, a tempo and a phase-locked beat grid, so the avatar lands on the
 * beat between samples. The renderer keeps the avatar still under reduced motion or static mode. */
(() => {
    'use strict';
    const A = window.Axx;
    if (!A) return;

    class BeatTracker {
        constructor() { this.reset(); }
        reset() {
            this.env = 0; this.prev = 0; this.fluxMean = 0; this.fluxVar = 0; this.lastT = null; this.firstT = null;
            this.onsets = []; this.lastOnset = -1e12; this.lastInstantAt = -1e12; this.period = 0; this.bpm = 0; this.confidence = 0;
            this.nextBeat = 0; this.lastBeat = -1e12; this.beats = 0;
        }
        /** One measured output peak (0..1) at time t (ms). Returns true when it is an onset. */
        sample(peak, t) {
            const dt = this.lastT === null ? 50 : Math.min(250, Math.max(1, t - this.lastT));
            this.lastT = t;
            this.firstT ??= t;
            const level = Math.max(0, Math.min(1, Number(peak) || 0));
            this.env += (level - this.env) * (1 - Math.exp(-dt / (level > this.env ? 12 : 90)));  // fast attack, slow release
            const flux = Math.max(0, this.env - this.prev);
            this.prev = this.env;
            const k = 1 - Math.exp(-dt / 1500), dev = flux - this.fluxMean;
            this.fluxMean += dev * k;
            this.fluxVar += (dev * dev - this.fluxVar) * k;
            const onset = t - this.firstT > 400 && this.env > .018 &&  // warm-up: the jump from 0 to the bed level is not a beat
                 flux > this.fluxMean + 1.5 * Math.sqrt(this.fluxVar) + .006 && t - this.lastOnset > 220;
            if (onset) {
                this.lastOnset = t;
                this.lastInstantAt = t;
                this.onsets.push(t);
                while (t - this.onsets[0] > 8000) this.onsets.shift();
                this.tempo();
                this.lock(t);
            }
            return onset;
        }
        /** Tempo = the 60–180 BPM grid the onsets fit best: phase coherence (half tempo scores ~0) times the share of
         *  grid beats that really have an onset (double tempo scores ~0.5). */
        tempo() {
            const o = this.onsets;
            if (o.length < 6) return;  // ~3 s of music: fewer onsets give a wrong first tempo
            let bestBpm = 0, score = 0;
            for (let bpm = 60; bpm <= 180; bpm += .5) {
                const P = 60000 / bpm;
                let c = 0, s = 0;
                for (const t of o) { const a = 2 * Math.PI * (t % P) / P; c += Math.cos(a); s += Math.sin(a); }
                const coherence = Math.hypot(c, s) / o.length, offset = (Math.atan2(s, c) / (2 * Math.PI)) * P, tol = Math.max(60, P * .2);
                let hit = 0, total = 0;
                for (let g = Math.ceil((o[0] - offset - tol) / P) * P + offset; g <= o.at(-1) + tol; g += P) {
                    total++;
                    if (o.some(t => Math.abs(t - g) < tol)) hit++;
                }
                const fit = coherence * (total ? hit / total : 0);
                if (fit > score + 1e-9) { score = fit; bestBpm = bpm; }
            }
            if (!bestBpm) return;
            this.confidence = score;
            let period = 60000 / bestBpm;
            // Least squares on the onsets that sit on that grid: averages out the meter's 50 ms sampling.
            const fit = o.map(t => [Math.round((t - o[0]) / period), t]).filter(([k, t]) => Math.abs(t - o[0] - k * period) < period * .25);
            if (fit.length >= 4 && fit.at(-1)[0] > 0) {
                const n = fit.length, mk = fit.reduce((a, [k]) => a + k, 0) / n, mt = fit.reduce((a, [, t]) => a + t, 0) / n;
                const slope = fit.reduce((a, [k, t]) => a + (k - mk) * (t - mt), 0) / fit.reduce((a, [k]) => a + (k - mk) ** 2, 0);
                if (Math.abs(slope / period - 1) < .08) period = slope;
            }
            this.period = period;
            this.bpm = 60000 / period;
        }
        /** Phase-locked loop: nudge the predicted beat grid toward each onset that falls near it. */
        lock(t) {
            if (!this.period) return;
            if (!this.nextBeat || t - this.lastBeat > this.period * 3) { this.nextBeat = t; return; }
            let err = t - this.nextBeat;
            err -= Math.round(err / this.period) * this.period;
            if (Math.abs(err) < this.period * .3) this.nextBeat += err * .35;
        }
        /** Frame time t (ms): advance the beat grid and return what the avatar should do now. */
        frame(t) {
            const live = t - this.lastOnset < 3000 && this.env > .018, locked = live && this.confidence > .5 && this.period > 0;
            if (this.period && this.nextBeat)
                while (t >= this.nextBeat) { this.lastBeat = this.nextBeat; this.nextBeat += this.period; if (locked) this.beats++; }
            const since = t - this.lastBeat;
            const instant = live ? Math.exp(-Math.max(0, t - this.lastInstantAt) / 110) : 0;
            return {level: this.env, locked, bpm: locked ? Math.round(this.bpm) : 0, confidence: this.confidence,
                pulse: locked ? Math.exp(-Math.max(0, since) / 140) : 0, instant,
                phase: locked ? (since % this.period) / this.period : 0};
        }
    }
    A.BeatTracker = BeatTracker;
    if (!A.isNative?.() || typeof document === 'undefined') return;

    const CODE = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
    const AMOUNTS = [['Normal', .95], ['Intenso', 1.35], ['Suave', .6]];
    const signal = {bass: 0, mid: 0, high: 0, level: 0, pulse: 0, bars: new Float32Array(44)};
    let progress = 0, active = false, tracker = null, raf = 0, polling = false, lastSampleAt = 0, quietSince = 0, trackTitle = '', amountIndex = 0, chip = null, bpmEl = null, trackEl = null, intensityBtn = null, renderer = null, setMusic = null, ownSetter = null;
    const still = () => { const s = A.app?.store?.data?.settings || {}; return s.reducedMotion || s.staticMode || matchMedia('(prefers-reduced-motion: reduce)').matches; };
    const toast = (text, ms) => A.app?.toast?.(text, ms);

    async function poll() {
        if (polling || !active || document.hidden) return;
        polling = true;
        try {
            const s = await A.nativeInvoke('system_media_status', {});
            if (s && Number.isFinite(s.updatedAt) && s.updatedAt !== lastSampleAt) {  // Windows refreshes the meter every 50 ms
                lastSampleAt = s.updatedAt;
                tracker.sample(s.peak, s.updatedAt);
            }
            const playing = Array.isArray(s?.sessions) ? (s.sessions.find(x => x?.playing && (x.title || x.app)) || null) : null;
            trackTitle = playing ? String(playing.title || playing.app).trim().slice(0, 32) : '';
        } catch { /* the meter is optional: no sound simply means no beat */ }
        finally { polling = false; }
    }
    function frame() {
        if (!active) return;
        raf = requestAnimationFrame(frame);
        const now = Date.now(), beat = tracker.frame(now);
        if (beat.level > .018) quietSince = now;
        else if (now - quietSince > 120000) { stop('Modo ritmo en pausa: no suena nada desde hace 2 minutos.'); return; }
        const kick = beat.locked ? beat.pulse : beat.instant * .72;
        const wave = .6 + .4 * Math.cos(beat.phase * Math.PI * 2);
        const harmonic = .5 + .5 * Math.sin(beat.phase * Math.PI * 4);
        signal.level = Math.min(1, beat.level * 1.25);
        signal.bass = Math.min(1, beat.level * .85 + kick * .6);
        signal.mid = Math.min(1, beat.level * .72 * wave + kick * .15);
        signal.high = Math.min(1, beat.level * .38 * harmonic + kick * .2);
        signal.pulse = kick;
        for (let i = 0; i < signal.bars.length; i++) {
            const norm = i / (signal.bars.length - 1);
            const band = (1 - norm) * signal.bass + Math.sin(norm * Math.PI) * signal.mid * .75 + norm * signal.high * .7;
            signal.bars[i] = Math.min(1, band);
        }
        setMusic(signal, AMOUNTS[amountIndex][1]);
        chip.dataset.beat = String(kick > .55);
        bpmEl.textContent = beat.locked ? beat.bpm + ' BPM' : beat.level > .018 ? 'buscando el ritmo…' : 'esperando música…';
        trackEl.hidden = !trackTitle;
        if (trackTitle) trackEl.textContent = trackTitle;
    }
    function start() {
        if (active) return;
        renderer = A.app?.renderer;
        if (!renderer?.setMusicSignal) return;
        if (still()) { toast('Modo ritmo: AXX no se mueve con «Movimiento reducido» o «Superficie estática» activos.', 6000); return; }
        active = true; tracker = new BeatTracker(); lastSampleAt = 0; quietSince = Date.now(); trackTitle = ''; amountIndex = 0;
        ownSetter = Object.prototype.hasOwnProperty.call(renderer, 'setMusicSignal') ? renderer.setMusicSignal : null;
        setMusic = renderer.setMusicSignal.bind(renderer);
        renderer.setMusicSignal = () => {};  // while dancing, the music panel's per-frame reset must not cancel the egg
        chip = Object.assign(document.createElement('div'), {className: 'axx-groove', role: 'region', ariaLabel: 'Modo ritmo'});
        const note = Object.assign(document.createElement('span'), {textContent: '♪'});
        note.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.textContent = 'Modo ritmo · ';
        bpmEl = document.createElement('b');
        bpmEl.textContent = 'esperando música…';
        trackEl = Object.assign(document.createElement('small'), {className: 'axx-groove-track', hidden: true});
        intensityBtn = Object.assign(document.createElement('button'), {type: 'button', className: 'axx-groove-btn',
            ariaLabel: 'Intensidad del ritmo', title: 'Cambiar intensidad de movimiento', textContent: AMOUNTS[amountIndex][0],
            onclick: () => { amountIndex = (amountIndex + 1) % AMOUNTS.length; intensityBtn.textContent = AMOUNTS[amountIndex][0]; }});
        const closeBtn = Object.assign(document.createElement('button'), {type: 'button', className: 'axx-groove-btn axx-groove-close',
            ariaLabel: 'Salir del modo ritmo', title: 'Salir del modo ritmo (Esc)', textContent: '×', onclick: () => stop()});
        chip.append(note, label, bpmEl, trackEl, intensityBtn, closeBtn);
        document.body.append(chip);
        A.rhythmEgg.timer = setInterval(poll, 40);
        raf = requestAnimationFrame(frame);
        toast('🎵 Modo ritmo: AXX sigue la música que suena en Windows. Esc para salir.', 5000);
    }
    function stop(message = 'Modo ritmo desactivado.') {
        if (!active) return;
        active = false;
        cancelAnimationFrame(raf); clearInterval(A.rhythmEgg.timer);
        if (ownSetter) renderer.setMusicSignal = ownSetter; else delete renderer.setMusicSignal;  // the music panel drives it again
        renderer.setMusicSignal(null);
        chip?.remove(); chip = bpmEl = trackEl = intensityBtn = null;
        if (message) toast(message, 3500);
    }
    addEventListener('visibilitychange', () => { if (active && !document.hidden) lastSampleAt = 0; });
    addEventListener('keydown', e => {
        const t = e.target;
        if (t?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t?.tagName || '')) return;
        if (active && e.key === 'Escape') { stop(); return; }
        const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
        progress = key === CODE[progress] ? progress + 1 : key === CODE[0] ? 1 : 0;
        if (progress === CODE.length) { progress = 0; active ? stop() : start(); }
    });
    addEventListener('pagehide', () => stop(''));
    const style = document.createElement('style');
    style.textContent = `.axx-groove{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:2147483000;display:flex;align-items:center;gap:6px;
      padding:5px 10px 5px 14px;border-radius:999px;border:1px solid #fff3;background:#0b1220d9;color:#e8f1ff;font:600 12px/1.2 "Segoe UI",sans-serif;
      box-shadow:0 6px 22px #0006;transition:box-shadow .12s,transform .12s;max-width:calc(100vw - 32px)}
      .axx-groove b{font-weight:700}.axx-groove > span:first-child{display:inline-block;transition:transform .12s}
      .axx-groove-track{opacity:.78;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .axx-groove-btn{border:1px solid #fff3;background:#ffffff14;color:inherit;border-radius:999px;padding:2px 8px;font:600 11px/1.3 "Segoe UI",sans-serif;cursor:pointer}
      .axx-groove-btn:hover{background:#ffffff29}.axx-groove-close{padding:2px 7px;font-size:13px}
      .axx-groove[data-beat=true]{box-shadow:0 0 0 3px #9274ffaa,0 6px 22px #0006}.axx-groove[data-beat=true] > span:first-child{transform:scale(1.45) rotate(-12deg)}
      @media (prefers-reduced-motion:reduce){.axx-groove,.axx-groove > span:first-child{transition:none}}`;
    document.head.append(style);
    A.rhythmEgg = {start, stop, get active() { return active; }, get tracker() { return tracker; }, timer: 0};
})();
