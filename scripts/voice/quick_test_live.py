import time, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.speech.piper_tts import PiperSpeechService

def main():
    data_dir = Path(os.environ.get('LOCALAPPDATA', '')) / 'Axx'
    svc = PiperSpeechService(data_dir=data_dir)

    phrases = [
        ('piper:axx-morcito-es', 'Hola mi amor, ¿cómo estás? Ya no me escucho robótica ni me trabo entre oraciones.'),
        ('piper:axx-morcito-es', 'Hello darling! Now when you speak English, I automatically respond with fluent English pronunciation.'),
        ('piper:axx-morcito-es@calma', 'Respira profundo mi cielo, todo va a salir perfecto y me siento muy relajada.'),
        ('piper:axx-morcito-es@emocion', '¡Amor, mira qué bien se escucha ahora! ¡Súper rápida, fluida y con toda la energía!')
    ]

    for voice, text in phrases:
        t0 = time.time()
        res = svc.synthesize({'text': text, 'voice': voice})
        dt = time.time() - t0
        print(f"[{voice}] (lang={res['language']}) -> synth in {dt:.2f}s | audio_len: {res['duration_seconds']}s | bytes: {res['evidence']['size']}")

if __name__ == '__main__':
    main()
