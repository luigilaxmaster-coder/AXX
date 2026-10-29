// Real native IPC, resident scheduler and file readback; no physical input claim.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto'),{execFileSync}=require('node:child_process');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const run=crypto.randomUUID(),out=path.resolve(process.argv[2]||'build/anticipation-native',run);fs.mkdirSync(out,{recursive:true});
 const lock=path.join(process.env.LOCALAPPDATA,'Axx','.anticipation-acceptance.lock');
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page,'Axx native WebView must already be running');
 const api=(method,route,body)=>page.evaluate(args=>Axx.backendRequest(...args),[method,route,body]);
 const status=()=>api('POST','/axx-api/anticipation/status',{task_id:task});
 const prefix='native-anticipation-'+run,folder='acceptance-'+prefix;let task=prefix;
 const runtime=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx','logs','native-runtime.json')));
 const receipt={kind:'NATIVE_ANTICIPATION',physical_input_tested:false,visible_proposal_acceptance_tested:false,process_restart_tested:false,
  source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:path.join(__dirname,'..'),encoding:'utf8'}).trim(),
  source_status:execFileSync('git',['status','--short'],{cwd:path.join(__dirname,'..'),encoding:'utf8'}),
  runtime:{version:runtime.version,pid:runtime.pid,executable:runtime.executable,sha256:crypto.createHash('sha256').update(fs.readFileSync(runtime.executable)).digest('hex')},
  task_prefix:prefix,checks:[],latencies_ms:[]};
 let configured=false,locked=false,grant,view,savedChat;const grants=[],trials=[];
 async function scope(profile,suffix){
  const chat=await api('POST','/axx-api/chat/create',{title:prefix+' '+suffix});assert(chat.id,JSON.stringify(chat));
  task=chat.id;trials.push(task);const current=await status();
  await api('POST','/axx-api/anticipation/configure',{scopes:[...current.scopes.filter(s=>s.task_id!==task),{task_id:task,profile}]});configured=true;
  await page.evaluate(async id=>{Axx.resident.summon(false);Axx.companion.openFeature('chat');await Axx.chatWorkspace.select(id);},task);
 }
 async function waitFor(predicate){const deadline=Date.now()+16000;while(Date.now()<deadline){const value=await status();if(predicate(value))return value;await sleep(250);}throw Error('Resident anticipation did not reach its expected state');}
 async function write(name){
  const id=crypto.randomUUID(),content='Axx ensayo real '+name+' '+id;
  const prepared=await api('POST','/axx-api/commands/prepare',{command_id:'axx.artifact.write',inputs:{path:folder+'/'+name,content},operation_id:id,conversation_id:task});
  assert.equal(prepared.state,'awaiting_approval');
  const artifact=await api('POST','/axx-api/commands/execute',{operation_id:id,approved:true});
  assert.equal(artifact.state,'succeeded',JSON.stringify(artifact));assert.equal(artifact.postconditions_passed,true);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(artifact.output.path)).digest('hex'),artifact.output.sha256);
  return artifact;
 }
 try{
  const lockHandle=fs.openSync(lock,'wx');fs.writeFileSync(lockHandle,run);fs.closeSync(lockHandle);locked=true;
  assert(await page.evaluate(()=>!!Axx.anticipation),'Anticipation frontend must be installed');
  const operations=await api('GET','/axx-api/commands/operations');
  assert(!(operations.operations||[]).some(r=>['prepared','awaiting_approval','running'].includes(r.state)),'Resolve existing pending commands before native acceptance');
  assert.equal(runtime.version,JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'))).version,'Installed version must match this source');
  const initial=await status();assert(!initial.error,JSON.stringify(initial));
  assert(!initial.paused&&!initial.observation_paused&&initial.sources.events,'Enable the authorized event source before this isolated acceptance');
  for(const [name,mode] of [['discreto','OFF'],['copiloto','SUGGEST'],['full','EXECUTE']])assert.equal(initial.profiles[name].mode,mode,'This acceptance requires default profile policies');
  view=await page.evaluate(()=>Axx.companion.dock.selected);
  savedChat=await page.evaluate(async()=>{await Axx.chatWorkspace.flush();return Axx.chatWorkspace.active?.id;});
  await scope('discreto','discreto');
  const discreet=await write('discreto.txt');await sleep(6000);assert.equal((await status()).suggestions.length,0);
  receipt.checks.push({profile:'discreto',result:'Only the explicitly approved writer ran',artifact:discreet});
  await scope('copiloto','copiloto');
  const start=Date.now(),copilot=await write('copiloto.txt');
  const proposed=(await waitFor(s=>s.suggestions.some(r=>r.state==='AWAITING_APPROVAL'))).suggestions.find(r=>r.state==='AWAITING_APPROVAL');
  receipt.latencies_ms.push({stage:'copilot_proposal',value:Date.now()-start});
  assert(!(await api('GET','/axx-api/commands/operations')).operations.some(r=>r.operation_id===proposed.operation_id));
  await page.locator('#anticipation-card').getByRole('button',{name:'Verificar',exact:true}).waitFor({state:'visible'});
  await page.locator('#anticipation-card').screenshot({path:path.join(out,'native-copilot-proposal.png')});
  await page.locator('#anticipation-card').getByRole('button',{name:'Verificar',exact:true}).click();
  const accepted=(await waitFor(s=>s.suggestions.some(r=>r.suggestion_id===proposed.suggestion_id&&r.state==='VERIFIED'))).suggestions.find(r=>r.suggestion_id===proposed.suggestion_id);
  assert.equal(accepted.state,'VERIFIED',JSON.stringify(accepted));assert.equal(accepted.result.postconditions_passed,true);
  receipt.visible_proposal_acceptance_tested=true;
  assert.equal(accepted.result.output.files[0].sha256,copilot.output.sha256);
  const replay=await api('POST','/axx-api/anticipation/accept',{suggestion_id:proposed.suggestion_id,plan_hash:proposed.plan_hash});
  assert.equal(replay.result.operation_id,accepted.result.operation_id);
  receipt.checks.push({profile:'copiloto',result:'Exact accepted plan verified once',proposal:proposed,accepted,replay});
  await scope('full','full');
  grant=await api('POST','/axx-api/anticipation/grant',{task_id:task,capability:'verify_artifact',root:path.dirname(discreet.output.path),expires_at:null,observe_events:true});
  if(grant.grant_id)grants.push(grant.grant_id);
  assert(grant.grant_id,JSON.stringify(grant));
  const fullStart=Date.now(),full=await write('full.txt');
  const verified=(await waitFor(s=>s.suggestions.some(r=>r.state==='VERIFIED'&&r.plan.inputs.path===full.output.path))).suggestions.find(r=>r.plan.inputs.path===full.output.path);
  receipt.latencies_ms.push({stage:'full_autonomous_verification',value:Date.now()-fullStart});
  assert.equal(verified.result.output.files[0].sha256,full.output.sha256);
  assert.equal(verified.approval,'persistent');receipt.checks.push({profile:'full',result:'Resident scheduler verified under persistent scoped grant',verified});
  await page.reload();await page.waitForFunction(()=>Axx.chatWorkspace?.ready&&Axx.anticipation);
  assert((await status()).scopes.some(s=>s.task_id===task&&s.profile==='full'));receipt.checks.push({result:'Task Full policy persisted across native WebView reload'});
  await api('POST','/axx-api/anticipation/revoke',{grant_id:grant.grant_id});
  await scope('full','revoked');
  const revokedGrant=await api('POST','/axx-api/anticipation/grant',{task_id:task,capability:'verify_artifact',root:path.dirname(discreet.output.path),expires_at:null,observe_events:true});
  if(revokedGrant.grant_id)grants.push(revokedGrant.grant_id);
  await api('POST','/axx-api/anticipation/revoke',{grant_id:revokedGrant.grant_id});
  const revoked=await write('revocado.txt');
  const pending=(await waitFor(s=>s.suggestions.some(r=>r.plan.inputs.path===revoked.output.path))).suggestions.find(r=>r.plan.inputs.path===revoked.output.path);
  assert.equal(pending.state,'AWAITING_APPROVAL');receipt.checks.push({result:'Revoked grant did not execute the next initiative',pending});
  const stopped=await api('POST','/axx-api/anticipation/cancel',{suggestion_id:pending.suggestion_id});assert.equal(stopped.state,'CANCELLED');
  receipt.checks.push({result:'Stop cancelled only the trial initiative and retained prior effects'});
  await page.evaluate(()=>{Axx.resident.summon(false);Axx.companion.openFeature('settings');});
  await page.evaluate(()=>Axx.anticipation.refresh(true));
  await page.locator('#anticipation-settings').waitFor({state:'visible'});
  await page.locator('#anticipation-settings').scrollIntoViewIfNeeded();
  await page.locator('#panel').screenshot({path:path.join(out,'native-profile-settings.png')});
  receipt.result='PASS';
 }catch(error){receipt.result='FAIL';receipt.error=error.stack;throw error;}
 finally{
  try{
   for(const grant_id of grants)await api('POST','/axx-api/anticipation/revoke',{grant_id});
   if(configured){const current=await status();await api('POST','/axx-api/anticipation/configure',{scopes:current.scopes.filter(s=>!trials.includes(s.task_id))});}
   if(savedChat)await page.evaluate(id=>Axx.chatWorkspace.select(id),savedChat);
   for(const id of trials){await api('POST','/axx-api/anticipation/forget',{task_id:id});await api('POST','/axx-api/chat/delete',{id});}
   if(trials.length)await page.evaluate(()=>Axx.chatWorkspace.refresh());
   if(view)await page.evaluate(id=>Axx.companion.openFeature(id),view);
  }catch(error){receipt.cleanup_error=String(error);receipt.result='FAIL';process.exitCode=1;}
  finally{fs.writeFileSync(path.join(out,'installed-anticipation.json'),JSON.stringify(receipt,null,2),{flag:'wx'});await browser.close();if(locked&&fs.readFileSync(lock,'utf8')===run)fs.unlinkSync(lock);}
 }
 console.log(receipt.result+': native anticipation profiles, real file hashes, scoped grant, replay, WebView reload, revoke and trial stop');
})().catch(error=>{console.error(error);process.exitCode=1;});
