/* Real browser, controlled IPC only. No backend, provider or native input. */
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {requirePlaywright,launchChromium}=require('./test-browser-runtime.cjs');
(async()=>{
 const browser=await launchChromium(requirePlaywright().chromium);
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('http://memory.test/',route=>route.fulfill({contentType:'text/html',body:'<main id="view-files"></main><section id="desktop-runtime"></section><section id="view-chat"><div id="chat-log"></div><textarea id="chat-input"></textarea><button id="chat-new"></button></section><input id="keep-history" type="checkbox" checked>'}));await page.goto('http://memory.test/');
  await page.evaluate(()=>{
   const clone=value=>structuredClone(value);window.calls=[];window.brainRequests=[];window.deltas=[];window.fallback=[];window.attentionInvalidations=[];window.serial=0;if(!crypto.randomUUID)crypto.randomUUID=()=> 'synthetic-request-'+(++serial);
   const message=(id,text)=>({id,role:'user',source:'model',status:'complete',text,at:Date.now()});
   const chat=id=>({id,title:'Chat '+id,group_id:'group',messages:[message(id+'-message','Private '+id)],draft:'Draft '+id,draft_at:Date.now(),context:[{id:id+'-note',text:'Context '+id,at:Date.now()}],links:[],agent_profile:{},mode:'ask',connect_id:'connect-'+id,shared_id:'shared-'+id,memory_scope:{task_id:id,generation:0},history_count:900,review_context:[{text:'OLD REVIEW ONLY'}]});
   window.chats={A:chat('A'),B:chat('B')};window.forgetFixtureTask=id=>{const owner=chats[id];owner.memory_scope.generation++;owner.messages=[];owner.context=[];owner.links=[];owner.attachment=null;owner.connect_id+='-forgotten';for(const peer of Object.values(chats))if(peer.links.some(link=>link.source_id===id)){peer.connect_id+='-rotated';peer.links=peer.links.filter(link=>link.source_id!==id);peer.messages=peer.messages.filter(message=>message.source_task_id!==id);}};
   const bridge={listen:async()=>()=>{}};
   window.Axx={isNative:()=>true,newId:()=> 'memory-'+(++serial),app:{bridge},resident:{schedule(){}},anticipation:{invalidateMemory:id=>attentionInvalidations.push({surface:'anticipation',id})},
    companion:{data:{messages:[],draft:'',prefs:{keepHistory:true,skillProject:'project'}},attachment:null,brain:{lastRoute:null,chat:async(p,messages,signal,onDelta)=>new Promise(resolve=>brainRequests.push({p:clone(p),messages:clone(messages),signal,onDelta,resolve}))},
     save(){},renderAttachment(){},renderChat(){const log=document.getElementById('chat-log');log.replaceChildren();for(const m of this.data.messages){const row=document.createElement('article');row.dataset.messageId=m.id;row.textContent=m.text;log.append(row);}},
     message(role,text,source='local'){const m={id:'message-'+(++serial),role,text,source,status:'complete',at:Date.now()};this.data.messages.push(m);return m;},
     localNotice(text){this.message('assistant',text);this.renderChat();this.save();},invalidateMissionAttention:id=>attentionInvalidations.push({surface:'activity',id}),send:async(raw,metadata)=>fallback.push({raw,metadata}),
     cancelRequest(){this.connecting?.abort();this.pending?.abort();},stopDictation(){},stopSpeech(){},sayStatus(){},openFeature(){},openChat(){},action(){},exportChat(){}},
    backendRequest:async(method,route,body)=>{
     calls.push({method,route,body:clone(body)});
     if(route==='/axx-api/chat/migrate')return {id:'A'};
     if(route==='/axx-api/chat/conversations')return {conversations:Object.values(chats).map(clone),groups:[{id:'group',title:'Group'}],default_mode:'ask'};
     if(route.startsWith('/axx-api/chat/conversations?')){const row=clone(chats[new URLSearchParams(route.split('?')[1]).get('id')]);if(window.holdContext){window.holdContext=false;await new Promise(resolve=>window.releaseContext=resolve);}return row;}
     if(route==='/axx-api/chat/operations')return {operations:[]};
     if(route==='/axx-api/chat/save'){
      if(window.holdSave){window.holdSave=false;await new Promise(resolve=>window.releaseSave=resolve);}
      const current=chats[body.id];if(body.memory_scope?.task_id!==body.id||body.memory_scope?.generation!==current.memory_scope.generation)throw Error('STALE_MEMORY_SCOPE');
      if(body.memory_context_id!==current.connect_id)throw Error('STALE_MEMORY_CONTEXT');
      for(const m of body.messages){const index=current.messages.findIndex(row=>row.id===m.id);if(index<0)current.messages.push(clone(m));else current.messages[index]=clone(m);}current.draft=body.draft;current.attachment=clone(body.attachment);return {id:body.id};
     }
     if(route==='/axx-api/chat/context'){if(body.source_message_id){const origin=chats[body.source_task_id];if(origin.memory_scope.generation!==body.memory_scope.generation||!origin.messages.some(m=>m.id===body.source_message_id&&m.text===body.text))throw Error('STALE_SOURCE_MESSAGE');}return {saved:true};}
     if(route.startsWith('/axx-api/learning/actions'))return {actions:[]};
     if(route.startsWith('/axx-api/learning/context'))return {project_id:'project',current_folder:'workspace/folder',context_meta:{current_folder:{status:'active',task_id:Axx.chatWorkspace.active.id}}};
     if(route.startsWith('/axx-api/learning/plans'))return {plans:[]};
     if(route==='/axx-api/learning/configure'){if(window.holdConfigure){window.holdConfigure=false;await new Promise(resolve=>window.releaseConfigure=resolve);}if(chats[body.memory_scope?.task_id]?.memory_scope.generation!==body.memory_scope?.generation)throw Error('STALE_MEMORY_SCOPE');return {id:body.id};}
     if(route==='/axx-api/learning/memory-preview'){
      const owner=chats[body.task_id],forget=body.text.startsWith('olvida');
      const preview={kind:'memory_change',status:!forget&&!body.target_operation_id&&!body.target_skill_id?'needs_input':'ready',summary:'Indica qué procedimiento quieres cambiar.',change:{operation_id:body.operation_id,action:forget?'forget_task':'correct_skill',task_id:body.task_id,project_id:body.project_id,memory_scope:clone(owner.memory_scope),memory_context_id:body.memory_context_id,target:forget?{task_id:body.task_id}:{skill_id:body.target_skill_id||'skill-1',version:body.target_skill_version||1}},review_hash:'a'.repeat(64)};
      if(window.holdPreview){window.holdPreview=false;await new Promise(resolve=>window.releasePreview=resolve);}return preview;
     }
     if(route==='/axx-api/learning/memory-apply'){
      const change=body.change,owner=chats[change.task_id];if(body.confirmed!==true||body.review_hash!=='a'.repeat(64)||change.memory_scope.generation!==owner.memory_scope.generation)throw Error('STALE_REVIEW');
      if(change.action==='forget_task')forgetFixtureTask(change.task_id);
      return {state:'applied',action:change.action,task_id:change.task_id,memory_scope:clone(owner.memory_scope),summary:'Cambio aplicado a '+owner.title,counts:{},coverage:{},requires_review:false};
     }
     if(route==='/axx-api/commands/resolve')return {match:'none'};
     if(route==='/axx-api/chat')return {choices:[{message:{content:'Synthetic bridge response'},finish_reason:'stop'}],axx_router:{provider:'fixture'}};
     throw Error('Unsupported fixture route '+route);
    }};
  });
  await page.addScriptTag({path:path.join(__dirname,'command-library.js')});
  await page.addScriptTag({path:path.join(__dirname,'chat-workspace.js')});
  await page.addScriptTag({path:path.join(__dirname,'skill-library.js')});
  await page.waitForFunction(()=>Axx.chatWorkspace?.ready);await page.evaluate(()=>Axx.chatWorkspace.flush());
  const checks=[];
  const saves=await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat/save').length);
  await page.evaluate(()=>{Axx.companion.save();Axx.companion.data.messages[0].text='Mutated after snapshot';});
  await page.waitForFunction(count=>calls.filter(c=>c.route==='/axx-api/chat/save').length>count,saves);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat/save').at(-1).body.messages[0].text),'Private A');
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat/save').at(-1).body.memory_scope.generation),0);
  checks.push('Save snapshots clone messages/draft and retain their captured durable generation');
  await page.evaluate(()=>{window.inference=Axx.companion.brain.chat({provider:'ollama'},[{role:'user',content:'Question'}],new AbortController().signal,text=>deltas.push(text)).then(()=> 'published',error=>error.name);});
  await page.waitForFunction(()=>brainRequests.length===1);
  const request=await page.evaluate(()=>({p:brainRequests[0].p,messages:brainRequests[0].messages}));
  assert.deepEqual(request.p.memory_scope,{task_id:'A',generation:0});assert.equal(request.p.conversation_id,'connect-A');assert.equal(request.p.memory_context_id,'connect-A');assert.doesNotMatch(JSON.stringify(request.messages),/OLD REVIEW ONLY|900/);
  await page.evaluate(()=>{window.holdSave=true;Axx.companion.data.messages.push({id:'late-A',role:'user',source:'model',status:'complete',text:'Old saved content',at:Date.now()});window.saving=Axx.chatWorkspace.flush().catch(error=>error.message);document.getElementById('chat-input').value='Independent human draft';Axx.companion.data.draft='Independent human draft';Axx.commandLibrary.actionContext={query:'Old query'};Axx.commandLibrary.actionContextChat='A';Axx.commandLibrary.learningQuestion={conversation_id:'A',request:'Old pending correction'};});
  await page.waitForFunction(()=>typeof releaseSave==='function');
  const beforeB=await page.evaluate(()=>structuredClone(chats.B));
  await page.evaluate(()=>Axx.companion.send('olvida lo que aprendiste de esta sesión'));
  assert.equal(await page.locator('#chat-input').inputValue(),'Independent human draft');
  assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.memory_scope.generation),1);
  assert.deepEqual(await page.evaluate(()=>chats.B),beforeB);
  assert.equal(await page.evaluate(()=>attentionInvalidations.some(row=>row.surface==='anticipation'&&row.id==='A')),true);
  assert.equal(await page.evaluate(()=>attentionInvalidations.some(row=>row.surface==='activity'&&row.id==='A')),true);
  assert.equal(await page.evaluate(()=>attentionInvalidations.some(row=>row.id==='B')),false,'Forgetting A invalidates its attention surfaces without clearing independent B');
  assert.deepEqual(await page.evaluate(()=>Axx.commandLibrary.actionContext),{});assert.equal(await page.evaluate(()=>Axx.commandLibrary.learningQuestion),null);
  await page.evaluate(()=>{brainRequests[0].onDelta('STALE MODEL OUTPUT');brainRequests[0].resolve({text:'STALE MODEL OUTPUT',reason:'stop'});releaseSave();});
  assert.equal(await page.evaluate(()=>inference),'AbortError');assert.equal(await page.evaluate(()=>saving),'STALE_MEMORY_SCOPE');assert.deepEqual(await page.evaluate(()=>deltas),[]);
  assert.doesNotMatch(await page.evaluate(()=>JSON.stringify(chats.A.messages)),/Old saved content|STALE MODEL OUTPUT|Private A/);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat/save'&&c.body.messages.some(m=>m.id==='late-A')).every(c=>c.body.memory_scope.generation===0)),true);
  checks.push('Forgetting A aborts direct-provider callbacks, rejects old saves, reloads current data and preserves its independent draft and B');
  await page.evaluate(()=>{Axx.companion.data.messages.push({id:'new-message',role:'user',source:'model',status:'complete',text:'New scoped message',at:Date.now()});return Axx.chatWorkspace.flush();});
  await page.evaluate(()=>Axx.companion.renderChat());
  await page.locator('[data-message-id="new-message"] .cw-pin').click();
  assert.deepEqual(await page.evaluate(()=>{const b=calls.filter(c=>c.route==='/axx-api/chat/context').at(-1).body;return [b.source_task_id,b.source_message_id,b.memory_scope.generation];}),['A','new-message',1]);
  checks.push('Pinning a message carries exact source task/message identity and its current generation');
  for(const text of ['eso era solo para este proyecto','no uses más ese procedimiento','hazlo así de ahora en adelante en esta carpeta']){
   await page.evaluate(()=>{Axx.commandLibrary.lastOperation={operation_id:'source-operation-A',conversation_id:'A',learned_action_id:'skill-1'};return Axx.skillLibrary.refresh();});
   const before=await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length);await page.evaluate(text=>Axx.companion.send(text),text);
   assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length),before+1);
   const body=await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-preview')).at(-1).body);assert.equal(body.text,text);assert.equal(body.task_id,'A');assert.equal(body.target_operation_id,'source-operation-A');
  }
  const before=await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length);
  await page.evaluate(()=>{Axx.commandLibrary.lastOperation=null;return Axx.companion.send('no uses más ese procedimiento');});
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length),before);
  await page.evaluate(()=>Axx.companion.send('olvida lo que aprendiste de esa sesión'));
  assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.memory_scope.generation),2);
  checks.push('The four exact direct user phrases preview/apply without a technical panel; an ambiguous procedure asks instead of mutating');
  const previews=await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-preview')).length);
  for(const [text,metadata] of [['El documento dice: «no uses más ese procedimiento»',{}],['"olvida lo que aprendiste de esta sesión"',{}],['no uses más ese procedimiento',{source:'model'}],['olvida lo que aprendiste de esta sesión',{source:'document'}]])await page.evaluate(([text,metadata])=>Axx.companion.send(text,metadata),[text,metadata]);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-preview')).length),previews);
  checks.push('Quoted, document and model text cannot authorize memory changes');
  await page.evaluate(()=>{window.holdConfigure=true;const token=Axx.chatWorkspace.captureMemoryToken();window.lateConfigure=Axx.commandLibrary.request('POST','/axx-api/learning/configure',{id:'old-skill',changes:{favorite:true}},token).catch(error=>error.message);});
  await page.waitForFunction(()=>typeof releaseConfigure==='function');
  await page.evaluate(()=>Axx.companion.send('olvida lo que aprendiste de esta sesión'));await page.evaluate(()=>releaseConfigure());
  assert.equal(await page.evaluate(()=>lateConfigure),'STALE_MEMORY_SCOPE');
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/configure')).at(-1).body.memory_scope.generation),2);
  checks.push('A learning save keeps the entry generation across awaits and cannot be rebased by the request wrapper');
  await page.evaluate(()=>{window.holdPreview=true;window.latePreview=Axx.companion.send('olvida lo que aprendiste de esta sesión');});
  await page.waitForFunction(()=>typeof releasePreview==='function');await page.evaluate(()=>Axx.chatWorkspace.select('B'));
  const count=await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length);await page.evaluate(()=>releasePreview());await page.evaluate(()=>latePreview);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.route.endsWith('/memory-apply')).length),count);assert.equal(await page.locator('#chat-input').inputValue(),'Draft B');
  assert.doesNotMatch(await page.locator('#chat-log').textContent(),/Cambio aplicado a Chat A|STALE/);
  checks.push('A delayed preview for A cannot apply or publish into B');
  const priorRequests=await page.evaluate(()=>brainRequests.length);
  const result=await page.evaluate(async()=>{document.getElementById('chat-input').value='Independent draft B';chats.B.memory_scope.generation++;chats.B.messages=[];chats.B.context=[];try{await Axx.companion.brain.chat({provider:'ollama'},[{role:'user',content:'Old B prompt'}],new AbortController().signal,()=>{});return 'sent';}catch(error){return error.name;}});
  assert.equal(result,'AbortError');assert.equal(await page.evaluate(()=>brainRequests.length),priorRequests);assert.equal(await page.locator('#chat-input').inputValue(),'Independent draft B');
  assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.memory_scope.generation),1);
  checks.push('A generation change discovered by refresh aborts the old prompt before even a direct/local provider is called');
  await page.evaluate(async()=>{const own={id:'own-B',role:'user',source:'model',status:'complete',text:'Unrelated B user content',at:Date.now()},derived={id:'derived-B',role:'assistant',source:'model',status:'complete',text:'Derived from A',source_task_id:'A',at:Date.now()};chats.B.messages=[own,derived];chats.B.links=[{source_id:'A',title:'A',messages:[{role:'user',text:'Linked A context'}]}];Axx.companion.data.messages=structuredClone(chats.B.messages);await Axx.chatWorkspace.flush();window.oldBToken=Axx.chatWorkspace.captureMemoryToken();window.linkedB=Axx.companion.brain.chat({provider:'ollama'},[{role:'user',content:'Use the selected link'}],new AbortController().signal,text=>deltas.push(text)).then(()=> 'published',error=>error.name);});
  await page.waitForFunction(()=>brainRequests.length===2);
  assert.match(await page.evaluate(()=>JSON.stringify(brainRequests[1].messages)),/Linked A context/);
  await page.evaluate(()=>{window.holdSave=true;window.oldBSaving=Axx.chatWorkspace.flush().catch(error=>error.message);});
  await page.waitForFunction(()=>typeof releaseSave==='function');
  await page.evaluate(async()=>{forgetFixtureTask('A');await Axx.chatWorkspace.refreshMemory('A',chats.A.memory_scope);});
  assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.memory_scope.generation),1);assert.equal(await page.evaluate(()=>Axx.chatWorkspace.isMemoryTokenCurrent(oldBToken,false)),false);
  assert.equal(await page.locator('#chat-input').inputValue(),'Independent draft B');assert.deepEqual(await page.evaluate(()=>chats.B.messages.map(message=>message.text)),['Unrelated B user content']);
  await page.evaluate(()=>{brainRequests[1].onDelta('Late B output using A');brainRequests[1].resolve({text:'Late B output using A',reason:'stop'});releaseSave();});
  assert.equal(await page.evaluate(()=>linkedB),'AbortError');assert.equal(await page.evaluate(()=>oldBSaving),'STALE_MEMORY_CONTEXT');assert.deepEqual(await page.evaluate(()=>deltas),[]);
  const oldBSave=await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat/save'&&c.body.messages.some(message=>message.id==='derived-B')).at(-1).body);
  assert.equal(oldBSave.memory_scope.generation,1);assert.equal(oldBSave.memory_context_id,'connect-B');assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.memory_context_id),'connect-B-rotated');
  checks.push('Forgetting linked A rotates B context without changing B generation; old B saves/results retain the old opaque ID and cannot restore A, while B user data/draft survive');
  const html=fs.readFileSync(path.join(__dirname,'../Axx.html'),'utf8'),brainStart=html.indexOf('    class BrainClient {'),brainEnd=html.indexOf('    Axx.BrainClient = BrainClient;',brainStart);
  assert(brainStart>0&&brainEnd>brainStart);await page.addScriptTag({content:html.slice(brainStart,brainEnd)+'\nAxx.BrainClient=BrainClient;'});
  await page.evaluate(async()=>{Axx.promptContracts={prepare:async(_p,messages)=>messages};const brain=new Axx.BrainClient(),p={provider:'bridge',model:'fixture',memory_scope:Axx.chatWorkspace.captureMemoryScope(),memory_context_id:Axx.chatWorkspace.active.memory_context_id,conversation_id:'wrong-logical-id'};brain.connected=true;brain.signature=brain.signatureOf(p);await brain.chat(p,[{role:'user',content:'Bridge scope'}],new AbortController().signal,()=>{});});
  const bridge=await page.evaluate(()=>calls.filter(c=>c.route==='/axx-api/chat').at(-1).body);assert.deepEqual(bridge.memory_scope,{task_id:'B',generation:1});assert.equal(bridge.conversation_id,'connect-B-rotated');
  await page.evaluate(()=>{window.fetchCalls=0;window.originalFetch=fetch;window.fetch=async()=>{fetchCalls++;throw Error('Direct provider must not be reached');};Axx.promptContracts.prepare=async(_p,messages)=>{await new Promise(resolve=>window.releasePrompt=resolve);return messages;};const brain=new Axx.BrainClient(),p={provider:'ollama',model:'fixture',endpoint:'http://unused.invalid',memory_scope:Axx.chatWorkspace.captureMemoryScope()};brain.connected=true;brain.signature=brain.signatureOf(p);window.preparingController=new AbortController();window.preparing=brain.chat(p,[{role:'user',content:'Old prepared prompt'}],preparingController.signal,()=>{}).then(()=> 'sent',error=>error.name);});
  await page.waitForFunction(()=>typeof releasePrompt==='function');await page.evaluate(()=>{preparingController.abort();releasePrompt();});assert.equal(await page.evaluate(()=>preparing),'AbortError');assert.equal(await page.evaluate(()=>fetchCalls),0);await page.evaluate(()=>{window.fetch=originalFetch;Axx.promptContracts.prepare=async(_p,messages)=>messages;});
  checks.push('Cancellation during awaited prompt preparation stops the actual direct-provider path before fetch');
  const connect=fs.readFileSync(path.join(__dirname,'axx-connect.js'),'utf8'),connectStart=connect.indexOf('    Axx.BrainClient.prototype.chat = async function'),connectEnd=connect.indexOf('    c.refreshChatGPTUI',connectStart);
  assert(connectStart>0&&connectEnd>connectStart);
  await page.addScriptTag({content:'(()=>{const c=Axx.companion,originalChat=Axx.BrainClient.prototype.chat;window.connectBodies=[];const run=async body=>{connectBodies.push(structuredClone(body));return {text:"Synthetic Connect response",reason:"stop"};};'+connect.slice(connectStart,connectEnd)+'})();'});
  await page.evaluate(async()=>{const brain=new Axx.BrainClient(),p={provider:'chatgpt',model:'fixture',memory_scope:Axx.chatWorkspace.captureMemoryScope(),memory_context_id:Axx.chatWorkspace.active.memory_context_id};Axx.companion.data.connectConversationId='wrong-current-context';await brain.chat(p,[{role:'user',content:'Connect scope'}],new AbortController().signal,()=>{});await brain.chat(p,[{role:'system',content:"Translate the user's text from es to en."},{role:'user',content:'Hola'}],new AbortController().signal,()=>{});});
  assert.equal(await page.evaluate(()=>connectBodies.length),2);for(const body of await page.evaluate(()=>connectBodies)){assert.deepEqual(body.memory_scope,{task_id:'B',generation:1});assert.equal(body.conversation_id,'connect-B-rotated');}
  checks.push('Actual Bridge/Connect chat and translation propagate the fixed scope and captured opaque context rather than reading a newer current ID');
  const sendStart=html.indexOf('        async send(raw, options = {}) {'),sendEnd=html.indexOf('        runLocal(i) {',sendStart);assert(sendStart>0&&sendEnd>sendStart);
  await page.addScriptTag({content:'(()=>{const node=id=>document.getElementById(id);window.actualCompanionSend=({'+html.slice(sendStart,sendEnd)+'}).send;})();'});
  const beforeConnect=await page.evaluate(()=>brainRequests.length);
  await page.evaluate(()=>{Axx.app.stopDemo=()=>{};Axx.parseIntent=()=>null;const c=Axx.companion;c.app=Axx.app;c.stopTour=()=>{};c.data.prefs.provider='ollama';c.brain.connected=false;c.connect=async function(){this.connecting=new AbortController();await new Promise(resolve=>window.releaseConnection=resolve);this.brain.connected=true;this.connecting=null;};window.connectingSend=actualCompanionSend.call(c,'Pending connection question').then(()=>window.connectionFinished=true,error=>{window.connectionError=error.message;});});
  await page.waitForFunction(()=>typeof releaseConnection==='function'||window.connectionError||window.connectionFinished);assert.equal(await page.evaluate(()=>window.connectionError),undefined);assert.equal(await page.evaluate(()=>typeof releaseConnection),'function');await page.evaluate(()=>Axx.companion.send('olvida lo que aprendiste de esta sesión'));await page.evaluate(()=>releaseConnection());await page.evaluate(()=>connectingSend);
  assert.equal(await page.evaluate(()=>brainRequests.length),beforeConnect);assert.doesNotMatch(await page.evaluate(()=>JSON.stringify(Axx.companion.data.messages)),/Pending connection question/);assert.doesNotMatch(await page.evaluate(()=>JSON.stringify(chats.B.messages)),/Pending connection question/);
  checks.push('Actual Companion.send captures its token before a held connection; forget then late connect completion causes zero upstream calls and no restored message');
  for(const created of [false,true]){
   const migration=await browser.newPage();try{
    await migration.route('http://migration.test/',route=>route.fulfill({contentType:'text/html',body:'<section id="view-chat"><div id="chat-log"></div><textarea id="chat-input"></textarea><button id="chat-new"></button></section><input id="keep-history" type="checkbox" checked>'}));await migration.goto('http://migration.test/');
    await migration.evaluate(created=>{window.calls=[];const old={id:'legacy-old',role:'user',source:'model',status:'complete',text:'Old local legacy',at:Date.now()},row={id:'migration',title:'Migration chat',mode:'ask',messages:created?[]:[{...old,id:'current',text:'Current server message'}],draft:'Server draft',context:[],links:[],connect_id:'migration-context',memory_scope:{task_id:'migration',generation:created?0:1}};window.Axx={isNative:()=>true,app:{bridge:{listen:async()=>()=>{}}},companion:{data:{messages:[old],draft:'Old local draft',prefs:{keepHistory:true}},save(){},renderChat(){},renderAttachment(){},cancelRequest(){},stopDictation(){},stopSpeech(){},sayStatus(){},send(){},exportChat(){},brain:{async chat(){}}},commandLibrary:{renderOperation(){},request:async()=>({})},backendRequest:async(method,route,body)=>{calls.push({method,route,body:structuredClone(body)});if(route.endsWith('/migrate'))return {id:row.id,created};if(route==='/axx-api/chat/conversations')return {conversations:[structuredClone(row)],groups:[],default_mode:'ask'};if(route.startsWith('/axx-api/chat/conversations?'))return structuredClone(row);if(route.endsWith('/operations'))return {operations:[]};if(route.endsWith('/save')){for(const message of body.messages)if(!row.messages.some(m=>m.id===message.id))row.messages.push(structuredClone(message));return {id:row.id};}throw Error('Unexpected migration fixture route');}};},created);
    await migration.addScriptTag({path:path.join(__dirname,'chat-workspace.js')});await migration.waitForFunction(()=>Axx.chatWorkspace?.ready);await migration.evaluate(()=>Axx.chatWorkspace.flush());
    const legacySaves=await migration.evaluate(()=>calls.filter(call=>call.route.endsWith('/save')&&call.body.messages.some(message=>message.id==='legacy-old')));
    if(created){assert(legacySaves.length>0);assert.equal(Object.hasOwn(legacySaves[0].body,'memory_scope'),false);assert.equal(Object.hasOwn(legacySaves[0].body,'memory_context_id'),false);}else assert.deepEqual(legacySaves,[]);
    if(!created){
     const references=await migration.evaluate(()=>{const workspace=Axx.chatWorkspace,token=workspace.captureMemoryToken(),ref={task_id:'unopened-A',generation:4,context_id:'server-captured-A'},before=calls.length;let unknown=false;try{workspace.captureMemoryScope(ref.task_id);}catch{unknown=true;}const allowed=workspace.allowsMemoryReference(ref);let stillUnknown=false;try{workspace.captureMemoryScope(ref.task_id);}catch{stillUnknown=true;}workspace.invalidateMemory(ref.task_id);return {unknown,allowed,stillUnknown,revoked:workspace.allowsMemoryReference(ref),independent:workspace.allowsMemoryReference(token.memory_scope),strictOwn:workspace.isMemoryTokenCurrent(token),wrongGeneration:workspace.allowsMemoryReference({...token.memory_scope,generation:token.memory_scope.generation+1}),wrongContext:workspace.allowsMemoryReference({...token.memory_scope,context_id:'other-context'}),requests:calls.length-before};});
     assert.deepEqual(references,{unknown:true,allowed:true,stillUnknown:true,revoked:false,independent:true,strictOwn:true,wrongGeneration:false,wrongContext:false,requests:0},'A fresh client can project server-validated B with unopened A lineage, then rejects known A revocation without rebasing scopes or clearing independent B');
    }
   }finally{await migration.close();}
  }
  checks.push('Legacy imports run only for migrate.created=true and never acquire a fresh scope/context for old local messages or a reopened forgotten chat');
  checks.push('Projection dependency checks allow an unopened server reference, reject known revocation/generation/context conflicts, and preserve strict own tokens without fetching a new scope');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({kind:'TASK_MEMORY_CONTROLLED_IPC',passed:checks.length,checks,native_acceptance:false},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
