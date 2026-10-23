# Axx automatic skills implementation plan

**Goal:** Reuse verified skills with typed variations, retain task/project context, select eligible free models, and preserve execution across provider changes and restarts.

**Architecture:** Keep the existing Python/SQLite/CommandService execution boundary and native HTML UI. Use additive database migrations, immutable operation identities, model-independent task records, and bounded Windows UI Automation observation. No new remote service is required for the core flow; compatible FreeLLMAPI endpoints remain optional and must satisfy the same free-route policy.

**Spec:** User's `AXX_MODO_AUTOMATICO_MODELOS_Y_MEMORIA.md` and ten-priority pasted proposal, approved for execution on 2026-10-23.

## Constraints
- Preserve local data, credentials, existing approvals, avatar geometry/palettes and radial layout.
- Deterministic reuse uses zero model calls. Inference fallback never repeats commands.
- Automatic free mode rejects unknown cost and billing-enabled routes, including local proxies with unverified downstream cost.
- No learned shell execution, unrestricted GUI replay or arbitrary instructions from recorded content.
- A recorded observation is candidate evidence, never proof of task completion.
- Actual task outcomes, transport reliability and user-confirmed outcomes remain distinct.
- New user request = new task. Retransmission/resume = same task and immutable step operation IDs.
- Unsupported application adapters and unverifiable effects remain explicitly blocked.

## Review focus
Changed parameters reusing operation IDs; restart between effect and result write; ambiguous aliases and project scope; legacy verified entries without evidence; model identity hidden behind an automatic proxy.

## Tasks and ownership

### 1. Skills, operational context, composition and durable learning
Owner: memory worker. Files: backend/action_learning.py, backend/memory/skill_memory.py (new), targeted backend/tests/test_skill_learning.py, existing learning tests as needed. Do not modify commands.py, server.py, inference or UI.
- [x] Add a unified skills view/storage with ID/version, typed schema, examples, templates, objective checks, provenance, favorites/project scope and immutable versions. Migrate learned_actions additively; preserve older Recipe records without silently upgrading their verification.
- [x] Keep ActionLearning constructor and old APIs compatible. Add `configure(action_id, body)`, `resume(key, approved=False)`, `compose(text, parts, operation_id=None, project_id='')`, `context(project_id='')`, `update_context(project_id, body)`.
- [x] Extend `propose(..., inputs=None, project_id='', selection_mode='manual')`; resolve exact IDs/examples first, context references second, model-assisted structured retrieval only when needed. Inputs are validated via CommandService before effects. Missing/ambiguous inputs produce needs_input.
- [x] Plans persist step IDs, input hashes, results before/after each effect; reconcile CommandService results on resume, skip succeeded effects, block unknown effects, preserve cancelled state and bind renewed approval to current plan.
- [x] Compose selected skill versions into a bounded plan (existing eight-step cap); retain provenance and stable IDs. Keep desktop effect execution serialized under its existing lock.
- [x] Store corrections as candidate versions, promote only after successful execution with adequate evidence; distinguish effect verification from goal confirmation. Record model metadata from response.route and use optional adapter.record_outcome when available.
- [x] Cover literal zero-call reuse, parameter variations, ambiguity, restart and no duplicate effects, migration, project isolation and composition with focused tests.

### 2. Automatic free model policy
Owner: inference worker. Files: backend/inference/router.py, adapter.py, provider_settings.py, backend/inference/selection.py (if useful), targeted inference tests. No server/UI/learning edits.
- [x] Add envelope selection_mode ('manual' default, 'automatic_free') and task profiles plan/parameters/repair/vision/code/writing/translation/chat.
- [x] Hard-filter free routes, capabilities/context and enabled/credential/quota state before ordering; automatic mode ignores manual model/provider pins. Never infer downstream gratuity from a loopback address.
- [x] Preserve current manual behavior. Add explicit route cost evidence configuration and curated quality/profile priority; do not advertise unavailable model capabilities.
- [x] Retain bounded existing deadline/attempt limits and genuine route metadata. Handle per-route auth failures without exhausting later eligible routes, while policy/payment blocks keep existing stop behavior.
- [x] Persist outcome metrics separately from HTTP metrics; expose `InferenceAdapter.record_outcome(route, task, outcome)` with validated values, and rank only eligible routes using sufficient observations. Unknown responder gets profile-level attribution.
- [x] Provider settings expose/save validated selection metadata without credentials; preserve old entries and avoid resetting quota-scope information on edits.
- [x] Test payment exclusion, local proxy policy, manual compatibility, eligible fallback, task capabilities, pinned automatic requests, quota scope and outcome attribution.

### 3. Demonstration and application capability inventory
Owner: observation worker. Files: backend/demonstration.py (new), backend/actions/uia_observer.ps1 (new), optional windows_automation.py/windows_apps.py helpers, targeted tests. No commands.py/tools.py/server/UI edits.
- [x] `DemonstrationService(state_path)` supports start(body), status(), stop(body), close(), get(id), list(); capture actual bounded semantic UIA events in an explicitly selected window/process while the user demonstrates. No global key logging, password values, screenshots, unbounded polling or silent background capture.
- [x] Capture event meaning, semantic selectors and observation provenance; stop on window identity loss, time/event cap or explicit stop. Unsupported providers clearly report absence of observations; events are not executable instructions.
- [x] Expose `inventory()` using installed-app and window observations with real supported Axx command IDs, no assumed AutoCAD/Revit/SketchUp/Photoshop integrations.
- [x] Return stopped demonstration as bounded structured reference for ActionLearning planning. Demonstration is a candidate until the approved CommandService plan executes and verifies; do not simulate or claim app-specific replay.
- [x] Tests cover event parsing, secret/password omission, process/window scope, bounds, restart status and inventory truthfulness.

### 4. Native integration and visible library
Owner: root. Files: backend/server.py, 1.AXX/scripts/command-library.js, providers.js, mobile-gateway.js, 1.AXX/Axx.html only where needed, src-tauri IPC allowlist if needed; browser/API tests.
- [x] Wire validated learning configuration/context/compose/resume APIs and demonstration lifecycle/inventory. All calls use authenticated native backend; teardown closes observer.
- [x] Add automatic-free selection alongside manual provider selection and pass it through desktop/mobile requests without overriding personal style/identity.
- [x] Library shows skill names, status, examples, parameters, favorites, projects and revisions. Bind inputs explicitly, compose selected skills, allow corrections and goal confirmation without upgrading unverified legacy evidence.
- [x] Provide Aprende esto in existing radial feature via the commands/library panel; show recording state, selected window, stop/cancel and prepare candidate controls.
- [x] Show real progress, waiting for capacity, resume and uncertain effects; render data with textContent, no injected markup.
- [ ] End-to-end offline contracts and real native smoke/visual checks; build/install and publish only with repository release receipts and verified artifacts.

## Implementation rulings
- Execute the user-approved plan without another approval cycle. Isolated managed worktree keeps unrelated main changes intact.
- Use parallel agents only for disjoint files via dispatching-parallel-agents; root owns integration.
- Application-specific exports require real adapters and cannot be synthesized from a recorded click. Deliver observation/candidate planning with explicit capability gaps; retain this requirement for native adapter work instead of claiming universal support.
- Preserve the eight-step action limit and single owner of desktop input. At most two explicitly independent read operations may run together; desktop effects retain a single owner.

## Progress
Core implementation and controlled integration checks complete. Native delivery remains in progress.

The user subsequently requested six initial model candidates and default anonymous setup through Kilo Gateway, OVHcloud and AI Horde. Candidate identity/evaluation and bounded background setup extend tasks 2 and 4. Models are activated only after actual exact-route task verification; insufficient catalog metadata remains pending.
