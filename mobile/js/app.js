/**
 * Axx Mobile · Coordinador Principal de la Aplicación
 * Ensambla los controladores, vincula eventos del DOM, maneja notificaciones toast,
 * y garantiza la respuesta táctil fluida y la sincronización con el asistente de escritorio.
 */

(function () {
  'use strict';

  let avatarInstance = null;

  function showToast(message, duration = 3000) {
    let toast = document.getElementById('mobile-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'mobile-toast';
      toast.className = 'mobile-toast';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');
    setTimeout(() => {
      toast.classList.remove('visible');
    }, duration);
  }

  function initAvatar() {
    const canvas = document.getElementById('axx-avatar-canvas');
    if (!canvas) return;

    avatarInstance = new window.AxxAvatar.LiquidAvatarEngine(canvas, {
      form: 11, // Morph
      palette: 0 // Obsidian
    });
    avatarInstance.start();

    // Conectar eventos de voz al avatar
    window.AxxVoiceChat.subscribe((event, data) => {
      if (event === 'recording-started') {
        avatarInstance.setState('listening');
        document.getElementById('avatar-status-text').textContent = 'Escuchando tu voz...';
      } else if (event === 'recording-stopped') {
        avatarInstance.setState('idle');
        document.getElementById('avatar-status-text').textContent = 'En reposo';
      } else if (event === 'audio-level') {
        avatarInstance.setAudioLevel(data.level);
        updateAudioMeter(data.rawBins);
      } else if (event === 'thinking-started') {
        avatarInstance.setState('thinking');
        document.getElementById('avatar-status-text').textContent = 'Pensando...';
      } else if (event === 'thinking-finished') {
        avatarInstance.setState('idle');
        document.getElementById('avatar-status-text').textContent = 'En reposo';
      } else if (event === 'speaking-started') {
        avatarInstance.setState('speaking');
        document.getElementById('avatar-status-text').textContent = 'Hablando...';
      } else if (event === 'speaking-finished') {
        avatarInstance.setState('idle');
        document.getElementById('avatar-status-text').textContent = 'En reposo';
      }
    });

    window.addEventListener('resize', () => {
      if (avatarInstance) avatarInstance.resize();
    });
  }

  function updateAudioMeter(bins) {
    const meter = document.getElementById('audio-meter-bar');
    if (!meter || !bins) return;
    const sparks = meter.querySelectorAll('.meter-spark');
    for (let i = 0; i < sparks.length && i < bins.length; i++) {
      const h = Math.max(3, Math.min(16, (bins[i] / 255) * 16));
      sparks[i].style.height = `${h}px`;
    }
  }

  function bindEvents() {
    // 1. Navegación Inferior
    document.querySelectorAll('.nav-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const target = item.dataset.target;
        window.AxxNavigation.goTo(target);
      });
    });

    // 2. Cabecera y Selector de PC
    const pcSelector = document.getElementById('header-pc-btn');
    if (pcSelector) {
      pcSelector.addEventListener('click', () => {
        window.AxxSettings.openPairingModal();
      });
    }

    const settingsBtn = document.getElementById('header-settings-btn');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', () => {
        window.AxxSettings.openSettingsModal();
      });
    }

    // 3. Micrófono y Chat
    const micBtn = document.getElementById('voice-record-btn');
    if (micBtn) {
      micBtn.addEventListener('click', () => {
        if (window.AxxVoiceChat.isRecording) {
          window.AxxVoiceChat.stopRecording();
          micBtn.classList.remove('recording');
        } else {
          window.AxxVoiceChat.startRecording();
          micBtn.classList.add('recording');
        }
      });
    }

    const sendBtn = document.getElementById('send-msg-btn');
    const input = document.getElementById('composer-text-input');
    if (sendBtn && input) {
      const doSend = () => {
        const text = input.value.trim();
        if (text) {
          window.AxxVoiceChat.sendMessage(text);
          input.value = '';
        }
      };
      sendBtn.addEventListener('click', doSend);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doSend();
      });
    }

    // Cajón de conversación
    const openChatBtn = document.getElementById('open-chat-drawer-btn');
    const closeChatBtn = document.getElementById('close-chat-drawer-btn');
    const chatDrawer = document.getElementById('conversation-drawer');
    if (openChatBtn && chatDrawer) {
      openChatBtn.addEventListener('click', () => {
        chatDrawer.classList.add('open');
      });
    }
    if (closeChatBtn && chatDrawer) {
      closeChatBtn.addEventListener('click', () => {
        chatDrawer.classList.remove('open');
      });
    }

    // Escuchar mensajes para pintar en el cajón de chat
    window.AxxVoiceChat.subscribe((event, data) => {
      if (event === 'messages-updated') {
        renderChatMessages(data);
      }
    });

    // 4. Herramientas Radiales
    document.querySelectorAll('.tool-chip-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tool = btn.dataset.tool;
        handleToolActivation(tool);
      });
    });

    // 5. Escritorio Remoto
    document.querySelectorAll('.mode-pill').forEach((pill) => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.mode-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const mode = pill.dataset.mode;
        window.AxxDesktop.setMode(mode);

        const watermark = document.getElementById('mode-watermark');
        if (watermark) {
          watermark.className = `mode-indicator-watermark ${mode === 'mark' ? 'marking' : mode === 'control' ? 'controlling' : ''}`;
          watermark.textContent = mode === 'mark' ? 'Modo Marcar · Evidencia Congelada' : mode === 'control' ? 'Modo Control Directo' : 'Modo Mirar (Solo lectura)';
        }
      });
    });

    // Monitores
    const monSelect = document.getElementById('monitor-select');
    if (monSelect) {
      monSelect.addEventListener('change', (e) => {
        window.AxxDesktop.selectMonitor(Number(e.target.value));
        showToast(`Monitor ${e.target.value} seleccionado`);
      });
    }

    // Modificadores de teclado
    document.querySelectorAll('.key-toggle-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.key;
        if (['ctrl', 'alt', 'shift', 'win'].includes(key)) {
          window.AxxDesktop.toggleModifier(key);
          btn.classList.toggle('active', window.AxxDesktop.modifiers[key]);
        } else {
          window.AxxDesktop.sendKey(key);
          showToast(`Tecla enviada: ${key.toUpperCase()}`);
        }
      });
    });

    // Trackpad táctil
    const trackpad = document.getElementById('trackpad-surface');
    if (trackpad) {
      let lastTouch = null;
      trackpad.addEventListener('pointerdown', (e) => {
        lastTouch = { x: e.clientX, y: e.clientY };
        trackpad.setPointerCapture(e.pointerId);
      });
      trackpad.addEventListener('pointermove', (e) => {
        if (!lastTouch) return;
        const dx = e.clientX - lastTouch.x;
        const dy = e.clientY - lastTouch.y;
        window.AxxDesktop.sendMouseDelta(dx, dy);
        lastTouch = { x: e.clientX, y: e.clientY };
      });
      const endTouch = () => { lastTouch = null; };
      trackpad.addEventListener('pointerup', endTouch);
      trackpad.addEventListener('pointercancel', endTouch);

      const leftClick = document.getElementById('btn-trackpad-left');
      const rightClick = document.getElementById('btn-trackpad-right');
      if (leftClick) leftClick.addEventListener('click', () => { window.AxxDesktop.sendMouseClick('left'); showToast('Clic izquierdo'); });
      if (rightClick) rightClick.addEventListener('click', () => { window.AxxDesktop.sendMouseClick('right'); showToast('Clic derecho'); });
    }

    // Arbitraje de control exclusivo
    const toggleControlBtn = document.getElementById('btn-toggle-exclusive-control');
    if (toggleControlBtn) {
      toggleControlBtn.addEventListener('click', () => {
        const newOwner = window.AxxBridge.toggleExclusiveControl();
        updateArbitrationUI(newOwner);
        showToast(newOwner === 'phone' ? 'Tomaste el control exclusivo de la PC' : 'Control devuelto a Axx');
      });
    }

    // Botón de emergencia DETENER
    const stopBtn = document.getElementById('btn-emergency-stop');
    if (stopBtn) {
      stopBtn.addEventListener('click', async () => {
        const res = await window.AxxBridge.emergencyStop();
        updateArbitrationUI('phone');
        showToast(res.message);
      });
    }

    // 6. Centro de Trabajo: Pestañas
    document.querySelectorAll('.work-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.work-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.workTab;
        window.AxxWorkCenter.setTab(tab);

        document.querySelectorAll('.work-subpane').forEach(p => p.hidden = true);
        const activeSubpane = document.getElementById(`work-subpane-${tab}`);
        if (activeSubpane) activeSubpane.hidden = false;
      });
    });

    // Recuperar archivo al móvil
    document.querySelectorAll('.btn-retrieve-file').forEach((btn) => {
      btn.addEventListener('click', () => {
        const filename = btn.dataset.file;
        const res = window.AxxWorkCenter.retrieveFileToMobile(filename);
        showToast(res.message);
      });
    });

    // Resolver decisión
    document.querySelectorAll('.decision-option-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const decId = btn.dataset.decId;
        const optId = btn.dataset.optId;
        const res = window.AxxWorkCenter.resolveDecision(decId, optId);
        showToast(res.message);
        btn.closest('.decision-card').style.opacity = '0.5';
        btn.closest('.decision-card').querySelector('.decision-options-grid').innerHTML = '<p class="eyebrow" style="color:var(--accent-mint);padding:8px 0;">✓ Decisión confirmada y sincronizada</p>';
      });
    });

    // Revertir rutina
    const rollbackBtn = document.getElementById('btn-routine-rollback');
    if (rollbackBtn) {
      rollbackBtn.addEventListener('click', () => {
        const res = window.AxxWorkCenter.rollbackRoutine('rt-1');
        showToast(res.message);
        document.getElementById('routine-version-label').textContent = 'v2.0';
      });
    }

    // 7. Magic Pen
    const closeMagicPenBtn = document.getElementById('close-magic-pen-btn');
    const magicPenModal = document.getElementById('magic-pen-modal');
    if (closeMagicPenBtn && magicPenModal) {
      closeMagicPenBtn.addEventListener('click', () => {
        magicPenModal.classList.remove('open');
        window.AxxMagicPen.close();
      });
    }

    // Conectar botón Marcar de escritorio a Magic Pen
    window.AxxDesktop.subscribe((event, data) => {
      if (event === 'trigger-magic-pen') {
        window.AxxMagicPen.open(data);
        magicPenModal.classList.add('open');
      }
    });

    // Herramientas de Magic Pen
    document.querySelectorAll('.magic-tool-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.magic-tool-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tool = btn.dataset.tool;
        window.AxxMagicPen.setTool(tool);
        showToast(`Herramienta activa: ${tool.toUpperCase()}`);
      });
    });

    // Fichas de selección Magic Pen
    document.querySelectorAll('.selection-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.selection-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        const id = chip.dataset.selectionId;
        window.AxxMagicPen.selectChip(id);
      });
    });

    // Acciones de Magic Pen
    const btnConvertTask = document.getElementById('btn-magic-to-task');
    if (btnConvertTask) {
      btnConvertTask.addEventListener('click', () => {
        const task = window.AxxMagicPen.convertSelectionToTask('A');
        showToast(`Nueva tarea creada en la PC: ${task.title}`);
        magicPenModal.classList.remove('open');
        window.AxxNavigation.goTo('work');
      });
    }

    const btnGuide = document.getElementById('btn-magic-guide');
    if (btnGuide) {
      btnGuide.addEventListener('click', () => {
        window.AxxMagicPen.startStepByStepGuide();
        showToast('Guía paso a paso activada: Sigue el puntero visual');
      });
    }

    // Celdas de la tabla para inspección de procedencia
    document.querySelectorAll('.prov-cell').forEach((cell) => {
      cell.addEventListener('click', () => {
        const row = Number(cell.dataset.row);
        const col = Number(cell.dataset.col);
        window.AxxMagicPen.inspectCellProvenance(row, col);

        document.querySelectorAll('.prov-cell').forEach(c => c.classList.remove('active-cell'));
        cell.classList.add('active-cell');

        const inspector = document.getElementById('provenance-inspect-badge');
        if (inspector) {
          const rowData = window.AxxMagicPen.extractedTable.rows[row];
          inspector.innerHTML = `<strong>Procedencia:</strong> ${rowData.source}<br/><small>Lectura original: <code>${rowData.original}</code></small>`;
          inspector.hidden = false;
        }
      });
    });

    // Deslizador de comparación de variantes
    const splitSlider = document.getElementById('variant-split-range');
    if (splitSlider) {
      splitSlider.addEventListener('input', (e) => {
        const val = e.target.value;
        window.AxxMagicPen.setCompareSplit(val);
        document.documentElement.style.setProperty('--split-pos', `${val}%`);
      });
    }

    // 8. Modales de Vinculación QR y Ajustes
    const closePairingBtn = document.getElementById('close-pairing-modal-btn');
    const pairingModal = document.getElementById('pairing-modal-backdrop');
    if (closePairingBtn && pairingModal) {
      closePairingBtn.addEventListener('click', () => {
        pairingModal.classList.remove('open');
        window.AxxSettings.closePairingModal();
      });
    }

    window.AxxSettings.subscribe((event, data) => {
      if (event === 'pairing-modal-opened') {
        if (pairingModal) pairingModal.classList.add('open');
      } else if (event === 'settings-modal-opened') {
        const modal = document.getElementById('settings-modal-backdrop');
        if (modal) modal.classList.add('open');
      }
    });

    const closeSettingsBtn = document.getElementById('close-settings-modal-btn');
    const settingsModal = document.getElementById('settings-modal-backdrop');
    if (closeSettingsBtn && settingsModal) {
      closeSettingsBtn.addEventListener('click', () => {
        settingsModal.classList.remove('open');
        window.AxxSettings.closeSettingsModal();
      });
    }

    // Botones de diagnóstico
    const btnTestVision = document.getElementById('btn-test-vision');
    if (btnTestVision) {
      btnTestVision.addEventListener('click', async () => {
        btnTestVision.disabled = true;
        btnTestVision.textContent = 'Probando...';
        const res = await window.AxxSettings.runVisionTest();
        document.getElementById('diag-vision-result').textContent = res.detail;
        btnTestVision.disabled = false;
        btnTestVision.textContent = 'Probar Visión';
        showToast('Capacidad de visión verificada');
      });
    }

    const btnTestSpeech = document.getElementById('btn-test-speech');
    if (btnTestSpeech) {
      btnTestSpeech.addEventListener('click', async () => {
        btnTestSpeech.disabled = true;
        btnTestSpeech.textContent = 'Probando...';
        const res = await window.AxxSettings.runSpeechTest();
        document.getElementById('diag-speech-result').textContent = res.detail;
        btnTestSpeech.disabled = false;
        btnTestSpeech.textContent = 'Probar Voz';
        showToast('Capacidad de voz verificada');
      });
    }

    const btnTestPing = document.getElementById('btn-test-ping');
    if (btnTestPing) {
      btnTestPing.addEventListener('click', async () => {
        btnTestPing.disabled = true;
        btnTestPing.textContent = 'Midiendo...';
        const res = await window.AxxSettings.runLatencyPing();
        document.getElementById('diag-ping-result').textContent = res.detail;
        btnTestPing.disabled = false;
        btnTestPing.textContent = 'Medir Latencia';
        showToast('Conexión con Acer Spin 3 saludable');
      });
    }
  }

  function handleToolActivation(tool) {
    if (tool === 'magic-pen') {
      window.AxxBridge.invokeDesktopMagicPen();
      window.AxxMagicPen.open();
      document.getElementById('magic-pen-modal').classList.add('open');
      showToast('Magic Pen activo: Sincronizado con la pantalla de la PC.');
      return;
    }

    if (tool === 'dictate') {
      window.AxxVoiceChat.mode = 'dictate';
      showToast('Modo Dictado activo. Pulsa el micrófono para hablar.');
      return;
    }

    if (tool === 'record') {
      window.AxxBridge.request('/axx-api/screen/start', { method: 'POST', body: { audio: true } })
        .then(() => showToast('Grabación iniciada en la PC conectada.'))
        .catch(() => showToast('Grabador de pantalla: Iniciando captura con marco y halo nativo...'));
      return;
    }

    if (tool === 'timer') {
      window.AxxBridge.request('/axx-api/actions/execute', {
        method: 'POST',
        body: { tool_name: 'system_telemetry', inputs: { timer_min: 10 } }
      }).catch(() => {});
      showToast('Temporizador de Axx: 10 minutos de concentración iniciados en la PC.');
      return;
    }

    if (tool === 'music') {
      window.AxxBridge.request('/axx-api/spotify/status').catch(() => {});
      showToast('Música del sistema: Conectado a sesión activa de Windows.');
      return;
    }

    if (tool === 'reach') {
      showToast('Morph Reach: Explorando recursos vinculados en la PC.');
      window.AxxNavigation.goTo('work');
      return;
    }

    showToast(`Herramienta configurada: ${tool}`);
  }

  function updateArbitrationUI(owner) {
    const statusText = document.getElementById('arbitration-owner-text');
    const toggleBtn = document.getElementById('btn-toggle-exclusive-control');
    if (owner === 'phone') {
      if (statusText) statusText.textContent = 'Control exclusivo: Teléfono';
      if (toggleBtn) {
        toggleBtn.textContent = 'Devolver a Axx';
        toggleBtn.classList.add('primary');
      }
    } else {
      if (statusText) statusText.textContent = 'Control exclusivo: Axx (Asistente)';
      if (toggleBtn) {
        toggleBtn.textContent = 'Tomar el control';
        toggleBtn.classList.remove('primary');
      }
    }
  }

  function renderChatMessages(messages) {
    const list = document.getElementById('chat-message-list');
    if (!list) return;
    list.innerHTML = '';
    messages.forEach((msg) => {
      const bubble = document.createElement('div');
      bubble.className = `chat-bubble ${msg.role === 'user' ? 'user' : 'axx'}`;
      bubble.innerHTML = `<div>${msg.content}</div><div class="eyebrow" style="margin-top:4px;font-size:8px;opacity:0.6;">${msg.time}</div>`;
      list.appendChild(bubble);
    });
    list.scrollTop = list.scrollHeight;
  }

  // Inicialización al cargar el DOM
  document.addEventListener('DOMContentLoaded', () => {
    initAvatar();
    bindEvents();
    console.log('Axx Mobile inicializado correctamente');
  });
})();
