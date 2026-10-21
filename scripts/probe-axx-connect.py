"""Real MCP SDK client probe; no mocks, no credential inspection, bounded waits.

Uses the exact shipped stdio launcher. Default performs discovery and a real
read-only status. --execute-telemetry adds one persisted read-only executor task
and checks a repeat of its ID returns the same result without another effect.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def payload(result):
    data = result.structuredContent
    if data is None:
        text = next((item.text for item in result.content if item.type == 'text'), '{}')
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('MCP did not return a structured object')
    if result.isError:
        error = data.get('error', {})
        raise ValueError(str(error.get('message', error.get('code', 'MCP tool failed'))))
    return data


async def probe(args):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from backend.connect.registry import tool_descriptors
    launcher = root / 'plugins' / 'axx-connect' / 'server' / 'launch.ps1'
    parameters = StdioServerParameters(command='powershell.exe', args=[
        '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(launcher)],
        cwd=str(root), env=os.environ.copy())
    report = {'schema_version': 1, 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'transport': 'stdio', 'client': 'official Python MCP SDK', 'mocked': False,
              'launcher': str(launcher), 'checks': [], 'ok': False}
    try:
        async with asyncio.timeout(60):
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as session:
                    init = await session.initialize()
                    report['server'] = init.serverInfo.model_dump()
                    listed = await session.list_tools()
                    names = sorted(tool.name for tool in listed.tools)
                    expected = sorted(item['name'] for item in tool_descriptors())
                    if names != expected:
                        raise ValueError('Discovered tool names differ from the documented interface')
                    report['checks'].append({'name': 'startup_and_discovery', 'passed': True, 'tools': names})
                    status = payload(await session.call_tool('axx_status', {}))
                    if status.get('executor') != 'ready':
                        raise ValueError('The Axx executor is not ready')
                    report['status'] = {key: status.get(key) for key in ('version', 'executor', 'ui_connected', 'backend_enabled', 'ui_enabled', 'capability_count')}
                    engine = status.get('engine', {})
                    report['engine'] = {key: engine.get(key) for key in ('state', 'authenticated', 'inference_verified', 'model')}
                    report['checks'].append({'name': 'authenticated_running_axx_status', 'passed': True})
                    capabilities = payload(await session.call_tool('axx_list_capabilities', {'query': 'axx.system.telemetry', 'limit': 10}))
                    command = next((item for item in capabilities.get('commands', []) if item['id'] == 'axx.system.telemetry'), None)
                    if not command or not command.get('execution_enabled'):
                        raise ValueError('The existing telemetry adapter is unavailable')
                    report['checks'].append({'name': 'real_registry_discovery', 'passed': True, 'command_id': command['id']})
                    if args.execute_telemetry:
                        operation_id = 'plugin-probe-' + uuid.uuid4().hex
                        request = {'command_id': 'axx.system.telemetry', 'inputs': {}, 'operation_id': operation_id}
                        task = payload(await session.call_tool('axx_execute_action', request))
                        deadline = time.monotonic() + 15
                        while task.get('state') in ('prepared', 'running', 'queued', 'claimed') and time.monotonic() < deadline:
                            await asyncio.sleep(.15)
                            task = payload(await session.call_tool('axx_get_task', {'operation_id': operation_id}))
                        if task.get('state') != 'succeeded' or task.get('postconditions_passed') is not True:
                            raise ValueError('Telemetry did not complete with verified postconditions')
                        report['operation'] = {key: task.get(key) for key in ('operation_id', 'command_id', 'state', 'postconditions_passed', 'duration_ms', 'procedure_id')}
                        report['operation']['output'] = task.get('output')
                        report['operation']['evidence'] = task.get('evidence')
                        repeat = payload(await session.call_tool('axx_execute_action', request))
                        if repeat.get('replayed') is not True or repeat.get('operation_id') != operation_id:
                            raise ValueError('Idempotent replay was not confirmed')
                        report['checks'].extend([{'name': 'real_executor_verified_telemetry', 'passed': True}, {'name': 'idempotent_replay', 'passed': True}])
                    report['ok'] = True
    except Exception as exc:
        # Do not write headers, subprocess environment, tokens or raw stderr.
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)[:600]}
    report['completed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    output = Path(args.output) if args.output else root / 'evidence' / 'axx-connect' / 'plugin-sdk-probe.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-telemetry', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args()
    return asyncio.run(probe(args))


if __name__ == '__main__':
    sys.exit(main())
