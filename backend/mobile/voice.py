"""PC-coordinated voice capture; Android never dispatches desktop commands itself."""
import base64
import hashlib
import json
import threading
import time
import uuid


ACTIVE = {'requested','recording','stopping','awaiting_audio','transcribing','review','ready','dispatching'}


class RemoteVoice:
    def __init__(self, store, shared, backend_call, clock=time.monotonic):
        self.store, self.shared, self.backend_call, self.clock = store, shared, backend_call, clock
        self.lock = threading.RLock()
        self.clients = {}
        self.deadline = None
        with store._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS mobile_voice_sessions(session_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)')
            rows = db.execute('SELECT data FROM mobile_voice_sessions ORDER BY updated_at DESC').fetchall()
        self.session = json.loads(rows[0]['data']) if rows else None
        if self.session and self.session['state'] in ACTIVE:
            self.session['state'] = 'outcome_unknown' if self.session['state']=='dispatching' else 'interrupted'
            self.session['mode'] = 'confirm'
            self.session['error'] = 'Axx restarted. Commands will not be repeated automatically.'
            self._save()

    def _save(self):
        self.session['updated_at'] = time.time()
        with self.store._connect() as db:
            db.execute('INSERT INTO mobile_voice_sessions VALUES(?,?,?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at',
                       (self.session['session_id'],json.dumps(self.session,ensure_ascii=False),self.session['updated_at']))

    def _device(self, device_id):
        return next((d for d in self.store.devices() if d['device_id']==device_id and not d['revoked']), None)

    def _require(self, session_id, device_id=None):
        if not self.session or self.session['session_id'] != session_id or device_id is not None and self.session['device_id'] != device_id:
            raise ValueError('Unknown voice session for this device')
        return self.session

    def _check_deadline(self):
        s=self.session
        if not s or s['state'] not in {'requested','recording','stopping'}:return
        seen=self.clients.get(s['device_id'],{}).get('seen',0)
        if self.clock()-seen>8:
            s.update(state='interrupted',mode='confirm',error='Connection lost. Capture must stop; audio will not be sent as an automatic command.')
            self._save()
        elif self.deadline is not None and self.clock()>self.deadline and s['state'] in {'requested','recording'}:
            s['state']='stopping';self._save()

    def status(self):
        with self.lock:
            self._check_deadline()
            clients=[{'device_id':key,**{k:v for k,v in value.items() if k!='seen'},'connected':self.clock()-value['seen']<4} for key,value in self.clients.items()]
            return {'session':dict(self.session) if self.session else None,'clients':clients,'partial_transcription':False}

    def poll(self, device_id, body):
        if set(body)!={'visible','permission','capture'} or not isinstance(body['visible'],bool) or body['permission'] not in ('granted','denied','prompt') or not isinstance(body['capture'],dict):
            raise ValueError('Invalid microphone state')
        capture=body['capture']
        if set(capture)-{'session_id','state','reason'} or capture.get('state') not in ('idle','recording','stopped','failed') or any(not isinstance(v,str) or len(v)>200 for v in capture.values()):
            raise ValueError('Invalid capture')
        with self.lock:
            self._check_deadline()
            self.clients[device_id]={'seen':self.clock(),'visible':body['visible'],'permission':body['permission'],'capture':capture}
            s=self.session
            if not s or s['device_id']!=device_id:return {'session':None}
            if s['state']=='stopping' and capture['state']=='idle':
                s['state']='empty';self._save()
            if capture.get('session_id')==s['session_id']:
                if capture['state']=='recording' and s['state']=='requested':s['state']='recording';self._save()
                if capture['state']=='failed' and s['state'] in {'requested','recording','stopping'}:
                    s.update(state='failed',error=capture.get('reason','Capture failed'));self._save()
                if capture['state']=='stopped' and s['state'] in {'requested','recording','stopping'}:
                    s['state']='awaiting_audio'
                    if capture.get('reason') not in ('pc_stop','timeout','user_stop'):s['mode']='confirm'
                    self._save()
            if s['state'] in {'requested','recording'} and (not body['visible'] or body['permission']!='granted'):
                s.update(state='interrupted',mode='confirm',error='The phone app is no longer visible or microphone permission was lost.');self._save()
            return {'session':dict(s)}

    def toggle(self, body):
        if set(body)!={'device_id','mode','max_seconds','conversation_id'} or body['mode'] not in ('confirm','handsfree') or type(body['max_seconds']) is not int or not 5<=body['max_seconds']<=55:
            raise ValueError('Select a phone, mode and a limit of 5 to 55 seconds')
        with self.lock:
            self._check_deadline()
            if self.session and self.session['state'] in {'requested','recording'}:
                self.session['state']='stopping';self._save();return dict(self.session)
            if self.session and self.session['state'] in ACTIVE:raise ValueError('Finish or cancel the current voice session')
            device=self._device(body['device_id'])
            if not device or 'voice' not in device['scopes']:raise ValueError('This phone does not have voice permission')
            if body['mode']=='handsfree' and 'tools.control' not in device['scopes']:raise ValueError('Hands-free mode requires command authorization for this phone from the PC')
            client=self.clients.get(body['device_id'],{})
            if self.clock()-client.get('seen',0)>4 or not client.get('visible') or client.get('permission')!='granted':raise ValueError('Open Axx Mobile and grant microphone permission before using the shortcut')
            if body['conversation_id']!=self.shared.snapshot()['conversation_id']:raise ValueError('The PC conversation changed')
            self.session={**body,'session_id':str(uuid.uuid4()),'state':'requested','text':'','confirmed_text':'','audio_hash':None,'result':None}
            self.deadline=self.clock()+body['max_seconds'];self._save();return dict(self.session)

    def phone_start(self, device_id, body):
        if not isinstance(body, dict) or set(body) != {'language'} or body['language'] not in ('es', 'en'):
            raise ValueError('Selecciona español o inglés')
        with self.lock:
            self._check_deadline()
            if self.session and self.session['state'] in ACTIVE:
                raise ValueError('Termina o cancela la sesión de voz actual')
            session = self.toggle({'device_id': device_id, 'mode': 'confirm', 'max_seconds': 30,
                                   'conversation_id': self.shared.snapshot()['conversation_id']})
            self.session['language'] = body['language']
            self._save()
            return dict(self.session)

    def audio(self, device_id, body):
        if set(body)!={'session_id','audio_base64','mime'} or body['mime']!='audio/mp4' or not isinstance(body['audio_base64'],str) or len(body['audio_base64'])>1900000:
            raise ValueError('Audio is invalid or too large')
        raw=base64.b64decode(body['audio_base64'],validate=True)
        if not 16<len(raw)<=1400*1024 or raw[4:8]!=b'ftyp':raise ValueError('Valid MP4 audio is required')
        digest=hashlib.sha256(raw).hexdigest()
        with self.lock:
            s=self._require(body['session_id'],device_id)
            if s['audio_hash']:
                if s['audio_hash']!=digest:raise ValueError('The session already received different audio')
                if s['state']!='interrupted' or s['text']:return dict(s)
            if s['state'] not in {'awaiting_audio','stopping','recording','interrupted'}:raise ValueError('This session cannot accept audio')
            if s['state']=='interrupted':s['mode']='confirm'
            s.update(audio_hash=digest,state='transcribing');self._save()
        def transcribe():
            try:
                result=self.backend_call('POST','/axx-api/speech/transcribe',{'audio_base64':body['audio_base64'],'mime':body['mime'],'language':s.get('language','es'),'task':'transcribe'})
                if result.get('ok',True) is False or not isinstance(result.get('text'),str):raise ValueError(result.get('error',{}).get('message','Whisper did not return text'))
                with self.lock:
                    if self.session['session_id']!=body['session_id'] or self.session['state']!='transcribing':return
                    text=result['text'].strip()[:10000]
                    self.session.update(text=text,confirmed_text=text if self.session['mode']=='handsfree' else '',state=('ready' if self.session['mode']=='handsfree' else 'review') if text else 'empty',transcription={'engine':result.get('engine'),'input_sha256':result.get('input_sha256'),'partial':False})
                    self._save()
            except Exception as exc:
                with self.lock:
                    if self.session['session_id']==body['session_id'] and self.session['state']=='transcribing':
                        self.session.update(state='failed',error=str(exc)[:400]);self._save()
        threading.Thread(target=transcribe,name='axx-remote-transcription',daemon=True).start()
        with self.lock:return dict(self.session)

    def confirm(self, session_id, text, device_id=None):
        if not isinstance(text,str) or not 1<=len(text.strip())<=10000:raise ValueError('Corrige el texto antes de enviarlo')
        with self.lock:
            s=self._require(session_id,device_id)
            if device_id is not None:
                device=self._device(device_id)
                if not device or 'tools.control' not in device['scopes']:
                    raise ValueError('Aprueba el permiso de comandos de este teléfono en la PC')
            if s['state']=='ready' and s['confirmed_text']==text.strip():return dict(s)
            if s['state']!='review':raise ValueError('This session is not awaiting confirmation')
            s.update(confirmed_text=text.strip(),state='ready');self._save();return dict(s)

    def claim(self, session_id, conversation_id):
        with self.lock:
            s=self._require(session_id)
            device=self._device(s['device_id'])
            if not device or 'voice' not in device['scopes'] or s['mode']=='handsfree' and 'tools.control' not in device['scopes']:raise ValueError('Session permissions were revoked')
            if s['conversation_id']!=conversation_id:raise ValueError('Return to the conversation where you started voice')
            if s['state']!='ready':return {'execute':False,'session':dict(s)}
            s['state']='dispatching';self._save();return {'execute':True,'session':dict(s)}

    def finish(self, session_id, result):
        if not isinstance(result,dict) or len(json.dumps(result))>100000:raise ValueError('Invalid result')
        with self.lock:
            s=self._require(session_id)
            if s['state']=='completed':return dict(s)
            if s['state'] not in {'dispatching','outcome_unknown'}:raise ValueError('This command was not admitted')
            s.update(state='completed',result=result);self._save();return dict(s)

    def cancel(self, session_id, device_id=None):
        with self.lock:
            s=self._require(session_id,device_id)
            if s['state']=='dispatching':raise ValueError('The command already reached Axx. Stop it using the existing operation controls.')
            if s['state'] in ACTIVE or s['state']=='interrupted':s['state']='cancelled';self._save()
            return dict(s)

    def disconnect(self, device_id=None):
        with self.lock:
            if self.session and (device_id is None or self.session['device_id']==device_id) and self.session['state'] in {'requested','recording','stopping','awaiting_audio'}:
                self.session.update(state='interrupted',mode='confirm',error='Mobile access closed. Review recovered audio before sending.');self._save()
