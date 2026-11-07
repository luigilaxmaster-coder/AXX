from pathlib import Path

# 1. voice-conversation.js
p1 = Path("1.AXX/scripts/voice-conversation.js")
c1 = p1.read_text(encoding="utf-8")
c1 = c1.replace(
    "window.setInterval(() => Axx.voiceConversation.maybeSurprise(), 30_000);",
    "if (typeof window.setInterval === 'function') window.setInterval(() => Axx.voiceConversation?.maybeSurprise?.(), 30_000);"
)
p1.write_text(c1, encoding="utf-8")

# 2. native-speech-stream.js: improve reserve capping and safe error recovery
p2 = Path("1.AXX/scripts/native-speech-stream.js")
c2 = p2.read_text(encoding="utf-8")
old_reserve = "const reserve = .6 + Math.max(0, Math.max(1, expectedSeconds - seconds) * (ratio - 1 / speed));"
new_reserve = "const reserve = Math.min(2.2, .6 + Math.max(0, Math.max(1, expectedSeconds - seconds) * (ratio - 1 / speed)));"
if old_reserve in c2:
    c2 = c2.replace(old_reserve, new_reserve)

old_phrase_call = "await this.phrase(remaining.slice(0, length).trim(), index);"
new_phrase_call = """const chunk = remaining.slice(0, length).trim();
                        if (chunk) {
                            try {
                                await this.phrase(chunk, index);
                            } catch (e) {
                                console.warn('[native-stream] phrase failed:', e);
                            }
                        }"""
if old_phrase_call in c2:
    c2 = c2.replace(old_phrase_call, new_phrase_call)

p2.write_text(c2, encoding="utf-8")

# 3. moss_tts.py: bump validation limit to 360 chars to avoid unnecessary freezes
p3 = Path("backend/speech/moss_tts.py")
c3 = p3.read_text(encoding="utf-8")
c3 = c3.replace("<= 220 or '\\x00' in body['text']:\n            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 220 characters')",
                "<= 360 or '\\x00' in body['text']:\n            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 360 characters')")
c3 = c3.replace("<= 220 or '\\x00' in body['text']:\r\n            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 220 characters')",
                "<= 360 or '\\x00' in body['text']:\r\n            raise SpeechError('INVALID_REQUEST', 'MOSS voice requires 1 to 360 characters')")
p3.write_text(c3, encoding="utf-8")

print("All streaming & conversational patches applied!")
