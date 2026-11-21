/**
 * AXX Evolution 3.0 — Agent Designer 10-Tab Configuration Controller (PR-12 / AGENT-01, AGENT-02, T-AG-007).
 * Reversible UX: Preview -> Aplicar -> Descartar. Visual previews never mutate global AXX settings.
 * Implements roving tabindex accessibility across tabs and 24-form / 9-palette selector.
 * Lazy-loaded; releases all event listeners on unmount.
 */
(function (global) {
  'use strict';

  const DESIGNER_TABS = [
    { id: 'identity', label: 'Identidad' },
    { id: 'appearance', label: 'Apariencia' },
    { id: 'intelligence', label: 'Inteligencia' },
    { id: 'voice', label: 'Voz' },
    { id: 'memory', label: 'Memoria' },
    { id: 'tools', label: 'Herramientas' },
    { id: 'computer', label: 'Computadora' },
    { id: 'autonomy', label: 'Autonomía' },
    { id: 'collaboration', label: 'Colaboración' },
    { id: 'resources', label: 'Recursos' },
  ];

  const CANONICAL_FORMS = [
    'Core', 'Flow', 'Pearl', 'Torus', 'Split', 'Wave', 'Bloom', 'Fold',
    'Spike', 'Drift', 'Orbit', 'Morph', 'Cushion', 'Trefoil', 'Nova', 'Heart',
    'Infinity', 'Helix', 'Knot', 'Petal', 'Prism', 'Capsule', 'Crescent', 'Ripple',
  ];

  const CANONICAL_PALETTES = [
    'Obsidian', 'Nebula', 'Ocean', 'Sunset', 'Amethyst', 'Emerald', 'Champagne', 'Silver', 'Void',
  ];

  function createAgentDesigner(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onPreview = typeof opts.onPreview === 'function' ? opts.onPreview : function () {};
    const onApply = typeof opts.onApply === 'function' ? opts.onApply : function () {};
    const onDiscard = typeof opts.onDiscard === 'function' ? opts.onDiscard : function () {};

    let mounted = false;
    let activeTabIndex = 0;
    let committedProfile = null;
    let draftProfile = null;
    let previewActive = false;
    const cleanupFns = [];

    function defaultDraft() {
      return {
        schema_version: '1.0',
        agent_id: 'axx-agent-new',
        revision: 1,
        name: 'Nuevo Agente AXX',
        role: 'general_assistant',
        description: '',
        instructions: '',
        enabled: true,
        appearance: {
          form_id: 0,
          palette_id: 0,
          catalog_version: 'axx-avatar-24x9-v1',
          material_preset: 'obsidian',
          scale: 1.0,
          reduce_motion: false,
        },
        intelligence: {
          route: 'manual',
          fallback: 'ask',
          max_parallel_turns: 1,
        },
        voice: {
          language: 'es-DO',
          auto_speak: false,
          speed: 1.0,
        },
        workspace: {
          runtime: 'api',
          foreground_policy: 'ask',
          allowed_roots: [],
        },
        permissions: {
          tool_grant_refs: [],
          delegation_enabled: false,
          max_delegate_depth: 0,
        },
        limits: {
          max_concurrent_jobs: 1,
          max_retries: 1,
          max_cost_usd: 0,
        },
        memory_scope: 'agent',
      };
    }

    function render() {
      if (!container || !mounted || !draftProfile) return;
      container.textContent = '';

      const panel = document.createElement('div');
      panel.className = 'axx-agent-designer-modal';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-label', 'Diseñador de Agente AXX');

      const tabList = document.createElement('div');
      tabList.className = 'axx-agent-designer-tabs';
      tabList.setAttribute('role', 'tablist');

      DESIGNER_TABS.forEach(function (tab, idx) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('role', 'tab');
        btn.setAttribute('data-tab-id', tab.id);
        btn.setAttribute('aria-selected', idx === activeTabIndex ? 'true' : 'false');
        btn.setAttribute('tabindex', idx === activeTabIndex ? '0' : '-1');
        btn.textContent = tab.label;

        const onClick = function () {
          activeTabIndex = idx;
          render();
        };
        const onKey = function (ev) {
          if (ev.key === 'ArrowRight') {
            ev.preventDefault();
            activeTabIndex = (activeTabIndex + 1) % DESIGNER_TABS.length;
            render();
          } else if (ev.key === 'ArrowLeft') {
            ev.preventDefault();
            activeTabIndex = (activeTabIndex - 1 + DESIGNER_TABS.length) % DESIGNER_TABS.length;
            render();
          }
        };
        btn.addEventListener('click', onClick);
        btn.addEventListener('keydown', onKey);
        cleanupFns.push(function () {
          btn.removeEventListener('click', onClick);
          btn.removeEventListener('keydown', onKey);
        });
        tabList.appendChild(btn);
      });
      panel.appendChild(tabList);

      const body = document.createElement('div');
      body.className = 'axx-agent-designer-body';
      body.setAttribute('role', 'tabpanel');
      const currentTab = DESIGNER_TABS[activeTabIndex].id;

      if (currentTab === 'appearance') {
        const formInfo = document.createElement('div');
        formInfo.textContent =
          'Forma: ' +
          CANONICAL_FORMS[draftProfile.appearance.form_id] +
          ' (#' +
          String(draftProfile.appearance.form_id) +
          ') | Paleta: ' +
          CANONICAL_PALETTES[draftProfile.appearance.palette_id];
        body.appendChild(formInfo);
      } else {
        const info = document.createElement('div');
        info.textContent =
          'Agente: ' +
          String(draftProfile.name) +
          ' | Rol: ' +
          String(draftProfile.role) +
          ' | Sección: ' +
          DESIGNER_TABS[activeTabIndex].label;
        body.appendChild(info);
      }
      panel.appendChild(body);

      const footer = document.createElement('div');
      footer.className = 'axx-agent-designer-footer';

      const previewBtn = document.createElement('button');
      previewBtn.type = 'button';
      previewBtn.textContent = 'Previsualizar';
      const onPrevClick = function () {
        previewActive = true;
        onPreview(JSON.parse(JSON.stringify(draftProfile)));
      };
      previewBtn.addEventListener('click', onPrevClick);
      cleanupFns.push(function () {
        previewBtn.removeEventListener('click', onPrevClick);
      });
      footer.appendChild(previewBtn);

      const applyBtn = document.createElement('button');
      applyBtn.type = 'button';
      applyBtn.textContent = 'Aplicar';
      const onAppClick = function () {
        committedProfile = JSON.parse(JSON.stringify(draftProfile));
        previewActive = false;
        onApply(JSON.parse(JSON.stringify(committedProfile)));
      };
      applyBtn.addEventListener('click', onAppClick);
      cleanupFns.push(function () {
        applyBtn.removeEventListener('click', onAppClick);
      });
      footer.appendChild(applyBtn);

      const discardBtn = document.createElement('button');
      discardBtn.type = 'button';
      discardBtn.textContent = 'Descartar';
      const onDiscClick = function () {
        draftProfile = JSON.parse(JSON.stringify(committedProfile));
        previewActive = false;
        onDiscard(JSON.parse(JSON.stringify(committedProfile)));
        render();
      };
      discardBtn.addEventListener('click', onDiscClick);
      cleanupFns.push(function () {
        discardBtn.removeEventListener('click', onDiscClick);
      });
      footer.appendChild(discardBtn);

      panel.appendChild(footer);
      container.appendChild(panel);
    }

    return {
      mount: function (initialProfile) {
        mounted = true;
        activeTabIndex = 0;
        committedProfile = initialProfile ? JSON.parse(JSON.stringify(initialProfile)) : defaultDraft();
        draftProfile = JSON.parse(JSON.stringify(committedProfile));
        previewActive = false;
        render();
      },
      selectTab: function (tabId) {
        const idx = DESIGNER_TABS.findIndex(function (t) { return t.id === tabId; });
        if (idx >= 0) {
          activeTabIndex = idx;
          render();
        }
      },
      setAppearanceDraft: function (formId, paletteId, materialPreset) {
        if (!draftProfile) return;
        if (Number.isInteger(formId) && formId >= 0 && formId <= 23) {
          draftProfile.appearance.form_id = formId;
        }
        if (Number.isInteger(paletteId) && paletteId >= 0 && paletteId <= 8) {
          draftProfile.appearance.palette_id = paletteId;
        }
        if (materialPreset) {
          draftProfile.appearance.material_preset = String(materialPreset);
        }
        render();
      },
      getDraft: function () {
        return draftProfile ? JSON.parse(JSON.stringify(draftProfile)) : null;
      },
      getCommitted: function () {
        return committedProfile ? JSON.parse(JSON.stringify(committedProfile)) : null;
      },
      isPreviewActive: function () {
        return previewActive;
      },
      unmount: function () {
        mounted = false;
        previewActive = false;
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxAgentDesigner = {
    DESIGNER_TABS: DESIGNER_TABS,
    CANONICAL_FORMS: CANONICAL_FORMS,
    CANONICAL_PALETTES: CANONICAL_PALETTES,
    createAgentDesigner: createAgentDesigner,
  };
})(typeof window !== 'undefined' ? window : globalThis);
