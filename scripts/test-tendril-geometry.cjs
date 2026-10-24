const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('1.AXX/Axx.html','utf8'),Axx={};
for(const name of ['organicCurve','flowArmRadius','fitTendrilLink']){const begin=html.indexOf('    function '+name+'('),end=html.indexOf('    Axx.'+name+' = '+name+';',begin);vm.runInNewContext(html.slice(begin,end)+'Axx.'+name+'='+name,{Axx,Math});}
for(const length of [8,24,60,180,600,2000]){let previous=Infinity;for(let i=0;i<=1000;i++){const r=Axx.flowArmRadius(i/1000,length);assert(Number.isFinite(r)&&r>=0&&r<=previous+1e-9);previous=r;}assert.equal(previous,0);}
for(const b of [{x:200,y:0},{x:-200,y:100},{x:0,y:-1000}]){const a={x:0,y:0},d=Math.hypot(b.x,b.y);for(const t of [0,1]){const q=Axx.organicCurve(a,b,t,0);assert(Math.hypot(q.x-(t?b.x:0),q.y-(t?b.y:0))<1e-8);}const q=Axx.organicCurve(a,b,.00001,0);assert(Math.abs(q.x*b.y-q.y*b.x)/(Math.hypot(q.x,q.y)*d)<.0001);}
const opaque=(x,y)=>x*x+y*y<50*50;
for(const distance of [80,100,200,1600]){const l=Axx.fitTendrilLink({a:{x:0,y:0},b:{x:distance,y:0},targetRadius:30},opaque,100);assert(l);assert(opaque(l.a.x,l.a.y));assert.equal(l.b.x,distance-24);assert(l.rootRadius<=24);assert(l.rootRadius<(l.b.x-l.a.x)*.3);}
assert.equal(Axx.fitTendrilLink({a:{x:0,y:0},b:{x:60,y:0},targetRadius:30},opaque,100),null);
assert.equal(Axx.fitTendrilLink({a:{x:0,y:0},b:{x:200,y:0}},()=>false,100),null);
assert.equal(Axx.fitTendrilLink({a:{x:0,y:0},b:{x:NaN,y:0}},opaque,100),null);
console.log('PASS: tapered radius, fixed endpoints/tangents, silhouette roots, target insets, near overlap and invalid inputs');
(async()=>{
 const begin=html.indexOf('    class OrganicTendrils {'),end=html.indexOf('    Axx.OrganicTendrils = OrganicTendrils;',begin);
 let cleared=0;
 const document={body:{append(){}},createElement:()=>({setAttribute(){},getContext:()=>({clearRect(){cleared++;}})})};
 vm.runInNewContext(html.slice(begin,end)+'Axx.OrganicTendrils=OrganicTendrils;',{Axx,document,queueMicrotask,Math,performance});
 const tube=new Axx.OrganicTendrils(),frames=[];let silhouette=0,failures=0;
 const renderer={recordFailure(){failures++;}};
 tube.render=(links,phase)=>frames.push({phase,silhouette});
 tube.draw([],1,null,0,renderer);tube.draw([],2,null,0,renderer);
 assert.equal(frames.length,0);silhouette=1;
 await Promise.resolve();assert.deepEqual(frames,[{phase:2,silhouette:1}]);
 tube.render=()=>{throw Error('probe');};tube.draw([],3,null,0,renderer);await Promise.resolve();
 assert.equal(failures,1);assert.equal(cleared,1);assert.equal(tube.drawQueued,false);
 console.log('PASS: same-frame silhouette, coalesced drawing and observable render failure');
})().catch(error=>{console.error(error);process.exitCode=1;});
