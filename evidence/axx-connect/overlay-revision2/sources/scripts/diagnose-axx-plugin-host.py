"""Inspect the installed Axx plugin through Codex App Server without inference.

Disables unrelated plugin/MCP entries only in this child process; no user config
is rewritten and no model turn is created. Reports schema-backed MCP discovery.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import tomllib


def redact(value):
    value = re.sub(r'(?i)bearer\s+\S+|\bsk-[A-Za-z0-9_-]+|\beyJ[A-Za-z0-9_.-]{20,}', '[redacted]', str(value))
    return value[:1000]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir')
    parser.add_argument('--output')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from backend.connect.provider import discover_codex
    from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
    executable = discover_codex()
    user_dir = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    config_file = user_dir / 'config.toml'
    config = tomllib.loads(config_file.read_text(encoding='utf-8-sig')) if config_file.exists() else {}
    command = [str(executable), 'app-server', '--listen', 'stdio://', '-c', 'features.apps=false', '-c', 'features.hooks=false',
               '-c', 'mcp_servers={}', '-c', 'mcp_optional_startup_grace_ms=0']
    for plugin in config.get('plugins', {}):
        # Codex 0.160 CLI dotted overrides treat quotes in path segments as
        # literal key characters. IDs from config are validated, not shell text.
        if not re.fullmatch(r'[A-Za-z0-9_@.-]+', plugin):
            raise ValueError('Plugin ID cannot be represented safely in a CLI dotted override')
        command.extend(['-c', 'plugins.' + plugin + '.enabled=' + ('true' if plugin == 'axx-connect@axx-local' else 'false')])
    env = os.environ.copy()
    if args.data_dir:
        env['AXX_CONNECT_DATA_DIR'] = str(Path(args.data_dir).resolve())
    process, job = spawn_managed_process(command, cwd=str(root), env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', bufsize=1)
    responses, stderr = queue.Queue(), []
    def read_stdout():
        for line in process.stdout:
            try:
                message = json.loads(line)
                if 'id' in message and 'method' not in message:
                    responses.put(message)
            except ValueError:
                pass
    def read_stderr():
        for line in process.stderr:
            # App Server diagnostics contain no request environment/config dump;
            # keep a small redacted tail for actionable startup errors.
            stderr.append(redact(line.strip()))
            if len(stderr) > 30:
                del stderr[:-30]
    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    sequence = 0
    deadline = time.monotonic() + 45
    report = {'inference_called': False, 'config_mutated': False, 'plugin': 'axx-connect@axx-local', 'ok': False}
    def request(method, params):
        nonlocal sequence
        sequence += 1
        process.stdin.write(json.dumps({'id': sequence, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()
        while time.monotonic() < deadline:
            try:
                response = responses.get(timeout=min(.2, max(.05, deadline - time.monotonic())))
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError('Codex exited during MCP discovery with code ' + str(process.returncode))
                continue
            if response.get('id') == sequence:
                if response.get('error'):
                    raise RuntimeError(redact(response['error']))
                return response.get('result', {})
        raise TimeoutError('Codex MCP status exceeded the 45-second diagnostic budget')
    try:
        init = request('initialize', {'clientInfo': {'name': 'axx_plugin_diagnostic', 'title': 'Axx plugin diagnostic', 'version': '0.1.0'}, 'capabilities': {'experimentalApi': True}})
        report['initialized'] = bool(init)
        process.stdin.write(json.dumps({'method': 'initialized'}) + '\n'); process.stdin.flush()
        inventory = request('mcpServerStatus/list', {'limit': 100, 'detail': 'toolsAndAuthOnly'})
        selected = [item for item in inventory.get('data', []) if item.get('pluginId') == 'axx-connect@axx-local' or 'axx-connect' in item.get('name', '')]
        report['servers'] = [{key: item.get(key) for key in ('name', 'pluginId', 'runtimeStatus', 'toolsError', 'serverInfo')} | {'tools': sorted(item.get('tools', {}))} for item in selected]
        report['ok'] = bool(selected) and any(item.get('tools') for item in selected)
    except Exception as exc:
        report['error'] = {'type': type(exc).__name__, 'message': redact(exc)}
    finally:
        terminate_process_tree(process, job, timeout=3)
        report['diagnostics'] = stderr[-15:]
    output = Path(args.output) if args.output else root / 'evidence' / 'axx-connect' / 'installed-plugin-host-diagnostic.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
