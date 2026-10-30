// Installed TTS -> speaker -> real microphone -> installed ASR. No human-speech or listener claim.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const matches = (text, color, number) => {
  const words = new Set(normalize(text).split(' '));
  const digits = {tres:'3', cinco:'5', siete:'7', nueve:'9'};
  return ['archivo', color, 'paginas'].every(word => words.has(word)) && (words.has(number) || words.has(digits[number]));
};

if (process.argv.includes('--self-test')) {
  assert(matches('El archivo VERDE contiene 7 páginas.', 'verde', 'siete'));
  assert(!matches('El archivo rojo contiene siete páginas.', 'verde', 'siete'));
  assert(!matches('silencio', 'verde', 'siete'));
  console.log('Acoustic harness self-check: PASS; no microphone, speaker or model used');
} else main().catch(error => { console.error(error.message); process.exitCode = 1; });

async function main() {
  const args = process.argv.slice(2), index = args.indexOf('--output');
  assert(index === 0 && args.length === 2 && !args[1].startsWith('--'), 'Use --output DIRECTORY');
  const out = path.resolve(args[1]), file = path.join(out, 'acoustic-receipt.json');
  assert(!fs.existsSync(file), 'Choose a new output directory; an acoustic attempt is never overwritten');
  fs.mkdirSync(out, {recursive:true});
  const color = ['verde','rojo','azul'][crypto.randomInt(3)], number = ['tres','cinco','siete','nueve'][crypto.randomInt(4)];
  const text = `Prueba acústica de Axx. El archivo ${color} contiene ${number} páginas.`;
  const receipt = {kind:'INSTALLED_ACOUSTIC_LOOP', result:'IN_PROGRESS', stage:'connect', stimulus_sha256:hash(text),
    method:'selected installed TTS, actual playback, getUserMedia microphone, installed speech/transcribe',
    limitations:['Synthesized speech played acoustically, not human speech.', 'No claim that the user heard the output.',
      'Reported microphone identity is checked for obvious loopback devices; this is not a hardware attestation.'],
    raw_audio_retained:false, transcript_retained:false};
  const save = () => fs.writeFileSync(file, JSON.stringify(receipt, null, 2));
  const stage = value => {receipt.stage=value; save();};
  save();
  let browser;
  try {
    const {chromium} = require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
    browser = await chromium.connectOverCDP('http://127.0.0.1:9224');
    const pages = browser.contexts().flatMap(context => context.pages()).filter(page => page.url().includes('Axx.html'));
    assert.equal(pages.length, 1, 'Exactly one installed Axx page is required');
    const page = pages[0];
    await page.waitForFunction(() => Axx.nativeVoice && Axx.symbiosis?.reader, {}, {timeout:60000});
    const selection = await page.evaluate(() => {
      const reader = Axx.symbiosis.reader;
      if (Axx.nativeVoice.activeCapture || ['starting','speaking','paused'].includes(reader.state)) throw Error('Existing audio activity must finish first');
      if (Axx.companion.data.prefs.mutedAll) throw Error('Current app output is muted');
      return {voiceURI:reader.voiceURI, rate:reader.rate, device:Axx.nativeVoice.liveDeviceId || ''};
    });
    assert(typeof selection.voiceURI === 'string' && selection.voiceURI, 'Select an installed voice before this test');
    assert(!selection.voiceURI.startsWith('web:'), 'The selected browser voice has no installed synthesis endpoint');
    const voice = selection.voiceURI.replace(/^sapi:/, '');
    const status = await page.evaluate(() => Axx.nativeInvoke('native_status'));
    const runtime = JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'Axx/logs/native-runtime.json'),'utf8'));
    assert(status.backendReady && status.backendInstance, 'Native backend is not ready');
    assert.equal(runtime.backendInstance, status.backendInstance, 'Startup receipt belongs to another backend');
    assert.equal(runtime.version, JSON.parse(fs.readFileSync(path.join(__dirname,'../package.json'),'utf8')).version);
    assert.equal(path.resolve(runtime.executable).toLowerCase(), path.resolve(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe').toLowerCase());
    receipt.runtime = {version:runtime.version, backendInstance:runtime.backendInstance, pid:runtime.pid,
      executable_sha256:hash(fs.readFileSync(runtime.executable))};
    receipt.voice = voice;
    stage('synthesis');
    const started = Date.now();
    const synthesis = await page.evaluate(async ({text,voice,rate}) => {
      const catalog = await Axx.backendRequest('GET','/axx-api/speech/voices');
      if (!catalog.voices?.some(item => item.name === voice && item.enabled !== false)) throw Error('Selected voice is unavailable');
      return Axx.backendRequest('POST','/axx-api/speech/synthesize', {text,voice,rate,volume:100});
    }, {text,voice,rate:voice.startsWith('piper:') ? 0 : Math.max(-5,Math.min(5,Math.round((Number(selection.rate || 1)-1)*5)))});
    assert.equal(synthesis.mime, 'audio/wav');
    assert(typeof synthesis.audio_base64 === 'string' && synthesis.audio_base64.length <= 8*1024*1024, 'Invalid bounded synthesized audio');
    assert(synthesis.duration_seconds > 0 && synthesis.duration_seconds <= 35, 'The stimulus must be at most 35 seconds');
    const generated = Buffer.from(synthesis.audio_base64,'base64');
    assert.equal(hash(generated), synthesis.evidence?.sha256, 'Synthesis bytes differ from the installed receipt');
    receipt.synthesis = {engine:synthesis.engine, voice:synthesis.voice, sha256:hash(generated),
      duration_seconds:synthesis.duration_seconds, elapsed_ms:Date.now()-started};
    stage('physical_capture_and_playback');
    const capture = await page.evaluate(async ({audio,voice,device}) => {
      let stream, recorder, playback, url, chain, watchdog, decode;
      const chunks = [];
      const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
      const stop = () => {
        if (recorder?.state === 'recording') recorder.stop();
        stream?.getTracks().forEach(track => track.stop());
        playback?.pause();
      };
      try {
        if (Axx.nativeVoice.activeCapture) throw Error('Microphone acquired by another task');
        stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false,
          ...(device ? {deviceId:{exact:device}} : {})},video:false});
        const tracks = stream.getAudioTracks();
        if (tracks.length !== 1 || tracks[0].readyState !== 'live') throw Error('A single live audio input is required');
        const label = tracks[0].label || '';
        if (!label || /loopback|stereo mix|mezcla estereo|virtual|vb.audio|cable output|monitor of/i.test(label)) throw Error('Reported input is absent or a loopback device');
        const settings = tracks[0].getSettings();
        const mime = ['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
        if (!mime) throw Error('No supported capture format');
        recorder = new MediaRecorder(stream,{mimeType:mime});
        let count = 0;
        recorder.ondataavailable = event => {count += event.data.size; if (count > 8*1024*1024) stop(); else if(event.data.size)chunks.push(event.data);};
        const stopped = new Promise((resolve,reject) => {recorder.onstop=resolve; recorder.onerror=()=>reject(Error('Microphone recorder failed'));});
        const bytes = Uint8Array.from(atob(audio), c => c.charCodeAt(0));
        url=URL.createObjectURL(new Blob([bytes],{type:'audio/wav'}));
        playback=new Audio(url);
        if (Axx.voiceAudio) chain=Axx.voiceAudio.attach(playback,voice);
        let playing=false,ended=false;
        const completed = new Promise((resolve,reject) => {
          playback.onplaying=()=>{playing=true;};
          playback.onended=()=>{ended=true;resolve();};
          playback.onerror=()=>reject(Error('Speaker playback failed'));
        });
        recorder.start(100);
        // This timer remains in the WebView even if the harness disconnects.
        watchdog=setTimeout(stop,45000);
        await wait(300);
        if(chain)await chain.context.resume();
        await playback.play();
        await Promise.race([completed,wait(40000).then(()=>{throw Error('Speaker playback exceeded deadline');})]);
        await wait(700);stop();
        await Promise.race([stopped,wait(2000).then(()=>{throw Error('Microphone did not finish recording');})]);
        if(!playing || !ended || count>8*1024*1024)throw Error('Playback or capture did not complete');
        const blob=new Blob(chunks,{type:mime});
        const raw=await blob.arrayBuffer();
        decode=new AudioContext();
        const decoded=await decode.decodeAudioData(raw.slice(0));
        let sum=0,peak=0,samples=0;
        for(let channel=0;channel<decoded.numberOfChannels;channel++)for(const value of decoded.getChannelData(channel)){
          sum+=value*value;peak=Math.max(peak,Math.abs(value));samples++;
        }
        const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('Capture read failed'));reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.readAsDataURL(blob);});
        return {audio_base64:base64,mime,label,sample_rate:decoded.sampleRate,duration_seconds:decoded.duration,
          tracks:tracks.length,tracks_ended:tracks.every(track=>track.readyState==='ended'),playing_event:playing,ended_event:ended,
          echo_cancellation:settings.echoCancellation,noise_suppression:settings.noiseSuppression,
          rms:samples?Math.sqrt(sum/samples):0,peak};
      } finally {
        clearTimeout(watchdog);stop();chain?.dispose();if(url)URL.revokeObjectURL(url);if(decode)await decode.close();
      }
    }, {audio:synthesis.audio_base64,voice,device:selection.device});
    const recorded = Buffer.from(capture.audio_base64,'base64');
    receipt.capture = {...Object.fromEntries(Object.entries(capture).filter(([key])=>key!=='audio_base64')),
      sha256:hash(recorded),bytes:recorded.length};save();
    assert(capture.tracks_ended && capture.duration_seconds>0 && capture.duration_seconds<=50, 'Capture duration or cleanup invalid');
    assert(capture.rms>0.0001 && capture.peak>0.001, 'Microphone captured silence');
    stage('installed_local_transcription');
    const recognition = await page.evaluate(({audio_base64,mime}) => Axx.backendRequest('POST','/axx-api/speech/transcribe',
      {audio_base64,mime,language:'es',task:'transcribe'}), capture);
    assert.equal(recognition.engine, 'faster-whisper');assert.equal(recognition.external_calls,0);
    receipt.recognition = {engine:recognition.engine,model:recognition.model,device:recognition.device,
      transcript_sha256:hash(recognition.text || ''),matches_stimulus:matches(recognition.text,color,number),timings_ms:recognition.timings_ms};save();
    assert(receipt.recognition.matches_stimulus, 'The physical recording did not match the fresh stimulus');
    receipt.result='PASS';receipt.stage='complete';save();
    console.log(JSON.stringify({result:receipt.result,receipt:file,raw_audio_retained:false}));
  } catch(error) {
    receipt.result='FAIL';receipt.error_type=error.name;save();
    throw Error('Acoustic acceptance failed at '+receipt.stage+'; see '+file);
  } finally {if(browser)await browser.close();}
}
