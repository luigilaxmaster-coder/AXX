import unittest
import base64
import io
import json
import tempfile
import subprocess
import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

from backend.speech.speech_text import prepare_spoken_text, spanish_integer
from backend.speech.offline_asr import OfflineTranscriptionService, excessive_repetition, model_path, guard_worker_imports, InferenceOnlyImports, worker_main, MAX_AUDIO, _ASRRequest
from backend.speech.windows_tts import SpeechError


class AttributedTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=OfflineTranscriptionService(self.temp.name);self.service.model_path=Path(self.temp.name)
        self.addCleanup(self.service.close)
        self.available=patch.object(self.service,'status',return_value={'available':True})
        self.available.start();self.addCleanup(self.available.stop)

    @staticmethod
    def body(request_id='request-a',language='es'):
        return {'request_id':request_id,'audio_base64':base64.b64encode(b'RIFF0000WAVEdata').decode(),
                'mime':'audio/wav','language':language,'task':'transcribe'}

    def wait_active(self,request_id):
        until=time.monotonic()+3
        while time.monotonic()<until:
            with self.service._lock:
                if self.service._active is not None and self.service._active.request_id==request_id:return self.service._active
            time.sleep(.005)
        self.fail('Synthetic ASR request was not admitted')

    def test_late_cancel_and_external_event_of_completed_a_do_not_kill_b_in_reused_worker(self):
        lease_event=threading.Event()
        script=("import json,os,sys,time\n"
                "n=0\n"
                "for line in sys.stdin.buffer:\n"
                " request=json.loads(line);n+=1\n"
                " if request.get('language')=='en':time.sleep(.4)\n"
                " print(json.dumps({'ok':True,'result':{'text':'synthetic','pid':os.getpid(),'count':n}}),flush=True)\n")
        def spawn(_command,**kwargs):
            return subprocess.Popen([sys.executable,'-u','-c',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs),None
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            first=self.service.transcribe(self.body(),cancel_event=lease_event)
            results=[]
            thread=threading.Thread(target=lambda:results.append(self.service.transcribe(self.body('request-b','en'))))
            thread.start()
            try:
                active=self.wait_active('request-b')
                with patch('backend.speech.offline_asr.terminate_process_tree') as terminate:
                    lease_event.set()
                    self.assertEqual(self.service.cancel('request-a'),0)
                    self.assertFalse(active.cancelled.is_set())
                    terminate.assert_not_called()
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(results[0]['pid'],first['pid'])
                self.assertEqual(results[0]['count'],2)
                self.assertEqual(results[0]['request_id'],'request-b')
            finally:
                if thread.is_alive():self.service.cancel('request-b');thread.join(3)

    def test_busy_and_foreign_owner_never_preempt_admitted_request(self):
        entered,release,lease_event=threading.Event(),threading.Event(),threading.Event();errors=[]
        def execute(request,**kwargs):
            entered.set()
            if not release.wait(3):raise AssertionError('Synthetic release timed out')
            return {'text':'synthetic'}
        def run():
            try:self.service.transcribe(self.body(),context_owner='lease-a',deadline_mono=time.monotonic()+5,cancel_event=lease_event)
            except SpeechError as exc:errors.append(exc.code)
        with patch.object(self.service,'_execute',side_effect=execute) as worker:
            thread=threading.Thread(target=run);thread.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(SpeechError) as caught:self.service.transcribe(self.body('request-b'))
                self.assertEqual(caught.exception.code,'BUSY')
                self.assertEqual(self.service.cancel('request-a',context_owner='lease-b'),0)
                self.assertFalse(self.service._requests['request-a'].cancelled.is_set())
                self.assertEqual(self.service.cancel('request-a',context_owner='lease-a'),1)
                self.assertFalse(lease_event.is_set())
                self.assertEqual(worker.call_count,1)
            finally:release.set();thread.join(3)
        self.assertEqual(errors,['CANCELLED'])
        self.assertFalse(self.service._requests)

    def test_captured_cancel_finishes_before_waiting_request_can_reuse_worker(self):
        from backend.inference.process_manager import terminate_process_tree
        killing,release,waiting=threading.Event(),threading.Event(),threading.Event()
        children=[];errors=[];results=[];cancelled=[]
        script=("import json,os,sys,time\nfor line in sys.stdin.buffer:\n"
                " request=json.loads(line)\n"
                " if request.get('language')=='es':time.sleep(10)\n"
                " print(json.dumps({'ok':True,'result':{'pid':os.getpid()}}),flush=True)\n")
        def spawn(_command,**kwargs):
            process=subprocess.Popen([sys.executable,'-u','-c',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            children.append(process);return process,None
        def terminate(process,job):
            killing.set()
            if not release.wait(3):raise AssertionError('Synthetic kill release timed out')
            terminate_process_tree(process,job)
        def first():
            try:self.service.transcribe(self.body())
            except SpeechError as exc:errors.append(exc.code)
        def second():
            waiting.set();results.append(self.service._execute({'language':'en'}))
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn), \
                patch('backend.speech.offline_asr.terminate_process_tree',side_effect=terminate):
            a=threading.Thread(target=first);a.start();self.wait_active('request-a')
            cancel=threading.Thread(target=lambda:cancelled.append(self.service.cancel('request-a')));cancel.start()
            b=threading.Thread(target=second)
            try:
                self.assertTrue(killing.wait(2));b.start();self.assertTrue(waiting.wait(2))
                acquired=self.service._io_lock.acquire(timeout=.05)
                if acquired:self.service._io_lock.release()
                self.assertFalse(acquired)
                self.assertFalse(results);self.assertEqual(len(children),1)
                release.set();cancel.join(3);a.join(3);b.join(3)
                self.assertFalse(any(thread.is_alive() for thread in (a,b,cancel)))
                self.assertEqual(cancelled,[1]);self.assertEqual(errors,['CANCELLED'])
                self.assertEqual(len(children),2)
                self.assertEqual(results[0]['pid'],children[1].pid)
                self.assertNotEqual(results[0]['pid'],children[0].pid)
            finally:
                release.set();cancel.join(3);a.join(3)
                if b.ident is not None:b.join(3)

    def test_response_arriving_after_lease_is_rejected_before_result_delivery(self):
        clock=[99.0]
        original_get=queue.Queue.get
        def get_response(instance,*args,**kwargs):
            line=original_get(instance,*args,**kwargs)
            if isinstance(line,bytes):clock[0]=101.0
            return line
        script="import sys\nfor line in sys.stdin.buffer:print('{\"ok\":true,\"result\":{\"text\":\"late\"}}',flush=True)\n"
        def spawn(_command,**kwargs):
            return subprocess.Popen([sys.executable,'-u','-c',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs),None
        context=_ASRRequest('late-context','lease-a',100.0)
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn), \
                patch('backend.speech.offline_asr.time.monotonic',side_effect=lambda:clock[0]), \
                patch.object(queue.Queue,'get',new=get_response):
            with self.assertRaises(SpeechError) as caught:self.service._execute({},_context=context,wait_for_io=False)
            self.assertEqual(caught.exception.code,'DEADLINE_EXCEEDED')
        self.assertIsNone(self.service._active);self.assertIsNone(self.service._worker)

    def test_scoped_cancel_unblocks_large_memory_pipe_without_taking_io_lock(self):
        children=[];errors=[]
        def spawn(_command,**kwargs):
            process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            children.append(process);return process,None
        body=self.body('large-request')
        body['audio_base64']=base64.b64encode(b'RIFF0000WAVE'+b'\0'*(MAX_AUDIO-12)).decode()
        def run():
            try:self.service.transcribe(body)
            except SpeechError as exc:errors.append(exc.code)
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            thread=threading.Thread(target=run);thread.start()
            try:
                self.wait_active('large-request')
                until=time.monotonic()+2
                while not any(row.name=='axx-asr-input' and row.is_alive() for row in threading.enumerate()) and time.monotonic()<until:time.sleep(.005)
                self.assertTrue(self.service._io_lock.locked())
                self.assertEqual(self.service.cancel('other-request'),0)
                self.assertEqual(self.service.cancel('large-request'),1)
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors,['CANCELLED'])
                self.assertTrue(children and all(child.poll() is not None for child in children))
                self.assertFalse(self.service.data_dir.exists())
            finally:
                if thread.is_alive():self.service.cancel_active();thread.join(3)

    def test_context_deadline_is_enforced_and_context_never_waits_for_foreign_io(self):
        with self.service._io_lock,patch('backend.speech.offline_asr.spawn_managed_process') as spawn:
            with self.assertRaises(SpeechError) as caught:
                self.service.transcribe(self.body(),context_owner='lease-a',deadline_mono=time.monotonic()+2)
            self.assertEqual(caught.exception.code,'BUSY');spawn.assert_not_called()
            with self.assertRaises(SpeechError) as caught:
                self.service.transcribe(self.body('event-only'),cancel_event=threading.Event())
            self.assertEqual(caught.exception.code,'BUSY');spawn.assert_not_called()
        script="import sys,time\nfor line in sys.stdin.buffer:time.sleep(10)\n"
        children=[]
        def spawn(_command,**kwargs):
            process=subprocess.Popen([sys.executable,'-u','-c',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            children.append(process);return process,None
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            with self.assertRaises(SpeechError) as caught:
                self.service.transcribe(self.body('short-lease'),context_owner='lease-a',deadline_mono=time.monotonic()+.1)
            self.assertEqual(caught.exception.code,'DEADLINE_EXCEEDED')
        self.assertTrue(children and all(child.poll() is not None for child in children))
        self.assertIsNone(self.service._active)
        self.assertFalse(self.service.data_dir.exists())

    def test_external_lease_event_unblocks_real_memory_pipe_and_kills_only_own_process(self):
        children=[];errors=[];lease_event=threading.Event()
        def spawn(_command,**kwargs):
            process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            children.append(process);return process,None
        body=self.body('external-lease')
        body['audio_base64']=base64.b64encode(b'RIFF0000WAVE'+b'\0'*(MAX_AUDIO-12)).decode()
        def run():
            try:self.service.transcribe(body,context_owner='lease-a',deadline_mono=time.monotonic()+5,cancel_event=lease_event)
            except SpeechError as exc:errors.append(exc.code)
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn):
            thread=threading.Thread(target=run);thread.start()
            try:
                active=self.wait_active('external-lease')
                until=time.monotonic()+2
                while not any(row.name=='axx-asr-input' and row.is_alive() for row in threading.enumerate()) and time.monotonic()<until:time.sleep(.005)
                self.assertTrue(self.service._io_lock.locked())
                self.assertFalse(active.cancelled.is_set())
                lease_event.set();thread.join(3)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,['CANCELLED'])
                self.assertFalse(active.cancelled.is_set())
                self.assertTrue(children and all(child.poll() is not None for child in children))
                self.assertIsNone(self.service._worker);self.assertFalse(self.service._requests)
                self.assertFalse(self.service.data_dir.exists())
            finally:
                lease_event.set()
                if thread.is_alive():self.service.cancel_active();thread.join(3)

    def test_internal_owner_deadline_and_json_identity_limits_fail_before_worker(self):
        with patch.object(self.service,'_execute',return_value={'text':'synthetic'}) as execute:
            for value in (True,1,None,'../bad','x'*129,'asr-auto-client'):
                with self.subTest(request_id=value),self.assertRaises(SpeechError):self.service.transcribe(self.body(value))
            for fields in ({'context_owner':'forged'},{'deadline_mono':time.monotonic()+1},{'cancel_event':False}):
                with self.subTest(fields=fields),self.assertRaises(SpeechError):self.service.transcribe(self.body()|fields)
            for event in (True,object(),threading.Lock()):
                with self.subTest(cancel_event=event),self.assertRaises(SpeechError):self.service.transcribe(self.body(),cancel_event=event)
            cancelled=threading.Event();cancelled.set()
            with self.assertRaises(SpeechError) as caught:self.service.transcribe(self.body(),cancel_event=cancelled)
            self.assertEqual(caught.exception.code,'CANCELLED');self.assertFalse(self.service._used_request_ids)
            for deadline in (True,float('nan'),time.monotonic()-1,time.monotonic()+61,None):
                with self.subTest(deadline=deadline),self.assertRaises(SpeechError):
                    self.service.transcribe(self.body(),context_owner='lease-a',deadline_mono=deadline)
            with self.assertRaises(SpeechError):self.service.transcribe(self.body(),context_owner=True,deadline_mono=time.monotonic()+1)
            execute.assert_not_called()
            legacy=self.body();legacy.pop('request_id')
            result=self.service.transcribe(legacy)
            self.assertTrue(result['request_id'].startswith('asr-auto-'))
            self.assertIsNone(execute.call_args.kwargs['_context'].deadline_mono)
            self.assertTrue(execute.call_args.kwargs['wait_for_io'])

    def test_used_ids_are_bounded_not_recycled_and_store_no_audio_or_text(self):
        with patch('backend.speech.offline_asr.MAX_REQUEST_IDS',2),patch.object(self.service,'_execute',return_value={'text':'private synthetic transcript'}):
            self.service.transcribe(self.body('first'))
            self.service.transcribe(self.body('second'))
            with self.assertRaises(SpeechError) as caught:self.service.transcribe(self.body('third'))
            self.assertEqual(caught.exception.code,'REQUEST_ID_LIMIT')
            with self.assertRaises(SpeechError) as caught:self.service.transcribe(self.body('first'))
            self.assertEqual(caught.exception.code,'REQUEST_ID_REUSED')
            self.assertEqual(len(self.service._used_request_ids),2)
            self.assertTrue(all(isinstance(value,bytes) and len(value)==32 for value in self.service._used_request_ids))
            legacy=self.body();legacy.pop('request_id')
            self.assertIn('request_id',self.service.transcribe(legacy))
            self.assertFalse(self.service._requests)
            self.assertFalse(self.service.data_dir.exists())


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

    def test_frozen_reuses_private_tiny_but_complete_private_base_keeps_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tiny = root/'Axx'/'models'/'faster-whisper-tiny'
            base = tiny.with_name('faster-whisper-base')
            bundled = root/'unpacked'/'models'/'faster-whisper-tiny'
            required = ('model.bin','tokenizer.json','config.json','vocabulary.txt')
            for folder in (tiny, bundled):
                folder.mkdir(parents=True)
                for name in required:
                    (folder/name).touch()  # Discovery fixture only; never load these files as weights.
            with patch.dict('os.environ', {'LOCALAPPDATA': directory}), \
                    patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(root/'installed'/'axx-backend.exe')), \
                    patch.object(sys, '_MEIPASS', str(root/'unpacked'), create=True):
                self.assertEqual(model_path(), tiny.resolve())
                base.mkdir(parents=True)
                for name in required[:-1]:
                    (base/name).touch()
                self.assertEqual(model_path(), tiny.resolve(), 'Incomplete Base must not hide existing complete Tiny')
                (base/required[-1]).touch()
                self.assertEqual(model_path(), base.resolve())

    def test_frozen_missing_or_partial_local_model_never_downloads_or_starts_worker(self):
        for partial in (False, True):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if partial:
                    tiny = root/'Axx'/'models'/'faster-whisper-tiny'
                    tiny.mkdir(parents=True)
                    for name in ('model.bin', 'tokenizer.json', 'config.json'):
                        (tiny/name).touch()
                before = sorted(str(path.relative_to(root)) for path in root.rglob('*'))
                with patch.dict('os.environ', {'LOCALAPPDATA': directory}), \
                        patch.object(sys, 'frozen', True, create=True), \
                        patch.object(sys, 'executable', str(root/'installed'/'axx-backend.exe')), \
                        patch.object(sys, '_MEIPASS', str(root/'unpacked'), create=True), \
                        patch('socket.socket', side_effect=AssertionError('No network for unavailable local ASR')) as network, \
                        patch('backend.speech.offline_asr.spawn_managed_process', side_effect=AssertionError('No ASR worker')) as spawn, \
                        patch('backend.speech.offline_asr._load_worker_model', side_effect=AssertionError('No model load')) as load:
                    service = OfflineTranscriptionService(root/'state')
                    try:
                        self.assertIsNone(service.model_path)
                        status = service.status()
                        self.assertFalse(status['available'])
                        self.assertTrue(status['local_only'])
                        self.assertEqual(status['external_calls'], 0)
                        service.warm()
                        with self.assertRaises(SpeechError) as unavailable:
                            service.transcribe(AttributedTranscriptionTests.body('missing-local-model'))
                        self.assertEqual(unavailable.exception.code, 'NOT_SUPPORTED')
                        self.assertIsNone(service._worker)
                        self.assertEqual(service._requests, {})
                        network.assert_not_called(); spawn.assert_not_called(); load.assert_not_called()
                    finally:
                        service.close()
                self.assertEqual(sorted(str(path.relative_to(root)) for path in root.rglob('*')), before)

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
