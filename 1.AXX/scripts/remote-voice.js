/* The existing desktop conversation owns interpretation and mandatory approvals. */
(function(Axx){
    'use strict';
    if(!Axx?.isNative() || !Axx.companion)return;
    const c=Axx.companion,$=id=>document.getElementById(id);
    const api=(method,path,body)=>Axx.backendRequest(method,'/axx-api/mobile/'+path,body);
    const card=document.createElement('section');card.className='setup-card';card.id='axx-remote-voice';
    card.innerHTML='<strong>Remote microphone · Android</strong><p id="remote-voice-shortcut">Ctrl + Alt + Shift + V · start / stop</p><p id="remote-voice-status" role="status">Open Axx Mobile and allow microphone access.</p><label>Phone<select id="remote-voice-device"></select></label><label>Delivery<select id="remote-voice-mode"><option value="confirm">Review text on the PC</option><option value="handsfree">Hands-free</option></select></label><label>Session limit (seconds)<input id="remote-voice-limit" type="number" min="5" max="55" value="30"></label><label><input id="remote-voice-tools" type="checkbox"> Authorize tools for this phone. Axx still requires sensitive-action confirmations.</label><div class="quick-row"><button id="remote-voice-toggle">Start / stop microphone</button><button id="remote-voice-cancel">Cancel session</button></div><p class="micro-copy">Keep the Android app visible. Local Whisper transcribes audio on this PC when capture ends. Voice does not take mouse or keyboard control.</p><div id="remote-voice-review" hidden><label>Final transcript · you can edit it<textarea id="remote-voice-text" maxlength="10000" rows="4" style="width:100%"></textarea></label><button id="remote-voice-confirm">Process in Axx</button></div><p id="remote-voice-result" style="white-space:pre-wrap"></p>';
    ($('view-settings')||document.body).append(card);
    let prefs={};try{prefs=JSON.parse(localStorage.getItem('axx.remoteVoice')||'{}');}catch{}
    $('remote-voice-mode').value=prefs.mode==='handsfree'?'handsfree':'confirm';$('remote-voice-limit').value=prefs.max_seconds||30;
    let polling=false,toggling=false,dispatching=false,session=null,reviewId='',devices=[];
    const status=text=>{$('remote-voice-status').textContent=text;};
    const labels={requested:'Requesting the phone microphone…',recording:'Listening on Android · press the shortcut again to finish',stopping:'Stopping capture…',awaiting_audio:'Receiving audio…',transcribing:'Whisper is transcribing on this PC…',review:'Final text · awaiting your confirmation',ready:'Confirmed text · waiting for Axx',dispatching:'Command sent to desktop Axx',completed:'Axx processed the command; check its result',empty:'No speech recognized',failed:'Session failed',interrupted:'Session interrupted · will not send automatically',outcome_unknown:'Result unconfirmed · command will not be repeated',cancelled:'Session cancelled'};
    function save(){prefs={device_id:$('remote-voice-device').value,mode:$('remote-voice-mode').value,max_seconds:Number($('remote-voice-limit').value)};localStorage.setItem('axx.remoteVoice',JSON.stringify(prefs));}
    function showPermission(){const device=devices.find(d=>d.device_id===$('remote-voice-device').value);$('remote-voice-tools').checked=!!device?.scopes.includes('tools.control');}
    $('remote-voice-device').onchange=()=>{save();showPermission();};$('remote-voice-mode').onchange=save;$('remote-voice-limit').onchange=save;
    $('remote-voice-tools').onchange=async()=>{try{const device_id=$('remote-voice-device').value;if(!device_id)throw new Error('Select a phone');await api('POST','tools-permission',{device_id,enabled:$('remote-voice-tools').checked});await poll();}catch(e){status(e.message||String(e));showPermission();}};
    async function toggle(){
        if(toggling)return;toggling=true;
        try{save();session=await api('POST','voice/toggle',{...prefs,conversation_id:c.data.sharedConversationId});status(labels[session.state]);}
        catch(e){status(e.message||String(e));Axx.app.toast(e.message||String(e));}
        finally{toggling=false;}
    }
    $('remote-voice-toggle').onclick=()=>void toggle();
    $('remote-voice-cancel').onclick=async()=>{if(!session)return;try{session=await api('POST','voice/cancel',{session_id:session.session_id});status(labels[session.state]);}catch(e){status(e.message||String(e));}};
    $('remote-voice-confirm').onclick=async()=>{if(!session)return;try{await api('POST','voice/confirm',{session_id:session.session_id,text:$('remote-voice-text').value});await poll();}catch(e){status(e.message||String(e));}};
    async function dispatch(s){
        if(dispatching || c.pending || c.externalBusy || c.attachment)return;
        dispatching=true;
        try{
            const admitted=await api('POST','voice/claim',{session_id:s.session_id,conversation_id:c.data.sharedConversationId});
            if(!admitted.execute)return;
            const previous=new Set(c.data.messages.map(m=>m.id));
            await c.send(admitted.session.confirmed_text,{source:'voice'});
            const messages=c.data.messages.filter(m=>!previous.has(m.id)).map(m=>({id:m.id,role:m.role,text:m.text.slice(0,20000),status:m.status})).slice(-4);
            const receipt={session_id:s.session_id,result:{messages,operation:Axx.commandLibrary?.lastOperation?.operation_id||null}};
            localStorage.setItem('axx.remoteVoice.receipt',JSON.stringify(receipt));
            await api('POST','voice/finish',receipt);localStorage.removeItem('axx.remoteVoice.receipt');
        }catch(e){status('Result not confirmed: '+(e.message||e)+'. It will not be sent again automatically.');}
        finally{dispatching=false;}
    }
    async function poll(){
        if(polling)return;polling=true;
        try{
            const receipt=localStorage.getItem('axx.remoteVoice.receipt');
            if(receipt){await api('POST','voice/finish',JSON.parse(receipt));localStorage.removeItem('axx.remoteVoice.receipt');}
            const [info,access]=await Promise.all([api('GET','voice/status'),api('GET','status')]);
            devices=(access.devices||[]).filter(d=>!d.revoked);
            const select=$('remote-voice-device'),selected=select.value||prefs.device_id||'';
            const markup=JSON.stringify(devices.map(d=>[d.device_id,d.name]));
            if(select.dataset.devices!==markup){select.replaceChildren(new Option('Select a phone',''),...devices.map(d=>new Option(d.name,d.device_id)));select.dataset.devices=markup;select.value=selected;if(!select.value && devices.length===1){select.value=devices[0].device_id;save();}showPermission();}
            const connected=info.clients.filter(d=>d.connected&&d.visible&&devices.some(device=>device.device_id===d.device_id));
            if(connected.length===1&&!info.clients.some(d=>d.device_id===select.value&&d.connected)){
                select.value=connected[0].device_id;save();showPermission();
            }
            session=info.session;
            if(!session){const client=info.clients.find(d=>d.device_id===select.value);status(client?.connected && client.visible && client.permission==='granted'?'Remote microphone ready · press Ctrl + Alt + Shift + V':'Open Axx Mobile and allow microphone access.');return;}
            status(labels[session.state]+(session.error?' · '+session.error:''));
            $('remote-voice-review').hidden=session.state!=='review';
            if(session.state==='review' && reviewId!==session.session_id){$('remote-voice-text').value=session.text;reviewId=session.session_id;}
            $('remote-voice-result').textContent=session.result?.messages?.filter(m=>m.role==='assistant').map(m=>m.text).join('\n') || '';
            if(session.state==='ready')void dispatch(session);
        }catch(e){status('Remote voice unavailable: '+(e.message||e));}
        finally{polling=false;}
    }
    void Axx.app.bridge.listen('axx-remote-voice-toggle',()=>void toggle());
    void Axx.nativeInvoke('native_status').then(info=>{if(info.remoteVoiceShortcutError)$('remote-voice-shortcut').textContent=info.remoteVoiceShortcutError;});
    setInterval(()=>void poll(),1000);void poll();
})(window.Axx);
