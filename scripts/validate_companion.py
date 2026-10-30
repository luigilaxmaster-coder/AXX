"""Run the paired source checks. This neither installs apps nor claims hardware acceptance."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from companion_contract import ROOT, check_contract, input_hashes, versions

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/companion-validation.json')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    before = input_hashes(ROOT)
    receipt = {'result': 'FAIL', 'versions': versions(ROOT), 'inputs': before, 'steps': [], 'physical_validation': 'separate receipt required'}
    args.output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    check_contract(ROOT)
    node = shutil.which('node')
    if not node:
        parser.exit(1, 'Node.js is required to rebuild the shared renderer\n')
    commands = [
        ('contract', [sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_companion_contract.py', '-q']),
        ('renderer_build', [node, 'mobile/build.mjs']),
        ('backend_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'backend/mobile/tests', '-q']),
        ('browser_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'mobile/tests', '-q']),
    ]
    for name, command in commands:
        print(f'Checking companion: {name}', flush=True)
        result = subprocess.run(command, cwd=ROOT)
        if name == 'browser_tests' and not result.returncode:
            print('Checking companion: desktop file selector', flush=True)
            result = subprocess.run([sys.executable, '1.AXX/scripts/test-transfer-ui.py', '-q'], cwd=ROOT)
        receipt['steps'].append({'id': name, 'exit_code': result.returncode})
        args.output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        if result.returncode:
            return result.returncode
        if name == 'renderer_build':
            check_contract(ROOT, built=True)
    if input_hashes(ROOT) != before:
        parser.exit(1, 'Source changed during validation; rerun against the final source\n')
    receipt['result'] = 'PASS'
    args.output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(f'PASS: paired compatibility receipt saved to {args.output}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
