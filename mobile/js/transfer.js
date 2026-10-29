/* Copy only. The native encrypted store confirms reception before the UI does. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),transport=window.Capacitor?.Plugins?.AxxTransport,native=window.Capacitor?.Plugins?.AxxFiles;
  const glyph='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 14h8m-4-3 3 3-3 3"/></svg>';
  const launch=document.createElement('button');launch.type='button';launch.id='tfm-launch';launch.className='files-launch';launch.innerHTML=glyph+'<span>Archivos</span>';launch.setAttribute('aria-controls','files-dialog');document.querySelector('.axx-stage-container')?.append(launch);
  const dialog=document.createElement('dialog');dialog.id='files-dialog';dialog.setAttribute('aria-labelledby','tfm-title');
  dialog.innerHTML=`<header class="tf-heading"><div><span class="tf-eyebrow">AXX TRANSFER</span><h2 id="tfm-title">Archivos</h2></div><button id="tfm-close" type="button" aria-label="Cerrar archivos">×</button></header>
    <p id="tfm-target" class="tf-subtitle">Archivos de tu PC</p><p id="tfm-permissions" class="tf-permissions"></p>
    <form id="tfm-search-form"><label for="tfm-query">Buscar en tu PC</label><input id="tfm-query" type="search" maxlength="200" placeholder="Nombre, proyecto o PDF…"><div class="tf-actions"><button type="submit" class="primary" id="tfm-search">Buscar</button><button id="tfm-send" type="button">Enviar archivo</button></div><p class="tf-search-hint">Solo carpetas que autorizaste en la PC. Las búsquedas de archivos se quedan entre tus dispositivos.</p></form>
    <p id="tfm-status" role="status" aria-live="polite">Conecta tu PC para empezar.</p>
    <div id="tfm-current"></div>
    <div class="tf-tabs" role="tablist" aria-label="Archivos"><button type="button" id="tfm-tab-results" role="tab" aria-selected="true" aria-controls="tfm-results">Resultados</button><button type="button" id="tfm-tab-received" role="tab" aria-selected="false" aria-controls="tfm-received">En este teléfono</button><button type="button" id="tfm-tab-history" role="tab" aria-selected="false" aria-controls="tfm-history">Recientes</button></div>
    <div id="tfm-results" role="tabpanel" aria-labelledby="tfm-tab-results"></div><div id="tfm-received" role="tabpanel" aria-labelledby="tfm-tab-received" hidden></div><div id="tfm-history" role="tabpanel" aria-labelledby="tfm-tab-history" hidden></div>`;
  document.body.append(dialog);
  const arrival=document.createElement('button');arrival.id='tfm-arrival';arrival.type='button';arrival.hidden=true;document.querySelector('.axx-stage-container')?.append(arrival);
  const element=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const bytes=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
  const total=t=>t.size??t.bytes??0;
  const labels={preparing:'Preparando copia',ready:'Preparado',transferring:'Transfiriendo',receiving:'Recibiendo',verifying:'Verificando',paused:'Pausado',completed:'Recibido y verificado',received:'Guardado en este teléfono',cancelled:'Cancelado',failed:'No se completó',interrupted:'Interrumpido'};
  let pending=null,active=null,files=[],history=[],permissions={},generation=0,running=false,controlling=false,refreshing=false,currentDevice='',searchRevision=0,operationMessage='',candidates=[],candidateDevice='',candidateTime=0,lastRefresh=0;
  try{pending=JSON.parse(localStorage.getItem('axx.transfer.pending')||'null');if(!pending||typeof pending.transfer_id!=='string')pending=null;}catch{}
  const setPending=value=>{pending=value;if(value)localStorage.setItem('axx.transfer.pending',JSON.stringify(value));else localStorage.removeItem('axx.transfer.pending');};
  const status=(message,error=false)=>{operationMessage=message;$('tfm-status').textContent=message;$('tfm-status').dataset.error=String(error);};
  const api=async(path,body,binding)=>{if(!transport||!binding?.device_id||!binding?.fingerprint)throw Error('Vuelve a verificar el enlace con tu PC.');const result=await transport.request({path:'/v1/'+path,method:body===undefined?'GET':'POST',expected_device_id:binding.device_id,expected_fingerprint:binding.fingerprint,...(body===undefined?{}:{body})});const data=result.data;if(data?.error)throw Error(data.error.message||data.error);return data;};
  function button(text,action){const b=element('button',text);b.type='button';b.onclick=()=>void action().catch(e=>status(e.message||String(e),true));return b;}
  function tab(name){for(const id of ['results','received','history']){$('tfm-'+id).hidden=id!==name;$('tfm-tab-'+id).setAttribute('aria-selected',String(id===name));}}
  for(const name of ['results','received','history'])$('tfm-tab-'+name).onclick=()=>tab(name);
  function requireNative(){if(!native)throw Error('Actualiza Axx Mobile para guardar archivos de forma cifrada.');}
  async function ensureDevice(){if(!transport)throw Error('Usa Axx Mobile instalada en Android.');const p=await transport.profile();if(!p.paired)throw Error('Enlaza tu PC antes de transferir archivos.');if(pending&&(pending.device_id!==p.device_id||pending.fingerprint!==p.fingerprint))throw Error('Hay una transferencia de otro enlace. Vuelve a enlazar esa PC para reconciliarla.');currentDevice=p.device_id||'';return {device_id:p.device_id,fingerprint:p.fingerprint};}
  function renderCurrent(){const host=$('tfm-current');host.replaceChildren();if(!pending&&!active)return;const t=active||{},row=element('article');row.className='tf-item tf-current';row.append(element('strong',t.name||'Transferencia pendiente'),element('small',(t.direction==='to_pc'?'Este teléfono → PC':'PC → Este teléfono')+' · '+(labels[t.state]||'Sin confirmar')));if(total(t)>0){const progress=element('progress');progress.max=total(t);progress.value=t.confirmed_bytes||0;progress.setAttribute('aria-label','Bytes guardados de '+(t.name||'archivo'));row.append(progress,element('small',bytes(t.confirmed_bytes||0)+' de '+bytes(total(t))));}const actions=element('div');actions.className='tf-actions';if(pending){actions.append(button(running?'Pausar':'Reanudar',async()=>running?control('pause'):resume()),button('Cancelar',async()=>control('cancel')));if(!running)actions.append(button('Consultar',refresh));}row.append(actions);host.append(row);}
  function renderLists(){
    const received=$('tfm-received');received.replaceChildren();for(const file of files){const row=element('article');row.className='tf-item';row.append(element('strong',file.name),element('small',file.state==='unavailable'?'No se puede abrir esta copia local':bytes(total(file))+' · '+({received:'Guardado y verificado en este teléfono',ready:'Copia de origen en este teléfono',importing:'Importación incompleta',receiving:'Recepción incompleta'}[file.state]||'Copia incompleta')));if(['received','ready'].includes(file.state))row.append(button('Guardar o compartir…',async()=>{requireNative();const result=await native.export({file_id:file.file_id});status(result.exported?'Copia exportada al destino elegido.':'Exportación cancelada.');}));if(native?.deleteCopy&&file.file_id!==pending?.file_id&&file.file_id!==pending?.transfer_id)row.append(button('Eliminar copia local',async()=>{if(!window.confirm('¿Eliminar de Axx la copia cifrada de «'+file.name+'»? Se conservan el original y las copias ya exportadas.'))return;await native.deleteCopy({file_id:file.file_id});await refresh();status('Copia local eliminada de Axx.');}));received.append(row);}
    const list=$('tfm-history');list.replaceChildren();for(const t of history.slice().reverse().slice(0,30)){const row=element('article');row.className='tf-item';row.append(element('strong',t.name),element('small',(t.direction==='to_pc'?'Teléfono → PC':'PC → Teléfono')+' · '+(labels[t.state]||t.state)));if(!['completed','cancelled','failed'].includes(t.state)&&(!pending||pending.transfer_id===t.transfer_id))row.append(button(t.direction==='to_phone'&&t.state==='ready'?'Recibir en este teléfono':'Continuar',async()=>{const binding=await ensureDevice();setPending({transfer_id:t.transfer_id,direction:t.direction,file_id:t.direction==='to_pc'?files.find(f=>f.sha256===t.sha256&&f.state==='ready')?.file_id:undefined,...binding});active=t;await resume();}));list.append(row);}
  }
  async function refresh(){
    if(refreshing)return;refreshing=true;lastRefresh=Date.now();
    try{
      if(native){const local=await native.list();files=local.files||[];renderLists();}
      const binding=await ensureDevice(),data=await api('files/status',undefined,binding);
      if(binding.device_id!==currentDevice)return;
      permissions=data.permissions||{};history=data.transfers||[];
      $('tfm-target').textContent='Axx · '+($('pc-name')?.textContent||'Tu PC');
      $('tfm-permissions').textContent=(permissions.read?'Lectura autorizada':'Lectura sin autorizar')+' · '+(permissions.write?'Recepción autorizada':'Recepción sin autorizar');
      $('tfm-search').disabled=!permissions.read;$('tfm-send').disabled=!permissions.write||!native;
      const waiting=history.filter(t=>t.direction==='to_phone'&&t.state==='ready').length;
      launch.querySelector('span').textContent=waiting?'Archivos · '+waiting:'Archivos';launch.title=waiting?'Hay copias preparadas en la PC. Abre Recientes para recibirlas.':'Archivos entre tus dispositivos';renderLists();
      if(pending&&!running&&!controlling){
        const id=pending.transfer_id,revision=generation,next=await api('transfers?transfer_id='+encodeURIComponent(id),undefined,binding);
        if(revision!==generation||pending?.transfer_id!==id)return;
        active=next;if(['completed','cancelled','failed'].includes(active.state)){setPending(null);status(active.name+' · '+(labels[active.state]||active.state));}
      }else if(!operationMessage)status('Busca un archivo o envía una copia a tu PC.');
      renderCurrent();
    }catch(e){status(e.message||String(e),true);}finally{refreshing=false;}
  }
  function open(){if(!dialog.open)dialog.showModal();void refresh();}
  launch.onclick=open;$('tfm-close').onclick=()=>dialog.close();arrival.onclick=()=>{open();tab('received');arrival.hidden=true;};
  async function search(query,filters={}){
    const revision=++searchRevision,binding=await ensureDevice();status('Buscando en tu PC…');tab('results');
    const result=await api('files/search',{query,...filters},binding);
    if(revision!==searchRevision||binding.device_id!==currentDevice)return;
    candidates=result.files||[];candidateDevice=binding.device_id;candidateTime=Date.now();
    $('tfm-results').replaceChildren(...candidates.map(file=>{
      const row=element('article');row.className='tf-item';row.append(element('strong',file.name),element('small',(file.root_name?file.root_name+' / ':'')+file.relative_path+' · '+bytes(total(file))+' · '+new Date(file.modified_at*1000).toLocaleString()));
      row.append(button('Traer al teléfono',async()=>startDownload(file)));return row;
    }));
    status(candidates.length?candidates.length+' coincidencias'+(result.truncated?' · Busca con más detalle para reducir los resultados.':'. Más recientes primero. Elige el archivo que quieres copiar.'):'No encontré coincidencias en las carpetas autorizadas.');
  }
  $('tfm-search-form').onsubmit=e=>{e.preventDefault();void search($('tfm-query').value.trim()).catch(e=>status(e.message||String(e),true));};
  async function startDownload(file){
    requireNative();const binding=await ensureDevice();
    if(candidateDevice!==binding.device_id||Date.now()-candidateTime>300000)throw Error('Vuelve a buscar: estos resultados ya no corresponden al contexto actual.');
    if(pending||running)throw Error('Termina o cancela la transferencia pendiente primero.');
    setPending({transfer_id:crypto.randomUUID(),direction:'to_phone',file_ref:file.file_ref,...binding});
    active={...file,transfer_id:pending.transfer_id,direction:'to_phone',state:'preparing',confirmed_bytes:0};renderCurrent();await resume();
  }
  $('tfm-send').onclick=()=>void (async()=>{
    requireNative();const binding=await ensureDevice(),revision=generation;
    if(pending||running)throw Error('Termina o cancela la transferencia pendiente primero.');
    const file=await native.choose();if(!file?.file_id)return;
    if(revision!==generation||binding.device_id!==currentDevice)throw Error('Cambió el enlace durante la selección. La copia queda en este teléfono.');
    if(pending)throw Error('Ya hay una transferencia pendiente. La copia elegida queda en este teléfono.');
    files.push(file);setPending({transfer_id:crypto.randomUUID(),direction:'to_pc',file_id:file.file_id,...binding});
    active={...file,transfer_id:pending.transfer_id,direction:'to_pc',state:'preparing',confirmed_bytes:0};renderCurrent();await resume();
  })().catch(e=>{status(e.message||String(e),true);renderCurrent();});
  async function control(action){
    if(!pending||controlling)return;controlling=true;
    const operation={...pending},revision=++generation;status(action==='cancel'?'Solicitando cancelación…':'Solicitando pausa…');
    try{
      const next=await api('transfers/'+action,{transfer_id:operation.transfer_id},operation);
      if(revision!==generation)return;active=next;
      if(action==='cancel'&&active.state==='cancelled'){
        if(native)await native.cancel({file_id:operation.direction==='to_pc'?operation.file_id:operation.transfer_id});
        if(revision!==generation)return;setPending(null);
      }
      status(active.name+' · '+(labels[active.state]||active.state));
    }catch(e){if(revision===generation)status((action==='cancel'?'Cancelación':'Pausa')+' sin confirmar: '+(e.message||e)+'. Consulta el estado antes de continuar.',true);}
    finally{controlling=false;renderCurrent();}
  }
  async function resume(){
    if(!pending||running||controlling)return;requireNative();running=true;
    const operation={...pending},id=operation.transfer_id,run=++generation,valid=()=>run===generation&&!document.hidden;renderCurrent();
    const update=async(path,body)=>{const next=await api(path,body,operation);if(valid())active=next;return valid();};
    try{
      await ensureDevice();if(!valid())return;
      if(operation.file_ref){if(!await update('transfers/create',{transfer_id:id,direction:'to_phone',file_ref:operation.file_ref}))return;}
      else if(operation.direction==='to_pc'&&operation.file_id){
        const local=(await native.list()).files.find(f=>f.file_id===operation.file_id);if(!valid())return;
        if(!local)throw Error('La copia de origen ya no está disponible en el teléfono.');
        if(!await update('transfers/create',{transfer_id:id,direction:'to_pc',name:local.name,size:total(local),sha256:local.sha256}))return;
      }else if(!await update('transfers?transfer_id='+encodeURIComponent(id)))return;
      if(active.state==='paused'&&!await update('transfers/resume',{transfer_id:id}))return;
      while(active.state==='preparing'&&valid()){
        status('Preparando una copia estable en tu PC…');await new Promise(resolve=>setTimeout(resolve,600));
        if(!valid()||!await update('transfers?transfer_id='+encodeURIComponent(id)))return;
      }
      if(!valid())return;
      if(['cancelled','failed'].includes(active.state))throw Error(active.error||labels[active.state]);
      if(active.state==='completed'){setPending(null);status(active.name+' · Recibido y verificado.');return;}
      if(active.chunk_size!==262144||!Number.isInteger(active.chunk_count)||active.chunk_count<0)throw Error('El protocolo de bloques no es compatible.');
      if(operation.direction==='to_phone'){
        let local=await native.beginReceive({transfer_id:id,name:active.name,size:total(active),sha256:active.sha256,chunk_size:active.chunk_size});if(!valid())return;
        for(let index=local.next_index||0;index<active.chunk_count&&valid();index++){
          const chunk=await api('transfers/chunk',{transfer_id:id,index},operation);if(!valid())return;
          local=await native.writeChunk({transfer_id:id,index,data:chunk.data});if(!valid())return;
          active={...active,confirmed_bytes:local.confirmed_bytes,state:'receiving'};status('Recibiendo '+active.name+'…');renderCurrent();
        }
        if(!valid())return;status('Verificando y guardando en este teléfono…');
        const receipt=await native.finishReceive({transfer_id:id});if(!valid())return;
        if(receipt.state!=='received'||total(receipt)!==total(active)||receipt.sha256!==active.sha256)throw Error('El teléfono no confirmó un archivo íntegro.');
        if(!await update('transfers/receipt',{transfer_id:id,size:total(receipt),sha256:receipt.sha256}))return;
        arrival.replaceChildren(element('strong',receipt.name),element('small','Recibido y verificado · Abrir archivos'));arrival.hidden=false;pulse();
      }else{
        if(!operation.file_id)throw Error('No se encuentra la copia de origen en este teléfono. Cancela esta transferencia y selecciona el archivo de nuevo.');
        for(let index=Math.ceil((active.confirmed_bytes||0)/active.chunk_size);index<active.chunk_count&&valid();index++){
          const chunk=await native.readChunk({file_id:operation.file_id,index});if(!valid())return;
          if(!await update('transfers/chunk',{transfer_id:id,index,data:chunk.data}))return;
          status('Enviando '+active.name+'…');renderCurrent();
        }
        if(!valid())return;status('La PC está verificando y guardando…');
        if(!await update('transfers/finish',{transfer_id:id}))return;
        while(active.state==='verifying'&&valid()){
          await new Promise(resolve=>setTimeout(resolve,600));if(!valid()||!await update('transfers?transfer_id='+encodeURIComponent(id)))return;
        }
      }
      if(active.state!=='completed')throw Error('La recepción todavía no está confirmada. Consulta el estado.');
      status(active.name+' · Recibido y verificado'+(operation.direction==='to_pc'?' en tu PC.':' en este teléfono.'));setPending(null);await refresh();
    }catch(e){if(valid())status('Transferencia pendiente: '+(e.message||String(e))+'. Puedes consultar o reanudar.',true);}
    finally{running=false;renderCurrent();}
  }
  function pulse(){
    const r=window.axxMobileRenderer;
    if(!r||r.hidden||dialog.open||document.hidden||r.reaching||r.settings.reducedMotion||r.settings.staticMode||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    const rect=r.canvas.getBoundingClientRect(),x=rect.left+rect.width/2,y=rect.top+rect.height/2,start=performance.now();
    const frame=now=>{
      try{
        const t=(now-start)/850;if(t>=1||document.hidden){r.setReach(null);return;}
        const amount=Math.sin(t*Math.PI);r.setReach(Axx.reachTube(r.screenPoint(x,y,.22),r.screenPoint(x+60*amount,y+25*amount,.22),amount,t),amount);requestAnimationFrame(frame);
      }catch{try{r.setReach(null);}catch{}}
    };
    requestAnimationFrame(frame);
  }
  function privateQuery(text){
    const raw=text.trim(),plain=raw.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/^axx(?: de (?:mi|la) (?:pc|computadora))?[, :]+/,'');
    if(!/^(?:\/archivos\b|(?:axx[, ]+)?(?:busca|buscar|trae|traeme|mandame|enviame|muestrame|ensename)\b)/.test(plain))return null;
    if(!plain.startsWith('/archivos')&&!/\b(?:archivo|documento|pdf|excel|presupuesto|plano|render|foto|imagen|proyecto)\b|\.[a-z0-9]{2,5}\b|\b(?:mi|la) pc\b/.test(plain))return null;
    const filters={};if(/\b(?:ayer|hoy)\b/.test(plain)){const now=new Date(),today=new Date(now.getFullYear(),now.getMonth(),now.getDate()),yesterday=/\bayer\b/.test(plain);filters.modified_after=(yesterday?new Date(now.getFullYear(),now.getMonth(),now.getDate()-1):today).getTime()/1000;filters.modified_before=(yesterday?today:new Date(now.getFullYear(),now.getMonth(),now.getDate()+1)).getTime()/1000;}
    const literal=raw.match(/["“]([^"”]+)["”]/);
    const query=literal?literal[1]:plain.replace(/^\/archivos\s*/,'').replace(/^(?:axx[, ]+)?(?:busca|buscar|trae|traeme|mandame|enviame|muestrame|ensename)\s*/,'').replace(/\s+(?:y\s+)?(?:traemelo|mandamelo|enviamelo)(?:\s+aqui)?[.!?]*$/,'').replace(/\b(?:en|de|desde|a|al) (?:(?:mi|la|el|este) )?(?:pc|telefono|computadora)\b/g,'').replace(/\b(?:el|la|los|las|un|una|ultimo|ultima|archivo|archivos|documento|documentos|ayer|hoy|aqui|que|modifique|modificado|guarde)\b/g,' ').replace(/\s+/g,' ').replace(/[.!?]+$/,'').trim();
    return {query,filters};
  }
  window.AxxTransfer={open,privateQuery,handleText(text){const plain=text.trim().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();const ordinal=plain.match(/^(?:(?:mandame|traeme|enviame|quiero)\s+)?el\s+(primero|segundo|tercero|ultimo)[.!]?$/);if(ordinal&&candidates.length){open();const index=ordinal[1]==='ultimo'?0:['primero','segundo','tercero'].indexOf(ordinal[1]);if(!candidates[index])status('No hay un resultado con ese número. Elige una tarjeta.');else void startDownload(candidates[index]).catch(e=>status(e.message||String(e),true));return true;}const parsed=privateQuery(text);if(!parsed){if(/\b(?:archivo|documento|pdf|dwg|rvt|excel|plano|render)\b/.test(plain)&&/\b(?:buscar|busca|trae|traeme|traig|enviar|envia|mandar|manda|descarga|guardar|guarda)/.test(plain)){open();status('Usa «busca el nombre en mi PC» y elige un resultado. Esta orden queda en Archivos, sin enviarse al modelo.');return true;}return false;}open();$('tfm-query').value=parsed.query;void search(parsed.query,parsed.filters).catch(e=>status(e.message||String(e),true));return true;}};
  window.addEventListener('axxSnapshot',event=>{const next=event.detail.device_id||currentDevice;if(next!==currentDevice){generation++;searchRevision++;candidates=[];candidateDevice='';history=[];$('tfm-results').replaceChildren();status('Cambió el enlace. Consulta las transferencias de la PC antes de continuar.');}currentDevice=next;if(native&&!running&&Date.now()-lastRefresh>4000)void refresh();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&running){generation++;status('Transferencia interrumpida al salir. Reanuda al volver a Axx.');}else if(dialog.open)void refresh();});
  dialog.addEventListener('close',()=>{if(!arrival.hidden)pulse();});
  if(!native){$('tfm-send').disabled=true;status('Actualiza Axx Mobile para enviar y guardar archivos.');}
})();
