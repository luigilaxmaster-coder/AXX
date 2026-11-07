#!/usr/bin/env bash
set -e

SRC1="/opt/axx-piper-train/work/axx-morcito-es"
SRC2="/opt/axx-piper-train/work/axx-morcito-v2"
DEST="/opt/axx-piper-train/work/axx-morcito-v3"

mkdir -p "$DEST/wavs"

# Copy wavs from both datasets
cp -f "$SRC1"/wavs/*.wav "$DEST/wavs/"
cp -f "$SRC2"/wavs/*.wav "$DEST/wavs/"

# Merge metadata.csv with pipes (audio_id|text)
cat "$SRC1/metadata.csv" > "$DEST/metadata.csv"
echo "" >> "$DEST/metadata.csv"
cat "$SRC2/metadata.csv" >> "$DEST/metadata.csv"

# Remove empty lines
sed -i '/^[[:space:]]*$/d' "$DEST/metadata.csv"

TOTAL=$(wc -l < "$DEST/metadata.csv")
WAVS=$(ls -1 "$DEST/wavs"/*.wav | wc -l)
echo "Merged dataset created at $DEST: $TOTAL lines in metadata.csv, $WAVS wav files."
