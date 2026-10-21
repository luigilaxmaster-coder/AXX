"""Offline release regressions exercising actual HTTP, workers and persisted effects."""
from __future__ import annotations
import http.client
import base64
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch
import urllib.error
import urllib.request

from backend.server import AxxBridgeHandler, ThreadedHTTPServer, resolve_app_paths
from backend.inference.adapter import InferenceAdapter
from backend.inference.router import Router, RequestError, PolicyBlocked, UpstreamError
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.sync.identity_sync import IdentityStore
from backend.speech.windows_tts import WindowsSpeechService
from backend.speech.offline_asr import OfflineTranscriptionService

class DeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'state.db'
        self.adapter = InferenceAdapter({'allow_paid': False, 'providers': []}, self.db)
        self.executor = ActionExecutor(self.db, workspace_root=Path(self.tmp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.memory = ProceduralMemory(self.db)
        self.identity = IdentityStore(self.db)
        self.speech = WindowsSpeechService(Path(self.tmp.name))
        self.transcription = OfflineTranscriptionService(Path(self.tmp.name))
        handler = type('TestHandler', (AxxBridgeHandler,), dict(adapter=self.adapter, executor=self.executor,
                      commands=self.commands, memory=self.memory, identity=self.identity, speech=self.speech, transcription=self.transcription))
        self.server = ThreadedHTTPServer(('127.0.0.1',0),handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.adapter.close()
        self.commands.close()
        self.executor.close()
        self.memory.close()
        self.identity.close()
        self.speech.close()
        self.transcription.close()
        self.tmp.cleanup()

    def request(self,path,body=None,headers=None,auth=True):
        h = {'Authorization': 'Bearer '+self.server.host_token} if auth else {}
        h.update(headers or {})
        data = None
        if body is not None:
            data=json.dumps(body).encode()
            h['Content-Type']='application/json'
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}'+path,data=data,headers=h)
        try:
            with urllib.request.urlopen(req,timeout=5) as response:
                return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code,json.loads(exc.read())

    def test_no_public_token_or_cross_origin_access(self):
        for path in ('/axx-api/status','/axx-api/actions','/axx-api/identity'):
            self.assertEqual(self.request(path,auth=False)[0],401)
        status,data=self.request('/axx-api/status')
        self.assertEqual(status,200)
        self.assertNotIn('csrf',data)
        self.assertNotIn(self.server.host_token,json.dumps(data))
        self.assertEqual(self.request('/axx-api/actions/execute',{'tool_name':'system_telemetry'},auth=False)[0],401)
        self.assertEqual(self.request('/axx-api/status',headers={'Origin':'https://untrusted.invalid'})[0],403)

    def test_models_empty_and_spotify_truthful(self):
        self.assertEqual(self.request('/axx-api/models')[1]['models'],[])
        status,data=self.request('/axx-api/spotify/command',{})
        self.assertEqual(status,501)
        self.assertFalse(data['available'])

    def test_session_desktop_permissions(self):
        discover=self.request('/axx-api/desktop/discover',{})[1]
        self.assertFalse(any(app['approved'] for app in discover['apps']))
        self.assertEqual(self.request('/axx-api/desktop/launch',{'id':'notepad'})[0],403)
        self.assertTrue(self.request('/axx-api/desktop/authorize',{'id':'notepad','approved':True})[1]['approved'])
        self.assertTrue(next(app for app in self.request('/axx-api/desktop/discover',{})[1]['apps'] if app['id']=='notepad')['approved'])
        self.assertEqual(self.request('/axx-api/desktop/authorize',{'id':'powershell','approved':True})[0],400)
        self.assertTrue(self.request('/axx-api/desktop/revoke-all',{})[1]['revoked'])
        self.assertFalse(any(app['approved'] for app in self.request('/axx-api/desktop/discover',{})[1]['apps']))

    def test_body_size_and_object_validation(self):
        self.assertEqual(self.request('/axx-api/identity',[])[0],400)
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        client.putrequest('POST','/axx-api/identity')
        client.putheader('Authorization','Bearer '+self.server.host_token)
        client.putheader('Content-Type','application/json')
        client.putheader('Content-Length',str(2*1024*1024+1))
        client.endheaders()
        response=client.getresponse()
        self.assertEqual(response.status,413)
        response.read()
        client.close()

    def test_real_file_recipe_approval_replay_new_inputs_and_restart(self):
        args={'path':'first.txt','content':'first verified artifact'}
        status,pending=self.request('/axx-api/commands/prepare',{'command_id':'axx.artifact.write','inputs':args,'operation_id':'first-write'})
        self.assertEqual(pending['state'],'awaiting_approval')
        self.assertFalse((self.executor.workspace_root/'first.txt').exists())
        status,first=self.request('/axx-api/commands/execute',{'operation_id':'first-write','approved':True})
        self.assertEqual(status,200)
        self.assertEqual(first['state'],'succeeded')
        target=Path(first['evidence']['path'])
        self.assertEqual(target.read_text(),'first verified artifact')
        original_mtime=target.stat().st_mtime_ns
        replay=self.request('/axx-api/commands/execute',{'operation_id':'first-write','approved':True})[1]
        self.assertTrue(replay['replayed'])
        self.assertEqual(target.stat().st_mtime_ns,original_mtime)
        status,recipe=self.request('/axx-api/recipes/register',{'id':'write-doc','intent_key':'write-document','operation_id':first['action_operation_id']})
        self.assertEqual(status,200)
        self.memory.close()
        self.memory.db=sqlite3.connect(str(self.db),check_same_thread=False)
        pending=self.request('/axx-api/recipes/prepare',{'intent_key':'write-document','inputs':{'path':'second.txt','content':'second real artifact'},'operation_id':'recipe-second'})[1]
        self.assertEqual(pending['state'],'awaiting_approval')
        self.assertFalse((self.executor.workspace_root/'second.txt').exists())
        result=self.request('/axx-api/commands/execute',{'operation_id':'recipe-second','approved':True})[1]
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(result['model_calls_used'],0)
        second=Path(self.tmp.name)/'artifacts'/'second.txt'
        self.assertEqual(second.read_text(),'second real artifact')
        replay=self.request('/axx-api/recipes/prepare',{'intent_key':'write-document','inputs':{'path':'second.txt','content':'second real artifact'},'operation_id':'recipe-second'})[1]
        self.assertTrue(replay['replayed'])
        mismatch=self.request('/axx-api/recipes/prepare',{'intent_key':'write-document','inputs':{'path':'third.txt','content':'different request'},'operation_id':'recipe-second'})
        self.assertEqual(mismatch[0],400)
        self.assertFalse((Path(self.tmp.name)/'artifacts'/'third.txt').exists())
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0],2)
        self.assertEqual(self.request('/axx-api/actions/operations')[1]['operations'][0]['state'],'succeeded')

    def test_recipe_requires_evidence_and_workspace_containment(self):
        self.assertEqual(self.request('/axx-api/recipes/register',{'id':'bad','intent_key':'bad','operation_id':'missing'})[0],400)
        status,result=self.request('/axx-api/commands/prepare',{'command_id':'axx.artifact.write','inputs':{'path':'../escape.txt','content':'blocked'}})
        self.assertEqual(status,400)
        self.assertFalse((Path(self.tmp.name)/'escape.txt').exists())

    def test_actual_source_worker_no_provider(self):
        result=self.adapter.route({'request_id':'actual-worker','messages':[{'role':'user','content':'offline'}]})
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'],'NO_PROVIDER_AVAILABLE')

    def test_worker_wall_deadline_and_cancel_terminate_process(self):
        # A deliberately stalled real OS child proves the host deadline and cancellation;
        # no provider, transcript, or inference success is simulated here.
        import backend.inference.adapter as module
        spawned=[]
        real_spawn=module.spawn_managed_process
        def stalled(command,**kwargs):
            proc,job=real_spawn([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            spawned.append(proc)
            return proc,job
        with patch.object(module,'spawn_managed_process',stalled):
            before=time.monotonic()
            result=self.adapter.route({'request_id':'deadline','deadline_ms':100,'messages':[{'role':'user','content':'x'*200000}]})
            self.assertEqual(result['error']['code'],'DEADLINE_EXCEEDED')
            self.assertLess(time.monotonic()-before,3)
            result_holder=[]
            worker=threading.Thread(target=lambda:result_holder.append(self.adapter.route({'request_id':'cancel','messages':[{'role':'user','content':'offline'}]})))
            worker.start()
            until=time.monotonic()+3
            while len(spawned)<2 and time.monotonic()<until:
                time.sleep(.01)
            self.assertTrue(self.adapter.cancel('cancel'))
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result_holder[0]['error']['code'],'CANCELLED')
        self.assertTrue(all(proc.poll() is not None for proc in spawned))

    def test_paid_and_local_only_blocked(self):
        with self.assertRaises(ValueError):
            InferenceAdapter({'allow_paid':True,'providers':[]},self.db)
        self.assertEqual(self.adapter.route({'sensitivity':'local_only'})['error']['code'],'INVALID_REQUEST')

    def test_memory_inspection_fallback_and_bounded_identifiers(self):
        status,data=self.request('/axx-api/memory/query',{'query':'verified recipe'})
        self.assertEqual(status,200)
        self.assertEqual(data['hits'],[])
        self.assertEqual(data['memory']['backend'],'sqlite')
        self.assertFalse(data['execution_allowed'])
        self.assertEqual(self.request('/axx-api/memory/read',{'recipe_id':'../escape'})[0],400)
        self.assertEqual(self.request('/axx-api/memory/query',{'query':'x'*4001})[0],400)

    def test_offline_transcription_input_guards(self):
        for body in ({'audio_base64':'bad','mime':'audio/wav'},
                     {'audio_base64':'YWJjZA==','mime':'audio/wav'},
                     {'audio_base64':'YWJjZA==','mime':'application/octet-stream'},
                     {'audio_base64':'YWJjZA==','mime':'audio/wav','task':'translate-to-spanish'}):
            self.assertEqual(self.request('/axx-api/speech/transcribe',body)[0],400)
        status,data=self.request('/axx-api/speech/status')
        self.assertEqual(status,200)
        self.assertTrue(data['asr']['local_only'])
        self.assertEqual(data['asr']['max_duration_seconds'],60)

    @unittest.skipUnless(os.name=='nt','Windows SAPI service requires Windows')
    def test_real_windows_speech_wav_and_input_guards(self):
        self.assertEqual(self.request('/axx-api/speech/synthesize',{'text':'x'*1201})[0],400)
        self.assertEqual(self.request('/axx-api/speech/synthesize',{'text':'test','rate':True})[0],400)
        self.assertEqual(self.request('/axx-api/speech/synthesize',{'text':'test','voice':'not-an-installed-voice'})[0],400)
        status,voices=self.request('/axx-api/speech/voices')
        self.assertEqual(status,200)
        self.assertTrue(voices['available'])
        status,result=self.request('/axx-api/speech/synthesize',{'text':'Axx local voice verification.','voice':voices['voices'][0]['name']})
        self.assertEqual(status,200)
        raw=base64.b64decode(result['audio_base64'],validate=True)
        with wave.open(io.BytesIO(raw),'rb') as audio:
            self.assertEqual(audio.getframerate(),16000)
            self.assertEqual(audio.getnchannels(),1)
            self.assertGreater(audio.getnframes(),0)
        self.assertEqual(result['evidence']['size'],len(raw))
        self.assertFalse(result['playback_verified'])
        self.assertEqual(result['external_calls'],0)
        self.assertFalse(any(self.speech.data_dir.iterdir()))

    def test_blender_capability_schema_and_idle_cancellation(self):
        status,result=self.request('/axx-api/actions/execute',{'tool_name':'blender_render_fixture','inputs':{'filename':'../escape.png'}})
        self.assertEqual(status,403)
        self.assertEqual(result['error']['code'],'USE_COMMAND_POLICY')
        self.assertEqual(self.request('/axx-api/actions/execute',{'tool_name':'blender_render_fixture','inputs':{'filename':'fixture.png','script':'blocked'}})[0],403)
        status,cancelled=self.request('/axx-api/actions/cancel',{})
        self.assertEqual(status,200)
        self.assertEqual(cancelled['cancelled_operations'],0)

    def test_baseline_sqlite_migration_and_preferences(self):
        legacy=Path(self.tmp.name)/'legacy.db'
        db=sqlite3.connect(str(legacy))
        db.execute('CREATE TABLE usage(name TEXT,day TEXT,attempts INTEGER,PRIMARY KEY(name,day))')
        db.execute('CREATE TABLE cooldown(name TEXT PRIMARY KEY,until REAL)')
        db.commit();db.close()
        with Router({'providers':[],'allow_paid':False},legacy) as router:
            self.assertIn('quota_scope_id',{row[1] for row in router.db.execute('PRAGMA table_info(usage)')})
        preferences={'studio':{'form':'Pearl','temporary_state':'thinking'},'settings':{'palette':'Opal'}}
        self.assertTrue(self.request('/axx-api/identity',preferences)[1]['saved'])
        self.assertEqual(self.request('/axx-api/identity')[1]['identity'],{'studio':{'form':'Pearl'},'settings':{'palette':'Opal'}})

if __name__=='__main__':
    unittest.main()
