/** QR presentation must survive polling and must not wait for conversation sync. */
const assert=require('node:assert/strict'),path=require('node:path');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AXX_TEST_CHROMIUM});
 try{
  const page=await browser.newPage();
  await page.setContent('<section id="view-settings"></section><div id="context-menu"><hr></div>');
  await page.evaluate(()=>{
   window.intervals=[];window.setInterval=(fn,ms)=>{intervals.push({fn,ms});return intervals.length;};window.clearInterval=()=>{};
   window.failStart=true;window.messages=0;
   window.Axx={isNative:()=>true,companion:{data:{sharedConversationId:'test',prefs:{keepHistory:true},messages:[]},save(){},renderChat(){}},
    normalizeSettings:x=>x,app:{store:{data:{settings:{}}},renderer:{getStudio:()=>({}),getCamera20:()=>({}),moving:()=>false}},
    backendRequest:async(method,path)=>{
     if(path.endsWith('/start')){
      if(failStart)throw Error('QR renderer unavailable');
      return{enabled:true,devices:[],endpoint:'https://127.0.0.1:1',pairing_uri:'test-only',qr_svg_base64:btoa('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="white"/></svg>'),expires_in:120};
     }
     if(path.endsWith('/messages')){messages++;return new Promise(()=>{});}
     return{enabled:true,devices:[],endpoint:'https://127.0.0.1:1'};
    }};
  });
  await page.addScriptTag({path:path.join(__dirname,'mobile-gateway.js')});
  await page.click('#axx-mobile-start');
  await page.waitForFunction(()=>!document.getElementById('axx-mobile-error').hidden);
  await page.evaluate(()=>intervals.find(x=>x.ms===5000).fn());
  assert.match(await page.textContent('#axx-mobile-error'),/QR renderer unavailable/);
  assert(await page.locator('#axx-mobile-error').isVisible());
  await page.evaluate(()=>window.failStart=false);
  await page.click('#axx-mobile-start');
  await page.waitForFunction(()=>document.getElementById('axx-mobile-qr').naturalWidth>0);
  assert(await page.locator('#axx-mobile-pair').isVisible());
  assert(!(await page.locator('#axx-mobile-error').isVisible()));
  assert(await page.evaluate(()=>messages>0),'history sync was attempted but remains unresolved');
  await page.evaluate(()=>{Date.now=()=>Number.MAX_SAFE_INTEGER;intervals.find(x=>x.ms===1000&&x.fn.toString().includes('seconds')).fn();});
  assert(!(await page.locator('#axx-mobile-pair').isVisible()));
  assert.match(await page.textContent('#axx-mobile-error'),/caducó/);
  console.log('PASS: QR errors persist across polling, successful QR appears without waiting for history, expiry hides stale QR');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
