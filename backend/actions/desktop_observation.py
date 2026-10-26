"""Compose UIA and optional local Magic Pen capture without a second executor."""
from __future__ import annotations

import time

from . import windows_automation as uia


def observe_desktop(window_id, expected_pid, *, capture_service=None, monitor_id=None, cancelled=None):
    result = uia.inspect_controls(window_id, expected_pid, cancelled=cancelled)
    observation = result['observation']
    result['quality'] = 'truncated' if result.get('truncated') else 'complete'
    if observation.get('minimized'):
        result['quality'] = 'unobservable'
    if monitor_id is None:
        return result
    if capture_service is None:
        raise ValueError('CAPTURE_UNAVAILABLE: el productor Magic Pen no está conectado.')
    if observation.get('minimized'):
        raise ValueError('CAPTURE_UNAVAILABLE: restaura la ventana antes de observarla.')
    monitor = next((m for m in observation['monitors'] if m['id'] == monitor_id), None)
    bounds = observation['window_bounds']
    if not monitor or not (bounds['x'] < monitor['x']+monitor['width'] and monitor['x'] < bounds['x']+bounds['width']
                           and bounds['y'] < monitor['y']+monitor['height'] and monitor['y'] < bounds['y']+bounds['height']):
        raise ValueError('La pantalla seleccionada no contiene la ventana observada.')
    if cancelled is not None and cancelled.is_set():
        raise ValueError('Observación cancelada antes de capturar.')
    captured = capture_service.capture({'monitor': monitor_id})
    after = uia.observe_geometry(window_id)
    if any(after[k] != observation[k] for k in ('window_bounds', 'monitors', 'minimized')):
        raise ValueError('STALE_OBSERVATION: la geometría cambió durante la captura.')
    uia.get_observation(observation['observation_id'], window_id, expected_pid)
    if uia.process_started(expected_pid) != observation['process_started']:
        raise ValueError('STALE_OBSERVATION: cambió la instancia del proceso durante la captura.')
    source = captured['source']
    if not any(w['window_id'] == window_id and w['pid'] == expected_pid and w['title'] == result['window_title'] for w in uia.list_windows()):
        raise ValueError('STALE_OBSERVATION: cambió el objetivo durante la captura.')
    image = capture_service.original(captured)
    black = image.convert('L').getextrema() == (0, 0)
    observation['screenshot'] = {'document_id': captured['id'], 'revision': captured['revision'],
                                'sha256': source['sha256'], 'captured_at': source['captured_at'],
                                'age_ms': max(0, round((time.time()-source['captured_at'])*1000)),
                                'width': source['width'], 'height': source['height'], 'scope': 'monitor',
                                'transform': {'scale_x': 1, 'scale_y': 1, 'offset_x': source['x'], 'offset_y': source['y']},
                                'content_status': 'unobservable' if black else 'captured',
                                'local_only': True}
    observation.pop('screenshot_unavailable_reason', None)
    if black:
        result['quality'] = 'unobservable'
    uia._remember_observation(result)
    return result
