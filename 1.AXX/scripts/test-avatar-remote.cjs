const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
(async()=>{
 const f={x:100,y:100,tx:100,ty:100,go(x,y){this.tx=x;this.ty=y;}};
 const c={follower:f,size:200,interactionLock:false,pointer:{known:true}},rotations=[],waiters=[];
 const Axx={isNative:()=>true,companion:c,app:{renderer:{rotate:(...v)=>rotations.push(v)}},backendRequest:()=>new Promise(resolve=>waiters.push(resolve))};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'avatar-remote.js'),'utf8'),{window:{Axx,addEventListener(){}},document:{hidden:true},innerWidth:1200,innerHeight:900,performance,setTimeout});
 assert.equal(waiters.length,1);
 waiters.shift()({boot_id:'one',sequence:4,events:[{sequence:1,kind:'rotate',dx:10,dy:5},{sequence:2,kind:'move',dx:10,dy:4},{sequence:3,kind:'move',dx:20,dy:2},{sequence:4,kind:'end'}]});
 await new Promise(setImmediate);
 assert.equal(f.tx,175);assert.equal(f.ty,115);assert.equal(c.interactionLock,false);assert.equal(c.pointer.known,false);assert.deepEqual(rotations,[[.12,.06]]);
 waiters.shift()({boot_id:'two',sequence:1,events:[{sequence:1,kind:'rotate',dx:-10,dy:-5}]});await new Promise(setImmediate);
 assert.equal(rotations.length,2);assert.equal(waiters.length,1);
 console.log('PASS: background gestures, accumulated movement, release and backend restart');
})().catch(e=>{console.error(e);process.exitCode=1;});
