"""Private, long-lived ONNX worker for the optional local Axx voices.

Protocol: one JSON request and one JSON result per line on private stdio.
The desktop backend validates requests; this worker also restricts voice and output paths.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


PERSONAL_VOICES = ('axx-alba', 'axx-nova', 'axx-aura', 'axx-titan')
FALLBACK_VOICES = ('voz_referencia', 'voz_referencia_completo')


def main() -> None:
    model_root = Path(sys.argv[1]).resolve()
    personal_samples = Path(sys.argv[2]).resolve()
    output_root = Path(sys.argv[3]).resolve()
    project_root = model_root.parent
    sys.path.insert(0, str(project_root))
    from onnx_tts_runtime import OnnxTtsRuntime

    class CachedRuntime(OnnxTtsRuntime):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.reference_codes = {}

        def encode_reference_audio(self, reference_audio_path):
            path = str(Path(reference_audio_path).resolve())
            if path not in self.reference_codes:
                self.reference_codes[path] = super().encode_reference_audio(path)
            return self.reference_codes[path]

    runtime = CachedRuntime(model_dir=model_root, thread_count=4, execution_provider='cpu')
    voices = {f'moss:{name}': personal_samples / f'{name}.wav' for name in PERSONAL_VOICES}
    voices.update({f'moss:{name}': project_root / 'samples' / f'{name}.wav' for name in FALLBACK_VOICES})
    output_root.mkdir(parents=True, exist_ok=True)
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            request_id = request['id']
            if not isinstance(request_id, str) or not request_id.isascii() or not request_id.isalnum() or len(request_id) > 32:
                raise ValueError('Invalid request id')
            voice = voices[request['voice']]
            if not voice.is_file():
                raise ValueError('Voice unavailable')
            text = request['text']
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 220 or '\x00' in text:
                raise ValueError('Invalid text')
            output = output_root / f'{request_id}.wav'
            runtime.synthesize(text=text, prompt_audio_path=voice, output_audio_path=output,
                               streaming=False, enable_wetext=False)
            print(json.dumps({'id': request_id, 'ok': True}), flush=True)
        except Exception:
            # Keep request text and local paths out of stdout and logs.
            print(json.dumps({'id': request.get('id') if isinstance(request, dict) else None,
                              'ok': False}), flush=True)


if __name__ == '__main__':
    main()
