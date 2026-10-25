"""UIA discovery and typed proposals; never a parallel command executor.

This local adapter is not the upstream CLI-Anything runtime. Observed patterns
need a registered action and a verified postcondition before activation.
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass
from .windows_automation import list_windows, scrape_window_tree


@dataclass
class CLIAppInterface:
    window_id: int
    pid: int
    title: str
    class_name: str
    foreground: bool
    controls: list[dict]
    truncated: bool
    observed_at: float
    observation: dict | None = None

    def to_dict(self):
        commands = {name: {'command_id': 'axx.desktop.window.' + name, 'available': True}
                    for name in ('inspect', 'read', 'focus')}
        writable = [c for c in self.controls if c.get('enabled') and not c.get('offscreen')
                    and c.get('supports_value_pattern') and not c.get('read_only', True)]
        if writable:
            commands['type'] = {'command_id': 'axx.desktop.window.set_value', 'available': True,
                                'control_ids': [c['control_id'] for c in writable]}
        buttons = [c for c in self.controls if c.get('control_type') == 'ControlType.Button'
                   and c.get('enabled') and not c.get('offscreen') and c.get('name')]
        if buttons:
            commands['press'] = {'command_id': 'axx.desktop.window.invoke', 'available': True,
                                 'control_ids': [c['control_id'] for c in buttons]}
        return {'window_id': self.window_id, 'pid': self.pid, 'title': self.title,
                'class_name': self.class_name, 'foreground': self.foreground,
                'observed_at': self.observed_at, 'observation': self.observation, 'total_controls': len(self.controls),
                'truncated': self.truncated, 'commands': commands, 'controls': self.controls,
                'limitation': 'Solo controles expuestos por UIA. Los patrones observados no son acciones validadas; toda ejecución pasa por el registro y su política.'}

    def generate_cli_help(self):
        lines = [f'{self.title} — {hex(self.window_id)} / PID {self.pid}',
                 f'{len(self.controls)} controles observados' + (' (límite alcanzado)' if self.truncated else '')]
        lines.extend(f"  {name}: {info['command_id']}" for name, info in self.to_dict()['commands'].items())
        lines.append('prepare genera una propuesta; aprueba y ejecuta la operación desde Axx.')
        return '\n'.join(lines)


class CLIAnythingEngine:
    """Stateless resolver: fresh observation, exact targets, no dispatch or cache."""

    def get_active_app(self, cancelled=None):
        windows = [w for w in list_windows() if w.get('foreground')]
        if len(windows) != 1:
            return None
        return self.scan_window(windows[0]['window_id'], windows[0]['pid'], cancelled=cancelled)

    def find_window_by_target(self, target):
        if isinstance(target, bool) or not isinstance(target, (str, int)):
            raise ValueError('Indica HWND hexadecimal, PID o título exacto.')
        text = str(target).strip()
        if not text or len(text) > 2048:
            raise ValueError('El destino está vacío o es demasiado largo.')
        windows = list_windows()
        if re.fullmatch(r'0x[0-9a-fA-F]{1,16}', text):
            matches = [w for w in windows if w['window_id'] == int(text, 16)]
        elif text.isdigit():
            matches = [w for w in windows if w['pid'] == int(text)]
        else:
            matches = [w for w in windows if w['title'].casefold() == text.casefold()]
        if len(matches) > 1:
            raise ValueError('Destino ambiguo: selecciona el HWND de la ventana exacta.')
        return matches[0] if matches else None

    def scan_window(self, window_id, pid, *, cancelled=None):
        window = next((w for w in list_windows() if w['window_id'] == window_id and w['pid'] == pid), None)
        if not window:
            raise ValueError('La ventana observada ya no existe.')
        result = scrape_window_tree(window_id, pid, cancelled=cancelled)
        if result.get('window_title') != window['title']:
            raise ValueError('La ventana cambió durante la observación.')
        return CLIAppInterface(window_id, pid, window['title'], window['class_name'], window['foreground'],
                               result.get('controls', [])[:1000], bool(result.get('truncated')), time.time(), result.get('observation'))

    def resolve(self, target, cancelled=None):
        if target is None:
            app = self.get_active_app(cancelled)
        else:
            window = self.find_window_by_target(target)
            app = self.scan_window(window['window_id'], window['pid'], cancelled=cancelled) if window else None
        if app is None:
            raise ValueError('No se encontró una única ventana para observar.')
        return app

    def list_commands(self, target=None):
        """Fresh metadata plus registry contracts, never learned executable IDs."""
        from backend.commands import ADAPTERS
        app = self.resolve(target)
        observation = app.to_dict()
        commands = []
        for name, item in observation['commands'].items():
            adapter = ADAPTERS[item['command_id']]
            commands.append({**item, 'name': name, 'registered': True,
                             'description': adapter['description'], 'risk': adapter['risk'],
                             'parameters': adapter['parameters'],
                             'requires_approval': bool(adapter.get('requires_approval', adapter['risk'] != 'read')),
                             'execution_verified': False})
        return {'window_id': app.window_id, 'pid': app.pid, 'title': app.title,
                'observed_at': app.observed_at, 'observation': app.observation, 'commands': commands,
                'observed_controls': app.controls, 'truncated': app.truncated,
                'limitation': observation['limitation'],
                'learning_endpoint': '/axx-api/learning/actions'}

    def propose(self, target, command, args=None):
        if not isinstance(command, str) or command not in ('inspect', 'read', 'focus', 'type', 'press'):
            raise ValueError('Acción sin contrato y postcondición registrados; usa inspect, read, focus, type o press.')
        args = {} if args is None else args
        allowed = {'control_id', 'text'} if command == 'type' else {'control_id'} if command == 'press' else set()
        if not isinstance(args, dict) or set(args) != allowed:
            raise ValueError('Parámetros inesperados o incompletos para la acción.')
        app = self.resolve(target)
        inputs = {'window_id': hex(app.window_id), 'pid': app.pid}
        suffix = {'inspect': 'inspect', 'read': 'read', 'focus': 'focus', 'type': 'set_value', 'press': 'invoke'}[command]
        if command == 'read':
            inputs['expected_title'] = app.title
        if command == 'type':
            candidates = [c for c in app.controls if c.get('control_id') == args['control_id']]
            if len(candidates) != 1 or not candidates[0].get('enabled') or candidates[0].get('offscreen') or not candidates[0].get('supports_value_pattern') or candidates[0].get('read_only', True):
                raise ValueError('Selecciona un control único, visible y editable de la observación actual.')
            inputs.update(control_id=args['control_id'], value=args['text'])
        if command == 'press':
            candidates = [c for c in app.controls if c.get('control_id') == args['control_id']
                          and c.get('control_type') == 'ControlType.Button' and c.get('enabled')
                          and not c.get('offscreen') and c.get('name')]
            if len(candidates) != 1:
                raise ValueError('Selecciona un botón único, visible y habilitado de la observación actual.')
            inputs.update(control_id=args['control_id'], expected_title=app.title, expected_name=candidates[0]['name'])
        from .desktop import validate_inputs
        validate_inputs({'inspect': 'inspect_window', 'read': 'read_window', 'focus': 'focus_window', 'type': 'set_window_value', 'press': 'invoke_window_button'}[command], inputs)
        return {'command_id': 'axx.desktop.window.' + suffix, 'inputs': inputs}


ENGINE = CLIAnythingEngine()
