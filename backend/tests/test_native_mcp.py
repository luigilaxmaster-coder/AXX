import threading
import unittest
import urllib.request
import urllib.error
from backend.actions.tools import ToolResult
from backend.mcp_host.native_bridge import NativeMcpBridge


class NativeMcpTests(unittest.TestCase):
    def test_real_http_transport_and_single_use_admission(self):
        bridge = NativeMcpBridge()
        calls = []
        def primitive():
            calls.append(1)
            # A gateway retry while a native call runs must not execute it twice.
            with self.assertRaises(ValueError): bridge._redeem(bridge.active['ticket'])
            return ToolResult(True, output={'observed': 42}, evidence={'verification': 'test_body'})
        try:
            with self.assertRaises(ValueError): bridge._redeem('unadmitted')
            result = bridge.execute('desktop_list_windows', primitive, threading.Event(), 'native-http')
            self.assertTrue(result.success, result.error)
            self.assertEqual(result.output, {'observed': 42})
            self.assertEqual(result.evidence['transport'], 'mcp_streamable_http')
            self.assertEqual(calls, [1])
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(f'http://127.0.0.1:{bridge.port}/mcp', timeout=5)
            self.assertEqual(rejected.exception.code, 401)
            with self.assertRaises(ValueError): bridge._redeem('expired')
            cancelled = threading.Event(); cancelled.set()
            result = bridge.execute('desktop_list_windows', primitive, cancelled, 'cancelled')
            self.assertFalse(result.success)
            self.assertEqual(calls, [1])
        finally: bridge.close()


if __name__ == '__main__': unittest.main()
