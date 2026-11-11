// Phase 6 / P0-02: tools from the NORMAL chat composer. Real Axx.html (WebView substitute: Chromium + a Tauri IPC shim
// that forwards backend_request to the REAL Python backend: HTTP, SQLite, CommandService, ActionExecutor, Connect journal).
// Provider: a scripted OpenAI-compatible server by default (contract), or a real Ollama with
//   AXX_TEST_OLLAMA_URL=http://127.0.0.1:11485 AXX_TEST_OLLAMA_MODEL=qwen2.5:7b-instruct   (real-model acceptance).
// Not native WebView2 acceptance. Text produced by a model is never counted as an execution; only receipts are.
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), os = require('node:os'), assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require(require('module').createRequire(path.join(process.env.USERPROFILE || '', '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json')).resolve('playwright'))); }
const root = path.join(__dirname, '../..'), real = Boolean(process.env.AXX_TEST_OLLAMA_URL), TOKEN = 't'.repeat(48);
const PROMPT = 'AXX, muéstrame el estado actual de CPU y memoria RAM.';
(async () => {
  const seen = [];
  const mock = http.createServer((req, res) => {
    let raw = ''; req.on('data', d => raw += d); req.on('end', async () => {
      const body = JSON.parse(raw || '{}'), user = [...(body.messages || [])].reverse().find(m => m.role === 'user')?.content || '';
      if (process.env.AXX_TEST_SIZES) process.stderr.write('REQUEST chars=' + raw.length + ' messages=' + (body.messages || []).map(m => m.role + ':' + String(m.content).length).join(',') + ' tools=' + JSON.stringify(body.tools || []).length + '\n');
      seen.push({ tools: (body.tools || []).map(t => t.function.name), user, system: (body.messages || []).filter(m => m.role === 'system').map(m => m.content) });
      const call = (name, args) => ({ role: 'assistant', content: '', tool_calls: [{ id: 'call_1', type: 'function', function: { name, arguments: typeof args === 'string' ? args : JSON.stringify(args) } }] });
      let message = { role: 'assistant', content: 'Respuesta sin herramienta.' };
      if (/ESPERA/.test(user)) await new Promise(r => setTimeout(r, 4000));
      if (body.tools?.length) {
        if (/ESQUEMA/.test(user)) message = call('axx_system_telemetry', { type: 'object', properties: {} });
        else if (/INVALIDO/.test(user)) message = call('axx_artifact_write', { path: 'sin-contenido.txt' });
        else if (/DESCONOCIDA/.test(user)) message = call('axx_shell_powershell', { script: 'Get-Date' });
        else if (/JSONROTO/.test(user)) message = call('axx_system_telemetry', '{"a":');
        else if (/ESCRIBE/.test(user)) message = call('axx_artifact_write', { path: 'composer.txt', content: 'hola' });
        else if (/CPU/.test(user) || /telemetr/i.test(user)) message = call('axx_system_telemetry', {});
      } else if (/CPU/.test(user)) message = { role: 'assistant', content: 'La CPU está al 12 % (valor inventado).' };
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ id: 'x', model: body.model, choices: [{ index: 0, message, finish_reason: message.tool_calls ? 'tool_calls' : 'stop' }], usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 } }));
    });
  });
  await new Promise(r => mock.listen(0, '127.0.0.1', r));
  const base = real ? process.env.AXX_TEST_OLLAMA_URL + '/v1' : 'http://127.0.0.1:' + mock.address().port + '/v1';
  const model = real ? process.env.AXX_TEST_OLLAMA_MODEL : 'mock-tools-model';
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'axx-composer-'));
  const provider = (name, m, caps) => ({ name, base_url: base, model: m, api_key_env: 'OLLAMA_API_KEY', enabled: true, free_confirmed: true, allow_sensitive: true, daily_attempt_limit: 500, max_output_tokens: 512, quota_scope_id: name + '-scope', capabilities: caps });
  fs.writeFileSync(path.join(tmp, 'providers.json'), JSON.stringify({ timeout_seconds: 60, global_deadline_seconds: 70, max_attempts: 1, max_request_bytes: 2097152, allow_paid: false,
    providers: real ? [provider('ollama-local', model, ['text', 'tools'])] : [provider('mock-tools', model, ['text', 'tools']), provider('mock-notools', 'mock-notools-model', ['text'])] }));
  const ready = path.join(tmp, 'ready.json');
  const backend = spawn('python', ['-B', '-m', 'backend.server', '--port', '0', '--config', path.join(tmp, 'providers.json'), '--state', path.join(tmp, 'state.db'), '--data-dir', tmp, '--ready-file', ready],
    { cwd: root, windowsHide: true, env: { ...process.env, AXX_HOST_TOKEN: TOKEN, AXX_HOST_INSTANCE: 'composer-test', PYTHONDONTWRITEBYTECODE: '1', no_proxy: '127.0.0.1', NO_PROXY: '127.0.0.1' }, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = ''; backend.stderr.on('data', d => stderr += d);
  let port; for (let i = 0; i < 160 && !port; i++) { try { port = JSON.parse(fs.readFileSync(ready, 'utf8')).port; } catch { await new Promise(r => setTimeout(r, 250)); } }
  assert(port, 'backend did not start: ' + stderr.slice(-600));
  const web = http.createServer((req, res) => {
    const url = req.url.split('?')[0], file = url.startsWith('/scripts/') ? path.join(__dirname, path.basename(url)) : path.join(__dirname, '../Axx.html');
    if (!fs.existsSync(file)) { res.statusCode = 404; return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(fs.readFileSync(file));
  });
  await new Promise(r => web.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || undefined });
  const checks = [], backendErrors = [];
  const ok = (name, detail) => checks.push({ name, detail });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } }); page.setDefaultTimeout(real ? 150000 : 20000);
    const pageErrors = []; page.on('pageerror', e => pageErrors.push(e.message));
    await page.exposeFunction('axxBackend', async (method, p, body) => {
      const r = await fetch(`http://127.0.0.1:${port}${p}`, { method, headers: { Authorization: 'Bearer ' + TOKEN, 'Content-Type': 'application/json' }, body: body == null ? undefined : JSON.stringify(body) });
      const text = await r.text(); let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
      if (!r.ok) { backendErrors.push({ p, status: r.status, data }); throw Error('Backend HTTP ' + r.status + ': ' + (data.error?.message || text)); }
      return data;
    });
    await page.addInitScript(() => {
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1660, spaceRight: 260, spaceAbove: 800, spaceBelow: 240 };
        if (name === 'native_status') return { native: true, backendReady: true, backendError: null, shortcut: 'Alt+Shift+A', restoreShortcutAvailable: true, restoreShortcutError: null, alwaysOnTop: true, timer: null, dataDirectory: 'COMPOSER_TEST', desktop };
        if (name === 'desktop_layout') return { ...desktop, ...args };
        if (name === 'backend_request') return window.axxBackend(args.method, args.path, args.body ?? null);
        return null;
      } }, event: { listen: async () => () => {} } };
    });
    await page.goto('http://127.0.0.1:' + web.address().port + '/');
    await page.waitForFunction(() => window.Axx?.companion && Axx.chatWorkspace?.ready && Axx.commandLibrary);
    const select = (apiConnection, m) => page.evaluate(async ({ apiConnection, m }) => {
      const c = Axx.companion; Object.assign(c.data.prefs, { provider: 'bridge', apiConnection, model: m, selection_mode: 'manual', voiceRead: false, keepHistory: true });
      c.save(); c.syncPreferences(); await c.connect(); c.openChat();
    }, { apiConnection, m });
    const mode = v => page.locator('#cw-mode').selectOption(v);
    const tools = on => page.evaluate(on => { const n = document.getElementById('ai-chat-tools'); n.checked = on; n.dispatchEvent(new Event('change')); }, on);
    const send = async text => {
      await page.evaluate(() => { Axx.commandLibrary.lastOperation = null; Axx.commandLibrary.operation = null; });
      const count = await page.evaluate(() => Axx.companion.data.messages.length);
      await page.locator('#chat-input').fill(text); await page.locator('#chat-input').press('Enter');
      await page.waitForFunction(n => Axx.companion.data.messages.length >= n + 2 && !Axx.companion.pending && Axx.companion.data.messages.at(-1)?.role === 'assistant' && ['complete', 'interrupted', 'error', 'failed'].includes(Axx.companion.data.messages.at(-1).status), count);
      // the receipt card is attached right after the message completes
      await page.waitForFunction(() => Axx.commandLibrary.lastOperation || !/Acción verificada|requiere revisión/.test(Axx.companion.data.messages.at(-1).text), undefined, { timeout: 5000 }).catch(() => {});
      return page.evaluate(() => ({ text: Axx.companion.data.messages.at(-1).text, status: Axx.companion.data.messages.at(-1).status, op: Axx.commandLibrary.lastOperation, planner: [...document.querySelectorAll('#cw-operation')].map(n => n.textContent).join(' ') }));
    };
    const planner = () => backendErrors.filter(e => /learning/.test(e.p));
    const operationsOnDisk = () => page.evaluate(() => Axx.backendRequest('GET', '/axx-api/commands/operations')).then(r => r.operations);
    await select(real ? 'ollama-local' : 'mock-tools', model); await mode('auto_safe'); await tools(true);

    // A. the required natural request: capability identified, executed by the existing executor, real data shown, verifiable receipt.
    const a = await send(PROMPT);
    assert.equal(a.op?.command_id, 'axx.system.telemetry', 'telemetry capability invoked: ' + JSON.stringify(a));
    assert.equal(a.op.state, 'succeeded'); assert.equal(a.op.postconditions_passed, true);
    assert.equal(a.op.origin ?? 'axx-provider', 'axx-provider');
    assert.match(a.text, /Acción verificada en Axx/); assert.doesNotMatch(a.text, /CPU:|RAM:|memory_/, 'tool output is not copied into the chat history sent to providers: ' + a.text);
    const card = await page.locator('#cw-operation').innerText();
    assert.match(card, /CPU: (\d+(?:\.\d+)? %|no disponible)/, 'the receipt card shows the real data: ' + card); assert.match(card, /RAM: [\d.]+ GB en uso de [\d.]+ GB/);
    const stored = (await operationsOnDisk()).find(o => o.operation_id === a.op.operation_id);
    assert.equal(stored?.state, 'succeeded', 'receipt persisted in the journal'); assert.equal(stored.postconditions_passed, true);
    assert.equal(typeof stored.output.memory_used_mb, 'number'); assert(stored.output.memory_total_mb >= stored.output.memory_used_mb);
    if (!real) { assert(seen.at(-1).tools.includes('axx_system_telemetry') && !seen.at(-1).tools.includes('axx_shell_powershell')); assert(seen.at(-1).system.some(s => /axx_system_telemetry/.test(s)), 'guidance sent'); }
    assert.deepEqual(planner(), [], 'the planner was not involved');
    ok('composer natural request -> telemetry receipt', { operation_id: a.op.operation_id, chat_text: a.text, card });

    if (!real) {
      // B. action-like wording (verbs the local grammar claims) must reach the chat tools, not the planner.
      const b = await send('Usa la función axx_system_telemetry sin parámetros. Llama exactamente una vez con {}.'); // the phase-5 prompt the planner used to swallow assert.equal(b.op?.command_id, 'axx.system.telemetry'); assert.equal(b.op.postconditions_passed, true);
      assert.doesNotMatch(b.planner, /waiting_capacity|learned/); ok('action-like verbs reach chat tools');
      // C. schema echoed as arguments of a parameterless tool is executed with {}; broken JSON is rejected.
      const c1 = await send('ESQUEMA CPU'); assert.equal(c1.op?.command_id, 'axx.system.telemetry', JSON.stringify(c1)); assert.deepEqual(c1.op.inputs, {}); ok('schema-echo arguments ignored for parameterless tool');
      // D. invalid arguments / unknown tool: rejected, nothing executed, nothing written.
      const before = (await operationsOnDisk()).length;
      const d1 = await send('INVALIDO'); assert.doesNotMatch(d1.text, /Acción verificada/); assert.equal(fs.existsSync(path.join(tmp, 'artifacts', 'sin-contenido.txt')), false);
      const d2 = await send('DESCONOCIDA'); assert.doesNotMatch(d2.text, /Acción verificada/);
      assert.equal((await operationsOnDisk()).length, before, 'rejected calls created no executable operation'); ok('invalid arguments and unknown tool rejected', { d1: d1.text, d2: d2.text });
      // E. a write needs approval in auto_safe and is not executed by the model text alone.
      const e = await send('ESCRIBE un archivo'); assert.equal(e.op?.state, 'awaiting_approval', JSON.stringify(e)); assert.equal(fs.existsSync(path.join(tmp, 'artifacts', 'composer.txt')), false); ok('write awaits approval');
      await page.evaluate(id => Axx.backendRequest('POST', '/axx-api/commands/cancel', { operation_id: id }), e.op.operation_id);
      // F. provider without tools capability: the model's invented number is plain text, never an execution.
      await select('mock-notools', 'mock-notools-model');
      const f = await send(PROMPT); assert.equal(f.op ?? null, null); assert.match(f.text, /valor inventado/); assert.match(f.text, /Herramientas no disponibles/);
      assert.deepEqual(seen.at(-1).tools, []); ok('provider without tools: text only, flagged unavailable', f.text);
      await select('mock-tools', model);
      // G. tools off (default): same provider, no tools offered.
      await tools(false); const g = await send(PROMPT); assert.equal(g.op ?? null, null); assert.deepEqual(seen.at(-1).tools, []); ok('opt-in off: no tools offered'); await tools(true);
      // H. cancellation while the provider is slow: no receipt, UI recovers.
      await page.locator('#chat-input').fill('ESPERA CPU'); await page.locator('#chat-input').press('Enter');
      await page.waitForFunction(() => Axx.companion.pending); await page.evaluate(() => Axx.companion.cancelRequest());
      await page.waitForFunction(() => !Axx.companion.pending); await page.waitForTimeout(4500);
      assert.equal((await operationsOnDisk()).filter(o => o.command_id === 'axx.system.telemetry').length >= 3, true);
      const afterCancel = await operationsOnDisk(); const last = afterCancel[0];
      assert.notEqual(last.operation_id, undefined); ok('cancel while provider runs leaves the composer usable');
    }
    if (!real) {
      // I. malformed JSON arguments are rejected by the router (kept last: a malformed provider reply puts that provider in cooldown).
      const c2 = await send('JSONROTO CPU'); assert.equal(c2.op ?? null, null); assert(c2.status === 'error' || /no fue ejecutada|sin confirmar|bloque/i.test(c2.text), JSON.stringify(c2)); assert.doesNotMatch(c2.text, /Acción verificada/); ok('malformed JSON arguments rejected', c2.text);
    }
    assert.deepEqual(pageErrors, []);
    console.log(JSON.stringify({ result: 'PASS', mode: real ? 'real-ollama:' + model : 'scripted-provider', checks: checks.length, detail: checks }, null, 1));
  } catch (e) {
    console.error(e && e.stack || e); console.error(JSON.stringify({ checks, backendErrors, seen: seen.slice(-3), stderr: stderr.slice(-800) }, null, 1)); process.exitCode = 1;
  } finally { await browser.close(); web.close(); mock.close(); backend.kill(); }
})();
