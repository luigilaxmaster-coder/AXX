"""OBS v5, local authenticated transport and explicit state-setting operations."""
import base64
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit
import uuid

from .artifact_verification import run_inspector


def configuration():
    endpoint, password = os.environ.get('AXX_OBS_URL', ''), os.environ.get('AXX_OBS_PASSWORD', '')
    url = urlsplit(endpoint)
    if (url.scheme != 'ws' or url.hostname not in ('127.0.0.1', '::1') or not url.port
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment or not password):
        raise ValueError('OBS requiere AXX_OBS_URL loopback con puerto y AXX_OBS_PASSWORD en el backend')
    return endpoint, password


def identity(endpoint):
    import psutil
    url = urlsplit(endpoint)
    pids = {row.pid for row in psutil.net_connections(kind='tcp')
            if row.status == psutil.CONN_LISTEN and row.laddr.port == url.port
            and row.laddr.ip in (url.hostname, '0.0.0.0', '::') and row.pid}
    if len(pids) != 1:
        raise ValueError('No se identificó un único proceso OBS dueño del puerto')
    process = psutil.Process(pids.pop())
    if process.name().casefold() not in ('obs64.exe', 'obs32.exe'):
        raise ValueError('El puerto configurado no pertenece a OBS')
    value = f'{endpoint}|{process.pid}|{process.create_time()}'
    return hashlib.sha256(value.encode()).hexdigest()


class Connection:
    def __init__(self, cancelled):
        import websocket
        self.socket = None
        self.cancelled, self.deadline = cancelled, time.monotonic() + 15
        endpoint, password = configuration()
        self.session = identity(endpoint)
        try:
            self.socket = websocket.create_connection(endpoint, timeout=1, suppress_origin=True,
                http_no_proxy=['127.0.0.1', '::1'], enable_multithread=True)
            hello = self.receive()
            auth = hello.get('d', {}).get('authentication', {})
            if hello.get('op') != 0 or not all(isinstance(auth.get(key), str) and 1 <= len(auth[key]) <= 1024 for key in ('salt', 'challenge')):
                raise ValueError('OBS no ofrece el protocolo autenticado esperado')
            secret = base64.b64encode(hashlib.sha256((password + auth['salt']).encode()).digest()).decode()
            response = base64.b64encode(hashlib.sha256((secret + auth['challenge']).encode()).digest()).decode()
            self.socket.send(json.dumps({'op': 1, 'd': {'rpcVersion': 1, 'authentication': response, 'eventSubscriptions': 0}}))
            if self.receive().get('op') != 2 or identity(endpoint) != self.session:
                raise ValueError('No se confirmó la sesión autenticada de OBS')
        except Exception:
            self.close()
            raise

    def close(self):
        if self.socket:
            try: self.socket.close(timeout=.2)
            except OSError: pass

    def receive(self):
        import websocket
        while time.monotonic() < self.deadline:
            if self.cancelled.is_set(): raise ValueError('OBS cancelado')
            try: raw = self.socket.recv()
            except websocket.WebSocketTimeoutException: continue
            if not isinstance(raw, str) or len(raw) > 512 * 1024:
                raise ValueError('Respuesta OBS inválida o excesiva')
            value = json.loads(raw)
            if not isinstance(value, dict): raise ValueError('Mensaje OBS inválido')
            return value
        raise TimeoutError('OBS superó su plazo')

    def call(self, method, data=None):
        if self.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise ValueError('OBS cancelado o fuera de plazo antes del despacho')
        key = uuid.uuid4().hex
        self.socket.send(json.dumps({'op': 6, 'd': {'requestType': method, 'requestId': key, 'requestData': data or {}}}))
        while True:
            message = self.receive()
            result = message.get('d', {})
            if message.get('op') == 7 and result.get('requestId') == key:
                if result.get('requestStatus', {}).get('result') is not True:
                    raise ValueError('OBS rechazó ' + method + ' (código ' + str(result.get('requestStatus', {}).get('code')) + ')')
                return result.get('responseData', {})


def observe(connection):
    version = connection.call('GetVersion')
    profiles = connection.call('GetProfileList')
    collections = connection.call('GetSceneCollectionList')
    scenes = connection.call('GetSceneList')
    status = connection.call('GetRecordStatus')
    if (not all(type(status.get(key)) is bool for key in ('outputActive', 'outputPaused'))
            or len(scenes.get('scenes', [])) > 200):
        raise ValueError('Estado o inventario OBS inválido')
    return {'obs_session': connection.session, 'version': version.get('obsVersion'),
            'profile': profiles.get('currentProfileName'), 'collection': collections.get('currentSceneCollectionName'),
            'scene': scenes.get('currentProgramSceneName'),
            'scenes': [row['sceneName'] for row in scenes.get('scenes', [])],
            'recording': status['outputActive'], 'paused': status['outputPaused'],
            'duration_ms': status.get('outputDuration'), 'observed_at': time.time()}


def validate(kind, inputs):
    required = set() if kind == 'observe' else {'obs_session', 'profile', 'collection', 'scene', 'action'}
    allowed = required | ({'target_scene'} if kind == 'control' else set())
    if not isinstance(inputs, dict) or set(inputs) - allowed or required - set(inputs):
        raise ValueError('Campos OBS inválidos')
    if kind == 'control':
        if not isinstance(inputs['obs_session'], str) or not re.fullmatch('[a-f0-9]{64}', inputs['obs_session']):
            raise ValueError('Indica la sesión OBS observada')
        if any(not isinstance(inputs[key], str) or not 1 <= len(inputs[key]) <= 256 for key in ('profile', 'collection', 'scene')):
            raise ValueError('Indica perfil, colección y escena observados')
        if inputs['action'] not in ('start', 'stop', 'pause', 'resume', 'scene'):
            raise ValueError('Acción OBS no admitida')
        if (inputs['action'] == 'scene') != ('target_scene' in inputs):
            raise ValueError('target_scene sólo se admite al establecer escena')
        if 'target_scene' in inputs and (not isinstance(inputs['target_scene'], str) or not 1 <= len(inputs['target_scene']) <= 256):
            raise ValueError('Escena destino inválida')


class ObsTool:
    version = '1.0.0'
    def __init__(self, kind):
        if kind not in ('observe', 'control'): raise ValueError('Operación OBS inválida')
        self.kind, self.name = kind, 'obs_' + kind
        self.description = 'OBS authenticated local ' + kind

    def verify_preconditions(self, inputs):
        try:
            validate(self.kind, inputs); configuration()
            import websocket, psutil
            return True, 'Configuración y parámetros OBS comprobados; host se verifica al conectar'
        except (ValueError, TypeError, ImportError) as exc: return False, str(exc)

    def execute(self, inputs):
        return self.execute_cancellable(inputs, None, threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        connection, dispatched, output = None, False, None
        try:
            validate(self.kind, inputs)
            if cancelled.is_set(): raise ValueError('Cancelado antes de conectar OBS')
            connection = Connection(cancelled)
            before = observe(connection)
            if self.kind == 'observe':
                return ToolResult(True, output=before, evidence={'verification': 'obs_state_readback'})
            if any(before[key] != inputs[key] for key in ('obs_session', 'profile', 'collection', 'scene')):
                raise ValueError('La sesión, perfil, colección o escena de OBS cambió')
            action = inputs['action']
            if action in ('pause', 'resume', 'stop') and not before['recording']:
                raise ValueError('No hay grabación activa; no se inventa un archivo anterior')
            if action == 'scene' and inputs['target_scene'] not in before['scenes']:
                raise ValueError('La escena elegida ya no existe')
            needed = not ((action == 'start' and before['recording']) or (action == 'pause' and before['paused'])
                or (action == 'resume' and not before['paused']) or (action == 'scene' and before['scene'] == inputs['target_scene']))
            response = {}
            if needed:
                method = {'start': 'StartRecord', 'stop': 'StopRecord', 'pause': 'PauseRecord', 'resume': 'ResumeRecord', 'scene': 'SetCurrentProgramScene'}[action]
                dispatched = True
                response = connection.call(method, {'sceneName': inputs['target_scene']} if action == 'scene' else None)
            after = observe(connection)
            if any(after[key] != before[key] for key in ('obs_session', 'profile', 'collection')):
                raise ValueError('El recurso OBS cambió durante la operación')
            matched = {'start': after['recording'], 'stop': not after['recording'],
                       'pause': after['recording'] and after['paused'], 'resume': after['recording'] and not after['paused'],
                       'scene': after['scene'] == inputs.get('target_scene')}[action]
            if not matched: raise ValueError('La lectura posterior no confirma el estado solicitado')
            output = after
            if action == 'stop':
                output['artifact'] = run_inspector('media', response.get('outputPath'), cancelled)
                if not any(row.get('codec_type') == 'video' for row in output['artifact']['streams']):
                    raise ValueError('La grabación no contiene una pista de vídeo')
            return ToolResult(True, output=output, evidence={'verification': 'obs_recording_file' if action == 'stop' else 'obs_state_readback',
                'already_in_state': not needed, 'recording_file_verified': action == 'stop'})
        except Exception as exc:
            return ToolResult(False, output=output, error=str(exc)[:600], evidence={'effect_uncertain': dispatched, 'cancelled': cancelled.is_set()})
        finally:
            if connection: connection.close()

    def verify_postconditions(self, inputs, result):
        return bool(result.success and result.evidence.get('verification') in ('obs_state_readback', 'obs_recording_file')), 'Estado OBS leído; archivo sólo al detener'
