const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), { webcrypto } = require('node:crypto');
(async () => {
    let interval, activeStream = false, resolveTranscript, focus = 'a', commits = [], calls = [], listeners = {}, micRequests = 0, nativeFailure=false, captureId=0, delayRelease=false, confirmRelease;
    const voice = { activeCapture: null, requireTranscription: async () => {}, acquireCapture(owner, preempt) { if (this.activeCapture && this.activeCapture !== owner) return false; this.activeCapture = owner; return true; } };
    const window = { Axx: { nativeVoice: voice, backendRequest: async (method, path, body) => {
        calls.push({ method, path, body });
        if (path.endsWith('/models')) return { models: [] };
        if (path.endsWith('/transcribe')) return await new Promise(resolve => { resolveTranscript = resolve; });
        return {};
    } }, __TAURI__: { core: { invoke: async (name, { request, shortcut }) => {
        if (name === 'dictation_shortcut') return { shortcut: shortcut || { key:68,modifiers:7,activation:'toggle' }, registered:true };
        if (request.action === 'start') return { session: 'synthetic-session' };
        if (request.action === 'probe') return { editable: !!focus, target: focus };
        if (request.action === 'audio_start') { if(nativeFailure)throw Error('Device unavailable'); assert.equal(activeStream,false,'One native stream'); micRequests++;activeStream=true;return {capture:String(++captureId),sample_rate:16000,microphone_open:true}; }
        if (request.action === 'audio_stop' || request.action === 'stop') { if(delayRelease)await new Promise(resolve=>{confirmRelease=resolve;});activeStream=false;return {microphone_open:false}; }
        if (request.action === 'commit') { commits.push(request); return { status: request.target === focus ? 'inserted' : 'pending' }; }
        return {};
    } }, event: { listen: async (name, fn) => { listeners[name] = fn; } } }, dispatchEvent() {}, addEventListener() {} };
    const sandbox = { window, navigator: { mediaDevices: { getUserMedia: async () => { throw Error('Global capture must be native'); } } },
        document: { getElementById: () => null, body: {} }, localStorage: { getItem: () => null, setItem() {} },
        MutationObserver: class { observe() {} }, CustomEvent: class {},
        setInterval: fn => { interval = fn; }, setTimeout:(fn,ms)=>setTimeout(fn,Math.min(ms,10)), clearTimeout, Float32Array, ArrayBuffer, DataView, crypto: webcrypto, btoa: s => Buffer.from(s, 'binary').toString('base64'), structuredClone, console };
    vm.runInNewContext(fs.readFileSync(require.resolve('./dictation-engine.js'), 'utf8'), sandbox);
    const api = window.Axx.dictation, settle = () => new Promise(resolve => setImmediate(resolve));
    const pulse = async () => { interval(); for(let i=0;i<6;i++)await settle(); };
    assert.equal(api.status().state, 'OFF'); assert.equal(micRequests, 0, 'Never open a mic on startup');
    await api.start('focus'); assert.equal(api.status().state, 'CAPTURING'); assert.equal(micRequests, 1);
    const feed = value => listeners['axx-dictation-pcm']({payload:{session:'synthetic-session',capture:String(captureId),target:focus,samples:Array(1600).fill(Math.round(value*32768))}});
    for (let i = 0; i < 10; i++) feed(0);
    for (let i = 0; i < 5; i++) feed(.02);
    for (let i = 0; i < 8; i++) feed(0);
    await settle(); assert.equal(api.status().decoding, true);
    assert.equal(activeStream, true, 'Pauses and decoding keep the same microphone stream');
    focus = 'b'; await pulse(); resolveTranscript({ text: '123,45 mg' }); await settle(); await settle();
    assert.equal(commits.length, 1); assert.equal(commits[0].target, 'a', 'Never retarget an old segment');
    assert.equal(api.pending()[0].status, 'pending');
    assert.ok(calls.every(c => c.path.startsWith('/axx-api/speech/')), 'No chat, commands or permissions calls');
    voice.activeCapture.stop(); await voice.waitForNativeCaptureRelease(); assert.equal(api.status().state, 'PAUSED'); assert.equal(activeStream, false);
    await pulse(); assert.equal(micRequests, 1, 'A preempted global session cannot steal back the mic');
    api.resume(); await settle(); await settle(); assert.equal(micRequests, 2);
    listeners['axx-dictation-cancel'](); await voice.waitForNativeCaptureRelease(); assert.equal(api.status().state, 'OFF'); assert.equal(activeStream, false); assert.deepEqual(api.pending(), []);
    await pulse(); assert.equal(micRequests, 2);
    await api.start('manual');
    api.finish(); assert.equal(api.status().state, 'OFF', 'A finished manual session must allow the next press');
    await voice.waitForNativeCaptureRelease();
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
    await voice.waitForNativeCaptureRelease();
    assert.equal(commits.length, beforeHold + 1); assert.equal(api.status().state, 'OFF');
    assert.equal(activeStream, false);
    const afterHold = micRequests;
    voice.activeCapture = { stop() { throw Error('must not preempt conversation'); } };
    await api.start('focus'); assert.equal(micRequests, afterHold);
    api.stop();
    voice.activeCapture=null;window.Axx.liveConversation={active:true};
    await api.start('focus');assert.equal(micRequests,afterHold);assert.equal(api.status().waiting_for_voice,true);
    window.Axx.liveConversation.active=false;await pulse();assert.equal(activeStream,true);
    window.Axx.companion={speaking:true};await pulse();await voice.waitForNativeCaptureRelease();assert.equal(activeStream,false);assert.equal(api.status().state,'PAUSED');
    api.stop();
    window.Axx.companion.speaking=false;nativeFailure=true;
    await api.start('focus');await voice.waitForNativeCaptureRelease();assert.equal(api.status().state,'ERROR');assert.equal(activeStream,false,'A failed native initialization cannot retain the microphone');
    api.stop();nativeFailure=false;
    assert.equal(api.conflictsWithShortcut('Ctrl+Alt+Shift+D'),true);
    voice.wake={hotkey:'Ctrl+Alt+Q'};
    await assert.rejects(api.configureShortcut({key:81,modifiers:3,activation:'toggle'}),/comandos de voz/);
    let stoppedCommands=0;window.Axx.symbiosis={use:'command',dictation:{stop(){stoppedCommands++;}}};
    await api.start('focus');assert.equal(stoppedCommands,1,'Switching to dictation cancels the old command capture before new speech');
    delayRelease=true;api.pause();await settle();assert.equal(activeStream,true);assert.equal(api.status().microphone_open,true,'Report the microphone open until native release is confirmed');
    let released=false;const waiting=voice.waitForNativeCaptureRelease().then(()=>{released=true;});await settle();assert.equal(released,false);delayRelease=false;confirmRelease();await waiting;assert.equal(activeStream,false);
    api.resume();await settle();await settle();
    const oldCapture=String(captureId-1);
    listeners['axx-dictation-audio-stopped']({payload:{session:'synthetic-session',capture:oldCapture,error:true}});assert.equal(api.status().state,'CAPTURING','Ignore stale stop events');
    listeners['axx-dictation-audio-stopped']({payload:{session:'synthetic-session',capture:String(captureId),error:true}});await voice.waitForNativeCaptureRelease();assert.equal(api.status().state,'ERROR');assert.equal(activeStream,false);
    api.stop();await voice.waitForNativeCaptureRelease();
    console.log('PASS: global opt-in, one stream, sustained decoding, old-focus pending, no auto-submit, priority, pause/resume, Escape and OFF cleanup');
})().catch(error => { console.error(error); process.exitCode = 1; });
