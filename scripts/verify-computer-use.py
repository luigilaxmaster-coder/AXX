"""Opt-in Windows/Codex check using only a disposable native test window.

Run with .venv/Scripts/python.exe scripts/verify-computer-use.py [--installed].
The real model receives the authorized fixture image. No user window is captured.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from importlib.machinery import SourceFileLoader

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def target():
    import win32api,win32con as wc,win32gui as wg
    label=None
    def handle(hwnd,msg,wparam,lparam):
        if msg==wc.WM_COMMAND and wparam&65535==101:
            wg.SetWindowText(label,'Resultado confirmado')
            print(json.dumps({'clicked':True}),flush=True);return 0
        if msg==wc.WM_DESTROY:wg.PostQuitMessage(0);return 0
        return wg.DefWindowProc(hwnd,msg,wparam,lparam)
    instance=win32api.GetModuleHandle(None);cls=wg.WNDCLASS();cls.hInstance=instance
    cls.lpszClassName='AxxComputerUseFixture';cls.lpfnWndProc=handle;cls.hbrBackground=wc.COLOR_WINDOW+1
    cls.hCursor=wg.LoadCursor(0,wc.IDC_ARROW);atom=wg.RegisterClass(cls)
    hwnd=wg.CreateWindow(atom,'Axx Computer Use · prueba aislada',wc.WS_OVERLAPPEDWINDOW,120,120,650,360,0,0,instance,None)
    wg.CreateWindow('STATIC','Prueba local: pulse Verificar para confirmar el resultado.',wc.WS_CHILD|wc.WS_VISIBLE,35,35,560,45,hwnd,0,instance,None)
    wg.CreateWindow('BUTTON','Verificar',wc.WS_CHILD|wc.WS_VISIBLE|wc.WS_TABSTOP,35,100,180,55,hwnd,101,instance,None)
    label=wg.CreateWindow('STATIC','Pendiente',wc.WS_CHILD|wc.WS_VISIBLE,35,185,560,45,hwnd,102,instance,None)
    wg.ShowWindow(hwnd,wc.SW_SHOW);wg.UpdateWindow(hwnd)
    print(json.dumps({'window_id':hwnd,'pid':os.getpid()}),flush=True);wg.PumpMessages()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installed',action='store_true');parser.add_argument('--target',action='store_true');args=parser.parse_args()
    if args.target:return target()
    from backend.server import AxxBridgeHandler,ThreadedHTTPServer
    from backend.actions.executor import ActionExecutor
    from backend.commands import CommandService
    from backend.chat_store import ChatStore
    from backend.computer_use import ComputerUse
    from backend.connect.service import ConnectService
    from backend.connect.provider import CodexProvider
    from backend.connect.mcp_server import LocalAxxClient
    from backend.mobile.control import RemoteControl
    from backend.mcp_host.native_bridge import NativeMcpBridge
    module=SourceFileLoader('computer_check_api',str(ROOT/'scripts/verify-generated-workshop.py')).load_module()
    out=ROOT/'build/computer-use';out.mkdir(parents=True,exist_ok=True)
    services=[];server=None;chat=None;api=None;heartbeat_stop=threading.Event();heartbeat=None
    fixture=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--target'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        window=json.loads(fixture.stdout.readline());assert window['pid']>0
        if args.installed:descriptor=LocalAxxClient()._descriptor()
        else:
            runtime=out/('runtime-'+uuid.uuid4().hex[:10]);runtime.mkdir();state=runtime/'state.db'
            executor=ActionExecutor(state,runtime/'artifacts');commands=CommandService(executor);chats=ChatStore(state)
            control=RemoteControl(None);executor.input_control=control
            computer=ComputerUse(commands);executor.computer_use=computer
            bridge=NativeMcpBridge(runtime);executor.native_bridge=bridge
            connect=ConnectService(commands,None);provider=CodexProvider(commands,state,runtime,dispatcher=connect.dispatch)
            services=[executor,commands,chats,control,computer,bridge,connect,provider]
            # The disposable host supplies a real visible test indicator, without altering Axx's saved material.
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
        chat=api('/axx-api/chat/create',{'title':'Verificación Computer Use','command_mode':'ask'})['id']
        connect_id=api('/axx-api/chat/conversations?id='+chat)['connect_id']
        api('/axx-api/computer/begin',{'conversation_id':chat,**window,'image_authorized':True,'allow_input':True})
        request='computer-accept-'+uuid.uuid4().hex
        message=('En la única ventana que he autorizado para Computer Use, observa su imagen, pulsa el botón Verificar una sola vez y comprueba que aparece Resultado confirmado. '
            'Es una prueba local sin datos externos. Usa axx_computer_observe y axx_computer_act. Consulta axx_get_task si el recibo sigue running; después observa de nuevo para confirmar. '
            'Para esta prueba pulsa mediante x e y de la imagen, sin control_id. No uses otros comandos ni terminal. Si no puedes verificar, indica el error y detente.')
        result=api('/axx-api/connect/start',{'request_id':request,'conversation_id':connect_id,'model':'gpt-6.1-sol','message':message,'origin':'test'},timeout=20)
        end=time.monotonic()+85
        while result['state'] not in ('completed','failed','unknown','cancelled','limit_reached') and time.monotonic()<end:
            time.sleep(.3);result=api('/axx-api/connect/run?request_id='+request)
        (out/('installed-run.json' if args.installed else 'dev-run.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        assert result['state']=='completed',result.get('error')
        events=[e for e in result['events'] if e.get('type')=='computer/image_attached' or e.get('kind')=='computer/image_attached']
        # Events use method as their persisted discriminator in the provider journal.
        if not events:events=[e for e in result['events'] if e.get('event')=='computer/image_attached']
        receipts=[r['result'] for r in result['tool_results'] if isinstance(r.get('result'),dict)]
        actions=[r for r in receipts if r.get('command_id')=='axx.computer.act' and r.get('state')=='succeeded' and r.get('output',{}).get('dispatched')]
        assert actions,[(r.get('state'),r.get('error')) for r in receipts]
        assert len(actions)==1,'More than one gesture dispatched'
        assert events,'No image attachment receipt'
        from backend.actions import windows_automation as uia
        readback=uia.read_window_content(window['window_id'],window['pid'],'Axx Computer Use · prueba aislada')
        assert any(r.get('name')=='Resultado confirmado' for r in readback['controls']),'Native readback mismatch'
        api('/axx-api/computer/stop',{'conversation_id':chat});assert not api('/axx-api/computer/status?conversation_id='+chat)['active']
        report={'result':'COMPUTER_USE_NATIVE_MODEL_PASS','installed':args.installed,'backend_instance':descriptor['instance_id'],
            'model':'gpt-6.1-sol','allow_paid':False,'images_attached':len(events),'verified_gestures':len(actions),'independent_native_readback':True,'revoked':True}
        (out/('installed-acceptance.json' if args.installed else 'dev-acceptance.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:
        if api and chat:
            try:api('/axx-api/computer/stop',{'conversation_id':chat})
            except Exception:pass
        heartbeat_stop.set()
        if heartbeat:heartbeat.join(2)
        fixture.terminate();fixture.wait(timeout=5)
        if server:server.shutdown();server.server_close()
        for service in reversed(services):service.close()


if __name__=='__main__':main()
