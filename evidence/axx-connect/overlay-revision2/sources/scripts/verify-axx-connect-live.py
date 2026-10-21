"""Real private backend + installed Codex plugin; never operates the Axx GUI.

Produces bounded evidence without tokens, authentication files or raw stderr.
The executor is the real application code with an isolated test data directory.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', action='store_true', help='Also run the installed plugin in Codex CLI')
    args = parser.parse_args()
    directory = ROOT / 'evidence/axx-connect' / ('live-' + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    env = dict(os.environ, AXX_HOST_TOKEN=secrets.token_hex(32), AXX_CONNECT_DATA_DIR=str(directory))
    ready = directory / 'ready.json'
    report = {'mocked': False, 'native_gui_tested': False, 'data_directory': str(directory), 'checks': [], 'ok': False}
    process = None
    try:
        process = subprocess.Popen([sys.executable, str(ROOT / 'backend/server.py'), '--port', '0', '--data-dir', str(directory), '--ready-file', str(ready)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 45
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.1)
        connection = json.loads(ready.read_text())
        def request(method, path, body=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{connection['port']}/axx-api/connect/" + path, data=data, method=method,
                headers={'Authorization': 'Bearer ' + env['AXX_HOST_TOKEN'], 'Content-Type': 'application/json'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=30) as response:
                return json.load(response)
        status = request('GET', 'status')
        assert status['instance_id'] == connection['instance_id'] and status['executor'] == 'ready'
        report['checks'].append('real_backend_authenticated_identity')
        report['engine'] = {k: status['engine'].get(k) for k in ('state','authenticated','inference_verified','model')}
        try:
            request('POST', 'execute', {'command_id':'axx.artifact.write', 'inputs':{'path':'../escape','content':'x'}})
            raise AssertionError('Invalid file path accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 400
        report['checks'].append('invalid_effect_rejected')
        (directory / 'connect/runtime.json').write_text(json.dumps({'mode':'source','source_root':str(ROOT)}))
        python = ROOT / '.venv-axx-connect/Scripts/python.exe'
        probe = subprocess.run([str(python), str(ROOT / 'scripts/probe-axx-connect.py'), '--execute-telemetry', '--output', str(directory / 'mcp-probe.json')],
            cwd=ROOT, env=env, capture_output=True, timeout=75, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['mcp_probe_exit'] = probe.returncode
        if probe.returncode:
            report['mcp_probe'] = json.loads((directory / 'mcp-probe.json').read_text())
            raise AssertionError('Real MCP probe failed')
        report['checks'].append('shipped_launcher_mcp_executor_and_idempotency')
        if args.host:
            from backend.connect.provider import discover_codex, CodexProvider
            # Select only the installed target plugin in this child client.
            # Read names through official RPC, never inspect authentication files
            # or change the user's persistent plugin/MCP configuration.
            inspector = CodexProvider(None, directory / 'host-config.db', directory)
            try:
                inspector.status()
                config_args = []
                for name in inspector.disabled_plugins:
                    if name != 'axx-connect@axx-local':
                        config_args.extend(['-c', 'plugins.' + name + '.enabled=false'])
                config_args.extend(['-c', 'mcp_servers={}', '-c', 'mcp_optional_startup_grace_ms=0'])
                config_args.extend(['-c', 'plugins.axx-connect@axx-local.enabled=true'])
            finally:
                inspector.close()
            prompt = 'Usa exclusivamente el plugin [@Axx Connect](plugin://axx-connect@axx-local). Llama axx_system_telemetry con operation_id host-check-' + uuid.uuid4().hex + '. Es una capacidad de lectura del registro real. Consulta axx_get_task si es necesario hasta obtener succeeded y postconditions_passed true. No uses shell ni herramientas ajenas. Después responde solamente AXX_CONNECT_HOST_OK.'
            cli = subprocess.run([str(discover_codex()), 'exec', '--skip-git-repo-check', '--sandbox', 'read-only', '--json', '-m', 'gpt-6.1-sol', '-C', str(directory),
                '-c', 'forced_login_method="chatgpt"', '-c', 'features.shell_tool=false', '-c', 'features.unified_exec=false', '-c', 'features.multi_agent=false', '-c', 'features.hooks=false', *config_args, prompt],
                cwd=directory, env={k:v for k,v in env.items() if k not in ('OPENAI_API_KEY','CODEX_API_KEY','ACCESS_TOKEN')}, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            events = []
            for line in cli.stdout.splitlines():
                try: events.append(json.loads(line))
                except ValueError: pass
            # Keep only tool/action results and model text, never raw environment/stderr.
            safe = [e for e in events if e.get('type') in ('item.completed','turn.completed','turn.failed','error')]
            (directory / 'codex-host-events.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2))
            report['host_exit'] = cli.returncode
            operations = request('GET', 'history')['operations']
            verified = [op for op in operations if op['operation_id'].startswith('host-check-') and op['state']=='succeeded' and op.get('postconditions_passed')]
            tool_seen = any('axx_system_telemetry' in json.dumps(e) and ('mcp_tool_call' in json.dumps(e)) for e in safe)
            marker = any('AXX_CONNECT_HOST_OK' in json.dumps(e) for e in safe)
            report['host'] = {'plugin_tool_observed':tool_seen,'verified_operations':len(verified),'reply_observed':marker}
            assert cli.returncode == 0 and verified and tool_seen and marker, 'Codex host did not complete the plugin executor round trip'
            report['checks'].append('codex_host_plugin_to_executor_return')
        report['ok'] = True
    except Exception as error:
        report['error'] = {'type':type(error).__name__, 'message':str(error)[:500]}
    finally:
        if process and process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
            else:
                process.terminate()
            try: process.wait(10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(5)
        # Only this probe's backend is terminated; the installed Axx is untouched.
        output = ROOT / 'evidence/axx-connect/live-integration-result.json'
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
