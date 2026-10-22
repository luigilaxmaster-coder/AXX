"""Smoke the frozen local backend with a real PNG conversion."""
import base64
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.request

from PIL import Image
from pypdf import PdfReader, PdfWriter
import psutil


root = Path(__file__).resolve().parents[1]
binary = root / 'dist' / 'axx-backend.exe'
assert binary.is_file(), binary
with tempfile.TemporaryDirectory(prefix='axx-converter-smoke-') as directory:
    folder = Path(directory)
    ready = folder / 'ready.json'
    token = secrets.token_hex(32)
    env = {**os.environ, 'AXX_HOST_TOKEN': token, 'AXX_HOST_INSTANCE': secrets.token_hex(16)}
    with (folder / 'backend.log').open('wb') as log:
        process = subprocess.Popen([str(binary), '--port', '0', '--data-dir', str(folder), '--ready-file', str(ready)],
                                   env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(200):
                if ready.exists():
                    break
                if process.poll() is not None:
                    raise RuntimeError('Frozen backend exited during startup')
                time.sleep(.1)
            else:
                raise RuntimeError('Frozen backend did not become ready')
            port = json.loads(ready.read_text(encoding='utf-8'))['port']

            def post(action, body):
                request = urllib.request.Request(f'http://127.0.0.1:{port}/axx-api/converter/{action}',
                    data=json.dumps(body).encode(), method='POST',
                    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.load(response)

            image = io.BytesIO()
            Image.new('RGBA', (2, 2), (255, 0, 0, 0)).save(image, format='PNG')
            source = image.getvalue()
            job = post('new', {'files': [{'name': 'test.png', 'size': len(source)}]})
            post('upload', {'id': job['id'], 'index': 0, 'offset': 0, 'data': base64.b64encode(source).decode()})
            inspected = post('probe', {'id': job['id']})
            assert inspected['info'][0]['kind'] == 'png'
            post('run', {'id': job['id'], 'operation': 'png-jpeg', 'options': {'background': '#ffffff', 'quality': 90}})
            for _ in range(100):
                result = post('status', {'id': job['id']})
                if result['state'] != 'running':
                    break
                time.sleep(.1)
            assert result['state'] == 'done', result
            with Image.open(result['result']['path']) as output:
                assert output.format == 'JPEG' and output.size == (2, 2)
            pdf = PdfWriter()
            pdf.add_blank_page(width=100, height=200)
            stream = io.BytesIO()
            pdf.write(stream)
            source_pdf = stream.getvalue()
            pdf_job = post('new', {'files': [{'name': name, 'size': len(source_pdf)} for name in ('a.pdf', 'b.pdf')]})
            for index in range(2):
                post('upload', {'id': pdf_job['id'], 'index': index, 'offset': 0, 'data': base64.b64encode(source_pdf).decode()})
            assert len(post('probe', {'id': pdf_job['id']})['info']) == 2
            post('run', {'id': pdf_job['id'], 'operation': 'pdf-merge', 'options': {}})
            for _ in range(100):
                pdf_result = post('status', {'id': pdf_job['id']})
                if pdf_result['state'] != 'running':
                    break
                time.sleep(.1)
            assert pdf_result['state'] == 'done', pdf_result
            with Path(pdf_result['result']['path']).open('rb') as output:
                assert len(PdfReader(output).pages) == 2
            print(json.dumps({'image': result['result']['verified'], 'pdf': pdf_result['result']['verified']}))
        finally:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                process.terminate()
                psutil.wait_procs(children + [parent], timeout=5)
                for child in children:
                    if child.is_running():
                        child.kill()
                if process.poll() is None:
                    process.kill()
            except psutil.NoSuchProcess:
                pass
