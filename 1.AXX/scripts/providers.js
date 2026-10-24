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
      <style>
        #subpanel-api #model-task-fit{border:1px solid var(--line);border-radius:16px;background:var(--surface-subtle,#a9c9ef0b);overflow:hidden}
        #subpanel-api #model-task-fit>summary{display:flex;align-items:center;gap:10px;cursor:pointer;list-style:none;padding:16px 18px;font-size:14px;font-weight:650;color:var(--ink,var(--text))}
        #subpanel-api #model-task-fit>summary::-webkit-details-marker{display:none}
        #subpanel-api #model-task-fit>summary::after{content:'⌄';margin-left:auto;color:var(--secondary,var(--quiet));font-size:20px;line-height:1;transition:transform .16s}
        #subpanel-api #model-task-fit[open]>summary::after{transform:rotate(180deg)}
        #subpanel-api .model-task-body{display:grid;gap:14px;padding:0 18px 18px}
        #subpanel-api .model-task-intro{margin:0;max-width:68ch}
        #subpanel-api .model-task-controls{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:12px}
        #subpanel-api .model-task-controls .setting{padding:0;border:0;gap:6px}
        #subpanel-api #model-task-check{white-space:nowrap}
        #subpanel-api #model-task-options:not(:empty){display:grid;gap:10px;border-top:1px solid var(--line);padding-top:14px}
        #subpanel-api #model-task-options>p{margin:0;line-height:1.5}
        #subpanel-api .model-task-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface,var(--bg))}
        #subpanel-api .model-task-row>div{min-width:0;display:grid;gap:2px;overflow-wrap:anywhere}
        #subpanel-api .model-task-row strong{font-size:13px;font-weight:600;color:var(--ink,var(--text))}
        #subpanel-api .model-task-row small{font-size:11px;color:var(--secondary,var(--quiet))}
        #subpanel-api .model-task-row button{flex:none}
        @media(max-width:640px){#subpanel-api .model-task-controls{grid-template-columns:1fr}#subpanel-api #model-task-check{width:100%}#subpanel-api .model-task-row{align-items:stretch;flex-direction:column}#subpanel-api .model-task-row button{width:100%}}
      </style>
      <label class="setting">Selección de modelos<select id="provider-selection-mode"><option value="automatic_free">Automático gratis · Sin claves</option><option value="manual">Manual · conexión seleccionada</option></select></label>
      <p class="micro-copy">Axx prepara Kilo Gateway, OVHcloud y AI Horde y prueba sus modelos sin claves personales. Solo usa las rutas que superan las pruebas. Si no hay disponibilidad, conserva la tarea pendiente.</p>
      <p class="micro-copy">También desde el chat: «/modelos», «cambia de modelo a nombre o ID» y «/modelo automático».</p>
      <details id="model-task-fit"><summary>Modelo según la tarea</summary><div class="model-task-body">
        <p class="micro-copy model-task-intro">Elige una tarea para ver rutas compatibles. Voz y visión tienen selección propia; las demás usan el router automático o el modelo principal.</p>
        <div class="model-task-controls"><label class="setting">Tarea<select id="model-task-kind"><option value="chat">Conversar</option><option value="voice">Responder por voz</option><option value="vision">Analizar imágenes</option><option value="plan">Planificar</option><option value="code">Código</option><option value="writing">Redactar</option><option value="translation">Traducir</option><option value="grounding">Control visual de Agent-S</option></select></label>
        <button id="model-task-check" type="button">Ver opciones</button></div><div id="model-task-options" role="status"></div>
        <p class="micro-copy">«Lista localmente» indica disponibilidad de la conexión, no calidad o velocidad comprobadas.</p></div>
      </details>
      <button id="keyless-refresh" type="button">Comprobar modelos sin claves</button><p id="keyless-status" role="status"></p>
      <p class="micro-copy">Son servicios públicos externos. Kilo indica que registra peticiones y respuestas para entrenamiento. Las conexiones personales de abajo son opcionales.</p>
      <details id="model-candidates-panel"><summary>Candidatos iniciales y evaluación</summary>
        <p class="micro-copy">Los nombres propuestos se resuelven contra el catálogo efectivo. Una prueba usa una petición gratuita con datos de ejemplo; no ejecuta los comandos o código generados. Si pasa, se actualiza su preferencia para esa tarea.</p>
        <button id="model-candidates-refresh" type="button">Actualizar catálogo de candidatos</button><div id="model-candidates-list"></div>
        <p id="model-candidates-status" role="status"></p>
      </details>
      <label class="setting">Conexiones guardadas<select id="provider-saved"><option value="">Nueva conexión</option></select></label>
      <label class="setting">Plataforma<select id="provider-kind">
        <option value="freellmapi">FreeLLMAPI · gateway de modelos</option>
        <option value="ollama">Ollama local (modelos instalados)</option><option value="ollama_cloud">Ollama Cloud (con clave de API)</option><option value="compat">LM Studio</option>
        <option value="groq">Groq</option><option value="anthropic">Claude · Anthropic</option>
        <option value="openrouter">OpenRouter</option><option value="openai">OpenAI</option>
        <option value="gemini">Google Gemini</option><option value="custom">Otra API compatible</option>
      </select></label>
      <label class="setting">Nombre de la conexión<input class="field" id="provider-name" maxlength="80" placeholder="Por ejemplo: Ollama escritorio" /></label>
      <label class="setting">URL o IP del servidor<input class="field" id="provider-url" spellcheck="false" placeholder="http://192.168.1.50:11434/v1" /></label>
      <label class="setting" id="provider-protocol-row" hidden>Protocolo<select id="provider-protocol"><option value="openai">Compatible con OpenAI</option><option value="anthropic">Anthropic Messages</option></select></label>
      <label class="setting">Clave de API personal — opcional<input class="field" id="provider-key" type="password" autocomplete="off" spellcheck="false" placeholder="No se necesita en el modo sin claves" /></label>
      <details id="gateway-controls"><summary>FreeLLMAPI: conexión y perfiles</summary>
        <p class="micro-copy">Axx puede administrar la instalación local fijada o conectarse a una instancia externa por su URL. Solo cierra los procesos que inició.</p>
        <div class="quick-row"><button id="gateway-start" type="button">Iniciar gateway local</button><button id="gateway-status" type="button">Comprobar conexión</button><button id="gateway-stop" type="button">Detener gateway de Axx</button></div>
        <label class="setting">Sesión del panel externo (opcional)<input id="gateway-dashboard" class="field" type="password" autocomplete="off" placeholder="No se necesita con el gateway administrado"></label>
        <label class="setting">Conexión gratuita de Axx para añadir al gateway<select id="gateway-import-source"></select></label><button id="gateway-import" type="button">Añadir esta conexión al gateway</button>
        <button id="gateway-inspect" type="button">Consultar miembros y perfiles</button><div id="gateway-members"></div>
        <p class="micro-copy">Marca solo las cuentas y modelos que no pueden consumir saldo. Axx comprueba miembros, capacidades y cuota antes de cada uso automático.</p>
        <button id="gateway-profiles" type="button">Crear y guardar perfiles con los miembros marcados</button><p id="gateway-result" role="status"></p>
      </details>
      <div class="quick-row"><button id="provider-discover" type="button">Consultar modelos</button></div>
      <label class="setting">Modelo disponible<select id="provider-model"><option value="">Pulsa Consultar modelos</option></select></label>
      <label class="setting" id="provider-manual-row" hidden>ID del modelo (no es una clave)<input class="field" id="provider-model-manual" maxlength="200" placeholder="Ejemplo: qwen3:4b" /></label>
      <p id="provider-catalog-status" class="micro-copy" role="status"></p>
      <label class="setting"><span><input id="provider-enabled" type="checkbox" checked /> Habilitar esta conexión</span></label>
      <label class="setting"><span><input id="provider-billing" type="checkbox" /> Autorizar el uso de mi cuota o saldo en este proveedor</span></label>
      <details><summary>Aptitud para Automático · gratuito</summary>
        <label class="setting">Coste de esta ruta<select id="provider-cost"><option value="unknown">Sin verificar</option><option value="direct_local">Modelo local directo</option><option value="free_tier">Cuota gratuita sin cobro posterior</option><option value="paid">De pago</option></select></label>
        <label class="setting">Conexión<select id="provider-route"><option value="unknown">Sin verificar</option><option value="direct">Directa al proveedor</option><option value="proxy">Intermediario / proxy</option></select></label>
        <label class="setting"><span><input id="provider-free" type="checkbox" /> Confirmo que esta ruta no puede consumir saldo ni activar cobros</span></label>
        <label class="setting">Ventana de contexto declarada (tokens)<input id="provider-context" type="number" min="1" max="10000000" placeholder="Según el modelo"></label>
        <label class="setting">Presupuesto máximo por imagen (tokens)<input id="provider-image-context" type="number" min="1" max="10000000" placeholder="Solo para visión"></label>
        <label class="setting">Capacidades<select id="provider-capabilities" multiple size="3"><option value="text">Texto</option><option value="vision">Visión</option><option value="tools">Llamadas a herramientas</option></select></label>
        <label class="setting">Tareas aptas<select id="provider-tasks" multiple size="8"><option value="chat">Conversación</option><option value="plan">Planes nuevos</option><option value="parameters">Interpretar parámetros</option><option value="repair">Reparar planes</option><option value="vision">Visión</option><option value="code">Código</option><option value="writing">Redacción</option><option value="translation">Traducción</option></select></label>
        <label class="setting">Prioridad inicial (0 mejor, 100 menor)<input id="provider-priority" type="number" min="0" max="100" value="50"></label>
        <p class="micro-copy">Declara únicamente capacidades y tareas que hayas comprobado. La prioridad se ajusta con resultados de Axx; una respuesta HTTP correcta no demuestra que la tarea haya funcionado. Un proxy local también puede cobrar.</p>
      </details>
      <p class="micro-copy">Las APIs pueden cobrar por uso. Guardar o consultar el catálogo no envía mensajes. Las claves se protegen en este usuario de Windows.</p>
      <div class="quick-row provider-actions"><button class="primary" id="provider-save" type="button">Guardar y seleccionar</button><button id="provider-refresh" type="button">Actualizar conexiones</button></div>
      <p id="provider-status" class="tool-feedback" role="status"></p>`;
    const presets = {
      ollama: 'http://127.0.0.1:11434/v1', compat: 'http://127.0.0.1:1234/v1',
      ollama_cloud: 'https://ollama.com/v1',
      groq: 'https://api.groq.com/openai/v1', anthropic: 'https://api.anthropic.com/v1',
      openrouter: 'https://openrouter.ai/api/v1', openai: 'https://api.openai.com/v1',
      gemini: 'https://generativelanguage.googleapis.com/v1beta/openai', custom: '', freellmapi: ''
    };
    let entries = [], busy = false;
    const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    Axx.modelSelection = {
      parse(text) {
        const raw = String(text || '').trim();
        const voice = raw.match(/^\/modelo-voz(?:\s+(.*))?$/i);
        if (voice) return {voice:true,target:(voice[1] || '').trim()};
        if (/^(?:\/modelos|(?:lista|muestra|ver) (?:los )?modelos)$/i.test(raw)) return {list:true};
        const match = raw.match(/^(?:\/modelo(?:\s+|$)|(?:cambia(?:r)?(?: de)?(?: el)? modelo a|usa(?:r)? (?:el )?modelo)\s+)(.*)$/i);
        if (match) return {target:match[1].trim()};
        if (/^(?:vuelve|volver|cambia) a automatico(?: gratis)?(?: sin claves)?$/.test(normalize(raw))) return {target:'automatico'};
        return null;
      },
      async run(command) {
        const c = Axx.companion;
        if (!Axx.isNative()) return 'El cambio de modelo requiere Axx para Windows.';
        if (busy || c.pending || c.externalBusy || c.connecting) return 'Espera a que termine la respuesta o la conexión actual y vuelve a escribir la orden. La tarea se conserva.';
        if (command.voice) {
          const target = normalize(command.target);
          if (['mismo','chat','mismo del chat'].includes(target)) {
            c.data.prefs.voiceModel=''; c.save(); Axx.refreshVoiceModelOptions?.();
            return 'La voz usará el modelo seleccionado para el chat.';
          }
          if (!c.brain.connected || c.data.prefs.selection_mode === 'automatic_free')
            return 'Para elegir un modelo de voz individual, conecta una opción manual en Conectar IA. En modo automático, usa /modelo-voz mismo.';
          const available = c.brain.models;
          if (!target) return 'Modelo de voz: ' + (c.data.prefs.voiceModel || 'mismo del chat') + '. Disponibles en esta conexión: ' + (available.join(', ') || 'ninguno') + '. Usa /modelo-voz ID o /modelo-voz mismo.';
          const matches = available.filter(model => normalize(model) === target);
          if (matches.length !== 1) return 'Ese modelo no está disponible en la conexión actual. Opciones: ' + (available.join(', ') || 'ninguna') + '. No cambié la selección.';
          c.data.prefs.voiceModel=matches[0]; c.save(); Axx.refreshVoiceModelOptions?.();
          return 'Modelo de voz seleccionado: ' + matches[0] + '. Se usará en el siguiente turno hablado.';
        }
        busy = true;
        try {
          const target = normalize(command.target);
          const automatic = /^(?:auto|automatico(?: gratis)?(?: ·)?(?: sin claves)?)$/.test(target);
          let selected;
          if (!automatic) {
            const result = await Axx.backendRequest('GET','/axx-api/status');
            const saved = await Axx.backendRequest('GET','/axx-api/providers');
            const available = (result.details?.providers || []).filter(p => p.state === 'ready_locally' && (saved.providers || []).some(s => s.name === p.name && !s.candidate_only));
            const choices = () => available.map(p => `${p.name} → ${p.model}${p.tasks?.length ? ' (' + p.tasks.join(', ') + ')' : ''}`).join('\n');
            if (command.list || !target) return 'Modo actual: ' + (c.data.prefs.selection_mode === 'automatic_free' ? 'Automático gratis · Sin claves' : c.data.prefs.apiConnection || c.data.prefs.model) + '\n' + (choices() || 'Todavía no hay conexiones disponibles.') + '\nEscribe «/modelo nombre de conexión», «cambia de modelo a ID» o «/modelo automático». Las conexiones con cuota mantienen tu autorización existente.';
            const exact = available.filter(p => normalize(p.name) === target);
            let matches = exact.length ? exact : available.filter(p => normalize(p.model) === target);
            if (!matches.length) {
              const catalog = await Axx.backendRequest('GET','/axx-api/model-candidates');
              const names = new Set((catalog.candidates || []).filter(p => normalize(p.model_id) === target).flatMap(p => (p.matched_routes || []).map(r => r.name)));
              matches = available.filter(p => names.has(p.name) && p.tasks?.includes('chat'));
            }
            if (matches.length !== 1) return (matches.length ? 'Hay varias conexiones para ese modelo. Escribe su nombre exacto.' : 'Ese modelo no tiene una conexión disponible. No cambié la selección.') + '\n' + choices();
            selected = matches[0];
            if (selected.capabilities && !selected.capabilities.includes('text') ||
                selected.tasks?.length && !selected.tasks.some(task => task === 'chat' || task === '*'))
              return 'La conexión seleccionada no declara aptitud para conversar. Conservé el modelo principal. Alternativas: ' +
                (available.filter(p => (!p.capabilities || p.capabilities.includes('text')) &&
                  (!p.tasks?.length || p.tasks.some(task => task === 'chat' || task === '*')))
                  .map(p => p.name + ' → ' + p.model).join(', ') || 'ninguna');
          }
          const before = {...c.data.prefs};
          Object.assign(c.data.prefs, {provider:'bridge', selection_mode:automatic ? 'automatic_free' : 'manual'}, selected ? {apiConnection:selected.name,model:selected.model} : {});
          $('ai-provider').value = 'bridge';
          await c.connect();
          if (!c.brain.connected || selected && c.data.prefs.model !== selected.model) {
            Object.assign(c.data.prefs,before); c.brain.reset(); c.save(); c.syncPreferences();
            return 'No se pudo conectar al modelo. Conservé la selección anterior y las tareas.';
          }
          c.save(); c.syncPreferences(); Axx.refreshVoiceModelOptions?.();
          return (automatic ? 'Automático gratis · Sin claves activado.' : `Modelo seleccionado: ${selected.model} · ${selected.name}.${selected.tasks?.length ? ' Tareas: ' + selected.tasks.join(', ') + '.' : ''}`) + ' Se usará en las siguientes inferencias. La memoria y las operaciones completadas se conservan.';
        } finally { busy = false; }
      }
    };
    const status = text => { $('provider-status').textContent = text; };
    const payload = () => ({ provider: $('provider-kind').value, name: $('provider-name').value.trim(),
      base_url: $('provider-url').value.trim(), model: ($('provider-model').value === '__manual__' ? $('provider-model-manual').value : $('provider-model').value).trim(),
      protocol: $('provider-protocol').value, api_key: $('provider-key').value.trim(),
      enabled: $('provider-enabled').checked, billing_allowed: $('provider-billing').checked,
      cost_evidence: $('provider-cost').value, route_kind: $('provider-route').value, free_confirmed: $('provider-free').checked,
      context_window: Number($('provider-context').value) || undefined, image_context_tokens: Number($('provider-image-context').value) || undefined,
      capabilities: [...$('provider-capabilities').selectedOptions].map(o => o.value), tasks: [...$('provider-tasks').selectedOptions].map(o => o.value),
      task_priority: Object.fromEntries([...$('provider-tasks').selectedOptions].map(o => [o.value, Number($('provider-priority').value)])) });
    $('provider-selection-mode').value = Axx.companion.data.prefs.selection_mode || 'automatic_free';
    const refresh = async () => {
      const selected = $('provider-saved').value || Axx.companion.data.prefs.apiConnection;
      const result = await Axx.backendRequest('GET', '/axx-api/providers');
      entries = result.providers || [];
      $('gateway-import-source').replaceChildren(...entries.filter(p=>p.kind!=='freellmapi'&&p.free_confirmed&&!p.billing_allowed).map(p=>new Option(p.name,p.name)));
      $('provider-saved').replaceChildren(new Option('Nueva conexión', ''), ...entries.map(p => new Option(p.name + ' · ' + p.model, p.name)));
      if (entries.some(p => p.name === selected)) { $('provider-saved').value = selected; $('provider-saved').onchange(); }
    };
    const checkTaskModels = async () => {
      const root = $('model-task-options'), task = $('model-task-kind').value, prefs = Axx.companion.data.prefs;
      root.replaceChildren();
      if (task === 'grounding') {
        root.textContent = 'Agent-S necesita localizar coordenadas de controles. Axx todavía no tiene un modelo de Ollama que haya superado esa prueba; una etiqueta «visión» no basta para activarlo.';
        return;
      }
      if (task === 'voice' && prefs.selection_mode !== 'manual') {
        root.textContent = 'En modo automático la voz usa el modelo que el router elija para el chat. Para fijar un modelo de voz, conecta una opción manual y selecciónalo en Voz, ritmo y privacidad.';
        return;
      }
      const [statusResult, savedResult] = await Promise.all([
        Axx.backendRequest('GET', '/axx-api/status'), Axx.backendRequest('GET', '/axx-api/providers')]);
      const saved = new Set((savedResult.providers || []).filter(p => p.enabled && !p.candidate_only).map(p => p.name));
      const requiredTask = task === 'voice' ? 'chat' : task, capability = task === 'vision' ? 'vision' : 'text';
      const ready = (statusResult.details?.providers || []).filter(p => p.state === 'ready_locally' && saved.has(p.name));
      const fits = ready.filter(p => (p.capabilities || []).includes(capability) &&
        (p.tasks || []).some(value => value === requiredTask || value === '*') &&
        (task !== 'voice' || p.name === prefs.apiConnection && Axx.companion.brain.models.includes(p.model)));
      const activeName = task === 'vision' && prefs.visionConnection ? prefs.visionConnection : prefs.apiConnection;
      const activeModel = task === 'vision' && prefs.visionModel ? prefs.visionModel : prefs.model;
      const active = ready.find(p => p.name === activeName && p.model === activeModel);
      const explanation = document.createElement('p');
      explanation.className = 'model-task-message';
      explanation.textContent = !active && prefs.selection_mode === 'manual' ? 'El modelo seleccionado no figura como listo localmente. ' :
        active && !fits.some(p => p.name === active.name && p.model === active.model) ?
          'El modelo seleccionado no declara aptitud para esta tarea. ' : '';
      explanation.textContent += fits.length ? 'Opciones declaradas disponibles; comprueba calidad y latencia con la tarea real:' :
        'No hay una conexión guardada y lista que declare esta capacidad. Consulta los modelos instalados, configura su conexión y evalúala antes de seleccionarla.';
      if (!['voice', 'vision', 'chat'].includes(task))
        explanation.textContent += ' En modo automático Axx elige una ruta para esta tarea; en manual, elegir una opción también cambia el chat.';
      root.append(explanation);
      if (task === 'vision' && prefs.visionConnection) {
        const reset = document.createElement('button'); reset.type = 'button'; reset.textContent = 'Usar ruta general para visión';
        reset.onclick = () => { prefs.visionConnection = ''; prefs.visionModel = ''; Axx.companion.save(); Axx.magicPen?.updateControls(); void checkTaskModels(); };
        root.append(reset);
      }
      for (const provider of fits) {
        const row = document.createElement('div'); row.className = 'model-task-row';
        const info = document.createElement('div'), name = document.createElement('strong'), state = document.createElement('small');
        name.textContent = provider.model; state.textContent = provider.name + ' · listo localmente';
        info.append(name, state); row.append(info);
        if (task === 'vision') {
          const choose = document.createElement('button'); choose.type = 'button'; choose.textContent = 'Usar en visión';
          choose.onclick = () => { prefs.visionConnection = provider.name; prefs.visionModel = provider.model;
            Axx.companion.save(); Axx.magicPen?.updateControls(); root.textContent = 'Modelo visual seleccionado: ' + provider.model + ' · ' + provider.name + '. Comprueba el resultado con una imagen real.'; };
          row.append(choose);
        } else if (task === 'voice') {
          const choose = document.createElement('button'); choose.type = 'button'; choose.textContent = 'Usar en voz';
          choose.onclick = async () => { root.textContent = await Axx.modelSelection.run({voice:true,target:provider.model}); };
          row.append(choose);
        } else if ((provider.capabilities || []).includes('text') &&
                   (provider.tasks || []).some(value => value === 'chat' || value === '*')) {
          const choose = document.createElement('button'); choose.type = 'button';
          choose.textContent = task === 'chat' ? 'Usar en chat' : 'Usar también como modelo principal';
          choose.onclick = async () => { root.textContent = await Axx.modelSelection.run({target:provider.name}); };
          row.append(choose);
        }
        root.append(row);
      }
    };
    $('model-task-check').onclick = async () => {
      $('model-task-options').textContent = 'Comprobando conexiones…';
      try { await checkTaskModels(); }
      catch (error) { $('model-task-options').textContent = 'No pude consultar los modelos: ' + (error.message || String(error)); }
    };
    const action = async (fn, clearKey = false) => {
      if (busy) return;
      busy = true;
      const controls = [...panel.querySelectorAll('button,input,select')].map(control => [control, control.disabled]);
      controls.forEach(([control]) => control.disabled = true);
      try { await fn(); } catch(e) { status(e.message || String(e)); }
      finally { busy = false; if (clearKey) { $('provider-key').value = ''; $('gateway-dashboard').value = ''; } controls.forEach(([control, disabled]) => control.disabled = disabled); }
    };
    const platform = () => {
      $('provider-url').value = presets[$('provider-kind').value];
      $('provider-protocol-row').hidden = $('provider-kind').value !== 'custom';
      $('provider-key').value = ''; $('provider-model').value = ''; $('provider-billing').checked = false;
      $('provider-enabled').checked = true;
      $('provider-cost').value = 'unknown'; $('provider-route').value = 'unknown'; $('provider-free').checked = false;
      $('provider-context').value = ''; $('provider-image-context').value = ''; $('provider-priority').value = 50;
      for (const option of $('provider-capabilities').options) option.selected = option.value === 'text';
      for (const option of $('provider-tasks').options) option.selected = option.value === 'chat';
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
      $('provider-cost').value = p.cost_evidence || 'unknown'; $('provider-route').value = p.route_kind || 'unknown'; $('provider-free').checked = !!p.free_confirmed;
      $('provider-context').value = p.context_window || ''; $('provider-image-context').value = p.image_context_tokens || '';
      $('provider-priority').value = p.task_priority?.chat ?? Object.values(p.task_priority || {})[0] ?? 50;
      for (const option of $('provider-capabilities').options) option.selected = (p.capabilities || []).includes(option.value);
      for (const option of $('provider-tasks').options) option.selected = (p.tasks || []).includes(option.value);
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
      c.data.prefs.selection_mode = 'manual'; $('provider-selection-mode').value = 'manual';
      c.data.prefs.apiConnection = data.name;
      $('ai-provider').value = 'bridge'; c.save();
      await c.connect();
      const selected = c.brain.connected && c.data.prefs.model === data.model;
      if (!selected) { c.brain.reset(); c.data.prefs.model = data.model; c.save(); c.syncProvider(); }
      status(selected ? 'Conexión guardada y modelo seleccionado. Ya puedes abrir el chat.' : 'Conexión guardada. Revisa la clave, la habilitación y la autorización de cuota antes de usarla.');
    }, true);
    $('provider-refresh').onclick = () => action(refresh);
    const showKeyless = result => {
      if (!result) return;
      const states = {idle:'Preparado para comprobar',preparing:'Preparando proveedores sin claves',evaluating:'Comprobando modelos',ready:'Modelos comprobados disponibles',waiting:'Sin modelos aptos por ahora',error:'No se pudo completar la comprobación',stopped:'Comprobación detenida'};
      const tested = Object.values(result.tasks || {}), count = tested.reduce((sum, task) => sum + (task.applied?.length || 0), 0);
      $('keyless-status').textContent = `${states[result.state] || result.state}${result.task ? ' · ' + result.task : ''} · ${count} preferencias verificadas. ${result.message || ''}`;
    };
    $('keyless-refresh').onclick = () => action(async () => showKeyless(await Axx.backendRequest('POST','/axx-api/keyless/start',{refresh:true})));
    let checkingKeyless = false;
    const keylessTimer = setInterval(async () => {
      if (checkingKeyless || panel.hidden || Axx.companion.data.prefs.selection_mode !== 'automatic_free' || !Axx.isNative()) return;
      checkingKeyless = true;
      try { showKeyless(await Axx.backendRequest('GET','/axx-api/keyless/status')); }
      catch(e) { $('keyless-status').textContent = e.message || 'No se pudo consultar la comprobación.'; }
      finally { checkingKeyless = false; }
    }, 2500);
    window.addEventListener('pagehide', () => clearInterval(keylessTimer));
    const refreshCandidates = async () => {
      const result=await Axx.backendRequest('GET','/axx-api/model-candidates'), root=$('model-candidates-list');root.replaceChildren();
      for(const candidate of result.candidates||[]){
        const card=document.createElement('article');card.className='setup-card';
        const title=document.createElement('strong');title.textContent=candidate.provider+' · '+candidate.model_id;
        const state=document.createElement('p');state.textContent=(candidate.matched_routes?.length?'Ruta encontrada':'Pendiente de conexión gratuita')+' · '+(candidate.pending_reason||candidate.status);
        const routes=document.createElement('p');routes.textContent=(candidate.matched_routes||[]).map(route=>route.name+' → '+(route.gateway_model_id||route.model||candidate.model_id)).join('\n');
        const task=document.createElement('select');task.setAttribute('aria-label','Tarea para evaluar '+candidate.model_id);
        const labels={chat:'Conversación',plan:'Planificación',parameters:'Parámetros',repair:'Reparación',vision:'Visión',code:'Código',writing:'Redacción',translation:'Traducción'};
        for(const name of candidate.tasks||[])task.add(new Option(labels[name]||name,name));
        const evaluate=document.createElement('button');evaluate.type='button';evaluate.textContent='Evaluar y actualizar preferencia';evaluate.disabled=!candidate.matched_routes?.length;
        evaluate.onclick=()=>action(async()=>{
          $('model-candidates-status').textContent='Evaluando '+candidate.model_id+'…';
          const body={candidate_id:candidate.id,task:task.value};
          const observed=await Axx.backendRequest('POST','/axx-api/model-candidates/evaluate',body);
          let applied=false;
          if(observed.passed&&observed.proof_mode==='actual'){await Axx.backendRequest('POST','/axx-api/model-candidates/apply',body);applied=true;}
          $('model-candidates-status').textContent=`${candidate.model_id}: ${observed.passed?'prueba correcta':observed.status==='pending'?'pendiente':'necesita corrección'} · ${Math.round(observed.latency_ms||0)} ms${applied?' · preferencia actualizada':''}. ${observed.message||observed.result_summary||''}`;
          await refreshCandidates();
        });
        card.append(title,state,routes,task,evaluate);root.append(card);
      }
    };
    $('model-candidates-refresh').onclick=()=>action(refreshCandidates);
    const gatewayBody = () => ({base_url:$('provider-url').value.trim(),name:$('provider-name').value.trim(),api_key:$('provider-key').value.trim(),dashboard_token:$('gateway-dashboard').value.trim()});
    const gatewayCall = (operation, body={}) => Axx.backendRequest('POST','/axx-api/freellmapi/'+operation,body);
    $('gateway-start').onclick = () => action(async()=>{
      const result=await gatewayCall('start'); $('provider-kind').value='freellmapi'; platform(); $('provider-url').value=result.base_url||'';
      $('gateway-controls').open=true; $('provider-name').value='FreeLLMAPI'; $('gateway-result').textContent=`Gateway ${result.connected?'conectado':'pendiente'} · ${result.ready_count||0} rutas disponibles · ${result.base_url||''}`;
    });
    $('gateway-status').onclick = () => action(async()=>{const result=await gatewayCall('status',gatewayBody());$('gateway-result').textContent=`${result.connected?'Conectado':'Sin conexión'} · ${result.ready_count||0} rutas listas · ${result.ownership==='managed'?'Administrado por Axx':'Instancia externa'} · ${result.message||result.base_url||''}`;});
    $('gateway-stop').onclick = () => action(async()=>{await gatewayCall('stop');$('gateway-result').textContent='Gateway administrado detenido. Las instancias externas siguen bajo su propio control.';});
    $('gateway-import').onclick = () => action(async()=>{await gatewayCall('import_provider',{source_name:$('gateway-import-source').value});$('gateway-result').textContent='Conexión añadida. Consulta los miembros y selecciona los que usarás.';});
    const profiles = async create => {
      const ids=[...$('gateway-members').querySelectorAll('input:checked')].map(n=>Number(n.value));
      if(create&&!ids.length)throw new Error('Marca al menos una ruta cuya gratuidad hayas confirmado.');
      const connection=gatewayBody(), result=await gatewayCall('profiles',{...connection,create,gateway_free_model_ids:ids});
      $('gateway-members').replaceChildren();
      for(const model of (result.models||[]).filter(m=>m.enabled===true&&m.contextWindow>0&&m.group_ready===true)){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.value=model.id;check.checked=ids.includes(model.id);label.append(check,document.createTextNode(` ${model.platform} · ${model.modelId} (${model.contextWindow||'?'} tokens)`));label.className='setting';$('gateway-members').append(label);}
      let saved=0;
      if(create) for(const profile of result.profiles||[]) if(profile.verified){
        await Axx.backendRequest('POST','/axx-api/providers/save',{provider:'freellmapi',...connection,...profile.provider_fields,name:'FreeLLMAPI '+profile.name,enabled:true,free_confirmed:true,billing_allowed:false,cost_evidence:'free_tier',gateway_free_model_ids:ids});saved++;
      }
      $('gateway-result').textContent=(create?`${saved} perfiles verificados y guardados. `:'')+(result.profiles||[]).map(p=>`${p.name}: ${p.verified?'listo':p.message||'pendiente de miembros'}`).join('\n');
      if(create) await refresh();
    };
    $('gateway-inspect').onclick=()=>action(()=>profiles(false));
    $('gateway-profiles').onclick=()=>action(()=>profiles(true),true);
    $('provider-selection-mode').onchange = () => action(async () => {
      const c = Axx.companion;
      c.data.prefs.selection_mode = $('provider-selection-mode').value;
      if (c.data.prefs.selection_mode === 'automatic_free') { c.data.prefs.provider = 'bridge'; $('ai-provider').value = 'bridge'; }
      c.brain.reset(); c.save(); await c.connect();
      status(c.data.prefs.selection_mode === 'automatic_free' ? 'Modo sin claves guardado. Axx está comprobando las rutas disponibles.' : 'Selección manual guardada.');
    });
    $('tab-mode-api').addEventListener('click', () => { void action(refresh); });
    $('provider-kind').value = 'ollama'; platform();
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
