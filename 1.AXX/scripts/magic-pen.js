/* Desktop ink uses the resident surface; clean snapshots remain immutable evidence. */
(() => {
    'use strict';
    const A = window.Axx, $ = id => document.getElementById(id);
    const api = (op, body = {}) => A.backendRequest('POST', '/axx-api/pen/' + op, body);
    const spatialApi = (op, body = {}) => A.backendRequest('POST', '/axx-api/spatial/session/' + op, body);
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
    // Labels for the backend-validated PresentationPlan v1 (backend/presentation_plan.py); rendered with textContent only.
    const BASIS={observed:'Observado',documented:'Documentado',inferred:'Inferido',assumed:'Supuesto'},FIDELITY={illustrative:'Ilustrativo',conceptual:'Conceptual',technical:'Técnico'};
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
                <div class="mp-spatial-options"><label>Modelo visual <select id="mp-spatial-provider" aria-label="Proveedor y modelo visual"><option value="">Elige proveedor y modelo</option></select></label><label>Esfuerzo <select id="mp-spatial-effort" aria-label="Esfuerzo del modelo"><option value="auto">Auto</option></select></label><button id="mp-spatial-verify" type="button" title="Envía una imagen sintética al proveedor elegido">Probar conexión</button><button id="mp-spatial-create" type="button">Visualizar selección</button></div><div id="mp-spatial-status" class="mp-spatial-status" role="status" aria-live="polite"></div>
                <div class="mp-composer"><textarea id="mp-question" rows="1" maxlength="4000" placeholder="Escribe tu pregunta… (Intro para enviar)" aria-label="Pregunta o instrucción sobre la selección" aria-describedby="mp-question-help"></textarea><button id="mp-voice" class="mp-icon-button" title="Dictar pregunta" aria-label="Dictar pregunta">${icon('mic')}</button><button id="mp-ask" class="mp-icon-button" title="Enviar pregunta" aria-label="Enviar pregunta">${icon('send')}</button></div><small id="mp-question-help" class="mp-composer-help">Intro envía · Mayús+Intro añade una línea</small>
                <p id="mp-status" role="status" aria-live="polite">Elige una pantalla y pulsa Capturar.</p><div id="mp-answers" aria-live="polite"></div>
                <details class="mp-save-section"><summary>${icon('save')}Guardar e historial<span>PNG + tinta editable</span></summary><label>Carpeta de destino<input id="mp-directory" type="text"></label><label>Nombre<input id="mp-name" type="text" value="Captura-Axx" maxlength="100"></label><div class="mp-row"><button id="mp-original">Guardar original</button><button id="mp-annotated">Guardar anotado</button><button id="mp-retry">Guardar borrador</button></div><p id="mp-export" role="status"></p><label>Capturas anteriores<select id="mp-history"><option value="">Elige una captura</option></select></label></details><p id="mp-capability" class="mp-muted"></p>`;
            document.body.append(view); this.view = view; this.canvas = $('mp-canvas'); this.ctx = this.canvas.getContext('2d');
            this.mountDesktop();
            const style = document.createElement('link'); style.rel='stylesheet';style.href='scripts/magic-pen.css';document.head.append(style);
            $('mp-capture').onclick = () => {this.cancelAnalysis();void this.run(()=>this.capture());};
            $('mp-ask').onclick = () => { void this.askFromComposer(); };
            $('mp-spatial-provider').onchange=()=>this.spatialProviderChanged();
            $('mp-spatial-effort').onchange=()=>this.saveSpatialPreferences();
            $('mp-spatial-verify').onclick=()=>{void this.verifySpatial();};
            $('mp-spatial-create').onclick=()=>{void this.spatialAction('diagram');};
            $('mp-question').oninput=()=>{const input=$('mp-question');input.style.height='42px';input.style.height=Math.min(96,input.scrollHeight)+'px';};
            $('mp-question').onkeydown = e => { if(e.key==='Enter'&&!e.shiftKey) {e.preventDefault();e.stopPropagation();this.askFromComposer();} };
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
            this.voiceOwner = {state:'idle',onFinal:text=>this.onDictated(text),onError:text=>this.status(text),onState:()=>{$('mp-voice').innerHTML=this.voiceOwner.state==='listening'?'<span aria-hidden="true">■</span>':this.icon('mic');}};
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
            this.widget=document.createElement('aside');this.widget.addEventListener('pointerdown',e=>this.leaseFocus(e.target));this.widget.id='mp-widget';this.widget.setAttribute('aria-label','Explicación de la selección');this.widget.tabIndex=-1;this.widget.hidden=true;
            this.widget.innerHTML='<div class="mp-widget-head"><span class="mp-head-mark" aria-hidden="true">'+this.icon('pen')+'</span><span class="mp-head-copy"><span><strong>Magic Pen</strong><small>LECTURA VISUAL</small></span></span><span id="mp-summary-spinner" class="mp-summary-spinner" hidden aria-hidden="true"></span><button id="mp-hide-answer" aria-label="Ocultar explicación">×</button></div><section id="mp-summary-bubble" class="mp-summary-bubble" hidden><div class="mp-summary-kicker"><span id="mp-summary-label">Lo esencial</span></div><p id="mp-summary-text" role="status" aria-live="polite"></p><p id="mp-summary-voice-status" role="status" aria-live="polite" hidden></p><div class="mp-summary-actions"><button id="mp-summary-expand" type="button">Ver explicación</button><button id="mp-summary-visual" type="button" aria-label="Explicar visualmente" title="Explicar visualmente como diagrama de pasos">Visualizar</button><button id="mp-summary-listen" type="button" aria-label="Escuchar resumen" title="Escuchar resumen">'+this.icon('voice')+'</button></div></section><figure id="mp-history-preview" hidden><canvas id="mp-preview-canvas" aria-label="Vista previa de la captura guardada"></canvas><figcaption>Captura guardada · no es el escritorio actual</figcaption><button id="mp-back-desktop" type="button">Volver al escritorio</button></figure><div id="mp-vision-missing" hidden><p>El modelo seleccionado no tiene análisis visual disponible.</p><button id="mp-configure" type="button">Ajustes de conexión</button></div>';
            const spatial=this.view.querySelector('.mp-spatial-options'),spatialStatus=this.view.querySelector('#mp-spatial-status'),create=spatial.querySelector('#mp-spatial-create'),verify=spatial.querySelector('#mp-spatial-verify'),settings=document.createElement('details'),settingsTitle=document.createElement('summary'),settingsBody=spatial;
            settings.className='mp-spatial-settings';settingsTitle.innerHTML='<span>Proveedor y calidad</span><small>POR SESIÓN</small>';settings.append(settingsTitle,settingsBody,verify);
            const chatDock=document.createElement('div');chatDock.className='mp-chat-dock';const spatialActions=document.createElement('div');spatialActions.className='mp-spatial-actions';spatialActions.setAttribute('role','group');spatialActions.setAttribute('aria-label','Formas de explicar la selección');
            const modeCaption=document.createElement('p');modeCaption.id='mp-model-caption';modeCaption.className='mp-model-caption';modeCaption.setAttribute('aria-live','polite');
            const locate=document.createElement('button'),model=document.createElement('button');locate.type=model.type='button';locate.id='mp-spatial-locate';model.id='mp-spatial-model';locate.innerHTML=this.icon('point')+'<span><strong>Señalar</strong><small>En la captura</small></span>';model.innerHTML=this.icon('capture')+'<span><strong>Modelo 3D</strong><small>Vista conceptual</small></span>';create.innerHTML=this.icon('rect')+'<span><strong>Diagrama</strong><small>Pasos y relaciones</small></span>';
            locate.title='Señalar en la captura lo que describes en la pregunta';create.title='Explicar la selección con un diagrama';model.title='Crear una vista 3D conceptual de la selección';
            locate.onclick=()=>{void this.spatialAction('locate');};model.onclick=()=>{void this.spatialAction('model');};spatialActions.append(locate,create,model);chatDock.append(modeCaption,spatialActions,this.view.querySelector('.mp-composer'),this.view.querySelector('#mp-question-help'));
            for(const selector of ['#mp-answers','#mp-status'])this.widget.append(this.view.querySelector(selector));
            this.widget.append(chatDock,settings,spatialStatus,this.view.querySelector('.mp-save-section'));
            const saved=this.widget.querySelector('.mp-save-section');saved.querySelector('summary').after($('mp-meta'));saved.append($('mp-capability'));
            const source=this.view.querySelector('.mp-source-row');this.widget.querySelector('.mp-save-section').append(source);source.hidden=true;
            this.stage=document.createElement('section');this.stage.id='mp-spatial-stage';this.stage.hidden=true;this.stage.setAttribute('aria-label','Modelo 3D flotante');
            this.stage.innerHTML='<div class="mp-stage-top"><span>MODELO CONCEPTUAL</span><button type="button" class="mp-stage-move" aria-label="Mover modelo 3D" title="Arrastra para mover el modelo">Mover modelo</button></div><div class="mp-stage-viewport"></div><div class="mp-stage-bottom"><span>Arrastra para girar · rueda para acercar · toca una pieza</span><button type="button" class="mp-stage-center" aria-label="Centrar modelo 3D">Centrar</button></div>';
            this.stage.querySelector('.mp-stage-center').onclick=()=>{this.stage.style.removeProperty('left');this.stage.style.removeProperty('top');this.syncInput();};
            const topBar=this.stage.querySelector('.mp-stage-top'),handle=this.stage.querySelector('.mp-stage-move');let moving=null;
            const startDrag=e=>{if(e.target.tagName==='BUTTON'&&e.target!==handle)return;e.preventDefault();const r=this.stage.getBoundingClientRect();moving={x:e.clientX-r.left-r.width/2,y:e.clientY-r.top-r.height/2};(e.target.setPointerCapture?e.target:handle).setPointerCapture?.(e.pointerId);};
            handle.addEventListener('pointerdown',startDrag);topBar.addEventListener('pointerdown',startDrag);
            const onDragMove=e=>{if(!moving)return;const w=this.stage.offsetWidth,h=this.stage.offsetHeight;this.stage.style.left=Math.max(w/2,Math.min(innerWidth-w/2,e.clientX-moving.x))+'px';this.stage.style.top=Math.max(h/2,Math.min(innerHeight-h/2,e.clientY-moving.y))+'px';this.syncInput();};
            handle.addEventListener('pointermove',onDragMove);topBar.addEventListener('pointermove',onDragMove);
            handle.addEventListener('keydown',e=>{const delta={ArrowLeft:[-20,0],ArrowRight:[20,0],ArrowUp:[0,-20],ArrowDown:[0,20]}[e.key];if(!delta)return;e.preventDefault();const r=this.stage.getBoundingClientRect();this.stage.style.left=Math.max(r.width/2,Math.min(innerWidth-r.width/2,r.left+r.width/2+delta[0]))+'px';this.stage.style.top=Math.max(r.height/2,Math.min(innerHeight-r.height/2,r.top+r.height/2+delta[1]))+'px';this.syncInput();});
            for(const event of ['pointerup','pointercancel','lostpointercapture']){handle.addEventListener(event,()=>{moving=null;});topBar.addEventListener(event,()=>{moving=null;});}
            this.view.append(this.canvas,this.stage,this.toolbar,this.widget);
            this.caption=document.createElement('div');this.caption.className='mp-caption';this.caption.hidden=true;this.caption.setAttribute('role','status');this.caption.setAttribute('aria-live','polite');this.view.append(this.caption);
            this.widget.addEventListener('animationend',e=>{if(e.target===this.widget&&e.animationName==='mp-bubble-in'&&this.active)this.syncInput();});
            for(const selector of ['.mp-modebar','.mp-stage','.mp-selection-row'])this.view.querySelector(selector).hidden=true;
            this.canvas.setAttribute('aria-label','Escritorio: selecciona o marca; Escape para salir');
            const option=new Option('Usar escritorio','interact');$('mp-tool').append(option);
            const reopen=document.createElement('button');reopen.id='mp-show-answer';reopen.type='button';reopen.className='mp-show-answer';reopen.hidden=true;reopen.innerHTML=this.icon('voice')+'<span>Ver explicación</span>';reopen.setAttribute('aria-label','Volver a la explicación');$('mp-more-panel').append(reopen);
            $('mp-done').onclick=()=>this.close();$('mp-hide-answer').onclick=()=>this.hideAnswer();reopen.onclick=()=>{this.closeTools();this.openAnswer();};
            $('mp-summary-expand').onclick=()=>this.openAnswer();$('mp-summary-visual').onclick=()=>{void this.spatialAction('diagram');};$('mp-summary-listen').onclick=()=>this.readSummary();
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
            this.clearSummaryBubble(true);this.summaryBubbleMode=true;this.widget.classList.add('mp-bubble-mode');$('mp-summary-bubble').hidden=false;$('mp-summary-label').textContent='Analizando';$('mp-summary-text').textContent='Estoy revisando esa zona…';$('mp-summary-spinner').hidden=false;$('mp-summary-listen').hidden=true;$('mp-summary-expand').hidden=true;$('mp-summary-visual').hidden=true;this.showWidget();
        }
        showSummaryBubble(response){
            this.summaryText=conciseSummary(response);if(!this.summaryText){this.clearSummaryBubble(true);this.status('La respuesta llegó vacía. Puedes volver a preguntar.');return;}
            this.clearSummaryBubble(false);this.answerAvailable=true;this.summaryBubbleMode=true;this.widget.classList.add('mp-bubble-mode');$('mp-summary-bubble').hidden=false;$('mp-summary-label').textContent='Lo esencial';$('mp-summary-text').textContent=this.summaryText;$('mp-summary-spinner').hidden=true;$('mp-summary-voice-status').hidden=true;$('mp-summary-listen').hidden=false;$('mp-summary-expand').hidden=false;$('mp-summary-visual').hidden=false;$('mp-show-answer').hidden=true;this.showWidget();
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
            if(!this.stage.hidden&&!this.summaryBubbleMode){
                const narrow=innerWidth<=900;if(narrow)this.widget.style.maxHeight=Math.max(120,Math.min(220,toolbar.top-24))+'px';
                this.widget.style.left=Math.max(12,innerWidth-this.widget.offsetWidth-12)+'px';
                this.widget.style.top=(narrow?Math.max(12,toolbar.top-this.widget.offsetHeight-12):Math.min(64,Math.max(12,toolbar.top-this.widget.offsetHeight-12)))+'px';
                this.syncInput();return;
            }
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
        async refresh(){
            const data=await api('status');this.capabilities=data.capabilities;
            $('mp-source').replaceChildren(...data.monitors.map((m,i)=>new Option(`Pantalla ${i+1} · ${m.width} × ${m.height}`,m.id)));
            $('mp-history').replaceChildren(new Option('Elige una captura',''),...data.history.map(d=>new Option(new Date(d.source.captured_at*1000).toLocaleString()+' · '+d.id.slice(0,6),d.id)));
            if(!$('mp-directory').value)$('mp-directory').value=data.capabilities.export_directory;
            $('mp-capability').textContent=(data.capabilities.vision.length?'Visión · '+data.capabilities.vision.map(p=>p.name).join(', '):'Análisis visual no configurado')+' · '+data.capabilities.ocr_message;
            this.setupSpatialOptions(data.capabilities);
            try{this.readiness=await A.backendRequest('GET','/axx-api/feature-readiness?feature_id=spatial_intelligence');}catch{this.readiness=null;}
            this.renderSpatialReadiness();
            this.updateControls();return data;
        }
        setupSpatialOptions(capabilities){
            const saved=(()=>{try{return JSON.parse(localStorage.getItem('axx.magicpen.spatial')||'{}');}catch{return {};}})(),prefs=A.companion.data.prefs||{};
            const entries=[...(capabilities.vision||[]),...(capabilities.codex_vision||[])];
            this.spatialProviders=new Map(entries.map(p=>[encodeURIComponent(p.name)+'::'+encodeURIComponent(p.model),p]));
            const select=$('mp-spatial-provider'),options=[new Option('Elige proveedor y modelo',''),...entries.map(p=>new Option((p.name==='@codex'?'ChatGPT/Codex':p.name)+' · '+p.model+' · '+(p.spatial_3d?'2D + 3D':'2D'),encodeURIComponent(p.name)+'::'+encodeURIComponent(p.model)))];
            select.replaceChildren(...options);
            const preferred=saved.provider&&saved.model?[saved.provider,saved.model]:[prefs.visionConnection||prefs.apiConnection||'',prefs.visionModel||prefs.model||''];
            const selected=[...this.spatialProviders].find(([,p])=>p.name===preferred[0]&&p.model===preferred[1])?.[0]||
                (entries.length===1?[...this.spatialProviders.keys()][0]:'');
            select.value=selected||'';this.spatialProviderChanged(saved.effort||'auto');this.renderSpatialReadiness();
        }
        spatialProviderChanged(preferredEffort){
            const key=$('mp-spatial-provider').value,provider=this.spatialProviders?.get(key),effort=$('mp-spatial-effort');
            const previous=preferredEffort||effort.value||'auto',levels=['auto',...(provider?.efforts||[]).filter(level=>['low','medium','high','xhigh','max'].includes(level))];
            effort.replaceChildren(...levels.map(level=>new Option(level==='auto'?'Auto':level,level)));
            effort.value=levels.includes(previous)?previous:'auto';
            const model=$('mp-spatial-model'),caption=$('mp-model-caption');model.disabled=!provider?.spatial_3d;
            model.title=provider?.spatial_3d?'Crear una vista 3D conceptual de la selección':'Elige ChatGPT/Codex o Claude con visión para crear una vista 3D';
            caption.textContent=provider?(provider.spatial_3d?'Modelo avanzado · señala, dibuja y crea 3D conceptual':'Modelo visual 2D · señala y dibuja diagramas; el 3D requiere un modelo avanzado'):'Elige un modelo visual para señalar, diagramar o crear 3D.';
            this.saveSpatialPreferences();this.renderSpatialReadiness();
        }
        saveSpatialPreferences(){
            const provider=this.spatialProviders?.get($('mp-spatial-provider').value);
            try{localStorage.setItem('axx.magicpen.spatial',JSON.stringify({provider:provider?.name||'',model:provider?.model||'',effort:$('mp-spatial-effort').value||'auto'}));}catch{}
        }
        spatialRoute(){
            const provider=this.spatialProviders?.get($('mp-spatial-provider').value);
            return provider?{provider:provider.name,model:provider.model,selection_mode:'manual',effort:$('mp-spatial-effort').value||'auto'}:null;
        }
        setSpatialStatus(message,state='info',detail=''){
            const node=$('mp-spatial-status');if(!node)return;node.replaceChildren();node.dataset.state=state;
            const text=document.createElement('span');text.className='mp-spatial-status-text';text.textContent=message;node.append(text);
            if(detail){const disclosure=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
                summary.textContent='Detalles técnicos';pre.textContent=detail.slice(0,1600);disclosure.append(summary,pre);node.append(disclosure);}
        }
        renderSpatialReadiness(){
            const node=$('mp-spatial-status');if(!node)return;const route=this.spatialRoute();
            if(!route){this.setSpatialStatus('Elige un proveedor visual con permiso existente. AXX no cambia proveedor automáticamente.');return;}
            const provider=this.readiness?.providers?.find(item=>item.name===route.provider&&item.model===route.model);
            this.setSpatialStatus(provider?.status==='ready'?'Modelo visual verificado para imagen y plan '+(provider.spatial_3d?'2D/3D.':'2D.'):
                'Modelo sin verificar. «Probar conexión» envía una imagen sintética para comprobar su respuesta visual.',provider?.status==='ready'?'success':'info');
        }
        async verifySpatial(){
            const route=this.spatialRoute();if(!route){const message='Elige primero un proveedor y modelo visual.';this.setSpatialStatus(message);return this.status(message);}
            const button=$('mp-spatial-verify'),label=button.textContent;button.disabled=true;button.setAttribute('aria-busy','true');button.textContent='Verificando…';
            this.setSpatialStatus('Comprobando imagen y formato de respuesta con '+(route.provider==='@codex'?'ChatGPT/Codex':route.provider)+'…','checking');
            this.status('Comprobando conexión visual…');
            try{const result=await A.backendRequest('POST','/axx-api/feature-readiness/verify',{feature_id:'spatial_intelligence',provider:route.provider,model:route.model,effort:route.effort});
                this.status('Conexión verificada para '+result.provider+' · '+result.model+'.');
                this.capabilities=(await api('status')).capabilities;this.setupSpatialOptions(this.capabilities);
                this.readiness=await A.backendRequest('GET','/axx-api/feature-readiness?feature_id=spatial_intelligence');this.renderSpatialReadiness();
            }catch(e){const detail=String(e?.message||e||'Error no identificado').slice(0,1600),schemaError=route.provider==='@codex'&&/codex_output_schema/i.test(detail)&&/schema\.required|invalid_json_schema/i.test(detail);
                const message=schemaError?'Codex rechazó el formato de respuesta estructurada. Revisa los detalles técnicos y vuelve a probar.':'No se pudo verificar la conexión. Revisa los detalles técnicos e inténtalo de nuevo.';
                this.setSpatialStatus(message,'error',detail);this.status('');}
            finally{button.disabled=false;button.removeAttribute('aria-busy');button.textContent=label;}
        }
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
        session(active){
            const leased=!active&&this.focusLeased;if(!active)this.focusLeased=false;
            if(A.isNative())this.sessionChain=this.sessionChain.catch(()=>{}).then(()=>A.nativeInvoke('magic_pen_session',{active})).then(()=>leased&&$('panel')?.hidden!==false&&A.app.bridge.action('close_panel')).catch(e=>this.status(String(e)));
        }
        // The resident window is non-focusable so opening Magic Pen never closes another app's menus; typing takes the panels' focus lease on first touch.
        leaseFocus(target){
            if(!A.isNative()||!this.active)return;
            const focus=()=>{if(this.active&&this.focusLeased&&this.widget.contains(target)&&target.matches?.('input,textarea')&&!target.disabled)target.focus({preventScroll:true});};
            if(this.focusLeased){this.sessionChain=this.sessionChain.catch(()=>{}).then(focus);return;}
            this.focusLeased=true;
            this.sessionChain=this.sessionChain.catch(()=>{}).then(()=>A.app.bridge.action('open_panel')).then(focus).catch(e=>{this.focusLeased=false;this.status(String(e.message||e));});
        }
        suspend(){this.saveViewNow();this.closeTools();this.clearSummaryBubble(true);this.cancelAnalysis();this.disposeScene();if(this.player)this.player.queryId=null;this.guide=null;this.session(false);this.active=false;this.root.hidden=true;this.state='closed';this.cancelGesture();this.setInput(false);this.voiceOwner.stop?.();++this.generation;this.working=false;this.updateControls();}
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
                void this.run(async()=>{if(!await this.capture())return;this.doc.selection=selection;this.selectionChanged();this.status(this.live?'Selección lista.':'Selección lista. Escribe tu pregunta y pulsa enviar.');this.scheduleAnalysis(0,false);});return;
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
                this.answerDirty=true;this.queueSave();this.status(this.live&&!this.livePaused?'Analizaré esta zona cuando termines de marcar.':'Marcas listas. Escribe tu pregunta y envíala.');this.renderAnswers();this.scheduleAnalysis(650,true);
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
        render(){const c=this.ctx;c.clearRect(0,0,this.canvas.width,this.canvas.height);if(!this.doc)return;this.doc.strokes.forEach(s=>this.stroke(s));const g=this.gesture;if(g&&['pen','marker'].includes(g.tool))this.stroke(g);c.save();c.strokeStyle='#9274ff';c.fillStyle='#b8aaff22';c.lineWidth=Math.max(2,this.canvas.width/450);c.setLineDash([c.lineWidth*3,c.lineWidth*2]);const s=this.pendingLasso||this.stage.hidden&&this.doc.selection;if(s){if(s.shape==='lasso'){this.path(s.points,true);c.fill('evenodd');c.stroke();}else{const [x,y,r,b]=s.bounds;c.strokeRect(x,y,r-x,b-y);}if(s.anchor){c.beginPath();c.arc(...s.anchor,6,0,Math.PI*2);c.stroke();}}if(g){if(g.tool==='rect'){const a=g.points[0],b=g.points.at(-1);c.strokeRect(...a,b[0]-a[0],b[1]-a[1]);}else if(g.tool==='lasso'){this.path(g.points);c.stroke();}else if(g.tool==='pointer'){c.setLineDash([]);c.beginPath();c.arc(...g.points.at(-1),12,0,Math.PI*2);c.stroke();}}c.restore();this.paintGuide();this.paintVisual();$('mp-close-lasso').hidden=!this.pendingLasso;this.updateMetadata();$('mp-undo').disabled=!this.undoStack.length;$('mp-redo').disabled=!this.redoStack.length;}
        renderAnswers(){const root=$('mp-answers');root.replaceChildren();if(this.answerDirty){this.disposeScene();return;}const current=this.presentationQuery(),guided=this.guideQuery();for(const q of (this.doc?.queries||[]).filter(q=>q.revision===this.doc.revision&&this.doc.selection&&q.selection?.shape===this.doc.selection.shape&&['bounds','points','anchor'].every(k=>JSON.stringify(q.selection[k])===JSON.stringify(this.doc.selection[k]))).slice(-5)){const visual=q===current||q===guided,card=q===current?this.presentationCard(q):q===guided?this.guideCard(q):document.createElement('p');card.classList.add('mp-answer');if(!visual)card.textContent=(q.format==='presentation'?q.presentation?.summary||q.error:q.format==='guide'?q.guide?.goal||q.error:q.response||q.error)||(q.state==='running'?'Analizando…':'Interrumpido; vuelve a preguntar.');card.title='Captura '+q.source_id.slice(0,6)+' · revisión '+q.revision;root.append(card);}this.queueView();}
        presentationQuery(){
            const d=this.doc,last=this.answerDirty?null:d?.queries?.findLast(q=>q.revision===d.revision&&q.state==='completed');
            return last?.presentation?last:null;
        }
        presentationCard(q){
            if(this.player?.queryId!==q.id){
                const previous=this.player,inherit=q.base_query_id===previous?.queryId,state=q.view_state,ids=new Set(q.presentation.scene?.objects.map(o=>o.id)||[]);
                const view=state?.camera||(inherit?previous?.scene?.getView():null),picked=state?.selected||(inherit?previous?.picked:null);
                this.stopPresentation();
                if(inherit&&previous?.scene&&q.presentation.scene){previous.scene.update(q.presentation.scene);previous.queryId=q.id;previous.index=Math.min(previous.index,q.presentation.steps.length-1);previous.picked=ids.has(picked)?picked:null;previous.hidden=new Set([...previous.hidden].filter(id=>ids.has(id)));previous.separated=new Set(previous.scene.getSeparated().filter(id=>ids.has(id)));}
                else{this.disposeScene();this.player={queryId:q.id,index:Math.max(0,state?q.presentation.steps.findIndex(s=>s.id===state.step_id):0),playing:false,timer:null,token:0,spoke:false,
                    exploded:state?.exploded||false,picked:ids.has(picked)?picked:null,overview:state?.overview??!!q.presentation.scene,isolated:state?.isolated||false,
                    hidden:new Set(state?.hidden||[]),separated:new Set(state?.separated||[]),initialView:view};}
            }
            const p=q.presentation,player=this.player,el=(tag,text,className)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(className)n.className=className;return n;};
            const card=el('figure',null,'mp-visual'),head=el('figcaption'),list=el('ol',null,'mp-visual-flow'),controls=el('div',null,'mp-visual-controls');
            head.append(el('strong',p.title),el('small',FIDELITY[p.fidelity]+' · explicación generada, no verificada','mp-visual-fidelity'));card.append(head);
            if(q.answer)card.append(el('p',q.answer,'mp-visual-answer'));
            const diagram=p.diagram||(!p.scene&&p.steps.length>1?{nodes:p.steps.map((step,i)=>({id:'d'+(i+1),label:step.title,step_id:step.id,bounds:[i%2?.55:.07,.06+Math.floor(i/2)*.23,.38,.16]})),edges:p.steps.slice(1).map((_,i)=>({from:'d'+(i+1),to:'d'+(i+2),label:'paso'}))}:null);
            if(diagram){
                const surface=el('div',null,'mp-diagram');card.append(surface);
                if(this.visualModule)this.visualModule.renderDiagram(surface,diagram,p.steps[player.index].id,id=>this.seekPresentation(p.steps.findIndex(s=>s.id===id)));
                else this.loadVisual();
            }
            if(p.overlays&&!this.visualModule)this.loadVisual();
            const button=(label,text,onclick,disabled=false)=>{const b=el('button',text);b.type='button';b.setAttribute('aria-label',label);b.disabled=disabled;b.onclick=onclick;return b;};
            if(p.scene)card.append(this.sceneBlock(p,player,el,button));
            p.steps.forEach((step,i)=>{
                const item=el('li'),ask=el('button','Preguntar');ask.type='button';ask.setAttribute('aria-label','Preguntar sobre el paso '+step.title);
                ask.onclick=()=>{const input=$('mp-question');input.value='Sobre el paso «'+step.title+'»: ';input.focus();};
                if(i===player.index)item.setAttribute('aria-current','step');else if(i>player.index)item.classList.add('mp-step-pending');
                const title=el('button',step.title,'mp-step-title'),meta=el('div',null,'mp-step-meta');title.type='button';title.setAttribute('aria-label','Ir al paso '+(i+1)+': '+step.title);title.onclick=()=>this.seekPresentation(i);meta.append(el('small',BASIS[step.basis],'mp-visual-basis'),ask);
                const sentences=step.body.split(/(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])/).filter(Boolean);
                const bodyWrap=el('div',null,'mp-step-body');
                if(sentences.length>1){const ul=el('ul',null,'mp-step-bullets');for(const s of sentences)ul.append(el('li',s));bodyWrap.append(ul);}
                else bodyWrap.append(el('span',step.body));
                item.append(title,bodyWrap,meta);list.append(item);
            });
            controls.append(button('Paso anterior','‹',()=>this.seekPresentation(player.index-1),player.index===0),
                button(player.playing?'Pausar narración':'Narrar desde este paso',player.playing?'Pausar':'Narrar',()=>{if(player.playing){this.stopPresentation();this.renderAnswers();}else this.playPresentation();}),
                button('Paso siguiente','›',()=>this.seekPresentation(player.index+1),player.index>=p.steps.length-1),
                button('Guíame para hacerlo en la aplicación','Guíame',()=>{void this.ask({fresh:false,format:'guide',base:q.id,question:$('mp-question').value.trim()||'Guíame paso a paso para hacer esto en la aplicación: '+p.title});}),el('span',(player.index+1)+' / '+p.steps.length,'mp-visual-progress'));
            card.append(list,controls);
            if(player.scene){for(const id of player.hidden)player.scene.setHidden(id,true);player.scene.focus(player.picked?[player.picked]:player.overview?[]:p.steps[player.index].focus||[],player.isolated);}
            return card;
        }
        sceneBlock(p,player,el,button){
            // The host survives re-renders so seeking never rebuilds the WebGL context.
            const block=el('div',null,'mp-scene'),objects=new Map(p.scene.objects.map(o=>[o.id,o]));
            block.append(el('small',(p.scene.fidelity==='illustrative'?'Escena ilustrativa':'Escena conceptual')+' · no es una simulación ni geometría exacta','mp-visual-fidelity'));
            if(player.sceneFailed){
                const list=el('ul',null,'mp-scene-fallback');block.append(el('p',player.sceneFailed));
                for(const o of p.scene.objects)list.append(el('li',o.label));block.append(list);return block;
            }
            if(player.qa)block.append(el('small',player.qa.webgl&&player.qa.finite?`Visor local operativo · ${player.qa.objects} piezas · ${player.qa.triangles} triángulos`:'La comprobación local del visor detectó un problema.','mp-visual-fidelity'));
            if(this.stage.hidden){this.stage.hidden=false;this.render();}
            if(!player.sceneHost){
                player.sceneHost=el('div',null,'mp-scene-host');player.sceneHost.append(el('p','Cargando escena 3D…','mp-scene-loading'));
                const fail=reason=>{if(this.player!==player)return;this.disposeScene();player.sceneFailed=reason+' Se muestran los componentes en lista.';this.renderAnswers();};
                import('./spatial-scene.js').then(module=>{
                    if(this.player!==player||!player.sceneHost)return;
                    player.sceneHost.replaceChildren();
                    try{player.scene=module.mountScene(player.sceneHost,p.scene,{reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches,initialView:player.initialView,
                        onPick:id=>{player.picked=id;player.overview=false;this.clearSummaryBubble(false);this.renderAnswers();this.showWidget();this.widget.querySelector('.mp-scene-picked')?.scrollIntoView({block:'nearest'});},onChange:()=>this.queueView(),onLost:()=>fail('Se perdió el contexto gráfico.')});}
                    catch{fail('Este equipo no ofrece WebGL para la escena 3D.');return;}
                    if(player.exploded)player.scene.setExploded(true);for(const id of player.hidden)player.scene.setHidden(id,true);for(const id of player.separated||[])player.scene.setObjectExploded(id,true);player.qa=player.scene.qa();this.renderAnswers();
                },()=>fail('No se pudo cargar el motor 3D.'));
            }
            const tools=el('div',null,'mp-scene-tools'),picked=objects.get(player.picked);
            const explode=button(player.exploded?'Unir piezas':'Vista despiezada',player.exploded?'Unir':'Despiezar',()=>{player.exploded=!player.exploded;player.scene?.setExploded(player.exploded);this.renderAnswers();},!player.scene);
            explode.setAttribute('aria-pressed',String(player.exploded));
            tools.append(explode,button('Ver toda la escena','Ver todo',()=>{player.picked=null;player.overview=true;player.isolated=false;this.renderAnswers();},!player.scene));
            if(picked){
                const hidden=player.hidden.has(picked.id);
                tools.append(button(hidden?'Mostrar '+picked.label:'Ocultar '+picked.label,hidden?'Mostrar':'Ocultar',()=>{
                    if(hidden)player.hidden.delete(picked.id);else player.hidden.add(picked.id);player.scene?.setHidden(picked.id,!hidden);this.renderAnswers();
                },!player.scene),button(player.isolated?'Mostrar todas las piezas':'Aislar '+picked.label,player.isolated?'Mostrar todas':'Aislar',()=>{
                    player.isolated=!player.isolated;player.overview=false;this.renderAnswers();
                },!player.scene));
                const separated=player.scene?.getSeparated().includes(picked.id);
                tools.append(button(separated?'Unir '+picked.label:'Separar '+picked.label,separated?'Unir pieza':'Separar pieza',()=>{player.scene?.setObjectExploded(picked.id,!separated);this.renderAnswers();},!player.scene));
            }
            tools.append(button('Guardar la escena como PNG','PNG',()=>this.run(()=>this.exportScene()),!player.scene));
            tools.append(button('Generar una versión con más detalle técnico','Más detalle',()=>this.ask({fresh:false,format:'presentation',question:'Genera otra versión del modelo 3D de esta selección, con más detalle técnico útil: piezas funcionales, conexiones y anotaciones explicativas. Conserva proporciones plausibles sin inventar medidas ni componentes que la imagen no permita inferir.'})));
            const colors=[...new Set(p.scene.objects.map(item=>item.color.toLowerCase()))].slice(0,8),saved=this.sceneStyle(),same=JSON.stringify(saved?.colors)===JSON.stringify(colors)&&saved?.detail===p.scene.objects.length;
            tools.append(button(same?'Quitar estilo guardado':'Conservar paleta de este modelo',same?'Estilo guardado':'Guardar estilo',()=>{if(same){localStorage.removeItem('axx.magicpen.scene-style');this.status('Estilo guardado eliminado.');}else this.saveSceneStyle();this.renderAnswers();}));
            const viewport=this.stage.querySelector('.mp-stage-viewport');if(player.sceneHost.parentElement!==viewport)viewport.append(player.sceneHost);
            block.append(el('p','Toca una etiqueta para entender la pieza. Pide cambios de tamaño, posición o color en el chat.','mp-scene-hint'));
            this.positionWidget();this.syncInput();
            const parts=el('details',null,'mp-scene-parts'),summary=el('summary','Seleccionar pieza');parts.append(summary);
            for(const item of p.scene.objects){const choose=button('Seleccionar '+item.label,item.label,()=>{player.picked=item.id;player.overview=false;player.scene?.focus([item.id],player.isolated);this.renderAnswers();this.widget.querySelector('.mp-scene-picked')?.scrollIntoView({block:'nearest'});}),swatch=el('span',null,'mp-scene-swatch');swatch.style.backgroundColor=item.color;choose.replaceChildren(swatch,el('span',item.label));choose.setAttribute('aria-pressed',String(player.picked===item.id));parts.append(choose);}
            if(picked){
                const info=el('section',null,'mp-scene-picked'),step=p.steps.find(item=>item.focus?.includes(picked.id));
                const role=p.asset?.kind==='single_cylinder_engine'?{engine_cylinder:'Guía el recorrido del pistón y deja a la vista el interior del mecanismo.',piston:'Se desplaza dentro del cilindro y transmite el empuje a la biela.',connecting_rod:'Une el pistón con el cigüeñal y transmite su movimiento.',crankshaft:'Transforma el movimiento alternativo de la biela en giro.'}[picked.shape]:null;
                info.setAttribute('aria-label','Detalle de '+picked.label);
                info.append(el('small','PIEZA '+(p.scene.objects.findIndex(item=>item.id===picked.id)+1)+' / '+p.scene.objects.length+' · '+(step?BASIS[step.basis]:'CONCEPTUAL'),'mp-scene-kicker'),el('strong',picked.label));
                if(role)info.append(el('p',role,'mp-scene-role'));
                if(step)info.append(el('p',step.body,'mp-scene-step-note'),el('small','En el paso «'+step.title+'»','mp-scene-source'));
                if(!role&&!step)info.append(el('p','Esta pieza forma parte de la escena conceptual. Pregunta para ampliar su función.','mp-scene-role'));
                info.append(button('Preguntar sobre '+picked.label,'Preguntar sobre esta pieza',()=>{const input=$('mp-question');input.value='Sobre «'+picked.label+'»: ';input.focus();}));
                block.append(info);
            }
            block.append(tools,parts);
            return block;
        }
        disposeScene(){this.stage.hidden=true;this.render();this.syncInput();const player=this.player;if(!player)return;player.scene?.dispose();player.scene=null;player.sceneHost?.remove();player.sceneHost=null;}
        async exportScene(){const image=this.player?.scene?.snapshot();if(!image)throw Error('La escena 3D no está disponible.');await this.export('scene',image);}
        seekPresentation(index){
            const q=this.presentationQuery(),player=this.player;if(!q||player?.queryId!==q.id||index<0||index>=q.presentation.steps.length)return;
            const playing=player.playing;this.stopPresentation();player.index=index;player.picked=null;player.overview=false;if(playing)this.playPresentation();else this.renderAnswers();
        }
        playPresentation(){
            const q=this.presentationQuery(),player=this.player;if(!q||player?.queryId!==q.id)return;
            const steps=q.presentation.steps,token=++player.token,step=steps[player.index];player.playing=true;player.overview=false;this.caption.textContent=step.narration;this.caption.hidden=false;this.renderAnswers();this.render();
            player.spoke=this.readNarration(step.narration);
            // One playback owner: a stale token (pause, seek, new answer) ends this chain without touching the voice.
            const next=()=>{
                if(player.token!==token||!player.playing)return;
                if(player.spoke&&this.speechBusy()){player.timer=setTimeout(next,300);return;}
                if(player.index>=steps.length-1){player.playing=false;this.caption.hidden=true;this.render();this.renderAnswers();return;}
                player.index++;player.picked=null;this.playPresentation();
            };
            player.timer=setTimeout(next,player.spoke?600:Math.max(2500,step.narration.length*60));
        }
        stopPresentation(){
            const player=this.player;if(!player)return;clearTimeout(player.timer);player.token++;
            if(player.playing&&player.spoke)try{A.companion.voiceDelegate?.stopOutput?.();}catch{}
            player.playing=false;player.spoke=false;
            if(this.caption)this.caption.hidden=true;this.render();
        }
        readNarration(text){
            const prefs=A.companion.data.prefs;if(prefs.mutedAll||this.speechBusy()||typeof A.companion.read!=='function')return false;
            try{return A.companion.read(text)!==false;}catch{return false;}
        }
        askFromComposer(){
            const base=this.presentationQuery(),question=$('mp-question').value.trim();
            if(base&&this.localSceneCommand(question))return;
            const normalized=question.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
            const locate=/\b(donde (esta|queda|se encuentra|puedo encontrar)|senala|marca|ubica)\b/.test(normalized),diagram=/\b(diagrama|esquema|flujo)\b/.test(normalized),model=/\b(3d|modelo tridimensional|en tres dimensiones|maqueta)\b/.test(normalized)||/\b(crea|genera|generame|haz|construye|muestrame)\b.{0,35}\bmodelo\b/.test(normalized),visual=/\b(analiza|explica|explicame|como funciona|funcionamiento|visualiza|ilustra|muestrame|desglosa|ensena)\b/.test(normalized);
            const spatial=this.spatialRoute(),advanced=this.spatialProviders?.get($('mp-spatial-provider').value)?.spatial_3d;
            if(model&&!advanced)return this.status('Para 3D, elige ChatGPT/Codex o Claude con visión en «Proveedor y calidad».');
            if(model&&!locate&&!diagram)return this.spatialAction('model');
            if(visual&&!spatial){this.widget.querySelector('.mp-spatial-settings').open=true;return this.status('Elige un modelo visual en «Proveedor y calidad» para generar un diagrama o modelo.');}
            if(locate||diagram||model||visual||spatial?.provider==='@codex'){
                const rebuild=visual&&!base?.presentation?.scene,hint=(!base||rebuild)&&!locate&&!diagram&&!model?'\n\nExplica visualmente con un diagrama de pasos y relaciones.'+(advanced?' Si la captura muestra un objeto físico cuya estructura puede explicarse con 3D, agrega una escena conceptual con piezas identificables; si no, conserva solo el diagrama.':' No generes una escena 3D.'):'',guided=question.length+hint.length<=4000?question+hint:question;
                return this.ask({fresh:false,format:'presentation',base:locate||diagram||model||rebuild?null:base?.id||null,question:locate?question+'\n\nUbica el elemento en la captura y marca sus límites con una caja visible en el primer paso. Si no está visible, dilo claramente sin inventar coordenadas.':guided});
            }
            return base?this.ask({fresh:false,format:'presentation',base:base.id}):this.ask();
        }
        spatialAction(mode){
            if(mode==='model'&&!this.spatialProviders?.get($('mp-spatial-provider').value)?.spatial_3d)return this.status('Para 3D, elige ChatGPT/Codex o Claude con visión en «Proveedor y calidad».');
            const question=$('mp-question').value.trim();
            if(mode==='locate'&&!question)return this.status('Escribe qué elemento quieres que señale en la captura.');
            const instruction={locate:'Ubica el elemento en la captura y marca sus límites con una caja visible en el primer paso, con nombre exacto y una explicación en bullet points de su posición y función observada.',diagram:'Explica la selección con un diagrama de pasos y relaciones.',model:'Si la selección muestra un objeto o mecanismo físico, crea un ensamblaje 3D conceptual con piezas funcionales identificables, proporciones coherentes, uniones visibles y anotaciones explicativas. Estilo de diseño técnico y producto industrial de alta calidad. Descompón el objeto en partes principales y secundarias con colores distinguibles. No extruyas pantallas o fondos planos como placas 3D; en ese caso ofrece un diagrama 2D. Distingue lo observado de lo inferido.'}[mode];
            return this.ask({fresh:false,format:'presentation',question:(question||'¿Cómo funciona lo seleccionado?')+'\n\n'+instruction});
        }
        loadVisual(){
            if(this.visualLoading)return;this.visualLoading=import('./visual-canvas.js').then(module=>{this.visualModule=module;if(this.active){this.renderAnswers();this.render();}}).catch(()=>this.status('No se pudo cargar el diagrama local.'));
        }
        paintVisual(){const q=this.presentationQuery(),player=this.player;if(q&&player?.queryId===q.id&&q.presentation.overlays&&this.visualModule)this.visualModule.paintOverlays(this.ctx,q.presentation.overlays,q.presentation.steps[player.index].id,this.doc?.selection,this.image);}
        saveViewNow(){
            clearTimeout(this.viewTimer);const q=this.presentationQuery(),p=this.player,d=this.doc;
            if(!this.active||!q||p?.queryId!==q.id||!d)return Promise.resolve();
            const view={camera:p.scene?.getView()||p.initialView||null,step_id:q.presentation.steps[p.index].id,selected:p.picked||null,
                hidden:[...p.hidden],separated:p.scene?.getSeparated()||[...(p.separated||[])],exploded:!!p.exploded,isolated:!!p.isolated,overview:!!p.overview};
            return spatialApi('view',{id:d.id,query_id:q.id,view}).then(()=>{q.view_state=view;this.viewError=false;}).catch(e=>{if(!this.viewError){this.viewError=true;this.status('No se pudo guardar la vista: '+String(e.message||e));}});
        }
        queueView(){
            clearTimeout(this.viewTimer);if(!this.active)return;
            this.viewTimer=setTimeout(()=>void this.saveViewNow(),300);
        }
        onDictated(text){
            if(!this.active)return;this.stopPresentation();if(this.presentationQuery()&&this.localSceneCommand(text))return;
            const input=$('mp-question');input.value=text;input.dispatchEvent(new Event('input'));this.leaseFocus(input);
        }
        sceneStyle(){try{const value=JSON.parse(localStorage.getItem('axx.magicpen.scene-style')||'null');return Array.isArray(value?.colors)&&value.colors.length>0&&value.colors.length<=8&&value.colors.every(color=>/^#[0-9a-f]{6}$/.test(color))&&Number.isInteger(value.detail)&&value.detail>=1&&value.detail<=24?value:null;}catch{return null;}}
        saveSceneStyle(){const scene=this.presentationQuery()?.presentation?.scene;if(!scene){this.status('Primero crea un modelo 3D para guardar su estilo.');return;}
            const colors=[...new Set(scene.objects.map(item=>item.color.toLowerCase()))].slice(0,8);localStorage.setItem('axx.magicpen.scene-style',JSON.stringify({colors,detail:scene.objects.length}));this.status('Paleta y nivel de detalle guardados para próximos modelos.');}
        localSceneCommand(raw){
            const q=this.presentationQuery(),p=this.player;if(!q||p?.queryId!==q.id)return false;
            const text=String(raw||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().replace(/[.!?¿¡]+$/,'');
            if(/^(me gusta(?: (?:este|el) (?:modelo|estilo)| como se ve)?|me encanta(?: (?:este|el) (?:modelo|estilo))?|asi me gusta)$/.test(text)){this.saveSceneStyle();$('mp-question').value='';this.renderAnswers();return true;}
            if(/^(pausa|pausar)( la explicacion)?$/.test(text)){this.stopPresentation();this.renderAnswers();return true;}
            if(/^(continua|reanuda|continuar)( la explicacion)?$/.test(text)){this.playPresentation();return true;}
            const match=/^(separa|separar|une|unir|junta|oculta|ocultar|muestra|mostrar|aisla|aislar)(?: (?:esta|esa|la) (?:pieza|parte))?$/.exec(text);
            if(!match)return false;
            if(!p.picked||!p.scene){this.status('Selecciona una pieza del modelo antes de dar esa orden.');return true;}
            const action=match[1];
            if(['separa','separar','une','unir','junta'].includes(action))p.scene.setObjectExploded(p.picked,['separa','separar'].includes(action));
            else if(['oculta','ocultar','muestra','mostrar'].includes(action)){const hidden=['oculta','ocultar'].includes(action);if(hidden)p.hidden.add(p.picked);else p.hidden.delete(p.picked);p.scene.setHidden(p.picked,hidden);}
            else{p.isolated=true;p.overview=false;}
            $('mp-question').value='';this.status('Vista actualizada sobre la pieza seleccionada.');this.renderAnswers();this.queueView();return true;
        }
        guideQuery(){
            const d=this.doc,last=this.answerDirty?null:d?.queries?.findLast(q=>q.revision===d.revision&&q.state==='completed');
            return last?.guide?last:null;
        }
        guideCard(q){
            if(this.guide?.queryId!==q.id){this.stopGuide();this.guide={queryId:q.id,token:0,running:false,timer:null,mark:null,message:'',started:0};queueMicrotask(()=>this.startGuide(false));}
            const g=this.guide,progress=q.guide_progress||{},el=(tag,text,className)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(className)n.className=className;return n;};
            const labels={WAITING_USER:'Te toca',VERIFIED:'Comprobado',UNKNOWN:'Sin comprobar',AMBIGUOUS:'No lo identifico',TARGET_NOT_FOUND:'No lo encuentro',STALE:'Ventana cambiada'};
            const card=el('figure',null,'mp-visual mp-guide'),head=el('figcaption'),list=el('ol',null,'mp-visual-flow'),controls=el('div',null,'mp-visual-controls');
            head.append(el('strong','Guíame · '+q.guide.goal),el('small','En «'+q.guide_window.title+'». Señalo el control; tú actúas y yo compruebo leyendo la ventana.','mp-visual-fidelity'));
            q.guide.steps.forEach(step=>{
                const item=el('li'),state=progress[step.id]?.state;item.dataset.state=state||'PENDING';
                if(step.id===g.stepId&&g.running)item.setAttribute('aria-current','step');else if(state!=='VERIFIED')item.classList.add('mp-step-pending');
                item.append(el('strong',step.instruction),el('small',labels[state]||'Pendiente','mp-visual-basis'));list.append(item);
            });
            const button=(label,text,onclick)=>{const b=el('button',text);b.type='button';b.setAttribute('aria-label',label);b.onclick=onclick;return b;};
            const done=q.guide.steps.every(s=>progress[s.id]?.state==='VERIFIED');
            if(!done)controls.append(g.running?button('Detener la guía','Detener',()=>{this.stopGuide();this.renderAnswers();}):button('Continuar la guía','Continuar',()=>this.startGuide(false)),
                button('Volver a señalar el paso actual','Volver a señalar',()=>this.startGuide(true)));
            const message=el('p',g.message||(done?'Guía completada: todos los pasos están comprobados.':''),'mp-guide-status');message.setAttribute('role','status');
            card.append(head,list,message,controls);return card;
        }
        startGuide(retarget){
            const q=this.guideQuery(),g=this.guide;if(!q||g?.queryId!==q.id)return;
            this.stopGuide();g.running=true;g.started=Date.now();this.setInput(false);
            const step=q.guide.steps.find(s=>q.guide_progress?.[s.id]?.state!=='VERIFIED');
            void this.guideStep(!retarget&&step&&['WAITING_USER','UNKNOWN'].includes(q.guide_progress?.[step.id]?.state)?'verify':'target');
        }
        stopGuide(){const g=this.guide;if(!g)return;g.token++;clearTimeout(g.timer);g.running=false;g.mark=null;if(this.ctx)this.render();}
        async guideStep(phase){
            const g=this.guide,q=this.guideQuery();if(!g?.running||!q||q.id!==g.queryId)return;
            const token=++g.token,step=q.guide.steps.find(s=>q.guide_progress?.[s.id]?.state!=='VERIFIED');
            if(!step){g.running=false;g.mark=null;g.message='Guía completada: todos los pasos están comprobados.';this.render();this.renderAnswers();return;}
            g.stepId=step.id;
            let r;try{r=await api('guide_check',{id:q.source_id,query_id:q.id,step_id:step.id,phase});}
            catch(e){if(token===g.token){g.running=false;g.mark=null;g.message=String(e.message||e);this.render();this.renderAnswers();}return;}
            if(token!==g.token||!this.active)return;
            (q.guide_progress||={})[step.id]=r.record;
            const stop=message=>{g.running=false;g.mark=null;g.message=message;};
            const mark=this.guideMark(r,step);
            if(mark==='stale')stop('La disposición de pantallas cambió desde la captura. Vuelve a capturar para seguir.');
            else if(r.state==='VERIFIED'){g.mark=null;g.message='Paso comprobado.';g.timer=setTimeout(()=>void this.guideStep('target'),600);}
            else if(r.state==='WAITING_USER'){
                g.mark=mark;g.message=step.instruction+(mark?'':' (el control está fuera de la pantalla capturada)');
                if(Date.now()-g.started>300000)stop('Sigo sin ver el cambio. Pulsa Continuar cuando lo hayas hecho.');
                else g.timer=setTimeout(()=>void this.guideStep('verify'),1500);
            }
            else stop({UNKNOWN:'No puedo comprobar si el paso se hizo: el control cambió o desapareció. No avanzo; pulsa Volver a señalar.',
                AMBIGUOUS:'Hay más de un control que coincide con «'+step.target.name+'». No señalo para no equivocarme.',
                TARGET_NOT_FOUND:'No encuentro «'+step.target.name+'» en la ventana. Hazlo visible y pulsa Volver a señalar.',
                STALE:'La ventana se cerró o se reinició. Pide «Guíame» de nuevo para observarla otra vez.'}[r.state]||'Estado de guía desconocido.');
            this.render();this.renderAnswers();
        }
        guideMark(r,step){
            // Only draw when the captured monitor still exists with the same geometry; otherwise the mapping is stale.
            const s=this.doc?.source,b=r.bounds;if(!s||!b)return null;
            if(r.monitors&&!r.monitors.some(m=>m.x===s.x&&m.y===s.y&&m.width===s.width&&m.height===s.height))return 'stale';
            const x=b.x-s.x,y=b.y-s.y;
            return x+b.width<=0||y+b.height<=0||x>=s.width||y>=s.height?null:{x,y,width:b.width,height:b.height,label:step.target.name};
        }
        paintGuide(){
            const m=this.guide?.mark;if(!m||typeof m!=='object')return;
            const c=this.ctx,pad=6,w=Math.max(3,this.canvas.width/480);
            c.save();c.strokeStyle='#9274ff';c.lineWidth=w;c.shadowColor='#9274ff';c.shadowBlur=w*4;
            c.beginPath();c.roundRect(m.x-pad,m.y-pad,m.width+pad*2,m.height+pad*2,10);c.stroke();
            c.shadowBlur=0;c.font=`600 ${Math.round(w*5)}px "Segoe UI",sans-serif`;const text='Aquí: '+m.label,tw=c.measureText(text).width,ty=m.y-pad-w*3;
            c.fillStyle='#9274ff';c.beginPath();c.roundRect(m.x-pad,ty-w*6,tw+w*5,w*7.5,w*3);c.fill();c.fillStyle='#fff';c.fillText(text,m.x-pad+w*2.5,ty);c.restore();
        }
        route(){const p=A.companion.data.prefs;return p.visionConnection&&p.visionModel?
            {selection_mode:'manual',provider:p.visionConnection,model:p.visionModel}:
            {selection_mode:p.selection_mode||'manual',provider:p.apiConnection||(p.provider==='bridge'?'':p.provider)||'',model:p.model||''};}
        hasVision(){
            const routes=[...(this.capabilities?.vision||[]),...(this.capabilities?.codex_vision||[])],r=this.route();
            if(this.spatialRoute())return true;
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
            const cancel=job.format==='presentation'?spatialApi('cancel',{id:job.source_id,query_id:job.id}):api('cancel',{id:job.source_id,query_id:job.id});
            this.cancelChain=this.cancelChain.catch(()=>{}).then(()=>cancel).catch(e=>{
                if(this.active)this.status('La cancelación no se pudo confirmar. La respuesta anterior no se mostrará. '+String(e.message||e));
            });return this.cancelChain;
        }
        cancelAnalysis(){
            clearTimeout(this.liveTimer);this.liveTimer=null;++this.analysisEpoch;this.stopPresentation();this.stopGuide();
            const job=this.analysisJob,wasPending=this.analysisPending;this.analysisJob=null;this.analysisPending=false;this.queries.clear();if(wasPending&&this.summaryBubbleMode)this.clearSummaryBubble(true);
            if(job)void this.cancelQuery(job);this.updateControls();return this.analysisEpoch;
        }
        scheduleAnalysis(delay=650,fresh=true){
            clearTimeout(this.liveTimer);this.liveTimer=null;
            if(!this.live||this.livePaused||this.historyMode||!this.active||!this.doc?.selection)return;
            if(!this.hasVision()){this.livePaused=true;this.updateControls();this.status('Configura un modelo con visión para activar el análisis en directo.');return;}
            const epoch=this.analysisEpoch;
            this.liveTimer=setTimeout(()=>{this.liveTimer=null;if(epoch===this.analysisEpoch&&!this.gesture)void this.ask({fresh,format:this.spatialRoute()?.provider==='@codex'?'presentation':'text'});},delay);
        }
        paintPreview(){
            if(!this.historyMode||!this.previewImage||!this.doc)return;
            const canvas=$('mp-preview-canvas'),s=this.doc.source,scale=Math.min(1,900/s.width);canvas.width=Math.round(s.width*scale);canvas.height=Math.round(s.height*scale);
            const c=canvas.getContext('2d');c.drawImage(this.previewImage,0,0,canvas.width,canvas.height);c.scale(scale,scale);
            for(const stroke of this.doc.strokes){c.save();c.globalAlpha=stroke.tool==='marker'?.33:1;c.strokeStyle=stroke.color;c.fillStyle=stroke.color;c.lineWidth=stroke.width;c.lineCap=c.lineJoin='round';c.beginPath();stroke.points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.stroke();if(stroke.points.length===1){c.beginPath();c.arc(...stroke.points[0],stroke.width/2,0,Math.PI*2);c.fill();}c.restore();}
        }
        async ask({fresh=true,format='text',base=null,question:explicit=''}={}){
            if(!this.active||!this.doc?.selection)return this.status('Selecciona o marca una región antes de preguntar.');
            if(base&&!explicit&&!$('mp-question').value.trim())return this.status('Escribe qué quieres saber o cambiar de la presentación.');
            const route=format==='presentation'?this.spatialRoute():this.route();
            if(format==='presentation'&&!route)return this.status('Elige un proveedor y modelo visual en «Proveedor y calidad».');
            if(format==='text'&&!this.hasVision()){this.livePaused=this.live;this.updateControls();return this.status('El modelo seleccionado no tiene visión disponible. Revisa Ajustes de conexión.');}
            const epoch=this.cancelAnalysis(),session=this.generation,userQuestion=explicit||$('mp-question').value.trim()||'Explica el contenido de toda la región seleccionada. Ignora el cursor del ratón y cualquier indicador de puntero. Responde de forma clara y breve.',style=this.sceneStyle(),hint=format==='presentation'&&!base&&/\b(3d|modelo tridimensional|en tres dimensiones)\b/i.test(userQuestion)&&style?'\n\nPreferencia visual guardada por el usuario: usa esta paleta como referencia si encaja con el objeto: '+style.colors.join(', ')+'. Si tiene sentido, conserva un nivel de detalle comparable a '+style.detail+' piezas funcionales distinguibles, con anotaciones explicativas.':'',question=format!=='text'?userQuestion+(userQuestion.length+hint.length<=4000?hint:''):userQuestion+'\n\nEmpieza con «Resumen:» y una síntesis en una frase de máximo 24 palabras; después da los detalles necesarios bajo «Detalle:».',
                providerRoute=format==='presentation'?{provider:route.provider,model:route.model,selection_mode:'manual'}:route;
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
                this.analysisJob={id:request_id,source_id:d.id,format};
                const body={id:d.id,revision,question,...providerRoute,request_id,...(format!=='text'?{format,effort:route.effort}:{}),...(base?{base_query_id:base}:{}),...(base&&this.player?.picked?{selected_object_id:this.player.picked}:{}),...(A.chatWorkspace?.active?.id?{conversation_id:A.chatWorkspace.active.id}:{})};
                const q=format==='presentation'?await spatialApi(base?'query':'start',body):await api('start',body);
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
                    q=format==='presentation'?await spatialApi('get',{id:job.d.id,query_id:q.id}):await api('query',{id:job.d.id,query_id:q.id});
                    if(q.id!==job.q.id||q.source_id!==job.d.id||q.revision!==job.revision)throw Error('El resultado no corresponde a esta selección.');
                }
                if(!current()||this.doc!==job.d||job.d.revision!==job.revision)return;
                if(!['completed','failed','cancelled','interrupted'].includes(q.state))throw Error('Estado de análisis desconocido.');
                if(!job.d.queries.some(item=>item.id===q.id))job.d.queries.push(q);
                this.answerDirty=false;this.renderAnswers();
                if(q.state==='completed'){
                    if(q.presentation){try{const readiness=await A.backendRequest('GET','/axx-api/feature-readiness?feature_id=spatial_intelligence');if(current()){this.readiness=readiness;this.renderSpatialReadiness();}}catch{}}
                    const location=/\b(donde (esta|queda|se encuentra|puedo encontrar)|senala|marca|ubica)\b/.test(userQuestion.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase());
                    const marked=q.presentation?.overlays?.some(item=>item.step_id===q.presentation.steps[0].id&&['box','arrow','label'].includes(item.kind));
                    this.status(location&&!marked?'No pude señalar una ubicación verificable en esta captura. Revisa la explicación o selecciona una zona más precisa.':'Respuesta lista. Puedes preguntar más o marcar otra zona.');
                    this.showSummaryBubble(q.presentation?q.answer||q.presentation.summary:q.guide?q.guide.goal:q.response);if(q.presentation||q.guide)this.openAnswer();}
                else {if(this.live)this.livePaused=true;this.clearSummaryBubble(true);this.status(q.error||'Análisis detenido. Puedes volver a intentarlo.');}
            }catch(e){if(current()){if(this.analysisJob)void this.cancelQuery(this.analysisJob);if(this.live)this.livePaused=true;this.clearSummaryBubble(true);this.status(String(e.message||e));}}
            finally{if(current()){this.analysisPending=false;this.analysisJob=null;this.queries.clear();this.updateControls();}}
        }
        async export(kind,image){if(!this.doc)throw Error('Captura una pantalla primero.');await this.flush();this.status('Verificando exportación…');const r=await api('export',{id:this.doc.id,revision:this.doc.revision,kind,directory:$('mp-directory').value,name:$('mp-name').value+{original:'-original',annotated:'-anotado',scene:'-escena'}[kind],...(image?{image}:{})});$('mp-export').textContent=`Guardado y verificado: ${r.path}\nSHA256 ${r.sha256}`;this.status('PNG guardado y verificado.');}
    }
    A.magicPenGeometry={sourcePoint,desktopPoint};
    A.magicPen=new MagicPen();
})();
