"""Freeze reviewed Connect changes and a verified V1-to-V2 incremental patch.

No stage, installation, account or runtime is modified. --check only reconstructs
V1 sources from the existing patch and verifies its immutable manifest hashes.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / 'evidence/axx-connect/overlay'
ARCHIVE = ROOT / 'evidence/axx-connect/overlay-revision1'
FREEZE = ROOT / 'evidence/axx-connect/overlay-revision2'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sections(patch):
    lines = patch.splitlines(keepends=True)
    result, index = {}, 0
    while index < len(lines):
        if not lines[index].startswith('--- '):
            raise ValueError(f'Expected file header at line {index + 1}')
        target = lines[index + 1].strip()
        if not target.startswith('+++ b/'):
            raise ValueError('Unsupported patch destination')
        relative = target[6:]
        index += 2
        begin = index
        while index < len(lines) and not lines[index].startswith('--- '):
            index += 1
        result[relative] = lines[begin:index]
    return result


def reconstruct(previous, hunks):
    original = previous.decode('utf-8-sig').splitlines(keepends=True)
    output, cursor, index = [], 0, 0
    while index < len(hunks):
        header = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\r?\n?', hunks[index])
        if not header:
            raise ValueError(f'Unsupported hunk header: {hunks[index]!r}')
        start = int(header[1]) - (0 if header[2] == '0' else 1)
        old_count = int(header[2]) if header[2] is not None else 1
        new_count = int(header[4]) if header[4] is not None else 1
        output.extend(original[cursor:start]); cursor = start
        old_seen = new_seen = 0
        index += 1
        while old_seen < old_count or new_seen < new_count:
            line = hunks[index]; index += 1
            if line[0] in ' -':
                if cursor >= len(original) or original[cursor] != line[1:]:
                    raise ValueError('V1 patch does not match its baseline context')
                cursor += 1; old_seen += 1
            if line[0] in ' +':
                output.append(line[1:]); new_seen += 1
            if line[0] not in ' +-':
                raise ValueError('Unsupported patch line')
        if old_seen != old_count or new_seen != new_count:
            raise ValueError('Hunk size mismatch')
    output.extend(original[cursor:])
    return ''.join(output).encode('utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((OVERLAY / 'manifest.json').read_text(encoding='utf-8'))
    with (OVERLAY / 'source.patch').open(encoding='utf-8', newline='') as stream:
        hunks = sections(stream.read())
    baseline = Path(manifest['baseline'])
    previous_sources = {}
    for item in manifest['files']:
        relative = item['path']
        if not (ROOT / relative).resolve().is_relative_to(ROOT):
            raise ValueError('Manifest path leaves workspace')
        base = baseline / relative
        before = base.read_bytes() if base.is_file() else b''
        if relative == '.gitignore':
            before = (ROOT / relative).read_bytes()
            for line in (b'.venv-axx-connect/\n', b'.venv-axx-connect-build/\n', b'**/endpoint.dpapi\n', b'**/endpoint.tmp\n'):
                before = before.replace(line, b'')
        result = reconstruct(before, hunks[relative])
        # The original overlay generator decoded UTF-8 BOMs. Recover a BOM
        # only when its exact bytes match the recorded V1 content hash.
        if digest(result) != item['sha256'] and digest(b'\xef\xbb\xbf' + result) == item['sha256']:
            result = b'\xef\xbb\xbf' + result
        if digest(result) != item['sha256']:
            raise ValueError(f'V1 reconstruction hash differs: {relative}')
        previous_sources[relative] = result
    if not args.freeze:
        print(json.dumps({'verified_v1_files':len(previous_sources),'mode':'read_only'}))
        return
    if ARCHIVE.exists() or FREEZE.exists():
        raise FileExistsError('Immutable revision directories already exist')
    shutil.copytree(OVERLAY, ARCHIVE)
    subprocess.run([sys.executable, str(ROOT / 'scripts/make-axx-connect-overlay.py')], cwd=ROOT, check=True)
    shutil.copytree(OVERLAY, FREEZE)
    current = json.loads((FREEZE / 'manifest.json').read_text(encoding='utf-8'))
    changes, patches = [], []
    for item in current['files']:
        relative = item['path']
        before = previous_sources.get(relative, b'')
        after = (ROOT / relative).read_bytes()
        if digest(after) != item['sha256']:
            raise ValueError(f'Source changed during freeze: {relative}')
        if before == after:
            continue
        changes.append({'path':relative,'base_sha256':digest(before) if before else None,
                        'sha256':digest(after),'bytes':len(after)})
        patches.append(''.join(difflib.unified_diff(before.decode('utf-8-sig').splitlines(keepends=True),
            after.decode('utf-8-sig').splitlines(keepends=True),
            fromfile='a/'+relative if before else '/dev/null',tofile='b/'+relative)))
    (FREEZE / 'incremental-v1-v2.patch').write_text(''.join(patches),encoding='utf-8',newline='\n')
    (FREEZE / 'incremental-manifest.json').write_text(json.dumps({'baseline':'overlay-revision1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':changes},indent=2),encoding='utf-8')
    # The snapshot includes test/docs content but never local descriptors or credentials.
    for item in current['files']:
        destination = FREEZE / 'sources' / item['path']
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((ROOT / item['path']).read_bytes())
    print(json.dumps({'frozen_files':len(current['files']),'incremental_files':len(changes),
                      'destination':str(FREEZE)},indent=2))


if __name__ == '__main__':
    main()
