"""Create an isolated delivery checkout from verified inputs; never restore worktree files."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
stage = root / 'build' / 'resident-release-0.20.3'
assert not stage.exists(), 'Preserve existing stage; choose a new directory'
stage.mkdir(parents=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest().upper()
pre = root / 'evidence' / 'command-library-20261019' / 'before'
receipt = json.loads((root / 'build/backend-build-receipt.json').read_text(encoding='utf-8-sig'))
copied = []
for name, expected in receipt['inputs'].items():
    source = Path(name)
    if not source.is_absolute():
        source = root / source
    relative = source.relative_to(root)
    if sha(source) != expected.upper():
        source = pre / relative
    assert source.is_file() and sha(source) == expected.upper(), f'No verified input for {relative}'
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(str(relative))
for directory in ['1.AXX', 'src-tauri/src', 'src-tauri/icons', 'src-tauri/capabilities',
                  'src-tauri/resources/license-notices']:
    shutil.copytree(root / directory, stage / directory, dirs_exist_ok=True)
html = pre / '1.AXX/Axx.html'
assert sha(html) == '1CC9A0E4F2B54C9B3012226B39E832882B266EF2BCBAB9B3302B7C1FA592AD45'
shutil.copy2(html, stage / '1.AXX/Axx.html')
assert sha(stage/'1.AXX/scripts/native-voice.js') == 'E61076C5081F8C442C054097731A7A15A25A1817E8035C6DAABEDB7594537555'
freeze = json.loads((root/'evidence/resident-20261019/native-source-freeze.json').read_text(encoding='utf-8-sig'))
for item in freeze:
    source = Path(item['path'])
    assert sha(source) == item['sha256'].upper(), f'Native input changed: {source}'
    target = stage/source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
for name in ['package.json','package-lock.json','src-tauri/build.rs',
             'src-tauri/resources/axx-backend.exe','src-tauri/resources/ai-memory.exe',
             'src-tauri/resources/ai-memory-LICENSE','dist/axx-backend.exe',
             'scripts/build-windows.ps1']:
    source, target = root/name, stage/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
assert sha(stage/'dist/axx-backend.exe') == receipt['sha256'].upper()
receipt['inputs'] = {str(stage/Path(k).relative_to(root)) if Path(k).is_absolute() else k:v
                     for k,v in receipt['inputs'].items()}
(stage/'build').mkdir(exist_ok=True)
(stage/'build/backend-build-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
# The local CLI is immutable tooling; do not duplicate node_modules or install packages.
builder = stage/'scripts/build-windows.ps1'
text = builder.read_text(encoding='utf-8-sig')
text = text.replace("(Join-Path $projectRoot 'node_modules\\.bin\\tauri.cmd')",
                    "'" + str(root/'node_modules/.bin/tauri.cmd') + "'")
builder.write_text(text,encoding='utf-8')
# Reuse a COPY of the release cache. Output files remain independent while the
# other chat compiles its own working tree. Cargo validates freshness normally.
print(json.dumps({'stage':str(stage),'verified_backend_inputs':len(copied),
                  'copying_independent_release_cache':True}),flush=True)
shutil.copytree(root/'src-tauri/target/release',stage/'src-tauri/target/release',
                ignore=shutil.ignore_patterns('bundle','nsis'),dirs_exist_ok=True)
for name in ['.rustc_info.json','CACHEDIR.TAG']:
    source=root/'src-tauri/target'/name
    if source.exists(): shutil.copy2(source,stage/'src-tauri/target'/name)
(root/'evidence/resident-20261019/isolated-release-stage.json').write_text(json.dumps({
    'root':str(stage),'reason':'Concurrent authorized command-library work in canonical checkout',
    'frontend_sha256':sha(stage/'1.AXX/Axx.html'),'backend_sha256':sha(stage/'dist/axx-backend.exe'),
    'native_inputs':freeze,'other_chat_worktree_restored_or_reverted':False},indent=2),encoding='utf-8')
print('Isolated source stage ready; canonical working tree was not restored or reverted.',flush=True)
