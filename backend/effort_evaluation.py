"""Descriptive arithmetic on declared human observations, never hardware acceptance."""
from collections import Counter
import hashlib
import json
import re


ACTIVITIES = {'manual_work', 'preparation', 'supervision', 'correction', 'undo', 'interruption', 'recovery'}
OUTCOMES = {'completed', 'failed', 'abandoned', 'abstained', 'incomplete'}


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('Invalid human observation fields')


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise ValueError('Observation identifiers must be opaque IDs up to 128 characters')
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('An exact SHA-256 reference is required')
    return value


def _number(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError('Use nonnegative integers; observation timestamps use milliseconds')
    return value


def _ids(value):
    if not isinstance(value, list):
        raise ValueError('Observation references must be a list')
    return {_id(item) for item in value}


def evaluate_effort(dataset):
    """One operator and one shared clock per dataset; incomplete is not zero."""
    _object(dataset, ('schema_version', 'dataset_id', 'dataset_revision', 'partition',
                      'measurement_basis', 'protocol_sha256', 'eligible_pairs', 'pairs'))
    if type(dataset['schema_version']) is not int or dataset['schema_version'] != 1:
        raise ValueError('Unknown human observation schema')
    _id(dataset['dataset_id']); _id(dataset['dataset_revision']); _hash(dataset['protocol_sha256'])
    if dataset['partition'] not in ('development', 'holdout'):
        raise ValueError('Declare the dataset partition')
    if dataset['measurement_basis'] not in ('self_reported_intervals', 'observer_recorded_intervals', 'fixture'):
        raise ValueError('Declare how human intervals were obtained')
    pairs = dataset['pairs']
    if not isinstance(pairs, list) or len(pairs) > 500:
        raise ValueError('At most 500 observed pairs are supported')
    eligible = _number(dataset['eligible_pairs'])
    if eligible < len(pairs):
        raise ValueError('The eligible universe cannot omit submitted pairs')
    rows, seen, intervals = [], set(), []
    totals = {arm: {'episodes': 0, 'outcomes': Counter(), 'known_human_ms': 0,
                   'unknown_measurements': eligible - len(pairs), 'useful_verified_results_declared': 0,
                   'corrections': set(), 'undos': set(), 'interruptions': set(), 'preparations': {}}
              for arm in ('manual', 'axx')}
    for pair in pairs:
        _object(pair, ('id', 'family', 'project', 'period', 'contract_sha256', 'equivalent', 'manual', 'axx'))
        for key in ('id', 'family', 'project', 'period'): _id(pair[key])
        _hash(pair['contract_sha256'])
        if type(pair['equivalent']) is not bool or pair['id'] in seen:
            raise ValueError('Pairs need unique identities and an explicit equivalence review')
        seen.add(pair['id'])
        row = {key: pair[key] for key in ('id', 'family', 'project', 'period', 'contract_sha256', 'equivalent')}
        comparable = pair['equivalent'] and dataset['measurement_basis'] != 'fixture'
        for arm in ('manual', 'axx'):
            episode, total = pair[arm], totals[arm]
            if episode is None:
                row[arm] = None; total['unknown_measurements'] += 1; comparable = False
                continue
            _object(episode, ('outcome', 'result_verified', 'result_receipt_sha256', 'useful',
                              'measurement_complete', 'intervals', 'corrections', 'undos',
                              'interruptions', 'preparations'))
            if (not isinstance(episode['outcome'], str) or episode['outcome'] not in OUTCOMES or type(episode['result_verified']) is not bool
                    or type(episode['measurement_complete']) is not bool
                    or episode['useful'] is not None and type(episode['useful']) is not bool):
                raise ValueError('Invalid outcome or human measurement state')
            if episode['result_verified']: _hash(episode['result_receipt_sha256'])
            elif episode['result_receipt_sha256'] is not None: _hash(episode['result_receipt_sha256'])
            if not isinstance(episode['intervals'], list) or not isinstance(episode['preparations'], list):
                raise ValueError('Intervals and preparations must be lists')
            cost, by_activity = 0, Counter()
            for segment in episode['intervals']:
                _object(segment, ('activity', 'start_ms', 'end_ms'))
                start, end = _number(segment['start_ms']), _number(segment['end_ms'])
                if not isinstance(segment['activity'], str) or segment['activity'] not in ACTIVITIES or end <= start:
                    raise ValueError('Human intervals need a supported activity and positive duration')
                intervals.append((start, end))
                by_activity[segment['activity']] += end - start; cost += end - start
            useful = episode['outcome'] == 'completed' and episode['result_verified'] and episode['useful'] is True
            measured = episode['measurement_complete']
            total['episodes'] += 1; total['outcomes'][episode['outcome']] += 1
            total['known_human_ms'] += cost; total['unknown_measurements'] += not measured
            total['useful_verified_results_declared'] += useful
            for field in ('corrections', 'undos', 'interruptions'):
                total[field].update(_ids(episode[field]))
            for preparation in episode['preparations']:
                _object(preparation, ('id', 'state'))
                key = _id(preparation['id'])
                if preparation['state'] not in ('used', 'obsolete', 'pending'):
                    raise ValueError('Unknown preparation outcome')
                previous = total['preparations'].get(key)
                if previous is not None and previous != preparation['state']:
                    raise ValueError('Conflicting snapshots for the same preparation')
                total['preparations'][key] = preparation['state']
            row[arm] = {'outcome': episode['outcome'], 'useful_verified_result_declared': useful,
                        'human_ms': cost if measured else None, 'known_human_ms': cost,
                        'activity_ms': dict(by_activity)}
            comparable = comparable and useful and measured
        row['declared_human_difference_ms'] = row['manual']['human_ms'] - row['axx']['human_ms'] if comparable else None
        rows.append(row)
    # shortcut: a dataset represents one operator on one clock; group clocks before supporting multiple operators.
    intervals.sort()
    if any(start < previous_end for (_, previous_end), (start, _) in zip(intervals, intervals[1:])):
        raise ValueError('Human intervals overlap; review attribution rather than counting twice')
    summaries = {}
    for arm, total in totals.items():
        preparations = Counter(total['preparations'].values())
        summaries[arm] = {key: total[key] for key in ('episodes', 'known_human_ms', 'unknown_measurements', 'useful_verified_results_declared')}
        summaries[arm].update(outcomes=dict(total['outcomes']), eligible_episodes=eligible,
            human_ms=None if total['unknown_measurements'] else total['known_human_ms'],
            human_ms_per_useful_result_declared=(total['known_human_ms'] / total['useful_verified_results_declared']
                if not total['unknown_measurements'] and total['useful_verified_results_declared'] else None),
            **{key: len(total[key]) for key in ('corrections', 'undos', 'interruptions')},
            obsolete_preparations={'numerator': preparations['obsolete'], 'denominator': sum(preparations.values()),
                'unresolved': preparations['pending'], 'percent': 100 * preparations['obsolete'] / sum(preparations.values())
                if preparations and not preparations['pending'] else None})
    differences = [row['declared_human_difference_ms'] for row in rows if row['declared_human_difference_ms'] is not None]
    return {'schema_version': 1, 'suite': 'axx-declared-human-effort-1', 'result': 'descriptive',
        'dataset': {key: dataset[key] for key in ('dataset_id', 'dataset_revision', 'partition', 'measurement_basis', 'protocol_sha256')},
        'dataset_sha256': hashlib.sha256(json.dumps(dataset, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
        'eligible_pairs_declared': eligible, 'pairs_reported': len(rows), 'pairs_missing': eligible - len(rows),
        'comparable_complete_pairs': len(differences),
        'paired_declared_human_difference_ms': sum(differences) if differences else None,
        'conditions': summaries, 'pairs': rows,
        'equivalence_basis': 'operator declaration; not independently certified',
        'result_evidence_basis': 'provided receipt references; their runtime contents were not inspected',
        'independent_holdout_verified': False, 'physical_acceptance_verified': False,
        'scope': 'Declared human intervals, including unsuccessful episodes. Executor latency is not human time or causal savings.'}
