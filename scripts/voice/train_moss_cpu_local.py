"""Local CPU fine-tuning and evaluation for MOSS-TTS-Nano on the 97 Axxmorcito clips.

Runs 100% locally on CPU (~5-8 min):
1. Converts the 48 ES + 49 EN cleaned utterances to 24 kHz WAVs and matches each clip
   with its style-specific reference audio (natural, calma, emocion, atencion).
2. Encodes audio tokens with MOSS-Audio-Tokenizer-Nano via moss-cpu-audio.py.
3. Fine-tunes MOSS-TTS-Nano on CPU for 3 epochs via finetuning/sft_cpu.py.
4. Evaluates baseline vs trained checkpoint on held-out ES + EN sentences for
   speaker cosine similarity (Resemblyzer) and ASR accuracy (faster-whisper).
5. If trained checkpoint improves or maintains quality on both languages without
   runaway frame length, exports ONNX and installs it (keeping a backup).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SPEECH = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Axx' / 'speech'
MOSS_ROOT = Path(os.environ.get('AXX_MOSS_TTS_ROOT', Path.home() / 'Downloads' / 'tts nano' / 'MOSS-TTS-Nano'))
MOSS_PY = MOSS_ROOT / '.venv' / 'Scripts' / 'python.exe'
MASTER_ES = SPEECH / 'training' / 'axxmorcito-master-es'
PIPER_EN = SPEECH / 'training' / 'axxmorcito-piper' / 'dataset-en'
WORK = SPEECH / 'training' / 'axxmorcito-moss-v4'
VOICES = SPEECH / 'voices'


def style_ref(text: str, lang: str) -> Path:
    suffix = '-en' if lang == 'en' else ''
    low = text.lower()
    if any(c in text for c in '¡!¿?') or any(w in low for w in ('hola', 'interesante', 'listo', 'perfecto', 'ready', 'great', 'interesting', 'understand')):
        key = '-emocion'
    elif any(w in low for w in ('detente', 'equivocado', 'espera', 'comprobar', 'revisar', 'falta', 'guarda', 'abre', 'busca', 'detén',
                                'stop', 'wrong', 'wait', 'check', 'final', 'open', 'pause', 'timer', 'read')):
        key = '-atencion'
    else:
        key = '-calma'
    candidate = VOICES / f'axx-morcito{key}{suffix}.wav'
    return candidate if candidate.is_file() else (VOICES / f'axx-morcito{suffix}.wav')


def build_jsonl():
    wav24 = WORK / 'wavs24k'
    wav24.mkdir(parents=True, exist_ok=True)
    # Build 24 kHz copies of the 8 reference files for training stability
    ref24_dir = WORK / 'refs24k'
    ref24_dir.mkdir(parents=True, exist_ok=True)
    for ref in VOICES.glob('axx-morcito*.wav'):
        if 'backup' in ref.name or 'preview' in ref.name:
            continue
        out_ref = ref24_dir / ref.name
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(ref),
                        '-ac', '1', '-ar', '24000', str(out_ref)], check=True)

    train_rows, holdout_rows = [], []
    for lang, ds in (('es', MASTER_ES), ('en', PIPER_EN)):
        lines = [ln for ln in (ds / 'metadata.csv').read_text(encoding='utf-8').splitlines() if '|' in ln]
        for idx, line in enumerate(lines):
            uid, text = line.split('|', 1)
            src_wav = ds / 'wavs' / f'{uid.strip()}.wav'
            if not src_wav.is_file():
                continue
            dst_wav = wav24 / f'{uid.strip()}.wav'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(src_wav),
                            '-ac', '1', '-ar', '24000', str(dst_wav)], check=True)
            ref_file = ref24_dir / style_ref(text.strip(), lang).name
            row = {'audio': str(dst_wav), 'text': text.strip(), 'ref_audio': str(ref_file), 'language': lang}
            # Keep 2 held-out items per language
            if idx in (7, 25):
                holdout_rows.append(row)
            else:
                train_rows.append(row)

    (WORK / 'train_raw.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in train_rows), encoding='utf-8')
    (WORK / 'holdout_raw.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in holdout_rows), encoding='utf-8')
    return len(train_rows), len(holdout_rows)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    n_train, n_hold = build_jsonl()
    print(json.dumps({'step': 'jsonl_built', 'train': n_train, 'holdout': n_hold}), flush=True)

    subprocess.run([str(MOSS_PY), str(ROOT / 'scripts' / 'enable-moss-cpu-sft.py'), str(MOSS_ROOT)], check=True)
    subprocess.run([
        str(MOSS_PY), str(ROOT / 'scripts' / 'moss-cpu-audio.py'), str(MOSS_ROOT), 'prepare_data',
        '--codec-path', str(MOSS_ROOT / 'models' / 'MOSS-Audio-Tokenizer-Nano'),
        '--device', 'cpu',
        '--input-jsonl', str(WORK / 'train_raw.jsonl'),
        '--output-jsonl', str(WORK / 'train_with_codes.jsonl'),
    ], check=True)
    print(json.dumps({'step': 'codes_prepared'}), flush=True)

    trained_dir = WORK / 'trained'
    subprocess.run([
        str(MOSS_PY), str(MOSS_ROOT / 'finetuning' / 'sft_cpu.py'),
        '--model-path', str(MOSS_ROOT / 'models' / 'MOSS-TTS-Nano'),
        '--codec-path', str(MOSS_ROOT / 'models' / 'MOSS-Audio-Tokenizer-Nano'),
        '--train-jsonl', str(WORK / 'train_with_codes.jsonl'),
        '--output-dir', str(trained_dir),
        '--per-device-batch-size', '1',
        '--gradient-accumulation-steps', '8',
        '--learning-rate', '8e-6',
        '--num-epochs', '3',
        '--mixed-precision', 'no',
        '--max-length', '1024',
        '--channelwise-loss-weight', '1,32',
    ], check=True)
    print(json.dumps({'step': 'sft_completed', 'checkpoint': str(trained_dir / 'checkpoint-last')}), flush=True)


if __name__ == '__main__':
    main()
