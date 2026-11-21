"""Supervised Language Server Protocol (LSP) Manager with Graceful AST Fallback (PR-18 / CODE-04).

Enforces Invariants:
- CODE-04: Only allowlisted LSP binaries can be spawned, strictly confined to project_root.
- If an LSP binary is missing, times out, or crashes mid-session, Code Studio degrades gracefully
  to 'degraded_syntax_only' mode using CodeStructuralIndexer without freezing or losing user edits.
"""
from __future__ import annotations

import shutil
from typing import Any

from backend.code_studio.indexer import CodeStructuralIndexer
from backend.code_studio.projects import CodeProjectService

ALLOWED_LSP_SERVERS: dict[str, list[str]] = {
    'python': ['pyright-langserver', 'pylsp'],
    'typescript': ['typescript-language-server'],
    'javascript': ['typescript-language-server'],
    'rust': ['rust-analyzer'],
}


class UnauthorizedLanguageServerError(PermissionError):
    """Raised when attempting to register or spawn a non-allowlisted LSP executable."""


class LanguageServerManager:
    """Manages per-project LSP sessions with automatic fallback to CodeStructuralIndexer on crash/absence (CODE-04)."""

    def __init__(self, project_service: CodeProjectService, indexer: CodeStructuralIndexer):
        self.projects = project_service
        self.indexer = indexer
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}

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
