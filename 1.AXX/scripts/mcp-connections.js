/* Outbound MCP configuration. Secrets travel once to the private backend, never localStorage. */
(function (A) {
    'use strict';
    if (!A?.companion || A.mcpConnections) return;
    const $ = id => document.getElementById(id);
    const card = document.createElement('section');
    card.id = 'mcp-connections'; card.className = 'setup-card';
    card.innerHTML = `<h3>Conexiones MCP</h3>
      <p>Conecta aplicaciones y servicios. Primero comprueba la conexión y después revisa qué herramientas activar.</p>
      <label>Nombre<input id="mcp-name" maxlength="120" autocomplete="off" placeholder="Navegador de trabajo"></label>
      <label>Cuenta o contexto<input id="mcp-context" maxlength="120" autocomplete="off" placeholder="Perfil o espacio de trabajo"></label>
      <label>Transporte<select id="mcp-transport"><option value="streamable_http">URL MCP</option><option value="stdio">Servidor local</option></select></label>
      <div id="mcp-http-fields"><label>URL<input id="mcp-url" type="url" placeholder="http://127.0.0.1:4000/mcp" autocomplete="off"></label>
      <label>Token de esta conexión<input id="mcp-token" type="password" maxlength="8192" autocomplete="off"></label></div>
      <div id="mcp-stdio-fields" hidden><label>Ejecutable absoluto<input id="mcp-command" maxlength="240" placeholder="C:\\ruta\\servidor.exe"></label>
      <label>Argumentos como lista JSON<textarea id="mcp-args" rows="2" maxlength="16000">[]</textarea></label>
      <p>Probar iniciará este proceso local. Usa únicamente servidores que hayas revisado.</p></div>
      <div class="quick-row"><button id="mcp-add" type="button">Guardar conexión</button><button id="mcp-refresh" type="button">Actualizar estado</button></div>
      <p id="mcp-status" role="status" aria-live="polite">Sin conexiones comprobadas.</p><div id="mcp-list"></div>`;
    $('view-settings')?.append(card);
    const api = async (method, action, body) => {
        if (!A.isNative()) throw new Error('Las conexiones requieren Axx Desktop.');
        const result = await A.backendRequest(method, '/axx-api/mcp/' + action, body);
        if (result?.error) throw new Error(result.error.message || result.error);
        return result;
    };
    const status = message => { $('mcp-status').textContent = message; };
    let busy = false;
    async function task(work) {
        if (busy) return;
        busy = true;
        card.querySelectorAll('button').forEach(button => button.disabled = true);
        try { await work(); }
        catch (error) { status(error.message || 'No se pudo completar la operación MCP.'); }
        finally { busy = false; card.querySelectorAll('button').forEach(button => button.disabled = false); }
    }
    function button(label, action) {
        const element = document.createElement('button'); element.type = 'button'; element.textContent = label;
        element.onclick = () => void task(action); return element;
    }
    async function refresh() {
        const data = await api('GET', 'connections');
        const list = $('mcp-list'); list.replaceChildren();
        if (data.storage_error) { status(data.storage_error); return; }
        for (const connection of data.connections || []) {
            const section = document.createElement('section'); section.className = 'setup-card';
            const title = document.createElement('h4'); title.textContent = connection.name;
            const detail = document.createElement('p'); detail.textContent = `${connection.context} · ${connection.status} · ${connection.endpoint}`;
            section.append(title, detail);
            if (connection.diagnostic) { const note = document.createElement('p'); note.textContent = connection.diagnostic; section.append(note); }
            for (const rejected of connection.rejected_tools || []) {
                const note = document.createElement('p'); note.textContent = `${rejected.name}: ${rejected.reason}`; section.append(note);
            }
            section.append(button('Probar y descubrir', async () => { status('Comprobando servidor y catálogo…'); await api('POST', 'probe', {id:connection.id}); await refresh(); }),
                button('Desconectar', async () => { await api('POST', 'disconnect', {id:connection.id}); await refresh(); }));
            for (const tool of connection.tools || []) {
                const item = document.createElement('details'), heading = document.createElement('summary');
                heading.textContent = `${tool.title} · ${tool.enabled ? 'activada' : 'desactivada'}`;
                const description = document.createElement('p'); description.textContent = tool.description;
                const schema = document.createElement('pre'); schema.style.whiteSpace = 'pre-wrap'; schema.textContent = JSON.stringify(tool.input_schema, null, 2);
                const label = document.createElement('label'), readOnly = document.createElement('input');
                readOnly.type = 'checkbox'; readOnly.checked = tool.read_only;
                label.append(readOnly, document.createTextNode(' He revisado que esta herramienta sólo consulta datos y no modifica el sistema.'));
                const limits = document.createElement('p'); limits.textContent = 'Las descripciones proceden del servidor. Una escritura necesita comprobar su efecto; un acuse no basta. El control global del escritorio debe usar la fachada nativa de Axx.';
                item.append(heading, description, schema, label, limits,
                    button(tool.enabled ? 'Desactivar' : 'Activar herramienta revisada', async () => {
                        await api('POST', 'activate', {tool_id:tool.id, enabled:!tool.enabled, read_only:readOnly.checked});
                        await refresh();
                    }));
                section.append(item);
            }
            list.append(section);
        }
        status(`${data.connections?.length || 0} conexiones guardadas. Consulta y ejecución se comprueban por separado.`);
    }
    $('mcp-transport').onchange = () => {
        const http = $('mcp-transport').value === 'streamable_http';
        $('mcp-http-fields').hidden = !http; $('mcp-stdio-fields').hidden = http;
    };
    $('mcp-add').onclick = () => void task(async () => {
        const body = {name:$('mcp-name').value.trim(), context:$('mcp-context').value.trim(), transport:$('mcp-transport').value};
        if (body.transport === 'streamable_http') Object.assign(body, {url:$('mcp-url').value.trim(), token:$('mcp-token').value});
        else Object.assign(body, {command:$('mcp-command').value.trim(), args:JSON.parse($('mcp-args').value)});
        try { await api('POST', 'add', body); }
        finally { $('mcp-token').value = ''; delete body.token; }
        await refresh();
    });
    $('mcp-refresh').onclick = () => void task(refresh);
    A.FEATURES.push({id:'mcp', family:'settings', title:'Conexiones MCP', view:'settings',
        description:'Conecta servidores, comprueba sus herramientas y revisa cuáles activar.', availability:'REQUIERE SERVIDOR COMPROBADO'});
    const openFeature = A.companion.openFeature.bind(A.companion);
    A.companion.openFeature = id => {
        const result = openFeature(id);
        if (id === 'mcp') { card.scrollIntoView({block:'start'}); void task(refresh); }
        return result;
    };
    const open = () => { A.companion.openFeature('mcp'); A.resident?.schedule(); };
    const previous = A.companion.externalCommand;
    A.companion.externalCommand = raw => /^(?:abre |abrir |muestra )?(?:las )?(?:conexiones|servidores) mcp$/.test(A.plain(raw))
        ? async () => { open(); return 'Conexiones MCP abiertas.'; } : previous?.call(A.companion, raw) || null;
    const shortcut = button('Conexiones MCP', async () => { A.companion.openFeature('settings'); card.scrollIntoView({block:'start'}); await refresh(); });
    shortcut.id = 'mcp-settings-shortcut'; $('view-settings')?.prepend(shortcut);
    A.mcpConnections = {open, refresh};
})(window.Axx);
