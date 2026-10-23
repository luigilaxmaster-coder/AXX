import base64
import tempfile
import time
import unittest
from pathlib import Path
from backend.mobile.trust_store import MobileTrustStore
from backend.mobile.shared_state import SharedState
from backend.mobile.voice import RemoteVoice


class RemoteVoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'state.db'
        self.store=MobileTrustStore(path);self.shared=SharedState(path)
        self.device=self.store.consume_pairing(self.store.create_pairing(),'Android')['device_id']
        self.now=100.;self.calls=[]
        def backend(method,path,body):
            self.calls.append(path);return {'text':'calcula dos más dos','engine':'faster-whisper','input_sha256':'test'}
        self.backend=backend
        self.voice=RemoteVoice(self.store,self.shared,backend,lambda:self.now)
        self.body={'device_id':self.device,'mode':'confirm','max_seconds':20,'conversation_id':self.shared.snapshot()['conversation_id']}
        self.poll={'visible':True,'permission':'granted','capture':{'state':'idle'}}
        self.voice.poll(self.device,self.poll)

    def test_phone_start_requires_permission_and_confirmation_is_device_bound(self):
        self.voice.poll(self.device,{**self.poll,'permission':'denied'})
        with self.assertRaises(ValueError):self.voice.phone_start(self.device,{'language':'es'})
        self.voice.poll(self.device,self.poll)
        session=self.voice.phone_start(self.device,{'language':'en'})
        self.assertEqual(session['language'],'en');self.assertEqual(session['mode'],'confirm')
        with self.assertRaises(ValueError):self.voice.phone_start(self.device,{'language':'es'})
        self.voice.session.update(state='review',text='Open calculator')
        with self.assertRaises(ValueError):self.voice.confirm(session['session_id'],'Open calculator','another-device')
        with self.assertRaises(ValueError):self.voice.confirm(session['session_id'],'Open calculator',self.device)
        self.store.set_tool_permission(self.device,True)
        self.assertEqual(self.voice.confirm(session['session_id'],'Open calculator',self.device)['state'],'ready')

    def capture(self,mode='confirm'):
        s=self.voice.toggle({**self.body,'mode':mode});sid=s['session_id']
        self.voice.poll(self.device,{**self.poll,'capture':{'state':'recording','session_id':sid}})
        self.assertEqual(self.voice.toggle(self.body)['state'],'stopping')
        self.voice.poll(self.device,{**self.poll,'capture':{'state':'stopped','session_id':sid,'reason':'pc_stop'}})
        body={'session_id':sid,'mime':'audio/mp4','audio_base64':base64.b64encode(b'\0\0\0\x18ftyp' + b'fixture-audio').decode()}
        self.voice.audio(self.device,body)
        for _ in range(100):
            if self.voice.status()['session']['state']!='transcribing':break
            time.sleep(.005)
        return sid,body

    def test_confirmed_text_dispatches_once_through_desktop(self):
        sid,audio=self.capture()
        self.assertEqual(self.voice.status()['session']['state'],'review')
        self.assertFalse(self.voice.claim(sid,self.body['conversation_id'])['execute'])
        self.voice.audio(self.device,audio);self.assertEqual(self.calls,['/axx-api/speech/transcribe'])
        self.voice.confirm(sid,'calcula 2 + 2')
        self.assertTrue(self.voice.claim(sid,self.body['conversation_id'])['execute'])
        self.assertFalse(self.voice.claim(sid,self.body['conversation_id'])['execute'])
        self.voice.finish(sid,{'text':'4'})
        self.assertEqual(self.voice.status()['session']['result'],{'text':'4'})

    def test_foreground_permission_and_handsfree_requirements(self):
        with self.assertRaises(ValueError):self.voice.toggle({**self.body,'mode':'handsfree'})
        self.store.set_tool_permission(self.device,True)
        self.voice.poll(self.device,{**self.poll,'permission':'denied'})
        with self.assertRaises(ValueError):self.voice.toggle(self.body)
        self.voice.poll(self.device,{**self.poll,'visible':False})
        with self.assertRaises(ValueError):self.voice.toggle(self.body)

    def test_stop_before_capture_acknowledgement_finishes_without_audio(self):
        self.voice.toggle(self.body)
        self.voice.toggle(self.body)
        result=self.voice.poll(self.device,self.poll)
        self.assertEqual(result['session']['state'],'empty')
        self.assertEqual(self.calls,[])

    def test_loss_and_restart_do_not_repeat_actions(self):
        s=self.voice.toggle(self.body);self.now+=9
        self.assertEqual(self.voice.status()['session']['state'],'interrupted')
        self.voice.cancel(s['session_id'])
        self.voice.poll(self.device,self.poll);self.store.set_tool_permission(self.device,True)
        sid,_=self.capture('handsfree')
        self.assertTrue(self.voice.claim(sid,self.body['conversation_id'])['execute'])
        recovered=RemoteVoice(self.store,self.shared,self.backend,lambda:self.now)
        self.assertEqual(recovered.status()['session']['state'],'outcome_unknown')
        self.assertFalse(recovered.claim(sid,self.body['conversation_id'])['execute'])
        recovered.finish(sid,{'text':'Resultado recuperado, no una nueva ejecución'})
        self.assertEqual(recovered.status()['session']['state'],'completed')

    def test_audio_and_sessions_are_bound_to_device(self):
        sid,_=self.capture()
        with self.assertRaises(ValueError):self.voice.cancel(sid,'another-device')
        self.store.revoke(self.device)
        self.voice.confirm(sid,'hola')
        with self.assertRaises(ValueError):self.voice.claim(sid,self.body['conversation_id'])
