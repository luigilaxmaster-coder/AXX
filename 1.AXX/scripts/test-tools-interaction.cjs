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
    const file = req.url.startsWith('/scripts/') ? path.join(__dirname, path.basename(req.url)) : (process.env.AXX_TEST_HTML || path.join(root, 'Axx.html'));
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
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
        const desktop = window.testDesktop || { screenX: 1000, screenY: 500, workWidth: 1920, workHeight: 1040, spaceLeft: 1000, spaceRight: 920, spaceAbove: 500, spaceBelow: 540 };
        if (name === 'desktop_move_body') {
          (window.bodyMoves ||= []).push(args);
          window.testDesktop = { ...desktop, screenX: args.x, screenY: args.y, spaceLeft: args.x, spaceRight: desktop.workWidth-args.x, spaceAbove: args.y, spaceBelow: desktop.workHeight-args.y };
          return window.testDesktop;
        }
        if (name === 'native_status') return { native: true, backendReady: false, shortcut: 'Alt+Shift+A', desktop };
        if (name === 'desktop_layout') return { ...desktop, ...args };
        return null;
      } }, event: { listen: async () => () => {} } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame);
    const check = async (name, fn) => {
      console.log('Checking:', name);
      try { await fn(); results.push(name); } catch (error) { failures.push({ name, error: error.stack, state: await page.evaluate(() => ({step:Axx.flow.nav.step, tool:Axx.flow.nav.tool, busy:Axx.resident.layoutBusy, pending:Axx.resident.pendingLayout, panelHidden:document.getElementById('panel').hidden})) }); }
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
      assert.equal(await page.locator('#flow-sheet').evaluate(el => getComputedStyle(el).backgroundColor), 'rgba(0, 0, 0, 0)', 'orbit must stay transparent around the avatar');
      assert.equal(await page.locator('#flow-sheet').evaluate(el => getComputedStyle(el).boxShadow), 'none', 'orbit must not draw a panel shadow');
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
    await check('Unchanged visibility does not repeatedly request native layout', async () => {
      await page.evaluate(() => Axx.companion.openFeature('notes'));
      await page.waitForTimeout(500);
      await page.evaluate(() => {
        window.statusCalls = 0;
        window.countedStatus = Axx.app.bridge.status;
        Axx.app.bridge.status = function (...args) { window.statusCalls++; return window.countedStatus.apply(this, args); };
        const panel = document.getElementById('panel');
        for (let i = 0; i < 50; i++) panel.hidden = false;
      });
      await page.waitForTimeout(600);
      const calls = await page.evaluate(() => { Axx.app.bridge.status = window.countedStatus; return window.statusCalls; });
      console.log('Idle native status requests in 600 ms:', calls);
      assert.ok(calls <= 4, `unchanged panel triggered ${calls} status requests`);
    });
    await check('Shared panels keep one drag owner, survive an in-flight layout and commit without snapping', async () => {
      for (const id of ['notes', 'calculator', 'dictation', 'screen', 'magicpen', 'chat']) {
        await page.evaluate(id => Axx.companion.openFeature(id), id);
        await page.waitForFunction(() => !Axx.resident.layoutBusy && !Axx.resident.pendingLayout, null, { polling: 50 });
        await page.evaluate(() => {
          window.dragStart = document.getElementById('panel').getBoundingClientRect().toJSON();
          window.legacyStarts = 0;
          document.querySelector('#panel .panel-head').addEventListener('pointerdown', () => window.legacyStarts++, { once: true });
          window.originalStatus = Axx.app.bridge.status;
          Axx.app.bridge.status = () => { Axx.app.bridge.status = window.originalStatus; return new Promise(resolve => { window.releaseStatus = () => resolve({ desktop: Axx.resident.geometry }); }); };
          void Axx.resident.layout();
        });
        const head = await page.locator('#panel .panel-head').boundingBox();
        const x = head.x + head.width / 2, y = head.y + head.height / 2;
        await page.mouse.move(x, y);
        await page.mouse.down();
        assert.equal(await page.evaluate(() => !!Axx.resident.panelDrag), true, id + ': missing drag');
        await page.mouse.move(x + 45, y + 24, { steps: 6 });
        await page.evaluate(() => { Axx.app.bridge.status = window.originalStatus; window.releaseStatus(); });
        await page.waitForTimeout(70);
        const moved = await page.evaluate(() => ({ rect: document.getElementById('panel').getBoundingClientRect().toJSON(), before: window.dragStart, legacy: window.legacyStarts, active: Axx.actions.windows.active }));
        assert.equal(moved.legacy, 0, id + ': legacy handler also owns drag');
        assert.ok(!moved.active, id + ': legacy window manager active');
        assert.ok(Math.abs(moved.rect.x - moved.before.x - 45) < 1, id + ': layout reset drag X');
        assert.ok(Math.abs(moved.rect.y - moved.before.y - 24) < 1, id + ': layout reset drag Y');
        await page.evaluate(() => { Axx.app.bridge.status = () => { Axx.app.bridge.status = window.originalStatus; return new Promise(resolve => { window.releaseStatus = () => resolve({ desktop: Axx.resident.geometry }); }); }; });
        await page.mouse.up();
        const ended = await page.locator('#panel').boundingBox();
        assert.ok(Math.abs(ended.x - moved.rect.x) < 1 && Math.abs(ended.y - moved.rect.y) < 1, `${id}: release snapped before native layout ${JSON.stringify({moved:moved.rect, ended})}`);
        assert.equal(await page.locator('.resident-manipulating').count(), 0);
        await page.evaluate(() => { Axx.app.bridge.status = window.originalStatus; window.releaseStatus(); });
        await page.waitForFunction(() => !Axx.resident.layoutBusy && !Axx.resident.pendingLayout, null, { polling: 50 });
      }
    });
    await check('Resize, cancel and fixed panels preserve interaction state', async () => {
      await page.evaluate(() => Axx.companion.openFeature('notes'));
      await page.waitForFunction(() => !Axx.resident.layoutBusy && !Axx.resident.pendingLayout, null, { polling: 50 });
      const grip = await page.locator('#panel > .resident-resize-handle').boundingBox();
      const before = await page.locator('#panel').boundingBox();
      await page.mouse.move(grip.x + 5, grip.y + 5); await page.mouse.down();
      await page.mouse.move(grip.x + 35, grip.y + 25, { steps: 5 });
      await page.evaluate(() => Axx.resident.layout());
      const resized = await page.locator('#panel').boundingBox();
      assert.ok(Math.abs(resized.width - before.width - 30) < 1);
      await page.evaluate(() => window.dispatchEvent(new Event('blur')));
      await page.mouse.up();
      assert.equal(await page.evaluate(() => Axx.resident.panelResize), null);
      assert.equal(await page.locator('.resident-manipulating').count(), 0);
      await page.waitForFunction(() => !Axx.resident.layoutBusy && !Axx.resident.pendingLayout, null, { polling: 50 });
      await page.evaluate(() => document.getElementById('panel').dataset.windowLocked = 'true');
      const head = await page.locator('#panel .panel-head').boundingBox();
      await page.mouse.move(head.x + head.width / 2, head.y + head.height / 2); await page.mouse.down();
      assert.equal(await page.evaluate(() => Axx.resident.panelDrag), null);
      await page.mouse.up();
      await page.evaluate(() => document.getElementById('panel').dataset.windowLocked = 'false');
    });
    await check('Dragging the avatar previews locally and commits its position once on release', async () => {
      await page.evaluate(() => Axx.resident.fold());
      await page.waitForTimeout(300);
      const point = await page.evaluate(() => { const r=document.getElementById('avatar').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}; });
      assert.ok(await page.evaluate(p => Axx.app.renderer.hitTest(p.x,p.y),point));
      const before = await page.evaluate(() => ({...Axx.resident.anchor}));
      await page.mouse.move(point.x,point.y);await page.mouse.down();
      await page.mouse.move(point.x+40,point.y+25,{steps:10});
      const preview = await page.evaluate(() => ({...Axx.resident.anchor}));
      assert.ok(Math.abs(preview.x-before.x-40)<1 && Math.abs(preview.y-before.y-25)<1);
      assert.equal(await page.evaluate(() => (window.bodyMoves||[]).length),0);
      await page.mouse.up();await page.waitForTimeout(100);
      assert.equal(await page.evaluate(() => window.bodyMoves.length),1);
      assert.equal(await page.evaluate(() => Axx.resident.drag),null);
      assert.equal(await page.evaluate(() => Axx.flow.nav.step),0);
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
