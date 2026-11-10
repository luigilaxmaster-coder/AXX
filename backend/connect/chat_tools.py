
"""Expose a bounded subset of the existing registry to the selected chat connection."""
import hashlib
import time

from backend.commands import ADAPTERS, parse_command_json
from backend.connect.registry import legacy_schema, validate


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
    for key, adapter in ADAPTERS.items():
        if (adapter['risk'] == 'read' or key == 'axx.artifact.write') and commands.commands[key]['execution_enabled']:
            name = key.replace('.', '_')
            tools[name] = (key, {'name': name, 'description': adapter['title'],
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
        validate(descriptor['parameters'], inputs)
        receipt = connect.execute({
            'command_id': command_id, 'inputs': inputs, 'operation_id': operation_id(request_id),
            'origin': 'axx-provider', 'parent_execution_id': request_id, 'delegation_depth': 1,
        }, chat_policy=policy)
        deadline = time.monotonic() + 2
        while receipt['state'] in ('prepared', 'running') and time.monotonic() < deadline:
            time.sleep(.05)
            receipt = connect.get_task(receipt['operation_id'])
        return receipt
    except (ValueError, KeyError, AttributeError, TypeError, RecursionError):
        return {'state': 'blocked', 'postconditions_passed': False, 'error': {
            'code': 'TOOL_REJECTED', 'message': 'La herramienta no se admitió. Revisa esquema, alcance o estado de la conversación.'}}

