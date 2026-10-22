"""Desktop-only management routes, behind AxxBridgeHandler's host authentication."""
import base64
import io
import urllib.parse
import json


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
        elif path == '/axx-api/mobile/snapshot':
            self.h._send_json(200, self.gateway.shared.snapshot())
        elif path == '/axx-api/mobile/voice/status':
            self.h._send_json(200, self.gateway.voice.status())
        elif path == '/axx-api/mobile/control/status':
            self.h._send_json(200, self.gateway.control.status())
        else:
            self.h._send_json(404, {'error': {'code':'NOT_FOUND'}})
        return True

    def post(self, path, body):
        if not path.startswith('/axx-api/mobile/'):
            return False
        if not self.gateway:
            self.h._send_json(503, {'error': {'code':'MOBILE_UNAVAILABLE'}})
            return True
        if path == '/axx-api/mobile/start':
            if body:
                raise ValueError('Activation does not accept client parameters')
            if not self.h.server.host_owned:
                raise ValueError('Enable mobile access from desktop Axx')
            result = self.gateway.start()
            if 'pairing_uri' in result:
                import qrcode
                import qrcode.image.svg
                image = qrcode.make(result['pairing_uri'], image_factory=qrcode.image.svg.SvgPathImage)
                output = io.BytesIO()
                image.save(output)
                result['qr_svg_base64'] = base64.b64encode(output.getvalue()).decode('ascii')
        elif path == '/axx-api/mobile/stop':
            self.gateway.stop()
            result = self.gateway.status()
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
            if not body['enabled']:self.gateway.control.disconnect(body['device_id'])
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
            if set(body) - {'messages', 'conversation_id', 'inference', 'appearance'} or not {'messages','conversation_id','inference'} <= set(body):
                raise ValueError('messages required')
            inference = body['inference']
            if not isinstance(inference, dict) or set(inference) != {'provider','provider_name','model'} or any(not isinstance(v,str) or len(v)>200 for v in inference.values()):
                raise ValueError('Invalid inference settings')
            self.gateway.preferences = dict(inference)
            appearance = body.get('appearance')
            if appearance is not None:
                self.gateway.appearance = checked_appearance(appearance)
            result = self.gateway.shared.merge_messages(body['messages'], 'desktop', body['conversation_id'], activate=True)
        else:
            self.h._send_json(404, {'error': {'code':'NOT_FOUND'}})
            return True
        self.h._send_json(200, result)
        return True
