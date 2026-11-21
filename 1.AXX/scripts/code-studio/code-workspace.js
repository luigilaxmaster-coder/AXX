/**
 * AXX Code Studio — Lazy-loaded Workspace Shell (PR-13 / CODE-01).
 * Manages project explorer, open editor tabs, diff review cards, and Time Machine rollback without
 * blocking the 3D avatar renderer when closed.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxCodeWorkspace = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class CodeWorkspaceController {
    constructor(options = {}) {
      this.apiBase = options.apiBase || '/axx-api/code/v1';
      this.fetchImpl = options.fetchImpl || (typeof fetch === 'function' ? fetch.bind(globalThis) : null);
      this.activeProjectId = null;
      this.openTabs = new Map();
      this.activeTabPath = null;
      this.isMounted = false;
    }

    mount() {
      this.isMounted = true;
      return { mounted: true, activeProjectId: this.activeProjectId };
    }

    unmount() {
      this.isMounted = false;
      this.openTabs.clear();
      this.activeTabPath = null;
      return { mounted: false };
    }

    openDocumentTab(doc) {
      if (!doc || !doc.path) {
        throw new Error('Document path is required');
      }
      const tab = {
        path: doc.path,
        project_id: doc.project_id || this.activeProjectId,
        sha256: doc.sha256,
        encoding: doc.encoding || 'utf-8',
        line_ending: doc.line_ending || 'LF',
        read_only_degraded: Boolean(doc.read_only_degraded),
        truncated: Boolean(doc.truncated),
        content: doc.content || '',
        dirty: false,
      };
      this.openTabs.set(doc.path, tab);
      this.activeTabPath = doc.path;
      return tab;
    }

    updateTabContent(path, newContent) {
      const tab = this.openTabs.get(path);
      if (!tab) {
        throw new Error(`Tab not open: ${path}`);
      }
      if (tab.read_only_degraded) {
        throw new Error(`File ${path} is open in read-only large-file degraded mode`);
      }
      tab.content = String(newContent);
      tab.dirty = true;
      return tab;
    }
  }

  return { CodeWorkspaceController };
});
