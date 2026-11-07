import sys
import pathlib
import time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from backend.speech.piper_tts import PiperSpeechService

def main():
    svc = PiperSpeechService(data_dir=pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx"))
    p = "Hoy fue un día bastante largo y con mucho movimiento, pero al final todo salió bien. Mañana temprano tenemos que salir a hacer unas compras."
    t0 = time.time()
    res = svc.synthesize({"text": p, "voice": "piper:axx-morcito-es"})
    dt = time.time() - t0
    print(f"Piper took: {dt:.3f}s for {len(p)} chars! Duration of audio: {res['duration_seconds']}s")

if __name__ == "__main__":
    main()
