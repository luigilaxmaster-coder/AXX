// Exploded view contract: without model vectors the pieces really separate (sub-assemblies move apart), explicit vectors win, and the
// camera keeps the exploded assembly in frame and returns when it is put back together.
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const server = http.createServer((req, res) => {
    if (!req.url.startsWith('/scripts/')) { res.setHeader('Content-Type', 'text/html'); return res.end('<!doctype html><body style="margin:0;background:#1b2230"></body>'); }
    res.setHeader('Content-Type', 'application/javascript'); res.end(fs.readFileSync(path.join(__dirname, path.basename(req.url))));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM });
  try {
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } }), errors = [];
    page.on('pageerror', e => errors.push(e.stack || e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const r = await page.evaluate(async () => {
      const { mountScene, explodeVectors, liveScenes } = await import('/scripts/spatial-scene.js');
      const obj = (id, group, position, size, extra = {}) => ({ id, label: id, shape: 'cylinder', size, position, color: '#9aa4b2', ...(group ? { group } : {}), ...extra });
      const objects = [
        obj('body', 'Motor DC', [0, 0, 0], [2, 3, 2], { rotation: [0, 0, 90] }), obj('cap1', 'Motor DC', [-1.7, 0, 0], [2, .4, 2], { rotation: [0, 0, 90] }), obj('cap2', 'Motor DC', [1.7, 0, 0], [2, .4, 2], { rotation: [0, 0, 90] }),
        obj('shaft', '', [0, 0, 0], [.3, 6, .3], { rotation: [0, 0, 90] }), obj('bracket', 'Escuadra', [0, -2.2, 0], [3, .3, 2]), obj('foot', 'Escuadra', [0, -2.6, 1], [3, .8, .3]),
        obj('bolt', '', [1, -1.8, 0.6], [.3, .5, .3]), obj('given', '', [0, 1.6, 0], [1, 1, 1], { explode: [0, 4, 0] })];
      const vectors = explodeVectors(objects), plain = explodeVectors(objects.map(o => ({ ...o, explode: undefined })));
      const host = document.createElement('div'); host.style.cssText = 'width:900px;height:700px;position:relative'; document.body.append(host);
      const view = mountScene(host, { fidelity: 'conceptual', objects, arrows: [] }, { reducedMotion: true });
      const box = async () => { const img = new Image(); img.src = view.snapshot(); await img.decode(); const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
        const d = x.getImageData(0, 0, c.width, c.height).data; let x0 = c.width, x1 = 0, y0 = c.height, y1 = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 16) { const p = (i - 3) / 4, px = p % c.width, py = Math.floor(p / c.width); x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py); }
        return { w: x1 - x0, h: y1 - y0, x0, y0, x1, y1, cw: c.width, ch: c.height }; };
      const rest = await box(), restDistance = view.getView().distance;
      view.setExploded(true); await new Promise(r => setTimeout(r, 200)); const open = await box(), openDistance = view.getView().distance;
      view.setExploded(false); await new Promise(r => setTimeout(r, 200)); const closedDistance = view.getView().distance;
      view.dispose();
      return { vectors: [...vectors], plain: [...plain], rest, open, restDistance, openDistance, closedDistance, live: liveScenes() };
    });
    assert.equal(errors.length, 0, errors.join('\n'));
    const v = Object.fromEntries(r.vectors), p = Object.fromEntries(r.plain);
    assert.deepEqual(v.given, undefined, 'An explicit vector is never recomputed'); assert.equal(Object.keys(p).length, 8, 'Every piece gets a computed vector when none is given');
    assert.ok(new Set(Object.values(p).map(x => x.join())).size >= 6, 'Pieces do not all move by the same amount: ' + JSON.stringify(p));
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    assert.ok(dot(p.bracket, [0, -1, 0]) > 0, 'The lower sub-assembly leaves downwards'); assert.ok(dot(p.cap1, [-1, 0, 0]) > 0 && dot(p.cap2, [1, 0, 0]) > 0, 'Sub-assembly members open outwards from their own centre');
    assert.ok(Math.abs(p.shaft[0]) > 1, 'A central piece slides along the main axis');
    for (const x of Object.values(p)) assert.ok(Math.hypot(...x) < 9, 'Displacements stay bounded');
    const extent = (box, distance) => Math.max(box.w, box.h) * distance;  // apparent size x camera distance ~ real extent
    assert.ok(extent(r.open, r.openDistance) > extent(r.rest, r.restDistance) * 1.25, `Exploding spreads the assembly: ${JSON.stringify(r.rest)}@${r.restDistance} -> ${JSON.stringify(r.open)}@${r.openDistance}`);
    assert.ok(r.open.x0 > 2 && r.open.y0 > 2 && r.open.x1 < r.open.cw - 2 && r.open.y1 < r.open.ch - 2, 'The exploded assembly stays inside the frame: ' + JSON.stringify(r.open));
    assert.ok(r.openDistance > r.restDistance, 'The camera backs off while exploded'); assert.equal(r.closedDistance, r.restDistance, 'The resting camera distance comes back');
    assert.equal(r.live, 0, 'Disposing releases the scene');
    console.log('PASS explode:', JSON.stringify({ rest: [r.rest.w, r.rest.h], open: [r.open.w, r.open.h], distance: [r.restDistance, r.openDistance] }));
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
