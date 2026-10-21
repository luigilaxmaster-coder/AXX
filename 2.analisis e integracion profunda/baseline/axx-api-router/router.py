"""Axx sequential failover router. Python 3.11+, standard library only."""
from __future__ import annotations
import argparse
import datetime as dt
import email.utils
import json
import logging
import math
import os
from pathlib import Path
import socket
import sqlite3
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

LOG = logging.getLogger('axx.router')
class RequestError(ValueError): pass
class Exhausted(RuntimeError): pass
class UpstreamError(RuntimeError):
    def __init__(self, status: int, retry_after: float = 0):
        super().__init__(f'Upstream HTTP {status}')
        self.status, self.retry_after = status, retry_after

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def retry_seconds(value: str | None) -> float:
    try: return max(0, float(value or 0))
    except ValueError:
        try: return max(0, email.utils.parsedate_to_datetime(value).timestamp()-time.time())
        except (ValueError, TypeError, OverflowError): return 0

def http_transport(provider: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(provider['base_url'].rstrip('/')+'/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type':'application/json',
        'Authorization':'Bearer '+os.environ[provider['api_key_env']]}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024: raise UpstreamError(502)
            try: return json.loads(raw)
            except (ValueError, UnicodeError): raise UpstreamError(502) from None
    except urllib.error.HTTPError as exc:
        raise UpstreamError(exc.code, retry_seconds(exc.headers.get('Retry-After'))) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError):
        raise UpstreamError(503) from None

class Router:
    def __init__(self, config: dict, state: str | Path = 'state.db', *,
                 transport: Callable = http_transport):
        self.providers=config.get('providers', [])
        self.timeout=float(config.get('timeout_seconds',20))
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120: raise ValueError('Invalid timeout')
        self.max_attempts=int(config.get('max_attempts',3))
        if not 1 <= self.max_attempts <= 10: raise ValueError('Invalid max_attempts')
        self.max_request_bytes=int(config.get('max_request_bytes', 2*1024*1024))
        if self.max_request_bytes < 1: raise ValueError('Invalid max_request_bytes')
        names=set()
        for p in self.providers:
            for field in ('name','base_url','model','api_key_env','daily_attempt_limit','capabilities'):
                if field not in p: raise ValueError(f'Missing provider field: {field}')
            u=urllib.parse.urlsplit(p['base_url'])
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError('base_url must be HTTPS without credentials/query/fragment')
            if p['name'] in names: raise ValueError('Duplicate provider name')
            names.add(p['name'])
            if type(p['daily_attempt_limit']) is not int or p['daily_attempt_limit']<1:
                raise ValueError('daily_attempt_limit must be positive integer')
            if not isinstance(p['capabilities'],list): raise ValueError('Invalid capabilities')
            if type(p.get('max_output_tokens',1024)) is not int or p.get('max_output_tokens',1024)<1:
                raise ValueError('Invalid max_output_tokens')
            if 'tasks' in p and (not isinstance(p['tasks'],list) or not all(isinstance(t,str) for t in p['tasks'])):
                raise ValueError('Invalid tasks')
        self.transport=transport
        self.db=sqlite3.connect(str(state), timeout=5)
        self.db.execute('CREATE TABLE IF NOT EXISTS usage (name TEXT, day TEXT, attempts INTEGER, PRIMARY KEY(name,day))')
        self.db.execute('CREATE TABLE IF NOT EXISTS cooldown (name TEXT PRIMARY KEY, until REAL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS metrics (name TEXT PRIMARY KEY, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, latency_ms REAL DEFAULT 0, last_status INTEGER)')
        self.db.commit()

    def _reserve(self,p:dict) -> bool:
        day=dt.datetime.now(dt.timezone.utc).date().isoformat()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute('SELECT until FROM cooldown WHERE name=?',(p['name'],)).fetchone()
            if row and row[0]>time.time(): return False
            self.db.execute('INSERT OR IGNORE INTO usage VALUES(?,?,0)',(p['name'],day))
            cur=self.db.execute('UPDATE usage SET attempts=attempts+1 WHERE name=? AND day=? AND attempts<?',
                (p['name'],day,p['daily_attempt_limit']))
            return cur.rowcount==1

    def _cool(self,name:str,seconds:float):
        with self.db:
            self.db.execute('INSERT INTO cooldown VALUES(?,?) ON CONFLICT(name) DO UPDATE SET until=max(until,excluded.until)',
                (name,time.time()+seconds))

    def _record(self, name: str, success: bool, elapsed: float, status: int):
        with self.db:
            self.db.execute("INSERT INTO metrics(name,successes,failures,latency_ms,last_status) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET successes=successes+excluded.successes, failures=failures+excluded.failures, latency_ms=latency_ms+excluded.latency_ms,last_status=excluded.last_status",
                (name,int(success),int(not success),elapsed*1000,status))

    def reset_cooldown(self, name: str):
        if name not in {p['name'] for p in self.providers}: raise ValueError('Unknown provider')
        with self.db: self.db.execute('DELETE FROM cooldown WHERE name=?',(name,))

    def status(self) -> dict:
        day=dt.datetime.now(dt.timezone.utc).date().isoformat()
        providers=[]
        for p in self.providers:
            usage=self.db.execute('SELECT attempts FROM usage WHERE name=? AND day=?',(p['name'],day)).fetchone()
            count=usage[0] if usage else 0
            pause=self.db.execute('SELECT until FROM cooldown WHERE name=?',(p['name'],)).fetchone()
            until=pause[0] if pause else 0
            metrics=self.db.execute('SELECT successes,failures,latency_ms,last_status FROM metrics WHERE name=?',(p['name'],)).fetchone()
            if not p.get('enabled',True): state='disabled'
            elif p.get('free_confirmed') is not True: state='free_not_confirmed'
            elif not os.environ.get(p['api_key_env']): state='missing_key'
            elif until>time.time(): state='cooldown'
            elif count>=p['daily_attempt_limit']: state='local_quota_exhausted'
            else: state='ready'
            m=metrics or (0,0,0,None)
            providers.append({'name':p['name'],'model':p['model'],'state':state,
                'capabilities':p['capabilities'],'tasks':p.get('tasks',['*']),
                'attempts_today':count,'daily_attempt_limit':p['daily_attempt_limit'],
                'cooldown_remaining_seconds':max(0,round(until-time.time())),
                'metrics':{'successes':m[0],'failures':m[1],
                    'mean_attempt_ms':round(m[2]/max(1,m[0]+m[1]),1),'last_status':m[3]}})
        return {'day_utc':day,'providers':providers,'quota_source':'local_attempts_only'}

    def chat(self, request: dict[str,Any]) -> dict[str,Any]:
        if not isinstance(request,dict) or not isinstance(request.get('messages'),list):
            raise RequestError('messages must be an array')
        if len(json.dumps(request).encode())>self.max_request_bytes: raise RequestError('Request too large')
        if 'max_tokens' in request and (type(request['max_tokens']) is not int or request['max_tokens']<1):
            raise RequestError('max_tokens must be a positive integer')
        if 'axx_task' in request and not isinstance(request['axx_task'],str): raise RequestError('axx_task must be a string')
        if 'axx_sensitive' in request and type(request['axx_sensitive']) is not bool: raise RequestError('axx_sensitive must be boolean')
        if request.get('stream'): raise RequestError('Streaming not supported; use stream=false')
        allowed={'messages','temperature','top_p','max_tokens','tools','tool_choice','response_format','seed','stream','axx_task','axx_sensitive'}
        if set(request)-allowed: raise RequestError('Unsupported fields: '+','.join(sorted(set(request)-allowed)))
        required={'text'}
        if request.get('tools'): required.add('tools')
        if request.get('response_format'): required.add('json')
        for msg in request['messages']:
            if not isinstance(msg,dict): raise RequestError('Invalid message')
            if msg.get('role')=='tool' or msg.get('tool_calls'): required.add('tools')
            content=msg.get('content')
            if isinstance(content,list):
                for part in content:
                    if not isinstance(part,dict): raise RequestError('Invalid content part')
                    if part.get('type')=='image_url': required.add('vision')
                    elif part.get('type')!='text': raise RequestError('Unsupported content modality')
        attempts=0
        for p in self.providers:
            if attempts>=self.max_attempts: break
            if p.get('enabled',True) is not True or p.get('free_confirmed') is not True: continue
            if request.get('axx_sensitive') and p.get('allow_sensitive') is not True: continue
            task=request.get('axx_task','chat')
            if 'tasks' in p and task not in p['tasks'] and '*' not in p['tasks']: continue
            if not required.issubset(set(p['capabilities'])): continue
            if not os.environ.get(p['api_key_env']): continue
            if not self._reserve(p): continue
            attempts+=1
            body={k:v for k,v in request.items() if not k.startswith('axx_')}
            body.update(model=p['model'],stream=False)
            body['max_tokens']=min(body.get('max_tokens',p.get('max_output_tokens',1024)),p.get('max_output_tokens',1024))
            started=time.monotonic()
            try:
                result=self.transport(p,body,self.timeout)
                if not isinstance(result,dict) or not isinstance(result.get('choices'),list) or not result['choices']:
                    raise UpstreamError(502)
                if not isinstance(result['choices'][0],dict) or not isinstance(result['choices'][0].get('message'),dict):
                    raise UpstreamError(502)
                self._record(p['name'],True,time.monotonic()-started,200)
                result['axx_router']={'provider':p['name'],'model':p['model'],'attempts':attempts}
                LOG.info('success provider=%s attempts=%d',p['name'],attempts)
                return result
            except UpstreamError as exc:
                self._record(p['name'],False,time.monotonic()-started,exc.status)
                LOG.warning('failure provider=%s status=%d',p['name'],exc.status)
                if exc.status in (401,402,403): seconds=86400
                elif exc.status==429: seconds=max(60,exc.retry_after)
                elif exc.status in (408,404) or 500<=exc.status<=599: seconds=30
                else: raise
                self._cool(p['name'],seconds)
        raise Exhausted(f'No eligible provider available; attempts={attempts}. Check keys, capabilities, quotas and cooldowns.')

    def close(self): self.db.close()

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='providers.json')
    parser.add_argument('--state',default='state.db')
    parser.add_argument('--request',help='JSON file; otherwise stdin')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--status',action='store_true',help='Local state; does not call APIs')
    action.add_argument('--reset-cooldown',metavar='PROVIDER',help='Clear pause, preserve counters')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    router=None
    try:
        config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        router=Router(config,args.state)
        if args.reset_cooldown:
            router.reset_cooldown(args.reset_cooldown)
            result=router.status()
        elif args.status: result=router.status()
        else:
            request=json.loads(Path(args.request).read_text(encoding='utf-8-sig') if args.request else __import__('sys').stdin.read())
            result=router.chat(request)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ValueError,OSError,sqlite3.Error,UpstreamError,Exhausted) as exc:
        print(json.dumps({'error':{'type':type(exc).__name__,'message':str(exc)}}))
        return 1
    finally:
        if router: router.close()

if __name__=='__main__': raise SystemExit(main())
