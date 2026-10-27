/* Small avatar interactions share the existing chat, microphone and speech owners. */
(function(Axx){
 'use strict';
 if(!Axx?.isNative()||!Axx.resident||!Axx.nativeVoice||!Axx.chatWorkspace)return;
 const c=Axx.companion,r=Axx.resident,$=id=>document.getElementById(id);
 const icon=(path)=>`<svg aria-hidden="true" viewBox="0 0 24 24">${path}</svg>`;
 const mic=icon('<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>');
 const pen=icon('<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14z"/>');
 const chat=icon('<path d="M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0ZM7 9h8M7 13h5"/>');
 const root=document.createElement('div');root.id='quick-root';
 root.innerHTML=`<style>
 #quick-root{--quick-bg:color-mix(in srgb,var(--surface,#18212c) var(--widget-opacity,96%),transparent);--quick-ink:var(--ink,#edf2fa);color:var(--quick-ink);font:calc(13px * var(--interface-scale,1))/1.5 var(--interface-font,"Segoe UI",sans-serif)}
 #quick-root [hidden]{display:none!important}#quick-root :is(button,input){font:inherit;box-sizing:border-box;color:inherit}
 #quick-root :is(button,input):focus-visible{outline:2px solid var(--accent,#95c9fc);outline-offset:3px}
 #quick-root #quick-input:focus-visible{outline:none}#quick-compose:has(#quick-input:focus-visible){outline:2px solid var(--accent,#95c9fc);outline-offset:2px}
 #quick-root button{display:inline-grid;place-items:center;flex:none;width:44px;min-height:44px;padding:10px;border-radius:50%;border:0;background:transparent;transition:background .15s,color .15s,transform .15s}
 #quick-root button:hover:enabled{background:color-mix(in srgb,var(--quick-ink) 9%,transparent);transform:translateY(-1px)}
 #quick-root button:active:enabled{transform:scale(.94)}#quick-root button:disabled{opacity:.4}
 #quick-root svg{width:21px;height:21px;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;fill:none}
 #quick-actions,#quick-compose,#quick-reply{position:fixed;z-index:95;pointer-events:auto;background:var(--quick-bg);border:1px solid var(--line,#ffffff26);box-shadow:0 6px 20px #0002;box-sizing:border-box}
 #quick-actions{display:flex;align-items:center;gap:3px;padding:4px;border-radius:30px;width:146px;height:54px}
 #quick-actions button[aria-pressed=true]{background:color-mix(in srgb,var(--accent,#95c9fc) 20%,transparent);color:var(--accent,#95c9fc)}
 #quick-compose{width:320px;border-radius:28px;padding:6px 8px}
 #quick-compose{transition:border-color .2s,box-shadow .2s}
 #quick-compose[data-phase=listening]{border-color:var(--accent,#95c9fc);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,#95c9fc) 12%,transparent),0 6px 20px #0002}
 #quick-compose form{display:flex;align-items:center;gap:4px;margin:0}
 #quick-input{flex:1;min-width:0;width:100%;min-height:44px;background:transparent;border:0;padding:8px;outline-offset:-2px}
 #quick-root #quick-send{width:36px;min-height:36px;padding:8px;background:var(--accent,#95c9fc);color:var(--bg,#101923)}
 #quick-root #quick-close{width:32px;min-height:36px;padding:6px;font-size:20px;color:var(--secondary,#a9b6c6)}
 #quick-state{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
 #quick-level{display:flex;flex:1;align-items:center;justify-content:center;gap:4px;height:44px;margin:0 4px}
 #quick-level i{display:block;width:4px;height:var(--bar,4px);border-radius:4px;background:var(--accent,#95c9fc);transition:height .1s}
 #quick-reply{width:260px;border-radius:18px;padding:8px 12px}
 #quick-reply:after{content:"";position:absolute;bottom:-5px;left:calc(50% - 5px);width:10px;height:10px;background:var(--quick-bg);border-right:1px solid var(--line,#ffffff26);border-bottom:1px solid var(--line,#ffffff26);transform:rotate(45deg)}
 #quick-reply[data-placement=below]:after{top:-5px;bottom:auto;transform:rotate(225deg)}
 #quick-reply[data-placement=left]:after{left:auto;right:-5px;top:calc(50% - 5px);bottom:auto;transform:rotate(-45deg)}
 #quick-reply[data-placement=right]:after{left:-5px;top:calc(50% - 5px);bottom:auto;transform:rotate(135deg)}
 #quick-reply-head{display:flex;justify-content:flex-end;font-size:10px;color:var(--secondary,#a9b6c6)}
 #quick-reply-head strong{display:none}
 #quick-reply-text{margin:4px 0;max-height:84px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;scrollbar-width:thin}
 #quick-root .quick-footer{display:flex;align-items:center;gap:4px;justify-content:flex-end}
 #quick-root .quick-footer button{width:36px;padding:7px;min-height:36px;border-radius:10px}
 #quick-root .quick-footer button:first-child{margin-right:auto}
 #quick-reply[data-phase=thinking] #quick-phase{animation:quick-wait 1.5s ease-in-out infinite}
 #quick-reply[data-phase=speaking] #quick-phase:before{content:"";display:inline-block;width:5px;height:5px;margin-right:6px;border-radius:50%;background:var(--accent,#95c9fc);animation:quick-wait .8s ease-in-out infinite}
 @keyframes quick-wait{50%{opacity:.45}}
 @media(prefers-reduced-motion:reduce){#quick-root *{animation:none!important;transition:none!important}}
 </style>
 <div id="quick-actions" role="toolbar" aria-label="Acciones rápidas de Axx" hidden><button id="quick-write" title="Escribir a Axx" aria-label="Escribir a Axx">${chat}</button><button id="quick-pen" title="Magic Pen" aria-label="Abrir Magic Pen">${pen}</button><button id="quick-talk" title="Hablar con Axx" aria-label="Hablar con Axx" aria-pressed="false">${mic}</button></div>
 <section id="quick-compose" aria-label="Mensaje rápido para Axx" hidden><form id="quick-form"><input id="quick-input" maxlength="10000" autocomplete="off" aria-label="Escribir un mensaje rápido" aria-describedby="quick-state"><div id="quick-level" aria-hidden="true" hidden><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><button id="quick-send" type="submit" aria-label="Enviar mensaje rápido">${icon('<path d="M12 20V4m-6 6 6-6 6 6"/>')}</button><button id="quick-close" type="button" aria-label="Cerrar acción rápida">×</button></form><p id="quick-state" role="status" aria-live="polite"></p></section>
 <section id="quick-reply" aria-label="Respuesta rápida de Axx" hidden><div id="quick-reply-head"><strong>Axx</strong><span id="quick-phase"></span></div><p id="quick-reply-text" aria-live="polite"></p><div class="quick-footer"><button id="quick-full" type="button" aria-label="Abrir chat" title="Abrir chat">${chat}</button><button id="quick-approval" type="button" aria-label="Revisar acción" title="Revisar acción" hidden>${icon('<path d="m9 12 2 2 4-4M9 3H5v18h14V3h-4M9 2h6v4H9z"/>')}</button><button id="quick-replay" type="button" aria-label="Leer respuesta de nuevo" title="Escuchar">${icon('<path d="M11 4 5 9H2v6h3l6 5zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>')}</button><button id="quick-stop" type="button" aria-label="Detener" title="Detener">${icon('<rect x="6" y="6" width="12" height="12" rx="2"/>')}</button></div></section>`;
 document.body.append(root);
 const motions=new Map();
 const bars=[...$('quick-level').children];
 let meterFrame=null,lastMeter=null,poll=null,renderState=null;
 let mode=null,origin=null,owned=false,revision=0,hovered=false,hideTimer=null,before=null,lastText='',notice='',phase='idle',layoutKey='';
 const active=()=>mode!==null;
 const sameChat=()=>origin===Axx.chatWorkspace.active?.id;
 const capture={state:'idle',onState(){
   const other=Axx.nativeVoice.activeCapture;
   if(!(capture.state==='idle'&&other&&other.owner!==capture)){
    c.dictating=capture.state==='listening';c.dictationStarting=capture.state==='starting';c.refreshVoiceState();
    if(c.dictationStarting||capture.state==='stopping')Axx.app.machine?.setConversation('thinking');
   }
   cancelAnimationFrame(meterFrame);meterFrame=null;paintMeter();refresh();
 },onFinal(text){if(active()&&sameChat())void send(text,'voice');},onInterim(text){if(text)notice=text;refresh();},
 onError(text){notice=text;phase='error';refresh();}};
 Axx.nativeVoice.attach(capture);
 function paintMeter(){
  const listening=active()&&capture.state==='listening'&&!document.hidden,input=Axx.nativeVoice.inputLevel;
  const level=listening&&input?.owner===capture&&input.rms>0?Math.round(Math.max(0,Math.min(1,(20*Math.log10(input.rms)+60)/40))*100)/100:0;
  if(level!==lastMeter){lastMeter=level;bars.forEach((bar,i)=>bar.style.setProperty('--bar',(4+28*level*(1-Math.abs(3-i)*.17))+'px'));}
  meterFrame=listening?requestAnimationFrame(paintMeter):null;
 }
 function scheduleRefresh(){if(poll===null&&active())poll=setTimeout(()=>{poll=null;refresh();scheduleRefresh();},120);}
 function changed(){r.schedule();void Axx.app.updateHitMap();}
 function aboveAvatar(g,size){return g?g.spaceBelow<size*.34+144&&g.spaceAbove>g.spaceBelow:root.dataset.above==='true';}
 function reveal(id,on){
  const node=$(id);if(node.dataset.quickVisible===String(on))return;
  const prior=motions.get(id),wasHidden=node.hidden,style=getComputedStyle(node),from={opacity:style.opacity,translate:style.translate,scale:style.scale,borderRadius:style.borderRadius};
  prior?.cancel();node.dataset.quickVisible=String(on);node.inert=!on;node.style.pointerEvents=on?'auto':'none';
  if(!on&&wasHidden)return;
  node.hidden=false;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches,duration=reduced||document.hidden?0:(Axx.interfaceTheme?.motionDuration||520)*(on?1:.65);
  const above=aboveAvatar(r.geometry,r.size),drop=id==='quick-actions'?(above?'0 70px':'0 -70px'):id==='quick-compose'?(above?'0 42px':'0 -42px'):'0 14px',small=id==='quick-actions'?'.2 .6':'.9 .86';
  const rest={opacity:1,translate:'0 0',scale:'1 1',borderRadius:id==='quick-actions'||id==='quick-compose'?'28px':'18px'};
  const frames=on?(wasHidden?[{opacity:0,translate:drop,scale:small,borderRadius:'50%'},{...rest,translate:'0 3px',scale:'1.015 .97',offset:.78},rest]:[from,rest]):[from,{opacity:0,translate:drop,scale:small,borderRadius:'50%'}];
  const animation=node.animate(frames,{duration,easing:'cubic-bezier(.22,.75,.24,1)',fill:'both'});motions.set(id,animation);
  animation.finished.then(()=>{if(motions.get(id)!==animation)return;node.hidden=!on;motions.delete(id);animation.cancel();changed();}).catch(()=>{});
 }
 function show(){if(!active())return;reveal('quick-compose',true);refresh();}
 function hover(value){
  clearTimeout(hideTimer);
  if(value){if(!hovered){hovered=true;if(!Axx.flow.nav.step&&$('panel').hidden&&!Axx.magicPen?.isOpen())reveal('quick-actions',true);changed();}}
  else hideTimer=setTimeout(()=>{hovered=$('avatar').matches(':hover')||[...root.querySelectorAll('#quick-actions,#quick-compose,#quick-reply')].some(n=>!n.hidden&&!n.inert&&(n.matches(':hover')||document.hasFocus()&&n.matches(':focus-within')));changed();},320);
 }
 function stop(){
  revision++;capture.stop();c.stopSpeech();
  if(owned){c.cancelRequest();if(Axx.commandLibrary?.busy||Axx.commandLibrary?.operation)void Axx.commandLibrary.cancel();}
  owned=false;c._forceVoiceReplyOnce=false;notice='Detenido. Los efectos ya realizados se conservan.';phase='idle';refresh();
 }
 function close(cancel=true){
  const wasActive=active();mode=null;origin=null;hovered=false;clearTimeout(hideTimer);
  clearTimeout(poll);poll=null;renderState=null;
  if(cancel&&wasActive)stop();else capture.stop();
  for(const id of ['quick-compose','quick-reply','quick-actions'])reveal(id,false);changed();
  if(wasActive&&$('panel').hidden)void Axx.app.bridge.action('close_panel').catch(error=>Axx.app.toast(error.message));
 }
 function begin(kind){
  if(!Axx.chatWorkspace.ready||!Axx.chatWorkspace.active?.id){Axx.app.toast('Axx todavía está cargando el historial. Inténtalo en un momento.');return false;}
  if(c.pending||c.connecting||c.externalBusy||Axx.commandLibrary?.busy||Axx.symbiosis?.liveBusy){Axx.app.toast('Espera a que termine la tarea actual.');return false;}
  if(active())close();
  Axx.nativeVoice.activeCapture?.stop();
  Axx.liveConversation?.stop();r.fold();mode=kind;origin=Axx.chatWorkspace.active?.id;before=c.data.messages.at(-1)?.id;lastText='';notice='';phase='idle';renderState=null;scheduleRefresh();
  $('quick-input').value='';reveal('quick-compose',true);reveal('quick-reply',false);hovered=true;refresh();changed();
  // The resident window is normally non-focusable; the small input needs the same native focus lease as panels.
  void Axx.app.bridge.action('open_panel').then(()=>{if(mode==='write'&&sameChat())$('quick-input').focus({preventScroll:true});}).catch(error=>{if(active()){notice=error.message;phase='error';refresh();}});return true;
 }
 function write(){if(begin('write'))$('quick-input').focus({preventScroll:true});}
 function magic(){
  if(!Axx.magicPen?.open){Axx.app.toast('Magic Pen todavía no está disponible.');return;}
  if((c.pending&&!owned)||c.externalBusy||Axx.commandLibrary?.busy||Axx.symbiosis?.liveBusy){Axx.app.toast('Espera a que termine la tarea actual.');return;}
  close();Axx.nativeVoice.activeCapture?.stop();Axx.liveConversation?.stop();c.stopSpeech();r.fold();Axx.magicPen.open();
 }
 function talk(){
  if(active()&&capture.state==='listening'){capture.finish();return;}
  if(!begin('voice'))return;
  c.stopSpeech();c.stopDictation();Axx.app.stopDemo();void Axx.prepareSpeechAudio?.();capture.start(Axx.symbiosis?.prefs.language||'es-DO');
 }
 async function send(raw,source='text'){
  raw=String(raw||'').trim();
  if(!raw||!active()||!sameChat()||owned)return;
  if(!Axx.chatWorkspace.ready||c.pending||c.externalBusy||Axx.commandLibrary?.busy||Axx.commandLibrary?.operation){notice='Hay una tarea pendiente. Revisa su resultado antes de enviar otra.';refresh();return;}
  capture.stop();c.stopSpeech();const serial=++revision;owned=true;before=c.data.messages.at(-1)?.id;lastText='';phase='thinking';notice='Preparando respuesta…';
  $('quick-input').value='';reveal('quick-reply',true);c._forceVoiceReplyOnce=true;refresh();
  try{await c.send(raw,{source});}
  catch(error){if(serial===revision){notice=error.message||String(error);phase='error';}}
  finally{if(serial===revision){owned=false;c._forceVoiceReplyOnce=false;
   if(!lastText&&phase!=='error'){phase='idle';notice=Axx.commandLibrary?.operation?'La acción requiere revisión. Pulsa Revisar acción.':'No se recibió una respuesta. Comprueba el estado antes de repetir la acción.';}
   refresh();}}
 }
 function refresh(){
  if(!active())return;
  if(!sameChat()){close();return;}
  const listening=capture.state==='listening',starting=capture.state==='starting',transcribing=capture.state==='stopping';
  const reader=Axx.symbiosis?.reader,speaking=reader?.state==='speaking',speechActive=['starting','speaking','paused'].includes(reader?.state);
  const last=c.data.messages.at(-1);
  if(last?.role==='assistant'&&last.id!==before){
   lastText=last.text||'';phase=last.status==='error'?'error':last.status==='pending'&&owned?'thinking':'ready';
   reveal('quick-reply',true);
  }
  if(speaking)phase='speaking';
  if(phase==='error'&&notice)reveal('quick-reply',true);
  const next=[capture.state,reader?.state,lastText,last?.status,notice,phase,owned,!!Axx.commandLibrary?.operation];
  if(renderState&&next.every((value,i)=>value===renderState[i]))return;renderState=next;
  const text=lastText||notice||'Preparando respuesta…';if($('quick-reply').dataset.quickVisible==='true'&&$('quick-reply-text').textContent!==text)$('quick-reply-text').textContent=text;
  $('quick-reply').dataset.phase=phase;$('quick-phase').textContent=speaking?'Hablando':reader?.state==='paused'?'Voz en pausa':reader?.state==='starting'?'Preparando voz…':phase==='thinking'?'Pensando…':phase==='error'?'Revisar':'Respuesta';
  $('quick-compose').dataset.phase=listening?'listening':starting||transcribing?'preparing':'idle';
  const message=listening?'Te escucho · pausa para enviar':starting?'Preparando micrófono…':transcribing?'Transcribiendo…':owned?'Preparando respuesta…':notice||'Intro para enviar · Esc para cerrar';
  if($('quick-state').textContent!==message)$('quick-state').textContent=message;
  $('quick-talk').setAttribute('aria-pressed',String(listening||starting));$('quick-talk').setAttribute('aria-label',listening?'Terminar grabación':'Hablar con Axx');
  $('quick-level').hidden=!listening;$('quick-input').hidden=listening;$('quick-input').disabled=owned||listening||starting||transcribing;$('quick-send').disabled=owned||starting||transcribing;
  $('quick-send').setAttribute('aria-label',listening?'Terminar grabación':'Enviar mensaje rápido');
  if($('quick-send').dataset.listening!==String(listening)){$('quick-send').dataset.listening=String(listening);$('quick-send').innerHTML=listening?icon('<path d="m5 12 4 4L19 6"/>'):icon('<path d="M12 20V4m-6 6 6-6 6 6"/>');}
  $('quick-approval').hidden=!Axx.commandLibrary?.operation;
  $('quick-replay').disabled=!lastText||owned||speechActive;$('quick-stop').disabled=!owned&&!speechActive&&!listening&&!starting&&!transcribing;
  const key=[listening,starting,transcribing,$('quick-reply').hidden,Math.min(160,$('quick-reply-text').scrollHeight+64)].join('/');
  if(key!==layoutKey){layoutKey=key;changed();}
 }
 function layout(g,size,add){
  const free=!Axx.flow.nav.step&&$('panel').hidden&&!Axx.magicPen?.isOpen();
  reveal('quick-actions',free&&(hovered||active())&&!r.drag);
  const bounded=(id,width,height,x,y)=>{
   width=Math.min(width,g.workWidth-24);height=Math.min(height,g.workHeight-24);
   x=Math.max(-g.spaceLeft+12,Math.min(g.spaceRight-width-12,x));y=Math.max(-g.spaceAbove+12,Math.min(g.spaceBelow-height-12,y));
   add(id,Math.round(x),Math.round(y),width,height);
  };
  const below=size*.34+12,above=aboveAvatar(g,size);
  if(root.dataset.above!==String(above))root.dataset.above=String(above);
  const groupTop=Math.max(-g.spaceAbove+12,Math.min(g.spaceBelow-132,above?-below-120:below));
  if(!$('quick-actions').hidden)bounded('quick-actions',146,54,-73,above?groupTop+66:groupTop);
  if(active()){
   bounded('quick-compose',320,56,-160,above?groupTop:groupTop+64);
   if(!$('quick-reply').hidden){
    const width=Math.round(260*(Axx.interfaceTheme?.widgetScale||1)),height=Math.max(96,Math.min(160,$('quick-reply-text').scrollHeight+64));
    let x=-width/2,y=above?below:-below-height-4,placement=above?'below':'above';
    if((above?g.spaceBelow:g.spaceAbove)<below+height+12){placement=g.spaceLeft>=g.spaceRight?'left':'right';x=placement==='left'?-below-width:below;y=-height/2;}
    if($('quick-reply').dataset.placement!==placement)$('quick-reply').dataset.placement=placement;bounded('quick-reply',width,height,x,y);
   }
  }
 }
 $('quick-write').onclick=write;$('quick-pen').onclick=magic;$('quick-talk').onclick=talk;$('quick-close').onclick=()=>close();$('quick-stop').onclick=stop;
 $('quick-replay').onclick=()=>{if(lastText)c.read(lastText);};
 $('quick-full').onclick=()=>{close(false);c.openChat();};
 $('quick-approval').onclick=()=>{close(false);Axx.commandLibrary.open();};
 $('quick-form').onsubmit=event=>{event.preventDefault();if(capture.state==='listening')capture.finish();else void send($('quick-input').value);};
 for(const target of [$('avatar'),$('quick-actions'),$('quick-compose'),$('quick-reply')]){
  target.addEventListener('pointerenter',()=>hover(true));target.addEventListener('pointerleave',()=>hover(false));
  target.addEventListener('focusin',()=>hover(true));target.addEventListener('focusout',()=>hover(false));
 }
 $('avatar').addEventListener('pointermove',()=>{if(!r.drag)hover(true);});
 $('avatar').addEventListener('keydown',event=>{if(event.key==='Tab'&&!event.shiftKey&&!Axx.flow.nav.step&&$('panel').hidden){event.preventDefault();hover(true);$('quick-write').focus();}});
 $('quick-actions').addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const buttons=[...$('quick-actions').querySelectorAll('button')],index=buttons.indexOf(document.activeElement);buttons[event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length].focus();}});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&active()){event.preventDefault();close();}});
 const render=c.renderChat.bind(c);c.renderChat=function(...args){const result=render(...args);refresh();return result;};
 const status=c.sayStatus.bind(c);c.sayStatus=function(...args){const result=status(...args);refresh();return result;};
 const resize=new ResizeObserver(()=>{if(active())changed();});resize.observe($('quick-reply-text'));
 window.addEventListener('pagehide',()=>{close();resize.disconnect();});
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&active())close();});
 Axx.quickReply={get active(){return active();},get microphoneLevel(){const n=Axx.nativeVoice.inputLevel;return capture.state==='listening'&&n?.owner===capture?Math.max(0,Math.min(1,n.rms*12)):null;},capture,write,talk,send,show,close,refresh,layout};
})(window.Axx);
