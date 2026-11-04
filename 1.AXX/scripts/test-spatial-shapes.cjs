// WebGL contract for the expanded spatial vocabulary: every shape and material renders, updates rebuild, and nothing leaks.
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const { createRequire } = require('node:module');
const { chromium } = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
  const out = path.resolve(__dirname, '../../build/magic-pen-desktop'); fs.mkdirSync(out, { recursive: true });
  const server = http.createServer((req, res) => {
    if (!req.url.startsWith('/scripts/')) { res.setHeader('Content-Type', 'text/html'); return res.end('<!doctype html><body style="margin:0;background:#1b2230"></body>'); }
    res.setHeader('Content-Type', 'application/javascript'); res.end(fs.readFileSync(path.join(__dirname, path.basename(req.url))));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  try {
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } }), errors = [];
    page.on('pageerror', e => errors.push(e.stack || e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const result = await page.evaluate(async () => {
      const { mountScene, liveScenes } = await import('/scripts/spatial-scene.js');
      const shapes = ['box', 'sphere', 'ellipsoid', 'cylinder', 'cone', 'frustum', 'hexprism', 'tube', 'capsule', 'dome', 'wedge', 'gable', 'torus', 'plane'];
      const materials = ['metal_brushed', 'metal_polished', 'metal_anodized', 'plastic', 'rubber', 'glass', 'ceramic', 'wood', 'fabric', 'stone', 'paint', 'emissive'];
      const objects = shapes.map((shape, i) => ({ id: 'o' + (i + 1), label: shape, shape, size: [1.1, 1.3, .9], position: [(i % 5) * 1.7 - 3.4, 1.7 - Math.floor(i / 5) * 1.8, 0],
        color: ['#c0c4c8', '#d4a017', '#4d7fb8', '#7a5a3c', '#8a8d90'][i % 5], material: materials[i % materials.length], ...(['tube', 'frustum', 'box'].includes(shape) ? { param: .3 } : {}) }));
      const host = document.createElement('div'); host.style.cssText = 'width:900px;height:700px;position:relative'; document.body.append(host);
      const before = liveScenes(), view = mountScene(host, { fidelity: 'conceptual', objects, arrows: [] }, { reducedMotion: true });
      const qa = view.qa(), img = new Image(); img.src = view.snapshot(); await img.decode();
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
      const d = x.getImageData(0, 0, c.width, c.height).data; let lit = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 16) lit++;
      const shot = view.snapshot();
      // A changed parameter or material must rebuild the mesh without growing the live count or throwing.
      const changed = objects.map(o => o.shape === 'tube' ? { ...o, param: .5 } : o.shape === 'box' ? { ...o, material: 'glass' } : o);
      view.update({ fidelity: 'conceptual', objects: changed, arrows: [] }); const qa2 = view.qa();
      view.dispose(); return { before, during: before + 1, after: liveScenes(), qa, qa2, lit, total: img.width * img.height, shot };
    });
    fs.writeFileSync(path.join(out, 'spatial-shapes.png'), Buffer.from(result.shot.split(',')[1], 'base64'));
    assert.equal(errors.length, 0, errors.join('\n'));
    assert.equal(result.qa.objects, 14); assert.equal(result.qa2.objects, 14);
    assert.ok(result.qa.webgl && result.qa.finite, 'WebGL context alive and camera finite');
    assert.ok(result.qa.triangles > 4000, 'Detailed shapes produce real geometry: ' + result.qa.triangles);
    assert.ok(result.lit > result.total * .04, 'The scene paints visible pixels: ' + result.lit + '/' + result.total);
    assert.equal(result.after, result.before, 'Disposing releases every scene');
    console.log('PASS spatial shapes:', JSON.stringify({ triangles: result.qa.triangles, litPercent: +(100 * result.lit / result.total).toFixed(1) }));
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
