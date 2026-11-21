/**
 * AXX Background Workspaces — Background Win32/UIA Window Stage View (PR-15 / PC-03).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxWindowStage = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class WindowStageController {
    constructor() {
      this.boundWindows = new Map();
    }

    bindWindow(windowInfo) {
      if (!windowInfo || !windowInfo.window_key) {
        throw new Error('window_key is required');
      }
      this.boundWindows.set(windowInfo.window_key, Object.assign({}, windowInfo));
      return this.boundWindows.get(windowInfo.window_key);
    }
  }

  return { WindowStageController };
});
