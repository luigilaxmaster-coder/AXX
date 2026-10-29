"""Phone-initiated dictation through the existing local Whisper worker."""
import base64
import hashlib
import threading
import time
import uuid


class MobileDictation:
    def __init__(self, store, backend_call):
        self.store, self.backend_call = store, backend_call
        self.lock = threading.Lock()
        self.jobs = {}
        self.slots = threading.BoundedSemaphore(2)

    def _authorized(self, device_id):
        if not any(d['device_id'] == device_id and not d['revoked'] and 'voice' in d['scopes']
                   for d in self.store.devices()):
            raise ValueError('Permiso de voz revocado')

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError('request_id debe ser un UUID')
        return value

    def status(self, device_id, request_id):
        self._authorized(device_id)
        key = (device_id, self._id(request_id))
        with self.lock:
            job = self.jobs.get(key)
            if not job:
                raise ValueError('Dictado no disponible; no se repetirá automáticamente')
            return {k: v for k, v in job.items() if k not in ('digest', 'created')}

    def submit(self, device_id, body):
        self._authorized(device_id)
        if set(body) != {'request_id', 'mime', 'audio_base64'} or body['mime'] != 'audio/mp4':
            raise ValueError('Dictado MP4 y request_id requeridos')
        request_id = self._id(body['request_id'])
        encoded = body['audio_base64']
        if not isinstance(encoded, str) or len(encoded) > 1900000:
            raise ValueError('Dictado demasiado grande')
        raw = base64.b64decode(encoded, validate=True)
        if not 16 < len(raw) <= 1400 * 1024 or raw[4:8] != b'ftyp':
            raise ValueError('Audio MP4 inválido')
        digest = hashlib.sha256(raw).hexdigest()
        key = (device_id, request_id)
        with self.lock:
            now = time.monotonic()
            self.jobs = {k: v for k, v in self.jobs.items()
                         if v['state'] == 'transcribing' or now - v['created'] < 900}
            existing = self.jobs.get(key)
            if existing:
                if existing['digest'] != digest:
                    raise ValueError('El identificador pertenece a otro audio')
                return {k: v for k, v in existing.items() if k not in ('digest', 'created')}
            if len(self.jobs) >= 32 or not self.slots.acquire(blocking=False):
                raise ValueError('Dictado ocupado; inténtalo al terminar la solicitud actual')
            self.jobs[key] = dict(request_id=request_id, state='transcribing', digest=digest, created=now)

        def run():
            try:
                self._authorized(device_id)
                result = self.backend_call('POST', '/axx-api/speech/transcribe', {
                    'audio_base64': encoded, 'mime': 'audio/mp4', 'language': 'es', 'task': 'transcribe'})
                if result.get('ok', True) is False or not isinstance(result.get('text'), str):
                    raise ValueError('No se pudo transcribir localmente')
                self._authorized(device_id)
                with self.lock:
                    self.jobs[key].update(state='completed', text=result['text'].strip()[:10000])
            except Exception:
                with self.lock:
                    self.jobs[key].update(state='failed', error='No se pudo transcribir localmente. Revisa el motor de voz de la PC.')
            finally:
                self.slots.release()

        threading.Thread(target=run, name='axx-phone-dictation', daemon=True).start()
        return self.status(device_id, request_id)
