"""Bounded private Office workflows with exclusive outputs and independent readback."""
from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from xml.etree import ElementTree as ET
import zipfile

from .file_inspection import hash_file, validate_path

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS, MAX_COLUMNS = 2000, 50
MAX_CELLS = 20000
OFFICE_TIMEOUT_SECONDS = 90
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _path(raw):
    from .tools import artifact_path_error
    error = artifact_path_error(raw)
    if error:
        raise ValueError(error)
    return Path(raw)


def _column(index):
    value = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def csv_data(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {'source', 'destination', 'delimiter', 'numeric_column'}:
        raise ValueError('Indica source, destination, delimiter y numeric_column exactos.')
    source = validate_path(inputs['source'])
    if source.suffix.lower() != '.csv':
        raise ValueError('El origen debe ser un CSV UTF-8 local.')
    destination = _path(inputs['destination'])
    if destination.is_absolute() or destination.drive or destination.suffix.lower() != '.xlsx' or '..' in destination.parts:
        raise ValueError('El destino debe ser un XLSX nuevo relativo al espacio autorizado.')
    if inputs['delimiter'] not in (',', ';', '\t') or not isinstance(inputs['numeric_column'], str):
        raise ValueError('Selecciona delimitador coma, punto y coma o tabulador, y encabezado numérico exacto.')
    with source.open('rb') as stream:
        raw = stream.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError('El CSV supera 2 MiB.')
    source_digest = hashlib.sha256(raw).hexdigest()
    if hash_file(str(source), threading.Event())['sha256'] != source_digest:
        raise ValueError('El CSV cambió durante la lectura.')
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), delimiter=inputs['delimiter'], strict=True))
    if not 2 <= len(rows) <= MAX_ROWS + 1 or not 1 <= len(rows[0]) <= MAX_COLUMNS or len(rows) * len(rows[0]) > MAX_CELLS:
        raise ValueError('El CSV requiere encabezados, 1–2000 filas, hasta 50 columnas y 20000 celdas en total.')
    headers = rows[0]
    if len(set(headers)) != len(headers) or any(not cell for cell in headers) or inputs['numeric_column'] not in headers:
        raise ValueError('Los encabezados deben ser únicos y contener la columna numérica exacta.')
    column = headers.index(inputs['numeric_column'])
    values = []
    for row in rows:
        if len(row) != len(headers) or any(len(cell) > 8192 or '\0' in cell for cell in row):
            raise ValueError('Filas con diferente longitud o celdas inválidas.')
    for row in rows[1:]:
        literal = row[column].strip()
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', literal):
            raise ValueError('La columna numérica requiere decimales con punto, sin moneda, agrupación ni vacíos.')
        value = Decimal(literal)
        if len(value.normalize().as_tuple().digits) > 15 or abs(value) > Decimal('1e12') or (value and abs(value) < Decimal('1e-300')):
            raise ValueError('El valor supera la precisión o magnitud admitida por Excel.')
        values.append(value)
    total = sum(values, Decimal(0))
    if abs(total) > Decimal('1e15'):
        raise ValueError('El total supera la magnitud admitida.')
    return {'source': str(source), 'source_sha256': source_digest, 'rows': rows,
            'numeric_column_index': column, 'numbers': [float(value) for value in values],
            'expected_total': str(total), 'formula': '=SUM(' + _column(column + 1) + '2:' + _column(column + 1) + str(len(rows)) + ')'}


def verify_xlsx(path, data):
    with zipfile.ZipFile(path) as package:
        entries = package.infolist()
        if len(entries) > 1000 or sum(row.file_size for row in entries) > 32 * 1024 * 1024:
            raise ValueError('XLSX excede los límites de verificación.')
        strings = []
        if 'xl/sharedStrings.xml' in package.namelist():
            strings = [''.join(node.itertext()) for node in ET.fromstring(package.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        sheet = ET.fromstring(package.read('xl/worksheets/sheet1.xml'))
        cells = {cell.attrib['r']: cell for cell in sheet.findall('s:sheetData/s:row/s:c', NS)}
        column = data['numeric_column_index']
        for row_number, row in enumerate(data['rows'], 1):
            for col, expected in enumerate(row):
                cell = cells.get(_column(col + 1) + str(row_number))
                if cell is None:
                    if expected == '':
                        continue
                    raise ValueError('Falta una celda del CSV en el XLSX.')
                if cell.find('s:f', NS) is not None:
                    raise ValueError('Una entrada CSV se convirtió indebidamente en fórmula.')
                raw = cell.findtext('s:v', '', NS)
                if row_number > 1 and col == column:
                    if cell.attrib.get('t') not in (None, 'n') or not math.isclose(float(raw), data['numbers'][row_number - 2], rel_tol=1e-12, abs_tol=0):
                        raise ValueError('La columna numérica no conserva valor y tipo.')
                else:
                    actual = strings[int(raw)] if cell.attrib.get('t') == 's' else ''.join(cell.find('s:is', NS).itertext()) if cell.attrib.get('t') == 'inlineStr' else raw
                    if actual != expected or cell.attrib.get('t') not in ('s', 'inlineStr'):
                        if actual != '' or expected != '':
                            raise ValueError('Una celda de texto cambió de contenido o tipo.')
        total_ref = _column(column + 1) + str(len(data['rows']) + 1)
        total = cells.get(total_ref)
        if total is None or total.findtext('s:f', '', NS) != data['formula'][1:]:
            raise ValueError('Falta la fórmula de total esperada.')
        if not math.isclose(float(total.findtext('s:v', 'nan', NS)), float(data['expected_total']), rel_tol=1e-12, abs_tol=0):
            raise ValueError('El total del XLSX no coincide con la suma independiente.')
    return {'data_rows': len(data['rows']) - 1, 'columns': len(data['rows'][0]),
            'total': data['expected_total'], 'formula': data['formula'], 'verification': 'reopened_com_and_independent_ooxml_cells'}


def _excel_worker(request):
    import ctypes as C
    from ctypes import wintypes as W
    import pythoncom
    import win32com.client
    from backend.actions.windows_automation import process_name, process_started
    from backend.inference.process_manager import WindowsJobObject

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = book = sheet = None
    job = None
    owned = False
    started = int((time.time() + 11644473600) * 10000000)
    try:
        app = win32com.client.DispatchEx('Excel.Application')
        user, kernel = C.WinDLL('user32', use_last_error=True), C.WinDLL('kernel32', use_last_error=True)
        user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        pid = W.DWORD()
        user.GetWindowThreadProcessId(W.HWND(app.Hwnd), C.byref(pid))
        birth = process_started(pid.value)
        if not pid.value or process_name(pid.value) != 'excel.exe' or not birth or int(birth) < started or app.Workbooks.Count:
            raise ValueError('Excel instance ownership cannot be confirmed; existing Office sessions were not touched')
        owned = True
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        handle = kernel.OpenProcess(0x101, False, pid.value)
        try:
            job = WindowsJobObject()
            if not handle or not job.assign_process(handle):
                raise ValueError('The private Excel process could not be placed under cancellation supervision')
        finally:
            if handle:
                kernel.CloseHandle(handle)
        app.Visible = False
        app.AutomationSecurity = 3
        app.DisplayAlerts = False
        app.EnableEvents = False
        data = request['data']
        target = request['output']
        if Path(target).exists():
            raise ValueError('Worker output already exists')
        book = app.Workbooks.Add(-4167)
        sheet = book.Worksheets(1)
        sheet.Name = 'Datos'
        rows, columns = len(data['rows']), len(data['rows'][0])
        area = sheet.Range(sheet.Cells(1, 1), sheet.Cells(rows, columns))
        area.NumberFormat = '@'
        area.Value2 = tuple(tuple(row) for row in data['rows'])
        col = data['numeric_column_index'] + 1
        numbers = sheet.Range(sheet.Cells(2, col), sheet.Cells(rows, col))
        numbers.NumberFormat = '0.###############'
        numbers.Value2 = tuple((value,) for value in data['numbers'])
        total = sheet.Cells(rows + 1, col)
        total.NumberFormat = '0.###############'
        total.Formula = data['formula']
        app.CalculateFull()
        book.SaveAs(target, 51)
        book.Close(False)
        book = app.Workbooks.Open(target, 0, True)
        sheet = book.Worksheets(1)
        for row_index, expected in enumerate(data['rows'], 1):
            for column_index, value in enumerate(expected, 1):
                cell = sheet.Cells(row_index, column_index)
                if cell.HasFormula:
                    raise ValueError('CSV text became an active formula')
                actual = cell.Value2
                if row_index > 1 and column_index == col:
                    if type(actual) not in (int, float) or not math.isclose(actual, data['numbers'][row_index - 2], rel_tol=1e-12, abs_tol=0):
                        raise ValueError('Excel numeric readback differs')
                elif (actual or '') != value:
                    raise ValueError('Excel text readback differs')
        if sheet.Cells(rows + 1, col).Formula != data['formula'] or not math.isclose(sheet.Cells(rows + 1, col).Value2, float(data['expected_total']), rel_tol=1e-12, abs_tol=0):
            raise ValueError('Excel total formula/readback differs')
        return {'success': True, 'application': 'Excel', 'version': str(app.Version), 'owned_pid': pid.value,
                'process_started': birth, 'reopened_verified': True}
    finally:
        if owned:
            if book is not None:
                try:
                    book.Close(False)
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
        sheet = book = app = None
        if job:
            job.close()
        pythoncom.CoUninitialize()


def worker_main():
    try:
        raw = sys.stdin.buffer.read(4 * MAX_CSV_BYTES + 1)
        if len(raw) > 4 * MAX_CSV_BYTES:
            raise ValueError('Office worker request exceeds the bound')
        request = json.loads(raw)
        if set(request) != {'operation', 'data', 'output'} or request['operation'] not in ('excel_csv', 'word_pdf'):
            raise ValueError('Unsupported fixed Office operation')
        result = _excel_worker(request) if request['operation'] == 'excel_csv' else _word_worker(request)
    except Exception as exc:
        result = {'success': False, 'error': str(exc)[:800]}
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    return 0 if result['success'] else 1


def _run_worker(data, output, cancelled, operation='excel_csv'):
    from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
    command = [sys.executable, '--office-worker'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'backend.actions.office_workflows']
    process, job = spawn_managed_process(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    payload = json.dumps({'operation': operation, 'data': data, 'output': str(output)}, ensure_ascii=True).encode()
    deadline = time.monotonic() + OFFICE_TIMEOUT_SECONDS
    try:
        while True:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise TimeoutError('Office cancelled or exceeded its deadline. Owned jobs were closed; an Office instance stalled before ownership verification cannot be confirmed closed.')
            try:
                stdout, stderr = process.communicate(payload, timeout=.1)
                break
            except subprocess.TimeoutExpired:
                payload = None
        if len(stdout) > 32768 or len(stderr) > 32768:
            raise ValueError('Office worker returned excessive output')
        result = json.loads(stdout)
        if not result.get('success') or process.returncode:
            raise ValueError(result.get('error', 'Office worker failed'))
        return result
    finally:
        terminate_process_tree(process, job)


class ExcelCsvTool:
    name, version = 'office_excel_csv', '1.0.0'
    description = 'Import an explicitly selected CSV into a new Excel workbook, preserving text and verifying the numeric total'

    def verify_preconditions(self, inputs):
        try:
            csv_data(inputs)
            if os.name != 'nt':
                raise ValueError('Microsoft Excel automation requires Windows')
            import win32com.client
            return True, 'CSV schema, bounds and Windows automation dependency checked; Office activation checked during execution'
        except (ValueError, OSError, UnicodeError, ImportError, csv.Error) as exc:
            return False, str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='An authorized executor workspace is required')

    def execute_in_workspace(self, inputs, workspace_root):
        return self.execute_cancellable(inputs, workspace_root, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        created, launched, target = False, False, None
        try:
            data = csv_data(inputs)
            root = _path(str(workspace_root)).resolve(strict=True)
            target = _path(str(root / inputs['destination']))
            if not target.resolve().is_relative_to(root) or not target.parent.is_dir() or target.exists():
                raise ValueError('El destino debe ser nuevo y su carpeta debe existir dentro del espacio autorizado.')
            if cancelled.is_set():
                raise ValueError('Cancelado antes de abrir Office.')
            with tempfile.TemporaryDirectory(prefix='.office-', dir=root) as folder:
                staging = Path(folder) / 'output.xlsx'
                launched = True
                application = _run_worker(data, staging, cancelled)
                verification = verify_xlsx(staging, data)
                if hash_file(data['source'], cancelled)['sha256'] != data['source_sha256']:
                    raise ValueError('El origen cambió; no se publica el resultado.')
                _path(str(target))
                if cancelled.is_set():
                    raise ValueError('Cancelado antes de publicar el archivo nuevo.')
                with staging.open('rb') as source, target.open('xb') as destination:
                    created = True
                    while chunk := source.read(1024 * 1024):
                        if cancelled.is_set():
                            raise ValueError('Cancelado durante la escritura; se conserva el archivo parcial.')
                        destination.write(chunk)
            verify_xlsx(target, data)
            file = hash_file(str(target), cancelled)
            return ToolResult(True, output={**verification, **file, 'source': data['source'], 'source_sha256': data['source_sha256'],
                                           'application': application}, evidence={'verification': verification['verification'], 'source_unchanged': True})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:800], output={'path': str(target) if created else None}, evidence={
                'cancelled': cancelled.is_set(), 'effect_uncertain': created or launched, 'partial_effect': created,
                'dispatch_status': 'delivered' if launched else 'rejected', 'effect_status': 'partial' if created else 'not_observed',
                'office_cleanup': 'owned_job_closed; pre_ownership_instance_unconfirmed' if launched else 'not_started',
                'created_paths': [str(target)] if created else []})

    def verify_postconditions(self, inputs, result):
        if not result.success:
            return False, result.error or 'Office operation failed'
        try:
            data = csv_data(inputs)
            verify_xlsx(result.output['path'], data)
            digest = hash_file(result.output['path'], threading.Event())
            valid = digest['sha256'] == result.output['sha256'] and data['source_sha256'] == result.output['source_sha256']
            return valid, 'Original CSV and published workbook independently verified' if valid else 'File hash changed'
        except Exception as exc:
            return False, str(exc)


def word_processes():
    if os.name != 'nt':
        raise ValueError('Microsoft Word automation requires Windows')
    executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/tasklist.exe'
    result = subprocess.run([str(executable), '/FI', 'IMAGENAME eq WINWORD.EXE', '/FO', 'CSV', '/NH'],
                            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError('Cannot inspect existing Word processes; automation is blocked')
    return [int(row[1]) for row in csv.reader(io.StringIO(result.stdout.decode(errors='replace')))
            if len(row) >= 2 and row[0].casefold() == 'winword.exe']


def _docx_text(path, require_safe=False):
    with zipfile.ZipFile(path) as package:
        entries = package.infolist()
        if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
            raise ValueError('DOCX excede los límites de lectura.')
        if require_safe:
            if any(any(marker in entry.filename.casefold() for marker in ('vbaproject', '/embeddings/', '/activex/')) for entry in entries):
                raise ValueError('Esta ruta no admite macros, objetos incrustados ni ActiveX.')
            for entry in entries:
                if entry.filename.endswith('.rels'):
                    relationships = ET.fromstring(package.read(entry))
                    if any(node.attrib.get('TargetMode', '').casefold() == 'external' for node in relationships):
                        raise ValueError('Esta ruta no admite vínculos o plantillas externas.')
                elif entry.filename.startswith('word/') and entry.filename.endswith('.xml'):
                    part = ET.fromstring(package.read(entry))
                    if any(node.tag.rsplit('}', 1)[-1] in ('instrText', 'fldSimple', 'altChunk') for node in part.iter()):
                        raise ValueError('Esta ruta no admite campos dinámicos ni contenido externo insertado.')
        document = ET.fromstring(package.read('word/document.xml'))
        if require_safe and any(node.tag.rsplit('}', 1)[-1] in ('instrText', 'fldSimple', 'altChunk') for node in document.iter()):
            raise ValueError('Esta ruta no admite campos dinámicos ni contenido externo insertado.')
        return ''.join(node.text or '' for node in document.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))


def word_data(inputs):
    if not isinstance(inputs, dict) or set(inputs) != {'source', 'destination', 'append_text'}:
        raise ValueError('Indica source, destination y append_text exactos.')
    source = validate_path(inputs['source'])
    if source.suffix.casefold() != '.docx' or source.stat().st_size > 25 * 1024 * 1024:
        raise ValueError('Se requiere DOCX local, sin macros, de hasta 25 MiB.')
    destination = _path(inputs['destination'])
    if destination.is_absolute() or destination.drive or '..' in destination.parts or destination == Path('.'):
        raise ValueError('El destino debe ser una carpeta nueva relativa al espacio autorizado.')
    text = inputs['append_text']
    if not isinstance(text, str) or not text.strip() or len(text) > 16384 or any(ord(char) < 32 and char not in '\r\n\t' for char in text):
        raise ValueError('Añade texto literal no vacío, hasta 16384 caracteres, sin controles ocultos.')
    source_hash = hash_file(str(source), threading.Event())['sha256']
    original_text = _docx_text(source, require_safe=True)
    if len(original_text) > 1000000:
        raise ValueError('El cuerpo del documento excede un millón de caracteres.')
    if hash_file(str(source), threading.Event())['sha256'] != source_hash:
        raise ValueError('El DOCX cambió durante la observación.')
    return {'source': str(source), 'source_sha256': source_hash, 'append_text': text, 'original_text': original_text}


def verify_word_output(directory, data):
    from backend.converter import _pdf
    docx, pdf = Path(directory) / 'document.docx', Path(directory) / 'document.pdf'
    actual = _docx_text(docx, require_safe=True)
    appended = data['append_text'].replace('\r', '').replace('\n', '').replace('\t', '')
    if not actual.startswith(data['original_text']) or not actual.endswith(appended):
        raise ValueError('El DOCX no conserva el cuerpo original y el texto solicitado.')
    if pdf.stat().st_size > 30 * 1024 * 1024:
        raise ValueError('PDF exportado supera 30 MiB.')
    PdfReader, _ = _pdf()
    reader = PdfReader(pdf, strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
        raise ValueError('El PDF debe ser legible, sin cifrado y de hasta 500 páginas.')
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    if ' '.join(data['append_text'].split()) not in ' '.join(text.split()):
        raise ValueError('El PDF no contiene el texto añadido legible.')
    return {'pages': len(reader.pages), 'verification': 'reopened_word_text_and_independent_docx_pdf'}


def _word_worker(request):
    if word_processes():
        raise ValueError('word_busy: cierra Word antes de usar esta ruta; no se tocó ninguna sesión existente')
    import ctypes as C
    from ctypes import wintypes as W
    import pythoncom
    import win32com.client
    from backend.actions.windows_automation import process_name, process_started
    from backend.inference.process_manager import WindowsJobObject
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = document = None
    job = None
    owned = False
    prior_links = None
    prior_security = None
    started = int((time.time() + 11644473600) * 10000000)
    try:
        app = win32com.client.DispatchEx('Word.Application')
        if app.Documents.Count:
            raise ValueError('Word unexpectedly contains documents; existing content was not modified')
        prior_security = app.AutomationSecurity
        app.AutomationSecurity = 3
        document = app.Documents.Add()
        hwnd = document.Windows(1).Hwnd
        user, kernel = C.WinDLL('user32', use_last_error=True), C.WinDLL('kernel32', use_last_error=True)
        user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        pid = W.DWORD()
        user.GetWindowThreadProcessId(W.HWND(hwnd), C.byref(pid))
        birth = process_started(pid.value)
        if not pid.value or process_name(pid.value) != 'winword.exe' or not birth or int(birth) < started or app.Documents.Count != 1:
            raise ValueError('Private Word instance ownership could not be verified')
        owned = True
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        handle = kernel.OpenProcess(0x101, False, pid.value)
        try:
            job = WindowsJobObject()
            if not handle or not job.assign_process(handle):
                raise ValueError('Private Word process could not be supervised for cancellation')
        finally:
            if handle:
                kernel.CloseHandle(handle)
        app.Visible = False
        app.DisplayAlerts = 0
        prior_links = app.Options.UpdateLinksAtOpen
        app.Options.UpdateLinksAtOpen = False
        document.Close(False)
        document = app.Documents.Open(FileName=request['data']['source'], ConfirmConversions=False, ReadOnly=True,
                                      AddToRecentFiles=False, Visible=False, OpenAndRepair=False, NoEncodingDialog=True)
        original = document.Content.Text
        appended = request['data']['append_text'].replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r')
        document.Content.InsertAfter('\r' + appended)
        expected = original[:-1] + '\r' + appended + '\r'
        if document.Content.Text != expected:
            raise ValueError('Word did not append exactly the requested text')
        output = Path(request['output'])
        target, pdf = output / 'document.docx', output / 'document.pdf'
        if target.exists() or pdf.exists():
            raise ValueError('Word staged outputs already exist')
        document.SaveAs2(FileName=str(target), FileFormat=12, AddToRecentFiles=False)
        document.ExportAsFixedFormat(OutputFileName=str(pdf), ExportFormat=17, OpenAfterExport=False)
        document.Close(False)
        document = app.Documents.Open(FileName=str(target), ConfirmConversions=False, ReadOnly=True,
                                      AddToRecentFiles=False, Visible=False, OpenAndRepair=False, NoEncodingDialog=True)
        if document.Content.Text != expected:
            raise ValueError('Reopened DOCX did not preserve exact text')
        return {'success': True, 'application': 'Word', 'version': str(app.Version), 'owned_pid': pid.value,
                'process_started': birth, 'reopened_verified': True}
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if app is not None:
            try:
                if prior_links is not None:
                    app.Options.UpdateLinksAtOpen = prior_links
                if prior_security is not None:
                    app.AutomationSecurity = prior_security
                if owned:
                    app.Quit(False)
            except Exception:
                pass
        document = app = None
        if job:
            job.close()
        pythoncom.CoUninitialize()


class WordPdfTool:
    name, version = 'office_word_pdf', '1.0.0'
    description = 'Append literal text to a new DOCX copy and export a verified PDF, with the original preserved'

    def verify_preconditions(self, inputs):
        try:
            word_data(inputs)
            if word_processes():
                raise ValueError('word_busy: Word ya está abierto; esta ruta requiere una instancia privada')
            import win32com.client
            return True, 'DOCX, new destination and absence of existing Word processes checked'
        except Exception as exc:
            return False, str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False, error='An authorized executor workspace is required')

    def execute_in_workspace(self, inputs, workspace_root):
        return self.execute_cancellable(inputs, workspace_root, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        created, launched, target = [], False, None
        try:
            data = word_data(inputs)
            root = _path(str(workspace_root)).resolve(strict=True)
            target = _path(str(root / inputs['destination']))
            if not target.resolve().is_relative_to(root) or not target.parent.is_dir() or target.exists():
                raise ValueError('La carpeta destino debe ser nueva dentro del espacio autorizado.')
            if cancelled.is_set():
                raise ValueError('Cancelado antes de abrir Word.')
            if word_processes():
                raise ValueError('word_busy: Word ya está abierto; no se modificó ninguna sesión existente')
            with tempfile.TemporaryDirectory(prefix='.office-', dir=root) as folder:
                staging = Path(folder)
                # Only the private copy is opened in Word; the selected original remains untouched.
                working_source = staging / 'source.docx'
                copied = 0
                with Path(data['source']).open('rb') as reader, working_source.open('xb') as writer:
                    while chunk := reader.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > 25 * 1024 * 1024:
                            raise ValueError('El DOCX cambió y excede 25 MiB durante la copia.')
                        if cancelled.is_set():
                            raise ValueError('Cancelado preparando la copia privada.')
                        writer.write(chunk)
                if hash_file(str(working_source), cancelled)['sha256'] != data['source_sha256']:
                    raise ValueError('La copia privada no coincide con el original observado.')
                launched = True
                application = _run_worker({**data, 'source': str(working_source)}, staging, cancelled, operation='word_pdf')
                verification = verify_word_output(staging, data)
                if hash_file(data['source'], cancelled)['sha256'] != data['source_sha256']:
                    raise ValueError('El original cambió; no se publica la exportación.')
                _path(str(target))
                if cancelled.is_set():
                    raise ValueError('Cancelado antes de publicar.')
                target.mkdir()
                created.append(str(target))
                for name in ('document.docx', 'document.pdf'):
                    path = target / name
                    _path(str(path))
                    with (staging / name).open('rb') as reader, path.open('xb') as writer:
                        created.append(str(path))
                        while chunk := reader.read(1024 * 1024):
                            if cancelled.is_set():
                                raise ValueError('Cancelado publicando; se conservan los resultados parciales.')
                            writer.write(chunk)
            verify_word_output(target, data)
            files = [hash_file(str(target / name), cancelled) for name in ('document.docx', 'document.pdf')]
            return ToolResult(True, output={'directory': str(target), 'files': files, **verification, 'source': data['source'],
                                           'source_sha256': data['source_sha256'], 'application': application},
                              evidence={'verification': verification['verification'], 'source_unchanged': True, 'created_paths': created})
        except Exception as exc:
            return ToolResult(False, error=str(exc)[:800], output={'directory': str(target) if created else None}, evidence={
                'cancelled': cancelled.is_set(), 'effect_uncertain': bool(created) or launched, 'partial_effect': bool(created),
                'dispatch_status': 'delivered' if launched else 'rejected', 'effect_status': 'partial' if created else 'not_observed',
                'office_cleanup': 'owned_job_closed; pre_ownership_instance_unconfirmed' if launched else 'not_started',
                'created_paths': created})

    def verify_postconditions(self, inputs, result):
        if not result.success:
            return False, result.error or 'Word export failed'
        try:
            data = word_data(inputs)
            verify_word_output(result.output['directory'], data)
            valid = data['source_sha256'] == result.output['source_sha256'] and all(
                hash_file(row['path'], threading.Event())['sha256'] == row['sha256'] for row in result.output['files'])
            return valid, 'Original, reopened DOCX and PDF independently verified' if valid else 'A file hash changed'
        except Exception as exc:
            return False, str(exc)


if __name__ == '__main__':
    raise SystemExit(worker_main())
