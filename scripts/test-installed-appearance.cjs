// Native installed controls, window geometry, keyboard and persistence.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const out=process.argv[2]||'build/chat-0.21.4';fs.mkdirSync(out,{recursive:true});
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 p.setDefaultTimeout(15000);const receipt={kind:'INSTALLED_APPEARANCE',checks:[]};
 const saved=await p.evaluate(()=>({theme:Axx.interfaceTheme.value,custom:localStorage.getItem('axx.interface.customization'),positions:localStorage.getItem('axx.resident.panel-pos'),view:Axx.companion.dock.selected}));
 const open=async id=>{await p.evaluate(id=>{Axx.resident.summon(false);Axx.companion.openFeature(id);},id);await p.waitForTimeout(650);};
 try{
  await open('settings');await p.locator('[data-axx-theme=light]').click();
  for(const [id,value] of [['background','#f3f6f2'],['text','#26332b'],['icons','#287355']])await p.locator('#axx-color-'+id).evaluate((el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));},value);
  await p.locator('#axx-interface-font').selectOption('serif');await p.locator('#axx-interface-size').selectOption('large');
  assert.equal(await p.locator('#panel').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(243, 246, 242)');
  assert.match(await p.locator('#axx-theme-contrast').innerText(),/se guarda/);
  await p.locator('#panel').screenshot({path:out+'/installed-custom-theme.png'});
  await p.reload();await p.waitForFunction(()=>Axx.chatWorkspace?.ready);await open('settings');
  assert.equal(await p.locator('#axx-color-background').inputValue(),'#f3f6f2');assert.equal(await p.locator('#axx-interface-font').inputValue(),'serif');assert.equal(await p.locator('#axx-interface-size').inputValue(),'large');
  receipt.checks.push('Custom background, text, icons, font and size persist across a WebView reload');
  await p.locator('[data-axx-theme=dark]').click();assert.notEqual(await p.locator('#axx-color-background').inputValue(),'#f3f6f2');
  await p.locator('[data-axx-theme=light]').click();assert.equal(await p.locator('#axx-color-background').inputValue(),'#f3f6f2');await p.locator('#axx-theme-reset').click();
  assert.equal(await p.locator('#axx-color-background').inputValue(),'#ffffff');receipt.checks.push('Light/dark retain independent colors; reset restores defaults');
  await open('chat');const chatBefore=await p.locator('#panel').boundingBox();await open('settings');
  const handle=p.locator('#panel .resident-resize-handle'),box=await handle.boundingBox();assert(box);
  await p.mouse.move(box.x+box.width/2,box.y+box.height/2);await p.mouse.down();await p.mouse.move(box.x-110,box.y-80,{steps:12});await p.mouse.up();await p.waitForTimeout(800);
  const resized=await p.locator('#panel').boundingBox();await open('chat');const chatAfter=await p.locator('#panel').boundingBox();
  assert(Math.abs(chatBefore.width-chatAfter.width)<2);assert(Math.abs(chatBefore.height-chatAfter.height)<2);
  await open('settings');const restored=await p.locator('#panel').boundingBox();assert(Math.abs(restored.width-resized.width)<2);assert(Math.abs(restored.height-resized.height)<2);
  receipt.checks.push('Pointer resize is stored per tool; changing settings size does not resize chat');
  await open('chat');await p.evaluate(()=>{Axx.resident.panelPositions['panel:chat']={width:540,height:480};Axx.resident.schedule();Axx.liveConversation.show();});await p.waitForTimeout(800);
  const compact=await p.locator('#panel').boundingBox(),composer=await p.locator('#chat-form').boundingBox();
  await p.locator('#panel').screenshot({path:out+'/installed-live-compact.png'});
  assert(composer&&composer.y+composer.height<=compact.y+compact.height+1,'Voice controls must leave the composer reachable in a compact chat');
  await p.locator('#chat-live-close').click();await p.evaluate(old=>{const positions=JSON.parse(old||'{}');if(positions['panel:chat'])Axx.resident.panelPositions['panel:chat']=positions['panel:chat'];else delete Axx.resident.panelPositions['panel:chat'];Axx.resident.schedule();},saved.positions);
  receipt.checks.push('Compact voice panel keeps its composer inside the window');
  await open('settings');
  await p.locator('#flow-detail-back').click();await p.locator('#flow-library').waitFor({state:'visible'});await p.waitForTimeout(700);
  assert.equal(await p.locator('#panel').isVisible(),false);
  for(const tab of await p.locator('#flow-tabs button').all()){
   await tab.click();await p.waitForTimeout(200);for(const item of await p.locator('#flow-grid [data-tool]').all()){assert((await item.innerText()).trim().length);const r=await item.boundingBox();assert(r.width>=40&&r.height>=40);}
  }
  await p.locator('#flow-tabs button').first().click();await p.keyboard.press('ArrowRight');assert(await p.locator('#flow-tabs button').nth(1).evaluate(e=>e===document.activeElement));
  await p.locator('#flow-library').screenshot({path:out+'/installed-catalog.png'});
  receipt.checks.push('Catalog replaces the main panel, exposes tool labels and supports keyboard tabs');
  await p.locator('#flow-back').click();await p.waitForTimeout(650);assert.equal(await p.locator('#panel').isVisible(),false);
  for(const item of await p.locator('#flow-fan button').all())assert.equal(await item.evaluate(e=>getComputedStyle(e).backgroundColor),'rgba(0, 0, 0, 0)');
  await p.screenshot({path:out+'/installed-orbit.png'});receipt.checks.push('Orbit controls retain transparent 3D artwork without white rectangles');
  receipt.result='PASS';
 }catch(e){receipt.result='FAIL';receipt.error=e.stack;throw e;}
 finally{
  await p.evaluate(s=>{for(const [key,value] of [['axx.interface.theme',s.theme],['axx.interface.customization',s.custom],['axx.resident.panel-pos',s.positions]]){if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}},saved);
  await p.reload();await p.waitForFunction(()=>Axx.chatWorkspace?.ready);await open(saved.view||'chat');
  fs.writeFileSync(out+'/installed-appearance.json',JSON.stringify(receipt,null,2));await b.close();console.log(receipt.result,receipt.checks);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
