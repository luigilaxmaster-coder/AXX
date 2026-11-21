/**
 * AXX Code Studio — Diagnostics & Problems Panel (PR-14 / PR-18).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxProblemsPanel = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class ProblemsPanelController {
    constructor() {
      this.diagnostics = [];
      this.degradedReason = null;
    }

    setDiagnostics(items, degradedReason = null) {
      this.diagnostics = Array.isArray(items) ? items.slice() : [];
      this.degradedReason = degradedReason;
      return {
        count: this.diagnostics.length,
        degraded: Boolean(this.degradedReason),
        degradedReason: this.degradedReason,
      };
    }
  }

  return { ProblemsPanelController };
});
