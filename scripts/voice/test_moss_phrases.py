import sys
import os
import pathlib
import time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from backend.speech.moss_tts import MossSpeechService

def main():
    data_dir = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx")
    svc = MossSpeechService(data_dir=data_dir)
    print("MOSS Available:", svc.available)
    
    test_phrases = [
        "Hola amor.",
        "¿Cómo te fue hoy?",
        "Cuesta 120 pesos y son 3 cajas.",
        "Te estaba esperando para contarte lo que pasó hoy.",
        "Hoy fue un día bastante largo y con mucho movimiento, pero al final todo salió bien. Mañana temprano tenemos que salir a hacer unas compras.",
        "¡Hola! ¿Estás ahí? Sí, claro... espera un segundo.",
        "Por supuesto, aquí tienes el resultado que me pediste para el proyecto de hoy."
    ]

    for p in test_phrases:
        t0 = time.time()
        print(f"\n[TESTING] '{p}' (len={len(p)} chars, {len(p.split())} words)", flush=True)
        try:
            res = svc.synthesize({"text": p, "voice": "moss:axx-morcito"})
            dt = time.time() - t0
            print(f" -> SUCCESS in {dt:.2f}s | dur={res.get('duration_seconds')}s | cache_hit={res.get('cache_hit')}", flush=True)
        except Exception as e:
            dt = time.time() - t0
            print(f" -> FAILED in {dt:.2f}s | ERROR: {e}", flush=True)

if __name__ == "__main__":
    main()
