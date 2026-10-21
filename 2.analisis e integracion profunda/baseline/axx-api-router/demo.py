"""Offline demonstration: a quota failure triggers a different provider."""
import json
import os
import tempfile
from pathlib import Path
from router import Router, UpstreamError

def main():
    os.environ['AXX_DEMO_KEY']='dummy-offline-only'
    config={'providers':[{'name':name,'base_url':'https://example.invalid/v1',
        'model':'offline-demo','api_key_env':'AXX_DEMO_KEY','free_confirmed':True,
        'capabilities':['text'],'daily_attempt_limit':10} for name in ['principal','respaldo']]}
    def simulated_transport(provider, body, timeout):
        if provider['name']=='principal': raise UpstreamError(429, retry_after=120)
        return {'choices':[{'message':{'role':'assistant','content':'Respuesta simulada desde el respaldo.'}}]}
    with tempfile.TemporaryDirectory() as tmp:
        router=Router(config,Path(tmp)/'demo.db',transport=simulated_transport)
        try:
            result=router.chat({'messages':[{'role':'user','content':'Hola'}]})
            assert result['axx_router']['provider']=='respaldo'
            assert result['axx_router']['attempts']==2
            print(json.dumps({'mode':'OFFLINE_SIMULATION','result':result,'status':router.status()},ensure_ascii=False,indent=2))
        finally: router.close()

if __name__=='__main__': main()
