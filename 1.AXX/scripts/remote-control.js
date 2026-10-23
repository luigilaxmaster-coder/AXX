/* Share the live character's material; Windows owns input, expiry and local priority. */
(function(Axx){
  'use strict';
  if(!Axx?.isNative())return;
  const $=id=>document.getElementById(id),api=(method,path,body)=>Axx.backendRequest(method,'/axx-api/mobile/'+path,body);
  const card=document.createElement('section');card.className='setup-card';card.id='axx-remote-control';
  card.innerHTML='<strong>Control desde el teléfono</strong><p class="micro-copy">Después de escanear el QR, aprueba aquí cada teléfono una sola vez. La aprobación queda guardada hasta que la revoques.</p><div id="rc-approval-list" aria-label="Teléfonos pendientes y aprobados"></div><button id="rc-stop">DETENER CONTROL AHORA</button><p id="rc-status" role="status">Sin control remoto</p><details><summary>Apariencia del cursor remoto</summary><label>Tamaño del contorno<input id="rc-size" type="range" min="36" max="64" value="48"></label><label>Intensidad<input id="rc-intensity" type="range" min="0.3" max="1" step="0.05" value="0.9"></label><label>Iluminación<input id="rc-glow" type="range" min="0" max="0.25" step="0.01" value="0.12"></label><label><input id="rc-reduced" type="checkbox"> Reducir movimiento del indicador</label></details><p class="micro-copy">El ratón físico y Escape en la PC detienen el control. Las ventanas elevadas y el escritorio seguro pueden rechazarlo.</p>';
  const mobileCard=$('axx-mobile');if(mobileCard)mobileCard.after(card);else ($('view-settings')||document.body).append(card);
  const style=document.createElement('style');style.textContent='#axx-remote-control{border:1px solid #a8c9e05a;border-radius:20px;padding:20px;background:linear-gradient(145deg,#203047b8,#0d1726db);box-shadow:0 15px 42px #0004;margin:0 0 18px}#axx-remote-control>strong{display:block;font-size:20px;color:#e8f4ff;margin-bottom:8px}#rc-approval-list{display:grid;gap:10px;margin:14px 0}#rc-approval-list .rc-phone{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px;border:1px solid #9bbcd050;border-radius:13px;background:#9fb9d40b}#rc-approval-list .rc-phone.pending{border-color:#e5bf7396;background:#f0bb5b13}#rc-approval-list .rc-phone strong{display:block;color:#e6f0fa;font-size:13px}#rc-approval-list .rc-phone small{display:block;color:#aabed0;font-size:11px;margin-top:4px}#rc-approval-list .rc-phone-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}#rc-approval-list button{min-height:40px;font-size:12px;flex:none}#rc-approval-list .rc-empty{font-size:12px;color:#adc1d5;padding:13px;border:1px dashed #9bbcd050;border-radius:12px}#rc-status{padding:10px 12px;border-radius:10px;background:#86c3d418;color:#c7e8f2;font-size:12px}#axx-remote-control details{margin-top:14px}#axx-remote-control details label{display:block;margin:8px 0}';document.head.append(style);
  let devices=[],busy=false,materialKey='',approvalBusy=false,deviceKey='';
  let prefs={};try{prefs=JSON.parse(localStorage.getItem('axx.remoteControl')||'{}');}catch{}
  for(const key of ['size','intensity','glow'])if(Number.isFinite(prefs[key]))$('rc-'+key).value=prefs[key];
  $('rc-reduced').checked=prefs.reduced===true;
  function renderDevices(){
    const key=JSON.stringify(devices.map(d=>[d.device_id,d.name,d.scopes]));if(key===deviceKey)return;deviceKey=key;
    const nodes=devices.slice().sort((a,b)=>Number(a.scopes.includes('input.control'))-Number(b.scopes.includes('input.control'))||b.created_at-a.created_at).map(d=>{
      const approved=d.scopes.includes('input.control'),work=d.scopes.includes('tools.control'),row=document.createElement('div');row.className='rc-phone'+(approved&&work?'':' pending');
      const copy=document.createElement('div'),name=document.createElement('strong'),state=document.createElement('small'),actions=document.createElement('div');
      name.textContent=d.name+' · '+d.device_id.slice(0,8);state.textContent='Control: '+(approved?'aprobado':'pendiente')+' · Work: '+(work?'aprobado':'pendiente');
      for(const [permission,current,label] of [['input-permission',approved,'control'],['tools-permission',work,'Work']]){
        const button=document.createElement('button');button.textContent=current?'Quitar '+label:'Aprobar '+label;
        button.setAttribute('aria-label',(current?'Quitar ':'Aprobar ')+label+' a '+d.name);
        button.onclick=async()=>{if(approvalBusy)return;approvalBusy=true;button.disabled=true;try{await api('POST',permission,{device_id:d.device_id,enabled:!current});deviceKey='';await poll();}catch(e){$('rc-status').textContent='No se pudo cambiar el permiso: '+(e.message||e);}finally{approvalBusy=false;button.disabled=false;}};
        actions.append(button);
      }
      actions.className='rc-phone-actions';copy.append(name,state);row.append(copy,actions);return row;
    });
    if(!nodes.length){const empty=document.createElement('p');empty.className='rc-empty';empty.textContent='Aún no hay teléfonos. Pulsa «Mostrar QR nuevo» arriba para conectar uno.';nodes.push(empty);}
    $('rc-approval-list').replaceChildren(...nodes);
  }
  $('rc-stop').onclick=async()=>{try{await api('POST','control/cancel',{});$('rc-status').textContent='Control stopped';}catch(e){$('rc-status').textContent=e.message;}};
  for(const id of ['size','intensity','glow','reduced'])$('rc-'+id).onchange=()=>{localStorage.setItem('axx.remoteControl',JSON.stringify(options()));void poll();};
  function options(){return {size:Number($('rc-size').value),intensity:Number($('rc-intensity').value),glow:Number($('rc-glow').value),reduced:$('rc-reduced').checked||matchMedia('(prefers-reduced-motion: reduce)').matches};}
  async function poll(){
    if(busy)return;busy=true;
    try{
      const access=await api('GET','status');devices=(access.devices||[]).filter(d=>!d.revoked);
      renderDevices();
      // Desktop automation uses the same owner and indicator even without a paired phone.
      const r=Axx.app?.renderer;
      if(r?.materialTable){
        const table=r.materialTable(),body={key:r.lutKey,...options()};
        if(materialKey!==body.key){
          const bytes=new Uint8Array(128*128*4);
          for(let y=0;y<128;y++)for(let x=0;x<128;x++){
            const i=(Math.round(y*511/127)*512+Math.round(x*511/127))*4;
            bytes.set(table.subarray(i,i+4),(y*128+x)*4);
          }
          let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));body.table=btoa(binary);
        }
        await api('POST','control/material',body);materialKey=body.key;
      }
      const state=await api('GET','control/status'),n=state.native;
      $('rc-status').textContent=n.active?(n.source==='axx_automation'?'Axx controla la aplicación':'Control desde el teléfono')+' · '+n.cursor.x+', '+n.cursor.y+' · teclas: '+(n.keys.join(', ')||'ninguna'):'Entrada física del usuario · '+(n.reason||'disponible');
    }catch(e){materialKey='';$('rc-status').textContent='Control unavailable: '+e.message;}
    finally{busy=false;}
  }
  setInterval(()=>void poll(),1000);void poll();
})(window.Axx);
