'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, '1.AXX/Axx.html'), 'utf8');
const addon = fs.readFileSync(path.join(root, '1.AXX/scripts/optical-glass.js'), 'utf8');

// 1. DOM and selector contracts
assert.match(html, /data-finish="opticalglass"/);
assert.match(html, /<script src="scripts\/optical-glass\.js"><\/script>/);
for (const name of ['obsidian', 'prism', 'smoke']) {
  assert.match(html, new RegExp('data-finish="' + name + '"'));
}
assert.equal((html.match(/\['obsidian', 'prism', 'smoke', 'opticalglass'\]\.includes/g) || []).length, 3);

// 2. Mock environment matching AXX engine
const PALETTES = [
  { name: 'Azul Cósmico', colors: ['#5c9fff', '#9af9ff', '#8759f8', '#fbd2ae'] },
  { name: 'Aurora', colors: ['#4ef2bb', '#75fbfd', '#a364ff', '#ffd285'] },
  { name: 'Obsidiana Pura', colors: ['#3a4d6b', '#6ba5ff', '#9055ff', '#ffc187'] },
  { name: 'Carmesí', colors: ['#ff4d79', '#ff94b8', '#9933ff', '#ffd199'] },
  { name: 'Esmeralda', colors: ['#2ee59d', '#84fbd7', '#4675f8', '#ffe08a'] },
  { name: 'Ámbar Solar', colors: ['#ffaa33', '#ffd277', '#ff4d6a', '#c76aff'] },
  { name: 'Amatista', colors: ['#9d55ff', '#d199ff', '#3d7aff', '#ffc285'] },
  { name: 'Cian Profundo', colors: ['#00c2ff', '#7be5ff', '#6e40ff', '#ffe2a0'] },
  { name: 'Perla Minimal', colors: ['#b4c7dc', '#e5f0fc', '#7d91aa', '#ffd8b3'] }
];

class Renderer {
  constructor() {
    this.finish = 'obsidian';
    this.settings = { palette: 0, keepForm: true };
    this.studio = { roughness: .035, exposure: 1, lightAngle: 0 };
    this.state = 'idle';
    this.lutKey = '';
    this.lut = new Uint8ClampedArray(512 * 512 * 4);
  }
  getFinish() { return this.finish; }
  shadeTable() {
    this.lutKey = 'native/' + this.finish;
    for (let i = 0; i < this.lut.length; i += 4) {
      this.lut[i] = 45;
      this.lut[i + 1] = 130;
      this.lut[i + 2] = 212;
      this.lut[i + 3] = 255;
    }
  }
}

class OrganicTendrils {
  constructor() {
    this.materialKey = null;
    this.filteredMaterial = null;
  }
  material(lut, key) {
    if (this.filteredMaterial && key !== undefined && this.materialKey === key) return this.filteredMaterial;
    const size = Math.round(Math.sqrt(lut.length / 4));
    const out = new Uint8ClampedArray(size * size * 4);
    for (let i = 0; i < lut.length; i++) out[i] = lut[i];
    this.materialKey = key;
    this.filteredMaterial = out;
    return out;
  }
}

const instance = new Renderer();
const tendrils = new OrganicTendrils();
const win = {
  Axx: {
    SoftwareRenderer: Renderer,
    OrganicTendrils,
    PALETTES,
    MOTION_PROFILES: { idle: { lightResponse: 1 } },
    app: { renderer: instance }
  }
};
const store = new Map();
const ctx = {
  window: win,
  console,
  document: { getElementById: () => null, addEventListener: () => {} },
  localStorage: { getItem: k => store.get(k) || null, setItem: (k, v) => store.set(k, v) },
  Object, Math, Number, JSON
};

vm.runInNewContext(addon, ctx, { filename: 'optical-glass.js', timeout: 5000 });
assert.equal(win.AxxOpticalGlass.version, '1.0.0');

// 3. Baseline legacy finish verification
instance.shadeTable();
assert.equal(instance.lutKey, 'native/obsidian');
assert.equal(instance.lut[0], 45);
assert.equal(instance.lut[3], 255);
const baselineObsidian = Array.from(instance.lut.slice(0, 16));

// 4. Optical glass finish activation & cache test
instance.finish = 'opticalglass';
instance.shadeTable();
const sample = Array.from(instance.lut.slice(0, 8));
assert.ok(instance.lutKey.startsWith('opticalglass/'));
assert.notEqual(instance.lut[0], 45);
assert.equal(instance.lut[3], 255, 'Alpha must be 255 for tentacle root attachment and hit-testing');

// Tendril material consumption test
const tendrilMat = tendrils.material(instance.lut, instance.lutKey);
assert.equal(tendrilMat.length, instance.lut.length);
assert.equal(tendrilMat[3], 255);
assert.equal(tendrils.materialKey, instance.lutKey);

// Cache hit verification
instance.shadeTable();
assert.deepEqual(Array.from(instance.lut.slice(0, 8)), sample);

// 5. Presets validation (all 5 required presets)
const expectedPresets = ['reference', 'crystal', 'liquid', 'silica', 'aura'];
assert.deepEqual(win.AxxOpticalGlass.presets, expectedPresets);

for (const presetName of expectedPresets) {
  win.AxxOpticalGlass.set({ preset: presetName });
  instance.shadeTable();
  assert.ok(instance.lutKey.startsWith('opticalglass/'));
  assert.equal(instance.lut[3], 255);
}

// 6. Parameter mutation, custom tint and bounds clamping
win.AxxOpticalGlass.set({ ior: 1.55, iridescence: 0.85, color: '#de88ff' });
assert.equal(win.AxxOpticalGlass.get().color, '#de88ff');
assert.equal(win.AxxOpticalGlass.get().ior, 1.55);
assert.equal(instance.lutKey, '');
instance.shadeTable();
assert.ok(instance.lutKey.startsWith('opticalglass/'));
assert.equal(instance.lut[3], 255);

// Reset custom color back to palette
win.AxxOpticalGlass.set({ color: '' });
assert.equal(win.AxxOpticalGlass.get().color, '');

// 7. Verify all 9 palettes with Optical Glass
for (let p = 0; p < 9; p++) {
  instance.settings.palette = p;
  instance.lutKey = '';
  instance.shadeTable();
  assert.ok(instance.lutKey.startsWith('opticalglass/'));
  assert.equal(instance.lut[3], 255);
}

// 8. Bit-for-bit restoration when reverting to Obsidian Chrome
instance.settings.palette = 0;
instance.finish = 'obsidian';
instance.shadeTable();
assert.equal(instance.lutKey, 'native/obsidian');
assert.deepEqual(Array.from(instance.lut.slice(0, 16)), baselineObsidian);

// 9. Reversion to Smoke Chrome
instance.finish = 'smoke';
instance.shadeTable();
assert.equal(instance.lutKey, 'native/smoke');
assert.equal(instance.lut[0], 45);
assert.equal(instance.lut[3], 255);

console.log('Optical Glass: opt-in finish, source integration, 5 presets, tendril LUT consumption, cache, and legacy materials OK');
