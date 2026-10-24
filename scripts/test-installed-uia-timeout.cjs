// Real WPF/UIA delayed provider against the installed host over temporary loopback CDP.
// The provider delays SetValue for 12 seconds and counts actual writes. No transport mocks.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process'),{createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const directory=path.resolve(process.argv[2] || 'build/installed-application-control');fs.mkdirSync(directory,{recursive:true});
 const out=path.join(directory,'slow-control.json');
 const framework=path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319');
 const executable=path.join(directory,'AxxSlowControl.exe');
 const references=['PresentationFramework','PresentationCore','WindowsBase','UIAutomationProvider','UIAutomationTypes'].map(name=>'/reference:'+path.join(framework,'WPF',name+'.dll'));
 execFileSync(path.join(framework,'csc.exe'),['/nologo','/target:winexe','/out:'+executable,'/reference:'+path.join(framework,'System.Xaml.dll'),...references,path.join(__dirname,'fixtures/SlowUiaControl.cs')],{windowsHide:true});
 const child=spawn(executable,[],{stdio:'ignore',windowsHide:true});
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('tauri.localhost/Axx.html'));
 const receipt={kind:'INSTALLED_NATIVE_UIA_DELAYED_PROVIDER',fixture_pid:child.pid,operations:[]};
 const api=(method,route,body)=>page.evaluate(({method,route,body})=>Axx.backendRequest(method,route,body),{method,route,body});
 const run=async(id,inputs,approved=false)=>{const p=await api('POST','/axx-api/commands/prepare',{command_id:id,inputs,source:'text'});return api('POST','/axx-api/commands/execute',{operation_id:p.operation_id,approved});};
 try{
  await delay(1000);
  const listed=await run('axx.desktop.list_windows',{});
  const target=listed.output.windows.find(w=>w.pid===child.pid);assert(target);
  const identity={window_id:'0x'+target.window_id.toString(16),pid:target.pid};
  const inspected=await run('axx.desktop.window.inspect',identity);
  const editor=inspected.output.controls.find(c=>c.automation_id==='axx-delayed-value'&&c.supports_value_pattern);assert(editor,JSON.stringify(inspected));
  const focused=await run('axx.desktop.window.focus',identity);assert.equal(focused.state,'succeeded');
  const value='Delayed effect verified exactly once';
  const started=Date.now();
  const uncertain=await run('axx.desktop.window.set_value',{...identity,control_id:editor.control_id,value},true);
  receipt.operations.push(uncertain);receipt.timeout_ms=Date.now()-started;
  assert.equal(uncertain.state,'unknown');assert(uncertain.evidence.reconciliation_required);
  assert.match(uncertain.error?.message||'',/excedió el límite/,'External input cancellation is not a timeout acceptance');
  assert(receipt.timeout_ms>=8000,'The real provider deadline must expire');
  const replay=await api('POST','/axx-api/commands/execute',{operation_id:uncertain.operation_id,approved:true});
  assert.equal(replay.state,'unknown');assert(replay.replayed);
  let blocked=false;try{await api('POST','/axx-api/commands/prepare',{command_id:'axx.desktop.window.set_value',inputs:{...identity,control_id:editor.control_id,value:'DO NOT DUPLICATE'},source:'text'});}catch{blocked=true;}assert(blocked);
  await delay(7000);
  const result=await api('POST','/axx-api/commands/reconcile',{operation_id:uncertain.operation_id});
  receipt.operations.push(result);assert.equal(result.state,'succeeded');assert(result.evidence.reconciled);
  assert.equal(fs.readFileSync(path.join(directory,'slow-control-writes.txt'),'utf8'),'1');
  receipt.checks=['Real provider blocked SetValue beyond worker deadline','Unknown result retained and duplicate write blocked','Late effect reconciled by readback','Fixture received exactly one SetValue'];
  receipt.result='PASS';console.log(JSON.stringify({result:receipt.result,checks:receipt.checks,timeout_ms:receipt.timeout_ms},null,2));
 }catch(e){receipt.result='FAIL';receipt.error=String(e);console.error(e);process.exitCode=1;}
 finally{fs.writeFileSync(out,JSON.stringify(receipt,null,2));child.kill();setTimeout(()=>process.exit(receipt.result==='PASS'?0:1),100);}
})().catch(e=>{console.error(e);process.exit(1)});
