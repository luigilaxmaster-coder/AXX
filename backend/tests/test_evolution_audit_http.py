"""Regression tests for actual Evolution HTTP storage, conflicts and trust boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.tests.test_evolution3_full_functional_audit import _start_bound_server, _stop_bound_server, _HttpTestClient
from backend.tests import test_motion_studio


class EvolutionAuditHttpTests(unittest.TestCase):
    def test_draft_http_limits_cas_and_recovery_cleanup_when_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);project=root/'project';project.mkdir();target=project/'large.py'
            target.write_text('A'*1024*1024,encoding='utf-8')
            services=_start_bound_server(root/'state.db',root/'runtime')
            try:
                rt=services[0].evolution_runtime;rt.flags.set_flag('code_studio_v1',True,reason='draft regression')
                api=_HttpTestClient(services[0].server_port,services[0].host_token)
                self.assertEqual(api.request('POST','/axx-api/code/v1/projects/register',{'project_id':'p','project_root':str(project)})[0],200)
                doc=rt.code_projects.read_document('p','large.py')
                body={'project_id':'p','path':'large.py','content':'\t'*1024*1024,'expected_revision':0,
                      'base_content':doc['content'],'base_sha256':doc['sha256'],'encoding':doc['encoding'],'line_ending':doc['line_ending']}
                code,result=api.request('POST','/axx-api/code/v1/drafts/save',body)
                self.assertEqual(code,200,result);self.assertEqual(result['revision'],1)
                self.assertEqual(target.read_text(),doc['content'])
                self.assertEqual(api.request('POST','/axx-api/code/v1/drafts/save',body)[0],409)
                self.assertEqual(api.request('POST','/axx-api/code/v1/drafts/save',{'project_id':'p','path':'large.py','expected_revision':1})[0],400)
                self.assertEqual(api.request('GET','/axx-api/code/v1/drafts?project_id=p&path=large.py')[1]['revision'],1)
                code,result=api.request('POST','/axx-api/code/v1/documents/save',{'project_id':'p','path':'large.py','new_content':body['content'],'expected_sha256':doc['sha256']})
                self.assertEqual(code,200,result);self.assertEqual(target.read_text(),body['content'])
                # Leave a genuine I/O conflict for review, then disable dispatch.
                def external_change(path,payload):
                    Path(path).write_bytes(b'EXTERNAL\n');raise OSError('controlled conflict')
                with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=external_change):
                    with self.assertRaises(OSError):rt.code_projects.save_document('p','large.py','NEXT\n',expected_sha256=result['new_sha256'])
                rt.flags.set_flag('code_studio_v1',False,reason='cleanup regression')
                code,result=api.request('POST','/axx-api/code/v1/file-transactions/recover',{'project_id':'p'})
                self.assertEqual(code,200,result)
                pending=next(row for row in result['transactions'] if row['state']=='recovery_conflict')
                review={'transaction_id':pending['transaction_id'],'preserve_external':'true','expected_hashes':{f['path']:f['current_sha'] for f in pending['files']}}
                self.assertEqual(api.request('POST','/axx-api/code/v1/file-transactions/acknowledge',review)[0],400)
                review['preserve_external']=True
                self.assertEqual(api.request('POST','/axx-api/code/v1/file-transactions/acknowledge',review)[0],200)
                self.assertEqual(target.read_bytes(),b'EXTERNAL\n')
                self.assertEqual(api.request('POST','/axx-api/code/v1/drafts/save',body)[0],403)
            finally:_stop_bound_server(*services)

    def test_asset_http_contract_keeps_unknown_measurements_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);services=_start_bound_server(root/'state.db',root/'runtime')
            try:
                for flag in ('magic_scene_v2','asset_gate_mcp_v1'):
                    services[0].evolution_runtime.flags.set_flag(flag,True,reason='isolated asset test')
                api=_HttpTestClient(services[0].server_port,services[0].host_token)
                code,data=api.request('POST','/axx-api/spatial/v2/assets/register',
                    {'filename':'triangle.gltf','license_spdx':'MIT','provenance_source':'local',
                     'content_text':'{"asset":{"version":"2.0"},"scenes":[{"nodes":[]}],"nodes":[]}'})
                self.assertEqual(code,200,data)
                self.assertIsNone(data['asset']['dimensions_m'])
            finally:
                _stop_bound_server(*services)

    def test_scene_patch_undo_redo_and_restart_use_the_persistent_store(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            services = _start_bound_server(root / 'state.db', root / 'runtime')
            services[0].evolution_runtime.flags.set_flag('magic_scene_v2', True, reason='isolated scene test')
            try:
                api = _HttpTestClient(services[0].server_port, services[0].host_token)
                scene = test_motion_studio.MotionStudioTests()._sample_motion_scene()
                self.assertEqual(api.request('POST', '/axx-api/spatial/v2/scenes', {'scene':scene})[0], 200)
                patch = {'document_id':scene['document_id'],'base_revision':1,'operation_id':'patch-name',
                         'target_object_ids':['piston-1'],'allowed_paths':['name'],
                         'changes':[{'op':'object.update','object_id':'piston-1','fields':{'name':'Verified change'}}]}
                self.assertEqual(api.request('POST','/axx-api/spatial/v2/scenes/patch',{'patch':patch})[0],200)
                self.assertEqual(api.request('POST','/axx-api/spatial/v2/scenes/patch',{'patch':patch})[0],409)
                read = lambda: api.request('GET','/axx-api/spatial/v2/scenes?document_id=' + scene['document_id'])[1]
                self.assertEqual(read()['objects'][0]['name'],'Verified change')
                for action, expected in [('undo','Pistón Principal'),('redo','Verified change')]:
                    code, data = api.request('POST','/axx-api/spatial/v2/scenes/' + action,
                                            {'document_id':scene['document_id'],'operation_id':action + '-name'})
                    self.assertEqual(code,200,data)
                    self.assertEqual(read()['objects'][0]['name'],expected)
            finally:
                _stop_bound_server(*services)
            services = _start_bound_server(root / 'state.db',root / 'runtime')
            try:
                api = _HttpTestClient(services[0].server_port,services[0].host_token)
                self.assertEqual(read()['objects'][0]['name'],'Verified change')
                self.assertEqual(read()['revision'],4)
            finally:
                _stop_bound_server(*services)

    def test_invalid_exports_cannot_allocate_directories_and_flags_require_real_booleans(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); services=_start_bound_server(root/'state.db',root/'runtime')
            try:
                api=_HttpTestClient(services[0].server_port,services[0].host_token)
                code,data=api.request('POST','/axx-api/code/v1/projects/register',{'project_id':'off','project_root':str(root)})
                self.assertEqual(code,403,data)
                for flag in ('magic_scene_v2','cad_worker_v1','motion_worker_v1'):
                    services[0].evolution_runtime.flags.set_flag(flag, True, reason='isolated negative test')
                for path,body in [('/axx-api/spatial/v2/cad/build',{'task':{'task_id':'../../escaped'}}),
                                  ('/axx-api/spatial/v2/motion/export-mp4',{'scene':{'document_id':'../../escaped'}})]:
                    code,data=api.request('POST',path,body)
                    self.assertEqual(code,400,data)
                self.assertFalse((root/'escaped').exists())
                self.assertFalse((root/'runtime/evolution3/cad_outputs').exists())
                code,data=api.request('POST','/axx-api/agents/v1/flags/set',
                    {'flag_id':'code_studio_v1','expected_revision':1,'enabled':'false'})
                self.assertEqual(code,400,data)
                self.assertFalse(services[0].evolution_runtime.flags.is_enabled('code_studio_v1'))
            finally:
                _stop_bound_server(*services)
