/* Shared surface skin. Geometry, renderer materials and tool state stay with Axx. */
(function(Axx){
 'use strict';if(!Axx?.isNative()||Axx.interfaceTheme)return;
 const key='axx.interface.theme',valid=new Set(['light','dark']);
 let current='light';try{const saved=localStorage.getItem(key);if(valid.has(saved))current=saved;}catch{}
 const prefsKey='axx.interface.customization',hex=/^#[0-9a-f]{6}$/i;
 const fonts={system:'"Segoe UI Variable", "Segoe UI", sans-serif',rounded:'"Trebuchet MS", "Segoe UI", sans-serif',serif:'Georgia, serif'};
 let preferences={};try{const saved=JSON.parse(localStorage.getItem(prefsKey)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))preferences=saved;}catch{}
 const rgb=c=>[1,3,5].map(i=>parseInt(c.slice(i,i+2),16));
 const mix=(a,b,t)=>'#'+rgb(a).map((v,i)=>Math.round(v*(1-t)+rgb(b)[i]*t).toString(16).padStart(2,'0')).join('');
 const luminance=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
 function customize(){
  const dark=current==='dark',p=preferences[current]||{},defaults=dark?{background:'#202023',text:'#ededf1',icons:'#64afff'}:{background:'#ffffff',text:'#29292f',icons:'#005fc7'};
  const colors=Object.fromEntries(Object.entries(defaults).map(([k,v])=>[k,hex.test(p[k])?p[k]:v]));
  const root=document.body.style;for(const token of ['surface','surface-subtle','surface-raised','field','line','ink','secondary','quiet','accent'])root.removeProperty('--'+token);
  if(hex.test(p.background)||hex.test(p.text))for(const [k,v] of Object.entries({surface:colors.background,'surface-subtle':mix(colors.background,colors.text,.035),'surface-raised':mix(colors.background,colors.text,.065),field:mix(colors.background,colors.text,.025),line:colors.text+'22',ink:colors.text,secondary:mix(colors.text,colors.background,.2),quiet:mix(colors.text,colors.background,.25)}))root.setProperty('--'+k,v);
  if(hex.test(p.icons))root.setProperty('--accent',p.icons);
  root.setProperty('--interface-font',fonts[preferences.font]||fonts.system);root.setProperty('--interface-scale',preferences.size==='large'?'1.15':'1');
  for(const k of Object.keys(colors)){const input=document.getElementById('axx-color-'+k);if(input)input.value=colors[k];}
  const font=document.getElementById('axx-interface-font'),size=document.getElementById('axx-interface-size');if(font)font.value=fonts[preferences.font]?preferences.font:'system';if(size)size.value=preferences.size==='large'?'large':'normal';
  const a=luminance(colors.background),b=luminance(colors.text),contrast=(Math.max(a,b)+.05)/(Math.min(a,b)+.05),notice=document.getElementById('axx-theme-contrast');
  const iconLuminance=luminance(colors.icons),iconContrast=(Math.max(a,iconLuminance)+.05)/(Math.min(a,iconLuminance)+.05);
  if(notice)notice.textContent=contrast<4.5?'Contraste bajo ('+contrast.toFixed(1)+':1). Cambia el color de texto o fondo para leer mejor.':iconContrast<3?'Los iconos tienen poco contraste ('+iconContrast.toFixed(1)+':1). Elige un color más visible sobre este fondo.':'Tu combinación se guarda para el tema '+(dark?'oscuro':'claro')+'.';
 }
 function savePreferences(){try{localStorage.setItem(prefsKey,JSON.stringify(preferences));}catch{}customize();}
 function apply(theme){if(!valid.has(theme))return;current=theme;document.body.dataset.uiTheme=theme;
  customize();
  try{localStorage.setItem(key,theme);}catch{}
  document.querySelectorAll('[data-axx-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.axxTheme===theme)));
  document.querySelectorAll('.axx-theme-toggle').forEach(b=>{b.setAttribute('aria-label',theme==='light'?'Activar modo oscuro':'Activar modo claro');b.title=b.getAttribute('aria-label');b.setAttribute('aria-pressed',String(theme==='dark'));});
 }
 const icon='<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/></svg>';
 function toggle(){const b=document.createElement('button');b.type='button';b.className='axx-theme-toggle';b.innerHTML=icon;b.onclick=()=>apply(current==='light'?'dark':'light');return b;}
 const chat=document.querySelector('.chat20-head-actions');chat?.prepend(toggle());
 const head=document.querySelector('#panel .flow-detail-nav>div');if(head){const b=toggle();b.classList.add('axx-theme-global');head.prepend(b);}
 const card=document.createElement('section');card.id='axx-interface-theme';card.className='setup-card';card.innerHTML='<div class="axx-theme-copy"><strong>Apariencia de la interfaz</strong><p>Elige cómo se ven las ventanas y herramientas.</p></div><div class="axx-theme-choices" role="group" aria-label="Tema de la interfaz"><button type="button" data-axx-theme="light"><span class="axx-theme-sample light" aria-hidden="true"></span>Claro</button><button type="button" data-axx-theme="dark"><span class="axx-theme-sample dark" aria-hidden="true"></span>Oscuro</button></div>';
 card.querySelectorAll('button').forEach(b=>b.onclick=()=>apply(b.dataset.axxTheme));document.getElementById('view-settings')?.prepend(card);
 const editor=document.createElement('div');editor.className='axx-theme-editor';editor.innerHTML='<label>Fondo<input id="axx-color-background" type="color"></label><label>Texto<input id="axx-color-text" type="color"></label><label>Iconos y acentos<input id="axx-color-icons" type="color"></label><label>Tipografía<select id="axx-interface-font"><option value="system">Sistema</option><option value="rounded">Redondeada</option><option value="serif">Clásica</option></select></label><label>Tamaño<select id="axx-interface-size"><option value="normal">Normal</option><option value="large">Amplio</option></select></label><div class="axx-color-presets" role="group" aria-label="Colores de iconos"></div><button id="axx-theme-reset" type="button">Restablecer este tema</button><p id="axx-theme-contrast" role="status" aria-live="polite"></p>';card.append(editor);
 for(const k of ['background','text','icons'])document.getElementById('axx-color-'+k).oninput=e=>{preferences[current]={...preferences[current],[k]:e.target.value};savePreferences();};
 for(const [id,k] of [['axx-interface-font','font'],['axx-interface-size','size']])document.getElementById(id).onchange=e=>{preferences[k]=e.target.value;savePreferences();};
 for(const [name,color] of [['Azul','#005fc7'],['Índigo','#6450c8'],['Violeta','#914ab1'],['Rosa','#ae3769'],['Coral','#b34f39'],['Verde','#287355'],['Grafito','#54545c']]){const b=document.createElement('button');b.type='button';b.setAttribute('aria-label','Iconos '+name);b.title=name;b.style.setProperty('--swatch',color);b.onclick=()=>{preferences[current]={...preferences[current],icons:color};savePreferences();};editor.querySelector('.axx-color-presets').append(b);}
 document.getElementById('axx-theme-reset').onclick=()=>{delete preferences[current];delete preferences.font;delete preferences.size;savePreferences();};
 window.addEventListener('storage',e=>{if(e.key===key&&valid.has(e.newValue))apply(e.newValue);});
 Axx.interfaceTheme={apply,get value(){return current;}};apply(current);
 const help=document.querySelector('#view-help .help-copy');if(help){for(const p of help.children)if(p.textContent.startsWith('Datos:'))p.innerHTML='<strong>Datos:</strong> los chats, borradores y contexto de grupo se guardan localmente hasta 90 días. Las notas y demás herramientas conservan su almacenamiento habitual. Exporta las conversaciones que quieras guardar fuera de Axx.';}
})(window.Axx);
