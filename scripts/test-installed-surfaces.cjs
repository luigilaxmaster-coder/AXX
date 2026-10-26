// Installed WebView inspection. Screenshots remain private in ignored build/.
const fs=require('fs'),assert=require('node:assert/strict'),{chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
await p.waitForFunction(()=>Axx.chatWorkspace?.ready,{},{timeout:120000});
const original=await p.evaluate(()=>({theme:Axx.interfaceTheme.value,view:Axx.companion.dock.selected,chat:Axx.chatWorkspace.active.id}));let auditChat;
try {
auditChat=await p.evaluate(async()=>{const r=await Axx.backendRequest('POST','/axx-api/chat/create',{title:'Aceptación visual del chat'});await Axx.backendRequest('POST','/axx-api/chat/save',{id:r.id,messages:[{id:'audit-user-'+Date.now(),role:'user',status:'complete',at:Date.now(),text:'Revisa el aspecto de este chat.'},{id:'audit-assistant-'+Date.now(),role:'assistant',status:'complete',at:Date.now()+1,text:'Texto legible, **énfasis**, `comandos` y [documentación](https://github.com/luigilaxmaster-coder/AXX).'}]});await Axx.chatWorkspace.select(r.id);return r.id;});
const dir=process.argv[2]||'build/chat-0.21.4/surface-audit';fs.mkdirSync(dir,{recursive:true});const rows=[];
const features=await p.evaluate(()=>Axx.FEATURES.filter((f,i,a)=>!['studio','tour','focusNow','reach','learn','magicpen'].includes(f.id)&&a.findIndex(x=>x.view===f.view)===i).map(f=>({id:f.id,view:f.view})));
for(const theme of ['light','dark']){await p.evaluate(t=>Axx.interfaceTheme.apply(t),theme);
 for(const f of features){await p.evaluate(f=>{Axx.companion.dock.detail(f.id);Axx.companion.renderDock();Axx.resident.schedule();document.getElementById('view-'+f.view).scrollTop=0},f);await p.waitForTimeout(600);
 const row=await p.evaluate(({f,theme})=>{
 const root=document.querySelector('#view-'+f.view);
 const rgb=s=>{const a=(s.match(/[\d.]+/g)||[]).map(Number);return a.length>=3?[...a.slice(0,3).map(v=>s.startsWith('color(srgb')?v*255:v),a[3]??1]:[0,0,0,0]};
 const blend=(a,b)=>a.slice(0,3).map((x,i)=>x*a[3]+b[i]*(1-a[3]));
 const lum=c=>c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
 const failures=[],gradients=[];const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
 while(n=walk.nextNode()){
  const e=n.parentElement,s=getComputedStyle(e);if(!n.textContent.trim()||!e.getClientRects().length||e.closest('[hidden],button:disabled,input:disabled,option,svg,style,script')||parseFloat(s.fontSize)<8||s.visibility!=='visible')continue;
  const chain=[];for(let a=e;a;a=a.parentElement)chain.unshift(a);
  let bg=[255,255,255],opacity=1,gradient=false;
  for(const a of chain){const st=getComputedStyle(a);bg=blend(rgb(st.backgroundColor),bg);opacity*=Number(st.opacity);if(st.backgroundImage!=='none')gradient=true;}
  if(opacity===0)continue;
  const fg=rgb(s.color);fg[3]*=opacity;const color=blend(fg,bg),l1=lum(color),l2=lum(bg),ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
  const selector=e.id?'#'+e.id:e.tagName.toLowerCase()+'.'+[...e.classList].join('.')+' (in '+(e.parentElement.id||e.parentElement.className)+')';
  const item={selector,ratio:Math.round(ratio*100)/100,color:s.color,bg:bg.map(Math.round),gradient};
  if(ratio<((parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700))?3:4.5))failures.push(item);
  if(gradient)gradients.push(selector);
 }
 const launcher=document.getElementById('flow-pill'),launcherHidden=!launcher.getClientRects().length||getComputedStyle(launcher).visibility==='hidden';
 return {theme,...f,visible:!root.hidden,launcherHidden,active:[...document.querySelectorAll('#panel .panel-view')].filter(n=>n.getClientRects().length&&getComputedStyle(n).display!=='none').map(n=>n.id),overflow:root.scrollWidth-root.clientWidth,failures,gradients:[...new Set(gradients)]};
 },{f,theme});rows.push(row);await p.locator('#panel').screenshot({path:`${dir}/${theme}-${f.id}.png`});
 }
}
fs.writeFileSync(dir+'/report.json',JSON.stringify(rows,null,2));
const failures=rows.filter(r=>r.failures.length||r.active.length!==1||r.overflow>2||!r.visible||!r.launcherHidden);
console.log(JSON.stringify({views:rows.length,failures},null,2));assert.equal(failures.length,0,'Inspect the private surface audit report');
} finally {await p.evaluate(async o=>{await Axx.chatWorkspace.select(o.chat);Axx.interfaceTheme.apply(o.theme);Axx.companion.openFeature(o.view||'chat');},original);if(auditChat)await p.evaluate(id=>Axx.backendRequest('POST','/axx-api/chat/delete',{id}),auditChat);await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
