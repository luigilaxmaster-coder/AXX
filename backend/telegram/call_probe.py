"""Isolated private-call transport probe; this is not the Axx call integration."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import time
import wave


def receipt(status: str, reason: str) -> dict:
    return {
        'status': status, 'reason': reason,
        'transport_observed': False, 'audible_confirmation': 'NOT_RUN',
        'incoming_frames': 0, 'incoming_non_silent_frames': 0,
        'outgoing_frames': 0, 'outgoing_non_silent_frames': 0,
        'connection_state': 'NOT_CONNECTED', 'remote_hangup_observed': False,
        'cleanup': 'NOT_RUN', 'native_cleanup': 'NOT_VERIFIED',
        'cleanup_started': False, 'disconnect_done': False, 'native_stop': 'NOT_RUN',
        'interruption': 'NOT_RUN',
        'media_mode': 'external', 'source_attached': False, 'playout_candidate': False, 'unmute': 'NOT_RUN', 'resume': 'NOT_RUN',
        'environment': {'python': platform.python_version(), 'platform': platform.system(), 'architecture': platform.machine()},
        'native_import_probe': 'NOT_RUN',
    }


def non_silent(data: bytes) -> bool:
    size = len(data) - len(data) % 2
    return bool(size and any(abs(sample[0]) > 100 for sample in struct.iter_unpack('<h', data[:size])))


def tone_frame(index: int) -> bytes:
    # Repeated one-second tone and silence, 10 ms frames, 48 kHz mono s16le.
    return struct.pack('<480h', *(int(4000 * math.sin(2 * math.pi * 440 * (index * 480 + n) / 48000)) if index % 200 < 100 else 0 for n in range(480)))


def incoming_action(peer: int, owner: int, active: int | None) -> str:
    if active == peer:
        return 'ignore'
    return 'accept' if peer == owner and active is None else 'reject'


def block_outgoing(calls):
    # PyTgCalls 3.0.0 uses this MTProto method when incoming state is lost.
    app = calls._app
    if not callable(getattr(app, 'request_call', None)):
        raise RuntimeError('Outgoing call guard unavailable')

    async def deny(*args, **kwargs):
        raise RuntimeError('Outgoing calls are disabled')

    app.request_call = deny
    if app.request_call is not deny:
        raise RuntimeError('Outgoing call guard unavailable')


def launcher() -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--telegram-call-probe']
    return [sys.executable, '-m', 'backend.telegram.call_probe']


def native_import_probe() -> tuple[str, dict]:
    try:
        result = subprocess.run(launcher() + ['--native-import-check'], capture_output=True, text=True,
                                timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode == 0:
            return 'PASS', json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return 'UNAVAILABLE', {}


def write_progress(path: Path | None, state: str, result: dict | None = None, reason: str = '') -> None:
    if path is None:
        return
    value = {'state': state, 'reason': reason}
    if result is not None:
        value.update({key: result[key] for key in ('incoming_frames', 'incoming_non_silent_frames', 'outgoing_frames', 'outgoing_non_silent_frames', 'connection_state', 'media_mode', 'source_attached', 'unmute', 'resume', 'cleanup_started', 'disconnect_done', 'native_stop')})
    name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(value, stream)
        os.replace(name, path)
    except OSError:
        if name:
            try:
                os.unlink(name)
            except OSError:
                pass


def supervise(timeout: int, data_dir: Path | None, progress_file: Path | None = None, media_mode: str = 'external') -> dict:
    with tempfile.TemporaryDirectory(prefix='axx-telegram-call-') as directory:
        output = Path(directory) / 'result.json'
        command = launcher() + ['--child',
                   '--output', str(output), '--timeout', str(timeout), '--media', media_mode]
        if data_dir is not None:
            command.extend(['--data-dir', str(data_dir)])
        if progress_file is not None:
            command.extend(['--progress-file', str(progress_file)])
        try:
            child = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=timeout + 30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            value = receipt('BLOCKED', 'child_timeout')
            value['native_cleanup'] = 'FAILED'
            value['media_mode'] = media_mode
            counters = ('incoming_frames', 'incoming_non_silent_frames', 'outgoing_frames', 'outgoing_non_silent_frames')
            for key in counters:
                value[key] = None
            try:
                if progress_file is not None and progress_file.stat().st_size <= 16384:
                    last = json.loads(progress_file.read_text(encoding='utf-8'))
                    for key in counters:
                        if type(last.get(key)) is int and last[key] >= 0:
                            value[key] = last[key]
                    for key in ('connection_state', 'media_mode', 'source_attached', 'unmute', 'resume', 'cleanup_started', 'disconnect_done', 'native_stop'):
                        if key in last and type(last[key]) is type(value[key]):
                            value[key] = last[key]
                    state = last.get('state') if last.get('state') in ('ended', 'active', 'ringing', 'ready', 'starting') else 'timeout'
                else:
                    state = 'timeout'
            except (OSError, ValueError, AttributeError):
                state = 'timeout'
            write_progress(progress_file, state, value, 'child_timeout')
            return value
        except OSError:
            write_progress(progress_file, 'error', reason='child_start_failed')
            return receipt('BLOCKED', 'child_start_failed')
        try:
            if output.stat().st_size > 16384:
                raise ValueError('receipt too large')
            value = json.loads(output.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or child.returncode not in (0, 2)
                    or not receipt('BLOCKED', '').keys() <= value.keys()):
                raise ValueError('invalid child result')
        except (OSError, ValueError):
            value = receipt('BLOCKED', 'child_receipt_unavailable')
            write_progress(progress_file, 'error', value, 'child_receipt_unavailable')
        value['native_cleanup'] = 'PROCESS_EXIT_VERIFIED' if child.returncode in (0, 2) else 'FAILED'
        value['status'] = 'BLOCKED'
        return value


async def run_probe(account: dict, timeout: int, progress=None, media_mode='external') -> dict:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from pytgcalls import PyTgCalls, filters
    from pytgcalls.types import ChatUpdate, Device, Direction, ExternalMedia, MediaStream, RecordStream
    from pytgcalls.types.raw import AudioParameters

    result = receipt('BLOCKED', 'call_not_completed')
    result['media_mode'] = media_mode
    temp_audio = None
    client = TelegramClient(StringSession(account['session']), account['api_id'], account['api_hash'])
    calls = None
    active = None
    connected = False
    ended = asyncio.Event()
    stop_audio = asyncio.Event()
    tasks: set[asyncio.Task] = set()
    last_update = 0.0

    def emit(state: str, reason: str = ''):
        if progress:
            progress(state, result, reason)

    async def stream_audio(peer: int):
        nonlocal last_update
        index = 0
        while not stop_audio.is_set():
            await calls.send_frame(peer, Device.MICROPHONE, tone_frame(index))
            if index % 200 < 100:
                result['outgoing_non_silent_frames'] += 1
            result['outgoing_frames'] += 1
            index += 1
            if not stop_audio.is_set() and time.monotonic() - last_update >= 1:
                last_update = time.monotonic()
                emit('active')
            await asyncio.sleep(0.01)

    async def accept(peer: int):
        nonlocal active, connected
        action = incoming_action(peer, account['owner_id'], active)
        if action == 'ignore':
            return
        if action == 'reject':
            try:
                await calls.leave_call(peer)
            except Exception:
                pass
            return
        active = peer
        emit('ringing')
        try:
            audio = AudioParameters(48000, 1)
            source = str(temp_audio.name) if temp_audio else ExternalMedia.AUDIO
            await calls.play(peer, MediaStream(source, audio))
            result['source_attached'] = True
            connected = True
            result['connection_state'] = 'CONNECTED'
            await calls.record(peer, RecordStream(audio=True, audio_parameters=audio))
            await calls.unmute(peer)
            result['unmute'] = 'CALLED'
            await calls.resume(peer)
            result['resume'] = 'CALLED'
            emit('active')
            if media_mode == 'external':
                await stream_audio(peer)
            else:
                await stop_audio.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            result['reason'] = 'call_transport_error'
            emit('error', 'call_transport_error')
            ended.set()

    try:
        if media_mode == 'file':
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio.close()
            with wave.open(temp_audio.name, 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48000)
                cycle = b''.join(tone_frame(index) for index in range(200))
                for _ in range((timeout + 6) // 2 + 1):
                    output.writeframesraw(cycle)
        await client.connect()
        if not await client.is_user_authorized():
            result['reason'] = 'authentication_required'
            emit('error', result['reason'])
            return result
        me = await client.get_me()
        if not me or me.bot or me.id != account['account_id']:
            result['reason'] = 'account_mismatch'
            emit('error', result['reason'])
            return result
        calls = PyTgCalls(client)
        block_outgoing(calls)

        @calls.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def incoming(_, update):
            task = asyncio.create_task(accept(update.chat_id))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        @calls.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def left(_, update):
            if update.chat_id == active:
                result['remote_hangup_observed'] = bool(connected and update.status & ChatUpdate.Status.DISCARDED_CALL)
                result['connection_state'] = 'ENDED'
                stop_audio.set()
                ended.set()
                emit('ended')

        @calls.on_update(filters.stream_frame(directions=Direction.INCOMING, devices=Device.MICROPHONE))
        async def frames(_, update):
            if update.chat_id == active and connected:
                for frame in update.frames:
                    result['incoming_frames'] += 1
                    speech = non_silent(frame.frame)
                    result['incoming_non_silent_frames'] += int(speech)

        await calls.start()
        if active is None and not ended.is_set():
            emit('ready')
        try:
            await asyncio.wait_for(ended.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            result['reason'] = 'timeout'
            emit('timeout', 'timeout')
    finally:
        result['cleanup_started'] = True
        emit('ended' if result['connection_state'] == 'ENDED' else 'cleanup')
        stop_audio.set()
        for task in list(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*list(tasks), return_exceptions=True)
        clean = True
        if calls and active is not None and not result['remote_hangup_observed']:
            try:
                await asyncio.wait_for(calls.leave_call(active), timeout=5)
            except Exception:
                clean = False
        if calls and active is not None and result['remote_hangup_observed']:
            try:
                await asyncio.wait_for(calls._binding.stop(active), timeout=5)
                result['native_stop'] = 'STOPPED'
            except Exception as exc:
                if type(exc).__name__ == 'ConnectionNotFound':
                    result['native_stop'] = 'ALREADY_STOPPED'
                else:
                    result['native_stop'] = 'FAILED'
                    clean = False
            emit('ended')
        try:
            await asyncio.wait_for(client.disconnect(), timeout=5)
            result['disconnect_done'] = True
        except Exception:
            clean = False
        emit('ended' if result['connection_state'] == 'ENDED' else 'cleanup')
        if temp_audio:
            try:
                os.unlink(temp_audio.name)
            except OSError:
                clean = False
        result['cleanup'] = 'PASS' if clean else 'FAILED'
        result['playout_candidate'] = bool(result['incoming_non_silent_frames'] and result['source_attached'] and result['remote_hangup_observed'] and clean)
        result['transport_observed'] = bool(result['playout_candidate'] and media_mode == 'external' and result['outgoing_non_silent_frames'])
        if result['playout_candidate']:
            result['reason'] = 'audible_confirmation_required'
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--data-dir', type=Path, help='Axx data directory; defaults to LOCALAPPDATA/Axx')
    parser.add_argument('--progress-file', type=Path)
    parser.add_argument('--media', choices=('external', 'file'), default='external')
    parser.add_argument('--timeout', type=int, default=180, choices=range(1, 181), metavar='1..180')
    parser.add_argument('--confirm-audible', action='store_true', help='Ask locally after the call whether the tone was heard')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--native-import-check', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.native_import_check:
        try:
            import importlib.metadata
            import ntgcalls
            instance = ntgcalls.NTgCalls()
            del instance
            print(json.dumps({name: importlib.metadata.version(name) for name in ('telethon', 'py-tgcalls', 'ntgcalls')}))
            return 0
        except Exception:
            return 2
    if args.output is None:
        parser.error('--output is required')
    if not args.child:
        write_progress(args.progress_file, 'starting')
        result = supervise(args.timeout, args.data_dir, args.progress_file, args.media)
        native_status, versions = native_import_probe()
        result['native_import_probe'] = native_status
        result['environment']['versions'] = versions
        if args.confirm_audible and result['playout_candidate'] and sys.stdin.isatty():
            answer = input('¿Escuchó el tono de prueba en Telegram? Escriba SI: ').strip()
            result['audible_confirmation'] = 'PASS' if answer == 'SI' else 'FAILED'
            if (answer == 'SI' and result['remote_hangup_observed'] and result['cleanup'] == 'PASS'
                    and result['native_cleanup'] == 'PROCESS_EXIT_VERIFIED'):
                result['status'] = 'PASS'
                result['transport_observed'] = True
                result['reason'] = 'transport_confirmed_locally'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else 2

    result = receipt('BLOCKED', 'configuration_missing_or_unreadable')
    write_progress(args.progress_file, 'starting')
    try:
        from backend.telegram.config import account_lease, load_account
        data_dir = args.data_dir or Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Axx'
        account = load_account(data_dir)
        if not account or not account.get('enabled') or not account.get('grants', {}).get('private_calls'):
            result['reason'] = 'channel_or_calls_disabled'
        elif not all(account.get(key) for key in ('api_id', 'api_hash', 'session', 'account_id', 'owner_id')):
            result['reason'] = 'configuration_incomplete'
        else:
            try:
                with account_lease(data_dir):
                    result = asyncio.run(asyncio.wait_for(run_probe(account, args.timeout, lambda state, data, reason: write_progress(args.progress_file, state, data, reason), args.media), timeout=args.timeout + 15))
            except ImportError:
                result['reason'] = 'dependencies_unavailable'
            except TimeoutError:
                result['reason'] = 'timeout'
            except RuntimeError as exc:
                result['reason'] = 'session_in_use' if str(exc) == 'TELEGRAM_SESSION_IN_USE' else 'probe_error'
            except Exception:
                result['reason'] = 'probe_error'
    except (ImportError, OSError, ValueError, KeyError, RuntimeError):
        pass
    if result['reason'] in ('configuration_missing_or_unreadable', 'channel_or_calls_disabled', 'configuration_incomplete', 'dependencies_unavailable', 'session_in_use', 'probe_error', 'timeout'):
        write_progress(args.progress_file, 'timeout' if result['reason'] == 'timeout' else 'error', result, result['reason'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
