"""Disposable real HTTP fixture; deterministic proposal model, real command executor."""
import json
import tempfile
from pathlib import Path
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning
from backend.capability_workshop import CapabilityWorkshop
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class ProposalModel:
    def route(self, request):
        definition = {'kind': 'workflow', 'title': 'Estado del equipo', 'objective': 'Consultar métricas locales',
            'schema': {'type': 'object', 'properties': {}, 'required': []},
            'templates': [{'command_id': 'axx.system.telemetry', 'inputs': {}}], 'sample_inputs': {}}
        return {'ok': True, 'message': {'content': json.dumps(definition)}}


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    executor = ActionExecutor(path / 'state.db', path / 'artifacts')
    commands = CommandService(executor)
    learning = ActionLearning(commands, ProposalModel()); commands.learning = learning
    workshop = CapabilityWorkshop(learning)
    handler = type('WorkshopFixture', (AxxBridgeHandler,), {'workshop': workshop, 'commands': commands, 'learning': learning})
    server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
    print(json.dumps({'port': server.server_port, 'token': server.host_token}), flush=True)
    try: server.serve_forever()
    finally:
        server.server_close(); workshop.close(); learning.close(); commands.close(); executor.close()
