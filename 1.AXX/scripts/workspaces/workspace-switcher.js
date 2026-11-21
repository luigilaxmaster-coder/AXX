/**
 * AXX Background Workspaces — Workspace Switcher & Active Lease Indicator (PR-15 / PC-01).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxWorkspaceSwitcher = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class WorkspaceSwitcherController {
    constructor() {
      this.workspaces = new Map();
      this.activeWorkspaceId = null;
    }

    registerWorkspace(ws) {
      if (!ws || !ws.workspace_id) {
        throw new Error('workspace_id is required');
      }
      this.workspaces.set(ws.workspace_id, Object.assign({}, ws));
      if (!this.activeWorkspaceId) {
        this.activeWorkspaceId = ws.workspace_id;
      }
      return this.workspaces.get(ws.workspace_id);
    }

    selectWorkspace(workspaceId) {
      if (!this.workspaces.has(workspaceId)) {
        throw new Error(`Workspace not found: ${workspaceId}`);
      }
      this.activeWorkspaceId = workspaceId;
      return this.workspaces.get(workspaceId);
    }
  }

  return { WorkspaceSwitcherController };
});
