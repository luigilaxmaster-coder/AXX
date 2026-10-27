/** Real Web Audio clock checks with controlled PCM; native voice measured separately. */
const assert = require('node:assert/strict');
const path = require('node:path');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
    const browser = await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM,
        args:['--autoplay-policy=no-user-gesture-required']});
    try {
        const page=await browser.newPage();
        await page.setContent('<html><body>PCM contract test</body></html>');
        await page.evaluate(() => {
            window.Axx={nativeVoice:{},backendRequest:async(method,path,body)=>{
                if(path.endsWith('/start')) {window.starts.push(body.text);window.languages.push(body.language);window.poll=0;return {stream_id:'fixture'};}
                if(path.endsWith('/poll')) {
                    window.poll++;
                    if(window.poll===1)return {events:[{seq:1,pcm_base64:btoa('\x01\x01'.repeat(4800)),sample_rate:24000,channels:1}],done:false};
                    await new Promise(r=>setTimeout(r,1200));window.completedAt=performance.now();
                    return {events:[{seq:2,pcm_base64:btoa('\x01\x01'.repeat(4800)),sample_rate:24000,channels:1}],done:true};
                }
            }};
            window.starts=[];window.languages=[];window.completedAt=null;
            window.reader={chunks:['Hola, Axx. Hello, Axx.'],lang:'es-DO',index:0,offset:0,rate:1,generation:1,state:'starting',onEnded(){window.ended=true;}};
        });
        await page.addScriptTag({path:path.join(__dirname,'native-speech-stream.js')});
        await page.addScriptTag({path:path.join(__dirname,'voice-conversation.js')});
        await page.evaluate(()=>{window.stream=reader.nativeStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-alba'},1);window.task=stream.play();});
        await page.waitForFunction(()=>Axx.nativeVoice.playback?.playing_event);
        const timing = await page.evaluate(()=>({first:Axx.nativeVoice.playback.first_audio_ms,total:window.completedAt ? window.completedAt-stream.started : Infinity}));
        assert(timing.first >= 1200,'Playback must wait for a complete phrase rather than starving between PCM packets');
        await page.evaluate(async()=>{reader.state='paused';await stream.pause();window.pausedTime=stream.context.currentTime;});
        await page.waitForTimeout(150);
        assert(await page.evaluate(()=>Math.abs(stream.context.currentTime-pausedTime)<.01),'Pause must stop the actual audio clock');
        await page.evaluate(()=>stream.resume());
        await page.waitForFunction(()=>window.ended);
        assert.deepEqual(await page.evaluate(()=>starts),['Hola, Axx.','Hello, Axx.']);
        assert.deepEqual(await page.evaluate(()=>languages),['es-DO','es-DO']);
        assert(await page.evaluate(()=>Axx.nativeVoice.playback.ended_event));
        assert.equal(await page.evaluate(()=>Axx.nativeVoice.playback.underruns),0,'No underruns inside a buffered phrase');
        await page.evaluate(()=>{reader.generation=2;reader.index=0;reader.chunks=['Cancel me'];window.ended=false;window.cancelledStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-alba'},2);window.cancelTask=cancelledStream.play();});
        await page.waitForTimeout(80);
        await page.evaluate(async()=>{reader.generation++;await cancelledStream.stop();await cancelTask;});
        assert(await page.evaluate(()=>cancelledStream.sources.size===0&&!window.ended));
        await page.evaluate(()=>{reader.generation=3;reader.index=0;reader.chunks=['Primera frase.'];reader.awaitingText=true;window.ended=false;window.starts=[];window.liveStream=reader.nativeStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-alba'},3);window.liveTask=liveStream.play();});
        await page.waitForFunction(()=>liveStream.played && !liveStream.sources.size && !liveStream.pending);
        await page.waitForTimeout(150);
        assert(await page.evaluate(()=>!window.ended && liveStream.valid()),'A temporary text gap must not finish the voice turn');
        await page.evaluate(()=>reader.chunks.push('Segunda frase.'));
        await page.waitForFunction(()=>starts.length===2);
        await page.evaluate(()=>{reader.awaitingText=false;});
        await page.waitForFunction(()=>window.ended);
        assert.deepEqual(await page.evaluate(()=>starts),['Primera frase.','Segunda frase.']);
        await page.evaluate(()=>{
            Axx.backendRequest=async(method,path,body)=>{
                if(path.endsWith('/start')){window.poll=0;window.cached=body.text==='Una frase ya guardada.';return {stream_id:'fast'};}
                await new Promise(r=>setTimeout(r,window.cached?10:window.slowdown && window.poll===4?1600:120));
                window.poll++;
                if(window.poll===8)window.fastCompleted=performance.now();
                return {events:[{seq:window.poll,pcm_base64:btoa('\x01\x01'.repeat(7680)),sample_rate:24000,channels:1,elapsed_ms:window.poll*120,cache_hit:window.cached}],done:window.poll===8};
            };
            reader.generation=4;reader.index=0;reader.chunks=['Una frase que empieza antes de terminar la síntesis.'];
            window.ended=false;window.fastCompleted=null;
            window.fastStream=reader.nativeStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-sam'},4);
            window.fastTask=fastStream.play();
        });
        await page.waitForFunction(()=>fastStream.played);
        assert(await page.evaluate(()=>fastCompleted===null),'Fast synthesis must play before its last packet');
        await page.waitForFunction(()=>window.ended);
        assert.equal(await page.evaluate(()=>fastStream.evidence.underruns),0);
        assert.equal(await page.evaluate(()=>fastStream.evidence.streamed_phrases),1);
        await page.evaluate(()=>{
            window.slowdown=true;window.ended=false;reader.generation=5;reader.index=0;
            reader.chunks.push('Una frase ya guardada.');
            window.recoveryStream=reader.nativeStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-sam'},5);
            window.recoveryTask=recoveryStream.play();
        });
        await page.waitForFunction(()=>window.ended);
        assert.equal(await page.evaluate(()=>recoveryStream.evidence.rebufferings),1,'A CPU stall must buffer the remaining phrase');
        assert.equal(await page.evaluate(()=>recoveryStream.evidence.underruns),1,'A single stall must not cause repeated chopped playback');
        assert.equal(await page.evaluate(()=>recoveryStream.evidence.cached_phrases),1,'A stalled phrase must not delay later cache hits');
        console.log('PASS: adaptive early playback, slow CPU phrase buffering, no underruns, ES/EN order, pause/resume and cancellation');
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
