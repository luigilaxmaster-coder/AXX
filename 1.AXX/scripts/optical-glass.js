(() => {
  'use strict';

  const A = window.Axx;
  if (!A || !A.SoftwareRenderer) return;

  const proto = A.SoftwareRenderer.prototype;
  if (proto.__axxOpticalGlass) return;

  const PRESETS = {
    reference: { transmission: .85, ior: 1.48, thickness: .50, roughness: .035, iridescence: .75, rim: .80, saturation: .80, exposure: 1.05, envBoost: 1.15, aurora: .55, mode: 'glass' },
    crystal:   { transmission: .60, ior: 1.72, thickness: .85, roughness: .018, iridescence: .95, rim: .95, saturation: .90, exposure: 1.25, envBoost: 1.35, aurora: .70, mode: 'crystal' },
    liquid:    { transmission: .92, ior: 1.33, thickness: .30, roughness: .080, iridescence: .45, rim: .60, saturation: .65, exposure: .95,  envBoost: 1.00, aurora: .40, mode: 'liquid' },
    silica:    { transmission: .75, ior: 1.45, thickness: .60, roughness: .025, iridescence: .60, rim: .70, saturation: .70, exposure: 1.00, envBoost: 1.10, aurora: .45, mode: 'silica' },
    aura:      { transmission: .80, ior: 1.60, thickness: .65, roughness: .030, iridescence: 1.0, rim: .90, saturation: 1.0, exposure: 1.15, envBoost: 1.40, aurora: .90, mode: 'aura' },
    ethereal:  { transmission: .98, ior: 1.50, thickness: .20, roughness: .020, iridescence: .85, rim: 1.00, saturation: .85, exposure: 1.10, envBoost: 1.25, aurora: .75, mode: 'ethereal' }
  };

  const STORAGE_KEY = 'axx_optical_glass_params';
  let p = { ...PRESETS.reference };
  let color = '';

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        p = { ...p, ...parsed };
        if (typeof parsed.color === 'string') color = parsed.color;
      }
    }
  } catch (_) {}

  const clamp = (v, min = 0, max = 1) => Math.max(min, Math.min(max, v));
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const norm = v => { const l = Math.hypot(...v) || 1; return v.map(x => x / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

  let panel = null;
  const inputs = new Map();

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...p, color }));
    } catch (_) {}
  }

  function set(updates) {
    if (updates.preset && PRESETS[updates.preset]) {
      p = { ...p, ...PRESETS[updates.preset] };
    }
    for (const k of ['transmission', 'ior', 'thickness', 'roughness', 'iridescence', 'rim', 'saturation', 'exposure', 'envBoost', 'aurora']) {
      if (typeof updates[k] === 'number' && !Number.isNaN(updates[k])) {
        p[k] = updates[k];
      }
    }
    if (typeof updates.color === 'string') {
      color = updates.color;
    }
    if (typeof updates.mode === 'string') {
      p.mode = updates.mode;
    }
    persist();
    sync();
    const r = A.app?.renderer;
    if (r) {
      r.lutKey = '';
    }
    const companion = A.app?.companion;
    const tendrils = companion?.experience?.tendrils || companion?.delivery || A.app?.tendrils;
    if (tendrils && tendrils.buffers) {
      tendrils.buffers.clear();
      tendrils.filteredMaterial = null;
    }
    r?.draw?.(0);
  }

  function getPaletteAccents(paletteIdx, customColor) {
    const palette = A.PALETTES[paletteIdx] || A.PALETTES[0];
    const fromHex = hex => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
    const cool = fromHex(palette.colors[1]), warm = fromHex(palette.colors[3]), magenta = fromHex(palette.colors[2]);
    const custom = /^#[0-9a-fA-F]{6}$/.test(customColor) ? fromHex(customColor) : null;
    const tintBlend = custom ? clamp(0.72, 0, 1) : 0;
    const blendRGB = col => col.map((v, i) => v * (1 - tintBlend) + (custom ? custom[i] : v) * tintBlend);
    return {
      cool: blendRGB(cool),
      warm: blendRGB(warm),
      magenta: blendRGB(magenta)
    };
  }

  // --- 1. SHADE TABLE (Full V7 Optical Glass Studio Illumination) ---
  const originalShadeTable = proto.shadeTable;
  proto.shadeTable = function opticalGlassShadeTable() {
    if (this.finish !== 'opticalglass') {
      return originalShadeTable.call(this);
    }

    const palIdx = this.settings?.palette ?? 0;
    const cacheKey = `opticalglass/${palIdx}/${color}/${p.ior.toFixed(2)}/${p.roughness.toFixed(3)}/${p.iridescence.toFixed(2)}/${p.rim.toFixed(2)}/${p.saturation.toFixed(2)}/${p.exposure.toFixed(2)}/${p.thickness.toFixed(2)}/${p.transmission.toFixed(2)}/${(p.envBoost || 1).toFixed(2)}/${(p.aurora || .5).toFixed(2)}/${p.mode || 'glass'}`;

    if (this.lutKey === cacheKey && this.lut) return;

    const width = 512;
    if (!this.lut || this.lut.length !== width * width * 4) {
      this.lut = new Uint8ClampedArray(width * width * 4);
    }
    const lut = this.lut;
    const pal = A.PALETTES[palIdx] || A.PALETTES[0];

    const decodeColor = hex => {
      const n = parseInt(hex.slice(1), 16);
      return [Math.pow(((n >> 16) & 255) / 255, 2.2), Math.pow(((n >> 8) & 255) / 255, 2.2), Math.pow((n & 255) / 255, 2.2)];
    };

    const palette = pal.colors.map(decodeColor);
    if (/^#[0-9a-fA-F]{6}$/.test(color)) {
      const user = decodeColor(color);
      const str = 0.65;
      for (const channel of palette) {
        for (let i = 0; i < 3; i++) channel[i] = channel[i] * (1 - str) + user[i] * str;
      }
    }

    const customTint = /^#[0-9a-fA-F]{6}$/.test(color) ? color : '';
    const tintV = customTint ? [parseInt(customTint.slice(1, 3), 16) / 255, parseInt(customTint.slice(3, 5), 16) / 255, parseInt(customTint.slice(5, 7), 16) / 255] : null;

    const w = .028 + p.roughness * .32;
    const cards = [
      { dir: [-.64, .80, .60], size: [.17, .57], feather: w * 2.3, color: [1.35, 1.48, 1.75] },
      { dir: [-.81, .74, .40], size: [.022, .53], feather: w * .62, color: [2.0, 2.12, 2.3] },
      { dir: [.15, .79, 1], size: [.52, .20], feather: w * 2.0, color: [.012, .019, .034] },
      { dir: [.87, .46, .48], size: [.055, .67], feather: w * 1.4, color: [1.2, 1.4, 1.65] },
      { dir: [-.25, 1, -.22], size: [.78, .026], feather: w * .8, color: [2, 2.16, 2.35] },
      { dir: [-1, -.06, .04], size: [.25, .81], feather: w * 2.1, color: palette[0].map(n => n * 2.1) },
      { dir: [-.61, -.53, .94], size: [.075, .57], feather: w * 1.2, color: palette[0].map(n => n * .80) },
      { dir: [.66, .16, .76], size: [.055, .44], feather: w * .85, color: palette[2].map(n => n * .70) },
      { dir: [-.34, -.91, .35], size: [.48, .085], feather: w * 1.3, color: palette[1].map(n => n * .95) },
      { dir: [.77, 0, -.72], size: [.14, .78], feather: w * 1.4, color: palette[2].map(n => n * 1.8) },
      { dir: [.98, -.20, .43], size: [.045, .67], feather: w * .85, color: palette[3].map(n => n * 1.9) },
      { dir: [-.63, -.37, -.62], size: [.078, .62], feather: w * 1.5, color: [.36, .40, .48] },
      { dir: [.30, -.63, -.72], size: [.56, .075], feather: w, color: [.26, .33, .46] }
    ];

    const preparedCards = cards.map(card => {
      const d = norm(card.dir);
      const r = norm(cross([0, 1, .02], d));
      const u = cross(d, r);
      return { ...card, dir: d, right: r, up: u };
    });

    const keydir = norm([-.64, .8, .6]);
    const forward = norm([.1, .12, 1]);
    const envBoost = p.envBoost || 1.15;
    const aurora = p.aurora || 0.55;

    const film = [0, 2.094395, 4.18879];
    const specPhase = [0, -2.094395, 2.094395];

    for (let j = 0; j < width; j++) {
      const ny = j / 511 * 2 - 1;
      const rowOffset = j * width * 4;

      for (let i = 0; i < width; i++) {
        const nx = i / 511 * 2 - 1;
        const nxy2 = nx * nx + ny * ny;
        const o = rowOffset + (i << 2);

        if (nxy2 > 1.0) {
          lut[o] = 0;
          lut[o + 1] = 0;
          lut[o + 2] = 0;
          lut[o + 3] = 255;
          continue;
        }

        const nz = Math.sqrt(Math.max(0.000001, 1.0 - nxy2));
        const rx = 2 * nx * nz, ry = 2 * ny * nz, rz = 2 * nz * nz - 1;

        const top = Math.pow(Math.max(0, ry * .5 + .5), 1.4);
        const g = Math.pow(Math.max(rx * keydir[0] + ry * keydir[1] + rz * keydir[2], 0), 18);
        const ambient = Math.pow(Math.max(rx * forward[0] + ry * forward[1] + rz * forward[2], 0), 5);
        const fres = Math.pow(1 - nz, 5);

        let cr = .002 + .009 * top + .009 * ambient + .06 * g;
        let cg = .003 + .013 * top + .012 * ambient + .085 * g;
        let cb = .005 + .021 * top + .019 * ambient + .12 * g;

        for (let c = 0; c < preparedCards.length; c++) {
          const card = preparedCards[c];
          const facing = rx * card.dir[0] + ry * card.dir[1] + rz * card.dir[2];
          if (facing <= 0) continue;
          const invF = 1 / facing;
          const qx = Math.abs((rx * card.right[0] + ry * card.right[1] + rz * card.right[2]) * invF);
          const qy = Math.abs((rx * card.up[0] + ry * card.up[1] + rz * card.up[2]) * invF);
          const s0 = card.size[0], f0 = card.feather, s1 = card.size[1];
          if (qx > s0 + f0 || qy > s1 + f0) continue;
          const mask = (1 - smooth(s0 - f0, s0 + f0, qx)) * (1 - smooth(s1 - f0, s1 + f0, qy));
          cr += card.color[0] * mask;
          cg += card.color[1] * mask;
          cb += card.color[2] * mask;
        }

        const base = [cr, cg, cb];
        const grazing = clamp(1 - nz, 0, 1);
        const edge = Math.pow(grazing, 1.32);
        const f0 = Math.pow((p.ior - 1) / (p.ior + 1), 2);
        const fresnel = f0 + (1 - f0) * Math.pow(grazing, 5);
        const highlightPower = 9 + 30 * (1 - p.roughness / .48);

        const whiteWide = Math.pow(Math.max(0, .45 + ny * .59 - nx * .16), 4.8);
        const upperBox  = Math.pow(Math.max(0, .29 + ny * .76 + nz * .28 - nx * .18), highlightPower * .31);
        const sideBox   = Math.pow(Math.max(0, .25 - nx * .80 + ny * .14 + nz * .12), highlightPower * .22);
        const glint     = Math.pow(Math.max(0, .17 + ny * .72 - nx * .25 + nz * .27), highlightPower * .76);
        const bottomBox = Math.pow(Math.max(0, -ny * .84 + nx * .11 + .13), 4.3);

        const phase = Math.atan2(ny, nx) * 2.7 + nx * 4.2 - ny * 3.1;
        const opticalPhase = phase + (1 - nz) * 7.5 * (.25 + p.ior * .30);

        for (let k = 0; k < 3; k++) {
          const filmVal = .5 + .5 * Math.cos(film[k] + (1 - nz) * 10.7);
          const tint = .72 + (.16 + .20 * fres) * filmVal;
          const accent = palette[Math.min(3, k)][k];
          const tintR = tintV ? (tintV[k] * tintV[k]) : accent;

          const spectrum = .5 + .5 * Math.cos(opticalPhase * (.68 + .8 * p.iridescence) + specPhase[k]);
          const iris = spectrum * (.09 + .28 * p.iridescence) * edge * p.iridescence * p.saturation * aurora;
          const reflection = base[k] * (.12 + .40 * edge + .14 * fresnel) * envBoost;
          const neutralRim = (.17 + .57 * p.rim) * Math.pow(grazing, .65) * (.80 + .24 * p.thickness);
          const whiteCoat = (upperBox * .43 + whiteWide * .15 + sideBox * .31 + glint * .84 + bottomBox * .18) * (.46 + .55 * p.rim) * (1 - p.roughness * .57);

          const transmissionBody = (.009 + .065 * tintR + .012 * spectrum) * p.transmission * (1 - .58 * edge) * (.9 + .4 * p.thickness);
          const absorption = Math.exp(-p.thickness * (.23 + .48 * tintR) * (1 + .62 * edge));
          const chroma = iris * (.12 + .58 * tintR + .26 * spectrum);
          const glassBase = (transmissionBody + chroma + reflection * .46) * absorption;
          const clear = glassBase + neutralRim * .34 + whiteCoat * (k === 0 ? .88 : k === 1 ? .92 : 1.04);
          const chromeReflection = base[k] * tint * (.58 + .56 * edge) * (1 - p.roughness * .48);

          let value = chromeReflection + clear * .54 + fresnel * .18 * base[k];
          if (p.mode === 'crystal') value += Math.pow(Math.abs(Math.sin(phase * 3.6)), 22) * edge * .15;
          if (p.mode === 'aura')    value += spectrum * .18 * edge * p.saturation;

          value *= p.exposure;
          const mapped = clamp((value * (2.51 * value + .03)) / (value * (2.43 * value + .59) + .14), 0, 1);
          lut[o + k] = Math.round(255 * Math.pow(mapped, 1 / 2.2));
        }
        lut[o + 3] = 255;
      }
    }

    this.lutKey = cacheKey;
  };

  // --- 2. MULTI-LAYER SILHOUETTE PASS (Volumetric Glass Body) ---
  const gauss = (v, target, spread) => Math.exp(-Math.pow(v - target, 2) / (spread * spread));

  function applyGlassSilhouettePass(renderer) {
    const raster = renderer.raster;
    const img = renderer.image;
    if (!raster || !img || !renderer.ctx) return;

    const w = raster.width, h = raster.height;
    const cov = raster.coverage;
    if (!cov) return;

    const sw = w >> 1, sh = h >> 1;
    if (sw < 4 || sh < 4) return;

    const mask = new Uint8Array(sw * sh);
    const dist = new Float32Array(sw * sh);
    dist.fill(1e4);

    let xmin = sw, xmax = 0, ymin = sh, ymax = 0;
    for (let y = 0; y < sh; y++) {
      const srcRow = (y * 2) * w;
      const dstRow = y * sw;
      for (let x = 0; x < sw; x++) {
        if (cov[srcRow + (x * 2)] > 16) {
          mask[dstRow + x] = 1;
          dist[dstRow + x] = 0;
          if (x < xmin) xmin = x;
          if (x > xmax) xmax = x;
          if (y < ymin) ymin = y;
          if (y > ymax) ymax = y;
        }
      }
    }
    if (xmax <= xmin || ymax <= ymin) return;

    for (let y = 1; y < sh - 1; y++) {
      for (let x = 1; x < sw - 1; x++) {
        const i = y * sw + x;
        if (!mask[i]) continue;
        dist[i] = Math.min(dist[i], dist[i - 1] + 1, dist[i - sw] + 1, dist[i - sw - 1] + 1.4, dist[i - sw + 1] + 1.4);
      }
    }
    for (let y = sh - 2; y >= 1; y--) {
      for (let x = sw - 2; x >= 1; x--) {
        const i = y * sw + x;
        if (!mask[i]) continue;
        dist[i] = Math.min(dist[i], dist[i + 1] + 1, dist[i + sw] + 1, dist[i + sw + 1] + 1.4, dist[i + sw - 1] + 1.4);
      }
    }

    const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
    const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;

    const rx = Math.max(10, xmax - xmin), ry = Math.max(10, ymax - ymin);
    const cx = (xmin + xmax) * .5, cy = (ymin + ymax) * .5;
    const tw = Math.max(2.7, Math.min(10, rx * .018 * (.65 + .65 * p.thickness)));
    const pix = img.data;

    const activeRoots = [];
    if (renderer.__activeTendrilRoots && renderer.canvas) {
      const cr = renderer.canvas.getBoundingClientRect();
      const scaleX = w / Math.max(1, cr.width), scaleY = h / Math.max(1, cr.height);
      for (let rIdx = 0; rIdx < renderer.__activeTendrilRoots.length; rIdx++) {
        const ar = renderer.__activeTendrilRoots[rIdx];
        activeRoots.push({
          cx: (ar.x - cr.left) * scaleX,
          cy: (ar.y - cr.top) * scaleY,
          cRad: ar.radius * scaleX
        });
      }
    }

    const yStart = Math.max(2, (ymin - 2) * 2), yEnd = Math.min(h - 2, (ymax + 3) * 2);
    const xStart = Math.max(2, (xmin - 2) * 2), xEnd = Math.min(w - 2, (xmax + 3) * 2);

    for (let y = yStart; y < yEnd; y++) {
      const ym = (y * .5 - cy) / ry * 2;
      const toplight = gauss(ym, -.74, .49);
      const bottom = gauss(ym, .91, .26);
      const row = y * w;

      for (let x = xStart; x < xEnd; x++) {
        const idx = row + x, cover = cov[idx] / 255;
        if (cover < .008) continue;
        const pIdx = idx * 4;

        const x2 = x * .5, y2 = y * .5, xi = x2 | 0, yi = y2 | 0;
        const sub = x2 - xi, suby = y2 - yi;
        const yi0 = Math.min(sh - 1, yi) * sw, yi1 = Math.min(sh - 1, yi + 1) * sw;
        const xi0 = Math.min(sw - 1, xi), xi1 = Math.min(sw - 1, xi + 1);
        const a = dist[yi0 + xi0], b = dist[yi0 + xi1], c_d = dist[yi1 + xi0], d = dist[yi1 + xi1];
        const dd = (a * (1 - sub) + b * sub) * (1 - suby) + (c_d * (1 - sub) + d * sub) * suby;

        const xn = (x2 - cx) / rx * 2;
        const side = gauss(Math.abs(xn), .88, .29);
        const topGold = gauss(xn, -.70, .43) * toplight;
        const pink = gauss(xn, .70, .44) * toplight;
        const cyan = gauss(xn, -.22, .44) * toplight;
        const whiteCap = (toplight * (.65 + .38 * gauss(xn, 0, .75)) + .19 * side + .17 * bottom);

        const width = tw * (1 + .42 * toplight + .07 * side);
        const edge1 = gauss(dd, width * .26, Math.max(1.2, width * .23));
        const body = gauss(dd, width * .76, Math.max(2.2, width * .66));
        const inner = gauss(dd, width * 1.9, Math.max(1.6, width * .45));
        const rimIntensity = (.48 + p.rim * .65);

        let tendrilDamp = 1.0;
        if (activeRoots.length > 0) {
          for (let rIdx = 0; rIdx < activeRoots.length; rIdx++) {
            const ar = activeRoots[rIdx];
            const distToRoot = Math.hypot(x - ar.cx, y - ar.cy);
            if (distToRoot < ar.cRad * 2.5) {
              const d = clamp((distToRoot - ar.cRad * 0.35) / (ar.cRad * 1.6), 0, 1);
              tendrilDamp = Math.min(tendrilDamp, d * d * (3 - 2 * d));
            }
          }
        }

        const white = clamp((edge1 * 1.10 + body * .26 + inner * .08) * whiteCap * rimIntensity * .95) * tendrilDamp;
        const blueGlint = (edge1 * .82 + body * .50 + inner * .18) * (cyan * 1.50 + bottom * 1.15 + gauss(xn, .85, .35) * .28) * p.iridescence * p.saturation * tendrilDamp;
        const pinkGlint = (edge1 * .72 + body * .52) * pink * p.iridescence * p.saturation * tendrilDamp;
        const goldGlint = (edge1 * .62 + body * .46) * (topGold + gauss(xn, -.95, .36) * .19) * p.iridescence * p.saturation * tendrilDamp;

        const depthCavity = inner * .14 * (1 - p.transmission * .8);

        const opticalWave = gauss(dd, width * 2.65, Math.max(3, width * 2.20));
        const blueBloom = gauss(xn, -.35, .60) * gauss(ym, -.55, .52) * opticalWave * p.iridescence * p.saturation;
        const pinkBloom = gauss(xn, .68, .41) * gauss(ym, -.66, .37) * opticalWave * p.iridescence * p.saturation;
        const warmBloom = gauss(xn, -.76, .36) * gauss(ym, -.62, .43) * opticalWave * p.iridescence * p.saturation;

        const addR = (235 * white + blueGlint * accentCool[0] * .70 + pinkGlint * accentMagenta[0] * .85 + goldGlint * accentWarm[0] * .60 + blueBloom * accentCool[0] * 1.9 + pinkBloom * accentMagenta[0] * 2.0 + warmBloom * accentWarm[0] * 1.35) * cover;
        const addG = (244 * white + blueGlint * accentCool[1] * .70 + pinkGlint * accentMagenta[1] * .85 + goldGlint * accentWarm[1] * .60 + blueBloom * accentCool[1] * 1.9 + pinkBloom * accentMagenta[1] * 2.0 + warmBloom * accentWarm[1] * 1.35) * cover;
        const addB = (253 * white + blueGlint * accentCool[2] * .70 + pinkGlint * accentMagenta[2] * .85 + goldGlint * accentWarm[2] * .60 + blueBloom * accentCool[2] * 1.9 + pinkBloom * accentMagenta[2] * 2.0 + warmBloom * accentWarm[2] * 1.35) * cover;

        pix[pIdx] = Math.min(255, Math.max(0, pix[pIdx] * (1 - depthCavity) + addR));
        pix[pIdx + 1] = Math.min(255, Math.max(0, pix[pIdx + 1] * (1 - depthCavity) + addG));
        pix[pIdx + 2] = Math.min(255, Math.max(0, pix[pIdx + 2] * (1 - depthCavity) + addB));

        const grazing = clamp(1.0 - dd / (width * 1.8), 0.0, 1.0) * tendrilDamp;
        const isEthereal = (p.mode === 'ethereal');
        const baseAlpha = isEthereal
          ? (0.05 + 0.12 * p.thickness + 0.20 * (1.0 - p.transmission)) + (0.35 + 0.25 * p.thickness) * Math.pow(grazing, 0.70)
          : (0.75 + 0.15 * (1.0 - p.transmission)) + (0.25 + 0.20 * p.thickness) * Math.pow(grazing, 0.70);
        const specAlpha = clamp(white * 1.15 + (blueGlint + pinkGlint + goldGlint) * 0.75 + (blueBloom + pinkBloom + warmBloom) * 0.65);
        const totAlpha = clamp(baseAlpha + specAlpha * (1.0 - baseAlpha), 0.05, 1.0);
        pix[pIdx + 3] = Math.round(255 * totAlpha * cover);
      }
    }

    renderer.ctx.putImageData(renderer.image, 0, 0);
  }

  const originalDraw = proto.draw;
  proto.draw = function opticalGlassDraw(timeSeconds) {
    if (originalDraw) originalDraw.call(this, timeSeconds);
    if (this.finish === 'opticalglass' && this.ctx && this.image && this.raster) {
      applyGlassSilhouettePass(this);
    }
  };

  // --- 3. SEAMLESS ORGANIC TENDRIL INTEGRATION ---
  if (A.OrganicTendrils) {
    const origTendrilDraw = A.OrganicTendrils.prototype.draw;
    if (origTendrilDraw) {
      A.OrganicTendrils.prototype.draw = function opticalTendrilDraw(links, phase, lut, view, renderer) {
        if (renderer && renderer.finish === 'opticalglass' && Array.isArray(links)) {
          const rect = renderer.canvas?.getBoundingClientRect();
          const raster = renderer.raster;
          const opaque = rect?.width && rect?.height && raster ? (x, y) => {
            const px = Math.floor((x - rect.left) * raster.width / rect.width);
            const py = Math.floor((y - rect.top) * raster.height / rect.height);
            return px >= 0 && py >= 0 && px < raster.width && py < raster.height && raster.pixels[(py * raster.width + px) * 4 + 3] > 128;
          } : null;

          const roots = [];
          for (let lIdx = 0; lIdx < links.length; lIdx++) {
            const raw = links[lIdx];
            const fitted = A.fitTendrilLink(raw, opaque, rect ? Math.hypot(rect.width, rect.height) * .5 : 0);
            if (fitted && fitted.a && Number.isFinite(fitted.rootRadius)) {
              roots.push({
                x: fitted.a.x,
                y: fitted.a.y,
                radius: fitted.rootRadius
              });
            }
          }
          renderer.__activeTendrilRoots = roots;
        }
        return origTendrilDraw.call(this, links, phase, lut, view, renderer);
      };
    }

    const origTendrilRender = A.OrganicTendrils.prototype.render;
    if (origTendrilRender) {
      A.OrganicTendrils.prototype.render = function opticalTendrilRender(links, phase, lut, view, renderer) {
        if (renderer && renderer.finish === 'opticalglass') {
          const rect = renderer.canvas?.getBoundingClientRect();
          const raster = renderer.raster;
          const opaque = rect?.width && rect?.height && raster ? (x, y) => {
            const px = Math.floor((x - rect.left) * raster.width / rect.width);
            const py = Math.floor((y - rect.top) * raster.height / rect.height);
            return px >= 0 && py >= 0 && px < raster.width && py < raster.height && raster.pixels[(py * raster.width + px) * 4 + 3] > 128;
          } : null;

          const roots = [];
          if (Array.isArray(links)) {
            for (let lIdx = 0; lIdx < links.length; lIdx++) {
              const raw = links[lIdx];
              const fitted = A.fitTendrilLink(raw, opaque, rect ? Math.hypot(rect.width, rect.height) * .5 : 0);
              if (fitted && fitted.a && Number.isFinite(fitted.rootRadius)) {
                roots.push({
                  x: fitted.a.x,
                  y: fitted.a.y,
                  radius: fitted.rootRadius
                });
              }
            }
          }
          renderer.__activeTendrilRoots = roots;
        } else if (renderer) {
          renderer.__activeTendrilRoots = null;
        }
        return origTendrilRender.call(this, links, phase, lut, view, renderer);
      };
    }

    const origTube = A.OrganicTendrils.prototype.tube;
    if (origTube) {
      A.OrganicTendrils.prototype.tube = function opticalGlassTube(link, phase, lut, view) {
        const renderer = A.app?.renderer;
        if (!renderer || renderer.finish !== 'opticalglass') {
          return origTube.call(this, link, phase, lut, view);
        }

        const pVal = Math.max(0, Math.min(1, link.progress)), route = document.body.classList.contains('a11-action-mode');
        const point = (t) => {
          const q = A.organicCurve(link.a, link.b, t, phase);
          if (route) q.x += A.actionArmOffset(link.a, link.b, t, this.width);
          return q;
        };
        const end = point(pVal);
        const dx = link.b.x - link.a.x, dy = link.b.y - link.a.y, fullLength = Math.hypot(dx, dy);
        if (!Number.isFinite(fullLength) || fullLength < 1) return;
        const ux = dx / fullLength, uy = dy / fullLength;
        const totalDist = Math.hypot(end.x - link.a.x, end.y - link.a.y);
        const rootRadius = Math.min(link.rootRadius, 24 * A.OrganicTendrils.thickness, Math.max(1, totalDist * .2));
        const radius = t => A.flowArmRadius(t, totalDist) * rootRadius / 24 * Math.sqrt(pVal);

        const segments = Math.min(1024, Math.max(64, Math.ceil(totalDist / 2)));
        const centers = new Float32Array((segments + 1) * 5);
        let minY = 0, maxY = 0;
        for (let j = 0; j <= segments; j++) {
          const t = j / segments, q = point(t * pVal), x = q.x - link.a.x, y = q.y - link.a.y;
          const k = j * 5;
          centers[k] = x * ux + y * uy;
          centers[k + 1] = -x * uy + y * ux;
          centers[k + 2] = radius(t);
          minY = Math.min(minY, centers[k + 1]); maxY = Math.max(maxY, centers[k + 1]);
        }
        for (let j = 0; j <= segments; j++) {
          const k = j * 5, before = Math.max(0, j - 1) * 5, after = Math.min(segments, j + 1) * 5;
          const span = Math.max(.0001, centers[after] - centers[before]);
          centers[k + 3] = (centers[after + 1] - centers[before + 1]) / span;
          centers[k + 4] = (centers[after + 2] - centers[before + 2]) / span;
          const projectedRadius = centers[k + 2] * Math.sqrt(1 + centers[k + 3] * centers[k + 3]);
          minY = Math.min(minY, centers[k + 1] - projectedRadius);
          maxY = Math.max(maxY, centers[k + 1] + projectedRadius);
        }

        const pad = Math.ceil(rootRadius * 1.6 + 6), left = -pad, top = Math.floor(minY - 4);
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
        const r = buffer.raster, pixels = r.pixels, sampling = scale, color = this.color;
        const lutSize = Math.round(Math.sqrt(lut.length / 4));
        pixels.fill(0);
        let segment = 0;

        const rootTransition = Math.max(10, rootRadius * 1.8);
        const glassTransmission = p.transmission;
        const glassThickness = p.thickness;
        const glassRim = p.rim;

        const accents = getPaletteAccents(renderer.settings?.palette ?? 0, color);
        const accentCool = accents.cool, accentWarm = accents.warm, accentMagenta = accents.magenta;
        const isEthereal = (p.mode === 'ethereal');

        for (let x = Math.max(0, Math.floor(-left * sampling)); x < r.width; x++) {
          const along = left + (x + .5) / sampling;
          if (along > centers[segments * 5]) break;
          while (segment < segments - 1 && centers[(segment + 1) * 5] < along) segment++;
          const k = segment * 5, span = centers[k + 5] - centers[k];
          if (span <= .0001) continue;
          const f = Math.max(0, Math.min(1, (along - centers[k]) / span));
          const cy = centers[k + 1] * (1 - f) + centers[k + 6] * f;
          let rad = centers[k + 2] * (1 - f) + centers[k + 7] * f;
          if (rad < .0001) continue;

          // Smooth trumpet flare at the base merging seamlessly into the body volume
          const rootT = clamp(along / rootTransition, 0, 1);
          const flare = 1.0 + 0.42 * Math.pow(1.0 - rootT, 2.0);
          rad *= flare;

          // Smooth dissolve inside the body volume: zero hard truncated cylinder edge
          const smoothFade = rootT * rootT * (3.0 - 2.0 * rootT);

          const tangent = centers[k + 3] * (1 - f) + centers[k + 8] * f;
          const inv = 1 / Math.sqrt(1 + tangent * tangent), tx = inv, ty = tangent * inv;
          const slope = (centers[k + 4] * (1 - f) + centers[k + 9] * f) * inv;
          const normalLength = Math.sqrt(1 + slope * slope);
          const half = rad / tx, first = Math.max(0, Math.floor((cy - half - top) * sampling - 1));
          const last = Math.min(r.height - 1, Math.ceil((cy + half - top) * sampling + 1));

          for (let y = first; y <= last; y++) {
            const transverse = (top + (y + .5) / sampling - cy) * tx;
            const coverage = Math.max(0, Math.min(1, (rad - Math.abs(transverse)) * sampling + .5));
            if (!coverage) continue;
            const q = Math.max(-1, Math.min(1, transverse / rad));
            const nAlong = (-ty * q - tx * slope) / normalLength, nAcross = (tx * q - ty * slope) / normalLength;
            const nx = ux * nAlong - uy * nAcross, ny = -(uy * nAlong + ux * nAcross);
            const nz = Math.sqrt(Math.max(0, 1 - q * q)) / normalLength;
            const o = (y * r.width + x) * 4;

            A.sampleMaterial(lut, lutSize, nx, ny, color);

            const grazing = clamp(1.0 - nz, 0.0, 1.0);
            const toplight = Math.max(0.0, -ny);
            const side = Math.abs(nx);

            const whiteGlint = Math.pow(grazing, 2.4) * (0.60 + 0.40 * toplight) * glassRim;
            const blueGlint = Math.pow(grazing, 3.2) * (0.45 + 0.55 * Math.max(0.0, ny)) * p.iridescence * p.saturation;
            const pinkGlint = Math.pow(grazing, 3.6) * (0.35 + 0.65 * side) * p.iridescence * p.saturation;
            const goldGlint = Math.pow(grazing, 2.8) * (0.40 + 0.60 * toplight) * p.iridescence * p.saturation;

            const addR = whiteGlint * 235 + blueGlint * accentCool[0] * 0.70 + pinkGlint * accentMagenta[0] * 0.85 + goldGlint * accentWarm[0] * 0.60;
            const addG = whiteGlint * 244 + blueGlint * accentCool[1] * 0.70 + pinkGlint * accentMagenta[1] * 0.85 + goldGlint * accentWarm[1] * 0.60;
            const addB = whiteGlint * 253 + blueGlint * accentCool[2] * 0.70 + pinkGlint * accentMagenta[2] * 0.85 + goldGlint * accentWarm[2] * 0.60;

            if (isEthereal) {
              // Ethereal Glass: sheer floating outline look with transparent center void
              const baseAlpha = (0.05 + 0.10 * glassThickness + 0.16 * (1.0 - glassTransmission)) + (0.35 + 0.25 * glassThickness) * Math.pow(grazing, 0.75);
              const specAlpha = clamp(whiteGlint * 1.15 + (blueGlint + pinkGlint + goldGlint) * 0.75, 0.0, 1.0);
              const totAlpha = clamp(baseAlpha + specAlpha * (1.0 - baseAlpha), 0.05, 1.0);
              const cavityDamp = (1.0 - 0.75 * glassTransmission);

              pixels[o]     = Math.min(255, Math.max(0, color[0] * cavityDamp + addR));
              pixels[o + 1] = Math.min(255, Math.max(0, color[1] * cavityDamp + addG));
              pixels[o + 2] = Math.min(255, Math.max(0, color[2] * cavityDamp + addB));
              pixels[o + 3] = Math.round(coverage * smoothFade * 255 * totAlpha);
            } else {
              // Full V7 Optical Glass: authentic continuous volumetric glass substance matching the body
              const baseAlpha = (0.75 + 0.14 * (1.0 - glassTransmission)) + (0.25 + 0.20 * glassThickness) * Math.pow(grazing, 0.70);
              const specAlpha = clamp(whiteGlint * 0.95 + (blueGlint + pinkGlint + goldGlint) * 0.60, 0.0, 1.0);
              const totAlpha = clamp(baseAlpha + specAlpha * (1.0 - baseAlpha), 0.70, 1.0);

              pixels[o]     = Math.min(255, Math.max(0, color[0] + addR * 0.55));
              pixels[o + 1] = Math.min(255, Math.max(0, color[1] + addG * 0.55));
              pixels[o + 2] = Math.min(255, Math.max(0, color[2] + addB * 0.55));
              pixels[o + 3] = Math.round(coverage * smoothFade * 255 * totAlpha);
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

  // --- 4. UI CONTROLS & APPEARANCE INTEGRATION ---
  const spec = [
    ['transmission', 'Transmisi\u00f3n \u00f3ptica', 0, 1, .01],
    ['ior', '\u00cdndice de refracci\u00f3n (IOR)', 1.01, 1.85, .01],
    ['thickness', 'Espesor del cristal', 0, 1, .01],
    ['roughness', 'Rugosidad microsc\u00f3pica', .015, .48, .005],
    ['iridescence', 'Iridescencia', 0, 1, .01],
    ['rim', 'Intensidad del borde', 0, 1, .01],
    ['saturation', 'Saturaci\u00f3n', 0, 1, .01],
    ['exposure', 'Exposici\u00f3n HDR', .48, 2.1, .01]
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
    panel.innerHTML = `
      <div class="field-title" style="margin-top:16px;">AJUSTES OPTICAL GLASS</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px 0;">
        <button type="button" class="tool-btn" data-preset="reference">Reference Glass</button>
        <button type="button" class="tool-btn" data-preset="crystal">Optical Crystal</button>
        <button type="button" class="tool-btn" data-preset="liquid">Liquid Gel</button>
        <button type="button" class="tool-btn" data-preset="silica">Pure Silica</button>
        <button type="button" class="tool-btn" data-preset="aura">Prismatic Aura</button>
        <button type="button" class="tool-btn" data-preset="ethereal" style="border-color:rgba(120,200,255,0.4);">Ethereal Glass</button>
      </div>
      <div id="axx-optical-sliders" style="display:grid;grid-template-columns:1fr;gap:10px;"></div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:12px;">
        <label for="axx-glass-color" style="font-size:12px;color:var(--text-muted, #94a3b8);">Color personalizado</label>
        <input type="color" id="axx-glass-color" value="${color || '#70caff'}" style="background:none;border:none;width:36px;height:24px;cursor:pointer;">
      </div>
    `;

    const container = panel.querySelector('#axx-optical-sliders');
    for (const [key, label, min, max, step] of spec) {
      const row = document.createElement('div');
      row.style.display = 'grid';
      row.style.gridTemplateColumns = '140px 1fr 44px';
      row.style.alignItems = 'center';
      row.style.gap = '8px';
      row.innerHTML = `
        <span style="font-size:11px;color:var(--text-muted, #94a3b8);">${label}</span>
        <input type="range" min="${min}" max="${max}" step="${step}" value="${p[key]}" style="width:100%;">
        <output style="font-size:11px;text-align:right;color:var(--text, #e2e8f0);font-variant-numeric:tabular-nums;">${p[key].toFixed(2)}</output>
      `;
      const slider = row.querySelector('input');
      const output = row.querySelector('output');
      slider.oninput = () => {
        output.value = Number(slider.value).toFixed(2);
        set({ [key]: Number(slider.value) });
      };
      inputs.set(key, { slider, output });
      container.appendChild(row);
    }

    const colorPicker = panel.querySelector('#axx-glass-color');
    colorPicker.oninput = () => set({ color: colorPicker.value });
    inputs.set('color', colorPicker);

    panel.querySelectorAll('[data-preset]').forEach(btn => {
      btn.onclick = () => set({ preset: btn.dataset.preset });
    });

    status.insertAdjacentElement('afterend', panel);
    sync();
  }

  const origSetFinish = proto.setFinish;
  if (origSetFinish) {
    proto.setFinish = function patchedSetFinish(f) {
      origSetFinish.call(this, f);
      sync();
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }

  window.AxxOpticalGlass = {
    version: '1.0.0',
    get: () => ({ ...p, color }),
    set,
    setPreset: name => set({ preset: name }),
    presets: Object.keys(PRESETS)
  };
})();
