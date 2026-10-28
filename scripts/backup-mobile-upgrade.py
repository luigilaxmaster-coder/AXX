"""Create a verified local recovery copy before updating the installed Axx."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from datetime import datetime

root = Path(__file__).resolve().parents[1]
destination = root / 'build' / 'mobile-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
assert destination.resolve().is_relative_to((root / 'build' / 'mobile-backups').resolve())
destination.mkdir(parents=True, exist_ok=False)
local = Path(os.environ['LOCALAPPDATA'])
sources = {'data':local/'Axx', 'webview':local/'com.axx.desktop', 'installation':local/'Programs'/'Axx'}
manifest = {}
excluded = []

def backup_files(source, label):
    for directory, names, files in os.walk(source):
        base = Path(directory)
        for name in names[:]:
            # Historical backups and downloaded npm caches are not user data.
            if label == 'data' and (name in {'node_modules', '__pycache__', '.tmp'} or base == source and name == 'backups'):
                names.remove(name)
                excluded.append(str(Path(label) / (base / name).relative_to(source)))
        for name in files:
            yield base / name

for label, source in sources.items():
    if not source.is_dir():
        continue
    for file in backup_files(source, label):
        if not file.is_file() or file.name.endswith(('.db-wal', '.db-shm')):
            continue
        target = destination / label / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix == '.db':
            original = sqlite3.connect(file.as_uri()+'?mode=ro', uri=True)
            copied = sqlite3.connect(target)
            try:
                original.backup(copied)
                if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('SQLite backup integrity check failed')
            finally:
                original.close(); copied.close()
        else:
            shutil.copy2(file, target)
            with file.open('rb') as original, target.open('rb') as copied:
                if hashlib.file_digest(original, 'sha256').digest() != hashlib.file_digest(copied, 'sha256').digest():
                    raise RuntimeError('Backup differs from source')
        with target.open('rb') as saved:
            manifest[str(target.relative_to(destination))] = hashlib.file_digest(saved, 'sha256').hexdigest()
(destination/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(destination/'excluded-directories.json').write_text(json.dumps(excluded, indent=2), encoding='utf-8')
print(json.dumps({'backup':str(destination), 'verified_files':len(manifest), 'excluded_rebuildable_directories':len(excluded)}))
