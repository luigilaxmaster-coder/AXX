// Spatial scene runtime for backend-validated ScenePlan data (backend/presentation_plan.py).
// Loaded on demand by Magic Pen. It renders only after a change, so it never runs a
// continuous loop next to the avatar, and dispose() releases every GPU resource.
import * as THREE from './three.module.min.js';

let live = 0;
export const liveScenes = () => live;

const scaled=(g,x,y,z)=>{g.scale(x,y,z);return g;};
// Physically based presets (roughness, metalness, base opacity). Environment reflections make the metals read as metal.
const MATERIALS={metal_brushed:{r:.38,m:.92},metal_polished:{r:.14,m:1},metal_anodized:{r:.34,m:.8},plastic:{r:.46,m:0},rubber:{r:.92,m:0},glass:{r:.06,m:0,a:.32},ceramic:{r:.18,m:0},wood:{r:.72,m:0},fabric:{r:.96,m:0},stone:{r:.88,m:0},paint:{r:.38,m:.12},emissive:{r:.5,m:0,glow:true}};
const sceneSignature=o=>JSON.stringify([o.size,o.param??null,o.material??null]);

function geometry(shape, [x, y, z], param) {
    switch (shape) {
        case 'box': {
            const r=Math.min(x,y,z)*Math.min(.3,param??.08);
            if(r<.015||z<=2*r||x<=2*r||y<=2*r)return new THREE.BoxGeometry(x,y,z);
            const s=new THREE.Shape();
            s.moveTo(-x/2+r,-y/2);s.lineTo(x/2-r,-y/2);s.quadraticCurveTo(x/2,-y/2,x/2,-y/2+r);
            s.lineTo(x/2,y/2-r);s.quadraticCurveTo(x/2,y/2,x/2-r,y/2);
            s.lineTo(-x/2+r,y/2);s.quadraticCurveTo(-x/2,y/2,-x/2,y/2-r);
            s.lineTo(-x/2,-y/2+r);s.quadraticCurveTo(-x/2,-y/2,-x/2+r,-y/2);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:Math.max(.01,z-2*r),bevelEnabled:true,bevelThickness:r,bevelSize:r,bevelSegments:3,steps:1});
            g.translate(0,0,-(z-2*r)/2);return g;
        }
        case 'sphere': return new THREE.SphereGeometry(x / 2, 40, 24);
        case 'ellipsoid': return scaled(new THREE.SphereGeometry(.5, 40, 24), x, y, z);
        case 'cylinder': return scaled(new THREE.CylinderGeometry(.5, .5, 1, 48), x, y, z);
        case 'cone': return scaled(new THREE.ConeGeometry(.5, 1, 48), x, y, z);
        case 'frustum': return scaled(new THREE.CylinderGeometry(.5 * Math.max(.05, param ?? .6), .5, 1, 48), x, y, z);
        case 'hexprism': return scaled(new THREE.CylinderGeometry(.5, .5, 1, 6), x, y, z);
        case 'tube': {
            const inner=.5*(1-Math.min(.9,Math.max(.04,param ?? .18)));
            const profile=[[inner,-.5],[.5,-.5],[.5,.5],[inner,.5],[inner,-.5]].map(([r,h])=>new THREE.Vector2(r,h));
            return scaled(new THREE.LatheGeometry(profile, 48), x, y, z);
        }
        case 'capsule': {
            const r=Math.min(x,z)/2;
            return scaled(new THREE.CapsuleGeometry(r, Math.max(0,y-2*r), 10, 32), x/(2*r), 1, z/(2*r));
        }
        case 'dome': {
            const g=scaled(new THREE.SphereGeometry(.5, 40, 20, 0, Math.PI*2, 0, Math.PI/2), x, 2*y, z);
            g.translate(0, -y/2, 0);return g;
        }
        case 'wedge': {
            const s=new THREE.Shape();s.moveTo(-x/2,-y/2);s.lineTo(x/2,-y/2);s.lineTo(-x/2,y/2);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:z,bevelEnabled:false,steps:1});g.translate(0,0,-z/2);return g;
        }
        case 'gable': {
            const s=new THREE.Shape();s.moveTo(-x/2,-y/2);s.lineTo(x/2,-y/2);s.lineTo(0,y/2);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:z,bevelEnabled:false,steps:1});g.translate(0,0,-z/2);return g;
        }
        case 'gear': {
            const teeth=Math.max(6,Math.min(36,Math.round(param??14))),s=new THREE.Shape();
            const rOuter=.5,rRoot=.38,rHole=.16;
            for(let i=0;i<teeth;i++){
                const a0=(i/teeth)*Math.PI*2,a1=a0+(Math.PI/teeth)*.25,a2=a0+(Math.PI/teeth)*.55,a3=a0+(Math.PI/teeth)*.8;
                if(i===0)s.moveTo(Math.cos(a0)*rRoot,Math.sin(a0)*rRoot);else s.lineTo(Math.cos(a0)*rRoot,Math.sin(a0)*rRoot);
                s.lineTo(Math.cos(a1)*rOuter,Math.sin(a1)*rOuter);s.lineTo(Math.cos(a2)*rOuter,Math.sin(a2)*rOuter);s.lineTo(Math.cos(a3)*rRoot,Math.sin(a3)*rRoot);
            }
            s.closePath();const hole=new THREE.Path();hole.absarc(0,0,rHole,0,Math.PI*2,true);s.holes.push(hole);
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);g.rotateX(Math.PI/2);return scaled(g,x,y,z);
        }
        case 'coil':
        case 'spring': {
            const turns=Math.max(2,Math.min(12,param??4.5));
            class HelixCurve extends THREE.Curve{
                getPoint(t){const a=t*Math.PI*2*turns;return new THREE.Vector3(Math.cos(a)*.42,t-.5,Math.sin(a)*.42);}
            }
            const g=new THREE.TubeGeometry(new HelixCurve(),Math.round(turns*24),.08,12,false);return scaled(g,x,y,z);
        }
        case 'l_bracket': {
            const t=Math.min(.45,Math.max(.06,param??.18)),s=new THREE.Shape();
            s.moveTo(-.5,-.5);s.lineTo(.5,-.5);s.lineTo(.5,-.5+t);s.lineTo(-.5+t,-.5+t);s.lineTo(-.5+t,.5);s.lineTo(-.5,.5);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);return scaled(g,x,y,z);
        }
        case 'u_channel': {
            const t=Math.min(.35,Math.max(.06,param??.15)),s=new THREE.Shape();
            s.moveTo(-.5,.5);s.lineTo(-.5+t,.5);s.lineTo(-.5+t,-.5+t);s.lineTo(.5-t,-.5+t);s.lineTo(.5-t,.5);s.lineTo(.5,.5);s.lineTo(.5,-.5);s.lineTo(-.5,-.5);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);return scaled(g,x,y,z);
        }
        case 'i_beam': {
            const tf=Math.min(.25,Math.max(.05,param??.12)),tw=tf*.9,s=new THREE.Shape();
            s.moveTo(-.5,.5);s.lineTo(.5,.5);s.lineTo(.5,.5-tf);s.lineTo(tw/2,.5-tf);s.lineTo(tw/2,-.5+tf);s.lineTo(.5,-.5+tf);s.lineTo(.5,-.5);s.lineTo(-.5,-.5);s.lineTo(-.5,-.5+tf);s.lineTo(-tw/2,-.5+tf);s.lineTo(-tw/2,.5-tf);s.lineTo(-.5,.5-tf);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);return scaled(g,x,y,z);
        }
        case 'pipe_elbow': {
            const g=new THREE.TorusGeometry(.5,Math.min(.3,Math.max(.08,param??.22)),20,32,Math.PI/2);
            g.translate(-.5,-.5,0);return scaled(g,x,y,z);
        }
        case 'heatsink': {
            const fins=Math.max(3,Math.min(12,Math.round(param??6))),s=new THREE.Shape(),baseH=.18,finSpan=1/fins,finW=finSpan*.35;
            s.moveTo(-.5,-.5);s.lineTo(.5,-.5);s.lineTo(.5,-.5+baseH);
            for(let i=fins-1;i>=0;i--){
                const xr=-.5+i*finSpan+finW,xl=-.5+i*finSpan;
                s.lineTo(xr,-.5+baseH);s.lineTo(xr,.5);s.lineTo(xl,.5);s.lineTo(xl,-.5+baseH);
            }
            s.lineTo(-.5,-.5+baseH);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);return scaled(g,x,y,z);
        }
        case 'flange': {
            const s=new THREE.Shape();s.absarc(0,0,.5,0,Math.PI*2,false);
            const ch=new THREE.Path();ch.absarc(0,0,.22,0,Math.PI*2,true);s.holes.push(ch);
            const bolts=Math.max(4,Math.min(12,Math.round(param??6)));
            for(let i=0;i<bolts;i++){
                const a=(i/bolts)*Math.PI*2,bh=new THREE.Path();bh.absarc(Math.cos(a)*.38,Math.sin(a)*.38,.04,0,Math.PI*2,true);s.holes.push(bh);
            }
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);g.rotateX(Math.PI/2);return scaled(g,x,y,z);
        }
        case 'pyramid': return scaled(new THREE.ConeGeometry(.5*Math.SQRT2,1,4),x,y,z);
        case 'threaded_rod': {
            const pitches=Math.max(4,Math.min(40,Math.round(param??14))),profile=[new THREE.Vector2(0,-.5)];
            for(let i=0;i<=pitches*2;i++)profile.push(new THREE.Vector2(i%2?.5:.41,-.5+i/(pitches*2)));
            profile.push(new THREE.Vector2(0,.5));
            return scaled(new THREE.LatheGeometry(profile,32),x,y,z);
        }
        case 'slot': {
            const s=new THREE.Shape(),r=.5*Math.min(1,y/Math.max(x,1e-3)),hx=.5-r;
            s.absarc(hx,0,r,-Math.PI/2,Math.PI/2,false);s.absarc(-hx,0,r,Math.PI/2,Math.PI*1.5,false);s.closePath();
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1,curveSegments:24});g.translate(0,0,-.5);return scaled(g,x,x,z);
        }
        case 'rect_tube': {
            const t=Math.min(.4,Math.max(.04,param??.12)),s=new THREE.Shape();
            s.moveTo(-.5,-.5);s.lineTo(.5,-.5);s.lineTo(.5,.5);s.lineTo(-.5,.5);s.closePath();
            const h=new THREE.Path();h.moveTo(-.5+t,-.5+t);h.lineTo(-.5+t,.5-t);h.lineTo(.5-t,.5-t);h.lineTo(.5-t,-.5+t);h.closePath();s.holes.push(h);
            const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);g.rotateX(Math.PI/2);return scaled(g,x,y,z);
        }
        case 'arc': {
            const angle=THREE.MathUtils.degToRad(Math.max(30,Math.min(360,param??180)));
            return scaled(new THREE.TorusGeometry(.42,.08,16,48,angle),x,y,z);
        }
        case 'knurled_cylinder': {
            const ribs=Math.max(8,Math.min(48,Math.round(param??24))),s=new THREE.Shape();
            for(let i=0;i<ribs*2;i++){const a=(i/(ribs*2))*Math.PI*2,r=i%2?.46:.5;i?s.lineTo(Math.cos(a)*r,Math.sin(a)*r):s.moveTo(Math.cos(a)*r,Math.sin(a)*r);}
            s.closePath();const g=new THREE.ExtrudeGeometry(s,{depth:1,bevelEnabled:false,steps:1});g.translate(0,0,-.5);g.rotateX(Math.PI/2);return scaled(g,x,y,z);
        }
        case 'chamfer_cylinder': {
            const c=Math.min(.25,Math.max(.02,param??.08));
            const profile=[[0,-.5],[.5-c,-.5],[.5,-.5+c],[.5,.5-c],[.5-c,.5],[0,.5]].map(([r,h])=>new THREE.Vector2(r,h));
            return scaled(new THREE.LatheGeometry(profile,48),x,y,z);
        }
        case 'torus': return new THREE.TorusGeometry(x / 2, Math.max(.02, Math.min(x / 4, y / 2)), 20, 48);
        default: return new THREE.BoxGeometry(x, .02, z);
    }
}

// Studio environment (soft boxes over a graded dome) for physically based reflections; no external HDR asset is loaded.
function studioEnvironment(renderer){
    const pm=new THREE.PMREMGenerator(renderer),env=new THREE.Scene(),disposables=[];
    const sky=new THREE.SphereGeometry(10,32,16),pos=sky.attributes.position,colors=[];
    for(let i=0;i<pos.count;i++){const t=(pos.getY(i)/10+1)/2,c=new THREE.Color().setHSL(.6,.1,.06+.5*t);colors.push(c.r,c.g,c.b);}
    sky.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
    const skyMaterial=new THREE.MeshBasicMaterial({side:THREE.BackSide,vertexColors:true});env.add(new THREE.Mesh(sky,skyMaterial));disposables.push(sky,skyMaterial);
    for(const [x,y,z,w,h,i] of [[4,6,6,5,3,4],[-7,3,3,2,5,2],[0,7,-6,6,2,2.5]]){
        const g=new THREE.PlaneGeometry(w,h),m=new THREE.MeshBasicMaterial({color:new THREE.Color(i,i,i),side:THREE.DoubleSide}),box=new THREE.Mesh(g,m);
        box.position.set(x,y,z);box.lookAt(0,0,0);env.add(box);disposables.push(g,m);
    }
    const target=pm.fromScene(env,.04);pm.dispose();disposables.forEach(d=>d.dispose());return target;
}

function objectMesh(o, fallbackExplode) {
    const [x,y,z]=o.size, engineered=['piston','connecting_rod','crankshaft','engine_cylinder'].includes(o.shape);
    const preset=MATERIALS[o.material]||{r:engineered?.32:.42,m:engineered?.45:.28};
    const material=new THREE.MeshStandardMaterial({color:o.color,roughness:preset.r,metalness:preset.m,transparent:true,opacity:preset.a??1,envMapIntensity:.7,side:['engine_cylinder','tube','dome','pipe_elbow','flange','u_channel','l_bracket','rect_tube','arc'].includes(o.shape)?THREE.DoubleSide:THREE.FrontSide}), geometries=[],materials=[material];
    material.userData={base:preset.a??1,glow:!!preset.glow};if(preset.glow){material.emissive.set(o.color);material.emissiveIntensity=.9;}
    const trim=engineered?new THREE.MeshStandardMaterial({color:0xd8e4f2,roughness:.26,metalness:.48,side:THREE.DoubleSide}):material;
    const seal=engineered?new THREE.MeshStandardMaterial({color:0x24344a,roughness:.50,metalness:.38}):material;
    if(engineered)materials.push(trim,seal);
    const addContour=(target,geo)=>{
        const edges=new THREE.EdgesGeometry(geo,26);
        const line=new THREE.LineSegments(edges,new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:.18,depthWrite:false}));
        target.add(line);geometries.push(edges);materials.push(line.material);
    };
    const part=(root,g,position=[0,0,0],rotation=[0,0,0],finish=material)=>{
        const m=new THREE.Mesh(g,finish);m.position.fromArray(position);m.rotation.set(...rotation);m.userData.id=o.id;
        addContour(m,g);root.add(m);geometries.push(g);
    };
    let root;
    if(['piston','connecting_rod','crankshaft','engine_cylinder'].includes(o.shape)){
        root=new THREE.Group();
        if(o.shape==='piston'){
            part(root,new THREE.CylinderGeometry(x*.46,x*.48,y*.82,48));
            part(root,new THREE.CylinderGeometry(x*.43,x*.46,y*.12,48),[0,y*.43,0]);
            for(const offset of [.12,.24,.34])part(root,new THREE.TorusGeometry(x*.465,Math.max(.012,y*.025),8,48),[0,y*offset,0],[Math.PI/2,0,0],seal);
            part(root,new THREE.CylinderGeometry(x*.14,x*.14,z*1.04,24),[0,-y*.13,0],[Math.PI/2,0,0],trim);
        }else if(o.shape==='connecting_rod'){
            part(root,new THREE.BoxGeometry(x*.52,y*.78,z*.52));
            for(const offset of [-.42,.42]){
                for(const face of [-.22,.22])part(root,new THREE.TorusGeometry(x*.38,x*.11,10,32),[0,y*offset,z*face],[0,0,0],trim);
            }
        }else if(o.shape==='crankshaft'){
            part(root,new THREE.CylinderGeometry(z*.24,z*.24,x,32),[0,0,0],[0,0,Math.PI/2]);
            for(const offset of [-.22,.22])part(root,new THREE.CylinderGeometry(y*.56,y*.56,x*.13,32),[x*offset,0,0],[0,0,Math.PI/2]);
            for(const offset of [-.44,.44])part(root,new THREE.CylinderGeometry(z*.36,z*.36,x*.1,32),[x*offset,0,0],[0,0,Math.PI/2],trim);
            part(root,new THREE.CylinderGeometry(z*.22,z*.22,x*.46,32),[0,y*.5,0],[0,0,Math.PI/2],seal);
        }else{
            part(root,new THREE.CylinderGeometry(x/2,x/2,y,48,1,true,Math.PI*.15,Math.PI*1.4));
            for(const offset of [-.42,-.14,.14,.42])part(root,new THREE.RingGeometry(x*.51,x*.58,48,1,Math.PI*.15,Math.PI*1.4),[0,y*offset,0],[-Math.PI/2,0,0],trim);
        }
    }else{
        const g=geometry(o.shape,o.size,o.param);
        root=new THREE.Mesh(g,material);geometries.push(g);
        addContour(root,g);
    }
    root.position.fromArray(o.position);if(o.rotation)root.rotation.set(...o.rotation.map(THREE.MathUtils.degToRad));
    root.userData={id:o.id,base:root.position.clone(),explode:new THREE.Vector3(...(o.explode||fallbackExplode||[0,1.5,0])),material,materials,geometries,shape:o.shape,size:sceneSignature(o)};
    return root;
}

function releaseObject(mesh){for(const g of mesh.userData.geometries)g.dispose();for(const m of mesh.userData.materials)m.dispose();mesh.removeFromParent();}

// Default exploded view when the model gives no `explode` vector (it almost never does, and the old default lifted every piece by the same
// amount, so nothing visibly separated). Sub-assemblies (same `group`) move together away from the assembly centre and open slightly inside
// themselves; central pieces move along the main axis, alternating direction. Explicit vectors from the plan are always respected.
export function explodeVectors(objects){
    const out=new Map(),todo=objects.filter(o=>!Array.isArray(o.explode));if(!todo.length)return out;
    const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    // Effective size: a quarter turn about an axis swaps the other two dimensions (the usual case: shafts and tubes lying on their side).
    const dims=o=>{const d=[...(o.size||[0,0,0])];(o.rotation||[0,0,0]).forEach((deg,axis)=>{if(Math.round(Math.abs(deg)/90)%2===1){const [i,j]=[0,1,2].filter(k=>k!==axis);[d[i],d[j]]=[d[j],d[i]];}});return d;};
    for(const o of objects){const d=dims(o);for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],o.position[i]-d[i]/2);hi[i]=Math.max(hi[i],o.position[i]+d[i]/2);}}
    const center=lo.map((v,i)=>(v+hi[i])/2),ext=hi.map((v,i)=>v-lo[i]),span=Math.max(...ext,1),axis=ext.indexOf(Math.max(...ext));
    const norm=v=>{const l=Math.hypot(...v);return l>1e-6?v.map(x=>x/l):null;},alongAxis=sign=>{const a=[0,0,0];a[axis]=sign;return a;};
    const units=new Map();
    for(const o of todo){const key=o.group?'g:'+o.group:'o:'+o.id,u=units.get(key)||{items:[],sum:[0,0,0]};u.items.push(o);for(let i=0;i<3;i++)u.sum[i]+=o.position[i];units.set(key,u);}
    let turn=0;
    for(const u of units.values()){
        const c=u.sum.map(v=>v/u.items.length),off=c.map((v,i)=>v-center[i]),dist=Math.hypot(...off);
        // A central sub-assembly opens up on itself without travelling; a lone central piece slides along the main axis.
        const central=dist<=span*.12,multi=u.items.length>1,dir=!central?norm(off):multi?[0,0,0]:alongAxis(turn++%2?-1:1),push=dir.map(v=>v*span*(.22+.5*Math.min(1,dist/span)));
        for(const o of u.items){
            let local=[0,0,0];
            if(u.items.length>1){const d=o.position.map((v,i)=>v-c[i]),n=norm(d)||alongAxis(1),k=central?1:.8,m=Math.min(span*(central?.3:.16),Math.hypot(...d)*k+span*(central?.05:.04));local=n.map(v=>v*m);}
            out.set(o.id,push.map((v,i)=>+(v+local[i]).toFixed(3)));
        }
    }
    return out;
}

export function mountScene(container, scene, {reducedMotion = false, onPick = () => {}, onLost = () => {}, onChange = () => {}, initialView = null} = {}) {
    const canvas = document.createElement('canvas');
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true}); // Throws when WebGL is unavailable.
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.3;
    canvas.className = 'mp-scene-canvas'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Escena 3D conceptual. Arrastra o usa las flechas para girar; rueda, + o − para acercar.');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    const annotations=document.createElement('div');annotations.className='mp-scene-annotations';
    const tooltip=document.createElement('div');tooltip.className='mp-scene-tooltip';tooltip.hidden=true;tooltip.setAttribute('aria-hidden','true');
    container.append(canvas,annotations,tooltip); live++;

    const world = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, .1, 200), meshes = new Map(), arrows = [];
    const environment=studioEnvironment(renderer);world.environment=environment.texture;
    world.add(new THREE.HemisphereLight(0xf2f7ff, 0x182434, 0.95));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(6, 10, 8); world.add(sun);
    const fill = new THREE.DirectionalLight(0xa6c5f2, 1.25); fill.position.set(-6, 4, 6); world.add(fill);
    const rim = new THREE.DirectionalLight(0x78b8ff, 1.7); rim.position.set(-4, 6, -8); world.add(rim);
    const autoExplode=explodeVectors(scene.objects);
    for (const o of scene.objects) {
        const mesh=objectMesh(o,autoExplode.get(o.id));meshes.set(o.id,mesh);world.add(mesh);
    }
    for (const a of scene.arrows || []) {
        const from = meshes.get(a.from).position, direction = meshes.get(a.to).position.clone().sub(from), length = direction.length();
        if (length < 1e-6) { arrows.push(null); continue; }
        const arrow = new THREE.ArrowHelper(direction.normalize(), from, length, 0x9274ff, Math.min(.4, length * .25), Math.min(.2, length * .12));
        world.add(arrow); arrows.push(arrow);
    }

    const bounds = new THREE.Box3(); meshes.forEach(m => bounds.expandByObject(m));
    const center = bounds.getCenter(new THREE.Vector3());let radius = Math.max(.5, bounds.getSize(new THREE.Vector3()).length() / 2), restDistance = 0;
    const view = {target: center.clone(), theta: scene.objects.some(o=>o.shape==='engine_cylinder')?-.95:.7, phi: 1.1, distance: radius * 2.45};
    if (initialView && Array.isArray(initialView.target) && initialView.target.length === 3
        && [...initialView.target, initialView.theta, initialView.phi, initialView.distance].every(Number.isFinite)
        && initialView.distance > 0) {
        view.target.fromArray(initialView.target); view.theta = initialView.theta;
        view.phi = Math.min(Math.PI - .15, Math.max(.15, initialView.phi));
        view.distance = Math.min(radius * 8, Math.max(radius * .8, initialView.distance));
    }
    let frame = 0, focused = [], exploded = false, disposed = false;
    const labels=new Map();
    const syncLabels=()=>{annotations.replaceChildren();labels.clear();for(const [index,o] of scene.objects.slice(0,8).entries()){
        const label=document.createElement('button');label.type='button';label.className='mp-part-label';label.setAttribute('aria-label','Seleccionar '+o.label);
        const number=document.createElement('span');number.textContent=String(index+1).padStart(2,'0');const name=document.createElement('span');name.textContent=o.label;
        label.append(number,name);label.onclick=()=>onPick(o.id);annotations.append(label);labels.set(o.id,label);
    }};
    syncLabels();
    const hidden = new Set(), separated = new Set();
    const animations = {};
    const render = () => {
        if (disposed) return;
        const {target, theta, phi, distance} = view;
        camera.position.set(target.x + distance * Math.sin(phi) * Math.sin(theta), target.y + distance * Math.cos(phi), target.z + distance * Math.sin(phi) * Math.cos(theta));
        camera.lookAt(target);camera.updateMatrixWorld();renderer.render(world, camera);
        const placed=[];
        for(const [id,label] of labels){const mesh=meshes.get(id);if(!mesh?.visible){label.hidden=true;continue;}const p=mesh.getWorldPosition(new THREE.Vector3()).project(camera);
            label.hidden=p.z< -1||p.z>1||Math.abs(p.x)>.9||Math.abs(p.y)>.9;
            if(!label.hidden){const x=Math.max(76,Math.min(canvas.clientWidth-76,(p.x+1)*canvas.clientWidth/2)),anchor=(1-p.y)*canvas.clientHeight/2;let y=Math.max(34,anchor-12);
                while(placed.some(other=>Math.abs(other.x-x)<140&&Math.abs(other.y-y)<32)&&y>42)y-=34;
                placed.push({x,y});label.style.left=x+'px';label.style.top=y+'px';label.style.setProperty('--mp-leader',Math.max(10,anchor-y)+'px');label.dataset.focused=String(focused.includes(id));}}
    };
    const schedule = () => { if (!frame && !disposed) frame = requestAnimationFrame(() => { frame = 0; render(); }); };
    const tween = (key, apply) => {
        cancelAnimationFrame(animations[key]);
        if (reducedMotion) { apply(1); schedule(); return; }
        const start = performance.now();
        const tick = now => { const t = Math.min(1, (now - start) / 450); apply(t * (2 - t)); render(); if (t < 1) animations[key] = requestAnimationFrame(tick); };
        animations[key] = requestAnimationFrame(tick);
    };
    const moveTarget = goal => { const from = view.target.clone(); tween('target', k => view.target.lerpVectors(from, goal, k)); };
    const resize = () => {
        const width = Math.max(200, container.clientWidth || 300), height = Math.min(Math.round(width * .76),Math.max(220,innerHeight-210));
        renderer.setSize(width, height, false); canvas.style.width = '100%'; canvas.style.height = height + 'px';
        camera.aspect = width / height; camera.updateProjectionMatrix(); schedule();
    };
    const observer = new ResizeObserver(resize); observer.observe(container); resize();

    const abort = new AbortController(), signal = abort.signal;
    const rotate = (dt, dp) => { view.theta += dt; view.phi = Math.min(Math.PI - .15, Math.max(.15, view.phi + dp)); schedule(); };
    const zoom = f => { view.distance = Math.min(radius * 8, Math.max(radius * .8, view.distance * (1 + f))); schedule(); };
    const pan = (dx,dy) => {const unit=2*view.distance*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))/canvas.clientHeight;view.target.addScaledVector(new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0),-dx*unit).addScaledVector(new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,1),dy*unit);schedule();};
    const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
    const hitId=e=>{const r=canvas.getBoundingClientRect();pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);ray.setFromCamera(pointer,camera);const hits=ray.intersectObjects([...meshes.values()],true);for(const hit of hits){let obj=hit.object;while(obj&&!obj.userData?.id&&obj!==world)obj=obj.parent;if(obj?.userData?.id)return obj.userData.id;}return null;};
    let drag = null,hover=null,hoverFrame=0,hoverPoint=null;
    const setHover=id=>{if(id!==hover){hover=id;tooltip.textContent=scene.objects.find(o=>o.id===id)?.label||'';tooltip.hidden=!id;}canvas.style.cursor=id?'pointer':'grab';};
    canvas.addEventListener('contextmenu',e=>e.preventDefault(),{signal});
    canvas.addEventListener('pointerdown', e => { cancelAnimationFrame(hoverFrame);hoverFrame=0;setHover(null);drag = {x: e.clientX, y: e.clientY, moved: 0,pan:e.button===2||e.shiftKey};canvas.style.cursor='grabbing';canvas.setPointerCapture?.(e.pointerId); }, {signal});
    canvas.addEventListener('pointermove', e => {
        if (!drag){const id=hitId(e);setHover(id);return;}
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved += Math.abs(dx) + Math.abs(dy); drag.x = e.clientX; drag.y = e.clientY;
        if(drag.pan)pan(dx,dy);else rotate(-dx * .01, -dy * .01);
    }, {signal});
    canvas.addEventListener('pointerup', e => {
        const click = drag && drag.moved < 5 && !drag.pan; drag = null;
        onChange();
        const id=hitId(e);setHover(id);if(click&&id)onPick(id);
    }, {signal});
    canvas.addEventListener('pointerleave',()=>{cancelAnimationFrame(hoverFrame);hoverFrame=0;setHover(null);},{signal});
    canvas.addEventListener('pointercancel',()=>{drag=null;setHover(null);},{signal});
    canvas.addEventListener('wheel', e => { e.preventDefault(); zoom(Math.sign(e.deltaY) * .12); onChange(); }, {signal, passive: false});
    canvas.addEventListener('keydown', e => {
        const keys = {ArrowLeft: () => rotate(-.15, 0), ArrowRight: () => rotate(.15, 0), ArrowUp: () => rotate(0, -.12), ArrowDown: () => rotate(0, .12),
            '+': () => zoom(-.12), '=': () => zoom(-.12), '-': () => zoom(.12)};
        if (keys[e.key]) { e.preventDefault(); e.stopPropagation(); keys[e.key](); onChange(); }
    }, {signal});
    canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); onLost(); }, {signal});

    // Targets come from resting/exploded goals, never from positions caught mid-animation.
    const goal = m => m.userData.base.clone().addScaledVector(m.userData.explode, exploded||separated.has(m.userData.id) ? 1 : 0);
    const showArrows=()=>arrows.forEach((arrow,index)=>{const link=scene.arrows[index];if(arrow)arrow.visible=!exploded&&!hidden.has(link.from)&&!hidden.has(link.to)&&!separated.has(link.from)&&!separated.has(link.to);});
    const goalBox = () => { const box = new THREE.Box3(); for (const m of meshes.values()) box.union(new THREE.Box3().setFromObject(m).translate(goal(m).sub(m.position))); return box; };
    const focusCenter = () => {
        if (!focused.length && !exploded) return center.clone();
        if (!focused.length) return goalBox().getCenter(new THREE.Vector3());
        const chosen = focused.length ? focused.map(id => meshes.get(id)) : [...meshes.values()];
        return chosen.reduce((sum, m) => sum.add(goal(m)), new THREE.Vector3()).divideScalar(chosen.length);
    };

    return {
        focus(ids,isolated=false) {
            focused = ids.filter(id => meshes.has(id));
            for (const [id, mesh] of meshes) {
                const on = !focused.length || focused.includes(id);
                const material=mesh.userData.material,shell=mesh.userData.shape==='engine_cylinder',base=material.userData.base??1;material.opacity = shell ? .48 : on ? base : base*.58; material.depthWrite = on&&!shell&&base>=1; mesh.visible = !hidden.has(id)&&(!isolated||on);
                if(!material.userData.glow)material.emissive.set(focused.includes(id) ? 0x11182a : 0x000000);
            }
            const visibleFocus = focused.filter(id => !hidden.has(id));
            if (focused.length && !visibleFocus.length) return;
            moveTarget(visibleFocus.length && focused.length
                ? visibleFocus.map(id => meshes.get(id).getWorldPosition(new THREE.Vector3())).reduce((sum, pos) => sum.add(pos), new THREE.Vector3()).divideScalar(visibleFocus.length)
                : focusCenter());
        },
        setHidden(id, value) {
            if (!meshes.has(id)) return;
            if (value) hidden.add(id); else hidden.delete(id);
            meshes.get(id).visible = !value;
            showArrows();
            schedule();
        },
        setExploded(value) {
            exploded = value;
            if(!value)separated.clear();
            // Keep the whole exploded assembly in frame; the resting distance comes back when it is put together again.
            if(value){restDistance=view.distance;const reach=Math.max(.5,goalBox().getSize(new THREE.Vector3()).length()/2);radius=Math.max(radius,reach);view.distance=Math.max(view.distance,reach*2.45);}
            else if(restDistance){view.distance=restDistance;restDistance=0;}
            const starts = new Map([...meshes].map(([id, m]) => [id, m.position.clone()]));
            showArrows(); // Arrows join resting positions only.
            tween('explode', k => { for (const [id, m] of meshes) m.position.lerpVectors(starts.get(id), goal(m), k); });
            moveTarget(focusCenter());
        },
        setObjectExploded(id,value){
            const mesh=meshes.get(id);if(!mesh)return false;
            if(value)separated.add(id);else separated.delete(id);mesh.position.copy(goal(mesh));showArrows();schedule();onChange();return true;
        },
        update(next){
            if(disposed)return;
            for(const key of Object.keys(animations)){cancelAnimationFrame(animations[key]);delete animations[key];}
            const ids=new Set(next.objects.map(o=>o.id));
            for(const [id,mesh] of meshes)if(!ids.has(id)){releaseObject(mesh);meshes.delete(id);hidden.delete(id);separated.delete(id);}
            const nextExplode=explodeVectors(next.objects);
            for(const o of next.objects){
                let mesh=meshes.get(o.id);
                if(!mesh||mesh.userData.shape!==o.shape||mesh.userData.size!==sceneSignature(o)){
                    if(mesh)releaseObject(mesh);mesh=objectMesh(o,nextExplode.get(o.id));meshes.set(o.id,mesh);world.add(mesh);
                }
                mesh.userData.base.fromArray(o.position);mesh.userData.explode.fromArray(o.explode||nextExplode.get(o.id)||[0,1.5,0]);
                mesh.position.copy(goal(mesh));mesh.rotation.set(...(o.rotation||[0,0,0]).map(THREE.MathUtils.degToRad));
                mesh.userData.material.color.set(o.color);mesh.visible=!hidden.has(o.id);
            }
            for(const arrow of arrows)if(arrow){arrow.removeFromParent();arrow.dispose();}arrows.length=0;scene=next;setHover(null);
            for(const a of scene.arrows||[]){
                const from=meshes.get(a.from).position,direction=meshes.get(a.to).position.clone().sub(from),length=direction.length();
                if(length<1e-6){arrows.push(null);continue;}
                const arrow=new THREE.ArrowHelper(direction.normalize(),from,length,0x9274ff,Math.min(.4,length*.25),Math.min(.2,length*.12));
                arrow.visible=!exploded&&!hidden.has(a.from)&&!hidden.has(a.to)&&!separated.has(a.from)&&!separated.has(a.to);world.add(arrow);arrows.push(arrow);
            }
            bounds.makeEmpty();meshes.forEach(m=>bounds.expandByObject(m));bounds.getCenter(center);radius=Math.max(.5,bounds.getSize(new THREE.Vector3()).length()/2);syncLabels();schedule();
        },
        qa(){render();return {objects:meshes.size,triangles:renderer.info.render.triangles,webgl:!renderer.getContext().isContextLost(),finite:[...camera.position.toArray(),...view.target.toArray()].every(Number.isFinite)};},
        snapshot() { render(); return canvas.toDataURL('image/png'); },
        getView() { return {target: view.target.toArray(), theta: view.theta, phi: view.phi, distance: view.distance}; },
        getSeparated(){return [...separated];},
        dispose() {
            if (disposed) return;
            disposed = true; live--; abort.abort(); observer.disconnect(); cancelAnimationFrame(frame);
            Object.values(animations).forEach(cancelAnimationFrame);
            cancelAnimationFrame(hoverFrame);meshes.forEach(releaseObject);arrows.forEach(a=>a?.dispose());environment.dispose();renderer.dispose(); renderer.forceContextLoss(); canvas.remove();annotations.remove();tooltip.remove();
        },
    };
}
