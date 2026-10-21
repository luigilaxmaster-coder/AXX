"""Isolated draft overlay: inert speech workers and one benign owned child per kind.

No microphone, recognition model, SAPI engine, speaker, GUI or application launch.
Run with python -B tests/test_speech_cancellation.py from this draft directory.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

sys.dont_write_bytecode = True
DRAFT = Path(__file__).resolve().parents[1]
PROJECT = DRAFT.parents[1]
STAGE = PROJECT / 'build' / 'phased-ux-20261020'
sys.path.insert(0, str(STAGE))

# Only these two modules are overlaid; stage source files remain untouched.
import backend.speech
from backend.inference.process_manager import spawn_managed_process as real_spawn


def load_overlay(name, filename):
    spec = importlib.util.spec_from_file_location(name, DRAFT / 'backend' / 'speech' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    setattr(backend.speech, name.rsplit('.', 1)[-1], module)
    return module


tts = load_overlay('backend.speech.windows_tts', 'windows_tts.py')
asr = load_overlay('backend.speech.offline_asr', 'offline_asr.py')
ASR_BODY = {'audio_base64': base64.b64encode(b'RIFF\0\0\0\0WAVE').decode(), 'mime': 'audio/wav', 'language': 'es'}
TTS_BODY = {'text': 'Inert fixture; never spoken.'}
VOICES = [{'name': 'INERT_FIXTURE', 'language': 'es-ES', 'enabled': True}]


class InertJob:
    def __init__(self):
        self.closed = False
        self.closes = 0

    def close(self):
        if not self.closed:
            self.closed = True
            self.closes += 1


class InertProcess:
    def __init__(self, *, complete=False, label='fixture', response=None):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(json.dumps(response or {'ok': True, 'result': {'text': label}}).encode())
        self.stderr = io.BytesIO()
        self.returncode = None
        self.polled = threading.Event()
        self.complete = threading.Event()
        self.waited = 0
        if complete:
            self.complete.set()

    def poll(self):
        self.polled.set()
        if self.complete.is_set() and self.returncode is None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        if not self.complete.wait(timeout):
            raise subprocess.TimeoutExpired('inert-fixture', timeout)
        self.waited += 1
        return self.poll()


class DeferredCancelLock:
    """Delay a captured cancel(A), without delaying A's owner or a new B."""
    def __init__(self, entered, release):
        self.lock, self.entered, self.release = threading.RLock(), entered, release

    def __enter__(self):
        if threading.current_thread().name == 'late-cancel-A':
            self.entered.set()
            if not self.release.wait(3):
                raise AssertionError('Late cancel barrier timed out')
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


class SpeechCancellationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='axx-speech-draft-'))
        self.stack.enter_context(patch.object(asr, 'model_path', return_value=Path(self.tmp) / 'unused-model'))
        self.asr = asr.OfflineTranscriptionService(self.tmp)
        self.stack.enter_context(patch.object(self.asr, 'status', return_value={'available': True}))
        self.tts = tts.WindowsSpeechService(self.tmp)
        self.tts.available = True
        self.tts._cached_voices = VOICES
        self.workers, self.pairs, self.barriers, self.terminated = [], [], [], []
        self.thread_errors = []
        self.stack.enter_context(patch.object(threading, 'excepthook', side_effect=self.thread_errors.append))
        self.asr_spawn = self.stack.enter_context(patch.object(asr, 'spawn_managed_process', side_effect=self.spawn_fixture))
        self.tts_spawn = self.stack.enter_context(patch.object(tts, 'spawn_managed_process', side_effect=self.spawn_fixture))
        self.stack.enter_context(patch.object(asr, 'terminate_process_tree', side_effect=self.terminate_fixture))
        self.stack.enter_context(patch.object(tts, 'terminate_process_tree', side_effect=self.terminate_fixture))
        self.popen = self.stack.enter_context(patch.object(subprocess, 'Popen', side_effect=AssertionError('No actual speech child permitted')))

    def tearDown(self):
        for barrier in self.barriers:
            barrier.set()
        for process, _ in self.pairs:
            process.complete.set()
        for worker in self.workers:
            worker.join(3)
        try:
            self.asr.close()
            self.tts.close()
            self.assertTrue(all(not worker.is_alive() for worker in self.workers), 'Fixture worker leaked')
            self.assertEqual(self.popen.call_count, 0)
            self.assertEqual(self.thread_errors, [], 'Unexpected exception in worker pipe thread')
        finally:
            self.stack.close()

    def event(self):
        event = threading.Event()
        self.barriers.append(event)
        return event

    def process(self, **kwargs):
        pair = InertProcess(**kwargs), InertJob()
        self.pairs.append(pair)
        return pair

    def spawn_fixture(self, *args, **kwargs):
        return self.process(complete=True)

    def terminate_fixture(self, process, job):
        self.terminated.append(process)
        process.returncode = -15
        process.complete.set()
        if job:
            job.close()

    def start(self, kind='transcription', operation_id='A'):
        service, body, method = ((self.asr, ASR_BODY, self.asr.transcribe) if kind == 'transcription'
                                 else (self.tts, TTS_BODY, self.tts.synthesize))
        outcome = {}
        def execute():
            try:
                outcome['result'] = method({**body, 'operation_id': operation_id})
            except Exception as error:
                outcome['error'] = getattr(error, 'code', type(error).__name__)
        worker = threading.Thread(target=execute, daemon=True)
        self.workers.append(worker)
        worker.start()
        return worker, outcome

    def join(self, worker):
        worker.join(3)
        self.assertFalse(worker.is_alive(), 'Fixture request did not retire')

    def retired(self, service):
        self.assertFalse(service._busy.locked())
        self.assertEqual(service.cancel_active(), 0)
        self.assertTrue(all(not run.active for run in service._operations.records.values()))
        if service.data_dir.exists():
            self.assertEqual(list(service.data_dir.iterdir()), [])

    def synth_fixture(self, request, run=None):
        with wave.open(request['output'], 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0\0' * 160)
        return {'voice': 'INERT_FIXTURE', 'language': 'es-ES'}

    def test_invalid_ids_and_body_shapes_are_rejected_before_admission(self):
        for invalid in (None, True, 1, '', 'x' * 129, '../escape', 'a b', 'é', 'x\n'):
            for service, body, method in ((self.asr, ASR_BODY, self.asr.transcribe), (self.tts, TTS_BODY, self.tts.synthesize)):
                with self.subTest(value=repr(invalid), service=type(service).__name__):
                    for call in (lambda: service.cancel(invalid), lambda: method({**body, 'operation_id': invalid})):
                        with self.assertRaises(tts.SpeechError) as error:
                            call()
                        self.assertEqual(error.exception.code, 'INVALID_REQUEST')
                    self.assertEqual(service._operations.records, {})
        for body in (None, [], 'x', {'unknown': True}):
            for method in (self.asr.transcribe, self.tts.synthesize):
                with self.assertRaises(tts.SpeechError) as error:
                    method(body)
                self.assertEqual(error.exception.code, 'INVALID_REQUEST')

    def test_cancel_before_admission_tombstones_both_kinds_and_never_spawns(self):
        for service, body, method, kind in ((self.asr, ASR_BODY, self.asr.transcribe, 'transcription'),
                                            (self.tts, TTS_BODY, self.tts.synthesize, 'synthesis')):
            result = service.cancel('early:A')
            self.assertEqual(result, {'kind': kind, 'operation_id': 'early:A', 'state': 'cancelled'})
            with self.assertRaises(tts.SpeechError) as error:
                method({**body, 'operation_id': 'early:A'})
            self.assertEqual(error.exception.code, 'CANCELLED')
            self.retired(service)
        self.assertEqual(self.asr_spawn.call_count + self.tts_spawn.call_count, 0)

    def test_legacy_and_explicit_success_ids_echo_and_cannot_replay(self):
        result = self.asr.transcribe({**ASR_BODY, 'operation_id': 'explicit:A-_.:1'})
        self.assertEqual((result['kind'], result['operation_id'], result['text']), ('transcription', 'explicit:A-_.:1', 'fixture'))
        self.assertRegex(result['input_sha256'], '^[0-9a-f]{64}$')
        self.assertEqual(self.asr.cancel('explicit:A-_.:1')['state'], 'already_finished')
        with self.assertRaises(tts.SpeechError) as error:
            self.asr.transcribe({**ASR_BODY, 'operation_id': 'explicit:A-_.:1'})
        self.assertEqual(error.exception.code, 'INVALID_REQUEST')
        legacy = self.asr.transcribe(ASR_BODY)
        self.assertRegex(legacy['operation_id'], '^[a-f0-9-]{36}$')
        with patch.object(self.tts, '_run', side_effect=self.synth_fixture):
            result = self.tts.synthesize({**TTS_BODY, 'operation_id': 'same-id'})
            legacy_tts = self.tts.synthesize(TTS_BODY)
        self.assertEqual((result['kind'], result['operation_id']), ('synthesis', 'same-id'))
        self.assertFalse(result['playback_verified'])
        self.assertRegex(legacy_tts['operation_id'], '^[a-f0-9-]{36}$')
        self.assertEqual(self.tts.cancel('same-id')['state'], 'already_finished')
        self.retired(self.asr)
        self.retired(self.tts)

    def test_cancellation_kind_is_isolated_even_with_the_same_id(self):
        self.asr.cancel('shared')
        with patch.object(self.tts, '_run', side_effect=self.synth_fixture):
            result = self.tts.synthesize({**TTS_BODY, 'operation_id': 'shared'})
        self.assertEqual(result['operation_id'], 'shared')
        self.assertEqual(self.tts.cancel('shared')['state'], 'already_finished')
        self.assertEqual(self.asr.cancel('shared')['state'], 'cancelled')

    def test_cancel_during_preparation_prevents_spawn_and_releases_busy(self):
        entered, release = threading.Event(), self.event()
        write_bytes = Path.write_bytes
        def blocked_write(path, value):
            if path.name == 'input.audio':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('Preparation barrier timed out')
            return write_bytes(path, value)
        with patch.object(Path, 'write_bytes', blocked_write):
            worker, outcome = self.start()
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.asr.cancel('A')['state'], 'cancel_requested')
            self.assertEqual(self.asr_spawn.call_count, 0)
            release.set()
            self.join(worker)
        self.assertEqual(outcome, {'error': 'CANCELLED'})
        self.assertEqual(self.asr_spawn.call_count, 0)
        self.retired(self.asr)

    def test_cancel_during_spawn_marks_published_run_and_reaps_late_child_both_kinds(self):
        for kind, service, spawn in (('transcription', self.asr, self.asr_spawn), ('synthesis', self.tts, self.tts_spawn)):
            with self.subTest(kind=kind):
                entered, release = threading.Event(), self.event()
                process, job = self.process()
                def blocked_spawn(*args, **kwargs):
                    entered.set()
                    if not release.wait(3):
                        raise AssertionError('Spawn barrier timed out')
                    return process, job
                spawn.side_effect = blocked_spawn
                worker, outcome = self.start(kind)
                self.assertTrue(entered.wait(1))
                self.assertEqual(service.cancel('A')['state'], 'cancel_requested')
                self.assertEqual(service.cancel('A')['state'], 'cancel_requested')
                self.assertNotIn(process, self.terminated)
                release.set()
                self.join(worker)
                self.assertEqual(outcome, {'error': 'CANCELLED'})
                self.assertEqual(self.terminated.count(process), 1)
                self.assertEqual(job.closes, 1)
                self.assertGreater(process.waited, 0)
                self.assertTrue(all(pipe.closed for pipe in (process.stdin, process.stdout, process.stderr)))
                self.assertEqual(service.cancel('A')['state'], 'cancelled')
                self.retired(service)

    def test_running_cancel_is_correlated_and_keeps_busy_until_owner_retires(self):
        for kind, service, spawn in (('transcription', self.asr, self.asr_spawn), ('synthesis', self.tts, self.tts_spawn)):
            with self.subTest(kind=kind):
                process, job = self.process()
                spawn.side_effect = None
                spawn.return_value = process, job
                worker, outcome = self.start(kind)
                self.assertTrue(process.polled.wait(1))
                self.assertEqual(service.cancel('different-ID')['state'], 'cancelled')
                self.assertIsNone(process.returncode)
                method, body = (service.transcribe, ASR_BODY) if kind == 'transcription' else (service.synthesize, TTS_BODY)
                with self.assertRaises(tts.SpeechError) as error:
                    method({**body, 'operation_id': 'B'})
                self.assertEqual(error.exception.code, 'BUSY')
                self.assertEqual(service.cancel('A')['state'], 'cancel_requested')
                self.join(worker)
                self.assertEqual(outcome, {'error': 'CANCELLED'})
                self.assertEqual(job.closes, 1)
                self.assertGreater(process.waited, 0)
                self.retired(service)

    def test_late_cancel_A_cannot_kill_or_clear_new_B(self):
        process_a, job_a = self.process()
        process_b, job_b = self.process(label='B')
        self.asr_spawn.side_effect = [(process_a, job_a), (process_b, job_b)]
        worker_a, outcome_a = self.start()
        self.assertTrue(process_a.polled.wait(1))
        entered, release = threading.Event(), self.event()
        self.asr._active.resources = DeferredCancelLock(entered, release)
        cancellations = []
        cancel = threading.Thread(target=lambda: cancellations.append(self.asr.cancel('A')), name='late-cancel-A', daemon=True)
        self.workers.append(cancel)
        cancel.start()
        self.assertTrue(entered.wait(1))
        self.join(worker_a)
        self.assertEqual(outcome_a, {'error': 'CANCELLED'})
        worker_b, outcome_b = self.start(operation_id='B')
        self.assertTrue(process_b.polled.wait(1))
        active_b = self.asr._active
        release.set()
        self.join(cancel)
        self.assertEqual(cancellations[0]['operation_id'], 'A')
        self.assertEqual(self.terminated, [process_a])
        self.assertIsNone(process_b.returncode)
        self.assertIs(self.asr._active, active_b)
        process_b.complete.set()
        self.join(worker_b)
        self.assertEqual(outcome_b['result']['text'], 'B')
        self.retired(self.asr)

    def test_cancel_between_worker_completion_and_commit_suppresses_result_both_kinds(self):
        for kind, service in (('transcription', self.asr), ('synthesis', self.tts)):
            with self.subTest(kind=kind), ExitStack() as stack:
                entered, release = threading.Event(), self.event()
                commit = service._operations.commit
                def blocked_commit(run, result):
                    entered.set()
                    if not release.wait(3):
                        raise AssertionError('Commit barrier timed out')
                    return commit(run, result)
                stack.enter_context(patch.object(service._operations, 'commit', side_effect=blocked_commit))
                if kind == 'synthesis':
                    stack.enter_context(patch.object(self.tts, '_run', side_effect=self.synth_fixture))
                worker, outcome = self.start(kind)
                self.assertTrue(entered.wait(1))
                self.assertEqual(service.cancel('A')['state'], 'cancel_requested')
                release.set()
                self.join(worker)
                self.assertEqual(outcome, {'error': 'CANCELLED'})
                self.retired(service)

    def test_synthesis_cancel_also_owns_uncached_voice_enumeration(self):
        self.tts._cached_voices = None
        process, job = self.process(response={'voices': VOICES})
        self.tts_spawn.side_effect = None
        self.tts_spawn.return_value = process, job
        worker, outcome = self.start('synthesis')
        self.assertTrue(process.polled.wait(1))
        self.tts.cancel('A')
        self.join(worker)
        self.assertEqual(outcome, {'error': 'CANCELLED'})
        self.assertIsNone(self.tts._cached_voices)
        self.assertEqual(self.tts_spawn.call_count, 1)
        self.retired(self.tts)

    def test_spawn_failure_releases_busy_and_new_id_can_run(self):
        self.asr_spawn.side_effect = OSError('Controlled spawn failure')
        with self.assertRaises(OSError):
            self.asr.transcribe({**ASR_BODY, 'operation_id': 'failed'})
        self.retired(self.asr)
        self.asr_spawn.side_effect = self.spawn_fixture
        self.assertEqual(self.asr.transcribe({**ASR_BODY, 'operation_id': 'new'})['text'], 'fixture')

    def test_worker_error_envelope_preserves_typed_error_and_reaps_child(self):
        process, job = self.process(complete=True, response={'ok': False, 'error': {'code': 'INVALID_REQUEST', 'message': 'Inert rejection'}})
        process.returncode = 1
        self.asr_spawn.side_effect = None
        self.asr_spawn.return_value = process, job
        with self.assertRaises(tts.SpeechError) as error:
            self.asr.transcribe({**ASR_BODY, 'operation_id': 'rejected'})
        self.assertEqual(error.exception.code, 'INVALID_REQUEST')
        self.assertGreater(process.waited, 0)
        self.retired(self.asr)

    def test_failed_reap_retains_ownership_and_busy_until_targeted_cleanup(self):
        with patch.object(tts, '_reap_speech_worker', side_effect=tts.SpeechError('PROCESS_FAILURE', 'Inert reaping failure')):
            with self.assertRaises(tts.SpeechError) as error:
                self.asr.transcribe({**ASR_BODY, 'operation_id': 'retained'})
        self.assertEqual(error.exception.code, 'PROCESS_FAILURE')
        self.assertTrue(self.asr._busy.locked())
        retained = self.asr._operations.records['retained']
        self.assertTrue(retained.active)
        self.assertIsNotNone(retained.process)
        self.assertEqual(self.asr.cancel('retained')['state'], 'cancelled')
        self.retired(self.asr)
        self.assertEqual(self.asr.transcribe({**ASR_BODY, 'operation_id': 'after-cleanup'})['text'], 'fixture')

    def test_shutdown_compatibility_cancels_owned_active_requests(self):
        process, job = self.process()
        self.asr_spawn.side_effect = None
        self.asr_spawn.return_value = process, job
        worker, outcome = self.start()
        self.assertTrue(process.polled.wait(1))
        self.assertEqual(self.asr.cancel_active(), 1)
        self.join(worker)
        self.assertEqual(outcome, {'error': 'CANCELLED'})
        self.retired(self.asr)

    def test_input_validation_and_static_script_are_preserved(self):
        for body in ({**TTS_BODY, 'text': 'x' * 1201}, {**TTS_BODY, 'rate': True},
                     {**TTS_BODY, 'volume': -1}, {**TTS_BODY, 'voice': 'missing'}):
            with self.assertRaises(tts.SpeechError) as error:
                self.tts.synthesize(body)
            self.assertEqual(error.exception.code, 'INVALID_REQUEST')
        for body in ({'audio_base64': 'bad', 'mime': 'audio/wav'},
                     {**ASR_BODY, 'mime': 'audio/ogg'}, {**ASR_BODY, 'task': 'arbitrary-task'}):
            with self.assertRaises(tts.SpeechError) as error:
                self.asr.transcribe(body)
            self.assertEqual(error.exception.code, 'INVALID_REQUEST')
        source = (STAGE / 'backend' / 'speech' / 'windows_tts.py').read_text(encoding='utf-8')
        self.assertIn(tts.SCRIPT, source)
        self.assertEqual(self.asr_spawn.call_count + self.tts_spawn.call_count, 0)


class OperationBoundsTests(unittest.TestCase):
    def test_cap_does_not_evict_live_tombstones_or_active_runs(self):
        registry = tts._SpeechOperations('transcription')
        with patch.object(tts, 'MAX_OPERATIONS', 2):
            registry.cancel('early', lambda *_: self.fail('No worker exists'))
            run = registry.admit('active')
            run.updated -= tts.OPERATION_TTL_SECONDS + 1
            with self.assertRaises(tts.SpeechError) as error:
                registry.cancel('overflow', lambda *_: None)
            self.assertEqual(error.exception.code, 'BUSY')
            self.assertEqual(set(registry.records), {'early', 'active'})
            with self.assertRaises(tts.SpeechError) as error:
                registry.admit('early')
            self.assertEqual(error.exception.code, 'CANCELLED')
            registry.retire(run)

    def test_expired_terminal_records_are_pruned_but_cancellation_remains_bounded(self):
        registry = tts._SpeechOperations('synthesis')
        registry.cancel('expired', lambda *_: None)
        registry.records['expired'].updated -= tts.OPERATION_TTL_SECONDS + 1
        registry.cancel('new', lambda *_: None)
        self.assertNotIn('expired', registry.records)
        self.assertEqual(len(registry.records), 1)

    def test_commit_and_cancel_have_one_terminal_ordering(self):
        registry = tts._SpeechOperations('transcription')
        run = registry.admit('finished')
        result = registry.commit(run, {'text': 'fixture'})
        self.assertEqual(registry.cancel('finished', lambda *_: self.fail('Finished worker cannot be killed'))['state'], 'already_finished')
        self.assertEqual(result['text'], 'fixture')
        cancelled = registry.admit('cancelled')
        registry.cancel('cancelled', lambda *_: None)
        with self.assertRaises(tts.SpeechError) as error:
            registry.commit(cancelled, {'text': 'must not publish'})
        self.assertEqual(error.exception.code, 'CANCELLED')
        registry.retire(cancelled)


class OwnedBenignProcessTests(unittest.TestCase):
    def test_cancel_reaps_actual_owned_benign_children_for_both_kinds(self):
        # Replace both speech executables with a known sleeping Python child.
        # This exercises process ownership/reaping, never ASR/SAPI/audio.
        with tempfile.TemporaryDirectory(prefix='axx-speech-owned-child-') as directory:
            for kind, module in (('transcription', asr), ('synthesis', tts)):
                with self.subTest(kind=kind), ExitStack() as stack:
                    thread_errors = []
                    stack.enter_context(patch.object(threading, 'excepthook', side_effect=thread_errors.append))
                    service = (asr.OfflineTranscriptionService(directory) if kind == 'transcription'
                               else tts.WindowsSpeechService(directory))
                    if kind == 'transcription':
                        stack.enter_context(patch.object(service, 'status', return_value={'available': True}))
                    else:
                        service.available, service._cached_voices = True, VOICES
                    children, outcome = [], {}
                    spawned = threading.Event()
                    def benign_spawn(command, **kwargs):
                        pair = real_spawn([sys.executable, '-c', 'import sys,time;sys.stdin.buffer.read();time.sleep(30)'], **kwargs)
                        children.append(pair)
                        spawned.set()
                        return pair
                    stack.enter_context(patch.object(module, 'spawn_managed_process', side_effect=benign_spawn))
                    body, method = (ASR_BODY, service.transcribe) if kind == 'transcription' else (TTS_BODY, service.synthesize)
                    def execute():
                        try:
                            outcome['result'] = method({**body, 'operation_id': 'owned-benign'})
                        except Exception as error:
                            outcome['error'] = getattr(error, 'code', type(error).__name__)
                    worker = threading.Thread(target=execute, daemon=True)
                    try:
                        worker.start()
                        self.assertTrue(spawned.wait(3))
                        self.assertEqual(service.cancel('owned-benign')['operation_id'], 'owned-benign')
                        worker.join(5)
                        self.assertFalse(worker.is_alive())
                        self.assertEqual(outcome, {'error': 'CANCELLED'})
                        self.assertEqual(thread_errors, [])
                        self.assertEqual(len(children), 1)
                        self.assertIsNotNone(children[0][0].poll())
                        self.assertEqual(service.cancel('owned-benign')['state'], 'cancelled')
                        self.assertFalse(service._busy.locked())
                        self.assertFalse(any(service.data_dir.iterdir()))
                    finally:
                        service.close()
                        for child, job in children:
                            if child.poll() is None:
                                module.terminate_process_tree(child, job)
                            child.wait(timeout=3)
                            if job:
                                job.close()
                        worker.join(3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
