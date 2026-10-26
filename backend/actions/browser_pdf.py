"""Open the exact verified PDF in a new background tab of the configured browser."""
import hashlib
from pathlib import Path
import re
import threading
import time

from . import browser_bridge as bridge
from .artifact_verification import run_inspector
from .file_inspection import hash_file, validate_path


class BrowserPdfTool:
    name, version = 'browser_open_pdf', '1.0.0'
    description = 'Open an explicitly selected, hash-verified PDF and read back its exact file URL'

    def verify_preconditions(self, inputs):
        try:
            if not isinstance(inputs, dict) or set(inputs) != {'path', 'sha256', 'browser_session'}: raise ValueError('Parámetros PDF inválidos')
            if any(not isinstance(inputs[key], str) or not re.fullmatch('[a-f0-9]{64}', inputs[key]) for key in ('sha256','browser_session')):
                raise ValueError('Hash o sesión inválidos')
            if validate_path(inputs['path']).suffix.lower() != '.pdf': raise ValueError('Selecciona el PDF exacto')
            return True, 'PDF y referencias tipadas'
        except (ValueError, OSError, TypeError) as exc: return False, str(exc)

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        connection, page = None, None
        dispatched = False
        try:
            valid, reason = self.verify_preconditions(inputs)
            if not valid: raise ValueError(reason)
            inspected = run_inspector('pdf', inputs['path'], cancelled)
            if inspected['sha256'] != inputs['sha256']: raise ValueError('El PDF cambió; vuelve a comprobarlo')
            endpoint, _ = bridge.configuration()
            socket = bridge._socket_url(bridge._json(endpoint, '/json/version').get('webSocketDebuggerUrl'), endpoint, r'/devtools/browser/[A-Za-z0-9_-]+')
            if hashlib.sha256(socket.encode()).hexdigest() != inputs['browser_session']: raise ValueError('La sesión del navegador cambió')
            url = Path(inputs['path']).resolve(strict=True).as_uri()
            connection = bridge._Connection(socket, cancelled)
            if cancelled.is_set(): raise ValueError('Cancelado antes de abrir PDF')
            dispatched = True
            target = connection.call('Target.createTarget', {'url':url, 'background':True})['targetId']
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if cancelled.is_set(): raise ValueError('Cancelado después de abrir PDF; comprueba la pestaña creada')
                rows = bridge._json(endpoint, '/json/list')
                current = next((row for row in rows if row.get('id') == target and row.get('url') == url), None)
                if current:
                    page = bridge._Connection(bridge._socket_url(current.get('webSocketDebuggerUrl'), endpoint, '/devtools/page/' + re.escape(target)), cancelled)
                    frame = bridge._frame(page)
                    if frame['url'] == url: break
                    page.close(); page = None
                cancelled.wait(.1)
            if page is None or hash_file(inputs['path'], cancelled)['sha256'] != inputs['sha256']:
                raise ValueError('No se comprobó el PDF exacto en el visor')
            return ToolResult(True, output={'path':inputs['path'], 'sha256':inputs['sha256'], 'url':url, 'tab_id':target,
                'browser_session':inputs['browser_session'], 'page_count':inspected['page_count'], 'visual_render_verified':False},
                evidence={'verification':'pdf_hash_and_viewer_file_url'})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:600], evidence={'effect_uncertain':dispatched,'cancelled':cancelled.is_set()})
        finally:
            if page: page.close()
            if connection: connection.close()

    def verify_postconditions(self, inputs, result):
        try:
            endpoint, _ = bridge.configuration()
            rows = bridge._json(endpoint, '/json/list')
            valid = (result.success and hash_file(inputs['path'], threading.Event())['sha256'] == inputs['sha256']
                     and any(row.get('id') == result.output['tab_id'] and row.get('url') == result.output['url'] for row in rows))
            return bool(valid), 'PDF exacto abierto en el perfil seleccionado'
        except (OSError, ValueError, TypeError): return False, 'El visor dejó de estar disponible'
