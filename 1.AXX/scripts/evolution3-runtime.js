/**
 * AXX Evolution 3.0 — Unified Frontend Runtime Bridge.
 * Connects Spatial Studio (Diagram/CAD/Motion/Asset Gate), Agent Designer, Multi-Agent Timeline,
 * Background Workspaces (Leases/FocusGuard/Virtual Cursors/VM), and Code Studio controllers
 * to the authenticated Axx.backendRequest transport (/axx-api/*).
 */
(function (global) {
  'use strict';

  const Axx = global.Axx || (global.Axx = {});

  function callBackend(method, path, body) {
    if (typeof Axx.backendRequest === 'function') {
      return Axx.backendRequest(method, path, body);
    }
    const opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined && method !== 'GET') {
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        throw new Error('HTTP ' + r.status + ' on ' + path);
      }
      return r.json();
    });
  }

  const evolution3 = {
    version: '3.0.0',
    request: callBackend,

    // Feature Flags
    getFlags: function () {
      return callBackend('GET', '/axx-api/agents/v1/flags');
    },
    setFlag: function (flagId, enabled, expectedRevision, reason, gateReceiptRef) {
      return callBackend('POST', '/axx-api/agents/v1/flags/set', {
        flag_id: flagId,
        enabled: Boolean(enabled),
        expected_revision: Number(expectedRevision || 1),
        reason: reason || 'ui_toggle',
        gate_receipt_ref: gateReceiptRef || 'GATE_G13',
      });
    },

    // Agent Designer & Profiles
    listProfiles: function () {
      return callBackend('GET', '/axx-api/agents/v1/profiles');
    },
    createProfile: function (profile) {
      return callBackend('POST', '/axx-api/agents/v1/profiles', profile);
    },
    updateProfile: function (agentId, patch, expectedRevision) {
      return callBackend('POST', '/axx-api/agents/v1/profiles/update', {
        agent_id: agentId,
        patch: patch,
        expected_revision: expectedRevision,
      });
    },
    convertChat: function (conversationId, leadAgentId, memberAgentIds) {
      return callBackend('POST', '/axx-api/agents/v1/bindings/convert', {
        conversation_id: conversationId,
        lead_agent_id: leadAgentId,
        member_agent_ids: memberAgentIds || [],
      });
    },

    // Code Studio
    registerCodeProject: function (projectId, projectRoot) {
      return callBackend('POST', '/axx-api/code/v1/projects/register', {
        project_id: projectId,
        project_root: projectRoot,
      });
    },
    readCodeDocument: function (projectId, path) {
      return callBackend('POST', '/axx-api/code/v1/documents/read', {
        project_id: projectId,
        path: path,
      });
    },
    saveCodeDocument: function (projectId, path, newContent, expectedSha256) {
      return callBackend('POST', '/axx-api/code/v1/documents/save', {
        project_id: projectId,
        path: path,
        new_content: newContent,
        expected_sha256: expectedSha256,
      });
    },

    // Workspaces & VM
    probeVm: function () {
      return callBackend('GET', '/axx-api/workspaces/v1/vm/probe');
    },
    revokeHostInput: function () {
      return callBackend('POST', '/axx-api/workspaces/v1/focus-guard/revoke', {});
    },

    // Controllers Registry
    controllers: {
      sceneHistory: global.AxxSceneHistory || null,
      diagramEditor: global.AxxDiagramEditor || null,
      cadEditor: global.AxxCadEditor || null,
      timelineEditor: global.AxxTimelineEditor || null,
      assetBrowser: global.AxxAssetBrowser || null,
      agentDesigner: global.AxxAgentDesigner || null,
      agentRoster: global.AxxAgentRoster || null,
      agentTimeline: global.AxxAgentTimeline ? new global.AxxAgentTimeline.AgentTimelineController() : null,
      teamChat: global.AxxTeamChat ? new global.AxxTeamChat.TeamChatController() : null,
      workApprovals: global.AxxWorkApprovals ? new global.AxxWorkApprovals.WorkApprovalsController() : null,
      codeWorkspace: global.AxxCodeWorkspace ? new global.AxxCodeWorkspace.CodeWorkspaceController() : null,
      codeEditor: global.AxxCodeEditor ? new global.AxxCodeEditor.CodeEditorAdapter() : null,
      codeDiff: global.AxxCodeDiff || null,
      gitPanel: global.AxxGitPanel ? new global.AxxGitPanel.GitWorktreePanel() : null,
      problemsPanel: global.AxxProblemsPanel ? new global.AxxProblemsPanel.ProblemsPanelController() : null,
      terminalPanel: global.AxxTerminalPanel ? new global.AxxTerminalPanel.TerminalPanelController() : null,
      workspaceSwitcher: global.AxxWorkspaceSwitcher ? new global.AxxWorkspaceSwitcher.WorkspaceSwitcherController() : null,
      virtualCursors: global.AxxVirtualCursors ? new global.AxxVirtualCursors.VirtualCursorOverlay() : null,
      browserStage: global.AxxBrowserStage ? new global.AxxBrowserStage.BrowserStageController() : null,
      windowStage: global.AxxWindowStage ? new global.AxxWindowStage.WindowStageController() : null,
      vmStage: global.AxxVmStage ? new global.AxxVmStage.VmStageController() : null,
    },
  };

  Axx.evolution3 = evolution3;
})(typeof window !== 'undefined' ? window : globalThis);
