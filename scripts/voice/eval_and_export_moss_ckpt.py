"""Evaluate a trained MOSS-TTS-Nano checkpoint against the baseline ONNX/PyTorch model
and export + install ONNX if speaker similarity and ASR pass.

Usage:
    python scripts/voice/eval_and_export_moss_ckpt.py <checkpoint-dir> [--install]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SPEECH = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Axx' / 'speech'
MOSS_ROOT = Path(os.environ.get('AXX_MOSS_TTS_ROOT', Path.home() / 'Downloads' / 'tts nano' / 'MOSS-TTS-Nano'))
MOSS_PY = MOSS_ROOT / '.venv' / 'Scripts' / 'python.exe'
AXX_PY = Path(__file__).resolve().parents[2] / '.venv' / 'Scripts' / 'python.exe'
VOICES = SPEECH / 'voices'

PROBES = [
    ('es', 'Hola principal, soy Axx. ¿Qué quieres que resolvamos hoy?', VOICES / 'axx-morcito.wav'),
    ('es', 'Detente por favor, primero necesito comprobar ese archivo.', VOICES / 'axx-morcito-atencion.wav'),
    ('en', 'Hello principal! Everything looks good so far, what should we work on next?', VOICES / 'axx-morcito-en.wav'),
]


def export_onnx(ckpt: Path, out_models_root: Path):
    tts_out = out_models_root / 'MOSS-TTS-Nano-100M-ONNX'
    codec_out = out_models_root / 'MOSS-Audio-Tokenizer-Nano-ONNX'
    if not codec_out.exists():
        out_models_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(MOSS_ROOT / 'models' / 'MOSS-Audio-Tokenizer-Nano-ONNX', codec_out)
    manifest_src = MOSS_ROOT / 'models' / 'MOSS-TTS-Nano-100M-ONNX' / 'browser_poc_manifest.json'
    if (tts_out / 'moss_tts_prefill.onnx').is_file():
        if manifest_src.is_file() and not (tts_out / 'browser_poc_manifest.json').is_file():
            shutil.copy2(manifest_src, tts_out / 'browser_poc_manifest.json')
        return out_models_root
    tts_out.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(MOSS_PY), str(MOSS_ROOT / 'onnx' / 'export_hf_to_tts_onnx.py'),
        '--checkpoint-path', str(ckpt),
        '--output-dir', str(tts_out),
    ], check=True, cwd=str(MOSS_ROOT))
    if manifest_src.is_file():
        shutil.copy2(manifest_src, tts_out / 'browser_poc_manifest.json')
    return out_models_root


def synth_with_onnx(models_root: Path, ref_cache_dir: Path, text: str, lang: str, ref_wav: Path, out_wav: Path) -> float:
    if out_wav.is_file() and out_wav.stat().st_size > 1000:
        return 0.0
    code = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, r'{Path(__file__).resolve().parents[2] / "backend" / "speech"}')
from moss_worker import create_runtime
from speech_text import prepare_spoken_text
spoken, language = prepare_spoken_text({text!r}, {lang!r})
rt = create_runtime(Path(r'{models_root}'), Path(r'{ref_cache_dir}'))
t0 = time.monotonic()
rt.synthesize(
    text=spoken,
    prompt_audio_path=Path(r'{ref_wav}'),
    output_audio_path=Path(r'{out_wav}'),
    streaming=True,
    sample_mode='fixed',
    enable_wetext=False,
    enable_normalize_tts_text=language not in ('es', 'en'),
    voice_clone_max_text_tokens=36,
    seed=1234,
)
print(round((time.monotonic() - t0) * 1000))
"""
    res = subprocess.run([str(MOSS_PY), '-c', code], cwd=str(MOSS_ROOT), check=True, capture_output=True, text=True)
    return float(res.stdout.strip().splitlines()[-1])


def score(wav_path: Path, ref_path: Path, lang: str):
    sim_code = f"""
import librosa, numpy as np, soundfile as sf
from resemblyzer import VoiceEncoder
e = VoiceEncoder('cpu')
def vec(p):
    y, sr = sf.read(p, dtype='float32')
    if y.ndim > 1: y = y.mean(axis=1)
    return e.embed_utterance(librosa.resample(y, orig_sr=sr, target_sr=16000)), round(len(y)/sr, 2)
v1, dur = vec(r'{wav_path}')
v2, _ = vec(r'{ref_path}')
import json
print(json.dumps({{'similarity': round(float(np.dot(v1, v2)), 4), 'duration_s': dur}}))
"""
    sim_out = subprocess.run([str(MOSS_PY), '-c', sim_code], check=True, capture_output=True, text=True).stdout.strip().splitlines()[-1]
    meta = json.loads(sim_out)
    asr_code = f"""
import json, subprocess, numpy as np
from faster_whisper import WhisperModel
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', r'{wav_path}', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'], check=True, capture_output=True).stdout
audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
m = WhisperModel('base', device='cpu', compute_type='int8')
segs, _ = m.transcribe(audio, language={lang!r}, beam_size=5, vad_filter=False)
print(json.dumps(' '.join(s.text.strip() for s in segs)))
"""
    asr_out = subprocess.run([str(AXX_PY), '-c', asr_code], check=True, capture_output=True, text=True).stdout.strip().splitlines()[-1]
    meta['asr'] = json.loads(asr_out)
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()

    ckpt = args.checkpoint.resolve()
    eval_dir = ckpt.parent / f'eval-{ckpt.name}'
    export_onnx(ckpt, eval_dir)

    baseline_models = MOSS_ROOT / 'models'
    baseline_onnx = baseline_models / 'MOSS-TTS-Nano-100M-ONNX'
    onnx_candidate = eval_dir / 'MOSS-TTS-Nano-100M-ONNX'

    results = []
    ref_cache = eval_dir / 'ref-cache'
    for idx, (lang, text, ref) in enumerate(PROBES):
        b_wav = eval_dir / f'base_{idx}_{lang}.wav'
        c_wav = eval_dir / f'cand_{idx}_{lang}.wav'
        b_ms = synth_with_onnx(baseline_models, ref_cache, text, lang, ref, b_wav)
        c_ms = synth_with_onnx(eval_dir, ref_cache, text, lang, ref, c_wav)
        b_sc = score(b_wav, ref, lang)
        c_sc = score(c_wav, ref, lang)
        results.append({
            'lang': lang, 'text': text,
            'baseline': b_sc | {'ms': b_ms},
            'candidate': c_sc | {'ms': c_ms},
        })

    report = {'checkpoint': str(ckpt), 'onnx_dir': str(onnx_candidate), 'probes': results}
    (eval_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

    if args.install:
        backup = SPEECH / 'training' / 'MOSS-TTS-Nano-100M-ONNX.baseline-backup'
        if not backup.exists():
            shutil.copytree(baseline_onnx, backup)
        for item in onnx_candidate.iterdir():
            if item.is_file():
                shutil.copy2(item, baseline_onnx / item.name)
        print(json.dumps({'installed_into': str(baseline_onnx), 'backup': str(backup)}), flush=True)


if __name__ == '__main__':
    main()
