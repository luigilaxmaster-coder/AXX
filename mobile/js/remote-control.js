/* Input is never replayed. Only renew the same live lease after a transient failure. */
(()=>{
  'use strict';
  const transport=window.Capacitor?.Plugins?.AxxTransport,$=id=>document.getElementById(id);
  const card=document.createElement('section');card.className='live-card';card.id='control-panel';
  const icons={pad:'<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M3 15h18m-9 0v5"/>',keyboard:'<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 16h10"/>'};
  const icon=name=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[name]+'</svg>';
  card.innerHTML='<div class="control-heading"><div><span class="control-eyebrow"></span><h2>Controlar PC</h2></div><span class="control-mini-mark" aria-hidden="true">↗</span></div><p></p><div class="control-launchers"><button id="control-open-pad">'+icon('pad')+'<strong>Ratón</strong><b aria-hidden="true">↗</b></button><button id="control-open-keyboard">'+icon('keyboard')+'<strong>Teclado</strong><b aria-hidden="true">↗</b></button></div><p class="hint"></p>';
  $('pane-pc').prepend(card);
  const surface=document.createElement('dialog');surface.id='control-surface';surface.setAttribute('aria-label','Control remoto del PC');
  surface.innerHTML=`<div class="control-shell">
    <header class="control-header"><button id="control-close" aria-label="Cerrar control">‹</button><div><span class="control-eyebrow">AXX</span><strong id="control-title">Ratón</strong></div><button id="control-settings" aria-label="Ajustes de control" aria-expanded="false">⚙</button></header>
    <div class="control-topline"><p id="control-status" role="status" aria-live="polite">Control sin iniciar</p><button id="control-acquire">Tomar control</button><button id="control-stop" hidden>DETENER</button></div>
    <div class="control-mode" role="group" aria-label="Modo de entrada"><button data-control-mode="pad" aria-pressed="true">${icon('pad')}Ratón</button><button data-control-mode="keyboard" aria-pressed="false">${icon('keyboard')}Teclado</button></div>
    <section id="control-options" hidden><label>Sensibilidad<input id="control-sensitivity" type="range" min="0.4" max="3" step="0.1" value="1"></label><label><input id="control-acceleration" type="checkbox" checked> Aceleración suave</label><p id="control-geometry" class="hint"></p><p id="control-telemetry" class="hint">Latencia: sin muestras</p><p class="hint">Usar el ratón del PC detiene el control remoto.</p></section>
    <section id="control-pad-view" class="control-mode-view"><div id="control-pad" role="group" aria-label="Panel táctil remoto" tabindex="0"><div class="control-pad-hint">${icon('pad')}<strong>Desliza aquí</strong><span>Un dedo: mover y pulsar</span><span>Dos dedos: desplazar</span></div><span class="control-pad-caption">Mantén pulsado para arrastrar</span></div><div class="control-mouse-buttons"><button id="control-left">Clic izquierdo</button><button id="control-drag" aria-pressed="false" aria-label="Hold drag">Drag</button><button id="control-right">Clic derecho</button></div><div class="control-scroll-buttons" aria-label="Desplazamiento"><span>Desplazar</span><button data-scroll="-120,0" aria-label="Desplazar a la izquierda">←</button><button data-scroll="0,120" aria-label="Subir">↑</button><button data-scroll="0,-120" aria-label="Bajar">↓</button><button data-scroll="120,0" aria-label="Desplazar a la derecha">→</button></div></section>
    <section id="control-keyboard-view" class="control-mode-view" hidden><div class="control-text-compose"><label for="control-text">Escribir en el PC</label><textarea id="control-text" rows="3" maxlength="512" placeholder="Escribe aquí…" enterkeyhint="enter" autocomplete="off" autocapitalize="off" spellcheck="true"></textarea><div><span id="control-text-count">0 / 512</span><label class="hint"><input id="control-live-ime" type="checkbox"> En vivo (IME)</label><button id="control-send">Enviar texto</button></div></div><div id="control-keys" aria-label="Teclas y modificadores"></div><details id="control-extra-keys"><summary>Teclas F1–F12 y navegación</summary><div id="control-extra-grid" class="control-key-row"></div></details><div class="control-chord-row"><label for="control-letter">Combinar con</label><select id="control-letter" aria-label="Letra o número del atajo"></select><button id="control-chord">Pulsar tecla</button></div><p class="control-keyboard-help">Elige un modificador y una tecla. Pulsa otra vez para soltarlo.</p></section>
  </div>`;
  document.body.append(surface);const stop=$('control-stop');
  const header=surface.querySelector('.control-header');$('control-title').parentElement.hidden=true;
  header.insertBefore(surface.querySelector('.control-mode'),$('control-settings'));
  $('control-options').append(surface.querySelector('.control-scroll-buttons'));
  $('control-left').textContent='Izq.';$('control-right').textContent='Der.';$('control-drag').textContent='Arrastrar';$('control-left').setAttribute('aria-label','Clic izquierdo');$('control-right').setAttribute('aria-label','Clic derecho');
  for(const group of ['modifiers','actions','arrows']){const row=document.createElement('div');row.className='control-key-row';row.id='control-key-'+group;$('control-keys').append(row);}
  for(const key of ['Control','Alt','Shift','Meta','Escape','Enter','Tab','Backspace','Delete','ArrowLeft','ArrowUp','ArrowDown','ArrowRight']){
    const b=document.createElement('button');b.textContent=({Control:'Ctrl',Meta:'Win',Backspace:'⌫',Delete:'Del',Enter:'↵',Tab:'⇥',Escape:'Esc',ArrowLeft:'←',ArrowRight:'→',ArrowUp:'↑',ArrowDown:'↓'})[key]||key;b.dataset.key=key;
    const modifier=['Control','Alt','Shift','Meta'].includes(key);
    if(modifier)b.setAttribute('aria-pressed','false');b.title=key;b.setAttribute('aria-label',({ArrowLeft:'Flecha izquierda',ArrowRight:'Flecha derecha',ArrowUp:'Flecha arriba',ArrowDown:'Flecha abajo',Backspace:'Retroceso',Enter:'Intro',Tab:'Tabulador',Meta:'Windows'})[key]||b.textContent);$('control-key-'+(modifier?'modifiers':key.startsWith('Arrow')?'arrows':'actions')).append(b);
  }
  for(const letter of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')$('control-letter').add(new Option(letter,letter));
  for(const key of ['Home','End','PageUp','PageDown','Space','F1','F2','F3','F4','F5','F6','F7','F8','F9','F10','F11','F12']){
    const b=document.createElement('button');b.type='button';b.dataset.extraKey=key;
    b.textContent=({PageUp:'RePág',PageDown:'AvPág',Home:'Inicio',End:'Fin',Space:'Espacio'})[key]||key;
    b.title=key;$('control-extra-grid').append(b);
  }
  if(!transport){$('control-status').textContent='Disponible en la app Android.';return;}
  let lease=null,boot='',seq=0,criticalQueue=[],motionMove=null,motionScroll=null,motionCaptureMs=0,motionRaf=0;
  let sendingGen=0,renewing=false,recovering=false,requesting=false,generation=0,keys=new Set(),drag=false,deadline=0,hadControl=false,nativeClear=false;
  let motionErrorStreak=0,lastTap=null,composing=false;
  const telemetrySamples=[];
  const pointers=new Map();let gesture=null,holdTimer=0,remainderX=0,remainderY=0,wakeLock=null,expiryTimer=0;
  const request=async(op,body)=>(await transport.request({path:'/v1/control/'+op,method:body?'POST':'GET',...(body?{body}:{})})).data;
  const message=text=>{$('control-status').textContent=text;};
  const hasMotion=()=>!!(motionMove||motionScroll);
  function percentile(sorted,p){if(!sorted.length)return 0;const idx=Math.min(sorted.length-1,Math.max(0,Math.ceil(sorted.length*p)-1));return Math.round(sorted[idx]*10)/10;}
  function recordTelemetry(sample){
    telemetrySamples.push(sample);if(telemetrySamples.length>200)telemetrySamples.shift();
    if(telemetrySamples.length%5===1 || telemetrySamples.length<5){
      const rtts=telemetrySamples.map(s=>s.rtt_ms).sort((a,b)=>a-b);
      const p50=percentile(rtts,.5),p95=percentile(rtts,.95),p99=percentile(rtts,.99);
      const jitter=Math.round(Math.max(0,p95-p50)*10)/10;
      const srv=sample.server_send_ms!=null?` · SendInput ${sample.server_send_ms} ms`:'';
      $('control-telemetry').textContent=`RTT p50 ${p50} ms · p95 ${p95} ms · p99 ${p99} ms · jitter ${jitter} ms${srv} (${telemetrySamples.length})`;
    }
  }
  window.axxControlTelemetry=()=>{
    const rtts=telemetrySamples.map(s=>s.rtt_ms).sort((a,b)=>a-b);
    const queues=telemetrySamples.map(s=>s.queue_ms).sort((a,b)=>a-b);
    const sends=telemetrySamples.filter(s=>s.server_send_ms!=null).map(s=>s.server_send_ms).sort((a,b)=>a-b);
    return {count:telemetrySamples.length,rtt_ms:{p50:percentile(rtts,.5),p95:percentile(rtts,.95),p99:percentile(rtts,.99)},
      queue_ms:{p50:percentile(queues,.5),p95:percentile(queues,.95)},
      send_input_ms:{p50:percentile(sends,.5),p95:percentile(sends,.95),p99:percentile(sends,.99)},
      samples:telemetrySamples.slice(-50)};
  };
  function enabled(){return !!lease&&performance.now()<deadline&&!recovering&&!document.hidden&&surface.open&&!$('pane-pc').hidden;}
  function confirmWindow(started,s){
    const now=performance.now(),ttl=Math.min(3000,s.ttl_ms||3000);
    let budget=ttl;
    if(Object.hasOwn(s,'request_window_ms')){
      budget=s.request_window_ms;
      if(typeof budget!=='number'||!Number.isFinite(budget)||budget<0||budget>now-started+ttl)throw Object.assign(Error('Confirmación de sesión inválida.'),{code:'CONTROL_REPLY_INVALID'});
    }
    const next=started+budget;
    if(lease&&now>=deadline||now>=next)throw Object.assign(Error('La confirmación llegó tarde. Pulsa Reconectar.'),{code:'CONTROL_REPLY_INVALID'});
    deadline=next;clearTimeout(expiryTimer);const owner=generation;
    expiryTimer=setTimeout(()=>{if(lease&&owner===generation)void cancel('Conexión sin confirmar. Pulsa Reconectar.');},next-now);
  }
  function paint(){
    stop.hidden=!lease;$('control-acquire').hidden=!!lease;$('control-acquire').disabled=requesting;$('control-acquire').textContent=hadControl?'Reconectar':'Tomar control';surface.dataset.connected=String(enabled());
    for(const b of surface.querySelectorAll('#control-left,#control-right,#control-drag,[data-scroll],[data-key],[data-extra-key],#control-send,#control-chord'))b.disabled=!enabled();
    $('control-pad').setAttribute('aria-disabled',String(!enabled()));
    for(const b of $('control-keys').querySelectorAll('[aria-pressed]'))b.setAttribute('aria-pressed',String(keys.has(b.dataset.key)));
    $('control-drag').setAttribute('aria-pressed',String(drag));document.body.classList.toggle('remote-control-active',!!lease);
  }
  function resetPointers(){pointers.clear();gesture=null;remainderX=remainderY=0;clearTimeout(holdTimer);lastTap=null;}
  function clear(){
    const wasActive=!!lease;
    lease=null;generation++;criticalQueue=[];motionMove=null;motionScroll=null;motionCaptureMs=0;motionErrorStreak=0;
    if(motionRaf){cancelAnimationFrame(motionRaf);motionRaf=0;}
    keys.clear();drag=false;recovering=false;nativeClear=false;deadline=0;clearTimeout(expiryTimer);resetPointers();void wakeLock?.release();wakeLock=null;paint();
    if(wasActive)window.dispatchEvent(new CustomEvent('axxInputActive',{detail:{active:false}}));
  }
  async function cancel(reason='Control detenido'){
    const old=lease,b=boot;clear();message(reason);
    if(old)try{await request('release',{lease_id:old,boot_id:b});}catch{message(reason+' · sin confirmación de red; la PC libera las entradas al caducar la sesión.');}
  }
  function state(s){
    const n=s.native;
    nativeClear=Array.isArray(n.keys)&&Array.isArray(n.buttons)&&n.keys.length===0&&n.buttons.length===0;
    $('control-geometry').textContent=(n.monitors||[]).map(m=>m.width+' × '+m.height+' @ '+m.x+','+m.y+(m.dpi?' · '+m.dpi+' DPI':'')).join(' / ')+(n.cursor?' · Cursor '+n.cursor.x+', '+n.cursor.y:'');
    if(lease&&(!n.active||s.lease?.state!=='granted'||s.lease?.lease_id!==lease||s.boot_id!==boot)){clear();const reason=({local_mouse:'Se usó el ratón del PC',local_keyboard:'Se usó el teclado del PC',expired_or_revoked:'La sesión caducó',display_changed:'Cambió la pantalla del PC',released:'Control detenido'})[n.reason]||'El PC finalizó el control';message(reason+'. Pulsa Reconectar.');}
  }
  $('control-acquire').onclick=async()=>{
    if(requesting||lease||document.hidden||!surface.open||$('pane-pc').hidden)return;requesting=true;paint();message('Solicitando control…');const current=++generation;
    let candidate=null;
    try{
      let s=await request('acquire',{request_id:crypto.randomUUID(),visible:true});
      if(s.lease?.lease_id)candidate={lease_id:s.lease.lease_id,boot_id:s.boot_id};
      if(current!==generation||document.hidden||!surface.open)return;
      if(!s.native.active||s.lease?.state!=='granted')throw new Error('El PC no concedió el control');
      // Cold startup may outlive a watchdog period; verify only this lease before enabling input.
      const started=performance.now();s=await request('renew',{...candidate,visible:true});
      if(current!==generation||document.hidden||!surface.open)return;
      if(!s.native.active||s.lease?.state!=='granted'||s.lease.lease_id!==candidate.lease_id||s.boot_id!==candidate.boot_id)throw Error('La sesión cambió. Vuelve a tomar control.');
      state(s);if(!nativeClear)throw Error('La PC mantiene entrada pulsada o sin confirmar.');
      confirmWindow(started,s);lease=candidate.lease_id;boot=candidate.boot_id;seq=s.lease.last_seq;candidate=null;hadControl=true;message('Control activo · sin límite');paint();
      window.dispatchEvent(new CustomEvent('axxInputActive',{detail:{active:true}}));
      try{navigator.wakeLock?.request('screen').then(lock=>{if(current===generation)wakeLock=lock;else void lock?.release();}).catch(()=>{});}catch{}
    }catch(e){if(current===generation)message(e.message);}
    finally{if(candidate)try{await request('release',candidate);}catch{}requesting=false;paint();}
  };
  stop.onclick=()=>void cancel();
  function mode(name){
    if(drag)setDrag(false);
    $('control-pad-view').hidden=name!=='pad';$('control-keyboard-view').hidden=name!=='keyboard';
    $('control-title').textContent=name==='pad'?'Ratón':'Teclado';surface.dataset.mode=name;
    surface.querySelectorAll('[data-control-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.controlMode===name)));
    if(name==='keyboard')$('control-text').focus();else document.activeElement?.blur();
  }
  function open(name){surface.showModal();document.body.classList.add('control-fullscreen');mode(name);fit();paint();void poll();}
  $('control-open-pad').onclick=()=>open('pad');$('control-open-keyboard').onclick=()=>open('keyboard');
  surface.querySelectorAll('[data-control-mode]').forEach(b=>b.onclick=()=>mode(b.dataset.controlMode));
  $('control-close').onclick=()=>surface.close();
  surface.addEventListener('close',()=>{document.body.classList.remove('control-fullscreen');void cancel('Control detenido al cerrar');});
  surface.addEventListener('cancel',()=>void cancel('Control detenido al volver'));
  $('control-settings').onclick=()=>{$('control-options').hidden=!$('control-options').hidden;$('control-settings').setAttribute('aria-expanded',String(!$('control-options').hidden));};
  $('control-text').oninput=()=>{$('control-text-count').textContent=$('control-text').value.length+' / 512';};
  function fit(){surface.style.height=(window.visualViewport?.height||innerHeight)+'px';}
  window.visualViewport?.addEventListener('resize',fit);window.addEventListener('resize',fit);

  function flushPendingMotionIntoCritical(){
    if(motionMove){criticalQueue.push(motionMove);motionMove=null;}
    if(motionScroll){criticalQueue.push(motionScroll);motionScroll=null;}
  }
  function scheduleMotionFlush(){
    if(motionRaf || sendingGen===generation)return;
    motionRaf=requestAnimationFrame(()=>{motionRaf=0;void flush();});
  }
  function enqueue(...events){
    if(!enabled())return;
    let hasCritical=false;
    for(const event of events){
      if(event.type==='move'){
        if(!motionCaptureMs)motionCaptureMs=performance.now();
        if(motionMove){motionMove.x=Math.max(-2000,Math.min(2000,motionMove.x+event.x));motionMove.y=Math.max(-2000,Math.min(2000,motionMove.y+event.y));}
        else motionMove={type:'move',x:event.x,y:event.y};
      }else if(event.type==='scroll'){
        if(!motionCaptureMs)motionCaptureMs=performance.now();
        if(motionScroll){motionScroll.x=Math.max(-2000,Math.min(2000,motionScroll.x+event.x));motionScroll.y=Math.max(-2000,Math.min(2000,motionScroll.y+event.y));}
        else motionScroll={type:'scroll',x:event.x,y:event.y};
      }else{
        // Preserve accumulated motion before any critical down/up/key/text boundary.
        flushPendingMotionIntoCritical();
        criticalQueue.push(event);
        hasCritical=true;
      }
    }
    if(criticalQueue.length>64){void cancel('Demasiadas entradas; control detenido');return;}
    if(hasCritical){if(motionRaf){cancelAnimationFrame(motionRaf);motionRaf=0;}void flush();}
    else if(hasMotion())scheduleMotionFlush();
  }
  async function flush(){
    if(sendingGen===generation||!enabled()||(!criticalQueue.length&&!hasMotion()))return;
    const current=generation;sendingGen=current;
    let batch=[],batchIsCritical=false,captureAt=0;
    if(criticalQueue.length){
      batch=criticalQueue.splice(0,16);
      batchIsCritical=batch.some(ev=>ev.type!=='move'&&ev.type!=='scroll');
      captureAt=performance.now();
    }else{
      if(motionMove){batch.push(motionMove);motionMove=null;}
      if(motionScroll){batch.push(motionScroll);motionScroll=null;}
      captureAt=motionCaptureMs||performance.now();
      motionCaptureMs=0;
    }
    const dispatchedAt=performance.now();
    const body={lease_id:lease,boot_id:boot,seq:++seq,events:batch};
    try{
      const s=await request('events',body);
      const ackAt=performance.now();
      if(current===generation){
        motionErrorStreak=0;
        state(s);
        recordTelemetry({
          kind:batchIsCritical?'critical':'motion',
          queue_ms:Math.round(Math.max(0,dispatchedAt-captureAt)*10)/10,
          rtt_ms:Math.round(Math.max(0,ackAt-dispatchedAt)*10)/10,
          server_send_ms:s.metrics?.send_input_ms??null,
          server_total_ms:s.metrics?.server_total_ms??null
        });
      }
    }catch(e){
      if(current===generation){
        const transient=e.code==='PC_TIMEOUT'||e.code==='PC_UNREACHABLE';
        if(!batchIsCritical && transient && !keys.size && !drag && nativeClear && motionErrorStreak<2 && performance.now()<deadline){
          motionErrorStreak++;
          try{
            const started=performance.now(),s=await request('renew',{lease_id:lease,boot_id:boot,visible:true});
            if(current===generation){
              state(s);
              if(lease && nativeClear && s.lease?.lease_id===lease && s.boot_id===boot){
                confirmWindow(started,s);seq=s.lease.last_seq;
              }else if(lease){await cancel('Entrada sin confirmar: '+e.message+'. No se repetirá.');}
            }
          }catch{if(current===generation&&lease)await cancel('Entrada sin confirmar: '+e.message+'. No se repetirá.');}
        }else{
          await cancel('Entrada sin confirmar: '+e.message+'. No se repetirá.');
        }
      }
    }finally{
      if(sendingGen===current)sendingGen=0;
      if(current===generation && enabled()){
        if(criticalQueue.length)void flush();
        else if(hasMotion())scheduleMotionFlush();
      }
    }
  }
  async function poll(){
    if(lease&&performance.now()>=deadline){await cancel('Conexión sin confirmar. Pulsa Reconectar.');return;}
    if(renewing||requesting||document.hidden||!surface.open)return;renewing=true;const current=generation;
    try{const started=performance.now(),s=lease?await request('renew',{lease_id:lease,boot_id:boot,visible:true}):await request('status');if(current===generation){state(s);if(lease)confirmWindow(started,s);}}
    catch(e){
      if(!lease||current!==generation)return;
      if(e.code&&!['PC_TIMEOUT','PC_UNREACHABLE'].includes(e.code)||!enabled()||sendingGen===generation||criticalQueue.length||hasMotion()||keys.size||drag||!nativeClear||performance.now()>=deadline){await cancel('Conexión interrumpida. Pulsa Reconectar.');return;}
      // A renewal has no input effects; discard unsent gestures while confirming this exact lease.
      recovering=true;criticalQueue=[];motionMove=null;motionScroll=null;resetPointers();paint();message('Recuperando conexión…');
      try{const started=performance.now(),s=await request('renew',{lease_id:lease,boot_id:boot,visible:true});if(current===generation){state(s);if(lease&&!nativeClear)await cancel('Control detenido para soltar la entrada. Pulsa Reconectar.');else if(lease){confirmWindow(started,s);recovering=false;paint();message('Control restablecido');}}}
      catch{if(lease&&current===generation)await cancel('Conexión interrumpida. Pulsa Reconectar.');}
    }
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
  $('control-extra-grid').onclick=e=>{
    const b=e.target.closest('[data-extra-key]');if(!b||!enabled())return;const key=b.dataset.extraKey;
    enqueue({type:'key',key,down:true},{type:'key',key,down:false});
  };
  $('control-chord').onclick=()=>{const key=$('control-letter').value;enqueue({type:'key',key,down:true},{type:'key',key,down:false});};
  $('control-send').onclick=()=>{
    const text=$('control-text').value;if(!text||!enabled())return;
    if(keys.size){message('Suelta los modificadores antes de enviar texto.');return;}
    enqueue({type:'text',text});message('Texto enviado una vez a la ventana activa. El borrador se conserva.');
  };
  const liveIme=$('control-live-ime'),textArea=$('control-text');
  textArea.addEventListener('compositionstart',()=>{composing=true;});
  textArea.addEventListener('compositionend',()=>{
    composing=false;
    if(!liveIme.checked||!enabled()||keys.size)return;
    const val=textArea.value;
    if(val){enqueue({type:'text',text:val.slice(0,512)});textArea.value='';$('control-text-count').textContent='0 / 512';}
  });
  textArea.addEventListener('beforeinput',e=>{
    if(!liveIme.checked||!enabled()||composing)return;
    if(e.inputType==='deleteContentBackward'&&!textArea.value){e.preventDefault();enqueue({type:'key',key:'Backspace',down:true},{type:'key',key:'Backspace',down:false});}
    else if(e.inputType==='insertLineBreak'&&!textArea.value){e.preventDefault();enqueue({type:'key',key:'Enter',down:true},{type:'key',key:'Enter',down:false});}
  });
  textArea.addEventListener('input',()=>{
    $('control-text-count').textContent=textArea.value.length+' / 512';
    if(!liveIme.checked||!enabled()||composing||keys.size)return;
    const val=textArea.value;
    if(val){enqueue({type:'text',text:val.slice(0,512)});textArea.value='';$('control-text-count').textContent='0 / 512';}
  });
  let prefs={};try{prefs=JSON.parse(localStorage.getItem('axx.control.trackpad')||'{}');}catch{}
  if(prefs.sensitivity)$('control-sensitivity').value=prefs.sensitivity;
  if(prefs.acceleration===false)$('control-acceleration').checked=false;
  for(const id of ['control-sensitivity','control-acceleration'])$(id).onchange=()=>localStorage.setItem('axx.control.trackpad',JSON.stringify({sensitivity:Number($('control-sensitivity').value),acceleration:$('control-acceleration').checked}));
  const pad=$('control-pad');
  pad.onpointerdown=e=>{
    if(!enabled())return;e.preventDefault();try{pad.setPointerCapture(e.pointerId);}catch{}
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===1){remainderX=remainderY=0;gesture={started:performance.now(),distance:0,max:1,holding:false,startX:e.clientX,startY:e.clientY};holdTimer=setTimeout(()=>{if(gesture&&gesture.max===1&&gesture.distance<6){gesture.holding=true;setDrag(true);}},450);}
    else{clearTimeout(holdTimer);if(gesture)gesture.max=pointers.size;if(drag)setDrag(false);}
  };
  pad.onpointermove=e=>{
    const old=pointers.get(e.pointerId);if(!old||!gesture||!enabled())return;e.preventDefault();
    const samples=typeof e.getCoalescedEvents==='function'&&e.getCoalescedEvents().length?e.getCoalescedEvents():[e];
    let prevX=old.x,prevY=old.y;
    for(const sample of samples){
      const dx=sample.clientX-prevX,dy=sample.clientY-prevY;prevX=sample.clientX;prevY=sample.clientY;
      gesture.distance+=Math.hypot(dx,dy);
      if(gesture.distance>6)clearTimeout(holdTimer);
      if(gesture.max>1){if(pointers.size===2)enqueue({type:'scroll',x:Math.round(dx*3),y:Math.round(-dy*3)});continue;}
      const factor=Number($('control-sensitivity').value)*($('control-acceleration').checked?1+Math.min(1,Math.hypot(dx,dy)/30):1);
      remainderX+=dx*factor;remainderY+=dy*factor;const x=Math.trunc(remainderX),y=Math.trunc(remainderY);remainderX-=x;remainderY-=y;
      if(x||y)enqueue({type:'move',x:Math.max(-2000,Math.min(2000,x)),y:Math.max(-2000,Math.min(2000,y))});
    }
    pointers.set(e.pointerId,{x:prevX,y:prevY});
  };
  pad.onpointerup=e=>{
    if(!pointers.has(e.pointerId))return;e.preventDefault();pointers.delete(e.pointerId);clearTimeout(holdTimer);
    if(pointers.size||!gesture)return;
    const now=performance.now();
    if(gesture.holding)setDrag(false);
    else if(gesture.distance<8&&now-gesture.started<450){
      if(gesture.max===2){click('right');lastTap=null;}
      else{
        click('left');
        if(lastTap && now-lastTap.at<320 && Math.hypot(e.clientX-lastTap.x,e.clientY-lastTap.y)<24){lastTap=null;}
        else lastTap={at:now,x:e.clientX,y:e.clientY};
      }
    }
    gesture=null;
  };
  pad.onpointercancel=()=>{resetPointers();if(drag)setDrag(false);};
  pad.onlostpointercapture=e=>{if(pointers.has(e.pointerId)){resetPointers();if(drag)setDrag(false);}};
  pad.oncontextmenu=e=>e.preventDefault();
  document.addEventListener('visibilitychange',()=>{if(document.hidden)void cancel('Control detenido al salir de la app');else void poll();});
  window.addEventListener('pagehide',()=>void cancel('Control detenido al cerrar la app'));
  // Navigating away from the pad also releases held input; voice remains independent.
  new MutationObserver(()=>{if($('pane-pc').hidden&&(lease||requesting))void cancel('Control detenido al cambiar de sección');}).observe($('pane-pc'),{attributes:true,attributeFilter:['hidden']});
  paint();setInterval(()=>void poll(),500);
})();
