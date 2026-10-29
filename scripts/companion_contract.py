"""Source/build/release guards for the approved desktop and phone companion."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {'contract', 'renderer_build', 'backend_tests', 'browser_tests'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(text):
    return hashlib.sha256(text.replace('\r\n', '\n').encode('utf-8')).hexdigest()

def protected_text(root, name):
    path, _, section = name.partition('#')
    file = (root / path).resolve()
    if not file.is_relative_to(root.resolve()):
        raise ValueError('Baseline path escapes the project')
    text = file.read_text(encoding='utf-8')
    if section == 'inline-styles':
        return '\n'.join(re.findall(r'<style(?:\s[^>]*)?>(.*?)</style>', text, re.S | re.I))
    if section == 'home':
        match = re.search(r'<section id="pane-axx"(?:\s[^>]*)?>.*?</section>', text, re.S)
        if not match:
            raise ValueError('Approved phone home is missing')
        return match[0]
    if section:
        raise ValueError('Unknown baseline section')
    return text

def renderer_source(root):
    text = (root / '1.AXX/Axx.html').read_bytes().decode('utf-8')
    start = text.index('<script>"use strict";') + len('<script>')
    marker = text.index('    Axx.SoftwareRenderer = SoftwareRenderer;', start)
    end = text.index('})(Axx || (Axx = {}));', marker) + len('})(Axx || (Axx = {}));')
    return text[start:end]

def versions(root):
    gradle=(root / 'mobile/android/app/build.gradle').read_text(encoding='utf-8')
    match=re.search(r'\bversionCode\s+(\d+)\b',gradle)
    if not match or int(match[1])<1:
        raise ValueError('Android versionCode must be a positive integer')
    return {'desktop': read(root / 'package.json')['version'], 'android': read(root / 'mobile/package.json')['version'], 'android_code':int(match[1])}

def check_contract(root=ROOT, built=False):
    contract = read(root / 'mobile/companion-contract.json')
    if contract['id'] != 'axx-companion-v1' or contract['api_prefix'] != '/v1' or contract['revision'] != 1:
        raise ValueError('Contract change needs a reviewed migration, not an in-place v1 replacement')
    baseline = read(root / 'mobile/design-baseline.json')
    for name, expected in baseline['protected'].items():
        if sha(protected_text(root, name)) != expected:
            raise ValueError(f'Approved design changed: {name}. Restore it or obtain an explicit design review; do not refresh hashes to pass.')
    version = versions(root)['android']
    lock = read(root / 'mobile/package-lock.json')
    gradle = (root / 'mobile/android/app/build.gradle').read_text(encoding='utf-8')
    if lock['version'] != version or lock['packages']['']['version'] != version or f'versionName "{version}-companion"' not in gradle:
        raise ValueError('Android manifests disagree; desktop and Android versions remain independent')
    approved=baseline['approved_runtime']
    newer=tuple(map(int,version.split('.')))>tuple(map(int,approved['android'].split('.')))
    code=versions(root)['android_code']
    if code<approved['android_code'] or newer and code<=approved['android_code']:
        raise ValueError('Android versionCode cannot downgrade or reuse the approved build code for a newer version')
    strings = set()
    for path in (root / 'backend/mobile').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        strings.update(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    if missing := set(contract['required_routes']) - strings:
        raise ValueError('v1 routes removed or renamed: ' + ', '.join(sorted(missing)))
    if built:
        www = root / 'mobile/www'
        extracted = (www / 'js/desktop-avatar.js').read_bytes().decode('utf-8')
        if extracted != renderer_source(root):
            raise ValueError('Phone renderer is stale; rebuild from the current desktop source')
        build = read(www / 'companion-build.json')
        if build['versions'] != versions(root) or build['contract_sha256'] != sha((root / 'mobile/companion-contract.json').read_text(encoding='utf-8')):
            raise ValueError('Phone build provenance is stale')
        if build['renderer_sha256'] != hashlib.sha256(extracted.encode()).hexdigest():
            raise ValueError('Phone renderer differs from its build provenance')
    return versions(root)

def input_hashes(root):
    paths = {root / p for p in ('package.json', '1.AXX/Axx.html', 'scripts/companion_contract.py', 'scripts/validate_companion.py', 'scripts/test_companion_contract.py', 'scripts/release.py', 'requirements-mobile.txt', 'requirements-companion-tests.txt')}
    for base in ('mobile', 'backend/mobile'):
        for path in (root / base).rglob('*'):
            relative = path.relative_to(root)
            if {'node_modules', 'www', 'build', '.gradle', '__pycache__', '.idea'}.intersection(relative.parts):
                continue
            if relative.as_posix().startswith(('mobile/android/app/src/main/assets/', 'mobile/android/capacitor-cordova-android-plugins/')) or relative.as_posix()=='mobile/android/app/src/main/res/xml/config.xml':
                continue
            if path.is_file() and path.suffix in {'.js', '.mjs', '.css', '.html', '.json', '.java', '.xml', '.gradle', '.properties', '.py'}:
                paths.add(path)
    return {p.relative_to(root).as_posix(): sha(p.read_text(encoding='utf-8-sig')) for p in sorted(paths)}

def validate_receipt(root, path):
    check_contract(root)
    if not path.is_file():
        raise ValueError('Missing companion receipt; run python scripts/validate_companion.py against the final source')
    receipt = read(path)
    if receipt.get('result') != 'PASS' or receipt.get('versions') != versions(root):
        raise ValueError('Companion receipt does not match both current application versions')
    steps = receipt.get('steps', [])
    if len(steps) != len(CHECKS) or {step.get('id') for step in steps} != CHECKS or any(type(step.get('exit_code')) is not int or step['exit_code'] != 0 for step in steps):
        raise ValueError('Companion compatibility checks are incomplete or failed')
    if receipt.get('inputs') != input_hashes(root):
        raise ValueError('Companion evidence is stale; rerun scripts/validate_companion.py after the final changes')
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built', action='store_true')
    args = parser.parse_args()
    try:
        print('PASS:', check_contract(ROOT, args.built))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Companion check stopped: {exc}\n')
