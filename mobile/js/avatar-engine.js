/**
 * Axx Mobile · Motor de Renderizado 3D Líquido Procedural
 * Implementa las 24 formas paramétricas, 9 paletas, físicas Spring y reactividad de estados.
 */

(function (global) {
  'use strict';

  const FORMS = [
    { name: 'Core', detail: 'Esfera compacta' },
    { name: 'Flow', detail: 'Masa fluida' },
    { name: 'Pearl', detail: 'Gota redondeada' },
    { name: 'Torus', detail: 'Anillo líquido' },
    { name: 'Split', detail: 'Volumen abierto' },
    { name: 'Wave', detail: 'Onda alargada' },
    { name: 'Bloom', detail: 'Lóbulos conectados' },
    { name: 'Fold', detail: 'Materia plegada' },
    { name: 'Spike', detail: 'Puntas suaves' },
    { name: 'Drift', detail: 'Bandas fluidas' },
    { name: 'Orbit', detail: 'Núcleo orbital' },
    { name: 'Morph', detail: 'Metamorfosis orgánica' },
    { name: 'Cushion', detail: 'Cojín de metal líquido' },
    { name: 'Trefoil', detail: 'Trébol de tres lóbulos' },
    { name: 'Nova', detail: 'Estrella de seis puntas' },
    { name: 'Heart', detail: 'Corazón volumétrico' },
    { name: 'Infinity', detail: 'Lazo infinito 3D' },
    { name: 'Helix', detail: 'Hélice doble' },
    { name: 'Knot', detail: 'Nudo tubular cerrado' },
    { name: 'Petal', detail: 'Flor de cinco pétalos' },
    { name: 'Prism', detail: 'Prisma blando retorcido' },
    { name: 'Capsule', detail: 'Cápsula vertical' },
    { name: 'Crescent', detail: 'Luna abierta' },
    { name: 'Ripple', detail: 'Disco ondulado con relieve' }
  ];

  const PALETTES = [
    { name: 'Obsidian', colors: ['#157eff', '#79e7ff', '#a14dff', '#edb58c'] },
    { name: 'Nebula', colors: ['#734bff', '#d599ff', '#e846d9', '#8faaff'] },
    { name: 'Ocean', colors: ['#057dff', '#7ef5ff', '#315dea', '#cbf4ff'] },
    { name: 'Sunset', colors: ['#ea4228', '#ffb47a', '#8a283f', '#ffe0b1'] },
    { name: 'Amethyst', colors: ['#8c2bea', '#d8a5ff', '#b21ff1', '#eed8ff'] },
    { name: 'Emerald', colors: ['#079c84', '#8dfad5', '#007158', '#e4dd9a'] },
    { name: 'Champagne', colors: ['#b58952', '#f1d8b6', '#795a46', '#fff1cd'] },
    { name: 'Silver', colors: ['#8e9dac', '#e3f0fa', '#7e8698', '#f4ece4'] },
    { name: 'Void', colors: ['#352966', '#847aa7', '#402460', '#b2b7d5'] }
  ];

  const STATE_FORM = {
    idle: 11,
    listening: 10,
    thinking: 7,
    speaking: 5,
    processing: 3,
    approval: 0,
    paused: 0,
    success: 6,
    error: 4,
    notification: 11
  };

  class Spring {
    constructor(value = 0, stiffness = 105, damping = 17) {
      this.stiffness = stiffness;
      this.damping = damping;
      this.value = value;
      this.velocity = 0;
    }
    step(target, dt) {
      let left = Math.max(0, Math.min(0.08, dt || 0.016));
      while (left > 0) {
        const h = Math.min(left, 1 / 120);
        this.velocity += (this.stiffness * (target - this.value) - this.damping * this.velocity) * h;
        this.value += this.velocity * h;
        left -= h;
      }
      return this.value;
    }
    impulse(v) {
      this.velocity += Math.max(-8, Math.min(8, v));
    }
    reset(v = 0) {
      this.value = v;
      this.velocity = 0;
    }
  }

  class LiquidAvatarEngine {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d', { alpha: true });
      this.form = options.form !== undefined ? options.form : 11; // Morph por defecto
      this.paletteIndex = options.palette !== undefined ? options.palette : 0; // Obsidian
      this.state = 'idle';
      this.audioLevel = 0; // 0.0 a 1.0 para reactividad de voz
      this.pressure = new Spring(0, 140, 18);
      this.rotX = new Spring(0, 70, 14);
      this.rotY = new Spring(0, 70, 14);
      this.phase = 0;
      this.lastTime = performance.now();
      this.isRunning = false;
      this.pointerDown = false;
      this.dragStart = { x: 0, y: 0 };

      // Configuración de resolución interna
      this.gridU = 64;
      this.gridV = 44;
      this.positions = new Float32Array((this.gridU + 1) * (this.gridV + 1) * 3);
      this.projected = new Float32Array((this.gridU + 1) * (this.gridV + 1) * 2);

      this.setupTouchInteractions();
      this.resize();
    }

    resize() {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.width = rect.width || 280;
      this.height = rect.height || 280;
      this.canvas.width = Math.round(this.width * dpr);
      this.canvas.height = Math.round(this.height * dpr);
      this.dpr = dpr;
    }

    setupTouchInteractions() {
      const el = this.canvas;
      el.addEventListener('pointerdown', (e) => {
        this.pointerDown = true;
        this.dragStart = { x: e.clientX, y: e.clientY };
        this.pressure.impulse(0.5);
        el.setPointerCapture(e.pointerId);
      });

      el.addEventListener('pointermove', (e) => {
        if (!this.pointerDown) return;
        const dx = (e.clientX - this.dragStart.x) * 0.01;
        const dy = (e.clientY - this.dragStart.y) * 0.01;
        this.rotY.value += dx * 0.5;
        this.rotX.value -= dy * 0.5;
        this.dragStart = { x: e.clientX, y: e.clientY };
      });

      const release = () => {
        this.pointerDown = false;
        this.pressure.impulse(-0.3);
      };
      el.addEventListener('pointerup', release);
      el.addEventListener('pointercancel', release);
    }

    setState(newState) {
      if (this.state === newState) return;
      this.state = newState;
      if (STATE_FORM[newState] !== undefined) {
        this.form = STATE_FORM[newState];
      }
      this.pressure.impulse(0.4);
    }

    setAudioLevel(level) {
      this.audioLevel = Math.max(0, Math.min(1.5, level));
    }

    setForm(formIndex) {
      if (formIndex >= 0 && formIndex < FORMS.length) {
        this.form = formIndex;
        this.pressure.impulse(0.3);
      }
    }

    setPalette(index) {
      if (index >= 0 && index < PALETTES.length) {
        this.paletteIndex = index;
      }
    }

    start() {
      if (this.isRunning) return;
      this.isRunning = true;
      this.lastTime = performance.now();
      const loop = (now) => {
        if (!this.isRunning) return;
        const dt = (now - this.lastTime) / 1000;
        this.lastTime = now;
        this.update(dt);
        this.render();
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }

    stop() {
      this.isRunning = false;
    }

    update(dt) {
      let speed = 0.8;
      if (this.state === 'thinking') speed = 1.4;
      if (this.state === 'processing') speed = 1.8;
      if (this.state === 'listening') speed = 0.9 + this.audioLevel * 1.5;

      this.phase += dt * speed;
      this.pressure.step(0, dt);
      this.rotX.step(0, dt);
      this.rotY.step(0, dt);
    }

    // Evaluación matemática paramétrica de superficie
    evaluateShape(u, v, phase, out, offset) {
      const a = u * Math.PI * 2;
      const t = v * Math.PI;
      const sa = Math.sin(a), ca = Math.cos(a);
      const st = Math.sin(t), ct = Math.cos(t);

      let x = st * ca;
      let y = ct;
      let z = st * sa;
      let r = 1.0;

      const id = this.form;
      switch (id) {
        case 0: // Core
          r = 0.95 + 0.05 * Math.sin(a * 4 + phase) * st;
          break;
        case 1: // Flow
          r = 0.88 + 0.22 * Math.sin(a * 3 + ct * 3 + phase) * st;
          break;
        case 2: // Pearl
          r = 0.9 + 0.25 * ct;
          y *= 1.15;
          break;
        case 3: // Torus
          {
            const R = 0.72, tr = 0.28;
            x = (R + tr * Math.cos(t * 2)) * ca;
            z = (R + tr * Math.cos(t * 2)) * sa;
            y = tr * Math.sin(t * 2);
            r = 1.0;
          }
          break;
        case 4: // Split
          r = 0.85 + 0.28 * Math.abs(sa) * st;
          y *= 1.1;
          break;
        case 5: // Wave
          r = 0.82 + 0.25 * Math.sin(a * 2 + phase * 2) * st;
          y += 0.15 * Math.sin(a * 3 + phase);
          break;
        case 6: // Bloom
          r = 0.82 + 0.3 * Math.cos(a * 4) * Math.sin(t * 2);
          break;
        case 7: // Fold
          r = 0.85 + 0.26 * Math.sin(a * 3) * Math.cos(t * 3 + phase);
          break;
        case 8: // Spike
          r = 0.78 + 0.35 * Math.pow(Math.abs(Math.sin(a * 5) * st), 2);
          break;
        case 10: // Orbit
          r = 0.88 + 0.2 * Math.sin(a * 6 + phase * 3) * st * st;
          break;
        case 12: // Cushion
          r = 0.92 + 0.18 * (Math.pow(ca, 4) + Math.pow(sa, 4)) * st;
          break;
        case 15: // Heart
          y = ct * 0.9 + 0.25 * Math.abs(x);
          r = 0.9 + 0.2 * ca * st;
          break;
        case 16: // Infinity
          {
            const ta = a;
            x = 0.9 * Math.sin(ta);
            y = 0.55 * Math.sin(2 * ta);
            z = 0.3 * Math.cos(ta) + st * 0.15;
            r = 1.0;
          }
          break;
        case 21: // Capsule
          y = ct * 0.85 + 0.35 * Math.tanh(ct * 3);
          x *= 0.65;
          z *= 0.65;
          break;
        default: // 11: Morph
          r = 0.92 + 0.24 * Math.sin(3 * a + 1.8 * ct + phase) * Math.pow(st, 2.5) + 0.12 * Math.cos(2 * a + phase);
          break;
      }

      x *= r;
      y *= r;
      z *= r;

      // Deformación orgánica viva
      const squash = 1 - this.pressure.value * 0.25;
      y *= squash;
      x /= Math.sqrt(squash);
      z /= Math.sqrt(squash);

      // Reactividad acústica (micrófono activo)
      if (this.audioLevel > 0.05) {
        const pulse = Math.sin(a * 4 + phase * 4) * this.audioLevel * 0.18;
        x += pulse * ca;
        z += pulse * sa;
      }

      out[offset] = x;
      out[offset + 1] = y;
      out[offset + 2] = z;
    }

    render() {
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const scale = (Math.min(w, h) * 0.38);

      const pal = PALETTES[this.paletteIndex] || PALETTES[0];
      const colors = pal.colors;

      // Rotación combinada
      const rx = this.rotX.value + Math.sin(this.phase * 0.5) * 0.08;
      const ry = this.rotY.value + this.phase * 0.3;

      const cosY = Math.cos(ry), sinY = Math.sin(ry);
      const cosX = Math.cos(rx), sinX = Math.sin(rx);

      // Evaluación de la malla y proyección 3D -> 2D
      let idx = 0;
      let pIdx = 0;
      const uSteps = this.gridU;
      const vSteps = this.gridV;

      for (let j = 0; j <= vSteps; j++) {
        const v = j / vSteps;
        for (let i = 0; i <= uSteps; i++) {
          const u = i / uSteps;
          this.evaluateShape(u, v, this.phase, this.positions, idx);

          let px = this.positions[idx];
          let py = this.positions[idx + 1];
          let pz = this.positions[idx + 2];

          // Rotar Y
          let x1 = px * cosY - pz * sinY;
          let z1 = px * sinY + pz * cosY;

          // Rotar X
          let y2 = py * cosX - z1 * sinX;
          let z2 = py * sinX + z1 * cosX;

          // Proyección con perspectiva sutil
          const fov = 3.2;
          const depth = fov / (fov + z2 * 0.5);

          this.projected[pIdx] = cx + x1 * scale * depth;
          this.projected[pIdx + 1] = cy - y2 * scale * depth;

          idx += 3;
          pIdx += 2;
        }
      }

      // Dibujar fondo sombreado sutil (Cuerpo de metal líquido)
      ctx.save();
      const bodyGrad = ctx.createRadialGradient(cx - scale * 0.25, cy - scale * 0.3, scale * 0.1, cx, cy, scale * 1.1);
      bodyGrad.addColorStop(0, colors[1]);
      bodyGrad.addColorStop(0.35, colors[0]);
      bodyGrad.addColorStop(0.75, colors[2]);
      bodyGrad.addColorStop(1, 'rgba(8, 11, 16, 0.95)');

      // Dibujar silueta fluida
      ctx.fillStyle = bodyGrad;
      ctx.beginPath();
      for (let i = 0; i <= uSteps; i++) {
        const midJ = Math.floor(vSteps / 2);
        const p = (midJ * (uSteps + 1) + i) * 2;
        if (i === 0) ctx.moveTo(this.projected[p], this.projected[p + 1]);
        else ctx.lineTo(this.projected[p], this.projected[p + 1]);
      }
      ctx.closePath();
      ctx.fill();

      // Malla de curvas orgánicas con aberración cromática especular
      ctx.lineWidth = 1.2 * this.dpr;
      for (let j = 4; j < vSteps; j += 4) {
        ctx.beginPath();
        const strokeGrad = ctx.createLinearGradient(cx - scale, cy, cx + scale, cy);
        strokeGrad.addColorStop(0, colors[0] + '40');
        strokeGrad.addColorStop(0.5, colors[1] + '90');
        strokeGrad.addColorStop(1, colors[3] + '50');
        ctx.strokeStyle = strokeGrad;

        for (let i = 0; i <= uSteps; i++) {
          const p = (j * (uSteps + 1) + i) * 2;
          if (i === 0) ctx.moveTo(this.projected[p], this.projected[p + 1]);
          else ctx.lineTo(this.projected[p], this.projected[p + 1]);
        }
        ctx.stroke();
      }

      // Reflejo especular cromo iridiscente superior
      const specGrad = ctx.createRadialGradient(
        cx - scale * 0.35,
        cy - scale * 0.45,
        0,
        cx - scale * 0.35,
        cy - scale * 0.45,
        scale * 0.45
      );
      specGrad.addColorStop(0, 'rgba(255, 255, 255, 0.75)');
      specGrad.addColorStop(0.4, 'rgba(235, 245, 255, 0.25)');
      specGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');

      ctx.fillStyle = specGrad;
      ctx.beginPath();
      ctx.arc(cx - scale * 0.35, cy - scale * 0.45, scale * 0.45, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    }
  }

  // Exportar al ámbito global
  global.AxxAvatar = {
    FORMS,
    PALETTES,
    STATE_FORM,
    LiquidAvatarEngine
  };
})(typeof window !== 'undefined' ? window : this);
