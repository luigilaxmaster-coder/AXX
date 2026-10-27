/* Explicit desktop or window grant; visual tools share the existing chat and input owner. */
(function(Axx){
 'use strict';
 if(!Axx?.isNative()||!Axx.chatWorkspace)return;
 const $=id=>document.getElementById(id),host=$('chat-workspace');if(!host)return;
 const c=Axx.companion,view=document.createElement('section');view.id='view-computeruse';view.className='panel-view';view.hidden=true;
 const screen='<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2" y="3" width="20" height="14" rx="3"/><path d="M8 21h8M12 17v4m-4-9 3-6 3 6-3-1z"/></svg>';
 view.innerHTML=`<style>
 #computer-use{color:var(--ink);font-family:var(--interface-font,"Segoe UI",sans-serif)}#computer-use [hidden]{display:none!important}
 #computer-use p{color:var(--secondary);line-height:1.5;font-size:12px}#computer-use .cu-intro{margin:0 0 10px}
 #computer-use .cu-status{position:sticky;top:0;z-index:1;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface-raised,var(--surface));margin:14px 0;display:flex;align-items:center;justify-content:space-between;gap:12px}
 #computer-use .cu-status p{margin:4px 0 0;overflow-wrap:anywhere}#computer-use .cu-status>div:first-child{min-width:0;flex:1}#computer-use .cu-status>.cu-row{flex-shrink:0}#computer-use .cu-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--secondary);margin-right:8px}
 #computer-use[data-active=true] .cu-dot{background:var(--success,#35a678)}#computer-use[data-working=true] .cu-dot{animation:cu-breathe 1.2s ease-in-out infinite}
 #computer-use .cu-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}#computer-use button{min-height:40px;border-radius:10px;background:var(--surface-subtle);color:var(--ink);border:1px solid var(--line)}
 #computer-use .cu-section{padding:13px 0;border-bottom:1px solid var(--line)}#computer-use summary{cursor:pointer;font-size:13px;min-height:32px;align-content:center}
 #computer-use h3{font-size:13px;margin:0 0 8px}#cu-model{margin:4px 0 9px}#computer-use .cu-help{margin:8px 0 0}
 #computer-use fieldset{border:0;padding:0;margin:0;display:grid;grid-template-columns:1fr 1fr;gap:8px}#computer-use legend{font-size:13px;margin-bottom:9px}
 #computer-use .cu-choice{display:grid;grid-template-columns:14px 1fr;gap:3px 8px;border:1px solid var(--line);border-radius:12px;padding:12px;cursor:pointer;transition:background .22s,border-color .22s;min-width:0}
 #computer-use .cu-choice:has(input:checked){border-color:var(--accent,#559ee5);background:var(--surface-subtle)}#computer-use .cu-choice strong{font-size:13px;line-height:20px}#computer-use .cu-choice small{display:block;grid-column:2;color:var(--secondary);font-size:11px;line-height:1.45;margin:0}#computer-use .cu-choice input{grid-row:1/3;margin:3px 0 0}
 #computer-use input[type=radio],#computer-use input[type=checkbox]{width:16px;height:16px;min-height:0;padding:0;margin:0 7px 0 0;accent-color:var(--accent,#559ee5)}#computer-use input:focus-visible{outline:2px solid var(--accent,#559ee5);outline-offset:3px}
 #computer-use .cu-consent{display:flex;align-items:flex-start;gap:4px;font-size:12px;line-height:1.5;margin:12px 0}#computer-use .cu-consent input{margin-top:3px;flex:none}
 #computer-use select{width:100%;margin:8px 0}#computer-use #cu-start{width:100%;min-height:44px;margin-top:4px;background:var(--ink);color:var(--surface-raised,var(--bg));border-color:var(--ink)}#computer-use #cu-start:disabled{background:var(--surface-subtle);color:var(--secondary);border-color:var(--line);opacity:.7}#computer-use #cu-stop{flex:none;color:var(--danger,#cf6666)}#cu-error,#cu-diagnostic{color:var(--danger,#cf6666)!important}
 #cu-next{min-height:18px;margin:7px 0 0}#cu-window-controls{margin-top:10px}#cu-window-controls label{font-size:12px}
 .cu-chat-entry{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:6px 0;padding:6px 10px;border:1px solid var(--line);border-radius:10px;color:var(--secondary);font-size:11px}.cu-chat-entry button{min-height:40px}
 .cu-launch{display:inline-flex;align-items:center;gap:6px;min-height:40px;border-radius:9px;background:var(--button);color:var(--ink);border:1px solid var(--line);padding:6px 10px}.cu-launch svg{width:20px;height:20px;flex:none}#panel:has(#view-chat.cw-narrow) .cu-launch span{display:none}
 @keyframes cu-breathe{50%{opacity:.35;transform:scale(.8)}}@media(prefers-reduced-motion:reduce){#computer-use *{animation:none!important;transition:none!important}}
 @media(max-width:440px){#computer-use fieldset{grid-template-columns:1fr}#computer-use .cu-status{flex-wrap:wrap}}
 </style><div id="computer-use">
 <p class="cu-intro">Controla tus aplicaciones desde el chat. Elige el alcance y autoriza esta sesión.</p>
 <div class="cu-status"><div><strong role="status" aria-live="polite"><i class="cu-dot" aria-hidden="true"></i><span id="cu-live">Sin autorizar</span></strong><p id="cu-chat"></p><p id="cu-target" hidden></p><p id="cu-diagnostic" role="alert" hidden></p></div><div class="cu-row"><button type="button" id="cu-chat-open">Ir al chat</button><button type="button" id="cu-stop" hidden>Detener</button></div></div>
 <details id="cu-connection" class="cu-section" open><summary id="cu-connection-summary">1 · Conexión del modelo</summary><div id="cu-step-model"><p id="cu-model" role="status">Comprobando conexión…</p><div class="cu-row"><button type="button" id="cu-connect">Conectar ChatGPT</button><button type="button" id="cu-check">Comprobar estado</button></div><p class="cu-help">En Conectar IA, pulsa «Probar respuesta y usar modelo». Vuelve aquí para comprobarlo.</p></div></details>
 <section id="cu-step-window" class="cu-section"><fieldset><legend>2 · Qué podrá controlar</legend><label class="cu-choice"><input id="cu-scope-desktop" name="cu-scope" value="desktop" type="radio" checked><strong>Escritorio completo</strong><small>Puede observar tus pantallas y cambiar entre aplicaciones.</small></label><label class="cu-choice"><input id="cu-scope-window" name="cu-scope" value="window" type="radio"><strong>Solo una ventana</strong><small>El acceso termina en la aplicación que elijas.</small></label></fieldset>
 <div id="cu-window-controls" hidden><label>Ventana autorizada<select id="cu-window" aria-label="Ventana autorizada"><option value="">Busca las ventanas abiertas</option></select></label><button type="button" id="cu-refresh">Buscar ventanas</button><p id="cu-window-status" role="status"></p></div></section>
 <section id="cu-step-permission" class="cu-section"><h3>3 · Autorizar esta sesión</h3><label class="cu-consent"><input id="cu-images" type="checkbox"><span id="cu-images-label">Permito enviar a Codex imágenes y texto visibles de mis pantallas.</span></label><label class="cu-consent"><input id="cu-input" type="checkbox"><span id="cu-input-label">Permito usar mouse y teclado y cambiar de aplicación para mis solicitudes.</span></label><button type="button" id="cu-start" class="primary" disabled>Habilitar Computer Use</button><p id="cu-next" role="status"></p></section>
 <button type="button" id="cu-review" hidden>Revisar acción pendiente</button>
 <p>15 minutos · 60 gestos · Solo este chat. Escape interrumpe la acción en curso; desde Axx también revoca la sesión. Detener conserva los efectos ya realizados.</p>
 <details><summary style="font-size:12px">Alcance y privacidad</summary><p>La vista general puede incluir contenido de todas tus pantallas. Cierra lo que no quieras compartir. Las imágenes de control son temporales y no se guardan en el historial. Axx no controla UAC, pantallas bloqueadas, gestores de contraseñas ni terminales; los scripts conservan su revisión separada.</p></details><p id="cu-error" role="alert" hidden></p></div>`;
 ($('panel')||document.body).append(view);
 const entry=document.createElement('div');entry.className='cu-chat-entry';entry.innerHTML='<span id="cu-chat-status">Computer Use · Sin autorizar</span><button id="cu-stop-chat" type="button" hidden>Detener</button><button id="cu-open" type="button" aria-controls="view-computeruse">Configurar control del PC</button>';host.append(entry);
 const launcher=document.createElement('button');launcher.type='button';launcher.id='cu-launch';launcher.className='cu-launch';launcher.title='Configurar Computer Use · Controlar PC';launcher.setAttribute('aria-label','Configurar Computer Use: controlar PC');launcher.innerHTML=screen+'<span>Controlar PC</span>';document.querySelector('.chat20-head-actions')?.prepend(launcher);
 const shortcut=document.createElement('section');shortcut.className='setup-card';shortcut.innerHTML='<strong>Computer Use · Controlar PC</strong><p>Autoriza el escritorio completo o limita el acceso a una aplicación.</p><button id="cu-settings-open" type="button">Configurar Computer Use</button>';$('view-settings')?.prepend(shortcut);
 let grant=null,chat=null,windows=[],engine=null,executorReady=false,checking=false,loading=false,starting=false,polling=false,selectionChat=null,checkRevision=0,grantRevision=0;
 const api=async(method,action,body)=>{const r=await Axx.backendRequest(method,'/axx-api/computer/'+action,body);if(r?.error)throw Error(r.error.message||'Computer Use no disponible.');return r;};
 const error=e=>{$('cu-error').hidden=false;$('cu-error').textContent=e.message||String(e);Axx.app?.toast(e.message||String(e));};
 const ready=()=>!checking&&executorReady&&c.data.prefs.provider==='chatgpt'&&!!c.data.prefs.model&&engine?.authenticated===true&&engine?.local_connection_enabled!==false&&engine?.inference_verified===true&&engine?.model===c.data.prefs.model;
 const selected=()=>{const value=$('cu-window').value;return value!==''?windows[Number(value)]:null;};
 const scope=()=>$('cu-scope-desktop').checked?'desktop':'window';
 const text=(id,value)=>{if($(id).textContent!==value)$(id).textContent=value;};
 function render(){
  const active=Boolean(grant?.active),modelReady=ready(),row=selected(),desktop=scope()==='desktop',targetReady=desktop||!!row,consent=$('cu-images').checked&&$('cu-input').checked;
  const status=active?(grant.blocked?'Revisión requerida':grant.last_error?'Última operación fallida':grant.actions>=60?'Límite de gestos alcanzado':modelReady?'Habilitado para este chat':'Acceso autorizado · comprobar modelo'):modelReady?'Listo para autorizar':'Necesita configuración';
  text('cu-live',status);text('cu-chat-status','Computer Use · '+status);
  $('computer-use').dataset.active=String(active);$('computer-use').dataset.working=String(active&&['observing','acting','verifying'].includes(grant.phase));
  const phases={observing:'Observando',acting:'Actuando',verifying:'Comprobando',ready:'Listo',blocked:'Revisión pendiente'};
  const target=active?(grant.scope==='desktop'?'Escritorio completo':grant.title)+(grant.target_title?' → '+grant.target_title:''):'';
  text('cu-target',active?`${phases[grant.phase]||'Listo'} · ${target.length>100?target.slice(0,100)+'…':target} · ${grant.actions}/60 · ${Math.ceil((grant.expires_in??900)/60)} min`:'');$('cu-target').title=target;$('cu-target').hidden=!active;
  text('cu-connection-summary',modelReady?'1 · Modelo comprobado':'1 · Conexión del modelo');
  const diagnostic=active&&grant.last_error; $('cu-diagnostic').hidden=!diagnostic;
  text('cu-diagnostic',diagnostic?diagnostic+(/UI Automation excedió/.test(diagnostic)?(grant.blocked?' Revisa el efecto antes de continuar; no repitas la acción.':' La lectura de accesibilidad tardó demasiado. Reduce las pestañas o paneles de la aplicación y pide una nueva observación.'):''): '');
  text('cu-chat','Chat: '+(Axx.chatWorkspace.active?.title||(Axx.chatWorkspace.active?.id?'Conversación actual':'selecciona una conversación')));
  text('cu-chat-open',Axx.chatWorkspace.active?.id?'Ir al chat':'Elegir chat');
  text('cu-model',checking?'Comprobando conexión…':c.data.prefs.provider!=='chatgpt'?'Selecciona ChatGPT en Conectar IA.':!executorReady?'El control del PC no está disponible todavía. Pulsa Comprobar estado.':modelReady?'Modelo comprobado: '+engine.model:engine?.authenticated?'La sesión está vinculada; falta probar el modelo seleccionado.':'La conexión no está comprobada. Abre ChatGPT y verifica el modelo.');
  text('cu-next',active?(grant.blocked?'Revisa el efecto en Comandos. Después detén y habilita una sesión nueva.':'Escribe la tarea en el chat.'):!Axx.chatWorkspace.active?.id?'Primero selecciona un chat.':!modelReady?'Completa el paso 1: conexión y modelo comprobados.':!targetReady?'Elige una ventana o usa Escritorio completo.':!consent?'Marca ambas autorizaciones para '+(desktop?'el escritorio completo.':'esta ventana.'):'Todo preparado. Pulsa Habilitar Computer Use.');
  text('cu-images-label',desktop?'Permito enviar a Codex imágenes y texto visibles de mis pantallas.':'Permito enviar a Codex imágenes y texto de la ventana seleccionada.');
  text('cu-input-label',desktop?'Permito usar mouse y teclado y cambiar de aplicación para mis solicitudes.':'Permito usar mouse y teclado solo en la ventana seleccionada.');
  $('cu-window-controls').hidden=desktop;$('cu-scope-desktop').disabled=$('cu-scope-window').disabled=active||starting;
  $('cu-step-model').dataset.ready=String(modelReady);$('cu-step-window').dataset.ready=String(targetReady);$('cu-step-permission').dataset.ready=String(active);
  $('cu-start').disabled=active||starting||loading||!modelReady||!targetReady||!consent||!Axx.chatWorkspace.active?.id;
  $('cu-window').disabled=active||loading||starting;$('cu-refresh').disabled=active||loading||starting;$('cu-check').disabled=checking||starting;
  $('cu-images').disabled=$('cu-input').disabled=active||starting;$('cu-stop').hidden=$('cu-stop-chat').hidden=!active;$('cu-review').hidden=!grant?.blocked;
  Axx.resident?.schedule();
 }
 async function check(){
  const revision=++checkRevision;checking=true;engine=null;executorReady=false;render();
  try{const r=await Axx.backendRequest('GET','/axx-api/connect/status?engine=1');if(r?.error||!r?.engine)throw Error(r?.error?.message||'No se pudo comprobar la conexión.');if(revision===checkRevision){engine=r.engine;executorReady=r.executor==='ready'&&r.ui_connected===true;}}
  finally{if(revision===checkRevision){checking=false;render();}}
 }
 async function stop(){
  if(!chat)return;const current=chat;++grantRevision;text('cu-live','Deteniendo…');
  const result=await api('POST','stop',{conversation_id:current});if(result.active!==false)throw Error('No se confirmó la parada. Conserva la sesión visible y vuelve a comprobarla.');if(chat===current){++grantRevision;chat=null;grant=null;render();}
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
  if(c.pending||c.connecting||c.externalBusy||Axx.commandLibrary?.busy)throw Error('Espera a que termine la tarea actual antes de habilitar Computer Use.');
  const current=Axx.chatWorkspace.active?.id;if(!current||current!==selectionChat)throw Error('El chat cambió. Abre de nuevo la configuración para autorizarlo.');
  if(!ready())throw Error('Primero conecta ChatGPT y comprueba el modelo seleccionado.');
  const row=selected(),mode=scope();if(mode==='window'&&!row)throw Error('Elige una ventana observada.');if(!$('cu-images').checked||!$('cu-input').checked)throw Error('Marca las dos autorizaciones del alcance elegido.');
  starting=true;++grantRevision;render();
  try{const result=await api('POST','begin',{conversation_id:current,scope:mode,...(mode==='window'?{window_id:row.window_id,pid:row.pid}:{}),image_authorized:$('cu-images').checked,allow_input:$('cu-input').checked});if(result.active!==true)throw Error('No se confirmó la autorización.');++grantRevision;chat=current;grant=result;if(Axx.chatWorkspace.active?.id!==current||c.data.prefs.provider!=='chatgpt'){await stop();return;}$('cu-images').checked=$('cu-input').checked=false;Axx.quickReply?.write?.();}
  finally{starting=false;render();}
 }
 const run=fn=>async()=>{$('cu-error').hidden=true;try{await fn();}catch(e){error(e);}};
 async function load(){
  const current=selectionChat=Axx.chatWorkspace.active?.id,revision=grantRevision;$('cu-images').checked=$('cu-input').checked=false;$('cu-error').hidden=true;render();
  await check();$('cu-connection').open=!ready();
  if(current){const status=await api('GET','status?conversation_id='+encodeURIComponent(current));if(revision===grantRevision&&current===Axx.chatWorkspace.active?.id){grant=status;chat=status.active?current:null;if(status.active){$('cu-scope-desktop').checked=status.scope==='desktop';$('cu-scope-window').checked=status.scope!=='desktop';}render();}}
 }
 const originalOpen=c.openFeature.bind(c);c.openFeature=function(id,...args){const result=originalOpen(id,...args);if(id==='computeruse')void run(load)();return result;};
 function open(){Axx.quickReply?.close(false);c.openFeature('computeruse');}
 $('cu-open').onclick=launcher.onclick=open;if($('cu-settings-open'))$('cu-settings-open').onclick=open;
 $('cu-connect').onclick=()=>{c.openFeature('ai');$('tab-mode-chatgpt')?.click();};
 $('cu-check').onclick=run(check);$('cu-refresh').onclick=run(refresh);$('cu-start').onclick=run(start);$('cu-stop').onclick=$('cu-stop-chat').onclick=run(stop);
 $('cu-scope-desktop').onchange=$('cu-scope-window').onchange=()=>{$('cu-images').checked=$('cu-input').checked=false;render();};
 $('cu-window').onchange=()=>{$('cu-images').checked=$('cu-input').checked=false;render();};$('cu-images').onchange=$('cu-input').onchange=render;
 $('cu-chat-open').onclick=()=>c.openChat();$('cu-review').onclick=()=>Axx.commandLibrary?.open();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&chat)void stop().catch(error);});
 setInterval(async()=>{
  if(polling)return;
  if(selectionChat!==Axx.chatWorkspace.active?.id){selectionChat=Axx.chatWorkspace.active?.id;$('cu-images').checked=$('cu-input').checked=false;render();}
  if(!chat)return;polling=true;
  try{if(Axx.chatWorkspace.active?.id!==chat||c.data.prefs.provider!=='chatgpt'){await stop();return;}const current=chat,revision=grantRevision,r=await api('GET','status?conversation_id='+encodeURIComponent(current));if(current===chat&&revision===grantRevision){grant=r;render();if(!r.active)chat=null;}}
  catch(e){error(e);}finally{polling=false;}
 },1500);
 Axx.computerUse={activeFor:id=>Boolean(grant?.active&&chat===id),stop,open};render();
})(window.Axx);
