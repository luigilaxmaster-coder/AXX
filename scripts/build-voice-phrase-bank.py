"""Render the shipped phrase catalog into Axx's private MOSS audio bank."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speech.moss_tts import MossSpeechService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=270)
    args = parser.parse_args()
    if not 1 <= args.limit <= 270:
        parser.error('--limit must be between 1 and 270')
    catalog_path = ROOT / '1.AXX' / 'scripts' / 'voice-phrases.js'
    result = subprocess.run(['node', '-e', 'process.stdout.write(JSON.stringify(require(process.argv[1])))',
                             str(catalog_path)], check=True, capture_output=True, text=True, encoding='utf-8')
    phrases = json.loads(result.stdout)
    if len(phrases) != 270 or len({item['text'] for item in phrases}) != 270:
        raise ValueError('Expected 270 distinct catalog phrases')
    data_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Axx'
    service = MossSpeechService(data_dir)
    if not service.available or 'moss:axx-morcito' not in service._voice_paths():
        raise RuntimeError('Axxmorcito and its MOSS ONNX engine must be installed locally')
    bank = service.data_dir / 'phrase-bank'
    bank.mkdir(parents=True, exist_ok=True)
    completed = skipped = 0
    started = time.monotonic()
    try:
        for item in phrases[:args.limit]:
            request = {'voice': 'moss:axx-morcito', 'text': item['text'], 'language': item['language']}
            path = service._phrase_bank_path(request, service._cache_path(request))
            if path is None:
                raise RuntimeError('Could not identify the phrase cache path')
            if service._read_cache(path):
                skipped += 1
                continue
            audio = service.synthesize(request)
            raw = base64.b64decode(audio['audio_base64'], validate=True)
            temporary = bank / (uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(raw)
                if service._read_cache(temporary) is None:
                    raise RuntimeError('MOSS produced an invalid WAV for ' + item['id'])
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            completed += 1
            print(f'{completed + skipped}/{args.limit} {item["id"]} {audio["duration_seconds"]}s', flush=True)
    finally:
        service.close()
    print(json.dumps({'requested': args.limit, 'generated': completed, 'reused': skipped,
                      'elapsed_seconds': round(time.monotonic() - started, 1),
                      'bank_files': sum(1 for _ in bank.glob('*.wav'))}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
