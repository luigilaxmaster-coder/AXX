"""Offline contract tests for saved source-context destinations and consent."""

import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.inference import provider_settings as settings
from backend.inference.router import profile_id


class FakeAdapter:
    """The save contract without a router, SDK, native calls, or runtime state."""

    def __init__(self, providers):
        self.config = {'allow_paid': False, 'providers': copy.deepcopy(providers)}
        self.lock = threading.RLock()
        self.active_requests = {}
        self.updates = 0

    def update_config(self, config):
        self.config = copy.deepcopy(config)
        self.updates += 1


def provider(**changes):
    entry = {
        'name': 'Saved source destination',
        'kind': 'custom',
        'base_url': 'https://source-destination.example/v1',
        'model': 'saved-model',
        'protocol': 'openai',
        'api_key_env': 'AXX_SOURCE_DESTINATION_TEST_KEY',
        'enabled': True,
        'daily_attempt_limit': 100,
        'capabilities': ['text'],
        'billing_allowed': False,
        'free_confirmed': False,
        'cost_evidence': 'unknown',
        'route_kind': 'direct',
        'allow_sensitive': True,
    }
    entry.update(changes)
    return entry


class SourceDestinationSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'providers.json'
        # These functions are unnecessary for listing or saving an unkeyed
        # fixture. A regression must fail instead of touching network/native APIs.
        for attribute in ('_dpapi_encrypt', '_dpapi_decrypt'):
            blocker = patch.object(settings, attribute, side_effect=AssertionError('Native credential call'))
            blocker.start()
            self.addCleanup(blocker.stop)
        network = patch.object(settings.urllib.request, 'build_opener', side_effect=AssertionError('Network call'))
        network.start()
        self.addCleanup(network.stop)

    def save(self, adapter, **changes):
        current = adapter.config['providers'][0]
        body = {
            'provider': current['kind'],
            'name': current['name'],
            'base_url': current['base_url'],
            'model': current['model'],
            'protocol': current['protocol'],
        }
        body.update(changes)
        return settings.save(body, adapter, self.path)

    def test_public_rows_preserve_existing_fields_order_and_disabled_connections(self):
        first = provider(
            tasks=['chat'], context_window=8192, image_context_tokens=1024,
            task_priority={'chat': 2}, quota_scope_id='saved-scope', scope_limit=50,
            gateway_free_model_ids=[3], gateway_attempt_limit=2,
            gateway_timeout_ms=1000, gateway_profile_verified=False,
            gateway_keyless=False, candidate_only=False,
        )
        second = provider(name='Disabled destination', enabled=False)
        config = {'providers': [first, second]}
        before = copy.deepcopy(config)
        rows = settings.public_entries(config)

        self.assertEqual([row['name'] for row in rows], [first['name'], second['name']])
        for field in (
            'name', 'kind', 'base_url', 'model', 'enabled', 'protocol',
            'billing_allowed', 'free_confirmed', 'capabilities', 'tasks',
            'context_window', 'image_context_tokens', 'task_priority',
            'quota_scope_id', 'scope_limit', 'gateway_free_model_ids',
            'gateway_attempt_limit', 'gateway_timeout_ms',
            'gateway_profile_verified', 'gateway_keyless', 'candidate_only',
            'cost_evidence', 'route_kind',
        ):
            with self.subTest(field=field):
                self.assertEqual(rows[0][field], first[field])
        self.assertIn('has_key', rows[0])
        self.assertEqual(rows[1]['source_context_reason'], 'disabled')
        self.assertIs(rows[1]['source_context_eligible'], False)
        self.assertEqual(config, before)

    def test_public_profile_ids_use_the_canonical_router_identity(self):
        original = provider()
        entries = [
            original,
            provider(model='different-model'),
            provider(base_url='https://another-destination.example/v1'),
            provider(protocol='anthropic'),
            provider(route_kind='proxy'),
            provider(kind='freellmapi', route_kind='proxy', gateway_member_ids=[1, 2]),
            provider(kind='freellmapi', route_kind='proxy', gateway_member_ids=[1, 3]),
        ]
        rows = settings.public_entries({'providers': entries})
        self.assertEqual([row['profile_id'] for row in rows], [profile_id(entry) for entry in entries])
        self.assertEqual(len({row['profile_id'] for row in rows}), len(entries))

    def test_only_explicit_enabled_direct_http_protocols_with_consent_are_eligible(self):
        for protocol, url in (
            ('openai', 'https://source-destination.example/v1'),
            ('anthropic', 'https://source-destination.example/v1'),
            ('openai', 'http://127.0.0.1:1234/v1'),
        ):
            with self.subTest(protocol=protocol, url=url):
                entry = provider(protocol=protocol, base_url=url)
                row = settings.public_entries({'providers': [entry]})[0]
                self.assertIs(row['source_context_eligible'], True)
                self.assertEqual(row['source_context_reason'], 'eligible')

    def test_public_reasons_are_closed_and_fail_closed_for_unsupported_destinations(self):
        cases = (
            ({'enabled': False}, 'disabled'),
            ({'enabled': None}, 'disabled'),
            ({'candidate_only': True}, 'candidate_only'),
            ({'allow_sensitive': False}, 'sensitive_not_allowed'),
            ({'allow_sensitive': 1}, 'sensitive_not_allowed'),
            ({'allow_sensitive': 'true'}, 'sensitive_not_allowed'),
            ({'protocol': 'sdk'}, 'unsupported_transport'),
            ({'base_url': 'stdio://source-destination'}, 'unsupported_transport'),
            ({'route_kind': 'proxy'}, 'unsupported_transport'),
            ({'route_kind': 'unknown'}, 'unsupported_transport'),
            ({'route_kind': None}, 'unsupported_transport'),
            ({'kind': 'freellmapi', 'route_kind': 'proxy'}, 'gateway_not_supported'),
        )
        allowed = {
            'eligible', 'disabled', 'sensitive_not_allowed',
            'unsupported_transport', 'gateway_not_supported', 'candidate_only',
        }
        for changes, expected in cases:
            with self.subTest(changes=changes):
                row = settings.public_entries({'providers': [provider(**changes)]})[0]
                self.assertIs(row['source_context_eligible'], False)
                self.assertIn(row['source_context_reason'], allowed)
                self.assertEqual(row['source_context_reason'], expected)

    def test_missing_consent_is_denied_and_credentials_remain_private(self):
        entry = provider(
            api_key='RAW_CREDENTIAL_CANARY',
            gateway_dashboard_env='AXX_DASHBOARD_ENV_CANARY',
            gateway_dashboard_token='DASHBOARD_CREDENTIAL_CANARY',
        )
        entry.pop('allow_sensitive')
        with patch.dict(os.environ, {entry['api_key_env']: 'ENV_CREDENTIAL_CANARY'}):
            row = settings.public_entries({'providers': [entry]})[0]
        self.assertIs(row['has_key'], True)
        self.assertIs(row['source_context_eligible'], False)
        self.assertEqual(row['source_context_reason'], 'sensitive_not_allowed')
        serialized = json.dumps(row)
        for forbidden in (
            'api_key_env', 'api_key', 'gateway_dashboard_env', 'gateway_dashboard_token',
            'RAW_CREDENTIAL_CANARY', 'DASHBOARD_CREDENTIAL_CANARY',
            'ENV_CREDENTIAL_CANARY', 'AXX_SOURCE_DESTINATION_TEST_KEY',
            'AXX_DASHBOARD_ENV_CANARY',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_save_same_identity_preserves_existing_consent(self):
        for consent in (True, False):
            with self.subTest(consent=consent):
                adapter = FakeAdapter([provider(allow_sensitive=consent)])
                old_id = profile_id(adapter.config['providers'][0])
                self.assertTrue(self.save(adapter)['ok'])
                saved = adapter.config['providers'][0]
                self.assertEqual(profile_id(saved), old_id)
                self.assertIs(saved['allow_sensitive'], consent)
                self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['providers'][0], saved)

    def test_save_changed_model_does_not_inherit_consent(self):
        adapter = FakeAdapter([provider()])
        old_id = profile_id(adapter.config['providers'][0])
        self.save(adapter, model='changed-model')
        saved = adapter.config['providers'][0]
        self.assertNotEqual(profile_id(saved), old_id)
        self.assertIs(saved.get('allow_sensitive', False), False)

    def test_save_changed_route_identity_does_not_inherit_consent(self):
        adapter = FakeAdapter([provider()])
        old_id = profile_id(adapter.config['providers'][0])
        self.save(adapter, route_kind='proxy')
        saved = adapter.config['providers'][0]
        self.assertNotEqual(profile_id(saved), old_id)
        self.assertIs(saved.get('allow_sensitive', False), False)

    def test_save_new_identity_accepts_fresh_explicit_boolean_consent(self):
        for changes in ({'model': 'changed-model'}, {'route_kind': 'proxy'}):
            with self.subTest(changes=changes):
                adapter = FakeAdapter([provider()])
                old_id = profile_id(adapter.config['providers'][0])
                self.save(adapter, allow_sensitive=True, **changes)
                saved = adapter.config['providers'][0]
                self.assertNotEqual(profile_id(saved), old_id)
                self.assertIs(saved['allow_sensitive'], True)

    def test_save_cannot_move_existing_connection_or_its_consent_to_another_endpoint(self):
        adapter = FakeAdapter([provider()])
        before = copy.deepcopy(adapter.config)
        with self.assertRaises(ValueError):
            self.save(adapter, base_url='https://another-destination.example/v1')
        self.assertEqual(adapter.config, before)
        self.assertEqual(adapter.updates, 0)
        self.assertFalse(self.path.exists())

    def test_save_new_connection_does_not_inherit_another_destination_consent(self):
        adapter = FakeAdapter([provider()])
        self.save(adapter, name='Another destination', base_url='https://another-destination.example/v1')
        self.assertIs(adapter.config['providers'][0]['allow_sensitive'], True)
        self.assertIs(adapter.config['providers'][1].get('allow_sensitive', False), False)

    def test_save_explicit_boolean_consent_can_grant_and_revoke(self):
        for old, requested in ((False, True), (True, False)):
            with self.subTest(old=old, requested=requested):
                adapter = FakeAdapter([provider(allow_sensitive=old)])
                self.save(adapter, allow_sensitive=requested)
                self.assertIs(adapter.config['providers'][0]['allow_sensitive'], requested)

    def test_save_nonboolean_consent_is_rejected_without_mutation_or_write(self):
        for invalid in (None, 0, 1, 'true', 'false', [], {}):
            with self.subTest(invalid=invalid):
                adapter = FakeAdapter([provider()])
                before = copy.deepcopy(adapter.config)
                with self.assertRaises(ValueError):
                    self.save(adapter, allow_sensitive=invalid)
                self.assertEqual(adapter.config, before)
                self.assertEqual(adapter.updates, 0)
                self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
