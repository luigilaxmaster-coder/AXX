/* Command catalog for the existing Axx UI. Recognition is data; only typed IDs reach the executor. */
(function installCommandLibrary(Axx) {
    'use strict';
    if (!Axx?.companion || Axx.commandLibrary) return;
    const node = id => document.getElementById(id);
    const errorText = error => typeof error === 'string' ? error : error?.message || error?.code || 'No se pudo completar el comando.';
    const requestWords = raw => {
        let text = String(raw).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/^[¡¿\s]+/,'');
        for (let i=0;i<6;i++) {
            const next = text.replace(/^(?:(?:(?:oye|hola|hey|ok|ey|escucha)[,\s]+)?axx\b[\s,.:!-]*|(?:oye|hola|hey)[,\s]+|por favor[,\s]+|(?:(?:me|nos)\s+)?(?:puedes|podrias|podias)[,:\s]+|(?:quiero|necesito|quisiera|me gustaria)\s+que\s+(?:me\s+)?|pero\s+)/,'').replace(/^[¿¡ ,]+/,'');
            if (next === text) break;
            text = next;
        }
        return text.replace(/^(?:quiero|necesito|quisiera|me gustaria)\s+(?=abrir|iniciar|cerrar|buscar|escuchar|reproducir|mover|leer|pulsar)/,'').replace(/[.!?]+$/,'').replace(/\s+por favor$/,'').trim();
    };
    class CommandLibrary {
        generation = 0; searchGeneration = 0; observationRevision = 0; cancellingGeneration = null; busy = false; operation = null; pendingOperationId = null; commands = []; voiceDraft = null; actionContext = {};
        constructor() {
            this.installControls();
            this.installDispatch();
            this.connectExistingActions();
            this.markVoiceProvenance();
            if (Axx.isNative() && !Axx.desktop) void Axx.app.bridge.listen('axx-cancel', () => { void this.cancel(); });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape' && (this.busy || this.operation)) void this.cancel();
            }, true);
        }
        status(text) {
            node('command-library-status').textContent = text;
            const rtStatus = node('desktop-runtime-status');
            if (rtStatus && Axx.desktop) rtStatus.textContent = text;
        }
        notice(text, conversationId) {
            // Results remain in their persisted operation card if the user moved
            // to another chat. Never copy or speak one chat's output in another.
            if (conversationId && Axx.chatWorkspace?.active?.id !== conversationId) return;
            Axx.companion.localNotice(text);
        }
        report(error) { this.status((this.operation ? 'Resultado incierto: ' : '') + errorText(error) + (this.operation ? ' Consulta el resultado antes de reintentar.' : '')); }
        async request(method, path, body) {
            const result = await Axx.backendRequest(method, path, body);
            if (!result || typeof result !== 'object') throw new Error('Respuesta de la biblioteca no válida.');
            if (result.error && !result.state) throw new Error(errorText(result.error));
            return result;
        }
        installControls() {
            const section = document.createElement('section');
            section.id = 'command-library'; section.className = 'setup-card';
            section.innerHTML = `<strong>Biblioteca de comandos</strong>
              <style>
                #command-library-approval{border:1px solid #98bce870;border-radius:12px;padding:14px;margin:12px 0;background:#91b6ec0d}
                #command-library-approval h3{font-size:15px;margin:0 0 8px;color:var(--text,#eef1f7)}
                #command-library-approval p,#command-library-approval li{font-size:12px;line-height:1.6;color:var(--text,#eef1f7)}
                #command-library-preview{padding-left:22px;margin:12px 0;overflow-wrap:anywhere}
                #command-library-preview li{padding:8px 0;border-bottom:1px solid #ffffff18}
                #command-library-preview strong{font-size:12px;color:inherit}
                #command-library-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:150px;overflow:auto;font:12px/1.6 ui-monospace,monospace;margin:4px 0}
                #command-library-approve{width:100%;min-height:44px;background:#cbdcf5;color:#142338;font-weight:600;margin-top:12px}
                #command-library-approve:disabled{opacity:.5}
                #command-library-approval-actions{display:flex;align-items:stretch;gap:8px;margin-top:12px}
                #command-library-approval-actions button{margin-top:0;min-height:44px}
                #command-library-approval-actions #command-library-cancel{flex-shrink:0}
                #command-library-approval summary{cursor:pointer;font-size:12px;margin-top:12px}
                #command-library-controls{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
                #command-library-controls button{min-height:40px}
                #command-library-approval :focus-visible{outline:2px solid #b9d6ff;outline-offset:3px}
              </style>
              <section id="command-library-approval" hidden aria-labelledby="command-library-approval-title">
                <h3 id="command-library-approval-title">Revisa lo que hará Axx</h3>
                <p id="command-library-approval-summary"></p><ol id="command-library-preview"></ol>
                <p>Apruebas solo los pasos pendientes y los datos mostrados. Cancelar no deshace pasos ya completados.</p>
                <details id="command-library-technical"><summary>Ver comandos y parámetros exactos</summary><pre id="command-library-raw" style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto"></pre></details>
                <div id="command-library-approval-actions"><button id="command-library-approve" type="button">Aprobar y ejecutar</button></div>
              </section>
              <div id="command-library-controls"><button id="command-library-cancel" type="button" disabled>Cancelar tarea</button><button id="command-library-recover" type="button" disabled>Consultar resultado</button><button id="command-library-remember" type="button" hidden>Guardar procedimiento verificado</button></div>
              <p id="command-library-status" role="status">${Axx.isNative() ? 'Lista para consultar el backend de Axx.' : 'El catálogo ejecutable requiere Axx para Windows. Puedes seguir usando las herramientas locales.'}</p>
              <p>Busca una acción y revisa sus parámetros. Las recetas documentadas permanecen bloqueadas hasta disponer de un adaptador validado.</p>
              <p id="command-library-counts">Consulta el catálogo para ver su disponibilidad.</p>
              <button id="command-library-learned" type="button">Mis acciones aprendidas</button><div id="command-library-learned-list"></div>
              <form id="command-library-search-form"><label class="setting">Buscar por nombre o ID<input class="field" id="command-library-query" type="search" maxlength="200" placeholder="Ej. estado del sistema"></label><button id="command-library-search" type="submit">Buscar comandos</button></form>
              <label class="setting">Comandos<select class="field" id="command-library-select"><option value="">Busca para consultar el catálogo</option></select></label>
              <div class="quick-row"><button id="command-library-prev" type="button" disabled>Anterior</button><span id="command-library-page" role="status"></span><button id="command-library-next" type="button" disabled>Siguiente</button></div>
              <p id="command-library-description"></p><p id="command-library-availability"></p>
              <details id="command-library-procedure" hidden><summary>Ver instrucciones, requisitos y comprobaciones</summary><div id="command-library-steps" style="max-height:340px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere"></div></details>
              <form id="command-library-parameters"><div id="command-library-fields"></div><button id="command-library-prepare" type="submit" disabled>Preparar comando</button></form>
              <details><summary>Detalles del resultado</summary><pre id="command-library-result" style="white-space:pre-wrap;word-break:break-word;max-height:280px;overflow:auto"></pre></details>
              <p>Desde el chat: «abre Spotify», «pausa Spotify», «abre Obsidian», «pulsa Nueva nota en Obsidian» o «escribe en Obsidian: hola». Para que el modelo prepare CMD, pide «usa CMD para mostrar mi IP» y revisa el código antes de aprobar. También puedes usar «/cmd dir» o dictar «ejecuta en CMD: dir». PowerShell requiere escribir «/powershell Get-Date». Los comandos pueden modificar tu equipo, se detienen a los 30 segundos y Escape cancela la ejecución. «/comandos texto» busca acciones.</p>`;
            node('view-files').prepend(section);
            node('command-library-search-form').onsubmit = event => { event.preventDefault(); void this.search().catch(e => this.status(errorText(e))); };
            node('command-library-select').onchange = () => this.renderSelection();
            node('command-library-prev').onclick=()=>void this.search(undefined,Math.max(0,(this.offset||0)-30)).catch(e=>this.report(e));
            node('command-library-next').onclick=()=>void this.search(undefined,(this.offset||0)+30).catch(e=>this.report(e));
            node('command-library-parameters').onsubmit = event => { event.preventDefault(); void this.fromSelection().catch(e => this.report(e)); };
            node('command-library-approve').onclick = () => { void this.approve().catch(e => this.report(e)); };
            node('command-library-remember').onclick = () => {
                const operation = this.lastOperation;
                if (!operation || this.busy || this.operation) return;
                node('command-library-remember').disabled = true;
                void this.request('POST','/axx-api/learning/remember',{operation_id:operation.operation_id})
                    .then(() => this.status('Procedimiento parametrizado guardado. Está disponible en Habilidades; cada repetición vuelve a resolver ventana y controles.'))
                    .catch(e => this.report(e)).finally(() => {node('command-library-remember').disabled = false;});
            };
            node('command-library-cancel').onclick = () => { void this.cancel(); };
            node('command-library-recover').onclick = () => { void this.recover().catch(e => this.status(errorText(e))); };
            node('command-library-learned').onclick = () => { void this.listLearned().catch(e => this.report(e)); };
            if (!Axx.isNative()) node('command-library-search').disabled = true;
            this.commands = [
                { id: 'axx.system.telemetry', title: 'Estado del sistema (CPU, RAM, disco)', description: 'Consulta métricas verificadas de CPU, memoria y disco local.', execution_enabled: true, validation_level: 'IMPLEMENTADO_LOCAL', parameters: {} },
                { id: 'axx.process.inspect', title: 'Inspeccionar proceso de Windows', description: 'Inspecciona el proceso indicado por PID (o el proceso actual de Axx).', execution_enabled: true, validation_level: 'IMPLEMENTADO_LOCAL', parameters: { pid: { type: 'integer', required: false, minimum: 1 } } },
                { id: 'axx.artifact.write', title: 'Crear archivo verificado en Axx/artifacts', description: 'Escribe un archivo de texto dentro de la carpeta aislada Axx/artifacts y verifica su SHA-256.', execution_enabled: true, validation_level: 'IMPLEMENTADO_CON_APROBACION', parameters: { path: { type: 'string', required: true, maxLength: 240 }, content: { type: 'string', required: true, maxLength: 65536 } } }
            ];
            const select = node('command-library-select');
            if (select) {
                select.replaceChildren();
                for (const command of this.commands) {
                    const option = document.createElement('option');
                    option.value = command.id;
                    option.textContent = `${command.title} · Habilitado · ${command.id}`;
                    select.append(option);
                }
                this.renderSelection();
            }
            const link = document.createElement('button'); link.id = 'command-library-open'; link.className = 'wide-button'; link.textContent = 'Abrir biblioteca de comandos';
            link.onclick = () => { this.open(); void this.search().catch(e => this.status(errorText(e))); };
            node('desktop-runtime')?.prepend(link);
        }
        open() { Axx.companion.openFeature(document.getElementById('view-commands') ? 'commands' : 'files'); node(this.operation?.state === 'awaiting_approval' ? 'command-library-approval' : 'command-library').scrollIntoView({ block: 'start' }); Axx.resident?.schedule(); }
        connectExistingActions() {
            if (!Axx.desktop) return;
            const ids = { system_telemetry: 'axx.system.telemetry', process_state_inspector: 'axx.process.inspect', file_artifact_writer: 'axx.artifact.write' };
            Axx.desktop.execute = async (toolName, inputs) => {
                if (!ids[toolName]) throw new Error('Este adaptador está pendiente de validación. Consulta la biblioteca.');
                await this.prepare(ids[toolName], inputs, 'text');
            };
            Axx.desktop.executeRecipe = async () => {
                const intent = node('desktop-recipes').value;
                if (!intent) throw new Error('Selecciona un procedimiento guardado.');
                const catalog = await this.request('GET', '/axx-api/recipes');
                const recipe = catalog.recipes?.find(item => item.intent_key === intent);
                if (!recipe?.schema || typeof recipe.schema !== 'object' || Array.isArray(recipe.schema)) throw new Error('La receta no expone un esquema de parámetros válido.');
                const known = { path: node('desktop-artifact-name').value.trim(), content: node('desktop-artifact-content').value }, inputs = {};
                for (const name of Object.keys(recipe.schema)) {
                    if (!Object.hasOwn(known, name)) throw new Error('Este procedimiento necesita parámetros que todavía no ofrece este panel: ' + name + '.');
                    inputs[name] = known[name];
                }
                await this.prepareRequest('/axx-api/recipes/prepare', { intent_key: intent, inputs });
            };
            const cancel = Axx.desktop.cancel.bind(Axx.desktop);
            Axx.desktop.cancel = () => { void this.cancel(); cancel(); };
            const blender = node('desktop-blender');
            if (blender) { blender.disabled = true; blender.textContent = 'Blender · pendiente de validación'; blender.title = 'El adaptador no está habilitado en la biblioteca hasta completar su validación física.'; }
        }
        async search(query = node('command-library-query').value.trim(), offset = 0) {
            const serial = ++this.searchGeneration;
            node('command-library-query').value = query;
            this.status('Consultando disponibilidad de los comandos.');
            const result = await this.request('GET', '/axx-api/commands?q=' + encodeURIComponent(query) + '&limit=30&offset='+offset);
            if (serial !== this.searchGeneration) return;
            if (!Array.isArray(result.commands)) throw new Error('El backend no devolvió un catálogo válido.');
            this.commands = result.commands;
            this.offset=offset;node('command-library-prev').disabled=offset===0;node('command-library-next').disabled=offset+this.commands.length>=result.matched;
            node('command-library-page').textContent=result.matched?`${offset+1}–${offset+this.commands.length} de ${result.matched}`:'Sin resultados';
            const select = node('command-library-select'); select.replaceChildren();
            for (const command of this.commands) {
                const option = document.createElement('option'); option.value = command.id;
                option.textContent = `${command.title || command.id} · ${command.execution_enabled ? 'Habilitado' : 'Bloqueado'} · ${command.id}`;
                select.append(option);
            }
            const counts = result.counts || {};
            node('command-library-counts').textContent = `Importadas: ${counts.imported ?? 'sin dato'} · Habilitadas: ${counts.enabled ?? 'sin dato'} · Bloqueadas: ${counts.blocked ?? 'sin dato'} · Operaciones verificadas: ${counts.verified_operations ?? 0}.`;
            if (result.procedure_count) node('command-library-counts').textContent += ` Instrucciones completas: ${result.procedure_count}.`;
            this.renderSelection(); this.status(this.commands.length ? 'Selecciona un comando para revisar sus condiciones. Usa Siguiente para recorrer el catálogo.' : 'No se encontraron comandos. Prueba otro nombre o ID.');
        }
        renderSelection() {
            const command = this.commands.find(item => item.id === node('command-library-select').value);
            const fields = node('command-library-fields'); fields.replaceChildren();
            node('command-library-procedure').hidden = !command?.has_recipe_details;
            node('command-library-steps').replaceChildren();
            if (command?.has_recipe_details) void this.loadProcedure(command.id);
            node('command-library-description').textContent = command?.description || '';
            node('command-library-availability').textContent = command ? `${command.execution_enabled ? 'Habilitado' : 'Bloqueado: ' + (command.blocked_reason || 'Sin adaptador ejecutable validado')}. ${command.validation_level || command.source_status || ''}` : '';
            node('command-library-prepare').disabled = !Axx.isNative() || !command?.execution_enabled || this.busy || !!this.operation;
            if (!command) return;
            if (command.delivery) {
                const label = document.createElement('label'); label.className = 'setting'; label.textContent = 'Entorno de ejecución';
                const field = document.createElement('select'); field.className = 'field'; field.id = 'command-delivery-mode';
                for (const [mode, title] of Object.entries({background:'Segundo plano · sin entrada global',foreground:'Escritorio activo · puede usar foco',isolated:'Escritorio aislado'})) {
                    const option = document.createElement('option'); option.value = mode;
                    option.disabled = !command.delivery.supported_modes.includes(mode);
                    option.textContent = title + (option.disabled ? ' · no disponible' : ''); field.append(option);
                }
                field.value = command.delivery.default_mode; label.append(field); fields.append(label);
            }
            for (const [name, schema] of Object.entries(command.parameters || {})) {
                const label = document.createElement('label'); label.className = 'setting'; label.textContent = name + (schema.required ? ' · obligatorio' : ' · opcional');
                const field = document.createElement(Array.isArray(schema.enum) ? 'select' : ['array','object'].includes(schema.type) || ['content', 'script'].includes(name) ? 'textarea' : 'input');
                field.className = 'field'; field.name = name; field.dataset.parameterType = schema.type || 'string';
                if (schema.type === 'boolean') { field.type = 'checkbox'; field.required = false; }
                else if (schema.type === 'integer' || schema.type === 'number') { field.type = 'number'; field.step = schema.type === 'integer' ? '1' : 'any'; }
                else if (field.tagName === 'INPUT') field.type = 'text';
                field.required = schema.type !== 'boolean' && !!schema.required;
                if (schema.maxLength) field.maxLength = schema.maxLength;
                if (schema.minimum !== undefined) field.min = String(schema.minimum);
                if (schema.maximum !== undefined) field.max = String(schema.maximum);
                if (Array.isArray(schema.enum)) for (const value of schema.enum) { const option = document.createElement('option'); option.value = String(value); option.textContent = String(value); field.append(option); }
                if (schema.default !== undefined) { if (schema.type === 'boolean') field.checked = schema.default === true; else field.value = String(schema.default); }
                label.append(field); fields.append(label);
            }
            Axx.resident?.schedule();
        }
        async loadProcedure(id) {
            const container = node('command-library-steps');
            container.textContent = 'Cargando procedimiento…';
            try {
                const result = await this.request('GET', '/axx-api/commands/details?id=' + encodeURIComponent(id));
                if (node('command-library-select').value !== id) return;
                container.replaceChildren();
                const recipe = result.procedure?.recipe;
                if (!recipe) { container.textContent = 'No hay instrucciones completas para este registro.'; return; }
                const sections = { platform:'Plataforma', prerequisites:'Requisitos', inputs:'Datos necesarios', permission:'Permisos', permission_risk:'Permisos y alcance', steps:'Pasos', commands:'Comandos documentados (no ejecutados)', success_evidence:'Cómo comprobar el resultado', errors_recovery:'Errores y recuperación', rollback:'Cómo deshacer', sources:'Fuentes' };
                for (const [key, title] of Object.entries(sections)) {
                    if (!recipe[key] || Array.isArray(recipe[key]) && !recipe[key].length) continue;
                    const heading = document.createElement('strong'); heading.textContent = title;
                    const body = document.createElement('p');
                    body.textContent = typeof recipe[key] === 'string' ? recipe[key] : Array.isArray(recipe[key])
                        ? recipe[key].map((step, index) => `${index + 1}. ${typeof step === 'string' ? step : step.action || step.command || JSON.stringify(step, null, 2)}`).join('\n\n')
                        : JSON.stringify(recipe[key], null, 2);
                    container.append(heading, body);
                }
                const source = document.createElement('p'); source.textContent = 'Origen: ' + result.procedure.source_member;
                container.append(source);
            } catch (error) { if (node('command-library-select').value === id) container.textContent = errorText(error); }
        }
        typedInputs() {
            const values = {};
            for (const field of node('command-library-fields').querySelectorAll('[name]')) {
                if (field.dataset.parameterType === 'boolean') { values[field.name] = field.checked; continue; }
                if (!field.value && !field.required) continue;
                if (['number', 'integer'].includes(field.dataset.parameterType)) {
                    const value = Number(field.value);
                    if (!field.value || !Number.isFinite(value) || field.dataset.parameterType === 'integer' && !Number.isInteger(value)) throw new Error('Revisa el número de ' + field.name + '.');
                    values[field.name] = value;
                } else if (['array','object'].includes(field.dataset.parameterType)) {
                    try { values[field.name] = JSON.parse(field.value); }
                    catch { throw new Error('Revisa el JSON de ' + field.name + '.'); }
                    if (field.dataset.parameterType === 'array' ? !Array.isArray(values[field.name]) : !values[field.name] || typeof values[field.name] !== 'object' || Array.isArray(values[field.name])) throw new Error('Tipo JSON incorrecto en ' + field.name + '.');
                } else values[field.name] = field.value;
            }
            return values;
        }
        async fromSelection() {
            const command = this.commands.find(item => item.id === node('command-library-select').value);
            if (!command?.execution_enabled) throw new Error('Este comando no tiene un adaptador habilitado.');
            return this.prepare(command.id, this.typedInputs(), 'text', node('command-delivery-mode')?.value);
        }
        isActionRequest(raw) {
            const text=requestWords(raw)
                .replace(/^(?:en|and)\s+(?:(?:google\s+)?chrome|crom|youtube|you tube|yutube|google|gugle|bing|duckduckgo|spotify)[,.:]?\s+(?:busca|buscar|buscame|bosca|vusca|encuentra|encontrar|localiza)\b/,'busca');
            if (/^(?:habre|avre|lanza|lanzar|arranca|iniciar|cerrarme|cierres|buscarme|busques|bosca|vusca|escucha|reproduzcas|reprogoce|reprodose|mover|moverme|mueveme|muevas|colocar|colocame|pulsar|pulses|enfoques|leeme|leas)\b/.test(text)) return true;
            return /^(?:\/(?:search|buscar|comando|powershell|cmd)\b|en\s+(?:google\s+)?chrome\s+busca\b|mis\s+ventanas\b|(?:lista|muestra)\s+(?:mis\s+)?(?:ventanas|aplicaciones)\b|(?:haz|repite|usa|saca|abre|abrir|abrirme|abras|abreme|abrela|abrelo|cierra|cerrar|cierrame|salir|inicia|ejecuta|busca|buscar|buscame|encuentra|localiza|observa|inspecciona|lee|leer|enfoca|enfocar|ponme|pon|reproduce|reproducir|escuchar|prepara|organiza|crea|crear|convierte|mueve|pulsa|presiona|clic|teclea|pega|selecciona|desplaza|navega|copia|renombra|comprime|extrae|descarga|instala|borra|elimina|envia|publica)\b|escribe\s+(?:en|dentro\s+de)\b)/.test(text);
        }
        internalAction(raw) {
            const plain = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
            const text = requestWords(raw).replace(/^(?:pon|ponme|deja) spotify en pausa$/,'pausa spotify');
            const spotify = text.match(/^(reproduce|reproducir|escucha|escuchar|pon|ponme|reanuda|reanudes|continua|sigue|pausa|pausar|pauses|deten|detener|para|siguiente|anterior)(?: (?:la |el )?(?:musica|cancion|tema|reproduccion))?(?: (?:de|en))?(?: (?:mi|el))? spotify$/);
            if (spotify) return {id:'music',verb:/^(pausa|pausar|pauses|deten|detener|para)$/.test(spotify[1])?'pause':spotify[1]==='siguiente'?'next':spotify[1]==='anterior'?'previous':'start',app:'spotify'};
            const aliases = {
                chat:'chat', conversacion:'chat', dictar:'dictation', dictado:'dictation', microfono:'dictation',
                grabar:'screen', grabadora:'screen', grabacion:'screen', 'grabar pantalla':'screen', pantalla:'screen',
                musica:'music', reproductor:'music', lector:'reader', lectura:'reader', cronometro:'stopwatch',
                temporizador:'timer', notas:'notes', tareas:'todos', calculadora:'calculator', unidades:'calculator',
                biblioteca:'files', archivos:'files', comandos:'commands', ajustes:'settings', configuracion:'settings',
                apariencia:'appearance', formas:'appearance', colores:'appearance', estudio:'studio', sonido:'sound', audio:'audio',
                ayuda:'help', actividad:'inbox', ia:'ai', modelos:'ai', 'conectar ia':'ai', subtitulos:'transcript',
                traduccion:'translation', traducir:'translation', imagenes:'images', 'editor de imagenes':'images',
                'taller de texto':'textstudio', concentracion:'focus', alcance:'reach'
            };
            const featureId = value => {
                const name = value.replace(/^(?:el|la|los|las|un|una)\s+/, '').replace(/^(?:apartado|panel|funcion) (?:de )?/, '').replace(/ de axx$/, '');
                return aliases[name] || Axx.FEATURES?.find(f => plain(f.title).replace(/^(?:el|la|los|las|un|una)\s+/, '') === name || plain(f.id) === name)?.id;
            };
            let match = text.match(/^(?:abre|abrir|abrirme|abreme|abras|muestra|muestrame|mostrar|ver|ve a|entra en) (.+)$/);
            if (match) { const id = featureId(match[1]); return id ? { id, verb:'open' } : null; }
            if (/^(?:dicta|dictar|empieza a dictar|comienza a dictar)$/.test(text)) return {id:'dictation',verb:'start'};
            if (/^(?:graba|grabar|grabr|empieza a grabar|comienza a grabar)(?: (?:la )?pantalla)?$/.test(text)) return {id:'screen',verb:'start'};
            match = text.match(/^(inicia|iniciar|empieza|comienza|activa|activar|pon|reproduce|reanuda|continuar|continua|sigue|pausa|pausar|deten|detener|para|termina|finaliza|cancela) (.+)$/);
            if (!match) return null;
            const id = featureId(match[2]);
            if (!['dictation','screen','music','reader','stopwatch','timer'].includes(id)) return id && /^(inicia|iniciar|activa|activar)$/.test(match[1]) ? {id,verb:'open'} : null;
            const verb = /^(pausa|pausar)$/.test(match[1]) ? 'pause' : /^(deten|detener|para|termina|finaliza|cancela)$/.test(match[1]) ? 'stop' : 'start';
            return {id,verb};
        }
        async runInternal({id,verb,app,source='text'}) {
            const actions = Axx.actions, voice = Axx.voice13;
            const feature = Axx.FEATURES?.find(f => f.id === id);
            if (!feature) throw new Error('Esta función no está disponible en esta versión de Axx.');
            Axx.home18?.wake();
            Axx.app.setVisible?.(true);
            if (verb === 'open') {
                if (id === 'dictation') voice.enter();
                else if (['screen','music','reader','stopwatch','timer'].includes(id)) actions.open(id);
                else if (Axx.flow) Axx.flow.select(id);
                else Axx.companion.openFeature(id);
                return 'Abierto: ' + feature.title + '.';
            }
            if (id === 'dictation') {
                if (verb === 'start') {
                    voice.enter();
                    if (!voice.target || !voice.usable(voice.target.field) || !voice.target.field.getClientRects().length) voice.openFields();
                    await voice.begin();
                }
                else voice.pause(true);
                if (voice.error) throw new Error(voice.error);
                if (voice.permit) return 'Activa el permiso de micrófono en Dictar para comenzar.';
                return voice.status === 'listening' ? 'Dictado escuchando.' : voice.status === 'starting' ? 'Iniciando el micrófono…' : voice.status === 'stopping' ? 'Terminando la transcripción…' : voice.notice || 'Dictado detenido. El texto se conserva.';
            }
            // Controls select without reopening the chat or resetting the active controller.
            actions.select(id);
            if (id === 'screen') {
                const screen = actions.screen;
                if (verb === 'stop') await screen.stop();
                else if (verb === 'pause' && screen.state === 'running' || verb === 'start' && screen.state === 'paused') await screen.toggle();
                else if (verb === 'start' && !screen.active) { actions.open(id); actions.record(); }
                if (screen.error) throw new Error(screen.error);
                const states = {running:'Grabando pantalla.',paused:'Grabación pausada.',requesting:'Selecciona el área de pantalla para grabar.',countdown:'Cuenta atrás para comenzar la grabación.',stopping:'Finalizando y guardando la grabación…',finished:'Grabación finalizada.',ready:'No hay una grabación activa.'};
                return states[screen.state] || 'Consulta el estado de la grabación en sus controles.';
            }
            if (id === 'music' && app === 'spotify' && !Axx.nativeMusic) {
                if (verb === 'start') return this.prepare('axx.desktop.spotify.play',{},source);
                throw new Error('El control multimedia de Windows no está disponible.');
            }
            if (id === 'music' && Axx.nativeMusic && (app === 'spotify' || Axx.media16?.source === 'system')) {
                const music = Axx.nativeMusic;
                await music.refresh();
                let before;
                if (app === 'spotify') {
                    const sessions=(music.snapshot.sessions||[]).filter(item=>/spotify/i.test(item.app||''));
                    if (!sessions.length && verb === 'start') return this.prepare('axx.desktop.spotify.play',{},source);
                    if (sessions.length !== 1) throw new Error(sessions.length?'Hay varias sesiones de Spotify. Elige una en Música.':'Spotify no expone una sesión multimedia controlable ahora. Abre una canción en Spotify y vuelve a intentarlo.');
                    music.selectedId=sessions[0].id;
                    before=sessions[0];
                }
                if (!music.target()) { actions.open(id); return 'No hay un reproductor con controles de Windows disponible.'; }
                await music.command(verb === 'start' ? 'play' : verb === 'next' ? 'next' : verb === 'previous' ? 'previous' : 'pause');
                if (music.error || music.readError) throw new Error(music.error || music.readError);
                const after=music.target();
                if (verb === 'next' || verb === 'previous') return after?.title && after.title !== before?.title ? 'Pista actual: ' + after.title + '.' : 'Se envió el cambio de pista, pero Spotify no confirmó otra canción.';
                return after?.playing === (verb === 'start') ? (verb === 'start' ? 'Reproducción en curso.' : 'Reproducción pausada.') : 'Se envió el control, pero Spotify no confirmó el estado.';
            }
            if (id === 'reader') {
                const reader = Axx.symbiosis.reader;
                if (verb === 'stop') reader.stop();
                else if (verb === 'pause') reader.pause();
                else if (!reader.chunks.length) { actions.open(id); return 'Añade el texto que quieres escuchar en el lector.'; }
                else Axx.symbiosis.startReader();
            } else {
                const phase = actions.phase(id);
                if (verb === 'stop') actions.stop();
                else if (verb === 'pause' && phase === 'running' || verb === 'start' && !['running','requesting'].includes(phase)) actions.primary();
            }
            const labels = {running:'en curso',paused:'en pausa',requesting:'iniciando',ready:'listo',finished:'finalizado',empty:'sin contenido',error:'con un error; revisa sus controles'};
            return feature.title + ': ' + (labels[actions.phase(id)] || 'consulta sus controles') + '.';
        }
        hasLocalIntent(raw) {
            if (this.internalAction(raw)) return true;
            if (/^(?:(?:en|and)\s+(?:google\s+)?chrome[,.]?\s+(?:busca|bosca)|busca\s+en\s+(?:google\s+)?chrome)\b/i.test(raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim())) return false;
            // Real local intents (notes, timers, tasks) precede the broad desktop verbs.
            try { if (Axx.parseIntent?.(raw)) return true; }
            catch { return true; } // Let the local tool display its own input error.
            const local = raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
            if (/^(?:(?:pon|poner)\s+(?:(?:el|la)\s+)?(?:forma|paleta|color)\s+.+|pon musica|reproduce musica|inicia la musica)$/.test(local) && Axx.isLocalExternalCommand?.(raw)) return true;
            if(this.isActionRequest(raw))return false;
            // The legacy reach tray treats any "abre ..." as its own resource.
            // Route supported desktop requests to the backend before that catch-all.
            // This only selects the resolver; it never authorizes or executes an action.
            const command = raw.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
                .replace(/^[¡¿\s]+/, '').replace(/^(?:(?:oye|hola)\s+)?axx[,\s]+/, '')
                .replace(/^por favor[,\s]+/, '').replace(/^(?:puedes|podrias|quiero que)\s+/, '')
                .replace(/\s+por favor[?.!]*$/, '').trim();
            if (/^(?:\/powershell\s|ejecuta\s+en\s+powershell:)/.test(command)
                || /^(?:abre|abrir|abras|abreme|inicia|ejecuta)\s+(?:(?:el|la)\s+)?(?:youtube|google|gmail|github|chatgpt|spotify|calculadora|calc|bloc de notas|notepad|paint|explorador(?: de archivos)?)[.!?]*$/.test(command)
                || /^(?:abre|abrir|abras|abreme)\s+(?:https?:\/\/|(?:[\w-]+\.)+[a-z]{2,}(?:[/?#:]|$))/.test(command)
                || /^(?:busca|buscar|buscame)\s+(?:en\s+(?:youtube|google|bing|duckduckgo|internet)\s+.+|.+\s+en\s+(?:youtube|google|bing|duckduckgo|internet)[.!?]*)$/.test(command)) return false;
            const allowed = new Set(['note', 'todo', 'timer', 'analyze', 'searchNotes', 'calculate', 'convert', 'completeTodo', 'pause', 'resume', 'cancel', 'notes', 'todos', 'time', 'date', 'help', 'greet', 'summon', 'follow', 'stay', 'hide']);
            try { return allowed.has(Axx.parseIntent?.(raw)?.type) || Boolean(Axx.isLocalExternalCommand?.(raw)); }
            catch { return true; } // The existing parser displays its own validation error locally.
        }
        installDispatch() {
            const previous = Axx.companion.send.bind(Axx.companion);
            if (Axx.symbiosis?.voiceCommand) {
                const voiceCommand = Axx.symbiosis.voiceCommand.bind(Axx.symbiosis);
                Axx.symbiosis.voiceCommand = text => this.internalAction(text)
                    ? Axx.companion.send(text, {source:'voice'}) : voiceCommand(text);
            }
            if (Axx.companion.submit) {
                const submit = Axx.companion.submit.bind(Axx.companion);
                Axx.companion.submit = async () => {
                    const draft = node('chat-input').value.trim();
                    if ((this.busy || this.operation) && !Axx.modelSelection?.parse(draft) && !this.hasLocalIntent(draft) && !/^(?:\/cancelar-comando|cancelar comando|cancela el comando|\/comandos(?:\s+.*)?)$/i.test(draft)) {
                        Axx.chatWorkspace?.operationCard(this.operation || this.lastOperation);
                        if (this.isActionRequest(draft)) { Axx.companion.openChat(); return; }
                    }
                    return submit();
                };
            }
            Axx.companion.send = async (text, metadata = {}) => {
                const raw = String(text || '').trim();
                const origin = Axx.chatWorkspace?.active?.id;
                const activeTask = this.operation || this.lastOperation;
                if (activeTask?.kind === 'learned_plan' && !['succeeded','cancelled','failed','blocked','expired'].includes(activeTask.state)) {
                    if (/^(?:pausa|pausa la tarea|pausa el trabajo)$/i.test(raw)) { await this.pausePlan(); return; }
                    if (/^(?:para|detente|detener tarea|cancela la tarea)$/i.test(raw)) { await this.cancel(); return; }
                    if (/^(?:retoma|reanuda|continua desde donde quedaste|continúa desde donde quedaste)$/i.test(raw)) { await this.resumePlan(); return; }
                }
                const goal = raw.match(/^\/(?:tarea|objetivo)\s+([\s\S]+)/i);
                if (goal) { Axx.companion.message('user', raw, 'local'); await this.planAction(goal[1]); return; }
                const modelCommand = Axx.modelSelection?.parse(raw);
                if (modelCommand) {
                    Axx.companion._forceVoiceReplyOnce = false;
                    Axx.companion.message('user', raw, 'local');
                    try { this.notice(await Axx.modelSelection.run(modelCommand), origin); }
                    catch (error) { this.notice('No se pudo consultar o cambiar el modelo: ' + errorText(error), origin); }
                    Axx.resident?.schedule(); return;
                }
                const internal = this.internalAction(raw);
                if (internal) {
                    Axx.companion._forceVoiceReplyOnce = false;
                    Axx.companion.message('user', raw, 'local');
                    try { this.notice(await this.runInternal({...internal,source:metadata.source === 'voice' ? 'voice' : 'text'}), origin); }
                    catch (error) { this.notice('No se pudo completar la orden: ' + errorText(error), origin); }
                    Axx.resident?.schedule(); return;
                }
                if (this.learningQuestion && /^(cancelar|cancela|cancelar accion)$/i.test(raw)) { this.learningQuestion = null; Axx.companion.localNotice('Preparación cancelada.'); return; }
                if (this.learningQuestion && raw && !raw.startsWith('/')) {
                    const question = this.learningQuestion; this.learningQuestion = null;
                    Axx.companion.message('user', raw, 'local');
                    if (Axx.skillLibrary && question.operation_id) { await Axx.skillLibrary.continueTask(question.operation_id,raw); return; }
                    await this.planAction(question.request + '\nAclaración solicitada: ' + question.question + '\nRespuesta del usuario: ' + raw); return;
                }
                if (/^\/(?:acciones|aprendidas)$/i.test(raw)) { this.open(); await this.listLearned(); return; }
                const learn = raw.match(/^\/(?:aprende|accion)\s+(.+)/is);
                if (learn) { Axx.companion.message('user', raw, 'local'); await this.planAction(learn[1]); return; }
                const catalogQuery = raw.match(/^\/comandos(?:\s+(.*))?$/i);
                if (catalogQuery) { this.open(); try { await this.search(catalogQuery[1] || ''); } catch (error) { this.status(errorText(error)); } return; }
                if (/^(?:\/cancelar-comando|cancelar comando|cancela el comando)$/i.test(raw)) { await this.cancel(); return; }
                if (!Axx.isNative() || !raw || Axx.companion.attachment || Axx.companion.pending || Axx.companion.externalBusy) return previous(raw, metadata);
                if (raw.length > 10000) {
                    if (this.isActionRequest(raw)) { Axx.companion.localNotice('La petición de acción es demasiado larga. Resúmela o usa un comando concreto.'); return; }
                    return previous(raw, metadata);
                }
                if (this.hasLocalIntent(raw)) return previous(raw, metadata);
                if (this.busy || this.operation) { Axx.chatWorkspace?.operationCard(this.operation || this.lastOperation); if (!this.isActionRequest(raw)) return previous(raw, metadata); Axx.companion.openChat(); return; }
                const source = metadata.source === 'voice' || this.voiceDraft?.value === raw ? 'voice' : 'text';
                this.voiceDraft = null;
                const serial = ++this.generation; let prepared = false; this.busy = true;
                try {
                    const resolved = await this.request('POST', '/axx-api/commands/resolve', { text: raw, source, context: this.actionContext, project_id:Axx.skillLibrary?.project() || '' });
                    if (serial !== this.generation) return;
                    this.busy = false;
                    if (origin && Axx.chatWorkspace?.active?.id !== origin) {
                        this.status('La conversación cambió antes de preparar la acción. No se ejecutó ningún comando.');
                        return;
                    }
                    if (resolved.match === 'learned') {
                        Axx.companion.message('user', raw, 'local');
                        await this.planAction(raw); return;
                    }
                    if (resolved.match === 'unsupported') {
                        Axx.companion.message('user', raw, 'local');
                        Axx.companion.localNotice(resolved.message || 'No encontré una acción ejecutable para esa petición.');
                        return;
                    }
                    if (resolved.match === 'none') {
                        if(!this.isActionRequest(raw))return previous(raw, metadata);
                        if (Axx.companion.data?.prefs?.provider === 'chatgpt') {
                            Axx.companion.message('user', raw, 'local');
                            Axx.companion.localNotice('El modo ChatGPT de Axx no está conectado al planificador de comandos. Selecciona un modelo de acciones de Ollama o de una API configurada en Ajustes y vuelve a intentarlo.');
                            return;
                        }
                        Axx.companion.message('user',raw,'local');
                        await this.planAction(raw);
                        return;
                    }
                    Axx.companion.message('user', raw, 'local');
                    if (resolved.match !== 'exact' || !resolved.command_id) {
                        Axx.companion.localNotice(resolved.message || (resolved.match === 'ambiguous' ? 'Hay varios comandos posibles. Abre /comandos y selecciona el ID exacto.' : 'No se pudo identificar un comando válido. Consulta /comandos.'));
                        return;
                    }
                    if (resolved.execution_enabled === false && resolved.has_recipe_details) {
                        await this.planAction(raw); return;
                    }
                    if (Object.entries(resolved.parameters || {}).some(([key, spec]) => spec.required && !Object.hasOwn(resolved.inputs || {}, key))) {
                        await this.search(resolved.command_id); this.open();
                        this.notice('He seleccionado el comando. Completa sus datos en la biblioteca para prepararlo.', origin);
                        return;
                    }
                    prepared = true;
                    const result = await this.prepare(resolved.command_id, resolved.inputs || {}, source);
                    if (result) this.notice(result, origin);
                } catch (error) {
                    if (serial + (prepared ? 1 : 0) === this.generation) {
                        this.report(error);
                        this.notice((this.operation ? 'No se confirmó el resultado del comando. ' : 'No se pudo consultar o preparar el comando. ') + errorText(error) + (this.operation ? ' Consulta el resultado en Biblioteca antes de reintentar.' : ' Puedes reintentar la consulta; no se enviará al modelo automáticamente.'), origin);
                    }
                } finally { if (serial === this.generation && !this.operation) this.busy = false; }
            };
        }
        markVoiceProvenance() {
            const voice = Axx.voice13;
            if (!voice?.applyPending) return;
            const apply = voice.applyPending.bind(voice);
            voice.applyPending = (...args) => {
                const field = voice.target?.field, before = field?.value;
                const result = apply(...args);
                if (field?.id === 'chat-input' && field.value !== before) this.voiceDraft = { value: field.value.trim() };
                return result;
            };
        }
        renderOperation(operation) {
            node('command-library-result').textContent = JSON.stringify(operation, null, 2);
            const awaiting = operation?.state === 'awaiting_approval';
            node(awaiting ? 'command-library-approval-actions' : 'command-library-controls').append(node('command-library-cancel'));
            node('command-library-approval').hidden = !awaiting;
            if (awaiting) this.renderApproval(operation);
            node('command-library-approve').disabled = !awaiting || this.busy;
            node('command-library-cancel').disabled = !this.busy && !this.operation;
            node('command-library-recover').disabled = this.busy || this.cancellingGeneration === this.generation || !operation?.operation_id;
            node('command-library-recover').textContent = operation?.state === 'unknown' && operation.evidence?.reconciliation_required ? 'Revisar efecto sin repetir' : 'Consultar resultado';
            node('command-library-remember').hidden = !(operation?.state === 'succeeded' && operation.postconditions_passed && ['axx.desktop.notepad.text','axx.desktop.explorer.folder'].includes(operation.command_id));
            node('command-library-prepare').disabled = this.busy || !!this.operation || !this.commands.find(item => item.id === node('command-library-select').value)?.execution_enabled;
            if (Axx.desktop) {
                const verified = operation?.state === 'succeeded' && operation.postconditions_passed === true;
                Axx.desktop.lastOperation = verified ? operation : null;
                node('desktop-action-result').textContent = JSON.stringify(operation, null, 2);
            }
            Axx.resident?.schedule();
        }
        renderApproval(operation) {
            const steps = operation.kind === 'learned_plan' ? operation.steps : [operation];
            const titles = {'axx.artifact.write':'Crear archivo en Axx/artifacts', 'axx.file.sha256':'Comprobar el contenido del archivo (SHA-256)',
                'axx.file.compare':'Comparar dos archivos', 'axx.shell.powershell':'Ejecutar script de PowerShell', 'axx.shell.cmd':'Ejecutar comando de CMD',
                'axx.desktop.open_url':'Abrir página web', 'axx.desktop.search':'Buscar en el navegador', 'axx.desktop.window.set_value':'Escribir en la ventana seleccionada',
                'axx.desktop.window.read':'Leer texto y enlaces de la ventana seleccionada',
                'axx.desktop.window.invoke':'Pulsar botón observado',
                'axx.desktop.notepad.text':'Reemplazar texto en el documento de Notepad (sin guardar)',
                'axx.desktop.explorer.folder':'Abrir y enfocar la carpeta en Explorador'};
            const labels = {path:'Archivo', other_path:'Segundo archivo', content:'Contenido que se guardará', script:'Código que se ejecutará',
                url:'Dirección', query:'Búsqueda', engine:'Buscador', value:'Texto que se escribirá', window_title:'Título exacto del documento de Notepad', window_id:'Ventana', pid:'Proceso', control_id:'Control', app:'Aplicación', expected_title:'Ventana o página que se leerá'};
            const preview = node('command-library-preview'); preview.replaceChildren();
            let completed = 0;
            steps.forEach((step, index) => {
                const done = operation.step_records?.[index]?.state === 'succeeded';
                if (done) completed++;
                const item = document.createElement('li'), title = document.createElement('strong');
                title.textContent = (done ? 'Completado · ' : '') + (titles[step.command_id] || this.commands.find(c => c.id === step.command_id)?.title || step.command_id);
                item.append(title);
                if (step.delivery_mode) { const mode = document.createElement('p'); mode.textContent = 'Entorno: ' + ({background:'segundo plano',foreground:'escritorio activo',isolated:'aislado'}[step.delivery_mode] || step.delivery_mode); item.append(mode); }
                if (done) { const note = document.createElement('p'); note.textContent = 'Se conserva el resultado. Este paso no se repetirá.'; item.append(note); }
                for (const [key, value] of Object.entries(step.inputs || {})) {
                    const label = document.createElement('div'), text = document.createElement('pre');
                    label.textContent = labels[key] || key; text.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
                    text.tabIndex = 0; text.setAttribute('aria-label', label.textContent);
                    item.append(label, text);
                }
                if (!done && ['axx.shell.powershell','axx.shell.cmd'].includes(step.command_id)) {
                    const note = document.createElement('p'); note.textContent = 'Puede modificar archivos y ajustes del equipo. Carpeta de trabajo: Axx/artifacts. Límite: 30 segundos.'; item.append(note);
                }
                preview.append(item);
            });
            const pending = steps.length - completed;
            node('command-library-approval-summary').textContent = (operation.title ? operation.title + ' · ' : '') + `${pending} ${pending === 1 ? 'paso pendiente' : 'pasos pendientes'}` + (completed ? ` · ${completed} ya completado(s)` : '') + '.';
            node('command-library-approve').textContent = this.busy ? 'Ejecutando…' : `Aprobar y ejecutar ${pending === 1 ? '1 paso' : pending + ' pasos'}`;
            node('command-library-raw').textContent = JSON.stringify({operation_id:operation.operation_id, steps}, null, 2);
        }
        async prepare(commandId, inputs, source, deliveryMode) {
            return this.prepareRequest('/axx-api/commands/prepare', { command_id: commandId, inputs, source, ...(deliveryMode ? {delivery_mode:deliveryMode} : {}) });
        }
        async prepareRequest(path, body) {
            if (this.busy || this.operation) throw new Error('Ya hay un comando pendiente.');
            const serial = ++this.generation; this.busy = true;
            ++this.observationRevision;
            const operationId = Axx.newId(); this.pendingOperationId = operationId;
            this.lastOperation = { operation_id: operationId, command_id: body.command_id, state: 'preparing' };
            this.status('Validando parámetros, adaptador y permisos.');
            node('command-library-cancel').disabled = false;
            node('command-library-recover').disabled = true;
            try {
                const operation = await this.request('POST', path, { ...body, operation_id: operationId });
                if (serial !== this.generation) return;
                if (operation.operation_id !== operationId) throw new Error('La preparación no corresponde al comando solicitado.');
                this.pendingOperationId = null;
                return await this.adopt(operation);
            } catch (error) {
                if (serial !== this.generation) return;
                throw error;
            } finally { if (serial === this.generation) { this.pendingOperationId = null; this.busy = false; node('command-library-cancel').disabled = !this.operation; node('command-library-recover').disabled = !this.lastOperation?.operation_id; } }
        }
        async adopt(operation) {
            if (!operation?.operation_id || !['prepared', 'awaiting_approval', 'blocked', 'cancelled'].includes(operation.state)) throw new Error('El backend no confirmó un comando preparado.');
            ++this.observationRevision; this.lastOperation = operation;
            this.operation = ['prepared', 'awaiting_approval'].includes(operation.state) ? operation : null;
            this.busy = false; this.renderOperation(operation);
            if (operation.state === 'blocked') { this.status('Comando bloqueado: ' + errorText(operation.error)); return 'Comando bloqueado: ' + errorText(operation.error); }
            if (operation.state === 'cancelled') { this.status('Comando cancelado antes de ejecutar.'); return 'Comando cancelado antes de ejecutar.'; }
            if (operation.state === 'awaiting_approval') { if(Axx.chatWorkspace) Axx.companion.openChat(); else this.open(); this.status('Esperando tu aprobación. Revisa los pasos antes de ejecutar.'); return 'Comando preparado. Revisa la tarjeta de acción y pulsa «Aprobar y ejecutar».'; }
            return await this.execute(false);
        }
        async approve() {
            if (!this.operation || this.operation.state !== 'awaiting_approval' || this.busy) return;
            if (this.operation.kind === 'learned_plan') return this.executePlan();
            const origin = this.operation.conversation_id || Axx.chatWorkspace?.active?.id;
            const message = await this.execute(true);
            if (message) this.notice(message, origin);
        }
        async execute(approved) {
            const operation = this.operation;
            if (!operation || this.busy) throw new Error('No hay un comando preparado para ejecutar.');
            ++this.observationRevision;
            const serial = this.generation; this.busy = true; this.renderOperation(operation); this.status('Ejecutando y comprobando el resultado.');
            try {
                const result = await this.request('POST', '/axx-api/commands/execute', { operation_id: operation.operation_id, ...(approved ? { approved: true } : {}) });
                if (serial !== this.generation) return;
                if (result.operation_id !== operation.operation_id) throw new Error('El resultado no corresponde al comando solicitado.');
                this.lastOperation = result; this.operation = null; this.busy = false; this.renderOperation(result);
                const launchNeedsWindow = ['axx.desktop.open_app', 'axx.desktop.installed_app'].includes(result.command_id);
                const verified = result.state === 'succeeded' && result.postconditions_passed === true
                    && (!launchNeedsWindow || result.output?.ready_for_action === true);
                if (verified && result.command_id === 'axx.desktop.window.read') Axx.windowContent?.accept(result);
                if (verified && result.command_id === 'axx.desktop.list_windows') Axx.windowContent?.acceptWindows(result);
                let detail = '';
                if (verified && result.evidence && typeof result.evidence === 'object') {
                    const ev = result.evidence;
                    if (typeof ev.cpu_usage_percent === 'number' || typeof ev.memory_used_mb === 'number') {
                        const parts = [];
                        if (typeof ev.cpu_usage_percent === 'number') parts.push(`CPU ${Math.round(ev.cpu_usage_percent)}%`);
                        if (typeof ev.memory_used_mb === 'number' && typeof ev.memory_total_mb === 'number') parts.push(`RAM ${Math.round(ev.memory_used_mb / 102.4) / 10} de ${Math.round(ev.memory_total_mb / 102.4) / 10} GB`);
                        if (parts.length) detail = ' (' + parts.join(', ') + ')';
                    } else if (ev.name && ev.pid) detail = ` (${ev.name}, PID ${ev.pid})`;
                }
                let message = verified ? 'Comando completado y verificado: ' + result.command_id + detail + '.' : result.state === 'cancelled' ? 'Comando cancelado. No se marcó como completado.' : 'Comando sin éxito verificado: ' + errorText(result.error || result.state) + '.';
                if (result.state === 'succeeded' && result.evidence?.verification === 'os_handoff') {
                    const target=result.evidence.target;
                    if(result.command_id==='axx.desktop.search')this.actionContext={engine:operation.inputs.engine,query:operation.inputs.query,url:target};
                    else if(result.command_id==='axx.desktop.open_url'){
                        const host=new URL(target).hostname.replace(/^www\./,'');
                        const engine=({'youtube.com':'youtube','google.com':'google','bing.com':'bing','duckduckgo.com':'duckduckgo'})[host];
                        this.actionContext={url:target,...(engine?{engine}:{})};
                    }
                    if (launchNeedsWindow && !result.output?.ready_for_action) {
                        message = 'Windows aceptó abrir ' + (result.output?.label || result.evidence.target)
                            + ', pero Axx no confirmó la ventana y el foco. Aún no puede actuar en esa aplicación.';
                    } else if (launchNeedsWindow) {
                        message = 'Ventana observada y foco confirmado para ' + (result.output?.label || result.evidence.target) + '.';
                    } else message = 'He enviado a Windows la apertura de ' + (result.output?.label || result.evidence.target) + '.';
                    if (result.command_id === 'axx.desktop.search') message += ' Los resultados se abren en tu navegador.';
                }
                if (result.command_id === 'axx.shell.powershell') {
                    const output = result.output || {};
                    message = result.state === 'cancelled' ? 'PowerShell cancelado. Los cambios ya realizados no se deshacen.' : verified ? 'PowerShell terminó correctamente (código 0).' : 'PowerShell: ' + errorText(result.error || result.state);
                    if (output.stdout) message += '\n\nSalida:\n' + output.stdout.slice(0, 12000);
                    if (output.stderr) message += '\n\nErrores:\n' + output.stderr.slice(0, 12000);
                    if ((output.stdout?.length || 0) > 12000 || (output.stderr?.length || 0) > 12000) message += '\n\nConsulta el resultado completo en la biblioteca.';
                }
                if (verified && result.command_id === 'axx.desktop.list_apps') {
                    const apps = result.output?.applications || [];
                    message = `Windows registra ${apps.length} aplicaciones instaladas. La detección no implica que cada una tenga acciones compatibles:\n\n` + apps.slice(0, 120).map(app => `${app.name} — detectada; controles por app sin validar`).join('\n');
                    if (apps.length > 120) message += '\n\nLa lista completa está en el resultado de la biblioteca.';
                }
                if (verified && result.command_id === 'axx.desktop.list_windows') {
                    const windows = result.output?.windows || [];
                    message = windows.length ? `Ventanas visibles: ${windows.length}.\n\n` + windows.slice(0, 80).map(w => `${w.foreground ? '●' : '○'} ${w.title} — HWND 0x${Number(w.window_id).toString(16)}, PID ${w.pid}`).join('\n')
                        : 'No se encontraron ventanas visibles con título.';
                }
                if (verified && result.evidence?.verification === 'stable_file_sha256') {
                    message = result.output.files.map(file => `${file.path}\nSHA256: ${file.sha256}\n${file.bytes} bytes`).join('\n\n');
                    if (typeof result.output.equal === 'boolean') message += result.output.equal ? '\n\nEl contenido de los dos archivos coincide.' : '\n\nLos archivos tienen contenido diferente.';
                }
                if (verified && result.command_id === 'axx.desktop.window.invoke')
                    message = `Pulsé «${result.output.button}» en «${result.output.window}». La aplicación recibió la pulsación; su efecto posterior no está verificado.`;
                if (verified && result.command_id === 'axx.desktop.window.set_value' && operation.inputs.expected_title)
                    message = `Escribí el texto en «${operation.inputs.expected_title}» y comprobé el campo. No envié el mensaje.`;
                this.status(message); Axx.companion.action(verified ? 'success' : result.state === 'cancelled' ? 'cancel' : 'error');
                return message;
            } catch (error) {
                if (serial !== this.generation) return;
                this.status('Resultado incierto: ' + errorText(error) + ' Consulta el resultado antes de reintentar.'); node('command-library-approval').hidden = true;
                throw error;
            } finally { if (serial === this.generation) { this.busy = false; node('command-library-recover').disabled = !operation.operation_id; node('command-library-cancel').disabled = !this.operation; } }
        }
        async listLearned() {
            if (Axx.skillLibrary) return Axx.skillLibrary.refresh();
            const result = await this.request('GET', '/axx-api/learning/actions');
            const list = node('command-library-learned-list'); list.replaceChildren();
            for (const action of result.actions || []) {
                const button = document.createElement('button'); button.type = 'button'; button.textContent = action.title;
                button.title = 'Revisar y repetir ' + action.steps.length + ' pasos guardados';
                button.onclick = () => { void this.planAction(action.id); };
                list.append(button);
            }
            if (!result.actions?.length) list.textContent = 'Aún no hay acciones aprendidas. Pide una acción o escribe /aprende seguido de lo que necesitas.';
            Axx.resident?.schedule();
        }
        async planAction(text, options = {}) {
            if (this.busy || this.operation) { Axx.companion.localNotice('Hay una acción pendiente. Revisa el resultado o cancélala antes de preparar otra.'); return; }
            const serial = ++this.generation, id = Axx.newId();
            const origin = Axx.chatWorkspace?.active?.id;
            this.busy = true; ++this.observationRevision;
            this.operation = this.lastOperation = { kind:'learned_plan', operation_id:id, command_id:'axx.learned', state:'planning' };
            this.status('Buscando una habilidad y preparando la acción…'); this.renderOperation(this.operation);
            Axx.companion.action('thinking');
            const prefs = Axx.companion.data?.prefs || {};
            try {
                const plan = await this.request('POST', '/axx-api/learning/propose', { text, operation_id:id, context:{...this.actionContext, ...options.context},
                    inputs:options.inputs, project_id:Axx.skillLibrary?.project() || '', selection_mode:prefs.selection_mode || 'manual',
                    model:prefs.model || '', provider_name:prefs.provider === 'bridge' ? prefs.apiConnection || '' : '' });
                if (serial !== this.generation) return;
                this.lastOperation = plan; this.operation = plan.state === 'awaiting_approval' ? plan : null;
                this.learningQuestion = plan.state === 'needs_input' ? {request:text,question:plan.message,operation_id:plan.operation_id} : null;
                this.busy = false; this.renderOperation(plan); this.status(plan.message || plan.state);
                if (this.operation) { if(Axx.chatWorkspace) Axx.companion.openChat(); else this.open(); }
                this.notice(plan.message || 'No se pudo preparar la acción.', origin);
                Axx.companion.action(this.operation ? 'approval' : 'idle');
            } catch (error) {
                if (serial !== this.generation) return;
                this.operation = null; this.report(error);
                this.notice('No se pudo preparar la acción: ' + errorText(error), origin);
            } finally {
                if (serial === this.generation) { this.busy = false; node('command-library-cancel').disabled = !this.operation; }
            }
        }
        async executePlan() {
            const operation = this.operation, serial = this.generation;
            if (!operation || this.busy) return;
            const origin = operation.conversation_id || Axx.chatWorkspace?.active?.id;
            this.busy = true; operation.state = 'running'; ++this.observationRevision;
            this.renderOperation(operation); this.status('Ejecutando los pasos y comprobando sus resultados…');
            const progress = setInterval(() => {
                void this.request('GET', '/axx-api/learning/plan?id=' + encodeURIComponent(operation.operation_id)).then(current => {
                    if (serial !== this.generation || !this.busy || this.operation?.operation_id !== operation.operation_id) return;
                    this.renderOperation(current);
                    this.status(`Ejecutando y comprobando: ${(current.step_records || []).filter(step => step.state === 'succeeded').length}/${current.steps?.length || 0} pasos confirmados.`);
                }).catch(() => {});
            }, 1000);
            try {
                const plan = await this.request('POST', '/axx-api/learning/execute', { operation_id:operation.operation_id, approved:true });
                if (serial !== this.generation) return;
                this.lastOperation = plan; this.operation = null; this.busy = false;
                this.renderOperation(plan); this.status(plan.message || plan.state);
                const verified = plan.state === 'succeeded' && plan.postconditions_passed === true;
                let message = plan.message || plan.state;
                for (const result of plan.results || []) {
                    if (result.evidence?.verification === 'os_handoff') message += '\nWindows aceptó abrir: ' + (result.output?.label || result.evidence.target);
                    if (result.evidence?.sha256) message += '\nArchivo verificado: ' + result.evidence.path;
                }
                this.notice(message, origin); Axx.companion.action(verified ? 'success' : 'error');
                if (verified) void this.listLearned().catch(() => {});
            } catch (error) {
                if (serial !== this.generation) return;
                this.status('Resultado incierto. Consulta el estado antes de repetir: ' + errorText(error));
            } finally { clearInterval(progress); if (serial === this.generation) { this.busy = false; this.renderOperation(this.lastOperation); } }
        }
        async pausePlan() {
            const task = this.operation || this.lastOperation;
            if (task?.kind !== 'learned_plan') return;
            try {
                const result = await this.request('POST','/axx-api/learning/pause',{operation_id:task.operation_id});
                this.lastOperation = result;
                this.renderOperation(result); this.status(result.message);
            } catch (error) { this.report(error); }
        }
        async resumePlan() {
            const task = this.operation || this.lastOperation;
            if (this.busy || task?.kind !== 'learned_plan') return;
            this.busy = true;
            try {
                const result = await this.request('POST','/axx-api/learning/resume',{operation_id:task.operation_id,approved:false});
                this.lastOperation = result; this.operation = result.state === 'awaiting_approval' ? result : null;
                this.busy = false; this.renderOperation(result); this.status(result.message);
            } catch (error) { this.report(error); }
            finally { this.busy = false; }
        }
        async recover() {
            if (this.busy || this.cancellingGeneration === this.generation) return;
            const operation = this.operation || this.lastOperation;
            if (!operation?.operation_id) return;
            const serial = this.generation;
            const revision = ++this.observationRevision;
            let result;
            try { result = operation.state === 'unknown' && operation.evidence?.reconciliation_required
                ? { operation: await this.request('POST', '/axx-api/commands/reconcile', {operation_id:operation.operation_id}) }
                : operation.kind === 'learned_plan'
                ? { operation: await this.request('GET', '/axx-api/learning/plan?id=' + encodeURIComponent(operation.operation_id)) }
                : await this.request('GET', '/axx-api/commands/operations?operation_id=' + encodeURIComponent(operation.operation_id)); }
            catch (error) { if (serial !== this.generation || revision !== this.observationRevision) return; throw error; }
            if (serial !== this.generation || revision !== this.observationRevision || this.busy) return;
            if (!result.operation || result.operation.operation_id !== operation.operation_id) throw new Error('El backend no confirmó el estado de este comando.');
            this.lastOperation = result.operation;
            this.operation = ['prepared', 'awaiting_approval', 'running'].includes(result.operation.state) ? result.operation : null;
            this.renderOperation(result.operation);
            this.status('Estado observado: ' + result.operation.state + (result.operation.postconditions_passed === true ? ' · condiciones verificadas.' : '.'));
        }
        async reviewUnknown(operation) {
            if (this.busy || operation?.state !== 'unknown') return;
            this.busy = true;
            try {
                const result = await this.request('POST','/axx-api/commands/review',{operation_id:operation.operation_id,reviewed:true});
                this.operation = null; this.lastOperation = result;
                this.renderOperation(result);
                this.status('Revisión manual registrada. El efecto sigue sin verificar; cualquier nueva acción requiere su propia preparación.');
            } catch (error) { this.report(error); }
            finally { this.busy = false; this.renderOperation(this.lastOperation); }
        }
        async cancel(send = true) {
            this.learningQuestion = null;
            if (this.cancellingGeneration === this.generation) return;
            const operation = this.operation;
            const operationId = operation?.operation_id || this.pendingOperationId;
            ++this.generation; this.busy = false; this.operation = null; this.pendingOperationId = null;
            const serial = this.generation, revision = ++this.observationRevision;
            node('command-library-approval').hidden = true; node('command-library-approve').disabled = true; node('command-library-cancel').disabled = true;
            if (!Axx.isNative()) return;
            if (send) { this.cancellingGeneration = serial; node('command-library-recover').disabled = true; }
            this.status('Cancelación solicitada. Se descartan las respuestas tardías.');
            if (send) {
                try {
                    const result = await this.request('POST', operation?.kind === 'learned_plan' ? '/axx-api/learning/cancel' : '/axx-api/commands/cancel', operationId ? { operation_id: operationId } : {});
                    if (serial !== this.generation || revision !== this.observationRevision) return;
                    if (result.operation_id === operationId && typeof result.state === 'string') {
                        ++this.observationRevision;
                        this.lastOperation = result;
                        this.operation = result.state === 'running' ? result : null;
                        this.renderOperation(result);
                        this.status('Estado observado tras cancelar: ' + result.state + (result.postconditions_passed === true ? ' · condiciones verificadas.' : '.'));
                        return;
                    }
                    node('command-library-result').textContent = JSON.stringify(result, null, 2);
                    this.status('Cancelación enviada al ejecutor. Consulta el resultado para observar el estado final.');
                } catch (error) { if (serial === this.generation && revision === this.observationRevision) this.status('No se confirmó la cancelación: ' + errorText(error) + '. Consulta el resultado antes de reintentar.'); }
                finally {
                    if (this.cancellingGeneration === serial) this.cancellingGeneration = null;
                    if (serial === this.generation) node('command-library-recover').disabled = this.busy || !this.lastOperation?.operation_id;
                }
            }
        }
    }
    Axx.commandLibrary = new CommandLibrary();
})(window.Axx);
