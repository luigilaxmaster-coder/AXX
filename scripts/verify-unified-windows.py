"""Real native UIA/SQLite acceptance on a disposable WPF application.

Run from repository root: python scripts/verify-unified-windows.py.
No provider calls, user documents, credentials, or global input are used.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.actions.executor import ActionExecutor
from backend.actions.windows_automation import list_windows
from backend.commands import CommandService


def main():
    if os.name != 'nt':
        raise RuntimeError('Windows native acceptance requires Windows')
    evidence = Path('build/unified-native')
    evidence.mkdir(parents=True, exist_ok=True)
    executable = evidence.resolve() / 'UnifiedControl.exe'
    csc = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    references = ['/reference:' + str(csc.parent / 'WPF' / (name + '.dll'))
                  for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase')]
    subprocess.run([str(csc), '/nologo', '/target:winexe', '/out:' + str(executable),
                    '/reference:' + str(csc.parent / 'System.Xaml.dll'), *references,
                    str(Path(__file__).with_name('fixtures') / 'UnifiedControl.cs')], check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    child = subprocess.Popen([str(executable)], creationflags=subprocess.CREATE_NO_WINDOW)
    report = {'kind':'NATIVE_FIXTURE_ACCEPTANCE', 'operations':[], 'not_tested':['physical typing', '1000-operation background stress', 'VLM', 'Cua', 'REA', 'VM']}
    try:
        deadline = time.monotonic() + 10
        window = None
        while window is None and time.monotonic() < deadline:
            window = next((item for item in list_windows() if item['pid'] == child.pid), None)
            time.sleep(.1)
        assert window, 'Native fixture did not expose a window'
        with tempfile.TemporaryDirectory() as directory:
            with ActionExecutor(Path(directory) / 'state.db', Path(directory) / 'artifacts') as executor:
                commands = CommandService(executor)
                try:
                    def run(command, inputs):
                        pending = commands.prepare(command, inputs, delivery_mode='background')
                        result = commands.execute(pending['operation_id'], approved=True)
                        report['operations'].append(result)
                        assert result['state'] == 'succeeded', result
                        return result
                    identity = {'window_id':hex(window['window_id']), 'pid':child.pid}
                    user = ctypes.WinDLL('user32', use_last_error=True)
                    user.GetForegroundWindow.restype = wintypes.HWND
                    user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
                    user.GetClipboardSequenceNumber.restype = wintypes.DWORD
                    def snapshot():
                        point = wintypes.POINT()
                        if not user.GetCursorPos(ctypes.byref(point)):
                            raise ctypes.WinError(ctypes.get_last_error())
                        return [int(user.GetForegroundWindow() or 0), point.x, point.y, user.GetClipboardSequenceNumber()]
                    samples = [snapshot()]
                    stop = threading.Event()
                    def monitor():
                        while not stop.wait(.01):
                            samples.append(snapshot())
                    watcher = threading.Thread(target=monitor)
                    watcher.start()
                    try:
                        process = run('axx.process.inspect', {'pid':child.pid})
                        observed = run('axx.desktop.window.inspect', identity)
                        assert observed['output']['observation']['process_started'] == process['output']['process_started']
                        assert observed['output']['observation']['screenshot'] is None
                        for name, status in [('Confirmar','selected'), ('Duplicado','ambiguous'), ('Ausente','not_found')]:
                            result = run('axx.desktop.window.find', identity | {'name':name})
                            assert result['output']['selection_status'] == status, result
                        written = run('axx.artifact.write', {'path':'acceptance.txt', 'content':'Axx background verification'})
                        assert written['effect_status'] == 'confirmed'
                        assert (Path(directory) / 'artifacts/acceptance.txt').read_text() == 'Axx background verification'
                    finally:
                        stop.set()
                        watcher.join(2)
                    samples.append(snapshot())
                    report['non_interference'] = {'samples':len(samples), 'interval_ms':10,
                        'focus_changes':sum(a[0] != b[0] for a,b in zip(samples,samples[1:])),
                        'pointer_changes':sum(a[1:3] != b[1:3] for a,b in zip(samples,samples[1:])),
                        'clipboard_changes':sum(a[3] != b[3] for a,b in zip(samples,samples[1:]))}
                    assert not any(report['non_interference'][key] for key in ('focus_changes','pointer_changes','clipboard_changes')), report['non_interference']
                    report['result'] = 'PASS'
                finally:
                    commands.close()
    except Exception as exc:
        report.update(result='FAIL', error=str(exc))
        raise
    finally:
        child.terminate()
        child.wait(timeout=5)
        (evidence / 'receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result':report['result'], 'non_interference':report['non_interference']}, indent=2))


if __name__ == '__main__':
    main()
