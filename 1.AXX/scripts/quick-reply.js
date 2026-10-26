/* Small avatar interactions share the existing chat, microphone and speech owners. */
(function(Axx){
 'use strict';
 if(!Axx?.isNative()||!Axx.resident||!Axx.nativeVoice||!Axx.chatWorkspace)return;
 const c=Axx.companion,r=Axx.resident,$=id=>document.getElementById(id);
 const icon=(path)=>`<svg aria-hidden="true" viewBox="0 0 24 24">${path}</svg>`;
 const mic=icon('<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>');
 const pen=icon('<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14z"/>');
 const root=document.createElement('div');root.id='quick-root';
 root.innerHTML=`<style>
 #quick-root{--quick-bg:var(--surface,#18212c);--quick-ink:var(--ink,#edf2fa);color:var(--quick-ink);font:13px/1.5 "Segoe UI",sans-serif}
 #quick-root [hidden]{display:none!important}#quick-root :is(button,input){font:inherit;box-sizing:border-box;color:inherit}
 #quick-root :is(button,input):focus-visible{outline:2px solid var(--accent,#95c9fc);outline-offset:3px}
 #quick-root button{display:inline-grid;place-items:center;flex:none;width:44px;min-height:44px;padding:10px;border-radius:50%;border:0;background:transparent}
 #quick-root button:hover{background:color-mix(in srgb,var(--quick-ink) 9%,transparent)}
 #quick-root svg{width:21px;height:21px;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;fill:none}
 #quick-actions,#quick-compose,#quick-reply{position:fixed;z-index:95;pointer-events:auto;background:var(--quick-bg);border:1px solid var(--line,#ffffff26);box-shadow:0 10px 30px #0003;box-sizing:border-box}
 #quick-actions{display:flex;align-items:center;gap:3px;padding:4px;border-radius:30px;width:99px;height:54px}
 #quick-actions button[aria-pressed=true]{background:color-mix(in srgb,var(--accent,#95c9fc) 20%,transparent);color:var(--accent,#95c9fc)}
 #quick-compose{width:340px;border-radius:22px;padding:8px 10px}
 #quick-compose[data-phase=listening]{border-color:var(--accent,#95c9fc);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,#95c9fc) 12%,transparent),0 10px 30px #0003}
 #quick-compose form{display:flex;align-items:center;gap:4px;margin:0}
 #quick-input{flex:1;min-width:0;width:100%;min-height:44px;background:transparent;border:0;padding:8px;outline-offset:-2px}
 #quick-send{background:var(--accent,#95c9fc)!important;color:var(--bg,#101923)!important}
 #quick-state{font-size:11px;color:var(--secondary,#a9b6c6);margin:3px 8px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 #quick-level{display:flex;align-items:center;justify-content:center;gap:4px;height:36px;margin:0 4px}
 #quick-level i{display:block;width:4px;height:var(--bar,4px);border-radius:4px;background:var(--accent,#95c9fc);transition:height .1s}
 #quick-reply{width:340px;border-radius:20px;padding:14px 16px}
 #quick-reply:after{content:"";position:absolute;bottom:-5px;left:calc(50% - 5px);width:10px;height:10px;background:var(--quick-bg);border-right:1px solid var(--line,#ffffff26);border-bottom:1px solid var(--line,#ffffff26);transform:rotate(45deg)}
 #quick-reply-head{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--secondary,#a9b6c6)}
 #quick-reply-head strong{flex:1;color:var(--quick-ink);font-size:12px}
 #quick-reply-text{margin:8px 0;max-height:148px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;scrollbar-width:thin}
 #quick-root .quick-footer{display:flex;align-items:center;gap:4px;justify-content:flex-end}
 #quick-root .quick-footer button{width:auto;padding:6px 9px;min-height:36px;border-radius:10px;font-size:11px}
 #quick-root .quick-footer button:first-child{margin-right:auto}
 #quick-reply[data-phase=thinking] #quick-phase{animation:quick-wait 1.5s ease-in-out infinite}
 #quick-reply[data-phase=speaking] #quick-phase:before{content:"";display:inline-block;width:5px;height:5px;margin-right:6px;border-radius:50%;background:var(--accent,#95c9fc);animation:quick-wait .8s ease-in-out infinite}
 @keyframes quick-wait{50%{opacity:.45}}
 @media(prefers-reduced-motion:reduce){#quick-root *{animation:none!important;transition:none!important}}
 </style>
 <div id="quick-actions" role="toolbar" aria-label="Acciones rápidas de Axx" hidden><button id="quick-write" title="Escribir a Axx" aria-label="Escribir a Axx">${pen}</button><button id="quick-talk" title="Hablar con Axx" aria-label="Hablar con Axx" aria-pressed="false">${mic}</button></div>
 <section id="quick-compose" aria-label="Mensaje rápido para Axx" hidden><form id="quick-form"><input id="quick-input" maxlength="10000" autocomplete="off" aria-label="Escribir un mensaje rápido" placeholder="Pregúntale algo a Axx…"><button id="quick-send" type="submit" aria-label="Enviar mensaje rápido">${icon('<path d="M12 20V4m-6 6 6-6 6 6"/>')}</button><button id="quick-close" type="button" aria-label="Cerrar acción rápida">×</button></form><div id="quick-level" aria-hidden="true" hidden><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><p id="quick-state" role="status" aria-live="polite"></p></section>
 <section id="quick-reply" aria-label="Respuesta rápida de Axx" hidden><div id="quick-reply-head"><strong>Axx</strong><span id="quick-phase"></span></div><p id="quick-reply-text" aria-live="polite"></p><div class="quick-footer"><button id="quick-full" type="button">Abrir chat</button><button id="quick-approval" type="button" hidden>Revisar acción</button><button id="quick-replay" type="button" aria-label="Leer respuesta de nuevo">Escuchar</button><button id="quick-stop" type="button">Detener</button></div></section>`;
 document.body.append(root);
 let mode=null,origin=null,owned=false,revision=0,hovered=false,hideTimer=null,before=null,lastText='',notice='',phase='idle',layoutKey='';
 const active=()=>mode!==null;
 const sameChat=()=>origin===Axx.chatWorkspace.active?.id;
 const capture={state:'idle',onState(){
   c.dictating=capture.state==='listening';c.dictationStarting=capture.state==='starting';c.refreshVoiceState();
   if(c.dictationStarting)Axx.app.machine?.setConversation('thinking');refresh();
 },onFinal(text){if(active()&&sameChat())void send(text,'voice');},onInterim(text){if(text)notice=text;refresh();},
 onError(text){notice=text;phase='error';refresh();}};
 Axx.nativeVoice.attach(capture);
 function changed(){r.schedule();void Axx.app.updateHitMap();}
 function show(){if(!active())return; $('quick-compose').hidden=false;refresh();}
 function hover(value){
  clearTimeout(hideTimer);
  if(value){if(!hovered){hovered=true;if(!Axx.flow.nav.step&&$('panel').hidden)$('quick-actions').hidden=false;changed();}}
  else hideTimer=setTimeout(()=>{hovered=false;changed();},220);
 }
 function stop(){
  revision++;capture.stop();c.stopSpeech();
  if(owned){c.cancelRequest();if(Axx.commandLibrary?.busy||Axx.commandLibrary?.operation)void Axx.commandLibrary.cancel();}
  owned=false;c._forceVoiceReplyOnce=false;notice='Detenido. Los efectos ya realizados se conservan.';phase='idle';refresh();
 }
 function close(cancel=true){
  const wasActive=active();mode=null;origin=null;hovered=false;clearTimeout(hideTimer);
  if(cancel&&wasActive)stop();else capture.stop();
  $('quick-compose').hidden=$('quick-reply').hidden=$('quick-actions').hidden=true;changed();
 }
 function begin(kind){
  if(!Axx.chatWorkspace.ready||!Axx.chatWorkspace.active?.id){Axx.app.toast('Axx todavía está cargando el historial. Inténtalo en un momento.');return false;}
  if(c.pending||c.connecting||c.externalBusy||Axx.commandLibrary?.busy||Axx.symbiosis?.liveBusy){Axx.app.toast('Espera a que termine la tarea actual.');return false;}
  if(active())close();
  Axx.nativeVoice.activeCapture?.stop();
  Axx.liveConversation?.stop();r.fold();mode=kind;origin=Axx.chatWorkspace.active?.id;before=c.data.messages.at(-1)?.id;lastText='';notice='';phase='idle';
  $('quick-input').value='';$('quick-compose').hidden=false;$('quick-reply').hidden=true;hovered=true;refresh();changed();return true;
 }
 function write(){if(begin('write'))$('quick-input').focus({preventScroll:true});}
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
  $('quick-input').value='';$('quick-reply').hidden=false;c._forceVoiceReplyOnce=true;refresh();
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
  const reader=Axx.symbiosis?.reader,speaking=reader?.state==='speaking';
  const last=c.data.messages.at(-1);
  if(last?.role==='assistant'&&last.id!==before){
   lastText=last.text||'';phase=last.status==='error'?'error':last.status==='pending'&&owned?'thinking':'ready';
   $('quick-reply').hidden=false;
  }
  if(speaking)phase='speaking';
  const text=lastText||notice||'Preparando respuesta…';if($('quick-reply-text').textContent!==text)$('quick-reply-text').textContent=text;
  $('quick-reply').dataset.phase=phase;$('quick-phase').textContent=speaking?'Hablando':phase==='thinking'?'Pensando…':phase==='error'?'Revisar':'Respuesta';
  $('quick-compose').dataset.phase=listening?'listening':starting||transcribing?'preparing':'idle';
  const message=listening?'Te escucho · termina con una pausa o vuelve a pulsar Hablar':starting?'Preparando micrófono o transcripción…':transcribing?'Transcribiendo en este equipo…':owned?'Preparando respuesta…':notice||'Escribe y pulsa Intro · Escape para cerrar';
  if($('quick-state').textContent!==message)$('quick-state').textContent=message;
  $('quick-talk').setAttribute('aria-pressed',String(listening||starting));$('quick-talk').setAttribute('aria-label',listening?'Terminar grabación':'Hablar con Axx');
  $('quick-level').hidden=!listening;$('quick-input').disabled=owned||listening||starting||transcribing;$('quick-send').disabled=owned||starting||transcribing;
  $('quick-approval').hidden=!Axx.commandLibrary?.operation;
  $('quick-replay').disabled=!lastText||owned;$('quick-stop').disabled=!owned&&!speaking&&!listening&&!starting&&!transcribing;
  const input=Axx.nativeVoice.inputLevel,level=listening&&input?.owner===capture&&input.rms>0?Math.max(0,Math.min(1,(20*Math.log10(input.rms)+60)/40)):0;
  [...$('quick-level').children].forEach((bar,i)=>bar.style.setProperty('--bar',(4+28*level*(1-Math.abs(3-i)*.17))+'px'));
  const key=[listening,starting,transcribing,$('quick-reply').hidden,Math.min(240,$('quick-reply-text').scrollHeight+80)].join('/');
  if(key!==layoutKey){layoutKey=key;changed();}
 }
 function layout(g,size,add){
  const free=!Axx.flow.nav.step&&$('panel').hidden;
  $('quick-actions').hidden=!free||(!hovered&&!active());
  const bounded=(id,width,height,x,y)=>{
   width=Math.min(width,g.workWidth-24);height=Math.min(height,g.workHeight-24);
   x=Math.max(-g.spaceLeft+12,Math.min(g.spaceRight-width-12,x));y=Math.max(-g.spaceAbove+12,Math.min(g.spaceBelow-height-12,y));
   add(id,Math.round(x),Math.round(y),width,height);
  };
  const below=size*.34+12;
  if(!$('quick-actions').hidden)bounded('quick-actions',99,54,-49.5,below);
  if(active()){
   const height=$('quick-level').hidden?96:132;
   bounded('quick-compose',340,height,-170,below+64);
   if(!$('quick-reply').hidden){const height=Math.max(120,Math.min(240,$('quick-reply-text').scrollHeight+80));bounded('quick-reply',340,height,-170,-size*.34-height-16);}
  }
 }
 $('quick-write').onclick=write;$('quick-talk').onclick=talk;$('quick-close').onclick=()=>close();$('quick-stop').onclick=stop;
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
 $('quick-actions').addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();($(document.activeElement.id==='quick-write'?'quick-talk':'quick-write')).focus();}});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&active()){event.preventDefault();close();}});
 const render=c.renderChat.bind(c);c.renderChat=function(...args){const result=render(...args);refresh();return result;};
 const status=c.sayStatus.bind(c);c.sayStatus=function(...args){const result=status(...args);refresh();return result;};
 const poll=setInterval(()=>{if(active())refresh();},120);
 window.addEventListener('pagehide',()=>{close();clearInterval(poll);});
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&active())close();});
 Axx.quickReply={get active(){return active();},get microphoneLevel(){const n=Axx.nativeVoice.inputLevel;return capture.state==='listening'&&n?.owner===capture?Math.max(0,Math.min(1,n.rms*12)):null;},capture,write,talk,send,show,close,refresh,layout};
})(window.Axx);
