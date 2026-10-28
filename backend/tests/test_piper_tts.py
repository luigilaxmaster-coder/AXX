"""Piper is optional, but a selected voice must synthesize or fail explicitly."""
import base64
import io
import os
from pathlib import Path
import tempfile
import time
import unittest
import wave

from backend.speech.piper_tts import PiperSpeechService
from backend.speech.windows_tts import SpeechError


class PiperSpeechTests(unittest.TestCase):
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
