"""Real private HTTP/DPAPI/executor; controlled hung model process boundary."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.connect.http_api import publish_endpoint, remove_endpoint
from backend.connect.mcp_server import LocalAxxClient
from backend.connect.service import ConnectService
from backend.connect.tests.test_provider import ControlledProvider
from backend.memory.procedural_memory import ProceduralMemory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class HttpIsolationTests(unittest.TestCase):
    def test_local_disconnect_over_http_overrides_cached_engine_and_preserves_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = ActionExecutor(root / 'state.db', workspace_root=root / 'artifacts')
            commands = CommandService(executor)
            memory = ProceduralMemory(root / 'state.db')
            service = ConnectService(commands, memory)
            provider = ControlledProvider(commands, root / 'state.db', root)
            handler = type('TestConnectHandler', (AxxBridgeHandler,), {'connect':service,'provider':provider,'commands':commands})
            server = ThreadedHTTPServer(('127.0.0.1',0),handler)
            worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            publish_endpoint(root,server)
            try:
                client = LocalAxxClient(root)
                descriptor = client._descriptor()
                result = client._request(descriptor,'POST','/axx-api/connect/disconnect',{})
                self.assertFalse(result['local_connection_enabled'])
                self.assertFalse(result['managed_credentials_revoked_by_axx'])
                # Even a stale in-flight health response cannot advertise a
                # connected model to subsequent MCP status while opted out.
                with server.connect_engine_lock:
                    server.connect_engine_status = {'state':'connected','authenticated':True,
                        'inference_verified':True,'checked_at':time.time()}
                for route in ('/axx-api/connect/status','/axx-api/connect/status?engine=1'):
                    status = client._request(descriptor,'GET',route)
                    self.assertEqual(status['executor'],'ready')
                    self.assertFalse(status['engine']['local_connection_enabled'])
                    self.assertFalse(status['engine']['authenticated'])
                    self.assertFalse(status['engine']['inference_verified'])
                alias = client._request(descriptor,'POST','/axx-api/connect/logout',{})
                self.assertFalse(alias['local_connection_enabled'])
                self.assertEqual(provider.rpc_calls,[])
                self.assertTrue(provider.authenticated)  # controlled shared account remains intact
                self.assertEqual(client.invoke('axx_status',{})['executor'],'ready')
            finally:
                server.shutdown(); server.server_close(); worker.join(2)
                remove_endpoint(root,server.instance_id)
                provider.close(); service.close(); commands.close(); memory.close(); executor.close()

    def test_hung_model_does_not_block_same_executor_or_mcp(self):
        gate = threading.Event()
        class HungProvider:
            def status(self):
                gate.wait(5)
                return {'state': 'unavailable', 'authenticated': False, 'inference_verified': False}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = ActionExecutor(root / 'state.db', workspace_root=root / 'artifacts')
            commands = CommandService(executor)
            memory = ProceduralMemory(root / 'state.db')
            service = ConnectService(commands, memory)
            handler = type('TestConnectHandler', (AxxBridgeHandler,), {'connect':service,'provider':HungProvider(),'commands':commands})
            server = ThreadedHTTPServer(('127.0.0.1',0),handler)
            worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            publish_endpoint(root,server)
            try:
                client = LocalAxxClient(root)
                before = time.monotonic()
                status = client.invoke('axx_status',{})
                self.assertLess(time.monotonic()-before,1)
                self.assertEqual(status['executor'],'ready')
                self.assertEqual(status['engine']['state'],'checking')
                self.assertEqual(status['instance_id'],server.instance_id)
                task = client.invoke('axx_system_telemetry',{'operation_id':'hung-model-telemetry'})
                deadline = time.monotonic()+3
                while task['state'] in ('prepared','running') and time.monotonic()<deadline:
                    time.sleep(.05)
                    task = client.invoke('axx_get_task',{'operation_id':task['operation_id']})
                self.assertEqual(task['state'],'succeeded')
                self.assertTrue(task['postconditions_passed'])
                self.assertFalse(gate.is_set())
            finally:
                gate.set(); server.shutdown(); server.server_close(); worker.join(2)
                remove_endpoint(root,server.instance_id)
                service.close(); commands.close(); memory.close(); executor.close()


if __name__ == '__main__':
    unittest.main()
