"""Synthetic declarations exercise arithmetic; these are not measured human trials."""
import copy
import unittest

from backend.effort_evaluation import evaluate_effort


def episode(start, costs):
    intervals = []
    for activity, duration in costs:
        intervals.append({'activity': activity, 'start_ms': start, 'end_ms': start + duration})
        start += duration
    return {'outcome': 'completed', 'result_verified': True, 'result_receipt_sha256': 'a' * 64,
        'useful': True, 'measurement_complete': True, 'intervals': intervals,
        'corrections': [], 'undos': [], 'interruptions': [], 'preparations': []}


def dataset():
    return {'schema_version': 1, 'dataset_id': 'synthetic-declarations', 'dataset_revision': 'r1',
        'partition': 'development', 'measurement_basis': 'self_reported_intervals',
        'protocol_sha256': 'b' * 64, 'eligible_pairs': 1,
        'pairs': [{'id': 'pair-1', 'family': 'file-bundle', 'project': 'project-a', 'period': 'period-1',
            'contract_sha256': 'c' * 64, 'equivalent': True,
            'manual': episode(0, [('manual_work', 10000)]),
            'axx': episode(20000, [('preparation', 1000), ('supervision', 2000), ('correction', 3000), ('undo', 1000)])}]}


class EffortEvaluationTests(unittest.TestCase):
    def test_cost_includes_all_human_work_and_does_not_certify_supplied_attestations(self):
        source = dataset(); original = copy.deepcopy(source)
        report = evaluate_effort(source)
        self.assertEqual(report['paired_declared_human_difference_ms'], 3000)
        self.assertEqual(report['conditions']['axx']['human_ms'], 7000)
        self.assertEqual(report['pairs'][0]['axx']['activity_ms']['undo'], 1000)
        self.assertEqual(report['result'], 'descriptive')
        self.assertFalse(report['physical_acceptance_verified'])
        self.assertFalse(report['independent_holdout_verified'])
        self.assertIn('not inspected', report['result_evidence_basis'])
        self.assertEqual(source, original)

    def test_corrections_can_make_declared_savings_negative(self):
        source = dataset()
        source['pairs'][0]['axx'] = episode(20000, [('supervision', 8000), ('correction', 5000), ('recovery', 2000)])
        self.assertEqual(evaluate_effort(source)['paired_declared_human_difference_ms'], -5000)

    def test_incomplete_or_unaccepted_results_never_generate_savings(self):
        for change in ({'measurement_complete': False}, {'result_verified': False, 'result_receipt_sha256': None},
                       {'useful': None}, {'useful': False}, {'outcome': 'failed'}, {'outcome': 'abandoned'},
                       {'outcome': 'abstained'}, {'outcome': 'incomplete'}):
            with self.subTest(change=change):
                source = dataset(); source['pairs'][0]['axx'].update(change)
                report = evaluate_effort(source)
                self.assertIsNone(report['paired_declared_human_difference_ms'])
                self.assertEqual(report['conditions']['axx']['known_human_ms'], 7000)
                if change.get('measurement_complete') is False:
                    self.assertIsNone(report['conditions']['axx']['human_ms'])

    def test_missing_pairs_and_episodes_stay_in_denominator(self):
        source = dataset(); source['eligible_pairs'] = 3; source['pairs'][0]['manual'] = None
        report = evaluate_effort(source)
        self.assertEqual(report['pairs_missing'], 2)
        self.assertEqual(report['conditions']['manual']['unknown_measurements'], 3)
        self.assertIsNone(report['conditions']['axx']['human_ms'])
        self.assertEqual(report['conditions']['axx']['known_human_ms'], 7000)
        self.assertIsNone(report['paired_declared_human_difference_ms'])

    def test_failed_and_obsolete_work_remains_in_global_cost(self):
        source = dataset(); source['eligible_pairs'] = 2
        failed = copy.deepcopy(source['pairs'][0]); failed['id'] = 'pair-failed'
        failed['manual'] = None; failed['axx'] = episode(40000, [('preparation', 4000), ('correction', 6000)])
        failed['axx'].update(outcome='failed', useful=False, preparations=[{'id': 'draft-failed', 'state': 'obsolete'}])
        source['pairs'].append(failed)
        report = evaluate_effort(source)
        self.assertEqual(report['conditions']['axx']['human_ms'], 17000)
        self.assertEqual(report['conditions']['axx']['outcomes']['failed'], 1)
        self.assertEqual(report['conditions']['axx']['obsolete_preparations'], {'numerator': 1, 'denominator': 1, 'unresolved': 0, 'percent': 100})
        self.assertEqual(report['conditions']['axx']['human_ms_per_useful_result_declared'], 17000)
        self.assertEqual(report['comparable_complete_pairs'], 1)
        self.assertEqual(report['paired_declared_human_difference_ms'], 3000)

    def test_repeated_event_references_do_not_inflate_counts_and_conflicting_snapshots_fail(self):
        source = dataset(); axx = source['pairs'][0]['axx']
        for field in ('corrections', 'undos', 'interruptions'): axx[field] = ['same-id', 'same-id']
        axx['preparations'] = [{'id': 'draft', 'state': 'pending'}] * 2
        report = evaluate_effort(source)
        self.assertEqual(report['conditions']['axx']['corrections'], 1)
        self.assertEqual(report['conditions']['axx']['obsolete_preparations'], {'numerator': 0, 'denominator': 1, 'unresolved': 1, 'percent': None})
        axx['preparations'].append({'id': 'draft', 'state': 'used'})
        with self.assertRaisesRegex(ValueError, 'Conflicting'): evaluate_effort(source)

    def test_overlap_anywhere_in_one_operator_dataset_is_rejected(self):
        source = dataset(); source['pairs'][0]['axx'] = episode(5000, [('supervision', 7000)])
        with self.assertRaisesRegex(ValueError, 'overlap'): evaluate_effort(source)
        source = dataset(); source['pairs'][0]['axx']['intervals'].append({'activity': 'correction', 'start_ms': 20500, 'end_ms': 21000})
        with self.assertRaisesRegex(ValueError, 'overlap'): evaluate_effort(source)

    def test_fixtures_inequivalence_and_holdout_labels_do_not_certify_savings(self):
        source = dataset(); source['measurement_basis'] = 'fixture'
        self.assertIsNone(evaluate_effort(source)['paired_declared_human_difference_ms'])
        source = dataset(); source['pairs'][0]['equivalent'] = False
        self.assertIsNone(evaluate_effort(source)['paired_declared_human_difference_ms'])
        source = dataset(); source['partition'] = 'holdout'
        self.assertFalse(evaluate_effort(source)['independent_holdout_verified'])

    def test_empty_dataset_is_no_evidence_of_utility(self):
        source = dataset(); source.update(pairs=[], eligible_pairs=0)
        report = evaluate_effort(source)
        self.assertEqual(report['comparable_complete_pairs'], 0)
        self.assertIsNone(report['paired_declared_human_difference_ms'])

    def test_strict_boundaries_and_duplicate_pair_ids(self):
        mutations = [lambda d: d.update(schema_version=True), lambda d: d.update(eligible_pairs=False),
            lambda d: d.update(eligible_pairs=0), lambda d: d.update(protocol_sha256='unknown'),
            lambda d: d.update(extra='not allowed'), lambda d: d['pairs'].append(copy.deepcopy(d['pairs'][0])),
            lambda d: d['pairs'][0]['axx'].update(outcome=[]),
            lambda d: d['pairs'][0]['axx']['intervals'][0].update(activity={}),
            lambda d: d['pairs'][0]['axx']['intervals'][0].update(start_ms=True),
            lambda d: d['pairs'][0]['axx']['intervals'][0].update(end_ms=float('nan'))]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                source = dataset(); mutate(source)
                with self.assertRaises(ValueError): evaluate_effort(source)
