"""GuideSession v1: one declarative, versioned description of a visual explanation (Visual Guidance Engine).

Contracts are additive: a GuideSession is derived from documents that are already validated (PresentationPlan for
diagrams and 3D, GuidePlan for real windows, drawing analyses for images). The model never supplies coordinates here:
anchors reference ids that exist in the source (scene object, diagram node, UIA control description, image region),
and the renderers compute geometry from the live source (camera projection, fresh UIA bounds, segmented regions).
Nothing in a session is executable: there are no commands, scripts, URLs or HTML, only visual actions on anchors.
"""
from __future__ import annotations

import copy
import re
import time
import unicodedata
from typing import Any

SCHEMA_VERSION = 'guide.v1'
SOURCE_KINDS = ('presentation', 'screen', 'drawing', 'diagram', 'code')
GUIDE_MODES = ('object3d', 'diagram', 'screen', 'drawing', 'code', 'mixed')
STATUSES = ('ready', 'playing', 'paused', 'waiting_user', 'completed', 'stale')
ANCHOR_TYPES = ('dom', 'uia', 'vision', 'image_region', 'diagram', 'object3d', 'code_line')
COORDINATE_SPACES = ('scene', 'diagram', 'screen_physical', 'window_relative', 'image_normalized', 'document_lines')
ANNOTATION_KINDS = (
    'arrow', 'highlight_box', 'outline', 'region_mask', 'pulse', 'step_number', 'label', 'callout', 'path',
    'guide_line', 'motion_direction', 'color_zone', 'avoid_zone', 'point_sequence', 'dimension', 'object_marker',
    'part_highlight', 'dim_others', 'zoom_frame', 'flow')
CAMERA_ACTIONS = ('none', 'overview', 'frame_targets', 'keep')
SCENE_ACTIONS = ('none', 'explode', 'assemble', 'animate', 'section')
COMPLETION = ('manual', 'narration_end', 'await_observation', 'await_interaction')
FAILURE = ('pause_and_reobserve', 'skip_target', 'stop')
VISIBILITY = ('visible', 'hidden', 'occluded', 'unresolved', 'stale')
FORBIDDEN_KEYS = {'command', 'commands', 'script', 'code', 'html', 'url', 'href', 'exec', 'eval', 'shell', 'keys', 'text_input'}
MAX_STEPS, MAX_ANCHORS, MAX_ANNOTATIONS = 24, 96, 240

# Illustrative motion chosen by the system from the part's shape or name (never a physics claim).
ROTATING = ('crankshaft', 'gear', 'pulley', 'wheel', 'fan', 'rotor', 'turbine', 'propeller', 'cigüeñal', 'engranaje', 'polea',
            'rueda', 'ventilador', 'rotor', 'turbina', 'hélice', 'eje', 'shaft', 'disco', 'cam', 'leva', 'tornillo sin fin')
TRANSLATING = ('piston', 'pistón', 'émbolo', 'embolo', 'slider', 'corredera', 'connecting_rod', 'biela', 'vástago', 'plunger', 'válvula', 'valve')
EXPLODE_WORDS = ('despiece', 'despiez', 'explot', 'desmont', 'separa', 'desarm', 'desensambl')
ASSEMBLE_WORDS = ('reensambl', 'ensambla', 'vuelve a unir', 'reúne', 'monta de nuevo')
MOTION_WORDS = ('gira', 'rota', 'mueve', 'desplaza', 'oscila', 'funciona', 'movimiento', 'recorrido', 'transmite', 'empuja', 'carrera')


class GuideError(ValueError):
    """A GuideSession or one of its parts violates the contract."""


def _norm(text: Any) -> str:
    return ' '.join(unicodedata.normalize('NFKC', str(text or '')).casefold().split())


def _text(value: Any, name: str, limit: int, *, required: bool = True) -> str:
    if value is None and not required:
        return ''
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise GuideError(f'{name} debe ser texto de 1 a {limit} caracteres.')
    return value.strip()


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}', value):
        raise GuideError(f'{name} inválido.')
    return value


def _closed(obj: Any, required: tuple, optional: tuple = (), *, name: str) -> dict:
    if not isinstance(obj, dict):
        raise GuideError(f'{name} debe ser un objeto.')
    forbidden = FORBIDDEN_KEYS & set(obj)
    if forbidden:
        raise GuideError(f'{name} no puede contener {sorted(forbidden)}: una guía solo describe acciones visuales.')
    missing, extra = set(required) - set(obj), set(obj) - set(required) - set(optional)
    if missing or extra:
        raise GuideError(f'{name}: faltan {sorted(missing)} o sobran {sorted(extra)}.')
    return obj


def _enum(value: Any, allowed: tuple, name: str) -> str:
    if value not in allowed:
        raise GuideError(f'{name} debe ser uno de {allowed}.')
    return value


def _number(value: Any, name: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high:
        raise GuideError(f'{name} fuera de rango.')
    return float(value)


def validate_anchor(anchor: dict) -> dict:
    _closed(anchor, ('anchor_id', 'type', 'target_ref', 'coordinate_space', 'confidence', 'visibility'),
            ('source_fingerprint', 'geometry', 'verified_at', 'update_policy', 'label'), name='GuideAnchor')
    target = anchor['target_ref']
    if not isinstance(target, dict) or not target or FORBIDDEN_KEYS & set(target) or len(str(target)) > 600:
        raise GuideError('GuideAnchor.target_ref inválido.')
    geometry = anchor.get('geometry')
    if geometry is not None and (not isinstance(geometry, dict) or len(str(geometry)) > 4000):
        raise GuideError('GuideAnchor.geometry inválida.')
    return {'anchor_id': _id(anchor['anchor_id'], 'anchor_id'), 'type': _enum(anchor['type'], ANCHOR_TYPES, 'type'),
            'target_ref': copy.deepcopy(target), 'coordinate_space': _enum(anchor['coordinate_space'], COORDINATE_SPACES, 'coordinate_space'),
            'confidence': _number(anchor['confidence'], 'confidence', 0, 1), 'visibility': _enum(anchor['visibility'], VISIBILITY, 'visibility'),
            **({'source_fingerprint': _text(anchor['source_fingerprint'], 'source_fingerprint', 200)} if anchor.get('source_fingerprint') else {}),
            **({'geometry': copy.deepcopy(geometry)} if geometry is not None else {}),
            **({'verified_at': _number(anchor['verified_at'], 'verified_at', 0, 4e12)} if anchor.get('verified_at') is not None else {}),
            **({'update_policy': _enum(anchor['update_policy'], ('live_projection', 'reobserve', 'static'), 'update_policy')} if anchor.get('update_policy') else {}),
            **({'label': _text(anchor['label'], 'label', 120)} if anchor.get('label') else {})}


def validate_annotation(item: dict, anchors: set) -> dict:
    _closed(item, ('annotation_id', 'kind', 'anchor_id', 'visibility', 'priority'), ('appearance', 'timing', 'text'), name='GuideAnnotation')
    if item['anchor_id'] is not None and item['anchor_id'] not in anchors:
        raise GuideError('GuideAnnotation apunta a un anclaje inexistente.')
    appearance = item.get('appearance') or {}
    if not isinstance(appearance, dict) or FORBIDDEN_KEYS & set(appearance) or len(str(appearance)) > 600:
        raise GuideError('GuideAnnotation.appearance inválida.')
    timing = item.get('timing') or {}
    if not isinstance(timing, dict) or set(timing) - {'start_ms', 'duration_ms', 'with_narration'}:
        raise GuideError('GuideAnnotation.timing inválido.')
    return {'annotation_id': _id(item['annotation_id'], 'annotation_id'), 'kind': _enum(item['kind'], ANNOTATION_KINDS, 'kind'),
            'anchor_id': item['anchor_id'], 'visibility': _enum(item['visibility'], ('visible', 'hidden'), 'visibility'),
            'priority': int(_number(item['priority'], 'priority', 0, 9)), 'appearance': copy.deepcopy(appearance), 'timing': copy.deepcopy(timing),
            **({'text': _text(item['text'], 'text', 200)} if item.get('text') else {})}


def validate_step(step: dict, anchors: set, annotations: set) -> dict:
    _closed(step, ('step_id', 'title', 'narration', 'target_anchor_ids', 'annotation_ids', 'camera_action', 'scene_action',
                   'completion_policy', 'failure_policy'), ('expected_observation', 'motion'), name='GuideStep')
    for ref, pool, name in ((step['target_anchor_ids'], anchors, 'target_anchor_ids'), (step['annotation_ids'], annotations, 'annotation_ids')):
        if not isinstance(ref, list) or len(ref) > 32 or any(r not in pool for r in ref):
            raise GuideError(f'GuideStep.{name} refiere elementos inexistentes.')
    motion = step.get('motion')
    if motion is not None:
        _closed(motion, ('anchor_id', 'kind', 'axis'), ('illustrative',), name='GuideStep.motion')
        if motion['anchor_id'] not in anchors:
            raise GuideError('GuideStep.motion apunta a un anclaje inexistente.')
        _enum(motion['kind'], ('rotate', 'translate'), 'motion.kind'); _enum(motion['axis'], ('x', 'y', 'z'), 'motion.axis')
        if motion.get('illustrative', True) is not True:
            raise GuideError('Solo se admiten animaciones ilustrativas; una simulación física necesita su propio validador.')
    expected = step.get('expected_observation')
    if expected is not None and (not isinstance(expected, dict) or FORBIDDEN_KEYS & set(expected) or len(str(expected)) > 800):
        raise GuideError('GuideStep.expected_observation inválida.')
    return {'step_id': _id(step['step_id'], 'step_id'), 'title': _text(step['title'], 'title', 120), 'narration': _text(step['narration'], 'narration', 1200),
            'target_anchor_ids': list(step['target_anchor_ids']), 'annotation_ids': list(step['annotation_ids']),
            'camera_action': _enum(step['camera_action'], CAMERA_ACTIONS, 'camera_action'), 'scene_action': _enum(step['scene_action'], SCENE_ACTIONS, 'scene_action'),
            'completion_policy': _enum(step['completion_policy'], COMPLETION, 'completion_policy'),
            'failure_policy': _enum(step['failure_policy'], FAILURE, 'failure_policy'),
            **({'expected_observation': copy.deepcopy(expected)} if expected is not None else {}),
            **({'motion': {**motion, 'illustrative': True}} if motion is not None else {})}


def validate_session(doc: dict) -> dict:
    _closed(doc, ('schema_version', 'guide_id', 'source_kind', 'source_ref', 'source_revision', 'user_goal', 'guide_mode', 'status',
                  'current_step_id', 'steps', 'anchors', 'annotations', 'timeline', 'verification_state', 'created_at', 'updated_at'),
            ('revision',), name='GuideSession')
    if doc['schema_version'] != SCHEMA_VERSION:
        raise GuideError('Versión de GuideSession no compatible.')
    for key, limit in (('anchors', MAX_ANCHORS), ('annotations', MAX_ANNOTATIONS), ('steps', MAX_STEPS)):
        if not isinstance(doc[key], list) or len(doc[key]) > limit or (key == 'steps' and not doc[key]):
            raise GuideError(f'GuideSession.{key} inválido.')
    anchors = [validate_anchor(a) for a in doc['anchors']]
    anchor_ids = {a['anchor_id'] for a in anchors}
    annotations = [validate_annotation(a, anchor_ids) for a in doc['annotations']]
    annotation_ids = {a['annotation_id'] for a in annotations}
    steps = [validate_step(s, anchor_ids, annotation_ids) for s in doc['steps']]
    for items, key in ((anchors, 'anchor_id'), (annotations, 'annotation_id'), (steps, 'step_id')):
        if len({i[key] for i in items}) != len(items):
            raise GuideError(f'GuideSession: {key} repetido.')
    if doc['current_step_id'] not in {s['step_id'] for s in steps}:
        raise GuideError('current_step_id no pertenece a la guía.')
    if not isinstance(doc['timeline'], list) or len(doc['timeline']) > 400 or not isinstance(doc['verification_state'], dict):
        raise GuideError('GuideSession.timeline o verification_state inválidos.')
    return {'schema_version': SCHEMA_VERSION, 'guide_id': _id(doc['guide_id'], 'guide_id'),
            'source_kind': _enum(doc['source_kind'], SOURCE_KINDS, 'source_kind'), 'source_ref': _id(doc['source_ref'], 'source_ref'),
            'source_revision': int(_number(doc['source_revision'], 'source_revision', 0, 1e9)), 'user_goal': _text(doc['user_goal'], 'user_goal', 600),
            'guide_mode': _enum(doc['guide_mode'], GUIDE_MODES, 'guide_mode'), 'status': _enum(doc['status'], STATUSES, 'status'),
            'current_step_id': doc['current_step_id'], 'steps': steps, 'anchors': anchors, 'annotations': annotations,
            'timeline': copy.deepcopy(doc['timeline']), 'verification_state': copy.deepcopy(doc['verification_state']),
            'created_at': _number(doc['created_at'], 'created_at', 0, 4e12), 'updated_at': _number(doc['updated_at'], 'updated_at', 0, 4e12),
            'revision': int(doc.get('revision', 1))}


# ---------- builders (the system chooses the representation) ----------

def _motion_for(obj: dict) -> dict | None:
    text = _norm(str(obj.get('shape', '')) + ' ' + str(obj.get('label', '')) + ' ' + str(obj.get('group', '')))
    if any(w in text for w in TRANSLATING):
        return {'kind': 'translate', 'axis': 'y'}
    if any(w in text for w in ROTATING):
        return {'kind': 'rotate', 'axis': 'y'}  # revolution bodies have their axis on local Y (presentation_plan contract)
    return None


def from_presentation(plan: dict, *, source_ref: str, revision: int = 1, user_goal: str = '', now: float | None = None) -> dict:
    """Derive the guide from a validated PresentationPlan: anchors are scene/diagram ids that exist in the plan."""
    now = time.time() if now is None else now
    scene, diagram = plan.get('scene') or {}, plan.get('diagram') or {}
    objects = {o['id']: o for o in scene.get('objects', [])}
    anchors, annotations, steps = [], [], []
    for o in objects.values():
        anchors.append({'anchor_id': 'a-' + o['id'], 'type': 'object3d', 'target_ref': {'object_id': o['id']}, 'coordinate_space': 'scene',
                        'geometry': {k: o[k] for k in ('position', 'size') if k in o}, 'confidence': 1.0, 'visibility': 'visible',
                        'update_policy': 'live_projection', 'label': o.get('label', o['id'])[:120]})
    for n in diagram.get('nodes', []):
        anchors.append({'anchor_id': 'a-' + n['id'], 'type': 'diagram', 'target_ref': {'node_id': n['id']}, 'coordinate_space': 'diagram',
                        'geometry': {'bounds': n.get('bounds')}, 'confidence': 1.0, 'visibility': 'visible', 'update_policy': 'static',
                        'label': n.get('label', n['id'])[:120]})
    exploded = False
    for index, s in enumerate(plan.get('steps', [])):
        text = _norm(s.get('title', '') + ' ' + s.get('body', '') + ' ' + s.get('narration', ''))
        targets = [i for i in (s.get('focus') or []) if i in objects]
        nodes = [n['id'] for n in diagram.get('nodes', []) if n.get('step_id') == s['id']]
        ids = []
        for i in targets:
            for kind, prio in (('part_highlight', 0), ('callout', 1)):
                aid = f"n-{s['id']}-{kind}-{i}"
                annotations.append({'annotation_id': aid, 'kind': kind, 'anchor_id': 'a-' + i, 'visibility': 'visible', 'priority': prio,
                                    'text': objects[i].get('label', i)[:200], 'timing': {'with_narration': True}})
                ids.append(aid)
        if targets and len(targets) < len(objects):
            aid = f"n-{s['id']}-dim"
            annotations.append({'annotation_id': aid, 'kind': 'dim_others', 'anchor_id': None, 'visibility': 'visible', 'priority': 3})
            ids.append(aid)
        for node in nodes:
            aid = f"n-{s['id']}-flow-{node}"
            annotations.append({'annotation_id': aid, 'kind': 'flow', 'anchor_id': 'a-' + node, 'visibility': 'visible', 'priority': 2})
            ids.append(aid)
        motion = None
        if any(w in text for w in MOTION_WORDS):
            motion = next(({'anchor_id': 'a-' + i, **m, 'illustrative': True} for i in targets if (m := _motion_for(objects[i]))), None)
        if motion:
            aid = f"n-{s['id']}-motion"
            annotations.append({'annotation_id': aid, 'kind': 'motion_direction', 'anchor_id': motion['anchor_id'], 'visibility': 'visible', 'priority': 1})
            ids.append(aid)
        if any(w in text for w in EXPLODE_WORDS) and objects:
            action, exploded = 'explode', True
        elif exploded and any(w in text for w in ASSEMBLE_WORDS):
            action, exploded = 'assemble', False
        else:
            action = 'animate' if motion else 'none'
        steps.append({'step_id': s['id'], 'title': s['title'][:120], 'narration': (s.get('narration') or s.get('body') or s['title'])[:1200],
                      'target_anchor_ids': ['a-' + i for i in targets] + ['a-' + n for n in nodes], 'annotation_ids': ids,
                      'camera_action': 'frame_targets' if targets else ('overview' if objects else 'none'), 'scene_action': action,
                      'completion_policy': 'narration_end', 'failure_policy': 'skip_target', **({'motion': motion} if motion else {})})
    fidelity = plan.get('fidelity', 'conceptual')
    session = {'schema_version': SCHEMA_VERSION, 'guide_id': 'g-' + source_ref[:40], 'source_kind': 'presentation', 'source_ref': source_ref,
               'source_revision': int(revision), 'user_goal': (user_goal or plan.get('title') or 'Explicación')[:600],
               'guide_mode': 'mixed' if objects and diagram.get('nodes') else 'object3d' if objects else 'diagram',
               'status': 'ready', 'current_step_id': steps[0]['step_id'], 'steps': steps, 'anchors': anchors, 'annotations': annotations,
               'timeline': [{'step_id': s['step_id'], 'events': ['narrate'] + (['camera'] if s['camera_action'] != 'none' else [])
                             + ([s['scene_action']] if s['scene_action'] != 'none' else []) + (['annotations'] if s['annotation_ids'] else [])} for s in steps],
               'verification_state': {'anchors_resolved': len(anchors), 'anchors_unresolved': 0,
                                      # 3D-08: plan scenes are conceptual; only CAD with verified congruence carries measurements.
                                      'geometry': 'conceptual' if fidelity != 'technical' else 'technical_unmeasured', 'measurements_verified': False,
                                      'animation': 'illustrative'},
               'created_at': now, 'updated_at': now, 'revision': 1}
    return validate_session(session)


def from_guide_plan(guide: dict, *, source_ref: str, window: dict | None = None, now: float | None = None) -> dict:
    """Real-window tutorial: UIA anchors describe the control; fresh observations compute bounds (never the model)."""
    now = time.time() if now is None else now
    anchors, annotations, steps = [], [], []
    for index, s in enumerate(guide['steps'], start=1):
        aid = 'a-' + s['id']
        anchors.append({'anchor_id': aid, 'type': 'uia', 'target_ref': dict(s['target']), 'coordinate_space': 'screen_physical',
                        'confidence': 0.0, 'visibility': 'unresolved', 'update_policy': 'reobserve', 'label': s['target']['name'][:120],
                        **({'source_fingerprint': f"window:{window['window_id']}:{window['pid']}"} if window else {})})
        ids = []
        for kind, prio in (('outline', 0), ('arrow', 0), ('step_number', 1), ('pulse', 2)):
            nid = f"n-{s['id']}-{kind}"
            annotations.append({'annotation_id': nid, 'kind': kind, 'anchor_id': aid, 'visibility': 'visible', 'priority': prio,
                                **({'text': str(index)} if kind == 'step_number' else {})})
            ids.append(nid)
        steps.append({'step_id': s['id'], 'title': s['instruction'][:120], 'narration': s['instruction'], 'target_anchor_ids': [aid],
                      'annotation_ids': ids, 'camera_action': 'none', 'scene_action': 'none', 'completion_policy': 'await_observation',
                      'failure_policy': 'pause_and_reobserve', 'expected_observation': dict(s['postcondition'])})
    session = {'schema_version': SCHEMA_VERSION, 'guide_id': 'g-' + source_ref[:40], 'source_kind': 'screen', 'source_ref': source_ref,
               'source_revision': 1, 'user_goal': guide['goal'][:600], 'guide_mode': 'screen', 'status': 'ready',
               'current_step_id': steps[0]['step_id'], 'steps': steps, 'anchors': anchors, 'annotations': annotations,
               'timeline': [{'step_id': s['step_id'], 'events': ['narrate', 'annotations', 'await_observation']} for s in steps],
               'verification_state': {'anchors_resolved': 0, 'anchors_unresolved': len(anchors), 'credentials_recorded': False},
               'created_at': now, 'updated_at': now, 'revision': 1}
    return validate_session(session)


def advance(session: dict, *, step_id: str | None = None, status: str | None = None, expected_revision: int | None = None,
            now: float | None = None) -> dict:
    """Persisted player state (resume after restart). CAS on revision so two players never overwrite each other."""
    if expected_revision is not None and expected_revision != session.get('revision', 1):
        raise GuideError('La guía cambió en otra ventana; recarga el estado antes de continuar.')
    nxt = copy.deepcopy(session)
    if step_id is not None:
        if step_id not in {s['step_id'] for s in nxt['steps']}:
            raise GuideError('Paso desconocido.')
        nxt['current_step_id'] = step_id
    if status is not None:
        nxt['status'] = _enum(status, STATUSES, 'status')
    nxt['revision'] = nxt.get('revision', 1) + 1
    nxt['updated_at'] = time.time() if now is None else now
    return validate_session(nxt)
