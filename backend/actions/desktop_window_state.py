"""Observed top-level window changes with native state/geometry readback."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import threading
import time
import uuid

from . import windows_automation as windows
from .desktop_input import _bind, _interactive_session, _process_identity


ACTIONS = ('restore', 'minimize', 'maximize', 'move_resize')
PARAMETERS = {
    'observation_id': {'type':'string', 'minLength':1, 'maxLength':80},
    'window_id': {'type':'integer', 'minimum':1},
    'pid': {'type':'integer', 'minimum':1},
    'action': {'type':'string', 'enum':list(ACTIONS)},
    'bounds': {'type':'object', 'required':['x','y','width','height'], 'additionalProperties':False,
               'properties':{'x':{'type':'integer','minimum':-1000000,'maximum':1000000},
                             'y':{'type':'integer','minimum':-1000000,'maximum':1000000},
                             'width':{'type':'integer','minimum':64,'maximum':32768},
                             'height':{'type':'integer','minimum':64,'maximum':32768}}},
}


def validate_action(inputs):
    if not isinstance(inputs, dict) or inputs.get('action') not in ACTIONS:
        raise ValueError('Estado de ventana desconocido')
    fields = {'observation_id','window_id','pid','action'}
    if inputs['action']=='move_resize': fields.add('bounds')
    if set(inputs)!=fields:
        raise ValueError('Parámetros de ventana incompletos o no admitidos')
    if not isinstance(inputs['observation_id'], str) or not 1<=len(inputs['observation_id'])<=80:
        raise ValueError('Observación requerida')
    windows._positive_int(inputs['window_id'],'window_id');windows._positive_int(inputs['pid'],'pid')
    if 'bounds' in inputs:
        bounds=inputs['bounds']
        if not isinstance(bounds,dict) or set(bounds)!={'x','y','width','height'}:
            raise ValueError('Geometría de ventana inválida')
        for name in bounds:
            low,high=(-1000000,1000000) if name in ('x','y') else (64,32768)
            if type(bounds[name]) is not int or not low<=bounds[name]<=high:
                raise ValueError('Geometría física fuera de rango')


def _reachable(bounds, monitors):
    # Keep a usable part of the top edge on a monitor instead of losing the window.
    return any(min(bounds['x']+bounds['width'],m['x']+m['width'])-max(bounds['x'],m['x'])>=64
               and min(bounds['y']+32,m['y']+m['height'])-max(bounds['y'],m['y'])>=16 for m in monitors)


def _state(user, kernel, target, *, before=False):
    observed=target['observation'];hwnd=observed['window_id'];pid=observed['pid']
    _interactive_session(user,kernel,pid)
    actual=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(actual))
    if not user.IsWindow(hwnd) or actual.value!=pid or _process_identity(kernel,pid)!=observed.get('process_started'):
        raise ValueError('Cambió la identidad del proceso o ventana')
    root=_bind(user,'GetAncestor',[W.HWND,W.UINT],W.HWND)(hwnd,2)
    shell=_bind(user,'GetShellWindow',[],W.HWND)()
    desktop=_bind(user,'GetDesktopWindow',[],W.HWND)()
    if int(root or 0)!=hwnd or hwnd in (int(shell or 0),int(desktop or 0)) or not user.IsWindowVisible(hwnd):
        raise ValueError('Se requiere una ventana de aplicación visible y de nivel superior')
    title=C.create_unicode_buffer(2049);user.GetWindowTextW(hwnd,title,len(title))
    if title.value!=target['window_title']:
        raise ValueError('Cambió el título o documento observado')
    geometry=windows.observe_geometry(hwnd)
    if geometry['monitors']!=observed.get('monitors'):
        raise ValueError('Cambió la topología de pantallas')
    if before and any(geometry[k]!=observed.get(k) for k in ('window_bounds','minimized')):
        raise ValueError('La ventana cambió desde la observación; vuelve a observarla')
    return {'window_id':hwnd,'pid':pid,'process_started':observed['process_started'],
            'bounds':geometry['window_bounds'],'minimized':geometry['minimized'],
            'maximized':bool(_bind(user,'IsZoomed',[W.HWND],W.BOOL)(hwnd)),
            'monitors':geometry['monitors']}


def _matches(action, state, bounds=None):
    if action=='minimize': return state['minimized']
    if action=='maximize': return state['maximized'] and not state['minimized']
    if action=='restore': return not state['minimized'] and not state['maximized']
    return not state['minimized'] and not state['maximized'] and state['bounds']==bounds


def observe_window_state(window_id, pid, cancelled=None):
    """Observe minimized windows without claiming their UI content is readable."""
    windows._positive_int(window_id,'window_id');windows._positive_int(pid,'pid')
    if cancelled is not None and cancelled.is_set():raise ValueError('Observación cancelada')
    user,kernel=windows._windows_api()
    geometry=windows.observe_geometry(window_id)
    title=C.create_unicode_buffer(2049);user.GetWindowTextW(window_id,title,len(title))
    target={'window_title':title.value, 'controls':[], 'truncated':False,
            'quality':'geometry_only', 'ui_content_status':'not_observed',
            'window_id':window_id, 'pid':pid,
            'observation':{'schema_version':1,'observation_id':str(uuid.uuid4()),
                'session_id':windows.OBSERVATION_SESSION_ID,'window_id':window_id,'pid':pid,
                'process_started':_process_identity(kernel,pid),'completed_monotonic':time.monotonic(),
                'coordinate_space':'physical_virtual_desktop','screenshot':None,
                'coordinate_epoch':hashlib.sha256(json.dumps([geometry['window_bounds'],geometry['monitors']],sort_keys=True).encode()).hexdigest(),
                **geometry}}
    state=_state(user,kernel,target,before=True)
    if cancelled is not None and cancelled.is_set():raise ValueError('Observación cancelada')
    target['observation_id']=target['observation']['observation_id']
    target['state']=state
    windows._remember_observation(target)
    return target


def execute_action(inputs, control):
    validate_action(inputs)
    if control is None or control.is_set():raise ValueError('Se requiere control local vigente')
    target=windows.get_observation(inputs['observation_id'],inputs['window_id'],inputs['pid'])
    user,kernel=windows._windows_api();action=inputs['action'];bounds=inputs.get('bounds')
    initial=_state(user,kernel,target,before=True)
    if action=='move_resize':
        if initial['minimized'] or initial['maximized']:
            raise ValueError('Restaura primero la ventana y obtiene una observación nueva')
        if not _reachable(bounds,initial['monitors']):
            raise ValueError('La posición dejaría la ventana fuera de las pantallas disponibles')
    dispatched=False
    try:
        current=initial
        if not _matches(action,current,bounds):
            if control.is_set():raise ValueError('Cambio cancelado antes del despacho')
            # Re-resolve expiry immediately before dispatch, without changing the approved target.
            windows.get_observation(inputs['observation_id'],inputs['window_id'],inputs['pid'])
            _state(user,kernel,target,before=True)
            if control.is_set():raise ValueError('Cambio cancelado antes del despacho')
            dispatched=True
            if action=='move_resize':
                from backend.magic_pen import physical_dpi_context
                with physical_dpi_context():
                    result=_bind(user,'SetWindowPos',[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL)(
                        inputs['window_id'],None,bounds['x'],bounds['y'],bounds['width'],bounds['height'],0x4000|0x10|0x4|0x200)
            else:
                result=_bind(user,'ShowWindowAsync',[W.HWND,C.c_int],W.BOOL)(inputs['window_id'],{'restore':1,'minimize':7,'maximize':3}[action])
            if not result:raise ValueError('Windows no confirmó el despacho del cambio')
            deadline=time.monotonic()+3.0
            while True:
                if control.is_set():raise ValueError('Cambio detenido; el efecto puede haberse producido')
                current=_state(user,kernel,target)
                if _matches(action,current,bounds):break
                if time.monotonic()>=deadline:raise ValueError('El estado leído no coincide con el solicitado')
                if control.wait(.05):raise ValueError('Cambio detenido durante la comprobación')
        output={**current,'action':action,'observation_id':inputs['observation_id'],
                'dispatch_status':'delivered' if dispatched else 'not_delivered','effect_status':'confirmed'}
        return {'success':True,'output':output,'evidence':{'accepted':True,'verification':'window_state_readback',
                'before':initial,'after':current,'unchanged':not dispatched}}
    except Exception as exc:
        if dispatched:
            unknown=windows.UncertainEffect('Cambio de ventana enviado; resultado pendiente de conciliar: '+str(exc))
            unknown.target={'window_id':inputs['window_id'],'pid':inputs['pid'],'observation_id':inputs['observation_id']}
            raise unknown from exc
        raise


class WindowStateTool:
    name='desktop_window_state'
    version='1.0.0'
    description='Estado o geometría de una ventana observada con lectura nativa posterior'

    def verify_preconditions(self, inputs):
        try:validate_action(inputs);return True,'Parámetros de ventana válidos'
        except (ValueError,TypeError) as exc:return False,str(exc)

    def execute(self, inputs):
        from .tools import ToolResult
        return ToolResult(False,error='El dueño de entrada de Windows no está conectado')

    def execute_with_runtime(self, inputs, workspace_root, cancelled, runtime):
        from .tools import ToolResult
        if getattr(runtime,'input_control',None) is None:return self.execute(inputs)
        try:
            with runtime.input_control.automation(cancelled) as control:
                return ToolResult(**execute_action(inputs,control))
        except windows.UncertainEffect as exc:
            return ToolResult(False,error=str(exc),evidence={'effect_uncertain':True,'reconciliation_required':True,
                              'reconciliation_target':getattr(exc,'target',None)})
        except (ValueError,OSError) as exc:
            return ToolResult(False,error=str(exc),evidence={'cancelled':cancelled.is_set() or getattr(exc,'input_cancelled',False)})

    def verify_postconditions(self, inputs, result):
        valid=(result.success and isinstance(result.output,dict) and result.evidence.get('verification')=='window_state_readback'
               and result.output.get('window_id')==inputs['window_id'] and result.output.get('pid')==inputs['pid']
               and _matches(inputs['action'],result.output,inputs.get('bounds')))
        return bool(valid),'Estado y geometría verificados' if valid else result.error or 'Estado no verificado'


class WindowObservationTool:
    name='desktop_window_observe'
    version='1.0.0'
    description='Geometría e identidad nativas, incluso minimizada; no acredita contenido UI'

    def verify_preconditions(self, inputs):
        try:
            if not isinstance(inputs,dict) or set(inputs)!={'window_id','pid'}:raise ValueError('Indica ventana y proceso')
            for key in ('window_id','pid'):windows._positive_int(inputs[key],key)
            return True,'Destino tipado válido'
        except (ValueError,TypeError) as exc:return False,str(exc)

    def execute(self, inputs):return self.execute_cancellable(inputs,None,threading.Event())

    def execute_cancellable(self, inputs, workspace_root, cancelled):
        from .tools import ToolResult
        try:
            result=observe_window_state(inputs['window_id'],inputs['pid'],cancelled)
            return ToolResult(True,output=result,evidence={'verification':'native_window_geometry',
                              'ui_content_observed':False,'observation_id':result['observation_id']})
        except (ValueError,OSError) as exc:return ToolResult(False,error=str(exc),evidence={'cancelled':cancelled.is_set()})

    def verify_postconditions(self, inputs, result):
        valid=(result.success and result.evidence.get('verification')=='native_window_geometry'
               and result.output.get('window_id')==inputs['window_id'] and result.output.get('pid')==inputs['pid']
               and result.output.get('quality')=='geometry_only' and bool(result.output.get('observation_id')))
        return bool(valid),'Geometría observada; contenido UI no leído' if valid else result.error or 'Geometría no verificada'
