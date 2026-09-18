# guards

The lessons, as code every stage imports, and the machinery that runs long work
unattended. Not a stage on the belt: the rails the belt runs on.

## Inputs
- none of its own; called by every stage

## Outputs
- exit codes and STOPPING messages that halt work before it produces wrong output

## Invariants
- a verifier re-derives from source and returns 0 / 1 / 2 per `guards/verify.py`
- nothing a reader might open is written in place
- an absent input stops the run; it never reads as empty
- no long job enters a chain without `Invoke-Step`, and no chain is started any
  way but `arm.ps1`

## Code
| file | role |
|---|---|
| `guards/__init__.py` | index of the guards and the learning each enforces |
| `guards/files.py` | atomic writes, absent-input stops, complete lines |
| `guards/alignment.py` | prove a positional cache still matches its source |
| `guards/verify.py` | the verifier exit-code contract |
| `guards/profile.py` | the personal terms, loaded from outside the repo, never guessed |
| `stagepath.py` | where every stage and script lives, so no file hardcodes a relative depth |
| `guards/steps.ps1` | Invoke-Step: preflight, progress, verify, postcondition |
| `guards/arm.ps1` | run a chain as a scheduled task; reap orphans first |
| `guards/rearm_when.ps1` | re-arm a chain when a log says so |
| `guards/paths.py` | every library path in one place |
| `contentarchives/__init__.py` | the reusable package root |

## Tests
- `tests/test_guards.py`
- `tests/test_stagepath.py`
- `tests/test_profile.py`
- `tests/test_paths.py`
- `tests/test_stage_contracts.py`
- `tests/test_chain_gating.py`
- `tests/test_steps.ps1`
- `tests/test_rearm_when.ps1`
- `tests/test_arm_parse.ps1`

## Lessons
| # | what the guards do about it | enforced by |
|---|---|---|
| 6 | a verifier that re-derived nothing has FAILED, not "can't tell" | `guard:guards/verify.py:def verdict`, `test:tests/test_guards.py:nothing re-derived is a failure` |
| 9 | chains are resumable and the task restarts on a kill | `code:guards/arm.ps1:RestartCount` |
| 10 | the checkpoint recalibrates its estimate out loud | `code:guards/steps.ps1:RECALIBRATE` |
| 34 | an absent input stops | `guard:guards/files.py:def require_dir`, `test:tests/test_guards.py:a missing directory stops` |
| 38 | work outlives the session through Task Scheduler, not a hidden window | `code:guards/arm.ps1:Register-ScheduledTask` |
| 39 | re-arming reaps orphaned workers first, by name | `code:guards/arm.ps1:Stop-ChainWorkers` |
| 40 | a real failure writes a halt file the restart loop respects | `code:stages/06_faces/chain_video_faces.ps1:HALTED` |
| 41 | a missing input never returns an empty shape | `guard:guards/files.py:def require_file`, `test:tests/test_guards.py:a missing file stops` |
| 42 | readers see whole files | `guard:guards/files.py:def atomic_writer`, `guard:guards/files.py:def complete_lines`, `test:tests/test_guards.py:a reader never sees a partial file` |
| 43 | a task status is parsed against the tool's vocabulary ("Running", not "Ready") | `code:tools/audit_previous_session.py:schtasks` |
| 44 | a chain that calls Invoke-Step without loading it fails the build | `test:tests/test_chain_gating.py:WITHOUT LOADING IT` |
| 45 | a positional cache is re-derived before use | `guard:guards/alignment.py:def check_alignment`, `test:tests/test_guards.py:a drifted cache is caught` |
| 46 | every Invoke-Step must declare a -Verify that re-derives | `test:tests/test_chain_gating.py:an Invoke-Step has no -Verify`, `test:tests/test_steps.ps1:halted on the verify` |
| 47 | a postcondition that fails is watched failing | `test:tests/test_steps.ps1:halted on the postcondition` |
| 50 | every learning is owned and its enforcement must exist | `test:tests/test_stage_contracts.py:every learning has an owner` |
| 53 | a chain is parsed before it is armed, so one that cannot run is refused while somebody is watching | `code:guards/arm.ps1:ParseFile` |
| 58 | a gate's answer is its LAST emission, so a block that logs cannot accidentally pass | `code:guards/steps.ps1:$out[-1]`, `test:tests/test_steps.ps1:a chatty postcondition still halts` |
