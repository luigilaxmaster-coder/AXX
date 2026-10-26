"""Bounded references to verified earlier receipts, never executable expressions."""
import copy
import json


def validate_bindings(step, index):
    bindings = step.get('bindings', {})
    if not isinstance(bindings, dict) or len(bindings) > 16:
        raise ValueError('Vínculos de pasos inválidos')
    if bindings and (step['command_id'].startswith('axx.shell.') or step['command_id'] == 'axx.process.run'):
        raise ValueError('Los resultados observados no pueden convertirse en código shell')
    for name, ref in bindings.items():
        if not isinstance(name, str) or name in step['inputs']:
            raise ValueError('Un parámetro no puede ser literal y vinculado a la vez')
        if not isinstance(ref, dict) or set(ref) != {'step', 'path'}:
            raise ValueError('Cada vínculo requiere step y path')
        if type(ref['step']) is not int or not 0 <= ref['step'] < index:
            raise ValueError('Un vínculo sólo puede leer un paso anterior')
        path = ref['path']
        if (not isinstance(path, list) or not 2 <= len(path) <= 8 or path[0] != 'output'
                or any(not (isinstance(p, str) and 1 <= len(p) <= 128 and not p.startswith('__')
                            or type(p) is int and 0 <= p < 200) for p in path)):
            raise ValueError('Ruta de resultado inválida')
    return bindings


def resolve_inputs(step, records):
    inputs = copy.deepcopy(step['inputs'])
    for name, ref in step.get('bindings', {}).items():
        receipt = records[ref['step']].get('result') or {}
        if receipt.get('state') != 'succeeded' or receipt.get('postconditions_passed') is not True:
            raise ValueError('El paso de origen aún no tiene un resultado verificado')
        if any(isinstance(receipt.get(key), dict) and receipt[key].get('truncated') for key in ('output', 'evidence')):
            raise ValueError('La observación está truncada; reduce el alcance antes de usarla para otra acción')
        value = receipt
        try:
            for segment in ref['path']:
                if type(segment) is int and not isinstance(value, list): raise TypeError()
                if isinstance(segment, str) and not isinstance(value, dict): raise TypeError()
                value = value[segment]
        except (KeyError, IndexError, TypeError):
            raise ValueError('El resultado no contiene el parámetro solicitado') from None
        inputs[name] = copy.deepcopy(value)
    if len(json.dumps(inputs, ensure_ascii=False, allow_nan=False).encode()) > 65536:
        raise ValueError('Los parámetros resueltos exceden el límite de 64 KiB')
    return inputs
