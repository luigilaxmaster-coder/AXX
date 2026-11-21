/**
 * AXX Multi-Agent Orchestration — Human-in-the-Loop Approval Cards Controller (PR-17 / E2E-14).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxWorkApprovals = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class WorkApprovalsController {
    constructor() {
      this.cards = new Map();
    }

    registerApprovalRequest(card) {
      if (!card || !card.operation_id) {
        throw new Error('operation_id is required for approval card');
      }
      const entry = Object.assign({ status: 'pending' }, card);
      this.cards.set(card.operation_id, entry);
      return entry;
    }

    resolveCard(operationId, approved) {
      const card = this.cards.get(operationId);
      if (!card) {
        throw new Error(`Approval card not found: ${operationId}`);
      }
      card.status = approved ? 'approved' : 'denied';
      return card;
    }
  }

  return { WorkApprovalsController };
});
