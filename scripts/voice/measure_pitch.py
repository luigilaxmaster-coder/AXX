import sys
import os
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import numpy as np
import wave
import subprocess

def get_pitch(path):
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
            capture_output=True, check=True
        ).stdout
    except Exception as e:
        return 0.0
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    frame_len = 800  # 50ms at 16kHz
    hop = 320        # 20ms
    pitches = []
    for i in range(0, len(samples) - frame_len, hop):
        frame = samples[i:i+frame_len]
        if np.std(frame) < 300:
            continue
        corr = np.correlate(frame, frame, mode="full")[frame_len-1:]
        # pitch range 80Hz - 450Hz -> lag between 35 and 200 samples
        sub = corr[35:200]
        if len(sub) == 0:
            continue
        lag = 35 + np.argmax(sub)
        pitch = 16000.0 / lag
        if 80 <= pitch <= 450:
            pitches.append(pitch)
    if not pitches:
        return 0.0
    return float(np.median(pitches))

def main():
    print("--- ORIGINAL RECORDINGS (User uploads) ---")
    orig_dir = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\training\axxmorcito-piper\raw")
    if orig_dir.exists():
        for f in sorted(orig_dir.glob("*.m4a")):
            p = get_pitch(f)
            print(f"  {f.name}: {p:.1f} Hz")
            
    print("\n--- AXXMORCITO CANDIDATES (Original WAVs) ---")
    cand_dir = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\voices\axxmorcito-candidates")
    if cand_dir.exists():
        for f in sorted(cand_dir.glob("*.wav")):
            p = get_pitch(f)
            print(f"  {f.name}: {p:.1f} Hz")

    print("\n--- SYNTHESIZED BY PIPER ---")
    pipe_dir = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\piper\models")
    # Let's synthesize sample text with piper:axx-morcito-es and measure pitch
    from backend.speech.piper_tts import PiperSpeechService
    data_dir = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx")
    svc = PiperSpeechService(data_dir=data_dir)
    try:
        res = svc.synthesize({"text": "Hola mi amor, te amo mucho.", "voice": "piper:axx-morcito-es"})
        import base64
        audio_bytes = base64.b64decode(res["audio_base64"])
        temp_wav = pathlib.Path("temp_piper_sample.wav")
        temp_wav.write_bytes(audio_bytes)
        p = get_pitch(temp_wav)
        print(f"  piper:axx-morcito-es current output pitch: {p:.1f} Hz")
        temp_wav.unlink(missing_ok=True)
    except Exception as e:
        print(f"  piper test error: {e}")

if __name__ == "__main__":
    main()
