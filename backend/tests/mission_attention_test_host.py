"""Private stdio-controlled loopback fixture; never starts the installed server."""
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import sys
import threading
import time

from backend.anticipation import AnticipationService
from backend.chat_store import ChatStore
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.tests.test_mission_attention import MissionAttentionTests, NoModel


class CountingNoModel(NoModel):
    calls = 0

    def route(self, request):
        self.calls += 1
        return super().route(request)


def main():
    fixture = MissionAttentionTests()
    fixture.setUp()
    chats = server = None
    try:
        chats = ChatStore(fixture.root / 'state.db')
        chat = chats.mutate('create', {'connect_id': 'test-context-' + secrets.token_hex(16)})
        fixture.learning.adapter = CountingNoModel()
        fixture.service.configure({'profiles': {'copiloto': {'interruptions': 'cards_voice'}}})
        plan = fixture.mission(chat['id'])
        initial = fixture.executor.list_operations(100)
        assert len(initial) == 3
        ledger_hash = lambda: hashlib.sha256(json.dumps(fixture.executor.list_operations(100),
            sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        original_ledger = ledger_hash()
        artifacts = [{'path': str(fixture.executor.workspace_root / f"mission-1-{i}.txt"),
            'sha256': hashlib.sha256((fixture.executor.workspace_root / f"mission-1-{i}.txt").read_bytes()).hexdigest()}
            for i in range(3)]
        requests = []

        class Handler(AxxBridgeHandler):
            executor, commands = fixture.executor, fixture.commands
            learning = fixture.learning
            anticipation = fixture.service

            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path.split('?', 1)[0] not in ('/axx-api/anticipation/status', '/axx-api/learning/plans'):
                    self._send_json(500, {'error': {'message': 'Unexpected fixture GET'}})
                    return
                requests.append({'method': 'GET', 'path': self.path.split('?', 1)[0]})
                super().do_GET()

            def do_POST(self):
                if self.path not in ('/axx-api/anticipation/status', '/axx-api/anticipation/feedback'):
                    self._send_json(500, {'error': {'message': 'Unexpected fixture POST'}})
                    return
                requests.append({'method': 'POST', 'path': self.path})
                super().do_POST()

        server = ThreadedHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def snapshot():
            status = fixture.service.status(chat['id'])
            return {'operation_count': len(fixture.executor.list_operations(100)),
                'ledger_unchanged': ledger_hash() == original_ledger,
                'artifact_hashes': [hashlib.sha256(Path(a['path']).read_bytes()).hexdigest() for a in artifacts],
                'model_calls': fixture.learning.adapter.calls,
                'model_ledger_rows': fixture.learning.db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0],
                'status': status, 'requests': list(requests)}

        def emit(value):
            print(json.dumps(value, ensure_ascii=True), flush=True)

        emit({'ready': True, 'pid': os.getpid(), 'url': f'http://127.0.0.1:{server.server_port}',
            'token': server.host_token, 'task_id': chat['id'], 'project_id': 'project-a',
            'memory_scope': chats.get(chat['id'])['memory_scope'],
            'memory_context_id': chats.get(chat['id'])['context_id'], 'artifacts': artifacts,
            'mission_id': plan['operation_id']})
        incoming = queue.Queue()
        def read_commands():
            for line in sys.stdin:
                if len(line) > 4096:
                    incoming.put({'action': 'invalid'})
                    break
                incoming.put(json.loads(line))
            incoming.put({'action': 'stop'})
        threading.Thread(target=read_commands, daemon=True).start()
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            command = incoming.get(timeout=max(.1, deadline - time.monotonic()))
            action = command.get('action')
            if action == 'stop':
                break
            if action == 'restart':
                fixture.service.close()
                fixture.service = AnticipationService(fixture.commands, clock=lambda: fixture.now)
                fixture.wire()
                Handler.anticipation = fixture.service
            elif action != 'snapshot':
                raise ValueError('Unknown fixture control')
            emit(snapshot())
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join(3)
        if chats:
            chats.close()
        fixture.tearDown()


if __name__ == '__main__':
    main()
