# Phase 9 Specification — AXX Code Studio Core (`PR-13` & `PR-14`, Gate `G9`)

## 1. Objective
Deliver the core transactional code editing, file boundary confinement, isolated per-agent Git worktree management, supervised test runner, and Code Time Machine rollback engine for AXX Code Studio.

## 2. Deliverables
- `backend/code_studio/__init__.py`
- `backend/code_studio/projects.py` (`CodeProjectService`, `resolve_scoped_project_path` blocking `..`, Windows ADS, UNC, secret basenames, and Windows junctions/symlinks `SEC-03`; exact `CRLF`/`LF` and `utf-8`/`utf-8-sig`/`utf-16` preservation `CODE-01`; binary rejection & large-file read-only degradation; CAS `expected_sha256` conflict guard; and Code Time Machine snapshots)
- `backend/code_studio/patch_engine.py` (`validate_code_changeset` against `schemas/code-changeset.schema.json`, two-phase atomic apply, and atomic rollback `CODE-03`)
- `backend/code_studio/git_workspace.py` (`GitWorkspaceService` managing isolated `axx/agent/<agent_id>/<task>` Git worktrees and dirty-file protection `CODE-02` without `git reset --hard` or `git clean -fd`)
- `backend/code_studio/test_runner.py` (`SupervisedTestRunner` with allowlisted executables and verifiable `TestReceipt` `stdout_hash`/`stderr_hash`/`exit_code`)
- `1.AXX/scripts/code-studio/code-workspace.js`, `code-editor.js`, `code-diff.js`, `git-panel.js`, `problems-panel.js`, `terminal-panel.js`
- `backend/tests/test_code_studio_core.py`
