/**
 * AXX Evolution 3.0 — Magic Pen CAD Studio Parametric Controller (PR-05).
 * Displays parametric dimensions, provenance badges (observed/documented/inferred/assumed),
 * engineering-unverified badge, section cut slider, explode slider, and STEP/GLB export triggers.
 * Lazy-loaded; releases all event listeners on unmount.
 */
(function (global) {
  'use strict';

  function createCadEditor(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onDimensionChange = typeof opts.onDimensionChange === 'function' ? opts.onDimensionChange : function () {};
    const onSectionChange = typeof opts.onSectionChange === 'function' ? opts.onSectionChange : function () {};
    const onExplodeChange = typeof opts.onExplodeChange === 'function' ? opts.onExplodeChange : function () {};
    const onExportStep = typeof opts.onExportStep === 'function' ? opts.onExportStep : function () {};

    let mounted = false;
    let sceneDoc = null;
    const cleanupFns = [];

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';
      if (!sceneDoc) return;

      const root = document.createElement('div');
      root.className = 'axx-cad-studio-panel';
      root.setAttribute('role', 'region');
      root.setAttribute('aria-label', 'Estudio CAD Paramétrico');

      const header = document.createElement('div');
      header.className = 'axx-cad-header';

      const fidelityBadge = document.createElement('span');
      fidelityBadge.className = 'axx-cad-fidelity-badge';
      fidelityBadge.textContent = 'Fidelidad: ' + String(sceneDoc.fidelity || 'conceptual') + ' (' + String(sceneDoc.units || 'mm') + ')';
      header.appendChild(fidelityBadge);

      const engBadge = document.createElement('span');
      engBadge.className = 'axx-cad-eng-badge';
      engBadge.textContent = 'engineering-unverified';
      header.appendChild(engBadge);

      const exportBtn = document.createElement('button');
      exportBtn.type = 'button';
      exportBtn.className = 'axx-cad-export-btn';
      exportBtn.textContent = 'Exportar STEP / GLB';
      const onExport = function () {
        onExportStep({ document_id: sceneDoc.document_id, revision: sceneDoc.revision });
      };
      exportBtn.addEventListener('click', onExport);
      cleanupFns.push(function () {
        exportBtn.removeEventListener('click', onExport);
      });
      header.appendChild(exportBtn);
      root.appendChild(header);

      (sceneDoc.objects || []).forEach(function (obj) {
        const card = document.createElement('div');
        card.className = 'axx-cad-part-card';
        card.setAttribute('data-part-id', obj.id);

        const title = document.createElement('div');
        title.className = 'axx-cad-part-title';
        title.textContent = String(obj.name || obj.id) + ' [' + String(obj.measured_source || 'assumed') + ']';
        card.appendChild(title);

        const dims = (obj.properties && obj.properties.dimensions) || {};
        const sources = (obj.properties && obj.properties.dimension_sources) || {};
        Object.keys(dims).forEach(function (dimKey) {
          const row = document.createElement('label');
          row.className = 'axx-cad-dim-row';
          row.textContent = dimKey + ' (' + String(sources[dimKey] || obj.measured_source || 'assumed') + '): ';

          const input = document.createElement('input');
          input.type = 'number';
          input.step = '0.1';
          input.min = '0.01';
          input.value = String(dims[dimKey]);
          const onChange = function () {
            const val = parseFloat(input.value);
            if (Number.isFinite(val) && val > 0) {
              onDimensionChange({
                document_id: sceneDoc.document_id,
                base_revision: sceneDoc.revision,
                part_id: obj.id,
                dimension: dimKey,
                value: val,
              });
            }
          };
          input.addEventListener('change', onChange);
          cleanupFns.push(function () {
            input.removeEventListener('change', onChange);
          });
          row.appendChild(input);
          card.appendChild(row);
        });

        root.appendChild(card);
      });

      container.appendChild(root);
    }

    return {
      mount: function (initialDoc) {
        mounted = true;
        sceneDoc = initialDoc ? JSON.parse(JSON.stringify(initialDoc)) : null;
        render();
      },
      update: function (nextDoc) {
        sceneDoc = nextDoc ? JSON.parse(JSON.stringify(nextDoc)) : sceneDoc;
        render();
      },
      setSectionCut: function (axis, offset) {
        onSectionChange({ axis: axis, offset: offset });
      },
      setExplodeFactor: function (factor) {
        onExplodeChange({ explode_factor: factor });
      },
      unmount: function () {
        mounted = false;
        sceneDoc = null;
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxCadEditor = { createCadEditor: createCadEditor };
})(typeof window !== 'undefined' ? window : globalThis);
