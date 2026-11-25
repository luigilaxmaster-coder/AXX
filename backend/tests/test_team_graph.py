"""Act Team graphs and routines: connections decide who works after whom and what each Act may read.

The model is a fixture (it echoes which upstream outputs it was given); the registry, TaskGraph, handoffs, events and
routine scheduler are the real ones behind the HTTP API.
"""
from datetime import datetime
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.agents.http_api import EvolutionHTTP
from backend.agents.routines import next_cron_ms
from backend.tests.test_acts_inference import _Server, act_spec, provider

ACTS = [('act-plan', 'Plan', 'Core'), ('act-front', 'Front', 'Flow'), ('act-back', 'Back', 'Helix'), ('act-qa', 'QA', 'Prism')]
# Plan fans out to Front and Back (drawn left to right), both feed QA.
GRAPH = {'nodes': [{'agent_id': 'act-plan', 'x': 40, 'y': 120, 'instruction': 'Divide el trabajo'},
                   {'agent_id': 'act-front', 'x': 300, 'y': 40, 'instruction': 'Interfaz'},
                   {'agent_id': 'act-back', 'x': 300, 'y': 220},
                   {'agent_id': 'act-qa', 'x': 560, 'y': 120, 'instruction': 'Revisa ambas ramas'}],
         'edges': [{'from': 'act-plan', 'to': 'act-front'}, {'from': 'act-plan', 'to': 'act-back'},
                   {'from': 'act-front', 'to': 'act-qa'}, {'from': 'act-back', 'to': 'act-qa'}]}
MEMBERS = [{'agent_id': 'act-plan', 'role': 'lead'}, {'agent_id': 'act-front', 'role': 'member'},
           {'agent_id': 'act-back', 'role': 'member'}, {'agent_id': 'act-qa', 'role': 'reviewer'}]


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.srv = _Server(Path(self.tmp.name), [provider('loop-a', 'http://127.0.0.1:9/v1', 'model-alpha')])
        self.srv.rt.flags.set_flag('agent_profiles_v1', True, reason='team graph test')
        for aid, name, form in ACTS:
            code, body = self.post('profiles', act_spec(aid, name, form, 'loop-a', 'model-alpha'))
            self.assertEqual(code, 200, body)
        self.prompts = {}
        test = self

        def fake_infer(http, act, envelope, conversation_id, cancel_event=None):
            text = envelope['messages'][-1]['content']
            test.prompts[act['act_id']] = text
            return {'ok': True, 'message': {'content': f'salida-de-{act["act_id"]}'}}, {'model_verified': True, 'model': 'model-alpha'}
        patcher = patch.object(EvolutionHTTP, '_infer_act', fake_infer)
        patcher.start(); self.addCleanup(patcher.stop)

    def tearDown(self):
        self.srv.close(); self.tmp.cleanup()

    def post(self, path, body):
        return self.srv.api.request('POST', '/axx-api/agents/v1/' + path, body)

    def team(self, **extra):
        return {'team_id': 'team-graph', 'title': 'Producto', 'members': MEMBERS, 'coordinator_agent_id': 'act-plan',
                'graph': GRAPH, **extra}


class TeamGraphTests(_Base):
    def test_graph_is_validated_saved_with_revision_and_deleted(self):
        cyclic = {**GRAPH, 'edges': GRAPH['edges'] + [{'from': 'act-qa', 'to': 'act-plan'}]}
        self.assertEqual(self.post('teams', self.team(graph=cyclic))[0], 400)
        stranger = {**GRAPH, 'edges': [{'from': 'act-plan', 'to': 'act-nobody'}]}
        self.assertEqual(self.post('teams', self.team(graph=stranger))[0], 400)
        missing = {**GRAPH, 'nodes': GRAPH['nodes'][:3]}
        self.assertEqual(self.post('teams', self.team(graph=missing))[0], 400)
        code, created = self.post('teams', self.team())
        self.assertEqual(code, 200, created)
        team = created['team']
        self.assertEqual((team['revision'], len(team['graph']['edges'])), (1, 4))
        moved = {**GRAPH, 'nodes': [{**GRAPH['nodes'][0], 'x': 90}] + GRAPH['nodes'][1:]}
        code, updated = self.post('teams/update', {**self.team(graph=moved), 'expected_revision': 1, 'title': 'Producto v2'})
        self.assertEqual((code, updated['team']['revision'], updated['team']['graph']['nodes'][0]['x']), (200, 2, 90))
        code, stale = self.post('teams/update', {**self.team(), 'expected_revision': 1})
        self.assertEqual(code, 409, stale)  # an editor that loaded revision 1 cannot overwrite revision 2
        self.assertEqual(self.post('teams/delete', {'team_id': 'team-graph'}), (200, {'team_id': 'team-graph', 'deleted': True}))
        self.assertEqual(self.srv.rt.registry.list_teams(), [])

    def test_connections_decide_order_handoffs_and_what_each_act_reads(self):
        self.assertEqual(self.post('teams', self.team())[0], 200)
        code, res = self.post('teams/run', {'run_id': 'graph-run', 'conversation_id': 'conv-g', 'team_id': 'team-graph',
                                            'prompt': 'Lanza la página de precios'})
        self.assertEqual(code, 200, res)
        # topological order; Front before Back because it is drawn higher at the same column
        self.assertEqual([s['act_id'] for s in res['steps']], ['act-plan', 'act-front', 'act-back', 'act-qa'])
        self.assertEqual(sorted((e['from'], e['to']) for e in res['edges']), sorted((e['from'], e['to']) for e in GRAPH['edges']))
        # each Act reads only what is connected upstream: the sibling branch never leaks
        self.assertIn('salida-de-act-plan', self.prompts['act-back'])
        self.assertNotIn('salida-de-act-front', self.prompts['act-back'])
        self.assertNotIn('salida-de-act', self.prompts['act-plan'])
        for upstream in ('act-plan', 'act-front', 'act-back'):
            self.assertIn('salida-de-' + upstream, self.prompts['act-qa'])
        self.assertIn('Tu parte en este flujo: Revisa ambas ramas', self.prompts['act-qa'])
        # TaskGraph dependencies mirror the connections
        deps = {n['agent_id']: n['depends_on'] for n in res['graph']['nodes']}
        task = {n['agent_id']: n['task_id'] for n in res['graph']['nodes']}
        self.assertEqual(sorted(deps['act-qa']), sorted([task['act-front'], task['act-back']]))
        self.assertEqual(deps['act-plan'], [])
        # one Handoff v1 per connection, and each node's start/finish carries its task for live canvases
        events = self.srv.rt.event_hub.replay_sse('conv-g')['events']
        kinds = [e.get('type') or e.get('event_type') for e in events]
        self.assertEqual(kinds.count('handoff.created'), 4)
        started = [e for e in events if (e.get('type') or e.get('event_type')) == 'run.started' and (e.get('payload') or {}).get('task_id')]
        self.assertEqual([e['payload']['task_id'] for e in started], [task[a] for a in ('act-plan', 'act-front', 'act-back', 'act-qa')])

    def test_disabled_act_in_graph_blocks_the_run_instead_of_skipping_a_connection(self):
        self.assertEqual(self.post('teams', self.team())[0], 200)
        self.assertEqual(self.post('profiles/disable', {'agent_id': 'act-back'})[0], 200)
        code, res = self.post('teams/run', {'run_id': 'graph-off', 'conversation_id': 'conv-g', 'team_id': 'team-graph', 'prompt': 'x'})
        self.assertEqual(code, 400, res)
        self.assertIn('act-back', res['error']['message'])

    def test_a_restricted_connection_also_restricts_what_flows_through_later_acts(self):
        chain = {'nodes': [{'agent_id': 'act-plan', 'x': 40, 'y': 40}, {'agent_id': 'act-front', 'x': 300, 'y': 40},
                           {'agent_id': 'act-qa', 'x': 560, 'y': 40}],
                 'edges': [{'from': 'act-plan', 'to': 'act-front', 'transfer': 'artifact_only'}, {'from': 'act-front', 'to': 'act-qa'}]}
        members = [m for m in MEMBERS if m['agent_id'] != 'act-back']
        self.assertEqual(self.post('teams', self.team(members=members, graph=chain))[0], 200)
        code, res = self.post('teams/run', {'run_id': 'chain-run', 'conversation_id': 'conv-g', 'team_id': 'team-graph', 'prompt': 'x'})
        self.assertEqual(code, 200, res)
        for act in ('act-front', 'act-qa'):  # Plan reaches both only as a verified artifact reference
            self.assertNotIn('salida-de-act-plan', self.prompts[act])
            self.assertIn('art-chain-run-t1', self.prompts[act])
        self.assertIn('salida-de-act-front', self.prompts['act-qa'])

class RoutineScheduleTests(_Base):
    def test_cron_preview_and_invalid_specs(self):
        now = datetime(2026, 11, 24, 8, 30).timestamp() * 1000  # a Tuesday
        at = lambda ms: datetime.fromtimestamp(ms / 1000)
        self.assertEqual(at(next_cron_ms('0 9 * * *', now)), datetime(2026, 11, 24, 9, 0))
        self.assertEqual(at(next_cron_ms('0 9 * * *', datetime(2026, 11, 24, 9, 0).timestamp() * 1000)), datetime(2026, 11, 25, 9, 0))
        self.assertEqual(at(next_cron_ms('30 18 * * 1,5', now)), datetime(2026, 11, 27, 18, 30))  # next Friday
        self.assertEqual(at(next_cron_ms('*/15 * * * *', now)), datetime(2026, 11, 24, 8, 45))
        self.assertEqual(at(next_cron_ms('0 0 29 2 *', now)), datetime(2028, 2, 29, 0, 0))
        self.assertIsNone(next_cron_ms('61 * * * *', now))
        code, preview = self.srv.api.request('GET', '/axx-api/agents/v1/routines/preview?schedule_spec=every:30m')
        self.assertEqual(code, 200, preview)
        runs = preview['next_runs_ms']
        self.assertEqual([b - a for a, b in zip(runs, runs[1:])], [1_800_000, 1_800_000])
        self.assertEqual(self.srv.api.request('GET', '/axx-api/agents/v1/routines/preview?schedule_spec=cada%20rato')[0], 400)
        code, bad = self.post('routines', {'routine_id': 'r-bad', 'agent_id': 'act-plan', 'conversation_id': 'conv-r',
                                           'schedule_spec': 'cada rato', 'prompt_text': 'x'})
        self.assertEqual(code, 400, bad)  # no silent "every 60 s" for a schedule AXX cannot read

    def test_team_routine_waits_for_approval_then_runs_the_whole_graph(self):
        self.srv.rt.inference_adapter = object()  # transport present; the model itself is the fixture above
        self.assertEqual(self.post('teams', self.team())[0], 200)
        code, other = self.post('routines', {'routine_id': 'r-x', 'agent_id': 'act-plan', 'conversation_id': 'conv-r',
                                             'schedule_spec': 'every:1h', 'team_id': 'team-nope', 'prompt_text': 'x'})
        self.assertNotEqual(code, 200, other)
        code, reg = self.post('routines', {'routine_id': 'r-team', 'agent_id': 'act-plan', 'conversation_id': 'conv-r',
                                           'schedule_spec': 'every:1h', 'team_id': 'team-graph', 'requires_approval': True,
                                           'prompt_text': 'Informe semanal de precios', 'enabled': True})
        self.assertEqual((code, reg['routine']['team_id']), (200, 'team-graph'), reg)
        code, trig = self.post('routines/trigger', {'routine_id': 'r-team', 'proposes_mutation': True})
        self.assertEqual((code, trig['status']), (200, 'awaiting_approval'))
        code, ran = self.post('routines/approve', {'routine_id': 'r-team', 'approved': True})
        self.assertEqual((code, ran['status'], ran['executed']), (200, 'completed', True), ran)
        for aid, _, _ in ACTS:
            self.assertIn('salida-de-' + aid, ran['summary'])
        self.assertEqual(self.srv.rt.routines.get_routine('r-team')['status'], 'scheduled')
        # a denied slot is skipped, not run, and the card is resolved without a TaskGraph node
        self.post('routines/trigger', {'routine_id': 'r-team', 'proposes_mutation': True})
        before = len(self.srv.rt.routines.list_runs('r-team'))
        code, denied = self.post('routines/approve', {'routine_id': 'r-team', 'approved': False})
        self.assertEqual((code, denied['executed'], denied['status']), (200, False, 'scheduled'), denied)
        self.assertEqual(len(self.srv.rt.routines.list_runs('r-team')), before)
        self.assertTrue(all(c['status'] != 'pending' for c in self.srv.rt.orchestrator.pending_approvals.values()))
        self.assertGreater(self.srv.rt.routines.get_routine('r-team')['next_run_at_ms'], time.time() * 1000)

