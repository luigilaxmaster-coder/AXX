"""Opt-in native acceptance using only disposable, owned test windows.

Installed: .venv/Scripts/python.exe scripts/verify-computer-use.py --installed
           --await-manual-consent --scope desktop
Wait for ready.json; select its chat in Axx and grant the requested scope
MANUALLY. No Enter is needed afterwards: keep physical input idle.
--self-check opens no windows and never contacts Axx or a model.
Historical source mode authorizes only its own disposable host and fixtures.
"""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from importlib.machinery import SourceFileLoader
from urllib.parse import urlencode
import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
TERMINAL={'completed','failed','unknown','cancelled','limit_reached'}


def require(condition,code):
    if not condition:raise ValueError(code)


def fixture_identity(owner,window):
    from win32process import GetWindowThreadProcessId
    require(type(window.get('pid')) is int and window['pid']>0
            and type(window.get('window_id')) is int and window['window_id']>0,'invalid_fixture_identity')
    require(owner.is_running(),'fixture_launcher_gone')
    # Windows venv's redirector owns a child interpreter with a different PID.
    identity=next((p for p in [owner,*owner.children(recursive=True)] if p.pid==window['pid']),None)
    require(identity is not None and identity.is_running(),'fixture_process_not_owned')
    require(GetWindowThreadProcessId(window['window_id'])[1]==identity.pid,'fixture_window_pid_differed')
    return identity


def stop_fixture(item):
    owner=item['owner'];identity=item.get('identity')
    try:owned=[*owner.children(recursive=True),owner] if owner.is_running() else []
    except psutil.NoSuchProcess:owned=[]
    if identity is not None and all(p.pid!=identity.pid for p in owned):owned.insert(0,identity)
    for process in owned:
        try:
            if process.is_running():process.terminate()
        except psutil.NoSuchProcess:pass
    for process in psutil.wait_procs(owned,timeout=3)[1]:
        try:
            if process.is_running():process.kill()
        except psutil.NoSuchProcess:pass
    item['process'].wait(timeout=5)


def manual_client(api):
    def call(route,body=None,**kwargs):
        require(route.split('?',1)[0]!='/axx-api/computer/begin','manual_mode_never_authorizes')
        return api(route,body,**kwargs)
    return call


def grant_status(api,chat):
    return api('/axx-api/computer/status?'+urlencode({'conversation_id':chat}),timeout=2)


def check_grant(grant,windows,scope):
    require(grant.get('active') is True and isinstance(grant.get('id'),str)
            and re.fullmatch(r'[a-f0-9]{32}',grant['id']),'invalid_grant')
    require(grant.get('scope')==scope,'manual_scope_differed')
    if scope=='window':
        require(all(grant.get(k)==windows[0][k] for k in ('window_id','pid')),'manual_target_differed')
    require(grant.get('phase')=='ready' and type(grant.get('actions')) is int and grant['actions']==0
            and not grant.get('blocked') and not grant.get('last_error'),'grant_not_fresh_and_idle')
    require(type(grant.get('expires_in')) is int and grant['expires_in']>120,'grant_near_expiry')


def empty_baseline(api):
    rows=api('/axx-api/chat/conversations').get('conversations')
    require(isinstance(rows,list),'invalid_chat_list')
    for row in rows:
        require(grant_status(api,row['id']).get('active') is False,'existing_grant_requires_manual_stop')


def await_manual_consent(api,chat,windows,scope,*,timeout=300,pause=time.sleep):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        grant=grant_status(api,chat)
        require(type(grant.get('active')) is bool,'invalid_grant_status')
        if grant['active']:
            try:check_grant(grant,windows,scope)
            except ValueError:
                if grant.get('id') and grant_status(api,chat).get('id')==grant['id']:confirm_stop(api,chat)
                raise
            return grant
        pause(.1)
    raise ValueError('manual_consent_timeout')


def checked_run(result,windows):
    require(result.get('state')=='completed' and result.get('inference_verified') is True,'model_run_not_verified')
    allowed={'axx_computer_status','axx_computer_observe','axx_computer_act','axx_get_task'}
    tools=result.get('tool_results',[])
    require(all(row.get('tool') in allowed for row in tools),'unexpected_tool_requested')
    receipts={};positions={}
    for index,row in enumerate(tools):
        receipt=row.get('result')
        if not isinstance(receipt,dict) or not receipt.get('operation_id'):continue
        operation=receipt['operation_id'];receipts[operation]=receipt
        if receipt.get('state')=='succeeded':positions.setdefault(operation,index)
    actions=[r for r in receipts.values() if r.get('command_id')=='axx.computer.act'
             and r.get('state')=='succeeded' and r.get('output',{}).get('dispatched') is True]
    require(len(actions)==len(windows),'unexpected_dispatched_gesture_count')
    for action in actions:
        output=action['output']
        require(action.get('postconditions_passed') is True and action.get('dispatch_status')=='delivered',
                'gesture_postconditions_not_verified')
        require(set(output.get('expected',{}))=={'region_changed'} and output.get('goal_verified') is False
                and action.get('evidence',{}).get('verification')=='computer_region_changed',
                'visual_change_cannot_certify_goal')
    attached={e.get('data',{}).get('observation_id'):e.get('data',{}).get('image_sha256')
              for e in result.get('events',[]) if e.get('type')=='computer/image_attached'}
    observed=[];owned={(w['window_id'],w['pid']) for w in windows}
    for receipt in receipts.values():
        if receipt.get('command_id')!='axx.computer.observe' or receipt.get('state')!='succeeded':continue
        output=receipt.get('output',{});identity=(output.get('window_id'),output.get('pid'))
        require(identity in owned and output.get('image_scope')=='window','non_fixture_image_observed')
        require(type(output.get('image_width')) is int and output['image_width']>0
                and type(output.get('image_height')) is int and output['image_height']>0,'invalid_image_dimensions')
        digest=output.get('image_sha256','');shot=output.get('observation_id')
        require(isinstance(shot,str) and shot and isinstance(digest,str) and re.fullmatch(r'[a-f0-9]{64}',digest)
                and attached.get(shot)==digest,'image_attachment_not_correlated')
        observed.append((positions[receipt['operation_id']],identity,shot,digest))
    targets=[]
    for action in sorted(actions,key=lambda r:positions[r['operation_id']]):
        index=positions[action['operation_id']]
        before=max((row for row in observed if row[0]<index),default=None)
        require(before is not None,'missing_pre_gesture_fixture_image')
        after=next((row for row in sorted(observed) if row[0]>index and row[1]==before[1]),None)
        require(after is not None and after[2]!=before[2] and after[3]!=before[3],'missing_post_gesture_fixture_image')
        targets.append(before[1])
    require(len(set(targets))==len(windows) and set(targets)==owned,'gestures_not_correlated_to_each_fixture')
    return len(attached),len(actions)


def check_readback(readback,window):
    require(all(readback.get('observation',{}).get(k)==window[k] for k in ('window_id','pid')),'readback_identity_differed')
    require(not readback.get('truncated') and len([r for r in readback.get('controls',[])
            if r.get('name')=='Resultado confirmado' and not r.get('offscreen')])==1,'native_readback_mismatch')


def confirm_stop(api,chat):
    stopped=api('/axx-api/computer/stop',{'conversation_id':chat})
    require(stopped.get('active') is False and grant_status(api,chat).get('active') is False,'stop_not_confirmed')


def target(slot):
    import win32api,win32con as wc,win32gui as wg
    label=None;clicks=0
    def handle(hwnd,msg,wparam,lparam):
        nonlocal clicks
        if msg==wc.WM_COMMAND and wparam&65535==101:
            clicks+=1;wg.SetWindowText(label,'Resultado confirmado')
            print(json.dumps({'clicked':clicks}),flush=True);return 0
        if msg==wc.WM_DESTROY:wg.PostQuitMessage(0);return 0
        return wg.DefWindowProc(hwnd,msg,wparam,lparam)
    instance=win32api.GetModuleHandle(None);cls=wg.WNDCLASS();cls.hInstance=instance
    cls.lpszClassName='AxxComputerUseFixture';cls.lpfnWndProc=handle;cls.hbrBackground=wc.COLOR_WINDOW+1
    cls.hCursor=wg.LoadCursor(0,wc.IDC_ARROW);atom=wg.RegisterClass(cls)
    title='Axx Computer Use · fixture '+('A' if slot==0 else 'B')+' · '+str(os.getpid())
    hwnd=wg.CreateWindow(atom,title,wc.WS_OVERLAPPEDWINDOW,80+slot*620,120,550,330,0,0,instance,None)
    wg.CreateWindow('STATIC','Prueba local: pulse Verificar una sola vez.',wc.WS_CHILD|wc.WS_VISIBLE,30,30,470,40,hwnd,0,instance,None)
    wg.CreateWindow('BUTTON','Verificar',wc.WS_CHILD|wc.WS_VISIBLE|wc.WS_TABSTOP,30,95,180,55,hwnd,101,instance,None)
    label=wg.CreateWindow('STATIC','Pendiente',wc.WS_CHILD|wc.WS_VISIBLE,30,175,470,40,hwnd,102,instance,None)
    wg.ShowWindow(hwnd,wc.SW_SHOW);wg.UpdateWindow(hwnd)
    print(json.dumps({'window_id':hwnd,'pid':os.getpid(),'title':title}),flush=True);wg.PumpMessages()


def self_check():
    from unittest.mock import patch
    class Owned:
        def __init__(self,pid,children=()):self.pid=pid;self.descendants=children;self.running=True
        def is_running(self):return self.running
        def children(self,recursive=False):return list(self.descendants)
        def terminate(self):self.running=False
        def wait(self,timeout):pass
    child=Owned(20);owner=Owned(10,[child]);window={'window_id':30,'pid':20}
    with patch('win32process.GetWindowThreadProcessId',return_value=(1,20)):
        require(fixture_identity(owner,window) is child,'self_check_redirector_child')
        try:fixture_identity(owner,window|{'pid':99})
        except ValueError:pass
        else:raise AssertionError('Accepted an unowned fixture PID')
    with patch('win32process.GetWindowThreadProcessId',return_value=(1,99)):
        try:fixture_identity(owner,window)
        except ValueError:pass
        else:raise AssertionError('Accepted a window belonging to another process')
    with patch('psutil.wait_procs',return_value=([],[])):
        stop_fixture({'owner':owner,'identity':child,'process':owner})
    require(not owner.running and not child.running,'self_check_owned_tree_cleanup')
    foreign=Owned(99);owner.descendants=[foreign];child.running=True
    with patch('psutil.wait_procs',return_value=([],[])):
        stop_fixture({'owner':owner,'identity':child,'process':owner})
    require(not child.running and foreign.running,'self_check_cleanup_preserves_unowned_process')
    window={'window_id':10,'pid':20};grant={'active':True,'id':'a'*32,'scope':'window',
        **window,'phase':'ready','actions':0,'blocked':None,'last_error':None,'expires_in':899}
    calls=[]
    def fixture_api(route,body=None,**_):
        calls.append(route)
        return {'active':False} if len(calls)==1 else grant
    safe=manual_client(fixture_api)
    require(await_manual_consent(safe,'chat',[window],'window',pause=lambda _:None)==grant,'self_check_wait')
    require(len(calls)==2,'self_check_no_extra_wait')
    rejected=0
    for change in ({'active':False},{'scope':'desktop'},{'pid':21},{'actions':1},
                   {'blocked':'unknown'},{'expires_in':1},{'phase':'acting'},{'last_error':'failure'}):
        try:check_grant(grant|change,[window],'window')
        except ValueError:rejected+=1
    require(rejected==8,'self_check_invalid_grants')
    check_grant(grant|{'scope':'desktop','window_id':None,'pid':None},[window],'desktop')
    try:safe('/axx-api/computer/begin',{})
    except ValueError:pass
    else:raise AssertionError('Manual API allowed authorization')
    require(len(calls)==2,'self_check_begin_reached_api')
    rejected_calls=[]
    def rejected_api(route,body=None,**_):
        rejected_calls.append(route)
        return {'active':False} if route.endswith('/stop') or len(rejected_calls)>2 else grant|{'scope':'desktop'}
    try:await_manual_consent(rejected_api,'chat',[window],'window',pause=lambda _:None)
    except ValueError:pass
    else:raise AssertionError('Accepted wrong scope')
    require('/axx-api/computer/stop' in rejected_calls,'self_check_rejected_grant_not_revoked')
    replaced_calls=[]
    def replaced_api(route,body=None,**_):
        replaced_calls.append(route)
        return grant|{'scope':'desktop','id':('a' if len(replaced_calls)==1 else 'b')*32}
    try:await_manual_consent(replaced_api,'chat',[window],'window',pause=lambda _:None)
    except ValueError:pass
    else:raise AssertionError('Accepted wrong scope')
    require('/axx-api/computer/stop' not in replaced_calls,'self_check_replacement_grant_revoked')
    try:empty_baseline(lambda route,**_: {'conversations':[{'id':'existing'}]} if route.endswith('/conversations') else grant)
    except ValueError:pass
    else:raise AssertionError('Accepted an already active grant')
    observations=[];events=[]
    for index in range(2):
        output={**window,'image_scope':'window','image_width':550,'image_height':330,
                'observation_id':str(index),'image_sha256':str(index)*64}
        observations.append({'tool':'axx_computer_observe','result':{'operation_id':'o'+str(index),
            'command_id':'axx.computer.observe','state':'succeeded','output':output}})
        events.append({'type':'computer/image_attached','data':{k:output[k] for k in ('observation_id','image_sha256')}})
    action={'tool':'axx_computer_act','result':{'operation_id':'act','command_id':'axx.computer.act',
        'state':'succeeded','postconditions_passed':True,'dispatch_status':'delivered',
        'output':{'dispatched':True,'expected':{'region_changed':[0,0,10,10]},'goal_verified':False},
        'evidence':{'verification':'computer_region_changed'}}}
    run={'state':'completed','inference_verified':True,'events':events,'tool_results':[observations[0],action,observations[1]]}
    require(checked_run(run,[window])==(2,1),'self_check_receipts')
    second={'window_id':11,'pid':21};desktop=copy.deepcopy(run)
    second_observations=[]
    for index,row in enumerate(observations):
        item=copy.deepcopy(row);item['result']['operation_id']='second-'+str(index)
        output=item['result']['output'];output.update(second,observation_id='second-'+str(index),image_sha256=str(index+2)*64)
        second_observations.append(item)
        desktop['events'].append({'type':'computer/image_attached','data':{k:output[k] for k in ('observation_id','image_sha256')}})
    item=copy.deepcopy(action);item['result']['operation_id']='second-act'
    desktop['tool_results'].extend([second_observations[0],item,second_observations[1]])
    require(checked_run(desktop,[window,second])==(4,2),'self_check_two_fixture_retarget')
    try:checked_run(run|{'tool_results':observations+[action]},[window])
    except ValueError:pass
    else:raise AssertionError('Two pre-images were accepted as before/after')
    bad=copy.deepcopy(run);bad['tool_results'][1]['result']['output']['goal_verified']=True
    try:checked_run(bad,[window])
    except ValueError:pass
    else:raise AssertionError('Visual change certified the goal')
    check_readback({'observation':window,'controls':[{'name':'Resultado confirmado'}]},window)
    try:check_readback({'observation':second,'controls':[{'name':'Resultado confirmado'}]},window)
    except ValueError:pass
    else:raise AssertionError('Accepted readback from another fixture')
    stop_calls=[]
    def stop_api(route,body=None,**_):
        stop_calls.append((route,body));return {'active':False}
    confirm_stop(stop_api,'chat')
    require(stop_calls==[('/axx-api/computer/stop',{'conversation_id':'chat'}),
                        ('/axx-api/computer/status?conversation_id=chat',None)],'self_check_stop')
    try:confirm_stop(lambda *_,**__: {'active':True},'chat')
    except ValueError:pass
    else:raise AssertionError('Accepted an unconfirmed Stop')
    print('PASS: manual admission, fresh grant/scope/target, correlated images, visual uncertainty and independent readback')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed',action='store_true')
    parser.add_argument('--await-manual-consent',action='store_true')
    parser.add_argument('--scope',choices=('window','desktop'),default='window')
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--target',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--target-slot',type=int,choices=(0,1),default=0,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.self_check:return self_check()
    if args.installed!=args.await_manual_consent:parser.error('--installed requires --await-manual-consent; manual consent requires the installed app')
    require(os.name=='nt','windows_required')
    if args.target:return target(args.target_slot)
    from backend.connect.mcp_server import LocalAxxClient
    from backend.actions import windows_automation as uia
    module=SourceFileLoader('computer_check_api',str(ROOT/'scripts/verify-generated-workshop.py')).load_module()
    out=ROOT/'build/computer-use'/('manual-'+uuid.uuid4().hex[:10] if args.installed else 'source-'+uuid.uuid4().hex[:10]);out.mkdir(parents=True)
    services=[];fixtures=[];server=None;chat=None;api=None;request=None;grant=None;result=None
    heartbeat_stop=threading.Event();heartbeat=None;client=None
    try:
        for slot in range(2 if args.scope=='desktop' else 1):
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--target','--target-slot',str(slot)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW,
                env=os.environ|{'PYTHONIOENCODING':'utf-8'})
            lines=queue.Queue()
            def collect(pipe=process.stdout,events=lines):
                for line in pipe:
                    try:events.put(json.loads(line))
                    except ValueError:events.put({'fixture_error':True})
            threading.Thread(target=collect,daemon=True).start()
            fixtures.append({'process':process,'events':lines,'owner':psutil.Process(process.pid)})
            window=lines.get(timeout=15)
            fixtures[-1]['identity']=fixture_identity(fixtures[-1]['owner'],window)
            fixtures[-1]['window']=window
        windows=[item['window'] for item in fixtures]
        if args.installed:
            client=LocalAxxClient();descriptor=client._descriptor();api=manual_client(module.InstalledApi(descriptor))
            status=api('/axx-api/status');snapshot=json.loads((client.data_dir/'logs/native-runtime.json').read_text(encoding='utf-8'))
            require(status.get('ready') is True and status.get('native') is True and status.get('desktop',{}).get('available') is True
                    and status.get('instance_id')==descriptor['instance_id']==snapshot.get('backendInstance')
                    and snapshot.get('backendReady') is True and snapshot.get('backendPort')==descriptor['port']
                    and snapshot.get('version')==json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version'],'installed_identity_not_ready')
            empty_baseline(api)
        else:
            from backend.server import AxxBridgeHandler,ThreadedHTTPServer
            from backend.actions.executor import ActionExecutor
            from backend.commands import CommandService
            from backend.chat_store import ChatStore
            from backend.computer_use import ComputerUse
            from backend.connect.service import ConnectService
            from backend.connect.provider import CodexProvider
            from backend.mobile.control import RemoteControl
            from backend.mcp_host.native_bridge import NativeMcpBridge
            runtime=out/'runtime';runtime.mkdir();state=runtime/'state.db'
            executor=ActionExecutor(state,runtime/'artifacts');commands=CommandService(executor);chats=ChatStore(state)
            control=RemoteControl(None);executor.input_control=control
            computer=ComputerUse(commands);executor.computer_use=computer
            bridge=NativeMcpBridge(runtime);executor.native_bridge=bridge
            connect=ConnectService(commands,None);provider=CodexProvider(commands,state,runtime,dispatcher=connect.dispatch)
            services=[executor,commands,chats,control,computer,bridge,connect,provider]
            material={'key':'computer-use-fixture','reduced':True,'size':48,'intensity':.9,'glow':0}
            control.material(material|{'table':base64.b64encode(bytes([85,170,230,255])*128*128).decode()})
            def refresh_indicator():
                while not heartbeat_stop.wait(1):control.material(material)
            heartbeat=threading.Thread(target=refresh_indicator,daemon=True);heartbeat.start()
            handler=type('ComputerAcceptance',(AxxBridgeHandler,),dict(executor=executor,commands=commands,chats=chats,computer_use=computer,connect=connect,provider=provider))
            server=ThreadedHTTPServer(('127.0.0.1',0),handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            descriptor={'port':server.server_port,'token':server.host_token,'instance_id':server.instance_id}
            api=module.InstalledApi(descriptor)
        title='Verificación Computer Use · '+out.name
        chat=api('/axx-api/chat/create',{'title':title,'command_mode':'ask'})['id']
        connect_id=api('/axx-api/chat/conversations?'+urlencode({'id':chat}))['connect_id']
        for window in windows:
            before=uia.read_window_content(window['window_id'],window['pid'],window['title'],full_window=True,timeout=5)
            require(any(r.get('name')=='Pendiente' for r in before['controls']),'fixture_not_initially_pending')
        if args.await_manual_consent:
            require(grant_status(api,chat).get('active') is False,'new_chat_already_authorized')
            # The API has no human-origin marker; the operator performs the UI grant after this empty baseline.
            ready={'state':'AWAITING_MANUAL_CONSENT','chat_id':chat,'connect_id':connect_id,'chat_title':title,
                   'scope':args.scope,'fixtures':windows,'backend_instance':descriptor['instance_id'],
                   'declared_manual_consent':False,'baseline_empty':True,'timeout_seconds':300}
            (out/'ready.json').write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'ready_file':str(out/'ready.json'),**ready},ensure_ascii=False),flush=True)
            grant=await_manual_consent(api,chat,windows,args.scope)
            require(api('/axx-api/chat/conversations?'+urlencode({'id':chat}))['connect_id']==connect_id,'chat_context_changed')
            engine=api('/axx-api/connect/status?engine=1',timeout=30)
            current=engine.get('engine',{});model=current.get('selected_model')
            require(engine.get('instance_id')==descriptor['instance_id'] and current.get('authenticated') is True
                    and current.get('allow_paid') is False and current.get('inference_verified') is True
                    and isinstance(model,str) and model==current.get('model'),'selected_model_not_verified')
            check_grant(grant_status(api,chat),windows,args.scope)
            require(grant_status(api,chat).get('id')==grant['id'],'grant_changed_before_start')
        else:
            grant=api('/axx-api/computer/begin',{'conversation_id':chat,'scope':args.scope,
                **({k:windows[0][k] for k in ('window_id','pid')} if args.scope=='window' else {}),
                'image_authorized':True,'allow_input':True});model='gpt-6.1-sol'
        request='computer-accept-'+uuid.uuid4().hex
        message=('Prueba local SOLO en estas fixtures propias: '+json.dumps(windows,ensure_ascii=False)+'. '
            'Para cada ventana, en ese orden: llama axx_computer_observe con window_id y pid explícitos; '
            'pulsa Verificar EXACTAMENTE una vez usando x/y de su imagen, sin control_id, con expected.region_changed '
            'en la región de la etiqueta Pendiente. Un cambio visual NO acredita el objetivo: vuelve a observar esa misma '
            'ventana y comprueba Resultado confirmado. Hazlo después en la segunda fixture si existe. '
            'Espera siempre el recibo succeeded de cada operación antes de la siguiente observación. '
            'Usa solo axx_computer_observe, axx_computer_act, axx_computer_status y axx_get_task para esperar recibos. '
            'No observes el escritorio general, no uses otras ventanas, comandos ni terminal. No detengas la sesión: '
            'el verificador comprobará Stop al terminar. Ante incertidumbre detente sin repetir gestos.')
        result=api('/axx-api/connect/start',{'request_id':request,'conversation_id':connect_id,'model':model,'message':message,'origin':'test'},timeout=20)
        end=time.monotonic()+120
        while result['state'] not in TERMINAL and time.monotonic()<end:
            live=grant_status(api,chat)
            require(live.get('active') is True and live.get('id')==grant['id'],'grant_revoked_or_replaced')
            time.sleep(.2);result=api('/axx-api/connect/run?'+urlencode({'request_id':request}))
        (out/'run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        require(result.get('request_id')==request and result.get('conversation_id')==connect_id
                and result.get('runtime_model')==model and result.get('runtime_provider')=='openai','run_identity_differed')
        images,actions=checked_run(result,windows)
        for item in fixtures:
            window=item['window']
            readback=uia.read_window_content(window['window_id'],window['pid'],window['title'],full_window=True,timeout=5)
            check_readback(readback,window)
            clicks=[item['events'].get(timeout=2)]
            while not item['events'].empty():clicks.append(item['events'].get_nowait())
            require(clicks==[{'clicked':1}],'fixture_did_not_receive_one_click')
        confirm_stop(api,chat)
        if client:
            after=client._descriptor()
            require(all(after.get(k)==descriptor.get(k) for k in ('instance_id','port'))
                    and api('/axx-api/status').get('instance_id')==descriptor['instance_id'],'installed_instance_changed')
        report={'result':'COMPUTER_USE_NATIVE_MODEL_PASS','installed':args.installed,'backend_instance':descriptor['instance_id'],
            'installed_version':snapshot['version'] if args.installed else None,
            'model':model,'allow_paid':False,'declared_manual_consent':args.await_manual_consent,'grant_id':grant['id'],
            'scope':args.scope,'fixtures':windows,'images_attached':images,'verified_gestures':actions,
            'independent_native_readback':True,'fixture_goal_verified':True,'visual_change_certifies_goal':False,'revoked':True}
        (out/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'receipt':str(out/'acceptance.json'),**report},ensure_ascii=False),flush=True)
    finally:
        if api and request and (not result or result.get('state') not in TERMINAL):
            try:api('/axx-api/connect/cancel',{'request_id':request})
            except Exception:pass
        if api and chat and grant:
            try:
                if grant_status(api,chat).get('id')==grant['id']:api('/axx-api/computer/stop',{'conversation_id':chat})
            except Exception:pass
        heartbeat_stop.set()
        if heartbeat:heartbeat.join(2)
        for item in fixtures:stop_fixture(item)
        if server:server.shutdown();server.server_close()
        for service in reversed(services):service.close()


if __name__=='__main__':main()
