"""Edit one exact text shape in a private PPTX copy, reopen it, and verify its PDF."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from xml.etree import ElementTree as ET
import zipfile

from .file_inspection import validate_path, hash_file
from .process_runner import _artifact_path


def powerpoint_processes():
    import psutil
    return [p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').casefold() == 'powerpnt.exe']


def checked_input(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {'source','destination','slide','shape_name','expected_text','new_text'}:
        raise ValueError('Indica origen, destino, diapositiva, forma y texto exactos')
    source = validate_path(inputs['source'])
    if source.suffix.lower() != '.pptx' or source.stat().st_size > 25 * 1024 * 1024: raise ValueError('Selecciona un PPTX local de hasta 25 MiB')
    if type(inputs['slide']) is not int or not 1 <= inputs['slide'] <= 100: raise ValueError('Diapositiva inválida')
    for key, maximum in [('shape_name',200),('expected_text',4000),('new_text',4000)]:
        if not isinstance(inputs[key], str) or not inputs[key] or len(inputs[key]) > maximum or any(ord(c)<32 and c not in '\r\n\t' for c in inputs[key]):
            raise ValueError('Texto de presentación inválido')
    if not isinstance(inputs['destination'], str) or Path(inputs['destination']).is_absolute() or '..' in Path(inputs['destination']).parts:
        raise ValueError('Indica una carpeta de destino nueva en artifacts')
    with zipfile.ZipFile(source) as archive:
        files = archive.infolist()
        if len(files) > 3000 or sum(item.file_size for item in files) > 100 * 1024 * 1024:
            raise ValueError('PPTX expandido fuera de límites')
        for item in files:
            name = item.filename.casefold()
            if any(marker in name for marker in ('vbaproject','/embeddings/','/activex/')):
                raise ValueError('Esta ruta no admite macros ni contenido activo incrustado')
            if name.endswith('.rels'):
                if any(node.attrib.get('TargetMode','').lower() == 'external' for node in ET.fromstring(archive.read(item))):
                    raise ValueError('Esta ruta no admite vínculos externos')
    return hash_file(str(source), threading.Event())


def powerpoint_worker(request):
    if powerpoint_processes(): raise ValueError('powerpoint_busy: cierra PowerPoint antes de ejecutar; no se modificó su sesión')
    import pythoncom
    import psutil
    import win32com.client
    from backend.inference.process_manager import WindowsJobObject
    from .windows_automation import process_name, process_started
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = deck = job = None
    owned = False
    started = int((time.time()+11644473600)*10000000)
    try:
        app = win32com.client.DispatchEx('PowerPoint.Application')
        kernel = C.WinDLL('kernel32',use_last_error=True)
        candidates = powerpoint_processes()
        if len(candidates) != 1: raise ValueError('No se pudo identificar un único proceso privado de PowerPoint')
        pid = candidates[0]
        birth = process_started(pid)
        arguments = {arg.casefold() for arg in psutil.Process(pid).cmdline()[1:]}
        # PowerPoint does not expose HWND consistently through late-bound COM.
        if not birth or int(birth) < started or process_name(pid) != 'powerpnt.exe' or arguments != {'/automation','-embedding'} or app.Presentations.Count:
            raise ValueError('No se pudo comprobar una instancia privada de PowerPoint')
        owned = True
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [W.DWORD,W.BOOL,W.DWORD], W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        handle = kernel.OpenProcess(0x101,False,pid)
        try:
            job = WindowsJobObject()
            if not handle or not job.assign_process(handle): raise ValueError('PowerPoint privado no puede supervisarse')
        finally:
            if handle: kernel.CloseHandle(handle)
        app.AutomationSecurity = 3
        data = request['data']
        deck = app.Presentations.Open(data['source'], ReadOnly=False, Untitled=False, WithWindow=False)
        count = deck.Slides.Count
        if not 1 <= count <= 100 or data['slide'] > count: raise ValueError('Presentación fuera de límites')
        slide = deck.Slides.Item(data['slide'])
        matches = [shape for shape in slide.Shapes if shape.Name == data['shape_name']]
        if len(matches) != 1 or not matches[0].HasTextFrame: raise ValueError('No se encontró una forma de texto única')
        shape = matches[0]
        if shape.TextFrame.TextRange.Text != data['expected_text']: raise ValueError('El texto de origen cambió')
        shape.TextFrame.TextRange.Text = data['new_text']
        output = Path(request['output']); target, pdf = output/'presentation.pptx', output/'presentation.pdf'
        if target.exists() or pdf.exists(): raise ValueError('El destino temporal ya existe')
        deck.SaveCopyAs(str(target), 24)
        deck.Close(); deck = None
        deck = app.Presentations.Open(str(target), ReadOnly=True, Untitled=False, WithWindow=False)
        if deck.Slides.Count != count or deck.Slides.Item(data['slide']).Shapes.Item(data['shape_name']).TextFrame.TextRange.Text != data['new_text']:
            raise ValueError('El PPTX reabierto no conserva la modificación exacta')
        deck.ExportAsFixedFormat(Path=str(pdf), FixedFormatType=2, PrintHiddenSlides=-1, PrintRange=None)
        return {'success':True,'application':'PowerPoint','version':str(app.Version),'slides':count,'owned_pid':pid,'reopened_verified':True}
    finally:
        if owned:
            if deck is not None:
                try: deck.Close()
                except Exception: pass
            if app is not None:
                try: app.Quit()
                except Exception: pass
        deck = app = None
        if job: job.close()
        pythoncom.CoUninitialize()


class PowerPointTool:
    name, version = 'office_powerpoint_pdf', '1.0.0'
    description = 'Exact shape text change on a private PowerPoint copy, followed by reopened PPTX/PDF verification'

    def verify_preconditions(self, inputs):
        try:
            checked_input(inputs)
            if os.name != 'nt': raise ValueError('PowerPoint requiere Windows')
            return True, 'PPTX acotado y sin vínculos externos'
        except Exception as exc: return False, str(exc)[:600]

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .office_workflows import _run_worker
        from .artifact_verification import run_inspector
        from .tools import ToolResult
        published, created = [], []
        try:
            before = checked_input(inputs)
            target = _artifact_path(inputs['destination'], workspace_root)
            if target.exists(): raise ValueError('El destino ya existe; no se sobrescribe')
            if powerpoint_processes(): raise ValueError('powerpoint_busy: cierra PowerPoint antes de ejecutar')
            if cancelled.is_set(): raise ValueError('Cancelado antes de abrir PowerPoint')
            with tempfile.TemporaryDirectory(prefix='axx-ppt-') as folder:
                staging = Path(folder); source = staging/'source.pptx'
                shutil.copyfile(inputs['source'], source)
                if hash_file(str(source), cancelled)['sha256'] != before['sha256']: raise ValueError('El origen cambió al copiarlo')
                application = _run_worker(inputs | {'source':str(source)}, staging, cancelled, operation='powerpoint_pdf')
                pdf = run_inspector('pdf',str(staging/'presentation.pdf'),cancelled)
                if pdf['page_count'] != application['slides'] or ' '.join(inputs['new_text'].split()) not in ' '.join(pdf['text_excerpt'].split()):
                    raise ValueError('El PDF no conserva las diapositivas y el texto solicitados')
                if hash_file(inputs['source'],cancelled) != before: raise ValueError('El PPTX original cambió')
                target.mkdir(parents=True, exist_ok=False)
                created.append(str(target))
                for name in ('presentation.pptx','presentation.pdf'):
                    if cancelled.is_set(): raise ValueError('Cancelado durante publicación; revisa los archivos creados')
                    output = _artifact_path(str(target/name),workspace_root)
                    with output.open('xb') as stream:
                        created.append(str(output))
                        stream.write((staging/name).read_bytes())
                    published.append(hash_file(str(output),cancelled))
            return ToolResult(True,output={'files':published,'source_sha256':before['sha256'],'application':application,'pages':pdf['page_count'],
                'visual_layout_verified':False},evidence={'verification':'reopened_powerpoint_and_pdf_text'})
        except Exception as exc:
            return ToolResult(False,error=str(exc)[:600],evidence={'created_paths':created,'created_files':published,'effect_uncertain':bool(created),'cancelled':cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        try:
            valid = result.success and all(hash_file(row['path'],threading.Event())['sha256'] == row['sha256'] for row in result.output['files'])
            valid = valid and hash_file(inputs['source'],threading.Event())['sha256'] == result.output['source_sha256']
            return bool(valid), 'PPTX y PDF comprobados, original intacto'
        except Exception: return False, 'No se verificaron los archivos'
