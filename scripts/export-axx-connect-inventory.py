"""Snapshot the shared registry without running actions or loading credentials."""
import json
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.connect.service import ConnectService

with tempfile.TemporaryDirectory() as directory:
    executor = ActionExecutor(Path(directory)/'state.db',workspace_root=Path(directory)/'artifacts')
    commands = CommandService(executor)
    service = ConnectService(commands,None)
    try:
        items=[]
        offset=0
        while True:
            page=service.capabilities('',100,offset)
            items.extend(page['commands'])
            offset+=len(page['commands'])
            if not page['commands'] or offset>=page['matched']: break
        result={'snapshot_only':True,'ui_heartbeat_present':False,'status':service.status(),'counts':page['counts'],'capabilities':items}
        output=ROOT/'evidence/axx-connect/capabilities.json'
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'output':str(output),'total':len(items),'counts':page['counts']},ensure_ascii=False,indent=2))
    finally:
        service.close();commands.close();executor.close()
