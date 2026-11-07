#!/usr/bin/env bash
# train_piper_v4.sh - Fine-tune Piper axx-morcito-v4-es with balanced phonetics
set -euo pipefail

ROOT="/opt/axx-piper-train"
NAME="axx-morcito-v4-es"
SRC_DATA="/mnt/c/Users/luigi/AppData/Local/Axx/speech/training/axxmorcito-master-es"
MODELS_DIR="/mnt/c/Users/luigi/AppData/Local/Axx/speech/piper/models"
WORK="$ROOT/work/$NAME"
WARMSTART="$ROOT/work/axx-morcito-es/lightning_logs/version_0/checkpoints/epoch=170-val_mel=0.3501.ckpt"

mkdir -p "$WORK/wavs" "$WORK/cache"
echo "=== Step 1: Copying 89 balanced master WAVs to Linux ext4 ==="
cp -u "$SRC_DATA"/wavs/*.wav "$WORK/wavs/"
sed 's/^\([^|]*\)|/\1.wav|/' "$SRC_DATA/metadata.csv" > "$WORK/metadata.csv"
cp "/opt/axx-piper-train/work/axx-morcito-es/config.json" "$WORK/config.json"

source "$ROOT/piper1-gpl/.venv/bin/activate"
cd "$ROOT/piper1-gpl"

echo "=== Step 2: Running Piper Training (30 epochs on CPU with warmstart) ==="
python -m piper.train fit \
  --data.voice_name "$NAME" \
  --data.csv_path "$WORK/metadata.csv" \
  --data.audio_dir "$WORK/wavs" \
  --model.sample_rate 22050 \
  --data.espeak_voice es-419 \
  --data.cache_dir "$WORK/cache" \
  --data.config_path "$WORK/config.json" \
  --data.batch_size 8 \
  --data.num_workers 2 \
  --data.trim_silence false \
  --data.validation_split 0.05 \
  --data.num_test_examples 2 \
  --model.mos_metric none \
  --trainer.accelerator cpu \
  --trainer.max_epochs 30 \
  --trainer.check_val_every_n_epoch 2 \
  --trainer.default_root_dir "$WORK" \
  --model.warmstart_ckpt "$WARMSTART"

echo "=== Step 3: Exporting Best ONNX Model ==="
BEST_CKPT="$(ls -t "$WORK"/lightning_logs/*/checkpoints/*.ckpt | head -1)"
echo "Using checkpoint: $BEST_CKPT"

python -m piper.train.export_onnx --checkpoint "$BEST_CKPT" --output-file "$WORK/axx-morcito-es.onnx"
cp "$WORK/config.json" "$WORK/axx-morcito-es.onnx.json"

python - "$WORK/axx-morcito-es.onnx.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
cfg = json.loads(p.read_text(encoding='utf-8'))
cfg['axx'] = {'label': 'Axxmorcito · Piper (ES)', 'language': 'es-MX', 'version': 'v4-phonetic-master'}
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
PY

echo "=== Step 4: Installing to AppData Piper Models ==="
if [ -f "$MODELS_DIR/axx-morcito-es.onnx" ]; then
  cp "$MODELS_DIR/axx-morcito-es.onnx" "$MODELS_DIR/axx-morcito-es.v3.bak.onnx"
  cp "$MODELS_DIR/axx-morcito-es.onnx.json" "$MODELS_DIR/axx-morcito-es.v3.bak.onnx.json"
fi

cp "$WORK/axx-morcito-es.onnx" "$MODELS_DIR/axx-morcito-es.onnx"
cp "$WORK/axx-morcito-es.onnx.json" "$MODELS_DIR/axx-morcito-es.onnx.json"

echo "=== DONE: Piper axx-morcito-es v4 successfully trained and installed ==="
