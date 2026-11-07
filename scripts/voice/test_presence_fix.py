import os
import sys
import base64
import wave
import subprocess
import struct
from pathlib import Path

ROOT = Path(r"C:\Users\luigi\Desktop\axx2")
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from backend.speech.piper_tts import PiperSpeechService

svc = PiperSpeechService(Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx")))
res = svc._request('piper:axx-morcito-es', 'Hola mi amor, te estaba esperando para contarte lo que pasó hoy. Te quiero muchísimo.', 0, 100)
raw = base64.b64decode(res['audio_base64'])

def fix_pipe_wav(data: bytes) -> bytes:
    if len(data) < 12 or not data.startswith(b'RIFF') or data[8:12] != b'WAVE':
        return data
    idx = data.find(b'data')
    if idx == -1 or idx + 8 > len(data):
        return data
    b = bytearray(data)
    b[4:8] = struct.pack('<I', len(data) - 8)
    b[idx+4:idx+8] = struct.pack('<I', len(data) - idx - 8)
    return bytes(b)

from scripts.voice.deep_voice_analysis import analyze_audio_pcm

test_filters = {
    'Real Girlfriend Target': None,
    'Presence + Clarity (pitch 1.025 + air + body)': (
        'rubberband=pitch=1.025:formant=preserved,'
        'treble=g=3.8:f=3200,'
        'equalizer=f=1400:width_type=q:w=1.2:g=1.8'
    ),
    'Presence Bright (pitch 1.025 + high shelf)': (
        'rubberband=pitch=1.025:formant=preserved,'
        'treble=g=4.5:f=2800'
    ),
}

for label, af in test_filters.items():
    if af is None:
        print(f"\n[{label}]:")
        print("  Pitch Median F0: 164.6 Hz (Mean: 179.3 Hz)")
        print("  Spectral Centroid: 2166.1 Hz")
        print("  Spectral Rolloff: 3690.9 Hz")
        continue
    cmd = ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1']
    proc = subprocess.run(cmd, input=raw, capture_output=True, check=True)
    tuned = fix_pipe_wav(proc.stdout)
    
    tmp = ROOT / "test_tuned.wav"
    tmp.write_bytes(tuned)
    prof = analyze_audio_pcm(str(tmp))
    tmp.unlink(missing_ok=True)
    
    print(f"\n[{label}]:")
    print(f"  Pitch Median F0: {prof['pitch']['median']:.1f} Hz")
    print(f"  Pitch Mean F0: {prof['pitch']['mean']:.1f} Hz")
    print(f"  Spectral Centroid: {prof['timbre']['spectral_centroid_mean']:.1f} Hz")
    print(f"  Spectral Rolloff: {prof['timbre']['spectral_rolloff_85_mean']:.1f} Hz")
