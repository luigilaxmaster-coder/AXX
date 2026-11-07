import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.telegram.config import GRANTS, account_lease, account_path, load_account, save_account, update_permissions, validate_account


def account():
    return {'api_id': 123, 'api_hash': 'a' * 32, 'session': 'private-session-string',
            'account_id': 111, 'owner_id': 222, 'enabled': False,
            'grants': {key: key == 'conversation' for key in GRANTS}}


class TelegramConfigTests(unittest.TestCase):
    def test_validation_rejects_invalid_ids_hash_and_permissions(self):
        for field, value in [('api_id', 0), ('api_id', True), ('api_hash', 'g' * 32),
                             ('owner_id', 111), ('session', ''), ('enabled', 1), ('grants', {})]:
            with self.subTest(field=field, value=value):
                invalid = account()
                invalid[field] = value
                with self.assertRaises(ValueError):
                    validate_account(invalid)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI required')
    def test_session_lease_excludes_second_owner_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            with account_lease(directory):
                with self.assertRaisesRegex(RuntimeError, '^TELEGRAM_SESSION_IN_USE$'):
                    with account_lease(directory):
                        self.fail('Second lease was acquired')
            with account_lease(directory):
                pass

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI required')
    def test_permissions_can_be_revoked_while_session_is_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            initial = account()
            initial['enabled'] = True
            save_account(initial, directory)
            with account_lease(directory):
                grants = {key: False for key in GRANTS}
                update_permissions(False, grants, directory)
            updated = load_account(directory)
            self.assertFalse(updated['enabled'])
            self.assertEqual(updated['grants'], grants)
            self.assertEqual(updated['session'], initial['session'])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI required')
    def test_encrypted_round_trip_and_no_overwrite_on_error(self):
        with tempfile.TemporaryDirectory() as directory:
            save_account(account(), directory)
            target = account_path(directory)
            previous = target.read_bytes()
            self.assertNotIn(b'private-session-string', previous)
            self.assertNotIn(b'a' * 32, previous)
            self.assertEqual(load_account(directory), account())
            with self.assertRaises(FileExistsError):
                save_account(account(), directory, create_only=True)
            self.assertEqual(target.read_bytes(), previous)
            invalid = account()
            invalid['owner_id'] = invalid['account_id']
            with self.assertRaises(ValueError):
                save_account(invalid, directory)
            self.assertEqual(target.read_bytes(), previous)
            with patch('backend.telegram.config.os.replace', side_effect=OSError('failed')):
                with self.assertRaises(OSError):
                    save_account(account(), directory)
            self.assertEqual(target.read_bytes(), previous)
            self.assertEqual({p.name for p in Path(directory, 'telegram').iterdir()}, {target.name, 'config.lock'})


if __name__ == '__main__':
    unittest.main()
