import sys
import pathlib
import wave
import subprocess
import json

def get_duration(path):
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, check=True
    ).stdout.decode('utf-8').strip()
    return float(raw)

def main():
    # In es_page1:
    # "vamos a probar mi voz, 1, 2, 3, 9, 10, 15 minutos, 23 de octubre, 125 pesos con 50 centavos"
    # Let's see how long the girlfriend took to say this in media_1793509176525_a5f13662.mp4
    orig = pathlib.Path(r"C:\Users\luigi\AppData\Local\Axx\speech\training\axxmorcito-piper\raw\es_page1.m4a")
    if orig.exists():
        print(f"Girlfriend es_page1 duration: {get_duration(orig):.2f}s")

if __name__ == "__main__":
    main()
