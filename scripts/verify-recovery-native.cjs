// Genuine WebView2/IPC, isolated candidate profile and synthetic model input. No microphone capture.
// node scripts/verify-recovery-native.cjs <AxxRecovery.exe>
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process'),{createHash}=require('node:crypto');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),out=path.join(root,'build/recovery'),exe=path.resolve(process.argv[2]||'');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const receipt={kind:'ISOLATED_RECOVERY_WEBVIEW2',checks:[],result:'FAIL'};
const save=()=>fs.writeFileSync(path.join(out,'native-acceptance.json'),JSON.stringify(receipt,null,2));
async function main(){
 assert(fs.statSync(exe).isFile(),'Pass the built isolated candidate executable');
 const profile=path.join(out,'native-profile'),local=path.join(profile,'local'),data=path.join(local,'com.axx.recovery/Axx');
 fs.mkdirSync(path.join(data,'credentials'),{recursive:true});
 const personal=path.join(process.env.LOCALAPPDATA,'Axx'),config=JSON.parse(fs.readFileSync(path.join(personal,'providers.json')));
 const selected=config.providers.find(p=>p.name==='axx1');assert(selected?.billing_allowed&&selected.capabilities.includes('vision'));
 fs.writeFileSync(path.join(data,'providers.json'),JSON.stringify({...config,providers:[selected]}));
 const credential=path.join(personal,'credentials',selected.api_key_env+'.bin');
 if(fs.existsSync(credential))fs.copyFileSync(credential,path.join(data,'credentials',path.basename(credential)));
 const flow=JSON.parse(fs.readFileSync(path.join(out,'claude-flow.json'))).providers[0].flow;
 const source=flow.find(p=>p.stage==='scene_3d'&&p.state==='completed');assert(source,'Run the real synthetic Magic Pen flow first');
 fs.mkdirSync(path.join(data,'magic-pen'),{recursive:true});
 fs.cpSync(path.join(out,'magic-pen',source.source_id),path.join(data,'magic-pen',source.source_id),{recursive:true});
 const personalBudget=path.join(personal,'magic-pen/spend-ledger.json');
 if(fs.existsSync(personalBudget))fs.copyFileSync(personalBudget,path.join(data,'magic-pen/spend-ledger.json'));
 const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
 const program=path.join(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe'),before=sha(fs.readFileSync(program));
 const log=fs.openSync(path.join(out,'native-process.log'),'a');let child,browser;
 try{
  child=spawn(exe,[],{cwd:path.dirname(exe),windowsHide:true,stdio:['ignore',log,log],env:{...process.env,LOCALAPPDATA:local,
   WEBVIEW2_USER_DATA_FOLDER:path.join(profile,'webview'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1`}});
  for(let i=0;i<180;i++){try{if((await fetch(`http://127.0.0.1:${port}/json/version`)).ok)break;}catch{}await sleep(500);}
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);const page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));assert(page);
  page.setDefaultTimeout(20000);await page.waitForFunction(()=>Axx.phase7&&Axx.chatWorkspace?.ready,null,{timeout:90000});
  await page.waitForFunction(async()=>(await Axx.nativeInvoke('native_status')).backendReady,null,{timeout:100000});
  const status=await page.evaluate(()=>Axx.nativeInvoke('native_status'));assert.equal(path.resolve(status.dataDirectory),path.resolve(data));
  assert.equal(await page.evaluate(()=>!!window.chrome?.webview),true);
  receipt.runtime={version:await page.evaluate(()=>Axx.VERSION),webview:browser.version(),backend_ready:status.backendReady,host_sha256:sha(fs.readFileSync(exe))};
  assert.equal(receipt.runtime.version,'0.22.48');
  receipt.assets={};
  for(const name of ['optical-glass.js','magic-pen.js','phase7-ui.js']){
   const bytes=Buffer.from(await page.evaluate(async name=>Array.from(new Uint8Array(await(await fetch('scripts/'+name)).arrayBuffer())),name));
   assert.equal(sha(bytes),sha(fs.readFileSync(path.join(root,'1.AXX/scripts',name))));receipt.assets[name]=sha(bytes);
  }
  receipt.checks.push('Genuine WebView2, matching source assets, backend ready and isolated namespace');save();
  const open=async id=>{await page.evaluate(id=>{Axx.resident.summon(false);Axx.companion.openFeature(id);},id);await sleep(300);};
  await open('appearance');
  receipt.material=await page.evaluate(()=>{
   const r=Axx.app.renderer,rows=[];r.setFinish('obsidian');const baseline=r.materialTable().slice();
   for(const name of AxxOpticalGlass.presets){AxxOpticalGlass.setPreset(name);r.setFinish('opticalglass');const start=performance.now(),lut=r.materialTable(),cold=performance.now()-start;
    const key=r.lutKey,cached=performance.now();r.materialTable();const warm=performance.now()-cached;
    let opaque=true;for(let i=3;i<lut.length;i+=4)if(lut[i]!==255){opaque=false;break;}
    const tendrils=Axx.organic?.tendrils||Axx.flow?.delivery;const shared=tendrils?.material(lut,r.lutKey);
    rows.push({preset:name,cold_ms:cold,cached_ms:warm,opaque,stable_cache:key===r.lutKey,tendril_lut:!!shared});
   }
   r.setFinish('obsidian');const restored=r.materialTable();return {rows,exact_obsidian:baseline.every((v,i)=>v===restored[i]),forms:Axx.FORMS.length,palettes:Axx.PALETTES.length};
  });
  assert(receipt.material.exact_obsidian);assert.equal(receipt.material.forms,24);assert.equal(receipt.material.palettes,9);
  for(const row of receipt.material.rows){assert(row.opaque&&row.stable_cache&&row.tendril_lut);assert(row.cached_ms<Math.max(5,row.cold_ms*.05));}
  receipt.checks.push('Five presets share cached tentacle material, opaque hit mask and exact full-LUT Obsidian restoration');save();
  for(const theme of ['light','dark']){
   await page.evaluate(t=>Axx.interfaceTheme.apply(t),theme);await open('appearance');
   await page.locator('[data-finish=opticalglass]').click();await page.locator('[data-optical-preset=reference]').click();await page.locator('#appearance-apply').click();
   await page.screenshot({path:path.join(out,'native-optical-'+theme+'.png')});
  }
  await page.reload();await page.waitForFunction(()=>Axx.phase7&&Axx.chatWorkspace?.ready);assert.equal(await page.evaluate(()=>Axx.app.renderer.getFinish()),'opticalglass');
  receipt.checks.push('Optical Glass and optical parameters persist across real WebView reload; both themes captured');save();
  const quality=fs.readFileSync(path.join(root,'scripts/test-installed-tendril-quality.cjs'),'utf8')
   .replace('http://127.0.0.1:9224',`http://127.0.0.1:${port}`)
   .replace('build/chat-0.21.4/tentacles/quality.json','build/recovery/tendril-quality.json')
   .replaceAll('INSTALLED_ANALYTIC_TUBE_COVERAGE','CANDIDATE_ANALYTIC_TUBE_COVERAGE');
  receipt.tendril_quality=JSON.parse(execFileSync(process.execPath,['-e',quality],{cwd:root,windowsHide:true,encoding:'utf8',timeout:240000}));
  receipt.checks.push('Existing native tube-quality sweep passed on Optical Glass');save();
  await page.evaluate(()=>Axx.magicPen.open());await page.waitForFunction(()=>Axx.magicPen.doc&&!Axx.magicPen.working);
  receipt.capture=await page.evaluate(()=>({source:Axx.magicPen.doc.source,viewport:Axx.magicPen.doc.viewport}));
  assert(receipt.capture.source.width>0&&receipt.capture.source.height>0);
  await page.evaluate(id=>Axx.magicPen.restore(id),source.source_id);
  await page.waitForFunction(()=>Axx.magicPen.player?.scene||Axx.magicPen.player?.sceneFailed,null,{timeout:60000});
  receipt.scene=await page.evaluate(()=>({qa:Axx.magicPen.player?.scene?.qa(),error:Axx.magicPen.player?.sceneFailed||null,query:Axx.magicPen.presentationQuery()?.id}));
  assert(!receipt.scene.error);assert.equal(receipt.scene.qa.objects,2);assert(receipt.scene.qa.webgl&&receipt.scene.qa.finite&&receipt.scene.qa.triangles>0);
  await page.screenshot({path:path.join(out,'native-real-3d.png')});
  receipt.checks.push('Native monitor capture and persisted real-provider 3D response rendered as two WebGL meshes');save();
  await page.evaluate(({name,model})=>{const p=Axx.magicPen;document.getElementById('mp-spatial-provider').value=encodeURIComponent(name)+'::'+encodeURIComponent(model);p.spatialProviderChanged();document.getElementById('mp-question').value='Cambia solamente el color de la primera pieza a #ff9922; conserva las dos piezas y explica el cambio.';void p.askFromComposer();},{name:selected.name,model:selected.model});
  await page.waitForFunction(()=>Axx.magicPen.analysisPending,null,{timeout:20000});
  await page.waitForFunction(()=>!Axx.magicPen.analysisPending,null,{timeout:300000});
  receipt.candidate_model=await page.evaluate(()=>{const q=Axx.magicPen.doc.queries.at(-1);return {state:q.state,query_id:q.id,objects:q.presentation?.scene?.objects.length,color:q.presentation?.scene?.objects[0]?.color,error:q.error||null,qa:Axx.magicPen.player?.scene?.qa()};});
  assert.equal(receipt.candidate_model.state,'completed',receipt.candidate_model.error);assert.equal(receipt.candidate_model.objects,2);assert.equal(receipt.candidate_model.color,'#ff9922');assert(receipt.candidate_model.qa.webgl);
  receipt.checks.push('Candidate composer, packaged backend and real authorized Claude patched the scene and rendered the result');save();
  const diagram=flow.find(p=>p.stage==='diagram_2d');
  await page.evaluate(async({id,qid})=>{const p=Axx.magicPen;const doc=await Axx.backendRequest('POST','/axx-api/pen/get',{id});doc.queries=doc.queries.filter(q=>q.id===qid);await p.load(doc,true);p.renderAnswers();},{id:source.source_id,qid:diagram.query_id});
  assert(await page.locator('.mp-diagram').count()>0);await page.screenshot({path:path.join(out,'native-real-2d.png')});
  receipt.dictation=await page.evaluate(()=>Axx.dictation.status());assert.equal(receipt.dictation.microphone_open,false);
  receipt.checks.push('Real-provider 2D diagram rendered; microphone remained closed');
  assert.equal(sha(fs.readFileSync(program)),before);receipt.personal_installation_sha256=before;receipt.result='PASS';save();
 }catch(error){receipt.error=String(error.message||error);save();throw error;}
 finally{if(browser)await browser.close();if(child&&child.exitCode===null)try{execFileSync('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}fs.closeSync(log);}
 console.log(JSON.stringify({result:receipt.result,checks:receipt.checks,material:receipt.material}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
