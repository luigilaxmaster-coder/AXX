// Run from repository root with the installed host temporarily exposing loopback CDP :9224.
// Uses scratch Notepad documents and test Explorer folders; never closes user Notepad tabs.
// Requires Python and Playwright in the same runtime used by the repository UI tests.
// Real installed WebView/native IPC, real Windows applications, no model or transport mocks.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process'),{createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const out=path.resolve(process.argv[2] || 'build/installed-application-control');fs.mkdirSync(out,{recursive:true});
 const runtime=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json')));
 assert.equal(runtime.version,require('../package.json').version);assert.equal(runtime.executable,path.join(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe'));
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');let page,originalChat,acceptanceChat;
 const receipt={kind:'INSTALLED_NATIVE_APPLICATION_ACCEPTANCE',version:runtime.version,pid:runtime.pid,checks:[],operations:[]};
 try{
  page=browser.contexts()[0].pages().find(p=>p.url().includes('tauri.localhost/Axx.html'));
  assert(page);page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.waitForFunction(()=>window.Axx?.windowContent&&Axx.commandLibrary&&!Axx.commandLibrary.busy);
  const readyDeadline=Date.now()+30000;let readyStatus;
  do{
   readyStatus=await page.evaluate(()=>Axx.nativeInvoke('native_status'));
   if(readyStatus?.backendReady===true)break;
   await wait(150);
  }while(Date.now()<readyDeadline);
  assert.equal(readyStatus?.backendReady,true,'Installed native host did not confirm backend readiness before the deadline');
  receipt.backendReady={ready:readyStatus.backendReady,instance:readyStatus.backendInstance};
  await page.waitForFunction(()=>Axx.chatWorkspace?.ready&&!Axx.chatWorkspace.busy);
  originalChat=await page.evaluate(()=>Axx.chatWorkspace.active.id);
  acceptanceChat=await page.evaluate(async()=>{const r=await Axx.backendRequest('POST','/axx-api/chat/create',{title:'Aceptación de control Windows',command_mode:'auto_safe'});await Axx.chatWorkspace.select(r.id);return r.id;});
  await page.evaluate(()=>{Axx.resident.summon(false);Axx.companion.openFeature('files');});await wait(1500);
  const run=async(id,inputs,approve=false)=>{
   await page.evaluate(async({id,inputs})=>Axx.commandLibrary.prepare(id,inputs,'text'),{id,inputs});
   let state=await page.evaluate(()=>Axx.commandLibrary.operation||Axx.commandLibrary.lastOperation);
   if(state.state==='awaiting_approval'){
    assert(approve,'Unexpected approval');assert.equal(state.postconditions_passed,false);
    await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
    await page.waitForFunction(()=>!Axx.commandLibrary.busy&&!Axx.commandLibrary.operation);
   }
   state=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
   receipt.operations.push(state);return state;
  };
  const verify=r=>{assert.equal(r.state,'succeeded',JSON.stringify(r));assert.equal(r.postconditions_passed,true);};
  const folderA=path.join(out,'folder-a'),folderB=path.join(out,'folder-b');fs.mkdirSync(folderA,{recursive:true});fs.mkdirSync(folderB,{recursive:true});
  await page.locator('#window-control-folder').fill(folderA);await page.locator('#window-control-open-folder').click();
  await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.command_id==='axx.desktop.explorer.folder'&&Axx.commandLibrary.lastOperation.state!=='preparing');
  const explorer=await page.evaluate(()=>Axx.commandLibrary.lastOperation);verify(explorer);receipt.operations.push(explorer);
  receipt.checks.push('Explorer folder and foreground read back from installed UI');
  execFileSync('python',['-c','import ctypes,sys;u=ctypes.WinDLL("user32");u.ShowWindowAsync.argtypes=[ctypes.c_void_p,ctypes.c_int];u.ShowWindowAsync(int(sys.argv[1]),6)',String(explorer.output.window_id)],{windowsHide:true});
  await page.evaluate(()=>Axx.nativeInvoke('window_action',{action:'open_panel'}));await wait(300);
  verify(await run('axx.desktop.window.focus',{window_id:'0x'+explorer.output.window_id.toString(16),pid:explorer.output.pid}));
  receipt.checks.push('Minimized Explorer restored and foreground verified');
  const scratch=path.join(out,'axx-installed-'+Date.now()+'.txt');fs.writeFileSync(scratch,'');
  spawn(path.join(process.env.SystemRoot,'System32/notepad.exe'),[scratch],{stdio:'ignore'}).unref();
  let target;
  for(let i=0;i<30;i++){
   const listed=await run('axx.desktop.list_windows',{});
   target=listed.output.windows.find(w=>w.title.includes(path.basename(scratch,'.txt')));
   receipt.operations.pop();if(target)break;await wait(100);
  }
  assert(target,'Scratch Notepad not observed');
  const value='Axx instalada: control verificado '+runtime.version;
  const written=await run('axx.desktop.notepad.text',{window_title:target.title,value},true);verify(written);
  receipt.checks.push('Notepad exact target approval and SHA256 readback');
  const replay=await page.evaluate(async id=>Axx.backendRequest('POST','/axx-api/commands/execute',{operation_id:id,approved:true}),written.operation_id);
  assert.equal(replay.operation_id,written.operation_id);assert(replay.replayed);verify(replay);
  receipt.checks.push('Same operation replay preserved receipt without repeating write');
  await page.evaluate(()=>Axx.commandLibrary.open());await page.locator('#command-library-remember').click();
  await page.waitForFunction(()=>document.getElementById('command-library-status').textContent.includes('Procedimiento parametrizado guardado'));
  const actions=await page.evaluate(()=>Axx.backendRequest('GET','/axx-api/learning/actions'));
  const skill=actions.actions.find(s=>s.provenance?.operation_id===written.operation_id);assert(skill);assert.equal(skill.status,'verified');
  assert.deepEqual(skill.templates[0].inputs,{window_title:'{{window_title}}',value:'{{value}}'});
  verify(await run('axx.desktop.notepad.text',{window_title:target.title,value:''},true));
  const secondScratch=path.join(out,'axx-installed-replay-'+Date.now()+'.txt');fs.writeFileSync(secondScratch,'');
  spawn(path.join(process.env.SystemRoot,'System32/notepad.exe'),[secondScratch],{stdio:'ignore'}).unref();
  target=null;
  for(let i=0;i<30;i++){
   const listed=await run('axx.desktop.list_windows',{});receipt.operations.pop();
   target=listed.output.windows.find(w=>w.title.includes(path.basename(secondScratch,'.txt')));
   if(target)break;await wait(100);
  }
  assert(target,'Second document not observed');
  await page.evaluate(async({id,title,value})=>Axx.commandLibrary.planAction(id,{inputs:{window_title:title,value}}),{id:skill.id,title:target.title,value:'Segundo texto parametrizado'});
  const plan=await page.evaluate(()=>Axx.commandLibrary.operation);
  assert.equal(plan.model_calls_used,0);assert.equal(plan.state,'awaiting_approval');
  await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
  await page.waitForFunction(()=>!Axx.commandLibrary.busy&&Axx.commandLibrary.lastOperation?.state==='succeeded');
  const repeat=await page.evaluate(()=>Axx.commandLibrary.lastOperation);verify(repeat);receipt.operations.push(repeat);
  assert.notEqual(repeat.results[0].output.control_id,written.output.control_id,'Procedure must resolve the new document control');
  receipt.checks.push('Verified parameterized procedure replayed via installed approval UI, zero model calls');
  const observed=await run('axx.desktop.cli_anything.scan',{window_id:'0x'+target.window_id.toString(16),pid:target.pid});verify(observed);
  assert(observed.output.total_controls>0);assert(observed.output.commands.inspect);assert(!observed.output.commands.click);
  assert(observed.output.controls.every(c=>!c.value&&!c.text),'Metadata discovery must not read document content');
  const field=observed.output.controls.find(c=>c.enabled&&!c.offscreen&&c.supports_value_pattern&&!c.read_only);assert(field);
  const proposal=await page.evaluate(async body=>Axx.backendRequest('POST','/axx-api/cli-anything/prepare',body),{target:'0x'+target.window_id.toString(16),command:'type',args:{control_id:field.control_id,text:'Must require new approval'},conversation_id:acceptanceChat});
  assert.equal(proposal.command_id,'axx.desktop.window.set_value');assert.equal(proposal.state,'awaiting_approval');
  await page.evaluate(async id=>Axx.backendRequest('POST','/axx-api/commands/cancel',{operation_id:id}),proposal.operation_id);
  receipt.checks.push('UIA discovery exposes metadata and exact registered proposals; writing still requires a separate approval');

  await page.evaluate(async({title})=>Axx.commandLibrary.prepare('axx.desktop.notepad.text',{window_title:title,value:'CANCELLED WRITE MUST NOT APPLY'},'text'),{title:target.title});
  const cancelledId=await page.evaluate(()=>Axx.commandLibrary.operation.operation_id);
  await page.locator('#cw-operation').getByRole('button',{name:'Aprobar y ejecutar',exact:true}).click();
  let ownerSeen=false;
  for(let i=0;i<40;i++){
   const status=await page.evaluate(()=>Axx.backendRequest('GET','/axx-api/mobile/control/status'));
   if(status.native.active&&status.native.source==='axx_automation'){ownerSeen=true;break;}
   await wait(10);
  }
  assert(ownerSeen,'Automation input ownership was not observed');
  execFileSync('python',['-c','import ctypes;ctypes.windll.user32.mouse_event(1,1,0,0,0)'],{windowsHide:true});
  await page.waitForFunction(()=>!Axx.commandLibrary.busy);
  const cancelled=await page.evaluate(()=>Axx.commandLibrary.lastOperation);
  assert.equal(cancelled.operation_id,cancelledId);assert.notEqual(cancelled.state,'succeeded');receipt.operations.push(cancelled);
  const stopped=await page.evaluate(()=>Axx.backendRequest('GET','/axx-api/mobile/control/status'));
  assert.equal(stopped.native.active,false);assert.deepEqual(stopped.native.keys,[]);assert.deepEqual(stopped.native.buttons,[]);
  receipt.checks.push('Foreign untagged Windows mouse event revoked installed owner and stopped pending flow (synthetic input, not physical hardware proof)');
  const inspected=await run('axx.desktop.window.inspect',{window_id:'0x'+target.window_id.toString(16),pid:target.pid});verify(inspected);
  const editor=inspected.output.controls.filter(c=>c.control_type==='ControlType.Document'&&c.enabled&&!c.offscreen&&c.supports_value_pattern);assert.equal(editor.length,1);
  await page.evaluate(()=>Axx.nativeInvoke('window_action',{action:'open_panel'}));await wait(300);
  const lost=await run('axx.desktop.window.set_value',{window_id:'0x'+target.window_id.toString(16),pid:target.pid,control_id:editor[0].control_id,value:'MUST NOT WRITE'},true);
  assert.notEqual(lost.state,'succeeded');receipt.checks.push('Write refused after loss of focus');
  // A pre-effect failure is not eligible for uncertain-effect reconciliation.
  const rejected=await page.evaluate(async id=>{try{return await Axx.backendRequest('POST','/axx-api/commands/reconcile',{operation_id:id});}catch(e){return {rejected:String(e)}}},lost.operation_id);
  assert(rejected.rejected);receipt.checks.push('Reconciliation rejected a known failed operation without repeating its write');
  verify(await run('axx.desktop.notepad.text',{window_title:target.title,value:''},true));
  execFileSync('python',['-c','import ctypes,sys;u=ctypes.WinDLL("user32");u.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t];u.PostMessageW(int(sys.argv[1]),16,0,0)',String(explorer.output.window_id)],{windowsHide:true});
  await wait(300);
  const stale=await run('axx.desktop.window.focus',{window_id:'0x'+explorer.output.window_id.toString(16),pid:explorer.output.pid});
  assert.notEqual(stale.state,'succeeded');receipt.checks.push('Closed Explorer window identity rejected');
  verify(await run('axx.desktop.explorer.folder',{path:folderB}));
  await page.evaluate(()=>Axx.companion.openFeature('files'));await page.locator('#window-content').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'installed-controls.png')});
  receipt.checks.push('Installed 3D surface and controls rendered');receipt.pageErrors=errors;assert.deepEqual(errors,[]);
  receipt.result='PASS';
 }catch(error){receipt.result='FAIL';receipt.error=String(error);if(page)await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw error;}
 finally{if(page&&originalChat){try{await page.evaluate(id=>Axx.chatWorkspace.select(id),originalChat);if(acceptanceChat)await page.evaluate(id=>Axx.backendRequest('POST','/axx-api/chat/delete',{id}),acceptanceChat);}catch(e){receipt.cleanupError=String(e);}}fs.writeFileSync(path.join(out,'native-acceptance.json'),JSON.stringify(receipt,null,2));setTimeout(()=>process.exit(receipt.result === 'PASS' ? 0 : 1),100);}
 console.log(JSON.stringify({result:receipt.result,checks:receipt.checks},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});


