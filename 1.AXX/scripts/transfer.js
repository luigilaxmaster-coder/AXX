/* The PC owns permission and file identity; presentation never confirms delivery. */
(() => {
  'use strict';
  const A=window.Axx,$=id=>document.getElementById(id);
  if(!A?.companion||A.transfer)return;
  const icon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8m-4-3 3 3-3 3"/></svg>';
  const view=document.createElement('section');view.id='view-transfer';view.className='panel-view transfer-view';view.hidden=true;
  view.innerHTML=`<div class="tf-heading"><div><span class="tf-eyebrow">AXX TRANSFER</span><h2>Archivos</h2></div><button id="tf-refresh" type="button">Actualizar</button></div>
    <p>Entre esta PC y tus teléfonos vinculados. Los originales se conservan.</p>
    <label for="tf-device">Dispositivo</label><select id="tf-device"><option value="">Cargando dispositivos…</option></select>
    <p id="tf-status" class="tf-state" role="status" aria-live="polite">Comprobando conexión…</p>
    <form id="tf-search-form" class="tf-drop"><label for="tf-query">Buscar en las carpetas autorizadas</label><div class="tf-row"><input id="tf-query" type="search" maxlength="500" placeholder="Nombre del documento o extensión"><button class="tf-primary" type="submit">Buscar</button></div><p>Suelta aquí un archivo para buscar su nombre. Elige el resultado antes de enviarlo.</p></form>
    <div id="tf-results" class="tf-list" aria-label="Resultados de archivos"></div>
    <details open><summary>Transferencias y recibos</summary><div id="tf-history" class="tf-list"></div></details>
    <details><summary>Carpetas y permisos</summary><p>El acceso se aplica solo al dispositivo elegido y a estas carpetas. Recibir guarda una copia en Axx; exportar requiere elegir un destino nuevo.</p>
      <form id="tf-permissions"><label class="tf-check"><input id="tf-read" type="checkbox"> Buscar y copiar al teléfono</label><label class="tf-check"><input id="tf-write" type="checkbox"> Recibir archivos del teléfono</label><label for="tf-roots">Carpetas permitidas · una ruta completa por línea</label><textarea id="tf-roots" rows="3" spellcheck="false" placeholder="C:\\Users\\tu usuario\\Documents"></textarea><button type="submit">Guardar permisos</button></form>
    </details>`;
  $('panel').append(view);
  const api=async(path,body)=>{if(!A.isNative())throw Error('La transferencia requiere Axx Desktop y un teléfono vinculado.');const r=await A.backendRequest(body===undefined?'GET':'POST','/axx-api/mobile/'+path,body??null);if(r?.error)throw Error(r.error.message||r.error);return r;};
  const element=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const bytes=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
  const labels={preparing:'Preparando copia',ready:'Listo para el teléfono',transferring:'Transfiriendo',receiving:'Recibiendo',paused:'Pausado',completed:'Recibido y verificado',cancelled:'Cancelado',failed:'No se completó',verifying:'Verificando',interrupted:'Interrumpido'};
  let state={devices:[],transfers:[]},refreshing=false,working=false,results=[],seen=new Map(),initialized=false,deviceKey='',historyKey='',searchRevision=0,grantDirty=false;
  const status=(text,error=false)=>{$('tf-status').textContent=text;$('tf-status').classList.toggle('tf-error',error);};
  const device=()=>state.devices.find(d=>d.device_id===$('tf-device').value);
  function button(text,action){const b=element('button',text);b.type='button';b.onclick=()=>void run(action);return b;}
  async function run(action){if(working)return;working=true;try{await action();}catch(e){status(e.message||String(e),true);}finally{working=false;}}
  function grant(){const d=device();return {...(d?.permissions||{}),roots:d?.roots||[]};}
  function fillGrant(){const g=grant();$('tf-read').checked=!!g.read;$('tf-write').checked=!!g.write;$('tf-roots').value=(g.roots||[]).map(r=>typeof r==='string'?r:r.path).join('\n');grantDirty=false;}
  function render(){
    const devices=state.devices.filter(d=>!d.revoked),key=JSON.stringify(devices.map(d=>[d.device_id,d.name]));
    if(key!==deviceKey){deviceKey=key;const selected=$('tf-device').value;$('tf-device').replaceChildren(...devices.map(d=>new Option(d.name||'Teléfono',d.device_id)));if(devices.some(d=>d.device_id===selected))$('tf-device').value=selected;if(!devices.length)$('tf-device').add(new Option('Vincula un teléfono en Ajustes',''));if(!grantDirty)fillGrant();}
    const rows=(state.transfers||[]).filter(t=>!device()||t.device_id===device().device_id),hk=JSON.stringify(rows);
    if(hk!==historyKey){historyKey=hk;const list=$('tf-history');list.replaceChildren();
      for(const t of rows.slice().reverse().slice(0,40)){
        const row=element('article');row.className='tf-item';row.dataset.transferId=t.transfer_id;
        row.append(element('strong',t.name),element('small',(t.direction==='to_pc'?'Teléfono → Esta PC':'Esta PC → Teléfono')+' · '+(labels[t.state]||t.state)));
        const total=t.size??t.bytes??0,confirmed=t.confirmed_bytes||0;
        if(t.state!=='completed'){const progress=element('progress');progress.max=Math.max(total,1);progress.value=confirmed;progress.setAttribute('aria-label','Bytes confirmados de '+t.name);row.append(progress,element('small',bytes(confirmed)+' de '+bytes(total)));}
        const actions=element('div');actions.className='tf-row';
        if(!['completed','cancelled','failed'].includes(t.state)){actions.append(button(t.state==='paused'?'Reanudar':'Pausar',async()=>{await api('transfers/'+(t.state==='paused'?'resume':'pause'),{transfer_id:t.transfer_id});await refresh();}),button('Cancelar',async()=>{await api('transfers/cancel',{transfer_id:t.transfer_id});await refresh();}));}
        if(t.state==='completed'&&t.direction==='to_pc'&&t.stored!==false)actions.append(button('Guardar copia…',async()=>{const destination=window.prompt('Ruta completa de un archivo nuevo. La copia exportada queda fuera de la bandeja cifrada de Axx.',t.name);if(!destination)return;await api('files/export',{transfer_id:t.transfer_id,destination});status('Copia guardada en el destino elegido.');}));
        if(['completed','cancelled','failed'].includes(t.state)&&t.stored!==false)actions.append(button('Eliminar copia de Axx',async()=>{if(!window.confirm('¿Eliminar la copia cifrada de «'+t.name+'» guardada en Axx? Se conservan el recibo, el archivo original y las copias exportadas.'))return;await api('files/remove',{transfer_id:t.transfer_id});await refresh();status('Copia de Axx eliminada. El recibo se conserva.');}));
        row.append(actions);list.append(row);
      }
      if(!rows.length)list.append(element('p','Todavía no hay transferencias con este dispositivo.'));
    }
    $('tf-query').disabled=!device();$('tf-permissions').querySelector('button').disabled=!device();
  }
  function pulse(){
    const r=A.app?.renderer;
    if(!r||r.hidden||view.hidden||document.hidden||r.reaching||r.settings?.reducedMotion||r.settings?.staticMode||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    const rect=$('avatar').getBoundingClientRect(),x=rect.left+rect.width/2,y=rect.top+rect.height/2,start=performance.now();
    const frame=now=>{try{const t=(now-start)/850;if(t>=1||view.hidden||document.hidden){r.setReach(null);return;}const strength=Math.sin(Math.PI*t);r.setReach(A.reachTube(r.screenPoint(x,y,.22),r.screenPoint(x+Math.min(75,rect.width*.3)*strength,y+25*strength,.22),strength,t),strength);requestAnimationFrame(frame);}catch{try{r.setReach(null);}catch{}}};requestAnimationFrame(frame);
  }
  async function refresh(){if(refreshing)return;refreshing=true;try{state=await api('files/status');render();for(const t of state.transfers||[]){if(initialized&&seen.get(t.transfer_id)!==t.state&&t.state==='completed'){status(t.name+' · Recibido y verificado.');pulse();}seen.set(t.transfer_id,t.state);}initialized=true;if(!$('tf-status').textContent||$('tf-status').textContent==='Comprobando conexión…')status(device()?'Elige un archivo o revisa los permisos de este teléfono.':'Vincula tu teléfono en Ajustes → Conectar teléfono.');}catch(e){status(e.message||String(e),true);}finally{refreshing=false;}}
  async function search(){const revision=++searchRevision,d=device();if(!d)throw Error('Vincula y elige un teléfono primero.');status('Buscando en tus carpetas autorizadas…');const data=await api('files/search',{device_id:d.device_id,query:$('tf-query').value.trim()});if(revision!==searchRevision||d.device_id!==$('tf-device').value)return;results=data.files||[];$('tf-results').replaceChildren(...results.map(file=>{const row=element('article');row.className='tf-item';row.append(element('strong',file.name),element('small',file.relative_path+' · '+bytes(file.size??file.bytes)+' · '+new Date(file.modified_at*1000).toLocaleString()));row.append(button('Enviar copia al teléfono',async()=>{const transfer=await api('transfers/create',{device_id:d.device_id,transfer_id:crypto.randomUUID(),direction:'to_phone',file_ref:file.file_ref});status(file.name+' · '+(labels[transfer.state]||transfer.state));pulse();await refresh();}));return row;}));status(results.length?(results.length+' coincidencias'+(data.truncated?' · limita la búsqueda para ver las restantes.':'. Elige la copia que quieres enviar.')):'No hay coincidencias en las carpetas autorizadas.');}
  $('tf-search-form').onsubmit=e=>{e.preventDefault();void run(search);};$('tf-refresh').onclick=()=>void refresh();$('tf-device').onchange=()=>{searchRevision++;results=[];$('tf-results').replaceChildren();historyKey='';fillGrant();render();};
  for(const id of ['tf-read','tf-write','tf-roots'])$(id).oninput=()=>grantDirty=true;
  $('tf-permissions').onsubmit=e=>{e.preventDefault();void run(async()=>{if(!device())throw Error('Selecciona un teléfono.');await api('files/permissions',{device_id:device().device_id,read:$('tf-read').checked,write:$('tf-write').checked,roots:$('tf-roots').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)});grantDirty=false;state=await api('files/status');fillGrant();render();status('Permisos guardados para '+device().name+'.');});};
  const drop=$('tf-search-form');drop.ondragover=e=>{if(e.dataTransfer?.types.includes('Files')){e.preventDefault();drop.classList.add('drag');}};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');const file=e.dataTransfer?.files?.[0];if(file){$('tf-query').value=file.name;void run(search);}};
  A.FEATURES.push({id:'transfer',family:'actions',title:'Archivos',description:'Enviar y recibir copias con tus teléfonos vinculados.',view:'transfer',availability:'TELÉFONO VINCULADO'});
  const previousOpen=A.companion.openFeature.bind(A.companion);A.companion.openFeature=id=>{const result=previousOpen(id);if(id==='transfer'){$('panel-title').textContent='Archivos';void refresh();}return result;};
  const open=()=>A.flow.select('transfer');
  const prior=A.companion.externalCommand;A.companion.externalCommand=raw=>/^(?:abre|abrir|muestra)?\s*(?:axx transfer|transferencias|archivos del telefono)$/.test(A.plain(raw))?async()=>{open();return 'Archivos abierto. Elige un teléfono y sus carpetas autorizadas.';}:prior?.(raw)||null;
  const launch=button('Archivos',async()=>open());launch.id='tf-launch';launch.className='tf-chat-launch';launch.innerHTML=icon+'<span>Archivos</span>';launch.setAttribute('aria-label','Archivos entre esta PC y el teléfono');document.querySelector('.chat20-head-actions')?.append(launch);
  A.transfer={open,refresh};setInterval(()=>{if(!view.hidden)void refresh();},2000);
})();
