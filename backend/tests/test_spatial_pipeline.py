import json
import tempfile
import unittest
from pathlib import Path

from backend.presentation_plan import PlanError
from backend.shape_registry import ShapeRegistry
from backend.spatial_pipeline import blueprint_context, catalog_matches, parse_blueprint, repair_message
from backend.spend_budget import ASSUMED_PRICES, BudgetExceeded, SpendBudget, estimate_usd, is_metered, prices_for

BLUEPRINT = {'objeto': 'Motor eléctrico de CC con escuadra', 'categoria': 'electrico', 'descripcion': 'Motor cilíndrico con eje y soporte.', 'vista': 'tres cuartos',
             'componentes': [{'nombre': 'Carcasa', 'forma': 'cilindro', 'proporcion': '60 % del largo', 'material': 'acero'}, {'nombre': 'Rodamiento del eje', 'forma': 'anillo', 'proporcion': 'pequeño', 'material': 'acero'},
                             {'nombre': 'Escuadra de montaje', 'forma': 'placa en L', 'proporcion': '40 % del ancho', 'material': 'metal negro'}],
             'proporcion_global': '3:2:2', 'simetria': 'axial', 'buscar': ['rodamiento', 'escuadra', 'tornillo'], 'dudas': ['no se ve la parte trasera']}


class BlueprintTests(unittest.TestCase):
    def test_a_valid_identification_is_cleaned_and_bounded(self):
        raw = dict(BLUEPRINT, componentes=[{'nombre': f'pieza {i}', 'forma': 'caja ' * 60, 'proporcion': '', 'material': ''} for i in range(40)], objeto='  Motor\n\n eléctrico  ')
        parsed = parse_blueprint('```json\n' + json.dumps(raw) + '\n```')
        self.assertEqual(parsed['objeto'], 'Motor eléctrico')
        self.assertEqual(len(parsed['componentes']), 14)
        self.assertLessEqual(len(parsed['componentes'][0]['forma']), 80)

    def test_an_identification_without_an_object_or_not_json_is_rejected_so_the_service_can_carry_on_without_it(self):
        for text in ('no es json', json.dumps({'categoria': 'mueble'}), json.dumps([1, 2]), json.dumps({'objeto': '   '})):
            with self.subTest(text=text), self.assertRaises(PlanError):
                parse_blueprint(text)

    def test_retrieval_finds_catalog_parts_that_match_what_was_identified_and_ignores_the_rest(self):
        matches = catalog_matches(ShapeRegistry(), parse_blueprint(json.dumps(BLUEPRINT)))
        ids = [m['id'] for m in matches]
        self.assertIn('ball_bearing', ids)  # "rodamiento" asked for explicitly
        self.assertIn('l_bracket', ids)  # "escuadra"
        self.assertNotIn('butterfly_valve', ids)
        self.assertLessEqual(len(matches), 8)
        self.assertEqual(matches, sorted(matches, key=lambda m: (-m['score'], m['id'])))
        unrelated = parse_blueprint(json.dumps({'objeto': 'Nube de tormenta', 'categoria': 'natural', 'buscar': ['vapor']}))
        self.assertEqual(catalog_matches(ShapeRegistry(), unrelated), [])

    def test_the_context_carries_the_identification_the_doubts_and_the_catalog_hint(self):
        blueprint = parse_blueprint(json.dumps(BLUEPRINT))
        text = blueprint_context(blueprint, catalog_matches(ShapeRegistry(), blueprint))
        for needle in ('Motor eléctrico de CC con escuadra', 'Rodamiento del eje', 'no se ve la parte trasera', 'PIEZAS DEL CATÁLOGO', 'ball_bearing', 'component'):
            self.assertIn(needle, text)
        self.assertNotIn('PIEZAS DEL CATÁLOGO', blueprint_context(blueprint, []))

    def test_the_repair_message_names_the_error_and_asks_for_a_compact_plan_when_the_answer_was_cut(self):
        self.assertIn('campos ausentes', repair_message('Plan tiene campos ausentes: [scene]'))
        self.assertIn('se cortó por longitud', repair_message('x', length=True))
        self.assertLessEqual(len(repair_message('e' * 5000)), 1000)


class SpendBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'spend.json'
        self.clock = lambda: 1000.0
        self.paid = {'name': 'axx1', 'model': 'claude-sonnet-5-5', 'kind': 'anthropic', 'protocol': 'anthropic', 'billing_allowed': True}
        self.usage = {'input_tokens': 1000, 'output_tokens': 2000, 'cache_creation_input_tokens': 8000, 'cache_read_input_tokens': 0}

    def test_cost_uses_the_connection_prices_or_the_stated_assumption_and_the_cache_terms(self):
        self.assertTrue(prices_for(self.paid)['assumed'])
        expected = (1000 * 3 + 8000 * 3 * 1.25 + 2000 * 15) / 1_000_000
        self.assertAlmostEqual(estimate_usd(self.usage, prices_for(self.paid)), expected)
        own = dict(self.paid, usd_per_mtok_in=1.0, usd_per_mtok_out=5.0)
        self.assertFalse(prices_for(own)['assumed'])
        self.assertAlmostEqual(estimate_usd(self.usage, prices_for(own)), (1000 + 8000 * 1.25 + 2000 * 5) / 1_000_000)
        self.assertEqual(estimate_usd({'input_tokens': True, 'output_tokens': -5}, prices_for(self.paid)), 0)  # junk never counts
        self.assertEqual(ASSUMED_PRICES, {'in': 3.0, 'out': 15.0})

    def test_only_paid_connections_are_metered(self):
        self.assertTrue(is_metered(self.paid))
        for free in ({'name': '@codex'}, {'name': 'a', 'kind': 'ollama_cloud'}, {'name': 'b', 'kind': 'ollama'}, {'name': 'c', 'free_confirmed': True}):
            self.assertFalse(is_metered(free), free)
        budget = SpendBudget(self.path, self.clock)
        self.assertEqual(budget.record({'name': '@codex'}, self.usage), 0.0)
        self.assertEqual(budget.summary()['spent_usd'], 0)

    def test_the_ceiling_stops_paid_calls_but_never_free_ones_and_survives_a_restart(self):
        budget = SpendBudget(self.path, self.clock)
        self.assertEqual(budget.summary()['limit_usd'], 5.0)
        budget.configure(limit_usd=0.05)
        budget.check(self.paid)  # nothing spent yet
        cost = budget.record(self.paid, self.usage, 'plan')
        self.assertGreater(cost, 0.05)
        with self.assertRaises(BudgetExceeded) as caught:
            budget.check(self.paid)
        self.assertIn('presupuesto', str(caught.exception).lower())
        budget.check({'name': '@codex'})  # a subscription still works
        reopened = SpendBudget(self.path, self.clock)
        self.assertEqual(reopened.summary()['spent_usd'], round(cost, 4))
        with self.assertRaises(BudgetExceeded):
            reopened.check(self.paid)
        stored = self.path.read_text(encoding='utf-8')
        self.assertNotIn('prompt', stored)  # only numbers are kept

    def test_the_owner_can_raise_the_ceiling_or_start_again_and_bad_values_are_refused(self):
        budget = SpendBudget(self.path, self.clock)
        budget.configure(limit_usd=0.01); budget.record(self.paid, self.usage)
        with self.assertRaises(BudgetExceeded):
            budget.check(self.paid)
        self.assertEqual(budget.configure(limit_usd=5)['remaining_usd'], round(5 - budget.spent(), 4))
        budget.check(self.paid)
        self.assertEqual(budget.configure(reset=True)['spent_usd'], 0)
        for bad in (0, -1, 5000, True, 'cinco'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                budget.configure(limit_usd=bad)

    def test_a_damaged_ledger_falls_back_to_a_clean_default(self):
        self.path.write_text('{no json', encoding='utf-8')
        self.assertEqual(SpendBudget(self.path, self.clock).summary()['limit_usd'], 5.0)


if __name__ == '__main__':
    unittest.main()
