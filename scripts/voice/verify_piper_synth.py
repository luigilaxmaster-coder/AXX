import os
import sys
import base64
from pathlib import Path

ROOT = Path(r"C:\Users\luigi\Desktop\axx2")
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from backend.speech.piper_tts import PiperSpeechService
from scripts.voice.deep_voice_analysis import analyze_audio_pcm

svc = PiperSpeechService(Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx")))
res = svc.synthesize({'text': 'Hola mi amor, te estaba esperando para contarte lo que pasó hoy.', 'voice': 'piper:axx-morcito-es'})
print('SUCCESS! Engine:', res['engine'], 'Duration:', res['duration_seconds'], 'Size:', len(res['audio_base64']))

raw = base64.b64decode(res['audio_base64'])
tmp = ROOT / "test_synth_out.wav"
tmp.write_bytes(raw)
prof = analyze_audio_pcm(str(tmp))
tmp.unlink(missing_ok=True)

print("Acoustics of calibrated Piper voice:")
print(f"  Pitch Median F0: {prof['pitch']['median']:.1f} Hz (Target: 164.6 Hz)")
print(f"  Pitch Mean F0: {prof['pitch']['mean']:.1f} Hz (Target: 179.3 Hz)")
print(f"  Spectral Centroid: {prof['timbre']['spectral_centroid_mean']:.1f} Hz")
print(f"  Spectral Rolloff: {prof['timbre']['spectral_rolloff_85_mean']:.1f} Hz")
