import urllib.request
import json

def main():
    url = 'https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json'
    try:
        req = urllib.request.urlopen(url, timeout=10)
        data = json.loads(req.read().decode('utf-8'))
        for k, v in data.items():
            if k.startswith('es_'):
                print(f"{k}: quality={v.get('quality')} speakers={len(v.get('speaker_id_map', {}))}")
    except Exception as e:
        print("Error fetching:", e)

if __name__ == "__main__":
    main()
