/* One capture owner in Windows. Encoded video stays on disk, outside the IPC payload. */
(() => {
    const A=window.Axx, studio=A?.capture19;
    if(!A?.isNative?.() || !studio) return;
    const el=id=>document.getElementById(id), active=new Set(['requesting','countdown','running','paused','stopping']);
    class NativeCapture {
        state='ready';error='';blob=null;url='';saved=false;bytes=0;source='';settings={};mime='video/mp4';
        sourceAudioIncluded=false;microphoneIncluded=false;audioIncluded=false;countdownLeft=0;id='';file='';region=null;elapsedMs=0;
        clock={elapsed:()=>this.elapsedMs};generation=0;busy=false;backendReady=false;pendingStop=false;selecting=false;polling=false;haloKey='';haloChain=Promise.resolve();
        get active(){return active.has(this.state);}
        get available(){return true;}
        changed(){A.actions.sync();this.paint();A.resident?.schedule();}
        accept(s){
            if(!s || !['ready','requesting','countdown','running','paused','stopping','finished','error'].includes(s.state))return;
            this.backendReady=true;
            this.state=s.state;this.id=s.id||'';this.error=s.error||'';this.region=s.region;this.file=s.path||'';this.bytes=s.bytes||0;this.elapsedMs=s.elapsedMs||0;this.countdownLeft=s.countdownLeft||0;this.saved=s.verified===true;
            this.settings={...s.region,frameRate:s.fps};this.source=s.region?`Área ${s.region.width} × ${s.region.height} · (${s.region.x}, ${s.region.y})`:'';
            this.changed();this.halo();
        }
        halo(){
            const phase=['countdown','running','paused','stopping'].includes(this.state)&&studio.prefs.halo?this.state:'closed';
            const key=JSON.stringify([phase,this.region]);if(key===this.haloKey)return;this.haloKey=key;
            const region=this.region;
            this.haloChain=this.haloChain.catch(()=>{}).then(()=>A.nativeInvoke('capture_halo',{phase,region})).catch(e=>{if(this.haloKey===key)this.haloKey='';this.error=String(e.message||e);this.changed();});
        }
        async start(_audio,options={}){
            if(this.active||this.busy)return;
            if(!this.backendReady){this.error='El grabador se está preparando. Espera unos segundos.';this.changed();return;}
            const token=++this.generation;this.error='';this.state='requesting';this.selecting=true;this.changed();
            try{
                const region=await A.nativeInvoke('capture_select',{});
                if(token!==this.generation)return;
                if(!region){this.state=this.file?'finished':'ready';this.changed();return;}
                // The boundary must exist before recording begins.
                await A.nativeInvoke('capture_halo',{region,phase:'countdown'});
                if(token!==this.generation){this.haloKey='';this.halo();return;}
                const data=await A.backendRequest('POST','/axx-api/screen/start',{region,fps:options.fps||30,quality:options.quality||'balanced',countdown:options.countdown??3,maxMinutes:options.maxMinutes||15});
                if(token!==this.generation){await A.backendRequest('POST','/axx-api/screen/control',{id:data.id,command:'stop'});this.haloKey='';this.halo();return;}
                this.accept(data);
            }catch(e){if(token===this.generation){this.state='error';this.error=String(e.message||e);this.changed();this.haloKey='';this.halo();}}
            finally{if(token===this.generation)this.selecting=false;}
        }
        async toggle(){if(!['running','paused'].includes(this.state)||this.busy)return;await this.control(this.state==='paused'?'resume':'pause');}
        async control(command){
            if(this.busy){if(command==='stop')this.pendingStop=true;return;}if(!this.id)return;
            this.busy=true;this.paint();
            try{this.accept(await A.backendRequest('POST','/axx-api/screen/control',{id:this.id,command}));}
            catch(e){this.error=String(e.message||e);this.changed();}
            finally{this.busy=false;this.paint();if(this.pendingStop){this.pendingStop=false;void this.stop();}}
        }
        async stop(){
            if(this.selecting){++this.generation;this.selecting=false;this.state=this.file?'finished':'ready';await A.nativeInvoke('capture_cancel_selection',{}).catch(()=>{});this.changed();this.haloKey='';this.halo();return;}
            if(this.active&&this.state!=='stopping')await this.control('stop');
        }
        async open(folder=false){try{await A.backendRequest('POST','/axx-api/screen/open',{id:this.id,folder});}catch(e){this.error=String(e.message||e);this.changed();}}
        download(){void this.open();}
        markSaved(){}
        dispose(){void this.stop();}
        async refresh(){
            if(this.selecting||this.polling||this.busy)return;
            this.polling=true;
            try{const s=await A.backendRequest('GET','/axx-api/screen/status');if(!this.selecting)this.accept(s);}
            catch(e){if(this.active){this.error='No se pudo consultar la grabación. '+String(e.message||e);this.changed();}}
            finally{this.polling=false;}
        }
        paint(){
            const button=(id,icon,label)=>{const b=el(id);const markup=icon==='record'?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/></svg>':icon==='stop'?'<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>':A.mi(icon);if(b.innerHTML!==markup)b.innerHTML=markup;b.title=label;b.setAttribute('aria-label',label);};
            button('a11-record-start','record','Seleccionar área y grabar');button('a11-record-pause',this.state==='paused'?'play':'pause',this.state==='paused'?'Continuar':'Pausar');button('a11-record-stop','stop',this.selecting?'Cancelar selección':'Finalizar y guardar');
            el('a11-record-start').hidden=this.active;el('a11-record-start').disabled=this.busy||!this.backendReady;
            el('a11-record-pause').disabled=this.busy;el('a11-record-stop').disabled=this.busy||this.state==='stopping';
            el('r19-native-result').hidden=!this.saved||this.state!=='finished';
            el('r19-native-path').textContent=this.file;
            el('r19-native-open').disabled=!this.saved;el('r19-native-folder').disabled=!this.saved;
            el('a11-record-error').textContent=this.error;
            if(this.state==='finished')el('a11-action-verb').textContent='Abrir vídeo';
            el('r19-source').textContent=this.source||'Selecciona un área directamente sobre el escritorio';
            el('r19-audio-status').textContent='Área · vídeo sin audio';
        }
    }
    const capture=new NativeCapture();A.actions.screen=capture;A.nativeCapture=capture;
    const oldSync=studio.sync.bind(studio);studio.sync=()=>{oldSync();capture.paint();};
    studio.save=()=>capture.open();A.actions.screenSave19=()=>capture.open();
    studio.layout=()=>A.resident?.schedule();
    studio.drawHalo=()=>{el('r19-halo').hidden=true;el('r19-demo-badge').hidden=true;};
    studio.prefs.audio=false;studio.prefs.options.microphone=false;studio.prefs.halo=true;
    el('r19-show-halo').checked=true;
    el('a11-screen-audio').checked=false;el('r19-microphone').checked=false;
    el('a11-screen-audio').closest('.r19-audio').hidden=true;
    el('r19-quality').previousSibling.textContent='Compresión del vídeo';
    el('r19-quality').closest('details').querySelector('summary').textContent='Calidad y cuenta previa';
    for(const [value,label] of [['light','Ligera'],['balanced','Equilibrada'],['detail','Máximo detalle']])el('r19-quality').querySelector(`[value="${value}"]`).textContent=label;
    el('r19-name').closest('details').hidden=true;
    el('r19-demo').closest('details').hidden=true;
    el('r19-mark').closest('details').hidden=true;
    el('view-screen').querySelector('.s19-lead').innerHTML='<h3>Graba un área de tu escritorio.</h3><p>Arrastra para seleccionarla. El halo marcará el borde; toca Axx para pausar o continuar.</p>';
    el('view-screen').querySelector('.r19-limit-copy').textContent='MP4 guardado automáticamente en Axx/artifacts/recordings. Hasta 30 minutos activos o 4 GB. Esta modalidad no graba audio.';
    const result=document.createElement('section');result.id='r19-native-result';result.className='s19-card';result.hidden=true;
    result.innerHTML='<strong>Vídeo guardado</strong><p id="r19-native-path"></p><div class="s19-primary-row"><button id="r19-native-open" title="Abrir vídeo" aria-label="Abrir vídeo">'+A.mi('play')+'</button><button id="r19-native-folder" title="Abrir carpeta" aria-label="Abrir carpeta">'+A.mi('list')+'</button></div>';
    el('r19-compact').before(result);el('r19-native-open').onclick=()=>capture.open();el('r19-native-folder').onclick=()=>capture.open(true);
    const style=document.createElement('style');style.textContent='#view-screen [hidden]{display:none!important}#view-screen .s19-lead{margin-bottom:12px}#view-screen .s19-lead h3{font-size:22px!important}#view-screen .r19-time{font-size:28px}#view-screen .a11-record-controls button{min-width:50px;min-height:48px}#view-screen .a11-record-controls svg,#r19-native-result svg{width:22px;height:22px}#r19-native-path{overflow-wrap:anywhere;font-size:12px;color:#a8c7dd}';document.head.append(style);
    capture.changed();
    let closed=false,timer;const poll=async()=>{await capture.refresh();if(!closed)timer=setTimeout(poll,capture.active?350:1500);};void poll();
    addEventListener('pagehide',()=>{closed=true;clearTimeout(timer);void A.nativeInvoke('capture_cancel_selection',{}).catch(()=>{});});
})();
