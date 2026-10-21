"""Import the pinned documentary library as inert, bounded catalog metadata.

No archive member is extracted or executed. The CLI accepts only the authorized
archive digest. build_catalog's explicit digest parameter supports controlled
fixture tests; it is not an authorization or execution interface.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

AUTHORIZED_SHA256 = '5d9445889c943cdfd22383ce43a719027c1c9698e218d487ba5ee7261f13d93d'
SOURCE_FILE_ID = '1iFeY3CBb8GjEqeTJs-uBYq-gd110pG0T'
SOURCE_URL = f'https://drive.google.com/file/d/{SOURCE_FILE_ID}/view'
STATUS = 'DOCUMENTED_NOT_EXECUTED'
GROUPS = {'PRINCIPAL_REVISADO', 'HEREDADO_SIN_CERTIFICAR', 'SUPLEMENTO_EXCLUIDO'}
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_MEMBER_BYTES = 24 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_RECORDS = 20000


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _json(content):
    try:
        return json.loads(content, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid bounded JSON document') from exc


def _text(value, limit=256):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('Metadata text must be a string')
    return ' '.join(value.replace('\x00', '').split())[:limit]


def _disabled(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'execution_enabled', 'voice_runtime_verified'} and item is not False:
                raise ValueError(f'{key} must remain false')
            _disabled(item)
    elif isinstance(value, list):
        for item in value:
            _disabled(item)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'AXX-[A-Za-z0-9-]{1,120}', value):
        raise ValueError('Invalid catalog ID')
    return value


def _archive_members(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            entries = source.infolist()
            if len(entries) > 100 or sum(entry.file_size for entry in entries) > MAX_TOTAL_BYTES:
                raise ValueError('Archive resource limit exceeded')
            names = set()
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (not entry.filename or '\\' in entry.filename or ':' in entry.filename
                        or path.is_absolute() or '..' in path.parts
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('Unsafe archive member')
                if entry.filename.casefold() in names:
                    raise ValueError('Duplicate archive member')
                names.add(entry.filename.casefold())
                if entry.file_size > MAX_MEMBER_BYTES or entry.flag_bits & 1:
                    raise ValueError('Archive member resource limit or encryption unsupported')
            # Read into memory only; do not call extract/extractall or import code.
            return {entry.filename: source.read(entry) for entry in entries if not entry.is_dir()}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Invalid or unsupported ZIP archive') from exc


def _verify_manifest(members):
    manifest = _json(members.get('manifest.json', b'{}'))
    if not isinstance(manifest, dict) or manifest.get('execution_enabled') is not False:
        raise ValueError('Manifest execution_enabled must remain false')
    declared = manifest.get('files')
    if not isinstance(declared, list):
        raise ValueError('Manifest file hashes required')
    checked = {}
    for entry in declared:
        if not isinstance(entry, dict) or not isinstance(entry.get('file'), str):
            raise ValueError('Invalid manifest member')
        name = entry['file']
        if name in checked or name not in members:
            raise ValueError('Duplicate or missing manifest member')
        content = members[name]
        digest = hashlib.sha256(content).hexdigest()
        if entry.get('bytes') != len(content) or entry.get('sha256') != digest:
            raise ValueError('Manifest member hash or size mismatch')
        checked[name] = {'name': name, 'bytes': len(content), 'sha256': digest}
    for name in ('VOICE_MAP_ACUMULADO.jsonl', 'recipes.jsonl'):
        if name not in checked:
            raise ValueError('Required catalog member missing from manifest')
    return manifest, list(checked.values())


def _records(content, key):
    rows = {}
    for line in content.splitlines():
        if not line.strip():
            continue
        if len(line) > 128 * 1024 or len(rows) >= MAX_RECORDS:
            raise ValueError('JSONL record resource limit exceeded')
        row = _json(line)
        if not isinstance(row, dict):
            raise ValueError('Catalog record must be an object')
        record_id = _identifier(row.get(key))
        if record_id in rows:
            raise ValueError(f'Duplicate catalog ID: {record_id}')
        if row.get('status') != STATUS or row.get('execution_enabled') is not False:
            raise ValueError('Catalog status or execution_enabled is not documentary-disabled')
        _disabled(row)
        rows[record_id] = row
    return rows


def build_catalog(zip_path, *, expected_sha256=AUTHORIZED_SHA256):
    """Return (inert catalog, provenance), after archive and member verification."""
    archive = Path(zip_path)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('Archive resource limit exceeded')
    raw = archive.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError('Archive SHA256 differs from the authorized source')
    members = _archive_members(raw)
    manifest, checked_members = _verify_manifest(members)
    rows = _records(members['VOICE_MAP_ACUMULADO.jsonl'], 'recipe_id')
    recipes = _records(members['recipes.jsonl'], 'id')
    if not rows or set(recipes) - set(rows):
        raise ValueError('Full recipe missing from accumulated catalog')
    commands = []
    groups = Counter()
    for record_id, row in rows.items():
        group = row.get('catalog_group')
        if group not in GROUPS:
            raise ValueError('Unknown catalog group')
        groups[group] += 1
        recipe = recipes.get(record_id, {})
        title = _text(row.get('title'), 256) or record_id
        if recipe and _text(recipe.get('title'), 256) != title:
            raise ValueError(f'Conflicting catalog and recipe ID: {record_id}')
        voice = row.get('voice_intent') or row.get('voice_contract') or {}
        if not isinstance(voice, dict):
            raise ValueError('Invalid voice metadata')
        phrases = voice.get('phrases', voice.get('utterances', voice.get('invocations', [])))
        blockers = row.get('blockers', [])
        if not isinstance(phrases, list) or not isinstance(blockers, list):
            raise ValueError('Invalid phrase or blocker metadata')
        source_hash = row.get('source_sha256')
        if not isinstance(source_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', source_hash):
            raise ValueError('Invalid original source hash')
        commands.append({
            'id': record_id, 'title': title,
            'description': _text(recipe.get('objective'), 512),
            'category': _text(recipe.get('category'), 256) or group,
            'catalog_group': group, 'source_member': 'VOICE_MAP_ACUMULADO.jsonl',
            'recipe_member': 'recipes.jsonl' if recipe else None,
            'source_status': _text(row.get('source_status') or row.get('status'), 128),
            'source_review_status': _text(row.get('source_review_status') or recipe.get('review_status'), 128),
            'source_sha256': source_hash, 'status': STATUS, 'execution_enabled': False,
            'voice_phrases': list(dict.fromkeys(_text(phrase) for phrase in phrases[:8] if phrase)),
            'voice_status': _text(row.get('coverage_status'), 128),
            'voice_runtime_verified': False,
            'blockers': list(dict.fromkeys([_text(item) for item in blockers[:8]] +
                         ['Adaptador y pruebas individuales pendientes; importacion solo documental.'])),
            'has_recipe_details': bool(recipe),
        })
    counts = {
        'total': len(rows), 'principal': len(rows) - groups['SUPLEMENTO_EXCLUIDO'],
        'supplements': groups['SUPLEMENTO_EXCLUIDO'],
        'reviewed': groups['PRINCIPAL_REVISADO'], 'legacy': groups['HEREDADO_SIN_CERTIFICAR'],
        'full_recipes': len(recipes), 'enabled': 0, 'verified': 0,
    }
    claims = {'nominal_inventory_total': counts['principal'], 'reviewed_total': counts['reviewed'],
              'legacy_uncertified': counts['legacy'], 'comparison_unique_ids': counts['total']}
    if any(manifest.get(key) != value for key, value in claims.items()):
        raise ValueError('Manifest inventory count does not match actual unique catalog IDs')
    if not isinstance(manifest.get('counts'), dict) or manifest['counts'].get('recipes') != len(recipes):
        raise ValueError('Manifest full recipe count does not match records')
    provenance = {
        'schema_version': 1, 'source_file_id': SOURCE_FILE_ID, 'source_url': SOURCE_URL,
        'source_filename': archive.name, 'source_sha256': digest, 'source_bytes': len(raw),
        'batch': _text(manifest.get('batch'), 128), 'archive_hash_verified': True,
        'source_member_hashes_verified': True, 'execution_enabled': False,
        'counts': counts,
        'limits': ['El mapa acumulado contiene metadatos de 7562 IDs; solo 4 recetas completas en este lote.',
                   'Revision documental y cobertura de frases no son pruebas de ejecucion o audio.',
                   'No se extrajo ni ejecuto codigo del ZIP; todos los comandos importados siguen deshabilitados.'],
        'verified_members': checked_members,
    }
    catalog = {'schema_version': 1, 'provenance': provenance, 'counts': counts, 'commands': commands}
    return catalog, provenance


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as target:
        temporary = Path(target.name)
        target.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'resources' / 'command-library.json')
    parser.add_argument('--provenance', type=Path, default=Path(__file__).resolve().parents[1] / 'resources' / 'command-library.provenance.json')
    args = parser.parse_args()
    try:
        catalog, provenance = build_catalog(args.archive)
        catalog_hash = _write_json(args.output, catalog)
        _write_json(args.provenance, {**provenance, 'catalog_sha256': catalog_hash})
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Import rejected: {exc}\n')
    print(json.dumps({'output': str(args.output), 'catalog_sha256': catalog_hash, 'counts': catalog['counts']}))


if __name__ == '__main__':
    main()
