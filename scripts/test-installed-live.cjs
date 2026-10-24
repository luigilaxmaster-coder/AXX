// Real installed ASR, selected model and TTS, with a locally synthesized input.
// A short microphone availability check is separate from the synthetic utterance.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 const receipt={kind:'INSTALLED_CONTINUOUS_VOICE',input:'Locally synthesized speech, not physical human speech',checks:[]};let prior,source,destination;
 const api=(method,route,body)=>p.evaluate(({method,route,body})=>Axx.backendRequest(method,route,body),{method,route,body});
 const restoreTranscript=()=>p.evaluate(()=>{
  const old=window.__axxPriorTranscript;if(!old)return;
  const s=Axx.symbiosis,player=document.getElementById('transcript-player');
  player.pause();
  if(old.file){s.loadMedia(old.file);player.currentTime=old.time;}
  else{if(s.mediaURL)URL.revokeObjectURL(s.mediaURL);s.mediaURL=null;s.mediaFile=null;player.removeAttribute('src');player.load();player.hidden=old.hidden;}
  s.cues=old.cues;s.transcriptSource=old.source;s.mediaName=old.name;s.mediaCue=old.cue;
  player.muted=old.muted;player.playbackRate=old.rate;
  document.getElementById('media-file-label').textContent=old.label;
  document.getElementById('transcript-file-status').textContent=old.status;
  const files=new DataTransfer();if(old.file)files.items.add(old.file);document.getElementById('transcript-media').files=files.files;
  s.renderCues();if(!old.paused&&old.file)void player.play().catch(()=>{});delete window.__axxPriorTranscript;
 });
 try{
  await p.waitForFunction(()=>Axx.chatWorkspace?.ready&&Axx.liveConversation);
  prior=await p.evaluate(()=>({id:Axx.chatWorkspace.active.id,voice:Axx.symbiosis.reader.voiceURI,voicePref:localStorage.getItem('axx.voice.uri'),muted:Axx.companion.data.prefs.mutedAll}));
  source=(await api('POST','/axx-api/chat/create',{title:'Aceptación · fuente de voz'})).id;
  await api('POST','/axx-api/chat/save',{id:source,messages:[{id:'voice-context-'+Date.now(),at:Date.now(),role:'user',status:'complete',text:'El color acordado para nuestro proyecto es jade. No hay otro color seleccionado.'}]});
  destination=(await api('POST','/axx-api/chat/create',{title:'Aceptación · conversación de voz'})).id;
  await api('POST','/axx-api/chat/link',{id:destination,source_id:source});await p.evaluate(id=>Axx.chatWorkspace.select(id),destination);
  let audio;const deadline=Date.now()+90000;receipt.input_prepare_retries=0;
  while(!audio){try{audio=await api('POST','/axx-api/speech/synthesize',{text:'¿Cuál es el color del proyecto? Responde en una frase.',voice:'moss:axx-valeria',language:'es',rate:0,volume:100});}catch(e){if(!/BUSY/.test(String(e))||Date.now()>=deadline)throw e;receipt.input_prepare_retries++;await p.waitForTimeout(1000);}}
  assert(audio.audio_base64);
  // Exercise the actual file UI with the complete generated input, without
  // changing the microphone provenance of the later conversational test.
  await p.evaluate(()=>{const s=Axx.symbiosis,player=document.getElementById('transcript-player');window.__axxPriorTranscript={file:s.mediaFile,cues:s.cues,source:s.transcriptSource,name:s.mediaName,cue:s.mediaCue,time:player.currentTime,hidden:player.hidden,paused:player.paused,muted:player.muted,rate:player.playbackRate,label:document.getElementById('media-file-label').textContent,status:document.getElementById('transcript-file-status').textContent};Axx.companion.openFeature('transcript');});
  await p.locator('#transcript-media').setInputFiles({name:'axx-acceptance-voice.wav',mimeType:'audio/wav',buffer:Buffer.from(audio.audio_base64,'base64')});
  await p.locator('#transcript-transcribe-file').click();
  await p.waitForFunction(()=>/Transcripción completa/.test(document.getElementById('transcript-file-status').textContent),{},{timeout:120000});
  assert(await p.evaluate(()=>Axx.symbiosis.cues.some(c=>c.text.trim())));
  receipt.checks.push('Installed file-transcription control processed the complete generated WAV through local Whisper');
  await restoreTranscript();
  const began=Date.now();
  const transcript=await api('POST','/axx-api/speech/transcribe',{audio_base64:audio.audio_base64,mime:audio.mime,language:'es',task:'transcribe'});
  assert(transcript.text?.trim());receipt.transcript=transcript.text;receipt.asr_ms=Date.now()-began;receipt.checks.push('Real local synthesis generated the input; packaged Whisper transcribed it');
  await p.evaluate(()=>{Axx.companion.data.prefs.mutedAll=false;Axx.symbiosis.reader.voiceURI='moss:axx-valeria';Axx.resident.summon(false);Axx.companion.openChat();Axx.liveConversation.show();});
  await p.locator('#chat-input').fill('Pregunta: ');
  const messageCount=await p.evaluate(()=>Axx.companion.data.messages.length);
  await p.locator('#chat-mic').click();
  await p.waitForFunction(()=>Axx.nativeVoice.chatDraft.state==='listening');
  await p.evaluate(async input=>{
   const session=Axx.nativeVoice.sessions.find(item=>item.owner===Axx.nativeVoice.chatDraft);
   // Release the physical stream and feed a declared synthetic clip to the
   // installed capture adapter. This is ASR integration, not human speech proof.
   session.stop();
   const bytes=Uint8Array.from(atob(input.audio_base64),ch=>ch.charCodeAt(0));
   await session.submit(new Blob([bytes],{type:input.mime}));
  },audio);
  assert.match(await p.locator('#chat-input').inputValue(),/^Pregunta: .+\s$/);
  assert.equal(await p.evaluate(()=>Axx.companion.data.messages.length),messageCount);
  assert.equal(await p.evaluate(()=>document.getElementById('panel').dataset.view),'chat');
  receipt.checks.push('Installed draft microphone transcribed the synthetic clip into the draft without sending or opening another panel');
  await p.locator('#chat-input').fill('');
  const entry=await p.locator('#chat-live-toggle').boundingBox(),composer=await p.locator('#chat-form').boundingBox();
  assert(entry&&composer&&entry.y>=composer.y&&entry.y+entry.height<=composer.y+composer.height+1);assert(entry.height>=40);
  assert.equal(await p.locator('#chat-live-toggle svg').count(),1);
  await p.locator('#chat-live-toggle').click();
  await p.waitForFunction(()=>['listening','error'].includes(Axx.symbiosis.dictation.state),{},{timeout:120000});
  const capture=await p.evaluate(()=>({state:Axx.symbiosis.dictation.state,tracks:Axx.nativeVoice.activeCapture?.stream?.getAudioTracks().filter(t=>t.readyState==='live').length||0}));
  receipt.microphone=capture;assert.equal(capture.state,'listening');assert(capture.tracks>0);
  receipt.checks.push('One click on the composer voice button acquired a real local microphone track');
  assert.equal(await p.locator('#chat-live-toggle').innerText(),'Voz activa');assert.equal(await p.locator('#chat-live-toggle svg').count(),1);
  assert.equal(await p.locator('#chat-live-toggle').getAttribute('aria-label'),'Terminar conversación por voz');
  await p.locator('#chat-live-toggle').click();
  await p.evaluate(async input=>{
   const bytes=Uint8Array.from(atob(input.audio_base64),ch=>ch.charCodeAt(0));
   const decode=new AudioContext(),buffer=await decode.decodeAudioData(bytes.buffer);await decode.close();
   const fixture=window.__axxLiveMediaFixture={original:navigator.mediaDevices.getUserMedia,contexts:[],deliveries:0,gain:.1,duration:buffer.duration};
   navigator.mediaDevices.getUserMedia=async()=>{
    const context=new AudioContext();fixture.contexts.push(context);await context.resume();
    const destination=context.createMediaStreamDestination();
    if(fixture.deliveries++===0){const source=context.createBufferSource(),gain=context.createGain();source.buffer=buffer;gain.gain.value=fixture.gain;source.connect(gain);gain.connect(destination);fixture.source=source;fixture.sourceContext=context;}
    else{const silence=context.createConstantSource();silence.offset.value=0;silence.connect(destination);silence.start();}
    return destination.stream;
   };
   Axx.nativeVoice.playback=null;
  },audio);
  await p.locator('#chat-live-toggle').click();
  await p.waitForFunction(()=>Axx.symbiosis.dictation.state==='listening',{},{timeout:30000});
  const vad=await p.evaluate(()=>{const fixture=window.__axxLiveMediaFixture;fixture.source.start(fixture.sourceContext.currentTime+.1);return{duration:fixture.duration,pause_ms:Axx.liveConversation.pauseMs};});
  const vadBegan=Date.now(),vadDeadline=Math.ceil(vad.duration*1000+vad.pause_ms+5000);
  assert(vadDeadline<30000,'Synthetic phrase must finish before either recording timeout');
  await p.waitForFunction(()=>Axx.symbiosis.dictation.state!=='listening',null,{timeout:vadDeadline});
  receipt.vad={...vad,recording_finished_ms:Date.now()-vadBegan,deadline_ms:vadDeadline};
  await p.waitForFunction(()=>!Axx.symbiosis.liveBusy&&(Axx.nativeVoice.playback?.ended_event||!Axx.symbiosis.liveActive),{},{timeout:180000});
  await p.waitForFunction(()=>!Axx.symbiosis.liveActive||['listening','error'].includes(Axx.symbiosis.dictation.state),{},{timeout:30000});
  receipt.turn=await p.evaluate(()=>({active:Axx.symbiosis.liveActive,state:Axx.symbiosis.dictation.state,playback:Axx.nativeVoice.playback,first_audio_ms:Axx.liveConversation.firstAudioMs,response:Axx.companion.data.messages.at(-1)?.text,model:Axx.companion.data.prefs.model,provider:Axx.companion.data.prefs.provider}));
  await p.locator('#panel').screenshot({path:'build/chat-0.21.4/installed-live.png'});
  assert(receipt.turn.active);assert.equal(receipt.turn.state,'listening');assert.match(receipt.turn.response,/jade/i);assert.equal(receipt.turn.playback.underruns,0);
  receipt.mediaRecorder={synthetic_gain:.1,manual_finish:false,callbacks_injected:false};
  receipt.checks.push('Real MediaRecorder encoded quiet synthetic audio; VAD ended the phrase, Whisper transcribed it, selected model used linked context, TTS spoke once and listening resumed');
  await p.evaluate(text=>{const s=Axx.symbiosis;s.dictation.stop();s.dictation.onFinal(text);s.dictation.onEnded();},transcript.text);
  await p.waitForFunction(()=>Axx.symbiosis.liveActive&&Axx.symbiosis.reader.state==='speaking',{},{timeout:180000});
  const interruption=Date.now();await p.locator('#chat-live-interrupt').click();
  await p.waitForFunction(()=>Axx.symbiosis.liveActive&&Axx.symbiosis.dictation.state==='listening'&&!Axx.symbiosis.liveBusy,{},{timeout:60000});
  receipt.interrupt_to_listening_ms=Date.now()-interruption;receipt.checks.push('Interrupt stopped a second spoken reply and reacquired the microphone');
  await p.locator('#chat-live-toggle').click();
  const stopped=await p.evaluate(()=>({active:Axx.liveConversation.active,tracks:Axx.nativeVoice.activeCapture?.stream?.getAudioTracks().filter(t=>t.readyState==='live').length||0}));assert.equal(stopped.active,false);assert.equal(stopped.tracks,0);
  assert.equal(await p.locator('#chat-live-toggle').innerText(),'Voz en vivo');
  receipt.checks.push('A second click on the composer voice button released the microphone');receipt.result='PASS';
 }catch(e){receipt.result='FAIL';receipt.error=e.stack;receipt.failureState=await p.evaluate(()=>({active:Axx.symbiosis.liveActive,busy:Axx.symbiosis.liveBusy,dictation:Axx.symbiosis.dictation.state,reader:Axx.symbiosis.reader.state,status:document.getElementById('chat-live-status').textContent,visibility:document.visibilityState,input:Axx.nativeVoice.inputLevel?{rms:Axx.nativeVoice.inputLevel.rms,phase:Axx.nativeVoice.inputLevel.phase,at:Axx.nativeVoice.inputLevel.at}:null,playback:Axx.nativeVoice.playback,fixture:window.__axxLiveMediaFixture?{deliveries:window.__axxLiveMediaFixture.deliveries,contexts:window.__axxLiveMediaFixture.contexts.map(c=>({state:c.state,time:c.currentTime}))}:null})).catch(()=>null);throw e;}
 finally{
  await p.evaluate(async()=>{const fixture=window.__axxLiveMediaFixture;if(!fixture)return;Axx.liveConversation.stop();navigator.mediaDevices.getUserMedia=fixture.original;await Promise.all(fixture.contexts.map(context=>context.close().catch(()=>{})));delete window.__axxLiveMediaFixture;});
  await restoreTranscript();
  if(prior){await p.evaluate(()=>Axx.liveConversation.stop());await p.evaluate(async old=>{Axx.symbiosis.reader.voiceURI=old.voice;Axx.companion.data.prefs.mutedAll=old.muted;if(old.voicePref===null)localStorage.removeItem('axx.voice.uri');else localStorage.setItem('axx.voice.uri',old.voicePref);await Axx.chatWorkspace.select(old.id);document.getElementById('chat-live-close').click();},prior);for(const id of [destination,source].filter(Boolean))await api('POST','/axx-api/chat/delete',{id});}
  fs.writeFileSync('build/chat-0.21.4/installed-live.json',JSON.stringify(receipt,null,2));await b.close();console.log(JSON.stringify(receipt,null,2));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
