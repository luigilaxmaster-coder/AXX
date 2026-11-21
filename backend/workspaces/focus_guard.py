"""AttentionGuardian & FocusGuard — Anti-Focus-Stealing & Zero Silent SendInput Fallback (PR-15 / PC-01 / PC-04 / I-06).

Enforces Invariants:
- I-06 / PC-01 / PC-04: Background UIA or browser tasks NEVER silently fall back to physical
  SendInput or SetForegroundWindow when the user is active or when foreground_policy is
  'isolated_only', 'deny', 'queue', or 'ask' without explicit approval + active host_input lease.
- PC-02: Emergency hotkey revocation (Ctrl+Alt+Backspace) immediately revokes the active host_input
  lease and increments the fencing counter so in-flight workers are fenced out.
"""
from __future__ import annotations

import time
from typing import Any

from backend.workspaces.leases import ResourceLeaseManager

VALID_FOREGROUND_POLICIES = frozenset({'ask', 'queue', 'isolated_only', 'deny'})


class PhysicalFocusProhibitedError(PermissionError):
    """Raised when an operation attempts physical focus / SendInput in violation of FocusGuard policy (PC-01 / PC-04)."""


class AttentionGuardian:
    """Monitors human desktop activity and gates any action that could steal focus or inject physical input."""

    def __init__(
        self,
        lease_manager: ResourceLeaseManager,
        *,
        host_resource_key: str = 'windows-host-001',
        human_quiet_window_ms: int = 5_000,
        clock=None,
    ):
        self.lease_manager = lease_manager
        self.host_resource_key = host_resource_key
        self.human_quiet_window_ms = int(human_quiet_window_ms)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.last_human_input_ms: int = -1_000_000
        self.call_or_dictation_active: bool = False
        self.fullscreen_app_active: bool = False
        self.approved_tokens: set[str] = set()

    def record_human_activity(self, timestamp_ms: int | None = None) -> None:
        self.last_human_input_ms = self.clock() if timestamp_ms is None else int(timestamp_ms)

    def set_call_or_dictation_active(self, active: bool) -> None:
        self.call_or_dictation_active = bool(active)

    def set_fullscreen_app_active(self, active: bool) -> None:
        self.fullscreen_app_active = bool(active)

    def grant_explicit_foreground_approval(self, approval_token: str) -> None:
        if not isinstance(approval_token, str) or not approval_token.strip():
            raise ValueError('approval_token must be a non-empty string')
        self.approved_tokens.add(approval_token.strip())

    def is_human_busy(self) -> tuple[bool, str]:
        now_ms = self.clock()
        if self.call_or_dictation_active:
            return True, 'call_or_dictation_active'
        if self.fullscreen_app_active:
            return True, 'fullscreen_app_active'
        if (now_ms - self.last_human_input_ms) < self.human_quiet_window_ms:
            return True, 'human_keyboard_or_mouse_active'
        return False, 'idle'

    def evaluate_foreground_request(
        self,
        *,
        foreground_policy: str,
        owner_run_id: str,
        fencing_token: int | None = None,
        approval_token: str | None = None,
        attempted_silent_fallback: bool = False,
    ) -> dict[str, Any]:
        """Evaluate whether a physical foreground / SendInput operation may proceed (PC-01 / PC-04)."""
        if foreground_policy not in VALID_FOREGROUND_POLICIES:
            raise ValueError(f'Invalid foreground_policy: {foreground_policy!r}')

        if attempted_silent_fallback:
            raise PhysicalFocusProhibitedError(
                'Silent fallback from background UIA/browser to physical SendInput is strictly prohibited (I-06 / PC-04)'
            )

        if foreground_policy in ('isolated_only', 'deny'):
            raise PhysicalFocusProhibitedError(
                f'Physical host focus / SendInput blocked by foreground_policy={foreground_policy!r}'
            )

        busy, busy_reason = self.is_human_busy()
        if foreground_policy == 'queue' and busy:
            return {
                'decision': 'queued',
                'allowed': False,
                'reason': busy_reason,
                'foreground_policy': foreground_policy,
            }

        if foreground_policy == 'ask':
            if not approval_token or approval_token not in self.approved_tokens:
                return {
                    'decision': 'approval_required',
                    'allowed': False,
                    'reason': 'explicit_user_approval_required_for_host_input',
                    'foreground_policy': foreground_policy,
                }
            if busy:
                return {
                    'decision': 'queued',
                    'allowed': False,
                    'reason': busy_reason,
                    'foreground_policy': foreground_policy,
                }

        if fencing_token is None:
            raise PhysicalFocusProhibitedError('Active host_input lease fencing_token is required for physical host input')

        lease = self.lease_manager.verify_fencing_token(
            resource_type='host_input',
            resource_key=self.host_resource_key,
            owner_run_id=owner_run_id,
            fencing_token=int(fencing_token),
        )
        return {
            'decision': 'allowed',
            'allowed': True,
            'lease_id': lease['lease_id'],
            'fencing_token': lease['fencing_token'],
            'foreground_policy': foreground_policy,
        }

    def trigger_emergency_hotkey_revocation(self) -> dict[str, Any]:
        """Handle emergency revocation hotkey (Ctrl+Alt+Backspace): revoke host_input lease & bump fencing token (PC-02)."""
        self.record_human_activity()
        new_fencing_token = self.lease_manager.preempt_and_revoke_resource('host_input', self.host_resource_key)
        return {
            'status': 'revoked',
            'resource_type': 'host_input',
            'resource_key': self.host_resource_key,
            'new_fencing_token': new_fencing_token,
        }
