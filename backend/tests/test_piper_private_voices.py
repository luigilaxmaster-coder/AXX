"""Private, locally trained Piper voices are discovered safely and expose styles."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.speech.piper_tts import PiperSpeechService, STYLES


class PrivatePiperVoiceTests(unittest.TestCase):
    def _service(self, directory):
        service = PiperSpeechService(Path(directory))
        service.python.parent.mkdir(parents=True)
        service.python.write_bytes(b'')
        service.models.mkdir(parents=True)
        return service

    def test_private_voice_lists_all_styles_with_config_label(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.script = Path(directory) / 'worker.py'
            service.script.write_text('')
            (service.models / 'axx-morcito-es.onnx').write_bytes(b'x')
            (service.models / 'axx-morcito-es.onnx.json').write_text(json.dumps(
                {'axx': {'label': 'Axxmorcito Rápida', 'language': 'es-MX'}}), encoding='utf-8')
            names = {voice['name']: voice for voice in service.voices()}
            self.assertEqual(len(names), len(STYLES))
            self.assertEqual(names['piper:axx-morcito-es']['label'], 'Axxmorcito Rápida')
            self.assertEqual(names['piper:axx-morcito-es@calma']['label'], 'Axxmorcito Rápida · Tranquila')
            self.assertEqual(names['piper:axx-morcito-es@emocion']['language'], 'es-MX')

    def test_invalid_private_names_and_configs_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.script = Path(directory) / 'worker.py'
            service.script.write_text('')
            for name in ('axx-Bad', 'axx-', 'axx-ok'):
                (service.models / (name + '.onnx')).write_bytes(b'x')
            (service.models / 'axx-ok.onnx.json').write_text('not json', encoding='utf-8')
            self.assertEqual(service.voices(), [])

    def test_style_parameters_reach_worker_request(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            sent = {}
            with patch.object(service, '_models', return_value={'piper:axx-a@calma': ('axx-a', 'A', 'es')}):
                class Stop(Exception):
                    pass
                def fake_write(data):
                    sent.update(json.loads(data))
                    raise Stop
                process = type('P', (), {'poll': lambda self: None,
                                         'stdin': type('S', (), {'write': staticmethod(fake_write), 'flush': lambda self: None})()})()
                service._worker = (process, None, None)
                with self.assertRaises(Exception):
                    service._request('piper:axx-a@calma', 'Hola')
            self.assertEqual(sent['voice'], 'axx-a')
            self.assertEqual(sent['length_factor'], STYLES['calma'][1])
            self.assertEqual(sent['noise_scale'], STYLES['calma'][2])


if __name__ == '__main__':
    unittest.main()
