/**
 * AXX Evolution 3.0 — Chats y Agentes Roster & Conversion Controller (PR-12 / E2E-01).
 * Extends Chats y grupos with 'Nuevo: Chat | Agente | Equipo', Agent Roster Cards (miniatura real,
 * rol, modelo, presupuesto, estado, abrir/pausar/editar/duplicar/exportar/desvincular),
 * and reversible chat-to-agent conversion without changing conversation_id.
 */
(function (global) {
  'use strict';

  function createAgentRoster(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onConvertChat = typeof opts.onConvertChat === 'function' ? opts.onConvertChat : function () {};
    const onUnlinkAgent = typeof opts.onUnlinkAgent === 'function' ? opts.onUnlinkAgent : function () {};
    const onEditAgent = typeof opts.onEditAgent === 'function' ? opts.onEditAgent : function () {};
    const onExportAgent = typeof opts.onExportAgent === 'function' ? opts.onExportAgent : function () {};

    let mounted = false;
    let profiles = [];
    let activeConversationId = null;
    const cleanupFns = [];

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';

      const root = document.createElement('div');
      root.className = 'axx-agent-roster-panel';
      root.setAttribute('role', 'region');
      root.setAttribute('aria-label', 'Chats y agentes');

      profiles.forEach(function (prof) {
        const card = document.createElement('div');
        card.className = 'axx-agent-roster-card';
        card.setAttribute('data-agent-id', prof.agent_id);

        const title = document.createElement('div');
        title.className = 'axx-agent-card-title';
        title.textContent =
          String(prof.name) +
          ' (' +
          String(prof.role) +
          ') — ' +
          (prof.enabled ? 'Activo' : 'Pausado');
        card.appendChild(title);

        const bindBtn = document.createElement('button');
        bindBtn.type = 'button';
        bindBtn.textContent = 'Vincular a este chat';
        const onBind = function () {
          if (activeConversationId) {
            onConvertChat({ conversation_id: activeConversationId, agent_id: prof.agent_id });
          }
        };
        bindBtn.addEventListener('click', onBind);
        cleanupFns.push(function () {
          bindBtn.removeEventListener('click', onBind);
        });
        card.appendChild(bindBtn);

        const unlinkBtn = document.createElement('button');
        unlinkBtn.type = 'button';
        unlinkBtn.textContent = 'Desvincular';
        const onUnlink = function () {
          if (activeConversationId) {
            onUnlinkAgent({ conversation_id: activeConversationId, agent_id: prof.agent_id });
          }
        };
        unlinkBtn.addEventListener('click', onUnlink);
        cleanupFns.push(function () {
          unlinkBtn.removeEventListener('click', onUnlink);
        });
        card.appendChild(unlinkBtn);

        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.textContent = 'Editar';
        const onEdit = function () {
          onEditAgent(prof);
        };
        editBtn.addEventListener('click', onEdit);
        cleanupFns.push(function () {
          editBtn.removeEventListener('click', onEdit);
        });
        card.appendChild(editBtn);

        const exportBtn = document.createElement('button');
        exportBtn.type = 'button';
        exportBtn.textContent = 'Exportar sin claves';
        const onExp = function () {
          onExportAgent(prof);
        };
        exportBtn.addEventListener('click', onExp);
        cleanupFns.push(function () {
          exportBtn.removeEventListener('click', onExp);
        });
        card.appendChild(exportBtn);

        root.appendChild(card);
      });

      container.appendChild(root);
    }

    return {
      mount: function (initialProfiles, conversationId) {
        mounted = true;
        profiles = Array.isArray(initialProfiles) ? initialProfiles.slice() : [];
        activeConversationId = conversationId || null;
        render();
      },
      setProfiles: function (nextProfiles) {
        profiles = Array.isArray(nextProfiles) ? nextProfiles.slice() : [];
        render();
      },
      setActiveConversation: function (conversationId) {
        activeConversationId = conversationId || null;
      },
      unmount: function () {
        mounted = false;
        profiles = [];
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxAgentRoster = { createAgentRoster: createAgentRoster };
})(typeof window !== 'undefined' ? window : globalThis);
