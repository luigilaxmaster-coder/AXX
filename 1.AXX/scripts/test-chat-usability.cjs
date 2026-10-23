const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { chromium } = createRequire(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async () => {
  const server = http.createServer((req, res) => {
    const file = req.url.startsWith('/scripts/') ? path.join(__dirname, path.basename(req.url)) : path.join(__dirname, '../Axx.html');
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : 'text/html'); res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, executablePath: process.env.AXX_TEST_CHROMIUM });
  const passed = [], failed = [], errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    page.setDefaultTimeout(4000);
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', e => { if(e.type()==='error') errors.push(e.text()); });
    await page.addInitScript(() => {
      window.__TAURI__ = { core: { invoke: async (name, args) => {
        const desktop = { workWidth: 1920, workHeight: 1040, spaceLeft: 1200, spaceRight: 720, spaceAbove: 550, spaceBelow: 490 };
        if (name === 'native_status') return { native: true, backendReady: false, shortcut: 'Alt+Shift+A', desktop };
        if (name === 'desktop_layout') return { ...desktop, ...args };
        return null;
      } }, event: { listen: async () => () => {} } };
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => window.Axx?.resident?.firstFrame).catch(error => { throw new Error(error.message + '\n' + errors.join('\n')); });
    await page.evaluate(() => { Axx.flow.select('chat'); for(let i=0;i<20;i++) Axx.companion.message(i%2?'assistant':'user', 'Mensaje '+i+'\n'+('Contenido de lectura. '.repeat(12)), 'local'); Axx.companion.renderChat(); });
    await page.waitForTimeout(400);
    const check = async (name, fn) => { try { await fn(); passed.push(name); } catch(e) { failed.push({name,error:e.message}); } };
    await check('Chat gives reading space and keeps the complete composer inside its panel', async () => {
      const bounds = await page.evaluate(() => {
        const p=document.getElementById('panel').getBoundingClientRect(), l=document.getElementById('chat-log').getBoundingClientRect(), f=document.getElementById('chat-form').getBoundingClientRect();
        return {width:p.width, reading:l.height, bottom:f.bottom, panelBottom:p.bottom};
      });
      assert.ok(bounds.width>=480 && bounds.reading>=300 && bounds.bottom<=bounds.panelBottom, JSON.stringify(bounds));
    });
    await check('Appending a reply preserves the reading position and selected text', async () => {
      const result=await page.evaluate(() => {
        const c=Axx.companion,l=document.getElementById('chat-log'); c.setChatScroll20(false); l.scrollTop=250;
        const text=l.children[2].querySelector('.message-body').firstChild;
        const range=document.createRange(); range.setStart(text,0); range.setEnd(text,8); getSelection().removeAllRanges(); getSelection().addRange(range);
        const before={top:l.scrollTop,selection:getSelection().toString()};
        c.message('assistant','Una nueva respuesta que no debe mover mi lectura.','local'); c.renderChat();
        return {before,after:{top:l.scrollTop,selection:getSelection().toString()}};
      });
      assert.ok(Math.abs(result.before.top-result.after.top)<2, JSON.stringify(result));
      assert.equal(result.after.selection,result.before.selection);
      await page.locator('#chat-jump-latest').click();
      assert.ok(await page.evaluate(()=> {const l=document.getElementById('chat-log'); return l.scrollHeight-l.clientHeight-l.scrollTop<3;}));
    });
    await check('Enter sends once and shrinks the composer; Shift+Enter keeps a newline; send retains focus', async () => {
      await page.evaluate(()=> {window.originalSend=Axx.companion.send; window.submitted=[]; Axx.companion.send=async text=>window.submitted.push(text);});
      const field=page.locator('#chat-input');
      await field.fill('Uno\nDos\nTres\nCuatro\nCinco\nSeis');
      await field.press('Enter');
      assert.equal(await field.inputValue(),'');
      assert.ok(await field.evaluate(el=>el.getBoundingClientRect().height<=70));
      await field.fill('Borrador'); await field.press('Shift+Enter'); await field.press('x');
      assert.equal(await field.inputValue(),'Borrador\nx');
      await page.locator('#chat-send').click();
      assert.ok(await field.evaluate(el=>el===document.activeElement));
      assert.equal(await page.evaluate(()=>window.submitted.length),2);
      await page.evaluate(()=>Axx.companion.send=window.originalSend);
    });
    await check('Completed replies render readable headings, lists and code without interpreting HTML', async () => {
      await page.evaluate(()=> { Axx.companion.message('assistant','## Ejemplo\n\n**Importante** y `código`.\n\n- Primero\n- Segundo\n\n```html\n<img src=x onerror="window.injected=true">\n```','model'); Axx.companion.renderChat(); });
      const row=page.locator('#chat-log .chat-message').last();
      assert.equal(await row.locator('h3').textContent(),'Ejemplo');
      assert.equal(await row.locator('li').count(),2);
      assert.ok((await row.locator('pre code').textContent()).includes('<img'));
      assert.equal(await row.locator('img').count(),0);
      assert.equal(await page.evaluate(()=>window.injected),undefined);
    });
    await check('Speech omits markup and punctuation while personality settings persist', async () => {
      const result=await page.evaluate(() => {
        document.getElementById('chat-personality-style').value='friendly';
        document.getElementById('chat-personality-style').dispatchEvent(new Event('change'));
        const notes=document.getElementById('chat-personality-notes');notes.value='Háblame de tú';notes.dispatchEvent(new Event('change'));
        return {spoken:Axx.speechReplyText('Hola, **mundo**. [Mira](https://example.com), ¡gracias!'),
                saved:Axx.decodeCompanion(localStorage.getItem('axx.companion.v4')).prefs};
      });
      assert.equal(result.spoken,'Hola mundo Mira ¡gracias');
      assert.equal(result.saved.personalityStyle,'friendly');
      assert.equal(result.saved.personalityNotes,'Háblame de tú');
    });
    await check('Local realtime chat delivers incremental text without exposing backend credentials', async () => {
      const result=await page.evaluate(async () => {
        const brain=new Axx.BrainClient(), deltas=[];
        const invoke=Axx.nativeInvoke, listen=window.__TAURI__.event.listen;
        let receiver, removed=false;
        window.__TAURI__.event.listen=async (_event, callback)=>{receiver=callback;return ()=>{removed=true;};};
        Axx.nativeInvoke=async (name,args)=>{
          if(name!=='ollama_realtime_chat') throw new Error('Unexpected command');
          receiver({payload:{request_id:args.requestId,delta:'Hola'}});
          receiver({payload:{request_id:args.requestId,delta:', señor.'}});
          return {text:'Hola, señor.',reason:'stop',route:{streamed_local:true,model:args.model}};
        };
        try {
          const final=await brain.localRealtimeChat('qwen2.5:3b',[{role:'user',content:'Hola'}],new AbortController().signal,t=>deltas.push(t));
          return {deltas,final,removed};
        } finally {Axx.nativeInvoke=invoke;window.__TAURI__.event.listen=listen;}
      });
      assert.deepEqual(result.deltas,['Hola','Hola, señor.']);
      assert.equal(result.final.route.streamed_local,true);
      assert.equal(result.removed,true);
    });
    await check('Closing and reopening the chat preserves the unsent draft', async () => {
      await page.locator('#chat-input').fill('Mi borrador pendiente');
      await page.locator('#chat20-close').click();
      await page.evaluate(()=>Axx.flow.select('chat'));
      assert.equal(await page.locator('#chat-input').inputValue(),'Mi borrador pendiente');
    });
    await check('A pending reply preserves the next draft and never pulls a reader to the bottom', async () => {
      await page.evaluate(() => {
        const c=Axx.companion; window.pendingRow=c.message('assistant','','model','pending'); c.renderChat();
        c.pending=new AbortController(); c.setBusy(true); c.setChatScroll20(false);
        document.getElementById('chat-log').scrollTop=150;
      });
      await page.locator('#chat-input').fill('Mi siguiente pregunta');
      await page.locator('#chat-input').press('Enter');
      assert.equal(await page.locator('#chat-input').inputValue(),'Mi siguiente pregunta');
      const result=await page.evaluate(() => {
        const c=Axx.companion,l=document.getElementById('chat-log'),before=l.scrollTop;
        pendingRow.text='Respuesta parcial. '.repeat(100);
        l.lastElementChild.querySelector('.message-body').textContent=pendingRow.text; c.scrollChat();
        pendingRow.status='complete'; c.pending=null; c.setBusy(false); c.renderChat();
        return {before,after:l.scrollTop};
      });
      assert.ok(Math.abs(result.before-result.after)<2,JSON.stringify(result));
      assert.equal(await page.locator('#chat-input').inputValue(),'Mi siguiente pregunta');
      await page.locator('#chat-jump-latest').click();
    });
    await check('A narrow chat keeps multiline input and controls inside the panel', async () => {
      await page.evaluate(async () => { Axx.resident.panelPositions.panel={width:340,height:450}; await Axx.resident.layout(); });
      await page.locator('#chat-input').fill('Uno\nDos\nTres\nCuatro\nCinco\nSeis\nSiete\nOcho');
      const bounds=await page.evaluate(() => {
        const p=document.getElementById('panel').getBoundingClientRect();
        return ['chat-input','chat-send','chat20-close','chat-log'].map(id=> {
          const r=document.getElementById(id).getBoundingClientRect();
          return {id,inside:r.left>=p.left&&r.right<=p.right&&r.top>=p.top&&r.bottom<=p.bottom,height:r.height};
        });
      });
      assert.ok(bounds.every(x=>x.inside&&x.height>0),JSON.stringify(bounds));
      await page.evaluate(async () => {delete Axx.resident.panelPositions.panel; await Axx.resident.layout();});
      await page.locator('#chat-input').fill('Mi borrador pendiente');
    });
    if(process.env.AXX_TEST_EVIDENCE) {fs.mkdirSync(process.env.AXX_TEST_EVIDENCE,{recursive:true});await page.screenshot({path:path.join(process.env.AXX_TEST_EVIDENCE,'chat.png'),omitBackground:true});}
    console.log(JSON.stringify({kind:'CHAT_USABILITY_BROWSER',passed,failed,errors},null,2));
    if(failed.length||errors.length) process.exitCode=1;
  } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
