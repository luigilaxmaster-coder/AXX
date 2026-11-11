const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), { webcrypto } = require('node:crypto');
(async () => {
    let processor, interval, activeStream = false, resolveTranscript, focus = 'a', commits = [], calls = [], listeners = {}, micRequests = 0;
    const track = { stop() { activeStream = false; }, addEventListener() {} };
    const voice = { activeCapture: null, requireTranscription: async () => {}, acquireCapture(owner, preempt) { if (this.activeCapture && this.activeCapture !== owner) return false; this.activeCapture = owner; return true; } };
    class Context {
        sampleRate = 16000;
        resume() { return Promise.resolve(); } close() { return Promise.resolve(); }
        createMediaStreamSource() { return { connect() {} }; }
        createGain() { return { gain: {}, connect() {} }; }
        createScriptProcessor() { return processor = { connect() {}, disconnect() {} }; }
    }
    const window = { Axx: { nativeVoice: voice, backendRequest: async (method, path, body) => {
        calls.push({ method, path, body });
        if (path.endsWith('/models')) return { models: [] };
        if (path.endsWith('/transcribe')) return await new Promise(resolve => { resolveTranscript = resolve; });
        return {};
    } }, __TAURI__: { core: { invoke: async (name, { request, shortcut }) => {
        if (name === 'dictation_shortcut') return { shortcut: shortcut || { key:68,modifiers:7,activation:'toggle' }, registered:true };
        if (request.action === 'start') return { session: 'synthetic-session' };
        if (request.action === 'probe') return { editable: !!focus, target: focus };
        if (request.action === 'commit') { commits.push(request); return { status: request.target === focus ? 'inserted' : 'pending' }; }
        return {};
    } }, event: { listen: async (name, fn) => { listeners[name] = fn; } } }, dispatchEvent() {}, addEventListener() {} };
    const sandbox = { window, navigator: { mediaDevices: { getUserMedia: async () => { micRequests++; activeStream = true; return { getTracks: () => [track] }; } } },
        document: { getElementById: () => null, body: {} }, localStorage: { getItem: () => null, setItem() {} },
        AudioContext: Context, MutationObserver: class { observe() {} }, CustomEvent: class {},
        setInterval: fn => { interval = fn; }, Float32Array, ArrayBuffer, DataView, crypto: webcrypto, btoa: s => Buffer.from(s, 'binary').toString('base64'), structuredClone, console };
    vm.runInNewContext(fs.readFileSync(require.resolve('./dictation-engine.js'), 'utf8'), sandbox);
    const api = window.Axx.dictation, settle = () => new Promise(resolve => setImmediate(resolve));
    assert.equal(api.status().state, 'OFF'); assert.equal(micRequests, 0, 'Never open a mic on startup');
    await api.start('focus'); assert.equal(api.status().state, 'CAPTURING'); assert.equal(micRequests, 1);
    const feed = value => processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(1600).fill(value) } });
    for (let i = 0; i < 10; i++) feed(0);
    for (let i = 0; i < 5; i++) feed(.02);
    for (let i = 0; i < 8; i++) feed(0);
    await settle(); assert.equal(api.status().decoding, true);
    assert.equal(activeStream, true, 'Pauses and decoding keep the same microphone stream');
    focus = 'b'; await interval(); resolveTranscript({ text: '123,45 mg' }); await settle(); await settle();
    assert.equal(commits.length, 1); assert.equal(commits[0].target, 'a', 'Never retarget an old segment');
    assert.equal(api.pending()[0].status, 'pending');
    assert.ok(calls.every(c => c.path.startsWith('/axx-api/speech/')), 'No chat, commands or permissions calls');
    voice.activeCapture.stop(); assert.equal(api.status().state, 'PAUSED'); assert.equal(activeStream, false);
    await interval(); assert.equal(micRequests, 1, 'A preempted global session cannot steal back the mic');
    api.resume(); await settle(); await settle(); assert.equal(micRequests, 2);
    listeners['axx-dictation-cancel'](); assert.equal(api.status().state, 'OFF'); assert.equal(activeStream, false); assert.deepEqual(api.pending(), []);
    await interval(); assert.equal(micRequests, 2);
    await api.start('manual');
    api.finish(); assert.equal(api.status().state, 'OFF', 'A finished manual session must allow the next press');
    assert.equal(activeStream, false);
    const afterManual = micRequests;
    listeners['axx-dictation-hold-start']();
    for (let i = 0; i < 6; i++) await settle();
    assert.equal(activeStream, true);
    for (let i = 0; i < 10; i++) feed(0);
    for (let i = 0; i < 5; i++) feed(.02);
    for (let i = 0; i < 8; i++) feed(0);
    const beforeHold = commits.length;
    resolveTranscript({ text: 'Texto al soltar' }); await settle(); await settle();
    assert.equal(commits.length, beforeHold, 'Do not type while shortcut modifiers are held');
    listeners['axx-dictation-hold-end'](); await settle(); await settle();
    assert.equal(commits.length, beforeHold + 1); assert.equal(api.status().state, 'OFF');
    assert.equal(activeStream, false);
    const afterHold = micRequests;
    voice.activeCapture = { stop() { throw Error('must not preempt conversation'); } };
    await api.start('focus'); assert.equal(micRequests, afterHold);
    api.stop();
    voice.activeCapture=null;window.Axx.liveConversation={active:true};
    await api.start('focus');assert.equal(micRequests,afterHold);assert.equal(api.status().waiting_for_voice,true);
    window.Axx.liveConversation.active=false;await interval();await settle();assert.equal(activeStream,true);
    window.Axx.companion={speaking:true};await interval();await settle();assert.equal(activeStream,false);assert.equal(api.status().state,'PAUSED');
    api.stop();
    console.log('PASS: global opt-in, one stream, sustained decoding, old-focus pending, no auto-submit, priority, pause/resume, Escape and OFF cleanup');
})().catch(error => { console.error(error); process.exitCode = 1; });
