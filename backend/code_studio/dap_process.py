"""Bounded stdio DAP transport for the installed debugpy adapter.

No attach, terminal requests or evaluation. Only an owner-approved file can be
launched; the existing process supervisor owns the adapter and its children.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree


class DapProcess:
    def __init__(self, python, root):
        self.condition, self.write_lock = threading.Condition(), threading.Lock()
        self.pending, self.events, self.seq, self.closed = {}, {}, 0, False
        self.kernel = None
        command = [python, '-I', '-m', 'debugpy.adapter']
        if os.name == 'nt':
            from backend.actions.process_runner import _spawn_owned, _locked_executable, ENV_NAMES
            env = {k:v for k,v in os.environ.items() if k.lower() in ENV_NAMES}
            with _locked_executable(python):
                self.proc, self.job, self.kernel, _ = _spawn_owned(command, str(root), env, threading.Event(),
                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        else:
            self.proc, self.job = spawn_managed_process(command, cwd=str(root),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = threading.Thread(target=self._read, name='axx-dap-stdio', daemon=True)
        self.reader.start()

    def _write(self, payload):
        raw = json.dumps(payload).encode('utf-8')
        with self.write_lock:
            self.proc.stdin.write(b'Content-Length: %d\r\n\r\n' % len(raw) + raw)
            self.proc.stdin.flush()

    def send(self, command, arguments):
        with self.condition:
            if self.closed or len(self.pending) >= 32:
                raise RuntimeError('DAP connection closed or busy')
            self.seq += 1
            seq = self.seq
            self.pending[seq] = None
        self._write({'seq': seq, 'type': 'request', 'command': command, 'arguments': arguments})
        return seq

    def response(self, seq, timeout=15):
        with self.condition:
            if not self.condition.wait_for(lambda: self.pending.get(seq) is not None or self.closed, timeout):
                self.pending.pop(seq, None)
                raise TimeoutError('DAP response deadline exceeded')
            result = self.pending.pop(seq, None)
        if result is None or result.get('success') is not True:
            raise RuntimeError((result or {}).get('message', 'DAP process disconnected')[:300])
        return result.get('body') or {}

    def request(self, command, arguments, timeout=15):
        return self.response(self.send(command, arguments), timeout)

    def event(self, names, timeout=15):
        with self.condition:
            if not self.condition.wait_for(lambda: self.closed or any(self.events.get(n) for n in names), timeout):
                return None
            for name in names:
                if self.events.get(name):
                    return {'event': name, 'body': self.events[name].pop(0)}
        return None

    def _read(self):
        try:
            while not self.closed:
                length, headers = None, 0
                while True:
                    line = self.proc.stdout.readline(4097)
                    headers += len(line)
                    if not line or len(line) > 4096 or headers > 16384:
                        return
                    if line in (b'\r\n', b'\n'):
                        break
                    if line.lower().startswith(b'content-length:'):
                        length = int(line.split(b':', 1)[1])
                if length is None or not 0 < length <= 1024 * 1024:
                    return
                message = json.loads(self.proc.stdout.read(length))
                with self.condition:
                    if message.get('type') == 'response' and message.get('request_seq') in self.pending:
                        self.pending[message['request_seq']] = message
                    elif message.get('type') == 'event':
                        name = message.get('event')
                        if name in ('initialized', 'stopped', 'terminated', 'exited'):
                            queue = self.events.setdefault(name, [])
                            queue.append(message.get('body') or {})
                            del queue[:-8]
                    elif message.get('type') == 'request':
                        # The adapter cannot request an unsupervised terminal or run a shell.
                        self._write({'seq': 0, 'type': 'response', 'request_seq': message['seq'],
                                     'command': message.get('command'), 'success': False, 'message': 'Not supported by AXX'})
                    self.condition.notify_all()
        except (OSError, ValueError, TypeError):
            pass
        finally:
            with self.condition:
                self.closed = True
                self.condition.notify_all()

    def close(self):
        if not self.closed:
            try:
                self.request('disconnect', {'terminateDebuggee': True}, timeout=3)
                self.event(['terminated', 'exited'], timeout=3)
            except (OSError, TimeoutError, RuntimeError):
                pass
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.kernel is not None:
            from backend.actions.process_runner import _stop_owned
            _stop_owned(self.kernel, self.proc, self.job)
        else:
            terminate_process_tree(self.proc, self.job)
        self.proc.wait(timeout=3)
        self.reader.join(timeout=2)
        for pipe in (self.proc.stdin, self.proc.stdout):
            if pipe is not None:
                pipe.close()
