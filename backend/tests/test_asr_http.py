"""Attributed ASR routes preserve authenticated legacy cancellation without live audio."""
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.speech.offline_asr import OfflineTranscriptionService


class AttributedAsrHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=OfflineTranscriptionService(self.temp.name);self.service.model_path=Path(self.temp.name)
        self.speech=Mock();self.speech.cancel_active.return_value=1
        handler=type('AsrHandler',(AxxBridgeHandler,),dict(transcription=self.service,speech=self.speech))
        self.server=ThreadedHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.service.close();self.temp.cleanup()

    def request(self,path,body,*,authorized=True):
        headers={'Content-Type':'application/json'}
        if authorized:headers['Authorization']='Bearer '+self.server.host_token
        request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/axx-api/speech/'+path,
            data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:
            try:return response.code,json.load(response)
            finally:response.close()

    def test_specific_cancel_never_calls_tts_or_global_asr_cancel(self):
        with patch.object(self.service,'cancel',return_value=1) as cancel,patch.object(self.service,'cancel_active') as global_cancel:
            status,result=self.request('cancel',{'request_id':'clip-one'})
            self.assertEqual(status,200);self.assertTrue(result['cancelled'])
            cancel.assert_called_once_with('clip-one')
            global_cancel.assert_not_called();self.speech.cancel_active.assert_not_called()
        with patch.object(self.service,'cancel_active',return_value=1) as global_cancel:
            status,result=self.request('cancel',{})
            self.assertEqual(status,200);self.assertEqual(result['cancelled_operations'],2)
            global_cancel.assert_called_once();self.speech.cancel_active.assert_called_once()

    def test_request_id_passes_through_but_context_authority_is_not_json(self):
        body={'request_id':'clip-one','audio_base64':base64.b64encode(b'RIFF0000WAVEdata').decode(),'mime':'audio/wav'}
        with patch.object(self.service,'status',return_value={'available':True}), \
                patch.object(self.service,'_execute',return_value={'text':'synthetic local transcript'}) as execute:
            status,result=self.request('transcribe',body)
            self.assertEqual(status,200);self.assertEqual(result['request_id'],'clip-one')
            self.assertEqual(result['text'],'synthetic local transcript')
            self.assertEqual(execute.call_args.kwargs['_context'].request_id,'clip-one')
            self.assertIsNone(execute.call_args.kwargs['_context'].context_owner)
            for extra in ({'context_owner':'forged'},{'deadline_mono':1}):
                self.assertEqual(self.request('transcribe',body|extra)[0],400)
            self.assertEqual(execute.call_count,1)
        self.assertFalse(self.service.data_dir.exists())

    def test_cancel_input_and_host_guards_do_not_reach_other_speech(self):
        for body in ({'request_id':True},{'request_id':'../bad'},{'request_id':'clip','context_owner':'forged'}):
            with self.subTest(body=body):self.assertEqual(self.request('cancel',body)[0],400)
        self.assertEqual(self.request('cancel',{'request_id':'clip'},authorized=False)[0],401)
        self.speech.cancel_active.assert_not_called()


if __name__=='__main__':unittest.main()
