/* AXX Optical Glass: optional finish for native AXX. No geometry or actions replaced. */
(() => {
  'use strict';
  const A=window.Axx;
  if(!A?.SoftwareRenderer || A.PALETTES?.length!==9) return;
  const proto=A.SoftwareRenderer.prototype;
  if(proto.__axxOpticalGlass) return;
  const original=proto.shadeTable,KEY='axx-optical-glass-v1';
  const DEFAULT={transmission:.78,ior:1.47,thickness:.82,roughness:.09,iridescence:.62,rim:1.25,saturation:.85,exposure:1.0};
  const R={transmission:[0,1],ior:[1,1.9],thickness:[.05,2],roughness:[.015,.55],iridescence:[0,1.6],rim:[0,2],saturation:[0,2],exposure:[.4,2.5]};
  const PRESETS={
    reference:{transmission:.80,ior:1.47,thickness:1.03,roughness:.045,iridescence:.70,rim:1.52,saturation:.85,exposure:1.13},
    crystal:{transmission:.91,ior:1.52,thickness:.95,roughness:.028,iridescence:.42,rim:1.72,saturation:.66,exposure:1.18},
    liquid:{transmission:.66,ior:1.42,thickness:1.32,roughness:.15,iridescence:.42,rim:1.07,saturation:.90,exposure:1.02},
    silica:{transmission:.95,ior:1.46,thickness:.73,roughness:.035,iridescence:.13,rim:1.6,saturation:.29,exposure:1.12},
    aura:{transmission:.74,ior:1.50,thickness:.99,roughness:.075,iridescence:1.26,rim:1.35,saturation:1.50,exposure:1.12}
  };
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const srgb=x=>Math.pow(clamp(x,0,1),1/2.2);
  const aces=x=>clamp(x*(2.51*x+.03)/(x*(2.43*x+.59)+.14),0,1);
  const decode=h=>[1,3,5].map(i=>Math.pow(parseInt(h.slice(i,i+2),16)/255,2.2));
  let p={...DEFAULT},color='',revision=0,panel=null,inputs=new Map();
  try {
    const saved=JSON.parse(localStorage.getItem(KEY)||'null');
    if(saved&&typeof saved==='object') {
      for(const [k,[a,b]] of Object.entries(R)) if(typeof saved[k]==='number'&&Number.isFinite(saved[k])) p[k]=clamp(saved[k],a,b);
      if(/^#[0-9a-f]{6}$/i.test(saved.color||''))color=saved.color;
    }
  } catch(e) {console.warn('[AXX Optical Glass] Settings read skipped',e);}
  const invalidate=()=>{revision++;const renderer=A.app?.renderer;if(renderer){renderer.lutKey='';renderer.lastDrawnSignature='';}};
  const save=()=>{try{localStorage.setItem(KEY,JSON.stringify({...p,color}));}catch(e){console.warn('[AXX Optical Glass] Settings save skipped',e);}};
  const set=patch=>{
    if(!patch||typeof patch!=='object')return;
    for(const [k,[a,b]] of Object.entries(R))if(Object.hasOwn(patch,k)&&Number.isFinite(Number(patch[k])))p[k]=clamp(Number(patch[k]),a,b);
    if(Object.hasOwn(patch,'color'))color=/^#[0-9a-f]{6}$/i.test(patch.color||'')?patch.color:'';
    save();invalidate();sync();
  };
  proto.shadeTable=function opticalGlassShadeTable(){
    if(this.finish!=='opticalglass')return original.call(this);
    const signature=[this.settings.palette,this.studio.roughness,this.studio.exposure,this.studio.lightAngle,this.state,this.settings.keepForm,revision].join('/');
    if(this.__opticalGlassSignature===signature&&this.lutKey==='opticalglass/'+signature)return;
    // Use original chrome environment and its highlights; do not touch meshes or tentacles.
    this.finish='obsidian';this.lutKey='';
    try{original.call(this);}finally{this.finish='opticalglass';}
    const lut=this.lut;
    const colors=A.PALETTES[this.settings.palette].colors;
    const tint=color?decode(color):decode(colors[0]),secondary=decode(colors[1]);
    const rough=1-p.roughness/.55,tx=p.transmission,io=(p.ior-1)/(p.ior+1),f0=io*io;
    for(let j=0;j<512;j++)for(let i=0;i<512;i++){
      const o=(j*512+i)*4,nx=i/511*2-1,ny=j/511*2-1;
      const nz=Math.sqrt(Math.max(0,1-nx*nx-ny*ny)),g=1-nz,edge=Math.pow(g,.69);
      const fres=f0+(1-f0)*Math.pow(g,5);
      const phase=Math.atan2(ny,nx)*2.7+nx*4.2-ny*3.1+this.studio.lightAngle*.5;
      const crown=Math.pow(Math.max(0,.30+ny*.72+nz*.28-nx*.18),3.5+rough*8);
      const side=Math.pow(Math.max(0,.24-nx*.84+ny*.12+nz*.12),3.5+rough*7);
      const shine=Math.pow(Math.max(0,.18+ny*.76-nx*.22+nz*.26),8+rough*18);
      const bottom=Math.pow(Math.max(0,.20-ny*.83+nx*.12),5);
      const cap=(.55*crown+.43*side+.85*shine+.24*bottom)*(.50+.65*p.rim)*(.7+.3*rough);
      const rim=(.17+.62*p.rim)*Math.pow(g,.56)*(.67+.29*p.thickness);
      for(let k=0;k<3;k++){
        const spectrum=.5+.5*Math.cos(phase*(.74+.70*p.iridescence)+g*7.4*p.ior+[0,2.094395,4.18879][k]);
        const chrome=Math.pow(lut[o+k]/255,2.2);
        const accent=tint[k]*.65+secondary[k]*.35;
        const dispersion=spectrum*p.iridescence*p.saturation*(.13+.28*edge);
        const transmit=(.01+.05*accent+.013*spectrum)*tx*(1-.56*edge);
        const absorption=Math.exp(-p.thickness*(.12+.35*accent)*(1+.75*edge));
        const reflection=chrome*(.39+.41*edge)*(.87+.13*rough);
        const specular=(rim*.31+cap*.67)*[.91,.97,1.05][k];
        const intensity=(reflection+specular+dispersion*(.16+.45*accent)+transmit+chrome*fres*.23)*absorption*p.exposure;
        lut[o+k]=Math.round(255*srgb(aces(Math.max(0,intensity))));
      }
      // Keep alpha opaque for native hit-testing, root attachments and morph reach.
      lut[o+3]=255;
    }
    this.__opticalGlassSignature=signature;
    this.lutKey='opticalglass/'+signature; // Tendrils share and cache this exact LUT.
  };
  Object.defineProperty(proto,'__axxOpticalGlass',{value:true});
  const spec=[
    ['transmission','Transmisión',0,1,.01],['ior','Índice óptico',1,1.9,.01],
    ['thickness','Espesor visual',.05,2,.01],['roughness','Pulido',.015,.55,.005],
    ['iridescence','Iridescencia',0,1.6,.01],['rim','Reflejo del borde',0,2,.01],
    ['saturation','Saturación',0,2,.01],['exposure','Brillo',.4,2.5,.01]
  ];
  function sync(){
    if(!panel)return;
    panel.hidden=A.app?.renderer?.getFinish?.()!=='opticalglass';
    for(const [k,v] of inputs){if(k==='color'){v.value=color||'#70caff';continue;}v.slider.value=p[k];v.output.value=p[k].toFixed(2);}
  }
  function mount(){
    const status=document.getElementById('finish-state');
    if(!status||document.getElementById('axx-optical-controls'))return;
    panel=document.createElement('section');panel.id='axx-optical-controls';panel.hidden=true;
    panel.setAttribute('aria-label','Ajustes de Optical Glass');
    panel.style.cssText='border-top:1px solid #c4dfff24;margin:14px 0;padding:14px 0 0';
    const h=document.createElement('h4');h.textContent='OPTICAL GLASS · LUZ Y CRISTAL';h.style.cssText='font:600 10px system-ui;letter-spacing:1.4px;color:#bad9ea;margin:0 0 12px';panel.append(h);
    const presetBar=document.createElement('div');presetBar.style.cssText='display:flex;flex-wrap:wrap;gap:6px';
    for(const [key,label] of [['reference','Reference Glass'],['crystal','Optical Crystal'],['liquid','Liquid Gel'],['silica','Pure Silica'],['aura','Prismatic Aura']]){
      const b=document.createElement('button');b.type='button';b.textContent=label;
      b.style.cssText='font:11px system-ui;min-height:34px;padding:6px 9px;border-radius:9px';
      b.onclick=()=>set(PRESETS[key]);presetBar.append(b);
    }
    panel.append(presetBar);
    for(const [k,label,min,max,step] of spec){
      const row=document.createElement('label');row.style.cssText='display:block;margin:12px 0 0;color:#bcd1e4;font:11px system-ui';
      const title=document.createElement('span');title.textContent=label;
      const output=document.createElement('output');output.style.cssText='float:right;color:#a2dff5';
      const slider=document.createElement('input');slider.type='range';slider.min=min;slider.max=max;slider.step=step;slider.style.cssText='width:100%;display:block;margin-top:8px';
      slider.oninput=()=>set({[k]:Number(slider.value)});
      row.append(title,output,slider);panel.append(row);inputs.set(k,{slider,output});
    }
    const label=document.createElement('label');label.style.cssText='display:flex;justify-content:space-between;align-items:center;font:11px system-ui;margin:12px 0';label.textContent='Color personalizado';
    const picker=document.createElement('input');picker.type='color';picker.value='#70caff';picker.style.cssText='width:55px;height:36px';
    picker.oninput=()=>set({color:picker.value});label.append(picker);panel.append(label);inputs.set('color',picker);
    const reset=document.createElement('button');reset.type='button';reset.textContent='Colores originales de la paleta';reset.onclick=()=>set({color:''});panel.append(reset);
    status.insertAdjacentElement('afterend',panel);
    for(const b of document.querySelectorAll('.finish-cards [data-finish],#finish-apply,#finish-restore'))b.addEventListener('click',()=>queueMicrotask(sync));
    sync();
  }
  mount();if(!panel)document.addEventListener('DOMContentLoaded',mount,{once:true});
  window.AxxOpticalGlass=Object.freeze({get:()=>({...p,color}),set,presets:Object.keys(PRESETS),version:'1.0.0'});
})();