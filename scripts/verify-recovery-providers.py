"""Explicit real probes of saved, authorized connections; receipts never contain prompts or credentials.

Run: python scripts/verify-recovery-providers.py --config <private providers.json> --output build/recovery/providers.json
Add --vision for the fixed synthetic aptitude image, or --codex for the existing ChatGPT account.
No settings are changed. Quota/spend from these calls is real. State and receipts stay beside --output.
"""
import argparse
import json
import re
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.connect.provider import CodexProvider
from backend.inference.adapter import InferenceAdapter
from backend.inference import provider_settings
from backend.magic_pen import MagicPenService
from PIL import Image, ImageDraw


def failure(exc):
    # Receipts classify errors without copying upstream bodies, URLs or credentials.
    message = str(exc).lower()
    reason = next((name for pattern, name in (
        (r'401|unauthori|authentication|api.?key|credential', 'AUTHENTICATION'),
        (r'429|quota|rate.limit|cuota|l[ií]mite', 'QUOTA'),
        (r'404|not.found|does.not.exist', 'MODEL_OR_ENDPOINT'),
        (r'timeout|timed.out|deadline|plazo', 'TIMEOUT'),
        (r'refus|connect|conexi', 'CONNECTION'),
    ) if re.search(pattern, message)), 'REQUEST_FAILED')
    code = getattr(exc, 'code', None)
    return {'state': 'FAIL', 'error_type': type(exc).__name__, 'reason': reason,
            **({'code': code} if isinstance(code, str) and re.fullmatch('[A-Z_]{1,80}', code) else {})}


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'source': 'real_provider_requests', 'providers': []}
    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with InferenceAdapter(config, args.output.parent / 'probe-state.db') as adapter:
        pen = MagicPenService(args.output.parent, adapter)
        try:
            for p in provider_settings.public_entries(config):
                if args.name and p['name'] not in args.name:
                    continue
                row = {k: p[k] for k in ('name', 'model', 'kind', 'has_key')}
                report['providers'].append(row)
                if p['enabled'] is False or not (p['free_confirmed'] or p['billing_allowed']):
                    row['state'] = 'NOT_AUTHORIZED_OR_DISABLED'
                    save()
                    continue
                started = time.monotonic()
                kind = p['kind'] or ('ollama' if p['base_url'].startswith('http://127.0.0.1:11434') else 'custom')
                try:
                    catalog = provider_settings.discover({'provider': kind, 'name': p['name'], 'base_url': p['base_url'],
                        'protocol': p['protocol'] or 'openai'}, config)
                    row['catalog'] = {'state': 'PASS', 'selected_exists': p['model'] in catalog['models'], 'count': len(catalog['models'])}
                except Exception as exc:
                    row['catalog'] = failure(exc)
                request = {'request_id': 'recovery-' + uuid.uuid4().hex, 'conversation_id': 'recovery-probe',
                    'selection_mode': 'manual', 'task': 'chat', 'provider_name': p['name'], 'model': p['model'],
                    'allow_paid': False, 'deadline_ms': 25000, 'generation': {'max_tokens': 32},
                    'messages': [{'role': 'user', 'content': 'Responde solamente OK.'}]}
                try:
                    result = pen._call({'cancel': __import__('threading').Event()}, p, request, False, 'recovery_probe')
                    text = result.get('message', {}).get('content')
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError('Empty model response')
                    row['response'] = {'state': 'PASS', 'nonempty': True, 'usage': result.get('usage')}
                except Exception as exc:
                    row['response'] = failure(exc)
                row['elapsed_seconds'] = round(time.monotonic() - started, 2)
                save()
                if args.vision and 'vision' in (p['capabilities'] or []):
                    try:
                        verdict = pen.verify_spatial({'provider': p['name'], 'model': p['model'], 'effort': 'auto'})
                        row['vision'] = {k: verdict.get(k) for k in ('verdict', 'capabilities', 'structured_output', 'reason')}
                    except Exception as exc:
                        row['vision'] = failure(exc)
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
            report['codex'] = {k: status.get(k) for k in ('state', 'authenticated', 'inference_verified', 'runtime', 'models')}
            if status.get('error'):
                report['codex']['error_code'] = status['error'].get('code')
            if args.vision and status.get('authenticated'):
                pen = MagicPenService(args.output.parent / 'codex', codex_provider=codex)
                try:
                    verdict = pen.verify_spatial({'provider': '@codex', 'model': status['selected_model'], 'effort': 'auto'})
                    report['codex']['vision'] = {k: verdict.get(k) for k in ('verdict', 'capabilities', 'structured_output', 'reason')}
                except Exception as exc:
                    report['codex']['vision'] = failure(exc)
                finally:
                    pen.close()
        finally:
            codex.close()
    save()
    print(args.output)


if __name__ == '__main__':
    main()
