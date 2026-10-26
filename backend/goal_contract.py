"""Durable outcome contracts; candidate code cannot rewrite the evaluator."""
import hashlib
from pathlib import Path, PureWindowsPath

from .memory.skill_memory import bounded_object


def contract(request, value=None):
    defaults={'intent':request,'objects':[],'sources':[], 'destination':'',
        'filters':{},'parameters':{},'preserve':[],'checks':[]}
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
    return result


def verify(goal, root, cancelled):
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
    return {'passed':all(row['passed'] for row in results),'checks':results,
            'coverage':'artifact_content' if results else 'executor_postconditions'}
