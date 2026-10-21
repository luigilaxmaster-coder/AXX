"""Axx Connect MCP stdio server. stdout is exclusively MCP JSON-RPC.

This process is a client of the SAME private running Axx backend. It neither
starts a second action executor nor reads Codex model credentials. The local
bearer descriptor is Windows DPAPI protected and never logged or passed in argv.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from backend.auth.chatgpt_auth import _dpapi_decrypt
from backend.connect.registry import VERSION, tool_descriptors, validate, read_only_aliases, concrete_action_arguments

LOG = logging.getLogger('axx.connect.mcp')
MAX_REPLY = 4 * 1024 * 1024


class LocalAxxClient:
    def __init__(self, data_dir=None):
        scoped = data_dir or os.environ.get('AXX_CONNECT_DATA_DIR')
        self.data_dir = Path(scoped) if scoped else Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'Axx'

    def _descriptor(self):
        if os.name != 'nt':
            raise ValueError('Este paquete requiere Windows DPAPI y un Axx local activo.')
        path = self.data_dir / 'connect' / 'endpoint.dpapi'
        try:
            raw = path.read_bytes()
            if len(raw) > 16384:
                raise ValueError('Descriptor local inválido')
            value = json.loads(_dpapi_decrypt(raw))
        except (OSError, ValueError, RuntimeError) as exc:
            raise ValueError('Inicia la versión instalada de Axx con Axx Connect; no hay descriptor local utilizable.') from exc
        if type(value.get('port')) is not int or not 1 <= value['port'] <= 65535 or not isinstance(value.get('token'), str) or len(value['token']) < 32 or not isinstance(value.get('instance_id'), str):
            raise ValueError('Descriptor de Axx inválido; reinicia Axx.')
        return value

    def _request(self, descriptor, method, route, body=None):
        if not route.startswith('/axx-api/connect/'):
            raise ValueError('Ruta local no permitida')
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        request = urllib.request.Request('http://127.0.0.1:' + str(descriptor['port']) + route, data=data,
            headers={'Authorization': 'Bearer ' + descriptor['token'], 'Content-Type': 'application/json'}, method=method)
        try:
            # A process-local loopback connection must not inherit HTTP proxies.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=10) as response:
                raw = response.read(MAX_REPLY + 1)
                if len(raw) > MAX_REPLY:
                    raise ValueError('Respuesta local excede el límite')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Never print the request/header or an unbounded backend body.
            raw = exc.read(65536)
            try:
                error = json.loads(raw).get('error', {})
                message = error.get('message', 'Solicitud local rechazada')
            except (ValueError, AttributeError):
                message = 'Solicitud local rechazada'
            raise ValueError(f'Axx HTTP {exc.code}: {message}') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError('Axx no responde. Reinicia Axx y consulta la tarea antes de repetir efectos.') from None

    def invoke(self, name, arguments):
        definitions = {item['name']: item for item in tool_descriptors()}
        if name not in definitions:
            raise ValueError('Herramienta desconocida')
        validate(definitions[name]['inputSchema'], arguments)
        descriptor = self._descriptor()
        # Correlate live backend identity; a stale port must not silently connect
        # to an unrelated local process, even if Windows reused its port.
        status = self._request(descriptor, 'GET', '/axx-api/connect/status')
        live_id = status.get('instance_id')
        if live_id is not None and live_id != descriptor['instance_id']:
            raise ValueError('Instancia de Axx cambiada; vuelve a consultar el estado.')
        if name == 'axx_status':
            return status
        if name == 'axx_list_capabilities':
            query = urllib.parse.urlencode({'q': arguments.get('query', ''), 'limit': arguments.get('limit', 100), 'offset': arguments.get('offset', 0)})
            return self._request(descriptor, 'GET', '/axx-api/connect/capabilities?' + query)
        if name == 'axx_execute_action' or name in read_only_aliases():
            arguments = concrete_action_arguments(name, arguments)
            # The MCP boundary owns origin; callers cannot impersonate the
            # in-Axx provider or attach misleading parent/delegation metadata.
            arguments.update(origin='mcp', delegation_depth=0)
            arguments.pop('parent_execution_id', None)
            return self._request(descriptor, 'POST', '/axx-api/connect/execute', arguments)
        if name == 'axx_get_task':
            return self._request(descriptor, 'GET', '/axx-api/connect/task?' + urllib.parse.urlencode(arguments)) or {'found': False}
        return self._request(descriptor, 'POST', '/axx-api/connect/cancel', arguments) or {'found': False}


async def serve():
    from mcp import types
    from mcp.server.lowlevel import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server

    client = LocalAxxClient()
    server = Server('axx-connect', version=VERSION, instructions=(
        'Axx Connect controls the existing local Axx executor. List capabilities before execution. '
        'Use stable operation_id values. Only succeeded plus postconditions_passed=true verifies success. '
        'Writes can require approval in Axx. Never retry unknown effects blindly. '
        'No chat/planner delegation, arbitrary shell, code evaluation or cloud localhost access is available.'))

    @server.list_tools()
    async def list_tools():
        return [types.Tool(**entry) for entry in tool_descriptors()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            result = await asyncio.to_thread(client.invoke, name, arguments)
            if not isinstance(result, dict):
                result = {'result': result}
            is_error = result.get('state') in ('failed', 'blocked', 'unknown', 'expired') or bool(result.get('error'))
            return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result, ensure_ascii=False, allow_nan=False))],
                structuredContent=result, isError=is_error)
        except (ValueError, TypeError) as exc:
            result = {'error': {'code': 'AXX_CONNECT_ERROR', 'message': str(exc)}}
            return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result, ensure_ascii=False))],
                structuredContent=result, isError=True)
        except Exception as exc:
            LOG.error('Local tool failed (%s)', type(exc).__name__)
            result = {'error': {'code': 'LOCAL_FAILURE', 'message': 'Consulta el diagnóstico de Axx.'}}
            return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result))], structuredContent=result, isError=True)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(server_name='axx-connect', server_version=VERSION,
            capabilities=server.get_capabilities(NotificationOptions(), {})))


def main():
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format='%(levelname)s %(name)s: %(message)s')
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
