// Real WebView -> authenticated Axx IPC -> shared native input owner/UIA.
// Usage: node scripts/test-installed-computer-use.cjs [receipt-parent] [--source]
// Requires Axx already running with WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
// "--remote-debugging-port=9224" and its real renderer/material heartbeat active.
// Keep physical input idle during the foreground section; Escape remains live.
// This script never launches/restarts Axx, submits provider calls, or fakes leases.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require(process.env.USERPROFILE + '/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');

(async () => {
  const mode = process.argv.includes('--source') ? 'source' : 'installed';
  const parent = path.resolve(process.argv.slice(2).find(arg => !arg.startsWith('--')) || 'build/computer-use-acceptance');
  fs.mkdirSync(parent, { recursive: true });
  const directory = fs.mkdtempSync(path.join(parent, 'run-'));
  const receipt = { kind: 'COMPUTER_USE_ACCEPTANCE', mode, started_at: new Date().toISOString(), checks: [], operations: [] };
  let browser, page, fixture, previous;
  const check = text => { receipt.checks.push(text); console.log('PASS: ' + text); };
  try {
    browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
    page = browser.contexts()[0].pages().find(candidate => candidate.url().includes('Axx.html'));
    assert(page, 'No native Axx WebView is attached to CDP 9224');
    await page.waitForFunction(() => window.Axx?.commandLibrary && Axx.chatWorkspace?.ready && !Axx.commandLibrary.busy, {}, { timeout: 90000 });
    receipt.webview_url = page.url();
    if (mode === 'installed') {
      receipt.runtime = JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA, 'Axx/logs/native-runtime.json'), 'utf8'));
      assert.equal(receipt.runtime.version, require('../package.json').version, 'Installed runtime version differs from source');
    }
    const api = (method, route, body) => page.evaluate(args => Axx.backendRequest(...args), [method, route, body]);
    const run = async (command_id, inputs, delivery_mode = 'background') => {
      const prepared = await api('POST', '/axx-api/commands/prepare', { command_id, inputs, delivery_mode });
      const result = await api('POST', '/axx-api/commands/execute', { operation_id: prepared.operation_id, approved: true });
      receipt.operations.push({ command_id, inputs, result });
      return result;
    };
    const succeeded = (operation, label) => {
      assert.equal(operation.state, 'succeeded', label + ': ' + JSON.stringify(operation));
      assert.equal(operation.postconditions_passed, true, label + ' lacks verified postconditions');
      return operation.output;
    };
    const nativeState = () => api('GET', '/axx-api/mobile/control/status');
    previous = await page.evaluate(() => ({ view: Axx.companion.dock.selected }));
    await page.evaluate(() => { Axx.resident.summon(false); });
    // Only observe the real application's polling loop. Never POST control/material.
    for (let attempt = 0; attempt < 20; attempt++) {
      receipt.native_before = await nativeState();
      if (receipt.native_before.native?.material_key) break;
      await sleep(500);
    }
    assert(receipt.native_before.native?.material_key, 'Axx renderer has not synchronized its actual input indicator');
    assert.equal(receipt.native_before.native.active, false, 'Another input lease is active; acceptance must not revoke it');
    check('Real renderer material available and shared input owner initially idle');

    const framework = path.join(process.env.SystemRoot, 'Microsoft.NET/Framework64/v4.0.30319');
    const executable = path.join(directory, 'ComputerUse.exe');
    const references = ['PresentationFramework', 'PresentationCore', 'WindowsBase'].map(name => '/reference:' + path.join(framework, 'WPF', name + '.dll'));
    execFileSync(path.join(framework, 'csc.exe'), ['/nologo', '/target:winexe', '/out:' + executable,
      '/reference:' + path.join(framework, 'System.Xaml.dll'), ...references, path.join(__dirname, 'fixtures/ComputerUse.cs')], { windowsHide: true });
    fixture = spawn(executable, [], { windowsHide: true, stdio: 'ignore' });
    let target;
    for (let attempt = 0; attempt < 20; attempt++) {
      await sleep(250);
      const listed = succeeded(await run('axx.desktop.list_windows', {}), 'List windows');
      target = listed.windows.find(row => row.pid === fixture.pid && row.title === 'Axx Computer Use Acceptance');
      if (target) break;
      assert(fixture.exitCode === null, 'The owned WPF fixture exited before discovery');
    }
    assert(target, 'Owned fixture window not found');
    const identity = { window_id: target.window_id, pid: target.pid };
    const legacyIdentity = { window_id: '0x' + target.window_id.toString(16), pid: target.pid };
    const title = target.title;
    const selected = succeeded(await run('axx.desktop.window.select', {title}), 'Select exact fixture window');
    assert.equal(selected.window_id, identity.window_id); assert.equal(selected.pid, identity.pid);
    assert.equal(parseInt(selected.window_id_hex,16),identity.window_id);
    receipt.fixture = { ...identity, executable, sha256: sha(executable) };
    const focus = async () => succeeded(await run('axx.desktop.window.focus', legacyIdentity, 'foreground'), 'Focus owned fixture');
    const find = async (name, pattern) => succeeded(await run('axx.desktop.control.find', { ...identity, name, pattern }), 'Find ' + name);
    const setState = async (found, pattern, value) => succeeded(await run('axx.desktop.state', {
      ...identity, observation_id: found.observation_id, control_id: found.control_id, pattern, state: { value }
    }, 'foreground'), 'Set ' + pattern);
    const geometry = async () => succeeded(await run('axx.desktop.window.observe', identity), 'Observe window geometry');
    const state = async (observation, action) => succeeded(await run('axx.desktop.window.state', {
      ...identity, observation_id: observation.observation_id, action
    }, 'foreground'), 'Window ' + action);
    await focus();
    const processInfo = succeeded(await run('axx.process.inspect', { pid: fixture.pid }), 'Inspect fixture identity');
    const toggle = await find('Enabled', 'Toggle');
    assert.equal(toggle.observation.process_started, processInfo.process_started);
    const toggled = await setState(toggle, 'Toggle', true);
    assert.equal(toggled.after.Toggle, 'On');
    const initialText = 'Valor verificado: áéíóú';
    const valueResult = await setState(await find('Editor', 'Value'), 'Value', initialText);
    assert.equal(valueResult.value_sha256, createHash('sha256').update(initialText, 'utf8').digest('hex'));
    check('Fresh Toggle and Value UIA states verified against the same live process instance');

    // A genuine previous observation becomes invalid when the window is minimized.
    const staleToggle = await find('Enabled', 'Toggle');
    assert.equal((await state(await geometry(), 'minimize')).minimized, true);
    const rejected = await run('axx.desktop.state', { ...identity, observation_id: staleToggle.observation_id,
      control_id: staleToggle.control_id, pattern: 'Toggle', state: { value: false } }, 'foreground');
    assert.equal(rejected.state, 'failed', 'Stale observation must fail before dispatch');
    assert.equal(rejected.postconditions_passed, false);
    assert.notEqual(rejected.dispatch_status, 'delivered');
    const minimized = await geometry();
    assert.equal(minimized.quality, 'geometry_only');
    assert.equal(minimized.state.minimized, true);
    assert.equal(minimized.ui_content_status, 'not_observed');
    assert.equal((await state(minimized, 'restore')).minimized, false);
    await focus();
    const afterRestore = await find('Enabled', 'Toggle');
    assert.equal(afterRestore.controls.find(control => control.control_id === afterRestore.control_id).state.Toggle, 'On');
    check('Minimize/readback, stale-token rejection before effect, and geometry-only restore verified');

    await setState(await find('Editor', 'Value'), 'Value', '');
    const editorFound = await find('Editor', 'Value');
    const editor = editorFound.controls.find(control => control.control_id === editorFound.control_id);
    assert(editor?.bounds?.width > 0 && editor.bounds.height > 0);
    const point = { x: Math.round(editor.bounds.x + editor.bounds.width / 2), y: Math.round(editor.bounds.y + editor.bounds.height / 2) };
    const moved = succeeded(await run('axx.desktop.input', { ...identity, observation_id: editorFound.observation_id,
      action: 'move', ...point }, 'foreground'), 'Broker cursor move');
    assert.equal(moved.confirmed, true);
    let cursor;
    for (let attempt = 0; attempt < 10; attempt++) {
      cursor = await nativeState();
      if (cursor.native.cursor.x === point.x && cursor.native.cursor.y === point.y) break;
      await sleep(50); // Snapshot publication can follow the completed owner command.
    }
    assert.deepEqual(cursor.native.cursor, point, 'Independent owner snapshot must match real cursor position');
    check('Cursor moved through synchronized shared broker and matched independent native snapshot');
    // Focus was assigned by the fixture's normal activation behavior, then observed.
    const beforeTyping = await find('Editor', 'Value');
    assert.equal(beforeTyping.focused_control_id, beforeTyping.control_id, 'Editor must own observed keyboard focus');
    const typedText = 'Axx entrada real áéíóú 2026';
    const typed = await run('axx.desktop.input', { ...identity, observation_id: beforeTyping.observation_id,
      action: 'type_text', text: typedText }, 'foreground');
    assert.equal(typed.state, 'unknown');
    assert.equal(typed.dispatch_status, 'delivered');
    assert.equal(typed.postconditions_passed, false);
    const read = succeeded(await run('axx.desktop.window.read', { ...legacyIdentity, expected_title: title }), 'Independent UIA text read');
    assert.equal(read.controls.find(control => control.automation_id === 'editor')?.value, typedText);
    const released = await nativeState();
    assert.equal(released.native.active, false);
    assert.deepEqual(released.native.keys, []);
    assert.deepEqual(released.native.buttons, []);
    receipt.native_after = released;
    check('Unicode SendInput receipt stayed unknown; independent UIA read confirmed exact text and owner released input');
    const reviewed = await api('POST','/axx-api/commands/review',{operation_id:typed.operation_id,reviewed:true});
    assert.equal(reviewed.state,'unknown');assert.equal(reviewed.postconditions_passed,false);assert.equal(reviewed.evidence.manual_reviewed,true);
    await focus();
    const reviewedObservation = await find('Editor','Value');
    succeeded(await run('axx.desktop.input',{...identity,observation_id:reviewedObservation.observation_id,action:'move',...point},'foreground'),'New cursor action after explicit fixture review');
    check('Explicit review preserved uncertainty and unlocked a separately prepared fresh action without replay');

    const sources = path.join(directory, 'sources'); fs.mkdirSync(sources);
    for (const [name, contents] of [['alpha.txt', 'Alpha archivo original'], ['beta.txt', 'Beta áéíóú'], ['gamma.txt','Gamma archivo original']]) {
      fs.writeFileSync(path.join(sources, name), contents, { flag: 'wx' });
    }
    const destination = 'computer-use-acceptance-' + Date.now();
    const prepared = await api('POST', '/axx-api/learning/prepare', {
      text: 'Buscar los tres archivos de prueba, crear una copia ZIP y abrir la carpeta, conservando los originales.',
      steps: [
        { command_id: 'axx.file.find', inputs: { directory: sources, pattern: '*.txt', recursive: false, limit: 10 }, delivery_mode: 'background' },
        { command_id: 'axx.file.bundle', inputs: { destination, archive_name: 'delivery.zip' },
          bindings: { paths: { step: 0, path: ['output', 'paths'] } }, delivery_mode: 'background' },
        { command_id: 'axx.desktop.explorer.folder', inputs: {},
          bindings: {path: {step:1,path:['output','directory']}}, delivery_mode:'foreground' }
      ]
    });
    receipt.plan_prepared = prepared;
    assert.equal(prepared.state, 'awaiting_approval');
    const plan = await api('POST', '/axx-api/learning/execute', { operation_id: prepared.operation_id, approved: true });
    receipt.plan = plan;
    assert.equal(plan.state, 'succeeded', JSON.stringify(plan));
    assert.equal(plan.step_records.length, 3);
    const discovered = succeeded(plan.step_records[0].result, 'Plan file discovery');
    const bundled = succeeded(plan.step_records[1].result, 'Plan file bundle');
    assert.equal(discovered.paths.length, 3); assert.equal(discovered.truncated, false);
    assert.equal(bundled.files.length, 3);
    succeeded(plan.step_records[2].result,'Explorer destination folder');
    for (const copied of bundled.files) {
      assert.equal(sha(copied.path), copied.sha256);
      assert.equal(sha(path.join(sources, path.basename(copied.path))), copied.sha256);
    }
    assert.equal(sha(bundled.archive.path), bundled.archive.sha256);
    assert.equal(sha(bundled.manifest.path), bundled.manifest.sha256);
    check('Typed learning plan bound verified discovery paths into copied files, manifest and ZIP; original bytes preserved');
    await page.screenshot({ path: path.join(directory, 'axx-webview.png') });
    receipt.result = 'PASS';
  } catch (error) {
    receipt.result = 'FAIL'; receipt.error = String(error); receipt.stack = error.stack;
    console.error(error); process.exitCode = 1;
  } finally {
    // Only the process spawned above is closed. Never cancel another broker lease.
    if (fixture && fixture.exitCode === null) {
      fixture.kill();
      await Promise.race([new Promise(resolve => fixture.once('exit', resolve)), sleep(3000)]);
    }
    if (previous && page) await page.evaluate(saved => {
      if (saved.view) Axx.companion.openFeature(saved.view);
    }, previous).catch(() => {});
    receipt.finished_at = new Date().toISOString();
    const receiptPath = path.join(directory, 'computer-use.json');
    fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2), { flag: 'wx' });
    console.log(JSON.stringify({ result: receipt.result, checks: receipt.checks.length, receipt: receiptPath }, null, 2));
    await browser?.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
