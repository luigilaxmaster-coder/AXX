import json
import tempfile
import time
import unittest
from pathlib import Path

from backend.chat_store import ChatStore
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory import task_memory


class ChatForgettingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.db'
        self.now = time.time() * 1000
        self.store = ChatStore(self.path, lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def chat(self, **body):
        return self.store.mutate('create', body)['id']

    def save(self, cid, mid, content, role='user', **body):
        return self.store.mutate('save', {'id': cid, 'messages': [{
            'id': mid, 'role': role, 'text': content, 'status': 'complete',
            'at': self.now, 'source': 'test'}], **body})

    def begin(self, cid, operation='forget-a'):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return task_memory.begin_forget(db, cid, operation, task_memory.state(db, cid)['generation'])

    def finish(self, ref, result):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(db, ref, result)

    def test_scoped_forget_preserves_b_and_retains_manual_history(self):
        group = self.store.mutate('group', {'title': 'Shared'})['id']
        a, b, c = self.chat(group_id=group), self.chat(group_id=group), self.chat()
        attachment = {'name': 'private.txt', 'text': 'PRIVATE_ARCHIVE', 'at': self.now}
        self.save(a, 'a-old', 'PRIVATE_A', attachment=attachment, draft='draft A')
        self.save(b, 'b-old', 'KEEP_B', draft='draft B')
        self.store.mutate('profile', {'name': 'Keep profile', 'context': 'Unattributed profile'})
        a_before, b_before, c_before = self.store.get(a), self.store.get(b), self.store.get(c)
        self.store.mutate('context', {'group_id': group, 'text': 'PRIVATE_A', 'source_task_id': a,
                                     'source_message_id': 'a-old', 'memory_scope': a_before['memory_scope']})
        self.store.mutate('context', {'group_id': group, 'text': 'KEEP_B_NOTE', 'source_task_id': b,
                                     'memory_scope': b_before['memory_scope']})
        self.store.mutate('context', {'group_id': group, 'text': 'UNKNOWN_SHARED'})
        self.store.mutate('link', {'id': b, 'source_id': a})
        self.store.mutate('link', {'id': a, 'source_id': b})
        self.store.mutate('link', {'id': c, 'source_id': b})
        a_before, b_before, c_before = self.store.get(a), self.store.get(b), self.store.get(c)

        ref = self.begin(a)
        pending = self.store.get(a)
        self.assertTrue(pending['memory_forgetting'])
        for field in ('messages', 'context', 'links'):
            self.assertEqual(pending[field], [])
        self.assertIsNone(pending['attachment'])
        self.assertEqual(pending['history_count'], 1)
        self.assertNotIn('history_messages', pending)
        self.assertNotIn('review_context', pending)
        self.assertEqual([n['text'] for n in self.store.get(b)['context']], ['KEEP_B_NOTE'])
        self.assertEqual(self.store.get(b)['links'], [])

        result = self.store.forget_task(a, ref)
        self.assertEqual(result, self.store.forget_task(a, ref))
        self.assertTrue(result['requires_review'])
        self.assertEqual(result['counts']['messages_invalidated'], 1)
        self.assertEqual(result['counts']['link_snapshots_removed'], 2)
        self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertIn(a_before['connect_id'], result['old_connect_ids'])
        self.assertIn(b_before['connect_id'], result['old_connect_ids'])
        self.finish(ref, result)

        after, b_after = self.store.get(a), self.store.get(b)
        self.assertEqual(after['messages'], [])
        self.assertIsNone(after['attachment'])
        self.assertEqual(after['draft'], 'draft A')
        self.assertEqual(after['shared_id'], a_before['shared_id'])
        self.assertEqual(after['agent_profile'], a_before['agent_profile'])
        self.assertEqual(b_after['messages'], b_before['messages'])
        self.assertEqual(b_after['draft'], 'draft B')
        self.assertEqual(b_after['shared_id'], b_before['shared_id'])
        self.assertEqual([n['text'] for n in b_after['context']], ['KEEP_B_NOTE'])
        self.assertEqual(b_after['review_context_count'], 1)
        self.assertNotEqual(after['connect_id'], a_before['connect_id'])
        self.assertNotEqual(b_after['connect_id'], b_before['connect_id'])
        self.assertEqual(self.store.get(c)['connect_id'], c_before['connect_id'])
        self.assertEqual(self.store.get(c)['links'], c_before['links'])
        self.assertEqual(len(self.store.list()['conversations']), 3)
        history = self.store.get(a, include_history=True)
        self.assertEqual(history['history_messages'][0]['text'], 'PRIVATE_A')
        self.assertEqual(history['history_attachment']['text'], 'PRIVATE_ARCHIVE')
        self.assertEqual(history['review_context'][0]['text'], 'UNKNOWN_SHARED')
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?', (a,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT text FROM chat_attachments WHERE conversation_id=?', (a,)).fetchone()[0], 'PRIVATE_ARCHIVE')
        self.assertEqual(self.store.by_shared_id(a_before['shared_id'])['id'], a)

    def test_late_mutations_and_relink_rejected_across_restart(self):
        group = self.store.mutate('group', {'title': 'Shared'})['id']
        a, b = self.chat(group_id=group), self.chat(group_id=group)
        self.save(a, 'old', 'OLD_A')
        old_ref = self.store.get(a)['memory_scope']
        ref = self.begin(a)
        for scope in (None, old_ref, {'task_id': a, 'generation': ref['generation']}):
            with self.subTest(pending_scope=scope), self.assertRaises(ValueError):
                self.save(a, 'late', 'LATE_A', memory_scope=scope)
        with self.assertRaises(ValueError):
            self.store.mutate('link', {'id': b, 'source_id': a})
        with self.assertRaises(ValueError):
            self.store.mutate('delete', {'id': a})
        result = self.store.forget_task(a, ref)
        self.finish(ref, result)
        self.store.close()
        self.store = ChatStore(self.path, lambda: self.now)
        for action, body in (
            ('save', {'id': a, 'messages': []}),
            ('update', {'id': a, 'title': 'late', 'memory_scope': old_ref}),
            ('link', {'id': a, 'source_id': b, 'memory_scope': old_ref}),
            ('context', {'group_id': group, 'source_task_id': a, 'text': 'late', 'memory_scope': old_ref}),
            ('context', {'group_id': group, 'text': 'unattributed late'}),
        ):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.store.mutate(action, body)
        active = self.store.get(a)
        current = active['memory_scope']
        with self.assertRaises(ValueError):
            self.save(a, 'old', 'OLD_A', memory_scope=current, memory_context_id=active['context_id'])
        self.save(a, 'new', 'NEW_A', memory_scope=current, memory_context_id=active['context_id'])
        self.save(b, 'new-b', 'KEEP_B', memory_context_id=self.store.get(b)['context_id'])
        self.assertEqual([m['text'] for m in self.store.get(a)['messages']], ['NEW_A'])
        self.assertEqual(self.store.get(a)['history_count'], 1)
        self.store.mutate('link', {'id': b, 'source_id': a})
        self.assertEqual([m['text'] for m in self.store.get(b)['links'][0]['messages']], ['NEW_A'])
        self.assertEqual(self.store.forget_task(a, ref), result)

    def test_pin_requires_exact_current_message_and_task(self):
        group = self.store.mutate('group', {'title': 'Shared'})['id']
        a, b = self.chat(group_id=group), self.chat(group_id=group)
        self.save(a, 'a', 'Original')
        scope = self.store.get(a)['memory_scope']
        valid = {'group_id': group, 'source_task_id': a, 'source_message_id': 'a',
                 'text': 'Original', 'memory_scope': scope}
        with self.assertRaises(ValueError):
            self.store.mutate('context', {'group_id': group, 'text': 'Malformed', 'memory_scope': 'invalid'})
        for change in ({'text': 'Invented'}, {'source_task_id': b}, {'source_message_id': 'missing'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.mutate('context', valid | change)
        self.store.mutate('context', valid)
        note = self.store.get(b)['context'][0]
        self.assertEqual(note['origin_task_id'], a)
        self.assertEqual(note['origin_message_id'], 'a')

    def test_link_derived_messages_and_snapshots_stay_forgotten_without_changing_b_scope(self):
        a, b, c = self.chat(), self.chat(), self.chat()
        self.save(a, 'source-a', 'PRIVATE_A')
        self.save(b, 'direct-b', 'KEEP_B_USER')
        self.save(b, 'assistant-before-link', 'KEEP_B_ASSISTANT', role='assistant')
        self.store.mutate('link', {'id': b, 'source_id': a})
        linked = self.store.get(b)
        self.save(b, 'derived-b', 'DERIVED_PRIVATE_A', role='assistant',
                  memory_scope=linked['memory_scope'], memory_context_id=linked['context_id'])
        self.save(b, 'user-after-link', 'KEEP_B_USER_AFTER', memory_context_id=linked['context_id'])
        self.save(b, 'assistant-before-link', 'KEEP_B_ASSISTANT', role='assistant',
                  memory_context_id=linked['context_id'])
        self.store.mutate('unlink', {'id': b, 'source_id': a})
        unlinked = self.store.get(b)
        self.save(b, 'derived-from-history', 'DERIVED_AFTER_UNLINK', role='assistant',
                  memory_context_id=unlinked['context_id'])
        self.store.mutate('link', {'id': c, 'source_id': b})

        ref = self.begin(a)
        expected = ['assistant-before-link', 'direct-b', 'user-after-link']
        self.assertEqual([m['id'] for m in self.store.get(b)['messages']], expected)
        self.assertEqual([m['id'] for m in self.store.get(c)['links'][0]['messages']], expected)
        with self.assertRaises(ValueError):
            self.save(b, 'late-pending', 'LATE_PRIVATE_A', role='assistant',
                      memory_scope=unlinked['memory_scope'], memory_context_id=unlinked['context_id'])
        result = self.store.forget_task(a, ref)
        self.finish(ref, result)
        self.assertEqual(result['counts']['derived_messages_invalidated'], 2)
        self.assertEqual(result['counts']['derived_snapshots_invalidated'], 2)
        after = self.store.get(b)
        self.assertEqual(after['memory_scope'], unlinked['memory_scope'])
        self.assertNotEqual(after['context_id'], unlinked['context_id'])
        for context in (None, unlinked['context_id']):
            with self.subTest(context=context), self.assertRaises(ValueError):
                self.save(b, 'late-b', 'LATE_PRIVATE_A', role='assistant',
                          memory_scope=after['memory_scope'], memory_context_id=context)
        with self.assertRaises(ValueError):
            self.save(b, 'derived-b', 'RESURRECTED', role='assistant',
                      memory_scope=after['memory_scope'], memory_context_id=after['context_id'])
        self.save(b, 'fresh-b', 'FRESH_B', role='assistant', memory_context_id=after['context_id'])
        self.assertEqual(self.store.get(b)['history_count'], 2)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?', (b,)).fetchone()[0], 6)
            old = db.execute("SELECT memory_dependencies FROM chat_messages WHERE id='assistant-before-link'").fetchone()[0]
            self.assertEqual(json.loads(old), [unlinked['memory_scope']])
        self.store.close()
        self.store = ChatStore(self.path, lambda: self.now)
        with self.assertRaises(ValueError):
            self.save(b, 'late-restart', 'LATE', role='assistant', memory_context_id=unlinked['context_id'])
        self.assertNotIn('DERIVED_', json.dumps(self.store.get(b)))

    def test_group_note_causality_propagates_through_pinned_derived_message(self):
        group = self.store.mutate('group', {'title': 'Shared'})['id']
        a, b = self.chat(group_id=group), self.chat(group_id=group)
        self.save(b, 'direct', 'KEEP_B')
        self.save(b, 'before-note', 'KEEP_DIRECT_ASSISTANT', role='assistant')
        self.store.mutate('context', {'group_id': group, 'source_task_id': a, 'text': 'PRIVATE_A'})
        context = self.store.get(b)
        self.save(b, 'from-note', 'PRIVATE_DERIVED_B', role='assistant', memory_context_id=context['context_id'])
        self.store.mutate('context', {'group_id': group, 'source_task_id': b, 'source_message_id': 'from-note',
                                     'text': 'PRIVATE_DERIVED_B', 'memory_scope': context['memory_scope']})
        ref = self.begin(a)
        self.assertEqual([m['id'] for m in self.store.get(b)['messages']], ['before-note', 'direct'])
        self.assertEqual(self.store.get(b)['context'], [])
        result = self.store.forget_task(a, ref)
        self.finish(ref, result)
        self.assertEqual(result['counts']['notes_invalidated'], 2)
        self.assertEqual(result['counts']['derived_messages_invalidated'], 1)
        self.assertNotIn('history_messages', self.store.get(b))
        self.assertEqual(self.store.get(b, include_history=True)['history_messages'][0]['text'], 'PRIVATE_DERIVED_B')

    def test_migration_distinguishes_new_import_from_existing_forgotten_chat(self):
        body = {'messages': [{'id': 'legacy', 'role': 'user', 'text': 'PRIVATE_LEGACY',
                              'at': self.now, 'status': 'complete'}]}
        first = self.store.mutate('migrate', body)
        self.assertTrue(first['created'])
        ref = self.begin(first['id'])
        result = self.store.forget_task(first['id'], ref)
        self.finish(ref, result)
        second = self.store.mutate('migrate', body)
        self.assertFalse(second['created'])
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(self.store.get(first['id'])['messages'], [])

    def test_unattributed_legacy_assistant_is_reviewed_only_in_affected_chat(self):
        group = self.store.mutate('group', {'title': 'Shared'})['id']
        a, b, unrelated = self.chat(group_id=group), self.chat(group_id=group), self.chat(group_id=group)
        self.save(a, 'a', 'PRIVATE_A')
        self.save(b, 'b-user', 'KEEP_B_USER')
        self.save(b, 'modern-before-link', 'KEEP_B_ASSISTANT', role='assistant')
        self.store.mutate('context', {'group_id': group, 'source_task_id': unrelated, 'text': 'KEEP_UNRELATED_NOTE'})
        legacy = {'id': 'legacy-b', 'role': 'assistant', 'text': 'PRIVATE_LEGACY_CANARY', 'at': self.now, 'status': 'complete'}
        other = legacy | {'id': 'legacy-unrelated', 'text': 'KEEP_UNRELATED_LEGACY'}
        with self.store.db() as db:
            for cid,message in ((b,legacy),(unrelated,other)):
                db.execute('INSERT INTO chat_messages(id,conversation_id,at,payload) VALUES(?,?,?,?)',
                           (message['id'],cid,self.now,json.dumps(message)))
        self.store.mutate('link', {'id': b, 'source_id': a})
        untouched = self.store.get(unrelated)
        self.assertIn('PRIVATE_LEGACY_CANARY', json.dumps(self.store.get(b)))
        ref = self.begin(a)
        self.assertNotIn('PRIVATE_LEGACY_CANARY', json.dumps(self.store.get(b)))
        self.assertIn('KEEP_UNRELATED_LEGACY', json.dumps(self.store.get(unrelated)))
        result = self.store.forget_task(a, ref)
        self.finish(ref, result)
        self.assertEqual(result['counts']['legacy_messages_review'], 1)
        self.assertTrue(result['requires_review'])
        self.assertEqual(self.store.get(b)['review_message_count'], 1)
        self.assertEqual([m['id'] for m in self.store.get(b)['messages']], ['b-user','modern-before-link'])
        self.assertEqual(self.store.get(unrelated)['connect_id'], untouched['connect_id'])
        self.assertEqual(self.store.get(unrelated)['messages'], untouched['messages'])
        with self.store.db() as db:
            stored = db.execute("SELECT payload,memory_dependencies,requires_review FROM chat_messages WHERE id='legacy-b'").fetchone()
            self.assertEqual(stored['payload'], json.dumps(legacy))
            self.assertEqual(stored['memory_dependencies'], '[]')
            self.assertEqual(stored['requires_review'], 1)
        self.store.close()
        self.store = ChatStore(self.path, lambda: self.now)
        self.assertNotIn('PRIVATE_LEGACY_CANARY', json.dumps(self.store.get(b)))
        self.assertEqual(self.store.get(b, include_history=True)['history_messages'][0], legacy)

    def test_global_history_clear_rejects_old_context_without_forgetting_learning_scope(self):
        cid = self.chat()
        self.save(cid, 'before', 'PRIVATE')
        old = self.store.get(cid)
        self.store.mutate('forget', {})
        current = self.store.get(cid)
        self.assertEqual(current['memory_scope'], old['memory_scope'])
        self.assertNotEqual(current['context_id'], old['context_id'])
        for context in (None, old['context_id']):
            with self.subTest(context=context), self.assertRaises(ValueError):
                self.save(cid, 'before', 'PRIVATE', memory_context_id=context)
        self.save(cid, 'fresh', 'FRESH', memory_context_id=current['context_id'])
        self.assertEqual([m['text'] for m in self.store.get(cid)['messages']], ['FRESH'])

    def test_effect_receipts_are_preserved_and_only_old_a_projection_is_forgotten(self):
        a, b, c = self.chat(), self.chat(), self.chat()
        self.save(a, 'a-source', 'PRIVATE_A')
        self.store.mutate('link', {'id': c, 'source_id': a})
        executor = ActionExecutor(self.path, Path(self.temp.name) / 'artifacts')
        commands = CommandService(executor)
        try:
            old_a = commands.prepare('axx.system.telemetry', {}, conversation_id=a, command_mode='ask')
            commands.cancel(old_a['operation_id'])
            keep_b = commands.prepare('axx.system.telemetry', {}, conversation_id=b, command_mode='ask')
            commands.cancel(keep_b['operation_id'])
            old_c = commands.prepare('axx.system.telemetry', {}, conversation_id=c, command_mode='ask',
                                     memory_context_id=self.store.get(c)['context_id'])
            commands.cancel(old_c['operation_id'])
            with self.store.db() as db:
                raw = {r[0]: r[1] for r in db.execute('SELECT operation_id,result_json FROM command_runs')}
            ref = self.begin(a)
            result = self.store.forget_task(a, ref)
            self.finish(ref, result)
            new_a = commands.prepare('axx.system.telemetry', {}, conversation_id=a, command_mode='ask',
                                     memory_scope=self.store.get(a)['memory_scope'],
                                     memory_context_id=self.store.get(a)['context_id'])
            commands.cancel(new_a['operation_id'])
            new_c = commands.prepare('axx.system.telemetry', {}, conversation_id=c, command_mode='ask',
                                     memory_scope=self.store.get(c)['memory_scope'],
                                     memory_context_id=self.store.get(c)['context_id'])
            projected = {r['operation_id']: r for r in self.store.operations()}
            self.assertTrue(projected[old_a['operation_id']]['memory_forgotten'])
            self.assertNotIn('memory_forgotten', projected[keep_b['operation_id']])
            self.assertNotIn('memory_forgotten', projected[new_a['operation_id']])
            self.assertTrue(projected[old_c['operation_id']]['memory_forgotten'])
            self.assertNotIn('memory_forgotten', projected[new_c['operation_id']])
            with self.store.db() as db:
                for operation, payload in raw.items():
                    self.assertEqual(db.execute('SELECT result_json FROM command_runs WHERE operation_id=?', (operation,)).fetchone()[0], payload)
        finally:
            commands.close()
            executor.close()


if __name__ == '__main__':
    unittest.main()
