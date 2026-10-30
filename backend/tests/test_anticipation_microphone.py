"""Local context clips use synthetic audio/children only; never a live microphone."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService
from backend.commands import CommandService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.speech.offline_asr import MAX_AUDIO, OfflineTranscriptionService
from backend.speech.windows_tts import SpeechError


class MicrophoneFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.now=time.time(); self.secret='SYNTHETIC_PRIVATE_MICROPHONE_TRANSCRIPT'
        self.executor=ActionExecutor(self.root/'state.db', self.root/'artifacts')
        self.commands=CommandService(self.executor)
        self.service=AnticipationService(self.commands, clock=lambda:self.now)
        self.asr=OfflineTranscriptionService(self.root); self.asr.model_path=self.root
        def status():
            self.assertFalse(self.service.lock._is_owned())
            return {'available':True,'busy':self.asr._busy.locked() or self.asr._io_lock.locked()}
        self.status_patch=patch.object(self.asr,'status',side_effect=status); self.status_patch.start()
        self.service.attach_transcription(self.asr)

    def tearDown(self):
        self.service.close(); self.asr.close(); self.status_patch.stop()
        self.commands.close(); self.executor.close(); self.temp.cleanup()

    def configure(self, retain=False, **changes):
        self.target={'id':'mic-local','source':'microphone','task_id':'task-mic','project_id':'project-a',
            'observe':True,'retain':retain,'send_to_provider':False,'expires_at':self.now+120}
        self.target.update(changes)
        self.service.configure({'profile':'copiloto','sources':{'microphone':True},'observation_targets':[self.target]})
        self.target=self.service.status()['observation_targets'][0]

    def begin(self):
        return self.service.microphone_begin({'target_id':self.target['id'],'task_id':self.target['task_id'],
            **{key:self.target[key] for key in ('project_id','application_id','device_id')}})

    def payload(self, lease):
        return {'capture_id':lease['capture_id'],'audio_base64':base64.b64encode(b'RIFF0000WAVEdata').decode(),
            'mime':'audio/wav','language':'es'}

    def result(self):
        return {'text':self.secret,'audio_duration_seconds':1.25}


class AnticipationMicrophoneTests(MicrophoneFixture):
    def test_defaults_capabilities_scope_busy_and_provider_fail_closed_without_capture(self):
        self.assertFalse(self.service.status()['sources']['microphone'])
        self.service.attach_transcription(None)
        self.assertFalse(self.service.status()['capabilities']['microphone'])
        self.assertTrue(self.service.status()['capabilities']['microphone_unavailable_reason'])
        with self.assertRaises(ValueError):self.configure()
        self.service.attach_transcription(self.asr); self.configure()
        self.assertTrue(self.service.status()['capabilities']['microphone'])
        for body in ({'target_id':'mic-local','task_id':'foreign','project_id':'project-a'},
                {'target_id':'mic-local','task_id':'task-mic','project_id':'foreign'},
                {'target_id':'mic-local','task_id':'task-mic','project_id':'project-a','allow_input':True}):
            with self.subTest(body=body),self.assertRaises(ValueError):self.service.microphone_begin(body)
        self.assertFalse(self.service.microphone_leases)
        with self.asr._busy:
            with self.assertRaises(SpeechError) as caught:self.begin()
            self.assertEqual(caught.exception.code,'BUSY')
        self.assertFalse(self.service.microphone_leases)
        with self.assertRaises(ValueError):self.configure(send_to_provider=True)
        self.configure(); self.service.configure({'profile':'discreto'})
        with self.assertRaises(ValueError):self.begin()
        self.service.configure({'profile':'copiloto','scopes':[{'project_id':'project-a','exclude':True}]})
        with self.assertRaises(ValueError):self.begin()
        self.assertFalse(self.service.microphone_leases)
        self.service.configure({'scopes':[]})
        self.service.attach_transcription(None)
        status=self.service.status()
        self.assertFalse(status['source_runtime'][0]['active'])
        self.assertIn('local ASR/TTS',status['metrics']['model_calls_scope'])

    def test_submit_has_metadata_only_history_no_raw_or_commands_or_explicit_ids(self):
        self.configure(retain=True); lease=self.begin(); body=self.payload(lease)
        with patch.object(self.asr,'_execute',return_value=self.result()) as execute:
            response=self.service.microphone_submit(body)
            self.assertTrue(response['accepted']); self.assertNotIn('text',response)
            context=execute.call_args.kwargs['_context']
            self.assertTrue(context.request_id.startswith('asr-auto-'))
            self.assertEqual(context.context_owner,'mic-'+lease['capture_id'])
            self.assertLessEqual(context.deadline_mono-time.monotonic(),60)
            self.assertFalse(self.asr._used_request_ids)
        state=self.service.source_state['mic-local']
        self.assertNotIn('raw',state)
        self.assertFalse(response['raw_content_retained']); self.assertIsNone(response['raw_expires_at'])
        status=self.service.status('task-mic'); event=status['source_observations'][0]
        self.assertEqual(event['resource']['fingerprint_scope'],'hmac_sha256_session')
        self.assertTrue(event['retained']); self.assertFalse(event['sent_to_provider'])
        self.assertNotIn(self.secret,json.dumps(status))
        self.assertEqual(self.service.provider_context_for_task('task-mic','project-a')['observations'],[])
        stored=self.service.db.execute('SELECT payload FROM anticipation_events').fetchone()[0]
        self.assertNotIn(self.secret,stored); self.assertNotIn(body['audio_base64'],stored)
        self.assertNotIn(self.secret.encode(),self.executor.db_path.read_bytes())
        self.assertFalse(self.executor.list_operations())
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM command_runs').fetchone()[0],0)
        with self.assertRaises(ValueError):self.service.microphone_submit(body)
        self.now+=31; next_lease=self.begin()
        self.assertNotIn('raw',state)
        self.service.microphone_stop({'capture_id':lease['capture_id']})
        self.assertIn(next_lease['capture_id'],self.service.microphone_leases)
        # Different valid base64 pad bits still describe the same audio bytes.
        alternate=self.payload(next_lease); encoded=alternate['audio_base64']
        alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        alternate['audio_base64']=encoded[:-3]+alphabet[alphabet.index(encoded[-3])^1]+encoded[-2:]
        self.assertEqual(base64.b64decode(encoded,validate=True),base64.b64decode(alternate['audio_base64'],validate=True))
        with patch.object(self.asr,'_execute',return_value=self.result()):self.service.microphone_submit(alternate)
        self.assertEqual(state['snapshot']['audio_fingerprint'],event['resource']['audio_fingerprint'])

    def test_no_retention_poll_skip_expiry_and_long_decoder_result_are_bounded(self):
        self.configure(); lease=self.begin()
        with patch.object(self.service,'_application_snapshot') as applications,patch.object(self.asr,'transcribe') as transcribe:
            self.service.tick(); applications.assert_not_called(); transcribe.assert_not_called()
        with patch.object(self.asr,'_execute',return_value={'text':'','audio_duration_seconds':1.25,'silence_detected':True}):
            response=self.service.microphone_submit(self.payload(lease))
            self.assertTrue(response['silence_detected']); self.assertEqual(response['characters'],0)
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM anticipation_events').fetchone()[0],0)
        runtime=self.service.status()['source_runtime'][0]
        self.assertEqual(runtime['samples'],1); self.assertIsNone(runtime['raw_expires_at'])
        self.assertEqual(self.service.status()['source_observations'][0]['resource']['characters'],0)
        event=self.service.microphone_leases[lease['capture_id']]['cancelled']
        self.now=lease['expires_at']+1; self.service._expire_source_content()
        self.assertTrue(event.is_set()); self.assertFalse(self.service.microphone_leases)
        self.assertNotIn('raw',self.service.source_state['mic-local'])
        with self.assertRaises(ValueError):self.service.microphone_submit(self.payload(lease))
        self.configure(expires_at=self.now+120); lease=self.begin()
        with patch.object(self.asr,'_execute',return_value={'text':self.secret,'audio_duration_seconds':11.01}):
            with self.assertRaises(SpeechError):self.service.microphone_submit(self.payload(lease))
        self.assertFalse(self.service.microphone_leases)
        self.assertNotIn('raw',self.service.source_state['mic-local'])

    def test_mutations_discard_inflight_result_without_touching_other_speech(self):
        for action in ('stop','pause','forget','rebind','close'):
            with self.subTest(action=action):
                self.configure(); lease=self.begin(); entered,release=threading.Event(),threading.Event(); errors=[]
                def execute(request,**kwargs):
                    self.assertFalse(self.service.lock._is_owned()); entered.set()
                    self.assertTrue(release.wait(3)); return self.result()
                def submit():
                    try:self.service.microphone_submit(self.payload(lease))
                    except SpeechError as exc:errors.append(exc.code)
                with patch.object(self.asr,'_execute',side_effect=execute),patch.object(self.asr,'cancel_active') as global_cancel,patch.object(self.asr,'cancel') as cancel:
                    thread=threading.Thread(target=submit); thread.start()
                    try:
                        self.assertTrue(entered.wait(2))
                        if action=='stop':self.service.microphone_stop({'capture_id':lease['capture_id']})
                        elif action=='pause':self.service.pause()
                        elif action=='forget':self.service.forget({'task_id':'task-mic'})
                        elif action=='close':self.service.close()
                        else:self.service.configure({'observation_targets':[self.target|{'project_id':'project-b'}]})
                        release.set(); thread.join(3); self.assertFalse(thread.is_alive())
                        self.assertTrue(errors); global_cancel.assert_not_called(); cancel.assert_not_called()
                        self.assertFalse(self.service.microphone_leases)
                        self.assertFalse(any(state.get('raw') for state in self.service.source_state.values()))
                    finally:release.set(); thread.join(3)
                if action!='close':self.service.configure({'paused':False,'observation_paused':False})
        self.assertNotIn(self.secret.encode(),self.executor.db_path.read_bytes())

    def test_stop_event_interrupts_real_asr_blocked_pipe_without_global_cancel(self):
        self.configure(); lease=self.begin(); body=self.payload(lease); children=[]; errors=[]
        body['audio_base64']=base64.b64encode(b'RIFF0000WAVE'+b'\0'*(MAX_AUDIO-12)).decode()
        def spawn(_command,**kwargs):
            self.assertFalse(self.service.lock._is_owned())
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)
            children.append(child); return child,None
        def submit():
            try:self.service.microphone_submit(body)
            except SpeechError as exc:errors.append(exc.code)
        with patch('backend.speech.offline_asr.spawn_managed_process',side_effect=spawn),patch.object(self.asr,'cancel_active') as cancel:
            thread=threading.Thread(target=submit); thread.start()
            try:
                until=time.monotonic()+3
                while self.asr._active is None and time.monotonic()<until:time.sleep(.005)
                self.assertIsNotNone(self.asr._active)
                self.service.microphone_stop({'capture_id':lease['capture_id']}); thread.join(3)
                self.assertFalse(thread.is_alive()); self.assertEqual(errors,['CANCELLED'])
                cancel.assert_not_called(); self.assertTrue(children and all(child.poll() is not None for child in children))
                self.assertFalse(self.service.microphone_leases); self.assertFalse(self.asr.data_dir.exists())
            finally:
                self.service.microphone_stop({'capture_id':lease['capture_id']}); thread.join(3)

    def test_close_invalidates_lease_and_safe_errors_never_echo_decoder_input(self):
        self.configure(); lease=self.begin()
        with patch.object(self.asr,'_execute',side_effect=SpeechError('PROCESS_FAILURE',self.secret)):
            with self.assertRaises(SpeechError) as caught:self.service.microphone_submit(self.payload(lease))
            self.assertNotIn(self.secret,str(caught.exception))
        lease=self.begin(); event=self.service.microphone_leases[lease['capture_id']]['cancelled']
        self.service.close(); self.assertTrue(event.is_set()); self.assertFalse(self.service.microphone_leases)
        self.assertEqual(self.service.microphone_stop({'capture_id':lease['capture_id']})['stopped'],True)

    def test_microphone_history_cap_preserves_other_sources_and_real_command_receipts(self):
        command=self.commands.prepare('axx.artifact.write',{'path':'receipt.txt','content':'synthetic fixture'},conversation_id='other-task')
        receipt=self.commands.execute(command['operation_id'],approved=True)
        self.assertTrue(receipt['postconditions_passed'])
        self.configure(retain=True)
        with self.service.db:
            self.service.db.execute('INSERT INTO anticipation_events VALUES (?,?,?,?)',
                ('folder-fixture','other-task',self.now,json.dumps({'source':'folders','history_kind':'context_observation_metadata'})))
        with patch('backend.anticipation.MAX_CONTEXT_SOURCE_EVENTS',2):
            for index in range(4):
                lease=self.begin()
                with patch.object(self.asr,'_execute',return_value={'text':self.secret+str(index),'audio_duration_seconds':1}):
                    self.service.microphone_submit(self.payload(lease))
                self.now+=31
        rows=[json.loads(row[0]) for row in self.service.db.execute('SELECT payload FROM anticipation_events')]
        self.assertEqual(len([row for row in rows if row.get('source')=='microphone']),2)
        self.assertTrue(any(row.get('source')=='folders' for row in rows))
        self.assertEqual(self.commands.get(command['operation_id'])['state'],'succeeded')
        self.assertEqual(self.executor.get_operation(receipt['action_operation_id'])['output']['sha256'],receipt['output']['sha256'])


class AnticipationMicrophoneHttpTests(MicrophoneFixture):
    def setUp(self):
        super().setUp(); self.configure()
        self.speech=Mock()
        handler=type('MicrophoneHandler',(AxxBridgeHandler,),{'anticipation':self.service,'speech':self.speech,'transcription':self.asr})
        self.server=ThreadedHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3); super().tearDown()

    def request(self,action,body,auth=True):
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer '+self.server.host_token
        request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/axx-api/anticipation/microphone/'+action,
            data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:
            with response:return response.code,json.load(response)

    def test_authenticated_begin_submit_and_scoped_stop_return_only_metadata(self):
        body={'target_id':'mic-local','task_id':'task-mic','project_id':'project-a'}
        self.assertEqual(self.request('begin',body,auth=False)[0],401)
        self.assertFalse(self.service.microphone_leases)
        code,lease=self.request('begin',body); self.assertEqual(code,200)
        with patch.object(self.asr,'_execute',return_value=self.result()):
            code,result=self.request('submit',self.payload(lease))
            self.assertEqual(code,200); self.assertTrue(result['accepted']); self.assertNotIn(self.secret,json.dumps(result))
        self.assertEqual(self.request('stop',{'capture_id':lease['capture_id']})[0],200)
        self.speech.cancel_active.assert_not_called()

    def test_busy_and_invalid_authority_do_not_create_or_preempt_lease(self):
        body={'target_id':'mic-local','task_id':'task-mic','project_id':'project-a'}
        with self.asr._busy:
            code,result=self.request('begin',body); self.assertEqual(code,409); self.assertEqual(result['error']['code'],'BUSY')
        self.assertFalse(self.service.microphone_leases)
        self.assertEqual(self.request('begin',body|{'allow_input':True})[0],400)
        code,lease=self.request('begin',body); self.assertEqual(code,200)
        self.assertEqual(self.request('submit',self.payload(lease)|{'context_owner':'forged'})[0],400)
        self.assertFalse(self.service.microphone_leases[lease['capture_id']]['submitted'])
        self.assertEqual(self.request('stop',{'capture_id':lease['capture_id'],'global':True})[0],400)


if __name__=='__main__':unittest.main()
