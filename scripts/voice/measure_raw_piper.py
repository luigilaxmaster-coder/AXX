import os
import sys
import base64
import wave
from pathlib import Path

# Explicit absolute working directory
ROOT = Path(r"C:\Users\luigi\Desktop\axx2")
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from backend.speech.piper_tts import PiperSpeechService
from scripts.voice.deep_voice_analysis import analyze_audio_pcm

svc = PiperSpeechService(Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx")))
res = svc._request('piper:axx-morcito-es', 'Hola mi amor, te estaba esperando para contarte lo que pasó hoy. Te quiero muchísimo.', 0, 100)
raw = base64.b64decode(res['audio_base64'])

test_wav = ROOT / "test_raw_piper.wav"
test_wav.write_bytes(raw)

prof = analyze_audio_pcm(str(test_wav))
print("=== RAW PIPER MODEL (axx-morcito-es.onnx from Epoch ~220) ===")
print(f"Pitch Median F0: {prof['pitch']['median']:.1f} Hz")
print(f"Pitch Mean F0: {prof['pitch']['mean']:.1f} Hz")
print(f"Pitch Min / Max: {prof['pitch']['min']:.1f} Hz / {prof['pitch']['max']:.1f} Hz")
print(f"Spectral Centroid: {prof['timbre']['spectral_centroid_mean']:.1f} Hz")
print(f"Spectral Rolloff 85%: {prof['timbre']['spectral_rolloff_85_mean']:.1f} Hz")
test_wav.unlink(missing_ok=True)
