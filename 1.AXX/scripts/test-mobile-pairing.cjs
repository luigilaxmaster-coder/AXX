/** QR presentation must survive polling and must not wait for conversation sync. */
const assert=require('node:assert/strict'),path=require('node:path');
const {requirePlaywright,launchChromium}=require('./test-browser-runtime.cjs');
(async()=>{
 const browser=await launchChromium(requirePlaywright().chromium);
 try{
  const page=await browser.newPage();
  await page.setContent('<section id="view-settings"></section><div id="context-menu"><hr></div>');
  await page.evaluate(()=>{
   window.intervals=[];window.setInterval=(fn,ms)=>{intervals.push({fn,ms});return intervals.length;};window.clearInterval=()=>{};
   window.failStart=true;window.messages=0;window.messageCalls=[];window.pendingMessages=[];window.saved=[];window.originalNow=Date.now;
   const active={id:'task-A',memory_scope:{task_id:'task-A',generation:0},memory_context_id:'context-0'};
   window.Axx={isNative:()=>true,chatWorkspace:{ready:true,active,async flush(){if(window.holdFlush){window.holdFlush=false;await new Promise(resolve=>window.releaseFlush=resolve);}},captureMemoryToken(){return structuredClone({memory_scope:this.active.memory_scope,memory_context_id:this.active.memory_context_id});},isMemoryTokenCurrent(token){return token.memory_scope.task_id===this.active.id&&token.memory_scope.generation===this.active.memory_scope.generation&&token.memory_context_id===this.active.memory_context_id;}},companion:{data:{sharedConversationId:'test',prefs:{keepHistory:true},messages:[]},save(){saved.push(structuredClone(this.data));},renderChat(){}},
    normalizeSettings:x=>x,app:{store:{data:{settings:{}}},renderer:{getStudio:()=>({}),getCamera20:()=>({}),moving:()=>false}},
    backendRequest:async(method,path,body)=>{
     if(path.endsWith('/start')){
      if(failStart)throw Error('QR renderer unavailable');
      return{enabled:true,devices:[],endpoint:'https://127.0.0.1:1',pairing_uri:'test-only',qr_svg_base64:btoa('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="white"/></svg>'),expires_in:120};
     }
     if(path.endsWith('/messages')){messages++;messageCalls.push(structuredClone(body));return new Promise(resolve=>pendingMessages.push(resolve));}
     return{enabled:true,devices:[],endpoint:'https://127.0.0.1:1'};
    }};
  });
  await page.addScriptTag({path:path.join(__dirname,'mobile-gateway.js')});
  await page.click('#axx-mobile-start');
  await page.waitForFunction(()=>!document.getElementById('axx-mobile-error').hidden);
  await page.evaluate(()=>intervals.find(x=>x.ms===2000).fn());
  assert.match(await page.textContent('#axx-mobile-error'),/QR renderer unavailable/);
  assert(await page.locator('#axx-mobile-error').isVisible());
  await page.evaluate(()=>window.failStart=false);
  await page.click('#axx-mobile-start');
  await page.waitForFunction(()=>document.getElementById('axx-mobile-qr').naturalWidth>0);
  assert(await page.locator('#axx-mobile-pair').isVisible());
  assert(!(await page.locator('#axx-mobile-error').isVisible()));
  assert(await page.evaluate(()=>messages>0),'history sync was attempted but remains unresolved');
  await page.evaluate(()=>Axx.companion.data.prefs.keepHistory=false);
  await page.click('#axx-mobile-start');
  assert(await page.locator('#axx-mobile-pair').isVisible(),'pairing must work when chat history sharing is off');
  await page.evaluate(()=>{Date.now=()=>Number.MAX_SAFE_INTEGER;intervals.find(x=>x.ms===1000&&x.fn.toString().includes('seconds')).fn();});
  assert(!(await page.locator('#axx-mobile-pair').isVisible()));
  assert.match(await page.textContent('#axx-mobile-error'),/caducó/);
  await page.evaluate(()=>{Date.now=originalNow;const c=Axx.companion;c.data.prefs.keepHistory=true;c.data.draft='Independent draft A';c.data.messages=[{id:'new-A',role:'user',source:'model',status:'complete',text:'New A',at:Date.now()}];Axx.chatWorkspace.active.memory_scope.generation=1;Axx.chatWorkspace.active.memory_context_id='context-1';pendingMessages.shift()({messages:[{id:'old-A',role:'assistant',text:'Old A',at:Date.now()}]});});
  await page.waitForTimeout(0);assert.deepEqual(await page.evaluate(()=>Axx.companion.data.messages.map(m=>m.id)),['new-A']);assert.equal(await page.evaluate(()=>Axx.companion.data.draft),'Independent draft A');assert.equal(await page.evaluate(()=>saved.length),0);
  await page.evaluate(()=>intervals.find(x=>x.ms===2000).fn());await page.waitForFunction(()=>pendingMessages.length===1);
  assert.deepEqual(await page.evaluate(()=>({scope:messageCalls.at(-1).memory_scope,context:messageCalls.at(-1).memory_context_id})),{scope:{task_id:'task-A',generation:1},context:'context-1'});
  await page.evaluate(()=>{Axx.companion.data.messages[0].text='Human edit after capture';});assert.equal(await page.evaluate(()=>messageCalls.at(-1).messages[0].text),'New A');
  await page.evaluate(()=>pendingMessages.shift()({messages:[{id:'incoming-current',role:'assistant',text:'Current A',at:Date.now()}],memory_scope:{task_id:'task-A',generation:1},memory_context_id:'context-1'}));
  await page.waitForFunction(()=>saved.length===1);assert.deepEqual(await page.evaluate(()=>Axx.companion.data.messages.map(m=>m.id)),['new-A','incoming-current']);assert.equal(await page.evaluate(()=>Axx.companion.data.sharedConversationId),'test');
  await page.evaluate(()=>intervals.find(x=>x.ms===2000).fn());await page.waitForFunction(()=>pendingMessages.length===1);
  await page.evaluate(()=>{Axx.chatWorkspace.active.memory_context_id='context-2';pendingMessages.shift()({messages:[{id:'old-causal',text:'Old causal A',at:Date.now()}]});});await page.waitForTimeout(0);
  assert.equal(await page.evaluate(()=>Axx.companion.data.messages.some(m=>m.id==='old-causal')),false);assert.equal(await page.evaluate(()=>saved.length),1);
  await page.evaluate(()=>intervals.find(x=>x.ms===2000).fn());await page.waitForFunction(()=>pendingMessages.length===1);
  await page.evaluate(()=>{Axx.chatWorkspace.active={id:'task-B',memory_scope:{task_id:'task-B',generation:0},memory_context_id:'context-B'};Axx.companion.data.sharedConversationId='shared-B';Axx.companion.data.messages=[{id:'own-B',role:'user',text:'B user',at:Date.now()}];Axx.companion.data.draft='Independent draft B';pendingMessages.shift()({messages:[{id:'late-A',text:'Late A',at:Date.now()}]});});await page.waitForTimeout(0);
  assert.deepEqual(await page.evaluate(()=>Axx.companion.data.messages.map(m=>m.id)),['own-B']);assert.equal(await page.evaluate(()=>Axx.companion.data.draft),'Independent draft B');assert.equal(await page.evaluate(()=>Axx.companion.data.sharedConversationId),'shared-B');assert.equal(await page.evaluate(()=>saved.length),1);
  const beforeFlush=await page.evaluate(()=>messageCalls.length);await page.evaluate(()=>{window.holdFlush=true;intervals.find(x=>x.ms===2000).fn();});await page.waitForFunction(()=>typeof releaseFlush==='function');await page.evaluate(()=>{Axx.chatWorkspace.active.memory_scope.generation++;releaseFlush();});await page.waitForTimeout(0);assert.equal(await page.evaluate(()=>messageCalls.length),beforeFlush);assert.equal(await page.evaluate(()=>Axx.companion.data.draft),'Independent draft B');
  console.log('PASS: QR polling/errors/expiry remain independent; mobile mirror snapshots preserve scope/context/source IDs and discard generation, causal-context and chat-switch late replies before merge/save without clearing drafts');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
