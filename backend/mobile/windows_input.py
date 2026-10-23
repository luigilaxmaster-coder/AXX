"""Windows-owned input gate and click-through cursor surface. No network in hooks."""
import base64
import ctypes as C
from ctypes import wintypes as W
import math
import os
import queue
import threading
import time
from PIL import Image,ImageFilter

UPTR=C.c_size_t
CALLBACK=getattr(C,'WINFUNCTYPE',C.CFUNCTYPE)
class Mouse(C.Structure):_fields_=[('dx',W.LONG),('dy',W.LONG),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',UPTR)]
class Key(C.Structure):_fields_=[('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',UPTR)]
class Hardware(C.Structure):_fields_=[('msg',W.DWORD),('lo',W.WORD),('hi',W.WORD)]
class InputUnion(C.Union):_fields_=[('mouse',Mouse),('key',Key),('hardware',Hardware)]
class Input(C.Structure):_fields_=[('type',W.DWORD),('data',InputUnion)]
class MouseHook(C.Structure):_fields_=[('point',W.POINT),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',UPTR)]
class KeyHook(C.Structure):_fields_=[('vk',W.DWORD),('scan',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',UPTR)]
WNDPROC=CALLBACK(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
HOOKPROC=CALLBACK(C.c_ssize_t,C.c_int,W.WPARAM,W.LPARAM)
class WindowClass(C.Structure):_fields_=[('style',W.UINT),('proc',WNDPROC),('classExtra',C.c_int),('windowExtra',C.c_int),('instance',W.HINSTANCE),('icon',W.HICON),('cursor',W.HANDLE),('background',W.HBRUSH),('menu',W.LPCWSTR),('name',W.LPCWSTR)]
class BitmapHeader(C.Structure):_fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('imageSize',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
class Blend(C.Structure):_fields_=[('op',C.c_ubyte),('flags',C.c_ubyte),('alpha',C.c_ubyte),('format',C.c_ubyte)]
KEYS={'Control':0x11,'Alt':0x12,'Shift':0x10,'Meta':0x5b,'Escape':0x1b,'Enter':0x0d,'Tab':9,'Backspace':8,'Delete':0x2e,'ArrowLeft':0x25,'ArrowRight':0x27,'ArrowUp':0x26,'ArrowDown':0x28,'Home':0x24,'End':0x23,'PageUp':0x21,'PageDown':0x22,'Space':0x20}
EXTENDED={'Meta','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'}
BUTTONS={'left':(2,4),'right':(8,16),'middle':(32,64)}
MARKER=0x41585804


def desktop_motion(x,y,dx,dy,monitors):
    left=min(m['x'] for m in monitors);top=min(m['y'] for m in monitors)
    width=max(m['x']+m['width'] for m in monitors)-left;height=max(m['y']+m['height'] for m in monitors)-top
    x=max(left,min(left+width-1,x+dx));y=max(top,min(top+height-1,y+dy))
    return x,y,min(65535,round((x-left+.5)*65536/width)),min(65535,round((y-top+.5)*65536/height))


def contour_rgba(table,size,opacity=1.,motion=(0.,0.),drag=False,pulse=0.,glow=.12,phase=0.):
    """Shade a small organic tube from the exact materialTable() of the live renderer."""
    pixels=bytearray(size*size*4);scale=size/48.;cx=size/2
    stretch=1.12 if drag else 1.;shift=max(-.10,min(.10,motion[0]/100));tilt=max(-.10,min(.10,motion[1]/100))
    for y in range(size):
        for x in range(size):
            px=(x+.5-cx)/scale/stretch;py=(y+.5-cx)/scale
            theta=math.atan2(py,px);radius=12+.5*math.sin(theta*3+phase)+pulse*.8
            distance=math.hypot(px,py)-radius;coverage=max(0.,min(1.,1.35-abs(distance)))
            if not coverage:continue
            normal=max(-.95,min(.95,distance/1.35));nx=math.cos(theta)*normal+shift;ny=-math.sin(theta)*normal+tilt
            ix=round(max(0,min(127,(nx+1)*63.5)));iy=round(max(0,min(127,(ny+1)*63.5)))
            source=(iy*128+ix)*4;dest=(y*size+x)*4
            pixels[dest:dest+3]=table[source:source+3];pixels[dest+3]=round(255*coverage*opacity)
    image=Image.frombytes('RGBA',(size,size),bytes(pixels))
    if glow>0:
        halo=image.filter(ImageFilter.GaussianBlur(1.1*scale));halo.putalpha(halo.getchannel('A').point(lambda n:round(n*glow)))
        image=Image.alpha_composite(halo,image)
    return image


class WindowsInput:
    def __init__(self):
        if os.name!='nt':raise ValueError('El control de entrada requiere Windows')
        self.user=C.WinDLL('user32',use_last_error=True);self.gdi=C.WinDLL('gdi32',use_last_error=True);self.kernel=C.WinDLL('kernel32',use_last_error=True)
        self._prototypes();self.commands=queue.Queue(32);self.stopping=threading.Event();self.abort=threading.Event();self.ready=threading.Event();self.error=None
        self.active=False;self.lease='';self.deadline=0.;self.reason='idle';self.abort_reason='expired_or_revoked';self.held_keys=set();self.held_buttons=set();self.table=None;self.material_at=0.;self.material_key='';self.reduced=False;self.intensity=.9;self.size=48;self.glow=.12
        self.snapshot={'active':False,'reason':'idle','keys':[],'buttons':[]};self.snapshot_lock=threading.Lock();self.hwnd=None;self.dc=None;self.bitmap=None;self.old_bitmap=None;self.bits=C.c_void_p();self.bitmap_size=0;self.last_frame=0.;self.last_point=None;self.velocity=(0.,0.);self.pulse_at=0.;self.granted_at=0.;self.release_at=0.
        self.hooks=[];self.thread_id=0
        self.thread=threading.Thread(target=self._run,name='axx-input-owner',daemon=True);self.thread.start()
        if not self.ready.wait(3) or self.error:raise ValueError('No se pudo iniciar el árbitro de Windows: '+str(self.error or 'timeout'))

    def _prototypes(self):
        def bind(dll,name,args,result):f=getattr(dll,name);f.argtypes=args;f.restype=result
        bind(self.user,'SendInput',[W.UINT,C.POINTER(Input),C.c_int],W.UINT)
        bind(self.user,'SetWindowsHookExW',[C.c_int,HOOKPROC,W.HINSTANCE,W.DWORD],W.HANDLE)
        bind(self.user,'CallNextHookEx',[W.HANDLE,C.c_int,W.WPARAM,W.LPARAM],C.c_ssize_t)
        bind(self.user,'UnhookWindowsHookEx',[W.HANDLE],W.BOOL)
        bind(self.user,'DefWindowProcW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM],C.c_ssize_t)
        bind(self.user,'RegisterClassW',[C.POINTER(WindowClass)],W.ATOM)
        bind(self.user,'CreateWindowExW',[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p],W.HWND)
        bind(self.user,'SetWindowPos',[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL)
        bind(self.user,'ShowWindow',[W.HWND,C.c_int],W.BOOL)
        bind(self.user,'DestroyWindow',[W.HWND],W.BOOL)
        bind(self.user,'GetDpiForWindow',[W.HWND],W.UINT)
        bind(self.user,'GetCursorPos',[C.POINTER(W.POINT)],W.BOOL)
        bind(self.user,'GetAsyncKeyState',[C.c_int],C.c_short)
        bind(self.user,'PeekMessageW',[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT],W.BOOL)
        bind(self.user,'TranslateMessage',[C.POINTER(W.MSG)],W.BOOL)
        bind(self.user,'DispatchMessageW',[C.POINTER(W.MSG)],C.c_ssize_t)
        bind(self.user,'PostThreadMessageW',[W.DWORD,W.UINT,W.WPARAM,W.LPARAM],W.BOOL)
        bind(self.user,'MsgWaitForMultipleObjectsEx',[W.DWORD,C.POINTER(W.HANDLE),W.DWORD,W.DWORD,W.DWORD],W.DWORD)
        bind(self.user,'SetThreadDpiAwarenessContext',[C.c_void_p],C.c_void_p)
        bind(self.user,'UpdateLayeredWindow',[W.HWND,W.HDC,C.POINTER(W.POINT),C.POINTER(W.SIZE),W.HDC,C.POINTER(W.POINT),W.DWORD,C.POINTER(Blend),W.DWORD],W.BOOL)
        bind(self.gdi,'CreateCompatibleDC',[W.HDC],W.HDC)
        bind(self.gdi,'CreateDIBSection',[W.HDC,C.POINTER(BitmapHeader),W.UINT,C.POINTER(C.c_void_p),W.HANDLE,W.DWORD],W.HBITMAP)
        bind(self.gdi,'SelectObject',[W.HDC,W.HANDLE],W.HANDLE)
        bind(self.gdi,'DeleteObject',[W.HANDLE],W.BOOL)
        bind(self.gdi,'DeleteDC',[W.HDC],W.BOOL)
        bind(self.kernel,'GetModuleHandleW',[W.LPCWSTR],W.HMODULE)
        bind(self.kernel,'GetCurrentThreadId',[],W.DWORD)

    def _call(self,operation,*args):
        item={'op':operation,'args':args,'done':threading.Event(),'expires':time.monotonic()+1.5}
        try:self.commands.put_nowait(item)
        except queue.Full:self.abort.set();raise ValueError('Canal de entrada ocupado; control cancelado')
        self.user.PostThreadMessageW(self.thread_id,0x8000,0,0)
        if not item['done'].wait(2):self.abort.set();raise ValueError('Windows no confirmó la entrada; control cancelado')
        if 'error' in item:raise ValueError(item['error'])
        return item.get('result')

    def status(self):
        with self.snapshot_lock:return dict(self.snapshot)
    def grant(self,lease,ttl,source='remote'):return self._call('grant',lease,ttl,source)
    def focus(self,lease,window_id,pid):return self._call('focus',lease,window_id,pid)
    def renew(self,lease,ttl):return self._call('renew',lease,ttl)
    def events(self,lease,events):return self._call('events',lease,events)
    def cancel(self,reason):self.abort_reason=reason;self.abort.set();return self._call('cancel',reason)
    def close(self):
        self.abort.set();self.stopping.set();self.user.PostThreadMessageW(self.thread_id,0x8000,0,0);self.thread.join(timeout=3)

    def _set_hooks(self,enabled):
        if not enabled:
            for hook in self.hooks:
                if hook:self.user.UnhookWindowsHookEx(hook)
            self.hooks=[]
        elif not self.hooks:
            instance=self.kernel.GetModuleHandleW(None)
            self.hooks=[self.user.SetWindowsHookExW(14,self.callbacks[1],instance,0),self.user.SetWindowsHookExW(13,self.callbacks[2],instance,0)]
            if not all(self.hooks):
                self._set_hooks(False)
                raise OSError('Could not establish local input priority')

    def material(self,body):
        if not isinstance(body,dict) or set(body)-{'key','table','reduced','size','intensity','glow'} or not {'key','reduced','size','intensity','glow'}<=set(body):raise ValueError('Material incompleto')
        if not isinstance(body['key'],str) or len(body['key'])>300 or type(body['reduced']) is not bool:raise ValueError('Material inválido')
        for key,low,high in [('size',36,64),('intensity',.3,1),('glow',0,.25)]:
            if type(body[key]) not in (int,float) or not math.isfinite(body[key]) or not low<=body[key]<=high:raise ValueError('Parámetros visuales fuera de rango')
        table=None
        if 'table' in body:
            if not isinstance(body['table'],str) or len(body['table'])>90000:raise ValueError('Tabla de material demasiado grande')
            table=base64.b64decode(body['table'],validate=True)
            if len(table)!=128*128*4:raise ValueError('Dimensiones del material inválidas')
        return self._call('material',body,table)

    def _mouse(self,flags,x=0,y=0,data=0):return Input(0,InputUnion(mouse=Mouse(x,y,data&0xffffffff,flags,0,MARKER)))
    def _key(self,key,down):
        vk=KEYS.get(key,ord(key) if len(key)==1 else 0)
        return Input(1,InputUnion(key=Key(vk,0,(0 if down else 2)|(1 if key in EXTENDED else 0),0,MARKER)))
    def _send(self,events):
        if events and self.user.SendInput(len(events),(Input*len(events))(*events),C.sizeof(Input))!=len(events):raise ValueError('Windows rechazó la entrada. No se controlan ventanas elevadas ni el escritorio seguro.')

    def _cancel(self,reason,physical_key=None,physical_button=None):
        was_active=self.active
        self.abort.set()
        self.active=False;self.reason=reason;self.lease='';self.deadline=0
        self._set_hooks(False)
        physical_key={0xa0:0x10,0xa1:0x10,0xa2:0x11,0xa3:0x11,0xa4:0x12,0xa5:0x12,0x5c:0x5b}.get(physical_key,physical_key)
        releases=[self._key(k,False) for k in self.held_keys if KEYS.get(k,ord(k) if len(k)==1 else 0)!=physical_key]
        releases += [self._mouse(BUTTONS[b][1]) for b in self.held_buttons if b!=physical_button]
        self.held_keys.clear();self.held_buttons.clear()
        try:self._send(releases)
        except Exception as exc:self.reason=reason+'; '+str(exc)
        self.release_at=(self.release_at or time.monotonic()) if (was_active or self.release_at) and reason=='released' and not self.reduced else 0.
        if self.hwnd and not self.release_at:self.user.ShowWindow(self.hwnd,0)

    def _check(self,lease):
        if self.abort.is_set() or not self.active or lease!=self.lease or time.monotonic()>=self.deadline:
            self._cancel('expired_or_revoked');raise ValueError('El control nativo terminó')

    def _execute(self,operation,args):
        now=time.monotonic()
        if operation=='material':
            body,table=args
            if table is not None:self.table=table;self.material_key=body['key']
            if self.table is None or body['key']!=self.material_key:raise ValueError('Axx aún no compartió el material del muñeco')
            animation=W.BOOL(True)
            self.user.SystemParametersInfoW(0x1042,0,C.byref(animation),0)
            self.material_at=now;self.reduced=body['reduced'] or not animation.value;self.size=body['size'];self.intensity=body['intensity'];self.glow=body['glow'];return
        if operation=='cancel':self._cancel(args[0]);return
        if operation=='grant':
            if self.active:raise ValueError('Ya existe control nativo')
            if self.table is None or now-self.material_at>5:raise ValueError('Abre Axx en la PC para sincronizar su indicador')
            if any(self.user.GetAsyncKeyState(k)<0 for k in (1,2,4,0x10,0x11,0x12,0x5b,0x5c)):raise ValueError('Suelta los botones y modificadores físicos antes de conceder control')
            self._set_hooks(True)
            self.abort.clear();self.abort_reason='expired_or_revoked';self.lease=args[0];self.deadline=now+args[1];self.active=True;self.source=args[2];self.reason='granted';self.granted_at=now;self.release_at=0;return
        self._check(args[0])
        if operation=='focus':
            from backend.actions.windows_automation import _windows_api
            user,_=_windows_api();hwnd=W.HWND(args[1]);pid=W.DWORD()
            user.GetWindowThreadProcessId(hwnd,C.byref(pid))
            if not user.IsWindow(hwnd) or pid.value!=args[2]:raise ValueError('La ventana cambió antes de enfocar')
            user.IsIconic.argtypes=[W.HWND];user.IsIconic.restype=W.BOOL
            user.ShowWindowAsync.argtypes=[W.HWND,C.c_int];user.ShowWindowAsync.restype=W.BOOL
            if user.IsIconic(hwnd):user.ShowWindowAsync(hwnd,9)
            if not user.SetForegroundWindow(hwnd):
                # The documented ALT activation gesture stays on the single input owner.
                self._check(args[0]);self.held_keys.add('Alt')
                self._send([self._key('Alt',True),self._key('Alt',False)])
                self.held_keys.discard('Alt')
                user.SetForegroundWindow(hwnd)
            return
        if operation=='renew':self.deadline=now+args[1];return
        if operation=='events':
            cursor=W.POINT()
            if not self.user.GetCursorPos(C.byref(cursor)):raise ValueError('No se pudo consultar el cursor')
            x,y=cursor.x,cursor.y
            for event in args[1]:
                self._check(args[0]);kind=event['type']
                if kind=='move':
                    # Relative phone deltas become physical desktop pixels, without Windows applying a second acceleration curve.
                    x,y,ax,ay=desktop_motion(x,y,event['x'],event['y'],self.monitors)
                    self._send([self._mouse(1|0x8000|0x4000,ax,ay)])
                elif kind=='scroll':
                    values=[]
                    if event['y']:values.append(self._mouse(0x800,data=event['y']))
                    if event['x']:values.append(self._mouse(0x1000,data=event['x']))
                    self._send(values)
                elif kind=='button':
                    b=event['button'];down=event['down']
                    if down==(b in self.held_buttons):continue
                    if down:self.held_buttons.add(b);self.pulse_at=now
                    else:self.held_buttons.discard(b)
                    self._send([self._mouse(BUTTONS[b][0 if down else 1])])
                elif kind=='key':
                    key=event['key'];down=event['down']
                    if down==(key in self.held_keys):continue
                    if down:self.held_keys.add(key)
                    else:self.held_keys.discard(key)
                    self._send([self._key(key,down)])
                elif kind=='text':
                    if self.held_keys:raise ValueError('Suelta los modificadores antes de enviar texto Unicode')
                    data=event['text'].encode('utf-16-le');values=[]
                    for i in range(0,len(data),2):
                        unit=int.from_bytes(data[i:i+2],'little')
                        values.extend([Input(1,InputUnion(key=Key(0,unit,4,0,MARKER))),Input(1,InputUnion(key=Key(0,unit,6,0,MARKER)))])
                    self._send(values)

    def _draw(self,now):
        if not self.active and not self.release_at:return
        if self.release_at and now-self.release_at>.15:self.release_at=0;self.user.ShowWindow(self.hwnd,0);return
        point=W.POINT()
        if not self.user.GetCursorPos(C.byref(point)):self._cancel('cursor_unavailable');return
        scale=max(1.,self.user.GetDpiForWindow(self.hwnd)/96.)
        size=max(36,min(192,round(self.size*scale)))
        if self.last_point:
            self.velocity=((point.x-self.last_point[0])*.35+self.velocity[0]*.65,(point.y-self.last_point[1])*.35+self.velocity[1]*.65)
        self.last_point=(point.x,point.y)
        self.user.SetWindowPos(self.hwnd,C.c_void_p(-1),point.x-size//2,point.y-size//2,size,size,0x10|0x40)
        if now-self.last_frame<1/30:return
        self.last_frame=now
        fade=1 if self.reduced else min(1.,(now-self.granted_at)/.15)
        if self.release_at:fade=max(0.,1-(now-self.release_at)/.15)
        image=contour_rgba(self.table,size,fade*self.intensity,(0,0) if self.reduced else self.velocity,bool(self.held_buttons) and not self.reduced,0 if self.reduced else max(0.,1-(now-self.pulse_at)/.18),self.glow,0 if self.reduced else math.sin(now*.5)*.15)
        raw=bytearray(image.tobytes('raw','BGRA'))
        for i in range(0,len(raw),4):
            alpha=raw[i+3]
            for k in range(3):raw[i+k]=raw[i+k]*alpha//255
        if self.bitmap_size!=size:
            if self.bitmap:self.gdi.SelectObject(self.dc,self.old_bitmap);self.gdi.DeleteObject(self.bitmap)
            header=BitmapHeader(C.sizeof(BitmapHeader),size,-size,1,32,0,size*size*4,0,0,0,0)
            self.bitmap=self.gdi.CreateDIBSection(self.dc,C.byref(header),0,C.byref(self.bits),None,0)
            if not self.bitmap:raise OSError('No se pudo crear el indicador')
            self.old_bitmap=self.gdi.SelectObject(self.dc,self.bitmap);self.bitmap_size=size
        C.memmove(self.bits,bytes(raw),len(raw));dest=W.POINT(point.x-size//2,point.y-size//2);origin=W.POINT(0,0);dimensions=W.SIZE(size,size);blend=Blend(0,0,255,1)
        if not self.user.UpdateLayeredWindow(self.hwnd,None,C.byref(dest),C.byref(dimensions),self.dc,C.byref(origin),0,C.byref(blend),2):raise OSError('Windows no pudo mostrar el indicador')

    def _publish(self):
        point=W.POINT();self.user.GetCursorPos(C.byref(point))
        with self.snapshot_lock:self.snapshot={'active':self.active,'source':getattr(self,'source','remote') if self.active else 'physical','reason':self.reason,'keys':sorted(self.held_keys),'buttons':sorted(self.held_buttons),'cursor':{'x':point.x,'y':point.y},'overlay_visible':bool(self.active or self.release_at),'material_key':self.material_key,'monitors':self.monitors}

    def _run(self):
        try:
            self.thread_id=self.kernel.GetCurrentThreadId()
            self.user.SetThreadDpiAwarenessContext(C.c_void_p(-4))
            from backend.magic_pen import monitors
            self.monitors=monitors();geometry_at=time.monotonic()
            @WNDPROC
            def proc(hwnd,msg,wparam,lparam):
                if msg==0x84:return -1  # HTTRANSPARENT
                if msg==0x21:return 3  # MA_NOACTIVATE
                return self.user.DefWindowProcW(hwnd,msg,wparam,lparam)
            @HOOKPROC
            def mouse_hook(code,wparam,lparam):
                if code>=0 and self.active:
                    event=C.cast(lparam,C.POINTER(MouseHook)).contents
                    if event.extra!=MARKER:
                        physical={0x201:'left',0x204:'right',0x207:'middle'}.get(wparam)
                        self._cancel('local_mouse',physical_button=physical)
                return self.user.CallNextHookEx(None,code,wparam,lparam)
            @HOOKPROC
            def key_hook(code,wparam,lparam):
                if code>=0 and self.active:
                    event=C.cast(lparam,C.POINTER(KeyHook)).contents
                    if event.extra!=MARKER:self._cancel('local_keyboard',physical_key=event.vk if wparam in (0x100,0x104) else None)
                return self.user.CallNextHookEx(None,code,wparam,lparam)
            self.callbacks=(proc,mouse_hook,key_hook)
            instance=self.kernel.GetModuleHandleW(None);name='AxxRemoteCursor'+str(id(self));cls=WindowClass(0,proc,0,0,instance,None,None,None,None,name)
            if not self.user.RegisterClassW(C.byref(cls)):raise OSError('No se pudo registrar la superficie')
            # Layered + transparent + no activate + tool window; never replaces the native cursor.
            self.hwnd=self.user.CreateWindowExW(0x80000|0x20|0x08000000|0x80,name,'Axx Remote Cursor',0x80000000,0,0,48,48,None,None,instance,None)
            if not self.hwnd:raise OSError('No se pudo crear la superficie')
            def geometry():
                result=monitors()
                for m in result:
                    probe=self.user.CreateWindowExW(0x08000000|0x80,name,'',0x80000000,m['x'],m['y'],1,1,None,None,instance,None)
                    if not probe:raise OSError('No se pudo consultar la escala de pantalla')
                    try:m['dpi']=self.user.GetDpiForWindow(probe);m['scale']=m['dpi']/96.
                    finally:self.user.DestroyWindow(probe)
                return result
            self.monitors=geometry()
            self.dc=self.gdi.CreateCompatibleDC(None)
            self.ready.set();msg=W.MSG()
            while not self.stopping.is_set():
                for _ in range(64):
                    if not self.user.PeekMessageW(C.byref(msg),None,0,0,1):break
                    self.user.TranslateMessage(C.byref(msg));self.user.DispatchMessageW(C.byref(msg))
                now=time.monotonic()
                if self.active and (self.abort.is_set() or now>=self.deadline or now-self.material_at>5):self._cancel(self.abort_reason if self.abort.is_set() else 'expired_or_revoked')
                try:item=self.commands.get_nowait()
                except queue.Empty:item=None
                if item:
                    try:
                        if now>=item['expires']:raise ValueError('Entrada demasiado antigua; no se ejecutó')
                        item['result']=self._execute(item['op'],item['args'])
                    except Exception as exc:item['error']=str(exc)
                    finally:self._publish();item['done'].set()
                if now-geometry_at>1:
                    current=geometry()
                    if current!=self.monitors and self.active:self._cancel('display_changed')
                    self.monitors=current;geometry_at=now
                try:self._draw(now)
                except Exception as exc:self._cancel('overlay_failed: '+str(exc))
                self._publish()
                # Low-level hooks block the system input path: wake on messages, never sleep through them.
                timeout=0 if not self.commands.empty() else 8 if self.active or self.release_at else 50
                self.user.MsgWaitForMultipleObjectsEx(0,None,timeout,0x04ff,0x0004)
        except Exception as exc:self.error=str(exc);self.ready.set()
        finally:
            self._cancel('shutdown')
            if self.bitmap:self.gdi.SelectObject(self.dc,self.old_bitmap);self.gdi.DeleteObject(self.bitmap)
            if self.dc:self.gdi.DeleteDC(self.dc)
            if self.hwnd:self.user.DestroyWindow(self.hwnd)
