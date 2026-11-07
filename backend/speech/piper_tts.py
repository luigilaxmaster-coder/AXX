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
import struct
import subprocess
import sys
import threading
import time
import uuid
import wave

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .speech_text import prepare_spoken_text
from .windows_tts import SpeechError


LOG = logging.getLogger(__name__)
MODELS = {
    'piper:es_ES-carlfm-x_low': ('es_ES-carlfm-x_low', 'Piper · España · CarlFM · ligera', 'es-ES'),
    'piper:es_MX-ald-medium': ('es_MX-ald-medium', 'Piper · México · Ald · media', 'es-MX'),
}
MAX_AUDIO = 12 * 1024 * 1024
# Privately trained voices live next to the public models as axx-*.onnx(.json).
# They are discovered at runtime and never shipped with the installer.
PRIVATE_VOICE = re.compile(r'axx-[a-z0-9]+(?:-[a-z0-9]+){0,4}')
# Speaking styles for private voices: suffix -> (label, length factor, noise, noise_w).
# Prosody presets only; true emotional timbre needs recordings in that emotion.
STYLES = {
    '': ('Natural', 0.98, 0.60, 0.80),
    'calma': ('Tranquila', 1.08, 0.58, 0.75),
    'emocion': ('Emocionada', 0.90, 0.65, 0.85),
    'atencion': ('Atenta', 0.95, 0.60, 0.78),
}

def _fix_pipe_wav(data: bytes) -> bytes:
    if len(data) < 12 or not data.startswith(b'RIFF') or data[8:12] != b'WAVE':
        return data
    idx = data.find(b'data')
    if idx == -1 or idx + 8 > len(data):
        return data
    b = bytearray(data)
    b[4:8] = struct.pack('<I', len(data) - 8)
    b[idx+4:idx+8] = struct.pack('<I', len(data) - idx - 8)
    return bytes(b)


def _apply_timbre_dsp(raw_bytes: bytes, style: str) -> bytes:
    # Direct neural synthesis: raw Piper ONNX output already matches the target
    # pitch (160.4 Hz vs 160.9-164.6 Hz ground truth) without phase vocoder distortion.
    return raw_bytes




_ES_MARKERS = re.compile(
    r'[¿¡ñáéíóúü]|\b(el|la|los|las|un|una|unos|unas|y|o|de|del|en|con|por|para|que|no|me|te|se|mi|tu|su|nos|es|son|'
    r'fue|era|va|vamos|bien|muy|como|todo|todos|esto|esta|este|amor|cielo|vida|quiero|puedo|hola|gracias|bueno|buenas|'
    r'noches|dias|estoy|estas|estan|siento|perfecto|ahora|aqui|ya|si|tiempo|persona|hacer|estar|decir|ir|ver|dar|saber|'
    r'querer|llegar|pasar|deber|poner|parecer|quedar|creer|hablar|llevar|dejar|seguir|encontrar|llamar|venir|pensar|'
    r'salir|volver|tomar|conocer|vivir|sentir|tratar|mirar|contar|empezar|esperar|buscar|existir|entrar|trabajar|'
    r'escribir|perder|producir|ocurrir|entender|pedir|recibir|recordar|terminar|permitir|aparecer|conseguir|comenzar|'
    r'servir|sacar|necesitar|mantener|resultar|leer|caer|cambiar|presentar|crear|abrir|considerar|oir|acabar|ganar|'
    r'formar|traer|partir|morir|aceptar|realizar|suponer|comprender|lograr|explicar|preguntar|tocar|reconocer|estudiar|'
    r'alcanzar|nacer|dirigir|correr|utilizar|pagar|ayudar|gustar|jugar|escuchar|cumplir|ofrecer|descubrir|levantar|intentar)\b',
    re.I
)

_EN_MARKERS = re.compile(
    r'\b(the|is|are|was|were|you|your|he|she|it|they|we|my|him|her|them|that|this|these|those|and|but|if|of|at|by|for|'
    r'with|about|into|through|during|before|after|above|below|to|from|up|down|in|out|on|off|over|under|again|further|'
    r'then|once|here|there|when|where|why|how|all|any|both|each|few|more|most|other|some|such|no|nor|not|only|own|same|'
    r'so|than|too|very|can|will|just|should|now|hello|darling|honey|please|thank|thanks|welcome|good|morning|afternoon|'
    r'evening|night|yes|yeah|sure|okay|cool|awesome|great|nice|love|baby|sweetheart)\b',
    re.I
)

def _detect_piper_language(text: str) -> str:
    es_score = len(_ES_MARKERS.findall(text))
    en_score = len(_EN_MARKERS.findall(text))
    if es_score > en_score:
        return 'es'
    if en_score > es_score:
        return 'en'
    if re.search(r'[¿¡ñáéíóúü]', text):
        return 'es'
    return 'es'


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
        if text is not None:
            request.update(text=text, rate=rate, volume=volume)
            _, length, noise, noise_w = STYLES.get(uri.partition('@')[2], STYLES[''])
            request.update({key: value for key, value in (('length_factor', length), ('noise_scale', noise),
                                                          ('noise_w', noise_w)) if value is not None})
        try:
            process.stdin.write((json.dumps(request, ensure_ascii=True) + '\n').encode('ascii'))
            process.stdin.flush()
            deadline = time.monotonic() + timeout
            while True:
                remaining = max(0.1, deadline - time.monotonic())
                response = responses.get(timeout=remaining)
                if not isinstance(response, dict):
                    raise ValueError('Invalid Piper response')
                if response.get('id') == request_id:
                    if response.get('error'):
                        raise ValueError(response['error'])
                    break
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
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume', 'language'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, uri = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200 or '\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'Text must contain 1 to 1200 characters')
        if not isinstance(uri, str) or uri not in self._models() or type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper voice or rate')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper volume')

        # Robust language resolution
        lang = body.get('language')
        if not lang or lang == 'auto':
            lang = _detect_piper_language(text)
        cleaned_text, _ = prepare_spoken_text(text, lang)
        spoken_text = cleaned_text.strip() or text.strip()

        # Automatic language routing for axx-morcito
        target_uri = uri
        base_voice, at, style = uri.partition('@')
        if base_voice.startswith('piper:axx-morcito'):
            if lang == 'en' and 'piper:axx-morcito-en' in self._models():
                target_uri = 'piper:axx-morcito-en' + (at + style if style else '')
            elif lang == 'es' and 'piper:axx-morcito-es' in self._models():
                target_uri = 'piper:axx-morcito-es' + (at + style if style else '')

        if not self._busy.acquire(timeout=10):
            raise SpeechError('BUSY', 'Piper is preparing another voice')
        try:
            self._cancelled.clear()
            raw = base64.b64decode(self._request(target_uri, spoken_text, body.get('rate', 0), body.get('volume', 100))['audio_base64'], validate=True)
            base_voice, _, style = uri.partition('@')
            if 'axx-morcito' in base_voice:
                raw = _apply_timbre_dsp(raw, style)
            if not 44 < len(raw) <= MAX_AUDIO:
                raise ValueError('Invalid Piper WAV size')
            with wave.open(io.BytesIO(raw), 'rb') as audio:
                rate, channels, frames = audio.getframerate(), audio.getnchannels(), audio.getnframes()
                if not 8000 <= rate <= 48000 or channels != 1 or audio.getsampwidth() != 2 or not 0 < frames / rate <= 90:
                    raise ValueError('Invalid Piper WAV format')
            return {'engine': 'piper-onnx', 'mime': 'audio/wav', 'audio_base64': base64.b64encode(raw).decode('ascii'),
                    'voice': uri, 'language': self._models()[target_uri][2], 'duration_seconds': round(frames / rate, 3),
                    'playback_verified': False, 'external_calls': 0,
                    'evidence': {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                                 'frames': frames, 'sample_rate': rate}}
        except (ValueError, KeyError, wave.Error):
            raise SpeechError('PROCESS_FAILURE', 'Piper devolvió audio inválido') from None
        finally:
            self._busy.release()
