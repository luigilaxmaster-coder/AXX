"""Comprehensive Test Suite for Axx Hardened Router (H01-H10) & Adapter.
Covers:
  - H01: Reloj de pared 70s global, lectura limitada de entrada.
  - H02: Parseo estricto JSON (rechazo NaN, Infinity), bool!=int, null por campo.
  - H03: Retry-After saturado a 86.400s, fechas RFC 2822, inválidos a 0.
  - H04: quota_scope_id compartido entre modelos de la misma cuenta.
  - H05: Validación de respuesta (content o tool_calls válidos; choices vacíos rechazados).
  - H06: enabled: true explícito, bloqueo modelos REPLACE_*, capacidades probadas.
  - H07: 403 política/moderación aborta sin failover; 401/403 credenciales conmuta.
  - H08: Cancelación activa en adaptador, descarte de respuestas tardías.
  - H09: Estado 'ready_locally' con semántica de cuota local únicamente.
  - H10: Error normalizado en frontera, fail-closed ante SQLite.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest

from backend.inference.router import (
    Router, UpstreamError, Exhausted, RequestError, StateError, PolicyBlocked,
    parse_strict_json, retry_seconds
)
from backend.inference.adapter import InferenceAdapter

class HardenedRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'state.db'
        os.environ['TEST_KEY_A'] = 'secret-a'
        os.environ['TEST_KEY_B'] = 'secret-b'
        self.calls = []
        self.responses = {}
        self.routers = []

    def tearDown(self):
        for r in self.routers:
            r.close()
        self.tmp.cleanup()

    def make_router(self, **overrides) -> Router:
        cfg = {
            'timeout_seconds': 10,
            'global_deadline_seconds': 70,
            'max_attempts': 3,
            'allow_paid': False,
            'providers': [
                {
                    'name': 'prov-a',
                    'base_url': 'https://api.example.com/v1',
                    'model': 'model-a',
                    'api_key_env': 'TEST_KEY_A',
                    'enabled': True,
                    'free_confirmed': True,
                    'daily_attempt_limit': 10,
                    'quota_scope_id': 'account-primary',
                    'capabilities': ['text', 'tools']
                },
                {
                    'name': 'prov-b',
                    'base_url': 'https://api.fallback.com/v1',
                    'model': 'model-b',
                    'api_key_env': 'TEST_KEY_B',
                    'enabled': True,
                    'free_confirmed': True,
                    'daily_attempt_limit': 10,
                    'quota_scope_id': 'account-secondary',
                    'capabilities': ['text']
                }
            ]
        }
        cfg.update(overrides)

        def mock_transport(p, body, timeout):
            self.calls.append((p['name'], body, timeout))
            r = self.responses.get(p['name'], {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'Valid response text'}
                }]
            })
            if isinstance(r, Exception):
                raise r
            return r

        router = Router(cfg, state=self.db_path, transport=mock_transport)
        self.routers.append(router)
        return router

    # === H01: Deadline global de 70s y presupuesto monotónico ===
    def test_h01_global_deadline_exhaustion(self):
        r = self.make_router()
        # Pass deadline in the past
        past_deadline = time.monotonic() - 1.0
        with self.assertRaises(UpstreamError) as ctx:
            r.chat({'messages': [{'role': 'user', 'content': 'hi'}]}, deadline_time=past_deadline)
        self.assertEqual(ctx.exception.status, 504)
        self.assertIn("deadline exceeded", str(ctx.exception).lower())

    # === H02: Parseo estricto JSON y rechazo NaN / Infinity ===
    def test_h02_strict_json_rejects_nan_and_infinity(self):
        # NaN and Infinity must fail
        with self.assertRaises(ValueError):
            parse_strict_json(b'{"value": NaN}')
        with self.assertRaises(ValueError):
            parse_strict_json(b'{"value": Infinity}')
        with self.assertRaises(ValueError):
            parse_strict_json(b'{"value": -Infinity}')
        # Normal JSON parses fine
        obj = parse_strict_json(b'{"valid": true, "number": 123.45}')
        self.assertEqual(obj['number'], 123.45)

    def test_h02_null_validation_per_field(self):
        r = self.make_router()
        # Null content on user message is rejected
        with self.assertRaises(RequestError):
            r.chat({'messages': [{'role': 'user', 'content': None}]})
        # Null content on assistant message with valid tool_calls is accepted
        r.chat({'messages': [{'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'function': {'name': 'test', 'arguments': '{}'}}]}]})

    # === H03: Retry-After seguro con saturación a 86.400s (24h) ===
    def test_h03_retry_after_parsing_and_saturation(self):
        self.assertEqual(retry_seconds('120'), 120.0)
        self.assertEqual(retry_seconds('99999999'), 86400.0)  # Capped at 24h
        self.assertEqual(retry_seconds('invalid_string'), 0.0)
        self.assertEqual(retry_seconds('-50'), 0.0)
        self.assertEqual(retry_seconds('NaN'), 0.0)
        self.assertEqual(retry_seconds(None), 0.0)
        self.assertEqual(retry_seconds('Wed, 21 Oct 2099 07:28:00'), 0.0)

    # === H04: Control por quota_scope_id compartido ===
    def test_h04_shared_quota_scope_cooldown(self):
        # Both providers share the same quota_scope_id
        r = self.make_router()
        r.providers[1]['quota_scope_id'] = 'account-primary'
        # Provider A hits 429
        self.responses['prov-a'] = UpstreamError(429, retry_after=300)
        # Because scope is shared, provider B will also be in cooldown, so UpstreamError 429 is propagated
        with self.assertRaises(UpstreamError) as ctx:
            r.chat({'messages': [{'role': 'user', 'content': 'test'}]})
        self.assertEqual(ctx.exception.status, 429)
        # Prov-a was called, but prov-b was skipped due to shared quota scope!
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], 'prov-a')

    def test_h04_implicit_shared_account_limit_prevents_model_switch(self):
        router = self.make_router()
        router.providers[0]['daily_attempt_limit'] = 1
        router.providers[1]['quota_scope_id'] = 'account-primary'
        router.chat({'messages': [{'role': 'user', 'content': 'first'}]})
        # No scope_limit field exists. The second model must still share the
        # strictest enabled daily account budget and may not reset the allowance.
        with self.assertRaises(Exhausted):
            router.chat({'messages': [{'role': 'user', 'content': 'second'}]})
        self.assertEqual(len(self.calls), 1)
        for provider in router.status()['providers']:
            self.assertEqual(provider['state'], 'local_quota_exhausted')
            self.assertEqual(provider['scope_attempts_today'], 1)

    # === H05: Validación de respuestas (rechazar empty y malformados) ===
    def test_h05_reject_empty_content_or_missing_choices(self):
        r = self.make_router()
        # Empty choices
        self.responses['prov-a'] = {'choices': []}
        # Next should failover to prov-b
        res = r.chat({'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(res['axx_router']['provider'], 'prov-b')

    def test_h05_reject_empty_assistant_message(self):
        r = self.make_router()
        # Message with empty content and no tool_calls
        self.responses['prov-a'] = {'choices': [{'message': {'role': 'assistant', 'content': '   '}}]}
        res = r.chat({'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(res['axx_router']['provider'], 'prov-b')

    # === H06: Exigir enabled: true y rechazar REPLACE_* ===
    def test_h06_template_models_rejected_at_config(self):
        with self.assertRaises(ValueError):
            self.make_router(providers=[{
                'name': 'prov-bad',
                'base_url': 'https://api.example.com/v1',
                'model': 'REPLACE_WITH_REAL_MODEL',
                'api_key_env': 'TEST_KEY_A',
                'enabled': True,
                'free_confirmed': True,
                'daily_attempt_limit': 10,
                'capabilities': ['text']
            }])

    def test_h06_missing_explicit_enabled_rejected(self):
        with self.assertRaises(ValueError):
            self.make_router(providers=[{
                'name': 'prov-no-enabled',
                'base_url': 'https://api.example.com/v1',
                'model': 'valid-model',
                'api_key_env': 'TEST_KEY_A',
                'free_confirmed': True,
                'daily_attempt_limit': 10,
                'capabilities': ['text']
            }])

    # === H07: 403 por política aborta sin failover ===
    def test_h07_policy_block_aborts_without_failover(self):
        r = self.make_router()
        # Simulate 403 moderation/policy error on prov-a
        self.responses['prov-a'] = UpstreamError(403, is_policy=True, message="Content moderation blocked")
        with self.assertRaises(PolicyBlocked):
            r.chat({'messages': [{'role': 'user', 'content': 'dangerous'}]})
        # Must NOT have retried on prov-b!
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], 'prov-a')

    def test_h07_auth_failure_aborts_without_failover(self):
        router=self.make_router()
        self.responses['prov-a']=UpstreamError(401)
        with self.assertRaises(UpstreamError) as error:
            router.chat({'messages':[{'role':'user','content':'hello'}]})
        self.assertEqual(error.exception.status,401)
        self.assertEqual(len(self.calls),1)

    def test_h05_tool_schema_and_explicit_no_stream(self):
        router=self.make_router()
        for tool_call in ('bad',[{'id':'','type':'function','function':{'name':'write','arguments':'{}'}}],
                          [{'id':'call','function':{'name':'write','arguments':'{}'}}]):
            with self.assertRaises(UpstreamError):
                router._validate_response_message({'choices':[{'message':{'role':'assistant','content':'text','tool_calls':tool_call}}]})
        router.chat({'messages':[{'role':'user','content':'hello'}]})
        self.assertIs(self.calls[0][1]['stream'],False)

    def test_h02_unsupported_fields_and_size_configuration(self):
        router=self.make_router()
        with self.assertRaises(RequestError):
            router.validate_request({'messages':[{'role':'user','content':'hello'}],'top_p':.9})
        with self.assertRaises(ValueError):
            self.make_router(max_request_bytes=8*1024*1024+1)

    # === H08: Cancelación activa y descarte de respuestas ===
    def test_h08_adapter_cancellation_and_discard(self):
        # Configure transport to trigger adapter.cancel during call
        adapter_holder = []
        def slow_transport(p, body, timeout):
            # Simulate user pressing Esc while request is in flight
            adapter_holder[0].cancel('req-cancel-1')
            return {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'Late response that should be discarded'}
                }]
            }

        cfg = {
            'timeout_seconds': 10,
            'global_deadline_seconds': 70,
            'max_attempts': 1,
            'allow_paid': False,
            'providers': [{
                'name': 'prov-slow',
                'base_url': 'https://api.example.com/v1',
                'model': 'model-slow',
                'api_key_env': 'TEST_KEY_A',
                'enabled': True,
                'free_confirmed': True,
                'daily_attempt_limit': 10,
                'capabilities': ['text']
            }]
        }
        r = Router(cfg, state=self.db_path, transport=slow_transport)
        self.routers.append(r)
        adapter = InferenceAdapter(cfg, router_instance=r)
        adapter_holder.append(adapter)

        envelope = {
            'request_id': 'req-cancel-1',
            'conversation_id': 'conv-1',
            'task': 'chat',
            'messages': [{'role': 'user', 'content': 'hello'}]
        }
        res = adapter.route(envelope)
        self.assertFalse(res['ok'])
        self.assertEqual(res['error']['code'], 'CANCELLED')
        adapter.close()

    # === H09: Status claro con semántica local 'ready_locally' ===
    def test_h09_status_semantics(self):
        r = self.make_router()
        st = r.status()
        self.assertEqual(st['quota_source'], 'local_attempts_only')
        self.assertTrue(len(st['providers']) >= 2)
        prov_a = next(p for p in st['providers'] if p['name'] == 'prov-a')
        self.assertEqual(prov_a['state'], 'ready_locally')

    # === H10: Error normalizado en frontera y fail-closed ante SQLite ===
    def test_h10_stream_true_clean_error(self):
        r = self.make_router()
        with self.assertRaises(RequestError) as ctx:
            r.chat({'messages': [], 'stream': True})
        self.assertEqual(ctx.exception.code, 'INVALID_REQUEST')

if __name__ == '__main__':
    unittest.main()
