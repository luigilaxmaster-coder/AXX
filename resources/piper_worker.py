"""Resident Piper process. All model paths are selected by the parent service."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import re
import sys
import wave

from piper import PiperVoice, SynthesisConfig


MODELS = {'es_ES-carlfm-x_low', 'es_MX-ald-medium'}
# Private voices trained locally (e.g. axx-morcito-es). The name never contains
# path separators, so the model is always resolved inside the given directory.
PRIVATE = re.compile(r'axx-[a-z0-9]+(?:-[a-z0-9]+){0,4}')


def _bounded(request, key, low, high):
    value = request.get(key)
    if value is None:
        return None
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError('Invalid synthesis parameter')
    return float(value)


def main():
    directory = Path(sys.argv[1])
    loaded = {}
    print('{"ready":true}', flush=True)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            name = request['voice']
            if not isinstance(name, str) or not (name in MODELS or PRIVATE.fullmatch(name)):
                raise ValueError('Unsupported Piper voice')
            if name not in loaded:
                loaded[name] = PiperVoice.load(str(directory / (name + '.onnx')))
            if request.get('prepare'):
                result = {'ok': True}
            else:
                output = io.BytesIO()
                style_length = _bounded(request, 'length_factor', .6, 1.6) or 1.0
                with wave.open(output, 'wb') as audio:
                    config = SynthesisConfig(length_scale=style_length / (1 + request['rate'] * .1),
                                             noise_scale=_bounded(request, 'noise_scale', 0, 1.2),
                                             noise_w_scale=_bounded(request, 'noise_w', 0, 1.5),
                                             volume=request['volume'] / 100)
                    loaded[name].synthesize_wav(request['text'], audio, syn_config=config)
                result = {'audio_base64': base64.b64encode(output.getvalue()).decode('ascii')}
        except Exception:
            result = {'error': 'Piper could not load or synthesize the selected voice'}
        result['id'] = request.get('id') if isinstance(request, dict) else None
        print(json.dumps(result, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
