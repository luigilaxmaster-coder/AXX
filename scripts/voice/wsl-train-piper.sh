#!/usr/bin/env bash
# Fine-tunes a private Piper voice on CPU inside WSL and exports ONNX.
# Usage: bash wsl-train-piper.sh <voice-name> <dataset-dir> <espeak-voice> <epochs> [batch]
#   e.g. bash wsl-train-piper.sh axx-morcito-es /mnt/c/.../dataset-es es-419 600 8
# The dataset dir needs metadata.csv (id|text) and wavs/. Outputs go to
# <dataset-dir>/../<voice-name>/ (checkpoints, logs, <voice>.onnx + .onnx.json).
set -euo pipefail

NAME="$1"; DATA="$2"; ESPEAK="$3"; EPOCHS="$4"; BATCH="${5:-8}"
ROOT="${AXX_PIPER_TRAIN_ROOT:-/opt/axx-piper-train}"
OUT="$(dirname "$DATA")/$NAME"
WORK="$ROOT/work/$NAME"   # Linux filesystem: much faster than /mnt/c for training I/O
mkdir -p "$OUT" "$WORK/wavs"

source "$ROOT/piper1-gpl/.venv/bin/activate"
cd "$ROOT/piper1-gpl"
python - <<'PY'
from pathlib import Path
p = Path("src/piper/train/__main__.py")
s = p.read_text()
start = s.find('ModelCheckpoint(\n            monitor="val_mos"')
if start != -1:
    end = s.find('),', start) + 2
    p.write_text(s[:start] + s[end:])
ep = Path("src/piper/train/export_onnx.py")
es = ep.read_text()
if "dynamo=" not in es:
    ep.write_text(es.replace("torch.onnx.export(", "torch.onnx.export(dynamo=False, "))
PY
rm -rf "$WORK/cache"
cp -u "$DATA"/wavs/*.wav "$WORK/wavs/"
sed 's/^\([^|]*\)|/\1.wav|/' "$DATA/metadata.csv" > "$WORK/metadata.csv"
export OMP_NUM_THREADS="$(nproc)"

RESUME=()
LAST="$(ls -t "$WORK"/lightning_logs/*/checkpoints/*.ckpt 2>/dev/null | head -1 || true)"
if [ -n "$LAST" ]; then RESUME=(--ckpt_path "$LAST"); else RESUME=(--model.warmstart_ckpt "$ROOT/checkpoints/lessac-medium.ckpt"); fi

python -m piper.train fit \
  --data.voice_name "$NAME" \
  --data.csv_path "$WORK/metadata.csv" \
  --data.audio_dir "$WORK/wavs" \
  --model.sample_rate 22050 \
  --data.espeak_voice "$ESPEAK" \
  --data.cache_dir "$WORK/cache" \
  --data.config_path "$WORK/config.json" \
  --data.batch_size "$BATCH" \
  --data.num_workers 2 \
  --data.trim_silence false \
  --data.validation_split 0.05 \
  --data.num_test_examples 2 \
  --model.mos_metric none \
  --trainer.accelerator cpu \
  --trainer.max_epochs "$EPOCHS" \
  --trainer.check_val_every_n_epoch 1 \
  --trainer.default_root_dir "$WORK" \
  "${RESUME[@]}"

CKPT="$(ls -t "$WORK"/lightning_logs/*/checkpoints/*.ckpt | head -1)"
python -m piper.train.export_onnx --checkpoint "$CKPT" --output-file "$OUT/$NAME.onnx"
cp "$WORK/config.json" "$OUT/$NAME.onnx.json"
python - "$OUT/$NAME.onnx.json" "$NAME" "$ESPEAK" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
name, espeak = sys.argv[2], sys.argv[3]
cfg = json.loads(p.read_text(encoding='utf-8'))
lang = 'es-MX' if espeak.startswith('es') else 'en-US'
tag = 'ES' if espeak.startswith('es') else 'EN'
cfg['axx'] = {'label': f'Axxmorcito \u00b7 Piper ({tag})', 'language': lang}
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
PY
MODELS_DIR="$(dirname "$(dirname "$OUT")")/piper/models"
if [ "$EPOCHS" -ge 50 ]; then
  mkdir -p "$MODELS_DIR"
  cp "$OUT/$NAME.onnx" "$MODELS_DIR/$NAME.onnx"
  cp "$OUT/$NAME.onnx.json" "$MODELS_DIR/$NAME.onnx.json"
  echo "AXX_PIPER_EXPORTED $MODELS_DIR/$NAME.onnx"
else
  echo "AXX_PIPER_SMOKE_EXPORTED $OUT/$NAME.onnx (train >=50 epochs to install into $MODELS_DIR)"
fi
