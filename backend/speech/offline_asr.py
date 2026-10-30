"""Local Whisper transcription in a bounded, cancellable CPU worker."""
from __future__ import annotations
import base64
from dataclasses import dataclass, field
import hashlib
import importlib.util
import importlib.abc
import io
import json
import logging
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
from .windows_tts import SpeechError

SNAPSHOT = 'd90ca5fe260221311c53c58e660288d3deb8d356'
MAX_AUDIO = 1400 * 1024
MAX_WORKER_REQUEST = ((MAX_AUDIO + 2) // 3) * 4 + 16384
MAX_SECONDS = 60
MAX_WORKER_OUTPUT = 256 * 1024
MAX_REQUEST_IDS = 4096
AUTO_REQUEST_PREFIX = 'asr-auto-'
VOICE_CONTEXT = 'Spotify. Google Chrome. YouTube. ChatGPT. Obsidian.'
LOG = logging.getLogger('axx.offline_asr')
_WORKER_MODEL = None
_WORKER_MODEL_PATH = None


@dataclass(eq=False)
class _ASRRequest:
    request_id: str
    context_owner: str | None = None
    deadline_mono: float | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event | None = None
    process: object = None
    job: object = None
    completed: bool = False

    def is_cancelled(self):
        return self.cancelled.is_set() or (self.cancel_event is not None and self.cancel_event.is_set())


def _request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise SpeechError('INVALID_REQUEST', 'Invalid transcription request_id')
    return value


def _context_deadline(context_owner, deadline_mono):
    if context_owner is not None and (not isinstance(context_owner, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', context_owner)):
        raise SpeechError('INVALID_REQUEST', 'Invalid internal transcription owner')
    if deadline_mono is None:
        if context_owner is not None:raise SpeechError('INVALID_REQUEST', 'Context transcription requires its lease deadline')
        return None
    if type(deadline_mono) not in (int, float) or not math.isfinite(deadline_mono):
        raise SpeechError('INVALID_REQUEST', 'Invalid internal transcription deadline')
    remaining = deadline_mono - time.monotonic()
    if remaining <= 0:raise SpeechError('DEADLINE_EXCEEDED', 'Transcription lease already expired')
    if remaining > 60:raise SpeechError('INVALID_REQUEST', 'Transcription lease exceeds its 60-second bound')
    return float(deadline_mono)


class InferenceOnlyImports(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','transformers','tensorflow','fairseq','onnxruntime'}:
            raise ModuleNotFoundError('Optional conversion framework is disabled in the Axx inference worker',name=fullname)
        return None


def guard_worker_imports():
    if not any(isinstance(finder,InferenceOnlyImports) for finder in sys.meta_path):
        sys.meta_path.insert(0,InferenceOnlyImports())


def excessive_repetition(text):
    words = re.findall(r'\w+', text.casefold())
    return len(words) >= 16 and any(words[i:i + n] == words[i + n:i + 2 * n] == words[i + 2 * n:i + 3 * n]
                                    for n in range(2, 6) for i in range(len(words) - 3 * n + 1))

def model_path():
    local_base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'Axx'/'models'/'faster-whisper-base'
    if getattr(sys,'frozen',False):
        # Existing private models survive upgrades independently of bundled data.
        candidates = [local_base, local_base.with_name('faster-whisper-tiny'),
                      Path(sys.executable).parent/'models'/'faster-whisper-tiny',
                      Path(sys.executable).parent/'resources'/'models'/'faster-whisper-tiny',
                      Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent))/'models'/'faster-whisper-tiny',
                      Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent))/'resources'/'models'/'faster-whisper-tiny']
    else:
        repo_root = Path(__file__).resolve().parents[2]
        hf_snapshots = Path.home()/'.cache'/'huggingface'/'hub'/'models--Systran--faster-whisper-tiny'/'snapshots'
        candidates = [local_base, repo_root/'resources'/'models'/'faster-whisper-tiny',
                      repo_root/'src-tauri'/'resources'/'models'/'faster-whisper-tiny',
                      Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'Axx'/'models'/'faster-whisper-tiny',
                      hf_snapshots/SNAPSHOT]
        if hf_snapshots.is_dir():
            candidates.extend(sorted(p for p in hf_snapshots.iterdir() if p.is_dir()))
    required = ('model.bin','tokenizer.json','config.json','vocabulary.txt')
    return next((p.resolve() for p in candidates if all((p/f).is_file() for f in required)),None)

def _load_worker_model(requested_model):
    global _WORKER_MODEL, _WORKER_MODEL_PATH
    from faster_whisper import WhisperModel
    if _WORKER_MODEL is None or _WORKER_MODEL_PATH != requested_model:
        _WORKER_MODEL = WhisperModel(requested_model,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
        _WORKER_MODEL_PATH = requested_model
    return _WORKER_MODEL


def worker_main(raw=None):
    """Only this isolated process imports the native ASR libraries/model."""
    started=time.monotonic()
    try:
        if raw is None: raw = sys.stdin.buffer.read(MAX_WORKER_REQUEST + 1)
        if len(raw)>MAX_WORKER_REQUEST: raise SpeechError('INVALID_REQUEST','Transcription worker request exceeds limit')
        request = json.loads(raw)
        # CTranslate2 also ships training-format converters. Those optional
        # frameworks are explicitly disabled in this inference-only worker.
        # They are unnecessary for an already converted local CTranslate2 model.
        guard_worker_imports()
        import av
        import numpy as np
        imported=time.monotonic()
        requested_model = request['model_path']
        if request.get('warmup'):
            _load_worker_model(requested_model)
            sys.stdout.buffer.write(json.dumps({'ok':True,'result':{'ready':True,'model':Path(requested_model).name}}).encode('utf-8')+b'\n')
            sys.stdout.buffer.flush()
            return 0
        if 'audio_base64' in request:
            encoded = request['audio_base64']
            if ('audio_path' in request or not isinstance(encoded, str)
                    or not 1 <= len(encoded) <= ((MAX_AUDIO + 2) // 3) * 4):
                raise SpeechError('INVALID_REQUEST','Invalid bounded audio payload')
            try: audio_bytes = base64.b64decode(encoded, validate=True)
            except ValueError: raise SpeechError('INVALID_REQUEST','Audio is not valid base64') from None
            if not 0 < len(audio_bytes) <= MAX_AUDIO: raise SpeechError('INVALID_REQUEST','Audio exceeds byte limit')
            source = io.BytesIO(audio_bytes)
        else:
            path = Path(request['audio_path'])
            if not 0<path.stat().st_size<=MAX_AUDIO: raise SpeechError('INVALID_REQUEST','Audio exceeds byte limit')
            source = str(path)
        pieces=[];samples=0
        with av.open(source) as container:
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
        load_ms=inference_ms=0
        if float(np.sqrt(np.mean(np.square(audio))))<.0001:
            result={'text':'','segments':[],'language':request.get('language'),'language_probability':None,
                    'audio_duration_seconds':round(samples/16000,3),'silence_detected':True}
        else:
            # Reject silence and invalid audio before spending memory/time on a cold model.
            model=_load_worker_model(requested_model)
            loaded=time.monotonic()
            load_ms=round((loaded-decoded)*1000)
            generated,info=model.transcribe(audio,language=request.get('language'),task=request['task'],
                beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=False,max_new_tokens=128,
                initial_prompt=VOICE_CONTEXT if request.get('language') == 'es' and request['task'] == 'transcribe' else None)
            segments=[]
            for segment in generated:
                if len(segments)>=128: raise SpeechError('INVALID_RESPONSE','Too many transcription segments')
                segments.append({'start':round(segment.start,3),'end':round(segment.end,3),'text':segment.text.strip()[:4000]})
            result={'text':' '.join(s['text'] for s in segments).strip(),'segments':segments,
                    'language':info.language,'language_probability':round(info.language_probability,6),
                    'audio_duration_seconds':round(samples/16000,3),'silence_detected':False}
            if excessive_repetition(result['text']):
                raise SpeechError('INVALID_RESPONSE','El dictado repitió palabras varias veces. Repite la orden antes de ejecutar una acción.')
            inference_ms=round((time.monotonic()-loaded)*1000)
        result.update({'engine':'faster-whisper','model':Path(request['model_path']).name.removeprefix('faster-whisper-'),'device':'cpu','compute_type':'int8',
                       'task':request['task'],'translation_target':'en' if request['task']=='translate' else None,
                       'external_calls':0,'automatic_actions':False})
        result['timings_ms']={'imports':round((imported-started)*1000), 'decode':round((decoded-imported)*1000),
                              'model_load':load_ms,'inference':inference_ms,
                              'worker_total':round((time.monotonic()-started)*1000)}
        response,code={'ok':True,'result':result},0
    except Exception as exc:
        response,code={'ok':False,'error':{'code':getattr(exc,'code','PROCESS_FAILURE'),'message':str(exc)[:400]}},1
    encoded=json.dumps(response,ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(encoded)>MAX_WORKER_OUTPUT:
        encoded=b'{"ok":false,"error":{"code":"INVALID_RESPONSE","message":"Transcription output exceeds limit"}}';code=1
    sys.stdout.buffer.write(encoded+b'\n');sys.stdout.buffer.flush()
    return code


def worker_server_main():
    while raw := sys.stdin.buffer.readline(MAX_WORKER_REQUEST + 2):
        worker_main(raw)
        if len(raw)>MAX_WORKER_REQUEST:
            return 1
        raw = None
    return 0

class OfflineTranscriptionService:
    def __init__(self,data_dir):
        self.data_dir=Path(data_dir)/'speech'
        self.model_path=model_path()
        self._busy=threading.Lock();self._lock=threading.Lock();self._active=None
        self._io_lock=threading.Lock();self._worker=None;self._closed=False
        self._requests={};self._used_request_ids=set()

    def status(self):
        return {'engine':'faster-whisper','model':self.model_path.name.removeprefix('faster-whisper-') if self.model_path else 'tiny','available':bool(self.model_path and importlib.util.find_spec('faster_whisper')),
                'device':'cpu','compute_type':'int8','local_only':True,'external_calls':0,'max_duration_seconds':MAX_SECONDS,
                'input_storage':'process_memory','input_transport':'bounded_worker_pipe',
                'busy':self._busy.locked() or self._io_lock.locked(),
                'request_cancel_supported':True,'explicit_request_id_limit':MAX_REQUEST_IDS,
                'context_deadline_max_seconds':60,'legacy_deadline_seconds':90}

    def warm(self):
        if not self.status()['available']: return
        def prepare():
            try:self._execute({'model_path':str(self.model_path),'warmup':True})
            except Exception as exc:LOG.warning('Local transcription warmup failed: %s',exc)
        threading.Thread(target=prepare,name='axx-asr-warmup',daemon=True).start()

    def close(self):
        with self._lock:self._closed=True
        self.cancel_active()
        with self._io_lock:
            self._stop_worker()

    @staticmethod
    def _cancel_locked(request):
        if request.completed or request.cancelled.is_set():return 0
        request.cancelled.set()
        # The ASR lock also guards completion/worker reuse. Never let the next
        # request inherit this process while its captured handle is being killed.
        if request.process is not None:terminate_process_tree(request.process,request.job)
        return 1

    def cancel(self,request_id,*,context_owner=None):
        """Cancel a captured ASR request; an optional internal owner must match."""
        request_id=_request_id(request_id)
        if context_owner is not None and (not isinstance(context_owner,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',context_owner)):
            raise SpeechError('INVALID_REQUEST','Invalid internal transcription owner')
        with self._lock:
            request=self._requests.get(request_id)
            if request is None and self._active is not None and self._active.request_id==request_id:request=self._active
            if request is None or context_owner is not None and request.context_owner!=context_owner:return 0
            return self._cancel_locked(request)

    def cancel_active(self):
        with self._lock:
            requests=list(self._requests.values())
            if self._active is not None and not any(request is self._active for request in requests):requests.append(self._active)
            return sum(self._cancel_locked(request) for request in requests)

    def transcribe(self,body,*,context_owner=None,deadline_mono=None,cancel_event=None):
        """Use RAM/pipe only; internal callers must derive ownership from a valid lease."""
        started=time.monotonic()
        if not isinstance(body,dict) or set(body)-{'audio_base64','mime','language','task','request_id'}: raise SpeechError('INVALID_REQUEST','Unsupported transcription fields')
        if cancel_event is not None and not isinstance(cancel_event,threading.Event):
            raise SpeechError('INVALID_REQUEST','Invalid internal transcription cancellation event')
        if cancel_event is not None and cancel_event.is_set():raise SpeechError('CANCELLED','Local transcription lease was cancelled')
        explicit='request_id' in body
        request_id=_request_id(body['request_id']) if explicit else AUTO_REQUEST_PREFIX+uuid.uuid4().hex
        if explicit and request_id.startswith(AUTO_REQUEST_PREFIX):raise SpeechError('INVALID_REQUEST','Transcription request_id uses a reserved namespace')
        deadline_mono=_context_deadline(context_owner,deadline_mono)
        encoded,mime,language,task=body.get('audio_base64'),body.get('mime'),body.get('language'),body.get('task','transcribe')
        if not isinstance(encoded,str) or not 1<=len(encoded)<=((MAX_AUDIO+2)//3)*4:
            raise SpeechError('INVALID_REQUEST','Invalid bounded audio payload')
        if not isinstance(mime,str) or mime.split(';')[0].lower() not in ('audio/webm','audio/ogg','audio/wav','audio/x-wav','audio/mp4'):
            raise SpeechError('INVALID_REQUEST','Unsupported audio MIME type')
        mime=mime.split(';')[0].lower()
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
        if not self.status()['available']:raise SpeechError('NOT_SUPPORTED','El modelo local de transcripción o su motor no está disponible.')
        if not self._busy.acquire(False):raise SpeechError('BUSY','Local transcription is busy')
        context=None
        try:
            with self._lock:
                if self._closed:raise SpeechError('CANCELLED','Local transcription service is closed')
                if cancel_event is not None and cancel_event.is_set():raise SpeechError('CANCELLED','Local transcription lease was cancelled')
                if explicit:
                    identity=hashlib.sha256(request_id.encode('utf-8')).digest()
                    if identity in self._used_request_ids:raise SpeechError('REQUEST_ID_REUSED','Transcription request_id has already been used; use a new ID')
                    if len(self._used_request_ids)>=MAX_REQUEST_IDS:raise SpeechError('REQUEST_ID_LIMIT','Explicit transcription ID capacity reached; restart the service before using new IDs')
                    self._used_request_ids.add(identity)
                context=_ASRRequest(request_id,context_owner,deadline_mono,cancel_event=cancel_event)
                self._requests[request_id]=context
            request={'audio_base64':encoded,'model_path':str(self.model_path),'language':language,'task':task}
            result=self._execute(request,_context=context,wait_for_io=deadline_mono is None and cancel_event is None)
            if context.is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled')
            result=dict(result)
            result['request_id']=request_id
            result['input_sha256']=hashlib.sha256(raw).hexdigest()
            result.setdefault('timings_ms',{})['service_total']=round((time.monotonic()-started)*1000)
            if context.deadline_mono is not None and time.monotonic()>=context.deadline_mono:
                raise SpeechError('DEADLINE_EXCEEDED','Transcription lease expired before delivery')
            if context.is_cancelled():raise SpeechError('CANCELLED','Local transcription lease was cancelled before delivery')
            return result
        finally:
            if context is not None:
                with self._lock:
                    context.completed=True
                    if self._requests.get(request_id) is context:self._requests.pop(request_id,None)
            self._busy.release()

    def _execute(self,request,*,_context=None,wait_for_io=True):
        context=_context or _ASRRequest(AUTO_REQUEST_PREFIX+uuid.uuid4().hex)
        if not self._io_lock.acquire(blocking=wait_for_io):raise SpeechError('BUSY','Local transcription worker is busy')
        try:
            if self._closed:raise SpeechError('CANCELLED','Local transcription service is closed')
            if context.is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled before dispatch')
            if context.deadline_mono is not None and time.monotonic()>=context.deadline_mono:
                raise SpeechError('DEADLINE_EXCEEDED','Transcription lease already expired')
            if not self._worker or self._worker[0].poll() is not None:
                self._stop_worker()
                command=([sys.executable,'--transcribe-worker'] if getattr(sys,'frozen',False)
                         else [sys.executable,'-m','backend.server','--transcribe-worker'])
                env=os.environ.copy();env.pop('AXX_HOST_TOKEN',None)
                env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
                process,job=spawn_managed_process(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    env=env,cwd=str(Path(__file__).resolve().parents[2]))
                responses=queue.Queue()
                def read_responses():
                    try:
                        while True:
                            line=process.stdout.readline(MAX_WORKER_OUTPUT+1)
                            responses.put(line)
                            if not line or len(line)>MAX_WORKER_OUTPUT:break
                    except (OSError,ValueError):
                        responses.put(b'')
                reader=threading.Thread(target=read_responses,name='axx-asr-output',daemon=True)
                reader.start()
                self._worker=(process,job,responses,reader)
            process,job,responses,reader=self._worker
            is_cancelled=context.is_cancelled;healthy=False
            with self._lock:
                context.process,context.job=process,job
                if self._closed:context.cancelled.set()
                self._active=context
            writer = None
            try:
                encoded=json.dumps(request,ensure_ascii=False).encode('utf-8')
                if len(encoded)>=MAX_WORKER_REQUEST:raise SpeechError('INVALID_REQUEST','Transcription worker request exceeds limit')
                deadline=context.deadline_mono if context.deadline_mono is not None else time.monotonic()+90
                write_errors = queue.Queue(maxsize=1)
                def write_request():
                    try:
                        if not is_cancelled():process.stdin.write(encoded+b'\n');process.stdin.flush()
                    except (OSError,ValueError):write_errors.put(True)
                writer=threading.Thread(target=write_request,name='axx-asr-input',daemon=True)
                writer.start()
                while True:
                    if is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled')
                    if time.monotonic()>=deadline:raise SpeechError('DEADLINE_EXCEEDED','Local transcription exceeded its request deadline')
                    if not write_errors.empty():raise SpeechError('PROCESS_FAILURE','Local transcription worker input failed')
                    try:line=responses.get(timeout=.025)
                    except queue.Empty:
                        if is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled')
                        if process.poll() is not None and not reader.is_alive():
                            raise SpeechError('PROCESS_FAILURE','Local transcription worker exited without a response')
                        continue
                    if is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled')
                    if time.monotonic()>=deadline:raise SpeechError('DEADLINE_EXCEEDED','Local transcription exceeded its request deadline')
                    if not line:raise SpeechError('PROCESS_FAILURE','Local transcription worker returned no response')
                    if len(line)>MAX_WORKER_OUTPUT:raise SpeechError('INVALID_RESPONSE','Transcription output exceeded limit')
                    try:response=json.loads(line)
                    except (ValueError,UnicodeError):raise SpeechError('PROCESS_FAILURE','Local transcription worker returned no valid response') from None
                    if not isinstance(response,dict) or type(response.get('ok')) is not bool:
                        raise SpeechError('INVALID_RESPONSE','Local transcription worker returned an invalid response')
                    if response['ok'] and not isinstance(response.get('result'),dict):
                        raise SpeechError('INVALID_RESPONSE','Local transcription worker returned no result')
                    healthy=True
                    if is_cancelled():raise SpeechError('CANCELLED','Local transcription was cancelled')
                    if not response.get('ok'):
                        error=response.get('error',{});raise SpeechError(error.get('code','PROCESS_FAILURE'),error.get('message','Transcription failed'))
                    return response['result']
            finally:
                with self._lock:
                    context.completed=True
                    if self._active is context:self._active=None
                if not healthy or is_cancelled() or process.poll() is not None:self._stop_worker()
                if writer:
                    writer.join(1)
                    if writer.is_alive():
                        self._stop_worker()
                        writer.join(1)
                        raise SpeechError('PROCESS_FAILURE','Local transcription worker input did not finish')
        finally:
            with self._lock:context.completed=True
            self._io_lock.release()

    def _stop_worker(self):
        if not self._worker:return
        process,job,_,reader=self._worker
        self._worker=None
        if process.poll() is None:terminate_process_tree(process,job)
        if job:job.close()
        reader.join(1)
        for pipe in (process.stdin,process.stdout):
            try:pipe.close()
            except (OSError,ValueError):pass
