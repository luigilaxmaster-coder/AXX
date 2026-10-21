/* Windows is the source of truth: no optimistic playback or invented audio spectrum. */
(() => {
    const A = window.Axx, hub = A?.media16;
    if (!hub) return;
    const el = id => document.getElementById(id);
    if (!A.isNative()) { el('m16-system-info').textContent = 'Abre Axx para Windows para controlar el sonido del equipo.'; return; }
    class NativeMusic {
        snapshot = { sessions: [], peak: 0, updatedAt: 0 };
        selectedId = '';
        automaticId = '';
        controlledId = '';
        pending = false;
        polling = false;
        level = 0;
        error = '';
        readError = '';
        lastList = '';
        envelope = { bass: 0, mid: 0, high: 0, level: 0, pulse: 0, bars: new Float32Array(44) };
        constructor() {
            el('m16-system-sessions').onchange = e => {
                this.selectedId = e.target.value; this.controlledId = ''; this.error = ''; this.paint();
            };
            const sync = hub.sync.bind(hub);
            hub.sync = () => { sync(); if (hub.source === 'system') this.decorate(); };
            const tick = async () => {
                await this.refresh();
                if (!this.closed) this.timer = setTimeout(tick, hub.source === 'system' && A.actions.selected === 'music' ? 120 : 1000);
            };
            hub.choose('system'); void tick();
            window.addEventListener('pagehide', () => { this.closed = true; clearTimeout(this.timer); });
        }
        target() {
            const list = this.snapshot.sessions || [];
            if (this.selectedId) return list.find(s => s.id === this.selectedId);
            // Retain the paused session so a second touch resumes the same playback.
            const previous = list.find(s => s.id === this.automaticId);
            const chosen = list.find(s => s.id === this.controlledId) || list.find(s => s.playing && s.id === this.snapshot.currentId) || list.find(s => s.playing) || previous || list.find(s => s.id === this.snapshot.currentId) || list[0];
            this.automaticId = chosen?.id || '';
            return chosen;
        }
        async refresh() {
            if (this.polling || this.closed) return;
            this.polling = true;
            try {
                const s = await A.nativeInvoke('system_media_status', {});
                if (!s || !Array.isArray(s.sessions)) throw Error('No se pudo consultar el audio de Windows.');
                this.snapshot = s; this.readError = s.error || '';
            } catch (e) { this.readError = String(e.message || e); this.snapshot = {sessions:[],peak:0,updatedAt:0}; }
            finally { this.polling = false; this.paint(); }
        }
        paint() {
            if (hub.source !== 'system') return;
            const t = this.target(), fresh = Date.now() - this.snapshot.updatedAt < 2500;
            hub.pending = this.pending;
            hub.state = A.cleanMedia16(t && fresh ? {...t, connected:true,updatedAt:Date.now()} : {}, 'system');
            hub.notice = this.error || this.readError;
            A.actions.sync();
        }
        decorate() {
            const t = this.target(), list = this.snapshot.sessions || [];
            const key = JSON.stringify(list.map(s => [s.id,s.title,s.app,s.playing])) + this.selectedId;
            const select = el('m16-system-sessions');
            if (key !== this.lastList) {
                this.lastList = key;
                select.replaceChildren(new Option('Automático' + (t && !this.selectedId ? ' · ' + (t.title || t.app) : ''), ''));
                for (const s of list) select.add(new Option(`${s.playing ? '▶ ' : ''}${s.title || 'Sin título'} · ${s.app}`, s.id));
                if (this.selectedId && !list.some(s => s.id === this.selectedId)) select.add(new Option('El reproductor seleccionado se cerró', this.selectedId));
                select.value = this.selectedId;
            }
            select.disabled = this.pending;
            const audible = this.snapshot.peak > .002;
            el('m16-system-info').textContent = this.error || this.readError || (t ? `Toca Axx para ${t.playing ? 'pausar' : 'continuar'} este reproductor.` + (list.filter(s=>s.playing).length > 1 ? ' Hay varias aplicaciones reproduciendo; selecciona cuál controlar.' : '') : this.selectedId ? 'Ese reproductor ya no está disponible. Elige otro o Automático.' : audible ? 'Sonido detectado. Esta aplicación no publica controles de pausa en Windows.' : 'Abre un vídeo, música o un reproductor. Axx lo detectará automáticamente.') + (this.snapshot.audioAvailable ? '' : ' No hay salida de audio disponible.');
            el('m16-system-level').value = Math.max(0, Math.min(1, this.snapshot.peak || 0));
            el('m16-no-spectrum').textContent = audible ? 'Sonido del equipo detectado · nivel real' : 'Esperando sonido del equipo';
            const enabled = !!t && (t.playing ? t.canPause : t.canPlay) && Date.now() - this.snapshot.updatedAt < 2500 && !this.pending;
            for (const id of ['m16-play','a11-main-button','m15-compact-play']) el(id).disabled = !enabled;
            el('m16-source-status').textContent = t ? 'Windows · conectado' : audible ? 'Windows · sonido detectado' : 'Windows · esperando';
            if (A.actions.selected === 'music') {
                el('a11-action-name').textContent = t?.title || 'Sonido del equipo';
                el('a11-action-detail').textContent = t?.app || 'Esperando un reproductor compatible';
                el('a11-action-verb').textContent = this.pending ? 'Aplicando…' : !t ? 'Esperando reproducción' : t.playing ? 'Pausar' : 'Continuar';
            }
        }
        async toggle() {
            const t = this.target();
            if (!t) { A.actions.open('music'); return; }
            await this.command(t.playing ? 'pause' : 'play');
        }
        async command(command, value) {
            if (this.pending) return;
            const t = this.target(), cap = {play:'canPlay',pause:'canPause',next:'canNext',previous:'canPrevious',seek:'canSeek'}[command];
            if (!t || !t[cap] || Date.now() - this.snapshot.updatedAt > 2500) { this.error = 'Este reproductor no permite ese control ahora.'; this.paint(); return; }
            this.pending = true; this.error = ''; this.paint();
            const id = t.id;
            this.controlledId = id;
            try {
                const ok = await A.nativeInvoke('system_media_control', {id,command,value:value ?? null});
                if (ok !== true) throw Error('El reproductor no aceptó el control.');
                // Read the actual postcondition; the acknowledgement alone is not a playback state.
                for (let i=0;i<8;i++) {
                    await new Promise(r=>setTimeout(r,140)); await this.refresh();
                    const current = this.snapshot.sessions.find(s=>s.id===id);
                    if (!['play','pause'].includes(command) || !current || current.playing === (command==='play')) break;
                    if(i===7) this.error = 'Windows recibió la orden, pero el reproductor aún no cambió de estado.';
                }
            } catch(e) { this.error = String(e.message || e); }
            finally { this.pending = false; this.paint(); }
        }
        signal(dt) {
            const target = Date.now() - this.snapshot.updatedAt < 1500 ? Math.max(0,Math.min(1,this.snapshot.peak || 0)) : 0;
            this.level += (target-this.level)*(1-Math.exp(-Math.min(.1,Math.max(.001,dt))/(target > this.level ? .05 : .22)));
            const s=this.envelope; s.level=this.level; s.bass=s.mid=s.high=this.level; s.pulse=0; s.bars.fill(this.level);
            return s;
        }
    }
    A.nativeMusic = new NativeMusic();
})();
