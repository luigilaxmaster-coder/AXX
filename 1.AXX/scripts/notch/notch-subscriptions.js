/* Read-only provider plans. The existing Connect service owns every query. */
(function (Axx) {
  'use strict';
  const names = { codex: 'Codex', claude: 'Claude Code', antigravity: 'Antigravity' };
  function el(tag, cls, text) { const node = document.createElement(tag); node.className = cls || ''; if (text !== undefined) node.textContent = text; return node; }
  function createSurface(onOpen) {
    const root = el('section', 'notch-subscriptions'); root.setAttribute('aria-label', 'Planes de tus coding agents');
    const heading = el('div', 'notch-row-between'); const refresh = el('button', 'notch-mode-link', 'Actualizar'); refresh.type = 'button'; refresh.setAttribute('aria-label', 'Actualizar planes de los agentes');
    heading.append(el('span', 'notch-eyebrow', 'TUS CODING AGENTS'), refresh);
    const list = el('div', 'notch-provider-list'); const status = el('p', 'notch-muted notch-subscription-status'); status.setAttribute('role', 'status');
    root.append(heading, list, status);
    let data = [], at = 0, pending = false, visible = false, privacy = false, selectedProvider = 'codex';
    function render() {
      list.replaceChildren();
      if (privacy) { list.append(el('p', 'notch-muted', 'Los planes están ocultos por tu configuración de privacidad.')); return; }
      for (const provider of Object.keys(names)) {
        const row = data.find(item => item.provider === provider);
        const card = el('article', 'notch-provider-card'); card.dataset.provider = provider;
        const identity = el('button', 'notch-provider-identity'); identity.type = 'button'; identity.setAttribute('aria-label', 'Ver plan de ' + names[provider]); identity.setAttribute('aria-expanded', String(selectedProvider === provider));
        identity.addEventListener('click', () => { selectedProvider = provider; render(); root.querySelector(`[data-provider="${provider}"] .notch-provider-identity`)?.focus(); });
        const monogram = el('span', 'notch-provider-dot', ''); monogram.setAttribute('aria-hidden', 'true');
        const copy = el('div'); copy.append(el('strong', '', names[provider]), el('span', 'notch-muted', row?.plan ? `Plan ${row.plan}` : 'Plan no informado'));
        const connection = el('span', 'notch-badge-chip', !row ? pending ? 'Consultando' : 'Sin datos' : row.stale ? 'Dato anterior' : row.connection === 'connected' ? 'Conectado' : row.connection === 'reported' ? 'Estado recibido' : row.connection === 'disconnected' ? 'Sin sesión' : 'Sin sincronizar');
        identity.append(monogram, copy, connection); card.append(identity);
        card.dataset.expanded = String(selectedProvider === provider);
        if (selectedProvider !== provider) { list.append(card); continue; }
        const windows = row?.windows || [];
        if (windows.length) {
          const allowances = el('div', 'notch-provider-allowances');
          for (const win of windows) {
            const pct = win.remaining_percent; if (!Number.isFinite(pct) || pct < 0 || pct > 100) continue;
            const allowance = el('div'); const label = win.label || (win.window_minutes === 300 ? '5 horas' : win.window_minutes === 10080 ? 'Semanal' : 'Cuota del proveedor');
            const caption = el('div', 'notch-row-between'); caption.append(el('span', '', label), el('strong', '', `${pct}% disponible`));
            const meter = el('meter'); meter.min = 0; meter.max = 100; meter.value = pct; meter.setAttribute('aria-label', `${names[provider]} · ${label}`);
            allowance.append(caption, meter);
            if (win.resets_at && Number.isFinite(win.resets_at)) allowance.append(el('small', 'notch-muted', 'Reinicia ' + new Date(win.resets_at * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })));
            allowances.append(allowance);
          }
          card.append(allowances);
        } else card.append(el('p', 'notch-muted', row?.reason || (pending ? 'Comprobando el cliente oficial…' : 'No se pudo consultar el cliente. Vuelve a actualizar.')));
        const foot = el('div', 'notch-row-between');
        const checked = row?.quota_checked_at || row?.checked_at;
        foot.append(el('small', 'notch-muted', checked ? `${row.verification === 'client_report' || row.quota_source ? 'Cliente' : 'Consulta'} · ${new Date(checked * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Sin datos verificables'));
        const actions = el('div', 'notch-actions-row');
        if (provider !== 'codex') {
          const setup = el('button', 'notch-mode-link', 'Sincronizar'); setup.type = 'button'; setup.setAttribute('aria-label', `Sincronizar estado de ${names[provider]}`);
          setup.addEventListener('click', async () => {
            setup.disabled = true;
            try {
              const result = await Axx.backendRequest('GET', '/axx-api/connect/subscriptions/setup?provider=' + provider);
              card.querySelector('.notch-subscription-setup')?.remove();
              const details = el('div', 'notch-subscription-setup');
              details.append(el('p', 'notch-muted', 'Conecta la salida de estado de tu CLI para recibir el plan y el saldo aquí. Tu sesión y tus credenciales permanecen en el cliente oficial.'));
              const copy = el('button', 'notch-pill-btn', 'Copiar conexión'); copy.type = 'button';
              copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(JSON.stringify(result.configuration, null, 2)); copy.textContent = 'Conexión copiada'; } catch { status.textContent = 'Abre Configuración avanzada para copiar el bloque de conexión.'; } });
              const advanced = el('details'); advanced.append(el('summary', '', 'Configuración avanzada'), el('p', 'notch-muted', result.instructions), el('p', 'notch-muted', result.settings_file));
              const code = el('pre', '', JSON.stringify(result.configuration, null, 2)); code.tabIndex = 0;
              advanced.append(code); details.append(copy, advanced); card.append(details);
            } catch { status.textContent = 'No se pudo preparar la conexión. Vuelve a actualizar.'; }
            finally { setup.disabled = false; }
          }); actions.append(setup);
        }
        const open = el('button', 'notch-mode-link', 'Abrir chat'); open.type = 'button'; open.setAttribute('aria-label', `Abrir chat de ${names[provider]}`); open.addEventListener('click', () => onOpen(provider)); actions.append(open); foot.append(actions); card.append(foot); list.append(card);
      }
    }
    async function load() {
      if (pending || privacy) return; pending = true; refresh.disabled = true; status.textContent = 'Consultando tus clientes…';
      try {
        const results = await Promise.allSettled(Object.keys(names).map(async provider => {
          const response = await Axx.backendRequest('GET', '/axx-api/connect/subscriptions?provider=' + provider);
          if (response.provider !== provider) throw Error('Invalid subscription');
          data = [...data.filter(row => row.provider !== provider), response]; render();
          return response;
        }));
        if (results.every(result => result.status === 'rejected')) throw Error('Unavailable');
        for (let index = 0; index < results.length; index++) if (results[index].status === 'rejected') data = data.map(row => row.provider === Object.keys(names)[index] ? { ...row, stale: true } : row);
        at = Date.now(); status.textContent = 'El saldo pertenece al plan; una ventana de 5 horas no equivale a horas de conversación.';
      } catch { at = Date.now(); data = data.map(row => ({ ...row, stale: true })); status.textContent = 'No se pudo actualizar. Los últimos datos se conservan como anteriores.'; }
      finally { pending = false; refresh.disabled = false; render(); }
    }
    refresh.addEventListener('click', () => void load()); render();
    return { root, show(host, privateMode = false) { visible = true; const changed = privacy !== privateMode; privacy = privateMode; host.append(root); if (changed) render(); if (!privacy && Date.now() - at > 60000) void load(); }, hide() { visible = false; }, tick() { if (visible && Date.now() - at > 60000) void load(); } };
  }
  Axx.notchSubscriptions = { createSurface };
})(window.Axx || (window.Axx = {}));
