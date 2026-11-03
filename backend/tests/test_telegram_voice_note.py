import base64
import io
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock
import wave

import av

from backend.telegram.voice_note import render_voice_note


class VoiceNoteTests(unittest.TestCase):
    def test_local_wav_becomes_opus_and_invalid_text_is_rejected(self):
        samples = [int(5000 * math.sin(i * 2 * math.pi * 220 / 16000)) for i in range(16000)]
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
        speech = Mock()
        speech.synthesize.return_value = {'mime': 'audio/wav', 'audio_base64': base64.b64encode(buffer.getvalue()).decode()}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'note.ogg'
            render_voice_note(speech, 'Hola, esta es la explicación.', 'moss:axx-morcito', target)
            with av.open(str(target)) as output:
                self.assertEqual(output.streams.audio[0].codec_context.name, 'opus')
                self.assertGreater(output.duration / av.time_base, .9)
            with self.assertRaises(ValueError):
                render_voice_note(speech, 'x' * 901, 'moss:axx-morcito', target)
            self.assertEqual(speech.synthesize.call_count, 1)
            self.assertEqual(speech.synthesize.call_args.args[0]['language'], 'es')
            render_voice_note(speech, 'Hola otra vez.', 'piper:es_ES-carlfm-x_low', target)
            self.assertNotIn('language', speech.synthesize.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
