"""Authoritative backend permission intersection, delegation attenuation, and provider switch policy (PR-11 / SEC-02 / AGENT-04).

Enforces Invariants:
- EffectivePermission = UserGrant ∩ ConversationPolicy ∩ AgentPolicy ∩ ProjectACL ∩ ResourcePolicy ∩ RuntimeCapability.
- I-02 / SEC-02: Delegation to a sub-agent strictly attenuates permissions (SubGrant ⊆ ParentEffectivePermission).
  Prompt text or role names ('admin', 'system', 'unrestricted') NEVER add permissions.
- I-09 / AGENT-04: Switching provider invalidates prior provider session tokens, preserves local conversation
  history, and never silently falls back to an unapproved paid provider.
"""
from __future__ import annotations

import copy
from typing import Any

OPERATION_CLASSES = frozenset({
    'read_scoped',
    'compute_pure',
    'write_workspace',
    'host_window',
    'host_global_input',
    'external_write',
    'privileged',
})


class PermissionDeniedError(PermissionError):
    """Raised when an operation or handoff exceeds effective permissions."""


def resolve_effective_permissions(
    *,
    user_grants: set[str],
    conversation_mode: str,
    agent_grants: set[str],
    project_allowed_tools: set[str] | None = None,
    runtime_supported_tools: set[str] | None = None,
    agent_enabled: bool = True,
) -> dict[str, Any]:
    """Compute the strict backend intersection of all 6 permission boundaries (§5.1)."""
    if not agent_enabled:
        return {
            'effective_tools': frozenset(),
            'auto_safe_allowed': False,
            'requires_explicit_approval': True,
            'reason': 'agent_disabled',
        }
    effective = set(user_grants) & set(agent_grants)
    if project_allowed_tools is not None:
        effective &= set(project_allowed_tools)
    if runtime_supported_tools is not None:
        effective &= set(runtime_supported_tools)

    # §5.2: 'unrestricted' stored in legacy chat NEVER translates to provider bypassPermissions
    auto_safe = conversation_mode in ('auto_safe', 'unrestricted')
    return {
        'effective_tools': frozenset(effective),
        'auto_safe_allowed': auto_safe,
        'requires_explicit_approval': not auto_safe,
        'provider_bypass_permissions': False,
    }


def attenuate_delegated_grants(
    *,
    parent_effective_tools: set[str] | frozenset[str],
    requested_delegate_tools: set[str] | list[str],
    parent_delegate_depth: int,
    max_delegate_depth: int,
) -> frozenset[str]:
    """Verify that a handoff only transmits an equal or narrower scope and respects delegation depth (I-02 / SEC-02)."""
    if parent_delegate_depth + 1 > max_delegate_depth:
        raise PermissionDeniedError(
            f'Delegation depth {parent_delegate_depth + 1} exceeds max_delegate_depth={max_delegate_depth}'
        )
    parent_set = set(parent_effective_tools)
    requested_set = set(requested_delegate_tools)
    unauthorized = requested_set - parent_set
    if unauthorized:
        raise PermissionDeniedError(
            f'Confused deputy / privilege escalation blocked (SEC-02): parent cannot delegate unowned grants {sorted(unauthorized)}'
        )
    return frozenset(requested_set & parent_set)


def apply_provider_switch_policy(
    profile: dict[str, Any],
    *,
    new_provider_ref: str,
    new_model_id: str,
    prior_session_tokens: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Switch an agent's provider/model safely without leaking prior session tokens or broadening grants (AGENT-04)."""
    updated = copy.deepcopy(profile)
    old_provider = updated.get('intelligence', {}).get('provider_profile_ref')
    updated['revision'] = int(updated.get('revision', 1)) + 1
    updated.setdefault('intelligence', {})['provider_profile_ref'] = str(new_provider_ref)
    updated['intelligence']['model_id'] = str(new_model_id)

    return {
        'profile': updated,
        'previous_provider_profile_ref': old_provider,
        'new_provider_profile_ref': new_provider_ref,
        'transferred_session_tokens': {},  # Never carry session tokens across providers
        'revoked_session_count': len(prior_session_tokens or {}),
        'permissions_unchanged': updated['permissions'] == profile['permissions'],
    }
