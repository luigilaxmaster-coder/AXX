// WebGL contract for technical engineering shapes: verifies rendering, triangle counts, and clean disposal.
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const out = path.resolve(__dirname, '../../build/magic-pen-desktop'); fs.mkdirSync(out, { recursive: true });
  const server = http.createServer((req, res) => {
    if (!req.url.startsWith('/scripts/')) { res.setHeader('Content-Type', 'text/html'); return res.end('<!doctype html><body style="margin:0;background:#1b2230"></body>'); }
    res.setHeader('Content-Type', 'application/javascript'); res.end(fs.readFileSync(path.join(__dirname, path.basename(req.url))));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM });
  try {
    const page = await browser.newPage({ viewport: { width: 1000, height: 750 } }), errors = [];
    page.on('pageerror', e => errors.push(e.stack || e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const result = await page.evaluate(async () => {
      const { mountScene, liveScenes } = await import('/scripts/spatial-scene.js');
      const techShapes = ['gear', 'coil', 'l_bracket', 'u_channel', 'i_beam', 'pipe_elbow', 'heatsink', 'flange', 'pyramid', 'chamfer_cylinder', 'threaded_rod', 'slot', 'rect_tube', 'arc', 'knurled_cylinder', 'octaprism', 'paraboloid', 'arch', 'dna_helix', 'tapered_capsule', 'hyperboloid', 'barrel', 'trefoil_knot', 'triangular_prism', 'pentaprism', 'helix_spring', 'tetrahedron', 'dodecahedron', 'icosahedron', 'bipyramid', 'fluted_column', 'conical_spring'];
      const materials = ['metal_polished', 'metal_anodized', 'metal_brushed', 'plastic', 'ceramic'];
      const objects = techShapes.map((shape, i) => ({
        id: 'tech_' + (i + 1),
        label: shape,
        shape,
        size: [1.2, 1.2, 1.0],
        position: [(i % 5) * 1.8 - 3.6, 2.2 - Math.floor(i / 5) * 2.0, 0],
        color: ['#d4af37', '#4682b4', '#708090', '#cd853f', '#2e8b57'][i % 5],
        material: materials[i % materials.length],
        param: shape === 'gear' ? 14 : shape === 'coil' ? 5 : shape === 'heatsink' ? 6 : shape === 'flange' ? 6 : shape === 'threaded_rod' ? 14 : shape === 'arc' ? 200 : shape === 'knurled_cylinder' ? 24 : 0.2
      }));
      const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:750px;position:relative'; document.body.append(host);
      const before = liveScenes(), view = mountScene(host, { fidelity: 'technical', objects, arrows: [] }, { reducedMotion: true });
      const qa = view.qa(), img = new Image(); img.src = view.snapshot(); await img.decode();
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const x = c.getContext('2d'); x.drawImage(img, 0, 0);
      const d = x.getImageData(0, 0, c.width, c.height).data; let lit = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 16) lit++;
      const shot = view.snapshot();
      view.dispose();
      return { before, during: before + 1, after: liveScenes(), qa, lit, total: img.width * img.height, shot };
    });
    fs.writeFileSync(path.join(out, 'spatial-tech-shapes.png'), Buffer.from(result.shot.split(',')[1], 'base64'));
    assert.equal(errors.length, 0, errors.join('\n'));
    assert.equal(result.qa.objects, 32);
    assert.ok(result.qa.webgl && result.qa.finite, 'WebGL context alive and camera finite');
    assert.ok(result.qa.triangles > 3000, 'Detailed technical shapes produce real geometry: ' + result.qa.triangles);
    assert.ok(result.lit > result.total * .03, 'The scene paints visible pixels: ' + result.lit + '/' + result.total);
    assert.equal(result.after, result.before, 'Disposing releases every scene');
    console.log('PASS technical shapes:', JSON.stringify({ triangles: result.qa.triangles, litPercent: +(100 * result.lit / result.total).toFixed(1) }));
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
