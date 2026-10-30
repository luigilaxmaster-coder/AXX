"""The evaluation receipt cannot turn missing or failed checks into acceptance."""
import copy
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
