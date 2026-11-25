"""Actual optional language/debug processes, skipped only when the provider is absent."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.code_studio.projects import CodeProjectService
from backend.code_studio.indexer import CodeStructuralIndexer
from backend.code_studio.language_servers import LanguageServerManager
from backend.code_studio.debug_adapters import DebugAdapterManager, DebugSecurityError


class CodeToolsRealTests(unittest.TestCase):
    @unittest.skipUnless(__import__('os').name=='nt','Windows registered interpreter discovery')
    def test_registered_python_tools_are_discoverable_without_python_on_path(self):
        from backend.code_studio.toolchain import installed_python
        import os
        installed_python.cache_clear()
        try:
            with patch.object(__import__('sys'),'frozen',True,create=True), patch.dict(os.environ,{'PATH':os.environ['SystemRoot']+'\\System32'}):
                self.assertTrue(Path(installed_python('pylsp')).is_file())
                self.assertTrue(Path(installed_python('debugpy')).is_file())
        finally:installed_python.cache_clear()
    @unittest.skipUnless(shutil.which('pylsp') and importlib.util.find_spec('pyflakes'), 'pylsp/pyflakes not installed')
    def test_real_lsp_diagnostic_and_cross_file_definition(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'helpers.py').write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
            text='from helpers import add\nresult = add(2, 3)\nprint(missing_name)\n'
            (root/'main.py').write_text(text,encoding='utf-8')
            projects=CodeProjectService(root/'state.db');projects.register_project('p',str(root))
            lsp=LanguageServerManager(projects,CodeStructuralIndexer(projects))
            try:
                result=lsp.sync_document(project_id='p',language='python',relative_path='main.py',content=text)
                self.assertEqual(result['lsp_status'],'live')
                self.assertTrue(any('missing_name' in d.get('message','') for d in result['diagnostics']),result)
                definition=lsp.query(project_id='p',language='python',relative_path='main.py',method='definition',line=1,character=10)
                self.assertEqual(definition['lsp_status'],'live')
                self.assertTrue(any(x['path']=='helpers.py' for x in definition['result']),definition)
            finally:lsp.close();projects.close()

    @unittest.skipUnless(importlib.util.find_spec('debugpy'), 'debugpy not installed')
    def test_real_dap_breakpoint_stack_locals_step_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);program=root/'calc.py'
            program.write_text('a = 2\nb = 3\nresult = a + b\nprint(result)\n',encoding='utf-8')
            projects=CodeProjectService(root/'state.db');projects.register_project('p',str(root))
            dap=DebugAdapterManager(projects)
            try:
                args=dict(session_id='s',project_id='p',path='calc.py',line=3,
                          expected_sha256=hashlib.sha256(program.read_bytes()).hexdigest())
                with self.assertRaises(DebugSecurityError):dap.launch_python(**args)
                stopped=dap.launch_python(**args,user_approved=True)
                self.assertEqual(stopped['state'],'stopped',stopped)
                self.assertTrue(stopped['breakpoints'][0]['verified'],stopped)
                self.assertEqual(stopped['stack_frames'][0]['line'],3)
                self.assertEqual((stopped['locals']['a'],stopped['locals']['b']),('2','3'))
                stepped=dap.resume('s',step=True)
                self.assertEqual(stepped['locals']['result'],'5')
                self.assertEqual(dap.stop('s')['state'],'terminated')
                self.assertFalse(dap.processes)
            finally:dap.close();projects.close()
