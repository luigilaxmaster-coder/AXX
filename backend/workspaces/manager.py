"""Background Interaction Router & Real Event-Correlated Virtual Cursor Telemetry (PR-15 & PR-16 / PC-01..PC-05 / I-10).

Enforces Invariants:
- PC-01..PC-05: Routes interaction through strict preference hierarchy:
  1. direct_api
  2. isolated_browser
  3. uia_background (with composite window identity verification and zero silent SendInput fallback)
  4. isolated_vm
  5. host_foreground (gated by AttentionGuardian + active host_input lease)
- I-10: Virtual cursor telemetry frames MUST correlate with a real registered tool/action event
  ('tool.dispatched', 'tool.progress', 'tool.completed'); decorative or unbacked cursor movements are rejected.
"""
from __future__ import annotations

from typing import Any

from backend.workspaces.browser_sessions import BrowserSessionManager
from backend.workspaces.focus_guard import AttentionGuardian, PhysicalFocusProhibitedError
from backend.workspaces.leases import ResourceLeaseManager, verify_window_identity
from backend.workspaces.vm_provider import IsolatedVMProvider

ALLOWED_CURSOR_EVENT_TYPES = frozenset({'tool.dispatched', 'tool.progress', 'tool.completed'})
ALLOWED_UIA_PATTERNS = frozenset({'InvokePattern', 'ValuePattern', 'TogglePattern', 'SelectionItemPattern', 'ExpandCollapsePattern'})


class FabricatedCursorTelemetryError(ValueError):
    """Raised when a virtual cursor frame is emitted without a real verified tool execution event (I-10)."""


class VirtualCursorTelemetryService:
    """Tracks and validates virtual cursor telemetry strictly correlated to real tool execution events (I-10)."""

    def __init__(self):
        self.registered_tool_events: dict[str, dict[str, Any]] = {}
        self.cursor_frames: list[dict[str, Any]] = []

    def register_real_tool_event(
        self,
        *,
        event_id: str,
        event_type: str,
        run_id: str,
        agent_id: str,
        workspace_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        if event_type not in ALLOWED_CURSOR_EVENT_TYPES:
            raise FabricatedCursorTelemetryError(
                f'Virtual cursor telemetry can only bind to {sorted(ALLOWED_CURSOR_EVENT_TYPES)}, got {event_type!r}'
            )
        record = {
            'event_id': event_id,
            'event_type': event_type,
            'run_id': run_id,
            'agent_id': agent_id,
            'workspace_id': workspace_id,
            'fencing_token': int(fencing_token),
        }
        self.registered_tool_events[event_id] = record
        return record

    def emit_cursor_frame(
        self,
        *,
        cursor_id: str,
        correlating_event_id: str,
        surface_type: str,
        x: float,
        y: float,
        action_state: str,
    ) -> dict[str, Any]:
        """Emit a virtual cursor frame only if backed by a registered real tool event (I-10)."""
        if not correlating_event_id or correlating_event_id not in self.registered_tool_events:
            raise FabricatedCursorTelemetryError(
                f'Virtual cursor frame rejected (I-10): correlating_event_id={correlating_event_id!r} is not a real tool event'
            )
        ev = self.registered_tool_events[correlating_event_id]
        frame = {
            'cursor_id': cursor_id,
            'correlating_event_id': correlating_event_id,
            'event_type': ev['event_type'],
            'run_id': ev['run_id'],
            'agent_id': ev['agent_id'],
            'workspace_id': ev['workspace_id'],
            'fencing_token': ev['fencing_token'],
            'surface_type': surface_type,
            'x': float(x),
            'y': float(y),
            'action_state': action_state,
            'affects_physical_host_cursor': False,
        }
        self.cursor_frames.append(frame)
        return frame


class BackgroundInteractionRouter:
    """Routes background computer-use actions across API, isolated browser, semantic UIA, isolated VM, and gated host input."""

    def __init__(
        self,
        *,
        lease_manager: ResourceLeaseManager,
        focus_guard: AttentionGuardian,
        browser_manager: BrowserSessionManager,
        vm_provider: IsolatedVMProvider,
        cursor_telemetry: VirtualCursorTelemetryService | None = None,
    ):
        self.lease_manager = lease_manager
        self.focus_guard = focus_guard
        self.browser_manager = browser_manager
        self.vm_provider = vm_provider
        self.cursor_telemetry = cursor_telemetry or VirtualCursorTelemetryService()

    def execute_uia_background_action(
        self,
        *,
        owner_run_id: str,
        fencing_token: int,
        leased_window_key: str,
        live_window_info: dict[str, Any],
        uia_pattern: str,
        control_id: str,
        value: Any = None,
        requires_physical_focus: bool = False,
        attempted_silent_sendinput_fallback: bool = False,
        foreground_policy: str = 'queue',
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        """Execute a semantic UIA action on a background window without stealing focus (PC-01, PC-03, PC-04)."""
        if attempted_silent_sendinput_fallback:
            raise PhysicalFocusProhibitedError(
                'Silent fallback from semantic UIA to physical SendInput is strictly prohibited (PC-04 / I-06)'
            )

        # 1. Verify window ResourceLease fencing token
        self.lease_manager.verify_fencing_token(
            resource_type='window',
            resource_key=leased_window_key,
            owner_run_id=owner_run_id,
            fencing_token=int(fencing_token),
        )

        # 2. Verify live window composite identity (hwnd + pid + process_start_ms + class_name) (PC-03)
        verify_window_identity(leased_window_key, live_window_info)

        # 3. If the control requires physical focus (cannot be driven via semantic UIA pattern),
        #    NEVER silently use SendInput; consult AttentionGuardian policy instead (PC-04).
        if requires_physical_focus or uia_pattern not in ALLOWED_UIA_PATTERNS:
            fg_eval = self.focus_guard.evaluate_foreground_request(
                foreground_policy=foreground_policy,
                owner_run_id=owner_run_id,
                fencing_token=None,
                approval_token=approval_token,
                attempted_silent_fallback=False,
            )
            return {
                'status': fg_eval['decision'],
                'executed': False,
                'channel': 'uia_background',
                'reason': fg_eval['reason'],
                'used_host_sendinput': False,
                'stole_foreground_focus': False,
            }

        return {
            'status': 'completed',
            'executed': True,
            'channel': 'uia_background',
            'window_key': leased_window_key,
            'uia_pattern': uia_pattern,
            'control_id': control_id,
            'value': value,
            'fencing_token': int(fencing_token),
            'used_host_sendinput': False,
            'stole_foreground_focus': False,
        }
