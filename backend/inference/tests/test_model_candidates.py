import copy
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from backend.inference.adapter import InferenceAdapter
from backend.inference.router import Router, profile_id
from backend.inference.model_candidates import ModelCandidates, _fixture, _valid_result


class ModelCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.provider = dict(name='Groq saved', kind='groq', model='openai/gpt-oss-120b',
            base_url='https://api.groq.com/openai/v1', api_key_env='CANDIDATE_TEST_KEY',
            enabled=True, free_confirmed=True, billing_allowed=False, cost_evidence='free_tier',
            route_kind='direct', capabilities=['text'], tasks=['parameters'], context_window=32768,daily_attempt_limit=100)
        self.config = {'providers':[self.provider]}
        self.calls = []
        self.answer = '{"pid":4242}'
        def transport(provider, payload, timeout):
            self.calls.append(provider['name'])
            return {'model':provider['model'], 'choices':[{'message':{'role':'assistant','content':self.answer}}]}
        self.adapter = InferenceAdapter(self.config, self.root/'state.db', router_instance=Router(self.config, self.root/'state.db', transport=transport))
        self.addCleanup(self.adapter.close)
        self.env = patch.dict(os.environ, {'CANDIDATE_TEST_KEY':'offline-test'}); self.env.start(); self.addCleanup(self.env.stop)
        self.discovery = patch('backend.inference.model_candidates.provider_settings.discover', return_value={'models':[self.provider['model']]})
        self.discovery.start(); self.addCleanup(self.discovery.stop)
        self.service = ModelCandidates(self.adapter); self.addCleanup(lambda:self.service.close())

    def test_seeds_are_unverified_and_catalog_does_not_activate_or_infer(self):
        before=copy.deepcopy(self.config)
        catalog=self.service.catalog()
        self.assertEqual(len(catalog['candidates']),6)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.config,before)
        self.assertTrue(all(not p for p in catalog['suggested_profiles'].values()))
        seed=next(c for c in catalog['candidates'] if c['provider']=='groq')
        self.assertEqual(seed['status'],'discovered')

    def test_evaluation_pins_exact_free_route_and_persists_proof(self):
        result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(result['passed']); self.assertEqual(result['proof_mode'],'simulated')
        self.assertEqual(self.calls,['Groq saved'])
        self.assertEqual(result['logical_requests'],1)
        self.service.close(); self.service=ModelCandidates(self.adapter)
        candidate=next(c for c in self.service.catalog()['candidates'] if c['provider']=='groq')
        self.assertEqual(candidate['evaluations'][0]['evaluation_id'],result['evaluation_id'])
        # Offline transport evidence must not make an automatic production suggestion.
        self.assertEqual(self.service.catalog()['suggested_profiles']['parameters'],[])

    def test_missing_credentials_or_catalog_or_paid_route_never_calls_model(self):
        for mutation in ('key','catalog','paid'):
            with self.subTest(mutation=mutation):
                context = patch.dict(os.environ, {'CANDIDATE_TEST_KEY':''}) if mutation=='key' else patch('backend.inference.model_candidates.provider_settings.discover',return_value={'models':[]}) if mutation=='catalog' else patch.dict(self.provider, billing_allowed=True)
                with context:
                    result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
                    self.assertEqual(result['status'],'pending'); self.assertEqual(result['logical_requests'],0)
        self.assertEqual(self.calls,[])

    def test_wrong_parameters_fail_without_effect_and_inputs_cannot_override_prompt(self):
        self.answer='{"pid":1,"script":"remove all"}'
        result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertFalse(result['passed']); self.assertEqual(result['corrections_required'],1); self.assertEqual(result['corrections'],0)
        with self.assertRaises(ValueError):
            self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters','messages':[]})

    def test_unknown_new_model_is_discovered_but_never_automatically_enabled(self):
        self.provider['model']='new-observed-model'
        with patch('backend.inference.model_candidates.provider_settings.discover',return_value={'models':['new-observed-model']}):
            catalog=self.service.catalog()
        new=next(c for c in catalog['candidates'] if c['model_id']=='new-observed-model')
        self.assertEqual(new['status'],'discovered'); self.assertEqual(new['source'],'discovered')
        self.assertFalse(any(catalog['suggested_profiles'].values()))

    def test_gateway_members_change_profile_identity(self):
        provider=dict(self.provider,kind='freellmapi',gateway_member_ids=[1,2])
        self.assertNotEqual(profile_id(provider),profile_id(dict(provider,gateway_member_ids=[1,3])))
        self.assertEqual(profile_id(provider),profile_id(dict(provider,gateway_member_ids=[2,1])))

    def test_every_task_uses_strict_representative_fixture_and_code_is_never_executed(self):
        for task in ('plan','repair','parameters','chat','writing','translation','vision'):
            messages,expected=_fixture(task)
            self.assertTrue(_valid_result(task,{'content':json.dumps(expected)},expected))
            self.assertFalse(_valid_result(task,{'content':'{"script":"unapproved"}'},expected))
        messages,expected=_fixture('vision')
        png=base64.b64decode(messages[1]['content'][1]['image_url']['url'].split(',')[1])
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        _,expected=_fixture('code')
        answer={'code':'def even_squares(values):\n return [x*x for x in values if x%2==0]','result':[4,16]}
        self.assertTrue(_valid_result('code',{'content':json.dumps(answer)},expected))
        answer['code']='import os\nos.remove("some-file")'
        self.assertFalse(_valid_result('code',{'content':json.dumps(answer)},expected))

    def test_production_json_fence_normalization_preserves_exact_fixture_validation(self):
        self.answer='```json\n{"pid":4242}\n```'
        result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(result['passed']); self.assertEqual(result['corrections'],1)
        self.assertTrue(result['identity_passed']); self.assertTrue(result['fixture_passed'])
        self.answer='```json\n{"pid":4242,"script":"unsafe"}\n```'
        result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertFalse(result['passed']); self.assertEqual(result['result_summary'],'REPRESENTATIVE_FIXTURE_MISMATCH')

    def test_actual_worker_evaluation_records_evidence_and_applies_only_verified_priority(self):
        observed=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                observed.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                payload=json.dumps({'model':'openai/gpt-oss-120b','choices':[{'message':{'role':'assistant','content':'{"pid":4242}'}}]}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(payload)
        server=HTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        config={'providers':[dict(self.provider,base_url=f'http://127.0.0.1:{server.server_port}/v1',cost_evidence='direct_local')]}
        adapter=InferenceAdapter(config,self.root/'actual.db'); self.addCleanup(adapter.close)
        config_path=self.root/'providers.json'
        service=ModelCandidates(adapter,state_path=self.root/'actual-evaluations.db',config_path=config_path); self.addCleanup(service.close)
        result=service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['proof_mode'],'actual'); self.assertEqual(len(observed),1)
        self.assertEqual(adapter.record_outcome(result['route'],'parameters','succeeded')['succeeded'],1)
        self.assertEqual(service.catalog()['suggested_profiles']['parameters'][0]['candidate_id'],'groq-gpt-oss-120b')
        applied=service.apply({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(applied['ok']); self.assertEqual(json.loads(config_path.read_text())['providers'][0]['task_priority'],{'parameters':0})
        self.assertEqual(len(observed),1)
        adapter.config['providers'][0]['model']='changed'
        with self.assertRaises(ValueError):
            service.apply({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})

    def test_simulated_success_cannot_be_applied(self):
        self.service.config_path=self.root/'providers.json'
        self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        with self.assertRaises(ValueError):
            self.service.apply({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertFalse(self.service.config_path.exists())

    def test_candidate_failure_cannot_fall_back_to_another_connection(self):
        other=dict(self.provider,name='Other',model='other-model')
        self.adapter.config['providers'].append(other)
        from backend.inference.router import UpstreamError
        def unavailable(provider,payload,timeout):
            self.calls.append(provider['name'])
            raise UpstreamError(503,message='fixture unavailable')
        self.adapter.router.transport=unavailable
        result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertFalse(result['passed'])
        self.assertEqual(self.calls,['Groq saved'])

    def test_trusted_direct_local_candidate_does_not_require_remote_api_key(self):
        self.provider.update(base_url='http://127.0.0.1:9988/v1',cost_evidence='direct_local',auth_optional=True)
        with patch.dict(os.environ,{'CANDIDATE_TEST_KEY':''}):
            result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(result['passed'],result)

    def test_staged_candidate_cannot_route_normally_but_exact_evaluation_can(self):
        self.provider['candidate_only']=True
        request={'messages':[{'role':'user','content':'hello'}],'task':'parameters'}
        for mode in ('manual','automatic_free'):
            result=self.adapter.route(dict(request,selection_mode=mode))
            self.assertFalse(result['ok']); self.assertFalse(result['error']['upstream_attempted'])
        self.assertEqual(self.calls,[])
        self.assertTrue(self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})['passed'])
        self.assertTrue(self.provider['candidate_only'])

    def test_gateway_catalog_maps_real_native_and_db_ids_then_isolates_only_for_evaluation(self):
        self.provider.update(kind='freellmapi',model='auto:axx_parameters',route_kind='proxy',gateway_profile_verified=True,
            gateway_attempt_limit=3,gateway_free_model_ids=[11,12],gateway_member_ids=[11,12])
        gateway=Mock()
        gateway.candidate_catalog.return_value={'models':[{'id':11,'platform':'Axx imported','provider_kind':'groq',
            'modelId':'openai/gpt-oss-120b','contextWindow':32768,'enabled':True,'group_ready':True,
            'group_member_ids':[11],'canonical_id':'gpt-oss-canonical'}]}
        self.service.gateway=gateway
        override=dict(self.provider,model='auto:axx_e_p_012345678901',gateway_free_model_ids=[11],gateway_member_ids=[11],tasks=['parameters'])
        with patch('backend.inference.freellmapi.evaluation_provider',return_value=override) as isolate, patch('backend.inference.freellmapi.verify_provider',return_value=override):
            catalog=self.service.catalog()
            matched=next(c for c in catalog['candidates'] if c['provider']=='groq')['matched_routes'][0]
            self.assertEqual(matched['native_model_id'],'openai/gpt-oss-120b')
            self.assertEqual(matched['canonical_id'],'gpt-oss-canonical')
            self.assertEqual(matched['gateway_model_ids'],[11]); isolate.assert_not_called()
            # Synthetic transport explicitly reports the requested underlying model.
            self.adapter.router.transport=lambda p,r,timeout: {'model':'openai/gpt-oss-120b','choices':[{'message':{'role':'assistant','content':'{"pid":4242}'}}]}
            result=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
            self.assertTrue(result['passed'],result)
            self.assertEqual(isolate.call_args.args[1:],([11],'parameters'))
            self.assertEqual(self.provider['model'],'auto:axx_parameters')
            self.assertEqual(self.provider['gateway_member_ids'],[11,12])
            # Trusted stored-evidence fixture for the independent apply transaction.
            stored=dict(result,proof_mode='actual')
            with self.service.db:
                self.service.db.execute('UPDATE model_evaluations SET result_json=? WHERE evaluation_id=?',(json.dumps(stored),result['evaluation_id']))
            self.service.config_path=self.root/'providers.json'
            applied=self.service.apply({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
            self.assertTrue(applied['ok'])
            entries=json.loads(self.service.config_path.read_text())['providers']
            self.assertEqual(entries[0]['gateway_member_ids'],[11,12])
            self.assertEqual(entries[1]['gateway_member_ids'],[11])
            self.assertEqual(entries[1]['quota_scope_id'],'Groq saved')
            self.assertEqual(entries[1]['tasks'],['parameters'])
            self.assertFalse(entries[1]['candidate_only'])

    def test_keyless_preparation_preserves_user_config_and_hides_private_fields(self):
        self.service.config_path=self.root/'providers.json'
        source=dict(self.provider,name='Anonymous stage',kind='freellmapi',model='auto:axx_parameters',route_kind='proxy',
            candidate_only=True,gateway_keyless=True,gateway_profile_verified=True,gateway_attempt_limit=3,gateway_free_model_ids=[11],
            gateway_dashboard_env='AXX_API_PRIVATE_DASH')
        self.service.gateway=Mock()
        self.service.gateway.bootstrap_keyless.return_value={'providers':[source],'status':'discovered','evidence':[]}
        result=self.service.prepare_keyless()
        self.assertEqual(result['providers'],['Anonymous stage'])
        self.assertNotIn('AXX_API_PRIVATE_DASH',json.dumps(result))
        saved=json.loads(self.service.config_path.read_text())['providers']
        self.assertEqual(saved[0]['name'],'Groq saved'); self.assertTrue(saved[1]['candidate_only'])

    def test_bootstrap_is_bounded_and_persists_pending_backoff(self):
        result=self.service.bootstrap('parameters')
        self.assertEqual(result['status'],'pending') # simulated proof cannot activate
        self.assertEqual(len(result['evaluations']),0) # personal routes require the explicit evaluate button
        again=self.service.bootstrap('parameters')
        self.assertEqual(again['status'],'backoff'); self.assertEqual(len(self.calls),0)

    def test_exact_evaluation_retains_tighter_shared_account_quota(self):
        self.provider.update(quota_scope_id='same-account',daily_attempt_limit=100)
        self.config['providers'].append(dict(self.provider,name='Sibling',model='other',scope_limit=1))
        # Router holds the same config provider list, including the sibling account constraint.
        first=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        second=self.service.evaluate({'candidate_id':'groq-gpt-oss-120b','task':'parameters'})
        self.assertTrue(first['passed']); self.assertEqual(second['status'],'pending')
        self.assertEqual(second['logical_requests'],0); self.assertEqual(len(self.calls),1)

    def bootstrap_catalog(self,count):
        return {'suggested_profiles':{'plan':[]},'candidates':[{'id':str(i),'provider':'keyless-'+str(i),
            'priority':50,'tasks':['plan'],'evaluations':[],
            'matched_routes':[{'name':'route-'+str(i),'profile_id':'profile-'+str(i),'tasks':['plan'],
                'gateway_keyless':True,'capabilities':['text'],'context_window':32768}]} for i in range(count)]}

    def test_bootstrap_moves_past_recent_failed_candidates_and_never_exceeds_two(self):
        catalog=self.bootstrap_catalog(4)
        calls=[]
        def evaluate(body):
            calls.append(body['candidate_id'])
            c=next(c for c in catalog['candidates'] if c['id']==body['candidate_id'])
            result={'task':'plan','proof_mode':'actual','passed':False,'status':'failed','latency_ms':10,'fixture_version':2,
                'corrections_required':1,'catalog_route_id':c['matched_routes'][0]['profile_id'],'evaluated_at':time.time()}
            c['evaluations'].insert(0,result)
            return result
        with patch.object(self.service,'catalog',return_value=catalog),patch.object(self.service,'evaluate',side_effect=evaluate):
            first=self.service.bootstrap('plan',force=True)
            second=self.service.bootstrap('plan',force=True)
        self.assertEqual(len(first['evaluations']),2); self.assertEqual(len(second['evaluations']),2)
        self.assertEqual(len(set(calls)),4)

    def test_bootstrap_reuses_success_then_force_tests_only_one_challenger(self):
        catalog=self.bootstrap_catalog(3)
        catalog['candidates'][0]['evaluations']=[{'task':'plan','proof_mode':'actual','passed':True,'status':'passed','fixture_version':2,
            'latency_ms':10,'corrections_required':0,'catalog_route_id':'profile-0','evaluated_at':time.time()}]
        with patch.object(self.service,'catalog',return_value=catalog),patch.object(self.service,'evaluate',return_value={'status':'pending'}) as evaluate,patch.object(self.service,'apply',return_value={'ok':True}):
            self.assertTrue(self.service.bootstrap('plan')['reused']); evaluate.assert_not_called()
            result=self.service.bootstrap('plan',force=True)
            self.assertEqual(len(result['evaluations']),1); evaluate.assert_called_once()
            self.assertNotEqual(evaluate.call_args.args[0]['candidate_id'],'0')

    def test_shutdown_before_prepare_never_restarts_gateway_setup(self):
        self.service.config_path=self.root/'providers.json'
        self.service.gateway=Mock()
        self.service.cancel_active()
        self.assertEqual(self.service.prepare_keyless(force=True)['status'],'cancelled')
        self.service.gateway.bootstrap_keyless.assert_not_called()

if __name__=='__main__': unittest.main()
