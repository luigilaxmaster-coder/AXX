"""Expose a bounded subset of the existing registry to the selected chat connection."""
import hashlib
import time

from backend.commands import ADAPTERS, parse_command_json
from backend.connect.registry import legacy_schema, validate


GUIDANCE = ('Axx ofrece herramientas estructuradas. Para consultar el estado del equipo (CPU, memoria, sistema) llama a '
            'axx_system_telemetry con arguments {} mediante la llamada de herramienta. No escribas esquemas JSON, no describas '
            'llamadas en texto y no inventes valores: solo un resultado verificado por Axx cuenta como ejecutado.')


SCHEMA_ECHO_KEYS = frozenset({'type', 'properties', 'required', 'additionalProperties', 'title', 'description', '$schema'})


def operation_id(request_id):
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ValueError('Falta la identidad de la solicitud de herramientas')
    return 'chat-tool-' + hashlib.sha256(request_id.encode()).hexdigest()


def catalog(commands, config, envelope):
    if envelope.get('selection_mode', 'manual') != 'manual':
        return None, {}
    selected = [p for p in config.get('providers', [])
                if p.get('enabled') is True and not p.get('candidate_only')
                and p.get('model') == envelope.get('model')
                and (not envelope.get('provider_name') or p['name'] == envelope['provider_name'])]
    if len(selected) != 1 or 'tools' not in selected[0].get('capabilities', []):
        return None, {}
    tools = {}
    for key in ('axx.system.telemetry', 'axx.architecture.status', 'axx.artifact.write'):
        if commands.commands[key]['execution_enabled']:
            adapter = ADAPTERS[key]
            name = key.replace('.', '_')
            description = adapter['title'] + ('' if adapter['parameters'] else '. Sin argumentos: arguments es {}.')
            tools[name] = (key, {'name': name, 'description': description,
                                 'parameters': legacy_schema(adapter['parameters'])})
    return selected[0]['name'], tools


def dispatch(connect, calls, tools, request_id, policy):
    try:
        if not isinstance(calls, list) or len(calls) != 1 or calls[0].get('type') != 'function':
            raise ValueError('Se admite una herramienta estructurada por turno')
        function = calls[0]['function']
        command_id, descriptor = tools[function['name']]
        raw = function['arguments']
        if not isinstance(raw, str) or len(raw.encode()) > 131072:
            raise ValueError('Argumentos fuera de límite')
        inputs = parse_command_json(raw)
        if not isinstance(inputs, dict):
            raise ValueError('Los argumentos deben ser un objeto')
        # Small models echo the JSON schema as the arguments of a parameterless tool. That exact shape (only JSON-schema
        # keywords) is dropped; any other key (e.g. approved/channel/origin) is still rejected by validation below,
        # and tools WITH parameters keep full schema validation.
        if inputs and not descriptor['parameters'].get('properties') and set(inputs) <= SCHEMA_ECHO_KEYS:
            inputs = {}
        validate(descriptor['parameters'], inputs)
        receipt = connect.execute({
            'command_id': command_id, 'inputs': inputs, 'operation_id': operation_id(request_id),
            'origin': 'axx-provider', 'parent_execution_id': request_id, 'delegation_depth': 1,
        }, chat_policy=policy)
        # Telemetry now samples the CPU (~0.3 s); under load 2 s returned a 'running' receipt for an op that then succeeded.
        deadline = time.monotonic() + 8
        while receipt['state'] in ('prepared', 'running') and time.monotonic() < deadline:
            time.sleep(.05)
            receipt = connect.get_task(receipt['operation_id'])
        return receipt
    except (ValueError, KeyError, AttributeError, TypeError, RecursionError):
        return {'state': 'blocked', 'postconditions_passed': False, 'error': {
            'code': 'TOOL_REJECTED', 'message': 'La herramienta no se admitió. Revisa esquema, alcance o estado de la conversación.'}}
