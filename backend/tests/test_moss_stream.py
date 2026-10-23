import base64
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.speech.moss_tts import MossSpeechService
from backend.speech.windows_tts import SpeechError


class MossStreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = MossSpeechService(Path(self.temp.name))
        self.addCleanup(self.service.close)
        self.voices = patch.object(self.service, '_voice_paths', return_value={'moss:axx-alba': (Path('sample.wav'), 'Axx Alba')})
        self.voices.start(); self.addCleanup(self.voices.stop)
        self.body = {'text': 'Hola. Hello.', 'voice': 'moss:axx-alba'}

    @staticmethod
    def event():
        return {'chunk': True, 'pcm_base64': base64.b64encode(b'\x01\x00' * 240).decode(),
                'sample_rate': 24000, 'channels': 1}

    def finish(self):
        deadline = time.monotonic() + 2
        while not self.service._stream['done']:
            if time.monotonic() > deadline: self.fail('stream did not finish')
            time.sleep(.01)

    def test_audio_available_before_generation_finishes_and_poll_is_replayable(self):
        gate = threading.Event()
        def generate(_):
            yield self.event()
            gate.wait(2)
            yield self.event()
        with patch.object(self.service, '_request', side_effect=generate):
            sid = self.service.start_stream(self.body)['stream_id']
            try:
                deadline = time.monotonic() + 1
                while not self.service._stream['events'] and time.monotonic() < deadline: time.sleep(.01)
                body = {'stream_id': sid, 'after': 0}
                first = self.service.poll_stream(body)
                self.assertFalse(first['done'])
                self.assertEqual(len(first['events']), 1)
                self.assertEqual(first['events'], self.service.poll_stream(body)['events'])
            finally: gate.set()
            self.finish()
            final = self.service.poll_stream({'stream_id': sid, 'after': 1})
            self.assertTrue(final['done'])
            self.assertEqual(final['events'][0]['seq'], 2)

    def test_invalid_voice_and_cursor_are_rejected(self):
        with self.assertRaises(SpeechError): self.service.start_stream({**self.body, 'voice': '../../other'})
        for body in ({'stream_id': 'x', 'after': -1}, {'stream_id': 'x', 'after': True}, {'stream_id': 'x', 'after': 0}):
            with self.assertRaises(SpeechError): self.service.poll_stream(body)

    def test_selected_language_reaches_worker_and_invalid_language_is_rejected(self):
        for language in (None, 2, '', 'es;command', 'spanish'):
            with self.assertRaises(SpeechError):
                self.service.start_stream({**self.body, 'language': language})
        received = []
        def generate(request):
            received.append(request)
            yield self.event()
        with patch.object(self.service, '_request', side_effect=generate):
            self.service.start_stream({**self.body, 'language': 'es-DO'})
            self.finish()
        self.assertEqual(received[0]['language'], 'es-DO')

    def test_invalid_audio_ends_stream_with_error(self):
        with patch.object(self.service, '_request', return_value=({**self.event(), 'sample_rate': 0} for _ in range(1))):
            sid = self.service.start_stream(self.body)['stream_id']
            self.finish()
            result = self.service.poll_stream({'stream_id': sid, 'after': 0})
            self.assertTrue(result['done'])
            self.assertEqual(result['error']['code'], 'PROCESS_FAILURE')
            self.assertFalse(result['events'])

    def test_poll_batch_is_bounded_and_old_stream_expires(self):
        with patch.object(self.service, '_request', side_effect=lambda _: iter(self.event() for _ in range(12))):
            sid = self.service.start_stream(self.body)['stream_id']; self.finish()
            result = self.service.poll_stream({'stream_id': sid, 'after': 0})
            self.assertEqual(len(result['events']), 8); self.assertFalse(result['done'])
            self.assertTrue(self.service.poll_stream({'stream_id': sid, 'after': 8})['done'])
            self.service.start_stream(self.body); self.finish()
            with self.assertRaises(SpeechError): self.service.poll_stream({'stream_id': sid, 'after': 0})


if __name__ == '__main__': unittest.main()
