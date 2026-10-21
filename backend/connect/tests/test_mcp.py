"""Real official SDK stdio subprocess contract; no Axx connection is mocked."""
import asyncio
from pathlib import Path
import sys
import unittest
from backend.connect.registry import read_only_aliases


class MCPProcessTests(unittest.TestCase):
    def test_real_stdio_discovery_and_invalid_input(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest('Install requirements-axx-connect.txt for real SDK subprocess test')

        async def scenario():
            params = StdioServerParameters(command=sys.executable, args=['-m', 'backend.connect.mcp_server'], cwd=str(Path(__file__).resolve().parents[3]))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    result = await session.initialize()
                    self.assertEqual(result.serverInfo.name, 'axx-connect')
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {'axx_status', 'axx_list_capabilities', 'axx_execute_action', 'axx_get_task', 'axx_cancel_task', *read_only_aliases()})
                    metadata = {tool.name: tool for tool in tools.tools}
                    for name in read_only_aliases():
                        self.assertTrue(metadata[name].annotations.readOnlyHint)
                        self.assertFalse(metadata[name].annotations.destructiveHint)
                    rejected = await session.call_tool('axx_execute_action', {'command_id': 'axx.system.telemetry', 'inputs': {}, 'operation_id': 'mcp-invalid', 'approved': True})
                    self.assertTrue(rejected.isError)
                    bad_alias = await session.call_tool('axx_process_inspect', {'operation_id': 'alias-bad', 'pid': True})
                    self.assertTrue(bad_alias.isError)
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
