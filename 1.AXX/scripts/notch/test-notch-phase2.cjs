/** Phase II Comprehensive Adversarial, Adaptive Composition, Performance, Failure Injection & Visual Evidence Suite
 * Generates real PNG screenshots under build/notch-evidence/screenshots/ for visual inspection.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createRequire } = require('node:module');

const bundledRequire = createRequire(
  path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json')
);
const { chromium } = bundledRequire('playwright');

const html = fs.readFileSync(path.join(__dirname, '../../Axx.html'), 'utf8');
const SCREENSHOT_DIR = path.join(__dirname, '../../../build/notch-evidence/screenshots');
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

function resolveAsset(reqUrl) {
  const cleanUrl = reqUrl.split('?')[0];
  if (cleanUrl.startsWith('/scripts/') && /\.(js|css)$/.test(cleanUrl)) {
    const file = require('../test-static-assets.cjs').scriptPath(cleanUrl);
    if (fs.existsSync(file)) return file;
  }
  return null;
}

(async () => {
  const server = http.createServer((req, res) => {
    const file = resolveAsset(req.url || '');
    if (file) {
      res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : 'application/javascript' });
      res.end(fs.readFileSync(file));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(html);
  });

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      process.env.AXX_TEST_CHROMIUM ||
      path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')
  });

  const port = server.address().port;

  async function openTestPage({ deviceScaleFactor = 1, colorScheme = 'dark', forcedColors = 'none', reducedMotion = 'no-preference', seedStorage = null } = {}) {
    const context = await browser.newContext({
      viewport: { width: 1536, height: 816 },
      deviceScaleFactor,
      colorScheme,
      forcedColors,
      reducedMotion
    });
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript((seed) => {
      if (seed) {
        for (const [k, v] of Object.entries(seed)) localStorage.setItem(k, v);
      }
      window.__notchTestInvokes = [];
      window.__TAURI__ = {
        core: {
          invoke: async (cmd, args) => {
            window.__notchTestInvokes.push({ cmd, args });
            if (cmd === 'native_status') {
              return { native: true, backendReady: true, shortcut: 'Ctrl+Alt+Space', shortcutError: null, alwaysOnTop: true, autostart: false, timer: null };
            }
            if (cmd === 'notch_monitors') {
              return [
                { id: '\\\\.\\DISPLAY1', primary: true, scaleFactor: 1.25, workX: 0, workY: 0, workWidth: 1536, workHeight: 816 },
                { id: '\\\\.\\DISPLAY2', primary: false, scaleFactor: 1.0, workX: 1920, workY: 0, workWidth: 1920, workHeight: 1032 }
              ];
            }
            if (cmd === 'desktop_layout') {
              return {
                screenX: 0, screenY: 0, width: args.width || 1536, height: args.height || 816,
                anchorX: args.anchorX || 768, anchorY: args.anchorY || 0,
                scaleFactor: 1, workX: 0, workY: 0, workWidth: 1536, workHeight: 816,
                dockEpoch: args.dockEpoch, geometryRevision: args.geometryRevision,
                displayId: args.displayId || '\\\\.\\DISPLAY1', ready: true
              };
            }
            if (cmd === 'hit_map') {
              return { accepted: true, epoch: args.map?.epoch || 0, revision: args.map?.revision || 0 };
            }
            return {};
          }
        },
        event: { listen: async () => () => {} }
      };
    }, seedStorage);
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.Axx?.app && window.Axx?.notch));
    return { context, page, errors };
  }

  try {
    // ── RUN 1: Full Visual Lab, Compositions, Stage Continuum, Renderer Suspend & Performance ──
    const { context, page, errors } = await openTestPage({ deviceScaleFactor: 1 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-free-avatar.png') });

    // Enable notch & inspect Approach Magnetic Preview
    await page.evaluate(() => {
      Axx.notch.setPreferences({ enabled: true, hoverPeek: true });
      Axx.notch.onAvatarDragMove({ pointerClientX: 768, pointerClientY: 16, localX: 768, localY: 16 });
    });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-approach-preview.png') });

    // Commit dock & verify renderer suspension + zero tendrils
    await page.evaluate(() => Axx.notch.onAvatarDragEnd());
    await page.waitForFunction(() => Axx.notch.getState().physical === 'docked');
    await page.waitForTimeout(100);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-compact-idle.png') });

    const suspendStats = await page.evaluate(() => ({
      hidden: Axx.app.renderer.hidden,
      perf: Axx.notch.getPerformanceMetrics(),
      tendrilsBlocked: Axx.notch.tendrilsBlocked()
    }));
    assert.equal(suspendStats.hidden, true, '3D CPU renderer must suspend when docked');
    assert.equal(suspendStats.tendrilsBlocked, true);

    // Compact with active Timer
    await page.evaluate(() => { Axx.notch.submitIntent('temporizador 5 min'); });
    await page.waitForFunction(() => Axx.app.store.data.timer?.status === 'running');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-compact-timer.png') });

    // Media Panoramic Composition (real peak + sessions + timeline)
    await page.evaluate(() => {
      Axx.media16.source = 'system';
      Axx.nativeMusic = {
        snapshot: {
          available: true,
          audioAvailable: true,
          peak: 0.72,
          updatedAt: Date.now(),
          sessions: [
            { id: 'sp-1', title: 'Midnight Synthwave', subtitle: 'AXX Radio', app: 'Spotify.exe', playing: true, canPlay: true, canPause: true, canNext: true, canPrevious: true, canSeek: true, time: 65, duration: 210 },
            { id: 'ed-2', title: 'Technical Talk', subtitle: 'Browser', app: 'msedge.exe', playing: false, canPlay: true, canPause: false, canNext: false, canPrevious: false, canSeek: false, time: 0, duration: 0 }
          ]
        },
        selectedId: '',
        target() { return this.snapshot.sessions[0]; },
        toggle() {}, command() {}, paint() {}
      };
      Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'media', size: 'expanded', activate: true });
      Axx.notch.stepProjections();
    });
    await page.waitForSelector('#notch-media-panoramic');
    await page.waitForTimeout(180);
    const mediaDims = await page.evaluate(() => document.getElementById('axx-notch-shell').getBoundingClientRect());
    assert(mediaDims.width >= 480 && mediaDims.height <= 352, `Media Panoramic must be wide & compact vertically, got ${mediaDims.width}x${mediaDims.height}`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-media-panoramic.png') });

    // Intent 2.0 Launcher Palette
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'intent', size: 'expanded', activate: true }));
    await page.waitForSelector('#notch-intent-input');
    await page.fill('#notch-intent-input', 'sistema');
    await page.waitForTimeout(160);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-intent-palette.png') });

    // Agent Observatory + DevPulse
    await page.evaluate(() => {
      Axx.evolution3?.controllers?.agentTimeline?.ingestEvent({
        conversation_id: 'conv-agent-1', seq: 1, agent_name: 'Architect Agent', tool: 'fs.audit', status: 'completed'
      });
      Axx.evolution3?.controllers?.agentTimeline?.ingestEvent({
        conversation_id: 'conv-agent-1', seq: 2, agent_name: 'Architect Agent', tool: 'cargo.test', status: 'running'
      });
      Axx.evolution3?.controllers?.workApprovals?.registerApprovalRequest({
        operation_id: 'wa-99', conversation_id: 'conv-agent-1', title: 'Aplicar patch en resident.rs', reason: 'Permiso explícito'
      });
      Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'agents', size: 'expanded', activate: true });
      Axx.notch.stepProjections();
    });
    await page.waitForSelector('.notch-agent-timeline');
    await page.waitForTimeout(180);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-agent-observatory.png') });

    // Portal 2.0 Smart Shelf + individual removal
    await page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'portal', size: 'expanded', activate: true }));
    await page.setInputFiles('#notch-portal-file-input', [
      { name: 'mockup.png', mimeType: 'image/png', buffer: Buffer.from('PNG_DATA') },
      { name: 'notas.txt', mimeType: 'text/plain', buffer: Buffer.from('TEXT_DATA') }
    ]);
    await page.waitForSelector('#notch-portal-to-converter');
    await page.waitForTimeout(160);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08-portal-shelf.png') });

    // Keep unsupported/multiple files in the shelf; prepare the text document explicitly.
    await page.locator('.notch-shelf-item').filter({ hasText: 'mockup.png' }).getByRole('button', { name: 'Quitar' }).click();

    // Stage 2.0 Continuum (Detach & Reattach preserving draft)
    await page.click('#notch-portal-to-chat');
    await page.waitForSelector('#notch-stage-bar');
    await page.click('#notch-stage-detach-btn');
    assert.equal(await page.evaluate(() => Axx.notch.getState().stageDetached), true, 'Stage must support explicit detach');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09-stage-continuum.png') });

    // Edit identity explicitly while Docked -> verify preserved (NOT overwritten by old snapshot) on undock!
    await page.evaluate(() => {
      Axx.app.store.data.settings.form = 7; // Fold
      Axx.app.store.data.settings.palette = 2; // Ocean
      Axx.app.applySettings();
    });
    assert(await page.evaluate(() => Axx.notch.getState().explicitIdentityEditRevision >= 1));

    // Undock & verify exact restoration of edited identity + renderer un-suspended
    await page.click('#notch-stage-return-btn');
    await page.click('#notch-undock-btn');
    await page.waitForFunction(() => Axx.notch.getState().physical === 'free');
    await page.waitForTimeout(80);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '11-undocked-restored.png') });

    const finalFree = await page.evaluate(() => ({
      hidden: Axx.app.renderer.hidden,
      form: Axx.app.store.data.settings.form,
      palette: Axx.app.store.data.settings.palette,
      timerStatus: Axx.app.store.data.timer?.status
    }));
    assert.equal(finalFree.hidden, false, 'Renderer must resume when back to FREE');
    assert.equal(finalFree.form, 7, 'Deliberate identity edit while docked must survive undock');
    assert.equal(finalFree.palette, 2);
    assert.equal(finalFree.timerStatus, 'running');

    // Performance Stress (50 real DOM + Coordinator dock/undock cycles in Playwright + 500 reducer cycles)
    const stressStart = Date.now();
    const memBefore = await page.evaluate(() => (performance.memory ? performance.memory.usedJSHeapSize : 0));
    await page.evaluate(() => {
      for (let i = 0; i < 50; i++) {
        Axx.notch.dockNow();
        Axx.notch.undockNow();
      }
    });
    const stressMs = Date.now() - stressStart;
    const cycles500 = await page.evaluate(() => {
      const t0 = performance.now();
      let st = Axx.notchState.createInitialState({ enabled: true });
      const snap = { schemaVersion: 1, identityRevision: 0, identity: { settings: { form: 0, palette: 0 }, studio: {}, camera: [0, 0], finish: 'obsidian' }, freePosition: { displayId: 'primary', size: 280 } };
      for (let i = 0; i < 500; i++) {
        let r = Axx.notchState.reduce(st, { type: 'DOCK_COMMAND', snapshot: snap });
        r = Axx.notchState.reduce(r.next, { type: 'RETRACT_COMPLETE', epoch: r.next.dockEpoch, tentacleLinks: 0 });
        r = Axx.notchState.reduce(r.next, { type: 'NATIVE_GEOMETRY_ACK', epoch: r.next.dockEpoch, revision: r.next.geometryRevision });
        r = Axx.notchState.reduce(r.next, { type: 'UNDOCK_REQUEST' });
        r = Axx.notchState.reduce(r.next, { type: 'UNDOCK_COMPLETE', epoch: r.next.dockEpoch, avatarValid: true });
        st = r.next;
      }
      return {
        cyclesMs: Number((performance.now() - t0).toFixed(3)),
        finalPhysical: st.physical,
        finalEpoch: st.dockEpoch,
        usedHeap: performance.memory ? performance.memory.usedJSHeapSize : 0
      };
    });
    assert.equal(cycles500.finalPhysical, 'free');
    assert.equal(cycles500.finalEpoch, 1000);
    const heapDeltaKb = memBefore && cycles500.usedHeap ? Math.round((cycles500.usedHeap - memBefore) / 1024) : null;
    const perfReport = await page.evaluate(() => Axx.notch.getPerformanceMetrics());
    assert.equal(perfReport.droppedAcks, 0);

    assert.deepStrictEqual(errors, [], `Uncaught errors in Run 1: ${errors.join('; ')}`);
    await context.close();

    // ── RUN 2: High Contrast / Forced Colors + Reduced Motion + Corrupt Prefs Recovery + 150% Scale ──
    const run2 = await openTestPage({
      deviceScaleFactor: 1.5,
      forcedColors: 'active',
      reducedMotion: 'reduce',
      seedStorage: {
        'axx.notch.v1': '{broken_json',
        'axx.notch.snapshot.v1': JSON.stringify({ schemaVersion: 1, identityRevision: 1, identity: { settings: { form: 11, palette: 0, scale: 1 }, studio: {}, camera: [-0.18, 0.08], finish: 'obsidian' }, freePosition: { displayId: 'primary', screenX: 0, screenY: 0, anchorX: 152, anchorY: 152, size: 280 } })
      }
    });
    const run2State = await run2.page.evaluate(() => {
      // Corrupt prefs fallback: notch stays disabled & crashed snapshot restored cleanly to FREE
      const st = Axx.notch.getState();
      const snapshotCleaned = localStorage.getItem('axx.notch.snapshot.v1') === null;
      Axx.notch.setPreferences({ enabled: true, privacyCurtain: true });
      Axx.notch.dockNow();
      return { initPhysical: st.physical, snapshotCleaned };
    });
    assert.equal(run2State.initPhysical, 'free');
    assert.equal(run2State.snapshotCleaned, true);
    await run2.page.waitForFunction(() => Axx.notch.getState().physical === 'docked');
    await run2.page.evaluate(() => Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content: 'resources', size: 'expanded', activate: true }));
    await run2.page.waitForTimeout(80);
    await run2.page.screenshot({ path: path.join(SCREENSHOT_DIR, '10-privacy-highcontrast.png') });
    assert.deepStrictEqual(run2.errors, [], `Uncaught errors in Run 2: ${run2.errors.join('; ')}`);
    await run2.context.close();

    // ── RUN 3: Failure Injection Suite (Safe Offline Queue, Stale hit_map, Unplug Monitor, Hide/Hotkey Recovery) ──
    const run3 = await openTestPage({ deviceScaleFactor: 1 });
    const failureRes = await run3.page.evaluate(async () => {
      Axx.notch.setPreferences({ enabled: true, preferredMonitor: '\\\\.\\DISPLAY2' });
      Axx.notch.dockNow();
      await new Promise(r => setTimeout(r, 110));
      // 1) Simulate backend disconnect -> Safe Offline Queue (no auto-replay)
      Axx.desktop.ready = false;
      Axx.isNative = () => true;
      Axx.companion.brain = { connected: false };
      Axx.notch.submitIntent('auditar estado de seguridad sin conexion');
      const queuedAfterOffline = Axx.notch.getOfflineQueue().length;
      Axx.notch.stepProjections();
      const queuedAfterProjectionTick = Axx.notch.getOfflineQueue().length;

      // 2) Re-enable & switch back via DISPLAY_CHANGED unplug fallback
      Axx.notch.dispatch({ type: 'DISPLAY_CHANGED', displayId: '\\\\.\\DISPLAY1' });
      const displayAfterFallback = Axx.notch.getState().displayId;

      // 3) Stale hit_map epoch rejection tracking
      const origInvoke = window.__TAURI__.core.invoke;
      window.__TAURI__.core.invoke = async (cmd, args) => {
        if (cmd === 'hit_map') return { accepted: false, epoch: 0, revision: 0 };
        return origInvoke(cmd, args);
      };
      Axx.app.lastHitSignature = '';
      await Axx.app.updateHitMap?.();
      const droppedAfterStale = Axx.notch.getPerformanceMetrics().droppedAcks;
      window.__TAURI__.core.invoke = origInvoke;

      // 4) Hide notch -> verify invisible -> recover via Alt+Shift+N hotkey
      Axx.notch.dispatch({ type: 'SET_VISIBILITY', visibility: 'userHidden' });
      const hiddenVisible = Axx.notch.isVisible();
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'N', altKey: true, shiftKey: true, bubbles: true }));
      const recoveredVisible = Axx.notch.isVisible();

      // 5) Idle Auto-Fade + Mouse Hover Wake + Shape/Swatch/Alignment Customization + Zero Desktop Scroll
      Axx.notch.setPreferences({
        idleFadeEnabled: true,
        idleFadeSeconds: 3,
        idleFadeOpacity: 'ghost',
        surfaceShape: 'island',
        borderStyle: 'glow',
        horizontalAlign: 'right',
        accent: 'emerald',
        compactMetrics: 'clock'
      });
      Axx.notch.dispatch({ type: 'SET_SURFACE_SIZE', size: 'compact', interaction: 'none' });
      const faded = Axx.notch.triggerIdleFadeNow();
      const fadedAttr = document.getElementById('axx-notch-shell').getAttribute('data-idle-faded');
      document.getElementById('axx-notch-shell').dispatchEvent(new Event('pointerenter'));
      const wokeAfterHover = !Axx.notch.isIdleFaded();

      // Reset to center + check zero desktop scroll across expanded views (after spring settles)
      Axx.notch.setPreferences({ surfaceShape: 'notch', horizontalAlign: 'center', compactMetrics: 'auto' });
      const scrollOverflows = [];
      for (const content of ['orbit', 'intent', 'portal', 'media', 'agents', 'voice', 'resources', 'recall']) {
        Axx.notch.dispatch({ type: 'SET_CONTENT_MODE', content, size: 'expanded', activate: true });
        await new Promise(r => setTimeout(r, 420));
        const bodyEl = document.getElementById('notch-body');
        if (bodyEl && bodyEl.scrollHeight > bodyEl.clientHeight + 2) {
          scrollOverflows.push(`${content}:${bodyEl.scrollHeight}>${bodyEl.clientHeight}`);
        }
      }
      document.getElementById('notch-customize-btn')?.click();
      await new Promise(r => setTimeout(r, 600));
      const sheet = document.getElementById('notch-appearance-sheet');
      const shell = document.getElementById('axx-notch-shell');
      const studioTabs = [];
      for (const tabBtn of [...document.querySelectorAll('.notch-sheet-tab')]) {
        tabBtn.click();
        await new Promise(r => setTimeout(r, 100));
        studioTabs.push({
          tab: tabBtn.dataset.tab,
          sh: sheet.scrollHeight,
          ch: sheet.clientHeight,
          overflow: sheet.scrollHeight > sheet.clientHeight + 2
        });
      }
      const sheetInfo = sheet ? {
        sh: Math.max(...studioTabs.map(t => t.sh)),
        ch: sheet.clientHeight,
        shellH: shell?.clientHeight,
        overflow: studioTabs.some(t => t.overflow),
        tabs: studioTabs
      } : null;

      // Test new customization capabilities: custom HEX accent, surfaceTheme, customPreset save/apply, JSON export/import
      Axx.notch.setPreferences({
        surfaceTheme: 'amethyst',
        material: 'frosted',
        borderStyle: 'prism',
        surfaceShape: 'bevel',
        accent: 'custom',
        customAccentHex: '#ff77aa',
        surfaceOpacity: 88,
        topOffsetPx: 10,
        fontPreset: 'mono',
        soundProfile: 'synth',
        compactMetrics: 'clock-date'
      });
      const customSaved = Axx.notch.saveCustomPreset();
      const exportedJson = Axx.notch.exportPreferencesJSON();
      Axx.notch.setPreferences({ surfaceTheme: 'obsidian', surfaceShape: 'notch', accent: 'avatar' });
      const appliedCustom = Axx.notch.applyCustomPreset();
      const restoredTheme = Axx.notch.getPreferences().surfaceTheme;
      const restoredHex = Axx.notch.getPreferences().customAccentHex;
      const importRes = Axx.notch.importPreferencesJSON(exportedJson);
      Axx.notch.setPreferences({ surfaceTheme: 'obsidian', surfaceShape: 'notch', accent: 'avatar', material: 'solid', borderStyle: 'subtle', topOffsetPx: 0, surfaceOpacity: 96, fontPreset: 'system', compactMetrics: 'auto' });

      return {
        queuedAfterOffline,
        queuedAfterProjectionTick,
        displayAfterFallback,
        droppedAfterStale,
        hiddenVisible,
        recoveredVisible,
        faded,
        fadedAttr,
        wokeAfterHover,
        scrollOverflows,
        sheetInfo,
        customCustomization: {
          saved: Boolean(customSaved),
          appliedCustom,
          restoredTheme,
          restoredHex,
          importedOk: Boolean(importRes?.ok)
        }
      };
    });
    assert.equal(failureRes.queuedAfterOffline, 1, 'Offline intent must enter Safe Offline Queue');
    assert.equal(failureRes.queuedAfterProjectionTick, 1, 'Safe Offline Queue must never auto-replay silently');
    assert.equal(failureRes.displayAfterFallback, '\\\\.\\DISPLAY1', 'Monitor fallback must update active displayId');
    assert(failureRes.droppedAfterStale >= 1, 'Rejected hit_map ack must be counted in droppedAcks');
    assert.equal(failureRes.hiddenVisible, false, 'userHidden must hide notch');
    assert.equal(failureRes.recoveredVisible, true, 'Alt+Shift+N must restore presentation cleanly');
    assert.equal(failureRes.faded, true, 'Auto-fade must activate when idle');
    assert.equal(failureRes.fadedAttr, 'true');
    assert.equal(failureRes.wokeAfterHover, true, 'Pointer hover must wake faded notch immediately');
    assert.deepStrictEqual(failureRes.scrollOverflows, [], `Desktop expanded views must not require vertical scroll: ${failureRes.scrollOverflows.join(', ')}`);
    assert.equal(failureRes.sheetInfo?.overflow, false, `Appearance settings sheet must fit without vertical scroll across all 4 tabs: ${JSON.stringify(failureRes.sheetInfo)}`);
    assert.equal(failureRes.customCustomization?.saved, true);
    assert.equal(failureRes.customCustomization?.appliedCustom, true);
    assert.equal(failureRes.customCustomization?.restoredTheme, 'amethyst');
    assert.equal(failureRes.customCustomization?.restoredHex, '#ff77aa');
    assert.equal(failureRes.customCustomization?.importedOk, true);
    assert.deepStrictEqual(run3.errors, [], `Uncaught errors in Run 3: ${run3.errors.join('; ')}`);
    await run3.context.close();

    console.log(JSON.stringify({
      status: 'PASS',
      screenshotsCaptured: 11,
      stress50CyclesMs: stressMs,
      cycles500Ms: cycles500.cyclesMs,
      heapDeltaKb,
      avgLayoutMs: Number(perfReport.avgLayoutMs.toFixed(3)),
      avgRenderMs: Number(perfReport.avgRenderMs.toFixed(3)),
      droppedAcks: perfReport.droppedAcks,
      failureInjection: failureRes
    }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
})();
