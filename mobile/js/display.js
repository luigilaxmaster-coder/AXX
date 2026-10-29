/* Phone surface preferences are local; character settings belong to the PC. */
(()=>{
  'use strict';
  const key='axx.mobile.display',hex=/^#[0-9a-f]{6}$/i,root=document.documentElement;
  let current={theme:'light',accent:'#2864df'};
  try{const value=JSON.parse(localStorage.getItem(key)||'null');if(value&&['light','dark'].includes(value.theme)&&hex.test(value.accent))current=value;}catch{}
  const rgb=value=>[1,3,5].map(i=>parseInt(value.slice(i,i+2),16));
  const mix=(a,b,t)=>'#'+rgb(a).map((v,i)=>Math.round(v*(1-t)+rgb(b)[i]*t).toString(16).padStart(2,'0')).join('');
  const luminance=value=>rgb(value).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
  const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
  function apply(){
    const dark=current.theme==='dark',bg=dark?'#090b10':'#f6f7f9',ink=dark?'#edf0f6':'#202127',surface=dark?'#151922':'#ffffff';
    root.dataset.theme=current.theme;
    root.style.setProperty('--mobile-accent',current.accent);
    root.style.setProperty('--mobile-on-accent',contrast(current.accent,'#ffffff')>=contrast(current.accent,'#101114')?'#ffffff':'#101114');
    let text=current.accent;for(let i=0;i<12&&contrast(text,bg)<4.5;i++)text=mix(text,ink,.18);
    root.style.setProperty('--mobile-accent-text',text);
    root.style.setProperty('--mobile-accent-soft',mix(surface,text,dark?.18:.10));
    document.querySelector('meta[name=theme-color]')?.setAttribute('content',bg);
  }
  apply();
  document.addEventListener('DOMContentLoaded',()=>{
    const transport=window.Capacitor?.Plugins?.AxxTransport,feedback=document.getElementById('display-feedback'),color=document.getElementById('accent-color');
    function paint(){document.querySelectorAll('[data-mobile-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mobileTheme===current.theme)));color.value=current.accent;}
    let saving=false;
    async function save(next){
      if(saving)return;saving=true;color.disabled=true;document.querySelectorAll('[data-mobile-theme]').forEach(b=>b.disabled=true);
      const previous=current;
      let nativeApplied=false;
      try{
        if(!['light','dark'].includes(next.theme)||!hex.test(next.accent))throw Error('Color o tema inválido');
        if(transport?.appearance){await transport.appearance({theme:next.theme});nativeApplied=true;}
        localStorage.setItem(key,JSON.stringify(next));current=next;apply();paint();feedback.textContent='';
      }catch(e){
        current=previous;apply();paint();feedback.textContent='No se pudo guardar la apariencia: '+e.message;
        if(nativeApplied)try{await transport.appearance({theme:previous.theme});}catch{feedback.textContent+=' Vuelve a elegir el tema para ajustar las barras.';}
      }
      finally{saving=false;color.disabled=false;document.querySelectorAll('[data-mobile-theme]').forEach(b=>b.disabled=false);}
    }
    paint();
    document.querySelectorAll('[data-mobile-theme]').forEach(b=>b.onclick=()=>void save({...current,theme:b.dataset.mobileTheme}));
    color.onchange=()=>void save({...current,accent:color.value});
    if(transport?.appearance)transport.appearance({theme:current.theme}).catch(e=>{feedback.textContent='No se pudieron ajustar las barras del teléfono: '+e.message;});
  });
})();
