/* Identity snapshot, restoration, and versioned additive notch preferences.
 * Preserves 24x9x4 avatar identity across dock/undock without mutating studio settings. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchSnapshot = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  const PREFS_KEY = 'axx.notch.v1';
  const SNAPSHOT_KEY = 'axx.notch.snapshot.v1';

  const VISUAL_PRESET_KEYS = [
    'styleDirection', 'surfaceTheme', 'material', 'accent', 'customAccentHex',
    'surfaceShape', 'borderStyle', 'horizontalAlign', 'compactMetrics',
    'contrast', 'surfaceScale', 'expandedScalePercent', 'compactWidthPx', 'density', 'motionIntensity',
    'surfaceOpacity', 'topOffsetPx', 'cornerRadiusScale', 'glowIntensity',
    'fontPreset', 'soundProfile', 'ambientPulse', 'showQuickChatButton',
    'showAvatarInNotch', 'idleFadeEnabled', 'idleFadeSeconds', 'idleFadeOpacity'
  ];

  function defaultPreferences() {
    return {
      schemaVersion: 2,
      enabled: true,
      styleDirection: 'identity-accent',
      surfaceTheme: 'obsidian',
      material: 'solid',
      accent: 'avatar',
      customAccentHex: '#8ab4f8',
      surfaceShape: 'notch',
      borderStyle: 'subtle',
      horizontalAlign: 'center',
      compactMetrics: 'auto',
      contrast: 'standard',
      surfaceScale: 'standard',
      expandedScalePercent: 100,
      compactWidthPx: 0,
      surfaceOpacity: 96,
      topOffsetPx: 0,
      cornerRadiusScale: 'balanced',
      glowIntensity: 'off',
      fontPreset: 'system',
      soundProfile: 'crystal',
      ambientPulse: false,
      showQuickChatButton: true,
      customPreset: null,
      dockBandDip: 48,
      dockSensitivity: 'normal',
      dwellMs: 120,
      autoDockOnTopDrag: true,
      hoverPeek: false,
      idleFadeEnabled: true,
      idleFadeSeconds: 8,
      idleFadeOpacity: 'subtle',
      soundEffectsEnabled: true,
      showAvatarInNotch: true,
      density: 'compact',
      motionIntensity: 'organic',
      suspendRendererWhenDocked: true,
      autoHideFullscreen: true,
      gamingSuppression: true,
      alwaysOnTop: true,
      privacyCurtain: false,
      performanceAdaptive: true,
      preferredMonitor: 'auto',
      pinnedActivityId: null,
      contextFreeze: false,
      rememberStableMode: true,
      lastStablePhysical: 'free',
      shortcut: 'Alt+Shift+N'
    };
  }

  function normalizePreferences(raw, _depth = 0) {
    const d = defaultPreferences();
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return d;
    if (typeof raw.enabled === 'boolean') d.enabled = raw.enabled;
    if (['identity-accent', 'neutral-monolith', 'theme-adaptive'].includes(raw.styleDirection)) {
      d.styleDirection = raw.styleDirection;
    }
    for (const [key, values] of Object.entries({
      surfaceTheme: ['obsidian', 'midnight', 'carbon', 'slate', 'amethyst', 'forest'],
      material: ['solid', 'translucent', 'mica', 'aurora', 'frosted'],
      accent: ['avatar', 'gemini', 'ice', 'iris', 'sage', 'amber', 'emerald', 'rose', 'cyberpunk', 'sunset', 'gold', 'crimson', 'custom'],
      surfaceShape: ['notch', 'island', 'pill', 'capsule', 'ribbon', 'bevel', 'zen-dot'],
      borderStyle: ['subtle', 'glow', 'borderless', 'neon-edge', 'glass-bevel', 'prism'],
      horizontalAlign: ['center', 'left', 'right'],
      compactMetrics: ['auto', 'clock', 'clock-date', 'stats', 'studio', 'greeting', 'minimal'],
      contrast: ['standard', 'high'],
      surfaceScale: ['small', 'standard', 'large'],
      cornerRadiusScale: ['sharp', 'balanced', 'round'],
      glowIntensity: ['off', 'subtle', 'vivid'],
      fontPreset: ['system', 'geometric', 'mono'],
      soundProfile: ['crystal', 'soft', 'mechanical', 'synth']
    })) {
      if (values.includes(raw[key])) d[key] = raw[key];
    }
    if (typeof raw.customAccentHex === 'string' && /^#[0-9a-f]{6}$/i.test(raw.customAccentHex.trim())) {
      d.customAccentHex = raw.customAccentHex.trim().toLowerCase();
    }
    if (typeof raw.surfaceOpacity === 'number' && Number.isFinite(raw.surfaceOpacity)) {
      d.surfaceOpacity = Math.max(65, Math.min(100, Math.round(raw.surfaceOpacity)));
    }
    if (typeof raw.expandedScalePercent === 'number' && Number.isFinite(raw.expandedScalePercent)) d.expandedScalePercent = Math.max(80, Math.min(110, Math.round(raw.expandedScalePercent)));
    if (typeof raw.compactWidthPx === 'number' && Number.isFinite(raw.compactWidthPx)) d.compactWidthPx = raw.compactWidthPx === 0 ? 0 : Math.max(184, Math.min(360, Math.round(raw.compactWidthPx)));
    if (typeof raw.topOffsetPx === 'number' && Number.isFinite(raw.topOffsetPx)) {
      d.topOffsetPx = Math.max(0, Math.min(24, Math.round(raw.topOffsetPx)));
    }
    if (['low', 'normal', 'high'].includes(raw.dockSensitivity)) {
      d.dockSensitivity = raw.dockSensitivity;
    }
    if (['ghost', 'subtle', 'dim', 'invisible'].includes(raw.idleFadeOpacity)) {
      d.idleFadeOpacity = raw.idleFadeOpacity;
    }
    if (typeof raw.idleFadeSeconds === 'number' && Number.isFinite(raw.idleFadeSeconds)) {
      d.idleFadeSeconds = Math.max(0, Math.min(120, Math.round(raw.idleFadeSeconds)));
    }
    if (['compact', 'comfortable'].includes(raw.density)) {
      d.density = raw.density;
    }
    if (['organic', 'crisp', 'reduced'].includes(raw.motionIntensity)) {
      d.motionIntensity = raw.motionIntensity;
    }
    if (typeof raw.dockBandDip === 'number' && Number.isFinite(raw.dockBandDip)) {
      d.dockBandDip = Math.max(24, Math.min(96, Math.round(raw.dockBandDip)));
    }
    if (typeof raw.dwellMs === 'number' && Number.isFinite(raw.dwellMs)) {
      d.dwellMs = Math.max(40, Math.min(400, Math.round(raw.dwellMs)));
    }
    for (const flag of [
      'autoDockOnTopDrag', 'hoverPeek', 'idleFadeEnabled', 'soundEffectsEnabled', 'showAvatarInNotch',
      'ambientPulse', 'showQuickChatButton',
      'suspendRendererWhenDocked', 'autoHideFullscreen', 'gamingSuppression', 'alwaysOnTop',
      'privacyCurtain', 'performanceAdaptive', 'contextFreeze', 'rememberStableMode'
    ]) {
      if (typeof raw[flag] === 'boolean') d[flag] = raw[flag];
    }
    if (_depth === 0 && raw.customPreset && typeof raw.customPreset === 'object' && !Array.isArray(raw.customPreset)) {
      const cleanPreset = normalizePreferences(raw.customPreset, 1);
      const picked = {};
      for (const k of VISUAL_PRESET_KEYS) picked[k] = cleanPreset[k];
      d.customPreset = picked;
    }
    if (typeof raw.preferredMonitor === 'string' && raw.preferredMonitor.length <= 128) {
      d.preferredMonitor = raw.preferredMonitor;
    }
    if (typeof raw.pinnedActivityId === 'string' && raw.pinnedActivityId.length <= 128) {
      d.pinnedActivityId = raw.pinnedActivityId;
    }
    if (raw.lastStablePhysical === 'docked' || raw.lastStablePhysical === 'free') {
      d.lastStablePhysical = raw.lastStablePhysical;
    }
    if (typeof raw.shortcut === 'string' && raw.shortcut.length <= 48) {
      d.shortcut = raw.shortcut;
    }
    return d;
  }

  function loadPreferences(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
    try {
      if (!storage) return defaultPreferences();
      const raw = JSON.parse(storage.getItem(PREFS_KEY) || 'null');
      if (raw && typeof raw === 'object' && !Array.isArray(raw) && (!raw.schemaVersion || raw.schemaVersion < 2)) {
        const migrated = normalizePreferences({ ...raw, enabled: true, schemaVersion: 2 });
        try { storage.setItem(PREFS_KEY, JSON.stringify(migrated)); } catch {}
        return migrated;
      }
      return normalizePreferences(raw);
    } catch {
      return defaultPreferences();
    }
  }

  function savePreferences(prefs, storage = typeof localStorage !== 'undefined' ? localStorage : null) {
    const normalized = normalizePreferences(prefs);
    try {
      storage?.setItem(PREFS_KEY, JSON.stringify(normalized));
    } catch { /* ignore storage quota issues */ }
    return normalized;
  }

  function deepFreeze(obj) {
    if (!obj || typeof obj !== 'object') return obj;
    Object.freeze(obj);
    for (const val of Object.values(obj)) {
      if (val && typeof val === 'object' && !Object.isFrozen(val)) deepFreeze(val);
    }
    return obj;
  }

  function captureSnapshot(sources = {}) {
    const settings = sources.settings ? { ...sources.settings } : {};
    const studio = sources.studio ? { ...sources.studio } : {};
    const camera = Array.isArray(sources.camera) ? sources.camera.slice(0, 2) : [-0.18, 0.08];
    const finish = typeof sources.finish === 'string' ? sources.finish : 'obsidian';
    const freePosition = sources.freePosition ? {
      displayId: String(sources.freePosition.displayId || 'primary'),
      screenX: Number.isFinite(sources.freePosition.screenX) ? sources.freePosition.screenX : 0,
      screenY: Number.isFinite(sources.freePosition.screenY) ? sources.freePosition.screenY : 0,
      anchorX: Number.isFinite(sources.freePosition.anchorX) ? sources.freePosition.anchorX : 152,
      anchorY: Number.isFinite(sources.freePosition.anchorY) ? sources.freePosition.anchorY : 152,
      size: Number.isFinite(sources.freePosition.size) ? sources.freePosition.size : 280
    } : { displayId: 'primary', screenX: 0, screenY: 0, anchorX: 152, anchorY: 152, size: 280 };

    return deepFreeze({
      schemaVersion: 1,
      identityRevision: Number.isFinite(sources.identityRevision) ? sources.identityRevision : 1,
      identity: {
        settings,
        studio,
        camera,
        finish
      },
      freePosition,
      capturedAt: Number.isFinite(sources.capturedAt) ? sources.capturedAt : Date.now()
    });
  }

  function restoreSnapshot(snapshot, targets = {}, options = {}) {
    if (!snapshot || snapshot.schemaVersion !== 1 || !snapshot.identity) {
      return { restored: false, reason: 'INVALID_SNAPSHOT' };
    }
    const preserveEditedIdentity = options.preserveEditedIdentity === true;
    const { settings, studio, camera, finish } = snapshot.identity;

    if (!preserveEditedIdentity) {
      if (targets.store && settings && typeof settings === 'object') {
        targets.store.data.settings = { ...targets.store.data.settings, ...settings };
        targets.store.save?.();
      }
      if (targets.renderer) {
        if (typeof targets.renderer.configure === 'function' && settings) {
          targets.renderer.configure(targets.store ? targets.store.data.settings : settings);
        }
        if (typeof targets.renderer.setStudio === 'function' && studio) {
          targets.renderer.setStudio(studio);
        }
        if (typeof targets.renderer.setCamera20 === 'function' && Array.isArray(camera)) {
          targets.renderer.setCamera20(camera);
        }
        if (typeof targets.renderer.setFinish === 'function' && finish) {
          targets.renderer.setFinish(finish);
        }
        if (typeof targets.renderer.setForm === 'function' && Number.isInteger(settings?.form)) {
          targets.renderer.setForm(settings.form, true);
        }
      }
      if (typeof targets.applySettings === 'function') {
        targets.applySettings();
      }
    }

    if (targets.resident && snapshot.freePosition) {
      const pos = snapshot.freePosition;
      if (Number.isFinite(pos.size)) {
        targets.resident.size = pos.size;
      }
      if (Number.isFinite(pos.anchorX) && Number.isFinite(pos.anchorY)) {
        targets.resident.anchor = { x: pos.anchorX, y: pos.anchorY };
      }
      targets.resident.paintBody?.();
    }

    return {
      restored: true,
      preservedIdentityEdit: preserveEditedIdentity,
      freePosition: snapshot.freePosition
    };
  }

  function persistSnapshot(snapshot, storage = typeof localStorage !== 'undefined' ? localStorage : null) {
    try {
      if (!snapshot) storage?.removeItem(SNAPSHOT_KEY);
      else storage?.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
    } catch { /* ignore */ }
  }

  function loadPersistedSnapshot(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
    try {
      const raw = storage?.getItem(SNAPSHOT_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && parsed.schemaVersion === 1 && parsed.identity ? parsed : null;
    } catch {
      return null;
    }
  }

  function resetPreferences(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
    return savePreferences(defaultPreferences(), storage);
  }

  return {
    PREFS_KEY,
    SNAPSHOT_KEY,
    defaultPreferences,
    normalizePreferences,
    loadPreferences,
    savePreferences,
    resetPreferences,
    captureSnapshot,
    restoreSnapshot,
    persistSnapshot,
    loadPersistedSnapshot
  };
});
