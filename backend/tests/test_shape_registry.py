import tempfile
from pathlib import Path
import unittest

from backend.shape_registry import ShapeRegistry, TECHNICAL_COMPONENTS, catalog_text, expand_component_refs


class ShapeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'dynamic_shapes.json'
        self.registry = ShapeRegistry(persistence_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_catalog_contains_at_least_20_components(self):
        components = self.registry.list_components()
        self.assertGreaterEqual(len(components), 20)
        self.assertGreaterEqual(len(TECHNICAL_COMPONENTS), 20)

    def test_instantiate_component_with_custom_scale_and_position(self):
        # Instantiate hex_bolt with 2x scale and offset
        parts = self.registry.instantiate('hex_bolt', scale=2.0, position=(1.0, 2.0, 3.0), color='#ff0000')
        self.assertGreaterEqual(len(parts), 2)
        head = parts[0]
        self.assertEqual(head['color'], '#ff0000')
        self.assertEqual(head['shape'], 'hexprism')
        # Scaled size: 0.7 * 2 = 1.4
        self.assertAlmostEqual(head['size'][0], 1.4, places=2)
        # Position offset: 1.0 + 0 = 1.0, 2.0 + 0.7*2 = 3.4
        self.assertAlmostEqual(head['position'][0], 1.0, places=2)
        self.assertAlmostEqual(head['position'][1], 3.4, places=2)

    def test_match_shape_by_alias_and_synonym(self):
        # Match 'tornillo' -> 'hex_bolt'
        match = self.registry.match_shape('Tornillo de fijación')
        self.assertIsNotNone(match)
        cid, comp = match
        self.assertEqual(cid, 'hex_bolt')

        # Match 'engranaje' -> 'spur_gear'
        match = self.registry.match_shape('engranaje')
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 'spur_gear')

        # Match 'rodamiento' -> 'ball_bearing'
        match = self.registry.match_shape('rodamiento')
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 'ball_bearing')

    def test_analyze_and_integrate_reuses_shapes_and_registers_new_ones(self):
        parts_to_analyze = [
            'tornillo hexagonal',
            'rodamiento principal',
            {'label': 'carcasa_especial_alfa', 'shape': 'box', 'size': [2.5, 1.2, 1.8], 'material': 'metal_anodized'},
        ]
        result = self.registry.analyze_and_integrate(parts_to_analyze, auto_register_missing=True)

        self.assertEqual(result['reused_from_catalog'], 2)  # hex_bolt and ball_bearing
        self.assertEqual(result['newly_registered'], 1)     # carcasa_especial_alfa
        self.assertGreaterEqual(len(result['objects']), 4)

        # Confirm the new shape was persisted into the registry
        self.assertTrue(self.registry.has_shape('dynamic_carcasa_especial_alfa'))

        # Create a new registry pointing to the same file and verify persistence
        new_reg = ShapeRegistry(persistence_path=self.db_path)
        self.assertTrue(new_reg.has_shape('dynamic_carcasa_especial_alfa'))
        restored = new_reg.get_shape('dynamic_carcasa_especial_alfa')
        self.assertEqual(restored['label'], 'carcasa_especial_alfa')

    def test_catalog_has_29_components_and_compact_text(self):
        self.assertGreaterEqual(len(TECHNICAL_COMPONENTS), 29)
        text = catalog_text(self.registry)
        self.assertIn('spur_gear', text)
        self.assertIn('knurled_knob', text)

    def test_every_component_uses_renderable_shapes(self):
        from backend.presentation_plan import SHAPES
        for cid, comp in TECHNICAL_COMPONENTS.items():
            for part in comp['parts']:
                self.assertIn(part['shape'], SHAPES, f'{cid}: {part["shape"]}')

    def test_expand_component_refs(self):
        objects = [
            {'id': 'o1', 'label': 'Carcasa', 'shape': 'box', 'size': [4, 2, 2], 'position': [0, 0, 0], 'color': '#555555'},
            {'id': 'o2', 'component': 'ball_bearing', 'label': 'Rodamiento delantero', 'scale': 0.5, 'position': [2, 0, 0]},
        ]
        out = expand_component_refs(objects, self.registry)
        self.assertEqual(len(out), 4)
        self.assertEqual(len({o['id'] for o in out}), 4)
        self.assertTrue(out[1]['label'].startswith('Rodamiento delantero'))
        self.assertEqual(out[1]['axx_component'], 'o2')
        with self.assertRaises(ValueError):
            expand_component_refs([{'id': 'o1', 'component': 'no_existe'}], self.registry)
