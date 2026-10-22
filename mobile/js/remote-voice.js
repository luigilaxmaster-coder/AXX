/* Foreground microphone capture only. The PC owns session creation and command dispatch. */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id),transport=window.Capacitor?.Plugins?.AxxTransport,voice=window.Capacitor?.Plugins?.AxxVoice;
  if(!transport || !voice){$('voice-status').textContent='Remote microphone is available in the Android app.';return;}
  let polling=false,session=null,capture=null,attempted='',startError=null,uploading='',acknowledged='';
  const request=async(path,body)=>(await transport.request({path:'/v1/voice/'+path,method:'POST',body})).data;
  const labels={requested:'PC is requesting microphone access…',recording:'Listening · microphone active',stopping:'Stopping capture…',awaiting_audio:'Sending audio to your PC…',transcribing:'Transcribing on your PC with Whisper…',review:'Final text · review and confirm on your PC',ready:'Confirmed text · waiting for Axx',dispatching:'Command sent · Axx is processing',completed:'Result received from Axx',empty:'No speech recognized',failed:'Session could not complete',interrupted:'Session interrupted · review required',outcome_unknown:'Unknown result · will not resend',cancelled:'Session cancelled'};
  function display(value){
    capture=value;
    const recording=value.state==='recording';
    $('voice-panel').classList.toggle('recording',recording);
    $('voice-permit').hidden=value.permission==='granted';$('voice-stop').hidden=!recording;
    $('voice-level').hidden=!recording;$('voice-level').value=value.level||0;
    $('voice-discard').hidden=!value.session_id || recording;
    if(recording)$('voice-status').textContent='Listening on this phone · '+value.elapsed_seconds+' s';
    else if(!session)$('voice-status').textContent=value.permission==='granted'?'Ready · use your PC shortcut to start':'Grant permission once to use the PC shortcut.';
  }
  $('voice-permit').onclick=async()=>{try{display(await voice.permit());}catch(e){$('voice-status').textContent=e.message;}};
  $('voice-stop').onclick=async()=>{if(!capture?.session_id)return;try{display(await voice.stop({session_id:capture.session_id,from_pc:false}));void poll();}catch(e){$('voice-status').textContent=e.message;}};
  $('voice-discard').onclick=async()=>{
    if(!capture?.session_id)return;
    try{await request('cancel',{session_id:capture.session_id});await voice.discard({session_id:capture.session_id});display(await voice.status());}
    catch(e){$('voice-status').textContent='Cancellation not confirmed: '+e.message;}
  };
  async function poll(){
    if(polling || document.hidden)return;polling=true;
    try{
      const local=await voice.status();display(local);
      const profile=await transport.profile();if(!profile.paired)return;
      const report=startError || {state:local.state,session_id:local.session_id,reason:local.reason};
      const response=await request('poll',{visible:local.visible,permission:local.permission,capture:report});
      await voice.heartbeat();session=response.session;
      if(!session)return;
      if(local.state!=='recording')$('voice-status').textContent=(labels[session.state]||session.state)+(session.error?' · '+session.error:'');
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
    }catch(e){$('voice-status').textContent='Voice offline: '+e.message+'. Capture stops if contact with the PC is lost.';}
    finally{polling=false;}
  }
  void voice.addListener('captureState',display);
  setInterval(()=>void poll(),750);document.addEventListener('visibilitychange',()=>{if(!document.hidden)void poll();});void poll();
})();
