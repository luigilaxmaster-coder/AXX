"""Private persistent MOSS worker: incremental PCM and cooperative cancellation."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

if __package__:
    from .speech_text import prepare_spoken_text
else:
    from speech_text import prepare_spoken_text

PERSONAL_VOICES = (
    'axx-valeria', 'axx-elena', 'axx-mateo', 'axx-dante',
    'axx-alba', 'axx-nova', 'axx-aura', 'axx-titan'
)
FALLBACK_VOICES = ('voz_referencia', 'voz_referencia_completo')


class SynthesisCancelled(Exception):
    pass


class WarmupComplete(Exception):
    pass


def create_runtime(model_root, cache_root):
    import numpy as np
    import onnxruntime as ort
    from onnx_tts_runtime import OnnxTtsRuntime

    class StreamingRuntime(OnnxTtsRuntime):
        def __init__(self, **kwargs):
            self.reference_codes = {}
            self.emit_pcm = None
            self.cancelled = threading.Event()
            super().__init__(**kwargs)

        def _session(self, path_value):
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = self.thread_count
            options.inter_op_num_threads = 1
            # Idle session pools must not compete with the active decoder/LLM.
            options.add_session_config_entry('session.intra_op.allow_spinning', '0')
            options.add_session_config_entry('session.inter_op.allow_spinning', '0')
            return ort.InferenceSession(str(path_value), sess_options=options, providers=['CPUExecutionProvider'])

        def _create_sessions(self):
            tts, codec = self.tts_meta_path.parent, self.codec_meta_path.parent
            # Fixed sampling is the supplied model's default; other decoder
            # variants need not be loaded just to synthesize this mode.
            return {name: self._session(folder / files[key]) for name, folder, files, key in (
                ('prefill', tts, self.tts_meta['files'], 'prefill'),
                ('decode', tts, self.tts_meta['files'], 'decode_step'),
                ('local_fixed_sampled_frame', tts, self.tts_meta['files'], 'local_fixed_sampled_frame'),
                ('codec_encode', codec, self.codec_meta['files'], 'encode'),
                ('codec_decode_step', codec, self.codec_meta['files'], 'decode_step'),
            )}

        def encode_reference_audio(self, reference_audio_path):
            path = Path(reference_audio_path).resolve()
            codec_files = sorted(self.codec_meta_path.parent.glob('*'))
            signature = '|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                 for p in codec_files if p.is_file())
            key = hashlib.sha256(path.read_bytes() + signature.encode()).hexdigest()
            if key not in self.reference_codes:
                cache = cache_root / (key + '.json')
                try:
                    codes = json.loads(cache.read_text(encoding='utf-8'))
                    if not isinstance(codes, list) or not 1 <= len(codes) <= 2000 or any(
                            not isinstance(row, list) or len(row) != 16 or any(type(v) is not int or not 0 <= v < 1024 for v in row)
                            for row in codes):
                        raise ValueError('Invalid reference code cache')
                except (OSError, ValueError):
                    codes = super().encode_reference_audio(path)
                    cache_root.mkdir(parents=True, exist_ok=True)
                    temp = cache.with_suffix('.tmp')
                    temp.write_text(json.dumps(codes), encoding='utf-8')
                    temp.replace(cache)
                self.reference_codes[key] = codes
            return self.reference_codes[key]

        def synthesize_single_chunk(self, *, text, prompt_audio_codes, streaming):
            tokens = self.encode_text(text)
            rows = self.build_voice_clone_request_rows(prompt_audio_codes, tokens)
            pending, waveforms = [], []
            emitted = 0
            rate = int(self.codec_meta['codec_config']['sample_rate'])
            self.codec_streaming_session.reset()

            def decode(force=False):
                nonlocal emitted
                budget = 1 if emitted == 0 else 4
                if not pending or (not force and len(pending) < budget):
                    return
                frames = list(pending)
                pending.clear()
                decoded = self.codec_streaming_session.run_frames(frames)
                if decoded is None:
                    return
                audio, length = decoded
                if length <= 0:
                    return
                waveform = np.asarray(audio[0, :, :length].T, dtype=np.float32)
                waveforms.append(waveform)
                emitted += length
                if self.emit_pcm:
                    self.emit_pcm(np.clip(waveform * 32767, -32768, 32767).astype('<i2').tobytes(), rate, waveform.shape[1])

            def on_frame(_frames, _index, frame):
                if self.cancelled.is_set():
                    raise SynthesisCancelled()
                pending.append(list(frame))
                decode()

            try:
                if self.cancelled.is_set():
                    raise SynthesisCancelled()
                frames = self.generate_audio_frames(rows, on_frame=on_frame)
                decode(True)
                if self.cancelled.is_set():
                    raise SynthesisCancelled()
            finally:
                self.codec_streaming_session.reset()
            channels = int(self.codec_meta['codec_config']['channels'])
            waveform = np.concatenate(waveforms) if waveforms else np.zeros((0, channels), dtype=np.float32)
            return {'text': text, 'text_token_ids': tokens, 'generated_frames': frames, 'waveform': waveform}

        def estimate_voice_clone_inter_chunk_pause_seconds(self, text_chunk):
            # Upstream adds this pause only to the completed WAV. Streaming must
            # receive the same boundary, or long sentences run together.
            stripped = str(text_chunk).rstrip()
            if stripped.endswith(('?', '¿', '!', '¡')):
                seconds = .36
            elif stripped.endswith((',', ';', ':')):
                seconds = .24
            else:
                seconds = .32
            if self.emit_pcm:
                rate = int(self.codec_meta['codec_config']['sample_rate'])
                channels = int(self.codec_meta['codec_config']['channels'])
                self.emit_pcm(bytes(round(rate * seconds) * channels * 2), rate, channels)
            return seconds

    threads = max(1, min(8, int(os.environ.get('AXX_MOSS_THREADS', str(min(4, os.cpu_count() or 2))))))
    return StreamingRuntime(model_dir=model_root, thread_count=threads, execution_provider='cpu')


def main():
    model_root, personal_samples, output_root = (Path(p).resolve() for p in sys.argv[1:4])
    sys.path.insert(0, str(model_root.parent))
    started = time.monotonic()
    runtime = create_runtime(model_root, output_root.parent / 'reference-cache')
    voices = {}
    for name in PERSONAL_VOICES:
        target = personal_samples / f'{name}.wav'
        if not target.is_file():
            fallback = model_root.parent / 'samples' / f'{name}.wav'
            if fallback.is_file():
                target = fallback
        voices[f'moss:{name}'] = target
    voices.update({f'moss:{name}': model_root.parent / 'samples' / f'{name}.wav' for name in FALLBACK_VOICES})
    output_root.mkdir(parents=True, exist_ok=True)
    requests, events, event_lock = queue.Queue(maxsize=2), {}, threading.Lock()

    def receive():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                request_id = request['id']
                if not isinstance(request_id, str) or not request_id.isascii() or not request_id.isalnum() or len(request_id) > 32:
                    continue
                with event_lock:
                    if request.get('cancel'):
                        if request_id in events:
                            events[request_id].set()
                        continue
                    event = threading.Event()
                    events[request_id] = event
                requests.put((request, event))
            except (ValueError, KeyError, TypeError):
                continue
        requests.put(None)

    threading.Thread(target=receive, daemon=True).start()
    print(json.dumps({'ready': True, 'startup_ms': round((time.monotonic() - started) * 1000)}), flush=True)
    while True:
        entry = requests.get()
        if entry is None:
            break
        request, runtime.cancelled = entry
        request_id = request['id']
        output = output_root / f'{request_id}.wav'
        started = time.monotonic()
        try:
            voice = voices[request['voice']]
            if request.get('prepare'):
                codes = runtime.encode_reference_audio(voice)
                # Ready means the actual prefill, frame and PCM decoder have
                # executed, not merely that their ONNX sessions were allocated.
                rng_state = runtime.rng.bit_generator.state
                def warm_pcm(*_):
                    raise WarmupComplete()
                runtime.emit_pcm = warm_pcm
                try:
                    runtime.synthesize_single_chunk(text='Hola. Hello.', prompt_audio_codes=codes, streaming=True)
                except WarmupComplete:
                    pass
                finally:
                    runtime.rng.bit_generator.state = rng_state
                    runtime.emit_pcm = None
                print(json.dumps({'id': request_id, 'ok': True}), flush=True)
                continue
            text = request['text']
            if not voice.is_file() or not isinstance(text, str) or not 1 <= len(text.strip()) <= 220 or '\x00' in text:
                raise ValueError('Invalid speech request')

            def emit(raw, rate, channels):
                print(json.dumps({'id': request_id, 'chunk': True, 'pcm_base64': base64.b64encode(raw).decode('ascii'),
                                  'sample_rate': rate, 'channels': channels,
                                  'elapsed_ms': round((time.monotonic() - started) * 1000)}), flush=True)

            runtime.emit_pcm = emit if request.get('stream') else None
            spoken, language = prepare_spoken_text(text, request.get('language', 'auto'))
            runtime.synthesize(text=spoken, prompt_audio_path=voice, output_audio_path=output,
                               streaming=True, sample_mode='fixed', enable_wetext=False,
                               enable_normalize_tts_text=language not in ('es', 'en'),
                               voice_clone_max_text_tokens=36)
            print(json.dumps({'id': request_id, 'ok': True,
                              'elapsed_ms': round((time.monotonic() - started) * 1000)}), flush=True)
        except SynthesisCancelled:
            print(json.dumps({'id': request_id, 'ok': False, 'cancelled': True}), flush=True)
        except Exception:
            print(json.dumps({'id': request_id, 'ok': False}), flush=True)
        finally:
            runtime.emit_pcm = None
            if request.get('stream'):
                output.unlink(missing_ok=True)
            with event_lock:
                events.pop(request_id, None)


if __name__ == '__main__':
    main()
