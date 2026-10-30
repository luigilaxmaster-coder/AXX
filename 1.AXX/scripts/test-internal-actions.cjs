/** Full UI and real controllers; simulated Windows IPC and microphone boundaries. */
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
    const server = http.createServer((req, res) => {
        const file = req.url.startsWith('/scripts/') ? path.join(__dirname, path.basename(req.url)) : path.join(__dirname, '../Axx.html');
        res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : 'text/html'); res.end(fs.readFileSync(file));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const browser = await chromium.launch({headless:true, executablePath:process.env.AXX_TEST_CHROMIUM});
    const results = [];
    try {
        const page = await browser.newPage({viewport:{width:1300,height:1000}}), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
            window.testConversation = {id:'internal-test',title:'Internal test',messages:[],draft:'',mode:'ask',context:[],links:[],connect_id:'internal-connect',memory_scope:{task_id:'internal-test',generation:0}};
            window.calls = []; window.rec = {state:'ready',id:''}; window.mediaPlaying = true;
            window.__TAURI__ = {core:{invoke:async (name,args) => {
                calls.push({name,args});
                const desktop = {workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
                if (name === 'native_status') return {native:true,backendReady:false,desktop};
                if (name === 'desktop_layout') return {...desktop,...args};
                if (name === 'capture_select') return {x:10,y:20,width:400,height:300};
                if (name === 'system_media_status') return {audioAvailable:true,updatedAt:Date.now(),sessions:[{id:'player',playing:mediaPlaying,canPlay:true,canPause:true,title:'Prueba',app:'Player'}]};
                if (name === 'system_media_control') { mediaPlaying = args.command === 'play'; return true; }
                if (name === 'backend_request') {
                    if (args.path === '/axx-api/chat/migrate') return {id:testConversation.id};
                    if (args.path === '/axx-api/chat/conversations') return {conversations:[testConversation],groups:[],default_mode:'ask'};
                    if (args.path.startsWith('/axx-api/chat/conversations?id=')) return structuredClone(testConversation);
                    if (args.path === '/axx-api/chat/save') { Object.assign(testConversation,args.body); return {saved:true}; }
                    if (args.path === '/axx-api/chat/operations') return {operations:[]};
                    if (args.path === '/axx-api/screen/status') return {...rec};
                    if (args.path === '/axx-api/screen/start') return rec = {state:'running',id:'test',region:args.body.region,fps:30};
                    if (args.path === '/axx-api/screen/control') return rec = {...rec,state:({pause:'paused',resume:'running',stop:'finished'})[args.body.command]};
                    if (args.path === '/axx-api/connect/ui/claim') return {tasks:[]};
                    if (/\/(commands\/resolve|learning\/propose|chat)$/.test(args.path)) throw Error('Internal command escaped to model/desktop');
                    return {};
                }
                return null;
            }},event:{listen:async () => () => {}}};
        });
        await page.goto('http://127.0.0.1:' + server.address().port);
        await page.waitForFunction(() => window.Axx?.nativeCapture?.backendReady && Axx.resident?.firstFrame && Axx.chatWorkspace?.ready);
        await page.evaluate(() => { Axx.companion.data.prefs.mutedAll = true; Axx.companion.data.prefs.voiceRead = false; });
        const send = text => page.evaluate(text => Axx.companion.send(text), text);
        const voice = text => page.evaluate(text => { Axx.symbiosis.use = 'command'; Axx.symbiosis.onFinal(text); }, text);
        await send('Oye Axx, puedes abrir el chat por favor?');
        assert.equal(await page.evaluate(() => Axx.companion.currentFeature), 'chat');
        await voice('abre las notas');
        await page.waitForFunction(() => Axx.companion.currentFeature === 'notes');
        await send('inicia chat');
        assert.equal(await page.evaluate(() => Axx.companion.currentFeature), 'chat');
        const missing = await page.evaluate(() => Axx.FEATURES.filter(f => Axx.commandLibrary.internalAction('abre ' + f.title)?.id !== f.id).map(f => f.id));
        assert.deepEqual(missing, [], 'Every registered feature title must be reachable');
        for (const text of ['no abras chat','explica cómo grabar','abre youtube y busca gatitos','anota abre chat','abre chat y borra mis notas']) {
            assert.equal(await page.evaluate(text => Axx.commandLibrary.internalAction(text), text), null);
        }
        results.push('Text and recognized voice open internal panels; all feature titles resolve; negatives and compound requests are not swallowed');
        await page.evaluate(() => { Axx.commandLibrary.operation = {operation_id:'pending'}; Axx.commandLibrary.learningQuestion = {request:'pending'}; });
        await send('abre grabar');
        assert.equal(await page.evaluate(() => Axx.actions.selected), 'screen');
        assert.equal(await page.evaluate(() => calls.filter(c => c.name === 'capture_select').length), 0);
        assert.equal(await page.evaluate(() => Axx.commandLibrary.learningQuestion.request), 'pending');
        await page.evaluate(() => { Axx.commandLibrary.operation = null; Axx.commandLibrary.learningQuestion = null; });
        await voice('graba la pantalla');
        await page.waitForFunction(() => Axx.nativeCapture.state === 'running');
        await send('empieza a grabar');
        assert.equal(await page.evaluate(() => calls.filter(c => c.name === 'capture_select').length), 1);
        await send('pausa la grabación');
        assert.equal(await page.evaluate(() => Axx.nativeCapture.state), 'paused');
        await voice('reanuda la grabación');
        await page.waitForFunction(() => Axx.nativeCapture.state === 'running');
        await send('finaliza la grabación');
        assert.equal(await page.evaluate(() => Axx.nativeCapture.state), 'finished');
        results.push('Opening recording does not capture; voice starts area selection; repeat start is idempotent; pause/resume/stop use capture IPC');
        await send('pausa la música');
        assert.equal(await page.evaluate(() => mediaPlaying), false);
        await send('continúa la música');
        assert.equal(await page.evaluate(() => mediaPlaying), true);
        await send('inicia el cronómetro');
        assert.equal(await page.evaluate(() => Axx.actions.tools.stopwatch.running), true);
        await voice('pausa el cronómetro');
        await page.waitForFunction(() => !Axx.actions.tools.stopwatch.running);
        await send('inicia el temporizador');
        assert.equal(await page.evaluate(() => Axx.app.store.data.timer.status), 'running');
        await send('pausa el temporizador');
        assert.equal(await page.evaluate(() => Axx.app.store.data.timer.status), 'paused');
        await send('cancela el temporizador');
        await send('inicia la lectura');
        assert.match(await page.evaluate(() => Axx.companion.data.messages.at(-1).text), /Añade el texto/);
        results.push('Music uses observed Windows playback; stopwatch and timer change their real local state');
        await send('abre dictar');
        assert.equal(await page.evaluate(() => Axx.voice13.entered), true);
        assert.equal(await page.evaluate(() => Axx.voice13.active), false);
        await send('empieza a dictar');
        assert.equal(await page.evaluate(() => Axx.voice13.permit), true);
        await page.evaluate(() => {
            const v = Axx.voice13;
            v.consent = true; v.permit = false;
            v.meter.start = async () => true;
            v.capture.start = () => { v.capture.state = 'listening'; v.capture.onState?.(); };
            v.capture.finish = () => { v.capture.onFinal?.('Texto dictado de prueba'); v.capture.state = 'idle'; v.capture.onState?.(); v.capture.onEnded?.(); };
        });
        await voice('empieza a dictar');
        await page.waitForFunction(() => Axx.voice13.status === 'listening', null, {timeout:3000}).catch(async error => {
            throw Error(error.message + '\n' + JSON.stringify(await page.evaluate(() => ({voice:Axx.voice13.snapshot(),last:Axx.companion.data.messages.at(-1),visible:Axx.app.machine.visible,pad:document.getElementById('v13-pad').outerHTML.slice(0,400),targetRect:Axx.voice13.target?.field.getClientRects().length,body:document.body.className}))));
        });
        await send('termina el dictado');
        assert.match(await page.evaluate(() => Axx.voice13.transcript), /Texto dictado de prueba/);
        results.push('Dictation uses its existing permission, destination, microphone start and graceful transcription stop');
        await page.evaluate(() => { Axx.nativeCapture.backendReady = false; });
        await send('graba');
        assert.match(await page.evaluate(() => Axx.companion.data.messages.at(-1).text), /No se pudo completar.*preparando/);
        await page.evaluate(() => { Axx.nativeMusic.refresh = async () => {}; Axx.nativeMusic.snapshot.sessions = []; });
        await send('reproduce música');
        assert.match(await page.evaluate(() => Axx.companion.data.messages.at(-1).text), /No hay un reproductor/);
        results.push('Missing reader content, unavailable recorder and absent media session report requirements instead of success');
        const handoff = await page.evaluate(async () => {
            const session = Axx.nativeVoice.sessions.find(s => s.owner === Axx.symbiosis.dictation), owner = session.owner;
            const request = Axx.backendRequest, final = owner.onFinal, ended = owner.onEnded;
            let staleEnded = false;
            Axx.backendRequest = async () => ({text:'abre chat'});
            owner.onFinal = () => { session.stop(); owner.state = 'starting'; };
            owner.onEnded = () => { staleEnded = true; };
            try { await session.submit(new Blob(['test'], {type:'audio/webm'})); return {state:owner.state,staleEnded}; }
            finally { Axx.backendRequest = request; owner.onFinal = final; owner.onEnded = ended; }
        });
        assert.deepEqual(handoff, {state:'starting',staleEnded:false});
        results.push('Completed voice transcription cannot overwrite a new microphone session or emit stale onEnded');
        assert.equal(await page.evaluate(() => calls.some(c => /\/(commands\/resolve|learning\/propose|chat)$/.test(c.args?.path || ''))), false);
        assert.deepEqual(errors, []);
        const report = {kind:'FULL_UI_CONTROLLED_IPC_AND_MICROPHONE',passed:results.length,results,uncaught:errors};
        const reportDir = path.resolve(__dirname, '../../build/desktop-validation');
        fs.mkdirSync(reportDir, {recursive:true});
        fs.writeFileSync(path.join(reportDir, 'internal-actions.json'), JSON.stringify(report,null,2));
        console.log(JSON.stringify(report,null,2));
    } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
