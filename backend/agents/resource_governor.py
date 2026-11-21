"""ResourceGovernor & CostLedger — Avatar/Voice Priority & Budget Enforcement (PR-19 / PERF-01 / PERF-02 / E2E-13).

Enforces Invariants:
- PERF-01 / E2E-13: User interaction, 3D avatar rendering (>= 45 FPS target), and real-time voice/dictation
  always take priority over heavy background tasks (CAD STEP/GLB generation, MP4 rendering, full AST indexing,
  background agent swarms). When voice is active or CPU/RAM/FPS thresholds are crossed, heavy tasks are queued.
- PERF-02: Tracks token and USD spend per run and per agent in SQLite ('cost_ledger'); exceeding budget
  pauses the run and notifies the user.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

RESOURCE_PROFILES: dict[str, dict[str, Any]] = {
    'Eco': {
        'max_cpu_percent': 65.0,
        'max_ram_percent': 75.0,
        'min_avatar_fps': 45.0,
        'max_parallel_heavy_jobs': 1,
    },
    'Balanceado': {
        'max_cpu_percent': 80.0,
        'max_ram_percent': 85.0,
        'min_avatar_fps': 45.0,
        'max_parallel_heavy_jobs': 2,
    },
    'Máximo': {
        'max_cpu_percent': 92.0,
        'max_ram_percent': 90.0,
        'min_avatar_fps': 35.0,
        'max_parallel_heavy_jobs': 4,
    },
}

HEAVY_BACKGROUND_JOBS = frozenset({
    'cad_step_export',
    'motion_mp4_render',
    'code_full_reindex',
    'lsp_background_scan',
    'splat_preview',
    'multiagent_background_batch',
})


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class ResourceGovernor:
    """Arbitrates CPU/RAM/GPU/FPS resources and enforces token/USD cost budgets (PERF-01, PERF-02, E2E-13)."""

    def __init__(
        self,
        db_path: str | Path = ':memory:',
        *,
        profile_name: str = 'Balanceado',
        clock=None,
    ):
        if profile_name not in RESOURCE_PROFILES:
            raise ValueError(f'Unknown resource profile: {profile_name!r}')
        self.db_path = str(db_path)
        self.profile_name = profile_name
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self.telemetry: dict[str, Any] = {
            'cpu_percent': 25.0,
            'ram_percent': 45.0,
            'gpu_vram_percent': 30.0,
            'avatar_fps': 60.0,
            'voice_active': False,
            'active_heavy_jobs': 0,
        }
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
                    CREATE TABLE IF NOT EXISTS cost_ledger (
                        entry_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL DEFAULT 0 CHECK(input_tokens >= 0),
                        output_tokens INTEGER NOT NULL DEFAULT 0 CHECK(output_tokens >= 0),
                        cost_usd REAL NOT NULL DEFAULT 0 CHECK(cost_usd >= 0),
                        created_at_ms INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_cost_ledger_run ON cost_ledger(run_id);
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def set_profile(self, profile_name: str) -> dict[str, Any]:
        if profile_name not in RESOURCE_PROFILES:
            raise ValueError(f'Unknown resource profile: {profile_name!r}')
        self.profile_name = profile_name
        return dict(RESOURCE_PROFILES[profile_name], profile_name=profile_name)

    def update_host_telemetry(
        self,
        *,
        cpu_percent: float | None = None,
        ram_percent: float | None = None,
        gpu_vram_percent: float | None = None,
        avatar_fps: float | None = None,
        voice_active: bool | None = None,
        active_heavy_jobs: int | None = None,
    ) -> dict[str, Any]:
        if cpu_percent is not None:
            self.telemetry['cpu_percent'] = float(cpu_percent)
        if ram_percent is not None:
            self.telemetry['ram_percent'] = float(ram_percent)
        if gpu_vram_percent is not None:
            self.telemetry['gpu_vram_percent'] = float(gpu_vram_percent)
        if avatar_fps is not None:
            self.telemetry['avatar_fps'] = float(avatar_fps)
        if voice_active is not None:
            self.telemetry['voice_active'] = bool(voice_active)
        if active_heavy_jobs is not None:
            self.telemetry['active_heavy_jobs'] = max(0, int(active_heavy_jobs))
        return dict(self.telemetry)

    def evaluate_job_admission(self, job_class: str) -> dict[str, Any]:
        """Decide whether a job can run immediately or must be queued to protect voice/avatar responsiveness (PERF-01 / E2E-13)."""
        limits = RESOURCE_PROFILES[self.profile_name]
        is_heavy = job_class in HEAVY_BACKGROUND_JOBS
        if not is_heavy:
            return {
                'job_class': job_class,
                'allowed': True,
                'decision': 'admitted_realtime',
                'profile': self.profile_name,
            }

        reasons: list[str] = []
        if self.telemetry['voice_active']:
            reasons.append('voice_or_dictation_active')
        if self.telemetry['avatar_fps'] < limits['min_avatar_fps']:
            reasons.append('avatar_fps_below_floor')
        if self.telemetry['cpu_percent'] >= limits['max_cpu_percent']:
            reasons.append('cpu_pressure_high')
        if self.telemetry['ram_percent'] >= limits['max_ram_percent']:
            reasons.append('ram_pressure_high')
        if self.telemetry['active_heavy_jobs'] >= limits['max_parallel_heavy_jobs']:
            reasons.append('max_parallel_heavy_jobs_reached')

        if reasons:
            return {
                'job_class': job_class,
                'allowed': False,
                'decision': 'queued_for_pressure',
                'reasons': reasons,
                'profile': self.profile_name,
                'avatar_protected': True,
                'voice_protected': True,
            }
        return {
            'job_class': job_class,
            'allowed': True,
            'decision': 'admitted_background',
            'reasons': [],
            'profile': self.profile_name,
        }

    def record_usage_and_check_budget(
        self,
        *,
        entry_id: str,
        run_id: str,
        agent_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        run_budget_usd: float,
    ) -> dict[str, Any]:
        """Record token/USD usage in cost_ledger and pause the run if run_budget_usd is exceeded (PERF-02)."""
        now = self.clock()
        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO cost_ledger
                        (entry_id, run_id, agent_id, provider, model, input_tokens, output_tokens, cost_usd, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        entry_id,
                        run_id,
                        agent_id,
                        provider,
                        model,
                        int(input_tokens),
                        int(output_tokens),
                        float(cost_usd),
                        now,
                    ),
                )
                row = db.execute(
                    'SELECT COALESCE(SUM(cost_usd), 0.0) AS total_usd, COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens FROM cost_ledger WHERE run_id=?',
                    (run_id,),
                ).fetchone()
                total_usd = round(float(row['total_usd']), 6)
                total_tokens = int(row['total_tokens'])

        exceeded = run_budget_usd > 0 and total_usd > run_budget_usd
        return {
            'run_id': run_id,
            'agent_id': agent_id,
            'total_cost_usd': total_usd,
            'total_tokens': total_tokens,
            'run_budget_usd': float(run_budget_usd),
            'budget_exceeded': exceeded,
            'decision': 'paused_budget_exceeded' if exceeded else 'within_budget',
            'user_notification': (
                f'Presupuesto de ejecución alcanzado ({total_usd:.4f} USD > {run_budget_usd:.4f} USD): ejecución en pausa.'
                if exceeded
                else None
            ),
        }
