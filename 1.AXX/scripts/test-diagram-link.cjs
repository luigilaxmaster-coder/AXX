// A diagram node reports its step and its node, so Magic Pen can focus the linked 3D piece.
const assert = require('node:assert/strict'), fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const { createRequire } = require('node:module');
const { chromium } = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
  const server = http.createServer((req, res) => {
    if (!req.url.startsWith('/scripts/')) { res.setHeader('Content-Type', 'text/html'); return res.end('<!doctype html><body></body>'); }
    res.setHeader('Content-Type', 'application/javascript'); res.end(fs.readFileSync(path.join(__dirname, path.basename(req.url))));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  try {
    const page = await browser.newPage(), errors = [];
    page.on('pageerror', e => errors.push(String(e))); await page.goto(`http://127.0.0.1:${server.address().port}/`);
    const calls = await page.evaluate(async () => {
      const { renderDiagram } = await import('/scripts/visual-canvas.js');
      const host = document.createElement('div'); document.body.append(host); const log = [];
      const diagram = { nodes: [{ id: 'd1', label: 'Rodamiento', step_id: 's2', bounds: [.1, .1, .3, .2], object_id: 'o3' }, { id: 'd2', label: 'Carcasa', step_id: 's1', bounds: [.6, .6, .3, .2] }],
        edges: [{ from: 'd1', to: 'd2', label: 'apoya' }] };
      renderDiagram(host, diagram, 's1', (step, node) => log.push([step, node && node.id, node && node.object_id || null]));
      const nodes = host.querySelectorAll('.mp-diagram-node');
      nodes[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
      nodes[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      return log;
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(calls, [['s2', 'd1', 'o3'], ['s1', 'd2', null]], 'click and Enter pass the step and the node (with its linked piece, if any)');
    console.log('PASS diagram node link');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
