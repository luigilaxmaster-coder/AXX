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
    def test_work_revoked_during_preparation_is_cancelled_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def backend(method,path,body):
                calls.append(path)
                if path.endswith('/executable'):
                    return {'commands':[{'id':'axx.system.telemetry','pc_approval_required':False}]}
                if path.endswith('/prepare'):
                    gateway.store.set_tool_permission(device['device_id'],False)
                    return {**body,'state':'prepared'}
                if path.endswith('/cancel'):return {'state':'cancelled'}
                raise AssertionError('Unexpected execution: '+path)
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
            try:
                device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
                gateway.store.set_tool_permission(device['device_id'],True)
                with self.assertRaisesRegex(ValueError,'revocado'):
                    gateway.work_execute(device['device_id'],{'command_id':'axx.system.telemetry','inputs':{},
                        'operation_id':str(uuid.uuid4()),'approved':False})
                self.assertEqual(calls,['/axx-api/commands/executable','/axx-api/commands/prepare','/axx-api/commands/cancel'])
            finally:gateway.close()

    def test_tls_rescan_preserves_grants_and_snapshot_reflects_pc_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:{},pc_name='Mi PC',host_resolver=lambda:'127.0.0.1')
            try:
                first=gateway.start()
                context=ssl.create_default_context(cafile=str(gateway._identity[0]))
                def request(path, body=None, token=None):
                    headers={'Content-Type':'application/json'}
                    if token:headers['Authorization']='Bearer '+token
                    req=urllib.request.Request(first['endpoint']+path,data=json.dumps(body).encode() if body else None,headers=headers)
                    with urllib.request.urlopen(req,context=context,timeout=3) as response:return json.load(response)
                device=request('/v1/pair/claim',{'code':first['pairing_code'],'device_name':'Phone'})
                gateway.store.set_tool_permission(device['device_id'],True)
                second=gateway.start()
                renewed=request('/v1/pair/claim',{'code':second['pairing_code'],'device_name':'Phone'},device['credential'])
                self.assertEqual(renewed['device_id'],device['device_id'])
                self.assertIn('tools.control',renewed['scopes'])
                self.assertEqual(len(gateway.store.devices()),1)
                gateway.appearance={'finish':'prism'}
                gateway.preferences={'provider':'bridge','provider_name':'configured','model':'chosen','selection_mode':'manual'}
                snapshot=request('/v1/snapshot',token=device['credential'])['data']
                self.assertEqual(snapshot['pc_name'],'Mi PC')
                self.assertEqual(snapshot['appearance'],gateway.appearance)
                self.assertEqual(snapshot['inference']['model'],'chosen')
                gateway.share_history=True
                gateway.shared.merge_messages([{'id':'private','role':'user','text':'Historial privado'}],'desktop','shared',activate=True)
                self.assertEqual(len(request('/v1/snapshot',token=device['credential'])['data']['messages']),1)
                gateway.share_history=False
                self.assertEqual(request('/v1/snapshot',token=device['credential'])['data']['messages'],[])
                with self.assertRaises(ValueError):
                    gateway.admit_chat(device['device_id'],{'operation':'chat','text':'hola','conversation_id':'shared','command_id':'blocked-history'})
                gateway.store.set_tool_permission(device['device_id'],False)
                self.assertNotIn('tools.control',request('/v1/snapshot',token=device['credential'])['data']['scopes'])
                gateway.revoke(device['device_id'])
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    request('/v1/snapshot',token=device['credential'])
                self.assertEqual(rejected.exception.code,403);rejected.exception.close()
            finally:gateway.close()

    def test_always_access_restarts_on_same_port_and_keeps_device_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.db'
            first=MobileGateway(path,tmp,lambda *args:{},host_resolver=lambda:'127.0.0.1')
            try:
                info=first.start()
                device=first.store.consume_pairing(info['pairing_code'],'Phone')
                first.store.set_input_permission(device['device_id'],True)
                first.set_always_access(True)
                port=first.httpd.server_port
                first._claimed=True
                first._last_contact=0
                first.expire_idle(first.httpd)
                self.assertTrue(first.status()['enabled'])
            finally:first.close()
            restarted=MobileGateway(path,tmp,lambda *args:{},host_resolver=lambda:'127.0.0.1')
            try:
                restarted.resume()
                self.assertTrue(restarted.status()['enabled'])
                self.assertEqual(restarted.httpd.server_port,port)
                self.assertTrue(restarted.store.authorize(device['credential'],'input.control'))
                restarted.set_always_access(False)
                self.assertFalse(restarted.status()['enabled'])
                self.assertFalse(restarted.store.access_settings()['always_on'])
            finally:restarted.close()

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

    def test_work_requires_pc_grant_and_runs_only_supported_command(self):
        calls=[]
        def backend(method,path,body):
            if path.endswith('/executable'):
                return {'commands':[
                    {'id':'axx.system.telemetry', 'pc_approval_required':False},
                    {'id':'axx.shell.powershell', 'pc_approval_required':True},
                    {'id':'axx.generated.test', 'pc_approval_required':False}]}
            calls.append(path)
            if path.endswith('/prepare'):
                return {'state':'awaiting_approval','operation_id':body['operation_id'],
                        'command_id':body['command_id'],'inputs':body['inputs']}
            if path.endswith('/execute'):
                return {'state':'succeeded','postconditions_passed':True,'output':{'os':'Windows'}}
            if path.endswith('/cancel'):
                return {'state':'cancelled'}
            return {'operation':{'state':'awaiting_approval','command_id':'axx.shell.powershell',
                                 'inputs':{'script':'Get-Date'}}}
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend,host_resolver=lambda:'127.0.0.1')
            info=gateway.start();device=gateway.store.consume_pairing(info['pairing_code'],'Phone')
            context=ssl.create_default_context(cafile=str(gateway._identity[0]))
            command={'command_id':'axx.system.telemetry','inputs':{},'operation_id':str(uuid.uuid4()),'approved':False}
            def post(body):
                req=urllib.request.Request(info['endpoint']+'/v1/work/execute',data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+device['credential']})
                with urllib.request.urlopen(req,context=context,timeout=3) as response:return json.load(response)
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    post(command)
                self.assertEqual(denied.exception.code,403);denied.exception.close()
                self.assertEqual(calls,[])
                gateway.store.set_tool_permission(device['device_id'],True)
                self.assertEqual(post(command)['data']['state'],'succeeded')
                self.assertEqual(calls,['/axx-api/commands/prepare','/axx-api/commands/execute'])
                shell={**command,'command_id':'axx.shell.powershell','inputs':{'script':'Get-Date'},
                       'operation_id':str(uuid.uuid4())}
                self.assertEqual(post(shell)['data']['state'],'awaiting_pc_approval')
                self.assertEqual(calls.count('/axx-api/commands/execute'),1)
                self.assertEqual(gateway.pending_work()['operations'][0]['inputs'],{'script':'Get-Date'})
                self.assertEqual(gateway.approve_work({'operation_id':shell['operation_id'],'approved':True})['state'],'succeeded')
                self.assertEqual(calls.count('/axx-api/commands/execute'),2)
                dynamic={**command,'command_id':'axx.generated.test','operation_id':str(uuid.uuid4())}
                self.assertEqual(post(dynamic)['data']['state'],'succeeded')
            finally:gateway.close()

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
                with self.assertRaises(urllib.error.HTTPError) as no_avatar:
                    request('/v1/avatar/gesture',{'kind':'rotate','dx':5,'dy':3},device['credential'])
                self.assertEqual(no_avatar.exception.code,403);no_avatar.exception.close()
                gateway.store.set_input_permission(device['device_id'],True)
                gesture=request('/v1/avatar/gesture',{'kind':'rotate','dx':5,'dy':3},device['credential'])['data']
                self.assertEqual(gateway.avatar_events(0)['events'][0]['sequence'],gesture['sequence'])
                state=request('/v1/control/acquire',acquire,device['credential'])['data']
                packet={'lease_id':state['lease']['lease_id'],'boot_id':state['boot_id'],'seq':1,'events':[{'type':'move','x':4,'y':3}]}
                request('/v1/control/events',packet,device['credential']);request('/v1/control/events',packet,device['credential'])
                self.assertEqual(len(gateway.control.native.sent),1)
                gateway.revoke(device['device_id'])
                self.assertFalse(gateway.control.native.active)
                self.assertEqual(gateway.avatar_events(0)['events'],[])
                with self.assertRaises(urllib.error.HTTPError) as revoked:
                    request('/v1/catalog', token=device['credential'])
                revoked.exception.close()
            finally:
                gateway.stop()
            self.assertFalse(gateway.status()['enabled'])

    def test_chat_retry_has_one_backend_call_and_shared_messages(self):
        calls=[]
        def backend(method, path, body):
            if path.endswith('/resolve'):
                return {'match':'none'}
            calls.append(body['request_id'])
            return {'request_id':body['request_id'], 'choices':[{'message':{'content':'Respuesta'}}]}
        with tempfile.TemporaryDirectory() as tmp:
            gateway=MobileGateway(Path(tmp)/'state.db', tmp, backend)
            gateway.preferences={'provider':'bridge','provider_name':'unit-test','model':'test-model'}
            device=gateway.store.consume_pairing(gateway.store.create_pairing(), 'Phone')
            body={'operation':'chat','command_id':'cmd-1','text':'Hola','conversation_id':'test'}
            gateway.share_history=True
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

    def test_mobile_commands_respect_scope_mode_and_actual_receipt(self):
        for permission, state, verified in ((False,'prepared',True),(True,'awaiting_approval',True),
                                             (True,'prepared',True),(True,'prepared',False)):
            with self.subTest(permission=permission,state=state,verified=verified), tempfile.TemporaryDirectory() as tmp:
                calls=[]
                def backend(method,path,body):
                    calls.append((method,path,body))
                    if path.endswith('/resolve'): return {'match':'exact','command_id':'axx.system.telemetry','inputs':{}}
                    if '?shared_id=' in path: return {'id':'desktop-thread','mode':'ask' if state=='awaiting_approval' else 'auto_safe'}
                    if path.endswith('/prepare'):
                        self.assertEqual(body['conversation_id'],'desktop-thread')
                        return {**body,'state':state}
                    if path.endswith('/execute'):
                        self.assertIs(body['approved'],False)
                        return {'state':'succeeded' if verified else 'unknown','postconditions_passed':verified,'output':{'cpu_percent':12.5}}
                    raise AssertionError(path)
                gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
                device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
                if permission: gateway.store.set_tool_permission(device['device_id'],True)
                body={'operation':'chat','command_id':'pc-command','text':'mis aplicaciones','conversation_id':'mobile-thread'}
                gateway.share_history=True
                gateway.admit_chat(device['device_id'],body)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    task=gateway.store.command(device['device_id'],'pc-command')
                    if task['state']=='completed':break
                    time.sleep(.01)
                self.assertEqual(task['state'],'completed',task)
                self.assertEqual(sum(path.endswith('/execute') for _,path,_ in calls),int(permission and state=='prepared'))
                if not permission: self.assertEqual([path for _,path,_ in calls],['/axx-api/commands/resolve'])
                answer=gateway.shared.snapshot('mobile-thread')['messages'][-1]['text']
                self.assertEqual('Ejecutado y verificado' in answer,permission and state=='prepared' and verified)
                count=len(calls);gateway.admit_chat(device['device_id'],body)
                self.assertEqual(len(calls),count)

    def test_mobile_cli_does_not_guess_or_autoapprove(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[];gateway=MobileGateway(Path(tmp)/'state.db',tmp,lambda *args:calls.append(args))
            device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
            gateway.store.set_tool_permission(device['device_id'],True)
            answer=gateway._execute_pc_command(device['device_id'],'/cli notepad type','shared','task')
            self.assertIn('no ejecuta',answer);self.assertEqual(calls,[])

    def test_conversational_imperatives_use_chat_without_work_permission(self):
        for message in ('escribe un poema', 'haz un resumen', 'crea un cuento'):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                calls=[]
                def backend(method,path,body):
                    calls.append(path)
                    if path.endswith('/resolve'): return {'match':'none'}
                    if path == '/axx-api/chat': return {'choices':[{'message':{'content':'Respuesta conversacional'}}]}
                    raise AssertionError(path)
                gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
                gateway.preferences={'provider':'bridge','provider_name':'unit-test','model':'test-model'}
                device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
                gateway.share_history=True
                gateway.admit_chat(device['device_id'],{'operation':'chat','command_id':'chat-imperative',
                    'text':message,'conversation_id':'mobile-thread'})
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    task=gateway.store.command(device['device_id'],'chat-imperative')
                    if task['state'] not in ('admitted','running'): break
                    time.sleep(.01)
                self.assertEqual(task['state'],'completed',task)
                self.assertEqual(calls,['/axx-api/commands/resolve','/axx-api/chat'])
                self.assertEqual(gateway.shared.snapshot('mobile-thread')['messages'][-1]['text'],'Respuesta conversacional')

    def test_unknown_explicit_command_does_not_fall_back_to_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def backend(method,path,body):
                calls.append(path)
                return {'match':'none'}
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
            device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
            result=gateway._execute_pc_command(device['device_id'],'/comando desconocido {}','shared','task')
            self.assertIn('No hay un comando exacto',result)
            self.assertEqual(calls,['/axx-api/commands/resolve'])

    def test_conversational_fallback_still_requires_configured_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def backend(method,path,body):
                calls.append(path)
                return {'match':'none'}
            gateway=MobileGateway(Path(tmp)/'state.db',tmp,backend)
            device=gateway.store.consume_pairing(gateway.store.create_pairing(),'Phone')
            gateway.share_history=True
            gateway.admit_chat(device['device_id'],{'operation':'chat','command_id':'no-engine',
                'text':'escribe un poema','conversation_id':'mobile-thread'})
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                task=gateway.store.command(device['device_id'],'no-engine')
                if task['state'] not in ('admitted','running'): break
                time.sleep(.01)
            self.assertEqual(task['state'],'failed',task)
            self.assertEqual(task['result']['error']['code'],'ENGINE_NOT_AVAILABLE')
            self.assertEqual(calls,['/axx-api/commands/resolve'])

if __name__ == '__main__': unittest.main()
