"""Evidence-only AppServer diagnostic: no turn/start, auth changes or user config writes.

Uses a new CODEX_HOME and ephemeral thread. The MCP canary can only create a
marker inside that temporary diagnostic directory if it is wrongly started.
This is not an inference or a complete built-in tool isolation acceptance test.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'evidence' / 'axx-connect'
SCHEMA = EVIDENCE / 'schema' / 'codex-0.160.0'
EXECUTABLE = Path(os.environ['APPDATA']) / 'npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
ALLOWED = {'initialize', 'config/read', 'configRequirements/read', 'experimentalFeature/list', 'thread/start', 'thread/read', 'mcpServerStatus/list'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(scratch=None, hardened=False, extended=False):
    scratch = Path(scratch).resolve() if scratch else EVIDENCE / ('runtime-inventory-isolated-' + uuid.uuid4().hex[:12])
    if scratch.parent != EVIDENCE.resolve() or not scratch.name.startswith('runtime-inventory-isolated-'):
        raise ValueError('Only this diagnostic evidence directory may be used')
    home, cwd = scratch / 'codex-home', scratch / 'workspace'
    home.mkdir(parents=True, exist_ok=True); cwd.mkdir(exist_ok=True)
    marker = scratch / 'mcp-canary-started.txt'
    canary = scratch / 'mcp-canary.py'
    canary.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('CANARY_PROCESS_STARTED', encoding='utf-8')\n", encoding='utf-8')
    quote = lambda value: "'" + str(value).replace("'", "") + "'"
    (home / 'config.toml').write_text('[mcp_servers.inventory_canary]\nenabled = true\ncommand = ' + quote(sys.executable) +
        '\nargs = [' + quote(canary) + ', ' + quote(marker) + ']\n', encoding='utf-8')
    flags = {'shell_tool': False, 'unified_exec': False, 'apps': False, 'multi_agent': False,
             'remote_plugin': False, 'hooks': False}
    if hardened or extended:
        flags.update({name: False for name in ('view_image', 'browser_use', 'computer_use', 'plugins',
            'code_mode_host', 'in_app_browser', 'sleep_tool', 'tool_suggest')})
    if extended:
        flags.update({name: False for name in ('image_generation', 'goals', 'skill_search',
            'skill_mcp_dependency_install', 'realtime_conversation')})
    args = [str(EXECUTABLE), 'app-server', '--listen', 'stdio://', '-c', 'model_provider="openai"',
            '-c', 'forced_login_method="chatgpt"', '-c', 'web_search="disabled"', '-c', 'mcp_servers={}', '-c', 'plugins={}',
            '-c', 'tools.view_image=false']
    for name in flags:
        args.extend(['-c', 'features.' + name + '=false'])
    env = {key: value for key, value in os.environ.items() if not re.search(r'TOKEN|API_KEY|SECRET|PASSWORD', key.upper())
           and key.upper() not in {'OPENAI_BASE_URL', 'OPENAI_API_BASE', 'AXX_HOST_INSTANCE'}}
    env['CODEX_HOME'] = str(home)
    result = {'classification': 'REAL_APPSERVER_NO_INFERENCE_DIAGNOSTIC', 'codex_version': '0.160.0',
        'isolated_codex_home': True, 'credentials_imported': False, 'user_config_modified': False,
        'turn_start_sent': False, 'builtin_inventory_complete': False, 'hardened_feature_probe': hardened or extended,
        'extended_feature_probe': extended,
        'requested_feature_flags': flags, 'scratch_directory': str(scratch),
        'schema_sha256': {name: digest(SCHEMA / name) for name in ['ClientRequest.json', 'v2/ThreadStartResponse.json', 'v2/ListMcpServerStatusParams.json', 'v2/ListMcpServerStatusResponse.json']},
        'provider_sha256_at_start': digest(ROOT / 'backend/connect/provider.py'), 'calls': [], 'notifications': {}}
    process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', bufsize=1,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    replies, pending, guard = queue.Queue(), {}, threading.RLock()
    stderr_count = [0]
    def reader():
        for line in process.stdout:
            try: message = json.loads(line)
            except ValueError: continue
            if 'id' in message and ('result' in message or 'error' in message):
                replies.put(message)
            elif 'method' in message:
                with guard:
                    result['notifications'][message['method']] = result['notifications'].get(message['method'], 0) + 1
    def drain():
        for line in process.stderr:
            stderr_count[0] += 1
    threading.Thread(target=reader, daemon=True).start(); threading.Thread(target=drain, daemon=True).start()
    serial = [0]
    def rpc(method, params, timeout=8):
        assert method in ALLOWED, 'No inference/auth/mutation methods permitted by diagnostic'
        serial[0] += 1; identity = serial[0]; began = time.monotonic()
        process.stdin.write(json.dumps({'id': identity, 'method': method, 'params': params}) + '\n'); process.stdin.flush()
        call = {'method': method, 'timeout_seconds': timeout}
        result['calls'].append(call)
        limit = began + timeout
        while time.monotonic() < limit:
            try: reply = replies.get(timeout=max(.001, limit-time.monotonic()))
            except queue.Empty: break
            if reply['id'] != identity:
                pending[reply['id']] = reply; continue
            call['elapsed_ms'] = round((time.monotonic()-began)*1000, 1)
            if 'error' in reply:
                call.update(outcome='rpc_error', error_code=reply['error'].get('code'))
                # Isolated home has no credentials, but retain only known error
                # classifications rather than unbounded runtime text.
                call['error_type'] = 'authentication' if 'auth' in str(reply['error']).lower() else 'runtime_rejection'
                return None
            call['outcome'] = 'responded'; return reply.get('result', {})
        call.update(outcome='timeout', elapsed_ms=round((time.monotonic()-began)*1000, 1)); return None
    def feature_pages(thread_id=None):
        rows, cursor, pages = [], None, 0
        for _ in range(10):
            params = {'limit': 100}
            if thread_id: params['threadId'] = thread_id
            if cursor: params['cursor'] = cursor
            page = rpc('experimentalFeature/list', params)
            if page is None: return rows, True, pages
            rows.extend(page.get('data', [])); pages += 1
            cursor = page.get('nextCursor')
            if not cursor: break
        return rows, bool(cursor), pages
    try:
        init = rpc('initialize', {'clientInfo': {'name': 'axx_inventory_diagnostic', 'title': 'Axx inventory diagnostic', 'version': '0.1.0'}, 'capabilities': {'experimentalApi': True}})
        if init is None: return result
        process.stdin.write('{"method":"initialized"}\n'); process.stdin.flush()
        effective = rpc('config/read', {'includeLayers': False})
        if effective is not None:
            config = effective.get('config', {})
            result['effective_config'] = {'requested_feature_flags': {name: (config.get('features') or {}).get(name) for name in flags},
                'view_image': (config.get('tools') or {}).get('view_image'), 'web_search': config.get('web_search'),
                'mcp_server_count': len(config.get('mcp_servers') or {}),
                'canary_enabled_after_empty_table_override': ((config.get('mcp_servers') or {}).get('inventory_canary') or {}).get('enabled')}
        feature_rows, more, pages = feature_pages()
        result['process_features'] = [{'name': row['name'], 'enabled': row['enabled'], 'stage': row['stage']}
            for row in feature_rows if row['name'] in flags or row['enabled']]
        result['feature_inventory_more_pages'] = more
        result['feature_inventory_pages'] = pages
        result['feature_inventory_count'] = len(feature_rows)
        requirements = rpc('configRequirements/read', {})
        if requirements is not None:
            req = requirements.get('requirements') or {}
            result['managed_feature_requirements'] = req.get('featureRequirements')
        thread = rpc('thread/start', {'model': 'gpt-6.1-sol', 'modelProvider': 'openai', 'cwd': str(cwd),
            'approvalPolicy': 'on-request', 'sandbox': 'read-only', 'ephemeral': True, 'environments': [], 'allowProviderModelFallback': False,
            'dynamicTools': [{'type': 'function', 'name': 'axx_inventory_noop', 'description': 'Diagnostic only; no turn is started and no tool executes.',
                              'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}],
            'config': {'features': flags, 'tools': {'view_image': False}, 'web_search': 'disabled',
                       'mcp_servers': {'inventory_canary': {'enabled': False}}, 'plugins': {}}})
        if thread is not None:
            thread_id = thread['thread']['id']
            result['thread_response'] = {'model': thread.get('model'), 'model_provider': thread.get('modelProvider'),
                'sandbox_type': thread.get('sandbox', {}).get('type'), 'response_fields': list(thread),
                'thread_fields': list(thread['thread']), 'ephemeral': thread['thread'].get('ephemeral')}
            inventory = rpc('mcpServerStatus/list', {'threadId': thread_id, 'detail': 'toolsAndAuthOnly', 'limit': 100})
            if inventory is not None:
                rows = inventory.get('data', [])
                result['thread_mcp_inventory'] = {'server_count': len(rows), 'tool_count': sum(len(row.get('tools', {})) for row in rows),
                    'canary': [{'runtime_status': row.get('runtimeStatus'), 'tool_count': len(row.get('tools', {})),
                                'tools_error': bool(row.get('toolsError'))} for row in rows if row.get('name') == 'inventory_canary'],
                    'more_pages': bool(inventory.get('nextCursor'))}
            feature_rows, more, pages = feature_pages(thread_id)
            result['thread_features'] = [{'name': row['name'], 'enabled': row['enabled'], 'stage': row['stage']}
                for row in feature_rows if row['name'] in flags or row['enabled']]
            result['thread_feature_inventory_more_pages'] = more
            result['thread_feature_inventory_pages'] = pages
            result['thread_feature_inventory_count'] = len(feature_rows)
            read = rpc('thread/read', {'threadId': thread_id, 'includeTurns': False})
            if read is not None:
                result['thread_read_fields'] = list(read.get('thread', {}))
    finally:
        result['mcp_canary_process_started'] = marker.exists()
        result['stderr_lines_drained_without_capture'] = stderr_count[0]
        result['provider_sha256_at_end'] = digest(ROOT / 'backend/connect/provider.py')
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        for pipe in (process.stdin, process.stdout, process.stderr):
            try: pipe.close()
            except OSError: pass
        destination = EVIDENCE / ('runtime-inventory-readonly-extended-result.json' if extended else
            'runtime-inventory-readonly-hardened-result.json' if hardened else 'runtime-inventory-readonly-result.json')
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--scratch'); parser.add_argument('--hardened', action='store_true')
    parser.add_argument('--extended', action='store_true')
    args = parser.parse_args()
    data = main(args.scratch, args.hardened, args.extended)
    print(json.dumps({'evidence': str(EVIDENCE / ('runtime-inventory-readonly-extended-result.json' if args.extended else
                      'runtime-inventory-readonly-hardened-result.json' if args.hardened else 'runtime-inventory-readonly-result.json')),
                      'calls': data['calls'], 'canary_started': data.get('mcp_canary_process_started'),
                      'builtin_inventory_complete': data['builtin_inventory_complete']}, indent=2))
