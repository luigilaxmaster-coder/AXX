"""Exercise real packaged MCP/Windows and artifact workers using owned fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from backend.inference.process_manager import spawn_managed_process, terminate_process_tree
    from backend.tests.test_ifc_inventory import IfcInventoryTests
    from PIL import Image, ImageDraw, ImageFont
    from pypdf import PdfWriter
    checks=[]
    with tempfile.TemporaryDirectory(prefix='axx-packaged-mcp-') as folder:
        private=Path(folder); ready=private/'ready.json'; token=secrets.token_hex(32)
        (private/'providers.json').write_text('{"allow_paid":false,"providers":[]}')
        log=private/'runtime.log'
        with log.open('wb') as stream:
            process,job=spawn_managed_process([str(args.binary.resolve()),'--port','0','--data-dir',str(private),'--ready-file',str(ready)],
                cwd=str(ROOT),env=os.environ|{'AXX_HOST_TOKEN':token},stdin=subprocess.DEVNULL,stdout=stream,stderr=stream)
            try:
                deadline=time.monotonic()+120
                while not ready.exists():
                    if process.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Packaged startup failed; '+log.read_text(errors='replace')[-3000:])
                    time.sleep(.1)
                base='http://127.0.0.1:'+str(json.loads(ready.read_text())['port'])+'/axx-api/'
                def request(path,body=None):
                    req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                    try:
                        with urllib.request.urlopen(req,timeout=120) as response: return json.load(response)
                    except urllib.error.HTTPError as error:
                        message=error.read(2000).decode(errors='replace')
                        if path=='mcp/probe': message += ' '+json.dumps(request('mcp/connections'))
                        raise RuntimeError(path+': '+message) from None
                def execute(command,inputs):
                    plan=request('commands/prepare',{'command_id':command,'inputs':inputs})
                    result=request('commands/execute',{'operation_id':plan['operation_id'],'approved':True})
                    assert result['state']=='succeeded',result
                    checks.append({'command':command,'state':result['state'],'postconditions_passed':result['postconditions_passed']})
                    return result
                fixture=private/'server.py'; shutil.copyfile(ROOT/'backend/tests/mcp_fixture_server.py',fixture)
                connection=request('mcp/add',{'name':'Packaged fixture','context':'Owned acceptance fixture','transport':'stdio','command':str(Path(sys.executable).resolve()),
                    'args':[str(fixture)],'cwd':str(private),'env':{'AXX_TEST_MCP_FILE':str(private/'effects.txt')}})
                request('mcp/probe',{'id':connection['id']})
                rows=request('mcp/connections')['connections'][0]['tools']
                tool=next(row for row in rows if row['name']=='add_numbers')
                request('mcp/activate',{'tool_id':tool['id'],'enabled':True,'read_only':True})
                result=execute(tool['id'],{'left':20,'right':22})
                assert json.loads(result['output']['result']['content'][0]['text'])['sum']==42
                result=execute('axx.desktop.list_windows',{})
                assert result['evidence']['transport']=='mcp_streamable_http',result
                pdf=private/'fixture.pdf'; writer=PdfWriter();writer.add_blank_page(width=300,height=400)
                with pdf.open('wb') as output: writer.write(output)
                assert execute('axx.artifact.pdf',{'path':str(pdf)})['output']['page_count']==1
                source=private/'model.ifc'; guid=IfcInventoryTests().fixture(source)
                result=execute('axx.ifc.inventory.csv',{'source':str(source),'destination':'inventory.csv'})
                image=Image.new('RGB',(1000,120),'white'); draw=ImageDraw.Draw(image)
                draw.text((24,25),'NO borrar plano_ñ.ifc',font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'),36),fill='black')
                path=private/'ocr.png';image.save(path)
                assert 'NO borrar plano_ñ.ifc' in execute('axx.artifact.ocr',{'path':str(path)})['output']['text']
                request('mcp/disconnect',{'id':connection['id']})
                report={'packaged':True,'installed_host':False,'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),'checks':checks,
                        'limitations':['Owned MCP fixture; not an authenticated AnythingMCP tool call','Windows window enumeration does not certify input or visual layout']}
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'passed':True,'checks':len(checks),'packaged':True}))
            finally:
                import psutil
                children=psutil.Process(process.pid).children(recursive=True) if process.poll() is None else []
                terminate_process_tree(process,job)
                psutil.wait_procs(children,timeout=5)


if __name__=='__main__': main()
