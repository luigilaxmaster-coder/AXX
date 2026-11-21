/**
 * AXX Code Studio — Git Worktrees & Dirty-File Conflict Panel (PR-14 / CODE-02).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxGitPanel = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class GitWorktreePanel {
    constructor() {
      this.worktrees = [];
      this.dirtyFiles = [];
    }

    setState({ worktrees = [], dirtyFiles = [] } = {}) {
      this.worktrees = Array.isArray(worktrees) ? worktrees.slice() : [];
      this.dirtyFiles = Array.isArray(dirtyFiles) ? dirtyFiles.slice() : [];
      return {
        activeCount: this.worktrees.filter((w) => w.status === 'active').length,
        dirtyCount: this.dirtyFiles.length,
      };
    }

    canIntegrateChangeSet(changeset) {
      const dirtySet = new Set(this.dirtyFiles);
      const overlapping = (changeset.files || [])
        .map((f) => f.path)
        .filter((p) => dirtySet.has(p));
      return {
        safe: overlapping.length === 0,
        overlappingDirtyFiles: overlapping,
      };
    }
  }

  return { GitWorktreePanel };
});
