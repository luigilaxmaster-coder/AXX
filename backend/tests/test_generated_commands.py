"""Real pure-code interpretation and durable, explicitly reviewed registration."""
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.capability_workshop import CapabilityWorkshop
from backend.commands import CommandService
from backend.connect.provider import ProviderError
from backend.generated_commands import (GeneratedTool, Interpreter, LIMITS, parse_source,
                                         run_tests, run_transform, source_digest,
                                         validate_arguments, validate_schema)


def transform(source='def run(inputs):\n    return " ".join(inputs["text"].strip().lower().split())'):
    return {'kind': 'python_transform', 'title': 'Normalizar texto',
            'objective': 'Quitar espacios repetidos y convertir a minúsculas',
            'source': source, 'schema': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                                        'required': ['text']}, 'output_schema': {'type': 'string'},
            'tests': [{'inputs': {'text': ' AXX  FUNCIONA '}, 'expected': 'axx funciona'},
                      {'inputs': {'text': ''}, 'expected': ''}],
            'readme': 'Transformación pura sin I/O. Revisar la fuente y los casos antes de activar.'}


class GeneratedInterpreterTests(unittest.TestCase):
    def test_interpreter_wall_clock_budget_is_independent_of_steps_and_resets_per_run(self):
        interpreter = Interpreter('def run(inputs):\n    return 1')
        with patch('backend.generated_commands.time.monotonic', side_effect=[0, 2.0]), \
                self.assertRaisesRegex(ValueError, 'tiempo de la transformación'):
            interpreter.run({})
        with patch('backend.generated_commands.time.monotonic', return_value=10):
            self.assertEqual(interpreter.run({}), 1)
        cancelled = threading.Event()
        cancelled.set()
        with patch('backend.generated_commands.time.monotonic', side_effect=[0]), \
                self.assertRaisesRegex(ValueError, 'cancelada'):
            Interpreter('def run(inputs):\n    return 1', cancelled).run({})

    def test_self_test_total_deadline_marks_every_unexecuted_case_failed(self):
        definition = transform()
        definition['tests'] = [copy.deepcopy(definition['tests'][0]) for _ in range(3)]
        with patch('backend.generated_commands.time.monotonic', side_effect=[0, 0, 0, 10.0]), \
                patch('backend.generated_commands.run_transform', return_value=definition['tests'][0]['expected']) as run:
            result = run_tests(definition)
        self.assertFalse(result['self_tests_passed'])
        self.assertEqual(len(result['tests']), 3)
        self.assertTrue(result['tests'][0]['passed'])
        self.assertTrue(result['tests'][0]['executed'])
        self.assertTrue(all(not row['passed'] and not row['executed'] and 'tiempo' in row['error'] for row in result['tests'][1:]))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs['deadline'], 10.0)

    def test_total_self_test_budget_and_cancellation_never_report_partial_success(self):
        definition = transform()
        with patch('backend.generated_commands.time.monotonic', side_effect=[0, 0, 10.0, 10.0]), \
                patch('backend.generated_commands.run_transform', return_value=definition['tests'][0]['expected']):
            result = run_tests(definition)
        self.assertFalse(result['self_tests_passed'])
        self.assertTrue(result['tests'][0]['executed'])
        self.assertFalse(result['tests'][0]['passed'])
        self.assertFalse(result['tests'][1]['executed'])
        cancelled = threading.Event()
        cancelled.set()
        with patch('backend.generated_commands.run_transform') as run:
            result = run_tests(definition, cancelled)
        run.assert_not_called()
        self.assertEqual(len(result['tests']), len(definition['tests']))
        self.assertFalse(result['self_tests_passed'])
        self.assertTrue(all(not row['executed'] and 'cancelada' in row['error'] for row in result['tests']))

    def test_interpreter_obeys_earlier_global_deadline(self):
        with patch('backend.generated_commands.time.monotonic', side_effect=[9.5, 10.0]), \
                self.assertRaisesRegex(ValueError, 'tiempo de la transformación'):
            Interpreter('def run(inputs):\n    return 1', deadline=10.0).run({})

    def test_text_math_lists_dicts_conditionals_and_local_loops(self):
        definition = transform()
        self.assertTrue(run_tests(definition)['self_tests_passed'])
        source = ('def run(inputs):\n    total = 0\n    rows = []\n'
                  '    for value in inputs["values"]:\n        if value > 0:\n'
                  '            total += value\n            rows = rows + [round(value * 1.2, 2)]\n'
                  '    return {"total": total, "values": sorted(rows)}')
        schema = {'type': 'object', 'properties': {'values': {'type': 'array', 'items': {'type': 'number'}}}, 'required': ['values']}
        output = {'type': 'object', 'properties': {'total': {'type': 'number'}, 'values': {'type': 'array', 'items': {'type': 'number'}}},
                  'required': ['total', 'values']}
        self.assertEqual(run_transform(source, {'values': [3, -2, 1]}, schema, output), {'total': 4, 'values': [1.2, 3.6]})

    def test_input_is_private_and_never_mutated(self):
        values = {'values': ['original']}
        source = 'def run(inputs):\n    rows = inputs["values"]\n    rows += ["local"]\n    return rows'
        self.assertEqual(Interpreter(source).run(values), ['original', 'local'])
        self.assertEqual(values, {'values': ['original']})
        returned = Interpreter('def run(inputs):\n    return inputs').run(values)
        returned['values'].append('outside')
        self.assertEqual(values, {'values': ['original']})

    def test_non_json_inputs_and_schema_inconsistency_fail_closed(self):
        schema = validate_schema(transform()['schema'], input_schema=True)
        for value in [{'text': True}, {}, {'text': 'ok', 'extra': 1}, {'text': object()}]:
            with self.subTest(value=value), self.assertRaises(ValueError): validate_arguments(schema, value)
        for schema in [{'$ref': 'http://external/'}, {'type': 'object', 'additionalProperties': True},
                       {'type': 'string', 'pattern': '(a+)+'}, {'type': 'array'},
                       {'type': 'integer', 'minimum': 5, 'maximum': 2},
                       {'type': 'object', 'properties': {'a': {}}, 'required': ['a']}]:
            with self.subTest(schema=schema), self.assertRaises(ValueError): validate_schema(schema)

    def test_ast_denies_io_imports_introspection_and_mutation_even_if_unreachable(self):
        bodies = ['import os\n    return "x"', 'return __import__("os")', 'return open("secret")',
                  'return exec("x=1")', 'return eval("1")', 'return inputs.__class__',
                  'return inputs["text"].__class__.__mro__', 'return inputs["text"].lower',
                  'return getattr(inputs, "text")', 'return (lambda: 1)()',
                  'inputs["text"] = "changed"\n    return inputs',
                  'rows = inputs\n    rows["text"] = "changed"\n    return rows',
                  'rows = []\n    rows.append(1)\n    return rows',
                  'while True:\n        return 1', 'return [x for x in inputs]',
                  'def nested():\n        return 1\n    return nested()',
                  'if False:\n        import socket\n    return 1', 'return {**inputs}',
                  'return 2 ** 1000000', 'return inputs.get("text")',
                  'return "{0.__class__}".format(inputs)', 'global value\n    return 1']
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(ValueError): parse_source('def run(inputs):\n    ' + body)

    def test_resource_limits_cancel_infinite_work_and_excessive_allocations(self):
        sources = ['return "x" * 1000000', 'return range(1000000)', 'return 1000000000000 * 1000000000000',
                   'return float("NaN")', 'return "a".replace("a", "b" * 16000)',
                   'return inputs["text"].replace("a", "b" * 16000, -1)',
                   'count = 0\n    for x in range(1000):\n        for y in range(1000):\n            count += 1\n    return count']
        for body in sources:
            with self.subTest(body=body), self.assertRaises(ValueError): Interpreter('def run(inputs):\n    ' + body).run({'text': 'a' * 100})
        with self.assertRaises(ValueError): parse_source('def run(inputs):\n    return "' + 'x' * LIMITS['source_bytes'] + '"')
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaisesRegex(ValueError, 'cancelada'): Interpreter('def run(inputs):\n    return 1', cancelled).run({})
        class CancelDuringExecution:
            def __init__(self): self.calls = 0
            def is_set(self): self.calls += 1; return self.calls > 10
        with self.assertRaisesRegex(ValueError, 'cancelada'):
            Interpreter('def run(inputs):\n    for value in range(100):\n        value += 1\n    return value', CancelDuringExecution()).run({})

    def test_tests_use_actual_results_and_validate_output_schema(self):
        numeric = transform('def run(inputs):\n    return 7.0')
        numeric.update(output_schema={'type': 'number'}, tests=[{'inputs': {'text': ''}, 'expected': 7}])
        self.assertTrue(run_tests(numeric)['self_tests_passed'])
        wrong = transform('def run(inputs):\n    return "wrong"')
        result = run_tests(wrong)
        self.assertFalse(result['self_tests_passed']); self.assertEqual(result['tests'][0]['actual'], 'wrong')
        wrong = transform('def run(inputs):\n    return 1')
        result = run_tests(wrong)
        self.assertFalse(result['self_tests_passed']); self.assertIn('tipo string', result['tests'][0]['error'])

    def test_tool_checks_current_registration_cancellation_and_postconditions(self):
        definition = transform()
        key = 'axx.generated.' + 'a' * 32 + '.r1.' + 'b' * 16
        record = {'command_id': key, 'revision': 1, 'digest': 'b' * 64,
                  'description': definition['objective'], 'source': definition['source'],
                  'source_digest': source_digest(definition['source']),
                  'input_schema': validate_schema(definition['schema'], input_schema=True),
                  'output_schema': definition['output_schema']}
        tool = GeneratedTool(record); runtime = SimpleNamespace(dynamic_tools={key: tool})
        cancelled = threading.Event()
        result = tool.execute_admitted({'text': ' REAL '}, None, cancelled, runtime, 'fixture')
        self.assertTrue(result.success, result.error); self.assertEqual(result.output['result'], 'real')
        self.assertTrue(tool.verify_postconditions({}, result)[0])
        runtime.dynamic_tools.clear()
        denied = tool.execute_admitted({'text': ' REAL '}, None, cancelled, runtime, 'revoked')
        self.assertFalse(denied.success); self.assertIn('revocada', denied.error)
        runtime.dynamic_tools[key] = tool; cancelled.set()
        self.assertFalse(tool.execute_admitted({'text': ' REAL '}, None, cancelled, runtime, 'cancelled').success)
        result.output['result'] = 123
        self.assertFalse(tool.verify_postconditions({}, result)[0])


class FixtureModel:
    config = {'allow_paid': False}
    def __init__(self): self.answer = transform(); self.calls = []
    def route(self, request):
        self.calls.append(request)
        return {'ok': True, 'message': {'content': json.dumps(self.answer)}, 'route': {'model': 'offline-fixture'}}


class GeneratedWorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor); self.model = FixtureModel()
        self.learning = ActionLearning(self.commands, self.model); self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)

    def tearDown(self):
        self.workshop.close(); self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    @staticmethod
    def ref(item): return item['id'], item['revision'], item['digest']

    def active(self, value=None):
        item = self.workshop.create(value or transform())
        self.workshop.validate(*self.ref(item))
        reviewed = self.workshop.approve(*self.ref(item), confirmed=True)
        return self.workshop.activate(*self.ref(reviewed))

    def test_json_generation_tests_review_activation_real_execution_and_revoke(self):
        item = self.workshop.generate('Normalizar texto', kind='python_transform', model='fixture', provider_name='offline')
        self.assertEqual(item['state'], 'draft'); self.assertFalse(item['validation']['self_tests_passed'])
        self.assertEqual(self.workshop.active_generated_records(), [])
        self.assertFalse(self.model.calls[0]['allow_paid']); self.assertEqual(self.model.calls[0]['task'], 'code')
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item), confirmed=True)
        with self.assertRaises(ValueError): self.workshop.activate(*self.ref(item))
        validation = self.workshop.validate(*self.ref(item))
        self.assertTrue(validation['self_tests_passed']); self.assertEqual(validation['tested_digest'], item['digest'])
        self.assertEqual(validation['tests'][0]['actual'], 'axx funciona')
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item))
        item = self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(self.commands.operations(), [])
        item = self.workshop.activate(*self.ref(item)); self.assertEqual(item['state'], 'active')
        record = self.workshop.active_generated_records()[0]
        self.assertEqual(record['command_id'], item['command_id']); self.assertIn(item['command_id'], self.executor.dynamic_tools)
        operation = self.commands.prepare(item['command_id'], {'text': ' FUNCIONA   REAL '})
        done = self.commands.execute(operation['operation_id'], approved=True)
        self.assertEqual(done['state'], 'succeeded', done); self.assertTrue(done['postconditions_passed'])
        self.assertEqual(done['output']['result'], 'funciona real')
        self.assertEqual(done['evidence']['verification'], 'bounded_python_transform')
        pending = self.commands.prepare(item['command_id'], {'text': 'pending'})
        revoked = self.workshop.revoke(*self.ref(item)); self.assertIsNone(revoked['active_revision'])
        self.assertNotIn(item['command_id'], self.executor.dynamic_tools)
        self.assertNotEqual(self.commands.execute(pending['operation_id'], approved=True)['state'], 'succeeded')

    def test_failed_tests_cannot_be_approved_or_registered(self):
        item = self.workshop.create(transform('def run(inputs):\n    return "wrong"'))
        self.assertFalse(self.workshop.validate(*self.ref(item))['self_tests_passed'])
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(self.workshop.active_generated_records(), [])

    def test_selected_codex_provider_generates_through_same_strict_workshop_gates(self):
        class SelectedProvider:
            def __init__(self): self.calls = []
            def generate_capability(selected, request):
                selected.calls.append(request)
                return {'ok': True, 'message': {'content': json.dumps(transform())},
                        'route': {'model': request['model'], 'provider_name': '@codex'}}
        selected = SelectedProvider(); self.workshop.provider = selected
        item = self.workshop.generate('Normalizar texto', kind='python_transform', model='gpt-6.1-sol', provider_name='@codex')
        self.assertEqual(self.model.calls, []); self.assertEqual(len(selected.calls), 1)
        self.assertFalse(selected.calls[0]['allow_paid'])
        self.assertEqual(item['provenance']['route'], {'model': 'gpt-6.1-sol', 'provider_name': '@codex'})
        self.assertIsNone(item['approval']); self.assertFalse(item['validation']['self_tests_passed'])
        self.assertEqual(self.workshop.active_generated_records(), [])
        self.workshop.validate(*self.ref(item)); self.workshop.approve(*self.ref(item), confirmed=True)
        self.assertEqual(self.workshop.activate(*self.ref(item))['state'], 'active')

    def test_selected_codex_missing_or_failing_provider_never_falls_back(self):
        with self.assertRaises(ValueError):
            self.workshop.generate('Normalizar texto', kind='python_transform', model='gpt-6.1-sol', provider_name='@codex')
        class BrokenProvider:
            def generate_capability(selected, request): raise ProviderError('AUTH_REQUIRED', 'Conecta la cuenta seleccionada.')
        self.workshop.provider = BrokenProvider()
        with self.assertRaisesRegex(ValueError, 'Conecta la cuenta'):
            self.workshop.generate('Normalizar texto', kind='python_transform', model='gpt-6.1-sol', provider_name='@codex')
        self.assertEqual(self.model.calls, []); self.assertEqual(self.workshop.list(), [])

    def test_revision_rollback_and_revoke_keep_explicit_review_gate(self):
        first = self.active(); old_id = first['command_id']
        second = self.workshop.revise(*self.ref(first), transform() | {'title': 'Revisión dos'})
        self.assertIsNone(second['approval']); self.assertFalse(second['validation']['self_tests_passed'])
        self.assertEqual(self.workshop.active_generated_records()[0]['command_id'], old_id)
        with self.assertRaises(ValueError): self.workshop.approve(*self.ref(first), confirmed=True)
        restored = self.workshop.rollback(*self.ref(second), target_revision=1)
        self.assertEqual(restored['revision'], 3); self.assertEqual(restored['active_revision'], 1)
        self.assertIsNone(restored['approval']); self.assertFalse(restored['validation']['self_tests_passed'])
        self.assertEqual(self.workshop.active_generated_records()[0]['command_id'], old_id)
        self.workshop.validate(*self.ref(restored)); self.workshop.approve(*self.ref(restored), confirmed=True)
        active = self.workshop.activate(*self.ref(restored))
        self.assertEqual(active['active_revision'], 3); self.assertNotEqual(active['command_id'], old_id)
        self.assertNotIn(old_id, self.executor.dynamic_tools)
        self.workshop.revoke(*self.ref(active)); self.assertEqual(self.workshop.active_generated_records(), [])

    def test_active_revision_reconstructs_after_restart(self):
        item = self.active()
        self.workshop.close(); self.learning.close()
        self.commands.refresh_generated_catalog([])
        self.assertNotIn(item['command_id'], self.executor.dynamic_tools)
        self.learning = ActionLearning(self.commands, self.model); self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)
        recovered = self.workshop.get(item['id']); self.assertEqual(recovered['approval'], item['approval'])
        self.assertIn(item['command_id'], self.executor.dynamic_tools)
        operation = self.commands.prepare(item['command_id'], {'text': ' REINICIO '})
        self.assertEqual(self.commands.execute(operation['operation_id'], True)['output']['result'], 'reinicio')

    def test_tampered_definition_and_tool_source_cannot_execute(self):
        item = self.active(); record = self.workshop.active_generated_records()[0]
        record['source'] = 'def run(inputs):\n    return "tampered"'
        with self.assertRaises(ValueError): GeneratedTool(record)
        tool = GeneratedTool(self.workshop.active_generated_records()[0]); tool.record['source'] = record['source']
        self.assertFalse(tool.verify_preconditions({'text': 'anything'})[0])
        tampered = copy.deepcopy(item); tampered['definition']['source'] = record['source']
        with self.workshop.lock, self.workshop.db:
            self.workshop.db.execute('UPDATE capability_revisions SET payload=? WHERE id=? AND revision=?',
                                     (json.dumps(tampered), item['id'], item['revision']))
        with self.assertRaisesRegex(ValueError, 'digest'): self.workshop.validate(*self.ref(item))
        with self.assertRaisesRegex(ValueError, 'digest'): self.workshop.active_generated_records()


if __name__ == '__main__': unittest.main()
