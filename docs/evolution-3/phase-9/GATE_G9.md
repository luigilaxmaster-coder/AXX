# Gate G9 Verification Report — AXX Code Studio Core (`PR-13` & `PR-14`)

- **Phase:** 9 (`PR-13`, `PR-14`)
- **Gate:** `G9`
- **Status:** `PASS`
- **Date:** 2026-11-21

## Verified Acceptance Criteria
1. **`SEC-03` (Project Boundary & Windows Reparse/ADS Protection):**
   - Verified `resolve_scoped_project_path` blocks `..` traversal, Windows Alternate Data Streams (`file.py:stream`), UNC paths, protected secret files (`.env`, `endpoint.dpapi`), and Windows directory junctions (`mklink /J`) escaping the project root.
2. **`CODE-01` (Encoding/EOL Preservation, Binary/Large-File Handling & CAS Save Conflict):**
   - Verified exact preservation of `utf-8-sig` BOM and `CRLF` line endings, `BinaryFileError` on null-byte binary files, read-only truncated degraded mode on oversized files, and `CodeConflictError` on stale `expected_sha256`.
3. **`CODE-02` (Concurrent Agent Git Worktrees & Dirty-File Protection):**
   - Verified two concurrent agents create and edit inside isolated worktrees (`axx/agent/agent-a/edit-a`, `axx/agent/agent-b/edit-b`) without touching the primary working copy, and `DirtyWorktreeError` blocks integration into files with uncommitted user edits.
4. **`CODE-03` (Transactional `CodeChangeSet` Apply, TestReceipt & Atomic Rollback):**
   - Verified schema-compliant `CodeChangeSet v1` two-phase atomic application, `SupervisedTestRunner` cryptographic `TestReceipt`, and atomic rollback restoring exact `base_sha256` bytes.

## Execution Evidence
- `python -m unittest backend.tests.test_code_studio_core -v` -> `4 tests in 3.0s — OK`.
