"""PC-issued, one-use Telegram Mini App pairing; no credentials stored here."""
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager

from backend.mobile.pairing_qr import pairing_qr_base64
from backend.telegram.config import account_path


class PairingStore:
    def __init__(self, data_dir=None):
        self.path = account_path(data_dir).parent / 'pairing.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS pending (token_hash TEXT PRIMARY KEY, account INTEGER NOT NULL, owner INTEGER NOT NULL, epoch TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS bindings (id TEXT PRIMARY KEY, secret_hash TEXT NOT NULL UNIQUE, account INTEGER NOT NULL, owner INTEGER NOT NULL, epoch TEXT NOT NULL, created REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _identity(account):
        if (not isinstance(account, dict) or account.get('enabled') is not True or type(account.get('account_id')) is not int
                or type(account.get('owner_id')) is not int or account['account_id'] <= 0 or account['owner_id'] <= 0
                or account['account_id'] == account['owner_id'] or not isinstance(account.get('session'), str) or not account['session']):
            raise ValueError('Account not authorized')
        return account['account_id'], account['owner_id'], hashlib.sha256(account['session'].encode()).hexdigest()

    def create_pairing(self, account, bot_username):
        account_id, owner, epoch = self._identity(account)
        if not isinstance(bot_username, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{4,31}', bot_username):
            raise ValueError('Invalid verified bot username')
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = time.time() + 120
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM pending WHERE expires<=?', (time.time(),))
            if db.execute('SELECT count(*) FROM pending').fetchone()[0] >= 120:
                raise ValueError('Too many pending pairings')
            db.execute('INSERT INTO pending VALUES(?,?,?,?,?)', (digest, account_id, owner, epoch, expires))
        url = 'https://t.me/' + bot_username + '?start=axx_' + token
        return {'url': url, 'qr_svg_base64': pairing_qr_base64(url), 'expires_at': expires}

    def pending(self, account, start_param):
        account_id, owner, epoch = self._identity(account)
        if not isinstance(start_param, str) or not re.fullmatch('axx_[A-Za-z0-9_-]{43}', start_param):
            return False
        token_hash = hashlib.sha256(start_param[4:].encode()).hexdigest()
        with self._db() as db:
            return db.execute('SELECT 1 FROM pending WHERE token_hash=? AND account=? AND owner=? AND epoch=? AND expires>?',
                              (token_hash, account_id, owner, epoch, time.time())).fetchone() is not None

    def consume(self, account, start_param):
        account_id, owner, epoch = self._identity(account)
        if not isinstance(start_param, str) or not re.fullmatch('axx_[A-Za-z0-9_-]{43}', start_param):
            raise ValueError('Pairing required')
        token_hash = hashlib.sha256(start_param[4:].encode()).hexdigest()
        secret, binding = secrets.token_urlsafe(32), str(uuid.uuid4())
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        now = time.time()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT account,owner,epoch,expires FROM pending WHERE token_hash=?', (token_hash,)).fetchone()
            if not row or row[0] != account_id or row[1] != owner or row[2] != epoch or row[3] <= now:
                raise ValueError('Pairing required')
            db.execute('DELETE FROM pending WHERE token_hash=?', (token_hash,))
            db.execute('INSERT INTO bindings VALUES(?,?,?,?,?,?,0)', (binding, secret_hash, account_id, owner, epoch, now))
        return binding, secret

    def check(self, account, secret, binding_id=None):
        account_id, owner, epoch = self._identity(account)
        if not isinstance(secret, str) or not re.fullmatch('[A-Za-z0-9_-]{43}', secret):
            return None
        digest = hashlib.sha256(secret.encode()).hexdigest()
        with self._db() as db:
            row = db.execute('SELECT id FROM bindings WHERE secret_hash=? AND account=? AND owner=? AND epoch=? AND revoked=0',
                             (digest, account_id, owner, epoch)).fetchone()
        return row[0] if row and (binding_id is None or row[0] == binding_id) else None

    def status(self, account):
        account_id, owner, epoch = self._identity(account)
        with self._db() as db:
            pending = [{'expires_at': row[0]} for row in db.execute('SELECT expires FROM pending WHERE account=? AND owner=? AND epoch=? AND expires>? ORDER BY expires', (account_id, owner, epoch, time.time()))]
            bindings = [{'id': row[0], 'created_at': row[1]} for row in db.execute('SELECT id,created FROM bindings WHERE account=? AND owner=? AND epoch=? AND revoked=0 ORDER BY created', (account_id, owner, epoch))]
        return {'pending': pending, 'bindings': bindings}

    def revoke(self, account, binding_id):
        account_id, owner, epoch = self._identity(account)
        if not isinstance(binding_id, str) or str(uuid.UUID(binding_id)) != binding_id:
            raise ValueError('Invalid binding')
        with self._db() as db:
            return bool(db.execute('UPDATE bindings SET revoked=1 WHERE id=? AND account=? AND owner=? AND epoch=? AND revoked=0', (binding_id, account_id, owner, epoch)).rowcount)

    def revoke_all(self, account):
        account_id, owner, epoch = self._identity(account)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM pending WHERE account=? AND owner=? AND epoch=?', (account_id, owner, epoch))
            return db.execute('UPDATE bindings SET revoked=1 WHERE account=? AND owner=? AND epoch=? AND revoked=0', (account_id, owner, epoch)).rowcount
