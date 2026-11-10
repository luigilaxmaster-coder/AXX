import base64
import json
import unittest
from unittest.mock import patch

from backend.inference.router import RequestError, http_transport
from backend.inference.provider_settings import anthropic_efforts
from backend.presentation_plan import output_schema


class Response:
    headers = {}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, _limit):
        return json.dumps({'model': 'claude-sonnet-4-6', 'content': [{'type': 'text', 'text': '{}'}],
                           'stop_reason': 'end_turn'}).encode()


class SpatialTransportTests(unittest.TestCase):
    def test_anthropic_receives_base64_image_schema_and_effort(self):
        image = base64.b64encode(b'png bytes').decode()
        schema = output_schema('presentation')
        provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1',
                    'model': 'claude-sonnet-4-6', 'api_key_env': 'AXX_TEST_SPATIAL_KEY'}
        request = {'model': provider['model'], 'max_tokens': 1200, 'effort': 'high', 'output_schema': schema,
                   'messages': [{'role': 'system', 'content': 'JSON only'}, {'role': 'user', 'content': [
                       {'type': 'text', 'text': 'Describe the crop.'},
                       {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image}}]}]}
        with patch('backend.inference.router.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = Response()
            result = http_transport(provider, request, 2)
        sent = json.loads(opener.return_value.open.call_args.args[0].data)
        block = sent['messages'][0]['content'][1]
        self.assertEqual(sent['system'], [{'type': 'text', 'text': 'JSON only', 'cache_control': {'type': 'ephemeral'}}])
        self.assertEqual(block, {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': image}})
        wire = json.dumps(sent['output_config']['format']['schema'])
        self.assertNotIn('maxItems', wire); self.assertNotIn('"minItems": 3', wire)  # rejected by Anthropic; Python validators keep the bounds
        self.assertIn('"required"', wire); self.assertEqual(sent['output_config']['effort'], 'high')
        self.assertIn('maxItems', json.dumps(schema))  # the shared schema itself is unchanged
        self.assertEqual(result['choices'][0]['message']['content'], '{}')

    def test_anthropic_adapts_structured_tools_in_both_directions(self):
        provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1',
                    'model': 'claude-sonnet-4-6', 'api_key_env': 'AXX_TEST_SPATIAL_KEY'}
        tool = {'name': 'axx_system_telemetry', 'parameters': {'type': 'object', 'additionalProperties': False}}
        request = {'model': provider['model'], 'messages': [{'role': 'user', 'content': 'estado'}],
                   'tools': [{'type': 'function', 'function': tool}]}
        result = {'content': [{'type': 'text', 'text': 'Voy a consultarlo.'},
                              {'type': 'tool_use', 'id': 't', 'name': tool['name'], 'input': {}}]}
        with patch('backend.inference.router.urllib.request.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(result).encode()
            data = http_transport(provider, request, 2)
        sent = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertEqual(sent['tools'][0]['input_schema'], tool['parameters'])
        choice = data['choices'][0]
        self.assertEqual(choice['finish_reason'], 'tool_calls')
        self.assertEqual(choice['message']['content'], 'Voy a consultarlo.')
        self.assertEqual(choice['message']['tool_calls'][0]['function'], {'name': tool['name'], 'arguments': '{}'})

    def test_claude_5_drops_deprecated_temperature_but_older_models_keep_it(self):
        for model, expected in (('claude-sonnet-5-5', False), ('claude-opus-5-5', False), ('claude-sonnet-4-6', True)):
            provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'model': model, 'api_key_env': 'AXX_TEST_SPATIAL_KEY'}
            with patch('backend.inference.router.urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = Response()
                http_transport(provider, {'model': model, 'temperature': 0, 'messages': [{'role': 'user', 'content': 'hola'}]}, 2)
            self.assertEqual('temperature' in json.loads(opener.return_value.open.call_args.args[0].data), expected, model)

    def send(self, provider, extra=None, response=None):
        body = {'model': provider['model'], 'messages': [{'role': 'system', 'content': 'stable contract'}, {'role': 'user', 'content': [
            {'type': 'text', 'text': 'question'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(b'x').decode()}}]}], **(extra or {})}
        with patch('backend.inference.router.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response or Response()
            result = http_transport(provider, body, 2)
        return json.loads(opener.return_value.open.call_args.args[0].data), result

    def test_prompt_caching_puts_one_explicit_breakpoint_on_the_stable_system_prefix_only(self):
        provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'model': 'claude-sonnet-5-5', 'api_key_env': 'AXX_TEST_SPATIAL_KEY'}
        sent, _ = self.send(provider)
        self.assertEqual(sent['system'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertNotIn('cache_control', sent)  # no automatic top-level breakpoint that could land on the image
        self.assertNotIn('cache_control', json.dumps(sent['messages']))  # neither the question nor the image block is cached
        self.assertEqual(json.dumps(sent).count('cache_control'), 1)
        sent, _ = self.send(dict(provider, cache_ttl='1h'))
        self.assertEqual(sent['system'][0]['cache_control'], {'type': 'ephemeral', 'ttl': '1h'})
        sent, _ = self.send(dict(provider, prompt_caching=False))
        self.assertEqual(sent['system'], 'stable contract')  # opt-out keeps the plain string
        sent, _ = self.send(dict(provider, cache_control={'type': 'ephemeral', 'ttl': '5m'}))
        self.assertEqual(sent['system'][0]['cache_control'], {'type': 'ephemeral', 'ttl': '5m'})

    def test_cache_token_usage_is_reported_and_unknown_fields_are_dropped(self):
        class Cached(Response):
            def read(self, _limit):
                return json.dumps({'model': 'claude-sonnet-5-5', 'content': [{'type': 'text', 'text': '{}'}], 'stop_reason': 'end_turn',
                                   'usage': {'input_tokens': 120, 'output_tokens': 40, 'cache_read_input_tokens': 3100, 'cache_creation_input_tokens': 0, 'secret': 'x'}}).encode()
        provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'model': 'claude-sonnet-5-5', 'api_key_env': 'AXX_TEST_SPATIAL_KEY'}
        _, result = self.send(provider, response=Cached())
        self.assertEqual(result['usage'], {'input_tokens': 120, 'output_tokens': 40, 'cache_read_input_tokens': 3100, 'cache_creation_input_tokens': 0})

    def test_invalid_caching_settings_are_rejected_by_the_config_validator(self):
        from backend.inference.router import Router
        base = {'timeout_seconds': 20, 'global_deadline_seconds': 70, 'max_attempts': 1, 'max_request_bytes': 2097152, 'allow_paid': False,
                'providers': [{'name': 'c', 'model': 'm', 'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'enabled': True,
                               'api_key_env': 'K', 'capabilities': ['text'], 'free_confirmed': False, 'billing_allowed': True, 'daily_attempt_limit': 100}]}
        Router._validate_config(None, base)
        for field, bad in (('prompt_caching', 'yes'), ('cache_ttl', '2h'), ('cache_control', 'ephemeral')):
            broken = json.loads(json.dumps(base)); broken['providers'][0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError): Router._validate_config(None, broken)

    def test_anthropic_rejects_non_data_image_before_network(self):
        provider = {'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'model': 'm', 'api_key_env': ''}
        body = {'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'http://example.com/a.png'}}]}]}
        with patch('backend.inference.router.urllib.request.build_opener') as opener:
            with self.assertRaises(RequestError):
                http_transport(provider, body, 2)
            opener.assert_not_called()

    def test_effort_catalog_is_conservative_and_model_specific(self):
        self.assertEqual(anthropic_efforts('claude-sonnet-4-6'), ['low', 'medium', 'high', 'xhigh', 'max'])
        self.assertEqual(anthropic_efforts('claude-sonnet-4-6-20260501')[-1], 'max')
        self.assertEqual(anthropic_efforts('claude-sonnet-4-5'), [])
        self.assertEqual(anthropic_efforts('custom-vision-model'), [])


if __name__ == '__main__':
    unittest.main()
