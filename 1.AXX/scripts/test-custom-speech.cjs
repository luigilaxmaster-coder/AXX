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
            window.reader={chunks:['Hola, Axx.','Hello, Axx.'],lang:'es-DO',index:0,offset:0,rate:1,generation:1,state:'starting',onEnded(){window.ended=true;}};
        });
        await page.addScriptTag({path:path.join(__dirname,'native-speech-stream.js')});
        await page.evaluate(()=>{window.stream=reader.nativeStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-alba'},1);window.task=stream.play();});
        await page.waitForFunction(()=>Axx.nativeVoice.playback?.playing_event);
        const timing = await page.evaluate(()=>({first:Axx.nativeVoice.playback.first_audio_ms,total:window.completedAt ? window.completedAt-stream.started : Infinity}));
        assert(timing.first < timing.total, JSON.stringify(timing));
        await page.evaluate(async()=>{reader.state='paused';await stream.pause();window.pausedTime=stream.context.currentTime;});
        await page.waitForTimeout(150);
        assert(await page.evaluate(()=>Math.abs(stream.context.currentTime-pausedTime)<.01),'Pause must stop the actual audio clock');
        await page.evaluate(()=>stream.resume());
        await page.waitForFunction(()=>window.ended);
        assert.deepEqual(await page.evaluate(()=>starts),['Hola, Axx.','Hello, Axx.']);
        assert.deepEqual(await page.evaluate(()=>languages),['es-DO','es-DO']);
        assert(await page.evaluate(()=>Axx.nativeVoice.playback.ended_event));
        await page.evaluate(()=>{reader.generation=2;reader.index=0;reader.chunks=['Cancel me'];window.ended=false;window.cancelledStream=new Axx.CustomSpeechStream(reader,{name:'moss:axx-alba'},2);window.cancelTask=cancelledStream.play();});
        await page.waitForTimeout(80);
        await page.evaluate(async()=>{reader.generation++;await cancelledStream.stop();await cancelTask;});
        assert(await page.evaluate(()=>cancelledStream.sources.size===0&&!window.ended));
        console.log('PASS: progressive playback, ES/EN phrase order, pause/resume, completion and cancellation');
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
