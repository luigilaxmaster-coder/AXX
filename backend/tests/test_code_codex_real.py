"""Opt-in acceptance against the owner's already signed-in Codex account; no paid API credentials."""
import os
from pathlib import Path
import tempfile
import unittest

from backend.tests.test_acts_code_tools import BUGGY, TESTS, git_repo
from backend.tests.test_acts_inference import _Server, act_spec


@unittest.skipUnless(os.environ.get('AXX_REAL_CODEX')=='1','Opt-in existing Codex account')
class CodeCodexRealTests(unittest.TestCase):
    def test_real_dev_and_independent_qa_use_their_own_models_with_disk_test_and_review_receipts(self):
        from backend.connect.provider import CodexProvider
        from backend.connect.service import ConnectService
        from backend.memory.procedural_memory import ProceduralMemory
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root=Path(tmp);repo=git_repo(root);srv=_Server(root,[])
            memory=ProceduralMemory(root/'state.db')
            connect=ConnectService(srv.commands,memory)
            codex=CodexProvider(srv.commands,root/'state.db',root,dispatcher=connect.dispatch)
            srv.server.RequestHandlerClass.connect=connect
            srv.server.RequestHandlerClass.provider=codex
            try:
                info=codex.status();self.assertTrue(info['authenticated'],info.get('diagnostic'))
                baseline=codex.selected_model
                models=[m for m in info['models'] if m.startswith('gpt-')]
                dev=baseline;qa=next(m for m in models if m!=dev)
                for flag in ('agent_profiles_v1','code_studio_v1','code_execution_v1'):
                    srv.rt.flags.set_flag(flag,True,reason='real Codex code acceptance')
                srv.rt.code_projects.register_project('p',str(repo))
                for aid,name,model,ops in [('dev','Dev',dev,['worktree','patch','test','integrate']),('qa','QA',qa,['review'])]:
                    srv.rt.registry.create_profile(act_spec(aid,name,'Helix','axx-connect',model,role=name))
                    srv.rt.registry.grant_permission(agent_id=aid,grant_id='code-'+aid,tool_id='axx.code',
                        resource_pattern='p',operation_kinds=ops,approval_mode='ask')
                srv.api.timeout=300
                code,result=srv.api.request('POST','/axx-api/agents/v1/teams/run',{'run_id':'codex-real-code',
                    'conversation_id':'conv-real-code','act_ids':['dev','qa'],'prompt':'Dev corrige add para que sume a y b; QA verifica el diff y las pruebas.',
                    'project_id':'p','file_path':'calc.py','apply_in_worktree':True,'test_command':TESTS})
                self.assertEqual(code,200,result)
                self.assertEqual([s['model'] for s in result['steps']],[dev,qa])
                self.assertTrue(all(s['model_verified'] for s in result['steps']))
                work=result['work'];self.assertTrue(work['test_receipt']['passed'],work['test_receipt'])
                self.assertEqual(work['reviews'][-1]['reviewer_id'],'qa')
                self.assertEqual(work['reviews'][-1]['verdict'],'approved',work['reviews'])
                self.assertEqual((repo/'calc.py').read_text(),BUGGY)
                code,integrated=srv.api.request('POST','/axx-api/code/v1/worktrees/integrate',{
                    'act_id':'dev','changeset_id':work['changeset_id'],'test_report_ids':[work['test_receipt']['report_id']]})
                self.assertEqual(code,200,integrated)
                self.assertIn('a + b',(repo/'calc.py').read_text())
                self.assertEqual(codex.selected_model,baseline)
                print(f'Real Codex Dev={dev}, QA={qa}: disk patch, tests, independent approval and integration verified')
            finally:
                codex.close();connect.close();memory.close();srv.close()
