"""Disposable real SQLite/HTTP fixture used by the chat browser integration check."""
import json
import tempfile
from pathlib import Path
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.actions.executor import ActionExecutor
from backend.server import AxxBridgeHandler, ThreadedHTTPServer

with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'state.db'
    chats=ChatStore(path);executor=ActionExecutor(path,Path(directory)/'artifacts');commands=CommandService(executor)
    handler=type('ChatHandler',(AxxBridgeHandler,),{'chats':chats,'commands':commands,'executor':executor})
    server=ThreadedHTTPServer(('127.0.0.1',0),handler)
    print(json.dumps({'port':server.server_port,'token':server.host_token}),flush=True)
    try:server.serve_forever()
    finally:server.server_close();chats.close();commands.close();executor.close()
