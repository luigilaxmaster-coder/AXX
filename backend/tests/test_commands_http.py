"""Actual authenticated loopback HTTP -> catalog -> executor, without external services."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import ssl
import uuid

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class CommandsHttpTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt', 'Compensation requires local NTFS handles')
    def test_compensation_http_preserves_approval_identity_and_reversible_bytes(self):
        status,prepared=self.request('commands/prepare',{'command_id':'axx.artifact.write',
            'operation_id':'http-source','inputs':{'path':'api-original.txt','content':'Synthetic reversible file'}})
        self.assertEqual(status,200,prepared)
        status,source=self.request('commands/execute',{'operation_id':'http-source','approved':True})
        self.assertEqual(source['state'],'succeeded',source)
        original=self.executor.workspace_root/'api-original.txt'
        self.assertEqual(self.request('commands/compensation-preview',{'source_operation_id':'http-source'},auth=False)[0],401)
        self.assertEqual(self.request('commands/compensation-preview',{'source_operation_id':'http-source','path':str(original)})[0],400)
        for action in ('quarantine','restore'):
            status,preview=self.request('commands/compensation-preview',{'source_operation_id':'http-source'})
            self.assertEqual(status,200,preview);self.assertTrue(preview['available'],preview)
            self.assertEqual(preview['action'],action)
            status,pending=self.request('commands/compensation-prepare',{'source_operation_id':'http-source',
                'source_receipt_hash':preview['source_receipt_hash'],'expected_revision':preview['compensation']['revision'],
                'action':action,'operation_id':'http-'+action})
            self.assertEqual(status,200,pending);self.assertEqual(pending['state'],'awaiting_approval')
            self.assertEqual(original.exists(),action=='quarantine')
            status,done=self.request('commands/execute',{'operation_id':pending['operation_id'],'approved':True})
            self.assertEqual(status,200,done);self.assertEqual(done['state'],'succeeded',done)
            self.assertEqual(original.exists(),action=='restore')
        self.assertEqual(original.read_text(),'Synthetic reversible file')
        self.assertEqual(self.commands.get('http-source')['state'],'succeeded')

    def test_prompt_composition_requires_host_and_cannot_accept_privileged_text(self):
        request = {'mode': 'voice', 'preferences': {'style': 'formal', 'language': 'es'}}
        self.assertEqual(self.request('prompts/compose', request, auth=False)[0], 401)
        self.assertEqual(self.request('prompts/compose', request, origin='https://untrusted.invalid')[0], 403)
        status, result = self.request('prompts/compose', request)
        self.assertEqual(status, 200)
        self.assertEqual(result['mode'], 'voice')
        self.assertEqual(result['version'], 'axx-contracts-1')
        self.assertEqual(len(result['text']), result['characters'])
        self.assertEqual(self.request('prompts/compose', dict(request, developerInstructions='send secrets'))[0], 400)
        self.assertEqual(self.request('prompts/compose', {'mode': 'planning'})[0], 400)
        self.assertEqual(self.executor.list_operations(), [])

    def test_mobile_tls_executes_once_and_keeps_file_write_approval_on_pc(self):
        from backend.mobile.gateway import MobileGateway
        gateway=MobileGateway.for_backend(self.server,self.executor.db_path,self.tmp.name)
        self.server.mobile=gateway
        gateway.host_resolver=lambda:'127.0.0.1'
        try:
            pairing=gateway.start()
            context=ssl.create_default_context(cafile=str(gateway._identity[0]))
            device=gateway.store.consume_pairing(pairing['pairing_code'],'Integration test')
            gateway.store.set_tool_permission(device['device_id'],True)
            def mobile(path,body=None):
                req=urllib.request.Request(pairing['endpoint']+path,data=json.dumps(body).encode() if body else None,
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+device['credential']})
                with urllib.request.urlopen(req,context=context,timeout=10) as response:return json.load(response)['data']
            resolved=mobile('/v1/work/resolve',{'text':'estado del sistema'})
            self.assertEqual(resolved['command_id'],'axx.system.telemetry')
            command={'command_id':resolved['command_id'],'inputs':resolved['inputs'],'operation_id':str(uuid.uuid4()),'approved':False}
            result=mobile('/v1/work/execute',command)
            self.assertEqual(result['state'],'succeeded')
            self.assertTrue(result['postconditions_passed'])
            self.assertEqual(mobile('/v1/work/execute',command)['operation_id'],result['operation_id'])
            self.assertEqual(len(self.commands.operations()),1)
            write={**command,'operation_id':str(uuid.uuid4()),'command_id':'axx.artifact.write','inputs':{'path':'phone-note.txt','content':'Contenido verificado'}}
            self.assertEqual(mobile('/v1/work/execute',write)['state'],'awaiting_pc_approval')
            target=self.executor.workspace_root/'phone-note.txt'
            self.assertFalse(target.exists())
            status,receipt=self.request('mobile/work/approve',{'operation_id':write['operation_id'],'approved':True})
            self.assertEqual(status,200)
            self.assertEqual(receipt['state'],'succeeded')
            self.assertTrue(receipt['postconditions_passed'])
            self.assertEqual(target.read_text(encoding='utf-8'),'Contenido verificado')
        finally:
            gateway.close()

    def test_executable_catalog_requires_auth_and_tracks_live_registry(self):
        self.assertEqual(self.request('commands/executable', auth=False)[0], 401)
        status, catalog = self.request('commands/executable')
        self.assertEqual(status, 200)
        ids = {row['id'] for row in catalog['commands']}
        expected = {key for key, row in self.commands.commands.items() if row['execution_enabled'] and key in self.commands.adapters}
        self.assertEqual(ids, expected)
        self.assertIn('axx.system.telemetry', ids)
        shell = next(row for row in catalog['commands'] if row['id']=='axx.shell.powershell')
        self.assertTrue(shell['pc_approval_required'])
        self.commands.commands['axx.system.telemetry']['execution_enabled'] = False
        self.assertNotIn('axx.system.telemetry', {row['id'] for row in self.request('commands/executable')[1]['commands']})
        self.assertEqual(self.executor.list_operations(), [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.memory = ProceduralMemory(self.executor.db_path)
        handler = type('CommandsHandler', (AxxBridgeHandler,), {'executor': self.executor, 'commands': self.commands, 'memory': self.memory})
        self.handler = handler
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.commands.channel_guard = self.server.commands_authorized
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.commands.close()
        self.memory.close()
        self.executor.close()

    def request(self, path, body=None, auth=True, origin=None, raw=None, token=None, channel_header=None):
        headers = {'Authorization': 'Bearer ' + (token or self.server.host_token)} if auth else {}
        if channel_header:
            headers['X-Axx-Command-Channel'] = channel_header
        if origin:
            headers['Origin'] = origin
        if body is not None or raw is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + path,
            data=raw if raw is not None else json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            try:
                return response.code, json.loads(response.read())
            finally:
                response.close()

    def test_telegram_daemon_uses_scoped_token_and_live_command_policy(self):
        import time
        from unittest.mock import patch
        from backend.chat_store import ChatStore
        from backend.telegram.daemon import CoreClient, ChatProxy, CommandProxy, DisabledInference
        from backend.telegram.service import TelegramService
        self.handler.chats = chats = ChatStore(self.executor.db_path)
        self.addCleanup(chats.close)
        root = Path(self.tmp.name)
        account = {'enabled':True,'account_id':41,'owner_id':52,'grants':{'pc_commands':True,'conversation':True}}
        self.handler.telegram = TelegramService(root, chats, self.commands, DisabledInference(), lambda: {})
        descriptor = root/'test-endpoint.json'
        descriptor.write_text(json.dumps({'port':self.server.server_port,'token':self.server.telegram_token,
                                          'instance_id':self.server.instance_id}),encoding='utf-8')
        with patch('backend.telegram.daemon._dpapi_decrypt',side_effect=lambda raw:raw), \
             patch('backend.telegram.service.load_account',return_value=account), \
             patch('backend.telegram.service.confirmation_policy',return_value={'enabled':False}):
            core = CoreClient(descriptor)
            daemon = TelegramService(root, ChatProxy(core), CommandProxy(core), DisabledInference(), lambda: {})
            chat = daemon._thread(account)
            chats.mutate('update',{'id':chat['id'],'command_mode':'unrestricted','confirm_unrestricted':True})
            response = daemon.admit({'account_id':41,'peer_id':52,'message_id':1,'sent_at':time.time(),
                                     'kind':'text','text':'/powershell Get-Date'})
            self.assertEqual(response['state'],'awaiting_approval',response)
            operation = self.commands.get(response['operation_id'])
            self.assertEqual((operation['channel'],operation['command_mode']),('telegram','ask'))
            self.assertEqual(self.request('commands/execute',{'operation_id':operation['operation_id'],'approved':True},
                                         token=self.server.telegram_token,channel_header='desktop')[0],400)
            self.assertEqual(self.request('chat/update',{'id':chat['id'],'command_mode':'auto_safe'},
                                         token=self.server.telegram_token)[0],403)
            self.assertEqual(self.request('commands/operations?operation_id='+operation['operation_id'],
                                         token=self.server.mobile_token)[0],404)
            self.assertEqual(self.request('commands/prepare',{'command_id':'axx.system.telemetry','inputs':{},
                                         'channel':'desktop'},token=self.server.telegram_token)[0],400)
            account['grants']['pc_commands'] = False
            _, denied = self.request('commands/execute',{'operation_id':operation['operation_id'],'approved':True})
            self.assertEqual(denied['state'],'blocked',denied)
            self.assertEqual(denied['error']['code'],'REMOTE_PERMISSION_REQUIRED')
            self.assertEqual(self.executor.list_operations(), [])

    def test_selected_chat_model_uses_connect_and_cannot_approve_a_write(self):
        from unittest.mock import Mock
        from backend.chat_store import ChatStore
        from backend.connect.service import ConnectService
        self.handler.chats = chats = ChatStore(self.executor.db_path)
        self.addCleanup(chats.close)
        self.handler.connect = connect = ConnectService(self.commands, self.memory)
        self.addCleanup(connect.close)
        self.handler.adapter = adapter = Mock()
        adapter.cancel.return_value = False
        adapter.config = {'providers':[{'name':'ollama-local','model':'test','enabled':True,'capabilities':['text','tools']}]}
        cid=chats.mutate('create',{'command_mode':'auto_safe'})['id']
        chat=chats.get(cid)
        body={'axx_tools':True,'model':'test','provider_name':'ollama-local','conversation_id':chat['connect_id'],
              'memory_scope':chat['memory_scope'],'messages':[{'role':'user','content':'test'}]}
        def request_tool(request_id, name, arguments):
            adapter.route.return_value={'ok':True,'request_id':request_id,'message':{'content':'',
                'tool_calls':[{'type':'function','id':'c','function':{'name':name,'arguments':arguments}}]}}
            status,result=self.request('chat',body|{'request_id':request_id})
            self.assertEqual(status,200,result)
            return result
        result=request_tool('read-1','axx_system_telemetry','{}')
        receipt=result['axx_tool_receipt']
        self.assertEqual(receipt['state'],'succeeded',receipt)
        self.assertTrue(receipt['postconditions_passed'])
        self.assertEqual(self.commands.get(receipt['operation_id'])['channel'],'model')
        self.assertEqual(request_tool('unknown','axx_shell_powershell','{}')['axx_tool_receipt']['state'],'blocked')
        self.assertEqual(request_tool('duplicate','axx_artifact_write','{"path":"a.txt","path":"b.txt","content":"x"}')
                         ['axx_tool_receipt']['state'],'blocked')
        chats.mutate('update',{'id':cid,'command_mode':'unrestricted','confirm_unrestricted':True})
        receipt=request_tool('write','axx_artifact_write','{"path":"owned.txt","content":"x"}')['axx_tool_receipt']
        self.assertEqual(receipt['state'],'awaiting_approval')
        self.assertFalse((self.executor.workspace_root/'owned.txt').exists())
        status, result=self.request('chat/cancel',{'request_id':'write','axx_tools':True})
        self.assertEqual(status,200)
        self.assertTrue(result['cancelled'])
        self.assertEqual(connect.get_task(receipt['operation_id'])['state'],'cancelled')
        adapter.config['providers'][0]['capabilities']=['text']
        self.assertEqual(request_tool('unsupported','axx_system_telemetry','{}')['axx_tools_status'],'unsupported')

    def test_stopping_speech_does_not_cancel_a_pending_command(self):
        pending = self.commands.prepare('axx.shell.powershell', {'script': 'Get-Date'})
        status, result = self.request('speech/cancel', {})
        self.assertEqual(status, 200)
        self.assertEqual(result['cancelled_operations'], 0)
        self.assertEqual(self.commands.get(pending['operation_id'])['state'], 'awaiting_approval')

    def test_delivery_mode_is_enforced_across_http(self):
        status, rejected = self.request('commands/prepare', {'command_id':'axx.desktop.open_app',
            'inputs':{'app':'calculator'}, 'delivery_mode':'background'})
        self.assertEqual(status, 400)
        self.assertIn('background_unavailable', str(rejected))
        status, pending = self.request('commands/prepare', {'command_id':'axx.architecture.status',
            'inputs':{}, 'delivery_mode':'background'})
        self.assertEqual(status, 200)
        status, result = self.request('commands/execute', {'operation_id':pending['operation_id']})
        self.assertEqual(status, 200)
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(result['delivery_mode'], 'background')

    def test_conversational_context_crosses_transport_and_details_are_read_only(self):
        status, result = self.request('commands/resolve', {'text': 'busca afraid', 'source': 'text', 'context': {'engine': 'youtube'}})
        self.assertEqual(status, 200)
        self.assertEqual(result['inputs'], {'engine': 'youtube', 'query': 'afraid'})
        self.assertEqual(self.request('commands/resolve', {'text': 'busca gatos', 'context': {'execute': True}})[0], 400)
        self.assertEqual(self.request('commands/resolve', {'text': 'busca gatos', 'context': []})[0], 400)
        status, details = self.request('commands/details?id=AXX-02-0147')
        self.assertEqual(status, 200)
        self.assertEqual(details['command']['adapter_id'], 'axx.file.sha256')
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.request('commands/details?id=AXX-02-0147', auth=False)[0], 401)

    def test_paraphrase_reports_interpretation_without_executing(self):
        status,result=self.request('commands/resolve',{'text':'Oye Axx, por favor podrías buscarme gatos usando YouTube','source':'voice'})
        self.assertEqual(status,200)
        self.assertEqual(result['inputs'],{'engine':'youtube','query':'gatos'})
        self.assertEqual(result['understanding']['canonical'],'busca gatos en youtube')
        self.assertEqual(result['understanding']['method'],'bounded_grammar')
        self.assertEqual(self.executor.list_operations(),[])

    def test_unknown_voice_verb_only_suggests_and_does_not_prepare(self):
        status,result=self.request('commands/resolve',{'text':'puedes sabrirme Spotify','source':'voice'})
        self.assertEqual(status,200)
        self.assertEqual(result['match'],'needs_input')
        self.assertEqual(result['understanding']['candidate'],'abre Spotify')
        self.assertIs(result['understanding']['execution_allowed'],False)
        self.assertEqual(self.request('commands/resolve',{'text':'sabrirme Spotify','source':'text'})[1]['match'],'none')
        self.assertEqual(self.executor.list_operations(),[])

    def test_discovery_preparation_uses_command_policy(self):
        from unittest.mock import patch
        proposal = {'command_id': 'axx.desktop.window.set_value',
                    'inputs': {'window_id': '0x123', 'pid': 99, 'control_id': 'a' * 64, 'value': 'hello'}}
        with patch('backend.actions.cli_anything_engine.ENGINE.propose', return_value=proposal):
            status, pending = self.request('cli-anything/prepare', {'target': '0x123', 'command': 'type', 'args': {'control_id': 'a'*64, 'text': 'hello'}})
            self.assertEqual(status, 200)
            self.assertEqual(pending['state'], 'awaiting_approval')
            self.assertEqual(pending['command_id'], proposal['command_id'])
            self.assertEqual(self.request('cli-anything/prepare', {'command': 'type', 'approved': True})[0], 400)
            self.assertEqual(self.request('cli-anything/prepare', {'command': 'type'}, auth=False)[0], 401)
        status, refused = self.request('cli-anything/execute', {'approved': True})
        self.assertEqual(status, 409)
        self.assertEqual(refused['error']['code'], 'USE_COMMAND_POLICY')

    def test_legacy_routes_cannot_bypass_catalog_policy(self):
        status, _ = self.request('actions/execute', {'tool_name': 'desktop_powershell', 'inputs': {'script': 'Get-Date'}})
        self.assertEqual(status, 403)
        for tool in ('file_artifact_writer', 'blender_render_fixture'):
            inputs = {'path': 'bypass.txt', 'content': 'x'} if tool == 'file_artifact_writer' else {'filename': 'fixture.png'}
            status, result = self.request('actions/execute', {'tool_name': tool, 'inputs': inputs})
            self.assertEqual(status, 403)
            self.assertEqual(result['error']['code'], 'USE_COMMAND_POLICY')
        self.memory.register_recipe(id='legacy-write', intent_key='legacy-write', status='verified',
            steps=[{'tool': 'file_artifact_writer', 'args': {'path': '$inputs.path', 'content': '$inputs.content'}}],
            schema={'path': {'type': 'string', 'required': True}, 'content': {'type': 'string', 'required': True}})
        status, _ = self.request('recipes/execute', {'intent_key': 'legacy-write', 'inputs': {'path': 'legacy.txt', 'content': 'x'}})
        self.assertEqual(status, 403)
        status, pending = self.request('recipes/prepare', {'intent_key': 'legacy-write', 'inputs': {'path': 'legacy.txt', 'content': 'x'}})
        self.assertEqual(status, 200)
        self.assertEqual(pending['state'], 'awaiting_approval')
        self.assertFalse((self.executor.workspace_root / 'legacy.txt').exists())
        status, result = self.request('commands/execute', {'operation_id': pending['operation_id'], 'approved': True})
        self.assertEqual(result['state'], 'succeeded')
        self.assertFalse((self.executor.workspace_root / 'bypass.txt').exists())

    def test_saved_recipe_listing_exposes_actual_parameter_schema(self):
        self.memory.register_recipe(id='telemetry', intent_key='telemetry', status='verified',
            steps=[{'tool': 'system_telemetry', 'args': {}}], schema={})
        self.memory.register_recipe(id='write', intent_key='write', status='verified',
            steps=[{'tool': 'file_artifact_writer', 'args': {'path': '$inputs.path', 'content': '$inputs.content'}}],
            schema={'path': {'type': 'string', 'required': True}, 'content': {'type': 'string', 'required': True}})
        status, result = self.request('recipes')
        self.assertEqual(status, 200)
        by_id = {row['id']: row for row in result['recipes']}
        self.assertEqual(by_id['telemetry']['schema'], {})
        self.assertEqual(set(by_id['write']['schema']), {'path', 'content'})
        status, pending = self.request('recipes/prepare', {'intent_key': 'telemetry', 'inputs': {}})
        self.assertEqual(status, 200)
        self.assertEqual(pending['command_id'], 'axx.system.telemetry')
        self.assertEqual(self.request('commands/execute', {'operation_id': pending['operation_id']})[1]['state'], 'succeeded')

    def test_catalog_search_and_real_text_voice_resolution_require_host(self):
        self.assertEqual(self.request('commands', auth=False)[0], 401)
        self.assertEqual(self.request('commands', origin='https://untrusted.invalid')[0], 403)
        status, catalog = self.request('commands?q=axx.system.telemetry&limit=1')
        self.assertEqual(status, 200)
        self.assertEqual(catalog['commands'][0]['id'], 'axx.system.telemetry')
        for source in ('text', 'voice'):
            status, result = self.request('commands/resolve', {'text': 'estado del sistema', 'source': source})
            self.assertEqual(status, 200)
            self.assertEqual(result['command_id'], 'axx.system.telemetry')

    def test_typed_prepare_approval_hash_verification_and_observation(self):
        status, operation = self.request('commands/prepare', {'command_id': 'axx.artifact.write',
            'inputs': {'path': 'http.txt', 'content': 'local HTTP evidence'}, 'source': 'text'})
        self.assertEqual(status, 200)
        op_id = operation['operation_id']
        status, denied = self.request('commands/execute', {'operation_id': op_id})
        self.assertEqual(status, 403)
        self.assertEqual(denied['error']['code'], 'APPROVAL_REQUIRED')
        self.assertFalse((self.executor.workspace_root / 'http.txt').exists())
        status, result = self.request('commands/execute', {'operation_id': op_id, 'approved': True})
        self.assertEqual(status, 200)
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        observed = self.request('commands/operations?operation_id=' + op_id)[1]['operation']
        self.assertEqual(observed['evidence']['sha256'], result['evidence']['sha256'])

    def test_cancel_and_invalid_requests_never_write(self):
        for body in ({'command_id': [], 'inputs': {}, 'source': 'text'},
                     {'command_id': 'axx.process.inspect', 'inputs': {'pid': True}, 'source': 'text'},
                     {'command_id': 'axx.system.telemetry', 'inputs': {}, 'source': 'voice', 'shell': 'calc'}):
            self.assertEqual(self.request('commands/prepare', body)[0], 400)
        status, operation = self.request('commands/prepare', {'command_id': 'axx.artifact.write',
            'inputs': {'path': 'cancel.txt', 'content': 'x'}, 'source': 'voice'})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('commands/cancel', {'operation_id': operation['operation_id']})[1]['state'], 'cancelled')
        self.assertEqual(self.request('commands/execute', {'operation_id': operation['operation_id'], 'approved': True})[1]['state'], 'cancelled')
        self.assertFalse((self.executor.workspace_root / 'cancel.txt').exists())
        self.assertEqual(self.request('commands?limit=100000')[0], 400)
        self.assertEqual(self.request('commands?limit=1&limit=2')[0], 400)

    def test_duplicate_json_keys_rejected_at_transport(self):
        status, _ = self.request('commands/execute', raw=b'{"operation_id":"x","approved":false,"approved":true}')
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
