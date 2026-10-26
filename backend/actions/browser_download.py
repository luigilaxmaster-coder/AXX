"""Download one observed PDF link through Playwright in the prepared CDP session."""
import asyncio
import hashlib
from pathlib import Path
import shutil
import tempfile
import threading
from urllib.parse import urljoin

from . import browser_bridge as bridge
from .artifact_verification import MAX_PDF_BYTES, run_inspector
from .file_inspection import hash_file
from .process_runner import _artifact_path


def validate(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {'tab_id', 'expected_url', 'browser_session', 'document_id', 'link_name', 'download_url', 'destination'}:
        raise ValueError('Se requieren sesión, pestaña, documento, enlace exacto, URL y destino')
    bridge.validate_inputs('navigate', {key: inputs[key] for key in ('tab_id', 'expected_url', 'browser_session', 'document_id')} | {'url': inputs['download_url']})
    if not isinstance(inputs['link_name'], str) or not 1 <= len(inputs['link_name']) <= 500:
        raise ValueError('Indica el nombre accesible exacto del enlace')
    raw = inputs['destination']
    from .tools import artifact_path_error
    if artifact_path_error(raw):
        raise ValueError('Ruta de destino inválida')
    path = Path(raw)
    if path.is_absolute() or path.drive or '..' in path.parts or path.suffix.lower() != '.pdf':
        raise ValueError('El destino debe ser un PDF relativo nuevo en el espacio autorizado')


async def _download(inputs, folder, cancelled, receipt):
    from playwright.async_api import async_playwright
    inventory = bridge.discover()
    if inventory['browser_session'] != inputs['browser_session']:
        raise ValueError('La sesión del navegador cambió')
    target = [row for row in inventory['tabs'] if row['tab_id'] == inputs['tab_id'] and bridge._same_url(row['url'], inputs['expected_url'])]
    if len(target) != 1:
        raise ValueError('La pestaña observada cambió')
    endpoint, _ = bridge.configuration()
    socket = bridge._socket_url(bridge._json(endpoint, '/json/version').get('webSocketDebuggerUrl'), endpoint, r'/devtools/browser/[A-Za-z0-9_-]+')
    if hashlib.sha256(socket.encode()).hexdigest() != inputs['browser_session']:
        raise ValueError('El navegador se reinició durante la conexión')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(socket, timeout=5000, artifacts_dir=str(folder))
        page, session = None, None
        for context in browser.contexts:
            for candidate in context.pages:
                probe = await context.new_cdp_session(candidate)
                info = await probe.send('Target.getTargetInfo')
                if info['targetInfo']['targetId'] == inputs['tab_id']:
                    page, session = candidate, probe
                    break
                await probe.detach()
            if page is not None:
                break
        if page is None:
            raise ValueError('Playwright no encontró la pestaña exacta')
        async def current():
            frame = (await session.send('Page.getFrameTree'))['frameTree']['frame']
            if frame['loaderId'] != inputs['document_id'] or not bridge._same_url(frame['url'], inputs['expected_url']):
                raise ValueError('El documento cambió; vuelve a inspeccionarlo')
        await current()
        link = page.get_by_role('link', name=inputs['link_name'], exact=True)
        if await link.count() != 1:
            raise ValueError('El enlace está ausente o es ambiguo')
        href = await link.get_attribute('href', timeout=1000)
        if not href or not bridge._same_url(urljoin(page.url, href), inputs['download_url']):
            raise ValueError('El destino del enlace no coincide con la URL autorizada')
        await link.click(trial=True, timeout=1000)
        await current()
        if cancelled.is_set():
            raise ValueError('Cancelado antes de pulsar el enlace')
        receipt['dispatched'] = True
        async with page.expect_download(timeout=25000) as pending:
            await link.click(timeout=1000, no_wait_after=True)
        download = await pending.value
        try:
            if not bridge._same_url(download.url, inputs['download_url']):
                raise ValueError('La descarga redirigió a otra URL; requiere revisión')
            staging = folder / 'verified-download.pdf'
            await download.save_as(str(staging))
            if await download.failure():
                raise ValueError('La descarga no terminó correctamente')
            if not staging.is_file() or staging.stat().st_size > MAX_PDF_BYTES:
                raise ValueError('Descarga ausente o mayor de 40 MiB')
            await current()
            return staging
        finally:
            await download.cancel()


async def _supervised(inputs, folder, cancelled, receipt):
    task = asyncio.create_task(_download(inputs, folder, cancelled, receipt))
    try:
        for _ in range(300):
            done, _ = await asyncio.wait({task}, timeout=.1)
            if done:
                return task.result()
            size = sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
            if cancelled.is_set() or size > 2 * MAX_PDF_BYTES or shutil.disk_usage(folder).free < 128 * 1024 * 1024:
                raise ValueError('Descarga detenida por cancelación o límite de recursos')
        raise TimeoutError('La descarga superó 30 segundos')
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except (Exception, asyncio.CancelledError):
            pass


class BrowserDownloadTool:
    name, version = 'browser_download_pdf', '1.0.0'
    description = 'Persist one exact observed PDF download with session binding and verified contents'

    def verify_preconditions(self, inputs):
        try:
            validate(inputs)
            bridge.configuration()
            import playwright.async_api
            return True, 'Descarga tipada y transporte configurado'
        except (ValueError, TypeError, ImportError) as exc:
            return False, str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='La descarga requiere el espacio autorizado del ejecutor')

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult, artifact_path_error
        receipt, created, target = {'dispatched': False}, False, None
        try:
            validate(inputs)
            target = _artifact_path(inputs['destination'], workspace_root)
            if target.exists() or not target.parent.is_dir():
                raise ValueError('El PDF debe ser nuevo y su carpeta debe existir')
            if cancelled.is_set():
                raise ValueError('Descarga cancelada antes de conectar')
            with tempfile.TemporaryDirectory(prefix='.download-', dir=workspace_root) as folder:
                staging = asyncio.run(_supervised(inputs, Path(folder), cancelled, receipt))
                verification = run_inspector('pdf', str(staging), cancelled)
                if cancelled.is_set() or artifact_path_error(str(target)):
                    raise ValueError('Cancelación o ruta modificada antes de publicar el PDF')
                with target.open('xb') as stream, staging.open('rb') as source:
                    created = True
                    shutil.copyfileobj(source, stream, 1024 * 1024)
                digest = hash_file(str(target), cancelled)
                if digest['sha256'] != verification['sha256']:
                    raise ValueError('El PDF persistido no coincide con la descarga')
            output = {**verification, **digest, 'source_url': inputs['download_url'],
                      'browser_session': inputs['browser_session'], 'tab_id': inputs['tab_id'],
                      'document_id': inputs['document_id']}
            return ToolResult(True, output=output, evidence={'verification': 'downloaded_pdf_persisted', 'original_document_unchanged': True})
        except Exception as exc:
            return ToolResult(False, output={'path': str(target) if created else None}, error=str(exc)[:600],
                evidence={'effect_uncertain': receipt['dispatched'], 'partial_effect': created, 'cancelled': cancelled.is_set(),
                          'created_paths': [str(target)] if created else []})

    def verify_postconditions(self, inputs, result):
        try:
            valid = bool(result.success and result.evidence.get('verification') == 'downloaded_pdf_persisted'
                         and hash_file(result.output['path'], threading.Event())['sha256'] == result.output['sha256'])
            return valid, 'PDF descargado y persistido' if valid else 'PDF no confirmado'
        except (ValueError, OSError, KeyError) as exc:
            return False, str(exc)
