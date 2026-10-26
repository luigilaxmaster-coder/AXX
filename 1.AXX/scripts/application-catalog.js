/* App profiles describe supported routes; live observations decide execution. */
(function (A) {
  'use strict';
  if (!A?.companion || !A.commandLibrary || A.applicationCatalog) return;
  const el = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
  const card = el('section'); card.id = 'application-catalog'; card.className = 'setup-card';
  card.innerHTML = `<style>#application-catalog input{width:100%;box-sizing:border-box}#application-catalog details{padding:12px 0;border-bottom:1px solid var(--line)}#application-catalog p{overflow-wrap:anywhere}#application-catalog .app-actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}</style>
    <h3>Aplicaciones y comandos</h3><p>Perfiles de uso, inventario de Windows y controles observados. Una aplicación detectada no acredita todas sus acciones.</p>
    <label>Buscar aplicación<input id="app-catalog-query" type="search" maxlength="240" placeholder="Telegram, TeamViewer, Spotify, Chrome…"></label>
    <button id="app-catalog-refresh" type="button">Consultar Windows</button><p id="app-catalog-status" role="status" aria-live="polite"></p><div id="app-catalog-list"></div>`;
  document.getElementById('view-settings')?.append(card);
  const $ = id => document.getElementById(id);
  let data = {profiles:[],applications:[]}, busy = false;
  async function run(work) {
    if (busy) return; busy = true; card.setAttribute('aria-busy', 'true');
    try { await work(); } catch (error) { $('app-catalog-status').textContent = error.message || String(error); }
    finally { busy = false; card.setAttribute('aria-busy', 'false'); A.resident?.schedule(); }
  }
  function button(title, action) { const n = el('button', title); n.type = 'button'; n.onclick = () => void run(action); return n; }
  async function prepare(id, inputs) {
    const message = await A.commandLibrary.prepare(id, inputs, 'text');
    $('app-catalog-status').textContent = message || 'Consulta el resultado en Comandos.';
    A.commandLibrary.open();
  }
  function render() {
    const list = $('app-catalog-list'), q = A.plain($('app-catalog-query').value); list.replaceChildren();
    for (const profile of data.profiles.filter(p => A.plain([p.title,...p.aliases].join(' ')).includes(q))) {
      const section = el('details'), installed = profile.installed_matches || [];
      section.append(el('summary', profile.title + ' · ' + (installed.length === 1 ? 'acceso detectado' : installed.length ? 'varios accesos; selecciona uno' : 'sin acceso detectado')));
      for (const instruction of profile.instructions) section.append(el('p', instruction));
      const actions = el('div'); actions.className = 'app-actions';
      if (installed.length === 1) actions.append(button('Abrir ' + profile.title, () => prepare('axx.app.open', {application:profile.id})));
      actions.append(button('Ventanas de ' + profile.title, () => prepare('axx.app.windows', {application:profile.id})),
        button('Inspeccionar ' + profile.title, () => prepare('axx.app.inspect', {application:profile.id})));
      section.append(actions);
      for (const command of profile.commands) {
        const row = el('details'); row.append(el('summary', command.title + ' · ' + (command.kind === 'guide' || command.requires_connection ? 'guía; requiere integración' : 'ruta disponible; efecto por verificar')));
        row.append(el('p', command.description), el('p', command.verification));
        if (command.kind !== 'guide' && !command.requires_connection) {
          let url;
          if (command.kind === 'navigate') { const label = el('label', 'URL http o https'); url = el('input'); url.type = 'url'; url.maxLength = 2048; label.append(url); row.append(label); }
          row.append(button('Preparar ' + command.title, () => prepare('axx.app.navigate', {application:profile.id,command_id:command.id,...(url ? {url:url.value.trim()} : {})})));
        }
        section.append(row);
      }
      list.append(section);
    }
    const inventory = el('details'); inventory.append(el('summary', 'Inventario completo de Windows'));
    for (const app of data.applications.filter(p => A.plain(p.name).includes(q))) {
      const row = el('p', app.name); row.append(button('Abrir ' + app.name, () => prepare('axx.desktop.installed_app', {app_id:app.app_id}))); inventory.append(row);
    }
    list.append(inventory);
  }
  async function refresh() {
    if (!A.isNative()) throw new Error('El inventario requiere Axx Desktop en Windows.');
    const result = await A.backendRequest('GET', '/axx-api/apps/catalog');
    if (result?.error) throw new Error(result.error.message || result.error);
    data = result; render();
    $('app-catalog-status').textContent = `${data.profiles.length} perfiles · ${data.applications.length} accesos observados. Las acciones mantienen sus permisos y comprobaciones.`;
  }
  $('app-catalog-query').oninput = render; $('app-catalog-refresh').onclick = () => void run(refresh);
  A.FEATURES.push({id:'applications',family:'settings',title:'Aplicaciones y comandos',view:'settings',description:'Consulta el inventario, instrucciones y acciones por aplicación.',availability:'WINDOWS · OBSERVACIÓN POR ACCIÓN'});
  const openFeature = A.companion.openFeature.bind(A.companion);
  A.companion.openFeature = id => { const result = openFeature(id); if (id === 'applications') { card.scrollIntoView({block:'start'}); void run(refresh); } return result; };
  function open() { A.companion.openFeature('applications'); }
  const isOpen = raw => /^(?:abre |abrir |muestra )?(?:el )?(?:catalogo de aplicaciones|aplicaciones y comandos)$/.test(A.plain(raw));
  const send = A.companion.send.bind(A.companion);
  A.companion.send = (text, metadata) => isOpen(text) ? (open(), Promise.resolve()) : send(text, metadata);
  const previous = A.companion.externalCommand;
  A.companion.externalCommand = raw => isOpen(raw) ? async () => { open(); return 'Catálogo de aplicaciones abierto.'; } : previous?.call(A.companion, raw) || null;
  A.applicationCatalog = {open,refresh};
})(window.Axx);
