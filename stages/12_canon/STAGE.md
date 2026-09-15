# 12 canon

Keep this repository true: regenerate state from disk, publish it redacted, audit
what the last session claimed, and keep the machine itself in a known state.

## Inputs
- artefacts on disk (via 04 inventory), the redaction key, the previous session's claims

## Outputs
- `state/STATE.json`, `state/PROGRESS.md`, `state/origin-folders.csv`
- the audit a resuming session runs first

## Invariants
- project state is counted from disk, never written from memory
- nothing is published that the tripwire matches; the key grows, the tripwire does not shrink
- a resuming session reports every audit failure before building on anything
- a chain armed on purpose is reported as intended work, never as orphans to kill

## Code
| file | role |
|---|---|
| `tools/refresh.py` | recount from disk and update state/, one command |
| `tools/publish_state.py` | publish local state into the repo, redacted, behind a tripwire |
| `tools/audit_previous_session.py` | verify what the previous session actually did |
| `scripts/refresh_and_push.py` | regenerate, verify and push, refusing a false report |
| `tools/machine-hygiene/guard-profile-root.mjs` | refuse loose files in the profile root |
| `tools/machine-hygiene/sweep-profile-root.mjs` | sweep the profile root to the agreed state |
| `tools/machine-hygiene/guard-profile-root.test.mjs` | tests for the profile-root guard |

## Tests
- none in tests/: `tools/machine-hygiene/guard-profile-root.test.mjs` runs under Node (debt: the Python side has none)

## Lessons
| # | what this stage does about it | enforced by |
|---|---|---|
| 13 | collaborating agents are told refusing a wrong-looking instruction is wanted | prose-only |
| 34 | the audit's own checks count real paths, and a zero is investigated | `code:tools/audit_previous_session.py:vacuous` |
