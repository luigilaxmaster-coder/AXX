import base64
import io
import queue
from pathlib import Path
import tempfile
import threading
import time
import unittest
import wave
from types import SimpleNamespace
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

    def test_stopped_worker_closes_stdin_once(self):
        import io
        from types import SimpleNamespace
        stream = io.BytesIO()
        process = SimpleNamespace(stdin=stream)
        self.service._worker = (process, None, None)
        with patch('backend.speech.moss_tts.terminate_process_tree') as terminate:
            self.service._stop_worker()
            self.service._stop_worker()
            terminate.assert_called_once_with(process, None)
        self.assertTrue(stream.closed)
        self.assertIsNone(self.service._worker)
        with self.assertRaises(BrokenPipeError):
            self.service._send(process, {'cancel': True})

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

    def enable_cache(self):
        reference = Path(self.temp.name) / 'reference.wav'
        reference.write_bytes(b'private-reference')
        self.service._voice_paths.return_value = {'moss:axx-alba': (reference, 'Axx Alba')}
        self.service.root = Path(self.temp.name)
        self.service.models = self.service.root / 'models'
        (self.service.root / 'onnx_tts_runtime.py').write_text('# engine fixture')
        (self.service.root / 'ort_cpu_runtime.py').write_text('# engine fixture')
        return reference

    def test_cached_stream_preserves_pcm_without_loading_model(self):
        self.enable_cache()
        request = {**self.body, 'id': 'request1', 'stream': True}
        responses = queue.Queue()
        responses.put({**self.event(), 'id': request['id']})
        responses.put({'id': request['id'], 'ok': True})
        worker = (SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None), None, responses)
        with patch.object(self.service, '_ensure_worker', return_value=worker):
            original = list(self.service._request(request))
        with patch.object(self.service, '_ensure_worker', side_effect=AssertionError('cache must bypass the model')):
            replay = list(self.service._request({**request, 'id': 'request2'}))
            wav = self.service.synthesize(self.body)
            self.assertFalse(wav['playback_verified'])
            self.assertEqual(wav['evidence']['frames'], 240)
        self.assertEqual(b''.join(base64.b64decode(e['pcm_base64']) for e in original),
                         b''.join(base64.b64decode(e['pcm_base64']) for e in replay))
        self.assertTrue(all(e['cache_hit'] and e['id'] == 'request2' for e in replay))
        self.assertEqual(self.service._cache_path({**request, 'language': 'es-DO'}),
                         self.service._cache_path({**request, 'language': 'es'}))
        self.assertNotEqual(self.service._cache_path(request), self.service._cache_path({**request, 'text': 'Otra frase.'}))
        old_path = self.service._cache_path(request)
        reference = self.service._voice_paths.return_value['moss:axx-alba'][0]
        reference.write_bytes(b'new-private-voice')
        self.assertNotEqual(old_path, self.service._cache_path(request))

    def test_cancelled_audio_is_not_cached(self):
        self.enable_cache()
        request = {**self.body, 'id': 'cancel', 'stream': True}
        responses = queue.Queue()
        responses.put({**self.event(), 'id': 'cancel'})
        responses.put({'id': 'cancel', 'cancelled': True})
        worker = (SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None), None, responses)
        with patch.object(self.service, '_ensure_worker', return_value=worker):
            with self.assertRaises(SpeechError): list(self.service._request(request))
        self.assertFalse(self.service._cache_path(request).exists())

    def test_cache_rejects_truncated_wav_and_stays_bounded(self):
        self.enable_cache()
        path = self.service._cache_path(self.body)
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
            output.writeframes(b'\x01\x00' * 240)
        raw = buffer.getvalue()
        self.service._save_cache(path, raw[:-10])
        self.assertIsNone(self.service._read_cache(path))
        self.service._save_cache(path, b'bad-wav-data' * 10)
        self.assertIsNone(self.service._read_cache(path))
        with patch('backend.speech.moss_tts.MAX_CACHE', len(raw) * 2):
            for index in range(5):
                self.service._save_cache(path.with_name(str(index)+'.wav'), raw)
        self.assertLessEqual(sum(p.stat().st_size for p in path.parent.glob('*.wav')), len(raw)*2)

    def test_background_model_load_does_not_block_cached_speech(self):
        self.enable_cache()
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
            output.writeframes(b'\x01\x00' * 240)
        self.service._save_cache(self.service._cache_path(self.body), buffer.getvalue())
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set(); release.wait(2)
            raise SpeechError('CANCELLED', 'fixture loading stopped')
        with patch.object(self.service, '_ensure_worker', side_effect=load):
            try:
                self.service.prepare({'voice': self.body['voice']})
                self.assertTrue(entered.wait(1))
                sid = self.service.start_stream(self.body)['stream_id']
                self.finish()
                result = self.service.poll_stream({'stream_id': sid, 'after': 0})
                self.assertIsNone(result['error'])
                self.assertTrue(result['events'][0]['cache_hit'])
                self.assertFalse(release.is_set())
            finally:
                release.set()
                deadline = time.monotonic()+2
                while self.service._preparing and time.monotonic()<deadline: time.sleep(.01)


if __name__ == '__main__': unittest.main()
