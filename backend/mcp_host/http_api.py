"""MCP connection management behind the existing private backend authentication."""
class McpHTTP:
    def __init__(self, handler):
        self.h = handler
        self.host = getattr(handler, 'mcp_host', None)

    def get(self, path):
        if path != '/axx-api/mcp/connections': return False
        if not self.host: raise ValueError('Host MCP no disponible')
        self.h._send_json(200, self.host.list())
        return True

    def post(self, path, body):
        if not path.startswith('/axx-api/mcp/'): return False
        if not self.host: raise ValueError('Host MCP no disponible')
        operation = path.rsplit('/', 1)[-1]
        if operation == 'add': result = self.host.add(body)
        elif operation in ('probe', 'disconnect') and set(body) == {'id'}:
            result = getattr(self.host, operation)(body['id'])
        elif operation == 'activate' and set(body) == {'tool_id', 'enabled', 'read_only'}:
            result = self.host.activate(body['tool_id'], body['enabled'], body['read_only'])
        else: raise ValueError('Operación de configuración MCP inválida')
        self.h._send_json(200, result)
        return True
