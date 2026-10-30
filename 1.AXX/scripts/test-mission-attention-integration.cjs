/* Real temporary executor -> authenticated HTTP -> actual UI; no native input or provider. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { requirePlaywright, launchChromium } = require('./test-browser-runtime.cjs');

const root = path.resolve(__dirname, '../..');
const temporaryParent = fs.realpathSync(os.tmpdir());
const temporary = fs.mkdtempSync(path.join(temporaryParent, 'axx-mission-attention-'));
const evidence = path.join(root, 'build/source-context-destinations/mission-attention');
const runId = new Date().toISOString().replace(/[:.]/g, '-');
const checks = [], effects = [], bridgeCalls = [], pageErrors = [], externalRequests = [];
let child, browser, ready, childErrors = '', hostExit, spawnFailed = false;
const pending = [];
function check(name, condition) { assert.ok(condition, name); checks.push(name); }
function bounded(promise, ms, phase) {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Harness timeout: ' + phase)), ms); })]).finally(() => clearTimeout(timer));
}
function startHost() {
  const env = {};
  for (const [key, value] of Object.entries(process.env))
    if (['SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT'].includes(key.toUpperCase())) env[key] = value;
  for (const key of ['APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'HOME', 'TEMP', 'TMP']) {
    env[key] = path.join(temporary, key); fs.mkdirSync(env[key], { recursive: true });
  }
  Object.assign(env, { PYTHONIOENCODING: 'utf-8', PYTHONNOUSERSITE: '1' });
  child = spawn(process.env.AXX_TEST_PYTHON || 'python', ['-u', '-B', '-m', 'backend.tests.mission_attention_test_host'],
    { cwd: root, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let buffer = '';
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stderr.on('data', data => { childErrors = (childErrors + data).slice(-12000); });
  child.stdout.on('data', data => {
    buffer += data;
    if (buffer.length > 2 * 1024 * 1024) { child.kill(); return; }
    let split;
    while ((split = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, split); buffer = buffer.slice(split + 1);
      const waiter = pending.shift();
      try { const value = JSON.parse(line); if (waiter) waiter.resolve(value); }
      catch { if (waiter) waiter.reject(Error('Invalid fixture JSON')); }
    }
  });
  child.stdin.on('error', error => { for (const waiter of pending.splice(0)) waiter.reject(error); });
  hostExit = new Promise(resolve => {
    child.on('error', error => { spawnFailed = true; for (const waiter of pending.splice(0)) waiter.reject(error); resolve('spawn_error'); });
    child.on('exit', code => {
      for (const waiter of pending.splice(0)) waiter.reject(Error('Fixture exited before response (' + code + ')'));
      resolve(code);
    });
  });
  return receive('host startup');
}
function receive(phase) { return bounded(new Promise((resolve, reject) => pending.push({ resolve, reject })), 20000, phase); }
function control(action) { const response = receive(action); child.stdin.write(JSON.stringify({ action }) + '\n'); return response; }
async function bridge(method, route, body) {
  if (method === 'GET' && route === '/axx-api/providers') return { providers: [] };
  checkRoute(method, route);
  const record = { method, path: route.split('?')[0], action: body?.action, phase: body?.phase };
  bridgeCalls.push(record);
  const response = await fetch(ready.url + route, { method, headers: { Authorization: 'Bearer ' + ready.token,
    ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(10000) });
  record.status = response.status;
  const value = await response.json();
  if (!response.ok || value.error) throw Error('Fixture HTTP ' + response.status + ': ' + (value.error?.message || 'request rejected'));
  return value;
}
function checkRoute(method, route) {
  assert.ok(method === 'POST' && ['/axx-api/anticipation/status', '/axx-api/anticipation/feedback'].includes(route)
    || method === 'GET' && route.startsWith('/axx-api/learning/plans?'), 'Unexpected UI bridge route');
}
function actualClass(html, name) {
  const begin = html.indexOf('    class ' + name + ' {'), end = html.indexOf('    Axx.' + name + ' = ' + name + ';', begin);
  assert.ok(begin >= 0 && end > begin, 'Actual application class ' + name);
  return html.slice(begin, end) + '\nwindow.Axx.' + name + ' = ' + name + ';';
}
async function mount() {
  const page = await browser.newPage(); page.setDefaultTimeout(10000);
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/*', route => {
    if (route.request().url() === 'http://localhost/mission-attention-integration')
      return route.fulfill({ contentType: 'text/html', body: '<section id="view-settings"></section><main id="panel" hidden></main><div id="activity-list"></div><span id="unread-count"></span>' });
    externalRequests.push(route.request().url().split('?')[0]); return route.abort();
  });
  await page.exposeFunction('testBridge', bridge);
  await page.exposeFunction('testEffect', (kind, value) => effects.push({ kind, value }));
  await page.goto('http://localhost/mission-attention-integration');
  await page.evaluate(info => {
    window.node = id => document.getElementById(id); let sequence = 0;
    const token = { memory_scope: info.memory_scope, memory_context_id: info.memory_context_id, epoch: 0 };
    window.Axx = { isNative: () => true, newId: () => 'e2e-event-' + ++sequence,
      backendRequest: (method, route, body) => window.testBridge(method, route, body),
      chatWorkspace: { active: { id: info.task_id }, busy: false,
        captureMemoryScope: () => ({ ...info.memory_scope }), captureMemoryToken: () => structuredClone(token),
        isMemoryTokenCurrent: candidate => JSON.stringify(candidate) === JSON.stringify(token), allowsMemoryReference: () => true },
      skillLibrary: { project: () => info.project_id }, resident: { schedule() {}, drag: null },
      commandLibrary: { busy: false, operation: null, renderOperation() { throw Error('No unsolicited plan review'); } },
      app: { updateHitMap() {}, toast(text) { throw Error('Unexpected UI notice: ' + text); },
        bridge: { async listen() {} }, machine: { visible: true, notify: value => window.testEffect('machine', value) },
        stopDemo() { throw Error('No focus changes'); } } };
  }, { task_id: ready.task_id, project_id: ready.project_id, memory_scope: ready.memory_scope, memory_context_id: ready.memory_context_id });
  const html = fs.readFileSync(path.join(root, '1.AXX/Axx.html'), 'utf8');
  await page.addScriptTag({ content: actualClass(html, 'InteractionOrchestrator') + actualClass(html, 'Companion') });
  await page.evaluate(() => {
    const c = Object.create(Axx.Companion.prototype);
    Object.assign(c, { orchestrator: new Axx.InteractionOrchestrator(), events: [], unread: 0,
      data: { prefs: { voiceRead: true } }, app: Axx.app, renderChat() {},
      audio: { play: value => window.testEffect('sound', value) },
      speakReply(text) { void window.testEffect('voice', text); return true; },
      openChat() { throw Error('No focus changes'); }, openFeature() { throw Error('No focus changes'); } });
    c.orchestrator.subscribe(event => c.presentEvent(event)); Axx.companion = c;
  });
  await page.addScriptTag({ path: path.join(__dirname, 'anticipation.js') });
  // The native renderer normally positions this card; keep only the test target in view.
  await page.addStyleTag({ content: '#anticipation-card{top:10px;right:10px}' });
  await page.waitForFunction(() => Axx.anticipation?.state?.mission_attention?.length === 1);
  return page;
}

(async () => {
  let failure, summary;
  const started = Date.now();
  try {
    ready = await startHost(); check('Real temporary host ready with generated authentication', ready.ready && ready.pid === child.pid
      && /^[a-f0-9]{64}$/.test(ready.token) && new URL(ready.url).hostname === '127.0.0.1');
    const unauthorized = await fetch(ready.url + '/axx-api/anticipation/status', { signal: AbortSignal.timeout(10000) });
    check('Real host rejects missing authentication', unauthorized.status === 401);
    check('Exactly three real approved artifact writes', ready.artifacts.length === 3);
    for (const [index, artifact] of ready.artifacts.entries()) {
      const bytes = fs.readFileSync(artifact.path);
      check('Independent artifact bytes and SHA256 ' + index, bytes.equals(Buffer.from('Parte ' + index, 'utf8'))
        && crypto.createHash('sha256').update(bytes).digest('hex') === artifact.sha256);
    }
    browser = await launchChromium(requirePlaywright().chromium);
    let page = await mount();
    await page.waitForFunction(() => Axx.anticipation.state.mission_attention[0].interruption.presented);
    check('One real grouped card mounted', await page.locator('#anticipation-card:visible').count() === 1);
    let status = await control('snapshot');
    check('Three old awaiting-approval children remain unexecuted', status.status.suggestions.length === 3
      && status.status.suggestions.every(item => item.state === 'AWAITING_APPROVAL'));
    check('One mission group and one charged presentation', status.status.mission_attention.length === 1
      && status.status.metrics.attention_interruptions === 1 && status.status.metrics.attention_presented === 1
      && status.status.metrics.attention_budget_used_last_hour === 1 && status.status.metrics.shown === 0);
    check('Actual Activity contains one grouped event', await page.locator('#activity-list .activity-row').count() === 1);
    check('Only one stubbed voice and no physical audio/focus effects', effects.filter(item => item.kind === 'voice').length === 1
      && effects.every(item => item.kind === 'voice'));
    await page.evaluate(async () => { await Axx.anticipation.refresh(); await Axx.anticipation.refresh(); Axx.anticipation.render(); });
    check('Refresh replay does not duplicate voice or Activity', effects.length === 1
      && await page.locator('#activity-list .activity-row').count() === 1);
    await page.locator('#anticipation-actions').getByRole('button', { name: /No volver a avisar de esta misión/ }).click();
    await page.waitForFunction(() => document.getElementById('anticipation-card').hidden);
    status = await control('snapshot');
    check('Mission suppression does not rotate to another child', !status.status.mission_attention[0].interruption.eligible);
    await page.close(); await control('restart'); page = await mount();
    check('Restart preserves suppression without another voice', await page.locator('#anticipation-card').isHidden() && effects.length === 1);
    await page.locator('#anticipation-mission').evaluate(node => { node.open = true; });
    await page.evaluate(() => Axx.anticipation.refresh());
    await page.waitForSelector('[data-mission-id]');
    const restore = page.locator('#anticipation-missions').getByRole('button', { name: /Restaurar|Volver a avisar/ });
    await restore.click(); await page.waitForFunction(() => !document.getElementById('anticipation-card').hidden);
    await page.locator('#anticipation-actions').getByRole('button', { name: 'Descartar', exact: true }).click();
    await page.waitForFunction(() => document.getElementById('anticipation-card').hidden);
    status = await control('snapshot');
    check('Group dismissal does not rotate to another child', !status.status.mission_attention[0].interruption.eligible);
    await page.close(); await control('restart'); page = await mount();
    check('Restart preserves key dismissal without another voice', await page.locator('#anticipation-card').isHidden() && effects.length === 1);
    status = await control('snapshot');
    check('Restore and mission suppression preserve the original charge and voice', status.status.metrics.attention_interruptions === 1
      && status.status.metrics.attention_budget_used_last_hour === 1 && effects.length === 1);
    check('Presentation never invents human acceptance or usefulness', status.status.metrics.explicit_acceptances === 0
      && status.status.metrics.explicit_useful_feedback === 0);
    check('Polling, claims, dismissal and restore add no effects or inference', status.operation_count === 3 && status.ledger_unchanged
      && status.model_calls === 0 && status.model_ledger_rows === 0 && status.status.grants.length === 0);
    check('All real artifact hashes remain unchanged', status.artifact_hashes.every((hash, i) => hash === ready.artifacts[i].sha256));
    check('No unexpected browser network or page errors', externalRequests.length === 0 && pageErrors.length === 0);
    summary = { passed: true, check_count: checks.length, checks, artifact_writes: 3, suggestions: 3, mission_groups: 1,
      attention_charges: status.status.metrics.attention_interruptions, stubbed_voice_calls: effects.length,
      model_calls: status.model_calls, ledger_unchanged: status.ledger_unchanged, bridge_calls: bridgeCalls };
  } catch (error) { failure = error; summary = { passed: false, check_count: checks.length, checks, error: error.message, page_errors: pageErrors, bridge_calls: bridgeCalls }; }
  finally {
    try {
      if (browser) await bounded(browser.close(), 5000, 'browser cleanup');
    } catch (error) { failure ||= error; }
    try {
      if (child && !spawnFailed && child.exitCode === null) {
        child.stdin.end('{"action":"stop"}\n');
        try { await bounded(hostExit, 5000, 'fixture shutdown'); }
        catch { child.kill(); await bounded(hostExit, 3000, 'fixture termination'); }
      }
      if (child && await bounded(hostExit, 3000, 'fixture exit status') !== 0) throw Error('Fixture exited unsuccessfully during cleanup');
    } catch (error) { failure ||= error; }
    try {
      assert.equal(fs.realpathSync(temporary), temporary);
      assert.equal(path.dirname(temporary), temporaryParent); assert.ok(path.basename(temporary).startsWith('axx-mission-attention-'));
      fs.rmSync(temporary, { recursive: true, force: true });
    } catch (error) { failure ||= error; }
    if (failure) { summary.passed = false; summary.error = failure.message; }
    fs.mkdirSync(evidence, { recursive: true }); summary.elapsed_ms = Date.now() - started;
    summary.scope = 'Temporary approved files, authenticated HTTP and headless UI; no native UI, provider, voice listening or installed app validation.';
    if (failure && childErrors) summary.host_error = ready?.token ? childErrors.split(ready.token).join('[redacted]') : childErrors;
    fs.writeFileSync(path.join(evidence, runId + '-e2e-report.json'), JSON.stringify(summary, null, 2));
    fs.appendFileSync(path.join(evidence, 'e2e.log'), JSON.stringify(summary) + '\n');
  }
  if (failure) throw failure;
  console.log('PASS: ' + checks.length + ' real file/HTTP/UI integration checks; 3 writes, 1 mission, 1 charge, 1 stubbed voice, 0 model calls');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
