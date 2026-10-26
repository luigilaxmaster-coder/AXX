"""Bounded, pure Python transformations interpreted as data, never CPython code.

There is deliberately no import, exec/eval, attribute traversal, external state,
or general Python object model. Every execution receives a private JSON copy.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
import threading
import time

LIMITS = {'source_bytes': 16000, 'ast_nodes': 600, 'ast_depth': 32,
          'steps': 12000, 'value_bytes': 64000, 'value_nodes': 3000,
          'value_depth': 16, 'container_items': 1000, 'string_chars': 16000,
          'number_absolute': 10 ** 12, 'tests': 32,
          'wall_seconds': 2.0, 'tests_wall_seconds': 10.0}
FUNCTIONS = {'len', 'str', 'int', 'float', 'round', 'abs', 'sum', 'min', 'max',
             'sorted', 'range', 'bool'}
METHODS = {'strip', 'lstrip', 'rstrip', 'lower', 'upper', 'title', 'capitalize',
           'replace', 'split', 'join', 'startswith', 'endswith', 'count'}
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')


def source_digest(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def checked_value(value):
    """Bound all objects before they enter or leave the interpreter."""
    pending = [(value, 0)]; nodes = 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        if nodes > LIMITS['value_nodes'] or depth > LIMITS['value_depth']:
            raise ValueError('El valor excede la complejidad permitida')
        if item is None or type(item) is bool: continue
        if type(item) in (int, float):
            if abs(item) > LIMITS['number_absolute'] or not math.isfinite(item):
                raise ValueError('Número no finito o fuera del presupuesto')
        elif type(item) is str:
            if len(item) > LIMITS['string_chars']: raise ValueError('Texto demasiado largo')
        elif type(item) in (list, dict):
            if len(item) > LIMITS['container_items']: raise ValueError('Colección demasiado grande')
            if type(item) is dict:
                if any(type(key) is not str for key in item): raise ValueError('Las claves deben ser texto')
                pending.extend((key, depth + 1) for key in item)
                pending.extend((part, depth + 1) for part in item.values())
            else: pending.extend((part, depth + 1) for part in item)
        else: raise ValueError('Solo se admiten valores JSON')
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > LIMITS['value_bytes']:
        raise ValueError('El valor excede el presupuesto de bytes')
    return value


def validate_schema(schema, *, input_schema=False):
    """Small, fully typed JSON schema subset; no references or executable regex."""
    checked_value(schema)
    def check(spec, depth):
        if type(spec) is not dict or depth > 8:
            raise ValueError('Esquema de transformación inválido')
        kind = spec.get('type')
        fields = {'type', 'description', 'enum'}
        if kind == 'object': fields |= {'properties', 'required', 'additionalProperties'}
        elif kind == 'array': fields |= {'items', 'minItems', 'maxItems'}
        elif kind == 'string': fields |= {'minLength', 'maxLength'}
        elif kind in ('number', 'integer'): fields |= {'minimum', 'maximum'}
        elif kind not in ('boolean', 'null'): raise ValueError('Todos los esquemas requieren un tipo JSON explícito')
        if set(spec) - fields: raise ValueError('Restricción de esquema no admitida')
        if 'description' in spec and (type(spec['description']) is not str or len(spec['description']) > 500):
            raise ValueError('Descripción de esquema inválida')
        if kind == 'object':
            props, required = spec.get('properties', {}), spec.get('required', [])
            if (type(props) is not dict or len(props) > 32 or type(required) is not list
                    or any(type(key) is not str or not NAME.fullmatch(key) for key in props)
                    or any(type(key) is not str or key not in props for key in required)
                    or len(required) != len(set(required)) or spec.get('additionalProperties', False) is not False):
                raise ValueError('Propiedades de esquema inválidas')
            spec.update(properties=props, required=required, additionalProperties=False)
            for sub in props.values(): check(sub, depth + 1)
        elif kind == 'array':
            if 'items' not in spec: raise ValueError('Los arrays requieren items tipados')
            check(spec['items'], depth + 1)
        for low, high, cap in [('minLength', 'maxLength', LIMITS['string_chars']),
                               ('minItems', 'maxItems', LIMITS['container_items'])]:
            for key in (low, high):
                if key in spec and (type(spec[key]) is not int or not 0 <= spec[key] <= cap):
                    raise ValueError('Límite de esquema inválido')
            if low in spec and high in spec and spec[low] > spec[high]: raise ValueError('Límites incompatibles')
        if any(key in spec and type(spec[key]) not in (int, float) for key in ('minimum', 'maximum')):
            raise ValueError('Límite numérico inválido')
        if 'minimum' in spec and 'maximum' in spec and spec['minimum'] > spec['maximum']:
            raise ValueError('Límites numéricos incompatibles')
        if 'enum' in spec:
            if type(spec['enum']) is not list or not 1 <= len(spec['enum']) <= 64:
                raise ValueError('Enum inválido')
            for value in spec['enum']: _arguments({key: val for key, val in spec.items() if key != 'enum'}, value)
    result = copy.deepcopy(schema)
    check(result, 0)
    if input_schema and result['type'] != 'object': raise ValueError('La entrada debe ser un objeto tipado')
    return result


def _arguments(schema, value):
    kind = schema['type']
    valid = {'object': type(value) is dict, 'array': type(value) is list,
             'string': type(value) is str, 'integer': type(value) is int,
             'number': type(value) in (int, float), 'boolean': type(value) is bool,
             'null': value is None}[kind]
    if not valid: raise ValueError('El valor no coincide con el tipo ' + kind)
    if 'enum' in schema and not any(type(value) is type(item) and value == item for item in schema['enum']):
        raise ValueError('El valor no coincide con las opciones')
    if kind == 'object':
        props = schema.get('properties', {})
        if set(value) - props.keys() or set(schema.get('required', [])) - value.keys():
            raise ValueError('Parámetros desconocidos o requeridos ausentes')
        for key, part in value.items(): _arguments(props[key], part)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', LIMITS['container_items']):
            raise ValueError('Longitud de colección incompatible')
        for part in value: _arguments(schema['items'], part)
    elif kind == 'string':
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', LIMITS['string_chars']):
            raise ValueError('Longitud de texto incompatible')
    elif kind in ('integer', 'number'):
        if not schema.get('minimum', -LIMITS['number_absolute']) <= value <= schema.get('maximum', LIMITS['number_absolute']):
            raise ValueError('Número fuera de los límites del esquema')


def validate_arguments(schema, arguments):
    checked_value(arguments)
    _arguments(validate_schema(schema), arguments)
    return copy.deepcopy(arguments)


def _json_equal(left, right):
    if type(left) in (int, float) and type(right) in (int, float): return left == right
    if type(left) is not type(right): return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_json_equal(value, right[key]) for key, value in left.items())
    if type(left) is list:
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def parse_source(source):
    if type(source) is not str or not source.strip() or len(source.encode('utf-8')) > LIMITS['source_bytes']:
        raise ValueError('Fuente de transformación inválida o excesiva')
    try: tree = ast.parse(source, mode='exec')
    except (SyntaxError, RecursionError, MemoryError, ValueError) as exc:
        raise ValueError('Sintaxis de transformación inválida') from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('La fuente debe contener únicamente def run(inputs)')
    function = tree.body[0]; args = function.args
    if (function.name != 'run' or function.decorator_list or function.returns or getattr(function, 'type_params', [])
            or args.posonlyargs or len(args.args) != 1 or args.args[0].arg != 'inputs'
            or args.args[0].annotation or args.defaults or args.kwonlyargs or args.vararg or args.kwarg):
        raise ValueError('La única firma admitida es def run(inputs)')
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.AugAssign,
               ast.Return, ast.If, ast.For, ast.Name, ast.Load, ast.Store, ast.Constant,
               ast.List, ast.Dict, ast.Subscript, ast.Slice, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.Attribute,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
               ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
               ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)
    pending = [(tree, 0)]; count = 0
    while pending:
        node, depth = pending.pop(); count += 1
        if count > LIMITS['ast_nodes'] or depth > LIMITS['ast_depth']:
            raise ValueError('La fuente excede la complejidad permitida')
        if not isinstance(node, allowed): raise ValueError('Instrucción Python no admitida: ' + type(node).__name__)
        if isinstance(node, ast.FunctionDef) and node is not function: raise ValueError('No se admiten funciones anidadas')
        if isinstance(node, ast.Name) and (not NAME.fullmatch(node.id) or node.id == 'run'):
            raise ValueError('Identificador no admitido')
        if isinstance(node, ast.Constant): checked_value(node.value)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1: raise ValueError('Solo se admite una variable por asignación')
            _target(node.targets[0])
        if isinstance(node, (ast.AugAssign, ast.For)): _target(node.target)
        if isinstance(node, ast.For) and node.orelse: raise ValueError('for else no admitido')
        if isinstance(node, ast.Dict) and any(key is None for key in node.keys): raise ValueError('No se admiten expansiones')
        if isinstance(node, ast.Call):
            if node.keywords: raise ValueError('No se admiten argumentos por nombre ni expansiones')
            if isinstance(node.func, ast.Name):
                if node.func.id not in FUNCTIONS: raise ValueError('Función no admitida')
            elif not isinstance(node.func, ast.Attribute) or node.func.attr not in METHODS:
                raise ValueError('Solo se admiten funciones puras y métodos de texto declarados')
        if isinstance(node, ast.Attribute):
            if node.attr not in METHODS: raise ValueError('Acceso a atributos no admitido')
            # An Attribute is never evaluated as a value. Calls handle it directly.
            if not any(isinstance(parent, ast.Call) and parent.func is node for parent in ast.walk(function)):
                raise ValueError('Los métodos no son valores ni permiten introspección')
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return function


def _target(node):
    if not isinstance(node, ast.Name) or node.id in FUNCTIONS | {'inputs', 'run'}:
        raise ValueError('Solo se asignan variables locales; la entrada es inmutable')


class _Returned(Exception):
    def __init__(self, value): self.value = value


class Interpreter:
    def __init__(self, source, cancelled=None, *, deadline=None):
        self.function = parse_source(source)
        self.cancelled = cancelled if cancelled is not None else threading.Event()
        self.steps = 0
        self.locals = {}
        self.outer_deadline = deadline
        self.deadline = None

    def tick(self):
        self.steps += 1
        if self.cancelled.is_set(): raise ValueError('Transformación cancelada')
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ValueError('Se agotó el presupuesto de tiempo de la transformación')
        if self.steps > LIMITS['steps']: raise ValueError('Se agotó el presupuesto de instrucciones')

    def run(self, inputs):
        self.deadline = time.monotonic() + LIMITS['wall_seconds']
        if self.outer_deadline is not None: self.deadline = min(self.deadline, self.outer_deadline)
        self.locals = {'inputs': copy.deepcopy(checked_value(inputs))}; self.steps = 0
        try: self.block(self.function.body)
        except _Returned as result:
            value = copy.deepcopy(checked_value(result.value))
            self.tick()
            return value
        raise ValueError('La transformación debe devolver un resultado')

    def block(self, statements):
        for node in statements:
            self.tick()
            if isinstance(node, ast.Return): raise _Returned(self.expr(node.value) if node.value else None)
            if isinstance(node, ast.Assign): self.locals[node.targets[0].id] = self.expr(node.value)
            elif isinstance(node, ast.AugAssign):
                self.locals[node.target.id] = self.binary(node.op, self.locals[node.target.id], self.expr(node.value))
            elif isinstance(node, ast.If): self.block(node.body if self.expr(node.test) else node.orelse)
            elif isinstance(node, ast.For):
                values = self.expr(node.iter)
                if type(values) not in (list, str, dict): raise ValueError('El bucle requiere una colección acotada')
                if len(values) > LIMITS['container_items']: raise ValueError('Bucle demasiado largo')
                for value in values:
                    self.tick(); self.locals[node.target.id] = value; self.block(node.body)

    def expr(self, node):
        self.tick()
        if isinstance(node, ast.Constant): value = node.value
        elif isinstance(node, ast.Name):
            if node.id not in self.locals: raise ValueError('Variable local desconocida: ' + node.id)
            value = self.locals[node.id]
        elif isinstance(node, ast.List): value = [self.expr(part) for part in node.elts]
        elif isinstance(node, ast.Dict): value = {self.expr(key): self.expr(part) for key, part in zip(node.keys, node.values)}
        elif isinstance(node, ast.Subscript):
            obj = self.expr(node.value)
            if type(obj) not in (list, str, dict): raise ValueError('Índice sobre un valor no admitido')
            index = node.slice
            if isinstance(index, ast.Slice):
                parts = [self.expr(part) if part is not None else None for part in (index.lower, index.upper, index.step)]
                if type(obj) is dict or any(part is not None and type(part) is not int for part in parts):
                    raise ValueError('Rango de índices inválido')
                value = obj[slice(*parts)]
            else:
                key = self.expr(index)
                if (type(obj) is dict and type(key) is not str) or (type(obj) is not dict and type(key) is not int):
                    raise ValueError('Tipo de índice inválido')
                value = obj[key]
        elif isinstance(node, ast.IfExp): value = self.expr(node.body if self.expr(node.test) else node.orelse)
        elif isinstance(node, ast.BinOp): value = self.binary(node.op, self.expr(node.left), self.expr(node.right))
        elif isinstance(node, ast.UnaryOp):
            part = self.expr(node.operand)
            if isinstance(node.op, ast.Not): value = not part
            else:
                if type(part) not in (int, float): raise ValueError('La operación requiere un número')
                value = -part if isinstance(node.op, ast.USub) else +part
        elif isinstance(node, ast.BoolOp):
            value = self.expr(node.values[0])
            for part in node.values[1:]:
                if (isinstance(node.op, ast.And) and not value) or (isinstance(node.op, ast.Or) and value): break
                value = self.expr(part)
        elif isinstance(node, ast.Compare):
            left = self.expr(node.left); value = True
            for op, part in zip(node.ops, node.comparators):
                right = self.expr(part)
                if isinstance(op, ast.Eq): good = left == right
                elif isinstance(op, ast.NotEq): good = left != right
                elif isinstance(op, ast.Lt): good = left < right
                elif isinstance(op, ast.LtE): good = left <= right
                elif isinstance(op, ast.Gt): good = left > right
                elif isinstance(op, ast.GtE): good = left >= right
                elif isinstance(op, ast.In): good = left in right
                elif isinstance(op, ast.NotIn): good = left not in right
                elif isinstance(op, ast.Is): good = left is right
                else: good = left is not right
                if not good: value = False; break
                left = right
        elif isinstance(node, ast.Call): value = self.call(node)
        else: raise ValueError('Expresión no admitida')
        return checked_value(value)

    def binary(self, op, left, right):
        numbers = type(left) in (int, float) and type(right) in (int, float)
        if isinstance(op, ast.Add):
            if not numbers and not (type(left) is type(right) and type(left) in (list, str)):
                raise ValueError('Suma incompatible')
            if type(left) in (str, list) and len(left) + len(right) > LIMITS['string_chars' if type(left) is str else 'container_items']:
                raise ValueError('Concatenación demasiado grande')
            value = left + right
        elif isinstance(op, ast.Mult) and not numbers:
            sequence, times = (left, right) if type(left) in (str, list) else (right, left)
            if type(sequence) not in (str, list) or type(times) is not int or abs(times) > LIMITS['container_items']:
                raise ValueError('Repetición inválida')
            if len(sequence) * max(0, times) > LIMITS['string_chars' if type(sequence) is str else 'container_items']:
                raise ValueError('Repetición demasiado grande')
            value = sequence * times
        else:
            if not numbers: raise ValueError('La operación requiere números')
            if isinstance(op, ast.Sub): value = left - right
            elif isinstance(op, ast.Mult): value = left * right
            elif isinstance(op, ast.Div): value = left / right
            elif isinstance(op, ast.FloorDiv): value = left // right
            elif isinstance(op, ast.Mod): value = left % right
            else: raise ValueError('Operación no admitida')
        return checked_value(value)

    def call(self, node):
        args = [self.expr(part) for part in node.args]
        if isinstance(node.func, ast.Attribute):
            obj = self.expr(node.func.value); name = node.func.attr
            if type(obj) is not str: raise ValueError('Solo se admiten métodos sobre texto')
            if name == 'replace' and len(args) in (2, 3) and all(type(value) is str for value in args[:2]):
                if len(args) == 3 and type(args[2]) is not int: raise ValueError('El límite de reemplazos debe ser entero')
                occurrences = obj.count(args[0])
                count = occurrences if len(args) == 2 or args[2] < 0 else min(occurrences, args[2])
                if len(obj) + count * len(args[1]) > LIMITS['string_chars']: raise ValueError('Reemplazo demasiado grande')
            if name == 'join':
                if len(args) != 1 or type(args[0]) is not list or any(type(item) is not str for item in args[0]):
                    raise ValueError('join requiere una lista de textos')
                if sum(len(item) for item in args[0]) + len(obj) * max(0, len(args[0]) - 1) > LIMITS['string_chars']:
                    raise ValueError('Texto unido demasiado grande')
            # getattr only uses the closed whitelist above, on an exact built-in str.
            return checked_value(getattr(obj, name)(*args))
        name = node.func.id
        if name == 'range':
            if not 1 <= len(args) <= 3 or any(type(arg) is not int for arg in args): raise ValueError('range requiere enteros')
            values = range(*args)
            if len(values) > LIMITS['container_items']: raise ValueError('range demasiado grande')
            return list(values)
        if name in ('int', 'float') and args and type(args[0]) is str and len(args[0]) > 64:
            raise ValueError('Conversión numérica demasiado larga')
        if name == 'round' and len(args) == 2 and (type(args[1]) is not int or abs(args[1]) > 16):
            raise ValueError('Precisión fuera del presupuesto')
        pure = {'len': len, 'str': str, 'int': int, 'float': float, 'round': round,
                'abs': abs, 'sum': sum, 'min': min, 'max': max, 'sorted': sorted, 'bool': bool}
        return checked_value(pure[name](*args))


def run_transform(source, inputs, input_schema, output_schema, cancelled=None, *, deadline=None):
    inputs = validate_arguments(input_schema, inputs)
    result = Interpreter(source, cancelled, deadline=deadline).run(inputs)
    validate_arguments(output_schema, result)
    return result


def validate_definition(definition):
    parse_source(definition['source'])
    schema = validate_schema(definition['schema'], input_schema=True)
    output = validate_schema(definition['output_schema'])
    tests = definition['tests']
    if type(tests) is not list or not 1 <= len(tests) <= LIMITS['tests']:
        raise ValueError('La transformación requiere entre uno y 32 casos de prueba')
    for test in tests:
        if type(test) is not dict or set(test) != {'inputs', 'expected'}: raise ValueError('Caso de prueba inválido')
        validate_arguments(schema, test['inputs']); validate_arguments(output, test['expected'])
    return schema, output


def run_tests(definition, cancelled=None):
    deadline = time.monotonic() + LIMITS['tests_wall_seconds']
    schema, output_schema = validate_definition(definition)
    results = []
    for index, test in enumerate(definition['tests']):
        reason = ('Prueba no ejecutada: transformación cancelada' if cancelled is not None and cancelled.is_set()
                  else 'Prueba no ejecutada: se agotó el presupuesto de tiempo de las pruebas' if time.monotonic() >= deadline else None)
        if reason:
            results.extend({'index': remaining, 'passed': False, 'executed': False, 'error': reason}
                           for remaining in range(index, len(definition['tests'])))
            break
        try:
            actual = run_transform(definition['source'], test['inputs'], schema, output_schema, cancelled, deadline=deadline)
            if time.monotonic() >= deadline: raise ValueError('Se agotó el presupuesto de tiempo de las pruebas')
            # JSON numbers preserve their value across editor/HTTP serialization;
            # booleans remain distinct from numbers, including nested values.
            passed = _json_equal(actual, test['expected'])
            results.append({'index': index, 'passed': passed, 'executed': True, 'actual': actual,
                            'error': None if passed else 'El resultado difiere del esperado'})
        except Exception as exc:
            results.append({'index': index, 'passed': False, 'executed': True, 'error': str(exc)[:300]})
    return {'self_tests_passed': len(results) == len(definition['tests']) and all(row['passed'] for row in results),
            'tests': results, 'source_digest': source_digest(definition['source'])}


class GeneratedTool:
    """An approved immutable revision; CommandService owns admission/revocation."""
    def __init__(self, record):
        self.record = copy.deepcopy(record)
        self.name = record['command_id']; self.version = str(record['revision'])
        self.description = record['description']
        self.parameter_names = set(record['input_schema']['properties'])
        if not re.fullmatch(r'axx\.generated\.[a-f0-9]{32}\.r[1-9][0-9]*\.[a-f0-9]{16}', self.name):
            raise ValueError('Identificador de transformación inválido')
        if source_digest(record['source']) != record['source_digest']: raise ValueError('La fuente cambió')
        parse_source(record['source'])
        validate_schema(record['input_schema'], input_schema=True); validate_schema(record['output_schema'])

    def verify_preconditions(self, inputs):
        try:
            validate_arguments(self.record['input_schema'], inputs)
            if source_digest(self.record['source']) != self.record['source_digest']: raise ValueError('La fuente cambió')
            return True, 'Transformación pura, contrato y fuente revisada comprobados'
        except Exception as exc: return False, str(exc)[:300]

    def execute_admitted(self, inputs, workspace_root, cancelled, runtime, operation_id):
        from .actions.tools import ToolResult
        try:
            ok, message = self.verify_preconditions(inputs)
            if not ok: raise ValueError(message)
            if runtime.dynamic_tools.get(self.name) is not self:
                raise ValueError('La transformación fue revocada o sustituida antes de ejecutar')
            result = run_transform(self.record['source'], inputs, self.record['input_schema'], self.record['output_schema'], cancelled)
            return ToolResult(True, output={'result': result, 'digest': self.record['digest'],
                                           'source_digest': self.record['source_digest']},
                              evidence={'verification': 'bounded_python_transform', 'effect_verified': True,
                                        'external_effects': False, 'digest': self.record['digest']})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:500], evidence={'effect_uncertain': False, 'cancelled': cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        try:
            if (not result.success or result.evidence.get('verification') != 'bounded_python_transform'
                    or result.output.get('digest') != self.record['digest']
                    or result.output.get('source_digest') != self.record['source_digest']): return False, 'Resultado de transformación no verificado'
            validate_arguments(self.record['output_schema'], result.output['result'])
            return True, 'Resultado puro calculado y validado contra su esquema'
        except Exception as exc: return False, str(exc)[:300]
