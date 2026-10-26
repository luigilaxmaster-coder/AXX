import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.mcp_host.catalog import checked_schema
from backend.mcp_host.client_manager import McpHost, checked_config


class McpHostTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'DPAPI persistence requires Windows')
    def test_slow_probe_does_not_block_list_or_disconnect_or_resurrect_connection(self):
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(max_workers=2) as pool:
            host = McpHost(folder, Mock())
            key = host.add({'name':'slow','context':'fixture','transport':'streamable_http','url':'https://example.com/mcp'})['id']
            started, release = threading.Event(), threading.Event()
            transport = Mock()
            def initialize(config):
                started.set()
                if not release.wait(5): raise TimeoutError('fixture deadline')
                return transport
            with patch('backend.mcp_host.client_manager.Transport', side_effect=initialize):
                pending = pool.submit(host.probe, key)
                try:
                    self.assertTrue(started.wait(2))
                    self.assertEqual(pool.submit(host.list).result(timeout=1)['connections'][0]['status'], 'connecting')
                    self.assertEqual(pool.submit(host.disconnect,key).result(timeout=1)['status'], 'disconnected')
                finally: release.set()
                with self.assertRaises(ValueError): pending.result(timeout=2)
            self.assertEqual(host.list()['connections'][0]['status'], 'disconnected')
            transport.close.assert_called_once()

    def test_config_and_schema_trust_boundaries(self):
        for url in ('http://example.com/mcp', 'https://u:secret@example.com/mcp', 'file:///c:/x', 'http://localhost:4000/mcp'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checked_config({'name':'Test', 'context':'Fixture', 'transport':'streamable_http', 'url':url})
        with self.assertRaises(ValueError): checked_schema({'type':'object', '$ref':'https://example.com/schema'})
        with self.assertRaises(ValueError): checked_schema({'$defs': {'loop':{'$ref':'#'}}})
        with self.assertRaises(ValueError): checked_schema({'type':'string', 'pattern':'(a+)+$'})

    @unittest.skipUnless(os.name == 'nt', 'DPAPI persistence requires Windows')
    def test_corrupt_storage_is_preserved_without_breaking_the_host(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'mcp-connections.dpapi'
            path.write_bytes(b'invalid protected store')
            host = McpHost(folder, Mock())
            self.assertTrue(host.list()['storage_error'])
            with self.assertRaises(ValueError): host.add({'name':'test', 'context':'test', 'transport':'streamable_http', 'url':'https://example.com/mcp'})
            self.assertEqual(path.read_bytes(), b'invalid protected store')

    @unittest.skipUnless(os.name == 'nt', 'DPAPI persistence requires Windows')
    def test_pagination_and_rejected_tool_do_not_disable_compatible_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            host = McpHost(folder, Mock())
            key = host.add({'name':'test', 'context':'test', 'transport':'streamable_http', 'url':'https://example.com/mcp'})['id']
            transport = Mock()
            transport.request.side_effect = [
                {'tools':[{'name':'valid','inputSchema':{'type':'object','properties':{}}}], 'nextCursor':'page2'},
                {'tools':[{'name':'unsupported','inputSchema':{'type':'object','properties':{'value':{'$ref':'#/$defs/value'}}}}]}]
            self.assertEqual([row['name'] for row in host._discover(key, transport)], ['valid'])
            self.assertEqual(transport.rejected_tools[0]['name'], 'unsupported')
            transport.request.side_effect = None
            transport.request.return_value = {'tools':[], 'nextCursor':'same-page'}
            with self.assertRaises(ValueError): host._discover(key, transport)

    @unittest.skipUnless(os.name == 'nt', 'DPAPI persistence requires Windows')
    def test_real_stdio_dynamic_catalog_execution_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executor = ActionExecutor(root/'state.db', root)
            commands = CommandService(executor)
            host = McpHost(root, commands)
            try:
                connection = host.add({'name':'Fixture', 'context':'test-account', 'transport':'stdio',
                    'command':sys.executable, 'args':['-m','backend.tests.mcp_fixture_server'],
                    'cwd':str(Path(__file__).resolve().parents[2]), 'env':{'AXX_TEST_MCP_FILE':str(root/'effects.txt')}})
                key = connection['id']
                self.assertEqual(host.probe(key)['tools'], 2)
                rows = host.list()['connections'][0]['tools']
                add = next(row for row in rows if row['name'] == 'add_numbers')
                write = next(row for row in rows if row['name'] == 'append_marker')
                self.assertFalse(commands.details(add['id'])['command']['execution_enabled'])
                host.activate(add['id'], True, True)
                self.assertTrue(commands.search(add['id'])['commands'][0]['execution_enabled'])
                with self.assertRaises(ValueError): commands.prepare(add['id'], {'left':'wrong', 'right':2})
                request = commands.prepare(add['id'], {'left':20,'right':22}, operation_id='external-read')
                result = commands.execute(request['operation_id'], approved=True)
                self.assertEqual(result['state'], 'succeeded', result)
                self.assertEqual(json.loads(result['output']['result']['content'][0]['text'])['sum'], 42)
                host.activate(write['id'], True, False)
                request = commands.prepare(write['id'], {'text':'one'}, operation_id='external-write')
                result = commands.execute(request['operation_id'], approved=True)
                self.assertEqual(result['state'], 'unknown', result)
                replay = commands.execute(request['operation_id'], approved=True)
                self.assertEqual(replay['state'], 'unknown')
                self.assertEqual((root/'effects.txt').read_text(), 'one\n')
                host.disconnect(key)
                self.assertFalse(commands.search(add['id'])['commands'][0]['execution_enabled'])
                with self.assertRaises(ValueError): commands.prepare(add['id'], {'left':1,'right':2})
                self.assertNotIn(b'test-account', (root/'mcp-connections.dpapi').read_bytes())
            finally:
                host.close(); commands.close(); executor.close()


if __name__ == '__main__': unittest.main()
