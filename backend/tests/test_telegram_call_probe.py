import asyncio
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from backend.telegram.call_probe import block_outgoing, incoming_action, launcher, non_silent, receipt, run_probe, supervise, tone_frame, write_progress


class CallProbeTests(unittest.TestCase):
    def test_only_owner_is_accepted_once(self):
        self.assertEqual(incoming_action(1, 1, None), 'accept')
        self.assertEqual(incoming_action(2, 1, None), 'reject')
        self.assertEqual(incoming_action(1, 1, 1), 'ignore')
        self.assertEqual(incoming_action(2, 1, 1), 'reject')

    def test_pcm_frame_and_energy(self):
        tone = tone_frame(0)
        silence = tone_frame(100)
        self.assertEqual(len(tone), 960)
        self.assertEqual(len(silence), 960)
        self.assertTrue(non_silent(tone))
        self.assertFalse(non_silent(silence))
        self.assertTrue(non_silent(tone_frame(200)))
        self.assertFalse(non_silent(struct.pack('<h', 20) + b'\0'))

    def test_default_receipt_never_claims_live_success(self):
        value = receipt('BLOCKED', 'configuration_missing_or_unreadable')
        self.assertFalse(value['transport_observed'])
        self.assertEqual(value['audible_confirmation'], 'NOT_RUN')
        self.assertNotIn('account_id', value)
        self.assertNotIn('session', value)

    def test_supervisor_requires_child_exit_and_receipt(self):
        def fake_run(command, **kwargs):
            path = Path(command[command.index('--output') + 1])
            path.write_text(json.dumps(receipt('BLOCKED', 'simulated')), encoding='utf-8')
            return types.SimpleNamespace(returncode=2)
        with patch('backend.telegram.call_probe.subprocess.run', side_effect=fake_run):
            value = supervise(1, None)
        self.assertEqual(value['native_cleanup'], 'PROCESS_EXIT_VERIFIED')
        self.assertEqual(value['status'], 'BLOCKED')

    def test_supervisor_marks_timeout_failed(self):
        with patch('backend.telegram.call_probe.subprocess.run', side_effect=subprocess.TimeoutExpired('fake', 1)):
            value = supervise(1, None)
        self.assertEqual(value['native_cleanup'], 'FAILED')
        self.assertEqual(value['reason'], 'child_timeout')

    def test_timeout_keeps_ended_progress_and_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.json'
            progress = receipt('BLOCKED', 'call_not_completed')
            progress.update(media_mode='file', connection_state='ENDED', incoming_frames=3774,
                            incoming_non_silent_frames=782, cleanup_started=True)
            write_progress(path, 'ended', progress)
            with patch('backend.telegram.call_probe.subprocess.run', side_effect=subprocess.TimeoutExpired('fake', 1)):
                value = supervise(1, None, path, 'file')
            observed = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(value['incoming_frames'], 3774)
        self.assertEqual(value['media_mode'], 'file')
        self.assertEqual(observed['state'], 'ended')
        self.assertEqual(observed['reason'], 'child_timeout')
        self.assertTrue(observed['cleanup_started'])

    def test_frozen_and_source_launchers(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(launcher()[1:], ['-m', 'backend.telegram.call_probe'])
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(launcher()[1:], ['--telegram-call-probe'])

    def test_child_crash_is_not_clean_exit(self):
        with patch('backend.telegram.call_probe.subprocess.run', return_value=types.SimpleNamespace(returncode=7)):
            value = supervise(1, None)
        self.assertEqual(value['native_cleanup'], 'FAILED')

    def test_progress_contains_only_safe_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'progress.json'
            data = receipt('BLOCKED', 'example')
            data['session'] = 'private'
            write_progress(path, 'ready', data)
            value = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(value['state'], 'ready')
        self.assertNotIn('session', value)
        self.assertEqual(value['incoming_frames'], 0)


class CallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_outgoing_guard_blocks_before_original_request(self):
        sent = []
        async def original(*args, **kwargs):
            sent.append(True)
        calls = types.SimpleNamespace(_app=types.SimpleNamespace(request_call=original))
        block_outgoing(calls)
        with self.assertRaisesRegex(RuntimeError, 'Outgoing calls are disabled'):
            await calls._app.request_call(20, b'key', object(), False)
        self.assertEqual(sent, [])

    async def test_outgoing_guard_fails_closed_when_api_missing(self):
        with self.assertRaisesRegex(RuntimeError, 'guard unavailable'):
            block_outgoing(types.SimpleNamespace(_app=object()))

    async def test_callbacks_transfer_frames_and_cleanup(self):
        calls_list = []
        clients = []
        filters = types.SimpleNamespace(chat_update=lambda value: value, stream_frame=lambda **kw: 'frames')
        status = types.SimpleNamespace(INCOMING_CALL=1, LEFT_CALL=2, DISCARDED_CALL=2)
        audio_types = types.ModuleType('pytgcalls.types')
        audio_types.ChatUpdate = types.SimpleNamespace(Status=status)
        audio_types.Device = types.SimpleNamespace(MICROPHONE=1)
        audio_types.Direction = types.SimpleNamespace(INCOMING=1)
        audio_types.ExternalMedia = types.SimpleNamespace(AUDIO=1)
        audio_types.MediaStream = lambda *args: args
        audio_types.RecordStream = lambda **kwargs: kwargs
        raw = types.ModuleType('pytgcalls.types.raw')
        raw.AudioParameters = lambda *args: args

        class Client:
            def __init__(self, *args):
                self.disconnected = False
                clients.append(self)

            async def connect(self):
                pass

            async def is_user_authorized(self):
                return True

            async def get_me(self):
                return types.SimpleNamespace(bot=False, id=10)

            async def disconnect(self):
                self.disconnected = True

        class Calls:
            def __init__(self, client):
                self.handlers = {}
                self.frames = []
                self.source_path = None
                self._app = types.SimpleNamespace(request_call=lambda *args: None)
                async def stop(peer):
                    pass
                self._binding = types.SimpleNamespace(stop=stop)
                calls_list.append(self)

            def on_update(self, event):
                def decorate(func):
                    self.handlers[event] = func
                    return func
                return decorate

            async def start(self):
                await self.handlers[1](self, types.SimpleNamespace(chat_id=20))

            async def play(self, peer, source):
                if isinstance(source[0], str):
                    self.source_path = source[0]
                    self.source_exists = Path(self.source_path).is_file()

            async def record(self, *args):
                await self.handlers['frames'](self, types.SimpleNamespace(chat_id=20, frames=[types.SimpleNamespace(frame=tone_frame(0))]))
                async def hangup():
                    await asyncio.sleep(0.06)
                    await self.handlers[2](self, types.SimpleNamespace(chat_id=20, status=2))
                asyncio.create_task(hangup())

            async def send_frame(self, peer, device, frame):
                self.frames.append(frame)

            async def unmute(self, peer):
                return False

            async def resume(self, peer):
                return False

        telethon = types.ModuleType('telethon')
        telethon.TelegramClient = Client
        sessions = types.ModuleType('telethon.sessions')
        sessions.StringSession = lambda value: value
        pytgcalls = types.ModuleType('pytgcalls')
        pytgcalls.PyTgCalls, pytgcalls.filters = Calls, filters
        modules = {'telethon': telethon, 'telethon.sessions': sessions, 'pytgcalls': pytgcalls,
                   'pytgcalls.types': audio_types, 'pytgcalls.types.raw': raw}
        states = []
        with patch.dict(sys.modules, modules):
            value = await run_probe({'session': 'x', 'api_id': 1, 'api_hash': 'x', 'account_id': 10, 'owner_id': 20}, 1, lambda state, data, reason: states.append(state))
        self.assertEqual(value['incoming_non_silent_frames'], 1)
        self.assertGreaterEqual(len(calls_list[0].frames), 2)
        self.assertTrue(all(len(frame) == 960 for frame in calls_list[0].frames))
        self.assertTrue(non_silent(calls_list[0].frames[0]))
        self.assertGreater(value['outgoing_non_silent_frames'], 0)
        self.assertEqual(value['interruption'], 'NOT_RUN')
        self.assertEqual(value['unmute'], 'CALLED')
        self.assertEqual(value['resume'], 'CALLED')
        self.assertTrue(clients[0].disconnected)
        self.assertTrue(value['transport_observed'])
        self.assertEqual(value['status'], 'BLOCKED')
        self.assertEqual(value['native_cleanup'], 'NOT_VERIFIED')
        self.assertIn('ringing', states)
        self.assertIn('active', states)
        self.assertEqual(states[-1], 'ended')
        with patch.dict(sys.modules, modules):
            file_value = await run_probe({'session': 'x', 'api_id': 1, 'api_hash': 'x', 'account_id': 10, 'owner_id': 20}, 1, media_mode='file')
        self.assertTrue(calls_list[-1].source_exists)
        self.assertFalse(Path(calls_list[-1].source_path).exists())
        self.assertEqual(file_value['media_mode'], 'file')
        self.assertEqual(file_value['outgoing_frames'], 0)
        self.assertEqual(file_value['status'], 'BLOCKED')

    async def test_unauthorized_disconnects(self):
        clients = []
        class Client:
            def __init__(self, *args):
                self.disconnected = False
                clients.append(self)
            async def connect(self): pass
            async def is_user_authorized(self): return False
            async def disconnect(self): self.disconnected = True
        telethon = types.ModuleType('telethon')
        telethon.TelegramClient = Client
        sessions = types.ModuleType('telethon.sessions')
        sessions.StringSession = lambda value: value
        pytgcalls = types.ModuleType('pytgcalls')
        pytgcalls.PyTgCalls = object
        pytgcalls.filters = object()
        audio_types = types.ModuleType('pytgcalls.types')
        for name in ('ChatUpdate', 'Device', 'Direction', 'ExternalMedia', 'MediaStream', 'RecordStream'):
            setattr(audio_types, name, object)
        raw = types.ModuleType('pytgcalls.types.raw')
        raw.AudioParameters = object
        modules = {'telethon': telethon, 'telethon.sessions': sessions, 'pytgcalls': pytgcalls,
                   'pytgcalls.types': audio_types, 'pytgcalls.types.raw': raw}
        with patch.dict(sys.modules, modules):
            value = await run_probe({'session': 'x', 'api_id': 1, 'api_hash': 'x'}, 1)
        self.assertEqual(value['reason'], 'authentication_required')
        self.assertTrue(clients[0].disconnected)


if __name__ == '__main__':
    unittest.main()
