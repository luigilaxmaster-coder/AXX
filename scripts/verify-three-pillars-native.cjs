// Actual Windows WebView2 and frozen sidecar; isolated data, synthetic image and temporary Git project.
// node scripts/verify-three-pillars-native.cjs <built Axx.exe>
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process'),{createHash}=require('node:crypto');
const {chromium}=require(process.env.USERPROFILE+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=process.cwd(),out=path.join(root,'build/three-pillars/native-'+Date.now());fs.mkdirSync(out,{recursive:true});
const exe=path.resolve(process.argv[2]||''),sha=bytes=>createHash('sha256').update(bytes).digest('hex'),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const version=JSON.parse(fs.readFileSync('package.json')).version;
const receipt={kind:'THREE_PILLARS_NATIVE_WEBVIEW2',version,result:'FAIL',checks:[],limitations:['Synthetic image; no real vision-provider claim','DPI/GPU physical classes outside this monitor unverified','Playback events do not measure physical speaker output','Remote Asset Gate not configured']};
const save=()=>fs.writeFileSync(path.join(out,'native-acceptance.json'),JSON.stringify(receipt,null,2));
let child,browser,page,log;
async function stop(){
 if(browser){try{await browser.close();}catch{}browser=null;}
 if(child&&child.exitCode===null){try{execFileSync('taskkill.exe',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}await sleep(1000);}
}
async function launch(fixture){
 const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
 const profile=path.join(out,'native-profile');
 child=spawn(exe,[],{cwd:path.dirname(exe),windowsHide:true,stdio:['ignore',log,log],env:{...process.env,
   LOCALAPPDATA:path.join(profile,'local'),APPDATA:path.join(profile,'roaming'),WEBVIEW2_USER_DATA_FOLDER:path.join(profile,'webview'),
   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port} --remote-debugging-address=127.0.0.1`}});
 for(let i=0;i<180;i++){if(child.exitCode!==null)throw Error('Native host exited before WebView2 connected');try{if((await fetch(`http://127.0.0.1:${port}/json/version`)).ok)break;}catch{}await sleep(500);}
 browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
 for(let i=0;i<120;i++){page=browser.contexts()[0].pages().find(p=>p.url().includes('Axx.html'));if(page)break;await sleep(500);}assert(page);
 page.setDefaultTimeout(45000);await page.waitForFunction(()=>Axx.chatWorkspace?.ready&&Axx.codeStudio&&Axx.acts,null,{timeout:90000});
 await page.waitForFunction(async()=>(await Axx.nativeInvoke('native_status')).backendReady,null,{timeout:120000});
 const state=await page.evaluate(()=>Axx.nativeInvoke('native_status'));
 assert.equal(path.resolve(state.dataDirectory),path.resolve(fixture.data_directory));
 assert(await page.evaluate(()=>!!window.chrome?.webview));assert.equal(await page.evaluate(()=>Axx.VERSION),version);
 receipt.runtime={pid:child.pid,webview:browser.version(),host_sha256:sha(fs.readFileSync(exe)),backend_ready:state.backendReady,desktop:state.desktop};save();
}
async function api(method,route,body){return page.evaluate(([method,route,body])=>Axx.backendRequest(method,route,body),[method,route,body]);}
async function flags(){
 for(const flag of (await api('GET','/axx-api/agents/v1/flags')).flags.filter(f=>['agent_profiles_v1','code_studio_v1','code_execution_v1','magic_scene_v2'].includes(f.flag_id)&&!f.enabled))
   await api('POST','/axx-api/agents/v1/flags/set',{flag_id:flag.flag_id,enabled:true,expected_revision:flag.revision,reason:'isolated native acceptance',gate_receipt_ref:'manual-opt-in'});
}
async function openScene(id){
 await page.evaluate(async id=>{Axx.companion.openFeature('chat');const pen=Axx.magicPen;pen.active=true;pen.root.hidden=false;pen.state='reviewing';
   await pen.load(await Axx.backendRequest('POST','/axx-api/pen/get',{id}),true);pen.showWidget();},id);
 await page.waitForFunction(()=>Axx.magicPen.player?.scene&&Axx.magicPen.player?.v2Scene);
}
async function openCode(repo,file='human.py'){
 await page.evaluate(()=>{Axx.magicPen.close?.();Axx.companion.openFeature('codestudio');});
 await page.waitForFunction(()=>Axx.codeStudio.editor);
 const settings=page.locator('[data-code=project-settings]');await settings.evaluate(n=>n.open=true);
 await page.locator('[data-code=root]').fill(repo);await page.getByRole('button',{name:'Abrir proyecto',exact:true}).click();
 await page.locator('[data-code=browser]').getByRole('button',{name:file,exact:true}).click();
 await page.waitForFunction(file=>Axx.codeStudio.activeFile?.path===file,file);
}
async function main(){
 assert(fs.statSync(exe).isFile());
 const fixture=JSON.parse(execFileSync('python',['scripts/seed-three-pillars-native.py',out],{encoding:'utf8',windowsHide:true}));
 const installed=path.join(process.env.LOCALAPPDATA,'Programs/Axx/Axx.exe'),oldHash=fs.existsSync(installed)?sha(fs.readFileSync(installed)):null;
 log=fs.openSync(path.join(out,'process.log'),'a');
 try{
  await launch(fixture);await flags();
  const originals=await page.evaluate(()=>({avatar:localStorage.getItem('axx-studio-v2'),reader:{voice:Axx.symbiosis.reader.voiceURI,rate:Axx.symbiosis.reader.rate}}));
  const voices=await api('GET','/axx-api/speech/voices'),voice=voices.voices.find(v=>!v.engine||v.engine==='windows-sapi');assert(voice,'Windows SAPI voice required for native TTS acceptance');
  for(const [i,name] of ['Native Dev','Native Visual','Native QA'].entries())await api('POST','/axx-api/agents/v1/profiles',{
   schema_version:'1.0',revision:1,agent_id:'native-'+i,name,role:i===2?'QA':'Assistant',instructions:'Responde solamente al alcance de tu turno.',
   enabled:true,appearance:{form_id:i,palette_id:i,material_preset:'optical_glass'},
   intelligence:{provider_profile_ref:'axx-connect',model_id:'gpt-6.1-sol',route:'manual',fallback:'none'},
   workspace:{runtime:'none',foreground_policy:'deny'},permissions:{tool_grant_refs:[],delegation_enabled:false},limits:{max_concurrent_jobs:1,max_retries:0},
   memory_scope:'agent',voice:{tts_profile_id:'sapi:'+voice.name,speed:1,language:voice.language||'es-ES'}});
  await page.evaluate(()=>Axx.acts.load());await page.evaluate(()=>Axx.companion.openFeature('chat'));
  const browse=page.locator('#cw-browse');if(await browse.isVisible())await browse.click();
  await page.locator('.axx-chat-act-navigation').getByRole('tab',{name:'Acts',exact:true}).click();
  await page.getByRole('button',{name:'Mis Acts',exact:true}).waitFor();
  await page.evaluate(()=>Axx.acts.chooseForChat('native-0'));
  assert.equal(await page.evaluate(()=>localStorage.getItem('axx-studio-v2')),originals.avatar);
  receipt.checks.push('Acts sidebar uses existing chats; three independent profiles; global avatar unchanged');
  await page.evaluate(()=>Axx.companion.read('〔Native Dev〕 Verificación de voz de AXX.'));
  await page.waitForFunction(()=>Axx.nativeVoice.playback?.ended_event||Axx.symbiosis.reader.state==='error',null,{timeout:90000});
  receipt.voice=await page.evaluate(()=>({playback:Axx.nativeVoice.playback,state:Axx.symbiosis.reader.state,global:Axx.symbiosis.reader.voiceURI}));
  assert(receipt.voice.playback?.playing_event&&receipt.voice.playback?.ended_event);assert.equal(receipt.voice.playback.voice,voice.name);
  assert.equal(receipt.voice.global,originals.reader.voice);receipt.checks.push('Real Windows SAPI WAV synthesized and played to ended event with Act voice');save();
  await openScene(fixture.capture_id);
  await page.evaluate(()=>Axx.magicPen.patchScenePartV2('a',{properties:{color:'#ff0000',material:'metal_brushed'},transform:{scale:[2,1,1]}}));
  const glb=await page.evaluate(()=>Axx.magicPen.exportSceneGeometry());assert.equal(sha(fs.readFileSync(glb.path)),glb.verification.sha256);
  await page.evaluate(id=>Axx.magicPen.insertGlbV2(id),glb.asset.asset_id);
  page.once('dialog',dialog=>dialog.accept());const cad=await page.evaluate(()=>Axx.magicPen.buildCadV2());assert.equal(cad.congruence.solid_count,3);assert(cad.congruence.congruent);
  await page.evaluate(()=>{Axx.magicPen.player.scene.setSection('x',0);Axx.magicPen.player.scene.setExploded(true);});
  await sleep(600);assert(await page.evaluate(()=>Axx.magicPen.player.scene.qa().webgl));
  await page.screenshot({path:path.join(out,'native-magic-pen.png')});
  await page.evaluate(()=>Axx.magicPen.addRotationV2('a'));const video=await page.evaluate(()=>Axx.magicPen.exportSceneVideo());
  assert.equal(video.frame_count,50);assert(video.motion_observed);assert.equal(sha(fs.readFileSync(video.output_path)),video.mp4_sha256);
  receipt.scene={capture_kind:'synthetic',glb:glb.verification,cad:cad.congruence,video,revision:await page.evaluate(()=>Axx.magicPen.player.v2Scene.revision)};
  receipt.checks.push('Native WebGL actual meshes, materials, local GLB reuse, three CAD solids, clipping/explode and decoded 5s MP4');save();
  await openCode(fixture.project);
  await page.evaluate(()=>Axx.codeStudio.editor.setValue('VALUE = 2\n'));await page.locator('[data-code=save]').click();
  await page.waitForFunction(()=>document.querySelector('[data-code=status]').textContent.includes('guardado y verificado'));
  assert.equal(fs.readFileSync(path.join(fixture.project,'human.py')).toString('hex'),Buffer.from('\ufeffVALUE = 2\r\n').toString('hex'));
  const project=await page.evaluate(()=>Axx.codeStudio.activeFile.project_id);
  const lsp=await api('POST','/axx-api/code/v1/lsp/sync',{project_id:project,language:'python',path:'lsp_case.py',content:fs.readFileSync(path.join(fixture.project,'lsp_case.py'),'utf8')});
  assert.equal(lsp.lsp_status,'live');assert(lsp.diagnostics.some(d=>d.message.includes('missing_name')));
  const debug=await api('POST','/axx-api/code/v1/dap/launch',{project_id:project,session_id:'native-debug',path:'debug_case.py',line:3,
    expected_sha256:sha(fs.readFileSync(path.join(fixture.project,'debug_case.py'))),user_approved:true});
  assert.equal(debug.state,'stopped');assert.equal(debug.locals.answer,'42');assert(debug.stack_frames.length);
  await api('POST','/axx-api/code/v1/dap/stop',{session_id:'native-debug'});
  await page.evaluate(()=>Axx.codeStudio.editor.setValue('VALUE = 3\n'));await page.evaluate(()=>Axx.codeStudio.flushDrafts());
  await page.screenshot({path:path.join(out,'native-monaco.png')});
  receipt.code={lsp_status:lsp.lsp_status,diagnostics:lsp.diagnostics,debug:{state:debug.state,locals:debug.locals,stack_frames:debug.stack_frames}};
  receipt.checks.push('Native bundled Monaco saves BOM/CRLF bytes; real LSP diagnostic and DAP breakpoint/stack/locals');save();
  await stop();await launch(fixture);await flags();await openCode(fixture.project);
  assert.equal(await page.evaluate(()=>Axx.codeStudio.editor.getValue()),'VALUE = 3\n');
  assert.equal(fs.readFileSync(path.join(fixture.project,'human.py')).toString('hex'),Buffer.from('\ufeffVALUE = 2\r\n').toString('hex'));
  await openScene(fixture.capture_id);assert.equal(await page.evaluate(()=>Axx.magicPen.player.v2Scene.revision),receipt.scene.revision);
  assert.equal((await api('GET','/axx-api/agents/v1/profiles')).profiles.length,3);
  receipt.checks.push('Native process restart recovers unsaved draft, persisted scene revision and three Acts');
  assert.equal(oldHash,fs.existsSync(installed)?sha(fs.readFileSync(installed)):null);receipt.personal_installation_unchanged=true;
  receipt.result='PASS';save();console.log(JSON.stringify({result:receipt.result,evidence:out,checks:receipt.checks}));
 }catch(error){receipt.error=String(error.stack||error);save();throw error;}
 finally{await stop();if(log!==undefined)fs.closeSync(log);}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
