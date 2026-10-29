const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const now = Date.now(), emitted = [], panel = { hidden: false, dataset: { view: 'chat' } };
const companion = {
    data: { prefs: { personalityStyle: 'playful' }, messages: [{ role: 'user', at: now - 180000 }] },
    message(role, text, source) { emitted.push({ role, text, source }); },
    renderChat() {}, save() {}, speakReply(text) { emitted.push({ spoken: text }); }
};
const Axx = { companion, voicePhrases: [], anticipation:{allowSurprises:()=>true} };
const window = { Axx, setInterval() {} };
const document = { visibilityState: 'visible', hasFocus: () => true, getElementById: () => panel };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'voice-conversation.js'), 'utf8'), { window, document, Date, Math });
const voice = Axx.voiceConversation;
voice.nextSurpriseAt = 0;
Axx.anticipation.allowSurprises=()=>false;
assert.equal(voice.maybeSurprise(now),false,'Discreto and quiet profiles never produce spontaneous speech');
Axx.anticipation.allowSurprises=()=>true;
assert.equal(voice.maybeSurprise(now), true);
assert.equal(emitted[0].source, 'local');
assert.equal(emitted[1].spoken, emitted[0].text);
assert.ok(voice.nextSurpriseAt >= now + 9 * 60000);
voice.nextSurpriseAt = 0; companion.pending = {};
assert.equal(voice.maybeSurprise(now), false, 'Never interrupt a running request');
companion.pending = null; panel.hidden = true;
assert.equal(voice.maybeSurprise(now), false, 'Never appear over a hidden chat');
panel.hidden = false; companion.data.prefs.personalityStyle = 'natural';
assert.equal(voice.maybeSurprise(now), false, 'Ordinary personalities never surprise');
console.log('PASS: playful surprise stays in chat, speaks only its local text, and respects busy/hidden/ordinary states');
