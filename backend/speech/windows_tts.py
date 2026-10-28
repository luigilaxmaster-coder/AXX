"""Windows SAPI synthesis through an immutable script and private stdin JSON."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
import wave

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

class WindowsSpeechService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir) / 'speech'
        self.executable = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.available = os.name == 'nt' and self.executable.is_file()
        self._active = {}
        self._lock = threading.RLock()
        self._busy = threading.Lock()
        self._voices_lock = threading.RLock()
        self._cached_voices = None
        from .moss_tts import MossSpeechService
        from .piper_tts import PiperSpeechService
        self.moss = MossSpeechService(data_dir)
        self.piper = PiperSpeechService(data_dir)
        self.available = self.available or self.moss.available or self.piper.available
        self.moss.start_warmup()

    def close(self):
        self.cancel_active()
        self.moss.close()
        self.piper.close()

    def cancel_active(self):
        with self._lock:
            active = list(self._active.values())
        for process, job, cancelled in active:
            cancelled.set()
            terminate_process_tree(process, job)
        return len(active) + self.moss.cancel_active() + self.piper.cancel_active()

    def _run(self, request):
        if not self.available:
            raise SpeechError('NOT_SUPPORTED', 'Windows speech synthesis is unavailable')
        encoded_script = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
        child_env = os.environ.copy()
        child_env.pop('AXX_HOST_TOKEN', None)
        process, job = spawn_managed_process([str(self.executable), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded_script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env)
        cancelled, overflow = threading.Event(), threading.Event()
        run_id = str(uuid.uuid4())
        with self._lock:
            self._active[run_id] = (process, job, cancelled)
        buffers = [bytearray(), bytearray()]
        def collect(pipe, target):
            try:
                while True:
                    chunk = pipe.read(8192)
                    if not chunk: break
                    if len(target) + len(chunk) > 65536:
                        overflow.set(); break
                    target.extend(chunk)
            finally:
                pipe.close()
        def write_input():
            try:
                process.stdin.write(json.dumps(request, ensure_ascii=True).encode('ascii'))
                process.stdin.close()
            except (OSError, ValueError):
                pass
        threads = [threading.Thread(target=collect, args=(pipe, target), daemon=True)
                   for pipe, target in zip((process.stdout, process.stderr), buffers)]
        threads.append(threading.Thread(target=write_input, daemon=True))
        for thread in threads: thread.start()
        try:
            deadline = time.monotonic() + 20
            while process.poll() is None:
                if cancelled.is_set(): raise SpeechError('CANCELLED', 'Speech synthesis was cancelled')
                if overflow.is_set(): raise SpeechError('PROCESS_FAILURE', 'Speech process output exceeded its limit')
                if time.monotonic() >= deadline: raise SpeechError('DEADLINE_EXCEEDED', 'Speech synthesis exceeded its 20-second deadline')
                time.sleep(.025)
            for thread in threads: thread.join(timeout=.2)
            if cancelled.is_set(): raise SpeechError('CANCELLED', 'Speech synthesis was cancelled')
            if overflow.is_set() or process.returncode:
                raise SpeechError('PROCESS_FAILURE', 'Windows could not synthesize speech with the selected voice')
            try:
                result = json.loads(bytes(buffers[0]).decode('utf-8-sig'))
                if not isinstance(result, dict): raise ValueError()
                return result
            except (ValueError, UnicodeError):
                raise SpeechError('PROCESS_FAILURE', 'Invalid Windows speech response') from None
        finally:
            if process.poll() is None: terminate_process_tree(process, job)
            if job: job.close()
            cleanup_deadline = time.monotonic() + 1
            for thread in threads: thread.join(timeout=max(0,cleanup_deadline-time.monotonic()))
            with self._lock:
                self._active.pop(run_id, None)

    def voices(self):
        moss_voices = self.moss.voices() + self.piper.voices()
        if not self.executable.is_file():
            return {'engine': 'local', 'available': bool(moss_voices), 'voices': moss_voices,
                    'external_calls': 0, 'microphone_access': False}
        with self._voices_lock:
            if self._cached_voices is None:
                result = self._run({'action': 'voices'})
                voices = result.get('voices', [])
                if not isinstance(voices, list): raise SpeechError('PROCESS_FAILURE', 'Invalid installed voice list')
                self._cached_voices = [v for v in voices if isinstance(v,dict) and isinstance(v.get('name'),str)
                                       and isinstance(v.get('language'),str) and v.get('enabled') is True]
        return {'engine': 'local', 'available': bool(self._cached_voices or moss_voices), 'voices': self._cached_voices + moss_voices,
                'external_calls': 0, 'microphone_access': False}

    def synthesize(self, body):
        if isinstance(body, dict) and isinstance(body.get('voice'), str) and body['voice'].startswith('moss:'):
            return self.moss.synthesize(body)
        if isinstance(body, dict) and isinstance(body.get('voice'), str) and body['voice'].startswith('piper:'):
            return self.piper.synthesize(body)
        if set(body) - {'text','voice','rate','volume'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, voice, rate, volume = body.get('text'), body.get('voice'), body.get('rate',0), body.get('volume',100)
        if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', f'text must contain 1 to {MAX_TEXT} characters')
        if voice is not None and (not isinstance(voice,str) or len(voice)>160):
            raise SpeechError('INVALID_REQUEST', 'Invalid voice name')
        if type(rate) is not int or not -5 <= rate <= 5 or type(volume) is not int or not 0 <= volume <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid speech rate or volume')
        if not self._busy.acquire(blocking=False): raise SpeechError('BUSY', 'Speech synthesis is busy')
        try:
            installed = self.voices()
            if not installed['available']: raise SpeechError('NOT_SUPPORTED', 'No installed Windows voice is available')
            if voice and not any(v['name'] == voice for v in installed['voices']):
                raise SpeechError('INVALID_REQUEST', 'Requested voice is not installed')
            self.data_dir.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='tts-',dir=self.data_dir) as directory:
                output = Path(directory) / 'speech.wav'
                result = self._run({'action':'synthesize','text':text,'voice':voice,'rate':rate,'volume':volume,'output':str(output)})
                size = output.stat().st_size
                if not 44 < size <= MAX_WAV: raise SpeechError('INVALID_REQUEST', 'Synthesized audio exceeds its 3 MiB limit')
                with wave.open(str(output),'rb') as audio:
                    frames, sample_rate = audio.getnframes(), audio.getframerate()
                    if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or sample_rate!=16000:
                        raise SpeechError('PROCESS_FAILURE','Invalid synthesized PCM audio format')
                    duration = frames/sample_rate
                if not 0 < duration <= MAX_DURATION:
                    raise SpeechError('INVALID_REQUEST','Synthesized audio exceeds its 90-second duration limit')
                raw = output.read_bytes()
                return {'engine':'windows-sapi','mime':'audio/wav','audio_base64':base64.b64encode(raw).decode('ascii'),
                        'voice':result['voice'],'language':result['language'],'duration_seconds':round(duration,3),
                        'playback_verified':False,'external_calls':0,
                        'evidence':{'sha256':hashlib.sha256(raw).hexdigest(),'size':size,'frames':frames,
                                    'sample_rate':sample_rate,'script_sha256':SCRIPT_SHA256}}
        finally:
            self._busy.release()
