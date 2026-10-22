/* Mobile shares desktop services and history through authenticated native IPC. */
(function (Axx) {
    'use strict';
    if (!Axx?.companion || !Axx.isNative()) return;
    const c = Axx.companion, $ = id => document.getElementById(id);
    const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/mobile/'+path, body);
    const card = document.createElement('section'); card.className = 'setup-card'; card.id = 'axx-mobile';
    card.innerHTML = '<strong>Connect your phone</strong><p id="axx-mobile-status" role="status">Mobile access is off</p><p class="micro-copy">Open Axx Mobile → Pair PC → Scan QR. Both devices must use the same local network.</p><div class="quick-row"><button id="axx-mobile-start">Show new QR</button><button id="axx-mobile-stop">Turn off</button></div><div id="axx-mobile-pair" hidden><img id="axx-mobile-qr" width="320" height="320" alt="One-use Axx pairing QR" style="display:block;background:white;padding:12px;width:320px;max-width:100%;height:auto;margin:12px auto"><p id="axx-mobile-expiry" role="status"></p><details><summary>Use a pairing link instead</summary><label>Paste this link in Axx Mobile<textarea id="axx-mobile-uri" readonly rows="3" style="width:100%"></textarea></label><p id="axx-mobile-fingerprint" class="micro-copy" style="overflow-wrap:anywhere"></p></details><p class="micro-copy">Allow camera access on Android. A new QR replaces the previous code. Pairing grants conversation and voice access; remote input requires separate approval.</p></div><details><summary>Paired devices</summary><div id="axx-mobile-devices"></div></details>';
    ($('view-settings') || document.body).prepend(card);
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
            const messages=c.data.messages.filter(m=>['user','assistant','system'].includes(m.role) && m.status!=='pending' && typeof m.text==='string');
            const inference={provider:c.data.prefs.provider||'', provider_name:c.data.prefs.apiConnection||'', model:c.data.prefs.model||''};
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
        $('axx-mobile-status').textContent=enabled?'Local access active · '+info.endpoint:'Mobile access is off';
        const nodes=(info.devices||[]).map(device=>{
            const row=document.createElement('p'); row.textContent=device.name+' · '+(device.revoked?'Revoked':device.scopes.join(', '))+' ';
            if(!device.revoked){const button=document.createElement('button');button.textContent='Revoke';button.onclick=async()=>{try{await api('POST','revoke',{device_id:device.device_id});await refresh();}catch(e){$('axx-mobile-status').textContent=e.message||String(e);}};row.append(button);}
            return row;
        });$('axx-mobile-devices').replaceChildren(...nodes);
        if(!enabled)hidePair();
    }
    async function refresh(){try{render(await api('GET','status'));if(enabled)await sync();}catch(e){$('axx-mobile-status').textContent='Mobile access unavailable: '+(e.message||e);}}
    $('axx-mobile-start').onclick=async()=>{
        if(!c.data.prefs.keepHistory){$('axx-mobile-status').textContent='Enable Keep history in Conversation settings before sharing this conversation with your phone.';return;}
        $('axx-mobile-start').disabled=true;
        try{const info=await api('POST','start',{});render(info);await sync();$('axx-mobile-uri').value=info.pairing_uri;$('axx-mobile-qr').src='data:image/svg+xml;base64,'+info.qr_svg_base64;$('axx-mobile-fingerprint').textContent='PC fingerprint: '+info.fingerprint;$('axx-mobile-pair').hidden=false;$('axx-mobile-qr').scrollIntoView({block:'center'});clearInterval(expiry);pairDeadline=Date.now()+info.expires_in*1000;const tick=()=>{const seconds=Math.max(0,Math.ceil((pairDeadline-Date.now())/1000));$('axx-mobile-expiry').textContent='Scan within '+seconds+' s';if(!seconds){hidePair();$('axx-mobile-status').textContent='QR expired. Select Show new QR to try again.';}};tick();expiry=setInterval(tick,1000);}
        catch(e){$('axx-mobile-status').textContent='Could not enable access: '+(e.message||e);}
        finally{$('axx-mobile-start').disabled=false;}
    };
    $('axx-mobile-stop').onclick=async()=>{try{render(await api('POST','stop',{}));}catch(e){$('axx-mobile-status').textContent=e.message||String(e);}};
    setInterval(()=>void refresh(),5000);setInterval(()=>void syncAppearance(),1000);void refresh();
})(window.Axx);
