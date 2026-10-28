/** Full native UI with synthetic microphone; no physical recording. */
const fs=require('node:fs'), path=require('node:path'), http=require('node:http'), assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
  const server=http.createServer((req,res)=>{
    const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,'../Axx.html');
    res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  let browser;
  try{
    browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
    const page=await browser.newPage({viewport:{width:1300,height:1000},reducedMotion:'reduce'}),errors=[];
    page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      window.requests=[];window.micRequests=0;window.transcribed=false;window.fixtureInput='silence';window.failVadResume=false;window.failDevice=false;window.holdCancel=false;
      const AudioBase=window.AudioContext;window.AudioContext=class extends AudioBase{resume(){return failVadResume?Promise.reject(Error('fixture resume rejected')):super.resume();}};
      window.traceVad=false;window.vadTrace=[];const getFloats=AnalyserNode.prototype.getFloatTimeDomainData;AnalyserNode.prototype.getFloatTimeDomainData=function(buffer){getFloats.call(this,buffer);if(traceVad&&fixtureInput==='startup-noise')buffer.fill(vadTrace.length?.014:.0043);if(traceVad)vadTrace.push({at:performance.now(),rms:Math.sqrt(buffer.reduce((sum,n)=>sum+n*n,0)/buffer.length),noise:Axx.nativeVoice.inputLevel?.noise_floor,phase:Axx.nativeVoice.inputLevel?.phase,context:this.context.state,sourceContext:fixtureContext.state});};
      navigator.mediaDevices.getUserMedia=async constraints=>{
        window.micRequests++;
        window.lastMicConstraints=constraints;
        if(failDevice)throw new DOMException('Fixture unavailable','NotFoundError');
        const ctx=new AudioContext();window.fixtureContext=ctx;
        const dest=ctx.createMediaStreamDestination();window.fixtureTracks=dest.stream.getAudioTracks();
        for(const track of fixtureTracks){const stop=track.stop.bind(track);track.stop=()=>{stop();if(ctx.state!=='closed')void ctx.close().catch(()=>{});};}
        if(fixtureInput!=='silence'){const oscillator=ctx.createOscillator(),gain=ctx.createGain();window.fixtureGain=gain;oscillator.frequency.value=180;oscillator.connect(gain);gain.connect(dest);gain.gain.value=fixtureInput==='noise'?.02:0;if(fixtureInput==='quiet-voice'){gain.gain.setValueAtTime(.012,ctx.currentTime+.7);gain.gain.setValueAtTime(0,ctx.currentTime+1.7);}oscillator.start();await ctx.resume();}
        return dest.stream;
      };
      window.MediaRecorder=class{
        static isTypeSupported(){return true;}
        state='inactive';
        constructor(stream){this.stream=stream;}
        start(){this.state='recording';queueMicrotask(()=>this.onstart?.());}
        stop(){this.state='inactive';queueMicrotask(()=>{this.ondataavailable?.({data:new Blob(['fixture audio'],{type:'audio/webm'})});this.onstop?.();});}
      };
      window.__TAURI__={core:{invoke:async(name,args)=>{
        const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
        if(name==='native_status')return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
        if(name==='desktop_layout')return {...desktop,...args};
        if(name==='backend_request'){
          requests.push(args.path);
          if(args.path==='/axx-api/speech/transcribe') {await new Promise(r=>window.releaseTranscript=r);return {text:'Hola desde el dictado'};}
          if(args.path==='/axx-api/speech/cancel'&&holdCancel){await new Promise(resolve=>window.releaseCancel=resolve);return {};}
          if(args.path==='/axx-api/speech/voices') {if(window.failVoiceList)throw Error('fixture voice list failed');return {available:true,voices:window.fixtureVoices||[]};}
          if(args.path==='/axx-api/speech/prepare') {if(window.failVoicePrepare)throw Error('fixture prepare failed');if(window.holdVoicePrepare)await new Promise(resolve=>window.releaseVoicePrepare=resolve);return {prepared_voices:[args.body.voice]};}
          if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};
          if(args.path.includes('/commands/resolve'))return {match:'none'};
          return {};
        }return null;
      }},event:{listen:async()=>()=>{}}};
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>Axx?.nativeVoice && Axx?.resident?.firstFrame);
    const voiceDefaults=await page.evaluate(async()=>{
      const state=Axx.nativeVoice,prepare=state.prepareVoice,results=[];state.prepareVoice=()=>{};
      const refresh=async saved=>{
        if(saved===null)localStorage.removeItem('axx.voice.uri');else localStorage.setItem('axx.voice.uri',saved);
        Axx.symbiosis.reader.voiceURI='';Axx.voice13.reader.voiceURI='';await state.refreshVoices(true);
        results.push(Axx.symbiosis.reader.voiceURI);
      };
      fixtureVoices=[{name:'axx-valeria',enabled:true},{name:'axx-sam',enabled:true}].map(v=>({...v,name:'moss:'+v.name,engine:'moss-onnx'}));
      await refresh(null);await refresh('moss:axx-valeria');await refresh('');
      fixtureVoices=fixtureVoices.slice(0,1);await refresh(null);
      fixtureVoices=[];await refresh('');localStorage.removeItem('axx.voice.uri');state.prepareVoice=prepare;
      return results;
    });
    assert.deepEqual(voiceDefaults.slice(0,4),['moss:axx-sam','moss:axx-valeria','','moss:axx-valeria'],
      'The private default must fall back when absent and respect explicit Windows/other voice choices');
    await page.evaluate(async()=>{
      fixtureVoices=[{name:'moss:axx-sam',label:'Xxx default',engine:'moss-onnx'}, {name:'moss:axx-valeria',label:'Axx Valeria',engine:'moss-onnx'}];
      localStorage.setItem('axx.voice.uri','moss:axx-sam');
      Axx.symbiosis.reader.voiceURI=Axx.voice13.reader.voiceURI='moss:axx-valeria';
      await Axx.nativeVoice.refreshVoices(true);
      window.savedVoiceRead=Axx.companion.read;Axx.companion.read=()=>{};
      Axx.companion.openChat();document.getElementById('chat20-menu').open=true;
    });
    assert.equal(await page.evaluate(()=>Axx.voice13.reader.voiceURI),'moss:axx-sam','Persisted selection must replace a stale legacy reader setting');
    assert.equal(await page.locator('#chat-live-voice').inputValue(),'moss:axx-sam');
    await page.waitForFunction(()=>document.getElementById('chat-voice-status').dataset.phase==='ready');
    await page.evaluate(()=>{const select=document.getElementById('chat-live-voice');select.value='moss:axx-valeria';select.dispatchEvent(new Event('change'));});
    assert.equal(await page.locator('#chat-voice-select').inputValue(),'moss:axx-valeria','Live voice must share the same selection owner');
    await page.locator('#chat-voice-select').selectOption('moss:axx-valeria');
    await page.evaluate(()=>window.holdVoicePrepare=true);
    await page.locator('#chat-voice-default').click();
    await page.waitForFunction(()=>typeof releaseVoicePrepare==='function');
    assert.equal(await page.locator('#chat-voice-status').getAttribute('data-phase'),'loading');
    assert.deepEqual(await page.evaluate(()=>[localStorage.getItem('axx.voice.uri'),Axx.symbiosis.reader.voiceURI,Axx.voice13.reader.voiceURI,document.getElementById('chat-live-voice').value]),Array(4).fill('moss:axx-sam'));
    await page.evaluate(()=>{holdVoicePrepare=false;releaseVoicePrepare();});
    await page.waitForFunction(()=>document.getElementById('chat-voice-status').dataset.phase==='ready');
    await page.evaluate(async()=>{fixtureVoices.push({name:'piper:es_ES-carlfm-x_low',label:'Piper · España · CarlFM · ligera',language:'es-ES',engine:'piper-onnx'});await Axx.nativeVoice.refreshVoices(true);});
    const voiceEvidence=path.resolve(__dirname,'../../build/voice-ui-'+require('../../package.json').version);fs.mkdirSync(voiceEvidence,{recursive:true});
    await page.locator('#chat-voice-settings').click();
    assert.equal(await page.locator('#view-voices').isVisible(),true,'The dedicated voice panel must open from chat');
    await page.locator('#voice-panel-select').selectOption('piper:es_ES-carlfm-x_low');
    await page.waitForFunction(()=>document.getElementById('voice-panel-status').dataset.phase==='ready');
    assert.deepEqual(await page.evaluate(()=>[localStorage.getItem('axx.voice.uri'),Axx.symbiosis.reader.voiceURI,Axx.voice13.reader.voiceURI,document.getElementById('chat-live-voice').value,document.getElementById('chat-voice-select').value]),Array(5).fill('piper:es_ES-carlfm-x_low'));
    assert.equal(await page.locator('[data-voice-choice="piper:es_ES-carlfm-x_low"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('[data-voice-choice="piper:es_MX-ald-medium"]').isDisabled(),true,'Missing Piper voice must not be selectable');
    await page.locator('#view-voices').screenshot({path:path.join(voiceEvidence,'voices-panel.png')});
    await page.locator('#view-voices').evaluate(element=>element.scrollTop=element.scrollHeight);
    await page.locator('#view-voices').screenshot({path:path.join(voiceEvidence,'voices-panel-bottom.png')});
    await page.locator('[data-voice-choice="moss:axx-sam"]').click();
    await page.waitForFunction(()=>document.getElementById('voice-panel-status').dataset.phase==='ready');
    assert.equal(await page.locator('#voice-panel-select').inputValue(),'moss:axx-sam','Voice cards must use the shared selector');
    await page.evaluate(()=>{Axx.companion.openChat();document.getElementById('chat20-menu').open=true;});
    await page.locator('.chat20-voice-card').first().screenshot({path:path.join(voiceEvidence,'settings.png')});
    await page.evaluate(async()=>{fixtureVoices=fixtureVoices.filter(v=>v.name==='moss:axx-valeria');await Axx.nativeVoice.refreshVoices(true);});
    assert.equal(await page.locator('#chat-voice-default').isDisabled(),true);
    assert.equal(await page.locator('#chat-voice-select').inputValue(),'moss:axx-sam','Missing selected voice must not silently appear as Windows');
    assert.equal(await page.locator('#chat-voice-status').getAttribute('data-phase'),'error');
    await page.evaluate(async()=>{failVoiceList=true;await Axx.nativeVoice.refreshVoices(true).catch(()=>{});});
    assert.match(await page.locator('#chat-voice-status').textContent(),/No se pudo consultar/);
    await page.evaluate(async()=>{failVoiceList=false;failVoicePrepare=true;fixtureVoices=[{name:'moss:axx-sam',label:'Xxx default',engine:'moss-onnx'}];await Axx.nativeVoice.refreshVoices(true);});
    await page.waitForFunction(()=>document.getElementById('chat-voice-status').textContent.includes('No se pudo preparar'));
    await page.evaluate(async()=>{
      failVoicePrepare=false;fixtureVoices=[];localStorage.setItem('axx.voice.uri','');await Axx.nativeVoice.refreshVoices(true);
      Axx.companion.read=savedVoiceRead;localStorage.removeItem('axx.voice.uri');document.getElementById('chat20-menu').open=false;
    });
    await page.evaluate(()=>{Axx.resident.summon(false);Axx.flow.select('dictation');});
    await page.waitForFunction(()=>document.getElementById('v13-dock').getBoundingClientRect().width>0);
    const layout=await page.evaluate(async()=>{
      await Axx.resident.layout();
      const el=document.getElementById('v13-dock'),before=el.getBoundingClientRect().toJSON();
      Axx.voice13.layout();
      return {before,after:el.getBoundingClientRect().toJSON()};
    });
    for(const key of ['x','y','width','height'])assert.ok(Math.abs(layout.before[key]-layout.after[key])<1,`Dictation layout has competing ${key}: ${JSON.stringify(layout)}`);
    await page.evaluate(()=>Axx.resident.tap());
    assert.equal(await page.evaluate(()=>Axx.flow.nav.step),2,'Avatar click opens all options without starting capture');
    assert.equal(await page.evaluate(()=>micRequests),0);
    await page.evaluate(()=>{Axx.flow.select('dictation');Axx.voice13.openFields();Axx.voice13.consent=true;Axx.voice13.permit=false;});
    const overlap=await page.evaluate(async()=>{
      await Axx.resident.layout();
      const a=document.getElementById('v13-dock').getBoundingClientRect(),b=document.getElementById('v13-pad').getBoundingClientRect();
      return Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
    });
    assert.equal(overlap,0,'Dictation controls must not sit behind the destination panel');
    await page.evaluate(()=>Axx.voice13.begin());
    try {await page.waitForFunction(()=>Axx.voice13.status==='listening');}
    catch(e){console.log(await page.evaluate(()=>({status:Axx.voice13.status,error:Axx.voice13.error,notice:Axx.voice13.notice,target:Axx.voice13.target?.name,capture:Axx.voice13.capture.state,mics:micRequests})));throw e;}
    assert.equal(await page.evaluate(()=>micRequests),1,'Meter and recorder must share the same capture');
    await page.evaluate(()=>Axx.voice13.pause(true));
    await page.waitForFunction(()=>typeof releaseTranscript==='function');
    assert.equal(await page.evaluate(()=>Axx.voice13.status),'stopping');
    await page.evaluate(()=>releaseTranscript());
    await page.waitForFunction(()=>document.getElementById('v13-note').value.includes('Hola desde el dictado'));
    assert.equal(await page.evaluate(()=>Axx.voice13.status),'paused');
    assert.equal(await page.evaluate(()=>Axx.voice13.meter.active),false);
    assert.equal(await page.evaluate(()=>Axx.companion.data.messages.length),0,'Dictation must not send text');
    assert.equal(await page.evaluate(()=>requests.includes('/axx-api/actions/cancel')),false);
    const states=await page.evaluate(async()=>{
      const values=[],owner={state:'idle',onState(){values.push(this.state);}};
      Axx.nativeVoice.attach(owner);const session=Axx.nativeVoice.sessions.at(-1);
      await session.start('es');await new Promise(resolve=>setTimeout(resolve,20));
      const started=[...values];session.stop();return {started,stopped:values.at(-1)};
    });
    assert.deepEqual(states.started,['starting','listening'],'Start must not emit an idle callback that cancels the initiating mode');
    assert.equal(states.stopped,'idle');
    await page.evaluate(()=>{
      Axx.companion.openChat();Axx.companion.data.prefs.voiceAutoSend=true;
      const input=document.getElementById('chat-input');input.value='Mi borrador';input.setSelectionRange(input.value.length,input.value.length);
      window.releaseTranscript=null;
    });
    await page.locator('#chat-mic').click();
    await page.waitForFunction(()=>Axx.nativeVoice.chatDraft.state==='listening');
    assert.equal(await page.evaluate(()=>document.getElementById('panel').dataset.view),'chat','Dictation stays in chat');
    assert.equal(await page.locator('#chat-mic').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#chat20-wake-toggle').getAttribute('aria-pressed'),'false','Draft dictation is not a command');
    await page.locator('#chat-mic').click();
    await page.waitForFunction(()=>typeof releaseTranscript==='function');
    assert.equal(await page.evaluate(()=>Axx.nativeVoice.chatDraft.state),'stopping');
    await page.evaluate(()=>releaseTranscript());
    await page.waitForFunction(()=>Axx.nativeVoice.chatDraft.state==='idle');
    assert.equal(await page.locator('#chat-input').inputValue(),'Mi borrador Hola desde el dictado ');
    assert.equal(await page.evaluate(()=>Axx.companion.data.messages.length),0,'Chat dictation never auto-sends, even with the legacy preference enabled');
    assert.equal(await page.locator('#chat-mic').getAttribute('aria-pressed'),'false');
    // An edit while recognition is pending cancels that capture; a late result
    // cannot replace the new draft or create a message.
    await page.evaluate(()=>{window.releaseTranscript=null;Axx.companion.startDictation();});
    await page.waitForFunction(()=>Axx.nativeVoice.chatDraft.state==='listening');
    await page.locator('#chat-mic').click();
    await page.waitForFunction(()=>typeof releaseTranscript==='function');
    await page.locator('#chat-input').fill('Edición manual');
    await page.evaluate(()=>releaseTranscript());
    await page.waitForTimeout(50);
    assert.equal(await page.locator('#chat-input').inputValue(),'Edición manual');
    assert.equal(await page.evaluate(()=>Axx.nativeVoice.chatDraft.state),'idle');
    assert.equal(await page.evaluate(()=>Axx.companion.data.messages.length),0);
    await page.evaluate(()=>{
      Axx.chatWorkspace={ready:true,active:{id:'controlled-live'}};
      Axx.companion.brain.connected=true;Axx.companion.data.prefs.mutedAll=false;
    });
    const liveButton=await page.locator('#chat-live-toggle').boundingBox(),composer=await page.locator('#chat-form').boundingBox();
    assert(liveButton.height>=40&&liveButton.y>=composer.y&&liveButton.y+liveButton.height<=composer.y+composer.height+1);
    assert.equal(await page.locator('#chat-live-toggle').evaluate(el=>getComputedStyle(el).borderRadius),'999px');
    await page.locator('#chat-live-toggle').click();
    await page.waitForFunction(()=>Axx.liveConversation.active&&Axx.symbiosis.dictation.state==='listening');
    assert.equal(await page.locator('#chat-live-toggle').innerText(),'Voz activa');
    assert.equal(await page.locator('#chat-live-toggle svg').count(),1);
    assert.equal(await page.locator('#chat-mic').getAttribute('aria-pressed'),'false','Live input must not mark draft dictation as recording');
    assert.equal(await page.locator('#chat20-wake-toggle').getAttribute('aria-pressed'),'false','Live input must not mark command voice as recording');
    await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
    assert.equal(await page.evaluate(()=>Axx.liveConversation.active),true,'Explicit live conversation survives focus loss while still visible');
    assert.equal(await page.evaluate(()=>Axx.symbiosis.dictation.state),'listening');
    await page.locator('#chat-live-toggle').click();
    assert.equal(await page.evaluate(()=>Axx.liveConversation.active),false);
    assert.equal(await page.evaluate(()=>Axx.nativeVoice.activeCapture?.stream||null),null);
    assert.equal(await page.locator('#chat-live-toggle').innerText(),'Voz en vivo');
    const failedReply=await page.evaluate(async()=>{
      const sym=Axx.symbiosis, companion=Axx.companion;
      const previousSend=companion.send, previousListen=sym.startListening;
      let restarted=0;
      companion.send=async()=>{companion.data.messages.push({id:'controlled-voice-error',role:'assistant',status:'error',source:'model',text:'Modelo no disponible'});};
      sym.startListening=()=>{restarted++;};
      sym.liveActive=true;sym.liveText='hola';
      try {await sym.sendLive();return {active:sym.liveActive,restarted};}
      finally {sym.liveActive=false;companion.data.messages.pop();companion.send=previousSend;sym.startListening=previousListen;}
    });
    assert.deepEqual(failedReply,{active:true,restarted:1},'A model error must keep live voice ready for the next utterance');
    await page.evaluate(()=>{fixtureInput='quiet-voice';window.oldLiveFinal=Axx.symbiosis.dictation.onFinal;window.oldLiveEnded=Axx.symbiosis.dictation.onEnded;Axx.symbiosis.dictation.onFinal=()=>{};Axx.symbiosis.dictation.onEnded=()=>{Axx.symbiosis.liveActive=false;};window.releaseTranscript=null;});
    await page.locator('#chat-live-toggle').click();await page.waitForFunction(()=>typeof releaseTranscript==='function',null,{timeout:7000});
    assert.equal(await page.evaluate(()=>Axx.symbiosis.dictation.state),'stopping','Quiet RMS below the old .024 threshold must finish after a pause');
    await page.evaluate(()=>releaseTranscript());await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='idle');
    await page.evaluate(()=>{fixtureInput='short';releaseTranscript=null;});await page.locator('#chat-live-toggle').click();await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='listening');
    await page.evaluate(()=>{fixtureGain.gain.setValueAtTime(.012,fixtureContext.currentTime+.05);fixtureGain.gain.setValueAtTime(0,fixtureContext.currentTime+.27);});
    await page.waitForFunction(()=>typeof releaseTranscript==='function',null,{timeout:5000});await page.evaluate(()=>releaseTranscript());await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='idle');
    const noiseTraces=[];
    for(let trial=0;trial<5;trial++){
      await page.evaluate(n=>{fixtureInput=n===0?'startup-noise':'noise';traceVad=true;vadTrace=[];},trial);await page.locator('#chat-live-toggle').click();await page.waitForTimeout(2000);
      noiseTraces.push(await page.evaluate(()=>vadTrace));assert.equal(await page.evaluate(()=>Axx.symbiosis.dictation.state),'listening');assert.equal(await page.evaluate(()=>Axx.nativeVoice.inputLevel.heard_speech),false,'Steady background noise must not count as voice: '+JSON.stringify(noiseTraces.at(-1)));await page.evaluate(()=>traceVad=false);
      const signal=await page.waitForFunction(()=>document.getElementById('chat-live-level').value||false);assert(await signal.jsonValue()>0,'Meter must reveal that the selected input carries a signal');await page.locator('#chat-live-toggle').click();
    }
    const tracesPath=path.resolve(__dirname,'../../build/chat-'+require('../../package.json').version+'/vad-noise-traces.json');fs.mkdirSync(path.dirname(tracesPath),{recursive:true});fs.writeFileSync(tracesPath,JSON.stringify(noiseTraces,null,2));
    await page.evaluate(()=>{fixtureInput='silence';});await page.locator('#chat-live-toggle').click();await page.waitForFunction(()=>Axx.nativeVoice.inputLevel?.phase==='calibrating');
    await page.evaluate(()=>{const end=performance.now()+600;while(performance.now()<end){};});await page.waitForTimeout(40);assert.equal(await page.evaluate(()=>Axx.symbiosis.dictation.state),'starting','UI stalls must not finish calibration with fewer than six samples');await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='listening');await page.locator('#chat-live-toggle').click();
    await page.evaluate(()=>{fixtureInput='silence';Axx.nativeVoice.liveDeviceId='missing-microphone';failDevice=true;});await page.locator('#chat-live-toggle').click();await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='error');
    assert.equal(await page.evaluate(()=>lastMicConstraints.audio.deviceId.exact),'missing-microphone');assert.match(await page.locator('#chat-live-status').innerText(),/micrófono seleccionado no está disponible/);assert.equal(await page.evaluate(()=>Axx.nativeVoice.activeCapture),null);
    await page.evaluate(()=>{failDevice=false;Axx.nativeVoice.liveDeviceId='';failVadResume=true;});await page.locator('#chat-live-toggle').click();await page.waitForFunction(()=>Axx.symbiosis.dictation.state==='error');assert.equal(await page.evaluate(()=>fixtureTracks.every(t=>t.readyState==='ended')),true);assert.match(await page.locator('#chat-live-status').innerText(),/resume rejected/);
    await page.evaluate(()=>{failVadResume=false;Axx.symbiosis.dictation.onFinal=oldLiveFinal;Axx.symbiosis.dictation.onEnded=oldLiveEnded;});
    const barrier=await page.evaluate(async()=>{
      const owner={state:'idle'},canceller={state:'idle'};Axx.nativeVoice.attach(owner);const local=Axx.nativeVoice.sessions.at(-1);Axx.nativeVoice.attach(canceller);const old=Axx.nativeVoice.sessions.at(-1);
      holdCancel=true;releaseCancel=null;old.pending=true;old.stop();await new Promise(resolve=>setTimeout(resolve,0));const beforeMic=micRequests,starting=local.start('es');await new Promise(resolve=>setTimeout(resolve,80));const micWaited=micRequests===beforeMic;releaseCancel();await starting;await new Promise(resolve=>setTimeout(resolve,0));
      releaseCancel=null;old.pending=true;old.stop();await new Promise(resolve=>setTimeout(resolve,0));const beforeSubmit=requests.filter(p=>p==='/axx-api/speech/transcribe').length;releaseTranscript=null;const submitted=local.submit(new Blob(['fixture'],{type:'audio/webm'}));await new Promise(resolve=>setTimeout(resolve,80));const submitWaited=requests.filter(p=>p==='/axx-api/speech/transcribe').length===beforeSubmit;releaseCancel();
      for(let i=0;i<100&&typeof releaseTranscript!=='function';i++)await new Promise(resolve=>setTimeout(resolve,10));releaseTranscript();await submitted;local.stop();old.stop();holdCancel=false;return{micWaited,submitWaited};
    });assert.deepEqual(barrier,{micWaited:true,submitWaited:true});
    await page.keyboard.press('Alt+Shift+KeyV');
    await page.waitForFunction(()=>Axx.nativeVoice.wake.active&&Axx.symbiosis.dictation.state==='listening');
    assert.equal(await page.locator('#chat20-wake-toggle').getAttribute('aria-pressed'),'true','Shortcut must toggle once, not start and immediately stop');
    assert.equal(await page.locator('#chat-mic').getAttribute('aria-pressed'),'false');
    await page.keyboard.press('Alt+Shift+KeyV');
    assert.equal(await page.evaluate(()=>Axx.nativeVoice.wake.active),false);
    assert.equal(await page.evaluate(()=>Axx.symbiosis.dictation.state),'idle');
    const rearm=await page.evaluate(async()=>{
      const wake=Axx.nativeVoice.wake, companion=Axx.companion;
      wake.setMode('always_active');
      wake.stop(false);
      companion.pending={};
      wake.scheduleRearm(20);
      await new Promise(resolve=>setTimeout(resolve,120));
      const waitedForAnswer=!wake.active;
      companion.pending=null;
      const reader=Axx.symbiosis.reader, previousReaderState=reader.state;
      reader.state='speaking';
      await new Promise(resolve=>setTimeout(resolve,650));
      const waitedForSpeech=!wake.active;
      reader.state=previousReaderState;
      await new Promise(resolve=>setTimeout(resolve,650));
      const resumedAfterAnswer=wake.active;
      wake.stop();
      wake.scheduleRearm(20);
      await new Promise(resolve=>setTimeout(resolve,120));
      const stayedStopped=!wake.active;
      wake.setMode('hotkey');
      return {waitedForAnswer,waitedForSpeech,resumedAfterAnswer,stayedStopped};
    });
    assert.deepEqual(rearm,{waitedForAnswer:true,waitedForSpeech:true,resumedAfterAnswer:true,stayedStopped:true},'Always active must wait for the reply and speech and respect Stop');
    await page.evaluate(()=>localStorage.setItem('axx.activation.mode','always_active'));
    await page.reload();
    await page.waitForFunction(()=>Axx.nativeVoice?.wake?.active&&Axx.symbiosis?.dictation?.state==='listening');
    await page.evaluate(()=>Axx.nativeVoice.wake.setMode('hotkey'));
    // The real avatar, capture adapter and chat pipeline run inside the full UI.
    await page.evaluate(()=>{
      Axx.chatWorkspace={ready:true,active:{id:'quick-voice-fixture'}};
      const c=Axx.companion;c.send=Object.getPrototypeOf(c).send.bind(c);c.brain.connected=true;c.brain.models=['ui-contract'];c.brain.chat=async()=>({text:'Respuesta breve de la prueba',reason:'stop'});
      Object.assign(c.data.prefs,{provider:'chatgpt',model:'ui-contract',selection_mode:'manual',mutedAll:true});
      fixtureInput='quiet-voice';Axx.resident.fold();Axx.quickReply.talk();
    });
    await page.waitForFunction(()=>Axx.quickReply.capture.state==='listening');
    assert.equal(await page.evaluate(()=>Axx.companion.dictating),true);
    await page.waitForFunction(()=>typeof releaseTranscript==='function');await page.evaluate(()=>releaseTranscript());
    await page.waitForFunction(()=>document.getElementById('quick-reply-text').textContent==='Respuesta breve de la prueba');
    assert.equal(await page.evaluate(()=>document.getElementById('panel').hidden),true);
    assert.equal(await page.evaluate(()=>Axx.quickReply.capture.state),'idle');
    assert.equal(await page.evaluate(()=>fixtureTracks.every(t=>t.readyState==='ended')),true);
    await page.waitForFunction(()=>!document.getElementById('quick-compose').getAnimations().length);const quick=await page.locator('#quick-compose').boundingBox();assert.ok(quick.width<=320&&quick.height<=56);
    await page.evaluate(()=>Axx.quickReply.close());
    assert.deepEqual(errors,[]);
    const output=path.resolve(__dirname,'../../build/quick-reply-'+require('../../package.json').version);fs.mkdirSync(output,{recursive:true});
    await page.screenshot({path:path.join(output,'dictation.png')});
    console.log('PASS: shared Xxx default selection, persisted voice, loading/ready/error states, missing voice, dictation geometry/owner/draft, live blur retention, quiet and short utterance VAD, steady-noise rejection, visible input meter, unavailable exact device, cancellation barriers, single command shortcut and always-active rearm');
  }finally{await browser?.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
