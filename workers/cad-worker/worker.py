"""Standalone isolated CAD worker process for AXX Evolution 3.0 (PR-05).

Reads a declarative JSON GeometryTask request from stdin, generates verified STEP + GLB
files in output_dir, and writes the JSON receipt to stdout. Never executes arbitrary code.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.spatial.cad_contracts import execute_cad_geometry_task


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8')
        request = json.loads(raw)
        task = request.get('task') or {}
        if task.get('_simulate_hang_seconds'):
            time.sleep(float(task['_simulate_hang_seconds']))
        output_dir = request.get('output_dir')
        res = execute_cad_geometry_task(task, output_dir=output_dir)
        serializable = {
            'task_id': res['task_id'],
            'scene_document': res['scene_document'],
            'step_path': res['step_path'],
            'glb_path': res['glb_path'],
            'congruence': res['congruence'],
            'diagnostic_report': res['diagnostic_report'],
        }
        sys.stdout.write(json.dumps({'ok': True, 'result': serializable}, ensure_ascii=False))
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
