"""Per-connection, per-model capability table with three honest levels.

    verificado     the aptitude test or a real call proved it
    declarado      the connection or the provider says so (configuration, Ollama /api/show)
    no_soportado   a real test failed

Nothing here is ever inferred from a model name. A capability with no entry has no data ('sin_datos').
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

CAPABILITIES = ('vision', 'json_estricto', 'scene_3d', 'diagram_2d', 'explicacion')
LEVELS = ('verificado', 'declarado', 'no_soportado')
NO_DATA = 'sin_datos'
_LOCK = threading.RLock()


class CapabilityTable:
    def __init__(self, path: Optional[Path] = None, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        if self.path and self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (OSError, ValueError):
                self._data = {}

    @staticmethod
    def _key(provider: str, model: str) -> str:
        if not all(isinstance(v, str) and 0 < len(v.strip()) <= 200 for v in (provider, model)):
            raise ValueError('Conexión y modelo deben ser texto de 1 a 200 caracteres.')
        return f'{provider.strip()}::{model.strip()}'

    @staticmethod
    def _check(capability: str) -> None:
        if capability not in CAPABILITIES:
            raise ValueError(f'Capacidad desconocida: {capability}')

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(temporary, self.path)  # atomic: a crash never leaves a half-written table

    def level(self, provider: str, model: str, capability: str) -> Optional[str]:
        self._check(capability)
        with _LOCK:
            entry = self._data.get(self._key(provider, model), {}).get(capability)
            return entry['level'] if isinstance(entry, dict) and entry.get('level') in LEVELS else None

    def get(self, provider: str, model: str) -> Dict[str, Optional[Dict[str, Any]]]:
        with _LOCK:
            row = self._data.get(self._key(provider, model), {})
            return {c: (dict(row[c]) if isinstance(row.get(c), dict) else None) for c in CAPABILITIES}

    def summary(self, provider: str, model: str) -> Dict[str, str]:
        return {c: (v['level'] if v else NO_DATA) for c, v in self.get(provider, model).items()}

    def declare(self, provider: str, model: str, capability: str, evidence: str) -> None:
        """Record what the provider or the connection claims. A real test result is never overwritten by a claim."""
        self._check(capability)
        with _LOCK:
            row = self._data.setdefault(self._key(provider, model), {})
            if row.get(capability, {}).get('level') in ('verificado', 'no_soportado'):
                return
            if row.get(capability, {}).get('level') == 'declarado' and row[capability].get('evidence') == str(evidence)[:200]:
                return  # unchanged claim: no rewrite
            row[capability] = {'level': 'declarado', 'evidence': str(evidence)[:200], 'at': self.clock()}
            self._save()

    def verify(self, provider: str, model: str, capability: str, ok: bool, evidence: str, mode: Optional[str] = None) -> None:
        """Record a real test result: verificado when it passed, no_soportado when it failed."""
        self._check(capability)
        with _LOCK:
            row = self._data.setdefault(self._key(provider, model), {})
            row[capability] = {'level': 'verificado' if ok else 'no_soportado', 'evidence': str(evidence)[:200], 'at': self.clock(),
                               **({'mode': mode} if mode else {})}
            self._save()
