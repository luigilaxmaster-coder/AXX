// Installed WebView -> authenticated IPC -> packaged executor and native UIA.
// Screenshots/receipts stay private under build/. No provider calls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const directory=path.resolve(process.argv[2]||'build/release-0.21.13');fs.mkdirSync(directory,{recursive:true});
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);
 const receipt={kind:'INSTALLED_UNIFIED_EXECUTION',checks:[],operations:[]};let fixture,previous;
 const api=(method,route,body)=>page.evaluate(args=>Axx.backendRequest(...args),[method,route,body]);
 const run=async(command_id,inputs,delivery_mode='background')=>{
  const pending=await api('POST','/axx-api/commands/prepare',{command_id,inputs,delivery_mode});
  const result=await api('POST','/axx-api/commands/execute',{operation_id:pending.operation_id,approved:true});
  receipt.operations.push(result);return result;
 };
 try{
  await page.waitForFunction(()=>Axx.commandLibrary&&Axx.chatWorkspace?.ready&&!Axx.commandLibrary.busy,{},{timeout:90000});
  receipt.runtime=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json'),'utf8'));
  assert.equal(receipt.runtime.version,require('../package.json').version);
  previous=await page.evaluate(()=>({view:Axx.companion.dock.selected,query:document.getElementById('command-library-query').value}));
  await page.evaluate(async()=>{Axx.resident.summon(false);Axx.commandLibrary.open();await Axx.commandLibrary.search('axx.architecture.status');});
  assert.equal(await page.locator('#command-delivery-mode').inputValue(),'background');
  receipt.modes=await page.locator('#command-delivery-mode option').evaluateAll(options=>options.map(o=>({value:o.value,disabled:o.disabled,label:o.textContent})));
  assert(receipt.modes.find(o=>o.value==='isolated')?.disabled,JSON.stringify(receipt.modes));
  await page.locator('#command-library-prepare').click();
  await page.waitForFunction(()=>!Axx.commandLibrary.busy&&['awaiting_approval','succeeded'].includes(Axx.commandLibrary.lastOperation?.state));
  if(await page.evaluate(()=>Axx.commandLibrary.operation?.state==='awaiting_approval')){
   await page.locator('#command-library-approve').click();
   await page.waitForFunction(()=>!Axx.commandLibrary.busy&&!Axx.commandLibrary.operation);
  }
  const inventory=await page.evaluate(()=>Axx.commandLibrary.lastOperation);assert.equal(inventory.state,'succeeded');
  assert(inventory.output.components.some(c=>c.id==='isolated_desktop'&&c.state==='unavailable'));
  receipt.operations.push(inventory);receipt.checks.push('Visible execution-mode selector and native inventory command');
  await page.locator('#command-library').screenshot({path:path.join(directory,'installed-command-modes.png')});
  let rejected=false;
  try{await api('POST','/axx-api/commands/prepare',{command_id:'axx.desktop.open_app',inputs:{app:'calculator'},delivery_mode:'background'});}catch(error){rejected=String(error).includes('background_unavailable');}
  assert(rejected);receipt.checks.push('Unsupported background launch rejected through installed IPC');
  const framework=path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319');
  const executable=path.join(directory,'UnifiedControl.exe');
  const references=['PresentationFramework','PresentationCore','WindowsBase'].map(name=>'/reference:'+path.join(framework,'WPF',name+'.dll'));
  execFileSync(path.join(framework,'csc.exe'),['/nologo','/target:winexe','/out:'+executable,'/reference:'+path.join(framework,'System.Xaml.dll'),...references,path.join(__dirname,'fixtures/UnifiedControl.cs')],{windowsHide:true});
  fixture=spawn(executable,[],{windowsHide:true,stdio:'ignore'});await sleep(1000);
  const listed=await run('axx.desktop.list_windows',{});const target=listed.output.windows.find(w=>w.pid===fixture.pid);assert(target);
  const identity={window_id:'0x'+target.window_id.toString(16),pid:target.pid};
  const processInfo=await run('axx.process.inspect',{pid:target.pid});
  let selected;
  for(const [name,status] of [['Confirmar','selected'],['Duplicado','ambiguous'],['Ausente','not_found']]){
   const result=await run('axx.desktop.window.find',{...identity,name});assert.equal(result.state,'succeeded');
   assert.equal(result.output.selection_status,status);assert.equal(result.output.observation.process_started,processInfo.output.process_started);
   if(status==='selected')selected=result.output;
  }
  const invoked=await run('axx.desktop.window.invoke',{...identity,control_id:selected.candidate.control_id,
   expected_title:selected.window_title,expected_name:'Confirmar'},'foreground');
  assert.equal(invoked.state,'unknown');assert.equal(invoked.dispatch_status,'delivered');assert.equal(invoked.postconditions_passed,false);
  const observed=await run('axx.desktop.window.read',{...identity,expected_title:selected.window_title});
  assert.equal(observed.state,'succeeded');assert(observed.output.text.includes('Confirmado'));
  receipt.checks.push('Real button effect observed independently; generic dispatch receipt remains uncertain');
  const file=await run('axx.artifact.write',{path:'unified-acceptance-'+Date.now()+'.txt',content:'Installed unified execution verified'});
  assert.equal(file.state,'succeeded');assert.equal(file.effect_status,'confirmed');assert(file.postconditions_passed);
  receipt.checks.push('Packaged UIA selected/abstained on real WPF controls and matched process instance');
  receipt.checks.push('Packaged executor created and hash-verified an actual file in its workspace');
  receipt.result='PASS';console.log(JSON.stringify({result:receipt.result,checks:receipt.checks},null,2));
 }catch(error){receipt.result='FAIL';receipt.error=String(error);console.error(error);process.exitCode=1;}
 finally{
  fixture?.kill();
  if(previous)await page.evaluate(async p=>{await Axx.commandLibrary.search(p.query);if(p.view)Axx.companion.openFeature(p.view);},previous).catch(()=>{});
  fs.writeFileSync(path.join(directory,'installed-unified.json'),JSON.stringify(receipt,null,2));
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exit(1)});
