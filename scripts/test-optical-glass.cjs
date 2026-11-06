'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, '1.AXX/Axx.html'), 'utf8');
const addon = fs.readFileSync(path.join(root, '1.AXX/scripts/optical-glass.js'), 'utf8');
assert.match(html, /data-finish="opticalglass"/);
assert.match(html, /<script src="scripts\/optical-glass\.js"><\/script>/);
for (const name of ['obsidian', 'prism', 'smoke']) assert.match(html, new RegExp('data-finish="'+name+'"'));
assert.equal((html.match(/\['obsidian', 'prism', 'smoke', 'opticalglass'\]\.includes/g)||[]).length, 3);
const PALETTES = Array.from({length:9},()=>({colors:['#5c9fff','#9af9ff','#8759f8','#fbd2ae']}));
class Renderer {
  constructor() {
    this.finish='obsidian'; this.settings={palette:0,keepForm:true};
    this.studio={roughness:.035,exposure:1,lightAngle:0};
    this.state='idle'; this.lutKey=''; this.lut=new Uint8ClampedArray(512*512*4);
  }
  getFinish(){return this.finish;}
  shadeTable(){
    this.lutKey='native/'+this.finish;
    for(let i=0;i<this.lut.length;i+=4){this.lut[i]=45;this.lut[i+1]=130;this.lut[i+2]=212;this.lut[i+3]=255;}
  }
}
const instance=new Renderer();
const win={Axx:{SoftwareRenderer:Renderer,PALETTES,app:{renderer:instance}}};
const store=new Map();
const ctx={window:win,console,document:{getElementById:()=>null,addEventListener:()=>{}},
  localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},Object,Math,Number,JSON};
vm.runInNewContext(addon,ctx,{filename:'optical-glass.js',timeout:5000});
assert.equal(win.AxxOpticalGlass.version,'1.0.0');
instance.shadeTable();
assert.equal(instance.lutKey,'native/obsidian');
assert.equal(instance.lut[0],45);
instance.finish='opticalglass';
instance.shadeTable();
const sample=Array.from(instance.lut.slice(0,8));
assert.ok(instance.lutKey.startsWith('opticalglass/'));
assert.notEqual(instance.lut[0],45);
assert.equal(instance.lut[3],255);
instance.shadeTable();
assert.deepEqual(Array.from(instance.lut.slice(0,8)),sample);
win.AxxOpticalGlass.set({ior:1.55,iridescence:1.1,color:'#de88ff'});
assert.equal(win.AxxOpticalGlass.get().color,'#de88ff');
assert.equal(instance.lutKey,'');
instance.shadeTable();
assert.ok(instance.lutKey.startsWith('opticalglass/'));
instance.finish='smoke';
instance.shadeTable();
assert.equal(instance.lutKey,'native/smoke');
assert.equal(instance.lut[0],45);
console.log('Optical Glass: opt-in finish, source integration, presets, cache, and legacy materials OK');