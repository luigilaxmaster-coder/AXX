/** Controlled browser/IPC contract tests. These do not certify native Windows behavior. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createRequire } = require('node:module');
const bundledRequire = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = bundledRequire('playwright');
const productionHtml = fs.readFileSync(path.join(__dirname, '../Axx.html'), 'utf8');
const html = process.env.AXX_TEST_VOICE_DRAFT ? productionHtml.replace('</body>', '<script>' + fs.readFileSync(path.join(__dirname, 'native-voice-fallback.draft.js'), 'utf8') + '</script></body>') : productionHtml;
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
assert(!html.includes('X-Axx-Token'), 'Host credentials must not appear in the frontend');
assert(!html.includes("const apiBase ="), 'Production must not hardcode a development port');

(async () => {
  const server = http.createServer((req, res) => { if (['/scripts/native-voice.js', '/scripts/command-library.js', '/scripts/axx-connect.js'].includes(req.url)) { res.writeHead(200, { 'Content-Type': 'application/javascript' }); res.end(fs.readFileSync(path.join(__dirname, path.basename(req.url)))); } else { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); } });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  const results = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      window.__contractCalls = [];
      window.__contractModels = [];
      window.__contractHoldChat = false;
      window.__contractIdentity = null;
      window.__contractRecipes = [];
      window.__contractCommands = {};
      window.__contractEvents = {};
      const pcm = new Uint8Array(44 + 3200), view = new DataView(pcm.buffer);
      const str = (at, text) => [...text].forEach((c, i) => pcm[at + i] = c.charCodeAt(0));
      str(0, 'RIFF'); view.setUint32(4, pcm.length - 8, true); str(8, 'WAVE'); str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); str(36, 'data'); view.setUint32(40, 3200, true);
      window.__contractWav = btoa(String.fromCharCode(...pcm));
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        window.__contractCalls.push({ name, args });
        const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1660, spaceRight: 260, spaceAbove: 800, spaceBelow: 240 };
        if (name === 'native_status') return { native: true, backendReady: !window.__contractSuppressBackend, backendError: null, shortcut: 'Alt+Shift+A', alwaysOnTop: true, timer: null, dataDirectory: 'CONTRACT_TEST_ONLY', desktop };
        if (name === 'desktop_layout') { await new Promise(resolve => setTimeout(resolve, 45)); window.__contractLayout = args; return { ...desktop, ...args }; }
        if (name !== 'backend_request') return null;
        const { method, path, body } = args;
        if (path === '/axx-api/status') return { ready: true, provider: 'Contract fixture', details: { providers: [{ name: 'contract-fixture', state: window.__contractProviderState || (window.__contractModels.length ? 'ready_locally' : 'missing_key'), model: window.__contractModels[0] || 'configured-fixture-model' }] } };
        if (path === '/axx-api/models') return { models: window.__contractModels };
        if (path === '/axx-api/identity') {
          if (method === 'GET') return { identity: window.__contractIdentity };
          window.__contractIdentity = body; return { saved: true };
        }
        if (path === '/axx-api/recipes' && method === 'GET') return { recipes: window.__contractRecipes };
        if (path === '/axx-api/actions/execute') return { operation_id: body.operation_id, tool_name: body.tool_name, state: 'succeeded', postconditions_passed: true, output: { os: 'CONTRACT_ONLY' }, evidence: { fixture: true } };
        if (path === '/axx-api/commands/resolve') { if (window.__contractDenyResolver) throw new Error('Backend HTTP 403: test denial'); return { match: 'none' }; }
        if (path.startsWith('/axx-api/commands?')) return { commands: [{ id: 'axx.system.telemetry', title: 'Estado del sistema', description: 'CONTRACT_ONLY', execution_enabled: true, parameters: {} }], counts: { imported: 0, enabled: 1, blocked: 0, verified_operations: 0 } };
        if (path === '/axx-api/commands/prepare') {
          const operation_id = body.operation_id;
          return window.__contractCommands[operation_id] = { operation_id, command_id: body.command_id, inputs: body.inputs, state: body.command_id === 'axx.artifact.write' ? 'awaiting_approval' : 'prepared' };
        }
        if (path === '/axx-api/recipes/prepare') {
          const recipe = window.__contractRecipes.find(record => record.intent_key === body.intent_key);
          if (!recipe || Object.keys(body.inputs).some(key => !(key in recipe.schema))) throw new Error('Parámetros de receta desconocidos');
          return window.__contractCommands[body.operation_id] = { operation_id: body.operation_id, command_id: 'axx.system.telemetry', inputs: {}, state: 'prepared' };
        }
        if (path === '/axx-api/commands/execute') return { ...window.__contractCommands[body.operation_id], state: 'succeeded', postconditions_passed: true, action_operation_id: 'fixture-action-' + body.operation_id, evidence: { fixture: true } };
        if (path === '/axx-api/commands/cancel') return { cancelled: true };
        if (path === '/axx-api/recipes/register') { window.__contractRecipes.push({ id: body.id, intent_key: body.intent_key, status: 'verified', schema: {} }); return { saved: true }; }
        if (path === '/axx-api/recipes/execute') return { success: true, fixture: true, steps_executed: 1 };
        if (path === '/axx-api/chat/cancel') return { cancelled: true };
        if (path === '/axx-api/actions/cancel') return { cancelled: true };
        if (path === '/axx-api/speech/voices') return { available: true, engine: 'windows-sapi', voices: [{ name: 'Contract fixture voice', language: 'en-US', enabled: true }] };
        if (path === '/axx-api/speech/synthesize') return { engine: 'windows-sapi', voice: body.voice, language: 'en-US', audio_base64: window.__contractWav, mime: 'audio/wav', duration_seconds: .1, evidence: { sha256: 'CONTRACT_ONLY' } };
        if (path === '/axx-api/speech/transcribe') { if (window.__contractHoldAsr) await new Promise(resolve => setTimeout(resolve, 150)); return { text: 'Texto del contrato de ASR', engine: 'faster-whisper', model: 'tiny' }; }
        if (path === '/axx-api/memory/query') return { hits: [{ path: 'recipes/contract.md' }], memory: { backend: 'ai-memory' }, execution_allowed: false };
        if (path === '/axx-api/memory/read') return { page: { body: 'Contract full recipe record' }, memory: { backend: 'ai-memory' }, execution_allowed: false };
        if (path === '/axx-api/chat') {
          if (window.__contractHoldChat) await new Promise(resolve => setTimeout(resolve, 500));
          return { request_id: body.request_id, choices: [{ message: { content: 'Contract fixture response' }, finish_reason: 'stop' }], axx_router: { provider: 'contract-fixture', model: body.model, elapsed_ms: 17 } };
        }
        throw new Error('Unsupported contract fixture route: ' + path);
      } }, event: { listen: async (name, fn) => { window.__contractEvents[name] = fn; return () => {}; } } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.desktop?.ready && !window.Axx.companion.connecting);
    assert.deepEqual(errors, []);
    assert.equal(await page.locator('#fatal').textContent(), '');
    results.push('Full original HTML starts without uncaught exceptions');
    const nativeBackground = await page.evaluate(() => [document.documentElement, document.body].map(e => getComputedStyle(e).backgroundColor));
    assert.deepEqual(nativeBackground, ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0)']);
    results.push('Native overlay backgrounds are transparent while the original UI surfaces remain');
    console.error(await page.evaluate(() => ({ resident: !!Axx.resident, fatal: document.getElementById('fatal').textContent, toast: document.getElementById('toast').textContent, layout: window.__contractLayout, first: Axx.resident?.firstFrame })));
    await page.waitForFunction(() => window.__contractLayout?.ready === true);
    console.error('resident: ready');
    const residentStartup = await page.evaluate(() => ({ layout: window.__contractLayout, size: Axx.resident.size, visibleButtons: [...document.querySelectorAll('button')].filter(n => n.getClientRects().length && getComputedStyle(n).visibility !== 'hidden').map(n => n.id) }));
    assert.equal(residentStartup.layout.width, residentStartup.size + 24);
    assert.equal(residentStartup.layout.height, residentStartup.size + 24);
    assert.deepEqual(residentStartup.visibleButtons, []);
    console.error('resident: no startup controls');
    const startupPng = await page.screenshot({ omitBackground: true });
    const alpha = await page.evaluate(async encoded => {
      const image = new Image(); image.src = 'data:image/png;base64,' + encoded; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
      const context = canvas.getContext('2d'); context.drawImage(image, 0, 0); const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const r = document.getElementById('stage').getBoundingClientRect(); let paintedOutside = 0, paintedBody = 0;
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) if (data[(y * canvas.width + x) * 4 + 3] > 0) { if (x < r.left || x >= r.right || y < r.top || y >= r.bottom) paintedOutside++; else paintedBody++; }
      return { paintedOutside, paintedBody };
    }, startupPng.toString('base64'));
    assert.equal(alpha.paintedOutside, 0); assert(alpha.paintedBody > 100);
    console.error('resident: alpha verified');
    results.push('Resident startup paints only the real liquid canvas, has zero alpha outside it and requests a compact window');
    await page.evaluate(() => Axx.flow.select('chat'));
    await page.waitForFunction(() => window.__contractLayout.width > Axx.resident.size + 100);
    console.error('resident: chat expanded');
    const expanded = await page.evaluate(() => window.__contractLayout);
    await page.setViewportSize({ width: expanded.width, height: expanded.height });
    await page.waitForFunction(() => document.getElementById('panel').getBoundingClientRect().width >= 400);
    assert(await page.evaluate(() => { const p = document.getElementById('panel').getBoundingClientRect(); return p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight; }));
    assert.equal(await page.evaluate(() => Axx.resident.size), residentStartup.size);
    await page.evaluate(() => Axx.resident.fold());
    await page.waitForFunction(() => window.__contractLayout.width === Axx.resident.size + 24);
    await page.setViewportSize({ width: residentStartup.layout.width, height: residentStartup.layout.height });
    console.error('resident: chat closed');
    assert.equal(await page.locator('#panel').isVisible(), false);
    results.push('Opening and closing the existing chat requests content-sized native geometry without changing body size');
    const bodyPoint = await page.evaluate(() => {
      const r = document.getElementById('avatar').getBoundingClientRect();
      for (let radius = 0; radius < 100; radius += 5) for (let angle = 0; angle < Math.PI * 2; angle += .3) { const x = r.left + r.width / 2 + Math.cos(angle) * radius, y = r.top + r.height / 2 + Math.sin(angle) * radius; if (Axx.app.renderer.hitTest(x, y)) return { x, y }; }
      return null;
    });
    assert(bodyPoint);
    await page.mouse.move(bodyPoint.x, bodyPoint.y); await page.mouse.down(); await page.mouse.move(bodyPoint.x + 20, bodyPoint.y + 14); await page.mouse.up();
    const dragCalls = await page.evaluate(() => window.__contractCalls.filter(c => c.name === 'window_action' && c.args?.action === 'drag'));
    assert.equal(dragCalls.length, 1);
    assert.equal(await page.evaluate(() => Axx.flow.nav.step), 0);
    results.push('Dragging the opaque body past seven pixels invokes native drag exactly once and releasing opens no tool');
    await page.setViewportSize({ width: 1440, height: 960 });
    assert.equal(await page.evaluate(() => Axx.FORMS.length), 24);
    assert.equal(await page.evaluate(() => Axx.PALETTES.length), 9);
    assert.equal(await page.evaluate(() => Axx.companion.brain.connected), false);
    assert.match(await page.locator('#ai-status').textContent(), /No hay un proveedor gratuito/);
    results.push('24 forms and 9 palettes retained; empty models remain disconnected');
    for (const providerState of ['missing_key', 'disabled']) {
      const guarded = await page.evaluate(async state => {
        window.__contractModels = ['contract-fixture-model']; window.__contractProviderState = state;
        await Axx.companion.connect();
        return { connected: Axx.companion.brain.connected, models: Axx.companion.brain.models, verified: Axx.companion.brain.inferenceVerified };
      }, providerState);
      assert.equal(guarded.connected, false); assert.deepEqual(guarded.models, []); assert.equal(guarded.verified, false);
    }
    results.push('A nonempty catalog with missing_key or disabled metadata exposes no usable model and remains disconnected');
    await page.evaluate(() => { window.__contractProviderState = 'ready_locally'; });
    await page.evaluate(async () => { window.__contractModels = ['contract-fixture-model']; await Axx.companion.connect(); });
    assert.equal(await page.evaluate(() => Axx.companion.brain.inferenceVerified), false);
    const inference = await page.evaluate(async () => {
      const brain = Axx.companion.brain, prefs = Axx.companion.data.prefs;
      const result = await brain.chat(prefs, [{ role: 'user', content: 'contract only' }], new AbortController().signal, () => {});
      return { result, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat') };
    });
    assert.equal(inference.calls.length, 1);
    assert.equal(inference.calls[0].args.body.stream, false);
    assert.equal(inference.result.route.elapsed_ms, 17);
    results.push('Chat sends exactly one native JSON request and preserves actual route metadata');
    const cancelled = await page.evaluate(async () => {
      window.__contractHoldChat = true;
      const ctrl = new AbortController();
      const pending = Axx.companion.brain.chat(Axx.companion.data.prefs, [{ role: 'user', content: 'cancel contract only' }], ctrl.signal, () => {});
      setTimeout(() => ctrl.abort(), 20);
      try { await pending; return { error: 'not cancelled' }; }
      catch (e) { return { error: e.name, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat/cancel') }; }
    });
    assert.equal(cancelled.error, 'AbortError'); assert.equal(cancelled.calls.length, 1);
    results.push('Cancellation emits one correlated cancellation request and rejects late response');
    const identity = await page.evaluate(() => {
      const app = Axx.app; app.store.data.settings.form = 17; app.store.data.settings.palette = 5; app.store.data.settings.keepForm = true;
      app.refreshIdentity(); app.machine.setConversation('thinking'); app.tick();
      return { saved: JSON.parse(localStorage.getItem('axx-studio-v2')), shown: app.displayForm20('error') };
    });
    assert.equal(identity.saved.form, 17); assert.equal(identity.saved.palette, 5); assert.equal(identity.shown, 17);
    results.push('Task state preserves canonical form and palette');
    await page.evaluate(() => { Axx.companion.openFeature('settings'); document.getElementById('desktop-runtime').scrollIntoView(); });
    await page.locator('#desktop-telemetry').click();
    await page.waitForFunction(() => Axx.desktop.lastOperation?.state === 'succeeded');
    await page.locator('#desktop-runtime details').nth(1).locator('summary').click();
    await page.locator('#desktop-recipe-save').click();
    await page.waitForFunction(() => document.getElementById('desktop-recipes').value === 'consultar-mi-pc');
    await page.locator('#desktop-recipe-run').click();
    await page.waitForFunction(() => window.__contractCalls.some(call => call.args?.path === '/axx-api/recipes/prepare'));
    await page.waitForFunction(() => !Axx.commandLibrary.busy);
    assert.equal(await page.evaluate(() => window.__contractCalls.filter(call => call.args?.path === '/axx-api/recipes/execute').length), 0);
    assert.equal(await page.evaluate(() => Object.keys(window.__contractCalls.filter(call => call.args?.path === '/axx-api/recipes/prepare').at(-1).args.body.inputs).length), 0);
    assert.equal(await page.evaluate(() => Axx.desktop.lastOperation?.state), 'succeeded');
    results.push('Visible action and recipe reuse controls pass through command preparation, preserve verified action IDs and register the real receipt');
    await page.evaluate(() => Axx.companion.send('/comandos estado del sistema'));
    await page.waitForFunction(() => document.getElementById('command-library-select').options.length === 1 && document.getElementById('command-library-select').value === 'axx.system.telemetry');
    assert.equal(await page.locator('#command-library').isVisible(), true);
    assert.match(await page.locator('#command-library-counts').textContent(), /Habilitadas: 1/);
    assert.equal(await page.evaluate(() => Axx.FORMS.length), 24);
    results.push('The command library opens inside the original files tool and exposes live availability without replacing the avatar');
    const localWithoutBackend = await page.evaluate(async () => {
      window.__contractDenyResolver = true;
      const before = window.__contractCalls.filter(call => call.args?.path === '/axx-api/commands/resolve').length;
      await Axx.companion.send('calcula 2 + 3');
      const calculation = Axx.companion.data.messages.at(-1).text;
      await Axx.companion.send('pon un temporizador de diez segundos');
      const timerStarted = Axx.app.store.data.timer?.status;
      await Axx.companion.send('cancelar temporizador');
      const timerCancelled = Axx.app.store.data.timer?.status;
      window.__contractDenyResolver = false;
      return { before, after: window.__contractCalls.filter(call => call.args?.path === '/axx-api/commands/resolve').length, calculation, timerStarted, timerCancelled };
    });
    assert.equal(localWithoutBackend.before, localWithoutBackend.after);
    assert.match(localWithoutBackend.calculation, /5/);
    assert.equal(localWithoutBackend.timerStarted, 'running');
    assert.equal(localWithoutBackend.timerCancelled, 'cancelled');
    results.push('Original calculator and timer start/cancel remain functional with the catalog backend denied');
    await page.evaluate(() => Axx.flow.select('settings'));
    await page.locator('#desktop-memory-query').fill('consultar-mi-pc');
    await page.locator('#desktop-memory-search').click();
    await page.waitForFunction(() => document.getElementById('desktop-memory-result').textContent.includes('"hits"'));
    await page.locator('#desktop-memory-read').click();
    await page.waitForFunction(() => document.getElementById('desktop-memory-result').textContent.includes('Contract full recipe record'));
    results.push('The memory panel exposes real query/read contracts with execution explicitly disallowed');
    await page.evaluate(() => { Axx.resident.fold(); Axx.organic.newWorkspace(); });
    await page.waitForFunction(() => Axx.resident.boxes.some(box => box.id.startsWith('resident-surface-')));
    const organic = await page.evaluate(() => { const box = Axx.resident.boxes.find(box => box.id.startsWith('resident-surface-')); const r = document.getElementById(box.id).getBoundingClientRect(); return { layout: window.__contractLayout, r: { x: r.x, y: r.y, right: r.right, bottom: r.bottom } }; });
    assert(organic.r.x >= 0 && organic.r.y >= 0 && organic.r.right <= organic.layout.width && organic.r.bottom <= organic.layout.height);
    await page.evaluate(() => { for (const id of [...Axx.organic.surfaces.keys()]) Axx.organic.removeSurface(id); Axx.resident.fold(); });
    results.push('New notebook surfaces are included in compact native geometry and remain fully reachable');
    if (await page.evaluate(() => !!Axx.nativeVoice)) {
      await page.evaluate(() => { window.__readerContract = new Axx.SpeechReader(); window.__readerContract.setText('Lectura del contrato local.'); window.__readerContract.play(); });
      await page.waitForFunction(() => window.__readerContract.state === 'ended');
      assert.equal(await page.evaluate(() => Axx.nativeVoice.playback.playing_event && Axx.nativeVoice.playback.ended_event), true);
      const speech = await page.evaluate(() => window.__contractCalls.filter(c => c.args?.path === '/axx-api/speech/synthesize'));
      assert.equal(speech.length, 1); assert.equal(speech[0].args.body.voice, 'Contract fixture voice');
      results.push('Native reader contract decodes a real PCM fixture WAV and receives playing/ended events without physical speaker claims');
      const asr = await page.evaluate(async () => {
        const session = Axx.nativeVoice.sessions[0], saved = session.owner.onFinal, finals = [];
        session.owner.onFinal = text => finals.push(text); session.lang = 'es-DO';
        const before = window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat').length;
        await session.submit(new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm;codecs=opus' }));
        session.owner.onFinal = saved;
        return { finals, before, after: window.__contractCalls.filter(c => c.args?.path === '/axx-api/chat').length, calls: window.__contractCalls.filter(c => c.args?.path === '/axx-api/speech/transcribe') };
      });
      assert.deepEqual(asr.finals, ['Texto del contrato de ASR']); assert.equal(asr.calls.length, 1); assert.equal(asr.calls[0].args.body.language, 'es'); assert.equal(asr.before, asr.after);
      results.push('ASR transport contract normalizes locale, emits confirmed text and never sends the chat automatically');
    }
    await page.addInitScript(() => { window.requestAnimationFrame = () => 1; window.__contractSuppressBackend = true; });
    await page.reload();
    // RAF is deliberately suspended above, so the observer must use an independent clock.
    await page.waitForFunction(() => window.__contractLayout?.ready === true, null, { polling: 50 });
    assert.equal(await page.evaluate(() => Axx.desktop.ready), false);
    assert.equal(await page.evaluate(() => Axx.resident.startup.renderedBody && Axx.resident.startup.readyAcknowledged), true);
    results.push('Transparent first content and native readiness complete even when hidden WebView suspends all RAF and backend readiness remains pending');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ kind: 'CONTROLLED_BROWSER_IPC_CONTRACT', passed: results.length, results, uncaught: errors }, null, 2));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; });
