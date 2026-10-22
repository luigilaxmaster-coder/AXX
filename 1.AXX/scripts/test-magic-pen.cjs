const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.resolve(__dirname,'../../evidence/mp-h1-20261022');
 const server=http.createServer((req,res)=>{const f=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(root,'Axx.html');res.setHeader('Content-Type',f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(f));});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   localStorage.setItem('axx.flow.favorites',JSON.stringify(['dictation','music','screen','timer','chat']));
   window.calls=[];window.documentFixture=null;window.pendingQueries=[];
   window.__TAURI__={core:{invoke:async(name,args)=>{calls.push({name,args});const desktop={screenX:900,screenY:500,workWidth:1440,workHeight:1000,spaceLeft:900,spaceRight:540,spaceAbove:500,spaceBelow:500};
    if(name==='native_status')return {native:true,backendReady:false,desktop};if(name==='desktop_layout')return {...desktop,...args};
    if(name==='magic_pen_capture'){const canvas=document.createElement('canvas');canvas.width=800;canvas.height=500;const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,800,500);c.fillStyle='black';c.font='40px sans-serif';c.fillText('Axx MP-H1 · evidencia de prueba',30,100);documentFixture={id:'a'.repeat(32),revision:1,source:{width:800,height:500,captured_at:Date.now()/1000,sha256:'fixture'},selection:null,strokes:[],queries:[],preview:canvas.toDataURL()};return structuredClone(documentFixture);}
    if(name==='backend_request'){const op=args.path.split('/').pop();if(op==='status'&&args.path.includes('/pen/'))return {monitors:[{id:'screen',width:800,height:500}],capabilities:{vision:[],ocr_message:'OCR no integrado',export_directory:'C:/fixture'},history:[]};
     if(op==='save'){assertRevision(args.body);documentFixture={...documentFixture,selection:args.body.selection,strokes:args.body.strokes,revision:documentFixture.revision+1};return structuredClone(documentFixture);}
     if(op==='analyze')return new Promise(resolve=>pendingQueries.push(()=>resolve({id:'query',source_id:args.body.id,revision:args.body.revision,selection:structuredClone(documentFixture.selection),question:args.body.question,state:'failed',error:'Análisis visual no configurado'})));
     if(op==='export')return {path:'C:/fixture/result.png',sha256:'fixture-only',verified:true};
     if(op==='get')return structuredClone(documentFixture);
     if(args.path==='/axx-api/screen/status')return {state:'running',id:'external-recording',region:{x:0,y:0,width:200,height:200}};
     if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};return {};
    }return null;
   }},event:{listen:async()=>()=>{}}};
   function assertRevision(b){if(b.expected_revision!==documentFixture.revision)throw Error('stale fixture revision');}
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>Axx.magicPen&&Axx.resident?.firstFrame);
  await page.evaluate(()=>Axx.flow.showQuick());assert.equal(await page.locator('#flow-fan [data-quick="magicpen"]').count(),1);
  await page.locator('#flow-fan [data-quick="magicpen"]').click();await page.waitForFunction(()=>Axx.magicPen.active&&!Axx.magicPen.working);
  assert.equal(await page.locator('#view-magicpen').isVisible(),true);await page.evaluate(()=>{Axx.magicPen.open();Axx.magicPen.open();});assert.equal(await page.locator('#view-magicpen').count(),1);
  await page.click('#mp-capture');await page.waitForFunction(()=>Axx.magicPen.doc&&!Axx.magicPen.working);
  const stroke=async(tool,points)=>{await page.locator(`[data-mp-mode="${['pen','marker','erase'].includes(tool)?'ink':tool==='pointer'?'pointer':'select'}"]`).click();if(tool!=='pointer')await page.locator(`[data-mp-tool="${tool}"]`).click();const r=await page.locator('#mp-canvas').boundingBox();await page.mouse.move(r.x+points[0][0]*r.width,r.y+points[0][1]*r.height);await page.mouse.down();for(const p of points.slice(1))await page.mouse.move(r.x+p[0]*r.width,r.y+p[1]*r.height,{steps:5});await page.mouse.up();await page.evaluate(()=>Axx.magicPen.flush());};
  await stroke('rect',[[.1,.1],[.6,.5]]);let b=await page.evaluate(()=>Axx.magicPen.doc.selection.bounds);assert.ok(Math.abs(b[0]-80)<2&&Math.abs(b[2]-480)<2);
  await page.selectOption('#mp-zoom','2');assert.deepEqual(await page.evaluate(()=>Axx.magicPen.doc.selection.bounds),b);await page.selectOption('#mp-zoom','1');
  await stroke('point',[[.4,.4]]);assert.equal(await page.evaluate(()=>Axx.magicPen.doc.selection.shape),'point');
  await stroke('lasso',[[.1,.1],[.5,.1],[.5,.5],[.1,.5]]);assert.equal(await page.locator('#mp-close-lasso').isVisible(),true);await page.click('#mp-close-lasso');await page.evaluate(()=>Axx.magicPen.flush());assert.equal(await page.evaluate(()=>Axx.magicPen.doc.selection.shape),'lasso');
  await stroke('pen',[[.2,.2],[.4,.4]]);assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),1);await page.click('#mp-undo');assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),0);await page.click('#mp-redo');assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),1);
  await page.click('#mp-ask');await page.waitForFunction(()=>pendingQueries.length===1);await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>Axx.magicPen.active),false);await page.evaluate(()=>pendingQueries.shift()());await page.waitForTimeout(300);assert.equal(await page.locator('#panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>calls.some(c=>c.args?.path==='/axx-api/screen/control'||c.args?.path==='/axx-api/actions/cancel')),false,'Escape in Pen must not stop another recording');
  await page.evaluate(()=>Axx.magicPen.open());await page.waitForFunction(()=>!Axx.magicPen.working);await page.screenshot({path:path.join(out,'browser-contract-panel.png')});
  const invalid=await page.evaluate(()=>{try{Axx.magicPenGeometry.sourcePoint(1,1,{left:0,top:0,width:0,height:100},800,500);return false;}catch{return true;}});assert.ok(invalid);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-contract.json'),JSON.stringify({kind:'BROWSER_POINTER_WITH_SIMULATED_NATIVE_BOUNDARY',passed:['single radial entry preserving saved tools','same panel instance','rect/point/lasso','zoom invariant','editable undo/redo','late response after close','Escape keeps recording','singular transform rejected'],errors},null,2));console.log('PASS Magic Pen browser contract');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
