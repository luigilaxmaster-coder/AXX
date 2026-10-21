"""Identity and Preference Synchronization for Axx.
Ensures axx-studio-v2 (form, palette, dimensions, camera, panels) has a single clear authority.
Stores visual preferences in SQLite while keeping them completely decoupled
from temporary task states (thinking, countdown, errors).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
import sqlite3

LOG = logging.getLogger('axx.identity_sync')

class IdentityStore:
    """Manages persistent visual identity, preventing task state overwrites."""
    def __init__(self, db_path: str | Path = 'state.db'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS identity_preferences (
                    key TEXT PRIMARY KEY,
                    data_json TEXT,
                    version INTEGER DEFAULT 1,
                    updated_at TEXT
                )
            ''')

    def close(self):
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_studio_identity(self) -> dict | None:
        """Retrieves stored axx-studio-v2 preferences."""
        cur = self.db.execute('SELECT data_json FROM identity_preferences WHERE key="axx-studio-v2"')
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def save_studio_identity(self, preferences: dict) -> bool:
        """Saves axx-studio-v2 preferences, explicitly verifying that transient task states are rejected."""
        if not isinstance(preferences, dict):
            return False

        # Invariant: Transient animation states (e.g. countdown, error, thinking) must NEVER overwrite form
        transient_keys = {'temporary_state', 'task_animation', 'error_pulse', 'countdown_active'}
        def sanitize(value, depth=0):
            if depth > 16:
                raise ValueError('Preference nesting is too deep')
            if isinstance(value, dict):
                return {k: sanitize(v, depth + 1) for k, v in value.items() if k not in transient_keys}
            if isinstance(value, list):
                return [sanitize(item, depth + 1) for item in value]
            return value
        sanitized = sanitize(preferences)
        encoded = json.dumps(sanitized, allow_nan=False)
        if len(encoded.encode('utf-8')) > 256 * 1024:
            raise ValueError('Preferences exceed size limit')

        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.db:
            self.db.execute(
                '''INSERT INTO identity_preferences(key, data_json, updated_at)
                   VALUES('axx-studio-v2', ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                   data_json=excluded.data_json,
                   version=identity_preferences.version + 1,
                   updated_at=excluded.updated_at''',
                (encoded, now_iso)
            )
        return True
