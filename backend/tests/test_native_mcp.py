import threading
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
import urllib.request
import urllib.error
from unittest.mock import patch
from backend.actions.tools import ToolResult
from backend.mcp_host.native_bridge import NativeMcpBridge, NATIVE_TOOLS
from backend.mcp_host.client_manager import Transport
from backend.mcp_host.native_gateway import GatewayUnavailable


class NativeMcpTests(unittest.TestCase):
    def test_offline_gateway_is_failure_not_user_cancellation(self):
        bridge=NativeMcpBridge();cancelled=threading.Event();calls=[]
        try:
            with patch.object(bridge,'_start',side_effect=GatewayUnavailable('Pasarela no disponible')):
                result=bridge.execute('desktop_list_windows',lambda:calls.append(1),cancelled,'offline')
            self.assertFalse(result.success);self.assertFalse(result.evidence['cancelled'])
            self.assertFalse(result.evidence['effect_uncertain']);self.assertFalse(result.evidence['native_started'])
            self.assertEqual(result.error,'Pasarela no disponible');self.assertEqual(calls,[])
            self.assertTrue(cancelled.is_set())
            from backend.actions.executor import ActionExecutor
            with tempfile.TemporaryDirectory() as folder, ActionExecutor(Path(folder)/'state.db',folder) as executor:
                executor.native_bridge=bridge
                executor.dynamic_tools['desktop_list_windows']=SimpleNamespace(parameter_names=set(),
                    verify_preconditions=lambda _: (True,''),verify_postconditions=lambda _,r:(r.success,''))
                with patch.object(bridge,'_start',side_effect=GatewayUnavailable('Pasarela no disponible')):
                    receipt=executor.execute_action('desktop_list_windows',{},'offline-ledger')
                self.assertEqual(receipt['state'],'failed');self.assertEqual(receipt['dispatch_status'],'rejected')
                self.assertEqual(executor.get_operation('offline-ledger')['state'],'failed')
        finally:bridge.close()

    def test_browser_workflows_use_the_same_admitted_native_route(self):
        self.assertTrue({'application_browse','application_hover','application_youtube'} <= NATIVE_TOOLS)
        for timeout in (True,0,91,'90'):
            with self.assertRaises(ValueError):Transport({},call_timeout=timeout)

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
