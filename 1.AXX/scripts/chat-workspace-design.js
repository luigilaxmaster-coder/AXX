/* Messages-style layout over the existing Companion. No duplicate chat state. */
(function(Axx){
 'use strict';
 const $=id=>document.getElementById(id),root=$('chat-workspace'),view=$('view-chat');
 if(!root||view.dataset.layout==='messages')return;
 view.dataset.layout='messages';
 const icons={history:'M4 5h16v14H4z M9 5v14 M12 9h5 M12 13h5',plus:'M12 5v14 M5 12h14',back:'M14 6l-6 6 6 6',chat:'M5 5h14v11H9l-4 4z'};
 function icon(name){const span=document.createElement('span');span.className='cw-icon';span.setAttribute('aria-hidden','true');span.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${icons[name]}"/></svg>`;return span;}
 const main=document.createElement('div');main.id='cw-main';
 const sidebar=$('cw-browser');sidebar.classList.add('cw-sidebar');sidebar.hidden=false;
 const nav=document.createElement('div');nav.className='cw-navigation';
 const identity=document.createElement('div');identity.className='cw-identity';identity.append($('cw-title'),$('cw-context-open'));
 const mode=$('cw-mode').closest('label');mode.className='cw-mode-label';$('cw-mode').setAttribute('aria-label','Modo de comandos');$('cw-mode').title='Preguntar solicita aprobación. Auto solo permite acciones seguras.';
 $('cw-browse').replaceChildren(icon('history'));$('cw-browse').setAttribute('aria-label','Mostrar conversaciones');$('cw-browse').title='Conversaciones';
 $('cw-browse').setAttribute('aria-controls','cw-browser');
 nav.append($('cw-browse'),identity,mode);
 const sideHead=sidebar.querySelector('.cw-heading');sideHead.querySelector('strong').textContent='Chats';
 $('cw-new').replaceChildren(icon('plus'));$('cw-new').setAttribute('aria-label','Nuevo chat');$('cw-new').title='Nuevo chat';sideHead.append($('cw-new'));
 $('cw-back').replaceChildren(icon('back'));$('cw-back').setAttribute('aria-label','Volver al chat');
 root.querySelectorAll(':scope > .cw-heading,:scope > .cw-current').forEach(n=>n.remove());root.prepend(nav);
 const search=$('cw-search');search.placeholder='Buscar';search.setAttribute('aria-label','Buscar conversación');search.closest('label').classList.add('cw-search-label');
 const settings=document.createElement('details');settings.className='cw-organize';const summary=document.createElement('summary');summary.textContent='Organizar chats y grupos';settings.append(summary);
 for(const item of [...sidebar.querySelectorAll(':scope > details'),$('cw-default').closest('label'),sidebar.querySelector(':scope > .cw-help')])if(item)settings.append(item);
 sidebar.append(settings);
 const filter=$('cw-filter').closest('label');filter.classList.add('cw-group-filter');
 sidebar.querySelector('.cw-check').classList.add('cw-archive-filter');
 const footer=document.createElement('p');footer.className='cw-retention';footer.textContent='Guardado en este equipo · 90 días';sidebar.append(footer);
 sidebar.remove();for(const child of [...view.children])main.append(child);view.append(sidebar,main);
 const empty=$('chat-empty');
 if(empty){const welcome=document.createElement('div');welcome.id='cw-welcome';const mark=document.createElement('div');mark.className='cw-welcome-mark';mark.append(icon('chat'));const title=document.createElement('h2');title.textContent='Una nueva conversación';const p=document.createElement('p');p.textContent='Escribe una idea, haz una pregunta o pide una acción.';welcome.append(mark,title,p);empty.append(welcome);}
 $('chat-input').placeholder='Mensaje para Axx';
 const keep=$('keep-history')?.closest('label')?.querySelector('span');if(keep)keep.textContent='Guardar historial local hasta 90 días';
 $('chat20-voice-toggle')?.setAttribute('aria-label','Activar o silenciar lectura de respuestas');$('chat20-wake-toggle')?.setAttribute('aria-label','Dictar una orden');
 const resize=()=>{const narrow=view.clientWidth<700;view.classList.toggle('cw-narrow',narrow);sidebar.hidden=narrow&&!view.classList.contains('cw-browsing');};
 new ResizeObserver(resize).observe(view);resize();
 // Keep the approved chat size while each other tool owns its own dimensions.
 if(Axx.resident){const r=Axx.resident;if(!r.panelPositions['panel:chat']&&r.panelPositions.panel){r.panelPositions['panel:chat']={...r.panelPositions.panel};r.savePanelPositions();}}
})(window.Axx);
