"""Build a private LJSpeech-style Piper dataset from long voice recordings.

Usage:
    python scripts/voice/prepare_piper_dataset.py --out DIR --lang es a.m4a b.m4a ...

Each recording is cleaned with ffmpeg, transcribed with faster-whisper using
word timestamps, then cut into 1.2-11 s utterances at sentence ends or pauses.
Output: DIR/wavs/*.wav (22.05 kHz mono s16), DIR/metadata.csv (id|text) and
DIR/report.json. Recordings and outputs stay wherever DIR points (keep private).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import wave

import numpy as np
from faster_whisper import WhisperModel

RATE = 22050
MIN_S, MAX_S, PAD_S = 1.2, 11.0, 0.12
CLEAN = 'highpass=f=70,lowpass=f=10500,afftdn=nf=-28,loudnorm=I=-20:TP=-2:LRA=11'


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-af', CLEAN, '-ac', '1',
                          '-ar', str(RATE), '-f', 's16le', '-'], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16)


def utterances(words):
    """Group words into utterances; break at sentence punctuation, long pauses or max length."""
    current = []
    for index, word in enumerate(words):
        current.append(word)
        nxt = words[index + 1] if index + 1 < len(words) else None
        span = word.end - current[0].start
        gap = (nxt.start - word.end) if nxt else 9
        ends = word.word.strip()[-1:] in '.?!;'
        if nxt is None or (span >= MIN_S and (ends or gap > 0.45)) or span >= MAX_S - 1.5 or (span >= 4 and word.word.strip()[-1:] == ','):
            yield current
            current = []


def write_wav(path: Path, pcm: np.ndarray):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(RATE)
        out.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--lang', required=True, choices=['es', 'en'])
    parser.add_argument('--model', default='medium')
    parser.add_argument('--prefix', default='axx')
    parser.add_argument('inputs', nargs='+', type=Path)
    args = parser.parse_args()

    wavs = args.out / 'wavs'
    wavs.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(args.model, device='cpu', compute_type='int8')
    rows, details, rejected, total = [], [], [], 0.0
    for file_index, source in enumerate(args.inputs, 1):
        audio = decode(source)
        audio_16k = np.frombuffer(
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-af', CLEAN, '-ac', '1',
                            '-ar', '16000', '-f', 's16le', '-'], check=True, capture_output=True).stdout,
            dtype=np.int16).astype(np.float32) / 32768
        segments, _ = model.transcribe(audio_16k, language=args.lang, beam_size=5,
                                       word_timestamps=True, vad_filter=True, condition_on_previous_text=True)
        words = [w for s in segments for w in (s.words or [])]
        for utt_index, group in enumerate(utterances(words), 1):
            text = ' '.join(''.join(w.word for w in group).split())
            start, end = group[0].start, group[-1].end
            duration = end - start
            prob = float(np.mean([w.probability for w in group]))
            item = {'source': source.name, 'start': round(start, 2), 'end': round(end, 2), 'text': text, 'prob': round(prob, 3)}
            if not MIN_S <= duration <= MAX_S or prob < 0.55 or len(text) < 3:
                rejected.append(item)
                continue
            clip = audio[max(0, int((start - PAD_S) * RATE)):int((end + PAD_S + 0.08) * RATE)]
            if len(clip) < int(0.8 * RATE):
                rejected.append(item)
                continue
            fade = min(len(clip) // 4, int(0.01 * RATE))
            clip = clip.astype(np.float32)
            clip[:fade] *= np.linspace(0, 1, fade); clip[-fade:] *= np.linspace(1, 0, fade)
            uid = f'{args.prefix}_{args.lang}_{file_index:02d}_{utt_index:03d}'
            write_wav(wavs / f'{uid}.wav', clip.astype(np.int16))
            rows.append((uid, text)); total += len(clip) / RATE
            item['id'] = uid
            details.append(item)
    (args.out / 'metadata.csv').write_text(''.join(f'{u}|{t}\n' for u, t in rows), encoding='utf-8')
    report = {'language': args.lang, 'utterances': len(rows), 'seconds': round(total, 1),
              'rejected': rejected, 'rows': details}
    (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('language', 'utterances', 'seconds')} | {'rejected': len(rejected)}))


if __name__ == '__main__':
    main()
