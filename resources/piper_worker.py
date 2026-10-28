"""Resident Piper process. All model paths are selected by the parent service."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import sys
import wave

from piper import PiperVoice, SynthesisConfig


MODELS = {'es_ES-carlfm-x_low', 'es_MX-ald-medium'}


def main():
    directory = Path(sys.argv[1])
    loaded = {}
    print('{"ready":true}', flush=True)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            name = request['voice']
            if name not in MODELS:
                raise ValueError('Unsupported Piper voice')
            if name not in loaded:
                loaded[name] = PiperVoice.load(str(directory / (name + '.onnx')))
            if request.get('prepare'):
                result = {'ok': True}
            else:
                output = io.BytesIO()
                with wave.open(output, 'wb') as audio:
                    config = SynthesisConfig(length_scale=1 / (1 + request['rate'] * .1),
                                             volume=request['volume'] / 100)
                    loaded[name].synthesize_wav(request['text'], audio, syn_config=config)
                result = {'audio_base64': base64.b64encode(output.getvalue()).decode('ascii')}
        except Exception:
            result = {'error': 'Piper could not load or synthesize the selected voice'}
        result['id'] = request.get('id') if isinstance(request, dict) else None
        print(json.dumps(result, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
