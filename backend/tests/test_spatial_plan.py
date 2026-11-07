"""Tests for Spatial Presentation Plan schema validation and model gating."""
import unittest
from backend.spatial_plan import (
    is_gpt_fast_model,
    validate_spatial_plan,
    extract_or_build_spatial_plan,
    get_perception_contract,
    ALLOWED_PRIMITIVES,
    ALLOWED_ANNOTATION_TYPES
)


class SpatialPlanTests(unittest.TestCase):
    def test_provider_gating_allows_only_gpt_fast(self):
        # Must allow gpt-6.1-sol-fast
        self.assertTrue(is_gpt_fast_model('openai', 'gpt-6.1-sol-fast'))
        self.assertTrue(is_gpt_fast_model('chatgpt', 'gpt-6.1-sol-fast'))
        self.assertTrue(is_gpt_fast_model('', 'gpt-6.1-sol-fast'))
        self.assertTrue(is_gpt_fast_model('openai', 'gpt-6-fast'))

        # Must reject Ollama and local models unconditionally
        self.assertFalse(is_gpt_fast_model('ollama', 'gemma4:31b'))
        self.assertFalse(is_gpt_fast_model('ollama', 'qwen3:4b'))
        self.assertFalse(is_gpt_fast_model('ollama', 'llama3.2-vision'))
        self.assertFalse(is_gpt_fast_model('lmstudio', 'qwen2-vl'))
        self.assertFalse(is_gpt_fast_model('local', 'mistral-vision'))
        self.assertFalse(is_gpt_fast_model('ollama', 'gpt-6.1-sol-fast-spoof'))

    def test_3d_mode_degrades_to_2d_when_not_allowed(self):
        plan = {
            'mode': 'interactive_3d',
            'summary': 'Explicación de un cilindro',
            'annotations_2d': [{'type': 'box', 'target_box_normalized': [0.1, 0.1, 0.5, 0.5], 'label': 'Cilindro'}],
            'scene_3d': {
                'root_primitives': [{
                    'id': 'p1',
                    'type': 'cylinder',
                    'dimensions': [1.0, 2.0, 1.0],
                    'position': [0, 0, 0]
                }]
            }
        }
        # When spatial_3d_allowed=False (e.g. Ollama):
        validated = validate_spatial_plan(plan, spatial_3d_allowed=False, provider_name='ollama', model_name='gemma4:31b')
        self.assertEqual(validated['mode'], 'overlay_2d')
        self.assertIsNone(validated['scene_3d'])
        self.assertEqual(validated['provider_gating']['spatial_3d_allowed'], False)
        self.assertEqual(validated['provider_gating']['gating_status'], '2d_only')

    def test_3d_mode_accepted_when_allowed_and_valid(self):
        plan = {
            'mode': 'interactive_3d',
            'summary': 'Motor conceptual en 3D',
            'annotations_2d': [{'type': 'box', 'target_box_normalized': [0.1, 0.2, 0.8, 0.9], 'label': 'Pistón'}],
            'scene_3d': {
                'root_primitives': [{
                    'id': 'piston_1',
                    'type': 'cylinder',
                    'dimensions': [2.0, 5.0, 2.0],
                    'position': [0.0, 1.0, 0.0],
                    'rotation': [0.0, 0.0, 0.0],
                    'color': '#ff5500',
                    'exploded_offset': [0.0, 2.0, 0.0]
                }]
            }
        }
        validated = validate_spatial_plan(plan, spatial_3d_allowed=True, provider_name='openai', model_name='gpt-6.1-sol-fast')
        self.assertEqual(validated['mode'], 'interactive_3d')
        self.assertIsNotNone(validated['scene_3d'])
        self.assertEqual(len(validated['scene_3d']['root_primitives']), 1)
        prim = validated['scene_3d']['root_primitives'][0]
        self.assertEqual(prim['type'], 'cylinder')
        self.assertEqual(prim['color'], '#ff5500')
        self.assertEqual(validated['provider_gating']['spatial_3d_allowed'], True)
        self.assertEqual(validated['provider_gating']['gating_status'], 'active')

    def test_rejects_arbitrary_or_malicious_inputs(self):
        plan = {
            'mode': 'interactive_3d',
            'summary': '<script>alert(1)</script>Explique',
            'annotations_2d': [{
                'type': 'invalid_type',
                'target_box_normalized': [float('nan'), -5.0, 10.0, float('inf')],
                'label': '<script>steal()</script>Etiqueta',
                'color': 'bad-color'
            }],
            'scene_3d': {
                'root_primitives': [{
                    'id': 'm1',
                    'type': 'unsupported_mesh_type',
                    'dimensions': [float('inf'), 1, 1],
                    'position': [0, 0, 0]
                }]
            }
        }
        validated = validate_spatial_plan(plan, spatial_3d_allowed=True, provider_name='openai', model_name='gpt-6.1-sol-fast')
        self.assertNotIn('<script>', validated['summary'])
        self.assertEqual(len(validated['annotations_2d']), 1)
        ann = validated['annotations_2d'][0]
        self.assertEqual(ann['type'], 'box')  # defaulted
        self.assertNotIn('<script>', ann['label'])
        self.assertEqual(ann['color'], '#38bdf8')  # defaulted
        self.assertEqual(ann['target_box_normalized'], [0.0, 0.0, 1.0, 1.0])  # defaulted due to nan/inf
        # Since the only primitive was unsupported, scene_3d should be None and mode fell back to overlay_2d
        self.assertEqual(validated['mode'], 'overlay_2d')
        self.assertIsNone(validated['scene_3d'])

    def test_extract_from_plain_text_ollama_response(self):
        ollama_response = (
            "Resumen: La zona contiene un panel de control con un botón de encendido.\n\n"
            "Detalle: Se puede observar el botón marcado en la parte superior derecha."
        )
        plan = extract_or_build_spatial_plan(
            ollama_response,
            spatial_3d_allowed=False,
            provider_name='ollama',
            model_name='gemma4:31b'
        )
        self.assertEqual(plan['mode'], 'overlay_2d')
        self.assertIsNone(plan['scene_3d'])
        self.assertEqual(plan['summary'], 'La zona contiene un panel de control con un botón de encendido.')
        self.assertEqual(len(plan['annotations_2d']), 1)
        self.assertEqual(plan['provider_gating']['spatial_3d_allowed'], False)

    def test_extract_from_json_code_fence(self):
        gpt_response = (
            "Aquí está la explicación en 3D:\n"
            "```json\n"
            "{\n"
            '  "mode": "interactive_3d",\n'
            '  "summary": "Pistón hidráulico en vista espacial.",\n'
            '  "annotations_2d": [{"type": "callout", "target_box_normalized": [0.2, 0.2, 0.6, 0.6], "label": "Eje central"}],\n'
            '  "scene_3d": {\n'
            '    "root_primitives": [{\n'
            '      "id": "shaft_1",\n'
            '      "type": "shaft",\n'
            '      "dimensions": [1, 4, 1],\n'
            '      "position": [0, 0, 0]\n'
            '    }]\n'
            '  }\n'
            "}\n"
            "```"
        )
        plan = extract_or_build_spatial_plan(
            gpt_response,
            spatial_3d_allowed=True,
            provider_name='openai',
            model_name='gpt-6.1-sol-fast'
        )
        self.assertEqual(plan['mode'], 'interactive_3d')
        self.assertEqual(plan['summary'], 'Pistón hidráulico en vista espacial.')
        self.assertIsNotNone(plan['scene_3d'])
        self.assertEqual(plan['scene_3d']['root_primitives'][0]['type'], 'shaft')

    def test_perception_contracts(self):
        c_2d = get_perception_contract(spatial_3d_allowed=False)
        self.assertIn('señalar elementos', c_2d)
        self.assertIn('annotations_2d', c_2d)

        c_3d = get_perception_contract(spatial_3d_allowed=True)
        self.assertIn('interactive_3d', c_3d)
        self.assertIn('SpatialPresentationPlan', c_3d)

    def test_extract_from_text_coordinates_for_gemma(self):
        gemma_response = (
            "He analizado la imagen y localicé estos componentes:\n"
            "- Flecha hacia [0.15, 0.20, 0.35, 0.40] Chip principal ARM\n"
            "- Spotlight en [0.55, 0.60, 0.70, 0.75] Botón de encendido\n"
            "- [0.80, 0.10, 0.95, 0.30] Puerto USB-C\n"
            "Resumen: Placa con 3 elementos identificados."
        )
        plan = extract_or_build_spatial_plan(
            gemma_response,
            spatial_3d_allowed=False,
            provider_name='ollama',
            model_name='gemma4:31b'
        )
        self.assertEqual(plan['mode'], 'diagram_2d')
        self.assertEqual(len(plan['annotations_2d']), 3)
        self.assertEqual(plan['annotations_2d'][0]['type'], 'arrow')
        self.assertEqual(plan['annotations_2d'][0]['label'], 'Chip principal ARM')
        self.assertEqual(plan['annotations_2d'][1]['type'], 'spotlight')
        self.assertEqual(plan['annotations_2d'][1]['label'], 'Botón de encendido')
        self.assertEqual(plan['annotations_2d'][2]['type'], 'box')
        self.assertIsNone(plan['scene_3d'])


if __name__ == '__main__':
    unittest.main()

