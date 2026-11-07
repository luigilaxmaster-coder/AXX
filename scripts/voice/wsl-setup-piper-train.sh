#!/usr/bin/env bash
# Prepares a CPU-only Piper training environment inside WSL Ubuntu.
# Usage (from Windows): wsl -d Ubuntu-24.04 -u root -- bash scripts/voice/wsl-setup-piper-train.sh
set -euo pipefail

ROOT="${AXX_PIPER_TRAIN_ROOT:-/opt/axx-piper-train}"
CKPT_URL="https://huggingface.co/datasets/rhasspy/piper-checkpoints/resolve/main/en/en_US/lessac/medium/epoch%3D2164-step%3D1355540.ckpt"

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git build-essential cmake ninja-build python3-venv python3-dev espeak-ng ffmpeg

mkdir -p "$ROOT"
cd "$ROOT"
[ -d piper1-gpl ] || git clone --depth 1 https://github.com/OHF-Voice/piper1-gpl.git
cd piper1-gpl
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -q --upgrade pip wheel setuptools scikit-build cython
python -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -q onnx onnxscript -e '.[train]'
./build_monotonic_align.sh
python setup.py build_ext --inplace
python - <<'PY'
from pathlib import Path
p = Path("src/piper/train/__main__.py")
s = p.read_text()
if 'monitor="val_mos"' in s:
    lines = [line for line in s.splitlines() if 'val_mos' not in line]
    # Replace the second ModelCheckpoint block cleanly
    s = p.read_text()
    start = s.find('ModelCheckpoint(\n            monitor="val_mos"')
    if start != -1:
        end = s.find('),', start) + 2
        s = s[:start] + s[end:]
        p.write_text(s)
PY

mkdir -p "$ROOT/checkpoints"
CKPT="$ROOT/checkpoints/lessac-medium.ckpt"
[ -s "$CKPT" ] || curl -L --fail --retry 3 -o "$CKPT" "$CKPT_URL"
python -c "import piper.train, torch; print('ok torch', torch.__version__)"
echo "AXX_PIPER_TRAIN_READY $ROOT"
