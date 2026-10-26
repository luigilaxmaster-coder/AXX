"""MCP transport below ActionExecutor: single-use admission, shared native input owner."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import socket
import threading
import time

from .client_manager import Transport
from .native_gateway import GATEWAY_TOOL, load_gateway_config, verify_wsl_network


NATIVE_TOOLS = frozenset({
    'computer_window', 'computer_observe', 'computer_find', 'computer_input', 'computer_state', 'computer_grid',
    'desktop_window_observe', 'desktop_window_state', 'desktop_list_windows', 'desktop_inspect_window',
    'desktop_read_window', 'desktop_focus_window', 'desktop_move_pointer', 'desktop_find_control',
    'desktop_notepad_text', 'desktop_explorer_folder', 'desktop_list_apps', 'desktop_close_window',
    'desktop_first_video_pointer', 'desktop_spotify_play', 'desktop_set_window_value', 'desktop_invoke_window_button',
    'desktop_installed_app', 'desktop_open_url', 'desktop_open_app', 'desktop_search', 'desktop_cli_anything_scan',
    'application_open', 'application_windows', 'application_focus', 'application_inspect', 'application_close', 'application_navigate',
    'application_browse', 'application_hover', 'application_youtube',
    'computer_use_observe', 'computer_use_act',
})


class NativeMcpBridge:
    tools = NATIVE_TOOLS

    def __init__(self, state_dir=None):
        self.lock = threading.RLock()
        self.active = None
        self.transport = self.server = self.thread = self.socket = None
        self.token = secrets.token_urlsafe(32)
        self.closed = False
        self.gateway = None
        self.configuration_error = False
        try:
            self.gateway = load_gateway_config(state_dir)
        except (OSError, ValueError, RuntimeError, TypeError, KeyError):
            self.configuration_error = True
        if self.gateway:
            self.token = self.gateway['native_token']
        self.state = 'error' if self.configuration_error else 'configured'
        self.last_operation_id = None

    def status(self):
        return {'mode': 'gateway' if self.gateway or self.configuration_error else 'direct',
                'state': self.state, 'last_operation_id': self.last_operation_id,
                'endpoint': self.gateway['gateway_url'] if self.gateway else None}

    def _start(self, cancelled):
        if self.configuration_error:
            raise ValueError('Configuración de gateway inválida; se bloquea la entrada nativa')
        if self.transport and not self.transport.closed: return
        if self.closed: raise ValueError('Fachada MCP cerrada')
        if self.gateway:
            verify_wsl_network(self.gateway)
        if self.server is None:
            import uvicorn
            from mcp.server.fastmcp import FastMCP
            host = self.gateway['listen_host'] if self.gateway else '127.0.0.1'
            mcp = FastMCP('Axx admitted native primitives', host=host, stateless_http=True, json_response=True)

            @mcp.tool()
            async def axx_native_execute(ticket: str) -> dict:
                """Execute only the one native primitive already admitted by Axx; no arbitrary action arguments."""
                return await asyncio.to_thread(self._redeem, ticket)

            app = mcp.streamable_http_app()
            token = self.token
            peer = self.gateway['allowed_peer'] if self.gateway else '127.0.0.1'

            async def authenticated(scope, receive, send):
                if scope['type'] == 'http':
                    headers = dict(scope['headers'])
                    authorization = headers.get(b'authorization', b'')
                    if (not scope.get('client') or scope['client'][0] != peer
                            or not hmac.compare_digest(authorization, ('Bearer ' + token).encode())):
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

            listener = socket.socket()
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind((host, self.gateway['listen_port'] if self.gateway else 0))
                listener.listen(8)
            except Exception:
                listener.close()
                raise
            self.socket = listener
            self.port = self.socket.getsockname()[1]
            self.server = uvicorn.Server(uvicorn.Config(authenticated, log_level='critical', access_log=False, lifespan='on'))
            self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.socket]}, daemon=True, name='axx-native-mcp')
            self.thread.start()
            deadline = time.monotonic() + 5
            while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.01)
            if not self.server.started:
                self.server.should_exit = True
                self.thread.join(timeout=2)
                self.socket.close()
                self.server = self.thread = self.socket = None
                raise ValueError('No inició la fachada MCP nativa')
        config = {'transport': 'streamable_http',
                  'url': self.gateway['gateway_url'] if self.gateway else f'http://127.0.0.1:{self.port}/mcp',
                  'token': self.gateway['gateway_token'] if self.gateway else self.token}
        self.transport = Transport(config, cancelled=cancelled, call_timeout=90)

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
        item = None
        try:
            with self.lock:
                if self.active and not self.active['finished'].is_set():
                    return ToolResult(False, error='La operación nativa anterior aún no terminó', evidence={'effect_uncertain': False})
                if cancelled.is_set(): return ToolResult(False, error='Cancelado antes de MCP', evidence={'cancelled': True})
                self.last_operation_id = operation_id
                self._start(cancelled)
                if cancelled.is_set() or self.closed:
                    raise ValueError('Cancelado antes de admitir la operación nativa')
                # Only an opaque operation nonce crosses the gateway; arguments and results stay here.
                item = {'ticket': secrets.token_urlsafe(32), 'receipt': secrets.token_urlsafe(32),
                        'operation_id': operation_id, 'body': body, 'cancelled': cancelled, 'expires': time.monotonic() + 30,
                        'started': False, 'done': False, 'finished': threading.Event()}
                self.active = item
                self.state = 'running'
            reply = self.transport.request('tools/call', cancelled,
                name=GATEWAY_TOOL if self.gateway else 'axx_native_execute', arguments={'ticket': item['ticket']})
            if self.gateway:
                if reply.get('isError'):
                    raise ValueError('El gateway informó un error')
                # AnythingMCP wraps the downstream CallToolResult as JSON text, including its isError.
                reply = json.loads(next(block['text'] for block in reply.get('content', []) if block.get('type') == 'text'))
                if not isinstance(reply, dict):
                    raise ValueError('Respuesta MCP descendente inválida')
            value = reply.get('structuredContent')
            if value is None:
                value = json.loads(next(block['text'] for block in reply.get('content', []) if block.get('type') == 'text'))
            if reply.get('isError') or not item['done'] or not hmac.compare_digest(str(value.get('receipt', '')), item['receipt']):
                raise ValueError('Falta el recibo local de la operación nativa')
            result = item['result']
            result.evidence = {**result.evidence,
                'transport': 'anythingmcp_streamable_http' if self.gateway else 'mcp_streamable_http',
                'native_operation_id': operation_id}
            if self.gateway:
                result.evidence['gateway_url'] = self.gateway['gateway_url']
                result.evidence['gateway_receipt_sha256'] = hashlib.sha256(item['receipt'].encode()).hexdigest()
            self.state = 'verified' if result.success else 'error'
            return result
        except Exception as exc:
            cancelled.set()
            self.state = 'error'
            return ToolResult(False, error='Fallo de transporte MCP nativo: ' + type(exc).__name__,
                              evidence={'effect_uncertain': bool(item and item['started']), 'cancelled': True,
                                        'native_started': bool(item and item['started']),
                                        'transport': 'anythingmcp_streamable_http' if self.gateway or self.configuration_error else 'mcp_streamable_http',
                                        'native_operation_id': operation_id})
        finally:
            with self.lock:
                if item is not None and (not item['started'] or item['finished'].is_set()): self.active = None

    def close(self):
        self.closed = True
        with self.lock:
            if self.active: self.active['cancelled'].set()
        if self.transport: self.transport.close()
        if self.server: self.server.should_exit = True
        if self.thread: self.thread.join(timeout=3)
        if self.socket: self.socket.close()
