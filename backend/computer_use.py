"""Explicit desktop or window grant over the existing journal and Windows owner."""
import base64
import json
import re
import threading
import time
import uuid

from .actions import windows_automation as uia
from .actions.desktop_input import execute_action, validate_action
from . import computer_vision as vision


ADAPTERS = {('axx.computer.'+kind): {
    'title':'Computer use: '+kind,'tool':'computer_use_'+kind,'risk':'local_state',
    'requires_approval':False,'aliases':[],
    'description':'Operación interna dentro del alcance autorizado por el propietario; requiere admisión efímera de computer use.',
    'parameters':{'ticket':{'type':'string','required':True,'maxLength':32}}}
    for kind in ('observe','act')}
BLOCKED_PROCESSES={'cmd.exe','powershell.exe','pwsh.exe','windowsterminal.exe','consent.exe',
                   'credentialuibroker.exe','lockapp.exe','winlogon.exe','keepass.exe','1password.exe'}


def predicate(observed, expected):
    rows=[row for row in observed.get('controls',[]) if not row.get('offscreen')]
    found=[row for row in rows if row.get('name')==expected['name']]
    if 'value' in expected:found=[row for row in found if not row.get('value_truncated') and row.get('value')==expected['value']]
    if expected.get('focused'):
        found=[row for row in found if row.get('control_id')==observed.get('focused_control_id')]
    focused_complete=observed.get('focused_only') is True and expected.get('focused') is True and any(row.get('control_id')==observed.get('focused_control_id') for row in rows)
    if observed.get('truncated') and not focused_complete:return False
    return len(found)==1 if expected.get('present',True) else not found


class _Cancellation:
    def __init__(self,*events,deadline):self.events,self.deadline=events,deadline
    def is_set(self):return time.monotonic()>=self.deadline or any(e.is_set() for e in self.events)
    def wait(self,seconds):
        end=time.monotonic()+seconds
        while not self.is_set() and time.monotonic()<end:self.events[0].wait(min(.02,max(0,end-time.monotonic())))
        return self.is_set()


class ComputerUse:
    def __init__(self,commands):
        self.commands=commands;self.lock=threading.RLock();self.grants={};self.admissions={}
    def close(self):
        with self.lock:
            for grant in self.grants.values():grant['cancelled'].set()
            self.grants.clear();self.admissions.clear()
    def _windows(self):
        allowed=[];hidden=[];names={}
        for row in uia.list_windows(include_untitled=True):
            pid=row['pid']
            if pid not in names:names[pid]=uia.process_name(pid).casefold()
            name=names[pid]
            if name in ('axx.exe','axx-backend.exe'):continue
            (hidden if not name or name in BLOCKED_PROCESSES else allowed).append(row)
        return allowed,hidden
    def begin(self,conversation_id,window_id=None,pid=None,*,scope='window',image_authorized=False,allow_input=False):
        from .chat_store import ident
        ident(conversation_id)
        if image_authorized is not True or allow_input is not True:
            raise ValueError('Autoriza explícitamente compartir esta ventana con Codex y controlar su entrada.')
        if scope not in ('window','desktop'):raise ValueError('Elige escritorio completo o una ventana.')
        if scope=='desktop' and (window_id is not None or pid is not None):raise ValueError('El escritorio completo no fija una sola ventana.')
        if scope=='window' and (type(window_id) is not int or type(pid) is not int or min(window_id,pid)<1):
            raise ValueError('Selecciona una ventana observada y su proceso.')
        if scope=='window':
            if uia.process_name(pid).casefold() in BLOCKED_PROCESSES|{'axx.exe','axx-backend.exe'}:
                raise ValueError('Esta superficie no admite computer use; usa los comandos explícitos de Axx.')
            matches=[row for row in uia.list_windows() if row['window_id']==window_id and row['pid']==pid]
            if len(matches)!=1:raise ValueError('La ventana seleccionada ya no está disponible.')
        for operation in self.commands.operations():
            target=(operation.get('evidence') or {}).get('reconciliation_target') or {}
            if (operation.get('state')=='unknown' and target.get('window_id') and (scope=='desktop' or target.get('window_id')==window_id and target.get('pid')==pid)
                    and not (operation.get('evidence') or {}).get('manual_reviewed')):
                raise ValueError('Revisa el efecto incierto '+operation['operation_id']+' en Comandos → Actividad antes de volver a autorizar el control.')
        for current in list(self.grants):self.end(current)
        with self.lock:
            self.grants[conversation_id]={'id':uuid.uuid4().hex,'conversation_id':conversation_id,
                'scope':scope,'window_id':window_id,'pid':pid,'title':matches[0]['title'] if scope=='window' else 'Escritorio completo',
                'birth':uia.process_started(pid) if pid else None,'target_title':None,'phase':'ready',
                'cancelled':threading.Event(),'deadline':time.monotonic()+900,'actions':0,'shot':None,'blocked':None,'last_error':None}
        return self.status(conversation_id)
    def end(self,conversation_id):
        grant=self.grants.get(conversation_id)
        if grant:grant['cancelled'].set()
        with self.lock:
            grant=self.grants.pop(conversation_id,None)
            if grant:grant['cancelled'].set();grant['shot']=None
            self.admissions={ticket:entry for ticket,entry in self.admissions.items() if entry['grant'] is not grant}
        return {'active':False}
    def status(self,conversation_id):
        with self.lock:
            grant=self.grants.get(conversation_id)
            if not grant:return {'active':False}
            if grant['cancelled'].is_set() or time.monotonic()>=grant['deadline']:return self.end(conversation_id)
            return {'active':True,'expires_in':max(0,int(grant['deadline']-time.monotonic())),
                **{k:grant[k] for k in ('id','scope','window_id','pid','title','target_title','phase','actions','blocked','last_error')}}
    def _grant(self,conversation_id,*,target=True):
        grant=self.grants.get(conversation_id)
        if not grant or grant['cancelled'].is_set() or time.monotonic()>=grant['deadline']:
            self.end(conversation_id)
            raise ValueError('Computer use no está autorizado en este chat. Selecciona y autoriza una ventana en Axx.')
        if target and grant['pid'] and uia.process_started(grant['pid'])!=grant['birth']:raise ValueError('Cambió la instancia del proceso autorizado.')
        return grant
    def _target(self,grant,args):
        for key in ('window_id','pid'):
            if key in args:uia._positive_int(args[key],key)
        if grant['scope']=='window':
            if any(args.get(k,grant[k])!=grant[k] for k in ('window_id','pid')):raise ValueError('Este permiso solo admite la ventana seleccionada.')
            return
        if ('window_id' in args)!=('pid' in args):raise ValueError('Indica ventana y proceso observados juntos.')
        rows,_=self._windows()
        if 'window_id' in args:
            rows=[r for r in rows if r['window_id']==args['window_id'] and r['pid']==args['pid']]
            if len(rows)!=1:raise ValueError('La aplicación elegida ya no está disponible o está protegida.')
            row=rows[0]
        else:
            if not rows:raise ValueError('No hay aplicaciones disponibles. Abre una aplicación normal de Windows.')
            row=next((r for r in rows if r.get('foreground')),None) or next((r for r in rows if r['window_id']==grant['window_id'] and r['pid']==grant['pid']),rows[0])
        grant.update(window_id=row['window_id'],pid=row['pid'],birth=uia.process_started(row['pid']),target_title=row['title'] or row.get('class_name') or 'Aplicación')
    def admit(self,name,arguments,run):
        with self.lock:
            if name=='axx_computer_status':return self.status(run['conversation_id'])
            if name=='axx_computer_stop':return self.end(run['conversation_id'])
            grant=self._grant(run['conversation_id'],target=name!='axx_computer_observe')
            account=run.get('account_fingerprint')
            if 'account' in grant and grant['account']!=account:raise ValueError('Cambió la cuenta del modelo; vuelve a autorizar la ventana.')
            grant['account']=account
            kind='observe' if name=='axx_computer_observe' else 'act'
            if kind=='act' and grant['blocked']:raise ValueError('El último efecto es incierto; observa y revísalo antes de continuar.')
            if kind=='act' and grant['actions']>=60:raise ValueError('Se alcanzó el límite de 60 gestos de esta autorización.')
            if len(self.admissions)>=256:raise ValueError('Finaliza la sesión de computer use antes de admitir más trabajo.')
            fingerprint=json.dumps(arguments,sort_keys=True,allow_nan=False)
            for ticket,entry in self.admissions.items():
                if entry['run_id']==run['request_id'] and entry['operation_id']==arguments['operation_id']:
                    if entry['fingerprint']!=fingerprint or entry['kind']!=kind:raise ValueError('La operación ya corresponde a otro gesto.')
                    return {'command_id':'axx.computer.'+kind,'inputs':{'ticket':ticket},'operation_id':entry['operation_id']}
            ticket=uuid.uuid4().hex
            self.admissions[ticket]={'grant':grant,'run_id':run['request_id'],'cancelled':run['_cancel'],
                'deadline':run['_deadline'],'kind':kind,'arguments':dict(arguments),'claimed':False,
                'operation_id':arguments['operation_id'],'fingerprint':fingerprint}
            return {'command_id':'axx.computer.'+kind,'inputs':{'ticket':ticket},'operation_id':arguments['operation_id']}
    def claim(self,ticket,kind,cancelled):
        with self.lock:
            entry=self.admissions.get(ticket)
            if not entry or entry['kind']!=kind or entry['claimed']:raise ValueError('Admisión inexistente o consumida; no se repite el gesto.')
            if self.commands.cancel_events.get(entry['operation_id']) is not cancelled:
                raise ValueError('El ticket no pertenece a esta operación del ejecutor.')
            grant=self._grant(entry['grant']['conversation_id'],target=kind!='observe')
            if grant is not entry['grant']:raise ValueError('La autorización fue sustituida.')
            event=_Cancellation(cancelled,entry['cancelled'],grant['cancelled'],deadline=min(entry['deadline'],grant['deadline']))
            if event.is_set():raise ValueError('Computer use detenido antes del despacho.')
            entry['claimed']=True
            return entry,grant,event
    def _observe(self,grant,event,*,overview=False):
        allowed,hidden=self._windows() if grant['scope']=='desktop' else ([],[])
        shot,output=vision.observe(grant,event,overview=overview,hidden=hidden)
        if grant['scope']=='desktop':output['windows']=[{k:w.get(k) for k in ('window_id','pid','title','class_name','foreground')} for w in allowed]
        return shot,output
    def image_content(self,result,run):
        if not isinstance(result,dict) or result.get('state')!='succeeded' or result.get('command_id')!='axx.computer.observe':return []
        with self.lock:
            entry=self.admissions.get((result.get('inputs') or {}).get('ticket'))
            if not entry or entry['run_id']!=run['request_id']:return []
            grant=self._grant(run['conversation_id']);shot=grant.get('shot')
            if not shot or shot['id']!=(result.get('output') or {}).get('observation_id') or time.monotonic()-shot['at']>60:return []
            return [{'type':'inputImage','imageUrl':'data:image/jpeg;base64,'+base64.b64encode(shot['jpeg']).decode()}]


class ComputerUseTool:
    version='1.1.0'
    def __init__(self,kind):self.kind,self.name=kind,'computer_use_'+kind;self.description='Control visual autorizado: '+kind
    def verify_preconditions(self,inputs):
        valid=isinstance(inputs,dict) and set(inputs)=={'ticket'} and isinstance(inputs.get('ticket'),str) and re.fullmatch(r'[a-f0-9]{32}',inputs['ticket'])
        return bool(valid),'Admisión efímera requerida'
    def execute_with_runtime(self,inputs,workspace,cancelled,runtime):
        from .actions.tools import ToolResult
        service=getattr(runtime,'computer_use',None);entry=grant=None;dispatched=False
        try:
            if not service:raise ValueError('Computer use no está conectado.')
            entry,grant,event=service.claim(inputs['ticket'],self.kind,cancelled)
            grant['last_error']=None
            owner=getattr(runtime,'input_control',None)
            if owner is None:raise ValueError('El dueño de entrada de Windows no está disponible.')
            if self.kind=='observe':
                grant['phase']='observing';service._target(grant,entry['arguments'])
                with owner.automation(event) as control:
                    uia.focus_window(grant['window_id'],grant['pid'],control=control)
                    shot,output=service._observe(grant,control,overview=grant['scope']=='desktop' and 'window_id' not in entry['arguments'])
                with service.lock:grant['shot']=shot
                return ToolResult(True,output=output,evidence={'verification':'computer_window_snapshot','effect_executed':False})
            args=entry['arguments'];old=grant.get('shot')
            if not old or old['id']!=args['observation_id'] or time.monotonic()-old['at']>60:raise ValueError('Observa de nuevo antes de actuar.')
            expected=args.get('expected')
            visual=isinstance(expected,dict) and set(expected)=={'region_changed'}
            if visual:
                box=expected['region_changed'];vision.region(old,box)
                image=old.get('image_bounds') or old['observed']['observation']['window_bounds'];target=old['observed']['observation']['window_bounds']
                left=image['x']+box[0]*image['width']/old['width'];right=image['x']+box[2]*image['width']/old['width']
                top=image['y']+box[1]*image['height']/old['height'];bottom=image['y']+box[3]*image['height']/old['height']
                if not (target['x']<=left<right<=target['x']+target['width'] and target['y']<=top<bottom<=target['y']+target['height']):
                    raise ValueError('La región de comprobación debe pertenecer a la aplicación observada.')
            if expected is not None:
                if not visual and (not isinstance(expected,dict) or not {'name'}<=set(expected) or set(expected)-{'name','value','present','focused'}
                        or not isinstance(expected['name'],str) or not 1<=len(expected['name'])<=200
                        or 'value' in expected and (not isinstance(expected['value'],str) or len(expected['value'])>8192)
                        or any(type(expected[k]) is not bool for k in ('present','focused') if k in expected)):
                    raise ValueError('Comprobación posterior inválida.')
            if args['action']!='move' and expected is None:raise ValueError('Indica una condición observable del resultado antes de este gesto.')
            grant['phase']='acting'
            with owner.automation(event) as control:
                uia.focus_window(grant['window_id'],grant['pid'],control=control)
                if args['action'] in ('type_text','hotkey'):
                    fresh=uia.inspect_focused_control(grant['window_id'],grant['pid'],cancelled=control)
                elif 'x' in args and not args.get('control_id'):
                    shot,_=service._observe(grant,control,overview=old.get('overview',False));fresh=shot['observed']
                else:fresh=uia.read_window_content(grant['window_id'],grant['pid'],old['observed']['window_title'],cancelled=control,full_window=True,timeout=5)
                if expected and not visual:
                    before=fresh
                    if predicate(before,expected):return ToolResult(True,output={'dispatched':False,'already_satisfied':True},evidence={'verification':'computer_expected_control'})
                    fresh=before
                payload={k:v for k,v in args.items() if k in ('action','keys','text','delta_x','delta_y')}
                if args.get('control_id'):
                    previous=next((r for r in old['observed']['controls'] if r['control_id']==args['control_id']),None)
                    rows=[r for r in fresh['controls'] if r['control_id']==args['control_id'] and not r.get('offscreen') and r.get('enabled')]
                    if not previous or len(rows)!=1 or rows[0]['name']!=previous['name']:raise ValueError('Cambió el control elegido; observa otra vez.')
                    if args['action'] not in ('hotkey','type_text'):
                        box=rows[0]['bounds'];payload.update(x=box['x']+box['width']//2,y=box['y']+box['height']//2)
                elif 'x' in args:
                    box=old.get('image_bounds') or fresh['observation']['window_bounds']
                    for x,y in (('x','y'),('to_x','to_y')):
                        if x not in args:continue
                        if (type(args[x]) is not int or type(args.get(y)) is not int or not 0<=args[x]<old['width'] or not 0<=args[y]<old['height']):
                            raise ValueError('Punto fuera de la imagen autorizada.')
                        if not vision.same_target(old,shot,args[x],args[y]):raise ValueError('Cambió la zona del gesto; observa otra vez antes de usar coordenadas.')
                        payload[x]=round(box['x']+args[x]*box['width']/old['width']);payload[y]=round(box['y']+args[y]*box['height']/old['height'])
                if args['action']=='type_text' and not any(r['control_id']==fresh.get('focused_control_id') and r.get('enabled') and not r.get('offscreen')
                        and r.get('control_type') in ('ControlType.Edit','ControlType.Document','ControlType.ComboBox')
                        and r.get('read_only') is False for r in fresh['controls']):
                    raise ValueError('No se identificó un campo de escritura permitido y enfocado.')
                payload.update(window_id=grant['window_id'],pid=grant['pid'],observation_id=fresh['observation']['observation_id'])
                validate_action(payload)
                dispatched=True;grant['actions']+=1
                result=execute_action(payload,control)
                grant['shot']=None
                if args['action']=='move':return ToolResult(**result)
                grant['phase']='verifying'
                deadline=time.monotonic()+5
                while time.monotonic()<deadline and not control.is_set():
                    rows=[r for r in uia.list_windows(include_untitled=True) if r['window_id']==grant['window_id'] and r['pid']==grant['pid']]
                    if len(rows)!=1:break
                    if visual:
                        after=vision.capture(grant,fresh['observation'],control,overview=old.get('overview',False),hidden=service._windows()[1] if old.get('overview') else ())
                        if ((after['width'],after['height'],after['image_bounds'])!=(old['width'],old['height'],old['image_bounds'])):break
                        if vision.region(old,expected['region_changed'])!=vision.region(after,expected['region_changed']):
                            return ToolResult(True,output={'dispatched':True,'expected':expected,'goal_verified':False,'next':'Observa la nueva imagen para comprobar el objetivo; solo se confirmó un cambio en la región.'},evidence={'verification':'computer_region_changed'})
                    else:
                        after=(uia.inspect_focused_control(grant['window_id'],grant['pid'],cancelled=control) if expected.get('focused') else
                               uia.read_window_content(grant['window_id'],grant['pid'],rows[0]['title'],cancelled=control,full_window=True,timeout=3))
                        if predicate(after,expected):return ToolResult(True,output={'dispatched':True,'expected':expected},evidence={'verification':'computer_expected_control'})
                    control.wait(.15)
                raise uia.UncertainEffect('Entrada entregada; no se verificó el resultado esperado. Observa y revisa antes de continuar.')
        except Exception as exc:
            uncertain=dispatched or isinstance(exc,uia.UncertainEffect)
            if grant:grant['last_error']=str(exc)[:500]
            if uncertain and grant:grant['blocked']=entry['operation_id']
            if grant and getattr(exc,'input_cancelled',False):service.end(grant['conversation_id'])
            return ToolResult(False,error=str(exc)[:500],evidence={'effect_uncertain':uncertain,'reconciliation_required':uncertain,
                'reconciliation_target':{'window_id':grant['window_id'],'pid':grant['pid']} if grant else None})
        finally:
            if grant:grant['phase']='blocked' if grant['blocked'] else 'ready'
    def verify_postconditions(self,inputs,result):
        good=result.success and result.evidence.get('verification') in ('computer_window_snapshot','computer_expected_control','computer_region_changed','cursor_readback')
        return bool(good),'Observación y comprobación posteriores; no acredita el objetivo completo'


TOOLS={tool.name:tool for tool in (ComputerUseTool('observe'),ComputerUseTool('act'))}
