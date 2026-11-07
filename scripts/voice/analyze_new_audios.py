import os
import sys
import subprocess
import json
import base64
import tempfile
from pathlib import Path
import numpy as np

sys.path.insert(0, r"C:\Users\luigi\Desktop\axx2")
from backend.speech.offline_asr import OfflineTranscriptionService
from scripts.voice.compare_acoustics import get_acoustic_profile

files = {
    'Page3': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586246328_185856b8.mp4',
    'Page_1_Spanish': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253170_31c780de.mp4',
    'Page_1_English': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253175_6d9e211f.mp4',
    'Page_2_Spanish': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253164_782b2b50.mp4',
    'Page_2_English': r'C:\Users\luigi\.gemini\antigravity\brain\49e4d794-e15c-403e-bc2b-2725483070ae\.user_uploaded\media_1793586253168_0902e299.mp4',
}

asr = OfflineTranscriptionService(Path(r"C:\Users\luigi\Desktop\axx2"))

print("================ ACOUSTIC & TRANSCRIPTION ANALYSIS ================")
results = {}

for name, path in files.items():
    # Convert to 22050Hz wav for acoustics
    tmp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp_wav.close()
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', path, '-ar', '22050', '-ac', '1', tmp_wav.name], check=True)
    
    prof = get_acoustic_profile(Path(tmp_wav.name))
    
    # Transcribe with ASR (chunks <= 30s or full)
    # Convert to 16kHz mono WAV for ASR
    tmp_16k = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp_16k.close()
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', path, '-ar', '16000', '-ac', '1', tmp_16k.name], check=True)
    
    wav_bytes = Path(tmp_16k.name).read_bytes()
    b64_audio = base64.b64encode(wav_bytes).decode('ascii')
    try:
        trans = asr.transcribe({'audio_base64': b64_audio, 'mime': 'audio/wav'})
    except Exception as err:
        trans = {'error': str(err)}
    
    results[name] = {
        'acoustics': prof,
        'transcription': trans
    }
    
    print(f"\n--- {name} ---")
    print(f"  Duration: {prof['duration_sec']:.2f}s")
    print(f"  Pitch Median (F0): {prof['pitch_median']:.1f} Hz | Mean: {prof['pitch_mean']:.1f} Hz | Min: {prof['pitch_min']:.1f} Hz | Max: {prof['pitch_max']:.1f} Hz")
    print(f"  Spectral Centroid: {prof['centroid_mean']:.1f} Hz")
    print(f"  ASR Result: {trans.get('text', trans.get('error', ''))}")
    
    os.unlink(tmp_wav.name)
    os.unlink(tmp_16k.name)

# Compare with reference axx-morcito.wav
ref_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\Axx\speech\voices\axx-morcito.wav"))
if ref_path.is_file():
    ref_prof = get_acoustic_profile(ref_path)
    print("\n--- EXISTING REFERENCE (axx-morcito.wav in MOSS) ---")
    print(f"  Duration: {ref_prof['duration_sec']:.2f}s")
    print(f"  Pitch Median (F0): {ref_prof['pitch_median']:.1f} Hz | Mean: {ref_prof['pitch_mean']:.1f} Hz")
    print(f"  Spectral Centroid: {ref_prof['centroid_mean']:.1f} Hz")

Path("acoustic_analysis_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
print("\nSaved detailed results to acoustic_analysis_results.json")
