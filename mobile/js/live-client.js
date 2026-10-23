/* Operational entrypoint: only confirmed desktop responses, no demo fallbacks. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const transport = window.Capacitor?.Plugins?.AxxTransport;
  let paired = false, online = false, busy = false, refreshing = false, avatar, conversationId, linking = false;
  let pending = null, desktopAppearance=null, appearanceRefreshing=false, pointer=null, interactionUntil=0;
  let homeIconKey='',homeIconUpdating=false;
  const motionPreference=localStorage.getItem('axx.mobile.motion') || 'system';
  try { pending = JSON.parse(localStorage.getItem('axx.mobile.pending') || 'null'); } catch {}
  $('draft').value = localStorage.getItem('axx.mobile.draft') || '';
  $('draft').oninput = () => localStorage.setItem('axx.mobile.draft', $('draft').value);
  const errorText = e => e?.message || String(e);
  const chatResult=document.createElement('pre');chatResult.className='work-result';chatResult.hidden=true;
  $('command-state').after(chatResult);
  const notice = text => { $('notice').textContent = text; };
  function syncState(state, text) {
    $('sync-status').hidden = false;
    $('sync-status').dataset.state = state;
    $('sync-text').textContent = text;
  }
  const request = async (path, body) => {
    if (!transport) throw new Error('Open the installed Android app to connect to Axx.');
    const response = await transport.request({path, method: body ? 'POST' : 'GET', ...(body ? {body} : {})});
    return response.data;
  };
  function connection(connected, text) {
    online = connected;
    $('connection-state').textContent = text;
    $('pc-dot').classList.toggle('online', connected);
    $('send').disabled = !connected || !!pending || busy;
    $('recover').hidden = !pending;
    if (!connected && $('sync-status').dataset.state === 'complete') syncState('offline','Offline · your last received appearance is saved');
  }
  function pane(name) {
    for (const section of document.querySelectorAll('.live-pane')) section.hidden = section.id !== 'pane-'+name;
    for (const button of document.querySelectorAll('[data-pane]')) {
      if (button.dataset.pane === name) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    }
    avatar?.setHidden(name !== 'axx');
    if (name === 'axx') avatar?.resize();
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
  async function syncHomeIcon(value){
    if(!transport?.updateHomeIcon || homeIconUpdating)return;
    // Camera motion and activity must not redraw the launcher icon every second.
    const key=JSON.stringify([value.settings,value.studio,value.finish]);
    if(key===homeIconKey)return;
    homeIconUpdating=true;
    try{await transport.updateHomeIcon({png:characterIcon()});homeIconKey=key;}
    catch(e){notice('Home shortcut update failed: '+errorText(e)+'. It will retry when the PC state is received.');}
    finally{homeIconUpdating=false;}
  }
  function renderMessages(messages) {
    const nodes = messages.map(message => {
      const node = document.createElement('div'); node.className = 'message '+message.role;
      const label = document.createElement('small'); label.textContent = (message.role === 'user' ? 'You' : 'Axx')+' · '+(message.source === 'mobile' ? 'Phone' : 'PC');
      node.append(label, document.createTextNode(message.text)); return node;
    });
    if (!nodes.length) { const p = document.createElement('p'); p.textContent = 'No shared messages yet.'; nodes.push(p); }
    $('messages').replaceChildren(...nodes);
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
    $('command-state').textContent = 'Task '+task.task_id+' · '+task.state;
    if(task.result?.kind==='work'){
      chatResult.hidden=false;
      chatResult.textContent=task.result.message+(task.result.operation?.output?'\n'+JSON.stringify(task.result.operation.output,null,2).slice(0,6000):'');
    }
    if (['completed','failed','outcome_unknown'].includes(task.state)) {
      if (task.state !== 'completed') notice(task.result?.error?.message || 'Result not confirmed. Check the task on your PC before sending again.');
      if (task.state === 'completed' && $('draft').value === pending.text) { $('draft').value=''; localStorage.removeItem('axx.mobile.draft'); }
      pending=null; localStorage.removeItem('axx.mobile.pending');
      avatar?.setState('idle'); $('avatar-state').textContent='Idle';
    }
  }
  async function refresh() {
    if (!paired || refreshing || document.hidden || $('pair-submit').disabled && !linking) return false;
    refreshing=true;
    try {
      const status = await request('/v1/status');
      if (!status.ready) throw new Error('The Axx engine is unavailable');
      await recover();
      const snapshot = await request('/v1/snapshot'); conversationId = snapshot.conversation_id; renderMessages(snapshot.messages); applyAppearance(snapshot.appearance);
      try{const tasks=await request('/v1/tasks');renderRows('tasks',tasks.operations||[],'Todavía no hay operaciones registradas.','task');}
      catch(e){$('tasks').textContent='No se pudo cargar la actividad: '+errorText(e);}
      connection(true, 'Connected to your PC');
      if (linking) {
        if (!snapshot.appearance) throw new Error('The PC has not shared its appearance yet. Tap Refresh to retry.');
        syncState('complete', 'Your Axx is synchronized'); linking=false;
        $('avatar-state').textContent='The same Axx as on your PC';
      }
      return true;
    } catch(e) { connection(false, 'Refresh failed · '+errorText(e)); if(linking)syncState('error','Sync did not finish. Tap Refresh to retry.');return false; }
    finally { refreshing=false; }
  }
  function showPair() { $('pair-error').textContent=''; if(!$('pair-dialog').open)$('pair-dialog').showModal(); $('scan-qr').focus(); }
  function previewPair(uri){
    const link=new URL(uri);
    if(link.protocol!=='axx:' || link.hostname!=='pair')throw new Error('This is not an Axx pairing QR. Generate one in Axx settings on your PC.');
    const endpoint=new URL(link.searchParams.get('endpoint'));
    if(endpoint.protocol!=='https:')throw new Error('Axx requires a secure PC connection.');
    $('pair-uri').value=uri;$('pair-preview').hidden=false;$('pair-preview').textContent='PC · '+endpoint.host;
    $('pair-error').textContent='QR ready. Confirm this PC to connect.';$('pair-submit').focus();
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
    try{if(!transport)throw new Error('Install the Android app to scan.');const scanned=await transport.scan();previewPair(scanned.uri);}
    catch(e){$('pair-error').textContent=errorText(e);}
    finally{button.disabled=false;}
  };
  $('pair-form').onsubmit=async event=>{
    event.preventDefault(); if($('pair-submit').disabled)return; $('pair-submit').disabled=true; $('scan-qr').disabled=true; $('pair-close').disabled=true;
    try { if (!transport) throw new Error('Install the Android APK to pair.');
      $('pair-error').textContent='Verifying your PC identity…';
      await transport.pair({uri:$('pair-uri').value.trim()}); $('pair-uri').value=''; $('pair-dialog').close();
      notice('');pane('axx');window.scrollTo(0,0);linking=true;syncState('syncing','Syncing your character and conversation…');
      await profile(); await refresh(); }
    catch(e){ $('pair-error').textContent=errorText(e); }
    finally { $('pair-submit').disabled=false; $('scan-qr').disabled=false; $('pair-close').disabled=false; }
  };
  $('chat-form').onsubmit=async event=>{
    event.preventDefault(); const text=$('draft').value.trim(); if(!text || pending || busy || !online)return;
    pending={command_id:crypto.randomUUID(), operation:'chat', text, conversation_id:conversationId}; localStorage.setItem('axx.mobile.pending',JSON.stringify(pending));
    busy=true; connection(online,'Sending to your PC…'); avatar?.setState('thinking'); $('avatar-state').textContent='Waiting for Axx';
    try { const task=await request('/v1/commands',pending); $('command-state').textContent='Task '+task.task_id+' · '+task.state; }
    catch(e){notice('Delivery was not confirmed. '+errorText(e)+' Your draft is still saved.');}
    finally {busy=false; await refresh();}
  };
  $('recover').onclick=()=>refresh(); $('refresh').onclick=()=>paired?refresh():showPair();
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
  commandCard.innerHTML='<h2>Enviar una orden a Axx</h2><p class="hint">Escribe una orden conocida, como «estado del sistema», «abre calculadora», «/powershell Get-Date» o «/cmd dir». Los comandos del sistema necesitan aprobación en la PC.</p><form id="work-text-form"><label for="work-text">Orden</label><textarea id="work-text" rows="3" maxlength="8000" required placeholder="¿Qué quieres que haga Axx en la PC?"></textarea><button type="submit" class="primary">Enviar orden</button></form><details><summary>Todos los comandos ejecutables</summary><p class="hint">Los comandos documentados sin adaptador no se anuncian como ejecutables.</p><form id="work-generic-form"><label for="work-command-select">Comando</label><select id="work-command-select"></select><p id="work-command-description" class="hint"></p><div id="work-command-fields"></div><button type="submit">Preparar comando</button></form></details>';
  $('pane-work').insertBefore(commandCard,$('pane-work').children[1]||null);
  let workCatalog=[];
  const workSelect=$('work-command-select'),workFields=$('work-command-fields');
  function renderCommandFields(){
    const command=workCatalog.find(row=>row.id===workSelect.value);
    workFields.replaceChildren();$('work-command-description').textContent=command?(command.description+(command.pc_approval_required?' · Requiere aprobación en la PC.':'')):'';
    if(!command)return;
    for(const [name,rule] of Object.entries(command.parameters)){
      const label=document.createElement('label');label.textContent=name;
      let input;
      if(Array.isArray(rule.enum)){input=document.createElement('select');for(const value of rule.enum)input.add(new Option(value,value));}
      else if(name==='script'||name==='content'){input=document.createElement('textarea');input.rows=name==='script'?5:3;}
      else{input=document.createElement('input');input.type=rule.type==='integer'?'number':'text';}
      input.dataset.field=name;input.required=rule.required===true;
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
      workCatalog=Array.isArray(result.commands)?result.commands:[];
      const previous=workSelect.value;workSelect.replaceChildren(...workCatalog.map(row=>new Option(row.title+' · '+row.id,row.id)));
      if(workCatalog.some(row=>row.id===previous))workSelect.value=previous;
      renderCommandFields();
    }catch(e){$('work-command-description').textContent='Aprueba Work para este teléfono en la PC: '+errorText(e);}
  }
  workSelect.onchange=renderCommandFields;
  if(pendingWork)workStatus('Hay una operación pendiente de comprobar. Pulsa «Actualizar actividad».');
  const workResult=result=>{$('work-result').textContent=JSON.stringify({state:result.state,output:result.output,evidence:result.evidence,error:result.error},null,2);};
  async function checkWork(){
    if(!pendingWork){await refresh();return;}
    try{
      const result=await request('/v1/work/operation?operation_id='+encodeURIComponent(pendingWork.operation_id));
      workResult(result);workStatus(result.state==='awaiting_approval'?'Pendiente de aprobación en la PC: '+pendingWork.command_id:'Estado de '+pendingWork.command_id+': '+result.state);
      if(['succeeded','failed','blocked','cancelled','expired','unknown'].includes(result.state))setPendingWork(null);
      await refresh();
    }catch(e){workStatus('No se pudo confirmar la operación. No la repetiré automáticamente: '+errorText(e));}
  }
  async function runWork(command_id,inputs,approved=false){
    if(!paired||!online){workStatus('Primero conecta el teléfono con la PC.');return;}
    if(pendingWork){workStatus('Hay una operación sin confirmar. Pulsa «Actualizar actividad» antes de enviar otra.');return;}
    const operation_id=crypto.randomUUID();setPendingWork({operation_id,command_id});
    workStatus('Enviando '+command_id+' a la PC…');
    try{
      const result=await request('/v1/work/execute',{command_id,inputs,operation_id,approved});
      workResult(result);workStatus(result.pc_approval_required?'Revisa y aprueba esta orden en Axx de la PC.':'Resultado confirmado: '+result.state);
      if(['succeeded','failed','blocked','cancelled','expired','unknown'].includes(result.state))setPendingWork(null);
      await refresh();
    }catch(e){workStatus('Entrega sin confirmar: '+errorText(e)+'. Pulsa «Actualizar actividad»; no se repetirá automáticamente.');}
  }
  $('work-health').onclick=()=>void runWork('axx.system.telemetry',{});
  $('work-text-form').onsubmit=async e=>{
    e.preventDefault();const text=$('work-text').value.trim();if(!text)return;
    try{
      const resolved=await request('/v1/work/resolve',{text});
      if(resolved.match!=='exact'||!resolved.command_id){workStatus(resolved.message||'No reconozco esa orden. Elige un comando en la lista.');return;}
      if(!workCatalog.some(row=>row.id===resolved.command_id)){workStatus('Ese comando está documentado, pero no tiene un ejecutor disponible.');return;}
      await runWork(resolved.command_id,resolved.inputs||{});
    }catch(error){workStatus('No se pudo preparar la orden: '+errorText(error));}
  };
  $('work-generic-form').onsubmit=e=>{
    e.preventDefault();const inputs={};
    for(const field of workFields.querySelectorAll('[data-field]'))inputs[field.dataset.field]=field.type==='number'?Number(field.value):field.value;
    void runWork(workSelect.value,inputs);
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
      if(!avatar || !transport)throw new Error('The character is not available yet.');
      const result=await transport.shortcut({png:characterIcon()});
      notice(result.requested?'Confirm Add on Android. If your home screen is locked, unlock its layout and try again.':'Home shortcut character updated.');
    }catch(e){notice(errorText(e));}finally{button.disabled=false;}
  };
  $('forget').onclick=async()=>{try{await transport.forget(); paired=false; connection(false,'PC forgotten on this phone. Also revoke this device from your PC.'); $('identity').textContent='No paired PC'; $('pc-name').textContent='Pair your PC';}catch(e){notice(errorText(e));}};
  document.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>pane(b.dataset.pane));
  $('open-catalog').onclick=()=>{pane('work');$('catalog').scrollIntoView({block:'start'});}; $('open-tasks').onclick=()=>pane('work');
  async function profile(){
    const info=await transport.profile(); paired=info.paired;
    if(paired){$('pc-name').textContent=new URL(info.endpoint).hostname; $('identity').textContent=info.endpoint+' · SHA-256 identity: '+info.fingerprint; $('scopes').textContent='PC permissions: '+info.scopes.join(', ');}
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
        gestureStatus(next.kind==='end'?'Gesto recibido por la PC':'Sincronizando '+(next.kind==='rotate'?'rotación':'movimiento')+' con la PC…');
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
    $('avatar-help').textContent=avatarMode==='rotate'?'Arrastra Axx para girarlo aquí y en la PC.':avatarMode==='move'?'Arrastra Axx para moverlo en la pantalla de la PC.':'Activa Rotate o Move y arrastra Axx con el dedo.';
  }
  $('avatar-interact').onclick=()=>setAvatarMode('rotate');
  $('avatar-move').onclick=()=>setAvatarMode('move');
  function reactToTouch(){avatar?.react();interactionUntil=Date.now()+1800;$('avatar-state').textContent='Axx reacts to your touch';}
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
      if(avatarMode==='rotate'){avatar?.rotate(dx*.012,dy*.012);avatar?.draw(avatar.lastTime||0);$('avatar-state').textContent='Rotating with your finger';}
      else $('avatar-state').textContent='Moving Axx on your PC';
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
    if(interactionUntil>Date.now())return;
    const preference=$('avatar-motion').value;
    const reduced=preference==='paused' || preference==='system' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const settings=window.Axx.normalizeSettings({...value.settings, quality:'eco', reducedMotion:reduced || value.settings?.reducedMotion});
    const state=value.activity?.state;
    if(state && window.Axx.MOTION_PROFILES[state])avatar.setState(pending?'thinking':state);
    const label=({idle:'Idle',thinking:'Thinking',speaking:'Speaking',listening:'Listening',processing:'Processing'})[avatar.state] || avatar.state;
    $('avatar-state').textContent=label+' · '+(settings.reducedMotion?'Reduced motion':settings.staticMode || !value.studio?.living?'Still':'Animated');
    $('avatar-pc-state').textContent=value.activity?'PC: '+(({idle:'Idle',thinking:'Thinking',listening:'Listening',speaking:'Speaking',processing:'Processing',approval:'Approval',paused:'Paused',success:'Success',error:'Error',notification:'Notification',focus:'Focus',transform:'Transform',offline:'Offline',cancelled:'Cancelled'})[state] || label)+' · '+(value.activity.moving?'moving':'still'):'';
    const key=JSON.stringify(value)+preference;if(key===appearanceKey){void syncHomeIcon(value);return;}
    if(JSON.stringify(avatar.settings)!==JSON.stringify(settings))avatar.configure(settings);if(avatar.form!==settings.form)avatar.setForm(settings.form);avatar.setStudio(value.studio||{});avatar.setCamera20(Array.isArray(value.camera)?[value.camera[0]%(Math.PI*2),value.camera[1]]:value.camera);avatar.setFinish(value.finish||'obsidian');if(!avatar.hidden)avatar.draw(avatar.lastTime || 0);appearanceKey=key;localStorage.setItem('axx.mobile.appearance',JSON.stringify(value));
    void syncHomeIcon(value);
  }
  try {const settings={...window.Axx.DEFAULT_SETTINGS,quality:'eco',reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches};avatar=new window.Axx.SoftwareRenderer($('axx-avatar-canvas'),settings);avatar.startLoop();window.axxMobileRenderer=avatar;} catch(e){notice('Animation is unavailable; controls remain active. '+errorText(e));}
  try{const cached=JSON.parse(localStorage.getItem('axx.mobile.appearance') || 'null');if(cached)applyAppearance(cached);}catch{}
  window.addEventListener('resize',()=>avatar?.resize());
  document.addEventListener('visibilitychange',()=>{if(document.hidden)avatar?.stop();else{avatar?.startLoop();void refresh();}});
  setInterval(()=>void refresh(),5000);
  setInterval(async()=>{
    if(!paired || !online || appearanceRefreshing || document.hidden)return;
    appearanceRefreshing=true;
    try{const data=await request('/v1/appearance');applyAppearance(data.appearance);}
    catch{ $('avatar-pc-state').textContent='PC state is out of date'; }
    finally{appearanceRefreshing=false;}
  },1000);
  if(transport) profile().then(()=>refresh()).catch(e=>notice(errorText(e)));
  else notice('Preview. Secure connection requires the Android APK.');
})();
