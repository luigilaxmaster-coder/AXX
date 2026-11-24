"""Native screen tutorial (GUIDE-01..06) on a real web page: real Edge window, real UI Automation, real input.

Opt-in (AXX_REAL_GUIDE=1, Windows): it opens a local login page in an isolated Edge app window (temporary profile,
no network) and plays the user with real keyboard and mouse input. Only the model is scripted: AXX resolves every
target against fresh UIA state of that window, so the marks are where the real controls are.
"""
import ctypes
import ctypes.wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from PIL import Image

EDGE = next((p for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                         r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') if os.path.exists(p)), None)
SECRET = 's3cr3t-Guide-Pass'
GUIDE = {'schema_version': '1.0', 'kind': 'guide', 'goal': 'Iniciar sesión en el portal', 'steps': [
    {'id': 'g1', 'instruction': 'Escribe tu usuario en «Usuario»', 'target': {'name': 'Usuario', 'control_type': 'Edit', 'automation_id': 'user'},
     'postcondition': {'kind': 'value_changed'}},
    {'id': 'g2', 'instruction': 'Pulsa «Iniciar sesión»', 'target': {'name': 'Iniciar sesión', 'control_type': 'Button'},
     'postcondition': {'kind': 'window_title_contains', 'value': 'Bienvenido'}},
    {'id': 'g3', 'instruction': 'Pulsa «Recuperar cuenta»', 'target': {'name': 'Recuperar cuenta', 'control_type': 'Button'},
     'postcondition': {'kind': 'exists'}}]}

user32 = ctypes.windll.user32 if sys.platform == 'win32' else None
if user32:  # the simulated user clicks in physical pixels, like UIA bounds (per-monitor DPI aware v2)
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def _click(x, y):
    user32.SetCursorPos(int(x), int(y))
    for flag in (2, 4):  # left down, left up
        user32.mouse_event(flag, 0, 0, 0, 0)
        time.sleep(.05)


def _type(text):
    """The simulated user's real keystrokes (virtual keys with Shift when the layout needs it)."""
    for ch in text:
        code = user32.VkKeyScanW(ord(ch))
        vk, shift = code & 0xFF, (code >> 8) & 1
        if shift:
            user32.keybd_event(0x10, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0); user32.keybd_event(vk, 0, 2, 0)
        if shift:
            user32.keybd_event(0x10, 0, 2, 0)
        time.sleep(.02)


def _key(vk):
    user32.keybd_event(vk, 0, 0, 0); time.sleep(.03); user32.keybd_event(vk, 0, 2, 0)


@unittest.skipUnless(os.environ.get('AXX_REAL_GUIDE') == '1' and sys.platform == 'win32' and EDGE,
                     'Native: set AXX_REAL_GUIDE=1 on Windows with Edge; it drives a temporary Edge window with real input.')
class NativeScreenGuideTests(unittest.TestCase):
    def setUp(self):
        from backend.actions import windows_automation as uia
        from backend.magic_pen import MagicPenService
        self.uia = uia
        self.profile = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        page = Path(__file__).with_name('guide_login_fixture.html').as_uri()
        self.edge = subprocess.Popen([EDGE, '--user-data-dir=' + self.profile.name, '--no-first-run', '--no-default-browser-check',
                                      '--force-renderer-accessibility', '--window-position=150,120', '--window-size=760,640', '--app=' + page])
        self.addCleanup(self._close_edge)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            rows = [w for w in uia.list_windows() if 'Portal de prueba AXX' in (w.get('title') or '')]
            if rows:
                break
            time.sleep(.3)
        self.assertTrue(rows, 'Edge fixture window did not appear')
        self.window = rows[0]
        time.sleep(1.5)
        bounds = uia.observe_geometry(self.window['window_id'])['window_bounds']
        temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.addCleanup(temp.cleanup)
        self.service = MagicPenService(Path(temp.name)); self.addCleanup(self.service.close)
        self.prompts = []
        test = self

        class Adapter:  # scripted model: proposes semantic targets only
            config = {'allow_paid': False, 'providers': [{'name': 'fixture', 'model': 'visual-model', 'enabled': True,
                      'free_confirmed': True, 'capabilities': ['vision']}]}
            def route(self, request, **kw):
                test.prompts.append(json.dumps(request, ensure_ascii=False, default=str))
                return {'ok': True, 'message': {'content': json.dumps(GUIDE)}}
            def cancel(self, request_id): return True
        self.service.adapter = Adapter()
        width, height = bounds['x'] + bounds['width'] + 400, bounds['y'] + bounds['height'] + 400
        self.doc = self.service.acquire(Image.new('RGB', (width, height), 'white'), {'id': 'native', 'x': 0, 'y': 0})
        cx, cy = bounds['x'] + bounds['width'] // 2, bounds['y'] + bounds['height'] // 2
        self.service.save({'id': self.doc['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [cx - 40, cy - 40, cx + 40, cy + 40]}, 'strokes': []})
        q = self.service.start({'id': self.doc['id'], 'revision': 2, 'question': 'Explícame señalándome cómo iniciar sesión aquí', 'provider': 'fixture',
                                'model': 'visual-model', 'selection_mode': 'manual', 'request_id': uuid.uuid4().hex, 'format': 'guide'})
        end = time.monotonic() + 30
        while q['state'] == 'running' and time.monotonic() < end:
            time.sleep(.05)
            q = self.service.query({'id': q['source_id'], 'query_id': q['id']})
        self.assertEqual(q['state'], 'completed', q.get('error'))
        self.q = q

    def _close_edge(self):
        # Only the Edge processes of this temporary profile; the user's own Edge is never touched.
        marker = Path(self.profile.name).name
        subprocess.run(['powershell', '-NoProfile', '-Command',
                        f"Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], capture_output=True)
        time.sleep(.5)
        self.profile.cleanup()

    def check(self, step, phase='target'):
        return self.service.guide_check({'id': self.doc['id'], 'query_id': self.q['id'], 'step_id': step, 'phase': phase})

    def control(self, name, kind):
        observed = self.uia.inspect_controls(self.window['window_id'], self.window['pid'])
        return next(c for c in observed['controls'] if c['name'] == name and c['control_type'] == 'ControlType.' + kind)

    def wait(self, step, phase, states, seconds=8):
        end, last = time.monotonic() + seconds, None
        while time.monotonic() < end:
            last = self.check(step, phase)
            if last['state'] in states:
                return last
            time.sleep(.4)
        return last

    def test_login_tutorial_points_follows_and_verifies_without_credentials(self):
        # GUIDE-01: the mark is the real field's bounds.
        first = self.check('g1')
        self.assertEqual(first['state'], 'WAITING_USER', first)
        field = self.control('Usuario', 'Edit')
        self.assertEqual(first['bounds'], field['bounds'])
        # GUIDE-06: an element that is not on the page gets no position at all.
        missing = self.check('g3')
        self.assertEqual((missing['state'], missing['bounds']), ('TARGET_NOT_FOUND', None))
        # GUIDE-02: move the window; re-targeting follows the field by the same displacement.
        before = self.uia.observe_geometry(self.window['window_id'])['window_bounds']
        user32.SetWindowPos(self.window['window_id'], 0, before['x'] + 160, before['y'] + 70, 0, 0, 0x0001 | 0x0004)
        time.sleep(.8)
        after = self.uia.observe_geometry(self.window['window_id'])['window_bounds']
        moved = self.check('g1')
        # +-2 px: per-monitor DPI rounding between logical and physical coordinates (125 % here)
        self.assertAlmostEqual(moved['bounds']['x'] - first['bounds']['x'], after['x'] - before['x'], delta=2)
        self.assertAlmostEqual(moved['bounds']['y'] - first['bounds']['y'], after['y'] - before['y'], delta=2)
        # GUIDE-03: the login button is below the fold -> not drawn; after the user scrolls it is drawn where it really is.
        hidden = self.check('g2')
        self.assertEqual((hidden['state'], hidden['bounds']), ('TARGET_NOT_FOUND', None))
        # The user fills the form (real typing). GUIDE-05: AXX never types, and the password is recorded nowhere.
        field = self.control('Usuario', 'Edit')
        user32.SetForegroundWindow(self.window['window_id']); time.sleep(.3)
        _click(field['bounds']['x'] + 20, field['bounds']['y'] + 10); time.sleep(.4); _type('demo'); time.sleep(.4)
        def typed_value():  # Chromium updates its UIA value a few hundred ms after the keystrokes
            title = next(w['title'] for w in self.uia.list_windows() if w['window_id'] == self.window['window_id'])
            read = self.uia.read_window_content(self.window['window_id'], self.window['pid'], title, full_window=True, timeout=5)
            return next(c['value'] for c in read['controls'] if c.get('name') == 'Usuario' and c.get('control_type') == 'ControlType.Edit')
        end = time.monotonic() + 3
        while typed_value() != 'demo' and time.monotonic() < end: time.sleep(.2)
        self.assertEqual(typed_value(), 'demo')  # the user's own typing reached the real field
        verified = self.wait('g1', 'verify', {'VERIFIED'})
        self.assertEqual(verified['state'], 'VERIFIED', verified)
        _key(0x09); _type(SECRET)  # Tab to the password field
        _key(0x22); _key(0x22)     # Page Down twice: the user scrolls
        shown = self.wait('g2', 'target', {'WAITING_USER'})
        self.assertEqual(shown['state'], 'WAITING_USER', shown)
        button = self.control('Iniciar sesión', 'Button')
        self.assertEqual(shown['bounds'], button['bounds'])
        # GUIDE-04: the user presses the button; the next screen is detected from the window, not from a timer.
        _click(button['bounds']['x'] + button['bounds']['width'] // 2, button['bounds']['y'] + button['bounds']['height'] // 2)
        done = self.wait('g2', 'verify', {'VERIFIED'})
        self.assertEqual(done['state'], 'VERIFIED', done)
        stale = self.check('g1')  # the old screen's field is gone: no outdated mark is drawn
        self.assertEqual((stale['state'], stale['bounds']), ('VERIFIED', None))  # verified steps are never downgraded, and carry no mark
        session = self.service.guide_session({'id': self.doc['id'], 'query_id': self.q['id']})
        self.assertEqual(session['guide_mode'], 'screen')
        stored = (Path(self.service.directory(self.doc['id'])) / 'document.json').read_text(encoding='utf-8')
        for blob in [stored, json.dumps(session, ensure_ascii=False)] + self.prompts:
            self.assertNotIn(SECRET, blob)


if __name__ == '__main__':
    unittest.main()
