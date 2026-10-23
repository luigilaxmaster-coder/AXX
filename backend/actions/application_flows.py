"""Typed application adapters. Durable selectors are resolved on every execution.

No saved HWND, coordinates, shell expressions, or UIA RuntimeIds are accepted.
The central executor owns approval, cancellation and idempotency for these flows.
"""
import hashlib
import os
from pathlib import Path, PureWindowsPath
import time

from . import windows_automation as windows


def validate_flow(kind, inputs):
    if kind == 'notepad_text':
        if set(inputs) != {'window_title', 'value'}:
            raise ValueError('Indica título exacto observado y texto literal.')
        if not isinstance(inputs['window_title'], str) or not 1 <= len(inputs['window_title']) <= 2048:
            raise ValueError('Título observado inválido.')
        value = inputs['value']
        if not isinstance(value, str) or len(value) > 8192 or '\x00' in value:
            raise ValueError('Texto inválido: máximo 8.192 caracteres sin NUL.')
        value.encode('utf-16-le')
    elif kind == 'explorer_folder':
        if set(inputs) != {'path'} or not isinstance(inputs['path'], str):
            raise ValueError('Indica una ruta de carpeta local.')
        path = inputs['path']; parsed = PureWindowsPath(path)
        if (not 1 <= len(path) <= 240 or not parsed.is_absolute() or len(parsed.drive) != 2
                or any(ord(c) < 32 or c in '*?"<>|' for c in path) or ':' in path[2:]
                or '..' in parsed.parts):
            raise ValueError('Usa una ruta absoluta local sin comodines, URI o dispositivos.')
    else:
        raise ValueError('Flujo no registrado.')


def execute_flow(kind, inputs, control):
    stages = []
    try:
        return _execute_flow(kind, inputs, control, stages)
    except Exception as exc:
        exc.partial_stages = list(stages)
        raise


def _execute_flow(kind, inputs, control, stages):
    validate_flow(kind, inputs)
    if control is None or control.is_set(): raise ValueError('Se requiere control local vigente.')
    if kind == 'explorer_folder':
        path = Path(inputs['path']).resolve(strict=True)
        if not path.is_dir(): raise ValueError('La carpeta ya no existe.')
        os.startfile(str(path))
        stages.append('open_requested')
        deadline = time.monotonic() + 5
        while True:
            result = windows._uia({'operation': 'locate_folder', 'path': str(path)}, cancelled=control)
            if len(result['windows']) == 1: break
            if len(result['windows']) > 1: raise ValueError('Varias ventanas muestran esta carpeta; selecciona una antes de continuar.')
            if time.monotonic() >= deadline: raise ValueError('No se observó la carpeta solicitada en Explorador.')
            if control.wait(.1): raise ValueError('Apertura cancelada por entrada local.')
        target = result['windows'][0]
        stages.append('folder_observed')
        windows.focus_window(target['window_id'], target['pid'], control)
        stages.append('focus_verified')
        check = windows._uia({'operation': 'locate_folder', 'path': str(path)}, cancelled=control)
        if not any(row['window_id'] == target['window_id'] and row['pid'] == target['pid'] for row in check['windows']):
            raise ValueError('La ubicación cambió antes de verificar.')
        if not any(row['window_id'] == target['window_id'] and row['pid'] == target['pid'] and row['foreground'] for row in windows.list_windows()):
            raise ValueError('El Explorador perdió el foco antes de verificar.')
        output = dict(target, path=str(path), foreground_verified=True, verification='shell_folder_and_foreground_readback')
    else:
        candidates = [row for row in windows.list_windows() if row['title'] == inputs['window_title']
                      and windows.process_name(row['pid']) == 'notepad.exe']
        if len(candidates) != 1: raise ValueError('No hay una única ventana de Notepad con ese título; vuelve a observar.')
        target = candidates[0]
        stages.append('window_resolved')
        windows.focus_window(target['window_id'], target['pid'], control)
        stages.append('focus_verified')
        observation = windows.inspect_controls(target['window_id'], target['pid'], cancelled=control)
        # Never select the search box, rename field or a hidden tab.
        editors = [row for row in observation['controls'] if row['control_type'] == 'ControlType.Document'
                   and row['supports_value_pattern'] and row['enabled'] and not row['offscreen']]
        if observation.get('truncated') or len(editors) != 1:
            raise ValueError('Notepad no expone un único editor completo con ValuePattern.')
        stages.append('editor_resolved')
        output = windows._uia({'operation': 'set_value', 'window_id': target['window_id'], 'pid': target['pid'],
                               'control_id': editors[0]['control_id'], 'value': inputs['value'],
                               'expected_title': inputs['window_title']}, cancelled=control)
        expected = hashlib.sha256(inputs['value'].encode('utf-8')).hexdigest()
        if output.get('value_sha256') != expected:
            raise windows.UncertainEffect('La escritura requiere reconciliación: SHA256 diferente.')
    stages.append('postcondition_verified')
    return {'success': True, 'output': output, 'evidence': {
        'accepted': True, 'verification': output['verification'], 'stages': stages,
        'window_id': target['window_id'], 'pid': target['pid'], 'input_source': 'axx_automation',
        **{k: output[k] for k in ('path', 'value_sha256', 'value_length') if k in output}}}
