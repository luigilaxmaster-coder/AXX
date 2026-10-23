"""Contract tests; native installed acceptance is recorded separately."""
from contextlib import nullcontext
import hashlib
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.actions.application_flows import execute_flow, validate_flow
from backend.actions.executor import ActionExecutor
from backend.actions.windows_automation import UncertainEffect
from backend.commands import CommandService, ApprovalRequired
from backend.mobile.control import AutomationLease


class ApplicationFlowTests(unittest.TestCase):
    def test_typed_paths_and_literal_text(self):
        for path in ('https://example.com', r'\\server\share', r'C:\x\..\y', r'\\.\C:', 'C:\\x\x00'):
            with self.assertRaises(ValueError): validate_flow('explorer_folder', {'path': path})
        validate_flow('explorer_folder', {'path': r'C:\Users'})
        validate_flow('notepad_text', {'window_title':'scratch - Notepad','value':'$(whoami) & echo data'})
        with self.assertRaises(ValueError): validate_flow('notepad_text', {'window_title':'scratch','value':'a','window_id':123})

    def test_physical_cancel_cannot_be_cleared_by_new_owner(self):
        native=SimpleNamespace(abort=threading.Event(),lease='first')
        lease=AutomationLease(native,'first',threading.Event())
        self.assertFalse(lease.is_set())
        native.lease='second'
        self.assertTrue(lease.is_set())

    def test_replay_resolves_new_window_and_editor(self):
        event=threading.Event(); calls=[]
        for hwnd in (123,456):
            row={'window_id':hwnd,'pid':10,'title':'scratch - Notepad','foreground':True}
            editor={'control_type':'ControlType.Document','control_id':str(hwnd),'enabled':True,'offscreen':False,'supports_value_pattern':True}
            with patch('backend.actions.windows_automation.list_windows',return_value=[row]), \
                 patch('backend.actions.windows_automation.process_name',return_value='notepad.exe'), \
                 patch('backend.actions.windows_automation.focus_window'), \
                 patch('backend.actions.windows_automation.inspect_controls',return_value={'controls':[editor],'truncated':False}), \
                 patch('backend.actions.windows_automation._uia',side_effect=lambda payload,**kw: calls.append(payload) or {'verification':'uia_value_readback','value_sha256':hashlib.sha256(b'text').hexdigest(),'value_length':4}):
                result=execute_flow('notepad_text',{'window_title':row['title'],'value':'text'},event)
                self.assertEqual(result['evidence']['window_id'],hwnd)
        self.assertEqual([c['window_id'] for c in calls],[123,456])
        self.assertNotEqual(calls[0]['control_id'],calls[1]['control_id'])

    def test_ambiguous_windows_never_write(self):
        row={'window_id':1,'pid':10,'title':'scratch'}
        with patch('backend.actions.windows_automation.list_windows',return_value=[row,row]), \
             patch('backend.actions.windows_automation.process_name',return_value='notepad.exe'), \
             patch('backend.actions.windows_automation._uia') as worker:
            with self.assertRaises(ValueError): execute_flow('notepad_text',{'window_title':'scratch','value':'a'},threading.Event())
            worker.assert_not_called()

    def test_approval_unknown_and_idempotent_no_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            executor=ActionExecutor(Path(directory)/'state.db'); commands=CommandService(executor)
            executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(event))
            try:
                pending=commands.prepare('axx.desktop.notepad.text',{'window_title':'scratch','value':'a'})
                with self.assertRaises(ApprovalRequired):commands.execute(pending['operation_id'])
                error=UncertainEffect('timeout');error.target={'window_id':1,'pid':2,'control_id':'a'*64}
                with patch('backend.actions.application_flows.execute_flow',side_effect=error) as write:
                    result=commands.execute(pending['operation_id'],True)
                    self.assertEqual(result['state'],'unknown')
                    self.assertTrue(result['evidence']['reconciliation_required'])
                    again=commands.execute(pending['operation_id'],True)
                    self.assertEqual(again['state'],'unknown');write.assert_called_once()
                with self.assertRaisesRegex(ValueError,'incierta'):
                    commands.prepare('axx.desktop.notepad.text',{'window_title':'scratch','value':'different'})
                with patch('backend.actions.windows_automation._uia',return_value={'value_sha256':hashlib.sha256(b'a').hexdigest(),'value_length':1}) as inspect:
                    reconciled=commands.reconcile(pending['operation_id'])
                    self.assertEqual(reconciled['state'],'succeeded')
                    self.assertEqual(inspect.call_args.args[0]['operation'],'check_value')
                self.assertEqual(commands.execute(pending['operation_id'],True)['state'],'succeeded')
            finally:commands.close();executor.close()

    def test_missing_owner_fails_closed(self):
        from backend.actions.tools import get_tool
        result=get_tool('desktop_notepad_text').execute_cancellable({'window_title':'scratch','value':'a'},None,threading.Event())
        self.assertFalse(result.success)
        self.assertIn('dueño',result.error)
