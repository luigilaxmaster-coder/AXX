// Installed regression: a real, controlled read failure must not poison a later model request.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const pick = (value, keys) => Object.fromEntries(keys.filter(key => value?.[key] !== undefined).map(key => [key, value[key]]));
const summary = item => pick(item, ['operation_id','command_id','state','postconditions_passed','model_calls_used','lesson_dependencies','memory_forgotten']);
const requireOwnPath = (file, folder) => {
  assert.equal(path.basename(file), 'source.txt', 'Unexpected source filename');
  assert.equal(path.basename(path.dirname(file)), folder, 'Source is outside this test directory');
  assert(path.isAbsolute(file), 'Source must be the returned absolute artifact path');
};

if (process.argv.includes('--self-test')) {
  requireOwnPath(path.resolve('stale-test-fixture/source.txt'), 'stale-test-fixture');
  assert.throws(() => requireOwnPath(path.resolve('other/source.txt'), 'stale-test-fixture'));
  assert.throws(() => requireOwnPath(path.resolve('stale-test-fixture/other.txt'), 'stale-test-fixture'));
  assert(!JSON.stringify(summary({state:'failed', secret:'PRIVATE'})).includes('PRIVATE'));
  console.log('Installed stale-lesson harness self-check: PASS; no app or model used');
} else main().catch(error => {console.error(error.message); process.exitCode = 1;});

async function main() {
  const args = process.argv.slice(2);
  assert(args.length === 2 && args[0] === '--output' && !args[1].startsWith('--'), 'Use --output DIRECTORY');
  const out = path.resolve(args[1]), file = path.join(out, 'stale-lesson-receipt.json');
  assert(!fs.existsSync(file), 'Choose a fresh output directory; do not repeat a partial attempt blindly');
  fs.mkdirSync(out, {recursive:true});
  const run = crypto.randomUUID(), folder = 'stale-test-' + run, project = 'stale-project-' + run;
  const receipt = {kind:'INSTALLED_STALE_LESSON', run, result:'IN_PROGRESS', stage:'connect', checks:[],
    source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:path.join(__dirname,'..'),encoding:'utf8'}).trim(),
    fault_injection:'Harness temporarily renames only its own artifact after read preparation; no mock or SQL mutation.',
    private_audio_retained:false};
  const save = () => fs.writeFileSync(file, JSON.stringify(receipt, null, 2));
  const stage = value => {receipt.stage=value; save();};
  save();
  let browser, page, prior, original, held, originalHash;
  const restoreFile = () => {
    if (!held || !fs.existsSync(held)) return;
    requireOwnPath(original, folder);
    assert(!fs.existsSync(original), 'Never overwrite a replacement source while restoring the test');
    assert.equal(hash(fs.readFileSync(held)), originalHash, 'Held source changed');
    fs.renameSync(held, original);
    assert.equal(hash(fs.readFileSync(original)), originalHash);
    held = null;
  };
  try {
    const {chromium} = require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
    browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
    const pages = browser.contexts().flatMap(context => context.pages()).filter(candidate => candidate.url().includes('Axx.html'));
    assert.equal(pages.length, 1, 'Exactly one installed Axx page is required');
    page = pages[0];
    await page.waitForFunction(() => Axx.chatWorkspace?.ready && Axx.commandLibrary, {}, {timeout:120000});
    const api = (method, route, body) => page.evaluate(args => Axx.backendRequest(...args), [method,route,body]);
    const scoped = (route, body) => page.evaluate(async ({route,body,chat}) => {
      if (Axx.chatWorkspace.active?.id !== chat) throw Error('The active test chat changed');
      const memory = Axx.commandLibrary.captureMemory();
      Axx.commandLibrary.checkMemory(memory, true);
      return Axx.commandLibrary.request('POST',route,body,memory);
    }, {route,body,chat:receipt.chat});
    const selection = () => page.evaluate(() => {
      const prefs = Axx.companion.data.prefs;
      return {provider:prefs.provider,model:prefs.model || '',apiConnection:prefs.apiConnection || '',selection_mode:prefs.selection_mode || 'manual'};
    });
    const native = await page.evaluate(() => Axx.nativeInvoke('native_status'));
    const runtime = JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json'),'utf8'));
    assert.equal(native.backendInstance, runtime.backendInstance, 'Runtime snapshot belongs to another backend');
    const installed = path.join(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe');
    assert.equal(path.resolve(runtime.executable).toLowerCase(), path.resolve(installed).toLowerCase());
    assert.equal(runtime.version, JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8')).version);
    receipt.runtime = {...pick(runtime, ['version','backendInstance','pid']),sha256:hash(fs.readFileSync(installed))};
    prior = await page.evaluate(async () => {
      await Axx.chatWorkspace.flush();
      if (Axx.commandLibrary.operation || Axx.commandLibrary.busy) throw Error('Finish the current command first');
      return {chat:Axx.chatWorkspace.active?.id,view:Axx.companion.dock.selected};
    });
    receipt.selection = await selection(); save();
    const chat = await api('POST','/axx-api/chat/create',{title:'Aceptación lección obsoleta '+run,command_mode:'ask'});
    assert(chat.id); receipt.chat = chat.id; save();
    await page.evaluate(async id => {Axx.resident.summon(false);Axx.companion.openChat();await Axx.chatWorkspace.select(id);}, chat.id);
    const approve = async (operation, expected) => {
      assert.equal(operation.conversation_id, chat.id);
      assert.equal(operation.state, 'awaiting_approval');
      receipt.pending_operation = operation.operation_id; save();
      await page.evaluate(item => Axx.commandLibrary.adopt(item), operation);
      await page.locator('#command-library-approve').waitFor({state:'visible'});
      assert.equal(await page.evaluate(() => Axx.chatWorkspace.active?.id), chat.id);
      await page.locator('#command-library-approve').click();
      await page.waitForFunction(id => !Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.operation_id === id
        && !['prepared','planning','awaiting_approval','running'].includes(Axx.commandLibrary.lastOperation.state), operation.operation_id, {timeout:120000});
      const result = await page.evaluate(() => Axx.commandLibrary.lastOperation);
      receipt.last_operation = summary(result); save();
      assert.equal(result.state, expected);
      receipt.pending_operation = null; save();
      return result;
    };

    stage('own_artifact');
    const content = 'Owned stale-lesson acceptance source '+run;
    const write = await scoped('/axx-api/commands/prepare',{command_id:'axx.artifact.write',inputs:{path:folder+'/source.txt',content},
      conversation_id:chat.id,operation_id:crypto.randomUUID(),command_mode:'ask'});
    const created = await approve(write,'succeeded');
    assert.equal(created.postconditions_passed, true);
    original = created.output.path; originalHash = hash(content); requireOwnPath(original,folder);
    assert.equal(hash(fs.readFileSync(original)),originalHash);
    receipt.source = {path:original,sha256:originalHash,operation_id:created.operation_id}; save();

    stage('real_read_failure');
    const prepared = await scoped('/axx-api/commands/prepare',{command_id:'axx.file.sha256',inputs:{path:original},
      conversation_id:chat.id,operation_id:crypto.randomUUID(),command_mode:'ask'});
    held = original+'.held'; assert(!fs.existsSync(held)); assert.equal(hash(fs.readFileSync(original)),originalHash);
    fs.renameSync(original,held);
    const failure = await approve(prepared,'failed');
    assert.equal(failure.error?.code,'PRECONDITION_CHANGED');
    assert.equal(failure.postconditions_passed,false);
    receipt.failure = {...summary(failure),error_code:failure.error.code};
    restoreFile(); receipt.source_restored=true;
    receipt.checks.push('A real prepared read failed after a bounded, reversible rename of the harness-owned file'); save();

    stage('record_current_lesson');
    const context = await scoped('/axx-api/learning/context',{project_id:project,conversation_id:chat.id,changes:{
      current_file:original,context_meta:{current_file:{kind:'observed',source_id:'stale-source-'+run,task_id:chat.id,origin:'acceptance_file_receipt'}}}});
    const dependency = {project_id:project,field:'current_file',revision:context.context_meta.current_file.revision};
    const proposalText = 'Crea un archivo de texto nuevo llamado '+folder+'/planned-'+run+'.txt con exactamente este contenido: VALIDACION STALE '+run+'. No abras aplicaciones ni ejecutes otros cambios.';
    const hypothesis = proposalText+' Hipótesis de ensayo: la lectura falló durante un cambio controlado del recurso; no es una causa general demostrada.';
    assert(hypothesis.includes(proposalText));
    const lesson = await scoped('/axx-api/learning/lesson',{operation_id:failure.operation_id,project_id:project,task_id:chat.id,
      conversation_id:chat.id,hypothesis,context_dependencies:[dependency],allow_provider:true});
    assert.equal(lesson.cause_confirmed,false); assert.equal(lesson.source_operation_id,failure.operation_id);
    receipt.lesson_id=lesson.id; receipt.proposal_sha256=hash(proposalText); save();
    const query = '/axx-api/learning/lessons?project_id='+encodeURIComponent(project)+'&task_id='+encodeURIComponent(chat.id)+'&query='+encodeURIComponent(proposalText);
    const before = await api('GET',query);
    assert(before.lessons.some(item=>item.id===lesson.id && item.status==='reference'), 'The exact proposal text did not retrieve the original lesson');

    stage('stale_optional_lesson');
    await scoped('/axx-api/learning/context',{project_id:project,conversation_id:chat.id,changes:{
      current_file:original,context_meta:{current_file:{kind:'observed',source_id:'stale-source-revised-'+run,task_id:chat.id,origin:'acceptance_file_receipt'}}}});
    const after = await api('GET',query);
    const stale = after.lessons.find(item=>item.id===lesson.id);
    assert(stale && stale.status==='stale' && stale.context_matches===false, 'The old context revision must remain visible as stale');
    receipt.lesson_after = pick(stale,['id','status','context_matches','environment_matches']);
    receipt.checks.push('The exact future request retrieves the lesson, and a real context revision makes it stale without deleting it'); save();

    stage('real_model_planning');
    const selected=receipt.selection, started=Date.now();
    const plan = await scoped('/axx-api/learning/propose',{text:proposalText,operation_id:crypto.randomUUID(),project_id:project,conversation_id:chat.id,
      selection_mode:selected.selection_mode,model:selected.model,
      provider_name:selected.provider==='chatgpt'?'@codex':selected.provider==='bridge'?selected.apiConnection:''});
    receipt.planning = {...summary(plan),elapsed_ms:Date.now()-started}; save();
    if (plan.state==='awaiting_approval') {
      const cancelled = await scoped('/axx-api/learning/cancel',{operation_id:plan.operation_id});
      assert.equal(cancelled.state,'cancelled');
      receipt.planning_cancelled=true; save();
    }
    assert(plan.model_calls_used>0,'The fresh request did not reach a real model');
    assert.equal(plan.state,'awaiting_approval','The selected model did not produce a reviewable new plan');
    assert.notEqual(plan.memory_forgotten,true);
    assert.deepEqual(plan.lesson_dependencies,[],'The obsolete optional lesson was inherited');
    assert.deepEqual(await selection(),selected,'Model selection changed during acceptance');
    assert.equal(hash(fs.readFileSync(original)),originalHash);
    receipt.checks.push('A real model produced a new reviewable plan without inheriting the stale lesson; its unexecuted plan was then cancelled');
    receipt.result='PASS'; receipt.stage='complete'; save();
    console.log(JSON.stringify({result:receipt.result,receipt:file,checks:receipt.checks.length}));
  } catch(error) {
    receipt.result='FAIL'; receipt.error={name:error.name,message:String(error.message).slice(0,800)}; save();
    throw error;
  } finally {
    try {restoreFile();} catch(error) {receipt.restore_error=String(error.message).slice(0,400);receipt.result='FAIL';save();}
    if(page && prior) try {
      await page.evaluate(async value=>{if(value.chat)await Axx.chatWorkspace.select(value.chat);if(value.view)Axx.companion.openFeature(value.view);},prior);
    } catch(error) {receipt.restore_view_error=String(error.message).slice(0,300);save();}
    if(browser)await browser.close();
  }
}
