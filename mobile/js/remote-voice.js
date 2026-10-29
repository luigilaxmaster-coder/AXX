/* Foreground microphone capture only. The PC owns command dispatch. */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id),transport=window.Capacitor?.Plugins?.AxxTransport,voice=window.Capacitor?.Plugins?.AxxVoice;
  if(!transport || !voice){$('voice-quick').hidden=true;$('voice-status').textContent='El micrófono está disponible en la app Android.';return;}
  let polling=false,session=null,capture=null,attempted='',startError=null,uploading='',acknowledged='',busy=false,failure='';
  const request=async(path,body)=>(await transport.request({path:'/v1/voice/'+path,method:'POST',body})).data;
  const setting={taps:'2',key:'off',mode:'confirm',limit:'30'};
  try{const saved=JSON.parse(localStorage.getItem('axx.phoneVoiceShortcut')||'{}');for(const key of Object.keys(setting)){
    const valid={taps:['1','2','3'],key:['off','alt-v','ctrl-shift-v'],mode:['confirm','handsfree'],limit:['15','30','55']};
    if(valid[key].includes(saved[key]))setting[key]=saved[key];
  }}catch{}
  for(const key of Object.keys(setting)){
    const field=$('voice-'+key);field.value=setting[key];field.onchange=()=>{
      setting[key]=field.value;localStorage.setItem('axx.phoneVoiceShortcut',JSON.stringify(setting));updateShortcut();
    };
  }
  const quick=$('voice-quick'),trigger=$('voice-trigger');
  const quickStatus=document.createElement('p');quickStatus.className='hint voice-quick-status';quickStatus.setAttribute('role','status');quickStatus.setAttribute('aria-live','polite');quick.after(quickStatus);
  const tapNames={1:'una vez',2:'dos veces',3:'tres veces'};
  function updateShortcut(){
    const label=capture?.state==='recording'?'Escuchando · toca '+tapNames[setting.taps]+' para terminar':'Toca '+tapNames[setting.taps]+' para hablar a la PC';
    quick.textContent=label;trigger.textContent=label;quick.setAttribute('aria-label',label);trigger.setAttribute('aria-label',label);
  }
  updateShortcut();
  const labels={requested:'Tu PC solicita el micrófono…',recording:'Escuchando · micrófono activo',stopping:'Deteniendo grabación…',awaiting_audio:'Enviando audio al PC…',transcribing:'Transcribiendo en tu PC…',review:'Revisa y confirma el texto en el PC',ready:'Texto confirmado · esperando a Axx',dispatching:'Orden enviada · Axx está procesando',completed:'Respuesta recibida',empty:'No se reconoció voz',failed:'No se pudo completar',interrupted:'Interrumpido · revisa el PC',outcome_unknown:'Resultado sin confirmar · no se repetirá',cancelled:'Sesión cancelada'};
  function display(value){
    if(window.axxFileDictationActive)return;
    capture=value;
    const recording=value.state==='recording';
    updateShortcut();
    if(recording)$('voice-details').open=true;
    $('voice-panel').classList.toggle('recording',recording);
    $('voice-permit').hidden=value.permission==='granted';$('voice-stop').hidden=!recording;
    $('voice-level').hidden=!recording;$('voice-level').value=value.level||0;
    $('voice-discard').hidden=!value.session_id || recording;
    if(recording){$('voice-status').textContent='Escuchando en el teléfono · '+value.elapsed_seconds+' s';quickStatus.textContent='Micrófono activo · '+value.elapsed_seconds+' s';}
    else if(!session){$('voice-status').textContent=failure || (value.permission==='granted'?'Listo · usa el gesto del teléfono o el atajo del PC':'Permite el micrófono para iniciar.');quickStatus.textContent=failure;}
  }
  async function phoneAction(){
    if(busy || document.hidden || window.axxFileDictationActive)return;
    busy=true;failure='';quick.disabled=trigger.disabled=true;
    try{
      const profile=await transport.profile();
      if(!profile.paired)throw new Error('Enlaza primero el teléfono con Axx en la PC.');
      let local=await voice.status();
      if(!local.visible)throw new Error('Abre Axx Mobile y desbloquea el teléfono.');
      if(local.state==='idle' && local.permission!=='granted')local=await voice.permit();
      if(local.permission!=='granted')throw new Error('Concede el permiso del micrófono en Android.');
      const report={visible:local.visible,permission:local.permission,capture:{state:local.state,session_id:local.session_id||'',reason:local.reason||''}};
      session=(await request('poll',report)).session;
      const active=local.state==='recording' && local.session_id && session?.session_id===local.session_id;
      if(local.state!=='idle' && !active)throw new Error('Termina o descarta la grabación anterior.');
      if(active){
        session=await request('action',{action:'stop',session_id:local.session_id});
        display(await voice.stop({session_id:local.session_id,from_pc:false}));
      }else{
        session=await request('action',{action:'start',mode:setting.mode,max_seconds:Number(setting.limit)});
        await poll();
      }
    }catch(error){failure='Micrófono remoto: '+error.message;$('voice-status').textContent=failure;quickStatus.textContent=failure;}
    finally{busy=false;quick.disabled=trigger.disabled=false;}
  }
  let taps=0,lastTap=0;
  function gesture(){
    const now=Date.now();taps=now-lastTap<900?taps+1:1;lastTap=now;
    if(taps<Number(setting.taps)){$('voice-status').textContent=`Toque ${taps} de ${setting.taps}`;return;}
    taps=0;void phoneAction();
  }
  quick.onclick=gesture;trigger.onclick=gesture;
  document.addEventListener('keydown',event=>{
    if(event.repeat || document.hidden || setting.key==='off' || event.target?.closest?.('input,textarea,select,[contenteditable]'))return;
    const match=setting.key==='alt-v'?event.altKey&&!event.ctrlKey&&!event.shiftKey:event.ctrlKey&&event.shiftKey&&!event.altKey;
    if(match && event.key.toLowerCase()==='v'){event.preventDefault();void phoneAction();}
  });
  $('voice-permit').onclick=async()=>{try{display(await voice.permit());}catch(e){$('voice-status').textContent=e.message;}};
  $('voice-stop').onclick=async()=>{if(!capture?.session_id)return;try{display(await voice.stop({session_id:capture.session_id,from_pc:false}));void poll();}catch(e){$('voice-status').textContent=e.message;}};
  $('voice-discard').onclick=async()=>{
    if(!capture?.session_id)return;
    try{await request('cancel',{session_id:capture.session_id});await voice.discard({session_id:capture.session_id});display(await voice.status());}
    catch(e){$('voice-status').textContent='Cancelación sin confirmar: '+e.message;}
  };
  async function poll(){
    if(polling || document.hidden || window.axxFileDictationActive)return;polling=true;
    try{
      const local=await voice.status();display(local);
      const profile=await transport.profile();if(!profile.paired)return;
      const report=startError || {state:local.state,session_id:local.session_id,reason:local.reason};
      const response=await request('poll',{visible:local.visible,permission:local.permission,capture:report});
      if(window.axxFileDictationActive)return;
      await voice.heartbeat();session=response.session;
      if(!session)return;
      if(local.state!=='recording'){$('voice-status').textContent=(labels[session.state]||session.state)+(session.error?' · '+session.error:'');quickStatus.textContent=$('voice-status').textContent;}
      $('voice-text').textContent=session.confirmed_text || session.text || '';
      $('voice-text').hidden=!$('voice-text').textContent;
      $('voice-result').textContent=session.result?.messages?.filter(m=>m.role==='assistant').map(m=>m.text).join('\n') || '';
      if(session.state==='requested' && attempted!==session.session_id && local.state==='idle'){
        attempted=session.session_id;startError=null;
        try{display(await voice.start({session_id:session.session_id,max_seconds:session.max_seconds}));}
        catch(e){startError={session_id:session.session_id,state:'failed',reason:e.message.slice(0,200)};$('voice-status').textContent=e.message;}
      }
      if(local.session_id===session.session_id && local.state==='recording' && !['requested','recording'].includes(session.state))display(await voice.stop({session_id:session.session_id,from_pc:true}));
      if(local.session_id===session.session_id && local.state==='stopped' && ['awaiting_audio','stopping','recording','interrupted'].includes(session.state) && uploading!==session.session_id){
        uploading=session.session_id;
        try{const audio=await voice.audio({session_id:session.session_id});await request('audio',audio);}
        finally{uploading='';}
      }
      if(local.session_id===session.session_id && ['review','ready','dispatching','completed','empty','cancelled'].includes(session.state) && acknowledged!==session.session_id){
        await voice.discard({session_id:session.session_id});acknowledged=session.session_id;display(await voice.status());
      }
    }catch(e){$('voice-status').textContent='Voz sin conexión: '+e.message+'. La grabación se detiene al perder contacto con el PC.';}
    finally{polling=false;}
  }
  void voice.addListener('captureState',display);
  setInterval(()=>void poll(),750);document.addEventListener('visibilitychange',()=>{if(!document.hidden)void poll();});void poll();
})();
