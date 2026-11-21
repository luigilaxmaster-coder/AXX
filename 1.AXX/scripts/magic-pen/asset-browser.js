/**
 * AXX Evolution 3.0 — Magic Pen Asset Gate Browser & Diorama Mode Selector (PR-07 & PR-08).
 * Displays content-addressed assets with license provenance, LOD badges, and Diorama/Codevember
 * scene presets while leaving the main AXX avatar untouched.
 * Lazy-loaded; releases all event listeners on unmount.
 */
(function (global) {
  'use strict';

  function createAssetBrowser(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onSelectAsset = typeof opts.onSelectAsset === 'function' ? opts.onSelectAsset : function () {};
    const onToggleDiorama = typeof opts.onToggleDiorama === 'function' ? opts.onToggleDiorama : function () {};

    let mounted = false;
    let assets = [];
    let currentPreset = '';
    const cleanupFns = [];

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';

      const root = document.createElement('div');
      root.className = 'axx-asset-browser-panel';
      root.setAttribute('role', 'region');
      root.setAttribute('aria-label', 'Catálogo Asset Gate y Diorama');

      const presetSelect = document.createElement('select');
      presetSelect.className = 'axx-diorama-preset-select';
      presetSelect.setAttribute('aria-label', 'Modo Diorama / Material de escena');
      [
        ['', 'Conceptual estándar'],
        ['toon_diorama', 'Diorama Toon'],
        ['pixel_maquette', 'Maqueta Pixel'],
        ['studio_clay', 'Arcilla de estudio'],
        ['technical_blueprint_diorama', 'Plano técnico'],
      ].forEach(function (pair) {
        const opt = document.createElement('option');
        opt.value = pair[0];
        opt.textContent = pair[1];
        if (pair[0] === currentPreset) opt.selected = true;
        presetSelect.appendChild(opt);
      });
      const onChangePreset = function () {
        currentPreset = presetSelect.value;
        onToggleDiorama({
          target_surface: 'magic_pen_scene',
          diorama_preset: currentPreset || null,
          enabled: Boolean(currentPreset),
        });
      };
      presetSelect.addEventListener('change', onChangePreset);
      cleanupFns.push(function () {
        presetSelect.removeEventListener('change', onChangePreset);
      });
      root.appendChild(presetSelect);

      const list = document.createElement('div');
      list.className = 'axx-asset-list';
      assets.forEach(function (item) {
        const card = document.createElement('div');
        card.className = 'axx-asset-card';
        card.setAttribute('data-asset-id', item.asset_id || item.component_id || '');

        const title = document.createElement('div');
        title.className = 'axx-asset-title';
        title.textContent = String(item.logical_name || item.label || item.asset_id);
        card.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'axx-asset-meta';
        meta.textContent =
          'Licencia: ' +
          String(item.license || 'MIT') +
          (item.lod_level ? ' | ' + String(item.lod_level).toUpperCase() : '') +
          (item.credit_line ? ' | ' + String(item.credit_line) : '');
        card.appendChild(meta);

        const useBtn = document.createElement('button');
        useBtn.type = 'button';
        useBtn.textContent = 'Insertar en escena';
        const onUse = function () {
          onSelectAsset(item);
        };
        useBtn.addEventListener('click', onUse);
        cleanupFns.push(function () {
          useBtn.removeEventListener('click', onUse);
        });
        card.appendChild(useBtn);

        list.appendChild(card);
      });
      root.appendChild(list);
      container.appendChild(root);
    }

    return {
      mount: function (initialAssets, preset) {
        mounted = true;
        assets = Array.isArray(initialAssets) ? initialAssets.slice() : [];
        currentPreset = preset || '';
        render();
      },
      setAssets: function (nextAssets) {
        assets = Array.isArray(nextAssets) ? nextAssets.slice() : [];
        render();
      },
      unmount: function () {
        mounted = false;
        assets = [];
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxAssetBrowser = { createAssetBrowser: createAssetBrowser };
})(typeof window !== 'undefined' ? window : globalThis);
