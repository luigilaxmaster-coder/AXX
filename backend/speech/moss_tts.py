"""Local MOSS synthesis with bounded PCM streaming and a persistent worker."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
import wave

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .speech_text import prepare_spoken_text
from .windows_tts import SpeechError

MAX_AUDIO = 12 * 1024 * 1024
MAX_CACHE = 64 * 1024 * 1024


class MossSpeechService:
    PERSONAL_VOICES = (
        ('axx-sam', 'Xxx default'),
        ('axx-valeria', 'Axx Valeria · Cálida y Elocuente'),
        ('axx-elena', 'Axx Elena · Cercana y Melódica'),
        ('axx-mateo', 'Axx Mateo · Ágil y Expresivo'),
        ('axx-dante', 'Axx Dante · Profundo y Sereno'),
        ('axx-alba', 'Axx Alba (Legado)'),
        ('axx-nova', 'Axx Nova (Legado)'),
        ('axx-aura', 'Axx Aura (Legado)'),
        ('axx-titan', 'Axx Titán (Legado)'),
    )
    FALLBACK_VOICES = (('voz_referencia', 'Axx Base'), ('voz_referencia_completo', 'Axx Base Plus'))

    def __init__(self, data_dir: Path):
        self.root = Path(os.environ.get('AXX_MOSS_TTS_ROOT', Path.home() / 'Downloads' / 'tts nano' / 'MOSS-TTS-Nano'))
        self.python = self.root / '.venv' / 'Scripts' / 'python.exe'
        self.script = (Path(sys._MEIPASS) / 'speech' / 'moss_worker.py'
                       if getattr(sys, 'frozen', False) else Path(__file__).with_name('moss_worker.py'))
        self.models, self.samples = self.root / 'models', self.root / 'samples'
        self.data_dir = Path(data_dir) / 'speech'
        self.output_dir, self.personal_samples = self.data_dir / 'generated', self.data_dir / 'voices'
        self._busy, self._lock, self._start_lock, self._stdin_lock = (threading.Lock() for _ in range(4))
        self._changed = threading.Condition(self._lock)
        self._worker = None
        self._request_id = None
        self._warm_started = False
        self._closed = False
        self._cancelled = threading.Event()
        self._ready = False
        self._prepared = set()
        self._preparing = None
        self._stream = None

    def _cache_path(self, request):
        """No text in filenames; invalidate on voice, engine or model changes."""
        if request.get('prepare'):
            return None
        try:
            voice = self._voice_paths()[request['voice']][0]
            engine = [self.script, self.script.with_name('speech_text.py'),
                      self.root / 'onnx_tts_runtime.py', self.root / 'ort_cpu_runtime.py']
            models = sorted(p for p in self.models.glob('*/*') if p.is_file())
            # PyInstaller extracts scripts to a new directory on each launch.
            # Hash their contents so the persistent cache survives a restart.
            signature = ([(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in models] +
                         [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in engine])
            spoken, language = prepare_spoken_text(request['text'], request.get('language', 'auto'))
            key = hashlib.sha256(voice.read_bytes() + json.dumps(
                [spoken, language, signature], ensure_ascii=True).encode()).hexdigest()
            return self.data_dir / 'audio-cache' / (key + '.wav')
        except (OSError, KeyError):
            return None

    @staticmethod
    def _read_cache(path):
        if path is None:
            return None
        try:
            if not 44 < path.stat().st_size <= MAX_AUDIO:
                return None
            raw = path.read_bytes()
            with wave.open(io.BytesIO(raw), 'rb') as audio:
                rate, channels, frames = audio.getframerate(), audio.getnchannels(), audio.getnframes()
                if rate not in (24000, 48000) or channels not in (1, 2) or audio.getsampwidth() != 2 or not 0 < frames / rate <= 90:
                    return None
                pcm = audio.readframes(frames)
                if len(pcm) != frames * channels * 2:
                    return None
            path.touch()
            return raw, pcm, rate, channels
        except (OSError, EOFError, wave.Error):
            return None

    @staticmethod
    def _save_cache(path, raw):
        if path is None or not 44 < len(raw) <= MAX_AUDIO:
            return
        temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(raw)
            temporary.replace(path)
            files = sorted(path.parent.glob('*.wav'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            used = 0
            for index, file in enumerate(files):
                used += file.stat().st_size
                if index >= 256 or used > MAX_CACHE:
                    file.unlink(missing_ok=True)
        except OSError:
            pass  # A full disk must not stop speech; this cache is expendable.
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @property
    def available(self):
        return (self.python.is_file() and self.script.is_file()
                and (self.models / 'MOSS-TTS-Nano-100M-ONNX').is_dir()
                and (self.models / 'MOSS-Audio-Tokenizer-Nano-ONNX').is_dir())

    def _voice_paths(self):
        if not self.available:
            return {}
        personal = {}
        for name, label in self.PERSONAL_VOICES:
            p = self.personal_samples / (name + '.wav')
            if not p.is_file():
                p = self.samples / (name + '.wav')
            if p.is_file():
                personal['moss:' + name] = (p, label)
        return personal or {'moss:' + name: (self.samples / (name + '.wav'), label)
                            for name, label in self.FALLBACK_VOICES if (self.samples / (name + '.wav')).is_file()}

    def voices(self):
        voices = [{'name': name, 'language': 'es / en', 'enabled': True, 'streaming': True,
                   'engine': 'moss-onnx', 'label': label + ' · Español / English'}
                  for name, (_, label) in self._voice_paths().items()]
        if voices:
            self.start_warmup()
        return voices

    def status(self):
        with self._lock:
            return {'available': self.available, 'ready': self._ready, 'preparing_voice': self._preparing,
                    'prepared_voices': sorted(self._prepared), 'streaming': True}

    def start_warmup(self):
        with self._lock:
            if self._warm_started or self._worker or self._closed or not self.available:
                return
            self._warm_started = True
        def warm():
            try:
                self._ensure_worker()
            except (OSError, SpeechError):
                pass
            finally:
                with self._lock:
                    self._warm_started = False
        threading.Thread(target=warm, name='axx-moss-warmup', daemon=True).start()

    def _stop_worker(self):
        with self._lock:
            worker, self._worker = self._worker, None
            self._ready = False
            self._prepared.clear()
        if worker:
            process, job, _ = worker
            terminate_process_tree(process, job)
            # Terminate first to release any blocked writer, then close its pipe.
            # The receiver thread owns stdout and closes it when it reaches EOF.
            with self._stdin_lock:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
            if job:
                job.close()

    def close(self):
        self._closed = True
        self._cancelled.set()
        self._stop_worker()

    def _ensure_worker(self):
        with self._start_lock:
            if self._closed:
                raise SpeechError('CANCELLED', 'Speech service closed')
            with self._lock:
                worker = self._worker
            if worker and worker[0].poll() is None and self._ready:
                return worker
            if worker:
                self._stop_worker()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.pop('AXX_HOST_TOKEN', None)
            args = [str(self.python), '-u', str(self.script), str(self.models), str(self.personal_samples), str(self.output_dir)]
            process, job = spawn_managed_process(args, cwd=str(self.root), env=env, stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            responses = queue.Queue(maxsize=512)
            worker = (process, job, responses)
            with self._lock:
                self._worker = worker
            def receive():
                try:
                    for line in process.stdout:
                        try:
                            item = json.loads(line)
                        except (ValueError, UnicodeError):
                            item = None
                        responses.put(item, timeout=2)
                except queue.Full:
                    process.terminate()
                finally:
                    try:
                        responses.put_nowait(None)
                    except queue.Full:
                        pass
                    process.stdout.close()
            threading.Thread(target=receive, name='axx-moss-results', daemon=True).start()
            try:
                ready = responses.get(timeout=90)
                if not isinstance(ready, dict) or ready.get('ready') is not True or process.poll() is not None:
                    raise SpeechError('PROCESS_FAILURE', 'MOSS voice model failed to start')
                if self._closed:
                    raise SpeechError('CANCELLED', 'Speech service closed')
                with self._lock:
                    self._ready = True
                return worker
            except queue.Empty:
                self._stop_worker()
                raise SpeechError('DEADLINE_EXCEEDED', 'MOSS voice model loading exceeded 90 seconds')
            except SpeechError:
                self._stop_worker()
                raise

    def _send(self, process, request):
        with self._stdin_lock:
            if not process.stdin or process.stdin.closed:
                raise BrokenPipeError('MOSS voice worker input is closed')
            process.stdin.write((json.dumps(request, ensure_ascii=True) + '\n').encode('ascii'))
            process.stdin.flush()

    def cancel_active(self):
        if not self._busy.locked():
            return 0
        self._cancelled.set()
        with self._lock:
            worker, request_id = self._worker, self._request_id
        if worker and request_id:
            try:
                self._send(worker[0], {'id': request_id, 'cancel': True})
            except OSError:
                self._stop_worker()
        return 1

    def _request(self, request):
        """Caller owns _busy. Drain cancellation acknowledgement before reuse."""
        if self._cancelled.is_set():
            raise SpeechError('CANCELLED', 'Speech was cancelled')
        cache_path = self._cache_path(request)
        cached = self._read_cache(cache_path)
        if cached:
            raw, pcm, rate, channels = cached
            if request.get('stream'):
                chunk_size = rate * channels * 2 // 5
                for start in range(0, len(pcm), chunk_size):
                    if self._cancelled.is_set():
                        raise SpeechError('CANCELLED', 'Speech was cancelled')
                    yield {'id': request['id'], 'chunk': True, 'pcm_base64': base64.b64encode(pcm[start:start + chunk_size]).decode('ascii'),
                           'sample_rate': rate, 'channels': channels, 'elapsed_ms': 0, 'cache_hit': True}
            else:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                (self.output_dir / (request['id'] + '.wav')).write_bytes(raw)
            return
        process, _, responses = self._ensure_worker()
        if self._cancelled.is_set():
            raise SpeechError('CANCELLED', 'Speech was cancelled')
        with self._lock:
            self._request_id = request['id']
        try:
            pcm, audio_format = bytearray(), None
            self._send(process, request)
            deadline, cancel_sent = time.monotonic() + 120, False
            while True:
                if self._cancelled.is_set() and not cancel_sent:
                    self._send(process, {'id': request['id'], 'cancel': True})
                    deadline = min(deadline, time.monotonic() + 3)
                    cancel_sent = True
                if time.monotonic() > deadline:
                    raise SpeechError('DEADLINE_EXCEEDED', 'MOSS synthesis timed out')
                try:
                    response = responses.get(timeout=.05)
                except queue.Empty:
                    if process.poll() is not None:
                        raise SpeechError('PROCESS_FAILURE', 'MOSS voice worker stopped')
                    continue
                if not isinstance(response, dict) or response.get('id') != request['id']:
                    raise SpeechError('PROCESS_FAILURE', 'MOSS worker returned an invalid response')
                if response.get('chunk'):
                    if not cancel_sent:
                        current_format = response.get('sample_rate'), response.get('channels')
                        if audio_format and audio_format != current_format:
                            raise SpeechError('PROCESS_FAILURE', 'MOSS changed PCM format mid-stream')
                        yield response
                        # The streaming consumer validates each packet before
                        # resuming this generator. Cancelled audio is never saved.
                        pcm.extend(base64.b64decode(response['pcm_base64']))
                        audio_format = current_format
                        if len(pcm) > MAX_AUDIO:
                            raise SpeechError('PROCESS_FAILURE', 'Speech exceeds audio cache limit')
                elif response.get('cancelled') or self._cancelled.is_set():
                    raise SpeechError('CANCELLED', 'Speech was cancelled')
                elif response.get('ok') is True:
                    with self._lock:
                        self._prepared.add(request['voice'])
                    # A reference can be replaced while ONNX loads/generates.
                    if cache_path is not None and cache_path != self._cache_path(request):
                        cache_path = None
                    if pcm and audio_format:
                        buffer = io.BytesIO()
                        with wave.open(buffer, 'wb') as audio:
                            audio.setframerate(audio_format[0]); audio.setnchannels(audio_format[1]); audio.setsampwidth(2)
                            audio.writeframes(pcm)
                        self._save_cache(cache_path, buffer.getvalue())
                    elif not request.get('prepare'):
                        output = self.output_dir / (request['id'] + '.wav')
                        audio = self._read_cache(output)
                        if audio:
                            self._save_cache(cache_path, audio[0])
                    return
                else:
                    raise SpeechError('PROCESS_FAILURE', 'MOSS could not synthesize the selected voice')
        except (OSError, SpeechError) as error:
            if not isinstance(error, SpeechError) or error.code != 'CANCELLED':
                self._stop_worker()
            raise
        finally:
            with self._lock:
                self._request_id = None

    def _validate(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume', 'language'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        if not isinstance(body.get('text'), str) or not 1 <= len(body['text'].strip()) <= 220 or '\x00' in body['text']:
            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 220 characters')
        if not isinstance(body.get('voice'), str) or body['voice'] not in self._voice_paths():
            raise SpeechError('NOT_SUPPORTED', 'The selected local MOSS voice is unavailable')
        if type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid voice speed')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid volume')
        language = body.get('language', 'auto')
        if not isinstance(language, str) or not re.fullmatch(r'auto|[a-zA-Z]{2,3}(?:-[a-zA-Z]{2,4})?', language):
            raise SpeechError('INVALID_REQUEST', 'Invalid speech language')

    def prepare(self, body):
        if not isinstance(body, dict) or set(body) != {'voice'} or not isinstance(body['voice'], str) or body['voice'] not in self._voice_paths():
            raise SpeechError('INVALID_REQUEST', 'Select an available custom voice')
        voice = body['voice']
        with self._lock:
            skip = voice in self._prepared or self._preparing is not None or self._closed
            if not skip:
                self._preparing = voice
        if skip:
            return self.status()
        def prepare_voice():
            acquired = False
            try:
                # Loading ONNX must not block replay of already cached speech.
                self._ensure_worker()
                acquired = self._busy.acquire(blocking=False)
                if not acquired:
                    return
                self._cancelled.clear()
                for _ in self._request({'id': uuid.uuid4().hex, 'voice': voice, 'prepare': True}):
                    pass
            except (SpeechError, OSError):
                pass  # Status stays unprepared and synthesis may retry.
            finally:
                with self._lock:
                    self._preparing = None
                if acquired:
                    self._busy.release()
        threading.Thread(target=prepare_voice, daemon=True, name='axx-moss-reference').start()
        return self.status()

    def start_stream(self, body):
        self._validate(body)
        if not self._busy.acquire(timeout=3):
            raise SpeechError('BUSY', 'The voice is still preparing; retry shortly')
        self._cancelled.clear()
        stream = {'id': uuid.uuid4().hex, 'events': [], 'done': False, 'error': None,
                  'bytes': 0, 'created': time.monotonic(), 'last_poll': time.monotonic(), 'first_audio_ms': None}
        with self._lock:
            self._stream = stream
        def generate():
            iterator = None
            try:
                request = {'id': stream['id'], 'voice': body['voice'], 'text': body['text'],
                           'language': body.get('language', 'auto'), 'stream': True}
                iterator = self._request(request)
                for event in iterator:
                    raw = base64.b64decode(event['pcm_base64'], validate=True)
                    rate, channels = event['sample_rate'], event['channels']
                    if rate not in (24000, 48000) or channels not in (1, 2) or not raw or len(raw) % (2 * channels):
                        raise SpeechError('PROCESS_FAILURE', 'Invalid PCM format')
                    with self._lock:
                        stream['bytes'] += len(raw)
                        if stream['bytes'] > MAX_AUDIO or len(stream['events']) >= 512:
                            raise SpeechError('PROCESS_FAILURE', 'Speech stream exceeds size limit')
                        if time.monotonic() - stream['last_poll'] > 15:
                            raise SpeechError('CANCELLED', 'Speech stream consumer disconnected')
                        event['seq'] = len(stream['events']) + 1
                        if stream['first_audio_ms'] is None:
                            stream['first_audio_ms'] = round((time.monotonic() - stream['created']) * 1000)
                        stream['events'].append(event)
                        self._changed.notify_all()
            except (SpeechError, OSError, ValueError, KeyError) as error:
                self.cancel_active()
                # If the consumer aborted iteration mid-request, the worker's
                # terminal reply was not drained; reset only this abnormal case.
                if self._request_id:
                    self._stop_worker()
                with self._lock:
                    stream['error'] = {'code': getattr(error, 'code', 'PROCESS_FAILURE'), 'message': str(error)}
            finally:
                if iterator:
                    iterator.close()
                with self._lock:
                    stream['done'] = True
                    self._changed.notify_all()
                self._busy.release()
        threading.Thread(target=generate, name='axx-moss-stream', daemon=True).start()
        spoken, _ = prepare_spoken_text(body['text'], body.get('language', 'auto'))
        return {'stream_id': stream['id'], 'engine': 'moss-onnx', 'format': 'pcm_s16le',
                'estimated_audio_seconds': min(90, max(1, len(spoken) / 7.5) + .5)}

    def poll_stream(self, body):
        if not isinstance(body, dict) or set(body) != {'stream_id', 'after'} or type(body['after']) is not int or body['after'] < 0:
            raise SpeechError('INVALID_REQUEST', 'Invalid speech stream cursor')
        with self._lock:
            stream = self._stream
            if not stream or body['stream_id'] != stream['id']:
                raise SpeechError('INVALID_REQUEST', 'Speech stream expired')
            if body['after'] > len(stream['events']):
                raise SpeechError('INVALID_REQUEST', 'Speech cursor is ahead of stream')
            stream['last_poll'] = time.monotonic()
            self._changed.wait_for(lambda: stream['done'] or len(stream['events']) > body['after'], timeout=.5)
            events = stream['events'][body['after']:body['after'] + 8]
            return {'events': events, 'done': stream['done'] and body['after'] + len(events) == len(stream['events']),
                    'error': stream['error'], 'first_audio_ms': stream['first_audio_ms']}

    def synthesize(self, body):
        self._validate(body)
        if not self._busy.acquire(blocking=False):
            raise SpeechError('BUSY', 'MOSS is generating another voice segment')
        self._cancelled.clear()
        request_id = uuid.uuid4().hex
        output = self.output_dir / f'{request_id}.wav'
        try:
            for _ in self._request({'id': request_id, 'voice': body['voice'], 'text': body['text'],
                                   'language': body.get('language', 'auto')}):
                pass
            size = output.stat().st_size
            if not 44 < size <= MAX_AUDIO:
                raise SpeechError('PROCESS_FAILURE', 'MOSS output size is invalid')
            with wave.open(str(output), 'rb') as audio:
                frames, rate, channels = audio.getnframes(), audio.getframerate(), audio.getnchannels()
                if channels not in (1, 2) or audio.getsampwidth() != 2 or rate not in (24000, 48000) or not 0 < frames / rate <= 90:
                    raise SpeechError('PROCESS_FAILURE', 'MOSS returned an unsupported WAV format')
            raw = output.read_bytes()
            return {'engine': 'moss-onnx', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                    'voice': body['voice'], 'language': 'es/en', 'duration_seconds': round(frames / rate, 3),
                    'playback_verified': False, 'external_calls': 0,
                    'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': size, 'frames': frames,
                                 'channels': channels, 'sample_rate': rate, 'model_source': 'local_onnx'}}
        finally:
            output.unlink(missing_ok=True)
            self._busy.release()
