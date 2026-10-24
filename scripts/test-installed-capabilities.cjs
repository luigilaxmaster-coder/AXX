// Installed WebView -> packaged workshop -> selected real model -> command executor.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 const receipt={kind:'INSTALLED_CAPABILITY_WORKSHOP',checks:[]};let capability,prior;
 const api=(method,route,body)=>p.evaluate(({method,route,body})=>Axx.backendRequest(method,route,body),{method,route,body});
 const ref=r=>({id:r.id,revision:r.revision,digest:r.digest});
 try{
  await p.waitForFunction(()=>Axx.chatWorkspace?.ready&&Axx.capabilityWorkshop);
  prior=await p.evaluate(()=>({view:Axx.companion.dock.selected,theme:Axx.interfaceTheme.value}));
  receipt.runtime=JSON.parse(fs.readFileSync(process.env.LOCALAPPDATA+'/Axx/logs/native-runtime.json','utf8'));
  await p.evaluate(()=>{Axx.resident.summon(false);return Axx.capabilityWorkshop.open();});
  await p.locator('#cap-kind').selectOption('workflow');
  await p.locator('#cap-goal').fill('Crea una capacidad llamada Aceptación · diagnóstico ECC. Objetivo: consultar el estado del equipo. Usa un único paso axx.system.telemetry sin parámetros. El esquema no tiene propiedades ni entradas requeridas, sample_inputs es un objeto vacío.');
  const previousId=await p.evaluate(()=>Axx.capabilityWorkshop.current?.id);
  const began=Date.now();await p.locator('#cap-generate').click();
  await p.waitForFunction(()=>!document.querySelector('#cap-generate').disabled,{},{timeout:100000});
  capability=await p.evaluate(()=>Axx.capabilityWorkshop.current);
  assert(capability,'Generation failed: '+await p.locator('#cap-status').innerText());
  assert.notEqual(capability.id,previousId,'The new proposal must not reuse a stale selection after an error');
  assert.equal(capability.definition.kind,'workflow');assert.equal(capability.definition.templates.length,1);
  assert.equal(capability.definition.templates[0].command_id,'axx.system.telemetry');
  receipt.generation_ms=Date.now()-began;receipt.provenance=capability.provenance;
  receipt.checks.push('Configured real model generated a bounded workflow through installed native IPC; creation performed no command');
  await p.getByRole('button',{name:'Aprobar esta versión',exact:true}).click();
  await p.getByRole('button',{name:'Preparar prueba',exact:true}).click();
  await p.waitForFunction(()=>Axx.commandLibrary.operation?.state==='awaiting_approval');
  const op=await p.evaluate(()=>Axx.commandLibrary.operation);assert.equal(op.conversation_id,await p.evaluate(()=>Axx.chatWorkspace.active.id));
  await p.locator('#command-library-approve').click();
  await p.waitForFunction(id=>Axx.commandLibrary.lastOperation?.operation_id===id&&Axx.commandLibrary.lastOperation?.state==='succeeded'&&!Axx.commandLibrary.busy,op.operation_id,{timeout:60000});
  await p.evaluate(()=>Axx.capabilityWorkshop.open());
  await p.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();
  await p.waitForFunction(()=>Axx.capabilityWorkshop.current?.state==='active');
  capability=await p.evaluate(()=>Axx.capabilityWorkshop.current);assert(capability.validation.runtime_verified);
  receipt.checks.push('Visible approval card executed telemetry; activation checked persisted plan and executor evidence');
  await p.getByRole('button',{name:'Usar capacidad',exact:true}).click();
  await p.waitForFunction(()=>/diagnóstico ECC/i.test(document.getElementById('skills-editor').innerText));
  assert(await p.locator('#skill-library').isVisible());assert.match(await p.locator('#skills-editor').innerText(),/diagnóstico ECC/i);
  receipt.checks.push('Active capability opens the existing parameterized skills surface in the Commands panel');
  await p.evaluate(()=>Axx.capabilityWorkshop.open());
  for(const theme of ['light','dark']){await p.evaluate(t=>Axx.interfaceTheme.apply(t),theme);await p.locator('#cap-editor').scrollIntoViewIfNeeded();await p.locator('#panel').screenshot({path:`build/chat-0.21.4/installed-capabilities-${theme}.png`});}
  await p.getByRole('button',{name:'Desactivar capacidad',exact:true}).click();
  await p.waitForFunction(()=>Axx.capabilityWorkshop.current?.state==='revoked');
  const rejected=await api('POST','/axx-api/learning/propose',{text:capability.skill_id,conversation_id:op.conversation_id}).catch(e=>({state:'rejected',error:String(e)}));
  assert(['rejected','failed','blocked','unavailable'].includes(rejected.state));
  receipt.checks.push('Revoked workflow cannot produce another executable plan');
  const definition={kind:'source_proposal',title:'Aceptación · código exportable',objective:'Revisar sin ejecutar',language:'python',source:"print('proposal only')",readme:'Borrador de aceptación; requiere integración manual.'};
  const source=await api('POST','/axx-api/capabilities/create',{definition});
  const exported=await api('GET','/axx-api/capabilities/export?id='+encodeURIComponent(source.id));assert.match(exported.content,/proposal only/);
  const revised=await api('POST','/axx-api/capabilities/revise',{...ref(source),definition:{...definition,title:'Aceptación · código revisado'}});
  const stale=await api('POST','/axx-api/capabilities/approve',{...ref(source),confirmed:true}).then(()=>false,()=>true);assert(stale);
  const refusesCode=await api('POST','/axx-api/capabilities/prepare',ref(revised)).then(()=>false,()=>true);assert(refusesCode);
  await api('POST','/axx-api/capabilities/revoke',ref(revised));
  receipt.checks.push('Installed code proposal exports as text; stale approval and direct code execution are rejected');
  receipt.pass=true;
 }finally{
  if(capability){try{await api('POST','/axx-api/capabilities/revoke',ref(capability));}catch(e){receipt.cleanup_error=String(e);}}
  if(prior)await p.evaluate(o=>{Axx.interfaceTheme.apply(o.theme);Axx.companion.openFeature(o.view||'chat');},prior);
  fs.writeFileSync('build/chat-0.21.4/installed-capabilities.json',JSON.stringify(receipt,null,2));await b.close();
 }
 console.log(JSON.stringify(receipt,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
