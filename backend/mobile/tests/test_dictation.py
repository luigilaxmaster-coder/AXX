import base64
import threading
import unittest
import uuid

from backend.mobile.dictation import MobileDictation


class Store:
    def __init__(self):
        self.revoked = False

    def devices(self):
        return [{'device_id': 'phone', 'revoked': self.revoked, 'scopes': ['voice']}]


class DictationTests(unittest.TestCase):
    def body(self):
        return dict(request_id=str(uuid.uuid4()), mime='audio/mp4',
                    audio_base64=base64.b64encode(b'\x00\x00\x00\x18ftyp' + b'0' * 32).decode())

    def test_replay_runs_local_asr_once_and_rejects_foreign_or_changed_audio(self):
        store, calls, entered, release = Store(), [], threading.Event(), threading.Event()

        def backend(*args):
            calls.append(args)
            entered.set()
            release.wait(2)
            return {'text': 'Tráeme el PDF de mi PC'}

        service = MobileDictation(store, backend)
        body = self.body()
        self.assertEqual(service.submit('phone', body)['state'], 'transcribing')
        self.assertTrue(entered.wait(1))
        service.submit('phone', body)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            service.submit('phone', {**body, 'audio_base64': self.body()['audio_base64'][:-4] + 'MTEx'})
        with self.assertRaises(ValueError):
            service.status('other', body['request_id'])
        release.set()
        for thread in threading.enumerate():
            if thread.name == 'axx-phone-dictation':
                thread.join(2)
        self.assertEqual(service.status('phone', body['request_id'])['text'], 'Tráeme el PDF de mi PC')
        self.assertEqual(calls[0][1], '/axx-api/speech/transcribe')
        store.revoked = True
        with self.assertRaises(ValueError):
            service.status('phone', body['request_id'])

    def test_invalid_audio_and_unbounded_input_are_rejected(self):
        service = MobileDictation(Store(), lambda *args: self.fail('must not transcribe'))
        for body in [self.body() | {'request_id': 'not-an-id'}, self.body() | {'audio_base64': '!'},
                     self.body() | {'audio_base64': 'A' * 1900001}, self.body() | {'mime': 'audio/wav'}]:
            with self.assertRaises((ValueError, TypeError)):
                service.submit('phone', body)
