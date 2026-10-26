/* Capability labels describe this connection, never infer modalities from a model name. */
(function (Axx) {
    'use strict';
    const style = document.createElement('style');
    style.textContent = `
      #subpanel-chatgpt,#axx-connect{min-width:0;max-width:100%;box-sizing:border-box}#axx-connect{grid-template-columns:minmax(0,1fr)}#axx-connect .setting{min-width:0}#axx-connect select{min-width:0;max-width:100%}
      .model-profile{box-sizing:border-box;min-width:0;max-width:100%;white-space:normal;margin:14px 0;padding:18px;border:1px solid var(--line,#8ca6c233);border-radius:16px;background:var(--surface-subtle,#a9c9ef08);color:var(--ink,var(--text,#e3eaf2));overflow-wrap:anywhere}
      .model-profile header{min-width:0;display:flex;align-items:start;justify-content:space-between;gap:12px}.model-profile h4{margin:3px 0 6px;font-size:18px;line-height:1.3}.model-profile p{margin:8px 0;font-size:12px;line-height:1.6;color:var(--secondary,var(--quiet,#aabaca))}
      .model-profile .model-eyebrow{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--secondary,var(--quiet,#aabaca))}.model-profile header>div{min-width:0}.model-profile .model-proof{flex-shrink:0;font-size:11px;padding:5px 8px;border:1px solid var(--line,#8ca6c233);border-radius:8px;max-width:45%}
      .model-profile .model-tags{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.model-profile .model-tag{font-size:11px;padding:5px 8px;border-radius:7px;background:var(--surface,#a9c9ef12);border:1px solid var(--line,#8ca6c233)}
      .model-profile .model-abilities{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.model-profile .model-ability{min-width:0;border:1px solid var(--line,#8ca6c233);border-radius:10px;padding:10px}.model-profile .model-ability strong{font-size:12px}.model-profile .model-ability p{font-size:11px;margin:4px 0 0}
      @media(max-width:420px){.model-profile .model-abilities{grid-template-columns:1fr}.model-profile header{flex-direction:column}.model-profile .model-proof{max-width:100%}}
    `;
    document.head.append(style);
    const text = (tag, value, className) => { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; };
    Axx.renderModelProfile = (root, model = {}) => {
        if (!root) return;
        root.replaceChildren(); root.className = 'model-profile';
        const connected = model.kind === 'chatgpt', caps = model.capabilities || [];
        const id = String(model.model || model.id || '').slice(0, 200);
        const declared = model.declared === true;
        const vision = connected ? model.input_modalities?.includes('image') : caps.includes('vision');
        const header = document.createElement('header'), heading = document.createElement('div');
        heading.append(text('span', connected ? 'ChatGPT · sesión de Codex' : model.name || 'Conexión personal', 'model-eyebrow'),
            text('h4', model.display_name || id || 'Elige un modelo'));
        header.append(heading, text('span', model.verified ? 'Respuesta comprobada' : id ? 'Pendiente de probar' : 'Sin selección', 'model-proof'));
        root.append(header);
        if (model.display_name && model.display_name !== id) root.append(text('p', id));
        if (model.description) root.append(text('p', String(model.description).slice(0, 600)));
        const tags = document.createElement('div'); tags.className = 'model-tags';
        const labels = [connected ? 'Cuota de ChatGPT' : model.kind === 'ollama' ? 'Ollama local' : 'API configurada',
            model.verified ? 'Texto probado' : caps.includes('text') || connected ? 'Texto declarado' : 'Texto por comprobar',
            vision ? 'Visión declarada' : 'Visión por comprobar', 'Voz local de Axx',
            model.executor_ready === true ? 'Ejecutor disponible' : 'Ejecutor por comprobar'];
        for (const label of labels) tags.append(text('span', label, 'model-tag'));
        root.append(tags);
        if (connected && Array.isArray(model.reasoning_efforts) && model.reasoning_efforts.length) {
            const modes=model.reasoning_efforts.map(r=>r.reasoningEffort).filter(r=>typeof r==='string');
            if (modes.length) root.append(text('p','Razonamiento disponible según el catálogo: '+modes.join(' · ')+'.'));
        }
        const abilities = document.createElement('div'); abilities.className = 'model-abilities';
        for (const [title, detail] of [
            ['Conversar', 'Respuestas progresivas; el historial y el estilo se conservan en Axx.'],
            ['Actuar en la PC', connected ? 'Consulta herramientas Axx y ejecuta las disponibles. Las acciones con aprobación muestran su tarjeta.' : 'Comandos directos de Axx. Los planes nuevos requieren una ruta apta para planificación.'],
            ['Hablar contigo', 'Micrófono → transcripción local → modelo → voz local. El timbre depende de la voz elegida.'],
            ['Ver imágenes', vision ? connected ? 'El modelo declara imágenes; esta conexión de Axx envía texto. Usa una ruta visual en Visión para adjuntarlas.' : 'La conexión declara imágenes. Comprueba el resultado con una imagen real.' : 'No hay prueba de visión en esta selección. Elige una conexión visual comprobada para analizar imágenes.']
        ]) {
            const cell = document.createElement('div'); cell.className = 'model-ability'; cell.append(text('strong', title), text('p', detail)); abilities.append(cell);
        }
        root.append(abilities);
        if (!connected && declared) root.append(text('p', 'Tareas declaradas: ' + (model.tasks || []).join(', ') + '. Declaración y calidad comprobada se evalúan por separado.'));
        root.append(text('p', connected ? 'Esta conexión no incluye el audio del modo Voz de ChatGPT ni habilita Realtime. La voz usa los motores locales de Axx; su latencia se mide en cada turno.' : 'La capacidad del modelo y las herramientas instaladas son distintas. Un catálogo no demuestra velocidad ni ejecución correcta.'));
    };
})(window.Axx = window.Axx || {});
