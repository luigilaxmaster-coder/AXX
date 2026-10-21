"""Run actual bundled memory, Blender, TTS and ASR without importing source code.

Usage: python backend/tests/verify_resident_packaged.py BINARY --output REPORT.json
All artifacts are generated under one fresh temporary app-data directory.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('binary',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    binary=args.binary.resolve(strict=True)
    workspace=Path(tempfile.mkdtemp(prefix='axx-resident-packaged-'))
    token=secrets.token_hex(32)
    environment=dict(os.environ,AXX_HOST_TOKEN=token)
    process=None
    base=None
    log=(workspace/'backend.log').open('ab')
    report={'binary':str(binary),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'workspace':str(workspace),'checks':[], 'physical_microphone_verified':False,
            'speaker_playback_verified':False,'remote_inference':'BLOCKED_CREDENTIALS'}

    def start():
        nonlocal process,base
        ready=workspace/'ready.json';ready.unlink(missing_ok=True)
        environment['AXX_HOST_INSTANCE']=str(uuid.uuid4())
        process=subprocess.Popen([str(binary),'--port','0','--data-dir',str(workspace),'--ready-file',str(ready)],
            cwd=workspace,env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        until=time.monotonic()+40
        while time.monotonic()<until:
            if process.poll() is not None:raise AssertionError('Frozen backend exited; inspect '+str(workspace/'backend.log'))
            if ready.is_file():
                state=json.loads(ready.read_text())
                assert state['instance_id']==environment['AXX_HOST_INSTANCE']
                base=f"http://127.0.0.1:{state['port']}";return
            time.sleep(.1)
        raise AssertionError('Frozen backend readiness timed out')

    def stop():
        nonlocal process
        if process and process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/F','/T','/PID',str(process.pid)],capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
            else:process.terminate()
            process.wait(timeout=5)
        process=None

    def request(path,body=None):
        req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},
            data=json.dumps(body).encode() if body is not None else None)
        try:response=urllib.request.urlopen(req,timeout=100)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.status,json.loads(response.read())

    try:
        start()
        status,data=request('/axx-api/status')
        assert status==200 and data['ready'] and data['memory']['backend']=='ai-memory',data
        report['checks'].append('owned_bundled_ai_memory_ready')
        status,action=request('/axx-api/actions/execute',{'tool_name':'file_artifact_writer','operation_id':str(uuid.uuid4()),
            'inputs':{'path':'memory-first.txt','content':'Resident memory lifecycle verified fixture'}})
        assert status==200 and action['state']=='succeeded',action
        status,recipe=request('/axx-api/recipes/register',{'id':'resident-proof','intent_key':'resident-proof','operation_id':action['operation_id']})
        assert status==200 and recipe['recipe']['status']=='verified',recipe
        status,page=request('/axx-api/memory/read',{'recipe_id':'resident-proof'})
        assert status==200 and page['memory']['backend']=='ai-memory' and page['page'] and 'resident-proof' in page['page']['body'],page
        status,query=request('/axx-api/memory/query',{'query':'Recipe'})
        assert status==200 and query['hits'] and query['execution_allowed'] is False,query
        report['checks'].append('actual_mcp_recipe_write_query_read')
        stop();start()
        status,page=request('/axx-api/memory/read',{'recipe_id':'resident-proof'})
        assert status==200 and page['page'] and 'resident-proof' in page['page']['body'],page
        report['checks'].append('actual_mcp_page_persisted_after_backend_restart')
        status,replay=request('/axx-api/recipes/execute',{'intent_key':'resident-proof','operation_id':str(uuid.uuid4()),
            'inputs':{'path':'memory-second.txt','content':'Second resident artifact after restart'}})
        assert status==200 and replay['outcome']=='succeeded' and replay['model_calls_used']==0,replay
        assert (workspace/'artifacts'/'memory-second.txt').read_text()=='Second resident artifact after restart'
        report['checks'].append('verified_procedure_reused_after_restart_without_model')
        status,render=request('/axx-api/actions/execute',{'tool_name':'blender_render_fixture','operation_id':str(uuid.uuid4()),'inputs':{'filename':'resident-cli.png'}})
        assert status==200 and render['state']=='succeeded' and render['postconditions_passed'],render
        image=Path(render['evidence']['path']).read_bytes()
        assert image[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',image[16:24])==(256,256)
        assert hashlib.sha256(image).hexdigest()==render['evidence']['sha256']
        report['checks'].append('real_cli_anything_blender_render_verified_png')
        report['blender']=render['evidence']
        status,voices=request('/axx-api/speech/voices')
        assert status==200 and voices['available'],voices
        voice=next((v for v in voices['voices'] if v['language'].startswith('en')),voices['voices'][0])
        status,speech=request('/axx-api/speech/synthesize',{'text':'Hello, this is a local voice transcription test. The desktop assistant is ready.','voice':voice['name']})
        assert status==200 and speech['playback_verified'] is False,speech
        audio=base64.b64decode(speech['audio_base64'],validate=True)
        with wave.open(io.BytesIO(audio),'rb') as wav:
            assert wav.getframerate()==16000 and wav.getnchannels()==1 and wav.getnframes()>0
        assert hashlib.sha256(audio).hexdigest()==speech['evidence']['sha256']
        report['checks'].append('real_windows_tts_pcm_wav_verified')
        started=time.monotonic()
        status,transcript=request('/axx-api/speech/transcribe',{'audio_base64':speech['audio_base64'],'mime':'audio/wav','language':'en'})
        assert status==200 and 'local' in transcript['text'].lower(),transcript
        assert transcript['engine']=='faster-whisper' and transcript['external_calls']==0 and transcript['automatic_actions'] is False
        report['checks'].append('real_bundled_cpu_tiny_transcribed_synthetic_tts')
        report['transcription']={'elapsed_seconds':round(time.monotonic()-started,3),**transcript}
        status,chat=request('/axx-api/chat',{'messages':[{'role':'user','content':'Controlled missing credential check'}],'stream':False})
        assert status==502 and chat['error']['code']=='NO_PROVIDER_AVAILABLE',chat
        report['checks'].append('typed_remote_inference_missing_credentials')
        report['result']='PASS'
    except Exception as error:
        report['result']='FAIL';report['failure']=str(error)
        raise
    finally:
        stop();log.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
