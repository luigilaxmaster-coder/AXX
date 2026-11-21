"""Unit, security, and integration tests for Phase 10 — Background Workspaces & Virtual Cursors (PR-15 & PR-16 / Gate G10).

Covers:
- PC-01 & E2E-03: Concurrent isolated background browser sessions while human is active; zero focus theft;
  personal default browser profile rejection.
- PC-02: ResourceLease v1 validation, exclusive lock, monotonic fencing_token, emergency Ctrl+Alt+Backspace
  revocation, and stale fencing token rejection.
- PC-03: Composite window identity (hwnd + pid + process_start_ms + class_name) verification and recycled
  handle abort.
- PC-04: Zero silent SendInput fallback when UIA pattern is unavailable; FocusGuard ask/queue/isolated_only/deny policies.
- PC-05 & E2E-04: IsolatedVMProvider probe -> create -> start -> act -> snapshot -> stop -> destroy lifecycle.
- I-10: Virtual cursor telemetry strictly correlated to real tool events.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.workspaces.browser_sessions import BrowserSessionManager, PersonalBrowserProfileBlockedError
from backend.workspaces.focus_guard import AttentionGuardian, PhysicalFocusProhibitedError
from backend.workspaces.leases import (
    LeaseConflictError,
    ResourceLeaseManager,
    StaleFencingTokenError,
    WindowIdentityMismatchError,
    build_window_identity_key,
    validate_resource_lease,
)
from backend.workspaces.manager import (
    BackgroundInteractionRouter,
    FabricatedCursorTelemetryError,
    VirtualCursorTelemetryService,
)
from backend.workspaces.vm_provider import IsolatedVMProvider, VMUnavailableError


class BackgroundWorkspacesTests(unittest.TestCase):
    def test_pc02_monotonic_fencing_tokens_and_emergency_hotkey_revocation(self) -> None:
        now = [1_700_000_000_000]
        leases = ResourceLeaseManager(':memory:', clock=lambda: now[0])
        self.addCleanup(leases.close)
        fg = AttentionGuardian(leases, clock=lambda: now[0])

        # Acquire first host_input lease -> fencing_token == 1
        l1 = leases.acquire_lease(
            lease_id='lease-1',
            owner_run_id='run-1',
            resource_type='host_input',
            resource_key='windows-host-001',
            ttl_ms=30_000,
        )
        validate_resource_lease(l1)
        self.assertEqual(l1['fencing_token'], 1)

        # Second concurrent run cannot acquire active host_input lease
        with self.assertRaises(LeaseConflictError):
            leases.acquire_lease(
                lease_id='lease-2',
                owner_run_id='run-2',
                resource_type='host_input',
                resource_key='windows-host-001',
            )

        # Human triggers emergency hotkey revocation (Ctrl+Alt+Backspace)
        rev = fg.trigger_emergency_hotkey_revocation()
        self.assertEqual(rev['status'], 'revoked')
        self.assertEqual(rev['new_fencing_token'], 2)

        # Delayed worker from run-1 presenting stale fencing_token=1 is fenced out
        with self.assertRaises(StaleFencingTokenError):
            leases.verify_fencing_token(
                resource_type='host_input',
                resource_key='windows-host-001',
                owner_run_id='run-1',
                fencing_token=1,
            )

        # Next acquired lease gets fencing_token == 3 (strictly monotonic)
        l3 = leases.acquire_lease(
            lease_id='lease-3',
            owner_run_id='run-2',
            resource_type='host_input',
            resource_key='windows-host-001',
        )
        self.assertEqual(l3['fencing_token'], 3)

    def test_pc01_and_e2e03_concurrent_isolated_browsers_while_human_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_700_000_000_000]
            leases = ResourceLeaseManager(':memory:', clock=lambda: now[0])
            self.addCleanup(leases.close)
            fg = AttentionGuardian(leases, clock=lambda: now[0])
            fg.record_human_activity(now[0])  # Human is actively typing right now

            browsers = BrowserSessionManager(leases, profiles_root=Path(tmp) / 'browser_profiles')

            # Personal profile names or Chrome User Data paths are blocked
            with self.assertRaises(PersonalBrowserProfileBlockedError):
                browsers.create_isolated_session(
                    session_id='s-bad',
                    profile_id='Default',
                    agent_id='agent-a',
                )
            with self.assertRaises(PersonalBrowserProfileBlockedError):
                browsers.create_isolated_session(
                    session_id='s-bad2',
                    profile_id='prof-ok',
                    agent_id='agent-a',
                    custom_profile_dir=Path('C:/Users/luigi/AppData/Local/Google/Chrome/User Data/Default'),
                )

            # Two agents create segregated background browser sessions and acquire per-profile leases
            s_a = browsers.create_isolated_session(
                session_id='sess-a',
                profile_id='agent-a-profile',
                agent_id='agent-a',
            )
            s_b = browsers.create_isolated_session(
                session_id='sess-b',
                profile_id='agent-b-profile',
                agent_id='agent-b',
            )
            self.assertNotEqual(s_a['user_data_dir'], s_b['user_data_dir'])

            lease_a = leases.acquire_lease(
                lease_id='l-ba',
                owner_run_id='run-a',
                resource_type='browser_profile',
                resource_key='agent-a-profile',
            )
            lease_b = leases.acquire_lease(
                lease_id='l-bb',
                owner_run_id='run-b',
                resource_type='browser_profile',
                resource_key='agent-b-profile',
            )

            res_a = browsers.execute_dom_action(
                session_id='sess-a',
                owner_run_id='run-a',
                fencing_token=lease_a['fencing_token'],
                action='navigate',
                target='https://docs.example.com/a',
            )
            res_b = browsers.execute_dom_action(
                session_id='sess-b',
                owner_run_id='run-b',
                fencing_token=lease_b['fencing_token'],
                action='navigate',
                target='https://docs.example.com/b',
            )
            self.assertFalse(res_a['action_receipt']['used_host_sendinput'])
            self.assertFalse(res_b['action_receipt']['stole_foreground_focus'])

    def test_pc03_and_pc04_window_identity_and_zero_silent_sendinput_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_700_000_000_000]
            leases = ResourceLeaseManager(':memory:', clock=lambda: now[0])
            self.addCleanup(leases.close)
            fg = AttentionGuardian(leases, clock=lambda: now[0])
            browsers = BrowserSessionManager(leases, profiles_root=Path(tmp) / 'profiles')
            vms = IsolatedVMProvider(leases, allow_simulated_sandbox=True)
            router = BackgroundInteractionRouter(
                lease_manager=leases,
                focus_guard=fg,
                browser_manager=browsers,
                vm_provider=vms,
            )

            win_key = build_window_identity_key(
                hwnd=102400,
                pid=4420,
                process_start_ms=1_699_999_000_000,
                class_name='Notepad',
                process_name='notepad.exe',
            )
            win_lease = leases.acquire_lease(
                lease_id='l-win-1',
                owner_run_id='run-uia',
                resource_type='window',
                resource_key=win_key,
            )
            live_win = {
                'exists': True,
                'hwnd': 102400,
                'pid': 4420,
                'process_start_ms': 1_699_999_000_000,
                'class_name': 'Notepad',
                'process_name': 'notepad.exe',
            }

            # 1. Valid semantic UIA background action succeeds without focus theft
            ok_res = router.execute_uia_background_action(
                owner_run_id='run-uia',
                fencing_token=win_lease['fencing_token'],
                leased_window_key=win_key,
                live_window_info=live_win,
                uia_pattern='ValuePattern',
                control_id='Edit1',
                value='Hello background UIA',
            )
            self.assertEqual(ok_res['status'], 'completed')
            self.assertFalse(ok_res['used_host_sendinput'])

            # 2. PC-03: If the window handle is recycled by another PID/class, action aborts immediately
            recycled_win = dict(live_win, pid=9999, class_name='Chrome_WidgetWin_1', process_name='chrome.exe')
            with self.assertRaises(WindowIdentityMismatchError):
                router.execute_uia_background_action(
                    owner_run_id='run-uia',
                    fencing_token=win_lease['fencing_token'],
                    leased_window_key=win_key,
                    live_window_info=recycled_win,
                    uia_pattern='InvokePattern',
                    control_id='Btn1',
                )

            # 3. PC-04: Silent fallback to SendInput is strictly prohibited
            with self.assertRaises(PhysicalFocusProhibitedError):
                router.execute_uia_background_action(
                    owner_run_id='run-uia',
                    fencing_token=win_lease['fencing_token'],
                    leased_window_key=win_key,
                    live_window_info=live_win,
                    uia_pattern='ValuePattern',
                    control_id='Edit1',
                    attempted_silent_sendinput_fallback=True,
                )

            # 4. PC-04: When a control requires physical focus while human is active:
            #    - policy='queue' -> queued (no SendInput)
            #    - policy='ask' -> approval_required
            #    - policy='isolated_only' -> PhysicalFocusProhibitedError
            fg.record_human_activity(now[0])
            queued = router.execute_uia_background_action(
                owner_run_id='run-uia',
                fencing_token=win_lease['fencing_token'],
                leased_window_key=win_key,
                live_window_info=live_win,
                uia_pattern='LegacyNonUiaCanvas',
                control_id='Canvas1',
                requires_physical_focus=True,
                foreground_policy='queue',
            )
            self.assertEqual(queued['status'], 'queued')
            self.assertFalse(queued['executed'])

            ask_res = router.execute_uia_background_action(
                owner_run_id='run-uia',
                fencing_token=win_lease['fencing_token'],
                leased_window_key=win_key,
                live_window_info=live_win,
                uia_pattern='LegacyNonUiaCanvas',
                control_id='Canvas1',
                requires_physical_focus=True,
                foreground_policy='ask',
            )
            self.assertEqual(ask_res['status'], 'approval_required')

            with self.assertRaises(PhysicalFocusProhibitedError):
                router.execute_uia_background_action(
                    owner_run_id='run-uia',
                    fencing_token=win_lease['fencing_token'],
                    leased_window_key=win_key,
                    live_window_info=live_win,
                    uia_pattern='LegacyNonUiaCanvas',
                    control_id='Canvas1',
                    requires_physical_focus=True,
                    foreground_policy='isolated_only',
                )

    def test_pc05_e2e04_and_i10_vm_lifecycle_and_event_correlated_virtual_cursors(self) -> None:
        leases = ResourceLeaseManager(':memory:')
        self.addCleanup(leases.close)
        vms = IsolatedVMProvider(leases, allow_simulated_sandbox=True)

        probe = vms.probe()
        self.assertTrue(probe['available'])
        self.assertFalse(probe['host_mouse_affected'])

        vm = vms.create(vm_id='vm-001', backend='isolated_sandbox_driver')
        self.assertEqual(vm['state'], 'created')
        vms.start('vm-001')

        vm_lease = leases.acquire_lease(
            lease_id='l-vm-1',
            owner_run_id='run-vm',
            resource_type='vm_instance',
            resource_key='vm-001',
        )
        act_res = vms.act(
            vm_id='vm-001',
            owner_run_id='run-vm',
            fencing_token=vm_lease['fencing_token'],
            action_type='guest_click',
            payload={'x': 320, 'y': 240},
        )
        self.assertEqual(act_res['status'], 'completed')
        self.assertFalse(act_res['receipt']['touched_host_mouse'])

        snap = vms.snapshot('vm-001', 'after-click')
        self.assertEqual(snap['action_count'], 1)
        vms.stop('vm-001')
        vms.destroy('vm-001')

        with self.assertRaises(VMUnavailableError):
            vms.act(
                vm_id='vm-001',
                owner_run_id='run-vm',
                fencing_token=vm_lease['fencing_token'],
                action_type='guest_click',
            )

        # I-10: Virtual cursor telemetry rejects unbacked decorative frames
        telemetry = VirtualCursorTelemetryService()
        with self.assertRaises(FabricatedCursorTelemetryError):
            telemetry.emit_cursor_frame(
                cursor_id='cur-1',
                correlating_event_id='fake-nonexistent-event',
                surface_type='isolated_vm',
                x=100,
                y=200,
                action_state='clicking',
            )

        telemetry.register_real_tool_event(
            event_id='ev-tool-101',
            event_type='tool.dispatched',
            run_id='run-vm',
            agent_id='agent-ops',
            workspace_id='ws-vm-1',
            fencing_token=vm_lease['fencing_token'],
        )
        frame = telemetry.emit_cursor_frame(
            cursor_id='cur-1',
            correlating_event_id='ev-tool-101',
            surface_type='isolated_vm',
            x=320,
            y=240,
            action_state='clicking',
        )
        self.assertEqual(frame['correlating_event_id'], 'ev-tool-101')
        self.assertFalse(frame['affects_physical_host_cursor'])


if __name__ == '__main__':
    unittest.main()
