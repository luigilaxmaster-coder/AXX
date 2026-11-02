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
        self.assertEqual(sent['system'], 'JSON only')
        self.assertEqual(block, {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': image}})
        self.assertEqual(sent['output_config'], {'format': {'type': 'json_schema', 'schema': schema}, 'effort': 'high'})
        self.assertEqual(result['choices'][0]['message']['content'], '{}')

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
