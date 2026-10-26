"""One installed-model proposal and pure tests, left pending the owner's review.

No approval, activation, command execution, credentials, prompts or user data are
written into the receipt. --self-check never contacts a running application.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODEL, PROVIDER = 'gpt-6.1-sol', '@codex'
MAX_REPLY = 2 * 1024 * 1024
GOAL = (
    'Crea una python_transform pura llamada Verificación de total. La función exacta será '
    'def run(inputs): return round(inputs["quantity"] * inputs["price"], 2). '
    'Entrada objeto JSON con exactamente quantity entero mínimo 0 máximo 100 y price number mínimo 0 '
    'máximo 1000; ambos required y additionalProperties=false. Salida output_schema type=number. '
    'Incluye exactamente estos tests: inputs={"quantity":3,"price":12.5}, expected=37.5; '
    'inputs={"quantity":0,"price":2}, expected=0. No uses otras herramientas ni datos externos. '
    'Es una propuesta sintética para revisión humana posterior; no la apruebes ni actives.'
)


class VerificationError(RuntimeError):
    """Stable codes only; provider/HTTP payloads may contain private content."""


def require(condition, code):
    if not condition: raise VerificationError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs): return None


class InstalledApi:
    def __init__(self, descriptor):
        require(type(descriptor.get('port')) is int and 1 <= descriptor['port'] <= 65535, 'invalid_port')
        require(isinstance(descriptor.get('token'), str) and len(descriptor['token']) >= 32
                and '\r' not in descriptor['token'] and '\n' not in descriptor['token'], 'invalid_local_token')
        self.descriptor = descriptor
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def __call__(self, route, body=None, *, timeout=15):
        require(route.startswith('/axx-api/') and not route.startswith('//') and '#' not in route, 'invalid_route')
        request = urllib.request.Request('http://127.0.0.1:' + str(self.descriptor['port']) + route,
            data=None if body is None else json.dumps(body, allow_nan=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.descriptor['token'], 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response: raw = response.read(MAX_REPLY + 1)
            require(len(raw) <= MAX_REPLY, 'reply_too_large')
            value = json.loads(raw)
            require(isinstance(value, dict), 'reply_not_object')
            return value
        except urllib.error.HTTPError as exc:
            status = exc.code; exc.close()
            raise VerificationError('http_' + str(status)) from None
        except (OSError, ValueError, TimeoutError):
            raise VerificationError('transport_or_json_error') from None


def checked_draft(item, *, expected_revision=1):
    require(isinstance(item, dict), 'proposal_not_object')
    require(re.fullmatch(r'cap\.[a-f0-9]{32}', item.get('id', '')) is not None, 'proposal_id_invalid')
    require(type(item.get('revision')) is int and item['revision'] >= 1
            and (expected_revision is None or item['revision'] == expected_revision), 'proposal_revision_invalid')
    require(re.fullmatch(r'[a-f0-9]{64}', item.get('digest', '')) is not None, 'proposal_digest_invalid')
    require(item.get('state') == 'draft' and item.get('approval') is None
            and item.get('active_revision') is None and item.get('generated_command_id') is None,
            'proposal_not_pending_review')
    definition = item.get('definition', {})
    require(definition.get('kind') == 'python_transform' and isinstance(definition.get('source'), str)
            and definition['source'].strip().startswith('def run(inputs):'), 'proposal_source_invalid')
    schema = definition.get('schema', {})
    props = schema.get('properties', {})
    require(schema.get('type') == 'object' and set(props) == {'quantity', 'price'}
            and set(schema.get('required', [])) == {'quantity', 'price'}
            and schema.get('additionalProperties') is False, 'proposal_input_contract_invalid')
    require(props['quantity'].get('type') == 'integer' and props['quantity'].get('minimum') == 0
            and props['quantity'].get('maximum') == 100 and props['price'].get('type') == 'number'
            and props['price'].get('minimum') == 0 and props['price'].get('maximum') == 1000,
            'proposal_input_bounds_invalid')
    require(definition.get('output_schema', {}).get('type') == 'number', 'proposal_output_contract_invalid')
    tests = definition.get('tests')
    require(isinstance(tests, list) and len(tests) == 2, 'proposal_tests_invalid')
    expected = [{'inputs': {'quantity': 3, 'price': 12.5}, 'expected': 37.5},
                {'inputs': {'quantity': 0, 'price': 2}, 'expected': 0}]
    require(all(any(test == sample and type(test.get('expected')) in (int, float) for test in tests)
                for sample in expected), 'proposal_tests_differ_from_requested')
    provenance = item.get('provenance', {})
    require(provenance.get('source') == 'model_proposal' and provenance.get('selected_model') == MODEL
            and provenance.get('selected_provider') == PROVIDER
            and provenance.get('route', {}).get('model') == MODEL
            and provenance.get('route', {}).get('provider_name') == PROVIDER,
            'proposal_provider_provenance_invalid')
    request_id = provenance.get('request_id')
    require(isinstance(request_id, str) and re.fullmatch(r'capability-[a-f0-9]{32}', request_id) is not None,
            'proposal_request_identity_invalid')
    return request_id


def generation_payload(previous=None):
    payload = {'goal': GOAL, 'kind': 'python_transform', 'model': MODEL,
               'provider_name': PROVIDER, 'selection_mode': 'manual'}
    if previous is not None:
        checked_draft(previous, expected_revision=None)
        require(isinstance(previous.get('project_id'), str) and len(previous['project_id']) <= 128,
                'previous_project_identity_invalid')
        payload.update(capability_id=previous['id'], revision=previous['revision'],
                       digest=previous['digest'], project_id=previous['project_id'])
        payload['goal'] += (
            '\nMejora la claridad del código anterior conservando exactamente el contrato y los dos tests. '
            'Reescribe el producto mediante variables locales quantity, price y total antes de round(total, 2). '
            'Añade este comentario dentro de la función: # Revisión ' + str(previous['revision'] + 1)
            + ': entradas separadas y total redondeado. La fuente debe cambiar respecto a la revisión anterior. '
            'Conserva el ID de la capacidad; esta revisión seguirá pendiente de aprobación humana.')
    return payload


def checked_revision(previous, revised):
    require(revised.get('id') == previous['id'] and revised.get('project_id') == previous['project_id'],
            'revision_changed_capability_or_project')
    checked_draft(revised, expected_revision=previous['revision'] + 1)
    require(revised['digest'] != previous['digest']
            and revised['provenance']['request_id'] != previous['provenance']['request_id'],
            'revision_reused_previous_evidence')
    require(revised['definition']['source'] != previous['definition']['source'], 'revision_source_unchanged')


def checked_inference(run, request_id):
    require(run.get('request_id') == request_id and run.get('purpose') == 'capability'
            and run.get('state') == 'completed' and run.get('inference_verified') is True,
            'real_generation_not_verified')
    require(run.get('model') == MODEL and run.get('runtime_model') == MODEL
            and run.get('runtime_provider') == 'openai', 'served_identity_differed')
    require(run.get('tool_results') == [] and not run.get('pending_approvals')
            and not run.get('managed_operations'), 'generation_requested_execution')


def checked_validation(item, validation):
    require(validation.get('self_tests_passed') is True and validation.get('tested_digest') == item['digest']
            and validation.get('source_digest') == hashlib.sha256(item['definition']['source'].encode('utf-8')).hexdigest(),
            'installed_pure_tests_not_verified')
    rows = validation.get('tests', [])
    require(len(rows) == 2 and all(row.get('passed') is True for row in rows), 'installed_test_count_or_result_invalid')
    for index, row in enumerate(rows):
        require(row.get('index') == index and type(row.get('actual')) in (int, float)
                and row['actual'] == item['definition']['tests'][index]['expected'], 'installed_test_actual_differed')


def verify(data_dir, version, revise_capability=None):
    from backend.connect.mcp_server import LocalAxxClient
    client = LocalAxxClient(data_dir)
    descriptor = client._descriptor(); api = InstalledApi(descriptor)
    require(isinstance(descriptor.get('instance_id'), str)
            and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', descriptor['instance_id']) is not None,
            'invalid_instance_identity')
    snapshot = json.loads((client.data_dir / 'logs/native-runtime.json').read_text(encoding='utf-8'))
    status = api('/axx-api/status')
    require(snapshot.get('version') == version and snapshot.get('backendReady') is True
            and status.get('ready') is True and status.get('native') is True
            and snapshot.get('backendInstance') == descriptor['instance_id'] == status.get('instance_id')
            and snapshot.get('backendPort') == descriptor['port'] and descriptor.get('pid') == status.get('pid'),
            'installed_version_or_instance_invalid')
    engine = api('/axx-api/connect/status?engine=1', timeout=30)
    require(engine.get('instance_id') == descriptor['instance_id']
            and engine.get('engine', {}).get('authenticated') is True
            and engine['engine'].get('allow_paid') is False, 'selected_codex_not_authenticated')
    previous = None
    if revise_capability is not None:
        previous = api('/axx-api/capabilities/get?' + urllib.parse.urlencode({'id': revise_capability}))
        require(previous.get('id') == revise_capability, 'previous_capability_identity_invalid')
        checked_draft(previous, expected_revision=None)
    draft = api('/axx-api/capabilities/generate', generation_payload(previous), timeout=85)
    expected_revision = previous['revision'] + 1 if previous is not None else 1
    request_id = checked_draft(draft, expected_revision=expected_revision)
    if previous is not None: checked_revision(previous, draft)
    run = api('/axx-api/connect/run?' + urllib.parse.urlencode({'request_id': request_id}))
    checked_inference(run, request_id)
    reference = {key: draft[key] for key in ('id', 'revision', 'digest')}
    validation = api('/axx-api/capabilities/validate', reference, timeout=30)
    checked_validation(draft, validation)
    current = api('/axx-api/capabilities/get?' + urllib.parse.urlencode({'id': draft['id']}))
    require(checked_draft(current, expected_revision=expected_revision) == request_id
            and current['digest'] == draft['digest'], 'proposal_changed_during_verification')
    checked_validation(current, current.get('validation', {}))
    prefix = 'axx.generated.' + draft['id'][4:]
    catalog = api('/axx-api/commands?' + urllib.parse.urlencode({'q': prefix, 'limit': 100, 'offset': 0}))
    require(catalog.get('matched') == 0 and catalog.get('commands') == [], 'unapproved_command_registered')
    # Re-read the same protected descriptor and instance after generation; never
    # accept a successful proposal from a backend replaced during the check.
    after = client._descriptor()
    require(after['instance_id'] == descriptor['instance_id'] and after['port'] == descriptor['port']
            and api('/axx-api/status').get('instance_id') == descriptor['instance_id'], 'installed_instance_changed')
    return {'schema_version': 1, 'passed': True, 'installed_version': version,
            'backend_instance': descriptor['instance_id'], 'capability_id': draft['id'],
            'revision': draft['revision'], 'request_id': request_id, 'model': MODEL, 'provider': PROVIDER,
            'previous_revision': previous['revision'] if previous is not None else None,
            'previous_digest': previous['digest'] if previous is not None else None,
            'source_revised': previous is not None,
            'digest': draft['digest'], 'source_digest': validation['source_digest'],
            'tests_count': len(validation['tests']), 'tests_passed': len(validation['tests']),
            'pending_review': True, 'approved': False, 'active': False,
            'command_execution_performed': False,
            'scope': 'real_installed_model_generation_and_pure_tests; activation_requires_owner_review'}


def self_check():
    item = {'id': 'cap.' + 'a' * 32, 'revision': 1, 'digest': 'b' * 64, 'state': 'draft', 'project_id': '',
            'approval': None, 'active_revision': None, 'generated_command_id': None,
            'definition': {'kind': 'python_transform', 'title': 'Synthetic fixture', 'objective': 'Synthetic calculation',
                           'source': 'def run(inputs):\n    return round(inputs["quantity"] * inputs["price"], 2)',
                           'readme': 'Synthetic self check.'},
            'provenance': {'source': 'model_proposal', 'selected_model': MODEL, 'selected_provider': PROVIDER,
                           'request_id': 'capability-' + 'c' * 32, 'route': {'model': MODEL, 'provider_name': PROVIDER}}}
    item['definition'].update(schema={'type': 'object', 'properties': {
        'quantity': {'type': 'integer', 'minimum': 0, 'maximum': 100},
        'price': {'type': 'number', 'minimum': 0, 'maximum': 1000}}, 'required': ['quantity', 'price'], 'additionalProperties': False},
        output_schema={'type': 'number'}, tests=[{'inputs': {'quantity': 3, 'price': 12.5}, 'expected': 37.5},
                                                {'inputs': {'quantity': 0, 'price': 2}, 'expected': 0}])
    request_id = checked_draft(item)
    run = {'request_id': request_id, 'purpose': 'capability', 'state': 'completed', 'inference_verified': True,
           'model': MODEL, 'runtime_model': MODEL, 'runtime_provider': 'openai', 'tool_results': [], 'pending_approvals': []}
    checked_inference(run, request_id)
    validation = {'self_tests_passed': True, 'tested_digest': item['digest'],
                  'source_digest': hashlib.sha256(item['definition']['source'].encode('utf-8')).hexdigest(),
                  'tests': [{'index': 0, 'passed': True, 'actual': 37.5}, {'index': 1, 'passed': True, 'actual': 0.0}]}
    checked_validation(item, validation)
    payload = generation_payload(item)
    require(all(payload[key] == item[field] for key, field in
                [('capability_id', 'id'), ('revision', 'revision'), ('digest', 'digest'), ('project_id', 'project_id')]),
            'self_check_revision_payload_mismatch')
    revised = copy.deepcopy(item)
    revised.update(revision=2, digest='d' * 64)
    revised['provenance']['request_id'] = 'capability-' + 'e' * 32
    revised['definition']['source'] = ('def run(inputs):\n    quantity = inputs["quantity"]\n'
                                     '    price = inputs["price"]\n    total = quantity * price\n    return round(total, 2)')
    checked_revision(item, revised)
    cases = [(checked_draft, item, lambda value: value.update(approval={'digest': value['digest']})),
             (checked_draft, item, lambda value: value.update(active_revision=1)),
             (checked_draft, item, lambda value: value['provenance'].update(selected_model='fallback')),
             (checked_draft, item, lambda value: value['definition']['schema']['properties']['quantity'].update(maximum=999)),
             (lambda value: checked_inference(value, request_id), run, lambda value: value.update(runtime_model='fallback')),
             (lambda value: checked_inference(value, request_id), run, lambda value: value.update(tool_results=[{'tool': 'forbidden'}])),
             (lambda value: checked_validation(item, value), validation, lambda value: value['tests'][0].update(actual=True)),
             (lambda value: checked_validation(item, value), validation, lambda value: value.update(tested_digest='d' * 64)),
             (lambda value: checked_revision(item, value), revised, lambda value: value.update(id='cap.' + 'f' * 32)),
             (lambda value: checked_revision(item, value), revised, lambda value: value.update(revision=1)),
             (lambda value: checked_revision(item, value), revised,
              lambda value: value['provenance'].update(request_id=item['provenance']['request_id'])),
             (lambda value: checked_revision(item, value), revised,
              lambda value: value['definition'].update(source=item['definition']['source']))]
    for check, original, change in cases:
        altered = copy.deepcopy(original); change(altered)
        try: check(altered)
        except VerificationError: continue
        raise VerificationError('self_check_accepted_invalid_evidence')
    return {'self_check': True, 'negative_cases': len(cases), 'revision_branch_checked': True, 'installed_contacted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version'); parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--report', type=Path); parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--revise-capability', help='Revise this existing unapproved synthetic capability; do not create another ID')
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps(self_check())); return 0
    if not args.version or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args.version) or args.report is None:
        parser.error('--version X.Y.Z and --report are required for installed verification')
    if args.revise_capability is not None and re.fullmatch(r'cap\.[a-f0-9]{32}', args.revise_capability) is None:
        parser.error('--revise-capability requires a capability ID')
    try: report = verify(args.data_dir, args.version, args.revise_capability)
    except Exception as exc:
        report = {'schema_version': 1, 'passed': False, 'error': str(exc) if isinstance(exc, VerificationError) else 'verification_internal_error',
                  'approved': False, 'active': False, 'command_execution_performed': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report)); return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
