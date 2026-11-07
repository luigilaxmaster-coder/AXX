import base64
import io
import json
import logging
import os
from pathlib import Path
import queue
import re
import struct
import subprocess
import sys
import threading
import time
import uuid
import wave

ROOT = Path(r"C:\Users\luigi\Desktop\axx2")
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

p = ROOT / "backend" / "speech" / "piper_tts.py"
content = p.read_text(encoding="utf-8")

# 1. Add import struct
if "import struct" not in content:
    content = content.replace("import subprocess", "import struct\nimport subprocess")

# 2. Add _fix_pipe_wav and update DSP profiles
old_dsp = """# DSP alignment profiles for axx-morcito: shifts raw Piper synthesis (~175 Hz Paula Lessac base)
# to exact real girlfriend acoustics (149.0 Hz median F0, 1320 Hz spectral centroid).
DSP_TIMBRE_PROFILES = {
    '': (0.9205, 2.8, -3.2),
    'calma': (0.9100, 3.2, -3.5),
    'emocion': (0.9400, 2.0, -2.5),
    'atencion': (0.9350, 2.2, -2.8),
}


def _apply_timbre_dsp(raw_bytes: bytes, style: str) -> bytes:
    ratio, bass, treble = DSP_TIMBRE_PROFILES.get(style, DSP_TIMBRE_PROFILES[''])
    try:
        af = (f"rubberband=pitch={ratio:.4f}:formant=preserved,"
              f"equalizer=f=260:width_type=q:w=1.2:g={bass},"
              f"equalizer=f=3800:width_type=q:w=1.4:g={treble}")
        proc = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1'],
            input=raw_bytes, capture_output=True, check=True, timeout=8
        )
        if len(proc.stdout) > 44:
            return proc.stdout
    except Exception as err:
        LOG.warning('DSP timbre alignment fallback: %s', err)
    return raw_bytes"""

new_dsp = """def _fix_pipe_wav(data: bytes) -> bytes:
    if len(data) < 12 or not data.startswith(b'RIFF') or data[8:12] != b'WAVE':
        return data
    idx = data.find(b'data')
    if idx == -1 or idx + 8 > len(data):
        return data
    b = bytearray(data)
    b[4:8] = struct.pack('<I', len(data) - 8)
    b[idx+4:idx+8] = struct.pack('<I', len(data) - idx - 8)
    return bytes(b)


# DSP alignment profiles for axx-morcito:
# Ground truth from all 5 girlfriend voice recordings (363s): F0 median = 164.6 Hz (mean 179.3 Hz), centroid = 2166 Hz.
# Raw Piper synthesis: F0 median = 160.4 Hz, centroid = 1209 Hz.
# (pitch_ratio, treble_gain_db, treble_freq, mid_gain_db, mid_freq)
DSP_TIMBRE_PROFILES = {
    '': (1.025, 6.8, 2800, 1.8, 1500),         # Natural: Exact F0 164.6 Hz, crisp feminine presence
    'calma': (1.000, 5.0, 2600, 1.2, 1400),    # Tranquila: F0 ~160.5 Hz, soft, intimate
    'emocion': (1.045, 7.8, 3000, 2.2, 1600),   # Emocionada: F0 ~168 Hz, bright, expressive
    'atencion': (1.030, 7.0, 2900, 2.0, 1500),  # Atenta: F0 ~165 Hz, focused, clear
}


def _apply_timbre_dsp(raw_bytes: bytes, style: str) -> bytes:
    ratio, treble_g, treble_f, mid_g, mid_f = DSP_TIMBRE_PROFILES.get(style, DSP_TIMBRE_PROFILES[''])
    try:
        af = (f"rubberband=pitch={ratio:.4f}:formant=preserved,"
              f"treble=g={treble_g:.1f}:f={treble_f},"
              f"equalizer=f={mid_f}:width_type=q:w=1.2:g={mid_g:.1f}")
        proc = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1'],
            input=raw_bytes, capture_output=True, check=True, timeout=8
        )
        if len(proc.stdout) > 44:
            return _fix_pipe_wav(proc.stdout)
    except Exception as err:
        LOG.warning('DSP timbre alignment fallback: %s', err)
    return raw_bytes"""

content = content.replace(old_dsp, new_dsp)
p.write_text(content, encoding="utf-8")
print("Updated piper_tts.py with _fix_pipe_wav and refined presence DSP!")
