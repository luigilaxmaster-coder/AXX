# Spatial Intelligence: implementation status

This status describes code and local contract tests. It does not certify a live model response, an installed Windows build, or physical multi-monitor behavior.

| Capability | State | Evidence and limit |
|---|---|---|
| Unified spatial context | Implemented in source | A capture revision, base presentation, selected object, Axx conversation ID, and view state travel through one Magic Pen session. View state is persisted with the query and restored after backend restart. |
| Magic Pen conversation surface | Implemented in source | The expanded panel keeps the question composer anchored while answers scroll, leaves “Visualizar selección” reachable, and tucks provider setup into a disclosure. The provider is never verified just by opening settings. |
| Visual compiler | Implemented in source | Closed `SpatialPresentationPlan v1` and patch schemas validate references, duplicate IDs, finite normalized coordinates, allowed types, and budgets before rendering. SVG text uses `textContent`; no model code is executed. |
| Semantic asset factory | Partial | `backend/spatial_assets.py` keeps five deterministic presets for stored scenes, but they are no longer offered to the model. New 3D answers are built from observed parts with 17 primitives, 12 PBR materials and up to 32 parts. They are conceptual approximations, not CAD, measurements or physics. |
| Local canvas runtime | Implemented in source | Locally packaged Three.js draws allowed primitives and engine components; SVG diagrams and 2D overlays render in the Magic Pen surface. Camera and component changes are local and saved. WebGL is still required at runtime. |
| Voice and teaching | Partial | Existing Axx speech reads each step; desktop captions follow step changes and pause, and a small Spanish command set manipulates selected scene pieces without inference. Captions are not word-timestamp aligned. |
| Guided Computer Use | Partial | The existing UIA guide points out a control and checks whether the user completed a step. This flow does not dispatch actions through `CommandService`; existing command approvals remain separate. |
| Visual QA and readiness | Partial | Backend validates data budgets and references; local checks warn about missing repeated parts, floating pieces, pieces outside the volume and upside-down roofs. Runtime reports WebGL availability, piece count, triangle count and finite camera state. Provider aptitude (a basic two-figure test) is stored per connection and model as verified, declared or unsupported. `GET /axx-api/model-ranking` ranks the models Magic Pen can use: measured aptitude first, then declared claims, then a dated, orientative reference table; `?refresh=1` (the «Actualizar ranking» button) additionally reads, read-only, the catalogs of the owner's saved connections and the local Ollama. Unconnected models are listed with instructions and are never connected or downloaded by Axx. None of this certifies semantic or engineering accuracy. |

## Session API

The additive `/axx-api/feature-readiness` and `/axx-api/spatial/session/*` routes preserve `/v1`. Readiness GET is local-only. Verification calls the provider only after an explicit UI request and with the configured cost policy. A spatial session has an explicit provider and model; it does not fall back to another provider. No credentials or capture pixels are included in the persisted view state.

## Acceptance still required

The installed Windows build must be checked for actual Magic Pen typing, selection, model rendering, keyboard/pointer input, DPI and monitor changes, focus recovery, capture anchoring, WebGL loss, and restart recovery. A successful response from a fixture or provider verification is narrower than this acceptance. Claude requires an explicitly configured authorized API connection; the Codex path requires the existing ChatGPT/Codex account and supported image model.

The comparison document also lists specialist agents, a Chrome extension, general scheduled routines, cross-provider multi-account integrations, correction-trained dictation, document previews, onboarding, and updater rollback. Those are separate product capabilities and are not represented as delivered by the spatial session work.
