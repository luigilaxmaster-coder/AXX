"""Scoped mobile mirror fences on isolated stores; no device or provider calls."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from backend.chat_store import ChatStore
from backend.memory import task_memory
from backend.mobile.gateway import MobileGateway
from backend.mobile.shared_state import SharedState


class SharedTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'state.db'
        self.chats = ChatStore(self.path)
        self.shared = SharedState(self.path)
        self.a = self.chats.mutate('create',{})['id']
        self.b = self.chats.mutate('create',{})['id']

    def tearDown(self):
        self.chats.close()
        self.temp.cleanup()

    def chat(self,task):
        return self.chats.get(task)

    def message(self,mid,text,role='user',**changes):
        return {'id':mid,'text':text,'role':role,'status':'complete','at':time.time()*1000,**changes}

    def save(self,task,message):
        chat = self.chat(task)
        self.chats.mutate('save',{'id':task,'messages':[message],
            'memory_scope':chat['memory_scope'],'memory_context_id':chat['context_id']})

    def mirror(self,task,messages,**changes):
        shared_id = self.chat(task)['shared_id']
        return self.shared.merge_messages(messages,'desktop',shared_id,
            **{key:self.shared.capture_scope(shared_id)[key] for key in ('memory_scope','memory_context_id')},**changes)

    def begin(self):
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return task_memory.begin_forget(db,self.a,'forget-a',task_memory.state(db,self.a)['generation'])

    def finish(self,reference):
        chat = self.chats.forget_task(self.a,reference)
        shared = self.shared.forget_task(self.a,reference)
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(db,reference,{'chat':chat,'shared':shared})
        return chat,shared

    def test_snapshot_events_late_sync_and_restart_preserve_b_and_old_bytes(self):
        a_user = self.message('a-user','PRIVATE_A')
        b_user = self.message('b-user','KEEP_B')
        b_assistant = self.message('b-direct','KEEP_DIRECT_ASSISTANT','assistant')
        for task,message in ((self.a,a_user),(self.b,b_user),(self.b,b_assistant)):
            self.save(task,message)
            self.mirror(task,[message])
        trusted = self.message('known-only','Trusted user')
        self.save(self.a,trusted)
        with self.assertRaises(ValueError):
            self.mirror(self.a,[trusted | {'role':'assistant'}])
        self.chats.mutate('link',{'id':self.b,'source_id':self.a})
        a_chat,b_chat = self.chat(self.a),self.chat(self.b)
        a_memory = self.shared.capture_scope(a_chat['shared_id'])
        b_memory = self.shared.capture_scope(b_chat['shared_id'])
        derived = self.message('b-derived','PRIVATE_DERIVED_A','assistant')
        self.shared.merge_messages([derived],'pc',b_chat['shared_id'],**b_memory)
        cursor = self.shared.snapshot(b_chat['shared_id'])['cursor']
        reference = self.begin()
        with self.assertRaises(ValueError):
            self.shared.forget_task(self.a,{'task_id':self.a,'generation':True})
        self.assertEqual(self.shared.snapshot(a_chat['shared_id'])['messages'],[])
        self.assertCountEqual([m['id'] for m in self.shared.snapshot(b_chat['shared_id'])['messages']],['b-user','b-direct'])
        self.assertNotIn('PRIVATE_',json.dumps(self.shared.events(0)))
        _,result = self.finish(reference)
        self.assertEqual(result,self.shared.forget_task(self.a,reference))
        with self.assertRaises(ValueError):
            self.shared.merge_messages([self.message('late','PRIVATE_LATE','assistant')],'pc',a_chat['shared_id'],**a_memory)
        with self.assertRaises(ValueError):
            self.shared.merge_messages([derived],'desktop',b_chat['shared_id'],**b_memory)
        with self.assertRaises(ValueError):
            self.shared.merge_messages([a_user],'desktop',a_chat['shared_id'])
        fresh = self.shared.capture_scope(a_chat['shared_id'])
        self.shared.merge_messages([a_user],'desktop',a_chat['shared_id'],**fresh)
        self.assertEqual(self.shared.snapshot(a_chat['shared_id'])['messages'],[])
        self.shared.merge_messages([self.message('fresh-user','FRESH')],'mobile',a_chat['shared_id'],**fresh)
        self.shared = SharedState(self.path)
        self.assertEqual([m['id'] for m in self.shared.snapshot(a_chat['shared_id'])['messages']],['fresh-user'])
        self.assertGreater(self.shared.snapshot(a_chat['shared_id'])['cursor'],cursor)
        with self.shared.connect() as db:
            self.assertEqual(db.execute("SELECT text FROM shared_messages WHERE id='a-user'").fetchone()[0],'PRIVATE_A')
            self.assertTrue(db.execute("SELECT 1 FROM shared_events WHERE data LIKE '%PRIVATE_A%'").fetchone())
        self.assertEqual(self.chat(self.a)['shared_id'],a_chat['shared_id'])

    def test_shared_only_derivation_fences_pending_and_rotates_extra_b_context(self):
        self.save(self.a,self.message('source','PRIVATE_A'))
        self.chats.mutate('link',{'id':self.b,'source_id':self.a})
        b = self.chat(self.b)
        memory = self.shared.capture_scope(b['shared_id'])
        self.shared.merge_messages([self.message('shared-only','PRIVATE_SHARED_DERIVED','assistant')],'pc',b['shared_id'],**memory)
        self.chats.mutate('unlink',{'id':self.b,'source_id':self.a})
        before = self.chat(self.b)
        reference = self.begin()
        with self.assertRaises(ValueError):
            with self.chats.db() as db:
                task_memory.assert_context(db,before['memory_scope'],before['context_id'])
        chat_result,shared_result = self.finish(reference)
        self.assertNotIn(self.b,chat_result['affected_task_ids'])
        self.assertIn(self.b,shared_result['affected_task_ids'])
        self.assertIn(before['context_id'],shared_result['old_connect_ids'])
        self.assertEqual(self.chat(self.b)['memory_scope'],before['memory_scope'])
        self.assertNotEqual(self.chat(self.b)['context_id'],before['context_id'])
        self.assertEqual(self.shared.snapshot(b['shared_id'])['messages'],[])
        self.assertEqual(self.shared.capture_scope(b['shared_id'])['memory_dependencies'],[before['memory_scope']])

    def test_archived_shared_derivative_does_not_rotate_independent_new_generation(self):
        self.save(self.b,self.message('source-b','OLD_B'))
        self.chats.mutate('link',{'id':self.a,'source_id':self.b})
        a_zero = self.chat(self.a)
        old = self.message('old-a-shared','OLD_A_DERIVED_B','assistant')
        self.shared.merge_messages([old],'pc',a_zero['shared_id'],**self.shared.capture_scope(a_zero['shared_id']))
        self.finish(self.begin())
        fresh = self.message('new-a-shared','INDEPENDENT_A_ONE','assistant')
        memory = self.shared.capture_scope(a_zero['shared_id'])
        self.shared.merge_messages([fresh],'pc',a_zero['shared_id'],**memory)
        before = self.chat(self.a)
        snapshot = self.shared.snapshot(a_zero['shared_id'])
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            b_forget = task_memory.begin_forget(db,self.b,'forget-b',task_memory.state(db,self.b)['generation'])
        self.chats.forget_task(self.b,b_forget)
        result = self.shared.forget_task(self.b,b_forget)
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(db,b_forget,result)
        self.assertNotIn(self.a,result['affected_task_ids'])
        self.assertEqual(self.chat(self.a)['context_id'],before['context_id'])
        self.assertEqual(self.shared.snapshot(a_zero['shared_id']),snapshot)
        self.shared.merge_messages([self.message('late-fresh','STILL_CURRENT')],'mobile',a_zero['shared_id'],**memory)
        self.assertEqual(self.shared.snapshot(a_zero['shared_id'])['messages'][-1]['text'],'STILL_CURRENT')

    def test_legacy_unknown_assistant_is_quarantined_without_harming_unrelated_chat(self):
        self.save(self.a,self.message('source','PRIVATE_A'))
        b = self.chat(self.b)
        legacy = self.message('unknown','PRIVATE_LEGACY','assistant')
        self.shared.merge_messages([legacy],'desktop',b['shared_id'])
        c = self.chats.mutate('create',{})['id']
        c_chat = self.chat(c)
        self.shared.merge_messages([self.message('unrelated','KEEP_C','assistant')],'desktop',c_chat['shared_id'])
        self.shared.merge_messages([self.message('unmapped','UNATTRIBUTED_HISTORY')],'desktop','legacy-unbound')
        self.chats.mutate('link',{'id':self.b,'source_id':self.a})
        reference = self.begin()
        self.assertEqual(self.shared.snapshot(b['shared_id'])['messages'],[])
        _,result = self.finish(reference)
        self.assertTrue(result['requires_review'])
        self.assertEqual(result['counts']['unmapped_legacy_review'],1)
        self.assertEqual(self.shared.snapshot(c_chat['shared_id'])['messages'][0]['text'],'KEEP_C')
        self.chats.mutate('create',{'shared_id':'legacy-unbound'})
        self.assertEqual(self.shared.snapshot('legacy-unbound')['messages'],[])
        fresh = self.shared.capture_scope(self.chat(self.a)['shared_id'])
        self.shared.merge_messages([self.message('unknown-old','PRIVATE_OLD_IMPORT','assistant',at=time.time()*1000-10000)],'desktop',self.chat(self.a)['shared_id'],
            memory_scope=fresh['memory_scope'],memory_context_id=fresh['memory_context_id'])
        self.assertEqual(self.shared.snapshot(self.chat(self.a)['shared_id'])['messages'],[])
        with self.shared.connect() as db:
            self.assertEqual(db.execute("SELECT text,requires_review FROM shared_messages WHERE id='unknown'").fetchone()[0],'PRIVATE_LEGACY')
            self.assertEqual(db.execute("SELECT requires_review FROM shared_messages WHERE id='unknown-old'").fetchone()[0],1)

    def test_gateway_late_reply_keeps_captured_scope_and_new_explicit_user_can_continue(self):
        entered,release = threading.Event(),threading.Event()
        calls = []
        def backend(method,path,body):
            if path.endswith('/resolve'):
                return {'match':'none'}
            if path=='/axx-api/chat':
                calls.append(body)
                entered.set()
                release.wait(3)
                return {'choices':[{'message':{'content':'PRIVATE_LATE' if len(calls)==1 else 'FRESH_REPLY'}}]}
            raise AssertionError(path)
        gateway = MobileGateway(self.path,self.temp.name,backend)
        gateway.preferences = {'provider':'bridge','provider_name':'fixture','model':'fixture'}
        gateway.share_history = True
        device = gateway.store.consume_pairing(gateway.store.create_pairing(),'Fixture phone')
        shared_id = self.chat(self.a)['shared_id']
        body = {'operation':'chat','command_id':'first','conversation_id':shared_id,'text':'Human request'}
        with self.assertLogs('axx.mobile',level='ERROR'):
            first = gateway.admit_chat(device['device_id'],body)
            self.assertTrue(entered.wait(2))
            captured = calls[0]
            self.assertEqual(captured['conversation_id'],self.a)
            self.assertEqual(captured['memory_scope']['generation'],0)
            reference = self.begin()
            self.finish(reference)
            release.set()
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                result = gateway.store.command(device['device_id'],'first')
                if result['state']=='outcome_unknown':
                    break
                time.sleep(.01)
        self.assertEqual(result['state'],'outcome_unknown')
        self.assertEqual(self.shared.snapshot(shared_id)['messages'],[])
        retry = gateway.admit_chat(device['device_id'],body)
        self.assertEqual(retry['task_id'],first['task_id'])
        self.assertEqual(len(calls),1)
        gateway.admit_chat(device['device_id'],body | {'command_id':'second','text':'New explicit human request'})
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            current = gateway.store.command(device['device_id'],'second')
            if current['state']=='completed':
                break
            time.sleep(.01)
        self.assertEqual(current['state'],'completed',current)
        self.assertEqual(calls[1]['memory_scope']['generation'],1)
        self.assertEqual(self.shared.snapshot(shared_id)['messages'][-1]['text'],'FRESH_REPLY')

    def test_completed_chat_cache_is_projected_without_erasing_operation_receipt(self):
        gateway = MobileGateway(self.path,self.temp.name,lambda *args:None)
        device = gateway.store.consume_pairing(gateway.store.create_pairing(),'Fixture phone')
        admission = gateway.store.admit_command(device['device_id'],'cached',{'operation':'chat'})
        task = admission['task_id']
        shared_id = self.chat(self.a)['shared_id']
        memory = self.shared.capture_scope(shared_id)
        self.shared.merge_messages([self.message(task+':assistant','PRIVATE_CACHED','assistant')],'pc',shared_id,**memory)
        receipt = {'choices':[{'message':{'role':'assistant','content':'PRIVATE_CACHED'}}]}
        gateway.store.finish_command(task,'completed',receipt)
        self.assertIn('PRIVATE_CACHED',json.dumps(gateway.command(device['device_id'],'cached')))
        self.finish(self.begin())
        projected = gateway.command(device['device_id'],'cached')
        self.assertTrue(projected['memory_forgotten'])
        self.assertEqual(projected['task_id'],task)
        self.assertEqual(projected['state'],'completed')
        self.assertNotIn('PRIVATE_CACHED',json.dumps(projected))
        self.assertEqual(gateway.store.command(device['device_id'],'cached')['result'],receipt)


if __name__=='__main__':
    unittest.main()
