"""Package the prepared ES/EN datasets for Google Colab or install returned Piper ONNX models.

Usage:
    # 1. Create the dataset zip to upload to Colab:
    python scripts/voice/colab_piper_bundle.py pack

    # 2. Install the trained zip downloaded from Colab (or local ONNX directory):
    python scripts/voice/colab_piper_bundle.py install path/to/axxmorcito-piper-models.zip
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import zipfile


DEFAULT_LABELS = {
    'axx-morcito-es': ('Axxmorcito Rápida (ES)', 'es-MX'),
    'axx-morcito-en': ('Axxmorcito Fast (EN)', 'en-US'),
}


def speech_root() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'Axx' / 'speech'


def pack_bundle(out_zip: Path) -> dict:
    train_root = speech_root() / 'training' / 'axxmorcito-piper'
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for lang in ('es', 'en'):
            ds = train_root / f'dataset-{lang}'
            for file in ds.rglob('*'):
                if file.is_file():
                    zf.write(file, file.relative_to(train_root).as_posix())
                    count += 1
        nb = Path(__file__).with_name('train_axxmorcito_colab.ipynb')
        if nb.is_file():
            zf.write(nb, nb.name)
    return {'bundle': str(out_zip), 'files': count, 'size_bytes': out_zip.stat().st_size}


def ensure_axx_metadata(json_path: Path, stem: str):
    cfg = json.loads(json_path.read_text(encoding='utf-8'))
    label, language = DEFAULT_LABELS.get(stem, (stem, 'es-MX'))
    cfg.setdefault('axx', {'label': label, 'language': language})
    json_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def install_models(source: Path) -> dict:
    models_dir = speech_root() / 'piper' / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    if source.is_dir():
        for onnx in source.glob('axx-*.onnx'):
            cfg = onnx.with_suffix('.onnx.json')
            if cfg.is_file():
                shutil.copy2(onnx, models_dir / onnx.name)
                shutil.copy2(cfg, models_dir / cfg.name)
                ensure_axx_metadata(models_dir / cfg.name, onnx.stem)
                installed.append(onnx.stem)
    else:
        with zipfile.ZipFile(source) as zf:
            for member in zf.namelist():
                name = Path(member).name
                if name.startswith('axx-') and (name.endswith('.onnx') or name.endswith('.onnx.json')):
                    target = models_dir / name
                    target.write_bytes(zf.read(member))
                    if name.endswith('.onnx.json'):
                        stem = name[:-len('.onnx.json')]
                        ensure_axx_metadata(target, stem)
                        installed.append(stem)
    return {'models_dir': str(models_dir), 'installed': sorted(set(installed))}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    p_pack = sub.add_parser('pack')
    p_pack.add_argument('--out', type=Path,
                        default=speech_root() / 'training' / 'axxmorcito-piper' / 'axxmorcito-colab-bundle.zip')
    p_inst = sub.add_parser('install')
    p_inst.add_argument('source', type=Path)
    args = parser.parse_args()
    res = pack_bundle(args.out) if args.cmd == 'pack' else install_models(args.source)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
