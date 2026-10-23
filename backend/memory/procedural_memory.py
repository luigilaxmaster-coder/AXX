"""Axx Procedural Memory Engine.
Stores, retrieves, executes, and promotes verified procedural recipes.
Allows Axx to execute multi-step tool procedures deterministically with ZERO model calls on repeat runs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from pathlib import Path
import platform
import sqlite3
import sys
import time
import uuid

from backend.actions.executor import ActionExecutor
from backend.actions.tools import get_tool
from .ai_memory_adapter import AiMemoryAdapter

LOG = logging.getLogger('axx.procedural_memory')

def get_current_env_fingerprint() -> str:
    """Returns fingerprint of host OS and Python environment."""
    info = f"{platform.system()}-{platform.release()}-{platform.machine()}-py{platform.python_version()}"
    return hashlib.sha256(info.encode('utf-8')).hexdigest()[:16]


def get_action_env_fingerprint(command_ids=()) -> str:
    """Bind learned action records to the exact registered adapter versions they use."""
    ids = sorted(set(command_ids))
    if not ids:
        return get_current_env_fingerprint()
    versions = {}
    for command_id in ids:
        if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128:
            raise ValueError('Invalid command id in environment fingerprint')
        try:
            from backend.commands import ADAPTERS
            from backend.actions.tools import get_tool
            adapter = ADAPTERS[command_id]
            tool = get_tool(adapter['tool'])
            if tool is None:
                raise ValueError
            versions[command_id] = {'tool_version': tool.version, 'parameters': adapter['parameters']}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Unknown adapter in environment fingerprint: {command_id}') from exc
    payload = json.dumps({'host': get_current_env_fingerprint(), 'adapters': versions}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]

class Recipe:
    def __init__(
        self,
        id: str,
        intent_key: str,
        version: int,
        status: str,
        env_fingerprint: str,
        schema: dict,
        steps: list[dict],
        preconditions: list[str],
        postconditions: list[str],
        verified_at: str | None = None
    ):
        self.id = id
        self.intent_key = intent_key
        self.version = version
        self.status = status  # 'candidate' | 'verified' | 'quarantined' | 'deprecated'
        self.env_fingerprint = env_fingerprint
        self.schema = schema
        self.steps = steps
        self.preconditions = preconditions
        self.postconditions = postconditions
        self.verified_at = verified_at

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'intent_key': self.intent_key,
            'version': self.version,
            'status': self.status,
            'env_fingerprint': self.env_fingerprint,
            'schema': self.schema,
            'steps': self.steps,
            'preconditions': self.preconditions,
            'postconditions': self.postconditions,
            'verified_at': self.verified_at
        }

class ProceduralMemory:
    """Persistent procedural memory repository backed by SQLite and ai-memory."""
    def __init__(self, db_path: str | Path = 'state.db', ai_memory: AiMemoryAdapter | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        # SQLite is the default authority. An unrelated MCP listener is never trusted
        # or contacted merely because it happens to occupy a localhost port.
        self.ai_memory = ai_memory
        try:
            self._init_schema()
        except Exception:
            self.db.close()
            raise

    def _init_schema(self):
        with self.db:
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS recipes (
                    id TEXT PRIMARY KEY,
                    intent_key TEXT,
                    version INTEGER,
                    status TEXT,
                    env_fingerprint TEXT,
                    schema_json TEXT,
                    steps_json TEXT,
                    preconditions_json TEXT,
                    postconditions_json TEXT,
                    verified_at TEXT
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS recipe_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipe_id TEXT,
                    recipe_version INTEGER,
                    operation_id TEXT UNIQUE,
                    started_at TEXT,
                    ended_at TEXT,
                    outcome TEXT,
                    duration_ms REAL,
                    evidence_json TEXT
                )
            ''')
            columns = {row[1] for row in self.db.execute('PRAGMA table_info(recipe_attempts)')}
            if 'result_json' not in columns:
                self.db.execute('ALTER TABLE recipe_attempts ADD COLUMN result_json TEXT')
            self.db.execute("UPDATE recipe_attempts SET outcome='unknown' WHERE outcome='running'")
            self.db.execute('CREATE TABLE IF NOT EXISTS recipe_versions (recipe_id TEXT,version INTEGER,recipe_json TEXT,PRIMARY KEY(recipe_id,version))')

    def close(self):
        if hasattr(self, 'db') and self.db:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
        if self.ai_memory:
            self.ai_memory.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def register_recipe(
        self,
        id: str,
        intent_key: str,
        steps: list[dict],
        schema: dict,
        preconditions: list[str] | None = None,
        postconditions: list[str] | None = None,
        status: str = 'verified',
        env_fingerprint: str | None = None
    ) -> Recipe:
        """Registers a procedural recipe in SQLite and synchronizes to ai-memory."""
        if not isinstance(id, str) or not 1 <= len(id) <= 128 or not isinstance(intent_key, str) or not 1 <= len(intent_key) <= 128:
            raise ValueError('Recipe id and intent_key must be non-empty strings within 128 characters')
        if status not in ('candidate', 'verified', 'quarantined', 'deprecated') or not isinstance(schema, dict):
            raise ValueError('Invalid recipe status or schema')
        if not isinstance(steps, list) or len(steps) > 32:
            raise ValueError('Recipe steps must be a list within 32 steps')
        for step in steps:
            if not isinstance(step, dict) or not get_tool(step.get('tool')) or not isinstance(step.get('args'), dict):
                raise ValueError('Recipe must reference registered tools and object arguments')
        fp = env_fingerprint or get_current_env_fingerprint()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        pre = preconditions or []
        post = postconditions or []

        prior = self.db.execute('SELECT version FROM recipes WHERE id=?', (id,)).fetchone()
        recipe = Recipe(
            id=id,
            intent_key=intent_key,
            version=prior[0] + 1 if prior else 1,
            status=status,
            env_fingerprint=fp,
            schema=schema,
            steps=steps,
            preconditions=pre,
            postconditions=post,
            verified_at=now_iso if status == 'verified' else None
        )

        with self.db:
            self.db.execute('INSERT OR IGNORE INTO recipe_versions(recipe_id,version,recipe_json) VALUES(?,?,?)',
                            (recipe.id,recipe.version,json.dumps(recipe.to_dict())))
            self.db.execute(
                '''INSERT INTO recipes(id, intent_key, version, status, env_fingerprint, schema_json, steps_json, preconditions_json, postconditions_json, verified_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                   intent_key=excluded.intent_key,
                   version=excluded.version,
                   status=excluded.status,
                   env_fingerprint=excluded.env_fingerprint,
                   schema_json=excluded.schema_json,
                   steps_json=excluded.steps_json,
                   preconditions_json=excluded.preconditions_json,
                   postconditions_json=excluded.postconditions_json,
                   verified_at=excluded.verified_at''',
                (
                    recipe.id,
                    recipe.intent_key,
                    recipe.version,
                    recipe.status,
                    recipe.env_fingerprint,
                    json.dumps(recipe.schema),
                    json.dumps(recipe.steps),
                    json.dumps(recipe.preconditions),
                    json.dumps(recipe.postconditions),
                    recipe.verified_at
                )
            )

        # Sync to ai-memory if available
        markdown_body = f"""# Recipe: {recipe.id}
- **Intent Key:** {recipe.intent_key}
- **Status:** {recipe.status}
- **Environment:** {recipe.env_fingerprint}
- **Steps:** {len(recipe.steps)}
- **Verified:** {recipe.verified_at}
"""
        # A complete data record can be read back after daemon restart. It is
        # historical evidence, never an instruction or an execution authority.
        memory_record = recipe.to_dict()
        # ai-memory 3.1.1 conservatively scrubs JSON fields ending in _key.
        # This harmless identifier uses an explicit transport alias; genuine
        # secret scrubbing is still honored by strict readback verification.
        memory_record['intent'] = memory_record.pop('intent_key')
        markdown_body += '\n```json\n' + json.dumps({'axx_recipe': memory_record},
            ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n```\n'
        if self.ai_memory:
            self.ai_memory.write_recipe_page(recipe.id, markdown_body)

        return recipe

    def find_recipe(self, intent_key: str, env_fingerprint: str | None = None) -> Recipe | None:
        """Retrieves a verified recipe matching intent and environment."""
        if not isinstance(intent_key, str):
            raise ValueError('intent_key must be a string')
        fp = env_fingerprint or get_current_env_fingerprint()
        cur = self.db.execute(
            '''SELECT id, intent_key, version, status, env_fingerprint, schema_json, steps_json, preconditions_json, postconditions_json, verified_at
               FROM recipes
               WHERE intent_key=? AND status='verified' AND (env_fingerprint=? OR env_fingerprint='*')
               ORDER BY version DESC LIMIT 1''',
            (intent_key, fp)
        )
        row = cur.fetchone()
        if not row:
            return None

        return Recipe(
            id=row[0],
            intent_key=row[1],
            version=row[2],
            status=row[3],
            env_fingerprint=row[4],
            schema=json.loads(row[5]),
            steps=json.loads(row[6]),
            preconditions=json.loads(row[7]),
            postconditions=json.loads(row[8]),
            verified_at=row[9]
        )

    def list_recipes(self) -> list[dict]:
        rows = self.db.execute('SELECT id,intent_key,version,status,env_fingerprint,verified_at FROM recipes ORDER BY intent_key').fetchall()
        return [dict(zip(('id','intent_key','version','status','env_fingerprint','verified_at'), row)) for row in rows]

    def execute_recipe(self, recipe: Recipe, inputs: dict, executor: ActionExecutor, operation_id: str | None = None) -> dict:
        """Executes recipe steps deterministically, verifying postconditions and recording evidence."""
        if recipe.status != 'verified' or recipe.env_fingerprint not in ('*', get_current_env_fingerprint()):
            raise ValueError('Recipe is not verified for the current environment')
        if not recipe.steps or not isinstance(inputs, dict):
            raise ValueError('Recipe requires steps and object inputs')
        if set(inputs) - set(recipe.schema):
            raise ValueError('Unknown recipe input')
        inputs_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':'),
                                               allow_nan=False).encode('utf-8')).hexdigest()
        for key, rule in recipe.schema.items():
            if not isinstance(rule, dict):
                raise ValueError('Invalid recipe input schema')
            if rule.get('required') and key not in inputs:
                raise ValueError(f'Missing recipe input: {key}')
            if key in inputs and rule.get('type') == 'string' and not isinstance(inputs[key], str):
                raise ValueError(f'Recipe input must be string: {key}')
        op_id = operation_id or str(uuid.uuid4())
        if not isinstance(op_id, str) or not 1 <= len(op_id) <= 128:
            raise ValueError('Invalid operation_id')
        prior = self.db.execute('SELECT recipe_id,recipe_version,outcome,result_json FROM recipe_attempts WHERE operation_id=?', (op_id,)).fetchone()
        if prior:
            if prior[0] != recipe.id or prior[1] != recipe.version:
                raise ValueError('operation_id already belongs to a different recipe')
            if prior[3]:
                previous_result = json.loads(prior[3])
                if previous_result.get('inputs_sha256') != inputs_hash:
                    raise ValueError('operation_id already belongs to different inputs or cannot be safely reconciled')
                return dict(previous_result, replayed=True)
            return {'recipe_id': recipe.id, 'operation_id': op_id, 'outcome': 'unknown',
                    'model_calls_used': 0, 'error': 'Prior effect requires reconciliation; automatic retry blocked'}
        start_time = time.monotonic()
        start_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.db:
            self.db.execute('INSERT INTO recipe_attempts(recipe_id,recipe_version,operation_id,started_at,outcome) VALUES(?,?,?,?,?)',
                            (recipe.id,recipe.version,op_id,start_iso,'running'))
        step_results = []
        overall_success = True
        error_msg = None
        evidence_collected = {}

        for step_index, step in enumerate(recipe.steps):
            tool_name = step.get('tool')
            # Interpolate step parameters with inputs
            arg_template = step.get('args', {})
            step_args = {}
            for k, v in arg_template.items():
                if isinstance(v, str) and v.startswith('$inputs.'):
                    input_key = v.split('$inputs.', 1)[1]
                    step_args[k] = inputs.get(input_key)
                else:
                    step_args[k] = v

            try:
                res = executor.execute_action(tool_name, step_args, operation_id=f'{op_id[:90]}-step-{step_index}')
            except Exception as exc:
                res = {'state': 'failed', 'error': str(exc)}
            step_results.append(res)
            if res.get('evidence'):
                evidence_collected.update(res['evidence'])

            if res['state'] != 'succeeded':
                overall_success = False
                error_msg = f"Step with tool '{tool_name}' failed: {res.get('error')}"
                break

        end_time = time.monotonic()
        end_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        duration_ms = (end_time - start_time) * 1000.0

        outcome = 'succeeded' if overall_success else 'cancelled' if step_results and step_results[-1].get('state') == 'cancelled' else 'failed'

        # Record attempt
        with self.db:
            self.db.execute(
                '''UPDATE recipe_attempts SET ended_at=?,outcome=?,duration_ms=?,evidence_json=? WHERE operation_id=?''',
                (
                    end_iso,
                    outcome,
                    duration_ms,
                    json.dumps(evidence_collected),
                    op_id
                )
            )

        result = {
            'recipe_id': recipe.id,
            'inputs_sha256': inputs_hash,
            'version': recipe.version,
            'operation_id': op_id,
            'outcome': outcome,
            'duration_ms': round(duration_ms, 2),
            'model_calls_used': 0,  # Reusing recipe requires ZERO LLM calls!
            'model_calls_source': 'deterministic_no_model_path',
            'error': error_msg,
            'steps_executed': len(step_results),
            'evidence': evidence_collected
        }
        with self.db:
            self.db.execute('UPDATE recipe_attempts SET result_json=? WHERE operation_id=?', (json.dumps(result),op_id))
            if outcome == 'failed':
                self.db.execute("UPDATE recipes SET status='quarantined' WHERE id=?", (recipe.id,))
        return result
