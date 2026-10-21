const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const runtime = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
const { chromium } = runtime('playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const server = http.createServer((req, res) => {
    const file = req.url.startsWith('/scripts/') ? path.join(__dirname, path.basename(req.url)) : path.join(root, 'Axx.html');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : 'text/html');
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM });
  const passed = [], failed = [], errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    page.setDefaultTimeout(3500);
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      localStorage.setItem('axx.experience.v1', JSON.stringify({ version: 1, consent: true }));
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1000, spaceRight: 920, spaceAbove: 500, spaceBelow: 540 };
        if (name === 'native_status') return { native: true, backendReady: false, shortcut: 'Alt+Shift+A', desktop };
        if (name === 'desktop_layout') return { ...desktop, ...args };
        return null;
      } }, event: { listen: async () => () => {} } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame);
    const check = async (name, fn) => {
      try { await fn(); passed.push(name); } catch (e) { failed.push({ name, error: e.message }); }
    };
    await check('Saved sound permission resumes audio on the next real interaction', async () => {
      await page.evaluate(() => Axx.flow.showQuick());
      await page.locator('#flow-all').click();
      await page.waitForFunction(() => Axx.companion.audio.ctx?.state === 'running');
      assert.ok(await page.evaluate(() => Axx.companion.audio.played.some(s => s.name === 'dock2')));
    });
    await check('Enable sounds recovers silent profile, zero volume and master mute', async () => {
      await page.evaluate(() => {
        Object.assign(Axx.companion.data.prefs, { sound: 'silent', volume: 0, mutedAll: true });
        Axx.companion.audio.configure(Axx.companion.data.prefs);
        Axx.flow.select('sound');
      });
      await page.locator('#sound-enable-settings').click();
      await page.waitForFunction(() => Axx.companion.audio.played.some(s => s.name === 'call'));
      assert.deepEqual(await page.evaluate(() => {
        const a = Axx.companion.audio;
        return [a.enabled, a.allMuted, a.profile, a.volume > 0];
      }), [true, false, 'discreet', true]);
    });
    await check('Audio resumes after suspension; disabling consent prevents restart and playback', async () => {
      await page.evaluate(async () => { await Axx.companion.audio.unlock(); await Axx.companion.audio.ctx.suspend(); });
      await page.locator('#sound-volume').click();
      await page.waitForFunction(() => Axx.companion.audio.ctx.state === 'running');
      await page.locator('#sound-off-settings').click();
      assert.equal(await page.evaluate(() => Axx.companion.audio.play('click', 'ui')), false);
    });
    await check('A real Web Audio graph carries the preview signal; capture and mute block effects', async () => {
      await page.locator('#sound-enable-settings').click();
      await page.waitForTimeout(450);
      const result = await page.evaluate(async () => {
        const audio = Axx.companion.audio, analyser = audio.ctx.createAnalyser();
        analyser.fftSize = 1024;
        audio.master.connect(analyser);
        const played = await audio.preview('success', 'notification');
        let peak = 0;
        for (let i = 0; i < 12; i++) {
          await new Promise(resolve => setTimeout(resolve, 15));
          const samples = new Float32Array(analyser.fftSize);
          analyser.getFloatTimeDomainData(samples);
          for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
        }
        audio.master.disconnect(analyser);
        audio.setContext(false, true);
        const duringCapture = audio.play('click', 'ui');
        audio.setContext(false, false);
        audio.muteAll(true);
        const whileMuted = audio.play('dock1', 'ui');
        audio.muteAll(false);
        return { played, peak, duringCapture, whileMuted };
      });
      assert.equal(result.played, true);
      assert.ok(result.peak > .001 && result.peak < 1, JSON.stringify(result));
      assert.equal(result.duringCapture, false);
      assert.equal(result.whileMuted, false);
      console.log('Measured Web Audio peak:', result.peak);
    });
    await check('Every synthesized cue produces non-clipped PCM with clean start/end and bounded DC', async () => {
      const stats = await page.evaluate(() => Object.keys(Axx.SIGNALS).map(name => {
        const pcm = Axx.synthesizeSignal(name, 48000);
        let peak = 0, power = 0, sum = 0, maxStep = 0;
        for (let i = 0; i < pcm.length; i++) { peak = Math.max(peak, Math.abs(pcm[i])); power += pcm[i] ** 2; sum += pcm[i]; if(i) maxStep = Math.max(maxStep, Math.abs(pcm[i]-pcm[i-1])); }
        return { name, peak, rms: Math.sqrt(power / pcm.length), dc: Math.abs(sum / pcm.length), maxStep, first: pcm[0], last: pcm[pcm.length-1] };
      }));
      for (const s of stats) { assert.ok(s.peak > .1 && s.peak < .9, JSON.stringify(s)); assert.ok(s.rms > .02 && s.dc < .01 && s.maxStep < .2, JSON.stringify(s)); assert.equal(s.first, 0); assert.equal(s.last, 0); }
      console.log('PCM cues checked:', stats.length);
    });
    console.log(JSON.stringify({ kind: 'WEB_AUDIO_RUNTIME_AND_PCM', passed, failed, errors }, null, 2));
    if (failed.length || errors.length) process.exitCode = 1;
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
