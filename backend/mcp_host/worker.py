"""Pinned SDK transport process. stdout contains only bounded host protocol messages."""
import asyncio
from contextlib import AsyncExitStack
import datetime
import json
import logging
import os
import sys

MAX_MESSAGE = 1024 * 1024


def emit(value):
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False)
    if len(encoded) > MAX_MESSAGE:
        raise ValueError('MCP response exceeds 1 MiB')
    sys.stdout.write(encoded + '\n'); sys.stdout.flush()


async def serve(config):
    call_timeout = config.get('call_timeout', 25)
    if type(call_timeout) is not int or not 1 <= call_timeout <= 90:
        raise ValueError('Invalid bounded call timeout')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client
    import httpx
    async with AsyncExitStack() as stack:
        if config['transport'] == 'stdio':
            names = {'systemroot', 'windir', 'path', 'temp', 'tmp', 'userprofile', 'localappdata', 'appdata', 'programfiles', 'programfiles(x86)'}
            env = {key: value for key, value in os.environ.items() if key.lower() in names}
            env.update(config.get('env', {}))
            stderr = stack.enter_context(open(os.devnull, 'w'))
            streams = await stack.enter_async_context(stdio_client(StdioServerParameters(
                command=config['command'], args=config.get('args', []), env=env, cwd=config.get('cwd')), errlog=stderr))
        else:
            def client_factory(headers=None, timeout=None, auth=None):
                return httpx.AsyncClient(headers=headers, timeout=timeout or 20, auth=auth,
                                         follow_redirects=False, trust_env=False)
            headers = {'Authorization': 'Bearer ' + config['token']} if config.get('token') else {}
            streams = await stack.enter_async_context(streamablehttp_client(config['url'], headers=headers,
                timeout=call_timeout if call_timeout > 25 else 15, sse_read_timeout=call_timeout + 5, httpx_client_factory=client_factory))
        session = await stack.enter_async_context(ClientSession(streams[0], streams[1], read_timeout_seconds=datetime.timedelta(seconds=call_timeout)))
        initialized = await session.initialize()
        emit({'ready': True, 'protocol': initialized.protocolVersion,
              'server': initialized.serverInfo.model_dump(mode='json')})
        while True:
            raw = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_MESSAGE + 2)
            if not raw: break
            if len(raw) > MAX_MESSAGE or not raw.endswith(b'\n'):
                raise ValueError('Invalid bounded host request')
            request = json.loads(raw)
            try:
                if request['method'] == 'tools/list':
                    result = await session.list_tools(cursor=request.get('cursor'))
                elif request['method'] == 'tools/call':
                    result = await session.call_tool(request['name'], request['arguments'],
                        read_timeout_seconds=datetime.timedelta(seconds=call_timeout), meta=request.get('meta'))
                else:
                    raise ValueError('Unsupported host operation')
                emit({'id': request['id'], 'result': result.model_dump(mode='json', by_alias=True, exclude_none=True)})
            except Exception as exc:
                # Server errors may contain credentials or document text; expose only their class.
                emit({'id': request.get('id'), 'error': type(exc).__name__})


def main():
    logging.basicConfig(level=logging.CRITICAL, stream=sys.stderr)
    try:
        raw = sys.stdin.buffer.readline(65538)
        if len(raw) > 65536 or not raw.endswith(b'\n'): raise ValueError('Invalid connection configuration')
        asyncio.run(serve(json.loads(raw)))
        return 0
    except Exception as exc:
        emit({'ready': False, 'error': type(exc).__name__})
        return 1


if __name__ == '__main__': raise SystemExit(main())
