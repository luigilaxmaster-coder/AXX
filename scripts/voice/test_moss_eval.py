import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.speech.moss_tts import MossSpeechService

def main():
    data_dir = Path(os.environ.get('LOCALAPPDATA', 'C:\\Users\\luigi\\AppData\\Local')) / 'Axx'
    moss = MossSpeechService(data_dir=data_dir)
    print("MOSS Available:", moss.available)
    print("MOSS Voices count:", len(moss.voices()))
    
    test_phrase = "Hola, ¿en qué te puedo ayudar hoy?"
    print(f"\n--- Testing MOSS synthesis on cached phrase: '{test_phrase}' ---")
    res = moss.synthesize({'text': test_phrase, 'voice': 'moss:axx-morcito'})
    print(f"MOSS Result: engine={res.get('engine')}, duration={res.get('duration_seconds')}s, cache_hit={res.get('cache_hit')}")

if __name__ == "__main__":
    main()
