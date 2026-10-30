"""Scoped memory changes exercise real isolated stores and preserve effect journals."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory import task_memory
from backend.memory.procedural_memory import get_action_env_fingerprint


class Model:
    def __init__(self): self.calls = []
    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        return {'ok': True, 'message': {'content': json.dumps({'title': 'Sin efecto nuevo',
            'steps': [{'command_id': 'axx.system.telemetry', 'inputs': {}}]})},
            'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}


class SessionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor); self.model = Model()
        self.learning = ActionLearning(self.commands, self.model); self.commands.learning = self.learning
        self.anticipation = AnticipationService(self.commands); self.learning.anticipation = self.anticipation
        self.chats = ChatStore(self.executor.db_path)
        self.a = self.chats.mutate('create', {'title': 'Sesión A'})['id']
        self.b = self.chats.mutate('create', {'title': 'Sesión B'})['id']

    def tearDown(self):
        self.learning.close(); self.anticipation.close(); self.chats.close()
        self.commands.close(); self.executor.close(); self.temp.cleanup()

    def scope(self, task): return task_memory.snapshot(self.learning.db, task)

    def completed(self, task, name, project):
        prepared = self.learning.prepare_steps('Crear ' + name, [{'command_id': 'axx.artifact.write',
            'inputs': {'path': name + '.txt', 'content': 'CANARY_' + name}}], conversation_id=task,
            project_id=project, memory_scope=self.scope(task))
        done = self.learning.execute(prepared['operation_id'], approved=True, plan_hash=prepared['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        return done

    def journal(self):
        return {table: self.commands.db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
                for table in ('command_runs', 'operations', 'artifact_compensations')}

    def forget(self, task=None, key='forget-a'):
        task = task or self.a
        return self.learning.forget_session(task, key, self.scope(task), chats=self.chats)

    def skill(self, key='scoped.file', trigger='Preparar salida', task=None):
        owner = task or self.b
        chat = self.chats.get(owner)
        self.learning.skills.insert({'id':key, 'version':1, 'title':trigger, 'trigger':trigger,
            'schema':{'type':'object', 'properties':{'path':{'type':'string'}}, 'required':['path']},
            'templates':[{'command_id':'axx.artifact.write', 'inputs':{'path':'{{path}}', 'content':'SCOPED'}}],
            'examples':[], 'project_id':'', 'favorite':False, 'checks':['executor_postconditions'],
            'environment':get_action_env_fingerprint(['axx.artifact.write']), 'executable':True, 'created_at':1,
            'origin_task_id':owner, 'memory_scope':chat['memory_scope'], 'memory_context_id':chat['context_id'],
            'provenance':{'source':'user_configuration'}})
        return self.learning.skills.get(key)

    def change(self, text, skill, project='pa', **extra):
        from backend.session_memory import preview_change, apply_change
        chat = self.chats.get(self.a)
        preview = preview_change(self.learning, text, self.a, project_id=project, chats=self.chats,
            memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'],
            target_skill_id=skill['id'], target_skill_version=skill['version'], **extra)
        self.assertEqual(preview['status'], 'ready', preview)
        return apply_change(self.learning, {'change':preview['change'], 'review_hash':preview['review_hash'],
            'confirmed':True}, chats=self.chats)

    def test_forget_closes_known_derivatives_and_preserves_b_files_and_receipts(self):
        first = self.completed(self.a, 'A', 'pa'); other = self.completed(self.b, 'B', 'pb')
        a_scope = self.scope(self.a)
        self.chats.mutate('save', {'id': self.a, 'memory_scope': a_scope, 'draft': 'Borrador humano', 'messages': [
            {'id': 'message-a', 'at': self.chats.clock(), 'role': 'user', 'status': 'complete', 'text': 'CANARY_CHAT_A'}]})
        before = self.journal(); b_before = self.learning.context('pb')
        result = self.forget()
        self.assertEqual(result['state'], 'applied', result)
        self.assertEqual(result['memory_scope'], {'task_id': self.a, 'generation': 1})
        self.assertEqual(self.journal(), before)
        self.assertEqual(self.learning.context('pb'), b_before)
        self.assertEqual((self.executor.workspace_root / 'A.txt').read_text(), 'CANARY_A')
        self.assertEqual((self.executor.workspace_root / 'B.txt').read_text(), 'CANARY_B')
        self.assertEqual(self.chats.get(self.a)['messages'], [])
        self.assertEqual(self.chats.get(self.a)['draft'], 'Borrador humano')
        self.assertEqual(self.chats.get(self.a, include_history=True)['history_messages'][0]['text'], 'CANARY_CHAT_A')
        self.assertTrue(self.learning.get(first['operation_id'])['memory_forgotten'])
        self.assertNotIn('CANARY_A', json.dumps(self.learning._prompt('Nueva tarea', {}, 'pa', self.a)))
        self.assertFalse(self.learning.get(other['operation_id']).get('memory_forgotten'))
        with self.assertRaises(ValueError):
            self.learning.resume(first['operation_id'], approved=True, memory_scope=result['memory_scope'])

    def test_pending_cleanup_blocks_old_writers_and_retries_same_operation(self):
        self.completed(self.a, 'A', 'pa'); old = self.scope(self.a)
        with patch.object(self.chats, 'forget_task', side_effect=OSError('controlled cleanup interruption')):
            with self.assertRaises(OSError): self.learning.forget_session(self.a, 'recover-a', old, chats=self.chats)
        self.assertTrue(task_memory.state(self.learning.db, self.a)['forgetting'])
        with self.assertRaises(ValueError):
            self.learning.prepare_steps('Entrada antigua', [{'command_id': 'axx.artifact.write',
                'inputs': {'path': 'late.txt', 'content': 'STALE'}}], conversation_id=self.a, memory_scope=old)
        result = self.learning.forget_session(self.a, 'recover-a', old, chats=self.chats)
        replay = self.learning.forget_session(self.a, 'recover-a', old, chats=self.chats)
        self.assertEqual(result, replay)
        self.assertFalse(task_memory.state(self.learning.db, self.a)['forgetting'])
        self.assertEqual(result['memory_scope']['generation'], 1)
        self.assertFalse((self.executor.workspace_root / 'late.txt').exists())

    def test_unknown_task_has_no_barrier_and_reopen_recovers_pending_cleanup(self):
        from backend.session_memory import retry_pending
        with self.assertRaises(ValueError):
            self.learning.forget_session('unknown-task', 'unknown-forget', {'task_id':'unknown-task','generation':0}, chats=self.chats)
        self.assertIsNone(task_memory.state(self.learning.db, 'unknown-task')['operation_id'])
        self.completed(self.a, 'A', 'pa'); old = self.scope(self.a); journal = self.journal()
        with patch.object(self.chats, 'forget_task', side_effect=OSError('controlled stop')):
            with self.assertRaises(OSError): self.learning.forget_session(self.a, 'resume-deleted', old, chats=self.chats)
        with self.assertRaises(ValueError): self.chats.mutate('delete', {'id':self.a})
        self.learning.close()
        self.learning = ActionLearning(self.commands, self.model); self.commands.learning = self.learning
        self.learning.anticipation = self.anticipation
        results = retry_pending(self.learning, chats=self.chats)
        self.assertEqual(len(results), 1); self.assertEqual(results[0]['state'], 'applied')
        self.assertFalse(task_memory.state(self.learning.db, self.a)['forgetting'])
        self.assertEqual(self.journal(), journal)
        self.assertEqual((self.executor.workspace_root/'A.txt').read_text(), 'CANARY_A')

    def test_late_inference_cannot_publish_candidate_or_reset_budget_after_forgetting(self):
        entered, release = threading.Event(), threading.Event(); output = []
        def delayed(request):
            entered.set(); self.assertTrue(release.wait(8))
            return {'ok': True, 'message': {'content': json.dumps({'title': 'CANARY_LATE', 'steps': [
                {'command_id': 'axx.artifact.write', 'inputs': {'path': 'late.txt', 'content': 'CANARY_LATE'}}]})},
                'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}
        self.model.route = delayed; old = self.scope(self.a)
        errors = []
        def propose():
            try: output.append(self.learning.propose('Preparar resultado', 'late-plan', conversation_id=self.a, memory_scope=old))
            except BaseException as exc: errors.append(exc)
        worker = threading.Thread(target=propose)
        worker.start()
        try:
            self.assertTrue(entered.wait(8), errors)
            self.forget()
        finally: release.set(); worker.join(10)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors, []); self.assertEqual(len(output), 1)
        plan = self.learning.get('late-plan')
        self.assertTrue(plan['memory_forgotten'])
        self.assertNotIn('CANARY_LATE', json.dumps(plan))
        self.assertGreaterEqual(plan['model_calls_used'], 1)
        self.assertEqual(self.executor.list_operations(), [])

    def test_legacy_planning_captures_context_before_wait_and_never_rebinds_after_unlink(self):
        a = self.chats.get(self.a)
        self.chats.mutate('save', {'id':self.a,'memory_scope':a['memory_scope'],'memory_context_id':a['context_id'],
            'messages':[{'id':'linked-source-a','role':'user','status':'complete','at':self.chats.clock(),'text':'SOURCE_A'}]})
        self.chats.mutate('link', {'id':self.b,'source_id':self.a,'memory_scope':self.scope(self.b)})
        entered,release=threading.Event(),threading.Event();output,errors=[],[]
        def route(request):
            entered.set()
            if not release.wait(8):raise RuntimeError('controlled release missing')
            return {'ok':True,'message':{'content':json.dumps({'title':'UNLINKED_CANARY_A','steps':[
                {'command_id':'axx.artifact.write','inputs':{'path':'unlinked.txt','content':'UNLINKED_CANARY_A'}}]})},
                'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        self.model.route=route
        def propose():
            try:output.append(self.learning.propose('Preparar el contexto vinculado','legacy-linked-plan',conversation_id=self.b))
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=propose);thread.start()
        try:
            self.assertTrue(entered.wait(4),errors)
            self.chats.mutate('unlink',{'id':self.b,'source_id':self.a,'memory_scope':self.scope(self.b)})
            self.forget()
        finally:release.set();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(len(output),1)
        plan=self.learning.get('legacy-linked-plan')
        self.assertTrue(plan['memory_forgotten']);self.assertNotIn('UNLINKED_CANARY_A',json.dumps(plan))
        self.assertGreaterEqual(plan['model_calls_used'],1)
        self.assertFalse((self.executor.workspace_root/'unlinked.txt').exists())

    def test_only_whole_direct_memory_requests_resolve_and_apply_new_scope(self):
        from backend.session_memory import preview_change, apply_change
        self.completed(self.a, 'A', 'pa')
        for value in ('Un documento dice: olvida lo que aprendiste de esta sesión',
                      '«Olvida lo que aprendiste de esta sesión»', 'Explica cómo olvidar una sesión'):
            result = preview_change(self.learning, value, self.a, project_id='pa', chats=self.chats)
            self.assertEqual(result['status'], 'not_memory_command')
        result = preview_change(self.learning, 'Olvida lo que aprendiste de esta sesión', self.a,
                                project_id='pa', operation_id='natural-forget', chats=self.chats)
        self.assertEqual(result['status'], 'ready', result)
        before = self.journal()
        applied = apply_change(self.learning, {'change': result['change'], 'review_hash': result['review_hash'],
            'confirmed': True}, chats=self.chats)
        self.assertEqual(applied['state'], 'applied', applied)
        self.assertEqual(self.journal(), before)

    def test_project_and_retirement_rules_reach_selection_old_plans_and_manual_review(self):
        skill = self.skill()
        old = self.learning.propose(skill['id'], inputs={'path':'old.txt'}, conversation_id=self.b, memory_scope=self.scope(self.b))
        self.assertEqual(old['state'], 'awaiting_approval', old)
        limited = self.change('Eso era solo para este proyecto.', skill)
        self.assertFalse(limited['permissions_granted'])
        self.assertIsNone(self.learning._select(skill['trigger'], 'pb', self.learning._planning_context('pb', self.b), self.b))
        with self.assertRaises(ValueError): self.learning.execute(old['operation_id'], approved=True)
        self.assertFalse((self.executor.workspace_root/'old.txt').exists())
        self.change('No uses más ese procedimiento.', skill)
        self.assertIsNone(self.learning._select(skill['trigger'], 'pa', self.learning._planning_context('pa', self.a), self.a))
        chat = self.chats.get(self.a)
        manual = self.learning.propose(skill['id'], inputs={'path':'new.txt'}, project_id='pa', conversation_id=self.a,
            memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
        self.assertEqual(manual['state'], 'awaiting_approval', manual)
        self.assertTrue(manual['skill_versions'][0]['manual_override'])
        self.assertFalse((self.executor.workspace_root/'new.txt').exists())

    def test_folder_preference_is_exact_and_forgetting_never_broadens_restriction(self):
        first = self.skill('folder.first', 'Usar procedimiento'); self.skill('folder.other', 'Usar procedimiento')
        folder = self.root/'chosen'; folder.mkdir(); (folder/'child').mkdir()
        self.learning.update_context('pa', {'current_folder':str(folder)}, memory_scope=self.scope(self.a))
        result = self.change('Hazlo así de ahora en adelante en esta carpeta.', first, folder=str(folder))
        self.assertEqual(result['selection_policy']['folder_preferences'], [{'project_id':'pa','folder':str(folder)}])
        self.assertEqual(self.learning._select(first['trigger'], 'pa', self.learning._planning_context('pa', self.a), self.a)['id'], first['id'])
        self.learning.update_context('pa', {'current_folder':str(folder/'child')}, memory_scope=self.scope(self.a))
        with self.assertRaises(ValueError): self.learning._select(first['trigger'], 'pa', self.learning._planning_context('pa', self.a), self.a)
        self.change('Eso era solo para este proyecto.', first)
        self.forget()
        rule = self.learning.skills.get(first['id'])['selection_policy']
        self.assertEqual(rule['project_id'], 'pa'); self.assertTrue(rule['retired']); self.assertEqual(rule['folder_preferences'], [])

    def test_completed_forget_replay_does_not_cancel_fresh_generation_work(self):
        old = self.scope(self.a); forgotten = self.forget(); chat = self.chats.get(self.a)
        fresh = self.learning.prepare_steps('Trabajo posterior explícito', [{'command_id':'axx.artifact.write',
            'inputs':{'path':'fresh.txt','content':'FRESH'}}], conversation_id=self.a,
            memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
        self.assertEqual(self.learning.forget_session(self.a, 'forget-a', old, chats=self.chats), forgotten)
        self.assertFalse(self.learning.events[fresh['operation_id']].is_set())
        done = self.learning.execute(fresh['operation_id'], approved=True, plan_hash=fresh['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)

    def test_concurrent_forget_has_one_owner_and_cannot_cancel_a_new_generation(self):
        entered, release = threading.Event(), threading.Event(); cancelled, errors, result = [], [], []
        old = self.scope(self.a)
        def add_run(key, scope):
            chat = self.chats.get(self.a)
            body = {'request_id':key,'memory_scope':scope,'memory_context_id':chat['context_id'],'conversation_id':chat['connect_id']}
            with self.learning.db:
                self.learning.db.execute('INSERT INTO connect_runs VALUES(?,?,?,?,?,?)',
                    (key, key, chat['connect_id'], json.dumps(body), time.time(), time.time()))
        with self.learning.db:
            self.learning.db.execute('CREATE TABLE connect_runs(request_id TEXT PRIMARY KEY,fingerprint TEXT,conversation_id TEXT,body_json TEXT,created_at REAL,updated_at REAL)')
            self.learning.db.execute('CREATE TABLE connect_events(request_id TEXT,seq INTEGER,event_json TEXT)')
        add_run('old', old)
        def cancel(key):
            cancelled.append(key); entered.set()
            if not release.wait(12): raise RuntimeError('controlled provider cancellation timeout')
        provider = SimpleNamespace(cancel=cancel)
        def forget():
            try: result.append(self.learning.forget_session(self.a, 'concurrent', old, chats=self.chats, provider=provider))
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=forget); thread.start()
        try:
            self.assertTrue(entered.wait(8), errors)
            with self.assertRaises(ValueError): self.learning.forget_session(self.a, 'concurrent', old, chats=self.chats, provider=provider)
            child = subprocess.run([sys.executable, '-c',
                'from types import SimpleNamespace as N;from backend.session_memory import _forget_lease;import sys\n'
                'learning=N(commands=N(executor=N(db_path=sys.argv[1])))\n'
                'try:\n with _forget_lease(learning,sys.argv[2]): print("unexpected-owner")\n'
                'except ValueError: print("busy")', str(self.executor.db_path), self.a],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr); self.assertEqual(child.stdout.strip(), 'busy')
        finally: release.set(); thread.join(15)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, []); self.assertEqual(len(result), 1)
        add_run('new', self.scope(self.a))
        self.assertEqual(self.learning.forget_session(self.a, 'concurrent', old, chats=self.chats, provider=provider), result[0])
        self.assertEqual(cancelled, ['old'])

    def test_new_human_skill_edit_preserves_context_after_forget(self):
        self.forget(); skill = self.skill(task=self.a); chat = self.chats.get(self.a)
        updated = self.learning.configure(skill['id'], {'version':1, 'title':'Edición posterior explícita'},
            memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
        self.assertEqual(updated['version'], 2)
        self.assertEqual(updated['memory_scope'], chat['memory_scope'])
        self.assertEqual(updated['memory_context_id'], chat['context_id'])

    def test_new_workshop_workflow_keeps_scoped_real_evidence_after_forget(self):
        from backend.capability_workshop import CapabilityWorkshop
        from backend.tests.test_capability_workshop import definition
        self.forget(); chat = self.chats.get(self.a); workshop = CapabilityWorkshop(self.learning)
        metadata = {'memory_scope':chat['memory_scope'], 'memory_context_id':chat['context_id']}
        try:
            item = workshop.create(definition('axx.artifact.write', {'path':'workflow.txt','content':'FRESH_WORKFLOW'}), **metadata)
            ref = (item['id'], item['revision'], item['digest'])
            workshop.approve(*ref, confirmed=True, **metadata)
            plan = workshop.prepare_validation(*ref, conversation_id=self.a, **metadata)
            done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **metadata)
            self.assertEqual(done['state'], 'succeeded', done)
            active = workshop.activate(*ref, **metadata)
            skill = self.learning.skills.get(active['skill_id'], task_id=self.a)
            self.assertTrue(skill['effect_verified'], skill)
            self.assertEqual(skill['memory_context_id'], chat['context_id'])
            self.assertEqual((self.executor.workspace_root/'workflow.txt').read_text(), 'FRESH_WORKFLOW')
        finally: workshop.close()

    def test_unforgotten_legacy_plan_accepts_new_client_scope_without_rewriting_hash(self):
        plan = self.learning.prepare_steps('Solicitud anterior', [{'command_id':'axx.artifact.write',
            'inputs':{'path':'legacy-approved.txt','content':'LEGACY'}}], conversation_id=self.a, operation_id='legacy-approved')
        chat = self.chats.get(self.a); metadata = {'memory_scope':chat['memory_scope'], 'memory_context_id':chat['context_id']}
        replay = self.learning.prepare_steps('Solicitud anterior', plan['steps'], conversation_id=self.a,
            operation_id='legacy-approved', **metadata)
        self.assertEqual(replay['plan_hash'], plan['plan_hash'])
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'], **metadata)
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual((self.executor.workspace_root/'legacy-approved.txt').read_text(), 'LEGACY')

    def test_model_materialized_b_inherits_a_without_chat_links(self):
        source = self.skill('knowledge.A', 'CANARY_RULE_A', task=self.a)
        independent = self.skill('knowledge.B', 'Independent knowledge', task=self.b)
        def route(request):
            payload = json.loads(request['messages'][1]['content'])
            candidates = payload['previous_action']['available_skills']
            self.assertEqual(candidates[0]['id'], source['id'])
            self.assertNotIn('memory_scope', candidates[0])
            return {'ok':True,'message':{'content':json.dumps({'title':'Resultado derivado', 'steps':[
                {'command_id':'axx.artifact.write','inputs':{'path':'derived-B.txt','content':candidates[0]['title']}}]})},
                'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        self.model.route = route; chat = self.chats.get(self.b)
        plan = self.learning.propose('Genera CANARY_RULE_A en un formato nuevo', conversation_id=self.b,
            memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        self.assertIn(self.a, [ref['task_id'] for ref in plan['memory_dependencies']])
        done = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        learned = self.learning.skills.get(done['learned_action_id'])
        self.assertIn(self.a, [ref['task_id'] for ref in learned['memory_dependencies']])
        receipt = self.commands.get(done['step_records'][0]['operation_id'])
        self.assertIn(self.a, [ref['task_id'] for ref in receipt['memory_dependencies']])
        notice = {'id':'derived-operation-notice','role':'assistant','source':'local','status':'complete',
            'at':self.chats.clock(),'text':source['title'],'operation_id':plan['operation_id']}
        self.chats.mutate('save', {'id':self.b,'messages':[notice], 'memory_scope':chat['memory_scope'],
            'memory_context_id':chat['context_id']})
        self.chats.mutate('save', {'id':self.b,'messages':[{key:value for key,value in notice.items() if key!='operation_id'}],
            'memory_scope':chat['memory_scope'],'memory_context_id':chat['context_id']})
        self.assertEqual(self.chats.get(self.b)['messages'][0]['operation_id'], plan['operation_id'])
        journal = self.journal(); self.forget()
        self.assertEqual(self.journal(), journal)
        self.assertEqual((self.executor.workspace_root/'derived-B.txt').read_text(), 'CANARY_RULE_A')
        with self.assertRaises(ValueError): self.learning.skills.get(learned['id'])
        self.assertEqual(self.learning.skills.get(independent['id'])['title'], 'Independent knowledge')
        self.assertTrue(self.learning.get(plan['operation_id'])['memory_forgotten'])
        self.assertEqual(self.chats.get(self.b)['messages'], [])
        self.assertNotIn('CANARY_RULE_A', json.dumps(self.learning._prompt('Preparar otra salida', {}, '', self.b)))

    def test_repaired_skill_preserves_the_inherited_source_of_the_original(self):
        source=self.skill('repair-source-A','Source procedure',task=self.a)
        self.change('No uses más ese procedimiento.',source)
        b=self.chats.get(self.b)
        plan=self.learning.propose(source['id'],inputs={'path':'before-repair.txt'},conversation_id=self.b,
            memory_scope=b['memory_scope'],memory_context_id=b['context_id'])
        self.assertEqual(plan['state'],'awaiting_approval',plan)
        self.model.route=lambda request:{'ok':True,'message':{'content':json.dumps({'title':'Corrected procedure','steps':[
            {'command_id':'axx.artifact.write','inputs':{'path':'after-repair.txt','content':'REPAIR_FROM_A'}}]})},
            'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        repaired=self.learning.repair(plan['operation_id'],'Usa otro archivo nuevo',memory_scope=b['memory_scope'],memory_context_id=b['context_id'])
        self.assertEqual(repaired['state'],'awaiting_approval',repaired)
        skill=self.learning.skills.get(repaired['skill_versions'][0]['id'],repaired['skill_versions'][0]['version'])
        self.assertEqual(skill['memory_scope'],b['memory_scope'])
        self.assertIn(self.a,[ref['task_id'] for ref in skill['memory_dependencies']])
        self.assertTrue(repaired['skill_versions'][0]['manual_override'])
        self.assertEqual(repaired['skill_versions'][0]['policy_revision'],1)
        journal=self.journal();self.forget()
        self.assertEqual(self.journal(),journal)
        with self.assertRaises(ValueError):self.learning.skills.get(skill['id'],skill['version'])
        self.assertFalse((self.executor.workspace_root/'after-repair.txt').exists())

    def test_known_legacy_parent_is_resolved_without_rebasing_or_rewriting_the_row(self):
        done=self.completed(self.a,'LegacySource','pa');key=done['learned_action_id']
        with self.learning.db:
            raw=json.loads(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',(key,)).fetchone()[0])
            for field in ('origin_task_id','memory_scope','memory_context_id','memory_dependencies'):raw.pop(field,None)
            serialized=json.dumps(raw,ensure_ascii=False)
            self.learning.db.execute('UPDATE skill_versions SET payload=? WHERE id=?',(serialized,key))
        resolved=self.learning.skills.get(key)
        self.assertEqual(resolved['memory_scope'],self.scope(self.a))
        self.assertEqual(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',(key,)).fetchone()[0],serialized)
        b=self.chats.get(self.b)
        configured=self.learning.configure(key,{'version':1,'title':'Corrección humana B'},
            memory_scope=b['memory_scope'],memory_context_id=b['context_id'])
        self.assertIn(self.a,[ref['task_id'] for ref in configured['memory_dependencies']])
        journal=self.journal();self.forget()
        self.assertEqual(self.journal(),journal)
        for version in (1,2):
            with self.assertRaises(ValueError):self.learning.skills.get(key,version)

    def test_known_legacy_parent_keeps_transitive_dependencies_without_rewriting_source(self):
        self.skill('legacy-source.A','CANARY_LEGACY_A',task=self.a)
        independent=self.skill('independent-legacy.B','Independent B',task=self.b)
        self.model.route=lambda request:{'ok':True,'message':{'content':json.dumps({'title':'Derived legacy B','steps':[
            {'command_id':'axx.artifact.write','inputs':{'path':'legacy-derived-B.txt','content':'CANARY_LEGACY_A'}}]})},
            'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        chat=self.chats.get(self.b)
        plan=self.learning.propose('Transforma CANARY_LEGACY_A',conversation_id=self.b,
            memory_scope=chat['memory_scope'],memory_context_id=chat['context_id'])
        self.assertIn(self.a,[ref['task_id'] for ref in plan['memory_dependencies']])
        done=self.learning.execute(plan['operation_id'],approved=True,plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'],'succeeded',done)
        key=done['learned_action_id']
        with self.learning.db:
            raw=json.loads(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',(key,)).fetchone()[0])
            for field in ('origin_task_id','memory_scope','memory_context_id','memory_dependencies'):raw.pop(field,None)
            serialized=json.dumps(raw,ensure_ascii=False)
            self.learning.db.execute('UPDATE skill_versions SET payload=? WHERE id=?',(serialized,key))
        resolved=self.learning.skills.get(key)
        self.assertEqual(resolved['memory_scope'],chat['memory_scope'])
        self.assertIn(self.a,[ref['task_id'] for ref in resolved['memory_dependencies']])
        self.assertEqual(self.learning.db.execute('SELECT payload FROM skill_versions WHERE id=?',(key,)).fetchone()[0],serialized)
        revised=self.learning.configure(key,{'version':1,'title':'Reviewed legacy B'},
            memory_scope=chat['memory_scope'],memory_context_id=chat['context_id'])
        self.assertIn(self.a,[ref['task_id'] for ref in revised['memory_dependencies']])
        journal=self.journal();self.forget()
        self.assertEqual(self.journal(),journal)
        for version in (1,2):
            with self.assertRaises(ValueError):self.learning.skills.get(key,version)
        self.assertEqual(self.learning.skills.get(independent['id'])['title'],'Independent B')
        self.assertEqual((self.executor.workspace_root/'legacy-derived-B.txt').read_text(),'CANARY_LEGACY_A')

    def test_archived_derivatives_do_not_invalidate_an_independent_new_generation(self):
        def save(task, key, role, text):
            chat = self.chats.get(task)
            self.chats.mutate('save', {'id':task,'memory_scope':chat['memory_scope'],'memory_context_id':chat['context_id'],
                'messages':[{'id':key,'role':role,'status':'complete','at':self.chats.clock(),'text':text}]})
        save(self.b, 'original-b', 'user', 'OLD_B')
        self.chats.mutate('link', {'id':self.a,'source_id':self.b,'memory_scope':self.scope(self.a)})
        save(self.a, 'derived-a-zero', 'assistant', 'OLD_A_DERIVED_B')
        self.forget()
        save(self.a, 'new-a-user', 'user', 'INDEPENDENT_A_ONE')
        save(self.a, 'new-a-assistant', 'assistant', 'INDEPENDENT_A_RESPONSE')
        before = self.chats.get(self.a)
        plan = self.learning.prepare_steps('Nueva orden independiente', [{'command_id':'axx.artifact.write',
            'inputs':{'path':'independent-a-one.txt','content':'FRESH_A'}}], conversation_id=self.a,
            memory_scope=before['memory_scope'], memory_context_id=before['context_id'])
        b = self.chats.get(self.b)
        self.learning.forget_session(self.b,'forget-b',b['memory_scope'],memory_context_id=b['context_id'],chats=self.chats)
        after = self.chats.get(self.a)
        self.assertEqual(after['context_id'], before['context_id'])
        self.assertEqual(after['messages'], before['messages'])
        self.assertFalse(self.learning.get(plan['operation_id']).get('memory_forgotten'))
        done = self.learning.execute(plan['operation_id'],approved=True,plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'],'succeeded',done)
        self.assertEqual((self.executor.workspace_root/'independent-a-one.txt').read_text(),'FRESH_A')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_new_reviewed_compensation_notice_can_be_saved_after_forgetting(self):
        done=self.completed(self.a,'A','pa');source=done['step_records'][0]['operation_id'];self.forget()
        preview=self.commands.compensation_preview(source)
        operation=self.commands.prepare_compensation(source,preview['source_receipt_hash'],preview['compensation']['revision'],
            action=preview['action'],operation_id='new-compensation')
        compensated=self.commands.execute(operation['operation_id'],approved=True)
        self.assertEqual(compensated['state'],'succeeded',compensated)
        chat=self.chats.get(self.a)
        self.chats.mutate('save',{'id':self.a,'memory_scope':chat['memory_scope'],'memory_context_id':chat['context_id'],
            'messages':[{'id':'new-compensation-notice','role':'assistant','source':'local','status':'complete',
                'at':self.chats.clock(),'text':'Compensación revisada y verificada','operation_id':operation['operation_id']}]})
        self.assertEqual(self.chats.get(self.a)['messages'][0]['operation_id'],operation['operation_id'])
        self.assertEqual(self.commands.get(source)['state'],'succeeded')

    def test_workshop_generated_commands_keep_origin_and_forget_only_attributable_code(self):
        from backend.capability_workshop import CapabilityWorkshop
        from backend.tests.test_generated_commands import transform
        workshop = CapabilityWorkshop(self.learning)
        try:
            def activate(task):
                chat = self.chats.get(task)
                item = workshop.create(transform(), memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
                ref = (item['id'], item['revision'], item['digest'])
                workshop.validate(*ref); workshop.approve(*ref, confirmed=True)
                return workshop.activate(*ref)
            first, second = activate(self.a), activate(self.b)
            pending = self.commands.prepare(first['command_id'], {'text':' AXX '}, conversation_id=self.b, memory_scope=self.scope(self.b))
            before = self.journal()
            result = self.forget()
            self.assertEqual(result['counts']['workshop']['withdrawn_capability_revisions'], 1)
            self.assertEqual(self.journal(), before)
            self.assertTrue(workshop.get(first['id'])['memory_forgotten'])
            self.assertEqual(workshop.get(second['id'])['active_revision'], second['revision'])
            self.assertEqual(self.commands.execute(pending['operation_id'])['state'], 'failed')
            other = self.commands.prepare(second['command_id'], {'text':' AXX FUNCIONA '}, conversation_id=self.b, memory_scope=self.scope(self.b))
            done = self.commands.execute(other['operation_id'])
            self.assertEqual(done['state'], 'succeeded', done); self.assertEqual(done['output']['result'], 'axx funciona')
        finally: workshop.close()

    def test_late_workshop_generation_does_not_create_a_derivative(self):
        from backend.capability_workshop import CapabilityWorkshop
        from backend.tests.test_generated_commands import transform
        entered, release = threading.Event(), threading.Event(); errors = []
        def route(request):
            entered.set()
            if not release.wait(10): raise RuntimeError('controlled fixture timeout')
            return {'ok':True, 'message':{'content':json.dumps(transform())}, 'route':{'upstream_attempts':1,'attempt_budget_used':1}}
        self.model.route = route; workshop = CapabilityWorkshop(self.learning); chat = self.chats.get(self.a)
        def generate():
            try: workshop.generate('Normalizar texto', kind='python_transform', conversation_id=self.a,
                memory_scope=chat['memory_scope'], memory_context_id=chat['context_id'])
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=generate); thread.start()
        try:
            self.assertTrue(entered.wait(8), errors); self.forget()
        finally: release.set(); thread.join(10); workshop.close()
        self.assertFalse(thread.is_alive()); self.assertEqual(len(errors), 1); self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(workshop.db.execute('SELECT COUNT(*) FROM capability_revisions').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
