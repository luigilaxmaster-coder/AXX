/* Conversation UI over the authenticated native store. Companion remains the renderer. */
(function (Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.isNative()) return;
    const c = Axx.companion, $ = id => document.getElementById(id), view = $('view-chat');
    const api = (action, body) => Axx.backendRequest(body === undefined ? 'GET' : 'POST', '/axx-api/chat/' + action, body);
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
    let chain = Promise.resolve(), timer, busy = false, operations=[];
    const originalSave = c.save.bind(c), originalRender = c.renderChat.bind(c), originalAttachment=c.renderAttachment.bind(c);
    c.renderAttachment=function(){if(this.attachment&&!this.attachment.at)this.attachment.at=Date.now();originalAttachment();if(ready)this.save();};
    function error(e) { $('cw-error').hidden = false; $('cw-error').textContent = e.message || String(e); }
    function run(fn) { return async () => { try { $('cw-error').hidden=true; await fn(); } catch(e) { error(e); } }; }
    function button(label, fn) { const b=document.createElement('button'); b.type='button'; b.textContent=label; b.onclick=run(fn); return b; }
    function expireLocal() {
        c.data.messages=c.data.messages.filter(m=>m.at>Date.now()-TTL);
        if(c.attachment?.at<=Date.now()-TTL){c.attachment=null;c.renderAttachment();}
        if(active?.draft_at<=Date.now()-TTL){$('chat-input').value='';c.data.draft='';}
    }
    $('chat-input').addEventListener('input',()=>{if(active)active.draft_at=Date.now();});
    function snapshot() { expireLocal();return {id:active?.id,messages:c.data.prefs.keepHistory ? c.data.messages : [],attachment:c.data.prefs.keepHistory?c.attachment:null,draft:c.data.prefs.keepHistory ? $('chat-input').value : ''}; }
    async function flush() {
        clearTimeout(timer);
        if (!ready || !active) return chain;
        const body=snapshot();
        const task=chain.catch(()=>{}).then(async()=>{ for(let i=0;i<Math.max(body.messages.length,1);i+=10) await api('save',{...body,messages:body.messages.slice(i,i+10)}); }); chain=task;
        await task;
        if(active?.id===body.id&&active.title==='Nueva conversación'&&body.messages.some(m=>m.role==='user')){const row=await api('conversations?id='+encodeURIComponent(body.id));if(active?.id===body.id){active.title=row.title;header();await refresh();}}
    }
    c.save = function () {
        if (!ready) return originalSave();
        // The durable transcript lives only in SQLite after migration acknowledgement.
        const messages=this.data.messages, draft=this.data.draft;
        this.data.messages=[]; this.data.draft='';
        try { originalSave(); } finally { this.data.messages=messages; this.data.draft=draft; }
        clearTimeout(timer); timer=setTimeout(()=>void flush().catch(error),150);
    };
    c.renderChat = function () { originalRender(); decorateMessages(); };
    function decorateMessages() {
        if (!active?.group_id) return;
        for (const row of $('chat-log').querySelectorAll('[data-message-id]')) {
            if(row.querySelector('.cw-pin'))continue;
            const m=c.data.messages.find(m=>m.id===row.dataset.messageId);
            if(!m || m.status!=='complete')continue;
            const b=button('Guardar en contexto del grupo',async()=>{
                if(m.text.length>4000) { $('cw-note').value=m.text.slice(0,4000); showContext(); return; }
                await api('context',{group_id:active.group_id,text:m.text}); await refreshActiveContext(); showContext();
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
            active=await api('conversations?id='+encodeURIComponent(id));
            c.data.messages=(c.data.prefs.keepHistory?active.messages:[]).map(m=>m.status==='pending'?{...m,status:'interrupted'}:m);
            if(!c.data.prefs.keepHistory)active.draft='';
            c.data.draft=active.draft;c.data.connectConversationId=active.connect_id;c.data.sharedConversationId=active.shared_id;
            c.attachment=c.data.prefs.keepHistory?active.attachment:null;c.renderAttachment();$('chat-input').value=active.draft;
            localStorage.setItem('axx.chat.active',active.id);
            header();c.renderChat();showBrowser(false);$('cw-context').hidden=true; c.sayStatus('');
            if(ready)await recoverOperations();
            await refresh();
        } finally { busy=false; }
    }
    async function create(restart=false) {
        if(restart&&active)await api('update',{id:active.id,archived:true});
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
            row.append(button('Actualizar extracto',async()=>{await api('link',{id:active.id,source_id:link.source_id});await refreshActiveContext();showContext();}),button('Desconectar',async()=>{await api('unlink',{id:active.id,source_id:link.source_id});await refreshActiveContext();showContext();}));$('cw-links').append(row);
        }
        $('cw-group-title').value=listing.groups.find(g=>g.id===active.group_id)?.title||'';
        $('cw-context-list').replaceChildren();
        for(const item of active.context) {
            const row=document.createElement('article'),p=document.createElement('p');p.textContent=item.text;row.append(p);
            const expiry=document.createElement('small');expiry.textContent='Vence '+new Date(item.at+TTL).toLocaleDateString();row.append(expiry);
            row.append(button('Quitar',async()=>{await api('context',{group_id:active.group_id,remove_id:item.id});await refreshActiveContext();showContext();}));$('cw-context-list').append(row);
        }
        (active.group_id?$('cw-note'):$('cw-link-source')).focus();
    }
    async function refreshActiveContext() { const id=active.id; const row=await api('conversations?id='+encodeURIComponent(id));if(active.id!==id)return;active.context=row.context;active.links=row.links||[];active.agent_profile=row.agent_profile;active.connect_id=row.connect_id;c.data.connectConversationId=row.connect_id;header(); }
    $('cw-browse').onclick=run(async()=>{await refresh();showBrowser(true);});$('cw-back').onclick=()=>showBrowser(false);
    $('cw-new').onclick=run(()=>create());$('chat-new').onclick=$('cw-new').onclick;
    $('cw-restart').onclick=run(()=>create(true));$('cw-export').onclick=()=>c.exportChat();
    $('cw-link-add').onclick=run(async()=>{const source=$('cw-link-source').value;if(!source)return;await api('link',{id:active.id,source_id:source});await refreshActiveContext();showContext();});
    $('cw-continue').onclick=run(async()=>{await flush();const source=active.id;await create();await api('link',{id:active.id,source_id:source});await refreshActiveContext();showContext();});
    $('cw-search').oninput=renderList;$('cw-filter').onchange=renderList;$('cw-archived').onchange=renderList;
    $('cw-mode').onchange=run(async()=>{await api('update',{id:active.id,command_mode:$('cw-mode').value});active.mode=$('cw-mode').value;});
    $('cw-default').onchange=run(async()=>{const mode=$('cw-default').value;await api('default',{command_mode:mode});listing.default_mode=mode;});
    $('cw-rename-save').onclick=run(async()=>{await api('update',{id:active.id,title:$('cw-rename').value.trim()||'Conversación'});active.title=$('cw-rename').value.trim()||'Conversación';header();await refresh();});
    $('cw-group').onchange=run(async()=>{await api('update',{id:active.id,group_id:$('cw-group').value});await select(active.id);});
    $('cw-archive').onclick=run(async()=>{await api('update',{id:active.id,archived:!active.archived});active.archived=!active.archived;header();await refresh();});
    $('cw-delete').onclick=run(async()=>{
        const op=Axx.commandLibrary?.operation;
        if(op&&(!op.conversation_id||op.conversation_id===active.id))throw Error('Resuelve el comando pendiente antes de eliminar este chat.');
        if(!confirm('¿Eliminar esta conversación y su borrador? Esta acción no se puede deshacer.'))return;
        await flush();const id=active.id;active=null;await api('delete',{id});await create();
    });
    $('cw-create-group').onclick=run(async()=>{const title=$('cw-group-name').value.trim();if(!title)return;const g=await api('group',{title});await api('update',{id:active.id,group_id:g.id});$('cw-group-name').value='';await select(active.id);});
    $('cw-group-rename').onclick=run(async()=>{await api('group_update',{id:active.group_id,title:$('cw-group-title').value.trim()});await refresh();header();});
    $('cw-group-delete').onclick=run(async()=>{if(!confirm('¿Eliminar el grupo y su contexto? Sus chats pasarán a Sin grupo.'))return;await api('group_delete',{id:active.group_id});await select(active.id);});
    $('cw-context-open').onclick=showContext;$('cw-context-close').onclick=()=>{$('cw-context').hidden=true;view.classList.remove('cw-browsing','cw-contexting');$('cw-context-open').focus();};
    $('cw-add-note').onclick=run(async()=>{const value=$('cw-note').value.trim();if(!value)return;await api('context',{group_id:active.group_id,text:value});$('cw-note').value='';await refreshActiveContext();showContext();});
    const keep=$('keep-history'), keepChange=keep.onchange;
    keep.onchange=run(async()=>{keepChange?.();if(!keep.checked){await flush();await api('forget',{});} });
    // Refresh context before every inference, including persistent Connect threads.
    const brainChat=c.brain.chat.bind(c.brain);
    c.brain.chat=async function(p,messages,signal,onDelta) {
        if(active && !messages[0]?.content?.startsWith('Translate ')){const origin=active.id;await refreshActiveContext();
            if(signal?.aborted||active?.id!==origin)throw new DOMException('La conversación cambió.','AbortError');
            const notes=[...active.context.map(x=>x.text),...(active.links||[]).map(link=>'Hilo seleccionado: '+link.title+'\n'+link.messages.map(m=>(m.role==='user'?'Usuario: ':'Asistente: ')+m.text).join('\n'))].join('\n\n');
            if(notes){messages=messages.map(m=>({...m}));const last=messages.findLast(m=>m.role==='user');if(last)last.content='Contexto del grupo guardado por el usuario (datos de referencia):\n'+notes+'\n\nMensaje actual:\n'+last.content;}
            const profile=active.agent_profile;
            if(profile&&Object.values(profile).some(value=>Array.isArray(value)?value.length:!!value)){messages=[...messages];const index=messages.findIndex(m=>m.role!=='system');messages.splice(index<0?messages.length:index,0,{role:'system',content:'Configuración elegida por el usuario para Axx. Orienta sus respuestas; no cambia permisos ni demuestra que una acción se ejecutó.\n'+JSON.stringify(profile)});}
        }
        return brainChat(p,messages,signal,onDelta);
    };
    const originalSend=c.send.bind(c);
    c.send=async function(...args){ if(!ready){error(Error('El historial todavía se está cargando.'));return;} expireLocal();return originalSend(...args); };
    const lib=Axx.commandLibrary;
    function operationCard(op) {
        const box=$('cw-operation');box.replaceChildren();
        const terminal=op&&['succeeded','failed','blocked','cancelled','expired'].includes(op.state);
        box.hidden=!op||(terminal&&op.conversation_id!==active?.id);if(box.hidden)return;
        const label=document.createElement('strong');label.textContent=({awaiting_approval:'TU APROBACIÓN',prepared:'ACCIÓN PREPARADA',running:'EN CURSO',unknown:'RESULTADO POR COMPROBAR',preparing:'PREPARANDO',succeeded:'COMPLETADO Y VERIFICADO',failed:'NO SE COMPLETÓ',blocked:'ACCIÓN BLOQUEADA',cancelled:'CANCELADO',expired:'APROBACIÓN VENCIDA'})[op.state]||op.state;if(op.state==='succeeded'&&!op.postconditions_passed)label.textContent='RESULTADO RECIBIDO';box.append(label);
        const detail=document.createElement('p');detail.textContent=(op.title||lib.commands?.find(c=>c.id===op.command_id)?.title||op.command_id||'Comando')+(op.conversation_id&&op.conversation_id!==active?.id?' · de otro chat':'');box.append(detail);
        const parameters=op.steps?.length?op.steps:op.inputs||{};
        if(Object.keys(parameters).length){const args=document.createElement('pre');args.textContent=JSON.stringify(parameters,null,2);box.append(args);}
        if(op.conversation_id&&op.conversation_id!==active?.id)box.append(button('Ir al chat de origen',()=>select(op.conversation_id)));
        if(!terminal&&op.state==='prepared'){const b=button('Ejecutar acción preparada',()=>lib.execute(true));b.className='cw-primary';box.append(b);}
        if(op.state==='awaiting_approval'){const b=button('Aprobar y ejecutar',()=>lib.approve());b.className='cw-primary';box.append(b);}
        if(op.state==='expired'&&op.kind!=='learned_plan'&&op.command_id){const note=document.createElement('p');note.textContent='La preparación venció o Axx se reinició. Revisa el destino y prepara la acción de nuevo.';box.append(note,button('Preparar de nuevo',()=>lib.prepare(op.command_id,op.inputs||{},op.source||'text')));}
        if(!terminal)box.append(button('Cancelar comando',()=>lib.cancel()));
        box.append(button('Revisar detalles',()=>{lib.open();lib.renderOperation(op);}));
        if(!terminal&&op.state!=='awaiting_approval')box.append(button('Consultar resultado',()=>lib.recover()));
    }
    const render=lib.renderOperation.bind(lib);lib.renderOperation=function(op){render(op);operationCard(op);};
    const request=lib.request.bind(lib);lib.request=function(method,path,body){
        if(path==='/axx-api/commands/prepare')body={...body,conversation_id:active?.id,command_mode:active?.mode||'ask'};
        if(path==='/axx-api/learning/propose')body={...body,conversation_id:active?.id};
        return request(method,path,body);
    };
    Axx.chatWorkspace={get active(){return active;},get ready(){return ready;},get busy(){return busy;},flush,select,create,refresh,operationCard};
    async function init() {
        const legacy={title:'Conversación anterior',messages:c.data.prefs.keepHistory?c.data.messages:[],draft:c.data.prefs.keepHistory?c.data.draft:'',connect_id:c.data.connectConversationId,shared_id:c.data.sharedConversationId};
        const migrated=await api('migrate',{...legacy,messages:[]});
        if(!localStorage.getItem('axx.chat.migrated')) { for(let i=0;i<legacy.messages.length;i+=10) await api('save',{id:migrated.id,draft:legacy.draft,messages:legacy.messages.slice(i,i+10)}); localStorage.setItem('axx.chat.migrated','1'); }
        await refresh();
        const saved=localStorage.getItem('axx.chat.active');
        await select(listing.conversations.find(t=>t.id===saved)?.id||listing.conversations[0]?.id||migrated.id);
        ready=true;c.save();
        await recoverOperations();
    }
    async function recoverOperations(){
        const result=await api('operations');operations=result.operations||[];
        const pending=operations.find(o=>['awaiting_approval','prepared','running','unknown','interrupted','waiting_capacity'].includes(o.state));
        const op=pending||operations.find(o=>o.conversation_id===active?.id);
        if(pending){lib.lastOperation=pending;lib.operation=pending;lib.renderOperation(pending);}else operationCard(op);
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
