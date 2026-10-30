"""Axx's bounded Blender fixture capability using the pinned CLI-Anything adapter.

Only a basename is accepted. No user scene, expression, script, command or blend
file is loaded. The upstream adapter creates a fixed scene/script; the installed
Blender performs the actual render under the existing managed-process boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import threading
import time
import uuid

from backend.inference.process_manager import spawn_managed_process, terminate_process_tree

LOG = logging.getLogger('axx.cli_blender')
UPSTREAM_COMMIT = '34f519533bc175d2fe287ab8316b0dd99bb9cc43'
WIDTH = HEIGHT = 256
RENDER_TIMEOUT = 45.0
MAX_OUTPUT = 8 * 1024 * 1024
MAX_LOG = 512 * 1024
_active = {}
_active_lock = threading.Lock()
_selected_binary = ContextVar('axx_blender_binary', default=None)


def _adapter():
    source_root = Path(__file__).resolve().parents[2] / 'vendor' / 'cli_anything_blender'
    if source_root.is_dir() and str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from cli_anything.blender.core import scene, objects, lighting, render
    return scene, objects, lighting, render


def find_blender() -> Path:
    """Discover an installed application; never execute a user-supplied path."""
    if _selected_binary.get() is not None:
        return Path(_selected_binary.get()['path'])
    if os.name != 'nt':
        raise RuntimeError('This capability requires the installed Windows Blender application')
    bases = [Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Blender Foundation']
    candidates = [p.resolve() for base in bases if base.is_dir() for p in base.glob('Blender */blender.exe') if p.is_file()]
    if not candidates:
        raise RuntimeError('Blender is not installed under Program Files/Blender Foundation')
    def version(path):
        return tuple(int(part) for part in re.findall(r'\d+', path.parent.name))
    return sorted(candidates, key=version, reverse=True)[0]


@contextmanager
def blender_version_lease():
    """Pin the selected executable while its existing Windows file lease is held."""
    if _selected_binary.get() is not None:
        yield
        return
    from .process_runner import _locked_executable
    from .file_inspection import hash_file
    binary = find_blender()
    with _locked_executable(str(binary)):
        token = _selected_binary.set(hash_file(str(binary), threading.Event()))
        try:
            yield
        finally:
            _selected_binary.reset(token)


def blender_binary_snapshot():
    from .file_inspection import hash_file
    bound = _selected_binary.get()
    return dict(bound) if bound is not None else hash_file(str(find_blender()), threading.Event())


def verify_png(path: Path) -> dict:
    size = path.stat().st_size
    if not 64 <= size <= MAX_OUTPUT:
        raise ValueError('Rendered PNG has invalid bounded size')
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
        raise ValueError('Blender output is not a PNG image')
    width, height = struct.unpack('>II', raw[16:24])
    if (width, height) != (WIDTH, HEIGHT) or raw[-12:] != b'\x00\x00\x00\x00IEND\xaeB`\x82':
        raise ValueError('Rendered PNG dimensions or final chunk are invalid')
    return {'path': str(path), 'size': size, 'sha256': hashlib.sha256(raw).hexdigest(), 'width': width, 'height': height}


def cancel_active() -> int:
    """Cancel only fixture render processes started by this capability."""
    with _active_lock:
        processes = list(_active.values())
    for process, job, cancelled in processes:
        cancelled.set()
        terminate_process_tree(process, job)
    return len(processes)


def render_fixture(workspace_root: Path, filename: str) -> dict:
    started = time.monotonic()
    run_id = str(uuid.uuid4())
    process = job = cancelled = None
    try:
        if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.png', filename):
            raise ValueError('filename must be a simple basename ending in .png (up to 84 characters)')
        workspace = Path(workspace_root).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        destination = workspace / filename
        if destination.exists():
            raise FileExistsError('The requested render filename already exists; choose a new name')
        blender = find_blender()
        scene, objects, lighting, render = _adapter()
        project = scene.create_scene(name='Axx CLI-Anything verified fixture', resolution_x=WIDTH, resolution_y=HEIGHT, engine='CYCLES', samples=8)
        objects.add_object(project, mesh_type='cube', name='AxxFixtureCube', location=[0, 0, 0], rotation=[0, 0, 20], scale=[0.8, 0.8, 0.8])
        lighting.add_camera(project, name='AxxFixtureCamera', location=[4, -6, 4], rotation=[63.559, 0, 33.690], focal_length=48, set_active=True)
        lighting.add_light(project, name='AxxFixtureKey', light_type='AREA', location=[2, -3, 5], power=600)
        render.set_render_settings(project, samples=8, use_denoising=False, output_format='PNG')
        run_dir = workspace / '.cli-anything' / run_id
        if not run_dir.resolve().is_relative_to(workspace):
            raise ValueError('CLI-Anything working directory must remain inside the authorized workspace')
        run_dir.mkdir(parents=True, exist_ok=False)
        scene_path = run_dir / 'scene.blend-cli.json'
        scene.save_scene(project, str(scene_path))
        temporary_output = run_dir / 'render.png'
        script = render.generate_bpy_script(project, str(temporary_output), frame=1, animation=False)
        compile(script, '<pinned-cli-anything-generated-fixture>', 'exec')
        script_path = run_dir / 'render.py'
        script_path.write_text(script, encoding='utf-8')
        command = [str(blender), '--background', '--factory-startup', '--disable-autoexec', '--threads', '2', '--python-exit-code', '9', '--python', str(script_path)]
        # Blender needs Windows runtime locations, never inference keys or host tokens.
        runtime_names = {'systemroot', 'windir', 'path', 'temp', 'tmp', 'userprofile', 'appdata', 'localappdata', 'programdata', 'programfiles', 'programfiles(x86)', 'commonprogramfiles', 'comspec', 'number_of_processors', 'processor_architecture'}
        runtime_env = {key: value for key, value in os.environ.items() if key.lower() in runtime_names}
        process, job = spawn_managed_process(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(run_dir), env=runtime_env)
        cancelled, overflow = threading.Event(), threading.Event()
        buffers = [bytearray(), bytearray()]
        def collect(pipe, target):
            try:
                while True:
                    chunk = pipe.read(8192)
                    if not chunk:
                        break
                    if len(target) + len(chunk) > MAX_LOG:
                        overflow.set()
                        break
                    target.extend(chunk)
            finally:
                pipe.close()
        readers = [threading.Thread(target=collect, args=(pipe, target), daemon=True) for pipe, target in zip((process.stdout, process.stderr), buffers)]
        with _active_lock:
            _active[run_id] = (process, job, cancelled)
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + RENDER_TIMEOUT
        try:
            while process.poll() is None:
                if cancelled.is_set():
                    raise RuntimeError('Blender fixture rendering was cancelled')
                if overflow.is_set():
                    raise RuntimeError('Blender output exceeded its bounded log limit')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Blender render exceeded the 45-second capability timeout')
                time.sleep(.025)
            for reader in readers:
                reader.join(timeout=1)
            if cancelled.is_set():
                raise RuntimeError('Blender fixture rendering was cancelled')
            if overflow.is_set():
                raise RuntimeError('Blender output exceeded its bounded log limit')
            stdout, stderr = (bytes(buffer).decode('utf-8', errors='replace') for buffer in buffers)
            (run_dir / 'stdout.log').write_text(stdout, encoding='utf-8')
            (run_dir / 'stderr.log').write_text(stderr, encoding='utf-8')
            if process.returncode != 0:
                raise RuntimeError(f'Blender exited with code {process.returncode}; inspect the capability logs')
            evidence = verify_png(temporary_output)
            # Exclusive creation prevents overwriting a file introduced during rendering.
            with destination.open('xb') as target:
                target.write(temporary_output.read_bytes())
            evidence = verify_png(destination)
            first_line = next((line for line in stdout.splitlines() if line.startswith('Blender ')), 'Blender version not reported')
            evidence.update({'adapter': 'HKUDS/CLI-Anything blender', 'upstream_commit': UPSTREAM_COMMIT, 'application': str(blender), 'application_version': first_line, 'exit_code': process.returncode, 'script_sha256': hashlib.sha256(script_path.read_bytes()).hexdigest(), 'scene_path': str(scene_path), 'logs_directory': str(run_dir), 'duration_ms': round((time.monotonic()-started)*1000, 2), 'method': 'original-adapter-generated-script-plus-real-blender-headless'})
            LOG.info('Blender fixture verified run=%s output=%s sha256=%s', run_id, filename, evidence['sha256'])
            return {'success': True, 'output': dict(evidence), 'error': None, 'evidence': evidence}
        finally:
            with _active_lock:
                _active.pop(run_id, None)
            if process.poll() is None:
                terminate_process_tree(process, job)
            if job:
                job.close()
            for reader in readers:
                reader.join(timeout=1)
    except Exception as exc:
        LOG.warning('Blender fixture failed run=%s error=%s', run_id, exc)
        return {'success': False, 'output': None, 'error': str(exc), 'evidence': {'adapter': 'HKUDS/CLI-Anything blender', 'upstream_commit': UPSTREAM_COMMIT, 'run_id': run_id, 'cancelled': bool(cancelled and cancelled.is_set()), 'duration_ms': round((time.monotonic()-started)*1000, 2)}}
