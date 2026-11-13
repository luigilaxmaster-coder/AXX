"""Piper is optional, but a selected voice must synthesize or fail explicitly."""
import base64
import io
import json
import os
import runpy
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import wave

from backend.speech.piper_tts import PiperSpeechService
from backend.speech.windows_tts import SpeechError


class PiperSpeechTests(unittest.TestCase):
    def test_worker_rejects_paths_and_unbounded_style_parameters(self):
        piper = types.SimpleNamespace(PiperVoice=None, PiperConfig=None, SynthesisConfig=None)
        with patch.dict('sys.modules', {'piper': piper, 'onnxruntime': types.SimpleNamespace()}):
            worker = runpy.run_path(str(Path(__file__).parents[2] / 'resources' / 'piper_worker.py'))
        self.assertTrue(worker['PRIVATE'].fullmatch('axx-morcito-es'))
        for name in ('../axx-morcito-es', 'axx-morcito-es.v3.bak', 'axx-x/other'):
            self.assertFalse(worker['PRIVATE'].fullmatch(name))
        for value in (-1, 2, True, float('nan'), '0.5'):
            with self.assertRaises(ValueError):
                worker['_bounded']({'noise_scale': value}, 'noise_scale', 0, 1.2)
        self.assertEqual(worker['_bounded']({'noise_scale': 0}, 'noise_scale', 0, 1.2), 0)

    def test_private_voice_discovery_preserves_identity_and_excludes_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            service = PiperSpeechService(Path(directory))
            service.python.parent.mkdir(parents=True)
            service.python.touch()
            service.models.mkdir()
            for name in ('axx-morcito-es', 'axx-morcito-en', 'axx-morcito-es.v3.bak', 'axx-invalid'):
                (service.models / (name + '.onnx')).touch()
                (service.models / (name + '.onnx.json')).write_text(json.dumps(
                    {'axx': {'label': 'Axxmorcito', 'language': 'es-DO'}}) if name != 'axx-invalid' else '[]', encoding='utf-8')
            voices = {v['name']: v for v in service.voices()}
            self.assertIn('piper:axx-morcito-es', voices)
            self.assertIn('piper:axx-morcito-en', voices)
            self.assertEqual(voices['piper:axx-morcito-es']['label'], 'Axxmorcito')
            self.assertEqual(voices['piper:axx-morcito-es']['language'], 'es-DO')
            self.assertFalse(any('bak' in name or 'invalid' in name for name in voices))

    def test_missing_voice_does_not_replace_saved_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            service = PiperSpeechService(Path(directory))
            self.assertEqual(service.voices(), [])
            self.assertFalse(service.status()['available'])
            with self.assertRaises(SpeechError):
                service.synthesize({'voice': 'piper:es_ES-carlfm-x_low', 'text': 'Hola'})
            with self.assertRaises(SpeechError):
                service.prepare({'voice': ['invalid']})

    @unittest.skipUnless(os.name == 'nt', 'Local Piper voice requires Windows')
    def test_installed_voice_produces_valid_wav(self):
        directory = Path(os.environ.get('LOCALAPPDATA', '')) / 'Axx'
        service = PiperSpeechService(directory)
        self.addCleanup(service.close)
        voices = service.voices()
        if not voices:
            self.skipTest('Piper voice pack not installed')
        uri = voices[0]['name']
        service.prepare({'voice': uri})
        deadline = time.monotonic() + 20
        while uri not in service.status()['prepared_voices'] and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertIn(uri, service.status()['prepared_voices'])
        result = service.synthesize({'voice': uri, 'text': 'Hola, soy Axx.'})
        raw = base64.b64decode(result['audio_base64'], validate=True)
        with wave.open(io.BytesIO(raw)) as audio:
            self.assertGreater(audio.getnframes(), 0)
            self.assertEqual(audio.getsampwidth(), 2)
        self.assertEqual(result['engine'], 'piper-onnx')
        self.assertFalse(result['playback_verified'])
