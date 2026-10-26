// Native packaged Excel step paused at its atomic boundary, then resumed without replay.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const out=path.resolve(process.argv[2]||'build/checkpoint-acceptance');fs.mkdirSync(out,{recursive:true});
 const id=crypto.randomUUID(),source=path.join(out,'checkpoint-'+id+'.csv');fs.writeFileSync(source,'Nombre;Importe\nUno;2.5\nDos;1.25\n',{flag:'wx'});
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224'),receipt={kind:'INSTALLED_CHECKPOINTS'};
 try{
  const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);
  const api=(method,route,body)=>page.evaluate(args=>Axx.backendRequest(...args),[method,route,body]);
  const plan=await api('POST','/axx-api/learning/prepare',{text:'Importar el CSV, pausar y comprobar su copia sin repetir la importación.',steps:[
   {command_id:'axx.office.excel.csv',inputs:{source,destination:'checkpoint-'+id+'.xlsx',delimiter:';',numeric_column:'Importe'}},
   {command_id:'axx.file.sha256',inputs:{},bindings:{path:{step:0,path:['output','path']}}}
  ]});receipt.prepared=plan;assert.equal(plan.state,'awaiting_approval');
  const running=api('POST','/axx-api/learning/execute',{operation_id:plan.operation_id,approved:true}).then(value=>({value}),error=>({error:String(error)}));
  let observed;
  for(let i=0;i<100;i++){observed=await api('GET','/axx-api/learning/plan?id='+plan.operation_id);if(observed.step_records[0].state==='running')break;await sleep(50);}
  assert.equal(observed.step_records[0].state,'running');
  receipt.pause=await api('POST','/axx-api/learning/pause',{operation_id:plan.operation_id});
  const execution=await running;assert(!execution.error,execution.error);receipt.paused=execution.value;
  assert.equal(receipt.paused.state,'paused');assert.equal(receipt.paused.step_records[0].state,'succeeded');assert.notEqual(receipt.paused.step_records[1].state,'succeeded');
  receipt.resume=await api('POST','/axx-api/learning/resume',{operation_id:plan.operation_id,approved:false});assert.equal(receipt.resume.state,'awaiting_approval');
  receipt.completed=await api('POST','/axx-api/learning/execute',{operation_id:plan.operation_id,approved:true});
  assert.equal(receipt.completed.state,'succeeded',JSON.stringify(receipt.completed));
  assert.equal(receipt.completed.step_records[0].operation_id,receipt.paused.step_records[0].operation_id);
  assert.equal(receipt.completed.results[0].output.sha256,receipt.completed.results[1].output.files[0].sha256);
  receipt.result='PASS';console.log('PASS: installed pause at atomic boundary, reviewed resume, original step identity and file hash preserved');
 }catch(error){receipt.result='FAIL';receipt.error=String(error);throw error;}
 finally{fs.writeFileSync(path.join(out,'installed-checkpoints.json'),JSON.stringify(receipt,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
