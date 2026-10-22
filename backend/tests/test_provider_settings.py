import json
import os
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import unittest
from unittest.mock import patch

from backend.inference import provider_settings as settings
from backend.inference.adapter import InferenceAdapter
from backend.inference.router import Router, http_transport


class ProviderSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'providers.json'
        self.adapter = InferenceAdapter({'allow_paid': False, 'providers': []}, Path(self.tmp.name) / 'state.db')
        self.env = dict(os.environ)

    def tearDown(self):
        self.adapter.close()
        os.environ.clear(); os.environ.update(self.env)
        self.tmp.cleanup()

    def save(self, **kwargs):
        return settings.save(dict(provider='ollama', name='Local', model='model-a', **kwargs), self.adapter, self.path)

    def test_ip_normalization_and_invalid_endpoints(self):
        self.assertEqual(settings.endpoint('192.168.1.20:11434', 'ollama'), 'http://192.168.1.20:11434/v1')
        self.assertEqual(settings.endpoint('http://[::1]:11434', 'ollama'), 'http://[::1]:11434/v1')
        for url in ['http://example.com', 'http://169.254.169.254', 'https://key@example.com', 'https://example.com?key=x']:
            with self.assertRaises(ValueError): settings.endpoint(url, 'custom')

    def test_local_without_key_and_persistent_configuration(self):
        self.save(base_url='192.168.1.20:11434')
        self.assertEqual(self.adapter.get_status()['providers'][0]['state'], 'ready_locally')
        self.assertEqual(json.loads(self.path.read_text())['providers'][0]['model'], 'model-a')
        self.assertFalse(settings.public_entries(self.adapter.config)[0]['has_key'])

    def test_remote_billing_is_explicit_not_marked_free(self):
        settings.save({'provider':'anthropic','name':'Claude','model':'claude-test'}, self.adapter, self.path)
        p = self.adapter.config['providers'][0]
        self.assertFalse(p['free_confirmed'])
        self.assertEqual(self.adapter.get_status()['providers'][0]['state'], 'free_not_confirmed')
        settings.save({'provider':'anthropic','name':'Claude','model':'claude-test','billing_allowed':True}, self.adapter, self.path)
        self.assertEqual(self.adapter.get_status()['providers'][0]['state'], 'missing_key')

    @unittest.skipUnless(os.name == 'nt', 'DPAPI requires Windows')
    def test_key_encrypted_reload_and_no_endpoint_reuse(self):
        self.save(api_key='TEST-ONLY-SECRET')
        env = self.adapter.config['providers'][0]['api_key_env']
        self.assertNotIn(b'TEST-ONLY-SECRET', next(settings.credentials_dir(self.path).glob('*.bin')).read_bytes())
        self.assertNotIn('TEST-ONLY-SECRET', self.path.read_text())
        del os.environ[env]; settings.load_credentials(self.path)
        self.assertEqual(os.environ[env], 'TEST-ONLY-SECRET')
        with self.assertRaises(ValueError): self.save(base_url='https://different.example/v1')
        self.assertNotIn('api_key_env', settings.public_entries(self.adapter.config)[0])

    def test_exact_selected_model_and_no_silent_fallback(self):
        self.save()
        settings.save({'provider':'ollama','name':'Second','model':'model-b'}, self.adapter, self.path)
        calls=[]
        def transport(p, body, timeout):
            calls.append(p['model'])
            return {'choices':[{'message':{'role':'assistant','content':'ok'}}]}
        self.adapter.router.transport=transport
        result=self.adapter.route({'model':'model-b','messages':[{'role':'user','content':'hello'}]})
        self.assertTrue(result['ok']); self.assertEqual(calls,['model-b'])
        result=self.adapter.route({'model':'missing','messages':[{'role':'user','content':'hello'}]})
        self.assertFalse(result['ok']); self.assertEqual(calls,['model-b'])

    def test_anthropic_transport_and_model_discovery(self):
        observed={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                observed['get']=self.path
                self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"claude-test"}]}')
            def do_POST(self):
                observed.update(path=self.path, body=json.loads(self.rfile.read(int(self.headers['Content-Length']))), key=self.headers.get('x-api-key'), version=self.headers.get('anthropic-version'))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"content":[{"type":"text","text":"hello"}],"stop_reason":"end_turn"}')
        server=HTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/v1'
            os.environ['TEST_PROVIDER_KEY']='test-only'
            result=http_transport({'base_url':url,'protocol':'anthropic','api_key_env':'TEST_PROVIDER_KEY'}, {'model':'claude-test','messages':[{'role':'system','content':'system rules'},{'role':'user','content':'hi'}],'stream':False}, 3)
            self.assertEqual(result['choices'][0]['message']['content'],'hello')
            self.assertEqual(observed['path'],'/v1/messages'); self.assertEqual(observed['key'],'test-only')
            self.assertEqual(observed['body']['system'],'system rules');self.assertEqual(len(observed['body']['messages']),1)
            self.assertEqual(settings.discover({'provider':'anthropic','base_url':url},self.adapter.config)['models'],['claude-test'])
        finally:
            server.shutdown();server.server_close()

    def test_cannot_save_while_request_active(self):
        self.adapter.active_requests['test']=object()
        with self.assertRaises(ValueError): self.save()
        self.adapter.active_requests.clear()

    def test_same_model_preserves_verified_capabilities(self):
        self.save()
        self.adapter.config['providers'][0]['capabilities'] = ['text', 'vision']
        self.save()
        self.assertEqual(self.adapter.config['providers'][0]['capabilities'], ['text', 'vision'])
        settings.save({'provider': 'ollama', 'name': 'Local', 'model': 'another-model'}, self.adapter, self.path)
        self.assertEqual(self.adapter.config['providers'][0]['capabilities'], ['text'])

    def test_rejects_key_in_model_field(self):
        with self.assertRaisesRegex(ValueError, 'clave de API'):
            settings.save({'provider':'ollama_cloud', 'name':'cloud', 'model':'a'*32+'.'+'B'*24}, self.adapter, self.path)

    def test_same_model_uses_only_selected_connection(self):
        self.save()
        settings.save({'provider':'ollama','name':'Second','model':'model-a'}, self.adapter, self.path)
        calls=[]
        def transport(p, body, timeout):
            calls.append(p['name'])
            return {'choices':[{'message':{'role':'assistant','content':'ok'}}]}
        self.adapter.router.transport=transport
        result=self.adapter.route({'model':'model-a','provider_name':'Second','messages':[{'role':'user','content':'hello'}]})
        self.assertTrue(result['ok']); self.assertEqual(calls,['Second'])

    def test_ollama_null_catalog_is_empty(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"object":"list","data":null}'
        with patch.object(settings.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(settings.discover({'provider':'ollama'}, {'providers':[]}), {'models':[]})

    def test_ollama_cloud_uses_native_catalog_and_filters_non_chat_models(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'models':[
            {'name':'cloud-chat','capabilities':['completion','thinking']},
            {'name':'embed-only','capabilities':['embedding']},
            {'name':'cloud-chat','capabilities':['completion']}
        ]}).encode()
        with patch.object(settings.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            result = settings.discover({'provider':'ollama_cloud'}, {'providers':[]})
            self.assertEqual(result, {'models':['cloud-chat']})
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url, 'https://ollama.com/api/tags')

    def test_ollama_native_local_catalog(self):
        from unittest.mock import MagicMock
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"models":[{"name":"local-model:4b"}]}'
        with patch.object(settings.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value=response
            self.assertEqual(settings.discover({'provider':'ollama'}, {'providers':[]}), {'models':['local-model:4b']})
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url, 'http://127.0.0.1:11434/api/tags')

if __name__ == '__main__': unittest.main()
