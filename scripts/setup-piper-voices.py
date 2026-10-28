"""Install the two reviewed Spanish Piper voices into private Axx data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv


VOICES = {
    'es_ES-carlfm-x_low': ('es/es_ES/carlfm/x_low', 'd69677323a907cd4963f42b29c20a98b5d6bfa7f3e64df339915e4650c00d125'),
    'es_MX-ald-medium': ('es/es_MX/ald/medium', '019b3803293c93e34a206dd2e53a3889209a514e786fd7144f7b70196c579b63'),
}
BASE = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'


def download(url: str, destination: Path, sha256: str | None = None):
    temporary = destination.with_suffix(destination.suffix + '.part')
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if sha256 and digest.hexdigest() != sha256:
            raise ValueError(f'SHA256 incorrecto: {destination.name}')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('voice', choices=[*VOICES, 'all'])
    args = parser.parse_args()
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Axx/speech/piper'
    python = root / '.venv/Scripts/python.exe'
    if not python.is_file():
        venv.create(root / '.venv', with_pip=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', 'piper-tts==1.4.1'], check=True)
    models = root / 'models'
    models.mkdir(parents=True, exist_ok=True)
    for name in (VOICES if args.voice == 'all' else [args.voice]):
        folder, expected = VOICES[name]
        model = models / (name + '.onnx')
        if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != expected:
            download(BASE + folder + '/' + model.name, model, expected)
        config = models / (model.name + '.json')
        if not config.is_file():
            download(BASE + folder + '/' + config.name, config)
        data = json.loads(config.read_text(encoding='utf-8'))
        if data.get('language', {}).get('code') != name.split('-')[0] or not isinstance(data.get('audio', {}).get('sample_rate'), int):
            raise ValueError(f'Configuración de voz inválida: {name}')
        print(f'{name}: instalado; SHA256 {expected}')


if __name__ == '__main__':
    main()
