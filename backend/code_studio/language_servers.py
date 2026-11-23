"""Supervised Language Server Protocol (LSP) Manager with Graceful AST Fallback (PR-18 / CODE-04).

Enforces Invariants:
- CODE-04: Only allowlisted LSP binaries can be spawned, strictly confined to project_root.
- If an LSP binary is missing, times out, or crashes mid-session, Code Studio degrades gracefully
  to 'degraded_syntax_only' mode using CodeStructuralIndexer without freezing or losing user edits.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.parse
from typing import Any

from backend.code_studio.indexer import CodeStructuralIndexer
from backend.code_studio.projects import CodeProjectService, resolve_scoped_project_path

ALLOWED_LSP_SERVERS: dict[str, list[str]] = {
    'python': ['pyright-langserver', 'pylsp'],
    'typescript': ['typescript-language-server'],
    'javascript': ['typescript-language-server'],
    'rust': ['rust-analyzer'],
}


LSP_QUERIES = ('hover', 'definition', 'references')
LSP_ARGS = {'pyright-langserver': ['--stdio'], 'typescript-language-server': ['--stdio'], 'pylsp': [], 'rust-analyzer': []}
MAX_FRAME = 8 * 1024 * 1024


class UnauthorizedLanguageServerError(PermissionError):
    """Raised when attempting to register or spawn a non-allowlisted LSP executable."""


def _works(binary: str) -> bool:
    """A PATH entry is not enough: rustup proxies exist without the component and fail at launch."""
    exe = shutil.which(binary)
    if not exe:
        return False
    try:
        return subprocess.run([exe, '--version'], capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class LspProcess:
    """One JSON-RPC stdio connection to an allowlisted language server, confined to the project root."""

    def __init__(self, command: list[str], root: Path, *, timeout: float = 15.0):
        self.root, self.next_id, self.lock = root, 0, threading.Lock()
        self.pending: dict[int, dict[str, Any]] = {}
        self.diagnostics: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, int] = {}
        self.changed = threading.Condition()
        self.proc = subprocess.Popen(command, cwd=str(root), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self._read, daemon=True).start()
        self.capabilities = self.request('initialize', {
            'processId': None, 'rootUri': root.as_uri(), 'workspaceFolders': [{'uri': root.as_uri(), 'name': root.name}],
            'capabilities': {'textDocument': {'publishDiagnostics': {}, 'synchronization': {'didSave': False},
                                              'completion': {'completionItem': {'snippetSupport': False}}}}},
            timeout=timeout).get('capabilities', {})
        self.notify('initialized', {})

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def _send(self, message: dict[str, Any]) -> None:
        data = json.dumps({'jsonrpc': '2.0', **message}).encode('utf-8')
        with self.lock:
            self.proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(data) + data)
            self.proc.stdin.flush()

    def _read(self) -> None:
        out = self.proc.stdout
        try:
            while True:
                length = None
                while True:
                    line = out.readline()
                    if not line:
                        return
                    if line in (b'\r\n', b'\n'):
                        break
                    if line.lower().startswith(b'content-length:'):
                        length = int(line.split(b':', 1)[1])
                if length is None or length > MAX_FRAME:
                    return  # malformed or oversized frame: stop reading; callers time out and degrade
                self._dispatch(json.loads(out.read(length)))
        except (OSError, ValueError):
            return
        finally:
            with self.changed:
                self.changed.notify_all()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if 'id' in msg and 'method' in msg:  # server → client request: answer so the server never blocks on us
            items = (msg.get('params') or {}).get('items') or []
            self._send({'id': msg['id'], 'result': [None] * len(items) if msg['method'] == 'workspace/configuration' else None})
        elif 'id' in msg:
            waiter = self.pending.get(msg['id'])
            if waiter:
                waiter['response'] = msg
                waiter['event'].set()
        elif msg.get('method') == 'textDocument/publishDiagnostics':
            params = msg.get('params') or {}
            with self.changed:
                self.diagnostics[params.get('uri', '')] = {'items': params.get('diagnostics') or [], 'at': time.monotonic()}
                self.changed.notify_all()

    def request(self, method: str, params: dict[str, Any], *, timeout: float = 5.0) -> Any:
        self.next_id += 1
        rid, waiter = self.next_id, {'event': threading.Event()}
        self.pending[rid] = waiter
        try:
            self._send({'id': rid, 'method': method, 'params': params})
            if not waiter['event'].wait(timeout):
                raise TimeoutError(f'{method} sin respuesta del servidor de lenguaje')
        finally:
            self.pending.pop(rid, None)
        if 'error' in waiter['response']:
            raise RuntimeError(str(waiter['response']['error'].get('message', 'LSP error'))[:300])
        return waiter['response'].get('result')

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({'method': method, 'params': params})

    def sync(self, uri: str, language: str, text: str, *, wait: float) -> list[dict[str, Any]]:
        started = time.monotonic()
        if uri in self.versions:
            self.versions[uri] += 1
            self.notify('textDocument/didChange', {'textDocument': {'uri': uri, 'version': self.versions[uri]},
                                                   'contentChanges': [{'text': text}]})
        else:
            self.versions[uri] = 1
            self.notify('textDocument/didOpen', {'textDocument': {'uri': uri, 'languageId': language, 'version': 1, 'text': text}})
        deadline = started + wait
        at = lambda: self.diagnostics.get(uri, {}).get('at', 0)
        with self.changed:  # servers publish more than once per edit: return once publishes go quiet for 300 ms
            self.changed.wait_for(lambda: at() >= started or not self.alive, wait)
            while self.alive and at() >= started and time.monotonic() < deadline:
                last = at()
                if not self.changed.wait_for(lambda: at() != last or not self.alive, min(.3, max(0, deadline - time.monotonic()))):
                    break
            return list(self.diagnostics.get(uri, {}).get('items', []))

    def close(self) -> None:
        try:
            if self.alive:
                self.request('shutdown', {}, timeout=2)
                self.notify('exit', {})
                self.proc.wait(timeout=3)
        except (OSError, TimeoutError, RuntimeError, subprocess.TimeoutExpired):
            pass
        if self.alive:
            self.proc.kill()


class LanguageServerManager:
    """Manages per-project LSP sessions with automatic fallback to CodeStructuralIndexer on crash/absence (CODE-04)."""

    def __init__(self, project_service: CodeProjectService, indexer: CodeStructuralIndexer):
        self.projects = project_service
        self.indexer = indexer
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.processes: dict[tuple[str, str], LspProcess] = {}
        self.commands: dict[str, list[str]] = {}  # binary → command override (tests, absolute paths)

    def probe_available_servers(self) -> dict[str, Any]:
        """Discover allowlisted LSP binaries installed on the machine; returns UNAVAILABLE when missing."""
        servers: dict[str, Any] = {}
        for lang, binaries in ALLOWED_LSP_SERVERS.items():
            found = next((b for b in binaries if b in self.commands or _works(b)), None)
            servers[lang] = {
                'language': lang,
                'binary': found,
                'installed': found is not None,
                'status': 'available' if found else 'UNAVAILABLE',
                'ast_fallback': True,
            }
        return {'servers': servers}

    def start_language_server(
        self,
        *,
        project_id: str,
        language: str,
        preferred_binary: str | None = None,
    ) -> dict[str, Any]:
        lang = language.strip().lower()
        if lang not in ALLOWED_LSP_SERVERS:
            raise UnauthorizedLanguageServerError(f'Unsupported or non-allowlisted LSP language: {language!r}')

        allowed_bins = ALLOWED_LSP_SERVERS[lang]
        if preferred_binary is not None and preferred_binary not in allowed_bins:
            raise UnauthorizedLanguageServerError(
                f'LSP binary {preferred_binary!r} is not in allowlist for {lang}: {allowed_bins}'
            )

        root = self.projects.get_project_root(project_id)
        candidates = [preferred_binary] if preferred_binary else allowed_bins
        resolved_exe = None
        for bin_name in candidates:
            if bin_name and shutil.which(bin_name):
                resolved_exe = bin_name
                break

        key = (project_id, lang)
        if resolved_exe is None:
            session = {
                'project_id': project_id,
                'language': lang,
                'project_root': str(root),
                'binary': None,
                'status': 'degraded_syntax_only',
                'degraded': True,
                'degraded_reason': f'No allowlisted LSP binary found on host for {lang} ({candidates}); using structural AST fallback.',
            }
        else:
            session = {
                'project_id': project_id,
                'language': lang,
                'project_root': str(root),
                'binary': resolved_exe,
                'status': 'degraded_syntax_only',
                'degraded': True,
                'degraded_reason': 'LSP executable detected; no protocol process is connected. Using structural AST.',
            }
        self.sessions[key] = session
        return dict(session)

    def _process(self, project_id: str, lang: str) -> LspProcess | None:
        key = (project_id, lang)
        proc = self.processes.get(key)
        if proc is not None and proc.alive:
            return proc
        root = self.projects.get_project_root(project_id)
        for binary in ALLOWED_LSP_SERVERS[lang]:
            command = self.commands.get(binary)
            if command is None and _works(binary):
                command = [shutil.which(binary), *LSP_ARGS[binary]]
            if command is None:
                continue
            try:
                proc = LspProcess(command, root)
            except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
                self.sessions[key] = {'project_id': project_id, 'language': lang, 'project_root': str(root), 'binary': binary,
                                      'status': 'degraded_syntax_only', 'degraded': True,
                                      'degraded_reason': f'{binary} no arrancó: {exc}'[:300]}
                continue
            self.processes[key] = proc
            self.sessions[key] = {'project_id': project_id, 'language': lang, 'project_root': str(root), 'binary': binary,
                                  'status': 'live', 'degraded': False, 'degraded_reason': ''}
            return proc
        return None

    def _live(self, project_id: str, language: str, relative_path: str):
        lang = language.strip().lower()
        if lang not in ALLOWED_LSP_SERVERS:
            raise UnauthorizedLanguageServerError(f'Unsupported or non-allowlisted LSP language: {language!r}')
        uri = resolve_scoped_project_path(self.projects.get_project_root(project_id), relative_path).as_uri()
        return lang, uri, self._process(project_id, lang)

    def sync_document(self, *, project_id: str, language: str, relative_path: str, content: str) -> dict[str, Any]:
        """Send the editor buffer to the live server and return its published diagnostics, or the AST fallback."""
        lang, uri, proc = self._live(project_id, language, relative_path)
        if proc is not None:
            try:
                return {'lsp_status': 'live', 'binary': self.sessions[(project_id, lang)]['binary'],
                        'diagnostics': proc.sync(uri, lang, content, wait=4.0)}
            except (OSError, TimeoutError, RuntimeError) as exc:
                proc.close()
                self.simulate_crash_or_disconnect(project_id, lang, f'El servidor de lenguaje falló: {exc}'[:300])
        return {**self.get_document_symbols_and_diagnostics(project_id=project_id, language=lang, relative_path=relative_path),
                'lsp_status': 'degraded_syntax_only'}

    def complete(self, *, project_id: str, language: str, relative_path: str, line: int, character: int) -> dict[str, Any]:
        lang, uri, proc = self._live(project_id, language, relative_path)
        if proc is None or uri not in proc.versions:
            return {'lsp_status': 'degraded_syntax_only', 'items': []}
        try:
            result = proc.request('textDocument/completion', {'textDocument': {'uri': uri},
                                                              'position': {'line': int(line), 'character': int(character)}})
        except (OSError, TimeoutError, RuntimeError):
            return {'lsp_status': 'live', 'items': []}
        items = result.get('items', []) if isinstance(result, dict) else (result or [])
        return {'lsp_status': 'live', 'items': [{'label': str(i.get('label', ''))[:200], 'kind': i.get('kind'),
                                                 'detail': str(i.get('detail') or '')[:200],
                                                 'insertText': str(i.get('insertText') or i.get('label', ''))[:2000]}
                                                for i in items[:200] if isinstance(i, dict)]}

    def query(self, *, project_id: str, language: str, relative_path: str, method: str, line: int, character: int) -> dict[str, Any]:
        """hover / definition / references for the open buffer; locations outside the project root are dropped."""
        if method not in LSP_QUERIES:
            raise ValueError(f'Consulta LSP no permitida: {method!r}')
        lang, uri, proc = self._live(project_id, language, relative_path)
        if proc is None or uri not in proc.versions:
            return {'lsp_status': 'degraded_syntax_only', 'result': None}
        params = {'textDocument': {'uri': uri}, 'position': {'line': int(line), 'character': int(character)}}
        if method == 'references':
            params['context'] = {'includeDeclaration': True}
        try:
            result = proc.request('textDocument/' + method, params)
        except (OSError, TimeoutError, RuntimeError):
            return {'lsp_status': 'live', 'result': None}
        if method == 'hover':
            contents = (result or {}).get('contents') if isinstance(result, dict) else None
            parts = contents if isinstance(contents, list) else [contents]
            text = '\n\n'.join(p.get('value', '') if isinstance(p, dict) else str(p) for p in parts if p)
            return {'lsp_status': 'live', 'result': {'markdown': text[:8000]} if text else None}
        root = proc.root.as_uri()
        locations = result if isinstance(result, list) else [result] if isinstance(result, dict) else []
        kept = []
        for loc in locations[:200]:
            target = loc.get('uri') or loc.get('targetUri') or ''
            rng = loc.get('range') or loc.get('targetSelectionRange') or loc.get('targetRange')
            if target.startswith(root + '/') and isinstance(rng, dict):
                kept.append({'path': urllib.parse.unquote(target[len(root) + 1:]), 'range': rng})
        return {'lsp_status': 'live', 'result': kept}

    def close(self) -> None:
        for proc in self.processes.values():
            proc.close()
        self.processes.clear()

    def simulate_crash_or_disconnect(self, project_id: str, language: str, reason: str = 'LSP process exited unexpectedly') -> dict[str, Any]:
        """Handle an unexpected LSP crash by transitioning cleanly to degraded_syntax_only mode (CODE-04)."""
        key = (project_id, language.strip().lower())
        session = self.sessions.get(key)
        if not session:
            session = self.start_language_server(project_id=project_id, language=language)
        session['status'] = 'degraded_syntax_only'
        session['degraded'] = True
        session['degraded_reason'] = reason
        return dict(session)

    def get_document_symbols_and_diagnostics(
        self,
        *,
        project_id: str,
        language: str,
        relative_path: str,
    ) -> dict[str, Any]:
        """Return symbols and diagnostics for a document, falling back seamlessly to CodeStructuralIndexer if LSP is degraded (CODE-04)."""
        key = (project_id, language.strip().lower())
        session = self.sessions.get(key)
        if not session:
            session = self.start_language_server(project_id=project_id, language=language)

        indexed = self.indexer.index_file(project_id, relative_path)
        return {
            'project_id': project_id,
            'path': relative_path,
            'lsp_status': session['status'],
            'degraded': session['degraded'],
            'degraded_reason': session['degraded_reason'],
            'editor_usable': True,
            'symbols': indexed['symbols'],
            'diagnostics': indexed['diagnostics'],
        }
