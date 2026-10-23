"""Explicit model proposals and bounded, effect-free representative evaluations.

Seeds are user-supplied identifiers, never a capability or availability claim.
Discovery and evaluation do not change provider settings or gateway profiles.
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import struct
import sys
import threading
import time
import urllib.parse
import uuid
import zlib

from . import provider_settings
from .router import TASK_PROFILES, Router, _optional_auth, automatic_free, http_transport, parse_strict_json, profile_id

FIXTURE_VERSION = 2

def _vision_fixture():
    """A real lossless RGB image: red canvas with a blue square at bottom right."""
    def chunk(kind, value):
        return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value))
    pixels = b''.join(b'\0' + b''.join(b'\0\0\xff' if 40 <= x < 60 and 40 <= y < 60 else b'\xff\0\0'
                                     for x in range(64)) for y in range(64))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',64,64,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND',b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def _fixture(task):
    plan = {'steps':[{'command_id':'axx.system.telemetry','inputs':{}}]}
    fixtures = {
        'plan': ('Create a plan to read current system telemetry. The available read-only command is axx.system.telemetry and it takes no parameters. Output schema: an object with exactly the key steps; steps is an array containing one object with exactly the keys command_id (string) and inputs (object). Use no additional keys.', plan),
        'repair': ('Repair this invalid read-only plan: {"steps":[{"command_id":"telemetry","inputs":{"script":"bad"}}]}. Return JSON only, exactly one step command_id axx.system.telemetry and empty inputs; remove all other fields.', plan),
        'parameters': ('Extract exactly the process ID from "Inspect process PID 4242". Return only a JSON object with the single integer field pid.', {'pid':4242}),
        'code': ('Return JSON with exactly code and result. code must define Python function even_squares(values) returning [x*x for x in values if x%2==0] with no other statements. result must be the output for [1,2,3,4]. Do not execute code.', {'result':[4,16]}),
        'writing': ('Correct the spelling of "The quik brown fox.". Return JSON only with the single field text containing the corrected sentence.', {'text':'The quick brown fox.'}),
        'translation': ('Translate "Buenos días" to English. Return JSON only with the single field text. Use the ordinary two-word greeting with no punctuation.', {'text':'Good morning'}),
        'chat': ('A box contains 3 red balls and 2 blue balls. How many balls total? Return JSON only with the single integer field total.', {'total':5}),
        'vision': ('Inspect the attached image. Return JSON only with exactly background, shape, position. Use lowercase English colors and bottom-right/top-left/bottom-left/top-right for position.', {'background':'red','shape':'blue square','position':'bottom-right'}),
    }
    prompt, expected = fixtures[task]
    content = prompt if task != 'vision' else [{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':_vision_fixture()}}]
    return [{'role':'system','content':'Return exactly one JSON object matching the requested schema. No prose, Markdown, or code fences. Do not execute any action.'},
            {'role':'user','content':content}], expected


def _normalized_content(message):
    content=message.get('content') if isinstance(message,dict) else None
    if not isinstance(content,str):
        return None,0
    raw=content.strip()
    normalized=re.sub(r'^```(?:json)?\s*|\s*```$', '', raw)
    return normalized,int(normalized!=raw)


def _valid_result(task, message, expected):
    if not isinstance(message, dict) or not isinstance(message.get('content'), str):
        return False
    try:
        actual = parse_strict_json(_normalized_content(message)[0].encode('utf-8'))
        if task != 'code':
            return actual == expected and json.dumps(actual,sort_keys=True) == json.dumps(expected,sort_keys=True)
        if not isinstance(actual, dict) or set(actual) != {'code','result'} or actual['result'] != expected['result'] or not isinstance(actual['code'],str):
            return False
        expected_ast = ast.parse('def even_squares(values):\n    return [x*x for x in values if x%2==0]')
        # Parse and compare syntax only. Model-supplied code is never compiled or executed.
        return ast.dump(ast.parse(actual['code'])) == ast.dump(expected_ast)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False


def _platform(provider):
    kind = provider.get('kind', '')
    if kind in ('gemini','groq','openrouter','nvidia'):
        return kind
    if urllib.parse.urlsplit(provider.get('base_url','')).hostname == 'integrate.api.nvidia.com':
        return 'nvidia'
    return kind or 'custom'


class ModelCandidates:
    def __init__(self, adapter, gateway=None, state_path=None, *, config_path=None):
        self.adapter, self.gateway = adapter, gateway
        self.config_path = Path(config_path) if config_path else None
        self.lock, self.gate = threading.RLock(), threading.Lock()
        self.cancelled=threading.Event()
        self.request_ids=set()
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        self.seeds = json.loads((root/'resources'/'model-candidates.json').read_text(encoding='utf-8'))['candidates']
        path = Path(state_path or adapter.state_path.with_name('model-candidates.db'))
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db = sqlite3.connect(path,timeout=10,check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS model_evaluations (evaluation_id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,task TEXT NOT NULL,created_at REAL NOT NULL,result_json TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS model_candidate_state (name TEXT PRIMARY KEY,value_json TEXT NOT NULL)')
        self.db.commit()

    def close(self):
        self.cancel_active()
        with self.gate,self.lock:
            if self.db is not None:
                self.db.close(); self.db = None

    def cancel_active(self):
        self.cancelled.set()
        with self.lock:
            request_ids=list(self.request_ids)
        for request_id in request_ids:
            self.adapter.cancel(request_id)
        return {'cancelled_requests':len(request_ids)}

    def _state(self,name,value=None):
        with self.lock:
            if value is not None:
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO model_candidate_state VALUES (?,?)',(name,json.dumps(value)))
                return value
            row=self.db.execute('SELECT value_json FROM model_candidate_state WHERE name=?',(name,)).fetchone()
            return json.loads(row[0]) if row else {}

    def _history(self,candidate_id):
        with self.lock:
            return [dict(json.loads(row[0]),evaluated_at=row[1]) for row in self.db.execute('SELECT result_json,created_at FROM model_evaluations WHERE candidate_id=? ORDER BY created_at DESC LIMIT 50',(candidate_id,))]

    def _save(self,result):
        with self.lock,self.db:
            self.db.execute('INSERT INTO model_evaluations VALUES (?,?,?,?,?)',(result['evaluation_id'],result['candidate_id'],result['task'],time.time(),json.dumps(result,ensure_ascii=False)))
        return result

    def catalog(self):
        with self.adapter.lock:
            config=copy.deepcopy(self.adapter.config)
        candidates=[dict(copy.deepcopy(seed),source='user',status='pending',matched_routes=[],evaluations=[],capabilities_verified=False) for seed in self.seeds]
        errors=[]
        gateway_catalogs={}
        direct_catalogs={}
        discovery_deadline=time.monotonic()+12
        def add_route(provider, effective, platform, model_id, ids=None, canonical=None, isolated=False):
            matches=[c for c in candidates if c['provider']==platform and c['model_id']==model_id]
            if not matches:
                identity=hashlib.sha256((platform+'\0'+model_id).encode()).hexdigest()[:20]
                tasks=[t for t in effective.get('candidate_tasks', effective.get('tasks', ['chat'])) if t in TASK_PROFILES]
                matches=[dict(id='discovered-'+identity,provider=platform,model_id=model_id,tasks=tasks or ['chat'],priority=50,
                    source='discovered',status='discovered',matched_routes=[],evaluations=[],capabilities_verified=False)]
                candidates.extend(matches)
            for candidate in matches:
                if candidate['source']=='discovered':
                    candidate['tasks']=sorted(set(candidate['tasks']) | {t for t in effective.get('candidate_tasks',effective.get('tasks',[])) if t in TASK_PROFILES})
                candidate['status']='discovered'
                route_identity=profile_id(effective)
                if isolated:
                    route_identity=hashlib.sha256((route_identity+json.dumps(sorted(ids or []))).encode()).hexdigest()[:32]
                candidate['matched_routes'].append({'name':provider['name'],'provider':platform,'model':provider['model'],
                    'native_model_id':model_id,'profile_id':route_identity,
                    'tasks':effective.get('tasks',list(TASK_PROFILES)), 'capabilities':effective.get('capabilities',[]),
                    'context_window':effective.get('context_window'), 'image_context_tokens':effective.get('image_context_tokens'),
                    'gateway_model_ids':ids or [],'gateway_model_id':provider['model'] if ids else None,
                    'canonical_id':canonical,'needs_isolation':isolated,'gateway_keyless':provider.get('gateway_keyless') is True})
        for provider in config.get('providers',[]):
            if time.monotonic()>=discovery_deadline:
                errors.append({'code':'DISCOVERY_DEADLINE'}); break
            if not provider.get('enabled', True) or not (_optional_auth(provider) or os.environ.get(provider.get('api_key_env',''), '').strip()):
                continue
            try:
                if provider.get('kind')=='freellmapi':
                    if self.gateway is None:
                        continue
                    discover_gateway=getattr(self.gateway,'candidate_catalog',self.gateway.profiles)
                    cache_key=(provider['base_url'],provider.get('api_key_env'),provider.get('gateway_dashboard_env'))
                    if cache_key not in gateway_catalogs:
                        gateway_catalogs[cache_key]=discover_gateway({'name':provider['name'],'base_url':provider['base_url'],
                            'gateway_free_model_ids':provider.get('gateway_free_model_ids',[])},config)
                    data=gateway_catalogs[cache_key]
                    if provider.get('billing_allowed') or provider.get('free_confirmed') is not True or provider.get('cost_evidence')!='free_tier':
                        continue
                    models=data.get('models',[])
                    groups={}
                    for model in models:
                        if model.get('enabled') is not True or not model.get('group_ready') or model.get('id') not in provider.get('gateway_free_model_ids',[]):
                            continue
                        platform=model.get('provider_kind') or model.get('platform','').lower()
                        groups.setdefault((platform,model.get('modelId'),model.get('canonical_id')),[]).append(model)
                    for (platform,model_id,canonical),members in groups.items():
                        ids=sorted(m['id'] for m in members)
                        if any(not set(m.get('group_member_ids',[])).issubset(ids) for m in members):
                            continue
                        contexts=[m.get('contextWindow') for m in members]
                        if any(type(n) is not int or n<=0 for n in contexts):
                            continue
                        caps=['text']+(['vision'] if all(m.get('supportsVision') is True for m in members) else [])
                        effective=dict(provider,context_window=min(contexts),capabilities=caps,tasks=list(TASK_PROFILES),candidate_tasks=provider.get('tasks',['chat']))
                        add_route(provider,effective,platform,model_id,ids,canonical,isolated=True)
                else:
                    cache_key=(provider['base_url'],provider.get('api_key_env'),provider.get('protocol'))
                    if cache_key not in direct_catalogs:
                        direct_catalogs[cache_key]=provider_settings.discover({'provider':provider.get('kind','custom'),'name':provider['name'],'base_url':provider['base_url'],'protocol':provider.get('protocol','openai')},config)
                    data=direct_catalogs[cache_key]
                    if provider['model'] not in data.get('models',[]):
                        continue
                    if automatic_free(dict(provider,candidate_only=False)):
                        add_route(provider,provider,_platform(provider),provider['model'])
            except (ValueError, OSError, KeyError, TypeError):
                errors.append({'provider_name':provider.get('name'),'code':'CATALOG_UNAVAILABLE'})
        suggested={task:[] for task in TASK_PROFILES}
        for candidate in candidates:
            candidate['evaluations']=self._history(candidate['id'])
            for task in candidate['tasks']:
                matching_profiles={r['profile_id'] for r in candidate['matched_routes'] if (task in r['tasks'] or '*' in r['tasks'])
                    and 'text' in r['capabilities'] and r['context_window'] and (task!='vision' or ('vision' in r['capabilities'] and r['image_context_tokens']))}
                evidence=[e for e in candidate['evaluations'] if e['task']==task and e.get('catalog_route_id',(e.get('route') or {}).get('profile_id')) in matching_profiles
                          and e.get('fixture_version')==FIXTURE_VERSION and e.get('proof_mode')=='actual' and e.get('status') in ('passed','failed')]
                if evidence and evidence[0]['passed']:
                    candidate['status']='evaluated'
                    suggested[task].append({'candidate_id':candidate['id'],'provider':candidate['provider'],'model_id':candidate['model_id'],
                        'priority':candidate['priority'],'success_rate':sum(e['passed'] for e in evidence)/len(evidence),
                        'samples':len(evidence),'latency_ms':sum(e['latency_ms'] for e in evidence)/len(evidence),
                        'corrections_required':sum(e.get('corrections_required',0) for e in evidence)/len(evidence),'activated':False})
            candidate['pending_reason']=None if candidate['matched_routes'] else 'No exact confirmed-free execution route found in the live catalog'
        for rows in suggested.values():
            rows.sort(key=lambda row:(-row['success_rate'],-row['samples'],row['corrections_required'],row['latency_ms'],row['priority'],row['candidate_id']))
        return {'candidates':candidates,'suggested_profiles':suggested,'errors':errors,'activation':'explicit_configuration_required'}

    def evaluate(self,body):
        if not isinstance(body,dict) or set(body)-{'candidate_id','task','route_name'} or not isinstance(body.get('candidate_id'),str) or body.get('task') not in TASK_PROFILES:
            raise ValueError('Select one candidate and one supported task; evaluation prompts are fixed')
        if 'route_name' in body and not isinstance(body['route_name'],str):
            raise ValueError('Invalid route name')
        if not self.gate.acquire(blocking=False):
            raise ValueError('BUSY: a candidate evaluation is already running')
        try:
            candidate=next((c for c in self.catalog()['candidates'] if c['id']==body['candidate_id']),None)
            if not candidate or body['task'] not in candidate['tasks']:
                raise ValueError('Unknown candidate or task not proposed for this candidate')
            task=body['task']
            result={'evaluation_id':str(uuid.uuid4()),'candidate_id':candidate['id'],'task':task,'status':'pending','passed':False,
                'proof_mode':'none','logical_requests':0,'latency_ms':0,'corrections':0,'corrections_required':0,'route':None,'fixture_version':FIXTURE_VERSION,
                'evidence_scope':'representative_fixture',
                'result_summary':'An exact configured free route and verified capabilities are required'}
            matches=[r for r in candidate['matched_routes'] if (task in r['tasks'] or '*' in r['tasks']) and r['context_window']
                and 'text' in r['capabilities'] and (task!='vision' or ('vision' in r['capabilities'] and r['image_context_tokens']))
                and (not body.get('route_name') or body['route_name']==r['name'])]
            if not matches:
                return self._save(result)
            selected=matches[0]
            provider_override=None
            expected_profile=selected['profile_id']
            if selected.get('needs_isolation'):
                from .freellmapi import evaluation_provider
                with self.adapter.lock:
                    source=next((copy.deepcopy(p) for p in self.adapter.config['providers'] if p['name']==selected['name']),None)
                try:
                    provider_override=evaluation_provider(source,selected['gateway_model_ids'],task)
                    expected_profile=profile_id(provider_override)
                except (ValueError,TypeError,KeyError):
                    result['result_summary']='GATEWAY_ISOLATED_PROFILE_UNAVAILABLE'
                    return self._save(result)
            result['catalog_route_id']=selected['profile_id']
            messages,expected=_fixture(task)
            result['fixture_sha256']=hashlib.sha256(json.dumps(messages,sort_keys=True).encode()).hexdigest()
            result['proof_mode']='actual' if self.adapter.router.transport is http_transport else 'simulated'
            start=time.monotonic()
            request_id='eval-'+result['evaluation_id']
            with self.lock:
                if self.cancelled.is_set():
                    result['result_summary']='CANCELLED'
                    return self._save(result)
                self.request_ids.add(request_id)
            try:
                response=self.adapter.route_candidate({'request_id':request_id,'messages':messages,'task':task,'conversation_id':'candidate-'+result['evaluation_id'],
                    'generation':{'temperature':0,'max_tokens':512},'deadline_ms':70000},selected['name'],provider_override=provider_override)
            finally:
                with self.lock:
                    self.request_ids.discard(request_id)
            result['latency_ms']=round((time.monotonic()-start)*1000,2)
            result['logical_requests']=0 if response.get('error',{}).get('upstream_attempted') is False else 1
            if not response.get('ok'):
                result.update(status='pending' if result['logical_requests']==0 else 'failed',corrections_required=0 if result['logical_requests']==0 else 1,
                    result_summary=response.get('error',{}).get('code','INFERENCE_FAILED'))
                return self._save(result)
            route=response.get('route',{})
            # Reconfiguration or a different responder must not validate the requested candidate.
            identity_ok=route.get('profile_id')==expected_profile and route.get('provider')==selected['name']
            if route.get('responder_model') and route['responder_model']!=candidate['model_id']:
                identity_ok=False
            if selected['gateway_model_ids'] and route.get('responder_model')!=candidate['model_id']:
                identity_ok=False
            fixture_ok=_valid_result(task,response.get('message'),expected)
            _,format_corrections=_normalized_content(response.get('message'))
            passed=identity_ok and fixture_ok
            result.update(status='passed' if passed else 'failed',passed=passed,corrections=format_corrections,
                corrections_required=0 if passed else 1,route=route,identity_passed=identity_ok,fixture_passed=fixture_ok,
                result_summary='Representative fixture passed' if passed else 'RESPONDER_IDENTITY_MISMATCH' if not identity_ok else 'REPRESENTATIVE_FIXTURE_MISMATCH')
            if result['proof_mode']=='actual' and identity_ok:
                self.adapter.record_outcome(route,task,'succeeded' if passed else 'failed')
            return self._save(result)
        finally:
            self.gate.release()

    def apply(self,body):
        """Persist priority for an exact existing route after real task evidence; never add models."""
        if not isinstance(body,dict) or set(body)-{'candidate_id','task','route_name'} or body.get('task') not in TASK_PROFILES or not isinstance(body.get('candidate_id'),str):
            raise ValueError('Select a candidate and its evaluated task')
        if self.config_path is None:
            raise ValueError('Persistent provider configuration is unavailable')
        catalog=self.catalog()
        candidate=next((c for c in catalog['candidates'] if c['id']==body['candidate_id']),None)
        suggestions=catalog['suggested_profiles'][body['task']]
        ranking=next((index for index,item in enumerate(suggestions) if item['candidate_id']==body['candidate_id']),None)
        if candidate is None or ranking is None:
            raise ValueError('A current successful actual evaluation is required')
        eligible=[]
        for route in candidate['matched_routes']:
            evidence=next((e for e in candidate['evaluations'] if e['task']==body['task'] and e.get('proof_mode')=='actual'
                and e.get('fixture_version')==FIXTURE_VERSION
                and e.get('catalog_route_id',(e.get('route') or {}).get('profile_id'))==route['profile_id'] and e['status'] in ('passed','failed')),None)
            if evidence and evidence['passed'] and (not body.get('route_name') or body['route_name']==route['name']):
                eligible.append((route,evidence))
        if not eligible:
            raise ValueError('No exact evaluated execution route is currently available')
        selected,evaluation=eligible[0]
        with provider_settings.LOCK,self.adapter.lock:
            if self.adapter.active_requests:
                raise ValueError('BUSY: wait for active inference before changing preferences')
            config=copy.deepcopy(self.adapter.config)
            provider=next((p for p in config['providers'] if p['name']==selected['name']),None)
            if provider is None or provider.get('billing_allowed') or provider.get('free_confirmed') is not True:
                raise ValueError('The evaluated connection changed')
            if selected.get('needs_isolation') or provider.get('candidate_only'):
                if selected.get('needs_isolation'):
                    from .freellmapi import evaluation_provider
                    effective=evaluation_provider(provider,selected['gateway_model_ids'],body['task'])
                else:
                    effective=copy.deepcopy(provider)
                if profile_id(effective)!=evaluation['route']['profile_id']:
                    raise ValueError('The evaluated gateway route changed')
                name='Candidate '+hashlib.sha256((provider['name']+'\0'+candidate['id']+'\0'+body['task']).encode()).hexdigest()[:20]
                effective.update(name=name,quota_scope_id=provider.get('quota_scope_id') or provider['name'],
                    scope_limit=provider.get('scope_limit',provider['daily_attempt_limit']),candidate_source_name=provider['name'],
                    candidate_id=candidate['id'],candidate_only=False,tasks=[body['task']])
                existing=next((p for p in config['providers'] if p['name']==name),None)
                if existing and (existing.get('candidate_id')!=candidate['id'] or existing.get('candidate_source_name')!=provider['name']):
                    raise ValueError('The evaluated connection name is already in use')
                config['providers']=[p for p in config['providers'] if p['name']!=name]+[effective]
                provider=effective
            else:
                effective=provider
                effective['candidate_only']=False
            if not automatic_free(effective) or (not effective.get('candidate_source_name') and profile_id(effective)!=selected['profile_id']):
                raise ValueError('The evaluated model or gateway membership changed')
            priority=min(ranking*10,100)
            provider.setdefault('task_priority',{})[body['task']]=priority
            Router._validate_config(None,config)
            self.config_path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.config_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(self.config_path)
            self.adapter.update_config(config)
        return {'ok':True,'candidate_id':candidate['id'],'task':body['task'],'provider_name':provider['name'],
            'task_priority':priority,'message':'Evaluated task preference saved'}

    def prepare_keyless(self, *, force=False):
        if type(force) is not bool:
            raise ValueError('force must be boolean')
        if self.cancelled.is_set():
            return {'status':'cancelled','message':'Candidate setup stopped','providers':[]}
        if self.gateway is None or self.config_path is None:
            return {'status':'pending','message':'Managed gateway configuration is unavailable','providers':[]}
        previous=self._state('keyless_setup')
        if not force and previous.get('retry_after',0)>time.time():
            return dict(previous,status='backoff')
        try:
            setup=self.gateway.bootstrap_keyless()
            sources=setup.get('providers',[])
            if not sources:
                return self._state('keyless_setup',{'status':'pending','message':setup.get('message','No anonymous free routes are available'),
                    'providers':[],'retry_after':time.time()+300})
            with provider_settings.LOCK,self.adapter.lock:
                if self.adapter.active_requests:
                    raise ValueError('Inference is active')
                config=copy.deepcopy(self.adapter.config)
                for source in sources:
                    if source.get('kind')!='freellmapi' or source.get('gateway_keyless') is not True or source.get('candidate_only') is not True:
                        raise ValueError('Invalid anonymous staging connection')
                    existing=next((p for p in config['providers'] if p['name']==source['name']),None)
                    if existing and not (existing.get('gateway_keyless') is True and existing.get('candidate_only') is True):
                        raise ValueError('Staging connection name belongs to a configured provider')
                    config['providers']=[p for p in config['providers'] if p['name']!=source['name']]+[copy.deepcopy(source)]
                Router._validate_config(None,config)
                self.config_path.parent.mkdir(parents=True,exist_ok=True)
                tmp=self.config_path.with_suffix('.tmp')
                tmp.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(self.config_path)
                self.adapter.update_config(config)
            return self._state('keyless_setup',{'status':'discovered','message':'Anonymous routes are staged for representative evaluation',
                'providers':[p['name'] for p in sources],'retry_after':0,'evidence':setup.get('evidence',[])})
        except (ValueError,OSError,KeyError,TypeError):
            return self._state('keyless_setup',{'status':'pending','message':'Anonymous gateway setup is not available; retry refresh',
                'providers':[],'retry_after':time.time()+300})

    def bootstrap(self,task='plan', *, force=False):
        if task not in TASK_PROFILES or type(force) is not bool:
            raise ValueError('Invalid bootstrap task or force')
        previous=self._state('bootstrap:'+task)
        if self.cancelled.is_set():
            return {'task':task,'status':'cancelled','evaluations':[],'applied':[]}
        if not force and previous.get('retry_after',0)>time.time():
            return dict(previous,status='backoff')
        catalog=self.catalog()
        evaluations=[]
        now=time.time()
        def rows(data):
            options=[]
            for candidate in data['candidates']:
                if task not in candidate['tasks']:
                    continue
                # Background bootstrap must never spend the user's personal credentials.
                for route in candidate['matched_routes']:
                    if route.get('gateway_keyless') is not True or task not in route['tasks'] or 'text' not in route['capabilities'] or not route['context_window']:
                        continue
                    if task=='vision' and ('vision' not in route['capabilities'] or not route['image_context_tokens']):
                        continue
                    history=[e for e in candidate['evaluations'] if e['task']==task and e.get('fixture_version')==FIXTURE_VERSION and e.get('catalog_route_id',(e.get('route') or {}).get('profile_id'))==route['profile_id']]
                    latest=history[0] if history else None
                    passed=bool(latest and latest.get('proof_mode')=='actual' and latest.get('passed'))
                    actual=[e for e in history if e.get('proof_mode')=='actual' and e['status'] in ('passed','failed')]
                    score=(sum(e['passed'] for e in actual)/len(actual)) if actual else .5
                    options.append({'candidate':candidate,'route':route,'latest':latest,'passed':passed,
                        'rank':(-score,-len(actual),sum(e.get('corrections_required',0) for e in actual)/max(1,len(actual)),
                                sum(e['latency_ms'] for e in actual)/max(1,len(actual)),candidate['priority'],candidate['id'])})
            unique={}
            for item in sorted(options,key=lambda item:item['rank']):
                unique.setdefault(item['candidate']['id'],item)
            return list(unique.values())
        options=rows(catalog)
        choices=[item for item in options if item['passed']]
        challengers=[item for item in options if not item['passed'] and (not item['latest'] or now-item['latest'].get('evaluated_at',0)>=300)]
        stale=any(now-item['latest'].get('evaluated_at',0)>=86400 for item in choices)
        selected=[]
        if not choices:
            if challengers:
                selected=[challengers[0]]
                remaining=challengers[1:]
                diverse=next((item for item in remaining if item['candidate']['provider']!=selected[0]['candidate']['provider']),None)
                if remaining:
                    selected.append(diverse or remaining[0])
        elif force or stale:
            selected=challengers[:1] or (choices[:1] if stale else [])
        for item in selected:
            if self.cancelled.is_set():
                break
            evaluations.append(self.evaluate({'candidate_id':item['candidate']['id'],'task':task,'route_name':item['route']['name']}))
        if selected:
            choices=[item for item in rows(self.catalog()) if item['passed']]
        applied=[]
        for choice in choices[:2]:
            if self.cancelled.is_set():
                break
            try:
                applied.append(self.apply({'candidate_id':choice['candidate']['id'],'task':task,'route_name':choice['route']['name']}))
            except ValueError:
                continue
        return self._state('bootstrap:'+task,{'task':task,'status':'ready' if applied else 'pending','evaluations':evaluations,
            'applied':applied,'reused':bool(applied and not evaluations),'retry_after':0 if applied else time.time()+300})
