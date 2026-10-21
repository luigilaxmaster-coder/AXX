"""Screen endpoints retain host authentication and validate controls over real HTTP."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from backend.screen_recording import ScreenRecordingService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer

class ScreenHttpTests(unittest.TestCase):
    def test_authenticated_countdown_cancellation_and_validation(self):
        with tempfile.TemporaryDirectory() as root, patch('backend.screen_recording.desktop_bounds',return_value=(0,0,1920,1080)):
            recording=ScreenRecordingService(root)
            handler=type('ScreenHandler',(AxxBridgeHandler,),{'recording':recording})
            server=ThreadedHTTPServer(('127.0.0.1',0),handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(route,body=None,auth=True):
                headers={'Authorization':'Bearer '+server.host_token} if auth else {}
                headers['Content-Type']='application/json'
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/axx-api/screen/'+route,data=json.dumps(body).encode() if body is not None else None,headers=headers)
                try:
                    with urllib.request.urlopen(req,timeout=5) as res:return res.status,json.loads(res.read())
                except urllib.error.HTTPError as res:
                    try:return res.code,json.loads(res.read())
                    finally:res.close()
            try:
                self.assertEqual(request('status',auth=False)[0],401)
                self.assertEqual(request('start',{},auth=False)[0],401)
                self.assertEqual(request('status')[1]['state'],'ready')
                self.assertEqual(request('start',{'region':{'x':-1,'y':0,'width':200,'height':160}})[0],400)
                code,data=request('start',{'region':{'x':0,'y':0,'width':200,'height':160},'countdown':5})
                self.assertEqual(code,200)
                self.assertEqual(request('control',{'id':'stale','command':'stop'})[0],400)
                self.assertEqual(request('open',{'id':data['id'],'path':'arbitrary.exe'})[0],400)
                self.assertEqual(request('control',{'id':data['id'],'command':'stop'})[0],200)
                recording.close()
                self.assertEqual(request('status')[1]['state'],'ready')
            finally:
                server.shutdown();server.server_close();thread.join(2);recording.close()
