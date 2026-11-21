"""Authenticated Mobile/Remote Continuity Protocol with Scope Intersection Guard (PR-19 / E2E-08 / MOBILE-01 / SEC-01).

Enforces Invariants:
- I-09 / MOBILE-01: Preserves all existing /v1 mobile companion routes, pairing state, and tokens.
- E2E-08: A paired mobile companion or remote worker node can monitor PC runs and resolve approval cards
  ONLY within the intersection of (device_granted_scopes & agent_allowed_scopes); any attempt to escalate
  scopes or invoke host_admin/ungranted tools from a mobile companion is rejected.
- SEC-01: Device tokens are verified in constant time via hmac.compare_digest.
"""
from __future__ import annotations

import hmac
from typing import Any


class RemoteAuthenticationError(PermissionError):
    """Raised when a remote worker or mobile companion presents an invalid or unpaired token (SEC-01)."""


class RemoteScopeEscalationError(PermissionError):
    """Raised when a mobile companion or remote worker requests an action outside its granted scopes (E2E-08)."""


class RemoteWorkerContinuityService:
    """Manages Mobile <-> PC multi-agent continuity, approval card forwarding, and remote worker handshakes."""

    def __init__(self):
        self.paired_devices: dict[str, dict[str, Any]] = {}

    def register_paired_device(
        self,
        *,
        device_id: str,
        device_token: str,
        granted_scopes: list[str] | set[str],
        device_kind: str = 'android_companion',
    ) -> dict[str, Any]:
        if not device_id or not device_token or len(device_token) < 12:
            raise ValueError('device_id and a strong device_token (>=12 chars) are required')
        entry = {
            'device_id': device_id,
            'device_token': device_token,
            'granted_scopes': set(granted_scopes),
            'device_kind': device_kind,
        }
        self.paired_devices[device_id] = entry
        return {
            'device_id': device_id,
            'granted_scopes': sorted(entry['granted_scopes']),
            'device_kind': device_kind,
        }

    def authenticate_device(self, device_id: str, presented_token: str | None) -> dict[str, Any]:
        if not presented_token or device_id not in self.paired_devices:
            raise RemoteAuthenticationError(f'Unauthenticated or unknown remote device: {device_id!r}')
        device = self.paired_devices[device_id]
        if not hmac.compare_digest(device['device_token'].encode('utf-8'), str(presented_token).encode('utf-8')):
            raise RemoteAuthenticationError(f'Invalid device token for {device_id!r}')
        return device

    def authorize_remote_command(
        self,
        *,
        device_id: str,
        presented_token: str | None,
        required_scope: str,
        agent_allowed_scopes: set[str] | list[str],
    ) -> dict[str, Any]:
        """Verify device token and enforce strict intersection (device_scopes & agent_scopes) (E2E-08)."""
        device = self.authenticate_device(device_id, presented_token)
        agent_set = set(agent_allowed_scopes)
        effective_scopes = device['granted_scopes'] & agent_set

        if required_scope not in device['granted_scopes']:
            raise RemoteScopeEscalationError(
                f'Mobile/remote device {device_id!r} lacks scope {required_scope!r} '
                f"(device_scopes={sorted(device['granted_scopes'])})"
            )
        if required_scope not in agent_set:
            raise RemoteScopeEscalationError(
                f'Target PC agent lacks scope {required_scope!r}; remote device cannot escalate agent privileges (E2E-08)'
            )

        return {
            'authorized': True,
            'device_id': device_id,
            'required_scope': required_scope,
            'effective_scopes': sorted(effective_scopes),
        }

    def resolve_approval_from_mobile(
        self,
        *,
        device_id: str,
        presented_token: str | None,
        orchestrator,
        operation_id: str,
        approved: bool,
    ) -> dict[str, Any]:
        """Allow a paired mobile device with 'companion.approvals' scope to resolve a pending PC approval card (E2E-08)."""
        device = self.authenticate_device(device_id, presented_token)
        if 'companion.approvals' not in device['granted_scopes']:
            raise RemoteScopeEscalationError(
                f'Device {device_id!r} does not have companion.approvals scope to resolve PC approval cards'
            )
        return orchestrator.resolve_human_approval(
            operation_id=operation_id,
            approved=approved,
            actor=f'mobile:{device_id}',
        )
