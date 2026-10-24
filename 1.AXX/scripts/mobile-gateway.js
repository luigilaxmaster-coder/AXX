/* Mobile shares desktop services and history through authenticated native IPC. */
(function (Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.isNative()) return;
    const c = Axx.companion, $ = id => document.getElementById(id);
    const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/mobile/'+path, body);
    const card = document.createElement('section'); card.className = 'setup-card'; card.id = 'axx-mobile';
    card.innerHTML = '<strong>Conectar teléfono</strong><p id="axx-mobile-status" role="status">Acceso móvil apagado</p><p class="micro-copy">1. Escanea el QR con Axx Mobile. 2. Confirma Connect en el teléfono. 3. Aprueba el control del teléfono abajo.</p><div class="quick-row"><button id="axx-mobile-start">Mostrar QR nuevo</button><button id="axx-mobile-stop">Apagar acceso</button></div><label class="axx-mobile-always"><input id="axx-mobile-always" type="checkbox"> Mantener la conexión disponible al reiniciar Axx</label><p class="micro-copy">Solo los teléfonos emparejados pueden conectarse. Puedes revocar cada teléfono.</p><div id="axx-mobile-pair" hidden><img id="axx-mobile-qr" width="320" height="320" alt="QR de emparejamiento de Axx de un solo uso" style="display:block;background:white;padding:12px;width:320px;max-width:100%;height:auto;margin:12px auto"><p id="axx-mobile-expiry" role="status"></p><details><summary>Usar enlace de emparejamiento</summary><label>Pega este enlace en Axx Mobile<textarea id="axx-mobile-uri" readonly rows="3" style="width:100%"></textarea></label><p id="axx-mobile-fingerprint" class="micro-copy" style="overflow-wrap:anywhere"></p></details><p class="micro-copy">El QR caduca a los dos minutos. Ratón, teclado y movimiento del avatar requieren aprobación desde esta PC.</p></div><details><summary>Teléfonos emparejados</summary><div id="axx-mobile-devices"></div></details>';
    ($('view-settings') || document.body).prepend(card);
    const pairError=document.createElement('p');pairError.id='axx-mobile-error';pairError.setAttribute('role','alert');pairError.hidden=true;
    pairError.style.cssText='color:#ffd1c9;padding:12px;border:1px solid #e8a09580;border-radius:10px';
    $('axx-mobile-status').after(pairError);
    const style=document.createElement('style');style.textContent='#axx-mobile{border:1px solid #98c6e273;border-radius:20px;padding:20px;background:linear-gradient(145deg,#21344db8,#0c182ad9);box-shadow:0 18px 45px #0004;margin-bottom:16px}#axx-mobile>strong{display:block;font-size:20px;margin-bottom:8px;color:#e6f3ff}#axx-mobile-status{padding:11px 13px;border-radius:10px;background:#87ccbe18;border:1px solid #8fd6c84f;color:#c1f2e5;font-size:13px}#axx-mobile .quick-row{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}#axx-mobile .quick-row button{min-height:42px;font-size:13px}#axx-mobile .axx-mobile-always{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid #9ebbd039;border-radius:12px;line-height:1.5;font-size:12px;cursor:pointer}#axx-mobile .axx-mobile-always input{width:19px;height:19px;flex:none}#axx-mobile details{margin-top:12px}';document.head.append(style);
    const connect=document.createElement('button');connect.id='context-mobile';connect.textContent='Connect phone · QR';
    connect.onclick=()=>{Axx.app.openPanel('settings');$('context-menu').hidden=true;card.scrollIntoView({block:'start'});$('axx-mobile-start').click();};
    $('context-menu')?.insertBefore(connect,$('context-menu').querySelector('hr'));
    let enabled=false, syncing=false, expiry, pairDeadline=0, appearanceSyncing=false;
    function appearance(){
        const r=Axx.app.renderer;
        return {settings:Axx.normalizeSettings(Axx.app.store.data.settings),studio:r.getStudio(),camera:r.getCamera20(),finish:r.finish,activity:{state:r.state,moving:r.moving()}};
    }
    async function syncAppearance(){
        if(!enabled || appearanceSyncing)return;
        appearanceSyncing=true;
        try{await api('POST','appearance',appearance());}
        catch(e){$('axx-mobile-status').textContent='Character sync failed: '+(e.message||e);}
        finally{appearanceSyncing=false;}
    }
    if (!c.data.sharedConversationId) { c.data.sharedConversationId=Axx.newId(); c.save(); }
    const originalSave=c.save.bind(c);
    c.save=function(){originalSave(); if(enabled) void sync();};
    async function sync(){
        if(syncing || c.pending || !c.data.prefs.keepHistory) return;
        syncing=true;
        const conversation_id=c.data.sharedConversationId;
        try {
            const messages=c.data.messages.filter(m=>['user','assistant','system'].includes(m.role) && m.status!=='pending' && typeof m.text==='string' && m.at>Date.now()-90*86400000).slice(-200);
            const inference={provider:c.data.prefs.provider||'', provider_name:c.data.prefs.apiConnection||'', model:c.data.prefs.model||'', selection_mode:c.data.prefs.selection_mode||'manual'};
            const result=await api('POST','messages',{conversation_id,messages,inference,appearance:appearance()});
            if(c.data.sharedConversationId!==conversation_id)return;
            const ids=new Set(c.data.messages.map(m=>m.id));
            const incoming=result.messages.filter(m=>!ids.has(m.id));
            if(incoming.length){c.data.messages=[...c.data.messages,...incoming].sort((a,b)=>a.at-b.at).slice(-200);originalSave();c.renderChat();}
        } catch(e){$('axx-mobile-status').textContent='Sync failed: '+(e.message||e);}
        finally{syncing=false;}
    }
    function hidePair(){clearInterval(expiry);$('axx-mobile-pair').hidden=true;$('axx-mobile-uri').value='';$('axx-mobile-qr').removeAttribute('src');}
    function render(info){
        enabled=info.enabled;
        $('axx-mobile-always').checked=!!info.always_on;
        $('axx-mobile-status').textContent=enabled?'Conexión activa · '+info.endpoint:'Acceso móvil apagado';
        const nodes=(info.devices||[]).map(device=>{
            const row=document.createElement('p'); row.textContent=device.name+' · '+(device.revoked?'Revoked':device.scopes.join(', '))+' ';
            if(!device.revoked){const button=document.createElement('button');button.textContent='Revoke';button.onclick=async()=>{try{await api('POST','revoke',{device_id:device.device_id});await refresh();}catch(e){$('axx-mobile-status').textContent=e.message||String(e);}};row.append(button);}
            return row;
        });$('axx-mobile-devices').replaceChildren(...nodes);
        if(!enabled)hidePair();
    }
    async function refresh(){try{render(await api('GET','status'));if(enabled)await sync();}catch(e){$('axx-mobile-status').textContent='Mobile access unavailable: '+(e.message||e);}}
    $('axx-mobile-start').onclick=async()=>{
        pairError.hidden=true;pairError.textContent='';hidePair();
        if(!c.data.prefs.keepHistory){pairError.textContent='Activa Guardar historial en los ajustes de conversación para compartirla con el teléfono.';pairError.hidden=false;return;}
        $('axx-mobile-start').disabled=true;
        try{
            const info=await api('POST','start',{});
            if(!info.qr_svg_base64 || !info.pairing_uri)throw new Error('Axx no generó el QR. Actualiza la aplicación de la PC e inténtalo de nuevo.');
            render(info);$('axx-mobile-uri').value=info.pairing_uri;$('axx-mobile-qr').src='data:image/svg+xml;base64,'+info.qr_svg_base64;
            $('axx-mobile-fingerprint').textContent='PC fingerprint: '+info.fingerprint;$('axx-mobile-pair').hidden=false;
            $('axx-mobile-qr').scrollIntoView({block:'center'});pairDeadline=Date.now()+info.expires_in*1000;
            const tick=()=>{const seconds=Math.max(0,Math.ceil((pairDeadline-Date.now())/1000));$('axx-mobile-expiry').textContent='Escanea el QR en '+seconds+' s';if(!seconds){hidePair();pairError.textContent='El QR caducó. Pulsa Mostrar QR nuevo.';pairError.hidden=false;}};
            tick();expiry=setInterval(tick,1000);void sync();
        }
        catch(e){pairError.textContent='No se pudo mostrar el QR: '+(e.message||e);pairError.hidden=false;}
        finally{$('axx-mobile-start').disabled=false;}
    };
    $('axx-mobile-stop').onclick=async()=>{try{render(await api('POST','stop',{}));}catch(e){$('axx-mobile-status').textContent=e.message||String(e);}};
    $('axx-mobile-always').onchange=async()=>{const checkbox=$('axx-mobile-always');checkbox.disabled=true;try{render(await api('POST','always-access',{enabled:checkbox.checked}));}catch(e){checkbox.checked=!checkbox.checked;$('axx-mobile-status').textContent='No se pudo cambiar el acceso: '+(e.message||e);}finally{checkbox.disabled=false;}};
    setInterval(()=>void refresh(),5000);setInterval(()=>void syncAppearance(),1000);void refresh();
})(window.Axx);
