// Invoke prepare, restart the installed executable, then invoke verify.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const b=await chromium.connectOverCDP('http://127.0.0.1:9224'),p=b.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));
 const file='build/chat-0.21.4/installed-restart.json';
 const api=(method,route,body)=>p.evaluate(({method,route,body})=>Axx.backendRequest(method,route,body),{method,route,body});
 try{
  await p.waitForFunction(()=>Axx.chatWorkspace?.ready,{},{timeout:120000});
  if(process.argv[2]==='prepare'){
   const original=await p.evaluate(()=>Axx.chatWorkspace.active.id),runtime=await p.evaluate(()=>Axx.nativeInvoke('native_status'));
   const chat=await api('POST','/axx-api/chat/create',{title:'Aceptación · reinicio real',command_mode:'ask'});
   await api('POST','/axx-api/chat/save',{id:chat.id,draft:'Borrador conservado después de reiniciar el ejecutable'});
   await p.evaluate(id=>Axx.chatWorkspace.select(id),chat.id);
   const pending=await api('POST','/axx-api/commands/prepare',{command_id:'axx.system.telemetry',inputs:{},source:'text',conversation_id:chat.id});
   assert.equal(pending.state,'awaiting_approval');
   fs.writeFileSync(file,JSON.stringify({original,chat:chat.id,operation:pending.operation_id,before:runtime.backendInstance,result:'PREPARED'},null,2));
  }else{
   const receipt=JSON.parse(fs.readFileSync(file));
   try{
    const runtime=await p.evaluate(()=>Axx.nativeInvoke('native_status'));assert.notEqual(runtime.backendInstance,receipt.before);
    await p.evaluate(id=>{Axx.resident.summon(false);Axx.companion.openChat();return Axx.chatWorkspace.select(id);},receipt.chat);
    assert.match(await p.locator('#chat-input').inputValue(),/Borrador conservado/);
    await p.locator('#cw-operation').getByRole('button',{name:'Preparar de nuevo',exact:true}).waitFor({state:'visible'});
    const all=await api('GET','/axx-api/chat/operations');assert.equal(all.operations.find(o=>o.operation_id===receipt.operation).state,'expired');
    await p.locator('#cw-operation').getByRole('button',{name:'Preparar de nuevo',exact:true}).click();
    await p.waitForFunction(()=>Axx.commandLibrary.operation?.state==='awaiting_approval');
    receipt.renewed=await p.evaluate(()=>Axx.commandLibrary.operation.operation_id);assert.notEqual(receipt.renewed,receipt.operation);
    await p.locator('#cw-operation').getByRole('button',{name:'Cancelar comando',exact:true}).click();
    const cancelDeadline=Date.now()+30000;let cancelled;
    do{
     const snapshot=await api('GET','/axx-api/chat/operations');
     cancelled=snapshot.operations.find(o=>o.operation_id===receipt.renewed);
     if(cancelled?.state==='cancelled')break;
     await wait(150);
    }while(Date.now()<cancelDeadline);
    assert.equal(cancelled?.operation_id,receipt.renewed,'Renewed operation disappeared before cancellation readback');
    assert.equal(cancelled.state,'cancelled','Renewed operation did not persist cancellation before the deadline');
    receipt.cancelReadback={operation_id:cancelled.operation_id,state:cancelled.state};
    receipt.after=runtime.backendInstance;receipt.result='PASS';receipt.checks=['New installed backend instance restored draft and expired preparation without execution','Explicit preparation requested a new approval; cancellation persisted'];
   }catch(e){receipt.result='FAIL';receipt.error=e.stack;throw e;}
   finally{for(const operation_id of new Set([receipt.operation,receipt.renewed].filter(Boolean)))await api('POST','/axx-api/commands/cancel',{operation_id});await p.evaluate(id=>Axx.chatWorkspace.select(id),receipt.original);await api('POST','/axx-api/chat/delete',{id:receipt.chat});fs.writeFileSync(file,JSON.stringify(receipt,null,2));console.log(receipt.result,receipt.checks);}
  }
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
