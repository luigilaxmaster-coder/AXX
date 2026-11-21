/**
 * AXX Code Studio — Editor Adapter with Encoding/EOL Preservation and CAS Save Guard (PR-13 / CODE-01).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AxxCodeEditor = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  class CodeEditorAdapter {
    constructor() {
      this.models = new Map();
    }

    loadDocument(doc) {
      if (!doc || typeof doc.path !== 'string') {
        throw new Error('Invalid document payload');
      }
      const state = {
        path: doc.path,
        baseSha256: doc.sha256,
        encoding: doc.encoding || 'utf-8',
        lineEnding: doc.line_ending || 'LF',
        readOnly: Boolean(doc.read_only_degraded),
        value: String(doc.content || ''),
      };
      this.models.set(doc.path, state);
      return state;
    }

    buildSavePayload(path, nextValue) {
      const model = this.models.get(path);
      if (!model) {
        throw new Error(`Model not loaded for ${path}`);
      }
      if (model.readOnly) {
        throw new Error(`Cannot save read-only degraded document: ${path}`);
      }
      return {
        path: model.path,
        expected_sha256: model.baseSha256,
        encoding: model.encoding,
        line_ending: model.lineEnding,
        new_content: String(nextValue !== undefined ? nextValue : model.value),
      };
    }
  }

  return { CodeEditorAdapter };
});
