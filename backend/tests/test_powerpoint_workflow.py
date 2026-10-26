import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from backend.actions import powerpoint_workflow as ppt


class PowerPointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.pptx'
        with zipfile.ZipFile(self.source, 'w') as package:
            package.writestr('[Content_Types].xml', '<Types/>')
        self.inputs = {'source':str(self.source),'destination':'output','slide':1,'shape_name':'AxxTitle',
                       'expected_text':'Original Axx','new_text':'Revisión técnica Axx 2026'}

    def test_external_content_and_existing_output_fail_without_launch(self):
        with zipfile.ZipFile(self.source, 'a') as package:
            package.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>')
        with self.assertRaises(ValueError): ppt.checked_input(self.inputs)
        with patch('backend.actions.office_workflows._run_worker') as worker:
            result = ppt.PowerPointTool().execute_cancellable(self.inputs,self.root,threading.Event())
            self.assertFalse(result.success)
            worker.assert_not_called()

    @unittest.skipUnless(os.environ.get('AXX_RUN_OFFICE_FIXTURE') == '1', 'Opt-in real private PowerPoint')
    def test_native_copy_reopen_pdf_and_original_preservation(self):
        self.assertEqual(ppt.powerpoint_processes(), [], 'PowerPoint must be closed for this fixture')
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        app = win32com.client.DispatchEx('PowerPoint.Application')
        deck = None
        try:
            deck = app.Presentations.Add(False)
            slide = deck.Slides.Add(1,12)
            shape = slide.Shapes.AddTextbox(1,40,40,600,100)
            shape.Name = 'AxxTitle'
            shape.TextFrame.TextRange.Text = self.inputs['expected_text']
            self.source.unlink()
            deck.SaveAs(str(self.source),24)
        finally:
            if deck is not None: deck.Close()
            app.Quit()
            shape = slide = deck = app = None
            pythoncom.CoUninitialize()
        for _ in range(40):
            if not ppt.powerpoint_processes(): break
            time.sleep(.25)
        original = self.source.read_bytes()
        tool = ppt.PowerPointTool()
        result = tool.execute_cancellable(self.inputs,self.root,threading.Event())
        self.assertTrue(result.success,result.error)
        self.assertTrue(tool.verify_postconditions(self.inputs,result)[0])
        self.assertEqual(result.output['pages'],1)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertFalse(result.output['visual_layout_verified'])
        again = tool.execute_cancellable(self.inputs,self.root,threading.Event())
        self.assertFalse(again.success)
