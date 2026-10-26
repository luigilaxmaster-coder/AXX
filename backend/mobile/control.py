"""Ephemeral input leases. Input packets are never persisted or replayed."""
import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager


class AutomationLease:
    """Cancellation view shared with the native hooks, never holds the UIA thread."""
    def __init__(self, native, lease_id, cancelled):
        self.native, self.lease_id, self.cancelled = native, lease_id, cancelled

    def is_set(self):
        return self.cancelled.is_set() or self.native.abort.is_set() or self.native.lease != self.lease_id

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.is_set() and time.monotonic() < deadline:
            self.cancelled.wait(min(.01, max(0, deadline - time.monotonic())))
        return self.is_set()

    def focus(self, window_id, pid):
        if self.is_set(): raise ValueError('Control cancelado antes de enfocar')
        self.native.focus(self.lease_id, window_id, pid)

    def move_absolute(self, x, y):
        if self.is_set(): raise ValueError('Control cancelado antes de mover el mouse')
        result = self.native.move_absolute(self.lease_id, x, y)
        if self.is_set(): raise ValueError('Control cancelado durante el movimiento')
        return result

    def targeted(self, target, operation, args=()):
        if self.is_set(): raise ValueError('Control cancelado antes de enviar entrada')
        return self.native.targeted(self.lease_id, target, operation, args)

    def renew(self):
        if self.is_set(): raise ValueError('Control cancelado antes de renovar')
        self.native.renew(self.lease_id, 30.)


def checked_events(events):
    if not isinstance(events,list) or not 1<=len(events)<=16:raise ValueError('Paquete de entrada inválido')
    if sum(len(e.get('text','')) for e in events if isinstance(e,dict) and isinstance(e.get('text',''),str))>512:raise ValueError('Paquete de texto demasiado largo')
    for e in events:
        if not isinstance(e,dict):raise ValueError('Evento inválido')
        kind=e.get('type')
        if kind in ('move','scroll'):
            if set(e)!={'type','x','y'} or any(type(e[k]) is not int or abs(e[k])>2000 for k in ('x','y')):raise ValueError('Desplazamiento inválido')
        elif kind=='button':
            if set(e)!={'type','button','down'} or e['button'] not in ('left','right','middle') or type(e['down']) is not bool:raise ValueError('Botón inválido')
        elif kind=='key':
            allowed={'Control','Alt','Shift','Meta','Escape','Enter','Tab','Backspace','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown','Space'}
            if set(e)!={'type','key','down'} or not isinstance(e['key'],str) or not (e['key'] in allowed or len(e['key'])==1 and e['key'] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') or type(e['down']) is not bool:raise ValueError('Tecla inválida')
        elif kind=='text':
            if set(e)!={'type','text'} or not isinstance(e['text'],str) or not 1<=len(e['text'])<=512 or '\x00' in e['text']:raise ValueError('Texto inválido')
            e['text'].encode('utf-16-le')
        else:raise ValueError('Tipo de entrada desconocido')
    return events


class RemoteControl:
    TTL=3.0
    def __init__(self,store,native=None,clock=time.monotonic):
        self.store,self.native,self.clock=store,native,clock
        self.lock=threading.RLock();self.lease=None;self.used=[];self.boot_id=str(uuid.uuid4())

    def _native(self):
        if self.native is None:
            from .windows_input import WindowsInput
            self.native=WindowsInput()
        return self.native

    def _allowed(self,device):
        return any(d['device_id']==device and not d['revoked'] and 'input.control' in d['scopes'] for d in self.store.devices())

    def _state(self):
        native=self.native.status() if self.native else {'active':False,'reason':'idle','keys':[],'buttons':[]}
        if self.lease and self.lease['state']=='granted':
            if self.clock()>=self.lease['deadline'] or not self._allowed(self.lease['device_id']):
                self.native.cancel('expired_or_revoked');native=self.native.status()
            if not native['active']:
                self.lease.update(state='released',reason=native['reason'])
        lease={k:v for k,v in self.lease.items() if k not in ('deadline','last_hash')} if self.lease else None
        return {'boot_id':self.boot_id,'lease':lease,'native':native,'ttl_ms':int(self.TTL*1000)}

    def status(self,device=None):
        with self.lock:
            result=self._state()
            if device and result['lease'] and result['lease']['device_id']!=device:
                result['lease']={'state':'occupied'}
            return result

    def acquire(self,device,body):
        if set(body)!={'request_id','visible'} or body['visible'] is not True:raise ValueError('Abre Axx Mobile para solicitar control')
        try:uuid.UUID(body['request_id'])
        except (ValueError,TypeError,AttributeError):raise ValueError('ID de solicitud inválido')
        with self.lock:
            self._state()
            if not self._allowed(device):raise ValueError('Autoriza ratón y teclado para este teléfono desde Axx en la PC')
            if self.lease and self.lease['state']=='granted':
                if self.lease['device_id']==device and self.lease['request_id']==body['request_id']:return self._state()
                raise ValueError('Ya existe una sesión de control. Libérala antes de solicitar otra.')
            if body['request_id'] in self.used:raise ValueError('Solicitud caducada. Solicita control de nuevo.')
            native=self._native();lease_id=str(uuid.uuid4());native.grant(lease_id,self.TTL)
            self.used=(self.used+[body['request_id']])[-128:]
            self.lease={'lease_id':lease_id,'device_id':device,'request_id':body['request_id'],'state':'granted','last_seq':0,'last_hash':'','deadline':self.clock()+self.TTL,'reason':''}
            return self._state()

    def _require(self,device,body):
        self._state()
        if not self.lease or self.lease['state']!='granted' or self.lease['device_id']!=device or body.get('lease_id')!=self.lease['lease_id'] or body.get('boot_id')!=self.boot_id:
            raise ValueError('El control terminó. No se reenviarán entradas; solicita una nueva sesión.')
        return self.lease

    def renew(self,device,body):
        if set(body)!={'lease_id','boot_id','visible'} or body['visible'] is not True:raise ValueError('La app debe permanecer visible')
        with self.lock:
            lease=self._require(device,body);self.native.renew(lease['lease_id'],self.TTL);lease['deadline']=self.clock()+self.TTL
            return self._state()

    def events(self,device,body):
        if set(body)!={'lease_id','boot_id','seq','events'} or type(body['seq']) is not int or body['seq']<1:raise ValueError('Secuencia inválida')
        checked_events(body['events']);digest=hashlib.sha256(json.dumps(body['events'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        with self.lock:
            lease=self._require(device,body)
            if body['seq']==lease['last_seq'] and digest==lease['last_hash']:return self._state()
            if body['seq']!=lease['last_seq']+1:raise ValueError('Paquete repetido, alterado o fuera de orden')
            # Admit before SendInput: uncertain outcomes must never be replayed.
            lease['last_seq']=body['seq'];lease['last_hash']=digest
            try:self.native.events(lease['lease_id'],body['events'])
            except Exception:
                self.native.cancel('input_failed');self._state();raise
            return self._state()

    def release(self,device=None,body=None,reason='released'):
        with self.lock:
            if device is not None:
                if not isinstance(body,dict) or set(body)!={'lease_id','boot_id'}:raise ValueError('Sesión requerida')
                if not self.lease or self.lease['device_id']!=device or body['lease_id']!=self.lease['lease_id'] or body['boot_id']!=self.boot_id:raise ValueError('Sesión distinta')
                if self.lease['state'] != 'granted' or (self.native and getattr(self.native, 'lease', self.lease['lease_id']) != self.lease['lease_id']):
                    return self._state()
            if self.native:self.native.cancel(reason)
            return self._state()

    def material(self,body):
        with self.lock:self._native().material(body)
        return {'updated':True}

    @contextmanager
    def automation(self, cancelled):
        with self.lock:
            self._state()
            if cancelled.is_set(): raise ValueError('Acción cancelada antes de tomar control')
            native = self._native()
            lease_id = str(uuid.uuid4())
            native.grant(lease_id, 30., 'axx_automation')
        lease = AutomationLease(native, lease_id, cancelled)
        try:
            yield lease
        except Exception as exc:
            exc.input_cancelled = lease.is_set()
            raise
        finally:
            with self.lock:
                # Do not revoke a new owner acquired after physical cancellation.
                if native.lease == lease_id:
                    native.cancel('released' if not lease.is_set() else 'automation_cancelled')

    def disconnect(self,device=None):
        with self.lock:
            if self.lease and (device is None or self.lease['device_id']==device):self.release(reason='disconnected')

    def close(self):
        self.disconnect()
        if self.native:self.native.close()
