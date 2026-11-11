import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.speech import dictation_models as models
from backend.speech.offline_asr import OfflineTranscriptionService
from backend.speech.windows_tts import SpeechError


class DictationModelsTests(unittest.TestCase):
    def test_catalog_has_pinned_hashes_licenses_and_no_implicit_download(self):
        self.assertEqual(models.CATALOG['engine_version'], '0.4.0')
        self.assertEqual(len(models.CATALOG['source_commit']), 40)
        for item in models.CATALOG['models']:
            self.assertEqual(len(item['sha256']), 64)
            self.assertEqual(len(item['revision']), 40)
            self.assertIn(item['license'], ('cc-by-4.0', 'apache-2.0'))
            self.assertFalse(item['capabilities']['streaming'])
        self.assertFalse(models.models(None)['downloads'])

    def test_missing_unknown_path_and_incompatible_translation_are_rejected(self):
        for model_id in ('../model', '/tmp/model.gguf', None, 'unknown'):
            with self.subTest(model_id=model_id), self.assertRaises(SpeechError): models.resolve(model_id, None, 'es', 'transcribe')
        with self.assertRaisesRegex(SpeechError, 'cannot translate'): models.resolve('parakeet-tdt-0.6b-v3', None, 'es', 'translate')
        with self.assertRaisesRegex(SpeechError, 'Language unavailable'): models.resolve('canary-180m-flash', None, 'ja', 'transcribe')

    def test_installed_whisper_is_selected_per_request_without_changing_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); selected = root / 'faster-whisper-small'; selected.mkdir()
            for name in ('model.bin', 'tokenizer.json', 'config.json', 'vocabulary.txt'): (selected / name).write_text('fixture')
            service = OfflineTranscriptionService(root); self.addCleanup(service.close)
            original = service.model_path
            with patch.object(models, 'model_root', return_value=root), patch.object(service, '_execute', return_value={'text':'123,45 mg'}) as execute:
                result = service.transcribe({'model':'faster-whisper-small', 'mime':'audio/wav', 'language':'fr',
                    'audio_base64':base64.b64encode(b'RIFF0000WAVEdata').decode()})
                self.assertEqual(result['text'], '123,45 mg')
                self.assertEqual(execute.call_args.args[0]['model_path'], str(selected))
                self.assertEqual(execute.call_args.args[0]['language'], 'fr')
            self.assertEqual(service.model_path, original)

    def test_modified_gguf_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            item = models.CATALOG['models'][0]; path = Path(directory) / item['filename']; path.write_bytes(b'bad model')
            with self.assertRaisesRegex(SpeechError, 'SHA256 mismatch'): models.verify_cpp_model(path)


if __name__ == '__main__': unittest.main()
