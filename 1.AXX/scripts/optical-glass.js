/* AXX Optical Glass V7: additive studio glass finish for body and OrganicTendrils. */
(() => {
  'use strict';
  const A = window.Axx;
  if (!A?.SoftwareRenderer || A.PALETTES?.length !== 9) return;
  const proto = A.SoftwareRenderer.prototype;
  if (proto.__axxOpticalGlass) return;

  const originalShadeTable = proto.shadeTable;
  const originalDraw = proto.draw;
  const originalResize = proto.resize;
  const originalSetFinish = proto.setFinish;
  const KEY = 'axx-optical-glass-v1';
  const LEGACY_KEY = 'axx_optical_glass_params';

  const PRESETS = {
    reference: { transmission: .91, ior: 1.48, thickness: .76, roughness: .045, iridescence: .63, rim: .96, saturation: .72, exposure: 1.21, envBoost: 1.08, aurora: 1.00, mode: 'glass' },
    crystal:   { transmission: .83, ior: 1.64, thickness: .87, roughness: .023, iridescence: .43, rim: 1.00, saturation: .45, exposure: 1.23, envBoost: 1.20, aurora: .17,  mode: 'crystal' },
    liquid:    { transmission: .60, ior: 1.39, thickness: .68, roughness: .18,  iridescence: .43, rim: .57, saturation: .56, exposure: .96,  envBoost: 1.08, aurora: 1.00, mode: 'glass' },
    silica:    { transmission: .96, ior: 1.46, thickness: .60, roughness: .026, iridescence: .12, rim: .94, saturation: .10, exposure: 1.21, envBoost: 1.20, aurora: .17,  mode: 'glass' },
    aura:      { transmission: .82, ior: 1.52, thickness: .62, roughness: .056, iridescence: 1.0, rim: .91, saturation: 1.0, exposure: 1.18, envBoost: 1.04, aurora: 1.28, mode: 'aura' },
    ethereal:  { transmission: .98, ior: 1.50, thickness: .24, roughness: .020, iridescence: .85, rim: 1.00, saturation: .85, exposure: 1.18, envBoost: 1.20, aurora: 1.00, mode: 'ethereal' }
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

  const gammaTable = new Uint8Array(1024);
  for (let g = 0; g < 1024; g++) {
    gammaTable[g] = Math.round(255 * Math.pow(g / 1023, 1 / 2.2));
  }

  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const norm = v => { const l = Math.hypot(...v) || 1; return v.map(x => x / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const gauss = (v, m, s) => Math.exp(-(((v - m) / s) ** 2));

  let p = { ...DEFAULT };
  let color = '';
  let revision = 0;
  let panel = null;
  const inputs = new Map();

  try {
    const raw = localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'null';
    const saved = JSON.parse(raw);
    if (saved && typeof saved === 'object') {
      for (const [k, [a, b]] of Object.entries(R)) {
        if (typeof saved[k] === 'number' && Number.isFinite(saved[k])) p[k] = clamp(saved[k], a, b);
      }
      if (['glass', 'crystal', 'aura', 'ethereal'].includes(saved.mode)) p.mode = saved.mode;
      if (/^#[0-9a-fA-F]{6}$/i.test(saved.color || '')) color = saved.color;
    }
  } catch (e) {
    console.warn('[AXX Optical Glass] Settings read skipped', e);
  }

  const registeredTendrils = new Set();
  const getTendrilInstances = (renderer = A.app?.renderer) => [
    ...registeredTendrils,
    renderer?.__lastTendrilInstance,
    A.organic?.tendrils,
    A.flow?.delivery,
    A.app?.companion?.experience?.tendrils,
    A.app?.companion?.delivery,
    A.app?.tendrils
  ].filter((v, i, a) => v && a.indexOf(v) === i);

  const invalidate = () => {
    revision++;
    const renderer = A.app?.renderer;
    if (renderer) {
      renderer.lutKey = '';
      renderer.lastDrawnSignature = '';
    }
    for (const t of getTendrilInstances(renderer)) {
      t.buffers?.clear?.();
      t.filteredMaterial = null;
      t.materialKey = null;
    }
    if (renderer?.ctx && typeof renderer.draw === 'function') {
      try { renderer.draw(renderer.lastTime || 0); } catch (_) {}
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
      if (Object.hasOwn(patch, k) && typeof patch[k] === 'number' && Number.isFinite(patch[k])) {
        p[k] = clamp(patch[k], a, b);
      }
    }
    if (['glass', 'crystal', 'aura', 'ethereal'].includes(patch.mode)) p.mode = patch.mode;
    if (Object.hasOwn(patch, 'color')) {
      color = /^#[0-9a-fA-F]{6}$/i.test(patch.color || '') ? patch.color : '';
    }
    if (persist) save();
    invalidate();
    sync();
  };

  const preview = patch => {
    A.experience?.beginPreview?.();
    set(patch, false);
    A.experience?.previewStatus?.();
  };

  function getPaletteAccents(paletteIdx, customColor) {
    const palette = A.PALETTES[paletteIdx] || A.PALETTES[0];
    const fromHex = hex => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
    const cool = fromHex(palette.colors[1]), warm = fromHex(palette.colors[3]), magenta = fromHex(palette.colors[2]);
    const custom = /^#[0-9a-fA-F]{6}$/i.test(customColor || '') ? fromHex(customColor) : null;
    const tintBlend = custom ? 0.72 : 0;
    const blendRGB = col => col.map((v, i) => v * (1 - tintBlend) + (custom ? custom[i] : v) * tintBlend);
    return {
      cool: blendRGB(cool),
      warm: blendRGB(warm),
      magenta: blendRGB(magenta)
    };
  }

  // --- 1. SUPERSAMPLED HD RESIZE FOR OPTICAL GLASS ---
  if (originalResize) {
    proto.resize = function opticalGlassResize() {
      if (this.finish !== 'opticalglass' || !this.canvas || !A.CpuRaster) {
        return originalResize.call(this);
      }
      const r = this.canvas.getBoundingClientRect();
      const qualityCap = this.settings?.quality === 'eco' ? 680 : this.settings?.quality === 'high' ? 1120 : 960;
      const scale = this.settings?.quality === 'eco' ? 1.25 : 1.62;
      const max = this.reaching ? 1320 : qualityCap;
      const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
      const requestedRatio = Math.min(dpr * scale, 2.7);
      const ratio = Math.min(requestedRatio, max * (this.adaptive || 1) / Math.max(r.width, r.height, 1));
      const rawW = Math.max(2, Math.round(r.width * ratio));
      const rawH = Math.max(2, Math.round(r.height * ratio));
      const safety = Math.min(1, 925 / Math.max(rawW, rawH), Math.sqrt(925000 / Math.max(1, rawW * rawH)));
      const w = Math.max(2, Math.floor(rawW * safety));
      const h = Math.max(2, Math.floor(rawH * safety));
      if (!this.raster || this.raster.width !== w * 2 || this.raster.height !== h * 2) {
        this.canvas.width = w;
        this.canvas.height = h;
        this.raster = new A.CpuRaster(w * 2, h * 2);
        this.image = this.ctx?.createImageData(w, h) || null;
        this.glassCoverage = new Uint8Array(w * h);
      }
    };
  }

  if (originalSetFinish) {
    proto.setFinish = function opticalGlassSetFinish(finish) {
      const prev = this.finish;
      originalSetFinish.call(this, finish);
      if (prev !== finish) {
        for (const t of getTendrilInstances(this)) {
          t.buffers?.clear?.();
          t.filteredMaterial = null;
          t.materialKey = null;
        }
        if (typeof this.resize === 'function') {
          try { this.resize(); } catch (_) {}
        }
      }
      sync();
    };
  }

  // --- 2. CPU RASTER PER-NORMAL ALPHA INTERPOLATION ---
  if (A.CpuRaster?.prototype?.triangle) {
    const origTriangle = A.CpuRaster.prototype.triangle;
    A.CpuRaster.prototype.triangle = function opticalGlassTriangle(vertices, ia, ib, ic, lut, view) {
      const alphaLut = this.__opticalAlphaLut;
      if (!alphaLut || view !== 0) {
        return origTriangle.call(this, vertices, ia, ib, ic, lut, view);
      }
      const a = ia * 6, b = ib * 6, c = ic * 6;
      const ax = vertices[a], ay = vertices[a + 1], bx = vertices[b], by = vertices[b + 1], cx = vertices[c], cy = vertices[c + 1];
      const den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (!Number.isFinite(den) || Math.abs(den) < .001) return;
      const left = Math.max(0, Math.floor(Math.min(ax, bx, cx))), right = Math.min(this.width - 1, Math.ceil(Math.max(ax, bx, cx)));
      const top = Math.max(0, Math.floor(Math.min(ay, by, cy))), bottom = Math.min(this.height - 1, Math.ceil(Math.max(ay, by, cy)));
      if (right < left || bottom < top) return;
      const dxA = (by - cy) / den, dyA = (cx - bx) / den, dxB = (cy - ay) / den, dyB = (ax - cx) / den;
      let rowA = ((by - cy) * (left + .5 - cx) + (cx - bx) * (top + .5 - cy)) / den;
      let rowB = ((cy - ay) * (left + .5 - cx) + (ax - cx) * (top + .5 - cy)) / den;
      const az = vertices[a + 2], bz = vertices[b + 2], cz = vertices[c + 2];
      const anx = vertices[a + 3], any = vertices[a + 4], anz = vertices[a + 5];
      const bnx = vertices[b + 3], bny = vertices[b + 4], bnz = vertices[b + 5];
      const cnx = vertices[c + 3], cny = vertices[c + 4], cnz = vertices[c + 5];
      const pix = this.pixels, depth = this.depth, lutSize = Math.round(Math.sqrt(lut.length / 4));
      const maxIdx = lutSize - 1, maxFloor = lutSize - 2, stride4 = lutSize * 4;

      for (let y = top; y <= bottom; y++, rowA += dyA, rowB += dyB) {
        let wa = rowA, wb = rowB;
        const rowOffset = y * this.width;
        for (let x = left; x <= right; x++, wa += dxA, wb += dxB) {
          const wc = 1 - wa - wb;
          if (wa < -.00001 || wb < -.00001 || wc < -.00001) continue;
          const index = rowOffset + x, iz = wa * az + wb * bz + wc * cz;
          if (iz <= depth[index]) continue;
          let nx = wa * anx + wb * bnx + wc * cnx;
          let ny = wa * any + wb * bny + wc * cny;
          let nz = wa * anz + wb * bnz + wc * cnz;
          const length = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
          nx /= length; ny /= length; nz /= length;
          if (nz < 0) { nx = -nx; ny = -ny; nz = -nz; }
          depth[index] = iz;

          const lx = clamp((nx * .5 + .5) * maxIdx, 0, maxIdx);
          const ly = clamp((ny * .5 + .5) * maxIdx, 0, maxIdx);
          const ix = Math.min(maxFloor, lx | 0), iy = Math.min(maxFloor, ly | 0);
          const fx = lx - ix, fy = ly - iy;
          const w00 = (1 - fx) * (1 - fy), w10 = fx * (1 - fy), w01 = (1 - fx) * fy, w11 = fx * fy;

          const ka = iy * lutSize + ix, kb = ka + 1, kc = ka + lutSize, kd = kc + 1;
          const k = ka << 2, kb4 = k + 4, kc4 = k + stride4, kd4 = kc4 + 4;
          const pIdx = index << 2;

          pix[pIdx]     = lut[k]     * w00 + lut[kb4]     * w10 + lut[kc4]     * w01 + lut[kd4]     * w11;
          pix[pIdx + 1] = lut[k + 1] * w00 + lut[kb4 + 1] * w10 + lut[kc4 + 1] * w01 + lut[kd4 + 1] * w11;
          pix[pIdx + 2] = lut[k + 2] * w00 + lut[kb4 + 2] * w10 + lut[kc4 + 2] * w01 + lut[kd4 + 2] * w11;
          pix[pIdx + 3] = alphaLut[ka] * w00 + alphaLut[kb] * w10 + alphaLut[kc] * w01 + alphaLut[kd] * w11;
        }
      }
    };
  }

  // --- 3. SHADE TABLE (Full V7 Optical Glass Studio Illumination + Per-Normal Alpha LUT) ---
  proto.shadeTable = function opticalGlassShadeTable() {
    if (this.finish !== 'opticalglass') {
      this.__opticalAlphaLut = null;
      return originalShadeTable.call(this);
    }

    const palIdx = this.settings?.palette ?? 0;
    const sRough = this.studio?.roughness ?? .035;
    const sExp = this.studio?.exposure ?? 1;
    const sAngle = this.studio?.lightAngle ?? 0;
    const sState = this.state ?? 'idle';
    const sKeep = this.settings?.keepForm ?? true;
    const signature = [palIdx, sRough, sExp, sAngle, sState, sKeep, revision].join('/');

    if (this.__opticalGlassSignature === signature && this.lutKey === 'opticalglass/' + signature && this.__opticalAlphaLut) {
      return;
    }

    const width = 512;
    if (!this.lut || this.lut.length !== width * width * 4) {
      this.lut = new Uint8ClampedArray(width * width * 4);
    }
    if (!this.__opticalAlphaLut || this.__opticalAlphaLut.length !== width * width) {
      this.__opticalAlphaLut = new Uint8ClampedArray(width * width);
    }
    const lut = this.lut;
    const alphaLut = this.__opticalAlphaLut;

    const decodeColor = hex => {
      const n = parseInt(hex.slice(1), 16);
      return [Math.pow(((n >> 16) & 255) / 255, 2.2), Math.pow(((n >> 8) & 255) / 255, 2.2), Math.pow((n & 255) / 255, 2.2)];
    };

    const pal = A.PALETTES[palIdx] || A.PALETTES[0];
    const palette = pal.colors.map(decodeColor);
    const hasCustom = /^#[0-9a-fA-F]{6}$/i.test(color || '');
    if (hasCustom) {
      const user = decodeColor(color);
      const strength = 0.72 * 0.86;
      for (const channel of palette) {
        for (let i = 0; i < 3; i++) channel[i] = channel[i] * (1 - strength) + user[i] * strength;
      }
    }

    const tintV = hasCustom
      ? [parseInt(color.slice(1, 3), 16) / 255, parseInt(color.slice(3, 5), 16) / 255, parseInt(color.slice(5, 7), 16) / 255]
      : null;

    const w = .028 + sRough * .32;
    const cards = [
      { dir: [-.64, .80, .60], size: [.17, .57], feather: w * 2.3, color: [1.35, 1.48, 1.75] },
      { dir: [-.81, .74, .40], size: [.022, .53], feather: w * .62, color: [2.0, 2.12, 2.3] },
      { dir: [.15, .79, 1],    size: [.52, .20], feather: w * 2.0, color: [.012, .019, .034] },
      { dir: [.87, .46, .48],  size: [.055, .67], feather: w * 1.4, color: [1.2, 1.4, 1.65] },
      { dir: [-.25, 1, -.22],  size: [.78, .026], feather: w * .8,  color: [2, 2.16, 2.35] },
      { dir: [-1, -.06, .04],  size: [.25, .81], feather: w * 2.1, color: palette[0].map(n => n * 2.1) },
      { dir: [-.61, -.53, .94], size: [.075, .57], feather: w * 1.2, color: palette[0].map(n => n * .80) },
      { dir: [.66, .16, .76],  size: [.055, .44], feather: w * .85, color: palette[2].map(n => n * .70) },
      { dir: [-.34, -.91, .35], size: [.48, .085], feather: w * 1.3, color: palette[1].map(n => n * .95) },
      { dir: [.77, 0, -.72],   size: [.14, .78], feather: w * 1.4, color: palette[2].map(n => n * 1.8) },
      { dir: [.98, -.20, .43], size: [.045, .67], feather: w * .85, color: palette[3].map(n => n * 1.9) },
      { dir: [-.63, -.37, -.62], size: [.078, .62], feather: w * 1.5, color: [.36, .40, .48] },
      { dir: [.30, -.63, -.72], size: [.56, .075], feather: w,       color: [.26, .33, .46] }
    ].map(card => {
      const d = norm(card.dir);
      const r = norm(cross([0, 1, .02], d));
      const u = cross(d, r);
      return { ...card, dir: d, right: r, up: u };
    });

    const keydir = norm([-.64, .8, .6]);
    const forward = norm([.1, .12, 1]);
    const co = Math.cos(sAngle), si = Math.sin(sAngle);

    const highlightPower = 9 + 30 * (1 - p.roughness / .48);
    const iorRatio = (p.ior - 1) / (p.ior + 1);
    const f0 = iorRatio * iorRatio;
    const envBoost = p.envBoost ?? 1.08;
    const aurora = p.aurora ?? 1.00;
    const mode = p.mode || 'glass';
    const lightResponse = sKeep ? 1 : (A.MOTION_PROFILES?.[sState]?.lightResponse ?? 1);
    const expVal = p.exposure * lightResponse;
    const filmPhase = [0, 2.094395, 4.18879];
    const specPhase = [0, -2.094395, 2.094395];

    for (let j = 0; j < width; j++) {
      const ny = j / 511 * 2 - 1;
      const rowIdx = j * width;

      for (let i = 0; i < width; i++) {
        const nx = i / 511 * 2 - 1;
        const nxy2 = nx * nx + ny * ny;
        const pFlat = rowIdx + i;
        const o = pFlat << 2;

        const nz = Math.sqrt(Math.max(.000001, 1 - nxy2));
        const rx0 = 2 * nx * nz, ry = 2 * ny * nz, rz0 = 2 * nz * nz - 1;
        const rx = rx0 * co + rz0 * si;
        const rz = -rx0 * si + rz0 * co;

        const top = Math.pow(Math.max(0, ry * .5 + .5), 1.4);
        const g = Math.pow(Math.max(rx * keydir[0] + ry * keydir[1] + rz * keydir[2], 0), 18);
        const ambient = Math.pow(Math.max(rx * forward[0] + ry * forward[1] + rz * forward[2], 0), 5);
        const fres = Math.pow(1 - nz, 5);

        let cr = .002 + .009 * top + .009 * ambient + .06 * g;
        let cg = .003 + .013 * top + .012 * ambient + .085 * g;
        let cb = .005 + .021 * top + .019 * ambient + .12 * g;

        for (let c = 0; c < cards.length; c++) {
          const card = cards[c];
          const facing = rx * card.dir[0] + ry * card.dir[1] + rz * card.dir[2];
          if (facing <= 0) continue;
          const invF = 1 / facing;
          const qx = Math.abs((rx * card.right[0] + ry * card.right[1] + rz * card.right[2]) * invF);
          const qy = Math.abs((rx * card.up[0] + ry * card.up[1] + rz * card.up[2]) * invF);
          const s0 = card.size[0], f0c = card.feather, s1 = card.size[1];
          if (qx > s0 + f0c || qy > s1 + f0c) continue;
          const mask = (1 - smooth(s0 - f0c, s0 + f0c, qx)) * (1 - smooth(s1 - f0c, s1 + f0c, qy));
          cr += card.color[0] * mask;
          cg += card.color[1] * mask;
          cb += card.color[2] * mask;
        }

        const base = [cr, cg, cb];
        const grazing = clamp(1 - nz, 0, 1);
        const edge = Math.pow(grazing, 1.32);
        const fresnel = f0 + (1 - f0) * Math.pow(grazing, 5);
        const bodyShade = Math.pow(Math.max(0, nz), 1.55);

        const wwVal = .45 + ny * .59 - nx * .16;
        const ubVal = .29 + ny * .76 + nz * .28 - nx * .18;
        const sbVal = .25 - nx * .80 + ny * .14 + nz * .12;
        const glVal = .17 + ny * .72 - nx * .25 + nz * .27;
        const bbVal = -ny * .84 + nx * .11 + .13;

        const whiteWide = wwVal > 0.01 ? Math.pow(wwVal, 5.4) * (0.28 + 0.72 * edge) : 0;
        const upperBox  = ubVal > 0.01 ? Math.pow(ubVal, highlightPower * .34) : 0;
        const sideBox   = sbVal > 0.01 ? Math.pow(sbVal, highlightPower * .24) : 0;
        const glint     = glVal > 0.01 ? Math.pow(glVal, highlightPower * .78) : 0;
        const bottomBox = bbVal > 0.01 ? Math.pow(bbVal, 4.5) : 0;

        const phase = Math.atan2(ny, nx) * 2.7 + nx * 4.2 - ny * 3.1 + sAngle * .50;
        const opticalPhase = phase + (1 - nz) * 7.5 * (.25 + p.ior * .30);

        const coatFresnel = 0.10 + 0.90 * Math.pow(grazing, 1.15);
        const whiteCoat = (upperBox * .42 + whiteWide * .12 + sideBox * .30 + glint * .82 + bottomBox * .18) * coatFresnel * (.46 + .55 * p.rim) * (1 - p.roughness * .57);
        // Steep grazing exponent keeps the deep optical core dark and transparent while lighting the 3D rim
        const neutralRim = (.16 + .54 * p.rim) * Math.pow(grazing, 1.65) * (.80 + .24 * p.thickness);

        // Optical transmission suppresses flat front-center chrome card decals while keeping curved Fresnel reflections and studio softboxes crisp
        const coreTransmitDamp = (1 - p.transmission * 0.90 * Math.pow(nz, 1.35)) * (0.15 + 0.85 * Math.pow(grazing, 0.85));
        const specEnergy = Math.max(cr, cg, cb) * coreTransmitDamp * (0.18 + 0.82 * edge) + whiteCoat * 1.25;
        const chromeSpec = clamp(specEnergy * 0.38, 0, 1);

        const matAlpha = mode === 'ethereal'
          ? clamp((0.02 + 0.04 * p.thickness + 0.08 * (1 - p.transmission)) * bodyShade + (0.22 + 0.18 * p.thickness) * Math.pow(grazing, 0.90) + 0.34 * chromeSpec, 0.025, 0.92)
          : clamp((0.04 + 0.075 * p.thickness + 0.15 * (1 - p.transmission)) * bodyShade + (0.30 + 0.22 * p.thickness) * Math.pow(grazing, 0.85) + 0.42 * chromeSpec * (0.50 + 0.50 * p.transmission), 0.04, 0.96);

        alphaLut[pFlat] = Math.round(255 * matAlpha);

        for (let k = 0; k < 3; k++) {
          const film = .5 + .5 * Math.cos(filmPhase[k] + (1 - nz) * 10.7);
          const tint = .72 + (.16 + .20 * fres) * film;
          const accent = palette[k][k];
          const tintR = tintV ? (tintV[k] * tintV[k]) : accent;

          const spectrum = .5 + .5 * Math.cos(opticalPhase * (.68 + .8 * p.iridescence) + specPhase[k]);
          const iris = spectrum * (.12 + .34 * p.iridescence) * Math.pow(grazing, 0.95) * p.iridescence * p.saturation * aurora;
          const effBase = base[k] * coreTransmitDamp;
          const reflection = effBase * (.10 + .44 * edge + .16 * fresnel) * envBoost;
          const transmissionBody = (.004 + .038 * tintR + .008 * spectrum) * p.transmission * (1 - .62 * edge) * (.85 + .35 * p.thickness);
          const absorption = Math.exp(-p.thickness * (.28 + .52 * tintR) * (1 + .62 * edge));
          const chroma = iris * (.16 + .68 * tintR + .32 * spectrum);
          const glassBase = (transmissionBody + chroma + reflection * .48) * absorption;
          const clear = glassBase + neutralRim * .36 + whiteCoat * (k === 0 ? .88 : k === 1 ? .92 : 1.04);
          const chromeReflection = effBase * tint * (.14 + .76 * edge) * (1 - p.roughness * .48);

          let value = chromeReflection + clear * .68 + fresnel * .20 * effBase;
          if (mode === 'crystal')  value += Math.pow(Math.abs(Math.sin(phase * 3.6)), 22) * edge * .16;
          if (mode === 'aura')     value += spectrum * .24 * Math.pow(grazing, 0.95) * p.saturation;
          if (mode === 'ethereal') value = clear * .82 + fresnel * .24 * effBase + spectrum * .18 * edge * p.saturation;

          value *= expVal;
          const mapped = clamp((value * (2.51 * value + .03)) / (value * (2.43 * value + .59) + .14), 0, 1);
          lut[o + k] = gammaTable[(mapped * 1023) | 0];
        }

        // Keep LUT alpha at 255 for native hit-testing, root attachments and contract tests
        lut[o + 3] = 255;
      }
    }

    this.__opticalGlassSignature = signature;
    this.lutKey = 'opticalglass/' + signature;
  };

  // --- 4. V7 SCREEN-SPACE OPTICAL BEVEL & SILHOUETTE PASS ---
  function computeActiveTendrilSamples(renderer, w, h, cov) {
    const samples = [];
    const rect = renderer.canvas?.getBoundingClientRect();
    const raster = renderer.raster;
    if (!rect || !rect.width || !rect.height || !raster) return samples;

    const scaleX = w / rect.width, scaleY = h / rect.height;
    const opaque = (x, y) => {
      const px = Math.floor((x - rect.left) * raster.width / rect.width);
      const py = Math.floor((y - rect.top) * raster.height / rect.height);
      return px >= 0 && py >= 0 && px < raster.width && py < raster.height && raster.pixels[(py * raster.width + px) * 4 + 3] > 128;
    };

    const rawJobs = [];
    for (const t of getTendrilInstances(renderer)) {
      if (Array.isArray(t.pendingDraw?.links)) rawJobs.push({ links: t.pendingDraw.links, phase: t.pendingDraw.phase || 0, width: t.width || 1920 });
      else if (Array.isArray(t.__lastLinks)) rawJobs.push({ links: t.__lastLinks, phase: t.__lastPhase || 0, width: t.width || 1920 });
    }

    const extent = Math.hypot(rect.width, rect.height) * .5;
    const route = typeof document !== 'undefined' && document.body?.classList?.contains('a11-action-mode');

    for (let j = 0; j < rawJobs.length; j++) {
      const { links, phase, width: tWidth } = rawJobs[j];
      for (let i = 0; i < links.length; i++) {
        const raw = links[i];
        if (!raw || !raw.a || !raw.b) continue;
        const fitted = A.fitTendrilLink ? A.fitTendrilLink(raw, opaque, extent) : raw;
        if (!fitted || (fitted.progress ?? 1) < .005) continue;
        const dx = fitted.b.x - fitted.a.x, dy = fitted.b.y - fitted.a.y, fullLen = Math.hypot(dx, dy);
        if (fullLen < 8) continue;
        const pVal = clamp(fitted.progress ?? 1, 0, 1);
        const point = t => {
          const q = A.organicCurve ? A.organicCurve(fitted.a, fitted.b, t, phase) : { x: fitted.a.x + dx * t, y: fitted.a.y + dy * t };
          if (route && A.actionArmOffset) q.x += A.actionArmOffset(fitted.a, fitted.b, t, tWidth);
          return q;
        };
        const end = point(pVal);
        const totalDist = Math.hypot(end.x - fitted.a.x, end.y - fitted.a.y);
        const rootRad = Math.min(fitted.rootRadius || 14, 24 * (A.OrganicTendrils?.thickness || 1.1), Math.max(1, totalDist * .2));
        const baseRad = t => (A.flowArmRadius ? A.flowArmRadius(t, totalDist) : 20) * rootRad / 24 * Math.sqrt(pVal);

        // Find where the curved centerline exits the body silhouette
        let exitT = 0;
        for (let s = 0; s <= 40; s++) {
          const t = (s / 40) * Math.min(0.75, pVal);
          const q = point(t);
          const ix = Math.floor((q.x - rect.left) * scaleX);
          const iy = Math.floor((q.y - rect.top) * scaleY);
          if (ix >= 0 && iy >= 0 && ix < w && iy < h && cov[iy * w + ix] > 35) {
            exitT = t;
          } else if (t > exitT + 0.06) {
            break;
          }
        }

        // Sample points along the actual curved centerline around exitT so neck damping follows the exact Bézier curve
        const tMin = Math.max(0, exitT * 0.35);
        const tMax = Math.min(pVal, exitT + Math.max(0.18, (rootRad * 2.2) / Math.max(20, totalDist)));
        for (let s = 0; s <= 18; s++) {
          const t = tMin + (s / 18) * (tMax - tMin);
          const q = point(t);
          const flareT = clamp(Math.max(0, t - exitT) / Math.max(0.05, (rootRad * 1.5) / Math.max(20, totalDist)), 0, 1);
          const flare = 1.0 + 0.28 * Math.pow(1.0 - flareT, 2.0);
          samples.push({
            x: (q.x - rect.left) * scaleX,
            y: (q.y - rect.top) * scaleY,
            r: baseRad(t) * flare * scaleX
          });
        }
      }
    }
    return samples;
  }

  function applyGlassSilhouettePass(renderer) {
    if (renderer.finish !== 'opticalglass' || (renderer.studio && renderer.studio.view !== 0)) return;
    const raster = renderer.raster;
    const img = renderer.image;
    if (!raster || !img || !renderer.ctx) return;

    const w = img.width, h = img.height;
    const rw = raster.width, rh = raster.height;
    if (w < 4 || h < 4 || rw !== w * 2 || rh !== h * 2) return;

    if (!renderer.glassCoverage || renderer.glassCoverage.length !== w * h) {
      renderer.glassCoverage = new Uint8Array(w * h);
    }
    const cov = renderer.glassCoverage;
    const depth = raster.depth;
    const rpix = raster.pixels;

    // Build 1x geometric coverage from 2x depth buffer AND restore 255 alpha in raster.pixels for hitTest / OrganicTendrils
    for (let y = 0; y < h; y++) {
      const r0 = (y * 2) * rw, r1 = r0 + rw, dstRow = y * w;
      for (let x = 0; x < w; x++) {
        const ia = r0 + (x * 2), ib = ia + 1, ic = r1 + (x * 2), id = ic + 1;
        const ca = depth[ia] > 0 ? 1 : 0;
        const cb = depth[ib] > 0 ? 1 : 0;
        const cc = depth[ic] > 0 ? 1 : 0;
        const cd = depth[id] > 0 ? 1 : 0;
        if (ca) rpix[(ia << 2) + 3] = 255;
        if (cb) rpix[(ib << 2) + 3] = 255;
        if (cc) rpix[(ic << 2) + 3] = 255;
        if (cd) rpix[(id << 2) + 3] = 255;
        cov[dstRow + x] = (ca + cb + cc + cd) * 63.75;
      }
    }

    const sw = Math.ceil(w / 2), sh = Math.ceil(h / 2), count = sw * sh;
    if (!renderer.edgeDist || renderer.edgeDist.length !== count) {
      renderer.edgeDist = new Float32Array(count);
      renderer.edgeMask = new Uint8Array(count);
    }
    const mask = renderer.edgeMask, dist = renderer.edgeDist;

    // Limit post-refraction bevel to the native body mesh; do not coat detached orbit beads
    const verts = renderer.mesh?.projected;
    let bodyLeft = 0, bodyRight = sw - 1, bodyTop = 0, bodyBottom = sh - 1;
    if (verts && verts.length >= 6) {
      let bxmin = w * 2, bymin = h * 2, bxmax = 0, bymax = 0;
      for (let k = 0; k < verts.length; k += 6) {
        const vx = verts[k], vy = verts[k + 1];
        if (Number.isFinite(vx) && Number.isFinite(vy)) {
          if (vx < bxmin) bxmin = vx;
          if (vx > bxmax) bxmax = vx;
          if (vy < bymin) bymin = vy;
          if (vy > bymax) bymax = vy;
        }
      }
      if (bxmax > bxmin && bymax > bymin) {
        bodyLeft = Math.max(0, Math.floor(bxmin / 4) - 2);
        bodyRight = Math.min(sw - 1, Math.ceil(bxmax / 4) + 2);
        bodyTop = Math.max(0, Math.floor(bymin / 4) - 2);
        bodyBottom = Math.min(sh - 1, Math.ceil(bymax / 4) + 2);
      }
    }

    let xmin = sw, ymin = sh, xmax = 0, ymax = 0;
    for (let y = 0; y < sh; y++) {
      const sy = Math.min(h - 1, y * 2) * w;
      const dRow = y * sw;
      const inY = y >= bodyTop && y <= bodyBottom;
      for (let x = 0; x < sw; x++) {
        const sx = Math.min(w - 1, x * 2);
        const a = cov[sy + sx], ind = dRow + x;
        const inside = inY && x >= bodyLeft && x <= bodyRight && a > 35;
        mask[ind] = inside ? 1 : 0;
        dist[ind] = inside ? 64 : 0;
        if (inside) {
          if (x < xmin) xmin = x;
          if (x > xmax) xmax = x;
          if (y < ymin) ymin = y;
          if (y > ymax) ymax = y;
        }
      }
    }
    if (xmax <= xmin || ymax <= ymin) return;

    for (let y = 1; y < sh - 1; y++) {
      const row = y * sw;
      for (let x = 1; x < sw - 1; x++) {
        const i = row + x;
        if (!mask[i]) continue;
        dist[i] = Math.min(dist[i], dist[i - 1] + 1, dist[i - sw] + 1, dist[i - sw - 1] + 1.4, dist[i - sw + 1] + 1.4);
      }
    }
    for (let y = sh - 2; y >= 1; y--) {
      const row = y * sw;
      for (let x = sw - 2; x >= 1; x--) {
        const i = row + x;
        if (!mask[i]) continue;
        dist[i] = Math.min(dist[i], dist[i + 1] + 1, dist[i + sw] + 1, dist[i + sw + 1] + 1.4, dist[i + sw - 1] + 1.4);
      }
    }

    const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
    const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;
    const rx = Math.max(10, xmax - xmin), ry = Math.max(10, ymax - ymin);
    const cx = (xmin + xmax) * .5, cy = (ymin + ymax) * .5;
    // Proportional V7 Studio wall thickness across any companion stage size
    const tw = Math.max(2.8, Math.min(10, rx * .022 * (.65 + .65 * p.thickness)));
    const pix = img.data;

    const samples = computeActiveTendrilSamples(renderer, w, h, cov);
    let activeSig = String(renderer.form ?? '');
    for (const t of getTendrilInstances(renderer)) {
      const l = t.pendingDraw?.links || t.__lastLinks;
      if (Array.isArray(l) && l.length) {
        activeSig += '|' + l.map(x => `${Math.round(x.a?.x || 0)},${Math.round(x.a?.y || 0)}-${Math.round(x.b?.x || 0)},${Math.round(x.b?.y || 0)}`).join(';');
      }
    }
    renderer.__opticalBodyMeta = { w, h, sw, sh, cov, dist, samplesCount: samples.length, activeSig };

    const yStart = Math.max(2, (ymin - 2) * 2), yEnd = Math.min(h - 2, (ymax + 3) * 2);
    const xStart = Math.max(2, (xmin - 2) * 2), xEnd = Math.min(w - 2, (xmax + 3) * 2);
    const rimIntensity = (.48 + p.rim * .64);
    const irisSat = p.iridescence * p.saturation;

    for (let y = yStart; y < yEnd; y++) {
      const ym = (y * .5 - cy) / ry * 2;
      const toplight = gauss(ym, -.74, .49);
      const bottom = gauss(ym, .91, .26);
      const row = y * w;
      const y2 = y * .5, yi = y2 | 0, suby = y2 - yi;
      const yi0 = Math.min(sh - 1, yi) * sw, yi1 = Math.min(sh - 1, yi + 1) * sw;

      for (let x = xStart; x < xEnd; x++) {
        const idx = row + x, cover = cov[idx] / 255;
        if (cover < .008) continue;
        const pIdx = idx << 2;

        const x2 = x * .5, xi = x2 | 0, sub = x2 - xi;
        const xi0 = Math.min(sw - 1, xi), xi1 = Math.min(sw - 1, xi + 1);
        const a = dist[yi0 + xi0], b = dist[yi0 + xi1], c = dist[yi1 + xi0], d = dist[yi1 + xi1];
        const dd = (a * (1 - sub) + b * sub) * (1 - suby) + (c * (1 - sub) + d * sub) * suby;

        const xn = (x2 - cx) / rx * 2;
        const side = gauss(Math.abs(xn), .88, .29);
        const topGold = gauss(xn, -.70, .43) * toplight;
        const pink = gauss(xn, .70, .44) * toplight;
        const cyan = gauss(xn, -.22, .44) * toplight;
        const whiteCap = (toplight * (.58 + .34 * gauss(xn, 0, .75)) + .19 * side + .17 * bottom);

        const width = tw * (1 + .28 * toplight + .07 * side);
        const edge1 = gauss(dd, width * .24, Math.max(0.95, width * .20));
        const body = gauss(dd, width * .76, Math.max(1.8, width * .62));
        const inner = gauss(dd, width * 1.85, Math.max(1.5, width * .45));

        // Open both the 2D silhouette rim and the 3D Fresnel edge inside the cross-section of any active tentacle exiting the body
        let tendrilDamp = 1.0;
        if (samples.length > 0 && dd < width * 3.4) {
          let minNormDist = 10.0;
          for (let sIdx = 0; sIdx < samples.length; sIdx++) {
            const sp = samples[sIdx];
            const d2 = (x - sp.x) * (x - sp.x) + (y - sp.y) * (y - sp.y);
            const rCheck = sp.r * 1.20;
            if (d2 < rCheck * rCheck) {
              const nd = Math.sqrt(d2) / Math.max(1, sp.r);
              if (nd < minNormDist) minNormDist = nd;
            }
          }
          if (minNormDist < 1.12) {
            const tRim = clamp((minNormDist - 0.65) / 0.42, 0, 1);
            tendrilDamp = tRim * tRim * (3 - 2 * tRim);
          }
        }

        const white = clamp((edge1 * 1.02 + body * .16 + inner * .04) * whiteCap * rimIntensity * .92) * tendrilDamp;
        const blueGlint = (edge1 * .88 + body * .56 + inner * .22) * (cyan * 1.65 + bottom * 1.25 + gauss(xn, .85, .35) * .32) * irisSat * tendrilDamp;
        const pinkGlint = (edge1 * .80 + body * .58) * pink * 1.15 * irisSat * tendrilDamp;
        const goldGlint = (edge1 * .68 + body * .50) * (topGold + gauss(xn, -.95, .36) * .22) * 1.10 * irisSat * tendrilDamp;

        const depthCavity = inner * .10 * (1 - p.transmission * .85);
        const opticalWave = gauss(dd, width * 2.45, Math.max(2.6, width * 2.00));
        const blueBloom = gauss(xn, -.35, .60) * gauss(ym, -.55, .52) * opticalWave * 1.15 * irisSat;
        const pinkBloom = gauss(xn, .68, .41) * gauss(ym, -.66, .37) * opticalWave * 1.20 * irisSat;
        const warmBloom = gauss(xn, -.76, .36) * gauss(ym, -.62, .43) * opticalWave * 1.10 * irisSat;

        const addR = (235 * white + blueGlint * accentCool[0] * .74 + pinkGlint * accentMagenta[0] * .90 + goldGlint * accentWarm[0] * .64 + blueBloom * accentCool[0] * 2.0 + pinkBloom * accentMagenta[0] * 2.1 + warmBloom * accentWarm[0] * 1.45) * cover;
        const addG = (244 * white + blueGlint * accentCool[1] * .74 + pinkGlint * accentMagenta[1] * .90 + goldGlint * accentWarm[1] * .64 + blueBloom * accentCool[1] * 2.0 + pinkBloom * accentMagenta[1] * 2.1 + warmBloom * accentWarm[1] * 1.45) * cover;
        const addB = (253 * white + blueGlint * accentCool[2] * .74 + pinkGlint * accentMagenta[2] * .90 + goldGlint * accentWarm[2] * .64 + blueBloom * accentCool[2] * 2.0 + pinkBloom * accentMagenta[2] * 2.1 + warmBloom * accentWarm[2] * 1.45) * cover;

        // When tendrilDamp < 1, also damp the 3D mesh's own grazing white edge so no white line cuts across the tentacle neck
        const meshEdgeDamp = (1 - depthCavity) * (0.14 + 0.86 * tendrilDamp);
        pix[pIdx]     = Math.min(255, Math.max(0, pix[pIdx]     * meshEdgeDamp + addR));
        pix[pIdx + 1] = Math.min(255, Math.max(0, pix[pIdx + 1] * meshEdgeDamp + addG));
        pix[pIdx + 2] = Math.min(255, Math.max(0, pix[pIdx + 2] * meshEdgeDamp + addB));

        const bevelAlpha = 255 * clamp((white * 1.05 + blueGlint * .72 + pinkGlint * .68 + goldGlint * .58 + blueBloom * .88 + pinkBloom * .78 + warmBloom * .68) * cover);
        const basePixAlpha = pix[pIdx + 3] * (0.26 + 0.74 * tendrilDamp);
        pix[pIdx + 3] = Math.min(255, Math.max(basePixAlpha, bevelAlpha));
      }
    }

    renderer.ctx.putImageData(img, 0, 0);
  }

  if (originalDraw) {
    proto.draw = function opticalGlassDraw(timeSeconds) {
      const isGlass = this.finish === 'opticalglass' && (!this.studio || this.studio.view === 0);
      if (isGlass) {
        this.shadeTable();
        if (this.raster) this.raster.__opticalAlphaLut = this.__opticalAlphaLut;
      } else if (this.raster) {
        this.raster.__opticalAlphaLut = null;
      }

      try {
        originalDraw.call(this, timeSeconds);
      } finally {
        if (this.raster) this.raster.__opticalAlphaLut = null;
      }

      if (isGlass && !this.hidden && this.ctx && this.image && this.raster) {
        applyGlassSilhouettePass(this);
      }
    };
  }

  // --- 5. SEAMLESS ORGANIC TENDRIL V7 OPTICAL GLASS INTEGRATION ---
  if (A.OrganicTendrils) {
    const tProto = A.OrganicTendrils.prototype;
    const origTendrilDraw = tProto.draw;
    if (origTendrilDraw) {
      tProto.draw = function opticalGlassTendrilDraw(links, phase, lut, view, renderer) {
        this.__lastLinks = Array.isArray(links) ? links : null;
        this.__lastPhase = phase || 0;
        if (Array.isArray(links) && links.length > 0) registeredTendrils.add(this);
        else registeredTendrils.delete(this);
        if (renderer) renderer.__lastTendrilInstance = this;
        return origTendrilDraw.call(this, links, phase, lut, view, renderer);
      };
    }

    const origTendrilRender = tProto.render;
    if (origTendrilRender) {
      tProto.render = function opticalGlassTendrilRender(links, phase, lut, view, renderer) {
        this.__lastLinks = Array.isArray(links) ? links : null;
        this.__lastPhase = phase || 0;
        if (Array.isArray(links) && links.length > 0) registeredTendrils.add(this);
        else registeredTendrils.delete(this);
        if (renderer && Array.isArray(links) && links.length > 0) renderer.__lastTendrilInstance = this;
        const isGlass = Boolean(renderer && renderer.finish === 'opticalglass');
        if (isGlass && !renderer.__inTendrilSyncDraw) {
          let expectedSig = String(renderer.form ?? '');
          for (const t of getTendrilInstances(renderer)) {
            const l = t.pendingDraw?.links || t.__lastLinks;
            if (Array.isArray(l) && l.length) {
              expectedSig += '|' + l.map(x => `${Math.round(x.a?.x || 0)},${Math.round(x.a?.y || 0)}-${Math.round(x.b?.x || 0)},${Math.round(x.b?.y || 0)}`).join(';');
            }
          }
          if (renderer.__opticalBodyMeta?.activeSig !== expectedSig && typeof renderer.draw === 'function') {
            renderer.__inTendrilSyncDraw = true;
            try { renderer.draw(renderer.lastTime || 0); } catch (_) {}
            finally { renderer.__inTendrilSyncDraw = false; }
          }
        }
        this.__activeRenderRenderer = isGlass ? renderer : null;
        try {
          return origTendrilRender.call(this, links, phase, lut, view, renderer);
        } finally {
          this.__activeRenderRenderer = null;
        }
      };
    }

    const origTube = tProto.tube;
    if (origTube) {
      tProto.tube = function opticalGlassTube(link, phase, lut, view) {
        const renderer = this.__activeRenderRenderer || A.app?.renderer;
        if (!renderer || renderer.finish !== 'opticalglass' || view !== 0) {
          return origTube.call(this, link, phase, lut, view);
        }

        const pVal = Math.max(0, Math.min(1, link.progress));
        const route = typeof document !== 'undefined' && document.body?.classList?.contains('a11-action-mode');
        const point = t => {
          const q = A.organicCurve(link.a, link.b, t, phase);
          if (route && A.actionArmOffset) q.x += A.actionArmOffset(link.a, link.b, t, this.width);
          return q;
        };
        const end = point(pVal);
        const dx = link.b.x - link.a.x, dy = link.b.y - link.a.y, fullLength = Math.hypot(dx, dy);
        if (!Number.isFinite(fullLength) || fullLength < 1) return;
        const ux = dx / fullLength, uy = dy / fullLength;
        const totalDist = Math.hypot(end.x - link.a.x, end.y - link.a.y);
        const rootRadius = Math.min(link.rootRadius, 24 * (A.OrganicTendrils.thickness || 1.1), Math.max(1, totalDist * .2));
        const baseRadius = t => A.flowArmRadius(t, totalDist) * rootRadius / 24 * Math.sqrt(pVal);

        // Determine where the tentacle exits the body silhouette in live rendering
        const liveRenderer = this.__activeRenderRenderer;
        const bodyMeta = liveRenderer?.__opticalBodyMeta;
        const canvasRect = liveRenderer?.canvas?.getBoundingClientRect();
        const hasLiveBody = Boolean(bodyMeta && canvasRect && canvasRect.width > 0 && canvasRect.height > 0);
        const scaleX = hasLiveBody ? bodyMeta.w / canvasRect.width : 1;
        const scaleY = hasLiveBody ? bodyMeta.h / canvasRect.height : 1;

        let exitAlong = 0;
        if (hasLiveBody) {
          const maxCheck = Math.min(totalDist * 0.75, Math.max(canvasRect.width, canvasRect.height) * 0.6);
          for (let d = 0; d <= maxCheck; d += 2) {
            const tApprox = clamp(d / Math.max(1, totalDist), 0, 1) * pVal;
            const q = point(tApprox);
            const ix = Math.floor((q.x - canvasRect.left) * scaleX);
            const iy = Math.floor((q.y - canvasRect.top) * scaleY);
            if (ix >= 0 && iy >= 0 && ix < bodyMeta.w && iy < bodyMeta.h && bodyMeta.cov[iy * bodyMeta.w + ix] > 35) {
              exitAlong = (q.x - link.a.x) * ux + (q.y - link.a.y) * uy;
            } else if (d > exitAlong + 8) {
              break;
            }
          }
        }

        const flareSpan = Math.max(16, rootRadius * 1.85);
        const segments = Math.min(1024, Math.max(64, Math.ceil(totalDist / 2)));
        const centers = new Float32Array((segments + 1) * 6);
        let minY = 0, maxY = 0;

        for (let j = 0; j <= segments; j++) {
          const t = j / segments, q = point(t * pVal), x = q.x - link.a.x, y = q.y - link.a.y;
          const k = j * 6;
          const along = x * ux + y * uy;
          centers[k] = along;
          centers[k + 1] = -x * uy + y * ux;

          const rBase = baseRadius(t);
          // Smooth S-curve trumpet collar flare centered across the exit contour (no derivative kink!)
          const flareU = clamp((along - (exitAlong - flareSpan * 0.25)) / (flareSpan * 1.25), 0, 1);
          const smoothFlare = (1 - flareU) * (1 - flareU) * (1 + 2 * flareU);
          centers[k + 2] = rBase * (1.0 + 0.26 * smoothFlare);
          centers[k + 5] = rBase;

          minY = Math.min(minY, centers[k + 1]);
          maxY = Math.max(maxY, centers[k + 1]);
        }

        for (let j = 0; j <= segments; j++) {
          const k = j * 6, before = Math.max(0, j - 1) * 6, after = Math.min(segments, j + 1) * 6;
          const span = Math.max(.0001, centers[after] - centers[before]);
          centers[k + 3] = (centers[after + 1] - centers[before + 1]) / span;
          // Use unflared base radius derivative for longitudinal normal slope so the collar never has a bright crease
          centers[k + 4] = (centers[after + 5] - centers[before + 5]) / span;
          const projectedRadius = centers[k + 2] * Math.sqrt(1 + centers[k + 3] * centers[k + 3]);
          minY = Math.min(minY, centers[k + 1] - projectedRadius);
          maxY = Math.max(maxY, centers[k + 1] + projectedRadius);
        }

        const pad = Math.ceil(rootRadius * 1.4 + 4), left = -pad, top = Math.floor(minY - 4);
        const width = Math.ceil(fullLength + pad * 2), height = Math.ceil(maxY - minY + 8);
        const scale = Math.min(Math.max(2.5, this.dpr * 1.5), 8192 / width, Math.sqrt(2600000 / (width * height)));
        const w = Math.max(32, Math.ceil(width * scale / 32) * 32), h = Math.max(16, Math.ceil(height * scale / 16) * 16);

        let buffer = this.buffers.get(link.id);
        if (!buffer || buffer.width !== w || buffer.height !== h) {
          const c = document.createElement('canvas');
          c.width = w; c.height = h;
          const ctx = c.getContext('2d', { alpha: true });
          if (!ctx) return;
          const image = ctx.createImageData(w, h);
          buffer = { canvas: c, ctx, image, raster: { width: w, height: h, pixels: image.data }, width: w, height: h };
          this.buffers.set(link.id, buffer);
        }

        const r = buffer.raster, pixels = r.pixels, sampling = scale, sampleCol = this.color;
        const lutSize = Math.round(Math.sqrt(lut.length / 4));
        pixels.fill(0);
        let segment = 0;

        const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
        const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;
        const isEthereal = (p.mode === 'ethereal');
        const rimIntensity = (.52 + p.rim * .68);
        const irisSat = p.iridescence * p.saturation;

        for (let x = Math.max(0, Math.floor(-left * sampling)); x < r.width; x++) {
          const along = left + (x + .5) / sampling;
          if (along > centers[segments * 6]) break;
          while (segment < segments - 1 && centers[(segment + 1) * 6] < along) segment++;
          const k = segment * 6, span = centers[k + 6] - centers[k];
          if (span <= .0001) continue;
          const f = Math.max(0, Math.min(1, (along - centers[k]) / span));
          const cy = centers[k + 1] * (1 - f) + centers[k + 7] * f;
          const rad = centers[k + 2] * (1 - f) + centers[k + 8] * f;
          if (rad < .0001) continue;

          const tangent = centers[k + 3] * (1 - f) + centers[k + 9] * f;
          const inv = 1 / Math.sqrt(1 + tangent * tangent), tx = inv, ty = tangent * inv;
          const slope = (centers[k + 4] * (1 - f) + centers[k + 10] * f) * inv;
          const normalLength = Math.sqrt(1 + slope * slope);
          const half = rad / tx;
          const first = Math.max(1, Math.floor((cy - half - top) * sampling - 1));
          const last = Math.min(r.height - 2, Math.ceil((cy + half - top) * sampling + 1));

          for (let y = first; y <= last; y++) {
            const localY = top + (y + .5) / sampling;
            const transverse = (localY - cy) * tx;
            const coverage = Math.max(0, Math.min(1, (rad - Math.abs(transverse)) * sampling + .5));
            if (!coverage) continue;

            // Seamless body contour masking: prevent any buried root pixels from showing behind the transparent glass body while filling concave bays cleanly
            let bodyMask = 1.0;
            let neckGlintFade = 1.0;
            if (hasLiveBody) {
              if (along < 0) continue;
              const sx = link.a.x + along * ux - localY * uy;
              const sy = link.a.y + along * uy + localY * ux;
              const bix = (sx - canvasRect.left) * scaleX;
              const biy = (sy - canvasRect.top) * scaleY;
              if (bix >= 0 && biy >= 0 && bix < bodyMeta.w && biy < bodyMeta.h) {
                const bx2 = bix * .5, by2 = biy * .5, bxi = bx2 | 0, byi = by2 | 0;
                const bsubx = bx2 - bxi, bsuby = by2 - byi;
                const by0 = Math.min(bodyMeta.sh - 1, byi) * bodyMeta.sw;
                const by1 = Math.min(bodyMeta.sh - 1, byi + 1) * bodyMeta.sw;
                const bx0 = Math.min(bodyMeta.sw - 1, bxi), bx1 = Math.min(bodyMeta.sw - 1, bxi + 1);
                const da = bodyMeta.dist[by0 + bx0], db = bodyMeta.dist[by0 + bx1];
                const dc = bodyMeta.dist[by1 + bx0], ddVal = bodyMeta.dist[by1 + bx1];
                const bodyDd = (da * (1 - bsubx) + db * bsubx) * (1 - bsuby) + (dc * (1 - bsubx) + ddVal * bsubx) * bsuby;
                if (bodyDd >= 1.85) continue;
                if (bodyDd > 0) {
                  bodyMask = clamp(1 - bodyDd / 1.85, 0, 1);
                  neckGlintFade = clamp(1 - bodyDd / 0.85, 0, 1);
                }
              }
            }

            const q = Math.max(-1, Math.min(1, transverse / rad));
            const nAlong = (-ty * q - tx * slope) / normalLength, nAcross = (tx * q - ty * slope) / normalLength;
            const nx = ux * nAlong - uy * nAcross, ny = -(uy * nAlong + ux * nAcross);
            const nz = Math.sqrt(Math.max(0, 1 - q * q)) / normalLength;
            const o = (y * r.width + x) << 2;

            A.sampleMaterial(lut, lutSize, nx, ny, sampleCol);

            // Pixel-space V7 Optical Glass Cross-Section Bevel on the tube matching glassSilhouettePass wall thickness
            const toplight = gauss(-ny, -.74, .50);
            const bottom = gauss(-ny, .91, .28);
            const side = gauss(Math.abs(nx), .88, .30);
            const whiteCap = (toplight * (.58 + .34 * gauss(nx, 0, .75)) + .19 * side + .17 * bottom);

            const ddPx = (1.0 - Math.abs(q)) * rad;
            const twTube = Math.min(rad * 0.54, (2.3 + 1.7 * p.thickness) * (1 + .26 * toplight + .07 * side));
            const edge1 = gauss(ddPx, twTube * .24, Math.max(0.70, twTube * .20));
            const wallBody = gauss(ddPx, twTube * .76, Math.max(1.25, twTube * .60));
            const wallInner = gauss(ddPx, twTube * 1.85, Math.max(1.05, twTube * .45));
            const opticalWave = gauss(ddPx, twTube * 2.45, Math.max(1.70, twTube * 1.95));

            const white = clamp((edge1 * 1.02 + wallBody * .16 + wallInner * .04) * whiteCap * rimIntensity * .92) * neckGlintFade;
            const blueGlint = (edge1 * .88 + wallBody * .56 + wallInner * .22) * (toplight * 1.35 + bottom * 1.25) * irisSat * neckGlintFade;
            const pinkGlint = (edge1 * .80 + wallBody * .58) * (side * 0.95 + toplight * 0.55) * irisSat * neckGlintFade;
            const goldGlint = (edge1 * .68 + wallBody * .50) * (toplight * 0.90) * irisSat * neckGlintFade;

            const blueBloom = opticalWave * toplight * 0.50 * irisSat;
            const pinkBloom = opticalWave * side * 0.48 * irisSat;
            const warmBloom = opticalWave * bottom * 0.38 * irisSat;

            const addR = 235 * white + blueGlint * accentCool[0] * .74 + pinkGlint * accentMagenta[0] * .90 + goldGlint * accentWarm[0] * .64 + blueBloom * accentCool[0] * 1.6 + pinkBloom * accentMagenta[0] * 1.7 + warmBloom * accentWarm[0] * 1.2;
            const addG = 244 * white + blueGlint * accentCool[1] * .74 + pinkGlint * accentMagenta[1] * .90 + goldGlint * accentWarm[1] * .64 + blueBloom * accentCool[1] * 1.6 + pinkBloom * accentMagenta[1] * 1.7 + warmBloom * accentWarm[1] * 1.2;
            const addB = 253 * white + blueGlint * accentCool[2] * .74 + pinkGlint * accentMagenta[2] * .90 + goldGlint * accentWarm[2] * .64 + blueBloom * accentCool[2] * 1.6 + pinkBloom * accentMagenta[2] * 1.7 + warmBloom * accentWarm[2] * 1.2;

            const wallGrazing = clamp(1.0 - ddPx / Math.max(1.5, twTube * 2.1), 0.0, 1.0);
            const grazing = clamp(1.0 - nz, 0.0, 1.0) * (0.35 + 0.65 * wallGrazing);
            const bodyShade = Math.pow(Math.max(0, nz), 1.55);
            const depthCavity = wallInner * .10 * (1 - p.transmission * .85);
            // Keep the tube core deep translucent glass just like the body interior, concentrating reflections on the curved glass walls
            const tubeCoreDamp = (1 - p.transmission * 0.84 * (1 - wallGrazing * 0.75)) * (1 - depthCavity);
            const coreDamp = isEthereal ? (1.0 - 0.86 * p.transmission) : tubeCoreDamp;

            pixels[o]     = Math.min(255, Math.max(0, sampleCol[0] * coreDamp + addR));
            pixels[o + 1] = Math.min(255, Math.max(0, sampleCol[1] * coreDamp + addG));
            pixels[o + 2] = Math.min(255, Math.max(0, sampleCol[2] * coreDamp + addB));

            const matAlpha = isEthereal
              ? clamp((0.02 + 0.04 * p.thickness + 0.08 * (1 - p.transmission)) * bodyShade + (0.22 + 0.18 * p.thickness) * Math.pow(grazing, 0.90), 0.025, 0.90)
              : clamp((0.04 + 0.075 * p.thickness + 0.15 * (1 - p.transmission)) * bodyShade + (0.30 + 0.22 * p.thickness) * Math.pow(grazing, 0.85), 0.04, 0.95);
            const bevelAlpha = clamp(white * 1.05 + blueGlint * .72 + pinkGlint * .68 + goldGlint * .58 + blueBloom * .88 + pinkBloom * .78 + warmBloom * .68, 0, 1);
            const totAlpha = Math.max(matAlpha, bevelAlpha);

            pixels[o + 3] = Math.round(coverage * bodyMask * 255 * totAlpha);
          }
        }

        buffer.ctx.putImageData(buffer.image, 0, 0);
        this.ctx.imageSmoothingEnabled = true;
        this.ctx.imageSmoothingQuality = 'high';
        this.ctx.globalAlpha = Math.min(1, pVal / .08);
        this.ctx.save();
        this.ctx.translate(link.a.x, link.a.y);
        this.ctx.transform(ux, uy, -uy, ux, 0, 0);
        this.ctx.drawImage(buffer.canvas, left, top, w / scale, h / scale);
        this.ctx.restore();
        this.ctx.globalAlpha = 1;
      };
    }
  }

  Object.defineProperty(proto, '__axxOpticalGlass', { value: true });

  // --- 6. UI CONTROLS & APPEARANCE INTEGRATION ---
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
      ['aura', 'Prismatic Aura'],
      ['ethereal', 'Ethereal Glass']
    ]) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.style.cssText = 'font:11px system-ui;min-height:34px;padding:6px 9px;border-radius:9px';
      b.dataset.opticalPreset = key;
      b.dataset.preset = key;
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
  if (!panel && typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  }

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
