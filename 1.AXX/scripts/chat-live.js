/* Continuous voice turns over the existing capture, chat and speech owners. */
(function(Axx){
 'use strict';if(!Axx?.isNative()||!Axx.symbiosis||Axx.liveConversation)return;
 const s=Axx.symbiosis,c=Axx.companion,$=id=>document.getElementById(id);
 let revision=0,starting=false,lastError='',turnStarted=0,firstAudio=0;
 let pauseMs=900;try{const saved=Number(localStorage.getItem('axx.live.pause'));if([700,900,1500].includes(saved))pauseMs=saved;}catch{}
 const toggle=document.createElement('button');toggle.id='chat-live-toggle';toggle.type='button';toggle.className='chat-live-launch';toggle.innerHTML='<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 10v4m4-7v10m4-13v16m4-13v10m4-7v4"/></svg><span>Voz en vivo</span>';toggle.title='Hablar con Axx: escucha, responde y vuelve a escuchar';toggle.setAttribute('aria-label','Voz en vivo: conversar con Axx');toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls','chat-live');document.querySelector('#chat-form .composer-bottom > div')?.append(toggle);
 const card=document.createElement('section');card.id='chat-live';card.hidden=true;card.setAttribute('aria-label','Conversación por voz');
 card.innerHTML='<div class="chat-live-heading"><strong>Conversación por voz</strong><button id="chat-live-close" type="button" aria-label="Cerrar conversación por voz">×</button></div><p id="chat-live-status" role="status" aria-live="polite">Habla y deja una pausa. Axx responderá y volverá a escucharte.</p><div class="chat-live-controls"><button id="chat-live-start" type="button">Iniciar</button><button id="chat-live-finish" type="button" hidden>Responder ahora</button><button id="chat-live-interrupt" type="button" hidden>Interrumpir y hablar</button><button id="chat-live-stop" type="button" hidden>Terminar</button></div><small id="chat-live-metrics"></small><details><summary>Voz, ritmo y privacidad</summary><div class="chat-live-settings"><label>Voz<select id="chat-live-voice"></select></label><label>Modelo para voz<select id="chat-live-model"><option value="">Mismo del chat</option></select></label><label>Pausa para responder<select id="chat-live-pause"><option value="700">Rápida · 0,7 s</option><option value="900">Ágil · 0,9 s</option><option value="1500">Tranquila · 1,5 s</option></select></label></div><p class="chat-live-privacy">Micrófono y transcripción local. El texto y el contexto elegido van al modelo del chat. El micrófono se pausa mientras Axx responde.</p></details>';
 $('chat-workspace').append(card);$('chat-live-pause').value=String(pauseMs);
 const inputMonitor=document.createElement('div');inputMonitor.className='chat-live-input';inputMonitor.innerHTML='<div><span id="chat-live-input-label">Entrada de micrófono</span><span id="chat-live-input-state">Apagado</span></div><meter id="chat-live-level" min="0" max="100" value="0" aria-label="Nivel de entrada del micrófono"></meter>';$('chat-live-status').after(inputMonitor);
 const inputSetting=document.createElement('label');inputSetting.textContent='Micrófono';const inputSelect=document.createElement('select');inputSelect.id='chat-live-microphone';inputSetting.append(inputSelect);card.querySelector('.chat-live-settings').prepend(inputSetting);
 function models(){
  const select=$('chat-live-model'),selected=c.data.prefs.voiceModel||'';
  const available=c.brain.connected&&c.data.prefs.selection_mode!=='automatic_free'?c.brain.models:[];
  select.replaceChildren(new Option('Mismo del chat',''));
  for(const model of available)select.add(new Option(model,model));
  if(selected&&!available.includes(selected)){const missing=new Option(selected+' · no disponible',selected);missing.disabled=true;select.add(missing);}
  select.value=selected;
 }
 function show(){card.hidden=false;toggle.setAttribute('aria-expanded','true');c.openChat();models();void voices();void microphones();render();}
 function stop(){const owned=starting||s.liveActive||s.liveBusy;revision++;starting=false;if(owned){s.stopListening();c.cancelRequest();c.stopSpeech();}render();}
 async function start(){
  show();if(starting||s.liveActive)return;
  if(!Axx.chatWorkspace?.ready){lastError='El historial todavía se está cargando.';render();return;}
  if(c.data.prefs.mutedAll){lastError='Activa el sonido antes de conversar por voz.';render();return;}
  if(c.pending||s.liveBusy){lastError='Espera a que termine la respuesta actual o pulsa Detener.';render();return;}
  const id=++revision;starting=true;lastError='';render();
  try{
   if(!c.brain.connected)await c.connect();
   if(id!==revision)return;
   if(!c.brain.connected)throw Error('Conecta un modelo en IA y vuelve a iniciar.');
   models();
   if(c.data.prefs.voiceModel&&(c.data.prefs.selection_mode==='automatic_free'||!c.brain.models.includes(c.data.prefs.voiceModel)))throw Error('El modelo para voz no está disponible en esta conexión. Elige Mismo del chat o un modelo de la lista.');
   await Axx.prepareSpeechAudio?.();
   if(id!==revision)return;
   s.startListening('live');
  }catch(e){if(id===revision)lastError=e.message||String(e);}
  finally{if(id===revision){starting=false;render();}}
 }
 async function interrupt(){
  stop();const id=revision;lastError='';starting=true;render();
  try{await s.liveTask;}catch{}
  if(id!==revision)return;starting=false;await start();
 }
 async function voices(){
  try{
   const list=await Axx.nativeVoice.refreshVoices(),select=$('chat-live-voice');select.replaceChildren();
   select.add(new Option('Windows automática · menor espera',''));
   for(const v of list)select.add(new Option((v.engine==='moss-onnx'?'Natural · ':'Windows · ')+(v.label||v.name),v.engine==='moss-onnx'?v.name:'sapi:'+v.name));
   const uri=s.reader.voiceURI||'';
   if(uri.startsWith('web:'))select.add(new Option('Voz del sistema seleccionada',uri));
   select.value=uri;
  }catch(e){lastError=e.message||String(e);render();}
 }
 async function microphones(){
  try{
   const devices=await navigator.mediaDevices.enumerateDevices(),selected=Axx.nativeVoice.liveDeviceId||'',select=$('chat-live-microphone');
   const inputs=devices.filter(d=>d.kind==='audioinput'&&!['default','communications'].includes(d.deviceId));
   select.replaceChildren(new Option('Predeterminado de Windows',''));
   inputs.forEach((d,i)=>select.add(new Option(d.label||'Micrófono '+(i+1),d.deviceId)));
   if(selected&&!inputs.some(d=>d.deviceId===selected))select.add(new Option('Micrófono seleccionado · no disponible',selected));
   select.value=selected;
  }catch{ $('chat-live-input-state').textContent='No se pudieron consultar las entradas'; }
 }
 function render(){
  const active=s.liveActive||starting,listen=s.liveActive&&s.dictation.state==='listening',preparing=s.liveActive&&s.dictation.state==='starting',speaking=s.liveActive&&['speaking','starting'].includes(s.reader.state);
  toggle.setAttribute('aria-pressed',String(active));$('chat-live-start').hidden=active;$('chat-live-stop').hidden=!active;
  const label=active?'Voz activa':'Voz en vivo';const labelNode=toggle.querySelector('span');if(labelNode.textContent!==label)labelNode.textContent=label;
  toggle.title=active?'Terminar conversación por voz':'Iniciar conversación por voz con Axx';
  toggle.setAttribute('aria-label',active?'Terminar conversación por voz':'Voz en vivo: iniciar conversación con Axx');
  $('chat-live-finish').hidden=!listen||s.dictation.state!=='listening';$('chat-live-interrupt').hidden=!s.liveActive||listen;
  $('chat-live-voice').disabled=active;$('chat-live-pause').disabled=active;$('chat-live-microphone').disabled=active;$('chat-live-model').disabled=active;
  if(s.liveActive&&s.reader.state==='speaking'&&turnStarted&&!firstAudio)firstAudio=performance.now()-turnStarted;
  const status=starting?'Preparando conversación…':lastError||(!s.liveActive?'Pulsa Iniciar para conversar.':preparing?'Preparando y comprobando el micrófono…':listen?'Te escucho. Habla y deja una pausa, o pulsa Responder ahora.':speaking?(s.reader.state==='starting'?'Preparando la voz…':'Axx está hablando. Puedes interrumpir.'):s.liveBusy?'Preparando la respuesta…':'Transcribiendo tu voz localmente…');
  if($('chat-live-status').textContent!==status)$('chat-live-status').textContent=status;
  const input=Axx.nativeVoice.inputLevel,level=listen&&input?.owner===s.dictation?input:null;
  $('chat-live-level').value=level?.rms?Math.max(0,Math.min(100,(20*Math.log10(level.rms)+60)/.6)):0;
  $('chat-live-input-label').textContent=level?.device||'Entrada de micrófono';
  $('chat-live-input-state').textContent=!listen?(preparing?'Comprobando…':'Apagado'):level?.phase==='calibrating'?'Ajustando nivel…':level?.phase==='voice'?'Voz detectada':level?.phase==='noise'?'Mucho ruido de fondo':level?.heard_speech?'Esperando tu pausa…':'Habla y revisa que suba el nivel';
  inputMonitor.title=level?`RMS ${level.rms.toFixed(4)} · umbral ${level.threshold.toFixed(4)} · ruido ${level.noise_floor.toFixed(4)}`:'';
  $('chat-live-metrics').textContent=firstAudio?'Último turno: '+(firstAudio/1000).toFixed(1)+' s desde el texto reconocido hasta la voz'+(Axx.nativeVoice.lastRecognition?' · transcripción '+(Axx.nativeVoice.lastRecognition.duration_ms/1000).toFixed(1)+' s':''):'Modelo: '+(c.data.prefs.model||'sin seleccionar');
 }
 const send=s.sendLive.bind(s);s.sendLive=function(){
  if(!s.liveActive||s.liveBusy||!s.liveText.trim())return Promise.resolve();
  turnStarted=performance.now();firstAudio=0;lastError='';
  const task=send().catch(e=>{s.stopListening();lastError=e.message||String(e);}).finally(render);s.liveTask=task;return task;
 };
 const dictError=s.dictation.onError;s.dictation.onError=message=>{if(s.liveActive)lastError=message;dictError?.(message);render();};
 const readerError=s.reader.onError;s.reader.onError=message=>{if(s.liveActive)lastError=message;readerError?.(message);render();};
 s.startLive=start;$('live-start').onclick=start;$('live-stop').onclick=stop;
 toggle.onclick=()=>{if(s.liveActive||starting){stop();}else{void start();}};
 $('chat-live-start').onclick=start;$('chat-live-stop').onclick=stop;$('chat-live-interrupt').onclick=interrupt;
 $('chat-live-finish').onclick=()=>s.dictation.finish();$('chat-live-close').onclick=()=>{stop();card.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus();};
  $('chat-live-pause').onchange=e=>{const v=parseInt(e.target.value,10);pauseMs=[700,900,1500].includes(v)?v:900;try{localStorage.setItem('axx.live.pause',String(pauseMs));}catch{}};
  $('chat-live-model').onchange=e=>{const m=e.target.value;if(m&&(!c.brain.connected||c.data.prefs.selection_mode==='automatic_free'||!c.brain.models.includes(m))){lastError='Selecciona un modelo disponible en esta conexión.';models();render();return;}c.data.prefs.voiceModel=m;lastError='';c.save();render();};
 $('chat-live-voice').onchange=e=>{
  const uri=e.target.value;s.reader.voiceURI=uri;if(Axx.voice13?.reader)Axx.voice13.reader.voiceURI=uri;
  try{localStorage.setItem('axx.voice.uri',uri);}catch{}
  for(const id of ['chat-voice-select','reader-voice','v13-voice'])if($(id))$(id).value=uri;
  Axx.nativeVoice.prepareVoice(uri);
 };
 $('chat-live-microphone').onchange=e=>{Axx.nativeVoice.liveDeviceId=e.target.value;try{localStorage.setItem('axx.live.microphone',e.target.value);}catch{lastError='No se pudo guardar el micrófono seleccionado.';}render();};
 const deviceChange=()=>{void microphones();};navigator.mediaDevices?.addEventListener?.('devicechange',deviceChange);
 const poll=setInterval(()=>{if((s.liveActive||starting)&&($('panel').hidden||$('panel').dataset.view!=='chat'||document.hidden))stop();if(!card.hidden)render();},200);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('pagehide',()=>{stop();clearInterval(poll);navigator.mediaDevices?.removeEventListener?.('devicechange',deviceChange);});
 Axx.liveConversation={start,stop,interrupt,show,get active(){return s.liveActive;},get pauseMs(){return pauseMs;},get firstAudioMs(){return firstAudio;}};
 render();
})(window.Axx);
