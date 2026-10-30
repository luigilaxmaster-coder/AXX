/** Real frontend scripts with isolated IPC/ChatStore doubles; no backend or native effects. */
const path = require('node:path');
const assert = require('node:assert/strict');
const { requirePlaywright, launchChromium } = require('./test-browser-runtime.cjs');
const { chromium } = requirePlaywright();

async function fixture(browser) {
  const page = await browser.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('http://document-provenance.test/', route => route.fulfill({contentType:'text/html',body:
    '<main id="view-files"><section id="view-commands"></section></main><section id="view-agent"></section><section id="desktop-runtime"></section>' +
    '<section id="view-chat"><div id="chat-log"></div><textarea id="chat-input"></textarea><button id="chat-new"></button></section><input id="keep-history" type="checkbox" checked>'}));
  await page.goto('http://document-provenance.test/');
  await page.evaluate(() => {
    const clone = value => value === undefined ? undefined : structuredClone(value);
    window.calls = []; window.notices = []; window.opened = []; window.renderedPlans = []; window.unexpectedRoutes = []; window.serial = 0;
    window.holds = {}; window.releases = {}; window.capabilities = {};
    if (!crypto.randomUUID) crypto.randomUUID = () => 'synthetic-' + (++serial);
    const chat = id => ({id,title:'Chat '+id,group_id:'group',mode:'ask',archived:false,updated:Date.now(),
      messages:[],context:[],links:[],draft:'Independent draft '+id,draft_at:Date.now(),agent_profile:{},
      connect_id:'opaque-'+id,context_id:'opaque-'+id,shared_id:'shared-'+id,memory_scope:{task_id:id,generation:0}});
    window.chats = {A:chat('A'),B:chat('B')};
    window.documentReference = {document_id:'AXX-REF-HISTORY-bbbbbbbbbbbb',record_sha256:'a'.repeat(64),member_sha256:'b'.repeat(64),revision:'2026-10-30'};
    window.procedure = {document_reference:clone(documentReference),reference_text:'UNTRUSTED DOCUMENT DATA',
      source_status:'DOCUMENTED_NOT_EXECUTED',execution_enabled:false,source_member:'<img src=x onerror=window.injected=true>',
      recipe:{prerequisites:'<img src=x onerror=window.injected=true>',steps:[{action:'reference_only',text:'Never execute this document'}]}};
    window.catalog = [{id:documentReference.document_id,title:'<img src=x onerror=window.injected=true>',
      description:'Reference data only',execution_enabled:false,has_recipe_details:true,source_status:'DOCUMENTED_NOT_EXECUTED',parameters:{}}];
    window.makeCapability = (id='cap.'+'c'.repeat(32),owner='A',state='draft') => ({id,revision:1,digest:'d'.repeat(64),state,
      memory_scope:clone(chats[owner].memory_scope),memory_context_id:chats[owner].connect_id,document_references:[clone(documentReference)],
      definition:{kind:'workflow',title:'PRIVATE_CAPABILITY_'+owner,objective:'Synthetic objective '+owner,
        schema:{type:'object',properties:{},required:[]},templates:[],sample_inputs:{}},
      validation:{steps:[],risks:[],runtime_verified:false},approval:state==='draft'?null:{digest:'d'.repeat(64),revision:1},
      validation_operation_id:state==='draft'?null:'trial-'+owner,versions:[{revision:1}]});
    window.makePlan = (body={},owner='A') => ({kind:'learned_plan',operation_id:body.operation_id||'task-'+owner,
      conversation_id:owner,memory_scope:clone(chats[owner].memory_scope),memory_context_id:chats[owner].connect_id,
      state:'awaiting_approval',title:'PRIVATE_PLAN_'+owner,message:'Synthetic prepared '+owner,plan_hash:'e'.repeat(64),
      steps:body.steps||[{command_id:'axx.file.compare',inputs:{path:'synthetic-left',other_path:'synthetic-right'}}],
      step_records:[{state:'pending'}],results:[],document_references:clone(body.document_references||[]),model_calls_used:0});
    window.hold = route => { holds[route] = true; };
    window.mutations = () => calls.filter(call => call.method==='POST' && /^\/axx-api\/(capabilities|learning|commands)\//.test(call.route));
    const c = {data:{messages:[],draft:'',prefs:{keepHistory:true,skillProject:'project',provider:'bridge',apiConnection:'fixture',model:'fixture-model',selection_mode:'manual'}},
      attachment:null,brain:{lastRoute:null,chat:async()=>{throw Error('No provider may run in this fixture');}},
      save(){},renderAttachment(){},renderChat(){document.getElementById('chat-log').textContent=this.data.messages.map(m=>m.text).join('\n');},
      message(role,text,source='local'){const message={id:'message-'+(++serial),role,text,source,status:'complete',at:Date.now()};this.data.messages.push(message);return message;},
      localNotice(text){notices.push(text);},send:async()=>{},cancelRequest(){},stopDictation(){},stopSpeech(){},sayStatus(){},
      openFeature(id){opened.push(id);},openChat(){opened.push('chat');},action(){},exportChat(){}};
    window.Axx = {isNative:()=>true,newId:()=> 'fixture-'+(++serial),app:{bridge:{listen:async()=>()=>{}},toast(){}},
      resident:{schedule(){}},companion:c,skillLibrary:{project:()=> 'project',invalidateMemory(){},async refresh(){}},
      backendRequest:async(method,route,body)=>{
        calls.push({method,route,body:clone(body)});
        let value;
        if(route==='/axx-api/chat/migrate')value={id:'A',created:false};
        else if(route==='/axx-api/chat/conversations')value={conversations:Object.values(chats).map(clone),groups:[{id:'group',title:'Group'}],default_mode:'ask'};
        else if(route.startsWith('/axx-api/chat/conversations?'))value=clone(chats[new URLSearchParams(route.split('?')[1]).get('id')]);
        else if(route==='/axx-api/chat/operations')value={operations:[]};
        else if(route==='/axx-api/chat/save'){
          const current=chats[body.id];
          if(body.memory_scope?.task_id!==body.id||body.memory_scope.generation!==current.memory_scope.generation||body.memory_context_id!==current.connect_id)throw Error('STALE_MEMORY_SNAPSHOT');
          current.messages=clone(body.messages);current.draft=body.draft;value={id:body.id};
        }
        else if(route.startsWith('/axx-api/commands?'))value={commands:clone(catalog),counts:{imported:1,enabled:0,blocked:1}};
        else if(route.startsWith('/axx-api/commands/details?'))value={procedure:clone(procedure)};
        else if(route==='/axx-api/capabilities/list')value={capabilities:Object.values(capabilities).map(clone)};
        else if(route.startsWith('/axx-api/capabilities/get?'))value=clone(capabilities[new URLSearchParams(route.split('?')[1]).get('id')]);
        else if(route==='/axx-api/capabilities/generate'){
          const owner=body.memory_scope?.task_id||'A',id='cap.'+(++serial).toString(16).padStart(32,'0');
          value=makeCapability(id,owner);value.document_references=clone(body.document_references||[]);
          if(body.kind==='source_proposal')value.definition={kind:'source_proposal',title:value.definition.title,objective:body.goal,
            language:'python',source:'SYNTHETIC_CODE_DATA_ONLY',readme:'Synthetic manual review'};
          capabilities[id]=clone(value);
        }
        else if(route==='/axx-api/capabilities/activate'){
          value={...clone(capabilities[body.id]),state:'active',active_revision:body.revision};capabilities[body.id]=clone(value);
        }
        else if(route==='/axx-api/learning/bind-capability')value={...clone(window.taskPlan),capability_build:{id:body.id,revision:body.revision,digest:body.digest}};
        else if(route==='/axx-api/learning/resume')value=makePlan(body,window.taskPlan?.conversation_id||'A');
        else if(route==='/axx-api/learning/prepare'||route==='/axx-api/learning/propose'){
          value=makePlan(body,body.conversation_id||'A');
          if(route.endsWith('/propose')&&window.capabilityMissing)value={...value,state:'failed',capability_missing:true,message:'Synthetic missing capability'};
        }
        else {unexpectedRoutes.push(method+' '+route);throw Error('Unexpected fixture route: '+method+' '+route);}
        value=clone(value);
        if(holds[route]){delete holds[route];await new Promise(resolve=>releases[route]=resolve);}
        return value;
      }};
  });
  for(const file of ['command-library.js','chat-workspace.js'])await page.addScriptTag({path:path.join(__dirname,file)});
  await page.waitForFunction(()=>Axx.chatWorkspace.ready);
  await page.addScriptTag({path:path.join(__dirname,'capability-workshop.js')});
  await page.waitForFunction(()=>document.getElementById('capability-workshop').getAttribute('aria-busy')==='false');
  await page.evaluate(async()=>{await Axx.chatWorkspace.flush();const render=Axx.commandLibrary.renderOperation.bind(Axx.commandLibrary);Axx.commandLibrary.renderOperation=operation=>{renderedPlans.push(structuredClone(operation));return render(operation);};});
  return {page,errors};
}

async function idle(page){await page.waitForFunction(()=>document.getElementById('capability-workshop').getAttribute('aria-busy')==='false');}
async function generate(page){await page.locator('#cap-goal').fill('Synthetic document-derived goal');await page.locator('#cap-generate').click();await idle(page);}
async function forget(page,id='A'){
  await page.evaluate(async id=>{const chat=chats[id];chat.memory_scope.generation++;chat.connect_id+='-forgotten';chat.context_id=chat.connect_id;await Axx.chatWorkspace.refreshMemory(id,chat.memory_scope);},id);
}
async function openTask(page){
  await page.evaluate(async()=>{const item=makeCapability(undefined,'A','reviewed');capabilities[item.id]=item;
    window.taskPlan={...makePlan({operation_id:'waiting-task-A'}),state:'waiting_capability',request:'PRIVATE_TASK_A',goal_revision:1,
      capability_build:{id:item.id,revision:0,digest:'0'.repeat(64)}};await Axx.capabilityWorkshop.openTask(taskPlan);});
  await idle(page);
}

(async()=>{
  const browser=await launchChromium(chromium),results=[];
  async function test(name,run){let context;try{context=await fixture(browser);await run(context.page);assert.deepEqual(context.errors,[]);assert.deepEqual(await context.page.evaluate(()=>unexpectedRoutes),[]);results.push({name,pass:true});}
    catch(error){results.push({name,pass:false,error:error.stack||String(error)});}finally{await context?.page.close();}}
  try{
    await test('Document details render untrusted text with no input, proposal or execution',async page=>{
      await page.evaluate(()=>Axx.commandLibrary.search());
      await page.waitForFunction(()=>document.querySelector('#command-library-steps button'));
      assert.equal(await page.evaluate(()=>window.injected),undefined);
      assert.match(await page.locator('#command-library-steps').textContent(),/<img src=x/);
      assert.equal(await page.locator('#command-library-steps img').count(),0);
      assert.deepEqual(await page.evaluate(()=>mutations()),[]);
    });
    await test('Use reference opens only the form without POST or inference',async page=>{
      await page.evaluate(()=>Axx.commandLibrary.search());await page.waitForFunction(()=>document.querySelector('#command-library-steps button'));
      await page.locator('#command-library-procedure').evaluate(node=>node.open=true);
      const before=await page.evaluate(()=>calls.filter(call=>call.method==='POST').length);
      await page.locator('#command-library-steps button').click();await idle(page);
      assert.equal(await page.locator('#cap-document-reference').isVisible(),true);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.method==='POST').length),before);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
    });
    await test('Generate carries cloned document identity and captured memory outside definition/context',async page=>{
      await page.evaluate(async()=>{window.caller=structuredClone(procedure);await Axx.capabilityWorkshop.openDocument(caller,'Synthetic source');caller.document_reference.record_sha256='f'.repeat(64);});
      await generate(page);
      const body=await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/capabilities/generate').body);
      assert.deepEqual(body.document_references,[await page.evaluate(()=>documentReference)]);
      assert.deepEqual(body.memory_scope,{task_id:'A',generation:0});assert.equal(body.memory_context_id,'opaque-A');assert.equal(body.conversation_id,'A');
      assert.equal(body.definition,undefined);assert.equal(body.context,undefined);
      assert.match(await page.locator('#cap-editor').textContent(),/Fuentes documentales/);
      assert.match(await page.locator('#cap-editor').textContent(),/2026-10-30/);
    });
    await test('Removing the selected document leaves the next draft without references',async page=>{
      await page.evaluate(()=>Axx.capabilityWorkshop.openDocument(procedure,'Synthetic source'));
      await page.locator('#cap-document-clear').click();await generate(page);
      const body=await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/capabilities/generate').body);
      assert.equal(Object.hasOwn(body,'document_references'),false);
    });
    for(const event of ['forget','switch'])await test('Held generate response cannot publish or issue successors after '+event,async page=>{
      await page.evaluate(()=>Axx.capabilityWorkshop.openDocument(procedure,'Synthetic source'));
      await page.evaluate(()=>hold('/axx-api/capabilities/generate'));
      await page.locator('#cap-goal').fill('Synthetic held generation');await page.locator('#cap-generate').click();
      await page.waitForFunction(()=>releases['/axx-api/capabilities/generate']);
      if(event==='forget')await forget(page);else await page.evaluate(()=>Axx.chatWorkspace.select('B'));
      const count=await page.evaluate(()=>calls.filter(call=>call.route.startsWith('/axx-api/capabilities/')).length);
      await page.evaluate(()=>releases['/axx-api/capabilities/generate']());await idle(page);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.route.startsWith('/axx-api/capabilities/')).length),count);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
      assert.doesNotMatch(await page.locator('#cap-editor').textContent(),/PRIVATE_CAPABILITY_A/);
      assert.deepEqual(await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/capabilities/generate').body.memory_scope),{task_id:'A',generation:0});
      assert.equal(await page.locator('#chat-input').inputValue(),'Independent draft '+(event==='switch'?'B':'A'));
    });
    await test('Invalidating attributable Workshop cache clears both selection and task continuation',async page=>{
      await openTask(page);await forget(page);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
      assert.equal(await page.locator('#cap-list').textContent(),'');
      await page.evaluate(async()=>{await Axx.chatWorkspace.select('B');const item=makeCapability(undefined,'B','reviewed');capabilities[item.id]=item;await Axx.capabilityWorkshop.refresh(item.id);});
      await page.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();await idle(page);
      assert.equal(await page.evaluate(()=>calls.filter(call=>/learning\/(bind-capability|resume)$/.test(call.route)).length),0);
    });
    await test('Forgetting A clears unattributed legacy model cache while preserving human drafts',async page=>{
      await page.evaluate(async()=>{const item=makeCapability();delete item.memory_scope;delete item.memory_context_id;delete item.conversation_id;delete item.memory_dependencies;
        item.definition.title='PRIVATE_LEGACY_MODEL_CACHE';capabilities[item.id]=item;await Axx.capabilityWorkshop.refresh(item.id);
        document.getElementById('cap-goal').value='Independent human capability draft';document.getElementById('chat-input').value='Independent human chat draft A';});
      assert.match(await page.locator('#cap-editor').textContent(),/PRIVATE_LEGACY_MODEL_CACHE/);
      assert.match(await page.locator('#cap-list').textContent(),/PRIVATE_LEGACY_MODEL_CACHE/);
      const posts=await page.evaluate(()=>mutations().length);await forget(page);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
      assert.equal(await page.locator('#cap-editor').textContent(),'');assert.equal(await page.locator('#cap-editor').isHidden(),true);
      assert.equal(await page.locator('#cap-list').textContent(),'');
      assert.equal(await page.locator('#cap-goal').inputValue(),'Independent human capability draft');
      assert.equal(await page.locator('#chat-input').inputValue(),'Independent human chat draft A');
      assert.equal(await page.evaluate(()=>mutations().length),posts);
    });
    await test('Forgetting A preserves independently attributed B capability cache and human drafts',async page=>{
      const before=await page.evaluate(async()=>{const item=makeCapability(undefined,'B');capabilities[item.id]=item;await Axx.capabilityWorkshop.refresh(item.id);
        document.getElementById('cap-goal').value='Independent human capability draft';document.getElementById('chat-input').value='Independent human chat draft A';
        return structuredClone(Axx.capabilityWorkshop.current);});
      const posts=await page.evaluate(()=>mutations().length);await forget(page);
      assert.deepEqual(await page.evaluate(()=>Axx.capabilityWorkshop.current),before);
      assert.match(await page.locator('#cap-editor').textContent(),/PRIVATE_CAPABILITY_B/);
      assert.match(await page.locator('#cap-list').textContent(),/PRIVATE_CAPABILITY_B/);
      assert.equal(await page.locator('#cap-goal').inputValue(),'Independent human capability draft');
      assert.equal(await page.locator('#chat-input').inputValue(),'Independent human chat draft A');
      assert.equal(await page.evaluate(()=>mutations().length),posts);
    });
    for(const typed of [true,false])await test('planAction '+(typed?'typed':'propose')+' forwards references separately and captures identity',async page=>{
      await page.evaluate(typed=>Axx.commandLibrary.planAction('Synthetic plan',{...(typed?{steps:[{command_id:'axx.file.compare',inputs:{path:'left',other_path:'right'}}]}:{context:{explicit:'data'}}),document_references:[documentReference]}),typed);
      const body=await page.evaluate(typed=>calls.find(call=>call.route==='/axx-api/learning/'+(typed?'prepare':'propose')).body,typed);
      assert.deepEqual(body.document_references,[await page.evaluate(()=>documentReference)]);
      assert.deepEqual(body.memory_scope,{task_id:'A',generation:0});assert.equal(body.memory_context_id,'opaque-A');assert.equal(body.conversation_id,'A');
      assert.equal(body.context?.document_references,undefined);assert.equal(body.definition,undefined);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.route.endsWith('/execute')).length),0);
    });
    await test('Held planAction response cannot render A into B',async page=>{
      await page.evaluate(()=>{hold('/axx-api/learning/propose');window.pendingPlan=Axx.commandLibrary.planAction('Synthetic held plan',{document_references:[documentReference]});});
      await page.waitForFunction(()=>releases['/axx-api/learning/propose']);await page.evaluate(()=>Axx.chatWorkspace.select('B'));
      await page.evaluate(()=>{renderedPlans.length=0;releases['/axx-api/learning/propose']();});await page.evaluate(()=>pendingPlan);
      assert.equal(await page.evaluate(()=>renderedPlans.some(plan=>plan?.conversation_id==='A')),false);
      assert.doesNotMatch(await page.locator('#command-library-preview').textContent(),/PRIVATE_PLAN_A/);
    });
    await test('Workshop continuation POSTs retain the entry memory token',async page=>{
      await openTask(page);await page.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();await idle(page);
      const bodies=await page.evaluate(()=>calls.filter(call=>/learning\/(bind-capability|resume)$/.test(call.route)).map(call=>call.body));
      assert.equal(bodies.length,2);for(const body of bodies){assert.deepEqual(body.memory_scope,{task_id:'A',generation:0});assert.equal(body.memory_context_id,'opaque-A');}
    });
    await test('A held bind response followed by forget and switch cannot POST resume',async page=>{
      await openTask(page);await page.evaluate(()=>hold('/axx-api/learning/bind-capability'));
      await page.getByRole('button',{name:'Comprobar resultado y activar',exact:true}).click();await page.waitForFunction(()=>releases['/axx-api/learning/bind-capability']);
      await forget(page);await page.evaluate(()=>Axx.chatWorkspace.select('B'));
      const count=await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/resume').length);
      await page.evaluate(()=>releases['/axx-api/learning/bind-capability']());await idle(page);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/learning/resume').length),count);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
    });
    await test('Held propose list cannot generate or publish an A response after switching to B',async page=>{
      await page.evaluate(()=>{const item=makeCapability();capabilities[item.id]=item;hold('/axx-api/capabilities/list');
        window.pendingProposal=Axx.capabilityWorkshop.propose('Independent human draft A','source_proposal',[documentReference]);});
      await page.waitForFunction(()=>releases['/axx-api/capabilities/list']);
      await page.evaluate(()=>Axx.chatWorkspace.select('B'));
      const posts=await page.evaluate(()=>mutations().length);
      await page.evaluate(()=>releases['/axx-api/capabilities/list']());await page.evaluate(()=>pendingProposal);await idle(page);
      assert.equal(await page.evaluate(()=>mutations().length),posts);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/capabilities/generate').length),0);
      assert.equal(await page.evaluate(()=>Axx.capabilityWorkshop.current),null);
      assert.doesNotMatch(await page.locator('#cap-list').textContent(),/PRIVATE_CAPABILITY_A/);
      assert.doesNotMatch(await page.locator('#cap-editor').textContent(),/PRIVATE_CAPABILITY_A/);
      assert.equal(await page.locator('#cap-goal').inputValue(),'Independent human draft A');
      assert.equal(await page.locator('#chat-input').inputValue(),'Independent draft B');
    });
    await test('Missing-capability fallback preserves the original cloned references outside context',async page=>{
      await page.evaluate(()=>{window.capabilityMissing=true;window.callerRefs=[structuredClone(documentReference)];hold('/axx-api/learning/propose');
        window.fallbackPlan=Axx.commandLibrary.planAction('crea un procedimiento para comparar archivos',{
          document_references:callerRefs,context:{explicit:'Synthetic context'}});});
      await page.waitForFunction(()=>releases['/axx-api/learning/propose']);
      await page.evaluate(()=>{callerRefs[0].record_sha256='f'.repeat(64);releases['/axx-api/learning/propose']();});
      await page.evaluate(()=>fallbackPlan);await idle(page);
      const reference=await page.evaluate(()=>documentReference);
      const proposal=await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/learning/propose').body);
      const generation=await page.evaluate(()=>calls.find(call=>call.route==='/axx-api/capabilities/generate')?.body);
      assert.ok(generation,'The missing capability must reach the real Workshop fallback');
      assert.deepEqual(proposal.document_references,[reference]);assert.equal(proposal.context.document_references,undefined);
      assert.deepEqual(generation.document_references,[reference]);assert.equal(generation.context,undefined);assert.equal(generation.definition,undefined);
      assert.deepEqual(generation.memory_scope,{task_id:'A',generation:0});assert.equal(generation.memory_context_id,'opaque-A');
      assert.equal(generation.kind,'source_proposal');
      assert.equal(await page.locator('#cap-document-reference').isVisible(),true);
      assert.equal(await page.evaluate(()=>calls.filter(call=>call.route.endsWith('/execute')).length),0);
    });
    await test('A generic propose clears a prior document selection for generation and the next form submit',async page=>{
      await page.evaluate(()=>Axx.capabilityWorkshop.openDocument(procedure,'Synthetic prior source'));
      assert.equal(await page.locator('#cap-document-reference').isVisible(),true);
      await page.evaluate(()=>Axx.capabilityWorkshop.propose('Synthetic generic proposal','source_proposal'));await idle(page);
      assert.equal(await page.locator('#cap-document-reference').isVisible(),false);
      assert.equal(await page.locator('#cap-document-clear').isVisible(),false);
      let body=await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/capabilities/generate').at(-1).body);
      assert.equal(Object.hasOwn(body,'document_references'),false);
      assert.equal(await page.locator('#cap-kind').inputValue(),'source_proposal');
      await generate(page);
      body=await page.evaluate(()=>calls.filter(call=>call.route==='/axx-api/capabilities/generate').at(-1).body);
      assert.equal(Object.hasOwn(body,'document_references'),false);
      assert.deepEqual(await page.evaluate(()=>Axx.capabilityWorkshop.current.document_references),[]);
    });
  }finally{await browser.close();}
  console.log(JSON.stringify({pass:results.filter(result=>result.pass).length,fail:results.filter(result=>!result.pass).length,total:results.length,results},null,2));
  if(results.some(result=>!result.pass))process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
