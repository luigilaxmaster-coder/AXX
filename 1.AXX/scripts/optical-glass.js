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
      t.__filteredAlphaLut = null;
      t.__filteredAlphaKey = null;
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

  // Upgrade mesh grid to V7 Studio density (144x96) when Optical Glass is active for smooth curvature without polygon facets
  function ensureV7MeshDensity(renderer) {
    if (!renderer || !A.SoftwareShapeCache20) return;
    if (renderer.finish === 'opticalglass') {
      if (renderer.mesh && (renderer.mesh.u !== 144 || renderer.mesh.v !== 96)) {
        if (!renderer.__nativeMesh) {
          renderer.__nativeMesh = renderer.mesh;
          renderer.__nativeShapeCache = renderer.shapeCache20;
        }
        if (!renderer.__v7Mesh) {
          const n = (144 + 1) * (96 + 1);
          renderer.__v7Mesh = {
            u: 144,
            v: 96,
            positions: new Float32Array(n * 3),
            projected: new Float32Array(n * 6),
            normals: new Float32Array(n * 3)
          };
          renderer.__v7ShapeCache = new A.SoftwareShapeCache20(144, 96);
        }
        renderer.mesh = renderer.__v7Mesh;
        renderer.shapeCache20 = renderer.__v7ShapeCache;
      }
    } else if (renderer.__nativeMesh && renderer.mesh !== renderer.__nativeMesh) {
      renderer.mesh = renderer.__nativeMesh;
      renderer.shapeCache20 = renderer.__nativeShapeCache;
    }
  }

  // --- 1. SUPERSAMPLED HD RESIZE FOR OPTICAL GLASS ---
  if (originalResize) {
    proto.resize = function opticalGlassResize() {
      ensureV7MeshDensity(this);
      if (this.finish !== 'opticalglass' || !this.canvas || !A.CpuRaster) {
        return originalResize.call(this);
      }
      const r = this.canvas.getBoundingClientRect();
      const qualityCap = this.settings?.quality === 'eco' ? 740 : this.settings?.quality === 'high' ? 1160 : 1040;
      const scale = this.settings?.quality === 'eco' ? 1.38 : 1.75;
      const max = this.reaching ? 1320 : qualityCap;
      const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
      const requestedRatio = Math.min(Math.max(dpr, 1.25) * scale, 2.75);
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
      ensureV7MeshDensity(this);
      if (prev !== finish) {
        for (const t of getTendrilInstances(this)) {
          t.buffers?.clear?.();
          t.filteredMaterial = null;
          t.materialKey = null;
          t.__filteredAlphaLut = null;
          t.__filteredAlphaKey = null;
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

  // --- 3. SHADE TABLE (Authentic V7 Optical Glass Studio Illumination + Per-Normal Alpha LUT) ---
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

        const whiteWide = wwVal > 0.01 ? Math.pow(wwVal, 4.8) : 0;
        const upperBox  = ubVal > 0.01 ? Math.pow(ubVal, highlightPower * .31) : 0;
        const sideBox   = sbVal > 0.01 ? Math.pow(sbVal, highlightPower * .22) : 0;
        const glint     = glVal > 0.01 ? Math.pow(glVal, highlightPower * .76) : 0;
        const bottomBox = bbVal > 0.01 ? Math.pow(bbVal, 4.3) : 0;

        const phase = Math.atan2(ny, nx) * 2.7 + nx * 4.2 - ny * 3.1 + sAngle * .50;
        const opticalPhase = phase + (1 - nz) * 7.5 * (.25 + p.ior * .30);

        // Exact V7 Studio equations preserving large curved 3D reflections and volumetric depth
        const neutralRim = (.17 + .57 * p.rim) * Math.pow(grazing, .65) * (.80 + .24 * p.thickness);
        const whiteCoat = (upperBox * .43 + whiteWide * .15 + sideBox * .31 + glint * .84 + bottomBox * .18) * (.46 + .55 * p.rim) * (1 - p.roughness * .57);
        const chromeSpec = clamp(Math.max(cr, cg, cb) * .40, 0, 1);

        const matAlpha = mode === 'ethereal'
          ? clamp((0.025 + 0.05 * p.thickness + 0.10 * (1 - p.transmission)) * bodyShade + (0.24 + 0.18 * p.thickness) * Math.pow(grazing, 0.80) + 0.34 * chromeSpec, 0.03, 0.92)
          : clamp((0.055 + 0.09 * p.thickness + 0.17 * (1 - p.transmission)) * bodyShade + (0.31 + 0.20 * p.thickness) * Math.pow(grazing, 0.70) + 0.43 * chromeSpec * (0.50 + 0.50 * p.transmission), 0.045, 0.96);

        alphaLut[pFlat] = Math.round(255 * matAlpha);

        for (let k = 0; k < 3; k++) {
          const film = .5 + .5 * Math.cos(filmPhase[k] + (1 - nz) * 10.7);
          const tint = .72 + (.16 + .20 * fres) * film;
          const accent = palette[k][k];
          const tintR = tintV ? (tintV[k] * tintV[k]) : accent;

          const spectrum = .5 + .5 * Math.cos(opticalPhase * (.68 + .8 * p.iridescence) + specPhase[k]);
          const iris = spectrum * (.09 + .28 * p.iridescence) * edge * p.iridescence * p.saturation * aurora;
          const reflection = base[k] * (.12 + .40 * edge + .14 * fresnel) * envBoost;
          const transmissionBody = (.009 + .065 * tintR + .012 * spectrum) * p.transmission * (1 - .58 * edge) * (.9 + .4 * p.thickness);
          const absorption = Math.exp(-p.thickness * (.23 + .48 * tintR) * (1 + .62 * edge));
          const chroma = iris * (.12 + .58 * tintR + .26 * spectrum);
          const glassBase = (transmissionBody + chroma + reflection * .46) * absorption;
          const clear = glassBase + neutralRim * .34 + whiteCoat * (k === 0 ? .88 : k === 1 ? .92 : 1.04);
          const chromeReflection = base[k] * tint * (.58 + .56 * edge) * (1 - p.roughness * .48);

          let value = chromeReflection + clear * .54 + fresnel * .18 * base[k];
          if (mode === 'crystal')  value += Math.pow(Math.abs(Math.sin(phase * 3.6)), 22) * edge * .15;
          if (mode === 'aura')     value += spectrum * .18 * edge * p.saturation;
          if (mode === 'ethereal') value = chromeReflection * .35 + clear * .76 + fresnel * .22 * base[k] + spectrum * .16 * edge * p.saturation;

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

  // --- 4. V7 FULL-RESOLUTION SMOOTHED SDF OPTICAL BEVEL & SILHOUETTE PASS ---
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

        const tMin = Math.max(0, exitT * 0.15);
        const tMax = Math.min(pVal, Math.max(0.68, exitT + (rootRad * 3.2) / Math.max(20, totalDist)));
        for (let s = 0; s <= 36; s++) {
          const t = tMin + (s / 36) * (tMax - tMin);
          const q = point(t);
          const flareT = clamp(Math.max(0, t - exitT) / Math.max(0.05, (rootRad * 1.75) / Math.max(20, totalDist)), 0, 1);
          const flare = 1.0 + 0.22 * Math.pow(1.0 - flareT, 2.0);
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

  const origDroplets = proto.droplets;
  if (origDroplets) {
    proto.droplets = function opticalGlassDroplets() {
      if (this.finish === 'opticalglass' && (!this.studio || this.studio.view === 0) && this.raster && this.image) {
        const w = this.image.width, h = this.image.height;
        const rw = this.raster.width, rh = this.raster.height;
        if (w >= 4 && h >= 4 && rw === w * 2 && rh === h * 2) {
          const totalPixels = w * h;
          if (!this.glassCoverage || this.glassCoverage.length !== totalPixels) {
            this.glassCoverage = new Uint8Array(totalPixels);
          }
          const cov = this.glassCoverage;
          const depth = this.raster.depth;
          for (let y = 0; y < h; y++) {
            const r0 = (y * 2) * rw, r1 = r0 + rw, dstRow = y * w;
            for (let x = 0; x < w; x++) {
              const ia = r0 + (x * 2), ib = ia + 1, ic = r1 + (x * 2), id = ic + 1;
              cov[dstRow + x] = ((depth[ia] > 0 ? 1 : 0) + (depth[ib] > 0 ? 1 : 0) + (depth[ic] > 0 ? 1 : 0) + (depth[id] > 0 ? 1 : 0)) * 63.75;
            }
          }
          this.__covCapturedPreDroplets = true;
        }
      }
      return origDroplets.call(this);
    };
  }

  function applyGlassSilhouettePass(renderer) {
    if (renderer.finish !== 'opticalglass' || (renderer.studio && renderer.studio.view !== 0)) return;
    const raster = renderer.raster;
    const img = renderer.image;
    if (!raster || !img || !renderer.ctx) return;

    const w = img.width, h = img.height;
    const rw = raster.width, rh = raster.height;
    if (w < 4 || h < 4 || rw !== w * 2 || rh !== h * 2) return;

    const totalPixels = w * h;
    if (!renderer.glassCoverage || renderer.glassCoverage.length !== totalPixels) {
      renderer.glassCoverage = new Uint8Array(totalPixels);
    }
    const cov = renderer.glassCoverage;
    const depth = raster.depth;
    const rpix = raster.pixels;
    const needCov = !renderer.__covCapturedPreDroplets;

    // 1. Restore 255 alpha in raster.pixels for hitTest / OrganicTendrils (and build cov if droplets hook didn't run)
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
        if (needCov) cov[dstRow + x] = (ca + cb + cc + cd) * 63.75;
      }
    }

    // 2. Full-Resolution (w x h) Subpixel-Seeded & Separable-Smoothed Signed Distance Field (zero staircase teeth!)
    if (!renderer.__fullDist || renderer.__fullDist.length !== totalPixels) {
      renderer.__fullDist = new Float32Array(totalPixels);
      renderer.__fullDistTemp = new Float32Array(totalPixels);
      renderer.__smoothCov = new Float32Array(totalPixels);
    }
    const dist = renderer.__fullDist;
    const temp = renderer.__fullDistTemp;
    const sCov = renderer.__smoothCov;
    dist.fill(0);
    sCov.fill(0);

    let xmin = w, ymin = h, xmax = 0, ymax = 0;
    for (let y = 1; y < h - 1; y++) {
      const row = y * w;
      for (let x = 1; x < w - 1; x++) {
        const ind = row + x;
        const a = cov[ind];
        if (a > 12) {
          // Subpixel seeding: fractional coverage seeds fractional boundary distance (0.25..1.0)
          dist[ind] = a < 250 ? (a / 255) : 128;
          if (x < xmin) xmin = x;
          if (x > xmax) xmax = x;
          if (y < ymin) ymin = y;
          if (y > ymax) ymax = y;
        }
      }
    }
    if (xmax <= xmin || ymax <= ymin) return;

    const y0 = Math.max(1, ymin - 2), y1 = Math.min(h - 2, ymax + 2);
    const x0 = Math.max(1, xmin - 2), x1 = Math.min(w - 2, xmax + 2);

    // Forward & backward Euclidean-Chamfer distance transform at full 1x resolution
    for (let y = y0; y <= y1; y++) {
      const row = y * w;
      for (let x = x0; x <= x1; x++) {
        const i = row + x;
        const d0 = dist[i];
        if (d0 <= 0) continue;
        dist[i] = Math.min(d0, dist[i - 1] + 1.0, dist[i - w] + 1.0, dist[i - w - 1] + 1.4142, dist[i - w + 1] + 1.4142);
      }
    }
    for (let y = y1; y >= y0; y--) {
      const row = y * w;
      for (let x = x1; x >= x0; x--) {
        const i = row + x;
        const d0 = dist[i];
        if (d0 <= 0) continue;
        dist[i] = Math.min(d0, dist[i + 1] + 1.0, dist[i + w] + 1.0, dist[i + w + 1] + 1.4142, dist[i + w - 1] + 1.4142);
      }
    }

    // Separable 5-tap [1, 4, 6, 4, 1]/16 Gaussian smoothing on dist & coverage eliminates all raster staircase steps
    for (let y = y0; y <= y1; y++) {
      const row = y * w;
      for (let x = x0; x <= x1; x++) {
        const i = row + x;
        const xm2 = Math.max(0, x - 2), xm1 = Math.max(0, x - 1), xp1 = Math.min(w - 1, x + 1), xp2 = Math.min(w - 1, x + 2);
        temp[i] = (dist[row + xm2] + 4 * dist[row + xm1] + 6 * dist[i] + 4 * dist[row + xp1] + dist[row + xp2]) * 0.0625;
        sCov[i] = (cov[row + xm1] + 2 * cov[i] + cov[row + xp1]) * 0.25;
      }
    }
    for (let y = y0; y <= y1; y++) {
      const row = y * w;
      const ym2 = Math.max(0, y - 2) * w, ym1 = Math.max(0, y - 1) * w, yp1 = Math.min(h - 1, y + 1) * w, yp2 = Math.min(h - 1, y + 2) * w;
      for (let x = x0; x <= x1; x++) {
        dist[row + x] = (temp[ym2 + x] + 4 * temp[ym1 + x] + 6 * temp[row + x] + 4 * temp[yp1 + x] + temp[yp2 + x]) * 0.0625;
      }
    }

    const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
    const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;
    // rx, ry, cx, cy, tw in half-pixel units to match V7 Studio scale exactly while sampling full-res smoothed dist * 0.5
    const rx = Math.max(10, (xmax - xmin) * .5), ry = Math.max(10, (ymax - ymin) * .5);
    const cx = (xmin + xmax) * .25, cy = (ymin + ymax) * .25;
    const tw = Math.max(2.7, Math.min(10, rx * .018 * (.65 + .65 * p.thickness)));
    const pix = img.data;

    const samples = computeActiveTendrilSamples(renderer, w, h, cov);
    let activeSig = String(renderer.form ?? '');
    for (const t of getTendrilInstances(renderer)) {
      const l = t.pendingDraw?.links || t.__lastLinks;
      if (Array.isArray(l) && l.length) {
        activeSig += '|' + l.map(x => `${Math.round(x.a?.x || 0)},${Math.round(x.a?.y || 0)}-${Math.round(x.b?.x || 0)},${Math.round(x.b?.y || 0)}`).join(';');
      }
    }
    renderer.__opticalBodyMeta = { w, h, cov, dist, samplesCount: samples.length, activeSig };

    const rimIntensity = (.48 + p.rim * .65);
    const irisSat = p.iridescence * p.saturation;

    for (let y = y0; y <= y1; y++) {
      const ym = (y * .5 - cy) / ry * 2;
      const toplight = gauss(ym, -.74, .49);
      const bottom = gauss(ym, .91, .26);
      const row = y * w;

      for (let x = x0; x <= x1; x++) {
        const idx = row + x;
        // Blend raw coverage with smoothed coverage at the outer edge for silky anti-aliased contours
        const rawCover = cov[idx] / 255;
        if (rawCover < .004) continue;
        const cover = rawCover < 0.98 ? clamp((rawCover * 0.65 + (sCov[idx] / 255) * 0.35), 0, 1) : 1.0;
        const pIdx = idx << 2;

        // Convert smoothed full-res pixel distance to V7 half-pixel distance units
        const dd = dist[idx] * 0.5;
        const xn = (x * .5 - cx) / rx * 2;
        const side = gauss(Math.abs(xn), .88, .29);
        const topGold = gauss(xn, -.70, .43) * toplight;
        const pink = gauss(xn, .70, .44) * toplight;
        const cyan = gauss(xn, -.22, .44) * toplight;
        const whiteCap = (toplight * (.65 + .38 * gauss(xn, 0, .75)) + .19 * side + .17 * bottom);

        const width = tw * (1 + .42 * toplight + .07 * side);
        const edge1 = gauss(dd, width * .26, Math.max(1.2, width * .23));
        const body = gauss(dd, width * .76, Math.max(2.2, width * .66));
        const inner = gauss(dd, width * 1.9, Math.max(1.6, width * .45));

        // Smoothly open the outer silhouette rim (both 2D bevel and 3D grazing Fresnel edge spike) where an active tentacle exits the body contour
        let tendrilDamp = 1.0;
        if (samples.length > 0 && dd < width * 3.2) {
          let minNormDist = 10.0;
          for (let sIdx = 0; sIdx < samples.length; sIdx++) {
            const sp = samples[sIdx];
            const d2 = (x - sp.x) * (x - sp.x) + (y - sp.y) * (y - sp.y);
            const rCheck = sp.r * 1.12;
            if (d2 < rCheck * rCheck) {
              const nd = Math.sqrt(d2) / Math.max(1, sp.r);
              if (nd < minNormDist) minNormDist = nd;
            }
          }
          if (minNormDist < 1.05) {
            const tRim = clamp((minNormDist - 0.76) / 0.26, 0, 1);
            tendrilDamp = tRim * tRim * (3 - 2 * tRim);
          }
        }

        const white = clamp((edge1 * 1.10 + body * .26 + inner * .08) * whiteCap * rimIntensity * .95) * tendrilDamp;
        const blueGlint = (edge1 * .82 + body * .50 + inner * .18) * (cyan * 1.50 + bottom * 1.15 + gauss(xn, .85, .35) * .28) * irisSat * tendrilDamp;
        const pinkGlint = (edge1 * .72 + body * .52) * pink * irisSat * tendrilDamp;
        const goldGlint = (edge1 * .62 + body * .46) * (topGold + gauss(xn, -.95, .36) * .19) * irisSat * tendrilDamp;

        const depthCavity = inner * .08 * (1 - p.transmission);
        const opticalWave = gauss(dd, width * 2.65, Math.max(3, width * 2.20));
        const blueBloom = gauss(xn, -.35, .60) * gauss(ym, -.55, .52) * opticalWave * irisSat * (0.25 + 0.75 * tendrilDamp);
        const pinkBloom = gauss(xn, .68, .41) * gauss(ym, -.66, .37) * opticalWave * irisSat * (0.25 + 0.75 * tendrilDamp);
        const warmBloom = gauss(xn, -.76, .36) * gauss(ym, -.62, .43) * opticalWave * irisSat * (0.25 + 0.75 * tendrilDamp);

        const addR = (235 * white + blueGlint * accentCool[0] * .70 + pinkGlint * accentMagenta[0] * .85 + goldGlint * accentWarm[0] * .60 + blueBloom * accentCool[0] * 1.9 + pinkBloom * accentMagenta[0] * 2.0 + warmBloom * accentWarm[0] * 1.35) * cover;
        const addG = (244 * white + blueGlint * accentCool[1] * .70 + pinkGlint * accentMagenta[1] * .85 + goldGlint * accentWarm[1] * .60 + blueBloom * accentCool[1] * 1.9 + pinkBloom * accentMagenta[1] * 2.0 + warmBloom * accentWarm[1] * 1.35) * cover;
        const addB = (253 * white + blueGlint * accentCool[2] * .70 + pinkGlint * accentMagenta[2] * .85 + goldGlint * accentWarm[2] * .60 + blueBloom * accentCool[2] * 1.9 + pinkBloom * accentMagenta[2] * 2.0 + warmBloom * accentWarm[2] * 1.35) * cover;

        // Soften the 3D mesh's grazing Fresnel rim across the entire outer grazing band (dd = 0..width*1.85) inside the tentacle core so zero contour arc cuts across the tentacle root
        const rimT = clamp(1.0 - dd / Math.max(2.2, width * 1.85), 0, 1);
        const rimBand = rimT * rimT * (3 - 2 * rimT);
        const grazeSoft = 1.0 - rimBand * (1.0 - tendrilDamp) * 0.65;
        const alphaSoft = 1.0 - rimBand * (1.0 - tendrilDamp) * 0.78;
        const edgeDamp = (1 - depthCavity) * grazeSoft;
        pix[pIdx]     = Math.min(255, Math.max(0, pix[pIdx]     * edgeDamp + addR));
        pix[pIdx + 1] = Math.min(255, Math.max(0, pix[pIdx + 1] * edgeDamp + addG));
        pix[pIdx + 2] = Math.min(255, Math.max(0, pix[pIdx + 2] * edgeDamp + addB));

        const bevelAlpha = 255 * clamp((white * 1.07 + blueGlint * .68 + pinkGlint * .64 + goldGlint * .56 + blueBloom * .85 + pinkBloom * .74 + warmBloom * .65) * cover);
        pix[pIdx + 3] = Math.min(255, Math.max(pix[pIdx + 3] * alphaSoft, bevelAlpha));
      }
    }

    if (!renderer.presentCanvas || renderer.presentCanvas.width !== w || renderer.presentCanvas.height !== h) {
      renderer.presentCanvas = document.createElement('canvas');
      renderer.presentCanvas.width = w;
      renderer.presentCanvas.height = h;
      renderer.presentCtx = renderer.presentCanvas.getContext('2d', { alpha: true });
    }
    if (renderer.presentCtx) {
      renderer.presentCtx.putImageData(img, 0, 0);
      renderer.ctx.clearRect(0, 0, w, h);
      renderer.ctx.imageSmoothingEnabled = true;
      renderer.ctx.imageSmoothingQuality = 'high';
      renderer.ctx.drawImage(renderer.presentCanvas, 0, 0, w, h);
    } else {
      renderer.ctx.putImageData(img, 0, 0);
    }
  }

  if (originalDraw) {
    proto.draw = function opticalGlassDraw(timeSeconds) {
      ensureV7MeshDensity(this);
      this.__covCapturedPreDroplets = false;
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

  // --- 5. HIGH-DPI ANTI-ALIASED 3D VOLUMETRIC ORGANIC TENDRILS ---
  if (A.OrganicTendrils) {
    const tProto = A.OrganicTendrils.prototype;

    function getFilteredAlphaLut(tendrilInst, renderer) {
      const rawAlpha = renderer?.__opticalAlphaLut;
      if (!rawAlpha) return null;
      const key = renderer.lutKey;
      if (tendrilInst.__filteredAlphaLut && tendrilInst.__filteredAlphaKey === key) {
        return tendrilInst.__filteredAlphaLut;
      }
      const size = 512;
      const temp = new Float32Array(size * size);
      const filtered = new Uint8ClampedArray(size * size);
      const weights = [1, 4, 6, 4, 1];
      for (let y = 0; y < size; y++) {
        const row = y * size;
        for (let x = 0; x < size; x++) {
          let sum = 0;
          for (let k = -2; k <= 2; k++) {
            const ix = Math.max(0, Math.min(size - 1, x + k * 2));
            sum += rawAlpha[row + ix] * weights[k + 2];
          }
          temp[row + x] = sum * 0.0625;
        }
      }
      for (let y = 0; y < size; y++) {
        const row = y * size;
        for (let x = 0; x < size; x++) {
          let sum = 0;
          for (let k = -2; k <= 2; k++) {
            const iy = Math.max(0, Math.min(size - 1, y + k * 2));
            sum += temp[iy * size + x] * weights[k + 2];
          }
          filtered[row + x] = sum * 0.0625;
        }
      }
      tendrilInst.__filteredAlphaKey = key;
      tendrilInst.__filteredAlphaLut = filtered;
      return filtered;
    }

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
        if (!isGlass) {
          this.__activeRenderRenderer = null;
          return origTendrilRender.call(this, links, phase, lut, view, renderer);
        }

        if (!renderer.__inTendrilSyncDraw) {
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

        // High-DPI 2.25x screen-space canvas rendering (never reset back to 1x by origTendrilRender)
        const started = performance.now();
        if (!this.ctx) return;
        const effPhase = phase * (A.OrganicTendrils.fluidity || 1);
        const ratio = Math.max(2.25, Math.min(2.5, typeof devicePixelRatio === 'number' ? devicePixelRatio : 2.25));
        if (this.width !== innerWidth || this.height !== innerHeight || this.dpr !== ratio) {
          this.width = innerWidth;
          this.height = innerHeight;
          this.dpr = ratio;
          this.canvas.width = Math.ceil(innerWidth * ratio);
          this.canvas.height = Math.ceil(innerHeight * ratio);
          this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        }
        this.ctx.clearRect(0, 0, this.width, this.height);
        this.visibleCount = 0;
        const rect = renderer?.canvas?.getBoundingClientRect(), raster = renderer?.raster;
        const opaque = rect?.width && rect?.height && raster ? (x, y) => {
          const px = Math.floor((x - rect.left) * raster.width / rect.width), py = Math.floor((y - rect.top) * raster.height / rect.height);
          return px >= 0 && py >= 0 && px < raster.width && py < raster.height && raster.pixels[(py * raster.width + px) * 4 + 3] > 128;
        } : null;
        const alive = new Set(links.map(l => l.id));
        for (const key of this.buffers.keys()) {
          if (!alive.has(key)) this.buffers.delete(key);
        }
        this.__activeRenderRenderer = renderer;
        try {
          const matLut = this.material(lut, renderer?.lutKey);
          for (const raw of links) {
            const link = A.fitTendrilLink(raw, opaque, rect ? Math.hypot(rect.width, rect.height) * .5 : 0);
            if (!link) continue;
            if (link.progress < .005 || Math.hypot(link.b.x - link.a.x, link.b.y - link.a.y) < 8) continue;
            this.tube(link, effPhase, matLut, view);
            this.visibleCount++;
          }
        } finally {
          this.__activeRenderRenderer = null;
        }
        this.drawMs = performance.now() - started;
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

        const flareSpan = Math.max(16, rootRadius * 1.75);
        const segments = Math.min(1024, Math.max(96, Math.ceil(totalDist / 1.5)));
        const centers = new Float32Array((segments + 1) * 6);
        let minY = 0, maxY = 0;

        for (let j = 0; j <= segments; j++) {
          const t = j / segments, q = point(t * pVal), x = q.x - link.a.x, y = q.y - link.a.y;
          const k = j * 6;
          const along = x * ux + y * uy;
          centers[k] = along;
          centers[k + 1] = -x * uy + y * ux;

          const rBase = baseRadius(t);
          const flareU = clamp((along - (exitAlong - flareSpan * 0.25)) / (flareSpan * 1.25), 0, 1);
          const smoothFlare = (1 - flareU) * (1 - flareU) * (1 + 2 * flareU);
          centers[k + 2] = rBase * (1.0 + 0.22 * smoothFlare);
          centers[k + 5] = rBase;

          minY = Math.min(minY, centers[k + 1]);
          maxY = Math.max(maxY, centers[k + 1]);
        }

        for (let j = 0; j <= segments; j++) {
          const k = j * 6, before = Math.max(0, j - 1) * 6, after = Math.min(segments, j + 1) * 6;
          const span = Math.max(.0001, centers[after] - centers[before]);
          centers[k + 3] = (centers[after + 1] - centers[before + 1]) / span;
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
          buffer = { canvas: c, ctx, image, raster: { width: w, height: h, pixels: image.data }, width: w, height: h, colTemp: new Float32Array(h * 4) };
          this.buffers.set(link.id, buffer);
        } else if (!buffer.colTemp || buffer.colTemp.length < h * 4) {
          buffer.colTemp = new Float32Array(h * 4);
        }

        const r = buffer.raster, pixels = r.pixels, colTemp = buffer.colTemp, sampling = scale, sampleCol = this.color;
        const lutSize = Math.round(Math.sqrt(lut.length / 4));
        const maxLutIdx = lutSize - 1, maxLutFloor = lutSize - 2;
        const filteredAlpha = getFilteredAlphaLut(this, renderer);
        pixels.fill(0);
        let segment = 0;

        const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
        const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;
        const isEthereal = (p.mode === 'ethereal');
        const rimIntensity = (.50 + p.rim * .65);
        const irisSat = p.iridescence * p.saturation;
        // Subpixel anti-aliasing half-band in CSS pixels (~0.62 CSS px => 1.24 CSS px total transition width)
        const aaBandCss = Math.max(0.55, 1.35 / sampling);

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
          const half = (rad + aaBandCss) / tx;
          const first = Math.max(1, Math.floor((cy - half - top) * sampling));
          const last = Math.min(r.height - 2, Math.ceil((cy + half - top) * sampling));

          const alongNorm = clamp(along / Math.max(1, totalDist), 0, 1);
          // Pixel-space optical glass wall thickness tw (matches V7 body rim thickness instead of fat 25% fractional radius!)
          const tw = Math.max(1.25, Math.min(3.3, rad * 0.21 * (0.65 + 0.65 * p.thickness)));

          let colHasPixels = false;

          for (let y = first; y <= last; y++) {
            const localY = top + (y + .5) / sampling;
            const transverse = (localY - cy) * tx;
            const distPx = rad - Math.abs(transverse);
            if (distPx <= -aaBandCss) continue;
            const covT = clamp((distPx + aaBandCss) / (2 * aaBandCss), 0, 1);
            const coverage = covT * covT * (3 - 2 * covT);
            if (coverage <= 0.001) continue;

            // Smooth CSS-pixel-normalized body contour weld (zero jagged cutoff teeth!)
            let bodyMask = 1.0;
            let neckGlintFade = 1.0;
            if (hasLiveBody) {
              if (along < 0) continue;
              const sx = link.a.x + along * ux - localY * uy;
              const sy = link.a.y + along * uy + localY * ux;
              const bix = (sx - canvasRect.left) * scaleX;
              const biy = (sy - canvasRect.top) * scaleY;
              if (bix >= 0 && biy >= 0 && bix < bodyMeta.w - 1 && biy < bodyMeta.h - 1) {
                const bxi = bix | 0, byi = biy | 0;
                const bsubx = bix - bxi, bsuby = biy - byi;
                const by0 = byi * bodyMeta.w, by1 = (byi + 1) * bodyMeta.w;
                const da = bodyMeta.dist[by0 + bxi], db = bodyMeta.dist[by0 + bxi + 1];
                const dc = bodyMeta.dist[by1 + bxi], ddVal = bodyMeta.dist[by1 + bxi + 1];
                // Convert HD body canvas distance to true CSS pixels
                const bodyDdCss = ((da * (1 - bsubx) + db * bsubx) * (1 - bsuby) + (dc * (1 - bsubx) + ddVal * bsubx) * bsuby) / Math.max(1, scaleX);
                if (bodyDdCss >= 5.4) continue;
                if (bodyDdCss > 0) {
                  const tM = clamp(1 - bodyDdCss / 5.4, 0, 1);
                  bodyMask = tM * tM * (3 - 2 * tM);
                  const tG = clamp(1 - bodyDdCss / 2.8, 0, 1);
                  neckGlintFade = tG * tG * (3 - 2 * tG);
                }
              }
              const alongT = clamp((along - (exitAlong - rootRadius * 0.25)) / Math.max(6, rootRadius * 0.85), 0, 1);
              neckGlintFade *= (0.28 + 0.72 * (alongT * alongT * (3 - 2 * alongT)));
            }

            const q = Math.max(-1, Math.min(1, transverse / Math.max(0.5, rad)));
            const u = Math.abs(q);
            const nAlong = (-ty * q - tx * slope) / normalLength, nAcross = (tx * q - ty * slope) / normalLength;
            const nz = Math.sqrt(Math.max(0, 1 - q * q)) / normalLength;

            // Parallel-flowing 3D refracted normal (depends on cross-section q and tube tangent, never cutting diagonally across the tube!)
            const nAlongRefr = clamp(nAlong - q * 0.34, -0.92, 0.92);
            const rNx = clamp(ux * nAlongRefr - uy * nAcross, -0.99, 0.99);
            const rNy = clamp(-(uy * nAlongRefr + ux * nAcross), -0.99, 0.99);
            const o = (y * r.width + x) << 2;

            // 1. Sample 5x5 normal-filtered V7 studio LUT at refracted 3D normal (rNx, rNy)
            A.sampleMaterial(lut, lutSize, rNx, rNy, sampleCol);

            // 2. Sample 5x5 normal-filtered V7 per-normal alpha LUT at (rNx, rNy)
            let lutAlpha = 0.22;
            if (filteredAlpha) {
              const lx = clamp((rNx * .5 + .5) * maxLutIdx, 0, maxLutIdx);
              const ly = clamp((rNy * .5 + .5) * maxLutIdx, 0, maxLutIdx);
              const ix = Math.min(maxLutFloor, lx | 0), iy = Math.min(maxLutFloor, ly | 0);
              const fx = lx - ix, fy = ly - iy;
              const ka = iy * lutSize + ix, kb = ka + 1, kc = ka + lutSize, kd = kc + 1;
              lutAlpha = (
                filteredAlpha[ka] * (1 - fx) * (1 - fy) +
                filteredAlpha[kb] * fx * (1 - fy) +
                filteredAlpha[kc] * (1 - fx) * fy +
                filteredAlpha[kd] * fx * fy
              ) / 255;
            }

            // 3. Pixel-space V7 optical glass contour bevel (dd in CSS pixels, matching body's applyGlassSilhouettePass!)
            const dd = Math.max(0, distPx);
            const outerTaper = clamp(dd / Math.max(0.32, tw * 0.20), 0, 1);
            const edge1 = gauss(dd, tw * 0.36, Math.max(0.45, tw * 0.23)) * (0.28 + 0.72 * outerTaper);
            const wallBody = gauss(dd, tw * 0.88, Math.max(0.85, tw * 0.56));
            const wallInner = gauss(dd, tw * 1.85, Math.max(1.10, tw * 0.65));
            const opticalWave = gauss(dd, tw * 2.65, Math.max(1.60, tw * 1.65));

            const toplight = gauss(-rNy, -.72, .49);
            const bottom = gauss(-rNy, .88, .29);
            const side = gauss(Math.abs(rNx), .82, .32);
            const whiteCap = (toplight * (.65 + .35 * gauss(rNx, 0, .75)) + .19 * side + .17 * bottom);

            // Smooth longitudinal dispersion waves that flow parallel to the tube walls
            const waveCyan = 0.55 + 0.45 * Math.cos(alongNorm * 4.2 - rNy * 1.4);
            const wavePink = 0.55 + 0.45 * Math.sin(alongNorm * 3.8 + rNx * 1.6 + 0.9);
            const waveGold = 0.55 + 0.45 * Math.cos(alongNorm * 3.4 + rNy * 1.3 - 0.7);

            const white = clamp((edge1 * 1.04 + wallBody * 0.14) * whiteCap * rimIntensity) * neckGlintFade;
            const blueGlint = (edge1 * 0.78 + wallBody * 0.54 + wallInner * 0.22) * (bottom * 1.35 + toplight * 0.95 * waveCyan) * irisSat * neckGlintFade;
            const pinkGlint = (edge1 * 0.70 + wallBody * 0.56 + wallInner * 0.20) * (side * 1.15 + toplight * 0.80) * wavePink * irisSat * neckGlintFade;
            const goldGlint = (edge1 * 0.60 + wallBody * 0.44) * (toplight * 1.10 * waveGold) * irisSat * neckGlintFade;

            const blueBloom = gauss(rNx, -.35, .60) * gauss(-rNy, -.55, .52) * opticalWave * irisSat * neckGlintFade;
            const pinkBloom = gauss(rNx, .65, .45) * gauss(-rNy, -.64, .42) * opticalWave * irisSat * neckGlintFade;
            const warmBloom = gauss(rNx, -.72, .40) * gauss(-rNy, -.60, .45) * opticalWave * irisSat * neckGlintFade;

            const addR = 235 * white + blueGlint * accentCool[0] * .74 + pinkGlint * accentMagenta[0] * .90 + goldGlint * accentWarm[0] * .64 + blueBloom * accentCool[0] * 1.40 + pinkBloom * accentMagenta[0] * 1.50 + warmBloom * accentWarm[0] * 1.05;
            const addG = 244 * white + blueGlint * accentCool[1] * .74 + pinkGlint * accentMagenta[1] * .90 + goldGlint * accentWarm[1] * .64 + blueBloom * accentCool[1] * 1.40 + pinkBloom * accentMagenta[1] * 1.50 + warmBloom * accentWarm[1] * 1.05;
            const addB = 253 * white + blueGlint * accentCool[2] * .74 + pinkGlint * accentMagenta[2] * .90 + goldGlint * accentWarm[2] * .64 + blueBloom * accentCool[2] * 1.40 + pinkBloom * accentMagenta[2] * 1.50 + warmBloom * accentWarm[2] * 1.05;

            // Keep the tube core crystal-clear and calm like the center of the avatar body, while reflections intensify smoothly toward the curved glass walls
            const coreCalm = 0.44 + 0.56 * Math.pow(u, 1.45);
            const depthCavity = wallInner * .10 * (1 - p.transmission);
            const coreScale = (isEthereal ? (1.0 - 0.55 * p.transmission) : (1.0 - depthCavity)) * coreCalm;

            pixels[o]     = Math.min(255, Math.max(0, sampleCol[0] * coreScale + addR));
            pixels[o + 1] = Math.min(255, Math.max(0, sampleCol[1] * coreScale + addG));
            pixels[o + 2] = Math.min(255, Math.max(0, sampleCol[2] * coreScale + addB));

            const bevelAlpha = clamp(white * 1.05 + blueGlint * .70 + pinkGlint * .66 + goldGlint * .56 + blueBloom * .75 + pinkBloom * .68 + warmBloom * .58, 0, 1);
            const baseAlpha = (isEthereal ? lutAlpha * 0.52 : lutAlpha) * (0.65 + 0.35 * coreCalm);
            const totAlpha = clamp(Math.max(baseAlpha, bevelAlpha), 0.04, 0.96);

            pixels[o + 3] = Math.round(coverage * bodyMask * 255 * totAlpha);
            colHasPixels = true;
          }

          // 1D transverse [1, 2, 1]/4 premultiplied anti-aliasing filter across y eliminates diagonal rotation staircase teeth
          if (colHasPixels && last - first >= 2) {
            const yStart = Math.max(1, first);
            const yEnd = Math.min(r.height - 2, last);
            for (let y = yStart; y <= yEnd; y++) {
              const o = (y * r.width + x) << 2;
              const a = pixels[o + 3];
              const ti = y << 2;
              colTemp[ti]     = pixels[o]     * a;
              colTemp[ti + 1] = pixels[o + 1] * a;
              colTemp[ti + 2] = pixels[o + 2] * a;
              colTemp[ti + 3] = a;
            }
            for (let y = yStart; y <= yEnd; y++) {
              const ym1 = Math.max(yStart, y - 1) << 2;
              const y0  = y << 2;
              const yp1 = Math.min(yEnd, y + 1) << 2;
              const outA = (colTemp[ym1 + 3] + 2 * colTemp[y0 + 3] + colTemp[yp1 + 3]) * 0.25;
              const o = (y * r.width + x) << 2;
              if (outA >= 1.0) {
                const invA = 1 / outA;
                pixels[o]     = Math.min(255, ((colTemp[ym1]     + 2 * colTemp[y0]     + colTemp[yp1])     * 0.25) * invA);
                pixels[o + 1] = Math.min(255, ((colTemp[ym1 + 1] + 2 * colTemp[y0 + 1] + colTemp[yp1 + 1]) * 0.25) * invA);
                pixels[o + 2] = Math.min(255, ((colTemp[ym1 + 2] + 2 * colTemp[y0 + 2] + colTemp[yp1 + 2]) * 0.25) * invA);
                pixels[o + 3] = Math.round(outA);
              } else {
                pixels[o] = pixels[o + 1] = pixels[o + 2] = pixels[o + 3] = 0;
              }
            }
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
