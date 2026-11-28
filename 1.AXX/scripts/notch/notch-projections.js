/* Read-only ActivityProjectionAdapter over AXX's real business authorities.
 * Covers Timers, Commands/Approvals, WinRT/Local Media + Core Audio Peak, Voice Studio,
 * Screen Capture, Chat, Transfers, Agent Observatory, DevPulse, Resource Lens, and Recall/Threads.
 * Never invents progress percentages, handlers, permissions, or synthetic agents.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  const Axx = root.Axx || (root.Axx = {});
  Axx.notchProjections = api;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';

  function formatRemaining(ms) {
    const total = Math.max(0, Math.ceil((Number(ms) || 0) / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function formatSeconds(sec) {
    const total = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function collectTimerProjection(Axx, now) {
    const task = Axx?.app?.store?.data?.timer;
    if (!task || !['running', 'paused'].includes(task.status)) return null;
    const remainingMs = typeof Axx.remaining === 'function' ? Axx.remaining(task, now) : Math.max(0, (task.deadline || now) - now);
    const durationMs = Math.max(1, Number(task.durationMs) || 1);
    const fraction = Math.max(0, Math.min(1, 1 - remainingMs / durationMs));
    const customLabel = Axx.time19?.labelById?.get?.(task.id);
    const title = customLabel || (task.kind === 'focus' ? 'Concentración' : 'Temporizador');
    return {
      id: 'timer:' + task.id,
      sessionId: task.id,
      source: 'timer',
      sourceEpoch: 'local',
      revision: Number(task.revision) || 1,
      status: task.status === 'paused' ? 'pending' : 'running',
      kind: 'timer',
      supportedLevels: ['L1', 'L2', 'L3', 'L4'],
      title,
      subtitle: (task.status === 'paused' ? 'En pausa · ' : '') + formatRemaining(remainingMs),
      metric: formatRemaining(remainingMs),
      progress: { kind: 'determinate', fraction },
      privacy: 'public',
      updatedAt: Number(task.updatedAt) || now,
      actions: [
        { capabilityId: task.status === 'paused' ? 'timer.resume' : 'timer.pause', label: task.status === 'paused' ? 'Reanudar' : 'Pausar', available: true, requiresApproval: false },
        { capabilityId: 'timer.cancel', label: 'Cancelar', available: true, requiresApproval: false },
        { capabilityId: 'timer.open', label: 'Abrir Stage', available: true, requiresApproval: false }
      ]
    };
  }

  function collectApprovalProjection(Axx, now) {
    const op = Axx?.commandLibrary?.operation;
    if (!op || !['awaiting_approval', 'prepared', 'running'].includes(op.state)) return null;
    const awaiting = op.state === 'awaiting_approval';
    return {
      id: 'cmd:' + (op.operation_id || 'pending'),
      sessionId: op.conversation_id || op.operation_id,
      source: 'commands',
      sourceEpoch: 'backend',
      revision: awaiting ? 2 : 1,
      status: awaiting ? 'awaiting_user' : 'running',
      kind: 'approval',
      supportedLevels: ['L1', 'L2', 'L3', 'L4'],
      title: op.title || op.command_id || 'Operación pendiente',
      subtitle: awaiting ? 'Requiere aprobación explícita' : 'Ejecutando comando verificado',
      progress: awaiting ? undefined : { kind: 'indeterminate' },
      privacy: 'private',
      updatedAt: now,
      payloadSummary: op.inputs || null,
      actions: awaiting ? [
        { capabilityId: 'command.open_approval', label: 'Revisar', available: true, requiresApproval: true },
        { capabilityId: 'command.cancel', label: 'Cancelar', available: true, requiresApproval: false }
      ] : [
        { capabilityId: 'command.cancel', label: 'Cancelar', available: true, requiresApproval: false }
      ]
    };
  }

  function collectMediaProjection(Axx, now) {
    const nm = Axx?.nativeMusic;
    const hub = Axx?.media16;
    const localMusic = Axx?.actions?.music;
    if (nm && hub?.source === 'system') {
      const target = nm.target?.();
      if (!target) return null;
      const dur = Number(target.duration) || 0;
      const pos = Number(target.time) || 0;
      const hasTimeline = dur > 0 && Number.isFinite(pos) && pos >= 0;
      const peak = Number(nm.snapshot?.peak) || 0;
      const sessions = Array.isArray(nm.snapshot?.sessions) ? nm.snapshot.sessions : [];
      return {
        id: 'media:' + (target.id || 'system'),
        sessionId: target.id || 'system-media',
        source: 'media',
        sourceEpoch: 'winrt',
        revision: Math.floor((nm.snapshot?.updatedAt || now) / 250),
        status: target.playing ? 'running' : 'pending',
        kind: 'media',
        supportedLevels: ['L1', 'L2', 'L3', 'L4'],
        title: target.title || 'Reproducción del sistema',
        subtitle: (target.subtitle ? target.subtitle + ' · ' : '') + (target.app || 'Windows'),
        metric: hasTimeline ? `${formatSeconds(pos)} / ${formatSeconds(dur)}` : (target.playing ? 'En vivo' : 'Pausa'),
        progress: hasTimeline ? { kind: 'determinate', fraction: Math.max(0, Math.min(1, pos / dur)) } : undefined,
        mediaMeta: {
          playing: Boolean(target.playing),
          canSeek: Boolean(target.canSeek),
          time: pos,
          duration: dur,
          peak,
          audioAvailable: Boolean(nm.snapshot?.audioAvailable),
          sessions: sessions.map(s => ({ id: s.id, title: s.title || s.app || s.id, app: s.app || '', playing: Boolean(s.playing) })),
          selectedId: target.id
        },
        privacy: 'private',
        updatedAt: nm.snapshot?.updatedAt || now,
        actions: [
          { capabilityId: 'media.previous', label: 'Anterior', available: Boolean(target.canPrevious), requiresApproval: false, disabledReason: target.canPrevious ? undefined : 'No compatible' },
          { capabilityId: target.playing ? 'media.pause' : 'media.play', label: target.playing ? 'Pausar' : 'Reproducir', available: target.playing ? Boolean(target.canPause) : Boolean(target.canPlay), requiresApproval: false },
          { capabilityId: 'media.next', label: 'Siguiente', available: Boolean(target.canNext), requiresApproval: false, disabledReason: target.canNext ? undefined : 'No compatible' }
        ]
      };
    }
    if (localMusic && localMusic.tracks?.length > 0 && !localMusic.audio?.paused) {
      const dur = Number(localMusic.audio.duration) || 0;
      const cur = Number(localMusic.audio.currentTime) || 0;
      const hasDur = Number.isFinite(dur) && dur > 0;
      return {
        id: 'media:local-' + localMusic.index,
        sessionId: 'local-music',
        source: 'media-local',
        sourceEpoch: 'local',
        revision: Math.floor(now / 500),
        status: 'running',
        kind: 'media',
        supportedLevels: ['L1', 'L2', 'L3', 'L4'],
        title: localMusic.name || 'Audio local',
        subtitle: 'Música local de AXX',
        metric: hasDur ? `${formatSeconds(cur)} / ${formatSeconds(dur)}` : 'Local',
        progress: hasDur ? { kind: 'determinate', fraction: Math.max(0, Math.min(1, cur / dur)) } : { kind: 'indeterminate' },
        mediaMeta: { playing: true, canSeek: false, time: cur, duration: dur, peak: 0, audioAvailable: true, sessions: [], selectedId: 'local' },
        privacy: 'public',
        updatedAt: now,
        actions: [
          { capabilityId: 'media.previous', label: 'Anterior', available: true, requiresApproval: false },
          { capabilityId: 'media.pause', label: 'Pausar', available: true, requiresApproval: false },
          { capabilityId: 'media.next', label: 'Siguiente', available: Boolean(localMusic.canNext), requiresApproval: false }
        ]
      };
    }
    return null;
  }

  function collectVoiceProjection(Axx, now) {
    const activeCapture = Axx?.nativeVoice?.activeCapture;
    const reader = Axx?.symbiosis?.reader;
    const inkReview = typeof document !== 'undefined' ? document.getElementById('ink-review') : null;
    const inkVisible = Boolean(inkReview && !inkReview.hidden);
    const listening = activeCapture && ['starting', 'listening', 'stopping'].includes(activeCapture.state);
    const reading = reader && ['starting', 'speaking', 'paused'].includes(reader.state);
    if (!listening && !reading && !inkVisible) return null;
    return {
      id: listening ? 'voice:capture' : reading ? 'voice:reader' : 'voice:ink',
      sessionId: listening ? 'voice-capture' : reading ? 'voice-reader' : 'voice-ink',
      source: 'voice',
      sourceEpoch: 'local',
      revision: Math.floor(now / 250),
      status: listening ? (activeCapture.state === 'listening' ? 'running' : 'pending') : reading ? (reader.state === 'paused' ? 'pending' : 'running') : 'awaiting_user',
      kind: 'voice',
      supportedLevels: ['L1', 'L2', 'L3', 'L4'],
      title: listening ? 'Micrófono / Dictado activo' : reading ? (reader.title || 'Lectura en voz alta') : 'Texto dictado listo',
      subtitle: listening ? 'Captura de audio real' : reading ? (reader.state === 'paused' ? 'Lectura en pausa' : `Fragmento ${(reader.index || 0) + 1}/${reader.chunks?.length || 1}`) : 'Revisa o edita antes de enviar',
      progress: listening ? { kind: 'indeterminate' } : reading && reader.chunks?.length ? { kind: 'determinate', fraction: (reader.index + 1) / reader.chunks.length } : undefined,
      privacy: 'private',
      updatedAt: now,
      actions: [
        ...(listening || reading ? [{ capabilityId: 'voice.stop', label: 'Detener', available: true, requiresApproval: false }] : []),
        { capabilityId: 'voice.open', label: 'Abrir Estudio', available: true, requiresApproval: false }
      ]
    };
  }

  function collectAgentProjections(Axx, now) {
    const items = [];
    const ev = Axx?.evolution3?.controllers;
    if (ev?.agentTimeline?.eventsByConversation) {
      for (const [cid, events] of ev.agentTimeline.eventsByConversation.entries()) {
        if (!events || !events.length) continue;
        const last = events[events.length - 1];
        const terminal = ['completed', 'failed', 'cancelled'].includes(last.status);
        items.push({
          id: 'agent:' + cid,
          sessionId: cid,
          source: 'evolution3-agent',
          sourceEpoch: 'agent-sse',
          revision: Number(last.seq) || events.length,
          status: last.status || (terminal ? 'completed' : 'running'),
          kind: 'agent',
          supportedLevels: ['L1', 'L2', 'L3', 'L4'],
          title: last.agent_name || last.title || `Agente ${cid.slice(0, 8)}`,
          subtitle: last.tool || last.phase || `${events.length} evento(s) verificados`,
          metric: `seq #${last.seq}`,
          agentEvents: events.slice(-5),
          privacy: 'private',
          updatedAt: now,
          actions: [
            { capabilityId: 'agents.open_stage', label: 'Inspeccionar en Stage', available: true, requiresApproval: false }
          ]
        });
      }
    }
    if (ev?.workApprovals?.cards) {
      for (const [opId, card] of ev.workApprovals.cards.entries()) {
        if (card.status !== 'pending') continue;
        items.push({
          id: 'agent-approval:' + opId,
          sessionId: card.conversation_id || opId,
          source: 'work-approvals',
          sourceEpoch: 'agent',
          revision: 1,
          status: 'awaiting_user',
          kind: 'approval',
          supportedLevels: ['L1', 'L2', 'L3', 'L4'],
          title: card.title || card.action || 'Aprobación de agente',
          subtitle: card.reason || 'Requiere revisión humana',
          privacy: 'private',
          updatedAt: now,
          actions: [
            { capabilityId: 'agents.approve', label: 'Aprobar', available: true, requiresApproval: true },
            { capabilityId: 'agents.deny', label: 'Denegar', available: true, requiresApproval: false }
          ]
        });
      }
    }
    const git = ev?.gitPanel;
    if (git && (git.worktrees?.length || git.dirtyFiles?.length)) {
      const activeWt = git.worktrees.filter(w => w.status === 'active').length;
      if (activeWt > 0 || git.dirtyFiles.length > 0) {
        items.push({
          id: 'devpulse:git',
          sessionId: 'devpulse',
          source: 'git-panel',
          sourceEpoch: 'local',
          revision: activeWt + git.dirtyFiles.length,
          status: 'running',
          kind: 'devpulse',
          supportedLevels: ['L2', 'L3', 'L4'],
          title: 'DevPulse · Worktrees',
          subtitle: `${activeWt} activo(s) · ${git.dirtyFiles.length} archivo(s) modificados`,
          privacy: 'private',
          updatedAt: now,
          actions: [{ capabilityId: 'agents.open_stage', label: 'Abrir Code Studio', available: true, requiresApproval: false }]
        });
      }
    }
    return items;
  }

  function collectChatProjection(Axx, now) {
    const c = Axx?.companion;
    if (!c) return null;
    const hasPending = Boolean(c.pending || c.connecting);
    const draft = ((typeof document !== 'undefined' ? document.getElementById?.('chat-input')?.value : '') || c.data?.draft || '').trim();
    if (!hasPending && !draft) return null;
    const activeChat = Axx.chatWorkspace?.active;
    return {
      id: 'chat:' + (activeChat?.id || 'main'),
      sessionId: activeChat?.id || 'main',
      source: 'chat',
      sourceEpoch: 'local',
      revision: Math.floor(now / 500),
      status: hasPending ? 'running' : 'pending',
      kind: 'chat',
      supportedLevels: ['L1', 'L2', 'L3', 'L4', 'L5'],
      title: activeChat?.title || 'Conversación AXX',
      subtitle: hasPending ? 'Esperando respuesta del modelo…' : 'Borrador conservado',
      progress: hasPending ? { kind: 'indeterminate' } : undefined,
      privacy: 'private',
      updatedAt: now,
      actions: [
        ...(hasPending ? [{ capabilityId: 'chat.cancel', label: 'Detener', available: true, requiresApproval: false }] : []),
        { capabilityId: 'chat.open', label: 'Abrir Chat', available: true, requiresApproval: false }
      ]
    };
  }

  function collectScreenProjection(Axx, now) {
    const s = Axx?.actions?.screen;
    if (!s || !['countdown', 'running', 'paused', 'stopping'].includes(s.state)) return null;
    return {
      id: 'screen:capture',
      sessionId: 'screen-capture',
      source: 'screen',
      sourceEpoch: 'local',
      revision: Math.floor(now / 500),
      status: s.state === 'paused' ? 'pending' : 'running',
      kind: 'screen',
      supportedLevels: ['L1', 'L2', 'L3'],
      title: 'Grabación de pantalla',
      subtitle: s.state === 'paused' ? 'Captura en pausa' : 'Grabando',
      progress: { kind: 'indeterminate' },
      privacy: 'private',
      updatedAt: now,
      actions: [
        { capabilityId: 'screen.toggle', label: s.state === 'paused' ? 'Continuar' : 'Pausar', available: s.state === 'running' || s.state === 'paused', requiresApproval: false },
        { capabilityId: 'screen.stop', label: 'Finalizar', available: true, requiresApproval: false }
      ]
    };
  }

  function collectTransferProjection(Axx, now) {
    const tf = Axx?.transfer;
    const active = (tf?.transfers || tf?.state?.transfers || []).filter(t => ['preparing', 'transferring', 'receiving', 'paused', 'verifying'].includes(t.state));
    if (!active.length) return null;
    const t = active[0];
    const total = Number(t.size ?? t.bytes ?? 0);
    const confirmed = Number(t.confirmed_bytes ?? 0);
    return {
      id: 'transfer:' + t.transfer_id,
      sessionId: t.transfer_id,
      source: 'transfer',
      sourceEpoch: 'backend',
      revision: Number(t.updated_at) || Math.floor(now / 500),
      status: t.state === 'paused' ? 'pending' : 'running',
      kind: 'transfer',
      supportedLevels: ['L1', 'L2', 'L3', 'L4'],
      title: t.name || 'Transferencia móvil',
      subtitle: active.length > 1 ? `${active.length} transferencias activas` : (t.direction === 'to_pc' ? 'Teléfono → PC' : 'PC → Teléfono'),
      progress: total > 0 ? { kind: 'determinate', fraction: Math.max(0, Math.min(1, confirmed / total)) } : { kind: 'indeterminate' },
      privacy: 'private',
      updatedAt: now,
      actions: [
        { capabilityId: 'transfer.open', label: 'Ver cola', available: true, requiresApproval: false }
      ]
    };
  }

  function collectRecallData(Axx) {
    const threads = [];
    const chats = Axx?.chatWorkspace?.chats || Axx?.chatWorkspace?.items || [];
    if (Array.isArray(chats)) {
      for (const ch of chats.slice(0, 6)) {
        threads.push({
          id: ch.id,
          title: ch.title || 'Conversación',
          updatedAt: ch.updated || ch.draft_at || 0,
          active: Axx?.chatWorkspace?.active?.id === ch.id
        });
      }
    }
    const recipes = Axx?.desktop?.recipesCache || [];
    return { threads, recipes };
  }

  function collectAllProjections(Axx, now = Date.now()) {
    const items = [
      collectApprovalProjection(Axx, now),
      ...collectAgentProjections(Axx, now),
      collectTimerProjection(Axx, now),
      collectVoiceProjection(Axx, now),
      collectScreenProjection(Axx, now),
      collectChatProjection(Axx, now),
      collectMediaProjection(Axx, now),
      collectTransferProjection(Axx, now)
    ].filter(Boolean);

    return {
      projections: items,
      lastReceipt: Axx?.commandLibrary?.lastOperation || Axx?.desktop?.lastOperation || null,
      telemetry: Axx?.notch?.getTelemetryCache?.() || null,
      recall: collectRecallData(Axx),
      backendReady: Boolean(Axx?.desktop?.ready),
      modelConnected: Boolean(Axx?.companion?.brain?.connected)
    };
  }

  return {
    formatRemaining,
    formatSeconds,
    collectTimerProjection,
    collectApprovalProjection,
    collectMediaProjection,
    collectVoiceProjection,
    collectAgentProjections,
    collectChatProjection,
    collectScreenProjection,
    collectTransferProjection,
    collectRecallData,
    collectAllProjections
  };
});
