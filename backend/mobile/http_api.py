"""Desktop-only management routes, behind AxxBridgeHandler's host authentication."""
import urllib.parse
import json
from .pairing_qr import pairing_qr_base64


def checked_appearance(value):
    required = {'settings','studio','camera','finish'}
    if not isinstance(value,dict) or not required <= set(value) or set(value) - required - {'activity'} or len(json.dumps(value)) > 16000:
        raise ValueError('Invalid appearance')
    if 'activity' in value:
        activity = value['activity']
        if not isinstance(activity,dict) or set(activity) != {'state','moving'} or not isinstance(activity['moving'],bool) or activity['state'] not in {'idle','listening','thinking','speaking','processing','approval','paused','success','error','notification','focus','transform','offline','cancelled'}:
            raise ValueError('Invalid character state')
    return value


class MobileHTTP:
    def __init__(self, handler):
        self.h = handler
        self.gateway = getattr(handler.server, 'mobile', None)

    def get(self, path):
        if not path.startswith('/axx-api/mobile/'):
            return False
        if not self.gateway:
            self.h._send_json(503, {'error': {'code':'MOBILE_UNAVAILABLE'}})
        elif path == '/axx-api/mobile/status':
            self.h._send_json(200, self.gateway.status())
        elif path == '/axx-api/mobile/files/status':
            self.h._send_json(200, self.gateway.transfers.status())
        elif path == '/axx-api/mobile/transfers':
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.h.path).query)
            if set(query) != {'transfer_id'} or len(query['transfer_id']) != 1:
                raise ValueError('transfer_id required')
            self.h._send_json(200, self.gateway.transfers.get(query['transfer_id'][0]))
        elif path == '/axx-api/mobile/snapshot':
            self.h._send_json(200, self.gateway.shared.snapshot())
        elif path == '/axx-api/mobile/voice/status':
            self.h._send_json(200, self.gateway.voice.status())
        elif path == '/axx-api/mobile/control/status':
            self.h._send_json(200, self.gateway.control.status())
        elif path == '/axx-api/mobile/avatar/events':
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.h.path).query)
            if set(query) != {'since'} or len(query['since']) != 1 or not query['since'][0].isdecimal():
                raise ValueError('since must be a nonnegative integer')
            self.h._send_json(200, self.gateway.avatar_events(int(query['since'][0])))
        elif path == '/axx-api/mobile/work/pending':
            self.h._send_json(200, self.gateway.pending_work())
        else:
            self.h._send_json(404, {'error': {'code':'NOT_FOUND'}})
        return True

    def post(self, path, body):
        if not path.startswith('/axx-api/mobile/'):
            return False
        if not self.gateway:
            self.h._send_json(503, {'error': {'code':'MOBILE_UNAVAILABLE'}})
            return True
        if path == '/axx-api/mobile/files/permissions':
            result = self.gateway.transfers.configure(body)
        elif path == '/axx-api/mobile/files/search':
            if 'device_id' not in body:
                raise ValueError('device_id required')
            result = self.gateway.transfers.search(body['device_id'], {k: v for k, v in body.items() if k != 'device_id'})
        elif path == '/axx-api/mobile/files/export':
            result = self.gateway.transfers.export(body)
        elif path == '/axx-api/mobile/files/save':
            result = self.gateway.transfers.save_downloads(body)
        elif path == '/axx-api/mobile/files/remove':
            result = self.gateway.transfers.remove(body)
        elif path in ('/axx-api/mobile/transfers/create', '/axx-api/mobile/transfers/chunk',
                      '/axx-api/mobile/transfers/pause', '/axx-api/mobile/transfers/resume',
                      '/axx-api/mobile/transfers/cancel', '/axx-api/mobile/transfers/finish', '/axx-api/mobile/transfers/receipt'):
            action = path.rsplit('/', 1)[1]
            payload = {k: v for k, v in body.items() if k != 'device_id'}
            device_id = body.get('device_id') if action == 'create' else self.gateway.transfers._load(body.get('transfer_id'))['device_id']
            result = (self.gateway.transfers.create(device_id, payload) if action == 'create'
                      else self.gateway.transfers.chunk(device_id, payload) if action == 'chunk'
                      else self.gateway.transfers.action(action, device_id, payload))
        elif path == '/axx-api/mobile/network':
            if set(body) != {'mode'} or not self.h.server.host_owned:
                raise ValueError('Selecciona la red desde Axx en la PC.')
            try:
                result = self.gateway.set_network_mode(body['mode'])
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
            if 'pairing_uri' in result:
                result['qr_svg_base64'] = pairing_qr_base64(result['pairing_uri'])
        elif path == '/axx-api/mobile/start':
            if body:
                raise ValueError('Activation does not accept client parameters')
            if not self.h.server.host_owned:
                raise ValueError('Enable mobile access from desktop Axx')
            try:
                result = self.gateway.start()
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
            if 'pairing_uri' in result:
                result['qr_svg_base64'] = pairing_qr_base64(result['pairing_uri'])
        elif path == '/axx-api/mobile/stop':
            result = self.gateway.set_always_access(False)
        elif path == '/axx-api/mobile/always-access':
            if set(body) != {'enabled'} or type(body['enabled']) is not bool:
                raise ValueError('enabled must be a boolean')
            try:
                result = self.gateway.set_always_access(body['enabled'])
            except RuntimeError as exc:
                raise ValueError(str(exc)) from exc
        elif path == '/axx-api/mobile/work/approve':
            result = self.gateway.approve_work(body)
        elif path == '/axx-api/mobile/revoke':
            if set(body) != {'device_id'} or not isinstance(body['device_id'], str):
                raise ValueError('device_id required')
            result = {'revoked': self.gateway.revoke(body['device_id'])}
        elif path == '/axx-api/mobile/voice/toggle':
            if not self.gateway.httpd:raise ValueError('Enable mobile access before using remote voice')
            result = self.gateway.voice.toggle(body)
        elif path == '/axx-api/mobile/tools-permission':
            if set(body)!={'device_id','enabled'}:raise ValueError('device_id and enabled required')
            result={'scopes':self.gateway.store.set_tool_permission(body['device_id'],body['enabled'])}
            if not body['enabled']:self.gateway.voice.disconnect(body['device_id'])
        elif path == '/axx-api/mobile/input-permission':
            if set(body)!={'device_id','enabled'}:raise ValueError('device_id and enabled required')
            result={'scopes':self.gateway.store.set_input_permission(body['device_id'],body['enabled'])}
            if not body['enabled']:
                self.gateway.control.disconnect(body['device_id'])
                self.gateway.clear_avatar_device(body['device_id'])
        elif path == '/axx-api/mobile/control/material':
            result=self.gateway.control.material(body)
        elif path == '/axx-api/mobile/control/cancel':
            if body:raise ValueError('Cancellation does not accept parameters')
            result=self.gateway.control.release(reason='local_cancel')
        elif path == '/axx-api/mobile/voice/confirm':
            if set(body)!={'session_id','text'}:raise ValueError('session_id and text required')
            result = self.gateway.voice.confirm(body['session_id'],body['text'])
        elif path == '/axx-api/mobile/voice/claim':
            if set(body)!={'session_id','conversation_id'}:raise ValueError('Session and conversation are required')
            result = self.gateway.voice.claim(body['session_id'],body['conversation_id'])
        elif path == '/axx-api/mobile/voice/finish':
            if set(body)!={'session_id','result'}:raise ValueError('Session and result are required')
            result = self.gateway.voice.finish(body['session_id'],body['result'])
        elif path == '/axx-api/mobile/voice/cancel':
            if set(body)!={'session_id'}:raise ValueError('session_id required')
            result = self.gateway.voice.cancel(body['session_id'])
        elif path == '/axx-api/mobile/appearance':
            self.gateway.appearance = checked_appearance(body)
            result = {'updated':True}
        elif path == '/axx-api/mobile/messages':
            if set(body) - {'messages', 'conversation_id', 'inference', 'appearance', 'share_history'} or not {'messages','conversation_id','inference'} <= set(body):
                raise ValueError('messages required')
            inference = body['inference']
            if not isinstance(inference, dict) or not {'provider','provider_name','model'} <= set(inference) or set(inference) - {'provider','provider_name','model','selection_mode'} or any(not isinstance(v,str) or len(v)>200 for v in inference.values()):
                raise ValueError('Invalid inference settings')
            if inference.get('selection_mode', 'manual') not in ('manual', 'automatic_free'):
                raise ValueError('Invalid selection mode')
            if type(body.get('share_history', True)) is not bool:
                raise ValueError('share_history must be a boolean')
            self.gateway.preferences = dict(inference)
            appearance = body.get('appearance')
            if appearance is not None:
                self.gateway.appearance = checked_appearance(appearance)
            self.gateway.share_history = body.get('share_history', True)
            result = self.gateway.shared.merge_messages(body['messages'] if self.gateway.share_history else [], 'desktop', body['conversation_id'], activate=True)
            if not self.gateway.share_history:
                result = {'conversation_id':body['conversation_id'],'messages':[]}
        else:
            self.h._send_json(404, {'error': {'code':'NOT_FOUND'}})
            return True
        self.h._send_json(200, result)
        return True
