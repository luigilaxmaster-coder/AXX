const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createRequire } = require('node:module');
const bundledRequire = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = bundledRequire('playwright');
const html = fs.readFileSync(path.join(__dirname, '../1.AXX/Axx.html'), 'utf8');

(async () => {
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(html);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.addInitScript(() => {
      window.__contractCalls = [];
      window.__TAURI__ = {
        core: {
          invoke: async (name, args) => {
            window.__contractCalls.push({ name, args });
            const desktop = { screenX: 900, screenY: 500, workWidth: 1920, workHeight: 1040, spaceLeft: 900, spaceRight: 1020, spaceAbove: 500, spaceBelow: 540 };
            if (name === 'native_status') return { native: true, backendReady: true, desktop };
            if (name === 'desktop_layout') { window.__contractLayout = args; return { ...desktop, ...args }; }
            return null;
          }
        },
        event: { listen: async () => () => {} }
      };
    });

    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame);

    // 1. Verify organicCurve under normal vs reduced motion
    const curveTest = await page.evaluate(() => {
      const a = { x: 100, y: 100 }, b = { x: 400, y: 300 };
      document.body.dataset.quietMotion = 'false';
      const normalCurve = Axx.organicCurve(a, b, 0.5, 1.5);
      document.body.dataset.quietMotion = 'true';
      const quietCurve = Axx.organicCurve(a, b, 0.5, 1.5);
      document.body.dataset.quietMotion = 'false';
      return { normalCurve, quietCurve };
    });
    console.log('Curve test:', curveTest);
    assert(curveTest.normalCurve.x !== undefined);
    assert(curveTest.quietCurve.x !== undefined);

    // 2. Open chat panel and verify tendril link creation
    await page.evaluate(() => Axx.flow.select('chat'));
    await page.waitForFunction(() => document.getElementById('panel') && !document.getElementById('panel').hidden);
    
    // Check panel initial position
    const panelRect = await page.evaluate(() => {
      const p = document.getElementById('panel').getBoundingClientRect();
      return { x: p.x, y: p.y, width: p.width, height: p.height };
    });
    console.log('Panel rect before drag:', panelRect);
    assert(panelRect.width > 200);

    // 3. Drag panel header and check position persistence
    const dragTargetInfo = await page.evaluate(() => {
      const brand = document.querySelector('.chat20-brand');
      const r = brand.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
      const el = document.elementFromPoint(pt.x, pt.y);
      return { pt, tag: el?.tagName, className: el?.className, id: el?.id };
    });
    console.log('dragTargetInfo:', dragTargetInfo);
    await page.mouse.move(dragTargetInfo.pt.x, dragTargetInfo.pt.y);
    await page.mouse.down();
    await page.mouse.move(dragTargetInfo.pt.x + 60, dragTargetInfo.pt.y + 40, { steps: 10 });
    await page.mouse.up();

    const persistedPos = await page.evaluate(() => {
      return {
        positions: Axx.resident.panelPositions,
        storage: JSON.parse(localStorage.getItem('axx.resident.panel-pos') || '{}')
      };
    });
    console.log('Persisted panel positions:', persistedPos);
    assert(persistedPos.positions['panel'] !== undefined);
    assert(persistedPos.storage['panel'] !== undefined);
    assert.equal(persistedPos.storage['panel'].relX, persistedPos.positions['panel'].relX);

    // 4. Verify spring smoothing map exists in OrganicDesk
    const hasSprings = await page.evaluate(() => {
      return Axx.organic.linkSprings instanceof Map;
    });
    assert(hasSprings, 'OrganicDesk must have linkSprings Map');

    console.log('Fase 1 interaction tests PASSED!');
  } finally {
    await browser.close();
    server.close();
  }
})();
