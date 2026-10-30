import concurrent.futures
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit

from backend.telegram.pairing import PairingStore


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PairingStore(self.temp.name)
        self.account = {'account_id': 10, 'owner_id': 20, 'enabled': True, 'session':'fixture'}

    def issue(self):
        data = self.store.create_pairing(self.account, 'ExampleBot')
        return data, parse_qs(urlsplit(data['url']).query)['start'][0]

    def test_one_use_and_only_hashes_persisted(self):
        data, start = self.issue()
        self.assertLessEqual(len(start), 64)
        self.assertTrue(data['qr_svg_base64'])
        binding, secret = self.store.consume(self.account, start)
        self.assertEqual(self.store.check(self.account, secret), binding)
        self.assertNotIn(start[4:].encode(), self.store.path.read_bytes())
        self.assertNotIn(secret.encode(), self.store.path.read_bytes())
        with self.assertRaises(ValueError):
            self.store.consume(self.account, start)

    def test_race_allows_one_binding_only(self):
        _, start = self.issue()
        def consume():
            try:
                return self.store.consume(self.account, start)
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: consume(), range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_expired_relinked_and_revoked_fail_closed(self):
        _, start = self.issue()
        with self.store._db() as db:
            db.execute('UPDATE pending SET expires=?', (time.time()-1,))
        with self.assertRaises(ValueError):
            self.store.consume(self.account, start)
        _, start = self.issue()
        other = {**self.account, 'owner_id': 21}
        with self.assertRaises(ValueError):
            self.store.consume(other, start)
        binding, secret = self.store.consume(self.account, start)
        self.assertIsNone(self.store.check(other, secret))
        self.assertIsNone(self.store.check({**self.account, 'session':'different'}, secret))
        self.assertTrue(self.store.revoke(self.account, binding))
        self.assertIsNone(self.store.check(self.account, secret))
        _, start = self.issue()
        self.store.revoke_all(self.account)
        with self.assertRaises(ValueError):
            self.store.consume(self.account, start)

    def test_status_has_no_secrets_and_disabled_refused(self):
        _, start = self.issue()
        self.assertNotIn(start, str(self.store.status(self.account)))
        with self.assertRaises(ValueError):
            self.store.create_pairing({**self.account, 'enabled':False}, 'ExampleBot')


if __name__ == '__main__':
    unittest.main()
