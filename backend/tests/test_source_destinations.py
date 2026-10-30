"""Recipient consent uses temporary policy storage; no observation or network."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService
from backend.commands import CommandService
from backend.inference.router import profile_id


class SourceDestinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.executor = ActionExecutor(Path(self.temp.name) / 'state.db', Path(self.temp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = AnticipationService(self.commands)
        self.providers = [dict(name=name, model='model-' + name, base_url='https://' + name + '.example/v1',
            protocol='openai', route_kind='direct', enabled=True, allow_sensitive=True) for name in ('a', 'b', 'c')]
        self.ids = [profile_id(row) for row in self.providers]
        self.catalog = patch.object(self.service, '_source_destination_catalog', create=True,
            side_effect=lambda: {profile_id(row): copy.deepcopy(row) for row in self.providers})
        self.catalog.start()
        self.target = dict(id='source-a', source='clipboard', task_id='task-a', observe=False,
                           retain=True, send_to_provider=False)

    def tearDown(self):
        self.catalog.stop()
        self.service.close(); self.commands.close(); self.executor.close()
        self.temp.cleanup()

    def configure(self, targets):
        return self.service.configure({'observation_targets': targets})['observation_targets']

    def test_legacy_defaults_to_empty_and_explicit_ids_are_canonical(self):
        self.assertEqual(self.configure([self.target])[0]['allowed_profile_ids'], [])
        saved = self.configure([self.target | {'allowed_profile_ids': list(reversed(self.ids))}])[0]
        self.assertEqual(saved['allowed_profile_ids'], sorted(self.ids))

    def test_invalid_unknown_or_unsupported_recipient_does_not_change_consent(self):
        before = self.configure([self.target])
        for value in ('a', [self.ids[0], self.ids[0]], ['A' * 32], ['d' * 32], self.ids * 6):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.configure([self.target | {'allowed_profile_ids': value}])
            self.assertEqual(self.service.status()['observation_targets'], before)
        self.providers[0]['route_kind'] = 'proxy'
        with self.assertRaises(ValueError):
            self.configure([self.target | {'allowed_profile_ids': [profile_id(self.providers[0])]}])
        with self.assertRaises(ValueError):
            self.configure([self.target | {'source': 'microphone', 'allowed_profile_ids': [self.ids[1]]}])

    def test_preserved_removed_identity_is_inert_but_can_be_removed(self):
        self.configure([self.target | {'allowed_profile_ids': [self.ids[0]]}])
        self.providers.clear()
        self.assertEqual(self.configure([self.target | {'allowed_profile_ids': [self.ids[0]]}])[0]['allowed_profile_ids'], [self.ids[0]])
        self.assertEqual(self.configure([self.target | {'allowed_profile_ids': []}])[0]['allowed_profile_ids'], [])

    def test_empty_intersection_and_incompatible_manual_selection_fail(self):
        targets = [self.target | {'allowed_profile_ids': self.ids[:2]},
                   self.target | {'id': 'source-b', 'allowed_profile_ids': self.ids[1:]}]
        self.configure(targets)
        refs = [{'target_id': row['id']} for row in targets]
        with patch.object(self.service, 'validate_provider_context_refs', return_value=True):
            self.assertEqual(self.service.allowed_provider_profile_ids('task-a', refs), (self.ids[1],))
            with self.assertRaisesRegex(ValueError, 'SOURCE_DESTINATION_UNAUTHORIZED'):
                self.service.allowed_provider_profile_ids('task-a', refs, provider_name='a', model='model-a')
            targets[1]['allowed_profile_ids'] = [self.ids[2]]
            self.configure(targets)
            with self.assertRaisesRegex(ValueError, 'SOURCE_DESTINATION_UNAUTHORIZED'):
                self.service.allowed_provider_profile_ids('task-a', refs)

    def test_old_consent_never_follows_changed_model_and_send_needs_a_recipient(self):
        target = self.target | {'allowed_profile_ids': [self.ids[0]]}
        self.configure([target])
        self.providers[0]['model'] = 'new-model'
        with patch.object(self.service, 'validate_provider_context_refs', return_value=True):
            with self.assertRaisesRegex(ValueError, 'SOURCE_DESTINATION_UNAUTHORIZED'):
                self.service.allowed_provider_profile_ids('task-a', [{'target_id': target['id']}])
        with self.assertRaisesRegex(ValueError, 'SOURCE_DESTINATION_UNAUTHORIZED'):
            self.configure([self.target | {'send_to_provider': True}])


class SourceDestinationPlanningTests(unittest.TestCase):
    def test_incompatible_causal_sources_abstain_before_mission_reservation(self):
        from backend.tests import test_planning_context as fixtures
        fixture = fixtures.SourcePublicationTests()
        fixture.setUp()
        try:
            provider = dict(fixture.model.config['providers'][0], name='another-recipient', model='another-model')
            fixture.model.config['providers'].append(provider)
            second = fixture.target | {'id': 'clipboard-second', 'allowed_profile_ids': [profile_id(provider)]}
            fixture.service.configure({'observation_targets': [fixture.target, second]})
            fixture.service.tick()
            with patch.object(fixture.learning, '_reserve_model_call', wraps=fixture.learning._reserve_model_call) as reserve, \
                    patch.object(fixture.model, 'route', wraps=fixture.model.route) as route:
                with self.assertRaisesRegex(ValueError, 'SOURCE_DESTINATION_UNAUTHORIZED'):
                    fixture.response()
            reserve.assert_not_called(); route.assert_not_called()
            self.assertEqual(fixture.learning.budget_db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0], 0)
            self.assertFalse(fixture.service.provider_context_leases)
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
