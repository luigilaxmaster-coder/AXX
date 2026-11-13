"""Explicit real probes of saved, authorized connections; receipts never contain prompts or credentials.

Run: python scripts/verify-recovery-providers.py --config <private providers.json> --output build/recovery/providers.json
Add --vision for the fixed synthetic aptitude image, or --codex for the existing ChatGPT account.
No settings are changed. Quota/spend from these calls is real. State and receipts stay beside --output.
"""
import argparse
import json
import os
import re
from pathlib import Path
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.connect.provider import CodexProvider
from backend.inference.adapter import InferenceAdapter
from backend.inference import provider_settings
from backend.magic_pen import MagicPenService
from PIL import Image, ImageDraw

SECRETS = []


def endpoint_state(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=5):
            return 'ACCESSIBLE'
    except urllib.error.HTTPError:
        return 'ACCESSIBLE'  # An HTTP rejection still proves transport reachability.
    except (urllib.error.URLError, TimeoutError, OSError):
        return 'UNREACHABLE_AT_PROBE'


def sanitized(value):
    text = json.dumps(value, ensure_ascii=False)
    for secret in SECRETS:
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    return json.loads(text)


def trace_calls(owner, method, attempts, save):
    original = getattr(owner, method)
    def traced(request, **kwargs):
        started = time.monotonic()
        row = {'stage': request['task'], 'model_requested': request['model'],
               'deadline_ms': request['deadline_ms'], 'output_schema_requested': bool(request.get('generation', {}).get('output_schema'))}
        attempts.append(row)
        try:
            result = original(request, **kwargs)
            row.update({k: result.get(k) for k in ('ok', 'route', 'finish_reason', 'usage', 'error')})
            row['response'] = (result.get('message') or {}).get('content')
            return result
        except Exception as exc:
            row['failure'] = failure(exc)
            raise
        finally:
            row['elapsed_seconds'] = round(time.monotonic() - started, 3)
            save()
    setattr(owner, method, traced)


def failure(exc):
    # Receipts classify errors without copying upstream bodies, URLs or credentials.
    message = str(exc).lower()
    reason = next((name for pattern, name in (
        (r'402|billing|payment|facturaci', 'BILLING_REQUIRED'),
        (r'503|high demand|overloaded|unavailable', 'PROVIDER_UNAVAILABLE'),
        (r'401|unauthori|authentication|api.?key|credential', 'AUTHENTICATION'),
        (r'429|quota|rate.limit|cuota|l[ií]mite', 'QUOTA'),
        (r'404|not.found|does.not.exist', 'MODEL_OR_ENDPOINT'),
        (r'timeout|timed.out|deadline|plazo', 'TIMEOUT'),
        (r'refus|connect|conexi', 'TRANSPORT'),
        (r'json|schema|plan|texto v[aá]lido|figura|no apto', 'OUTPUT_VALIDATION'),
    ) if re.search(pattern, message)), 'REQUEST_FAILED')
    code = getattr(exc, 'code', None)
    if code in ('RPC_TIMEOUT', 'DEADLINE_EXCEEDED'):
        reason = 'LOCAL_RPC_TIMEOUT' if code == 'RPC_TIMEOUT' else 'TIMEOUT'
    return sanitized({'state': 'FAIL', 'error_type': type(exc).__name__, 'reason': reason, 'message': str(exc)[:2000],
            **({'code': code} if isinstance(code, str) and re.fullmatch('[A-Z_]{1,80}', code) else {})})


def visual_flow(pen, provider, model):
    image = Image.new('RGB', (320, 200), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 50, 135, 155), fill='#d33b36')
    draw.ellipse((190, 65, 280, 155), fill='#2878c8')
    doc = pen.acquire(image, {'id': 'recovery-synthetic', 'x': 0, 'y': 0}, image=True)
    doc = pen.save({'id': doc['id'], 'expected_revision': doc['revision'],
        'selection': {'shape': 'rect', 'bounds': [0, 0, 320, 200]}, 'strokes': []})
    result, base = [], None
    for stage, question in (
        ('diagram_2d', 'Explica las dos figuras de la imagen en dos pasos con un diagrama 2D, sin scene.'),
        ('scene_3d', 'Crea una escena 3D conceptual sencilla: caja roja y esfera azul, exactamente dos piezas, con dos pasos explicativos.'),
        ('patch', 'Cambia solamente el color de la primera pieza a verde #22aa55 y explica el cambio. Conserva ambas piezas.'),
    ):
        body = {'id': doc['id'], 'revision': doc['revision'], 'request_id': uuid.uuid4().hex,
            'question': question, 'provider': provider, 'model': model, 'selection_mode': 'manual', 'format': 'presentation'}
        if stage == 'patch':
            if not base:
                result.append({'stage': stage, 'state': 'BLOCKED_NO_3D_BASE'})
                continue
            body['base_query_id'] = base
        started = time.monotonic()
        q = pen.start(body)
        deadline = started + 310
        while q['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(.2)
            q = pen.query({'id': doc['id'], 'query_id': q['id']})
        plan = q.get('presentation') or {}
        scene = plan.get('scene') or {}
        row = {'stage': stage, 'state': q['state'], 'source_id': doc['id'], 'query_id': q['id'],
            'elapsed_seconds': round(time.monotonic() - started, 2), 'steps': len(plan.get('steps', [])),
            'objects': len(scene.get('objects', [])), 'diagram': bool(plan.get('diagram'))}
        if q.get('error'):
            row['failure'] = failure(ValueError(q['error']))
        if stage == 'scene_3d' and q['state'] == 'completed':
            assert row['objects'] > 0, 'Completed 3D must contain real scene objects'
            base = q['id']
        if stage == 'patch' and q['state'] == 'completed':
            assert row['objects'] == 2 and scene['objects'][0]['color'] == '#22aa55', 'Patch must update and preserve the scene'
        result.append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', action='append')
    parser.add_argument('--vision', action='store_true')
    parser.add_argument('--codex', action='store_true')
    parser.add_argument('--flow', action='store_true', help='Real 2D, 3D and patch requests using only the synthetic image')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    provider_settings.load_credentials(args.config)
    SECRETS.extend(os.environ[p['api_key_env']] for p in config.get('providers', [])
                   if p.get('api_key_env') and os.environ.get(p['api_key_env']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'source': 'real_provider_requests', 'tested_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'providers': [], 'attempts': []}
    report_lock = threading.Lock()
    def save():
        with report_lock:
            temp = args.output.with_suffix('.tmp')
            temp.write_text(json.dumps(sanitized(report), ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(args.output)
    with InferenceAdapter(config, args.output.parent / 'probe-state.db') as adapter:
        trace_calls(adapter, 'route', report['attempts'], save)
        pen = MagicPenService(args.output.parent, adapter)
        try:
            for p in provider_settings.public_entries(config):
                if args.name and p['name'] not in args.name:
                    continue
                row = {k: p[k] for k in ('name', 'model', 'kind', 'has_key')}
                row.update(configured=True, endpoint=endpoint_state(p['base_url']), authenticated='NOT_VERIFIED',
                           real_response='NOT_TESTED', vision='NOT_TESTED', structured_output='NOT_TESTED',
                           cost_quota={k: p[k] for k in ('free_confirmed', 'billing_allowed', 'cost_evidence', 'quota_scope_id')}, last_error=None)
                report['providers'].append(row)
                if p['enabled'] is False or not (p['free_confirmed'] or p['billing_allowed']):
                    row['state'] = 'NOT_AUTHORIZED_OR_DISABLED'
                    save()
                    continue
                if p['name'] == 'openrouter-free' and not p['has_key']:
                    row.update(state='NOT_VERIFIABLE', last_error='MISSING_CREDENTIAL')
                    save()
                    continue
                started = time.monotonic()
                kind = p['kind'] or ('ollama' if p['base_url'].startswith('http://127.0.0.1:11434') else 'custom')
                try:
                    catalog = provider_settings.discover({'provider': kind, 'name': p['name'], 'base_url': p['base_url'],
                        'protocol': p['protocol'] or 'openai'}, config)
                    row['catalog'] = {'state': 'PASS', 'selected_exists': p['model'] in catalog['models'], 'count': len(catalog['models'])}
                    row['endpoint'] = 'ACCESSIBLE'
                except Exception as exc:
                    row['catalog'] = failure(exc)
                    if re.search(r'HTTP \d{3}', str(exc)):
                        row['endpoint'] = 'ACCESSIBLE'
                request = {'request_id': 'recovery-' + uuid.uuid4().hex, 'conversation_id': 'recovery-probe',
                    'selection_mode': 'manual', 'task': 'chat', 'provider_name': p['name'], 'model': p['model'],
                    'allow_paid': False, 'deadline_ms': 25000, 'generation': {'max_tokens': 512},
                    'messages': [{'role': 'user', 'content': 'Responde solamente OK.'}]}
                try:
                    result = pen._call({'cancel': threading.Event()}, p, request, False, 'recovery_probe')
                    text = result.get('message', {}).get('content')
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError('Empty model response')
                    row['response'] = {'state': 'PASS', 'nonempty': True, 'usage': result.get('usage')}
                    row.update(endpoint='ACCESSIBLE', authenticated='VERIFIED', real_response='VERIFIED')
                except Exception as exc:
                    row['response'] = failure(exc)
                    row['last_error'] = row['response']
                row['elapsed_seconds'] = round(time.monotonic() - started, 2)
                save()
                if args.vision and 'vision' in (p['capabilities'] or []):
                    try:
                        verdict = pen.verify_spatial({'provider': p['name'], 'model': p['model'], 'effort': 'auto'})
                        row['vision'] = {k: verdict.get(k) for k in ('verdict', 'capabilities', 'structured_output', 'reason')}
                        row.update(endpoint='ACCESSIBLE', authenticated='VERIFIED', real_response='VERIFIED')
                        row['structured_output'] = verdict.get('structured_output') or verdict.get('mode') or 'SEE_CAPABILITY_RECEIPT'
                    except Exception as exc:
                        row['vision'] = failure(exc)
                        row['last_error'] = row['vision']
                    save()
                    if args.flow and row.get('vision', {}).get('verdict') == 'apto_3d':
                        row['flow'] = visual_flow(pen, p['name'], p['model'])
                        save()
        finally:
            pen.close()
    if args.codex:
        codex = CodexProvider(None, args.output.parent / 'codex-probe.db', Path(__file__).resolve().parents[1])
        try:
            status = codex.status()
            report['codex'] = {k: status.get(k) for k in ('state', 'authenticated', 'inference_verified', 'runtime', 'selected_model', 'models', 'allow_paid', 'extra_credit_fallback')}
            if status.get('error'):
                report['codex']['error_code'] = status['error'].get('code')
            if args.vision and status.get('authenticated'):
                report['codex']['attempts'] = []
                report['codex']['rpc'] = []
                original_rpc = codex._rpc
                def traced_rpc(method, params=None, timeout=20):
                    started = time.monotonic()
                    rpc = {'method': method, 'timeout_seconds': timeout}
                    report['codex']['rpc'].append(rpc)
                    try:
                        result = original_rpc(method, params, timeout)
                        rpc.update(state='PASS', model=result.get('model'), model_provider=result.get('modelProvider'))
                        return result
                    except Exception as exc:
                        rpc['failure'] = failure(exc)
                        raise
                    finally:
                        rpc['elapsed_seconds'] = round(time.monotonic() - started, 3)
                        save()
                codex._rpc = traced_rpc
                trace_calls(codex, 'generate_spatial', report['codex']['attempts'], save)
                pen = MagicPenService(args.output.parent / 'codex', codex_provider=codex)
                try:
                    report['codex']['vision'] = []
                    for attempt in range(3):
                        try:
                            verdict = pen.verify_spatial({'provider': '@codex', 'model': status['selected_model'], 'effort': 'auto'})
                            report['codex']['vision'].append({k: verdict.get(k) for k in ('verdict', 'capabilities', 'structured_output', 'reason')})
                        except Exception as exc:
                            report['codex']['vision'].append(failure(exc))
                        save()
                finally:
                    pen.close()
        finally:
            codex.close()
    save()
    print(args.output)


if __name__ == '__main__':
    main()
