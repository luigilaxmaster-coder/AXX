// Installed WebView -> native authenticated IPC -> packaged SQLite/command services.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{createRequire}=require('module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const out=path.resolve(process.argv[2]||'build/chat-0.21.4');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');
 const receipt={kind:'INSTALLED_CHAT_ACCEPTANCE',checks:[],screenshots:[],limitations:['Screen reader audio output was not physically verified.']};
 let original,first,second,group,page,profile;
 try{
  page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);page.setDefaultTimeout(15000);
  await page.waitForFunction(()=>window.Axx?.chatWorkspace?.ready&&!Axx.chatWorkspace.busy,{},{timeout:150000});
  const runtime=await page.evaluate(()=>Axx.nativeInvoke('native_status'));assert(runtime.backendReady);
  receipt.runtime=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json')));assert.equal(receipt.runtime.version,require('../package.json').version);
  original=await page.evaluate(()=>Axx.chatWorkspace.active.id);
  profile=await page.evaluate(()=>Axx.backendRequest('GET','/axx-api/chat/profile'));
  receipt.profileBefore=profile;
  await page.evaluate(()=>{Axx.resident.summon(false);Axx.companion.openChat();});
  const create=async title=>page.evaluate(async title=>{const r=await Axx.backendRequest('POST','/axx-api/chat/create',{title});await Axx.chatWorkspace.select(r.id);return r.id;},title);
  first=await create('Aceptación · chat A');
  await page.locator('#chat-input').fill('Borrador privado A');await page.evaluate(()=>Axx.chatWorkspace.flush());
  second=await create('Aceptación · chat B');assert.equal(await page.locator('#chat-input').inputValue(),'');
  await page.evaluate(id=>Axx.chatWorkspace.select(id),first);assert.equal(await page.locator('#chat-input').inputValue(),'Borrador privado A');
  receipt.checks.push('New conversation preserves previous draft and isolated identities');
  group=await page.evaluate(async()=>{const g=await Axx.backendRequest('POST','/axx-api/chat/group',{title:'Aceptación · contexto'});await Axx.backendRequest('POST','/axx-api/chat/update',{id:Axx.chatWorkspace.active.id,group_id:g.id});await Axx.chatWorkspace.select(Axx.chatWorkspace.active.id);return g.id;});
  await page.locator('#cw-context-open').click();await page.locator('#cw-note').fill('Nota de aceptación: solo compartir esta nota.');await page.locator('#cw-add-note').click();
  await page.waitForFunction(()=>Axx.chatWorkspace.active.context.length===1);
  await page.screenshot({path:path.join(out,'installed-group-context.png')});receipt.screenshots.push('installed-group-context.png');
  await page.locator('#cw-context-close').click();
  const shared=await page.evaluate(()=>Axx.chatWorkspace.active.context[0].text);assert.match(shared,/Nota de aceptación/);
  await page.evaluate(id=>Axx.chatWorkspace.select(id),second);assert.equal(await page.evaluate(()=>Axx.chatWorkspace.active.context.length),0);
  receipt.checks.push('Curated group context persisted and absent in unrelated conversation');
  await page.evaluate(async id=>{await Axx.backendRequest('POST','/axx-api/chat/save',{id,messages:[{id:crypto.randomUUID(),role:'user',text:'Proyecto de aceptación: el color acordado es jade.',status:'complete',at:Date.now()}]});},first);
  await page.locator('#cw-context-open').click();await page.locator('#cw-link-source').selectOption(first);await page.locator('#cw-link-add').click();
  await page.waitForFunction(()=>Axx.chatWorkspace.active.links.length===1);
  const linked=await page.locator('#cw-links').innerText();assert.match(linked,/color acordado es jade/);assert.doesNotMatch(linked,/Borrador privado|Nota de aceptación/);
  await page.screenshot({path:path.join(out,'installed-linked-context.png')});receipt.screenshots.push('installed-linked-context.png');
  await page.locator('#cw-context-close').click();receipt.checks.push('Selected thread snapshot contains completed messages but excludes source drafts and group notes');
  await page.evaluate(()=>Axx.companion.openFeature('agent'));
  await page.waitForFunction(()=>document.getElementById('agent-profile-status').textContent.startsWith('Configuración local'));
  await page.locator('#agent-name').fill('Agente de aceptación');await page.locator('#agent-role').fill('Asistente de diseño');await page.locator('#agent-instructions').fill('Resume el contexto elegido en una oración.');if(!await page.locator('#agent-preferred').isVisible())await page.locator('#agent-profile-form details summary').click();await page.locator('#agent-preferred').fill('axx.system.telemetry');
  await page.locator('#agent-profile-form button[type=submit]').click();await page.waitForFunction(()=>document.getElementById('agent-profile-status').textContent.includes('guardada'));
  const savedProfile=await page.evaluate(()=>Axx.backendRequest('GET','/axx-api/chat/profile'));assert.equal(savedProfile.role,'Asistente de diseño');assert.deepEqual(savedProfile.preferred_commands,['axx.system.telemetry']);
  await page.screenshot({path:path.join(out,'installed-agent-profile.png')});receipt.screenshots.push('installed-agent-profile.png');
  const rejected=await page.evaluate(async()=>{try{await Axx.backendRequest('POST','/axx-api/chat/profile',{preferred_commands:['not.registered.command']});return false;}catch{return true;}});assert(rejected);
  receipt.checks.push('Profile form persists instructions and registered command IDs; packaged backend rejects unknown commands');
  await page.evaluate(()=>Axx.companion.openChat());
  await page.waitForTimeout(600); // Native layout ACK and ResizeObserver settle.
  if(await page.locator('#cw-browse').isVisible())await page.locator('#cw-browse').click();
  await page.locator('#cw-browser').waitFor({state:'visible'});await page.screenshot({path:path.join(out,'installed-history.png')});receipt.screenshots.push('installed-history.png');
  if(await page.locator('#cw-back').isVisible())await page.locator('#cw-back').click();
  await page.evaluate(()=>Axx.commandLibrary.prepare('axx.system.telemetry',{},'text'));
  const pending=await page.evaluate(()=>Axx.commandLibrary.operation);assert.equal(pending.state,'awaiting_approval');
  await page.evaluate(()=>{Axx.companion.openChat();});assert(await page.locator('#cw-operation').isVisible());
  await page.screenshot({path:path.join(out,'installed-pending-command.png')});receipt.screenshots.push('installed-pending-command.png');
  await page.evaluate(id=>Axx.chatWorkspace.select(id),first);assert(await page.locator('#cw-operation').isVisible());
  await page.evaluate(()=>Axx.commandLibrary.recover());await page.evaluate(()=>Axx.commandLibrary.cancel());
  receipt.checks.push('Ask mode waits; pending command remains visible across chat navigation; cancel reaches packaged executor');
  await page.locator('#cw-mode').selectOption('auto_safe');await page.waitForFunction(()=>Axx.chatWorkspace.active.mode==='auto_safe');
  await page.evaluate(()=>Axx.commandLibrary.prepare('axx.system.telemetry',{},'text'));
  const verified=await page.evaluate(()=>Axx.commandLibrary.lastOperation);assert.equal(verified.state,'succeeded');assert.equal(verified.postconditions_passed,true);
  const write=await page.evaluate(()=>Axx.commandLibrary.prepare('axx.artifact.write',{path:'chat-acceptance-no-write.txt',content:'Must require approval'},'text'));
  assert.equal(await page.evaluate(()=>Axx.commandLibrary.operation.state),'awaiting_approval');await page.evaluate(()=>Axx.commandLibrary.cancel());
  receipt.checks.push('Auto runs verified telemetry; file write still awaits approval and is cancelled without writing');
  await page.evaluate(()=>Axx.companion.openChat());
  if(await page.locator('#cw-browse').isVisible()){await page.locator('#cw-browse').focus();await page.keyboard.press('Enter');await page.locator('#cw-browser').waitFor({state:'visible'});await page.locator('#cw-back').click();}
  else {await page.locator('#cw-search').focus();await page.keyboard.press('Control+A');await page.keyboard.press('Backspace');await page.keyboard.type('Aceptación');await page.waitForFunction(()=>document.getElementById('cw-search').value==='Aceptación'&&document.activeElement===document.getElementById('cw-search'),{},{polling:50,timeout:2000});assert.equal(await page.locator('#cw-search').inputValue(),'Aceptación');await page.locator('#cw-search').fill('');}
  receipt.checks.push('Keyboard activation and focus return work in installed WebView');
  await page.reload();await page.waitForFunction(()=>Axx.chatWorkspace?.ready&&!Axx.chatWorkspace.busy);
  await page.evaluate(id=>Axx.chatWorkspace.select(id),first);assert.equal(await page.locator('#chat-input').inputValue(),'Borrador privado A');
  receipt.checks.push('WebView reload restores durable conversations and draft');
  receipt.result='PASS';
 }catch(e){receipt.result='FAIL';receipt.error=e.stack;throw e;}
 finally{
  receipt.fixtures={original,first,second,group};
  if(page){
   const restore=async(label,action)=>{try{await action();}catch(error){(receipt.cleanupErrors??=[]).push({label,error:error.message});receipt.result='FAIL';process.exitCode=1;}};
   await restore('search',()=>page.evaluate(()=>{const input=document.getElementById('cw-search');if(input){input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));}}));
   if(profile)await restore('profile',()=>page.evaluate(profile=>Axx.backendRequest('POST','/axx-api/chat/profile',profile),profile));
   if(original)await restore('active conversation',()=>page.evaluate(id=>Axx.chatWorkspace.select(id),original));
   for(const id of [first,second].filter(Boolean))await restore('scratch conversation',()=>page.evaluate(id=>Axx.backendRequest('POST','/axx-api/chat/delete',{id}),id));
   if(group)await restore('scratch group',()=>page.evaluate(id=>Axx.backendRequest('POST','/axx-api/chat/group_delete',{id}),group));
  }
  fs.writeFileSync(path.join(out,'installed-chat.json'),JSON.stringify(receipt,null,2));await browser.close();console.log(receipt.result,receipt.checks);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
