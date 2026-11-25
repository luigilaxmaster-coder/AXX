"""Autonomous Scheduled Routines with Microphone/Host-Input Block and Import Pause Guard (PR-19 / E2E-07).

Enforces Invariants:
- E2E-07: Autonomous routines can never request or auto-activate 'microphone' or 'host_input'
  capabilities.
- Imported routines ALWAYS start paused (enabled=False, status='paused_on_import') until the user
  explicitly enables them.
- Any routine execution that proposes a workspace or external mutation pauses in 'awaiting_approval'
  and generates an approval card instead of mutating silently.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
FORBIDDEN_ROUTINE_CAPABILITIES = frozenset({'microphone', 'host_input', 'audio_capture', 'sendinput_physical'})


def _cron_field(text: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(','):
        step = 1
        if '/' in part:
            part, raw_step = part.split('/', 1)
            step = int(raw_step)
            if step < 1:
                raise ValueError('cron step must be positive')
        if part == '*':
            a, b = lo, hi
        elif '-' in part:
            a, b = (int(v) for v in part.split('-', 1))
        else:
            a = b = int(part)
        if a < lo or b > hi or a > b:
            raise ValueError('cron value out of range')
        values.update(range(a, b + 1, step))
    return values


def next_cron_ms(spec: str, now_ms: int) -> int | None:
    """Next local time matching a 5-field cron (minute hour day-of-month month day-of-week), after now.

    Vixie semantics: when both day fields are restricted, either one matching is enough."""
    fields = spec.split()
    if len(fields) != 5:
        return None
    try:
        minutes, hours = sorted(_cron_field(fields[0], 0, 59)), sorted(_cron_field(fields[1], 0, 23))
        doms, months = _cron_field(fields[2], 1, 31), _cron_field(fields[3], 1, 12)
        dows = {d % 7 for d in _cron_field(fields[4], 0, 7)}
    except ValueError:
        return None
    start = datetime.fromtimestamp(now_ms / 1000).replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = start.replace(hour=0, minute=0)
    either = fields[2] != '*' and fields[4] != '*'
    for _ in range(366 * 5):  # five years always contains a 29 February
        if day.month in months:
            dom_ok, dow_ok = day.day in doms, day.isoweekday() % 7 in dows
            if (dom_ok or dow_ok) if either else (dom_ok and dow_ok):
                for h in hours:
                    for m in minutes:
                        t = day.replace(hour=h, minute=m)
                        if t >= start:
                            return int(t.timestamp() * 1000)
        day += timedelta(days=1)
    return None


class RoutineSecurityError(PermissionError):
    """Raised when an autonomous routine requests forbidden capabilities like microphone or host_input (E2E-07)."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class AutonomousRoutineService:
    """SQLite-backed autonomous routine manager enforcing E2E-07 privacy and approval invariants."""

    def __init__(self, db_path: str | Path = ':memory:', *, clock=None, dispatcher=None, event_hub=None, orchestrator=None, governor=None):
        self.db_path = str(db_path)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.dispatcher = dispatcher
        self.event_hub = event_hub
        self.orchestrator = orchestrator
        self.governor = governor
        self._stop_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self.lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _connect(self):
        if self._persistent_conn is not None:
            return _NullClosing(self._persistent_conn)
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def _init_schema(self) -> None:
        with self.lock, self._connect() as db:
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS autonomous_routines (
                        routine_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        schedule_spec TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                        requires_approval INTEGER NOT NULL DEFAULT 1 CHECK(requires_approval IN (0, 1)),
                        capabilities_json TEXT NOT NULL,
                        last_run_at_ms INTEGER,
                        next_run_at_ms INTEGER,
                        status TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS routine_runs (
                        run_id TEXT PRIMARY KEY,
                        routine_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        result_summary TEXT NOT NULL DEFAULT '',
                        started_at_ms INTEGER NOT NULL,
                        finished_at_ms INTEGER
                    );
                    '''
                )
                cols = {r[1] for r in db.execute('PRAGMA table_info(autonomous_routines)')}
                for col_name, col_def in (('prompt_text', "TEXT NOT NULL DEFAULT ''"), ('max_retries', 'INTEGER NOT NULL DEFAULT 1'),
                                          ('retry_count', 'INTEGER NOT NULL DEFAULT 0'), ('budget_usd', 'REAL NOT NULL DEFAULT 0.5'),
                                          ('team_id', "TEXT NOT NULL DEFAULT ''")):
                    if col_name not in cols:
                        db.execute(f'ALTER TABLE autonomous_routines ADD COLUMN {col_name} {col_def}')

    def close(self) -> None:
        self.stop_scheduler()
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    @staticmethod
    def _compute_next_run_ms(schedule_spec: str, now_ms: int) -> int | None:
        spec = str(schedule_spec or '').strip().lower()
        m = re.fullmatch(r'every:(\d+)(ms|s|m|h)', spec)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            mult = {'ms': 1, 's': 1000, 'm': 60_000, 'h': 3_600_000}[unit]
            return now_ms + max(50, n * mult)
        if spec.startswith('at:'):
            try:
                return int(spec[3:])
            except ValueError:
                return None
        return next_cron_ms(spec, now_ms)

    def preview_schedule(self, schedule_spec: str, count: int = 3) -> list[int]:
        """The next run times the scheduler would use, so the editor shows exactly what will happen."""
        now, runs = self.clock(), []
        while len(runs) < count:
            nxt = self._compute_next_run_ms(schedule_spec, runs[-1] if runs else now)
            if nxt is None:
                if not runs:
                    raise ValueError(f'Programación no válida: {schedule_spec!r}')
                break
            runs.append(nxt)
            if str(schedule_spec).strip().lower().startswith('at:'):
                break
        return runs

    def register_routine(
        self,
        *,
        routine_id: str,
        agent_id: str,
        conversation_id: str,
        schedule_spec: str,
        requested_capabilities: list[str] | None = None,
        enabled: bool = True,
        requires_approval: bool = True,
        imported_from_package: bool = False,
        prompt_text: str = '',
        max_retries: int = 1,
        budget_usd: float = 0.5,
        team_id: str = '',
    ) -> dict[str, Any]:
        for field, val in (('routine_id', routine_id), ('agent_id', agent_id), ('conversation_id', conversation_id)):
            if not isinstance(val, str) or not ID_RE.fullmatch(val):
                raise ValueError(f'Invalid {field}: {val!r}')
        if team_id and not ID_RE.fullmatch(str(team_id)):
            raise ValueError(f'Invalid team_id: {team_id!r}')
        if self._compute_next_run_ms(schedule_spec, self.clock()) is None:
            raise ValueError(f'Programación no válida: {schedule_spec!r} (usa every:30m, at:<ms> o cron de 5 campos)')

        caps = [str(c).strip().lower() for c in (requested_capabilities or [])]
        forbidden = [c for c in caps if c in FORBIDDEN_ROUTINE_CAPABILITIES]
        if forbidden:
            raise RoutineSecurityError(
                f'Autonomous routine {routine_id!r} cannot request forbidden capabilities (E2E-07): {forbidden}'
            )

        if imported_from_package:
            effective_enabled = False
            status = 'paused_on_import'
            next_run = None
        else:
            effective_enabled = bool(enabled)
            status = 'scheduled' if effective_enabled else 'paused'
            next_run = self._compute_next_run_ms(schedule_spec, self.clock()) if effective_enabled else None

        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO autonomous_routines
                        (routine_id, agent_id, conversation_id, schedule_spec, enabled,
                         requires_approval, capabilities_json, next_run_at_ms, status, prompt_text, max_retries, budget_usd, team_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        routine_id,
                        agent_id,
                        conversation_id,
                        schedule_spec,
                        1 if effective_enabled else 0,
                        1 if requires_approval else 0,
                        json.dumps(caps),
                        next_run,
                        status,
                        str(prompt_text)[:4000],
                        max(0, min(int(max_retries), 5)),
                        max(0.0, float(budget_usd)),
                        str(team_id or ''),
                    ),
                )
        return self.get_routine(routine_id)

    def get_routine(self, routine_id: str) -> dict[str, Any]:
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT * FROM autonomous_routines WHERE routine_id=?',
                (routine_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Routine not found: {routine_id}')
            return self._row_to_dict(row)

    def list_routines(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            if conversation_id:
                rows = db.execute(
                    'SELECT * FROM autonomous_routines WHERE conversation_id=? ORDER BY routine_id',
                    (conversation_id,),
                ).fetchall()
            else:
                rows = db.execute('SELECT * FROM autonomous_routines ORDER BY routine_id').fetchall()
            return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        keys = set(row.keys())
        return {
            'routine_id': row['routine_id'],
            'agent_id': row['agent_id'],
            'conversation_id': row['conversation_id'],
            'schedule_spec': row['schedule_spec'],
            'enabled': bool(row['enabled']),
            'requires_approval': bool(row['requires_approval']),
            'capabilities': json.loads(row['capabilities_json']),
            'last_run_at_ms': row['last_run_at_ms'],
            'next_run_at_ms': row['next_run_at_ms'],
            'status': row['status'],
            'prompt_text': row['prompt_text'] if 'prompt_text' in keys else '',
            'max_retries': int(row['max_retries']) if 'max_retries' in keys else 1,
            'retry_count': int(row['retry_count']) if 'retry_count' in keys else 0,
            'budget_usd': float(row['budget_usd']) if 'budget_usd' in keys else 0.5,
            'team_id': row['team_id'] if 'team_id' in keys else '',
        }

    def list_runs(self, routine_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            if routine_id:
                rows = db.execute(
                    'SELECT * FROM routine_runs WHERE routine_id=? ORDER BY started_at_ms DESC LIMIT ?',
                    (routine_id, int(limit)),
                ).fetchall()
            else:
                rows = db.execute(
                    'SELECT * FROM routine_runs ORDER BY started_at_ms DESC LIMIT ?',
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]

    def trigger_routine(
        self,
        routine_id: str,
        *,
        proposes_mutation: bool = True,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Trigger a scheduled routine; pauses in awaiting_approval if it proposes any mutation (E2E-07)."""
        routine = self.get_routine(routine_id)
        if not routine['enabled']:
            return {
                'routine_id': routine_id,
                'executed': False,
                'status': routine['status'],
                'reason': 'routine_is_disabled_or_paused',
                'activated_microphone': False,
                'activated_host_input': False,
            }

        now = self.clock()
        if not approved and (proposes_mutation or routine['requires_approval']):
            next_status = 'awaiting_approval'
            approval_created = False
            if self.orchestrator is not None:
                op_id = f'rout-op-{routine_id}-{now}'
                self.orchestrator.request_human_approval(
                    conversation_id=routine['conversation_id'],
                    run_id=f'rout-run-{routine_id}-{now}',
                    task_id=f'rout-task-{routine_id}',
                    agent_id=routine['agent_id'],
                    operation_id=op_id,
                    tool_name='routine.execute',
                    risk_class='write_workspace',
                    parameters={'routine_id': routine_id, 'capabilities': routine['capabilities']},
                )
                approval_created = True
            with self.lock, self._connect() as db:
                with db:
                    db.execute(
                        'UPDATE autonomous_routines SET last_run_at_ms=?, status=? WHERE routine_id=?',
                        (now, next_status, routine_id),
                    )
            return {
                'routine_id': routine_id,
                'executed': False,
                'status': next_status,
                'approval_card_created': approval_created,
                'approval_required': True,
                'dispatcher_connected': self.dispatcher is not None,
                'activated_microphone': False,
                'activated_host_input': False,
            }

        if self.dispatcher is None:
            with self.lock, self._connect() as db:
                with db:
                    db.execute(
                        'UPDATE autonomous_routines SET last_run_at_ms=?, status=? WHERE routine_id=?',
                        (now, 'blocked_dispatcher_unavailable', routine_id),
                    )
            return {
                'routine_id': routine_id,
                'executed': False,
                'status': 'blocked_dispatcher_unavailable',
                'approval_card_created': False,
                'approval_required': False,
                'dispatcher_connected': False,
                'activated_microphone': False,
                'activated_host_input': False,
            }

        if self.governor is not None:
            adm = self.governor.evaluate_job_admission('multiagent_background_batch')
            if not adm.get('allowed', True):
                return {
                    'routine_id': routine_id,
                    'executed': False,
                    'status': 'queued_for_pressure',
                    'reasons': adm.get('reasons', []),
                    'dispatcher_connected': True,
                    'activated_microphone': False,
                    'activated_host_input': False,
                }

        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                current=db.execute('SELECT * FROM autonomous_routines WHERE routine_id=?',(routine_id,)).fetchone()
                if not current['enabled'] or current['status']!='scheduled':
                    db.execute('COMMIT')
                    return {'routine_id':routine_id,'executed':False,'status':current['status']}
                slot=current['next_run_at_ms'] if current['next_run_at_ms'] is not None else now
                run_id='r-'+hashlib.sha256(f'{routine_id}:{slot}'.encode()).hexdigest()[:32]
                if db.execute('SELECT 1 FROM routine_runs WHERE run_id=?',(run_id,)).fetchone():
                    db.execute('COMMIT')
                    return {'routine_id':routine_id,'run_id':run_id,'executed':False,'status':'already_recorded'}
                db.execute(
                    'INSERT INTO routine_runs (run_id, routine_id, agent_id, status, started_at_ms) VALUES (?, ?, ?, ?, ?)',
                    (run_id, routine_id, routine['agent_id'], 'running', now),
                )
                db.execute("UPDATE autonomous_routines SET status='running' WHERE routine_id=?",(routine_id,))
                db.execute('COMMIT')
            except Exception:
                if db.in_transaction: db.execute('ROLLBACK')
                raise
        try:
            dispatch_res = self.dispatcher(routine, run_id)
            summary = str((dispatch_res or {}).get('summary', 'ok'))[:1000]
            finished = self.clock()
            nxt = self._compute_next_run_ms(routine['schedule_spec'], finished)
            if routine['schedule_spec'].lower().startswith('at:'):
                nxt=None
            with self.lock, self._connect() as db:
                with db:
                    db.execute(
                        "UPDATE routine_runs SET status=?, result_summary=?, finished_at_ms=? WHERE run_id=? AND status='running'",
                        ('completed', summary, finished, run_id),
                    )
                    db.execute(
                        "UPDATE autonomous_routines SET last_run_at_ms=?, next_run_at_ms=?, retry_count=0, status=? WHERE routine_id=? AND status='running'",
                        (now, nxt, 'scheduled' if nxt is not None else 'completed', routine_id),
                    )
            if self.event_hub is not None:
                self.event_hub.publish_event(
                    conversation_id=routine['conversation_id'],
                    run_id=run_id,
                    agent_id=routine['agent_id'],
                    event_type='run.completed',
                    payload={'kind': 'routine', 'routine_id': routine_id, 'summary': summary},
                )
            return {
                'routine_id': routine_id,
                'run_id': run_id,
                'executed': True,
                'status': 'completed',
                'summary': summary,
                'next_run_at_ms': nxt,
                'approval_card_created': False,
                'approval_required': False,
                'dispatcher_connected': True,
                'activated_microphone': False,
                'activated_host_input': False,
            }
        except Exception as exc:
            finished = self.clock()
            retries = routine['retry_count'] + 1
            exhausted = retries > routine['max_retries']
            with self.lock, self._connect() as db:
                with db:
                    db.execute(
                        "UPDATE routine_runs SET status=?, result_summary=?, finished_at_ms=? WHERE run_id=? AND status='running'",
                        ('failed', str(exc)[:1000], finished, run_id),
                    )
                    db.execute(
                        "UPDATE autonomous_routines SET last_run_at_ms=?, retry_count=?, status=?, next_run_at_ms=? WHERE routine_id=? AND status='running'",
                        (now, retries, 'failed' if exhausted else 'scheduled', finished+min(60_000,5000*retries), routine_id),
                    )
            return {
                'routine_id': routine_id,
                'run_id': run_id,
                'executed': False,
                'status': 'failed' if exhausted else 'retry_pending',
                'error': str(exc),
                'dispatcher_connected': True,
                'activated_microphone': False,
                'activated_host_input': False,
            }

    def resolve_approval(self, routine_id: str, approved: bool) -> dict[str, Any]:
        """The owner's decision on a routine slot waiting for approval: run it once now, or skip to the next slot."""
        routine = self.get_routine(routine_id)
        if routine['status'] != 'awaiting_approval':
            return {'routine_id': routine_id, 'executed': False, 'status': routine['status'], 'reason': 'not_awaiting_approval'}
        nxt = None if routine['schedule_spec'].lower().startswith('at:') else self._compute_next_run_ms(routine['schedule_spec'], self.clock())
        with self.lock, self._connect() as db:
            with db:
                if approved:
                    db.execute("UPDATE autonomous_routines SET status='scheduled' WHERE routine_id=? AND status='awaiting_approval'", (routine_id,))
                else:
                    db.execute("UPDATE autonomous_routines SET status=?, next_run_at_ms=? WHERE routine_id=? AND status='awaiting_approval'",
                               ('scheduled' if nxt is not None else 'completed', nxt, routine_id))
        if not approved:
            return {'routine_id': routine_id, 'executed': False, 'status': self.get_routine(routine_id)['status'], 'reason': 'denied_by_owner'}
        return self.trigger_routine(routine_id, proposes_mutation=False, approved=True)

    def tick_due_routines(self, *, now_ms: int | None = None) -> list[dict[str, Any]]:
        """Evaluate all enabled scheduled routines whose next_run_at_ms <= now and trigger them."""
        now = self.clock() if now_ms is None else int(now_ms)
        due = [
            r for r in self.list_routines()
            if r['enabled'] and r['status'] == 'scheduled' and r.get('next_run_at_ms') is not None and int(r['next_run_at_ms']) <= now
        ]
        results = []
        for r in due:
            results.append(self.trigger_routine(r['routine_id'], proposes_mutation=bool(r['requires_approval'])))
        return results

    def pause_routine(self, routine_id: str) -> dict[str, Any]:
        self.get_routine(routine_id)
        with self.lock, self._connect() as db:
            with db:
                db.execute("UPDATE autonomous_routines SET enabled=0, status='paused' WHERE routine_id=?", (routine_id,))
        return self.get_routine(routine_id)

    def resume_routine(self, routine_id: str) -> dict[str, Any]:
        r = self.get_routine(routine_id)
        nxt = self._compute_next_run_ms(r['schedule_spec'], self.clock())
        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    "UPDATE autonomous_routines SET enabled=1, next_run_at_ms=?, retry_count=0, status='scheduled' WHERE routine_id=?",
                    (nxt, routine_id),
                )
        return self.get_routine(routine_id)

    def start_scheduler(self, poll_interval_sec: float = 2.0) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.wait(poll_interval_sec):
                try:
                    self.tick_due_routines()
                except Exception:
                    pass

        self._scheduler_thread = threading.Thread(target=_loop, name='axx-routine-scheduler', daemon=True)
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=1.5)
        self._scheduler_thread = None

    def cancel_routine(self, routine_id: str) -> dict[str, Any]:
        """Cancel and disable an autonomous routine, persisting state across restarts."""
        self.get_routine(routine_id)
        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    "UPDATE autonomous_routines SET enabled=0, status='cancelled' WHERE routine_id=?",
                    (routine_id,),
                )
        return self.get_routine(routine_id)

    def reconcile_on_startup(self, *, recover_running: bool = False) -> dict[str, Any]:
        """Reconcile persisted routines on service startup without auto-executing pending mutations."""
        if recover_running:
            with self.lock, self._connect() as db:
                with db:
                    db.execute("UPDATE autonomous_routines SET status='interrupted', enabled=0 WHERE status='running'")
                    db.execute("UPDATE routine_runs SET status='interrupted' WHERE status='running'")
        routines = self.list_routines()
        scheduled = [r['routine_id'] for r in routines if r['enabled'] and r['status'] == 'scheduled']
        awaiting = [r['routine_id'] for r in routines if r['status'] == 'awaiting_approval']
        cancelled = [r['routine_id'] for r in routines if r['status'] == 'cancelled']
        paused = [r['routine_id'] for r in routines if r['status'] in ('paused', 'paused_on_import')]
        return {
            'total': len(routines),
            'scheduled': scheduled,
            'awaiting_approval': awaiting,
            'cancelled': cancelled,
            'paused': paused,
        }
