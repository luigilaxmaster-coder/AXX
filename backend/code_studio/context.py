"""Bounded, provenance-bearing model context and strict incremental code edits.

Uses the existing project scope, indexer and Git service. Model output is data;
only CodePatchEngine performs journaled writes after the normal grant checks.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from backend.code_studio.projects import CodeConflictError, CodeSecurityError

MAX_CONTEXT_BYTES = 64000
MAX_FILES = 8
_SECRET = re.compile(
    r'(?im)((?:api[_-]?key|access[_-]?token|password|secret|authorization)\s*[=:]\s*[\x22\x27]?)([^\s\x22\x27,;]{8,})'
    r'|\b(?:sk-(?:proj-)?|gh[pousr]_)[A-Za-z0-9_-]{16,}'
    r'|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'
)


def redact_code(text: str) -> str:
    return _SECRET.sub(lambda m: (m.group(1) or '') + '[REDACTED]', text)


class CodeContextService:
    def __init__(self, projects, git, indexer):
        self.projects, self.git, self.indexer = projects, git, indexer
        with projects.lock, projects._connect() as db:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS code_context_packets '
                           '(sha256 TEXT PRIMARY KEY, packet_json TEXT NOT NULL, expires_at_ms INTEGER NOT NULL)')

    def get(self, sha256: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute('SELECT packet_json FROM code_context_packets WHERE sha256=? AND expires_at_ms>?',
                             (sha256, self.projects.clock())).fetchone()
        if row is None:
            raise CodeConflictError('Context expired or unknown; build a fresh context before delegating')
        return json.loads(row['packet_json'])

    def build(self, project_id: str, selections: list[dict[str, Any]], *, act_id: str | None = None,
              allowed_tools: list[str] | None = None) -> dict[str, Any]:
        if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_FILES:
            raise ValueError(f'selections must contain 1..{MAX_FILES} files')
        root = self.projects.get_project_root(project_id)
        base_commit = self.git.get_head_commit(root)
        branch = self.git._run_git(root, ['rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip()
        files, seen = [], set()
        for selection in selections:
            if not isinstance(selection, dict) or not isinstance(selection.get('path'), str):
                raise ValueError('Each selection needs a path')
            names = selection['path'].replace('\\', '/').casefold().split('/')
            if any(name.startswith('.env') or name in ('.ssh', '.aws', '.azure', '.kube')
                   or name.endswith(('.pem', '.key', '.p12', '.pfx', '.dpapi')) for name in names):
                raise CodeSecurityError('Credential files cannot be shared as model context')
            doc = self.projects.read_document(project_id, selection['path'])
            path = doc['path'].replace('\\', '/')
            if path.casefold() in seen:
                raise ValueError('Duplicate file in context')
            seen.add(path.casefold())
            if doc.get('truncated'):
                raise ValueError('Truncated files cannot be delegated')
            if selection.get('sha256') and selection['sha256'] != doc['sha256']:
                raise CodeConflictError('The selected file changed; reload it before delegating')
            lines = doc['content'].splitlines(keepends=True)
            start, end = selection.get('start_line', 1), selection.get('end_line', max(1, len(lines)))
            if (type(start) is not int or type(end) is not int or start < 1
                    or end < start or end > max(1, len(lines))):
                raise ValueError('Invalid selection line range')
            content = redact_code(''.join(lines[start - 1:end]))
            index = self.indexer.index_file(project_id, path)
            if index['sha256'] != doc['sha256']:
                raise CodeConflictError('The file changed while indexing its context')
            files.append({
                'path': path, 'source_path': path, 'sha256': doc['sha256'],
                'encoding': doc['encoding'], 'line_ending': doc['line_ending'],
                'start_line': start, 'end_line': end, 'content': content,
                'complete_file': start == 1 and end == max(1, len(lines)),
                'redacted': content != ''.join(lines[start - 1:end]),
                'symbols': index['symbols'][:100], 'diagnostics': index['diagnostics'][:100],
            })
        if self.git.get_head_commit(root) != base_commit:
            raise CodeConflictError('Git HEAD changed while building context')
        packet = {'schema_version': '1.0', 'project_id': project_id, 'act_id': act_id,
                  'base_commit': base_commit, 'branch': branch,
                  'working_tree_status': self.git.detect_dirty_files(root),
                  'read_at_ms': self.projects.clock(), 'files': files,
                  'allowed_tools': list(allowed_tools or []),
                  'constraints': ['Only selected files', 'No shell from model text',
                                  'Apply in own worktree; review before integration'],
                  'secret_policy': 'Common credential patterns redacted; excluded paths enforced by project scope'}
        raw = json.dumps(packet, ensure_ascii=False, sort_keys=True).encode('utf-8')
        if len(raw) > MAX_CONTEXT_BYTES:
            raise ValueError('Context exceeds 64 KB; select smaller ranges or fewer files')
        packet['packet_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute('DELETE FROM code_context_packets WHERE expires_at_ms<=?', (self.projects.clock(),))
                db.execute('INSERT OR IGNORE INTO code_context_packets VALUES (?, ?, ?)',
                           (packet['packet_sha256'], json.dumps(packet, ensure_ascii=False),
                            self.projects.clock() + 3600000))
        return packet


def incremental_content(current: str, edit: dict[str, Any]) -> str:
    """Apply exact old/new hunks in memory. Ambiguous or overlapping edits fail closed."""
    if 'new_content' in edit:
        if 'hunks' in edit or not isinstance(edit['new_content'], str):
            raise ValueError('Use either new_content or hunks')
        return edit['new_content']
    hunks = edit.get('hunks')
    if not isinstance(hunks, list) or not 1 <= len(hunks) <= 128:
        raise ValueError('An incremental edit needs 1..128 hunks')
    current = current.replace('\r\n', '\n')
    replacements = []
    for hunk in hunks:
        if (not isinstance(hunk, dict) or set(hunk) != {'old_text', 'new_text'}
                or not isinstance(hunk['old_text'], str) or not hunk['old_text']
                or not isinstance(hunk['new_text'], str)):
            raise ValueError('Each hunk needs nonempty old_text and new_text')
        old, new = hunk['old_text'].replace('\r\n', '\n'), hunk['new_text'].replace('\r\n', '\n')
        pos = current.find(old)
        if pos < 0 or current.find(old, pos + 1) >= 0:
            raise CodeConflictError('Hunk context is missing or ambiguous')
        replacements.append((pos, pos + len(old), new))
    replacements.sort()
    if any(a[1] > b[0] for a, b in zip(replacements, replacements[1:])):
        raise CodeConflictError('Overlapping hunks')
    for start, end, text in reversed(replacements):
        current = current[:start] + text + current[end:]
    return current


def parse_model_edits(text: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind a model proposal to an exact packet and its original file hashes.

Legacy single-file fenced output remains supported only for a complete,
unredacted file. JSON proposals cannot escape the selected paths or omit CAS.
"""
    blocks = re.findall(r'```[^\n]*\n([\s\S]*?)```', text)
    candidate = text.strip() if text.strip().startswith('{') else (blocks[-1].strip() if blocks else '')
    try:
        proposal = json.loads(candidate)
    except json.JSONDecodeError:
        if len(packet['files']) != 1 or len(blocks) != 1:
            raise ValueError('Return one JSON proposal with file_edits') from None
        doc = packet['files'][0]
        if doc['redacted'] or not doc['complete_file']:
            raise CodeSecurityError('Partial/redacted context requires incremental JSON hunks')
        return [{'path': doc['path'], 'new_content': blocks[0], 'expected_base_sha256': doc['sha256']}]
    if not isinstance(proposal, dict) or proposal.get('context_sha256') != packet['packet_sha256']:
        raise CodeConflictError('Proposal does not reference the current context packet')
    edits = proposal.get('file_edits')
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_FILES:
        raise ValueError('file_edits must contain 1..8 edits')
    by_path = {f['path']: f for f in packet['files']}
    seen, validated = set(), []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) - {'path', 'expected_base_sha256', 'hunks', 'new_content'}:
            raise ValueError('Invalid file edit fields')
        path = edit.get('path')
        if not isinstance(path, str) or path not in by_path or path in seen:
            raise CodeSecurityError('Proposal contains an unselected or duplicate file')
        seen.add(path)
        if edit.get('expected_base_sha256') != by_path[path]['sha256']:
            raise CodeConflictError('Proposal base hash does not match its context')
        if (by_path[path]['redacted'] or not by_path[path]['complete_file']) and 'new_content' in edit:
            raise CodeSecurityError('Partial/redacted files require incremental hunks')
        validated.append(edit)
    return validated
