/* Explicit window grant; visual tools share the existing chat and input owner. */
(function(Axx){
 'use strict';
 if(!Axx?.isNative()||!Axx.chatWorkspace)return;
 const $=id=>document.getElementById(id),host=$('chat-workspace');if(!host)return;
 const c=Axx.companion,view=document.createElement('section');view.id='view-computeruse';view.className='panel-view';view.hidden=true;
 const screen='<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2" y="3" width="20" height="14" rx="3"/><path d="M8 21h8M12 17v4m-4-9 3-6 3 6-3-1z"/></svg>';
 view.innerHTML=`<style>
 #computer-use{color:var(--ink);font-family:var(--interface-font,"Segoe UI",sans-serif)}
 #computer-use [hidden]{display:none!important}#computer-use p{line-height:1.6;color:var(--secondary)}
 #computer-use .cu-status{padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface-subtle)}
 #computer-use .cu-status strong{display:block;margin-bottom:4px}#computer-use .cu-status p{margin:0}
 #computer-use .cu-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 #computer-use ol{list-style:none;padding:0;margin:16px 0;counter-reset:cu}
 #computer-use li{position:relative;counter-increment:cu;padding:16px 12px 16px 44px;border-bottom:1px solid var(--line)}
 #computer-use li:before{content:counter(cu);position:absolute;left:8px;top:16px;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--surface-raised);color:var(--secondary)}
 #computer-use li[data-ready=true]:before{content:'✓';color:var(--success,#287355)}
 #computer-use h3{margin:0;font-size:14px}#computer-use li p{margin:7px 0 10px;font-size:12px}
 #computer-use label{display:block;margin:10px 0;font-size:12px}#computer-use select{width:100%;margin:6px 0}
 #computer-use input[type=checkbox]{width:auto;margin-right:8px}#computer-use .cu-note{font-size:12px}
 #cu-start{min-height:44px}#cu-live{font-weight:600}#cu-error{color:var(--danger,#b53a3a)}
 .cu-chat-entry{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0;padding:6px 10px;border:1px solid var(--line);border-radius:10px;color:var(--secondary);font-size:11px}
 .cu-chat-entry button{min-height:40px}.cu-launch{display:inline-flex;align-items:center;gap:6px;min-height:40px;border-radius:9px;background:var(--button);color:var(--ink);border:1px solid var(--line);padding:6px 10px}
 .cu-launch svg{width:20px;height:20px;flex:none}#panel:has(#view-chat.cw-narrow) .cu-launch span{display:none}
 </style><div id="computer-use">
 <h2>Controlar una ventana con Axx</h2>
 <p>Computer Use permite que Axx vea una ventana y use su mouse y teclado para la tarea que le pidas.</p>
 <div class="cu-status"><strong id="cu-live" role="status" aria-live="polite">Sin autorizar</strong><p id="cu-chat"></p><p id="cu-diagnostic" role="alert" hidden></p><button type="button" id="cu-stop" hidden>Detener y quitar autorización</button></div>
 <ol>
 <li id="cu-step-model"><h3>Conectar y comprobar ChatGPT</h3><p id="cu-model" role="status">Comprueba la conexión antes de habilitar el control.</p><div class="cu-row"><button type="button" id="cu-connect">Abrir conexión de ChatGPT</button><button type="button" id="cu-check">Comprobar estado</button></div><p>En Conectar IA, inicia sesión y pulsa «Probar respuesta y usar modelo». Después vuelve aquí y comprueba el estado.</p></li>
 <li id="cu-step-window"><h3>Elegir la ventana</h3><p>Axx solo tendrá acceso a la ventana que selecciones, no a todo el escritorio.</p><label>Ventana que Axx podrá ver y controlar<select id="cu-window" aria-label="Ventana autorizada"><option value="">Primero busca las ventanas abiertas</option></select></label><button type="button" id="cu-refresh">Buscar ventanas abiertas</button><p id="cu-window-status" role="status"></p></li>
 <li id="cu-step-permission"><h3>Habilitar para este chat</h3><label><input id="cu-images" type="checkbox">Permito enviar imágenes y texto de esta ventana a Codex.</label><label><input id="cu-input" type="checkbox">Permito usar el mouse y teclado de esta ventana para mis solicitudes.</label><button type="button" id="cu-start" disabled>Habilitar Computer Use para este chat</button><p id="cu-next" role="status"></p></li>
 </ol>
 <div class="cu-row"><button type="button" id="cu-chat-open">Volver al chat</button><button type="button" id="cu-review" hidden>Revisar acción pendiente</button></div>
 <p class="cu-note">Pide la tarea en el chat, por ejemplo: «En la ventana autorizada, busca Faint de Linkin Park». La autorización termina a los 15 minutos o 60 gestos. Puedes detenerla aquí o con Escape desde Axx.</p>
 <p class="cu-note">Evita ventanas con información que no quieras compartir. Los efectos ya realizados se conservan al detener.</p><p id="cu-error" role="alert" hidden></p></div>`;
 ($('panel')||document.body).append(view);
 const entry=document.createElement('div');entry.className='cu-chat-entry';entry.innerHTML='<span id="cu-chat-status">Computer Use · Sin autorizar</span><button id="cu-open" type="button" aria-controls="view-computeruse">Configurar control del PC</button>';host.append(entry);
 const launcher=document.createElement('button');launcher.type='button';launcher.id='cu-launch';launcher.className='cu-launch';launcher.title='Configurar Computer Use · Controlar PC';launcher.setAttribute('aria-label','Configurar Computer Use: controlar PC');launcher.innerHTML=screen+'<span>Controlar PC</span>';document.querySelector('.chat20-head-actions')?.prepend(launcher);
 const shortcut=document.createElement('section');shortcut.className='setup-card';shortcut.innerHTML='<strong>Computer Use · Controlar PC</strong><p>Configura una ventana y autoriza a Axx a ayudarte en ella.</p><button id="cu-settings-open" type="button">Configurar Computer Use</button>';$('view-settings')?.prepend(shortcut);
 let grant=null,chat=null,windows=[],engine=null,executorReady=false,checking=false,loading=false,starting=false,polling=false,selectionChat=null,checkRevision=0;
 const api=async(method,action,body)=>{const r=await Axx.backendRequest(method,'/axx-api/computer/'+action,body);if(r?.error)throw Error(r.error.message||'Computer Use no disponible.');return r;};
 const error=e=>{$('cu-error').hidden=false;$('cu-error').textContent=e.message||String(e);};
 const ready=()=>!checking&&executorReady&&c.data.prefs.provider==='chatgpt'&&!!c.data.prefs.model&&engine?.authenticated===true&&engine?.local_connection_enabled!==false&&engine?.inference_verified===true&&engine?.model===c.data.prefs.model;
 const selected=()=>{const value=$('cu-window').value;return value!==''?windows[Number(value)]:null;};
 const text=(id,value)=>{if($(id).textContent!==value)$(id).textContent=value;};
 function render(){
  const active=Boolean(grant?.active),modelReady=ready(),row=selected(),consent=$('cu-images').checked&&$('cu-input').checked;
  const status=active?(grant.blocked?'Revisión requerida':grant.last_error?'Última operación fallida':grant.actions>=60?'Límite de gestos alcanzado':modelReady?'Habilitado para este chat':'Ventana autorizada · comprobar modelo'):modelReady?'Falta autorizar una ventana':'Necesita configuración';
  text('cu-live',status+(active?` · ${grant.title} · ${grant.actions}/60`:''));text('cu-chat-status','Computer Use · '+status);
  const diagnostic=active&&grant.last_error; $('cu-diagnostic').hidden=!diagnostic;
  text('cu-diagnostic',diagnostic?diagnostic+(/UI Automation excedió/.test(diagnostic)?(grant.blocked?' Revisa el efecto antes de continuar; no repitas la acción.':' La lectura de accesibilidad tardó demasiado. Reduce las pestañas o paneles de la aplicación y pide una nueva observación.'):''): '');
  text('cu-chat','Chat: '+(Axx.chatWorkspace.active?.title||(Axx.chatWorkspace.active?.id?'Conversación actual':'selecciona una conversación')));
  text('cu-model',checking?'Comprobando conexión…':c.data.prefs.provider!=='chatgpt'?'Selecciona ChatGPT en Conectar IA.':!executorReady?'El control del PC no está disponible todavía. Pulsa Comprobar estado.':modelReady?'Modelo comprobado: '+engine.model:engine?.authenticated?'La sesión está vinculada; falta probar el modelo seleccionado.':'La conexión no está comprobada. Abre ChatGPT y verifica el modelo.');
  text('cu-next',active?(grant.blocked?'Revisa el resultado de la acción antes de continuar.':'Vuelve al chat y escribe la tarea.'):!Axx.chatWorkspace.active?.id?'Primero selecciona un chat.':!modelReady?'Completa el paso 1: conexión y modelo comprobados.':!row?'Completa el paso 2: elige una ventana.':!consent?'Marca las dos autorizaciones para habilitar esta ventana.':'Todo preparado. Pulsa Habilitar Computer Use.');
  $('cu-step-model').dataset.ready=String(modelReady);$('cu-step-window').dataset.ready=String(!!row);$('cu-step-permission').dataset.ready=String(active);
  $('cu-start').disabled=active||starting||loading||!modelReady||!row||!consent||!Axx.chatWorkspace.active?.id;
  $('cu-window').disabled=active||loading||starting;$('cu-refresh').disabled=active||loading||starting;$('cu-check').disabled=checking||starting;
  $('cu-images').disabled=$('cu-input').disabled=active||starting;$('cu-stop').hidden=!active;$('cu-review').hidden=!grant?.blocked;
  Axx.resident?.schedule();
 }
 async function check(){
  const revision=++checkRevision;checking=true;engine=null;executorReady=false;render();
  try{const r=await Axx.backendRequest('GET','/axx-api/connect/status?engine=1');if(r?.error||!r?.engine)throw Error(r?.error?.message||'No se pudo comprobar la conexión.');if(revision===checkRevision){engine=r.engine;executorReady=r.executor==='ready'&&r.ui_connected===true;}}
  finally{if(revision===checkRevision){checking=false;render();}}
 }
 async function stop(){
  if(!chat)return;const current=chat;text('cu-live','Deteniendo…');
  try{await api('POST','stop',{conversation_id:current});if(chat===current){chat=null;grant=null;render();}}
  catch(e){error(e);throw e;}
 }
 async function refresh(){
  if(loading)return;loading=true;windows=[];$('cu-window').replaceChildren(new Option('Elige una ventana…',''));$('cu-images').checked=$('cu-input').checked=false;text('cu-window-status','Buscando ventanas abiertas…');render();
  try{
   const r=await Axx.backendRequest('POST','/axx-api/commands/prepare',{command_id:'axx.desktop.list_windows',inputs:{},operation_id:crypto.randomUUID()});if(r?.error)throw Error(r.error.message);
   let result=await Axx.backendRequest('POST','/axx-api/commands/execute',{operation_id:r.operation_id,approved:false});
   for(let i=0;i<60&&['prepared','running','queued'].includes(result.state);i++){await new Promise(resolve=>setTimeout(resolve,250));result=(await Axx.backendRequest('GET','/axx-api/commands/operations?operation_id='+encodeURIComponent(r.operation_id))).operation;}
   if(result?.state!=='succeeded')throw Error(result?.error?.message||'No se confirmaron las ventanas.');
   if(!Array.isArray(result.output?.windows))throw Error('La lista de ventanas recibida no es válida.');windows=result.output.windows;
   for(const [index,row]of windows.entries())$('cu-window').add(new Option(row.title||'Ventana sin título · '+row.pid,String(index)));
   text('cu-window-status',windows.length?`${windows.length} ventanas encontradas. Elige una para continuar.`:'No hay ventanas disponibles. Abre una aplicación y vuelve a buscar.');
  }catch(e){text('cu-window-status','No se pudieron consultar las ventanas. Vuelve a buscar.');throw e;}finally{loading=false;render();}
 }
 async function start(){
  if(starting||grant?.active)return;
  const current=Axx.chatWorkspace.active?.id;if(!current||current!==selectionChat)throw Error('El chat cambió. Abre de nuevo la configuración para autorizarlo.');
  if(!ready())throw Error('Primero conecta ChatGPT y comprueba el modelo seleccionado.');
  const row=selected();if(!row)throw Error('Elige una ventana observada.');if(!$('cu-images').checked||!$('cu-input').checked)throw Error('Marca las dos autorizaciones de esta ventana.');
  starting=true;render();
  try{const result=await api('POST','begin',{conversation_id:current,window_id:row.window_id,pid:row.pid,image_authorized:$('cu-images').checked,allow_input:$('cu-input').checked});chat=current;grant=result;if(Axx.chatWorkspace.active?.id!==current||c.data.prefs.provider!=='chatgpt'){await stop();return;}$('cu-images').checked=$('cu-input').checked=false;}
  finally{starting=false;render();}
 }
 const run=fn=>async()=>{$('cu-error').hidden=true;try{await fn();}catch(e){error(e);}};
 async function load(){
  const current=selectionChat=Axx.chatWorkspace.active?.id;$('cu-images').checked=$('cu-input').checked=false;$('cu-error').hidden=true;render();
  await check();
  if(current){const status=await api('GET','status?conversation_id='+encodeURIComponent(current));if(current===Axx.chatWorkspace.active?.id){grant=status;chat=status.active?current:null;render();}}
 }
 const originalOpen=c.openFeature.bind(c);c.openFeature=function(id,...args){const result=originalOpen(id,...args);if(id==='computeruse')void run(load)();return result;};
 function open(){Axx.quickReply?.close(false);c.openFeature('computeruse');}
 $('cu-open').onclick=launcher.onclick=open;if($('cu-settings-open'))$('cu-settings-open').onclick=open;
 $('cu-connect').onclick=()=>{c.openFeature('ai');$('tab-mode-chatgpt')?.click();};
 $('cu-check').onclick=run(check);$('cu-refresh').onclick=run(refresh);$('cu-start').onclick=run(start);$('cu-stop').onclick=run(stop);
 $('cu-window').onchange=()=>{$('cu-images').checked=$('cu-input').checked=false;render();};$('cu-images').onchange=$('cu-input').onchange=render;
 $('cu-chat-open').onclick=()=>c.openChat();$('cu-review').onclick=()=>Axx.commandLibrary?.open();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&chat)void stop().catch(error);});
 setInterval(async()=>{
  if(polling)return;
  if(selectionChat!==Axx.chatWorkspace.active?.id){selectionChat=Axx.chatWorkspace.active?.id;$('cu-images').checked=$('cu-input').checked=false;render();}
  if(!chat)return;polling=true;
  try{if(Axx.chatWorkspace.active?.id!==chat||c.data.prefs.provider!=='chatgpt'){await stop();return;}const current=chat,r=await api('GET','status?conversation_id='+encodeURIComponent(current));if(current===chat){grant=r;render();if(!r.active)chat=null;}}
  catch(e){error(e);}finally{polling=false;}
 },1500);
 Axx.computerUse={activeFor:id=>Boolean(grant?.active&&chat===id),stop,open};render();
})(window.Axx);
