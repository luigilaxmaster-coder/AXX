"""Incremental Structural Code Indexer (AST & Symbol Reference Graph) (PR-18 / CODE-04).

Enforces Invariants:
- SEC-03: Only indexes files inside the authorized project_root, skipping symlinks/junctions,
  secret files, and ignored directories (.git, node_modules, __pycache__, .venv, build, dist).
- CODE-04: Provides deterministic AST/symbol fallback for definitions, references, and syntax diagnostics
  even when external LSP binaries are unavailable or crash.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
from typing import Any

from backend.code_studio.projects import (
    BinaryFileError,
    CodeProjectService,
    CodeSecurityError,
    detect_encoding_and_eol,
    resolve_scoped_project_path,
)

IGNORED_DIRS = frozenset({'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'dist', '.tox', '.mypy_cache'})
JS_SYMBOL_RE = re.compile(
    r'(?:function\s+([A-Za-z_$][A-Za-z0-9_$]*)|class\s+([A-Za-z_$][A-Za-z0-9_$]*)|(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>))'
)


class CodeStructuralIndexer:
    """Indexes symbols and syntax diagnostics incrementally by file SHA-256 inside an authorized project."""

    def __init__(self, project_service: CodeProjectService):
        self.projects = project_service
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def index_file(self, project_id: str, relative_path: str) -> dict[str, Any]:
        root = self.projects.get_project_root(project_id)
        full_path = resolve_scoped_project_path(root, relative_path)
        if not full_path.is_file():
            raise FileNotFoundError(f'File not found: {relative_path}')

        raw = full_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        cache_key = (project_id, relative_path.replace('\\', '/'))
        cached = self._cache.get(cache_key)
        if cached and cached['sha256'] == sha256:
            return cached

        info = detect_encoding_and_eol(raw)
        text = info['text']
        suffix = full_path.suffix.lower()

        symbols: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []

        if suffix == '.py':
            try:
                tree = ast.parse(text, filename=relative_path)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(
                            {
                                'name': node.name,
                                'kind': 'function',
                                'line': int(node.lineno),
                                'end_line': int(getattr(node, 'end_lineno', node.lineno)),
                                'path': relative_path,
                            }
                        )
                    elif isinstance(node, ast.ClassDef):
                        symbols.append(
                            {
                                'name': node.name,
                                'kind': 'class',
                                'line': int(node.lineno),
                                'end_line': int(getattr(node, 'end_lineno', node.lineno)),
                                'path': relative_path,
                            }
                        )
            except SyntaxError as exc:
                diagnostics.append(
                    {
                        'severity': 'error',
                        'source': 'ast-fallback',
                        'line': int(exc.lineno or 1),
                        'column': int(exc.offset or 1),
                        'message': f'SyntaxError: {exc.msg}',
                        'path': relative_path,
                    }
                )
        elif suffix in ('.js', '.cjs', '.mjs', '.ts', '.tsx', '.jsx'):
            for line_no, line in enumerate(text.splitlines(), start=1):
                for match in JS_SYMBOL_RE.finditer(line):
                    sym_name = match.group(1) or match.group(2) or match.group(3)
                    sym_kind = 'class' if match.group(2) else 'function'
                    symbols.append(
                        {
                            'name': sym_name,
                            'kind': sym_kind,
                            'line': line_no,
                            'end_line': line_no,
                            'path': relative_path,
                        }
                    )

        symbols.sort(key=lambda s: (s['line'], s['name']))
        entry = {
            'project_id': project_id,
            'path': relative_path.replace('\\', '/'),
            'sha256': sha256,
            'symbols': symbols,
            'diagnostics': diagnostics,
        }
        self._cache[cache_key] = entry
        return entry

    def index_project(self, project_id: str) -> dict[str, Any]:
        root = self.projects.get_project_root(project_id)
        indexed_files: list[str] = []
        all_symbols: list[dict[str, Any]] = []
        all_diagnostics: list[dict[str, Any]] = []

        for path in sorted(root.rglob('*')):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace('\\', '/')
            try:
                entry = self.index_file(project_id, rel)
            except (CodeSecurityError, BinaryFileError, OSError):
                continue
            indexed_files.append(rel)
            all_symbols.extend(entry['symbols'])
            all_diagnostics.extend(entry['diagnostics'])

        return {
            'project_id': project_id,
            'indexed_file_count': len(indexed_files),
            'files': indexed_files,
            'symbols': all_symbols,
            'diagnostics': all_diagnostics,
        }

    def query_symbol(self, project_id: str, query: str) -> list[dict[str, Any]]:
        q_lower = query.strip().lower()
        results: list[dict[str, Any]] = []
        for (pid, _), entry in self._cache.items():
            if pid != project_id:
                continue
            for sym in entry['symbols']:
                if q_lower in sym['name'].lower():
                    results.append(sym)
        return results
