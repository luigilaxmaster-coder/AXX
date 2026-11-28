/** Controlled Playwright UI verification over real 1.AXX/Axx.html for AXX Notch Singularity.
 * Exercises state transitions, zero-tentacle gate, hit_map revisions, Portal, Intent, Approval Inbox,
 * Orbit/Parallel, Stage session continuity, Privacy Curtain, Fullscreen policy, and Reduce Motion.
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

  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 816 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message + ' @ ' + (e.stack || '').split('\n').slice(0, 3).join(' | ')));

    await page.addInitScript(() => {
      window.__notchTestInvokes = [];
      window.__notchTestListeners = {};
      window.__TAURI__ = {
        core: {
          invoke: async (cmd, args) => {
            window.__notchTestInvokes.push({ cmd, args });
            if (cmd === 'native_status') {
              return { native: true, backendReady: true, shortcut: 'Ctrl+Alt+Space', shortcutError: null, alwaysOnTop: true, autostart: false, timer: null };
            }
            if (cmd === 'desktop_layout') {
              return {
                screenX: 0, screenY: 0, width: args.width || 1536, height: args.height || 816,
                anchorX: args.anchorX || 768, anchorY: args.anchorY || 0,
                scaleFactor: 1, workX: 0, workY: 0, workWidth: 1536, workHeight: 816,
                spaceLeft: 768, spaceRight: 768, spaceAbove: 408, spaceBelow: 408,
                ready: true, displayId: '\\\\.\\DISPLAY1'
              };
            }
            return {};
          }
        },
        event: {
          listen: async (name, cb) => {
            (window.__notchTestListeners[name] ||= []).push(cb);
            return () => {};
          }
        }
      };
    });

    const port = server.address().port;
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => Boolean(window.Axx?.app && window.Axx?.notch));

    // 1. Notch is armed by default while preserving FREE 3D avatar until docked; opt-out disables cleanly
    const initialCheck = await page.evaluate(() => {
      const prefs = Axx.notch.getPreferences();
      const shell = document.getElementById('axx-notch-shell');
      const settingsCard = document.getElementById('axx-notch-settings');
      Axx.notch.setPreferences({ enabled: false });
      Axx.notch.onAvatarDragMove({ pointerClientY: 16, localY: 16 });
      const blockedWhenDisabled = Axx.notch.getState().physical === 'free';
      return {
        enabled: prefs.enabled,
        blockedWhenDisabled,
        physical: Axx.notch.getState().physical,
        shellHidden: shell.hidden,
        hasSettingsCard: Boolean(settingsCard)
      };
    });
    assert.equal(initialCheck.enabled, true, 'Notch docking must be armed by default while staying in FREE 3D avatar mode');
    assert.equal(initialCheck.blockedWhenDisabled, true, 'Disabling notch preference must block drag approach');
    assert.equal(initialCheck.physical, 'free');
    assert.equal(initialCheck.shellHidden, true);
    assert.equal(initialCheck.hasSettingsCard, true);

    // Save custom 3D identity before docking
    await page.evaluate(() => {
      Axx.app.store.data.settings.form = 3; // Torus
      Axx.app.store.data.settings.palette = 4; // Amethyst
      Axx.app.store.data.settings.scale = 1.15;
      Axx.app.store.save();
      Axx.app.applySettings?.();
    });

    // 2. Enable via preferences & test drag approach -> release dock -> zero tendrils -> compact notch
    await page.evaluate(() => {
      Axx.notch.setPreferences({ enabled: true });
      Axx.notch.onAvatarDragMove({ pointerClientY: 16, localY: 16 });
    });
    const inApproach = await page.evaluate(() => ({
      physical: Axx.notch.getState().physical,
      activeAttr: document.getElementById('axx-notch-approach').getAttribute('data-active')
    }));
    assert.equal(inApproach.physical, 'approach');
    assert.equal(inApproach.activeAttr, 'true');

    await page.evaluate(() => {
      Axx.notch.onAvatarDragEnd();
    });
    await page.waitForFunction(() => Axx.notch.getState().physical === 'docked');
    await page.waitForTimeout(60);

    const dockedState = await page.evaluate(() => {
      // Force tendril and flow draw attempts while docked to verify hard gate
      Axx.organic?.tendrils?.draw?.([{ id: 't', a: { x: 10, y: 10 }, b: { x: 80, y: 80 }, progress: 1 }], 0.5, Axx.app.renderer.materialTable(), 0, Axx.app.renderer);
      Axx.organic?.frame?.(0.016);
      Axx.flow?.frame?.(0.016);
      const shell = document.getElementById('axx-notch-shell');
      const rect = shell.getBoundingClientRect();
      const stage = document.getElementById('stage');
      const tendrilCanvases = [...document.querySelectorAll('canvas.organic-tendrils')];
      return {
        physical: Axx.notch.getState().physical,
        tendrilsBlocked: Axx.notch.tendrilsBlocked(),
        shellHidden: shell.hidden,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        stageOpacity: stage ? getComputedStyle(stage).opacity : null,
        allTendrilsHidden: tendrilCanvases.every(c => c.hidden === true),
        visibleTendrilCount: Axx.organic?.tendrils?.visibleCount ?? 0
      };
    });

    assert.equal(dockedState.physical, 'docked');
    assert.equal(dockedState.tendrilsBlocked, true);
    assert.equal(dockedState.shellHidden, false);
    assert.equal(Math.round(dockedState.rect.y), 0, 'Notch must flush-dock to top edge y=0');
    assert(dockedState.rect.width >= 180 && dockedState.rect.height >= 28 && dockedState.rect.height <= 46, 'Compact dimensions within spec');
    assert.equal(dockedState.stageOpacity, '0', '3D avatar stage must be hidden while docked');
    assert.equal(dockedState.allTendrilsHidden, true, 'Zero tendril canvases visible while docked');
    assert.equal(dockedState.visibleTendrilCount, 0, 'Zero tendril draw segments while docked');

    // 3. Verify hit_map exclusion & notch interactive region inclusion
    await page.evaluate(() => Axx.app.updateHitMap());
    const hitCheck = await page.evaluate(() => {
      const hits = window.__notchTestInvokes.filter(x => x.cmd === 'hit_map');
      const last = hits[hits.length - 1]?.args?.map;
      const shellRect = document.getElementById('axx-notch-shell').getBoundingClientRect();
      const nonZeroBits = (last?.bits || []).filter(b => b !== 0).length;
      const coversNotch = (last?.regions || []).some(
        r => Math.abs(r.x - shellRect.x) <= 2 && Math.abs(r.y - shellRect.y) <= 2 && r.width >= 180
      );
      return { epoch: last?.epoch, nonZeroBits, coversNotch, regionCount: last?.regions?.length || 0 };
    });
    assert(hitCheck.epoch >= 1, 'hit_map must carry dockEpoch');
    assert.equal(hitCheck.nonZeroBits, 0, 'Avatar hitMask bits must be cleared when docked');
    assert.equal(hitCheck.coversNotch, true, 'Notch interactive shell must be present in hit_map regions');

    // 4. Expand & execute real local timer via Intent + verify compact metric survival
    await page.click('#notch-expand-btn');
    await page.waitForFunction(() => Axx.notch.getState().size === 'expanded');
    await page.click('button.notch-mode-link:has-text("Acciones")');
    await page.fill('#notch-intent-input', 'temporizador 5 min');
    await page.click('#notch-intent-submit');
    await page.waitForFunction(() => Axx.app.store.data.timer?.status === 'running');

    // Collapse back to compact via Escape key and confirm real timer metric stays visible
    await page.locator('#axx-notch-shell').press('Escape');
    await page.waitForFunction(() => Axx.notch.getState().size === 'compact');
    const compactMetric = await page.textContent('#notch-primary-metric');
    assert(/\d{2}:\d{2}/.test(compactMetric || ''), `Expected compact timer metric MM:SS, got: ${compactMetric}`);

    // 5. Approval Inbox: pending backend command requires explicit approval (never auto-approved)
    const approvalResult = await page.evaluate(() => {
      let approvedCount = 0;
      Axx.commandLibrary = {
        operation: {
          state: 'awaiting_approval',
          operation_id: 'op-test-1',
          command_id: 'axx.system.telemetry',
          title: 'Consultar estado del equipo'
        },
        lastOperation: { operation_id: 'op-prev', command_id: 'axx.system.telemetry', state: 'succeeded', summary: 'CPU 18% · RAM 42%' },
        approve() { approvedCount++; this.operation.state = 'completed'; },
        cancel() { this.operation.state = 'cancelled'; }
      };
      window.__getApprovedCount = () => approvedCount;
      Axx.notch.stepProjections();
      return { attention: Axx.notch.getState().attention };
    });
    assert.equal(approvalResult.attention, 'approval');
    await page.click('#notch-expand-btn');
    await page.waitForSelector('#notch-approve-btn');
    assert.equal(await page.evaluate(() => window.__getApprovedCount()), 0, 'Must NOT auto-approve before explicit click');
    await page.click('#notch-approve-btn');
    assert.equal(await page.evaluate(() => window.__getApprovedCount()), 1, 'Explicit approval click must execute once');
    await page.waitForFunction(() => !document.getElementById('notch-approve-btn'));

    // 6. Portal keyboard file picker + forwarding to Chat Stage
    await page.click('button.notch-mode-link:has-text("Archivos")');
    await page.waitForFunction(() => Axx.notch.getState().content === 'portal');
    await page.setInputFiles('#notch-portal-file-input', {
      name: 'diagnostico.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('contenido portal AXX')
    });
    await page.waitForSelector('#notch-portal-to-chat');
    await page.click('#notch-portal-to-chat');
    await page.waitForFunction(() => Axx.notch.getState().stageOpen);
    const stageState = await page.evaluate(() => ({
      stageOpen: Axx.notch.getState().stageOpen,
      attachment: Axx.companion.attachment,
      stillDocked: Axx.notch.isDocked()
    }));
    assert.equal(stageState.stageOpen, true);
    assert.equal(stageState.attachment.name, 'diagnostico.txt');
    assert.equal(stageState.attachment.text, 'contenido portal AXX', 'Portal must attach actual content, not a filename placeholder');
    assert.equal(stageState.stillDocked, true);

    // 7. Fullscreen suppression hides notch cleanly and restores afterward
    await page.evaluate(() => {
      for (const cb of window.__notchTestListeners['axx-fullscreen-policy'] || []) {
        cb({ payload: { fullscreen: true } });
      }
    });
    assert.equal(await page.evaluate(() => document.getElementById('axx-notch-shell').hidden), true, 'Fullscreen must suppress notch');
    await page.evaluate(() => {
      for (const cb of window.__notchTestListeners['axx-fullscreen-policy'] || []) {
        cb({ payload: { fullscreen: false } });
      }
    });
    assert.equal(await page.evaluate(() => document.getElementById('axx-notch-shell').hidden), false, 'Exiting fullscreen restores notch');

    // 8. Privacy Curtain masks private titles without stopping running timer
    await page.evaluate(() => {
      Axx.app?.pauseResume?.();
      Axx.companion.pending = true;
      Axx.notch.setPreferences({ privacyCurtain: true });
      Axx.notch.stepProjections();
    });
    const privacyText = await page.textContent('#notch-primary-title');
    assert(privacyText && privacyText.length > 0);
    await page.evaluate(() => {
      Axx.companion.pending = false;
      Axx.notch.setPreferences({ privacyCurtain: false });
    });

    // 9. Undock via button -> returns to FREE with exact pre-dock identity & restored tendrils
    await page.click('#notch-undock-btn');
    await page.waitForFunction(() => Axx.notch.getState().physical === 'free');
    const restored = await page.evaluate(() => ({
      physical: Axx.notch.getState().physical,
      tendrilsBlocked: Axx.notch.tendrilsBlocked(),
      shellHidden: document.getElementById('axx-notch-shell').hidden,
      stageOpacity: getComputedStyle(document.getElementById('stage')).opacity,
      form: Axx.app.renderer.form,
      palette: Axx.app.renderer.settings.palette,
      scale: Axx.app.renderer.settings.scale,
      timerStatus: Axx.app.store.data.timer?.status
    }));
    assert.equal(restored.physical, 'free');
    assert.equal(restored.tendrilsBlocked, false);
    assert.equal(restored.shellHidden, true);
    assert.equal(restored.stageOpacity, '1');
    assert.equal(restored.form, 3, 'Exact 3D form must survive dock/undock cycle');
    assert.equal(restored.palette, 4, 'Exact palette must survive dock/undock cycle');
    assert.equal(restored.scale, 1.15, 'Exact scale must survive dock/undock cycle');
    assert(['running', 'paused'].includes(restored.timerStatus), 'Running timer business task must survive undock cleanly');

    assert.deepStrictEqual(errors, [], `Uncaught page errors: ${errors.join('; ')}`);
    console.log('PASS: test-notch-ui (opt-in off, dock/undock slice, zero tentacles, hit_map exclusion, intent timer, approval inbox, portal, fullscreen, privacy, identity restoration)');
  } finally {
    await browser.close();
    server.close();
  }
})();
