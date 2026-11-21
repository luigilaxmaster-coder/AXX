/**
 * AXX Evolution 3.0 — Magic Pen SceneDocument v2 History & Undo/Redo Controller (PR-03).
 * Lazy-loaded module; releases all DOM listeners and references on unmount.
 * Never alters PresentationPlan v1 when magic_scene_v2 flag is OFF.
 */
(function (global) {
  'use strict';

  function createSceneHistoryController(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onRevisionSelect = typeof opts.onRevisionSelect === 'function' ? opts.onRevisionSelect : function () {};
    const onUndo = typeof opts.onUndo === 'function' ? opts.onUndo : function () {};
    const onRedo = typeof opts.onRedo === 'function' ? opts.onRedo : function () {};

    let mounted = false;
    let currentDocumentId = null;
    let currentRevision = 1;
    let revisions = [];
    const cleanupFns = [];

    function bindKeydown(target) {
      function handler(ev) {
        if (!mounted) return;
        const isCtrl = ev.ctrlKey || ev.metaKey;
        if (isCtrl && !ev.shiftKey && ev.key.toLowerCase() === 'z') {
          ev.preventDefault();
          onUndo({ document_id: currentDocumentId, base_revision: currentRevision });
        } else if (isCtrl && (ev.key.toLowerCase() === 'y' || (ev.shiftKey && ev.key.toLowerCase() === 'z'))) {
          ev.preventDefault();
          onRedo({ document_id: currentDocumentId, base_revision: currentRevision });
        }
      }
      target.addEventListener('keydown', handler);
      cleanupFns.push(function () {
        target.removeEventListener('keydown', handler);
      });
    }

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';
      const bar = document.createElement('div');
      bar.className = 'axx-scene-history-bar';
      bar.setAttribute('role', 'toolbar');
      bar.setAttribute('aria-label', 'Historial de revisiones de escena');

      const revBadge = document.createElement('span');
      revBadge.className = 'axx-scene-rev-badge';
      revBadge.textContent = 'Rev v' + String(currentRevision);
      bar.appendChild(revBadge);

      const undoBtn = document.createElement('button');
      undoBtn.type = 'button';
      undoBtn.className = 'axx-scene-history-btn';
      undoBtn.textContent = 'Deshacer';
      undoBtn.disabled = currentRevision <= 1;
      const undoClick = function () {
        onUndo({ document_id: currentDocumentId, base_revision: currentRevision });
      };
      undoBtn.addEventListener('click', undoClick);
      cleanupFns.push(function () {
        undoBtn.removeEventListener('click', undoClick);
      });
      bar.appendChild(undoBtn);

      const redoBtn = document.createElement('button');
      redoBtn.type = 'button';
      redoBtn.className = 'axx-scene-history-btn';
      redoBtn.textContent = 'Rehacer';
      const redoClick = function () {
        onRedo({ document_id: currentDocumentId, base_revision: currentRevision });
      };
      redoBtn.addEventListener('click', redoClick);
      cleanupFns.push(function () {
        redoBtn.removeEventListener('click', redoClick);
      });
      bar.appendChild(redoBtn);

      if (revisions.length > 0) {
        const select = document.createElement('select');
        select.className = 'axx-scene-rev-select';
        select.setAttribute('aria-label', 'Seleccionar revisión');
        revisions.forEach(function (item) {
          const opt = document.createElement('option');
          opt.value = String(item.revision);
          opt.textContent = 'v' + String(item.revision) + ' (' + String(item.operation_id || 'init') + ')';
          if (item.revision === currentRevision) opt.selected = true;
          select.appendChild(opt);
        });
        const changeHandler = function () {
          const rev = parseInt(select.value, 10);
          if (!Number.isNaN(rev)) {
            onRevisionSelect({ document_id: currentDocumentId, revision: rev });
          }
        };
        select.addEventListener('change', changeHandler);
        cleanupFns.push(function () {
          select.removeEventListener('change', changeHandler);
        });
        bar.appendChild(select);
      }

      container.appendChild(bar);
    }

    return {
      mount: function (docState, revList) {
        mounted = true;
        if (docState) {
          currentDocumentId = docState.document_id || null;
          currentRevision = docState.revision || 1;
        }
        revisions = Array.isArray(revList) ? revList.slice() : [];
        if (container) bindKeydown(container);
        render();
      },
      update: function (docState, revList) {
        if (docState) {
          currentDocumentId = docState.document_id || currentDocumentId;
          currentRevision = docState.revision || currentRevision;
        }
        if (Array.isArray(revList)) {
          revisions = revList.slice();
        }
        render();
      },
      unmount: function () {
        mounted = false;
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
      isMounted: function () {
        return mounted;
      },
    };
  }

  global.AxxSceneHistory = { createSceneHistoryController: createSceneHistoryController };
})(typeof window !== 'undefined' ? window : globalThis);
