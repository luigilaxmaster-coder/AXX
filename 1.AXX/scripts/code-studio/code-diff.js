/**
 * AXX Code Studio — CodeChangeSet Diff Reviewer & Rollback Card Controller (PR-13 / CODE-03).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxCodeDiff = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function summarizeChangeSet(changeset) {
    if (!changeset || !Array.isArray(changeset.files)) {
      throw new Error('Invalid CodeChangeSet');
    }
    return {
      changeset_id: changeset.changeset_id,
      agent_id: changeset.agent_id,
      branch: changeset.branch,
      status: changeset.status,
      file_count: changeset.files.length,
      files: changeset.files.map((f) => ({
        path: f.path,
        base_sha256: f.base_sha256,
        proposed_sha256: f.proposed_sha256,
        encoding: f.encoding,
        line_ending: f.line_ending || 'LF',
      })),
    };
  }

  return { summarizeChangeSet };
});
