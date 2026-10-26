import copy
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from backend.actions import windows_automation as uia
from backend.actions.visual_grounding import propose_grounding


class VisualGroundingTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'observation_id': 'ground-fixture', 'session_id': uia.OBSERVATION_SESSION_ID,
            'window_id': 123, 'pid': 42, 'process_started': '123456', 'completed_monotonic': time.monotonic(),
            'window_bounds': {'x': -100, 'y': 10, 'width': 100, 'height': 80},
            'monitors': [{'id': '1', 'x': -200, 'y': 0, 'width': 400, 'height': 200}], 'minimized': False,
            'screenshot': {'document_id': 'image', 'revision': 1, 'sha256': 'image-hash', 'content_status': 'captured'}}
        self.observed = {'observation': self.identity, 'window_title': 'Fixture'}
        uia._remember_observation(self.observed)
        self.document = {'revision': 1, 'source': {'id': '1', 'x': -200, 'y': 0, 'sha256': 'image-hash'}}
        self.image = Image.new('RGB', (400, 200), (50, 80, 120))
        self.route = {'provider': 'selected', 'configured_model': 'vision', 'selection_mode': 'manual'}
        self.answer = {'status': 'selected', 'point': {'x': 99.99, 'y': 79.99}, 'confidence': .95, 'label': 'Target'}
        self.service = Mock()
        self.service.adapter.config = {'allow_paid': False, 'providers': [{'name': 'selected', 'model': 'vision',
            'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']}]}
        self.service.adapter.supports_cancel_event = True
        self.service.adapter.route.side_effect = lambda *a, **k: {'ok': True, 'route': self.route, 'message': {'content': json.dumps(self.answer)}}
        self.service.get.return_value = self.document
        self.service.capture.return_value = self.document
        self.service.original.return_value = self.image
        for name, value in [('observe_geometry', copy.deepcopy(self.identity)), ('process_started', '123456'),
                            ('list_windows', [{'window_id': 123, 'pid': 42, 'title': 'Fixture'}])]:
            p = patch.object(uia, name, return_value=value)
            p.start(); self.addCleanup(p.stop)

    def call(self, **kwargs):
        args = {'capture_service': self.service, 'provider_name': 'selected', 'model': 'vision', 'image_authorized': True}
        args.update(kwargs)
        return propose_grounding(123, 42, 'ground-fixture', 'Target', **args)

    def test_explicit_authorization_and_selected_free_route_required(self):
        with self.assertRaisesRegex(ValueError, 'IMAGE_AUTHORIZATION_REQUIRED'):
            self.call(image_authorized=False)
        with self.assertRaisesRegex(ValueError, 'VISION_UNAVAILABLE'):
            self.call(model='other')
        self.service.adapter.config['providers'][0]['free_confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'VISION_UNAVAILABLE'):
            self.call()
        self.service.adapter.route.assert_not_called()

    def test_strict_envelope_and_physical_coordinate_edge_remain_inside_window(self):
        result = self.call()
        self.assertEqual(result['desktop_point'], {'x': -1, 'y': 89})
        self.assertTrue(result['proposal_only'])
        self.assertFalse(result['effect_executed'])
        self.assertEqual(result['semantic_verification'], 'indeterminate')
        sent = self.service.adapter.route.call_args.args[0]
        self.assertEqual((sent['provider_name'], sent['model'], sent['selection_mode'], sent['allow_paid']),
                         ('selected', 'vision', 'manual', False))
        self.assertLessEqual(sent['deadline_ms'], 12000)
        self.assertIsInstance(self.service.adapter.route.call_args.kwargs['cancel_event'], threading.Event)

    def test_low_confidence_has_no_actionable_point(self):
        self.answer['confidence'] = .84
        result = self.call()
        self.assertEqual(result['status'], 'ambiguous')
        self.assertIsNone(result['point'])
        self.assertIsNone(result['desktop_point'])

    def test_downscaled_image_uses_explicit_physical_transform(self):
        self.identity['window_bounds'] = {'x': -2800, 'y': 10, 'width': 2560, 'height': 100}
        self.document['source']['x'] = -3000
        self.service.original.return_value = Image.new('RGB', (3000, 200), 'blue')
        uia._remember_observation(self.observed)
        uia.observe_geometry.return_value = copy.deepcopy(self.identity)
        self.answer['point'] = {'x': 1279.99, 'y': 49.99}
        result = self.call()
        self.assertEqual(result['desktop_point'], {'x': -241, 'y': 109})
        self.assertEqual(result['transform']['scale_x'], 2)
        self.assertEqual((result['image_width'], result['image_height']), (1280, 50))

    def test_malformed_and_action_like_responses_rejected(self):
        valid = json.dumps(self.answer)
        for text in ['print("click")', valid[:-1]+',"click":true}', valid.replace('"x": 99.99', '"x": 99.99,"x": 2'),
                     valid.replace('99.99', 'true'), valid.replace('99.99', '100'), valid.replace('0.95', 'NaN')]:
            self.service.adapter.route.side_effect = lambda *a, **k: {'ok': True, 'route': self.route, 'message': {'content': text}}
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.call()

    def test_pixel_change_during_inference_rejects_proposal(self):
        self.service.original.side_effect = [self.image, Image.new('RGB', self.image.size, 'red')]
        with self.assertRaisesRegex(ValueError, 'STALE_OBSERVATION'):
            self.call()

    def test_expired_inference_does_not_refresh_token(self):
        def late(*args, **kwargs):
            stale = copy.deepcopy(self.observed)
            stale['observation']['completed_monotonic'] -= 20
            uia._remember_observation(stale)
            return {'ok': True, 'route': self.route, 'message': {'content': json.dumps(self.answer)}}
        self.service.adapter.route.side_effect = late
        with self.assertRaisesRegex(ValueError, 'STALE_OBSERVATION'):
            self.call()
        self.service.capture.assert_not_called()

    def test_unexpected_route_is_rejected(self):
        self.route['provider'] = 'fallback'
        with self.assertRaisesRegex(ValueError, 'VISION_ROUTE_MISMATCH'):
            self.call()
        self.service.capture.assert_not_called()

    def test_cancelled_and_invalid_provider_response(self):
        cancel = threading.Event(); cancel.set()
        with self.assertRaisesRegex(ValueError, 'cancelado'):
            self.call(cancelled=cancel)
        self.service.adapter.route.assert_not_called()
        for response in [{'ok': False}, {'ok': True, 'route': self.route, 'message': None}]:
            self.service.adapter.route.side_effect = None
            self.service.adapter.route.return_value = response
            with self.assertRaises(ValueError):
                self.call()


if __name__ == '__main__':
    unittest.main()
