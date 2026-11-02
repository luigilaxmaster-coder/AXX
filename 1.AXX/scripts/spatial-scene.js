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

export function mountScene(container, scene, {reducedMotion = false, onPick = () => {}, onLost = () => {}} = {}) {
    const canvas = document.createElement('canvas');
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true}); // Throws when WebGL is unavailable.
    canvas.className = 'mp-scene-canvas'; canvas.tabIndex = 0; canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Escena 3D conceptual. Arrastra o usa las flechas para girar; rueda, + o − para acercar.');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    container.append(canvas); live++;

    const world = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, .1, 200), disposables = [], meshes = new Map(), arrows = [];
    world.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(5, 8, 6); world.add(sun);
    for (const o of scene.objects) {
        const material = new THREE.MeshStandardMaterial({color: o.color, roughness: .55, metalness: .15, transparent: true});
        const mesh = new THREE.Mesh(geometry(o.shape, o.size), material);
        mesh.position.fromArray(o.position);
        if (o.rotation) mesh.rotation.set(...o.rotation.map(THREE.MathUtils.degToRad));
        mesh.userData = {id: o.id, base: mesh.position.clone(), explode: new THREE.Vector3(...(o.explode || [0, 0, 0]))};
        meshes.set(o.id, mesh); world.add(mesh); disposables.push(mesh.geometry, material);
    }
    for (const a of scene.arrows || []) {
        const from = meshes.get(a.from).position, direction = meshes.get(a.to).position.clone().sub(from), length = direction.length();
        if (length < 1e-6) continue;
        const arrow = new THREE.ArrowHelper(direction.normalize(), from, length, 0x9274ff, Math.min(.4, length * .25), Math.min(.2, length * .12));
        world.add(arrow); arrows.push(arrow); disposables.push(arrow.line.geometry, arrow.line.material, arrow.cone.geometry, arrow.cone.material);
    }

    const bounds = new THREE.Box3(); meshes.forEach(m => bounds.expandByObject(m));
    const center = bounds.getCenter(new THREE.Vector3()), radius = Math.max(.5, bounds.getSize(new THREE.Vector3()).length() / 2);
    const view = {target: center.clone(), theta: .7, phi: 1.1, distance: radius * 2.8};
    let frame = 0, focused = [], exploded = false, disposed = false;
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
        const width = Math.max(200, container.clientWidth || 300), height = Math.round(width * .62);
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
        if (!click) return;
        const r = canvas.getBoundingClientRect();
        pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
        ray.setFromCamera(pointer, camera);
        const hit = ray.intersectObjects([...meshes.values()])[0];
        if (hit) onPick(hit.object.userData.id);
    }, {signal});
    canvas.addEventListener('wheel', e => { e.preventDefault(); zoom(Math.sign(e.deltaY) * .12); }, {signal, passive: false});
    canvas.addEventListener('keydown', e => {
        const keys = {ArrowLeft: () => rotate(-.15, 0), ArrowRight: () => rotate(.15, 0), ArrowUp: () => rotate(0, -.12), ArrowDown: () => rotate(0, .12),
            '+': () => zoom(-.12), '=': () => zoom(-.12), '-': () => zoom(.12)};
        if (keys[e.key]) { e.preventDefault(); e.stopPropagation(); keys[e.key](); }
    }, {signal});
    canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); onLost(); }, {signal});

    // Targets come from resting/exploded goals, never from positions caught mid-animation.
    const goal = m => m.userData.base.clone().addScaledVector(m.userData.explode, exploded ? 1 : 0);
    const focusCenter = () => {
        if (!focused.length && !exploded) return center.clone();
        const chosen = focused.length ? focused.map(id => meshes.get(id)) : [...meshes.values()];
        return chosen.reduce((sum, m) => sum.add(goal(m)), new THREE.Vector3()).divideScalar(chosen.length);
    };

    return {
        focus(ids) {
            focused = ids.filter(id => meshes.has(id));
            for (const [id, mesh] of meshes) {
                const on = !focused.length || focused.includes(id);
                mesh.material.opacity = on ? 1 : .18; mesh.material.depthWrite = on;
                mesh.material.emissive.set(focused.includes(id) ? 0x3a2a80 : 0x000000);
            }
            moveTarget(focusCenter());
        },
        setExploded(value) {
            exploded = value;
            const starts = new Map([...meshes].map(([id, m]) => [id, m.position.clone()]));
            arrows.forEach(a => { a.visible = !exploded; }); // Arrows join resting positions only.
            tween('explode', k => { for (const [id, m] of meshes) m.position.lerpVectors(starts.get(id), goal(m), k); });
            moveTarget(focusCenter());
        },
        snapshot() { render(); return canvas.toDataURL('image/png'); },
        dispose() {
            if (disposed) return;
            disposed = true; live--; abort.abort(); observer.disconnect(); cancelAnimationFrame(frame);
            Object.values(animations).forEach(cancelAnimationFrame);
            disposables.forEach(d => d.dispose()); renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
        },
    };
}
