/* Ephemeral input only: no persistence, retry or automatic reacquisition. */
(()=>{
  'use strict';
  const transport=window.Capacitor?.Plugins?.AxxTransport,$=id=>document.getElementById(id);
  const card=document.createElement('section');card.className='live-card';card.id='control-panel';
  const icons={pad:'<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M3 15h18m-9 0v5"/>',keyboard:'<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 16h10"/>'};
  const icon=name=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[name]+'</svg>';
  card.innerHTML='<div class="control-heading"><div><span class="control-eyebrow">YOUR PC, WITHIN REACH</span><h2>Remote control</h2></div><span class="control-mini-mark" aria-hidden="true">↗</span></div><p>Choose how to control your computer.</p><div class="control-launchers"><button id="control-open-pad">'+icon('pad')+'<strong>Trackpad</strong><span>Move, click and drag</span><b aria-hidden="true">↗</b></button><button id="control-open-keyboard">'+icon('keyboard')+'<strong>Keyboard</strong><span>Text and shortcuts</span><b aria-hidden="true">↗</b></button></div><p class="hint">Opens full screen. Your PC always takes priority.</p>';
  $('pane-pc').prepend(card);
  const surface=document.createElement('dialog');surface.id='control-surface';surface.setAttribute('aria-label','Remote control of your PC');
  surface.innerHTML=`<div class="control-shell">
    <header class="control-header"><button id="control-close" aria-label="Close remote control">‹</button><div><span class="control-eyebrow">AXX</span><strong id="control-title">Trackpad</strong></div><button id="control-settings" aria-label="Control settings" aria-expanded="false">⚙</button></header>
    <div class="control-topline"><p id="control-status" role="status" aria-live="polite">Authorize this phone in Axx settings on your PC.</p><button id="control-acquire">Take control</button><button id="control-stop" hidden>STOP CONTROL</button></div>
    <div class="control-mode" role="group" aria-label="Input mode"><button data-control-mode="pad" aria-pressed="true">${icon('pad')}Trackpad</button><button data-control-mode="keyboard" aria-pressed="false">${icon('keyboard')}Keyboard</button></div>
    <section id="control-options" hidden><label>Sensitivity<input id="control-sensitivity" type="range" min="0.4" max="3" step="0.1" value="1"></label><label><input id="control-acceleration" type="checkbox" checked> Smooth acceleration</label><p id="control-geometry" class="hint"></p><p class="hint">Physical PC input stops remote control. Voice works independently.</p></section>
    <section id="control-pad-view" class="control-mode-view"><div id="control-pad" role="group" aria-label="Remote trackpad" tabindex="0"><div class="control-pad-hint">${icon('pad')}<strong>Slide here</strong><span>One finger: move and click</span><span>Two fingers: scroll and menu</span></div><span class="control-pad-caption">Hold to drag</span></div><div class="control-mouse-buttons"><button id="control-left">Left click</button><button id="control-drag" aria-pressed="false" aria-label="Hold drag">Drag</button><button id="control-right">Right click</button></div><div class="control-scroll-buttons" aria-label="Scrolling"><span>Scroll</span><button data-scroll="-120,0" aria-label="Scroll left">←</button><button data-scroll="0,120" aria-label="Scroll up">↑</button><button data-scroll="0,-120" aria-label="Scroll down">↓</button><button data-scroll="120,0" aria-label="Scroll right">→</button></div></section>
    <section id="control-keyboard-view" class="control-mode-view" hidden><div class="control-text-compose"><label for="control-text">Type on your PC</label><textarea id="control-text" rows="3" maxlength="512" placeholder="Tap here to type…" enterkeyhint="enter" autocomplete="off" autocapitalize="off" spellcheck="true"></textarea><div><span id="control-text-count">0 / 512</span><button id="control-send">Send text ↗</button></div></div><div id="control-keys" aria-label="Keys and modifiers"></div><div class="control-chord-row"><label for="control-letter">Combine with</label><select id="control-letter" aria-label="Letter or number for the shortcut"></select><button id="control-chord">Press key</button></div><p class="control-keyboard-help">Select Ctrl, Alt, Shift or Windows and choose a key. Tap a modifier again to release it.</p></section>
  </div>`;
  document.body.append(surface);const stop=$('control-stop');
  const header=surface.querySelector('.control-header');$('control-title').parentElement.hidden=true;
  header.insertBefore(surface.querySelector('.control-mode'),$('control-settings'));
  $('control-options').append(surface.querySelector('.control-scroll-buttons'));
  $('control-left').textContent='Left';$('control-right').textContent='Right';$('control-drag').textContent='Drag';$('control-left').setAttribute('aria-label','Left click');$('control-right').setAttribute('aria-label','Right click');
  for(const group of ['modifiers','actions','arrows']){const row=document.createElement('div');row.className='control-key-row';row.id='control-key-'+group;$('control-keys').append(row);}
  for(const key of ['Control','Alt','Shift','Meta','Escape','Enter','Tab','Backspace','Delete','ArrowLeft','ArrowUp','ArrowDown','ArrowRight']){
    const b=document.createElement('button');b.textContent=({Control:'Ctrl',Meta:'Win',Backspace:'⌫',Delete:'Del',Enter:'↵',Tab:'⇥',Escape:'Esc',ArrowLeft:'←',ArrowRight:'→',ArrowUp:'↑',ArrowDown:'↓'})[key]||key;b.dataset.key=key;
    const modifier=['Control','Alt','Shift','Meta'].includes(key);
    if(modifier)b.setAttribute('aria-pressed','false');b.title=key;b.setAttribute('aria-label',({ArrowLeft:'Left arrow',ArrowRight:'Right arrow',ArrowUp:'Up arrow',ArrowDown:'Down arrow',Backspace:'Backspace',Enter:'Enter',Tab:'Tab',Meta:'Windows'})[key]||b.textContent);$('control-key-'+(modifier?'modifiers':key.startsWith('Arrow')?'arrows':'actions')).append(b);
  }
  for(const letter of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')$('control-letter').add(new Option(letter,letter));
  if(!transport){$('control-status').textContent='Available in the Android app.';return;}
  let lease=null,boot='',seq=0,queue=[],sending=false,renewing=false,requesting=false,generation=0,keys=new Set(),drag=false;
  const pointers=new Map();let gesture=null,holdTimer=0,remainderX=0,remainderY=0,wakeLock=null;
  const request=async(op,body)=>(await transport.request({path:'/v1/control/'+op,method:body?'POST':'GET',...(body?{body}:{})})).data;
  const message=text=>{$('control-status').textContent=text;};
  function enabled(){return !!lease&&!document.hidden;}
  function paint(){
    stop.hidden=!lease;$('control-acquire').hidden=!!lease;$('control-acquire').disabled=requesting;surface.dataset.connected=String(!!lease);
    for(const b of surface.querySelectorAll('#control-left,#control-right,#control-drag,[data-scroll],[data-key],#control-send,#control-chord'))b.disabled=!lease;
    $('control-pad').setAttribute('aria-disabled',String(!lease));
    for(const b of $('control-keys').querySelectorAll('[aria-pressed]'))b.setAttribute('aria-pressed',String(keys.has(b.dataset.key)));
    $('control-drag').setAttribute('aria-pressed',String(drag));document.body.classList.toggle('remote-control-active',!!lease);
  }
  function clear(){lease=null;generation++;queue=[];keys.clear();drag=false;pointers.clear();gesture=null;remainderX=remainderY=0;clearTimeout(holdTimer);void wakeLock?.release();wakeLock=null;paint();}
  async function cancel(reason='Control stopped'){
    const old=lease,b=boot;clear();message(reason);
    if(old)try{await request('release',{lease_id:old,boot_id:b});}catch{message(reason+' · network acknowledgement missing; the PC lease expires within 3 s.');}
  }
  function state(s){
    const n=s.native;
    $('control-geometry').textContent=(n.monitors||[]).map(m=>m.width+' × '+m.height+' @ '+m.x+','+m.y+(m.dpi?' · '+m.dpi+' DPI':'')).join(' / ')+(n.cursor?' · Cursor '+n.cursor.x+', '+n.cursor.y:'');
    if(lease&&(!n.active||s.lease?.lease_id!==lease||s.boot_id!==boot)){clear();message('Control ended · '+(n.reason||'revoked')+'. Request control again to continue.');}
  }
  $('control-acquire').onclick=async()=>{
    if(requesting||lease||document.hidden)return;requesting=true;paint();message('Requesting PC control…');const current=++generation;
    try{
      const s=await request('acquire',{request_id:crypto.randomUUID(),visible:true});
      if(current!==generation||document.hidden){if(s.lease?.lease_id)await request('release',{lease_id:s.lease.lease_id,boot_id:s.boot_id});return;}
      if(!s.native.active||s.lease?.state!=='granted')throw new Error('The PC did not grant control');
      lease=s.lease.lease_id;boot=s.boot_id;seq=s.lease.last_seq;state(s);message('Control granted');
      try{const lock=await navigator.wakeLock?.request('screen');if(current===generation)wakeLock=lock;else void lock?.release();}catch{}
    }catch(e){message(e.message);}finally{requesting=false;paint();}
  };
  stop.onclick=()=>void cancel();
  function mode(name){
    if(drag)setDrag(false);
    $('control-pad-view').hidden=name!=='pad';$('control-keyboard-view').hidden=name!=='keyboard';
    $('control-title').textContent=name==='pad'?'Trackpad':'Keyboard';surface.dataset.mode=name;
    surface.querySelectorAll('[data-control-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.controlMode===name)));
    if(name==='keyboard')$('control-text').focus();else document.activeElement?.blur();
  }
  function open(name){surface.showModal();document.body.classList.add('control-fullscreen');mode(name);fit();}
  $('control-open-pad').onclick=()=>open('pad');$('control-open-keyboard').onclick=()=>open('keyboard');
  surface.querySelectorAll('[data-control-mode]').forEach(b=>b.onclick=()=>mode(b.dataset.controlMode));
  $('control-close').onclick=()=>surface.close();
  surface.addEventListener('close',()=>{document.body.classList.remove('control-fullscreen');void cancel('Control stopped on close');});
  surface.addEventListener('cancel',()=>void cancel('Control stopped on back'));
  $('control-settings').onclick=()=>{$('control-options').hidden=!$('control-options').hidden;$('control-settings').setAttribute('aria-expanded',String(!$('control-options').hidden));};
  $('control-text').oninput=()=>{$('control-text-count').textContent=$('control-text').value.length+' / 512';};
  function fit(){surface.style.height=(window.visualViewport?.height||innerHeight)+'px';}
  window.visualViewport?.addEventListener('resize',fit);window.addEventListener('resize',fit);

  function enqueue(...events){
    if(!enabled())return;
    for(const event of events){
      const tail=queue.at(-1);
      if(['move','scroll'].includes(event.type)&&tail?.type===event.type){tail.x=Math.max(-2000,Math.min(2000,tail.x+event.x));tail.y=Math.max(-2000,Math.min(2000,tail.y+event.y));}
      else queue.push(event);
    }
    if(queue.length>64){void cancel('Input backlog; control stopped');return;}
    void flush();
  }
  async function flush(){
    if(sending||!enabled()||!queue.length)return;sending=true;const current=generation;
    const body={lease_id:lease,boot_id:boot,seq:++seq,events:queue.splice(0,16)};
    try{const s=await request('events',body);if(current===generation)state(s);}
    catch(e){if(current===generation)await cancel('Input unconfirmed: '+e.message+'. It will not be replayed.');}
    finally{sending=false;if(current===generation&&queue.length)void flush();}
  }
  async function poll(){
    if(renewing||document.hidden)return;renewing=true;const current=generation;
    try{const s=lease?await request('renew',{lease_id:lease,boot_id:boot,visible:true}):await request('status');if(current===generation)state(s);}
    catch(e){if(lease&&current===generation)await cancel('Control connection interrupted: '+e.message);}
    finally{renewing=false;}
  }
  const button=(button,down)=>({type:'button',button,down});
  function click(which){enqueue(button(which,true),button(which,false));}
  $('control-left').onclick=()=>click('left');$('control-right').onclick=()=>click('right');
  function setDrag(value){if(!enabled())return;drag=value;enqueue(button('left',drag));paint();}
  $('control-drag').onclick=()=>setDrag(!drag);
  surface.querySelectorAll('[data-scroll]').forEach(b=>b.onclick=()=>{const [x,y]=b.dataset.scroll.split(',').map(Number);enqueue({type:'scroll',x,y});});
  $('control-keys').onclick=e=>{
    const b=e.target.closest('[data-key]');if(!b||!enabled())return;const key=b.dataset.key;
    if(b.hasAttribute('aria-pressed')){const down=!keys.has(key);if(down)keys.add(key);else keys.delete(key);enqueue({type:'key',key,down});paint();}
    else enqueue({type:'key',key,down:true},{type:'key',key,down:false});
  };
  $('control-chord').onclick=()=>{const key=$('control-letter').value;enqueue({type:'key',key,down:true},{type:'key',key,down:false});};
  $('control-send').onclick=()=>{
    const text=$('control-text').value;if(!text||!enabled())return;
    if(keys.size){message('Suelta los modificadores antes de enviar texto.');return;}
    enqueue({type:'text',text});message('Texto enviado una vez a la ventana activa. El borrador se conserva.');
  };
  let prefs={};try{prefs=JSON.parse(localStorage.getItem('axx.control.trackpad')||'{}');}catch{}
  if(prefs.sensitivity)$('control-sensitivity').value=prefs.sensitivity;
  if(prefs.acceleration===false)$('control-acceleration').checked=false;
  for(const id of ['control-sensitivity','control-acceleration'])$(id).onchange=()=>localStorage.setItem('axx.control.trackpad',JSON.stringify({sensitivity:Number($('control-sensitivity').value),acceleration:$('control-acceleration').checked}));
  const pad=$('control-pad');
  pad.onpointerdown=e=>{
    if(!enabled())return;e.preventDefault();pad.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===1){remainderX=remainderY=0;gesture={started:performance.now(),distance:0,max:1,holding:false};holdTimer=setTimeout(()=>{if(gesture&&gesture.max===1&&gesture.distance<6){gesture.holding=true;setDrag(true);}},450);}
    else{clearTimeout(holdTimer);if(gesture)gesture.max=pointers.size;if(drag)setDrag(false);}
  };
  pad.onpointermove=e=>{
    const old=pointers.get(e.pointerId);if(!old||!gesture||!enabled())return;e.preventDefault();
    const dx=e.clientX-old.x,dy=e.clientY-old.y;pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});gesture.distance+=Math.hypot(dx,dy);
    if(gesture.distance>6)clearTimeout(holdTimer);
    if(gesture.max>1){if(pointers.size===2)enqueue({type:'scroll',x:Math.round(dx*3),y:Math.round(-dy*3)});return;}
    const factor=Number($('control-sensitivity').value)*($('control-acceleration').checked?1+Math.min(1,Math.hypot(dx,dy)/30):1);
    remainderX+=dx*factor;remainderY+=dy*factor;const x=Math.trunc(remainderX),y=Math.trunc(remainderY);remainderX-=x;remainderY-=y;
    if(x||y)enqueue({type:'move',x:Math.max(-2000,Math.min(2000,x)),y:Math.max(-2000,Math.min(2000,y))});
  };
  pad.onpointerup=e=>{
    if(!pointers.has(e.pointerId))return;e.preventDefault();pointers.delete(e.pointerId);clearTimeout(holdTimer);
    if(pointers.size||!gesture)return;
    if(gesture.holding)setDrag(false);
    else if(gesture.distance<8&&performance.now()-gesture.started<450)click(gesture.max===2?'right':'left');
    gesture=null;
  };
  pad.onpointercancel=()=>{pointers.clear();gesture=null;clearTimeout(holdTimer);if(drag)setDrag(false);};
  pad.oncontextmenu=e=>e.preventDefault();
  document.addEventListener('visibilitychange',()=>{if(document.hidden)void cancel('Control stopped al salir de la app');else void poll();});
  window.addEventListener('pagehide',()=>void cancel('Control stopped on close la app'));
  // Navigating away from the pad also releases held input; voice remains independent.
  new MutationObserver(()=>{if($('pane-pc').hidden&&(lease||requesting))void cancel('Control stopped when changing section');}).observe($('pane-pc'),{attributes:true,attributeFilter:['hidden']});
  paint();setInterval(()=>void poll(),800);
})();
