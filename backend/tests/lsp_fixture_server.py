"""Controlled stdio language server for tests: real LSP framing and JSON-RPC, deterministic answers.

Lines containing BAD_TOKEN get an error diagnostic; completion returns one fixed item. After `initialized` it asks
the client for workspace/configuration and only publishes once the client has answered.
"""
import json
import sys

out = sys.stdout.buffer


def send(message):
    data = json.dumps({'jsonrpc': '2.0', **message}).encode('utf-8')
    out.write(b'Content-Length: %d\r\n\r\n' % len(data) + data)
    out.flush()


def read():
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b'\r\n', b'\n'):
            break
        if line.lower().startswith(b'content-length:'):
            length = int(line.split(b':', 1)[1])
    return json.loads(sys.stdin.buffer.read(length))


def publish(uri, text):
    send({'method': 'textDocument/publishDiagnostics', 'params': {'uri': uri, 'diagnostics': [
        {'range': {'start': {'line': n, 'character': 0}, 'end': {'line': n, 'character': len(line)}},
         'severity': 1, 'source': 'fixture-lsp', 'message': 'BAD_TOKEN no permitido'}
        for n, line in enumerate(text.splitlines()) if 'BAD_TOKEN' in line]}})


configured, docs = False, {}
while (msg := read()) is not None:
    method = msg.get('method')
    if method == 'initialize':
        send({'id': msg['id'], 'result': {'capabilities': {'textDocumentSync': 1, 'completionProvider': {'triggerCharacters': ['.']}}}})
    elif method == 'initialized':
        send({'id': 'cfg-1', 'method': 'workspace/configuration', 'params': {'items': [{'section': 'fixture'}]}})
    elif 'id' in msg and 'method' not in msg and msg['id'] == 'cfg-1':
        configured = msg.get('result') == [None]
        for uri, text in docs.items():  # like real servers, re-publish once configuration arrives
            publish(uri, text)
    elif method == 'textDocument/didOpen':
        docs[msg['params']['textDocument']['uri']] = msg['params']['textDocument']['text']
        publish(msg['params']['textDocument']['uri'], msg['params']['textDocument']['text'] if configured else '')
    elif method == 'textDocument/didChange':
        docs[msg['params']['textDocument']['uri']] = msg['params']['contentChanges'][-1]['text']
        publish(msg['params']['textDocument']['uri'], msg['params']['contentChanges'][-1]['text'] if configured else '')
    elif method == 'textDocument/completion':
        send({'id': msg['id'], 'result': {'isIncomplete': False, 'items': [{'label': 'axx_fixture_item', 'kind': 3, 'detail': 'fixture'}]}})
    elif method == 'shutdown':
        send({'id': msg['id'], 'result': None})
    elif method == 'exit':
        break
