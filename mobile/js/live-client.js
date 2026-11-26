/* Operational entrypoint: only confirmed desktop responses, no demo fallbacks. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const transport = window.Capacitor?.Plugins?.AxxTransport;
  let paired = false, online = false, busy = false, refreshing = false, avatar, conversationId, linking = false;
  let pending = null, desktopAppearance=null, pointer=null, interactionUntil=0;
  let messageKey='', catalogKey='', lastCatalogAt=0;
  let homeIconKey='',homeIconUpdating=false;
  let serverEpoch='', eventCursor=0, eventsSupported=false, eventsLoopRunning=false, lastRefreshAt=0;
  let chatAvailable=true, currentMessages=[];
  const motionPreference=localStorage.getItem('axx.mobile.motion') || 'system';
  try { pending = JSON.parse(localStorage.getItem('axx.mobile.pending') || 'null'); } catch {}
  $('draft').value = localStorage.getItem('axx.mobile.draft') || '';
  $('draft').oninput = () => localStorage.setItem('axx.mobile.draft', $('draft').value);
  const errorText = e => e?.message || String(e);
  const notice = text => { $('notice').textContent = text; };
  function syncState(state, text) {
    $('sync-status').hidden = false;
    $('sync-status').dataset.state = state;
    $('sync-text').textContent = state==='complete'?'Sincronizado':text;
  }
  const request = async (path, body) => {
    if (!transport) throw new Error('Abre Axx Mobile instalada en Android para conectarte.');
    const response = await transport.request({path, method: body ? 'POST' : 'GET', ...(body ? {body} : {})});
    return response.data;
  };
  function connection(connected, text) {
    online = connected;
    if(!connected){window.dispatchEvent(new Event('axxOffline'));}
    document.body.dataset.online=String(connected);
    $('connection-state').textContent = text;
    $('pc-dot').classList.toggle('online', connected);
    $('send').disabled = !connected || !conversationId || conversationId==='main' || !chatAvailable || !!pending || busy;
    $('recover').hidden = !pending;
    forgetDelivery.hidden = !pending;
    if (!connected && $('sync-status').dataset.state === 'complete') syncState('offline','Sin conexión · se conserva la última apariencia recibida');
  }
  let inputActive=false, avatarAdaptiveEco=false, slowFrames=0, fastFrames=0;
  const avatarFrameSamples=[];
  function syncAvatarLoop(){
    if(!avatar)return;
    const visible=!document.hidden && !$('pane-axx').hidden && !inputActive;
    avatar.setHidden(!visible);
    if(visible){avatar.resize();avatar.startLoop();}
    else avatar.stop();
  }
  function pane(name) {
    for (const section of document.querySelectorAll('.live-pane')) section.hidden = section.id !== 'pane-'+name;
    for (const button of document.querySelectorAll('[data-pane]')) {
      if (button.dataset.pane === name) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    }
    syncAvatarLoop();
    if (name === 'chat') $('messages').scrollTop=$('messages').scrollHeight;
    if (name === 'work') void refreshWorkCatalog();
    window.scrollTo(0,0);
  }
  function characterIcon() {
    const host=document.createElement('div'),canvas=document.createElement('canvas');
    host.className='icon-render-stage';host.append(canvas);document.body.append(host);
    let renderer;
    try {
      renderer=new Axx.SoftwareRenderer(canvas,{...avatar.settings,quality:'eco',scale:1,staticMode:true,reducedMotion:true});
      renderer.setStudio(avatar.getStudio());renderer.setCamera20([-.18,.08]);renderer.setFinish(avatar.finish);renderer.draw(0);
      return canvas.toDataURL('image/png');
    }finally{renderer?.stop();renderer?.observer?.disconnect();host.remove();}
  }
  let homeIconTimer=0;
  function syncHomeIcon(value){
    if(!transport?.updateHomeIcon || homeIconUpdating)return;
    // Camera motion and activity must not redraw the launcher icon every second.
    const key=JSON.stringify([value.settings,value.studio,value.finish]);
    if(key===homeIconKey)return;
    clearTimeout(homeIconTimer);
    homeIconTimer=setTimeout(async()=>{
      homeIconTimer=0;
      if(homeIconUpdating || key===homeIconKey)return;
      homeIconUpdating=true;
      try{await transport.updateHomeIcon({png:characterIcon()});homeIconKey=key;}
      catch(e){notice('No se pudo actualizar el acceso de inicio: '+errorText(e)+'. Se reintentará al recibir el estado de la PC.');}
      finally{homeIconUpdating=false;}
    }, 120);
  }
  function buildMessageNode(message) {
    const node = document.createElement('div');
    node.className = 'message ' + message.role;
    if (message.id) node.dataset.messageId = message.id;
    const label = document.createElement('small');
    label.textContent = (message.role === 'user' ? 'Tú' : 'Axx') + ' · ' + (message.source === 'mobile' ? 'Teléfono' : 'PC');
    const body = document.createElement('span');
    body.className = 'message-text';
    body.textContent = message.text || '';
    node.append(label, body);
    return node;
  }
  function renderMessages(messages) {
    const list = Array.isArray(messages) ? messages : [];
    const key = JSON.stringify(list);
    if (key === messageKey) return;
    messageKey = key;
    currentMessages = list.slice();
    const log = $('messages'), follow = log.scrollHeight - log.scrollTop - log.clientHeight < 48;
    if (!list.length) {
      const p = document.createElement('p');
      p.textContent = 'Todavía no hay mensajes compartidos.';
      log.replaceChildren(p);
      return;
    }
    const existingById = new Map();
    for (const child of Array.from(log.children)) {
      if (child.dataset?.messageId) existingById.set(child.dataset.messageId, child);
      else child.remove();
    }
    const desiredIds = new Set(list.map(m => m.id).filter(Boolean));
    for (const [id, el] of existingById) {
      if (!desiredIds.has(id)) { el.remove(); existingById.delete(id); }
    }
    let prev = null;
    for (const message of list) {
      let node = message.id ? existingById.get(message.id) : null;
      if (node) {
        const expectedClass = 'message ' + message.role;
        if (node.className !== expectedClass) node.className = expectedClass;
        const body = node.querySelector('.message-text');
        if (body && body.textContent !== (message.text || '')) body.textContent = message.text || '';
      } else {
        node = buildMessageNode(message);
        if (message.id) existingById.set(message.id, node);
      }
      const expectedNext = prev ? prev.nextSibling : log.firstChild;
      if (node !== expectedNext) log.insertBefore(node, expectedNext);
      prev = node;
    }
    if (follow) log.scrollTop = log.scrollHeight;
  }
  function upsertLiveMessage(message) {
    if (!message || !message.id) return;
    if (message.conversation_id && conversationId && message.conversation_id !== conversationId) return;
    const index = currentMessages.findIndex(m => m.id === message.id);
    if (index >= 0) {
      currentMessages[index] = { ...currentMessages[index], ...message };
    } else {
      currentMessages.push(message);
      if (currentMessages.length > 200) currentMessages = currentMessages.slice(-200);
    }
    renderMessages(currentMessages);
  }
  function appendChatDelta(ev) {
    if (!ev || !ev.message_id || typeof ev.delta !== 'string') return;
    if (ev.conversation_id && conversationId && ev.conversation_id !== conversationId) return;
    const existing = currentMessages.find(m => m.id === ev.message_id);
    const nextText = (existing ? existing.text : '') + ev.delta;
    upsertLiveMessage({ id: ev.message_id, role: 'assistant', source: 'pc', text: nextText, conversation_id: ev.conversation_id || conversationId, at: Date.now() });
  }
  function phaseLabel(phase, detail) {
    const labels = {
      understood: 'Entendí tu orden',
      planning: 'Entendí → Preparando plan…',
      preparing: 'Entendí → Preparando…',
      awaiting_approval: 'Preparado · requiere aprobación en la PC',
      executing: 'Entendí → Preparando → Ejecutando…',
      verifying: 'Ejecutando → Verificando resultado…',
      completed: 'Verificado · terminado',
      succeeded: 'Ejecutado y verificado en tu PC',
      failed: 'No se pudo completar',
      outcome_unknown: 'Entrega sin confirmar. Revisa el PC antes de repetir.'
    };
    const base = labels[phase] || detail || '';
    return detail && labels[phase] && !detail.includes(labels[phase]) ? base + ' · ' + detail : base;
  }
  function updateModelDisplay(inference, modelStatus) {
    $('model-state').textContent = inference?.selection_mode === 'automatic_free'
      ? 'Automático gratis'
      : inference?.model || (modelStatus === 'unconfigured' ? 'Modelo sin configurar en PC' : 'Modelo de tu PC');
  }
  function renderRows(id, items, empty, kind) {
    const nodes = items.map(item => {
      const row = document.createElement('div'); row.className = kind;
      const title = document.createElement('strong'); title.textContent = item.title || item.name || item.tool_name || item.command_id || item.operation_id || item.id;
      const detail = document.createElement('small'); detail.textContent = kind === 'tool' ? item.description || '' : [item.state || item.status, item.operation_id || item.id].filter(Boolean).join(' · ');
      row.append(title, detail); return row;
    });
    if (!nodes.length) { const p=document.createElement('p'); p.textContent=empty; nodes.push(p); }
    $(id).replaceChildren(...nodes);
  }
  async function recover() {
    if (!pending) return;
    const task = await request('/v1/command?command_id='+encodeURIComponent(pending.command_id));
    $('command-state').textContent = chatReceipt(task);
    if (['completed','failed','outcome_unknown'].includes(task.state)) {
      if (task.state !== 'completed') notice(task.result?.error?.message || 'Resultado sin confirmar. Revisa la tarea en la PC antes de repetir.');
      if (task.state === 'completed' && $('draft').value === pending.text) { $('draft').value=''; localStorage.removeItem('axx.mobile.draft'); }
      pending=null; localStorage.removeItem('axx.mobile.pending');
      avatar?.setState('idle'); $('avatar-state').textContent='Idle';
    }
  }
  async function pollEventsLoop() {
    if (eventsLoopRunning || !paired || !online || !eventsSupported || document.hidden) return;
    eventsLoopRunning = true;
    try {
      while (paired && online && eventsSupported && !document.hidden) {
        const res = await request('/v1/events?after=' + encodeURIComponent(String(eventCursor)));
        if (!res || typeof res !== 'object') break;
        if (res.server_epoch && serverEpoch && res.server_epoch !== serverEpoch) {
          serverEpoch = res.server_epoch;
          await refresh();
          continue;
        }
        if (res.server_epoch && !serverEpoch) serverEpoch = res.server_epoch;
        if (res.resync_required) {
          await refresh();
          continue;
        }
        if (typeof res.cursor === 'number' && res.cursor >= eventCursor) eventCursor = res.cursor;
        if (Array.isArray(res.events)) {
          let shouldRecover = false, shouldRefreshTasks = false;
          for (const ev of res.events) {
            if (!ev || !ev.type) continue;
            if (ev.type === 'chat.message.created') upsertLiveMessage(ev.data);
            else if (ev.type === 'chat.delta') appendChatDelta(ev.data);
            else if (ev.type === 'chat.completed') {
              if (ev.data?.message) upsertLiveMessage(ev.data.message);
              shouldRecover = true;
            } else if (ev.type === 'appearance.changed' && ev.data?.appearance) {
              applyAppearance(ev.data.appearance);
            } else if (ev.type === 'grant.changed' && Array.isArray(ev.data?.scopes)) {
              renderScopes(ev.data.scopes);
              if (!$('pane-work').hidden) void refreshWorkCatalog();
            } else if (ev.type === 'model.changed') {
              updateModelDisplay(ev.data?.inference, ev.data?.model_status);
            } else if (ev.type === 'operation.changed') {
              const label = phaseLabel(ev.data?.phase || ev.data?.state, ev.data?.summary || '');
              if (label) $('command-state').textContent = label;
              if (['completed', 'succeeded', 'failed', 'outcome_unknown', 'awaiting_approval'].includes(ev.data?.state)) {
                shouldRecover = true;
                shouldRefreshTasks = true;
              }
            }
          }
          if (shouldRecover && pending) {
            try { await recover(); } catch {}
          }
          if (shouldRefreshTasks) {
            try {
              const tasks = await request('/v1/tasks');
              renderRows('tasks', tasks.operations || [], 'Todavía no hay operaciones registradas.', 'task');
            } catch {}
          }
        }
      }
    } catch (e) {
      if (/404|Unknown route/i.test(errorText(e))) eventsSupported = false;
    } finally {
      eventsLoopRunning = false;
    }
  }
  async function refresh() {
    if (!paired || refreshing || document.hidden || $('pair-submit').disabled && !linking) return false;
    refreshing=true;
    try {
      const [statusRes, snapshotRes, tasksRes] = await Promise.allSettled([
        request('/v1/status'),
        request('/v1/snapshot'),
        request('/v1/tasks')
      ]);
      if (statusRes.status !== 'fulfilled') throw statusRes.reason;
      const status = statusRes.value;
      if (!status.ready) throw new Error('El motor de Axx no está disponible');
      try{await recover();}
      catch(e){$('command-state').textContent='El envío sigue sin confirmar: '+errorText(e)+'. Revisa la PC antes de repetirlo.';}
      if (snapshotRes.status !== 'fulfilled') throw snapshotRes.reason;
      const snapshot = snapshotRes.value;
      conversationId = snapshot.conversation_id;
      chatAvailable = snapshot.chat_available !== undefined ? !!snapshot.chat_available : (!!conversationId && conversationId !== 'main');
      if (typeof snapshot.cursor === 'number') eventCursor = snapshot.cursor;
      if (snapshot.server_epoch) serverEpoch = snapshot.server_epoch;
      eventsSupported = snapshot.capabilities?.events_stream === true;
      renderMessages(snapshot.messages); applyAppearance(snapshot.appearance);
      if(Array.isArray(snapshot.scopes))renderScopes(snapshot.scopes);
      if(snapshot.pc_name)$('pc-name').textContent=snapshot.pc_name;
      updateModelDisplay(snapshot.inference, snapshot.model_status);
      $('draft-state').textContent = (snapshot.chat_blocked_reason === 'history_disabled' || conversationId === 'main')
        ? 'Activa «Guardar historial» en el chat del PC para compartirlo.'
        : snapshot.chat_blocked_reason === 'no_conversation'
          ? 'Selecciona una conversación guardada en Axx del PC para chatear.'
          : 'Chat del PC · mismas aprobaciones';
      const timeLabel = new Date().toLocaleTimeString('es',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
      $('connection-detail').textContent = 'Última respuesta autenticada · ' + timeLabel + (snapshot.always_on === false ? ' · Consejo: activa «Mantener conexión» en tu PC' : '');
      if (tasksRes.status === 'fulfilled') {
        renderRows('tasks', tasksRes.value.operations || [], 'Todavía no hay operaciones registradas.', 'task');
      } else {
        $('tasks').textContent = 'No se pudo cargar la actividad: ' + errorText(tasksRes.reason);
      }
      lastRefreshAt = Date.now();
      connection(true, 'Conectado');
      window.dispatchEvent(new CustomEvent('axxSnapshot',{detail:{appearance:snapshot.appearance,scopes:snapshot.scopes,capabilities:snapshot.capabilities,device_id:currentDevice,fingerprint:currentFingerprint,conversation_id:snapshot.conversation_id}}));
      if(pendingWork)await checkWork(false);
      if(!$('pane-work').hidden && Date.now()-lastCatalogAt>10000)await refreshWorkCatalog();
      if (linking) {
        if (!snapshot.appearance) throw new Error('La PC todavía no comparte su apariencia. Pulsa Actualizar para reintentar.');
        syncState('complete', 'Tu Axx está sincronizado'); linking=false;
        $('avatar-state').textContent='El mismo Axx de tu PC';
      }
      if(snapshot.appearance && !linking)syncState('complete','Sincronizado con tu PC');
      if (eventsSupported && !eventsLoopRunning) void pollEventsLoop();
      return true;
    } catch(e) { connection(false, 'Sin conexión · '+errorText(e)); if(linking)syncState('error','Sincronización pendiente. Reintentando al recuperar la conexión.');return false; }
    finally { refreshing=false; }
  }
  function showPair() { $('pair-error').textContent=''; if(!$('pair-dialog').open)$('pair-dialog').showModal(); $('scan-qr').focus(); }
  function previewPair(uri){
    const link=new URL(uri);
    if(link.protocol!=='axx:' || link.hostname!=='pair' || link.username || link.password || link.port || link.pathname || link.hash ||
       [...link.searchParams].length!==3 || !['endpoint','fingerprint','code'].every(name=>link.searchParams.getAll(name).length===1) ||
       !/^[a-f0-9]{64}$/.test(link.searchParams.get('fingerprint')) || !/^[A-Za-z0-9_-]{20,128}$/.test(link.searchParams.get('code')))
      throw new Error('Este no es un QR válido de Axx. Genera uno nuevo en Ajustes de tu PC.');
    const endpoint=new URL(link.searchParams.get('endpoint'));
    if(endpoint.protocol!=='https:')throw new Error('Axx requiere una conexión HTTPS segura.');
    $('pair-uri').value=uri;$('pair-preview').hidden=false;$('pair-preview').textContent='PC · '+endpoint.host;
    $('pair-error').textContent='QR listo. Confirma que reconoces esta PC.';$('pair-submit').focus();
  }
  async function incomingPair(){
    if(!transport?.pairingLink)return;
    try{const link=await transport.pairingLink();if(link.uri){showPair();previewPair(link.uri);}}
    catch(e){$('pair-error').textContent=errorText(e);}
  }
  window.addEventListener('axxPairingLink',()=>void incomingPair());
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void incomingPair();});
  void incomingPair();
  for (const id of ['pc-button','open-pair']) $(id).onclick=showPair;
  $('pair-dialog').addEventListener('cancel',event=>{if($('pair-submit').disabled)event.preventDefault();});
  $('pair-close').onclick=()=>{ $('pair-dialog').close(); $('pair-uri').value=''; $('pair-preview').hidden=true; };
  $('scan-qr').onclick=async()=>{
    const button=$('scan-qr');button.disabled=true;
    try{if(!transport)throw new Error('Instala Axx Mobile en Android para escanear.');const scanned=await transport.scan();previewPair(scanned.uri);}
    catch(e){$('pair-error').textContent=errorText(e);}
    finally{button.disabled=false;}
  };
  $('pair-form').onsubmit=async event=>{
    event.preventDefault(); if($('pair-submit').disabled)return; $('pair-submit').disabled=true; $('scan-qr').disabled=true; $('pair-close').disabled=true;
    try { if (!transport) throw new Error('Instala Axx Mobile en Android para enlazar.');
      $('pair-error').textContent='Verificando la identidad de tu PC…';
      previewPair($('pair-uri').value.trim());
      const next=await transport.pair({uri:$('pair-uri').value.trim()});
      if(next?.device_id && currentDevice && next.device_id!==currentDevice){
        pending=null;localStorage.removeItem('axx.mobile.pending');setPendingWork(null);
      }
      $('pair-uri').value=''; $('pair-dialog').close();
      notice('');pane('axx');window.scrollTo(0,0);linking=true;syncState('syncing','Sincronizando tu personaje y conversación…');
      await profile(); await refresh(); }
    catch(e){ $('pair-error').textContent=errorText(e); }
    finally { $('pair-submit').disabled=false; $('scan-qr').disabled=false; $('pair-close').disabled=false; }
  };
  $('chat-form').onsubmit=async event=>{
    event.preventDefault(); const text=$('draft').value.trim(); if(!text || pending || busy || !online)return;
    if(window.AxxTransfer?.handleText(text)){$('draft').value='';localStorage.removeItem('axx.mobile.draft');return;}
    pending={command_id:crypto.randomUUID(), operation:'chat', text, conversation_id:conversationId}; localStorage.setItem('axx.mobile.pending',JSON.stringify(pending));
    busy=true; connection(online,'Enviando a la PC principal…'); avatar?.setState('thinking'); $('avatar-state').textContent='Axx procesando en PC';
    try { const task=await request('/v1/commands',pending); $('command-state').textContent=chatReceipt(task); }
    catch(e){notice('No se confirmó el envío. '+errorText(e)+' Tu borrador sigue guardado.');}
    finally {busy=false; await refresh();}
  };
  const forgetDelivery=document.createElement('button');forgetDelivery.type='button';forgetDelivery.id='forget-delivery';forgetDelivery.hidden=!pending;forgetDelivery.textContent='Descartar seguimiento del envío';
  $('recover').after(forgetDelivery);
  forgetDelivery.onclick=()=>{
    if(!window.confirm('Esto solo descarta el seguimiento del teléfono. El envío puede seguir en la PC. Revisa su conversación y actividad antes de repetirlo.'))return;
    pending=null;localStorage.removeItem('axx.mobile.pending');connection(online,$('connection-state').textContent);
    $('command-state').textContent='Seguimiento descartado. El borrador se conserva; no se ha reenviado ni cancelado ninguna orden en la PC.';
  };
  $('recover').onclick=()=>refresh(); $('refresh').onclick=()=>paired?refresh():showPair();
  function chatReceipt(task){return ({queued:'Enviado al PC',running:'Axx está respondiendo…',completed:'Respuesta recibida',failed:'No se pudo completar',outcome_unknown:'Entrega sin confirmar. Revisa el PC antes de repetir.'})[task.state]||'Pendiente de confirmar en tu PC';}
  let pendingWork=null;try{pendingWork=JSON.parse(localStorage.getItem('axx.mobile.pendingWork')||'null');}catch{}
  if(!pendingWork||typeof pendingWork.operation_id!=='string'||typeof pendingWork.command_id!=='string')pendingWork=null;
  const forgetWork=document.createElement('button');forgetWork.type='button';forgetWork.textContent='Olvidar seguimiento';forgetWork.disabled=!pendingWork;
  $('work-refresh').insertAdjacentElement('afterend',forgetWork);
  const setPendingWork=value=>{pendingWork=value;forgetWork.disabled=!value;if(value)localStorage.setItem('axx.mobile.pendingWork',JSON.stringify(value));else localStorage.removeItem('axx.mobile.pendingWork');};
  forgetWork.onclick=()=>{
    if(!pendingWork)return;
    if(!window.confirm('Esto solo quita el seguimiento en el teléfono. La orden puede seguir pendiente en la PC. Revisa Axx antes de enviar otra.'))return;
    setPendingWork(null);workStatus('Seguimiento local descartado. Comprueba la actividad y las aprobaciones en la PC.');
  };
  const workStatus=text=>{$('work-status').textContent=text;};
  const commandCard=document.createElement('section');commandCard.className='live-card';commandCard.id='work-commands-card';
  commandCard.innerHTML='<h2>Orden para tu PC</h2><form id="work-text-form"><label for="work-text" class="sr-only">Orden</label><textarea id="work-text" rows="2" maxlength="8000" required placeholder="Ej.: estado del sistema"></textarea><button type="submit" class="primary">Enviar orden</button></form><details><summary>Todas las herramientas</summary><form id="work-generic-form"><label for="work-command-select">Comando</label><select id="work-command-select"></select><p id="work-command-description" class="hint"></p><div id="work-command-fields"></div><button type="submit">Preparar comando</button></form></details>';
  $('pane-work').insertBefore(commandCard,$('pane-work').children[1]||null);
  let workCatalog=[];
  const workSelect=$('work-command-select'),workFields=$('work-command-fields');
  const filterLabel=document.createElement('label');filterLabel.htmlFor='work-command-filter';filterLabel.textContent='Buscar una herramienta de tu PC';
  const filter=document.createElement('input');filter.id='work-command-filter';filter.type='search';filter.placeholder='Nombre o función…';filter.maxLength=200;
  workSelect.before(filterLabel,filter);
  function filterCommands(){
    const previous=workSelect.value, query=filter.value.trim().toLocaleLowerCase();
    workSelect.replaceChildren(...workCatalog.filter(row=>[row.title,row.id,row.description].join(' ').toLocaleLowerCase().includes(query)).map(row=>new Option(row.title+' · '+row.id,row.id)));
    if([...workSelect.options].some(option=>option.value===previous))workSelect.value=previous;
    renderCommandFields();
  }
  filter.oninput=filterCommands;
  function renderCommandFields(){
    const command=workCatalog.find(row=>row.id===workSelect.value);
    workFields.replaceChildren();$('work-command-description').textContent=command?(command.description+(command.pc_approval_required?' · Requiere aprobación en la PC.':'')):'';
    if(!command)return;
    for(const [name,rule] of Object.entries(command.parameters)){
      const label=document.createElement('label');label.textContent=name;
      let input;
      if(Array.isArray(rule.enum)){input=document.createElement('select');for(const value of rule.enum)input.add(new Option(value,value));}
      else if(rule.type==='boolean'){input=document.createElement('input');input.type='checkbox';}
      else if(['object','array'].includes(rule.type)){input=document.createElement('textarea');input.dataset.jsonType=rule.type;input.placeholder=rule.type==='array'?'[]':'{}';}
      else if(name==='script'||name==='content'){input=document.createElement('textarea');input.rows=name==='script'?5:3;}
      else{input=document.createElement('input');input.type=['integer','number'].includes(rule.type)?'number':'text';if(rule.type==='number')input.step='any';}
      input.dataset.field=name;input.required=rule.required===true && rule.type!=='boolean';
      if(rule.maxLength)input.maxLength=rule.maxLength;
      if(rule.minimum!==undefined)input.min=rule.minimum;
      if(rule.maximum!==undefined)input.max=rule.maximum;
      label.append(input);workFields.append(label);
    }
  }
  async function refreshWorkCatalog(){
    if(!online)return;
    try{
      const result=await request('/v1/work/catalog');
      lastCatalogAt=Date.now();
      const key=JSON.stringify(result.commands);if(key===catalogKey)return;catalogKey=key;
      workCatalog=Array.isArray(result.commands)?result.commands:[];
      filterCommands();
    }catch(e){catalogKey='';workCatalog=[];filterCommands();$('work-command-description').textContent='Aprueba Work para este teléfono en la PC: '+errorText(e);}
  }
  workSelect.onchange=renderCommandFields;
  if(pendingWork)workStatus('Hay una operación pendiente de comprobar. Pulsa «Actualizar actividad».');
  const workResult=result=>{$('work-result').textContent=JSON.stringify({state:result.state,postconditions_passed:result.postconditions_passed,output:result.output,evidence:result.evidence,error:result.error},null,2);};
  const workReceipt=result=>result.pc_approval_required || result.state==='awaiting_approval'?'Pendiente de aprobación en la PC.':result.state==='succeeded' && result.postconditions_passed===true?'Ejecutado y verificado en tu PC.':'Estado: '+result.state+'. Revisa el resultado antes de repetir.';
  async function checkWork(refreshAfter=true){
    if(!pendingWork){await refresh();return;}
    try{
      const result=await request('/v1/work/operation?operation_id='+encodeURIComponent(pendingWork.operation_id));
      workResult(result);workStatus(workReceipt(result));
      if(['succeeded','failed','blocked','cancelled','expired'].includes(result.state))setPendingWork(null);
      if(refreshAfter)await refresh();
    }catch(e){workStatus('No se pudo confirmar la operación. No la repetiré automáticamente: '+errorText(e));}
  }
  async function runWork(command_id,inputs,approved=false){
    if(!paired||!online){workStatus('Primero conecta el teléfono con la PC.');return;}
    if(pendingWork){workStatus('Hay una operación sin confirmar. Pulsa «Actualizar actividad» antes de enviar otra.');return;}
    const operation_id=crypto.randomUUID();setPendingWork({operation_id,command_id});
    workStatus('Enviando '+command_id+' a la PC…');
    try{
      const result=await request('/v1/work/execute',{command_id,inputs,operation_id,approved});
      workResult(result);workStatus(workReceipt(result));
      if(['succeeded','failed','blocked','cancelled','expired'].includes(result.state))setPendingWork(null);
      await refresh();
    }catch(e){workStatus('Entrega sin confirmar: '+errorText(e)+'. Pulsa «Actualizar actividad»; no se repetirá automáticamente.');}
  }
  $('work-health').onclick=()=>void runWork('axx.system.telemetry',{});
  $('work-text-form').onsubmit=async e=>{
    e.preventDefault();const text=$('work-text').value.trim();if(!text)return;
    if(window.AxxTransfer?.handleText(text))return;
    try{
      const resolved=await request('/v1/work/resolve',{text});
      if(resolved.match!=='exact'||!resolved.command_id){workStatus(resolved.message||'No reconozco esa orden. Elige un comando en la lista.');return;}
      if(!workCatalog.some(row=>row.id===resolved.command_id)){workStatus('Ese comando está documentado, pero no tiene un ejecutor disponible.');return;}
      await runWork(resolved.command_id,resolved.inputs||{});
    }catch(error){workStatus('No se pudo preparar la orden: '+errorText(error));}
  };
  $('work-generic-form').onsubmit=e=>{
    e.preventDefault();const inputs={};
    try{
      for(const field of workFields.querySelectorAll('[data-field]')){
        if(!field.required && field.type!=='checkbox' && field.value==='')continue;
        const value=field.dataset.jsonType?JSON.parse(field.value):field.type==='checkbox'?field.checked:field.type==='number'?Number(field.value):field.value;
        if(field.dataset.jsonType && (field.dataset.jsonType==='array'?!Array.isArray(value):!value || typeof value!=='object' || Array.isArray(value)))throw new Error('Revisa el JSON de '+field.dataset.field);
        inputs[field.dataset.field]=value;
      }
      void runWork(workSelect.value,inputs);
    }catch(error){workStatus('Parámetros inválidos: '+errorText(error));}
  };
  $('work-app-form').onsubmit=e=>{e.preventDefault();void runWork('axx.desktop.open_app',{app:$('work-app').value});};
  $('work-search-form').onsubmit=e=>{e.preventDefault();const query=$('work-search').value.trim();if(query)void runWork('axx.desktop.search',{query,engine:$('work-engine').value});};
  $('work-note-form').onsubmit=e=>{
    e.preventDefault();const name=$('work-note-name').value.trim(),content=$('work-note-content').value;
    if(!/^[^\\/<>:"|?*\x00-\x1f.][^\\/<>:"|?*\x00-\x1f]{0,99}$/.test(name)||name.endsWith('.')){workStatus('Usa un nombre de archivo válido, sin carpetas ni caracteres reservados.');return;}
    if(!content.trim()){workStatus('Escribe el contenido de la nota.');return;}
    if(!window.confirm('Crear el archivo nuevo «'+name+'» en los artefactos de Axx de la PC?\n\nVista previa:\n'+content.slice(0,500))){workStatus('Creación cancelada.');return;}
    void runWork('axx.artifact.write',{path:name,content},true);
  };
  $('work-refresh').onclick=()=>{void checkWork();void refreshWorkCatalog();};
  $('pin-shortcut').onclick=async()=>{
    const button=$('pin-shortcut');button.disabled=true;
    try {
      if(!avatar || !transport)throw new Error('El personaje todavía no está disponible.');
      const result=await transport.shortcut({png:characterIcon()});
      notice(result.requested?'Confirma Añadir en Android. Si el inicio está bloqueado, desbloquea su diseño y reintenta.':'Personaje del acceso de inicio actualizado.');
    }catch(e){notice(errorText(e));}finally{button.disabled=false;}
  };
  $('forget').onclick=async()=>{try{
    if(!window.confirm('¿Olvidar esta PC? Las operaciones ya enviadas pueden seguir en la PC. Revisa su actividad antes de repetirlas.'))return;
    await transport.forget();paired=false;conversationId=null;currentDevice='';currentFingerprint='';pending=null;setPendingWork(null);
    for(const key of ['pending','appearance','draft','device'])localStorage.removeItem('axx.mobile.'+key);
    $('draft').value='';$('messages').replaceChildren();messageKey='';currentMessages=[];eventCursor=0;serverEpoch='';eventsSupported=false;workCatalog=[];catalogKey='';filterCommands();
    connection(false,'PC olvidada. Puedes revocar este teléfono en la PC.');$('identity').textContent='Sin PC enlazada';$('pc-name').textContent='Enlazar PC';renderScopes([]);
  }catch(e){notice(errorText(e));}};
  document.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>pane(b.dataset.pane));
  $('open-chat').onclick=()=>{pane('chat');$('draft').focus();};
  $('character-options').onclick=()=>{if(!$('character-dialog').open)$('character-dialog').showModal();};
  $('character-close').onclick=()=>$('character-dialog').close();
  const textSize=$('text-size');
  textSize.disabled=!transport?.textSize;
  if(transport?.textSize){
    transport.textSize().then(value=>{textSize.value=value.mode;textSize.dataset.confirmed=value.mode;}).catch(e=>notice('No se pudo consultar el tamaño de texto: '+errorText(e)));
    textSize.onchange=async()=>{textSize.disabled=true;try{const value=await transport.textSize({mode:textSize.value});textSize.value=value.mode;textSize.dataset.confirmed=value.mode;avatar?.resize();}catch(e){textSize.value=textSize.dataset.confirmed||'standard';notice('No se pudo cambiar el texto: '+errorText(e));}finally{textSize.disabled=false;}};
  }
  let currentDevice=localStorage.getItem('axx.mobile.device')||'',currentFingerprint='';
  function renderScopes(scopes){
    $('scopes').replaceChildren(...[['query','Conversación y estado'],['tools.control','Comandos y herramientas'],['input.control','Ratón, teclado y gestos'],['voice','Micrófono remoto']].map(([scope,label])=>{
      const row=document.createElement('div');row.className='permission-row';row.dataset.granted=String(scopes.includes(scope));
      const name=document.createElement('strong');name.textContent=label;const value=document.createElement('span');value.textContent=scopes.includes(scope)?'Permitido':'Aprobar en PC';row.append(name,value);return row;
    }));
  }
  async function profile(){
    const info=await transport.profile(); paired=info.paired;
    if(paired){currentDevice=info.device_id||currentDevice;currentFingerprint=info.fingerprint||'';if(currentDevice)localStorage.setItem('axx.mobile.device',currentDevice);$('pc-name').textContent=new URL(info.endpoint).hostname; $('identity').textContent=info.endpoint+' · Identidad SHA-256: '+info.fingerprint;renderScopes(info.scopes||[]);}
    return info;
  }
  let appearanceKey='';
  $('avatar-motion').value=motionPreference;
  $('avatar-motion').onchange=()=>{localStorage.setItem('axx.mobile.motion',$('avatar-motion').value);appearanceKey='';if(desktopAppearance)applyAppearance(desktopAppearance);};
  let avatarMode='',gestureQueue=[],gestureSending=false,gestureTimer=0;
  function gestureStatus(text){$('avatar-remote-status').textContent=text;}
  async function sendGestures(){
    if(gestureSending)return;gestureSending=true;
    try{
      while(gestureQueue.length){
        const next=gestureQueue.shift();
        await request('/v1/avatar/gesture',next);
        gestureStatus(next.kind==='end'?'Gesto reflejado en la PC':'Sincronizando '+(next.kind==='rotate'?'rotación':'movimiento')+' con la PC…');
      }
    }catch(e){gestureQueue=[];gestureStatus('La PC no recibió el gesto: '+errorText(e)+'. Aprueba este teléfono en Axx de la PC.');}
    finally{gestureSending=false;if(gestureQueue.length)queueGestureSend();}
  }
  function queueGestureSend(){if(gestureTimer)return;gestureTimer=setTimeout(()=>{gestureTimer=0;void sendGestures();},32);}
  function gesture(kind,dx=0,dy=0){
    if(!paired){gestureStatus('Empareja este teléfono con el QR de la PC.');return;}
    const last=gestureQueue.at(-1),x=Math.max(-200,Math.min(200,dx)),y=Math.max(-200,Math.min(200,dy));
    if(kind!=='end'&&last?.kind===kind&&Math.abs(last.dx+x)<=200&&Math.abs(last.dy+y)<=200){last.dx+=x;last.dy+=y;}
    else gestureQueue.push({kind,dx:x,dy:y});
    if(gestureQueue.length>64){gestureQueue=[];gestureStatus('La conexión está lenta. Vuelve a mover Axx.');return;}
    queueGestureSend();
  }
  function setAvatarMode(mode){
    avatarMode=avatarMode===mode?'':mode;
    $('avatar-interact').setAttribute('aria-pressed',String(avatarMode==='rotate'));
    $('avatar-move').setAttribute('aria-pressed',String(avatarMode==='move'));
    $('axx-avatar-canvas').classList.toggle('interactive',!!avatarMode);
    $('avatar-help').textContent=avatarMode==='rotate'?'Arrastra Axx para girarlo aquí y en la PC.':avatarMode==='move'?'Arrastra Axx para moverlo en la pantalla de la PC.':'Activa Girar o Mover y arrastra Axx con el dedo.';
    gestureStatus(avatarMode?$('avatar-help').textContent:'');
    if($('character-dialog').open)$('character-dialog').close();
  }
  $('avatar-interact').onclick=()=>setAvatarMode('rotate');
  $('avatar-move').onclick=()=>setAvatarMode('move');
  function reactToTouch(){avatar?.react();interactionUntil=Date.now()+1800;$('avatar-state').textContent='Axx responde a tu toque';}
  const canvas=$('axx-avatar-canvas');
  canvas.onpointerdown=event=>{
    if(!event.isPrimary)return;
    pointer={id:event.pointerId,x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,drag:false};
    if(canvas.classList.contains('interactive'))canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove=event=>{
    if(!pointer || pointer.id!==event.pointerId || !canvas.classList.contains('interactive'))return;
    const dx=event.clientX-pointer.x,dy=event.clientY-pointer.y;
    if(Math.hypot(event.clientX-pointer.startX,event.clientY-pointer.startY)>5)pointer.drag=true;
    if(pointer.drag){
      if(avatarMode==='rotate'){avatar?.rotate(dx*.012,dy*.012);avatar?.draw(avatar.lastTime||0);$('avatar-state').textContent='Girando con tu dedo';}
      else $('avatar-state').textContent='Moviendo Axx en tu PC';
      interactionUntil=Date.now()+5000;gesture(avatarMode,dx,dy);
    }
    pointer.x=event.clientX;pointer.y=event.clientY;
  };
  canvas.onpointerup=event=>{if(pointer?.id!==event.pointerId)return;if(pointer.drag&&avatarMode)gesture('end');if(!pointer.drag && Math.hypot(event.clientX-pointer.startX,event.clientY-pointer.startY)<8)reactToTouch();pointer=null;};
  canvas.onpointercancel=()=>{if(pointer?.drag&&avatarMode)gesture('end');pointer=null;};
  canvas.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();reactToTouch();}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();avatar.rotate(event.key==='ArrowLeft'?-.15:event.key==='ArrowRight'?.15:0,event.key==='ArrowUp'?-.15:event.key==='ArrowDown'?.15:0);avatar.draw(avatar.lastTime||0);interactionUntil=Date.now()+5000;}};
  function applyAppearance(value){
    if(!value || !avatar)return;
    desktopAppearance=value;
    const cameraLocked=interactionUntil>Date.now();
    const preference=$('avatar-motion').value;
    const reduced=preference==='paused' || preference==='system' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const still=reduced || value.settings?.reducedMotion || value.settings?.staticMode || value.studio?.living===false;
    const quality = still ? 'balanced' : (avatar.accelerated && !avatarAdaptiveEco) ? 'balanced' : 'eco';
    const settings=window.Axx.normalizeSettings({...value.settings, quality, reducedMotion:reduced || value.settings?.reducedMotion});
    const state=value.activity?.state;
    if(state && window.Axx.MOTION_PROFILES[state])avatar.setState(pending?'thinking':state);
    const label=({idle:'Aquí estoy',thinking:'Pensando',speaking:'Hablando',listening:'Escuchando',processing:'Procesando'})[avatar.state] || avatar.state;
    $('avatar-state').textContent=label;
    $('avatar-pc-state').textContent=value.activity?'PC: '+(({idle:'Idle',thinking:'Thinking',listening:'Listening',speaking:'Speaking',processing:'Processing',approval:'Approval',paused:'Paused',success:'Success',error:'Error',notification:'Notification',focus:'Focus',transform:'Transform',offline:'Offline',cancelled:'Cancelled'})[state] || label)+' · '+(value.activity.moving?'moving':'still'):'';
    const key=JSON.stringify([settings,value.studio,value.camera,value.finish,preference,cameraLocked]);if(key===appearanceKey){void syncHomeIcon(value);return;}
    const structuralKey=JSON.stringify([settings,value.studio,value.finish]);
    if(JSON.stringify(avatar.settings)!==JSON.stringify(settings))avatar.configure(settings);if(avatar.form!==settings.form)avatar.setForm(settings.form);if(JSON.stringify(avatar.getStudio())!==JSON.stringify(value.studio))avatar.setStudio(value.studio||{});if(!cameraLocked)avatar.setCamera20(Array.isArray(value.camera)?[value.camera[0]%(Math.PI*2),value.camera[1]]:value.camera);if(avatar.finish!==(value.finish||'obsidian'))avatar.setFinish(value.finish||'obsidian');if(!avatar.hidden)avatar.draw(avatar.lastTime || 0);appearanceKey=key;
    if(structuralKey!==lastStoredAppearanceKey){lastStoredAppearanceKey=structuralKey;localStorage.setItem('axx.mobile.appearance',JSON.stringify(value));}
    void syncHomeIcon(value);
  }
  let lastStoredAppearanceKey='', lastFrameDrawnAt=0, avatarFrameCapFps=60;
  try {const settings={...window.Axx.DEFAULT_SETTINGS,quality:'eco',reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches};avatar=new window.Axx.MobileRenderer($('axx-avatar-canvas'),settings);avatar.startLoop();window.axxMobileRenderer=avatar;} catch(e){notice('La animación no está disponible; puedes seguir usando los controles. '+errorText(e));}
  if(avatar){
    const origDraw=avatar.draw.bind(avatar);
    avatar.draw=function(time){
      const now=performance.now();
      const budgetGap=avatarFrameCapFps<60 ? (1000/avatarFrameCapFps) : 0;
      if(budgetGap && !pointer?.drag && lastFrameDrawnAt && (now-lastFrameDrawnAt)<budgetGap && typeof time==='number' && time>0){
        return;
      }
      lastFrameDrawnAt=now;
      origDraw(time);
      if(typeof avatar.drawMs==='number' && Number.isFinite(avatar.drawMs) && !avatar.hidden){
        avatarFrameSamples.push(avatar.drawMs);
        if(avatarFrameSamples.length>120)avatarFrameSamples.shift();
        const animated=avatar.accelerated && !avatar.settings?.reducedMotion && !avatar.settings?.staticMode && avatar.moving?.();
        if(animated){
          // Cap decorative FPS to ~30 on budget mobile GPUs so UI taps and navigation stay snappy.
          if(avatarFrameSamples.length>=12){
            const recent=avatarFrameSamples.slice(-12);
            const avg=recent.reduce((a,b)=>a+b,0)/recent.length;
            if(avg>11 && avatarFrameCapFps===60)avatarFrameCapFps=30;
            else if(avg<6 && avatarFrameCapFps===30)avatarFrameCapFps=60;
          }
          if(avatar.drawMs>28){slowFrames++;fastFrames=0;}
          else if(avatar.drawMs<14){fastFrames++;slowFrames=0;}
          else{slowFrames=0;fastFrames=0;}
          if(!avatarAdaptiveEco && slowFrames>=15){avatarAdaptiveEco=true;slowFrames=0;appearanceKey='';if(desktopAppearance)applyAppearance(desktopAppearance);}
          else if(avatarAdaptiveEco && fastFrames>=30){avatarAdaptiveEco=false;fastFrames=0;appearanceKey='';if(desktopAppearance)applyAppearance(desktopAppearance);}
        }
      }
    };
  }
  window.axxAvatarTelemetry=()=>{
    const sorted=[...avatarFrameSamples].sort((a,b)=>a-b);
    const pct=p=>sorted.length?Math.round(sorted[Math.min(sorted.length-1,Math.max(0,Math.ceil(sorted.length*p)-1))]*10)/10:0;
    return {samples:sorted.length,p50_ms:pct(.5),p95_ms:pct(.95),max_ms:sorted.length?Math.round(sorted[sorted.length-1]*10)/10:0,
      quality:avatar?.settings?.quality||null,adaptive_eco:avatarAdaptiveEco,frame_cap_fps:avatarFrameCapFps,accelerated:!!avatar?.accelerated,paused_for_input:inputActive};
  };
  window.addEventListener('axxInputActive',e=>{inputActive=!!e.detail?.active;syncAvatarLoop();});
  try{const cached=JSON.parse(localStorage.getItem('axx.mobile.appearance') || 'null');if(cached)applyAppearance(cached);}catch{}
  window.addEventListener('resize',()=>avatar?.resize());
  document.addEventListener('visibilitychange',()=>{syncAvatarLoop();if(!document.hidden){void refresh();}});
  setInterval(()=>{if(inputActive)return;if(!eventsLoopRunning || Date.now()-lastRefreshAt>=10000)void refresh();},2000);
  window.addEventListener('online',()=>void refresh());
  window.addEventListener('offline',()=>connection(false,'Sin red · tus borradores siguen guardados'));
  if(transport) profile().then(()=>refresh()).catch(e=>notice(errorText(e)));
  else notice('Vista previa. Para conectar de forma segura necesitas la app Android.');
})();
