// Spatial scene runtime for backend-validated ScenePlan data (backend/presentation_plan.py).
// Loaded on demand by Magic Pen. It renders only after a change, so it never runs a
// continuous loop next to the avatar, and dispose() releases every GPU resource.
import * as THREE from './three.module.min.js';
import {GLTFLoader} from './vendor/three-r162/GLTFLoader.js';

let live = 0;
export const liveScenes = () => live;

const scaled=(g,x,y,z)=>{g.scale(x,y,z);return g;};
// Physically based presets (roughness, metalness, base opacity). Environment reflections make the metals read as metal.
const MATERIALS={metal_brushed:{r:.38,m:.92},metal_polished:{r:.14,m:1},metal_anodized:{r:.34,m:.8},plastic:{r:.46,m:0},rubber:{r:.92,m:0},glass:{r:.06,m:0,a:.32},ceramic:{r:.18,m:0},wood:{r:.72,m:0},fabric:{r:.96,m:0},stone:{r:.88,m:0},paint:{r:.38,m:.12},emissive:{r:.5,m:0,glow:true}};
const sceneSignature=o=>JSON.stringify([o.size,o.param??null,o.material??null,o.assetId,o.assetNode,o.normalizeGlb]);

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
                case 'octaprism': return scaled(new THREE.CylinderGeometry(.5, .5, 1, 8), x, y, z);
        case 'paraboloid': {
            const steps=24,profile=[new THREE.Vector2(0,-.5)];
            for(let i=1;i<=steps;i++){const t=i/steps;profile.push(new THREE.Vector2(Math.sqrt(t)*.5,t-.5));}
            return scaled(new THREE.LatheGeometry(profile,36),x,y,z);
        }
        case 'arch': {
            const angle=THREE.MathUtils.degToRad(Math.max(30,Math.min(180,param??180)));
            const g=new THREE.TorusGeometry(.5,Math.min(.3,Math.max(.05,param??.15)),20,36,angle);
            g.translate(-.5,0,0);return scaled(g,x,y,z);
        }
        case 'dna_helix': {
            const turns=Math.max(1.5,Math.min(6,param??3));
            class DoubleHelixCurve extends THREE.Curve{
                getPoint(t){
                    if(t<=0.48){const s=t/0.48,a=s*Math.PI*2*turns;return new THREE.Vector3(Math.cos(a)*.4,s-.5,Math.sin(a)*.4);}
                    else if(t<=0.52){const u=(t-0.48)/0.04,a=Math.PI*2*turns+u*Math.PI;return new THREE.Vector3(Math.cos(a)*.4,.5,Math.sin(a)*.4);}
                    else{const s=1-(t-0.52)/0.48,a=s*Math.PI*2*turns+Math.PI;return new THREE.Vector3(Math.cos(a)*.4,s-.5,Math.sin(a)*.4);}
                }
            }
            return scaled(new THREE.TubeGeometry(new DoubleHelixCurve(),Math.round(turns*48),.06,10,false),x,y,z);
        }
        case 'tapered_capsule': {
            const profile=[new THREE.Vector2(0,-.5),new THREE.Vector2(.25,-.48),new THREE.Vector2(.45,-.2),new THREE.Vector2(.5,.1),new THREE.Vector2(.35,.4),new THREE.Vector2(0,.5)];
            return scaled(new THREE.LatheGeometry(profile,36),x,y,z);
        }
        case 'hyperboloid': {
            const steps=32,profile=[],waist=Math.min(.45,Math.max(.1,param??.25));
            for(let i=0;i<=steps;i++){const t=i/steps,y=t-.5,r=Math.sqrt(waist*waist+y*y*(.25-waist*waist)/.25);profile.push(new THREE.Vector2(r,y));}
            return scaled(new THREE.LatheGeometry(profile,36),x,y,z);
        }
        case 'barrel': {
            const steps=32,profile=[],bulge=Math.min(.5,Math.max(.2,param??.42));
            for(let i=0;i<=steps;i++){const t=i/steps,y=t-.5,r=bulge*Math.cos(y*Math.PI*.7);profile.push(new THREE.Vector2(r,y));}
            return scaled(new THREE.LatheGeometry(profile,36),x,y,z);
        }
        case 'trefoil_knot': {
            const p=Math.max(1,Math.min(8,Math.round(param??2))),q=3;
            return scaled(new THREE.TorusKnotGeometry(.35,.08,64,16,p,q),x,y,z);
        }
        case 'triangular_prism': return scaled(new THREE.CylinderGeometry(.5, .5, 1, 3), x, y, z);
        case 'pentaprism': return scaled(new THREE.CylinderGeometry(.5, .5, 1, 5), x, y, z);
        case 'helix_spring': {
            const turns=Math.max(2,Math.min(10,param??4));
            class SpringCurve extends THREE.Curve{
                getPoint(t){const a=t*Math.PI*2*turns;return new THREE.Vector3(Math.cos(a)*.4,t-.5,Math.sin(a)*.4);}
            }
            return scaled(new THREE.TubeGeometry(new SpringCurve(),Math.round(turns*36),.07,12,false),x,y,z);
        }
        case 'tetrahedron': return scaled(new THREE.TetrahedronGeometry(0.5), x, y, z);
        case 'dodecahedron': return scaled(new THREE.DodecahedronGeometry(0.5), x, y, z);
        case 'icosahedron': return scaled(new THREE.IcosahedronGeometry(0.5), x, y, z);
        case 'bipyramid': return scaled(new THREE.OctahedronGeometry(0.5), x, y, z);
        case 'fluted_column': return scaled(new THREE.CylinderGeometry(0.48, 0.48, 1, 32), x, y, z);
        case 'conical_spring': {
            const turns = Math.max(2, Math.min(10, param ?? 4));
            class ConicalCurve extends THREE.Curve {
                getPoint(t) {
                    const a = t * Math.PI * 2 * turns;
                    const r = 0.15 + 0.35 * (1 - t);
                    return new THREE.Vector3(Math.cos(a) * r, t - 0.5, Math.sin(a) * r);
                }
            }
            return scaled(new THREE.TubeGeometry(new ConicalCurve(), Math.round(turns * 36), 0.06, 12, false), x, y, z);
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

function objectMesh(o, fallbackExplode, glbRoot=null) {
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
    if(o.assetId){
        if(!glbRoot)throw Error('El GLB validado todavía no se ha cargado.');
        const source=o.assetNode?glbRoot.getObjectByName(o.assetNode):glbRoot;
        if(!source)throw Error('La pieza CAD no existe en el GLB verificado.');
        glbRoot.updateMatrixWorld(true);const loaded=source.clone(true);loaded.matrixAutoUpdate=false;loaded.matrix.copy(source.matrixWorld);
        root=new THREE.Group();root.add(loaded);
        loaded.traverse(child=>{if(child.isMesh){child.userData.id=o.id;child.geometry=child.geometry.clone();geometries.push(child.geometry);
            const clone=m=>{const next=m.clone();next.userData={...next.userData,base:next.opacity};materials.push(next);return next;};
            child.material=Array.isArray(child.material)?child.material.map(clone):clone(child.material);
        }});
        root.scale.fromArray(o.scale||[1,1,1]);
    }else if(['piston','connecting_rod','crankshaft','engine_cylinder'].includes(o.shape)){
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
    if(o.assetId)material.dispose();
    root.userData={id:o.id,base:root.position.clone(),explode:new THREE.Vector3(...(o.explode||fallbackExplode||[0,1.5,0])),material:o.assetId?materials[1]:material,materials:o.assetId?materials.slice(1):materials,geometries,shape:o.shape,size:sceneSignature(o)};
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
    const glbRoots=new Map(),glbMetadata=new Map();let glbBytes=0,glbTexturePixels=0;
    const releaseGlb=root=>{const textures=new Set();root.traverse(m=>{if(m.geometry)m.geometry.dispose();for(const material of m.material?(Array.isArray(m.material)?m.material:[m.material]):[]){
        for(const value of Object.values(material))if(value?.isTexture)textures.add(value);material.dispose();}});for(const texture of textures){texture.source?.data?.close?.();texture.dispose();}};
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
    // Labels exist for every part; render() shows only what fits (guided/focused first) so complex scenes never saturate.
    const labels=new Map();
    const syncLabels=()=>{annotations.replaceChildren();labels.clear();for(const [index,o] of scene.objects.entries()){
        const label=document.createElement('button');label.type='button';label.className='mp-part-label';label.setAttribute('aria-label','Seleccionar '+o.label);
        const number=document.createElement('span');number.textContent=String(index+1).padStart(2,'0');const name=document.createElement('span');name.textContent=o.label;
        label.append(number,name);label.onclick=()=>onPick(o.id);label.hidden=true;annotations.append(label);labels.set(o.id,label);
    }};
    syncLabels();
    // Guide layer: connectors from a callout to the part's projected anchor and motion arrows, recomputed every frame.
    const SVGNS='http://www.w3.org/2000/svg',guideLayer=document.createElementNS(SVGNS,'svg');guideLayer.setAttribute('class','mp-scene-guide');guideLayer.setAttribute('aria-hidden','true');
    container.append(guideLayer);
    const guide={targets:new Set(),callouts:new Map(),motions:new Map(),onFrame:null};
    const anchorOf=id=>{const m=meshes.get(id);if(!m?.visible)return null;const box=new THREE.Box3().setFromObject(m);if(box.isEmpty())return null;
        const c=box.getCenter(new THREE.Vector3());c.y=Math.min(box.max.y,c.y+(box.max.y-c.y)*.6);return c;};  // a visible point on the upper body, not the hidden centre
    const projectPoint=p=>{const v=p.clone().project(camera);return {x:(v.x+1)*canvas.clientWidth/2,y:(1-v.y)*canvas.clientHeight/2,depth:v.z,visible:v.z>=-1&&v.z<=1&&Math.abs(v.x)<=1.02&&Math.abs(v.y)<=1.02};};
    const hidden = new Set(), separated = new Set();
    const animations = {};
    const render = () => {
        if (disposed) return;
        const {target, theta, phi, distance} = view;
        camera.position.set(target.x + distance * Math.sin(phi) * Math.sin(theta), target.y + distance * Math.cos(phi), target.z + distance * Math.sin(phi) * Math.cos(theta));
        camera.lookAt(target);camera.updateMatrixWorld();renderer.render(world, camera);
        // Priority: guided targets, then focused parts, then everything else by projected size; only what fits is shown.
        const W=canvas.clientWidth,H=canvas.clientHeight,budget=Math.max(6,Math.min(32,Math.floor(W*H/14000))),placed=[],shown=[];
        const rank=id=>guide.targets.has(id)?0:focused.includes(id)?1:2;
        const candidates=[];
        for(const [id,label] of labels){label.hidden=true;const anchor=anchorOf(id);if(!anchor)continue;const p=projectPoint(anchor);
            if(!p.visible||p.x<0||p.y<0||p.x>W||p.y>H)continue;
            const size=new THREE.Box3().setFromObject(meshes.get(id)).getSize(new THREE.Vector3()).length()/Math.max(.1,camera.position.distanceTo(anchor));
            candidates.push({id,label,p,rank:rank(id),size});}
        candidates.sort((a,b)=>a.rank-b.rank||b.size-a.size);
        for(const c of candidates){
            if(shown.length>=budget&&c.rank===2)break;
            const x=Math.max(76,Math.min(W-76,c.p.x));let y=Math.max(34,c.p.y-(c.rank===0?46:12)),ok=true;
            while(placed.some(o=>Math.abs(o.x-x)<140&&Math.abs(o.y-y)<32)){y-=34;if(y<34){ok=false;break;}}
            if(!ok&&c.rank===2)continue;  // never stack unrelated labels on top of each other
            placed.push({x,y});shown.push(c);c.label.hidden=false;c.label.style.left=x+'px';c.label.style.top=y+'px';
            c.label.style.setProperty('--mp-leader',Math.max(10,c.p.y-y)+'px');c.label.dataset.focused=String(focused.includes(c.id));
            c.label.dataset.guided=String(c.rank===0);c.label.dataset.anchorX=String(Math.round(c.p.x));c.label.dataset.anchorY=String(Math.round(c.p.y));
            const callout=guide.callouts.get(c.id);if(callout)c.label.title=callout;
        }
        drawGuide(shown);
        guide.onFrame?.();
    };
    // Connectors for guided labels (label -> exact projected anchor) and arrows for illustrative motions.
    const drawGuide=shown=>{
        guideLayer.setAttribute('viewBox',`0 0 ${canvas.clientWidth} ${canvas.clientHeight}`);guideLayer.setAttribute('width',canvas.clientWidth);guideLayer.setAttribute('height',canvas.clientHeight);
        const parts=[];
        for(const c of shown)if(c.rank===0){const lx=parseFloat(c.label.style.left),ly=parseFloat(c.label.style.top)+14;
            parts.push(`<line class="mp-guide-leader" x1="${lx}" y1="${ly}" x2="${c.p.x.toFixed(1)}" y2="${c.p.y.toFixed(1)}"/><circle class="mp-guide-dot" cx="${c.p.x.toFixed(1)}" cy="${c.p.y.toFixed(1)}" r="5"/><circle class="mp-guide-pulse" cx="${c.p.x.toFixed(1)}" cy="${c.p.y.toFixed(1)}" r="5"/>`);}
        for(const [id,motion] of guide.motions){const m=meshes.get(id);if(!m?.visible)continue;const a=anchorOf(id);if(!a)continue;const p=projectPoint(a);if(!p.visible)continue;
            if(motion.kind==='rotate'){const r=Math.max(18,Math.min(60,40*motion.scale||40));
                parts.push(`<path class="mp-guide-motion" d="M ${(p.x+r).toFixed(1)} ${p.y.toFixed(1)} A ${r} ${r*.45} 0 1 1 ${(p.x-r*.7).toFixed(1)} ${(p.y-r*.32).toFixed(1)}" marker-end="url(#mp-arrow)"/>`);}
            else{const axis=new THREE.Vector3(...motion.axisVector),q=projectPoint(a.clone().addScaledVector(axis,motion.amplitude||.6));
                parts.push(`<line class="mp-guide-motion" x1="${p.x.toFixed(1)}" y1="${p.y.toFixed(1)}" x2="${q.x.toFixed(1)}" y2="${q.y.toFixed(1)}" marker-end="url(#mp-arrow)" marker-start="url(#mp-arrow-back)"/>`);}}
        guideLayer.innerHTML='<defs><marker id="mp-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker>'
            +'<marker id="mp-arrow-back" viewBox="0 0 10 10" refX="2" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>'+parts.join('');
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
        const click = drag && drag.moved < 16 && !drag.pan; drag = null;
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

    // Illustrative motion (not a physics simulation): rotation about the part's own axis or a back-and-forth stroke.
    let motionFrame=0,motionLast=0;
    const AXES={x:new THREE.Vector3(1,0,0),y:new THREE.Vector3(0,1,0),z:new THREE.Vector3(0,0,1)};
    const motionTick=now=>{motionFrame=0;if(disposed||!guide.motions.size)return;
        const dt=Math.min(.05,(now-(motionLast||now))/1000);motionLast=now;
        if(!document.hidden&&canvas.isConnected&&canvas.getClientRects().length){for(const [id,m] of guide.motions){const mesh=meshes.get(id);if(!mesh)continue;m.t+=dt;
            if(m.kind==='rotate')mesh.quaternion.copy(m.baseQuat).multiply(new THREE.Quaternion().setFromAxisAngle(AXES[m.axis],m.t*m.speed));
            else mesh.position.copy(goal(mesh)).addScaledVector(new THREE.Vector3(...m.axisVector),m.amplitude*Math.sin(m.t*2*Math.PI/m.period));}
            render();}
        motionFrame=requestAnimationFrame(motionTick);};
    const stopMotion=id=>{const m=guide.motions.get(id),mesh=meshes.get(id);if(!m)return;guide.motions.delete(id);
        if(mesh){mesh.quaternion.copy(m.baseQuat);mesh.position.copy(goal(mesh));}};

    return {
        /** Screen point (CSS px inside the canvas) of a part's visible anchor, or null when it cannot be shown. */
        project(id){const a=anchorOf(id);if(!a)return null;const p=projectPoint(a);return p.visible?{x:p.x,y:p.y,depth:p.depth}:null;},
        flyTo(goalView={}){const from={...view,target:view.target.clone()};const to={theta:goalView.theta??view.theta,phi:Math.min(Math.PI-.15,Math.max(.15,goalView.phi??view.phi)),
            distance:Math.min(radius*8,Math.max(radius*.5,goalView.distance??view.distance)),target:goalView.target?new THREE.Vector3(...goalView.target):view.target.clone()};
            tween('camera',k=>{view.theta=from.theta+(to.theta-from.theta)*k;view.phi=from.phi+(to.phi-from.phi)*k;view.distance=from.distance+(to.distance-from.distance)*k;view.target.lerpVectors(from.target,to.target,k);});},
        /** Frame the given parts: target their centre and back off just enough to fit them. */
        frame(ids){const box=new THREE.Box3();for(const id of ids){const m=meshes.get(id);if(m?.visible)box.union(new THREE.Box3().setFromObject(m));}if(box.isEmpty())return false;
            const size=box.getSize(new THREE.Vector3()).length();this.flyTo({target:box.getCenter(new THREE.Vector3()).toArray(),distance:Math.max(size*1.9,radius*.6)});return true;},
        animateObject(id,motion){const mesh=meshes.get(id);if(!mesh||reducedMotion)return false;stopMotion(id);
            const axis=['x','y','z'].includes(motion.axis)?motion.axis:'y';
            guide.motions.set(id,{kind:motion.kind==='translate'?'translate':'rotate',axis,t:0,baseQuat:mesh.quaternion.clone(),speed:Number(motion.speed)||Math.PI,
                amplitude:Number(motion.amplitude)||.5,period:Number(motion.period)||1.6,scale:Number(motion.scale)||1,
                axisVector:AXES[axis].clone().applyQuaternion(mesh.quaternion).toArray()});
            motionLast=0;if(!motionFrame)motionFrame=requestAnimationFrame(motionTick);return true;},
        stopMotions(){for(const id of [...guide.motions.keys()])stopMotion(id);cancelAnimationFrame(motionFrame);motionFrame=0;schedule();},
        motions(){return [...guide.motions].map(([id,m])=>({id,kind:m.kind,axis:m.axis,illustrative:true}));},
        /** Guided step: anchored callouts on targets (unique ids that exist), optional per-frame hook for external overlays. */
        setGuide({targets=[],callouts={},onFrame=null}={}){guide.targets=new Set(targets.filter(id=>meshes.has(id)));
            guide.callouts=new Map(Object.entries(callouts).filter(([id])=>meshes.has(id)));guide.onFrame=onFrame;schedule();return [...guide.targets];},
        guideState(){return {targets:[...guide.targets],labels:[...labels].filter(([,l])=>!l.hidden).map(([id,l])=>({id,guided:l.dataset.guided==='true',
            x:+l.dataset.anchorX,y:+l.dataset.anchorY})),motions:this.motions()};},
        hasGlb(assetId){return glbRoots.has(assetId);},
        async loadGlb(assetId,content,verification){
            if(glbRoots.has(assetId))return;
            if(disposed)throw Error('Visor cerrado');
            if(glbRoots.size>=8||glbBytes+verification.size_bytes>32*1024*1024||glbTexturePixels+verification.texture_pixels>32*1024*1024)
                throw Error('Presupuesto de GLB/texturas del visor agotado. Cierra y vuelve a abrir la escena.');
            const bytes=Uint8Array.from(atob(content),c=>c.charCodeAt(0));
            const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
            if(digest!==verification.sha256)throw Error('El GLB cambió durante la transferencia.');
            const manager=new THREE.LoadingManager();manager.setURLModifier(url=>{if(!url.startsWith('blob:')&&!url.startsWith('data:'))throw Error('Recurso externo bloqueado en GLB');return url;});
            const result=await new GLTFLoader(manager).parseAsync(bytes.buffer,'');
            if(disposed){releaseGlb(result.scene);throw Error('Visor cerrado durante la carga');}
            glbRoots.set(assetId,result.scene);glbMetadata.set(assetId,verification);glbBytes+=verification.size_bytes;glbTexturePixels+=verification.texture_pixels;
        },
        geometrySnapshot() {
            const encode = array => {
                const bytes=new Uint8Array(array.buffer,array.byteOffset,array.byteLength);let binary='';
                for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                return btoa(binary);
            };
            world.updateMatrixWorld(true);const parts=[];
            for(const [id,root] of meshes)root.traverse(mesh=>{
                if(!mesh.isMesh||!mesh.geometry?.attributes?.position)return;
                const attr=mesh.geometry.attributes.position, positions=new Float32Array(attr.count*3), point=new THREE.Vector3();
                for(let i=0;i<attr.count;i++)point.fromBufferAttribute(attr,i).applyMatrix4(mesh.matrixWorld).toArray(positions,i*3);
                const indices=mesh.geometry.index?new Uint32Array(mesh.geometry.index.array):Uint32Array.from({length:attr.count},(_,i)=>i);
                const mat=Array.isArray(mesh.material)?mesh.material[0]:mesh.material;
                parts.push({object_id:id,positions_b64:encode(positions),indices_b64:encode(indices),material:{
                    color:mat.color.toArray(),roughness:mat.roughness??.5,metalness:mat.metalness??0,opacity:mat.userData.base??mat.opacity}});
            });
            return parts;
        },
        focus(ids,isolated=false) {
            focused = ids.filter(id => meshes.has(id));
            for (const [id, mesh] of meshes) {
                const on = !focused.length || focused.includes(id);
                const shell=mesh.userData.shape==='engine_cylinder';for(const material of mesh.userData.materials){const base=material.userData.base??1;material.opacity = shell ? .48 : on ? base : base*.58; material.depthWrite = on&&!shell&&base>=1;
                    if(material.emissive&&!material.userData.glow)material.emissive.set(focused.includes(id) ? 0x11182a : 0x000000);}
                mesh.visible = !hidden.has(id)&&(!isolated||on);
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
        setSection(axis,offset){
            if(!['x','y','z','none'].includes(axis)||!Number.isFinite(offset))throw Error('Sección no válida');
            const normal=new THREE.Vector3(axis==='x'?1:0,axis==='y'?1:0,axis==='z'?1:0);
            const plane=new THREE.Plane(normal,offset);renderer.localClippingEnabled=axis!=='none';
            for(const mesh of meshes.values())for(const material of mesh.userData.materials)material.clippingPlanes=axis==='none'?[]:[plane];
            schedule();
        },
        update(next){
            if(disposed)return;
            for(const id of [...guide.motions.keys()])stopMotion(id);  // meshes may be rebuilt: motions restart from the new rest pose
            for(const key of Object.keys(animations)){cancelAnimationFrame(animations[key]);delete animations[key];}
            const ids=new Set(next.objects.map(o=>o.id));
            for(const [id,mesh] of meshes)if(!ids.has(id)){releaseObject(mesh);meshes.delete(id);hidden.delete(id);separated.delete(id);}
            const nextExplode=explodeVectors(next.objects);
            for(const o of next.objects){
                let mesh=meshes.get(o.id);
                if(!mesh||mesh.userData.shape!==o.shape||mesh.userData.size!==sceneSignature(o)){
                    if(mesh)releaseObject(mesh);
                    let glb=glbRoots.get(o.assetId);
                    if(glb&&o.normalizeGlb){glb=glb.clone(true);const box=new THREE.Box3().setFromObject(glb),extent=box.getSize(new THREE.Vector3());
                        const scale=2/Math.max(extent.x,extent.y,extent.z,1e-6),center=box.getCenter(new THREE.Vector3());
                        glb.scale.multiplyScalar(scale);glb.position.addScaledVector(center,-scale);glb.updateMatrixWorld(true);}
                    mesh=objectMesh(o,nextExplode.get(o.id),glb);meshes.set(o.id,mesh);world.add(mesh);
                }
                mesh.userData.base.fromArray(o.position);mesh.userData.explode.fromArray(o.explode||nextExplode.get(o.id)||[0,1.5,0]);
                mesh.position.copy(goal(mesh));mesh.rotation.set(...(o.rotation||[0,0,0]).map(THREE.MathUtils.degToRad));
                if(o.assetId)mesh.scale.fromArray(o.scale||[1,1,1]);
                for(const material of mesh.userData.materials){if(o.color&&!o.preserveColor&&material.color)material.color.set(o.color);
                    if(o.assetId&&o.material&&MATERIALS[o.material]){material.roughness=MATERIALS[o.material].r;material.metalness=MATERIALS[o.material].m;}}
                mesh.visible=!hidden.has(o.id);
            }
            for(const arrow of arrows)if(arrow){arrow.removeFromParent();arrow.dispose();}arrows.length=0;scene=next;setHover(null);
            for(const a of scene.arrows||[]){
                const from=meshes.get(a.from).position,direction=meshes.get(a.to).position.clone().sub(from),length=direction.length();
                if(length<1e-6){arrows.push(null);continue;}
                const arrow=new THREE.ArrowHelper(direction.normalize(),from,length,0x9274ff,Math.min(.4,length*.25),Math.min(.2,length*.12));
                arrow.visible=!exploded&&!hidden.has(a.from)&&!hidden.has(a.to)&&!separated.has(a.from)&&!separated.has(a.to);world.add(arrow);arrows.push(arrow);
            }
            bounds.makeEmpty();meshes.forEach(m=>bounds.expandByObject(m));bounds.getCenter(center);radius=Math.max(.5,bounds.getSize(new THREE.Vector3()).length()/2);syncLabels();schedule();
            const usedAssets=new Set(next.objects.map(o=>o.assetId));for(const [id,root] of glbRoots)if(!usedAssets.has(id)){
                releaseGlb(root);glbBytes-=glbMetadata.get(id).size_bytes;glbTexturePixels-=glbMetadata.get(id).texture_pixels;glbMetadata.delete(id);glbRoots.delete(id);}
        },
        qa(){render();return {objects:meshes.size,triangles:renderer.info.render.triangles,webgl:!renderer.getContext().isContextLost(),finite:[...camera.position.toArray(),...view.target.toArray()].every(Number.isFinite)};},
        snapshot(options={}) {
            render();if(!options.maxWidth)return canvas.toDataURL('image/png');
            const scale=Math.min(1,options.maxWidth/canvas.width,(options.maxHeight||1080)/canvas.height),out=document.createElement('canvas');
            out.width=Math.max(2,Math.floor(canvas.width*scale/2)*2);out.height=Math.max(2,Math.floor(canvas.height*scale/2)*2);
            out.getContext('2d').drawImage(canvas,0,0,out.width,out.height);return out.toDataURL('image/png');
        },
        getView() { return {target: view.target.toArray(), theta: view.theta, phi: view.phi, distance: view.distance}; },
        getSeparated(){return [...separated];},
        dispose() {
            if (disposed) return;
            disposed = true; live--; abort.abort(); observer.disconnect(); cancelAnimationFrame(frame);
            Object.values(animations).forEach(cancelAnimationFrame);cancelAnimationFrame(motionFrame);guide.motions.clear();guide.onFrame=null;guideLayer.remove();
            cancelAnimationFrame(hoverFrame);meshes.forEach(releaseObject);glbRoots.forEach(releaseGlb);glbRoots.clear();arrows.forEach(a=>a?.dispose());environment.dispose();renderer.dispose(); renderer.forceContextLoss(); canvas.remove();annotations.remove();tooltip.remove();
        },
    };
}
