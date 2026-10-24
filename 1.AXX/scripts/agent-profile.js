/* Profile preferences share the local chat store and existing typed command catalog. */
(function(Axx){
 'use strict';if(!Axx?.isNative())return;
 const $=id=>document.getElementById(id),panel=$('panel');
 const view=document.createElement('section');view.id='view-agent';view.className='panel-view';view.hidden=true;
 view.innerHTML=`<p class="panel-description">Define quién es tu agente, en qué trabajas y cómo quieres que te ayude. Se aplica a las respuestas nuevas de todos tus chats.</p>
 <form id="agent-profile-form"><label class="setting">Nombre del agente<input id="agent-name" maxlength="80" placeholder="Axx"></label>
 <label class="setting">Rol y trabajo<input id="agent-role" maxlength="240" placeholder="Asistente de proyectos, diseño y organización"></label>
 <label class="setting">Contexto sobre ti y tus proyectos<textarea id="agent-context" maxlength="4000" rows="4" placeholder="Tu trabajo, objetivos, herramientas y preferencias habituales"></textarea></label>
 <label class="setting">Instrucciones permanentes<textarea id="agent-instructions" maxlength="4000" rows="5" placeholder="Cómo razonar, qué preguntar y cómo presentar los resultados"></textarea></label>
 <div id="agent-tone"></div>
 <details><summary>Conectar preferencias con comandos</summary><p>Indica IDs registrados, uno por línea. El agente podrá sugerirlos; los permisos y la aprobación de cada acción siguen vigentes.</p><label class="setting">Comandos preferidos<textarea id="agent-preferred" rows="3" placeholder="axx.system.telemetry"></textarea></label><button id="agent-open-commands" type="button">Explorar el catálogo</button></details>
 <div class="quick-row"><button type="submit" class="primary">Guardar configuración</button><button id="agent-profile-clear" type="button">Restablecer perfil</button></div></form>
 <p id="agent-profile-status" role="status" aria-live="polite"></p>`;
 panel.append(view);
 const tone=$('chat-personality-style')?.closest('.chat20-voice-card');if(tone)$('agent-tone').append(tone);
 const menu=document.querySelector('.chat20-menu-body');if(menu){for(const [title,id] of [['Personalizar agente','agent'],['Comandos disponibles','commands']]){const b=document.createElement('button');b.type='button';b.textContent=title;b.onclick=()=>Axx.companion.openFeature(id);menu.append(b);}}
 const commands=document.createElement('section');commands.id='view-commands';commands.className='panel-view';commands.hidden=true;panel.append(commands);
 if($('skill-library'))commands.append($('skill-library'));
 commands.append($('command-library'));
 const guide=document.createElement('details');guide.innerHTML='<summary>Añadir comandos mediante código</summary><p>El catálogo ejecuta únicamente adaptadores registrados. Añade el ID y sus argumentos tipados en <code>backend/commands.py</code>, conecta su herramienta en <code>backend/actions/tools.py</code> y define permiso, cancelación y postcondición. Los registros documentales no habilitan ejecución por sí solos.</p><p>Guía del proyecto: <code>docs/COMMAND-EXTENSIONS.md</code>. Incluye el recorrido completo y las comprobaciones antes de reconstruir e instalar Axx.</p>';commands.append(guide);
 const status=text=>{$('agent-profile-status').textContent=text;};
 const api=(method,body)=>Axx.backendRequest(method,'/axx-api/chat/profile',body);
 const fields=['name','role','context','instructions'];
 async function load(){try{const p=await api('GET');for(const k of fields)$('agent-'+k).value=p[k]||'';$('agent-preferred').value=(p.preferred_commands||[]).join('\n');status('Configuración local. Se envía al proveedor seleccionado al conversar.');}catch(e){status(e.message||String(e));}}
 $('agent-profile-form').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(fields.map(k=>[k,$('agent-'+k).value]));body.preferred_commands=$('agent-preferred').value.split(/\s+/).filter(Boolean);try{await api('POST',body);status('Configuración guardada. Se aplicará al próximo mensaje.');}catch(e){status(e.message||String(e));}};
 $('agent-profile-clear').onclick=async()=>{if(!confirm('¿Restablecer la identidad, contexto e instrucciones del agente?'))return;try{await api('POST',{});await load();status('Perfil restablecido.');}catch(e){status(e.message||String(e));}};
 $('agent-open-commands').onclick=()=>Axx.commandLibrary.open();
 const open=Axx.companion.openFeature.bind(Axx.companion);Axx.companion.openFeature=function(id){const result=open(id);if(id==='agent')void load();if(id==='commands')void Axx.commandLibrary.search().catch(e=>Axx.commandLibrary.status(e.message));return result;};
 const shortcut=document.createElement('button');shortcut.type='button';shortcut.className='wide-button';shortcut.textContent='Personalizar agente y sus instrucciones';shortcut.onclick=()=>Axx.companion.openFeature('agent');$('view-settings').prepend(shortcut);
})(window.Axx);
