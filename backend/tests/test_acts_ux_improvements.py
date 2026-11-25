"""Verification for Equipos edge metadata/policies and UI persistence."""
from __future__ import annotations

import functools
import http.server
from pathlib import Path
import tempfile
import unittest

from playwright.sync_api import sync_playwright

from backend.agents.registry import AgentProfileValidationError, checked_team_graph
from backend.tests.test_acts_inference import _EchoModel, _Server, act_spec, provider
from backend.tests.test_acts_ui import ROOT, open_axx, serve


class EdgeMetadataAndPoliciesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        _EchoModel.seen = []
        self.prov = serve(_EchoModel)
        url = f'http://127.0.0.1:{self.prov.server_address[1]}'
        self.srv = _Server(Path(self.tmp.name), [provider('loop-edge', url, 'model-edge')])
        self.srv.rt.flags.set_flag('agent_profiles_v1', True, reason='edge test')
        self.srv.rt.registry.create_profile(act_spec('a1', 'Dev', 'Helix', 'loop-edge', 'model-edge', role='Developer'))
        self.srv.rt.registry.create_profile(act_spec('a2', 'Reviewer', 'Core', 'loop-edge', 'model-edge', role='QA Reviewer'))

    def tearDown(self):
        self.srv.close()
        self.prov.shutdown()
        self.prov.server_close()
        self.tmp.cleanup()

    def test_checked_team_graph_validates_edge_contracts_and_rejects_bad_transfer(self):
        graph = checked_team_graph({
            'nodes': [{'agent_id': 'a1', 'x': 20, 'y': 20, 'instruction': 'fix'},
                      {'agent_id': 'a2', 'x': 300, 'y': 20, 'instruction': 'verify'}],
            'edges': [{'from': 'a1', 'to': 'a2', 'label': '  Diff + pruebas  ', 'transfer': 'summary'}],
        }, ['a1', 'a2'])
        self.assertEqual(graph['edges'], [{'from': 'a1', 'to': 'a2', 'label': 'Diff + pruebas', 'transfer': 'summary'}])
        with self.assertRaises(AgentProfileValidationError):
            checked_team_graph({
                'nodes': [{'agent_id': 'a1', 'x': 0, 'y': 0}, {'agent_id': 'a2', 'x': 100, 'y': 0}],
                'edges': [{'from': 'a1', 'to': 'a2', 'transfer': 'magic'}],
            }, ['a1', 'a2'])

    def test_edge_transfer_mode_and_team_policies_reach_downstream_act(self):
        code, created = self.srv.api.request('POST', '/axx-api/agents/v1/teams', {
            'team_id': 'team-edge-meta', 'title': 'Equipo Contrato',
            'coordinator_agent_id': 'a1',
            'delegation_rules': 'Usar diff verificable antes de aprobar',
            'review_criteria': 'Zero regresiones sin prueba',
            'members': [{'agent_id': 'a1', 'role': 'lead'}, {'agent_id': 'a2', 'role': 'reviewer'}],
            'graph': {
                'nodes': [{'agent_id': 'a1', 'x': 40, 'y': 40, 'instruction': 'Analiza fallo'},
                          {'agent_id': 'a2', 'x': 320, 'y': 40, 'instruction': 'Emite veredicto'}],
                'edges': [{'from': 'a1', 'to': 'a2', 'label': 'Diff + pruebas', 'transfer': 'artifact_only'}],
            },
        })
        self.assertEqual(code, 200, created)
        code, run = self.srv.api.request('POST', '/axx-api/agents/v1/teams/run', {
            'run_id': 'run-edge-meta-1', 'conversation_id': 'conv-edge',
            'team_id': 'team-edge-meta', 'prompt': 'Verifica contrato de conexión',
        })
        self.assertEqual(code, 200, run)
        self.assertEqual(run['edges'], [{'from': 'a1', 'to': 'a2', 'label': 'Diff + pruebas', 'transfer': 'artifact_only'}])
        downstream_prompt = _EchoModel.seen[-1]['messages'][-1]['content']
        self.assertIn('Reglas de delegación del equipo: Usar diff verificable antes de aprobar', downstream_prompt)
        self.assertIn('Criterios de revisión del equipo: Zero regresiones sin prueba', downstream_prompt)
        self.assertIn('artefacto ', downstream_prompt)
        self.assertIn('(entrega: Diff + pruebas)', downstream_prompt)


class TeamEdgeInspectorUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        _EchoModel.seen = []
        self.prov = serve(_EchoModel)
        url = f'http://127.0.0.1:{self.prov.server_address[1]}'
        self.srv = _Server(Path(self.tmp.name), [provider('loop-ui', url, 'model-ui')])
        self.srv.rt.flags.set_flag('agent_profiles_v1', True, reason='edge ui test')
        self.srv.rt.registry.create_profile(act_spec('a1', 'Dev', 'Helix', 'loop-ui', 'model-ui', role='Developer'))
        self.srv.rt.registry.create_profile(act_spec('a2', 'QA', 'Core', 'loop-ui', 'model-ui', role='QA Reviewer'))
        self.srv.rt.registry.create_team(
            team_id='team-ui-edge', title='Equipo UI', coordinator_agent_id='a1',
            members=[{'agent_id': 'a1', 'role': 'lead'}, {'agent_id': 'a2', 'role': 'reviewer'}],
            graph={'nodes': [{'agent_id': 'a1', 'x': 40, 'y': 60, 'instruction': ''},
                             {'agent_id': 'a2', 'x': 310, 'y': 60, 'instruction': ''}],
                   'edges': [{'from': 'a1', 'to': 'a2'}]},
        )
        self.web = serve(functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / '1.AXX')))

    def tearDown(self):
        self.web.shutdown()
        self.web.server_close()
        self.srv.close()
        self.prov.shutdown()
        self.prov.server_close()
        self.tmp.cleanup()

    def test_edge_contract_and_transfer_mode_persist_through_ui(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = open_axx(browser, self.srv, self.web)
                page.evaluate("Axx.companion.openFeature('agent')")
                page.get_by_role('button', name='Abrir Acts', exact=True).click()
                page.get_by_role('tab', name='Equipos (Teams)').click()
                page.locator('.axx-flow-team').first.click()
                page.locator('.axx-flow-edge').first.click(force=True)
                page.get_by_role('button', name='Diff + pruebas', exact=True).click()
                page.get_by_label('Alcance de transferencia').select_option('summary')
                self.assertEqual(page.locator('.axx-flow-edge-tag').first.text_content(), 'Diff + pruebas · Resumen')
                page.get_by_role('button', name='Guardar cambios', exact=True).click()
                page.wait_for_function('''async () => {
                    const teams = await Axx.backendRequest('GET', '/axx-api/agents/v1/teams');
                    return teams.teams[0]?.graph?.edges?.[0]?.label === 'Diff + pruebas'
                        && teams.teams[0]?.graph?.edges?.[0]?.transfer === 'summary';
                }''')
                team = self.srv.rt.registry.get_team('team-ui-edge')
                self.assertEqual(team['graph']['edges'][0], {'from': 'a1', 'to': 'a2', 'label': 'Diff + pruebas', 'transfer': 'summary'})
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
