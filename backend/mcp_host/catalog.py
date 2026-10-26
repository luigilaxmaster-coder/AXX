"""Validate remote schemas as data; annotations never grant execution permissions."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def checked_schema(schema):
    from jsonschema import Draft202012Validator
    if not isinstance(schema, dict) or len(json.dumps(schema, allow_nan=False)) > 32768:
        raise ValueError('Esquema MCP inválido o excesivo')
    nodes = [(schema, 0)]; count = 0
    while nodes:
        value, depth = nodes.pop(); count += 1
        if count > 2000 or depth > 16: raise ValueError('Esquema MCP demasiado complejo')
        if isinstance(value, dict):
            # No remote references or recursive schemas at the execution boundary.
            if any(key in value for key in ('$ref', '$dynamicRef', '$recursiveRef')):
                raise ValueError('El catálogo no admite referencias de esquema; usa un esquema autocontenido')
            if any(key in value for key in ('pattern', 'patternProperties')):
                raise ValueError('El catálogo no ejecuta expresiones regulares suministradas por servidores')
            nodes.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list): nodes.extend((item, depth + 1) for item in value)
    Draft202012Validator.check_schema(schema)
    return schema


def tool_record(connection_id, revision, row):
    if not isinstance(row, dict): raise ValueError('Descriptor MCP inválido')
    name = row.get('name')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name):
        raise ValueError('Nombre de herramienta MCP inválido')
    schema = checked_schema(row.get('inputSchema'))
    if schema.get('type') != 'object': raise ValueError('La herramienta debe recibir un objeto tipado')
    if len(schema.get('properties', {})) > 32:
        raise ValueError('La herramienta supera 32 parámetros')
    if any(not isinstance(spec, dict) for spec in schema.get('properties', {}).values()):
        raise ValueError('Los parámetros MCP requieren esquemas tipados')
    output_schema = checked_schema(row['outputSchema']) if row.get('outputSchema') is not None else None
    schema_digest = digest({'input': schema, 'output': output_schema})
    key = 'axx.mcp.' + connection_id + '.' + digest([revision, name, schema_digest])[:20]
    return {'id': key, 'name': name, 'title': str(row.get('title') or name)[:200],
            'description': str(row.get('description') or '')[:1000], 'input_schema': schema,
            'output_schema': output_schema, 'schema_digest': schema_digest, 'revision': revision,
            'connection_id': connection_id, 'enabled': False, 'read_only': False}


def validate_arguments(schema, arguments):
    from jsonschema import Draft202012Validator
    if not isinstance(arguments, dict) or len(json.dumps(arguments, allow_nan=False)) > 65536:
        raise ValueError('Argumentos MCP inválidos o excesivos')
    error = next(Draft202012Validator(schema).iter_errors(arguments), None)
    if error: raise ValueError('Argumentos incompatibles con el esquema MCP: ' + error.validator)
