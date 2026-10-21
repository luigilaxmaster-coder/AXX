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

// Exact Rust PixelMask oracle implementation
class RustPixelMaskOracle {
  constructor(bounds, cols, rows, bits) {
    this.bounds = bounds; // { x, y, width, height }
    this.cols = cols;
    this.rows = rows;
    this.bits = bits;
  }

  contains(x, y) {
    const padded = {
      x: this.bounds.x - 2.0,
      y: this.bounds.y - 2.0,
      width: this.bounds.width + 4.0,
      height: this.bounds.height + 4.0,
    };
    if (x < padded.x || y < padded.y || x >= padded.x + padded.width || y >= padded.y + padded.height) {
      return false;
    }
    const clamped_x = Math.max(this.bounds.x, Math.min(this.bounds.x + this.bounds.width, x));
    const clamped_y = Math.max(this.bounds.y, Math.min(this.bounds.y + this.bounds.height, y));
    const column = Math.min(this.cols - 1, Math.floor(((clamped_x - this.bounds.x) / this.bounds.width) * this.cols));
    const row = Math.min(this.rows - 1, Math.floor(((clamped_y - this.bounds.y) / this.bounds.height) * this.rows));

    const rMin = Math.max(0, row - 1);
    const rMax = Math.min(this.rows - 1, row + 1);
    const cMin = Math.max(0, column - 1);
    const cMax = Math.min(this.cols - 1, column + 1);

    for (let r = rMin; r <= rMax; r++) {
      for (let c = cMin; c <= cMax; c++) {
        if (this.bits[r * this.cols + c]) {
          return true;
        }
      }
    }
    return false;
  }
}

// Rust hit-test loop decision oracle
function computeRustIgnoreCursor(regions, mask, x, y, lbutton_down = false, current_ignore = true) {
  const regions_empty = regions.length === 0;
  const mask_present = mask !== null;
  const inside = regions.some(r => x >= r.x && y >= r.y && x < r.x + r.width && y < r.y + r.height)
    || (mask !== null && mask.contains(x, y));

  let ignore;
  if (inside) {
    ignore = false;
  } else if (lbutton_down && !current_ignore) {
    ignore = false;
  } else {
    ignore = (!regions_empty || mask_present) && !inside;
  }
  return { inside, ignore };
}

(async () => {
  console.log('=== CHALLENGER HARNESS: MILESTONE 1 ITERATION 2 ===');
  console.log('Target: Transparent Desktop Click-Through & Hit-Testing Precision');

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

    // Set avatar size to 530x530 as mandated by challenge specification
    await page.evaluate(async () => {
      Axx.companion.setSize(530, true);
      await new Promise(r => setTimeout(r, 60));
    });

    console.log('\n--- 1. EMPIRICAL TEST: 4 CORNERS OF 530x530 STAGE ---');

    const cornersTest = await page.evaluate(() => {
      const stage = document.getElementById('stage');
      const avatar = document.getElementById('avatar');
      const renderer = Axx.app.renderer;
      const stageRect = stage.getBoundingClientRect();
      const canvasRect = renderer.canvas.getBoundingClientRect();
      const mask = renderer.hitMask(64, 64);
      const regions = Axx.resident ? Axx.resident.interactiveRegions() : [];

      // Corner test points relative to 530x530 stage rect
      const cornerCoords = [
        { name: 'Top-Left', x: stageRect.x + 10, y: stageRect.y + 10, relX: 10, relY: 10 },
        { name: 'Top-Right', x: stageRect.x + 520, y: stageRect.y + 10, relX: 520, relY: 10 },
        { name: 'Bottom-Left', x: stageRect.x + 10, y: stageRect.y + 520, relX: 10, relY: 520 },
        { name: 'Bottom-Right', x: stageRect.x + 520, y: stageRect.y + 520, relX: 520, relY: 520 }
      ];

      const cornerEvaluations = cornerCoords.map(pt => {
        const hitDirect = renderer.hitTest(pt.x, pt.y);
        // Calculate corresponding mask grid cell
        const col = Math.min(mask.cols - 1, Math.floor(((pt.x - canvasRect.x) / canvasRect.width) * mask.cols));
        const row = Math.min(mask.rows - 1, Math.floor(((pt.y - canvasRect.y) / canvasRect.height) * mask.rows));
        const bit = mask.bits[row * mask.cols + col];

        // Also check 3x3 neighborhood bits
        let neighborhoodSolid = false;
        for (let r = Math.max(0, row - 1); r <= Math.min(mask.rows - 1, row + 1); r++) {
          for (let c = Math.max(0, col - 1); c <= Math.min(mask.cols - 1, col + 1); c++) {
            if (mask.bits[r * mask.cols + c] === 1) neighborhoodSolid = true;
          }
        }

        // Check if any region contains this point
        const regionHit = regions.some(r => pt.x >= r.x && pt.y >= r.y && pt.x < r.x + r.width && pt.y < r.y + r.height);

        return {
          ...pt,
          col,
          row,
          bit,
          neighborhoodSolid,
          hitDirect,
          regionHit
        };
      });

      return {
        stageWidth: stageRect.width,
        stageHeight: stageRect.height,
        cornerEvaluations,
        maskCols: mask.cols,
        maskRows: mask.rows,
        totalMaskBits: mask.bits.length,
        solidBitsCount: mask.bits.reduce((a, b) => a + b, 0),
        regionsCount: regions.length,
        stageInRegions: regions.some(r => Math.abs(r.x - stageRect.x) < 2 && Math.abs(r.width - stageRect.width) < 2),
        avatarInRegions: regions.some(r => Math.abs(r.x - stageRect.x) < 2 && Math.abs(r.height - stageRect.height) < 2)
      };
    });

    recordTest('1.1 Stage bounding box matches expected dimensions (530x530)',
      Math.abs(cornersTest.stageWidth - 530) < 5 && Math.abs(cornersTest.stageHeight - 530) < 5,
      { width: cornersTest.stageWidth, height: cornersTest.stageHeight }
    );

    recordTest('1.2 Neither #stage nor #avatar rectangle is present in interactiveRegions',
      !cornersTest.stageInRegions && !cornersTest.avatarInRegions,
      { stageInRegions: cornersTest.stageInRegions, avatarInRegions: cornersTest.avatarInRegions }
    );

    cornersTest.cornerEvaluations.forEach((evalPt, idx) => {
      const pass = !evalPt.hitDirect && evalPt.bit === 0 && !evalPt.neighborhoodSolid && !evalPt.regionHit;
      recordTest(`1.3.${idx + 1} Corner ${evalPt.name} (rel: ${evalPt.relX}, ${evalPt.relY}): direct hit is false, mask bit is 0, neighborhood is clear, regionHit is false`,
        pass,
        evalPt
      );
    });

    console.log('\n--- 2. EMPIRICAL TEST: RUST ORACLE ON 4 CORNERS (CLICK-THROUGH) ---');

    const oracleSetup = await page.evaluate(() => {
      const renderer = Axx.app.renderer;
      const canvasRect = renderer.canvas.getBoundingClientRect();
      const mask = renderer.hitMask(64, 64);
      const regions = Axx.resident ? Axx.resident.interactiveRegions() : [];
      return {
        bounds: { x: canvasRect.x, y: canvasRect.y, width: canvasRect.width, height: canvasRect.height },
        cols: mask.cols,
        rows: mask.rows,
        bits: mask.bits.map(b => b === 1),
        regions
      };
    });

    const rustMask = new RustPixelMaskOracle(oracleSetup.bounds, oracleSetup.cols, oracleSetup.rows, oracleSetup.bits);

    const cornerCoords = [
      { name: 'Top-Left', x: oracleSetup.bounds.x + 10, y: oracleSetup.bounds.y + 10 },
      { name: 'Top-Right', x: oracleSetup.bounds.x + 520, y: oracleSetup.bounds.y + 10 },
      { name: 'Bottom-Left', x: oracleSetup.bounds.x + 10, y: oracleSetup.bounds.y + 520 },
      { name: 'Bottom-Right', x: oracleSetup.bounds.x + 520, y: oracleSetup.bounds.y + 520 }
    ];

    cornerCoords.forEach(c => {
      const maskContains = rustMask.contains(c.x, c.y);
      const rustDecision = computeRustIgnoreCursor(oracleSetup.regions, rustMask, c.x, c.y);
      recordTest(`2.1 Corner ${c.name} Rust PixelMask.contains evaluates to false`, !maskContains, { ...c, maskContains });
      recordTest(`2.2 Corner ${c.name} Rust hit-test evaluates inside=false, ignore=true (CLICK-THROUGH PASSED TO DESKTOP)`,
        !rustDecision.inside && rustDecision.ignore === true,
        { ...c, ...rustDecision }
      );
    });

    console.log('\n--- 3. EMPIRICAL TEST: AVATAR BODY HIT-TESTING (ALPHA > 16) ---');

    const bodyTest = await page.evaluate(() => {
      const renderer = Axx.app.renderer;
      const stage = document.getElementById('stage');
      const stageRect = stage.getBoundingClientRect();
      const canvasRect = renderer.canvas.getBoundingClientRect();
      const mask = renderer.hitMask(64, 64);
      const regions = Axx.resident ? Axx.resident.interactiveRegions() : [];

      // Test center of avatar body (265, 265 relative to 530x530 stage)
      const centerX = canvasRect.x + canvasRect.width / 2;
      const centerY = canvasRect.y + canvasRect.height / 2;
      const hitCenter = renderer.hitTest(centerX, centerY);

      // Radial samples at various distances from center
      const radialSamples = [];
      const radii = [30, 60, 90, 110];
      const angles = [0, Math.PI / 2, Math.PI, 3 * Math.PI / 2];

      for (const r of radii) {
        for (const theta of angles) {
          const sx = centerX + r * Math.cos(theta);
          const sy = centerY + r * Math.sin(theta);
          const hit = renderer.hitTest(sx, sy);
          const col = Math.min(mask.cols - 1, Math.floor(((sx - canvasRect.x) / canvasRect.width) * mask.cols));
          const row = Math.min(mask.rows - 1, Math.floor(((sy - canvasRect.y) / canvasRect.height) * mask.rows));
          const bit = mask.bits[row * mask.cols + col];
          radialSamples.push({ r, theta: (theta * 180 / Math.PI).toFixed(0), sx, sy, hit, bit });
        }
      }

      return {
        centerX,
        centerY,
        hitCenter,
        radialSamples
      };
    });

    recordTest('3.1 Center of avatar body (265, 265 relative) hitTest evaluates to true',
      bodyTest.hitCenter === true,
      { centerHit: bodyTest.hitCenter }
    );

    const rustCenterDecision = computeRustIgnoreCursor(oracleSetup.regions, rustMask, bodyTest.centerX, bodyTest.centerY);
    recordTest('3.2 Center of avatar body: Rust PixelMask.contains evaluates to true',
      rustMask.contains(bodyTest.centerX, bodyTest.centerY) === true,
      { contains: rustMask.contains(bodyTest.centerX, bodyTest.centerY) }
    );

    recordTest('3.3 Center of avatar body: Rust hit-test evaluates inside=true, ignore=false (CLICKS CAUGHT BY AXX)',
      rustCenterDecision.inside === true && rustCenterDecision.ignore === false,
      rustCenterDecision
    );

    const innerBodySamples = bodyTest.radialSamples.filter(s => s.r <= 60);
    const innerHits = innerBodySamples.every(s => s.hit === true && s.bit === 1);
    recordTest('3.4 Inner liquid body samples (radius <= 60px) all register hitTest=true and mask bit=1',
      innerHits,
      { innerBodySamples }
    );

    console.log('\n--- 4. EMPIRICAL TEST: ALPHA THRESHOLD RIGOROUS BOUNDARY CHECK (> 16) ---');

    const alphaThresholdCheck = await page.evaluate(() => {
      const mockCanvas = document.createElement('canvas');
      mockCanvas.width = 100;
      mockCanvas.height = 100;
      const ctx = mockCanvas.getContext('2d');
      const raster = {
        width: 10,
        height: 10,
        pixels: new Uint8ClampedArray(10 * 10 * 4)
      };

      function testSoftwareHitTest(alpha) {
        raster.pixels.fill(0);
        const idx = (5 * 10 + 5) * 4;
        raster.pixels[idx + 0] = 128;
        raster.pixels[idx + 1] = 128;
        raster.pixels[idx + 2] = 128;
        raster.pixels[idx + 3] = alpha;

        const dummyRenderer = {
          ctx,
          canvas: mockCanvas,
          raster,
          hitTest: Axx.SoftwareRenderer.prototype.hitTest
        };
        mockCanvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 });
        return dummyRenderer.hitTest(55, 55);
      }

      function testSoftwareHitMask(alpha) {
        raster.pixels.fill(0);
        const idx = (5 * 10 + 5) * 4;
        raster.pixels[idx + 0] = 128;
        raster.pixels[idx + 1] = 128;
        raster.pixels[idx + 2] = 128;
        raster.pixels[idx + 3] = alpha;

        const dummyRenderer = {
          ctx,
          canvas: mockCanvas,
          raster,
          hitMask: Axx.SoftwareRenderer.prototype.hitMask
        };
        mockCanvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 });
        const mask = dummyRenderer.hitMask(10, 10);
        return mask.bits[5 * 10 + 5];
      }

      return {
        hit_0: testSoftwareHitTest(0),
        hit_15: testSoftwareHitTest(15),
        hit_16: testSoftwareHitTest(16),
        hit_17: testSoftwareHitTest(17),
        hit_32: testSoftwareHitTest(32),
        hit_96: testSoftwareHitTest(96),
        hit_97: testSoftwareHitTest(97),
        hit_255: testSoftwareHitTest(255),

        mask_0: testSoftwareHitMask(0),
        mask_15: testSoftwareHitMask(15),
        mask_16: testSoftwareHitMask(16),
        mask_17: testSoftwareHitMask(17),
        mask_32: testSoftwareHitMask(32),
        mask_96: testSoftwareHitMask(96),
        mask_97: testSoftwareHitMask(97),
        mask_255: testSoftwareHitMask(255)
      };
    });

    recordTest('4.1 Alpha <= 16 (0, 15, 16) produces hitTest=false and mask bit=0 (transparent / click-through)',
      alphaThresholdCheck.hit_0 === false && alphaThresholdCheck.hit_15 === false && alphaThresholdCheck.hit_16 === false &&
      alphaThresholdCheck.mask_0 === 0 && alphaThresholdCheck.mask_15 === 0 && alphaThresholdCheck.mask_16 === 0,
      alphaThresholdCheck
    );

    recordTest('4.2 Alpha = 17 (just above threshold > 16) produces hitTest=true and mask bit=1 (hit caught)',
      alphaThresholdCheck.hit_17 === true && alphaThresholdCheck.mask_17 === 1,
      alphaThresholdCheck
    );

    recordTest('4.3 Alpha = 96 (previous LiquidRenderer threshold) now produces hitTest=true and mask bit=1',
      alphaThresholdCheck.hit_96 === true && alphaThresholdCheck.mask_96 === 1,
      alphaThresholdCheck
    );

    recordTest('4.4 Alpha = 255 (solid body) produces hitTest=true and mask bit=1',
      alphaThresholdCheck.hit_255 === true && alphaThresholdCheck.mask_255 === 1,
      alphaThresholdCheck
    );

    // Static code verification on LiquidRenderer source in Axx.html
    const hitMaskIdx = html.indexOf('hitMask(cols = 64, rows = 64)');
    const liquidHitMaskSource = html.slice(hitMaskIdx, hitMaskIdx + 2500);
    const has16InLiquidHitMask = liquidHitMaskSource.includes('> 16 ? 1 : 0');
    const has96InLiquidHitMask = liquidHitMaskSource.includes('> 96 ? 1 : 0');

    recordTest('4.5 LiquidRenderer.hitMask() in Axx.html uses > 16 and DOES NOT use > 96',
      has16InLiquidHitMask && !has96InLiquidHitMask,
      { has16InLiquidHitMask, has96InLiquidHitMask }
    );

    console.log('\n--- 5. EMPIRICAL TEST: DRAG CONTINUITY & THROTTLING ---');

    // 5.1 Drag continuity across boundaries
    // Start drag on body: lbutton_down = true, current_ignore = false
    const dragDecisionInside = computeRustIgnoreCursor(oracleSetup.regions, rustMask, bodyTest.centerX, bodyTest.centerY, true, false);
    // Cursor moves to corner (10, 10): lbutton_down = true, current_ignore was false
    const dragDecisionMovedToCorner = computeRustIgnoreCursor(oracleSetup.regions, rustMask, oracleSetup.bounds.x + 10, oracleSetup.bounds.y + 10, true, false);
    // User releases mouse button at corner: lbutton_down = false, current_ignore was false
    const dragDecisionReleasedAtCorner = computeRustIgnoreCursor(oracleSetup.regions, rustMask, oracleSetup.bounds.x + 10, oracleSetup.bounds.y + 10, false, false);

    recordTest('5.1a While mouse button is held down, moving outside body retains ignore=false (drag does not drop)',
      dragDecisionMovedToCorner.inside === false && dragDecisionMovedToCorner.ignore === false,
      { dragDecisionMovedToCorner }
    );

    recordTest('5.1b Once mouse button is released outside, ignore reverts to true (restoring click-through)',
      dragDecisionReleasedAtCorner.inside === false && dragDecisionReleasedAtCorner.ignore === true,
      { dragDecisionReleasedAtCorner }
    );

    // 5.2 Cursor throttling in lib.rs
    const libRsContent = fs.readFileSync(path.join(__dirname, '../src-tauri/src/lib.rs'), 'utf8');
    const hasThrottling = libRsContent.includes('if point.x != last_x || point.y != last_y {') &&
      libRsContent.includes('last_x = point.x;') &&
      libRsContent.includes('last_y = point.y;');

    recordTest('5.2 src-tauri/src/lib.rs implements cursor IPC throttling on point.x != last_x || point.y != last_y',
      hasThrottling,
      { hasThrottling }
    );

    console.log('\n--- 6. EMPIRICAL TEST: VERIFY NO TRANSPARENT DEAD ZONE REMAINS ---');

    // Sample a 10x10 grid over the 530x530 stage area
    const deadZoneGrid = await page.evaluate(() => {
      const renderer = Axx.app.renderer;
      const stage = document.getElementById('stage');
      const stageRect = stage.getBoundingClientRect();
      const canvasRect = renderer.canvas.getBoundingClientRect();
      const mask = renderer.hitMask(64, 64);
      const regions = Axx.resident ? Axx.resident.interactiveRegions() : [];

      let totalSampled = 0;
      let solidSampled = 0;
      let transparentSampled = 0;
      let deadZoneViolations = 0;

      for (let gx = 0; gx < 10; gx++) {
        for (let gy = 0; gy < 10; gy++) {
          totalSampled++;
          const sx = stageRect.x + (gx / 9) * (stageRect.width - 2) + 1;
          const sy = stageRect.y + (gy / 9) * (stageRect.height - 2) + 1;

          const col = Math.min(mask.cols - 1, Math.floor(((sx - canvasRect.x) / canvasRect.width) * mask.cols));
          const row = Math.min(mask.rows - 1, Math.floor(((sy - canvasRect.y) / canvasRect.height) * mask.rows));
          const bit = mask.bits[row * mask.cols + col];

          // Check direct hit
          const hit = renderer.hitTest(sx, sy);
          const regionHit = regions.some(r => sx >= r.x && sy >= r.y && sx < r.x + r.width && sy < r.y + r.height);

          if (bit === 1 || hit) {
            solidSampled++;
          } else {
            transparentSampled++;
            // If bit === 0 and hit === false, but regionHit === true because of stage/avatar -> that would be a dead zone!
            if (regionHit) {
              deadZoneViolations++;
            }
          }
        }
      }

      return {
        totalSampled,
        solidSampled,
        transparentSampled,
        deadZoneViolations
      };
    });

    recordTest('6.1 10x10 Grid over #stage reveals zero dead zone violations across all transparent samples',
      deadZoneGrid.deadZoneViolations === 0 && deadZoneGrid.transparentSampled > 30,
      deadZoneGrid
    );

  } finally {
    await browser.close();
    server.close();
  }

  console.log('\n==================================================');
  console.log(`TOTAL TESTS: ${results.total}`);
  console.log(`PASSED: ${results.passed}`);
  console.log(`FAILED: ${results.failed}`);
  console.log('==================================================\n');

  if (results.failed > 0) {
    process.exit(1);
  }
})();
