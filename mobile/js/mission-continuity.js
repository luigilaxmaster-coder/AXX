/* The phone reviews the PC's existing mission; only the PC can approve its effects. */
(()=>{
  'use strict';
  const transport=window.Capacitor?.Plugins?.AxxTransport,host=document.getElementById('work-activity');
  if(!host)return;
  const namespace='axx.missionContinuity.',clone=value=>JSON.parse(JSON.stringify(value));
  const canonical=value=>JSON.stringify(value,(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  const element=(tag,text,id)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(id)node.id=id;return node;};
  const button=(text,id,action)=>{const node=element('button',text,id);node.type='button';node.onclick=action;return node;};
  const panel=element('details',undefined,'mission-continuity'),summary=element('summary','Misiones de la PC');
  const status=element('p','Abre una misión para revisar su objetivo y destino.','mission-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const list=element('div',undefined,'mission-list'),editor=element('section',undefined,'mission-editor');editor.hidden=true;
  const identity=element('p',undefined,'mission-identity'),destination=element('p',undefined,'mission-destination'),progress=element('p',undefined,'mission-progress');
  const goalLabel=element('label','Objetivo completo (JSON): revisa destino, comprobaciones y criterios');goalLabel.htmlFor='mission-goal';
  const goal=element('textarea',undefined,'mission-goal');goal.rows=10;goal.maxLength=32768;goal.spellcheck=false;
  const reasonLabel=element('label','Corrección que debe preparar la PC');reasonLabel.htmlFor='mission-correction';
  const reason=element('textarea',undefined,'mission-correction');reason.rows=3;reason.maxLength=4000;
  const reviewPanel=element('details',undefined,'mission-reviewed');reviewPanel.hidden=true;
  const reviewedLabel=element('label','Contenido exacto revisado');reviewedLabel.htmlFor='mission-review-json';
  const reviewed=element('textarea',undefined,'mission-review-json');reviewed.readOnly=true;reviewed.rows=10;
  reviewPanel.append(element('summary','Revisión exacta antes de preparar'),reviewedLabel,reviewed);
  let online=false,snapshot=null,snapshotKey='',detail=null,binding=null,selection=0,selectedOperation='',epoch=0,review=null,draftKey='',pending=null,checking=false,sending=false,loading=false,stale=false;
  try{pending=JSON.parse(localStorage.getItem(namespace+'pending')||'null');}catch{}
  if(pending&&(!pending.body?.command_id||!pending.binding?.device_id||!pending.binding?.fingerprint))pending=null;
  const refreshButton=button('Actualizar misiones','mission-refresh',()=>void refresh());
  const reviewButton=button('Revisar corrección','mission-review',reviewCorrection);
  const prepareButton=button('Preparar en la misma misión','mission-prepare',()=>void prepare());prepareButton.className='primary';
  prepareButton.style.minWidth='min-content';
  const checkButton=button('Consultar corrección pendiente','mission-reconcile',()=>void reconcile(true));
  const forgetButton=button('Olvidar seguimiento','mission-forget',()=>{
    if(!pending||!window.confirm('Esto elimina solo el seguimiento local. No cancela la corrección ni los efectos en la PC. Revisa esa PC antes de volver a enviarla.'))return;
    localStorage.removeItem(namespace+'pending');pending=null;epoch++;review=null;paint();status.textContent='Seguimiento local olvidado. Revisa la misión en la PC antes de repetir.';
  });
  const pcButton=button('Revisar y continuar en la PC','mission-pc-review',()=>{
    if(detail)status.textContent='En Axx de la PC, abre la misión '+detail.operation_id+' en Actividad. Revisa su revisión y hash; la aprobación y ejecución se realizan en la PC.';
  });
  const actions=element('div');actions.className='actions';actions.append(reviewButton,prepareButton,pcButton);
  const tracking=element('div');tracking.className='actions';tracking.append(checkButton,forgetButton);
  editor.append(identity,destination,progress,goalLabel,goal,reasonLabel,reason,reviewPanel,actions);
  panel.append(summary,element('p','Mismo objetivo y operación de la PC. Una corrección prepara una revisión; sus efectos requieren revisión y aprobación en la PC.'),refreshButton,status,tracking,list,editor);host.append(panel);

  const available=()=>online&&snapshot?.capabilities?.mission_continuity===true&&snapshot?.scopes?.includes('tools.control')&&snapshot?.conversation_id&&snapshot.conversation_id!=='main';
  const sameBinding=(a,b)=>!!a&&!!b&&a.device_id===b.device_id&&a.fingerprint===b.fingerprint;
  const missionContext=value=>canonical({operation_id:value.operation_id,conversation_id:value.conversation_id,goal_revision:value.goal_revision,plan_hash:value.plan_hash,memory_scope:value.memory_scope,memory_context_id:value.memory_context_id,goal_spec:value.goal_spec});
  const validDetail=value=>value?.executor==='pc'&&typeof value.operation_id==='string'&&value.conversation_id===snapshot?.conversation_id&&Number.isSafeInteger(value.goal_revision)&&value.goal_revision>0&&typeof value.plan_hash==='string'&&value.plan_hash.length>0;
  const current=(ticket,original)=>ticket===epoch&&available()&&sameBinding(original,binding)&&snapshot.device_id===original.device_id&&snapshot.fingerprint===original.fingerprint;
  function forgetContent(operationId,original){
    if(selectedOperation===operationId&&sameBinding(binding||{},original)){
      epoch++;selection++;selectedOperation='';detail=null;review=null;draftKey='';stale=true;
      goal.value=reason.value=reviewed.value='';identity.textContent=destination.textContent=progress.textContent='';
      editor.hidden=reviewPanel.hidden=true;
    }
    let failed=false;
    if(pending?.body.operation_id===operationId&&sameBinding(pending.binding,original)){
      pending={binding:clone(original),body:Object.fromEntries(['command_id','operation_id','conversation_id','plan_hash','goal_revision'].map(key=>[key,pending.body[key]])),memory_forgotten:true};
      try{localStorage.setItem(namespace+'pending',JSON.stringify(pending));}
      catch{failed=true;try{localStorage.removeItem(namespace+'pending');}catch{}}
    }
    try{
      for(const key of Array.from({length:localStorage.length},(_,index)=>localStorage.key(index))){
        if(!key?.startsWith(namespace+'draft.'))continue;
        let source;try{source=JSON.parse(key.slice((namespace+'draft.').length));}catch{continue;}
        if(Array.isArray(source)&&source[1]===operationId&&sameBinding(source[0]||{},original)){
          try{localStorage.removeItem(key);}catch{failed=true;}
        }
      }
    }catch{failed=true;}
    if(failed){const error=Object.assign(Error('Local forgetting incomplete'),{code:'forget_storage'});status.textContent=errorMessage(error);paint();throw error;}
    status.textContent='La memoria de esta misión se olvidó; se depuró su contenido local.';
  }
  function paint(){
    panel.hidden=snapshot?.capabilities?.mission_continuity!==true;
    refreshButton.disabled=!available()||loading;
    reviewButton.disabled=!available()||!detail||detail.can_correct!==true||stale||!!pending||sending;
    prepareButton.disabled=reviewButton.disabled||!review;
    checkButton.hidden=forgetButton.hidden=!pending;checkButton.disabled=!available()||checking||sending;
    pcButton.disabled=!detail;
  }
  function errorMessage(error){
    if(error?.code==='forget_storage')return 'No se pudo depurar todo el contenido local. Revisa el almacenamiento de este teléfono; no repitas la operación.';
    const text=String(error?.code||'')+' '+String(error?.message||error||'');
    if(/memory|forgot|context|olvid/i.test(text))return 'La memoria o el contexto cambió. Vuelve a abrir la misión; se conserva tu borrador.';
    if(/scope|permission|denied|403|unauthor|tools.control/i.test(text))return 'Aprueba el acceso a herramientas y al historial de este chat en la PC.';
    if(/binding|enlace|paired|fingerprint/i.test(text))return 'Cambió el enlace. Vuelve a la PC original para consultar el seguimiento pendiente.';
    return 'No se confirmó la respuesta de la PC. Se conserva el borrador y el seguimiento; consulta antes de repetir.';
  }
  async function profile(original){
    if(!transport)throw Error('paired');
    const value=await transport.profile();
    if(!value.paired||!value.device_id||!value.fingerprint||!sameBinding(value,original)||snapshot?.device_id!==value.device_id||snapshot?.fingerprint!==value.fingerprint)throw Error('binding');
    if(pending&&!sameBinding(value,pending.binding))throw Error('binding');
    return value;
  }
  async function api(path,body,original,ticket=epoch){
    await profile(original);
    if(!current(ticket,original))throw Error('context');
    const response=await transport.request({path:'/v1/work/'+path,method:body===undefined?'GET':'POST',expected_device_id:original.device_id,expected_fingerprint:original.fingerprint,...(body===undefined?{}:{body})});
    await profile(original);
    if(response.data?.error){const error=Error(response.data.error.message||response.data.error);error.code=response.data.error.code;throw error;}
    return response.data;
  }
  function saveDraft(){
    if(!draftKey)return;
    localStorage.setItem(namespace+'draft.'+draftKey,JSON.stringify({goal:goal.value,text:reason.value}));
  }
  function invalidateReview(){
    epoch++;review=null;reviewPanel.hidden=true;reviewed.value='';
    try{saveDraft();status.textContent='Borrador guardado. Revisa el contenido exacto antes de preparar.';}
    catch{status.textContent='No se pudo guardar el borrador en este teléfono. No envíes hasta recuperar el almacenamiento.';}
    paint();
  }
  goal.oninput=reason.oninput=invalidateReview;
  function publicGoal(value){
    // Opaque memory bindings belong to the request, never to an editable/raw view.
    if(/"memory_(?:context_id|scope|dependencies)"\s*:/.test(JSON.stringify(value)))throw Error('context');
    if(!value||typeof value!=='object'||Array.isArray(value))throw Error('goal');
    return value;
  }
  function showDetail(value,original){
    detail=clone(value);binding=clone(original);stale=false;review=null;reviewPanel.hidden=true;reviewed.value='';
    identity.textContent='Misión '+value.operation_id+' · revisión '+value.goal_revision+' · hash '+value.plan_hash+' · estado '+value.state;
    destination.textContent='Destino completo: '+(typeof value.goal_spec?.destination==='string'?value.goal_spec.destination:JSON.stringify(value.goal_spec?.destination||value.mission?.destination||'Sin destino declarado'));
    const mission=value.mission||{},verified=Array.isArray(mission.verified_steps)?mission.verified_steps.length:0;
    progress.textContent=(mission.completed===true?'Objetivo completado con criterios y efectos verificados.':verified+' pasos con recibo y postcondiciones verificadas; objetivo pendiente.')+(value.can_correct===true?'':' Corrección no disponible: '+(value.correction_reason||'revisa la misión en la PC.'));
    draftKey=canonical([original,value.operation_id,value.goal_revision,value.plan_hash,value.memory_scope,value.memory_context_id]);
    const saved=JSON.parse(localStorage.getItem(namespace+'draft.'+draftKey)||'null');
    goal.value=saved?.goal??JSON.stringify(publicGoal(value.goal_spec),null,2);reason.value=saved?.text||'';editor.hidden=false;
    status.textContent=value.memory_forgotten?'La memoria se olvidó. Esta misión no admite correcciones.':'Revisa el objetivo completo y explica la corrección. Nada se ejecuta desde esta pantalla.';paint();
  }
  async function openMission(operationId){
    const ticket=++epoch,selected=++selection,original={device_id:snapshot?.device_id,fingerprint:snapshot?.fingerprint};
    selectedOperation=operationId;review=null;detail=null;draftKey='';goal.value=reason.value=reviewed.value='';editor.hidden=true;binding=original;paint();
    if(!available())return;
    status.textContent='Consultando la misión de la PC…';
    try{
      const result=await api('mission?operation_id='+encodeURIComponent(operationId),undefined,original);
      if(!current(ticket,original)||selected!==selection)return;
      if(result?.executor!=='pc'||result.operation_id!==operationId||result.conversation_id!==snapshot.conversation_id)throw Error('context');
      if(result.memory_forgotten){forgetContent(operationId,original);list.replaceChildren();status.textContent='La memoria se olvidó. Se depuraron los borradores de esta misión; revisa su estado en la PC.';return;}
      if(!validDetail(result))throw Error('context');
      showDetail(result,original);
    }catch(error){if(current(ticket,original))status.textContent=errorMessage(error);}
    finally{paint();}
  }
  async function refresh(){
    if(!available()||loading)return;
    loading=true;const ticket=epoch,original={device_id:snapshot.device_id,fingerprint:snapshot.fingerprint};binding=original;paint();
    try{
      const result=await api('missions?conversation_id='+encodeURIComponent(snapshot.conversation_id),undefined,original,ticket);
      if(!current(ticket,original))return;
      if(result.executor!=='pc'||result.conversation_id!==snapshot.conversation_id||!Array.isArray(result.missions))throw Error('context');
      list.replaceChildren();
      for(const mission of result.missions){
        const row=element('div');row.className='task';
        if(mission.memory_forgotten){
          forgetContent(mission.operation_id,original);
          row.append(element('strong','Misión '+mission.operation_id+' · memoria olvidada'),button('Abrir misión',undefined,()=>void openMission(mission.operation_id)));list.append(row);continue;
        }
        const destination=mission.mission?.destination??mission.destination??'Sin destino declarado';
        row.append(element('strong',mission.mission?.objective||mission.title||mission.operation_id),element('p','Destino completo: '+(typeof destination==='string'?destination:JSON.stringify(destination))),element('small','Misión '+mission.operation_id+' · revisión '+mission.goal_revision+' · hash '+mission.plan_hash),button('Abrir misión',undefined,()=>void openMission(mission.operation_id)));list.append(row);
        if(detail?.operation_id===mission.operation_id&&(mission.memory_forgotten||detail.plan_hash!==mission.plan_hash||detail.goal_revision!==mission.goal_revision)){if(!stale)epoch++;stale=true;review=null;reviewPanel.hidden=true;status.textContent='La revisión o memoria de la PC cambió. Abre la misión de nuevo; se conserva el borrador de la revisión anterior.';}
      }
      if(!result.missions.length)list.append(element('p','No hay misiones compartidas en este chat de la PC.'));
      if(pending&&!stale)await reconcile();
    }catch(error){if(current(ticket,original))status.textContent=errorMessage(error);}
    finally{loading=false;paint();}
  }
  function reviewCorrection(){
    if(reviewButton.disabled)return;
    try{
      const goalSpec=publicGoal(JSON.parse(goal.value)),text=reason.value.trim();
      if(!text||text.length>4000||goal.value.length>32768)throw Error('validation');
      saveDraft();
      review={epoch,context:missionContext(detail),goal_spec:clone(goalSpec),text,goalText:goal.value,reasonText:reason.value};
      reviewed.value=JSON.stringify({operation_id:detail.operation_id,conversation_id:detail.conversation_id,goal_revision:detail.goal_revision,plan_hash:detail.plan_hash,text,goal_spec:goalSpec},null,2);
      reviewPanel.hidden=false;reviewPanel.open=true;status.textContent='Contenido revisado. Preparar conserva la misión; la aprobación de sus efectos sigue en la PC.';paint();
    }catch{review=null;reviewPanel.hidden=true;status.textContent='Indica la corrección y un objeto JSON válido para el objetivo completo, conservando los campos y criterios necesarios.';paint();}
  }
  function receipt(result,operation){
    const body=operation.body;
    if(!result){status.textContent='La PC aún no conoce este envío. Su resultado sigue pendiente; no se repite.';return;}
    if(result.executor!=='pc'||result.command_id!==body.command_id||result.operation_id!==body.operation_id||result.conversation_id!==body.conversation_id||result.from_plan_hash!==body.plan_hash||result.from_goal_revision!==body.goal_revision)throw Error('context');
    if(result.memory_forgotten===true){forgetContent(body.operation_id,operation.binding);list.replaceChildren();status.textContent='El contexto original ya no está disponible. Se depuró su contenido local; sólo queda el seguimiento de sus identificadores. Revisa esa misión en la PC.';paint();return;}
    if(result.state==='confirmed'){
      const confirmed=result.receipt;
      if(!confirmed||typeof confirmed.id!=='string'||!confirmed.id||typeof confirmed.request_hash!=='string'||!confirmed.request_hash||confirmed.origin_device_id!==operation.binding.device_id||confirmed.from_plan_hash!==body.plan_hash||confirmed.from_goal_revision!==body.goal_revision||typeof confirmed.plan_hash!=='string'||!confirmed.plan_hash||!Number.isSafeInteger(confirmed.goal_revision)||confirmed.goal_revision<=body.goal_revision)throw Error('context');
      localStorage.removeItem(namespace+'pending');pending=null;
      if(detail?.operation_id===body.operation_id&&detail.conversation_id===body.conversation_id){review=null;stale=true;reviewPanel.hidden=true;}
      status.textContent=(confirmed.state==='awaiting_approval'?'Preparado; revisar y aprobar en PC.':'Corrección registrada por la PC · estado '+confirmed.state+'.')+' Misma misión '+body.operation_id+' · revisión '+confirmed.goal_revision+' · hash '+confirmed.plan_hash+'. No confirma ejecución.';
    }else if(result.state==='rejected'){
      localStorage.removeItem(namespace+'pending');pending=null;review=null;reviewPanel.hidden=true;status.textContent='La PC rechazó esta corrección. Reabre la misión y revisa su contexto antes de corregir.';
    }else status.textContent='Corrección pendiente o resultado sin confirmar. Se consultará el mismo envío; no se repite.';
    paint();
  }
  async function prepare(){
    if(prepareButton.disabled||sending||pending||!review)return;
    const captured=clone(review),source=clone(detail),original=clone(binding),ticket=epoch;
    if(captured.epoch!==ticket||captured.context!==missionContext(source)||goal.value!==captured.goalText||reason.value!==captured.reasonText)return invalidateReview();
    sending=true;paint();status.textContent='Verificando la revisión exacta y su contexto en la PC…';
    try{
      const fresh=await api('mission?operation_id='+encodeURIComponent(source.operation_id),undefined,original);
      if(!current(ticket,original))return;
      if(fresh?.memory_forgotten&&fresh.operation_id===source.operation_id&&fresh.conversation_id===source.conversation_id){forgetContent(source.operation_id,original);list.replaceChildren();status.textContent='La memoria se olvidó. Se depuraron los borradores; no se envió la corrección.';return;}
      if(!validDetail(fresh)||fresh.memory_forgotten||fresh.can_correct!==true||missionContext(fresh)!==captured.context){stale=true;review=null;reviewPanel.hidden=true;status.textContent='Cambió la misión, su revisión o la memoria. Reábrela antes de revisar otra corrección; se conserva el borrador.';return;}
      const body={command_id:crypto.randomUUID(),operation_id:source.operation_id,conversation_id:source.conversation_id,plan_hash:source.plan_hash,goal_revision:source.goal_revision,text:captured.text,goal_spec:captured.goal_spec,memory_scope:clone(source.memory_scope),memory_context_id:source.memory_context_id};
      const operation={binding:original,body,draft:{goal:captured.goalText,text:captured.reasonText}};
      localStorage.setItem(namespace+'pending',JSON.stringify(operation));pending=operation;paint();
      const result=await api('mission-correct',body,original,ticket);
      if(current(ticket,original)&&pending?.body.command_id===body.command_id)receipt(result,operation);
    }catch(error){if(current(ticket,original))status.textContent=errorMessage(error);}
    finally{sending=false;paint();}
  }
  async function reconcile(manual=false){
    if(!pending||checking||sending||!available())return;
    const operation=clone(pending),ticket=epoch,original=operation.binding;
    if(!manual&&snapshot.conversation_id!==operation.body.conversation_id)return;
    checking=true;paint();
    try{
      const result=await api('mission-correction?command_id='+encodeURIComponent(operation.body.command_id),undefined,original);
      if(current(ticket,original)&&pending?.body.command_id===operation.body.command_id)receipt(result,operation);
    }catch(error){if(ticket===epoch)status.textContent=errorMessage(error);}
    finally{checking=false;paint();}
  }
  panel.addEventListener('toggle',()=>{if(panel.open)void refresh();});
  window.addEventListener('axxSnapshot',event=>{
    const next=event.detail,key=canonical([next.device_id,next.fingerprint,next.conversation_id,next.scopes?.includes('tools.control')===true,next.capabilities?.mission_continuity===true]);
    if(snapshotKey&&snapshotKey!==key){epoch++;selection++;selectedOperation='';review=null;detail=null;draftKey='';goal.value=reason.value=reviewed.value='';editor.hidden=true;list.replaceChildren();reviewPanel.hidden=true;status.textContent='Cambió el enlace o el chat compartido. Abre la misión de nuevo; se conservan borradores y seguimientos.';}
    snapshot=next;snapshotKey=key;online=true;binding={device_id:next.device_id,fingerprint:next.fingerprint};
    if(!available())status.textContent='Comparte el historial de este chat y aprueba herramientas en la PC para ver sus misiones.';
    paint();if(panel.open&&available())void refresh();
  });
  window.addEventListener('axxOffline',()=>{online=false;epoch++;review=null;reviewPanel.hidden=true;paint();});
  if(pending?.memory_forgotten)try{forgetContent(pending.body.operation_id,pending.binding);}catch{}
  paint();
})();
