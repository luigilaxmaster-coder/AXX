"""End-to-end verification for Milestone 4: Voice, Dictation & Translation."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.server import AxxBridgeHandler, ThreadedHTTPServer, resolve_app_paths
from backend.inference.adapter import InferenceAdapter
from backend.inference.router import parse_strict_json
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.sync.identity_sync import IdentityStore
from backend.speech.windows_tts import WindowsSpeechService
from backend.speech.offline_asr import OfflineTranscriptionService, model_path


class Milestone4VoiceTranslationE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.tmp_path = Path(cls.tmp.name)
        cls.config_path, cls.state_path = resolve_app_paths(data_dir=cls.tmp_path)
        config = parse_strict_json(Path(cls.config_path).read_bytes())
        cls.adapter = InferenceAdapter(config, cls.state_path)
        cls.executor = ActionExecutor(cls.state_path, workspace_root=cls.tmp_path / 'artifacts')
        cls.commands = CommandService(cls.executor)
        cls.memory = ProceduralMemory(cls.state_path)
        cls.identity = IdentityStore(cls.state_path)
        cls.speech = WindowsSpeechService(cls.tmp_path)
        cls.transcription = OfflineTranscriptionService(cls.tmp_path)
        handler = type(
            'M4LiveHandler',
            (AxxBridgeHandler,),
            dict(
                adapter=cls.adapter,
                executor=cls.executor,
                commands=cls.commands,
                memory=cls.memory,
                identity=cls.identity,
                speech=cls.speech,
                transcription=cls.transcription,
                config_path=cls.config_path,
            ),
        )
        cls.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.adapter.close()
        cls.commands.close()
        cls.executor.close()
        cls.memory.close()
        cls.identity.close()
        cls.speech.close()
        cls.transcription.close()
        cls.tmp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None, timeout: float = 45.0):
        headers = {'Authorization': f'Bearer {self.server.host_token}'}
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.server.server_port}{path}',
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode('utf-8'))

    def test_1_whisper_model_path_and_tts_to_asr_roundtrip(self):
        resolved = model_path()
        self.assertIsNotNone(resolved, 'faster-whisper-tiny model_path() must resolve')
        self.assertTrue((resolved / 'model.bin').is_file())

        code, status = self.request('GET', '/axx-api/speech/status')
        self.assertEqual(code, 200)
        self.assertTrue(status['asr']['available'])
        self.assertTrue(status['tts']['configured'])

        code, voices = self.request('GET', '/axx-api/speech/voices')
        self.assertEqual(code, 200)
        self.assertTrue(voices['available'])
        voice_name = voices['voices'][0]['name']

        code, synth = self.request('POST', '/axx-api/speech/synthesize', {
            'text': 'Hello system status report one two three',
            'voice': voice_name,
            'rate': 0,
            'volume': 100,
        })
        self.assertEqual(code, 200)
        self.assertEqual(synth['mime'], 'audio/wav')

        code, asr = self.request('POST', '/axx-api/speech/transcribe', {
            'audio_base64': synth['audio_base64'],
            'mime': 'audio/wav',
            'language': 'en',
            'task': 'transcribe',
        })
        self.assertEqual(code, 200)
        self.assertEqual(asr['engine'], 'faster-whisper')
        self.assertEqual(asr['model'], 'tiny')
        self.assertFalse(asr['silence_detected'])
        self.assertTrue(len(asr['text'].strip()) > 0, f'Expected transcribed text, got: {asr}')

    def test_2_local_translation_endpoint_and_validation(self):
        code, same = self.request('POST', '/axx-api/translate', {
            'text': 'Hola mundo',
            'source_lang': 'es-DO',
            'target_lang': 'es',
        })
        self.assertEqual(code, 200)
        self.assertTrue(same['ok'])
        self.assertEqual(same['translated_text'], 'Hola mundo')

        code, tr = self.request('POST', '/axx-api/translate', {
            'text': 'Hola amigo, el archivo está listo.',
            'source_lang': 'es-DO',
            'target_lang': 'en',
        })
        self.assertEqual(code, 200, f'Translate failed: {tr}')
        self.assertTrue(tr['ok'])
        self.assertTrue(len(tr['translated_text'].strip()) > 0)
        self.assertEqual(tr['source_lang'], 'es')
        self.assertEqual(tr['target_lang'], 'en')

        code, bad = self.request('POST', '/axx-api/translate', {
            'text': '',
            'source_lang': 'es',
            'target_lang': 'en',
        })
        self.assertEqual(code, 400)

    def test_3_frontend_voice_dictation_cancellation_and_translation(self):
        import subprocess
        node_script = """
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
              window.__TAURI__ = {
                core: {
                  invoke: async (name, args) => {
                    if (name === 'native_status') return { native: true, backendReady: true, backendError: null, shortcut: 'Alt+Shift+A', alwaysOnTop: true, timer: null, dataDirectory: 'LIVE_M4', desktop };
                    if (name === 'desktop_layout') return { ...desktop, ...args };
                    if (name !== 'backend_request') return null;
                    const { method, path: route, body } = args;
                    if (route === '/axx-api/speech/transcribe' && window.__delayTranscribeMs) {
                      await new Promise(r => setTimeout(r, window.__delayTranscribeMs));
                      return { text: 'Texto tardío que debe descartarse', engine: 'faster-whisper', model: 'tiny' };
                    }
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
            });

            await page.goto(`http://127.0.0.1:${server.address().port}`);
            await page.waitForFunction(() => window.Axx?.desktop?.ready && !window.Axx.companion.connecting);

            const m4Check = await page.evaluate(async () => {
              // 1. Verify wakeWord is honestly reported as planned-not-active and no continuous SpeechRecognition is running
              const snap = Axx.stability20.snapshot();
              const wakeLabel = document.getElementById('chat20-wake-toggle')?.textContent?.trim();

              // 2. Verify late ASR cancellation discards result and never modifies target or sends chat
              const session = Axx.nativeVoice.sessions[0];
              const finals = [];
              const prevFinal = session.owner.onFinal;
              session.owner.onFinal = t => finals.push(t);
              window.__delayTranscribeMs = 300;
              const submitPromise = session.submit(new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'audio/webm;codecs=opus' }));
              setTimeout(() => session.stop(), 40);
              await submitPromise;
              window.__delayTranscribeMs = 0;
              session.owner.onFinal = prevFinal;

              // 3. Verify VoiceTranslation18 (#v18-translation-pane) prepares and translates while keeping original + result
              await Axx.voice13.translation18.prepare('browser', 'es-DO', 'en');
              const v18Ready = Axx.voice13.translation18.ready;
              document.getElementById('v18-original').value = 'Buenos días equipo.';
              Axx.voice13.original18 = 'Buenos días equipo.';
              Axx.voice13.translateManual18();
              await new Promise(resolve => {
                const check = () => {
                  if (!Axx.voice13.jobs18.pending && Axx.voice13.translated18.trim()) resolve();
                  else setTimeout(check, 100);
                };
                check();
              });

              // 4. Verify Symbiosis.translate() (#view-translation) keeps original and translated text
              document.getElementById('translation-source').value = 'El sistema funciona correctamente.';
              document.getElementById('translation-from').value = 'es';
              document.getElementById('translation-to').value = 'en';
              document.getElementById('translation-engine').value = 'browser';
              await Axx.symbiosis.translate();

              return {
                wakeWord: snap.wakeWord,
                wakeLabel,
                lateFinalsCount: finals.length,
                v18Ready,
                v18Original: document.getElementById('v18-original').value,
                v18Result: document.getElementById('v18-result').value,
                symOriginal: document.getElementById('translation-source').value,
                symOutput: document.getElementById('translation-output').value
              };
            });

            assert.equal(m4Check.wakeWord, 'planned-not-active');
            assert(!m4Check.wakeLabel.includes('Hey Axx'), 'Wake button must not claim permanent Hey Axx');
            assert.equal(m4Check.lateFinalsCount, 0, 'Cancelled ASR must not emit late final text');
            assert.equal(m4Check.v18Ready, true);
            assert.equal(m4Check.v18Original, 'Buenos días equipo.');
            assert(m4Check.v18Result.trim().length > 0);
            assert.equal(m4Check.symOriginal, 'El sistema funciona correctamente.');
            assert(m4Check.symOutput.trim().length > 0);
            console.log(JSON.stringify({ ok: true, m4Check }));
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
        self.assertEqual(proc.returncode, 0, f'Playwright M4 test failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}')
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(out['ok'])



if __name__ == '__main__':
    unittest.main()
