"""Evaluate reasoning contracts or declared human effort; never certify hardware."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITE = 'axx-reasoning-contracts-1'
CASES = (
    ('authority_boundary', 'offline_unit', (
        'backend.tests.test_prompts.PromptTests.test_unknown_modules_preferences_and_privileged_text_fail_before_dispatch',
        'backend.tests.test_prompts.PromptTests.test_tone_notes_cannot_select_a_policy_or_change_the_module_set')),
    ('document_is_reference', 'offline_unit', (
        'backend.tests.test_document_references.DocumentReferenceTests.test_exact_identity_and_full_reference_text_remain_documentary',
        'backend.tests.test_document_references.DocumentReferenceTests.test_expected_reference_is_strict_and_cannot_supply_text_or_authority')),
    ('current_document_identity', 'offline_unit', (
        'backend.tests.test_document_references.DocumentReferenceTests.test_current_member_and_canonical_recipe_changes_are_detected_after_construction',
        'backend.tests.test_document_references.DocumentReferenceTests.test_revision_changes_require_the_new_exact_reference')),
    ('reviewed_skill_reuse', 'isolated_integration', (
        'backend.tests.test_document_skill_learning.DocumentSkillLearningTests.test_reviewed_candidate_learns_and_reuses_real_different_files_without_inference',)),
    ('source_revocation', 'isolated_integration', (
        'backend.tests.test_document_skill_learning.DocumentSkillLearningTests.test_changed_source_abstains_before_provider_effect_and_publication',)),
    ('optional_current_lessons', 'isolated_integration', (
        'backend.tests.test_document_lesson_provenance.DocumentLessonProvenanceTests.test_stale_optional_lesson_does_not_cancel_a_new_plan',
        'backend.tests.test_document_lesson_provenance.DocumentLessonProvenanceTests.test_current_lesson_is_not_hidden_by_newer_stale_lessons')),
    ('scoped_forgetting', 'isolated_integration', (
        'backend.tests.test_document_skill_learning.DocumentSkillLearningTests.test_forgetting_causal_session_blocks_document_derivatives_but_preserves_independent_b',)),
    ('durable_goal', 'isolated_integration', (
        'backend.tests.test_goal_cycle.GoalCycleTests.test_waiting_goal_survives_restart_and_keeps_exact_build_revision',
        'backend.tests.test_goal_cycle.GoalCycleTests.test_candidate_or_model_cannot_weaken_the_original_contract')),
)
NOT_RUN = (
    ('model_compliance', 'real_model', 'Obedience and interpretation by the selected live model, including E01–E28.'),
    ('native_windows', 'native_acceptance', 'Real application targets, desktop effects and installed build acceptance.'),
    ('physical_audio', 'physical_acceptance', 'Speech capture, audible output and end-of-speech to first-audio latency.'),
    ('external_services', 'external_acceptance', 'Authenticated connectors and their remote effects.'),
    ('holdout', 'unexposed_evaluation', 'Independent cases not exposed to development or the candidate.'),
)


class RecordedResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records = []
        self.current = None

    def startTest(self, test):
        super().startTest(test)
        self.started = time.perf_counter()
        self.current = {'test': test.id(), 'status': 'passed'}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.current['status'] = 'failed'

    def addError(self, test, err):
        super().addError(test, err)
        if self.current is None:
            self.records.append({'test': test.id(), 'status': 'failed', 'duration_ms': 0})
        else:
            self.current['status'] = 'failed'

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.current is None:
            self.records.append({'test': test.id(), 'status': 'skipped', 'duration_ms': 0})
        else:
            self.current['status'] = 'skipped'

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.current['status'] = 'skipped'

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.current['status'] = 'failed'

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.current['status'] = 'failed'

    def stopTest(self, test):
        self.current['duration_ms'] = round((time.perf_counter() - self.started) * 1000, 3)
        self.records.append(self.current)
        self.current = None
        super().stopTest(test)


def status(records):
    states = [row['status'] for row in records]
    if 'failed' in states:
        return 'failed'
    if not states or any(state != 'passed' for state in states):
        return 'incomplete'
    return 'passed'


def source_identity(root):
    digest = hashlib.sha256()
    evaluator = hashlib.sha256()
    paths = sorted((root / 'backend').rglob('*.py')) + [root / 'scripts/evaluate_reasoning.py']
    for path in paths:
        payload = path.relative_to(root).as_posix().encode() + b'\0' + path.read_bytes() + b'\0'
        digest.update(payload)
        if path.name.startswith('test_') or path in (root / 'scripts/evaluate_reasoning.py', root / 'backend/effort_evaluation.py'):
            evaluator.update(payload)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True,
        capture_output=True, text=True, timeout=15).stdout.strip()
    return {'commit': commit, 'sha256': digest.hexdigest(), 'evaluator_sha256': evaluator.hexdigest(), 'file_count': len(paths)}


def run_cases(cases=CASES, loader=None):
    loader = loader or unittest.TestLoader()
    rows = []
    for key, scope, names in cases:
        result = RecordedResult()
        # Fixture output and tracebacks are intentionally absent from the shareable receipt.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in names)
            suite.run(result)
        rows.append({'id': key, 'scope': scope, 'status': status(result.records), 'tests': result.records})
    return rows


def compare(baseline, report):
    source = baseline.get('source')
    if (baseline.get('source_unchanged_during_run') is not True or not isinstance(source, dict)
            or not isinstance(source.get('commit'), str) or not source['commit']
            or not isinstance(source.get('sha256'), str) or len(source['sha256']) != 64):
        raise ValueError('Baseline has no stable source identity')
    if source.get('evaluator_sha256') != report['source'].get('evaluator_sha256'):
        raise ValueError('Baseline has different evaluation code')
    for field in ('schema_version', 'suite', 'dataset', 'environment'):
        if baseline.get(field) != report[field]:
            raise ValueError('Baseline has incompatible ' + field)
    before = baseline.get('cases')
    if not isinstance(before, list) or len(before) != len(report['cases']):
        raise ValueError('Baseline has incompatible cases')
    comparisons = []
    for old, new in zip(before, report['cases']):
        for field in ('id', 'scope'):
            if not isinstance(old, dict) or old.get(field) != new[field]:
                raise ValueError('Baseline has incompatible case identities')
        tests = old.get('tests')
        if (not isinstance(tests, list) or any(not isinstance(test, dict) for test in tests)
                or [test.get('test') for test in tests] != [test['test'] for test in new['tests']]):
            raise ValueError('Baseline has incompatible test identities')
        previous = old.get('status')
        if previous not in ('passed', 'failed', 'incomplete', 'not_run'):
            raise ValueError('Baseline has invalid case status')
        outcome = 'unchanged' if previous == new['status'] else 'changed'
        if previous == 'passed' and new['status'] != 'passed':
            outcome = 'regressed'
        elif previous == 'failed' and new['status'] == 'passed':
            outcome = 'improved'
        comparisons.append({'id': new['id'], 'before': previous, 'after': new['status'], 'outcome': outcome})
    return comparisons


def evaluate(root=ROOT):
    before = source_identity(root)
    cases = run_cases()
    unchanged = before == source_identity(root)
    contract_result = status(cases) if unchanged else 'incomplete'
    cases.extend({'id': key, 'scope': scope, 'status': 'not_run', 'reason': reason, 'tests': []}
        for key, scope, reason in NOT_RUN)
    return {'schema_version': 1, 'suite': SUITE, 'dataset': 'development_exposed',
        'source': before, 'source_unchanged_during_run': unchanged,
        'environment': {'python': platform.python_version(), 'system': platform.system(),
            'machine': platform.machine(), 'provider': 'offline_fixtures'},
        'result': 'failed' if contract_result == 'failed' else 'partial',
        'contract_result': contract_result, 'cases': cases}


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                        prefix='.axx-evaluation-', suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--human-episodes', type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    try:
        if args.human_episodes:
            from backend.effort_evaluation import evaluate_effort
            if (args.baseline or args.human_episodes.resolve() == args.output.resolve()
                    or args.output.exists() and args.human_episodes.samefile(args.output)):
                raise ValueError('Human episodes need a separate output and cannot use a reasoning baseline')
            with args.human_episodes.open('rb') as stream:
                observations = stream.read(1024 * 1024 + 1)
            if len(observations) > 1024 * 1024:
                raise ValueError('Human episodes exceed 1 MiB')
            before = source_identity(ROOT)
            report = evaluate_effort(json.loads(observations.decode('utf-8')))
            if before != source_identity(ROOT):
                raise ValueError('Source changed while evaluating human observations')
            report.update(source=before, source_unchanged_during_run=True)
            write_report(args.output, report)
            print('Human effort: descriptive; independently verified acceptance: not run')
            return 0
        baseline = None
        if args.baseline:
            if args.baseline.resolve() == args.output.resolve():
                raise ValueError('Output must not overwrite the baseline')
            if args.baseline.stat().st_size > 1024 * 1024:
                raise ValueError('Baseline exceeds 1 MiB')
            baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
            if not isinstance(baseline, dict):
                raise ValueError('Baseline must be an object')
        report = evaluate()
        if baseline is not None:
            report['comparison'] = compare(baseline, report)
        write_report(args.output, report)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, 'Evaluation failed: ' + str(error) + '\n')
    print('Reasoning contracts: ' + report['contract_result'] + '; overall acceptance: partial')
    return 0 if report['contract_result'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
