import unittest
import base64
import io
import json
import tempfile
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

from backend.speech.speech_text import prepare_spoken_text, spanish_integer
from backend.speech.offline_asr import OfflineTranscriptionService, excessive_repetition, model_path, guard_worker_imports, InferenceOnlyImports, worker_main, MAX_AUDIO
from backend.speech.windows_tts import SpeechError


class SpokenTextTests(unittest.TestCase):
    def test_mime_case_is_normalized_and_service_timing_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            service = OfflineTranscriptionService(directory)
            service.model_path = Path(directory)
            try:
                with patch.object(service, 'status', return_value={'available': True}), \
                        patch.object(service, '_execute', return_value={'text': 'hola'}) as execute:
                    result = service.transcribe({'audio_base64': base64.b64encode(b'RIFF0000WAVEdata').decode(),
                                                 'mime': 'Audio/WAV; codecs=pcm', 'language': 'es'})
                    self.assertEqual(result['text'], 'hola'); self.assertGreaterEqual(result['timings_ms']['service_total'], 0)
                    self.assertEqual(execute.call_count, 1)
                    request = execute.call_args.args[0]
                    self.assertNotIn('audio_path', request)
                    self.assertEqual(base64.b64decode(request['audio_base64']), b'RIFF0000WAVEdata')
                    self.assertFalse(service.data_dir.exists())
                for body in ([], None, 'audio'):
                    with self.assertRaises(SpeechError): service.transcribe(body)
            finally: service.close()

    def test_silence_does_not_load_model(self):
        try:
            import av
            import numpy
        except ImportError:
            self.skipTest('Native audio decoder is not installed')
        import wave
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'silence.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 16000)
            for audio in ({'audio_path': str(path)}, {'audio_base64':base64.b64encode(path.read_bytes()).decode()}):
                with self.subTest(source=next(iter(audio))):
                    output = io.BytesIO()
                    with patch('backend.speech.offline_asr._load_worker_model') as load, \
                            patch.object(sys, 'stdout', type('Output', (), {'buffer': output})()), \
                            patch.object(sys, 'meta_path', list(sys.meta_path)):
                        code = worker_main(json.dumps({**audio, 'model_path':'unused', 'language':'es', 'task':'transcribe'}).encode())
                    result = json.loads(output.getvalue())
                    self.assertEqual(code, 0, result); load.assert_not_called()
                    self.assertTrue(result['result']['silence_detected']); self.assertEqual(result['result']['text'], '')
                    self.assertEqual(result['result']['timings_ms']['model_load'], 0)
                    self.assertEqual(result['result']['timings_ms']['inference'], 0)

    def test_large_memory_payload_remains_cancellable_if_worker_never_reads(self):
        children = []
        def spawn(_command, **kwargs):
            process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            children.append(process)
            return process,None
        with tempfile.TemporaryDirectory() as directory, patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            service = OfflineTranscriptionService(directory)
            errors = []
            def execute():
                try:service._execute({'audio_base64':'A' * (((MAX_AUDIO+2)//3)*4)})
                except SpeechError as exc:errors.append(exc.code)
            thread = threading.Thread(target=execute)
            thread.start()
            try:
                until = time.monotonic()+3
                while (service._active is None or not any(row.name=='axx-asr-input' and row.is_alive() for row in threading.enumerate())) and time.monotonic()<until:
                    time.sleep(.01)
                self.assertEqual(service.cancel_active(),1)
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,['CANCELLED'])
                self.assertTrue(children and all(child.poll() is not None for child in children))
                self.assertFalse(service.data_dir.exists())
            finally:service.close();thread.join(3)

    def test_persistent_worker_installs_only_one_import_guard(self):
        with patch.object(sys,'meta_path',list(sys.meta_path)):
            guard_worker_imports()
            guard_worker_imports()
            guards=[finder for finder in sys.meta_path if isinstance(finder,InferenceOnlyImports)]
            self.assertEqual(len(guards),1)
            with self.assertRaises(ModuleNotFoundError):guards[0].find_spec('torch')

    def test_transcription_worker_is_reused_and_cancelled_worker_is_discarded(self):
        script = ("import json,os,sys,time\n"
                  "n=0\n"
                  "for line in sys.stdin.buffer:\n"
                  " request=json.loads(line);n+=1\n"
                  " if request.get('wait'):time.sleep(10)\n"
                  " print(json.dumps({'ok':True,'result':{'pid':os.getpid(),'count':n}}),flush=True)\n")
        def spawn(_command,**kwargs):
            return subprocess.Popen([sys.executable,'-u','-c',script],**kwargs),None
        with tempfile.TemporaryDirectory() as directory, patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            service=OfflineTranscriptionService(directory)
            try:
                first=service._execute({})
                second=service._execute({})
                self.assertEqual((first['pid'],first['count']),(second['pid'],1))
                self.assertEqual(second['count'],2)
                errors=[]
                def wait_for_worker():
                    try:service._execute({'wait':True})
                    except SpeechError as exc:errors.append(exc.code)
                thread=threading.Thread(target=wait_for_worker)
                thread.start()
                until=time.monotonic()+2
                while service._active is None and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(service.cancel_active(),1)
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,['CANCELLED'])
                self.assertNotEqual(service._execute({})['pid'],first['pid'])
            finally:service.close()

    def test_repeated_asr_output_is_rejected_before_actions(self):
        self.assertTrue(excessive_repetition('no es el que no es el que no es el que no es el que no es el que'))
        self.assertFalse(excessive_repetition('reproduce la canción en Spotify'))

    def test_local_base_model_takes_precedence_when_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'Axx'/'models'/'faster-whisper-base'
            base.mkdir(parents=True)
            with patch.dict('os.environ',{'LOCALAPPDATA':directory}):
                self.assertNotEqual(model_path(),base)
                for name in ('model.bin','tokenizer.json','config.json','vocabulary.txt'):
                    (base/name).touch()
                self.assertEqual(model_path(),base.resolve())

    def test_spanish_accents_questions_and_voice_name_survive(self):
        text = '¡Hola! Soy Axx Titán. ¿Cómo estás? Mañana te ayudaré.'
        self.assertEqual(prepare_spoken_text(text, 'es-DO'), (text, 'es'))
        self.assertEqual(prepare_spoken_text('Man\u0303ana', 'es')[0], 'Mañana.')

    def test_cardinals_and_abbreviations_are_spoken_in_spanish(self):
        self.assertEqual(prepare_spoken_text('Sr. Pérez, hay 22 tareas y 75% listo', 'es')[0],
                         'señor Pérez, hay veintidós tareas y setenta y cinco por ciento listo.')
        for number, expected in [(100, 'cien'), (101, 'ciento uno'), (500, 'quinientos'),
                                 (999, 'novecientos noventa y nueve'), (2026, 'dos mil veintiséis')]:
            self.assertEqual(spanish_integer(number), expected)

    def test_identifiers_versions_dates_and_decimals_are_not_rewritten(self):
        text = 'v0.20.19 192.168.1.1 23/10/2026 09:30 -25 3,14 0012 X123 99999.'
        self.assertEqual(prepare_spoken_text(text, 'es')[0], text)

    def test_latin_punctuation_does_not_become_chinese(self):
        self.assertEqual(prepare_spoken_text('**Sí**... vamos — juntos!!', 'es')[0], 'Sí, vamos, juntos!')
        self.assertEqual(prepare_spoken_text('Ready', 'en-US')[0], 'Ready.')
        self.assertEqual(prepare_spoken_text('Hay 2 tareas')[0], 'Hay 2 tareas.')  # ambiguous: no forced language
        self.assertEqual(prepare_spoken_text('Hola, hay 2 tareas')[0], 'Hola, hay dos tareas.')

    def test_english_and_other_languages_do_not_receive_spanish_expansions(self):
        self.assertEqual(prepare_spoken_text('Dr. Smith has 22 tasks.', 'en')[0], 'Dr. Smith has 22 tasks.')
        self.assertEqual(prepare_spoken_text('Bonjour', 'fr'), ('Bonjour', 'fr'))

    def test_conversational_pauses_ordinals_and_technical_terms(self):
        text = 'Hola principal podemos revisar el PDF de la 1ª prueba'
        self.assertEqual(prepare_spoken_text(text, 'es')[0],
                         'Hola principal, podemos revisar el pe-de-efe de la primera prueba.')
        text2 = 'Por supuesto revisa la pág. 10 y el Wi-Fi'
        self.assertEqual(prepare_spoken_text(text2, 'es')[0],
                         'Por supuesto, revisa la página diez y el uay-fay.')
        self.assertEqual(prepare_spoken_text('1er intento, 2do intento y 3er intento.', 'es')[0],
                         'primer intento, segundo intento y tercer intento.')


if __name__ == '__main__':
    unittest.main()
