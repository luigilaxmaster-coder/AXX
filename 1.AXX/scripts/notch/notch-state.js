/* Pure deterministic state machine and layout resolver for AXX Notch Presentation.
 * Zero business execution authority; enforces INV-01..INV-07 invariants. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchState = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  const PHYSICAL_MODES = Object.freeze(['free', 'approach', 'retracting', 'docking', 'docked', 'undocking']);
  const SURFACE_SIZES = Object.freeze(['compact', 'ambient', 'peek', 'expanded', 'stage']);
  const CONTENT_MODES = Object.freeze([
    'home', 'orbit', 'parallel', 'portal', 'intent',
    'media', 'chat', 'voice', 'agents', 'transfer', 'magicPen', 'resources', 'recall', 'settings'
  ]);
  const ATTENTION_LEVELS = Object.freeze(['idle', 'active', 'progress', 'completed', 'approval', 'error', 'offline']);
  const INTERACTION_MODES = Object.freeze(['none', 'pointer', 'hoverIntent', 'keyboard', 'dragEnter', 'dragActive', 'focused']);
  const VISIBILITY_POLICIES = Object.freeze(['normal', 'presentation', 'fullscreenSuppressed', 'privacySuppressed', 'userHidden']);

  const ATTENTION_PRIORITY = Object.freeze({
    offline: 1,
    idle: 0,
    active: 2,
    progress: 3,
    completed: 4,
    error: 5,
    approval: 6
  });

  function clamp(v, lo, hi) {
    const min = Math.min(lo, hi);
    const max = Math.max(lo, hi);
    return Math.max(min, Math.min(max, v));
  }

  function createInitialState(overrides = {}) {
    return {
      enabled: Boolean(overrides.enabled),
      physical: 'free',
      size: 'compact',
      content: 'home',
      attention: 'idle',
      interaction: 'none',
      visibility: 'normal',
      dockEpoch: 0,
      geometryRevision: 0,
      layoutRevision: 0,
      activityRevision: 0,
      activityIds: [],
      selectedActivityId: null,
      pinnedActivityId: overrides.pinnedActivityId || null,
      prePortalState: null,
      stageOpen: false,
      snapshot: null,
      displayId: overrides.displayId || 'primary',
      lastError: null,
      handledTokens: [],
      sourceEpochs: {},
      entityRevisions: {},
      explicitIdentityEditRevision: 0,
      contextFrozen: false,
      frozenContext: null,
      stageDetached: false,
      stagePos: null
    };
  }

  function isDockedPresentation(state) {
    return state.physical === 'docking' || state.physical === 'docked' || state.physical === 'undocking';
  }

  function tendrilsAllowed(state) {
    return state.physical === 'free' || state.physical === 'approach';
  }

  function isNotchVisible(state) {
    if (!state.enabled) return false;
    if (!isDockedPresentation(state)) return false;
    if (state.visibility === 'userHidden' || state.visibility === 'fullscreenSuppressed') return false;
    return true;
  }

  function recordToken(tokens, token) {
    if (!token) return tokens;
    const next = tokens.filter(t => t !== token);
    next.push(token);
    if (next.length > 64) next.shift();
    return next;
  }

  function highestAttention(projections, backendOffline) {
    if (backendOffline) return 'offline';
    let best = 'idle';
    let bestRank = 0;
    for (const item of projections) {
      if (!item) continue;
      let att = 'idle';
      if (item.status === 'awaiting_user') att = 'approval';
      else if (item.status === 'failed') att = 'error';
      else if (item.status === 'completed') att = 'completed';
      else if (item.status === 'running') att = item.progress ? 'progress' : 'active';
      else if (item.status === 'pending') att = 'active';
      const rank = ATTENTION_PRIORITY[att] || 0;
      if (rank > bestRank) {
        bestRank = rank;
        best = att;
      }
    }
    return best;
  }

  function reduce(state, event) {
    if (!event || typeof event.type !== 'string') {
      return { next: state, effects: [] };
    }
    const effects = [];

    switch (event.type) {
      case 'SET_ENABLED': {
        const enabled = Boolean(event.enabled);
        if (enabled === state.enabled) return { next: state, effects };
        if (!enabled) {
          const wasDocked = state.physical !== 'free';
          const next = {
            ...state,
            enabled: false,
            physical: 'free',
            size: 'compact',
            content: 'home',
            interaction: 'none',
            prePortalState: null,
            stageOpen: false,
            dockEpoch: state.dockEpoch + 1,
            geometryRevision: state.geometryRevision + 1,
            layoutRevision: state.layoutRevision + 1
          };
          if (wasDocked) {
            if (state.snapshot) effects.push({ type: 'RESTORE_SNAPSHOT', snapshot: state.snapshot, epoch: next.dockEpoch });
            effects.push({ type: 'RESUME_3D_RENDERER', epoch: next.dockEpoch });
            effects.push({ type: 'RELEASE_FOCUS', epoch: next.dockEpoch });
            effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: 'free', epoch: next.dockEpoch, revision: next.geometryRevision });
            next.snapshot = null;
          }
          effects.push({ type: 'PERSIST_PREFS' });
          return { next, effects };
        }
        effects.push({ type: 'PERSIST_PREFS' });
        return { next: { ...state, enabled: true, layoutRevision: state.layoutRevision + 1 }, effects };
      }

      case 'DRAG_APPROACH_ENTER': {
        if (!state.enabled) return { next: state, effects };
        if (state.physical !== 'free') return { next: state, effects };
        return {
          next: {
            ...state,
            physical: 'approach',
            displayId: event.displayId || state.displayId,
            layoutRevision: state.layoutRevision + 1
          },
          effects: [{ type: 'SHOW_DOCK_PREVIEW', displayId: event.displayId || state.displayId }]
        };
      }

      case 'DRAG_APPROACH_LEAVE': {
        if (state.physical !== 'approach') return { next: state, effects };
        return {
          next: { ...state, physical: 'free', layoutRevision: state.layoutRevision + 1 },
          effects: [{ type: 'HIDE_DOCK_PREVIEW' }]
        };
      }

      case 'DOCK_COMMIT':
      case 'DOCK_COMMAND': {
        if (!state.enabled) return { next: state, effects };
        if (state.physical !== 'free' && state.physical !== 'approach') return { next: state, effects };
        if (event.token && state.handledTokens.includes(event.token)) return { next: state, effects };
        const nextEpoch = state.dockEpoch + 1;
        const snapshot = event.snapshot || state.snapshot;
        if (!snapshot || !snapshot.identity) {
          return {
            next: { ...state, physical: 'free', lastError: 'SNAPSHOT_INVALID' },
            effects: [{ type: 'HIDE_DOCK_PREVIEW' }]
          };
        }
        const next = {
          ...state,
          physical: 'retracting',
          dockEpoch: nextEpoch,
          snapshot,
          displayId: event.displayId || snapshot.freePosition?.displayId || state.displayId,
          lastError: null,
          handledTokens: recordToken(state.handledTokens, event.token),
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({ type: 'HIDE_DOCK_PREVIEW' });
        effects.push({ type: 'RETRACT_TENDRILS', epoch: nextEpoch });
        return { next, effects };
      }

      case 'RETRACT_COMPLETE': {
        if (state.physical !== 'retracting') return { next: state, effects };
        if (event.epoch !== state.dockEpoch) return { next: state, effects };
        if (event.tentacleLinks !== 0 || !state.snapshot) {
          const rollbackEpoch = state.dockEpoch + 1;
          return {
            next: {
              ...state,
              physical: 'free',
              dockEpoch: rollbackEpoch,
              lastError: 'TENTACLE_RETRACT_FAILED',
              layoutRevision: state.layoutRevision + 1
            },
            effects: [{ type: 'RESTORE_SNAPSHOT', snapshot: state.snapshot, epoch: rollbackEpoch }]
          };
        }
        const nextRev = state.geometryRevision + 1;
        const next = {
          ...state,
          physical: 'docking',
          size: 'compact',
          geometryRevision: nextRev,
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({ type: 'DISABLE_TENDRILS', epoch: state.dockEpoch });
        effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: 'docking', size: 'compact', epoch: state.dockEpoch, revision: nextRev, displayId: next.displayId });
        return { next, effects };
      }

      case 'TRANSITION_CANCEL':
      case 'RETRACT_TIMEOUT': {
        if (state.physical === 'approach') {
          return {
            next: { ...state, physical: 'free', layoutRevision: state.layoutRevision + 1 },
            effects: [{ type: 'HIDE_DOCK_PREVIEW' }]
          };
        }
        if (state.physical === 'retracting' || state.physical === 'docking') {
          const nextEpoch = state.dockEpoch + 1;
          const nextRev = state.geometryRevision + 1;
          return {
            next: {
              ...state,
              physical: 'free',
              size: 'compact',
              dockEpoch: nextEpoch,
              geometryRevision: nextRev,
              layoutRevision: state.layoutRevision + 1,
              lastError: event.type === 'RETRACT_TIMEOUT' ? 'RETRACT_TIMEOUT' : null
            },
            effects: [
              ...(state.snapshot ? [{ type: 'RESTORE_SNAPSHOT', snapshot: state.snapshot, epoch: nextEpoch }] : []),
              { type: 'RESUME_3D_RENDERER', epoch: nextEpoch },
              { type: 'APPLY_NATIVE_GEOMETRY', mode: 'free', epoch: nextEpoch, revision: nextRev }
            ]
          };
        }
        if (state.physical === 'undocking') {
          const nextEpoch = state.dockEpoch + 1;
          const nextRev = state.geometryRevision + 1;
          return {
            next: {
              ...state,
              physical: 'docked',
              size: 'compact',
              dockEpoch: nextEpoch,
              geometryRevision: nextRev,
              layoutRevision: state.layoutRevision + 1
            },
            effects: [
              { type: 'DISABLE_TENDRILS', epoch: nextEpoch },
              { type: 'SUSPEND_3D_RENDERER', epoch: nextEpoch },
              { type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: 'compact', epoch: nextEpoch, revision: nextRev, displayId: state.displayId }
            ]
          };
        }
        return { next: state, effects };
      }

      case 'NATIVE_GEOMETRY_ACK': {
        if (typeof event.epoch === 'number' && event.epoch !== state.dockEpoch) return { next: state, effects };
        if (typeof event.revision === 'number' && event.revision < state.geometryRevision) return { next: state, effects };
        if (state.physical === 'docking') {
          if (event.tentacleLinks && event.tentacleLinks > 0) {
            return reduce(state, { type: 'TRANSITION_CANCEL' });
          }
          const next = {
            ...state,
            physical: 'docked',
            size: state.size || 'compact',
            layoutRevision: state.layoutRevision + 1
          };
          effects.push({ type: 'DISABLE_TENDRILS', epoch: state.dockEpoch });
          effects.push({ type: 'SUSPEND_3D_RENDERER', epoch: state.dockEpoch });
          effects.push({ type: 'SYNC_HIT_REGIONS', epoch: state.dockEpoch, revision: state.geometryRevision });
          effects.push({ type: 'PERSIST_STABLE_MODE', physical: 'docked', displayId: state.displayId });
          return { next, effects };
        }
        return { next: state, effects: [{ type: 'SYNC_HIT_REGIONS', epoch: state.dockEpoch, revision: state.geometryRevision }] };
      }

      case 'UNDOCK_REQUEST': {
        if (state.physical !== 'docked' && state.physical !== 'docking') return { next: state, effects };
        if (event.token && state.handledTokens.includes(event.token)) return { next: state, effects };
        const nextEpoch = state.dockEpoch + 1;
        const nextRev = state.geometryRevision + 1;
        const next = {
          ...state,
          physical: 'undocking',
          size: 'compact',
          interaction: 'none',
          prePortalState: null,
          stageOpen: false,
          dockEpoch: nextEpoch,
          geometryRevision: nextRev,
          handledTokens: recordToken(state.handledTokens, event.token),
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({ type: 'RELEASE_FOCUS', epoch: nextEpoch });
        effects.push({ type: 'RESUME_3D_RENDERER', epoch: nextEpoch });
        if (state.snapshot) {
          effects.push({
            type: 'RESTORE_SNAPSHOT',
            snapshot: state.snapshot,
            epoch: nextEpoch,
            preserveEditedIdentity: state.explicitIdentityEditRevision > (state.snapshot.identityRevision || 0)
          });
        }
        effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: 'undocking', epoch: nextEpoch, revision: nextRev });
        return { next, effects };
      }

      case 'UNDOCK_COMPLETE': {
        if (state.physical !== 'undocking') return { next: state, effects };
        if (event.epoch !== state.dockEpoch) return { next: state, effects };
        if (!event.avatarValid) return { next: state, effects };
        const next = {
          ...state,
          physical: 'free',
          size: 'compact',
          content: 'home',
          snapshot: null,
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({ type: 'ENABLE_FREE_TENDRILS', epoch: state.dockEpoch });
        effects.push({ type: 'SYNC_HIT_REGIONS', epoch: state.dockEpoch, revision: state.geometryRevision });
        effects.push({ type: 'PERSIST_STABLE_MODE', physical: 'free', displayId: state.displayId });
        return { next, effects };
      }

      case 'SET_SURFACE_SIZE': {
        if (state.physical !== 'docked') return { next: state, effects };
        if (!SURFACE_SIZES.includes(event.size)) return { next: state, effects };
        if (state.size === event.size && (!event.content || state.content === event.content)) {
          return { next: state, effects };
        }
        const nextRev = state.geometryRevision + 1;
        const nextContent = CONTENT_MODES.includes(event.content) ? event.content : state.content;
        const next = {
          ...state,
          size: event.size,
          content: nextContent,
          stageOpen: event.size === 'stage' ? true : (event.size === 'compact' || event.size === 'ambient' ? false : state.stageOpen),
          interaction: event.interaction && INTERACTION_MODES.includes(event.interaction) ? event.interaction : state.interaction,
          geometryRevision: nextRev,
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({
          type: 'APPLY_NATIVE_GEOMETRY',
          mode: 'docked',
          size: next.size,
          epoch: state.dockEpoch,
          revision: nextRev,
          activate: event.activate === true,
          displayId: state.displayId
        });
        if (event.activate === true && (next.size === 'expanded' || next.size === 'stage')) {
          effects.push({ type: 'ACQUIRE_FOCUS', epoch: state.dockEpoch });
        } else if (next.size === 'compact' || next.size === 'ambient') {
          effects.push({ type: 'RELEASE_FOCUS', epoch: state.dockEpoch });
        }
        return { next, effects };
      }

      case 'SET_CONTENT_MODE': {
        if (state.physical !== 'docked') return { next: state, effects };
        if (!CONTENT_MODES.includes(event.content)) return { next: state, effects };
        const nextSize = event.size && SURFACE_SIZES.includes(event.size) ? event.size : (state.size === 'compact' || state.size === 'ambient' ? 'expanded' : state.size);
        const nextRev = nextSize !== state.size ? state.geometryRevision + 1 : state.geometryRevision;
        const next = {
          ...state,
          content: event.content,
          size: nextSize,
          selectedActivityId: event.activityId !== undefined ? event.activityId : state.selectedActivityId,
          geometryRevision: nextRev,
          layoutRevision: state.layoutRevision + 1
        };
        if (nextRev !== state.geometryRevision) {
          effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: nextSize, epoch: state.dockEpoch, revision: nextRev, activate: event.activate === true, displayId: state.displayId });
        }
        if (event.activate === true) effects.push({ type: 'ACQUIRE_FOCUS', epoch: state.dockEpoch });
        return { next, effects };
      }

      case 'ESCAPE_PRESSED': {
        if (state.physical === 'approach' || state.physical === 'retracting' || state.physical === 'docking') {
          return reduce(state, { type: 'TRANSITION_CANCEL' });
        }
        if (state.physical !== 'docked') return { next: state, effects };
        if (state.prePortalState) {
          return reduce(state, { type: 'PORTAL_DRAG_LEAVE' });
        }
        if (state.stageOpen) {
          return reduce(state, { type: 'CLOSE_STAGE' });
        }
        if (state.size !== 'compact') {
          return reduce(state, { type: 'SET_SURFACE_SIZE', size: 'compact', interaction: 'none' });
        }
        return { next: state, effects };
      }

      case 'PORTAL_DRAG_ENTER': {
        if (state.physical !== 'docked') return { next: state, effects };
        const pre = state.prePortalState || { size: state.size, content: state.content };
        const nextRev = state.geometryRevision + 1;
        return {
          next: {
            ...state,
            prePortalState: pre,
            size: 'peek',
            content: 'portal',
            interaction: 'dragEnter',
            geometryRevision: nextRev,
            layoutRevision: state.layoutRevision + 1
          },
          effects: [{ type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: 'peek', epoch: state.dockEpoch, revision: nextRev, displayId: state.displayId }]
        };
      }

      case 'PORTAL_DRAG_LEAVE': {
        if (state.physical !== 'docked' || !state.prePortalState) return { next: state, effects };
        const restored = state.prePortalState;
        const nextRev = state.geometryRevision + 1;
        return {
          next: {
            ...state,
            prePortalState: null,
            size: restored.size,
            content: restored.content,
            interaction: 'none',
            geometryRevision: nextRev,
            layoutRevision: state.layoutRevision + 1
          },
          effects: [{ type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: restored.size, epoch: state.dockEpoch, revision: nextRev, displayId: state.displayId }]
        };
      }

      case 'PORTAL_DROP': {
        if (state.physical !== 'docked') return { next: state, effects };
        if (event.token && state.handledTokens.includes(event.token)) return { next: state, effects };
        const next = {
          ...state,
          prePortalState: null,
          size: 'expanded',
          content: 'portal',
          interaction: 'pointer',
          handledTokens: recordToken(state.handledTokens, event.token),
          geometryRevision: state.geometryRevision + 1,
          layoutRevision: state.layoutRevision + 1
        };
        effects.push({ type: 'DISPATCH_PORTAL_DROP', targetId: event.targetId, files: event.files || [], text: event.text || '', token: event.token || null });
        effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: 'expanded', epoch: state.dockEpoch, revision: next.geometryRevision, displayId: state.displayId });
        return { next, effects };
      }

      case 'OPEN_STAGE': {
        if (state.physical !== 'docked') return { next: state, effects };
        const nextRev = state.geometryRevision + 1;
        return {
          next: {
            ...state,
            size: 'stage',
            stageOpen: true,
            content: event.content && CONTENT_MODES.includes(event.content) ? event.content : state.content,
            selectedActivityId: event.activityId !== undefined ? event.activityId : state.selectedActivityId,
            geometryRevision: nextRev,
            layoutRevision: state.layoutRevision + 1
          },
          effects: [
            { type: 'OPEN_STAGE_SURFACE', content: event.content || state.content, activityId: event.activityId || state.selectedActivityId },
            { type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: 'stage', epoch: state.dockEpoch, revision: nextRev, activate: true, displayId: state.displayId }
          ]
        };
      }

      case 'CLOSE_STAGE': {
        if (!state.stageOpen) return { next: state, effects };
        const targetSize = event.nextSize && SURFACE_SIZES.includes(event.nextSize) ? event.nextSize : 'compact';
        const nextRev = state.geometryRevision + 1;
        return {
          next: {
            ...state,
            size: targetSize,
            stageOpen: false,
            geometryRevision: nextRev,
            layoutRevision: state.layoutRevision + 1
          },
          effects: [
            { type: 'CLOSE_STAGE_SURFACE' },
            { type: 'APPLY_NATIVE_GEOMETRY', mode: 'docked', size: targetSize, epoch: state.dockEpoch, revision: nextRev, displayId: state.displayId }
          ]
        };
      }

      case 'SET_VISIBILITY': {
        if (!VISIBILITY_POLICIES.includes(event.visibility)) return { next: state, effects };
        if (state.visibility === event.visibility) return { next: state, effects };
        const next = { ...state, visibility: event.visibility, layoutRevision: state.layoutRevision + 1 };
        if (isDockedPresentation(next)) {
          const nextRev = state.geometryRevision + 1;
          next.geometryRevision = nextRev;
          effects.push({ type: 'APPLY_VISIBILITY_POLICY', visibility: event.visibility, epoch: state.dockEpoch, revision: nextRev });
        }
        return { next, effects };
      }

      case 'SELECT_ACTIVITY': {
        return {
          next: { ...state, selectedActivityId: event.activityId || null, layoutRevision: state.layoutRevision + 1 },
          effects
        };
      }

      case 'PIN_ACTIVITY': {
        return {
          next: { ...state, pinnedActivityId: event.activityId || null, layoutRevision: state.layoutRevision + 1 },
          effects: [{ type: 'PERSIST_PREFS' }]
        };
      }

      case 'SYNC_PROJECTIONS': {
        const list = Array.isArray(event.projections) ? event.projections : [];
        const source = event.source || 'runtime';
        const prevEpoch = state.sourceEpochs[source];
        const nextSourceEpochs = { ...state.sourceEpochs };
        const nextEntityRevisions = { ...state.entityRevisions };
        const acceptedIds = [];
        for (const proj of list) {
          if (!proj || !proj.id) continue;
          const entityKey = (proj.source || source) + ':' + proj.id;
          const epochChanged = proj.sourceEpoch && prevEpoch && proj.sourceEpoch !== prevEpoch;
          if (!epochChanged && typeof proj.revision === 'number' && typeof nextEntityRevisions[entityKey] === 'number' && proj.revision < nextEntityRevisions[entityKey]) {
            continue;
          }
          if (typeof proj.revision === 'number') nextEntityRevisions[entityKey] = proj.revision;
          acceptedIds.push(proj.id);
        }
        if (event.sourceEpoch) nextSourceEpochs[source] = event.sourceEpoch;
        const attention = highestAttention(list, event.backendOffline === true);
        let selectedActivityId = state.selectedActivityId;
        if (selectedActivityId && !acceptedIds.includes(selectedActivityId)) {
          selectedActivityId = acceptedIds[0] || null;
        } else if (!selectedActivityId && acceptedIds.length) {
          selectedActivityId = (state.pinnedActivityId && acceptedIds.includes(state.pinnedActivityId)) ? state.pinnedActivityId : acceptedIds[0];
        }
        return {
          next: {
            ...state,
            attention,
            activityIds: acceptedIds,
            selectedActivityId,
            activityRevision: state.activityRevision + 1,
            sourceEpochs: nextSourceEpochs,
            entityRevisions: nextEntityRevisions
          },
          effects
        };
      }

      case 'IDENTITY_EDITED_WHILE_DOCKED': {
        const rev = typeof event.identityRevision === 'number' ? event.identityRevision : state.explicitIdentityEditRevision + 1;
        return {
          next: { ...state, explicitIdentityEditRevision: Math.max(state.explicitIdentityEditRevision, rev) },
          effects
        };
      }

      case 'DISPLAY_CHANGED': {
        const nextRev = state.geometryRevision + 1;
        const next = {
          ...state,
          displayId: event.displayId || state.displayId,
          geometryRevision: nextRev,
          layoutRevision: state.layoutRevision + 1
        };
        if (isDockedPresentation(next)) {
          effects.push({ type: 'APPLY_NATIVE_GEOMETRY', mode: next.physical, size: next.size, epoch: next.dockEpoch, revision: nextRev, displayId: next.displayId });
        }
        return { next, effects };
      }

      case 'TOGGLE_CONTEXT_FREEZE': {
        const frozen = typeof event.frozen === 'boolean' ? event.frozen : !state.contextFrozen;
        return {
          next: {
            ...state,
            contextFrozen: frozen,
            frozenContext: frozen ? (event.context || state.frozenContext || { label: state.content, activityId: state.selectedActivityId }) : null,
            layoutRevision: state.layoutRevision + 1
          },
          effects
        };
      }

      case 'SET_STAGE_DETACHED': {
        return {
          next: {
            ...state,
            stageDetached: Boolean(event.detached),
            stagePos: event.detached ? (event.pos || state.stagePos) : null,
            layoutRevision: state.layoutRevision + 1
          },
          effects
        };
      }

      default:
        return { next: state, effects };
    }
  }

  function resolveLayout(state, workArea = { x: 0, y: 0, width: 1536, height: 816 }, uiScale = 1, metrics = {}) {
    const scale = clamp(Number.isFinite(uiScale) ? uiScale : 1, 0.85, 1.35);
    const workW = Math.max(240, Number(workArea.width) || 1536);
    const workH = Math.max(200, Number(workArea.height) || 816);
    const activityCount = Number.isFinite(metrics.activityCount) ? metrics.activityCount : state.activityIds.length;
    const semanticWidth = Number.isFinite(metrics.semanticWidth) ? metrics.semanticWidth : 0;
    const semanticHeight = Number.isFinite(metrics.semanticHeight) ? metrics.semanticHeight : 0;

    let targetW;
    let targetH;
    let radius;

    if (state.size === 'ambient') {
      const maxW = Math.max(168, Math.min(320, Math.round(workW * 0.22)));
      const contentW = semanticWidth || (activityCount > 0 ? 228 : 178);
      targetW = clamp(contentW, 168, maxW);
      targetH = clamp(Math.round(30 * scale), 28, 36);
      radius = Math.round(targetH * 0.45);
    } else if (state.size === 'peek') {
      const maxW = Math.max(260, Math.min(440, Math.round(workW * 0.36)));
      const contentW = semanticWidth || (state.content === 'portal' ? 380 : 340);
      targetW = clamp(contentW, Math.min(260, workW - 24), maxW);
      targetH = clamp(semanticHeight || 78, 56, Math.min(112, Math.round(workH * 0.2)));
      radius = 18;
    } else if (state.size === 'expanded') {
      const maxW = Math.max(320, Math.min(680, Math.round(workW * 0.58)));
      const maxH = Math.max(180, Math.min(520, Math.round(workH * 0.52)));
      const defaultW = state.content === 'intent' ? 520 : state.content === 'parallel' || state.content === 'orbit' ? 480 : 440;
      const defaultH = state.content === 'intent' ? 320 : state.content === 'home' ? 250 : 280;
      targetW = clamp(semanticWidth || defaultW, Math.min(320, workW - 24), maxW);
      targetH = clamp(semanticHeight || defaultH, Math.min(180, workH - 32), maxH);
      radius = 22;
    } else if (state.size === 'stage') {
      const maxW = Math.max(240, Math.min(420, Math.round(workW * 0.3)));
      targetW = clamp(semanticWidth || 300, 220, maxW);
      targetH = clamp(Math.round(36 * scale), 32, 42);
      radius = 16;
    } else {
      // compact
      const maxW = Math.max(184, Math.min(368, Math.round(workW * 0.25)));
      const baseCompact = activityCount >= 2 ? 296 : activityCount === 1 ? 256 : 196;
      targetW = clamp(semanticWidth || Math.round(baseCompact * scale), 184, maxW);
      targetH = clamp(Math.round(34 * scale), 30, 42);
      radius = Math.round(targetH * 0.48);
    }

    targetW = Math.min(targetW, workW - 16);
    targetH = Math.min(targetH, workH - 16);
    const x = Math.round(workW / 2 - targetW / 2);
    const y = 0; // Top seam flush with workArea top edge
    const visibleSlots = targetW >= 300 ? 3 : targetW >= 240 ? 2 : 1;
    const overflowCount = Math.max(0, activityCount - visibleSlots);

    return {
      x,
      y,
      width: Math.round(targetW),
      height: Math.round(targetH),
      radius,
      visibleSlots,
      overflowCount,
      visible: isNotchVisible(state)
    };
  }

  function isInDockApproachBand(localY, bandDip = 48, hysteresisDip = 24, alreadyInApproach = false) {
    if (!Number.isFinite(localY)) return false;
    const threshold = alreadyInApproach ? bandDip + hysteresisDip : bandDip;
    return localY <= threshold;
  }

  return {
    PHYSICAL_MODES,
    SURFACE_SIZES,
    CONTENT_MODES,
    ATTENTION_LEVELS,
    INTERACTION_MODES,
    VISIBILITY_POLICIES,
    createInitialState,
    isDockedPresentation,
    tendrilsAllowed,
    isNotchVisible,
    reduce,
    resolveLayout,
    isInDockApproachBand
  };
});
