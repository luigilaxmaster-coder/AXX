"""CPU sidecar bridge. Parent ASR supervisor owns deadline and tree cancellation."""
import json
import subprocess
from .dictation_models import cpp_binary, verify_cpp_model
from .windows_tts import SpeechError
from backend.inference.process_manager import spawn_managed_process, terminate_process_tree

_worker = None
_identity = None


def unload():
    global _worker, _identity
    if _worker:
        process, job = _worker
        if process.poll() is None: terminate_process_tree(process, job)
        if job: job.close()
        for pipe in (process.stdin, process.stdout): pipe.close()
    _worker = _identity = None


def transcribe(audio, request):
    global _worker, _identity
    import numpy as np
    path = request['model_path']
    from pathlib import Path
    stat = Path(path).stat()
    identity = (path, stat.st_size, stat.st_mtime_ns)
    if identity != _identity or not _worker or _worker[0].poll() is not None:
        unload(); verify_cpp_model(path)
        process, job = spawn_managed_process([str(cpp_binary())], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        _worker = process, job; _identity = identity
    process, _ = _worker
    header = {'model_path': path, 'language': request.get('language'), 'task': request['task'] if audio is not None else 'prepare', 'samples': len(audio) if audio is not None else 0}
    process.stdin.write(json.dumps(header).encode('utf-8') + b'\n')
    if audio is not None: process.stdin.write(np.asarray(audio, dtype='<f4').tobytes())
    process.stdin.flush()
    received = 0
    while received <= 256 * 1024:
        line = process.stdout.readline(256 * 1024 + 1); received += len(line)
        if not line: raise SpeechError('PROCESS_FAILURE', 'Native ASR worker exited')
        if line.startswith(b'AXX_ASR_V1 '):
            try: result = json.loads(line[11:])
            except (ValueError, UnicodeError): raise SpeechError('INVALID_RESPONSE', 'Native ASR protocol failure') from None
            if not result.get('ok'): raise SpeechError('PROCESS_FAILURE', 'Native model could not transcribe this segment')
            return result['result']
    raise SpeechError('INVALID_RESPONSE', 'Native ASR output exceeded limit')
