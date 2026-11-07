import time
import os
import io
import wave
import subprocess
from pathlib import Path
from piper import PiperVoice, SynthesisConfig

def main():
    data_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'Axx' / 'speech' / 'piper'
    model_path = data_dir / 'models' / 'axx-morcito-es.onnx'
    voice = PiperVoice.load(str(model_path))
    text = "Hola mi amor, esta es una prueba de síntesis directa para comparar velocidad y fluidez."
    
    # 1. Direct synthesis
    t0 = time.time()
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav_file:
        cfg = SynthesisConfig(noise_scale=0.6, noise_w_scale=0.8, length_scale=1.0)
        voice.synthesize_wav(text, wav_file, syn_config=cfg)
    raw_direct = out.getvalue()
    t1 = time.time()
    print(f"Direct synthesis: {(t1 - t0)*1000:.1f}ms (size: {len(raw_direct)} bytes)")
    
    # 2. With ffmpeg rubberband filter (current DSP filter)
    t2 = time.time()
    af = "rubberband=pitch=1.0250:formant=preserved,treble=g=6.8:f=2800,equalizer=f=1500:width_type=q:w=1.2:g=1.8"
    proc = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-af', af, '-f', 'wav', 'pipe:1'],
        input=raw_direct, capture_output=True, check=True
    )
    dsp_bytes = proc.stdout
    t3 = time.time()
    print(f"FFmpeg rubberband DSP time: {(t3 - t2)*1000:.1f}ms (size: {len(dsp_bytes)} bytes)")
    print(f"Total time with DSP: {(t3 - t0)*1000:.1f}ms")

if __name__ == "__main__":
    main()
