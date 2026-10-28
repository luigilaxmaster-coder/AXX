/* One PC-owned character, durable operation tracking, no automatic resubmission. */
(()=>{
  'use strict';
  const $=id=>document.getElementById(id),transport=window.Capacitor?.Plugins?.AxxTransport,key='axx.mobile.avatar.operation';
  const palette=$('character-palette'),form=$('character-form'),finish=$('character-finish'),status=$('character-status');
  const names=['Obsidiana','Nébula','Océano','Atardecer','Amatista','Esmeralda','Champán','Plata','Vacío'];
  Axx.PALETTES.forEach((row,i)=>palette.add(new Option(names[i]||row.name,String(i))));
  Axx.FORMS.forEach((row,i)=>form.add(new Option(row.detail,String(i))));
  let online=false,allowed=false,capable=false,device='',appearance=null,pending=null,checking=false;
  try{pending=JSON.parse(localStorage.getItem(key)||'null');}catch{}
  if(!pending||typeof pending.operation_id!=='string'||typeof pending.device_id!=='string')pending=null;
  const request=async(path,body)=>(await transport.request({path,method:body?'POST':'GET',...(body?{body}:{})})).data;
  function paint(){
    for(const input of [palette,form,finish])input.disabled=!online||!allowed||!capable||!!pending;
    $('character-recover').hidden=!pending;$('character-forget').hidden=!pending;
    if(appearance&&!pending){palette.value=String(appearance.settings?.palette??0);form.value=String(appearance.settings?.form??0);finish.value=appearance.finish||'obsidian';}
  }
  function save(value){if(value)localStorage.setItem(key,JSON.stringify(value));else localStorage.removeItem(key);pending=value;paint();}
  function receipt(result){
    if(result.state==='succeeded'&&result.postconditions_passed===true){
      pending.confirmedAt=pending.confirmedAt||Date.now();pending.expected=result.output;save(pending);status.textContent='Guardado en tu PC · sincronizando…';
    }else if(['failed','blocked','cancelled','expired'].includes(result.state)){
      save(null);status.textContent=result.error?.message||'La PC no aplicó el cambio.';
    }else status.textContent=result.state==='unknown'?'Resultado sin confirmar. Consulta el estado antes de repetir.':'Aplicando en tu PC…';
  }
  async function recover(){
    if(!pending||pending.confirmedAt||!online||!capable||checking)return;
    checking=true;
    const operation=pending.operation_id;
    try{const result=await request('/v1/avatar/operation?operation_id='+encodeURIComponent(operation));if(pending?.operation_id===operation)receipt(result);}
    catch(e){status.textContent='Cambio sin confirmar: '+e.message+'. No se repetirá automáticamente.';}
    finally{checking=false;}
  }
  async function change(inputs){
    if(!online||!allowed||!capable||pending){paint();return;}
    try{
      save({operation_id:crypto.randomUUID(),device_id:device,inputs});status.textContent='Aplicando en tu PC…';
      const operation=pending.operation_id;
      const result=await request('/v1/avatar/customize',{operation_id:operation,device_id:device,inputs});
      if(pending?.operation_id===operation)receipt(result);
    }catch(e){status.textContent='Cambio sin confirmar: '+e.message+'. Consulta su estado antes de repetir.';paint();}
  }
  palette.onchange=()=>void change({action:'settings',palette:Number(palette.value)});
  form.onchange=()=>void change({action:'settings',form:Number(form.value)});
  finish.onchange=()=>void change({action:'finish',finish:finish.value});
  $('character-recover').onclick=()=>void recover();
  $('character-forget').onclick=()=>{
    if(!pending||!confirm('Esto solo descarta el seguimiento. El cambio puede haberse aplicado en la PC. No se repetirá ni cancelará.'))return;
    save(null);status.textContent='Seguimiento descartado. Se muestra la apariencia que comparta la PC.';
  };
  window.addEventListener('axxSnapshot',event=>{
    const value=event.detail;
    if(pending&&value.device_id&&pending.device_id!==value.device_id){save(null);status.textContent='Se ha enlazado otra PC; no se reenviaron cambios.';}
    online=true;device=value.device_id;allowed=value.scopes?.includes('input.control')===true;capable=value.capabilities?.avatar_customization===true;appearance=value.appearance;
    if(pending?.confirmedAt&&appearance){
      const actual={form:appearance.settings?.form,palette:appearance.settings?.palette,finish:appearance.finish};
      const matched=Object.entries(pending.expected||{}).every(([k,v])=>actual[k]===v);
      if(matched){save(null);status.textContent='Sincronizado con tu PC';}
      else if(Date.now()-pending.confirmedAt>6000){save(null);status.textContent='La PC tiene otra apariencia. Se muestra su estado actual.';}
    }
    if(!pending){if(!capable)status.textContent='Actualiza Axx del PC para personalizar desde aquí.';else if(!allowed)status.textContent='Aprueba el control de este teléfono en la PC.';}
    paint();
  });
  window.addEventListener('axxOffline',()=>{online=false;paint();});
  paint();setInterval(()=>void recover(),750);
})();
