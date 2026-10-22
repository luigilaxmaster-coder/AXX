/* Share the live character's material; Windows owns input, expiry and local priority. */
(function(Axx){
  'use strict';
  if(!Axx?.isNative())return;
  const $=id=>document.getElementById(id),api=(method,path,body)=>Axx.backendRequest(method,'/axx-api/mobile/'+path,body);
  const card=document.createElement('section');card.className='setup-card';card.id='axx-remote-control';
  card.innerHTML='<strong>Mouse and keyboard · Android</strong><p>Your physical mouse and keyboard take immediate priority. Press Escape on the PC to stop control, even without a network.</p><label>Phone<select id="rc-device"></select></label><label><input type="checkbox" id="rc-permit"> Allow mouse and keyboard control for this phone</label><button id="rc-stop">STOP CONTROL</button><p id="rc-status" role="status">No remote control</p><label>Outline size<input id="rc-size" type="range" min="36" max="64" value="48"></label><label>Intensity<input id="rc-intensity" type="range" min="0.3" max="1" step="0.05" value="0.9"></label><label>Surface light<input id="rc-glow" type="range" min="0" max="0.25" step="0.01" value="0.12"></label><label><input id="rc-reduced" type="checkbox"> Reduce indicator motion</label><p class="micro-copy">The material comes from your current character. The Windows cursor stays unchanged. Elevated windows and the secure desktop may reject input.</p>';
  ($('view-settings')||document.body).append(card);
  let devices=[],busy=false,materialKey='';
  let prefs={};try{prefs=JSON.parse(localStorage.getItem('axx.remoteControl')||'{}');}catch{}
  for(const key of ['size','intensity','glow'])if(Number.isFinite(prefs[key]))$('rc-'+key).value=prefs[key];
  $('rc-reduced').checked=prefs.reduced===true;
  function permission(){const d=devices.find(d=>d.device_id===$('rc-device').value);$('rc-permit').checked=!!d?.scopes.includes('input.control');}
  $('rc-device').onchange=permission;
  $('rc-permit').onchange=async()=>{try{await api('POST','input-permission',{device_id:$('rc-device').value,enabled:$('rc-permit').checked});await poll();}catch(e){$('rc-status').textContent=e.message;permission();}};
  $('rc-stop').onclick=async()=>{try{await api('POST','control/cancel',{});$('rc-status').textContent='Control stopped';}catch(e){$('rc-status').textContent=e.message;}};
  for(const id of ['size','intensity','glow','reduced'])$('rc-'+id).onchange=()=>{localStorage.setItem('axx.remoteControl',JSON.stringify(options()));void poll();};
  function options(){return {size:Number($('rc-size').value),intensity:Number($('rc-intensity').value),glow:Number($('rc-glow').value),reduced:$('rc-reduced').checked||matchMedia('(prefers-reduced-motion: reduce)').matches};}
  async function poll(){
    if(busy)return;busy=true;
    try{
      const access=await api('GET','status');devices=(access.devices||[]).filter(d=>!d.revoked);
      const select=$('rc-device'),selected=select.value,identity=JSON.stringify(devices);
      if(select.dataset.devices!==identity){select.replaceChildren(new Option('Select a phone',''),...devices.map(d=>new Option(d.name,d.device_id)));select.dataset.devices=identity;select.value=selected;if(!select.value&&devices.length===1)select.value=devices[0].device_id;permission();}
      if(!access.enabled){materialKey='';return;}
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
      $('rc-status').textContent=n.active?'Android control granted · '+n.cursor.x+', '+n.cursor.y+' · keys: '+(n.keys.join(', ')||'none'):'No remote control · '+(n.reason||'ready');
    }catch(e){materialKey='';$('rc-status').textContent='Control unavailable: '+e.message;}
    finally{busy=false;}
  }
  setInterval(()=>void poll(),1000);void poll();
})(window.Axx);
