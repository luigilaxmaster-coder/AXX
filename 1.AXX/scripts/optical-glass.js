/* AXX Optical Glass: optional finish for native AXX. No geometry or actions replaced. */
(() => {
  'use strict';
  const A = window.Axx;
  if (!A?.SoftwareRenderer || A.PALETTES?.length !== 9) return;
  const proto = A.SoftwareRenderer.prototype;
  if (proto.__axxOpticalGlass) return;
  const original = proto.shadeTable, KEY = 'axx-optical-glass-v1';

  const PRESETS = {
    reference: { transmission: .91, ior: 1.48, thickness: .76, roughness: .045, iridescence: .63, rim: .96, saturation: .72, exposure: 1.21, envBoost: 1.08, aurora: 1.00, mode: 'glass' },
    crystal:   { transmission: .83, ior: 1.64, thickness: .87, roughness: .023, iridescence: .43, rim: 1.00, saturation: .45, exposure: 1.23, envBoost: 1.20, aurora: .17,  mode: 'crystal' },
    liquid:    { transmission: .60, ior: 1.39, thickness: .68, roughness: .18,  iridescence: .43, rim: .57, saturation: .56, exposure: .96,  envBoost: 1.08, aurora: 1.00, mode: 'glass' },
    silica:    { transmission: .96, ior: 1.46, thickness: .60, roughness: .026, iridescence: .12, rim: .94, saturation: .10, exposure: 1.21, envBoost: 1.20, aurora: .17,  mode: 'glass' },
    aura:      { transmission: .82, ior: 1.52, thickness: .62, roughness: .056, iridescence: 1.0, rim: .91, saturation: 1.0, exposure: 1.18, envBoost: 1.04, aurora: 1.28, mode: 'aura' }
  };

  const DEFAULT = { ...PRESETS.reference };
  const R = {
    transmission: [0, 1],
    ior: [1.01, 1.85],
    thickness: [0, 1],
    roughness: [.015, .48],
    iridescence: [0, 1],
    rim: [0, 1],
    saturation: [0, 1],
    exposure: [.48, 2.1],
    envBoost: [0, 2],
    aurora: [0, 2]
  };

  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const decode = h => [1, 3, 5].map(i => Math.pow(parseInt(h.slice(i, i + 2), 16) / 255, 2.2));

  const invAces = y => {
    if (y <= 0) return 0;
    if (y >= .999) return 10;
    const a = 2.51 - 2.43 * y, b = .03 - .59 * y, c = -.14 * y;
    const disc = b * b - 4 * a * c;
    return (-b + Math.sqrt(Math.max(0, disc))) / (2 * a);
  };

  let p = { ...DEFAULT }, color = '', revision = 0, panel = null, inputs = new Map();

  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (saved && typeof saved === 'object') {
      for (const [k, [a, b]] of Object.entries(R)) {
        if (typeof saved[k] === 'number' && Number.isFinite(saved[k])) p[k] = clamp(saved[k], a, b);
      }
      if (['glass', 'crystal', 'aura'].includes(saved.mode)) p.mode = saved.mode;
      if (/^#[0-9a-fA-F]{6}$/i.test(saved.color || '')) color = saved.color;
    }
  } catch (e) {
    console.warn('[AXX Optical Glass] Settings read skipped', e);
  }

  const invalidate = () => {
    revision++;
    const renderer = A.app?.renderer;
    if (renderer) {
      renderer.lutKey = '';
      renderer.lastDrawnSignature = '';
    }
  };

  const save = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...p, color }));
    } catch (e) {
      console.warn('[AXX Optical Glass] Settings save skipped', e);
    }
  };

  const set = (patch, persist = true) => {
    if (!patch || typeof patch !== 'object') return;
    if (typeof patch.preset === 'string' && PRESETS[patch.preset]) {
      patch = { ...PRESETS[patch.preset], ...patch };
    }
    for (const [k, [a, b]] of Object.entries(R)) {
      if (Object.hasOwn(patch, k) && typeof patch[k] === 'number' && Number.isFinite(patch[k])) p[k] = clamp(patch[k], a, b);
    }
    if (['glass', 'crystal', 'aura'].includes(patch.mode)) p.mode = patch.mode;
    if (Object.hasOwn(patch, 'color')) color = /^#[0-9a-fA-F]{6}$/i.test(patch.color || '') ? patch.color : '';
    if (persist) save();
    invalidate();
    sync();
  };

  const preview = patch => {
    A.experience.beginPreview();
    set(patch, false);
    A.experience.previewStatus();
  };

  proto.shadeTable = function opticalGlassShadeTable() {
    if (this.finish !== 'opticalglass') return original.call(this);
    const signature = [
      this.settings.palette,
      this.studio.roughness,
      this.studio.exposure,
      this.studio.lightAngle,
      this.state,
      this.settings.keepForm,
      revision
    ].join('/');

    if (this.__opticalGlassSignature === signature && this.lutKey === 'opticalglass/' + signature) return;

    // Use original obsidian chrome pass to generate studio reflection card data
    this.finish = 'obsidian';
    this.lutKey = '';
    try {
      original.call(this);
    } finally {
      this.finish = 'opticalglass';
    }

    const lut = this.lut;
    const colors = A.PALETTES[this.settings.palette].colors;
    const palette = colors.map(decode);
    const tintV = /^#[0-9a-fA-F]{6}$/.test(color)
      ? [parseInt(color.slice(1, 3), 16) / 255, parseInt(color.slice(3, 5), 16) / 255, parseInt(color.slice(5, 7), 16) / 255]
      : null;

    const highlightPower = 9 + 30 * (1 - p.roughness / .48);
    const iorRatio = (p.ior - 1) / (p.ior + 1);
    const f0 = iorRatio * iorRatio;
    const envBoost = p.envBoost;
    const aurora = p.aurora;
    const mode = p.mode || 'glass';
    const lightResponse = this.settings.keepForm ? 1 : A.MOTION_PROFILES[this.state].lightResponse;

    for (let j = 0; j < 512; j++) {
      for (let i = 0; i < 512; i++) {
        const o = (j * 512 + i) * 4;
        const nx = i / 511 * 2 - 1, ny = j / 511 * 2 - 1;
        const nz = Math.sqrt(Math.max(.000001, 1 - nx * nx - ny * ny));
        const grazing = clamp(1 - nz, 0, 1);
        const edge = Math.pow(grazing, 1.32);
        const fresnel = f0 + (1 - f0) * Math.pow(grazing, 5);

        const whiteWide = Math.pow(Math.max(0, .45 + ny * .59 - nx * .16), 4.8);
        const upperBox = Math.pow(Math.max(0, .29 + ny * .76 + nz * .28 - nx * .18), highlightPower * .31);
        const sideBox = Math.pow(Math.max(0, .25 - nx * .80 + ny * .14 + nz * .12), highlightPower * .22);
        const glint = Math.pow(Math.max(0, .17 + ny * .72 - nx * .25 + nz * .27), highlightPower * .76);
        const bottomBox = Math.pow(Math.max(0, -ny * .84 + nx * .11 + .13), 4.3);

        const phase = Math.atan2(ny, nx) * 2.7 + nx * 4.2 - ny * 3.1 + this.studio.lightAngle * .50;
        const opticalPhase = phase + (1 - nz) * 7.5 * (.25 + p.ior * .30);

        const whiteCoat = (upperBox * .43 + whiteWide * .15 + sideBox * .31 + glint * .84 + bottomBox * .18) * (.46 + .55 * p.rim) * (1 - p.roughness * .57);
        const neutralRim = (.17 + .57 * p.rim) * Math.pow(grazing, .65) * (.80 + .24 * p.thickness);

        for (let k = 0; k < 3; k++) {
          const mapped = Math.pow(lut[o + k] / 255, 2.2);
          const obsVal = invAces(mapped);
          const film = .5 + .5 * Math.cos([0, 2.094395, 4.18879][k] + (1 - nz) * 10.7);
          const obsidianTint = .72 + (.16 + .20 * Math.pow(1 - nz, 5)) * film;
          const baseK = Math.max(0, obsVal / (this.studio.exposure * lightResponse) - .003) / obsidianTint;

          const accent = palette[[0, 1, 2][k]][k];
          const tintR = tintV ? (tintV[k] * tintV[k]) : accent;
          const spectrum = .5 + .5 * Math.cos(opticalPhase * (.68 + .8 * p.iridescence) + [0, -2.094395, 2.094395][k]);
          const iris = spectrum * (.09 + .28 * p.iridescence) * edge * p.iridescence * p.saturation * aurora;

          const reflection = baseK * (.12 + .40 * edge + .14 * fresnel) * envBoost;
          const transmissionBody = (.009 + .065 * tintR + .012 * spectrum) * p.transmission * (1 - .58 * edge) * (.9 + .4 * p.thickness);
          const absorption = Math.exp(-p.thickness * (.23 + .48 * tintR) * (1 + .62 * edge));
          const chroma = iris * (.12 + .58 * tintR + .26 * spectrum);
          const glassBase = (transmissionBody + chroma + reflection * .46) * absorption;
          const clear = glassBase + neutralRim * .34 + whiteCoat * (k === 0 ? .88 : k === 1 ? .92 : 1.04);
          const chromeReflection = baseK * obsidianTint * (.58 + .56 * edge) * (1 - p.roughness * .48);

          let value = chromeReflection + clear * .54 + fresnel * .18 * baseK;
          if (mode === 'crystal') value += Math.pow(Math.abs(Math.sin(phase * 3.6)), 22) * edge * .15;
          if (mode === 'aura') value += spectrum * .18 * edge * p.saturation;

          value *= p.exposure * lightResponse;
          const finalMapped = clamp((value * (2.51 * value + .03)) / (value * (2.43 * value + .59) + .14), 0, 1);
          lut[o + k] = Math.round(255 * Math.pow(finalMapped, 1 / 2.2));
        }

        // Keep alpha fully opaque for native hit-testing, root attachments and morph reach.
        lut[o + 3] = 255;
      }
    }

    this.__opticalGlassSignature = signature;
    this.lutKey = 'opticalglass/' + signature; // Tendrils share and cache this exact LUT.
  };

  Object.defineProperty(proto, '__axxOpticalGlass', { value: true });

  const spec = [
    ['transmission', 'Transmisión óptica', 0, 1, .01],
    ['ior', 'Índice de refracción (IOR)', 1.01, 1.85, .01],
    ['thickness', 'Espesor del cristal', 0, 1, .01],
    ['roughness', 'Rugosidad microscópica', .015, .48, .005],
    ['iridescence', 'Iridescencia', 0, 1, .01],
    ['rim', 'Intensidad del borde', 0, 1, .01],
    ['saturation', 'Saturación', 0, 1, .01],
    ['exposure', 'Exposición HDR', .48, 2.1, .01]
  ];

  function sync() {
    if (!panel) return;
    panel.hidden = A.app?.renderer?.getFinish?.() !== 'opticalglass';
    for (const [k, v] of inputs) {
      if (k === 'color') {
        v.value = color || '#70caff';
        continue;
      }
      v.slider.value = p[k];
      v.output.value = p[k].toFixed(2);
    }
  }

  function mount() {
    const status = document.getElementById('finish-state');
    if (!status || document.getElementById('axx-optical-controls')) return;
    panel = document.createElement('section');
    panel.id = 'axx-optical-controls';
    panel.hidden = true;
    panel.setAttribute('aria-label', 'Ajustes de Optical Glass');
    panel.className = 'p7-body';

    const h = document.createElement('h4');
    h.textContent = 'OPTICAL GLASS · LUZ Y CRISTAL';
    panel.append(h);

    const presetBar = document.createElement('div');
    presetBar.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px';
    for (const [key, label] of [
      ['reference', 'Reference Glass'],
      ['crystal', 'Optical Crystal'],
      ['liquid', 'Liquid Gel'],
      ['silica', 'Pure Silica'],
      ['aura', 'Prismatic Aura']
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.style.cssText = 'font:11px system-ui;min-height:34px;padding:6px 9px;border-radius:9px';
      b.dataset.opticalPreset = key;
      b.onclick = () => preview(PRESETS[key]);
      presetBar.append(b);
    }
    panel.append(presetBar);

    for (const [k, label, min, max, step] of spec) {
      const row = document.createElement('label');
      row.className = 'id20-range';
      const title = document.createElement('span');
      title.textContent = label;
      const output = document.createElement('output');
      const slider = document.createElement('input');
      slider.type = 'range';
      slider.min = min;
      slider.max = max;
      slider.step = step;
      slider.style.cssText = 'width:100%;display:block;margin-top:8px';
      slider.oninput = () => preview({ [k]: Number(slider.value) });
      row.append(title, output, slider);
      panel.append(row);
      inputs.set(k, { slider, output });
    }

    const label = document.createElement('label');
    label.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font:11px system-ui;margin:12px 0';
    label.textContent = 'Color personalizado';
    const picker = document.createElement('input');
    picker.type = 'color';
    picker.value = '#70caff';
    picker.style.cssText = 'width:55px;height:36px';
    picker.setAttribute('aria-label', 'Color personalizado de Optical Glass');
    picker.oninput = () => preview({ color: picker.value });
    label.append(picker);
    panel.append(label);
    inputs.set('color', picker);

    const reset = document.createElement('button');
    reset.type = 'button';
    reset.textContent = 'Colores originales de la paleta';
    reset.onclick = () => preview({ color: '' });
    panel.append(reset);

    status.insertAdjacentElement('afterend', panel);
    for (const b of document.querySelectorAll('.finish-cards [data-finish],#finish-apply,#finish-restore')) {
      b.addEventListener('click', () => queueMicrotask(sync));
    }
    sync();
  }

  mount();
  if (!panel) document.addEventListener('DOMContentLoaded', mount, { once: true });
  window.AxxOpticalGlass = Object.freeze({
    get: () => ({ ...p, color }),
    set,
    save,
    sync,
    setPreset: name => { if (PRESETS[name]) set(PRESETS[name]); },
    presets: Object.keys(PRESETS),
    version: '1.0.0'
  });
})();
