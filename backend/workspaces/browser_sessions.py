"""Isolated Background Browser Profile & Session Manager (PR-15 / PC-01 / E2E-03).

Enforces Invariants:
- E2E-03 / PC-01: Each background browser workspace uses an isolated, dedicated profile directory
  ('browser_profiles/<profile_id>') and NEVER attaches to the user's personal default Chrome/Edge/Brave
  profile or steals physical OS focus.
- PC-02: Every mutating browser action verifies its 'browser_profile' ResourceLease fencing_token.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from backend.workspaces.leases import ResourceLeaseManager

PROFILE_ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,120}$')
FORBIDDEN_PERSONAL_PATH_MARKERS = (
    'google/chrome/user data',
    'microsoft/edge/user data',
    'bravesoftware/brave-browser/user data',
    'mozilla/firefox/profiles',
)


class PersonalBrowserProfileBlockedError(PermissionError):
    """Raised when an agent or workspace attempts to attach to the user's personal browser profile (E2E-03)."""


class BrowserSessionManager:
    """Manages isolated background browser profiles and lease-fenced DOM operations (PC-01 / E2E-03)."""

    def __init__(self, lease_manager: ResourceLeaseManager, *, profiles_root: str | Path):
        self.lease_manager = lease_manager
        self.profiles_root = Path(profiles_root).resolve()
        self._validate_not_personal_root(self.profiles_root)
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _validate_not_personal_root(candidate_path: Path) -> None:
        normalized = str(candidate_path).replace('\\', '/').lower()
        for marker in FORBIDDEN_PERSONAL_PATH_MARKERS:
            if marker in normalized:
                raise PersonalBrowserProfileBlockedError(
                    f'Attaching to personal browser profile path is strictly prohibited: {candidate_path}'
                )
        if candidate_path.name.lower() in ('default', 'profile 1', 'profile 2'):
            raise PersonalBrowserProfileBlockedError(
                f'Personal browser profile name {candidate_path.name!r} is prohibited'
            )

    def create_isolated_session(
        self,
        *,
        session_id: str,
        profile_id: str,
        agent_id: str,
        custom_profile_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(profile_id):
            raise ValueError(f'Invalid profile_id: {profile_id!r}')
        if profile_id.lower() in ('default', 'personal', 'system-default'):
            raise PersonalBrowserProfileBlockedError(f'Reserved personal profile_id rejected: {profile_id!r}')

        if custom_profile_dir is not None:
            cand = Path(custom_profile_dir).resolve()
            self._validate_not_personal_root(cand)
            if not cand.is_relative_to(self.profiles_root):
                raise PersonalBrowserProfileBlockedError(
                    f'Browser profile directory {cand} must reside inside isolated root {self.profiles_root}'
                )
            profile_dir = cand
        else:
            profile_dir = (self.profiles_root / profile_id).resolve()
            self._validate_not_personal_root(profile_dir)

        profile_dir.mkdir(parents=True, exist_ok=True)
        session = {
            'session_id': session_id,
            'profile_id': profile_id,
            'agent_id': agent_id,
            'user_data_dir': str(profile_dir),
            'headless_or_offscreen': True,
            'steals_host_focus': False,
            'current_url': 'about:blank',
            'history': [],
        }
        self.sessions[session_id] = session
        return dict(session)

    def execute_dom_action(
        self,
        *,
        session_id: str,
        owner_run_id: str,
        fencing_token: int,
        action: str,
        target: str = '',
        value: str = '',
    ) -> dict[str, Any]:
        """Execute an isolated DOM action after verifying the browser_profile ResourceLease fencing_token."""
        if session_id not in self.sessions:
            raise LookupError(f'Browser session not found: {session_id}')
        session = self.sessions[session_id]

        self.lease_manager.verify_fencing_token(
            resource_type='browser_profile',
            resource_key=session['profile_id'],
            owner_run_id=owner_run_id,
            fencing_token=int(fencing_token),
        )

        if action == 'navigate':
            session['current_url'] = target
        record = {
            'action': action,
            'target': target,
            'value': value,
            'fencing_token': int(fencing_token),
            'used_host_sendinput': False,
            'stole_foreground_focus': False,
        }
        session['history'].append(record)
        return {
            'status': 'completed',
            'session_id': session_id,
            'profile_id': session['profile_id'],
            'current_url': session['current_url'],
            'action_receipt': record,
        }
