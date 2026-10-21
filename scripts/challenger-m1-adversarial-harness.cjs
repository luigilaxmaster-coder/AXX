const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createRequire } = require('node:module');

const bundledRequire = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = bundledRequire('playwright');
const html = fs.readFileSync(path.join(__dirname, '../1.AXX/Axx.html'), 'utf8');

const results = {
  total: 0,
  passed: 0,
  failed: 0,
  tests: []
};

function recordTest(name, passed, details = {}) {
  results.total++;
  if (passed) {
    results.passed++;
    results.tests.push({ name, status: 'PASS', details });
    console.log(`[PASS] ${name}`);
  } else {
    results.failed++;
    results.tests.push({ name, status: 'FAIL', details });
    console.error(`[FAIL] ${name}:`, details);
  }
}

(async () => {
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(html);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.addInitScript(() => {
      window.__contractCalls = [];
      window.__contractHits = [];
      window.__TAURI__ = {
        core: {
          invoke: async (name, args) => {
            window.__contractCalls.push({ name, args });
            const desktop = { screenX: 900, screenY: 500, workWidth: 1920, workHeight: 1040, spaceLeft: 900, spaceRight: 1020, spaceAbove: 500, spaceBelow: 540 };
            if (name === 'native_status') return { native: true, backendReady: true, desktop };
            if (name === 'desktop_layout') return { ...desktop, ...args };
            if (name === 'desktop_hit_map') { window.__contractHits.push(args); return true; }
            if (name === 'desktop_action') return true;
            return null;
          }
        },
        event: { listen: async () => () => {} }
      };
    });

    await page.goto(`http://127.0.0.1:${port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame);

    console.log('\n--- 1. STRESS TEST: CLICK VS DRAG DISCRIMINATION ---');

    // 1.1 Single click (detail = 1)
    const singleClickResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const initialStep = Axx.flow.nav.step;
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));

      const click = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, detail: 1 });
      const clickPrevented = !avatar.dispatchEvent(click);

      return { initialStep, finalStep: Axx.flow.nav.step, clickPrevented };
    });
    recordTest('1.1 Single click with detail = 1 triggers menu open (step: 0 -> 2)', 
      singleClickResult.initialStep === 0 && singleClickResult.finalStep === 2 && !singleClickResult.clickPrevented,
      singleClickResult
    );

    // 1.2 Double click with detail = 2
    const doubleClickResult = await page.evaluate(() => {
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      const stepBefore = Axx.flow.nav.step;
      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));

      const click = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, detail: 2 });
      const clickPrevented = !avatar.dispatchEvent(click);

      return { stepBefore, stepAfter: Axx.flow.nav.step, clickPrevented };
    });
    recordTest('1.2 Double click (2nd tap with detail = 2) toggles menu close (step: 2 -> 0)',
      doubleClickResult.stepBefore === 2 && doubleClickResult.stepAfter === 0 && !doubleClickResult.clickPrevented,
      doubleClickResult
    );

    // 1.3 Triple click with detail = 3
    const tripleClickResult = await page.evaluate(() => {
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
      Axx.flow.nav.close();

      const steps = [Axx.flow.nav.step];
      for (let detail = 1; detail <= 3; detail++) {
        avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
        avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
        avatar.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, detail }));
        steps.push(Axx.flow.nav.step);
      }
      return steps;
    });
    recordTest('1.3 Triple click (detail 1, 2, 3) progresses predictably [0, 2, 0, 2]',
      JSON.stringify(tripleClickResult) === JSON.stringify([0, 2, 0, 2]),
      tripleClickResult
    );

    // 1.4 Micro-movements (< 4px jitter)
    const microMoveResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 1, clientY: pt.y + 1, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 2, clientY: pt.y + 2, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 2.5, clientY: pt.y + 2.5, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x + 2.5, clientY: pt.y + 2.5, button: 0, pointerId: 1 }));

      return { step: Axx.flow.nav.step };
    });
    recordTest('1.4 Micro-movements (< 4px jitter) are treated as clicks (step becomes 2)',
      microMoveResult.step === 2,
      microMoveResult
    );

    // 1.5 Boundary test: exactly 4.0px movement
    const exactBoundaryResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 4.0, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x + 4.0, clientY: pt.y, button: 0, pointerId: 1 }));

      return { step: Axx.flow.nav.step };
    });
    recordTest('1.5 Exact boundary condition (dx = 4.0px) treated as click (step becomes 2)',
      exactBoundaryResult.step === 2,
      exactBoundaryResult
    );

    // 1.6 Movement exceeding threshold (dx = 5.0px)
    const thresholdExceededResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 5.0, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x + 5.0, clientY: pt.y, button: 0, pointerId: 1 }));

      return { step: Axx.flow.nav.step, suppressClickUntil: Axx.resident.suppressClickUntil, now: performance.now() };
    });
    recordTest('1.6 Movement exceeding 4px (dx = 5.0px) treated as drag (step stays 0)',
      thresholdExceededResult.step === 0 && thresholdExceededResult.suppressClickUntil > thresholdExceededResult.now,
      thresholdExceededResult
    );

    // 1.7 Real drag movement (> 4px) suppresses trailing click
    const dragSuppressionResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, clientX: pt.x + 25, clientY: pt.y + 20, button: 0, pointerId: 1 }));
      avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x + 25, clientY: pt.y + 20, button: 0, pointerId: 1 }));

      const click = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x + 25, clientY: pt.y + 20, detail: 1 });
      const dispatched = avatar.dispatchEvent(click);
      const isPrevented = !dispatched || click.defaultPrevented;

      return {
        step: Axx.flow.nav.step,
        clickPrevented: isPrevented,
        suppressActive: Axx.resident.suppressClickUntil > performance.now()
      };
    });
    recordTest('1.7 Real drag (> 4px) suppresses trailing clicks and prevents menu toggle',
      dragSuppressionResult.step === 0 && dragSuppressionResult.clickPrevented && dragSuppressionResult.suppressActive,
      dragSuppressionResult
    );

    // 1.8 Recovery after suppressClickUntil expires
    const postSuppressionResult = await page.evaluate(async () => {
      // Artificially simulate suppressClickUntil set 50ms into future
      Axx.resident.suppressClickUntil = performance.now() + 50;
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      // Immediate click is suppressed
      const immediateClick = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, detail: 1 });
      const immPrevented = !avatar.dispatchEvent(immediateClick) || immediateClick.defaultPrevented;

      // Wait 70ms for timeout to expire
      await new Promise(res => setTimeout(res, 70));

      // Subsequent click is NOT suppressed
      const laterClick = new MouseEvent('click', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, detail: 1 });
      const laterPrevented = !avatar.dispatchEvent(laterClick) || laterClick.defaultPrevented;

      return { immPrevented, laterPrevented };
    });
    recordTest('1.8 Clicks are allowed normally after suppression window expires',
      postSuppressionResult.immPrevented === true && postSuppressionResult.laterPrevented === false,
      postSuppressionResult
    );

    // 1.9 Right-click / Middle-click rejection
    const nonPrimaryButtonsResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      // Middle click (button = 1)
      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 1, pointerId: 1 }));
      const middleDragActive = Axx.resident.drag !== null;

      // Right click (button = 2)
      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 2, pointerId: 1 }));
      const rightDragActive = Axx.resident.drag !== null;

      return { middleDragActive, rightDragActive, step: Axx.flow.nav.step };
    });
    recordTest('1.9 Non-primary pointer buttons (middle/right) do not initiate avatar drag or tap',
      !nonPrimaryButtonsResult.middleDragActive && !nonPrimaryButtonsResult.rightDragActive && nonPrimaryButtonsResult.step === 0,
      nonPrimaryButtonsResult
    );

    // 1.10 Pointercancel / Blur cleans up drag state
    const cleanupResult = await page.evaluate(() => {
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      // Start drag
      avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
      const wasActive = Axx.resident.drag !== null;

      // Dispatch pointercancel
      document.dispatchEvent(new PointerEvent('pointercancel', { bubbles: true }));
      const dragAfterCancel = Axx.resident.drag;

      return { wasActive, dragAfterCancel };
    });
    recordTest('1.10 Pointercancel cleanly resets active avatar drag state',
      cleanupResult.wasActive === true && cleanupResult.dragAfterCancel === null,
      cleanupResult
    );

    console.log('\n--- 2. STRESS TEST: ALPHA HIT-TESTING ---');

    // 2.1 SoftwareRenderer hitTest with synthetic pixel buffers
    const alphaBufferResults = await page.evaluate(() => {
      const mockCanvas = document.createElement('canvas');
      mockCanvas.width = 100;
      mockCanvas.height = 100;
      const ctx = mockCanvas.getContext('2d');
      const raster = {
        width: 10,
        height: 10,
        pixels: new Uint8ClampedArray(10 * 10 * 4)
      };

      function testAlpha(alphaValue) {
        raster.pixels.fill(0);
        const idx = (5 * 10 + 5) * 4;
        raster.pixels[idx + 0] = 120;
        raster.pixels[idx + 1] = 130;
        raster.pixels[idx + 2] = 140;
        raster.pixels[idx + 3] = alphaValue;

        const dummyRenderer = {
          ctx,
          canvas: mockCanvas,
          raster,
          hitTest: Axx.SoftwareRenderer.prototype.hitTest
        };

        mockCanvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 });
        return dummyRenderer.hitTest(55, 55);
      }

      return {
        alpha0: testAlpha(0),
        alpha10: testAlpha(10),
        alpha16: testAlpha(16),
        alpha17: testAlpha(17),
        alpha20: testAlpha(20),
        alpha128: testAlpha(128),
        alpha255: testAlpha(255)
      };
    });

    recordTest('2.1a Alpha = 0 (transparent outside) returns false', alphaBufferResults.alpha0 === false, alphaBufferResults);
    recordTest('2.1b Alpha = 10 (faint noise <= 16) returns false', alphaBufferResults.alpha10 === false, alphaBufferResults);
    recordTest('2.1c Alpha = 16 (cutoff boundary <= 16) returns false', alphaBufferResults.alpha16 === false, alphaBufferResults);
    recordTest('2.1d Alpha = 17 (above cutoff > 16) returns true', alphaBufferResults.alpha17 === true, alphaBufferResults);
    recordTest('2.1e Alpha = 20 (outer translucent rim) returns true', alphaBufferResults.alpha20 === true, alphaBufferResults);
    recordTest('2.1f Alpha = 255 (solid center) returns true', alphaBufferResults.alpha255 === true, alphaBufferResults);

    // 2.2 Live renderer hitTest on real avatar
    const liveHitTestResult = await page.evaluate(() => {
      const renderer = Axx.app.renderer;
      const r = renderer.canvas.getBoundingClientRect();
      const centerHit = renderer.hitTest(r.left + r.width / 2, r.top + r.height / 2);
      const cornerHit = renderer.hitTest(r.left + 2, r.top + 2);
      const outsideHit = renderer.hitTest(r.left - 50, r.top - 50);

      return { centerHit, cornerHit, outsideHit, canvasWidth: r.width, canvasHeight: r.height };
    });
    recordTest('2.2 Live avatar: Center is interactive (true), corner is non-interactive (false), outside is false',
      liveHitTestResult.centerHit === true && liveHitTestResult.cornerHit === false && liveHitTestResult.outsideHit === false,
      liveHitTestResult
    );

    // 2.3 SoftwareRenderer hitMask 64x64 generation
    const hitMaskResult = await page.evaluate(() => {
      const mask = Axx.app.renderer.hitMask();
      const totalBits = mask.bits.length;
      const solidBits = mask.bits.reduce((a, b) => a + b, 0);
      const transparentBits = totalBits - solidBits;
      return {
        cols: mask.cols,
        rows: mask.rows,
        totalBits,
        solidBits,
        transparentBits,
        ratioSolid: solidBits / totalBits
      };
    });
    recordTest('2.3 hitMask generates 64x64 grid with both solid avatar body and transparent click-through bits',
      hitMaskResult.cols === 64 && hitMaskResult.rows === 64 && hitMaskResult.solidBits > 100 && hitMaskResult.transparentBits > 100,
      hitMaskResult
    );

    // 2.4 Stage/Avatar rect is present in interactiveRegions to guarantee prompt Rust responsiveness
    const regionsAnalysis = await page.evaluate(() => {
      const regions = Axx.resident.interactiveRegions();
      const stage = document.getElementById('stage');
      const avatar = document.getElementById('avatar');
      const stageRect = stage.getBoundingClientRect();
      const avatarRect = avatar.getBoundingClientRect();

      const stageInRegions = regions.some(r => Math.abs(r.x - stageRect.x) < 1 && Math.abs(r.y - stageRect.y) < 1 && Math.abs(r.width - stageRect.width) < 1);
      const avatarInRegions = regions.some(r => Math.abs(r.x - avatarRect.x) < 1 && Math.abs(r.y - avatarRect.y) < 1 && Math.abs(r.width - avatarRect.width) < 1);

      return {
        regionsCount: regions.length,
        stageRect: { x: stageRect.x, y: stageRect.y, w: stageRect.width, h: stageRect.height },
        avatarRect: { x: avatarRect.x, y: avatarRect.y, w: avatarRect.width, h: avatarRect.height },
        stageInRegions,
        avatarInRegions
      };
    });
    recordTest('2.4 Stage/Avatar rect is present in interactiveRegions to guarantee prompt Rust responsiveness',
      regionsAnalysis.stageInRegions || regionsAnalysis.avatarInRegions,
      regionsAnalysis
    );

    console.log('\n--- 3. STRESS TEST: RADIAL MENU TOGGLE RAPID CYCLING ---');

    // 3.1 100 Rapid Toggles on Avatar
    const rapidToggleResult = await page.evaluate(() => {
      Axx.flow.nav.close();
      const avatar = document.getElementById('avatar');
      const r = avatar.getBoundingClientRect();
      const pt = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };

      let cycleErrors = 0;
      const history = [];

      for (let i = 1; i <= 100; i++) {
        avatar.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));
        avatar.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: pt.x, clientY: pt.y, button: 0, pointerId: 1 }));

        const expectedStep = (i % 2 === 1) ? 2 : 0;
        const actualStep = Axx.flow.nav.step;
        if (actualStep !== expectedStep) {
          cycleErrors++;
          history.push({ cycle: i, expected: expectedStep, actual: actualStep });
        }
      }

      return {
        cycles: 100,
        cycleErrors,
        history,
        finalStep: Axx.flow.nav.step
      };
    });
    recordTest('3.1 100 Rapid avatar clicks alternate strictly between 0 and 2 without desync or getting stuck',
      rapidToggleResult.cycleErrors === 0 && rapidToggleResult.finalStep === 0,
      rapidToggleResult
    );

    // 3.2 Quick launch radial buttons clickable in step = 2
    const radialButtonsResult = await page.evaluate(() => {
      Axx.flow.nav.tap();
      const step = Axx.flow.nav.step;
      const fan = document.getElementById('flow-fan');
      const fanStyle = getComputedStyle(fan);
      const buttons = Array.from(document.querySelectorAll('#flow-fan > [data-quick], #flow-fan button'));

      const buttonStyles = buttons.map(b => ({
        id: b.id || b.getAttribute('data-quick'),
        pointerEvents: getComputedStyle(b).pointerEvents,
        display: getComputedStyle(b).display,
        visibility: getComputedStyle(b).visibility
      }));

      const sheet = document.getElementById('flow-sheet');
      const sheetPointerEvents = sheet ? getComputedStyle(sheet).pointerEvents : null;
      const allButtonsAuto = buttonStyles.every(b => b.pointerEvents === 'auto');

      return {
        step,
        fanPointerEvents: fanStyle.pointerEvents,
        sheetPointerEvents,
        buttonCount: buttons.length,
        allButtonsAuto
      };
    });
    recordTest('3.2 Flow fan buttons have pointer-events: auto and flow-sheet backdrop has pointer-events: none',
      radialButtonsResult.step === 2 && radialButtonsResult.allButtonsAuto && radialButtonsResult.sheetPointerEvents === 'none',
      radialButtonsResult
    );

    // 3.3 Clicking orbital button opens target tool
    const orbitalClickResult = await page.evaluate(async () => {
      const chatBtn = document.querySelector('#flow-fan [data-quick="chat"]') || document.querySelector('#flow-chat');
      if (!chatBtn) return { found: false };

      chatBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      await new Promise(r => setTimeout(r, 50));

      const panel = document.getElementById('panel');
      const panelVisible = panel && !panel.hidden;
      return { found: true, panelVisible, currentTool: Axx.flow.nav.tool || Axx.flow.currentTool };
    });
    recordTest('3.3 Clicking orbital radial button opens target panel and tool',
      orbitalClickResult.found && orbitalClickResult.panelVisible,
      orbitalClickResult
    );

  } finally {
    await browser.close();
    server.close();
  }

  console.log('\n========================================');
  console.log(`TOTAL: ${results.total} | PASSED: ${results.passed} | FAILED: ${results.failed}`);
  console.log('========================================\n');

  if (results.failed > 0) {
    process.exit(1);
  } else {
    process.exit(0);
  }
})();
