import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.speech.piper_tts import PiperSpeechService

def main():
    data_dir = Path(os.environ.get('LOCALAPPDATA', 'C:\\Users\\luigi\\AppData\\Local')) / 'Axx'
    svc = PiperSpeechService(data_dir=data_dir)
    voices = svc.voices()
    print("Installed Piper voices in Axx:")
    for v in voices:
        print(f"  - {v['name']}: {v['label']} ({v['language']})")
    
    for voice_uri in [
        "piper:axx-morcito-es",
        "piper:axx-morcito-es@calma",
        "piper:axx-morcito-es@emocion",
        "piper:axx-morcito-es@atencion",
        "piper:axx-morcito-en"
    ]:
        try:
            print(f"\n--- Testing {voice_uri} ---")
            text = (
                "Hola mi amor, esta es la voz de axxmorcito funcionando de manera fluida y rapida en Axx."
                if "-es" in voice_uri else
                "Hello darling, this is your custom fast voice running smoothly."
            )
            res = svc.synthesize({'text': text, 'voice': voice_uri})
            print(f"SUCCESS {voice_uri}: duration={res['duration_seconds']}s, bytes={res['evidence']['size']}")
        except Exception as e:
            print(f"FAILED {voice_uri}: {e}")

if __name__ == "__main__":
    main()
