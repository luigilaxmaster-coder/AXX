"""Application routes over owned inventories/UIA observations; no native input."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.actions import application_tools as apps
from backend.actions.executor import ActionExecutor
from backend.actions.tools import ToolResult


CHROME = {'id': 'chrome', 'title': 'Chrome', 'aliases': ['Google Chrome'],
          'process_names': ['chrome.exe'], 'instructions': [], 'commands': [
              {'id': 'navigate', 'kind': 'navigate', 'names': ['Address and search bar'], 'requires_text': True},
              {'id': 'new_tab', 'kind': 'shortcut', 'keys': ['Control', 'T']},
              {'id': 'settings', 'kind': 'invoke', 'names': ['Settings']}]}
TELEGRAM = {'id': 'telegram', 'title': 'Telegram', 'aliases': [],
            'process_names': ['Telegram.exe'], 'instructions': [], 'commands': [
                {'id': 'send', 'kind': 'guide', 'requires_connection': True}]}
TEAMVIEWER = {'id': 'teamviewer', 'title': 'TeamViewer', 'aliases': [],
              'process_names': ['TeamViewer.exe'], 'instructions': [], 'commands': [
                  {'id': 'connect', 'kind': 'guide', 'requires_connection': True}]}
SPOTIFY = {'id': 'spotify', 'title': 'Spotify', 'aliases': [],
           'process_names': ['Spotify.exe'], 'instructions': [], 'commands': []}
WINDOW = {'window_id': 123, 'pid': 1001, 'title': 'Owned fixture', 'class_name': 'OwnedClass', 'foreground': True}
ADDRESS = {'control_id': 'a' * 64, 'name': 'Address and search bar', 'control_type': 'ControlType.Edit',
           'enabled': True, 'offscreen': False, 'supports_value_pattern': True, 'read_only': False,
           'value': 'https://example.com/'}


def observation(value=None, *, controls=None, focused=None, quality='complete', birth='birth-1', sequence=1):
    row = deepcopy(ADDRESS)
    if value is not None:
        row['value'] = value
    return {'quality': quality, 'controls': [row] if controls is None else controls,
            'focused_control_id': row['control_id'] if focused is None else focused,
            'observation': {'process_started': birth, 'observation_id': 'owned-' + str(sequence)}}


class InputOwner:
    def __init__(self):
        self.acquisitions = self.releases = 0
        self.control = threading.Event()

    @contextmanager
    def automation(self, cancelled):
        self.acquisitions += 1
        if cancelled.is_set():
            raise ValueError('Owned lease cancelled')
        try:
            yield self.control
        finally:
            self.releases += 1


@contextmanager
def owned_windows(rows=None, *, processes=None, birth='birth-1'):
    """Only process and UIA primitives are replaced; real routing remains active."""
    profiles = [CHROME, TELEGRAM, TEAMVIEWER, SPOTIFY]
    def profile_for(query):
        query = apps.plain(query)
        return next((deepcopy(p) for p in profiles if query in
                    [apps.plain(p['id']), apps.plain(p['title']), *map(apps.plain, p['aliases'])]), None)
    with ExitStack() as stack:
        stack.enter_context(patch.object(apps.catalog, 'profile_for', side_effect=profile_for))
        stack.enter_context(patch.object(apps.uia, 'list_windows', return_value=deepcopy([WINDOW] if rows is None else rows)))
        stack.enter_context(patch.object(apps.uia, 'process_name', side_effect=lambda pid: (processes or {1001: 'chrome.exe'})[pid]))
        stack.enter_context(patch.object(apps.uia, 'process_started', return_value=birth))
        yield stack


class ApplicationToolTests(unittest.TestCase):
    def test_visible_url_comparison_elides_only_http_scheme_and_keeps_all_other_parts_exact(self):
        for scheme in ('http', 'https'):
            requested = scheme + '://example.com:8443/path?q=owned#section'
            with self.subTest(scheme=scheme):
                self.assertEqual(apps._url_readback(requested, requested), (True, True))
                self.assertEqual(apps._url_readback(requested.split('://', 1)[1], requested), (True, False))
            for observed in [('https' if scheme == 'http' else 'http') + '://example.com:8443/path?q=owned#section',
                             'other.example:8443/path?q=owned#section', 'example.com:8444/path?q=owned#section',
                             'example.com/path?q=owned#section', 'example.com:8443/other?q=owned#section',
                             'example.com:8443/path?q=different#section', 'example.com:8443/path?q=owned#other',
                             'example.com:8443/path?q=owned', 'user:password@example.com:8443/path?q=owned#section',
                             'javascript:alert(1)', 'file:///C:/data', '//example.com:8443/path?q=owned#section',
                             'example.com:8443/path?q=owned#section ', 'example.com:8443\\path?q=owned#section']:
                with self.subTest(scheme=scheme, observed=observed):
                    self.assertFalse(apps._same_url(observed, requested))
        self.assertFalse(apps._same_url('example.com:80/path', 'http://example.com/path'))
        self.assertFalse(apps._same_url('example.com', 'http://example.com/'))
        for requested in ['javascript:alert(1)', 'file:///C:/data', 'https://user:pass@example.com/']:
            self.assertEqual(apps._url_readback('example.com/', requested), (False, False))

    def run_tool(self, kind, inputs, owner=None, cancelled=None):
        return apps.ApplicationTool(kind).execute_with_runtime(inputs, None, cancelled or threading.Event(),
                                                              SimpleNamespace(input_control=owner))

    def test_arguments_and_guides_fail_before_any_desktop_primitive(self):
        with owned_windows(), patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
            bad = [{'application': 'chrome', 'window_id': 123}, {'application': 'chrome', 'pid': 1001},
                   {'application': 'chrome', 'window_id': True, 'pid': 1001}, {'application': 'x' * 241},
                   {'application': 'chrome\x00'}, {'application': 'chrome', 'unexpected': True}]
            for inputs in bad:
                with self.subTest(inputs=inputs):
                    self.assertFalse(self.run_tool('focus', inputs).success)
            for application, command in [('telegram', 'send'), ('teamviewer', 'connect')]:
                result = self.run_tool('navigate', {'application': application, 'command_id': command})
                self.assertFalse(result.success)
                self.assertIn('adaptador', result.error)
            body.assert_not_called()

    def test_open_uses_only_unique_catalog_app_id_and_preserves_failure(self):
        resolved = {'profile': CHROME, 'app': {'name': 'Google Chrome', 'app_id': 'actual-installed-id'}}
        owner = InputOwner()
        with patch.object(apps.catalog, 'resolve_application', return_value=resolved), \
                patch('backend.actions.tools.DesktopTool.execute_with_control', return_value=ToolResult(True, evidence={'accepted': True})) as body:
            result = self.run_tool('open', {'application': 'chrome'}, owner)
            self.assertTrue(result.success)
            self.assertEqual(body.call_args.args[0], {'app_id': 'actual-installed-id'})
            self.assertIs(body.call_args.args[3], owner)
        with patch.object(apps.catalog, 'resolve_application', side_effect=ValueError('Ambiguous: Owned A, Owned B')), \
                patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
            result = self.run_tool('open', {'application': 'chrome'})
            self.assertFalse(result.success)
            self.assertIn('Ambiguous', result.error)
            body.assert_not_called()

    def test_windows_uses_process_identity_and_reports_ambiguity(self):
        other = dict(WINDOW, window_id=124, pid=1002, title='Chrome misleading title')
        second = dict(WINDOW, window_id=125, pid=1003, title='Second owned window')
        with owned_windows([WINDOW, other, second], processes={1001: 'chrome.exe', 1002: 'other.exe', 1003: 'CHROME.EXE'}):
            result = self.run_tool('windows', {'application': 'chrome'})
            self.assertTrue(result.success)
            self.assertTrue(result.output['ambiguous'])
            self.assertEqual([row['window_id'] for row in result.output['windows']], [123, 125])
            self.assertEqual(result.evidence['count'], 2)
            self.assertTrue(apps.ApplicationTool('windows').verify_postconditions({}, result)[0])
            with patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
                self.assertFalse(self.run_tool('focus', {'application': 'chrome'}).success)
                body.assert_not_called()

    def test_generic_app_requires_matching_executable_path(self):
        with owned_windows(processes={1001: 'owned.exe'}), \
                patch.object(apps.catalog, 'resolve_application', return_value={'app': {'name': 'Owned', 'app_id': 'UWP!Owned'}}):
            self.assertFalse(self.run_tool('windows', {'application': 'owned'}).success)
        app = {'app': {'name': 'Owned', 'app_id': 'C:\\Owned\\owned.exe'}}
        with owned_windows(processes={1001: 'owned.exe'}), patch.object(apps.catalog, 'resolve_application', return_value=app), \
                patch.object(apps, '_process_path', return_value='c:\\other\\owned.exe'):
            self.assertEqual(self.run_tool('windows', {'application': 'owned'}).output['windows'], [])
        with owned_windows(processes={1001: 'owned.exe'}), patch.object(apps.catalog, 'resolve_application', return_value=app), \
                patch.object(apps, '_process_path', return_value='c:\\owned\\owned.exe'):
            self.assertEqual(len(self.run_tool('windows', {'application': 'owned'}).output['windows']), 1)

    def test_explicit_reference_and_live_process_guard(self):
        with owned_windows(), patch('backend.actions.tools.DesktopTool.execute_with_control', return_value=ToolResult(True, evidence={'accepted': True})) as body:
            for reference in [{'window_id': 124, 'pid': 1001}, {'window_id': 123, 'pid': 1002}]:
                self.assertFalse(self.run_tool('inspect', {'application': 'chrome', **reference}).success)
            body.assert_not_called()
            result = self.run_tool('inspect', {'application': 'chrome', 'window_id': 123, 'pid': 1001})
            self.assertTrue(result.success)
            self.assertEqual(body.call_args.args[0], {'window_id': '0x7b', 'pid': 1001})
        with owned_windows(), patch.object(apps.uia, 'process_started', side_effect=['birth-1', 'replacement']), \
                patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
            self.assertFalse(self.run_tool('close', {'application': 'chrome'}).success)
            body.assert_not_called()
        with owned_windows(), patch.object(apps.uia, 'process_started', side_effect=['birth-1', 'birth-1', 'replacement']), \
                patch('backend.actions.tools.DesktopTool.execute_with_control', return_value=ToolResult(True, evidence={'accepted': True})):
            result = self.run_tool('inspect', {'application': 'chrome'})
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['effect_uncertain'])

    def test_truncated_window_inventory_and_observation_abstain(self):
        with owned_windows([dict(WINDOW, window_id=i + 1) for i in range(apps.uia.MAX_WINDOWS)]):
            self.assertFalse(self.run_tool('windows', {'application': 'chrome'}).success)
        with owned_windows(), patch('backend.actions.desktop_observation.observe_desktop', return_value=observation(quality='truncated')), \
                patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
            self.assertFalse(self.run_tool('navigate', {'application': 'chrome', 'command_id': 'settings'}).success)
            body.assert_not_called()

    def test_invoke_requires_exact_unique_observed_button_and_keeps_unknown(self):
        button = {'control_id': 'b' * 64, 'name': 'Settings', 'control_type': 'ControlType.Button',
                  'enabled': True, 'offscreen': False, 'supports_invoke_pattern': True}
        ack = ToolResult(True, output={'button_sent': True}, evidence={'verification': 'uia_invoke_acknowledged'})
        inputs = {'application': 'chrome', 'command_id': 'settings'}
        with owned_windows(), patch('backend.actions.desktop_observation.observe_desktop', return_value=observation(controls=[button])), \
                patch('backend.actions.tools.DesktopTool.execute_with_control', return_value=ack) as body:
            result = self.run_tool('navigate', inputs, InputOwner())
            self.assertTrue(result.success)
            self.assertFalse(apps.ApplicationTool('navigate').verify_postconditions(inputs, result)[0])
            self.assertEqual(body.call_args.args[0]['control_id'], button['control_id'])
            self.assertEqual(body.call_args.args[0]['expected_name'], 'Settings')
        for controls in [[button, dict(button, control_id='c' * 64)], [dict(button, name='Settings and more')], [dict(button, offscreen=True)]]:
            with self.subTest(controls=controls), owned_windows(), \
                    patch('backend.actions.desktop_observation.observe_desktop', return_value=observation(controls=controls)), \
                    patch('backend.actions.tools.DesktopTool.execute_with_control') as body:
                self.assertFalse(self.run_tool('navigate', inputs, InputOwner()).success)
                body.assert_not_called()

    def test_shortcut_retains_delivery_only_effect_and_uses_one_lease(self):
        owner = InputOwner()
        output = {'success': True, 'evidence': {'accepted': True, 'verification': 'input_delivery_only',
                                              'effect_uncertain': True, 'reconciliation_required': True}}
        with owned_windows(), patch.object(apps.uia, 'focus_window') as focus, \
                patch('backend.actions.desktop_observation.observe_desktop', return_value=observation()), \
                patch('backend.actions.desktop_input.execute_action', return_value=output) as action, \
                tempfile.TemporaryDirectory() as folder, ActionExecutor(Path(folder) / 'state.db', folder) as executor:
            executor.input_control = owner
            executor.dynamic_tools['application_navigate'] = apps.ApplicationTool('navigate')
            inputs = {'application': 'chrome', 'command_id': 'new_tab'}
            result = executor.execute_action('application_navigate', inputs, 'owned-shortcut')
            self.assertEqual(result['state'], 'unknown', result)
            self.assertFalse(result['postconditions_passed'])
            self.assertTrue(result['evidence']['reconciliation_required'])
            self.assertTrue(executor.execute_action('application_navigate', inputs, 'owned-shortcut')['replayed'])
            self.assertEqual(executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
            self.assertEqual((owner.acquisitions, owner.releases), (1, 1))
            action.assert_called_once()
            self.assertEqual(action.call_args.args[0]['keys'], ['Control', 'T'])
            self.assertIs(action.call_args.args[1], owner.control)
            self.assertIs(focus.call_args.kwargs['control'], owner.control)

    def test_unsafe_url_rejected_before_focus_or_input(self):
        bad = ['javascript:alert(1)', 'file:///C:/data', 'https://user:pass@example.com',
               'https://example.com\\evil', 'https://example.com:65536/', 'https://example.com/\n', '//example.com']
        with owned_windows(), patch.object(apps.uia, 'focus_window') as focus, \
                patch('backend.actions.desktop_input.execute_action') as action:
            for url in bad:
                with self.subTest(url=url):
                    self.assertFalse(self.run_tool('navigate', {'application': 'chrome', 'command_id': 'navigate', 'url': url}, InputOwner()).success)
            focus.assert_not_called()
            action.assert_not_called()

    def test_browser_navigation_requires_focused_selector_and_readback(self):
        inputs = {'application': 'chrome', 'command_id': 'navigate', 'url': 'https://example.com/path?q=owned'}
        owner = InputOwner()
        # Real inspect observations expose metadata and an empty value field.
        observed = [observation('', sequence=index, controls=[dict(ADDRESS, name='Address and search bar ', value='')])
                    for index in range(1, 5)]
        with owned_windows(), patch.object(apps.uia, 'focus_window'), \
                patch.object(apps.uia, 'inspect_browser_controls', side_effect=observed), \
                patch('backend.actions.desktop_input.execute_action', return_value={'success': True}) as action, \
                patch.object(apps.uia, 'read_control_value', return_value={'value': inputs['url']}) as read, \
                patch.object(apps.uia, 'set_control_value') as write:
            result = self.run_tool('navigate', inputs, owner)
            self.assertTrue(result.success, result.error)
            self.assertTrue(apps.ApplicationTool('navigate').verify_postconditions(inputs, result)[0])
            self.assertEqual(result.evidence['verification'], 'application_url_readback')
            self.assertTrue(result.evidence['scheme_verified'])
            self.assertFalse(result.evidence['content_verified'])
            self.assertEqual([call.args[0]['keys'] for call in action.call_args_list], [['Control', 'L'], ['Enter']])
            self.assertEqual([call.args[0]['observation_id'] for call in action.call_args_list], ['owned-1', 'owned-3'])
            self.assertEqual(write.call_args.args[3], inputs['url'])
            self.assertIs(write.call_args.kwargs['cancelled'], owner.control)
            self.assertEqual([call.args[3] for call in read.call_args_list], ['owned-3', 'owned-4'])
            self.assertTrue(all(call.kwargs['cancelled'] is owner.control for call in read.call_args_list))
            self.assertEqual((owner.acquisitions, owner.releases), (1, 1))
        for unsafe_observation in [observation(focused='other-control'), observation(controls=[dict(ADDRESS, read_only=True)]), observation(birth='replacement')]:
            with self.subTest(observation=unsafe_observation), owned_windows(), patch.object(apps.uia, 'focus_window'), \
                    patch.object(apps.uia, 'inspect_browser_controls', side_effect=[observation(), unsafe_observation]), \
                    patch('backend.actions.desktop_input.execute_action', return_value={'success': True}) as action, \
                    patch.object(apps.uia, 'set_control_value') as write:
                result = self.run_tool('navigate', inputs, InputOwner())
                self.assertFalse(result.success)
                self.assertTrue(result.evidence['effect_uncertain'])
                self.assertEqual(action.call_count, 1)
                write.assert_not_called()

    def test_elided_address_bar_does_not_claim_scheme_or_loaded_content(self):
        for scheme in ('http', 'https'):
            requested = scheme + '://example.com:8443/path?q=owned#section'
            inputs = {'application': 'chrome', 'command_id': 'navigate', 'url': requested}
            with self.subTest(scheme=scheme), owned_windows(), patch.object(apps.uia, 'focus_window'), \
                    patch.object(apps.uia, 'inspect_browser_controls', side_effect=[observation('') for _ in range(4)]), \
                    patch('backend.actions.desktop_input.execute_action', return_value={'success': True}), \
                    patch.object(apps.uia, 'set_control_value'), \
                    patch.object(apps.uia, 'read_control_value', side_effect=[{'value': requested}, {'value': requested.split('://', 1)[1]}]):
                result = self.run_tool('navigate', inputs, InputOwner())
                self.assertTrue(result.success, result.error)
                self.assertTrue(apps.ApplicationTool('navigate').verify_postconditions(inputs, result)[0])
                self.assertFalse(result.output['scheme_verified'])
                self.assertFalse(result.evidence['scheme_verified'])
                self.assertFalse(result.output['content_verified'])
                self.assertFalse(result.evidence['content_verified'])


    def test_address_label_edge_whitespace_does_not_allow_ambiguous_post_navigation_bar(self):
        inputs = {'application': 'chrome', 'command_id': 'navigate', 'url': 'https://example.com/requested'}
        ambiguous = observation('', controls=[dict(ADDRESS, value=''),
            dict(ADDRESS, control_id='b' * 64, name='Address and search bar ', value='')])
        with owned_windows(), patch.object(apps.uia, 'focus_window'), \
                patch.object(apps.uia, 'inspect_browser_controls', side_effect=[observation(''), observation(''), observation(''), ambiguous]), \
                patch('backend.actions.desktop_input.execute_action', return_value={'success': True}) as action, \
                patch.object(apps.uia, 'set_control_value'), \
                patch.object(apps.uia, 'read_control_value', return_value={'value': inputs['url']}) as read:
            result = self.run_tool('navigate', inputs, InputOwner())
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['effect_uncertain'])
            self.assertEqual(action.call_count, 2)
            self.assertEqual(read.call_count, 1)

    def test_navigation_does_not_press_enter_after_wrong_value_readback(self):
        inputs = {'application': 'chrome', 'command_id': 'navigate', 'url': 'https://example.com/requested'}
        with owned_windows(), patch.object(apps.uia, 'focus_window'), \
                patch.object(apps.uia, 'inspect_browser_controls', side_effect=[observation(), observation(), observation('https://other.example/')]), \
                patch('backend.actions.desktop_input.execute_action', return_value={'success': True}) as action, \
                patch.object(apps.uia, 'set_control_value'), \
                patch.object(apps.uia, 'read_control_value', return_value={'value': 'https://other.example/'}):
            result = self.run_tool('navigate', inputs, InputOwner())
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['effect_uncertain'])
            self.assertEqual(action.call_count, 1)

    def test_navigation_keeps_unknown_after_enter_when_explicit_bar_readback_differs(self):
        inputs = {'application': 'chrome', 'command_id': 'navigate', 'url': 'https://example.com/requested'}
        with owned_windows(), patch.object(apps.uia, 'focus_window'), \
                patch.object(apps.uia, 'inspect_browser_controls', side_effect=[observation('') for _ in range(4)]), \
                patch('backend.actions.desktop_input.execute_action', return_value={'success': True}) as action, \
                patch.object(apps.uia, 'set_control_value'), \
                patch.object(apps.uia, 'read_control_value', side_effect=[{'value': inputs['url']}, {'value': 'https://other.example/'}]) as read:
            result = self.run_tool('navigate', inputs, InputOwner())
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['effect_uncertain'])
            self.assertEqual(action.call_count, 2)
            self.assertEqual(read.call_count, 2)

    def test_cancelled_application_does_not_resolve_or_act(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(apps.catalog, 'resolve_application') as resolve:
            result = self.run_tool('open', {'application': 'chrome'}, cancelled=cancelled)
            self.assertFalse(result.success)
            self.assertTrue(result.evidence['cancelled'])
            resolve.assert_not_called()

    def test_exact_language_routes_and_information_remains_informational(self):
        examples = {'abre Telegram': ('open', 'telegram'), 'muestra ventanas de Chrome': ('windows', 'chrome'),
                    'enfoca Spotify': ('focus', 'spotify'), 'inspecciona TeamViewer': ('inspect', 'teamviewer'),
                    'lista comandos de Google Chrome': ('catalog', 'chrome')}
        with owned_windows(), patch.object(apps.catalog, 'resolve_application', side_effect=ValueError('No exact installed match')):
            for text, (kind, application) in examples.items():
                self.assertEqual(apps.resolve_application_command(text), {'match': 'exact', 'command_id': 'axx.app.' + kind,
                                                                          'inputs': {'application': application}})
            for text in ['¿Cómo abro Telegram?', 'qué puede hacer Chrome', 'abre Telegr', 'abre Chrome y Spotify',
                         'abre Telegram; abre TeamViewer', 'Telegram', 'puedes inspeccionar TeamViewer']:
                self.assertIsNone(apps.resolve_application_command(text), text)

    def test_catalog_filter_reports_only_selected_profile_and_real_matches(self):
        match = {'name': 'Google Chrome', 'app_id': 'actual-id'}
        value = {'profiles': [dict(CHROME, installed_matches=[match]), dict(TELEGRAM, installed_matches=[])],
                 'applications': [match, {'name': 'Unrelated', 'app_id': 'other-id'}]}
        with owned_windows(), patch.object(apps.catalog, 'installed_catalog', return_value=value):
            result = self.run_tool('catalog', {'application': 'chrome'})
            self.assertTrue(result.success)
            self.assertEqual(result.output['applications'], [match])
            self.assertEqual([row['id'] for row in result.output['profiles']], ['chrome'])


if __name__ == '__main__':
    unittest.main()
