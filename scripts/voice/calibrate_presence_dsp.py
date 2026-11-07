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
from scripts.voice.deep_voice_analysis import analyze_audio_pcm

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

configs = {
    'Real Girlfriend Target': None,
    'Raw Piper (No Filter)': None,
    'Tuned Presence B (pitch 1.022 + clarity)': 'rubberband=pitch=1.022:formant=preserved,equalizer=f=3400:width_type=q:w=0.9:g=4.0,equalizer=f=250:width_type=q:w=1.2:g=-1.0',
    'Tuned Presence C (pitch 1.025 + high-shelf)': 'rubberband=pitch=1.025:formant=preserved,treble=g=4:f=3200,equalizer=f=1800:width_type=q:w=1.0:g=2.0',
    'Tuned Presence D (pitch 1.022 + warmth balance)': 'rubberband=pitch=1.022:formant=preserved,treble=g=3.2:f=3000,equalizer=f=1200:width_type=q:w=1.2:g=1.5'
}

for label, af in configs.items():
    if label == 'Real Girlfriend Target':
        print(f"\n[{label}]:")
        print("  Pitch Median F0: 164.6 Hz")
        print("  Spectral Centroid: 2166.1 Hz")
        print("  Spectral Rolloff: 3690.9 Hz")
        continue
    if af is None:
        tuned = raw
    else:
        cmd = ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1']
        proc = subprocess.run(cmd, input=raw, capture_output=True, check=True)
        tuned = fix_pipe_wav(proc.stdout)
    
    tmp = ROOT / f"test_{label[:6].strip()}.wav"
    tmp.write_bytes(tuned)
    prof = analyze_audio_pcm(str(tmp))
    
    print(f"\n[{label}]:")
    print(f"  Pitch Median F0: {prof['pitch']['median']:.1f} Hz")
    print(f"  Pitch Mean F0: {prof['pitch']['mean']:.1f} Hz")
    print(f"  Spectral Centroid: {prof['timbre']['spectral_centroid_mean']:.1f} Hz")
    print(f"  Spectral Rolloff: {prof['timbre']['spectral_rolloff_85_mean']:.1f} Hz")
