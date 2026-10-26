import csv
import io
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zipfile

from backend.actions import office_workflows as office


def workbook_fixture(path, data, inject_formula=False, wrong_total=False):
    ns = office.NS['s']
    sheet = ET.Element('worksheet', xmlns=ns)
    rows = ET.SubElement(sheet, 'sheetData')
    for index, expected in enumerate(data['rows'], 1):
        row = ET.SubElement(rows, 'row', r=str(index))
        for col, text in enumerate(expected):
            numeric = index > 1 and col == data['numeric_column_index']
            cell = ET.SubElement(row, 'c', r=office._column(col + 1) + str(index), t='n' if numeric else 'inlineStr')
            if numeric:
                ET.SubElement(cell, 'v').text = str(data['numbers'][index - 2])
            else:
                ET.SubElement(ET.SubElement(cell, 'is'), 't').text = text
            if inject_formula and index == 2 and col == 0:
                ET.SubElement(cell, 'f').text = '1+1'
    row = ET.SubElement(rows, 'row', r=str(len(data['rows']) + 1))
    cell = ET.SubElement(row, 'c', r=office._column(data['numeric_column_index'] + 1) + str(len(data['rows']) + 1))
    ET.SubElement(cell, 'f').text = data['formula'][1:]
    ET.SubElement(cell, 'v').text = '999' if wrong_total else data['expected_total']
    with zipfile.ZipFile(path, 'w') as package:
        package.writestr('xl/worksheets/sheet1.xml', ET.tostring(sheet))


class OfficeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.source = self.root / 'input.csv'
        self.source.write_text('Nombre;Importe;Codigo\n=1+1;2.5;001\nSegunda;-0.25;002\n', encoding='utf8')
        self.inputs = {'source': str(self.source), 'destination': 'result.xlsx', 'delimiter': ';', 'numeric_column': 'Importe'}
        self.tool = office.ExcelCsvTool()

    def test_decimal_parser_preserves_text_and_builds_exact_sum(self):
        data = office.csv_data(self.inputs)
        self.assertEqual(data['expected_total'], '2.25')
        self.assertEqual(data['rows'][1][0], '=1+1')
        self.assertEqual(data['rows'][1][2], '001')
        self.assertEqual(data['formula'], '=SUM(B2:B3)')
        path = self.root / 'readback.xlsx'
        workbook_fixture(path, data)
        self.assertEqual(office.verify_xlsx(path, data)['data_rows'], 2)

    def test_ambiguous_numeric_data_is_not_guessed(self):
        for literal in ('1,20', '', '$10', 'NaN', '1e3', '1234567890123456', '0.' + '0'*301 + '1'):
            with self.subTest(literal=literal):
                self.source.write_text('Nombre;Importe\nRow;' + literal + '\n')
                with self.assertRaises(ValueError):
                    office.csv_data(self.inputs)

    def test_external_destination_and_duplicate_headers_rejected(self):
        with self.assertRaises(ValueError):
            office.csv_data({**self.inputs, 'destination': '../outside.xlsx'})
        self.source.write_text('Importe;Importe\n1;2\n')
        with self.assertRaises(ValueError):
            office.csv_data(self.inputs)

    def test_independent_verifier_rejects_formula_injection_and_wrong_total(self):
        data = office.csv_data(self.inputs)
        for options in ({'inject_formula': True}, {'wrong_total': True}):
            with self.subTest(options=options):
                path = self.root / 'bad.xlsx'
                workbook_fixture(path, data, **options)
                with self.assertRaises(ValueError):
                    office.verify_xlsx(path, data)

    def test_cancel_and_existing_target_never_launch_office(self):
        event = threading.Event()
        event.set()
        with patch.object(office, '_run_worker') as worker:
            result = self.tool.execute_cancellable(self.inputs, self.workspace, event)
            self.assertFalse(result.success)
            worker.assert_not_called()
            target = self.workspace / 'result.xlsx'
            target.write_bytes(b'user workbook')
            result = self.tool.execute_cancellable(self.inputs, self.workspace, threading.Event())
            self.assertFalse(result.success)
            self.assertEqual(target.read_bytes(), b'user workbook')
            worker.assert_not_called()

    def test_verified_worker_result_publishes_exclusively_and_preserves_csv(self):
        before = self.source.read_bytes()
        def worker(data, output, cancelled):
            workbook_fixture(output, data)
            return {'reopened_verified': True, 'application': 'Excel fixture'}
        with patch.object(office, '_run_worker', side_effect=worker):
            result = self.tool.execute_cancellable(self.inputs, self.workspace, threading.Event())
        self.assertTrue(result.success, result.error)
        self.assertTrue(self.tool.verify_postconditions(self.inputs, result)[0])
        self.assertEqual(self.source.read_bytes(), before)

    def test_external_race_cannot_overwrite_target(self):
        target = self.workspace / 'result.xlsx'
        def worker(data, output, cancelled):
            workbook_fixture(output, data)
            target.write_bytes(b'racing owner')
            return {'reopened_verified': True}
        with patch.object(office, '_run_worker', side_effect=worker):
            result = self.tool.execute_cancellable(self.inputs, self.workspace, threading.Event())
        self.assertFalse(result.success)
        self.assertEqual(target.read_bytes(), b'racing owner')
        self.assertEqual(result.evidence['created_paths'], [])

    @unittest.skipUnless(os.environ.get('AXX_RUN_OFFICE_FIXTURE') == '1', 'Opt-in real private Excel instance')
    def test_native_excel_reopen_and_independent_verification(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        existing = win32com.client.DispatchEx('Excel.Application')
        book = existing.Workbooks.Add(-4167)
        book.Worksheets(1).Cells(1, 1).Value2 = 'Existing independent workbook'
        try:
            result = self.tool.execute_cancellable(self.inputs, self.workspace, threading.Event())
            self.assertTrue(result.success, result.error)
            self.assertTrue(result.output['application']['reopened_verified'])
            self.assertEqual(result.output['total'], '2.25')
            self.assertTrue(self.tool.verify_postconditions(self.inputs, result)[0])
            self.assertEqual(book.Worksheets(1).Cells(1, 1).Value2, 'Existing independent workbook')
            self.assertEqual(existing.Workbooks.Count, 1)
        finally:
            book.Close(False)
            existing.Quit()
            book = existing = None
            pythoncom.CoUninitialize()


def document_fixture(path, text='Original document.', external=False, dynamic=False):
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    document = ET.Element('w:document', {'xmlns:w': ns})
    paragraph = ET.SubElement(ET.SubElement(document, 'w:body'), 'w:p')
    run = ET.SubElement(paragraph, 'w:r')
    ET.SubElement(run, 'w:t').text = text
    if dynamic:
        ET.SubElement(run, 'w:instrText').text = 'DDEAUTO something'
    with zipfile.ZipFile(path, 'w') as package:
        package.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        package.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        package.writestr('word/document.xml', ET.tostring(document))
        if external:
            package.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId2" TargetMode="External" Target="https://example.invalid"/></Relationships>')


class WordWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.source = self.root / 'input.docx'
        document_fixture(self.source)
        self.inputs = {'source': str(self.source), 'destination': 'result', 'append_text': 'Revision requested.\nSecond line.'}
        self.tool = office.WordPdfTool()

    def test_input_rejects_dynamic_fields_and_external_links(self):
        self.assertEqual(office.word_data(self.inputs)['original_text'], 'Original document.')
        for options in ({'external': True}, {'dynamic': True}):
            document_fixture(self.source, **options)
            with self.assertRaises(ValueError):
                office.word_data(self.inputs)

    def test_cancel_existing_folder_and_busy_word_never_launch_worker(self):
        with patch.object(office, '_run_worker') as worker, patch.object(office, 'word_processes', return_value=[123]):
            result = self.tool.execute_in_workspace(self.inputs, self.workspace)
            self.assertIn('word_busy', result.error)
            event = threading.Event()
            event.set()
            result = self.tool.execute_cancellable(self.inputs, self.workspace, event)
            self.assertTrue(result.evidence['cancelled'])
            target = self.workspace / 'result'
            target.mkdir()
            (target / 'user.txt').write_text('preserved')
            result = self.tool.execute_in_workspace(self.inputs, self.workspace)
            self.assertFalse(result.success)
            self.assertEqual((target / 'user.txt').read_text(), 'preserved')
            worker.assert_not_called()

    def test_worker_timeout_preserves_source_and_does_not_publish(self):
        before = self.source.read_bytes()
        with patch.object(office, 'word_processes', return_value=[]), patch.object(office, '_run_worker', side_effect=TimeoutError('fixture timeout')):
            result = self.tool.execute_in_workspace(self.inputs, self.workspace)
        self.assertFalse(result.success)
        self.assertEqual(result.evidence['created_paths'], [])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_worker_timeout_and_cancel_terminate_only_owned_subprocess(self):
        from backend.inference import process_manager
        for cancel in (False, True):
            process, job = process_manager.spawn_managed_process(
                [sys.executable, '-c', 'import time; time.sleep(30)'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            event = threading.Event()
            if cancel:
                event.set()
            with patch.object(process_manager, 'spawn_managed_process', return_value=(process, job)), patch.object(office, 'OFFICE_TIMEOUT_SECONDS', .15):
                with self.assertRaises(TimeoutError):
                    office._run_worker({}, self.workspace, event, operation='word_pdf')
            self.assertIsNotNone(process.poll())

    def test_partial_publication_is_retained_and_reported(self):
        def worker(data, output, cancelled, operation):
            (output / 'document.docx').write_bytes(b'docx staged fixture')
            (output / 'document.pdf').write_bytes(b'pdf staged fixture')
            return {'reopened_verified': True}
        real_open = Path.open
        def controlled_open(path, *args, **kwargs):
            if path == self.workspace / 'result/document.pdf' and args == ('xb',):
                raise OSError('fixture disk failure')
            return real_open(path, *args, **kwargs)
        with patch.object(office, 'word_processes', return_value=[]), patch.object(office, '_run_worker', side_effect=worker), patch.object(office, 'verify_word_output', return_value={'pages': 1, 'verification': 'fixture'}), patch.object(Path, 'open', controlled_open):
            result = self.tool.execute_in_workspace(self.inputs, self.workspace)
        self.assertFalse(result.success)
        self.assertTrue(result.evidence['partial_effect'])
        self.assertTrue(result.evidence['effect_uncertain'])
        self.assertEqual((self.workspace / 'result/document.docx').read_bytes(), b'docx staged fixture')
        self.assertFalse((self.workspace / 'result/document.pdf').exists())

    @unittest.skipUnless(os.environ.get('AXX_RUN_OFFICE_FIXTURE') == '1', 'Opt-in real private Word instance')
    def test_native_word_reopen_pdf_and_existing_instance_preservation(self):
        self.assertEqual(office.word_processes(), [], 'Native fixture requires Word closed')
        before = self.source.read_bytes()
        result = self.tool.execute_in_workspace(self.inputs, self.workspace)
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.output['application']['reopened_verified'])
        self.assertGreater(result.output['pages'], 0)
        self.assertTrue(self.tool.verify_postconditions(self.inputs, result)[0])
        self.assertEqual(self.source.read_bytes(), before)
        for _ in range(20):
            if not office.word_processes():
                break
            time.sleep(.25)
        self.assertEqual(office.word_processes(), [])
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        existing = win32com.client.DispatchEx('Word.Application')
        doc = existing.Documents.Add()
        doc.Content.Text = 'Independent Word fixture'
        try:
            result = self.tool.execute_in_workspace({**self.inputs, 'destination': 'other'}, self.workspace)
            self.assertFalse(result.success)
            self.assertIn('word_busy', result.error)
            self.assertEqual(doc.Content.Text, 'Independent Word fixture\r')
            self.assertEqual(existing.Documents.Count, 1)
        finally:
            doc.Close(False)
            existing.Quit(False)
            doc = existing = None
            pythoncom.CoUninitialize()


if __name__ == '__main__':
    unittest.main()
