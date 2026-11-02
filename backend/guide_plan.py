"""GuidePlan v1: teach an operation in a real window and verify each step from fresh UIA state.

The model proposes semantic targets and postconditions. Axx resolves targets only
against a fresh UI Automation observation of the same window and process, abstains
on ambiguity, and never treats a click, a drawn overlay or elapsed time as success.
"""
import json
import math
import re
import unicodedata

from backend.presentation_plan import PlanError, _closed, _text

SCHEMA_VERSION = '1.0'
MAX_STEPS = 8
MAX_PROMPT_CONTROLS = 120
CONTROL_TYPES = ('Button', 'Edit', 'CheckBox', 'ComboBox', 'Slider', 'MenuItem', 'TabItem', 'RadioButton',
                 'ListItem', 'TreeItem', 'Hyperlink', 'Text', 'Document', 'Spinner', 'SplitButton', 'DataItem')
POSTCONDITIONS = ('value_equals', 'value_changed', 'toggle_on', 'toggle_off', 'selected', 'expanded', 'exists',
                  'window_title_contains')
NEEDS_VALUE = ('value_equals', 'window_title_contains')
STEP_ID = re.compile(r'g[0-9]{1,3}')

GUIDE_CONTRACT = (
    'Vas a guiar al usuario para que haga él mismo una operación en la aplicación de la imagen. '
    'Recibes la lista de controles reales de esa ventana (UI Automation). Responde SOLO con un objeto JSON sin texto adicional: '
    '{"schema_version":"1.0","kind":"guide","goal":"…","steps":[{"id":"g1","instruction":"qué debe hacer el usuario",'
    '"target":{"name":"nombre exacto del control","control_type":"Button|Edit|CheckBox|ComboBox|Slider|MenuItem|TabItem|RadioButton|ListItem|TreeItem|Hyperlink|Text|Document|Spinner|SplitButton|DataItem","automation_id":"opcional"},'
    '"postcondition":{"kind":"value_equals|value_changed|toggle_on|toggle_off|selected|expanded|exists|window_title_contains","value":"solo para value_equals y window_title_contains",'
    '"target":{"name":"…","control_type":"…"}}}]}. '
    'Usa entre 1 y 8 pasos. Copia name, control_type y automation_id de la lista de controles; si el control no aparece, '
    'no lo inventes: usa solo los pasos que puedas señalar. Cada postcondición debe poder comprobarse leyendo la ventana después '
    'de que el usuario actúe; postcondition.target es opcional y por defecto es el mismo control. Nunca incluyas código ni enlaces.'
)


def _target(target, name='target'):
    _closed(target, ('name', 'control_type'), ('automation_id',), name=name)
    if target['control_type'] not in CONTROL_TYPES:
        raise PlanError(f'{name}.control_type no permitido.')
    result = {'name': _text(target['name'], 'name', 200), 'control_type': target['control_type']}
    if target.get('automation_id') not in (None, ''):
        result['automation_id'] = _text(target['automation_id'], 'automation_id', 200)
    return result


def _postcondition(post):
    _closed(post, ('kind',), ('value', 'target'), name='postcondition')
    if post['kind'] not in POSTCONDITIONS:
        raise PlanError('postcondition.kind no permitido.')
    result = {'kind': post['kind']}
    if post['kind'] in NEEDS_VALUE:
        result['value'] = _text(post.get('value'), 'value', 200)
    elif post.get('value') not in (None, ''):
        raise PlanError(f'{post["kind"]} no admite value.')
    if post.get('target') is not None:
        result['target'] = _target(post['target'], 'postcondition.target')
    return result


def validate_guide(plan):
    _closed(plan, ('schema_version', 'kind', 'goal', 'steps'), name='Guía')
    if plan['schema_version'] != SCHEMA_VERSION or plan['kind'] != 'guide':
        raise PlanError('Versión o tipo de guía no compatible.')
    steps = plan['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise PlanError(f'La guía necesita entre 1 y {MAX_STEPS} pasos.')
    result = []
    for step in steps:
        _closed(step, ('id', 'instruction', 'target', 'postcondition'), name='Paso de guía')
        if not isinstance(step['id'], str) or not STEP_ID.fullmatch(step['id']):
            raise PlanError('Cada paso de guía necesita un id como "g1".')
        result.append({'id': step['id'], 'instruction': _text(step['instruction'], 'instruction', 300),
                       'target': _target(step['target']), 'postcondition': _postcondition(step['postcondition'])})
    if len({s['id'] for s in result}) != len(result):
        raise PlanError('Los ids de los pasos de guía deben ser únicos.')
    return {'schema_version': SCHEMA_VERSION, 'kind': 'guide', 'goal': _text(plan['goal'], 'goal', 200), 'steps': result}


def _normal(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def prompt_controls(observed):
    """Compact, bounded control list for the model; secrets never leave as values."""
    rows = []
    for row in observed.get('controls', []):
        kind = str(row.get('control_type', '')).removeprefix('ControlType.')
        if kind in CONTROL_TYPES and row.get('name') and not row.get('offscreen'):
            rows.append({'name': row['name'][:120], 'control_type': kind, **({'automation_id': row['automation_id'][:80]} if row.get('automation_id') else {})})
        if len(rows) == MAX_PROMPT_CONTROLS:
            break
    return json.dumps({'window_title': observed.get('window_title', '')[:200], 'controls': rows}, ensure_ascii=False)


def resolve(observed, target):
    """Return (status, control). Abstain unless exactly one visible control matches."""
    kind = 'ControlType.' + target['control_type']
    rows = [r for r in observed.get('controls', []) if r.get('control_type') == kind and not r.get('offscreen')]
    matches = []
    if target.get('automation_id'):
        matches = [r for r in rows if r.get('automation_id') == target['automation_id']]
    if not matches:
        matches = [r for r in rows if _normal(r.get('name')) == _normal(target['name'])]
    if len(matches) > 1 or observed.get('truncated'):  # A cut-off tree may hide a duplicate, as in windows_automation.
        return 'ambiguous', None
    return ('found', matches[0]) if matches else ('not_found', None)


def snapshot(control):
    """The comparable state of one control: value text plus UIA pattern state."""
    return {'value': control.get('value'), 'state': control.get('state') or {}}


def _number(value):
    try:
        number = float(str(value).replace(',', '.'))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def evaluate(post, status, control, baseline, window_title):
    """Return VERIFIED, WAITING or UNKNOWN for one postcondition on a fresh observation."""
    kind = post['kind']
    if kind == 'window_title_contains':
        return 'VERIFIED' if _normal(post['value']) in _normal(window_title) else 'WAITING'
    if kind == 'exists':
        return 'VERIFIED' if status == 'found' else 'UNKNOWN' if status == 'ambiguous' else 'WAITING'
    if status != 'found':
        return 'UNKNOWN'  # The control vanished or became ambiguous: the effect cannot be proven.
    state = control.get('state') or {}
    if kind == 'value_changed':
        return 'VERIFIED' if snapshot(control) != baseline else 'WAITING'
    if kind == 'value_equals':
        current = state.get('RangeValue', {}).get('value') if 'RangeValue' in state else control.get('value')
        expected, actual = _number(post['value']), _number(current)
        if expected is not None and actual is not None:
            return 'VERIFIED' if abs(expected - actual) <= max(1e-6, abs(expected) * 1e-3) else 'WAITING'
        return 'VERIFIED' if _normal(current) == _normal(post['value']) else 'WAITING'
    if kind in ('toggle_on', 'toggle_off'):
        if 'Toggle' not in state:
            return 'UNKNOWN'
        return 'VERIFIED' if state['Toggle'] == ('On' if kind == 'toggle_on' else 'Off') else 'WAITING'
    if kind == 'selected':
        return 'UNKNOWN' if 'SelectionItem' not in state else 'VERIFIED' if state['SelectionItem'] is True else 'WAITING'
    return 'UNKNOWN' if 'ExpandCollapse' not in state else 'VERIFIED' if state['ExpandCollapse'] == 'Expanded' else 'WAITING'
