// Real installed WebView/IPC/screen capture/provider. The visible stimulus is a
// disposable browser window with known content, never a mocked capture or answer.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.USERPROFILE + '/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const out = path.resolve('build/chat-' + require('../package.json').version + '/magic-pen'); fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
  const page = browser.contexts()[0].pages().find(p => p.url().includes('Axx.html'));
  assert(page, 'Installed Axx WebView unavailable');
  const receipt = { kind: 'INSTALLED_MAGIC_PEN_NATIVE_CAPTURE_REAL_VISION', started: new Date().toISOString(), checks: [] };
  const api = (op, body = {}) => page.evaluate(({ op, body }) => Axx.backendRequest('POST', '/axx-api/pen/' + op, body), { op, body });
  const clickControl = async selector => {
    if (!await page.locator(selector).isVisible()) await page.locator('#mp-more-toggle').click();
    await page.locator(selector).click();
  };
  let fixture, prior;
  try {
    page.setDefaultTimeout(12000);
    await page.waitForFunction(() => Axx.magicPen && Axx.chatWorkspace?.ready);
    prior = await page.evaluate(() => ({ theme: Axx.interfaceTheme.value, view: Axx.companion.dock.selected, preferences: localStorage.getItem('axx.magicpen.prefs'), question: document.getElementById('mp-question').value }));
    await page.evaluate(() => Axx.chatWorkspace.flush());
    receipt.runtime = JSON.parse(fs.readFileSync(process.env.LOCALAPPDATA + '/Axx/logs/native-runtime.json', 'utf8'));
    const desktop = await page.evaluate(async () => (await Axx.nativeInvoke('native_status')).desktop);
    const origin = { x: Math.round(desktop.screenX - desktop.anchorX * desktop.scaleFactor), y: Math.round(desktop.screenY - desktop.anchorY * desktop.scaleFactor) };
    fixture = await chromium.launch({ channel: 'chrome', headless: false, args: ['--window-position=' + (origin.x + 580) + ',70', '--window-size=940,720'] });
    const stimulus = await fixture.newPage({ viewport: null });
    await stimulus.setContent('<!doctype html><html lang="es"><head><title>Aceptación de Magic Pen</title><style>html,body{margin:0;background:#fff;color:#111;font-family:Arial,sans-serif}main{padding:44px;height:500px;box-sizing:border-box}h1{font-size:48px;margin:0 0 28px}p{font-size:24px}.shape{position:absolute;left:560px;top:310px;width:170px;height:130px;background:#125ce0}</style></head><body><main><h1>MAGIC PEN 4279</h1><p>Captura nativa de prueba.</p><div class="shape" aria-label="Rectángulo azul"></div></main></body></html>');
    await stimulus.bringToFront();
    receipt.stimulus = await stimulus.evaluate(() => ({ screenX, screenY, outerWidth, outerHeight, innerWidth, innerHeight }));
    // Chromium's command-line position can be virtualized on mixed-DPI Windows.
    // Position only this disposable fixture in physical coordinates.
    const title = 'Axx Magic Pen fixture ' + Date.now();
    await stimulus.evaluate(t => { document.title = t; }, title);
    receipt.stimulus.physical = JSON.parse(execFileSync('python', ['-c', `import ctypes,json,sys,time
from ctypes import wintypes as w
u=ctypes.WinDLL('user32',use_last_error=True)
u.SetThreadDpiAwarenessContext.argtypes=[w.HANDLE];u.SetThreadDpiAwarenessContext.restype=w.HANDLE
old=u.SetThreadDpiAwarenessContext(w.HANDLE(-4))
assert old
callback=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
u.EnumWindows.argtypes=[callback,w.LPARAM];u.EnumWindows.restype=w.BOOL
u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int];u.GetWindowTextW.restype=ctypes.c_int
u.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT];u.SetWindowPos.restype=w.BOOL
u.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)];u.GetWindowRect.restype=w.BOOL
u.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)];u.GetWindowThreadProcessId.restype=w.DWORD
found=[]
@callback
def visit(hwnd,_):
 text=ctypes.create_unicode_buffer(1024);u.GetWindowTextW(hwnd,text,1024)
 if sys.argv[1] in text.value:found.append(hwnd)
 return True
try:
 for _ in range(20):
  found.clear();u.EnumWindows(visit,0)
  if found:break
  time.sleep(.1)
 assert len(found)==1,found
 x,y,width,height=map(int,sys.argv[2:])
 # Raise this disposable fixture above other ordinary windows without activation.
 # Keep Axx's topmost transparent overlay above the fixture.
 assert u.SetWindowPos(found[0],None,x,y,width,height,16)
 rect=w.RECT();assert u.GetWindowRect(found[0],ctypes.byref(rect))
 pid=w.DWORD();u.GetWindowThreadProcessId(found[0],ctypes.byref(pid))
 print(json.dumps(dict(left=rect.left,top=rect.top,right=rect.right,bottom=rect.bottom,window_id=found[0],pid=pid.value)))
finally:u.SetThreadDpiAwarenessContext(old)
`, title, String(origin.x + 580), '70', '940', '720'], { windowsHide: true, encoding: 'utf8' }));
    receipt.stimulus.focus = await page.evaluate(async target => {
      const prepared = await Axx.backendRequest('POST', '/axx-api/commands/prepare', { command_id: 'axx.desktop.window.focus', inputs: { window_id: '0x' + target.window_id.toString(16), pid: target.pid }, source: 'text' });
      return Axx.backendRequest('POST', '/axx-api/commands/execute', { operation_id: prepared.operation_id, approved: true });
    }, receipt.stimulus.physical);
    assert.equal(receipt.stimulus.focus.state, 'succeeded', 'The disposable stimulus must have confirmed foreground before capture');
    await stimulus.screenshot({ path: path.join(out, 'stimulus.png') });
    await page.evaluate(() => { Axx.resident.summon(false); Axx.magicPen.open(); });
    await page.waitForFunction(() => Axx.magicPen.active && !Axx.magicPen.working && (Axx.magicPen.doc || Axx.magicPen.state === 'error'));
    const opened = await page.evaluate(() => ({ source: Axx.magicPen.doc?.source, status: document.getElementById('mp-status').textContent }));
    assert(opened.source, 'Native desktop capture failed: ' + opened.status);
    await page.locator('#mp-more-toggle').focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('mp-more-tools').open);
    await page.waitForFunction(() => {
      const rect = document.getElementById('mp-more-panel').getBoundingClientRect();
      return Axx.resident.interactiveRegions().some(r => Math.abs(r.x - rect.x) < 1 && Math.abs(r.y - rect.y) < 1 && Math.abs(r.width - rect.width) < 1 && Math.abs(r.height - rect.height) < 1);
    });
    await page.locator('#mp-more-panel').screenshot({ path: path.join(out, 'more-tools.png') });
    await page.locator('#mp-more-toggle').click();
    await page.locator('#mp-toolbar').screenshot({ path: path.join(out, 'compact-toolbar.png') });
    receipt.checks.push('Compact toolbar and keyboard disclosure expose the secondary tools with their own native hit region');
    assert.equal(await page.locator('#mp-more-tools').evaluate(el => el.open), false);
    if (await page.locator('#mp-live').getAttribute('aria-pressed') !== 'true') await clickControl('#mp-live');
    if (await page.locator('#mp-pause').innerText() === 'Reanudar') await clickControl('#mp-pause');
    if (await page.locator('#mp-more-tools').evaluate(el => el.open)) await page.locator('#mp-more-toggle').click();
    const geometry = await page.evaluate(() => ({ source: Axx.magicPen.doc.source, viewport: Axx.magicPen.viewport }));
    receipt.geometry = geometry;
    const question = 'Transcribe los números visibles y describe la forma y su color.';
    // The question editor appears only after selection; establish a neutral
    // fixture before the automatic analysis without revealing the expected text.
    await page.locator('#mp-question').evaluate((input, value) => { input.value = value; }, question);
    assert.equal(await page.locator('#panel').isVisible(), false);
    assert.equal(await page.evaluate(() => Axx.magicPen.ctx.getImageData(40, 40, 1, 1).data[3]), 0, 'Desktop canvas must stay transparent');
    const fixtureBox = receipt.stimulus.physical, viewport = geometry.viewport;
    const target = { x0: (fixtureBox.left + 20 - viewport.x) / viewport.scale, y0: (fixtureBox.top + 90 - viewport.y) / viewport.scale, x1: (fixtureBox.right - 20 - viewport.x) / viewport.scale, y1: (fixtureBox.bottom - 30 - viewport.y) / viewport.scale };
    const mark = async (tool, points) => {
      await clickControl('[data-mp-tool="' + tool + '"]');
      await page.waitForFunction(() => !Axx.magicPen.working && Axx.magicPen.inputEnabled);
      await page.mouse.move(...points[0]); await page.mouse.down();
      for (const point of points.slice(1)) await page.mouse.move(...point, { steps: 8 });
      await page.mouse.up();
    };
    const began = Date.now();
    await mark('rect', [[target.x0, target.y0], [target.x1, target.y1]]);
    await page.waitForFunction(() => Axx.magicPen.doc?.queries.some(q => q.state === 'completed' || q.state === 'failed'), null, { timeout: 90000 });
    const query = await page.evaluate(() => Axx.magicPen.doc.queries.at(-1));
    receipt.analysis_ms = Date.now() - began; receipt.query = query;
    const docId = query.source_id;
    const saved = await api('get', { id: docId }); assert(saved.preview?.startsWith('data:image/png;base64,'));
    fs.writeFileSync(path.join(out, 'native-capture.png'), Buffer.from(saved.preview.split(',')[1], 'base64'));
    assert.equal(query.state, 'completed', query.error);
    assert(query.question.startsWith(question)); assert.match(query.question, /Resumen:.*24 palabras/);
    const v = geometry.viewport, s = geometry.source;
    const expectedBounds = [v.x + target.x0 * v.scale - s.x, v.y + target.y0 * v.scale - s.y, v.x + target.x1 * v.scale - s.x, v.y + target.y1 * v.scale - s.y];
    assert.equal(query.selection.shape, 'rect');
    assert.deepEqual(query.selection.bounds, expectedBounds);
    assert.match(query.response, /4279/); assert.match(query.response, /azul/i);
    await page.waitForFunction(() => Axx.magicPen.summaryBubbleMode && document.getElementById('mp-summary-bubble').getClientRects().length > 0);
    receipt.summary = await page.locator('#mp-summary-text').innerText();
    assert(receipt.summary.length > 0 && receipt.summary.split(/\s+/).length <= 28, 'The avatar bubble must show a concise explanation');
    await page.screenshot({ path: path.join(out, 'magic-pen-summary-bubble.png') });
    await page.locator('#mp-summary-expand').click();
    assert.equal(await page.locator('#mp-summary-bubble').isVisible(), false);
    assert.equal(await page.locator('#mp-answers').isVisible(), true);
    assert.match(await page.locator('#mp-answers').innerText(), /4279/);
    receipt.checks.push('Concise avatar-origin summary appears for the real selection and expands to the complete provider answer');
    const prefs = await page.evaluate(() => ({ name: Axx.companion.data.prefs.apiConnection, model: Axx.companion.data.prefs.model }));
    assert.equal(query.provider.name, prefs.name); assert.equal(query.provider.model, prefs.model);
    receipt.checks.push('Real desktop selection recognized known digits and blue rectangle through selected provider');

    // Stop is deterministic even if the actual provider answers unusually fast:
    // cancel immediately after start and verify its persisted terminal state.
    const requestId = require('node:crypto').randomBytes(16).toString('hex');
    const job = await api('start', { id: docId, revision: saved.revision, question: 'Describe el contenido visible.', provider: prefs.name, model: prefs.model, selection_mode: 'manual', request_id: requestId });
    const cancelBegan = Date.now(); const cancelled = await api('cancel', { id: docId, query_id: job.id });
    assert.equal(cancelled.state, 'cancelled');
    receipt.cancel_ms = Date.now() - cancelBegan;
    await page.waitForTimeout(300);
    assert.equal((await api('query', { id: docId, query_id: job.id })).state, 'cancelled');
    receipt.checks.push('Packaged backend cancellation persisted and discarded late completion');

    // A new pen gesture must remain available while the real model is working.
    await page.locator('#mp-question').fill('Explica los elementos de la imagen en cinco frases.');
    await page.locator('#mp-ask').click();
    await page.waitForFunction(() => Axx.magicPen.analysisJob && !Axx.magicPen.working);
    const replaced = await page.evaluate(() => Axx.magicPen.analysisJob);
    await mark('pen', [[680, 250], [840, 250], [840, 285]]);
    assert((await page.evaluate(() => Axx.magicPen.doc.strokes.length)) > 0, 'Ink must be accepted while inference is pending');
    await page.waitForFunction(() => !Axx.magicPen.analysisPending && !Axx.magicPen.liveTimer && Axx.magicPen.doc?.queries.some(q => q.state === 'completed' || q.state === 'failed'), null, { timeout: 90000 });
    const ink = await page.evaluate(() => ({ id: Axx.magicPen.doc.id, query: Axx.magicPen.doc.queries.at(-1), strokes: Axx.magicPen.doc.strokes.length }));
    assert.equal(ink.query.state, 'completed', ink.query.error);
    assert.notEqual(ink.query.id, replaced.id);
    receipt.ink = ink;
    receipt.checks.push('Ink accepted during real inference; pause automatically analyzed the new region without another Ask');

    await clickControl('#mp-pause');
    assert.equal(await page.locator('#mp-pause').innerText(), 'Reanudar');
    const beforePause = await page.evaluate(() => Axx.magicPen.doc.id);
    await mark('pen', [[900, 280], [950, 300]]);
    await page.waitForTimeout(900);
    assert.equal(await page.evaluate(() => Axx.magicPen.doc.id), beforePause);
    assert.equal(await page.evaluate(() => Axx.magicPen.analysisPending), false);
    receipt.checks.push('Paused live mode retains ink without automatically capturing or asking');

    // Exercise every selection/ink button reported as unresponsive, with live
    // analysis paused so these gestures do not send additional desktop content.
    await mark('point', [[760, 350]]);
    await page.waitForFunction(() => !Axx.magicPen.working && Axx.magicPen.doc?.selection?.shape === 'point');
    await mark('lasso', [[720, 320], [920, 320], [920, 480], [720, 480], [720, 320]]);
    await page.waitForFunction(() => !Axx.magicPen.working && Axx.magicPen.doc?.selection?.shape === 'lasso');
    await clickControl('#mp-all');
    await page.waitForFunction(() => !Axx.magicPen.working && Axx.magicPen.doc?.selection?.bounds?.[0] === 0);
    assert.deepEqual(await page.evaluate(() => Axx.magicPen.doc.selection.bounds), [0, 0, geometry.source.width, geometry.source.height]);
    const strokesBefore = await page.evaluate(() => Axx.magicPen.doc.strokes.length);
    await mark('marker', [[1050, 450], [1170, 450]]);
    assert.equal(await page.evaluate(() => Axx.magicPen.doc.strokes.length), strokesBefore + 1);
    await page.locator('#mp-undo').click();
    assert.equal(await page.evaluate(() => Axx.magicPen.doc.strokes.length), strokesBefore);
    await clickControl('#mp-redo');
    assert.equal(await page.evaluate(() => Axx.magicPen.doc.strokes.length), strokesBefore + 1);
    await mark('erase', [[1100, 450]]);
    assert.equal(await page.evaluate(() => Axx.magicPen.doc.strokes.length), strokesBefore);
    await page.locator('#mp-interact').click();
    assert.equal(await page.evaluate(() => Axx.magicPen.inputEnabled), false);
    receipt.checks.push('Point, lasso, whole screen, marker, eraser, undo, redo and desktop interaction respond through actual controls');

    await page.evaluate(() => Axx.magicPen.refresh());
    await page.locator('#mp-widget details.mp-save-section').evaluate(e => { e.open = true; });
    await page.locator('#mp-history').selectOption(docId);
    await page.waitForFunction(() => Axx.magicPen.historyMode && !Axx.magicPen.working);
    assert.equal(await page.locator('#mp-history-preview').isVisible(), true);
    assert.equal(await page.locator('#mp-canvas').isVisible(), false);
    assert((await page.locator('#mp-preview-canvas').evaluate(c => c.width)) > 0);
    receipt.checks.push('Saved capture and answer restored in separate preview, never overlaid on live desktop');
    for (const theme of ['light', 'dark']) {
      await page.evaluate(t => Axx.interfaceTheme.apply(t), theme);
      const metrics = await page.evaluate(() => {
        const w = document.getElementById('mp-widget').getBoundingClientRect();
        const t = document.getElementById('mp-toolbar').getBoundingClientRect();
        return { widgetBottom: w.bottom, toolbarTop: t.top, toolbarWidth: t.width, viewport: innerWidth, controls: ['mp-interact', 'mp-more-toggle', 'mp-done'].map(id => ({ id, height: document.getElementById(id).getBoundingClientRect().height })) };
      });
      assert(metrics.widgetBottom <= metrics.toolbarTop - 2, 'Historical widget overlaps toolbar');
      assert(metrics.toolbarWidth <= metrics.viewport, 'Toolbar exceeds viewport');
      assert(metrics.controls.every(c => c.height >= 40), 'Primary controls must remain at least 40 px');
      await page.locator('#mp-widget').screenshot({ path: path.join(out, 'history-' + theme + '.png') });
      await page.locator('#mp-toolbar').screenshot({ path: path.join(out, 'toolbar-' + theme + '.png') });
      receipt.checks.push('Readable ' + theme + ' surfaces, separated toolbar/widget and 40 px controls');
    }
    await page.locator('#mp-back-desktop').click();
    await page.waitForFunction(() => !Axx.magicPen.historyMode && !!Axx.magicPen.viewport && !Axx.magicPen.working);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#mp-desktop').isVisible(), false);
    await page.evaluate(() => Axx.magicPen.open());
    await page.waitForFunction(() => Axx.magicPen.active && !Axx.magicPen.working && !!Axx.magicPen.doc);
    assert.equal(await page.evaluate(() => Axx.magicPen.analysisPending), false);
    assert.equal(await page.locator('#panel').isVisible(), false);
    receipt.checks.push('Return to live desktop, Escape and reopen recover without old pending analysis or overlapping panel');

    await page.evaluate(() => Axx.magicPen.close());
    // The avatar can start on either display. Explicitly exercise another
    // physical monitor so a successful primary-screen run cannot hide DPI drift.
    const displays = (await api('status')).monitors;
    const recordingMonitor = displays.find(m => m.id !== geometry.source.id) || displays.find(m => m.id === geometry.source.id);
    assert(recordingMonitor, 'Capture monitor disappeared');
    receipt.monitorCoverage = { interaction: geometry.source, recording: recordingMonitor, multiple: displays.length > 1 };
    if (displays.length > 1) {
      assert.notEqual(recordingMonitor.id, geometry.source.id);
      const secondary = await page.evaluate(monitor => Axx.nativeInvoke('magic_pen_capture', { monitor }), recordingMonitor.id);
      assert.equal(secondary.source.id, recordingMonitor.id);
      assert.deepEqual([secondary.source.x, secondary.source.y, secondary.source.width, secondary.source.height], [recordingMonitor.x, recordingMonitor.y, recordingMonitor.width, recordingMonitor.height]);
      receipt.secondaryCapture = secondary.source;
      receipt.checks.push('Explicit capture of another physical monitor matches the enumerated DPI-aware bounds');
    }
    if (process.env.AXX_MAGIC_PEN_SKIP_RECORDING === '1') {
      receipt.recording = { state: 'NOT_TESTED', reason: 'Excluded by AXX_MAGIC_PEN_SKIP_RECORDING=1' };
    } else {
    const recordingRegion = { x: recordingMonitor.x + 640, y: recordingMonitor.y + 220, width: 640, height: 360 };
    assert(recordingRegion.x + recordingRegion.width <= recordingMonitor.x + recordingMonitor.width);
    assert(recordingRegion.y + recordingRegion.height <= recordingMonitor.y + recordingMonitor.height);
    const recording = await page.evaluate(region => Axx.backendRequest('POST', '/axx-api/screen/start', { region, fps: 15, quality: 'light', countdown: 0, maxMinutes: 1 }), recordingRegion);
    const waitRecording = async predicate => {
      const deadline = Date.now() + 30000;
      let status;
      do {
        status = await page.evaluate(() => Axx.backendRequest('GET', '/axx-api/screen/status'));
        assert.equal(status.id, recording.id);
        if (status.state === 'error') throw Error(status.error);
        if (predicate(status)) return status;
        await page.waitForTimeout(250);
      } while (Date.now() < deadline);
      throw Error('Recording did not reach its expected state: ' + JSON.stringify(status));
    };
    try {
      await waitRecording(s => s.state === 'running' && s.frames > 3);
    } finally { await page.evaluate(id => Axx.backendRequest('POST', '/axx-api/screen/control', { id, command: 'stop' }), recording.id); }
    receipt.recording = await waitRecording(s => s.state === 'finished');
    assert.equal(receipt.recording.verified, true);
    assert.deepEqual(receipt.recording.region, recordingRegion);
    receipt.checks.push('Packaged area recording on the explicitly selected physical monitor produced a verified decodable video');
    }
    receipt.result = 'PASS';
  } catch (error) { receipt.result = 'FAIL'; receipt.error = error.stack; throw error; }
  finally {
    const errors = [];
    try { await page.evaluate(() => Axx.magicPen.close()); } catch (e) { errors.push(e.message); }
    if (prior) {
      try { await page.evaluate(async p => {
        const settings = JSON.parse(p.preferences || '{}');
        Axx.magicPen.live = settings.live === true; Axx.magicPen.livePaused = false;
        for (const id of ['mp-color', 'mp-width', 'mp-tool', 'mp-directory']) if (settings[id]) document.getElementById(id).value = settings[id];
        document.getElementById('mp-question').value = p.question; Axx.magicPen.updateControls();
        if (p.preferences === null) localStorage.removeItem('axx.magicpen.prefs'); else localStorage.setItem('axx.magicpen.prefs', p.preferences);
        Axx.interfaceTheme.apply(p.theme); await Axx.companion.openFeature(p.view || 'chat');
      }, prior); } catch (e) { errors.push(e.message); }
    }
    try { await fixture?.close(); } catch (e) { errors.push(e.message); }
    if (errors.length) { receipt.cleanupErrors = errors; receipt.result = 'FAIL'; process.exitCode = 1; }
    receipt.completed = new Date().toISOString();
    fs.writeFileSync(path.join(out, 'installed-magic-pen.json'), JSON.stringify(receipt, null, 2));
    await browser.close();
  }
  console.log(receipt.result, receipt.checks.length, 'native Magic Pen checks');
})().catch(error => { console.error(error); process.exitCode = 1; });
