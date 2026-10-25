// Real authenticated HTTP + SQLite; minimal Companion harness, not native visual acceptance.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{spawn}=require('child_process'),{createRequire}=require('module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const child=spawn('python',['-m','backend.tests.chat_http_fixture'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
 let browser;
 try{
  const config=await new Promise((resolve,reject)=>{let output='';child.stdout.on('data',d=>{output+=d;if(output.includes('\n'))resolve(JSON.parse(output.split('\n')[0]));});child.on('exit',code=>reject(Error('fixture exited '+code)));});
  browser=await chromium.launch({headless:true,executablePath:path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
  const page=await browser.newPage();page.setDefaultTimeout(10000);page.on('console',m=>console.log('BROWSER',m.text()));const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.exposeFunction('backend',async(method,url,body)=>{const r=await fetch('http://127.0.0.1:'+config.port+url,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;});
  await page.route('http://chat.test/',route=>route.fulfill({contentType:'text/html',body:'<section id="view-chat"><div id="chat-log"></div><textarea id="chat-input"></textarea><button id="chat-new"></button></section><input id="keep-history" type="checkbox" checked>'}));
  await page.goto('http://chat.test/');
  await page.evaluate(()=>{
   window.Axx={isNative:()=>true,newId:()=>crypto.randomUUID(),backendRequest:(method,url,body)=>url==='/axx-api/chat/operations'?Promise.resolve({operations:[{operation_id:'uncertain-restart',command_id:'axx.desktop.window.invoke',state:'unknown',postconditions_passed:false}]}):window.backend(method,url,body)};
   const data={messages:[{id:'legacy-message',role:'user',source:'model',status:'complete',text:'Legacy transcript',at:Date.now()}],draft:'Legacy draft',prefs:{keepHistory:true}};
   Axx.companion={data,save(){localStorage.setItem('legacy',JSON.stringify(this.data));},renderChat(){},cancelRequest(){},stopDictation(){},stopSpeech(){},renderAttachment(){},sayStatus(){},send(){},exportChat(){},brain:{async chat(p,m){return m;}}};
   Axx.commandLibrary={renderOperation(){},request:window.backend};
  });
  await page.addScriptTag({path:'1.AXX/scripts/chat-workspace.js'});
  await page.waitForFunction(()=>Axx.chatWorkspace?.ready&&Axx.chatWorkspace.active).catch(async e=>{console.log(await page.locator('#cw-error').textContent(),errors);throw e;});
  await page.waitForFunction(()=>Axx.commandLibrary.lastOperation?.operation_id==='uncertain-restart');
  assert.equal(await page.evaluate(()=>Axx.commandLibrary.operation),null);
  assert.match(await page.locator('#cw-operation').textContent(),/RESULTADO POR COMPROBAR/);
  assert.equal(await page.locator('#chat-input').inputValue(),'Legacy draft');
  const first=await page.evaluate(()=>Axx.chatWorkspace.active.id);
  await page.locator('#chat-input').fill('Private draft A');await page.click('#cw-new');
  await page.waitForFunction(id=>Axx.chatWorkspace.active.id!==id&&!Axx.chatWorkspace.busy,first);
  const second=await page.evaluate(()=>Axx.chatWorkspace.active.id);
  assert.equal(await page.locator('#chat-input').inputValue(),'');
  await page.evaluate(id=>Axx.chatWorkspace.select(id),first);
  assert.equal(await page.locator('#chat-input').inputValue(),'Private draft A');
  assert.equal(await page.evaluate(()=>Axx.companion.data.messages[0].text),'Legacy transcript');
  await page.evaluate(async()=>{const g=await Axx.backendRequest('POST','/axx-api/chat/group',{title:'Group'});await Axx.backendRequest('POST','/axx-api/chat/update',{id:Axx.chatWorkspace.active.id,group_id:g.id});await Axx.chatWorkspace.select(Axx.chatWorkspace.active.id);});
  await page.click('#cw-context-open');await page.fill('#cw-note','Curated group note');await page.click('#cw-add-note');
  await page.waitForFunction(()=>Axx.chatWorkspace.active.context.length===1);
  const sent=await page.evaluate(()=>Axx.companion.brain.chat({},[{role:'user',content:'Question'}]));assert.match(sent[0].content,/Curated group note/);
  await page.evaluate(id=>Axx.chatWorkspace.select(id),second);
  const privateSent=await page.evaluate(()=>Axx.companion.brain.chat({},[{role:'user',content:'Question'}]));assert.equal(privateSent[0].content,'Question');
  await page.click('#cw-context-open');await page.selectOption('#cw-link-source',first);await page.click('#cw-link-add');
  await page.waitForFunction(()=>Axx.chatWorkspace.active.links?.length===1);
  const linked=await page.evaluate(()=>Axx.companion.brain.chat({},[{role:'user',content:'Continue'}]));assert.match(linked[0].content,/Legacy transcript/);assert.doesNotMatch(linked[0].content,/Curated group note|Private draft/);
  await page.evaluate(()=>Axx.backendRequest('POST','/axx-api/chat/profile',{name:'Axx Test',instructions:'Use concise numbered answers',preferred_commands:['axx.system.telemetry']}));
  const configured=await page.evaluate(()=>Axx.companion.brain.chat({},[{role:'user',content:'Continue'}]));assert.equal(configured[0].role,'system');assert.match(configured[0].content,/Use concise numbered answers/);
  const ask=await page.evaluate(()=>Axx.commandLibrary.request('POST','/axx-api/commands/prepare',{command_id:'axx.system.telemetry',inputs:{},source:'text'}));assert.equal(ask.state,'awaiting_approval');
  await page.evaluate(op=>Axx.commandLibrary.renderOperation(op),ask);assert.equal(await page.locator('#cw-operation').isVisible(),true);
  await page.evaluate(id=>Axx.backendRequest('POST','/axx-api/commands/cancel',{operation_id:id}),ask.operation_id);
  await page.selectOption('#cw-mode','auto_safe');await page.waitForFunction(()=>Axx.chatWorkspace.active.mode==='auto_safe');
  const auto=await page.evaluate(()=>Axx.commandLibrary.request('POST','/axx-api/commands/prepare',{command_id:'axx.system.telemetry',inputs:{},source:'text'}));assert.equal(auto.state,'prepared');
  await page.evaluate(id=>Axx.backendRequest('POST','/axx-api/commands/cancel',{operation_id:id}),auto.operation_id);
  const forged=await page.evaluate(()=>Axx.backendRequest('POST','/axx-api/commands/prepare',{command_id:'axx.artifact.write',inputs:{path:'must-not-exist.txt',content:'x'},source:'text',conversation_id:Axx.chatWorkspace.active.id,command_mode:'auto_safe'}));assert.equal(forged.state,'awaiting_approval');
  assert.deepEqual(errors,[]);console.log('PASS: SQLite migration, per-chat drafts, navigation, curated context isolation, backend Ask/Auto policy and visible pending card');
 }finally{await browser?.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
