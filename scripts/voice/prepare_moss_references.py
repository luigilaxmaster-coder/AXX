"""Build 48 kHz mono reference clips for MOSS Axxmorcito style voices.

Usage:
    python scripts/voice/prepare_moss_references.py --dataset-es DIR --dataset-en DIR --out VOICES_DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import wave

import numpy as np

RATE = 48000
# Gently upsample 22.05 kHz already-cleaned utterances to 48 kHz with crisp presence
RESAMPLE = 'aresample=48000:resampler=soxr,loudnorm=I=-19:TP=-1.5:LRA=9'


def load_48k(wav_path: Path) -> np.ndarray:
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(wav_path), '-af', RESAMPLE,
                          '-ac', '1', '-ar', str(RATE), '-f', 's16le', '-'],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def apply_fade(pcm: np.ndarray) -> np.ndarray:
    out = pcm.astype(np.float32).copy()
    fi = min(int(0.02 * RATE), len(out) // 4)
    fo = min(int(0.035 * RATE), len(out) // 4)
    if fi > 0:
        out[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
    if fo > 0:
        out[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
    return np.clip(out, -32768, 32767).astype(np.int16)


def concat_clips(wavs_dir: Path, rows: list[dict], target_sec: float = 3.2) -> np.ndarray:
    pieces = []
    pause = np.zeros(int(0.14 * RATE), dtype=np.int16)
    tail = np.zeros(int(0.12 * RATE), dtype=np.int16)
    total = 0.0
    for row in rows:
        wav_path = wavs_dir / f"{row['id']}.wav"
        if not wav_path.is_file():
            continue
        pcm = apply_fade(load_48k(wav_path))
        dur = len(pcm) / RATE
        if not 1.8 <= dur <= 4.8:
            continue
        if pieces and total + dur > 4.6:
            break
        pieces.append(pcm)
        pieces.append(pause)
        total += dur + 0.14
        if total >= target_sec:
            break
    return np.concatenate(pieces[:-1] + [tail]) if pieces else np.zeros(RATE, dtype=np.int16)


def save_wav(path: Path, pcm: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


def pick_styles(rows: list[dict]):
    emocion = [r for r in rows if any(c in r['text'] for c in '¡!¿?') or
               any(w in r['text'].lower() for w in ('hola', 'interesante', 'listo', 'perfecto', 'ready', 'great', 'interesting', 'understand'))]
    atencion = [r for r in rows if any(w in r['text'].lower() for w in (
        'detente', 'equivocado', 'espera', 'comprobar', 'revisar', 'falta', 'guarda', 'abre', 'busca', 'detén',
        'stop', 'wrong', 'wait', 'check', 'final', 'open', 'pause', 'timer', 'read'))]
    calma = [r for r in rows if r not in emocion and r not in atencion]
    greeting = [r for r in rows if any(w in r['text'].lower() for w in ('principal', 'what would you like', 'qué quieres', 'entendido', 'understood'))]
    base = greeting + [r for r in rows if r not in greeting]
    return {
        '': base,
        '-calma': calma or rows,
        '-emocion': emocion or rows,
        '-atencion': atencion or rows,
    }


def build_lang(dataset_dir: Path, out_dir: Path, suffix: str):
    rows = []
    for line in (dataset_dir / 'metadata.csv').read_text(encoding='utf-8').splitlines():
        if '|' in line:
            uid, text = line.split('|', 1)
            rows.append({'id': uid.strip(), 'text': text.strip()})
    styles = pick_styles(rows)
    summary = {}
    for style_key, selected in styles.items():
        pcm = concat_clips(dataset_dir / 'wavs', selected)
        fname = f'axx-morcito{style_key}{suffix}.wav'
        save_wav(out_dir / fname, pcm)
        summary[fname] = {'seconds': round(len(pcm) / RATE, 2), 'sample_texts': [r['text'] for r in selected[:3]]}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-es', required=True, type=Path)
    parser.add_argument('--dataset-en', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    es = build_lang(args.dataset_es, args.out, '')
    en = build_lang(args.dataset_en, args.out, '-en')
    print(json.dumps({'es': es, 'en': en}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
