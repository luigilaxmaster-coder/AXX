import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions import browser_bridge as bridge
from backend.actions.browser_download import BrowserDownloadTool, validate
from backend.actions.browser_pdf import BrowserPdfTool
from backend.actions.executor import ActionExecutor
from backend.inference.process_manager import spawn_managed_process, terminate_process_tree


class BrowserDownloadContracts(unittest.TestCase):
    def test_no_script_or_path_escape(self):
        valid = dict(tab_id='A', browser_session='a'*64, document_id='doc', expected_url='https://example.com/',
                     link_name='Download', download_url='https://example.com/file.pdf', destination='out.pdf')
        validate(valid)
        for change in ({'destination': '../out.pdf'}, {'destination': 'C:/out.pdf'}, {'download_url': 'javascript:alert(1)'}, {'script': 'x'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(valid | change)

    @unittest.skipUnless(os.environ.get('AXX_TEST_BROWSER_NATIVE') == '1', 'requires explicitly enabled isolated native Edge test')
    def test_native_download_identity_and_no_overwrite(self):
        from pypdf import PdfWriter
        writer = PdfWriter(); writer.add_blank_page(width=300, height=400)
        stream = io.BytesIO(); writer.write(stream); pdf = stream.getvalue()
        class Fixture(BaseHTTPRequestHandler):
            def do_GET(self):
                body = pdf if self.path == '/file.pdf' else b'<html><title>Axx download fixture</title><a href="/file.pdf">Download sheet</a></html>'
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf' if self.path == '/file.pdf' else 'text/html')
                if self.path == '/file.pdf': self.send_header('Content-Disposition', 'attachment; filename="sheet.pdf"')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        process = job = None
        with tempfile.TemporaryDirectory(prefix='axx-download-') as temp:
            root = Path(temp); profile = root / 'profile'; profile.mkdir()
            try:
                base = 'http://127.0.0.1:' + str(server.server_port)
                executable = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
                process, job = spawn_managed_process([str(executable), '--headless=new', '--remote-debugging-address=127.0.0.1',
                    '--remote-debugging-port=0', '--user-data-dir='+str(profile), '--no-first-run', '--no-default-browser-check', base],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                active = profile / 'DevToolsActivePort'
                deadline = time.monotonic() + 15
                while not active.exists() and time.monotonic() < deadline: time.sleep(.1)
                self.assertTrue(active.exists())
                port = int(active.read_text().splitlines()[0])
                with patch.dict(os.environ, {'AXX_BROWSER_CDP_URL': f'http://127.0.0.1:{port}', 'AXX_BROWSER_PROFILE_LABEL': 'download-fixture'}):
                    inventory = bridge.discover()
                    target = next(row for row in inventory['tabs'] if row['url'].rstrip('/') == base)
                    identity = {'browser_session': inventory['browser_session'], 'tab_id': target['tab_id'], 'expected_url': target['url']}
                    observed = bridge.BrowserBridgeTool('inspect').execute(identity)
                    self.assertTrue(observed.success, observed.error)
                    inputs = identity | {'document_id': observed.output['document_id'], 'link_name': 'Download sheet', 'download_url': base+'/file.pdf', 'destination': 'sheet.pdf'}
                    tool = BrowserDownloadTool()
                    stale = tool.execute_cancellable(inputs | {'document_id': 'stale'}, root, threading.Event())
                    self.assertFalse(stale.success); self.assertFalse(stale.evidence['effect_uncertain'])
                    with ActionExecutor(root / 'state.db', root) as executor:
                        result = executor.execute_action(tool.name, inputs)
                        self.assertTrue(result['postconditions_passed'], result)
                        self.assertEqual(result['output']['sha256'], hashlib.sha256(pdf).hexdigest())
                        self.assertEqual(result['output']['page_count'], 1)
                        opened = executor.execute_action('browser_open_pdf', {'path':result['output']['path'],
                            'sha256':result['output']['sha256'], 'browser_session':inventory['browser_session']})
                        self.assertEqual(opened['state'], 'succeeded', opened)
                        self.assertEqual(opened['output']['path'], result['output']['path'])
                    second = tool.execute_cancellable(inputs, root, threading.Event())
                    self.assertFalse(second.success); self.assertFalse(second.evidence['effect_uncertain'])
                    self.assertEqual((root/'sheet.pdf').read_bytes(), pdf)
            finally:
                if process: terminate_process_tree(process, job)
                server.shutdown(); server.server_close()
                time.sleep(.3)


if __name__ == '__main__': unittest.main()
