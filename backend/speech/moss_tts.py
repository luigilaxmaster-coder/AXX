"""Opt-in local MOSS-TTS-Nano ONNX voice source; model assets stay outside Axx."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
import wave

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .windows_tts import SpeechError


class MossSpeechService:
    PERSONAL_VOICES = (
        ('axx-alba', 'Axx Alba'),
        ('axx-nova', 'Axx Nova'),
        ('axx-aura', 'Axx Aura'),
        ('axx-titan', 'Axx Titán'),
    )
    FALLBACK_VOICES = (
        ('voz_referencia', 'Axx Base'),
        ('voz_referencia_completo', 'Axx Base Plus'),
    )

    def __init__(self, data_dir: Path):
        self.root = Path(os.environ.get('AXX_MOSS_TTS_ROOT', Path.home() / 'Downloads' / 'tts nano' / 'MOSS-TTS-Nano'))
        self.python = self.root / '.venv' / 'Scripts' / 'python.exe'
        self.script = (Path(sys._MEIPASS) / 'speech' / 'moss_worker.py'
                       if getattr(sys, 'frozen', False) else Path(__file__).with_name('moss_worker.py'))
        self.models = self.root / 'models'
        self.samples = self.root / 'samples'
        self.data_dir = Path(data_dir) / 'speech'
        self.output_dir = self.data_dir / 'generated'
        self.personal_samples = self.data_dir / 'voices'
        self._busy = threading.Lock()
        self._active = None
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._worker = None
        self._warm_started = False
        self._cancelled = threading.Event()

    @property
    def available(self):
        return (self.python.is_file() and self.script.is_file()
                and (self.models / 'MOSS-TTS-Nano-100M-ONNX').is_dir()
                and (self.models / 'MOSS-Audio-Tokenizer-Nano-ONNX').is_dir())

    def _voice_paths(self):
        if not self.available:
            return {}
        personal = {'moss:' + name: (self.personal_samples / (name + '.wav'), label)
                    for name, label in self.PERSONAL_VOICES
                    if (self.personal_samples / (name + '.wav')).is_file()}
        if personal:
            return personal
        return {'moss:' + name: (self.samples / (name + '.wav'), label)
                for name, label in self.FALLBACK_VOICES
                if (self.samples / (name + '.wav')).is_file()}

    def voices(self):
        voices = [{'name': name, 'language': 'es-DO / en-US', 'enabled': True,
                 'engine': 'moss-onnx', 'label': label + ' · Español / English'}
                for name, (_, label) in self._voice_paths().items()]
        if voices:
            self.start_warmup()
        return voices

    def start_warmup(self):
        with self._lock:
            if self._warm_started or self._worker:
                return
            self._warm_started = True
        def warm():
            try:
                self._ensure_worker()
            except (OSError, SpeechError):
                pass  # A later synthesis can retry and surface its error.
        threading.Thread(target=warm, name='axx-moss-warmup', daemon=True).start()

    def _stop_worker(self):
        with self._lock:
            worker, self._worker, self._active = self._worker, None, None
        if worker:
            process, job, _ = worker
            terminate_process_tree(process, job)
            if job:
                job.close()

    def close(self):
        self._cancelled.set()
        self._stop_worker()

    def _ensure_worker(self):
        with self._start_lock:
            with self._lock:
                worker = self._worker
            if worker and worker[0].poll() is None:
                return worker
            if worker:
                self._stop_worker()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.pop('AXX_HOST_TOKEN', None)
            args = [str(self.python), '-u', str(self.script), str(self.models),
                    str(self.personal_samples), str(self.output_dir)]
            process, job = spawn_managed_process(args, cwd=str(self.root), env=env,
                                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                 stderr=subprocess.DEVNULL)
            responses = queue.Queue()
            worker = (process, job, responses)
            with self._lock:
                self._worker = worker
            def receive():
                try:
                    for line in process.stdout:
                        try:
                            responses.put(json.loads(line))
                        except (ValueError, UnicodeError):
                            responses.put(None)
                finally:
                    responses.put(None)
                    process.stdout.close()
            threading.Thread(target=receive, name='axx-moss-results', daemon=True).start()
            try:
                ready = responses.get(timeout=90)
                if not isinstance(ready, dict) or ready.get('ready') is not True or process.poll() is not None:
                    raise SpeechError('PROCESS_FAILURE', 'MOSS voice model failed to start')
                return worker
            except queue.Empty:
                self._stop_worker()
                raise SpeechError('DEADLINE_EXCEEDED', 'MOSS voice model loading exceeded 90 seconds')
            except SpeechError:
                self._stop_worker()
                raise

    def cancel_active(self):
        with self._lock:
            active = self._active
        if active:
            self._cancelled.set()
            self._stop_worker()
            return 1
        return 0

    def synthesize(self, body):
        if set(body) - {'text', 'voice', 'rate', 'volume'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, voice = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 220 or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 220 characters')
        voice_paths = self._voice_paths()
        if not isinstance(voice, str) or voice not in voice_paths:
            raise SpeechError('NOT_SUPPORTED', 'The selected local MOSS voice is unavailable')
        if type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid voice speed')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid volume')
        if not self._busy.acquire(blocking=False):
            raise SpeechError('BUSY', 'MOSS is generating another voice segment')
        try:
            self._cancelled.clear()
            process, job, responses = self._ensure_worker()
            request_id = uuid.uuid4().hex
            output = self.output_dir / f'{request_id}.wav'
            with self._lock:
                self._active = (process, job)
            try:
                request = json.dumps({'id': request_id, 'voice': voice, 'text': text}, ensure_ascii=True)
                process.stdin.write((request + '\n').encode('ascii'))
                process.stdin.flush()
                deadline = time.monotonic() + 120
                while True:
                    if self._cancelled.is_set():
                        raise SpeechError('CANCELLED', 'MOSS synthesis was cancelled')
                    if time.monotonic() >= deadline:
                        raise SpeechError('DEADLINE_EXCEEDED', 'MOSS synthesis exceeded 120 seconds')
                    try:
                        response = responses.get(timeout=.1)
                    except queue.Empty:
                        if process.poll() is not None:
                            raise SpeechError('PROCESS_FAILURE', 'MOSS voice worker stopped')
                        continue
                    if not isinstance(response, dict) or response.get('id') != request_id or response.get('ok') is not True:
                        raise SpeechError('PROCESS_FAILURE', 'MOSS could not synthesize the selected voice')
                    if not output.is_file():
                        raise SpeechError('PROCESS_FAILURE', 'MOSS did not produce audio')
                    size = output.stat().st_size
                    if not 44 < size <= 12 * 1024 * 1024:
                        raise SpeechError('PROCESS_FAILURE', 'MOSS output size is invalid')
                    with wave.open(str(output), 'rb') as audio:
                        frames, rate, channels = audio.getnframes(), audio.getframerate(), audio.getnchannels()
                        if channels not in (1, 2) or audio.getsampwidth() != 2 or rate not in (24000, 48000):
                            raise SpeechError('PROCESS_FAILURE', 'MOSS returned an unsupported WAV format')
                        duration = frames / rate
                    if not 0 < duration <= 90:
                        raise SpeechError('PROCESS_FAILURE', 'MOSS output duration is invalid')
                    raw = output.read_bytes()
                    return {'engine': 'moss-onnx', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                            'voice': voice, 'language': 'es-DO/en-US', 'duration_seconds': round(duration, 3),
                            'playback_verified': False, 'external_calls': 0,
                            'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': size,
                                         'frames': frames, 'channels': channels,
                                         'sample_rate': rate, 'model_source': 'local_onnx'}}
            except (OSError, SpeechError):
                self._stop_worker()
                raise
            finally:
                output.unlink(missing_ok=True)
                with self._lock:
                    self._active = None
        finally:
            self._busy.release()
