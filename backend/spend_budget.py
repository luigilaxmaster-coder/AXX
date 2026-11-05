"""Estimated spend of paid models in Magic Pen, with a hard ceiling the owner chooses (5 USD by default).

It counts tokens the provider reports and multiplies them by the connection's own prices (``usd_per_mtok_in`` / ``usd_per_mtok_out``) or, when
a connection declares none, by a stated assumption. It is an estimate, never an invoice. Subscriptions (ChatGPT/Codex), local Ollama and
connections confirmed free are not metered. Only usage numbers are stored: no prompts, answers, images or keys.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

DEFAULT_LIMIT_USD = 5.0
MAX_LIMIT_USD = 1000.0
ASSUMED_PRICES = {'in': 3.0, 'out': 15.0}  # USD per million tokens; used only when the connection declares no price
CACHE_WRITE_FACTOR, CACHE_READ_FACTOR = 1.25, 0.10  # of the input price, the usual prompt-cache terms
MAX_ENTRIES = 400
UNMETERED_KINDS = {'ollama', 'ollama_cloud', 'compat', 'freellmapi'}
_LOCK = threading.RLock()


class BudgetExceeded(ValueError):
    """The estimated spend reached the owner's ceiling; no further paid call is made."""


def is_metered(connection: Dict[str, Any]) -> bool:
    """True when calls through this connection cost money. Codex is a subscription; unknown connections count as paid, the safe side."""
    if connection.get('name') == '@codex' or connection.get('protocol') == 'codex':
        return False
    if connection.get('kind') in UNMETERED_KINDS or connection.get('free_confirmed') is True:
        return False
    return True


def prices_for(connection: Dict[str, Any]) -> Dict[str, Any]:
    declared_in, declared_out = connection.get('usd_per_mtok_in'), connection.get('usd_per_mtok_out')
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1000 for v in (declared_in, declared_out)):
        return {'in': float(declared_in), 'out': float(declared_out), 'assumed': False}
    return {**ASSUMED_PRICES, 'assumed': True}


def estimate_usd(usage: Dict[str, Any], prices: Dict[str, Any]) -> float:
    def count(key: str) -> int:
        value = usage.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
    per_token_in, per_token_out = prices['in'] / 1_000_000, prices['out'] / 1_000_000
    return (count('input_tokens') * per_token_in + count('cache_creation_input_tokens') * per_token_in * CACHE_WRITE_FACTOR
            + count('cache_read_input_tokens') * per_token_in * CACHE_READ_FACTOR + count('output_tokens') * per_token_out)


class SpendBudget:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path, self.clock = Path(path), clock
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('entries'), list):
                limit = data.get('limit_usd')
                return {'limit_usd': float(limit) if isinstance(limit, (int, float)) and 0 < limit <= MAX_LIMIT_USD else DEFAULT_LIMIT_USD,
                        'since': float(data.get('since') or self.clock()), 'entries': [e for e in data['entries'] if isinstance(e, dict)][-MAX_ENTRIES:],
                        'spent_before_trim': float(data.get('spent_before_trim') or 0)}
        except (OSError, ValueError, TypeError):
            pass
        return {'limit_usd': DEFAULT_LIMIT_USD, 'since': self.clock(), 'entries': [], 'spent_before_trim': 0.0}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(temporary, self.path)

    def spent(self) -> float:
        with _LOCK:
            return round(self._data['spent_before_trim'] + sum(float(e.get('usd', 0)) for e in self._data['entries']), 6)

    def summary(self) -> Dict[str, Any]:
        with _LOCK:
            spent, limit = self.spent(), self._data['limit_usd']
            return {'limit_usd': limit, 'spent_usd': round(spent, 4), 'remaining_usd': round(max(0.0, limit - spent), 4), 'calls': len(self._data['entries']),
                    'since': self._data['since'], 'estimate': True, 'assumed_prices': ASSUMED_PRICES}

    def check(self, connection: Dict[str, Any]) -> None:
        """Called before every call. Unmetered connections never consume the budget."""
        if not is_metered(connection):
            return
        with _LOCK:
            if self.spent() >= self._data['limit_usd']:
                raise BudgetExceeded(f"Se alcanzó el presupuesto de {self._data['limit_usd']:.2f} USD (gasto estimado {self.spent():.2f} USD). "
                                     'Súbelo o restablécelo en «Mejores modelos», o elige un modelo gratuito o de suscripción.')

    def record(self, connection: Dict[str, Any], usage: Optional[Dict[str, Any]], purpose: str = '') -> float:
        """Add one call. Returns its estimated cost in USD (0 when unmetered or when the provider reported no usage)."""
        if not is_metered(connection) or not isinstance(usage, dict):
            return 0.0
        prices = prices_for(connection)
        usd = round(estimate_usd(usage, prices), 6)
        with _LOCK:
            self._data['entries'].append({'at': round(self.clock(), 1), 'connection': str(connection.get('name', ''))[:80], 'model': str(connection.get('model', ''))[:120],
                                          'purpose': purpose[:30], 'usd': usd, 'assumed_prices': prices['assumed'],
                                          **{k: usage[k] for k in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
                                             if isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)}})
            if len(self._data['entries']) > MAX_ENTRIES:
                overflow = self._data['entries'][:-MAX_ENTRIES]
                self._data['spent_before_trim'] += sum(float(e.get('usd', 0)) for e in overflow)
                self._data['entries'] = self._data['entries'][-MAX_ENTRIES:]
            self._save()
        return usd

    def configure(self, *, limit_usd: Optional[float] = None, reset: bool = False) -> Dict[str, Any]:
        """The owner's decision: change the ceiling and/or start counting again. Never called by a model or by page content."""
        with _LOCK:
            if limit_usd is not None:
                if isinstance(limit_usd, bool) or not isinstance(limit_usd, (int, float)) or not 0 < limit_usd <= MAX_LIMIT_USD:
                    raise ValueError(f'El presupuesto debe estar entre 0 y {MAX_LIMIT_USD:.0f} USD.')
                self._data['limit_usd'] = float(limit_usd)
            if reset:
                self._data.update(entries=[], spent_before_trim=0.0, since=self.clock())
            self._save()
        return self.summary()
