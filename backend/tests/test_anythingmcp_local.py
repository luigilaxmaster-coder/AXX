import importlib.util
import os
import json
import subprocess
import threading
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock, MagicMock

spec = importlib.util.spec_from_file_location('anythingmcp_local', Path(__file__).resolve().parents[2]/'scripts'/'anythingmcp-local.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class LocalGatewayTests(unittest.TestCase):
    def test_resume_only_starts_existing_stack_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);local.prepare(root);local.remember_runtime(root,'Ubuntu-24.04',True)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            first=Mock(returncode=0);first.communicate.return_value=(b'/mnt/c/private',None)
            second=Mock(returncode=0);second.communicate.return_value=(b'',None)
            opener=MagicMock();opener.open.return_value.__enter__.return_value.status=200
            with patch.object(local.shutil,'which',return_value='wsl.exe'), patch.object(local,'wsl_keeper') as keeper, \
                    patch('backend.inference.process_manager.spawn_managed_process',side_effect=[(first,None),(second,None)]) as spawn, \
                    patch.object(local.urllib.request,'build_opener',return_value=opener), \
                    patch('backend.inference.process_manager.terminate_process_tree'):
                local.resume(root)
            command=spawn.call_args_list[-1].args[0]
            self.assertEqual(command[-1],'start')
            self.assertNotIn('--wait',command)
            self.assertNotIn('up',command);self.assertNotIn('pull',command)
            keeper.assert_called_once_with(root,'Ubuntu-24.04')
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_resume_rejects_disabled_missing_changed_or_cancelled_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);local.prepare(root)
            with self.assertRaises(ValueError):local.resume(root)
            local.remember_runtime(root,'Ubuntu-24.04',False)
            with self.assertRaisesRegex(ValueError,'detenida'):local.resume(root)
            local.remember_runtime(root,'Ubuntu-24.04;other',True)
            with self.assertRaisesRegex(ValueError,'distribución'):local.resume(root)
            local.remember_runtime(root,None,True)
            with patch.object(local.shutil,'which',return_value='docker.exe'), \
                    patch('backend.inference.process_manager.spawn_managed_process') as spawn:
                stop=threading.Event();stop.set()
                with self.assertRaisesRegex(ValueError,'cancelado'):local.resume(root,stop)
                spawn.assert_not_called()
            (root/'compose.json').write_text(json.dumps({'services':{}}))
            with self.assertRaisesRegex(ValueError,'cambió'):local.resume(root)

    def test_cancelled_startup_terminates_only_its_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);local.prepare(root);local.remember_runtime(root,None,True)
            stop=threading.Event();process=Mock()
            def pending(**kwargs):
                stop.set();raise subprocess.TimeoutExpired('docker',.1)
            process.communicate.side_effect=pending
            with patch.object(local.shutil,'which',return_value='docker.exe'), \
                    patch('backend.inference.process_manager.spawn_managed_process',return_value=(process,'owned-job')), \
                    patch('backend.inference.process_manager.terminate_process_tree') as terminate:
                with self.assertRaisesRegex(ValueError,'cancelado'):local.resume(root,stop)
                terminate.assert_called_once_with(process,'owned-job')

    def test_preparation_preserves_keys_and_loopback_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'private'
            local.prepare(root)
            original = (root/'.env').read_bytes()
            local.prepare(root)
            self.assertEqual(original, (root/'.env').read_bytes())
            data = local.compose()
            self.assertTrue(all('@sha256:' in item['image'] for item in data['services'].values()))
            self.assertTrue(all(item.startswith('127.0.0.1:') for item in data['services']['app']['ports']))
            self.assertNotIn('ports', data['services']['postgres'])
            self.assertEqual(data['services']['app']['environment']['MCP_ALLOW_ANONYMOUS'], 'false')
            self.assertNotIn(original.splitlines()[0].split(b'=')[1].decode(), str(data))
            with patch.object(local.shutil, 'which', return_value=None):
                self.assertFalse(local.preflight(root)['ready_to_start'])

    def test_existing_invalid_secret_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.env').write_text('ENCRYPTION_KEY=existing-data')
            with self.assertRaises(ValueError): local.prepare(root)
            self.assertEqual((root/'.env').read_text(), 'ENCRYPTION_KEY=existing-data')
