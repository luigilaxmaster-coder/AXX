"""Render a short Axx explanation as a private Telegram Opus voice note."""
import base64
import io
from pathlib import Path
import textwrap

import av


def render_voice_note(speech, text, voice, target, language='es'):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 900:
        raise ValueError('La explicación debe contener entre 1 y 900 caracteres.')
    if not isinstance(voice, str) or not voice.startswith(('moss:', 'piper:')):
        raise ValueError('Selecciona una voz local MOSS o Piper.')
    if language not in ('es', 'en'):
        raise ValueError('El idioma de la nota debe ser español o inglés.')
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    try:
        with av.open(str(temporary), 'w', format='ogg') as output:
            stream = output.add_stream('libopus', rate=48000)
            stream.layout = 'mono'
            resampler = av.AudioResampler(format='s16', layout='mono', rate=48000)
            for part in textwrap.wrap(text.strip(), width=180, break_long_words=False, break_on_hyphens=False):
                request = {'text': part, 'voice': voice, 'rate': 0, 'volume': 100}
                if voice.startswith('moss:'):
                    request['language'] = language
                result = speech.synthesize(request)
                if result.get('mime') != 'audio/wav':
                    raise ValueError('La voz local no devolvió un WAV.')
                raw = base64.b64decode(result['audio_base64'], validate=True)
                if not 44 < len(raw) <= 12 * 1024 * 1024:
                    raise ValueError('El audio generado supera el límite.')
                with av.open(io.BytesIO(raw)) as source:
                    if len(source.streams.audio) != 1:
                        raise ValueError('El audio generado no tiene una pista válida.')
                    for frame in source.decode(audio=0):
                        for ready in resampler.resample(frame):
                            for packet in stream.encode(ready):
                                output.mux(packet)
            for ready in resampler.resample(None):
                for packet in stream.encode(ready):
                    output.mux(packet)
            for packet in stream.encode(None):
                output.mux(packet)
        if not 100 < temporary.stat().st_size <= 8 * 1024 * 1024:
            raise ValueError('La nota de voz está vacía o supera el límite.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
