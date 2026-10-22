/**
 * Axx Mobile · Controlador de Navegación Principal y Modales
 * Gestiona el intercambio fluido entre los tres destinos persistentes:
 * AXX, ESCRITORIO y TRABAJO, además de los talleres modales (Magic Pen, Pairing, Settings).
 */

(function (global) {
  'use strict';

  class NavigationController {
    constructor() {
      this.currentDestination = 'axx'; // 'axx' | 'desktop' | 'work'
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
          console.error('Error en listener de NavigationController', e);
        }
      }
    }

    goTo(destination) {
      if (this.currentDestination === destination) return;
      this.currentDestination = destination;

      // Háptica sutil en dispositivos compatibles
      if ('vibrate' in navigator) {
        try { navigator.vibrate(10); } catch (e) {}
      }

      // Actualizar vistas en el DOM
      document.querySelectorAll('.view-pane').forEach((pane) => {
        pane.classList.remove('active');
      });
      const activePane = document.getElementById(`view-${destination}`);
      if (activePane) {
        activePane.classList.add('active');
      }

      // Actualizar botones de navegación inferior
      document.querySelectorAll('.nav-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.target === destination);
      });

      this.emit('navigated', { destination });
    }
  }

  global.AxxNavigation = new NavigationController();
})(typeof window !== 'undefined' ? window : this);
