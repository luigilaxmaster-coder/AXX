/* Convertidor: local files become bounded, verified jobs in the Axx backend. */
(() => {
    'use strict';
    const A = window.Axx, $ = id => document.getElementById(id);
    const api = (action, body = {}) => A.backendRequest('POST', '/axx-api/converter/' + action, body);
    const explanations = {
        'png-jpeg': 'La transparencia se compone sobre el color elegido. JPEG pierde detalle por compresión; orientación aplicada; ICC se conserva si existe.',
        'jpeg-png': 'La orientación se aplica. PNG no recupera detalle perdido del JPEG y puede ocupar más espacio; ICC se conserva si existe.',
        'pdf-merge': 'Conserva orden y tamaños físicos de página. Los marcadores y metadatos de documento no se reconstruyen. PDFs con formularios o firmas se rechazan.',
        'pdf-extract': 'Conserva las páginas seleccionadas y sus tamaños físicos. Se crea un documento nuevo; marcadores y metadatos globales no se reconstruyen.'
    };
    class Converter {
        constructor() {
            const view = document.createElement('section');
            view.id = 'view-converter'; view.className = 'panel-view cv-view'; view.hidden = true;
            view.innerHTML = `<div class="cv-lead"><span>ARCHIVOS · LOCAL</span><h3>Convertidor y PDF</h3><p>Inspecciona, revisa las pérdidas y guarda un resultado verificado. Los originales permanecen intactos.</p></div>
                <div class="cv-tabs" role="group" aria-label="Secciones del convertidor"><button data-cv-tab="quick" aria-pressed="true">Conversión rápida</button><button data-cv-tab="pdf">PDF</button><button data-cv-tab="cad">CAD y BIM</button><button data-cv-tab="models">Modelos 3D</button><button data-cv-tab="batches">Lotes</button><button data-cv-tab="history">Historial</button></div>
                <div id="cv-work"><label class="cv-drop" id="cv-drop" tabindex="0">Arrastra archivos aquí o <strong>selecciónalos</strong><input id="cv-files" type="file" accept=".png,.jpg,.jpeg,.pdf" multiple hidden></label>
                <p class="cv-note">Hasta 10 archivos, 30 MB cada uno y 60 MB por lote. La inspección detecta el contenido real; no convierte al añadir.</p>
                <div id="cv-file-list" class="cv-list" aria-live="polite"></div><div id="cv-preview"></div>
                <label>Operación<select id="cv-operation" aria-label="Operación de conversión"></select></label>
                <div id="cv-image-options" hidden><label>Fondo del JPEG<input id="cv-background" type="color" value="#ffffff"></label><label>Calidad JPEG <output id="cv-quality-value">90</output>%<input id="cv-quality" type="range" min="20" max="100" value="90"></label></div>
                <div id="cv-pdf-options" hidden><label>Páginas (por ejemplo 1, 3-5)<input id="cv-pages" type="text" value="1" maxlength="200"></label></div>
                <p id="cv-loss" class="cv-note"></p><p id="cv-destination" class="cv-note"></p>
                <div class="cv-actions"><button id="cv-run" class="primary" disabled>Ejecutar</button><button id="cv-cancel" disabled>Cancelar</button><button id="cv-retry" hidden>Reintentar</button></div>
                <p id="cv-status" role="status" aria-live="polite">Elige archivos para empezar.</p><div id="cv-result" hidden><strong>Resultado verificado</strong><p id="cv-result-detail"></p><button id="cv-open">Abrir carpeta</button></div></div>
                <div id="cv-unavailable" hidden><h3 id="cv-unavailable-title"></h3><p id="cv-unavailable-detail"></p></div>
                <div id="cv-history" hidden></div>`;
            $('panel').append(view);
            const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = 'scripts/converter.css'; document.head.append(style);
            this.view = view; this.files = []; this.job = null; this.tab = 'quick'; this.busy = false; this.poller = null;
            $('cv-files').onchange = event => { void this.select([...event.target.files]); event.target.value = ''; };
            $('cv-drop').ondragover = event => { event.preventDefault(); $('cv-drop').classList.add('drag'); };
            $('cv-drop').ondragleave = () => $('cv-drop').classList.remove('drag');
            $('cv-drop').ondrop = event => { event.preventDefault(); $('cv-drop').classList.remove('drag'); void this.select([...event.dataTransfer.files]); };
            $('cv-drop').onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('cv-files').click(); } };
            view.querySelectorAll('[data-cv-tab]').forEach(button => button.onclick = () => this.showTab(button.dataset.cvTab));
            $('cv-operation').onchange = () => this.renderOperation();
            $('cv-quality').oninput = () => $('cv-quality-value').textContent = $('cv-quality').value;
            $('cv-run').onclick = () => void this.run();
            $('cv-cancel').onclick = () => void this.cancel();
            $('cv-retry').onclick = () => void this.select(this.files);
            $('cv-open').onclick = () => void this.open();
            const prior = A.companion.externalCommand;
            A.companion.externalCommand = raw => /^(abre|abrir|muestra) (el )?(convertidor|pdf)$/.test(A.plain(raw))
                ? async () => { A.flow.select('converter'); return 'Convertidor abierto. Selecciona archivos para inspeccionarlos.'; }
                : prior?.(raw) || null;
            if (!A.isNative()) this.status('El convertidor de archivos requiere Axx Desktop para guardar resultados locales.');
        }
        status(message) { $('cv-status').textContent = message; }
        showTab(tab) {
            this.tab = tab;
            this.view.querySelectorAll('[data-cv-tab]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.cvTab === tab)));
            $('cv-work').hidden = !['quick', 'pdf'].includes(tab);
            $('cv-history').hidden = tab !== 'history';
            $('cv-unavailable').hidden = !['cad', 'models', 'batches'].includes(tab);
            if (tab === 'history') void this.history();
            if (tab === 'cad' || tab === 'models' || tab === 'batches') {
                $('cv-unavailable-title').textContent = {cad:'CAD y BIM',models:'Modelos 3D',batches:'Lotes y paquetes'}[tab];
                $('cv-unavailable-detail').textContent = 'Pendiente de implementación: no se ofrece una ruta sin motor de lectura, escritura y validación comprobado.';
            }
        }
        async select(files) {
            if (!A.isNative()) return this.status('Esta operación requiere Axx Desktop.');
            if (!files.length || files.length > 10 || files.some(file => !file.size || file.size > 30 * 1024 * 1024) || files.reduce((sum, file) => sum + file.size, 0) > 60 * 1024 * 1024) return this.status('Elige 1–10 archivos de hasta 30 MB cada uno y 60 MB en total.');
            clearTimeout(this.poller);
            if (this.previewURL) URL.revokeObjectURL(this.previewURL);
            this.previewURL = null;
            this.files = files; this.job = null; this.busy = true; $('cv-run').disabled = true; $('cv-cancel').disabled = true; $('cv-retry').hidden = true; $('cv-result').hidden = true;
            $('cv-file-list').replaceChildren(...files.map(file => { const row = document.createElement('div'); row.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB · esperando inspección`; return row; }));
            try {
                this.job = await api('new', {files: files.map(file => ({name:file.name, size:file.size}))});
                $('cv-cancel').disabled = false;
                for (let index = 0; index < files.length; index++) {
                    for (let offset = 0; offset < files[index].size; offset += 256 * 1024) {
                        if (!this.busy) return;
                        const bytes = new Uint8Array(await files[index].slice(offset, offset + 256 * 1024).arrayBuffer());
                        let binary = '';
                        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
                        await api('upload', {id:this.job.id, index, offset, data:btoa(binary)});
                        $('cv-file-list').children[index].textContent = `${files[index].name} · recibiendo ${Math.round(100 * (offset + bytes.length) / files[index].size)}%`;
                        this.status(`Recibiendo ${index + 1}/${files.length}: ${Math.round(100 * (offset + bytes.length) / files[index].size)}%`);
                    }
                }
                if (!this.busy) return;
                this.job = await api('probe', {id:this.job.id});
                this.renderProbe();
                this.status('Inspección completa. Revisa la operación y las pérdidas antes de ejecutar.');
            } catch (error) {
                if (this.job) try { this.job = await api('cancel', {id:this.job.id}); } catch (_) { /* Keep the original error. */ }
                this.status(error.message || String(error)); $('cv-retry').hidden = false;
            } finally { this.busy = false; $('cv-cancel').disabled = !this.job || !['uploading', 'ready', 'running'].includes(this.job.state); }
        }
        renderProbe() {
            const info = this.job.info;
            $('cv-file-list').replaceChildren(...info.map(file => { const row = document.createElement('div'); row.textContent = `${file.name} · ${file.kind.toUpperCase()} · ${file.pages ? file.pages + ' páginas' : file.width + ' × ' + file.height + ' px'} · SHA-256 ${file.sha256.slice(0, 12)}…`; return row; }));
            const first = info[0], kinds = info.map(file => file.kind);
            const operations = first.kind === 'png' && info.length === 1 ? [['png-jpeg','PNG → JPEG']] : first.kind === 'jpeg' && info.length === 1 ? [['jpeg-png','JPEG → PNG']] : kinds.every(kind => kind === 'pdf') ? (info.length === 1 ? [['pdf-extract','Extraer páginas PDF']] : [['pdf-merge','Unir PDF']]) : [];
            $('cv-operation').replaceChildren(...operations.map(([id, label]) => new Option(label, id)));
            $('cv-run').disabled = !operations.length;
            const preview = $('cv-preview');
            preview.textContent = first.pages ? `Página 1: ${(first.page_sizes_pt[0][0] * 25.4 / 72).toFixed(0)} × ${(first.page_sizes_pt[0][1] * 25.4 / 72).toFixed(0)} mm. Los tamaños mixtos se conservan.` : `Imagen ${first.width} × ${first.height} px.`;
            if (!first.pages) { this.previewURL = URL.createObjectURL(this.files[0]); const image = document.createElement('img'); image.src = this.previewURL; image.alt = 'Vista previa de la imagen seleccionada'; preview.prepend(image); }
            $('cv-destination').textContent = 'Salida nueva en ' + this.job.output_directory + '. No se sobrescribe el original.';
            this.renderOperation();
        }
        renderOperation() {
            const operation = $('cv-operation').value;
            $('cv-image-options').hidden = operation !== 'png-jpeg';
            $('cv-pdf-options').hidden = operation !== 'pdf-extract';
            $('cv-loss').textContent = explanations[operation] || 'No hay ruta verificada para esta combinación.';
        }
        async run() {
            if (!this.job || this.job.state !== 'ready') return;
            const operation = $('cv-operation').value;
            const options = operation === 'png-jpeg' ? {background:$('cv-background').value, quality:Number($('cv-quality').value)} : operation === 'pdf-extract' ? {pages:$('cv-pages').value} : {};
            $('cv-run').disabled = true; $('cv-retry').hidden = true;
            try {
                this.job = await api('run', {id:this.job.id, operation, options});
                this.startedAt = Date.now();
                this.status(this.job.stage + ' · porcentaje no disponible');
                this.poll();
            } catch (error) { this.status(error.message || String(error)); $('cv-run').disabled = false; }
        }
        async poll() {
            try {
                this.job = await api('status', {id:this.job.id});
                this.status(this.job.stage + (this.job.state === 'running' ? ` · ${Math.floor((Date.now() - this.startedAt) / 1000)} s · porcentaje no disponible` : this.job.error ? ': ' + this.job.error : ''));
                if (this.job.state === 'running') this.poller = setTimeout(() => this.poll(), 500);
                else if (this.job.state === 'done') {
                    $('cv-result').hidden = false;
                    $('cv-result-detail').textContent = `${this.job.result.name} · ${(this.job.result.size / 1024).toFixed(1)} KB · SHA-256 ${this.job.result.sha256} · ${this.job.result.path}`;
                    $('cv-cancel').disabled = true;
                } else { $('cv-retry').hidden = false; $('cv-cancel').disabled = true; }
            } catch (error) { this.status(error.message || String(error)); $('cv-retry').hidden = false; }
        }
        async cancel() {
            this.busy = false;
            if (this.job) {
                try { this.job = await api('cancel', {id:this.job.id}); this.status(this.job.stage); }
                catch (error) { this.status(error.message || String(error)); }
            }
            $('cv-cancel').disabled = true; $('cv-retry').hidden = false;
        }
        async open() {
            if (!this.job || this.job.state !== 'done') return;
            try { await api('open', {id:this.job.id}); }
            catch (error) { this.status(error.message || String(error)); }
        }
        async history() {
            const root = $('cv-history'); root.textContent = 'Cargando historial…';
            try {
                const data = await api('history');
                root.replaceChildren(...data.results.map(result => { const item = document.createElement('div'); item.className = 'cv-history-item'; item.textContent = `${result.name} · ${result.path} · SHA-256 ${result.sha256.slice(0, 12)}… `; const button = document.createElement('button'); button.textContent = 'Abrir carpeta'; button.onclick = () => void api('open', {id:result.id}).catch(error => { item.textContent = error.message || String(error); }); item.append(button); return item; }));
                if (!data.results.length) root.textContent = 'Aún no hay resultados publicados.';
                for (const item of data.incomplete || []) { const row = document.createElement('div'); row.className = 'cv-history-item'; row.textContent = `Trabajo ${item.id.slice(0, 8)} · ${item.state === 'interrupted' ? 'interrumpido al cerrar Axx' : item.state === 'cancelled' ? 'cancelado' : 'fallido'} · sin salida publicada`; root.append(row); }
            } catch (error) { root.textContent = error.message || String(error); }
        }
    }
    A.converter = new Converter();
})();
