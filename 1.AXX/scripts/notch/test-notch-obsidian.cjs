/* Real renderer/browser integration with controlled external-provider responses.
 * PNGs are app captures; external messages/quotas in this suite are test fixtures.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { chromium } = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(__dirname, '../../../build/obsidian-rework/after'); fs.mkdirSync(output, { recursive: true });
const prefs = require('./notch-snapshot.js');
assert.equal(prefs.normalizePreferences({ material: 'broken', accent: '#bad', surfaceScale: Infinity }).material, 'solid');
assert.equal(prefs.normalizePreferences({ material: 'translucent', accent: 'sage', surfaceScale: 'large' }).accent, 'sage');
assert.equal(prefs.normalizePreferences({ expandedScalePercent: Infinity }).expandedScalePercent, 100);
assert.equal(prefs.normalizePreferences({ expandedScalePercent: 70, compactWidthPx: 10 }).expandedScalePercent, 80);
assert.equal(prefs.normalizePreferences({ compactWidthPx: 10 }).compactWidthPx, 184);
const server = http.createServer((req, res) => {
  const file = req.url.startsWith('/scripts/') ? require('../test-static-assets.cjs').scriptPath(req.url.split('?')[0]) : path.join(root, 'Axx.html');
  if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : 'text/html'); res.end(fs.readFileSync(file));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  const errors = [], findings = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 816 } });
    page.on('pageerror', error => (errors.push(error.stack || error.message), console.error('PAGE:', error.message)));
    await page.addInitScript(() => {
      window.__nativeListeners = {};
      window.__TAURI__ = { core: { invoke: async (cmd, args = {}) => {
        if (cmd === 'native_status') return { native: true, backendReady: true, alwaysOnTop: true, shortcut: 'Ctrl+Alt+Space', shortcutError: null, timer: null, autostart: false };
        if (cmd === 'desktop_layout') return { width: 1536, height: 816, scaleFactor: 1, ready: true, displayId: 'primary', dockEpoch: args.dockEpoch, geometryRevision: args.geometryRevision };
        if (cmd === 'hit_map') return { accepted: true, epoch: args.map?.epoch, revision: args.map?.revision };
        return {};
      } }, event: { listen: async (name, callback) => { (window.__nativeListeners[name] ||= []).push(callback); return () => {}; } } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(() => window.Axx?.notch);
    await page.evaluate(() => { Axx.notch.setPreferences({ enabled: true }); Axx.notch.dockNow(); });
    await page.waitForFunction(() => Axx.notch.getState().physical === 'docked');
    const portrait = await page.evaluate(() => {
      const r = Axx.app.renderer, original = { hidden: r.hidden, canvas: r.canvas, transition: r.transition, settings: JSON.stringify(r.settings), studio: JSON.stringify(r.studio) };
      const old = r.tendril; let tendrilCalls = 0; r.tendril = () => tendrilCalls++;
      let result;
      try { result = r.captureIdentityPNG(128); } finally { r.tendril = old; }
      const img = document.querySelector('#notch-spine-btn img');
      return { hasPortrait: img?.src.startsWith('data:image/png'), result: result?.startsWith('data:image/png'), tendrilCalls,
        restored: r.hidden === original.hidden && r.canvas === original.canvas && r.transition === original.transition && JSON.stringify(r.settings) === original.settings && JSON.stringify(r.studio) === original.studio };
    });
    assert.deepEqual(portrait, { hasPortrait: true, result: true, tendrilCalls: 0, restored: true }); findings.push(portrait);
    await page.click('#notch-spine-btn'); await page.waitForTimeout(700);
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '01-home.png') });
    assert(await page.evaluate(() => document.querySelector('.notch-quick-action:last-child').getBoundingClientRect().bottom <= document.querySelector('#notch-body').getBoundingClientRect().bottom), 'All three home actions must fit');
    for (const [name, values] of [
      ['obsidian', { styleDirection: 'neutral-monolith', material: 'solid', density: 'compact', contrast: 'standard' }],
      ['living', { styleDirection: 'identity-accent', material: 'translucent', density: 'compact', contrast: 'standard' }],
      ['spatial', { styleDirection: 'identity-accent', material: 'solid', density: 'comfortable', contrast: 'high' }]
    ]) {
      await page.evaluate(values => Axx.notch.setPreferences(values), values); await page.waitForTimeout(550);
      await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, `direction-${name}-home.png`) });
    }
    await page.evaluate(() => Axx.notch.setPreferences({ styleDirection: 'identity-accent', material: 'solid', density: 'compact', contrast: 'standard' }));
    const layoutAudit = async name => {
      const audit = await page.evaluate(() => {
        const shell = document.querySelector('#axx-notch-shell'), footer = shell.querySelector('.notch-context-footer');
        const r = shell.getBoundingClientRect(), f = footer.getBoundingClientRect();
        return { horizontalOverflow: shell.scrollWidth > shell.clientWidth + 1, footerFits: f.right <= r.right + 1 && f.bottom <= r.bottom + 1, width: r.width, height: r.height };
      });
      assert.equal(audit.horizontalOverflow, false, name + ' horizontal overflow'); assert.equal(audit.footerFits, true, name + ' footer clipping'); findings.push({ name, ...audit });
    };
    await layoutAudit('home');
    await page.click('#notch-customize-btn'); await page.waitForTimeout(700);
    await page.click('[data-profile="comfortable"]'); await page.waitForTimeout(700);
    assert.equal(await page.evaluate(() => Axx.notch.getPreferences().density), 'comfortable');
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '02-personalization.png') });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#notch-appearance-sheet').isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'notch-customize-btn');
    await page.evaluate(() => Axx.notch.setPreferences({ density: 'compact', surfaceScale: 'standard', contrast: 'standard' }));
    // Inject controlled external services, never a paid or real model request.
    await page.evaluate(() => {
      const original = Axx.backendRequest; window.__directSends = [];
      Axx.backendRequest = async (method, endpoint, body) => {
        if (endpoint.startsWith('/axx-api/connect/sessions')) {
          if (window.__simulateBackendStarting) throw Error('Backend starting');
          const provider = new URL('http://test' + endpoint).searchParams.get('provider');
          return provider === 'antigravity' ? { available: false, sessions: [], reason: 'CLI no conectada (fixture)' } : { available: true, next_cursor: 'fixture-page-2', sessions: [{ id: provider + '-session', project: 'C:/Projects/AXX', title: 'Mejorar AXX (fixture)', model: 'fixture', active: false }] };
        }
        if (endpoint.startsWith('/axx-api/connect/subscriptions/setup')) return { instructions: 'Conecta la salida oficial.', settings_file: '~/.gemini/antigravity-cli/settings.json', configuration: { statusLine: { type: 'command', command: 'official-status-fixture' } } };
        if (endpoint.startsWith('/axx-api/connect/subscriptions')) {
          const provider = new URL('http://test' + endpoint).searchParams.get('provider');
          return { provider, plan: provider === 'codex' ? 'Plus' : provider === 'claude' ? 'Pro' : null, connection: provider === 'antigravity' ? 'unknown' : 'connected', source: 'Controlled fixture', verification: 'official_client', available: provider === 'codex', windows: provider === 'codex' ? [{ window_minutes: 300, remaining_percent: 72 }, { window_minutes: 10080, remaining_percent: 46 }] : [], checked_at: Date.now()/1000, reason: 'El cliente no informó un saldo.' };
        }
        if (endpoint.startsWith('/axx-api/connect/usage')) return { provider: 'codex', available: true, checked_at: Date.now()/1000, source: 'Controlled test fixture', windows: [{ window_minutes: 300, remaining_percent: 72, used_percent: 28, resets_at: Date.now()/1000 + 7200 }, { window_minutes: 10080, remaining_percent: 46, used_percent: 54, resets_at: Date.now()/1000 + 86400 }] };
        if (endpoint === '/axx-api/connect/session/start') {
          if (window.__simulateReject) throw Error('BUSY: La conversación está ocupada (HTTP 400)');
          window.__directSends.push(body);
          if (window.__simulateDisconnect) throw Error('Connection lost after admission');
          return { request_id: body.request_id, state: 'processing', response: '' };
        }
        if (endpoint.startsWith('/axx-api/connect/run')) return { request_id: window.__directSends.at(-1)?.request_id, state: 'completed', response: 'Respuesta de prueba: el proyecto y la conversación se conservaron.' };
        return original(method, endpoint, body);
      };
    });
    await page.evaluate(() => { window.__simulateBackendStarting = true; });
    await page.click('#notch-direct-chat-btn');
    await page.waitForFunction(() => document.querySelector('.notch-chat-surface [role="status"]').textContent.includes('Backend starting'));
    await page.evaluate(() => { window.__simulateBackendStarting = false; for (const callback of window.__nativeListeners['axx-backend-ready'] || []) callback({ payload: {} }); });
    await page.waitForSelector('#notch-chat-input:not(:disabled)'); await page.waitForTimeout(700);
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '03-direct-chat-fixture.png') }); await layoutAudit('chat');
    findings.push(await page.evaluate(() => ({accent:getComputedStyle(document.getElementById('axx-notch-root')).getPropertyValue('--notch-accent'),quotaColor:getComputedStyle(document.querySelector('.notch-usage-window strong')).color,sendColor:getComputedStyle(document.querySelector('.notch-chat-composer [type=submit]')).backgroundColor})));
    assert(await page.evaluate(() => {const b=document.querySelector('.notch-chat-composer [type=submit]').getBoundingClientRect(),v=document.querySelector('#notch-body').getBoundingClientRect();return b.bottom<=v.bottom;}), 'Send must be visible above footer');
    await page.getByRole('button', { name: 'Cambiar conversación', exact: true }).click();
    await page.getByRole('combobox', { name: 'Filtrar destinos' }).fill('no-coincide');
    assert.equal(await page.locator('.notch-picker-option').count(), 0);
    await page.getByRole('combobox', { name: 'Filtrar destinos' }).fill('Mejorar');
    await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
    assert.equal(await page.locator('.notch-picker-dialog').isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-label')), 'Cambiar conversación');
    assert.equal(await page.evaluate(() => window.__directSends.length), 0);
    await page.fill('#notch-chat-input', 'Mensaje de prueba sin enviar automáticamente');
    await page.evaluate(() => Axx.notch.stepProjections());
    assert.equal(await page.inputValue('#notch-chat-input'), 'Mensaje de prueba sin enviar automáticamente');
    assert.equal(await page.evaluate(() => window.__directSends.length), 0);
    await page.press('#notch-chat-input', 'Enter');
    await page.waitForFunction(() => document.querySelector('.notch-chat-response').textContent.includes('Respuesta de prueba'));
    assert.equal(await page.evaluate(() => window.__directSends.length), 1);
    await page.evaluate(() => { window.__simulateReject = true; });
    await page.fill('#notch-chat-input', 'Borrador conservado ante rechazo'); await page.press('#notch-chat-input', 'Enter');
    await page.waitForFunction(() => !document.querySelector('#notch-chat-input').disabled);
    assert.equal(await page.inputValue('#notch-chat-input'), 'Borrador conservado ante rechazo');
    assert.equal(await page.evaluate(() => window.__directSends.length), 1);
    await page.evaluate(() => { window.__simulateReject = false; window.__simulateDisconnect = true; });
    await page.press('#notch-chat-input', 'Enter');
    await page.waitForFunction(() => document.querySelector('.notch-chat-surface [role="status"]').textContent.includes('Connection lost'));
    assert.equal(await page.evaluate(() => window.__directSends.length), 2);
    assert.equal(await page.locator('#notch-chat-input').isDisabled(), true, 'Uncertain admission must not permit a duplicate send');
    await page.getByRole('button', { name: 'Actualizar conversaciones y saldo' }).click();
    await page.waitForFunction(() => !document.querySelector('#notch-chat-input').disabled);
    assert.equal(await page.evaluate(() => window.__directSends.length), 2, 'Reconciliation is a GET, never a repeat POST');
    await page.evaluate(() => Axx.notch.setPreferences({ privacyCurtain: true }));
    assert.equal(await page.locator('#notch-chat-input').isVisible(), false);
    assert.equal(await page.locator('.notch-chat-output').isVisible(), false);
    await page.evaluate(() => Axx.notch.setPreferences({ privacyCurtain: false }));
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '04-response-fixture.png') });
    await page.click('[data-provider="antigravity"]');
    await page.waitForFunction(() => document.querySelector('.notch-chat-surface [role="status"]').textContent.includes('CLI no conectada'));
    assert.equal(await page.locator('#notch-chat-input').isDisabled(), true);
    // Actual UI paths with controlled system/recall services; no external sends.
    await page.click('#notch-more-btn');
    assert.equal(await page.getByRole('menu', { name: 'Más apartados' }).isVisible(), true);
    await page.locator('.notch-more-menu').screenshot({ path: path.join(output, '07-more-menu.png') });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#notch-more-btn').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => Axx.notch.getState().size), 'expanded');
    await page.evaluate(() => {
      const original = Axx.backendRequest;
      Axx.backendRequest = async (method, endpoint, body) => endpoint === '/axx-api/actions/execute' ? { output: { cpu_percent: 32, cpu_count: 12, memory_percent: 62.5, memory_used_mb: 20480, memory_total_mb: 32768, disk_free_gb: 128, disk_total_gb: 512 } } : original(method, endpoint, body);
      window.__receiptSounds = []; Axx.companion.audio.unlock = async () => {}; Axx.companion.audio.play = (...args) => window.__receiptSounds.push(args);
      Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'resources', size: 'expanded' });
    });
    await page.click('#notch-resource-poll-btn');
    await page.waitForFunction(() => document.querySelector('#notch-resource-lens').textContent.includes('62.5'));
    assert.equal(await page.locator('.notch-resource-metric').nth(1).locator('strong').textContent(), '62.5');
    assert((await page.locator('#notch-resource-lens').textContent()).includes('20.0 de 32.0 GB'));
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '08-system-fixture.png') });
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'portal', size: 'expanded' }));
    await page.getByRole('textbox', { name: 'Enlace o texto para Archivos' }).fill('https://example.com/project');
    await page.getByRole('button', { name: 'Añadir', exact: true }).click();
    await page.waitForSelector('.notch-portal-receipt');
    assert((await page.locator('.notch-shelf-item').textContent()).includes('example.com'));
    assert((await page.locator('.notch-portal-receipt').textContent()).includes('Enlace recibido'));
    assert.equal(await page.evaluate(() => window.__receiptSounds.length), 1);
    await page.locator('#notch-portal-file-input').setInputFiles({ name: 'contexto.txt', mimeType: 'text/plain', buffer: Buffer.from('Contenido real del documento') });
    await page.click('#notch-portal-to-chat');
    await page.waitForFunction(() => Axx.notch.getState().stageOpen);
    assert.equal(await page.evaluate(() => Axx.companion.attachment?.text), 'Contenido real del documento');
    assert((await page.inputValue('#chat-input')).includes('https://example.com/project'));
    await page.evaluate(() => { Axx.notch.dispatch({ type: 'CLOSE_STAGE', nextSize: 'expanded' }); Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'portal', size: 'expanded' }); });
    await page.waitForTimeout(650); await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '09-files-received.png') });
    await page.evaluate(() => {
      window.__selectedRecent = null;
      Axx.chatWorkspace = { chats: [{ id: 'recent-fixture', title: 'Proyecto de prueba' }], active: { id: 'other' }, select: async function(id) { window.__selectedRecent = id; this.active = { id }; } };
      Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'recall', size: 'expanded' });
    });
    await page.getByRole('button', { name: /Proyecto de prueba/ }).click();
    await page.waitForFunction(() => Axx.notch.getState().stageOpen);
    assert.equal(await page.evaluate(() => window.__selectedRecent), 'recent-fixture');
    await page.evaluate(() => Axx.notch.dispatch({ type: 'CLOSE_STAGE', nextSize: 'expanded' }));
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'agents', size: 'expanded' }));
    await page.waitForFunction(() => document.querySelector('.notch-provider-card')?.textContent.includes('Plus'));
    assert.equal(await page.locator('.notch-provider-card').count(), 3);
    await page.getByRole('button', { name: 'Ver plan de Claude Code' }).click();
    assert((await page.locator('.notch-provider-card[data-expanded="true"]').textContent()).includes('Plan Pro'));
    await page.getByRole('button', { name: 'Ver plan de Antigravity' }).click();
    await page.getByRole('button', { name: 'Sincronizar estado de Antigravity' }).click();
    assert((await page.locator('.notch-subscription-setup pre').textContent()).includes('official-status-fixture'));
    await page.getByRole('button', { name: 'Ver plan de Codex', exact: true }).click();
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '11-subscriptions-fixture.png') });
    await page.evaluate(() => { Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'orbit', size: 'expanded' }); Axx.notch.setPreferences({ surfaceScale: 'standard', expandedScalePercent: 100 }); });
    await page.waitForTimeout(650); const standardSize = await page.locator('#axx-notch-shell').boundingBox();
    await page.evaluate(() => Axx.notch.setPreferences({ surfaceScale: 'small', expandedScalePercent: 80 }));
    await page.waitForTimeout(650); const smallSize = await page.locator('#axx-notch-shell').boundingBox();
    assert(smallSize.width < standardSize.width * .8 && smallSize.height < standardSize.height * .8, 'Discreto must visibly shrink width and height');
    await layoutAudit('small-custom-size');
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '12-small-custom.png') });
    await page.evaluate(() => { Axx.notch.setPreferences({ compactWidthPx: 200 }); Axx.notch.dispatch({ type: 'SET_SURFACE_SIZE', size: 'compact' }); });
    await page.waitForTimeout(650); assert(Math.abs((await page.locator('#axx-notch-shell').boundingBox()).width - 200) <= 1);
    await page.evaluate(() => { Axx.notch.setPreferences({ surfaceScale: 'standard', expandedScalePercent: 100, compactWidthPx: 0 }); });
    for (const content of ['intent', 'agents', 'voice', 'media', 'recall']) {
      await page.evaluate(content => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content, size: 'expanded' }), content);
      await page.waitForTimeout(650); await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, 'section-' + content + '.png') });
    }
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'agents', size: 'expanded' }));
    await page.getByRole('button', { name: 'Abrir Axx Code Studio', exact: true }).click();
    await page.waitForSelector('.axx-code-studio:not([hidden])');
    assert.equal(await page.evaluate(() => Axx.companion.currentFeature), 'agent');
    await page.waitForTimeout(700);
    const stageBounds = await page.locator('#panel').boundingBox();
    assert(stageBounds.x >= 0 && stageBounds.x + stageBounds.width <= 1537, 'Code Studio must fit the viewport horizontally');
    assert(stageBounds.y >= 0 && stageBounds.y + stageBounds.height <= 817, 'Code Studio must fit the viewport vertically');
    await page.screenshot({ path: path.join(output, '10-code-studio-workspace.png') });
    await page.evaluate(() => Axx.notch.dispatch({ type: 'CLOSE_STAGE', nextSize: 'expanded' }));
    // Responsive checks at narrow logical work areas, not just devicePixelRatio changes.
    await page.setViewportSize({ width: 480, height: 640 });
    await page.evaluate(() => { Axx.desktop.width = 480; Axx.desktop.height = 640; Axx.notch.setPreferences({ surfaceScale: 'standard' }); });
    for (const content of ['orbit', 'intent', 'portal', 'media', 'agents', 'voice', 'resources', 'recall', 'parallel', 'chat']) {
      await page.evaluate(content => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content, size: 'expanded' }), content);
      await page.waitForTimeout(650); await layoutAudit('narrow-' + content);
    }
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '05-narrow-chat.png') });
    await page.emulateMedia({ reducedMotion: 'reduce', forcedColors: 'active' });
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'orbit', size: 'expanded' }));
    await page.locator('#axx-notch-shell').screenshot({ path: path.join(output, '06-forced-colors.png') });
    assert.deepEqual(errors, []); fs.writeFileSync(path.join(output, 'browser-report.json'), JSON.stringify({ status: 'PASS', evidenceKind: 'browser-real-renderer-controlled-provider-fixtures', errors, findings }, null, 2));
    console.log(`PASS: Obsidian portrait, zero tendril calls, settings, focus, direct session send-once, draft, privacy and ${findings.length-1} layout checks`);
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
