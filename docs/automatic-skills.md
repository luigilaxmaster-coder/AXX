# Automatic skills in Axx

## Component map

| Existing component | Responsibility after this change |
| --- | --- |
| `backend/inference/router.py` and `adapter.py` | One bounded inference boundary; task/capability/context/free-cost eligibility, outcome receipts and fallback |
| `backend/inference/model_candidates.py` and `keyless.py` | Native/gateway identity mapping, representative evaluation, activation and bounded anonymous startup |
| `backend/inference/provider_settings.py` | Existing protected Windows credential storage, connection editing and catalogs |
| `backend/inference/freellmapi.py` | Ready catalog and real named profile validation; managed versus external gateway lifecycle |
| `backend/action_learning.py` | Retrieve, bind, plan, approve, execute, reconcile, repair and compose durable tasks |
| `backend/memory/skill_memory.py` | Additive skill versions, evidence and project context alongside existing procedural tables |
| `backend/commands.py` and `actions/executor.py` | Typed adapters, command approval, immutable operation arguments and real verification |
| `backend/demonstration.py` | Window/process-scoped observation and operational inventory |
| `backend/server.py` | Authenticated loopback APIs and resident recovery lifecycle |
| `providers.js`, `skill-library.js`, `command-library.js` | Model mode, gateway setup, skills, demonstration and approval UI |

The native host and existing main conversation remain the owners of tools,
identity and settings. A gateway does not own task state or command execution.

## Setup and everyday use

1. New installations default to **Automático gratis · Sin claves**. Open
   **Conectar IA → Por API** to select it explicitly on an existing installation.
   Existing explicitly selected manual connections remain available.
2. Axx prepares the pinned FreeLLMAPI gateway, discovers Kilo Gateway, OVHcloud
   AI Endpoints and AI Horde, checks anonymous connectivity and evaluates
   representative tasks. Setup runs in the background with visible progress.
   The user supplies neither a personal API key nor provider/model IDs.
3. Only successful, exact, free task routes become eligible. An unavailable or
   insufficiently described model stays pending. **Comprobar modelos sin claves**
   refreshes discovery and evaluation; paid routes remain excluded. Personal
   connections below this control are optional. Kilo's anonymous service records
   prompts/outputs for training; anonymous routes disallow sensitive requests.
4. Ask for an action, or use `/aprende` followed by the objective. Review the
   commands and inputs before execution. Successful effects acquire evidence;
   user confirmation of the broader objective is stored separately.
5. Open **Mis habilidades** in the existing files/commands panel. Search by name
   or example, choose a project, enter parameters, favorite a skill or modify
   its examples. Advanced templates use `{{parameter}}` and a typed schema.
6. Use **Tareas e historial** to inspect, resume or repair a task. A new request
   starts a new execution; resuming uses the existing task and step IDs.
7. **Aprende esto** selects a real window, observes a demonstration, then
   prepares a candidate using available commands. Escape cancels observation.
   Empty observations cannot prepare a candidate. A stopped observation is
   untrusted reference material, not executable code.

## FreeLLMAPI installation and profiles

The official source build is pinned to commit
`26484157fd15f5fb66f54d3a86f568997ea304de` (0.16.9):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-freellmapi.ps1
```

Installation metadata lives under `%LOCALAPPDATA%/Axx/gateways`; dependencies
and gateway runtime state remain outside the repository and Windows installer.
Setup downloads and verifies the official Node Windows archive when needed; a new installation needs neither preinstalled Node nor Git. It records Node by absolute path, so subsequent launches do not depend on a development shell's PATH. Start the gateway from the provider panel; use the
returned URL, which contains its actual reserved port. Axx reconnects only its
enabled managed instance and terminates only its own process tree. An external
gateway remains under its owner's lifecycle.

For optional personal accounts, add a saved, explicitly free Axx connection to the managed gateway using the
panel's import control. This copies only the selected connection's credential
inside the local backend/gateway boundary. Importing does not perform inference.
Inspect model members, confirm their free accounts and create the named
`axx_parameters`, `axx_chat`, `axx_plan`, `axx_vision`, `axx_code`, `axx_writing`
and `axx_repair` profiles. Translation uses the writing profile. Empty or
unverifiable profiles are not made eligible. Synthetic `auto` entries are
listed separately from actual executable models.

The inference key and dashboard session are different credentials. Managed
sessions are injected server-side; external instances require their own
authenticated dashboard session to validate profile membership. Axx checks
members, readiness and guardrails again before automatic gateway use, reserves
the gateway's attempt bound from the same request budget and prevents a second
outer fallback chain after gateway failure.

Official references: [installation](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/docs/en/install/01-install.md),
[REST API](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/docs/en/api/01-rest-api.md),
[routing](https://github.com/tashfeenahmed/freellmapi/blob/26484157fd15f5fb66f54d3a86f568997ea304de/docs/en/architecture/01-routing-and-bandit-scoring.md).

## Model candidates and measured preferences

`resources/model-candidates.json` preserves the six user-proposed native IDs and
initial task distribution. They are proposals, not claims of account access or
capability. The live catalog records provider, native model ID, canonical group,
gateway database member IDs and the exact gateway execution profile.

**Candidatos iniciales y evaluación** refreshes this mapping. Its representative
fixtures check a valid Axx plan, plan repair, typed parameters, code syntax,
writing, translation, arithmetic and an actual small PNG. Generated commands and
code are inspected, never executed by these evaluation fixtures. Passing a basic
fixture is evidence for that task, not a general benchmark of intelligence.

Automatic anonymous setup stages new routes as `candidate_only`; normal routing
cannot execute them. Successful evaluation creates a dedicated connection for
only the task that passed. An isolated gateway profile ensures the candidate
really responded; simulated responses never enable production routes. Evidence
records quality checks, corrections required, transport reliability and latency.
A refresh can evaluate new candidates; preferences change only with actual
results. Pending task classes retry at five-minute intervals while Axx is open;
successful classes reuse their evidence. Full ready catalogs refresh at six-hour
intervals, with at most two representative evaluations per task per cycle.
Closing Axx cancels the job and its timer. Personal-key candidates require their own configured access.

Catalog discovery, anonymous connectivity, task evaluation, command result
verification and user goal confirmation remain separate evidence categories.
If no model passes a vision/context requirement, that task stays unavailable;
text success is never promoted to visual capability.

## Storage, compatibility and evidence

Migrations add `skill_versions`, `skill_evidence` and `skill_context` to the
existing SQLite state. Existing learned actions and procedural recipes are
retained with their original provenance. A legacy `verified` flag is not
converted into an observed successful execution. Unsupported legacy tool
recipes remain visible but cannot bypass the current typed command policy.

Each task stores the relevant skill/version, bound inputs, step IDs, command
operation IDs, hashes, results, inference counters and route receipts. A
repaired suffix gets new identities while confirmed effects retain theirs.
Cancelled tasks remain cancelled. Arbitrary unknown external effects cannot be
assumed successful; filesystem reconciliation verifies the expected artifact
without rewriting it.

Personal style/language remain in existing companion settings. Project aliases,
folder/document/application references are explicit and isolated by project.
Skill versions carry their own schema and provenance; each task stores its
working state separately. Exact examples/aliases take the deterministic route;
model interpretation is used only when required. No embedding service is added.

Model transport success, command execution success and user confirmation are
different observations. Quality-based ordering requires sufficient execution
observations; initial task priority handles cold start. Inference outcomes are
attributed to a saved route receipt, not an arbitrary caller-supplied model name.

## Diagnosis and validation

- No eligible model: inspect confirmed cost, billing flag, task capabilities,
  context size, credentials and quota. Waiting tasks remain listed. Local
  deterministic skills remain available.
- FreeLLMAPI catalog empty: inspect anonymous setup status; optionally connect/import a personal free account. A synthetic
  `auto` entry does not prove that a model can execute.
- Profile rejected: check the exact member account IDs, disabled automatic
  member inclusion, real readiness, context and bounded gateway retries.
- Unknown result: consult task receipts and artifacts. Do not start a new
  execution to recover the same effect.
- Demonstration empty: the selected application did not expose supported
  semantic accessibility events. Cross-process child controls and arbitrary
  application automation are not inferred from a window title.

Useful checks:

```powershell
python -m unittest backend.tests.test_action_learning backend.tests.test_skill_learning backend.tests.test_skills_http backend.tests.test_demonstration
python -m unittest discover -s backend/inference/tests
$env:AXX_TEST_CHROMIUM='C:\Program Files\Google\Chrome\Application\chrome.exe'
node 1.AXX/scripts/test-skills.cjs --source
```

The browser integration uses a controlled model endpoint and real temporary
files/SQLite. Its measured zero-call reuse is an integration result, not a
benchmark of remote model quality. Source and packaged runs write separate
receipts under `build/automatic-skills-e2e`; native installation verification
uses the repository's build and installed-runtime receipts.

Application-specific exports require real adapters and observed verification.
This release does not label arbitrary AutoCAD, Revit, SketchUp or Photoshop
demonstrations as executable. Unsupported steps remain blocked. Desktop effects
retain a single owner; any parallel work is restricted to explicitly supported
independent reads.
