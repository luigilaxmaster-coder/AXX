/**
 * AXX Background Workspaces — Isolated Browser Stage View (PR-15 / E2E-03).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxBrowserStage = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class BrowserStageController {
    constructor() {
      this.sessions = new Map();
    }

    updateSession(session) {
      if (!session || !session.session_id) {
        throw new Error('session_id is required');
      }
      this.sessions.set(session.session_id, Object.assign({}, session));
      return this.sessions.get(session.session_id);
    }
  }

  return { BrowserStageController };
});
