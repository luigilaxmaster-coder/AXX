/**
 * AXX Background Workspaces — Isolated VM Stage View (PR-16 / PC-05 / E2E-04).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxVmStage = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class VmStageController {
    constructor() {
      this.vms = new Map();
    }

    updateVmState(vmInfo) {
      if (!vmInfo || !vmInfo.vm_id) {
        throw new Error('vm_id is required');
      }
      this.vms.set(vmInfo.vm_id, Object.assign({}, vmInfo));
      return this.vms.get(vmInfo.vm_id);
    }
  }

  return { VmStageController };
});
