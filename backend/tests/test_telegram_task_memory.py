"""Telegram task-memory boundaries with isolated SQLite and synthetic transports."""
import copy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from backend.chat_store import ChatStore
from backend.memory import task_memory
from backend.telegram.service import TelegramService
from backend.telegram.daemon import CommandProxy


class TelegramTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.chats=ChatStore(Path(self.temp.name)/'state.db')
        self.account={'account_id':10,'owner_id':20,'enabled':True,'grants':{'conversation':True,'pc_commands':True}}
        self.account_patch=patch('backend.telegram.service.load_account',side_effect=lambda _:copy.deepcopy(self.account));self.account_patch.start()
        self.commands=Mock();self.commands.resolve.return_value={'match':'none'}
        self.adapter=Mock();self.adapter.route.return_value={'ok':True,'message':{'content':'SYNTHETIC_RESPONSE'}}
        self.service=TelegramService(self.temp.name,self.chats,self.commands,self.adapter,
            lambda:{'provider':'bridge','model':'synthetic','provider_name':'synthetic','selection_mode':'manual'})

    def tearDown(self):
        self.account_patch.stop();self.chats.close();self.temp.cleanup()

    def body(self,message=1,text='Synthetic user message'):
        return {'account_id':10,'peer_id':20,'message_id':message,'sent_at':time.time(),'kind':'text','text':text}

    def forget(self,task):
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE');ref=task_memory.begin_forget(db,task,'forget-'+str(time.time_ns()),task_memory.state(db,task)['generation'])
        result=self.chats.forget_task(task,ref)
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE');task_memory.finish_forget(db,ref,result)

    def test_new_entry_uses_current_scope_but_cached_response_never_gets_rebased(self):
        first=self.service.admit(self.body(text='SYNTHETIC_OLD_USER'))
        self.assertEqual(first['state'],'succeeded',first)
        chat=self.service._thread(self.account);old_context=chat['connect_id']
        self.assertEqual(self.service.admit(self.body(text='SYNTHETIC_OLD_USER')),first)
        self.assertEqual(self.adapter.route.call_count,1)
        self.forget(chat['id'])
        replay=self.service.admit(self.body(text='SYNTHETIC_OLD_USER'))
        self.assertEqual(replay['state'],'unknown');self.assertNotIn('SYNTHETIC_RESPONSE',replay['text'])
        self.assertEqual(self.adapter.route.call_count,1)
        result=self.service.admit(self.body(2,'SYNTHETIC_NEW_USER'))
        self.assertEqual(result['state'],'succeeded',result)
        request=self.adapter.route.call_args.args[0]
        self.assertNotEqual(request['conversation_id'],old_context)
        self.assertNotIn('SYNTHETIC_OLD_USER',str(request['messages']))
        self.assertNotIn('memory_scope',request);self.assertNotIn('memory_context_id',request)
        with self.service._db() as db:
            rows=db.execute('SELECT memory_scope,memory_context_id FROM inbox ORDER BY created').fetchall()
        self.assertIn('"generation": 0',rows[0][0]);self.assertIn('"generation": 1',rows[1][0])
        self.assertEqual(rows[0][1],old_context)

    def test_forget_during_provider_response_cannot_save_or_publish_old_assistant(self):
        chat=self.service._thread(self.account);captured=copy.deepcopy(chat)
        def route(envelope):
            self.assertEqual(envelope['conversation_id'],captured['connect_id']);self.forget(chat['id'])
            return {'ok':True,'message':{'content':'SYNTHETIC_LATE_PRIVATE'}}
        self.adapter.route.side_effect=route
        body=self.body();result=self.service.admit(body)
        self.assertEqual(result['state'],'unknown');self.assertNotIn('SYNTHETIC_LATE_PRIVATE',str(result))
        self.assertEqual(self.chats.get(chat['id'])['messages'],[])
        self.assertEqual(self.service.admit(body)['state'],'unknown');self.adapter.route.assert_called_once()
        with self.service._db() as db:self.assertIsNone(db.execute('SELECT response FROM inbox').fetchone()[0])

    def test_linked_a_forget_rejects_b_late_result_without_erasing_b_user(self):
        b=self.service._thread(self.account);a=self.chats.mutate('create',{'title':'A'})['id']
        source=self.chats.get(a)
        self.chats.mutate('save',{'id':a,'memory_scope':source['memory_scope'],'memory_context_id':source['connect_id'],
            'messages':[{'id':'linked-source','role':'user','text':'SYNTHETIC_A','status':'complete','at':self.chats.clock()}]})
        self.chats.mutate('link',{'id':b['id'],'source_id':a,'memory_scope':b['memory_scope'],'memory_context_id':b['connect_id']})
        def route(envelope):
            self.assertEqual(envelope['conversation_id'],b['connect_id']);self.forget(a)
            return {'ok':True,'message':{'content':'SYNTHETIC_LINK_A_LATE'}}
        self.adapter.route.side_effect=route
        result=self.service.admit(self.body(text='KEEP_B_USER'))
        self.assertEqual(result['state'],'unknown');self.assertNotIn('SYNTHETIC_LINK_A_LATE',str(result))
        current=self.chats.get(b['id']);self.assertEqual(current['memory_scope'],b['memory_scope'])
        self.assertNotEqual(current['connect_id'],b['connect_id'])
        self.assertEqual([m['text'] for m in current['messages']],['KEEP_B_USER'])

    def test_forget_after_resolve_prevents_provider_admission(self):
        chat=self.service._thread(self.account)
        self.commands.resolve.side_effect=lambda *_args,**_kwargs:(self.forget(chat['id']) or {'match':'none'})
        self.assertEqual(self.service.admit(self.body())['state'],'unknown')
        self.adapter.route.assert_not_called();self.commands.prepare.assert_not_called()

    def test_command_prepare_and_daemon_proxy_keep_the_entry_identity(self):
        chat=self.service._thread(self.account)
        self.commands.resolve.return_value={'match':'exact','command_id':'synthetic','inputs':{}}
        self.commands.prepare.return_value={'state':'awaiting_approval'}
        result=self.service.admit(self.body(text='/synthetic'))
        self.assertEqual(result['state'],'awaiting_approval',result)
        self.assertEqual(self.commands.prepare.call_args.kwargs['memory_scope'],chat['memory_scope'])
        self.assertEqual(self.commands.prepare.call_args.kwargs['memory_context_id'],chat['connect_id'])
        core=Mock();proxy=CommandProxy(core)
        proxy.prepare('synthetic',{},source='text',operation_id='synthetic-op',conversation_id=chat['id'],command_mode='ask',
            memory_scope=chat['memory_scope'],memory_context_id=chat['connect_id'])
        payload=core.request.call_args.args[2]
        self.assertEqual(payload['memory_scope'],chat['memory_scope']);self.assertEqual(payload['memory_context_id'],chat['connect_id'])


if __name__=='__main__':unittest.main()
