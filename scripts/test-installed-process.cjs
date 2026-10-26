// Reviewed, read-only Windows process through the packaged executor; exit is not application success.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const out=path.resolve(process.argv[2]||'build/process-acceptance');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9224');let receipt={kind:'INSTALLED_PROCESS'};
 try{
  const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);
  const api=(method,route,body)=>page.evaluate(args=>Axx.backendRequest(...args),[method,route,body]);
  const prepared=await api('POST','/axx-api/commands/prepare',{command_id:'axx.process.run',inputs:{executable:path.join(process.env.SystemRoot,'System32/cmd.exe'),args:['/d','/c','ver'],cwd:out,timeout_s:10}});
  assert.equal(prepared.state,'awaiting_approval');
  receipt.operation=await api('POST','/axx-api/commands/execute',{operation_id:prepared.operation_id,approved:true});
  assert.equal(receipt.operation.state,'unknown',JSON.stringify(receipt.operation));assert.equal(receipt.operation.postconditions_passed,false);
  assert.equal(receipt.operation.output.exit_code,0);assert.match(receipt.operation.output.stdout,/Microsoft Windows/);
  receipt.review=await api('POST','/axx-api/commands/review',{operation_id:prepared.operation_id,reviewed:true});
  assert.equal(receipt.review.state,'unknown');receipt.result='PASS';console.log('PASS: packaged owned process returned Windows version; zero exit stayed separate from verified application effect');
 }finally{fs.writeFileSync(path.join(out,'installed-process.json'),JSON.stringify(receipt,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
