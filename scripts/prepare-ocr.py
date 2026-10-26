"""Install verified OCR models in private local data, never in the repository or release."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request


def main():
    manifest = json.loads((Path(__file__).resolve().parents[1]/'resources/ocr-model-manifest.json').read_text())
    root = Path(os.environ['LOCALAPPDATA'])/'Axx/models/ocr'
    root.mkdir(parents=True, exist_ok=True)
    for record in manifest['models'].values():
        target = root/record['file']
        if target.exists():
            content = target.read_bytes()
        else:
            with urllib.request.urlopen(record['url'], timeout=40) as response: content = response.read(32 * 1024 * 1024 + 1)
        if len(content) > 32 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != record['sha256']:
            raise ValueError('Modelo fuera de límites o hash distinto: ' + record['file'])
        if not target.exists():
            with target.open('xb') as output: output.write(content)
        print(json.dumps({'model': record['file'], 'bytes': len(content), 'sha256': record['sha256']}))


if __name__ == '__main__': main()
