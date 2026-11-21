"""Typed Multi-Agent Handoff v1 Contract, Scope Attenuation, Prompt-Injection Sanitizer & DLP Filter (PR-17 / SEC-02 / SEC-04 / E2E-10).

Enforces Invariants:
- SEC-02: A parent agent can NEVER delegate a tool grant or scope it does not possess itself
  (strict scope attenuation: child_grants <= parent_grants).
- SEC-04: External data, tool outputs, and sibling agent messages are treated as untrusted data;
  prompt-injection directives attempting to override system rules or escalate permissions are stripped
  and flagged, never executed as control instructions.
- E2E-10: DLP-classified context items ('secret', 'private_credential', 'personal_vault') are blocked
  from handoffs to subagents outside the authorized scope.
"""
from __future__ import annotations

import copy
import re
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SHA256_RE = re.compile(r'^[a-f0-9]{64}$')

PROMPT_INJECTION_PATTERNS = (
    re.compile(r'ignore\s+(all\s+)?(previous|prior|system)\s+instructions', re.IGNORECASE),
    re.compile(r'<\s*/?\s*(system|developer|admin_override)\s*>', re.IGNORECASE),
    re.compile(r'grant_tool_permission|elevate_privilege|bypass_approval|disable_focus_guard', re.IGNORECASE),
    re.compile(r'execute_shell_unrestricted|sendinput_force', re.IGNORECASE),
)


class HandoffValidationError(ValueError):
    """Raised when a Handoff payload violates schemas/handoff.schema.json."""


class ScopeEscalationError(PermissionError):
    """Raised when a handoff attempts to grant tools or scopes not held by the delegating agent (SEC-02)."""


class PromptInjectionBlockedError(PermissionError):
    """Raised when untrusted handoff input attempts to execute an injected control action (SEC-04)."""


class DlpPolicyViolationError(PermissionError):
    """Raised when private/DLP-protected data is included in a handoff to an unauthorized agent (E2E-10)."""


def validate_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a Handoff v1 against schemas/handoff.schema.json."""
    if not isinstance(payload, dict):
        raise HandoffValidationError('Handoff must be a JSON object')

    required = {
        'schema_version',
        'handoff_id',
        'task_id',
        'run_id',
        'conversation_id',
        'from_agent_id',
        'to_agent_id',
        'objective',
        'operation_id',
        'idempotency_key',
        'tool_grant_refs',
        'inputs',
        'required_outputs',
        'acceptance_criteria',
        'limits',
    }
    allowed = required | {'context_refs'}
    missing = required - set(payload.keys())
    if missing:
        raise HandoffValidationError(f'Missing required Handoff fields: {sorted(missing)}')
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise HandoffValidationError(f'Unknown Handoff fields: {sorted(unknown)}')

    if payload.get('schema_version') != '1.0':
        raise HandoffValidationError("schema_version must be '1.0'")

    for id_field in (
        'handoff_id',
        'task_id',
        'run_id',
        'conversation_id',
        'from_agent_id',
        'to_agent_id',
        'operation_id',
        'idempotency_key',
    ):
        val = payload.get(id_field)
        if not isinstance(val, str) or not ID_RE.fullmatch(val):
            raise HandoffValidationError(f'Invalid {id_field}: {val!r}')

    if payload['from_agent_id'] == payload['to_agent_id']:
        raise HandoffValidationError('Self-handoff (from_agent_id == to_agent_id) is invalid')

    obj = payload.get('objective')
    if not isinstance(obj, str) or not (1 <= len(obj.strip()) <= 6000):
        raise HandoffValidationError('objective must be 1..6000 chars')

    if 'context_refs' in payload:
        c_refs = payload['context_refs']
        if not isinstance(c_refs, list) or len(c_refs) > 64 or not all(isinstance(r, str) and ID_RE.fullmatch(r) for r in c_refs):
            raise HandoffValidationError('Invalid context_refs')

    grants = payload.get('tool_grant_refs')
    if (
        not isinstance(grants, list)
        or len(grants) > 128
        or len(set(grants)) != len(grants)
        or not all(isinstance(g, str) and ID_RE.fullmatch(g) for g in grants)
    ):
        raise HandoffValidationError('tool_grant_refs must be a unique list of valid IDs (<= 128)')

    inputs = payload.get('inputs')
    if not isinstance(inputs, list) or len(inputs) > 128:
        raise HandoffValidationError('inputs must be a list of <= 128 items')
    for idx, inp in enumerate(inputs):
        if not isinstance(inp, dict):
            raise HandoffValidationError(f'inputs[{idx}] must be an object')
        if set(inp.keys()) - {'artifact_id', 'sha256', 'revision'} or not {'artifact_id', 'sha256'}.issubset(inp.keys()):
            raise HandoffValidationError(f'inputs[{idx}] invalid keys')
        if not isinstance(inp['artifact_id'], str) or not ID_RE.fullmatch(inp['artifact_id']):
            raise HandoffValidationError(f'inputs[{idx}].artifact_id invalid')
        if not isinstance(inp['sha256'], str) or not SHA256_RE.fullmatch(inp['sha256']):
            raise HandoffValidationError(f'inputs[{idx}].sha256 invalid')
        if 'revision' in inp and (not isinstance(inp['revision'], int) or isinstance(inp['revision'], bool) or inp['revision'] < 1):
            raise HandoffValidationError(f'inputs[{idx}].revision must be integer >= 1')

    req_out = payload.get('required_outputs')
    if not isinstance(req_out, list) or len(req_out) > 64 or not all(isinstance(s, str) and 1 <= len(s) <= 240 for s in req_out):
        raise HandoffValidationError('Invalid required_outputs')

    criteria = payload.get('acceptance_criteria')
    if not isinstance(criteria, list) or not (1 <= len(criteria) <= 64) or not all(isinstance(c, str) and 1 <= len(c) <= 2000 for c in criteria):
        raise HandoffValidationError('acceptance_criteria must be 1..64 non-empty strings')

    limits = payload.get('limits')
    if not isinstance(limits, dict):
        raise HandoffValidationError('limits must be an object')
    if set(limits.keys()) - {'max_attempts', 'deadline_seconds', 'max_cost_usd'} or not {'max_attempts', 'deadline_seconds'}.issubset(limits.keys()):
        raise HandoffValidationError('limits missing required fields or has unknown fields')
    ma = limits['max_attempts']
    ds = limits['deadline_seconds']
    if not isinstance(ma, int) or isinstance(ma, bool) or not (1 <= ma <= 10):
        raise HandoffValidationError('limits.max_attempts must be 1..10')
    if not isinstance(ds, int) or isinstance(ds, bool) or not (1 <= ds <= 604800):
        raise HandoffValidationError('limits.deadline_seconds must be 1..604800')
    if 'max_cost_usd' in limits:
        mc = limits['max_cost_usd']
        if not isinstance(mc, (int, float)) or isinstance(mc, bool) or mc < 0:
            raise HandoffValidationError('limits.max_cost_usd must be >= 0')

    return copy.deepcopy(payload)


def attenuate_handoff_grants(parent_grants: list[str] | set[str], requested_child_grants: list[str]) -> list[str]:
    """Ensure a delegated handoff only includes tool grants held by the parent agent (SEC-02)."""
    parent_set = set(parent_grants)
    escalated = [g for g in requested_child_grants if g not in parent_set]
    if escalated:
        raise ScopeEscalationError(
            f'Handoff scope escalation blocked (SEC-02): child requested grants not held by parent: {escalated}'
        )
    return list(dict.fromkeys(requested_child_grants))


def inspect_and_sanitize_untrusted_text(raw_text: str) -> dict[str, Any]:
    """Inspect untrusted tool output or inter-agent transcript for prompt injection patterns (SEC-04)."""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    matched_patterns: list[str] = []
    sanitized = raw_text
    for pat in PROMPT_INJECTION_PATTERNS:
        if pat.search(sanitized):
            matched_patterns.append(pat.pattern)
            sanitized = pat.sub('[REDACTED_UNTRUSTED_DIRECTIVE]', sanitized)
    return {
        'injection_detected': len(matched_patterns) > 0,
        'matched_patterns': matched_patterns,
        'sanitized_text': sanitized,
        'envelope': f'<untrusted_data>\n{sanitized}\n</untrusted_data>',
    }


def filter_dlp_context_items(
    context_items: list[dict[str, Any]],
    *,
    recipient_allowed_classifications: set[str] | None = None,
    strict_raise: bool = True,
) -> list[dict[str, Any]]:
    """Filter or block DLP-sensitive context items before handoff to another agent (E2E-10)."""
    allowed = recipient_allowed_classifications or {'public', 'workspace_internal'}
    safe_items: list[dict[str, Any]] = []
    for item in context_items:
        classification = str(item.get('classification', 'workspace_internal')).lower()
        text_val = str(item.get('content', ''))
        has_raw_secret = any(tok in text_val for tok in ('sk-live-', 'ghp_', 'AIzaSy', 'PRIVATE KEY-----'))
        if classification not in allowed or has_raw_secret:
            if strict_raise:
                raise DlpPolicyViolationError(
                    f"DLP policy blocked handoff of item {item.get('id', '?')!r} (classification={classification!r})"
                )
            continue
        safe_items.append(copy.deepcopy(item))
    return safe_items
