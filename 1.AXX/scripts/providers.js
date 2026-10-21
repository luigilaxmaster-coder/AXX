/* Native provider settings. Never persist API keys in browser storage. */
(() => {
  const setup = () => {
    if (!window.Axx?.companion) return setTimeout(setup, 50);
    const $ = id => document.getElementById(id);
    const misplacedKey = value => /^[0-9a-f]{24,}\.[A-Za-z0-9_-]{16,}$/i.test(value || '') || /^(sk-|AIza)/.test(value || '');
    if (misplacedKey(Axx.companion.data.prefs.model)) {
      Axx.companion.data.prefs.model = '';
      Axx.companion.brain.reset(); Axx.companion.save();
    }
    const panel = $('subpanel-api');
    panel.innerHTML = `
      <label class="setting">Conexiones guardadas<select id="provider-saved"><option value="">Nueva conexión</option></select></label>
      <label class="setting">Plataforma<select id="provider-kind">
        <option value="ollama">Ollama local (modelos instalados)</option><option value="ollama_cloud">Ollama Cloud (con clave de API)</option><option value="compat">LM Studio</option>
        <option value="groq">Groq</option><option value="anthropic">Claude · Anthropic</option>
        <option value="openrouter">OpenRouter</option><option value="openai">OpenAI</option>
        <option value="gemini">Google Gemini</option><option value="custom">Otra API compatible</option>
      </select></label>
      <label class="setting">Nombre de la conexión<input class="field" id="provider-name" maxlength="80" placeholder="Por ejemplo: Ollama escritorio" /></label>
      <label class="setting">URL o IP del servidor<input class="field" id="provider-url" spellcheck="false" placeholder="http://192.168.1.50:11434/v1" /></label>
      <label class="setting" id="provider-protocol-row" hidden>Protocolo<select id="provider-protocol"><option value="openai">Compatible con OpenAI</option><option value="anthropic">Anthropic Messages</option></select></label>
      <label class="setting">Clave de API — pega tu clave aquí<input class="field" id="provider-key" type="password" autocomplete="off" spellcheck="false" placeholder="No hace falta para Ollama local" /></label>
      <div class="quick-row"><button id="provider-discover" type="button">Consultar modelos</button></div>
      <label class="setting">Modelo disponible<select id="provider-model"><option value="">Pulsa Consultar modelos</option></select></label>
      <label class="setting" id="provider-manual-row" hidden>ID del modelo (no es una clave)<input class="field" id="provider-model-manual" maxlength="200" placeholder="Ejemplo: qwen3:4b" /></label>
      <p id="provider-catalog-status" class="micro-copy" role="status"></p>
      <label class="setting"><span><input id="provider-enabled" type="checkbox" checked /> Habilitar esta conexión</span></label>
      <label class="setting"><span><input id="provider-billing" type="checkbox" /> Autorizar el uso de mi cuota o saldo en este proveedor</span></label>
      <p class="micro-copy">Las APIs pueden cobrar por uso. Guardar o consultar el catálogo no envía mensajes. Las claves se protegen en este usuario de Windows.</p>
      <div class="quick-row provider-actions"><button class="primary" id="provider-save" type="button">Guardar y seleccionar</button><button id="provider-refresh" type="button">Actualizar conexiones</button></div>
      <p id="provider-status" class="tool-feedback" role="status"></p>`;
    const presets = {
      ollama: 'http://127.0.0.1:11434/v1', compat: 'http://127.0.0.1:1234/v1',
      ollama_cloud: 'https://ollama.com/v1',
      groq: 'https://api.groq.com/openai/v1', anthropic: 'https://api.anthropic.com/v1',
      openrouter: 'https://openrouter.ai/api/v1', openai: 'https://api.openai.com/v1',
      gemini: 'https://generativelanguage.googleapis.com/v1beta/openai', custom: ''
    };
    let entries = [], busy = false;
    const status = text => { $('provider-status').textContent = text; };
    const payload = () => ({ provider: $('provider-kind').value, name: $('provider-name').value.trim(),
      base_url: $('provider-url').value.trim(), model: ($('provider-model').value === '__manual__' ? $('provider-model-manual').value : $('provider-model').value).trim(),
      protocol: $('provider-protocol').value, api_key: $('provider-key').value.trim(),
      enabled: $('provider-enabled').checked, billing_allowed: $('provider-billing').checked });
    const refresh = async () => {
      const selected = $('provider-saved').value || Axx.companion.data.prefs.apiConnection;
      const result = await Axx.backendRequest('GET', '/axx-api/providers');
      entries = result.providers || [];
      $('provider-saved').replaceChildren(new Option('Nueva conexión', ''), ...entries.map(p => new Option(p.name + ' · ' + p.model, p.name)));
      if (entries.some(p => p.name === selected)) { $('provider-saved').value = selected; $('provider-saved').onchange(); }
    };
    const action = async (fn, clearKey = false) => {
      if (busy) return;
      busy = true;
      panel.querySelectorAll('button,input,select').forEach(control => control.disabled = true);
      try { await fn(); } catch(e) { status(e.message || String(e)); }
      finally { busy = false; if (clearKey) $('provider-key').value = ''; panel.querySelectorAll('button,input,select').forEach(control => control.disabled = false); }
    };
    const platform = () => {
      $('provider-url').value = presets[$('provider-kind').value];
      $('provider-protocol-row').hidden = $('provider-kind').value !== 'custom';
      $('provider-key').value = ''; $('provider-model').value = ''; $('provider-billing').checked = false;
      $('provider-enabled').checked = true;
      $('provider-model').replaceChildren(new Option('Pulsa Consultar modelos', ''), new Option('Escribir ID manualmente…', '__manual__'));
      $('provider-manual-row').hidden = true; $('provider-model-manual').value = '';
      $('provider-key').placeholder = $('provider-kind').value === 'ollama' ? 'No hace falta para Ollama local' : 'Pega tu clave o deja vacío para conservar la guardada';
      $('provider-catalog-status').textContent = $('provider-kind').value === 'ollama_cloud' ? 'Modelos de la nube de Ollama. No necesitas descargarlos.' : $('provider-kind').value === 'ollama' ? 'Aquí aparecen solo los modelos instalados en este servidor.' : '';
    };
    $('provider-kind').onchange = platform;
    $('provider-saved').onchange = () => {
      const p = entries.find(p => p.name === $('provider-saved').value);
      if (!p) { $('provider-name').value = ''; platform(); return; }
      $('provider-kind').value = p.kind || 'custom'; platform();
      $('provider-name').value = p.name; $('provider-url').value = p.base_url;
      $('provider-model').add(new Option(p.model, p.model), 1); $('provider-model').value = p.model;
      $('provider-protocol').value = p.protocol || 'openai'; $('provider-billing').checked = !!p.billing_allowed;
      $('provider-enabled').checked = p.enabled; status(p.has_key ? 'Clave guardada. Déjala vacía para conservarla.' : 'Conexión sin clave guardada.');
    };
    $('provider-model').onchange = () => { $('provider-manual-row').hidden = $('provider-model').value !== '__manual__'; };
    const discover = async () => {
      status('Consultando el servidor…');
      const result = await Axx.backendRequest('POST', '/axx-api/providers/discover', payload());
      const previous = payload().model;
      $('provider-model').replaceChildren(new Option(result.models.length ? 'Selecciona un modelo' : 'No hay modelos instalados', ''), ...result.models.map(m => new Option(m, m)), new Option('Escribir ID manualmente…', '__manual__'));
      $('provider-model').value = result.models.includes(previous) ? previous : result.models[0] || '';
      $('provider-manual-row').hidden = true;
      const message = result.models.length ? `${result.models.length} modelos disponibles. Abre la lista y elige uno.` : $('provider-kind').value === 'ollama' ? 'Ollama está conectado, pero no tiene modelos instalados. Para usar una clave de API elige Ollama Cloud; para uso local instala primero un modelo en Ollama.' : 'El servidor no devolvió modelos. Puedes introducir el ID manualmente.';
      $('provider-catalog-status').textContent = message; status(message);
    };
    $('provider-discover').onclick = () => action(discover);
    $('provider-save').onclick = () => action(async () => {
      const data = payload();
      if (!data.name || !data.model) throw new Error('Escribe el nombre de la conexión y el modelo.');
      if (misplacedKey(data.model)) throw new Error('La clave va en Clave de API. Selecciona un modelo de la lista.');
      status('Guardando conexión…');
      await Axx.backendRequest('POST', '/axx-api/providers/save', data);
      await refresh(); $('provider-saved').value = data.name;
      const c = Axx.companion; c.data.prefs.provider = 'bridge'; c.data.prefs.model = data.model;
      c.data.prefs.apiConnection = data.name;
      $('ai-provider').value = 'bridge'; c.save();
      await c.connect();
      const selected = c.brain.connected && c.data.prefs.model === data.model;
      if (!selected) { c.brain.reset(); c.data.prefs.model = data.model; c.save(); c.syncProvider(); }
      status(selected ? 'Conexión guardada y modelo seleccionado. Ya puedes abrir el chat.' : 'Conexión guardada. Revisa la clave, la habilitación y la autorización de cuota antes de usarla.');
    }, true);
    $('provider-refresh').onclick = () => action(refresh);
    $('tab-mode-api').addEventListener('click', () => { void action(refresh); });
    platform();
    // Local network requests also go through the host, avoiding browser CORS and exposing no credentials.
    $('ai-test').onclick = async () => {
      $('tab-mode-api').click();
      while (busy) await new Promise(resolve => setTimeout(resolve, 25));
      $('provider-kind').value = $('local-server-type').value; platform();
      $('provider-url').value = $('ai-endpoint').value;
      $('provider-name').value = 'Servidor local';
      await action(discover);
    };
  };
  setup();
})();
