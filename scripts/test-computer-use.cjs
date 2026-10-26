// UI authorization, provider routing, visible status and revocation on chat change.
const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe')});
  try{
    const p=await browser.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
    await p.setContent('<section id="chat-workspace"></section>');
    await p.evaluate(()=>{
      Object.defineProperty(crypto,'randomUUID',{value:()=>String(Math.random())});window.calls=[];window.stopped=0;let grant={active:false};
      window.Axx={isNative:()=>true,chatWorkspace:{active:{id:'chat-one'}},companion:{data:{prefs:{provider:'chatgpt'}}},resident:{schedule(){}},
        backendRequest:async(method,route,body)=>{
          calls.push({method,route,body});
          if(route.endsWith('/prepare'))return{operation_id:'windows'};
          if(route.endsWith('/execute'))return{state:'succeeded',output:{windows:[{window_id:10,pid:20,title:'Fixture'}]}};
          if(route.endsWith('/begin')){
            if(!body.image_authorized||!body.allow_input)return{error:{message:'Autorice imágenes y entrada'}};
            grant={active:true,title:'Fixture',actions:0};return grant;
          }
          if(route.includes('/status?'))return grant;
          if(route.endsWith('/stop')){stopped++;grant={active:false};return grant;}
          throw Error('Unexpected route '+route);
        }};
    });
    await p.addScriptTag({path:'1.AXX/scripts/computer-use.js'});
    await p.click('#cu-open');await p.click('#cu-start');await p.waitForFunction(()=>!document.getElementById('cu-error').hidden);
    assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-one')),false);
    await p.check('#cu-images');await p.check('#cu-input');await p.click('#cu-start');
    await p.waitForFunction(()=>Axx.computerUse.activeFor('chat-one'));assert.match(await p.locator('#cu-live').innerText(),/Activo.*Fixture/);
    assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-two')),false);
    await p.evaluate(()=>Axx.chatWorkspace.active={id:'chat-two'});
    await p.waitForFunction(()=>stopped===1);assert.equal(await p.evaluate(()=>Axx.computerUse.activeFor('chat-one')),false);
    await p.click('#cu-open');await p.check('#cu-images');await p.check('#cu-input');await p.click('#cu-start');
    await p.waitForFunction(()=>Axx.computerUse.activeFor('chat-two'));await p.keyboard.press('Escape');
    await p.waitForFunction(()=>stopped===2);assert.equal(await p.locator('#cu-stop').isHidden(),true);assert.deepEqual(errors,[]);
    console.log('COMPUTER_USE_UI_CONSENT_SCOPE_STOP_PASS');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
