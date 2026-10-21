"""Owned native ai-memory MCP client; SQLite remains execution authority.

No unrelated localhost service is discovered or adopted. No models, provider
credentials, harness hooks, or autostart registration are required or changed.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

LOG = logging.getLogger('axx.ai_memory')
MAX_BYTES = 2 * 1024 * 1024


class AiMemoryAdapter:
    def __init__(self, endpoint: str | None = None, workspace: str = 'axx', project: str = 'procedural',
                 *, start_owned: bool = False, data_dir: str | Path | None = None,
                 executable: str | Path | None = None, startup_timeout: float = 8.0):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', workspace) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', project):
            raise ValueError('Invalid explicit memory scope')
        self.workspace, self.project = workspace, project
        self.endpoint = self.token = self.process = self.server_version = None
        self.is_available = False
        self.error = 'Owned ai-memory service was not started'
        self.last_sync = None
        self._counter = 0
        self._rpc_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._startup_timeout = min(15.0, max(1.0, float(startup_timeout)))
        default_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Axx' / 'ai-memory'
        self.data_dir = Path(data_dir or default_dir).resolve()
        candidate = executable or os.environ.get('AXX_AI_MEMORY_EXE')
        self.executable = (Path(candidate).resolve() if candidate else
            Path(sys.executable).resolve().parent / 'ai-memory.exe' if getattr(sys, 'frozen', False) else
            Path(__file__).resolve().parents[2] / 'src-tauri' / 'resources' / 'ai-memory.exe')
        if endpoint is not None:
            self.error = 'External memory listeners are not adopted; use the owned bundled service'
        if start_owned:
            try:
                self.start()
            except Exception as error:
                self.error = str(error)[:300]
                self.close()

    def _request(self, method: str, params: dict, timeout: float = 3.0) -> dict:
        if not self.endpoint or not self.token or not self.process or self.process.poll() is not None:
            raise RuntimeError('Owned ai-memory process is not running')
        with self._rpc_lock:
            self._counter += 1
            request_id = self._counter
            payload = json.dumps({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}, allow_nan=False).encode('utf-8')
            if len(payload) > MAX_BYTES:
                raise ValueError('Memory request exceeds its limit')
            request = urllib.request.Request(self.endpoint, data=payload, method='POST', headers={
                'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                'Authorization': 'Bearer ' + self.token})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                encoded = response.read(MAX_BYTES + 1)
            if len(encoded) > MAX_BYTES:
                raise ValueError('Memory response exceeds its limit')
            data = json.loads(encoded)
            if not isinstance(data, dict) or data.get('id') != request_id:
                raise ValueError('Memory returned an invalid correlated response')
            if data.get('error'):
                error = data['error']
                raise ValueError('MCP ' + str(error.get('code')) + ': ' + str(error.get('message', 'operation failed'))[:240])
            result = data.get('result')
            if not isinstance(result, dict) or result.get('isError'):
                raise ValueError('Memory tool returned an error')
            return result

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self.is_available and self.process and self.process.poll() is None:
                return True
            self.close()
            if not self.executable.is_file():
                self.error = 'Bundled ai-memory executable is missing'
                return False
            self.data_dir.mkdir(parents=True, exist_ok=True)
            config = self.data_dir / 'axx-service.toml'
            config.write_text('embedding_provider = "none"\n', encoding='utf-8')
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            self.token = secrets.token_hex(32)
            self.endpoint = f'http://127.0.0.1:{port}/mcp'
            environment = {key: value for key, value in os.environ.items()
                if not key.upper().startswith(('AXX_', 'AI_MEMORY_')) and
                not any(word in key.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))}
            environment.update(AI_MEMORY_AUTH_TOKEN=self.token, AI_MEMORY_EMBEDDING_PROVIDER='none')
            command = [str(self.executable), '--data-dir', str(self.data_dir), '--config', str(config),
                       'serve', '--transport', 'http', '--bind', f'127.0.0.1:{port}', '--no-watcher']
            try:
                with (self.data_dir / 'service.log').open('ab') as log:
                    # Inherits the Windows host Job Object; no BREAKAWAY flag.
                    self.process = subprocess.Popen(command, cwd=self.data_dir, env=environment,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic() + self._startup_timeout
                while time.monotonic() < deadline and self.process.poll() is None:
                    try:
                        initialized = self._request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                            'clientInfo': {'name': 'Axx', 'version': '0.20.1'}}, timeout=min(.5, max(.05, deadline - time.monotonic())))
                        server = initialized.get('serverInfo', {})
                        if server.get('name') != 'ai-memory' or server.get('version') != '3.1.1':
                            raise ValueError('Bundled memory identity/version does not match ai-memory 3.1.1')
                        self.server_version = server['version']
                        self.is_available, self.error = True, None
                        return True
                    except (OSError, ValueError, urllib.error.URLError):
                        time.sleep(.1)
                raise RuntimeError('Owned ai-memory did not confirm authenticated readiness within its startup budget')
            except Exception as error:
                self.error = str(error)[:300]
                self.close()
                LOG.warning('ai-memory unavailable; SQLite remains active: %s', self.error)
                return False

    def status(self) -> dict:
        running = bool(self.is_available and self.process and self.process.poll() is None)
        return {'backend': 'ai-memory' if running else 'sqlite', 'available': running, 'fallback': not running,
                'version': self.server_version if running else None, 'embedding_provider': 'none',
                'scope': {'workspace': self.workspace, 'project': self.project},
                'owned_pid': self.process.pid if running else None, 'error': self.error,
                'last_sync': self.last_sync}

    def _tool(self, name: str, arguments: dict) -> dict:
        if not self.is_available:
            raise RuntimeError('ai-memory unavailable; SQLite fallback is active')
        result = self._request('tools/call', {'name': name, 'arguments': {
            'workspace': self.workspace, 'project': self.project, **arguments}})
        blocks = result.get('content')
        if not isinstance(blocks, list):
            raise ValueError('Memory tool returned no content blocks')
        payloads = [json.loads(block['text']) for block in blocks if isinstance(block, dict) and block.get('type') == 'text' and isinstance(block.get('text'), str)]
        if len(payloads) != 1 or not isinstance(payloads[0], dict):
            raise ValueError('Memory tool returned an invalid JSON payload')
        return payloads[0]

    @staticmethod
    def _recipe_path(recipe_id: str) -> str:
        if not isinstance(recipe_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', recipe_id) or recipe_id in ('.', '..'):
            raise ValueError('Invalid memory recipe identifier')
        return 'recipes/' + recipe_id + '.md'

    def write_recipe_page(self, recipe_id: str, body: str) -> bool:
        try:
            path = self._recipe_path(recipe_id)
            result = self._tool('memory_write_page', {'path': path, 'body': body})
            if result.get('path') != path or not isinstance(result.get('page_id'), str):
                raise ValueError('Memory write returned no matching page confirmation')
            readback = self.read_recipe_page(recipe_id)
            if not readback or readback['body'].rstrip() != body.rstrip():
                raise ValueError('Memory write failed exact readback verification')
            self.last_sync = {'recipe_id': recipe_id, 'page_id': result['page_id'], 'verified_readback': True}
            self.error = None
            return True
        except Exception as error:
            self.error = str(error)[:300]
            LOG.warning('Procedure remains in SQLite; ai-memory page was not confirmed: %s', self.error)
            return False

    def query_recipes(self, query: str) -> list[dict]:
        try:
            if not isinstance(query, str) or not 1 <= len(query) <= 4000:
                raise ValueError('Invalid memory query')
            payload = self._tool('memory_query', {'query': query})
            hits = payload.get('hits')
            if not isinstance(hits, list):
                raise ValueError('Memory query returned no hits list')
            return [hit for hit in hits[:100] if isinstance(hit, dict)]
        except Exception as error:
            self.error = str(error)[:300]
            return []

    def read_recipe_page(self, recipe_id: str) -> dict | None:
        try:
            path = self._recipe_path(recipe_id)
            payload = self._tool('memory_read_page', {'path': path})
            if payload.get('path') != path or not isinstance(payload.get('body'), str):
                raise ValueError('Memory read returned an invalid page')
            return payload
        except Exception as error:
            self.error = str(error)[:300]
            return None

    def close(self):
        with self._lifecycle_lock:
            self.is_available = False
            process, self.process = self.process, None
            if process is not None and process.poll() is None:
                # Console-free Windows has no portable graceful signal. Stop
                # only our child, wait boundedly; committed WAL/wiki survives.
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            self.token = self.endpoint = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
