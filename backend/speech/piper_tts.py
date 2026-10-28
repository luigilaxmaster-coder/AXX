"""Optional local Piper voices kept outside the published desktop artifact."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
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


LOG = logging.getLogger(__name__)
MODELS = {
    'piper:es_ES-carlfm-x_low': ('es_ES-carlfm-x_low', 'Piper · España · CarlFM · ligera', 'es-ES'),
    'piper:es_MX-ald-medium': ('es_MX-ald-medium', 'Piper · México · Ald · media', 'es-MX'),
}
MAX_AUDIO = 12 * 1024 * 1024


class PiperSpeechService:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / 'speech' / 'piper'
        self.python = self.root / '.venv' / 'Scripts' / 'python.exe'
        self.models = self.root / 'models'
        self.script = (Path(sys._MEIPASS) / 'speech' / 'piper_worker.py'
                       if getattr(sys, 'frozen', False) else Path(__file__).parents[2] / 'resources' / 'piper_worker.py')
        self._lock = threading.RLock()
        self._busy = threading.Lock()
        self._worker = None
        self._prepared = set()
        self._preparing = None
        self._last_error = None
        self._cancelled = threading.Event()

    def _models(self):
        if not self.python.is_file() or not self.script.is_file():
            return {}
        return {uri: (name, label, language) for uri, (name, label, language) in MODELS.items()
                if (self.models / (name + '.onnx')).is_file()
                and (self.models / (name + '.onnx.json')).is_file()}

    @property
    def available(self):
        return bool(self._models())

    def voices(self):
        return [{'name': uri, 'label': label, 'language': language, 'enabled': True,
                 'engine': 'piper-onnx', 'streaming': False}
                for uri, (_, label, language) in self._models().items()]

    def status(self):
        with self._lock:
            return {'available': self.available, 'ready': bool(self._worker),
                    'preparing_voice': self._preparing, 'prepared_voices': sorted(self._prepared),
                    'error': self._last_error}

    def _stop(self):
        with self._lock:
            worker, self._worker = self._worker, None
            self._prepared.clear()
        if worker:
            process, job, _ = worker
            terminate_process_tree(process, job)
            if job: job.close()
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    try: pipe.close()
                    except (OSError, ValueError): pass

    def close(self):
        self._stop()

    def cancel_active(self):
        if not self._busy.locked():
            return 0
        self._cancelled.set()
        self._stop()
        return 1

    def _request(self, uri, text=None, rate=0, volume=100, timeout=30):
        name = self._models().get(uri, (None,))[0]
        if not name:
            raise SpeechError('NOT_SUPPORTED', 'La voz Piper seleccionada no está instalada')
        if self._cancelled.is_set():
            raise SpeechError('CANCELLED', 'Piper speech was cancelled')
        if not self._worker or self._worker[0].poll() is not None:
            self._stop()
            try:
                process, job = spawn_managed_process(
                    [str(self.python), '-u', str(self.script), str(self.models)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env={k: os.environ[k] for k in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'USERPROFILE') if k in os.environ})
            except OSError:
                raise SpeechError('PROCESS_FAILURE', 'No se pudo iniciar Piper') from None
            responses = queue.Queue()
            def receive():
                try:
                    for line in process.stdout:
                        if len(line) > 17 * 1024 * 1024: break
                        try: responses.put(json.loads(line))
                        except ValueError: responses.put({'error': 'Invalid Piper response'})
                except (OSError, ValueError):
                    pass
                finally:
                    responses.put({'error': 'Piper process stopped'})
            threading.Thread(target=receive, name='axx-piper-output', daemon=True).start()
            with self._lock: self._worker = process, job, responses
            try:
                ready = responses.get(timeout=15)
                if ready.get('ready') is not True: raise ValueError('Piper did not start')
            except (queue.Empty, ValueError):
                self._stop()
                raise SpeechError('PROCESS_FAILURE', 'No se pudo iniciar Piper') from None
        if self._cancelled.is_set() or not self._worker:
            self._stop()
            raise SpeechError('CANCELLED', 'Piper speech was cancelled')
        process, _, responses = self._worker
        request_id = uuid.uuid4().hex
        request = {'id': request_id, 'voice': name, 'prepare': text is None}
        if text is not None: request.update(text=text, rate=rate, volume=volume)
        try:
            process.stdin.write((json.dumps(request, ensure_ascii=True) + '\n').encode('ascii'))
            process.stdin.flush()
            response = responses.get(timeout=timeout)
            if not isinstance(response, dict) or response.get('id') != request_id or response.get('error'):
                raise ValueError('Invalid or failed Piper response')
            with self._lock: self._prepared.add(uri)
            return response
        except (OSError, ValueError, queue.Empty):
            cancelled = self._cancelled.is_set()
            if not cancelled: LOG.warning('Piper worker failed for %s', uri)
            self._stop()
            raise SpeechError('CANCELLED' if cancelled else 'PROCESS_FAILURE',
                              'Piper fue interrumpido' if cancelled else 'Piper no pudo generar la voz seleccionada') from None

    def prepare(self, body):
        if not isinstance(body, dict) or set(body) != {'voice'} or not isinstance(body['voice'], str) or body['voice'] not in self._models():
            raise SpeechError('INVALID_REQUEST', 'Selecciona una voz Piper instalada')
        uri = body['voice']
        with self._lock:
            if uri in self._prepared or self._preparing:
                return self.status()
            self._preparing = uri
            self._last_error = None
        def load():
            try:
                with self._busy:
                    self._cancelled.clear()
                    self._request(uri)
            except SpeechError as error:
                with self._lock: self._last_error = str(error)
            finally:
                with self._lock: self._preparing = None
        threading.Thread(target=load, name='axx-piper-prepare', daemon=True).start()
        return self.status()

    def synthesize(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, uri = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200 or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'Text must contain 1 to 1200 characters')
        if not isinstance(uri, str) or uri not in self._models() or type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper voice or rate')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper volume')
        if not self._busy.acquire(timeout=10):
            raise SpeechError('BUSY', 'Piper is preparing another voice')
        try:
            self._cancelled.clear()
            raw = base64.b64decode(self._request(uri, text, body.get('rate', 0), body.get('volume', 100))['audio_base64'], validate=True)
            if not 44 < len(raw) <= MAX_AUDIO:
                raise ValueError('Invalid Piper WAV size')
            with wave.open(io.BytesIO(raw), 'rb') as audio:
                rate, channels, frames = audio.getframerate(), audio.getnchannels(), audio.getnframes()
                if not 8000 <= rate <= 48000 or channels != 1 or audio.getsampwidth() != 2 or not 0 < frames / rate <= 90:
                    raise ValueError('Invalid Piper WAV format')
            return {'engine': 'piper-onnx', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                    'voice': uri, 'language': MODELS[uri][2], 'duration_seconds': round(frames / rate, 3),
                    'playback_verified': False, 'external_calls': 0,
                    'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                                 'frames': frames, 'sample_rate': rate}}
        except (ValueError, KeyError, wave.Error):
            raise SpeechError('PROCESS_FAILURE', 'Piper devolvió audio inválido') from None
        finally:
            self._busy.release()
