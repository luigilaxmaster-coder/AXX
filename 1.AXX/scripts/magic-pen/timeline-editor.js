/**
 * AXX Evolution 3.0 — Magic Pen Motion & Simulation Timeline Editor (PR-06).
 * Deterministic freeze(t) scrubber, playback controls, seed configuration,
 * and synchronized TTS/subtitle cue notifications.
 * Lazy-loaded; cleans up all timers and event listeners on unmount.
 */
(function (global) {
  'use strict';

  function createTimelineEditor(options) {
    const opts = options || {};
    const container = opts.container || null;
    const onSeek = typeof opts.onSeek === 'function' ? opts.onSeek : function () {};
    const onExportMp4 = typeof opts.onExportMp4 === 'function' ? opts.onExportMp4 : function () {};

    let mounted = false;
    let currentTime = 0.0;
    let duration = 4.0;
    let seed = 42;
    let playing = false;
    let timerId = null;
    const cleanupFns = [];

    function stopTimer() {
      playing = false;
      if (timerId !== null) {
        clearInterval(timerId);
        timerId = null;
      }
    }

    function freeze(tSeconds) {
      const clamped = Math.min(Math.max(0, Number(tSeconds) || 0), duration);
      currentTime = Math.round(clamped * 1000) / 1000;
      onSeek({ timestamp_seconds: currentTime, seed: seed });
      render();
      return currentTime;
    }

    function render() {
      if (!container || !mounted) return;
      container.textContent = '';

      const panel = document.createElement('div');
      panel.className = 'axx-motion-timeline-panel';
      panel.setAttribute('role', 'region');
      panel.setAttribute('aria-label', 'Línea de tiempo Motion Studio');

      const playBtn = document.createElement('button');
      playBtn.type = 'button';
      playBtn.className = 'axx-motion-play-btn';
      playBtn.textContent = playing ? 'Pausar' : 'Reproducir';
      const onPlayClick = function () {
        if (playing) {
          stopTimer();
          render();
        } else {
          playing = true;
          timerId = setInterval(function () {
            if (!mounted) {
              stopTimer();
              return;
            }
            const next = currentTime + 0.1;
            if (next >= duration) {
              stopTimer();
              freeze(duration);
            } else {
              freeze(next);
            }
          }, 100);
          render();
        }
      };
      playBtn.addEventListener('click', onPlayClick);
      cleanupFns.push(function () {
        playBtn.removeEventListener('click', onPlayClick);
      });
      panel.appendChild(playBtn);

      const slider = document.createElement('input');
      slider.type = 'range';
      slider.min = '0';
      slider.max = String(duration);
      slider.step = '0.05';
      slider.value = String(currentTime);
      slider.setAttribute('aria-label', 'Tiempo en segundos');
      const onSlide = function () {
        stopTimer();
        freeze(parseFloat(slider.value));
      };
      slider.addEventListener('input', onSlide);
      cleanupFns.push(function () {
        slider.removeEventListener('input', onSlide);
      });
      panel.appendChild(slider);

      const timeLabel = document.createElement('span');
      timeLabel.className = 'axx-motion-time-label';
      timeLabel.textContent = currentTime.toFixed(2) + 's / ' + duration.toFixed(2) + 's';
      panel.appendChild(timeLabel);

      const exportBtn = document.createElement('button');
      exportBtn.type = 'button';
      exportBtn.className = 'axx-motion-export-btn';
      exportBtn.textContent = 'Exportar MP4';
      const onExport = function () {
        onExportMp4({ seed: seed, duration_seconds: duration });
      };
      exportBtn.addEventListener('click', onExport);
      cleanupFns.push(function () {
        exportBtn.removeEventListener('click', onExport);
      });
      panel.appendChild(exportBtn);

      container.appendChild(panel);
    }

    return {
      mount: function (timelineConfig) {
        mounted = true;
        if (timelineConfig && typeof timelineConfig === 'object') {
          duration = Math.max(0.1, Number(timelineConfig.duration_seconds) || 4.0);
          seed = Number.isInteger(timelineConfig.seed) ? timelineConfig.seed : 42;
        }
        render();
      },
      freeze: freeze,
      unmount: function () {
        mounted = false;
        stopTimer();
        while (cleanupFns.length > 0) {
          const fn = cleanupFns.pop();
          try { fn(); } catch (_) {}
        }
        if (container) container.textContent = '';
      },
    };
  }

  global.AxxTimelineEditor = { createTimelineEditor: createTimelineEditor };
})(typeof window !== 'undefined' ? window : globalThis);
