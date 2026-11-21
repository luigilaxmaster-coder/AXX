/**
 * AXX Multi-Agent Orchestration — Team Chat & Typed Handoff Card Renderer (PR-17 / E2E-09).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxTeamChat = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class TeamChatController {
    constructor() {
      this.handoffs = [];
    }

    recordHandoff(handoff) {
      if (!handoff || !handoff.handoff_id || handoff.from_agent_id === handoff.to_agent_id) {
        throw new Error('Invalid Handoff payload');
      }
      this.handoffs.push(Object.assign({}, handoff));
      return handoff;
    }
  }

  return { TeamChatController };
});
