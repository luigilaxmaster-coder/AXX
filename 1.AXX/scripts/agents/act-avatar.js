/* Act avatars drawn with AXX's own avatar renderer (SoftwareRenderer: 3D mesh on the CPU, Canvas 2D).
 * One hidden renderer makes cached still portraits; one live renderer animates the Act that is working or being
 * edited. Never one renderer per card, and the global avatar (Axx.app.renderer and its settings) is never touched. */
(function (Axx) {
  'use strict';
  if (!Axx?.SoftwareRenderer || !Axx.FORMS || !Axx.PALETTES || !Axx.MOTION_PROFILES) return;

  // Act materials -> AXX finishes; materials without a finish of their own get a studio tweak.
  const FINISH = {obsidian: 'obsidian', optical_glass: 'opticalglass', iridescent_pearl: 'prism', brushed_titanium: 'obsidian',
    velvet_matte: 'smoke', bioluminescent_gel: 'prism'};
  const MATERIAL_STUDIO = {brushed_titanium: {roughness: .3, exposure: 1.12}, velvet_matte: {roughness: .42, exposure: .92},
    bioluminescent_gel: {roughness: .03, exposure: 1.45}};
  const MATERIAL_LABEL = {obsidian: 'Obsidiana', optical_glass: 'Cristal óptico', iridescent_pearl: 'Perla iridiscente',
    brushed_titanium: 'Titanio cepillado', velvet_matte: 'Terciopelo mate', bioluminescent_gel: 'Gel bioluminiscente'};
  const GESTURES = {ripple: 'Onda', nod: 'Asentir', sway: 'Balanceo', stretch: 'Estirar', orbit: 'Órbita', gather: 'Recoger'};
  // Act/run states -> AXX motion states (keys of Axx.MOTION_PROFILES) and the reaction slot each one uses.
  const MOTION = {idle: 'idle', planning: 'thinking', thinking: 'thinking', working: 'processing', awaiting_approval: 'approval',
    paused: 'paused', blocked: 'error', completed: 'success', failed: 'error', disabled: 'offline', speaking: 'speaking'};
  const REACTION = {planning: 'thinking', thinking: 'thinking', working: 'working', awaiting_approval: 'approval',
    completed: 'completed', failed: 'error', blocked: 'error'};
  const tick = cb => (document.hidden ? setTimeout(cb, 0) : requestAnimationFrame(cb));
  const userSettings = () => ({...Axx.DEFAULT_SETTINGS, ...(Axx.app?.store?.data?.settings || {})});
  const reduced = look => !!look?.reduce_motion || !!userSettings().reducedMotion || !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const int = (v, max) => Math.min(max, Math.max(0, Number.parseInt(v, 10) || 0));

  function normal(look = {}) {
    return {form_id: int(look.form_id, Axx.FORMS.length - 1), palette_id: int(look.palette_id, Axx.PALETTES.length - 1),
      material_preset: FINISH[look.material_preset] ? look.material_preset : 'obsidian', studio: look.studio || {},
      scale: Number(look.scale) || 1, animation_intensity: look.animation_intensity, reactions: look.reactions || {},
      reduce_motion: !!look.reduce_motion};
  }
  // zoom frames the form for its box: portraits and small presence boxes need it larger than the main avatar does.
  function settingsFor(look, still, zoom = 1) {
    return {...userSettings(), form: look.form_id, palette: look.palette_id, keepForm: true, actionMorph: false,
      scale: zoom * Math.min(1.3, Math.max(.6, look.scale)), reducedMotion: still || reduced(look), staticMode: !!still};
  }
  function studioFor(look) {
    const s = look.studio, out = {...MATERIAL_STUDIO[look.material_preset], living: true, autoRotate: false};
    if (Number.isFinite(s.exposure)) out.exposure = s.exposure;
    if (Number.isFinite(s.roughness)) out.roughness = s.roughness;
    if (Number.isFinite(s.light_angle)) out.lightAngle = s.light_angle * Math.PI / 180;
    if (Number.isFinite(s.fluidity)) out.fluidity = s.fluidity;
    if (Number.isFinite(look.animation_intensity)) out.intensity = .2 + Math.min(2, Math.max(0, look.animation_intensity)) * .75;
    return out;
  }
  function apply(r, look, still, zoom) {
    r.configure(settingsFor(look, still, zoom)); r.setFinish(FINISH[look.material_preset]); r.setStudio(studioFor(look));
    r.setForm(look.form_id, true); r.resetCamera();
  }
  function makeRenderer(canvas, look, still) {
    const mode = document.body.dataset.renderMode;  // the constructor writes the global render mode; keep the app's value
    const r = new Axx.SoftwareRenderer(canvas, settingsFor(look, still));
    if (mode === undefined) delete document.body.dataset.renderMode; else document.body.dataset.renderMode = mode;
    r.onError = () => {};
    return r;
  }
  const keyOf = (look, size) => [look.form_id, look.palette_id, look.material_preset, JSON.stringify(look.studio), look.scale, size].join('|');

  // ---- Still portraits: one hidden renderer, sequential queue, cached PNG per look and size ----
  const cache = new Map();
  let shot = null, queue = Promise.resolve();
  function portrait(rawLook, size = 128) {
    const look = normal(rawLook), key = keyOf(look, size);
    if (!cache.has(key)) {
      const job = queue.then(() => new Promise(resolve => tick(() => {
        try {
          if (!shot || shot.size !== size) {
            shot?.stage.remove();
            const stage = Object.assign(document.createElement('div'), {className: 'axx-act-avatar-stage'});
            stage.setAttribute('aria-hidden', 'true');
            stage.style.cssText = `position:fixed;left:${-4 * size}px;top:0;width:${size}px;height:${size}px;pointer-events:none;opacity:0;contain:strict`;
            const canvas = document.createElement('canvas'); canvas.style.cssText = 'width:100%;height:100%;display:block';
            stage.append(canvas); document.body.append(stage);
            shot = {size, stage, renderer: makeRenderer(canvas, look, true)};
          }
          const r = shot.renderer; apply(r, look, true, 1.7); r.resize(); r.draw(0);
          resolve(r.canvas.toDataURL('image/png'));
        } catch { resolve(null); }  // renderer unavailable: callers keep their SVG fallback
      })));
      queue = job; cache.set(key, job);
      if (cache.size > 400) cache.delete(cache.keys().next().value);
    }
    return cache.get(key);
  }
  // Fill an <img> with the real portrait; the existing src (SVG fallback) stays if rendering is unavailable.
  function paint(img, look, size) {
    const token = keyOf(normal(look), size); img.dataset.avatarKey = token;
    void portrait(look, size).then(url => { if (url && img.dataset.avatarKey === token) { img.src = url; img.dataset.real = 'true'; } });
    return img;
  }

  // ---- Live: a single animated renderer that moves to whichever host shows the working/edited Act ----
  const live = {renderer: null, canvas: null, host: null, key: '', look: null};
  // A panel can hide its connected subtree without removing the canvas. Stop
  // rendering while hidden, retaining the host/state so reopening resumes it.
  const visibilityObserver = new MutationObserver(syncVisibility);
  function observeVisibility() {
    visibilityObserver.disconnect();
    for (let node = live.host; node; node = node.parentElement)
      visibilityObserver.observe(node, {attributes: true, attributeFilter: ['hidden', 'class', 'style'], childList: true});
  }
  function syncVisibility() {
    const r = live.renderer;
    if (!r || !live.host) return;
    if (!live.canvas.isConnected) { hide(); return; }
    const visible = !document.hidden && live.canvas.getClientRects().length > 0
      && getComputedStyle(live.canvas).visibility !== 'hidden';
    if (!visible) { r.stop(); r.hidden = true; }
    else if (r.hidden || !r.frameHandle) { r.setHidden(false); r.startLoop(); }
  }
  document.addEventListener('visibilitychange', syncVisibility);
  function show(host, rawLook, state = 'working', zoom = 1) {
    if (!host) return;
    const look = normal(rawLook), key = keyOf(look, zoom);
    if (!live.canvas) {
      live.canvas = Object.assign(document.createElement('canvas'), {className: 'axx-act-live'});
      live.canvas.setAttribute('role', 'img');
    }
    if (live.canvas.parentElement !== host) host.append(live.canvas);
    live.host = host;
    if (!live.renderer) {
      live.renderer = makeRenderer(live.canvas, look, false);
      live.renderer.onFrame = syncVisibility;
    }
    if (live.key !== key) { apply(live.renderer, look, false, zoom); live.key = key; }
    live.look = look;
    live.canvas.setAttribute('aria-label', Axx.FORMS[look.form_id].name + ' · ' + Axx.PALETTES[look.palette_id].name);
    setState(state); observeVisibility(); syncVisibility();
  }
  function setState(state) {
    const r = live.renderer; if (!r) return;
    r.setState(MOTION[state] || 'processing', state === 'working' ? .85 : .45);
    const gesture = live.look?.reactions?.[REACTION[state]];
    if (GESTURES[gesture]) r.performGesture20(gesture);
  }
  function hide(host) {
    if (!live.renderer || (host && live.host !== host)) return;
    visibilityObserver.disconnect();
    live.renderer.stop(); live.canvas.remove(); live.host = null; live.renderer.hidden = true;
  }
  // Drag to turn the live preview, like the main avatar.
  function rotatable(host) {
    let last = null;
    host.addEventListener('pointerdown', e => { if (live.host !== host) return; last = [e.clientX, e.clientY]; host.setPointerCapture(e.pointerId); });
    host.addEventListener('pointermove', e => { if (!last || live.host !== host) return;
      live.renderer.rotate((e.clientX - last[0]) * .012, (e.clientY - last[1]) * .012); last = [e.clientX, e.clientY]; });
    host.addEventListener('pointerup', () => { last = null; });
    return host;
  }

  Axx.actAvatar = {portrait, paint, show, hide, setState, rotatable, normal, FINISH, MATERIAL_LABEL, GESTURES, MOTION,
    get liveHost() { return live.host; }};
})(window.Axx);
