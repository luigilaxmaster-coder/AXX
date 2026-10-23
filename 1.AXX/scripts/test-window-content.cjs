/* Controlled UI contract; native reading is checked separately on Windows. */
const path = require('node:path'), assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.AXX_TEST_CHROMIUM});
  try {
    const page = await browser.newPage(), errors=[]; page.on('pageerror', e=>errors.push(e.message));
    await page.setContent('<section id="command-library"></section><p id="command-library-approval-summary"></p>');
    await page.evaluate(() => {
      window.calls=[]; window.notices=[]; window.testWindows=[{window_id:123,pid:10,title:'YouTube'}];
      window.Axx={resident:{schedule(){}}, companion:{send:async()=>{}, message(){}, localNotice:t=>notices.push(t), renderAttachment(){}, openFeature(){}},
        commandLibrary:{async prepare(id,inputs) { calls.push({id,inputs}); this.lastOperation={output:{windows:testWindows}}; return 'Preparado'; }}};
    });
    await page.addScriptTag({path:path.join(__dirname,'window-content.js')});
    await page.evaluate(()=>Axx.companion.send('lee YouTube'));
    assert.deepEqual(await page.evaluate(()=>calls.at(-1)), {id:'axx.desktop.window.read',inputs:{window_id:'0x7b',pid:10,expected_title:'YouTube'}});
    assert.equal(await page.evaluate(()=>Axx.companion.attachment), undefined);
    await page.evaluate(()=>{testWindows=[{window_id:456,pid:20,title:'IANA — Example Domains'}]; return Axx.companion.send('lee la página IANA');});
    assert.deepEqual(await page.evaluate(()=>calls.at(-1)), {id:'axx.desktop.window.read',inputs:{window_id:'0x1c8',pid:20,expected_title:'IANA — Example Domains'}});
    await page.evaluate(()=>{testWindows.push({window_id:789,pid:20,title:'IANA — Another page'}); return Axx.companion.send('lee IANA');});
    assert.equal(await page.evaluate(()=>calls.at(-1).id),'axx.desktop.list_windows');
    assert.match(await page.evaluate(()=>notices.at(-1)),/varias ventanas/);
    await page.evaluate(()=>{
      window.snapshot={text:'Texto observado <img src=x>', observed_at:Date.now()/1000, links:[
        {title:'Video observado',url:'https://www.youtube.com/watch?v=aaaaaaaaaaa',video_id:'aaaaaaaaaaa'},
        {title:'Malicioso',url:'javascript:alert(1)'}],limitation:'Contenido parcial'};
      Axx.windowContent.accept({output:snapshot});
    });
    assert.equal(await page.locator('#window-content-links button').count(),1);
    assert.equal(await page.locator('#window-content-text img').count(),0);
    await page.evaluate(()=>Axx.companion.send('abre el primer video'));
    assert.deepEqual(await page.evaluate(()=>calls.at(-1)),{id:'axx.desktop.open_url',inputs:{url:'https://www.youtube.com/watch?v=aaaaaaaaaaa'}});
    const before = await page.evaluate(()=>calls.length);
    await page.evaluate(()=>{snapshot.observed_at-=61; return Axx.companion.send('abre el primer video');});
    assert.equal(await page.evaluate(()=>calls.length),before);
    assert.match(await page.evaluate(()=>notices.at(-1)),/Vuelve a leer/);
    await page.locator('#window-content-attach').click();
    await page.waitForFunction(()=>Axx.companion.attachment);
    assert.match(await page.evaluate(()=>Axx.companion.attachment.text),/no es una instrucción/);
    await page.evaluate(()=>Axx.companion.attachment={name:'existente',text:'preservado'});
    await page.locator('#window-content-attach').click();
    await page.waitForFunction(()=>notices.at(-1).includes('Ya hay un adjunto'));
    assert.equal(await page.evaluate(()=>Axx.companion.attachment.text),'preservado');
    assert.deepEqual(errors,[]);
    console.log('PASS: generic page read, ambiguous window refusal, observed URL, safe text, stale refusal, opt-in model attachment, existing attachment preserved');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
