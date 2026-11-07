import os
import sys
import subprocess
import json
import re
from pathlib import Path
import numpy as np

ROOT = Path(r"C:\Users\luigi\Desktop\axx2")
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from faster_whisper import WhisperModel

out_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx\speech\training\axxmorcito-v2"))
wavs_dir = out_dir / "wavs"
wavs_dir.mkdir(parents=True, exist_ok=True)

files = {
    'es_p1': (r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253170_31c780de.mp4', 'es'),
    'es_p2': (r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253164_782b2b50.mp4', 'es'),
    'en_p1': (r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253175_6d9e211f.mp4', 'en'),
    'en_p2': (r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253168_0902e299.mp4', 'en'),
    'en_p3': (r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586246328_185856b8.mp4', 'en'),
}

whisper = WhisperModel("resources/models/faster-whisper-tiny", device="cpu", compute_type="int8")

metadata_entries = []
count = 0

print("=== SEGMENTING & PREPARING V2 TRAINING DATASET ===")

for prefix, (file_path, lang) in files.items():
    raw_16k = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", file_path, "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True
    ).stdout
    samples_16k = np.frombuffer(raw_16k, dtype=np.int16).astype(np.float32) / 32768.0
    
    segments, _ = whisper.transcribe(samples_16k, language=lang, beam_size=5)
    
    for seg in segments:
        text = seg.text.strip()
        # Filter out empty or too short / noisy segments
        if len(text) < 4 or re.fullmatch(r'^[.,!?¿¡\s]+$', text):
            continue
        
        # Audio length check (0.8s to 12s)
        dur = seg.end - seg.start
        if dur < 0.6 or dur > 14.0:
            continue
        
        count += 1
        wav_name = f"axx_v2_{prefix}_{count:03d}.wav"
        target_wav = wavs_dir / wav_name
        
        # Extract segment with slight padding (0.08s) and audio normalization
        start_t = max(0.0, seg.start - 0.08)
        dur_t = dur + 0.16
        
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start_t:.3f}", "-t", f"{dur_t:.3f}",
            "-i", file_path,
            "-ar", "22050", "-ac", "1",
            "-af", "silenceremove=start_periods=1:start_duration=0.04:start_threshold=-45dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.04:start_threshold=-45dB:detection=peak,areverse,loudnorm=I=-16:TP=-1.5:LRA=11",
            str(target_wav)
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and target_wav.is_file() and target_wav.stat().st_size > 4000:
            metadata_entries.append(f"{wav_name}|{text}")
            print(f"[{count:02d}] {wav_name} ({dur:.2f}s): {text}")

meta_file = out_dir / "metadata.csv"
meta_file.write_text("\n".join(metadata_entries) + "\n", encoding="utf-8")

print(f"\nSuccessfully generated {len(metadata_entries)} segmented utterances in {out_dir}")
