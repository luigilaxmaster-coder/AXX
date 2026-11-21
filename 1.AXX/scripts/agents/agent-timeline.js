/**
 * AXX Multi-Agent Orchestration — Monotonic SSE Timeline & Flight Recorder Viewer (PR-17 / ORCH-03 / E2E-11).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxAgentTimeline = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class AgentTimelineController {
    constructor() {
      this.eventsByConversation = new Map();
      this.lastSeqByConversation = new Map();
    }

    ingestEvent(ev) {
      if (!ev || !ev.conversation_id || typeof ev.seq !== 'number') {
        throw new Error('Invalid RuntimeEvent v1');
      }
      const cid = ev.conversation_id;
      const lastSeq = this.lastSeqByConversation.get(cid) || 0;
      if (ev.seq <= lastSeq) {
        return { accepted: false, duplicate: true, lastSeq };
      }
      if (!this.eventsByConversation.has(cid)) {
        this.eventsByConversation.set(cid, []);
      }
      this.eventsByConversation.get(cid).push(ev);
      this.lastSeqByConversation.set(cid, ev.seq);
      return { accepted: true, duplicate: false, lastSeq: ev.seq };
    }
  }

  return { AgentTimelineController };
});
