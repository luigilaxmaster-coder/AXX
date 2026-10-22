import tempfile
import unittest
from pathlib import Path
from backend.mobile.shared_state import SharedState


class SharedStateTests(unittest.TestCase):
    def test_message_import_is_idempotent_and_snapshot_cursor_is_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SharedState(Path(tmp) / 'state.db')
            message = {'id':'desktop-1', 'role':'user', 'text':'Hola', 'at':100, 'status':'sent'}
            store.merge_messages([message], 'desktop')
            snapshot = store.snapshot()
            store.merge_messages([message], 'desktop')
            self.assertEqual(store.snapshot(), snapshot)
            store.merge_messages([{'id':'phone-1','role':'assistant','text':'Respuesta','at':101}], 'mobile')
            events = store.events(snapshot['cursor'])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['data']['id'], 'phone-1')
            self.assertEqual(len(store.snapshot()['messages']), 2)

    def test_conflicting_message_id_never_overwrites_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SharedState(Path(tmp) / 'state.db')
            store.merge_messages([{'id':'one','role':'user','text':'original','at':1}], 'desktop')
            with self.assertRaises(ValueError):
                store.merge_messages([{'id':'one','role':'user','text':'changed','at':1}], 'mobile')
            self.assertEqual(store.snapshot()['messages'][0]['text'], 'original')

    def test_new_conversation_keeps_old_history_without_reopening_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=SharedState(Path(tmp)/'state.db')
            store.merge_messages([{'id':'old','role':'user','text':'Original','at':1}], 'desktop', 'first', activate=True)
            store.merge_messages([], 'desktop', 'second', activate=True)
            self.assertEqual(store.snapshot()['messages'], [])
            self.assertEqual(store.snapshot('first')['messages'][0]['text'], 'Original')
