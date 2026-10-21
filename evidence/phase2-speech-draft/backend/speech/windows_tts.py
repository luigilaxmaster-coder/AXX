"""Windows SAPI synthesis through an immutable script and private stdin JSON."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from typing import Literal, TypedDict

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree

MAX_TEXT = 1200
MAX_WAV = 3 * 1024 * 1024
MAX_DURATION = 90
SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
$req = [Console]::In.ReadToEnd() | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($synth.GetInstalledVoices() | ForEach-Object {
    @{ name=$_.VoiceInfo.Name; language=$_.VoiceInfo.Culture.Name; enabled=$_.Enabled }
  })
  if ($req.action -eq 'voices') {
    @{ voices=$voices } | ConvertTo-Json -Compress -Depth 5
  } elseif ($req.action -eq 'synthesize') {
    if ($req.voice) {
      if (-not ($voices | Where-Object { $_.name -ceq $req.voice -and $_.enabled })) { throw 'Requested voice is not installed' }
      $synth.SelectVoice([string]$req.voice)
    }
    $synth.Rate = [int]$req.rate
    $synth.Volume = [int]$req.volume
    $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile([string]$req.output, $format)
    $synth.Speak([string]$req.text)
    $synth.SetOutputToNull()
    @{ voice=$synth.Voice.Name; language=$synth.Voice.Culture.Name } | ConvertTo-Json -Compress
  } else { throw 'Unsupported speech operation' }
} finally { $synth.Dispose() }
'''
SCRIPT_SHA256 = hashlib.sha256(SCRIPT.encode('utf-8')).hexdigest()

class SpeechError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class CancellationResult(TypedDict):
    kind: Literal['transcription', 'synthesis']
    operation_id: str
    state: Literal['cancelled', 'cancel_requested', 'already_finished']


OPERATION_TTL_SECONDS = 300
MAX_OPERATIONS = 256
_OPERATION_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', re.ASCII)


def _validate_operation_id(value):
    if not isinstance(value, str) or _OPERATION_ID.fullmatch(value) is None:
        raise SpeechError('INVALID_REQUEST', 'operation_id must contain 1 to 128 safe ASCII characters')
    return value


def _body_operation_id(body):
    return _validate_operation_id(body['operation_id']) if 'operation_id' in body else str(uuid.uuid4())


class _SpeechOperation:
    """One admitted ID owns its event and children until bounded cleanup ends."""
    def __init__(self, operation_id):
        self.operation_id = operation_id
        self.cancelled = threading.Event()
        self.resources = threading.RLock()
        self.process = self.job = None
        self.active = True
        self.finished = False
        self.owner_done = False
        self.busy = None
        self.busy_released = False
        self.updated = time.monotonic()


class _SpeechOperations:
    """Fail-closed bounded admission, early tombstones and atomic result commit."""
    def __init__(self, kind):
        self.kind = kind
        self.lock = threading.RLock()
        self.records = {}

    def _prune(self):
        cutoff = time.monotonic() - OPERATION_TTL_SECONDS
        for key, run in tuple(self.records.items()):
            if not run.active and run.updated < cutoff:
                del self.records[key]

    def _reserve(self):
        self._prune()
        if len(self.records) >= MAX_OPERATIONS:
            raise SpeechError('BUSY', 'Speech operation capacity is temporarily exhausted')

    def admit(self, operation_id, busy=None):
        with self.lock:
            self._prune()
            previous = self.records.get(operation_id)
            if previous is not None:
                if previous.cancelled.is_set():
                    raise SpeechError('CANCELLED', 'Speech operation was cancelled')
                if previous.active:
                    raise SpeechError('BUSY', 'Speech operation is already active')
                raise SpeechError('INVALID_REQUEST', 'operation_id has already finished; use a new ID')
            self._reserve()
            if busy is not None and not busy.acquire(blocking=False):
                raise SpeechError('BUSY', 'Speech service is busy')
            run = _SpeechOperation(operation_id)
            run.busy = busy
            self.records[operation_id] = run
            return run

    @staticmethod
    def check(run):
        if run.cancelled.is_set():
            raise SpeechError('CANCELLED', 'Speech operation was cancelled')

    def commit(self, run, result):
        # Cancellation and result publication have a single ordering point.
        with self.lock:
            self.check(run)
            run.finished, run.active, run.updated = True, False, time.monotonic()
            result['operation_id'], result['kind'] = run.operation_id, self.kind
            return result

    def retire(self, run):
        with self.lock:
            run.owner_done = True
            self._retire_reaped(run)
            run.updated = time.monotonic()

    @staticmethod
    def _retire_reaped(run):
        if run.process is not None:
            # Fail closed if Windows refuses termination/reaping: keep ownership
            # and admission until a later targeted cancel can complete cleanup.
            run.cancelled.set()
            run.active = True
            return
        run.active = False
        if run.busy is not None and not run.busy_released:
            run.busy.release()
            run.busy_released = True

    def cancel(self, operation_id, terminate) -> CancellationResult:
        operation_id = _validate_operation_id(operation_id)
        with self.lock:
            self._prune()
            run = self.records.get(operation_id)
            if run is None:
                self._reserve()
                run = _SpeechOperation(operation_id)
                run.active = False
                run.cancelled.set()
                self.records[operation_id] = run
            elif run.finished or (not run.active and not run.cancelled.is_set()):
                return {'kind': self.kind, 'operation_id': operation_id, 'state': 'already_finished'}
            else:
                run.cancelled.set()
            # A cancellation that arrives during spawn marks the published run.
            # It never changes another ID, nor relies on a later global lookup.
        with run.resources:
            if run.process is not None and run.process.poll() is None:
                terminate(run.process, run.job)
            if run.process is not None and run.owner_done:
                _reap_speech_worker(run.process, run.job)
                run.process = run.job = None
        with self.lock:
            if run.owner_done:
                self._retire_reaped(run)
            state = 'cancel_requested' if run.active else 'cancelled'
            return {'kind': self.kind, 'operation_id': operation_id, 'state': state}

    def cancel_active(self, terminate):
        with self.lock:
            active = [run.operation_id for run in self.records.values() if run.active]
        for operation_id in active:
            self.cancel(operation_id, terminate)
        return len(active)


def _close_speech_pipe(pipe):
    try:
        pipe.close()
    except (OSError, ValueError):
        # A killed child can make a buffered Windows pipe fail while flushing.
        pass


def _reap_speech_worker(process, job):
    if job:
        job.close()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            raise SpeechError('PROCESS_FAILURE', 'Speech worker could not be reaped') from None


def _run_speech_worker(command, request, run, *, env, timeout, output_limit, spawn, terminate, cwd=None,
                       allow_error_envelope=False):
    """Bounded private pipes; cancellation owns only this worker and reaps it."""
    _SpeechOperations.check(run)
    kwargs = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if cwd is not None:
        kwargs['cwd'] = cwd
    process, job = spawn(command, **kwargs)
    overflow = threading.Event()
    buffers, threads = [bytearray(), bytearray()], []
    unowned_pipes = [process.stdout, process.stderr, process.stdin]

    def collect(pipe, target):
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                if len(target) + len(chunk) > output_limit:
                    overflow.set()
                    break
                target.extend(chunk)
        except (OSError, ValueError):
            pass
        finally:
            _close_speech_pipe(pipe)

    def write_input():
        try:
            process.stdin.write(json.dumps(request, ensure_ascii=True).encode('ascii'))
        except (OSError, ValueError):
            pass
        finally:
            _close_speech_pipe(process.stdin)

    try:
        with run.resources:
            run.process, run.job = process, job
        _SpeechOperations.check(run)
        readers = [threading.Thread(target=collect, args=(pipe, target), daemon=True)
                   for pipe, target in zip((process.stdout, process.stderr), buffers)]
        readers.append(threading.Thread(target=write_input, daemon=True))
        for thread, pipe in zip(readers, tuple(unowned_pipes)):
            thread.start()
            threads.append(thread)
            unowned_pipes.remove(pipe)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            _SpeechOperations.check(run)
            if overflow.is_set():
                raise SpeechError('INVALID_RESPONSE', 'Speech process output exceeded its limit')
            if time.monotonic() >= deadline:
                raise SpeechError('DEADLINE_EXCEEDED', 'Speech process exceeded its deadline')
            time.sleep(.025)
        for thread in threads:
            thread.join(timeout=.2)
        _SpeechOperations.check(run)
        if overflow.is_set():
            raise SpeechError('INVALID_RESPONSE', 'Speech process output exceeded its limit')
        try:
            result = json.loads(bytes(buffers[0]).decode('utf-8-sig'))
            if not isinstance(result, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise SpeechError('PROCESS_FAILURE', 'Invalid speech worker response') from None
        if process.returncode and not (allow_error_envelope and result.get('ok') is False):
            raise SpeechError('PROCESS_FAILURE', 'Speech worker failed')
        return result
    finally:
        try:
            with run.resources:
                try:
                    if process.poll() is None:
                        terminate(process, job)
                finally:
                    # Keep ownership if reaping fails; never report cancelled
                    # or release service admission while this child is live.
                    _reap_speech_worker(process, job)
                    run.process = run.job = None
        finally:
            cleanup_deadline = time.monotonic() + 1
            for thread in threads:
                thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
            for pipe in unowned_pipes:
                _close_speech_pipe(pipe)

class WindowsSpeechService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir) / 'speech'
        self.executable = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.available = os.name == 'nt' and self.executable.is_file()
        self._operations = _SpeechOperations('synthesis')
        self._busy = threading.Lock()
        self._voices_lock = threading.RLock()
        self._cached_voices = None

    def close(self):
        self.cancel_active()

    def cancel(self, operation_id) -> CancellationResult:
        return self._operations.cancel(operation_id, terminate_process_tree)

    def cancel_active(self):
        """Explicit shutdown compatibility; request cancellation must use cancel(id)."""
        return self._operations.cancel_active(terminate_process_tree)

    def _run(self, request, run=None):
        owned = run is None
        if owned:
            run = self._operations.admit(str(uuid.uuid4()))
        try:
            self._operations.check(run)
            if not self.available:
                raise SpeechError('NOT_SUPPORTED', 'Windows speech synthesis is unavailable')
            encoded_script = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
            child_env = os.environ.copy()
            child_env.pop('AXX_HOST_TOKEN', None)
            result = _run_speech_worker(
                [str(self.executable), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded_script],
                request, run, env=child_env, timeout=20, output_limit=65536,
                spawn=spawn_managed_process, terminate=terminate_process_tree)
            self._operations.check(run)
            return self._operations.commit(run, result) if owned else result
        finally:
            if owned:
                self._operations.retire(run)

    def voices(self, _run=None):
        with self._voices_lock:
            if _run is not None:
                self._operations.check(_run)
            if self._cached_voices is None:
                result = self._run({'action': 'voices'}, _run)
                voices = result.get('voices', [])
                if not isinstance(voices, list):
                    raise SpeechError('PROCESS_FAILURE', 'Invalid installed voice list')
                with self._operations.lock:
                    if _run is not None:
                        self._operations.check(_run)
                    self._cached_voices = [v for v in voices if isinstance(v, dict) and isinstance(v.get('name'), str)
                                           and isinstance(v.get('language'), str) and v.get('enabled') is True]
        return {'engine': 'windows-sapi', 'available': bool(self._cached_voices), 'voices': self._cached_voices,
                'external_calls': 0, 'microphone_access': False}

    def synthesize(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume', 'operation_id'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        operation_id = _body_operation_id(body)
        text, voice, rate, volume = body.get('text'), body.get('voice'), body.get('rate', 0), body.get('volume', 100)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', f'text must contain 1 to {MAX_TEXT} characters')
        if voice is not None and (not isinstance(voice, str) or len(voice) > 160):
            raise SpeechError('INVALID_REQUEST', 'Invalid voice name')
        if type(rate) is not int or not -5 <= rate <= 5 or type(volume) is not int or not 0 <= volume <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid speech rate or volume')
        run = self._operations.admit(operation_id, self._busy)
        try:
            self._operations.check(run)
            installed = self.voices(_run=run)
            if not installed['available']:
                raise SpeechError('NOT_SUPPORTED', 'No installed Windows voice is available')
            if voice and not any(v['name'] == voice for v in installed['voices']):
                raise SpeechError('INVALID_REQUEST', 'Requested voice is not installed')
            self._operations.check(run)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='tts-', dir=self.data_dir) as directory:
                output = Path(directory) / 'speech.wav'
                result = self._run({'action': 'synthesize', 'text': text, 'voice': voice,
                                    'rate': rate, 'volume': volume, 'output': str(output)}, run)
                self._operations.check(run)
                size = output.stat().st_size
                if not 44 < size <= MAX_WAV:
                    raise SpeechError('INVALID_REQUEST', 'Synthesized audio exceeds its 3 MiB limit')
                with wave.open(str(output), 'rb') as audio:
                    frames, sample_rate = audio.getnframes(), audio.getframerate()
                    if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or sample_rate != 16000:
                        raise SpeechError('PROCESS_FAILURE', 'Invalid synthesized PCM audio format')
                    duration = frames / sample_rate
                if not 0 < duration <= MAX_DURATION:
                    raise SpeechError('INVALID_REQUEST', 'Synthesized audio exceeds its 90-second duration limit')
                raw = output.read_bytes()
                response = {'engine': 'windows-sapi', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                            'voice': result['voice'], 'language': result['language'], 'duration_seconds': round(duration, 3),
                            'playback_verified': False, 'external_calls': 0,
                            'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': size, 'frames': frames,
                                         'sample_rate': sample_rate, 'script_sha256': SCRIPT_SHA256}}
            # Cleanup temporary data before the atomic result/cancellation commit.
            return self._operations.commit(run, response)
        finally:
            self._operations.retire(run)
