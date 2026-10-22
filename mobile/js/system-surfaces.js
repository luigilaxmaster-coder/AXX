/**
 * Axx Mobile · Superficies del Sistema y Widgets
 * Simula y renderiza las vistas para Dynamic Island, Live Activities (iOS)
 * y widgets de pantalla de bloqueo/inicio de Android.
 */

(function (global) {
  'use strict';

  class SystemSurfacesController {
    constructor() {
      this.isDynamicIslandVisible = false;
      this.isLiveActivityExpanded = false;
      this.activeWidget = {
        title: 'Exportando Cava_Vino_Final.png',
        progress: 85,
        pc: 'Acer Spin 3',
        remainingTime: '00:18'
      };
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
          console.error('Error en listener de SystemSurfaces', e);
        }
      }
    }

    toggleDynamicIsland() {
      this.isDynamicIslandVisible = !this.isDynamicIslandVisible;
      this.emit('island-toggle', { visible: this.isDynamicIslandVisible });
    }

    expandLiveActivity() {
      this.isLiveActivityExpanded = !this.isLiveActivityExpanded;
      this.emit('live-activity-expanded', { expanded: this.isLiveActivityExpanded });
    }

    updateWidgetData(title, progress, remainingTime) {
      this.activeWidget.title = title;
      this.activeWidget.progress = progress;
      this.activeWidget.remainingTime = remainingTime;
      this.emit('widget-updated', this.activeWidget);
    }
  }

  global.AxxSystemSurfaces = new SystemSurfacesController();
})(typeof window !== 'undefined' ? window : this);
