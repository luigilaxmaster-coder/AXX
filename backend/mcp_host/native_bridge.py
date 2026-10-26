"""MCP transport below ActionExecutor: single-use admission, shared native input owner."""
from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import socket
import threading
import time

from .client_manager import Transport


NATIVE_TOOLS = frozenset({
    'computer_window', 'computer_observe', 'computer_find', 'computer_input', 'computer_state', 'computer_grid',
    'desktop_window_observe', 'desktop_window_state', 'desktop_list_windows', 'desktop_inspect_window',
    'desktop_read_window', 'desktop_focus_window', 'desktop_move_pointer', 'desktop_find_control',
})


class NativeMcpBridge:
    tools = NATIVE_TOOLS

    def __init__(self):
        self.lock = threading.RLock()
        self.active = None
        self.transport = self.server = self.thread = self.socket = None
        self.token = secrets.token_urlsafe(32)
        self.closed = False

    def _start(self):
        if self.transport and not self.transport.closed: return
        if self.closed: raise ValueError('Fachada MCP cerrada')
        if self.server is None:
            import uvicorn
            from mcp.server.fastmcp import FastMCP
            mcp = FastMCP('Axx admitted native primitives', host='127.0.0.1', stateless_http=True, json_response=True)

            @mcp.tool()
            async def axx_native_execute(ticket: str) -> dict:
                """Execute only the one native primitive already admitted by Axx; no arbitrary action arguments."""
                return await asyncio.to_thread(self._redeem, ticket)

            app = mcp.streamable_http_app()
            token = self.token

            async def authenticated(scope, receive, send):
                if scope['type'] == 'http':
                    headers = dict(scope['headers'])
                    authorization = headers.get(b'authorization', b'')
                    if not hmac.compare_digest(authorization, ('Bearer ' + token).encode()):
                        await send({'type': 'http.response.start', 'status': 401, 'headers': []})
                        await send({'type': 'http.response.body', 'body': b'Unauthorized'})
                        return
                    consumed = 0
                    async def bounded_receive():
                        nonlocal consumed
                        message = await receive()
                        consumed += len(message.get('body', b''))
                        if consumed > 16384: raise ValueError('Native MCP request exceeds limit')
                        return message
                    return await app(scope, bounded_receive, send)
                return await app(scope, receive, send)

            self.socket = socket.socket()
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(('127.0.0.1', 0))
            self.socket.listen(8)
            self.port = self.socket.getsockname()[1]
            self.server = uvicorn.Server(uvicorn.Config(authenticated, log_level='critical', access_log=False, lifespan='on'))
            self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.socket]}, daemon=True, name='axx-native-mcp')
            self.thread.start()
            deadline = time.monotonic() + 5
            while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.01)
            if not self.server.started: raise ValueError('No inició la fachada MCP nativa')
        self.transport = Transport({'transport': 'streamable_http', 'url': f'http://127.0.0.1:{self.port}/mcp', 'token': self.token})

    def _redeem(self, ticket):
        with self.lock:
            item = self.active
            if (not isinstance(ticket, str) or len(ticket) > 100 or not item
                    or not hmac.compare_digest(ticket, item['ticket'])):
                raise ValueError('No existe una operación admitida para este ticket')
            if item['done']:
                return {'receipt': item['receipt']}
            if item['started']: raise ValueError('Operación ya en curso; no se repite')
            if item['cancelled'].is_set() or time.monotonic() > item['expires']:
                raise ValueError('Admisión cancelada o vencida')
            item['started'] = True
        try:
            # This invokes only the admitted tool body. It never re-enters the executor or its journal.
            result = item['body']()
            with self.lock:
                item['result'] = result
                item['done'] = True
            return {'receipt': item['receipt']}
        finally:
            item['finished'].set()

    def execute(self, tool_name, body, cancelled, operation_id):
        from backend.actions.tools import ToolResult
        if tool_name not in NATIVE_TOOLS: raise ValueError('Primitiva no permitida por la fachada nativa')
        with self.lock:
            if self.active and not self.active['finished'].is_set():
                return ToolResult(False, error='La operación nativa anterior aún no terminó', evidence={'effect_uncertain': False})
            if cancelled.is_set(): return ToolResult(False, error='Cancelado antes de MCP', evidence={'cancelled': True})
            self._start()
            item = {'ticket': secrets.token_urlsafe(32), 'receipt': secrets.token_urlsafe(32),
                    'operation_id': operation_id, 'body': body, 'cancelled': cancelled, 'expires': time.monotonic() + 30,
                    'started': False, 'done': False, 'finished': threading.Event()}
            self.active = item
        try:
            reply = self.transport.request('tools/call', cancelled, name='axx_native_execute', arguments={'ticket': item['ticket']})
            value = reply.get('structuredContent')
            if value is None:
                value = json.loads(next(block['text'] for block in reply.get('content', []) if block.get('type') == 'text'))
            if reply.get('isError') or not item['done'] or not hmac.compare_digest(str(value.get('receipt', '')), item['receipt']):
                raise ValueError('Falta el recibo local de la operación nativa')
            result = item['result']
            result.evidence = {**result.evidence, 'transport': 'mcp_streamable_http', 'native_operation_id': operation_id}
            return result
        except Exception as exc:
            cancelled.set()
            return ToolResult(False, error='Fallo de transporte MCP nativo: ' + type(exc).__name__,
                              evidence={'effect_uncertain': item['started'], 'cancelled': True})
        finally:
            with self.lock:
                if not item['started'] or item['finished'].is_set(): self.active = None

    def close(self):
        self.closed = True
        with self.lock:
            if self.active: self.active['cancelled'].set()
        if self.transport: self.transport.close()
        if self.server: self.server.should_exit = True
        if self.thread: self.thread.join(timeout=3)
        if self.socket: self.socket.close()
