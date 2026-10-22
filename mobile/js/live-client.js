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
      const tasks = await request('/v1/tasks'); renderRows('tasks', tasks.operations || [], 'No recorded operations.', 'task');
      const catalog = await request('/v1/catalog'); renderRows('catalog', catalog.tools || [], 'The PC has not published any tools.', 'tool');
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
  $('avatar-interact').onclick=()=>{
    const active=$('avatar-interact').getAttribute('aria-pressed')!=='true';
    $('avatar-interact').setAttribute('aria-pressed',String(active));
    $('axx-avatar-canvas').classList.toggle('interactive',active);
    $('avatar-help').textContent=active?'Tap to say hello. Drag Axx to rotate; use the margin to scroll.':'Tap Axx to say hello. Enable Rotate to drag it.';
  };
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
    if(pointer.drag){avatar.rotate(dx*.012,dy*.012);avatar.draw(avatar.lastTime||0);interactionUntil=Date.now()+5000;$('avatar-state').textContent='Rotating with your finger';}
    pointer.x=event.clientX;pointer.y=event.clientY;
  };
  canvas.onpointerup=event=>{if(pointer?.id!==event.pointerId)return;if(!pointer.drag && Math.hypot(event.clientX-pointer.startX,event.clientY-pointer.startY)<8)reactToTouch();pointer=null;};
  canvas.onpointercancel=()=>{pointer=null;};
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
