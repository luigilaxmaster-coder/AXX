"""Real local TLS envelope/schema checks, using isolated storage and declared identity data."""
import json
import ssl
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from backend.mobile.gateway import MobileGateway

ROOT=Path(__file__).resolve().parents[3]

class CompanionSchemaTests(unittest.TestCase):
    def test_v1_tls_snapshot_preserves_required_shape_and_mutation_permissions(self):
        contract=json.loads((ROOT/'mobile/companion-contract.json').read_text(encoding='utf-8'))
        fixture=json.loads((ROOT/'mobile/tests/fixtures/compatibility-v1.json').read_text(encoding='utf-8'))['customization']
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:calls.append(args),host_resolver=lambda:'127.0.0.1')
            try:
                info=gateway.start()
                context=ssl.create_default_context(cafile=str(gateway._identity[0]))
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
                def request(path,body=None,credential=None):
                    headers={'Content-Type':'application/json'}
                    if credential:headers['Authorization']='Bearer '+credential
                    req=urllib.request.Request(info['endpoint']+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
                    with opener.open(req,timeout=4) as response:return json.load(response)
                device=request('/v1/pair/claim',{'code':info['pairing_code'],'device_name':'Schema fixture'})
                cold=request('/v1/snapshot',credential=device['credential'])['data']
                self.assertIsNone(cold['appearance'])
                gateway.appearance=fixture['appearance']
                result=request('/v1/snapshot',credential=device['credential'])
                self.assertIs(result['ok'],True);data=result['data']
                self.assertTrue(set(contract['snapshot_required'])<=set(data))
                self.assertTrue(set(contract['appearance_required'])<=set(data['appearance']))
                self.assertIsInstance(data['conversation_id'],str);self.assertIsInstance(data['messages'],list)
                self.assertIsInstance(data['scopes'],list);self.assertTrue(data['inference'] is None or isinstance(data['inference'],dict))
                self.assertIsInstance(data['appearance']['settings'],dict);self.assertIsInstance(data['appearance']['studio'],dict)
                self.assertEqual(len(data['appearance']['camera']),2);self.assertIsInstance(data['appearance']['finish'],str)
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    request('/v1/avatar/customize',{'operation_id':'00000000-0000-4000-8000-000000000000','device_id':device['device_id'],'inputs':{'action':'settings','palette':2}},device['credential'])
                self.assertEqual(denied.exception.code,403);self.assertFalse(calls)
                with self.assertRaises(urllib.error.HTTPError) as wrong_method:request('/v1/snapshot',{},device['credential'])
                self.assertEqual(wrong_method.exception.code,404)
            finally:gateway.close()
