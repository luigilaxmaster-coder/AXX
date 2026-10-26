import tempfile
import threading
import unittest
from pathlib import Path

from backend.actions.artifact_verification import ArtifactInspectTool, inspect_pdf, run_inspector
from backend.actions.executor import ActionExecutor


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pdf(self, name='sheet.pdf', encrypted=False):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=841.89, height=1190.55)
        if encrypted:
            writer.encrypt('private')
        target = self.root / name
        with target.open('wb') as stream:
            writer.write(stream)
        return target

    def test_pdf_dimensions_hash_and_worker(self):
        path = self.pdf()
        result = run_inspector('pdf', str(path))
        self.assertEqual(result['page_count'], 1)
        self.assertAlmostEqual(result['pages'][0]['width_pt'], 841.89)
        self.assertEqual(len(result['sha256']), 64)
        self.assertFalse(result['visual_render_verified'])

    def test_executor_registers_real_pdf_evidence(self):
        with ActionExecutor(self.root / 'state.db', self.root) as executor:
            result = executor.execute_action('artifact_pdf', {'path': str(self.pdf())})
            self.assertTrue(result['postconditions_passed'], result)
            self.assertEqual(result['state'], 'succeeded')

    def test_encrypted_broken_and_non_pdf_rejected(self):
        with self.assertRaises(ValueError):
            inspect_pdf(str(self.pdf('locked.pdf', True)))
        target = self.root / 'bad.pdf'
        for data in (b'<html>login</html>', b'%PDF-1.7\nbroken'):
            target.write_bytes(data)
            self.assertFalse(ArtifactInspectTool('pdf').execute({'path': str(target)}).success)

    def test_cancelled_before_read_and_unknown_fields(self):
        event = threading.Event(); event.set()
        tool = ArtifactInspectTool('pdf')
        path = str(self.pdf())
        self.assertFalse(tool.execute_cancellable({'path': path}, self.root, event).success)
        self.assertFalse(tool.verify_preconditions({'path': path, 'script': 'x'})[0])

    def test_changed_file_invalidates_postcondition(self):
        path = self.pdf()
        tool = ArtifactInspectTool('pdf')
        result = tool.execute({'path': str(path)})
        self.assertTrue(result.success)
        path.write_bytes(b'changed')
        self.assertFalse(tool.verify_postconditions({'path': str(path)}, result)[0])


if __name__ == '__main__':
    unittest.main()
