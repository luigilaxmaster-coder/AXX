"""Validate internal machine-readable documentation, without modifying AXX.

Usage: python qa/validate_bundle.py
Requires: Python stdlib. Optional: jsonschema (for semantic example checks).
This is NOT a product acceptance or Windows test.
"""
from __future__ import annotations
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    schemas: dict[str, dict] = {}
    for path in sorted((ROOT / 'schemas').glob('*.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            assert payload.get('$schema') == 'https://json-schema.org/draft/2020-12/schema'
            schemas[path.name] = payload
        except (ValueError, AssertionError) as exc:
            errors.append(f'{path.name}: {exc}')
    manifest = json.loads((ROOT / 'records/upstream-lock.json').read_text(encoding='utf-8'))
    for entry in manifest['entries']:
        if entry['verified_commit'] and (not isinstance(entry.get('commit'), str) or len(entry['commit']) != 40):
            errors.append(f'Incomplete pinned SHA for {entry["repository"]}')
        if not entry['verified_commit'] and entry.get('commit') is not None:
            errors.append(f'Unverified commit represented as pinned: {entry["repository"]}')
    with (ROOT / 'qa/acceptance-matrix.csv').open(encoding='utf-8',newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 30 or len({row['test_id'] for row in rows}) != len(rows):
        errors.append('QA matrix incomplete or duplicated IDs')
    for row in rows:
        if row['status'] not in ('NOT_RUN','PASS','FAIL','SKIPPED','BLOCKED'):
            errors.append(f'Invalid QA status {row["test_id"]}: {row["status"]}')
    con = sqlite3.connect(':memory:')
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY)')
    try:
        con.executescript((ROOT / 'sql/001_agent_foundation.sql').read_text(encoding='utf-8'))
        problems = con.execute('PRAGMA foreign_key_check').fetchall()
        if problems:
            errors.append(f'Foreign-key issues: {problems[:3]}')
        # smoke: bind to actual legacy-shaped synthetic chat and delete it (membership should cascade)
        con.execute('INSERT INTO chat_conversations(id) VALUES (?)', ('chat-fixture',))
        con.execute('INSERT INTO agent_profiles (agent_id,name,role,created_at_ms,updated_at_ms) VALUES (?,?,?,?,?)', ('a1','Axx Demo','tester',1,1))
        con.execute('INSERT INTO agent_conversation_links (conversation_id,agent_id,membership_role,created_at_ms) VALUES (?,?,?,?)', ('chat-fixture','a1','lead',1))
        con.execute('DELETE FROM chat_conversations WHERE id=?',('chat-fixture',))
        if con.execute('SELECT COUNT(*) FROM agent_conversation_links').fetchone()[0] != 0:
            errors.append('Legacy chat deletion did not remove binding')
    except sqlite3.DatabaseError as exc:
        errors.append(f'SQL: {exc}')
    mapping = {'agent-profile':'agent-profile', 'handoff':'handoff', 'runtime-event':'runtime-event','scene-document-v2':'scene-document-v2','code-changeset':'code-changeset','workspace-lease':'workspace-lease'}
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print('INFO jsonschema not installed; only parsed JSON, basic manifest, QA and SQL smoke checked.')
    else:
        for prefix in mapping:
            schema = schemas.get(prefix + '.schema.json')
            if schema is None:
                errors.append(f'Missing schema {prefix}'); continue
            sample=json.loads((ROOT/'examples'/ (prefix+'.example.json')).read_text(encoding='utf-8'))
            try:
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema,format_checker=None).validate(sample)
            except Exception as exc:
                errors.append(f'Schema or example {prefix}: {exc}')
    print(f'Doc checks: {len(schemas)} JSON schemas, {len(rows)} QA rows, {len(manifest["entries"])} upstream entries; {len(errors)} errors')
    for err in errors: print('ERROR', err)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
