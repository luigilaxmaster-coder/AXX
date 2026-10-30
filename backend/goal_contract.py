"""Durable outcome contracts; candidate code cannot rewrite the evaluator."""
import hashlib
from pathlib import Path, PureWindowsPath

from .memory.skill_memory import bounded_object
from .actions.file_inspection import MAX_BYTES
from .goal_criteria import criteria_catalog, evaluate_criteria, propose_goal_step, assert_input_versions, input_version_lease, validate_criteria


def contract(request, value=None):
    defaults={'intent':request,'objects':[],'sources':[], 'destination':'',
        'filters':{},'parameters':{},'preserve':[],'checks':[], 'criteria':[]}
    supplied=bounded_object(defaults if value is None else value,16000)
    if 'intent' not in supplied or set(supplied)-set(defaults):
        raise ValueError('Contrato de objetivo incompleto o con campos desconocidos')
    result=defaults|supplied
    if not isinstance(result['intent'],str) or not 1 <= len(result['intent']) <= 4000:
        raise ValueError('Intención de objetivo inválida')
    if not isinstance(result['destination'],str) or len(result['destination']) > 2048:
        raise ValueError('Destino de objetivo inválido')
    for key in ('objects','sources','preserve','checks'):
        if not isinstance(result[key],list) or len(result[key]) > 32: raise ValueError('Lista de objetivo inválida')
    for key in ('filters','parameters'):
        bounded_object(result[key],8000)
    if any(not isinstance(row,str) or len(row)>1000 for row in result['preserve']):
        raise ValueError('Condición de conservación inválida')
    for check in result['checks']:
        if not isinstance(check,dict) or set(check) != {'path','text'}:
            raise ValueError('La comprobación final requiere path relativo y text esperado')
        raw = check['path']
        if (not isinstance(raw,str) or not raw or len(raw)>180 or PureWindowsPath(raw).is_absolute()
                or PureWindowsPath(raw).drive or PureWindowsPath(raw).root or any(part in ('..','.') for part in raw.replace('\\','/').split('/'))):
            raise ValueError('La comprobación debe permanecer dentro de artifacts')
        if not isinstance(check['text'],str) or len(check['text']) > 8000:
            raise ValueError('Contenido esperado inválido')
    result['criteria'] = validate_criteria(result['criteria'], result['checks'])
    bounded_object(result,16000)
    return result


def validate_steps(goal, steps, root):
    root = Path(root).resolve()
    declared = {(root / value).resolve() for step in steps for key,value in step['inputs'].items()
                if key in ('path','destination') and isinstance(value,str)}
    for check in goal['checks']:
        target = (root / check['path']).resolve()
        if target not in declared and not target.is_file():
            raise ValueError('La comprobación final debe referirse a una ruta de archivo declarada en los pasos o ya existente en artifacts; no a un campo de respuesta como output.')
        for step in steps:
            if (step['command_id'] == 'axx.artifact.write' and isinstance(step['inputs'].get('path'),str)
                    and (root / step['inputs']['path']).resolve() == target and 'content' in step['inputs']
                    and step['inputs']['content'] != check['text']):
                raise ValueError('El texto de la comprobación final no coincide con el contenido literal que se guardará. Conserva el contenido solicitado.')


def verify(goal, root, cancelled, *, max_file_bytes=MAX_BYTES):
    from .actions.file_inspection import hash_file
    root = Path(root).resolve()
    results = []
    for check in goal['checks']:
        path = (root / check['path']).resolve()
        try:
            if not path.is_relative_to(root): raise ValueError('El archivo sale de artifacts')
            observed = hash_file(str(path), cancelled)
            expected = hashlib.sha256(check['text'].encode('utf-8')).hexdigest()
            results.append({'path':check['path'],'passed':observed['sha256']==expected,'sha256':observed['sha256']})
        except (ValueError,OSError) as exc:
            results.append({'path':check['path'],'passed':False,'error':str(exc)[:300]})
    report = {'passed':all(row['passed'] for row in results),'checks':results,
              'coverage':'artifact_content' if results else 'executor_postconditions'}
    if goal.get('criteria'):
        criteria = evaluate_criteria(goal, root, cancelled, max_file_bytes=max_file_bytes)
        report.update(criteria=criteria, passed=report['passed'] and all(row['status']=='satisfied' for row in criteria),
                      coverage='typed_outcomes')
    return report
