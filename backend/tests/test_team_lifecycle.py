"""A cancelled/retried team must not repeat real worktree effects or retain forgotten output."""
import threading
import time
import unittest
from unittest.mock import patch

from backend.agents.http_api import EvolutionHTTP
from backend.tests import test_acts_code_tools as fixtures
from backend.tests.test_acts_code_tools import BUGGY, TESTS


class TeamLifecycleTests(unittest.TestCase):
    setUp = fixtures.ActCodeToolsTests.setUp
    tearDown = fixtures.ActCodeToolsTests.tearDown
    grant = fixtures.ActCodeToolsTests.grant

    def body(self, run_id):
        self.grant(['worktree', 'patch', 'test'])
        self.grant(['review'], act='act-qa')
        return {'run_id': run_id, 'conversation_id': 'conv-team', 'act_ids': ['act-dev', 'act-qa'],
                'prompt': 'Corrige add para sumar y revisa.', 'project_id': 'proj', 'file_path': 'calc.py',
                'apply_in_worktree': True, 'test_command': TESTS}

    def test_durable_retry_returns_original_result_and_forget_scrubs_it(self):
        body = self.body('retry-once')
        api = self.srv.api
        code, result = api.request('POST', '/axx-api/agents/v1/teams/run', body)
        self.assertEqual(code, 200, result)
        self.assertTrue(result['work']['test_receipt']['passed'])
        code, retry = api.request('POST', '/axx-api/agents/v1/teams/run', body)
        self.assertEqual((code, retry), (200, result))
        code, conflict = api.request('POST', '/axx-api/agents/v1/teams/run', {**body, 'prompt': 'Otra tarea'})
        self.assertEqual(code, 409, conflict)
        self.srv.rt.bindings.scrub_forgotten_conversation('conv-team')
        code, status = api.request('GET', '/axx-api/agents/v1/teams/result?run_id=retry-once')
        self.assertEqual((code, status['status']), (200, 'forgotten'))
        self.assertNotIn('result', status)
        self.assertNotEqual(api.request('POST', '/axx-api/agents/v1/teams/run', body)[0], 200)

    def test_cancel_during_inference_never_applies_late_patch_or_runs_next_act(self):
        body = self.body('cancel-late')
        entered, release = threading.Event(), threading.Event()
        calls, result = [], []

        def late_reply(http, act, envelope, conversation_id, cancel_event=None):
            calls.append(act['act_id'])
            entered.set()
            self.assertTrue(release.wait(10))
            return ({'ok': True, 'message': {'content': '```python\ndef add(a, b):\n    return a + b\n```'}},
                    {'model_verified': True})

        with patch.object(EvolutionHTTP, '_infer_act', late_reply):
            worker = threading.Thread(target=lambda: result.append(
                self.srv.api.request('POST', '/axx-api/agents/v1/teams/run', body)))
            worker.start()
            self.assertTrue(entered.wait(10))
            try:
                code, cancelled = self.srv.api.request('POST', '/axx-api/agents/v1/teams/cancel', {'run_id':body['run_id']})
                self.assertEqual((code, cancelled['cancel_requested']), (200, True))
            finally:
                release.set()
                worker.join(10)
            self.assertFalse(worker.is_alive())
        self.assertNotEqual(result[0][0], 200, result)
        self.assertEqual(calls, ['act-dev'])
        self.assertEqual((self.repo / 'calc.py').read_text(), BUGGY)
        with self.srv.rt.code_projects._connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM code_changesets').fetchone()[0], 0)
        graph = self.srv.rt.task_graph.get_graph(body['run_id'])
        self.assertTrue(all(n['state'] in ('cancelled', 'cancelled_with_effects') for n in graph['nodes']))

    def test_scheduler_fires_without_http_trigger_and_does_not_replay_a_completed_slot(self):
        self.srv.rt.inference_adapter=self.srv.adapter
        self.srv.rt.routines.register_routine(routine_id='one-shot',agent_id='act-dev',conversation_id='conv-auto',
            schedule_spec='at:'+str(int(time.time()*1000)+100),prompt_text='Responde al objetivo de esta rutina.',
            requires_approval=False,requested_capabilities=[],enabled=True)
        self.srv.rt.routines.start_scheduler(poll_interval_sec=.05)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            runs=self.srv.rt.routines.list_runs('one-shot')
            if runs and runs[0]['status']=='completed':break
            time.sleep(.05)
        self.srv.rt.routines.stop_scheduler()
        self.assertTrue(runs)
        self.assertEqual(runs[0]['status'],'completed',runs)
        self.assertTrue(fixtures._CoderModel.seen)
        count=len(fixtures._CoderModel.seen)
        self.assertFalse(self.srv.rt.routines.trigger_routine('one-shot',proposes_mutation=False)['executed'])
        self.assertEqual(len(fixtures._CoderModel.seen),count)
        self.assertEqual(self.srv.rt.task_graph.get_graph(runs[0]['run_id'])['status'],'completed')


if __name__ == '__main__':
    unittest.main()
