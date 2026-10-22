import unittest
from backend.mobile.http_api import checked_appearance


class AppearanceTests(unittest.TestCase):
    def test_activity_preserves_real_state_and_rejects_invalid_payloads(self):
        value = {'settings':{'form':19},'studio':{},'camera':[0,0],'finish':'prism',
                 'activity':{'state':'thinking','moving':True}}
        self.assertEqual(checked_appearance(value), value)
        for activity in ({'state':'imagined','moving':True}, {'state':'idle','moving':'yes'}, None):
            with self.assertRaises(ValueError):
                checked_appearance({**value,'activity':activity})
        with self.assertRaises(ValueError):
            checked_appearance({**value,'unexpected':'value'})
