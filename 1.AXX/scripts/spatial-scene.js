// Spatial scene runtime for backend-validated ScenePlan data (backend/presentation_plan.py).
// Loaded on demand by Magic Pen. It renders only after a change, so it never runs a
// continuous loop next to the avatar, and dispose() releases every GPU resource.
import * as THREE from './three.module.min.js';

let live = 0;
export const liveScenes = () => live;

function geometry(shape, [x, y, z]) {
    switch (shape) {
        case 'box': return new THREE.BoxGeometry(x, y, z);
        case 'sphere': return new THREE.SphereGeometry(x / 2, 32, 16);
        case 'cylinder': return new THREE.CylinderGeometry(x / 2, x / 2, y, 32);
        case 'cone': return new THREE.ConeGeometry(x / 2, y, 32);
        case 'torus': return new THREE.TorusGeometry(x / 2, Math.max(.02, Math.min(x / 4, y / 2)), 16, 48);
        default: return new THREE.BoxGeometry(x, .02, z); // plane: a thin box shows both faces
    }
}

function objectMesh(o) {
    const [x,y,z]=o.size, engineered=['piston','connecting_rod','crankshaft','engine_cylinder'].includes(o.shape);
    const material=new THREE.MeshStandardMaterial({color:o.color,roughness:engineered?.32:.55,metalness:engineered?.62:.15,transparent:true,side:o.shape==='engine_cylinder'?THREE.DoubleSide:THREE.FrontSide}), geometries=[];
    const part=(root,g,position=[0,0,0],rotation=[0,0,0])=>{const m=new THREE.Mesh(g,material);m.position.fromArray(position);m.rotation.set(...rotation);m.userData.id=o.id;root.add(m);geometries.push(g);};
    let root;
    if(['piston','connecting_rod','crankshaft','engine_cylinder'].includes(o.shape)){
        root=new THREE.Group();
        if(o.shape==='piston'){
            part(root,new THREE.CylinderGeometry(x*.46,x*.48,y*.82,48));
            part(root,new THREE.CylinderGeometry(x*.43,x*.46,y*.12,48),[0,y*.43,0]);
            for(const offset of [.12,.24,.34])part(root,new THREE.TorusGeometry(x*.465,Math.max(.012,y*.025),8,48),[0,y*offset,0],[Math.PI/2,0,0]);
            part(root,new THREE.CylinderGeometry(x*.14,x*.14,z*1.04,24),[0,-y*.13,0],[Math.PI/2,0,0]);
        }else if(o.shape==='connecting_rod'){
            part(root,new THREE.BoxGeometry(x*.52,y*.78,z*.52));
            for(const offset of [-.42,.42]){
                for(const face of [-.22,.22])part(root,new THREE.TorusGeometry(x*.38,x*.11,10,32),[0,y*offset,z*face]);
            }
        }else if(o.shape==='crankshaft'){
            part(root,new THREE.CylinderGeometry(z*.24,z*.24,x,32),[0,0,0],[0,0,Math.PI/2]);
            for(const offset of [-.22,.22])part(root,new THREE.CylinderGeometry(y*.56,y*.56,x*.13,32),[x*offset,0,0],[0,0,Math.PI/2]);
            for(const offset of [-.44,.44])part(root,new THREE.CylinderGeometry(z*.36,z*.36,x*.1,32),[x*offset,0,0],[0,0,Math.PI/2]);
            part(root,new THREE.CylinderGeometry(z*.22,z*.22,x*.46,32),[0,y*.5,0],[0,0,Math.PI/2]);
        }else{
            // The open side exposes the conceptual internal parts without claiming a physical cutaway.
            part(root,new THREE.CylinderGeometry(x/2,x/2,y,48,1,true,Math.PI*.15,Math.PI*1.4));
            for(const offset of [-.48,-.32,-.16,.16,.32,.48])part(root,new THREE.TorusGeometry(x*.52,x*.035,8,48,Math.PI*1.4),[0,y*offset,0],[Math.PI/2,0,Math.PI*.15]);
        }
    }else{
        root=new THREE.Mesh(geometry(o.shape,o.size),material);geometries.push(root.geometry);
    }
    root.position.fromArray(o.position);if(o.rotation)root.rotation.set(...o.rotation.map(THREE.MathUtils.degToRad));
    root.userData={id:o.id,base:root.position.clone(),explode:new THREE.Vector3(...(o.explode||[0,1.5,0])),material,geometries,shape:o.shape,size:JSON.stringify(o.size)};
    return root;
}

function releaseObject(mesh){for(const g of mesh.userData.geometries)g.dispose();mesh.userData.material.dispose();mesh.removeFromParent();}

export function mountScene(container, scene, {reducedMotion = false, onPick = () => {}, onLost = () => {}, onChange = () => {}, initialView = null} = {}) {
    const canvas = document.createElement('canvas');
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true}); // Throws when WebGL is unavailable.
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.3;
    canvas.className = 'mp-scene-canvas'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Escena 3D conceptual. Arrastra o usa las flechas para girar; rueda, + o − para acercar.');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    container.append(canvas); live++;

    const world = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, .1, 200), meshes = new Map(), arrows = [];
    world.add(new THREE.HemisphereLight(0xffffff, 0x344861, 1.2));
    const sun = new THREE.DirectionalLight(0xffffff, 2.0); sun.position.set(5, 8, 6); world.add(sun);
    const rim = new THREE.DirectionalLight(0xa9bbff, 1.1); rim.position.set(-5, 3, -4); world.add(rim);
    for (const o of scene.objects) {
        const mesh=objectMesh(o);meshes.set(o.id,mesh);world.add(mesh);
    }
    for (const a of scene.arrows || []) {
        const from = meshes.get(a.from).position, direction = meshes.get(a.to).position.clone().sub(from), length = direction.length();
        if (length < 1e-6) { arrows.push(null); continue; }
        const arrow = new THREE.ArrowHelper(direction.normalize(), from, length, 0x9274ff, Math.min(.4, length * .25), Math.min(.2, length * .12));
        world.add(arrow); arrows.push(arrow);
    }

    const bounds = new THREE.Box3(); meshes.forEach(m => bounds.expandByObject(m));
    const center = bounds.getCenter(new THREE.Vector3());let radius = Math.max(.5, bounds.getSize(new THREE.Vector3()).length() / 2);
    const view = {target: center.clone(), theta: .7, phi: 1.1, distance: radius * 2.8};
    if (initialView && Array.isArray(initialView.target) && initialView.target.length === 3
        && [...initialView.target, initialView.theta, initialView.phi, initialView.distance].every(Number.isFinite)
        && initialView.distance > 0) {
        view.target.fromArray(initialView.target); view.theta = initialView.theta;
        view.phi = Math.min(Math.PI - .15, Math.max(.15, initialView.phi));
        view.distance = Math.min(radius * 8, Math.max(radius * .8, initialView.distance));
    }
    let frame = 0, focused = [], exploded = false, disposed = false;
    const hidden = new Set(), separated = new Set();
    const animations = {};
    const render = () => {
        if (disposed) return;
        const {target, theta, phi, distance} = view;
        camera.position.set(target.x + distance * Math.sin(phi) * Math.sin(theta), target.y + distance * Math.cos(phi), target.z + distance * Math.sin(phi) * Math.cos(theta));
        camera.lookAt(target); renderer.render(world, camera);
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
        const width = Math.max(200, container.clientWidth || 300), height = Math.round(width * .76);
        renderer.setSize(width, height, false); canvas.style.width = '100%'; canvas.style.height = height + 'px';
        camera.aspect = width / height; camera.updateProjectionMatrix(); schedule();
    };
    const observer = new ResizeObserver(resize); observer.observe(container); resize();

    const abort = new AbortController(), signal = abort.signal;
    const rotate = (dt, dp) => { view.theta += dt; view.phi = Math.min(Math.PI - .15, Math.max(.15, view.phi + dp)); schedule(); };
    const zoom = f => { view.distance = Math.min(radius * 8, Math.max(radius * .8, view.distance * (1 + f))); schedule(); };
    const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
    let drag = null;
    canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, moved: 0}; canvas.setPointerCapture?.(e.pointerId); }, {signal});
    canvas.addEventListener('pointermove', e => {
        if (!drag) return;
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved += Math.abs(dx) + Math.abs(dy); drag.x = e.clientX; drag.y = e.clientY;
        rotate(-dx * .01, -dy * .01);
    }, {signal});
    canvas.addEventListener('pointerup', e => {
        const click = drag && drag.moved < 5; drag = null;
        onChange();
        if (!click) return;
        const r = canvas.getBoundingClientRect();
        pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
        ray.setFromCamera(pointer, camera);
        const hit = ray.intersectObjects([...meshes.values()],true)[0];
        if (hit) onPick(hit.object.userData.id);
    }, {signal});
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
    const focusCenter = () => {
        if (!focused.length && !exploded) return center.clone();
        const chosen = focused.length ? focused.map(id => meshes.get(id)) : [...meshes.values()];
        return chosen.reduce((sum, m) => sum.add(goal(m)), new THREE.Vector3()).divideScalar(chosen.length);
    };

    return {
        focus(ids,isolated=false) {
            focused = ids.filter(id => meshes.has(id));
            for (const [id, mesh] of meshes) {
                const on = !focused.length || focused.includes(id);
                const material=mesh.userData.material;material.opacity = on ? 1 : .18; material.depthWrite = on; mesh.visible = !hidden.has(id)&&(!isolated||on);
                material.emissive.set(focused.includes(id) ? 0x3a2a80 : 0x000000);
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
            for(const o of next.objects){
                let mesh=meshes.get(o.id);
                if(!mesh||mesh.userData.shape!==o.shape||mesh.userData.size!==JSON.stringify(o.size)){
                    if(mesh)releaseObject(mesh);mesh=objectMesh(o);meshes.set(o.id,mesh);world.add(mesh);
                }
                mesh.userData.base.fromArray(o.position);mesh.userData.explode.fromArray(o.explode||[0,1.5,0]);
                mesh.position.copy(goal(mesh));mesh.rotation.set(...(o.rotation||[0,0,0]).map(THREE.MathUtils.degToRad));
                mesh.userData.material.color.set(o.color);mesh.visible=!hidden.has(o.id);
            }
            for(const arrow of arrows)if(arrow){arrow.removeFromParent();arrow.dispose();}arrows.length=0;scene=next;
            for(const a of scene.arrows||[]){
                const from=meshes.get(a.from).position,direction=meshes.get(a.to).position.clone().sub(from),length=direction.length();
                if(length<1e-6){arrows.push(null);continue;}
                const arrow=new THREE.ArrowHelper(direction.normalize(),from,length,0x9274ff,Math.min(.4,length*.25),Math.min(.2,length*.12));
                arrow.visible=!exploded&&!hidden.has(a.from)&&!hidden.has(a.to)&&!separated.has(a.from)&&!separated.has(a.to);world.add(arrow);arrows.push(arrow);
            }
            bounds.makeEmpty();meshes.forEach(m=>bounds.expandByObject(m));bounds.getCenter(center);radius=Math.max(.5,bounds.getSize(new THREE.Vector3()).length()/2);schedule();
        },
        qa(){render();return {objects:meshes.size,triangles:renderer.info.render.triangles,webgl:!renderer.getContext().isContextLost(),finite:[...camera.position.toArray(),...view.target.toArray()].every(Number.isFinite)};},
        snapshot() { render(); return canvas.toDataURL('image/png'); },
        getView() { return {target: view.target.toArray(), theta: view.theta, phi: view.phi, distance: view.distance}; },
        getSeparated(){return [...separated];},
        dispose() {
            if (disposed) return;
            disposed = true; live--; abort.abort(); observer.disconnect(); cancelAnimationFrame(frame);
            Object.values(animations).forEach(cancelAnimationFrame);
            meshes.forEach(releaseObject);arrows.forEach(a=>a?.dispose());renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
        },
    };
}
