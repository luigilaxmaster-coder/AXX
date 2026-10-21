"""Exercise the frozen backend against a loopback fixture, never a paid service."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

binary = Path(sys.argv[1]).resolve(strict=True)
output = Path(sys.argv[2])
workspace = Path(tempfile.mkdtemp(prefix='axx-providers-check-'))
calls = []
class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"models":[{"name":"packaged-fixture"}]}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append(body['model'])
        self.send_response(200); self.end_headers()
        self.wfile.write(b'{"choices":[{"message":{"role":"assistant","content":"Native fixture response"},"finish_reason":"stop"}]}')
fixture = HTTPServer(('127.0.0.1', 0), Fixture)
threading.Thread(target=fixture.serve_forever, daemon=True).start()
config = workspace / 'providers.json'
config.write_text('{"allow_paid":false,"providers":[]}')
ready = workspace / 'ready.json'
token = secrets.token_hex(32)
env = dict(os.environ, AXX_HOST_TOKEN=token)
log = (workspace/'backend.log').open('ab')
process = subprocess.Popen([str(binary), '--port', '0', '--data-dir', str(workspace), '--ready-file', str(ready)],
    env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    deadline = time.monotonic() + 60
    while not ready.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise AssertionError('Packaged backend did not start; ' + str(workspace/'backend.log'))
        time.sleep(.2)
    base = 'http://127.0.0.1:' + str(json.loads(ready.read_text())['port'])
    def request(path, body=None):
        req = urllib.request.Request(base + '/axx-api/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer '+token, 'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=75) as response: return json.load(response)
    data = dict(provider='ollama', name='Packaged check', model='packaged-fixture',
                base_url=f'http://127.0.0.1:{fixture.server_port}/v1', api_key='FIXTURE-ONLY-KEY')
    assert request('providers/discover', data)['models'] == ['packaged-fixture']
    assert request('providers/save', data)['ok']
    entries = request('providers')['providers']
    assert entries[-1]['has_key'] is True and 'api_key' not in entries[-1]
    reply = request('chat', {'model':'packaged-fixture','messages':[{'role':'user','content':'test'}]})
    assert reply['choices'][0]['message']['content'] == 'Native fixture response'
    assert calls == ['packaged-fixture']
    assert b'FIXTURE-ONLY-KEY' not in next((workspace/'credentials').glob('*.bin')).read_bytes()
    report = {'binary': str(binary), 'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
              'passed':['frozen startup', 'model discovery over HTTP', 'connection save', 'DPAPI credential encryption',
                        'redacted provider listing', 'selected model inference through frozen worker'],
              'external_provider_inference':False}
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
finally:
    subprocess.run(['taskkill','/F','/T','/PID',str(process.pid)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    process.wait(timeout=10); log.close(); fixture.shutdown();fixture.server_close()
