"""Exercise the frozen command integration in disposable app-data. No source imports/audio/network services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    workspace = Path(tempfile.mkdtemp(prefix='axx-command-package-'))
    config = workspace / 'providers.json'
    config.write_text(json.dumps({'allow_paid': False, 'providers': []}))
    state = workspace / 'state.db'
    sqlite3.connect(state).close()  # Never migrate the user's legacy state.
    token = secrets.token_hex(32)
    env = dict(os.environ, AXX_HOST_TOKEN=token, AXX_AI_MEMORY_EXE=str(workspace / 'not-configured.exe'))
    report = {'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'workspace': str(workspace), 'checks': [], 'physical_microphone_verified': False,
              'speaker_playback_verified': False, 'external_services_used': False}
    process = None
    base = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = (workspace / 'backend.log').open('ab')

    def check(name, condition):
        assert condition, name
        report['checks'].append({'name': name, 'passed': True})

    def request(path, body=None, authenticated=True):
        headers = {'Authorization': 'Bearer ' + token} if authenticated else {}
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode()
        try:
            response = opener.open(urllib.request.Request(base + '/axx-api/' + path, headers=headers, data=data), timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def start():
        nonlocal process, base
        ready = workspace / 'ready.json'
        ready.unlink(missing_ok=True)
        process = subprocess.Popen([str(binary), '--port', '0', '--data-dir', str(workspace),
            '--config', str(config), '--state', str(state), '--ready-file', str(ready)],
            cwd=workspace, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError('Frozen backend exited; inspect ' + str(workspace / 'backend.log'))
            if ready.is_file():
                base = 'http://127.0.0.1:' + str(json.loads(ready.read_text())['port'])
                return
            time.sleep(.1)
        raise AssertionError('Frozen backend readiness timed out')

    def stop():
        nonlocal process
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        process = None

    try:
        start()
        check('unauthenticated catalog denied', request('commands', authenticated=False)[0] == 401)
        status, catalog = request('commands?limit=5')
        counts = catalog['counts']
        report['counts'] = counts
        check('frozen catalog contains all documentary IDs and three closed adapters',
              status == 200 and counts['imported'] == 7562 and counts['enabled'] == 3 and counts['blocked'] == 7563)
        check('verified source provenance bundled', catalog['provenance']['source_sha256'] ==
              '5d9445889c943cdfd22383ce43a719027c1c9698e218d487ba5ee7261f13d93d')
        ids = [request('commands/resolve', {'text': 'información del sistema', 'source': source})[1]['command_id']
               for source in ('text', 'voice')]
        check('same canonical ID from text and recognized voice', ids == ['axx.system.telemetry'] * 2)
        op = request('commands/prepare', {'command_id': ids[0], 'inputs': {}, 'source': 'voice'})[1]
        telemetry = request('commands/execute', {'operation_id': op['operation_id']})[1]
        check('real telemetry observed and verified', telemetry['state'] == 'succeeded' and telemetry['postconditions_passed'] and bool(telemetry['output']['os']))
        op = request('commands/prepare', {'command_id': 'axx.process.inspect', 'inputs': {}})[1]
        inspected = request('commands/execute', {'operation_id': op['operation_id']})[1]
        check('real frozen process active', inspected['state'] == 'succeeded' and inspected['output']['active'] is True)
        file_inputs = {'path': 'check/hello.txt', 'content': 'Axx frozen command evidence á'}
        op = request('commands/prepare', {'command_id': 'axx.artifact.write', 'inputs': file_inputs, 'operation_id': 'frozen-write'})[1]
        target = workspace / 'artifacts/check/hello.txt'
        check('write requires review and boolean approval', op['state'] == 'awaiting_approval' and not target.exists() and
              request('commands/execute', {'operation_id': op['operation_id']})[0] == 403)
        result = request('commands/execute', {'operation_id': op['operation_id'], 'approved': True})[1]
        check('approved actual artifact matches SHA256', result['state'] == 'succeeded' and result['postconditions_passed'] and
              target.read_text(encoding='utf-8') == file_inputs['content'] and hashlib.sha256(target.read_bytes()).hexdigest() == result['evidence']['sha256'])
        before = target.stat().st_mtime_ns
        check('idempotent replay does not rewrite', request('commands/execute', {'operation_id': 'frozen-write', 'approved': True})[1].get('replayed') and target.stat().st_mtime_ns == before)
        check('legacy action cannot bypass policy', request('actions/execute', {'tool_name': 'file_artifact_writer', 'inputs': {'path': 'bypass.txt', 'content': 'x'}})[0] == 403 and not (workspace / 'artifacts/bypass.txt').exists())
        check('disabled Blender cannot bypass policy', request('actions/execute', {'tool_name': 'blender_render_fixture', 'inputs': {'filename': 'blocked.png'}})[0] == 403)
        _, doc = request('commands/prepare', {'command_id': 'AXX-20261018-0800-IMG-0001', 'inputs': {}})
        check('original documentary recipe remains blocked', doc['state'] == 'blocked' and request('commands/execute', {'operation_id': doc['operation_id'], 'approved': True})[1]['state'] == 'blocked')
        check('saved recipe registration uses observed action evidence', request('recipes/register', {'id': 'frozen-recipe', 'intent_key': 'frozen-write-recipe', 'operation_id': result['action_operation_id']})[0] == 200)
        listed = request('recipes')[1]['recipes']
        check('frozen recipe list supplies UI parameter schema', set(next(row for row in listed if row['id'] == 'frozen-recipe')['schema']) == {'path', 'content'})
        check('saved recipe cannot bypass approval', request('recipes/execute', {'intent_key': 'frozen-write-recipe', 'inputs': {'path': 'recipe.txt', 'content': 'new'}})[0] == 403)
        pending = request('recipes/prepare', {'intent_key': 'frozen-write-recipe', 'inputs': {'path': 'recipe.txt', 'content': 'new'}})[1]
        check('saved recipe reuses same typed preparation', pending['command_id'] == 'axx.artifact.write' and pending['state'] == 'awaiting_approval')
        request('commands/cancel', {'operation_id': pending['operation_id']})
        check('cancelled recipe never writes', request('commands/execute', {'operation_id': pending['operation_id'], 'approved': True})[1]['state'] == 'cancelled' and not (workspace / 'artifacts/recipe.txt').exists())
        request('commands/cancel', {'operation_id': 'early-cancel'})
        check('late prepare respects prior cancellation', request('commands/prepare', {'operation_id': 'early-cancel', 'command_id': 'axx.artifact.write', 'inputs': {'path': 'late.txt', 'content': 'x'}})[1]['state'] == 'cancelled')
        request('commands/prepare', {'operation_id': 'expires-on-restart', 'command_id': 'axx.artifact.write', 'inputs': {'path': 'pending.txt', 'content': 'x'}})
        stop()
        start()
        observed = request('commands/operations?operation_id=frozen-write')[1]['operation']
        check('restart preserves observed successful evidence', observed['state'] == 'succeeded' and observed['evidence']['sha256'] == result['evidence']['sha256'])
        check('restart expires unapproved request without effect', request('commands/execute', {'operation_id': 'expires-on-restart', 'approved': True})[1]['state'] == 'expired' and not (workspace / 'artifacts/pending.txt').exists())
        report['passed'] = True
    except Exception as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        stop()
        log.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed': report.get('passed'), 'checks': len(report['checks']), 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
