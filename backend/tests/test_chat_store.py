import tempfile
import unittest
from pathlib import Path
from backend.chat_store import ChatStore, TTL
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService, ApprovalRequired

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1800000000000
        self.path=Path(self.tmp.name)/'state.db';self.store=ChatStore(self.path,lambda:self.now)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def message(self, mid='m', **kw):
        return dict(id=mid,role='user',text='private',source='model',status='complete',at=self.now,**kw)
    def test_shared_thread_maps_to_persisted_mode(self):
        cid=self.store.mutate('create',{})['id']; row=self.store.get(cid)
        self.assertEqual(self.store.by_shared_id(row['shared_id'])['id'],cid)
        self.store.mutate('update',{'id':cid,'command_mode':'auto_safe'})
        self.assertEqual(self.store.by_shared_id(row['shared_id'])['mode'],'auto_safe')
        with self.assertRaises(ValueError): self.store.by_shared_id('unknown-shared')

    def test_migration_idempotent_and_transactional(self):
        body={'messages':[self.message()],'draft':'unsent','connect_id':'provider-thread','shared_id':'phone-thread'}
        cid=self.store.mutate('migrate',body)['id']
        self.assertEqual(cid,self.store.mutate('migrate',body)['id'])
        row=self.store.get(cid);self.assertEqual(len(row['messages']),1);self.assertEqual(row['draft'],'unsent')
        self.assertEqual(row['connect_id'],'provider-thread');self.assertEqual(row['shared_id'],'phone-thread')
        with self.assertRaises(ValueError):self.store.mutate('save',{'id':cid,'messages':[self.message('m2'),{'id':'bad'}]})
        self.assertEqual(len(self.store.get(cid)['messages']),1)
    def test_groups_only_share_curated_context_and_rotated_provider(self):
        group=self.store.mutate('group',{'title':'Work'})['id']
        a=self.store.mutate('create',{'group_id':group})['id'];b=self.store.mutate('create',{'group_id':group})['id']
        self.store.mutate('save',{'id':a,'messages':[self.message()]})
        before=self.store.get(b)['connect_id']
        self.store.mutate('context',{'group_id':group,'text':'Shared only'})
        row=self.store.get(b);self.assertEqual(row['messages'],[]);self.assertEqual(row['context'][0]['text'],'Shared only')
        self.assertNotEqual(row['connect_id'],before)
        self.store.mutate('update',{'id':b,'group_id':None});self.assertEqual(self.store.get(b)['context'],[])
    def test_exact_expiry_and_no_resurrection(self):
        cid=self.store.mutate('create',{})['id'];m=self.message()
        self.store.mutate('save',{'id':cid,'messages':[m]})
        self.now+=TTL-1;self.assertEqual(len(self.store.get(cid)['messages']),1)
        self.store.mutate('save',{'id':cid,'messages':[]})
        self.now+=1;self.assertEqual(self.store.get(cid)['messages'],[])
        self.store.mutate('save',{'id':cid,'messages':[m]});self.assertEqual(self.store.get(cid)['messages'],[])
    def test_cross_chat_message_collision_rejected(self):
        a=self.store.mutate('create',{})['id'];b=self.store.mutate('create',{})['id']
        self.store.mutate('save',{'id':a,'messages':[self.message()]})
        with self.assertRaises(ValueError):self.store.mutate('save',{'id':b,'messages':[self.message()]})
    def test_linked_context_is_explicit_snapshot_and_keeps_original_expiry(self):
        a=self.store.mutate('create',{})['id'];b=self.store.mutate('create',{})['id'];c=self.store.mutate('create',{})['id']
        self.store.mutate('save',{'id':a,'messages':[self.message('linked')],'draft':'never shared'})
        before=self.store.get(b)['connect_id']
        self.store.mutate('link',{'id':b,'source_id':a})
        linked=self.store.get(b);self.assertNotEqual(linked['connect_id'],before)
        self.assertEqual([m['text'] for m in linked['links'][0]['messages']],['private'])
        self.store.mutate('save',{'id':a,'messages':[self.message('later')]})
        self.assertEqual(len(self.store.get(b)['links'][0]['messages']),1)
        with self.assertRaises(ValueError):self.store.mutate('link',{'id':c,'source_id':b})
        self.now+=TTL-1;self.store.mutate('save',{'id':a});self.store.mutate('save',{'id':b});self.store.mutate('save',{'id':c})
        self.now+=1;self.assertEqual(self.store.get(b)['links'][0]['messages'],[])
        self.assertEqual(self.store.get(c)['links'],[])
    def test_link_limits_removal_and_source_deletion(self):
        destination=self.store.mutate('create',{})['id'];sources=[]
        for i in range(4):
            source=self.store.mutate('create',{})['id'];sources.append(source)
            self.store.mutate('save',{'id':source,'messages':[self.message('s'+str(i))]})
        for source in sources[:3]:self.store.mutate('link',{'id':destination,'source_id':source})
        with self.assertRaises(ValueError):self.store.mutate('link',{'id':destination,'source_id':sources[3]})
        with self.assertRaises(ValueError):self.store.mutate('link',{'id':destination,'source_id':destination})
        self.store.mutate('unlink',{'id':destination,'source_id':sources[0]})
        self.store.mutate('delete',{'id':sources[1]})
        self.assertEqual(len(self.store.get(destination)['links']),1)
    def test_profile_persistence_validation_and_connect_rotation(self):
        cid=self.store.mutate('create',{})['id'];before=self.store.get(cid)['connect_id']
        self.store.mutate('profile',{'name':'Axx','role':'Asistente de proyectos','instructions':'Responde breve','preferred_commands':['axx.system.telemetry']})
        self.assertEqual(self.store.get(cid)['agent_profile']['instructions'],'Responde breve')
        self.assertNotEqual(self.store.get(cid)['connect_id'],before)
        with self.assertRaises(ValueError):self.store.mutate('profile',{'instructions':'x'*4001})
        with self.assertRaises(ValueError):self.store.mutate('profile',{'execute_any':True})
    def test_context_expires_even_in_active_chat(self):
        group=self.store.mutate('group',{'title':'Work'})['id'];cid=self.store.mutate('create',{'group_id':group})['id']
        self.store.mutate('context',{'group_id':group,'text':'old instruction'})
        self.now+=TTL-1;self.store.mutate('save',{'id':cid,'messages':[]})
        self.now+=1;self.assertEqual(self.store.get(cid)['context'],[])
    def test_draft_expires_independently_and_title_uses_first_message(self):
        cid=self.store.mutate('create',{'draft':'old draft'})['id']
        self.now+=TTL-1
        self.store.mutate('save',{'id':cid,'draft':'old draft','messages':[self.message()]})
        self.assertEqual(self.store.get(cid)['title'],'private')
        self.now+=1
        row=self.store.get(cid)
        self.assertEqual(row['draft'],'')
        self.assertEqual(len(row['messages']),1)
    def test_group_context_budget_and_attachment_validation(self):
        group=self.store.mutate('group',{'title':'Work'})['id']
        cid=self.store.mutate('create',{'group_id':group})['id']
        for _ in range(3):self.store.mutate('context',{'group_id':group,'text':'a'*4000})
        with self.assertRaises(ValueError):self.store.mutate('context',{'group_id':group,'text':'over budget'})
        with self.assertRaises(ValueError):self.store.mutate('save',{'id':cid,'attachment':[]})
    def test_command_modes_enforced_without_dispatch(self):
        executor=ActionExecutor(self.path,Path(self.tmp.name)/'artifacts');commands=CommandService(executor)
        try:
            ask=commands.prepare('axx.system.telemetry',{},conversation_id='chat-a',command_mode='ask')
            self.assertEqual(ask['state'],'awaiting_approval')
            with self.assertRaises(ApprovalRequired):commands.execute(ask['operation_id'])
            with self.assertRaises(ValueError):commands.prepare('axx.system.telemetry',{},conversation_id='chat-b',command_mode='auto_safe')
            commands.cancel(ask['operation_id'])
            auto=commands.prepare('axx.system.telemetry',{},conversation_id='chat-b',command_mode='auto_safe')
            self.assertEqual(auto['state'],'prepared')
            commands.cancel(auto['operation_id'])
            sensitive=commands.prepare('axx.artifact.write',{'path':'test.txt','content':'x'},conversation_id='chat-b',command_mode='auto_safe')
            self.assertEqual(sensitive['state'],'awaiting_approval')
            with self.assertRaises(ApprovalRequired):commands.execute(sensitive['operation_id'])
            with self.assertRaises(ValueError):commands.prepare('axx.system.telemetry',{},operation_id=ask['operation_id'],conversation_id='chat-b',command_mode='auto_safe')
            self.assertFalse((Path(self.tmp.name)/'artifacts/test.txt').exists())
        finally:commands.close();executor.close()

if __name__=='__main__':unittest.main()
