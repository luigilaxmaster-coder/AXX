/**
 * Axx Mobile · Controlador de Escritorio Remoto
 * Permite seleccionar monitores y ventanas, alternar entre modos Mirar/Controlar/Marcar,
 * controlar el cursor mediante trackpad relativo o clic directo, enviar pulsaciones
 * de teclado Windows con modificadores, y arbitrar el control con Axx.
 */

(function (global) {
  'use strict';

  class DesktopController {
    constructor() {
      this.mode = 'look'; // 'look' | 'control' | 'mark'
      this.activeMonitor = 1;
      this.activeWindow = null;
      this.zoomLevel = 1.0;
      this.panOffset = { x: 0, y: 0 };
      this.modifiers = {
        ctrl: false,
        alt: false,
        shift: false,
        win: false
      };
      this.monitors = [
        { id: 1, name: 'Monitor 1 (Principal)', resolution: '1920×1080' },
        { id: 2, name: 'Monitor 2 (Cava 4K)', resolution: '2560×1440' }
      ];
      this.windows = [
        { id: 'win-1', title: 'Blender 4.2 · [Cava_Vino_Final.blend]', process: 'blender.exe', monitor: 1 },
        { id: 'win-2', title: 'Axx Studio v20 - Núcleo Activo', process: 'Axx.exe', monitor: 1 },
        { id: 'win-3', title: 'Explorador · C:\\Proyectos\\Cava', process: 'explorer.exe', monitor: 2 },
        { id: 'win-4', title: 'Plano_Arquitectura_Cava.pdf', process: 'acrobat.exe', monitor: 2 }
      ];

      this.listeners = new Set();
    }

    subscribe(fn) {
      this.listeners.add(fn);
      return () => this.listeners.delete(fn);
    }

    emit(event, data) {
      for (const fn of this.listeners) {
        try {
          fn(event, data);
        } catch (e) {
          console.error('Error en listener de DesktopController', e);
        }
      }
    }

    setMode(newMode) {
      if (this.mode === newMode) return;
      this.mode = newMode;
      this.emit('mode-changed', { mode: newMode });

      if (newMode === 'mark') {
        // En modo Marcar, congelar evidencia actual y abrir Magic Pen
        this.emit('trigger-magic-pen', {
          source: this.activeWindow ? this.activeWindow.title : `Monitor ${this.activeMonitor}`,
          timestamp: Date.now()
        });
      }
    }

    selectMonitor(monitorId) {
      this.activeMonitor = monitorId;
      this.zoomLevel = 1.0;
      this.panOffset = { x: 0, y: 0 };
      this.emit('viewport-updated', { monitorId, zoom: 1.0 });
    }

    selectWindow(windowId) {
      const win = this.windows.find(w => w.id === windowId);
      if (win) {
        this.activeWindow = win;
        this.activeMonitor = win.monitor;
        this.emit('window-focused', win);
      }
    }

    toggleModifier(key) {
      if (this.modifiers[key] !== undefined) {
        this.modifiers[key] = !this.modifiers[key];
        this.emit('modifiers-changed', this.modifiers);
      }
    }

    // Envío de atajos de teclado Windows
    sendKey(keyName) {
      const activeMods = Object.entries(this.modifiers)
        .filter(([_, v]) => v)
        .map(([k]) => k.toUpperCase());

      const combo = [...activeMods, keyName].join('+');
      this.emit('key-dispatched', { combo });

      // Limpiar modificadores si se pulsó una tecla normal
      if (!['ctrl', 'alt', 'shift', 'win'].includes(keyName.toLowerCase())) {
        this.modifiers.ctrl = false;
        this.modifiers.alt = false;
        this.modifiers.shift = false;
        this.modifiers.win = false;
        this.emit('modifiers-changed', this.modifiers);
      }
    }

    // Simulación de interacción con trackpad relativo
    sendMouseDelta(dx, dy) {
      if (this.mode !== 'control') return;
      this.emit('cursor-moved', { dx, dy });
    }

    sendMouseClick(button = 'left') {
      if (this.mode !== 'control') return;
      this.emit('mouse-clicked', { button });
    }

    // Zoom interactivo
    zoomIn() {
      this.zoomLevel = Math.min(3.0, this.zoomLevel + 0.25);
      this.emit('zoom-changed', { zoom: this.zoomLevel });
    }

    zoomOut() {
      this.zoomLevel = Math.max(0.75, this.zoomLevel - 0.25);
      this.emit('zoom-changed', { zoom: this.zoomLevel });
    }

    resetZoom() {
      this.zoomLevel = 1.0;
      this.panOffset = { x: 0, y: 0 };
      this.emit('zoom-changed', { zoom: 1.0 });
    }
  }

  global.AxxDesktop = new DesktopController();
})(typeof window !== 'undefined' ? window : this);
