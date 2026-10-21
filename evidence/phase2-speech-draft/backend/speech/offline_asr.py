"""Local tiny Whisper transcription in a bounded, cancellable CPU worker."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import importlib.abc
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .windows_tts import (SpeechError, CancellationResult, _SpeechOperations,
                          _body_operation_id, _run_speech_worker)

SNAPSHOT = 'd90ca5fe260221311c53c58e660288d3deb8d356'
MAX_AUDIO = 1400 * 1024
MAX_SECONDS = 60
MAX_WORKER_OUTPUT = 256 * 1024

def model_path():
    if getattr(sys,'frozen',False):
        candidates = [Path(sys.executable).parent/'models'/'faster-whisper-tiny',
                      Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent))/'models'/'faster-whisper-tiny']
    else:
        candidates = [Path(__file__).resolve().parents[2]/'src-tauri'/'resources'/'models'/'faster-whisper-tiny',
                      Path.home()/'.cache'/'huggingface'/'hub'/'models--Systran--faster-whisper-tiny'/'snapshots'/SNAPSHOT]
    required = ('model.bin','tokenizer.json','config.json','vocabulary.txt')
    return next((p.resolve() for p in candidates if all((p/f).is_file() for f in required)),None)

def worker_main():
    """Only this disposable process imports the native ASR libraries/model."""
    started=time.monotonic()
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw)>16384: raise SpeechError('INVALID_REQUEST','Transcription worker request exceeds limit')
        request = json.loads(raw)
        # CTranslate2 also ships training-format converters. Those optional
        # frameworks are explicitly disabled in this inference-only worker.
        # They are unnecessary for an already converted local CTranslate2 model.
        class InferenceOnlyImports(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in {'torch','transformers','tensorflow','fairseq','onnxruntime'}:
                    raise ModuleNotFoundError('Optional conversion framework is disabled in the Axx inference worker',name=fullname)
                return None
        sys.meta_path.insert(0,InferenceOnlyImports())
        import av
        import numpy as np
        from faster_whisper import WhisperModel
        imported=time.monotonic()
        path = Path(request['audio_path'])
        if not 0<path.stat().st_size<=MAX_AUDIO: raise SpeechError('INVALID_REQUEST','Audio exceeds byte limit')
        pieces=[];samples=0
        with av.open(str(path)) as container:
            if not container.streams.audio: raise SpeechError('INVALID_REQUEST','Input contains no audio stream')
            if container.duration is not None and container.duration/av.time_base>MAX_SECONDS+1:
                raise SpeechError('INVALID_REQUEST','Audio exceeds its 60-second duration limit')
            resampler=av.AudioResampler(format='s16',layout='mono',rate=16000)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    data=converted.to_ndarray().reshape(-1)
                    samples+=data.size
                    if samples>MAX_SECONDS*16000: raise SpeechError('INVALID_REQUEST','Audio exceeds its 60-second duration limit')
                    pieces.append(data.astype(np.float32)/32768.0)
            for converted in resampler.resample(None):
                data=converted.to_ndarray().reshape(-1);samples+=data.size
                if samples>MAX_SECONDS*16000: raise SpeechError('INVALID_REQUEST','Audio exceeds its 60-second duration limit')
                pieces.append(data.astype(np.float32)/32768.0)
        if not samples: raise SpeechError('INVALID_REQUEST','Input contains no decoded audio samples')
        audio=np.concatenate(pieces)
        decoded=time.monotonic()
        if float(np.sqrt(np.mean(np.square(audio))))<.0001:
            result={'text':'','segments':[],'language':request.get('language'),'language_probability':None,
                    'audio_duration_seconds':round(samples/16000,3),'silence_detected':True}
        else:
            model=WhisperModel(request['model_path'],device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
            loaded=time.monotonic()
            generated,info=model.transcribe(audio,language=request.get('language'),task=request['task'],
                beam_size=1,temperature=0,condition_on_previous_text=False,vad_filter=False,max_new_tokens=128)
            segments=[]
            for segment in generated:
                if len(segments)>=128: raise SpeechError('INVALID_RESPONSE','Too many transcription segments')
                segments.append({'start':round(segment.start,3),'end':round(segment.end,3),'text':segment.text.strip()[:4000]})
            result={'text':' '.join(s['text'] for s in segments).strip(),'segments':segments,
                    'language':info.language,'language_probability':round(info.language_probability,6),
                    'audio_duration_seconds':round(samples/16000,3),'silence_detected':False}
        result.update({'engine':'faster-whisper','model':'tiny','device':'cpu','compute_type':'int8',
                       'task':request['task'],'translation_target':'en' if request['task']=='translate' else None,
                       'external_calls':0,'automatic_actions':False})
        result['timings_ms']={'imports':round((imported-started)*1000), 'decode':round((decoded-imported)*1000),
                              'worker_total':round((time.monotonic()-started)*1000)}
        if not result['silence_detected']:
            result['timings_ms'].update(model_load=round((loaded-decoded)*1000),inference=round((time.monotonic()-loaded)*1000))
        response,code={'ok':True,'result':result},0
    except Exception as exc:
        response,code={'ok':False,'error':{'code':getattr(exc,'code','PROCESS_FAILURE'),'message':str(exc)[:400]}},1
    encoded=json.dumps(response,ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(encoded)>MAX_WORKER_OUTPUT:
        encoded=b'{"ok":false,"error":{"code":"INVALID_RESPONSE","message":"Transcription output exceeds limit"}}';code=1
    sys.stdout.buffer.write(encoded+b'\n');sys.stdout.buffer.flush()
    return code

class OfflineTranscriptionService:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir) / 'speech'
        self.model_path = model_path()
        self._busy = threading.Lock()
        self._operations = _SpeechOperations('transcription')
        self._lock = self._operations.lock
        self._active = None

    def status(self):
        return {'engine': 'faster-whisper', 'model': 'tiny',
                'available': bool(self.model_path and importlib.util.find_spec('faster_whisper')),
                'device': 'cpu', 'compute_type': 'int8', 'local_only': True, 'external_calls': 0,
                'max_duration_seconds': MAX_SECONDS}

    def close(self):
        self.cancel_active()

    def cancel(self, operation_id) -> CancellationResult:
        return self._operations.cancel(operation_id, terminate_process_tree)

    def cancel_active(self):
        """Explicit shutdown compatibility; request cancellation must use cancel(id)."""
        return self._operations.cancel_active(terminate_process_tree)

    def transcribe(self, body):
        if not isinstance(body, dict) or set(body) - {'audio_base64', 'mime', 'language', 'task', 'operation_id'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported transcription fields')
        operation_id = _body_operation_id(body)
        encoded,mime,language,task=body.get('audio_base64'),body.get('mime'),body.get('language'),body.get('task','transcribe')
        if not isinstance(encoded,str) or not 1<=len(encoded)<=((MAX_AUDIO+2)//3)*4:
            raise SpeechError('INVALID_REQUEST','Invalid bounded audio payload')
        if not isinstance(mime,str) or mime.split(';')[0].lower() not in ('audio/webm','audio/ogg','audio/wav','audio/x-wav','audio/mp4'):
            raise SpeechError('INVALID_REQUEST','Unsupported audio MIME type')
        mime = mime.split(';')[0].lower()
        if language in ('auto',''):language=None
        if language is not None and (not isinstance(language,str) or not re.fullmatch('[a-z]{2,3}',language)):
            raise SpeechError('INVALID_REQUEST','Invalid transcription language')
        if task not in ('transcribe','translate'):raise SpeechError('INVALID_REQUEST','Only transcription and translation into English are supported locally')
        try:raw=base64.b64decode(encoded,validate=True)
        except ValueError:raise SpeechError('INVALID_REQUEST','Audio is not valid base64') from None
        if not 0<len(raw)<=MAX_AUDIO:raise SpeechError('INVALID_REQUEST','Audio exceeds byte limit')
        valid = ((mime.startswith(('audio/wav','audio/x-wav')) and raw.startswith(b'RIFF') and raw[8:12]==b'WAVE')
                 or (mime.startswith('audio/webm') and raw.startswith(b'\x1a\x45\xdf\xa3'))
                 or (mime.startswith('audio/ogg') and raw.startswith(b'OggS'))
                 or (mime.startswith('audio/mp4') and raw[4:8]==b'ftyp'))
        if not valid:raise SpeechError('INVALID_REQUEST','Audio signature does not match its MIME type')
        # Admission and run publication precede all files and child creation.
        with self._lock:
            run = self._operations.admit(operation_id, self._busy)
            self._active = run
        try:
            self._operations.check(run)
            if not self.status()['available']:
                raise SpeechError('NOT_SUPPORTED', 'Bundled local tiny transcription model or runtime is unavailable')
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='asr-', dir=self.data_dir) as directory:
                audio_path = Path(directory) / 'input.audio'
                audio_path.write_bytes(raw)
                self._operations.check(run)
                request = {'audio_path': str(audio_path), 'model_path': str(self.model_path), 'language': language, 'task': task}
                result = self._execute(request, run)
                self._operations.check(run)
                result['input_sha256'] = hashlib.sha256(raw).hexdigest()
            return self._operations.commit(run, result)
        finally:
            with self._lock:
                self._operations.retire(run)
                if self._active is run and not run.active:
                    self._active = None

    def _execute(self, request, run):
        command = ([sys.executable, '--transcribe-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-m', 'backend.server', '--transcribe-worker'])
        env = os.environ.copy()
        env.pop('AXX_HOST_TOKEN', None)
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        response = _run_speech_worker(command, request, run, env=env, timeout=90,
            output_limit=MAX_WORKER_OUTPUT, spawn=spawn_managed_process, terminate=terminate_process_tree,
            cwd=str(Path(__file__).resolve().parents[2]), allow_error_envelope=True)
        if not response.get('ok'):
            error = response.get('error', {})
            raise SpeechError(error.get('code', 'PROCESS_FAILURE'), error.get('message', 'Transcription failed'))
        result = response.get('result')
        if not isinstance(result, dict):
            raise SpeechError('PROCESS_FAILURE', 'Invalid transcription worker result')
        return result
