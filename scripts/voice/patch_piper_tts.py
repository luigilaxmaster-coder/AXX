from pathlib import Path
import re

path = Path('C:/Users/luigi/Desktop/axx2/backend/speech/piper_tts.py')
content = path.read_text(encoding='utf-8')

# 1. Add prepare_spoken_text import
if 'from .speech_text import prepare_spoken_text' not in content:
    content = content.replace(
        'from .windows_tts import SpeechError',
        'from .speech_text import prepare_spoken_text\nfrom .windows_tts import SpeechError'
    )

# 2. Update STYLES
old_styles = """STYLES = {
    '': ('Natural', None, None, None),
    'calma': ('Tranquila', 1.12, .45, .55),
    'emocion': ('Emocionada', .88, .8, 1.05),
    'atencion': ('Atenta', .95, .6, .7),
}"""

new_styles = """STYLES = {
    '': ('Natural', 0.98, 0.60, 0.80),
    'calma': ('Tranquila', 1.08, 0.58, 0.75),
    'emocion': ('Emocionada', 0.90, 0.65, 0.85),
    'atencion': ('Atenta', 0.95, 0.60, 0.78),
}"""

if old_styles in content:
    content = content.replace(old_styles, new_styles)

# 3. Replace _apply_timbre_dsp to direct pass-through
dsp_block = re.search(r'# DSP alignment profiles.*?def _apply_timbre_dsp.*?return raw_bytes\n', content, re.DOTALL)
if dsp_block:
    replacement = """def _apply_timbre_dsp(raw_bytes: bytes, style: str) -> bytes:
    # Direct neural synthesis: raw Piper ONNX output already matches the target
    # pitch (160.4 Hz vs 160.9-164.6 Hz ground truth) without phase vocoder distortion.
    return raw_bytes\n"""
    content = content[:dsp_block.start()] + replacement + content[dsp_block.end():]

# 4. Update cancel_active to avoid killing worker
old_cancel = """    def cancel_active(self):
        if not self._busy.locked():
            return 0
        self._cancelled.set()
        self._stop()
        return 1"""

new_cancel = """    def cancel_active(self):
        if not self._busy.locked():
            return 0
        self._cancelled.set()
        return 1"""

if old_cancel in content:
    content = content.replace(old_cancel, new_cancel)

# 5. Update _request to drain stale responses
old_req_drain = """            response = responses.get(timeout=timeout)
            if not isinstance(response, dict) or response.get('id') != request_id or response.get('error'):
                raise ValueError('Invalid or failed Piper response')"""

new_req_drain = """            deadline = time.monotonic() + timeout
            while True:
                remaining = max(0.1, deadline - time.monotonic())
                response = responses.get(timeout=remaining)
                if not isinstance(response, dict):
                    raise ValueError('Invalid Piper response')
                if response.get('id') == request_id:
                    if response.get('error'):
                        raise ValueError(response['error'])
                    break"""

if old_req_drain in content:
    content = content.replace(old_req_drain, new_req_drain)

# 6. Update synthesize for language resolution, text cleaning, and model auto-routing
old_synth_start = """    def synthesize(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, uri = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200 or '\\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'Text must contain 1 to 1200 characters')
        if not isinstance(uri, str) or uri not in self._models() or type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper voice or rate')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper volume')
        if not self._busy.acquire(timeout=10):
            raise SpeechError('BUSY', 'Piper is preparing another voice')
        try:
            self._cancelled.clear()
            raw = base64.b64decode(self._request(uri, text, body.get('rate', 0), body.get('volume', 100))['audio_base64'], validate=True)"""

new_synth_start = """    def synthesize(self, body):
        if not isinstance(body, dict) or set(body) - {'text', 'voice', 'rate', 'volume', 'language'}:
            raise SpeechError('INVALID_REQUEST', 'Unsupported speech fields')
        text, uri = body.get('text'), body.get('voice')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1200 or '\\x00' in text:
            raise SpeechError('INVALID_REQUEST', 'Text must contain 1 to 1200 characters')
        if not isinstance(uri, str) or uri not in self._models() or type(body.get('rate', 0)) is not int or not -5 <= body.get('rate', 0) <= 5:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper voice or rate')
        if type(body.get('volume', 100)) is not int or not 0 <= body.get('volume', 100) <= 100:
            raise SpeechError('INVALID_REQUEST', 'Invalid Piper volume')

        # Clean spoken text and resolve language
        cleaned_text, lang = prepare_spoken_text(text, body.get('language', 'auto'))
        spoken_text = cleaned_text.strip() or text.strip()

        # Automatic language routing for axx-morcito
        target_uri = uri
        base_voice, at, style = uri.partition('@')
        if base_voice.startswith('piper:axx-morcito'):
            if lang == 'en' and 'piper:axx-morcito-en' in self._models():
                target_uri = 'piper:axx-morcito-en' + (at + style if style else '')
            elif lang == 'es' and 'piper:axx-morcito-es' in self._models():
                target_uri = 'piper:axx-morcito-es' + (at + style if style else '')

        if not self._busy.acquire(timeout=10):
            raise SpeechError('BUSY', 'Piper is preparing another voice')
        try:
            self._cancelled.clear()
            raw = base64.b64decode(self._request(target_uri, spoken_text, body.get('rate', 0), body.get('volume', 100))['audio_base64'], validate=True)"""

if old_synth_start in content:
    content = content.replace(old_synth_start, new_synth_start)

# Update return voice/language in synthesize
old_return = "'voice': uri, 'language': self._models()[uri][2],"
new_return = "'voice': uri, 'language': self._models()[target_uri][2],"
if old_return in content:
    content = content.replace(old_return, new_return)

path.write_text(content, encoding='utf-8')
print("Successfully updated piper_tts.py")
