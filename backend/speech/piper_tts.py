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
import re
import subprocess
import sys
import threading
import time
import uuid
import wave

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .speech_text import prepare_spoken_text, resolve_language
from .windows_tts import SpeechError

try:
    from .prosody import ProsodyAnalyzer, HumanizerDSP
except ImportError:
    ProsodyAnalyzer = None
    HumanizerDSP = None


LOG = logging.getLogger(__name__)
MODELS = {
    'piper:es_ES-carlfm-x_low': ('es_ES-carlfm-x_low', 'Piper · España · CarlFM · ligera', 'es-ES'),
    'piper:es_MX-ald-medium': ('es_MX-ald-medium', 'Piper · México · Ald · media', 'es-MX'),
}
MAX_AUDIO = 12 * 1024 * 1024


PRIVATE_VOICE = re.compile(r'axx-[a-z0-9]+(?:-[a-z0-9]+){0,4}')
# Speaking styles for private voices: suffix -> (label, length factor, noise, noise_w).
STYLES = {
    '': ('Natural', 0.96, 0.50, 0.65),
    'calma': ('Tranquila', 1.04, 0.44, 0.58),
    'emocion': ('Emocionada', 0.91, 0.58, 0.70),
    'atencion': ('Atenta', 0.99, 0.44, 0.58),
}

def _private_meta(config_path: Path, name: str):
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(config, dict):
        return None
    axx = config.get('axx') if isinstance(config.get('axx'), dict) else {}
    label = axx.get('label') if isinstance(axx.get('label'), str) else name
    language = axx.get('language')
    if not isinstance(language, str):
        code = config['language'].get('code') if isinstance(config.get('language'), dict) else None
        espeak = config['espeak'].get('voice') if isinstance(config.get('espeak'), dict) else None
        language = str(code or espeak or 'es').replace('_', '-')
    return label[:80], language[:16]


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
        found = {uri: (name, label, language) for uri, (name, label, language) in MODELS.items()
                 if (self.models / (name + '.onnx')).is_file()
                 and (self.models / (name + '.onnx.json')).is_file()}
        try:
            private = sorted(self.models.glob('axx-*.onnx'), key=lambda m: (not m.stem.endswith('-es'), m.stem))
        except OSError:
            private = []
        for model in private:
            name = model.stem
            meta = PRIVATE_VOICE.fullmatch(name) and _private_meta(model.with_suffix('.onnx.json'), name)
            if not meta:
                continue
            for style, (style_label, *_unused) in STYLES.items():
                uri = 'piper:' + name + ('@' + style if style else '')
                found[uri] = (name, meta[0] + (' · ' + style_label if style else ''), meta[1])
        return found

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

    def _request(self, uri, text=None, rate=0, volume=100, timeout=90,
                 length_override=None, noise_override=None, noise_w_override=None):
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
        if text is not None:
            request.update(text=text, rate=rate, volume=volume)
            if '@' in uri:
                _, length, noise, noise_w = STYLES[uri.partition('@')[2]]
                request.update(length_factor=length, noise_scale=noise, noise_w=noise_w)
            if length_override is not None:
                request['length_factor'] = length_override
            if noise_override is not None:
                request['noise_scale'] = noise_override
            if noise_w_override is not None:
                request['noise_w'] = noise_w_override
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

    def _apply_warmth_to_wav(self, raw_wav: bytes, clause=None, mood: str = 'neutral') -> bytes:
        if HumanizerDSP is None:
            return raw_wav
        try:
            import numpy as np
            with wave.open(io.BytesIO(raw_wav), 'rb') as audio:
                sr = audio.getframerate()
                ch = audio.getnchannels()
                sw = audio.getsampwidth()
                frames = audio.readframes(audio.getnframes())
            if sw != 2 or ch != 1 or len(frames) < 128:
                return raw_wav
            arr = np.frombuffer(frames, dtype='<i2').astype(np.float32) / 32768.0
            if clause is not None:
                arr = HumanizerDSP.process_clause_pcm(arr, sr, clause)
            else:
                arr = HumanizerDSP.trim_silence(arr, sr, threshold=0.0045, head_ms=14, tail_ms=20)
                arr = HumanizerDSP.apply_vocal_warmth_eq(arr, sr, mood=mood)
            pcm_out = np.clip(arr * 32767.0, -32768.0, 32767.0).astype('<i2').tobytes()
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as out_wav:
                out_wav.setnchannels(1)
                out_wav.setsampwidth(2)
                out_wav.setframerate(sr)
                out_wav.writeframes(pcm_out)
            return buf.getvalue()
        except Exception:
            return raw_wav

    def _process_expressive_piper(self, uri: str, spoken: str, rate: int, volume: int) -> bytes:
        base_mood = ProsodyAnalyzer.detect_mood(spoken) if ProsodyAnalyzer is not None else 'neutral'
        if ProsodyAnalyzer is None or '@' in uri:
            raw = base64.b64decode(self._request(uri, spoken, rate, volume)['audio_base64'], validate=True)
            return self._apply_warmth_to_wav(raw, mood=base_mood)

        clauses = ProsodyAnalyzer.segment(spoken)
        if not clauses:
            raw = base64.b64decode(self._request(uri, spoken, rate, volume)['audio_base64'], validate=True)
            return self._apply_warmth_to_wav(raw, mood=base_mood)

        if len(clauses) == 1:
            clause = clauses[0]
            eff_vol = max(10, min(100, int(round(volume * clause.volume))))
            raw = base64.b64decode(
                self._request(
                    uri, clause.text, rate, eff_vol,
                    length_override=clause.length_factor,
                    noise_override=clause.noise_scale,
                    noise_w_override=clause.noise_w,
                )['audio_base64'],
                validate=True,
            )
            return self._apply_warmth_to_wav(raw, clause=clause, mood=clause.mood)

        import numpy as np
        pcm_chunks = []
        sample_rate = 22050
        channels = 1
        sampwidth = 2

        for idx, clause in enumerate(clauses):
            eff_vol = max(10, min(100, int(round(volume * clause.volume))))
            chunk_raw = base64.b64decode(
                self._request(
                    uri, clause.text, rate, eff_vol,
                    length_override=clause.length_factor,
                    noise_override=clause.noise_scale,
                    noise_w_override=clause.noise_w,
                )['audio_base64'],
                validate=True,
            )
            chunk_raw = self._apply_warmth_to_wav(chunk_raw, clause=clause, mood=clause.mood)
            with wave.open(io.BytesIO(chunk_raw), 'rb') as wav_in:
                sample_rate = wav_in.getframerate()
                channels = wav_in.getnchannels()
                sampwidth = wav_in.getsampwidth()
                frames = wav_in.readframes(wav_in.getnframes())
                pcm_chunks.append(frames)

            if idx < len(clauses) - 1 and clause.pause_ms > 0:
                if HumanizerDSP is not None:
                    pause_arr = HumanizerDSP.create_comfort_pause(clause.pause_ms, sample_rate)
                    pcm_chunks.append(np.clip(pause_arr * 32767.0, -32768.0, 32767.0).astype('<i2').tobytes())
                else:
                    silence_samples = int(sample_rate * clause.pause_ms / 1000.0)
                    pcm_chunks.append(b'\x00\x00' * (silence_samples * channels))

        out_buf = io.BytesIO()
        with wave.open(out_buf, 'wb') as wav_out:
            wav_out.setnchannels(channels)
            wav_out.setsampwidth(sampwidth)
            wav_out.setframerate(sample_rate)
            wav_out.writeframes(b''.join(pcm_chunks))
        return out_buf.getvalue()

    def synthesize(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, uri = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200 or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'Text must contain 1 to 1200 characters')
        models = self._models()
        if not isinstance(uri, str) or uri not in models or type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper voice or rate')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper volume')
        if not self._busy.acquire(timeout=10):
            raise SpeechError('BUSY', 'Piper is preparing another voice')
        try:
            self._cancelled.clear()
            effective_uri = uri
            if uri.startswith('piper:axx-morcito-'):
                detected = resolve_language(text, 'auto')
                base, sep, suffix = uri.partition('@')
                style_part = (sep + suffix) if sep else ''
                if detected == 'en' and base.endswith('-es'):
                    alt = 'piper:axx-morcito-en' + style_part
                    if alt in models:
                        effective_uri = alt
                elif detected == 'es' and base.endswith('-en'):
                    alt = 'piper:axx-morcito-es' + style_part
                    if alt in models:
                        effective_uri = alt
            spoken, _ = prepare_spoken_text(text, models[effective_uri][2])
            raw = self._process_expressive_piper(effective_uri, spoken, body.get('rate', 0), body.get('volume', 100))
            if not 44 < len(raw) <= MAX_AUDIO:
                raise ValueError('Invalid Piper WAV size')
            with wave.open(io.BytesIO(raw), 'rb') as audio:
                rate, channels, frames = audio.getframerate(), audio.getnchannels(), audio.getnframes()
                if not 8000 <= rate <= 48000 or channels != 1 or audio.getsampwidth() != 2 or not 0 < frames / rate <= 90:
                    raise ValueError('Invalid Piper WAV format')
            return {'engine': 'piper-onnx', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                    'voice': uri, 'language': models[effective_uri][2], 'duration_seconds': round(frames / rate, 3),
                    'playback_verified': False, 'external_calls': 0,
                    'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                                 'frames': frames, 'sample_rate': rate}}
        except (ValueError, KeyError, wave.Error):
            raise SpeechError('PROCESS_FAILURE', 'Piper devolvió audio inválido') from None
        finally:
            self._busy.release()
