import tempfile
import unittest
import uuid
import json
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from backend.mobile.gateway import MobileGateway


class AvatarCustomizationTests(unittest.TestCase):
    def test_real_tls_route_requires_grant_and_receipts_are_device_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks={}
            def backend(method,path,body):
                if method=='POST':
                    tasks[body['operation_id']]={'state':'succeeded','postconditions_passed':True,
                        'output':{'settings':{'form':3,'palette':2},'finish':'prism'}}
                    return tasks[body['operation_id']]
                return tasks.get(path.split('operation_id=')[1])
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend,host_resolver=lambda:'127.0.0.1')
            try:
                info=gateway.start();context=ssl.create_default_context(cafile=str(gateway._identity[0]))
                def request(path,body=None,credential=None):
                    headers={'Content-Type':'application/json'}
                    if credential:headers['Authorization']='Bearer '+credential
                    req=urllib.request.Request(info['endpoint']+path,data=json.dumps(body).encode() if body else None,headers=headers)
                    with urllib.request.urlopen(req,context=context,timeout=3) as response:return json.load(response)
                device=request('/v1/pair/claim',{'code':info['pairing_code'],'device_name':'Phone'})
                operation=str(uuid.uuid4());body={'operation_id':operation,'device_id':device['device_id'],'inputs':{'action':'settings','palette':2}}
                with self.assertRaises(urllib.error.HTTPError) as denied:request('/v1/avatar/customize',body,device['credential'])
                self.assertEqual(denied.exception.code,403);self.assertFalse(tasks)
                gateway.store.set_input_permission(device['device_id'],True)
                self.assertTrue(request('/v1/avatar/customize',body,device['credential'])['data']['postconditions_passed'])
                self.assertEqual(request('/v1/avatar/operation?operation_id='+operation,credential=device['credential'])['data']['output']['palette'],2)
                other=gateway.store.consume_pairing(gateway.store.create_pairing(),'Other')
                with self.assertRaises(urllib.error.HTTPError) as denied:request('/v1/avatar/operation?operation_id='+operation,credential=other['credential'])
                self.assertEqual(denied.exception.code,404)
            finally:gateway.close()

    def test_permission_validation_stable_identity_and_private_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def backend(method,path,body):
                calls.append((method,path,body))
                return {'state':'succeeded','postconditions_passed':True,
                        'output':{'settings':{'palette':2,'form':8},'finish':'prism'},
                        'evidence':{'private':'must not cross the phone boundary'}}
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
            try:
                device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')['device_id']
                operation=str(uuid.uuid4());body={'operation_id':operation,'device_id':device,'inputs':{'action':'settings','palette':2}}
                with self.assertRaisesRegex(ValueError,'Aprueba'):
                    gateway.avatar_customize(device,body)
                self.assertEqual(calls,[])
                with self.assertRaisesRegex(ValueError,'enlace cambió'):
                    gateway.avatar_customize(device,{**body,'device_id':'other'})
                gateway.store.set_input_permission(device,True)
                receipt=gateway.avatar_customize(device,body)
                self.assertTrue(receipt['postconditions_passed'])
                self.assertEqual(receipt['operation_id'],operation)
                self.assertEqual(receipt['output'],{'palette':2,'form':8,'finish':'prism'})
                self.assertNotIn('evidence',receipt)
                first=calls[-1][2]
                self.assertEqual(first['command_id'],'axx.ui.identity')
                self.assertEqual(first['origin'],'mobile')
                gateway.avatar_customize(device,body)
                self.assertEqual(first['operation_id'],calls[-1][2]['operation_id'])
                self.assertNotEqual(first['operation_id'],gateway._avatar_operation_id('another-device',operation))
                self.assertEqual(gateway.avatar_operation(device,operation)['state'],'succeeded')
                self.assertIn(first['operation_id'],calls[-1][1])
                before=len(calls)
                for inputs in ({'action':'size','size':200},{'action':'settings','palette':9},
                               {'action':'settings','palette':True},{'action':'finish','finish':'invalid'},
                               {'action':'finish','finish':'prism','palette':2}):
                    with self.assertRaises(ValueError):
                        gateway.avatar_customize(device,{'operation_id':str(uuid.uuid4()),'device_id':device,'inputs':inputs})
                self.assertEqual(len(calls),before)
                gateway.store.set_input_permission(device,False)
                with self.assertRaises(ValueError):gateway.avatar_customize(device,body)
            finally:gateway.close()

    def test_missing_receipt_is_not_success_and_ids_are_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:None)
            try:
                self.assertIsNone(gateway.avatar_operation('phone',str(uuid.uuid4())))
                for value in ('not-an-id',None,{},str(uuid.uuid4()).upper()):
                    with self.assertRaises(ValueError):gateway.avatar_operation('phone',value)
            finally:gateway.close()
