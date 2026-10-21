const fs=require('node:fs'), path=require('node:path'), http=require('node:http'), assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
  const server=http.createServer((req,res)=>{
    const file=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(__dirname,'../Axx.html');
    res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':'text/html');res.end(fs.readFileSync(file));
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
  try{
    const page=await browser.newPage({viewport:{width:1200,height:1000}}), errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      window.testProviders=[];window.savedCalls=[];
      window.__TAURI__={core:{invoke:async(name,args)=>{
        const desktop={workWidth:1920,workHeight:1080,spaceLeft:1000,spaceRight:920,spaceAbove:540,spaceBelow:540};
        if(name==='native_status')return {native:true,backendReady:false,shortcut:'Alt+Shift+A',desktop};
        if(name==='desktop_layout')return {...desktop,...args};
        if(name==='backend_request'){
          if(args.path==='/axx-api/providers')return {providers:window.testProviders};
          if(args.path==='/axx-api/providers/discover')return {models:window.testModels || ['fixture-model','second-model']};
          if(args.path==='/axx-api/providers/save'){
            window.savedCalls.push(args.body);
            window.testProviders=[{...args.body,kind:args.body.provider,has_key:!!args.body.api_key}];
            return {ok:true};
          }
          if(args.path==='/axx-api/status')return {provider:'fixture',details:{providers:window.testProviders.map(p=>({...p,state:p.enabled?'ready_locally':'disabled'}))}};
          if(args.path==='/axx-api/models')return {models:window.testProviders.map(p=>p.model)};
        } return null;
      }},event:{listen:async()=>()=>{}}};
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>window.Axx?.resident?.firstFrame);
    await page.evaluate(()=>Axx.flow.select('ai'));
    await page.locator('#tab-mode-api').click();
    await page.locator('#provider-kind').selectOption('groq');
    assert.equal(await page.locator('#provider-url').inputValue(),'https://api.groq.com/openai/v1');
    await page.locator('#provider-name').fill('My Groq');
    await page.locator('#provider-key').fill('FIXTURE-ONLY-KEY');
    await page.locator('#provider-discover').click();
    await page.waitForFunction(()=>document.getElementById('provider-model').value==='fixture-model');
    assert.equal(await page.locator('#provider-key').inputValue(),'FIXTURE-ONLY-KEY');
    assert.equal(await page.locator('#provider-model').evaluate(el=>el.tagName),'SELECT');
    await page.locator('#provider-model').selectOption('second-model');
    await page.locator('#provider-model').selectOption('fixture-model');
    await page.locator('#provider-billing').check();
    await page.locator('#provider-save').click();
    await page.waitForFunction(()=>document.getElementById('provider-status').textContent.includes('modelo seleccionado'));
    assert.equal(await page.locator('#provider-key').inputValue(),'');
    assert.equal(await page.evaluate(()=>Axx.companion.data.prefs.model),'fixture-model');
    assert.equal(await page.evaluate(()=>Axx.companion.data.prefs.apiConnection),'My Groq');
    assert.equal(await page.evaluate(()=>JSON.stringify({...localStorage}).includes('FIXTURE-ONLY-KEY')),false);
    await page.locator('#provider-saved').selectOption('My Groq');
    assert.equal(await page.locator('#provider-model').inputValue(),'fixture-model');
    await page.locator('#provider-enabled').uncheck();
    await page.locator('#provider-save').click();
    await page.waitForFunction(()=>document.getElementById('provider-status').textContent.includes('Revisa'));
    assert.equal(await page.evaluate(()=>Axx.companion.brain.connected),false);
    await page.locator('#provider-kind').selectOption('anthropic');
    assert.equal(await page.locator('#provider-url').inputValue(),'https://api.anthropic.com/v1');
    assert.equal(await page.locator('#provider-billing').isChecked(),false);
    await page.locator('#provider-kind').selectOption('custom');
    assert.equal(await page.locator('#provider-protocol-row').isVisible(),true);
    await page.locator('#provider-kind').selectOption('ollama_cloud');
    assert.equal(await page.locator('#provider-url').inputValue(),'https://ollama.com/v1');
    await page.locator('#provider-discover').click();
    await page.locator('#provider-model').selectOption('second-model');
    await page.evaluate(()=>window.testModels=[]);
    await page.locator('#tab-mode-local').click();
    await page.locator('#ai-test').click();
    await page.waitForFunction(()=>document.getElementById('provider-catalog-status').textContent.includes('no tiene modelos instalados'));
    assert.equal(await page.locator('#provider-model').inputValue(),'');
    assert.deepEqual(errors,[]);
    fs.mkdirSync('evidence/providers-20261021',{recursive:true});
    await page.locator('#provider-kind').selectOption('ollama');
    await page.locator('#provider-name').fill('Ollama en mi equipo');
    await page.locator('#provider-model').selectOption('__manual__');
    await page.locator('#provider-model-manual').fill('qwen3:4b');
    await page.screenshot({path:'evidence/providers-20261021/settings.png'});
    console.log('PASS: provider presets, discovery, save, key clearing, no browser persistence, edit/disable, exact model and custom protocol');
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
