# Phase 12 Specification — Code Studio Pro: Structural Indexer, LSP, DAP & External Git Gate (`PR-18`, Gate `G12`)

## 1. Objective
Complete AXX Code Studio Pro with an incremental AST/symbol reference indexer, supervised Language Server Protocol (LSP) lifecycle with graceful `'degraded_syntax_only'` fallback on crash or missing binaries, loopback-only Debug Adapter Protocol (DAP) sessions with dangerous `evaluate` blocking, bidirectional Code <-> Spatial artifact links, and the external Git push / PR approval gate.

## 2. Deliverables
- `backend/code_studio/indexer.py` (`CodeStructuralIndexer` incremental SHA-256 AST/symbol and syntax diagnostic indexer)
- `backend/code_studio/language_servers.py` (`LanguageServerManager` with allowlisted LSP executables and automatic fallback to `CodeStructuralIndexer` on crash `CODE-04`)
- `backend/code_studio/debug_adapters.py` (`DebugAdapterManager` enforcing `127.0.0.1` loopback binding and blocking unauthorized side-effecting agent `evaluate` expressions `CODE-04`)
- `backend/code_studio/artifact_link.py` (`CodeArtifactLinkService` linking source changesets with Spatial Studio objects `E2E-05` and gating remote `git push`/PR actions on explicit `write_external` approval `CODE-05`)
- `backend/tests/test_code_studio_pro.py`
