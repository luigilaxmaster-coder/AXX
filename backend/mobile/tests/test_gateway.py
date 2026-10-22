import json
import ssl
import tempfile
import unittest
import urllib.request
import time
import uuid
import http.client
from unittest.mock import patch
from pathlib import Path
from backend.mobile.gateway import MobileGateway


class GatewayTests(unittest.TestCase):
    def test_new_qr_has_full_scan_window_after_idle_or_prior_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:{},host_resolver=lambda:'127.0.0.1')
            try:
                with patch('backend.mobile.gateway.time.monotonic',return_value=1000):
                    first=gateway.start()
                server=gateway.httpd
                gateway._claimed=True
                with patch('backend.mobile.gateway.time.monotonic',return_value=1119):
                    second=gateway.start()
                    gateway.expire_idle(server)
                self.assertIs(gateway.httpd,server)
                self.assertNotEqual(first['pairing_code'],second['pairing_code'])
                with patch('backend.mobile.gateway.time.monotonic',return_value=1238):
                    gateway.expire_idle(server)
                self.assertIs(gateway.httpd,server)
                with patch('backend.mobile.gateway.time.monotonic',return_value=1240):
                    gateway.expire_idle(server)
                self.assertFalse(gateway.status()['enabled'])
            finally:gateway.close()

    def test_persistent_control_transport_rechecks_disabled_gateway(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:{},host_resolver=lambda:'127.0.0.1')
            info=gateway.start();device=gateway.store.consume_pairing(info['pairing_code'],'Phone')
            context=ssl.create_default_context(cafile=str(gateway._identity[0]))
            conn=http.client.HTTPSConnection('127.0.0.1',gateway.httpd.server_port,context=context,timeout=3)
            headers={'Authorization':'Bearer '+device['credential']}
            try:
                for _ in range(2):
                    conn.request('GET','/v1/control/status',headers=headers);response=conn.getresponse()
                    self.assertEqual(response.status,200);self.assertEqual(response.getheader('Connection'),'keep-alive');response.read()
                gateway.stop()
                conn.request('GET','/v1/control/status',headers=headers);response=conn.getresponse()
                self.assertEqual(response.status,403)
                self.assertEqual(json.loads(response.read())['error']['code'],'GATEWAY_DISABLED')
            finally:conn.close();gateway.stop()

    def test_tls_pair_query_revoke_and_stop(self):
        calls = []
        def backend(method, path, body):
            calls.append(path)
            return {'tools': [{'name': 'real-tool'}]}
        with tempfile.TemporaryDirectory() as tmp:
            gateway = MobileGateway(Path(tmp)/'state.db', tmp, backend, host_resolver=lambda: '127.0.0.1')
            self.assertFalse(gateway.status()['enabled'])
            try:
                info = gateway.start()
                context = ssl.create_default_context(cafile=str(gateway._identity[0]))
                def request(path, body=None, token=None):
                    headers = {'Content-Type': 'application/json'}
                    if token: headers['Authorization'] = 'Bearer ' + token
                    req = urllib.request.Request(info['endpoint'] + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
                    with urllib.request.urlopen(req, context=context, timeout=3) as response:
                        return json.load(response)
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request('/v1/catalog')
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                self.assertEqual(calls, [])
                device = request('/v1/pair/claim', {'code': info['pairing_code'], 'device_name': 'Test phone'})
                self.assertEqual(request('/v1/catalog', token=device['credential'])['data']['tools'][0]['name'], 'real-tool')
                from backend.mobile.tests.test_control import Native
                gateway.control.native=Native()
                acquire={'request_id':str(uuid.uuid4()),'visible':True}
                with self.assertRaises(urllib.error.HTTPError) as no_input:
                    request('/v1/control/acquire',acquire,device['credential'])
                self.assertEqual(no_input.exception.code,403);no_input.exception.close()
                gateway.store.set_input_permission(device['device_id'],True)
                state=request('/v1/control/acquire',acquire,device['credential'])['data']
                packet={'lease_id':state['lease']['lease_id'],'boot_id':state['boot_id'],'seq':1,'events':[{'type':'move','x':4,'y':3}]}
                request('/v1/control/events',packet,device['credential']);request('/v1/control/events',packet,device['credential'])
                self.assertEqual(len(gateway.control.native.sent),1)
                gateway.revoke(device['device_id'])
                self.assertFalse(gateway.control.native.active)
                with self.assertRaises(urllib.error.HTTPError) as revoked:
                    request('/v1/catalog', token=device['credential'])
                revoked.exception.close()
            finally:
                gateway.stop()
            self.assertFalse(gateway.status()['enabled'])

    def test_chat_retry_has_one_backend_call_and_shared_messages(self):
        calls=[]
        def backend(method, path, body):
            calls.append(body['request_id'])
            return {'request_id':body['request_id'], 'choices':[{'message':{'content':'Respuesta'}}]}
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db', tmp, backend)
            gateway.preferences={'provider':'bridge','provider_name':'unit-test','model':'test-model'}
            device=gateway.store.consume_pairing(gateway.store.create_pairing(), 'Phone')
            body={'operation':'chat','command_id':'cmd-1','text':'Hola','conversation_id':'test'}
            first=gateway.admit_chat(device['device_id'],body)
            retry=gateway.admit_chat(device['device_id'],body)
            self.assertEqual(first['task_id'], retry['task_id'])
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                task=gateway.store.command(device['device_id'],'cmd-1')
                if task['state']=='completed':break
                time.sleep(.01)
            self.assertEqual(task['state'],'completed')
            self.assertEqual(calls,[first['task_id']])
            self.assertEqual(len(gateway.shared.snapshot('test')['messages']),2)
