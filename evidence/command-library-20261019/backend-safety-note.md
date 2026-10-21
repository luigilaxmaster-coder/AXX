# Backend executor safety review — 2026-10-19

Scope: controlled inspection and regressions of `backend/actions/tools.py`,
`backend/actions/executor.py`, procedural memory, existing HTTP routes and tests.
No library recipes, Blender renders, live inference, microphone recordings,
installations, credential changes or Drive publications were executed.

## Changes

- `backend/actions/tools.py`: file artifacts are created exclusively (`xb`),
  preserving existing files, including hard links. Preconditions no longer create
  directories. Paths reject Windows device/reserved names, alternate streams,
  invalid characters, network/device namespaces and observed symbolic links or
  reparse points. The executor checks the lexical path before resolving it.
- `backend/actions/tools.py`: process inspection uses `OpenProcess` with only
  `SYNCHRONIZE` and immediate `WaitForSingleObject`, instead of parsing `tasklist`.
  PID values must fit a positive Windows DWORD. Inspection failures produce
  errors rather than claiming an inactive process. Process exit code 259 cannot
  masquerade as an active process.
- `backend/actions/executor.py`: unexpected execution or verification exceptions
  preserve `unknown` in SQLite with the complete result. Idempotent replay keeps
  that state and does not repeat the possible effect.
- `backend/actions/tests/test_executor_guards.py`: eight controlled regressions
  covering the above behaviors. All writes use temporary directories. The process
  regression starts only the installed test Python with a fixed exit instruction.

## Evidence

- Baseline: `python -m unittest discover -s backend -p 'test_*.py' -v`:
  45 tests, 2 failures. Log: `baseline-backend.log`.
  Failures: `test_process_state_inspector` and
  `test_real_windows_speech_wav_and_input_guards`.
- Red tests before fixes: `executor-guards-red.log` (7 tests, 11 failed
  assertions including subtests and 1 verification exception).
- Additional real-process reproduction before the final process correction:
  `process-exit259-red.log` (1 failing test).
- Green: `python -m unittest backend.actions.tests.test_executor_guards
  backend.actions.tests.test_action_executor
  backend.memory.tests.test_procedural_memory -v`: 15 tests, all pass.
  Log: `executor-guards-green.log`.
- Full suite after these changes, including command tests added concurrently by
  the main integration: 67 tests, 66 pass, one pre-existing failure:
  `test_real_windows_speech_wav_and_input_guards` returns HTTP 502 instead of 400.
  Log: `backend-after-executor-fixes.log`. Python was 3.14.8.
- Original `tasklist` reproduction returned exit 1, empty stdout and
  `ERRORE: Accesso negato`. The former implementation ignored that exit code.
  Native process inspection passes in the same environment.
- Harmless speech voices discovery returns `SpeechError PROCESS_FAILURE`.
  The file-existence `available` flag alone therefore does not prove SAPI works.

## Existing architecture and integration constraints

There were exactly four registered tools at inspection: `system_telemetry`,
`process_state_inspector`, `file_artifact_writer`, `blender_render_fixture`.
The first three are bounded adapter candidates; Blender should remain disabled
in the imported catalogue until explicitly authorized and tested in this task.

Procedural memory uses SQLite by default, permits only registered tool steps,
matches environment fingerprints and supports deterministic replay. HTTP recipe
registration requires a persisted successful operation with verified
postconditions. Text preconditions stored in historical recipes are documentary;
they are not executable capability checks.

Legacy direct `/actions/execute` and `/recipes/execute` routes need the same new
permission policy as command routes, otherwise a disabled catalogue entry alone
does not disable its underlying registered tool. This was reported to the main
integration owner, who owns those routes and their tests.

The live router code already stops on every HTTP 403, including unclassified
responses. A historical test-module description claiming credential failover is
stale; it does not describe the actual current behavior.

No Python corruption was observed: UTF-8/raw reads are intact and the suites
import the modules. Replacement glyphs seen in some document output reflect
encoding/display issues and do not establish truncated source files.

## Runtime and remaining validation

Python 3.14.8 runs in the default environment. Executing
`C:\Users\luigi\AppData\Local\Programs\Python\Python312\python.exe --version`
under default permissions initially returned OS `Accesso negato`; no escalation
or auto-review rejection occurred in that attempt. The main integration owner
subsequently verified that Python 3.12 can run with escalated execution and owns
the final suite and packaging validation. No installation is required.

## Reversal

Original source snapshots are `tools-before.py` and `executor-before.py` in this
evidence folder. Reverting this subtask restores those two files and removes
`backend/actions/tests/test_executor_guards.py`. Coordinate with the main
integration owner before reversal because its command catalogue relies on the
exclusive-creation behavior.
