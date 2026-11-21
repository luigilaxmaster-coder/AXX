/**
 * AXX Background Workspaces — Event-Correlated Virtual Cursor Renderer (PR-15 / I-10).
 * Only renders virtual cursor positions backed by verified tool execution events.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxVirtualCursors = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const ALLOWED_EVENT_TYPES = new Set(['tool.dispatched', 'tool.progress', 'tool.completed']);

  class VirtualCursorOverlay {
    constructor() {
      this.cursors = new Map();
    }

    applyTelemetryFrame(frame) {
      if (!frame || !frame.correlating_event_id || !ALLOWED_EVENT_TYPES.has(frame.event_type)) {
        throw new Error('Virtual cursor frame rejected (I-10): missing real correlating tool event');
      }
      const state = {
        cursor_id: frame.cursor_id,
        agent_id: frame.agent_id,
        workspace_id: frame.workspace_id,
        correlating_event_id: frame.correlating_event_id,
        event_type: frame.event_type,
        fencing_token: frame.fencing_token,
        x: Number(frame.x || 0),
        y: Number(frame.y || 0),
        action_state: frame.action_state || 'idle',
      };
      this.cursors.set(frame.cursor_id, state);
      return state;
    }
  }

  return { VirtualCursorOverlay };
});
