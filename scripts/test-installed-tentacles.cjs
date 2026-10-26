// Production installed renderer, pointer-driven panel distances, actual body silhouettes.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 const out=process.argv[2]||'build/chat-0.21.4/tentacles';fs.mkdirSync(out,{recursive:true});const receipt={kind:'INSTALLED_TENDRILS',checks:[],surfaces:[]};
 const saved=await p.evaluate(()=>({theme:Axx.interfaceTheme.value,positions:localStorage.getItem('axx.resident.panel-pos'),form:Axx.app.renderer.form,view:Axx.companion.dock.selected}));
 try{
  await p.evaluate(()=>{Axx.resident.summon(false);Axx.flow.showQuick();});await p.waitForTimeout(600);
  for(const theme of ['light','dark']){
   await p.evaluate(t=>Axx.interfaceTheme.apply(t),theme);
   for(const form of [0,11,17]){
    await p.evaluate(id=>Axx.app.renderer.setForm(id,true),form);await p.waitForTimeout(500);
    await p.locator('#flow-fan [data-quick]').nth(1).hover();await p.waitForTimeout(1000);
    const state=await p.evaluate(()=>({render:Axx.app.renderer.diagnostics(),link:Axx.flow.delivery.snapshot(),filter:getComputedStyle(Axx.app.renderer.canvas).filter,forms:Axx.FORMS.length,palettes:Axx.PALETTES?.length}));
    assert.equal(state.filter,'none');assert(state.link.links===1);assert(state.render.failures===0);assert.equal(state.forms,24);
    const stage=await p.locator('#stage').boundingBox();await p.screenshot({path:`${out}/${theme}-form-${form}.png`,clip:{x:Math.max(0,stage.x-100),y:Math.max(0,stage.y-100),width:Math.min(stage.width+360,1920-Math.max(0,stage.x-100)),height:Math.min(stage.height+230,1032-Math.max(0,stage.y-100))}});
    receipt.surfaces.push({theme,form,...state});
   }
  }
  receipt.checks.push('Installed orbit hover attaches on three actual silhouettes in both themes; identity retained');
  await p.evaluate(()=>{Axx.app.renderer.setForm(11,true);Axx.companion.openFeature('settings');Axx.resident.panelPositions['panel:settings']={width:420,height:500};Axx.resident.schedule();});await p.waitForTimeout(800);
  const geometry=await p.evaluate(()=>{const s=document.getElementById('stage').getBoundingClientRect();return {center:s.x+s.width/2,width:innerWidth,height:innerHeight,stageWidth:s.width};});
  const side=geometry.center>geometry.width/2?'left':'right',nearGap=Math.max(120,geometry.stageWidth/2+30);
  const farX=side==='left'?24:geometry.width-420-24;
  const nearX=side==='left'?geometry.center-420-nearGap:geometry.center+nearGap;
  const distance=panel=>side==='left'?geometry.center-(panel.x+panel.width):panel.x-geometry.center;
  receipt.geometry={...geometry,side,nearGap};
  for(const [name,x] of [['far',farX],['near',nearX]]){
   const header=await p.locator('#panel .panel-head').boundingBox();assert(header);const panel=await p.locator('#panel').boundingBox();
   await p.mouse.move(header.x+header.width*.42,header.y+20);await p.mouse.down();await p.mouse.move(x+header.width*.42,header.y+20,{steps:24});await p.mouse.up();await p.waitForTimeout(1000);
   const state=await p.evaluate(()=>({panel:document.getElementById('panel').getBoundingClientRect().toJSON(),link:Axx.organic.tendrils.snapshot(),buffers:[...Axx.organic.tendrils.buffers.values()].map(v=>({w:v.raster.width,h:v.raster.height}))}));
   assert(Math.abs(state.panel.x-panel.x)>50,'Pointer drag must actually move the panel');assert(distance(state.panel)>0,'Observed panel must not cover the avatar');assert(state.link.links>=1);for(const r of state.buffers)assert(r.w*r.h<4000000);
   await p.screenshot({path:`${out}/${name}-panel.png`});receipt.surfaces.push({distance:name,...state});
  }
  receipt.checks.push('Pointer drag exercises long and short installed panel links within raster budget');
  for(const [name,x] of [['long-detail',farX],['close-detail',nearX]]){
   await p.evaluate(x=>{
    const r=Axx.resident,g=r.geometry,stage=document.getElementById('stage').getBoundingClientRect();
    const center=stage.x+stage.width/2,relX=x-center;
    r.panelPositions['panel:settings']={width:420,height:500,relX,relY:-250,screenX:g.screenX+relX*(g.scaleFactor||1),screenY:g.screenY-250*(g.scaleFactor||1)};r.schedule();
   },x);await p.waitForTimeout(1200);
   const box=await p.locator('#stage').boundingBox(),panel=await p.locator('#panel').boundingBox();
   const gap=distance(panel);assert(name==='long-detail'?gap>nearGap*2:gap>0&&gap<=nearGap+2);
   const start=side==='left'?panel.x+panel.width-12:box.x-20;
   const end=side==='left'?box.x+box.width+20:panel.x+12;
   const clip={x:Math.max(0,start),y:Math.max(0,box.y-20),width:Math.min(geometry.width,end)-Math.max(0,start),height:Math.min(geometry.height-box.y+20,box.height+40)};
   await p.screenshot({path:`${out}/${name}.png`,clip});
   receipt.surfaces.push({detail:name,gap,link:await p.evaluate(()=>Axx.organic.tendrils.snapshot())});
  }
  receipt.checks.push('Native detail captures cover measured near and long gaps without changing avatar material');
  await p.locator('#flow-detail-back').click();await p.waitForTimeout(500);await p.locator('#flow-back').click();await p.waitForTimeout(500);
  await p.locator('#flow-fan [data-quick]').nth(1).hover();await p.waitForTimeout(600);await p.mouse.move(20,20);await p.waitForTimeout(2200);
  assert.equal(await p.evaluate(()=>Axx.flow.delivery.snapshot().links),0);receipt.checks.push('Hover release retracts and clears its surface');receipt.result='PASS';
 }catch(e){receipt.result='FAIL';receipt.error=e.stack;throw e;}
 finally{
  await p.evaluate(s=>{Axx.app.renderer.setForm(s.form,true);Axx.interfaceTheme.apply(s.theme);if(s.positions===null)localStorage.removeItem('axx.resident.panel-pos');else localStorage.setItem('axx.resident.panel-pos',s.positions);Axx.resident.panelPositions=JSON.parse(s.positions||'{}');Axx.companion.openFeature(s.view||'chat');Axx.resident.schedule();},saved);
  fs.writeFileSync(out+'/receipt.json',JSON.stringify(receipt,null,2));await b.close();console.log(receipt.result,receipt.checks);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
