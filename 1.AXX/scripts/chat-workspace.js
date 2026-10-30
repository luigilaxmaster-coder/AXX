/* Conversation UI over the authenticated native store. Companion remains the renderer. */
(function (Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.isNative()) return;
    const c = Axx.companion, $ = id => document.getElementById(id), view = $('view-chat');
    const api = async (action, body,token=null) => {if(token&&!isMemoryTokenCurrent(token,false))throw abortMemory();const result=await Axx.backendRequest(body === undefined ? 'GET' : 'POST', '/axx-api/chat/' + action,token?{...body,memory_scope:{...token.memory_scope},memory_context_id:token.memory_context_id}:body);if(token&&!isMemoryTokenCurrent(token,false))throw abortMemory();return result;};
    const TTL = 90 * 86400000;
    const ui = document.createElement('section'); ui.id = 'chat-workspace';
    ui.innerHTML = `<div class="cw-heading"><button id="cw-browse" type="button">Chats y grupos</button><button id="cw-new" type="button">Nuevo chat</button></div>
      <div class="cw-current"><strong id="cw-title">Cargando conversaciones…</strong><label>Comandos <select id="cw-mode"><option value="ask">Preguntar</option><option value="auto_safe">Auto seguro</option></select></label></div>
      <button id="cw-context-open" class="cw-context-link" type="button">Sin contexto de grupo</button>
      <div id="cw-operation" hidden role="status" aria-live="polite"></div>
      <p id="cw-error" role="alert" hidden></p><button id="cw-retry" type="button" hidden>Volver a cargar chats</button>
      <section id="cw-browser" hidden aria-label="Conversaciones y grupos">
        <div class="cw-heading"><strong>Tu historial</strong><button id="cw-back" type="button">Volver al chat</button></div>
        <label>Buscar conversación<input id="cw-search" type="search" placeholder="Título de la conversación"></label>
        <label>Grupo<select id="cw-filter"><option value="">Todos los grupos</option></select></label>
        <label class="cw-check"><input id="cw-archived" type="checkbox"> Mostrar archivados</label>
        <div id="cw-list"></div>
        <details><summary>Organizar este chat</summary>
          <label>Título<input id="cw-rename" maxlength="120"></label><button id="cw-rename-save" type="button">Guardar título</button>
          <label>Mover a grupo<select id="cw-group"></select></label>
          <div class="cw-heading"><button id="cw-restart" type="button">Reiniciar contexto</button><button id="cw-archive" type="button">Archivar</button><button id="cw-delete" type="button">Eliminar</button></div>
          <button id="cw-export" type="button">Exportar conversación</button><button id="cw-continue" type="button">Nuevo chat con contexto de este hilo</button>
        </details>
        <details><summary>Crear grupo</summary><label>Nombre<input id="cw-group-name" maxlength="120"></label><button id="cw-create-group" type="button">Crear grupo</button></details>
        <label>Modo para nuevos chats<select id="cw-default"><option value="ask">Preguntar</option><option value="auto_safe">Auto seguro</option></select></label>
        <p class="cw-help">Auto ejecuta solo acciones seguras del catálogo. Las acciones sensibles siempre piden aprobación. El historial se elimina a los 90 días.</p>
      </section>
      <section id="cw-context" hidden aria-label="Contexto enviado al modelo">
        <div class="cw-heading"><strong>Contexto de este chat</strong><button id="cw-context-close" type="button">Cerrar</button></div>
        <p class="cw-help">Este contenido se envía al proveedor seleccionado con tu siguiente mensaje. Los vínculos incluyen un extracto guardado, sin los borradores, grupos ni otros vínculos del hilo original.</p>
        <label>Conectar un hilo anterior<select id="cw-link-source"></select></label><button id="cw-link-add" type="button">Añadir su contexto</button><div id="cw-links"></div>
        <div id="cw-group-context">
        <p class="cw-help">Notas compartidas explícitamente con el grupo. El contenido y los extractos vencen 90 días después de su fecha original.</p>
        <label>Nombre del grupo<input id="cw-group-title" maxlength="120"></label><div class="cw-heading"><button id="cw-group-rename" type="button">Renombrar grupo</button><button id="cw-group-delete" type="button">Eliminar grupo</button></div><div id="cw-context-list"></div>
        <label>Instrucción o nota<textarea id="cw-note" maxlength="4000" rows="3" placeholder="Escribe el contexto que compartirán estos chats"></textarea></label>
        <button id="cw-add-note" type="button">Guardar en el grupo</button></div>
      </section>`;
    view.prepend(ui);
    let active = null, listing = {conversations:[],groups:[],default_mode:'ask'}, ready = false;
    let chain = Promise.resolve(), timer, busy = false, operations=[], contextRevision=0;
    const memoryScopes=new Map(),memoryContexts=new Map(),memoryEpochs=new Map(),memoryMinimum=new Map(),memoryBlocked=new Set(),memoryRuns=new Set();
    const abortMemory=()=>new DOMException('La memoria de esta conversación cambió.','AbortError');
    function validScope(ref,id){return ref&&ref.task_id===id&&Number.isSafeInteger(ref.generation)&&ref.generation>=0;}
    function captureMemoryScope(id=active?.id){const ref=memoryScopes.get(id);if(memoryBlocked.has(id)||!validScope(ref,id))throw abortMemory();return {...ref};}
    function contextId(row){const id=row.memory_context_id||row.context_id||row.connect_id;if(typeof id!=='string'||!id||id!==row.connect_id)throw Error('El chat no confirmó su identidad de contexto.');return id;}
    function captureMemoryToken(id=active?.id){const memory_scope=captureMemoryScope(id),memory_context_id=memoryContexts.get(id);if(!memory_context_id)throw abortMemory();return {memory_scope,memory_context_id,epoch:memoryEpochs.get(memory_scope.task_id)||0};}
    function isMemoryTokenCurrent(token,requireActive=true){const ref=token?.memory_scope,current=memoryScopes.get(ref?.task_id);return !!ref&&(!requireActive||active?.id===ref.task_id)&&!memoryBlocked.has(ref.task_id)&&current?.generation===ref.generation&&memoryContexts.get(ref.task_id)===token.memory_context_id&&(memoryEpochs.get(ref.task_id)||0)===token.epoch;}
    function invalidateMemory(id){
        memoryBlocked.add(id);memoryEpochs.set(id,(memoryEpochs.get(id)||0)+1);
        for(const run of memoryRuns)if(run.task_id===id)run.controller.abort();
        lib.invalidateMemory?.(id);Axx.skillLibrary?.invalidateMemory?.(id);Axx.connect?.invalidateMemory?.(id);
        if(active?.id!==id)return;
        clearTimeout(timer);c.cancelRequest();c.streamElement=null;c.brain.lastRoute=null;
    }
    function applyRow(row,preserveDraft=false){
        if(!validScope(row.memory_scope,row.id))throw Error('El chat no confirmó su generación de memoria.');
        const known=memoryScopes.get(row.id);if(row.memory_scope.generation<(memoryMinimum.get(row.id)||0)||known&&row.memory_scope.generation<known.generation)throw abortMemory();
        const memory_context_id=contextId(row),changed=known&&(known.generation!==row.memory_scope.generation||memoryContexts.get(row.id)!==memory_context_id);
        if(changed)invalidateMemory(row.id);
        memoryScopes.set(row.id,{...row.memory_scope});memoryContexts.set(row.id,memory_context_id);
        const draft=preserveDraft?$('chat-input').value:(c.data.prefs.keepHistory?row.draft:'');
        active={...row,memory_scope:{...row.memory_scope},memory_context_id,draft,...(preserveDraft&&draft?{draft_at:Date.now()}: {})};memoryBlocked.delete(row.id);
        c.data.messages=(c.data.prefs.keepHistory?row.messages:[]).map(m=>m.status==='pending'?{...m,status:'interrupted'}:{...m});
        c.data.draft=draft;c.data.connectConversationId=row.connect_id;c.data.sharedConversationId=row.shared_id;
        c.attachment=c.data.prefs.keepHistory?row.attachment:null;$('chat-input').value=draft;c.renderAttachment();
        return changed;
    }
    const originalSave = c.save.bind(c), originalRender = c.renderChat.bind(c), originalAttachment=c.renderAttachment.bind(c);
    c.renderAttachment=function(){if(this.attachment&&!this.attachment.at)this.attachment.at=Date.now();originalAttachment();if(ready)this.save();};
    function error(e) { $('cw-error').hidden = false; $('cw-error').textContent = e.message || String(e); }
    function run(fn) { return async () => { try { $('cw-error').hidden=true; await fn(active?captureMemoryToken():null); } catch(e) { error(e); } }; }
    function button(label, fn) { const b=document.createElement('button'); b.type='button'; b.textContent=label; b.onclick=run(fn); return b; }
    function expireLocal() {
        c.data.messages=c.data.messages.filter(m=>m.at>Date.now()-TTL);
        if(c.attachment?.at<=Date.now()-TTL){c.attachment=null;c.renderAttachment();}
        if(active?.draft_at<=Date.now()-TTL){$('chat-input').value='';c.data.draft='';}
    }
    $('chat-input').addEventListener('input',()=>{if(active)active.draft_at=Date.now();});
    function snapshot() { expireLocal();if(!active||memoryBlocked.has(active.id))return null;const token=captureMemoryToken();return structuredClone({id:active.id,memory_scope:token.memory_scope,memory_context_id:token.memory_context_id,messages:c.data.prefs.keepHistory ? c.data.messages : [],attachment:c.data.prefs.keepHistory?c.attachment:null,draft:c.data.prefs.keepHistory ? $('chat-input').value : ''}); }
    async function flush(body=snapshot()) {
        clearTimeout(timer);
        if (!ready || !body) return chain;
        const task=chain.catch(()=>{}).then(async()=>{ for(let i=0;i<Math.max(body.messages.length,1);i+=10){const current=memoryScopes.get(body.id);if(memoryBlocked.has(body.id)||current?.generation!==body.memory_scope.generation||memoryContexts.get(body.id)!==body.memory_context_id)return;await api('save',{...body,messages:body.messages.slice(i,i+10)});} }); chain=task;
        await task;
        if(active?.id===body.id&&memoryContexts.get(body.id)===body.memory_context_id&&active.title==='Nueva conversación'&&body.messages.some(m=>m.role==='user')){const row=await api('conversations?id='+encodeURIComponent(body.id));if(active?.id===body.id&&memoryContexts.get(body.id)===body.memory_context_id&&row.memory_scope?.generation===body.memory_scope.generation&&contextId(row)===body.memory_context_id){active.title=row.title;header();await refresh();}}
    }
    c.save = function () {
        if (!ready) return originalSave();
        // The durable transcript lives only in SQLite after migration acknowledgement.
        const messages=this.data.messages, draft=this.data.draft;
        this.data.messages=[]; this.data.draft='';
        try { originalSave(); } finally { this.data.messages=messages; this.data.draft=draft; }
        const body=snapshot();clearTimeout(timer);if(body)timer=setTimeout(()=>void flush(body).catch(error),150);
    };
    c.renderChat = function () { originalRender(); decorateMessages(); };
    function decorateMessages() {
        if (!active?.group_id) return;
        for (const row of $('chat-log').querySelectorAll('[data-message-id]')) {
            if(row.querySelector('.cw-pin'))continue;
            const m=c.data.messages.find(m=>m.id===row.dataset.messageId);
            if(!m || m.status!=='complete')continue;
            const token=captureMemoryToken(),group_id=active.group_id;
            const b=button('Guardar en contexto del grupo',async()=>{
                if(!isMemoryTokenCurrent(token)||active.group_id!==group_id)throw abortMemory();
                if(m.text.length>4000)throw Error('El mensaje supera el límite de contexto de grupo.');
                await api('context',{group_id,text:m.text,source_task_id:token.memory_scope.task_id,source_message_id:m.id},token);if(!isMemoryTokenCurrent(token))return;await refreshActiveContext(); showContext();
            }); b.className='cw-pin';row.append(b);
        }
    }
    function options(select, first, selected) {
        select.replaceChildren(new Option(first,''));
        for(const g of listing.groups)select.add(new Option(g.title,g.id));
        select.value=selected || '';
    }
    async function refresh() {
        listing=await api('conversations');
        options($('cw-filter'),'Todos los grupos',$('cw-filter').value);
        options($('cw-group'),'Sin grupo',active?.group_id);
        $('cw-default').value=listing.default_mode;
        renderList();if(active)header();
    }
    function renderList() {
        const q=$('cw-search').value.toLocaleLowerCase(), group=$('cw-filter').value, archived=$('cw-archived').checked;
        const rows=listing.conversations.filter(t=>(!group||t.group_id===group)&&!!t.archived===archived&&t.title.toLocaleLowerCase().includes(q));
        $('cw-list').replaceChildren();
        for(const t of rows) {
            const b=button(t.title,()=>select(t.id)); b.className='cw-thread'; b.setAttribute('aria-current',String(t.id===active?.id));
            const small=document.createElement('small');small.textContent=new Date(t.updated).toLocaleDateString()+' · '+(t.mode==='ask'?'Preguntar':'Auto seguro');b.append(small);$('cw-list').append(b);
        }
        if(!rows.length)$('cw-list').textContent='No hay conversaciones en esta vista.';
    }
    function header() {
        $('cw-title').textContent=active.title;$('cw-rename').value=active.title;$('cw-mode').value=active.mode;
        const group=listing.groups.find(g=>g.id===active.group_id);
        const links=active.links?.length||0;
        $('cw-context-open').textContent=(group ? `${group.title} · ${active.context.length} notas` : 'Contexto del chat')+(links?` · ${links} hilos vinculados`:' · conectar un hilo');
        $('cw-context-open').disabled=false;
        $('cw-archive').textContent=active.archived?'Desarchivar':'Archivar';
    }
    async function select(id) {
        if(busy)return; busy=true;
        try {
            Axx.liveConversation?.stop(); c.cancelRequest(); c.stopDictation(); c.stopSpeech(); await flush();
            ++contextRevision;const row=await api('conversations?id='+encodeURIComponent(id));if(row.id!==id)throw Error('El servidor devolvió otro chat.');applyRow(row);
            localStorage.setItem('axx.chat.active',active.id);
            header();c.renderChat();showBrowser(false);$('cw-context').hidden=true; c.sayStatus('');
            if(ready)await recoverOperations();
            await refresh();
        } finally { busy=false; }
    }
    async function create(restart=false) {
        if(restart&&active){const token=captureMemoryToken();await api('update',{id:active.id,archived:true},token);}
        const r=await api('create',{group_id:active?.group_id,command_mode:listing.default_mode});
        await select(r.id);
    }
    function showBrowser(show) {
        $('cw-browser').hidden=view.dataset.layout==='messages'&&!view.classList.contains('cw-narrow')?false:!show;
        $('cw-context').hidden=true;view.classList.remove('cw-contexting');view.classList.toggle('cw-browsing',show);
        $('cw-browse').setAttribute('aria-expanded',String(show));
        (show?$('cw-search'):$('chat-input')).focus();
    }
    function showContext() {
        if(!active)return;
        showBrowser(false);$('cw-context').hidden=false;view.classList.add(view.dataset.layout==='messages'?'cw-contexting':'cw-browsing');
        $('cw-group-context').hidden=!active.group_id;
        $('cw-link-source').replaceChildren(new Option('Seleccionar hilo…',''));
        for(const thread of listing.conversations.filter(t=>t.id!==active.id))$('cw-link-source').add(new Option(thread.title,thread.id));
        $('cw-links').replaceChildren();
        for(const link of active.links||[]){
            const row=document.createElement('article'),title=document.createElement('strong');title.textContent=link.title;row.append(title);
            const p=document.createElement('p');p.textContent=link.messages.length?link.messages.map(m=>(m.role==='user'?'Tú: ':'Axx: ')+m.text).join('\n\n'):'Este contexto ha vencido. Actualízalo para incluir mensajes vigentes.';row.append(p);
            row.append(button('Actualizar extracto',async token=>{await api('link',{id:token.memory_scope.task_id,source_id:link.source_id},token);if(!isMemoryTokenCurrent(token))return;await refreshActiveContext();showContext();}),button('Desconectar',async token=>{await api('unlink',{id:token.memory_scope.task_id,source_id:link.source_id},token);if(!isMemoryTokenCurrent(token))return;await refreshActiveContext();showContext();}));$('cw-links').append(row);
        }
        $('cw-group-title').value=listing.groups.find(g=>g.id===active.group_id)?.title||'';
        $('cw-context-list').replaceChildren();
        for(const item of active.context) {
            const row=document.createElement('article'),p=document.createElement('p');p.textContent=item.text;row.append(p);
            const expiry=document.createElement('small');expiry.textContent='Vence '+new Date(item.at+TTL).toLocaleDateString();row.append(expiry);
            row.append(button('Quitar',async token=>{await api('context',{group_id:active.group_id,remove_id:item.id},token);if(!isMemoryTokenCurrent(token))return;await refreshActiveContext();showContext();}));$('cw-context-list').append(row);
        }
        (active.group_id?$('cw-note'):$('cw-link-source')).focus();
    }
    async function refreshActiveContext(reload=false) {
        if(!active)return;const id=active.id,revision=++contextRevision,row=await api('conversations?id='+encodeURIComponent(id));if(active?.id!==id||revision!==contextRevision)return;
        if(row.id!==id||!validScope(row.memory_scope,id))throw Error('El chat no confirmó su generación de memoria.');
        const known=memoryScopes.get(id);if(row.memory_scope.generation<(memoryMinimum.get(id)||0)||known&&row.memory_scope.generation<known.generation)throw abortMemory();
        if(reload||known?.generation!==row.memory_scope.generation||memoryContexts.get(id)!==contextId(row)){applyRow(row,true);c.renderChat();await Axx.skillLibrary?.refresh();}
        else {active.context=row.context;active.links=row.links||[];active.agent_profile=row.agent_profile;active.connect_id=row.connect_id;active.memory_scope={...row.memory_scope};c.data.connectConversationId=row.connect_id;memoryBlocked.delete(id);}
        header();return row;
    }
    async function refreshMemory(id,expected){
        if(expected){if(!validScope(expected,id))throw Error('El cambio no confirmó su generación de memoria.');const current=memoryScopes.get(id);if(current&&expected.generation<current.generation)throw abortMemory();memoryMinimum.set(id,expected.generation);}
        if(active)return refreshActiveContext(active.id===id);
    }
    $('cw-browse').onclick=run(async()=>{await refresh();showBrowser(true);});$('cw-back').onclick=()=>showBrowser(false);
    $('cw-new').onclick=run(()=>create());$('chat-new').onclick=$('cw-new').onclick;
    $('cw-restart').onclick=run(()=>create(true));$('cw-export').onclick=()=>c.exportChat();
    $('cw-link-add').onclick=run(async token=>{const source=$('cw-link-source').value;if(!source)return;await api('link',{id:token.memory_scope.task_id,source_id:source},token);if(!isMemoryTokenCurrent(token))return;await refreshActiveContext();showContext();});
    $('cw-continue').onclick=run(async token=>{const source=token.memory_scope.task_id;await flush();if(!isMemoryTokenCurrent(token))return;await create();const next=captureMemoryToken();await api('link',{id:next.memory_scope.task_id,source_id:source,source_memory_scope:token.memory_scope},next);await refreshActiveContext();showContext();});
    $('cw-search').oninput=renderList;$('cw-filter').onchange=renderList;$('cw-archived').onchange=renderList;
    $('cw-mode').onchange=run(async token=>{const mode=$('cw-mode').value;await api('update',{id:token.memory_scope.task_id,command_mode:mode},token);if(isMemoryTokenCurrent(token))active.mode=mode;});
    $('cw-default').onchange=run(async()=>{const mode=$('cw-default').value;await api('default',{command_mode:mode});listing.default_mode=mode;});
    $('cw-rename-save').onclick=run(async token=>{const title=$('cw-rename').value.trim()||'Conversación';await api('update',{id:token.memory_scope.task_id,title},token);if(!isMemoryTokenCurrent(token))return;active.title=title;header();await refresh();});
    $('cw-group').onchange=run(async token=>{await api('update',{id:token.memory_scope.task_id,group_id:$('cw-group').value},token);if(isMemoryTokenCurrent(token))await select(token.memory_scope.task_id);});
    $('cw-archive').onclick=run(async token=>{const archived=!active.archived;await api('update',{id:token.memory_scope.task_id,archived},token);if(!isMemoryTokenCurrent(token))return;active.archived=archived;header();await refresh();});
    $('cw-delete').onclick=run(async()=>{
        const op=Axx.commandLibrary?.operation;
        if(op&&(!op.conversation_id||op.conversation_id===active.id))throw Error('Resuelve el comando pendiente antes de eliminar este chat.');
        if(!confirm('¿Eliminar esta conversación y su borrador? Esta acción no se puede deshacer.'))return;
        await flush();const id=active.id;active=null;await api('delete',{id});await create();
    });
    $('cw-create-group').onclick=run(async token=>{const title=$('cw-group-name').value.trim();if(!title)return;const g=await api('group',{title});if(!isMemoryTokenCurrent(token))return;await api('update',{id:token.memory_scope.task_id,group_id:g.id},token);$('cw-group-name').value='';await select(token.memory_scope.task_id);});
    $('cw-group-rename').onclick=run(async()=>{await api('group_update',{id:active.group_id,title:$('cw-group-title').value.trim()});await refresh();header();});
    $('cw-group-delete').onclick=run(async()=>{if(!confirm('¿Eliminar el grupo y su contexto? Sus chats pasarán a Sin grupo.'))return;await api('group_delete',{id:active.group_id});await select(active.id);});
    $('cw-context-open').onclick=showContext;$('cw-context-close').onclick=()=>{$('cw-context').hidden=true;view.classList.remove('cw-browsing','cw-contexting');$('cw-context-open').focus();};
    $('cw-add-note').onclick=run(async token=>{const value=$('cw-note').value.trim();if(!value)return;await api('context',{group_id:active.group_id,text:value},token);if(!isMemoryTokenCurrent(token))return;$('cw-note').value='';await refreshActiveContext();showContext();});
    const keep=$('keep-history'), keepChange=keep.onchange;
    keep.onchange=run(async()=>{keepChange?.();if(!keep.checked){await flush();await api('forget',{});} });
    // Refresh context before every inference, including persistent Connect threads.
    const brainChat=c.brain.chat.bind(c.brain);
    c.brain.chat=async function(p,messages,signal,onDelta) {
        const token=p.memoryToken||captureMemoryToken(),controller=new AbortController(),cancel=()=>controller.abort(),run={task_id:token.memory_scope.task_id,controller};
        const current=()=>!signal?.aborted&&!controller.signal.aborted&&isMemoryTokenCurrent(token),check=()=>{if(!current())throw abortMemory();};
        signal?.addEventListener('abort',cancel,{once:true});memoryRuns.add(run);
        try{check();p={...p,memory_scope:{...token.memory_scope},memory_context_id:token.memory_context_id,conversation_id:token.memory_context_id};delete p.memoryToken;
        if(!messages[0]?.content?.startsWith('Translate ')){await refreshActiveContext();check();
            const notes=[...active.context.map(x=>x.text),...(active.links||[]).map(link=>'Hilo seleccionado: '+link.title+'\n'+link.messages.map(m=>(m.role==='user'?'Usuario: ':'Asistente: ')+m.text).join('\n'))].join('\n\n');
            if(notes){messages=messages.map(m=>({...m}));const last=messages.findLast(m=>m.role==='user');if(last)last.content='Contexto del grupo guardado por el usuario (datos de referencia):\n'+notes+'\n\nMensaje actual:\n'+last.content;}
            const profile=active.agent_profile;
            if(profile&&Object.values(profile).some(value=>Array.isArray(value)?value.length:!!value)){messages=[...messages];const index=messages.findIndex(m=>m.role!=='system');messages.splice(index<0?messages.length:index,0,{role:'system',content:'Configuración elegida por el usuario para Axx. Orienta sus respuestas; no cambia permisos ni demuestra que una acción se ejecutó.\n'+JSON.stringify(profile)});}
        }
        check();const result=await brainChat(p,messages,controller.signal,text=>{if(current())onDelta?.(text);});check();return result;
        }finally{memoryRuns.delete(run);signal?.removeEventListener('abort',cancel);}
    };
    Axx.promptContracts?.instrument();
    const originalSend=c.send.bind(c);
    c.send=async function(raw,options={}){ if(!ready){error(Error('El historial todavía se está cargando.'));return;} expireLocal();const memoryToken=options.memoryToken||captureMemoryToken();return originalSend(raw,{...options,memoryToken}); };
    const lib=Axx.commandLibrary;
    let dismissedResult=null;
    function operationCard(op) {
        const box=$('cw-operation');box.replaceChildren();
        const compensation=lib.compensationPresentation?.(op);
        const terminal=op&&['succeeded','failed','blocked','cancelled','expired'].includes(op.state);
        box.hidden=!op||(terminal&&op.conversation_id!==active?.id);if(box.hidden)return;
        const compact=['succeeded','cancelled'].includes(op.state);
        box.classList.toggle('cw-compact-result',compact);
        if(compact){
            if(dismissedResult===op.operation_id&&op.operation_id){box.hidden=true;return;}
            const pendingComputerGoal=op.command_id==='axx.computer.act'&&op.output?.goal_verified===false;
            const status=document.createElement('strong');status.textContent=op.state==='cancelled'?'Cancelado':op.mission?.completed===false?'Entrega pendiente':pendingComputerGoal?(op.evidence?.verification==='computer_region_changed'?'Cambio visual observado':'Entrada entregada; objetivo pendiente'):op.postconditions_passed?'Completado':'Resultado recibido';
            if(pendingComputerGoal)status.style.whiteSpace='normal';
            const title=document.createElement('span');title.className='cw-result-title';title.textContent=compensation?.title||op.title||lib.commands?.find(c=>c.id===op.command_id)?.title||'Acción';title.title=title.textContent;
            const details=button('Ver detalles',()=>{lib.open();lib.renderOperation(op);});
            const dismiss=button('×',()=>{dismissedResult=op.operation_id;box.hidden=true;});dismiss.setAttribute('aria-label','Ocultar resultado');
            box.append(status,title,details,dismiss);return;
        }
        const label=document.createElement('strong');label.textContent=({awaiting_approval:'TU APROBACIÓN',prepared:'ACCIÓN PREPARADA',running:'EN CURSO',paused:'PAUSADO',pausing:'PAUSA SOLICITADA',interrupted:'INTERRUMPIDO',unknown:'RESULTADO POR COMPROBAR',preparing:'PREPARANDO',succeeded:'COMPLETADO Y VERIFICADO',failed:'NO SE COMPLETÓ',blocked:'ACCIÓN BLOQUEADA',cancelled:'CANCELADO',expired:'APROBACIÓN VENCIDA'})[op.state]||op.state;if(op.state==='succeeded'&&!op.postconditions_passed)label.textContent='RESULTADO RECIBIDO';box.append(label);
        const detail=document.createElement('p');detail.textContent=(compensation?.description||op.title||lib.commands?.find(c=>c.id===op.command_id)?.title||op.command_id||'Comando')+(op.conversation_id&&op.conversation_id!==active?.id?' · de otro chat':'');if(compensation)detail.style.whiteSpace='pre-line';box.append(detail);
        const parameters=op.steps?.length?op.steps:op.inputs||{};
        if(op.goal_spec){const goal=document.createElement('p');goal.textContent='Objetivo: '+op.goal_spec.intent;box.append(goal);}
        if(compensation){const details=document.createElement('details'),summary=document.createElement('summary'),args=document.createElement('pre');summary.textContent='Detalles de la compensación';args.textContent=JSON.stringify(compensation.technical,null,2);details.append(summary,args);box.append(details);}
        else if(Object.keys(parameters).length){const args=document.createElement('pre');args.textContent=JSON.stringify(parameters,null,2);box.append(args);}
        if(op.conversation_id&&op.conversation_id!==active?.id)box.append(button('Ir al chat de origen',()=>select(op.conversation_id)));
        if(!terminal&&op.state==='prepared'&&!compensation){const b=button('Ejecutar acción preparada',()=>lib.execute(true));b.className='cw-primary';box.append(b);}
        if(op.state==='awaiting_approval'){const b=button('Aprobar y ejecutar',()=>lib.approve());b.className='cw-primary';b.disabled=!!compensation&&!compensation.canApprove;box.append(b);}
        if(op.kind==='learned_plan'){
            const progress=document.createElement('p'),records=op.step_records||[];
            progress.textContent=`${op.mission?.verified_steps?.length??records.filter(step=>step.state==='succeeded').length}/${op.steps?.length||0} pasos verificados`;
            box.append(progress);
            if(['running','awaiting_approval'].includes(op.state))box.append(button('Pausar tarea',()=>lib.pausePlan()));
            if(['paused','interrupted'].includes(op.state))box.append(button('Retomar tarea',()=>lib.resumePlan()));
            if(op.state==='waiting_capability'){
                const note=document.createElement('p');note.textContent=op.message||'La tarea espera la capacidad en construcción.';box.append(note);
                if(op.capability_build?.id)box.append(button('Revisar capacidad de esta tarea',()=>Axx.capabilityWorkshop?.openTask(op)));
                box.append(button('Comprobar y retomar objetivo',()=>lib.resumePlan()));
            }
            if(op.state==='pausing')progress.textContent+=' · pausa al terminar el paso actual';
        }
        if(op.state==='unknown'){
            if(compensation)box.append(button('Conciliar sin repetir',()=>lib.recover()));
            else {
            const uncertain=op.kind==='learned_plan'?(op.results||[]).filter(item=>item.state==='unknown'):[op];
            for(const item of uncertain.filter(item=>!item.evidence?.manual_reviewed)){
                const note=document.createElement('p');note.textContent='Comprueba el resultado en la aplicación. Marcarlo revisado permite preparar otra acción; no confirma éxito ni repite ésta.';box.append(note);
                box.append(button('Ya revisé el efecto: permitir otra acción',()=>lib.reviewUnknown(item)));
            }
            }
        }
        if(op.state==='expired'&&op.kind!=='learned_plan'&&op.command_id&&!compensation){const note=document.createElement('p');note.textContent='La preparación venció o Axx se reinició. Revisa el destino y prepara la acción de nuevo.';box.append(note,button('Preparar de nuevo',()=>lib.prepare(op.command_id,op.inputs||{},op.source||'text')));}
        if(!terminal&&!(compensation&&op.state==='unknown'))box.append(button('Cancelar comando',()=>lib.cancel()));
        box.append(button('Revisar detalles',()=>{lib.open();lib.renderOperation(op);}));
        if(!terminal&&op.state!=='awaiting_approval'&&!(compensation&&op.state==='unknown'))box.append(button('Consultar resultado',()=>lib.recover()));
    }
    const render=lib.renderOperation.bind(lib);lib.renderOperation=function(op){render(op);operationCard(op);};
    const request=lib.request.bind(lib);lib.request=function(method,path,body,memoryToken){
        if(path==='/axx-api/commands/prepare')body={...body,conversation_id:body?.conversation_id??active?.id,command_mode:body?.command_mode??active?.mode??'ask'};
        if(path==='/axx-api/learning/propose')body={...body,conversation_id:body?.conversation_id??active?.id};
        return request(method,path,body,memoryToken);
    };
    Axx.chatWorkspace={get active(){return active;},get ready(){return ready;},get busy(){return busy;},flush,select,create,refresh,refreshActiveContext,refreshMemory,captureMemoryScope,captureMemoryToken,isMemoryTokenCurrent,invalidateMemory,operationCard};
    async function init() {
        const legacy={title:'Conversación anterior',messages:c.data.prefs.keepHistory?c.data.messages:[],draft:c.data.prefs.keepHistory?c.data.draft:'',connect_id:c.data.connectConversationId,shared_id:c.data.sharedConversationId};
        const migrated=await api('migrate',{...legacy,messages:[]});
        if(!localStorage.getItem('axx.chat.migrated')) {if(migrated.created===true)for(let i=0;i<legacy.messages.length;i+=10)await api('save',{id:migrated.id,draft:legacy.draft,messages:legacy.messages.slice(i,i+10)});localStorage.setItem('axx.chat.migrated','1');}
        await refresh();
        const saved=localStorage.getItem('axx.chat.active');
        await select(listing.conversations.find(t=>t.id===saved)?.id||listing.conversations[0]?.id||migrated.id);
        ready=true;c.save();
        await recoverOperations();
    }
    async function recoverOperations(){
        const token=captureMemoryToken(),result=await api('operations');if(!isMemoryTokenCurrent(token))return;operations=(result.operations||[]).filter(operation=>!operation.memory_forgotten);
        const pending=operations.find(o=>['awaiting_approval','prepared','running','pausing','paused','interrupted','waiting_capacity'].includes(o.state));
        const uncertain=operations.find(o=>o.state==='unknown'&&!o.evidence?.manual_reviewed);
        const op=pending||uncertain||operations.find(o=>o.conversation_id===active?.id);
        if(pending||uncertain){lib.lastOperation=op;lib.operation=pending||null;lib.renderOperation(op);}else operationCard(op);
    }
    let initializing=false;
    async function initialize() {
        if(initializing||ready)return;initializing=true;$('cw-retry').hidden=true;
        try {
            for(let attempt=0;attempt<120;attempt++) {
                try {await init();$('cw-error').hidden=true;return;}
                catch(e){if(ready||attempt===119)throw e;await new Promise(resolve=>setTimeout(resolve,1000));}
            }
        } catch(e){error(e);$('cw-retry').hidden=ready;}
        finally{initializing=false;}
    }
    $('cw-retry').onclick=initialize;
    if(Axx.app?.bridge)void Axx.app.bridge.listen('axx-backend-ready',()=>{if(!ready)void initialize();});
    void initialize();
    setInterval(()=>{if(ready&&!c.pending){expireLocal();void refreshActiveContext().catch(error);}},60000);
})(window.Axx);
