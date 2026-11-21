/**
 * AXX Code Studio — Supervised Test Runner & Terminal Output Panel (PR-14 / CODE-03).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxTerminalPanel = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class TerminalPanelController {
    constructor() {
      this.receipts = [];
    }

    recordReceipt(receipt) {
      if (!receipt || !receipt.report_id) {
        throw new Error('Invalid TestReceipt');
      }
      this.receipts.push(receipt);
      return receipt;
    }
  }

  return { TerminalPanelController };
});
