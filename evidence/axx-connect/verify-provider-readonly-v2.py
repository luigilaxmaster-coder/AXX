"""Actual pinned App Server status using final provider; no turn or auth mutation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.connect.provider import CodexProvider, discover_codex


class ObservedProvider(CodexProvider):
    def __init__(self, *args, **kwargs):
        self.rpc_methods = []
        super().__init__(*args, **kwargs)

    def _request(self, method, *args, **kwargs):
        self.rpc_methods.append(method)
        return super()._request(method, *args, **kwargs)


def main():
    source = ROOT / 'backend/connect/provider.py'
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='provider-readonly-v2-',dir=ROOT/'evidence/axx-connect') as directory:
        provider = ObservedProvider(None,Path(directory)/'state.db',directory)
        try:
            status = provider.status()
            process = provider.process
            executable = discover_codex()
            result = {'classification':'REAL_PINNED_APPSERVER_STATUS_NO_INFERENCE',
                'created_at_utc':datetime.now(timezone.utc).isoformat(),
                'source_sha256':before,'codex_executable_sha256':digest(executable),
                'codex_version':status.get('runtime',{}).get('version'),
                'state':status.get('state'),'authenticated':status.get('authenticated'),
                'inference_verified':status.get('inference_verified'),
                'models_in_catalog':len(status.get('models',[])),
                'rpc_methods':provider.rpc_methods,'turn_start_sent':'turn/start' in provider.rpc_methods,
                'credentials_copied':False,'auth_mutation_rpc_sent':any(method.startswith('account/login') or method=='account/logout' for method in provider.rpc_methods),
                'native_gui_tested':False,'executor_tested':False,'builtin_inventory_complete':False,
                'diagnostic':status.get('error'),
                'ok':status.get('authenticated') is True and not status.get('inference_verified')}
        finally:
            provider.close()
        result.update(elapsed_seconds=round(time.monotonic()-start,3),
                      owned_process_closed=process is not None and process.poll() is not None,
                      source_unchanged=before==digest(source))
    destination=ROOT/'evidence/axx-connect/provider-readonly-v2-result.json'
    destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['ok'] and result['owned_process_closed'] and result['source_unchanged'] else 1


if __name__=='__main__':
    raise SystemExit(main())
