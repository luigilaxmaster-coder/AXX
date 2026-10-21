import json, os, tempfile, unittest
from pathlib import Path
from router import Router, UpstreamError, Exhausted, RequestError

class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['TEST_KEY'] = 'secret'
        self.calls = []
        self.responses = {}
    def tearDown(self): self.tmp.cleanup()
    def make(self, **overrides):
        cfg = {'providers': [{'name': n, 'base_url': 'https://example.com/v1', 'model': n,
            'api_key_env': 'TEST_KEY', 'free_confirmed': True, 'daily_attempt_limit': 10,
            'capabilities': ['text']} for n in ['a','b']]}
        cfg.update(overrides)
        def send(p, body, timeout):
            self.calls.append((p['name'], body))
            r = self.responses.get(p['name'], {'choices':[{'message':{'content':'ok'}}]})
            if isinstance(r, Exception): raise r
            return r
        return Router(cfg, Path(self.tmp.name)/'state.db', transport=send)
    def test_success_keeps_messages(self):
        r=self.make(); messages=[{'role':'user','content':'hola'}]
        self.assertEqual(r.chat({'messages':messages})['axx_router']['provider'],'a')
        self.assertEqual(self.calls[0][1]['messages'], messages)
    def test_quota_switches_and_persists_cooldown(self):
        self.responses['a']=UpstreamError(429, retry_after=600)
        r=self.make(); self.assertEqual(r.chat({'messages':[]})['axx_router']['provider'],'b')
        self.calls.clear(); self.make().chat({'messages':[]})
        self.assertEqual([x[0] for x in self.calls], ['b'])
    def test_auth_failure_switches(self):
        self.responses['a']=UpstreamError(401)
        self.assertEqual(self.make().chat({'messages':[]})['axx_router']['provider'],'b')
    def test_bad_request_is_not_retried(self):
        self.responses['a']=UpstreamError(400)
        with self.assertRaises(UpstreamError): self.make().chat({'messages':[]})
        self.assertEqual(len(self.calls),1)
    def test_all_exhausted_has_bounded_attempts(self):
        self.responses={n:UpstreamError(503) for n in ['a','b']}
        with self.assertRaises(Exhausted): self.make().chat({'messages':[]})
        self.assertEqual(len(self.calls),2)
    def test_local_daily_cap(self):
        r=self.make()
        r.providers[0]['daily_attempt_limit']=1
        r.chat({'messages':[]}); r.chat({'messages':[]})
        self.assertEqual([x[0] for x in self.calls],['a','b'])
    def test_no_unapproved_paid_provider(self):
        r=self.make(); r.providers[0]['free_confirmed']=False
        self.assertEqual(r.chat({'messages':[]})['axx_router']['provider'],'b')
    def test_tools_require_capability(self):
        with self.assertRaises(Exhausted): self.make().chat({'messages':[], 'tools':[{'type':'function'}]})
        self.assertEqual(self.calls,[])
    def test_missing_keys_skip(self):
        del os.environ['TEST_KEY']
        with self.assertRaises(Exhausted): self.make().chat({'messages':[]})
    def test_stream_rejected(self):
        with self.assertRaises(RequestError): self.make().chat({'messages':[], 'stream':True})
    def test_invalid_response_switches(self):
        self.responses['a']={'error':'broken'}
        self.assertEqual(self.make().chat({'messages':[]})['axx_router']['provider'],'b')
    def test_http_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            self.make(providers=[{'name':'x','base_url':'http://example.com','model':'x',
                'api_key_env':'TEST_KEY','free_confirmed':True,'daily_attempt_limit':1,'capabilities':['text']}])

    def test_output_limit_is_enforced(self):
        r=self.make(); r.providers[0]['max_output_tokens']=128
        r.chat({'messages':[], 'max_tokens':9000})
        self.assertEqual(self.calls[0][1]['max_tokens'],128)
    def test_negative_tokens_rejected(self):
        with self.assertRaises(RequestError): self.make().chat({'messages':[], 'max_tokens':-1})
        self.assertEqual(self.calls,[])
    def test_status_explains_local_quota(self):
        r=self.make(); r.providers[0]['daily_attempt_limit']=1
        r.chat({'messages':[]})
        state=r.status()['providers'][0]
        self.assertEqual(state['state'],'local_quota_exhausted')
        self.assertEqual(state['attempts_today'],1)
        self.assertNotIn('secret',json.dumps(r.status()))
    def test_reset_preserves_usage(self):
        self.responses['a']=UpstreamError(401)
        r=self.make(); r.chat({'messages':[]}); r.reset_cooldown('a')
        state=r.status()['providers'][0]
        self.assertEqual(state['state'],'ready')
        self.assertEqual(state['attempts_today'],1)
    def test_task_routes_to_matching_provider(self):
        r=self.make(); r.providers[0]['tasks']=['chat']; r.providers[1]['tasks']=['code']
        result=r.chat({'messages':[], 'axx_task':'code'})
        self.assertEqual(result['axx_router']['provider'],'b')
        self.assertNotIn('axx_task',self.calls[0][1])
    def test_metrics_count_failover(self):
        self.responses['a']=UpstreamError(429)
        r=self.make(); r.chat({'messages':[]})
        states=r.status()['providers']
        self.assertEqual(states[0]['metrics']['failures'],1)
        self.assertEqual(states[1]['metrics']['successes'],1)
    def test_request_size_limit(self):
        r=self.make(max_request_bytes=10)
        with self.assertRaises(RequestError): r.chat({'messages':[{'role':'user','content':'too long'}]})
    def test_privacy_filter(self):
        r=self.make(); r.providers[0]['allow_sensitive']=False; r.providers[1]['allow_sensitive']=True
        result=r.chat({'messages':[], 'axx_sensitive':True})
        self.assertEqual(result['axx_router']['provider'],'b')
        self.assertNotIn('axx_sensitive',self.calls[0][1])

if __name__ == '__main__': unittest.main()
