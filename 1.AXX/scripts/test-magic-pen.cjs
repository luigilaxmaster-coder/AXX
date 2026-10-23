/** Real DOM/pointers; native capture and external inference are simulated. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),out=path.resolve(__dirname,'../../build/magic-pen-desktop');fs.mkdirSync(out,{recursive:true});
 const server=http.createServer((req,res)=>{const f=req.url.startsWith('/scripts/')?path.join(__dirname,path.basename(req.url)):path.join(root,'Axx.html');res.setHeader('Content-Type',f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(f));});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.setDefaultTimeout(6000);page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.calls=[];window.docs={};window.pendingQueries=[];window.captureFails=false;window.delayAnalysis=false;window.captureCount=0;window.holdCapture=false;window.releaseCapture=null;
   window.__TAURI__={core:{invoke:async(name,args)=>{calls.push({name,args});const desktop={screenX:900,screenY:500,anchorX:900,anchorY:460,scaleFactor:1,workWidth:1440,workHeight:1000,spaceLeft:900,spaceRight:540,spaceAbove:460,spaceBelow:540};
    if(name==='native_status')return {native:true,backendReady:false,desktop};if(name==='desktop_layout')return {...desktop,...args};
    if(name==='magic_pen_capture'){
     if(captureFails)throw Error('CAPTURE_UNAVAILABLE');if(holdCapture)await new Promise(r=>releaseCapture=r);
     const canvas=document.createElement('canvas');canvas.width=1440;canvas.height=1080;
     const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,1440,1080);
     const d={id:(++captureCount).toString(16).padStart(32,'0'),revision:1,source:{x:0,y:0,width:1440,height:1080,captured_at:Date.now()/1000,sha256:'fixture'},viewport:{x:0,y:40,scale:1},selection:null,strokes:[],queries:[],preview:canvas.toDataURL()};docs[d.id]=d;return structuredClone(d);
    }
    if(name==='backend_request'){const op=args.path.split('/').pop(),b=args.body;
     if(op==='status'&&args.path.includes('/pen/'))return {monitors:[{id:'0,0,1440,1080',x:0,y:0,width:1440,height:1080}],capabilities:{vision:[{name:'fixture'}],ocr_message:'OCR no integrado',export_directory:'C:/fixture'},history:[]};
     if(op==='save'){const d=docs[b.id];if(b.expected_revision!==d.revision)throw Error('stale fixture revision');Object.assign(d,{selection:b.selection,strokes:b.strokes,revision:d.revision+1});return structuredClone(d);}
     if(op==='analyze'){const d=docs[b.id];if(b.revision!==d.revision||!d.selection)throw Error('unsaved selection');const q={id:'query',source_id:b.id,revision:b.revision,selection:structuredClone(d.selection),question:b.question,state:'completed',response:'Respuesta de prueba sobre la región seleccionada.'};if(delayAnalysis)return new Promise(resolve=>pendingQueries.push(()=>resolve(q)));return q;}
     if(op==='export')return {path:'C:/fixture/result.png',sha256:'fixture-only',verified:true};
     if(op==='get')return structuredClone(docs[b.id]);
     if(args.path==='/axx-api/connect/ui/claim')return {tasks:[]};return {};
    }return null;
   }},event:{listen:async()=>()=>{}}};
  });
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>Axx.magicPen&&Axx.resident?.firstFrame);
  await page.evaluate(()=>Axx.flow.showQuick());assert.equal(await page.locator('#flow-fan [data-quick="magicpen"]').count(),1);
  await page.locator('#flow-fan [data-quick="magicpen"]').click();await page.waitForFunction(()=>Axx.magicPen.active&&!Axx.magicPen.working);
  assert.equal(await page.locator('#panel').isVisible(),false,'Magic Pen must open on the desktop without the tool panel');
  assert.equal(await page.locator('#mp-desktop').isVisible(),true);
  await page.evaluate(()=>{Axx.magicPen.open();Axx.magicPen.open();});assert.equal(await page.locator('#mp-desktop').count(),1);
  const stroke=async(tool,points)=>{
   await page.locator('[data-mp-tool="'+tool+'"]').click();
   await page.mouse.move(...points[0]);await page.mouse.down();for(const p of points.slice(1))await page.mouse.move(...p,{steps:5});await page.mouse.up();
   await page.waitForFunction(()=>!Axx.magicPen.working);await page.evaluate(()=>Axx.magicPen.flush());
  };
  await page.evaluate(()=>holdCapture=true);await page.mouse.move(100,150);await page.mouse.down();await page.mouse.move(450,350,{steps:5});await page.mouse.up();
  await page.waitForFunction(()=>typeof releaseCapture==='function');
  assert.equal(Math.round((await page.locator('#mp-widget').boundingBox()).x),466,'widget must be anchored before the capture returns');
  await page.evaluate(()=>{holdCapture=false;releaseCapture();});await page.waitForFunction(()=>!Axx.magicPen.working);
  await page.waitForFunction(()=>Axx.magicPen.doc.queries.length===1);
  assert.deepEqual(await page.evaluate(()=>Axx.magicPen.doc.selection.bounds.map(Math.round)),[100,190,450,390]);
  assert.ok(await page.evaluate(()=>captureCount>=2),'selection must capture the current desktop');
  assert.match(await page.locator('#mp-answers').innerText(),/Respuesta de prueba/);
  assert.equal(await page.locator('#mp-canvas').evaluate(c=>getComputedStyle(c).pointerEvents),'none');
  assert.equal(await page.evaluate(()=>Axx.resident.interactiveRegions().some(r=>r.x<=1000&&r.y<=800&&r.x+r.width>1000&&r.y+r.height>800)),false,'desktop outside the widget must pass clicks through');
  assert.equal(await page.evaluate(()=>Axx.magicPen.ctx.getImageData(1000,800,1,1).data[3]),0,'no frozen desktop backdrop');
  const widget=await page.locator('#mp-widget').boundingBox();assert.ok(widget.x>=0&&widget.y>=0&&widget.x+widget.width<=1440&&widget.y+widget.height<=1000);
  await page.click('#mp-all');await page.waitForFunction(()=>!Axx.magicPen.working);
  assert.deepEqual(await page.evaluate(()=>Axx.magicPen.doc.selection.bounds),[0,0,1440,1080]);
  await stroke('point',[[600,250]]);assert.equal(await page.evaluate(()=>Axx.magicPen.doc.selection.shape),'point');
  const a=await page.locator('#avatar').boundingBox(),w=await page.locator('#mp-widget').boundingBox();
  assert.ok(w.x+w.width<=a.x||w.x>=a.x+a.width||w.y+w.height<=a.y||w.y>=a.y+a.height,'widget must leave the avatar clear when there is space');
  await stroke('lasso',[[100,150],[450,150],[450,350],[100,350]]);assert.equal(await page.evaluate(()=>Axx.magicPen.doc.selection.shape),'lasso');
  await page.locator('[data-mp-tool="marker"]').click();await page.mouse.move(200,200);await page.mouse.down();
  const paints=await page.evaluate(async()=>{
   const mp=Axx.magicPen,render=mp.render;let count=0;mp.render=function(){count++;return render.call(this);};
   for(let i=0;i<100;i++)mp.canvas.dispatchEvent(new PointerEvent('pointermove',{clientX:200+i,clientY:200+i/2,pointerId:mp.gesture.id,bubbles:true}));
   await new Promise(requestAnimationFrame);mp.render=render;return count;
  });
  assert.ok(paints<=2,'pointer bursts must paint once per frame');await page.mouse.up();await page.evaluate(()=>Axx.magicPen.flush());assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),1);
  assert.equal(await page.locator('#mp-answers').innerText(),'','a new marked region must not display the previous explanation');
  await page.click('#mp-undo');assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),0);await page.click('#mp-redo');assert.equal(await page.evaluate(()=>Axx.magicPen.doc.strokes.length),1);
  await page.locator('#mp-widget details.mp-save-section > summary').click();await page.click('#mp-annotated');await page.waitForFunction(()=>!Axx.magicPen.working);assert.match(await page.locator('#mp-export').innerText(),/verificado/);
  await page.evaluate(()=>{delayAnalysis=true;});await page.click('#mp-ask');await page.waitForFunction(()=>pendingQueries.length===1);
  await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>Axx.magicPen.active),false);await page.evaluate(()=>pendingQueries.shift()());await page.waitForTimeout(200);assert.equal(await page.locator('#mp-desktop').isVisible(),false);
  await page.evaluate(()=>Axx.magicPen.open());await page.waitForFunction(()=>!Axx.magicPen.working);
  assert.equal(await page.locator('#panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>calls.some(c=>c.args?.path==='/axx-api/screen/control'||c.args?.path==='/axx-api/actions/cancel')),false);
  await page.evaluate(()=>{delayAnalysis=false;Axx.magicPen.open();});await page.waitForFunction(()=>!Axx.magicPen.working);
  await page.evaluate(()=>{captureFails=true;});await stroke('rect',[[100,150],[450,350]]);assert.match(await page.locator('#mp-status').innerText(),/CAPTURE_UNAVAILABLE/);
  assert.equal(await page.evaluate(()=>Axx.magicPen.doc?.selection??null),null,'failed capture must not analyze an older selection');
  assert.deepEqual(await page.evaluate(()=>Axx.magicPenGeometry.desktopPoint(100,150,{x:-1920,y:40,scale:1.5},{x:-2000,y:0,width:3000,height:2000})),[230,265]);
  await page.evaluate(()=>{captureFails=false;});await stroke('rect',[[100,150],[450,350]]);await page.waitForFunction(()=>Axx.magicPen.doc.queries.length===1);
  await page.locator('#mp-widget details.mp-save-section > summary').click();await page.screenshot({path:path.join(out,'desktop-contract.png')});
  await page.setViewportSize({width:1280,height:900});await page.waitForTimeout(150);
  await page.locator('[data-mp-tool="rect"]').click();await page.waitForFunction(()=>!!Axx.magicPen.doc&&!Axx.magicPen.working);
  assert.equal(await page.evaluate(()=>Axx.magicPen.inputEnabled),true,'selection must recover after a display resize');
  await page.evaluate(()=>Axx.companion.openFeature('chat'));assert.equal(await page.locator('#mp-desktop').isVisible(),false);assert.equal(await page.locator('#panel').isVisible(),true);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-contract.json'),JSON.stringify({kind:'BROWSER_POINTER_WITH_SIMULATED_NATIVE_BOUNDARY',paintsFor100PointerEvents:paints,passed:['single radial entry','desktop without panel or backdrop','fresh physical-coordinate selection','widget anchored while capture is pending','avatar remains clear','new marks clear previous explanations','display resize recovery','point/rect/lasso','editable marker undo/redo','answer widget and click-through','export','late response after Escape','capture failure cannot reuse old selection'],errors},null,2));console.log('PASS Magic Pen desktop contract');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
