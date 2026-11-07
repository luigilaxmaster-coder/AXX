import sys
import os
import pathlib
import subprocess
import time
import base64
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from scripts.voice.compare_acoustics import get_acoustic_profile
from backend.speech.piper_tts import PiperSpeechService

def test_styles():
    svc = PiperSpeechService(data_dir=pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx"))
    ref_path = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\voices\axx-morcito.wav")
    ref_prof = get_acoustic_profile(ref_path)
    print("--- REFERENCE (Girlfriend Audio) ---")
    print(f"  Pitch: {ref_prof['pitch_median']:.1f} Hz | Centroid: {ref_prof['centroid_mean']:.1f} Hz")
    
    text = "Hola mi amor, te estaba esperando para contarte lo que pasó hoy. Te quiero muchísimo."
    
    styles = {
        'natural': ('piper:axx-morcito-es', 0.9205, 2.8, -3.2),
        'calma': ('piper:axx-morcito-es@calma', 0.9100, 3.2, -3.5),
        'emocion': ('piper:axx-morcito-es@emocion', 0.9400, 2.0, -2.5),
        'atencion': ('piper:axx-morcito-es@atencion', 0.9350, 2.2, -2.8),
    }

    for name, (uri, ratio, bass, treble) in styles.items():
        t0 = time.time()
        res = svc.synthesize({"text": text, "voice": uri})
        synth_ms = (time.time() - t0) * 1000
        raw_bytes = base64.b64decode(res["audio_base64"])
        
        # Apply DSP filter
        t1 = time.time()
        af = f"rubberband=pitch={ratio:.4f}:formant=preserved,equalizer=f=260:width_type=q:w=1.2:g={bass},equalizer=f=3800:width_type=q:w=1.4:g={treble}"
        proc = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1'],
            input=raw_bytes, capture_output=True, check=True
        )
        tuned_bytes = proc.stdout
        dsp_ms = (time.time() - t1) * 1000
        
        temp_out = pathlib.Path(f"test_{name}.wav")
        temp_out.write_bytes(tuned_bytes)
        prof = get_acoustic_profile(temp_out)
        temp_out.unlink(missing_ok=True)
        
        print(f"\n[{name.upper()}] (synth={synth_ms:.0f}ms, dsp={dsp_ms:.0f}ms):")
        print(f"  Pitch: {prof['pitch_median']:.1f} Hz (target ~ 149Hz)")
        print(f"  Centroid: {prof['centroid_mean']:.1f} Hz (target ~ 1320Hz)")

if __name__ == "__main__":
    test_styles()
