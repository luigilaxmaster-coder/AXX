/**
 * Axx Mobile · Subsistema de Voz, Dictado y Conversación
 * Procesa captura de micrófono con Web Audio API, análisis de frecuencia en tiempo real,
 * transcripción de dictado, traducción por segmentos y síntesis de voz (TTS).
 */

(function (global) {
  'use strict';

  class VoiceChatController {
    constructor() {
      this.mode = 'chat'; // 'chat' | 'dictate' | 'translate'
      this.isRecording = false;
      this.audioContext = null;
      this.analyser = null;
      this.mediaStream = null;
      this.animFrame = null;
      this.messages = [];
      this.dictationDraft = '';
      this.translationResult = '';
      this.sourceLang = 'es';
      this.targetLang = 'en';
      this.audioDestination = 'speaker'; // 'speaker' | 'headphones' | 'pc_remote'
      this.listeners = new Set();

      this.initSpeechRecognition();
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
          console.error('Error en listener de VoiceChat', e);
        }
      }
    }

    initSpeechRecognition() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = this.sourceLang === 'es' ? 'es-ES' : 'en-US';

        this.recognition.onresult = (event) => {
          let interim = '';
          let final = '';
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              final += event.results[i][0].transcript;
            } else {
              interim += event.results[i][0].transcript;
            }
          }
          const text = (final || interim).trim();
          if (text) {
            this.handleTranscriptUpdate(text);
          }
        };

        this.recognition.onerror = (err) => {
          console.warn('SpeechRecognition error', err);
        };
      }
    }

    async startRecording() {
      if (this.isRecording) return;
      try {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 64;
        source.connect(this.analyser);

        this.isRecording = true;
        this.emit('recording-started', { mode: this.mode });

        if (this.recognition) {
          try {
            this.recognition.start();
          } catch (e) {}
        }

        this.monitorAudioLevels();
      } catch (err) {
        console.warn('Micrófono nativo no disponible o denegado, usando emulación táctil', err);
        this.isRecording = true;
        this.emit('recording-started', { mode: this.mode, simulated: true });
        this.simulateAudioLevels();
      }
    }

    monitorAudioLevels() {
      const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      const update = () => {
        if (!this.isRecording) return;
        this.analyser.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        const normalized = Math.min(1.0, avg / 128);

        this.emit('audio-level', { level: normalized, rawBins: Array.from(dataArray.slice(0, 8)) });
        this.animFrame = requestAnimationFrame(update);
      };
      this.animFrame = requestAnimationFrame(update);
    }

    simulateAudioLevels() {
      let t = 0;
      const update = () => {
        if (!this.isRecording) return;
        t += 0.1;
        const level = 0.3 + 0.5 * Math.abs(Math.sin(t * 3) * Math.cos(t * 1.5));
        const mockBins = [level * 200, level * 160, level * 230, level * 180, level * 210, level * 140, level * 90, level * 60];
        this.emit('audio-level', { level, rawBins: mockBins });
        this.animFrame = requestAnimationFrame(update);
      };
      this.animFrame = requestAnimationFrame(update);
    }

    stopRecording() {
      if (!this.isRecording) return;
      this.isRecording = false;

      if (this.animFrame) cancelAnimationFrame(this.animFrame);
      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach((track) => track.stop());
        this.mediaStream = null;
      }
      if (this.audioContext && this.audioContext.state !== 'closed') {
        this.audioContext.close();
      }
      if (this.recognition) {
        try {
          this.recognition.stop();
        } catch (e) {}
      }

      this.emit('recording-stopped', {
        draft: this.dictationDraft,
        mode: this.mode
      });

      // Si estábamos en modo Conversar y hay borrador, enviarlo automáticamente
      if (this.mode === 'chat' && this.dictationDraft.trim()) {
        this.sendMessage(this.dictationDraft.trim());
        this.dictationDraft = '';
      }
    }

    handleTranscriptUpdate(text) {
      this.dictationDraft = text;
      this.emit('transcript-update', { text, mode: this.mode });

      // En modo dictar con traducción, pre-calcular traducción
      if (this.mode === 'translate') {
        this.translateText(text);
      }
    }

    async translateText(text) {
      if (!text.trim()) return;
      try {
        const res = await global.AxxBridge.request('/axx-api/translate', {
          method: 'POST',
          body: {
            text: text,
            source_lang: this.sourceLang,
            target_lang: this.targetLang
          }
        });
        if (res && res.translated_text) {
          this.translationResult = res.translated_text;
          this.emit('translation-ready', {
            original: text,
            translated: res.translated_text,
            source: this.sourceLang,
            target: this.targetLang
          });
        }
      } catch (e) {
        // Fallback simple de visualización
        this.translationResult = `[EN]: ${text}`;
        this.emit('translation-ready', { original: text, translated: this.translationResult });
      }
    }

    async sendMessage(text) {
      if (!text || !text.trim()) return;
      const userMsg = { id: 'msg-' + Date.now(), role: 'user', content: text.trim(), time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
      this.messages.push(userMsg);
      this.emit('messages-updated', this.messages);

      // Notificar que Axx está pensando
      this.emit('thinking-started', {});

      try {
        const response = await global.AxxBridge.request('/axx-api/chat', {
          method: 'POST',
          body: {
            messages: [{ role: 'user', content: text.trim() }]
          }
        });

        const replyContent = response.choices?.[0]?.message?.content || 'He recibido la instrucción en el equipo seleccionado.';
        const axxMsg = {
          id: 'msg-' + (Date.now() + 1),
          role: 'assistant',
          content: replyContent,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        this.messages.push(axxMsg);
        this.emit('messages-updated', this.messages);
        this.emit('thinking-finished', {});

        // Reproducir por voz si la salida no está silenciada
        this.speakText(replyContent);
      } catch (err) {
        this.emit('thinking-finished', {});
        this.emit('chat-error', { error: 'No se pudo comunicar con el router de inferencia' });
      }
    }

    speakText(text) {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'es-ES';
        utterance.rate = 1.05;
        utterance.pitch = 0.95;
        utterance.onstart = () => this.emit('speaking-started', { text });
        utterance.onend = () => this.emit('speaking-finished', {});
        window.speechSynthesis.speak(utterance);
      }
    }

    cancelSpeech() {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      this.emit('speaking-finished', {});
    }
  }

  global.AxxVoiceChat = new VoiceChatController();
})(typeof window !== 'undefined' ? window : this);
