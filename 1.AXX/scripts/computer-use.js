/* Explicit window grant; visual tools share the existing chat and input owner. */
(function(Axx){
  'use strict';
  if(!Axx?.isNative()||!Axx.chatWorkspace)return;
  const host=document.getElementById('chat-workspace');if(!host)return;
  const ui=document.createElement('section');ui.id='computer-use';
  ui.innerHTML=`<style>
    #computer-use{border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0;font-size:12px}
    #computer-use p{line-height:1.5;color:var(--secondary)}#computer-use label{display:block;margin:10px 0}
    #computer-use input[type=checkbox]{width:auto;margin-right:8px}#computer-use select{width:100%;margin:8px 0}
    #computer-use [hidden]{display:none!important}#computer-use .cu-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    #cu-live{font-weight:600;color:var(--ink)}
  </style><div class="cu-row"><button type="button" id="cu-open" aria-expanded="false">Computer Use</button>
  <span id="cu-live" role="status" aria-live="polite">Desactivado</span><button type="button" id="cu-stop" hidden>Detener</button></div>
  <div id="cu-setup" hidden><p>Conecta ChatGPT en Ajustes. Autoriza una ventana y pide la tarea en este chat. Codex recibirá imágenes y texto de esa ventana. La sesión dura hasta 15 minutos o 60 gestos.</p>
  <label>Ventana autorizada<select id="cu-window" aria-label="Ventana autorizada"></select></label>
  <button type="button" id="cu-refresh">Actualizar ventanas</button>
  <label><input id="cu-images" type="checkbox">Permito enviar imágenes y texto de esta ventana a Codex.</label>
  <label><input id="cu-input" type="checkbox">Permito controlar su mouse y teclado para mis solicitudes.</label>
  <button type="button" id="cu-start">Autorizar esta ventana</button>
  <p>Evite ventanas con datos que no quiera compartir. Puede detener con este botón o Escape desde Axx. Una acción incierta requiere revisión en Comandos.</p></div>
  <p id="cu-error" role="alert" hidden></p>`;
  host.append(ui);
  const $=id=>document.getElementById(id);let grant=null,chat=null,windows=[],polling=false;
  const api=async(method,action,body)=>{const r=await Axx.backendRequest(method,'/axx-api/computer/'+action,body);if(r?.error)throw Error(r.error.message||'Computer Use no disponible.');return r;};
  const error=e=>{$('cu-error').hidden=false;$('cu-error').textContent=e.message||String(e);};
  function render(){
    $('cu-stop').hidden=!grant?.active;
    $('cu-live').textContent=grant?.active?`${grant.blocked?'Revisión requerida':'Activo'} · ${grant.title} · ${grant.actions}/60`:'Desactivado';
    $('cu-start').disabled=Boolean(grant?.active);Axx.resident?.schedule();
  }
  async function stop(){
    if(!chat)return;
    const current=chat;$('cu-live').textContent='Deteniendo…';
    try{await api('POST','stop',{conversation_id:current});if(chat===current){chat=null;grant=null;render();}}
    catch(e){error(e);throw e;}
  }
  async function refresh(){
    const r=await Axx.backendRequest('POST','/axx-api/commands/prepare',{command_id:'axx.desktop.list_windows',inputs:{},operation_id:crypto.randomUUID()});
    if(r?.error)throw Error(r.error.message);let result=await Axx.backendRequest('POST','/axx-api/commands/execute',{operation_id:r.operation_id,approved:false});
    for(let i=0;i<60&&['prepared','running','queued'].includes(result.state);i++){
      await new Promise(resolve=>setTimeout(resolve,250));result=(await Axx.backendRequest('GET','/axx-api/commands/operations?operation_id='+encodeURIComponent(r.operation_id))).operation;
    }
    if(result?.state!=='succeeded')throw Error(result?.error?.message||'No se confirmaron las ventanas.');
    windows=result.output?.windows||[];$('cu-window').replaceChildren();
    for(const [index,row]of windows.entries()){const option=document.createElement('option');option.value=String(index);option.textContent=`${row.title} · PID ${row.pid}`;$('cu-window').append(option);}
    if(!windows.length)throw Error('No hay ventanas disponibles.');
  }
  async function start(){
    const current=Axx.chatWorkspace.active?.id;if(!current)throw Error('Seleccione un chat.');
    if(Axx.companion.data.prefs.provider!=='chatgpt')throw Error('Seleccione ChatGPT en Ajustes antes de autorizar.');
    const row=windows[Number($('cu-window').value)];if(!row)throw Error('Seleccione una ventana observada.');
    $('cu-start').disabled=true;
    try{
      const result=await api('POST','begin',{conversation_id:current,window_id:row.window_id,pid:row.pid,image_authorized:$('cu-images').checked,allow_input:$('cu-input').checked});
      chat=current;grant=result;
      if(Axx.chatWorkspace.active?.id!==current){await stop();return;}
      $('cu-setup').hidden=true;$('cu-open').setAttribute('aria-expanded','false');$('cu-images').checked=$('cu-input').checked=false;render();
    }finally{render();}
  }
  const run=fn=>async()=>{$('cu-error').hidden=true;try{await fn();}catch(e){error(e);}};
  $('cu-open').onclick=run(async()=>{const open=$('cu-setup').hidden;$('cu-setup').hidden=!open;$('cu-open').setAttribute('aria-expanded',String(open));if(open)await refresh();});
  $('cu-refresh').onclick=run(refresh);$('cu-start').onclick=run(start);$('cu-stop').onclick=run(stop);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&chat)void stop().catch(error);});
  setInterval(async()=>{
    if(!chat||polling)return;polling=true;
    try{
      if(Axx.chatWorkspace.active?.id!==chat||Axx.companion.data.prefs.provider!=='chatgpt'){await stop();return;}
      const current=chat,r=await api('GET','status?conversation_id='+encodeURIComponent(current));
      if(current===chat){grant=r;render();if(!r.active)chat=null;}
    }catch(e){error(e);}finally{polling=false;}
  },1500);
  Axx.computerUse={activeFor:id=>Boolean(grant?.active&&chat===id),stop};render();
})(window.Axx);
