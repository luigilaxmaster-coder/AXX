/* The PC owns permission and file identity; presentation never confirms delivery. */
(() => {
  'use strict';
  const A=window.Axx,$=id=>document.getElementById(id);
  if(!A?.companion||A.transfer)return;
  const icon='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8m-4-3 3 3-3 3"/></svg>';
  const view=document.createElement('section');view.id='view-transfer';view.className='panel-view transfer-view';view.hidden=true;
  view.innerHTML=`<div class="tf-heading"><div><span class="tf-eyebrow">AXX TRANSFER</span><h2 id="tf-heading-title">Recibidos del teléfono</h2></div><button id="tf-refresh" type="button">Actualizar</button></div>
    <p>Recoge aquí tus archivos recibidos. La copia original siempre se conserva.</p>
    <nav class="tf-tabs" role="tablist" aria-label="Secciones de Archivos">
      <button type="button" id="tf-tab-received" role="tab" aria-selected="true" aria-controls="tf-received-panel">Recibidos <span id="tf-received-count">0</span></button>
      <button type="button" id="tf-tab-send" role="tab" aria-selected="false" aria-controls="tf-send-panel" tabindex="-1">Enviar</button>
      <button type="button" id="tf-tab-activity" role="tab" aria-selected="false" aria-controls="tf-activity-panel" tabindex="-1">Actividad y permisos</button>
    </nav>
    <p id="tf-status" class="tf-state" role="status" aria-live="polite">Comprobando archivos recibidos…</p>
    <div id="tf-device-controls" hidden><label for="tf-device">Teléfono para enviar o configurar</label><select id="tf-device"><option value="">Cargando dispositivos…</option></select></div>
    <section id="tf-received-panel" role="tabpanel" aria-labelledby="tf-tab-received"><div id="tf-received" class="tf-list" aria-label="Archivos recibidos del teléfono"><p>Cargando archivos recibidos…</p></div></section>
    <section id="tf-send-panel" role="tabpanel" aria-labelledby="tf-tab-send" hidden>
      <form id="tf-search-form" class="tf-drop"><label for="tf-query">Buscar en las carpetas autorizadas de esta PC</label><div class="tf-row"><input id="tf-query" type="search" maxlength="200" placeholder="Nombre del documento o extensión"><button class="tf-primary" type="submit">Buscar</button></div><p>Suelta aquí un archivo para buscar su nombre. Elige el resultado antes de enviarlo.</p></form>
      <div id="tf-results" class="tf-list" aria-label="Resultados de archivos"></div>
    </section>
    <section id="tf-activity-panel" role="tabpanel" aria-labelledby="tf-tab-activity" hidden>
      <div id="tf-history" class="tf-list" aria-label="Actividad del teléfono seleccionado"></div>
      <details><summary>Carpetas y permisos</summary><p>Permite recibir desde el teléfono seleccionado. Buscar y enviar desde esta PC requiere autorizar sus carpetas.</p>
        <form id="tf-permissions"><label class="tf-check"><input id="tf-read" type="checkbox"> Buscar y copiar al teléfono</label><label class="tf-check"><input id="tf-write" type="checkbox"> Recibir archivos del teléfono</label><label for="tf-roots">Carpetas permitidas · una ruta completa por línea</label><textarea id="tf-roots" rows="3" spellcheck="false" placeholder="C:\\Users\\tu usuario\\Documents"></textarea><button type="submit">Guardar permisos</button></form>
      </details>
    </section>`;
  $('panel').append(view);
  const api=async(path,body)=>{if(!A.isNative())throw Error('La transferencia requiere Axx Desktop y un teléfono vinculado.');const r=await A.backendRequest(body===undefined?'GET':'POST','/axx-api/mobile/'+path,body??null);if(r?.error)throw Error(r.error.message||r.error);return r;};
  const element=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const bytes=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
  const labels={preparing:'Preparando copia',ready:'Listo para el teléfono',transferring:'Transfiriendo',receiving:'Recibiendo',paused:'Pausado',completed:'Recibido y verificado',cancelled:'Cancelado',failed:'No se completó',verifying:'Verificando',interrupted:'Interrumpido'};
  let state={devices:[],transfers:[]},refreshing=false,working=false,results=[],seen=new Map(),initialized=false,deviceKey='',historyKey='',receivedKey='',searchRevision=0,grantDirty=false,grantRevision=0,deviceChosen=false,grantKey='',activeTab='received';
  const status=(text,error=false)=>{$('tf-status').textContent=text;$('tf-status').classList.toggle('tf-error',error);};
  const device=()=>state.devices.find(d=>!d.revoked&&d.device_id===$('tf-device').value);
  const deviceLabel=d=>(d.name||'Teléfono')+' · '+d.device_id.slice(-6).toUpperCase();
  const grantDrafts=new Map();
  function invalidateResults(){searchRevision++;results=[];$('tf-results').replaceChildren();historyKey='';}
  function button(text,action){const b=element('button',text);b.type='button';b.onclick=()=>void run(action);return b;}
  async function run(action){if(working)return;working=true;try{await action();}catch(e){status(e.message||String(e),true);}finally{working=false;}}
  function tab(name){activeTab=name;for(const id of ['received','send','activity']){const selected=id===name;$('tf-'+id+'-panel').hidden=!selected;$('tf-tab-'+id).setAttribute('aria-selected',String(selected));$('tf-tab-'+id).tabIndex=selected?0:-1;}$('tf-device-controls').hidden=name==='received';$('tf-heading-title').textContent={received:'Recibidos del teléfono',send:'Enviar al teléfono',activity:'Actividad y permisos'}[name];}
  for(const name of ['received','send','activity'])$('tf-tab-'+name).onclick=()=>tab(name);
  view.querySelector('.tf-tabs').onkeydown=e=>{const names=['received','send','activity'],current=names.indexOf(activeTab);if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?2:(current+(e.key==='ArrowLeft'?-1:1)+3)%3;tab(names[next]);$('tf-tab-'+names[next]).focus();};
  const remove=async t=>{if(!window.confirm('¿Eliminar la copia cifrada de «'+t.name+'» guardada en Axx? Se conservan el recibo, el original y las copias exportadas.'))return;await api('files/remove',{transfer_id:t.transfer_id});await refresh();status('Copia de Axx eliminada. El recibo se conserva.');};
  const saveAs=async t=>{const destination=window.prompt('Ruta completa de un archivo nuevo. La copia exportada queda fuera de la bandeja cifrada de Axx.',t.name);if(!destination)return;await api('files/export',{transfer_id:t.transfer_id,destination});status('Copia guardada en el destino elegido.');};
  function grant(){const d=device();return {...(d?.permissions||{}),roots:d?.roots||[]};}
  function fillGrant(){const draft=grantDrafts.get($('tf-device').value),g=draft||grant();$('tf-read').checked=!!g.read;$('tf-write').checked=!!g.write;$('tf-roots').value=draft?draft.rootsText:(g.roots||[]).map(r=>typeof r==='string'?r:r.path).join('\n');grantDirty=!!draft;}
  function render(){
    const devices=state.devices.filter(d=>!d.revoked).sort((a,b)=>(b.created_at||0)-(a.created_at||0)),key=JSON.stringify(devices.map(d=>[d.device_id,d.name,d.created_at]));
    if(key!==deviceKey){deviceKey=key;const selected=$('tf-device').value,keep=selected&&(deviceChosen||grantDirty);$('tf-device').replaceChildren(...devices.map(d=>new Option(deviceLabel(d)+(d.created_at?' · '+new Date(d.created_at*1000).toLocaleDateString():''),d.device_id)));if(keep){if(!devices.some(d=>d.device_id===selected)){const unavailable=new Option('Enlace '+selected.slice(-6).toUpperCase()+' no disponible · elige otro',selected,true,true);unavailable.disabled=true;$('tf-device').add(unavailable);}$('tf-device').value=selected;}if(!$('tf-device').options.length)$('tf-device').add(new Option('Vincula un teléfono en Ajustes',''));if(selected!==$('tf-device').value||!device())invalidateResults();}
    const nextGrant=JSON.stringify([$('tf-device').value,grant()]);if(!grantDirty&&nextGrant!==grantKey){fillGrant();grantKey=nextGrant;}
    const received=(state.transfers||[]).filter(t=>t.direction==='to_pc'&&t.state==='completed'&&t.stored!==false).sort((a,b)=>(b.completed_at||b.updated_at||b.created_at||0)-(a.completed_at||a.updated_at||a.created_at||0));
    $('tf-received-count').textContent=String(received.length);
    const rk=JSON.stringify([received,devices.map(d=>[d.device_id,d.name])]);
    if(rk!==receivedKey){receivedKey=rk;const list=$('tf-received');list.replaceChildren();
      for(const t of received){
        const row=element('article');row.className='tf-item tf-received-item';row.dataset.transferId=t.transfer_id;
        const mark=element('span',(t.name.split('.').pop()||'Archivo').slice(0,7).toUpperCase());mark.className='tf-file-mark';mark.setAttribute('aria-hidden','true');
        const info=element('div');info.className='tf-file-info';info.append(element('strong',t.name));
        const origin=devices.find(d=>d.device_id===t.device_id)?.name||'Teléfono vinculado',at=t.completed_at||t.updated_at||t.created_at;
        info.append(element('small',origin+' · '+bytes(t.size??t.bytes??0)+(at?' · '+new Date(at*1000).toLocaleString():'')),element('span','Recibido y verificado'));
        info.lastChild.className='tf-verified';const actions=element('div');actions.className='tf-row';
        actions.append(button('Guardar en Descargas',async()=>{const saved=await api('files/save',{transfer_id:t.transfer_id});status('Copia guardada: '+saved.path);}),button('Guardar como…',()=>saveAs(t)),button('Eliminar de Axx',()=>remove(t)));
        row.append(mark,info,actions);list.append(row);
      }
      if(!received.length){const empty=element('div');empty.className='tf-inbox-empty';empty.innerHTML='<span aria-hidden="true">↓</span><strong>Aquí llegan los archivos de tu teléfono</strong><p>En Axx Mobile, abre Archivos → Enviar archivo. Cuando termine y se verifique, aparecerá aquí para guardarlo en tu PC.</p>';empty.append(button('Revisar permisos del teléfono',async()=>{tab('activity');view.querySelector('#tf-activity-panel details').open=true;}));list.append(empty);}
    }
    const rows=(state.transfers||[]).filter(t=>!device()||t.device_id===device().device_id),hk=JSON.stringify(rows);
    if(hk!==historyKey){historyKey=hk;const list=$('tf-history');list.replaceChildren();
      for(const t of rows.slice().reverse().slice(0,40)){
        const row=element('article');row.className='tf-item';row.dataset.transferId=t.transfer_id;
        row.append(element('strong',t.name),element('small',(t.direction==='to_pc'?'Teléfono → Esta PC':'Esta PC → Teléfono')+' · '+(labels[t.state]||t.state)));
        const total=t.size??t.bytes??0,confirmed=t.confirmed_bytes||0;
        if(t.state!=='completed'){const progress=element('progress');progress.max=Math.max(total,1);progress.value=confirmed;progress.setAttribute('aria-label','Bytes confirmados de '+t.name);row.append(progress,element('small',bytes(confirmed)+' de '+bytes(total)));}
        const actions=element('div');actions.className='tf-row';
        if(!['completed','cancelled','failed'].includes(t.state)){actions.append(button(t.state==='paused'?'Reanudar':'Pausar',async()=>{await api('transfers/'+(t.state==='paused'?'resume':'pause'),{transfer_id:t.transfer_id});await refresh();}),button('Cancelar',async()=>{await api('transfers/cancel',{transfer_id:t.transfer_id});await refresh();}));}
        if(t.state==='completed'&&t.direction==='to_pc'&&t.stored!==false)actions.append(button('Guardar como…',()=>saveAs(t)));
        if(['completed','cancelled','failed'].includes(t.state)&&t.stored!==false)actions.append(button('Eliminar copia de Axx',()=>remove(t)));
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
  async function refresh(){if(refreshing)return;refreshing=true;try{state=await api('files/status');render();for(const t of state.transfers||[]){if(initialized&&seen.get(t.transfer_id)!==t.state&&t.state==='completed'){status(t.name+' · Recibido y verificado.');pulse();}seen.set(t.transfer_id,t.state);}initialized=true;if(!$('tf-status').textContent||$('tf-status').textContent==='Comprobando archivos recibidos…')status('Bandeja de todos tus teléfonos vinculados. Solo muestra copias completas y verificadas.');}catch(e){status(e.message||String(e),true);}finally{refreshing=false;}}
  async function search(){const revision=++searchRevision,d=device();if(!d)throw Error('Vincula y elige un teléfono primero.');deviceChosen=true;status('Buscando en tus carpetas autorizadas…');const data=await api('files/search',{device_id:d.device_id,query:$('tf-query').value.trim()});if(revision!==searchRevision||d.device_id!==$('tf-device').value)return;results=data.files||[];$('tf-results').replaceChildren(...results.map(file=>{const row=element('article');row.className='tf-item';row.append(element('strong',file.name),element('small',file.relative_path+' · '+bytes(file.size??file.bytes)+' · '+new Date(file.modified_at*1000).toLocaleString()));row.append(button('Enviar copia al teléfono',async()=>{if(revision!==searchRevision||device()?.device_id!==d.device_id||!results.some(row=>row.file_ref===file.file_ref))throw Error('Cambió el teléfono o la búsqueda. Vuelve a elegir el archivo.');const transfer=await api('transfers/create',{device_id:d.device_id,transfer_id:crypto.randomUUID(),direction:'to_phone',file_ref:file.file_ref});status(file.name+' · '+(labels[transfer.state]||transfer.state));pulse();await refresh();}));return row;}));status(results.length?(results.length+' coincidencias'+(data.truncated?' · limita la búsqueda para ver las restantes.':'. Elige la copia que quieres enviar.')):'No hay coincidencias en las carpetas autorizadas.');}
  $('tf-query').oninput=()=>deviceChosen=true;
  $('tf-search-form').onsubmit=e=>{e.preventDefault();void run(search);};$('tf-refresh').onclick=()=>void refresh();$('tf-device').onchange=()=>{deviceChosen=true;grantRevision++;invalidateResults();fillGrant();render();};
  for(const id of ['tf-read','tf-write','tf-roots'])$(id).oninput=()=>{grantDirty=true;grantRevision++;grantDrafts.set($('tf-device').value,{read:$('tf-read').checked,write:$('tf-write').checked,rootsText:$('tf-roots').value});};
  $('tf-permissions').onsubmit=e=>{e.preventDefault();void run(async()=>{const selected=device(),revision=grantRevision;if(!selected)throw Error('Selecciona un teléfono válido. El borrador sigue asociado a su enlace original.');const read=$('tf-read').checked,draft=grantDrafts.get(selected.device_id);await api('files/permissions',{device_id:selected.device_id,read,write:$('tf-write').checked,roots:$('tf-roots').value.split(/\r?\n/).map(v=>v.trim().replace(/^"(.+)"$/,'$1')).filter(Boolean)});state=await api('files/status');if(grantDrafts.get(selected.device_id)===draft)grantDrafts.delete(selected.device_id);grantDirty=grantDrafts.has($('tf-device').value);if(revision===grantRevision)fillGrant();render();status(read?'Carpetas compartidas con '+deviceLabel(selected)+'. Compruébalas en Archivos del teléfono.':'Permisos guardados para '+deviceLabel(selected)+'. Activa «Buscar y copiar al teléfono» para ver sus carpetas.');});};
  const drop=$('tf-search-form');drop.ondragover=e=>{if(e.dataTransfer?.types.includes('Files')){e.preventDefault();drop.classList.add('drag');}};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');const file=e.dataTransfer?.files?.[0];if(file){$('tf-query').value=file.name;void run(search);}};
  A.FEATURES.push({id:'transfer',family:'actions',title:'Archivos',description:'Enviar y recibir copias con tus teléfonos vinculados.',view:'transfer',availability:'TELÉFONO VINCULADO'});
  if(!A.flow.favorites.includes('transfer')){A.flow.favorites.unshift('transfer');if(A.flow.nav.step===2)A.flow.renderQuick();}
  const previousOpen=A.companion.openFeature.bind(A.companion);A.companion.openFeature=id=>{const result=previousOpen(id);if(id==='transfer'){tab('received');$('panel-title').textContent='Archivos';void refresh();}return result;};
  const open=()=>{tab('received');A.flow.select('transfer');};
  const prior=A.companion.externalCommand;A.companion.externalCommand=raw=>/^(?:abre|abrir|muestra)?\s*(?:axx transfer|transferencias|archivos del telefono)$/.test(A.plain(raw))?async()=>{open();return 'Archivos abierto. Elige un teléfono y sus carpetas autorizadas.';}:prior?.(raw)||null;
  const launch=button('Archivos',async()=>open());launch.id='tf-launch';launch.className='tf-chat-launch';launch.innerHTML=icon+'<span>Archivos</span>';launch.setAttribute('aria-label','Archivos entre esta PC y el teléfono');document.querySelector('.chat20-head-actions')?.append(launch);
  A.transfer={open,refresh};setInterval(()=>{if(!view.hidden)void refresh();},2000);
})();
