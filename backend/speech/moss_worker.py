"""Private persistent MOSS worker: incremental PCM, context-aware voice shifts, and cooperative cancellation."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time

if __package__:
    from .speech_text import prepare_spoken_text, resolve_language
else:
    from speech_text import prepare_spoken_text, resolve_language

try:
    if __package__:
        from .prosody import ProsodyAnalyzer, HumanizerDSP
    else:
        from prosody import ProsodyAnalyzer, HumanizerDSP
except ImportError:
    ProsodyAnalyzer = None
    HumanizerDSP = None

PERSONAL_VOICES = (
    'axx-morcito', 'axx-morcito-calma', 'axx-morcito-emocion', 'axx-morcito-atencion',
    'axx-sam',
    'axx-valeria', 'axx-elena', 'axx-mateo', 'axx-dante',
    'axx-alba', 'axx-nova', 'axx-aura', 'axx-titan'
)
FALLBACK_VOICES = ('voz_referencia', 'voz_referencia_completo')


class SynthesisCancelled(Exception):
    pass


class WarmupComplete(Exception):
    pass


class _SilentChunkRetry(Exception):
    pass


def create_runtime(model_root, cache_root):
    import numpy as np
    import onnxruntime as ort
    from onnx_tts_runtime import OnnxTtsRuntime

    class StreamingRuntime(OnnxTtsRuntime):
        def __init__(self, **kwargs):
            self.reference_codes = {}
            self.mood_reference_codes = {}
            self.emit_pcm = None
            self.cancelled = threading.Event()
            super().__init__(**kwargs)

        def _session(self, path_value):
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = self.thread_count
            options.inter_op_num_threads = 1
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
                # Cap reference prompt to 96 frames (~7.68s) so complete reference sentences stay intact without mid-word truncation
                self.reference_codes[key] = codes[:96] if isinstance(codes, list) else codes
            return self.reference_codes[key]

        def synthesize_single_chunk(self, *, text, prompt_audio_codes, streaming):
            chunk_mood = ProsodyAnalyzer.detect_mood(text) if ProsodyAnalyzer is not None else 'neutral'
            mood_vol = (
                ProsodyAnalyzer.MOOD_PROFILES.get(chunk_mood, (0.0, 1.0))[1]
                if ProsodyAnalyzer is not None else 1.0
            )
            clean_text = re.sub(r'^[¡¿\s]+', '', text).strip() or text.strip()
            rate = int(self.codec_meta['codec_config']['sample_rate'])
            channels = int(self.codec_meta['codec_config']['channels'])
            expected_frames = max(16.0, float(len(clean_text)) * 0.85)
            overlap_len = max(64, int(0.005 * rate))

            defaults = self.manifest.get('generation_defaults') or {}
            old_max = defaults.get('max_new_frames', 375)
            char_len = len(clean_text)
            frames = []
            tokens = []
            waveforms = []

            for attempt in range(3):
                active_codes = (
                    self.mood_reference_codes.get(chunk_mood, prompt_audio_codes)
                    if attempt == 0 else prompt_audio_codes
                )
                attempt_text = clean_text if attempt == 0 else (
                    clean_text if clean_text[-1:] in '.!?' else clean_text + '.'
                )
                tokens = self.encode_text(attempt_text)
                rows = self.build_voice_clone_request_rows(active_codes, tokens)
                pending, waveforms = [], []
                emitted = 0
                decoded_frames = 0
                silent_lead_frames = 0
                prev_tail = None
                self.codec_streaming_session.reset()
                defaults['max_new_frames'] = min(
                    int(old_max),
                    max(28, min(len(tokens) * 4 + 12, int(char_len * 1.30) + 14))
                )

                def decode(force=False):
                    nonlocal emitted, decoded_frames, silent_lead_frames, prev_tail
                    budget = 3 if emitted == 0 else 4
                    if not pending or (not force and len(pending) < budget):
                        return
                    frames_batch = list(pending)
                    pending.clear()
                    decoded = self.codec_streaming_session.run_frames(frames_batch)
                    if decoded is None:
                        return
                    audio, length = decoded
                    if length <= 0:
                        return
                    waveform = np.asarray(audio[0, :, :length].T, dtype=np.float32)
                    raw_rms = float(np.sqrt(np.mean(waveform ** 2))) if len(waveform) else 0.0
                    if emitted == 0 and raw_rms < 0.0065:
                        silent_lead_frames += len(frames_batch)
                        if not force:
                            if silent_lead_frames >= 6 and attempt < 2:
                                raise _SilentChunkRetry()
                            return
                        if attempt < 2:
                            raise _SilentChunkRetry()

                    u0 = min(0.92, float(decoded_frames) / expected_frames)
                    decoded_frames += len(frames_batch)
                    u1 = 1.0 if force else min(0.98, float(decoded_frames) / expected_frames)
                    if u1 <= u0:
                        u1 = min(1.0, u0 + 0.12)

                    if HumanizerDSP is not None and len(waveform) >= 256:
                        processed_cols = []
                        for ch_idx in range(waveform.shape[1]):
                            col = waveform[:, ch_idx]
                            if emitted == 0:
                                col = HumanizerDSP.trim_silence(col, rate, threshold=0.0040, head_ms=12, tail_ms=24)
                            col = HumanizerDSP.apply_natural_intonation_warp(
                                col, rate, mood=chunk_mood, base_cents=0.0, u_start=u0, u_end=u1
                            )
                            col = HumanizerDSP.apply_dynamic_timbre_contour(
                                col, rate, mood=chunk_mood, u_start=u0, u_end=u1
                            )
                            if abs(mood_vol - 1.0) >= 0.02:
                                col = col * mood_vol
                            col = HumanizerDSP.apply_vocal_warmth_eq(col, rate, mood=chunk_mood, engine='moss')
                            processed_cols.append(col)
                        min_len = min(len(c) for c in processed_cols)
                        waveform = np.column_stack([c[:min_len] for c in processed_cols]).astype(np.float32)

                    if prev_tail is not None and len(waveform) > overlap_len:
                        alpha = (0.5 - 0.5 * np.cos(np.pi * np.arange(overlap_len, dtype=np.float32) / overlap_len))[:, None]
                        waveform[:overlap_len] = prev_tail * (1.0 - alpha) + waveform[:overlap_len] * alpha
                        prev_tail = None

                    if not force and len(waveform) > overlap_len * 2:
                        prev_tail = waveform[-overlap_len:].copy()
                        waveform = waveform[:-overlap_len]
                    elif force:
                        if prev_tail is not None and len(waveform) <= overlap_len:
                            waveform = np.concatenate([prev_tail, waveform], axis=0)
                            prev_tail = None
                        if len(waveform) > 64:
                            fade_len = min(int(0.025 * rate), len(waveform) // 3)
                            if fade_len > 0:
                                waveform[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)[:, None]

                    if len(waveform) == 0:
                        return
                    waveforms.append(waveform)
                    emitted += len(waveform)
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
                    if prev_tail is not None and len(prev_tail) > 0:
                        fade_len = len(prev_tail)
                        prev_tail *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)[:, None]
                        waveforms.append(prev_tail)
                        if self.emit_pcm:
                            self.emit_pcm(np.clip(prev_tail * 32767, -32768, 32767).astype('<i2').tobytes(), rate, prev_tail.shape[1])
                        prev_tail = None
                    if self.cancelled.is_set():
                        raise SynthesisCancelled()
                    break
                except _SilentChunkRetry:
                    self.rng.random()
                    continue
                finally:
                    defaults['max_new_frames'] = old_max
                    self.codec_streaming_session.reset()

            waveform = np.concatenate(waveforms) if waveforms else np.zeros((0, channels), dtype=np.float32)
            return {'text': text, 'text_token_ids': tokens, 'generated_frames': frames, 'waveform': waveform}

        def estimate_voice_clone_inter_chunk_pause_seconds(self, text_chunk):
            # Context-aware inter-chunk breath pause aligned with original human cadence
            stripped = str(text_chunk).rstrip()
            chunk_mood = ProsodyAnalyzer.detect_mood(stripped) if ProsodyAnalyzer is not None else 'neutral'
            if chunk_mood == 'serious':
                seconds = .22
            elif chunk_mood in ('affectionate', 'reflective'):
                seconds = .18
            elif chunk_mood == 'intro':
                seconds = .09
            elif stripped.endswith(('?', '¿', '!', '¡')):
                seconds = .16
            elif stripped.endswith((',', ';', ':')):
                seconds = .07
            else:
                seconds = .14
            if self.emit_pcm:
                rate = int(self.codec_meta['codec_config']['sample_rate'])
                channels = int(self.codec_meta['codec_config']['channels'])
                self.emit_pcm(bytes(round(rate * seconds) * channels * 2), rate, channels)
            return seconds

    default_threads = str(min(6, max(4, (os.cpu_count() or 6) - 2)))
    threads = max(2, min(8, int(os.environ.get('AXX_MOSS_THREADS', default_threads))))
    return StreamingRuntime(model_dir=model_root, thread_count=threads, execution_provider='cpu')


def main():
    model_root, personal_samples, output_root = (Path(p).resolve() for p in sys.argv[1:4])
    sys.path.insert(0, str(model_root.parent))
    started = time.monotonic()
    runtime = create_runtime(model_root, output_root.parent / 'reference-cache')
    voices = {f'moss:{name}': name for name in (*PERSONAL_VOICES, *FALLBACK_VOICES)}
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
            name = voices[request['voice']]
            voice = model_root.parent / 'samples' / f'{name}.wav'
            personal = personal_samples / f'{name}.wav'
            # Match the service's current reference instead of its startup path.
            if name in PERSONAL_VOICES and personal.is_file():
                voice = personal
            # Axxmorcito styles may ship their own English reference; otherwise
            # they share the base English clip.
            morcito = name.startswith('axx-morcito')
            english = personal_samples / f'{name}-en.wav'
            if morcito and not english.is_file():
                english = personal_samples / 'axx-morcito-en.wav'
            is_english = (
                morcito and not request.get('prepare') and english.is_file()
                and resolve_language(request.get('text', ''), request.get('language', 'auto')) == 'en'
            )
            if is_english:
                voice = english

            # Populate mood-specific reference codes for automatic contextual shifts on base axx-morcito
            runtime.mood_reference_codes = {}
            if morcito:
                for mood_names, style_file in (
                    (('serious', 'analytical', 'affectionate', 'reflective'), personal_samples / 'axx-morcito-calma.wav'),
                    (('question', 'intro'), personal_samples / 'axx-morcito-atencion.wav'),
                    (('excited',), personal_samples / 'axx-morcito-emocion.wav'),
                ):
                    if style_file.is_file() and (request.get('prepare') or (name == 'axx-morcito' and not is_english)):
                        try:
                            scodes = runtime.encode_reference_audio(style_file)
                            if name == 'axx-morcito' and not is_english:
                                for m_name in mood_names:
                                    runtime.mood_reference_codes[m_name] = scodes
                        except Exception:
                            pass

            if request.get('prepare'):
                codes = runtime.encode_reference_audio(voice)
                if morcito and english.is_file():
                    runtime.encode_reference_audio(english)
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
            if not voice.is_file() or not isinstance(text, str) or not 1 <= len(text.strip()) <= 360 or '\x00' in text:
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
                               voice_clone_max_text_tokens=84)
            print(json.dumps({'id': request_id, 'ok': True,
                              'elapsed_ms': round((time.monotonic() - started) * 1000)}), flush=True)
        except SynthesisCancelled:
            print(json.dumps({'id': request_id, 'ok': False, 'cancelled': True}), flush=True)
        except Exception:
            print(json.dumps({'id': request_id, 'ok': False}), flush=True)
        finally:
            runtime.emit_pcm = None
            runtime.mood_reference_codes = {}
            if request.get('stream'):
                output.unlink(missing_ok=True)
            with event_lock:
                events.pop(request_id, None)


if __name__ == '__main__':
    main()
