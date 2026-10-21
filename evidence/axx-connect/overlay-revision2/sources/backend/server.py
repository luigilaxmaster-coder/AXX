"""Private loopback service owned and authenticated by the Axx native host."""
from __future__ import annotations
import argparse
import datetime as dt
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
import os
from pathlib import Path
import secrets
import re
import shutil
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import urllib.parse
import uuid

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
from backend.inference.router import parse_strict_json
from backend.inference.adapter import InferenceAdapter, worker_main
from backend.actions.executor import ActionExecutor, ActionExecutionError
from backend.actions.tools import list_tools
from backend.commands import CommandService, ApprovalRequired, parse_command_json, ADAPTERS
from backend.memory.procedural_memory import ProceduralMemory
from backend.memory.ai_memory_adapter import AiMemoryAdapter
from backend.sync.identity_sync import IdentityStore
from backend.speech.windows_tts import WindowsSpeechService, SpeechError
from backend.speech.offline_asr import OfflineTranscriptionService, worker_main as transcribe_worker_main
from backend.auth.chatgpt_auth import ChatGPTAuthManager
from backend.inference.chatgpt_adapter import ChatGPTSubscriptionAdapter
from backend.auth.callback_page import get_callback_html
from backend.connect.http_api import ConnectHTTP, publish_endpoint, remove_endpoint
from backend.connect.service import ConnectService
from backend.connect.provider import CodexProvider, ProviderError

LOG = logging.getLogger('axx.server')
MAX_BODY = 2 * 1024 * 1024

class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 16

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_token = os.environ.get('AXX_HOST_TOKEN') or secrets.token_hex(32)
        self.instance_id = os.environ.get('AXX_HOST_INSTANCE') or str(uuid.uuid4())
        self.host_owned = bool(os.environ.get('AXX_HOST_TOKEN'))
        self.action_lock = threading.RLock()
        self.desktop_approvals = set()
        self.connect_engine_lock = threading.Lock()
        self.connect_engine_status = None
        self.connect_engine_checking = False

class AxxBridgeHandler(BaseHTTPRequestHandler):
    adapter = executor = memory = identity = speech = transcription = None
    commands = None
    chatgpt_auth = chatgpt_adapter = None
    connect = provider = None
    frontend_path = root_dir / '1.AXX' / 'Axx.html'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        LOG.debug('%s %s', self.command, urllib.parse.urlsplit(self.path).path)

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        self.close_connection = True

    def _authorized(self):
        expected_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in expected_hosts:
            self._send_json(403, {'error': {'code': 'FORBIDDEN', 'message': 'Invalid loopback host'}})
            return False
        # The UI uses native IPC. Browser-origin requests never access this private service.
        if self.headers.get('Origin'):
            self._send_json(403, {'error': {'code': 'FORBIDDEN', 'message': 'Use the native host bridge'}})
            return False
        value = self.headers.get('Authorization', '')
        if not secrets.compare_digest(value, 'Bearer ' + self.server.host_token):
            length = self.headers.get('Content-Length')
            if length and length.isdecimal():
                try:
                    self.rfile.read(min(int(length), MAX_BODY))
                except Exception:
                    pass
            self._send_json(401, {'error': {'code': 'UNAUTHORIZED', 'message': 'Native host authentication required'}})
            return False
        return True

    def do_OPTIONS(self):
        self._send_json(403, {'error': {'code': 'FORBIDDEN', 'message': 'Browser access is disabled'}})

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/auth/callback':
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            code = query.get('code', [''])[0]
            state = query.get('state', [''])[0]
            success, msg = False, "Código o estado no proporcionado"
            if self.chatgpt_auth and code and state:
                success, msg = self.chatgpt_auth.handle_callback(code, state)
            user_name = self.chatgpt_auth.get_status().get('name') if (self.chatgpt_auth and success) else None
            content = get_callback_html(success, msg, user_name)
            self.send_response(200 if success else 400)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
            self.close_connection = True
            return

        if path in ('/', '/Axx.html', '/Axx-20.html', '/index.html') and not self.server.host_owned:
            if not self.frontend_path.exists():
                self._send_json(404, {'error': 'Frontend is unavailable'})
                return
            content = self.frontend_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
            self.close_connection = True
            return
        if not self._authorized():
            return
        try:
            if ConnectHTTP(self).get(path):
                return
            if path == '/axx-api/status':
                self._send_json(200, {'ready': True, 'instance_id': self.server.instance_id,
                    'pid': os.getpid(), 'provider': 'Axx Hardened Inference Router',
                    'native': self.server.host_owned, 'desktop': {'available': os.name == 'nt' and self.server.host_owned,
                    'platform': sys.platform}, 'details': self.adapter.get_status(),
                    'chatgpt_auth': self.chatgpt_auth.get_status() if self.chatgpt_auth else {'authenticated': False},
                    'memory': self.memory.ai_memory.status() if self.memory.ai_memory else {'backend': 'sqlite', 'available': False},
                    'features': {'actions': True, 'command_library': bool(self.commands), 'procedural_memory': True, 'spotify': False,
                                 'chatgpt_subscription': bool(self.chatgpt_auth and self.chatgpt_auth.is_authenticated()),
                                 'remote_inference_configured': any(p.get('enabled') for p in self.adapter.config.get('providers', []))}})
            elif path == '/axx-api/auth/chatgpt/status':
                self._send_json(200, self.chatgpt_auth.get_status() if self.chatgpt_auth else {'authenticated': False})
            elif path == '/axx-api/auth/chatgpt/start':
                if not self.chatgpt_auth:
                    self._unsupported('ChatGPT Auth no está disponible')
                    return
                res = self.chatgpt_auth.start_oauth(self.server.server_port, open_browser=True)
                self._send_json(200, res)
            elif path == '/axx-api/auth/chatgpt/disconnect':
                if self.chatgpt_auth:
                    self.chatgpt_auth.clear_auth()
                self._send_json(200, {'ok': True, 'message': 'Desconectado'})
            elif path == '/axx-api/models':
                models = list(dict.fromkeys(p['model'] for p in self.adapter.get_status().get('providers', [])))
                if self.chatgpt_auth and self.chatgpt_auth.is_authenticated():
                    models = list(dict.fromkeys(self.chatgpt_auth.get_status().get('models', []) + models))
                self._send_json(200, {'models': models, 'chatgpt_active': bool(self.chatgpt_auth and self.chatgpt_auth.is_authenticated())})
            elif path == '/axx-api/actions':
                self._send_json(200, {'tools': list_tools(), 'artifact_root': str(self.executor.workspace_root)})
            elif path in ('/axx-api/commands', '/axx-api/commands/operations'):
                if not self.commands:
                    self._unsupported('Command library service is unavailable')
                    return
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                allowed = {'q', 'limit', 'offset'} if path == '/axx-api/commands' else {'operation_id'}
                if set(query) - allowed or any(len(values) != 1 for values in query.values()):
                    raise ValueError('Invalid command query fields')
                if path == '/axx-api/commands':
                    self._send_json(200, self.commands.search(query.get('q', [''])[0],
                        int(query.get('limit', ['30'])[0]), int(query.get('offset', ['0'])[0])))
                elif 'operation_id' in query:
                    operation = self.commands.get(query['operation_id'][0])
                    self._send_json(200 if operation else 404, {'operation': operation})
                else:
                    self._send_json(200, {'operations': self.commands.operations()})
            elif path == '/axx-api/actions/operations':
                with self.server.action_lock:
                    self._send_json(200, {'operations': self.executor.list_operations()})
            elif path == '/axx-api/recipes':
                with self.server.action_lock:
                    recipes = self.memory.list_recipes()
                    for recipe in recipes:
                        compatible = self.memory.find_recipe(recipe['intent_key'])
                        recipe['schema'] = compatible.schema if compatible else None
                    self._send_json(200, {'recipes': recipes, 'memory': self._memory_status()})
            elif path == '/axx-api/speech/voices':
                if not self.speech:
                    self._unsupported('Windows speech service is unavailable')
                else:
                    self._send_json(200, self.speech.voices())
            elif path == '/axx-api/speech/status':
                self._send_json(200, {'tts': {'engine':'windows-sapi','configured':bool(self.speech and self.speech.available)},
                                     'asr':self.transcription.status() if self.transcription else {'available':False}})
            elif path == '/axx-api/identity':
                with self.server.action_lock:
                    self._send_json(200, {'identity': self.identity.get_studio_identity()})
            elif path.startswith('/axx-api/spotify/'):
                self._unsupported('Spotify requires a separately configured account integration')
            else:
                self._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': 'Endpoint not found'}})
        except ProviderError as exc:
            self._send_json(409 if exc.code == 'BUSY' else 400, {'error': {'code': exc.code, 'message': str(exc)}})
        except SpeechError as exc:
            self._speech_error(exc)
        except ValueError as exc:
            self._send_json(400, {'error': {'code': 'INVALID_REQUEST', 'message': str(exc)}})
        except Exception:
            LOG.exception('GET endpoint failed')
            self._send_json(500, {'error': {'code': 'STATE_UNAVAILABLE', 'message': 'Local state operation failed'}})

    def _unsupported(self, message):
        self._send_json(501, {'connected': False, 'available': False,
                             'error': {'code': 'NOT_CONFIGURED', 'message': message}})

    def _memory_status(self):
        return self.memory.ai_memory.status() if self.memory.ai_memory else {'backend': 'sqlite', 'available': False, 'fallback': True}

    def _speech_error(self, error):
        status = {'INVALID_REQUEST':400, 'BUSY':409, 'CANCELLED':499, 'NOT_SUPPORTED':501, 'DEADLINE_EXCEEDED':504}.get(error.code,502)
        self._send_json(status, {'error': {'code': error.code, 'message': str(error)}})

    def _body(self):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked bodies are unsupported')
        length_header = self.headers.get('Content-Length')
        if not length_header or not length_header.isdecimal():
            raise ValueError('Content-Length is required')
        length = int(length_header)
        if length > MAX_BODY:
            self._send_json(413, {'error': {'code': 'INVALID_REQUEST', 'message': 'Body exceeds 2 MiB limit'}})
            return None
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Content-Type must be application/json')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('Incomplete body')
        body = parse_command_json(raw) if raw else {}
        if not isinstance(body, dict):
            raise ValueError('JSON body must be an object')
        return body

    def do_POST(self):
        if not self._authorized():
            return
        try:
            body = self._body()
            if body is None:
                return
        except (ValueError, UnicodeError, socket.timeout):
            self._send_json(400, {'error': {'code': 'INVALID_REQUEST', 'message': 'Invalid bounded JSON request body'}})
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if ConnectHTTP(self).post(path, body):
                return
            if path == '/axx-api/chat':
                if body.get('provider') == 'chatgpt' or body.get('mode') == 'auth':
                    self._send_json(409, {'error': {'code': 'USE_AXX_CONNECT', 'message': 'Usa Axx Connect con el runtime oficial de Codex; el transporte OAuth anterior está desactivado.'}})
                    return
                if set(body) - {'model', 'stream', 'axx_task', 'messages', 'temperature', 'max_tokens', 'tools',
                                'request_id', 'conversation_id', 'deadline_ms', 'sensitivity',
                                'provider', 'allow_fallback', 'mode'}:
                    raise ValueError('Unsupported chat fields')

                model = body.get('model', '')
                is_chatgpt = (body.get('provider') == 'chatgpt' or 
                              body.get('mode') == 'auth' or 
                              model in ('gpt-4o', 'gpt-4o-mini', 'o1-mini', 'chatgpt-auto') or
                              (self.chatgpt_auth and self.chatgpt_auth.is_authenticated() and body.get('provider') in (None, 'chatgpt', 'bridge') and model.startswith('gpt-')))

                if is_chatgpt and self.chatgpt_adapter and self.chatgpt_adapter.is_available():
                    try:
                        res = self.chatgpt_adapter.chat(
                            model=model or 'gpt-4o',
                            messages=body.get('messages', []),
                            allow_fallback=body.get('allow_fallback', True)
                        )
                        message = res['choices'][0]['message']
                        if body.get('stream') is True:
                            payload = ('data: ' + json.dumps({'delta': message.get('content', ''), 'done': True,
                                       'choices': [{'delta': message, 'finish_reason': 'stop'}]}) + '\n\ndata: [DONE]\n\n').encode('utf-8')
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                            self.send_header('Content-Length', str(len(payload)))
                            self.send_header('Connection', 'close')
                            self.end_headers()
                            self.wfile.write(payload)
                            self.close_connection = True
                        else:
                            self._send_json(200, {
                                'request_id': body.get('request_id') or str(uuid.uuid4()),
                                'choices': [{'message': message, 'finish_reason': 'stop'}],
                                'axx_router': res.get('axx_router')
                            })
                        return
                    except Exception as exc:
                        LOG.error('ChatGPT inference execution error: %s', exc)
                        self._send_json(502, {'ok': False, 'error': {'code': 'CHATGPT_ERROR', 'message': str(exc), 'retryable': True}})
                        return

                envelope = {'task': body.get('axx_task', 'chat'), 'messages': body.get('messages', []),
                    'generation': {key: body[key] for key in ('temperature', 'max_tokens', 'tools') if key in body}}
                for key in ('request_id', 'conversation_id', 'deadline_ms', 'sensitivity'):
                    if key in body:
                        envelope[key] = body[key]
                result = self.adapter.route(envelope)
                if not result.get('ok'):
                    code = result.get('error', {}).get('code')
                    status = 409 if code == 'BUSY' else 400 if code == 'INVALID_REQUEST' else 499 if code == 'CANCELLED' else 502
                    self._send_json(status, result)
                    return
                message = result['message']
                # Compatibility SSE carries one complete response; providers always stream=false.
                if body.get('stream') is True:
                    payload = ('data: ' + json.dumps({'delta': message.get('content', ''), 'done': True,
                               'choices': [{'delta': message, 'finish_reason': 'stop'}]}) + '\n\ndata: [DONE]\n\n').encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                    self.send_header('Content-Length', str(len(payload)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(payload)
                    self.close_connection = True
                else:
                    self._send_json(200, {'request_id': result['request_id'], 'choices': [{'message': message, 'finish_reason': 'stop'}],
                                         'axx_router': result.get('route')})
            elif path == '/axx-api/chat/cancel':
                request_id = body.get('request_id')
                if not isinstance(request_id, str):
                    raise ValueError('request_id is required')
                if self.provider:
                    self.provider.cancel(request_id)
                self._send_json(200, {'request_id': request_id, 'cancelled': self.adapter.cancel(request_id)})
            elif path == '/axx-api/auth/save-key':
                provider_type = body.get('provider', 'openrouter')
                api_key = (body.get('api_key') or '').strip()
                if not api_key:
                    raise ValueError('La clave de API es requerida')
                
                env_map = {
                    'openrouter': 'OPENROUTER_API_KEY',
                    'openai': 'OPENAI_API_KEY',
                    'gemini': 'GEMINI_API_KEY'
                }
                env_var = env_map.get(provider_type, 'OPENROUTER_API_KEY')
                os.environ[env_var] = api_key

                cfg_path = getattr(self, 'config_path', None)
                if not cfg_path or not Path(cfg_path).exists():
                    cfg_path = root_dir / 'providers.json'
                
                cfg = {}
                try:
                    cfg = parse_strict_json(Path(cfg_path).read_bytes())
                except Exception:
                    cfg = {'providers': []}
                if not isinstance(cfg.get('providers'), list):
                    cfg['providers'] = []

                found = False
                for p in cfg['providers']:
                    if p.get('api_key_env') == env_var or (provider_type == 'openrouter' and 'openrouter' in p.get('name', '')):
                        p['enabled'] = True
                        p['api_key_env'] = env_var
                        found = True
                        break
                if not found:
                    if provider_type == 'openai':
                        cfg['providers'].append({
                            "name": "openai-direct",
                            "base_url": "https://api.openai.com/v1",
                            "model": "gpt-4o-mini",
                            "api_key_env": "OPENAI_API_KEY",
                            "enabled": True,
                            "daily_attempt_limit": 100,
                            "max_output_tokens": 2048,
                            "capabilities": ["text", "tools"]
                        })
                    elif provider_type == 'gemini':
                        cfg['providers'].append({
                            "name": "gemini-flash",
                            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                            "model": "gemini-2.0-flash",
                            "api_key_env": "GEMINI_API_KEY",
                            "enabled": True,
                            "daily_attempt_limit": 100,
                            "max_output_tokens": 2048,
                            "capabilities": ["text", "tools"]
                        })
                    else:
                        cfg['providers'].append({
                            "name": "openrouter-user",
                            "base_url": "https://openrouter.ai/api/v1",
                            "model": "openrouter/free",
                            "api_key_env": "OPENROUTER_API_KEY",
                            "enabled": True,
                            "daily_attempt_limit": 100,
                            "max_output_tokens": 2048,
                            "capabilities": ["text"]
                        })

                try:
                    Path(cfg_path).write_bytes(json.dumps(cfg, indent=2, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    LOG.warning('Could not write config file %s: %s', cfg_path, e)

                if hasattr(self.adapter, 'update_config'):
                    self.adapter.update_config(cfg)

                self._send_json(200, {
                    'ok': True,
                    'provider': provider_type,
                    'env_var': env_var,
                    'message': f'Clave {env_var} registrada y activada con éxito.'
                })
            elif path == '/axx-api/auth/chatgpt/set-client-id':
                if not self.chatgpt_auth:
                    self._unsupported('ChatGPT Auth no está disponible')
                    return
                client_id = (body.get('client_id') or '').strip()
                self.chatgpt_auth.set_client_id(client_id)
                self._send_json(200, {
                    'ok': True,
                    'client_id': self.chatgpt_auth.get_client_id(),
                    'message': 'ID de cliente de OpenAI guardado con éxito.'
                })
            elif path.startswith('/axx-api/commands/'):
                if not self.commands:
                    self._unsupported('Command library service is unavailable')
                    return
                fields = {
                    'resolve': {'text', 'source'},
                    'prepare': {'command_id', 'inputs', 'source', 'operation_id'},
                    'execute': {'operation_id', 'approved'},
                    'cancel': {'operation_id'},
                }
                action = path.rsplit('/', 1)[-1]
                if action not in fields or set(body) - fields[action]:
                    raise ValueError('Unsupported command request fields')
                if action == 'resolve':
                    result = self.commands.resolve(body.get('text'), body.get('source', 'text'))
                elif action == 'prepare':
                    result = self.commands.prepare(body.get('command_id'), body.get('inputs', {}),
                        body.get('source', 'text'), body.get('operation_id'))
                elif action == 'execute':
                    result = self.commands.execute(body.get('operation_id'), body.get('approved', False))
                else:
                    result = self.commands.cancel(body.get('operation_id'))
                self._send_json(200, result)
            elif path == '/axx-api/actions/execute':
                # The legacy transport cannot confer permission to write or run blocked adapters.
                if body.get('tool_name') not in ('system_telemetry', 'process_state_inspector'):
                    self._send_json(403, {'error': {'code': 'USE_COMMAND_POLICY',
                        'message': 'Prepara y aprueba este comando en la biblioteca; la ruta antigua no autoriza efectos.'}})
                    return
                with self.server.action_lock:
                    self._send_json(200, self.executor.execute_action(body.get('tool_name'), body.get('inputs', {}), body.get('operation_id')))
            elif path == '/axx-api/actions/cancel':
                # This must not wait on action_lock, which the active render owns.
                if self.commands:
                    self.commands.cancel()
                from backend.actions.cli_blender import cancel_active
                cancelled_count = cancel_active()
                if self.speech:
                    cancelled_count += self.speech.cancel_active()
                if self.transcription:
                    cancelled_count += self.transcription.cancel_active()
                self._send_json(200, {'cancelled': cancelled_count > 0, 'cancelled_operations': cancelled_count})
            elif path == '/axx-api/speech/synthesize':
                if not self.speech:
                    self._unsupported('Windows speech service is unavailable')
                else:
                    self._send_json(200, self.speech.synthesize(body))
            elif path == '/axx-api/speech/transcribe':
                if not self.transcription:
                    self._unsupported('Local transcription is unavailable')
                else:
                    self._send_json(200, self.transcription.transcribe(body))
            elif path == '/axx-api/memory/query':
                query = body.get('query')
                if set(body) != {'query'} or not isinstance(query,str) or not 1 <= len(query) <= 4000:
                    raise ValueError('query must contain 1 to 4000 characters')
                adapter = self.memory.ai_memory
                hits = adapter.query_recipes(query) if adapter and adapter.status()['available'] else []
                self._send_json(200, {'hits': hits, 'memory': self._memory_status(), 'execution_allowed': False})
            elif path == '/axx-api/memory/read':
                recipe_id = body.get('recipe_id')
                if set(body) != {'recipe_id'} or not isinstance(recipe_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',recipe_id) or recipe_id in ('.','..'):
                    raise ValueError('Invalid recipe_id')
                adapter = self.memory.ai_memory
                page = adapter.read_recipe_page(recipe_id) if adapter and adapter.status()['available'] else None
                self._send_json(200, {'page': page, 'memory': self._memory_status(), 'execution_allowed': False})
            elif path == '/axx-api/recipes/register':
                with self.server.action_lock:
                    operation = self.executor.get_operation(body.get('operation_id'))
                    if not operation or operation.get('state') != 'succeeded' or not operation.get('postconditions_passed'):
                        raise ValueError('A persisted successful action with verified postconditions is required')
                    args, schema = operation['inputs'], {}
                    if operation['tool_name'] == 'file_artifact_writer':
                        args = {'path': '$inputs.path', 'content': '$inputs.content'}
                        schema = {'path': {'type': 'string', 'required': True},
                                  'content': {'type': 'string', 'required': True}}
                    recipe = self.memory.register_recipe(id=body.get('id'), intent_key=body.get('intent_key'),
                        steps=[{'tool': operation['tool_name'], 'args': args}], schema=schema, status='verified')
                    self._send_json(200, {'recipe': recipe.to_dict()})
            elif path in ('/axx-api/recipes/execute', '/axx-api/recipes/prepare'):
                with self.server.action_lock:
                    recipe = self.memory.find_recipe(body.get('intent_key'))
                    if not recipe:
                        self._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': 'No verified compatible recipe'}})
                    elif path.endswith('/prepare'):
                        if set(body) - {'intent_key', 'inputs', 'operation_id'} or not self.commands:
                            raise ValueError('Preparación de receta no disponible o parámetros desconocidos')
                        if len(recipe.steps) != 1 or recipe.steps[0].get('tool') not in {a['tool'] for a in ADAPTERS.values()}:
                            self._send_json(403, {'error': {'code': 'USE_COMMAND_POLICY', 'message': 'La receta requiere un adaptador de catálogo validado.'}})
                            return
                        inputs = body.get('inputs', {})
                        if not isinstance(inputs, dict) or set(inputs) - set(recipe.schema):
                            raise ValueError('Parámetros de receta desconocidos')
                        for key, rule in recipe.schema.items():
                            if rule.get('required') and key not in inputs:
                                raise ValueError('Falta un parámetro de receta')
                        step = recipe.steps[0]
                        args = {key: inputs.get(value[8:]) if isinstance(value, str) and value.startswith('$inputs.') else value
                                for key, value in step.get('args', {}).items()}
                        command_id = next(key for key, adapter in ADAPTERS.items() if adapter['tool'] == step['tool'])
                        self._send_json(200, self.commands.prepare(command_id, args, 'text', body.get('operation_id')))
                    elif any(step.get('tool') not in ('system_telemetry', 'process_state_inspector') for step in recipe.steps):
                        self._send_json(403, {'error': {'code': 'USE_COMMAND_POLICY', 'message': 'Usa la preparación de receta y confirma sus parámetros en Biblioteca.'}})
                    else:
                        self._send_json(200, self.memory.execute_recipe(recipe, body.get('inputs', {}), self.executor,
                                                                       operation_id=body.get('operation_id')))
            elif path == '/axx-api/identity':
                with self.server.action_lock:
                    self._send_json(200, {'saved': self.identity.save_studio_identity(body)})
            elif path == '/axx-api/desktop/discover':
                self._send_json(200, {'apps': [{'id': key, 'name': name, 'approved': key in self.server.desktop_approvals} for key, name in
                     [('notepad', 'Bloc de notas'), ('calc', 'Calculadora'), ('explorer', 'Explorador de archivos')]]})
            elif path == '/axx-api/desktop/authorize':
                target = body.get('id')
                if target not in ('notepad', 'calc', 'explorer') or type(body.get('approved')) is not bool:
                    raise ValueError('A discovered app id and boolean approved are required')
                with self.server.action_lock:
                    if body['approved']:
                        self.server.desktop_approvals.add(target)
                    else:
                        self.server.desktop_approvals.discard(target)
                self._send_json(200, {'id': target, 'approved': body['approved'], 'scope': 'current_session'})
            elif path == '/axx-api/desktop/revoke-all':
                with self.server.action_lock:
                    self.server.desktop_approvals.clear()
                self._send_json(200, {'ok': True, 'revoked': True, 'scope': 'current_session'})
            elif path == '/axx-api/desktop/icon':
                self._send_json(200, {'id': body.get('id'), 'available': False, 'icon': None})
            elif path == '/axx-api/desktop/launch':
                target = str(body.get('id') or body.get('app') or '').lower()
                allowed = {'notepad': 'notepad.exe', 'calc': 'calc.exe', 'calculator': 'calc.exe', 'explorer': 'explorer.exe'}
                if target not in allowed or os.name != 'nt':
                    raise ValueError('Application is unavailable or not approved')
                approved_target = 'calc' if target == 'calculator' else target
                if approved_target not in self.server.desktop_approvals:
                    self._send_json(403, {'error': {'code': 'NOT_AUTHORIZED', 'message': 'Authorize this app for the current session first'}})
                    return
                executable = Path(os.environ.get('WINDIR', r'C:\Windows')) / ('explorer.exe' if target == 'explorer' else 'System32/' + allowed[target])
                # Explicitly detach only user-approved applications from the native
                # host's kill-on-close job. Inference workers remain job-owned.
                process = subprocess.Popen([str(executable)], shell=False,
                                           creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB | subprocess.CREATE_NO_WINDOW)
                self._send_json(200, {'ok': True, 'launched': target, 'pid': process.pid,
                                     'state': 'dispatched', 'verified': False})
            elif path.startswith('/axx-api/spotify/'):
                self._unsupported('Spotify playback has no configured integration')
            else:
                self._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': 'Endpoint not found'}})
        except SpeechError as exc:
            self._speech_error(exc)
        except ProviderError as exc:
            self._send_json(409 if exc.code == 'BUSY' else 400, {'error': {'code': exc.code, 'message': str(exc)}})
        except ApprovalRequired as exc:
            self._send_json(403, {'error': {'code': 'APPROVAL_REQUIRED', 'message': str(exc)}})
        except (ValueError, TypeError, ActionExecutionError) as exc:
            self._send_json(400, {'error': {'code': 'INVALID_REQUEST', 'message': str(exc)}})
        except Exception:
            LOG.exception('POST endpoint failed')
            self._send_json(500, {'error': {'code': 'STATE_UNAVAILABLE', 'message': 'Local operation failed; inspect diagnostics'}})

def resolve_app_paths(config_path='providers.json', state_path='state.db', data_dir=None):
    """Migrate legacy files only on first use; never overwrite existing user data."""
    app_dir = Path(data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'Axx').resolve()
    app_dir.mkdir(parents=True, exist_ok=True)
    resolved_config = app_dir / 'providers.json' if config_path in ('providers.json', '') else Path(config_path).resolve()
    resolved_state = app_dir / 'state.db' if state_path in ('state.db', '') else Path(state_path).resolve()
    if not resolved_config.exists():
        candidates = [root_dir / 'providers.json', Path(getattr(sys, '_MEIPASS', root_dir)) / 'resources' / 'providers.default.json',
                      root_dir / 'resources' / 'providers.default.json']
        source = next((p for p in candidates if p.is_file() and p.resolve() != resolved_config), None)
        if source:
            shutil.copy2(source, resolved_config)
        else:
            resolved_config.write_text(json.dumps({'allow_paid': False, 'providers': []}), encoding='utf-8')
    legacy_state = root_dir / 'state.db'
    if not resolved_state.exists() and legacy_state.is_file() and legacy_state.resolve() != resolved_state:
        source_db = sqlite3.connect(f'file:{legacy_state.as_posix()}?mode=ro', uri=True)
        destination = sqlite3.connect(str(resolved_state))
        try:
            source_db.backup(destination)
        finally:
            source_db.close()
            destination.close()
    return str(resolved_config), str(resolved_state)

def run_server(host='127.0.0.1', port=4173, config_path='providers.json', state_path='state.db', data_dir=None, ready_file=None):
    if host != '127.0.0.1':
        raise ValueError('Backend must bind only to 127.0.0.1')
    if ready_file and len(os.environ.get('AXX_HOST_TOKEN', '')) < 32:
        raise ValueError('Native host must supply a private token of at least 32 characters')
    config_path, state_path = resolve_app_paths(config_path, state_path, data_dir)
    config = parse_strict_json(Path(config_path).read_bytes())
    state_dir = Path(state_path).parent
    # Capture one consistent SQLite backup before the delivery schema migration.
    migration_backup = state_dir / 'backups' / 'state-before-desktop-v1.db'
    if Path(state_path).exists() and not migration_backup.exists():
        migration_backup.parent.mkdir(parents=True, exist_ok=True)
        source_db = sqlite3.connect(f'file:{Path(state_path).as_posix()}?mode=ro', uri=True)
        backup_db = sqlite3.connect(str(migration_backup))
        try:
            source_db.backup(backup_db)
        finally:
            source_db.close()
            backup_db.close()
    services = []
    server = None
    ready_path = Path(ready_file).resolve() if ready_file else None
    try:
        adapter = InferenceAdapter(config, state_path=state_path)
        services.append(adapter)
        executor = ActionExecutor(db_path=state_path, workspace_root=state_dir / 'artifacts')
        services.append(executor)
        commands = CommandService(executor)
        services.append(commands)
        speech = WindowsSpeechService(state_dir)
        services.append(speech)
        transcription = OfflineTranscriptionService(state_dir)
        services.append(transcription)
        memory_adapter = AiMemoryAdapter(start_owned=True, data_dir=state_dir / 'ai-memory')
        services.append(memory_adapter)
        memory = ProceduralMemory(db_path=state_path, ai_memory=memory_adapter)
        services.append(memory)
        identity = IdentityStore(db_path=state_path)
        services.append(identity)
        # Codex owns its authentication. Never load/copy legacy Axx OAuth tokens.
        chatgpt_auth = chatgpt_adapter = None
        connect = ConnectService(commands, memory)
        services.append(connect)
        provider = CodexProvider(commands, state_path, state_dir, dispatcher=connect.dispatch)
        services.append(provider)
        handler = type('ConfiguredAxxHandler', (AxxBridgeHandler,), {
            'adapter': adapter, 'executor': executor, 'commands': commands,
            'memory': memory, 'identity': identity, 'speech': speech,
            'transcription': transcription, 'chatgpt_auth': chatgpt_auth,
            'chatgpt_adapter': chatgpt_adapter, 'config_path': Path(config_path),
            'connect': connect, 'provider': provider
        })
        server = ThreadedHTTPServer((host, port), handler)
        publish_endpoint(state_dir, server)
        if ready_path:
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = ready_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'port': server.server_port, 'pid': os.getpid(), 'parent_pid': os.getppid(),
                                             'instance_id': server.instance_id}), encoding='utf-8')
            os.replace(temporary, ready_path)
        LOG.info('Private Axx backend ready on loopback port %s', server.server_port)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        from backend.actions.cli_blender import cancel_active
        cancel_active()
        if server:
            server.server_close()
            remove_endpoint(state_dir, server.instance_id)
        for service in reversed(services):
            service.close()
        if ready_path:
            ready_path.unlink(missing_ok=True)

def main():
    if '--mcp-server' in sys.argv[1:]:
        from backend.connect.mcp_server import main as mcp_main
        return mcp_main()
    parser = argparse.ArgumentParser(description='Axx private native-host backend')
    parser.add_argument('--router-worker', action='store_true')
    parser.add_argument('--transcribe-worker', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--config', default='providers.json')
    parser.add_argument('--state', default='state.db')
    parser.add_argument('--data-dir')
    parser.add_argument('--ready-file')
    parser.add_argument('--mcp-server', action='store_true', help='Run Axx Connect MCP over stdio (no separate executor)')
    args = parser.parse_args()
    if args.router_worker:
        return worker_main(args.state)
    if args.transcribe_worker:
        return transcribe_worker_main()
    logging.basicConfig(level=logging.INFO)
    run_server(host=args.host, port=args.port, config_path=args.config, state_path=args.state,
               data_dir=args.data_dir, ready_file=args.ready_file)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
