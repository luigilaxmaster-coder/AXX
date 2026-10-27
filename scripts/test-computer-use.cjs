// Real UI and chat routing; native windows, model readiness and grants are controlled contracts.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const html=fs.readFileSync('1.AXX/Axx.html','utf8'),start=html.indexOf('        async send(raw, options = {}) {'),end=html.indexOf('        runLocal(i) {',start);assert.ok(start>0&&end>start);
 let visual=true,externalCalls=0,parsed=0;
 const axx={computerUse:{activeFor:id=>visual&&id==='chat-one'},chatWorkspace:{active:{id:'chat-one'}},parseIntent:()=>{parsed++;return null;}};
 const send=new Function('Axx','node','return ({'+html.slice(start,end)+'}).send')(axx,()=>({disabled:false}));
 const companion={pending:false,externalBusy:false,externalCommand:()=>{externalCalls++;return async()=>'local';},attachment:null,brain:{connected:false},app:{stopDemo(){},toast(){}},stopTour(){},stopSpeech(){},message(){return{};},renderChat(){},save(){},sayStatus(){},speakReply(){},action(){},error:e=>e.message};
 await send.call(companion,'reproduce Faint');assert.equal(externalCalls,0);assert.equal(parsed,0);visual=false;await send.call(companion,'reproduce Faint');assert.equal(externalCalls,1);
 const browser=await chromium.launch({headless:true,executablePath:path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
 try{
  const p=await browser.newPage({viewport:{width:1000,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.setContent('<header class="chat20-head-actions"></header><main id="panel"><section class="panel-view" id="view-chat"><div id="chat-workspace"></div></section><section class="panel-view" id="view-settings" hidden></section><section class="panel-view" id="view-ai" hidden><button id="tab-mode-chatgpt">ChatGPT</button></section></main>');
  await p.evaluate(()=>{
   Object.defineProperty(crypto,'randomUUID',{value:()=>String(Math.random())});window.calls=[];window.stopped=0;window.grant={active:false};window.grantChat=null;window.engineVerified=true;window.engineAuthenticated=true;window.engineModel='fixture';window.engineOffline=false;window.windowRows=[{window_id:10,pid:20,title:'Fixture'},{window_id:11,pid:21,title:'Otra ventana'}];window.holdBegin=false;window.connectionTabOpened=0;
   document.getElementById('tab-mode-chatgpt').onclick=()=>connectionTabOpened++;
   const openFeature=id=>{window.opened=id;document.querySelectorAll('.panel-view').forEach(n=>n.hidden=n.id!=='view-'+id);};
   window.Axx={isNative:()=>true,chatWorkspace:{active:{id:'chat-one',title:'Mi chat'}},companion:{data:{prefs:{provider:'chatgpt',model:'fixture'}},openFeature,openChat:()=>openFeature('chat')},resident:{schedule(){}},commandLibrary:{open(){window.reviewOpened=true;}},
    backendRequest:async(method,route,body)=>{
     calls.push({method,route,body});
     if(route==='/axx-api/connect/status?engine=1'){if(engineOffline)throw Error('Conexión no disponible');return {executor:'ready',ui_connected:true,engine:{authenticated:engineAuthenticated,inference_verified:engineVerified,model:engineModel}};}
     if(route.endsWith('/prepare'))return {operation_id:'windows'};
     if(route.endsWith('/execute'))return {state:'succeeded',output:{windows:windowRows}};
     if(route.endsWith('/begin')){if(holdBegin)await new Promise(resolve=>window.releaseBegin=resolve);if(!body.image_authorized||!body.allow_input)return {error:{message:'Autorice imágenes y entrada'}};grantChat=body.conversation_id;grant={active:true,title:'Fixture',actions:0};return grant;}
     if(route.includes('/status?'))return new URLSearchParams(route.split('?')[1]).get('conversation_id')===grantChat?grant:{active:false};
     if(route.endsWith('/stop')){stopped++;grant={active:false};return grant;}
     throw Error('Unexpected route '+route);
    }};
  });
  await p.addScriptTag({path:'1.AXX/scripts/computer-use.js'});
  await p.click('#cu-open');await p.waitForFunction(()=>document.getElementById('cu-model').textContent.includes('Modelo comprobado'));assert.equal(await p.locator('#view-computeruse').isVisible(),true);assert.equal(await p.locator('#cu-start').isDisabled(),true);
  assert.equal(await p.evaluate(()=>calls.some(c=>c.route.endsWith('/begin'))),false);
  await p.click('#cu-refresh');await p.waitForFunction(()=>document.getElementById('cu-window').options.length===3);assert.equal(await p.locator('#cu-window').inputValue(),'');
  await p.selectOption('#cu-window','0');await p.check('#cu-images');assert.equal(await p.locator('#cu-start').isDisabled(),true);await p.check('#cu-input');assert.equal(await p.locator('#cu-start').isEnabled(),true);
  await p.evaluate(()=>engineVerified=false);await p.click('#cu-check');await p.waitForFunction(()=>document.getElementById('cu-model').textContent.includes('falta probar'));assert.equal(await p.locator('#cu-start').isDisabled(),true);
  await p.evaluate(()=>engineVerified=true);await p.click('#cu-check');await p.waitForFunction(()=>!document.getElementById('cu-start').disabled);await p.click('#cu-start');await p.waitForFunction(()=>Axx.computerUse.activeFor('chat-one'));assert.match(await p.locator('#cu-live').innerText(),/Habilitado.*Fixture/);
  assert.equal(await p.locator('#cu-images').isChecked(),false);assert.equal(await p.locator('#cu-input').isChecked(),false);assert.equal(await p.evaluate(()=>calls.filter(c=>c.route.endsWith('/begin')).length),1);
  await p.click('#cu-chat-open');assert.equal(await p.evaluate(()=>opened),'chat');assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-two')),false);
  await p.evaluate(()=>Axx.chatWorkspace.active={id:'chat-two',title:'Otro chat'});await p.waitForFunction(()=>stopped===1);assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-one')),false);
  await p.click('#cu-launch');await p.waitForFunction(()=>document.getElementById('cu-model').textContent.includes('Modelo comprobado'));assert.match(await p.locator('#cu-chat').innerText(),/Otro chat/);assert.equal(await p.locator('#cu-images').isChecked(),false);
  await p.check('#cu-images');await p.check('#cu-input');await p.click('#cu-start');await p.waitForFunction(()=>Axx.computerUse.activeFor('chat-two'));await p.evaluate(()=>grant.blocked='Efecto incierto');await p.waitForFunction(()=>!document.getElementById('cu-review').hidden);assert.match(await p.locator('#cu-live').innerText(),/Revisión requerida/);await p.click('#cu-review');assert.equal(await p.evaluate(()=>reviewOpened),true);
  await p.evaluate(()=>{grant.blocked=null;grant.last_error='UI Automation excedió el límite';});await p.waitForFunction(()=>!document.getElementById('cu-diagnostic').hidden);assert.match(await p.locator('#cu-diagnostic').innerText(),/nueva observación/);
  await p.evaluate(()=>grant.blocked='uncertain');await p.waitForFunction(()=>document.getElementById('cu-diagnostic').textContent.includes('no repitas'));await p.evaluate(()=>grant.last_error=null);await p.waitForFunction(()=>document.getElementById('cu-diagnostic').hidden);
  await p.keyboard.press('Escape');await p.waitForFunction(()=>stopped===2);assert.equal(await p.locator('#cu-stop').isHidden(),true);
  await p.evaluate(()=>{Axx.companion.data.prefs.provider='bridge';});await p.click('#cu-check');assert.equal(await p.locator('#cu-start').isDisabled(),true);await p.click('#cu-connect');assert.equal(await p.evaluate(()=>opened),'ai');assert.equal(await p.evaluate(()=>connectionTabOpened),1);assert.equal(await p.evaluate(()=>Axx.companion.data.prefs.provider),'bridge');
  await p.evaluate(()=>{Axx.companion.data.prefs.provider='chatgpt';engineModel='different';});await p.click('#cu-launch');await p.waitForFunction(()=>document.getElementById('cu-model').textContent.includes('falta probar'));assert.equal(await p.locator('#cu-start').isDisabled(),true);
  await p.evaluate(()=>{engineModel='fixture';engineOffline=true;});await p.click('#cu-check');await p.waitForFunction(()=>!document.getElementById('cu-error').hidden);assert.match(await p.locator('#cu-error').innerText(),/Conexión no disponible/);assert.equal(await p.locator('#cu-start').isDisabled(),true);
  await p.evaluate(()=>{engineOffline=false;windowRows=[];});await p.click('#cu-check');await p.click('#cu-refresh');await p.waitForFunction(()=>document.getElementById('cu-window-status').textContent.includes('No hay ventanas'));assert.equal(await p.locator('#cu-start').isDisabled(),true);
  await p.evaluate(()=>windowRows=[{window_id:10,pid:20,title:'Fixture'}]);await p.click('#cu-refresh');await p.waitForFunction(()=>document.getElementById('cu-window').options.length===2);await p.selectOption('#cu-window','0');await p.check('#cu-images');await p.check('#cu-input');await p.evaluate(()=>holdBegin=true);await p.click('#cu-start');await p.waitForFunction(()=>typeof releaseBegin==='function');await p.evaluate(()=>{Axx.chatWorkspace.active={id:'chat-three'};holdBegin=false;releaseBegin();});await p.waitForFunction(()=>stopped===3);assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-two')),false);
  const beforeRecovery=await p.evaluate(()=>calls.filter(c=>c.route.endsWith('/begin')).length);await p.evaluate(()=>{grantChat='chat-three';grant={active:true,title:'Permiso existente',actions:2};});await p.click('#cu-launch');await p.waitForFunction(()=>Axx.computerUse.activeFor('chat-three'));assert.match(await p.locator('#cu-live').innerText(),/Permiso existente/);assert.equal(await p.evaluate(()=>calls.filter(c=>c.route.endsWith('/begin')).length),beforeRecovery);
  await p.click('#cu-stop');await p.waitForFunction(()=>stopped===4);await p.evaluate(()=>Axx.companion.openFeature('settings'));await p.click('#cu-settings-open');assert.equal(await p.evaluate(()=>opened),'computeruse');assert.deepEqual(errors,[]);

  // Full application: actual catalog, panel routing and original avatar; native calls remain fixtures.
  const full=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),fullErrors=[];full.on('pageerror',e=>fullErrors.push(e.message));
  await full.route('http://127.0.0.1:14174/**',route=>{const pathname=new URL(route.request().url()).pathname;const root=path.resolve('1.AXX'),file=path.resolve(root,'.'+(pathname==='/'?'/Axx.html':pathname));if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){return route.fulfill({status:404,body:''});}return route.fulfill({path:file});});
  await full.addInitScript(()=>{const desktop={workWidth:1440,workHeight:1000,spaceLeft:800,spaceRight:640,spaceAbove:450,spaceBelow:550,anchorX:800,anchorY:450,screenX:800,screenY:450,scaleFactor:1};window.__TAURI__={core:{invoke:async(name,args)=>{if(name==='native_status')return {native:true,backendReady:false,desktop};if(name==='desktop_layout')return {...desktop,...args};if(name==='backend_request'){if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};if(args.path==='/axx-api/connect/status?engine=1')return {executor:'ready',ui_connected:true,engine:{authenticated:false,inference_verified:false}};return {};}return null;}},event:{listen:async()=>()=>{}}};});
  await full.goto('http://127.0.0.1:14174/');await full.waitForFunction(()=>Axx.computerUse&&Axx.resident?.firstFrame);
  await full.evaluate(()=>{Axx.flow.nav.catalog('assist');Axx.flow.render();});await full.locator('#flow-grid [data-tool=computeruse]').click();await full.waitForFunction(()=>Axx.companion.dock.selected==='computeruse');assert.equal(await full.locator('#view-computeruse').isVisible(),true);assert.equal(await full.locator('#cu-start').isDisabled(),true);
  await full.evaluate(()=>Axx.companion.openFeature('settings'));await full.locator('#cu-settings-open').click();assert.equal(await full.locator('#view-computeruse').isVisible(),true);
  await full.evaluate(()=>Axx.companion.openChat());assert.equal(await full.locator('#cu-launch').isVisible(),true);await full.locator('#cu-launch').click();assert.equal(await full.locator('#view-computeruse').isVisible(),true);
  const output=path.resolve('build/computer-use-ui');fs.mkdirSync(output,{recursive:true});for(const theme of ['light','dark']){await full.evaluate(t=>Axx.interfaceTheme.apply(t),theme);await full.screenshot({path:path.join(output,'setup-'+theme+'.png')});}
  assert.deepEqual(fullErrors,[]);console.log('COMPUTER_USE_DISCOVERY_READINESS_CONSENT_RECONCILE_SCOPE_LAYOUT_PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
