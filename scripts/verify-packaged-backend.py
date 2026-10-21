"""Exercise the frozen sidecar from a separate cwd, then restart and replay.

Only generated files under a dedicated temporary app-data directory are used.
No model credentials, source imports, development runtimes or remote mocks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('binary', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--memory-binary', type=Path)
parser.add_argument('--blender', action='store_true')
args = parser.parse_args()
binary = args.binary.resolve(strict=True)
workspace = Path(tempfile.mkdtemp(prefix='axx-packaged-'))
if args.memory_binary:
    packaged = workspace / 'bin'
    packaged.mkdir()
    shutil.copy2(binary, packaged / 'axx-backend.exe')
    shutil.copy2(args.memory_binary.resolve(strict=True), packaged / 'ai-memory.exe')
    binary = packaged / 'axx-backend.exe'
token = secrets.token_hex(32)
instance = str(uuid.uuid4())
environment = dict(os.environ, AXX_HOST_TOKEN=token, AXX_HOST_INSTANCE=instance)
report = {'binary': str(binary), 'workspace': str(workspace), 'checks': [], 'remote_inference': 'BLOCKED_CREDENTIALS'}
process = None
log = (workspace / 'sidecar.log').open('ab')

def start():
    global process, base
    ready = workspace / 'ready.json'
    ready.unlink(missing_ok=True)
    process = subprocess.Popen([str(binary), '--port', '0', '--data-dir', str(workspace), '--ready-file', str(ready)],
                               cwd=workspace, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError('Sidecar exited: ' + (workspace / 'sidecar.log').read_text(errors='replace'))
        if ready.exists():
            try:
                state = json.loads(ready.read_text())
                assert state['instance_id'] == instance
                base = f"http://127.0.0.1:{state['port']}"
                return state
            except (ValueError, KeyError):
                pass
        time.sleep(.1)
    raise AssertionError('Sidecar readiness timed out')

def stop():
    global process
    if process and process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        else:
            process.terminate()
        process.wait(timeout=5)
    process = None

def request(path, body=None, authenticated=True, origin=None):
    headers = {'Content-Type': 'application/json'}
    if authenticated:
        headers['Authorization'] = 'Bearer ' + token
    if origin:
        headers['Origin'] = origin
    req = urllib.request.Request(base + path, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, json.loads(response.read()), dict(response.headers)

try:
    first = start()
    status, data, headers = request('/axx-api/status')
    assert status == 200 and data['ready'] and data['instance_id'] == instance
    assert 'csrf' not in data and 'Access-Control-Allow-Origin' not in headers
    report['checks'].append('frozen_auto_start_authenticated_instance')
    if args.memory_binary:
        assert data['memory']['available'] and data['memory']['backend'] == 'ai-memory', data['memory']
        report['memory'] = data['memory']
        report['checks'].append('packaged_owned_ai_memory_authenticated_ready')
    assert request('/axx-api/actions', authenticated=False)[0] == 401
    assert request('/axx-api/actions', origin='https://foreign.invalid')[0] == 403
    report['checks'].append('unauthenticated_and_foreign_origin_rejected')
    action = {'tool_name': 'file_artifact_writer', 'operation_id': str(uuid.uuid4()),
              'inputs': {'path': str(workspace / 'artifacts' / 'first.txt'), 'content': 'AXX primera entrada verificada'}}
    status, result, _ = request('/axx-api/actions/execute', action)
    assert status == 200 and result['state'] == 'succeeded' and result['postconditions_passed'], result
    assert Path(action['inputs']['path']).read_text(encoding='utf-8') == action['inputs']['content']
    report['checks'].append('real_file_action_and_sha256')
    _, repeat, _ = request('/axx-api/actions/execute', action)
    assert repeat.get('replayed') or repeat.get('idempotent_replay') or repeat == result, repeat
    status, recipe, _ = request('/axx-api/recipes/register', {'id': 'packaged-file', 'intent_key': 'packaged-file', 'operation_id': action['operation_id']})
    assert status == 200 and recipe['recipe']['status'] == 'verified', recipe
    identity = {'shape': 'torus', 'palette': 'aurora', 'keepForm': True}
    assert request('/axx-api/identity', identity)[0] == 200
    stop()
    second = start()
    assert first['pid'] != second['pid']
    assert request('/axx-api/identity')[1]['identity'] is not None
    if args.memory_binary:
        status, memory, _ = request('/axx-api/memory/read', {'recipe_id': 'packaged-file'})
        assert status == 200 and memory.get('page'), memory
        report['checks'].append('ai_memory_exact_recipe_read_after_service_restart')
    new_inputs = {'path': str(workspace / 'artifacts' / 'second.txt'), 'content': 'AXX segunda entrada despues de reiniciar'}
    status, replay, _ = request('/axx-api/recipes/execute', {'intent_key': 'packaged-file', 'operation_id': str(uuid.uuid4()), 'inputs': new_inputs})
    assert status == 200 and replay['outcome'] == 'succeeded', replay
    assert Path(new_inputs['path']).read_text(encoding='utf-8') == new_inputs['content']
    report['checks'].append('recipe_restart_new_parameters_real_second_file')
    report['second_artifact'] = {'path': new_inputs['path'], 'sha256': hashlib.sha256(Path(new_inputs['path']).read_bytes()).hexdigest()}
    _, telemetry, _ = request('/axx-api/actions/execute', {'tool_name': 'system_telemetry', 'inputs': {}, 'operation_id': str(uuid.uuid4())})
    assert telemetry['state'] == 'succeeded'
    report['checks'].append('real_windows_telemetry')
    if args.blender:
        status, render, _ = request('/axx-api/actions/execute', {'tool_name': 'blender_render_fixture', 'inputs': {'filename': 'packaged-blender.png'}, 'operation_id': str(uuid.uuid4())})
        assert status == 200 and render['state'] == 'succeeded' and render['postconditions_passed'], render
        report['blender'] = render['evidence']
        report['checks'].append('packaged_cli_anything_actual_blender_verified_png')
    status, chat, _ = request('/axx-api/chat', {'messages': [{'role': 'user', 'content': 'Comprobacion sintetica Axx'}], 'stream': False})
    assert status == 502 and chat['error']['code'] == 'NO_PROVIDER_AVAILABLE', chat
    report['checks'].append('frozen_worker_missing_credential_typed_error')
    report['result'] = 'PASS'
finally:
    stop()
    log.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))
