// Actual quick UI + original openChat/tap methods; microphone/model are controlled contracts.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM||path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const p=await browser.newPage({viewport:{width:1000,height:800}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.route('http://127.0.0.1:14173/**',route=>route.fulfill({contentType:'text/html',body:'<body class="native axx-resident"><canvas id="avatar" tabindex="0" style="position:fixed;left:450px;top:300px;width:100px;height:100px"></canvas><section id="panel" hidden></section><section id="view-settings"></section><section id="view-help"><div class="help-copy"></div></section></body>'}));await p.goto('http://127.0.0.1:14173/');
  const source=fs.readFileSync('1.AXX/Axx.html','utf8');const start=source.indexOf('        openChat(reposition = true) {'),end=source.indexOf('        openFamily(',start);
  const tapStart=source.indexOf('        tap() { Axx.quickReply?.close();'),tapEnd=source.indexOf('        summon(',tapStart);
  assert.ok(start>0&&end>start&&tapStart>0&&tapEnd>tapStart);
  await p.evaluate(({open,tap})=>{
   window.fullChat=0;window.captures=0;window.sent=[];window.stopped=0;window.hits=0;window.focusActions=[];window.penOpen=false;
   window.Axx={isNative:()=>true,chatWorkspace:{ready:true,active:{id:'chat-one'}},liveConversation:{stop(){}},flow:{nav:{step:0},fold(){this.nav.step=0;},tap(){this.nav.step=2;}},
    nativeVoice:{inputLevel:null,attach(owner){owner.start=()=>{captures++;owner.state='starting';owner.onState();};owner.finish=()=>{owner.state='stopping';owner.onState();};owner.stop=()=>{owner.state='idle';owner.onState();};}},
    app:{bridge:{async action(name){focusActions.push(name);}},toast(){},stopDemo(){},updateHitMap:async()=>{hits++;},setVisible(){}},magicPen:{open(){penOpen=true;},isOpen(){return penOpen;}},symbiosis:{prefs:{language:'es-DO'},reader:{state:'idle'}},
    commandLibrary:{busy:false,operation:null,cancel(){stopped++;},open(){window.libraryOpened=true;}}};
   const c=Axx.companion={data:{messages:[],prefs:{mode:'companion'}},pending:null,dictating:false,renderChat(){},sayStatus(){},refreshVoiceState(){window.bodyPhase=this.dictating?'listening':'idle';},
    stopSpeech(){Axx.symbiosis.reader.state='idle';},stopDictation(){},cancelRequest(){stopped++;this.pending=null;window.releaseResponse?.();},read(text){window.spoken=text;Axx.symbiosis.reader.state='speaking';},
    setSize(){},follower:{go(){}},openFeature(){fullChat++;document.getElementById('panel').hidden=false;},positionPanel(){},
    async send(text,metadata){sent.push({text,metadata});this.openChat();this.data.messages.push({id:'user-'+sent.length,role:'user',text});this.pending={};
     await new Promise(resolve=>{window.releaseResponse=resolve;});this.data.messages.push({id:'reply-'+sent.length,role:'assistant',text:'Respuesta comprobada',status:'complete'});this.pending=null;this.renderChat();}};
   c.app=Axx.app;
   c.openChat=new Function('Axx','node','return ({'+open+'}).openChat')(Axx,id=>document.getElementById(id));
   const g={workWidth:1000,workHeight:800,spaceLeft:500,spaceRight:500,spaceAbove:350,spaceBelow:450};
   const layout=()=>{if(!Axx.quickReply)return;Axx.quickReply.layout(g,240,(id,x,y,width,height)=>Object.assign(document.getElementById(id).style,{left:x+500+'px',top:y+350+'px',width:width+'px',height:height+'px'}));};
   Axx.resident={drag:null,fold(){Axx.flow.nav.step=0;document.getElementById('panel').hidden=true;},schedule(){queueMicrotask(layout);}};
   Axx.resident.tap=new Function('Axx','return ({'+tap+'}).tap')(Axx);
   window.layout=layout;window.localStorageSnapshot='shape-preserved';
  },{open:source.slice(start,end),tap:source.slice(tapStart,tapEnd)});
  await p.addScriptTag({path:'1.AXX/scripts/quick-reply.js'});
  await p.addScriptTag({path:'1.AXX/scripts/interface-theme.js'});
  await p.addStyleTag({path:'1.AXX/scripts/interface-theme.css'});
  assert.equal(await p.evaluate(()=>captures),0);
  await p.focus('#avatar');await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement.id),'quick-write');await p.keyboard.press('ArrowRight');assert.equal(await p.evaluate(()=>document.activeElement.id),'quick-pen');await p.keyboard.press('ArrowRight');assert.equal(await p.evaluate(()=>document.activeElement.id),'quick-talk');await p.keyboard.press('ArrowRight');assert.equal(await p.evaluate(()=>document.activeElement.id),'quick-write');await p.keyboard.press('End');assert.equal(await p.evaluate(()=>document.activeElement.id),'quick-talk');
  await p.hover('#avatar');await p.waitForFunction(()=>!document.getElementById('quick-actions').hidden);assert.equal(await p.locator('#quick-actions button').count(),3);
  await p.click('#quick-write');assert.equal(await p.evaluate(()=>fullChat),0);
  assert.ok((await p.locator('#quick-compose').boundingBox()).y>400);assert.ok((await p.locator('#quick-compose').boundingBox()).height<=56);assert.ok(await p.evaluate(()=>focusActions.includes('open_panel')));
  assert.equal(await p.locator('#quick-input').getAttribute('placeholder'),null);assert.equal(await p.locator('#quick-state').evaluate(el=>getComputedStyle(el).clipPath),'inset(50%)');
  const activitiesStart=source.indexOf('        activities() {'),activitiesEnd=source.indexOf('        arrange() {',activitiesStart);assert.ok(activitiesStart>0&&activitiesEnd>activitiesStart);
  const activityState=await p.evaluate(fragment=>{const host=document.createElement('nav');host.id='a11-activities';document.body.append(host);const controller={music:{tracks:[{}],audio:{paused:true}},remoteMusic:{state:{connected:true,playing:false}},screen:{active:false,blob:null},app:{store:{data:{timer:null}}},tools:{stopwatch:{running:false}},selected:null};const activities=new Function('ac','ACTION_NAMES','return ({'+fragment+'}).activities')(id=>document.getElementById(id),{music:'Música'});activities.call(controller);const idleHidden=host.hidden;controller.music.audio.paused=false;activities.call(controller);const playingVisible=!host.hidden;controller.music.audio.paused=true;activities.call(controller);const stoppedHidden=host.hidden;host.remove();return {idleHidden,playingVisible,stoppedHidden};},source.slice(activitiesStart,activitiesEnd));assert.deepEqual(activityState,{idleHidden:true,playingVisible:true,stoppedHidden:true});
  await p.fill('#quick-input','Una pregunta');await p.press('#quick-input','Enter');await p.waitForFunction(()=>sent.length===1);
  assert.equal(await p.evaluate(()=>fullChat),0);assert.equal(await p.locator('#quick-reply').isVisible(),true);
  await p.evaluate(()=>releaseResponse());await p.waitForFunction(()=>document.getElementById('quick-reply-text').textContent==='Respuesta comprobada');
  await p.waitForFunction(()=>!document.getElementById('quick-reply').getAnimations().length);const replySize=await p.locator('#quick-reply').boundingBox();assert.equal(replySize.width,260);assert.ok(replySize.height<=160);
  await p.evaluate(()=>{const change=(id,value,event='input')=>{const input=document.getElementById(id);input.value=value;input.dispatchEvent(new Event(event));};change('axx-widget-opacity','55');change('axx-widget-size','125');change('axx-widget-motion','700');change('axx-interface-font','serif','change');change('axx-color-background','#272035');});
  await p.waitForFunction(()=>document.getElementById('quick-reply').offsetWidth===325);assert.equal(await p.locator('#quick-root').evaluate(el=>getComputedStyle(el).fontFamily),'Georgia, serif');assert.equal(await p.evaluate(()=>Axx.interfaceTheme.motionDuration),700);assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('axx.interface.customization')).opacity),55);assert.match(await p.locator('#quick-compose').evaluate(el=>getComputedStyle(el).backgroundColor),/0.55/);
  await p.evaluate(()=>document.getElementById('axx-widgets-reset').click());await p.waitForFunction(()=>document.getElementById('quick-reply').offsetWidth===260);
  await p.click('#quick-replay');assert.equal(await p.evaluate(()=>spoken),'Respuesta comprobada');await p.click('#quick-stop');assert.equal(await p.evaluate(()=>Axx.symbiosis.reader.state),'idle');
  await p.click('#quick-talk');assert.equal(await p.evaluate(()=>captures),1);assert.equal(await p.evaluate(()=>bodyPhase),'idle');
  await p.evaluate(()=>{const q=Axx.quickReply.capture;q.state='listening';Axx.nativeVoice.inputLevel={owner:q,rms:.04};q.onState();});
  await p.waitForFunction(()=>bodyPhase==='listening'&&!document.getElementById('quick-level').hidden);assert.ok(await p.evaluate(()=>Axx.quickReply.microphoneLevel>.4));
  assert.equal(await p.locator('#quick-input').isVisible(),false);assert.equal(await p.locator('#quick-send').getAttribute('aria-label'),'Terminar grabación');assert.ok((await p.locator('#quick-compose').boundingBox()).height<=76);
  await p.click('#quick-pen');assert.equal(await p.evaluate(()=>penOpen),true);assert.equal(await p.evaluate(()=>Axx.quickReply.active),false);assert.equal(await p.evaluate(()=>Axx.quickReply.capture.state),'idle');assert.equal(await p.evaluate(()=>fullChat),0);await p.waitForFunction(()=>document.getElementById('quick-actions').hidden);await p.evaluate(()=>penOpen=false);
  await p.evaluate(()=>Axx.quickReply.write());assert.equal(await p.evaluate(()=>Axx.quickReply.capture.state),'idle');await p.click('#quick-talk');assert.equal(await p.evaluate(()=>captures),2);
  await p.evaluate(()=>Axx.quickReply.capture.onFinal('Consulta por voz'));await p.waitForFunction(()=>sent.length===2);assert.equal(await p.evaluate(()=>sent[1].metadata.source),'voice');assert.equal(await p.evaluate(()=>fullChat),0);
  await p.evaluate(()=>releaseResponse());await p.waitForFunction(()=>!Axx.companion.pending);
  await p.click('#quick-full');assert.equal(await p.evaluate(()=>fullChat),1);assert.equal(await p.evaluate(()=>Axx.quickReply.active),false);
  await p.evaluate(()=>{Axx.resident.fold();Axx.quickReply.write();Axx.quickReply.capture.onError('Micrófono desconectado');});
  assert.match(await p.locator('#quick-state').innerText(),/Micrófono desconectado/);
  await p.evaluate(()=>Axx.chatWorkspace.active={id:'chat-two'});await p.waitForFunction(()=>!Axx.quickReply.active);
  await p.evaluate(()=>{Axx.quickReply.write();Axx.resident.tap();});assert.equal(await p.evaluate(()=>Axx.flow.nav.step),2);assert.equal(await p.evaluate(()=>Axx.quickReply.active),false);
  await p.evaluate(()=>{Axx.resident.fold();Axx.quickReply.write();});await p.keyboard.press('Escape');assert.equal(await p.evaluate(()=>Axx.quickReply.active),false);
  assert.equal(await p.evaluate(()=>focusActions.at(-1)),'close_panel');
  await p.emulateMedia({reducedMotion:'reduce'});await p.evaluate(()=>Axx.quickReply.write());assert.equal(await p.locator('#quick-compose').evaluate(el=>getComputedStyle(el).animationName),'none');
  await p.waitForFunction(()=>!document.getElementById('quick-compose').getAnimations().length);await p.evaluate(()=>Axx.quickReply.close());await p.waitForFunction(()=>document.getElementById('quick-actions').hidden);
  await p.emulateMedia({reducedMotion:'no-preference'});await p.hover('#avatar');await p.waitForFunction(()=>document.getElementById('quick-actions').getAnimations().length>0);assert.notEqual(await p.locator('#quick-actions').evaluate(el=>getComputedStyle(el).translate),'none');
  await p.mouse.move(20,20);await p.waitForTimeout(380);await p.hover('#avatar');await p.waitForTimeout(650);assert.equal(await p.locator('#quick-actions').isVisible(),true);assert.equal(await p.locator('#quick-actions').getAttribute('inert'),null);
  assert.deepEqual(errors,[]);console.log('QUICK_REPLY_HOVER_COMPOSER_VOICE_STATE_RESPONSE_CANCEL_SCOPE_PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
