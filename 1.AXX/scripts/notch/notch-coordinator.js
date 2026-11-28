/* AXX Singularity Notch Coordinator (`Axx.notch`) — Phase II Production Architecture
 * Orchestrates NotchState, NotchLayout, NotchMotion, NotchSnapshot, ActivityProjections,
 * NotchUI, Stage Continuum, Intent 2.0, Portal 2.0, Focus Return, and Rust host IPC.
 */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notch = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function (root) {
  'use strict';

  const MAX_PORTAL_ITEMS = 8;
  const RETRACT_DURATION_MS = 70;

  function createCoordinator() {
    const NS = root.Axx?.notchState;
    const NL = root.Axx?.notchLayout;
    const NM = root.Axx?.notchMotion;
    const NK = root.Axx?.notchSnapshot;
    const NP = root.Axx?.notchProjections;
    const NU = root.Axx?.notchUI;

    let prefs = NK ? NK.loadPreferences() : { enabled: false, suspendRendererWhenDocked: true, dockSensitivity: 'normal' };
    let state = NS ? NS.createInitialState({ enabled: prefs.enabled, pinnedActivityId: prefs.pinnedActivityId }) : {
      enabled: false, physical: 'free', size: 'compact', content: 'home', attention: 'idle',
      interaction: 'none', visibility: 'normal', dockEpoch: 0, geometryRevision: 0,
      layoutRevision: 0, activityIds: [], stageOpen: false, snapshot: null
    };
    const motion = NM ? new NM.NotchMotionController({ width: 204, height: 32, radius: 16 }) : null;
    const attentionEngine = NL ? NL.createAttentionEngine({ cooldownMs: 3000 }) : null;

    let portalItems = [];
    let offlineQueue = [];
    let recentIntents = [];
    let intentQuery = '';
    let telemetryCache = null;
    let telemetryPending = false, telemetryError = '', portalReceipt = '';
    let approachPull = 0;
    let approachTimer = null;
    let approachDwellSatisfied = false;
    let retractTimer = null;
    let hoverTimer = null;
    let prevDragSample = null;
    let lastTransitionTime = performance.now();
    let initialized = false;
    let settingsBinding = null;
    let lastNativeSig = '';
    let motionRaf = 0;
    let lastMotionFrame = 0;
    let monitorsCache = null;
    let rendererSuspendedByNotch = false;
    let appearanceOpen = false;
    let idleFaded = false;
    let idleTimer = null;
    let pointerInsideNotch = false;

    function shouldPauseIdleFade() {
      if (!prefs.enabled || !prefs.idleFadeEnabled) return true;
      const secs = Number(prefs.idleFadeSeconds);
      if (!Number.isFinite(secs) || secs <= 0) return true;
      if (!NS?.isDockedPresentation(state) || !NS?.isNotchVisible(state)) return true;
      if (pointerInsideNotch || appearanceOpen) return true;
      if (state.interaction === 'dragActive' || state.interaction === 'dragEnter') return true;
      if (state.attention === 'approval' || state.attention === 'error') return true;
      try {
        const active = document.activeElement;
        if (active && ui?.shellEl?.contains(active) && active.matches('input, textarea, select')) return true;
      } catch {}
      return false;
    }

    function clearIdleTimer() {
      if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
      }
    }

    function applyIdleFadeState(nextFaded) {
      const target = Boolean(nextFaded);
      if (idleFaded === target) return;
      idleFaded = target;
      ui?.setIdleFade?.(idleFaded, prefs.idleFadeOpacity || 'subtle');
    }

    function scheduleIdleFade() {
      clearIdleTimer();
      if (shouldPauseIdleFade()) {
        applyIdleFadeState(false);
        return;
      }
      const delayMs = Math.max(1000, Math.round(Number(prefs.idleFadeSeconds) * 1000));
      idleTimer = setTimeout(() => {
        idleTimer = null;
        if (!shouldPauseIdleFade()) applyIdleFadeState(true);
      }, delayMs);
    }

    function wakeFromIdleFade(rearm = true) {
      clearIdleTimer();
      applyIdleFadeState(false);
      if (rearm) scheduleIdleFade();
    }

    const perfStats = {
      dockTransitions: 0,
      undockTransitions: 0,
      layoutSamplesMs: [],
      renderSamplesMs: [],
      droppedAcks: 0
    };

    function recordSample(arr, val) {
      arr.push(val);
      if (arr.length > 120) arr.shift();
    }

    function prefersReducedMotion() {
      try {
        return Boolean(
          prefs.motionIntensity === 'reduced' ||
          root.Axx?.app?.store?.data?.settings?.reducedMotion ||
          root.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        );
      } catch {
        return false;
      }
    }

    function getWorkArea() {
      const g = root.Axx?.resident?.geometry;
      if (g && Number(g.workWidth) > 0 && Number(g.workHeight) > 0) {
        return { x: Number(g.workX) || 0, y: Number(g.workY) || 0, width: Number(g.workWidth), height: Number(g.workHeight) };
      }
      const d = root.Axx?.desktop;
      if (d && Number(d.width) > 0 && Number(d.height) > 0) {
        return { x: Number(d.x) || 0, y: Number(d.y) || 0, width: Number(d.width), height: Number(d.height) };
      }
      return {
        x: 0,
        y: 0,
        width: Math.max(320, root.innerWidth || 1536),
        height: Math.max(240, root.innerHeight || 816)
      };
    }

    let lastMotionHitSync = 0;
    function pumpMotion() {
      if (motionRaf || !motion || motion.isSettled()) return;
      lastMotionFrame = performance.now();
      const stepFrame = (timestamp) => {
        motionRaf = 0;
        if (!motion || motion.isSettled()) {
          renderNow();
          root.Axx?.app?.updateHitMap?.();
          return;
        }
        const dt = Math.max(0, Math.min(0.05, (timestamp - lastMotionFrame) / 1000));
        lastMotionFrame = timestamp;
        motion.step(dt, prefersReducedMotion());
        renderNow();
        if (timestamp - lastMotionHitSync >= 70) {
          lastMotionHitSync = timestamp;
          root.Axx?.app?.updateHitMap?.();
        }
        if (!motion.isSettled() && typeof root.requestAnimationFrame === 'function') {
          motionRaf = root.requestAnimationFrame(stepFrame);
        } else {
          root.Axx?.app?.updateHitMap?.();
        }
      };
      if (typeof root.requestAnimationFrame === 'function') {
        motionRaf = root.requestAnimationFrame(stepFrame);
      } else {
        motion.snap({
          width: motion.channels.width.target,
          height: motion.channels.height.target,
          radius: motion.channels.radius.target,
          shellOpacity: motion.channels.shellOpacity.target,
          contentReveal: motion.channels.contentReveal.target,
          avatarOpacity: motion.channels.avatarOpacity.target
        });
        root.Axx?.app?.updateHitMap?.();
      }
    }

    function resolveCurrentLayout(nextState, ctx) {
      const t0 = performance.now();
      const work = getWorkArea();
      const layout = NL
        ? NL.resolveAdaptiveGeometry(nextState, work, 1, {
            projections: ctx.projections,
            density: prefs.density,
            surfaceScale: prefs.surfaceScale,
            expandedScalePercent: prefs.expandedScalePercent,
            compactWidthPx: prefs.compactWidthPx,
            surfaceShape: prefs.surfaceShape,
            cornerRadiusScale: prefs.cornerRadiusScale,
            topOffsetPx: prefs.topOffsetPx,
            horizontalAlign: prefs.horizontalAlign,
            portalCount: ctx.portalItems?.length || 0,
            hasApproval: ctx.commandOperation?.state === 'awaiting_approval',
            appearanceOpen,
            intentResultCount: ctx.intentResults?.length || 4
          })
        : NS.resolveLayout(nextState, work, 1, { activityCount: ctx.projections.length });
      recordSample(perfStats.layoutSamplesMs, performance.now() - t0);
      return layout;
    }

    function computeTargets(nextState, ctx) {
      const layout = resolveCurrentLayout(nextState, ctx);
      if (motion) {
        const reduced = prefersReducedMotion();
        motion.setProfile?.(prefs.motionIntensity);
        const docked = Boolean(NS?.isDockedPresentation(nextState));
        motion.setTargets({
          x: layout.x,
          y: layout.y,
          width: layout.width,
          height: layout.height,
          radius: layout.radius,
          shellOpacity: docked ? 1 : 0,
          contentReveal: (nextState.size === 'expanded' || nextState.size === 'peek') ? 1 : 0,
          avatarOpacity: docked ? 0 : 1
        }, reduced);
        pumpMotion();
      }
      return layout;
    }

    function buildLiveSnapshot() {
      if (!NK) return null;
      const Axx = root.Axx || {};
      const r = Axx.app?.renderer;
      const res = Axx.resident;
      const g = res?.geometry || {};
      const snap = NK.captureSnapshot({
        settings: Axx.app?.store?.data?.settings,
        studio: r?.getStudio?.(),
        camera: r?.getCamera20?.(),
        finish: r?.finish,
        identityRevision: state.explicitIdentityEditRevision,
        freePosition: {
          displayId: prefs.preferredMonitor && prefs.preferredMonitor !== 'auto' ? prefs.preferredMonitor : state.displayId,
          screenX: g.screenX,
          screenY: g.screenY,
          anchorX: res?.anchor?.x,
          anchorY: res?.anchor?.y,
          size: res?.size
        }
      });
      NK.persistSnapshot(snap);
      return snap;
    }

    function silenceTendrils() {
      try {
        root.Axx?.app?.renderer?.setReach?.(null, 0);
        root.Axx?.reach?.stop?.();
        if (root.Axx?.organic?.tendrils) {
          root.Axx.organic.tendrils.visibleCount = 0;
          root.Axx.organic.tendrils.pendingDraw = null;
          root.Axx.organic.tendrils.drawQueued = false;
          if (root.Axx.organic.tendrils.canvas) {
            root.Axx.organic.tendrils.canvas.hidden = true;
          }
          root.Axx.organic.tendrils.ctx?.clearRect?.(0, 0, root.Axx.organic.tendrils.width || 0, root.Axx.organic.tendrils.height || 0);
        }
        if (root.Axx?.flow?.delivery) {
          root.Axx.flow.delivery.visibleCount = 0;
          root.Axx.flow.delivery.pendingDraw = null;
          if (root.Axx.flow.delivery.canvas) root.Axx.flow.delivery.canvas.hidden = true;
        }
      } catch {}
    }

    function setRendererSuspended(suspend) {
      const r = root.Axx?.app?.renderer;
      if (!r || typeof r.setHidden !== 'function') return;
      if (suspend && prefs.suspendRendererWhenDocked !== false) {
        if (!rendererSuspendedByNotch) {
          rendererSuspendedByNotch = true;
          r.setHidden(true);
        }
      } else if (!suspend && rendererSuspendedByNotch) {
        rendererSuspendedByNotch = false;
        if (root.Axx?.app?.machine?.visible !== false) {
          r.setHidden(false);
        }
      }
    }

    function applySideEffects(effects) {
      for (const eff of effects) {
        if (eff.type === 'RETRACT_TENDRILS') {
          clearTimeout(retractTimer);
          const hadTendrils = Boolean(
            (root.Axx?.organic?.tendrils?.visibleCount || 0) > 0 ||
            root.Axx?.app?.renderer?.reaching
          );
          silenceTendrils();
          const completeRetract = () => {
            if (state.physical !== 'retracting' || state.dockEpoch !== eff.epoch) return;
            silenceTendrils();
            dispatch({ type: 'RETRACT_COMPLETE', epoch: eff.epoch, tentacleLinks: 0 });
          };
          if (!hadTendrils || prefersReducedMotion()) {
            queueMicrotask(completeRetract);
          } else {
            retractTimer = setTimeout(completeRetract, RETRACT_DURATION_MS);
          }
        } else if (eff.type === 'DISABLE_TENDRILS') {
          silenceTendrils();
        } else if (eff.type === 'SUSPEND_3D_RENDERER') {
          silenceTendrils();
          setRendererSuspended(true);
          perfStats.dockTransitions++;
          ui?.playTactileChime?.('dock');
          if (prefs.lastStablePhysical !== 'docked') {
            prefs = NK ? NK.savePreferences({ ...prefs, lastStablePhysical: 'docked' }) : { ...prefs, lastStablePhysical: 'docked' };
          }
        } else if (eff.type === 'RESTORE_SNAPSHOT') {
          const snap = eff.snapshot || state.snapshot || NK?.loadPersistedSnapshot();
          if (NK && snap && root.Axx?.app) {
            NK.restoreSnapshot(
              snap,
              {
                store: root.Axx.app.store,
                renderer: root.Axx.app.renderer,
                resident: root.Axx.resident,
                applySettings: () => {
                  root.Axx.app.applySettings?.();
                  root.Axx.app.refreshIdentity?.();
                }
              },
              { preserveEditedIdentity: Boolean(eff.preserveEditedIdentity) }
            );
          }
          NK?.persistSnapshot(null);
        } else if (eff.type === 'RESUME_3D_RENDERER') {
          setRendererSuspended(false);
          perfStats.undockTransitions++;
          ui?.playTactileChime?.('undock');
          if (prefs.lastStablePhysical !== 'free') {
            prefs = NK ? NK.savePreferences({ ...prefs, lastStablePhysical: 'free' }) : { ...prefs, lastStablePhysical: 'free' };
          }
        } else if (eff.type === 'ENABLE_FREE_TENDRILS') {
          try {
            if (root.Axx?.organic?.tendrils?.canvas && root.Axx?.app?.machine?.visible) {
              root.Axx.organic.tendrils.canvas.hidden = false;
            }
          } catch {}
        } else if (eff.type === 'OPEN_STAGE_SURFACE') {
          syncStagePanel(true, eff.content);
        } else if (eff.type === 'CLOSE_STAGE_SURFACE') {
          syncStagePanel(false);
        } else if (eff.type === 'SYNC_HIT_REGIONS' || eff.type === 'APPLY_VISIBILITY_POLICY') {
          root.Axx?.app?.updateHitMap?.();
        } else if (eff.type === 'APPLY_NATIVE_GEOMETRY') {
          syncNativeLayout(eff);
        } else if (eff.type === 'ACQUIRE_FOCUS') {
          invokeNative('notch_focus', { acquire: true, allowClickFocus: true });
        } else if (eff.type === 'RELEASE_FOCUS') {
          const allowClick = Boolean(state.size === 'expanded' || state.stageOpen);
          invokeNative('notch_focus', { acquire: false, restoreFocus: !allowClick, allowClickFocus: allowClick });
        } else if (eff.type === 'PERSIST_PREFS') {
          NK?.savePreferences({ ...prefs, pinnedActivityId: state.pinnedActivityId || null });
        }
      }
    }

    function invokeNative(cmd, args) {
      if (typeof root.Axx?.nativeInvoke === 'function') {
        return Promise.resolve(root.Axx.nativeInvoke(cmd, args)).catch(() => null);
      }
      const inv = root.__TAURI__?.core?.invoke || root.__TAURI_INTERNALS__?.invoke;
      if (typeof inv === 'function') {
        return inv(cmd, args).catch(() => null);
      }
      return Promise.resolve(null);
    }

    function resolvedDisplayId() {
      if (prefs.preferredMonitor && prefs.preferredMonitor !== 'auto') return prefs.preferredMonitor;
      return state.displayId || 'primary';
    }

    function syncNativeLayout(eff) {
      const work = getWorkArea();
      const winW = Math.min(Math.max(work.width, 320), 4096);
      const winH = Math.min(Math.max(work.height, 240), 4096);
      const anchorX = Math.round(winW / 2);
      const anchorY = eff.mode === 'free' ? Math.round(winH / 2) : 0;
      const targetDisplay = eff.displayId || resolvedDisplayId();
      const sig = `${eff.mode}|${eff.epoch}|${eff.revision}|${winW}|${winH}|${state.size}|${state.stageOpen}|${targetDisplay}`;
      if (sig === lastNativeSig) {
        if (eff.mode === 'docking') {
          queueMicrotask(() => dispatch({ type: 'NATIVE_GEOMETRY_ACK', epoch: eff.epoch, revision: eff.revision, tentacleLinks: 0 }));
        } else if (eff.mode === 'undocking') {
          queueMicrotask(() => dispatch({ type: 'UNDOCK_COMPLETE', epoch: eff.epoch, avatarValid: true }));
        }
        return;
      }
      lastNativeSig = sig;
      const allowClick = Boolean(state.size === 'expanded' || state.stageOpen);
      if (NS?.isDockedPresentation(state)) {
        void invokeNative('notch_focus', { acquire: eff.activate === true, restoreFocus: false, allowClickFocus: allowClick });
      }
      invokeNative('desktop_layout', {
        width: winW,
        height: winH,
        anchorX,
        anchorY,
        ready: true,
        panelDrag: false,
        stableSurface: true,
        dockEpoch: eff.epoch ?? state.dockEpoch,
        geometryRevision: eff.revision ?? state.geometryRevision,
        displayId: targetDisplay
      }).then((ack) => {
        if (ack && typeof ack.dockEpoch === 'number' && ack.dockEpoch < state.dockEpoch) {
          perfStats.droppedAcks++;
          return;
        }
        if (eff.mode === 'docking' && state.physical === 'docking' && state.dockEpoch === eff.epoch) {
          dispatch({ type: 'NATIVE_GEOMETRY_ACK', epoch: eff.epoch, revision: eff.revision, tentacleLinks: 0 });
        } else if (eff.mode === 'undocking' && state.physical === 'undocking' && state.dockEpoch === eff.epoch) {
          dispatch({ type: 'UNDOCK_COMPLETE', epoch: eff.epoch, avatarValid: true });
        } else {
          root.Axx?.app?.updateHitMap?.();
        }
      });
    }

    function ensureStageBar(panel) {
      let bar = document.getElementById('notch-stage-bar');
      if (!panel) return null;
      if (!bar) {
        bar = document.createElement('div');
        bar.id = 'notch-stage-bar';
        const title = document.createElement('span');
        title.id = 'notch-stage-title';
        title.textContent = 'AXX · Tu espacio de trabajo';
        const btns = document.createElement('div');
        btns.style.cssText = 'display:flex;gap:6px;';
        const detachBtn = document.createElement('button');
        detachBtn.type = 'button';
        detachBtn.id = 'notch-stage-detach-btn';
        detachBtn.className = 'notch-pill-btn';
        detachBtn.onclick = () => {
          dispatch({ type: 'SET_STAGE_DETACHED', detached: !state.stageDetached, pos: state.stagePos });
          syncStagePanel(true);
        };
        const returnBtn = document.createElement('button');
        returnBtn.type = 'button';
        returnBtn.id = 'notch-stage-return-btn';
        returnBtn.className = 'notch-pill-btn';
        returnBtn.textContent = 'Volver al notch';
        returnBtn.onclick = () => dispatch({ type: 'CLOSE_STAGE', nextSize: 'compact' });
        btns.append(detachBtn, returnBtn);
        bar.append(title, btns);
        panel.prepend(bar);
      }
      const detachBtn = document.getElementById('notch-stage-detach-btn');
      if (detachBtn) {
        detachBtn.textContent = state.stageDetached ? 'Acoplar al notch' : 'Mover libremente';
      }
      return bar;
    }

    function mapContentToFeature(content) {
      if (content === 'media') return 'music';
      if (content === 'voice') return 'dictation';
      if (content === 'agents') return 'agent';
      if (content === 'magicPen') return 'magicpen';
      if (content === 'transfer') return 'transfer';
      if (content === 'portal') return 'files';
      return 'chat';
    }

    function syncStagePanel(open, requestedContent) {
      const panel = document.getElementById('panel');
      const stage = document.getElementById('stage');
      if (stage) {
        stage.classList.toggle('notch-avatar-hidden', NS?.isDockedPresentation(state) || false);
      }
      if (!panel) return;
      if (open) {
        const feature = mapContentToFeature(requestedContent || state.content);
        if ((panel.hidden || root.Axx?.companion?.currentFeature !== feature) && root.Axx?.companion?.openFeature) {
          root.Axx.companion.openFeature(feature);
        }
        panel.hidden = false;
        panel.dataset.notchStage = 'true';
        panel.dataset.stageDetached = state.stageDetached ? 'true' : 'false';
        ensureStageBar(panel);
        if (state.stageDetached) {
          const pos = state.stagePos || { x: Math.max(24, Math.round((getWorkArea().width - 680) / 2)), y: 96 };
          panel.style.setProperty('left', `${pos.x}px`, 'important');
          panel.style.setProperty('top', `${pos.y}px`, 'important');
          panel.style.setProperty('transform', 'none', 'important');
        } else {
          const layout = resolveCurrentLayout(state, collectContext());
          panel.style.setProperty('left', '50%', 'important');
          panel.style.setProperty('top', `${Math.round(layout.height + 14)}px`, 'important');
          panel.style.setProperty('transform', 'translateX(-50%)', 'important');
        }
      } else {
        document.getElementById('notch-stage-bar')?.remove();
        delete panel.dataset.notchStage;
        delete panel.dataset.stageDetached;
        panel.style.transform = '';
        if (!panel.hidden) {
          root.Axx?.app?.closePanel?.();
          panel.hidden = true;
        }
      }
      root.Axx?.app?.updateHitMap?.();
    }

    function dispatch(event) {
      if (!NS) return state;
      const result = NS.reduce(state, event);
      state = result.next;
      const ctx = collectContext();
      const layout = computeTargets(state, ctx);

      const hideAvatar = NS.isDockedPresentation(state);
      document.body?.classList?.toggle('axx-notch-docked', hideAvatar);
      const stageEl = document.getElementById('stage');
      if (stageEl) {
        stageEl.classList.toggle('notch-avatar-hidden', hideAvatar);
        stageEl.style.opacity = hideAvatar ? '0' : '1';
        stageEl.style.pointerEvents = hideAvatar ? 'none' : '';
      }

      applySideEffects(result.effects);
      renderNow(layout, ctx);
      if (['DOCK_COMMIT', 'DOCK_COMMAND', 'NATIVE_GEOMETRY_ACK', 'SET_SURFACE_SIZE', 'SET_CONTENT_MODE', 'OPEN_STAGE', 'CLOSE_STAGE'].includes(event.type)) {
        wakeFromIdleFade(true);
      } else {
        scheduleIdleFade();
      }
      return state;
    }

    function clearApproachTimer() {
      if (approachTimer) {
        clearTimeout(approachTimer);
        approachTimer = null;
      }
      approachDwellSatisfied = false;
      approachPull = 0;
    }

    let intentCategory = 'all';

    function inferIntentCategory(item) {
      const text = `${item.id || ''} ${item.title || ''} ${item.badge || ''}`.toLowerCase();
      if (/media|reproduc|música|music|audio|spotify|pausar/.test(text)) return 'media';
      if (/voice|voz|dicta|hablar|mic/.test(text)) return 'voice';
      if (/agent|studio|code|codex|claude|antigravity/.test(text)) return 'agents';
      if (/system|sistema|telemetry|cpu|ram|disco|recurso|timer|temporiz|focus|concentr|magic/.test(text)) return 'system';
      return 'system';
    }

    function buildIntentCandidates(query, category = intentCategory) {
      const q = String(query || '').trim().toLowerCase();
      const cat = String(category || 'all').toLowerCase();
      const out = [
        { id: 'local:timer-5m', title: 'Temporizador 5 minutos', badge: 'Focus', category: 'system', cmd: 'temporizador 5 min', available: true },
        { id: 'local:focus-25m', title: 'Sesión Concentración 25m', badge: 'Focus', category: 'system', cmd: 'concentracion 25 min', available: true },
        { id: 'local:media-toggle', title: 'Pausar / Reanudar reproducción', badge: 'Media', category: 'media', cmd: 'media toggle', available: true },
        { id: 'local:magic-pen', title: 'Abrir Magic Pen (Anotar / Captura)', badge: 'Magic Lens', category: 'system', cmd: 'magic pen', available: true },
        { id: 'local:voice', title: 'Activar Voz / Dictado editable', badge: 'Voice Studio', category: 'voice', cmd: 'voice', available: true },
        { id: 'local:code-studio', title: 'Abrir Axx Code Studio (Agentes)', badge: 'Agentes', category: 'agents', cmd: 'code studio', available: true },
        { id: 'local:telemetry', title: 'Medir recursos de este PC (CPU / RAM / Disco)', badge: 'Sistema', category: 'system', commandId: 'axx.system.telemetry', available: Boolean(root.Axx?.desktop?.ready) }
      ];
      const catalog = root.Axx?.commandLibrary?.commands;
      if (Array.isArray(catalog)) {
        for (const c of catalog) {
          out.push({
            id: c.id,
            commandId: c.id,
            title: c.title || c.id,
            badge: c.execution_enabled ? 'Comando' : 'Bloqueado',
            category: inferIntentCategory(c),
            available: Boolean(c.execution_enabled),
            hasParams: Boolean(c.parameters && Object.keys(c.parameters).length > 0)
          });
        }
      }
      const byCategory = cat === 'all' ? out : out.filter(item => item.category === cat);
      const filtered = q
        ? byCategory.filter(item =>
            item.title.toLowerCase().includes(q) ||
            item.id.toLowerCase().includes(q) ||
            String(item.badge || '').toLowerCase().includes(q)
          )
        : byCategory;
      return filtered.slice(0, 6);
    }

    function collectContext() {
      const Axx = root.Axx || {};
      const collected = NP ? NP.collectAllProjections(Axx) : { projections: [], lastReceipt: null, recall: { threads: [], recipes: [] }, backendReady: false, modelConnected: false };
      return {
        ...collected,
        commandOperation: Axx.commandLibrary?.operation || null,
        hasCommands: Boolean(Axx.commandLibrary),
        hasConverter: Boolean(Axx.converter),
        hasTransfer: Boolean(Axx.transfer),
        hasSystemMedia: Boolean(Axx.nativeMusic),
        portalItems,
        offlineQueue,
        intentQuery,
        intentCategory,
        intentResults: buildIntentCandidates(intentQuery, intentCategory),
        pinnedActivityId: state.pinnedActivityId || prefs.pinnedActivityId || null,
        contextFrozen: Boolean(state.contextFrozen),
        styleDirection: prefs.styleDirection || 'identity-accent',
        preferences: prefs,
        telemetry: telemetryCache,
        telemetryPending, telemetryError, portalReceipt,
        approachPull,
        privacyShield: Boolean(prefs.privacyCurtain)
      };
    }

    function renderNow(precomputedLayout, precomputedCtx) {
      if (!ui) return;
      const t0 = performance.now();
      const ctx = precomputedCtx || collectContext();
      const layout = precomputedLayout || resolveCurrentLayout(state, ctx);
      const channels = motion ? motion.snapshot() : {};
      ui.update({ Axx: root.Axx, state, layout, channels, context: ctx });
      recordSample(perfStats.renderSamplesMs, performance.now() - t0);
    }

    function stepProjections(now = Date.now()) {
      const ctx = collectContext();
      const sig = ctx.projections.map(p => `${p.id}:${p.status}:${p.revision}:${p.metric || ''}`).join('|') + '|' + (ctx.backendReady ? '1' : '0');
      const changed = sig !== stepProjections.lastSig;
      if (changed) {
        stepProjections.lastSig = sig;
        const userTyping = Boolean(document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName));
        if (attentionEngine) {
          attentionEngine.evaluateEvent({ kind: 'projection-sync', priority: state.attention === 'approval' ? 'approval' : 'passive', userTyping, now });
        }
        dispatch({ type: 'SYNC_PROJECTIONS', projections: ctx.projections, backendOffline: !ctx.backendReady && Boolean(root.Axx?.app?.bridge) });
      }
      // Geometry has one RAF clock; projection polling must not advance the springs twice.
      const settled = motion ? motion.isSettled() : true;
      lastTransitionTime = performance.now();
      if (NS?.isDockedPresentation(state) || state.physical === 'approach' || !settled) {
        renderNow(null, ctx);
      }
    }

    function executeActivityAction(proj, act) {
      const Axx = root.Axx;
      if (!Axx) return;
      if (act.capabilityId === 'timer.pause' || act.capabilityId === 'timer.resume') {
        Axx.app?.pauseResume?.();
      } else if (act.capabilityId === 'timer.cancel') {
        Axx.app?.cancelCurrent?.();
      } else if (act.capabilityId === 'timer.open' || act.capabilityId === 'chat.open') {
        dispatch({ type: 'OPEN_STAGE', content: proj?.kind === 'chat' ? 'chat' : 'orbit', activityId: proj?.id });
      } else if (act.capabilityId === 'command.open_approval') {
        dispatch({ type: 'SET_CONTENT_MODE', content: 'intent', size: 'expanded', activate: true });
      } else if (act.capabilityId === 'command.cancel') {
        Axx.commandLibrary?.cancel?.();
      } else if (act.capabilityId === 'agents.open_stage') {
        dispatch({ type: 'OPEN_STAGE', content: 'agents', activityId: proj?.id });
      } else if (act.capabilityId === 'agents.approve') {
        const opId = proj?.id?.replace('agent-approval:', '');
        if (opId) Axx.evolution3?.controllers?.workApprovals?.resolveCard?.(opId, true);
      } else if (act.capabilityId === 'agents.deny') {
        const opId = proj?.id?.replace('agent-approval:', '');
        if (opId) Axx.evolution3?.controllers?.workApprovals?.resolveCard?.(opId, false);
      } else if (act.capabilityId === 'media.play' || act.capabilityId === 'media.pause') {
        if (Axx.media16?.source === 'system') Axx.nativeMusic?.toggle?.();
        else Axx.actions?.music?.toggle?.();
      } else if (act.capabilityId === 'media.next') {
        if (Axx.media16?.source === 'system') Axx.nativeMusic?.command?.('next');
        else Axx.actions?.music?.next?.();
      } else if (act.capabilityId === 'media.previous') {
        if (Axx.media16?.source === 'system') Axx.nativeMusic?.command?.('previous');
        else Axx.actions?.music?.previous?.();
      } else if (act.capabilityId === 'voice.stop') {
        Axx.nativeVoice?.stop?.();
        Axx.symbiosis?.reader?.stop?.();
      } else if (act.capabilityId === 'voice.open') {
        dispatch({ type: 'OPEN_STAGE', content: 'voice', activityId: proj?.id });
      } else if (act.capabilityId === 'chat.cancel') {
        Axx.companion?.stop?.();
      } else if (act.capabilityId === 'screen.toggle') {
        Axx.actions?.screen?.togglePause?.();
      } else if (act.capabilityId === 'screen.stop') {
        Axx.actions?.screen?.stop?.();
      } else if (act.capabilityId === 'transfer.open') {
        dispatch({ type: 'OPEN_STAGE', content: 'transfer', activityId: proj?.id });
      }
      stepProjections();
    }

    function submitIntent(text) {
      const Axx = root.Axx;
      const raw = String(text || '').trim();
      if (!raw || !Axx) return;
      recentIntents = [raw, ...recentIntents.filter(r => r !== raw)].slice(0, 8);
      const lower = raw.toLowerCase();
      if (lower === 'media toggle' || lower.startsWith('pausa m') || lower.startsWith('reproduc')) {
        if (Axx.media16?.source === 'system') Axx.nativeMusic?.toggle?.();
        else Axx.actions?.music?.toggle?.();
        stepProjections();
        return;
      }
      if (lower === 'magic pen') {
        dispatch({ type: 'OPEN_STAGE', content: 'magicPen' });
        Axx.magicPen?.open?.();
        return;
      }
      if (lower === 'voice' || lower === 'voz') {
        dispatch({ type: 'OPEN_STAGE', content: 'voice' });
        Axx.nativeVoice?.toggle?.();
        return;
      }
      if (lower === 'code studio' || lower === 'agentes') {
        dispatch({ type: 'OPEN_STAGE', content: 'agents' });
        if (document.querySelector('.axx-code-studio')?.hidden) Axx.codeStudio?.open?.();
        syncStagePanel(true, 'agents');
        return;
      }
      const parsed = typeof Axx.parseIntent === 'function' ? Axx.parseIntent(raw) : null;
      if (parsed && typeof Axx.companion?.runLocal === 'function' && parsed.type && parsed.type !== 'chat') {
        Axx.companion.runLocal(parsed);
        stepProjections();
        return;
      }
      // Safe Offline Queue: preserve intent/chat draft when backend is disconnected without auto-replay
      if (Axx.isNative?.() && Axx.desktop && !Axx.desktop.ready && !Axx.companion?.brain?.connected) {
        offlineQueue = [...offlineQueue, { id: `off-${Date.now()}`, text: raw, createdAt: Date.now() }].slice(-10);
        dispatch({ type: 'SET_CONTENT_MODE', content: 'recall', size: 'expanded' });
        renderNow();
        return;
      }
      if (typeof Axx.companion?.send === 'function') {
        void Axx.companion.send(raw);
        dispatch({ type: 'SET_CONTENT_MODE', content: 'orbit', size: 'expanded' });
        stepProjections();
      }
    }

    function runIntentItem(item) {
      if (!item) return;
      if (item.cmd) {
        submitIntent(item.cmd);
        return;
      }
      if (item.commandId && root.Axx?.commandLibrary) {
        if (!item.available) {
          root.Axx.app?.toast?.('Este comando requiere adaptación validada en CommandLibrary.');
          return;
        }
        void root.Axx.commandLibrary.prepare?.(item.commandId, {}, 'text').catch(() => {});
        dispatch({ type: 'SET_CONTENT_MODE', content: 'intent', size: 'expanded' });
      }
    }

    function handlePortalDrop({ files = [], text = '' }) {
      const next = [];
      for (const f of files) {
        if (!f) continue;
        next.push({ id: `${Date.now()}-${next.length}`, kind: 'file', name: f.name || 'archivo', size: f.size || 0, type: f.type || '', file: f });
      }
      if (text && text.trim()) {
        const value = text.trim();
        if (value.length > 20000) { portalReceipt = 'El texto supera 20.000 caracteres. Usa un archivo de texto.'; renderNow(); return; }
        let url; try { url = new URL(value); } catch {}
        const isLink = url && ['https:', 'http:'].includes(url.protocol);
        next.push({ id: `${Date.now()}-txt`, kind: isLink ? 'link' : 'text', name: isLink ? url.hostname : 'Texto recibido', text: value });
      }
      if (!next.length) return;
      portalItems = [...portalItems, ...next].slice(-MAX_PORTAL_ITEMS);
      portalReceipt = `${next.length === 1 ? next[0].kind === 'file' ? 'Archivo recibido' : next[0].kind === 'link' ? 'Enlace recibido' : 'Texto recibido' : `${next.length} elementos recibidos`} · listo para usar`;
      const audio = root.Axx?.companion?.audio;
      if (audio && prefs.soundEffectsEnabled !== false) {
        void Promise.resolve(audio.unlock?.()).then(() => audio.play?.('settle', 'ui', `portal-${next[0].id}`)).catch(() => {});
      }
      wakeFromIdleFade();
      dispatch({ type: 'PORTAL_DROP', files, text });
      renderNow();
    }

    async function handlePortalAction(kind) {
      if (kind === 'clear') {
        portalItems = [];
        dispatch({ type: 'PORTAL_DRAG_LEAVE' });
        renderNow();
        return;
      }
      if (kind === 'converter' && root.Axx?.converter) {
        const files = portalItems.map(i => i.file).filter(Boolean);
        if (files.length) void root.Axx.converter.select?.(files);
        dispatch({ type: 'OPEN_STAGE', content: 'portal' });
        root.Axx.flow?.select?.('converter');
        return;
      }
      if (kind === 'transfer' && root.Axx?.transfer) {
        dispatch({ type: 'OPEN_STAGE', content: 'transfer' });
        root.Axx.transfer.open?.();
        return;
      }
      if (kind === 'chat' && portalItems.length) {
        const files = portalItems.filter(i => i.file);
        if (files.length > 1) { root.Axx.app?.toast?.('Prepara un archivo de texto cada vez. Los demás siguen en Archivos.'); return; }
        if (files.length && !await root.Axx.companion?.attach?.(files[0].file)) return;
        const summary = portalItems.filter(i => i.text).map(i => i.text).join('\n');
        const input = document.getElementById('chat-input');
        if (input && summary) { input.value = input.value ? `${input.value}\n${summary}` : summary; input.dispatchEvent(new Event('input', { bubbles: true })); }
        dispatch({ type: 'OPEN_STAGE', content: 'chat' });
      }
    }

    const ui = NU ? NU.createNotchUI({
      onToggleExpand() {
        if (state.size === 'expanded') dispatch({ type: 'SET_SURFACE_SIZE', size: 'compact', interaction: 'none' });
        else dispatch({ type: 'SET_SURFACE_SIZE', size: 'expanded', content: state.content === 'home' ? 'orbit' : state.content, activate: true });
      },
      onSelectContent(content) {
        dispatch({ type: 'SET_CONTENT_MODE', content, size: 'expanded', activate: true });
      },
      onPreferencesChange(patch) { setPreferences(patch); },
      onAppearanceChange(open) {
        appearanceOpen = Boolean(open);
        const ctx = collectContext();
        renderNow(computeTargets(state, ctx), ctx);
        root.Axx?.app?.updateHitMap?.();
      },
      onSelectActivity(id) {
        dispatch({ type: 'SELECT_ACTIVITY', activityId: id });
      },
      onTogglePin(id) {
        dispatch({ type: 'PIN_ACTIVITY', activityId: id });
      },
      onActivityAction: executeActivityAction,
      onMediaSeek(sec) {
        if (!Number.isFinite(sec) || sec < 0) return;
        if (root.Axx?.media16?.source === 'system') root.Axx?.nativeMusic?.command?.('seek', sec);
        else {
          const music = root.Axx?.actions?.music;
          if (music?.audio && Number.isFinite(music.audio.duration)) music.seek?.(Math.min(sec, music.audio.duration) - music.audio.currentTime);
        }
        stepProjections();
      },
      onSetMediaSource(source) {
        if (!['local', 'system'].includes(source)) return;
        root.Axx?.media16?.choose?.(source);
        stepProjections();
      },
      onSelectMediaSession(id) {
        if (root.Axx?.nativeMusic) {
          root.Axx.nativeMusic.selectedId = id;
          root.Axx.nativeMusic.paint?.();
          stepProjections();
        }
      },
      onApproveOperation() {
        root.Axx?.commandLibrary?.approve?.();
        stepProjections();
      },
      onRejectOperation() {
        root.Axx?.commandLibrary?.cancel?.();
        stepProjections();
      },
      onIntentQueryChange(q, rebuildCb, cat) {
        intentQuery = q;
        if (typeof cat === 'string') intentCategory = cat;
        rebuildCb?.(buildIntentCandidates(q, intentCategory));
      },
      onSaveCustomPreset() {
        return saveCustomPreset();
      },
      onApplyCustomPreset() {
        return applyCustomPreset();
      },
      onExportPreferences() {
        return exportPreferencesJSON();
      },
      onImportPreferences(raw) {
        return importPreferencesJSON(raw);
      },
      onSelectIntentCommand: runIntentItem,
      onRunIntentItem: runIntentItem,
      onSubmitIntent: submitIntent,
      onToggleStage() {
        if (state.stageOpen) dispatch({ type: 'CLOSE_STAGE', nextSize: 'expanded' });
        else dispatch({ type: 'OPEN_STAGE' });
      },
      onOpenCodeStudio() {
        dispatch({ type: 'OPEN_STAGE', content: 'agents' });
        if (document.querySelector('.axx-code-studio')?.hidden) root.Axx?.codeStudio?.open?.();
        syncStagePanel(true, 'agents');
      },
      onTogglePrivacy() {
        setPreferences({ privacyCurtain: !prefs.privacyCurtain });
      },
      onToggleContextFreeze() {
        dispatch({ type: 'TOGGLE_CONTEXT_FREEZE' });
      },
      onPollTelemetry() {
        if (!root.Axx?.desktop?.ready || telemetryPending) return;
        telemetryPending = true; telemetryError = ''; renderNow();
        void root.Axx.backendRequest?.('POST', '/axx-api/actions/execute', {
          tool_name: 'system_telemetry',
          inputs: {},
          operation_id: root.Axx.newId?.() || `tel-${Date.now()}`
        }).then(res => {
          if (res?.output || res?.telemetry) {
            telemetryCache = { ...(res.telemetry || res.output), updatedAt: Date.now() };
            renderNow();
          }
          else telemetryError = 'El equipo no devolvió una medición. Vuelve a consultar.';
        }).catch(() => { telemetryError = 'No se pudo medir el equipo. Comprueba la conexión e inténtalo de nuevo.'; }).finally(() => { telemetryPending = false; renderNow(); });
      },
      async onOpenThread(id) {
        try {
          if (!id || !root.Axx?.chatWorkspace?.select) throw new Error('Conversaciones no disponibles.');
          if (root.Axx.chatWorkspace.busy) throw new Error('El chat está ocupado.');
          await root.Axx.chatWorkspace.select(id);
          if (root.Axx.chatWorkspace.active?.id !== id) throw new Error('No cambió el destino.');
          dispatch({ type: 'OPEN_STAGE', content: 'chat' });
        } catch { root.Axx.app?.toast?.('No se pudo abrir la conversación. Tu borrador se conserva.'); }
      },
      onRetryOfflineItem(id) {
        const idx = offlineQueue.findIndex(x => x.id === id);
        if (idx < 0) return;
        const [item] = offlineQueue.splice(idx, 1);
        submitIntent(item.text);
      },
      onHideNotch() {
        dispatch({ type: 'SET_VISIBILITY', visibility: 'userHidden' });
      },
      onUndock() {
        clearApproachTimer();
        dispatch({ type: 'UNDOCK_REQUEST' });
      },
      onPointerEnter() {
        pointerInsideNotch = true;
        wakeFromIdleFade(false);
        if (!prefs.hoverPeek || state.size !== 'compact' || !NS?.isDockedPresentation(state)) return;
        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(() => {
          if (state.size === 'compact' && state.interaction !== 'dragActive') {
            dispatch({ type: 'SET_SURFACE_SIZE', size: 'peek', interaction: 'hoverIntent' });
          }
        }, 160);
      },
      onPointerLeave() {
        pointerInsideNotch = false;
        clearTimeout(hoverTimer);
        if (state.size === 'peek') {
          dispatch({ type: 'SET_SURFACE_SIZE', size: 'compact', interaction: 'none' });
        }
        scheduleIdleFade();
      },
      onUserActivity() {
        wakeFromIdleFade(true);
      },
      onDragEnter() {
        dispatch({ type: 'PORTAL_DRAG_ENTER' });
      },
      onDragLeave() {
        dispatch({ type: 'PORTAL_DRAG_LEAVE' });
      },
      onDrop: handlePortalDrop,
      onPortalRemove(id) {
        portalItems = portalItems.filter(i => i.id !== id);
        renderNow();
      },
      onPortalAction: handlePortalAction,
      onEscape() {
        dispatch({ type: 'ESCAPE_PRESSED' });
      }
    }) : null;

    function saveCustomPreset() {
      const visualKeys = [
        'styleDirection', 'surfaceTheme', 'material', 'accent', 'customAccentHex',
        'surfaceShape', 'borderStyle', 'horizontalAlign', 'compactMetrics',
        'contrast', 'surfaceScale', 'density', 'motionIntensity',
        'surfaceOpacity', 'topOffsetPx', 'cornerRadiusScale', 'glowIntensity',
        'fontPreset', 'soundProfile', 'ambientPulse', 'showQuickChatButton',
        'showAvatarInNotch', 'idleFadeEnabled', 'idleFadeSeconds', 'idleFadeOpacity'
      ];
      const preset = {};
      for (const k of visualKeys) preset[k] = prefs[k];
      setPreferences({ customPreset: preset });
      return preset;
    }

    function applyCustomPreset() {
      if (!prefs.customPreset || typeof prefs.customPreset !== 'object') return false;
      setPreferences(prefs.customPreset);
      return true;
    }

    function exportPreferencesJSON() {
      return JSON.stringify(prefs, null, 2);
    }

    function importPreferencesJSON(raw) {
      try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ok: false, reason: 'JSON inválido' };
        const clean = NK ? NK.normalizePreferences({ ...prefs, ...parsed, enabled: prefs.enabled }) : { ...prefs, ...parsed };
        setPreferences(clean);
        return { ok: true, prefs: clean };
      } catch {
        return { ok: false, reason: 'No se pudo leer el JSON de configuración' };
      }
    }

    function setPreferences(patch) {
      if (patch?.resetNotch) {
        prefs = NK ? NK.resetPreferences() : { enabled: true };
        dispatch({ type: 'SET_ENABLED', enabled: Boolean(prefs.enabled) });
        settingsBinding?.sync?.(prefs);
        const ctx = collectContext();
        renderNow(computeTargets(state, ctx), ctx);
        root.Axx?.app?.updateHitMap?.();
        return prefs;
      }
      const nextPatch = { ...patch };
      delete nextPatch.toggleNow;
      prefs = NK ? NK.savePreferences({ ...prefs, ...nextPatch }) : { ...prefs, ...nextPatch };
      if ('enabled' in nextPatch) {
        dispatch({ type: 'SET_ENABLED', enabled: Boolean(prefs.enabled) });
      }
      if ('preferredMonitor' in nextPatch && NS?.isDockedPresentation(state)) {
        dispatch({ type: 'DISPLAY_CHANGED', displayId: nextPatch.preferredMonitor });
      }
      if ('suspendRendererWhenDocked' in nextPatch && NS?.isDockedPresentation(state)) {
        setRendererSuspended(Boolean(prefs.suspendRendererWhenDocked));
      }
      settingsBinding?.sync?.(prefs);
      const ctx = collectContext();
      const layout = computeTargets(state, ctx);
      renderNow(layout, ctx);
      ui?.setIdleFade?.(idleFaded, prefs.idleFadeOpacity || 'subtle');
      scheduleIdleFade();
      root.Axx?.app?.updateHitMap?.();
      return prefs;
    }

    function togglePresentation(trigger = 'toggle') {
      if (!prefs.enabled) setPreferences({ enabled: true });
      if (NS?.isDockedPresentation(state) && state.visibility === 'userHidden') {
        dispatch({ type: 'SET_VISIBILITY', visibility: 'normal' });
        return state;
      }
      if (NS?.isDockedPresentation(state)) undockNow(trigger);
      else dockNow(trigger);
      return state;
    }

    function dockNow() {
      if (!prefs.enabled) setPreferences({ enabled: true });
      if (state.visibility === 'userHidden') {
        dispatch({ type: 'SET_VISIBILITY', visibility: 'normal' });
      }
      clearApproachTimer();
      const snapshot = buildLiveSnapshot();
      dispatch({ type: 'DOCK_COMMAND', snapshot, displayId: resolvedDisplayId() });
      return state;
    }

    function undockNow() {
      clearApproachTimer();
      dispatch({ type: 'UNDOCK_REQUEST' });
      return state;
    }

    function onAvatarDragMove(info = {}) {
      if (!prefs.enabled || !prefs.autoDockOnTopDrag) return;
      const work = getWorkArea();
      const rawPointerY = Number(info.pointerClientY);
      const rawLocalY = Number(info.localY);
      const hasPointer = Number.isFinite(rawPointerY);
      const hasLocal = Number.isFinite(rawLocalY);
      const bestY = (hasPointer && hasLocal)
        ? Math.min(rawPointerY, rawLocalY)
        : (hasPointer ? rawPointerY : (hasLocal ? rawLocalY : 999));
      const pointerX = Number(info.pointerClientX ?? info.localX ?? work.width / 2);
      const localY = bestY <= work.height ? bestY : (bestY - work.y);
      const now = performance.now();
      let vy = 0;
      let vx = 0;
      if (prevDragSample && now > prevDragSample.t) {
        const dt = (now - prevDragSample.t) / 1000;
        vy = (localY - prevDragSample.y) / dt;
        vx = (pointerX - prevDragSample.x) / dt;
      }
      prevDragSample = { x: pointerX, y: localY, t: now };

      const evalRes = NL
        ? NL.evaluateApproach({
            localY,
            vy,
            vx,
            sensitivity: prefs.dockSensitivity || 'normal',
            alreadyInApproach: state.physical === 'approach'
          })
        : {
            inBand: NS.isInDockApproachBand(localY, 64, 28, state.physical === 'approach'),
            magneticPull: localY <= 64 ? 1 - localY / 64 : 0,
            dwellMs: 80
          };
      approachPull = evalRes.magneticPull || 0;

      if (evalRes.inBand && state.physical === 'free') {
        dispatch({ type: 'DRAG_APPROACH_ENTER', displayId: resolvedDisplayId() });
        clearApproachTimer();
        approachPull = evalRes.magneticPull || 0.35;
        approachTimer = setTimeout(() => { approachDwellSatisfied = true; }, evalRes.dwellMs || 80);
      } else if (!evalRes.inBand && state.physical === 'approach') {
        clearApproachTimer();
        dispatch({ type: 'DRAG_APPROACH_LEAVE' });
      } else if (state.physical === 'approach') {
        renderNow();
      }
    }

    function onAvatarDragEnd() {
      prevDragSample = null;
      if (state.physical === 'approach') {
        const shouldCommit = approachDwellSatisfied || approachPull >= 0.25;
        clearApproachTimer();
        if (shouldCommit) {
          const snapshot = buildLiveSnapshot();
          dispatch({ type: 'DOCK_COMMIT', snapshot, displayId: resolvedDisplayId() });
        } else {
          dispatch({ type: 'DRAG_APPROACH_LEAVE' });
        }
      } else {
        clearApproachTimer();
      }
    }

    function interactiveRegions() {
      if (!NS?.isNotchVisible(state)) return [];
      const regions = [];
      const rect = ui?.shellEl?.getBoundingClientRect?.();
      if (rect && rect.width > 0 && rect.height > 0) {
        regions.push({ x: rect.x, y: rect.y, width: rect.width, height: rect.height });
      }
      if (state.stageOpen) {
        const pRect = document.getElementById('panel')?.getBoundingClientRect?.();
        if (pRect && pRect.width > 0 && pRect.height > 0) {
          regions.push({ x: pRect.x, y: pRect.y, width: pRect.width, height: pRect.height });
        }
      }
      return regions;
    }

    function observeIdentityEdited() {
      if (NS?.isDockedPresentation(state)) {
        dispatch({ type: 'IDENTITY_EDITED_WHILE_DOCKED' });
      }
    }

    function init() {
      if (initialized) return api;
      initialized = true;

      settingsBinding = ui?.mountSettingsCard(
        prefs,
        (patch) => {
          if (patch.toggleNow) togglePresentation('settings-button');
          else setPreferences(patch);
        },
        async () => {
          const res = await invokeNative('notch_monitors', {});
          monitorsCache = Array.isArray(res) ? res : [];
          return monitorsCache;
        }
      );

      // Observe explicit customization while docked so snapshot restoration never overwrites deliberate changes
      if (root.Axx?.app && typeof root.Axx.app.applySettings === 'function') {
        const origApply = root.Axx.app.applySettings.bind(root.Axx.app);
        root.Axx.app.applySettings = (...args) => {
          const res = origApply(...args);
          observeIdentityEdited();
          return res;
        };
      }

      let lastToggleAt = 0;
      const guardedToggle = (source) => {
        const now = performance.now();
        if (now - lastToggleAt < 180) return;
        lastToggleAt = now;
        togglePresentation(source);
      };

      root.addEventListener('keydown', (ev) => {
        if (ev.altKey && ev.shiftKey && (ev.key === 'N' || ev.key === 'n')) {
          ev.preventDefault();
          guardedToggle('hotkey');
        }
      });

      const handleFullscreen = (payload) => {
        if (prefs.autoHideFullscreen === false) return;
        const fs = Boolean(payload?.foregroundFullscreenSameMonitor ?? payload?.fullscreen);
        dispatch({ type: 'SET_VISIBILITY', visibility: fs ? 'fullscreenSuppressed' : 'normal' });
      };

      const bridgeListen = root.Axx?.app?.bridge?.listen?.bind(root.Axx.app.bridge);
      const tauriListen = root.__TAURI__?.event?.listen;
      if (typeof bridgeListen === 'function') {
        void bridgeListen('axx-notch-toggle', () => guardedToggle('native')).catch(() => {});
        void bridgeListen('axx-fullscreen-policy', (payload) => handleFullscreen(payload)).catch(() => {});
      } else if (typeof tauriListen === 'function') {
        tauriListen('axx-notch-toggle', () => guardedToggle('tray')).catch(() => {});
        tauriListen('axx-fullscreen-policy', (ev) => handleFullscreen(ev?.payload)).catch(() => {});
      }

      const leftover = NK?.loadPersistedSnapshot();
      if (leftover && root.Axx?.app) {
        NK.restoreSnapshot(
          leftover,
          {
            store: root.Axx.app.store,
            renderer: root.Axx.app.renderer,
            resident: root.Axx.resident,
            applySettings: () => {
              root.Axx.app.applySettings?.();
              root.Axx.app.refreshIdentity?.();
            }
          },
          { preserveEditedIdentity: false }
        );
        NK.persistSnapshot(null);
      }

      stepProjections();
      if (prefs.enabled && prefs.rememberStableMode && prefs.lastStablePhysical === 'docked') {
        setTimeout(() => {
          if (state.physical === 'free' && prefs.enabled) dockNow();
        }, 260);
      }
      setInterval(() => {
        if (NS?.isDockedPresentation(state) && ['clock', 'clock-date', 'greeting'].includes(prefs.compactMetrics)) {
          renderNow();
        }
      }, 15000);
      return api;
    }

    const api = {
      init,
      getState: () => state,
      getPreferences: () => ({ ...prefs }),
      setPreferences,
      saveCustomPreset,
      applyCustomPreset,
      exportPreferencesJSON,
      importPreferencesJSON,
      dispatch,
      dockNow,
      undockNow,
      togglePresentation,
      onAvatarDragMove,
      onAvatarDragEnd,
      stepProjections,
      submitIntent,
      handlePortalDrop,
      interactiveRegions,
      getTelemetryCache: () => telemetryCache,
      getOfflineQueue: () => offlineQueue.slice(),
      recordDroppedAck: () => { perfStats.droppedAcks++; },
      getPerformanceMetrics: () => ({
        dockTransitions: perfStats.dockTransitions,
        undockTransitions: perfStats.undockTransitions,
        rendererSuspendedByNotch,
        droppedAcks: perfStats.droppedAcks,
        avgLayoutMs: perfStats.layoutSamplesMs.length ? perfStats.layoutSamplesMs.reduce((a, b) => a + b, 0) / perfStats.layoutSamplesMs.length : 0,
        avgRenderMs: perfStats.renderSamplesMs.length ? perfStats.renderSamplesMs.reduce((a, b) => a + b, 0) / perfStats.renderSamplesMs.length : 0
      }),
      tendrilsBlocked: () => (NS ? !NS.tendrilsAllowed(state) : false),
      isDocked: () => (NS ? NS.isDockedPresentation(state) : false),
      isDockingOrDocked: () => ['retracting', 'docking', 'docked'].includes(state.physical),
      isVisible: () => (NS ? NS.isNotchVisible(state) : false),
      isIdleFaded: () => idleFaded,
      triggerIdleFadeNow: () => {
        if (!shouldPauseIdleFade()) applyIdleFadeState(true);
        return idleFaded;
      },
      wakeFromIdleFade: (rearm = true) => { wakeFromIdleFade(rearm); return idleFaded; },
      getHitRevision: () => ({ epoch: state.dockEpoch, revision: state.geometryRevision + state.layoutRevision })
    };

    if (root.Axx?.app && document.body) {
      init();
    } else if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => init(), { once: true });
    } else {
      init();
    }

    return api;
  }

  return createCoordinator();
});
