# Phase 10 Specification — Background Workspaces, FocusGuard, Leases, Virtual Cursors & Isolated VM (`PR-15` & `PR-16`, Gate `G10`)

## 1. Objective
Implement multi-agent background Computer Use without stealing the user's physical mouse, keyboard, or active window focus, enforcing monotonic resource lease fencing tokens, composite Win32 window identity verification, isolated browser profiles, event-correlated virtual cursors, and the isolated VM provider contract.

## 2. Deliverables
- `backend/workspaces/__init__.py`
- `backend/workspaces/leases.py` (`ResourceLeaseManager`, `validate_resource_lease` against `schemas/workspace-lease.schema.json`, monotonic `fencing_token` per `(resource_type, resource_key)`, `StaleFencingTokenError`, `build_window_identity_key`, `verify_window_identity` `PC-02`, `PC-03`)
- `backend/workspaces/focus_guard.py` (`AttentionGuardian`, `foreground_policy` `ask|queue|isolated_only|deny`, zero silent `SendInput` fallback `PC-01`, `PC-04`, `I-06`, and emergency hotkey revocation `Ctrl+Alt+Backspace`)
- `backend/workspaces/browser_sessions.py` (`BrowserSessionManager` with isolated per-agent profile directories and `PersonalBrowserProfileBlockedError` blocking personal Chrome/Edge default profiles `E2E-03`)
- `backend/workspaces/vm_provider.py` (`IsolatedVMProvider` implementing `probe -> create -> start -> act -> snapshot -> stop -> destroy` with lease fencing `PC-05`, `E2E-04`)
- `backend/workspaces/manager.py` (`BackgroundInteractionRouter` and `VirtualCursorTelemetryService` strictly bound to real `tool.dispatched`/`tool.progress`/`tool.completed` events `I-10`)
- `1.AXX/scripts/workspaces/workspace-switcher.js`, `virtual-cursors.js`, `browser-stage.js`, `window-stage.js`, `vm-stage.js`
- `backend/tests/test_background_workspaces.py`
