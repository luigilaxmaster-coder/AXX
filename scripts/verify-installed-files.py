"""Verify installed resources and Tauri's documented-in-binary NSIS marker.

Tauri patches the bundle marker while producing NSIS, then restores the release
EXE to UNK. Compare against that exact three-byte transform; accept no other
binary difference. This verifier never edits the installed or release files.
"""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--installed', type=Path, required=True)
parser.add_argument('--build-result', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
build = json.loads(args.build_result.read_text(encoding='utf-8-sig'))
release_path = Path(build['artifacts'][1]['path'])
release = release_path.read_bytes()
installed_path = args.installed / 'Axx.exe'
installed = installed_path.read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
if digest(release).lower() != build['artifacts'][1]['sha256'].lower():
    raise RuntimeError('Release changed since build')
if installed == release:
    marker = 'identical-release'
else:
    # The namespace prefix can vary; this exact suffix is part of the Tauri
    # bundle-type static. Require one occurrence and the entire resulting hash.
    old, new = b'BUNDLE_TYPE_VAR_UNK', b'BUNDLE_TYPE_VAR_NSS'
    if release.count(old) != 1:
        raise RuntimeError('Expected one Tauri bundle marker')
    expected = release.replace(old, new, 1)
    if installed != expected:
        raise RuntimeError('Installed EXE differs outside the exact NSIS bundle marker')
    marker = 'Tauri UNK -> NSS; exactly three bytes'
backend_path = args.installed / 'resources' / 'axx-backend.exe'
backend_hash = digest(backend_path.read_bytes())
if backend_hash.lower() != build['artifacts'][2]['sha256'].lower():
    raise RuntimeError('Backend differs from verified build')
memory_inputs = [value for name, value in build['source_hashes'].items()
                 if name.replace('\\', '/').lower().endswith('src-tauri/resources/ai-memory.exe')]
if len(memory_inputs) != 1:
    raise RuntimeError('Expected one frozen ai-memory dependency hash in build receipt')
memory_path = args.installed / 'resources' / 'ai-memory.exe'
memory_hash = digest(memory_path.read_bytes())
if memory_hash.lower() != memory_inputs[0].lower():
    raise RuntimeError('ai-memory differs from frozen dependency verified during build')
report = {'result': 'PASS', 'version': build['artifacts'][0]['version'],
          'installed_directory': str(args.installed.resolve()), 'tauri_bundle_marker': marker,
          'installed_exe_sha256': digest(installed), 'release_exe_sha256': digest(release),
          'backend_sha256': backend_hash, 'ai_memory_sha256': memory_hash,
          'files': [{'path': str(p.resolve()), 'bytes': p.stat().st_size}
                    for p in (installed_path, backend_path, memory_path)]}
args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
