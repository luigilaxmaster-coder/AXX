"""The evaluation receipt cannot turn missing or failed checks into acceptance."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_reasoning as evaluation


class Fixture(unittest.TestCase):
    __test__ = False

    def pass_case(self):
        pass

    def fail_case(self):
        self.fail('private fixture data must not appear in a receipt')

    def skip_case(self):
        self.skipTest('private fixture data must not appear in a receipt')

    def subtest_case(self):
        with self.subTest(secret='private'):
            self.assertTrue(False)


class EvaluationTests(unittest.TestCase):
    def human_input(self, folder):
        path = folder / 'human.json'
        path.write_text(json.dumps({'schema_version': 1, 'dataset_id': 'fixture', 'dataset_revision': 'r1',
            'partition': 'development', 'measurement_basis': 'fixture', 'protocol_sha256': 'a' * 64,
            'eligible_pairs': 1, 'pairs': []}), encoding='utf-8')
        return path

    def test_human_report_is_offline_descriptive_and_never_runs_reasoning_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = self.human_input(folder); output = folder / 'report.json'
            original = source.read_bytes()
            with patch.object(evaluation, 'source_identity', return_value={'commit': 'fixture'}), \
                    patch.object(evaluation, 'run_cases', side_effect=AssertionError('No inference or unrelated test run')), \
                    patch('builtins.print'):
                self.assertEqual(evaluation.main(['--human-episodes', str(source), '--output', str(output)]), 0)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['result'], 'descriptive')
            self.assertEqual(report['pairs_missing'], 1)
            self.assertIsNone(report['paired_declared_human_difference_ms'])
            self.assertFalse(report['physical_acceptance_verified'])
            self.assertEqual(source.read_bytes(), original)

    def test_human_input_cannot_be_overwritten_by_path_or_hard_link_or_mixed_with_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = self.human_input(folder); alias = folder / 'alias.json'
            os.link(source, alias)
            original = source.read_bytes()
            for destination, extra in ((source, []), (alias, []), (folder / 'other.json', ['--baseline', str(source)])):
                with self.subTest(destination=destination, extra=extra), self.assertRaises(SystemExit) as error:
                    evaluation.main(['--human-episodes', str(source), '--output', str(destination), *extra])
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(source.read_bytes(), original)

    def test_invalid_or_oversized_human_data_never_creates_a_report(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = folder / 'human.json'; output = folder / 'report.json'
            for content in ('[]', '{}', ' ' * (1024 * 1024 + 1)):
                source.write_text(content, encoding='utf-8')
                with self.assertRaises(SystemExit) as error:
                    evaluation.main(['--human-episodes', str(source), '--output', str(output)])
                self.assertEqual(error.exception.code, 2)
                self.assertFalse(output.exists())

    def test_source_drift_during_human_evaluation_keeps_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = self.human_input(folder); output = folder / 'report.json'
            output.write_text('original report', encoding='utf-8')
            with patch.object(evaluation, 'source_identity', side_effect=[{'commit': 'before'}, {'commit': 'after'}]), \
                    self.assertRaises(SystemExit) as error:
                evaluation.main(['--human-episodes', str(source), '--output', str(output)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.read_text(encoding='utf-8'), 'original report')

    def test_output_failure_preserves_previous_report_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); output = folder / 'report.json'; output.write_text('original', encoding='utf-8')
            with patch.object(evaluation.os, 'replace', side_effect=OSError('fixture replacement failure')):
                with self.assertRaises(OSError): evaluation.write_report(output, {'result': 'descriptive'})
            self.assertEqual(output.read_text(encoding='utf-8'), 'original')
            self.assertEqual(list(folder.glob('.axx-evaluation-*')), [])

    def test_output_hard_link_created_after_precheck_cannot_truncate_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = self.human_input(folder); output = folder / 'report.json'
            original = source.read_bytes(); identities = []
            def identity(root):
                identities.append(True)
                if len(identities) == 2: os.link(source, output)
                return {'commit': 'fixture'}
            with patch.object(evaluation, 'source_identity', side_effect=identity), patch('builtins.print'):
                self.assertEqual(evaluation.main(['--human-episodes', str(source), '--output', str(output)]), 0)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['result'], 'descriptive')

    def rows(self):
        cases = tuple((name, 'offline_unit', ('test_evaluate_reasoning.Fixture.' + name,))
            for name in ('pass_case', 'fail_case', 'skip_case', 'subtest_case'))
        return evaluation.run_cases(cases)

    def test_failures_skips_and_subtests_never_pass_or_leak_fixture_text(self):
        rows = self.rows()
        self.assertEqual([row['status'] for row in rows], ['passed', 'failed', 'incomplete', 'failed'])
        self.assertEqual(rows[2]['tests'][0]['status'], 'skipped')
        self.assertNotIn('private', str(rows))
        self.assertEqual(evaluation.status([]), 'incomplete')

    def test_missing_test_is_failed(self):
        rows = evaluation.run_cases((('missing', 'offline_unit', ('does_not_exist.test',)),))
        self.assertEqual(rows[0]['status'], 'failed')

    def test_report_keeps_unexecuted_acceptance_visible(self):
        with patch.object(evaluation, 'source_identity', return_value={'commit': 'a', 'sha256': 'b'}), \
             patch.object(evaluation, 'run_cases', return_value=[{'id': 'fixture', 'scope': 'offline_unit', 'status': 'passed', 'tests': []}]):
            report = evaluation.evaluate()
        self.assertEqual(report['contract_result'], 'passed')
        self.assertEqual(report['result'], 'partial')
        self.assertEqual(report['dataset'], 'development_exposed')
        self.assertTrue(all(row['status'] == 'not_run' for row in report['cases'][1:]))

    def test_changed_source_invalidates_run(self):
        with patch.object(evaluation, 'source_identity', side_effect=[{'sha256': 'before'}, {'sha256': 'after'}]), \
             patch.object(evaluation, 'run_cases', return_value=[{'status': 'passed'}]):
            report = evaluation.evaluate()
        self.assertEqual(report['contract_result'], 'incomplete')
        self.assertFalse(report['source_unchanged_during_run'])

    def test_comparison_rejects_different_conditions_and_test_inventory(self):
        report = {'schema_version': 1, 'suite': evaluation.SUITE, 'dataset': 'development_exposed',
            'source': {'commit': 'a' * 40, 'sha256': 'b' * 64, 'evaluator_sha256': 'c' * 64}, 'source_unchanged_during_run': True,
            'environment': {'provider': 'offline_fixtures'}, 'cases': self.rows()}
        baseline = copy.deepcopy(report)
        self.assertTrue(all(row['outcome'] == 'unchanged' for row in evaluation.compare(baseline, report)))
        for field in ('schema_version', 'suite', 'dataset', 'environment'):
            wrong = copy.deepcopy(baseline)
            wrong[field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluation.compare(wrong, report)
        baseline['cases'][0]['tests'][0]['test'] = 'different'
        with self.assertRaises(ValueError):
            evaluation.compare(baseline, report)
        baseline = copy.deepcopy(report)
        baseline['source']['evaluator_sha256'] = 'd' * 64
        with self.assertRaises(ValueError):
            evaluation.compare(baseline, report)

    def test_class_setup_error_is_recorded_without_a_started_test(self):
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError('private class fixture')

            def runTest(self):
                pass

        result = evaluation.RecordedResult()
        unittest.TestSuite([Broken()]).run(result)
        self.assertEqual(evaluation.status(result.records), 'failed')
        self.assertNotIn('private', str(result.records))

    def test_class_setup_skip_is_incomplete(self):
        class Skipped(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest('private class fixture')

            def runTest(self):
                pass

        result = evaluation.RecordedResult()
        unittest.TestSuite([Skipped()]).run(result)
        self.assertEqual(evaluation.status(result.records), 'incomplete')
        self.assertEqual(result.records[0]['status'], 'skipped')
        self.assertNotIn('private', str(result.records))


if __name__ == '__main__':
    unittest.main()
