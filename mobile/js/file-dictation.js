/* Dictation stays on the paired PC and never dispatches a command automatically. */
(() => {
  'use strict';
  const voice = window.Capacitor?.Plugins?.AxxVoice;
  const transport = window.Capacitor?.Plugins?.AxxTransport;
  const draft = document.getElementById('draft');
  if (!voice || !transport || !draft) return;
  const button = document.createElement('button');
  button.type = 'button'; button.id = 'file-dictation'; button.textContent = 'Dictar';
  button.setAttribute('aria-label', 'Dictar un mensaje con reconocimiento local en la PC');
  document.getElementById('chat-form').append(button);
  const status = document.createElement('p'); status.className = 'hint';
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); button.after(status);
  const discard = document.createElement('button'); discard.type = 'button';
  discard.textContent = 'Descartar dictado'; discard.hidden = true; status.after(discard);
  let session = null, pending = null, timer = null, working = false, binding = null;
  const request = async (path, body) => (await transport.request({path,
    method: body ? 'POST' : 'GET', ...(binding || {}), ...(body ? {body} : {})})).data;
  function release() {
    clearInterval(timer); timer = null; window.axxFileDictationActive = false;
    button.textContent = pending ? 'Consultar dictado' : 'Dictar';
    discard.hidden = !session;
  }
  async function result() {
    if (!pending) return;
    const value = await request('/v1/files/dictation?request_id=' + encodeURIComponent(pending));
    if (value.state === 'transcribing') { status.textContent = 'Transcribiendo localmente en tu PC…'; return; }
    if (value.state !== 'completed') throw new Error(value.error || 'No se pudo transcribir.');
    draft.value = [draft.value.trim(), value.text].filter(Boolean).join(' ');
    draft.dispatchEvent(new Event('input', {bubbles: true}));
    status.textContent = value.text ? 'Texto listo. Revísalo y pulsa Enviar.' : 'No se reconoció voz. Puedes intentarlo otra vez.';
    pending = null;
    if (session) await voice.discard({session_id: session});
    session = null; binding = null; release();
  }
  async function finish() {
    if (working || !session || pending) return;
    working = true; button.disabled = true;
    try {
      const audio = await voice.audio({session_id: session});
      pending = session;
      status.textContent = 'Enviando dictado cifrado a tu PC…';
      await request('/v1/files/dictation', {request_id: pending, mime: audio.mime, audio_base64: audio.audio_base64});
      clearInterval(timer);
      timer = setInterval(() => { if (!working && !document.hidden) void poll(); }, 1000);
      await result();
    } catch (error) {
      status.textContent = error.message + ' El texto no se ha enviado al chat.';
      clearInterval(timer); timer = null;
    } finally { working = false; button.disabled = false; button.textContent = pending ? 'Consultar dictado' : 'Dictar'; }
  }
  async function poll() {
    if (working) return;
    working = true;
    try { await result(); }
    catch (error) { status.textContent = error.message; release(); }
    finally { working = false; }
  }
  button.onclick = async () => {
    if (working) return;
    if (pending) { await poll(); return; }
    working = true; button.disabled = true;
    try {
      if (session) {
        await voice.stop({session_id: session, from_pc: false});
        working = false; await finish(); return;
      }
      const profile = await transport.profile();
      if (!profile.paired) throw new Error('Enlaza la PC antes de dictar.');
      binding = {expected_device_id: profile.device_id, expected_fingerprint: profile.fingerprint};
      await request('/v1/status');
      const current = await voice.status();
      if (current.state !== 'idle') throw new Error('Termina o descarta la grabación actual antes de dictar.');
      const permission = await voice.permit();
      if (permission.permission !== 'granted') throw new Error('Permite el micrófono para dictar.');
      window.axxFileDictationActive = true;
      session = crypto.randomUUID();
      await voice.start({session_id: session, max_seconds: 30});
      discard.hidden = false;
      button.textContent = 'Terminar dictado'; status.textContent = 'Escuchando · máximo 30 s. Solo tu PC transcribe.';
      timer = setInterval(() => { void voice.heartbeat().catch(() => {}); }, 1000);
    } catch (error) { status.textContent = error.message; if (session) await voice.discard({session_id: session}).catch(() => {}); session = null; binding = null; release(); }
    finally { working = false; button.disabled = false; }
  };
  discard.onclick = async () => {
    if (working || !session) return;
    working = true;
    try { await voice.discard({session_id: session}); session = null; pending = null; binding = null; release(); status.textContent = 'Dictado descartado.'; }
    catch (error) { status.textContent = error.message; }
    finally { working = false; }
  };
  void voice.addListener('captureState', value => {
    if (!session || value.session_id !== session || pending) return;
    if (value.state === 'stopped' && !working) {
      if (!document.hidden && ['timeout', 'user_stop'].includes(value.reason)) void finish();
      else { release(); status.textContent = 'Grabación interrumpida. Pulsa Dictar para revisar el audio pendiente.'; }
    }
  });
})();
