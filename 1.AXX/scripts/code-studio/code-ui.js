/* Human code editing through the existing authenticated project/CAS services. */
(function (Axx) {
  'use strict';
  if (!Axx?.isNative?.() || !document.getElementById('view-agent')) return;
  const host = document.createElement('section');
  host.className = 'axx-code-studio'; host.hidden = true;
  host.innerHTML = `<h3>Code Studio</h3>
    <details data-code="project-settings" open><summary>Carpeta del proyecto</summary><label class="setting">Proyecto guardado<select data-code="recent"><option value="">Seleccionar…</option></select></label><button data-code="open-recent" type="button">Abrir proyecto guardado</button><form data-code="project-form"><label class="setting">Ruta local<input data-code="root" required placeholder="C:\\Proyectos\\mi-proyecto"></label><button type="submit">Abrir proyecto</button></form></details>
    <div class="quick-row"><button data-code="parent" type="button">Subir carpeta</button><button data-code="save" type="button" disabled>Guardar archivo</button><button data-code="diff" type="button" disabled>Comparar con disco</button><button data-code="reload" type="button" disabled>Descartar borrador y recargar</button></div>
    <p data-code="status" role="status" aria-live="polite">Abra una carpeta para editar sus archivos.</p>
    <p data-code="draft-status" role="status" aria-live="polite"></p><nav data-code="drafts" aria-label="Borradores recuperables"></nav><div data-code="recovery" role="status"></div>
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
  const attempt = async task => { try { await task(); } catch (error) {
    status(error.message || String(error));
    if(project)try{await refreshRecovery();}catch{}
  } };
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
  function draftStatus(tab) {
    if (tabs.get(active) !== tab) return;
    ui('draft-status').textContent = tab.draftError || (tab.pending || tab.generation !== tab.ack ? 'Protegiendo borrador…' : tab.dirty ? 'Borrador protegido en este equipo.' : 'Sin cambios pendientes.');
  }
  async function persistDraft(tab) {
    clearTimeout(tab.timer);
    if (tab.pending) { await tab.pending; if(tab.generation!==tab.ack)return persistDraft(tab);return; }
    tab.pending = (async () => {
      do {
        const generation = tab.generation, content = tab.model.getValue();
        const saved = await api('POST','drafts/save',{project_id:tab.project_id,path:tab.path,
          expected_revision:tab.draftRevision,content:content === tab.base ? null : content,
          base_content:tab.base,base_sha256:tab.sha256,encoding:tab.encoding,line_ending:tab.line_ending});
        tab.draftRevision=saved.revision;tab.ack=generation;tab.draftError='';
      } while (tab.generation !== tab.ack);
    })();
    draftStatus(tab);
    try { await tab.pending; }
    catch(error) { tab.draftError='Borrador no protegido: '+(error.message||error); throw error; }
    finally { tab.pending=null;draftStatus(tab); }
  }
  function changed(tab) {
    if(tab.suppress||tab.read_only_degraded)return;
    tab.dirty=tab.model.getValue()!==tab.base;tab.generation++;renderTabs();draftStatus(tab);
    clearTimeout(tab.timer);tab.timer=setTimeout(()=>void persistDraft(tab).catch(()=>{}),250);
  }
  async function refreshProjects() {
    const result=await api('GET','projects');ui('recent').replaceChildren(new Option('Seleccionar…',''));
    for(const row of result.projects)ui('recent').append(new Option(row.project_root_ref,row.project_id));
  }
  async function refreshRecovery() {
    const result=await api('GET','file-transactions?project_id='+encodeURIComponent(project.project_id));ui('recovery').replaceChildren();
    for(const row of result.transactions.filter(r=>['prepared','recovery_conflict'].includes(r.state))) {
      const box=document.createElement('section'),label=document.createElement('p');label.textContent='Operación pendiente de resolución: '+row.state+' · '+(row.error||row.transaction_id);box.append(label);
      const retry=document.createElement('button');retry.textContent='Comprobar recuperación';retry.onclick=()=>attempt(async()=>{await api('POST','file-transactions/recover',{project_id:project.project_id});await refreshRecovery();status('Recuperación comprobada. Compare o recargue los archivos antes de guardar.');});box.append(retry);
      if(row.state==='recovery_conflict') {
        const keep=document.createElement('button');keep.textContent='Conservar archivos actuales';keep.onclick=()=>attempt(async()=>{
          if(!confirm('¿Conservar exactamente los archivos revisados y cerrar esta recuperación? No se sobrescribirá su contenido.'))return;
          await api('POST','file-transactions/acknowledge',{transaction_id:row.transaction_id,preserve_external:true,expected_hashes:Object.fromEntries(row.files.map(f=>[f.path,f.current_sha]))});await refreshRecovery();
        });box.append(keep);
      }
      ui('recovery').append(box);
    }
  }
  async function activateProject(value) {
    project=value;ui('root').value=project.project_root;ui('project-settings').open=false;
    await refreshProjects();ui('recent').value=project.project_id;
    await browse();const drafts=await api('GET','drafts?project_id='+encodeURIComponent(project.project_id));ui('drafts').replaceChildren();
    for(const draft of drafts.drafts){const button=document.createElement('button');button.textContent='Recuperar '+draft.relative_path;button.onclick=()=>attempt(()=>openFile(draft.relative_path));ui('drafts').append(button);}
    await refreshRecovery();status('Proyecto abierto: '+project.project_root);
  }
  ui('open-recent').onclick=()=>attempt(async()=>{
    const result=await api('GET','projects'),row=result.projects.find(p=>p.project_id===ui('recent').value);
    if(!row)throw Error('Seleccione un proyecto guardado.');
    await activateProject({project_id:row.project_id,project_root:row.project_root_ref});
  });
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
    ui('save').disabled = tab.read_only_degraded; ui('diff').disabled = false; ui('reload').disabled=false;
    status(tab.read_only_degraded ? tab.truncation_notice : tab.path + ' · ' + tab.encoding + ' · ' + tab.line_ending);
    renderTabs(); draftStatus(tab); editor.focus();
  }
  async function openFile(path) {
    const selectedProject=project;
    await loadEditor(); const id = key(selectedProject.project_id, path);
    if (!tabs.has(id)) {
      const draft=await api('GET','drafts?project_id='+encodeURIComponent(selectedProject.project_id)+'&path='+encodeURIComponent(path));
      let doc;
      try {doc=await api('POST','documents/read',{project_id:selectedProject.project_id,path});}
      catch(error){if(draft.content===null)throw error;doc={project_id:selectedProject.project_id,path,content:draft.base_content,sha256:draft.base_sha256,encoding:draft.encoding,line_ending:draft.line_ending,read_only_degraded:false};}
      const recovered=draft.content!==null && draft.content!==doc.content;
      const tab={...doc,base:recovered?draft.base_content:doc.content,sha256:recovered?draft.base_sha256:doc.sha256,
        encoding:recovered?draft.encoding:doc.encoding,line_ending:recovered?draft.line_ending:doc.line_ending,
        dirty:recovered,draftRevision:draft.revision,generation:0,ack:0,pending:null,draftError:'',
        model:monaco.editor.createModel(recovered?draft.content:doc.content,language(path))};
      tab.listener=tab.model.onDidChangeContent(()=>changed(tab));
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
        if (!confirm('¿Activar Code Studio para este perfil? Los borradores se guardan en este equipo para recuperarlos al reiniciar. Guardar modifica el archivo del proyecto.')) {
          setOpen(false); return;
        }
        await Axx.evolution3.setFlag(flag.flag_id, true, flag.revision, 'user_code_studio_opt_in', 'manual-opt-in');
      }
      await loadEditor(); editor.layout(); await refreshProjects();
    }
  });
  ui('project-form').onsubmit = event => { event.preventDefault(); void attempt(async () => {
    const root = ui('root').value.trim();
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(root));
    const id = 'project-' + [...new Uint8Array(digest)].slice(0,12).map(v=>v.toString(16).padStart(2,'0')).join('');
    await activateProject(await api('POST','projects/register',{project_id:id,project_root:root}));
  }); };
  ui('parent').onclick = () => attempt(() => browse(directory.split('/').slice(0,-1).join('/')));
  ui('save').onclick = () => attempt(async () => {
    const tab = tabs.get(active); if (!tab) return;
    const content = tab.model.getValue(); ui('save').disabled = true;
    try {
      const saved = await api('POST','documents/save',{project_id:tab.project_id,path:tab.path,new_content:content,expected_sha256:tab.sha256});
      tab.sha256 = saved.new_sha256; tab.base = content; tab.dirty = tab.model.getValue() !== content;
      tab.generation++;try{await persistDraft(tab);}catch(error){status('Archivo guardado en disco; borrador pendiente: '+(error.message||error));return;}renderTabs(); status(tab.dirty ? 'Guardado; hay cambios posteriores sin guardar.' : 'Archivo guardado y verificado en disco.');
    } finally { ui('save').disabled = Boolean(tab.read_only_degraded); }
  });
  ui('diff').onclick = () => attempt(async () => {
    const tab = tabs.get(active); if (!tab) return;
    ui('diff-editor').hidden = false;
    if (!diffEditor) diffEditor = monaco.editor.createDiffEditor(ui('diff-editor'), {automaticLayout:true,readOnly:true,renderSideBySide:false,
      minimap:{enabled:false},theme:document.body.dataset.uiTheme === 'light' ? 'vs' : 'vs-dark'});
    diffEditor.setModel(null); originalModel?.dispose();
    const disk=await api('POST','documents/read',{project_id:tab.project_id,path:tab.path});
    originalModel = monaco.editor.createModel(disk.content,language(tab.path));
    diffEditor.setModel({original:originalModel,modified:tab.model}); diffEditor.layout();
  });
  ui('reload').onclick=()=>attempt(async()=>{
    const tab=tabs.get(active);if(!tab)return;
    if(tab.dirty&&!confirm('¿Descartar este borrador y cargar el contenido actual del disco?'))return;
    await persistDraft(tab);const doc=await api('POST','documents/read',{project_id:tab.project_id,path:tab.path});
    const cleared=await api('POST','drafts/save',{project_id:tab.project_id,path:tab.path,expected_revision:tab.draftRevision,content:null});
    tab.draftRevision=cleared.revision;tab.base=doc.content;tab.sha256=doc.sha256;tab.encoding=doc.encoding;tab.line_ending=doc.line_ending;
    tab.suppress=true;try{tab.model.setValue(doc.content);}finally{tab.suppress=false;}tab.dirty=false;tab.generation++;tab.ack=tab.generation;select(active);
  });
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
  Axx.codeStudio = {flushDrafts:() => Promise.all([...tabs.values()].filter(t=>!t.read_only_degraded).map(t=>persistDraft(t))),open:() => entry.click(), openFile, browse, get editor(){return editor;}, get diffEditor(){return diffEditor;}, get tabs(){return tabs;}};
})(window.Axx);
