"""Milestone 5 E2E Verification: Screen Recorder (verified file on disk), Timer & Music."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.inference.adapter import InferenceAdapter
from backend.inference.router import parse_strict_json
from backend.memory.procedural_memory import ProceduralMemory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer, resolve_app_paths
from backend.speech.offline_asr import OfflineTranscriptionService
from backend.speech.windows_tts import WindowsSpeechService
from backend.sync.identity_sync import IdentityStore


class Milestone5MediaTimerRecorderE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='axx_m5_e2e_')
        cls.state_dir = Path(cls.tmp.name)
        config_path, state_path = resolve_app_paths('providers.json', 'state.db', data_dir=cls.state_dir)
        config = parse_strict_json(Path(config_path).read_bytes())

        cls.adapter = InferenceAdapter(config, state_path=state_path)
        cls.executor = ActionExecutor(db_path=state_path, workspace_root=cls.state_dir / 'artifacts')
        cls.commands = CommandService(cls.executor)
        cls.memory = ProceduralMemory(db_path=state_path, ai_memory=None)
        cls.identity = IdentityStore(db_path=state_path)
        cls.speech = WindowsSpeechService(cls.state_dir)
        cls.transcription = OfflineTranscriptionService(cls.state_dir)

        handler = type('M5Handler', (AxxBridgeHandler,), {
            'adapter': cls.adapter,
            'executor': cls.executor,
            'commands': cls.commands,
            'memory': cls.memory,
            'identity': cls.identity,
            'speech': cls.speech,
            'transcription': cls.transcription,
            'config_path': Path(config_path),
            'connect': None,
            'provider': None,
        })
        cls.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for svc in (cls.commands, cls.adapter, cls.executor, cls.memory, cls.identity, cls.speech, cls.transcription):
            try:
                svc.close()
            except Exception:
                pass
        cls.tmp.cleanup()

    def request_api(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode('utf-8')
        headers = {'Authorization': f'Bearer {self.server.host_token}'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.server.server_port}{path}',
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.status, json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode('utf-8'))

    def test_1_screen_save_endpoint_verifies_disk_existence_and_sha256(self):
        fake_webm = b'\x1a\x45\xdf\xa3' + b'AXX_WEBM_TEST_PAYLOAD' * 64
        expected_sha = hashlib.sha256(fake_webm).hexdigest()
        status, res = self.request_api('POST', '/axx-api/screen/save', {
            'filename': '../../intento-escape/Mi Grabacion.webm',
            'video_base64': base64.b64encode(fake_webm).decode('ascii'),
            'mime': 'video/webm',
            'markers': [{'atMs': 420, 'label': 'Momento 1'}],
        })
        self.assertEqual(status, 200, f'Expected 200, got {status}: {res}')
        self.assertTrue(res.get('ok'))
        self.assertTrue(res.get('saved'))
        self.assertTrue(res.get('verified'))
        self.assertEqual(res.get('bytes'), len(fake_webm))
        self.assertEqual(res.get('sha256'), expected_sha)

        saved_path = Path(res['path'])
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.parent, (self.executor.workspace_root / 'recordings').resolve())
        self.assertEqual(saved_path.read_bytes(), fake_webm)

        markers_path = Path(res['markers_path'])
        self.assertTrue(markers_path.exists())
        markers_data = json.loads(markers_path.read_text(encoding='utf-8'))
        self.assertEqual(len(markers_data['markers']), 1)

    def test_2_frontend_screen_recorder_timer_and_music_e2e(self):
        node_script = r"""
        const fs = require('node:fs');
        const path = require('node:path');
        const http = require('node:http');
        const assert = require('node:assert/strict');
        const { createRequire } = require('node:module');
        const bundledRequire = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'));
        const { chromium } = bundledRequire('playwright');

        const apiPort = Number(process.env.AXX_LIVE_PORT);
        const apiToken = process.env.AXX_LIVE_TOKEN;
        const root = path.resolve('1.AXX');

        (async () => {
          const server = http.createServer((req, res) => {
            if (req.url.startsWith('/proxy-api/')) {
              const targetPath = req.url.slice('/proxy-api'.length);
              const chunks = [];
              req.on('data', c => chunks.push(c));
              req.on('end', () => {
                const bodyBuf = Buffer.concat(chunks);
                const headers = { 'Authorization': `Bearer ${apiToken}` };
                if (bodyBuf.length) {
                  headers['Content-Type'] = 'application/json';
                  headers['Content-Length'] = String(bodyBuf.length);
                }
                const proxyReq = http.request({
                  hostname: '127.0.0.1',
                  port: apiPort,
                  path: targetPath,
                  method: req.method,
                  headers
                }, proxyRes => {
                  res.writeHead(proxyRes.statusCode, { 'Content-Type': 'application/json' });
                  proxyRes.pipe(res);
                });
                proxyReq.on('error', err => {
                  res.writeHead(502, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify({ error: { message: String(err) } }));
                });
                if (bodyBuf.length) proxyReq.write(bodyBuf);
                proxyReq.end();
              });
              return;
            }
            const urlPath = new URL(req.url, 'http://127.0.0.1').pathname;
            const file = urlPath === '/' ? path.join(root, 'Axx.html') : path.join(root, urlPath);
            if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
            res.writeHead(200, { 'Content-Type': file.endsWith('.js') ? 'application/javascript' : 'text/html' });
            res.end(fs.readFileSync(file));
          });
          await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
          const browser = await chromium.launch({
            headless: true,
            executablePath: process.env.AXX_TEST_CHROMIUM || path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')
          });
          try {
            const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
            await page.addInitScript(() => {
              const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1660, spaceRight: 260, spaceAbove: 800, spaceBelow: 240 };
              window.__timerCalls = [];
              window.__TAURI__ = {
                core: {
                  invoke: async (name, args) => {
                    if (name === 'native_status') return { native: true, backendReady: true, backendError: null, shortcut: 'Alt+Shift+A', alwaysOnTop: true, timer: null, dataDirectory: 'LIVE_M5', desktop };
                    if (name === 'desktop_layout') return { ...desktop, ...args };
                    if (name === 'set_timer') { window.__timerCalls.push(args.task); return null; }
                    if (name !== 'backend_request') return null;
                    const { method, path: route, body } = args;
                    const res = await fetch(`/proxy-api${route}`, {
                      method,
                      headers: body ? { 'Content-Type': 'application/json' } : {},
                      body: body ? JSON.stringify(body) : undefined
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
                    return data;
                  }
                },
                event: { listen: async () => () => {} }
              };

              // Provide a real canvas MediaStream for getDisplayMedia in headless Chromium
              if (navigator.mediaDevices) {
                navigator.mediaDevices.getDisplayMedia = async () => {
                  const c = document.createElement('canvas');
                  c.width = 320;
                  c.height = 180;
                  const ctx = c.getContext('2d');
                  let frame = 0;
                  const timer = setInterval(() => {
                    frame++;
                    ctx.fillStyle = frame % 2 ? '#101828' : '#1d2939';
                    ctx.fillRect(0, 0, 320, 180);
                    ctx.fillStyle = '#51ceff';
                    ctx.fillRect((frame * 12) % 280, 40, 40, 40);
                  }, 50);
                  const stream = c.captureStream(20);
                  const track = stream.getVideoTracks()[0];
                  track.addEventListener('ended', () => clearInterval(timer));
                  return stream;
                };
              }
            });

            await page.goto(`http://127.0.0.1:${server.address().port}`);
            await page.waitForFunction(() => window.Axx?.desktop?.ready && !window.Axx.companion.connecting);

            const m5Result = await page.evaluate(async () => {
              // --- A. SCREEN RECORDER ---
              document.getElementById('r19-countdown').value = '0';
              document.getElementById('r19-microphone').checked = false;
              document.getElementById('a11-screen-audio').checked = false;
              document.getElementById('r19-auto-save').checked = false;
              Axx.capture19.readFields();
              Axx.capture19.start();

              await new Promise(resolve => {
                const check = () => Axx.actions.screen.state === 'running' ? resolve() : setTimeout(check, 40);
                check();
              });
              const indicatorRunning = document.getElementById('a11-capture-indicator').dataset.state;
              await new Promise(r => setTimeout(r, 350));
              Axx.capture19.addMarker();
              Axx.actions.screen.toggle(); // pause
              await new Promise(resolve => {
                const check = () => Axx.actions.screen.state === 'paused' ? resolve() : setTimeout(check, 40);
                check();
              });
              const elapsedPaused1 = Axx.actions.screen.clock.elapsed();
              await new Promise(r => setTimeout(r, 150));
              const elapsedPaused2 = Axx.actions.screen.clock.elapsed();
              Axx.actions.screen.toggle(); // resume
              await new Promise(resolve => {
                const check = () => Axx.actions.screen.state === 'running' ? resolve() : setTimeout(check, 40);
                check();
              });
              await new Promise(r => setTimeout(r, 350));
              Axx.actions.screen.stop();
              await new Promise(resolve => {
                const check = () => Axx.actions.screen.state === 'finished' && Axx.actions.screen.blob?.size > 0 ? resolve() : setTimeout(check, 50);
                check();
              });
              await Axx.capture19.save(false, false);
              const recVerified = Axx.capture19.lastVerifiedFile;
              const recSavedFlag = Axx.actions.screen.saved;
              const recStatusText = document.getElementById('r19-save-status').textContent;

              // --- B. TIMER ---
              Axx.app.startTimer(2000, 'timer');
              const tRunning = Axx.app.store.data.timer.status;
              await new Promise(r => setTimeout(r, 200));
              Axx.app.pauseResume();
              const tPaused = Axx.app.store.data.timer.status;
              const remPaused1 = Axx.remaining(Axx.app.store.data.timer, Date.now());
              // Trigger 3D visual transformations and verify remaining time does not change
              Axx.app.renderer.setForm(15);
              Axx.app.renderer.setDigit(7);
              await new Promise(r => setTimeout(r, 150));
              const remPaused2 = Axx.remaining(Axx.app.store.data.timer, Date.now());
              Axx.app.pauseResume(); // resume
              const tResumed = Axx.app.store.data.timer.status;
              Axx.app.cancelCurrent();
              const tCancelled = Axx.app.store.data.timer.status;

              // Short timer completion
              Axx.app.startTimer(1000, 'timer');
              await new Promise(resolve => {
                const check = () => {
                  Axx.app.tick();
                  if (Axx.app.store.data.timer?.status === 'completed') resolve();
                  else setTimeout(check, 60);
                };
                check();
              });
              const tCompleted = Axx.app.store.data.timer.status;

              // --- C. MUSIC ---
              const musicEmptyPhase = Axx.actions.music.phase;
              const musicEmptySignal = Axx.actions.music.readSignal(0.016).level;
              const demoWav = Axx.music15.demoFile();
              Axx.actions.music.add([demoWav]);
              const musicLoadedCount = Axx.actions.music.tracks.length;
              await Axx.actions.music.play();
              const musicPlayingPhase = Axx.actions.music.phase;
              Axx.actions.music.pause();
              const musicPausedPhase = Axx.actions.music.phase;
              const musicPausedSignal = Axx.actions.music.readSignal(0.016).level;
              const mediaHubSnap = Axx.media16.snapshot();

              return {
                recorder: {
                  indicatorRunning,
                  elapsedPausedDiff: Math.abs(elapsedPaused2 - elapsedPaused1),
                  recSavedFlag,
                  recVerified,
                  recStatusText,
                  markerCount: Axx.capture19.markers.length
                },
                timer: {
                  tRunning,
                  tPaused,
                  remPausedDiff: Math.abs(remPaused2 - remPaused1),
                  tResumed,
                  tCancelled,
                  tCompleted,
                  ipcTimerCalls: window.__timerCalls.length
                },
                music: {
                  musicEmptyPhase,
                  musicEmptySignal,
                  musicLoadedCount,
                  musicPlayingPhase,
                  musicPausedPhase,
                  musicPausedSignal,
                  mediaHubSource: mediaHubSnap.source
                }
              };
            });

            assert.equal(m5Result.recorder.indicatorRunning, 'running');
            assert.equal(m5Result.recorder.elapsedPausedDiff, 0, 'Clock must not advance while paused');
            assert.equal(m5Result.recorder.recSavedFlag, true);
            assert.equal(m5Result.recorder.recVerified.verified, true);
            assert(m5Result.recorder.recVerified.bytes > 0);
            assert(m5Result.recorder.recStatusText.startsWith('Guardado:'));
            assert.equal(m5Result.recorder.markerCount, 1);

            assert.equal(m5Result.timer.tRunning, 'running');
            assert.equal(m5Result.timer.tPaused, 'paused');
            assert.equal(m5Result.timer.remPausedDiff, 0, 'Visual 3D transforms or pause time must not alter timer remaining');
            assert.equal(m5Result.timer.tResumed, 'running');
            assert.equal(m5Result.timer.tCancelled, 'cancelled');
            assert.equal(m5Result.timer.tCompleted, 'completed');
            assert(m5Result.timer.ipcTimerCalls >= 4);

            assert.equal(m5Result.music.musicEmptyPhase, 'empty');
            assert.equal(m5Result.music.musicEmptySignal, 0);
            assert.equal(m5Result.music.musicLoadedCount, 1);
            assert.equal(m5Result.music.musicPlayingPhase, 'running');
            assert.equal(m5Result.music.musicPausedPhase, 'paused');
            assert.equal(m5Result.music.musicPausedSignal, 0, 'Paused music must not fake audio energy');

            console.log(JSON.stringify({ ok: true, m5Result }));
          } finally {
            await browser.close();
            server.closeAllConnections?.();
            server.close();
          }
          process.exit(0);
        })().catch(e => { console.error(e); process.exit(1); });
        """
        env = os.environ.copy()
        env['AXX_LIVE_PORT'] = str(self.server.server_port)
        env['AXX_LIVE_TOKEN'] = self.server.host_token
        proc = subprocess.run(['node', '-e', node_script], env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(proc.returncode, 0, f'Playwright M5 test failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}')
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(out['ok'])
        rec_info = out['m5Result']['recorder']['recVerified']
        disk_file = Path(rec_info['path'])
        self.assertTrue(disk_file.exists(), 'Recorded video file must exist on disk')
        self.assertGreater(disk_file.stat().st_size, 0)
        self.assertEqual(hashlib.sha256(disk_file.read_bytes()).hexdigest(), rec_info['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
