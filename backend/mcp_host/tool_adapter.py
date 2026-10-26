"""An admitted remote call is a tool body, never another action executor."""
import threading

from .catalog import validate_arguments


class McpTool:
    version = '1.0.0'

    def __init__(self, host, record):
        self.host, self.record = host, record
        self.name = record['id']
        self.description = record['description']
        self.parameter_names = set(record['input_schema'].get('properties', {}))

    def verify_preconditions(self, inputs):
        try:
            self.host.validate(self.record['id'], inputs)
            return True, 'Conexión, revisión de esquema y activación comprobadas'
        except Exception as exc:
            return False, str(exc)[:300]

    def execute_admitted(self, inputs, workspace_root, cancelled, runtime, operation_id):
        from backend.actions.tools import ToolResult
        try:
            result, record = self.host.call(self.record['id'], inputs, cancelled, operation_id)
            structured = result.get('structuredContent')
            if record['output_schema'] is not None:
                validate_arguments(record['output_schema'], structured)
            output = {'server': record['connection_id'], 'tool': record['name'],
                      'schema_digest': record['schema_digest'], 'result': result}
            if result.get('isError'):
                return ToolResult(False, output=output, error='El servidor MCP informó un error; revisa posibles efectos',
                    evidence={'effect_uncertain': not record['read_only'], 'verification': 'remote_error'})
            if not record['read_only']:
                return ToolResult(False, output=output, error='Llamada MCP entregada; falta comprobar el efecto en la aplicación',
                    evidence={'effect_uncertain': True, 'dispatch_status': 'delivered', 'verification': 'remote_acknowledgement_only'})
            return ToolResult(True, output=output, evidence={'verification':'mcp_read_response',
                'scope':'response_from_configured_server; content_not_independently_verified', 'untrusted_content':True})
        except Exception as exc:
            # Once transport work starts a lost response cannot establish absence of effects.
            return ToolResult(False, error=str(exc)[:500], evidence={'effect_uncertain': not self.record['read_only'], 'cancelled':cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        return bool(result.success and result.evidence.get('verification') == 'mcp_read_response'), 'Respuesta de lectura MCP recibida'
