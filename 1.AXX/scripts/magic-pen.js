/* Desktop ink uses the resident surface; clean snapshots remain immutable evidence. */
(() => {
    'use strict';
    const A = window.Axx, $ = id => document.getElementById(id);
    const api = (op, body = {}) => A.backendRequest('POST', '/axx-api/pen/' + op, body);
    const clone = value => structuredClone(value);
    function sourcePoint(x, y, rect, width, height) {
        if (![x,y,rect.left,rect.top,rect.width,rect.height,width,height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) throw Error('Transformación inválida.');
        const p = [(x-rect.left)*width/rect.width, (y-rect.top)*height/rect.height];
        if (p[0]<0 || p[1]<0 || p[0]>=width || p[1]>=height) throw Error('Fuera de la imagen.');
        return p;
    }
    function desktopPoint(x, y, viewport, source) {
        if (![x,y,viewport.x,viewport.y,viewport.scale,source.x,source.y].every(Number.isFinite) || viewport.scale <= 0) throw Error('Geometría de escritorio no disponible.');
        const p = [viewport.x + x * viewport.scale - source.x, viewport.y + y * viewport.scale - source.y];
        if (p[0]<0 || p[1]<0 || p[0]>=source.width || p[1]>=source.height) throw Error('Fuera de la pantalla activa.');
        return p;
    }
    class MagicPen {
        active = false; state = 'closed'; doc = null; image = null; gesture = null; pendingLasso = null;
        undoStack = []; redoStack = []; saveChain = Promise.resolve(); saveError = null; generation = 0; working = false; queries = new Set(); sessionChain = Promise.resolve();
        constructor() {
            const view = document.createElement('section'); view.id = 'view-magicpen'; view.className = 'panel-view'; view.hidden = true;
            const icons = {
                rect:'<rect x="4" y="4" width="16" height="16" rx="3" stroke-dasharray="3 3"/>',
                point:'<circle cx="12" cy="12" r="6"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',
                lasso:'<path d="M8 19c-4-1-6-4-5-8S9 4 15 5s8 6 4 10c-2 2-7 4-10 3s-2-4 0-4 3 4 1 7"/>',
                pen:'<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-4L4 15z"/>',
                marker:'<path d="m14 3 7 7-9 9-7-7zM6 13l-3 6 2 2 6-3M3 22h11"/>',
                erase:'<path d="m14 3 7 7-11 11H6l-4-4zM7 12l7 7M10 21h11"/>',
                pointer:'<path d="m5 3 15 10-8 1-3 8z"/>',
                capture:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="12" cy="12" r="4"/>',
                undo:'<path d="m7 4-4 4 4 4M3 8h11a6 6 0 0 1 0 12h-3"/>',
                redo:'<path d="m17 4 4 4-4 4m4-4H10a6 6 0 0 0 0 12h3"/>',
                mic:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
                send:'<path d="M12 20V4m-7 7 7-7 7 7"/>',
                save:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>'
            };
            const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
            this.icon = icon;
            const tool = (id,label) => `<button class="mp-icon-button" data-mp-tool="${id}" title="${label}" aria-label="${label}" aria-pressed="false">${icon(id)}</button>`;
            view.innerHTML = `<div class="mp-source-row"><div class="mp-source-label"><span class="mp-dot"></span><select id="mp-source" aria-label="Pantalla de origen"></select></div><button id="mp-capture">${icon('capture')}<span>Capturar</span></button></div>
                <div class="mp-modebar" role="group" aria-label="Modo de Magic Pen"><button data-mp-mode="select" aria-pressed="true">${icon('rect')}Seleccionar</button><button data-mp-mode="ink" aria-pressed="false">${icon('pen')}Anotar</button><button data-mp-mode="pointer" aria-pressed="false">${icon('pointer')}Señalar</button></div>
                <select id="mp-tool" hidden aria-label="Modo de Magic Pen"><option value="rect">Rectángulo</option><option value="point">Punto y contexto</option><option value="lasso">Lazo</option><option value="pen">Pluma</option><option value="marker">Marcador</option><option value="erase">Borrar trazo</option><option value="pointer">Señalar temporalmente</option></select>
                <div class="mp-toolstrip"><div id="mp-select-tools" class="mp-toolgroup">${tool('rect','Rectángulo')}${tool('point','Punto y contexto')}${tool('lasso','Lazo')}</div><div id="mp-ink-tools" class="mp-toolgroup" hidden>${tool('pen','Pluma')}${tool('marker','Marcador')}${tool('erase','Borrar trazo')}<span class="mp-divider"></span><input id="mp-color" type="color" value="#b8aaff" aria-label="Color de tinta"><input id="mp-width" type="range" min="1" max="40" value="4" aria-label="Grosor de tinta"></div><span id="mp-tool-hint">Arrastra para seleccionar</span><div class="mp-history-tools"><button id="mp-undo" class="mp-icon-button" title="Deshacer tinta" aria-label="Deshacer tinta">${icon('undo')}</button><button id="mp-redo" class="mp-icon-button" title="Rehacer tinta" aria-label="Rehacer tinta">${icon('redo')}</button></div></div>
                <div class="mp-stage"><div id="mp-viewport"><canvas id="mp-canvas" tabindex="0" aria-label="Captura congelada: selecciona o anota; Escape para salir"></canvas><div id="mp-empty">${icon('capture')}<strong>Todo empieza con una captura.</strong><span>Selecciona un detalle. Pregunta. Deja una nota.</span></div></div><div class="mp-stage-footer"><span id="mp-meta">Sin captura</span><label>Zoom <select id="mp-zoom"><option value="1">Ajustar</option><option value="2">200%</option><option value="4">400%</option></select></label></div></div>
                <div class="mp-selection-row"><details><summary>Ajustar selección</summary><div class="mp-row">${['x0','y0','x1','y1'].map(k=>`<label>${k}<input id="mp-${k}" type="number" min="0" step="1"></label>`).join('')}<button id="mp-adjust">Aplicar</button></div><small>Coordenadas del original. Aplicar crea un rectángulo.</small></details><button id="mp-close-lasso" hidden>Cerrar lazo</button></div>
                <div class="mp-composer"><input id="mp-question" type="text" maxlength="4000" placeholder="¿Qué quieres saber de esta selección?" aria-label="Pregunta sobre la selección"><button id="mp-voice" class="mp-icon-button" title="Dictar pregunta" aria-label="Dictar pregunta">${icon('mic')}</button><button id="mp-ask" class="mp-icon-button" title="Preguntar" aria-label="Preguntar">${icon('send')}</button></div>
                <p id="mp-status" role="status" aria-live="polite">Elige una pantalla y pulsa Capturar.</p><div id="mp-answers" aria-live="polite"></div>
                <details class="mp-save-section"><summary>${icon('save')}Guardar e historial<span>PNG + tinta editable</span></summary><label>Carpeta de destino<input id="mp-directory" type="text"></label><label>Nombre<input id="mp-name" type="text" value="Captura-Axx" maxlength="100"></label><div class="mp-row"><button id="mp-original">Guardar original</button><button id="mp-annotated">Guardar anotado</button><button id="mp-retry">Guardar borrador</button></div><p id="mp-export" role="status"></p><label>Capturas anteriores<select id="mp-history"><option value="">Elige una captura</option></select></label></details><p id="mp-capability" class="mp-muted"></p>`;
            document.body.append(view); this.view = view; this.canvas = $('mp-canvas'); this.ctx = this.canvas.getContext('2d');
            this.mountDesktop();
            const style = document.createElement('link'); style.rel='stylesheet';style.href='scripts/magic-pen.css';document.head.append(style);
            $('mp-capture').onclick = () => this.run(()=>this.capture());
            $('mp-ask').onclick = () => this.ask();
            $('mp-question').onkeydown = e => { if(e.key==='Enter') {e.stopPropagation();this.ask();} };
            $('mp-original').onclick = () => this.run(()=>this.export('original'));
            $('mp-annotated').onclick = () => this.run(()=>this.export('annotated'));
            $('mp-retry').onclick = () => this.run(async()=>{this.saveError=null;this.queueSave();await this.flush();this.status('Borrador guardado.');});
            $('mp-history').onchange = () => this.run(()=>this.restore($('mp-history').value));
            $('mp-tool').onchange = () => this.chooseTool($('mp-tool').value);
            view.querySelectorAll('[data-mp-tool]').forEach(b=>b.onclick=()=>this.chooseTool(b.dataset.mpTool));
            view.querySelectorAll('[data-mp-mode]').forEach(b=>b.onclick=()=>this.chooseTool({select:'rect',ink:'pen',pointer:'pointer'}[b.dataset.mpMode]));
            for(const id of ['mp-color','mp-width','mp-directory']) $(id).onchange=()=>this.preferences();
            $('mp-zoom').onchange = () => {this.cancelGesture();this.fit();};
            $('mp-undo').onclick=()=>this.undo(false);$('mp-redo').onclick=()=>this.undo(true);
            $('mp-close-lasso').onclick=()=>{if(this.pendingLasso){this.doc.selection=this.pendingLasso;this.pendingLasso=null;this.selectionChanged();}};
            $('mp-adjust').onclick=()=>{if(!this.doc)return;const b=['x0','y0','x1','y1'].map(k=>Number($('mp-'+k).value));const {width:w,height:h}=this.doc.source;if(!b.every(Number.isFinite)||b[0]<0||b[1]<0||b[2]>w||b[3]>h||b[0]>=b[2]||b[1]>=b[3])return this.status('Región inválida.');this.doc.selection={shape:'rect',bounds:b};this.selectionChanged();};
            this.canvas.onpointerdown=e=>this.down(e);this.canvas.onpointermove=e=>this.move(e);this.canvas.onpointerup=e=>this.up(e);
            this.canvas.onpointercancel=()=>this.cancelGesture();this.canvas.onlostpointercapture=()=>{if(this.gesture)this.cancelGesture();};
            document.addEventListener('keydown',e=>{if(!this.active)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();this.close();}else if(e.ctrlKey&&!e.target.matches('input,textarea')&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();e.stopImmediatePropagation();this.undo(e.key.toLowerCase()==='y'||e.shiftKey);}},true);
            const prior = A.app.onViewWillOpen; A.app.onViewWillOpen=name=>{if(this.active)this.suspend();prior?.(name);};
            const openFeature = A.companion.openFeature.bind(A.companion);
            A.companion.openFeature=id=>id==='magicpen'?this.open():openFeature(id);
            void A.app.bridge.listen('axx-pen-escape',()=>{if(this.active)this.close();});
            addEventListener('pagehide',()=>this.suspend());
            addEventListener('resize',()=>{if(this.active){this.cancelGesture();this.setInput(false);this.doc=null;this.viewport=null;this.pendingSelection=null;++this.generation;this.working=false;this.state='selecting';this.image=null;this.canvas.hidden=true;this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);this.status('La pantalla cambió. Selecciona de nuevo.');this.positionWidget();}});
            try {const p=JSON.parse(localStorage.getItem('axx.magicpen.prefs')||'{}');for(const id of ['mp-color','mp-width','mp-tool','mp-directory']) if(p[id])$(id).value=p[id];}catch{}
            this.voiceOwner = {state:'idle',onFinal:text=>{if(this.active)$('mp-question').value=text;},onError:text=>this.status(text),onState:()=>{$('mp-voice').innerHTML=this.voiceOwner.state==='listening'?'<span aria-hidden="true">■</span>':this.icon('mic');}};
            A.nativeVoice?.attach?.(this.voiceOwner);
            $('mp-voice').onclick=()=>{if(this.voiceOwner.state==='listening')this.voiceOwner.finish?.();else if(A.nativeVoice?.activeCapture)this.status('Termina el dictado activo antes de dictar esta pregunta.');else this.voiceOwner.start?.('es-ES');};
            $('mp-voice').hidden=!this.voiceOwner.start;this.chooseTool($('mp-tool').value||'rect');
        }
        mountDesktop(){
            this.root=document.createElement('section');this.root.id='mp-desktop';this.root.hidden=true;
            this.view.before(this.root);this.root.append(this.view);this.view.className='';this.view.hidden=false;
            this.toolbar=document.createElement('div');this.toolbar.id='mp-toolbar';this.toolbar.setAttribute('role','toolbar');this.toolbar.setAttribute('aria-label','Magic Pen en el escritorio');
            this.toolbar.innerHTML='<div class="mp-desktop-title"><strong>Magic Pen</strong><span>Sobre tu escritorio</span><button id="mp-done" aria-label="Cerrar Magic Pen">Listo · Esc</button></div>';
            this.toolbar.append(this.view.querySelector('.mp-toolstrip'));
            const interact=document.createElement('button');interact.id='mp-interact';interact.innerHTML=this.icon('pointer');interact.className='mp-icon-button';interact.title='Usar escritorio sin cerrar Magic Pen';interact.setAttribute('aria-label',interact.title);interact.onclick=()=>this.setInput(false);
            this.toolbar.querySelector('.mp-history-tools').before(interact);
            const all=document.createElement('button');all.id='mp-all';all.textContent='Todo';all.title='Seleccionar toda la pantalla actual';all.onclick=()=>{
                this.chooseTool('rect');this.setInput(false);
                this.run(async()=>{if(!await this.capture())return;this.doc.selection={shape:'rect',bounds:[0,0,this.doc.source.width,this.doc.source.height]};this.selectionChanged();await this.ask();});
            };this.toolbar.querySelector('#mp-select-tools').append(all);
            this.widget=document.createElement('aside');this.widget.id='mp-widget';this.widget.setAttribute('aria-label','Explicación de la selección');this.widget.hidden=true;
            this.widget.innerHTML='<div class="mp-widget-head"><strong>Sobre lo que marcaste</strong><button id="mp-hide-answer" aria-label="Ocultar explicación">×</button></div>';
            for(const selector of ['.mp-composer','#mp-status','#mp-answers','.mp-save-section','#mp-capability'])this.widget.append(this.view.querySelector(selector));
            const source=this.view.querySelector('.mp-source-row');this.widget.querySelector('.mp-save-section').append(source);source.hidden=true;
            this.view.append(this.canvas,this.toolbar,this.widget);
            for(const selector of ['.mp-modebar','.mp-stage','.mp-selection-row'])this.view.querySelector(selector).hidden=true;
            this.canvas.setAttribute('aria-label','Escritorio: selecciona o marca; Escape para salir');
            const option=new Option('Usar escritorio','interact');$('mp-tool').append(option);
            $('mp-done').onclick=()=>this.close();$('mp-hide-answer').onclick=()=>{this.widget.hidden=true;this.syncInput();};
            this.widget.querySelector('details').addEventListener('toggle',()=>this.positionWidget());
            new ResizeObserver(()=>{if(this.active)this.positionWidget();}).observe(this.widget);
        }
        chooseTool(tool){
            this.cancelGesture();$('mp-tool').value=tool;
            this.view.querySelectorAll('[data-mp-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mpTool===tool)));
            $('mp-select-tools').hidden=false;$('mp-ink-tools').hidden=false;
            $('mp-tool-hint').textContent={rect:'Arrastra sobre cualquier aplicación',point:'Toca un detalle',lasso:'Rodea lo que quieras explicar',pen:'Dibuja sobre el escritorio',marker:'Marca lo que quieras explicar',erase:'Toca un trazo para borrarlo',pointer:'Señala sobre el escritorio'}[tool]||'Usa el escritorio';
            if(this.active){
                this.widget.hidden=true;this.setInput(tool!=='interact'&&!!this.viewport);
                if(tool!=='interact'&&!this.viewport&&!this.working&&this.state!=='opening')this.run(async()=>{if(await this.capture())this.setInput(true);});
            }
            this.preferences();
        }
        setInput(enabled){
            this.inputEnabled=enabled;this.canvas.style.pointerEvents=enabled?'auto':'none';
            this.canvas.style.cursor=$('mp-tool').value==='erase'?'cell':'crosshair';
            $('mp-interact').setAttribute('aria-pressed',String(!enabled));this.syncInput();
        }
        syncInput(){if(A.app.ready)void A.app.updateHitMap();A.resident?.schedule();}
        positionWidget(){
            if(this.widget.hidden)return;
            const s=this.pendingSelection||this.doc?.selection,v=this.viewport,source=this.doc?.source;
            const b=s&&v?[(source.x+s.bounds[0]-v.x)/v.scale,(source.y+s.bounds[1]-v.y)/v.scale,(source.x+s.bounds[2]-v.x)/v.scale,(source.y+s.bounds[3]-v.y)/v.scale]:[24,140,24,140];
            const width=this.widget.offsetWidth,height=this.widget.offsetHeight;
            const right=b[2]+16,left=b[0]-width-16;
            const x=right+width<=innerWidth-12?right:left>=12?left:Math.max(12,innerWidth-width-12);
            const y=Math.max(12,Math.min(b[1],innerHeight-height-12));
            const avatar=$('avatar').getBoundingClientRect();
            const candidates=[[x,y],[left,y],[right,y],[x,avatar.top-height-16],[x,avatar.bottom+16]];
            const position=candidates.find(([cx,cy])=>cx>=12&&cy>=12&&cx+width<=innerWidth-12&&cy+height<=innerHeight-12&&(cx+width<=avatar.left||cx>=avatar.right||cy+height<=avatar.top||cy>=avatar.bottom))||[x,y];
            this.widget.style.left=position[0]+'px';this.widget.style.top=position[1]+'px';this.syncInput();
        }
        showWidget(){this.widget.hidden=false;this.positionWidget();}
        status(text){$('mp-status').textContent=text;if(this.active&&text)this.showWidget();}
        preferences(){try{localStorage.setItem('axx.magicpen.prefs',JSON.stringify(Object.fromEntries(['mp-color','mp-width','mp-tool','mp-directory'].map(id=>[id,$(id).value]))));}catch{this.status('No se pudieron guardar las preferencias.');}}
        async run(fn){
            if(this.working)return;const token=this.generation;this.working=true;$('mp-capture').disabled=true;
            try{await fn();}catch(e){if(token===this.generation){this.state='error';this.status(String(e.message||e));}}
            finally{if(token===this.generation){this.working=false;$('mp-capture').disabled=false;}}
        }
        async refresh(){const data=await api('status');this.capabilities=data.capabilities;$('mp-source').replaceChildren(...data.monitors.map((m,i)=>new Option(`Pantalla ${i+1} · ${m.width} × ${m.height}`,m.id)));$('mp-history').replaceChildren(new Option('Elige una captura',''),...data.history.map(d=>new Option(new Date(d.source.captured_at*1000).toLocaleString()+' · '+d.id.slice(0,6),d.id)));if(!$('mp-directory').value)$('mp-directory').value=data.capabilities.export_directory;$('mp-capability').textContent=(data.capabilities.vision.length?'Visión · '+data.capabilities.vision.map(p=>p.name).join(', '):'Análisis visual no configurado')+' · '+data.capabilities.ocr_message;return data;}
        open(){
            if(this.active)return;
            A.flow.cancelReview();A.companion.closeSurface();A.flow.fold();A.companion.enableFollow(false,false);
            this.active=true;this.pendingSelection=null;this.root.hidden=false;this.session(true);this.state='opening';this.doc=null;this.image=null;this.viewport=null;this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);this.renderAnswers();
            this.chooseTool('rect');
            this.run(async()=>{await this.refresh();if(!await this.capture())return;this.widget.hidden=true;this.state='selecting';this.setInput(true);});
        }
        isOpen(){return this.active;}
        session(active){if(A.isNative())this.sessionChain=this.sessionChain.catch(()=>{}).then(()=>A.nativeInvoke('magic_pen_session',{active})).catch(e=>this.status(String(e)));}
        suspend(){this.session(false);this.active=false;this.root.hidden=true;this.state='closed';this.cancelGesture();this.setInput(false);this.voiceOwner.stop?.();++this.generation;this.working=false;}
        close(){this.state='closing';this.suspend();this.syncInput();}
        async capture(){
            const token=this.generation;await this.flush();if(!this.active||token!==this.generation)return false;
            const d=await A.nativeInvoke('magic_pen_capture',{monitor:''});if(token!==this.generation)return false;
            const old=this.doc,undo=this.undoStack,redo=this.redoStack;
            await this.load(d);if(token!==this.generation)return false;
            if(old&&!['x','y','width','height'].every(k=>old.source[k]===d.source[k]))throw Error('La pantalla cambió. Selecciona otra vez.');
            if(old&&['x','y','width','height'].every(k=>old.source[k]===d.source[k])){
                d.strokes=clone(old.strokes);this.undoStack=undo;this.redoStack=redo;
            }
            return true;
        }
        async restore(id){if(!id)return;await this.flush();const token=this.generation;const d=await api('get',{id});if(token!==this.generation)return;await this.load(d);this.setInput(false);this.status('Historial: captura guardada; pulsa un selector para volver al escritorio actual.');}
        async load(d){
            const token=this.generation;delete d.preview;
            if(token!==this.generation||!this.active)return;
            this.doc=d;this.viewport=d.viewport||null;this.canvas.hidden=!this.viewport;this.image=null;this.undoStack=[];this.redoStack=[];this.saveError=null;
            this.cancelGesture();this.canvas.width=d.source.width;this.canvas.height=d.source.height;this.canvas.dataset.ready='true';
            $('mp-name').value='Axx-'+d.id.slice(0,8);this.state='reviewing';this.fit();this.render();this.renderAnswers();this.selectionFields();
        }
        queueSave(){if(!this.doc)return;const d=this.doc,snapshot={selection:clone(d.selection),strokes:clone(d.strokes)};this.saveChain=this.saveChain.then(async()=>{if(this.saveError)return;try{const saved=await api('save',{id:d.id,expected_revision:d.revision,...snapshot});d.revision=saved.revision;}catch(e){this.saveError=e;this.status('Borrador sin guardar: '+String(e.message||e));}});}
        async flush(){await this.saveChain;if(this.saveError)throw this.saveError;}
        selectionFields(){if(!this.doc?.selection)return;['x0','y0','x1','y1'].forEach((k,i)=>$('mp-'+k).value=Math.round(this.doc.selection.bounds[i]));}
        selectionChanged(){this.pendingSelection=null;this.pendingLasso=null;this.selectionFields();this.render();this.queueSave();this.setInput(false);this.showWidget();}
        fit(){if(!this.doc||!this.viewport)return;const s=this.doc.source,v=this.viewport;Object.assign(this.canvas.style,{left:(s.x-v.x)/v.scale+'px',top:(s.y-v.y)/v.scale+'px',width:s.width/v.scale+'px',height:s.height/v.scale+'px'});}
        point(e){if(!this.viewport)throw Error('Espera a que el escritorio esté listo.');return desktopPoint(e.clientX,e.clientY,this.viewport,this.doc.source);}
        down(e){if(!this.doc||!this.inputEnabled||this.working||e.button!==0)return;e.preventDefault();e.stopPropagation();try{const p=this.point(e),tool=$('mp-tool').value;this.pendingLasso=null;this.gesture={id:e.pointerId,tool,points:[p],color:$('mp-color').value,width:Math.min(80,Number($('mp-width').value)*(tool==='marker'?4:1)*this.viewport.scale)};this.canvas.setPointerCapture(e.pointerId);this.render();}catch(e){this.status(e.message);}}
        move(e){if(!this.gesture)return;e.preventDefault();e.stopPropagation();try{const p=this.point(e);if(this.gesture.points.length>=4096)return;this.gesture.points.push(p);if(!this.paintPending){this.paintPending=requestAnimationFrame(()=>{this.paintPending=0;this.render();});}}catch{this.cancelGesture();this.status('Gesto cancelado fuera de la imagen.');}}
        up(e){
            const g=this.gesture;if(!g)return;e.preventDefault();e.stopPropagation();this.gesture=null;
            if(this.canvas.hasPointerCapture(e.pointerId))this.canvas.releasePointerCapture(e.pointerId);
            if(g.tool==='pointer'){this.render();return;}
            const a=g.points[0],b=g.points.at(-1),w=this.canvas.width,h=this.canvas.height;
            let selection=null;
            if(g.tool==='point'){const r=100*this.viewport.scale;selection={shape:'point',anchor:a,bounds:[Math.max(0,a[0]-r),Math.max(0,a[1]-r),Math.min(w,a[0]+r),Math.min(h,a[1]+r)]};}
            else if(g.tool==='rect'){const bounds=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];if(bounds[2]-bounds[0]>=2&&bounds[3]-bounds[1]>=2)selection={shape:'rect',bounds};}
            else if(g.tool==='lasso'&&g.points.length>=3){
                const xs=g.points.map(p=>p[0]),ys=g.points.map(p=>p[1]);const pts=g.points;
                const area=pts.reduce((sum,p,i)=>{const q=pts[(i+1)%pts.length];return sum+p[0]*q[1]-q[0]*p[1];},0);
                if(Math.abs(area)>=2)selection={shape:'lasso',points:pts,bounds:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)]};
            }
            if(selection){
                this.pendingSelection=selection;this.doc.selection=null;this.renderAnswers();this.setInput(false);this.status('Capturando lo que acabas de seleccionar…');
                this.run(async()=>{if(!await this.capture())return;this.doc.selection=selection;this.selectionChanged();await this.ask();});return;
            }
            if(['pen','marker','erase'].includes(g.tool)){
                this.undoStack.push(clone(this.doc.strokes));this.redoStack=[];
                if(g.tool==='erase'){
                    const distance=(p,a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);};
                    this.doc.strokes=this.doc.strokes.filter(s=>!g.points.some(p=>s.points.some((q,i)=>distance(p,q,s.points[Math.max(0,i-1)])<=Math.max(12,s.width/2))));
                }else{
                    this.doc.strokes.push({tool:g.tool,points:g.points,color:g.color,width:g.width});
                    const pts=this.doc.strokes.flatMap(s=>s.points),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),pad=24*this.viewport.scale;
                    this.doc.selection={shape:'rect',bounds:[Math.max(0,Math.min(...xs)-pad),Math.max(0,Math.min(...ys)-pad),Math.min(w,Math.max(...xs)+pad),Math.min(h,Math.max(...ys)+pad)]};
                }
                this.queueSave();this.status('Marcas listas. Pulsa la flecha para explicar esta zona.');this.renderAnswers();
            }
            this.render();
        }
        cancelGesture(){const id=this.gesture?.id;this.gesture=null;this.pendingLasso=null;if(id!=null&&this.canvas.hasPointerCapture(id))this.canvas.releasePointerCapture(id);this.render();}
        undo(redo){if(!this.doc)return;const from=redo?this.redoStack:this.undoStack,to=redo?this.undoStack:this.redoStack;if(!from.length)return;to.push(clone(this.doc.strokes));this.doc.strokes=from.pop();this.queueSave();this.render();}
        path(points,close=false){const c=this.ctx;c.beginPath();points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));if(close)c.closePath();}
        stroke(s){const c=this.ctx;c.save();c.globalAlpha=s.tool==='marker'?.33:1;c.strokeStyle=s.color;c.fillStyle=s.color;c.lineWidth=s.width;c.lineCap='round';c.lineJoin='round';this.path(s.points);c.stroke();if(s.points.length===1){c.beginPath();c.arc(...s.points[0],s.width/2,0,Math.PI*2);c.fill();}c.restore();}
        render(){const c=this.ctx;c.clearRect(0,0,this.canvas.width,this.canvas.height);if(!this.doc)return;this.doc.strokes.forEach(s=>this.stroke(s));const g=this.gesture;if(g&&['pen','marker'].includes(g.tool))this.stroke(g);c.save();c.strokeStyle='#9274ff';c.fillStyle='#b8aaff22';c.lineWidth=Math.max(2,this.canvas.width/450);c.setLineDash([c.lineWidth*3,c.lineWidth*2]);const s=this.pendingLasso||this.doc.selection;if(s){if(s.shape==='lasso'){this.path(s.points,true);c.fill('evenodd');c.stroke();}else{const [x,y,r,b]=s.bounds;c.strokeRect(x,y,r-x,b-y);}if(s.anchor){c.beginPath();c.arc(...s.anchor,6,0,Math.PI*2);c.stroke();}}if(g){if(g.tool==='rect'){const a=g.points[0],b=g.points.at(-1);c.strokeRect(...a,b[0]-a[0],b[1]-a[1]);}else if(g.tool==='lasso'){this.path(g.points);c.stroke();}else if(g.tool==='pointer'){c.setLineDash([]);c.beginPath();c.arc(...g.points.at(-1),12,0,Math.PI*2);c.stroke();}}c.restore();$('mp-close-lasso').hidden=!this.pendingLasso;$('mp-meta').textContent=`${this.doc.source.width} × ${this.doc.source.height} · ${new Date(this.doc.source.captured_at*1000).toLocaleTimeString()} · ${this.doc.id.slice(0,6)}`;$('mp-undo').disabled=!this.undoStack.length;$('mp-redo').disabled=!this.redoStack.length;}
        renderAnswers(){const root=$('mp-answers');root.replaceChildren();for(const q of (this.doc?.queries||[]).filter(q=>this.doc.selection&&q.selection?.shape===this.doc.selection.shape&&['bounds','points','anchor'].every(k=>JSON.stringify(q.selection[k])===JSON.stringify(this.doc.selection[k]))).slice(-5)){const card=document.createElement('p');card.className='mp-answer';card.textContent=q.response||q.error||(q.state==='running'?'Analizando…':'Interrumpido; vuelve a preguntar.');card.title='Captura '+q.source_id.slice(0,6)+' · revisión '+q.revision;root.append(card);}}
        async ask(){
            if(!this.doc?.selection)return this.status('Selecciona o marca una región antes de preguntar.');
            if(this.queries.size)return this.status('Hay una explicación en curso. Espera su respuesta.');
            let d=this.doc;const token=this.generation;this.queries.add(d.id);$('mp-ask').disabled=true;this.setInput(false);
            try{
                // Ink is excluded from the new evidence, while its editable coordinates are preserved.
                if(['pen','marker','erase'].includes($('mp-tool').value)){
                    const selection=clone(d.selection);if(!await this.capture())return;
                    this.queries.delete(d.id);d=this.doc;this.queries.add(d.id);d.selection=selection;this.queueSave();
                }
                await this.flush();const revision=d.revision;this.status('Analizando tu selección…');
                const q=await api('analyze',{id:d.id,revision,selection_mode:Axx.companion.data.prefs.selection_mode||'manual',question:$('mp-question').value.trim()||'Explica el contenido de toda la región seleccionada. Ignora el cursor del ratón y cualquier indicador de puntero. Responde de forma clara y breve.'});
                d.queries.push(q);
                if(this.active&&token===this.generation&&this.doc===d&&d.revision===revision){this.renderAnswers();this.status(q.state==='completed'?'Puedes preguntar más o seleccionar otra zona.':q.error);}
            }catch(e){if(this.active&&token===this.generation&&this.doc===d)this.status(String(e.message||e));}
            finally{this.queries.delete(d.id);$('mp-ask').disabled=false;}
        }
        async export(kind){if(!this.doc)throw Error('Captura una pantalla primero.');await this.flush();this.status('Verificando exportación…');const r=await api('export',{id:this.doc.id,revision:this.doc.revision,kind,directory:$('mp-directory').value,name:$('mp-name').value+(kind==='original'?'-original':'-anotado')});$('mp-export').textContent=`Guardado y verificado: ${r.path}\nSHA256 ${r.sha256}`;this.status('PNG guardado y verificado.');}
    }
    A.magicPenGeometry={sourcePoint,desktopPoint};
    A.magicPen=new MagicPen();
})();
