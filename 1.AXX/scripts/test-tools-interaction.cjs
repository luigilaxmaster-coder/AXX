/** Real browser pointer tests; the native IPC boundary is simulated. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const runtime = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = runtime('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const server = http.createServer((req, res) => {
    const file = req.url.startsWith('/scripts/') ? path.join(__dirname, path.basename(req.url)) : path.join(root, 'Axx.html');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : 'text/html');
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM });
  const failures = [], results = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.stack || e.message));
    await page.addInitScript(() => {
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        const desktop = { screenX: 1000, screenY: 500, workWidth: 1920, workHeight: 1040, spaceLeft: 1000, spaceRight: 920, spaceAbove: 500, spaceBelow: 540 };
        if (name === 'native_status') return { native: true, backendReady: false, shortcut: 'Alt+Shift+A', desktop };
        if (name === 'desktop_layout') return { ...desktop, ...args };
        return null;
      } }, event: { listen: async () => () => {} } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame);
    const check = async (name, fn) => {
      console.log('Checking:', name);
      try { await fn(); results.push(name); } catch (error) { failures.push({ name, error: error.message, state: await page.evaluate(() => ({step:Axx.flow.nav.step, tool:Axx.flow.nav.tool, busy:Axx.resident.layoutBusy, pending:Axx.resident.pendingLayout, panelHidden:document.getElementById('panel').hidden})) }); }
    };
    const openCatalog = async () => {
      await page.evaluate(() => { Axx.flow.showQuick(); });
      await page.locator('#flow-all').click();
      await page.waitForFunction(() => Axx.flow.nav.step === 3 && getComputedStyle(document.getElementById('flow-sheet')).pointerEvents === 'auto');
    };
    await check('Orbit → catalog accepts real pointer clicks and opens Chat', async () => {
      await openCatalog();
      assert.equal(await page.locator('[data-tool="chat"]').evaluate(el => getComputedStyle(el).pointerEvents), 'auto', 'catalog inherits disabled pointer events from orbit');
      await page.locator('[data-tool="chat"]').click({ timeout: 3000 });
      await page.waitForFunction(() => Axx.flow.nav.tool === 'chat' && !document.getElementById('panel').hidden);
    });
    await check('Catalog tabs, search, Notes and Calculator remain clickable after repeated navigation', async () => {
      for (const [group, id] of [['create', 'notes'], ['work', 'calculator'], ['create', 'chat']]) {
        await openCatalog();
        await page.locator(`[data-group="${group}"]`).click({ timeout: 3000 });
        await page.locator(`[data-tool="${id}"]`).click({ timeout: 3000 });
        await page.waitForFunction(id => Axx.flow.nav.tool === id && !document.getElementById('panel').hidden, id);
      }
      await openCatalog();
      await page.locator('#flow-search').fill('Notas', { timeout: 3000 });
      assert.equal(await page.locator('#flow-grid [data-tool]').count(), 1);
      await page.locator('#flow-search').fill('');
    });
    await check('Tool controls show icons with accessible names, without visible captions', async () => {
      await page.evaluate(() => Axx.flow.showQuick());
      assert.equal(await page.locator('#flow-fan .orbit-label').first().isVisible(), false);
      assert.ok(await page.locator('#flow-fan [data-quick]').first().getAttribute('aria-label'));
      await openCatalog();
      const tool = page.locator('[data-tool="chat"]');
      assert.equal(await tool.innerText(), '');
      assert.equal(await tool.getAttribute('aria-label'), 'Chat');
      assert.equal(await tool.locator('svg').count(), 1);
      if (process.env.AXX_TEST_EVIDENCE) {
        fs.mkdirSync(process.env.AXX_TEST_EVIDENCE, { recursive: true });
        await page.screenshot({ path: path.join(process.env.AXX_TEST_EVIDENCE, 'catalog.png'), omitBackground: true });
      }
    });
    await check('Tentacle stays attached during a long hover and retracts continuously on exit', async () => {
      await page.evaluate(() => Axx.flow.showQuick());
      await page.waitForTimeout(700);
      const button = page.locator('#flow-fan [data-quick="chat"]');
      await button.hover();
      await page.waitForTimeout(1800);
      const before = await page.evaluate(() => Axx.orbit.reachProgress);
      assert.ok(before > .9, `long hover must stay extended; got ${before}`);
      if (process.env.AXX_TEST_EVIDENCE) await page.screenshot({ path: path.join(process.env.AXX_TEST_EVIDENCE, 'tentacle.png'), omitBackground: true });
      await page.mouse.move(5, 5);
      await page.waitForTimeout(65);
      const during = await page.evaluate(() => Axx.orbit.reachProgress);
      assert.ok(during > .05 && during < before, `exit must retract, not cut: ${during}`);
      await page.waitForTimeout(1200);
      assert.ok(await page.evaluate(() => Axx.orbit.reachProgress < .01));
    });
    console.log(JSON.stringify({ kind: 'BROWSER_POINTER_WITH_NATIVE_IPC_FIXTURE', passed: results, failures, errors }, null, 2));
    if (failures.length || errors.length) process.exitCode = 1;
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
