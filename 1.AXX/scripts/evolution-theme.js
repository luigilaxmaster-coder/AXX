/**
 * AXX Evolution 3.0 — Aesthetic Theme Loader (Apple × Google Design x100)
 *
 * Dynamically ensures `scripts/evolution-theme.css` is attached to the document
 * with zero impact on companion baseline hashes.
 */
(function (global) {
  'use strict';

  function initEvolutionTheme() {
    if (typeof document === 'undefined') return;
    const existing = document.getElementById('axx-evolution-theme-link');
    if (existing) return;

    const link = document.createElement('link');
    link.id = 'axx-evolution-theme-link';
    link.rel = 'stylesheet';
    link.href = 'scripts/evolution-theme.css';
    link.onload = function () {
      document.documentElement.classList.add('axx-evolution-theme-active');
    };
    (document.head || document.documentElement).appendChild(link);
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initEvolutionTheme);
    } else {
      initEvolutionTheme();
    }
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { initEvolutionTheme };
  } else {
    global.AxxEvolutionTheme = { initEvolutionTheme };
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
