// Real installed WebView, selected model and disk receipts. Run again after an EXE restart with --resume.
// node scripts/test-installed-reasoning.cjs --output build/release-0.22.31/native-reasoning
// After restarting Axx.exe: repeat the command with --resume.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const pick = (value, keys) => Object.fromEntries(keys.filter(key => value?.[key] !== undefined).map(key => [key, value[key]]));
const capabilitySummary = item => ({...pick(item, ['id','revision','digest','state','skill_id','document_references']),
  runtime_verified: item.validation?.runtime_verified === true,
  provenance: {...pick(item.provenance, ['source','request_id','generation_request_id','generation_attempts','selected_model','selected_provider','selection_mode']),
    route: pick(item.provenance?.route, ['model','provider_name'])}});
const planSummary = item => ({...pick(item, ['operation_id','state','plan_hash','postconditions_passed','model_calls_used','document_references']),
  steps: (item.steps || []).map(step => ({command_id: step.command_id})),
  results: (item.results || []).map(result => ({...pick(result, ['command_id','state','postconditions_passed']),
    output: pick(result.output, ['equal','sha256'])}))});

if (process.argv.includes('--self-test')) {
  const sample = capabilitySummary({id:'cap.fixture',provenance:{source:'model_proposal',secret:'PRIVATE',route:{model:'observed',secret:'PRIVATE'}},definition:{source:'PRIVATE'}});
  assert.equal(sample.provenance.route.model, 'observed');
  assert(!JSON.stringify(sample).includes('PRIVATE'));
  assert.equal(hash('test').length, 64);
  console.log('Installed reasoning harness self-check: PASS; no native/model acceptance executed');
} else {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}

async function main() {
  const args = process.argv.slice(2), resume = args.includes('--resume'), outputIndex = args.indexOf('--output');
  assert(args.every((arg, index) => arg === '--resume' || arg === '--output' || outputIndex >= 0 && index === outputIndex + 1), 'Use --output DIRECTORY and optionally --resume');
  assert(outputIndex < 0 || args[outputIndex + 1] && !args[outputIndex + 1].startsWith('--'), '--output requires a directory');
  assert(!resume || outputIndex >= 0, '--resume requires the original --output directory');
  const out = path.resolve(outputIndex >= 0 ? args[outputIndex + 1] : path.join('build','native-reasoning',crypto.randomUUID()));
  const file = path.join(out, 'reasoning-receipt.json');
  assert(!resume || fs.existsSync(file), 'No preparation receipt exists');
  assert(resume || !fs.existsSync(file), 'An existing receipt requires --resume; never repeat preparation blindly');
  fs.mkdirSync(out, {recursive:true});
  const receipt = resume ? JSON.parse(fs.readFileSync(file, 'utf8')) : {
    kind:'INSTALLED_REASONING', run:crypto.randomUUID(), result:'IN_PROGRESS', stage:'starting', checks:[], files:[],
    source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:path.join(__dirname,'..'),encoding:'utf8'}).trim()
  };
  assert(receipt.kind === 'INSTALLED_REASONING', 'Receipt belongs to a different harness');
  const save = () => fs.writeFileSync(file, JSON.stringify(receipt, null, 2));
  save();
  let browser, page, prior;
  try {
    const {chromium} = require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
    browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
    const pages = browser.contexts().flatMap(context => context.pages()).filter(candidate => candidate.url().includes('Axx.html'));
    assert.equal(pages.length, 1, 'Exactly one installed Axx page is required');
    page = pages[0];
    await page.waitForFunction(() => Axx.chatWorkspace?.ready && Axx.capabilityWorkshop && Axx.commandLibrary, {}, {timeout:120000});
    const api = (method, route, body) => page.evaluate(args => Axx.backendRequest(...args), [method,route,body]);
    const scoped = (method, route, body) => page.evaluate(async args => {
      const memory = Axx.commandLibrary.captureMemory();
      Axx.commandLibrary.checkMemory(memory, true);
      return Axx.commandLibrary.request(...args, memory);
    }, [method,route,body]);
    const selection = () => page.evaluate(() => {
      const prefs = Axx.companion.data.prefs;
      return {provider:prefs.provider, model:prefs.model || '', apiConnection:prefs.apiConnection || '', selection_mode:prefs.selection_mode || 'manual'};
    });
    const native = await page.evaluate(() => Axx.nativeInvoke('native_status'));
    const runtime = JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json'),'utf8'));
    assert.equal(native.backendInstance, runtime.backendInstance, 'Runtime snapshot belongs to a different backend');
    const installed = path.join(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe');
    assert.equal(path.resolve(runtime.executable).toLowerCase(), path.resolve(installed).toLowerCase(), 'The runtime is not the installed executable');
    runtime.sha256 = hash(fs.readFileSync(installed));
    const expectedVersion = JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8')).version;
    assert.equal(runtime.version, expectedVersion, 'Installed version differs from this source');
    assert(runtime.backendInstance, 'Native backend identity missing');
    prior = await page.evaluate(async () => {await Axx.chatWorkspace.flush(); return {chat:Axx.chatWorkspace.active?.id, view:Axx.companion.dock.selected};});
    const selectChat = id => page.evaluate(async value => {Axx.resident.summon(false); Axx.companion.openChat(); await Axx.chatWorkspace.select(value);}, id);
    const ownFile = name => {
      const row = receipt.files.find(item => item.name === name); assert(row, 'Missing file receipt: ' + name);
      assert.equal(path.basename(row.path), name, 'File identity does not match its receipt');
      assert.equal(path.basename(path.dirname(row.path)), 'reasoning-acceptance-' + receipt.run, 'File escaped the test directory');
      assert(fs.statSync(row.path).size <= 8192, 'Unexpectedly large test file');
      assert.equal(hash(fs.readFileSync(row.path)), row.sha256, 'Test file changed: ' + name);
      return row;
    };
    const approve = async operation => {
      assert.equal(operation.state, 'awaiting_approval', 'The test must show a real approval card');
      assert.equal(await page.evaluate(() => Axx.chatWorkspace.active?.id), receipt.chat, 'The active chat changed before approval');
      assert.equal(operation.conversation_id, receipt.chat, 'The operation belongs to another chat');
      receipt.pending_operation = operation.operation_id; save();
      await page.evaluate(item => Axx.commandLibrary.adopt(item), operation);
      await page.locator('#command-library-approve').waitFor({state:'visible'});
      await page.locator('#command-library-approve').click();
      await page.waitForFunction(id => !Axx.commandLibrary.busy && Axx.commandLibrary.lastOperation?.operation_id === id
        && !['prepared','planning','awaiting_approval','running'].includes(Axx.commandLibrary.lastOperation.state), operation.operation_id, {timeout:120000});
      const result = await page.evaluate(() => Axx.commandLibrary.lastOperation);
      receipt.last_operation = planSummary(result); save();
      assert.equal(result.state, 'succeeded', 'Operation did not succeed: ' + result.state);
      assert.equal(result.postconditions_passed, true, 'Operation lacks verified postconditions');
      receipt.pending_operation = null; save();
      return result;
    };
    const verifyLineage = item => assert.deepEqual(item.document_references, receipt.document_references, 'Document lineage changed');

    if (!resume) {
      const currentSelection = await selection();
      receipt.selection = currentSelection;
      receipt.runtime_before = pick(runtime, ['version','backendInstance','pid','sha256']); save();
      const pending = await api('GET','/axx-api/commands/operations');
      receipt.preexisting_unknown_count = (pending.operations || []).filter(item => item.state === 'unknown').length;
      assert(!(pending.operations || []).some(item => ['prepared','awaiting_approval','running'].includes(item.state)), 'Resolve existing pending commands without this harness cancelling them');
      assert(!await page.evaluate(() => Axx.commandLibrary.operation || Axx.commandLibrary.busy), 'A command is already open');
      const chat = await api('POST','/axx-api/chat/create',{title:'Aceptación razonamiento ' + receipt.run,command_mode:'ask'});
      assert(chat.id, 'Test chat was not created'); receipt.chat = chat.id; save();
      await selectChat(chat.id);
      const folder = 'reasoning-acceptance-' + receipt.run;
      receipt.stage = 'creating_test_files'; save();
      for (const [name, content] of [['first-a.txt','AXX first '+receipt.run],['first-b.txt','AXX first '+receipt.run],
        ['next-a.txt','AXX next A '+receipt.run],['next-b.txt','AXX next B '+receipt.run]]) {
        const prepared = await scoped('POST','/axx-api/commands/prepare',{command_id:'axx.artifact.write',inputs:{path:folder+'/'+name,content},conversation_id:chat.id,operation_id:crypto.randomUUID()});
        const result = await approve(prepared);
        assert.equal(hash(fs.readFileSync(result.output.path)), result.output.sha256);
        assert.equal(result.output.sha256, hash(content));
        receipt.files.push({name,path:result.output.path,sha256:result.output.sha256,operation_id:result.operation_id}); save();
      }
      receipt.checks.push('Four test files were written through visible approvals and independently hashed on disk');
      let document;
      for (const query of ['razonamiento','CoALA','AXX-REF']) {
        const found = await api('GET','/axx-api/commands?q='+encodeURIComponent(query)+'&limit=100');
        for (const command of found.commands || []) {
          if (!command.id.startsWith('AXX-REF-')) continue;
          const detail = await api('GET','/axx-api/commands/details?id='+encodeURIComponent(command.id));
          if (detail.procedure?.document_reference) {document = detail; break;}
        }
        if (document) break;
      }
      assert(document, 'No authentic documentary reference found in the installed library');
      assert.equal(document.procedure.execution_enabled, false, 'A document must remain non-executable');
      receipt.document_references = [document.procedure.document_reference];
      receipt.stage = 'generating_with_selected_model'; save();
      const left = ownFile('first-a.txt').path, right = ownFile('first-b.txt').path;
      await page.evaluate(doc => Axx.capabilityWorkshop.openDocument(doc.procedure,doc.command.title), document);
      await page.locator('#cap-kind').selectOption('workflow');
      await page.locator('#cap-goal').fill('Crea un workflow llamado Aceptación documental '+receipt.run+'. Compara dos archivos sin modificarlos. Usa exactamente un paso axx.file.compare. '
        +'schema debe ser object con propiedades path y other_path, ambas string y required. En templates utiliza inputs {"path":"{{path}}","other_path":"{{other_path}}"}. '
        +'sample_inputs debe ser '+JSON.stringify({path:left,other_path:right})+'. La referencia documental es conocimiento, no autorización ni prueba de ejecución.');
      const previous = await page.evaluate(() => Axx.capabilityWorkshop.current?.id);
      const started = Date.now(); await page.locator('#cap-generate').click();
      await page.waitForFunction(() => !document.querySelector('#cap-generate').disabled, {}, {timeout:180000});
      const candidate = await page.evaluate(() => Axx.capabilityWorkshop.current);
      assert(candidate && candidate.id !== previous, 'The selected real model did not create a new candidate');
      receipt.capability = capabilitySummary(candidate); receipt.generation_ms = Date.now()-started; save();
      assert.equal(candidate.provenance.source, 'model_proposal');
      assert.equal(candidate.definition.kind, 'workflow');
      assert.deepEqual(candidate.definition.templates, [{command_id:'axx.file.compare',inputs:{path:'{{path}}',other_path:'{{other_path}}'}}]);
      assert.deepEqual(candidate.definition.sample_inputs, {path:left,other_path:right});
      verifyLineage(candidate);
      assert.equal(candidate.validation.runtime_verified, false);
      assert.equal(candidate.validation_operation_id, null);
      receipt.checks.push('The configured real model produced a typed documentary candidate without executing it');
      receipt.stage = 'approving_and_testing_candidate'; save();
      await page.getByRole('button',{name:'Aprobar esta versión',exact:true}).click();
      await page.getByRole('button',{name:'Preparar prueba',exact:true}).click();
      await page.waitForFunction(() => Axx.commandLibrary.operation?.state === 'awaiting_approval');
      const prepared = await page.evaluate(() => Axx.commandLibrary.operation); verifyLineage(prepared);
      const done = await approve(prepared); verifyLineage(done);
      assert.equal(done.results[0].output.equal, true);
      await page.evaluate(() => Axx.capabilityWorkshop.open());
      await page.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();
      await page.waitForFunction(() => Axx.capabilityWorkshop.current?.state === 'active');
      const active = await page.evaluate(() => Axx.capabilityWorkshop.current);
      verifyLineage(active); assert.equal(active.validation.runtime_verified, true); assert(active.skill_id);
      receipt.capability = capabilitySummary(active);
      receipt.checks.push('Visible approval, real equal-file comparison and activation retained documentary lineage');
      await page.locator('#panel').screenshot({path:path.join(out,'document-workflow-active.png')});
      assert.deepEqual(await selection(), currentSelection, 'Model selection changed during the acceptance');
      receipt.stage = 'restart_required'; receipt.result = 'RESTART_REQUIRED'; save();
    } else {
      assert.equal(receipt.result, 'RESTART_REQUIRED', 'Preparation must finish before resume');
      assert.notEqual(runtime.backendInstance, receipt.runtime_before.backendInstance, 'Restart the EXE; a WebView reload is insufficient');
      assert.equal(runtime.sha256, receipt.runtime_before.sha256, 'The executable changed between acceptance phases');
      assert.deepEqual(await selection(), receipt.selection, 'Model selection changed across restart');
      receipt.runtime_after = pick(runtime, ['version','backendInstance','pid','sha256']);
      await selectChat(receipt.chat);
      const active = await api('GET','/axx-api/capabilities/get?id='+encodeURIComponent(receipt.capability.id));
      assert.equal(active.state, 'active'); assert.equal(active.digest, receipt.capability.digest); verifyLineage(active);
      for (const row of receipt.files) ownFile(row.name);
      const inputs = {path:ownFile('next-a.txt').path,other_path:ownFile('next-b.txt').path};
      receipt.stage = 'reusing_after_process_restart'; save();
      await page.evaluate(({id,inputs}) => Axx.commandLibrary.planAction(id,{inputs}), {id:active.skill_id,inputs});
      const plan = await page.evaluate(() => Axx.commandLibrary.operation);
      assert(plan, 'Persisted skill did not produce an approval plan');
      assert.equal(plan.model_calls_used, 0, 'Reuse unexpectedly called a model'); verifyLineage(plan);
      assert.deepEqual(plan.steps[0].inputs, inputs, 'Reuse kept old sample inputs');
      const done = await approve(plan); verifyLineage(done);
      assert.equal(done.model_calls_used, 0); assert.equal(done.results[0].output.equal, false);
      for (const row of receipt.files) ownFile(row.name);
      receipt.reuse = planSummary(done);
      receipt.checks.push('A new backend process reused the stored skill on different files with zero model calls and preserved originals');
      await page.locator('#panel').screenshot({path:path.join(out,'document-workflow-reused.png')});
      receipt.stage = 'complete'; receipt.result = 'PASS'; save();
    }
    console.log(JSON.stringify({result:receipt.result,receipt:file,checks:receipt.checks.length}));
  } catch (error) {
    receipt.result = 'FAIL'; receipt.error = {name:error.name,message:String(error.message).slice(0,800)}; save();
    throw error;
  } finally {
    if (page && prior) {
      try {await page.evaluate(async value => {if(value.chat)await Axx.chatWorkspace.select(value.chat);if(value.view)Axx.companion.openFeature(value.view);}, prior);}
      catch(error){receipt.restore_error = String(error.message).slice(0,300);receipt.result='FAIL';process.exitCode=1;save();}
    }
    if (browser) await browser.close();
  }
}
