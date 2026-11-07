"""HTTP Integration tests for Axx Magic Pen Spatial Presentation Plan endpoint."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from PIL import Image
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.magic_pen import MagicPenService


class SpatialHTTPTests(unittest.TestCase):
    def test_spatial_plan_endpoint_ollama_and_gpt_fast(self):
        with tempfile.TemporaryDirectory() as root:
            class MockAdapter:
                config = {'allow_paid': False, 'providers': [
                    {'name': 'ollama', 'model': 'gemma4:31b', 'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']},
                    {'name': 'openai', 'model': 'gpt-6.1-sol-fast', 'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']}
                ]}
                def __init__(self):
                    self.calls = []
                def route(self, req):
                    self.calls.append(req)
                    model = req.get('model', '')
                    if 'gpt-6.1-sol-fast' in model:
                        content = (
                            "```json\n"
                            "{\n"
                            '  "mode": "interactive_3d",\n'
                            '  "summary": "Pistón 3D procedural.",\n'
                            '  "annotations_2d": [{"type": "box", "target_box_normalized": [0.1, 0.1, 0.9, 0.9], "label": "Pistón"}],\n'
                            '  "scene_3d": {\n'
                            '    "root_primitives": [{\n'
                            '      "id": "piston_1",\n'
                            '      "type": "cylinder",\n'
                            '      "dimensions": [1, 3, 1],\n'
                            '      "position": [0, 0, 0]\n'
                            '    }]\n'
                            '  }\n'
                            "}\n"
                            "```"
                        )
                    else:
                        content = "Resumen: Imagen capturada con un botón azul.\n\nDetalle: Ubicado en la parte superior."
                    return {'ok': True, 'message': {'content': content}}
                def cancel(self, request_id):
                    return True

            adapter = MockAdapter()
            pen = MagicPenService(Path(root), adapter=adapter)
            doc = pen.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'fixture'})
            pen.save({'id': doc['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]}, 'strokes': []})

            handler = type('SpatialHandler', (AxxBridgeHandler,), {'magic_pen': pen})
            server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def request(operation, body):
                headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + server.host_token}
                req = urllib.request.Request(
                    f'http://127.0.0.1:{server.server_port}/axx-api/pen/{operation}',
                    data=json.dumps(body).encode(),
                    headers=headers
                )
                with opener.open(req, timeout=5) as resp:
                    return resp.status, json.load(resp)

            try:
                # 1. Check capabilities endpoint returns spatial_3d_supported
                st_status, st_body = request('status', {})
                self.assertEqual(st_status, 200)
                self.assertTrue(st_body['capabilities']['spatial_3d_supported'])

                # 2. Query with Ollama -> Must receive 2D overlay plan only
                q_ollama_id = '0123456789abcdef0123456789abcdef'
                req_ollama = {
                    'id': doc['id'],
                    'revision': 2,
                    'question': 'Explica esto con Ollama',
                    'provider': 'ollama',
                    'model': 'gemma4:31b',
                    'request_id': q_ollama_id
                }
                s_code, q_res = request('start', req_ollama)
                self.assertEqual(s_code, 200)

                # Wait for completion
                for _ in range(50):
                    time.sleep(0.05)
                    _, q_info = request('query', {'id': doc['id'], 'query_id': q_ollama_id})
                    if q_info['state'] == 'completed':
                        break

                self.assertEqual(q_info['state'], 'completed')
                plan_ollama = q_info.get('spatial_plan')
                self.assertIsNotNone(plan_ollama)
                self.assertEqual(plan_ollama['mode'], 'overlay_2d')
                self.assertIsNone(plan_ollama['scene_3d'])
                self.assertFalse(plan_ollama['provider_gating']['spatial_3d_allowed'])

                # Check spatial_plan direct endpoint
                sp_code, sp_plan = request('spatial_plan', {'id': doc['id'], 'query_id': q_ollama_id})
                self.assertEqual(sp_code, 200)
                self.assertEqual(sp_plan['mode'], 'overlay_2d')
                self.assertFalse(sp_plan['provider_gating']['spatial_3d_allowed'])

                # 3. Query with GPT-6.1 Sol Fast -> Must receive interactive_3d plan
                q_gpt_id = 'fedcba9876543210fedcba9876543210'
                req_gpt = {
                    'id': doc['id'],
                    'revision': 2,
                    'question': 'Explica esto en 3D con GPT Sol Fast',
                    'provider': 'openai',
                    'model': 'gpt-6.1-sol-fast',
                    'request_id': q_gpt_id
                }
                s_code, q_gpt_res = request('start', req_gpt)
                self.assertEqual(s_code, 200)

                # Wait for completion
                for _ in range(50):
                    time.sleep(0.05)
                    _, q_gpt_info = request('query', {'id': doc['id'], 'query_id': q_gpt_id})
                    if q_gpt_info['state'] == 'completed':
                        break

                self.assertEqual(q_gpt_info['state'], 'completed')
                plan_gpt = q_gpt_info.get('spatial_plan')
                self.assertIsNotNone(plan_gpt)
                self.assertEqual(plan_gpt['mode'], 'interactive_3d')
                self.assertIsNotNone(plan_gpt['scene_3d'])
                self.assertEqual(len(plan_gpt['scene_3d']['root_primitives']), 1)
                self.assertEqual(plan_gpt['scene_3d']['root_primitives'][0]['type'], 'cylinder')
                self.assertTrue(plan_gpt['provider_gating']['spatial_3d_allowed'])

                # Check spatial_plan direct endpoint for GPT query
                sp_code, sp_gpt_plan = request('spatial_plan', {'id': doc['id'], 'query_id': q_gpt_id})
                self.assertEqual(sp_code, 200)
                self.assertEqual(sp_gpt_plan['mode'], 'interactive_3d')
                self.assertTrue(sp_gpt_plan['provider_gating']['spatial_3d_allowed'])

            finally:
                pen.close()
                server.shutdown()
                server.server_close()
                thread.join(2)


if __name__ == '__main__':
    unittest.main()

