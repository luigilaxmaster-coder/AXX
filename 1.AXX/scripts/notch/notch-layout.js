/* AXX Singularity — Adaptive Composition Engine 2.0 & Approach Trajectory Solver
 * Resolves L0..L5 semantic representations, asymmetric dimensions, attention budget,
 * and velocity-aware docking approach intention without duplicating business state.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchLayout = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  const SENSITIVITY_BANDS = Object.freeze({
    low: { bandDip: 40, hysteresisDip: 20, dwellMs: 130 },
    normal: { bandDip: 64, hysteresisDip: 28, dwellMs: 80 },
    high: { bandDip: 88, hysteresisDip: 32, dwellMs: 50 }
  });

  const GEOMETRY = Object.freeze({
    header: 44, footer: 54, inset: 22,
    expanded: {
      orbit: [596, 536], home: [596, 536], parallel: [620, 440],
      media: [580, 338], agents: [620, 600], voice: [540, 432],
      resources: [600, 524], recall: [590, 444], portal: [624, 520], intent: [608, 548],
      chat: [660, 688]
    }
  });

  function clamp(v, lo, hi) {
    const min = Math.min(lo, hi);
    const max = Math.max(lo, hi);
    return Math.max(min, Math.min(max, v));
  }

  /**
   * Velocity- and trajectory-aware approach evaluation.
   * Prevents accidental horizontal edge swipes from falsely triggering dock approach.
   */
  function evaluateApproach({
    localY,
    vy = 0,
    vx = 0,
    sensitivity = 'normal',
    alreadyInApproach = false
  }) {
    if (!Number.isFinite(localY)) return { inBand: false, magneticPull: 0, intentional: false };
    const cfg = SENSITIVITY_BANDS[sensitivity] || SENSITIVITY_BANDS.normal;
    const threshold = alreadyInApproach ? cfg.bandDip + cfg.hysteresisDip : cfg.bandDip;
    const inBand = localY <= threshold;
    if (!inBand) return { inBand: false, magneticPull: 0, intentional: false };
    const dominanceRatio = Math.abs(vx) > 220 && Math.abs(vy) < Math.abs(vx) * 0.25 && localY > 18;
    const magneticPull = clamp(1 - Math.max(0, localY) / Math.max(1, threshold), 0, 1);
    const intentional = alreadyInApproach ? true : (!dominanceRatio && (vy <= 120 || localY <= 24));
    return { inBand: intentional || alreadyInApproach, magneticPull, intentional, dwellMs: cfg.dwellMs };
  }

  /**
   * Semantic level mapping L0..L5 based on size + content + projections.
   */
  function resolveSemanticLevel(state, context = {}) {
    if (!state.enabled || state.visibility === 'userHidden' || state.visibility === 'fullscreenSuppressed') {
      return 'L0';
    }
    if (state.stageOpen || state.size === 'stage') return 'L5';
    if (state.size === 'expanded') return 'L4';
    if (state.size === 'peek') return 'L3';
    if (state.size === 'ambient') return 'L1';
    if (context.projections?.length > 0 || state.attention !== 'idle') return 'L2';
    return 'L1';
  }

  /**
   * Resolves adaptive geometry per content archetype so Media, Agents, Portal, Intent, Voice,
   * Parallel, Resources, and Stage adopt genuinely distinct proportions rather than one fixed box.
   */
  function resolveAdaptiveGeometry(state, workArea = { x: 0, y: 0, width: 1536, height: 816 }, uiScale = 1, context = {}) {
    const scale = clamp(Number.isFinite(uiScale) ? uiScale : 1, 0.85, 1.35);
    const densityMul = context.density === 'comfortable' ? 1.08 : 1;
    const workW = Math.max(280, Number(workArea.width) || 1536);
    const workH = Math.max(220, Number(workArea.height) || 816);
    const projections = Array.isArray(context.projections) ? context.projections : [];
    const count = projections.length;
    const primary = projections.find(p => p.id === state.selectedActivityId) || projections[0] || null;
    const level = resolveSemanticLevel(state, { projections });

    let targetW = 204;
    let targetH = Math.round(32 * scale);
    let radius = Math.round(targetH * 0.48);
    let layoutMode = 'minimal';

    const shape = context.surfaceShape || 'notch';
    if (level === 'L0' || level === 'L1') {
      const compactCap = Math.min(420, Math.round(workW * 0.28));
      const baseW = shape === 'ribbon' ? (count > 0 ? 316 : 292)
        : shape === 'zen-dot' ? (count > 0 ? 228 : 186)
        : (count > 0 ? 248 : 224);
      targetW = clamp(baseW, 184, compactCap);
      const baseH = shape === 'ribbon' || shape === 'zen-dot' ? 28 : 30;
      targetH = clamp(Math.round(baseH * scale), 28, 36);
      radius = (shape === 'capsule' || shape === 'pill' || shape === 'zen-dot') ? 999
        : shape === 'bevel' ? 10
        : shape === 'ribbon' ? 12
        : Math.round(targetH * 0.46);
      layoutMode = primary?.kind || 'minimal';
    } else if (level === 'L2') {
      const compactCap = Math.min(440, Math.round(workW * 0.30));
      const ribbonExtra = shape === 'ribbon' ? 44 : 0;
      if (primary?.kind === 'media') {
        // Panoramic horizontal strip for audio + secondary pill
        targetW = clamp(Math.round(((count > 1 ? 344 : 308) + ribbonExtra) * scale), 240, compactCap);
        targetH = clamp(Math.round((shape === 'ribbon' ? 30 : 34) * scale), 28, 40);
        layoutMode = 'media-strip';
      } else if (primary?.kind === 'agent' || state.attention === 'approval') {
        targetW = clamp(Math.round((326 + ribbonExtra) * scale), 240, compactCap);
        targetH = clamp(Math.round((shape === 'ribbon' ? 30 : 34) * scale), 28, 40);
        layoutMode = 'agent-strip';
      } else {
        targetW = clamp(Math.round(((count >= 2 ? 318 : 284) + ribbonExtra) * scale), 216, compactCap);
        targetH = clamp(Math.round((shape === 'ribbon' ? 30 : 32) * scale), 28, 38);
        layoutMode = count >= 2 ? 'orbit-strip' : 'activity-strip';
      }
      radius = (shape === 'capsule' || shape === 'pill' || shape === 'zen-dot') ? 999
        : shape === 'bevel' ? 10
        : shape === 'ribbon' ? 12
        : Math.round(targetH * 0.48);
    } else if (level === 'L3') {
      const maxW = Math.max(280, Math.min(500, Math.round(workW * 0.38)));
      if (state.content === 'portal') {
        targetW = clamp(410, 280, maxW);
        targetH = clamp(Math.round(92 * densityMul), 72, 114);
        layoutMode = 'portal-shelf';
      } else if (primary?.kind === 'media' || state.content === 'media') {
        targetW = clamp(448, 300, maxW);
        targetH = clamp(Math.round(98 * densityMul), 80, 120);
        layoutMode = 'media-lens';
      } else {
        targetW = clamp(360, 260, maxW);
        targetH = clamp(Math.round(82 * densityMul), 64, 108);
        layoutMode = 'quick-peek';
      }
      radius = shape === 'bevel' ? 12 : 20;
    } else if (level === 'L4') {
      const maxW = Math.max(340, Math.min(720, Math.round(workW * 0.74)));
      const maxH = Math.max(200, Math.min(760, Math.round(workH - 20)));
      if (state.content === 'intent') {
        const resultRows = Math.max(1, Math.min(5, Number(context.intentResultCount) || 1));
        targetW = clamp(GEOMETRY.expanded.intent[0], 340, maxW);
        targetH = clamp(Math.round((316 + resultRows * 46) * densityMul), 440, maxH);
        layoutMode = 'intent-palette';
      } else {
        const recipe = GEOMETRY.expanded[state.content] || GEOMETRY.expanded.orbit;
        targetW = clamp(recipe[0], 320, maxW);
        targetH = clamp(Math.round(recipe[1] * densityMul), 200, maxH);
        if (['orbit', 'home'].includes(state.content) && count > 0) targetH = Math.min(targetH, Math.round(440 * densityMul));
        layoutMode = ({ media: 'media-panoramic', agents: 'agent-observatory', portal: 'portal-magnetic',
          parallel: 'parallel-lanes', voice: 'voice-studio', resources: 'resource-lens', recall: 'recall-threads', chat: 'direct-chat' })[state.content] || 'orbit-focus';
      }
      radius = shape === 'bevel' ? 12 : (shape === 'island' || shape === 'capsule' || shape === 'zen-dot') ? 28 : 24;
      if (context.hasApproval) targetH = Math.min(maxH, targetH + 112);
      if (context.appearanceOpen) { targetW = Math.min(maxW, 676); targetH = Math.min(maxH, 696); }
    } else {
      // L5 Stage top anchor header while Stage workspace floats cleanly below or detached
      const maxW = Math.max(240, Math.min(420, Math.round(workW * 0.3)));
      targetW = clamp(320, 236, maxW);
      targetH = clamp(Math.round(34 * scale), 30, 40);
      radius = shape === 'bevel' ? 10 : 16;
      layoutMode = 'stage-anchor';
    }

    if (context.cornerRadiusScale === 'sharp') {
      radius = radius === 999 ? 14 : Math.max(8, Math.round(radius * 0.52));
    } else if (context.cornerRadiusScale === 'round') {
      radius = radius === 999 ? 999 : Math.min(34, Math.round(radius * 1.24));
    }

    const presetMul = context.surfaceScale === 'large' ? 1.12 : context.surfaceScale === 'small' ? 0.86 : 1;
    const userMul = Number.isFinite(context.expandedScalePercent) ? clamp(context.expandedScalePercent, 80, 110) / 100 : 1;
    const sizeMul = level === 'L4' ? (context.appearanceOpen ? 1 : presetMul * userMul) : 1;
    if (['L0', 'L1', 'L2'].includes(level) && context.compactWidthPx > 0) targetW = clamp(context.compactWidthPx, 184, 360);
    targetW = Math.min(Math.round(targetW * sizeMul), workW - 16);
    if (level === 'L4') targetH = Math.min(Math.round(targetH * sizeMul), workH - 16);
    targetH = Math.min(targetH, workH - 16);
    const align = context.horizontalAlign || 'center';
    const x = align === 'left' ? 14 : align === 'right' ? Math.max(14, workW - Math.round(targetW) - 14) : Math.round(workW / 2 - targetW / 2);
    const baseY = (shape === 'island' || shape === 'capsule') ? 8 : (shape === 'pill' || shape === 'zen-dot') ? 6 : 0;
    const customTop = Number.isFinite(context.topOffsetPx) ? clamp(Math.round(context.topOffsetPx), 0, 24) : 0;
    const y = customTop > 0 ? Math.max(baseY, customTop) : baseY;
    const visibleSlots = targetW >= 320 ? 3 : targetW >= 240 ? 2 : 1;
    const visible = Boolean(
      state.enabled &&
      (state.physical === 'docking' || state.physical === 'docked' || state.physical === 'undocking') &&
      state.visibility !== 'userHidden' &&
      state.visibility !== 'fullscreenSuppressed'
    );

    return {
      level,
      layoutMode,
      x,
      y,
      width: Math.round(targetW),
      height: Math.round(targetH),
      radius,
      visibleSlots,
      overflowCount: Math.max(0, count - visibleSlots),
      visible
    };
  }

  /**
   * Attention Budget: prevents non-critical passive cues from auto-expanding or interrupting typing.
   */
  function createAttentionEngine({ cooldownMs = 3000 } = {}) {
    let lastCueAt = 0;
    const missedCues = [];

    function evaluateEvent({ kind, priority = 'passive', userTyping = false, now = Date.now() }) {
      if (priority === 'critical' || priority === 'approval') {
        return { surfaceCue: true, autoExpand: false, queuedDigest: false };
      }
      if (userTyping || now - lastCueAt < cooldownMs) {
        missedCues.push({ kind, at: now });
        if (missedCues.length > 24) missedCues.shift();
        return { surfaceCue: false, autoExpand: false, queuedDigest: true, digestCount: missedCues.length };
      }
      lastCueAt = now;
      return { surfaceCue: true, autoExpand: false, queuedDigest: false };
    }

    function consumeDigest() {
      const items = missedCues.slice();
      missedCues.length = 0;
      return items;
    }

    return {
      evaluateEvent,
      consumeDigest,
      getDigestCount: () => missedCues.length
    };
  }

  return {
    GEOMETRY,
    SENSITIVITY_BANDS,
    evaluateApproach,
    resolveSemanticLevel,
    resolveAdaptiveGeometry,
    createAttentionEngine
  };
});
