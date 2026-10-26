"""Bounded input on the existing Windows owner, bound to a trusted observation.

SendInput delivery is not an application postcondition. Mutations retain an
unknown effect until another registered observation verifies their result.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import time

from backend.mobile.control import checked_events
from . import windows_automation as windows

MAX_AGE = 15.0
_FIELDS = {
    'move': {'x', 'y'}, 'click': {'x', 'y'}, 'double_click': {'x', 'y'},
    'right_click': {'x', 'y'}, 'drag': {'x', 'y', 'to_x', 'to_y'},
    'scroll': {'x', 'y', 'delta_x', 'delta_y'}, 'hotkey': {'keys'},
    'type_text': {'text'},
}


def validate_action(inputs):
    if not isinstance(inputs, dict) or not isinstance(inputs.get('action'), str) or inputs['action'] not in _FIELDS:
        raise ValueError('Acción de entrada desconocida')
    action = inputs['action']
    if set(inputs) != {'observation_id', 'window_id', 'pid', 'action'} | _FIELDS[action]:
        raise ValueError('La acción requiere sólo sus argumentos tipados y una observación')
    if not isinstance(inputs['observation_id'], str) or not 1 <= len(inputs['observation_id']) <= 80:
        raise ValueError('Observación requerida')
    for name in ('window_id', 'pid'):
        windows._positive_int(inputs[name], name)
    for name in _FIELDS[action] & {'x', 'y', 'to_x', 'to_y'}:
        if type(inputs[name]) is not int or abs(inputs[name]) > 1000000:
            raise ValueError('Coordenada física inválida')
    if action == 'scroll':
        checked_events([{'type': 'scroll', 'x': inputs['delta_x'], 'y': inputs['delta_y']}])
        if not inputs['delta_x'] and not inputs['delta_y']:
            raise ValueError('El desplazamiento no puede estar vacío')
    if action == 'type_text':
        checked_events([{'type': 'text', 'text': inputs['text']}])
    if action == 'hotkey':
        keys = inputs['keys']
        if not isinstance(keys, list) or not 1 <= len(keys) <= 4 or any(not isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
            raise ValueError('Combinación de teclas inválida')
        modifiers = {'Control', 'Alt', 'Shift'}
        if any(k not in modifiers for k in keys[:-1]) or keys[-1] in modifiers or 'Meta' in keys:
            raise ValueError('Usa modificadores y una tecla de aplicación; no atajos del sistema')
        if 'Alt' in keys and keys[-1] in ('Tab', 'Escape') or {'Control', 'Alt', 'Delete'} <= set(keys):
            raise ValueError('El atajo cambia de escritorio o destino')
        checked_events([{'type': 'key', 'key': k, 'down': True} for k in keys])


def _inside(point, bounds):
    x, y = point
    return bounds['x'] <= x < bounds['x'] + bounds['width'] and bounds['y'] <= y < bounds['y'] + bounds['height']


def _bind(dll, name, args, result):
    fn = getattr(dll, name); fn.argtypes = args; fn.restype = result
    return fn


def _interactive_session(user, kernel, pid):
    query_session = _bind(kernel, 'ProcessIdToSessionId', [W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
    own, target = W.DWORD(), W.DWORD()
    if not query_session(os.getpid(), C.byref(own)) or not query_session(pid, C.byref(target)) or not own.value or own.value != target.value:
        raise ValueError('La sesión interactiva del destino no está disponible')
    wts = C.WinDLL('wtsapi32', use_last_error=True)
    query = _bind(wts, 'WTSQuerySessionInformationW', [W.HANDLE, W.DWORD, C.c_int, C.POINTER(C.c_void_p), C.POINTER(W.DWORD)], W.BOOL)
    free = _bind(wts, 'WTSFreeMemory', [C.c_void_p], None)
    data, size = C.c_void_p(), W.DWORD()
    if not query(None, own.value, 8, C.byref(data), C.byref(size)):
        raise ValueError('No se pudo verificar que la sesión esté conectada')
    try:
        if size.value < C.sizeof(C.c_int) or C.cast(data, C.POINTER(C.c_int)).contents.value != 0:
            raise ValueError('La sesión está desconectada o bloqueada')
    finally:
        free(data)
    desktop = _bind(user, 'OpenInputDesktop', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)(0, False, 1)
    if not desktop:
        raise ValueError('El escritorio está bloqueado, seguro o no observable')
    try:
        name, needed = C.create_unicode_buffer(256), W.DWORD()
        info = _bind(user, 'GetUserObjectInformationW', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
        if not info(desktop, 2, name, C.sizeof(name), C.byref(needed)) or name.value.lower() != 'default':
            raise ValueError('Sólo se permite entrada en el escritorio interactivo normal')
    finally:
        _bind(user, 'CloseDesktop', [W.HANDLE], W.BOOL)(desktop)


def _process_identity(kernel, pid):
    handle = _bind(kernel, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)(0x1000, False, pid)
    if not handle:
        raise ValueError('No se pudo verificar el proceso del destino')
    close = _bind(kernel, 'CloseHandle', [W.HANDLE], W.BOOL)
    try:
        created, ended, kt, ut = (W.FILETIME() for _ in range(4))
        times = _bind(kernel, 'GetProcessTimes', [W.HANDLE, *[C.POINTER(W.FILETIME)] * 4], W.BOOL)
        if not times(handle, C.byref(created), C.byref(ended), C.byref(kt), C.byref(ut)):
            raise ValueError('No se pudo verificar el inicio del proceso')
        advapi = C.WinDLL('advapi32', use_last_error=True)
        open_token = _bind(advapi, 'OpenProcessToken', [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL)
        token_info = _bind(advapi, 'GetTokenInformation', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
        sub_count = _bind(advapi, 'GetSidSubAuthorityCount', [C.c_void_p], C.POINTER(C.c_ubyte))
        sub_value = _bind(advapi, 'GetSidSubAuthority', [C.c_void_p, W.DWORD], C.POINTER(W.DWORD))
        def integrity(process):
            token, length = W.HANDLE(), W.DWORD()
            if not open_token(process, 8, C.byref(token)):
                raise ValueError('No se pudo verificar integridad del proceso')
            try:
                token_info(token, 25, None, 0, C.byref(length))
                if not 1 <= length.value <= 65536:
                    raise ValueError('Nivel de integridad inválido')
                buf = C.create_string_buffer(length.value)
                if not token_info(token, 25, buf, length.value, C.byref(length)):
                    raise ValueError('No se pudo leer integridad del proceso')
                sid = C.cast(buf, C.POINTER(C.c_void_p)).contents.value
                count = sub_count(sid).contents.value
                if not count: raise ValueError('SID de integridad inválido')
                return sub_value(sid, count - 1).contents.value
            finally:
                close(token)
        own = _bind(kernel, 'GetCurrentProcess', [], W.HANDLE)()
        if integrity(handle) > integrity(own):
            raise ValueError('UIPI: la ventana elevada requiere intervención del usuario')
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        close(handle)


def verify_target(target, *, point=None, keyboard=False, cursor=False):
    """Called on the input owner thread immediately before each native packet."""
    observed = target['observation']
    age = time.monotonic() - observed['completed_monotonic']
    if not 0 <= age <= MAX_AGE:
        raise ValueError('La observación caducó; observa de nuevo antes de actuar')
    user, kernel = windows._windows_api()
    hwnd, pid = observed['window_id'], observed['pid']
    _interactive_session(user, kernel, pid)
    actual_pid = W.DWORD()
    user.GetWindowThreadProcessId(hwnd, C.byref(actual_pid))
    if not user.IsWindow(hwnd) or actual_pid.value != pid or _process_identity(kernel, pid) != observed['process_started']:
        raise ValueError('La identidad del proceso o ventana cambió')
    if not user.IsWindowVisible(hwnd) or _bind(user, 'IsIconic', [W.HWND], W.BOOL)(hwnd):
        raise ValueError('La ventana no está visible y restaurada')
    if int(user.GetForegroundWindow() or 0) != hwnd:
        raise ValueError('El destino perdió el foco; no se envió entrada')
    title = C.create_unicode_buffer(2049)
    user.GetWindowTextW(hwnd, title, len(title))
    if title.value != target['window_title']:
        raise ValueError('El título o documento cambió; observa de nuevo')
    rect = W.RECT()
    if not _bind(user, 'GetWindowRect', [W.HWND, C.POINTER(W.RECT)], W.BOOL)(hwnd, C.byref(rect)):
        raise ValueError('No se pudo verificar la geometría')
    bounds = dict(x=rect.left, y=rect.top, width=rect.right-rect.left, height=rect.bottom-rect.top)
    from backend.magic_pen import monitors
    if bounds != observed['window_bounds'] or monitors() != observed['monitors']:
        raise ValueError('Cambió la geometría o la topología; observa de nuevo')
    if keyboard:
        class GUIThreadInfo(C.Structure):
            _fields_ = [('cbSize', W.DWORD), ('flags', W.DWORD), *[(key, W.HWND) for key in ('active','focus','capture','menu','move','caret')], ('rect', W.RECT)]
        info = GUIThreadInfo(); info.cbSize = C.sizeof(info)
        query = _bind(user, 'GetGUIThreadInfo', [W.DWORD, C.POINTER(GUIThreadInfo)], W.BOOL)
        if not observed.get('focus_hwnd') or not query(0, C.byref(info)) or int(info.focus or 0) != observed['focus_hwnd']:
            raise ValueError('Cambió el control de texto o no se puede identificar su foco')
    if cursor:
        location = W.POINT()
        if not _bind(user, 'GetCursorPos', [C.POINTER(W.POINT)], W.BOOL)(C.byref(location)):
            raise ValueError('No se pudo verificar el cursor')
        point = (location.x, location.y)
    if point is not None:
        if len(point) != 2 or not _inside(point, bounds) or not any(_inside(point, m) for m in observed['monitors']):
            raise ValueError('El punto está fuera del destino observado')
        hit = _bind(user, 'WindowFromPoint', [W.POINT], W.HWND)(W.POINT(*point))
        root = _bind(user, 'GetAncestor', [W.HWND, W.UINT], W.HWND)(hit, 2)
        if int(root or 0) != hwnd:
            raise ValueError('El punto está cubierto por otra ventana')


def execute_action(inputs, control):
    validate_action(inputs)
    if control is None or control.is_set():
        raise ValueError('Se requiere una concesión de entrada local vigente')
    target = windows.get_observation(inputs['observation_id'], inputs['window_id'], inputs['pid'], max_age=MAX_AGE)
    action = inputs['action']
    points = [(inputs['x'], inputs['y'])] if 'x' in inputs else []
    if action == 'drag': points.append((inputs['to_x'], inputs['to_y']))
    if any(not _inside(point, target['observation']['window_bounds']) or
           not any(_inside(point, monitor) for monitor in target['observation']['monitors']) for point in points):
        raise ValueError('El gesto sale del destino observado; requiere otra tarea con ambos destinos')
    control.targeted(target, 'check')
    dispatched = False
    def packet(kind, values):
        nonlocal dispatched
        if control.is_set(): raise ValueError('Entrada detenida por el usuario')
        dispatched = True
        return control.targeted(target, kind, values)
    def events(values): return packet('events', values)
    try:
        if action in ('move','click','double_click','right_click','drag','scroll'):
            moved = packet('move_absolute', (inputs['x'], inputs['y']))
            if not moved.get('confirmed'):
                raise ValueError('El cursor no alcanzó el punto solicitado')
        if action in ('click','double_click','right_click','drag'):
            button = 'right' if action == 'right_click' else 'left'
            for _ in range(2 if action == 'double_click' else 1):
                events([{'type':'button','button':button,'down':True}])
                if action == 'drag':
                    for step in range(1, 13):
                        x = round(inputs['x'] + (inputs['to_x']-inputs['x'])*step/12)
                        y = round(inputs['y'] + (inputs['to_y']-inputs['y'])*step/12)
                        packet('move_absolute', (x,y))
                        if control.wait(.01): raise ValueError('Arrastre detenido por el usuario')
                events([{'type':'button','button':button,'down':False}])
        elif action == 'scroll':
            events([{'type':'scroll','x':inputs['delta_x'],'y':inputs['delta_y']}])
        elif action == 'hotkey':
            events([{'type':'key','key':key,'down':True} for key in inputs['keys']] +
                   [{'type':'key','key':key,'down':False} for key in reversed(inputs['keys'])])
        elif action == 'type_text':
            # Return to the owner's message loop between chunks so physical input wins.
            for offset in range(0, len(inputs['text']), 32):
                events([{'type':'text','text':inputs['text'][offset:offset+32]}])
        output = {'action':action, 'observation_id':inputs['observation_id'], 'window_id':inputs['window_id'],
                  'pid':inputs['pid'], 'dispatch_status':'delivered', 'effect_status':'confirmed' if action=='move' else 'unknown'}
        evidence = {'accepted':True, 'verification':'cursor_readback' if action=='move' else 'input_delivery_only',
                    'effect_uncertain':action!='move', 'reconciliation_required':action!='move'}
        if action == 'move': output.update(moved)
        return {'success':True, 'output':output, 'evidence':evidence}
    except Exception as exc:
        if dispatched:
            unknown = windows.UncertainEffect('Entrada enviada o parcial; requiere observación independiente: '+str(exc))
            unknown.target = {'window_id':inputs['window_id'], 'pid':inputs['pid'], 'observation_id':inputs['observation_id']}
            raise unknown from exc
        raise
