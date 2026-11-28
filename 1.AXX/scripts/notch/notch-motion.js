/* Continuous retargetable spring motion controller for AXX Notch.
 * Preserves current position and velocity on retargeting (C0/C1 continuity). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchMotion = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  class MotionChannel {
    constructor(value = 0, stiffness = 290, damping = 28, maxOvershoot = 0) {
      this.value = value;
      this.velocity = 0;
      this.target = value;
      this.stiffness = stiffness;
      this.damping = damping;
      this.maxOvershoot = maxOvershoot;
      this._direction = 0;
    }

    setTarget(nextTarget, reducedMotion = false) {
      if (!Number.isFinite(nextTarget)) return;
      if (reducedMotion) {
        this.target = nextTarget;
        this.value = nextTarget;
        this.velocity = 0;
        this._direction = 0;
        return;
      }
      this._direction = Math.sign(nextTarget - this.value);
      this.target = nextTarget;
      // Deliberately preserve `this.value` and `this.velocity` for C0/C1 retarget continuity.
    }

    reset(value) {
      this.value = value;
      this.target = value;
      this.velocity = 0;
      this._direction = 0;
    }

    step(dt, reducedMotion = false) {
      if (reducedMotion) {
        this.value = this.target;
        this.velocity = 0;
        return this.value;
      }
      let left = clamp(Number.isFinite(dt) ? dt : 0, 0, 0.05);
      while (left > 0) {
        const h = Math.min(left, 1 / 120);
        const accel = this.stiffness * (this.target - this.value) - this.damping * this.velocity;
        this.velocity += accel * h;
        this.value += this.velocity * h;
        if (this.maxOvershoot >= 0 && this._direction !== 0) {
          const past = (this.value - this.target) * this._direction;
          if (past > this.maxOvershoot) {
            this.value = this.target + this._direction * this.maxOvershoot;
            this.velocity *= 0.25;
          }
        }
        left -= h;
      }
      if (this.isSettled()) {
        this.value = this.target;
        this.velocity = 0;
        this._direction = 0;
      }
      return this.value;
    }

    isSettled(epsilon = 0.25, velEpsilon = 1.0) {
      return Math.abs(this.target - this.value) <= epsilon && Math.abs(this.velocity) <= velEpsilon;
    }
  }

  class NotchMotionController {
    constructor(initial = {}) {
      this.channels = {
        x: new MotionChannel(initial.x ?? 0, 320, 34, 6),
        y: new MotionChannel(initial.y ?? 0, 320, 34, 4),
        width: new MotionChannel(initial.width ?? 220, 300, 33, 8),
        height: new MotionChannel(initial.height ?? 34, 300, 33, 6),
        radius: new MotionChannel(initial.radius ?? 16, 260, 30, 2),
        shellOpacity: new MotionChannel(initial.shellOpacity ?? 0, 220, 28, 0),
        contentReveal: new MotionChannel(initial.contentReveal ?? 0, 240, 29, 0),
        avatarOpacity: new MotionChannel(initial.avatarOpacity ?? 1, 220, 28, 0)
      };
    }

    setProfile(profile) {
      // Critically damped crisp response; changing profile preserves position and velocity.
      const crisp = profile === 'crisp';
      for (const key of ['x', 'y', 'width', 'height', 'radius']) {
        this.channels[key].stiffness = crisp ? 460 : 300;
        this.channels[key].damping = crisp ? 43 : 34;
        this.channels[key].maxOvershoot = 0;
      }
    }

    setTargets(targets, reducedMotion = false) {
      for (const [key, val] of Object.entries(targets)) {
        if (this.channels[key] && Number.isFinite(val)) {
          this.channels[key].setTarget(val, reducedMotion);
        }
      }
    }

    snap(values) {
      for (const [key, val] of Object.entries(values)) {
        if (this.channels[key] && Number.isFinite(val)) {
          this.channels[key].reset(val);
        }
      }
    }

    step(dt, reducedMotion = false) {
      const out = {};
      for (const [key, ch] of Object.entries(this.channels)) {
        out[key] = ch.step(dt, reducedMotion);
      }
      return out;
    }

    snapshot() {
      const out = {};
      for (const [key, ch] of Object.entries(this.channels)) {
        out[key] = { value: ch.value, velocity: ch.velocity, target: ch.target };
      }
      return out;
    }

    isSettled() {
      for (const [key, ch] of Object.entries(this.channels)) {
        const eps = key === 'shellOpacity' || key === 'contentReveal' || key === 'avatarOpacity' ? 0.01 : 0.35;
        const veps = key === 'shellOpacity' || key === 'contentReveal' || key === 'avatarOpacity' ? 0.05 : 1.5;
        if (!ch.isSettled(eps, veps)) return false;
      }
      return true;
    }
  }

  return { MotionChannel, NotchMotionController };
});
