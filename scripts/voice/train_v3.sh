#!/usr/bin/env bash
set -e

WORK="/opt/axx-piper-train/work/axx-morcito-v3"
CKPT="/opt/axx-piper-train/work/axx-morcito-es/lightning_logs/version_0/checkpoints/last.ckpt"
VENV="/opt/axx-piper-train/piper1-gpl/.venv"

mkdir -p "$WORK/cache"
cd /opt/axx-piper-train/piper1-gpl

echo "Starting Piper training for axx-morcito-v3 (84 utterances) on CPU..."
nohup "$VENV/bin/python3" -m piper.train fit \
  --data.voice_name axx-morcito-v3 \
  --data.csv_path "$WORK/metadata.csv" \
  --data.audio_dir "$WORK/wavs" \
  --model.sample_rate 22050 \
  --data.espeak_voice es-419 \
  --data.cache_dir "$WORK/cache" \
  --data.config_path "$WORK/config.json" \
  --data.batch_size 12 \
  --data.num_workers 2 \
  --data.trim_silence false \
  --data.validation_split 0.05 \
  --data.num_test_examples 2 \
  --model.mos_metric none \
  --trainer.accelerator cpu \
  --trainer.max_epochs 1000 \
  --trainer.check_val_every_n_epoch 25 \
  --trainer.default_root_dir "$WORK" \
  --model.warmstart_ckpt "$CKPT" \
  > "$WORK/train.log" 2>&1 &

PID=$!
echo "Training launched in background with PID: $PID"
echo "Log file: $WORK/train.log"
