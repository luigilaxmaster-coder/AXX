// Installed WebView -> packaged Office workers -> independent file verification.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async()=>{
 const parent=path.resolve(process.argv[2]||'build/office-acceptance');fs.mkdirSync(parent,{recursive:true});
 const dir=fs.mkdtempSync(path.join(parent,'office-')),python=path.resolve('.venv/Scripts/python.exe');
 const csv=path.join(dir,'source.csv'),docx=path.join(dir,'source.docx');
 fs.writeFileSync(csv,'Nombre;Importe;Codigo\n=1+1;2.5;001\nSegunda;-0.25;002\n');
 execFileSync(python,['-c','from backend.tests.test_office_workflows import document_fixture; from pathlib import Path; import sys; document_fixture(Path(sys.argv[1]))',docx],{windowsHide:true});
 const before={csv:hash(csv),docx:hash(docx)},receipt={kind:'INSTALLED_OFFICE',operations:[],checks:[]};
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');
 try{
  const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);
  const api=(method,route,body)=>page.evaluate(args=>Axx.backendRequest(...args),[method,route,body]);
  const stamp=crypto.randomUUID();
  for(const [command_id,inputs] of [
   ['axx.office.excel.csv',{source:csv,destination:'office-'+stamp+'.xlsx',delimiter:';',numeric_column:'Importe'}],
   ['axx.office.word.pdf',{source:docx,destination:'office-'+stamp,append_text:'Revision requested.\nSecond line.'}]
  ]){
   const pending=await api('POST','/axx-api/commands/prepare',{command_id,inputs});
   assert.equal(pending.state,'awaiting_approval');
   const result=await api('POST','/axx-api/commands/execute',{operation_id:pending.operation_id,approved:true});receipt.operations.push(result);
   assert.equal(result.state,'succeeded',JSON.stringify(result));assert.equal(result.postconditions_passed,true);
   receipt.checks.push(command_id+' packaged worker and independent verifier passed');
  }
  assert.deepEqual({csv:hash(csv),docx:hash(docx)},before);receipt.checks.push('Both originals preserved byte for byte');
  console.log('PASS: '+receipt.checks.join('; '));
 }finally{fs.writeFileSync(path.join(dir,'installed-office.json'),JSON.stringify(receipt,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
