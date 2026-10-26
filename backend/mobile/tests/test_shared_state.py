import tempfile
import time
import unittest
from pathlib import Path
from backend.mobile.shared_state import SharedState


class SharedStateTests(unittest.TestCase):
    def setUp(self):
        self.now = int(time.time() * 1000)

    def test_message_import_is_idempotent_and_snapshot_cursor_is_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SharedState(Path(tmp) / 'state.db')
            message = {'id':'desktop-1', 'role':'user', 'text':'Hola', 'at':self.now, 'status':'sent'}
            store.merge_messages([message], 'desktop')
            snapshot = store.snapshot()
            store.merge_messages([message], 'desktop')
            self.assertEqual(store.snapshot(), snapshot)
            store.merge_messages([{'id':'phone-1','role':'assistant','text':'Respuesta','at':self.now+1}], 'mobile')
            events = store.events(snapshot['cursor'])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['data']['id'], 'phone-1')
            self.assertEqual(len(store.snapshot()['messages']), 2)

    def test_conflicting_message_id_never_overwrites_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SharedState(Path(tmp) / 'state.db')
            store.merge_messages([{'id':'one','role':'user','text':'original','at':self.now}], 'desktop')
            with self.assertRaises(ValueError):
                store.merge_messages([{'id':'one','role':'user','text':'changed','at':self.now}], 'mobile')
            self.assertEqual(store.snapshot()['messages'][0]['text'], 'original')

    def test_new_conversation_keeps_old_history_without_reopening_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=SharedState(Path(tmp)/'state.db')
            store.merge_messages([{'id':'old','role':'user','text':'Original','at':self.now}], 'desktop', 'first', activate=True)
            store.merge_messages([], 'desktop', 'second', activate=True)
            self.assertEqual(store.snapshot()['messages'], [])
            self.assertEqual(store.snapshot('first')['messages'][0]['text'], 'Original')

    def test_expired_messages_are_not_imported_or_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SharedState(Path(tmp) / 'state.db')
            store.merge_messages([{'id':'expired','role':'user','text':'Old','at':self.now-91*86400000}], 'desktop')
            self.assertEqual(store.snapshot()['messages'], [])
            self.assertEqual(store.events(0), [])
