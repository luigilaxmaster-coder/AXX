/* Human code editing through the existing authenticated project/CAS services. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative?.() || !document.getElementById('view-agent')) return;
  const host = document.createElement('section');
  host.className = 'axx-code-studio'; host.hidden = true;
  host.innerHTML = `<h3>Code Studio</h3>
    <details data-code="project-settings" open><summary>Carpeta del proyecto</summary><form data-code="project-form"><label class="setting">Ruta local<input data-code="root" required placeholder="C:\\Proyectos\\mi-proyecto"></label><button type="submit">Abrir proyecto</button></form></details>
    <div class="quick-row"><button data-code="parent" type="button">Subir carpeta</button><button data-code="save" type="button" disabled>Guardar archivo</button><button data-code="diff" type="button" disabled>Comparar cambios</button></div>
    <p data-code="status" role="status" aria-live="polite">Abra una carpeta para editar sus archivos.</p>
    <nav data-code="browser" class="axx-code-browser" aria-label="Archivos del proyecto"></nav>
    <div data-code="tabs" class="axx-code-tabs" role="tablist" aria-label="Archivos abiertos"></div>
    <div data-code="editor" class="axx-code-editor" aria-label="Editor de código"></div>
    <div data-code="diff-editor" class="axx-code-editor" aria-label="Comparación de cambios" hidden></div>
    <details><summary>Git y pruebas</summary><div class="quick-row"><button data-code="git" type="button">Estado Git</button><button data-code="worktree" type="button">Crear worktree</button><button data-code="test" type="button">Ejecutar pruebas Python</button></div></details>
    <pre data-code="output" class="axx-code-output" tabindex="0" hidden></pre>`;
  const entry = document.createElement('button'); entry.type = 'button'; entry.textContent = 'Abrir Code Studio';
  entry.className = 'axx-code-entry';
  document.getElementById('view-agent').append(entry, host);
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'scripts/code-studio/code-ui.css'; document.head.append(css);
  const ui = key => host.querySelector(`[data-code="${key}"]`);
  const api = (method, path, body) => Axx.backendRequest(method, '/axx-api/code/v1/' + path, body);
  const status = text => { ui('status').textContent = text; };
  const output = text => { ui('output').hidden = false; ui('output').textContent = text; };
  const tabs = new Map(); let project = null, directory = '', active = null, editor = null, monaco = null, loading = null, diffEditor = null, originalModel = null;
  function setOpen(open) {
    host.hidden = !open; entry.textContent = open ? 'Cerrar Code Studio' : 'Abrir Code Studio';
    host.parentElement.classList.toggle('axx-code-active',open);
    Axx.resident?.schedule?.();
  }
  const attempt = async task => { try { await task(); } catch (error) { status(error.message || String(error)); } };
  const key = (id, path) => id + ':' + path;
  const language = path => ({py:'python',js:'javascript',cjs:'javascript',mjs:'javascript',ts:'typescript',json:'json',html:'html',css:'css',md:'markdown',rs:'rust'})[path.split('.').pop()] || 'plaintext';

  function loadEditor() {
    if (loading) return loading;
    loading = (async () => {
      const base = new URL('scripts/vendor/monaco-0.57.0-esm/',document.baseURI);
      window.MonacoEnvironment = {getWorker:() => new Worker(new URL('editor.worker.js',base),{type:'module'})};
      const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = new URL('editor.css',base).href;
      document.head.append(style);
      monaco = await import(new URL('editor.js',base).href);
      editor = monaco.editor.create(ui('editor'), {automaticLayout:true,minimap:{enabled:false},fontSize:13,
        theme:document.body.dataset.uiTheme === 'light' ? 'vs' : 'vs-dark',ariaLabel:'Código del archivo'});
      return editor;
    })().catch(error => { loading = null; throw error; });
    return loading;
  }
  function renderTabs() {
    ui('tabs').replaceChildren();
    for (const [id, tab] of tabs) {
      const button = document.createElement('button'); button.type = 'button'; button.role = 'tab';
      button.textContent = tab.path + (tab.dirty ? ' •' : ''); button.setAttribute('aria-selected', String(active === id));
      button.onclick = () => select(id); ui('tabs').append(button);
    }
  }
  function select(id) {
    active = id; const tab = tabs.get(id); editor.setModel(tab.model);
    ui('diff-editor').hidden = true;
    editor.updateOptions({readOnly:tab.read_only_degraded});
    ui('save').disabled = tab.read_only_degraded; ui('diff').disabled = false;
    status(tab.read_only_degraded ? tab.truncation_notice : tab.path + ' · ' + tab.encoding + ' · ' + tab.line_ending);
    renderTabs(); editor.focus();
  }
  async function openFile(path) {
    await loadEditor(); const id = key(project.project_id, path);
    if (!tabs.has(id)) {
      const doc = await api('POST', 'documents/read', {project_id:project.project_id,path});
      const tab = {...doc, base:doc.content, dirty:false, model:monaco.editor.createModel(doc.content,language(path))};
      tab.listener = tab.model.onDidChangeContent(() => { tab.dirty = tab.model.getValue() !== tab.base; renderTabs(); });
      tabs.set(id, tab);
    }
    select(id);
  }
  async function browse(path = '') {
    if (!project) throw new Error('Abra primero una carpeta.');
    const result = await api('GET','directory?project_id=' + encodeURIComponent(project.project_id) + '&path=' + encodeURIComponent(path));
    directory = path; ui('browser').replaceChildren();
    for (const item of result.entries) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = (item.directory ? '▸ ' : '') + item.name;
      button.onclick = () => attempt(() => item.directory ? browse(item.path) : openFile(item.path)); ui('browser').append(button);
    }
    if (!result.entries.length) ui('browser').textContent = 'Carpeta vacía o sin archivos accesibles.';
  }
  entry.onclick = () => attempt(async () => {
    setOpen(host.hidden);
    if (!host.hidden) {
      const flags = await Axx.evolution3.getFlags();
      const flag = flags.flags.find(flag => flag.flag_id === 'code_studio_v1');
      if (flag && !flag.enabled) {
        if (!confirm('¿Activar Code Studio para este perfil? Los archivos solo cambian al pulsar Guardar.')) {
          setOpen(false); return;
        }
        await Axx.evolution3.setFlag(flag.flag_id, true, flag.revision, 'user_code_studio_opt_in', 'manual-opt-in');
      }
      await loadEditor(); editor.layout();
    }
  });
  ui('project-form').onsubmit = event => { event.preventDefault(); void attempt(async () => {
    const root = ui('root').value.trim();
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(root));
    const id = 'project-' + [...new Uint8Array(digest)].slice(0,12).map(v=>v.toString(16).padStart(2,'0')).join('');
    project = await api('POST','projects/register',{project_id:id,project_root:root});
    ui('project-settings').open = false;
    await browse(); status('Proyecto abierto: ' + project.project_root);
  }); };
  ui('parent').onclick = () => attempt(() => browse(directory.split('/').slice(0,-1).join('/')));
  ui('save').onclick = () => attempt(async () => {
    const tab = tabs.get(active); if (!tab) return;
    const content = tab.model.getValue(); ui('save').disabled = true;
    try {
      const saved = await api('POST','documents/save',{project_id:tab.project_id,path:tab.path,new_content:content,expected_sha256:tab.sha256});
      tab.sha256 = saved.new_sha256; tab.base = content; tab.dirty = tab.model.getValue() !== content;
      renderTabs(); status(tab.dirty ? 'Guardado; hay cambios posteriores sin guardar.' : 'Archivo guardado y verificado en disco.');
    } finally { ui('save').disabled = Boolean(tab.read_only_degraded); }
  });
  ui('diff').onclick = () => {
    const tab = tabs.get(active); if (!tab) return;
    ui('diff-editor').hidden = false;
    if (!diffEditor) diffEditor = monaco.editor.createDiffEditor(ui('diff-editor'), {automaticLayout:true,readOnly:true,renderSideBySide:false,
      minimap:{enabled:false},theme:document.body.dataset.uiTheme === 'light' ? 'vs' : 'vs-dark'});
    diffEditor.setModel(null); originalModel?.dispose();
    originalModel = monaco.editor.createModel(tab.base,language(tab.path));
    diffEditor.setModel({original:originalModel,modified:tab.model}); diffEditor.layout();
  };
  ui('git').onclick = () => attempt(async () => {
    if (!project) throw new Error('Abra primero un proyecto Git.');
    const result = await api('GET','git/status?project_id=' + encodeURIComponent(project.project_id));
    output('HEAD: ' + result.head + '\n' + (result.dirty_files.join('\n') || 'Sin cambios pendientes.'));
  });
  ui('worktree').onclick = () => attempt(async () => {
    if (!project) throw new Error('Abra primero un proyecto Git.');
    const id = 'edit-' + crypto.randomUUID();
    const result = await api('POST','worktrees/create',{project_id:project.project_id,workspace_id:id,agent_id:'user',task_slug:id});
    output('Worktree creado. Abra esta carpeta para editarlo:\n' + result.worktree.worktree_path);
  });
  ui('test').onclick = () => attempt(async () => {
    if (!project) throw new Error('Abra primero un proyecto.');
    if (!confirm('¿Ejecutar las pruebas Python de esta carpeta? El código del proyecto se ejecutará con su cuenta.')) return;
    const flags = await Axx.evolution3.getFlags();
    const flag = flags.flags.find(flag => flag.flag_id === 'code_execution_v1');
    if (flag && !flag.enabled) await Axx.evolution3.setFlag(flag.flag_id,true,flag.revision,'user_test_execution_opt_in','manual-opt-in');
    status('Ejecutando pruebas…');
    const result = await api('POST','tests/run',{project_id:project.project_id,workspace_id:project.project_id,
      report_id:'test-' + crypto.randomUUID(),command:['python','-m','unittest','discover','-v']});
    output('Salida: ' + result.receipt.exit_code + '\n' + result.receipt.stdout_preview + '\n' + result.receipt.stderr_preview);
    status(result.receipt.passed ? 'Pruebas terminadas correctamente.' : 'Las pruebas detectaron errores.');
  });
  window.addEventListener('beforeunload', event => { if ([...tabs.values()].some(tab => tab.dirty)) { event.preventDefault(); event.returnValue = ''; } });
  Axx.codeStudio = {open:() => entry.click(), openFile, browse, get editor(){return editor;}, get diffEditor(){return diffEditor;}, get tabs(){return tabs;}};
})(window.Axx);
