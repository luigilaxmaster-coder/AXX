import sys
import os
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import numpy as np
import subprocess
import json

def get_acoustic_profile(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ar", "22050", "-ac", "1", "-f", "s16le", "-"],
        capture_output=True, check=True
    ).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    # FFT spectral centroid
    fft_size = 1024
    hop = 512
    centroids = []
    freqs = np.fft.rfftfreq(fft_size, 1.0 / 22050)
    for i in range(0, len(samples) - fft_size, hop):
        frame = samples[i:i+fft_size]
        if np.std(frame) < 200: continue
        mag = np.abs(np.fft.rfft(frame * np.hanning(fft_size)))
        if np.sum(mag) > 0:
            c = np.sum(freqs * mag) / np.sum(mag)
            centroids.append(c)
            
    # Pitch
    frame_len = 800
    hop_p = 320
    pitches = []
    for i in range(0, len(samples) - frame_len, hop_p):
        frame = samples[i:i+frame_len]
        if np.std(frame) < 300: continue
        corr = np.correlate(frame, frame, mode="full")[frame_len-1:]
        sub = corr[35:220]
        if len(sub) == 0: continue
        lag = 35 + np.argmax(sub)
        p = 22050.0 / lag
        if 80 <= p <= 450: pitches.append(p)

    return {
        "pitch_median": float(np.median(pitches)) if pitches else 0,
        "pitch_std": float(np.std(pitches)) if pitches else 0,
        "pitch_min": float(np.min(pitches)) if pitches else 0,
        "pitch_max": float(np.max(pitches)) if pitches else 0,
        "centroid_mean": float(np.mean(centroids)) if centroids else 0
    }

def main():
    ref_path = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\voices\axx-morcito.wav")
    print("Reference Clip (Girlfriend):", get_acoustic_profile(ref_path))

    from backend.speech.piper_tts import PiperSpeechService
    svc = PiperSpeechService(data_dir=pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx"))
    res = svc.synthesize({"text": "Hola mi amor, ¿cómo estás hoy? Te quiero mucho.", "voice": "piper:axx-morcito-es"})
    
    import base64
    temp_pipe = pathlib.Path("temp_piper_out.wav")
    temp_pipe.write_bytes(base64.b64decode(res["audio_base64"]))
    print("Piper Synthetic Output:", get_acoustic_profile(temp_pipe))
    temp_pipe.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
