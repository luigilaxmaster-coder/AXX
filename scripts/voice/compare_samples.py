import os
import io
import wave
from pathlib import Path
from piper import PiperVoice, SynthesisConfig

def generate():
    data_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'Axx' / 'speech' / 'piper'
    model_es = data_dir / 'models' / 'axx-morcito-es.onnx'
    out_dir = Path('C:/Users/luigi/Desktop/axx2/scripts/voice/samples')
    out_dir.mkdir(parents=True, exist_ok=True)
    
    voice = PiperVoice.load(str(model_es))
    phrases = [
        ("es_natural", "Hola amor, ¿cómo estás? Ya casi terminamos de ajustar todo para que la voz funcione súper bien.", 0.60, 0.80, 0.98),
        ("es_calma", "Todo está tranquilo mi vida, respira y descansa que yo me encargo de todo.", 0.58, 0.75, 1.08),
        ("es_emocion", "¡Mi amor, no te imaginas lo bien que está quedando todo, qué felicidad!", 0.65, 0.85, 0.90),
    ]
    
    for name, text, ns, nw, ls in phrases:
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav_file:
            cfg = SynthesisConfig(noise_scale=ns, noise_w_scale=nw, length_scale=ls)
            voice.synthesize_wav(text, wav_file, syn_config=cfg)
        path = out_dir / f"{name}.wav"
        path.write_bytes(out.getvalue())
        print(f"Generated {path.name}: {len(out.getvalue())} bytes")

if __name__ == '__main__':
    generate()
