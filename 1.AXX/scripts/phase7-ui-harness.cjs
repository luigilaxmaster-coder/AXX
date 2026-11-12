/** Phase 7 UI harness: controlled browser + fake native host. Proves DOM/visual contracts only, never native Windows behaviour.
 *  node phase7-ui-harness.cjs inventory            -> control inventory of the three areas (JSON on stdout)
 *  node phase7-ui-harness.cjs shots <dir> [tag]    -> light/dark screenshots of every area
 *  node phase7-ui-harness.cjs test                 -> regression assertions (exit code 1 on failure) */
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const bundled = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = bundled('playwright');
const root = path.join(__dirname, '..'), [mode = 'test', outDir = 'phase7-shots', tag = 'after'] = process.argv.slice(2);
const VIEWS = ['settings', 'ai', 'appearance', 'agent', 'sound', 'lab', 'personalize', ...(process.env.P7_EXTRA || '').split(',').filter(Boolean)];

const fakeNative = () => {
  localStorage.setItem('axx.companion.v4', JSON.stringify({ version: 4, prefs: { provider: 'bridge', selection_mode: 'manual', apiConnection: 'Ollama local', model: 'qwen3:4b' } }));
  window.__calls = [];
  const chat = { id: 'p7-chat', title: 'Fase 7', messages: [], draft: '', draft_at: Date.now(), updated: Date.now(), mode: 'ask', context: [], links: [], connect_id: 'p7-connect', shared_id: 'p7-shared', memory_scope: { task_id: 'p7-chat', generation: 0 } };
  const providers = [{ name: 'Ollama local', kind: 'ollama', model: 'qwen3:4b', base_url: 'http://127.0.0.1:11434/v1', enabled: true, has_key: false, free_confirmed: true, billing_allowed: false, capabilities: ['text'], tasks: ['chat'] }];
  const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1660, spaceRight: 260, spaceAbove: 800, spaceBelow: 240 };
  window.__TAURI__ = { core: { invoke: async (name, args) => {
    window.__calls.push({ name, path: args?.path, method: args?.method, body: args?.body, request: args?.request });
    if (name === 'dictation_shortcut') return { registered: true, shortcut: args?.shortcut || { key: 68, modifiers: 7, activation: 'toggle' } };
    if (name === 'dictation_control') { if (args.request.action === 'audio_devices') return { devices: [] }; throw Error('Unexpected capture or insertion in visual fixture'); }
    if (name === 'native_status') return { native: true, backendReady: true, backendError: null, shortcut: 'Alt+Shift+A', restoreShortcutAvailable: true, restoreShortcutError: null, alwaysOnTop: true, timer: null, dataDirectory: 'PHASE7_FIXTURE', desktop };
    if (name === 'desktop_layout') return { ...desktop, ...args };
    if (name !== 'backend_request') return null;
    const { path, body } = args;
    if (path === '/axx-api/prompts/compose') return { version: 'fixture', mode: body.mode, text: 'fixture' };
    if (path === '/axx-api/chat/migrate') return { id: chat.id };
    if (path === '/axx-api/chat/conversations') return { conversations: [chat], groups: [], default_mode: 'ask' };
    if (path.startsWith('/axx-api/chat/conversations?id=')) return structuredClone(chat);
    if (path === '/axx-api/chat/save') return { saved: true };
    if (path === '/axx-api/chat/operations') return { operations: [] };
    if (path === '/axx-api/chat/profile') return window.__profile = body && Object.keys(body).length ? body : (args.method === 'POST' ? {} : window.__profile || {});
    if (path === '/axx-api/status') return { ready: true, provider: 'Fixture', details: { providers: providers.map(p => ({ ...p, state: 'ready_locally' })) } };
    if (path === '/axx-api/models') return { models: ['qwen3:4b'] };
    if (path === '/axx-api/providers') return { providers };
    if (path === '/axx-api/providers/discover') return { models: ['qwen3:4b', 'llama3.2:3b'] };
    if (path === '/axx-api/providers/save') return { saved: true };
    if (path === '/axx-api/providers/probe') return { text: 'Respuesta de fixture', axx_router: { provider: window.__probeBad ? 'otra-ruta' : body.provider_name, model: body.model } };
    if (path === '/axx-api/model-candidates') return { candidates: [] };
    if (path.startsWith('/axx-api/keyless/')) return { state: 'idle', tasks: {} };
    if (path === '/axx-api/speech/status') return { asr: { available: true } };
    if (path === '/axx-api/speech/models') return { models: [{ id: 'parakeet-tdt-0.6b-v3', family: 'parakeet', engine: 'transcribe-cpp', available: true }, { id: 'whisper-small', family: 'whisper', engine: 'transcribe-cpp', available: true }, { id: 'canary-180m-flash', family: 'canary', engine: 'transcribe-cpp', available: false }] };
    if (path === '/axx-api/speech/voices') return { available: true, engine: 'windows-sapi', voices: [{ name: 'Fixture voice', language: 'es-ES', enabled: true }] };
    if (path.startsWith('/axx-api/commands?')) return { commands: [], counts: { imported: 0, enabled: 0, blocked: 0, verified_operations: 0 } };
    if (path === '/axx-api/learning/actions') return { actions: [] };
    if (path.startsWith('/axx-api/learning/plans')) return { plans: [] };
    if (path === '/axx-api/recipes') return { recipes: [] };
    if (path === '/axx-api/identity') return { identity: null };
    return {};
  } }, event: { listen: async () => () => {} } };
};

// Every control with an id inside the areas this phase reorganises; their handlers must survive the regrouping.
const inventory = () => {
  const describe = view => {
    const el = document.getElementById('view-' + view); if (!el) return null;
    const outline = [...el.children].map(c => (c.tagName.toLowerCase() + (c.id ? '#' + c.id : '') + (c.className && typeof c.className === 'string' ? '.' + c.className.trim().split(/\s+/).join('.') : '') + (c.hidden ? ' [hidden]' : '') + ' :: ' + (c.querySelector('summary,strong,h3,legend,.section-title')?.textContent || c.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 70)));
    const controls = [...el.querySelectorAll('button,input,select,textarea,summary,a[href]')].map(c => (c.id || '') + '|' + c.tagName.toLowerCase() + (c.type ? ':' + c.type : '') + '|' + (c.getAttribute('aria-label') || c.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 50));
    return { outline, controls, ids: [...el.querySelectorAll('[id]')].map(c => c.id) };
  };
  return Object.fromEntries(['settings', 'ai', 'appearance', 'agent', 'sound', 'lab', 'personalize'].map(v => [v, describe(v)]));
};

(async () => {
  const html = fs.readFileSync(path.join(root, 'Axx.html'), 'utf8');
  const server = http.createServer((req, res) => {
    const file = path.join(root, 'scripts', path.basename(req.url.split('?')[0]));
    if (req.url.startsWith('/scripts/') && fs.existsSync(file)) { res.writeHead(200, { 'Content-Type': req.url.includes('.css') ? 'text/css' : 'application/javascript' }); return res.end(fs.readFileSync(file)); }
    res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  let failed = 0;
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1040 } }); page.setDefaultTimeout(15000);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(fakeNative);
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.desktop?.ready && Axx.chatWorkspace?.ready && !Axx.companion.connecting);
    await page.waitForTimeout(600);
    const open = async id => { await page.evaluate(id => Axx.companion.openFeature(id), id); await page.waitForTimeout(450); };
    const theme = t => page.evaluate(t => Axx.interfaceTheme.apply(t), t);

    if (mode === 'contrast') {
      // WCAG: text 4.5:1 (3:1 when large), field boundaries 3:1; labelled buttons 1.5:1 (their text identifies them). Colours are composited over the real ancestors.
      const audit = () => { const parse = c => { const f = c.startsWith('color(') ? 255 : 1, m = c.replace('color(srgb', '').match(/[\d.]+(e-?\d+)?/g).map(Number); return [m[0] * f, m[1] * f, m[2] * f, m.length < 4 ? 1 : m[3]]; }; // color-mix() computes to color(srgb 0..1)
        const over = (f, b) => [0, 1, 2].map(i => f[i] * f[3] + b[i] * (1 - f[3])).concat(1);
        const bgOf = n => { const stack = []; for (; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c[3] > 0) { stack.push(c); if (c[3] === 1) break; } } let b = [18, 18, 18, 1]; for (const c of stack.reverse()) b = over(c, b); return b; };
        const lum = c => c.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
        const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
        const view = [...document.querySelectorAll('#panel>.panel-view')].find(v => !v.hidden) || document.getElementById('panel'), out = [];
        const name = n => (n.id ? '#' + n.id : n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\s+/)[0] : '')) + ' "' + (n.textContent || n.value || '').trim().replace(/\s+/g, ' ').slice(0, 24) + '"';
        for (const n of document.getElementById('panel').querySelectorAll('*')) { if (!n.getClientRects().length || n.closest('[data-palette],.axx-theme-sample,canvas,svg')) continue; const s = getComputedStyle(n);
          if (s.visibility === 'hidden' || +s.opacity < .5) continue; const bg = bgOf(n);
          if ([...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim()) && !n.disabled) { const r = ratio(over(parse(s.color), bg), bg), big = parseFloat(s.fontSize) >= 18.66; if (r < (big ? 3 : 4.5)) out.push(['text', r.toFixed(2), name(n)]); }
          if (n.matches('button,select,textarea,input:not([type=range]):not([type=checkbox]):not([type=radio]):not([type=color]):not([type=file])') && !n.disabled) { const outer = bgOf(n.parentElement), edge = parseFloat(s.borderTopWidth) ? over(parse(s.borderTopColor), outer) : bg, line = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) ? over(parse(s.outlineColor), outer) : bg;
            const r = Math.max(ratio(edge, outer), ratio(line, outer), ratio(bg, outer)); if (r < (n.tagName === 'BUTTON' ? 1.5 : 3) && !n.closest('[role=tablist]') && s.backgroundColor !== 'rgba(0, 0, 0, 0)') out.push(['edge', r.toFixed(2), name(n)]); } }
        return out; };
      let total = 0; for (const t of ['light', 'dark']) { await theme(t); for (const v of [...VIEWS, 'chat', 'voices']) {
        if (!await page.evaluate(v => Axx.FEATURES.some(f => f.id === v), v)) continue; await open(v);
        if (v === 'settings') await page.evaluate(() => { for (const d of document.querySelectorAll('#view-settings details')) d.open = true; }); await page.waitForTimeout(200);
        const bad = await page.evaluate(audit), kinds = k => bad.filter(b => b[0] === k).length; total += bad.length;
        console.log(`${t.padEnd(5)} ${v.padEnd(12)} text:${String(kinds('text')).padStart(3)} edge:${String(kinds('edge')).padStart(3)}  ${process.env.P7_VERBOSE ? '\n   ' + bad.map(b => b.join(' ')).join('\n   ') : bad.slice(0, 3).map(b => b[1] + ' ' + b[2]).join(' | ')}`); } }
      console.log('total below threshold:', total); return;
    }

    if (mode === 'outline') { await open(outDir); console.log(await page.evaluate(v => { const tag = n => n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\s+/).join('.') : '') + (n.hidden ? ' [hidden]' : '');
      const walk = (n, d) => d > 2 ? [] : [...n.children].flatMap(c => ['  '.repeat(d) + tag(c) + ' :: ' + c.textContent.trim().replace(/\s+/g, ' ').slice(0, 40), ...walk(c, d + 1)]); return walk(document.getElementById('view-' + v), 0).join('\n'); }, outDir)); return; }
    if (mode === 'inventory') { process.stdout.write(JSON.stringify({ errors, views: await page.evaluate(inventory) }, null, 1)); return; }

    if (mode === 'shots') {
      fs.mkdirSync(outDir, { recursive: true });
      for (const t of ['light', 'dark']) { await theme(t); for (const v of VIEWS) {
        if (!await page.evaluate(v => Axx.FEATURES.some(f => f.id === v), v)) continue;
        await open(v);
        // Full-height capture of the scrolling view so nothing below the fold is left unreviewed.
        const el = await page.$('#view-' + v); if (!el || !await el.isVisible()) continue;
        const panel = await page.$('#panel');
        await panel.screenshot({ path: path.join(outDir, `${tag}-${v}-${t}-fold.png`) }); // real 680x720 panel
        if (t === 'dark' && !process.env.P7_FULL_BOTH) continue;                           // full-length review once per view keeps evidence small
        const tall = Math.min(9000, await el.evaluate(n => n.scrollHeight) + 220); if (process.env.P7_DEBUG) console.log(v, 'scrollHeight', tall - 220);
        await page.setViewportSize({ width: 1920, height: tall + 40 });
        const saved = await page.evaluate(([v, tall]) => { const p = document.getElementById('panel'), el = document.getElementById('view-' + v), old = [p.style.cssText, el.style.cssText];
          for (const [k, val] of [['top', '0px'], ['height', tall + 'px'], ['max-height', 'none']]) p.style.setProperty(k, val, 'important');
          for (const [k, val] of [['overflow', 'visible'], ['max-height', 'none'], ['height', 'auto'], ['flex', 'none']]) el.style.setProperty(k, val, 'important'); return old; }, [v, tall]);
        // The resident layout manager re-applies its own inline size; hold ours until it settles.
        for (let i = 0; i < 12; i++) { await page.waitForTimeout(120); await page.evaluate(([v, tall]) => { const p = document.getElementById('panel'), el = document.getElementById('view-' + v);
          for (const [k, val] of [['top', '0px'], ['height', tall + 'px'], ['max-height', 'none']]) p.style.setProperty(k, val, 'important');
          for (const [k, val] of [['overflow', 'visible'], ['max-height', 'none'], ['height', 'auto'], ['flex', 'none']]) el.style.setProperty(k, val, 'important'); }, [v, tall]); }
        await panel.screenshot({ path: path.join(outDir, `${tag}-${v}-${t}-full.png`) });
        await page.evaluate(([v, old]) => { document.getElementById('panel').style.cssText = old[0]; document.getElementById('view-' + v).style.cssText = old[1]; }, [v, saved]);
        await page.setViewportSize({ width: 1920, height: 1040 }); await page.waitForTimeout(150);
      } }
      for (const t of ['light', 'dark']) { await theme(t); await page.evaluate(() => Axx.phase7?.personalize('motion')); await page.waitForTimeout(400);
        if (await page.$('.p7-tabs')) await (await page.$('#panel')).screenshot({ path: path.join(outDir, tag + '-personalize-motion-' + t + '-fold.png') }); }
      await theme('light');
      console.log('shots ->', outDir, errors.length ? 'pageerrors: ' + errors.join(' | ') : ''); return;
    }

    const check = async (name, fn) => { try { await fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + ' :: ' + String(e.message).split('\n')[0]); } };
    const baseline = JSON.parse(fs.readFileSync(path.join(__dirname, 'phase7-control-baseline.json'), 'utf8'));
    const now = await page.evaluate(inventory);
    await check('no page errors at startup', async () => assert.deepEqual(errors, []));
    await check('every pre-phase-7 control id still exists exactly once', async () => {
      const all = await page.evaluate(() => [...document.querySelectorAll('[id]')].map(n => n.id));
      const missing = [], dup = [];
      for (const v of Object.keys(baseline)) for (const id of baseline[v] || []) { const n = all.filter(x => x === id).length; if (!n) missing.push(id); if (n > 1) dup.push(id); }
      assert.deepEqual({ missing, dup }, { missing: [], dup: [] });
    });
    for (const v of VIEWS) await check(`${v}: opens and no control is unreachable`, async () => {
      if (!now[v]) return; await open(v);
      // A control is reachable when it is displayed, or sits inside a closed <details> the user can open, or was hidden by its own module.
      const lost = await page.evaluate(v => { const view = document.getElementById('view-' + v), out = [];
        for (const c of view.querySelectorAll('button,input:not([type=file]),select,textarea')) {
          if (c.hidden || c.closest('[hidden]')) continue; let n = c, ok = c.getClientRects().length > 0;
          for (; !ok && n && n !== view; n = n.parentElement) if (n.tagName === 'DETAILS' && !n.open) ok = true;
          if (!ok) out.push(c.id || c.textContent.trim().slice(0, 30));
        } return out; }, v);
      assert.deepEqual(lost, []);
    });
    const ev = (fn, arg) => page.evaluate(fn, arg);
    await check('settings: four core groups first, in order, then connections', async () => { await open('settings');
      assert.deepEqual(await ev(() => [...document.querySelectorAll('#view-settings>.p7-group')].map(g => g.id)), ['p7-windows', 'p7-data', 'p7-backup', 'p7-performance', 'p7-connections', 'p7-personal']); });
    await check('settings: destructive and restore controls are unambiguous', async () => {
      assert.equal(await ev(() => !!document.getElementById('clear-data').closest('.p7-row.p7-danger')), true);
      assert.equal(await ev(() => !!document.getElementById('import-all').closest('.p7-row.p7-caution')), true);
      assert.equal(await ev(() => document.getElementById('backup-all').closest('.p7-group').id), 'p7-backup');
      assert.notEqual(await ev(() => getComputedStyle(document.getElementById('clear-data')).color), await ev(() => getComputedStyle(document.getElementById('import-all')).color)); });
    await check('settings: a module that scrolls to its card opens the fold that holds it', async () => {
      assert.equal(await ev(() => document.getElementById('mcp-connections').closest('details').open), false);
      await ev(() => document.getElementById('mcp-connections').scrollIntoView({ block: 'start' }));
      assert.equal(await ev(() => document.getElementById('mcp-connections').closest('details').open), true); });
    await check('settings: existing handlers still fire after regrouping', async () => {
      await ev(() => { window.__clicked = []; for (const id of ['recenter', 'summon-settings', 'reset-position']) document.getElementById(id).addEventListener('click', () => window.__clicked.push(id)); });
      await page.click('#toggle-diagnostics'); assert.equal(await ev(() => document.getElementById('diagnostics').hidden), false);
      await page.click('#recenter'); assert.deepEqual(await ev(() => window.__clicked), ['recenter']);
      assert.ok(await ev(() => window.__calls.some(c => c.name !== 'backend_request' && c.name !== 'native_status'))); });
    await check('ai: configuration alone is never shown as verified', async () => { await open('ai');
      assert.equal(await ev(() => Axx.companion.brain.inferenceVerified), false);
      assert.notEqual(await ev(() => document.getElementById('p7-ai-state').dataset.state), 'ok');
      assert.equal(await ev(() => document.getElementById('p7-ai-model').textContent), 'qwen3:4b'); });
    await check('ai: a failed probe keeps the model unverified', async () => {
      await ev(() => { window.__probeBad = true; }); await page.click('#p7-ai-test');
      await page.waitForFunction(() => /no confirm/.test(document.getElementById('p7-ai-result').textContent));
      assert.notEqual(await ev(() => document.getElementById('p7-ai-state').dataset.state), 'ok'); });
    await check('ai: Probar conexión runs the owner probe and only then reports a checked response', async () => {
      await ev(() => { window.__probeBad = false; }); await page.click('#p7-ai-test');
      await page.waitForFunction(() => /Respuesta recibida/.test(document.getElementById('p7-ai-result').textContent));
      assert.equal(await ev(() => window.__calls.filter(c => c.path === '/axx-api/providers/probe').length), 2);
      assert.equal(await ev(() => document.getElementById('p7-ai-state').dataset.state === 'ok'), await ev(() => Axx.companion.brain.inferenceVerified === true)); });
    await check('ai: cost and capabilities are stated for the model in use', async () => {
      assert.match(await ev(() => document.getElementById('p7-ai-cost').textContent), /Sin coste/);
      assert.match(await ev(() => document.getElementById('p7-ai-caps').textContent), /declaradas/); });
    await check('ai: each option shows only its own controls', async () => {
      for (const m of ['local', 'chatgpt', 'api']) { await page.click('#tab-mode-' + m);
        assert.deepEqual(await ev(() => ['local', 'chatgpt', 'api'].filter(k => !document.getElementById('subpanel-' + k).hidden)), [m]); }
      assert.equal(await ev(() => document.getElementById('gateway-controls').hidden), true);
      await page.selectOption('#provider-kind', 'freellmapi'); await page.waitForTimeout(50);
      assert.equal(await ev(() => document.getElementById('gateway-controls').hidden), false);
      await page.selectOption('#provider-kind', 'ollama'); });
    await check('keyboard: Tab reaches controls and shows a focus ring in both themes', async () => { for (const t of ['light', 'dark']) { await theme(t); await open('settings');
      await ev(() => document.getElementById('always-top').focus()); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
      const ring = await ev(() => { const s = getComputedStyle(document.activeElement); return [document.activeElement.id, s.outlineStyle, parseFloat(s.outlineWidth)]; });
      assert.equal(ring[0], 'always-top'); assert.notEqual(ring[1], 'none'); assert.ok(ring[2] >= 2); } await theme('light'); });
    await check('personalize: one entry with five tabs, each showing its owner controls', async () => { await open('personalize');
      assert.equal(await ev(() => document.querySelectorAll('.p7-tabs [role=tab]').length), 5);
      for (const [key, view, id] of [['shape', 'appearance', 'forms'], ['sound', 'sound', 'sound-restore'], ['agent', 'agent', 'agent-name'], ['motion', 'personalize', 'id20-motion-grid'], ['interface', 'personalize', 'axx-interface-font']]) {
        await ev(key => Axx.phase7.personalize(key), key); await page.waitForTimeout(350);
        assert.equal(await ev(view => !document.getElementById('view-' + view).hidden && !!document.querySelector('#view-' + view + ' .p7-tabs [aria-selected=true]'), view), true, key);
        assert.equal(await page.locator('#' + id).isVisible(), true, id); assert.equal(await ev(() => document.getElementById('panel-title').textContent), 'Personalizar AXX'); } });
    await check('personalize: arrow keys move between tabs', async () => { await ev(() => Axx.phase7.personalize('interface')); await page.waitForTimeout(300);
      await page.focus('.p7-tabs [aria-selected=true]'); await page.keyboard.press('ArrowRight'); await page.waitForTimeout(300);
      assert.equal(await ev(() => document.querySelector('.p7-tabs [aria-selected=true]').dataset.p7Tab), 'motion'); });
    await check('personalize: shared controls are one node, shown in whichever entry is open', async () => {
      for (const [view, sel] of [['personalize', '#view-personalize'], ['settings', '#view-settings'], ['personalize', '#view-personalize'], ['settings', '#view-settings']]) { if (view === 'settings') await open(view); else { await ev(() => Axx.phase7.personalize('interface')); await page.waitForTimeout(350); }
        assert.equal(await ev(sel => !!document.querySelector(sel + ' #axx-interface-theme') && document.querySelectorAll('#axx-interface-theme').length === 1, sel), true, view);
        assert.equal(await page.locator('[data-axx-theme=dark]').isVisible(), true); }
      assert.equal(await ev(() => document.getElementById('reduced-motion').closest('.p7-group').id), 'p7-performance'); });
    await check('personalize: theme, font and widget size still persist through their owner', async () => { await ev(() => Axx.phase7.personalize('interface')); await page.waitForTimeout(350);
      await page.click('[data-axx-theme=dark]'); await page.selectOption('#axx-interface-font', 'serif');
      await ev(() => { const n = document.getElementById('axx-widget-size'); n.value = '110'; n.dispatchEvent(new Event('input', { bubbles: true })); });
      const saved = await ev(() => [localStorage.getItem('axx.interface.theme'), JSON.parse(localStorage.getItem('axx.interface.customization'))]);
      assert.equal(saved[0], 'dark'); assert.equal(saved[1].font, 'serif'); assert.equal(saved[1].widgetSize, 110);
      await page.click('#axx-theme-reset'); await page.click('#axx-widgets-reset'); await page.click('[data-axx-theme=light]');
      assert.equal(await ev(() => document.body.dataset.uiTheme), 'light'); });
    await check('layout: no view scrolls sideways at the default and at a narrow panel width', async () => { for (const width of [null, 380]) for (const v of ['settings', 'ai', 'personalize', 'agent', 'sound', 'appearance']) {
      await open(v);
      const wide = await ev(([v, width]) => { const p = document.getElementById('panel'), el = document.getElementById('view-' + v), old = p.style.cssText; if (width) p.style.setProperty('width', width + 'px', 'important');
        const r = el.scrollWidth - el.clientWidth; p.style.cssText = old; return r; }, [v, width]);
      assert.ok(wide <= 1, v + ' overflows by ' + wide + 'px at ' + (width || 'default')); } });
    await check('personalize: the panel keeps its size and place across tabs and saved positions are not rewritten', async () => {
      await open('settings'); await open('sound'); await page.waitForTimeout(500);
      const box = () => ev(() => { const r = document.getElementById('panel').getBoundingClientRect(); return [r.x, r.y, r.width, r.height].map(Math.round).join(','); });
      const first = await box(), stored = await ev(() => localStorage.getItem('axx.resident.panel-pos')), positions = await ev(() => JSON.stringify(Axx.resident.panelPositions));
      for (const key of ['shape', 'interface', 'motion', 'agent', 'sound']) { await ev(key => Axx.phase7.personalize(key), key); await page.waitForTimeout(500); assert.equal(await box(), first, key); }
      assert.equal(await ev(() => localStorage.getItem('axx.resident.panel-pos')), stored);
      assert.equal(await ev(() => JSON.stringify(Axx.resident.panelPositions)), positions, 'navigation must not mutate saved sizes in RAM either');
      await open('settings'); await page.waitForTimeout(500); await open('appearance'); await page.waitForTimeout(500);
      assert.equal((await box()).split(',')[2], '680', 'a view entered on its own keeps its own default width'); });
    await check('shape: four groups, renderer controls untouched and still driving the preview', async () => { await open('appearance'); await page.waitForTimeout(300);
      assert.deepEqual(await ev(() => [...document.querySelectorAll('#view-appearance>.p7-group,#view-appearance>details.p7-more')].map(n => n.id)), ['p7-shape-preview', 'p7-shape-form', 'p7-shape-material', 'p7-shape-advanced']);
      assert.equal(await ev(() => document.getElementById('forms').closest('.p7-group').id + '/' + document.getElementById('material-roughness').closest('.p7-group').id + '/' + document.getElementById('id20-profiles').closest('details').id), 'p7-shape-form/p7-shape-material/p7-shape-advanced');
      const before = await ev(() => [document.getElementById('appearance-apply').disabled, document.getElementById('scale').value, document.getElementById('material-roughness').value]);
      await page.locator('#forms .form-option:not(.active)').first().click(); await page.waitForTimeout(200);
      assert.equal(await ev(() => document.getElementById('appearance-apply').disabled), false, 'choosing a form starts a preview');
      await page.click('#appearance-restore'); await page.waitForTimeout(200);
      assert.deepEqual(await ev(() => [document.getElementById('appearance-apply').disabled, document.getElementById('scale').value, document.getElementById('material-roughness').value]), before);
      await page.click('#p7-shape-advanced>summary'); assert.equal(await page.locator('#export-png').isVisible(), true); await page.click('#p7-shape-advanced>summary'); });
    await check('chat (light): controls show an edge and keep their geometry and focus ring', async () => { await theme('light'); await open('chat'); await page.waitForTimeout(300);
      const o = await ev(() => { const s = getComputedStyle(document.getElementById('cw-search')); return [s.outlineStyle, s.outlineOffset, s.borderTopWidth]; });
      assert.equal(o[0], 'solid'); assert.equal(o[1], '-1px');
      await page.focus('#cw-search'); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
      assert.equal(await ev(() => getComputedStyle(document.getElementById('cw-search')).outlineWidth), '2px'); });
    await check('personalize: distinct saved layouts survive tabs; explicit resize and drag persist only for the entry view', async () => {
      await open('settings');
      const original = await ev(() => structuredClone(Axx.resident.panelPositions));
      try {
        await ev(() => { Object.assign(Axx.resident.panelPositions, { 'panel:sound': {width:440,height:600,relX:-700,relY:-500}, 'panel:appearance': {width:630,height:680}, 'panel:personalize': {width:510,height:640} }); Axx.resident.savePanelPositions(); });
        await open('sound'); await page.waitForTimeout(300);
        const saved = await ev(() => localStorage.getItem('axx.resident.panel-pos'));
        for (const key of ['shape','interface','motion','agent','sound']) { await ev(key => Axx.phase7.personalize(key), key); await page.waitForTimeout(200); assert.equal(Math.round((await page.locator('#panel').boundingBox()).width),440); }
        assert.equal(await ev(() => localStorage.getItem('axx.resident.panel-pos')),saved);
        const handle = await page.locator('#panel .resident-resize-handle').boundingBox(); assert.ok(handle);
        await page.mouse.move(handle.x+handle.width/2,handle.y+handle.height/2); await page.mouse.down(); await page.mouse.move(handle.x+handle.width/2+45,handle.y+handle.height/2+25,{steps:8}); await page.mouse.up(); await page.waitForTimeout(350);
        const resized = await ev(() => structuredClone(Axx.resident.panelPositions['panel:sound'])); assert.ok(resized.width>470 && resized.height>610);
        const head = await page.locator('#panel-title').boundingBox(); assert.ok(head);
        await page.mouse.move(head.x+head.width/2,head.y+head.height/2); await page.mouse.down(); await page.mouse.move(head.x+head.width/2+30,head.y+head.height/2+20,{steps:8}); await page.mouse.up(); await page.waitForTimeout(350);
        const moved = await ev(() => JSON.parse(localStorage.getItem('axx.resident.panel-pos'))['panel:sound']); assert.notEqual(moved.relX,resized.relX);
        assert.deepEqual(await ev(() => Axx.resident.panelPositions['panel:appearance']),{width:630,height:680});
        await page.reload(); await page.waitForFunction(() => Axx.desktop?.ready && Axx.chatWorkspace?.ready && !!Axx.phase7); await open('sound');
        assert.deepEqual(await ev(() => Axx.resident.panelPositions['panel:sound']),moved);
        await open('settings'); await open('appearance'); assert.equal(Math.round((await page.locator('#panel').boundingBox()).width),630);
      } finally { await ev(saved => { Axx.resident.panelPositions=saved;Axx.resident.savePanelPositions();Axx.resident.schedule(); },original); }
    });
    await check('integration: one dictation owner in Sound, quick access, model persistence and no implicit permissions', async () => {
      await page.waitForFunction(() => document.querySelector('#axx-dictation [data-engine] option[value=parakeet]'));
      assert.equal(await page.locator('#p7-dictation #axx-dictation').count(),1);
      for (const key of ['shape','interface','motion','agent','sound']) await ev(key => Axx.phase7.personalize(key),key);
      assert.equal(await page.locator('#axx-dictation').count(),1); assert.equal(await page.locator('#axx-dictation-open').count(),1);
      await open('voices'); await page.locator('#axx-dictation-open').click();
      assert.equal(await page.locator('[data-p7-tab=sound]').getAttribute('aria-selected'),'true');
      assert.equal(await page.locator('#axx-dictation').getAttribute('open'),'');
      for (const t of ['light','dark']) { await theme(t); assert.ok(await ev(() => { const n=document.querySelector('#view-sound'); return n.scrollWidth<=n.clientWidth+1; }));
        const ratio = await ev(() => { const s=getComputedStyle(document.querySelector('#axx-dictation [data-file]')); const lum=color=>color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);const a=lum(s.color),b=lum(s.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05); });
        assert.ok(ratio>=4.5,'File selection text contrast '+t+': '+ratio);
      }
      await page.locator('#axx-dictation [data-engine]').selectOption('parakeet');
      assert.equal(await page.locator('#axx-dictation [data-config=model]').inputValue(),'parakeet-tdt-0.6b-v3');
      await page.locator('#axx-dictation [data-config=language]').fill('es');await page.locator('#axx-dictation [data-save]').click();
      assert.equal(await ev(() => Axx.dictation.settings().language),'es');
      await page.locator('#axx-dictation [data-config=language]').fill('auto');
      await page.locator('#axx-dictation [data-save]').click();
      assert.equal(await ev(() => Axx.dictation.settings().language),'auto');
      assert.equal(await ev(() => Axx.dictation.settings().model),'parakeet-tdt-0.6b-v3');
      await page.reload(); await page.waitForFunction(() => Axx.phase7 && document.querySelector('#axx-dictation [data-engine]')?.value==='parakeet');
      assert.equal(await ev(() => Axx.dictation.settings().model),'parakeet-tdt-0.6b-v3');
      assert.equal(await ev(() => Axx.dictation.status().state),'OFF');
      assert.equal(await ev(() => Axx.dictation.status().microphone_open),false);
      assert.equal(await ev(() => __calls.filter(c => c.request && c.request.action!=='audio_devices').length),0);
      assert.equal(await ev(() => __calls.filter(c => /(?:computer-use\/configure|microphone\/begin)/.test(c.path || '')).length),0);
      await ev(() => Axx.dictation.configure({model:''}));
    });
    /*P7-CHECKS*/
    await check('no page errors after interaction', async () => assert.deepEqual(errors, []));
  } finally { await browser.close(); server.close(); }
  if (mode === 'test') { console.log(failed ? `\n${failed} FAILED` : '\nphase7-ui: all checks passed'); process.exitCode = failed ? 1 : 0; }
})();
