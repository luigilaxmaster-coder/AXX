# Gate G10 Verification Report — Background Workspaces, FocusGuard, Leases & VM Provider (`PR-15` & `PR-16`)

- **Phase:** 10 (`PR-15`, `PR-16`)
- **Gate:** `G10`
- **Status:** `PASS`
- **Date:** 2026-11-21

## Verified Acceptance Criteria
1. **`PC-01` & `E2E-03` (Concurrent Isolated Background Browser Workspaces Without Focus Theft):**
   - Verified two concurrent agents create isolated browser profiles and execute DOM actions while the human is actively typing, with zero physical `SendInput` or foreground focus theft, and verified `PersonalBrowserProfileBlockedError` blocks personal default Chrome/Edge profiles.
2. **`PC-02` (Monotonic Fencing Tokens & Emergency Hotkey Revocation):**
   - Verified `ResourceLease v1` exclusive acquisition, strictly increasing `fencing_token`, emergency `Ctrl+Alt+Backspace` revocation (`trigger_emergency_hotkey_revocation()`), and `StaleFencingTokenError` rejecting delayed workers after revocation.
3. **`PC-03` (Composite Window Identity Verification):**
   - Verified `hwnd + pid + process_start_ms + class_name` check aborts execution (`WindowIdentityMismatchError`) when a window closes or its handle is recycled.
4. **`PC-04` & `I-06` (Zero Silent `SendInput` Fallback):**
   - Verified `PhysicalFocusProhibitedError` blocks any silent fallback from UIA/browser to `SendInput`, and verified `queue`, `ask`, `isolated_only`, and `deny` policies under `AttentionGuardian`.
5. **`PC-05`, `E2E-04` & `I-10` (Isolated VM Lifecycle & Event-Correlated Virtual Cursors):**
   - Verified `probe -> create -> start -> act -> snapshot -> stop -> destroy` lifecycle with lease fencing and verified `VirtualCursorTelemetryService` rejects unbacked decorative cursor frames (`FabricatedCursorTelemetryError`).

## Execution Evidence
- `python -m unittest backend.tests.test_background_workspaces -v` -> `4 tests in 0.096s — OK`.
