/* Controlled DOM/transport checks of the shipped operational module. No browser or PC effects. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../js/mission-continuity.js'),'utf8');
const copy=value=>JSON.parse(JSON.stringify(value));
const pendingKey='axx.missionContinuity.pending';
const tick=async()=>{for(let index=0;index<8;index++)await new Promise(resolve=>setImmediate(resolve));};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function mission(id='mission-a',overrides={}){
  return {operation_id:id,conversation_id:'shared-chat',project_id:'project-a',state:'awaiting_approval',executor:'pc',goal_revision:2,plan_hash:'original-hash-'+id,
    goal_spec:{intent:'Guardar entrega',destination:'C:\\Proyecto A\\entrega.txt',checks:[{path:'original.txt',text:'exacto'}],criteria:[{id:'final',check:'file_contains',parameters:{path:'original.txt',text:'exacto'}}],preserve:['origen']},
    mission:{objective:'Guardar entrega',destination:'C:\\Proyecto A\\entrega.txt',verified_steps:[0],completed:false},
    memory_scope:{task_id:'chat-internal',generation:0},memory_context_id:'opaque-private-memory-token',can_correct:true,correction_reason:'',...overrides};
}
function fixture(storage=new Map()){
  const nodes=new Map(),listeners=new Map();
  class Element{
    constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.events={};this.attributes={};this.style={};this.hidden=false;this.disabled=false;this.value='';this.open=false;this._text='';}
    set id(id){this._id=id;nodes.set(id,this);}get id(){return this._id;}
    set textContent(text){this._text=String(text);this.children=[];}get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
    append(...children){this.children.push(...children);for(const child of children)child.parentNode=this;}
    replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
    setAttribute(key,value){this.attributes[key]=String(value);}
    addEventListener(name,callback){(this.events[name]??=[]).push(callback);}
    dispatch(name){for(const callback of this.events[name]||[])callback({target:this});}
    click(){if(!this.disabled)this.onclick?.();}
  }
  const activity=new Element('details');activity.id='work-activity';
  const state={profile:{paired:true,device_id:'phone-original',fingerprint:'a'.repeat(64)},missions:[mission()],calls:[],post:null,getReceipt:null,getDetail:null,profileHook:null,storageFailure:false};
  const localStorage={get length(){return storage.size;},key:index=>[...storage.keys()][index]??null,getItem:key=>storage.get(key)??null,setItem(key,value){if(state.storageFailure)throw Error('storage unavailable');storage.set(key,String(value));},removeItem:key=>storage.delete(key)};
  const envelope=(body,extra={})=>({command_id:body.command_id,operation_id:body.operation_id,conversation_id:body.conversation_id,from_plan_hash:body.plan_hash,from_goal_revision:body.goal_revision,executor:'pc',state:'confirmed',
    receipt:{id:'derived-correction-id',request_hash:'canonical-request-hash',origin_device_id:'phone-original',from_plan_hash:body.plan_hash,from_goal_revision:body.goal_revision,plan_hash:'review-in-pc-hash',goal_revision:body.goal_revision+1,state:'awaiting_approval'},...extra});
  const transport={profile:async()=>{if(state.profileHook)await state.profileHook();return copy(state.profile);},request:async args=>{
    assert.equal(args.expected_device_id,state.profile.device_id,'Every request pins the original device');
    assert.equal(args.expected_fingerprint,state.profile.fingerprint,'Every request pins the original PC fingerprint');
    state.calls.push(copy(args));
    if(args.path.startsWith('/v1/work/missions?')){
      const conversation=new URL('https://fixture'+args.path).searchParams.get('conversation_id');
      return {data:{executor:'pc',conversation_id:conversation,missions:state.missions.filter(value=>value.conversation_id===conversation).map(copy)}};
    }
    if(args.path.startsWith('/v1/work/mission?')){
      const id=new URL('https://fixture'+args.path).searchParams.get('operation_id');
      return {data:state.getDetail?await state.getDetail(id):copy(state.missions.find(item=>item.operation_id===id))};
    }
    if(args.path==='/v1/work/mission-correct'){
      assert.deepEqual(JSON.parse(storage.get(pendingKey)).body,copy(args.body),'Tracking is durable before the first POST');
      return {data:state.post?await state.post(args.body):envelope(args.body)};
    }
    if(args.path.startsWith('/v1/work/mission-correction?')){
      const body=JSON.parse(storage.get(pendingKey)).body;
      return {data:state.getReceipt?await state.getReceipt(body):envelope(body,{state:'outcome_unknown',receipt:undefined})};
    }
    throw Error('Unexpected endpoint '+args.path);
  }};
  const window={Capacitor:{Plugins:{AxxTransport:transport}},confirm:()=>true,addEventListener(name,callback){(listeners.get(name)||listeners.set(name,[]).get(name)).push(callback);}};
  let serial=0;vm.runInNewContext(source,{window,document:{getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag)},localStorage,crypto:{randomUUID:()=>`request-${++serial}`},console});
  const emit=(name,detail)=>{for(const listener of listeners.get(name)||[])listener({detail});};
  const snapshot=(overrides={})=>emit('axxSnapshot',{...copy(state.profile),conversation_id:'shared-chat',scopes:['tools.control'],capabilities:{mission_continuity:true},...overrides});
  const by=id=>{assert.ok(nodes.has(id),'Expected real module control '+id);return nodes.get(id);};
  const buttons=(node,text)=>node.children.flatMap(child=>[...(child.tagName==='BUTTON'&&(!text||child.textContent===text)?[child]:[]),...buttons(child,text)]);
  const open=async(id='mission-a')=>{snapshot();const panel=by('mission-continuity');panel.open=true;panel.dispatch('toggle');await tick();const row=by('mission-list').children.find(row=>row.textContent.includes('Misión '+id+' '));assert.ok(row);buttons(row,'Abrir misión')[0].click();await tick();};
  const edit=(id,value)=>{by(id).value=value;by(id).oninput();};
  const review=()=>{edit('mission-correction','Cambiar destino y criterio final según el contrato revisado');by('mission-review').click();assert.equal(by('mission-reviewed').hidden,false);};
  return {state,storage,by,buttons,open,edit,review,snapshot,emit,envelope};
}

async function reachableSameMission(){
  const f=fixture();await f.open();
  assert.match(f.by('mission-progress').textContent,/1 pasos con recibo y postcondiciones/);
  assert.match(f.by('mission-destination').textContent,/Proyecto A/);
  const goal=JSON.parse(f.by('mission-goal').value);goal.destination='C:\\Proyecto B\\entrega.txt';goal.checks[0].path='final.txt';goal.criteria[0].parameters.path='final.txt';
  f.edit('mission-goal',JSON.stringify(goal));f.review();
  const reviewed=JSON.parse(f.by('mission-review-json').value);assert.deepEqual(reviewed.goal_spec,goal);
  assert.equal(f.by('mission-review-json').value.includes('opaque-private-memory-token'),false);
  assert.equal(f.by('mission-continuity').textContent.includes('opaque-private-memory-token'),false);
  f.by('mission-prepare').click();await tick();
  const posts=f.state.calls.filter(call=>call.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(Object.keys(posts[0].body).sort(),['command_id','operation_id','conversation_id','plan_hash','goal_revision','text','goal_spec','memory_scope','memory_context_id'].sort());
  assert.equal(posts[0].body.operation_id,'mission-a');assert.equal(posts[0].body.conversation_id,'shared-chat');assert.equal(posts[0].body.goal_revision,2);assert.equal(posts[0].body.plan_hash,'original-hash-mission-a');
  assert.deepEqual(posts[0].body.goal_spec,goal);assert.deepEqual(posts[0].body.memory_scope,{task_id:'chat-internal',generation:0});assert.equal(posts[0].body.memory_context_id,'opaque-private-memory-token');
  assert.match(f.by('mission-status').textContent,/Preparado; revisar y aprobar en PC/);assert.match(f.by('mission-status').textContent,/No confirma ejecución/);assert.equal(f.storage.has(pendingKey),false);
  f.by('mission-pc-review').click();assert.match(f.by('mission-status').textContent,/aprobación y ejecución se realizan en la PC/);
  assert.equal(f.state.calls.some(call=>/execute|approve|commands|provider/.test(call.path)),false);
}
async function exactLabelsAndStableDrafts(){
  const f=fixture();f.state.missions.push(mission('mission-b',{goal_spec:{intent:'Otro',destination:'D:\\Proyecto B\\entrega.txt'},mission:{objective:'Otra misión',destination:'D:\\Proyecto B\\entrega.txt'}}));await f.open();
  assert.match(f.by('mission-list').textContent,/C:\\Proyecto A\\entrega.txt/);assert.match(f.by('mission-list').textContent,/D:\\Proyecto B\\entrega.txt/);
  f.edit('mission-goal','{"intent":"Borrador estable","destination":"E:\\\\propio.txt","criteria":[]}');f.review();
  assert.equal(f.by('mission-prepare').disabled,false);f.edit('mission-correction','Segundo borrador');assert.equal(f.by('mission-prepare').disabled,true);assert.equal(f.by('mission-reviewed').hidden,true);
  const original=f.by('mission-goal').value;f.by('mission-refresh').click();f.snapshot();await tick();assert.equal(f.by('mission-goal').value,original);assert.equal(f.by('mission-correction').value,'Segundo borrador');
  const reloaded=fixture(f.storage);await reloaded.open();assert.equal(reloaded.by('mission-goal').value,original);assert.equal(reloaded.by('mission-correction').value,'Segundo borrador');assert.equal(reloaded.by('mission-prepare').disabled,true);
}
async function staleRevisionAndMemory(){
  for(const update of [value=>value.goal_revision++,value=>value.plan_hash='different',value=>value.memory_scope.generation++,value=>value.memory_context_id='new-token',value=>value.memory_forgotten=true,value=>value.can_correct=false]){
    const f=fixture();await f.open();f.review();update(f.state.missions[0]);f.by('mission-prepare').click();await tick();
    assert.equal(f.state.calls.filter(call=>call.method==='POST').length,0);assert.equal(f.by('mission-prepare').disabled,true);assert.match(f.by('mission-status').textContent,f.state.missions[0].memory_forgotten?/La memoria se olvidó/:/Cambió la misión/);
  }
  const f=fixture();await f.open();f.review();f.state.missions[0].goal_revision++;f.by('mission-refresh').click();await tick();assert.equal(f.by('mission-prepare').disabled,true);assert.match(f.by('mission-status').textContent,/revisión o memoria de la PC cambió/);
}
async function lostAckAndReload(){
  const f=fixture();await f.open();f.review();f.state.post=()=>{throw Error('connection lost');};f.by('mission-prepare').click();await tick();assert.ok(f.storage.has(pendingKey));
  const original=JSON.parse(f.storage.get(pendingKey));assert.equal(f.by('mission-prepare').disabled,true);
  const reload=fixture(f.storage);await reload.open();assert.equal(reload.state.calls.some(call=>call.method==='POST'),false);assert.ok(reload.state.calls.some(call=>call.path.includes('mission-correction?command_id='+original.body.command_id)));assert.ok(reload.storage.has(pendingKey));
  reload.state.getReceipt=()=>null;reload.by('mission-reconcile').click();await tick();assert.ok(reload.storage.has(pendingKey));assert.match(reload.by('mission-status').textContent,/sigue pendiente/);
  reload.by('mission-review').click();reload.by('mission-prepare').click();await tick();assert.equal(reload.state.calls.some(call=>call.method==='POST'),false);
  reload.state.getReceipt=body=>reload.envelope(body);reload.by('mission-reconcile').click();await tick();assert.equal(reload.storage.has(pendingKey),false);assert.match(reload.by('mission-status').textContent,/revisión 3/);
}
async function bindingChangePreservesTracking(){
  const f=fixture();await f.open();f.review();f.state.post=()=>{throw Error('lost ACK');};f.by('mission-prepare').click();await tick();const original=f.storage.get(pendingKey),count=f.state.calls.length;
  f.state.profile={paired:true,device_id:'different-phone',fingerprint:'b'.repeat(64)};f.snapshot();await tick();f.by('mission-reconcile').click();await tick();
  assert.equal(f.state.calls.length,count,'No mission request may go to a newly paired PC while old tracking exists');assert.equal(f.storage.get(pendingKey),original);
  f.by('mission-forget').click();await tick();assert.equal(f.storage.has(pendingKey),false);assert.equal(f.state.calls.length,count,'Forgetting tracking has no cancellation or execution effect');
}
async function reconcileOriginalWhilePcMultitasks(){
  const f=fixture();f.state.missions.push(mission('mission-b',{conversation_id:'other-shared-chat',goal_spec:{intent:'Trabajo B',destination:'D:\\Proyecto B\\salida.txt',criteria:[]},memory_scope:{task_id:'chat-b-internal',generation:0},memory_context_id:'opaque-chat-b-token'}));
  await f.open();f.review();f.state.post=()=>{throw Error('lost ACK');};f.by('mission-prepare').click();await tick();
  const original=JSON.parse(f.storage.get(pendingKey));
  f.snapshot({conversation_id:'other-shared-chat'});await tick();
  assert.equal(f.state.calls.filter(call=>call.path.includes('mission-correction?')).length,0,'Switching chats does not retarget background polling');
  f.buttons(f.by('mission-list').children[0],'Abrir misión')[0].click();await tick();
  f.edit('mission-correction','Borrador de la misión B');const goalB=f.by('mission-goal').value,identityB=f.by('mission-identity').textContent;
  const callsBefore=f.state.calls.length;f.state.getReceipt=body=>f.envelope(body);f.by('mission-reconcile').click();await tick();
  assert.equal(f.storage.has(pendingKey),false);assert.match(f.by('mission-status').textContent,/Misma misión mission-a/);assert.match(f.by('mission-status').textContent,/Preparado; revisar y aprobar en PC/);
  assert.equal(f.by('mission-goal').value,goalB);assert.equal(f.by('mission-correction').value,'Borrador de la misión B');assert.equal(f.by('mission-identity').textContent,identityB);assert.equal(f.by('mission-review').disabled,false,'Settling A does not invalidate editor B');
  assert.deepEqual(f.state.calls.slice(callsBefore).map(call=>[call.method,call.path]),[['GET','/v1/work/mission-correction?command_id='+original.body.command_id]]);
  assert.equal(f.state.calls.filter(call=>call.method==='POST').length,1,'Manual recovery never resubmits the original request');

  for(const blocked of ['permission','forgotten']){
    const scoped=fixture();await scoped.open();scoped.review();scoped.state.post=()=>{throw Error('lost ACK');};scoped.by('mission-prepare').click();await tick();const saved=scoped.storage.get(pendingKey);
    scoped.snapshot({conversation_id:'other-shared-chat'});await tick();
    scoped.state.getReceipt=body=>{if(blocked==='permission')throw Error('permission denied for original chat');return scoped.envelope(body,{state:'outcome_unknown',memory_forgotten:true,receipt:undefined});};
    scoped.by('mission-reconcile').click();await tick();if(blocked==='permission')assert.equal(scoped.storage.get(pendingKey),saved);else assert.equal(JSON.parse(scoped.storage.get(pendingKey)).body.goal_spec,undefined);assert.doesNotMatch(scoped.by('mission-status').textContent,/Preparado/);
    if(blocked==='forgotten')assert.match(scoped.by('mission-status').textContent,/contexto original ya no está disponible/);
    const scopedTracking=scoped.storage.get(pendingKey),count=scoped.state.calls.length;scoped.snapshot({conversation_id:'other-shared-chat',scopes:['query']});scoped.by('mission-reconcile').click();await tick();assert.equal(scoped.state.calls.length,count);assert.equal(scoped.storage.get(pendingKey),scopedTracking);
  }
}
async function deniedAndForgotten(){
  const denied=fixture();denied.snapshot({scopes:['query']});denied.by('mission-continuity').open=true;denied.by('mission-continuity').dispatch('toggle');await tick();assert.equal(denied.state.calls.length,0);assert.equal(denied.by('mission-refresh').disabled,true);
  const forgotten=fixture();forgotten.state.missions=[mission('mission-a',{memory_forgotten:true,can_correct:false,goal_spec:undefined,memory_scope:undefined,memory_context_id:undefined})];await forgotten.open();assert.equal(forgotten.by('mission-editor').hidden,true);assert.match(forgotten.by('mission-status').textContent,/memoria se olvidó/);
  const deniedRead=fixture();await deniedRead.open();deniedRead.review();deniedRead.state.getDetail=()=>{throw Error('permission denied');};deniedRead.by('mission-prepare').click();await tick();assert.equal(deniedRead.state.calls.some(call=>call.method==='POST'),false);assert.match(deniedRead.by('mission-status').textContent,/Aprueba el acceso/);
  const unavailableStorage=fixture();await unavailableStorage.open();unavailableStorage.review();unavailableStorage.state.storageFailure=true;unavailableStorage.by('mission-prepare').click();await tick();assert.equal(unavailableStorage.state.calls.some(call=>call.method==='POST'),false);
}
async function forgottenContentLeavesOnlyReconciliationHeaders(){
  const f=fixture(),canary='FORGOTTEN_MOBILE_CONTENT_4391';await f.open();
  f.edit('mission-correction',canary);f.by('mission-review').click();
  f.state.post=()=>{throw Error('lost ACK');};f.by('mission-prepare').click();await tick();
  const original=JSON.parse(f.storage.get(pendingKey)),otherKey='axx.missionContinuity.draft.'+JSON.stringify([original.binding,'other-mission',1,'other-hash']);
  f.storage.set(otherKey,'unrelated draft');
  assert.ok([...f.storage.values()].some(value=>value.includes(canary)),'Authorized draft was persisted before forgetting');
  f.state.getReceipt=body=>f.envelope(body,{state:'outcome_unknown',memory_forgotten:true,receipt:undefined});
  f.by('mission-reconcile').click();await tick();
  assert.equal([...f.storage.entries()].some(([key,value])=>(key+value).includes(canary)),false,'Known forgetting removes the owned mobile content');
  assert.equal([...f.storage.keys()].some(key=>key.includes('opaque-private-memory-token')),false,'All revisions of the original draft lose their source binding');
  const pending=JSON.parse(f.storage.get(pendingKey));
  assert.deepEqual(Object.keys(pending.body).sort(),['command_id','conversation_id','goal_revision','operation_id','plan_hash']);
  assert.equal(pending.body.command_id,original.body.command_id);assert.equal(pending.body.operation_id,original.body.operation_id);
  assert.equal(pending.draft,undefined);assert.equal(f.storage.get(otherKey),'unrelated draft');
  assert.equal(f.by('mission-goal').value,'');assert.equal(f.by('mission-correction').value,'');assert.equal(f.by('mission-review-json').value,'');
  assert.equal(f.by('mission-editor').hidden,true);assert.equal(f.state.calls.filter(call=>call.method==='POST').length,1);
  const loaded=fixture(f.storage);loaded.snapshot();await tick();assert.equal(loaded.state.calls.filter(call=>call.method==='POST').length,0);
}
async function forgettingFencesHeldReadsAndPreservesOtherProject(){
  for(const active of ['original','other-project']){
    const f=fixture();await f.open();f.edit('mission-correction','FORGOTTEN_PROJECT_A');f.by('mission-review').click();
    f.state.post=()=>{throw Error('lost ACK');};f.by('mission-prepare').click();await tick();
    let held,otherGoal;
    if(active==='original'){
      held=deferred();f.state.getDetail=()=>held.promise;f.buttons(f.by('mission-list').children[0],'Abrir misión')[0].click();await tick();
    }else{
      f.state.missions.push(mission('mission-b',{conversation_id:'other-shared-chat',memory_scope:{task_id:'other-shared-chat',policy:'internal',generation:0},memory_context_id:'other-private-context'}));
      f.snapshot({conversation_id:'other-shared-chat'});await tick();f.buttons(f.by('mission-list').children[0],'Abrir misión')[0].click();await tick();
      f.edit('mission-correction','KEEP_PROJECT_B');otherGoal=f.by('mission-goal').value;
    }
    f.state.getReceipt=body=>f.envelope(body,{state:'outcome_unknown',memory_forgotten:true,receipt:undefined});
    f.by('mission-reconcile').click();await tick();if(held){held.resolve(mission());await tick();}
    assert.equal([...f.storage.values()].some(value=>value.includes('FORGOTTEN_PROJECT_A')),false);
    if(held){assert.equal(f.by('mission-editor').hidden,true);assert.equal(f.by('mission-goal').value,'');}
    else{assert.equal(f.by('mission-goal').value,otherGoal);assert.equal(f.by('mission-correction').value,'KEEP_PROJECT_B');assert.ok([...f.storage.values()].some(value=>value.includes('KEEP_PROJECT_B')));}
    assert.equal(f.state.calls.filter(call=>call.method==='POST').length,1);
  }
}
async function heldCallbacks(){
  const f=fixture();f.state.missions.push(mission('mission-b'));await f.open();
  const held=deferred();f.state.getDetail=id=>id==='mission-a'?held.promise:copy(f.state.missions.find(value=>value.operation_id===id));
  f.buttons(f.by('mission-list').children[0],'Abrir misión')[0].click();await tick();f.buttons(f.by('mission-list').children[1],'Abrir misión')[0].click();await tick();assert.match(f.by('mission-identity').textContent,/mission-b/);held.resolve(mission('mission-a'));await tick();assert.match(f.by('mission-identity').textContent,/mission-b/);
  const post=fixture();await post.open();post.review();const response=deferred();let body;post.state.post=value=>{body=copy(value);return response.promise;};post.by('mission-prepare').click();await tick();post.edit('mission-correction','Borrador nuevo durante respuesta antigua');response.resolve(post.envelope(body));await tick();assert.ok(post.storage.has(pendingKey));assert.equal(post.by('mission-correction').value,'Borrador nuevo durante respuesta antigua');assert.doesNotMatch(post.by('mission-status').textContent,/Preparado/);
  for(const change of [value=>value.goal_revision++,value=>value.memory_forgotten=true]){
    const changed=fixture();await changed.open();changed.review();const response=deferred();let original;changed.state.post=value=>{original=copy(value);return response.promise;};changed.by('mission-prepare').click();await tick();change(changed.state.missions[0]);changed.by('mission-refresh').click();await tick();response.resolve(changed.envelope(original));await tick();assert.ok(changed.storage.has(pendingKey));assert.match(changed.by('mission-status').textContent,changed.state.missions[0].memory_forgotten?/memoria de esta misión se olvidó/:/revisión o memoria/);assert.doesNotMatch(changed.by('mission-status').textContent,/Preparado/);
  }
  const switchPc=fixture();await switchPc.open();switchPc.review();const failure=deferred();switchPc.state.post=()=>failure.promise;switchPc.by('mission-prepare').click();await tick();switchPc.state.profile={paired:true,device_id:'other',fingerprint:'c'.repeat(64)};switchPc.snapshot();await tick();const status=switchPc.by('mission-status').textContent;failure.reject(Error('OLD_PRIVATE_ERROR'));await tick();assert.equal(switchPc.by('mission-status').textContent,status);assert.ok(switchPc.storage.has(pendingKey));
}
async function receiptMustMatch(){
  for(const alter of [value=>value.command_id='another-request',value=>value.from_plan_hash='other',value=>value.receipt.origin_device_id='another-device',value=>value.receipt.goal_revision=2,value=>delete value.receipt.request_hash]){
    const f=fixture();await f.open();f.review();f.state.post=body=>{const value=f.envelope(body);alter(value);return value;};f.by('mission-prepare').click();await tick();assert.ok(f.storage.has(pendingKey));assert.doesNotMatch(f.by('mission-status').textContent,/Preparado/);
  }
  for(const state of ['needs_input','failed']){
    const f=fixture();await f.open();f.review();f.state.post=body=>{const value=f.envelope(body);value.receipt.state=state;return value;};f.by('mission-prepare').click();await tick();assert.match(f.by('mission-status').textContent,new RegExp('estado '+state));assert.doesNotMatch(f.by('mission-status').textContent,/Preparado/);
  }
}
function wiring(){
  assert.match(fs.readFileSync(path.join(__dirname,'../client.html'),'utf8'),/src="js\/mission-continuity.js"/);
  assert.match(fs.readFileSync(path.join(__dirname,'../build.mjs'),'utf8'),/copyFile\(new URL\('js\/mission-continuity.js'/);
  const live=fs.readFileSync(path.join(__dirname,'../js/live-client.js'),'utf8');assert.match(live,/fingerprint:currentFingerprint,conversation_id:snapshot.conversation_id/);assert.equal(live.includes('axx.missionContinuity.'),false,'Legacy pairing cleanup cannot erase mission drafts or tracking');
}
(async()=>{for(const test of [reachableSameMission,exactLabelsAndStableDrafts,staleRevisionAndMemory,lostAckAndReload,bindingChangePreservesTracking,reconcileOriginalWhilePcMultitasks,deniedAndForgotten,forgottenContentLeavesOnlyReconciliationHeaders,forgettingFencesHeldReadsAndPreservesOtherProject,heldCallbacks,receiptMustMatch]){await test();console.log('PASS '+test.name);}wiring();console.log('PASS operational wiring; controlled VM only');})().catch(error=>{console.error(error);process.exitCode=1;});
