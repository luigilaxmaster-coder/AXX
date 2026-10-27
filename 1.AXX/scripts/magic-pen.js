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
    function conciseSummary(response) {
        let text=String(response||'').replace(/```[\s\S]*?```/g,' ').replace(/!\[[^\]]*\]\([^)]*\)/g,' ').replace(/^\s*#{1,6}\s*/gm,'').replace(/[>*_`]/g,' ').split(/\n\s*\n/)[0].replace(/\s+/g,' ').trim();
        text=text.replace(/^(?:resumen|síntesis|en breve)\s*[:—-]\s*/i,'');
        const sentence=text.match(/^(.+?[.!?])(?:\s|$)/)?.[1]||text,words=sentence.split(/\s+/);
        return words.length>28?words.slice(0,28).join(' ')+'…':sentence;
    }
    class MagicPen {
        active = false; state = 'closed'; doc = null; image = null; gesture = null; pendingLasso = null;
        undoStack = []; redoStack = []; saveChain = Promise.resolve(); saveError = null; generation = 0; working = false; queries = new Set(); sessionChain = Promise.resolve();
        analysisEpoch = 0; analysisJob = null; analysisPending = false; analysisSetup = Promise.resolve(); cancelChain = Promise.resolve(); liveTimer = null; bubbleTimer = null; summaryBubbleMode = false; answerAvailable = false; summaryText = '';
        captureChain = Promise.resolve(); capturePending = 0;
        live = false; livePaused = false; historyMode = false; previewImage = null; answerDirty = false; selectionOrigin = null; inkBaseSelection = null;
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
                more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
                stop:'<rect x="6" y="6" width="12" height="12" rx="2"/>',
                done:'<path d="m5 12 4 4L19 6"/>',
                capture:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="12" cy="12" r="4"/>',
                undo:'<path d="m7 4-4 4 4 4M3 8h11a6 6 0 0 1 0 12h-3"/>',
                redo:'<path d="m17 4 4 4-4 4m4-4H10a6 6 0 0 0 0 12h3"/>',
                mic:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
                voice:'<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M17 9a5 5 0 0 1 0 6m2-9a9 9 0 0 1 0 12"/>',
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
            $('mp-capture').onclick = () => {this.cancelAnalysis();void this.run(()=>this.capture());};
            $('mp-ask').onclick = () => { void this.ask(); };
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
            $('mp-close-lasso').onclick=()=>{if(this.pendingLasso){this.cancelAnalysis();this.doc.selection=this.pendingLasso;this.pendingLasso=null;this.selectionChanged();this.scheduleAnalysis();}};
            $('mp-adjust').onclick=()=>{if(!this.doc)return;const b=['x0','y0','x1','y1'].map(k=>Number($('mp-'+k).value));const {width:w,height:h}=this.doc.source;if(!b.every(Number.isFinite)||b[0]<0||b[1]<0||b[2]>w||b[3]>h||b[0]>=b[2]||b[1]>=b[3])return this.status('Región inválida.');this.cancelAnalysis();this.doc.selection={shape:'rect',bounds:b};this.selectionChanged();this.scheduleAnalysis();};
            this.canvas.onpointerdown=e=>this.down(e);this.canvas.onpointermove=e=>this.move(e);this.canvas.onpointerup=e=>this.up(e);
            this.canvas.onpointercancel=()=>this.cancelGesture();this.canvas.onlostpointercapture=()=>{if(this.gesture)this.cancelGesture();};
            document.addEventListener('keydown',e=>{if(!this.active)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();this.close();}else if(e.ctrlKey&&!e.target.matches('input,textarea')&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();e.stopImmediatePropagation();this.undo(e.key.toLowerCase()==='y'||e.shiftKey);}},true);
            const prior = A.app.onViewWillOpen; A.app.onViewWillOpen=name=>{if(this.active)this.suspend();prior?.(name);};
            const openFeature = A.companion.openFeature.bind(A.companion);
            A.companion.openFeature=id=>id==='magicpen'?this.open():openFeature(id);
            void A.app.bridge.listen('axx-pen-escape',()=>{if(this.active)this.close();});
            void A.app.bridge.listen('axx-pen-geometry',()=>this.invalidateGeometry());
            addEventListener('pagehide',()=>this.suspend());
            addEventListener('resize',()=>{this.invalidateGeometry();if(this.active)this.positionWidget();});
            try {const p=JSON.parse(localStorage.getItem('axx.magicpen.prefs')||'{}');for(const id of ['mp-color','mp-width','mp-tool','mp-directory']) if(p[id])$(id).value=p[id];this.live=p.live===true;}catch{}
            this.voiceOwner = {state:'idle',onFinal:text=>{if(this.active)$('mp-question').value=text;},onError:text=>this.status(text),onState:()=>{$('mp-voice').innerHTML=this.voiceOwner.state==='listening'?'<span aria-hidden="true">■</span>':this.icon('mic');}};
            A.nativeVoice?.attach?.(this.voiceOwner);
            $('mp-voice').onclick=()=>{if(this.voiceOwner.state==='listening')this.voiceOwner.finish?.();else if(A.nativeVoice?.activeCapture)this.status('Termina el dictado activo antes de dictar esta pregunta.');else this.voiceOwner.start?.('es-ES');};
            $('mp-voice').hidden=!this.voiceOwner.start;this.chooseTool($('mp-tool').value||'rect');this.updateControls();
        }
        mountDesktop(){
            this.root=document.createElement('section');this.root.id='mp-desktop';this.root.hidden=true;
            this.view.before(this.root);this.root.append(this.view);this.view.className='';this.view.hidden=false;
            this.toolbar=document.createElement('div');this.toolbar.id='mp-toolbar';this.toolbar.setAttribute('role','toolbar');this.toolbar.setAttribute('aria-label','Magic Pen en el escritorio');
            this.view.append(this.toolbar);
            this.toolbar.innerHTML='<div class="mp-toolbar-row"><div class="mp-primary-tools" role="group" aria-label="Herramientas principales"></div><button id="mp-interact" type="button" class="mp-icon-button" title="Usar escritorio sin cerrar Magic Pen" aria-label="Usar escritorio sin cerrar Magic Pen" aria-pressed="false">'+this.icon('pointer')+'</button><details id="mp-more-tools"><summary id="mp-more-toggle" aria-label="Más herramientas" aria-controls="mp-more-panel" aria-expanded="false" title="Más herramientas">'+this.icon('more')+'<span>Más</span></summary><div id="mp-more-panel" role="group" aria-label="Más herramientas de Magic Pen"><section class="mp-more-section" aria-labelledby="mp-selection-label"><span id="mp-selection-label" class="mp-section-label">Selección</span></section><section class="mp-more-section" aria-labelledby="mp-ink-label"><span id="mp-ink-label" class="mp-section-label">Tinta</span><div class="mp-ink-settings"></div></section><section class="mp-more-section" aria-labelledby="mp-analysis-label"><span id="mp-analysis-label" class="mp-section-label">Análisis</span><div class="mp-menu-actions"><button id="mp-live" type="button" aria-pressed="false">En directo</button><button id="mp-pause" type="button" hidden>Pausar</button></div><p id="mp-live-status" role="status" aria-live="polite">Análisis manual · solo al pulsar Preguntar</p></section></div></details><button id="mp-stop-analysis" type="button" aria-label="Detener análisis" title="Detener análisis" hidden>'+this.icon('stop')+'<span>Detener</span></button><button id="mp-done" type="button" aria-label="Cerrar Magic Pen" title="Cerrar Magic Pen · Esc">'+this.icon('done')+'<span>Listo</span></button></div>';
            for(const [id,label] of [['rect','Seleccionar'],['pen','Dibujar']]){
                const button=this.view.querySelector('[data-mp-tool="'+id+'"]');button.className='mp-primary-tool';button.setAttribute('aria-label',id==='rect'?'Seleccionar un rectángulo':'Dibujar con pluma');button.insertAdjacentHTML('beforeend','<span>'+label+'</span>');this.toolbar.querySelector('.mp-primary-tools').append(button);
            }
            this.toolbar.querySelector('#mp-more-tools').before($('mp-undo'));
            this.toolbar.querySelector('[aria-labelledby="mp-selection-label"]').append($('mp-select-tools'));
            this.toolbar.querySelector('[aria-labelledby="mp-ink-label"]>.mp-ink-settings').before($('mp-ink-tools'));
            this.toolbar.querySelector('.mp-ink-settings').append($('mp-color'),$('mp-width'));
            $('mp-ink-tools').querySelector('.mp-divider').remove();
            for(const [id,label] of [['mp-color','Color'],['mp-width','Grosor']]){const field=document.createElement('label');field.textContent=label;$(id).before(field);field.append($(id));}
            const pointer=document.createElement('button');pointer.className='mp-icon-button';pointer.dataset.mpTool='pointer';pointer.title='Señalar temporalmente';pointer.setAttribute('aria-label',pointer.title);pointer.setAttribute('aria-pressed','false');pointer.innerHTML=this.icon('pointer');$('mp-ink-tools').append(pointer);
            for(const [id,label] of [['point','Punto'],['lasso','Lazo'],['marker','Marcador'],['erase','Borrar'],['pointer','Señalar']]){const button=this.toolbar.querySelector('[data-mp-tool="'+id+'"]');button.className='mp-secondary-tool';button.insertAdjacentHTML('beforeend','<span>'+label+'</span>');}
            this.toolbar.querySelector('.mp-ink-settings').append($('mp-redo'));
            this.toolbar.querySelector('[aria-labelledby="mp-ink-label"]').append($('mp-tool-hint'));
            this.view.querySelector('.mp-toolstrip').remove();
            $('mp-interact').onclick=()=>{this.closeTools();this.setInput(false);};
            $('mp-more-tools').addEventListener('toggle',()=>{$('mp-more-toggle').setAttribute('aria-expanded',String($('mp-more-tools').open));this.syncInput();});
            this.toolbar.addEventListener('animationend',()=>this.syncInput());
            document.addEventListener('pointerdown',e=>{if(this.active&&!$('mp-more-tools').contains(e.target))this.closeTools();},true);
            const all=document.createElement('button');all.id='mp-all';all.innerHTML=this.icon('capture')+'<span>Pantalla</span>';all.title='Seleccionar toda la pantalla actual';all.onclick=()=>{
                this.chooseTool('rect');this.setInput(false);
                this.cancelAnalysis();void this.run(async()=>{if(!await this.capture())return;this.doc.selection={shape:'rect',bounds:[0,0,this.doc.source.width,this.doc.source.height]};this.selectionChanged();this.scheduleAnalysis(0,false);});
            };this.toolbar.querySelector('#mp-select-tools').append(all);
            this.widget=document.createElement('aside');this.widget.id='mp-widget';this.widget.setAttribute('aria-label','Explicación de la selección');this.widget.tabIndex=-1;this.widget.hidden=true;
            this.widget.innerHTML='<div class="mp-widget-head"><span class="mp-head-mark" aria-hidden="true">'+this.icon('pen')+'</span><span class="mp-head-copy"><strong>Magic Pen</strong></span><span id="mp-summary-spinner" class="mp-summary-spinner" hidden aria-hidden="true"></span><button id="mp-hide-answer" aria-label="Ocultar explicación">×</button></div><section id="mp-summary-bubble" class="mp-summary-bubble" hidden><div class="mp-summary-kicker"><span id="mp-summary-label">Lo esencial</span></div><p id="mp-summary-text" role="status" aria-live="polite"></p><p id="mp-summary-voice-status" role="status" aria-live="polite" hidden></p><div class="mp-summary-actions"><button id="mp-summary-expand" type="button">Ver explicación</button><button id="mp-summary-listen" type="button" aria-label="Escuchar resumen" title="Escuchar resumen">'+this.icon('voice')+'</button></div></section><figure id="mp-history-preview" hidden><canvas id="mp-preview-canvas" aria-label="Vista previa de la captura guardada"></canvas><figcaption>Captura guardada · no es el escritorio actual</figcaption><button id="mp-back-desktop" type="button">Volver al escritorio</button></figure><div id="mp-vision-missing" hidden><p>El modelo seleccionado no tiene análisis visual disponible.</p><button id="mp-configure" type="button">Ajustes de conexión</button></div>';
            for(const selector of ['#mp-answers','.mp-composer','#mp-status','.mp-save-section'])this.widget.append(this.view.querySelector(selector));
            const saved=this.widget.querySelector('.mp-save-section');saved.querySelector('summary').after($('mp-meta'));saved.append($('mp-capability'));
            const source=this.view.querySelector('.mp-source-row');this.widget.querySelector('.mp-save-section').append(source);source.hidden=true;
            this.view.append(this.canvas,this.toolbar,this.widget);
            this.widget.addEventListener('animationend',e=>{if(e.target===this.widget&&e.animationName==='mp-bubble-in'&&this.active)this.syncInput();});
            for(const selector of ['.mp-modebar','.mp-stage','.mp-selection-row'])this.view.querySelector(selector).hidden=true;
            this.canvas.setAttribute('aria-label','Escritorio: selecciona o marca; Escape para salir');
            const option=new Option('Usar escritorio','interact');$('mp-tool').append(option);
            const reopen=document.createElement('button');reopen.id='mp-show-answer';reopen.type='button';reopen.className='mp-show-answer';reopen.hidden=true;reopen.innerHTML=this.icon('voice')+'<span>Ver explicación</span>';reopen.setAttribute('aria-label','Volver a la explicación');$('mp-more-panel').append(reopen);
            $('mp-done').onclick=()=>this.close();$('mp-hide-answer').onclick=()=>this.hideAnswer();reopen.onclick=()=>{this.closeTools();this.openAnswer();};
            $('mp-summary-expand').onclick=()=>this.openAnswer();$('mp-summary-listen').onclick=()=>this.readSummary();
            $('mp-live').onclick=()=>{this.live=!this.live;this.livePaused=false;this.cancelAnalysis();this.preferences();this.updateControls();this.status(this.live?'En directo: analiza al terminar una selección o al hacer una pausa en la tinta.':'Modo manual: selecciona y pulsa Preguntar.');};
            $('mp-pause').onclick=()=>{this.livePaused=!this.livePaused;this.cancelAnalysis();this.updateControls();this.status(this.livePaused?'Análisis en directo pausado. Puedes seguir anotando.':'En directo preparado. Haz una nueva selección o marca.');};
            $('mp-stop-analysis').onclick=()=>{this.cancelAnalysis();if(this.live)this.livePaused=true;this.updateControls();this.status('Análisis detenido. Tus marcas se conservan.');};
            $('mp-back-desktop').onclick=()=>{void this.run(()=>this.returnDesktop());};
            $('mp-configure').onclick=()=>A.companion.openFeature('ai');
            this.widget.querySelector('details').addEventListener('toggle',()=>this.positionWidget());
            new ResizeObserver(()=>{if(this.active)this.positionWidget();}).observe(this.widget);
        }
        closeTools(restoreFocus=false){
            const menu=$('mp-more-tools');if(!menu.open)return;
            const focused=menu.contains(document.activeElement);menu.open=false;$('mp-more-toggle').setAttribute('aria-expanded','false');
            if(restoreFocus&&focused)$('mp-more-toggle').focus({preventScroll:true});this.syncInput();
        }
        chooseTool(tool){
            this.closeTools(true);this.cancelGesture();$('mp-tool').value=tool;
            $('mp-select-tools').hidden=false;$('mp-ink-tools').hidden=false;
            $('mp-tool-hint').textContent={rect:'Arrastra sobre cualquier aplicación',point:'Toca un detalle',lasso:'Rodea lo que quieras explicar',pen:'Dibuja sobre el escritorio',marker:'Marca lo que quieras explicar',erase:'Toca un trazo para borrarlo',pointer:'Señala sobre el escritorio'}[tool]||'Usa el escritorio';
            if(this.active){
                if(this.historyMode&&tool!=='interact'){void this.run(()=>this.returnDesktop());return;}
                if(!this.analysisPending)this.widget.hidden=true;this.setInput(tool!=='interact'&&!!this.viewport);
                if(tool!=='interact'&&!this.viewport&&!this.working&&this.state!=='opening')this.run(async()=>{if(await this.capture())this.setInput(true);});
            }
            this.preferences();
        }
        setInput(enabled){
            this.inputEnabled=enabled;this.canvas.style.pointerEvents=enabled?'auto':'none';
            const tool=$('mp-tool').value,family={point:'rect',lasso:'rect',marker:'pen',erase:'pen',pointer:'pen'}[tool]||tool;
            this.view.querySelectorAll('[data-mp-tool]').forEach(b=>b.setAttribute('aria-pressed',String(enabled&&b.dataset.mpTool===(b.classList.contains('mp-primary-tool')?family:tool))));
            this.canvas.style.cursor=tool==='erase'?'cell':'crosshair';
            $('mp-interact').setAttribute('aria-pressed',String(!enabled));this.syncInput();
        }
        syncInput(){if(A.app.ready)void A.app.updateHitMap();A.resident?.schedule();}
        clearBubbleTimer(){clearTimeout(this.bubbleTimer);this.bubbleTimer=null;}
        clearSummaryBubble(clearAnswer=false){
            this.clearBubbleTimer();this.summaryBubbleMode=false;this.widget.classList.remove('mp-bubble-mode','mp-bubble-leaving');this.widget.removeAttribute('data-bubble-side');this.widget.style.removeProperty('--mp-bubble-enter');$('mp-summary-bubble').hidden=true;$('mp-summary-spinner').hidden=true;$('mp-summary-voice-status').hidden=true;$('mp-show-answer').hidden=true;
            if(clearAnswer){this.answerAvailable=false;this.summaryText='';$('mp-summary-text').textContent='';}
        }
        showPendingBubble(){
            this.clearSummaryBubble(true);this.summaryBubbleMode=true;this.widget.classList.add('mp-bubble-mode');$('mp-summary-bubble').hidden=false;$('mp-summary-label').textContent='Analizando';$('mp-summary-text').textContent='Estoy revisando esa zona…';$('mp-summary-spinner').hidden=false;$('mp-summary-listen').hidden=true;$('mp-summary-expand').hidden=true;this.showWidget();
        }
        showSummaryBubble(response){
            this.summaryText=conciseSummary(response);if(!this.summaryText){this.clearSummaryBubble(true);this.status('La respuesta llegó vacía. Puedes volver a preguntar.');return;}
            this.clearSummaryBubble(false);this.answerAvailable=true;this.summaryBubbleMode=true;this.widget.classList.add('mp-bubble-mode');$('mp-summary-bubble').hidden=false;$('mp-summary-label').textContent='Lo esencial';$('mp-summary-text').textContent=this.summaryText;$('mp-summary-spinner').hidden=true;$('mp-summary-voice-status').hidden=true;$('mp-summary-listen').hidden=false;$('mp-summary-expand').hidden=false;$('mp-show-answer').hidden=true;this.showWidget();
            this.bubbleTimer=setTimeout(()=>this.dismissSummaryBubble(),12000);
            const prefs=A.companion.data.prefs;if(prefs.voiceRead===true&&!prefs.mutedAll&&!this.speechBusy())this.readSummary(true);
        }
        dismissSummaryBubble(){
            if(!this.summaryBubbleMode)return;this.clearBubbleTimer();this.widget.classList.add('mp-bubble-leaving');this.bubbleTimer=setTimeout(()=>{this.summaryBubbleMode=false;this.widget.hidden=true;this.widget.classList.remove('mp-bubble-mode','mp-bubble-leaving');this.widget.removeAttribute('data-bubble-side');this.widget.style.removeProperty('--mp-bubble-enter');$('mp-summary-bubble').hidden=true;$('mp-show-answer').hidden=!this.answerAvailable;this.bubbleTimer=null;this.syncInput();},260);
        }
        hideAnswer(){this.clearSummaryBubble(false);this.widget.hidden=true;$('mp-show-answer').hidden=!this.answerAvailable;this.syncInput();}
        openAnswer(){
            if(!this.answerAvailable)return;this.clearSummaryBubble(false);this.widget.classList.remove('mp-bubble-mode','mp-bubble-leaving');$('mp-summary-bubble').hidden=true;$('mp-show-answer').hidden=true;this.showWidget();this.widget.focus({preventScroll:true});$('mp-answers').lastElementChild?.scrollIntoView({block:'nearest'});
        }
        speechBusy(){
            const s=A.symbiosis,readers=[s?.reader,A.voice13?.reader];
            return Boolean(A.companion?.speaking||A.companion?.pending||A.nativeVoice?.activeCapture||s?.liveActive||['starting','listening','stopping'].includes(s?.dictation?.state)||A.voice13?.status==='listening'||readers.some(r=>['starting','speaking','paused'].includes(r?.state))||window.speechSynthesis?.speaking||window.speechSynthesis?.pending);
        }
        readSummary(automatic=false){
            const prefs=A.companion.data.prefs;
            if(prefs.mutedAll){if(!automatic)this.summaryFeedback('La voz está silenciada en Sonido.');return false;}
            if(this.speechBusy()){if(!automatic)this.summaryFeedback('Axx está usando la voz o el micrófono. Espera a que termine y vuelve a pulsar.');return false;}
            if(!this.summaryText||typeof A.companion.read!=='function'){if(!automatic)this.summaryFeedback('La voz todavía no está disponible.');return false;}
            try{A.companion.read(this.summaryText);this.summaryFeedback('Leyendo el resumen…');return true;}catch(e){this.summaryFeedback('No se pudo iniciar la voz: '+String(e.message||e));return false;}
        }
        summaryFeedback(text){$('mp-summary-voice-status').textContent=text;$('mp-summary-voice-status').hidden=false;}
        positionWidget(){
            if(this.widget.hidden)return;
            const toolbar=this.toolbar.getBoundingClientRect();
            this.widget.style.maxHeight=Math.max(80,Math.min(innerHeight-24,toolbar.top-24))+'px';
            const stage=$('stage').getBoundingClientRect(),canvas=$('avatar').getBoundingClientRect(),bounds=stage.width&&stage.height?stage:canvas,size=Math.min(bounds.width,bounds.height)*.58,cx=bounds.left+bounds.width/2,cy=bounds.top+bounds.height/2,avatar={left:cx-size/2,right:cx+size/2,top:cy-size/2,bottom:cy+size/2,width:size,height:size},width=this.widget.offsetWidth,height=this.widget.offsetHeight,bottom=Math.min(innerHeight-12,toolbar.top-12);
            if(this.summaryBubbleMode){
                const center=avatar.left+avatar.width/2-width/2,mid=avatar.top+avatar.height/2-height/2;
                const candidates=[{x:avatar.right+4,y:mid,side:'left'},{x:avatar.left-width-4,y:mid,side:'right'},{x:center,y:avatar.top-height-4,side:'bottom'},{x:center,y:avatar.bottom+4,side:'top'}];
                const position=candidates.find(p=>p.x>=12&&p.y>=12&&p.x+width<=innerWidth-12&&p.y+height<=bottom);
                if(position){this.widget.dataset.bubbleSide=position.side;this.widget.style.setProperty('--mp-bubble-enter',{left:'translateX(-10px)',right:'translateX(10px)',bottom:'translateY(8px)',top:'translateY(-8px)'}[position.side]);this.widget.style.left=position.x+'px';this.widget.style.top=position.y+'px';this.syncInput();return;}
            }
            const s=this.pendingSelection||this.doc?.selection,v=this.viewport,source=this.doc?.source;
            const b=s&&v?[(source.x+s.bounds[0]-v.x)/v.scale,(source.y+s.bounds[1]-v.y)/v.scale,(source.x+s.bounds[2]-v.x)/v.scale,(source.y+s.bounds[3]-v.y)/v.scale]:[24,140,24,140];
            const right=b[2]+16,left=b[0]-width-16;
            const x=right+width<=innerWidth-12?right:left>=12?left:Math.max(12,innerWidth-width-12);
            const y=Math.max(12,Math.min(b[1],bottom-height));
            const candidates=[[x,y],[left,y],[right,y],[x,avatar.top-height-16],[x,avatar.bottom+16]];
            const position=candidates.find(([cx,cy])=>cx>=12&&cy>=12&&cx+width<=innerWidth-12&&cy+height<=bottom&&(cx+width<=avatar.left||cx>=avatar.right||cy+height<=avatar.top||cy>=avatar.bottom))||[x,y];
            this.widget.style.left=position[0]+'px';this.widget.style.top=position[1]+'px';this.syncInput();
        }
        showWidget(){this.widget.hidden=false;this.positionWidget();}
        status(text){$('mp-status').textContent=text;if(this.active&&text)this.showWidget();}
        preferences(){try{localStorage.setItem('axx.magicpen.prefs',JSON.stringify({...Object.fromEntries(['mp-color','mp-width','mp-tool','mp-directory'].map(id=>[id,$(id).value])),live:this.live}));}catch{this.status('No se pudieron guardar las preferencias.');}}
        async run(fn){
            if(this.working)return false;const token=this.generation;this.working=true;this.updateControls();
            try{return await fn();}catch(e){if(token===this.generation){this.state='error';this.status(String(e.message||e));}return false;}
            finally{if(token===this.generation){this.working=false;this.updateControls();}}
        }
        async refresh(){const data=await api('status');this.capabilities=data.capabilities;$('mp-source').replaceChildren(...data.monitors.map((m,i)=>new Option(`Pantalla ${i+1} · ${m.width} × ${m.height}`,m.id)));$('mp-history').replaceChildren(new Option('Elige una captura',''),...data.history.map(d=>new Option(new Date(d.source.captured_at*1000).toLocaleString()+' · '+d.id.slice(0,6),d.id)));if(!$('mp-directory').value)$('mp-directory').value=data.capabilities.export_directory;$('mp-capability').textContent=(data.capabilities.vision.length?'Visión · '+data.capabilities.vision.map(p=>p.name).join(', '):'Análisis visual no configurado')+' · '+data.capabilities.ocr_message;this.updateControls();return data;}
        open(){
            if(this.active)return;
            $('mp-status').textContent='Preparando el escritorio…';
            A.flow.cancelReview();A.companion.closeSurface();A.flow.fold();A.companion.enableFollow(false,false);
            this.clearSummaryBubble(true);this.active=true;this.pendingSelection=null;this.root.hidden=false;this.session(true);this.state='opening';this.doc=null;this.image=null;this.viewport=null;this.historyMode=false;this.livePaused=false;this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);this.renderAnswers();this.updateControls();
            this.chooseTool('rect');
            const session=this.generation,current=()=>this.active&&session===this.generation;
            this.run(async()=>{await this.refresh();if(!current()||!await this.capture({isCurrent:current}))return;$('mp-status').textContent='Selecciona una región o dibuja para empezar.';this.widget.hidden=true;this.state='selecting';this.setInput(true);});
        }
        isOpen(){return this.active;}
        session(active){if(A.isNative())this.sessionChain=this.sessionChain.catch(()=>{}).then(()=>A.nativeInvoke('magic_pen_session',{active})).catch(e=>this.status(String(e)));}
        suspend(){this.closeTools();this.clearSummaryBubble(true);this.cancelAnalysis();this.session(false);this.active=false;this.root.hidden=true;this.state='closed';this.cancelGesture();this.setInput(false);this.voiceOwner.stop?.();++this.generation;this.working=false;this.updateControls();}
        close(){this.state='closing';this.suspend();this.syncInput();}
        invalidateGeometry(){
            // Native move/scale events also invalidate physical coordinates even
            // when the WebView's CSS dimensions have not changed.
            if(!this.active||!this.doc||!this.viewport)return;
            this.cancelAnalysis();this.cancelGesture();this.setInput(false);this.doc=null;this.viewport=null;this.pendingSelection=null;++this.generation;
            this.working=false;this.state='selecting';this.image=null;this.historyMode=false;this.canvas.hidden=true;this.ctx.clearRect(0,0,this.canvas.width,this.canvas.height);
            this.renderAnswers();this.status('La pantalla o la posición de Axx cambió. Selecciona de nuevo.');this.updateControls();this.positionWidget();
        }
        async capture({isCurrent=()=>true}={}){
            const token=this.generation;await this.flush();if(!this.active||token!==this.generation||!isCurrent())return false;
            const current=()=>this.active&&token===this.generation&&isCurrent();
            if(this.capturePending)this.status('Esperando que termine la captura anterior…');
            ++this.capturePending;
            const request=this.captureChain.catch(()=>{}).then(()=>current()?A.nativeInvoke('magic_pen_capture',{monitor:''}):null);
            this.captureChain=request.then(()=>{},()=>{});
            let d;try{d=await request;}finally{--this.capturePending;}
            if(!d||!current())return false;
            const old=this.doc,undo=this.undoStack,redo=this.redoStack,origin=this.selectionOrigin,base=this.inkBaseSelection;
            await this.load(d);if(token!==this.generation)return false;
            if(old&&(!['x','y','width','height'].every(k=>old.source[k]===d.source[k])||!['x','y','scale'].every(k=>old.viewport?.[k]===d.viewport?.[k]))){this.pendingSelection=null;this.setInput(false);throw Error('La pantalla o la posición de Axx cambió. Selecciona otra vez.');}
            if(old&&['x','y','width','height'].every(k=>old.source[k]===d.source[k])){
                d.strokes=clone(old.strokes);this.undoStack=undo;this.redoStack=redo;this.selectionOrigin=origin;this.inkBaseSelection=base;this.render();
            }
            return true;
        }
        async restore(id){if(!id)return;this.clearSummaryBubble(true);this.cancelAnalysis();const token=this.generation,current=()=>this.active&&token===this.generation;await this.flush();if(!current())return;const d=await api('get',{id});if(!current())return;await this.load(d,true);if(!current())return;this.setInput(false);this.status('Historial: la imagen guardada se muestra solo en esta vista previa.');}
        async returnDesktop(){this.clearSummaryBubble(true);this.cancelAnalysis();const token=this.generation,current=()=>this.active&&token===this.generation;await this.flush();if(!current())return;this.doc=null;this.historyMode=false;this.previewImage=null;this.viewport=null;this.updateControls();if(await this.capture({isCurrent:current})){this.setInput($('mp-tool').value!=='interact');this.status('Escritorio actual preparado. Haz una nueva selección.');}}
        async load(d,history=false){
            const token=this.generation;
            if(token!==this.generation||!this.active)return;
            this.doc=d;this.selectionOrigin=d.selection?'explicit':null;this.inkBaseSelection=null;this.answerDirty=false;this.historyMode=history;this.viewport=history?null:d.viewport||null;this.canvas.hidden=!this.viewport;this.image=null;this.previewImage=null;this.undoStack=[];this.redoStack=[];this.saveError=null;
            this.cancelGesture();this.canvas.width=d.source.width;this.canvas.height=d.source.height;this.canvas.dataset.ready='true';
            $('mp-name').value='Axx-'+d.id.slice(0,8);this.state='reviewing';this.fit();this.render();this.renderAnswers();this.selectionFields();
            this.updateControls();
            if(history){
                if(typeof d.preview!=='string'||!/^data:image\/png;base64,/.test(d.preview))throw Error('No se pudo recuperar la vista previa de esta captura.');
                const image=new Image();image.src=d.preview;await image.decode();
                if(token!==this.generation||this.doc!==d||!this.active)return;
                this.previewImage=image;this.paintPreview();this.showWidget();
            }
        }
        queueSave(){if(!this.doc)return;const d=this.doc,snapshot={selection:clone(d.selection),strokes:clone(d.strokes)};this.saveChain=this.saveChain.then(async()=>{if(this.saveError)return;try{const saved=await api('save',{id:d.id,expected_revision:d.revision,...snapshot});d.revision=saved.revision;}catch(e){this.saveError=e;this.status('Borrador sin guardar: '+String(e.message||e));}});}
        async flush(){await this.saveChain;if(this.saveError)throw this.saveError;}
        selectionFields(){if(!this.doc?.selection)return;['x0','y0','x1','y1'].forEach((k,i)=>$('mp-'+k).value=Math.round(this.doc.selection.bounds[i]));}
        selectionChanged(){this.clearSummaryBubble(true);this.pendingSelection=null;this.pendingLasso=null;this.selectionOrigin='explicit';this.inkBaseSelection=null;this.answerDirty=true;this.selectionFields();this.render();this.renderAnswers();this.queueSave();this.setInput(this.live&&!this.livePaused&&!this.historyMode);this.showWidget();}
        fit(){if(!this.doc||!this.viewport)return;const s=this.doc.source,v=this.viewport;Object.assign(this.canvas.style,{left:(s.x-v.x)/v.scale+'px',top:(s.y-v.y)/v.scale+'px',width:s.width/v.scale+'px',height:s.height/v.scale+'px'});}
        point(e){if(!this.viewport)throw Error('Espera a que el escritorio esté listo.');return desktopPoint(e.clientX,e.clientY,this.viewport,this.doc.source);}
        down(e){if(!this.doc||!this.inputEnabled||this.working||e.button!==0)return;e.preventDefault();e.stopPropagation();try{const p=this.point(e),tool=$('mp-tool').value;if(tool!=='pointer')this.cancelAnalysis();this.pendingLasso=null;this.gesture={id:e.pointerId,tool,points:[p],color:$('mp-color').value,width:Math.min(80,Number($('mp-width').value)*(tool==='marker'?4:1)*this.viewport.scale)};this.canvas.setPointerCapture(e.pointerId);this.render();}catch(e){this.status(e.message);}}
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
                void this.run(async()=>{if(!await this.capture())return;this.doc.selection=selection;this.selectionChanged();this.status(this.live?'Selección lista.':'Selección lista. Pulsa Preguntar para analizarla.');this.scheduleAnalysis(0,false);});return;
            }
            if(['pen','marker','erase'].includes(g.tool)){
                if(g.tool!=='erase'&&(this.doc.strokes.length>=1000||this.doc.strokes.reduce((sum,s)=>sum+s.points.length,0)+g.points.length>50000)){this.status('Límite de tinta alcanzado. Guarda tus marcas y comienza otra captura.');this.render();return;}
                this.undoStack.push(this.inkSnapshot());if(this.undoStack.length>50)this.undoStack.shift();this.redoStack=[];
                if(g.tool==='erase'){
                    const distance=(p,a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);};
                    this.doc.strokes=this.doc.strokes.filter(s=>!g.points.some(p=>s.points.some((q,i)=>distance(p,q,s.points[Math.max(0,i-1)])<=Math.max(12,s.width/2))));
                    if(this.selectionOrigin==='ink')this.selectInk();
                }else{
                    if(this.selectionOrigin!=='ink')this.inkBaseSelection=clone(this.doc.selection);
                    this.doc.strokes.push({tool:g.tool,points:g.points,color:g.color,width:g.width});
                    this.selectInk();
                }
                this.answerDirty=true;this.queueSave();this.status(this.live&&!this.livePaused?'Analizaré esta zona cuando termines de marcar.':'Marcas listas. Pulsa Preguntar para explicar esta zona.');this.renderAnswers();this.scheduleAnalysis(650,true);
            }
            this.render();
        }
        cancelGesture(){const id=this.gesture?.id;this.gesture=null;this.pendingLasso=null;if(id!=null&&this.canvas.hasPointerCapture(id))this.canvas.releasePointerCapture(id);this.render();}
        inkSnapshot(){return {strokes:clone(this.doc.strokes),selection:clone(this.doc.selection),origin:this.selectionOrigin,base:clone(this.inkBaseSelection)};}
        selectInk(){
            if(!this.doc.strokes.length){this.doc.selection=clone(this.inkBaseSelection);this.selectionOrigin=this.doc.selection?'explicit':null;this.inkBaseSelection=null;return;}
            const pts=this.doc.strokes.flatMap(s=>s.points),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),pad=24*(this.viewport?.scale||1),{width:w,height:h}=this.doc.source;
            this.doc.selection={shape:'rect',bounds:[Math.max(0,Math.min(...xs)-pad),Math.max(0,Math.min(...ys)-pad),Math.min(w,Math.max(...xs)+pad),Math.min(h,Math.max(...ys)+pad)]};this.selectionOrigin='ink';
        }
        undo(redo){if(!this.doc)return;const from=redo?this.redoStack:this.undoStack,to=redo?this.undoStack:this.redoStack;if(!from.length)return;this.cancelAnalysis();to.push(this.inkSnapshot());const snapshot=from.pop();this.doc.strokes=snapshot.strokes;this.doc.selection=snapshot.selection;this.selectionOrigin=snapshot.origin;this.inkBaseSelection=snapshot.base;this.answerDirty=true;this.queueSave();this.render();this.renderAnswers();this.paintPreview();this.scheduleAnalysis(650,true);}
        path(points,close=false){const c=this.ctx;c.beginPath();points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));if(close)c.closePath();}
        stroke(s){const c=this.ctx;c.save();c.globalAlpha=s.tool==='marker'?.33:1;c.strokeStyle=s.color;c.fillStyle=s.color;c.lineWidth=s.width;c.lineCap='round';c.lineJoin='round';this.path(s.points);c.stroke();if(s.points.length===1){c.beginPath();c.arc(...s.points[0],s.width/2,0,Math.PI*2);c.fill();}c.restore();}
        render(){const c=this.ctx;c.clearRect(0,0,this.canvas.width,this.canvas.height);if(!this.doc)return;this.doc.strokes.forEach(s=>this.stroke(s));const g=this.gesture;if(g&&['pen','marker'].includes(g.tool))this.stroke(g);c.save();c.strokeStyle='#9274ff';c.fillStyle='#b8aaff22';c.lineWidth=Math.max(2,this.canvas.width/450);c.setLineDash([c.lineWidth*3,c.lineWidth*2]);const s=this.pendingLasso||this.doc.selection;if(s){if(s.shape==='lasso'){this.path(s.points,true);c.fill('evenodd');c.stroke();}else{const [x,y,r,b]=s.bounds;c.strokeRect(x,y,r-x,b-y);}if(s.anchor){c.beginPath();c.arc(...s.anchor,6,0,Math.PI*2);c.stroke();}}if(g){if(g.tool==='rect'){const a=g.points[0],b=g.points.at(-1);c.strokeRect(...a,b[0]-a[0],b[1]-a[1]);}else if(g.tool==='lasso'){this.path(g.points);c.stroke();}else if(g.tool==='pointer'){c.setLineDash([]);c.beginPath();c.arc(...g.points.at(-1),12,0,Math.PI*2);c.stroke();}}c.restore();$('mp-close-lasso').hidden=!this.pendingLasso;this.updateMetadata();$('mp-undo').disabled=!this.undoStack.length;$('mp-redo').disabled=!this.redoStack.length;}
        renderAnswers(){const root=$('mp-answers');root.replaceChildren();if(this.answerDirty)return;for(const q of (this.doc?.queries||[]).filter(q=>q.revision===this.doc.revision&&this.doc.selection&&q.selection?.shape===this.doc.selection.shape&&['bounds','points','anchor'].every(k=>JSON.stringify(q.selection[k])===JSON.stringify(this.doc.selection[k]))).slice(-5)){const card=document.createElement('p');card.className='mp-answer';card.textContent=q.response||q.error||(q.state==='running'?'Analizando…':'Interrumpido; vuelve a preguntar.');card.title='Captura '+q.source_id.slice(0,6)+' · revisión '+q.revision;root.append(card);}}
        route(){const p=A.companion.data.prefs;return p.visionConnection&&p.visionModel?
            {selection_mode:'manual',provider:p.visionConnection,model:p.visionModel}:
            {selection_mode:p.selection_mode||'manual',provider:p.apiConnection||(p.provider==='bridge'?'':p.provider)||'',model:p.model||''};}
        hasVision(){
            const routes=this.capabilities?.vision||[],r=this.route();
            if(r.selection_mode!=='manual')return routes.length>0;
            return routes.some(p=>(!r.provider||p.name===r.provider)&&(!r.model||p.model===r.model));
        }
        updateControls(){
            if(!$('mp-live'))return;
            const live=this.live&&!this.livePaused;
            const more=$('mp-more-toggle'),mode=this.live?(this.livePaused?'en directo pausado':'en directo'):'manual';
            more.querySelector('span').textContent='Más';more.title='Más herramientas · análisis '+mode;more.setAttribute('aria-label',more.title);more.dataset.state=this.live?(this.livePaused?'paused':'live'):'idle';
            $('mp-live').setAttribute('aria-pressed',String(this.live));
            $('mp-pause').hidden=!this.live;$('mp-pause').textContent=this.livePaused?'Reanudar':'Pausar';
            $('mp-stop-analysis').hidden=!this.analysisPending;
            $('mp-capture').disabled=this.working;$('mp-ask').disabled=this.working;
            $('mp-history-preview').hidden=!this.historyMode;
            $('mp-live-status').textContent=this.analysisPending?'Analizando · puedes seguir dibujando':this.livePaused?'Directo en pausa':live?'Directo · al seleccionar o dibujar':'Manual · pulsa Preguntar';
            $('mp-live-status').dataset.state=this.analysisPending?'running':live?'live':'idle';
            $('mp-vision-missing').hidden=!this.capabilities||this.hasVision();
            this.updateMetadata();if(this.active){this.positionWidget();this.syncInput();}
        }
        updateMetadata(){
            const d=this.doc,r=this.route(),q=!this.answerDirty?d?.queries?.findLast(item=>item.revision===d.revision&&item.state==='completed'):null;
            const connection=q?.provider?.name||r.provider||(r.selection_mode==='manual'?'Conexión seleccionada':'Selección automática');
            const model=q?.provider?.model||r.model;
            const capture=d?`${this.historyMode?'Captura guardada':'Imagen capturada'} · ${new Date(d.source.captured_at*1000).toLocaleString()} · ${d.source.width} × ${d.source.height}`:'Sin captura actual';
            $('mp-meta').textContent=capture+'\n'+connection+(model?' · '+model:'');
        }
        cancelQuery(job){
            if(!job?.id||!job.source_id)return Promise.resolve();
            this.cancelChain=this.cancelChain.catch(()=>{}).then(()=>api('cancel',{id:job.source_id,query_id:job.id})).catch(e=>{
                if(this.active)this.status('La cancelación no se pudo confirmar. La respuesta anterior no se mostrará. '+String(e.message||e));
            });return this.cancelChain;
        }
        cancelAnalysis(){
            clearTimeout(this.liveTimer);this.liveTimer=null;++this.analysisEpoch;
            const job=this.analysisJob,wasPending=this.analysisPending;this.analysisJob=null;this.analysisPending=false;this.queries.clear();if(wasPending&&this.summaryBubbleMode)this.clearSummaryBubble(true);
            if(job)void this.cancelQuery(job);this.updateControls();return this.analysisEpoch;
        }
        scheduleAnalysis(delay=650,fresh=true){
            clearTimeout(this.liveTimer);this.liveTimer=null;
            if(!this.live||this.livePaused||this.historyMode||!this.active||!this.doc?.selection)return;
            if(!this.hasVision()){this.livePaused=true;this.updateControls();this.status('Configura un modelo con visión para activar el análisis en directo.');return;}
            const epoch=this.analysisEpoch;
            this.liveTimer=setTimeout(()=>{this.liveTimer=null;if(epoch===this.analysisEpoch&&!this.gesture)void this.ask({fresh});},delay);
        }
        paintPreview(){
            if(!this.historyMode||!this.previewImage||!this.doc)return;
            const canvas=$('mp-preview-canvas'),s=this.doc.source,scale=Math.min(1,900/s.width);canvas.width=Math.round(s.width*scale);canvas.height=Math.round(s.height*scale);
            const c=canvas.getContext('2d');c.drawImage(this.previewImage,0,0,canvas.width,canvas.height);c.scale(scale,scale);
            for(const stroke of this.doc.strokes){c.save();c.globalAlpha=stroke.tool==='marker'?.33:1;c.strokeStyle=stroke.color;c.fillStyle=stroke.color;c.lineWidth=stroke.width;c.lineCap=c.lineJoin='round';c.beginPath();stroke.points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.stroke();if(stroke.points.length===1){c.beginPath();c.arc(...stroke.points[0],stroke.width/2,0,Math.PI*2);c.fill();}c.restore();}
        }
        async ask({fresh=true}={}){
            if(!this.active||!this.doc?.selection)return this.status('Selecciona o marca una región antes de preguntar.');
            if(!this.hasVision()){this.livePaused=this.live;this.updateControls();return this.status('El modelo seleccionado no tiene visión disponible. Revisa Ajustes de conexión.');}
            const epoch=this.cancelAnalysis(),session=this.generation,userQuestion=$('mp-question').value.trim()||'Explica el contenido de toda la región seleccionada. Ignora el cursor del ratón y cualquier indicador de puntero. Responde de forma clara y breve.',question=userQuestion+'\n\nEmpieza con «Resumen:» y una síntesis en una frase de máximo 24 palabras; después da los detalles necesarios bajo «Detalle:».',route=this.route();
            this.analysisPending=true;this.updateControls();this.showPendingBubble();
            const current=()=>this.active&&this.generation===session&&this.analysisEpoch===epoch;
            const setup=this.analysisSetup.catch(()=>{}).then(async()=>{
                await this.cancelChain;if(!current())return null;
                if(fresh&&!this.historyMode){
                    const selection=clone(this.doc.selection);
                    if(!await this.run(()=>this.capture({isCurrent:current}))||!current())return null;
                    this.doc.selection=selection;this.queueSave();this.render();
                }
                await this.flush();if(!current())return null;
                const d=this.doc,revision=d.revision;
                this.status('Analizando tu selección…');
                const request_id=crypto.randomUUID().replace(/-/g,'');
                this.analysisJob={id:request_id,source_id:d.id};
                const q=await api('start',{id:d.id,revision,question,...route,request_id});
                if(q?.id!==request_id||q.source_id!==d.id)throw Error('El servicio devolvió un análisis sin identidad válida.');
                if(!current()){await this.cancelQuery(q);return null;}
                this.analysisJob=q;this.queries.add(q.id);return {d,revision,q};
            });
            this.analysisSetup=setup.then(()=>{},()=>{});
            try{
                const job=await setup;if(!job){if(current()&&this.summaryBubbleMode)this.clearSummaryBubble(true);return;}
                let q=job.q;const deadline=Date.now()+80000;
                while(q.state==='running'&&current()){
                    if(Date.now()>deadline)throw Error('El análisis superó el tiempo de espera. Puedes volver a intentarlo.');
                    await new Promise(resolve=>setTimeout(resolve,350));if(!current())return;
                    q=await api('query',{id:job.d.id,query_id:q.id});
                    if(q.id!==job.q.id||q.source_id!==job.d.id||q.revision!==job.revision)throw Error('El resultado no corresponde a esta selección.');
                }
                if(!current()||this.doc!==job.d||job.d.revision!==job.revision)return;
                if(!['completed','failed','cancelled','interrupted'].includes(q.state))throw Error('Estado de análisis desconocido.');
                if(!job.d.queries.some(item=>item.id===q.id))job.d.queries.push(q);
                this.answerDirty=false;this.renderAnswers();
                if(q.state==='completed'){this.status('Respuesta lista. Puedes preguntar más o marcar otra zona.');this.showSummaryBubble(q.response);}
                else {if(this.live)this.livePaused=true;this.clearSummaryBubble(true);this.status(q.error||'Análisis detenido. Puedes volver a intentarlo.');}
            }catch(e){if(current()){if(this.analysisJob)void this.cancelQuery(this.analysisJob);if(this.live)this.livePaused=true;this.clearSummaryBubble(true);this.status(String(e.message||e));}}
            finally{if(current()){this.analysisPending=false;this.analysisJob=null;this.queries.clear();this.updateControls();}}
        }
        async export(kind){if(!this.doc)throw Error('Captura una pantalla primero.');await this.flush();this.status('Verificando exportación…');const r=await api('export',{id:this.doc.id,revision:this.doc.revision,kind,directory:$('mp-directory').value,name:$('mp-name').value+(kind==='original'?'-original':'-anotado')});$('mp-export').textContent=`Guardado y verificado: ${r.path}\nSHA256 ${r.sha256}`;this.status('PNG guardado y verificado.');}
    }
    A.magicPenGeometry={sourcePoint,desktopPoint};
    A.magicPen=new MagicPen();
})();
